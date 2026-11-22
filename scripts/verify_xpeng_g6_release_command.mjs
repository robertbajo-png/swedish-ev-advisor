import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import test from 'node:test';
import { releaseMode, runXpG6Release, verifyRegisteredPhoto } from './publish_approved_xpeng_g6.mjs';
import { publicationHash } from './new_model_publication.mjs';
import { catalogHash, SOURCE } from './sync_public_catalog.mjs';

const json = async path => JSON.parse(await readFile(path, 'utf8'));
const [reviewedFile, uiFile, freshFile, projection] = process.argv.slice(2);
assert(reviewedFile && uiFile && freshFile && projection, 'Supply private historical rehearsal receipts');
const reviewed = await json(reviewedFile), ui = await json(uiFile), fresh = await json(freshFile);
const { records: baseline } = await json('public/data/public_ev_variants.json');
const added = await json(projection);
assert(Array.isArray(added));
assert.equal(added.length, 3);
const approved = reviewed.plan_hash;
const clock = new Date(fresh.plan.intake.market.source.fetched_at);
const request = { mode: 'commit', hash: approved, reviewed, ui };

function setup() {
  const state = { events: [], canonical: baseline, local: baseline, closes: 0, commits: 0, exports: 0 };
  const snapshot = {};
  const record = (name, value) => { state.events.push(name); return value; };
  const io = {
    now: () => clock,
    checkMain: commit => assert.equal(commit, ui.main_review.commit),
    existingCatalog: () => ({ records: state.local }),
    publicRows: () => record('public', { rows: state.canonical, missing: [] }),
    verifyPhoto: image => verifyRegisteredPhoto(resolve('.'), image),
    freshSource: () => record('source', {}),
    openSnapshot: () => record('snapshot', snapshot),
    prepare: client => { assert.equal(client, snapshot); return fresh; },
    closeSnapshot: client => { assert.equal(client, snapshot); state.closes++; },
    beginJournal: attempt => { assert(!state.attempt, 'Release journal already exists'); state.attempt = attempt; },
    commit(client, freshReceipt, reviewedReceipt, uiReceipt, hash, expectedBaseline) {
      assert.equal(client, snapshot);
      assert.equal(freshReceipt, fresh);
      assert.equal(reviewedReceipt, reviewed);
      assert.equal(uiReceipt, ui);
      assert.equal(hash, approved);
      assert.equal(expectedBaseline, catalogHash(baseline));
      assert.equal(state.attempt.fresh_plan_hash, publicationHash(fresh.plan));
      assert.equal(state.attempt.baseline_hash, expectedBaseline);
      state.commits++;
      state.canonical = [...baseline, ...added];
      return { committed: true, model_id: fresh.plan.expected_model.id, anonymous_before_commit: true,
        variants_inserted: 3, canonical_variant_ids: fresh.plan.targets.map(t => t.id),
        publication_batch_id: publicationHash(fresh.plan), paid_calls: 0 };
    },
    writeCommit: receipt => { state.committed = receipt; },
    readJournal: () => ({ attempt: state.attempt, committed: state.committed }),
    saveCatalog: payload => {
      assert.equal(payload.source, SOURCE);
      assert.equal(payload.catalog_sha256, catalogHash(payload.records));
      state.exports++;
      state.local = payload.records;
    },
  };
  return { state, io };
}

test('require an exact reviewed hash and mutually exclusive action flags', () => {
  assert.deepEqual(releaseMode({}), { mode: 'check', hash: undefined });
  assert.throws(() => releaseMode({ 'commit-plan': '', 'resume-export': '' }), /exact approved/);
  assert.throws(() => releaseMode({ 'commit-plan': approved, 'resume-export': approved }), /Choose commit/);
  assert.deepEqual(releaseMode({ 'resume-export': approved }), { mode: 'export', hash: approved });
});

test('read-only mode checks real registered photo bytes and does not create a journal', async () => {
  const { state, io } = setup();
  const result = await runXpG6Release({ ...request, mode: 'check', hash: undefined }, io);
  assert.equal(result.status, 'ready_for_owner_review');
  assert.equal(result.production_writes, 0);
  assert.equal(result.baseline_count, 84);
  assert.equal(state.attempt, undefined);
  assert.equal(state.commits, 0);
  assert.equal(state.exports, 0);
  assert.equal(state.closes, 1);
});

test('wrong approval or duplicated browser run stops before connecting', async () => {
  for (const wrong of [{...request, hash: '0'.repeat(64)}, {...request, ui: {...ui, runs: [...ui.runs.slice(1), ui.runs[1]]}}]) {
    const { state, io } = setup();
    await assert.rejects(runXpG6Release(wrong, io), /Wrong approved|browser matrix/);
    assert.deepEqual(state.events, []);
  }
});

test('expired receipts close the snapshot without commit or journal', async () => {
  const { state, io } = setup();
  io.now = () => new Date(fresh.evidence_expires_at);
  await assert.rejects(runXpG6Release(request, io), /window expired/);
  assert.equal(state.closes, 1);
  assert.equal(state.commits, 0);
  assert.equal(state.attempt, undefined);
});

test('drift after preflight stops before journal and commit', async () => {
  const { state, io } = setup();
  io.prepare = () => { state.canonical = baseline.slice(1); return fresh; };
  await assert.rejects(runXpG6Release(request, io), /Canonical catalog changed/);
  assert.equal(state.closes, 1);
  assert.equal(state.commits, 0);
  assert.equal(state.attempt, undefined);
});

test('commit journal prevents rerunning a partially completed attempt', async () => {
  const { state, io } = setup();
  state.attempt = { approved_hash: approved };
  await assert.rejects(runXpG6Release(request, io), /already exists/);
  assert.equal(state.commits, 0);
  assert.equal(state.exports, 0);
});

test('approved mock commit exports all 84 original rows and exactly three G6 variants', async () => {
  const { state, io } = setup();
  const result = await runXpG6Release(request, io);
  assert.equal(result.database_transaction, 'committed');
  assert.deepEqual([result.preserved, result.added.length, result.count], [84, 3, 87]);
  assert.equal(state.commits, 1);
  assert.equal(state.exports, 1);
  assert.equal(state.closes, 1);
});

test('post-commit drift preserves the old file and the recovery receipt', async () => {
  const { state, io } = setup();
  const commit = io.commit;
  io.commit = (...args) => {
    const value = commit(...args);
    state.canonical = state.canonical.slice(1);
    return value;
  };
  await assert.rejects(runXpG6Release(request, io), /Existing public rows disappeared/);
  assert.equal(state.committed.result.committed, true);
  assert.equal(state.exports, 0);
  assert.equal(catalogHash(state.local), catalogHash(baseline));
  state.canonical = [...baseline, ...added];
  const recovered = await runXpG6Release({ mode: 'export', hash: approved }, io);
  assert.deepEqual([recovered.preserved, recovered.count], [84, 87]);
  await runXpG6Release({ mode: 'export', hash: approved }, io);
  assert.equal(state.commits, 1);
  assert.equal(state.exports, 1);
  assert.equal(state.closes, 1);
});

test('recovery refuses a changed journal or altered checked-in catalog', async () => {
  const { state, io } = setup();
  await runXpG6Release(request, io);
  state.attempt = { ...state.attempt, fresh_plan_hash: '0'.repeat(64) };
  await assert.rejects(runXpG6Release({ mode: 'export', hash: approved }, io), /Journal plan mismatch/);
  state.attempt = { ...state.attempt, fresh_plan_hash: publicationHash(fresh.plan) };
  state.local = baseline.slice(1);
  await assert.rejects(runXpG6Release({ mode: 'export', hash: approved }, io), /Local catalog changed/);
  assert.equal(state.commits, 1);
  assert.equal(state.exports, 1);
});
