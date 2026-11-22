import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdir,mkdtemp,readFile,realpath,writeFile} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {parse} from 'parse5';
import {loadEnv} from 'vite';
import {createGlbScope,runGlbRelease} from './mercedes_glb_release.mjs';
import {readGlbCapture} from './mercedes_glb_publication.mjs';
import {applyGlbRelease,publicationHash} from './new_model_publication.mjs';
import {readGlbSnapshot} from './verify_mercedes_glb_local.mjs';
import {CATALOG_PROJECT,catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {catalogHash,fetchCatalog,publicHeaders,SOURCE} from './sync_public_catalog.mjs';

const project='eutcryxbitudllcnpnex', origin='https://elbilsagenten.se';
const sha=body=>createHash('sha256').update(body).digest('hex');
const codeHash=body=>sha(body.toString('utf8').replace(/\r\n/g,'\n'));
const hex=/^[a-f0-9]{64}$/;
const uiFiles=['src/main.jsx','src/vehicle-ui.jsx','src/price-evidence.js','src/vehicle-names.js','src/spec-qualifications.js',
  'src/advisor-matching.js','src/decision-metrics.js','src/tco.js','scripts/audit_image_rights.py','scripts/prepare_responsive_images.py'];
const codeFiles=[...uiFiles,'database/migrations/026_manufacturer_from_price.sql','functions/_shared/advisor-core.mjs',
  'scripts/prerender_static_routes.py','scripts/sync_public_catalog.mjs','scripts/model_image_sync.mjs','scripts/new_model_adapters.mjs',
  'scripts/new_model_publication.mjs','scripts/mercedes_glb_review.mjs','scripts/mercedes_glb_publication.mjs',
  'scripts/mercedes_glb_release.mjs','scripts/publish_approved_mercedes_glb.mjs','scripts/verify_mercedes_glb_local.mjs',
  'scripts/local_catalog_connector.mjs','scripts/isolated_catalog_review.mjs'].sort();
const clean=async path=>assert.equal(await realpath(path),path,'Require an unlinked local GLB path');
const bytes=async path=>{await clean(path);return readFile(path);};
const json=async path=>JSON.parse(await bytes(path));
const save=(path,value)=>writeFile(path,JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const assetPath=/^\/media\/(?:vehicles|responsive)\/mercedes-benz-glb-press-[a-f0-9]{12}(?:-\d+)?\.(?:jpg|webp)$/;

async function prepare(root,release,folder,uiPath) {
  assert.equal(dirname(folder),release);
  assert.match(basename(folder),/^mercedes-glb-local-[a-z0-9]+$/i);
  assert.equal(dirname(dirname(uiPath)),folder);
  assert.match(basename(dirname(uiPath)),/^ui-[a-z0-9]+$/i);
  assert.equal(basename(uiPath),'ui-report.json');
  const [plan,report,ui,baseline,candidate]=await Promise.all([
    json(join(folder,'plan.json')),json(join(folder,'report.json')),json(uiPath),
    json(join(folder,'main-source/public/data/public_ev_variants.json')),json(join(folder,'candidate-catalog.json'))]);
  assert.deepEqual(Object.keys(ui.code_sha256).sort(),[...uiFiles].sort());
  const code={};
  const uiSource=join(dirname(uiPath),'source');
  for(const file of codeFiles) {
    const raw=await bytes(join(root,file));
    code[file]=codeHash(raw);
    if(uiFiles.includes(file)){
      const observed=await bytes(join(uiSource,file));
      assert.equal(sha(observed),ui.code_sha256[file],'GLB browser proof changed: '+file);
      assert.equal(code[file],codeHash(observed),'GLB UI differs from verified package: '+file);
    }
  }
  const manifest=(await json(join(uiSource,'src','image-variants.json')))[plan.image.asset_url];
  assert.equal(manifest.source_sha256,plan.image.content_sha256);
  assert.deepEqual(manifest.variants.map(m=>m.width),[746,1782]);
  const media=[{url:plan.image.asset_url,sha256:plan.image.content_sha256},
    ...manifest.variants.map(({url,sha256})=>({url,sha256}))];
  for(const item of media){
    assert.match(item.url,assetPath);
    assert.equal(sha(await bytes(join(uiSource,'public',item.url.slice(1)))),item.sha256);
  }
  const scope=createGlbScope({plan,report,ui,baseline:baseline.records,candidate:candidate.records,code,media});
  const path=join(await mkdtemp(join(release,'mercedes-glb-scope-')),'scope.json');
  await save(path,scope);
  return {status:scope.status,scope:path,variants:2,publication_approved:false,production_writes:0,paid_calls:0};
}

function entryBundle(homepage) {
  const matches=[];
  function scan(node){
    if(node.tagName==='script'){
      const attrs=Object.fromEntries(node.attrs.map(({name,value})=>[name,value]));
      if(attrs.type==='module'&&/^\/assets\/index-[a-zA-Z0-9_-]+\.js$/.test(attrs.src??''))matches.push(attrs.src);
    }
    for(const child of node.childNodes??[])scan(child);
  }
  scan(parse(homepage));
  assert.equal(matches.length,1,'Require one deployed GLB reader entry bundle');
  return matches[0];
}

let stage='arguments';
async function main(){
  const {values}=parseArgs({options:{
    prepare:{type:'boolean'},readback:{type:'string'},ui:{type:'string'},scope:{type:'string'},fresh:{type:'string'},
    'release-commit':{type:'string'},'reader-sha256':{type:'string'},'commit-approved':{type:'string'},
    'export-approved':{type:'string'},journal:{type:'string'},'client-module':{type:'string'},
  }});
  const root=await realpath('.'), release=join(root,'data','local','release-data');
  await clean(release);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  if(values.prepare){
    assert(values.readback&&values.ui&&Object.keys(values).length===3,'Use --prepare with the isolated readback and browser proof only');
    return prepare(root,release,resolve(values.readback),resolve(values.ui));
  }
  assert(!(values.ui||values.readback));
  assert(!(values['commit-approved']&&values['export-approved']));
  const mode=values['commit-approved']?'commit':values['export-approved']?'export':'check';
  assert(values.scope&&values['release-commit']&&values['reader-sha256']);
  assert(mode==='export'?!values.fresh:values.fresh,'Require a new GLB capture for check or commit, not export');
  assert(mode==='check'?!values.journal:values.journal,'Require a private attempt journal for commit or export');
  const path=resolve(values.scope);
  assert.equal(dirname(dirname(path)),release);
  assert.match(basename(dirname(path)),/^mercedes-glb-scope-[a-z0-9]+$/i);
  assert.equal(basename(path),'scope.json');
  const scope=await json(path), target={commit:values['release-commit'],reader_sha256:values['reader-sha256']};
  const approval=values['commit-approved']??values['export-approved'];
  const journal=values.journal&&resolve(values.journal);
  if(journal){
    assert.equal(dirname(journal),release);
    assert.match(basename(journal),/^mercedes-glb-apply-[a-z0-9]+$/i);
  }
  const git=(...args)=>execFileSync('git',args,{cwd:root,timeout:30000,maxBuffer:16_000_000,windowsHide:true});
  const gitText=(...args)=>git(...args).toString('utf8').trim();
  const stored=(file)=>git('show',target.commit+':'+file);
  const registry=(name)=>JSON.parse(stored('src/'+name+'.json'));
  const live=async pathname=>{
    const response=await fetch(origin+pathname,{redirect:'error',signal:AbortSignal.timeout(20000)});
    assert.equal(response.status,200,'Missing deployed GLB prerequisite: '+pathname);
    return response;
  };
  assert.equal(project,CATALOG_PROJECT);
  const connection=await catalogConnectorPath(root,values['client-module']);
  let snapshot;
  return runGlbRelease({mode,scope,target,approval},{
    now:()=>new Date(),
    async verifyProduction(reviewed,requested) {
      stage='exact_main';
      assert.match(gitText('remote','get-url','origin'),/^(?:https:\/\/github\.com\/|git@github\.com:)robertbajo-png\/swedish-ev-advisor(?:\.git)?$/i);
      assert.equal(gitText('ls-remote','--exit-code','origin','refs/heads/main'),requested.commit+'\trefs/heads/main',
        'Reviewed GLB code is not current main');
      assert.deepEqual(Object.keys(reviewed.code).sort(),codeFiles);
      for(const file of codeFiles){
        assert.match(reviewed.code[file],hex);
        assert.equal(codeHash(stored(file)),reviewed.code[file],'Main lacks reviewed GLB code: '+file);
        assert.equal(codeHash(await bytes(join(root,file))),reviewed.code[file],'Local GLB release code differs: '+file);
      }
      if(mode==='commit'){
        assert.equal(await realpath(gitText('rev-parse','--show-toplevel')),root);
        assert.equal(gitText('rev-parse','HEAD'),requested.commit);
        assert.equal(gitText('status','--porcelain','--untracked-files=normal'),'','GLB release needs a clean exact-main checkout');
      }
      stage='reviewed_live_images';
      const image=reviewed.plan.image;
      const photos=registry('image-rights').assets.filter(row=>row.model_key===image.model_key);
      assert.equal(photos.length,1,'Require one exact GLB model photo');
      for(const [key,value] of Object.entries(image))assert.deepEqual(photos[0][key],value,'GLB image attribution changed: '+key);
      assert.equal(registry('model-images')[image.model_key],image.asset_url);
      const manifest=registry('image-variants')[image.asset_url];
      assert.equal(manifest.source_sha256,image.content_sha256);
      assert.deepEqual(manifest.variants.map(({url,sha256})=>({url,sha256})),reviewed.media.slice(1));
      assert.deepEqual(reviewed.media[0],{url:image.asset_url,sha256:image.content_sha256});
      const position=registry('image-presentation').models[image.model_key];
      assert.deepEqual([position.asset_url,position.content_sha256,position.status,position.object_fit],
        [image.asset_url,image.content_sha256,'approved','contain']);
      for(const item of reviewed.media){
        assert.match(item.url,assetPath);
        assert.equal(sha(stored('public'+item.url)),item.sha256,'Main GLB photo differs from review');
        assert.equal(sha(Buffer.from(await (await live(item.url)).arrayBuffer())),item.sha256,'Live GLB photo differs from review');
      }
      stage='reviewed_live_reader';
      const entry=entryBundle(await (await live('/')).text());
      const reader=Buffer.from(await (await live(entry)).arrayBuffer());
      assert.equal(sha(reader),requested.reader_sha256,'Live GLB reader differs from the approved bundle');
      assert.match(reader.toString('utf8'),/manufacturer_from/,'Starting-price support is not deployed');
    },
    baseline:()=>JSON.parse(stored('public/data/public_ev_variants.json')).records,
    liveBaseline:async()=>(await (await live('/data/public_ev_variants.json')).json()).records,
    async publicRows(){
      stage='anonymous_supabase';
      const env={...loadEnv('production',connection.sourceRoot,'SUPABASE_'),...loadEnv('production',connection.sourceRoot,'VITE_SUPABASE_')};
      const url=env.SUPABASE_URL||env.VITE_SUPABASE_URL, key=env.SUPABASE_ANON_KEY||env.VITE_SUPABASE_ANON_KEY;
      assert.equal(url?.replace(/\/$/,''),'https://'+project+'.supabase.co');
      publicHeaders(key);
      return fetchCatalog({url,key,includeIds:true,onSchema:missing=>assert.deepEqual(missing,[])});
    },
    freshSource(){stage='source_replay';return readGlbCapture(values.fresh).intake;},
    async openSnapshot(){
      stage='read_only_database_prerequisites';
      snapshot=await openCatalogSnapshot(connection);
      return snapshot.client;
    },
    readSnapshot:readGlbSnapshot,
    closeSnapshot:()=>snapshot.close(),
    async saveAttempt(attempt){
      stage='exclusive_local_attempt_journal';
      await mkdir(journal);
      await clean(journal);
      await save(join(journal,'attempt.json'),attempt);
    },
    async commit(client,plan,approved){
      stage='approved_atomic_database_transaction';
      await client.query('ROLLBACK');
      return applyGlbRelease(client,plan,scope,target,approved);
    },
    saveCommit:receipt=>save(join(journal,'committed-receipt.json'),receipt),
    async readJournal(){
      await clean(journal);
      return {attempt:await json(join(journal,'attempt.json')),receipt:await json(join(journal,'committed-receipt.json'))};
    },
    saveExport:records=>save(join(journal,'candidate-catalog.json'),{source:SOURCE,schema_version:1,
      generated_at:new Date().toISOString(),catalog_sha256:catalogHash(records),records,missing_view_columns:[]}),
  });
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  try{console.log(JSON.stringify(await main()));}
  catch(error){
    console.error(JSON.stringify({status:'held',stage,code:error.code??null,
      ...(error.code==='ERR_ASSERTION'?{reason:error.message.split('\n')[0]}:{}),
      production_write_attempted:stage==='approved_atomic_database_transaction',
      ...(stage==='approved_atomic_database_transaction'?{action:'Inspect the journal and database before any retry'}:{})}));
    process.exitCode=1;
  }
}
