import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import test from 'node:test';
import { ioniq5ReleaseReceipt } from './hyundai_ioniq5_release_scope.mjs';
import { runIoniq5Release, verifyIoniq5RegisteredMedia } from './publish_approved_hyundai_ioniq5.mjs';
import { publicationHash } from './new_model_publication.mjs';
import { catalogHash, SOURCE } from './sync_public_catalog.mjs';

const [scopeFile, uiFile, rowsFile] = process.argv.slice(2);
assert(scopeFile && uiFile && rowsFile);
const json = async file => JSON.parse(await readFile(file, 'utf8'));
const reviewed = await json(scopeFile), ui = await json(uiFile), added = await json(rowsFile);
const media = resolve('.');
assert.match(ui.baseline.commit, /^[a-f0-9]{40}$/);
const {records: baseline} = JSON.parse(execFileSync('git', ['show', ui.baseline.commit + ':public/data/public_ev_variants.json'],
  {encoding:'utf8', maxBuffer:5000000}));
assert.equal(ui.plan_hash, reviewed.plan_hash);
assert.equal(catalogHash(baseline), ui.baseline.baseline_sha256);
assert.equal(publicationHash(added), ui.transaction_rows_sha256);
const now = new Date(reviewed.plan.intake.market.source.fetched_at);
const fresh = ioniq5ReleaseReceipt(reviewed.plan, publicationHash({test_only: true, original: reviewed.review_hash}));
const request = {mode: 'commit', approval: reviewed.plan_hash, reviewed, ui};

function fixture() {
  const state = { local: baseline, remote: baseline, migrated: true, opens: 0, closes: 0, commits: 0, exports: 0 };
  const client = {};
  const io = {
    now: () => now,
    assertMain: revision => assert.equal(revision, ui.baseline.commit),
    publicRows: () => state.remote,
    catalog: () => ({records: state.local}),
    verifyMedia: (plan, report) => verifyIoniq5RegisteredMedia(media, plan, report),
    freshSource: () => ({}),
    openSnapshot: () => { state.opens++; return client; },
    closeSnapshot: db => { assert.equal(db,client); state.closes++; },
    prepare: db => { assert.equal(db,client); return fresh; },
    photoMigration: db => { assert.equal(db,client); return state.migrated; },
    beginJournal: attempt => { assert(!state.attempt, 'Duplicate journal'); state.attempt = attempt; },
    commit(db, candidate, original, tested, approval) {
      assert.equal(db, client);
      assert.equal(candidate,fresh);
      assert.equal(original,reviewed);
      assert.equal(tested,ui);
      assert.equal(approval,reviewed.plan_hash);
      assert.equal(state.attempt.fresh_plan_hash, fresh.plan_hash);
      state.commits++;
      state.remote = [...baseline, ...added];
      return {committed:true, anonymous_before_commit:true, variants_inserted:7, model_id:fresh.plan.expected_model.id,
        canonical_variant_ids:fresh.plan.targets.map(target => target.id), publication_batch_id:fresh.plan_hash, paid_calls:0};
    },
    saveCommit: committed => {state.committed = committed;},
    readJournal: () => ({attempt:state.attempt, committed:state.committed}),
    saveCatalog: payload => {
      assert.equal(payload.source,SOURCE);
      assert.equal(payload.catalog_sha256,catalogHash(payload.records));
      state.local = payload.records;
      state.exports++;
    },
  };
  return {state,io};
}

test('read-only preflight verifies actual media and reports absent migration', async () => {
  const {state,io} = fixture();
  state.migrated = false;
  const result = await runIoniq5Release({...request, mode:'check', approval:undefined},io);
  assert.equal(result.status,'held_for_migration_025');
  assert.equal(state.opens,1);
  assert.equal(state.closes,1);
  assert.equal(state.attempt,undefined);
  assert.equal(state.commits,0);
});

test('wrong approval and changed catalog stop before an SQL connection', async () => {
  const {state,io} = fixture();
  await assert.rejects(runIoniq5Release({...request,approval:'0'.repeat(64)},io),/Invalid Ioniq 5 approval/);
  state.remote = baseline.slice(1);
  await assert.rejects(runIoniq5Release(request,io),/Canonical catalog changed/);
  assert.equal(state.opens,0);
});

test('commit never installs a missing migration or creates a new journal', async () => {
  const {state,io} = fixture();
  state.migrated = false;
  await assert.rejects(runIoniq5Release(request,io),/separately approved migration 025/);
  assert.equal(state.attempt,undefined);
  assert.equal(state.commits,0);
  assert.equal(state.closes,1);
});

test('expired sources and a repeated browser case each stop the write', async () => {
  const {state,io} = fixture();
  io.now = () => new Date(fresh.evidence_expires_at);
  await assert.rejects(runIoniq5Release(request,io),/source window expired/);
  io.now = () => now;
  await assert.rejects(runIoniq5Release({...request,ui:{...ui,runs:[...ui.runs.slice(1),ui.runs[1]]}},io),/browser matrix differs/);
  assert.equal(state.commits,0);
  assert.equal(state.attempt,undefined);
});

test('simulated release exports precisely seven variants and preserves all existing rows', async () => {
  const {state,io} = fixture();
  const result = await runIoniq5Release(request,io);
  assert.deepEqual([result.status,result.added,result.preserved,state.local.length],
    ['export_verified',7,baseline.length,baseline.length+7]);
  assert.deepEqual([state.commits,state.exports,state.closes],[1,1,1]);
});

test('incorrect edition after commit leaves export untouched and recoverable without SQL', async () => {
  const {state,io} = fixture();
  const original = io.commit;
  const nLine = added.find(row => row.variant_name.endsWith(' N Line'));
  const base = added.find(row => !row.variant_name.endsWith(' N Line'));
  io.commit = (...args) => {
    const result = original(...args);
    state.remote = [...baseline,...added.map(row => row === nLine ? {...row,image_url:base.image_url} : row)];
    return result;
  };
  await assert.rejects(runIoniq5Release(request,io),/Unexpected public Ioniq 5 field: image_url/);
  assert.equal(state.exports,0);
  assert.equal(state.committed.result.committed,true);
  state.remote = [...baseline,...added];
  const recover = {mode:'export',approval:reviewed.plan_hash};
  await runIoniq5Release(recover,io);
  await runIoniq5Release(recover,io);
  assert.deepEqual([state.opens,state.commits,state.exports],[1,1,1]);
});
