import assert from 'node:assert/strict';
import { ADAPTER, policy } from './hyundai_ioniq5_publication.mjs';
import { publicationHash, validateNewModelIntake } from './new_model_publication.mjs';
import { vehicleSlug } from '../src/vehicle-names.js';

const shaPattern = /^[a-f0-9]{64}$/;
const strip = (value, excluded) => JSON.parse(JSON.stringify(value,
  (key, entry) => excluded.includes(key) ? undefined : entry));
const sourceExpiry = intake => Math.min(...[intake.market.source, ...intake.sources].map(row => Date.parse(row.fetched_at))) + 900000;

export function ioniq5ReleaseReceipt(plan, reviewHash) {
  assert.match(reviewHash, shaPattern);
  assert.equal(plan.adapter, ADAPTER);
  assert.equal(plan.targets.length, 7);
  assert.deepEqual(plan.intake.model_evidence.identity_holds, {});
  return { status: 'ready_for_review', publication_approved: false, production_writes: 0,
    plan_hash: publicationHash(plan), review_hash: reviewHash, evidence_expires_at: new Date(sourceExpiry(plan.intake)).toISOString(), plan };
}

export function proveIoniq5ReleaseScope(reviewed, fresh, ui, approval, now = new Date()) {
  for (const receipt of [reviewed, fresh]) {
    assert.deepEqual(receipt, ioniq5ReleaseReceipt(receipt.plan, receipt.review_hash), 'Ioniq 5 receipt changed');
  }
  assert.match(approval ?? '', shaPattern, 'Require the exact reviewed Ioniq 5 plan hash');
  assert.equal(approval, reviewed.plan_hash, 'Invalid Ioniq 5 approval');
  assert.notEqual(fresh.review_hash, reviewed.review_hash, 'Fetch current Ioniq 5 sources again');
  assert(sourceExpiry(fresh.plan.intake) > now.getTime(), 'Ioniq 5 source window expired');
  validateNewModelIntake(fresh.plan.intake, now);
  assert.equal(ui.status, 'passed_local_only');
  assert.equal(ui.plan_hash, reviewed.plan_hash);
  assert.equal(ui.publication_approved, false);
  assert.equal(ui.production_writes, 0);
  assert.equal(ui.paid_calls, 0);
  assert.equal(ui.listing, true);
  assert.equal(ui.comparison, true);
  assert.match(ui.baseline.baseline_sha256, shaPattern);
  assert.match(ui.baseline.database_baseline_sha256, shaPattern);
  assert.equal(ui.baseline.candidate_count, ui.baseline.baseline_count + 7);
  assert.deepEqual([ui.distribution.preserved, ui.distribution.count, ui.distribution.added.length],
    [ui.baseline.baseline_count, ui.baseline.candidate_count, 7]);
  assert.equal(ui.distribution.intercepted_catalog, false);
  assert.equal(ui.distribution.intercepted_images, false);
  assert.equal(ui.distribution.approved_for_deployment, false);
  assert.equal(ui.distribution.static_assets.length, 8);
  const {brand, model} = reviewed.plan.intake.model;
  const expectedRuns = [320,390,768,1440].flatMap(width => reviewed.plan.targets
    .map(({draft}) => vehicleSlug(brand, model, draft.variant_name) + ':' + width)).sort();
  assert.deepEqual(ui.runs.map(run => run.slug + ':' + run.width).sort(), expectedRuns, 'Ioniq 5 browser matrix differs');
  const editions = new Set(reviewed.plan.targets
    .map(({draft}) => policy.variantPhoto(draft)?.image.content_sha256).filter(Boolean));
  assert.deepEqual([...editions], [ui.photos.n_line]);
  assert.equal(ui.photos.base, reviewed.plan.image.content_sha256);
  for (const key of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources','image']) {
    assert.deepEqual(fresh.plan[key], reviewed.plan[key], 'Reviewed Ioniq 5 scope changed: ' + key);
  }
  assert.deepEqual(strip(fresh.plan.intake.market, ['fetched_at']), strip(reviewed.plan.intake.market, ['fetched_at']),
    'Mobility Sweden workbook changed');
  const pdfs = intake => intake.sources.filter(source => source.source_type === 'technical_pdf' || source.source_type === 'price_list_pdf');
  assert.deepEqual(strip(pdfs(fresh.plan.intake), ['fetched_at']), strip(pdfs(reviewed.plan.intake), ['fetched_at']),
    'Reviewed Ioniq 5 PDF evidence changed');
  const volatile = ['fetched_at','content_hash','source_hash','authorization_hash'];
  for (const key of ['intake','targets']) {
    assert.deepEqual(strip(fresh.plan[key], volatile), strip(reviewed.plan[key], volatile), 'Ioniq 5 evidence or price changed: ' + key);
  }
}

export function assertIoniq5PublishedRows(rows, plan) {
  assert.equal(plan.adapter, ADAPTER);
  assert.equal(rows.length, 7);
  assert.equal(plan.targets.length, 7);
  const primary = plan.intake.sources.find(source => source.final_url === policy.primaryUrl);
  assert(primary);
  for (const { draft } of plan.targets) {
    const matched = rows.filter(row => row.variant_name === draft.variant_name);
    assert.equal(matched.length, 1, 'Missing or duplicated public Ioniq 5 variant');
    const row = matched[0];
    const photo = policy.variantPhoto(draft)?.image ?? plan.image;
    const price = draft.price_evidence;
    const priceSource = plan.intake.sources.find(source => source.final_url === price.source_url);
    const sourceQuote = [...new Set(Object.values(draft.field_evidence).map(proof => proof.source_url + ' | ' + proof.quote))].join(' | ');
    const expected = {
      brand: plan.intake.model.brand, model: plan.intake.model.model, body_type: plan.intake.model.body_type,
      ...draft.facts, validation_status: 'published', extraction_confidence: draft.extraction_confidence,
      image_url: photo.asset_url, image_source_url: photo.source_url,
      price_sek: price.value, price_type: 'list_price', price_valid_until: price.price_valid_until,
      price_source_url: price.source_url, price_source_hash: price.source_hash, price_source_quote: price.quote,
      price_source_name: priceSource.source_name, source_url: primary.final_url, source_hash: primary.content_hash,
      source_quote: sourceQuote, market_seen: true,
      ...Object.fromEntries(['available_confirmed','discontinued_candidate','coming_or_low_volume']
        .map(key => [key, plan.expected_model[key]])),
    };
    for (const [key, value] of Object.entries(expected)) assert.equal(row[key], value, 'Unexpected public Ioniq 5 field: ' + key);
    assert.equal(Date.parse(row.price_verified_at), Date.parse(priceSource.fetched_at), 'Unexpected Ioniq 5 price date');
  }
}
