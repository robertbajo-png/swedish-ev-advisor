import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFile,realpath} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {assertExactDcInstalled} from './verify_exact_dc_migration.mjs';

const file='database/migrations/027_exact_dc_charging.sql';
const storage=['canonical_model_variants','extracted_variant_drafts','public_ev_variants'];
let stage='arguments';

async function inventory(client){
  const counts=[];
  for(const table of storage){
    const {rows:[row]}=await client.query(`
      SELECT count(*)::int AS count, pg_catalog.md5(
        coalesce(jsonb_agg(to_jsonb(item) ORDER BY item.id)::text,'[]')) AS digest
      FROM public.${table} item`);
    counts.push(row);
  }
  const acl=(await client.query(`
    SELECT relname AS name, relrowsecurity AS rls,
      has_any_column_privilege('anon',oid,'SELECT') AS anon_read,
      has_any_column_privilege('authenticated',oid,'SELECT') AS user_read,
      has_table_privilege('anon',oid,'INSERT, UPDATE, DELETE, TRUNCATE') AS anon_write,
      has_table_privilege('authenticated',oid,'INSERT, UPDATE, DELETE, TRUNCATE') AS user_write
    FROM pg_catalog.pg_class
    WHERE relnamespace='public'::regnamespace AND relname=ANY($1::text[])
    ORDER BY relname`,[storage])).rows;
  assert.deepEqual(acl.map(r=>[r.name,r.rls,r.anon_read,r.user_read,r.anon_write,r.user_write]),[
    ['canonical_model_variants',true,false,false,false,false],
    ['extracted_variant_drafts',true,false,false,false,false],
    ['public_ev_variants',false,true,true,false,false],
  ]);
  return {counts,acl};
}

export async function applyExactDcMigration(client,source){
  const wrapped=/^--[^\n]*\nbegin;\n([\s\S]+)\ncommit;\n?$/i.exec(source);
  assert(wrapped,'Require the version-controlled transactional migration 027');
  const before=await inventory(client);
  let installed=true;
  try{await assertExactDcInstalled(client);}
  catch(error){
    if(!error.message.includes('Migration 027 is required'))throw error;
    installed=false;
  }
  if(installed)return {installed:true,applied:false,public_variants:before.counts[2].count};

  await client.query('ROLLBACK');
  await client.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ WRITE');
  try{
    await client.query(wrapped[1]);
    await assertExactDcInstalled(client);
    assert.deepEqual(await inventory(client),before,'Migration would change the catalog or role boundary');
    await client.query('SET LOCAL ROLE anon');
    const {rows:[reader]}=await client.query('SELECT count(*)::int AS count FROM public.public_ev_variants');
    assert.equal(reader.count,before.counts[2].count,'Anonymous reader changed during migration');
    await client.query('RESET ROLE');
    await client.query('COMMIT');
  }catch(error){
    await client.query('ROLLBACK');
    throw error;
  }
  await client.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
  await assertExactDcInstalled(client);
  assert.deepEqual(await inventory(client),before,'Post-commit catalog or roles differed from the saved baseline');
  return {installed:true,applied:true,public_variants:before.counts[2].count};
}

async function main(){
  const {values}=parseArgs({options:{'main-commit':{type:'string'},'client-module':{type:'string'}}});
  const main=values['main-commit'];
  assert.match(main??'',/^[a-f0-9]{40}$/,'Pin the currently verified GitHub main commit');
  const root=await realpath(fileURLToPath(new URL('../',import.meta.url)));
  assert.equal(await realpath('.'),root,'Run from the checkout containing migration 027');
  const git=(...args)=>execFileSync('git',args,{cwd:root,encoding:'utf8',timeout:30000,windowsHide:true});
  assert.match(git('remote','get-url','origin').trim(),
    /^(?:https:\/\/github\.com\/|git@github\.com:)robertbajo-png\/swedish-ev-advisor(?:\.git)?$/i);
  assert.equal(git('ls-remote','--exit-code','origin','refs/heads/main').trim(),main+'\trefs/heads/main');
  assert.equal(await realpath(join(root,file)),join(root,file));
  const source=(await readFile(join(root,file),'utf8')).replaceAll('\r\n','\n');
  assert.equal(source,git('show',main+':'+file),'Use the exact migration from reviewed main');
  const session=await openCatalogSnapshot(await catalogConnectorPath(root,values['client-module']));
  try{
    stage='migration_027';
    const result=await applyExactDcMigration(session.client,source);
    console.log(JSON.stringify({status:'exact_dc_verified',migration_sha256:createHash('sha256').update(source).digest('hex'),
      main,...result,vehicle_updates:0,paid_calls:0}));
  }finally{await session.close();}
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main().catch(error=>{
  console.error(JSON.stringify({status:'migration_027_not_verified',stage,code:error.code??null,
    reason:error.code==='ERR_ASSERTION'?error.message.split('\n')[0]:'Open a fresh read-only check before retrying.'}));
  process.exitCode=1;
});
