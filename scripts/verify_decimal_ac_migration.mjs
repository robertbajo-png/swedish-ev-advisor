import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
const sql=await readFile('database/migrations/023_decimal_ac_charging.sql','utf8');
async function fixture(){
 const db=new PGlite();await db.exec(`CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role;
 CREATE TABLE canonical_model_variants(id int primary key,ac_charge_kw int,validation_status text);
 CREATE TABLE extracted_variant_drafts(id int primary key,ac_charge_kw int);
 ALTER TABLE canonical_model_variants ENABLE ROW LEVEL SECURITY;
 ALTER TABLE extracted_variant_drafts ENABLE ROW LEVEL SECURITY;
 CREATE POLICY no_direct_read ON canonical_model_variants FOR SELECT TO anon USING(false);
 CREATE VIEW public_ev_variants WITH(security_barrier=true) AS SELECT id,ac_charge_kw FROM canonical_model_variants WHERE validation_status='published';
 REVOKE ALL ON canonical_model_variants,extracted_variant_drafts FROM PUBLIC,anon,authenticated;
 GRANT SELECT ON public_ev_variants TO anon,authenticated;
 GRANT SELECT ON public_ev_variants TO service_role WITH GRANT OPTION;
 COMMENT ON VIEW public_ev_variants IS 'Existing catalog';
 INSERT INTO canonical_model_variants VALUES(1,11,'published'),(2,null,'published'),(3,22,'draft');
 INSERT INTO extracted_variant_drafts VALUES(1,11),(2,null);`);return db;
}
const db=await fixture();
try{
 const old=(await db.query('select * from public_ev_variants order by id')).rows;
 await db.exec(sql);assert.deepEqual((await db.query('select * from public_ev_variants order by id')).rows.map(r=>({...r,ac_charge_kw:r.ac_charge_kw==null?null:Number(r.ac_charge_kw)})),old);
 await db.exec(sql);
 await db.exec('update canonical_model_variants set ac_charge_kw=10.5 where id=2;update extracted_variant_drafts set ac_charge_kw=10.5 where id=2');
 assert.equal(Number((await db.query('select ac_charge_kw from public_ev_variants where id=2')).rows[0].ac_charge_kw),10.5);
 assert.equal(Number((await db.query('select ac_charge_kw from extracted_variant_drafts where id=2')).rows[0].ac_charge_kw),10.5);
 await db.exec('set role anon');assert.equal((await db.query('select * from public_ev_variants')).rows.length,2);
 await assert.rejects(db.query('select * from canonical_model_variants'));await db.exec('reset role');
 const boundary=(await db.query("select relrowsecurity from pg_class where oid='canonical_model_variants'::regclass")).rows[0];assert(boundary.relrowsecurity);
}finally{await db.close();}
for(const extra of ['CREATE VIEW unexpected_dependent AS SELECT * FROM public_ev_variants',
 'CREATE FUNCTION unexpected_typed_function() RETURNS SETOF public_ev_variants LANGUAGE sql AS $$ SELECT * FROM public_ev_variants $$',
 'GRANT SELECT(ac_charge_kw) ON public_ev_variants TO anon']){
 const db=await fixture();try{
  await db.exec(extra);await assert.rejects(db.exec(sql));await db.exec('rollback');
  const type=(await db.query("select data_type from information_schema.columns where table_name='canonical_model_variants' and column_name='ac_charge_kw'")).rows[0];
  assert.equal(type.data_type,'integer');assert.equal((await db.query('select count(*) n from public_ev_variants')).rows[0].n,2);
 }finally{await db.close();}
}
console.log(JSON.stringify({decimal_ac_migration:'passed',facts_and_grants_preserved:true,rls_preserved:true,
 decimal_roundtrip:10.5,idempotent:true,dependency_and_metadata_rollback:true,production_writes:0,paid_calls:0}));
