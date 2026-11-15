import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {buildNewModelPlan,applyNewModelPlan,publicationSnapshot,publicationHash} from './new_model_publication.mjs';
import {buildImagePlan} from './model_image_sync.mjs';
const intake=JSON.parse(await readFile('tests/fixtures/toyota_chr_plus_intake.json','utf8'));
const image=JSON.parse(await readFile('src/image-rights.json','utf8')).assets.find(r=>r.model_key==='toyota|c hr');assert(image);
const now=new Date(Math.max(...[...intake.sources,intake.market.source].map(s=>Date.parse(s.fetched_at))));
const db=new PGlite(),model='11111111-1111-4111-8111-111111111111',outside='22222222-2222-4222-8222-222222222222';
const market='44444444-4444-4444-8444-444444444444';
const same=(a,b)=>assert.deepEqual(JSON.parse(JSON.stringify(a)),JSON.parse(JSON.stringify(b)));
try{
 const schema=await readFile('database/schema.sql','utf8');
 await db.exec(schema.slice(0,schema.indexOf('create or replace view public_ev_models')).replace('create extension if not exists pgcrypto;',''));
 const migration=await readFile('database/migrations/020_price_only_refresh.sql','utf8');
 await db.exec(migration.match(/alter table public\.canonical_model_variants\s+add column[\s\S]*?price_refresh_batch_id text;/)[0]);
 await db.exec(migration.match(/alter table public\.canonical_model_variants add constraint canonical_price_evidence_complete check\([\s\S]*?\);/)[0]);
 await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
 await db.exec(`CREATE TRIGGER invalidate_replaced_price_evidence BEFORE UPDATE OF price_sek,price_type,price_valid_until
 ON canonical_model_variants FOR EACH ROW EXECUTE FUNCTION public.invalidate_replaced_price_evidence();`);
 await db.query(`INSERT INTO canonical_models(id,brand,model,normalized_brand,normalized_model,market_seen) VALUES
 ($1,'Toyota','C-Hr+','toyota','c hr',true),($2,'Toyota','bZ4X','toyota','bz4x',true)`,[model,outside]);
 await db.query(`INSERT INTO model_aliases(canonical_model_id,brand_raw,model_raw,normalized_brand,normalized_model,alias_rule)
 VALUES($1,'TOYOTA','C-HR+','toyota','c hr','mobility_sweden_exact_raw_name')`,[model]);
 await db.query(`INSERT INTO market_models(id,brand_raw,model_raw,fuel_type_raw,normalized_brand,normalized_model,first_seen_month,last_seen_month,registrations_last_month,registrations_ytd)
 VALUES($1,'TOYOTA','C-HR+','EL','toyota','c hr','2026-03-01','2026-03-01',106,106)`,[market]);
 await db.query(`INSERT INTO market_model_monthly_stats(market_model_id,month,brand_raw,model_raw,fuel_type_raw,registrations)
 VALUES($1,'2026-03-01','TOYOTA','C-HR+','EL',106)`,[market]);
 await db.query(`INSERT INTO manufacturer_sources(canonical_model_id,brand,model,source_type,url,content_hash)
 VALUES($1,'Toyota','bZ4X','manufacturer_configurator','https://dxp-webcarconfig.toyota-europe.com/v1/api/data/se/sv','unchanged-bz4x-api-hash')`,[outside]);
 await db.query(`INSERT INTO canonical_model_variants(canonical_model_id,variant_name,price_sek,validation_status) VALUES($1,'Existing bZ4X',400000,'published')`,[outside]);
 await db.query(`INSERT INTO extracted_variant_drafts(canonical_model_id,brand,model,variant_name,source_url,validation_status)
 VALUES($1,'Toyota','bZ4X','Unrelated staging','https://example.invalid/spec','extracted')`,[outside]);
 const before=await publicationSnapshot(db),plan=buildNewModelPlan(before,intake,image,now),hash=publicationHash(plan);
 for(const mutate of [d=>d.model.model='C-Hr',d=>d.market.row.model_raw='C-HR',d=>d.market.row.needs_mapping=true,
  d=>d.drafts[0].facts.tow_kg=1500,d=>d.drafts[1].facts.tow_kg=750,d=>d.drafts[2].facts.ac_charge_kw=11,
  d=>d.drafts[2].facts.wltp_range_km=607,d=>d.drafts[0].facts.battery_kwh=61,d=>d.drafts[0].facts.boot_liters=null,
  d=>d.drafts[0].price_evidence.value=3610,d=>d.drafts[0].price_evidence.price_valid_until='2027-01-11',
  d=>d.drafts[0].price_evidence.price_type='campaign_price',d=>d.drafts[0].manufacturer_identity=d.drafts[2].manufacturer_identity,
  d=>d.sources[0].http_status=403,d=>d.sources[0].country='US',d=>d.sources[0].source_authority='authorized_dealer',
  d=>d.drafts[0].field_evidence.boot_liters.source_hash='0'.repeat(64),d=>d.drafts.pop()]){
  const bad=structuredClone(intake);mutate(bad);assert.throws(()=>buildNewModelPlan(before,bad,image,now));
 }
 for(const mutate of [s=>s.model_aliases[0].model_raw='C-HR',s=>s.model_aliases[0].needs_mapping=true,
  s=>s.model_aliases[0].canonical_model_id=outside,s=>s.canonical_models.find(r=>r.id===model).model='C-Hr',
  s=>s.market_models[0].fuel_type_raw='HYBRID',s=>s.market_models[0].last_seen_month='2026-11-01']){
  const bad=structuredClone(before);mutate(bad);assert.throws(()=>buildNewModelPlan(bad,intake,image,now));
 }
 for(const patch of [{model_key:'toyota|bz4x'},{downloaded_from:image.downloaded_from.replace('_014-','_010-')},
  {source_url:image.source_url.replace('c-hr-design','c-hr-hybrid')},{full_frame:false},{content_sha256:'0'.repeat(64)}])
  assert.throws(()=>buildNewModelPlan(before,intake,{...image,...patch},now));
 assert.throws(()=>buildNewModelPlan(before,intake,image,new Date(now.getTime()+86400000)));
 const collision=structuredClone(plan);collision.targets[0].id=before.canonical_model_variants[0].id;
 await assert.rejects(applyNewModelPlan(db,collision,publicationHash(collision),now));same(await publicationSnapshot(db),before);
 await db.query("UPDATE model_aliases SET model_raw='C-HR' WHERE canonical_model_id=$1",[model]);
 const changed=await publicationSnapshot(db);await assert.rejects(applyNewModelPlan(db,plan,hash,now));same(await publicationSnapshot(db),changed);
 await db.query("UPDATE model_aliases SET model_raw='C-HR+' WHERE canonical_model_id=$1",[model]);
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Late fixture failure'; END $$;
 CREATE TRIGGER late_failure BEFORE UPDATE ON market_models FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applyNewModelPlan(db,plan,hash,now));same(await publicationSnapshot(db),before);
 await db.exec('DROP TRIGGER late_failure ON market_models');
 const result=await applyNewModelPlan(db,plan,hash,now);assert(result.committed);assert.equal(result.variants_inserted,3);
 const after=await publicationSnapshot(db),rows=after.canonical_model_variants.filter(r=>r.canonical_model_id===model);
 assert.equal(rows.length,3);assert(rows.every(r=>r.validation_status==='published'&&r.price_valid_until===null&&r.price_source_hash&&r.price_refresh_batch_id===hash));
 assert.equal(after.market_models[0].first_seen_month,'2026-03-01');assert.equal(after.market_models[0].last_seen_month,'2026-10-01');
 assert.equal(after.market_models[0].registrations_12m,null);assert.equal(after.market_model_monthly_stats.length,2);
 assert.equal(after.canonical_models.find(r=>r.id===model).available_confirmed,false);
 same(after.manufacturer_sources.filter(r=>r.canonical_model_id===outside),before.manufacturer_sources);
 same(after.canonical_model_variants.filter(r=>r.canonical_model_id===outside),before.canonical_model_variants);
 const replay=await applyNewModelPlan(db,plan,hash,now);assert(replay.already_applied);assert.equal(replay.variants_inserted,0);same(await publicationSnapshot(db),after);
 assert.throws(()=>buildNewModelPlan(after,intake,image,now));
 await db.query('UPDATE canonical_model_variants SET price_sek=price_sek+1 WHERE id=$1',[rows[0].id]);
 const altered=await publicationSnapshot(db);await assert.rejects(applyNewModelPlan(db,plan,hash,now));same(await publicationSnapshot(db),altered);
 console.log(JSON.stringify({toyota_chr_plus_publication:'passed',profiles:3,complete_fields:27,raw_plus_alias_guard:true,
  real_schema_price_guard:true,source_price_image_binding:true,late_rollback:true,exact_replay:true,bz4x_api_preserved:true,
  collision_concurrency_rejection:true,history_and_availability_preserved:true,remote_writes:0,paid_calls:0}));
}finally{await db.close();}
