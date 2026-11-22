import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { loadEnv } from 'vite';
import { readPairCapture } from './renault_4_pair_publication.mjs';
import { readEvolutionImage } from './renault_4_evolution_publication.mjs';
import { readRenault4Scope } from './prepare_renault_4_evolution_readback.mjs';
import { verifyRenault4PairMedia } from './verify_renault_4_pair_release.mjs';
import { assertRenault4PairPublishedRows, proveRenault4PairRelease, renault4PairApproval } from './renault_4_pair_release_scope.mjs';
import { applyRenault4PairRelease, publicationHash } from './new_model_publication.mjs';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';
import { atomicJson, catalogHash, compareCatalogs, fetchCatalog, publicHeaders, SOURCE, variantKey } from './sync_public_catalog.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';

const project = 'eutcryxbitudllcnpnex';
const sha = /^[a-f0-9]{64}$/;
const json = async path=>JSON.parse(await readFile(path,'utf8'));
const unlinked = async path=>assert.equal(await realpath(path),path,'Require an unlinked release path');
const saveNew = (path,value)=>writeFile(path,JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const compareHash = rows=>catalogHash(catalogWithComparableTimes(rows));
const targetKeys = plan=>plan.targets.map(({draft})=>variantKey({...plan.intake.model,variant_name:draft.variant_name})).sort();
let stage = 'arguments';

function assertDatabaseCommit(result,plan) {
  assert.equal(result.committed,true);
  assert.equal(result.anonymous_before_commit,true);
  assert.equal(result.variants_inserted,2);
  assert.equal(result.model_id,plan.expected_model.id);
  assert.deepEqual(result.canonical_variant_ids,plan.targets.map(({id})=>id));
  assert.equal(result.publication_batch_id,publicationHash(plan));
  assert.equal(result.paid_calls,0);
}

export async function runRenault4PairRelease({mode,approval,reviewed,ui},io) {
  assert(['check','commit','export'].includes(mode));
  if(mode!=='check') assert.match(approval??'',sha,'Require the explicitly approved Renault 4 pair hash');
  if(mode==='export') {
    const {attempt,committed}=await io.readJournal();
    assert.equal(attempt.approval,approval);
    assert.equal(attempt.approval,renault4PairApproval(attempt.reviewed,attempt.ui));
    assert.equal(committed.attempt_sha256,publicationHash(attempt),'Committed receipt does not match the attempt journal');
    const {plan,baseline}=attempt;
    assert.equal(catalogHash(baseline),attempt.reviewed.baseline_hash);
    assertDatabaseCommit(committed.result,plan);
    await io.assertMain(attempt.reviewed.commit);
    await io.verifyMedia(plan.image,attempt.ui);
    const rows=await io.publicRows();
    const keys=targetKeys(plan);
    const diff=compareCatalogs(catalogWithComparableTimes(baseline),catalogWithComparableTimes(rows));
    assert.deepEqual(diff.local_only,[],'Existing catalog rows disappeared');
    assert.deepEqual(diff.changed,[],'Existing catalog rows changed');
    assert.deepEqual(diff.remote_only.slice().sort(),keys,'Only the approved Renault 4 pair may be exported');
    const additions=rows.filter(row=>keys.includes(variantKey(row)));
    assertRenault4PairPublishedRows(additions,plan,{requireIds:false});
    const fromDatabase=compareHash(rows);
    const records=[...baseline,...additions].sort((a,b)=>variantKey(a)<variantKey(b)?-1:variantKey(a)>variantKey(b)?1:0);
    const catalog_sha256=catalogHash(records);
    assert.equal(compareHash(records),fromDatabase);
    assert.equal(compareHash(await io.publicRows()),fromDatabase,'Canonical catalog changed during export');
    const current=catalogHash((await io.catalog()).records);
    assert([attempt.reviewed.baseline_hash,catalog_sha256].includes(current),'Local catalog changed since the commit');
    if(current!==catalog_sha256) await io.saveCatalog({generated_at:io.now().toISOString(),source:SOURCE,
      schema_version:1,missing_view_columns:[],catalog_sha256,records});
    return {status:'export_verified',added:2,preserved:baseline.length,catalog_sha256,paid_calls:0};
  }

  const required=renault4PairApproval(reviewed,ui);
  if(mode==='commit') assert.equal(approval,required,'Invalid Renault 4 pair approval');
  await io.assertMain(reviewed.commit);
  const {records:baseline}=await io.catalog();
  assert.equal(catalogHash(baseline),reviewed.baseline_hash,'Reviewed baseline changed');
  assert.equal(baseline.length,reviewed.baseline_count);
  const confirmPublic=async()=>assert.equal(compareHash(await io.publicRows()),reviewed.database_baseline_hash,'Live canonical catalog changed');
  await confirmPublic();
  await io.verifyMedia(reviewed.plan.image,ui);
  const intake=await io.freshSource();
  const client=await io.openSnapshot();
  try {
    const fresh=await io.prepare(client,intake);
    proveRenault4PairRelease(reviewed,fresh,ui,required,io.now());
    if(mode==='check') return {status:'ready_for_owner_review',variants:2,preserved:baseline.length,
      reviewed_scope_sha256:required,production_writes:0,paid_calls:0};
    await confirmPublic();
    assert.equal(catalogHash((await io.catalog()).records),reviewed.baseline_hash);
    const attempt={approval,reviewed,ui,plan:fresh.plan,baseline};
    await io.beginJournal(attempt);
    const result=await io.commit(client,fresh,reviewed,ui,approval);
    assertDatabaseCommit(result,fresh.plan);
    await io.saveCommit({attempt_sha256:publicationHash(attempt),result});
    return {status:'committed_export_pending',added:2,preserved:baseline.length,paid_calls:0};
  } finally { await io.closeSnapshot(client); }
}

async function main() {
  const {values}=parseArgs({options:{reviewed:{type:'string'},ui:{type:'string'},fresh:{type:'string'},
    output:{type:'string'},'commit-plan':{type:'string'},'resume-export':{type:'string'}}});
  assert(!(values['commit-plan']&&values['resume-export']),'Choose the database commit or export recovery');
  const mode=values['commit-plan']?'commit':values['resume-export']?'export':'check';
  const approval=values['commit-plan']??values['resume-export'];
  if(approval!==undefined) assert.match(approval,sha);
  const root=await realpath('.');
  const evidence=join(root,'data/local/release-data');
  await unlinked(evidence);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(root));
  const catalog=join(root,'public/data/public_ev_variants.json');
  await unlinked(catalog);
  let options={mode,approval},mediaRoot=root,folder;
  if(mode!=='export') {
    assert(values.reviewed&&values.ui&&values.fresh,'Supply the reviewed receipt, UI report and new source capture');
    const review=resolve(values.reviewed),uiPath=resolve(values.ui);
    await unlinked(review);
    await unlinked(uiPath);
    assert.equal(dirname(dirname(review)),evidence);
    assert.match(basename(dirname(review)),/^renault-4-pair-release-review-[a-z0-9]+$/i);
    assert.equal(basename(review),'release-review.json');
    assert.equal(dirname(dirname(dirname(uiPath))),evidence);
    assert.match(basename(dirname(dirname(uiPath))),/^renault-4-pair-ui-[a-z0-9]+$/i);
    assert.match(basename(dirname(uiPath)),/^browser-[a-z0-9]+$/i);
    assert.equal(basename(uiPath),'ui-report.json');
    const receipt=await json(review),ui=await json(uiPath);
    assert.equal(receipt.status,'fresh_readonly_and_isolated_transaction_passed');
    assert.equal(receipt.publication_approved,false);
    assert.equal(receipt.production_writes,0);
    assert.equal(receipt.transaction.scoped_late_rollback,true);
    assert.equal(receipt.transaction.preserved,receipt.reviewed.baseline_count);
    assert.equal(receipt.transaction.private_rows,receipt.reviewed.baseline_count+2);
    assert.equal(receipt.reviewed_scope_sha256,renault4PairApproval(receipt.reviewed,ui));
    options={...options,reviewed:receipt.reviewed,ui};
    if(mode==='check') mediaRoot=join(dirname(dirname(uiPath)),'source');
  } else assert(!(values.reviewed||values.ui||values.fresh),'Recover using the committed journal only');
  if(mode!=='check'){
    assert(values.output,'Require a private Renault 4 attempt directory');
    folder=resolve(values.output);
    assert.equal(dirname(folder),evidence);
    assert.match(basename(folder),/^renault-4-pair-apply-[a-z0-9-]+$/);
  } else assert(!values.output,'The read-only check does not create an attempt');
  await unlinked(mediaRoot);
  const env={...loadEnv('production',root,'SUPABASE_'),...loadEnv('production',root,'VITE_SUPABASE_')};
  const url=env.SUPABASE_URL||env.VITE_SUPABASE_URL,key=env.SUPABASE_ANON_KEY||env.VITE_SUPABASE_ANON_KEY;
  assert.equal(new URL(url).origin,'https://'+project+'.supabase.co');
  publicHeaders(key);
  const journal=name=>join(folder,name+'.json');
  const readJournalFile=async name=>{const path=journal(name);await unlinked(path);return json(path);};
  let connector;
  const result=await runRenault4PairRelease(options,{
    now:()=>new Date(),
    async assertMain(commit) {
      stage='main_revision';
      assert.match(commit,/^[a-f0-9]{40}$/);
      assert.equal(execFileSync('git',['ls-remote','origin','refs/heads/main'],{encoding:'utf8',timeout:20000}).trim(),
        commit+'\trefs/heads/main','Main changed since Renault 4 browser review');
      if(mode!=='check') {
        const top=execFileSync('git',['rev-parse','--show-toplevel'],{encoding:'utf8'}).trim();
        assert.equal(await realpath(top),root,'Use a release checkout, not its nested preview');
        assert.equal(execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),commit,'Use the exact-main release candidate');
      }
    },
    catalog:()=>mode==='check'?JSON.parse(execFileSync('git',['show',options.reviewed.commit+':public/data/public_ev_variants.json'],
      {encoding:'utf8',timeout:15000,maxBuffer:5000000})):json(catalog),
    publicRows() {
      stage='anonymous_catalog';
      return fetchCatalog({url,key,onSchema:missing=>assert.deepEqual(missing,[],'Missing public view columns')});
    },
    verifyMedia:(image,report)=>{stage='registered_renault_media';return verifyRenault4PairMedia(mediaRoot,image,report);},
    freshSource:()=>{stage='source_replay';return readPairCapture(values.fresh).intake;},
    async openSnapshot(){
      stage='open_readonly_snapshot';
      const path=join(root,'data/local/db-tools/source-client.mjs');
      await unlinked(path);
      connector=await import(pathToFileURL(path).href);
      assert.equal(connector.PROJECT_REF,project);
      return connector.openSourceSnapshot();
    },
    async prepare(client,intake){
      stage='readback';
      useCalendarDateText(client);
      const {plan}=await readRenault4Scope(client,intake,readEvolutionImage(),new Date());
      return {plan,plan_hash:publicationHash(plan)};
    },
    closeSnapshot:client=>connector.closeSourceSnapshot(client),
    async beginJournal(attempt){
      stage='attempt_journal';
      await mkdir(folder);
      await unlinked(folder);
      await saveNew(journal('attempt'),attempt);
    },
    async commit(client,fresh,reviewed,ui,hash){
      stage='renault_4_transaction';
      await client.query('ROLLBACK');
      return applyRenault4PairRelease(client,fresh,reviewed,ui,hash);
    },
    saveCommit:receipt=>{stage='commit_receipt';return saveNew(journal('committed-receipt'),receipt);},
    async readJournal(){
      stage='export_journal';
      await unlinked(folder);
      return {attempt:await readJournalFile('attempt'),committed:await readJournalFile('committed-receipt')};
    },
    saveCatalog:async value=>{stage='save_catalog';await unlinked(catalog);return atomicJson(catalog,value);},
  });
  console.log(JSON.stringify(result));
}

if(process.argv[1]&&pathToFileURL(process.argv[1]).href===import.meta.url) main().catch(error=>{
  console.error(JSON.stringify({status:'held_or_incomplete',stage,
    reason:error.code==='ERR_ASSERTION'?error.message.split('\n')[0]:'Renault 4 release step failed'}));
  process.exitCode=1;
});
