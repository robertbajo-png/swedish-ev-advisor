import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';
import { ADAPTER, validateSpecDraft, buildSpecPlan, applySpecPlan, specPlanHash, intakeFingerprint } from './mazda_renault_spec_sync.mjs';
import { TECHNICAL_FIELDS, buildSpecPlan as kiaPlan } from './kia_spec_sync.mjs';
import { specQualifications } from '../src/spec-qualifications.js';
const intake=JSON.parse(await readFile('tests/fixtures/mazda_renault_specs.json','utf8'));
const now=new Date('2026-11-13T21:01:00Z');
const db=new PGlite();
try {
 const columns=[...TECHNICAL_FIELDS,'ac_charge_kw'].map(f=>f+(f==='drivetrain'?' text':' numeric')).join(',');
 await db.exec(`CREATE TABLE canonical_models(id text primary key,brand text,model text,body_type text,updated_at timestamptz);
 CREATE TABLE canonical_model_variants(id text primary key,canonical_model_id text,variant_name text,validation_status text,
 review_approved_by text,review_promoted_at text,price_sek int,price_type text,price_valid_until date,
 price_source_url text,price_source_hash text,price_source_quote text,price_verified_at timestamptz,price_source_name text,price_refresh_batch_id text,
 ${columns},source_id text,source_url text,source_hash text,source_quote text,extraction_confidence numeric,updated_at timestamptz);
 CREATE TABLE manufacturer_sources(id text primary key default gen_random_uuid()::text,canonical_model_id text,brand text,model text,
 source_type text,url text unique,title text,country text,language text,fetched_at timestamptz,content_hash text,http_status int,
 final_url text,source_validation text,source_authority text,source_name text,extraction_status text,verified_at timestamptz,updated_at timestamptz);
 CREATE TABLE extracted_variant_drafts(canonical_model_id text,source_id text,brand text,model text,variant_name text,${columns},
 source_url text,source_hash text,source_quote text,extraction_confidence numeric,extraction_payload jsonb,validation_status text,
 validation_errors jsonb,updated_at timestamptz,unique(source_url,variant_name));
 INSERT INTO canonical_models VALUES ('outside','Other','Untouched',null,now());
 INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek) VALUES ('outside','outside','Untouched',123456);`);
 const migration=await readFile('database/migrations/020_price_only_refresh.sql','utf8');
 await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
 await db.exec(`CREATE TRIGGER invalidate_replaced_price_evidence BEFORE UPDATE OF price_sek,price_type,price_valid_until
 ON canonical_model_variants FOR EACH ROW EXECUTE FUNCTION public.invalidate_replaced_price_evidence();
 ALTER TABLE canonical_model_variants ADD CONSTRAINT price_proof_complete CHECK (
 num_nonnulls(price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id) IN (0,6));`);
 const modelIds=new Set();
 for(const [i,row] of intake.drafts.entries()){
   validateSpecDraft(row,now);const modelId=row.brand+row.model;
   if(!modelIds.has(modelId)){modelIds.add(modelId);await db.query('INSERT INTO canonical_models VALUES ($1,$2,$3,null,now())',[modelId,row.brand,row.model]);}
   await db.query(`INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,validation_status,price_sek,price_type,source_url,source_hash,updated_at)
     VALUES ($1,$2,$3,'published',$4,'list_price',$5,$6,now())`,[String(i),modelId,row.variant_name,row.price_evidence.value,row.source.final_url,'c'.repeat(64)]);
 }
 const joined=async()=>(await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
 // Preserve the existing source alias and require its exact canonical parent.
 await db.query(`INSERT INTO manufacturer_sources(id,brand,model,canonical_model_id,url,country,language)
   VALUES ('legacy-mazda','Mazda','6e','Mazda6E',$1,'SE','sv')`,['https://www.mazda.se/modeller/mazda-6e/']);
 const rows=await joined(),plan=buildSpecPlan(rows,intake,now);
 for(const mutate of [d=>d.drafts[0].facts.dc_charge_kw=1200,d=>d.drafts[0].facts.battery_kwh=68.8,
   d=>d.drafts[0].facts.seats=7,d=>d.drafts[0].facts.boot_liters=1074,d=>d.drafts[0].facts.ac_charge_kw=7.9,
   d=>d.drafts[0].variant_name='Takumi MY2025',d=>d.drafts[0].source.fetched_at='2020-01-01',
   d=>d.drafts[0].field_evidence.seats.source_url=d.drafts[0].source.final_url,
   d=>d.drafts[0].price_evidence.price_type='campaign_price',d=>d.drafts[0].price_evidence.value++,
   d=>d.drafts[4].facts.wltp_range_km=421,d=>d.drafts[4].field_evidence.wltp_range_km.column_header='ICONIC FIVE 52 kWh',
   d=>d.drafts[4].field_evidence.wltp_consumption_kwh_100km.interval=[14.1],
   d=>d.drafts[4].field_evidence.drivetrain.source_hash='b'.repeat(64),d=>d.drafts.push(d.drafts[0])]){
   const invalid=structuredClone(intake);mutate(invalid);assert.throws(()=>buildSpecPlan(rows,invalid,now));
 }
 assert.throws(()=>kiaPlan(rows,intake,now));
 const conflict=structuredClone(rows);conflict.find(r=>r.id==='0').tow_kg=2000;assert.throws(()=>buildSpecPlan(conflict,intake,now));
 const wrongPrice=structuredClone(rows);wrongPrice.find(r=>r.id==='0').price_sek++;assert.throws(()=>buildSpecPlan(wrongPrice,intake,now));
 const before=(await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
 const models=(await db.query('SELECT * FROM canonical_models ORDER BY id')).rows;
 const beforeSources=(await db.query('SELECT * FROM manufacturer_sources ORDER BY id')).rows;
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.variant_name='iconic five 52 kWh' THEN RAISE EXCEPTION 'Fixture late failure'; END IF; RETURN NEW; END $$;
 CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 assert.deepEqual((await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows,before);
 assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
 assert.deepEqual((await db.query('SELECT * FROM manufacturer_sources ORDER BY id')).rows,beforeSources);
 await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
 const result=await applySpecPlan(db,plan,specPlanHash(plan),now);
 assert.equal(result.variants_updated,6);assert.equal(result.models_changed,2);
 const saved=await joined();assert.equal(saved.find(r=>r.id==='outside').price_sek,123456);
 for(const r of saved.filter(r=>r.id!=='outside')){
   assert.equal(r.price_type,'list_price');assert(r.price_source_quote&&r.price_refresh_batch_id);
   const original=rows.find(o=>o.id===r.id);assert.equal(r.price_sek,original.price_sek);
 }
 const sources=(await db.query('SELECT * FROM manufacturer_sources')).rows;
 assert.equal(sources.filter(s=>s.country==='DE'&&s.language==='de'&&s.source_validation==='reachable_eu_official_source').length,2);
 const staged=(await db.query('SELECT * FROM extracted_variant_drafts')).rows;
 assert(staged.every(r=>r.validation_status==='published'&&r.extraction_payload.price_evidence&&r.extraction_payload.source_decisions.length>=4));
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 const qualified=saved.find(r=>r.variant_name==='iconic five 52 kWh');
 assert.equal(specQualifications(qualified).consumptionInterval,'14,1–14,2 kWh/100 km');
 assert.match(specQualifications(qualified).consumptionNote,/gemensamma WLTP-intervall/);
 const fresh=structuredClone(intake);fresh.drafts[0].source.content_hash='d'.repeat(64);
 assert.deepEqual(intakeFingerprint(fresh),intakeFingerprint(intake));fresh.drafts[0].facts.wltp_range_km++;
 assert.notDeepEqual(intakeFingerprint(fresh),intakeFingerprint(intake));
 console.log(JSON.stringify({mazda_renault_sync:'passed',six_exact_versions:true,source_locales:true,price_provenance:true,
   rollback_replay_and_scope:true,group_consumption_not_false_precision:true,production_writes:0,paid_calls:0}));
}finally{await db.close();}
