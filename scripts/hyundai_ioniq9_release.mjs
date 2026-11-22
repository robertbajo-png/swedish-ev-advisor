import assert from 'node:assert/strict';
import {ADAPTER,policy} from './hyundai_ioniq9_publication.mjs';
import {catalogWithComparableTimes} from './isolated_catalog_review.mjs';
import {assertGlbPriceMigration as assertStartingPriceMigration} from './mercedes_glb_release.mjs';
import {buildNewModelPlan,publicationHash,validateNewModelIntake} from './new_model_publication.mjs';
import {catalogHash,normalizeCatalog,variantKey} from './sync_public_catalog.mjs';

export {assertStartingPriceMigration};
const sha=/^[a-f0-9]{64}$/;
const revision=/^[a-f0-9]{40}$/;
export const databaseCatalogHash=rows=>catalogHash(catalogWithComparableTimes(rows));
const receipts=intake=>[...intake.sources,intake.market.source,intake.market.article,
  ...['downloads','factory_trim','factory_wltp'].map(key=>intake.source_decisions[key])];
const stable=value=>JSON.parse(JSON.stringify(value,(key,entry)=>
  ['fetched_at','content_hash','source_hash'].includes(key)?undefined:entry));

export function assertIoniq9PublishedRows(rows,plan,{ids=true}={}){
  assert.equal(plan.adapter,ADAPTER);
  policy.verifyPublic(rows,plan);
  const [row]=rows,[{id,draft}]=plan.targets;
  const primary=plan.intake.sources.find(source=>source.final_url===policy.primaryUrl);
  const p=draft.price_evidence,price=plan.intake.sources.find(source=>source.final_url===p.source_url);
  if(ids)assert.deepEqual([row.id,row.canonical_model_id],[id,plan.expected_model.id]);
  assert.equal(row.source_hash,primary.content_hash);
  assert.equal(row.source_quote,[...new Set(Object.values(draft.field_evidence).map(f=>f.source_url+' | '+f.quote))].join(' | '));
  assert.deepEqual([row.price_source_hash,row.price_source_quote,row.price_source_name,Date.parse(row.price_verified_at)],
    [p.source_hash,p.quote,price.source_name,Date.parse(price.fetched_at)]);
  for(const flag of ['available_confirmed','discontinued_candidate','coming_or_low_volume'])
    assert.equal(row[flag],plan.expected_model[flag],'IONIQ 9 status changed: '+flag);
}

export function ioniq9CatalogDelta(baseline,rows,plan,options){
  const prior=new Set(baseline.map(variantKey));
  assert.equal(databaseCatalogHash(rows.filter(row=>prior.has(variantKey(row)))),databaseCatalogHash(baseline),
    'An incumbent catalog row changed');
  const added=rows.filter(row=>!prior.has(variantKey(row)));
  assert.equal(added.length,1,'Require exactly one IONIQ 9 variant');
  assertIoniq9PublishedRows(added,plan,options);
  return normalizeCatalog([...baseline,...catalogWithComparableTimes(added)]);
}

export function createIoniq9Scope({plan,report,ui,seo,baseline,candidate,code,media}){
  assert.equal(plan.adapter,ADAPTER);
  assert.deepEqual([report.status,report.technical_fields,report.late_rollback,report.exact_replay_noop,
    report.anonymous_before_commit,report.publication_approved,report.production_writes],
  ['ioniq9_local_insertion_verified',9,true,true,true,false,0]);
  assert.match(report.commit,revision);
  assert.equal(report.baseline_count,baseline.length);
  assert.equal(report.plan_sha256,publicationHash(plan));
  assert.equal(report.baseline_sha256,catalogHash(baseline));
  assert.equal(report.candidate_sha256,catalogHash(candidate));
  assert.equal(report.candidate_sha256,catalogHash(ioniq9CatalogDelta(baseline,candidate,plan,{ids:false})));
  assert.deepEqual([ui.status,ui.catalog_sha256,ui.comparison,ui.existing_records,ui.publication_approved,ui.production_writes],
    ['ioniq9_private_ui_verified',report.candidate_sha256,true,baseline.length,false,0]);
  assert.deepEqual(ui.checks.map(check=>check.viewport),[320,390,1440]);
  const responsive=plan.image.asset_url.replace('/vehicles/','/responsive/').replace(/\.jpg$/,'-746.webp');
  assert.deepEqual(media.map(item=>item.url),[plan.image.asset_url,responsive]);
  assert(media.every(item=>sha.test(item.sha256)));
  assert.equal(media[0].sha256,plan.image.content_sha256);
  assert(ui.checks.every(check=>check.asset===responsive));
  assert.deepEqual([seo.status,seo.catalog_sha256,seo.fixed_offer,seo.production_writes,seo.publication_approved],
    ['ioniq9_static_preview_verified',report.candidate_sha256,false,0,false]);
  assert.equal(seo.added,'https://elbilsagenten.se/bilar/hyundai-ioniq-9-advanced-awd-7-sits-my27');
  assert(seo.news_articles_preserved>0);
  assert.equal(seo.candidate_urls,seo.existing_urls+1);
  assert(Object.keys(code).length>0&&Object.values(code).every(digest=>sha.test(digest)));
  return {status:'ioniq9_release_scope_private',plan,plan_sha256:report.plan_sha256,baseline_commit:report.commit,
    baseline_count:baseline.length,baseline_sha256:report.baseline_sha256,database_baseline_sha256:databaseCatalogHash(baseline),
    candidate_sha256:report.candidate_sha256,code,media,seo,publication_approved:false};
}

export function ioniq9ReleaseHash(scope,{commit,reader_sha256}){
  assert.deepEqual([scope.status,scope.publication_approved,scope.plan.adapter],['ioniq9_release_scope_private',false,ADAPTER]);
  assert.match(commit,revision);
  assert.match(reader_sha256,sha);
  return publicationHash({scope,commit,reader_sha256});
}

export function proveIoniq9Release(scope,fresh,target,seal,now){
  assert.equal(seal,ioniq9ReleaseHash(scope,target),'Require the exact reviewed IONIQ 9 scope');
  assert.equal(scope.plan_sha256,publicationHash(scope.plan),'Reviewed IONIQ 9 plan changed');
  assert.deepEqual([fresh.adapter,validateNewModelIntake(fresh.intake,now).adapter],[ADAPTER,ADAPTER]);
  for(const key of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources','image'])
    assert.deepEqual(fresh[key],scope.plan[key],'IONIQ 9 identity, history or media changed: '+key);
  const previous=receipts(scope.plan.intake),current=receipts(fresh.intake);
  const parsed=list=>list.map(item=>Date.parse(item.fetched_at));
  assert(parsed(current).every(time=>time>=+now-900000&&time<=+now+60000),'Expired or invalid IONIQ 9 receipt');
  assert(Math.min(...parsed(current))>Math.max(...parsed(previous)),'Require new official source capture after review');
  assert.deepEqual(stable(fresh.intake),stable(scope.plan.intake),'IONIQ 9 source values or literal evidence changed');
  assert.deepEqual(stable(fresh.targets),stable(scope.plan.targets),'IONIQ 9 release targets changed');
}

export function buildIoniq9ReleasePlan({expected},intake,image,now){
  return buildNewModelPlan({canonical_models:[expected.expected_model],canonical_model_variants:[],
    model_aliases:[expected.expected_alias],market_models:[expected.expected_market],
    market_model_monthly_stats:expected.expected_monthly,manufacturer_sources:expected.expected_sources},intake,image,now);
}

export async function runIoniq9Release({mode,scope,target,seal},io){
  assert(['check','commit','export'].includes(mode));
  const required=ioniq9ReleaseHash(scope,target);
  if(mode!=='check')assert.equal(seal,required,'IONIQ 9 release seal mismatch');
  await io.verifyProduction(scope,target);
  const baseline=await io.baseline(target.commit);
  assert.equal(catalogHash(baseline),scope.baseline_sha256,'Committed catalog baseline changed');
  assert.equal(catalogHash(await io.liveBaseline()),scope.baseline_sha256,'Deployed catalog baseline changed');
  const assertCommit=(result,plan)=>{
    assert.deepEqual([result.committed,result.variants_inserted,result.anonymous_before_commit,result.paid_calls],[true,1,true,0]);
    assert.equal(result.publication_batch_id,publicationHash(plan));
    assert.deepEqual(result.canonical_variant_ids,plan.targets.map(target=>target.id));
  };
  if(mode==='export'){
    const {attempt,receipt}=await io.readJournal();
    assert.deepEqual([attempt.seal,attempt.target],[required,target]);
    proveIoniq9Release(scope,attempt.plan,target,required,
      new Date(Math.max(...receipts(attempt.plan.intake).map(item=>Date.parse(item.fetched_at)))));
    assert.equal(receipt.attempt_sha256,publicationHash(attempt),'Commit receipt and journal do not match');
    assertCommit(receipt.result,attempt.plan);
    const rows=await io.publicRows(),records=ioniq9CatalogDelta(baseline,rows,attempt.plan);
    assert.equal(databaseCatalogHash(await io.publicRows()),databaseCatalogHash(rows),'Catalog changed during export');
    await io.saveExport(records);
    return {status:'private_ioniq9_export_verified',catalog_sha256:catalogHash(records),added:1,deployed:false,paid_calls:0};
  }
  const checkBaseline=async()=>assert.equal(databaseCatalogHash(await io.publicRows()),scope.database_baseline_sha256,
    'Anonymous Supabase baseline changed');
  await checkBaseline();
  const {intake,image}=await io.freshSource();
  const client=await io.openSnapshot();
  try{
    await assertStartingPriceMigration(client);
    const fresh=buildIoniq9ReleasePlan(await io.readSnapshot(client,intake),intake,image,io.now());
    proveIoniq9Release(scope,fresh,target,required,io.now());
    if(mode==='check')return {status:'ioniq9_read_only_preflight_passed',scope_sha256:required,variants:1,production_writes:0,paid_calls:0};
    await checkBaseline();
    await io.verifyProduction(scope,target);
    const attempt={seal:required,target,plan:fresh};
    await io.saveAttempt(attempt);
    const result=await io.commit(client,fresh,required);
    assertCommit(result,fresh);
    await io.saveCommit({attempt_sha256:publicationHash(attempt),result});
    return {status:'ioniq9_committed_private_export_pending',added:1,deployed:false,paid_calls:0};
  }finally{await io.closeSnapshot(client);}
}
