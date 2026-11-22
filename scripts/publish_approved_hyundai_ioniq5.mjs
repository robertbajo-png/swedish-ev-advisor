import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { loadEnv } from 'vite';
import { readIoniq5Capture, readReviewedPhoto } from './hyundai_ioniq5_publication.mjs';
import { CATALOG_PROJECT, catalogConnectorPath, openCatalogSnapshot } from './local_catalog_connector.mjs';
import { isIoniq5 } from './hyundai_ioniq5_distribution.mjs';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';
import { assertIoniq5PublishedRows, ioniq5ReleaseReceipt, proveIoniq5ReleaseScope } from './hyundai_ioniq5_release_scope.mjs';
import { applyIoniq5Release, publicationHash } from './new_model_publication.mjs';
import { prepareIoniq5Readback } from './prepare_hyundai_ioniq5_readback.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { atomicJson, catalogHash, compareCatalogs, fetchCatalog, normalizeCatalog, publicHeaders, SOURCE, variantKey } from './sync_public_catalog.mjs';
import { hasVariantPhotoMigration } from './verify_variant_photo_migration.mjs';

const shaPattern = /^[a-f0-9]{64}$/;
const json = async path => JSON.parse(await readFile(path, 'utf8'));
const samePath = async path => assert.equal(await realpath(path), path, 'Require an unlinked release path');
const hash = body => createHash('sha256').update(body).digest('hex');
const saveNew = (path, value) => writeFile(path, JSON.stringify(value, null, 2) + '\n', {flag: 'wx'});
let stage = 'arguments';

export function assertIoniq5MainRevision(commit, {local = false, exportRecovery = false} = {}) {
  const git = (...args) => execFileSync('git', args, {encoding:'utf8', timeout:20000}).trim();
  assert.match(commit, /^[a-f0-9]{40}$/);
  assert.equal(git('ls-remote','origin','refs/heads/main'), commit + '\trefs/heads/main',
    'Main changed since Ioniq 5 browser review');
  if (local) {
    assert.equal(git('rev-parse','HEAD'), commit, 'Operate on the browser-reviewed main commit');
    assert.equal(git('status','--porcelain=v1','--untracked-files=all','--','scripts','src','database','public/media',
      'vite.config.mjs','package.json','bun.lock','functions','index.html',
      ...(exportRecovery ? [] : ['public/data/public_ev_variants.json'])),
    '', 'Release inputs differ from reviewed main');
  }
}

export async function verifyIoniq5RegisteredMedia(root, plan, report) {
  const [base, edition] = ['base', 'nLine'].map(name => readReviewedPhoto(name).image);
  assert.deepEqual(base, plan.image);
  const registry = (await json(join(root, 'src/image-rights.json'))).assets.filter(asset => asset.model_key === base.model_key);
  assert.equal(registry.length, 2);
  assert.equal((await json(join(root, 'src/model-images.json')))[base.model_key], base.asset_url);
  const responsive = await json(join(root, 'src/image-variants.json'));
  const files = [];
  for (const image of [base, edition]) {
    const registered = registry.find(row => row.asset_url === image.asset_url);
    assert(registered);
    for (const [key, value] of Object.entries(image)) assert.deepEqual(registered[key], value, 'Changed image metadata: ' + key);
    if (image === base) assert(!Object.hasOwn(registered, 'variant_names'));
    else assert.deepEqual(registered.variant_names.slice().sort(), plan.targets
      .filter(({draft}) => draft.variant_name.endsWith(' N Line')).map(({draft}) => draft.variant_name).sort());
    const manifest = responsive[image.asset_url];
    assert.equal(manifest.source_sha256, image.content_sha256);
    assert.deepEqual(manifest.variants.map(row => row.width), [480, 800, 1280]);
    for (const file of [{url: image.asset_url, sha256: image.content_sha256}, ...manifest.variants]) {
      const {width, url, sha256} = file;
      if (width) assert.equal(url, image.asset_url.replace('/vehicles/', '/responsive/').replace('.jpg', '-' + width + '.webp'));
      const path = join(root, 'public', url.slice(1));
      await samePath(path);
      assert.equal(hash(await readFile(path)), sha256, 'Registered Ioniq 5 image bytes changed');
      files.push({url, ...(width ? {width} : {}), sha256});
    }
  }
  if (report) assert.deepEqual(files, report.distribution.static_assets, 'Shipped image bundle differs from browser review');
  return publicationHash(files);
}

function requireCommit(result, plan) {
  assert.equal(result.committed, true);
  assert.equal(result.anonymous_before_commit, true);
  assert.equal(result.variants_inserted, 7);
  assert.equal(result.model_id, plan.expected_model.id);
  assert.deepEqual(result.canonical_variant_ids, plan.targets.map(target => target.id));
  assert.equal(result.publication_batch_id, publicationHash(plan));
  assert.equal(result.paid_calls, 0);
}

async function exportReviewed(io, committed) {
  const {plan, result, baseline, baseline_hash, baseline_identities} = committed;
  requireCommit(result, plan);
  assert.equal(catalogHash(baseline), baseline_hash);
  const rows = await io.publicRows({includeIds:true});
  const difference = compareCatalogs(baseline, rows);
  assert.deepEqual(difference.local_only, [], 'Existing public rows disappeared');
  assert.deepEqual(difference.changed, [], 'Existing public rows changed');
  assert.deepEqual(difference.remote_only.slice().sort(),
    plan.targets.map(({draft}) => variantKey({...plan.intake.model, variant_name: draft.variant_name})).sort());
  const ioniq5 = rows.filter(isIoniq5);
  assertIoniq5PublishedRows(ioniq5, plan);
  const expected = new Map(plan.targets.map(({draft,id}) => [
    variantKey({...plan.intake.model,variant_name:draft.variant_name}), id,
  ]));
  for (const row of ioniq5) {
    assert.equal(row.id, expected.get(variantKey(row)), 'Unexpected public Ioniq 5 variant ID');
    assert.equal(row.canonical_model_id, plan.expected_model.id, 'Unexpected public Ioniq 5 model ID');
  }
  assert.deepEqual(catalogIdentities(rows.filter(row => !isIoniq5(row))), baseline_identities, 'Existing public IDs changed');
  const catalog_sha256 = catalogHash(rows);
  assert.deepEqual(await io.publicRows({includeIds:true}), rows, 'Anonymous catalog changed during export');
  const current = catalogHash((await io.catalog()).records);
  assert([baseline_hash, catalog_sha256].includes(current), 'Checked-in catalog changed during release');
  if (current !== catalog_sha256) await io.saveCatalog({generated_at: io.now().toISOString(), source: SOURCE,
    schema_version: 1, missing_view_columns: [], catalog_sha256, records: normalizeCatalog(rows)});
  return {status: 'export_verified', added: 7, preserved: baseline.length, catalog_sha256, paid_calls: 0};
}

function catalogIdentities(rows) {
  const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  return rows.map(row => {
    assert.match(row.id, uuid, 'Missing public variant ID');
    assert.match(row.canonical_model_id, uuid, 'Missing public model ID');
    return [variantKey(row), row.id, row.canonical_model_id];
  });
}

export async function runIoniq5Release({mode, approval, reviewed, ui}, io) {
  assert(['check','commit','export'].includes(mode));
  if (mode !== 'check') assert.match(approval ?? '', shaPattern, 'Require the exact approved Ioniq 5 plan hash');
  if (mode === 'export') {
    const {attempt, committed} = await io.readJournal();
    assert.equal(attempt.approval, approval);
    assert.equal(committed.approval, approval);
    assert.equal(attempt.fresh_plan_hash, publicationHash(committed.plan), 'Ioniq 5 commit journal differs');
    assert.equal(attempt.baseline_hash, committed.baseline_hash);
    assert.equal(attempt.main_commit, committed.main_commit);
    assert.equal(attempt.baseline_identity_hash, publicationHash(committed.baseline_identities));
    await io.assertMain(committed.main_commit);
    assert.equal(await io.verifyMedia(committed.plan), attempt.media_hash);
    return exportReviewed(io, committed);
  }
  if (mode === 'commit') assert.equal(approval, reviewed.plan_hash, 'Invalid Ioniq 5 approval');
  await io.assertMain(ui.baseline.commit);
  const {records: baseline} = await io.catalog();
  const baseline_hash = catalogHash(baseline);
  assert.equal(baseline_hash, ui.baseline.baseline_sha256, 'Ioniq 5 review baseline changed');
  assert.equal(catalogHash(catalogWithComparableTimes(baseline)),ui.baseline.database_baseline_sha256,'Ioniq 5 database baseline changed');
  assert.equal(baseline.length, ui.baseline.baseline_count);
  const confirmPublic = async () => {
    const rows = await io.publicRows({includeIds:true});
    assert.equal(catalogHash(rows), baseline_hash, 'Canonical catalog changed');
    return catalogIdentities(rows);
  };
  const baseline_identities = await confirmPublic();
  const media_hash = await io.verifyMedia(reviewed.plan, ui, mode);
  const input = await io.freshSource();
  const client = await io.openSnapshot();
  try {
    const fresh = await io.prepare(client, input);
    proveIoniq5ReleaseScope(reviewed, fresh, ui, reviewed.plan_hash, io.now());
    const migration = await io.photoMigration(client);
    if (mode === 'check') return {status: migration ? 'ready_for_owner_review' : 'held_for_migration_025',
      variants: 7, preserved: baseline.length, reviewed_plan_sha256: reviewed.plan_hash,
      source_window_ends_at: fresh.evidence_expires_at, production_writes: 0, paid_calls: 0};
    assert(migration, 'Install only separately approved migration 025 before Ioniq 5 release');
    assert.deepEqual(await confirmPublic(), baseline_identities, 'Canonical identities changed');
    assert.equal(catalogHash((await io.catalog()).records), baseline_hash);
    const main_commit = ui.baseline.commit;
    await io.beginJournal({approval, fresh_plan_hash: fresh.plan_hash, baseline_hash, media_hash, main_commit,
      baseline_identity_hash:publicationHash(baseline_identities)});
    const result = await io.commit(client, fresh, reviewed, ui, approval);
    requireCommit(result, fresh.plan);
    const receipt = {approval, plan: fresh.plan, baseline, baseline_hash, baseline_identities, main_commit, result};
    await io.saveCommit(receipt);
    return {...await exportReviewed(io, receipt), database_transaction: 'committed'};
  } finally {
    await io.closeSnapshot(client);
  }
}

async function main() {
  const {values} = parseArgs({options: {reviewed: {type:'string'}, fresh: {type:'string'}, ui: {type:'string'},
    output: {type:'string'}, 'client-module': {type:'string'}, 'commit-plan': {type:'string'}, 'resume-export': {type:'string'}}});
  assert(!(values['commit-plan'] && values['resume-export']), 'Choose commit or export recovery');
  const approval = values['commit-plan'] ?? values['resume-export'];
  if (approval !== undefined) assert.match(approval, shaPattern);
  const mode = values['commit-plan'] ? 'commit' : values['resume-export'] ? 'export' : 'check';
  const root = await realpath('.');
  const evidence = join(root, 'data', 'local', 'release-data');
  await samePath(evidence);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(root));
  const catalog = join(root, 'public/data/public_ev_variants.json');
  await samePath(catalog);
  const connection = await catalogConnectorPath(root, values['client-module']);
  const { sourceRoot } = connection;
  const env = {...loadEnv('production', sourceRoot, 'SUPABASE_'), ...loadEnv('production', sourceRoot, 'VITE_SUPABASE_')};
  const url = env.SUPABASE_URL || env.VITE_SUPABASE_URL, key = env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY;
  assert.equal(new URL(url).origin, 'https://' + CATALOG_PROJECT + '.supabase.co');
  publicHeaders(key);
  async function privateInput(value, name, pattern) {
    assert(value);
    const file = resolve(value);
    await samePath(file);
    assert.equal(dirname(dirname(file)), evidence);
    assert.equal(basename(file), name);
    assert.match(basename(dirname(file)), pattern);
    return file;
  }
  const options = {mode, approval};
  let uiPath, folder;
  if (mode !== 'export') {
    uiPath = await privateInput(values.ui, 'report.json', /^hyundai-ioniq5-ui-[a-z0-9]+$/i);
    options.ui = await json(uiPath);
    options.reviewed = await json(await privateInput(values.reviewed, 'reviewed-scope.json', /^hyundai-ioniq5-local-test-[a-z0-9]+$/i));
    assert(values.fresh);
  } else assert(!(values.reviewed || values.ui || values.fresh), 'Recover from the committed journal only');
  if (mode !== 'check') {
    assert(values.output);
    folder = resolve(values.output);
    assert.equal(dirname(folder), evidence);
    assert.match(basename(folder), /^hyundai-ioniq5-release-[a-z0-9-]+$/);
  }
  const journal = name => join(folder, name + '.json');
  const readJournalFile = async name => { const path = journal(name); await samePath(path); return json(path); };
  let snapshot;
  const result = await runIoniq5Release(options, {
    now: () => new Date(),
    async assertMain(commit) {
      stage = 'main_revision';
      assertIoniq5MainRevision(commit, {local:mode !== 'check', exportRecovery:mode === 'export'});
      if (mode === 'commit') assert.equal(options.ui.baseline.exact_main_code, true, 'Require browser review of registered main assets');
    },
    catalog: () => mode === 'check'
      ? JSON.parse(execFileSync('git', ['show', options.ui.baseline.commit + ':public/data/public_ev_variants.json'],
        {cwd:sourceRoot, encoding:'utf8', maxBuffer:5000000}))
      : json(catalog),
    async publicRows({includeIds = false} = {}) {
      stage = 'anonymous_catalog';
      return fetchCatalog({url,key,includeIds,onSchema: missing => assert.deepEqual(missing, [], 'Missing public view columns')});
    },
    verifyMedia: async (plan, ui) => {
      stage = 'media_scope';
      return verifyIoniq5RegisteredMedia(root, plan, ui);
    },
    async freshSource() {
      stage = 'source_replay';
      const capture = await readIoniq5Capture(values.fresh);
      if (mode === 'commit') {
        const timestamps = intake => [intake.market.source, ...intake.sources].map(source => Date.parse(source.fetched_at));
        assert(Math.min(...timestamps(capture.intake)) > Math.max(...timestamps(options.reviewed.plan.intake)),
          'Commit capture must have been fetched after the browser-reviewed source capture');
      }
      return capture;
    },
    async openSnapshot() {
      stage = 'open_readonly_snapshot';
      snapshot = await openCatalogSnapshot(connection);
      return snapshot.client;
    },
    async prepare(client, {intake, images, reviewHash}) {
      stage = 'readback';
      useCalendarDateText(client);
      return ioniq5ReleaseReceipt(await prepareIoniq5Readback(client,intake,images.base), reviewHash);
    },
    photoMigration: client => {stage = 'migration_guard'; return hasVariantPhotoMigration(client);},
    closeSnapshot: () => snapshot.close(),
    async beginJournal(attempt) {
      stage = 'attempt_journal';
      await mkdir(folder);
      await samePath(folder);
      await saveNew(journal('attempt'), attempt);
    },
    async commit(client, fresh, reviewed, ui, authority) {
      stage = 'ioniq5_transaction';
      await client.query('ROLLBACK');
      return applyIoniq5Release(client,fresh,reviewed,ui,authority);
    },
    saveCommit: receipt => {stage = 'commit_receipt'; return saveNew(journal('committed-receipt'),receipt);},
    async readJournal() {
      stage = 'export_journal';
      await samePath(folder);
      return {attempt:await readJournalFile('attempt'), committed:await readJournalFile('committed-receipt')};
    },
    saveCatalog: async value => {stage = 'save_catalog'; await samePath(catalog); return atomicJson(catalog,value);},
  });
  console.log(JSON.stringify(result));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) main().catch(error => {
  console.error(JSON.stringify({status:'held_or_incomplete', stage,
    code: /^[A-Z0-9_]{1,32}$/.test(error.code ?? '') ? error.code : null,
    reason: error.code === 'ERR_ASSERTION' ? error.message.split('\n')[0] : 'Ioniq 5 release step failed'}));
  process.exitCode = 1;
});
