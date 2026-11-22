import assert from 'node:assert/strict';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';
import { publicationHash, validateNewModelIntake } from './new_model_publication.mjs';
import { catalogHash, compareCatalogs, variantKey } from './sync_public_catalog.mjs';
import { ADAPTER, policy } from './xpeng_g9_publication.mjs';

const sha256 = /^[a-f0-9]{64}$/;
const specsSource = 'https://store.xpeng.com/se/configurator/new_G6';
const expectedNames = ['AWD Performance 20 tum','RWD Long Range 20 tum','RWD Standard Range 20 tum'];
const isG9 = row=>String(row.brand).toLowerCase()==='xpeng' && String(row.model).toLowerCase()==='g9';
export const isG6 = row=>String(row.brand).toLowerCase()==='xpeng' && String(row.model).toLowerCase()==='g6';

export function requirePublishedG6(rows) {
  const g6 = rows.filter(isG6);
  assert.deepEqual(g6.map(row=>row.variant_name).sort(),expectedNames,
    'All three reviewed G6 variants must exist in the public baseline');
  for(const row of g6) {
    assert(['published','published_reviewed'].includes(row.validation_status),'G6 baseline contains a non-public variant');
    assert.equal(row.source_url,specsSource,'G6 baseline is not the reviewed facelift');
    assert.match(row.source_hash,sha256);
  }
  return g6;
}

export function validateG9PostG6Delta(baseline,candidate,plan) {
  requirePublishedG6(baseline);
  assert.equal(plan.adapter,ADAPTER);
  assert.equal(plan.targets.length,2);
  assert(!baseline.some(isG9),'The baseline already contains G9');
  const additions = candidate.filter(isG9);
  assert.equal(additions.length,2,'Only the two exact G9 variants may be added');
  policy.verifyPublic(additions,plan);
  for(const {draft} of plan.targets) {
    const row = additions.find(row=>row.variant_name===draft.variant_name);
    assert(row);
    assert.equal(row.price_source_quote,draft.price_evidence.quote);
    assert.equal(row.price_valid_until,null);
    assert.equal(row.extraction_confidence,draft.extraction_confidence);
  }
  assert.equal(candidate.length,baseline.length+2);
  assert.equal(new Set(candidate.map(variantKey)).size,candidate.length,'Unexpected duplicated vehicle identity');
  const base = catalogWithComparableTimes(baseline);
  const unchanged = catalogWithComparableTimes(candidate.filter(row=>!isG9(row)));
  assert(compareCatalogs(base,unchanged).ok,'G9 would change another public row');
  return {baseline_sha256:catalogHash(base),candidate_sha256:catalogHash(catalogWithComparableTimes(candidate)),
    existing:base.length,added:2};
}

function requireUi(report,ui,plan) {
  assert.equal(ui.status,'g9_private_ui_passed');
  assert.deepEqual([ui.source_commit,ui.candidate_sha256,ui.private_variants],
    [report.commit,report.candidate_sha256,report.baseline_count+2]);
  assert.deepEqual([ui.g6_evidence,ui.production_writes,ui.publication_approved],['live_catalog_and_view',0,false]);
  assert(ui.exact_photos&&ui.g6_photo_separate&&ui.compared_from_detail&&ui.no_legacy_badges);
  const expected = plan.targets.flatMap(({draft})=>[320,390,768,1440].map(width=>[draft.variant_name,width]));
  assert.deepEqual(ui.responsive_checks.map(row=>[row.variant,row.width]).sort(),expected.sort());
  assert.equal(ui.g9_media.length,4);
  assert.deepEqual(ui.g9_media[0],{url:plan.image.asset_url,sha256:plan.image.content_sha256});
  for(const [i,width] of [480,800,1280].entries()) {
    assert.equal(ui.g9_media[i+1].url,plan.image.asset_url.replace('/vehicles/','/responsive/').replace(/\.jpg$/,`-${width}.webp`));
    assert.match(ui.g9_media[i+1].sha256,sha256);
  }
}

export function prepareG9ReleaseReview({report,ui,plan,baseline,candidate}) {
  assert.equal(report.status,'xpeng_g9_local_after_g6_passed');
  assert.equal(report.g6_evidence,'live_catalog_and_view','A fixture of G6 is not a live baseline');
  assert.deepEqual([report.variants,report.production_writes,report.publication_approved],[2,0,false]);
  assert(report.anonymous_before_commit&&report.late_rollback&&report.exact_replay_noop&&report.market_history_preserved);
  assert.match(report.commit,/^[0-9a-f]{40}$/);
  assert.equal(report.plan_hashes.length,1);
  assert.equal(report.plan_hashes[0],publicationHash(plan));
  const delta = validateG9PostG6Delta(baseline,candidate,plan);
  assert.equal(delta.existing,report.baseline_count);
  assert.equal(catalogHash(baseline),report.baseline_sha256);
  assert.equal(catalogHash(candidate),report.candidate_sha256);
  requireUi(report,ui,plan);
  return {plan,commit:report.commit,ui,baseline_sha256:report.baseline_sha256,
    database_baseline_sha256:delta.baseline_sha256,candidate_sha256:report.candidate_sha256,
    preserved:delta.existing,added:2};
}

export const g9ApprovalHash = reviewed=>publicationHash(reviewed);
const captureTimes = plan=>[plan.intake.market.source,...plan.intake.sources].map(row=>Date.parse(row.fetched_at));
const stable = value=>JSON.parse(JSON.stringify(value,(key,item)=>
  ['fetched_at','content_hash','source_hash','authorization_hash'].includes(key)?undefined:item));

export function proveFreshG9Release(reviewed,fresh,approvedHash,now=new Date()) {
  assert.equal(approvedHash,g9ApprovalHash(reviewed),'Require the exact approved G9 release hash');
  const {plan} = fresh;
  assert.equal(fresh.plan_hash,publicationHash(plan),'Fresh G9 plan changed');
  assert.equal(plan.adapter,ADAPTER);
  assert.equal(plan.expected_model.validation_status,'draft');
  validateNewModelIntake(plan.intake,now);
  assert(Math.min(...captureTimes(plan))>Math.max(...captureTimes(reviewed.plan)),'G9 sources must be recaptured after review');
  for(const key of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources','image']) {
    assert.deepEqual(plan[key],reviewed.plan[key],'Reviewed G9 scope changed: '+key);
  }
  assert.equal(plan.intake.market.source.content_hash,reviewed.plan.intake.market.source.content_hash,'Mobility Sweden workbook changed');
  for(const key of ['intake','targets']) assert.deepEqual(stable(plan[key]),stable(reviewed.plan[key]),'Reviewed G9 evidence changed: '+key);
}
