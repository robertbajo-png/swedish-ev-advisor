import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { loadEnv } from 'vite';
import { policy, readPumaCapture } from './ford_puma_gen_e_publication.mjs';
import { readPumaIdentity } from './ford_puma_identity.mjs';
import { assertPumaPriceMigration, pumaApprovalHash, pumaCatalogDelta, pumaReleaseReview, provePumaRelease } from './ford_puma_release_scope.mjs';
import { applyPumaRelease, publicationHash } from './new_model_publication.mjs';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';
import { CATALOG_PROJECT, catalogConnectorPath, openCatalogSnapshot } from './local_catalog_connector.mjs';
import { catalogHash, fetchCatalog, publicHeaders, SOURCE, variantKey } from './sync_public_catalog.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';

const origin = 'https://elbilsagenten.se';
const sha = /^[a-f0-9]{64}$/;
const gitSha = /^[a-f0-9]{40}$/;
const hash = body => createHash('sha256').update(body).digest('hex');
const codeHash = body => hash(body.toString('utf8').replace(/\r\n/g, '\n'));
const comparable = rows => catalogHash(catalogWithComparableTimes(rows));
const save = (path, value) => writeFile(path, JSON.stringify(value, null, 2) + '\n', {flag: 'wx'});
const unlinked = async (path) => assert.equal(await realpath(path), path, 'Require an unlinked Puma release path');
const bytes = async (path) => { await unlinked(path); return readFile(path); };
const json = async (path) => JSON.parse(await bytes(path));
const codeFiles = [
  'functions/_shared/advisor-core.mjs', 'database/migrations/026_manufacturer_from_price.sql',
  'scripts/prerender_static_routes.py', 'scripts/sync_public_catalog.mjs', 'scripts/new_model_publication.mjs',
  'scripts/ford_puma_identity.mjs', 'scripts/ford_puma_gen_e_publication.mjs', 'scripts/ford_puma_gen_e_review.py',
  'scripts/ford_puma_release_scope.mjs', 'scripts/publish_approved_ford_puma.mjs',
  'scripts/new_model_adapters.mjs', 'scripts/model_image_sync.mjs', 'src/puma-photo-policy.json',
  'scripts/isolated_catalog_review.mjs', 'scripts/import_mobility_sweden.py', 'scripts/local_catalog_connector.mjs',
];

export async function runPumaRelease({mode, reviewed, commit, approval}, io) {
  assert(['check', 'commit', 'export'].includes(mode));
  const required = pumaApprovalHash(reviewed, commit);
  if (mode !== 'check') assert.equal(approval, required, 'Puma release needs the explicit approved hash');
  await io.verifyCode(commit, reviewed.code);
  await io.verifyMedia(reviewed.media, reviewed.packet.image);
  const {records: baseline} = await io.baseline(commit);
  assert.equal(catalogHash(baseline), reviewed.baseline_sha256, 'Committed Puma baseline changed');
  const live = await io.liveBaseline();
  assert.equal(catalogHash(live), reviewed.baseline_sha256, 'The website baseline changed');

  if (mode === 'export') {
    const {attempt, receipt} = await io.readJournal();
    assert.equal(attempt.approval, required);
    assert.equal(attempt.commit, commit);
    assert.equal(receipt.attempt_sha256, publicationHash(attempt), 'Puma commit receipt does not match journal');
    const result = receipt.result;
    assert.equal(result.committed, true);
    assert.equal(result.publication_batch_id, publicationHash(attempt.fresh));
    assert.deepEqual(result.variant_plan.intake, attempt.fresh.intake);
    assert.deepEqual(result.variant_plan.image, reviewed.packet.image);
    assert.deepEqual([result.variants_inserted, result.anonymous_before_commit, result.atomic_identity, result.paid_calls], [2, true, true, 0]);
    const rows = await io.publicRows();
    const records = pumaCatalogDelta(baseline, rows, result.variant_plan);
    const keys = new Set(baseline.map(variantKey));
    const newRows = rows.filter(row => !keys.has(variantKey(row)));
    for (const {id, draft} of result.variant_plan.targets) {
      const row = newRows.find(row => row.variant_name === draft.variant_name);
      assert.equal(row.id,id,'Unexpected public Puma variant ID');
      assert.equal(row.canonical_model_id,result.model_id,'Unexpected public Puma model ID');
    }
    assert.deepEqual(await io.publicRows(),rows,'Canonical catalog changed during private export');
    const digest = catalogHash(records);
    await io.saveExport({source: SOURCE, schema_version: 1, generated_at: io.now().toISOString(),
      catalog_sha256: digest, records, missing_view_columns: []});
    return {status: 'private_export_verified', catalog_sha256: digest, added: 2, deployed: false, paid_calls: 0};
  }
  assert.equal(comparable(await io.publicRows()), reviewed.packet.baseline_sha256, 'Anonymous Supabase baseline changed');
  const intake = await io.freshSource();
  const client = await io.openSnapshot();
  try {
    await assertPumaPriceMigration(client);
    const fresh = {...reviewed.packet, intake, ...await io.readState(client, intake)};
    provePumaRelease(reviewed, fresh, commit, required, io.now());
    if (mode === 'check') return {status: 'ready_for_explicit_owner_approval', scope_sha256: required, variants: 2,
      prior_variants: baseline.length, production_writes: 0, paid_calls: 0};
    assert.equal(comparable(await io.publicRows()), reviewed.packet.baseline_sha256, 'Anonymous Supabase baseline changed before write');
    const attempt = {approval: required, commit, fresh};
    await io.saveAttempt(attempt);
    const result = await io.commit(client, fresh, required);
    assert.equal(result.publication_batch_id, publicationHash(fresh));
    assert.deepEqual([result.committed, result.atomic_identity, result.variants_inserted, result.anonymous_before_commit, result.paid_calls],
      [true, true, 2, true, 0]);
    await io.saveCommit({attempt_sha256: publicationHash(attempt), result});
    return {status: 'committed_private_export_pending', added: 2, deployed: false, paid_calls: 0};
  } finally { await io.closeSnapshot(client); }
}

async function prepare(root, evidence, folder, uiPath) {
  assert.equal(dirname(folder), evidence);
  assert.match(basename(folder), /^ford-puma-local-[a-z0-9]+$/i);
  assert.equal(dirname(dirname(uiPath)), folder);
  assert.match(basename(dirname(uiPath)), /^ui-[a-z0-9]+$/i);
  assert.equal(basename(uiPath), 'ui-report.json');
  const [packet, plan, report, ui, baseline, candidate] = await Promise.all([
    json(join(folder, 'atomic-packet.json')), json(join(folder, 'puma-plan.json')), json(join(folder, 'report.json')),
    json(uiPath), json(join(folder, 'main-source/public/data/public_ev_variants.json')), json(join(folder, 'candidate-catalog.json')),
  ]);
  const uiSource = join(dirname(uiPath), 'source');
  const manifest = await json(join(uiSource, 'src/image-variants.json'));
  const item = manifest[packet.image.asset_url];
  assert.equal(item.source_sha256, packet.image.content_sha256);
  const media = [{url: packet.image.asset_url, sha256: packet.image.content_sha256},
    ...item.variants.map(({url, sha256}) => ({url, sha256}))];
  for (const m of media) {
    assert.match(m.url, /^\/media\/(?:vehicles|responsive)\/[a-z0-9-]+\.(?:jpg|webp)$/);
    assert.equal(hash(await bytes(join(uiSource, 'public', m.url.slice(1)))), m.sha256);
  }
  const code = {};
  const observedUi = {};
  for (const path of [...Object.keys(ui.price_ui_sha256), ...codeFiles].sort()) {
    assert(/^src\/[a-z0-9-]+\.(?:jsx|js)$/.test(path) || codeFiles.includes(path));
    const body = await bytes(join(root, path));
    code[path] = codeHash(body);
    if (path in ui.price_ui_sha256) observedUi[path] = hash(body);
  }
  const reviewed = pumaReleaseReview({packet, plan, report, ui, baseline: baseline.records, candidate: candidate.records, media, code, observedUi});
  const out = join(await mkdtemp(join(evidence, 'ford-puma-release-review-')), 'scope.json');
  await save(out, reviewed);
  return {status: reviewed.status, scope: out, reviewed_sha256: publicationHash(reviewed), variants: 2,
    production_writes: 0, publication_approved: false, paid_calls: 0};
}

let stage = 'arguments';
async function main() {
  const {values, positionals} = parseArgs({options: {
    review: {type: 'string'}, ui: {type: 'string'}, scope: {type: 'string'}, fresh: {type: 'string'},
    'release-commit': {type: 'string'}, 'commit-approved': {type: 'string'}, 'export-approved': {type: 'string'}, journal: {type: 'string'},
    'client-module': {type:'string'},
  }, allowPositionals: true});
  assert.equal(positionals.length, 0);
  const root = await realpath('.');
  const evidence = join(root, 'data/local/release-data');
  await unlinked(evidence);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(evidence));
  if (values.review || values.ui) {
    assert(values.review && values.ui && Object.keys(values).length === 2, 'Use only --review and --ui to prepare the release scope');
    return prepare(root, evidence, resolve(values.review), resolve(values.ui));
  }
  assert(values.scope && values['release-commit']);
  assert(!(values['commit-approved'] && values['export-approved']));
  const mode = values['commit-approved'] ? 'commit' : values['export-approved'] ? 'export' : 'check';
  assert(values.fresh || mode === 'export', 'A new replayed Puma source capture is required');
  assert(mode === 'check' ? !values.journal : values.journal, 'Use a new private journal for commit, or its existing path for export');
  const path = resolve(values.scope);
  assert.equal(dirname(dirname(path)), evidence);
  assert.match(basename(dirname(path)), /^ford-puma-release-review-[a-z0-9]+$/i);
  assert.equal(basename(path), 'scope.json');
  const reviewed = await json(path);
  const commit = values['release-commit'], approval = values['commit-approved'] ?? values['export-approved'];
  const git = (...args) => execFileSync('git', args, {cwd: root, timeout: 30000, maxBuffer: 32_000_000});
  const journal = values.journal && resolve(values.journal);
  if (journal) {
    assert.equal(dirname(journal), evidence);
    assert.match(basename(journal), /^ford-puma-apply-[a-z0-9-]+$/);
  }
  const connection = await catalogConnectorPath(root,values['client-module']);
  const env = {...loadEnv('production', connection.sourceRoot, 'SUPABASE_'), ...loadEnv('production', connection.sourceRoot, 'VITE_SUPABASE_')};
  const dbUrl = env.SUPABASE_URL || env.VITE_SUPABASE_URL, key = env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY;
  let snapshot;
  async function live(pathname) {
    const response = await fetch(origin + pathname, {redirect: 'error', signal: AbortSignal.timeout(20000)});
    assert(response.ok, 'Published Puma prerequisite missing: ' + pathname);
    return response;
  }
  return runPumaRelease({mode, reviewed, commit, approval}, {
    now: () => new Date(),
    async verifyCode(revision, code) {
      stage = 'exact_main';
      assert.match(revision, gitSha);
      assert.equal(git('ls-remote', 'origin', 'refs/heads/main').toString().trim(),
        revision + '\trefs/heads/main', 'Reviewed production commit is not current main');
      for (const [path, digest] of Object.entries(code)) {
        const allowed = /^src\/[a-z0-9-]+\.(?:jsx|js)$/.test(path) || codeFiles.includes(path);
        assert(allowed && sha.test(digest));
        assert.equal(codeHash(git('show', revision + ':' + path)), digest, 'Exact main lacks reviewed Puma code: ' + path);
      }
      if (mode === 'commit') {
        assert.equal(await realpath(git('rev-parse', '--show-toplevel').toString().trim()), root);
        assert.equal(git('rev-parse', 'HEAD').toString().trim(), revision);
        assert.equal(git('status', '--porcelain', '--untracked-files=no').toString().trim(), '', 'Commit from a clean, exact-main checkout only');
      }
    },
    async verifyMedia(media, image) {
      stage = 'exact_published_photograph';
      const registry = name => JSON.parse(git('show', commit + ':src/' + name + '.json'));
      const assets = registry('image-rights').assets.filter(row => row.model_key === image.model_key);
      assert.equal(assets.length, 1, 'Require reviewed Puma image attribution in main');
      for (const [key, value] of Object.entries(image)) assert.deepEqual(assets[0][key], value, 'Puma image attribution changed: ' + key);
      assert.equal(registry('model-images')[image.model_key], image.asset_url);
      const file = registry('image-variants')[image.asset_url];
      assert.equal(file.source_sha256, image.content_sha256);
      assert.deepEqual(file.variants.map(({url, sha256}) => ({url, sha256})), media.slice(1));
      for (const m of media) {
        assert.match(m.url, /^\/media\/(?:vehicles|responsive)\/[a-z0-9-]+\.(?:jpg|webp)$/);
        assert.equal(hash(git('show', commit + ':public' + m.url)), m.sha256, 'Main photo differs from the browser proof');
        assert.equal(hash(Buffer.from(await (await live(m.url)).arrayBuffer())), m.sha256, 'Live photo differs from the browser proof');
      }
      const homepage = await (await live('/')).text();
      const bundles = [...homepage.matchAll(/<script[^>]*\bsrc="(\/assets\/index-[a-zA-Z0-9_-]+\.js)"[^>]*>/g)];
      assert.equal(bundles.length, 1, 'Require exact live reader entry bundle');
      const bundle = await (await live(bundles[0][1])).text();
      assert.match(bundle, /manufacturer_from/, 'Starting-price reader is not deployed');
    },
    baseline: revision => JSON.parse(git('show', revision + ':public/data/public_ev_variants.json')),
    liveBaseline: async () => (await (await live('/data/public_ev_variants.json')).json()).records,
    publicRows() {
      stage = 'anonymous_supabase';
      assert.equal(new URL(dbUrl).origin, 'https://' + CATALOG_PROJECT + '.supabase.co');
      publicHeaders(key);
      return fetchCatalog({url: dbUrl, key, includeIds:mode==='export', onSchema: missing => assert.deepEqual(missing, [])});
    },
    freshSource: () => {stage = 'source_replay'; return readPumaCapture(values.fresh).intake;},
    async openSnapshot() {
      stage = 'read_only_database_prerequisites';
      snapshot = await openCatalogSnapshot(connection);
      return snapshot.client;
    },
    async readState(client, intake) {
      const identity = await readPumaIdentity(client);
      const {rows} = await client.query('SELECT * FROM public.manufacturer_sources WHERE url=ANY($1::text[]) ORDER BY id',
        [intake.sources.map(s => s.final_url)]);
      const drafts = await client.query('SELECT id FROM public.extracted_variant_drafts WHERE source_url=$1 AND variant_name=ANY($2::text[])',
        [policy.primaryUrl, intake.drafts.map(d => d.variant_name)]);
      assert.equal(drafts.rows.length, 0, 'Existing Puma draft requires separate review');
      return {identity, expected_sources: JSON.parse(JSON.stringify(rows))};
    },
    closeSnapshot: () => snapshot.close(),
    async saveAttempt(value) {
      stage = 'journal_new_attempt';
      await mkdir(journal);
      await unlinked(journal);
      await save(join(journal, 'attempt.json'), value);
    },
    async commit(client, fresh, hash) {
      stage = 'approved_atomic_database_transaction';
      await client.query('ROLLBACK');
      useCalendarDateText(client);
      return applyPumaRelease(client, reviewed, fresh, commit, hash);
    },
    saveCommit: value => save(join(journal, 'committed-receipt.json'), value),
    async readJournal() {
      await unlinked(journal);
      return {attempt: await json(join(journal, 'attempt.json')), receipt: await json(join(journal, 'committed-receipt.json'))};
    },
    saveExport: value => save(join(journal, 'candidate-catalog.json'), value),
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().then(result => {
  console.log(JSON.stringify(result));
}).catch(error => {
  console.error(JSON.stringify({status: 'held', stage, code: error.code ?? null,
    ...(error.code === 'ERR_ASSERTION' ? {reason: error.message.split('\n')[0]} : {}),
    production_write_attempted: stage === 'approved_atomic_database_transaction'}));
  process.exitCode = 1;
});
