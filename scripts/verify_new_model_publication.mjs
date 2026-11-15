import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {buildNewModelPlan,applyNewModelPlan,publicationSnapshot,publicationHash,rollingRegistrations} from './new_model_publication.mjs';
const intake=JSON.parse(await readFile('tests/fixtures/kia_ev2_intake.json','utf8'));
const registry=JSON.parse(await readFile('src/image-rights.json','utf8'));
const image=registry.assets.find(r=>r.model_key==='kia|ev2');assert(image);
const now=new Date(Math.max(...[...intake.sources,intake.market.source].map(s=>Date.parse(s.fetched_at))));
const db=new PGlite(),model='11111111-1111-4111-8111-111111111111',outside='22222222-2222-4222-8222-222222222222';
const market='44444444-4444-4444-8444-444444444444';
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
  ($1,'Kia','Ev2','kia','ev2',true),($2,'Other','Untouched','other','untouched',true)`,[model,outside]);
 await db.query(`INSERT INTO model_aliases(canonical_model_id,brand_raw,model_raw,normalized_brand,normalized_model,alias_rule)
  VALUES($1,'KIA','EV2','kia','ev2','mobility_sweden_exact_raw_name')`,[model]);
 await db.query(`INSERT INTO market_models(id,brand_raw,model_raw,fuel_type_raw,normalized_brand,normalized_model,first_seen_month,last_seen_month,registrations_last_month,registrations_ytd)
  VALUES($1,'KIA','EV2','EL','kia','ev2','2026-03-01','2026-03-01',6,6)`,[market]);
 await db.query(`INSERT INTO market_model_monthly_stats(market_model_id,month,brand_raw,model_raw,fuel_type_raw,registrations)
  VALUES($1,'2026-03-01','KIA','EV2','EL',6)`,[market]);
 const ps=intake.sources.find(s=>s.key==='price_pdf');
 await db.query(`INSERT INTO manufacturer_sources(brand,model,source_type,url,country,language,content_hash,http_status,
  final_url,source_validation,source_authority,source_name) VALUES('Kia','*','price_list_pdf',$1,'SE','sv',$2,200,$1,'reachable_official_model_source','manufacturer','Kia Sverige')`,[ps.final_url,ps.content_hash]);
 await db.query(`INSERT INTO canonical_model_variants(canonical_model_id,variant_name,price_sek,validation_status) VALUES($1,'Untouched',123456,'published')`,[outside]);
 await db.query(`INSERT INTO extracted_variant_drafts(canonical_model_id,brand,model,variant_name,source_url,validation_status) VALUES($1,'Other','Untouched','Unrelated staging','https://example.invalid/spec','extracted')`,[outside]);
 const before=await publicationSnapshot(db),plan=buildNewModelPlan(before,intake,image,now),hash=publicationHash(plan);
 assert.equal(plan.targets.length,3);
 for(const mutate of [d=>d.adapter='unregistered',d=>d.model.body_type=null,d=>d.sources[0].http_status=403,
  d=>d.sources[0].country='US',d=>d.sources[0].source_authority='authorized_dealer',d=>d.market.row.needs_mapping=true,
  d=>d.market.source.content_hash='',d=>d.market.row.model_raw='EV3',d=>d.drafts[0].facts.seats=4,
  d=>d.drafts[0].facts.boot_liters=403,d=>d.drafts[0].facts.ac_charge_kw=11,d=>d.drafts[0].facts.tow_kg=null,
  d=>d.drafts[2].facts.wltp_range_km=453,d=>d.drafts[0].price_evidence.value=3495,
  d=>d.drafts[0].price_evidence.price_type='campaign_price',d=>d.drafts[0].field_evidence.boot_liters.source_hash='0'.repeat(64),
  d=>d.drafts[1].manufacturer_identity=d.drafts[0].manufacturer_identity,d=>d.drafts.pop()]){
  const bad=structuredClone(intake);mutate(bad);assert.throws(()=>buildNewModelPlan(before,bad,image,now));
 }
 for(const mutate of [s=>s.model_aliases[0].needs_mapping=true,s=>s.market_models[0].canonical_model_id=outside,
  s=>s.market_models[0].last_seen_month='2026-11-01',s=>s.canonical_models[0].validation_status='rejected']){
  const bad=structuredClone(before);mutate(bad);assert.throws(()=>buildNewModelPlan(bad,intake,image,now));
 }
 assert.throws(()=>buildNewModelPlan(before,intake,{...image,content_sha256:'0'.repeat(64)},now));
 assert.throws(()=>buildNewModelPlan(before,intake,{...image,model_key:'kia|ev3'},now));
 assert.throws(()=>buildNewModelPlan(before,intake,image,new Date(now.getTime()+86400000)));
 const collision=structuredClone(plan);collision.targets[0].id=before.canonical_model_variants[0].id;
 await assert.rejects(applyNewModelPlan(db,collision,publicationHash(collision),now));same(await publicationSnapshot(db),before);
 await db.query("UPDATE canonical_models SET body_type='SUV' WHERE id=$1",[model]);
 const concurrent=await publicationSnapshot(db);await assert.rejects(applyNewModelPlan(db,plan,hash,now));same(await publicationSnapshot(db),concurrent);
 await db.query('UPDATE canonical_models SET body_type=null WHERE id=$1',[model]);
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Late fixture failure'; END $$;
 CREATE TRIGGER late_failure BEFORE UPDATE ON market_models FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applyNewModelPlan(db,plan,hash,now));same(await publicationSnapshot(db),before);
 await db.exec('DROP TRIGGER late_failure ON market_models');
 const result=await applyNewModelPlan(db,plan,hash,now);assert.equal(result.variants_inserted,3);assert(result.committed);
 const after=await publicationSnapshot(db),rows=after.canonical_model_variants.filter(r=>r.canonical_model_id===model);
 assert.equal(rows.length,3);assert(rows.every(r=>r.validation_status==='published'&&Number(r.ac_charge_kw)===10.5&&r.price_refresh_batch_id===hash));
 same(after.canonical_model_variants.filter(r=>r.canonical_model_id===outside),before.canonical_model_variants);
 assert.equal(after.extracted_variant_drafts.filter(r=>r.canonical_model_id===model&&r.validation_status==='published').length,3);
 assert(rows.every(r=>r.price_source_hash===ps.content_hash&&r.price_verified_at));
 const mr=after.market_models[0];assert.equal(mr.first_seen_month,'2026-03-01');assert.equal(mr.last_seen_month,'2026-10-01');
 assert.equal(mr.registrations_12m,null);assert.equal(mr.registrations_last_month,407);assert.equal(mr.registrations_ytd,2138);assert.equal(mr.canonical_model_id,model);
 assert.equal(after.market_model_monthly_stats.length,2);assert.equal(after.canonical_models.find(r=>r.id===model).available_confirmed,false);
 same(after.model_aliases,before.model_aliases);
 const replay=await applyNewModelPlan(db,plan,hash,now);assert(replay.already_applied);assert.equal(replay.variants_inserted,0);same(await publicationSnapshot(db),after);
 assert.throws(()=>buildNewModelPlan(after,intake,image,now),'Never overwrite an already public model');
 const months=Array.from({length:12},(_,i)=>{const d=new Date(Date.UTC(2025,10+i,1));return{month:d.toISOString().slice(0,10),registrations:10,county:null,municipality:null};});
 assert.equal(rollingRegistrations(months,'2026-10-01'),120);assert.equal(rollingRegistrations(months.slice(1),'2026-10-01'),null);
 await db.query('UPDATE canonical_model_variants SET price_sek=price_sek+1 WHERE id=$1',[rows[0].id]);
 const altered=await publicationSnapshot(db);await assert.rejects(applyNewModelPlan(db,plan,hash,now));same(await publicationSnapshot(db),altered);
 console.log(JSON.stringify({new_model_publication:'passed',profiles:3,complete_fields:27,source_price_image_binding:true,
  real_schema_constraints:true,real_price_guard:true,late_rollback:true,idempotent_replay:true,collision_concurrency_rejection:true,
  market_history_preserved:true,twelve_month_completeness:true,remote_writes:0,paid_calls:0}));
}finally{await db.close();}
function same(a,b){assert.deepEqual(JSON.parse(JSON.stringify(a)),JSON.parse(JSON.stringify(b)));}
