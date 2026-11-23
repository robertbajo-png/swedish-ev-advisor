import assert from 'node:assert/strict';
import {mkdtemp,readFile,realpath,writeFile} from 'node:fs/promises';
import {dirname,join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {PGlite} from '@electric-sql/pglite';
import {anonymousCatalogRows,catalogWithComparableTimes,readPublishedFixture,seedCatalogFixture} from './isolated_catalog_review.mjs';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {applyTouringAtomicLocally,applyTouringRelease,assertTouringIdentityAbsent,buildTouringScopePlan,publicationHash,
  publicationSnapshot} from './new_model_publication.mjs';
import {databaseCatalogHash} from './hyundai_inster_advanced_release_scope.mjs';
import {readTouringCapture} from './toyota_bz4x_touring_publication.mjs';
import {touringCatalogDelta,touringReleaseHash} from './toyota_bz4x_touring_release_scope.mjs';
import {assertExactDcInstalled} from './verify_exact_dc_migration.mjs';

export async function assertTouringSnapshot(client,plan){
  assert.equal((await client.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
  await assertExactDcInstalled(client);
  const rows=async(sql,args)=>(await client.query(sql,args)).rows.map(r=>r.row);
  const {expected_model:model,expected_alias:alias,expected_market:market}=plan;
  const scope={};
  for(const [table,item] of [['canonical_models',model],['model_aliases',alias],['market_models',market]]){
    const includeAlias=table==='canonical_models'?'':' OR (t.brand_raw=$4 AND t.model_raw=$5)';
    scope[table]=await rows(`SELECT to_jsonb(t) AS row FROM public.${table} t
      WHERE t.id=$1 OR (t.normalized_brand=$2 AND t.normalized_model=$3)${includeAlias}`,
      [item.id,model.normalized_brand,model.normalized_model,...(includeAlias?[alias.brand_raw,alias.model_raw]:[])]);
  }
  scope.manufacturer_sources=await rows('SELECT to_jsonb(s) AS row FROM public.manufacturer_sources s WHERE url=ANY($1::text[])',
    [plan.intake.sources.map(s=>s.final_url)]);
  scope.extracted_variant_drafts=await rows('SELECT to_jsonb(d) AS row FROM public.extracted_variant_drafts d WHERE brand=$1 AND model=$2',
    [model.brand,model.model]);
  assertTouringIdentityAbsent(scope,plan);
  return rows('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id');
}

async function main(){
  const {values}=parseArgs({options:{fresh:{type:'string'},'client-module':{type:'string'},'reviewed-scope':{type:'string'}}});
  assert(values.fresh);
  const now=new Date(),root=await realpath('.'),release=join(root,'data','local','release-data');
  assert.equal(await realpath(release),release);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  const source=readTouringCapture(values.fresh);
  const plan=buildTouringScopePlan(source.intake,source.image,now);
  const seal=publicationHash(plan);
  let reviewed;
  if(values['reviewed-scope']){
    const file=resolve(values['reviewed-scope']);
    assert.equal(await realpath(file),file);
    assert.equal(dirname(dirname(file)),release);
    reviewed=JSON.parse(await readFile(file,'utf8'));
  }
  const connector=await openCatalogSnapshot(await catalogConnectorPath(root,values['client-module']));
  let baseline,fixture;
  try{
    baseline=await assertTouringSnapshot(connector.client,plan);
    fixture=await readPublishedFixture(connector.client);
  }finally{await connector.close();}
  const baselineHash=databaseCatalogHash(baseline);
  const db=new PGlite();
  let candidate;
  try{
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db,fixture,[]);
    assert.equal(databaseCatalogHash(await anonymousCatalogRows(db)),baselineHash);
    assert(baseline.some(row=>row.brand==='Toyota'&&row.model==='bZ4X')&&baseline.some(row=>row.brand==='Toyota'&&row.model==='C-Hr+'));
    const snapshot=()=>publicationSnapshot(db,false,{exactJson:true});
    const before=await snapshot(),local=(p=plan,hash=seal)=>applyTouringAtomicLocally(db,p,hash,baselineHash,now);
    const releaseTarget={commit:'1'.repeat(40),reader_sha256:'2'.repeat(64)};
    const apply=reviewed?()=>applyTouringRelease(db,plan,reviewed,releaseTarget,touringReleaseHash(reviewed,releaseTarget),now):local;
    await assert.rejects(applyTouringAtomicLocally({query:()=>assert.fail('remote query attempted')},plan,seal,baselineHash,now),/local PGlite/);
    for(const corrupt of [
      p=>{p.expected_alias.model_raw='BZ4X';},
      p=>{p.intake.drafts[0].facts.tow_kg=1500;},
      p=>{p.image.model_image_notice='Swedish FWD.';},
      p=>{p.intake.market.row.registrations_last_month=372;},
    ]){
      const bad=structuredClone(plan);corrupt(bad);await assert.rejects(local(bad,publicationHash(bad)));
    }
    await db.query(`INSERT INTO public.model_aliases(brand_raw,model_raw,normalized_brand,normalized_model,needs_mapping)
      VALUES('TOYOTA','BZ4X TOURING','toyota','bz4x touring',true)`);
    const collision=await snapshot();
    await assert.rejects(local(),/Existing Touring identity/);
    assert.deepEqual(await snapshot(),collision);
    await db.query("DELETE FROM public.model_aliases WHERE normalized_brand='toyota' AND normalized_model='bz4x touring'");
    assert.deepEqual(await snapshot(),before);
    await db.query(`ALTER TABLE public.canonical_model_variants ADD CONSTRAINT touring_late_failure CHECK (variant_name <> 'Active Tech FWD') NOT VALID`);
    await assert.rejects(apply(),/touring_late_failure/);
    assert.deepEqual(await snapshot(),before);
    assert.equal(databaseCatalogHash(await anonymousCatalogRows(db)),baselineHash);
    await db.query('ALTER TABLE public.canonical_model_variants DROP CONSTRAINT touring_late_failure');
    const result=await apply();
    assert.deepEqual([result.committed,result.atomic_identity,result.anonymous_before_commit,result.variants_inserted],[true,true,true,1]);
    assert.deepEqual(result.canonical_variant_ids,plan.targets.map(t=>t.id));
    candidate=touringCatalogDelta(baseline,await anonymousCatalogRows(db),plan);
    const after=await snapshot();
    const replay=await local();
    assert.deepEqual([replay.committed,replay.already_applied,replay.variants_inserted],[false,true,0]);
    assert.deepEqual(await snapshot(),after);
  }finally{await db.close();}
  const folder=await mkdtemp(join(release,'toyota-touring-local-'));
  const report={status:'touring_local_atomic_rehearsal_verified',public_baseline:baseline.length,local_variants:candidate.length,
    plan_sha256:seal,baseline_sha256:baselineHash,candidate_sha256:databaseCatalogHash(candidate),technical_fields:9,
    late_rollback:true,exact_replay_noop:true,anonymous_before_commit:true,remote_write_rejected:true,scope_conflicts_rejected:true,
    reviewed_transaction_tested:Boolean(reviewed),publication_approved:false,production_writes:0,paid_calls:0};
  for(const [file,data] of Object.entries({report,plan,'baseline-catalog':baseline,
    'candidate-catalog':{status:'local_only',publication_approved:false,catalog_sha256:report.candidate_sha256,
      records:catalogWithComparableTimes(candidate)}}))
    await writeFile(join(folder,file+'.json'),JSON.stringify(data,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({...report,folder}));
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main().catch(error=>{
  console.error(JSON.stringify({status:'touring_rehearsal_held',reason:error.message.split('\n')[0],production_writes:0}));
  process.exitCode=1;
});
