import assert from 'node:assert/strict';
import {ADAPTER,policy} from './porsche_macan_publication.mjs';
import {publicationHash,validateNewModelIntake} from './new_model_publication.mjs';
import {assertScopedPublishedRows,databaseCatalogHash,singleCatalogDelta} from './hyundai_inster_advanced_release_scope.mjs';

const hash=/^[a-f0-9]{64}$/;
const route='https://elbilsagenten.se/bilar/porsche-macan-electric-rwd-my27';
const volatile=new Set(['fetched_at','content_hash','source_hash']);
const stable=value=>JSON.parse(JSON.stringify(value,(key,item)=>volatile.has(key)?undefined:item));
const receiptTimes=i=>[...i.sources,i.market.source].map(s=>Date.parse(s.fetched_at));

export const assertMacanPublishedRows=(rows,plan)=>assertScopedPublishedRows(rows,plan,policy);
export const macanCatalogDelta=(baseline,rows,plan,options)=>singleCatalogDelta(baseline,rows,plan,policy,options);

export function createMacanReleaseScope({plan,report,ui,seo,baseline,candidate,media}){
  assert.equal(plan.adapter,ADAPTER);
  assert.deepEqual([report.status,report.technical_fields,report.late_rollback,report.exact_replay_noop,
    report.anonymous_before_commit,report.remote_write_rejected,report.scope_conflicts_rejected,
    report.publication_approved,report.production_writes,report.paid_calls],
  ['macan_local_atomic_rehearsal_verified',9,true,true,true,true,true,false,0,0]);
  assert.equal(report.plan_sha256,publicationHash(plan));
  assert.equal(report.baseline_sha256,databaseCatalogHash(baseline));
  assert.equal(report.candidate_sha256,databaseCatalogHash(candidate));
  assert.equal(report.candidate_sha256,databaseCatalogHash(macanCatalogDelta(baseline,candidate,plan,{ids:false})));
  assert.deepEqual([ui.status,ui.comparison,ui.catalog_sha256,ui.production_writes,ui.publication_approved],
    ['macan_private_ui_verified',true,report.candidate_sha256,0,false]);
  assert.deepEqual(ui.checks.map(r=>r.viewport),[320,390,1440]);
  assert.deepEqual([seo.status,seo.added,seo.catalog_sha256,seo.fixed_offer,seo.production_writes,seo.publication_approved],
    ['macan_static_preview_verified',route,report.candidate_sha256,false,0,false]);
  assert(seo.news_articles_preserved>0&&hash.test(seo.public_news_sha256));
  assert.equal(seo.candidate_urls,seo.existing_urls+1);
  const picture=plan.image.asset_url;
  assert.deepEqual(media.map(r=>r.url),[picture,...[480,800,1280].map(width=>
    picture.replace('/vehicles/','/responsive/').replace(/\.jpg$/,'-'+width+'.webp'))]);
  assert(ui.checks.every(row=>media.some(asset=>asset.url===row.asset)));
  assert(media.every(r=>hash.test(r.sha256)));
  assert.equal(media[0].sha256,policy.imageHash);
  assert.deepEqual([baseline.length,candidate.length],[report.public_baseline,report.public_baseline+1]);
  return {status:'macan_release_scope_private',publication_approved:false,plan,plan_sha256:report.plan_sha256,
    database_baseline_sha256:report.baseline_sha256,candidate_sha256:report.candidate_sha256,media,seo};
}

export function macanReleaseHash(scope,{commit,reader_sha256}){
  assert.deepEqual([scope.status,scope.publication_approved,scope.plan.adapter],['macan_release_scope_private',false,ADAPTER]);
  assert.match(commit,/^[a-f0-9]{40}$/);
  assert.match(reader_sha256,hash);
  return publicationHash({scope,commit,reader_sha256});
}

export function proveMacanRelease(scope,fresh,target,seal,now){
  assert.equal(seal,macanReleaseHash(scope,target),'Match the exact reviewed Macan release scope');
  assert.equal(scope.plan_sha256,publicationHash(scope.plan),'Reviewed Macan plan changed');
  assert.deepEqual([fresh.adapter,validateNewModelIntake(fresh.intake,now).adapter],[ADAPTER,ADAPTER]);
  for(const key of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources'])
    assert.deepEqual(fresh[key],scope.plan[key],'Macan catalog scope changed: '+key);
  for(const key of ['intake','targets','image'])
    assert.deepEqual(stable(fresh[key]),stable(scope.plan[key]),'Macan evidence or target changed: '+key);
  const dates=receiptTimes(fresh.intake),prior=receiptTimes(scope.plan.intake);
  assert(dates.every(t=>t>=+now-900000&&t<=+now+60000),'Fresh Macan evidence is required');
  assert(Math.min(...dates)>Math.max(...prior),'Capture official sources again after reviewing Macan');
}
