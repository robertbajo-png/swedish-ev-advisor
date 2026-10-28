import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';

const db=new PGlite();
try {
  await db.exec('create role anon;create role authenticated;create role service_role bypassrls;grant usage on schema public to anon,authenticated,service_role');
  const schema=(await readFile(new URL('../database/schema.sql',import.meta.url),'utf8')).replace('create extension if not exists pgcrypto;','')
    .replace(/, 'authorized_dealer_model_page', 'authorized_dealer_stock_page'/g,'')
    .replace(/^\s*alter type source_type add value if not exists 'authorized_dealer_(?:model|stock)_page';$/gm,'');
  await db.exec(schema);
  const state=async()=>({
    columns:(await db.query("select table_name,column_name,data_type,udt_name from information_schema.columns where table_schema='public' order by 1,2")).rows,
    permissions:(await db.query("select relname,relrowsecurity,relforcerowsecurity,relacl::text from pg_class where relnamespace='public'::regnamespace and relkind in ('r','v') order by relname")).rows,
    policies:(await db.query("select * from pg_policies where schemaname='public' order by tablename,policyname")).rows,
  });
  const before=await state();
  const old=(await db.query("select enumlabel from pg_enum where enumtypid='public.source_type'::regtype order by enumsortorder")).rows.map(r=>r.enumlabel);
  assert(!old.includes('authorized_dealer_stock_page'));
  const migration=await readFile(new URL('../database/migrations/021_source_type_alignment.sql',import.meta.url),'utf8');
  await db.exec(migration);await db.exec(migration);
  assert.deepEqual(await state(),before);
  const actual=(await db.query("select enumlabel from pg_enum where enumtypid='public.source_type'::regtype order by enumsortorder")).rows.map(r=>r.enumlabel);
  assert.deepEqual(actual,[...old,'authorized_dealer_model_page','authorized_dealer_stock_page']);
  await db.exec('set role anon');
  await assert.rejects(db.query('select * from manufacturer_sources'));
  await db.exec('reset role');
  console.log(JSON.stringify({source_enum_alignment_ok:true,legacy_schema_tested:true,idempotent:true,rows_views_privileges_unchanged:true,remote_writes:0,paid_calls:0}));
}finally{await db.close()}
