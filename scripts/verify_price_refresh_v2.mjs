
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
const read=n=>readFile(new URL('../'+n,import.meta.url),'utf8');
const migration=await read('database/migrations/028_skoda_separate_price_proof.sql');
const rollback=await read('database/rollback/028_skoda_separate_price_proof.sql');
const schema=await read('database/schema.sql');
assert(schema.includes(migration.trim()),'Fresh schema must contain exact v2 migration');
const db=new PGlite();
const url='https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660';
const techUrl='https://www.skoda.se/modeller/enyaq/enyaq';
const technicalHash='a'.repeat(64), oldPriceHash='d'.repeat(64), freshHash='b'.repeat(64), oldBatch='e'.repeat(64);
const adapter='skoda_enyaq_price_separate_proof_v2';
const expiry=new Date(Date.now()+14*86400000).toISOString().slice(0,10);
const oldVerified=new Date(Date.now()-40*86400000).toISOString();
const oldProofFields=['price_source_url','price_source_hash','price_source_quote','price_source_name','price_verified_at','price_refresh_batch_id','price_sek','price_type','price_valid_until'];
const snapshot=async()=>(await db.query("select jsonb_build_object('variants',(select jsonb_agg(to_jsonb(v) order by v.id) from canonical_model_variants v),'sources',(select jsonb_agg(to_jsonb(s) order by s.id) from manufacturer_sources s),'drafts',(select jsonb_agg(to_jsonb(d) order by d.id) from extracted_variant_drafts d),'models',(select jsonb_agg(to_jsonb(m) order by m.id) from canonical_models m)) as value")).rows[0].value;
const acl=async()=>(await db.query("select relname,relacl::text,relrowsecurity from pg_class where oid in ('canonical_model_variants'::regclass,'manufacturer_sources'::regclass,'extracted_variant_drafts'::regclass,'public_ev_variants'::regclass) order by relname")).rows;
const v1Definition=async()=>(await db.query("select pg_get_functiondef('publish_skoda_price_refresh(jsonb)'::regprocedure) as def")).rows[0].def;
const call=async value=>(await db.query('select publish_skoda_price_refresh_v2($1) value',[value])).rows[0].value;
let rejected=0;
try{
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls; grant usage on schema public to anon,authenticated,service_role');
  await db.exec(schema.replace('create extension if not exists pgcrypto;',''));
  const model=(await db.query("insert into canonical_models(brand,model,normalized_brand,normalized_model,market_seen) values('Skoda','Enyaq','skoda','enyaq',true) returning *")).rows[0];
  const priceSource=(await db.query("insert into manufacturer_sources(canonical_model_id,brand,model,source_type,url,content_hash,verified_at,source_authority) values($1,'Skoda','Enyaq','price_list_pdf',$2,$3,now()-interval '80 days','manufacturer') returning to_jsonb(manufacturer_sources) as r",[model.id,url,oldPriceHash])).rows[0].r;
  const techSource=(await db.query("insert into manufacturer_sources(canonical_model_id,brand,model,source_type,url,content_hash,verified_at,source_authority) values($1,'Skoda','Enyaq','model_page',$2,$3,now()-interval '3 days','manufacturer') returning *",[model.id,techUrl,technicalHash])).rows[0];
  const other=(await db.query("insert into canonical_models(brand,model,normalized_brand,normalized_model) values('Other','BEV','other','bev') returning *")).rows[0];
  const otherSource=(await db.query("insert into manufacturer_sources(canonical_model_id,brand,model,source_type,url,content_hash) values($1,'Other','BEV','model_page','https://example.invalid/specs',$2) returning *",[other.id,technicalHash])).rows[0];
  await db.query("insert into canonical_model_variants(canonical_model_id,source_id,variant_name,price_sek,wltp_range_km,source_url,source_hash,source_quote,validation_status,extraction_confidence) values($1,$2,'Unrelated',500000,500,'https://example.invalid/specs',$3,'Synthetic unrelated evidence','published',0.95)",[other.id,otherSource.id,technicalHash]);
  const targets=[];
  for(const [i,motor] of ['85','85x','85x Sportline','RS'].entries()){
    const name='Solid Edition '+motor,price=500000+i*50000;
    const quote=motor+' 286 572 155 0 '+(i===2?'- ':i===3?'- - ':'')+Math.floor(price/1000)+' 000 kr'+(i<2?' - -':'');
    const previousQuote='Škoda Enyaq Solid Edition | '+quote+' | Erbjudandet är begränsat | Gäller tom '+expiry;
    const variant=(await db.query("insert into canonical_model_variants(canonical_model_id,source_id,variant_name,price_sek,price_type,price_valid_until,wltp_range_km,dc_charge_kw,source_url,source_hash,source_quote,validation_status,extraction_confidence,price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id) values($1,$2,$3,$4,'campaign_price',$5,572,185,$6,$7,'Synthetic exact technical evidence',$8,$9,$10,$11,$12,'Skoda Sverige',$13,$14) returning to_jsonb(canonical_model_variants) as r",[model.id,techSource.id,name,price,expiry,techUrl,technicalHash,i===3?'published_reviewed':'published',i===3?0.9:0.95,url,oldPriceHash,previousQuote,oldVerified,oldBatch])).rows[0].r;
    const proof={source_url:url,source_hash:freshHash,quote,scope:'exact_variant_row',row_label:motor,edition:'Škoda Enyaq Solid Edition'};
    const payload={adapter,field_evidence:{price_sek:proof,price_type:{...proof,quote:'Erbjudandet är begränsat'},price_valid_until:{...proof,quote:'Gäller tom '+expiry}}};
    const draft=(await db.query("insert into extracted_variant_drafts(canonical_model_id,source_id,brand,model,variant_name,price_sek,price_type,price_valid_until,source_url,source_hash,source_quote,extraction_confidence,extraction_payload,validation_status,validation_errors) values($1,$2,'Skoda','Enyaq',$3,$4,'campaign_price',$5,$6,$7,$8,0.99,$9,'validated','[]') returning *",[model.id,priceSource.id,name,price,expiry,url,freshHash,previousQuote,JSON.stringify(payload)])).rows[0];
    targets.push({id:variant.id,draft_id:draft.id,expected_updated_at:variant.updated_at,expected_hash:technicalHash,expected_technical_source_id:techSource.id,expected_technical_source_url:techUrl,expected_price:Object.fromEntries(oldProofFields.map(k=>[k,variant[k]]))});
  }
  const beforeMigration=await snapshot(), beforeAcl=await acl(), oldV1=await v1Definition();
  await db.exec(rollback);assert.deepEqual(await snapshot(),beforeMigration);
  await db.exec(migration);await db.exec(migration);
  assert.deepEqual(await snapshot(),beforeMigration,'Installing v2 must not write any data');
  assert.deepEqual(await acl(),beforeAcl,'Existing ACLs and RLS stay unchanged');
  assert.equal(await v1Definition(),oldV1,'Legacy publisher remains unchanged');
  for(const role of ['anon','authenticated']){
    await db.exec('set role '+role);
    await assert.rejects(db.query('select skoda_price_refresh_contract_v2()'),e=>e.code==='42501');
    await assert.rejects(call({}),e=>e.code==='42501');
    await db.exec('reset role');
  }
  await db.exec('set role service_role');
  assert.deepEqual((await db.query('select skoda_price_refresh_contract_v2() value')).rows[0].value,{contract:adapter,publisher:'publish_skoda_price_refresh_v2'});
  const batch={adapter,batch_id:'c'.repeat(64),source_id:priceSource.id,source_hash:freshHash,expected_source_hash:oldPriceHash,expected_source_updated_at:priceSource.updated_at,final_url:url,fetched_at:new Date().toISOString(),targets};
  const reject=async packet=>{const before=await snapshot();await assert.rejects(call(packet));assert.deepEqual(await snapshot(),before,'Rejected v2 packet must roll back every row');rejected++;};
  const beforeLegacy=await snapshot();
  await assert.rejects(db.query('select publish_skoda_price_refresh($1)',[{...batch,adapter:'skoda_enyaq_price_private_v1'}]),/Incomplete price source group/);
  assert.deepEqual(await snapshot(),beforeLegacy);
  for(const packet of [{},{...batch,targets:targets.slice(0,3)},{...batch,targets:[targets[0],targets[0],...targets.slice(2)]},{...batch,adapter:'skoda_enyaq_price_private_v1'},{...batch,final_url:techUrl},{...batch,source_id:techSource.id},{...batch,fetched_at:'2020-01-01T00:00:00Z'},{...batch,fetched_at:new Date(Date.now()+600000).toISOString()},{...batch,expected_source_hash:freshHash}] )await reject(packet);
  const late=[...targets].sort((a,b)=>a.id.localeCompare(b.id)).at(-1);
  const withLate=patch=>({...batch,targets:targets.map(t=>t.id===late.id?{...t,...patch}:t)});
  for(const patch of [{expected_hash:freshHash},{expected_technical_source_id:priceSource.id},{expected_technical_source_url:url},{expected_updated_at:'2020-01-01T00:00:00Z'},{expected_price:null},...oldProofFields.map(k=>({expected_price:{...late.expected_price,[k]:null}})),{expected_price:{...late.expected_price,price_source_hash:freshHash}},{expected_price:{...late.expected_price,price_source_quote:'different'}},{expected_price:{...late.expected_price,price_verified_at:'2020-01-01T00:00:00Z'}}])await reject(withLate(patch));
  for(const [field,value] of [['price_sek',499999],['price_type','list_price'],['price_valid_until','2099-01-01'],['wltp_range_km',500],['validation_status','needs_review'],['extraction_confidence',0.5],['source_quote','']]){
    const old=(await db.query('select '+field+' value from extracted_variant_drafts where id=$1',[late.draft_id])).rows[0].value;
    await db.query('update extracted_variant_drafts set '+field+'=$1 where id=$2',[value,late.draft_id]);
    await reject(batch);
    await db.query('update extracted_variant_drafts set '+field+'=$1 where id=$2',[old,late.draft_id]);
  }
  const oldPayload=(await db.query('select extraction_payload value from extracted_variant_drafts where id=$1',[late.draft_id])).rows[0].value;
  for(const mut of [p=>p.field_evidence.price_sek.source_hash=oldPriceHash,p=>p.field_evidence.price_sek.row_label='wrong',p=>p.field_evidence.price_type.quote='Listpris',p=>p.field_evidence.price_valid_until.quote='Gäller tom 2099-01-01']){
    const v=structuredClone(oldPayload);mut(v);await db.query('update extracted_variant_drafts set extraction_payload=$1 where id=$2',[JSON.stringify(v),late.draft_id]);await reject(batch);
  }
  await db.query('update extracted_variant_drafts set extraction_payload=$1 where id=$2',[JSON.stringify(oldPayload),late.draft_id]);
  // Wrong/missing existing price binding must fail even with a matching technical source and complete group.
  const oldRow=(await db.query('select to_jsonb(v) r from canonical_model_variants v where id=$1',[late.id])).rows[0].r;
  await db.query("update canonical_model_variants set price_source_url=$1 where id=$2",[techUrl,late.id]);await reject(batch);
  await db.query('update canonical_model_variants set price_source_url=$1 where id=$2',[url,late.id]);
  await db.query("update canonical_model_variants set price_source_url=null,price_source_hash=null,price_source_quote=null,price_source_name=null,price_verified_at=null,price_refresh_batch_id=null where id=$1",[late.id]);await reject(batch);
  await db.query('update canonical_model_variants set price_source_url=$1,price_source_hash=$2,price_source_quote=$3,price_source_name=$4,price_verified_at=$5,price_refresh_batch_id=$6 where id=$7',[...oldProofFields.slice(0,6).map(k=>oldRow[k]),late.id]);
  const extra=(await db.query("insert into canonical_model_variants(canonical_model_id,source_id,variant_name,price_sek,wltp_range_km,source_url,source_hash,source_quote,validation_status,extraction_confidence) values($1,$2,'Unexpected extra variant',500000,500,$3,$4,'Synthetic unexpected row','published',0.95) returning id",[model.id,techSource.id,techUrl,technicalHash])).rows[0].id;
  await reject(batch);await db.query('delete from canonical_model_variants where id=$1',[extra]);
  const before=await snapshot();
  assert.deepEqual(await call(batch),{published:4,already_applied:false,price_verified:true,specifications_reverified:false});
  const after=await snapshot();
  assert.deepEqual(after.sources,before.sources);assert.deepEqual(after.models,before.models);
  const targetIds=new Set(targets.map(t=>t.id));
  for(const row of after.variants){
    const old=before.variants.find(v=>v.id===row.id);
    if(!targetIds.has(row.id)){assert.deepEqual(row,old);continue;}
    const allowed=new Set(['price_source_hash','price_source_quote','price_verified_at','price_refresh_batch_id','updated_at']);
    for(const k of Object.keys(row))if(!allowed.has(k))assert.deepEqual(row[k],old[k],k+' changed');
    assert.equal(row.price_source_hash,freshHash);assert.equal(Date.parse(row.price_verified_at),Date.parse(batch.fetched_at));
  }
  assert.deepEqual(await call(batch),{published:4,already_applied:true,price_verified:true,specifications_reverified:false});
  assert.deepEqual(await snapshot(),after,'Exact replay does not touch timestamps');
  await db.exec('reset role');await db.exec(rollback);
  assert.deepEqual(await snapshot(),after,'Code rollback does not undo approved data');
  assert.equal(await v1Definition(),oldV1);
  assert.equal((await db.query("select to_regprocedure('publish_skoda_price_refresh_v2(jsonb)') is null gone")).rows[0].gone,true);
  console.log(JSON.stringify({separate_price_proof_contract_ok:true,rejected_batches:rejected,late_rollback:true,legacy_route_rejected_separate_binding:true,migration_idempotent:true,role_boundary:true,technical_provenance_preserved:true,unrelated_rows_preserved:true,replay_idempotent:true,code_rollback:true,remote_requests:0,real_publications:0}));
}finally{await db.close();}

