import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { loadEnv } from 'vite';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';
import { applyXpG9Release, publicationHash } from './new_model_publication.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { atomicJson, catalogHash, fetchCatalog, normalizeCatalog, publicHeaders, SOURCE, variantKey } from './sync_public_catalog.mjs';
import { readG9Plan } from './verify_xpeng_g9_local.mjs';
import { readG9Capture, readG9Image } from './xpeng_g9_publication.mjs';
import { g9ApprovalHash, proveFreshG9Release, validateG9PostG6Delta } from './xpeng_g9_release_review.mjs';

const project = 'eutcryxbitudllcnpnex';
const sha = /^[a-f0-9]{64}$/;
const gitRef = /^[a-f0-9]{40}$/;
const compareHash = rows => catalogHash(catalogWithComparableTimes(rows));
const unlinked = async path => assert.equal(await realpath(path),path,'Linked release path');
const json = async path => {
  await unlinked(path);
  return JSON.parse(await readFile(path,'utf8'));
};
const saveNew = (path,value) => writeFile(path,JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const isG9 = ({brand,model}) => [brand.toLowerCase(),model.toLowerCase()].join('|')==='xpeng|g9';
let stage = 'arguments';

export async function verifyRegisteredG9Media(root,image,ui) {
  const data = file => json(join(root,'src',file+'.json'));
  assert.equal((await data('model-images'))[image.model_key],image.asset_url);
  const photo = (await data('image-presentation')).models[image.model_key];
  assert.deepEqual([photo.asset_url,photo.content_sha256,photo.status,photo.object_fit],
    [image.asset_url,image.content_sha256,'approved','contain']);
  const rights = (await data('image-rights')).assets.filter(row=>row.model_key===image.model_key);
  assert.deepEqual(rights,[{...image,changes:image.model_image_notice+' Endast storlek och format har anpassats.'}]);
  const publisher = (await data('press-image-publishers'))[image.publisher_id];
  assert.equal(publisher.approved_source_sha256,image.source_content_sha256);
  assert.equal(publisher.approved_asset_url,image.downloaded_from);
  assert.deepEqual(publisher.approved_image_paths,[new URL(image.source_url).pathname]);
  assert.deepEqual(publisher.model_keys,[image.model_key]);
  const responsive = (await data('image-variants'))[image.asset_url];
  assert.equal(responsive.source_sha256,image.content_sha256);
  assert.deepEqual(responsive.variants.map(row=>row.width),[480,800,1280]);
  const media = [{url:image.asset_url,sha256:image.content_sha256},
    ...responsive.variants.map(({url,sha256})=>({url,sha256}))];
  assert.deepEqual(media,ui.g9_media,'Registered G9 images differ from browser QA');
  for(const {url,sha256} of media) {
    assert.match(url,/^\/media\/(?:vehicles|responsive)\/xpeng-g9-press-[a-f0-9]{12}(?:-(?:480|800|1280)\.webp|\.jpg)$/);
    const path = join(root,'public',url.slice(1));
    await unlinked(path);
    assert.equal(createHash('sha256').update(await readFile(path)).digest('hex'),sha256,'G9 image bytes changed');
  }
}

function assertCommit(result,plan) {
  assert.deepEqual([result.committed,result.anonymous_before_commit,result.variants_inserted,result.paid_calls],[true,true,2,0]);
  assert.equal(result.model_id,plan.expected_model.id);
  assert.deepEqual(result.canonical_variant_ids,plan.targets.map(({id})=>id));
  assert.equal(result.publication_batch_id,publicationHash(plan));
}

export async function runXpG9Release({mode,approval,reviewed},io) {
  assert(['check','commit','export'].includes(mode));
  if(mode!=='check') assert.match(approval??'',sha,'Require the exact G9 scope hash');
  if(mode==='export') {
    const {attempt,committed} = await io.readJournal();
    const {baseline,plan,reviewed} = attempt;
    assert.equal(attempt.approval,approval);
    assert.equal(g9ApprovalHash(reviewed),approval);
    assert.equal(committed.attempt_sha256,publicationHash(attempt),'Commit receipt does not match the G9 journal');
    proveFreshG9Release(reviewed,{plan,plan_hash:publicationHash(plan)},approval,new Date(attempt.prepared_at));
    assertCommit(committed.result,plan);
    assert.equal(catalogHash(baseline),reviewed.baseline_sha256);
    assert.equal(compareHash(baseline),reviewed.database_baseline_sha256);
    await io.assertMain(reviewed.commit);
    await io.verifyMedia(plan.image,reviewed.ui);
    const rows = await io.publicRows();
    const delta = validateG9PostG6Delta(baseline,rows,plan);
    const additions = rows.filter(isG9);
    assert.deepEqual(additions.map(row=>row.id).sort(),plan.targets.map(row=>row.id).sort());
    const records = [...baseline,...normalizeCatalog(additions)].sort((a,b)=>variantKey(a)<variantKey(b)?-1:variantKey(a)>variantKey(b)?1:0);
    assert.equal(compareHash(records),delta.candidate_sha256);
    assert.equal(compareHash(await io.publicRows()),delta.candidate_sha256,'Live catalog changed during G9 export');
    const catalog_sha256 = catalogHash(records);
    const current = catalogHash((await io.catalog()).records);
    assert([reviewed.baseline_sha256,catalog_sha256].includes(current),'Local catalog changed since the G9 commit');
    if(current!==catalog_sha256) await io.saveCatalog({generated_at:io.now().toISOString(),source:SOURCE,
      schema_version:1,missing_view_columns:[],catalog_sha256,records});
    return {status:'export_verified',added:2,preserved:baseline.length,catalog_sha256,paid_calls:0};
  }

  const required = g9ApprovalHash(reviewed);
  if(mode==='commit') assert.equal(approval,required,'Invalid G9 scope hash');
  await io.assertMain(reviewed.commit);
  const {records:baseline} = await io.catalog();
  assert.equal(catalogHash(baseline),reviewed.baseline_sha256,'Reviewed G9 catalog baseline changed');
  assert.equal(compareHash(baseline),reviewed.database_baseline_sha256);
  assert.equal(baseline.length,reviewed.preserved);
  const confirmBaseline = async () => {
    assert.equal(catalogHash(await io.siteRows()),reviewed.baseline_sha256,'Website catalog changed since G9 review');
    assert.equal(compareHash(await io.publicRows()),reviewed.database_baseline_sha256,'Live canonical catalog changed since G9 review');
  };
  await confirmBaseline();
  await io.verifyMedia(reviewed.plan.image,reviewed.ui);
  const intake = await io.freshSource();
  const client = await io.openSnapshot();
  try {
    const fresh = await io.prepare(client,intake);
    proveFreshG9Release(reviewed,fresh,required,io.now());
    if(mode==='check') return {status:'ready_for_release_review',added:2,preserved:baseline.length,
      reviewed_scope_sha256:required,production_writes:0,paid_calls:0};
    await confirmBaseline();
    assert.equal(catalogHash((await io.catalog()).records),reviewed.baseline_sha256);
    const attempt = {approval,reviewed,plan:fresh.plan,baseline,prepared_at:io.now().toISOString()};
    await io.beginJournal(attempt);
    const result = await io.commit(client,fresh,reviewed,required);
    assertCommit(result,fresh.plan);
    await io.saveCommit({attempt_sha256:publicationHash(attempt),result});
    return {status:'committed_export_pending',added:2,preserved:baseline.length,paid_calls:0};
  } finally { await io.closeSnapshot(client); }
}

async function main() {
  const {values} = parseArgs({options:{reviewed:{type:'string'},fresh:{type:'string'},output:{type:'string'},
    'connection-root':{type:'string'},'commit-plan':{type:'string'},'resume-export':{type:'string'}}});
  assert(!(values['commit-plan']&&values['resume-export']),'Choose a database commit or an export recovery');
  const mode = values['commit-plan']?'commit':values['resume-export']?'export':'check';
  const approval = values['commit-plan']??values['resume-export'];
  const root = await realpath('.');
  const connectionRoot = await realpath(values['connection-root']??root);
  assert(![root,connectionRoot].some(path=>/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(path)));
  const evidence = join(root,'data','local','release-data');
  const catalog = join(root,'public','data','public_ev_variants.json');
  await unlinked(evidence);
  await unlinked(catalog);
  let reviewed,folder;
  if(mode==='export') assert(!(values.reviewed||values.fresh),'Resume from the G9 commit receipt only');
  else {
    assert(values.reviewed&&values.fresh,'Supply the G9 review and a freshly captured source bundle');
    const file = resolve(values.reviewed);
    assert.equal(dirname(dirname(file)),evidence);
    assert.match(basename(dirname(file)),/^xpeng-g9-release-review-[a-z0-9]+$/i);
    assert.equal(basename(file),'release-review.json');
    const receipt = await json(file);
    assert.deepEqual([receipt.status,receipt.publication_approved,receipt.production_writes],['ready_for_owner_review',false,0]);
    reviewed = receipt.reviewed;
    assert.equal(receipt.reviewed_scope_sha256,g9ApprovalHash(reviewed));
  }
  if(mode!=='check') {
    assert(values.output,'Require a private G9 attempt directory');
    folder = resolve(values.output);
    assert.equal(dirname(folder),evidence);
    assert.match(basename(folder),/^xpeng-g9-apply-[a-z0-9-]+$/);
  } else assert(!values.output,'Checking does not create a release journal');
  const env = {...loadEnv('production',connectionRoot,'SUPABASE_'),...loadEnv('production',connectionRoot,'VITE_SUPABASE_')};
  const url = env.SUPABASE_URL||env.VITE_SUPABASE_URL;
  const key = env.SUPABASE_ANON_KEY||env.VITE_SUPABASE_ANON_KEY;
  assert.equal(new URL(url).origin,'https://'+project+'.supabase.co');
  publicHeaders(key);
  const git = (...args) => execFileSync('git',args,{cwd:root,encoding:'utf8',timeout:20000,maxBuffer:5000000}).trim();
  const journal = name => join(folder,name+'.json');
  let connector;
  const result = await runXpG9Release({mode,approval,reviewed},{
    now:()=>new Date(),
    async assertMain(commit) {
      stage = 'main_revision';
      assert.match(commit,gitRef);
      assert.equal(git('remote','get-url','origin'),'https://github.com/robertbajo-png/swedish-ev-advisor.git');
      assert.equal(git('ls-remote','origin','refs/heads/main'),commit+'\trefs/heads/main','Main changed since G9 review');
      if(mode!=='check') {
        assert.equal(await realpath(git('rev-parse','--show-toplevel')),root,'Require the actual release checkout');
        assert.equal(git('rev-parse','HEAD'),commit,'Require exact main for writes or export');
        assert.equal(git('status','--porcelain','--','database','scripts','functions','src','public/media'),'',
          'The release code or media differ from exact main');
      }
    },
    catalog:()=>mode==='check'?JSON.parse(git('show',reviewed.commit+':public/data/public_ev_variants.json')):json(catalog),
    async siteRows() {
      stage = 'website_catalog';
      const response = await fetch('https://elbilsagenten.se/data/public_ev_variants.json',
        {redirect:'error',signal:AbortSignal.timeout(15000)});
      assert(response.ok,'Could not check website catalog');
      return (await response.json()).records;
    },
    publicRows() {
      stage = 'anonymous_catalog';
      return fetchCatalog({url,key,includeIds:mode==='export',onSchema:missing=>assert.deepEqual(missing,[],'Missing public view columns')});
    },
    verifyMedia:(image,ui)=>{stage='registered_g9_media';return verifyRegisteredG9Media(root,image,ui);},
    freshSource:()=>{stage='source_replay';return readG9Capture(values.fresh).intake;},
    async openSnapshot() {
      stage = 'readonly_snapshot';
      const path = join(connectionRoot,'data','local','db-tools','source-client.mjs');
      await unlinked(path);
      connector = await import(pathToFileURL(path).href);
      assert.equal(connector.PROJECT_REF,project);
      process.chdir(connectionRoot);
      try { return await connector.openSourceSnapshot(); }
      finally { process.chdir(root); }
    },
    async prepare(client,intake) {
      stage = 'readback';
      useCalendarDateText(client);
      const plan = await readG9Plan(client,intake,readG9Image(),new Date());
      return {plan,plan_hash:publicationHash(plan)};
    },
    closeSnapshot:client=>connector.closeSourceSnapshot(client),
    async beginJournal(attempt) {
      stage = 'attempt_journal';
      await mkdir(folder);
      await unlinked(folder);
      await saveNew(journal('attempt'),attempt);
    },
    async commit(client,fresh,reviewed,hash) {
      stage = 'g9_transaction';
      await client.query('ROLLBACK');
      return applyXpG9Release(client,fresh,reviewed,hash);
    },
    saveCommit:receipt=>{stage='commit_receipt';return saveNew(journal('committed-receipt'),receipt);},
    async readJournal() {
      stage = 'export_journal';
      await unlinked(folder);
      return {attempt:await json(journal('attempt')),committed:await json(journal('committed-receipt'))};
    },
    saveCatalog:async value=>{stage='save_catalog';await unlinked(catalog);return atomicJson(catalog,value);},
  });
  console.log(JSON.stringify(result));
}

if(process.argv[1]&&pathToFileURL(process.argv[1]).href===import.meta.url) main().catch(error=>{
  console.error(JSON.stringify({status:'held_or_incomplete',stage,
    reason:error.code==='ERR_ASSERTION'?error.message.split('\n')[0]:'G9 release step failed'}));
  process.exitCode=1;
});
