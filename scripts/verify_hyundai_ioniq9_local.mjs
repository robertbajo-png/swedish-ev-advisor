import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtemp,realpath,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {PGlite} from '@electric-sql/pglite';
import {MODEL,policy,readIoniq9Capture} from './hyundai_ioniq9_publication.mjs';
import {anonymousCatalogRows,catalogWithComparableTimes,readCommittedPublicBaseline,readPublishedFixture,
  seedCatalogFixture} from './isolated_catalog_review.mjs';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {applyNewModelPlan,buildNewModelPlan,publicationHash,publicationSnapshot} from './new_model_publication.mjs';
import {catalogHash,compareCatalogs,normalizeCatalog,variantKey} from './sync_public_catalog.mjs';

export async function readIoniq9Snapshot(db,intake){
  assert.equal((await db.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
  if(typeof db.setTypeParser==='function')db.setTypeParser(1082,value=>value);
  const rows=async(table,predicate='',args=[])=>JSON.parse(JSON.stringify((
    await db.query('SELECT t.* FROM public.'+table+' t '+predicate+' ORDER BY id',args)
  ).rows)).map(row=>{
    for(const key of ['month','first_seen_month','last_seen_month'])if(row[key]!=null){
      assert.match(row[key],/^\d{4}-\d{2}-\d{2}(?:T00:00:00\.000Z)?$/);
      row[key]=row[key].slice(0,10);
    }
    return row;
  });
  const only=items=>{assert.equal(items.length,1,'Require just one exact IONIQ 9 discovery record');return items[0];};
  const terms=[MODEL.normalized_brand,MODEL.normalized_model];
  const key='WHERE normalized_brand=$1 AND normalized_model=$2';
  const model=only(await rows('canonical_models',key,terms));
  assert.deepEqual([model.brand,model.model,model.validation_status],[MODEL.brand,MODEL.model,'draft']);
  const alias=only(await rows('model_aliases',key,terms));
  const market=await rows('market_models',key+' OR canonical_model_id=$3',[...terms,model.id]);
  const exact=only(market.filter(m=>m.fuel_type_raw==='EL'&&m.normalized_brand===terms[0]&&m.normalized_model===terms[1]));
  policy.scopedDiscovery.check({market_models:market},model,exact);
  const months=await rows('market_model_monthly_stats','WHERE market_model_id=$1',[exact.id]);
  const sources=await rows('manufacturer_sources','WHERE url=ANY($1::text[])',[intake.sources.map(s=>s.final_url)]);
  assert.equal((await rows('canonical_model_variants','WHERE canonical_model_id=$1',[model.id])).length,0);
  assert.equal((await rows('extracted_variant_drafts','WHERE canonical_model_id=$1 OR (source_url=$2 AND variant_name=$3)',
    [model.id,policy.primaryUrl,intake.drafts[0].variant_name])).length,0);
  const databaseRows=(await db.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')).rows.map(r=>r.row);
  return {fixture:await readPublishedFixture(db),databaseRows,
    expected:{expected_model:model,expected_alias:alias,expected_market:exact,expected_monthly:months,expected_sources:sources}};
}

export async function rehearseIoniq9(scope,intake,image,baseline,now){
  const db=new PGlite();
  try{
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db,scope.fixture,[scope.expected]);
    const initial=await anonymousCatalogRows(db);
    assert(compareCatalogs(catalogWithComparableTimes(baseline),catalogWithComparableTimes(initial)).ok,'Isolated baseline differs from live');
    const before=await publicationSnapshot(db);
    const plan=buildNewModelPlan(before,intake,image,now);
    const apply=(candidate=plan,at=now)=>applyNewModelPlan(db,candidate,publicationHash(candidate),at);
    await assert.rejects(applyNewModelPlan({query:()=>assert.fail('Remote query attempted')},plan,publicationHash(plan),now),/local PGlite/);
    for(const dirty of [
      p=>{p.intake.drafts[0].facts.seats=6;},
      p=>{p.intake.drafts[0].identity_evidence.wheels_inches=21;},
      p=>{p.intake.drafts[0].price_evidence.price_type='list_price';},
      p=>{p.intake.drafts[0].price_evidence.source_url=p.intake.market.source.final_url;},
      p=>{p.image.credit='Incorrect photograph credit';},
    ]){
      const wrong=structuredClone(plan);
      dirty(wrong);
      await assert.rejects(apply(wrong));
    }
    await assert.rejects(apply(plan,new Date(+now+910000)),/Fresh source capture/);
    assert.deepEqual(await publicationSnapshot(db),before);
    await db.exec(`CREATE FUNCTION public.ioniq9_late_failure() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (SELECT count(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id)<>1
          OR (SELECT count(*) FROM public.extracted_variant_drafts WHERE canonical_model_id=NEW.canonical_model_id)<>1
        THEN RAISE EXCEPTION 'IONIQ 9 rollback probe did not reach both insertions'; END IF;
        RAISE EXCEPTION 'IONIQ 9 late rollback probe';
      END $$;
      CREATE TRIGGER ioniq9_late_failure BEFORE UPDATE ON public.market_models
        FOR EACH ROW EXECUTE FUNCTION public.ioniq9_late_failure()`);
    await assert.rejects(apply(),error=>{
      if(!/IONIQ 9 late rollback probe/.test(error.message))throw error;
      return true;
    });
    assert.deepEqual(await publicationSnapshot(db),before,'Late failure left changes');
    assert.deepEqual(await anonymousCatalogRows(db),initial);
    await db.exec('DROP TRIGGER ioniq9_late_failure ON public.market_models');
    const receipt=await apply();
    assert.deepEqual([receipt.committed,receipt.variants_inserted,receipt.anonymous_before_commit],[true,1,true]);
    const after=await publicationSnapshot(db);
    assert.equal((await apply()).already_applied,true);
    assert.deepEqual(await publicationSnapshot(db),after,'Exact replay changed rows');
    const publishedRows=await anonymousCatalogRows(db);
    const [id]=receipt.canonical_variant_ids;
    assert.deepEqual(publishedRows.filter(row=>row.id!==id),initial,'Existing variants changed');
    const added=publishedRows.filter(row=>row.id===id);
    policy.verifyPublic(added,plan);
    const oldMonths=new Set(before.market_model_monthly_stats.map(r=>r.id));
    assert.deepEqual(after.market_model_monthly_stats.filter(r=>oldMonths.has(r.id)),before.market_model_monthly_stats);
    return {plan,added};
  }finally{await db.close();}
}

async function main(){
  const {values}=parseArgs({options:{review:{type:'string'},'client-module':{type:'string'}}});
  assert(values.review,'Supply an unchanged IONIQ 9 source capture');
  const root=await realpath('.');
  const release=await realpath('data/local/release-data');
  assert.equal(release,join(root,'data','local','release-data'));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  const {intake,image,reviewHash}=readIoniq9Capture(values.review);
  const snapshot=await openCatalogSnapshot(await catalogConnectorPath(root,values['client-module']));
  let scope;
  try{scope=await readIoniq9Snapshot(snapshot.client,intake);}finally{await snapshot.close();}
  const folder=await mkdtemp(join(release,'hyundai-ioniq9-local-'));
  const {base,proof}=await readCommittedPublicBaseline(release,folder,{imageTools:true});
  assert.equal(execFileSync('git',['ls-remote','origin','refs/heads/main'],{encoding:'utf8',timeout:20000}).trim(),
    proof.commit+'\trefs/heads/main','Local origin/main is stale');
  assert(compareCatalogs(catalogWithComparableTimes(base),catalogWithComparableTimes(scope.databaseRows)).ok,'Live export differs from canonical data');
  const {plan,added}=await rehearseIoniq9(scope,intake,image,base,new Date());
  const records=normalizeCatalog([...base,...catalogWithComparableTimes(added)]),old=new Set(base.map(variantKey));
  assert.equal(records.length,base.length+1);
  assert.deepEqual(records.filter(row=>old.has(variantKey(row))),base);
  const report={status:'ioniq9_local_insertion_verified',...proof,technical_fields:9,candidate_count:records.length,
    candidate_sha256:catalogHash(records),plan_sha256:publicationHash(plan),review_sha256:reviewHash,
    historical_months_preserved:plan.expected_monthly.length,late_rollback:true,exact_replay_noop:true,anonymous_before_commit:true,
    publication_approved:false,production_writes:0,paid_calls:0};
  const save=(name,data)=>writeFile(join(folder,name),JSON.stringify(data,null,2)+'\n',{flag:'wx'});
  await save('candidate-catalog.json',{status:'local_only',publication_approved:false,records});
  await save('plan.json',plan);
  await save('report.json',report);
  console.log(JSON.stringify({...report,folder}));
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main().catch(error=>{
  console.error(JSON.stringify({status:'held',reason:error.message.split('\n')[0],
    location:error.stack?.split('\n').find(line=>/\.mjs:\d+:\d+/.test(line))?.trim(),production_writes:0}));
  process.exitCode=1;
});
