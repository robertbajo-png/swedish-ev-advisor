import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { publicationHash, validateNewModelIntake } from './new_model_publication.mjs';
import { catalogHash } from './sync_public_catalog.mjs';
import { prepareXpG6Readback } from './prepare_xpeng_g6_readback.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { ADAPTER, readReviewedImage, readXpG6Capture } from './xpeng_g6_publication.mjs';

const liveCatalogUrl = 'https://elbilsagenten.se/data/public_ev_variants.json';
const asJson = async path => JSON.parse(await readFile(path, 'utf8'));
const stripped = (object, keys) => JSON.parse(JSON.stringify(object, (key, value) =>
  keys.includes(key) ? undefined : value));
let stage = 'review_receipt';

export function proveG6ReviewScope(reviewed, fresh, ui, now = new Date()) {
  for (const item of [reviewed, fresh]) {
    assert.equal(item.status, 'ready_for_review');
    assert.equal(item.apply_allowed, false);
    assert.equal(item.production_writes, 0);
    assert.equal(item.plan.adapter, ADAPTER);
    assert.equal(item.plan.intake.adapter, ADAPTER);
    assert.equal(item.plan.targets.length, 3);
    assert.equal(item.plan_hash, publicationHash(item.plan));
  }
  assert.equal(ui.status, 'passed_local_only');
  assert.equal(ui.plan_hash, reviewed.plan_hash);
  assert.equal(ui.main_review.capture_sha256, reviewed.review_hash);
  assert.equal(ui.main_review.apply_allowed, false);
  assert.equal(ui.main_review.candidate_count, ui.main_review.baseline_count + 3);
  assert.equal(ui.main_review.baseline_count, ui.main_review.preserved_other_variants);
  assert.equal(ui.main_review.photo_sha256, reviewed.plan.image.content_sha256);
  assert.equal(ui.publication_approved, false);
  assert.equal(ui.production_writes, 0);
  assert.equal(ui.paid_calls, 0);
  assert.equal(ui.runs.length, 12, 'Require the complete reviewed browser matrix');
  assert.equal(ui.comparison, true);
  assert.equal(ui.advisor_towing, true);
  assert.equal(ui.photo_attribution, true);
  assert(Date.parse(fresh.evidence_expires_at) > now.getTime(), 'Fresh production readback window expired');
  assert.notEqual(fresh.review_hash, reviewed.review_hash, 'Provide a newly fetched source packet');
  for (const key of ['expected_model', 'expected_alias', 'expected_market', 'expected_monthly', 'expected_sources', 'image']) {
    assert.deepEqual(fresh.plan[key], reviewed.plan[key], 'Reviewed production scope changed: ' + key);
  }
  // The workbook, reviewed image and technical PDF are stable. HTML may render different bytes without a fact changing.
  assert.deepEqual(stripped(fresh.plan.intake.market, ['fetched_at']), stripped(reviewed.plan.intake.market, ['fetched_at']),
    'Reviewed Swedish market workbook changed');
  const tech = report => report.plan.intake.sources.find(item => item.source_type === 'technical_pdf');
  assert.deepEqual(stripped(tech(fresh), ['fetched_at']), stripped(tech(reviewed), ['fetched_at']), 'Reviewed technical PDF changed');
  const captureKeys = ['fetched_at', 'content_hash', 'source_hash', 'authorization_hash'];
  assert.deepEqual(stripped(fresh.plan.intake, captureKeys), stripped(reviewed.plan.intake, captureKeys),
    'Reviewed G6 profiles or evidence changed');
  assert.deepEqual(stripped(fresh.plan.targets, captureKeys), stripped(reviewed.plan.targets, captureKeys),
    'Reviewed G6 target variants changed');
  assert(validateNewModelIntake(fresh.plan.intake, now).localOnly);
}

async function main() {
  const {values} = parseArgs({options: {reviewed: {type: 'string'}, ui: {type: 'string'}, fresh: {type: 'string'}}});
  assert(values.reviewed && values.ui && values.fresh, 'Supply reviewed readback, browser report, and fresh source capture');
  const root = await realpath('.');
  const evidence = await realpath(join(root, 'data', 'local', 'release-data'));
  assert.equal(evidence, join(root, 'data', 'local', 'release-data'));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(evidence));
  async function scoped(file, name, folder) {
    const path = await realpath(file);
    assert.equal(dirname(dirname(path)), evidence);
    assert.equal(basename(path), name);
    assert.match(basename(dirname(path)), folder);
    return path;
  }
  const reviewed = await asJson(await scoped(values.reviewed, 'readback.json', /^xpeng-g6-readback-[a-z0-9]+$/i));
  const ui = await asJson(await scoped(values.ui, 'report.json', /^xpeng-g6-ui-[a-z0-9]+$/i));
  stage = 'public_baseline';
  const expectedCommit = execFileSync('git', ['rev-parse', 'refs/remotes/origin/main'], {encoding: 'utf8'}).trim();
  assert.equal(ui.main_review.commit, expectedCommit, 'Main changed since the G6 browser review');
  const res = await fetch(liveCatalogUrl, {redirect: 'error', signal: AbortSignal.timeout(15000)});
  assert(res.ok);
  const live = await res.json();
  assert.equal(live.records.length, ui.main_review.baseline_count);
  assert.equal(catalogHash(live.records), ui.main_review.baseline_sha256, 'Public catalogue changed since the G6 browser review');
  stage = 'source_replay';
  const {intake, reviewHash} = readXpG6Capture(values.fresh);
  stage = 'read_only_scope';
  const connector = join(root, 'data', 'local', 'db-tools', 'source-client.mjs');
  assert.equal(await realpath(connector), connector);
  const {openSourceSnapshot, closeSourceSnapshot} = await import(pathToFileURL(connector).href);
  const client = await openSourceSnapshot();
  let fresh;
  try {
    useCalendarDateText(client);
    fresh = {...await prepareXpG6Readback(client, intake, readReviewedImage()), review_hash: reviewHash};
  } finally {
    await closeSourceSnapshot(client);
  }
  stage = 'compare_scope';
  proveG6ReviewScope(reviewed, fresh, ui);
  const output = await mkdtemp(join(evidence, 'xpeng-g6-release-review-'));
  const receipt = {status: 'maps_to_reviewed_release_candidate', reviewed_plan_sha256: reviewed.plan_hash,
    fresh_plan_sha256: fresh.plan_hash, source_review_hash: reviewHash, baseline_commit: expectedCommit,
    baseline_variants: live.records.length, models_to_add: 1, variants_to_add: 3,
    source_window_ends_at: fresh.evidence_expires_at, publication_approved: false,
    production_writes: 0, paid_calls: 0, apply_allowed: false};
  await writeFile(join(output, 'fresh-readback.json'), JSON.stringify(fresh, null, 2) + '\n', {flag: 'wx'});
  await writeFile(join(output, 'release-review.json'), JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({...receipt, output}));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) main().catch(error => {
  console.error(JSON.stringify({status: 'held', stage, code: typeof error.code === 'string' && /^[A-Z0-9_]{1,32}$/.test(error.code)
    ? error.code : null, reason: error.code === 'ERR_ASSERTION'
    ? error.message.split('\n')[0] : 'The read-only review check failed',
    production_writes: 0, paid_calls: 0, apply_allowed: false}));
  process.exitCode = 1;
});
