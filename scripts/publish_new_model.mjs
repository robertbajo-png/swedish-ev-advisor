import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile,realpath} from 'node:fs/promises';
import {resolve,relative,isAbsolute} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {spawnSync} from 'node:child_process';
import {newModelAdapter} from './new_model_adapters.mjs';
import {publicationSnapshot,buildNewModelPlan,applyNewModelPlan,publicationHash} from './new_model_publication.mjs';
import {useCalendarDateText,reportFailure} from './refresh_kia_specs.mjs';
import {ADAPTER as ID_BUZZ_ADAPTER} from './volkswagen_id_buzz_publication.mjs';
const read=async p=>JSON.parse(await readFile(p,'utf8'));
const save=async(p,v)=>writeFile(p,JSON.stringify(v,null,2)+'\n');
const fingerprint=v=>JSON.parse(JSON.stringify(v,(k,value)=>['content_hash','source_hash','fetched_at'].includes(k)?undefined:value));
const collectors=new Map([['kia_ev2_sweden_pilot_v1','scripts/kia_ev2_intake.py'],
 ['toyota_chr_plus_sweden_pilot_v1','scripts/toyota_chr_plus_intake.py']]);
async function main(){
 const {values}=parseArgs({options:{adapter:{type:'string',default:'kia_ev2_sweden_pilot_v1'},'client-module':{type:'string'},
  output:{type:'string',default:'data/local/release-data/kia-ev2-pilot-2026-11-15/publication'},apply:{type:'string'},
  review:{type:'string'},'approved-plan':{type:'string'},'prepare-only':{type:'boolean'},'export-only':{type:'boolean'}}});
 const policy=newModelAdapter(values.adapter),collector=collectors.get(values.adapter);
 if(policy.adapter===ID_BUZZ_ADAPTER && values.review && values['approved-plan']){
  const {publishApprovedIdBuzz}=await import('./publish_approved_id_buzz.mjs');
  return publishApprovedIdBuzz(values);
 }
 assert(!values.review&&!values['approved-plan']&&!values['prepare-only']&&!values['export-only'],'ID. Buzz release options are model-specific');
 assert(!policy.localOnly,'Local-only pilot cannot use the production connector');assert(collector);assert(values['client-module']);
 const folder=resolve(values.output),local=await realpath('data/local');await mkdir(folder,{recursive:true});
 const rel=relative(local,await realpath(folder));assert(rel&&!rel.startsWith('..')&&!isAbsolute(rel),'Private proof must remain under data/local');
 try{await readFile(resolve(folder,'committed-receipt.json'));throw Error('ExistingCommittedReceiptCheckBeforeRetry');}catch(e){if(e.code!=='ENOENT')throw e;}
 let client;const connector=await import(pathToFileURL(resolve(values['client-module'])).href);
 try{
  client=await connector.openSourceSnapshot();useCalendarDateText(client);
  const before=await publicationSnapshot(client);
  const news=async()=>JSON.parse(JSON.stringify({controls:(await client.query('SELECT * FROM public.news_ai_config ORDER BY id')).rows,
   articles:(await client.query('SELECT id,status,updated_at FROM public.news_articles ORDER BY id')).rows}));
  const unchangedNews=await news();await client.query('ROLLBACK');
  const capture=resolve(folder,values.apply?'fresh':'source');
  const collected=spawnSync(process.execPath,['scripts/run_python.mjs',collector,'--output',capture],{encoding:'utf8',windowsHide:true,timeout:240000});
  assert.equal(collected.status,0,'Exact-source collection failed; inspect private captures, no publication');
  const intake=await read(resolve(capture,'intake.json'));
  const registry=await read('src/image-rights.json');
  const image=registry.assets.filter(r=>r.model_key===policy.imageKey);assert.equal(image.length,1);
  const plan=buildNewModelPlan(before,intake,image[0]),hash=publicationHash(plan);
  if(!values.apply){
   await save(resolve(folder,'prepared-plan.json'),{hash,plan,news:unchangedNews});
   console.log(JSON.stringify({dry_run:true,plan_sha256:hash,model:intake.model.model,variants:plan.targets.length,database_writes:0,paid_calls:0}));return;
  }
  const prepared=await read(resolve(folder,'prepared-plan.json'));
  assert.equal(prepared.hash,values.apply);assert.equal(publicationHash(prepared.plan),prepared.hash);
  assert.deepEqual(unchangedNews,prepared.news,'News changed since preparation; prepare again');
  assert.deepEqual(fingerprint(intake),fingerprint(prepared.plan.intake),'Exact extracted identities/facts/evidence changed');
  for(const key of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources','image','targets']){
   if(key==='targets')continue;
   assert.deepEqual(plan[key],prepared.plan[key],'Prepared scope changed: '+key);
  }
  const result=await applyNewModelPlan(client,plan,hash);
  await save(resolve(folder,'committed-receipt.json'),{...result,prepared_plan_sha256:prepared.hash,committed_at:new Date().toISOString()});
  assert.deepEqual(await news(),unchangedNews,'Check committed receipt: concurrent news changed');
  console.log(JSON.stringify({...result,news_unchanged:true}));
 }finally{await connector.closeSourceSnapshot(client);}
}
main().catch(reportFailure);
