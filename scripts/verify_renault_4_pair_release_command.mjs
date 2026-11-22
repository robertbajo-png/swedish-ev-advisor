import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import test from 'node:test';
import { runRenault4PairRelease } from './publish_approved_renault_4_pair.mjs';
import { verifyRenault4PairMedia } from './verify_renault_4_pair_release.mjs';
import { publicationHash } from './new_model_publication.mjs';
import { catalogHash, normalizeCatalog, SOURCE, variantKey } from './sync_public_catalog.mjs';

const [receiptPath,uiPath,readbackPath]=process.argv.slice(2);
assert(receiptPath&&uiPath&&readbackPath);
const json=async path=>JSON.parse(await readFile(path,'utf8'));
const {reviewed,reviewed_scope_sha256:approval}=await json(receiptPath);
const ui=await json(uiPath),readback=await json(readbackPath);
const media=join(dirname(dirname(resolve(uiPath))),'source');
assert.match(reviewed.commit,/^[a-f0-9]{40}$/);
const {records:baseline}=JSON.parse(execFileSync('git',['show',reviewed.commit+':public/data/public_ev_variants.json'],
  {encoding:'utf8',maxBuffer:5000000}));
assert.equal(catalogHash(baseline),reviewed.baseline_hash);
const plan=structuredClone(reviewed.plan);
const shift=901000;
for(const source of [...plan.intake.sources,plan.intake.market.source])
  source.fetched_at=new Date(Date.parse(source.fetched_at)+shift).toISOString();
const now=new Date(Math.max(...plan.intake.sources.map(source=>Date.parse(source.fetched_at)),Date.parse(plan.intake.market.source.fetched_at)));
const fresh={plan,plan_hash:publicationHash(plan)};
const additions=normalizeCatalog(readback.added_variants.map(row=>({...row,
  price_verified_at:new Date(Date.parse(row.price_verified_at)+shift).toISOString()})));
const request={mode:'commit',approval,reviewed,ui};
const recovery={mode:'export',approval};

function fixture() {
  const state={local:baseline,remote:baseline,opens:0,closes:0,commits:0,exports:0};
  const client={};
  const io={
    now:()=>now,
    assertMain:revision=>assert.equal(revision,reviewed.commit),
    catalog:()=>({records:state.local}),
    publicRows:()=>state.remote,
    verifyMedia:(image,report)=>verifyRenault4PairMedia(media,image,report),
    freshSource:()=>plan.intake,
    openSnapshot:()=>{state.opens++;return client;},
    closeSnapshot:db=>{assert.equal(db,client);state.closes++;},
    prepare:(db,intake)=>{assert.equal(db,client);assert.equal(intake,plan.intake);return fresh;},
    beginJournal:attempt=>{assert(!state.attempt,'Duplicate journal');state.attempt=attempt;},
    commit(db,candidate,original,tested,hash){
      assert.equal(db,client);
      assert.equal(candidate,fresh);
      assert.equal(original,reviewed);
      assert.equal(tested,ui);
      assert.equal(hash,approval);
      assert.equal(state.attempt.plan,plan);
      state.commits++;
      state.remote=[...baseline,...additions];
      return {committed:true,anonymous_before_commit:true,variants_inserted:2,model_id:plan.expected_model.id,
        canonical_variant_ids:plan.targets.map(({id})=>id),publication_batch_id:fresh.plan_hash,paid_calls:0};
    },
    saveCommit:receipt=>{state.committed=receipt;},
    readJournal:async()=>{
      assert(state.attempt&&state.committed,'Require both the attempt and committed receipt');
      // Journal recovery must work after parsing JSON in a separate process.
      return JSON.parse(JSON.stringify({attempt:state.attempt,committed:state.committed}));
    },
    saveCatalog:payload=>{
      assert.equal(payload.source,SOURCE);
      assert.equal(payload.catalog_sha256,catalogHash(payload.records));
      state.local=payload.records;
      state.exports++;
    },
  };
  return {state,io};
}

test('read-only preparation checks the reviewed source and real media without journaling or writing',async()=>{
  const {state,io}=fixture();
  const result=await runRenault4PairRelease({mode:'check',reviewed,ui},io);
  assert.equal(result.status,'ready_for_owner_review');
  assert.equal(result.reviewed_scope_sha256,approval);
  assert.deepEqual([state.opens,state.closes,state.attempt,state.commits,state.exports],[1,1,undefined,0,0]);
});

test('wrong approval, stale main and live catalog drift fail before database connection',async()=>{
  const {state,io}=fixture();
  await assert.rejects(runRenault4PairRelease({...request,approval:'0'.repeat(64)},io),/Invalid Renault 4 pair approval/);
  const main=io.assertMain;
  io.assertMain=()=>{throw Error('Different main');};
  await assert.rejects(runRenault4PairRelease(request,io),/Different main/);
  io.assertMain=main;
  state.remote=baseline.slice(1);
  await assert.rejects(runRenault4PairRelease(request,io),/Live canonical catalog changed/);
  assert.deepEqual([state.opens,state.commits,state.attempt],[0,0,undefined]);
});

test('expired and reused source captures cannot create an attempt',async()=>{
  const {state,io}=fixture();
  io.now=()=>new Date(now.getTime()+901000);
  await assert.rejects(runRenault4PairRelease(request,io),/Fresh source capture required/);
  io.now=()=>now;
  io.prepare=()=>({plan:reviewed.plan,plan_hash:reviewed.plan_hash});
  await assert.rejects(runRenault4PairRelease(request,io),/Capture both Renault 4 grades again/);
  assert.deepEqual([state.opens,state.closes,state.commits,state.attempt],[2,2,0,undefined]);
});

test('commit leaves the catalog untouched; repeatable export preserves every prior JSON row',async()=>{
  const {state,io}=fixture();
  const committed=await runRenault4PairRelease(request,io);
  assert.equal(committed.status,'committed_export_pending');
  assert.equal(state.exports,0);
  const exported=await runRenault4PairRelease(recovery,io);
  assert.equal(exported.status,'export_verified');
  assert.deepEqual([exported.added,exported.preserved,state.local.length],[2,baseline.length,baseline.length+2]);
  const byKey=new Map(state.local.map(row=>[variantKey(row),row]));
  assert.deepEqual(baseline.map(row=>byKey.get(variantKey(row))),baseline);
  await runRenault4PairRelease(recovery,io);
  assert.deepEqual([state.opens,state.closes,state.commits,state.exports],[1,1,1,1]);
});

test('receipt mismatch or incomplete journal does not query Supabase or modify the local catalog',async()=>{
  const {state,io}=fixture();
  await assert.rejects(runRenault4PairRelease(recovery,io),/Require both the attempt and committed receipt/);
  await runRenault4PairRelease(request,io);
  state.committed.attempt_sha256='0'.repeat(64);
  io.publicRows=()=>{throw Error('Unexpected catalog request');};
  await assert.rejects(runRenault4PairRelease(recovery,io),/does not match the attempt journal/);
  assert.deepEqual([state.opens,state.commits,state.exports],[1,1,0]);
});

test('wrong variant values, changed prior rows or an extra variant hold export without SQL',async()=>{
  const {state,io}=fixture();
  await runRenault4PairRelease(request,io);
  state.remote=[...baseline,additions[0],{...additions[1],price_sek:400000}];
  await assert.rejects(runRenault4PairRelease(recovery,io));
  state.remote=[{...baseline[0],source_quote:'Changed old evidence'},...baseline.slice(1),...additions];
  await assert.rejects(runRenault4PairRelease(recovery,io),/Existing catalog rows changed/);
  state.remote=[...baseline,...additions,{...additions[0],variant_name:'Other Renault grade'}];
  await assert.rejects(runRenault4PairRelease(recovery,io),/Only the approved Renault 4 pair/);
  assert.deepEqual([state.opens,state.commits,state.exports],[1,1,0]);
});
