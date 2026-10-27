import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';

const read=name=>readFile(new URL('../'+name,import.meta.url),'utf8');
const migration=await read('database/migrations/020_price_only_refresh.sql');
const schema=await read('database/schema.sql');
assert(schema.includes(migration.trim()),'Fresh schema and migration must agree');
const db=new PGlite();
const url='https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660';
const hash='a'.repeat(64), freshHash='b'.repeat(64);
const expiry=new Date(Date.now()+14*86400000).toISOString().slice(0,10);
let rejected=0;
try {
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls; grant usage on schema public to anon,authenticated,service_role');
  await db.exec(schema.replace('create extension if not exists pgcrypto;',''));
  const model=(await db.query("insert into canonical_models(brand,model,normalized_brand,normalized_model,market_seen) values('Skoda','Enyaq','skoda','enyaq',true) returning *")).rows[0];
  const source=(await db.query("insert into manufacturer_sources(canonical_model_id,brand,model,source_type,url,content_hash,verified_at) values($1,'Skoda','Enyaq','price_list_pdf',$2,$3,now()-interval '80 days') returning *",[model.id,url,hash])).rows[0];
  const targets=[];
  for(const [i,motor] of ['85','85x','85x Sportline','RS'].entries()) {
    const name='Solid Edition '+motor,price=500000+i*50000;
    const variant=(await db.query("insert into canonical_model_variants(canonical_model_id,source_id,variant_name,price_sek,wltp_range_km,dc_charge_kw,source_url,source_hash,source_quote,validation_status,extraction_confidence) values($1,$2,$3,$4,572,185,$5,$6,'Synthetic historical technical evidence',$7,$8) returning *",[model.id,source.id,name,price,url,hash,i===3?'published_reviewed':'published',i===3?0.9:0.95])).rows[0];
    const money=new Intl.NumberFormat('sv-SE').format(price+1000).replaceAll('\u00a0',' ');
    const quote=`${motor} 286 572 155 0 ${i===2?'- ':i===3?'- - ':''}${money} kr${i<2?' - -':''}`;
    const proof={source_url:url,source_hash:freshHash,quote,scope:'exact_variant_row',row_label:motor,edition:'Škoda Enyaq Solid Edition'};
    const payload={adapter:'skoda_enyaq_price_private_v1',field_evidence:{price_sek:proof,price_type:{...proof,quote:'Erbjudandet är begränsat'},price_valid_until:{...proof,quote:'Gäller tom '+expiry}}};
    const draft=(await db.query("insert into extracted_variant_drafts(canonical_model_id,source_id,brand,model,variant_name,price_sek,price_type,price_valid_until,source_url,source_hash,source_quote,extraction_confidence,extraction_payload,validation_status,validation_errors) values($1,$2,'Skoda','Enyaq',$3,$4,'campaign_price',$5,$6,$7,$8,0.99,$9,'validated','[]') returning *",[model.id,source.id,name,price+1000,expiry,url,freshHash,`${proof.edition} | ${quote} | Erbjudandet är begränsat | Gäller tom ${expiry}`,JSON.stringify(payload)])).rows[0];
    targets.push({id:variant.id,draft_id:draft.id,expected_updated_at:variant.updated_at,expected_hash:hash});
  }
  const snapshot=async()=>(await db.query("select jsonb_build_object('variants',(select jsonb_agg(to_jsonb(v) order by v.id) from canonical_model_variants v),'sources',(select jsonb_agg(to_jsonb(s) order by s.id) from manufacturer_sources s),'drafts',(select jsonb_agg(to_jsonb(d) order by d.id) from extracted_variant_drafts d)) as value")).rows[0].value;
  const acl=async()=>(await db.query("select relname,relacl::text,relrowsecurity from pg_class where oid in ('canonical_model_variants'::regclass,'manufacturer_sources'::regclass,'extracted_variant_drafts'::regclass,'public_ev_variants'::regclass) order by relname")).rows;
  const beforeMigration=await snapshot(),beforeAcl=await acl();
  await db.exec('create view price_dependent_catalog as select id,wltp_range_km from public_ev_variants');
  await db.exec(migration);await db.exec(migration);
  assert.deepEqual(await snapshot(),beforeMigration,'Migration cannot change facts or verification dates');
  assert.deepEqual(await acl(),beforeAcl,'Migration cannot change table/view ACLs or RLS');
  assert.equal((await db.query('select count(*)::int n from price_dependent_catalog')).rows[0].n,4);
  for(const role of ['anon','authenticated']) {
    await db.exec(`set role ${role}`);
    await assert.rejects(db.query('select publish_skoda_price_refresh($1)',[{}]),e=>e.code==='42501');
    await assert.rejects(db.query('select price_source_hash from canonical_model_variants'),e=>e.code==='42501');
    await assert.rejects(db.query("update public_ev_variants set price_source_quote='bad'"),e=>['42501','55000'].includes(e.code));
    assert.equal((await db.query('select count(*)::int n from public_ev_variants')).rows[0].n,4);
    await db.exec('reset role');
  }
  const batch={adapter:'skoda_enyaq_price_private_v1',batch_id:'c'.repeat(64),source_id:source.id,source_hash:freshHash,expected_source_hash:hash,expected_source_updated_at:source.updated_at,final_url:url,fetched_at:new Date().toISOString(),targets};
  const call=async value=>(await db.query('select publish_skoda_price_refresh($1) value',[value])).rows[0].value;
  const reject=async value=>{const before=await snapshot();await assert.rejects(call(value));assert.deepEqual(await snapshot(),before,'Every failed batch must roll back all rows');rejected++;};
  await db.exec('set role service_role');
  for(const packet of [{},{...batch,targets:targets.slice(0,3)},{...batch,targets:[targets[0],targets[0],...targets.slice(2)]},
    {...batch,adapter:'general_refresh'},{...batch,final_url:'https://ev-database.org/'},{...batch,fetched_at:'2020-01-01T00:00:00Z'},
    {...batch,fetched_at:new Date(Date.now()+600000).toISOString()},{...batch,expected_source_hash:freshHash},
    {...batch,targets:targets.map((t,i)=>i===3?{...t,expected_hash:freshHash}:t)}])await reject(packet);
  const last=targets[3].draft_id;
  for(const [field,value]of [['validation_status','needs_review'],['source_quote',''],['price_sek',1000000],['price_type','list_price'],['wltp_range_km',500],['extraction_confidence',0.5],['price_valid_until','2020-01-01'],['extraction_payload',{}]]) {
    const previous=(await db.query(`select ${field} value from extracted_variant_drafts where id=$1`,[last])).rows[0].value;
    await db.query(`update extracted_variant_drafts set ${field}=$1 where id=$2`,[field==='extraction_payload'?JSON.stringify(value):value,last]);
    await reject(batch);
    await db.query(`update extracted_variant_drafts set ${field}=$1 where id=$2`,[field==='extraction_payload'?JSON.stringify(previous):previous,last]);
  }
  const originalPayload=(await db.query('select extraction_payload value from extracted_variant_drafts where id=$1',[last])).rows[0].value;
  for(const mutate of [p=>p.field_evidence.price_sek.row_label='85',p=>p.field_evidence.price_sek.source_hash=hash,
    p=>p.field_evidence.price_sek.quote=p.field_evidence.price_sek.quote.replace('651 000','551 000'),
    p=>p.field_evidence.price_sek.edition='Skoda Elroq',p=>p.field_evidence.price_type.quote='Listpris',
    p=>p.field_evidence.price_valid_until.quote='Gäller tom 2099-01-01']) {
    const payload=structuredClone(originalPayload);mutate(payload);
    await db.query('update extracted_variant_drafts set extraction_payload=$1 where id=$2',[JSON.stringify(payload),last]);await reject(batch);
  }
  await db.query('update extracted_variant_drafts set extraction_payload=$1 where id=$2',[JSON.stringify(originalPayload),last]);
  const before=await snapshot();
  assert.deepEqual(await call(batch),{published:4,already_applied:false,price_verified:true,specifications_reverified:false});
  const after=await snapshot();
  assert.deepEqual(after.sources,before.sources,'A price refresh cannot re-verify the technical source');
  const technical=row=>Object.fromEntries(Object.entries(row).filter(([name])=>!['price_sek','price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote','price_source_name','price_verified_at','price_refresh_batch_id','updated_at'].includes(name)));
  assert.deepEqual(after.variants.map(technical),before.variants.map(technical),'All technical facts, source hashes and review decisions are unchanged');
  assert.deepEqual(await call(batch),{published:4,already_applied:true,price_verified:true,specifications_reverified:false});
  assert.deepEqual(await snapshot(),after,'Replay must not change timestamps or evidence');
  const publicRows=(await db.query('select verified_at,source_hash,price_verified_at,price_source_hash,wltp_range_km,dc_charge_kw from public_ev_variants')).rows;
  assert(publicRows.every(row=>row.source_hash===hash&&row.price_source_hash===freshHash&&row.price_verified_at>row.verified_at&&row.wltp_range_km===572&&row.dc_charge_kw===185));
  await db.query('update canonical_model_variants set price_sek=price_sek+2000 where id=$1',[targets[0].id]);
  const replaced=(await db.query('select price_source_hash,price_verified_at,price_refresh_batch_id from canonical_model_variants where id=$1',[targets[0].id])).rows[0];
  assert.deepEqual(replaced,{price_source_hash:null,price_verified_at:null,price_refresh_batch_id:null},'Other price writers invalidate old price-only evidence');
  await reject(batch);
  await db.exec('reset role');
  console.log(JSON.stringify({price_refresh_contract_ok:true,rejected_batches:rejected,atomic_rollback:true,technical_facts_and_dates_preserved:true,migration_idempotent:true,public_roles_denied:true,replay_idempotent:true,replaced_price_evidence_invalidated:true,remote_requests:0,real_publications:0}));
}finally{await db.close();}
