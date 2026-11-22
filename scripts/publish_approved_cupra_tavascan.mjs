import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { loadEnv } from 'vite';
import { readDriveCapture, readDriveImage } from './cupra_tavascan_drive_publication.mjs';
import { hashPattern, proveTavascanRelease, reviewApproval, tavascanCatalogHash, verifyTavascanProjection } from './cupra_tavascan_release_scope.mjs';
import { applyTavascanDriveRelease, publicationHash, validateNewModelIntake } from './new_model_publication.mjs';
import { readTavascanDriveScope } from './prepare_cupra_tavascan_drive_readback.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { atomicJson, catalogHash, fetchCatalog, publicHeaders, SOURCE } from './sync_public_catalog.mjs';

const project='eutcryxbitudllcnpnex';
const repo='robertbajo-png/swedish-ev-advisor';
const local=['data','local','release-data'];
const catalogPath='public/data/public_ev_variants.json';
const sha=body=>createHash('sha256').update(body).digest('hex');
const json=async path=>JSON.parse(await readFile(path,'utf8'));
const save=(path,value)=>writeFile(path,JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const git=(root,args)=>execFileSync('git',['-C',root,...args],{encoding:'utf8',timeout:20000,maxBuffer:8000000}).trim();
const isLocal=path=>!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(path);
const inside=(parent,child)=>{
  const rel=relative(parent,child);
  return rel&&!isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('../')&&!rel.startsWith('..\\');
};
const unlinked=async path=>assert.equal(await realpath(path),path,'Require a real, unlinked local path');

export async function verifyTavascanMedia(root,image,media) {
  const files=await json(join(root,'src/image-rights.json'));
  const rights=files.assets.filter(asset=>asset.model_key===image.model_key);
  assert.equal(rights.length,1,'Require one exact Tavascan press image');
  for (const [key,value] of Object.entries(image)) assert.deepEqual(rights[0][key],value,'Image evidence changed: '+key);
  assert(!Object.hasOwn(rights[0],'variant_names'),'Reviewed press image is model-level');
  assert.equal((await json(join(root,'src/model-images.json')))[image.model_key],image.asset_url);
  const publisher=(await json(join(root,'src/press-image-publishers.json')))[image.publisher_id];
  assert.deepEqual(publisher.model_keys,[image.model_key]);
  assert.deepEqual(publisher.approved_image_paths,[new URL(image.source_url).pathname]);
  assert.equal(publisher.approved_asset_url,image.downloaded_from);
  assert.equal(publisher.approved_source_sha256,image.source_content_sha256);
  const style=(await json(join(root,'src/image-presentation.json'))).models[image.model_key];
  assert.deepEqual([style.asset_url,style.content_sha256,style.status,style.object_fit],
    [image.asset_url,image.content_sha256,'approved','contain']);
  const responsive=(await json(join(root,'src/image-variants.json')))[image.asset_url];
  assert.equal(responsive.source_sha256,image.content_sha256);
  assert.deepEqual(responsive.variants.map(file=>file.width),[480,800,1280]);
  const assets=[{url:image.asset_url,sha256:image.content_sha256},...responsive.variants.map(({url,sha256})=>({url,sha256}))];
  assert.deepEqual(assets,media,'Static image bundle differs from browser review');
  for (const file of assets) {
    assert.match(file.url,/^\/media\/(?:vehicles|responsive)\/cupra-tavascan-press-9c79705e02a2(?:-(?:480|800|1280)\.webp|\.jpg)$/);
    const path=join(root,'public',file.url.slice(1));
    await unlinked(path);
    assert.equal(sha(await readFile(path)),file.sha256,'Public asset bytes changed');
  }
}

function requireCommit(result,plan) {
  assert.deepEqual([result.committed,result.already_applied,result.variants_inserted,result.anonymous_before_commit,result.paid_calls],
    [true,false,1,true,0]);
  assert.equal(result.model_id,plan.expected_model.id);
  assert.deepEqual(result.canonical_variant_ids,plan.targets.map(item=>item.id));
  assert.equal(result.publication_batch_id,publicationHash(plan));
}

export async function exportTavascanCommit({attempt,committed,approval,publicRows,catalog,saveCatalog,now}) {
  assert.equal(attempt.approval,approval);
  assert.equal(committed.approval,approval);
  const {fresh,reviewed,ui,result,baseline}=committed;
  requireCommit(result,fresh.plan);
  const committedAt=new Date(committed.committed_at);
  proveTavascanRelease(reviewed,fresh,ui,approval,committedAt);
  assert.deepEqual([attempt.fresh_plan_hash,attempt.baseline_sha256,attempt.ui_sha256],
    [fresh.plan_hash,reviewed.baseline_sha256,sha(JSON.stringify(ui))]);
  assert.equal(catalogHash(baseline),reviewed.baseline_sha256);
  const rows=verifyTavascanProjection(baseline,await publicRows(),fresh.plan,reviewed.public_projection_sha256);
  const catalog_sha256=catalogHash(rows);
  assert.equal(catalogHash(await publicRows()),catalog_sha256,'Canonical catalog changed during export');
  const localHash=catalogHash((await catalog()).records);
  assert([reviewed.baseline_sha256,catalog_sha256].includes(localHash),'Local catalog changed during release');
  if(localHash!==catalog_sha256) await saveCatalog({generated_at:now.toISOString(),source:SOURCE,
    schema_version:1,missing_view_columns:[],catalog_sha256,records:rows});
  return {status:'export_verified',added:1,preserved:baseline.length,catalog_sha256,paid_calls:0};
}

async function main() {
  const {values}=parseArgs({options:{connector:{type:'string'},reviewed:{type:'string'},ui:{type:'string'},
    fresh:{type:'string'},output:{type:'string'},apply:{type:'string'},'resume-export':{type:'string'},simulate:{type:'boolean'}}});
  assert(!(values.apply&&values['resume-export']),'Choose commit or export recovery, not both');
  const approval=values.apply??values['resume-export'];
  assert(!(values.simulate&&approval!==undefined),'Simulation never uses a writable connection or exports files');
  if(approval!==undefined) assert.match(approval,hashPattern,'Use the exact owner-approved scope hash');
  const checkout=await realpath('.');
  assert(isLocal(checkout));
  const connectorPath=resolve(values.connector??join(checkout,'data','local','db-tools','source-client.mjs'));
  const sourceRoot=resolve(dirname(connectorPath),'../../..');
  assert.equal(connectorPath,join(sourceRoot,'data','local','db-tools','source-client.mjs'));
  assert(isLocal(sourceRoot)&&(checkout===sourceRoot||inside(join(sourceRoot,...local),checkout)));
  await unlinked(connectorPath);
  assert([ `https://github.com/${repo}`, `https://github.com/${repo}.git`, `git@github.com:${repo}.git`]
    .includes(git(sourceRoot,['remote','get-url','origin'])),'Wrong release repository');
  const releaseRoot=join(checkout,...local);
  await unlinked(releaseRoot);
  const readLocal=async (value,name,pattern,root)=>{
    const path=resolve(value??'');
    await unlinked(path);
    assert.equal(dirname(dirname(path)),root);
    assert.equal(basename(path),name);
    assert.match(basename(dirname(path)),pattern);
    return path;
  };
  const output=values.output&&resolve(values.output);
  if(approval!==undefined){
    assert(output&&dirname(output)===releaseRoot);
    assert.match(basename(output),/^cupra-tavascan-drive-release-[a-z0-9-]+$/);
  }else assert(!output,'Check is read-only and does not use a journal');
  const forJournal=name=>join(output,name+'.json');
  const readJournal=async name=>{const path=forJournal(name);await unlinked(path);return json(path);};
  const env={...loadEnv('production',sourceRoot,'SUPABASE_'),...loadEnv('production',sourceRoot,'VITE_SUPABASE_')};
  const url=env.SUPABASE_URL||env.VITE_SUPABASE_URL,key=env.SUPABASE_ANON_KEY||env.VITE_SUPABASE_ANON_KEY;
  assert.equal(new URL(url).origin,`https://${project}.supabase.co`);
  publicHeaders(key);
  const publicRows=()=>fetchCatalog({url,key,onSchema:missing=>assert.deepEqual(missing,[],'Missing public view columns')});
  const catalog=async()=>{const path=join(checkout,catalogPath);await unlinked(path);return json(path);};
  const assertMain=commit=>{
    assert.match(commit,/^[a-f0-9]{40}$/);
    assert.equal(git(sourceRoot,['ls-remote','origin','refs/heads/main']),commit+'\trefs/heads/main','GitHub main changed since review');
    if(approval!==undefined){
      assert.equal(git(checkout,['rev-parse','HEAD']),commit,'Use the exact-main release checkout');
      assert.equal(resolve(git(checkout,['rev-parse','--show-toplevel'])),checkout,'Use the release checkout root');
      assert(!git(checkout,['status','--porcelain','--untracked-files=no','--','scripts','src','database','public/media']),
        'Release code or registered media has uncommitted changes');
    }
  };
  if(values['resume-export']){
    assert(!(values.fresh||values.reviewed||values.ui),'Recover only from the commit journal');
    await unlinked(output);
    const attempt=await readJournal('attempt'),committed=await readJournal('committed-receipt');
    assertMain(committed.reviewed.commit);
    await verifyTavascanMedia(checkout,readDriveImage(),committed.ui.media);
    const result=await exportTavascanCommit({attempt,committed,approval,publicRows,catalog,now:new Date(),
      saveCatalog:value=>atomicJson(join(checkout,catalogPath),value)});
    console.log(JSON.stringify(result));
    return;
  }
  const reviewed=await json(await readLocal(values.reviewed,'reviewed-plan.json',/^cupra-tavascan-readback-[a-z0-9]+$/i,releaseRoot));
  const uiPath=await readLocal(values.ui,'ui-report.json',/^tavascan-ui-[a-z0-9]+$/i,releaseRoot);
  const ui=await json(uiPath),scope=reviewApproval(reviewed,ui);
  if(values.apply) assert.equal(approval,scope,'Invalid Tavascan release approval');
  assertMain(reviewed.commit);
  const {records:baseline}=await catalog();
  assert.equal(baseline.length,reviewed.baseline_count);
  assert.equal(catalogHash(baseline),reviewed.baseline_sha256);
  assert.equal(tavascanCatalogHash(baseline),reviewed.public_projection_sha256);
  const checkPublic=async()=>assert.equal(catalogHash(await publicRows()),reviewed.baseline_sha256,'Live public catalog differs from review');
  const live=await fetch('https://elbilsagenten.se/'+catalogPath.slice('public/'.length),
    {redirect:'error',signal:AbortSignal.timeout(15000)});
  assert(live.ok && catalogHash((await live.json()).records)===reviewed.baseline_sha256,'Deployed catalog differs from review');
  await checkPublic();
  const mediaRoot=values.apply?checkout:join(dirname(uiPath),'source'),image=readDriveImage();
  await unlinked(mediaRoot);
  await verifyTavascanMedia(mediaRoot,image,ui.media);
  const {intake,capture_sha256}=await readDriveCapture(values.fresh);
  const connector=await import(pathToFileURL(connectorPath).href);
  assert.equal(connector.PROJECT_REF,project);
  let client;
  try {
    try {process.chdir(sourceRoot);client=await connector.openSourceSnapshot();}
    finally {process.chdir(checkout);}
    useCalendarDateText(client);
    const now=new Date();
    validateNewModelIntake(intake,now);
    const plan=await readTavascanDriveScope(client,intake,image,now);
    const fresh={plan,plan_hash:publicationHash(plan),capture_sha256};
    const evidence_expires_at=proveTavascanRelease(reviewed,fresh,ui,scope,new Date());
    if(values.simulate){
      const {verifyTavascanReleaseRehearsal}=await import('./verify_cupra_tavascan_release.mjs');
      const {readPublishedFixture}=await import('./isolated_catalog_review.mjs');
      const test=await verifyTavascanReleaseRehearsal({reviewed,fresh,ui,scope,baseline,fixture:await readPublishedFixture(client),now});
      console.log(JSON.stringify(test));
      return;
    }
    if(!values.apply){
      console.log(JSON.stringify({status:'ready_for_owner_review',scope_sha256:scope,variants:1,
        preserved:baseline.length,evidence_expires_at,production_writes:0,paid_calls:0}));
      return;
    }
    assertMain(reviewed.commit);
    await checkPublic();
    assert.equal(catalogHash((await catalog()).records),reviewed.baseline_sha256);
    await mkdir(output);
    await unlinked(output);
    await save(forJournal('attempt'),{approval,fresh_plan_hash:fresh.plan_hash,
      baseline_sha256:reviewed.baseline_sha256,ui_sha256:sha(JSON.stringify(ui))});
    await client.query('ROLLBACK');
    const checkedAt=new Date();
    const result=await applyTavascanDriveRelease(client,fresh,reviewed,ui,approval,checkedAt);
    requireCommit(result,plan);
    await save(forJournal('committed-receipt'),{approval,result,fresh,reviewed,ui,baseline,committed_at:checkedAt.toISOString()});
    console.log(JSON.stringify({status:'committed_export_pending',inserted:1,paid_calls:0}));
  } finally {if(client) await connector.closeSourceSnapshot(client);}
}

if(process.argv[1]&&pathToFileURL(process.argv[1]).href===import.meta.url) main().catch(error=>{
  console.error(JSON.stringify({status:'held_or_incomplete',code:/^[A-Z0-9_]{1,32}$/.test(error.code??'')?error.code:null,
    reason:error.code==='ERR_ASSERTION'?error.message.split('\n')[0]:'Release step failed; inspect the private journal before retrying'}));
  process.exitCode=1;
});
