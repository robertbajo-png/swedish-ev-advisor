import assert from 'node:assert/strict';
import { test } from 'node:test';
import { normalizePublicVariants } from '../functions/_shared/advisor-core.mjs';
import { matchAdvisorVariants, ruleRequirements } from '../src/advisor-matching.js';
import { specQualifications } from '../src/spec-qualifications.js';
import { publicationHash } from '../scripts/new_model_publication.mjs';
import { ADAPTER, MODEL, readPolestar3Image } from '../scripts/polestar_3_publication.mjs';
import { polestar3Media, preparePolestar3ReleaseReview, proveFreshPolestar3Release } from '../scripts/polestar_3_release_scope.mjs';
import { catalogHash } from '../scripts/sync_public_catalog.mjs';

const manual = 'https://www.polestar.com/se/manual/polestar-3/2027/article/certified-wltp/';
const row = {id: 'isolated-polestar-fixture', brand: 'Polestar', model: '3', variant_name: 'Performance',
  validation_status: 'published', source_url: 'https://www.polestar.com/se/polestar-3/specifications/',
  source_hash: 'a'.repeat(64), source_quote: manual + ' | Performance | 742 | 601 | 20,5 | 649 | 524 | 23,1',
  price_sek: 999000, price_type: 'list_price', wltp_range_km: 601, wltp_consumption_kwh_100km: 20.5};

test('the certified combined interval excludes city range and follows the exact variant', () => {
  const qualified = specQualifications(row);
  assert.equal(qualified.rangeMinimum, 524);
  assert.equal(qualified.rangeInterval, '524\u2013601 km');
  assert.equal(qualified.consumptionInterval, '20,5\u201323,1 kWh/100 km');
  assert.equal(qualified.rangeIsTarget, false);
  for (const patch of [{variant_name: 'Dual motor'}, {wltp_range_km: 742},
    {source_quote: row.source_quote.replace('/2027/', '/2026/')}, {source_quote: 'Performance | 601 km'}]) {
    assert.equal(specQualifications({...row, ...patch}).rangeMinimum, null);
  }
});

test('normalized and raw advice never confirm an interval-dependent minimum', () => {
  for (const variants of [[row], normalizePublicVariants([row])]) {
    const match = range => matchAdvisorVariants(variants, ruleRequirements({budget: 1000000, range}));
    const result = match(524);
    assert.equal(result.matching_count, 1);
    assert(result.shortlist[0].reasons.some(reason => reason.includes('524\u2013601 km WLTP')));
    assert.deepEqual([match(525).matching_count, match(525).excluded_unknown_count], [0, 1]);
    assert.deepEqual([match(601).matching_count, match(601).excluded_unknown_count], [0, 1]);
    assert.match(match(600).interpreted_requirements.notes, /Exakt konfiguration/);
    assert.deepEqual([match(602).matching_count, match(602).excluded_unknown_count], [0, 0]);
  }
});

function releaseProof() {
  const photo = readPolestar3Image();
  const priceQuote = 'Performance | 999 000 kr';
  const flags = {market_seen:true, available_confirmed:false, discontinued_candidate:false, coming_or_low_volume:false};
  const facts = {wltp_range_km:601, wltp_consumption_kwh_100km:20.5, dc_charge_kw:350};
  const candidateRow = {...row, ...facts, ...flags, body_type:MODEL.body_type, source_name:'Polestar',
    price_valid_until:null, price_source_url:row.source_url, price_source_hash:row.source_hash,
    price_source_quote:priceQuote, price_source_name:'Polestar', price_verified_at:'2026-11-22',
    image_url:photo.asset_url, image_source_url:photo.source_url, extraction_confidence:0.96};
  const baseline = [{...row, ...flags, brand:'Cupra', model:'Tavascan', variant_name:'Drive', extraction_confidence:0.97}];
  const candidate = [...baseline, candidateRow];
  const plan = {adapter:ADAPTER, image:photo, expected_model:{...flags, id:'isolated-model'},
    intake:{sources:[{final_url:row.source_url, content_hash:row.source_hash}]}, targets:[{id:row.id, draft:{
      facts, extraction_confidence:0.96,
      price_evidence:{source_hash:row.source_hash, quote:priceQuote},
      field_evidence:{wltp_range_km:{source_url:manual, quote:row.source_quote.split(' | ').slice(1).join(' | ')}},
    }}]};
  const report = {status:'polestar_3_local_insertion_verified', commit:'a'.repeat(40), variants:1, technical_fields:9,
    anonymous_before_commit:true, exact_replay_noop:true, late_rollback:true, publication_approved:false, production_writes:0,
    plan_sha256:publicationHash(plan), baseline_sha256:catalogHash(baseline), candidate_sha256:catalogHash(candidate),
    baseline_count:baseline.length, candidate_count:candidate.length};
  const media = polestar3Media(photo);
  const ui = {status:'polestar_3_private_ui_verified', source_commit:report.commit, plan_sha256:report.plan_sha256,
    candidate_sha256:report.candidate_sha256, exact_main_code:true, production_writes:0, publication_approved:false,
    photo_sha256:photo.content_sha256, native_media_evidence:'b'.repeat(64), media,
    checks:[390,1440].map((width,index)=>({width, image:media[index+1].url, exact_image:true, certified_interval:true, no_overflow:true}))};
  return {plan, report, ui, baseline, candidate};
}

test('Polestar 3 release review binds scope to exact main, evidence, and native image assets', () => {
  const proof = releaseProof();
  const reviewed = preparePolestar3ReleaseReview(proof);
  assert.deepEqual([reviewed.added,reviewed.preserved],[1,1]);
  assert.throws(()=>proveFreshPolestar3Release(reviewed, null, 'unrelated'), /exact reviewed/);
  for(const change of [
    p=>{p.ui.exact_main_code=false;},
    p=>{p.ui.source_commit='b'.repeat(40);},
    p=>{p.ui.media[1].sha256='c'.repeat(64);},
    p=>{p.ui.checks[0].certified_interval=false;},
    p=>{p.report.late_rollback=false;},
  ]) {
    const changed = structuredClone(proof);
    change(changed);
    assert.throws(()=>preparePolestar3ReleaseReview(changed));
  }
});

test('Polestar additions cannot change other catalog prices or replace certified combined range', () => {
  for(const change of [
    p=>{p.candidate[0]={...p.candidate[0],price_sek:500000};},
    p=>{p.candidate[1].wltp_range_km=742;},
    p=>{p.candidate[1].source_quote='Performance | 601 km';},
    p=>{p.candidate[1].price_source_quote='Dual motor | 924 000 kr';},
  ]) {
    const proof = releaseProof();
    change(proof);
    proof.report.candidate_sha256=proof.ui.candidate_sha256=catalogHash(proof.candidate);
    assert.throws(()=>preparePolestar3ReleaseReview(proof));
  }
});
