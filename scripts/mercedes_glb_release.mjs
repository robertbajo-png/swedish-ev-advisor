import assert from 'node:assert/strict';
import {ADAPTER,policy} from './mercedes_glb_publication.mjs';
import {catalogWithComparableTimes} from './isolated_catalog_review.mjs';
import {buildNewModelPlan,publicationHash,validateNewModelIntake} from './new_model_publication.mjs';
import {catalogHash,normalizeCatalog,variantKey} from './sync_public_catalog.mjs';

const sha=/^[a-f0-9]{64}$/;
const revision=/^[a-f0-9]{40}$/;
export const glbCatalogHash=rows=>catalogHash(catalogWithComparableTimes(rows));
const receipts=intake=>[...intake.sources,intake.market.source,intake.market.article];
const withoutReceiptDrift=value=>JSON.parse(JSON.stringify(value,(key,entry)=>
  ['fetched_at','content_hash','source_hash'].includes(key)?undefined:entry));

export function assertGlbPublishedRows(rows,plan,{checkIds=true}={}) {
  assert.equal(plan.adapter,ADAPTER);
  policy.verifyPublic(rows,plan);
  const primary=plan.intake.sources.find(source=>source.final_url===policy.primaryUrl);
  for(const {id,draft} of plan.targets) {
    const row=rows.find(item=>checkIds?item.id===id:item.variant_name===draft.variant_name), p=draft.price_evidence;
    const priceSource=plan.intake.sources.find(source=>source.final_url===p.source_url);
    assert.equal(row?.variant_name,draft.variant_name,'Exact GLB variant ID and name required');
    if(checkIds)assert.equal(row.canonical_model_id,plan.expected_model.id);
    assert.equal(row.source_hash,primary.content_hash);
    assert.equal(row.source_quote,[...new Set(Object.values(draft.field_evidence).map(f=>f.source_url+' | '+f.quote))].join(' | '));
    assert.deepEqual([row.price_source_hash,row.price_source_quote,row.price_source_name,Date.parse(row.price_verified_at)],
      [p.source_hash,p.quote,priceSource.source_name,Date.parse(priceSource.fetched_at)],'Published GLB starting-price proof changed');
    for(const flag of ['available_confirmed','discontinued_candidate','coming_or_low_volume'])
      assert.equal(row[flag],plan.expected_model[flag],'GLB market flag changed: '+flag);
  }
}

export function glbCatalogDelta(baseline,rows,plan,options) {
  const old=new Set(baseline.map(variantKey));
  assert.equal(glbCatalogHash(rows.filter(row=>old.has(variantKey(row)))),glbCatalogHash(baseline),'Existing GLB catalog baseline rows changed');
  const added=rows.filter(row=>!old.has(variantKey(row)));
  assert.equal(added.length,2,'Require exactly two new GLB variants');
  assertGlbPublishedRows(added,plan,options);
  return normalizeCatalog([...baseline,...catalogWithComparableTimes(added)]);
}

export function createGlbScope({plan,report,ui,baseline,candidate,code,media}) {
  assert.equal(plan.adapter,ADAPTER);
  assert.deepEqual([report.status,report.variants,report.technical_fields,report.exact_replay_noop,report.late_rollback,
    report.anonymous_before_commit,report.starting_price_migration_local,report.publication_approved,report.production_writes],
  ['glb_local_insertion_verified',2,18,true,true,true,true,false,0]);
  assert.match(report.commit,revision);
  assert.equal(report.plan_sha256,publicationHash(plan));
  assert.equal(report.baseline_sha256,catalogHash(baseline));
  assert.equal(report.baseline_count,baseline.length);
  assert.equal(report.candidate_sha256,catalogHash(candidate));
  assert.equal(report.candidate_sha256,catalogHash(glbCatalogDelta(baseline,candidate,plan,{checkIds:false})));
  assert.deepEqual([ui.status,ui.catalog_sha256,ui.existing_routes_preserved,ui.comparison,ui.inventory_copy_removed,
    ui.legacy_inventory_detail_checked,ui.publication_approved,ui.production_writes],
  ['glb_private_ui_verified',report.candidate_sha256,baseline.length,true,true,true,false,0]);
  assert.deepEqual(ui.checks.map(check=>[check.viewport,check.variant]).sort(),[320,390,1440].flatMap(width=>
    plan.targets.map(target=>[width,target.draft.variant_name])).sort());
  assert(Array.isArray(media)&&media.length===3);
  const expectedUrl=width=>plan.image.asset_url.replace('/vehicles/','/responsive/').replace(/\.jpg$/,'-'+width+'.webp');
  assert.deepEqual(media.map(item=>item.url),[plan.image.asset_url,expectedUrl(746),expectedUrl(1782)]);
  assert(media.every(item=>sha.test(item.sha256)));
  assert.equal(media[0].sha256,plan.image.content_sha256);
  for(const check of ui.checks)assert.equal(check.asset,expectedUrl(check.viewport<800?746:1782));
  assert(Object.keys(code).length>0&&Object.values(code).every(digest=>sha.test(digest)));
  return {status:'glb_release_scope_private',plan,plan_sha256:report.plan_sha256,baseline_commit:report.commit,
    baseline_count:baseline.length,baseline_sha256:report.baseline_sha256,database_baseline_sha256:glbCatalogHash(baseline),
    candidate_sha256:report.candidate_sha256,code,media,publication_approved:false};
}

export function glbApprovalHash(scope,{commit,reader_sha256}) {
  assert.deepEqual([scope.status,scope.publication_approved,scope.plan.adapter],['glb_release_scope_private',false,ADAPTER]);
  assert.match(commit,revision);
  assert.match(reader_sha256,sha);
  return publicationHash({scope,commit,reader_sha256});
}

export function proveGlbRelease(scope,fresh,target,approval,now) {
  assert.equal(approval,glbApprovalHash(scope,target),'Require exact GLB owner approval hash');
  assert.equal(scope.plan_sha256,publicationHash(scope.plan),'Reviewed GLB plan changed');
  assert.deepEqual([fresh.adapter,validateNewModelIntake(fresh.intake,now).adapter],[ADAPTER,ADAPTER]);
  for(const key of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources','image'])
    assert.deepEqual(fresh[key],scope.plan[key],'GLB identity, history, or media changed: '+key);
  const previous=receipts(scope.plan.intake), current=receipts(fresh.intake);
  const oldest=Math.min(...current.map(item=>Date.parse(item.fetched_at)));
  const prior=Math.max(...previous.map(item=>Date.parse(item.fetched_at)));
  assert(oldest>prior,'GLB release requires a new capture after review');
  assert(now-Date.parse(fresh.intake.market.article.fetched_at)<=900000,'GLB market article receipt expired');
  assert.equal(fresh.intake.market.source.content_hash,scope.plan.intake.market.source.content_hash,'Reviewed market workbook changed');
  assert.deepEqual(withoutReceiptDrift(fresh.intake),withoutReceiptDrift(scope.plan.intake),'GLB source facts or literal evidence changed');
  assert.deepEqual(withoutReceiptDrift(fresh.targets),withoutReceiptDrift(scope.plan.targets),'Reviewed GLB targets changed');
}

export async function assertGlbPriceMigration(client) {
  const {rows}=await client.query(`SELECT conname,pg_get_constraintdef(oid) AS rule FROM pg_constraint WHERE convalidated AND
    ((conrelid='public.canonical_model_variants'::regclass AND conname IN
      ('canonical_manufacturer_from_evidence','canonical_model_variants_catalog_price_type_check')) OR
     (conrelid='public.extracted_variant_drafts'::regclass AND conname IN
      ('draft_manufacturer_from_evidence','extracted_variant_drafts_catalog_price_type_check')))`);
  assert.equal(rows.length,4,'Migration 026 is not installed');
  assert(rows.every(row=>/manufacturer_from/.test(row.rule)),'Incorrect starting-price constraint');
  assert.match(rows.find(row=>row.conname==='canonical_manufacturer_from_evidence').rule,/num_nonnulls.*price_source_hash.*price_refresh_batch_id/);
  assert.match(rows.find(row=>row.conname==='draft_manufacturer_from_evidence').rule,/extraction_payload.*price_evidence.*source_hash/);
}

export function buildGlbReleasePlan(scoped,intake,image,now) {
  const {model,plans}=scoped;
  assert(plans.length>0);
  return buildNewModelPlan({
    canonical_models:[model],canonical_model_variants:[],model_aliases:[plans[0].expected_alias],
    market_models:plans.map(plan=>plan.expected_market),market_model_monthly_stats:plans.flatMap(plan=>plan.expected_monthly),
    manufacturer_sources:plans[0].expected_sources,
  },intake,image,now);
}

export async function runGlbRelease({mode,scope,target,approval},io) {
  assert(['check','commit','export'].includes(mode));
  const required=glbApprovalHash(scope,target);
  if(mode!=='check')assert.equal(approval,required,'GLB release needs the explicit approved hash');
  await io.verifyProduction(scope,target);
  const baseline=await io.baseline(target.commit);
  assert.equal(catalogHash(baseline),scope.baseline_sha256,'Committed GLB baseline changed');
  assert.equal(catalogHash(await io.liveBaseline()),scope.baseline_sha256,'Live GLB baseline changed');
  if(mode==='export') {
    const {attempt,receipt}=await io.readJournal();
    assert.deepEqual([attempt.approval,attempt.target],[required,target]);
    proveGlbRelease(scope,attempt.plan,target,required,new Date(Math.max(...receipts(attempt.plan.intake).map(item=>Date.parse(item.fetched_at)))));
    assert.equal(receipt.attempt_sha256,publicationHash(attempt),'GLB commit receipt does not match the attempt');
    assert.deepEqual([receipt.result.committed,receipt.result.variants_inserted,receipt.result.anonymous_before_commit,receipt.result.paid_calls],
      [true,2,true,0]);
    assert.equal(receipt.result.publication_batch_id,publicationHash(attempt.plan));
    assert.deepEqual(receipt.result.canonical_variant_ids,attempt.plan.targets.map(target=>target.id));
    const rows=await io.publicRows();
    const records=glbCatalogDelta(baseline,rows,attempt.plan);
    assert.equal(glbCatalogHash(await io.publicRows()),glbCatalogHash(rows),'Canonical catalog changed during GLB export');
    await io.saveExport(records);
    return {status:'private_glb_export_verified',catalog_sha256:catalogHash(records),added:2,deployed:false,paid_calls:0};
  }
  const checkBaseline=async()=>assert.equal(glbCatalogHash(await io.publicRows()),scope.database_baseline_sha256,
    'Anonymous Supabase baseline changed');
  await checkBaseline();
  const intake=await io.freshSource();
  const client=await io.openSnapshot();
  try {
    await assertGlbPriceMigration(client);
    const fresh=buildGlbReleasePlan(await io.readSnapshot(client,intake),intake,scope.plan.image,io.now());
    proveGlbRelease(scope,fresh,target,required,io.now());
    if(mode==='check')return {status:'ready_for_explicit_glb_approval',scope_sha256:required,variants:2,production_writes:0,paid_calls:0};
    await checkBaseline();
    await io.verifyProduction(scope,target);
    const attempt={approval:required,target,plan:fresh};
    await io.saveAttempt(attempt);
    const result=await io.commit(client,fresh,required);
    assert.equal(result.publication_batch_id,publicationHash(fresh));
    assert.deepEqual([result.committed,result.variants_inserted,result.anonymous_before_commit,result.paid_calls],[true,2,true,0]);
    await io.saveCommit({attempt_sha256:publicationHash(attempt),result});
    return {status:'glb_committed_private_export_pending',added:2,deployed:false,paid_calls:0};
  } finally {await io.closeSnapshot(client);}
}
