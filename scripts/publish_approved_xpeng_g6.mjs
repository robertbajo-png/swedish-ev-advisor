import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { loadEnv } from 'vite';
import { applyXpG6Release, publicationHash } from './new_model_publication.mjs';
import { prepareXpG6Readback } from './prepare_xpeng_g6_readback.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { proveG6ReviewScope } from './revalidate_xpeng_g6_release.mjs';
import { atomicJson, catalogHash, fetchCatalog, publicHeaders, SOURCE } from './sync_public_catalog.mjs';
import { verifyXpG6CatalogDelta } from './xpeng_g6_distribution.mjs';
import { ADAPTER, readReviewedImage, readXpG6Capture } from './xpeng_g6_publication.mjs';

const project = 'eutcryxbitudllcnpnex';
const catalogPath = 'public/data/public_ev_variants.json';
const shaPattern = /^[a-f0-9]{64}$/;
let stage = 'arguments';
let requestedMode = 'check';
const json = async file => JSON.parse(await readFile(file, 'utf8'));
const sha = body => createHash('sha256').update(body).digest('hex');
const samePath = async path => assert.equal(await realpath(path), path, 'Unexpected linked release path');

export function releaseMode(values) {
  assert(!(values['commit-plan'] && values['resume-export']), 'Choose commit or export recovery, not both');
  const hash = values['commit-plan'] ?? values['resume-export'];
  if (hash !== undefined) assert.match(hash, shaPattern, 'Supply the exact approved G6 plan hash');
  return { mode: values['commit-plan'] ? 'commit' : values['resume-export'] ? 'export' : 'check', hash };
}

export async function verifyRegisteredPhoto(root, image) {
  const file = 'xpeng-g6-press-3d0ad9b81b94';
  const original = '/media/vehicles/' + file + '.jpg';
  assert.equal(image.asset_url, original);
  assert.equal(image.model_key, 'xpeng|g6');
  const { assets } = await json(join(root, 'src/image-rights.json'));
  const registered = assets.filter(asset => asset.model_key === image.model_key || asset.asset_url === original);
  assert.equal(registered.length, 1, 'Register exactly one reviewed G6 photo');
  for (const [key, value] of Object.entries(image)) {
    assert.deepEqual(registered[0][key], value, 'Registered G6 image differs: ' + key);
  }
  assert.equal((await json(join(root, 'src/model-images.json')))[image.model_key], original);
  const responsive = (await json(join(root, 'src/image-variants.json')))[original];
  assert.equal(responsive.source_sha256, image.content_sha256);
  assert.deepEqual(responsive.variants.map(asset => asset.width), [480, 800, 1280]);
  for (const { width, url, sha256 } of [{ url: original, sha256: image.content_sha256 }, ...responsive.variants]) {
    if (width) assert.equal(url, '/media/responsive/' + file + '-' + width + '.webp');
    const path = join(root, 'public', url.slice(1));
    await samePath(path);
    assert.equal(sha(await readFile(path)), sha256, 'Registered G6 photo bytes changed');
  }
}

function verifyCommit(result, plan) {
  assert.equal(plan.adapter, ADAPTER);
  assert.equal(result.committed, true, 'No verified G6 commit');
  assert.equal(result.anonymous_before_commit, true);
  assert.equal(result.variants_inserted, 3);
  assert.equal(result.model_id, plan.expected_model.id);
  assert.equal(result.publication_batch_id, publicationHash(plan));
  assert.deepEqual(result.canonical_variant_ids, plan.targets.map(target => target.id));
  assert.equal(result.paid_calls, 0);
}

async function exportResult(io, receipt) {
  verifyCommit(receipt.result, receipt.plan);
  assert.equal(catalogHash(receipt.baseline), receipt.baseline_hash, 'Original G6 export baseline changed');
  const first = await io.publicRows();
  assert.deepEqual(first.missing, [], 'Canonical export schema changed');
  const delta = verifyXpG6CatalogDelta(receipt.baseline, first.rows, receipt.plan);
  const second = await io.publicRows();
  const hash = catalogHash(first.rows);
  assert.deepEqual(second.missing, []);
  assert.equal(catalogHash(second.rows), hash, 'Public catalog changed during G6 export');
  const current = catalogHash((await io.existingCatalog()).records);
  assert([receipt.baseline_hash, hash].includes(current), 'Local catalog changed since G6 preparation');
  if (current !== hash) await io.saveCatalog({ generated_at: io.now().toISOString(), source: SOURCE,
    schema_version: 1, missing_view_columns: [], catalog_sha256: hash, records: first.rows });
  return { status: 'export_verified', ...delta, catalog_sha256: hash, paid_calls: 0 };
}

export async function runXpG6Release(options, io) {
  const { mode, hash } = options;
  assert(['check', 'commit', 'export'].includes(mode));
  if (mode === 'export') {
    assert.match(hash ?? '', shaPattern);
    const { attempt, committed } = await io.readJournal();
    assert.equal(attempt.approved_hash, hash, 'Not the approved G6 export');
    assert.equal(committed.approved_hash, hash);
    assert.equal(attempt.fresh_plan_hash, publicationHash(committed.plan), 'Journal plan mismatch');
    assert.equal(attempt.baseline_hash, committed.baseline_hash, 'Journal baseline mismatch');
    await io.verifyPhoto(committed.plan.image);
    return exportResult(io, committed);
  }
  const { reviewed, ui } = options;
  if (mode === 'commit') {
    assert.match(hash ?? '', shaPattern, 'Require explicit approved G6 plan');
    assert.equal(reviewed.plan_hash, hash, 'Wrong approved G6 plan');
  }
  const expectedRuns = [320, 390, 768, 1440].flatMap(width => ['awd-performance', 'rwd-long-range', 'rwd-standard-range']
    .map(version => 'xpeng-g6-' + version + '-20-tum:' + width)).sort();
  assert.deepEqual(ui.runs.map(run => run.slug + ':' + run.width).sort(), expectedRuns, 'Reviewed G6 browser matrix differs');
  assert.equal(ui.distribution?.intercepted_catalog, false, 'Require a review of the real build catalog');
  assert.equal(ui.distribution.intercepted_images, false, 'Require a review of the shipped photos');
  assert.equal(ui.distribution.preserved, ui.main_review.baseline_count);
  assert.equal(ui.distribution.count, ui.main_review.candidate_count);
  await io.checkMain(ui.main_review.commit);
  const baseline = (await io.existingCatalog()).records;
  const baseline_hash = catalogHash(baseline);
  assert.equal(baseline.length, ui.main_review.baseline_count);
  assert.equal(baseline_hash, ui.main_review.baseline_sha256, 'Checked-in catalog differs from the reviewed baseline');
  const checkPublic = async () => {
    const current = await io.publicRows();
    assert.deepEqual(current.missing, [], 'Canonical public view contract changed');
    assert.equal(catalogHash(current.rows), baseline_hash, 'Canonical catalog changed since G6 review');
  };
  await checkPublic();
  await io.verifyPhoto(reviewed.plan.image);
  const observed = await io.freshSource();
  const prepared = await io.openSnapshot();
  try {
    const fresh = await io.prepare(prepared, observed, reviewed.plan.image);
    proveG6ReviewScope(reviewed, fresh, ui, io.now());
    if (mode === 'check') return { status: 'ready_for_owner_review', variants: 3, baseline_count: baseline.length,
      reviewed_plan_sha256: reviewed.plan_hash, fresh_plan_sha256: fresh.plan_hash,
      evidence_expires_at: fresh.evidence_expires_at, production_writes: 0, paid_calls: 0 };
    await checkPublic();
    assert.equal(catalogHash((await io.existingCatalog()).records), baseline_hash, 'Local catalog changed during preparation');
    await io.beginJournal({ approved_hash: hash, fresh_plan_hash: fresh.plan_hash, baseline_hash });
    const result = await io.commit(prepared, fresh, reviewed, ui, hash, baseline_hash);
    verifyCommit(result, fresh.plan);
    const receipt = { approved_hash: hash, plan: fresh.plan, baseline, baseline_hash, result };
    await io.writeCommit(receipt);
    return { ...await exportResult(io, receipt), database_transaction: 'committed' };
  } finally {
    await io.closeSnapshot(prepared);
  }
}

async function main() {
  const { values } = parseArgs({ options: { reviewed: { type: 'string' }, ui: { type: 'string' },
    fresh: { type: 'string' }, output: { type: 'string' }, 'client-module': { type: 'string' },
    'commit-plan': { type: 'string' }, 'resume-export': { type: 'string' } } });
  const { mode, hash } = releaseMode(values);
  requestedMode = mode;
  stage = 'local_paths';
  const root = await realpath('.');
  const evidence = join(root, 'data', 'local', 'release-data');
  await samePath(evidence);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(root), 'Require the local project, not OneDrive');
  assert(values['client-module'], 'Supply the existing local source connector path');
  const connectorPath = resolve(values['client-module']);
  await samePath(connectorPath);
  const sourceRoot = resolve(dirname(connectorPath), '../../..');
  assert.equal(connectorPath, join(sourceRoot, 'data', 'local', 'db-tools', 'source-client.mjs'));
  const sourceLocal = join(sourceRoot, 'data', 'local', 'release-data');
  const rel = relative(sourceLocal, root);
  assert(root === sourceRoot || (rel && !rel.startsWith('..') && !isAbsolute(rel)), 'Require the existing project connector');
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(sourceRoot));
  stage = 'production_configuration';
  const env = { ...loadEnv('production', sourceRoot, 'SUPABASE_'), ...loadEnv('production', sourceRoot, 'VITE_SUPABASE_') };
  const url = env.SUPABASE_URL || env.VITE_SUPABASE_URL;
  assert.equal(new URL(url).origin, 'https://' + project + '.supabase.co', 'Unexpected canonical project');
  const key = env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY;
  publicHeaders(key);
  const file = join(root, catalogPath);
  stage = 'input_receipts';
  await samePath(file);
  let folder;
  if (mode !== 'check') {
    assert(values.output, 'Supply a private G6 release journal directory');
    folder = resolve(values.output);
    assert.equal(dirname(folder), evidence);
    assert.match(basename(folder), /^xpeng-g6-release-[a-z0-9-]+$/);
  }
  async function privateReceipt(input, filename, prefix) {
    const path = resolve(input);
    await samePath(path);
    assert.equal(dirname(dirname(path)), evidence);
    assert(basename(dirname(path)).startsWith(prefix));
    assert.equal(basename(path), filename);
    return json(path);
  }
  const options = { mode, hash };
  if (mode !== 'export') {
    assert(values.reviewed && values.ui && values.fresh, 'Supply reviewed readback, browser report and new source capture');
    options.reviewed = await privateReceipt(values.reviewed, 'readback.json', 'xpeng-g6-readback-');
    options.ui = await privateReceipt(values.ui, 'report.json', 'xpeng-g6-ui-');
  } else assert(!(values.reviewed || values.ui || values.fresh), 'Export recovery uses only the committed journal');
  const journal = name => join(folder, name + '.json');
  const safeReadJournal = async name => { const path = journal(name); await samePath(path); return json(path); };
  const saveNew = (path, value) => writeFile(path, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
  let connector;
  const result = await runXpG6Release(options, {
    now: () => new Date(),
    checkMain(commit) {
      stage = 'main_revision';
      assert.match(commit, /^[a-f0-9]{40}$/);
      const current = execFileSync('git', ['ls-remote', 'origin', 'refs/heads/main'],
        { cwd: sourceRoot, encoding: 'utf8', timeout: 20000 }).trim();
      assert.equal(current, commit + '\trefs/heads/main', 'Main changed since browser review');
    },
    existingCatalog: () => json(file),
    async publicRows() {
      stage = 'public_catalog';
      let missing;
      const rows = await fetchCatalog({ url, key, onSchema: value => { missing = value; } });
      return { rows, missing };
    },
    verifyPhoto: image => { stage = 'photo_registry'; return verifyRegisteredPhoto(root, image); },
    freshSource: () => { stage = 'source_replay'; return readXpG6Capture(values.fresh); },
    async openSnapshot() {
      stage = 'open_readonly_snapshot';
      connector = await import(pathToFileURL(connectorPath).href);
      assert.equal(connector.PROJECT_REF, project);
      process.chdir(sourceRoot);
      try { return await connector.openSourceSnapshot(); }
      finally { process.chdir(root); }
    },
    async prepare(client, { intake, reviewHash }, image) {
      stage = 'readback_and_review_comparison';
      useCalendarDateText(client);
      assert.deepEqual(image, readReviewedImage(), 'Reviewed photo changed');
      return { ...await prepareXpG6Readback(client, intake, image), review_hash: reviewHash };
    },
    closeSnapshot: client => connector.closeSourceSnapshot(client),
    async beginJournal(attempt) {
      stage = 'attempt_journal';
      await mkdir(folder);
      await samePath(folder);
      await saveNew(journal('attempt'), attempt);
    },
    async commit(client, fresh, reviewed, ui, approval, baseline) {
      stage = 'g6_transaction';
      await client.query('ROLLBACK');
      return applyXpG6Release(client, fresh, reviewed, ui, approval, new Date(), baseline);
    },
    writeCommit: receipt => { stage = 'commit_receipt'; return saveNew(journal('committed-receipt'), receipt); },
    async readJournal() {
      stage = 'export_journal';
      await samePath(folder);
      return { attempt: await safeReadJournal('attempt'), committed: await safeReadJournal('committed-receipt') };
    },
    saveCatalog: async value => { stage = 'save_catalog'; await samePath(file); await atomicJson(file, value); },
  });
  console.log(JSON.stringify(result));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) main().catch(error => {
  console.error(JSON.stringify({ status: 'held_or_incomplete', stage,
    code: /^[A-Z0-9_]{1,32}$/.test(error.code ?? '') ? error.code : null,
    reason: error.code === 'ERR_ASSERTION' ? error.message.split('\n')[0] : 'G6 release step failed',
    action: requestedMode === 'check' ? 'Read-only check stopped; no release journal was created.'
      : 'Inspect the private journal before retrying. If a commit receipt exists, use export recovery only.' }));
  process.exitCode = 1;
});
