import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdtemp,readFile,realpath,writeFile} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {parse} from 'parse5';
import {loadEnv} from 'vite';
import {policy,readInsterCapture} from './hyundai_inster_advanced_publication.mjs';
import {databaseCatalogHash,insterCatalogDelta,insterReleaseHash,proveInsterRelease} from './hyundai_inster_advanced_release_scope.mjs';
import {readInsterScope} from './verify_hyundai_inster_advanced_local.mjs';
import {applyInsterRelease,buildNewModelPlan,publicationHash} from './new_model_publication.mjs';
import {CATALOG_PROJECT,catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {catalogHash,fetchCatalog,publicHeaders,SOURCE} from './sync_public_catalog.mjs';

const repository='robertbajo-png/swedish-ev-advisor';
const site='https://elbilsagenten.se';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const shaPattern=/^[a-f0-9]{64}$/;
const bytes=async file=>{assert.equal(await realpath(file),file);return readFile(file);};
const json=async file=>JSON.parse(await bytes(file));
const save=(file,v)=>writeFile(file,JSON.stringify(v,null,2)+'\n',{flag:'wx'});
const get=async url=>{
  const response=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(20000)});
  assert.equal(response.status,200,'Unavailable prerequisite: '+new URL(url).pathname);
  return response;
};
const live=path=>get(site+path);
let stage='arguments';

function readerPath(html){
  const hits=[];
  function scan(node){
    if(node.tagName==='script'){
      const attributes=Object.fromEntries(node.attrs.map(({name,value})=>[name,value]));
      if(attributes.type==='module'&&/^\/assets\/index-[a-zA-Z0-9_-]+\.js$/.test(attributes.src??''))
        hits.push(attributes.src);
    }
    for(const child of node.childNodes??[])scan(child);
  }
  scan(parse(html));assert.equal(hits.length,1,'Expected one deployed reader bundle');
  return hits[0];
}

async function main(){
  const {values:v}=parseArgs({options:{scope:{type:'string'},fresh:{type:'string'},'ci-run':{type:'string'},
    'release-commit':{type:'string'},'reader-sha256':{type:'string'},'commit-seal':{type:'string'},
    'export-journal':{type:'string'},'client-module':{type:'string'}}});
  const root=await realpath('.'),release=join(root,'data','local','release-data');
  assert.equal(await realpath(release),release);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  const target={commit:v['release-commit'],reader_sha256:v['reader-sha256']};
  assert.match(target.commit??'',/^[a-f0-9]{40}$/);
  assert.match(target.reader_sha256??'',shaPattern);
  assert.match(v['ci-run']??'',/^[1-9][0-9]{0,19}$/);
  assert(v.scope&&Boolean(v.fresh)!==Boolean(v['export-journal']));
  assert(!(v['commit-seal']&&v['export-journal']));
  const file=resolve(v.scope);
  assert.equal(dirname(dirname(file)),release);
  assert.match(basename(dirname(file)),/^inster-advanced-scope-[a-z0-9]+$/i);
  assert.equal(basename(file),'scope.json');
  const scope=await json(file);
  const seal=insterReleaseHash(scope,target);
  if(v['commit-seal'])assert.equal(v['commit-seal'],seal,'Require the exact verified Inster seal');

  const git=(...args)=>execFileSync('git',args,{cwd:root,timeout:30000,maxBuffer:16_000_000,windowsHide:true});
  const text=(...args)=>git(...args).toString('utf8').trim();
  const stored=file=>git('show',target.commit+':'+file);
  async function requireRelease(){
    stage='exact_main_and_ci';
    assert.match(text('remote','get-url','origin'),
      /^(?:https:\/\/github\.com\/|git@github\.com:)robertbajo-png\/swedish-ev-advisor(?:\.git)?$/i);
    assert.equal(text('ls-remote','--exit-code','origin','refs/heads/main'),target.commit+'\trefs/heads/main');
    assert.equal(text('rev-parse','HEAD'),target.commit);
    assert.equal(text('status','--porcelain','--untracked-files=normal'),'','Use the clean exact-main checkout');
    const ci=await (await get('https://api.github.com/repos/'+repository+'/actions/runs/'+v['ci-run'])).json();
    assert.deepEqual([ci.head_sha,ci.head_branch,ci.path,ci.event,ci.status,ci.conclusion,ci.repository?.full_name],
      [target.commit,'main','.github/workflows/ci.yml','push','completed','success',repository],'Current main CI not verified');
  }
  await requireRelease();
  stage='verified_live_media';
  const registry=name=>JSON.parse(stored('src/'+name+'.json'));
  const image=scope.plan.image;
  const {private_file,...publicRights}=image;
  assert.deepEqual(registry('image-rights').assets.filter(item=>item.model_key===image.model_key),[publicRights]);
  assert.equal(registry('model-images')[policy.imageKey],image.asset_url);
  const responsive=registry('image-variants')[image.asset_url],position=registry('image-presentation').models[policy.imageKey];
  assert.deepEqual([position.asset_url,position.content_sha256,position.status,position.object_fit],
    [image.asset_url,policy.imageHash,'approved','contain']);
  assert.equal(responsive.source_sha256,policy.imageHash);
  assert.deepEqual(responsive.variants.map(({url,sha256})=>({url,sha256})),scope.media.slice(1));
  for(const item of scope.media){
    assert.match(item.url,/^\/media\/(vehicles|responsive)\/hyundai-inster-74c89ece773a(?:-(?:480|800|1280))?\.(?:jpg|webp)$/);
    assert.equal(sha(stored('public'+item.url)),item.sha256);
    assert.equal(sha(Buffer.from(await (await live(item.url)).arrayBuffer())),item.sha256);
  }
  stage='verified_live_reader_and_catalog';
  const entry=readerPath(await (await live('/')).text());
  const reader=Buffer.from(await (await live(entry)).arrayBuffer());
  assert.equal(sha(reader),target.reader_sha256);
  assert(reader.includes('hyundai-inster-74c89ece773a'),'Deployed reader does not contain approved Inster support');
  const baseline=JSON.parse(stored('public/data/public_ev_variants.json')).records;
  assert.equal(databaseCatalogHash(baseline),scope.database_baseline_sha256);
  assert.equal(databaseCatalogHash((await (await live('/data/public_ev_variants.json')).json()).records),
    scope.database_baseline_sha256,'Live catalog changed before Inster release');

  const connection=await catalogConnectorPath(root,v['client-module']);
  const fetchAnonymousRows=async()=>{
    const env={...loadEnv('production',connection.sourceRoot,'SUPABASE_'),
      ...loadEnv('production',connection.sourceRoot,'VITE_SUPABASE_')};
    const url=env.SUPABASE_URL||env.VITE_SUPABASE_URL,key=env.SUPABASE_ANON_KEY||env.VITE_SUPABASE_ANON_KEY;
    assert.equal(url?.replace(/\/$/,''),'https://'+CATALOG_PROJECT+'.supabase.co');
    publicHeaders(key);
    return fetchCatalog({url,key,includeIds:true,onSchema:missing=>assert.deepEqual(missing,[])});
  };
  if(v['export-journal']){
    stage='scoped_readback_export';
    const dir=resolve(v['export-journal']);
    assert.equal(dirname(dir),release);
    assert.match(basename(dir),/^inster-advanced-apply-[a-z0-9]+$/i);
    const attempt=await json(join(dir,'attempt.json')),receipt=await json(join(dir,'commit.json'));
    assert.deepEqual([attempt.seal,attempt.target],[seal,target]);
    assert.equal(receipt.attempt_sha256,publicationHash(attempt));
    proveInsterRelease(scope,attempt.plan,target,seal,new Date(attempt.checked_at));
    assert.deepEqual([receipt.result.committed,receipt.result.variants_inserted,receipt.result.anonymous_before_commit,
      receipt.result.publication_batch_id,receipt.result.canonical_variant_ids],
    [true,1,true,publicationHash(attempt.plan),attempt.plan.targets.map(item=>item.id)]);
    const rows=await fetchAnonymousRows(),records=insterCatalogDelta(baseline,rows,attempt.plan);
    assert.equal(databaseCatalogHash(await fetchAnonymousRows()),databaseCatalogHash(rows),'Public rows changed during export');
    const output=join(dir,'public_ev_variants.json');
    await save(output,{source:SOURCE,generated_at:new Date().toISOString(),catalog_sha256:catalogHash(records),records});
    return {status:'private_inster_export_verified',output,added:1,catalog_sha256:catalogHash(records),deployed:false};
  }

  stage='fresh_sources';
  assert.equal(databaseCatalogHash(await fetchAnonymousRows()),scope.database_baseline_sha256,'Anonymous Supabase baseline changed');
  const fresh=readInsterCapture(v.fresh,root);
  const session=await openCatalogSnapshot(connection);
  let journal;
  try{
    stage='core_scope';
    const {expected:e,productionExactDc,publicRows:sqlRows}=await readInsterScope(session.client,fresh.intake);
    assert(productionExactDc,'Migration 027 must be installed');
    assert.equal(databaseCatalogHash(sqlRows),scope.database_baseline_sha256,'SQL baseline changed');
    const plan=buildNewModelPlan({canonical_models:[e.expected_model],canonical_model_variants:[],
      model_aliases:[e.expected_alias],market_models:[e.expected_market],market_model_monthly_stats:e.expected_monthly,
      manufacturer_sources:e.expected_sources},fresh.intake,fresh.image);
    proveInsterRelease(scope,plan,target,seal,new Date());
    if(!v['commit-seal'])return {status:'inster_can_insert_verified_scope',seal,production_writes:0};
    await requireRelease();
    journal=await mkdtemp(join(release,'inster-advanced-apply-'));
    const attempt={seal,target,plan,checked_at:new Date().toISOString()};
    await save(join(journal,'attempt.json'),attempt);
    stage='scoped_transaction';
    await session.client.query('ROLLBACK');
    const result=await applyInsterRelease(session.client,plan,scope,target,seal);
    assert.deepEqual([result.committed,result.variants_inserted,result.anonymous_before_commit,result.publication_batch_id],
      [true,1,true,publicationHash(plan)]);
    await save(join(journal,'commit.json'),{attempt_sha256:publicationHash(attempt),result});
    stage='separate_anon_readback';
    const readback=insterCatalogDelta(baseline,await fetchAnonymousRows(),plan);
    return {status:'inster_inserted_and_verified',journal,variants:readback.length,paid_calls:0};
  }catch(error){
    if(journal)console.error(JSON.stringify({journal,status:'inspect_journal_before_retrying'}));
    throw error;
  }finally{await session.close();}
}

await main().then(r=>console.log(JSON.stringify(r))).catch(error=>{
  console.error(JSON.stringify({status:'inster_release_not_verified',stage,
    reason:error.code==='ERR_ASSERTION'?error.message.split('\n')[0]:'Check exact release evidence before retrying.'}));
  process.exitCode=1;
});
