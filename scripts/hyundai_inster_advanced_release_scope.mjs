import assert from 'node:assert/strict';
import {ADAPTER,policy} from './hyundai_inster_advanced_publication.mjs';
import {catalogWithComparableTimes} from './isolated_catalog_review.mjs';
import {publicationHash,validateNewModelIntake} from './new_model_publication.mjs';
import {catalogHash,normalizeCatalog,variantKey} from './sync_public_catalog.mjs';

const sha=/^[a-f0-9]{64}$/;
const origin='https://elbilsagenten.se';
export const insterRoute='/bilar/hyundai-inster-49-kwh-advanced-tech-17-tum-my27';
export const databaseCatalogHash=rows=>catalogHash(catalogWithComparableTimes(rows));
const volatile=new Set(['fetched_at','content_hash','source_hash','request_hash','private_file']);
const stable=value=>JSON.parse(JSON.stringify(value,(key,item)=>volatile.has(key)?undefined:item));
const receiptTimes=i=>[...i.sources,i.market.source,i.source_decisions.model,
  ...Object.values(i.source_decisions.factory_receipts)].map(r=>Date.parse(r.fetched_at));

export function assertInsterPublishedRows(rows,plan,{ids=true}={}){
  assert.equal(plan.adapter,ADAPTER);
  policy.verifyPublic(rows,plan);
  const [row]=rows,[{id,draft}]=plan.targets;
  const primary=plan.intake.sources.find(source=>source.final_url===policy.primaryUrl);
  const price=plan.intake.sources.find(source=>source.final_url===draft.price_evidence.source_url);
  if(ids)assert.deepEqual([row.id,row.canonical_model_id],[id,plan.expected_model.id]);
  assert.equal(row.source_hash,primary.content_hash);
  assert.equal(row.source_quote,[...new Set(Object.values(draft.field_evidence).map(r=>r.source_url+' | '+r.quote))].join(' | '));
  assert.deepEqual([row.price_source_hash,row.price_source_quote,row.price_source_name,Date.parse(row.price_verified_at)],
    [price.content_hash,draft.price_evidence.quote,price.source_name,Date.parse(price.fetched_at)]);
  for(const flag of ['available_confirmed','discontinued_candidate','coming_or_low_volume'])
    assert.equal(row[flag],plan.expected_model[flag],'Inster market flag changed: '+flag);
}

export function insterCatalogDelta(baseline,rows,plan,options){
  const keys=new Set(baseline.map(variantKey));
  assert.equal(databaseCatalogHash(rows.filter(row=>keys.has(variantKey(row)))),databaseCatalogHash(baseline),
    'Existing catalog changed');
  const added=rows.filter(row=>!keys.has(variantKey(row)));
  assert.equal(added.length,1,'Release may add only the reviewed Inster');
  assertInsterPublishedRows(added,plan,options);
  return normalizeCatalog([...baseline,...catalogWithComparableTimes(added)]);
}

export function createInsterReleaseScope({plan,report,ui,seo,baseline,candidate,media}){
  assert.deepEqual([report.status,report.technical_fields,report.live_decimal_migration_verified,report.late_rollback,
    report.exact_replay_noop,report.publication_approved,report.production_writes],
  ['inster_advanced_atomic_local_verified',9,true,true,true,false,0]);
  assert.deepEqual(Object.values(report.decimal_projections).map(Number),[85.3,85.3,85.3]);
  assert.equal(report.plan_sha256,publicationHash(plan));
  assert.equal(report.baseline_sha256,databaseCatalogHash(baseline));
  assert.equal(report.candidate_sha256,databaseCatalogHash(candidate));
  assert.equal(report.candidate_sha256,databaseCatalogHash(insterCatalogDelta(baseline,candidate,plan,{ids:false})));
  assert.deepEqual([ui.status,ui.comparison,ui.catalog_sha256,ui.production_writes,ui.publication_approved],
    ['inster_private_ui_verified',true,report.candidate_sha256,0,false]);
  assert.deepEqual(ui.checks.map(r=>r.viewport),[320,390,1440]);
  assert.deepEqual([seo.status,seo.added,seo.catalog_sha256,seo.fixed_offer,seo.production_writes,seo.publication_approved],
    ['inster_static_preview_verified',origin+insterRoute,report.candidate_sha256,false,0,false]);
  assert(seo.news_articles_preserved>0&&sha.test(seo.public_news_sha256));
  assert.equal(seo.candidate_urls,seo.existing_urls+1);
  const responsive=width=>plan.image.asset_url.replace('/vehicles/','/responsive/').replace(/\.jpg$/,'-'+width+'.webp');
  assert.deepEqual(media.map(r=>r.url),[plan.image.asset_url,...[480,800,1280].map(responsive)]);
  assert(ui.checks.every(row=>media.some(asset=>asset.url===row.asset)));
  assert(media.every(r=>sha.test(r.sha256)));
  assert.equal(media[0].sha256,policy.imageHash);
  assert.equal(baseline.length,report.canonical_baseline);
  assert.equal(candidate.length,baseline.length+1);
  return {status:'inster_release_scope_private',publication_approved:false,plan,plan_sha256:report.plan_sha256,
    database_baseline_sha256:report.baseline_sha256,candidate_sha256:report.candidate_sha256,media,seo};
}

export function insterReleaseHash(scope,{commit,reader_sha256}){
  assert.deepEqual([scope.status,scope.publication_approved,scope.plan.adapter],['inster_release_scope_private',false,ADAPTER]);
  assert.match(commit,/^[a-f0-9]{40}$/);
  assert.match(reader_sha256,sha);
  return publicationHash({scope,commit,reader_sha256});
}

export function proveInsterRelease(scope,fresh,target,seal,now){
  assert.equal(seal,insterReleaseHash(scope,target),'Match the exact reviewed Inster release scope');
  assert.equal(scope.plan_sha256,publicationHash(scope.plan),'Reviewed Inster plan changed');
  assert.deepEqual([fresh.adapter,validateNewModelIntake(fresh.intake,now).adapter],[ADAPTER,ADAPTER]);
  for(const key of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources'])
    assert.deepEqual(fresh[key],scope.plan[key],'Inster catalog scope changed: '+key);
  for(const key of ['intake','targets','image'])
    assert.deepEqual(stable(fresh[key]),stable(scope.plan[key]),'Inster evidence or target changed: '+key);
  const dates=receiptTimes(fresh.intake),prior=receiptTimes(scope.plan.intake);
  assert(dates.every(t=>t>=+now-900000&&t<=+now+60000),'Fresh Inster evidence is required');
  assert(Math.min(...dates)>Math.max(...prior),'Capture official sources again after reviewing Inster');
}
