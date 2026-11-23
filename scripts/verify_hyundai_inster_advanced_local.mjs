import assert from 'node:assert/strict';
import {mkdtemp,readFile,realpath,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {PGlite} from '@electric-sql/pglite';
import {MODEL,policy,readInsterCapture} from './hyundai_inster_advanced_publication.mjs';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {anonymousCatalogRows,catalogWithComparableTimes,readPublishedFixture,seedCatalogFixture} from './isolated_catalog_review.mjs';
import {applyNewModelPlan,buildNewModelPlan,publicationHash,publicationSnapshot} from './new_model_publication.mjs';
import {catalogHash,compareCatalogs,normalizeCatalog,variantKey} from './sync_public_catalog.mjs';
import {assertExactDcInstalled} from './verify_exact_dc_migration.mjs';

const one=(rows,label)=>{assert.equal(rows.length,1,'Require one exact Inster '+label);return rows[0];};
const normalDc=snapshot=>({...snapshot,...Object.fromEntries(['canonical_model_variants','extracted_variant_drafts'].map(table=>
  [table,snapshot[table].map(r=>({...r,dc_charge_kw:r.dc_charge_kw===null?null:Number(r.dc_charge_kw)}))]))});

async function readScope(db,intake){
  assert.equal((await db.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
  assert.equal((await db.query('SHOW transaction_isolation')).rows[0].transaction_isolation,'repeatable read');
  const rows=async(sql,args)=>(await db.query(sql,args)).rows.map(({row})=>row);
  const key=[MODEL.normalized_brand,MODEL.normalized_model];
  const filter='normalized_brand=$1 AND normalized_model=$2';
  const expected_model=one(await rows('SELECT to_jsonb(m) AS row FROM public.canonical_models m WHERE '+filter,key),'draft');
  const id=expected_model.id;
  assert.deepEqual([expected_model.brand,expected_model.model,expected_model.validation_status],
    [MODEL.brand,MODEL.model,'draft']);
  assert(!expected_model.image_url,'Existing Inster model image needs separate review');
  const expected_alias=one(await rows('SELECT to_jsonb(a) AS row FROM public.model_aliases a WHERE ('+filter+') OR canonical_model_id=$3',
    [...key,id]),'alias');
  assert.deepEqual([expected_alias.brand_raw,expected_alias.model_raw,expected_alias.canonical_model_id,
    expected_alias.needs_mapping,expected_alias.alias_rule],['HYUNDAI','INSTER',id,false,policy.aliasRule]);
  const expected_market=one(await rows('SELECT to_jsonb(m) AS row FROM public.market_models m WHERE ('+filter+') OR canonical_model_id=$3',
    [...key,id]),'market row');
  assert.equal(expected_market.fuel_type_raw,'EL');
  const expected_monthly=await rows('SELECT to_jsonb(s) AS row FROM public.market_model_monthly_stats s WHERE market_model_id=$1 ORDER BY id',
    [expected_market.id]);
  const expected_sources=await rows('SELECT to_jsonb(s) AS row FROM public.manufacturer_sources s WHERE url=ANY($1::text[]) ORDER BY id',
    [intake.sources.map(s=>s.final_url)]);
  assert(expected_sources.every(s=>s.canonical_model_id===null||s.canonical_model_id===id),
    'An evidence URL belongs to another canonical model');
  for(const target of ['canonical_model_variants','extracted_variant_drafts']){
    assert.equal((await db.query('SELECT id FROM public.'+target+' WHERE canonical_model_id=$1',[id])).rows.length,0);
  }
  let productionExactDc=true;
  try{await assertExactDcInstalled(db);}catch(error){
    if(!/Migration 027 is required/.test(error.message))throw error;
    productionExactDc=false;
  }
  return {expected:{expected_model,expected_alias,expected_market,expected_monthly,expected_sources},productionExactDc,
    fixture:await readPublishedFixture(db),publicRows:await rows('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')};
}

async function rehearse(scope,intake,image,now){
  const db=new PGlite();
  try{
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db,scope.fixture,[scope.expected]);
    const initial=await anonymousCatalogRows(db);
    assert(compareCatalogs(catalogWithComparableTimes(scope.publicRows),catalogWithComparableTimes(initial)).ok,
      'Isolated starting catalog does not match the live canonical view');
    const before=await publicationSnapshot(db);
    const plan=buildNewModelPlan(before,intake,image,now);
    const apply=(p=plan,at=now)=>applyNewModelPlan(db,p,publicationHash(p),at);
    await assert.rejects(applyNewModelPlan({query:()=>assert.fail('Remote write attempted')},plan,publicationHash(plan),now),/local PGlite/);
    await assert.rejects(apply(),/Migration 027 is required/);
    assert.deepEqual(await publicationSnapshot(db),before,'Pre-migration failure wrote data');
    const migration=await readFile(new URL('../database/migrations/027_exact_dc_charging.sql',import.meta.url),'utf8');
    await db.exec(migration);
    await assertExactDcInstalled(db);
    assert.deepEqual(await anonymousCatalogRows(db),initial,'Decimal migration changed prior public rows or values');
    const migrated=await publicationSnapshot(db);
    assert.deepEqual(normalDc(migrated),normalDc(before),'Decimal migration changed previously stored facts');
    for(const mutate of [
      p=>{p.intake.drafts[0].facts.dc_charge_kw=85;},
      p=>{p.intake.drafts[0].facts.seats=5;},
      p=>{p.intake.drafts[0].identity_evidence.wheels_inches=15;},
      p=>{p.intake.drafts[0].price_evidence.value=354900;},
      p=>{p.intake.drafts[0].price_evidence.value=385400;},
      p=>{p.image.model_key='hyundai|inster cross';},
    ]){
      const wrong=structuredClone(plan);mutate(wrong);
      await assert.rejects(apply(wrong));
    }
    await assert.rejects(apply(plan,new Date(+now+910000)),/Fresh source capture/);
    const changedAlias=structuredClone(plan);
    changedAlias.expected_alias.confidence=0.9;
    await assert.rejects(apply(changedAlias),/Concurrent alias change/);
    const collision=structuredClone(plan);
    collision.targets[0].id=initial[0].id;
    await assert.rejects(apply(collision),/Publication scope changed/);
    await db.exec(`CREATE FUNCTION public.inster_rollback_probe() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id AND dc_charge_kw=85.30)
          OR NOT EXISTS (SELECT 1 FROM public.extracted_variant_drafts WHERE canonical_model_id=NEW.canonical_model_id AND dc_charge_kw=85.30)
        THEN RAISE EXCEPTION 'Inster probe did not reach both decimal writes'; END IF;
        RAISE EXCEPTION 'Inster late rollback probe';
      END $$;
      CREATE TRIGGER inster_rollback_probe BEFORE UPDATE ON public.market_models
        FOR EACH ROW EXECUTE FUNCTION public.inster_rollback_probe()`);
    await assert.rejects(apply(),/Inster late rollback probe/);
    assert.deepEqual(await publicationSnapshot(db),migrated);
    assert.deepEqual(await anonymousCatalogRows(db),initial);
    await db.exec('DROP TRIGGER inster_rollback_probe ON public.market_models');
    const result=await apply();
    assert.deepEqual([result.committed,result.variants_inserted,result.anonymous_before_commit],[true,1,true]);
    const after=await publicationSnapshot(db),visible=await anonymousCatalogRows(db);
    assert.equal((await apply()).already_applied,true);
    assert.deepEqual(await publicationSnapshot(db),after);
    const [id]=result.canonical_variant_ids;
    assert.deepEqual(visible.filter(r=>r.id!==id),initial);
    policy.verifyPublic(visible.filter(r=>r.id===id),plan);
    const methodRows=await db.query(`SELECT
      (SELECT dc_charge_kw::text FROM public.canonical_model_variants WHERE id=$1) AS canonical,
      (SELECT dc_charge_kw::text FROM public.extracted_variant_drafts WHERE canonical_model_id=$2) AS extracted,
      (SELECT dc_charge_kw::text FROM public.public_ev_variants WHERE id=$1) AS public_value`,[id,scope.expected.expected_model.id]);
    assert(Object.values(methodRows.rows[0]).every(value=>Number(value)===85.3));
    const history=new Set(before.market_model_monthly_stats.map(r=>r.id));
    assert.deepEqual(after.market_model_monthly_stats.filter(r=>history.has(r.id)),before.market_model_monthly_stats);
    const report={status:'inster_advanced_atomic_local_verified',canonical_baseline:initial.length,local_variants:visible.length,
      technical_fields:9,dc_kw:85.3,price_sek:377900,seats:4,decimal_projections:methodRows.rows[0],
      live_decimal_migration_verified:scope.productionExactDc,pre_migration_write_rejected:true,
      remote_write_rejected:true,scope_conflicts_rejected:true,late_rollback:true,exact_replay_noop:true,
      historical_months_preserved:history.size,production_writes:0,paid_calls:0,publication_approved:false};
    return {report,added:visible.find(r=>r.id===id)};
  }finally{await db.close();}
}

async function main(){
  const {values}=parseArgs({options:{intake:{type:'string'},'client-module':{type:'string'}}});
  assert(values.intake,'Supply a fresh exact Inster bundle');
  const root=await realpath('.'),release=join(root,'data','local','release-data');
  assert.equal(await realpath(release),release);
  const connectorPath=await catalogConnectorPath(root,values['client-module']);
  const {intake,image,receipt_sha256}=readInsterCapture(values.intake,connectorPath.sourceRoot);
  const session=await openCatalogSnapshot(connectorPath);
  let scope;
  try{scope=await readScope(session.client,intake);}finally{await session.close();}
  const {report:local,added}=await rehearse(scope,intake,image,new Date());
  const base=catalogWithComparableTimes(scope.publicRows);
  const existing=new Set(base.map(variantKey));
  const records=normalizeCatalog([...base,...catalogWithComparableTimes([added])]);
  assert.deepEqual(records.filter(row=>existing.has(variantKey(row))),base);
  assert.equal(records.length,base.length+1);
  const report={...local,receipt_sha256,candidate_sha256:catalogHash(records)};
  const folder=await mkdtemp(join(release,'inster-advanced-local-'));
  await writeFile(join(folder,'candidate-catalog.json'),JSON.stringify({
    status:'local_only',publication_approved:false,catalog_sha256:report.candidate_sha256,records,
  },null,2)+'\n',{flag:'wx'});
  await writeFile(join(folder,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({...report,folder}));
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main().catch(error=>{
  console.error(JSON.stringify({status:'held',reason:error.code==='ERR_ASSERTION'
    ?error.message.split('\n')[0]:'Inster rehearsal could not be verified',production_writes:0}));
  process.exitCode=1;
});
