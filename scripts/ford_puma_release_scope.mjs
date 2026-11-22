import assert from 'node:assert/strict';
import { ADAPTER, policy } from './ford_puma_gen_e_publication.mjs';
import { planPumaIdentity } from './ford_puma_identity.mjs';
import { publicationHash, validateNewModelIntake } from './new_model_publication.mjs';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';
import { catalogHash, normalizeCatalog, variantKey } from './sync_public_catalog.mjs';

const sha = /^[a-f0-9]{64}$/;
const gitSha = /^[a-f0-9]{40}$/;
const type = 'manufacturer_from';
const proofKeys = ['src/price-evidence.js', 'src/main.jsx', 'src/vehicle-ui.jsx', 'src/advisor-matching.js',
  'src/decision-metrics.js', 'src/tco.js', 'src/vehicle-names.js'];
const stableFiles = new Set(['price_list_pdf', 'technical_pdf']);
const strip = (value, keys) => JSON.parse(JSON.stringify(value, (key, entry) => keys.includes(key) ? undefined : entry));
const sources = intake => [...intake.sources, intake.market.source, intake.market.article];
const compareHash = rows => catalogHash(catalogWithComparableTimes(rows));
const responsiveUrl = (url, width) => url.replace('/vehicles/', '/responsive/').replace(/\.jpg$/, '-' + width + '.webp');

export function assertPumaPublishedRows(rows, plan) {
  assert.equal(plan.adapter, ADAPTER);
  policy.verifyPublic(rows, plan);
  const primary = plan.intake.sources.find(s => s.final_url === policy.primaryUrl);
  for (const {draft} of plan.targets) {
    const row = rows.find(r => r.variant_name === draft.variant_name);
    const p = draft.price_evidence;
    assert.equal(p.price_type, type);
    assert.equal(row.price_source_hash, p.source_hash);
    assert.equal(row.price_source_quote, p.quote);
    assert.equal(row.price_source_name, primary.source_name);
    assert.equal(Date.parse(row.price_verified_at), Date.parse(primary.fetched_at));
    assert.equal(row.source_hash, primary.content_hash);
    assert.equal(row.source_quote, [...new Set(Object.values(draft.field_evidence).map(f => f.source_url + ' | ' + f.quote))].join(' | '));
    for (const flag of ['available_confirmed', 'coming_or_low_volume', 'discontinued_candidate']) assert.equal(row[flag], false);
  }
}

export function pumaReleaseReview({packet, plan, baseline, candidate, report, ui, media, code, observedUi}) {
  assert.deepEqual([report.status, report.variants, report.fields, report.atomic_identity, report.exact_replay_noop,
    report.late_rollback, report.anonymous_before_commit, report.starting_price_migration_local, report.invalid_price_evidence_rejected,
    report.publication_approved, report.production_writes, report.paid_calls],
  ['puma_local_insertion_verified', 2, 18, true, true, true, true, true, true, false, 0, 0]);
  assert.deepEqual([packet.status, packet.publication_approved, packet.intake.adapter],
    ['puma_atomic_rehearsal_only', false, ADAPTER]);
  assert.equal(publicationHash(packet), report.plan_sha256);
  assert.deepEqual(plan.intake, packet.intake);
  assert.deepEqual(plan.image, packet.image);
  assert.deepEqual(plan.expected_sources, packet.expected_sources);
  assert.deepEqual(planPumaIdentity(packet.identity.expected), packet.identity);
  assert.deepEqual(plan.targets.map(t => t.draft), packet.intake.drafts);
  assert.equal(plan.expected_market.id, packet.identity.market_id);
  assert.match(report.commit, gitSha);
  assert.deepEqual([baseline.length, candidate.length], [report.baseline_count, report.baseline_count + 2]);
  assert.equal(catalogHash(baseline), report.baseline_sha256);
  assert.equal(compareHash(baseline), packet.baseline_sha256);
  assert.equal(catalogHash(candidate), report.candidate_sha256);
  const prior = new Set(baseline.map(variantKey));
  const added = candidate.filter(row => !prior.has(variantKey(row)));
  assert.deepEqual(normalizeCatalog(candidate.filter(row => prior.has(variantKey(row)))), normalizeCatalog(baseline));
  assert.equal(added.length, 2);
  assertPumaPublishedRows(added, plan);
  assert.deepEqual([ui.status, ui.candidate_sha256, ui.atomic_plan_sha256, ui.publisher_starting_price_checked,
    ui.compared_from_detail, ui.photo_sha256, ui.publication_approved, ui.production_writes],
  ['puma_private_ui_verified', report.candidate_sha256, report.plan_sha256, true, true, packet.image.content_sha256, false, 0]);
  assert.deepEqual(Object.keys(ui.price_ui_sha256).sort(), [...proofKeys].sort());
  for (const path of proofKeys) {
    assert.match(ui.price_ui_sha256[path], sha);
    assert.equal(observedUi[path], ui.price_ui_sha256[path], 'Reviewed Puma UI changed: ' + path);
    assert.match(code[path], sha);
  }
  assert(media.length === 4 && media.every(m => sha.test(m.sha256)));
  assert.deepEqual(media[0], {url: packet.image.asset_url, sha256: packet.image.content_sha256});
  assert.deepEqual(media.slice(1).map(m => m.url), [480, 800, 1280].map(w => responsiveUrl(media[0].url, w)));
  assert.deepEqual(ui.checks.map(c => c.viewport + ':' + c.variant + ':' + c.asset).sort(),
    [390, 1440].flatMap(w => plan.targets.map(t => w + ':' + t.draft.variant_name + ':' + responsiveUrl(media[0].url, w === 390 ? 480 : 1280))).sort());
  return {status: 'puma_release_scope_private', packet, baseline_commit: report.commit, baseline_count: report.baseline_count,
    baseline_sha256: report.baseline_sha256, candidate_sha256: report.candidate_sha256,
    rehearsal_sha256: report.plan_sha256, added, media, code, publication_approved: false};
}

export function pumaApprovalHash(reviewed, commit) {
  assert.equal(reviewed.status, 'puma_release_scope_private');
  assert.equal(reviewed.publication_approved, false);
  assert.match(commit, gitSha);
  return publicationHash({reviewed, commit});
}

export function provePumaRelease(reviewed, fresh, commit, approval, now = new Date()) {
  assert.equal(approval, pumaApprovalHash(reviewed, commit), 'Require exact Puma owner approval hash');
  assert.equal(reviewed.rehearsal_sha256, publicationHash(reviewed.packet));
  for (const field of ['identity', 'image', 'expected_sources', 'baseline_sha256']) {
    assert.deepEqual(fresh[field], reviewed.packet[field], 'Puma release state changed: ' + field);
  }
  assert.equal(fresh.status, 'puma_atomic_rehearsal_only');
  assert.equal(fresh.publication_approved, false);
  assert.equal(validateNewModelIntake(fresh.intake, now).adapter, ADAPTER);
  const previous = sources(reviewed.packet.intake);
  const current = sources(fresh.intake);
  assert(Math.min(...current.map(s => Date.parse(s.fetched_at))) > Math.max(...previous.map(s => Date.parse(s.fetched_at))),
    'Puma release requires a capture newer than the reviewed one');
  assert(now - Date.parse(fresh.intake.market.article.fetched_at) <= 900000, 'Puma market index receipt is stale');
  for (const source of current) {
    if (stableFiles.has(source.source_type) || source.final_url === fresh.intake.market.source.final_url) {
      assert.equal(source.content_hash, previous.find(p => p.final_url === source.final_url)?.content_hash, 'Puma PDF or workbook changed');
    }
  }
  assert.deepEqual(strip(fresh.intake, ['fetched_at', 'content_hash', 'source_hash']),
    strip(reviewed.packet.intake, ['fetched_at', 'content_hash', 'source_hash']), 'Puma facts or literal evidence changed');
}

export async function assertPumaPriceMigration(client) {
  const {rows} = await client.query("SELECT conname, pg_get_constraintdef(oid) AS rule FROM pg_constraint WHERE convalidated " +
    "AND ((conrelid='public.canonical_model_variants'::regclass AND conname IN ('canonical_manufacturer_from_evidence','canonical_model_variants_catalog_price_type_check')) " +
    "OR (conrelid='public.extracted_variant_drafts'::regclass AND conname IN ('draft_manufacturer_from_evidence','extracted_variant_drafts_catalog_price_type_check')))");
  assert.equal(rows.length, 4, 'Migration 026 is not installed');
  for (const row of rows) assert.match(row.rule, /manufacturer_from/, 'Starting-price type missing from migration contract');
  assert.match(rows.find(r => r.conname === 'canonical_manufacturer_from_evidence').rule, /num_nonnulls.*price_source_hash.*price_refresh_batch_id/);
  assert.match(rows.find(r => r.conname === 'draft_manufacturer_from_evidence').rule, /extraction_payload.*price_evidence.*source_hash/);
}

export function pumaCatalogDelta(baseline, current, plan) {
  assert.equal(plan.intake.adapter, ADAPTER);
  const old = new Set(baseline.map(variantKey));
  assert.equal(compareHash(current.filter(row => old.has(variantKey(row)))), compareHash(baseline), 'Existing public rows changed');
  const added = current.filter(row => !old.has(variantKey(row)));
  assert.equal(added.length, 2, 'Unexpected Puma export delta');
  assertPumaPublishedRows(added, plan);
  return normalizeCatalog([...baseline, ...catalogWithComparableTimes(added)]);
}
