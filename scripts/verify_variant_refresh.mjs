import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';

const read = (path) => readFile(new URL('../' + path, import.meta.url), 'utf8');
const db = new PGlite();
const url = 'https://www.polestar.com/se/polestar-2/specifications/';
const oldHash = 'a'.repeat(64), newHash = 'b'.repeat(64);
try {
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls; grant usage on schema public to anon,authenticated,service_role');
  await db.exec((await read('database/schema.sql')).replace('create extension if not exists pgcrypto;', ''));
  const model = (await db.query("insert into canonical_models(brand,model,normalized_brand,normalized_model) values ('Polestar','2','polestar','2') returning *")).rows[0];
  const source = (await db.query("insert into manufacturer_sources(canonical_model_id,brand,model,source_type,url,content_hash) values ($1,'Polestar','2','specs_page',$2,$3) returning *", [model.id,url,oldHash])).rows[0];
  const targets = [];
  for (const [name,price] of [['Alpha',510000],['Beta',610000]]) {
    const variant = (await db.query("insert into canonical_model_variants(canonical_model_id,variant_name,price_sek,wltp_range_km,source_url,source_hash,validation_status) values ($1,$2,$3,600,$4,$5,'published') returning *", [model.id,name,price,url,oldHash])).rows[0];
    const proof = { source_url:url,source_hash:newHash,quote:'Synthetic test evidence',scope:'variant_column',column_header:name };
    const payload = {adapter:'polestar_table_v1',field_evidence:{price_sek:proof,wltp_range_km:proof}};
    const draft = (await db.query("insert into extracted_variant_drafts(canonical_model_id,source_id,brand,model,variant_name,price_sek,wltp_range_km,source_url,source_hash,source_quote,extraction_confidence,extraction_payload,validation_status,validation_errors) values ($1,$2,'Polestar','2',$3,$4,600,$5,$6,'Synthetic test evidence',0.99,$7,'validated','[]') returning *",[model.id,source.id,name,price+1000,url,newHash,JSON.stringify(payload)])).rows[0];
    targets.push({id:variant.id,draft_id:draft.id,expected_updated_at:variant.updated_at,expected_hash:oldHash});
  }
  const privateAcl = () => db.query("select relname,relacl::text,relrowsecurity from pg_class where oid in ('canonical_models'::regclass,'canonical_model_variants'::regclass,'extracted_variant_drafts'::regclass,'manufacturer_sources'::regclass) order by relname");
  const beforeAcl = (await privateAcl()).rows;
  const migration = await read('database/migrations/010_atomic_variant_refresh.sql');
  assert((await read('database/schema.sql')).includes(migration.trim()),'Fresh schema uses the same refresh function');
  await db.exec(migration);
  await db.exec(migration);
  assert.deepEqual((await privateAcl()).rows,beforeAcl,'Migration preserves table ACLs and RLS');
  for (const role of ['anon','authenticated']) {
    await db.exec(`set role ${role}`);
    await assert.rejects(db.query('select public.publish_variant_refresh($1)',[{}]),e=>e.code==='42501');
    await assert.rejects(db.query('select * from extracted_variant_drafts'),e=>e.code==='42501');
    await db.exec('reset role');
  }
  const batch = {adapter:'polestar_table_v1',batch_id:'c'.repeat(64),source_id:source.id,source_hash:newHash,
    expected_source_hash:oldHash,expected_source_updated_at:source.updated_at,final_url:url,fetched_at:new Date().toISOString(),targets};
  const snapshot = async () => (await db.query(`select jsonb_build_object('variants',(select jsonb_agg(to_jsonb(v) order by v.id) from canonical_model_variants v),
    'sources',(select jsonb_agg(to_jsonb(s)) from manufacturer_sources s),'drafts',(select jsonb_agg(to_jsonb(d) order by d.id) from extracted_variant_drafts d)) as data`)).rows[0].data;
  const call = async (packet) => (await db.query('select public.publish_variant_refresh($1) as result',[packet])).rows[0].result;
  await db.exec('set role service_role');
  for (const packet of [ {...batch,targets:targets.slice(0,1)}, {...batch,targets:[targets[0],targets[0]]},
    {...batch,fetched_at:'2020-01-01T00:00:00Z'}, {...batch,final_url:'https://ev-database.org/'},
    {...batch,expected_source_hash:newHash}, {...batch,targets:targets.map((t,i)=>i?{...t,expected_hash:newHash}:t)} ]) {
    const before = await snapshot();
    await assert.rejects(call(packet));
    assert.deepEqual(await snapshot(),before,'All-or-nothing rollback, including late conflicts');
  }
  const lastDraft = targets[1].draft_id;
  for (const [field,value] of [['validation_status','needs_review'],['source_quote',''],['price_sek',1000000],['wltp_range_km',null],['extraction_confidence',0.5],['extraction_payload',{}]]) {
    const original = (await db.query(`select ${field} as value from extracted_variant_drafts where id=$1`,[lastDraft])).rows[0].value;
    await db.query(`update extracted_variant_drafts set ${field}=$1 where id=$2`,[field==='extraction_payload'?JSON.stringify(value):value,lastDraft]);
    const before = await snapshot();
    await assert.rejects(call(batch));
    assert.deepEqual(await snapshot(),before,'Rejected draft cannot partially publish');
    await db.query(`update extracted_variant_drafts set ${field}=$1 where id=$2`,[field==='extraction_payload'?JSON.stringify(original):original,lastDraft]);
  }
  const flags = (await db.query('select market_seen,available_confirmed,discontinued_candidate,coming_or_low_volume from canonical_models')).rows;
  assert.deepEqual(await call(batch),{published:2,already_applied:false,source_verified:true});
  const applied = await snapshot();
  assert.deepEqual(await call(batch),{published:2,already_applied:true,source_verified:true});
  assert.deepEqual(await snapshot(),applied,'Replay does not change values or timestamps');
  assert.deepEqual((await db.query('select market_seen,available_confirmed,discontinued_candidate,coming_or_low_volume from canonical_models')).rows,flags);
  const publicRows = (await db.query('select price_sek,verified_at,source_hash from public_ev_variants order by price_sek')).rows;
  assert.deepEqual(publicRows.map(r=>r.price_sek),[511000,611000]);
  assert(publicRows.every(r=>r.verified_at && r.source_hash===newHash));
  await db.exec('reset role');
  console.log(JSON.stringify({variant_refresh_ok:true,transactional_rollback:true,staging_required:true,exact_source_group:true,
    optimistic_concurrency:true,idempotent:true,unchanged_market_flags:true,public_roles_denied:true,remote_requests:0}));
} finally {await db.close();}
