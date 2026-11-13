import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {validateSpecDraft,buildSpecPlan,applySpecPlan,specPlanHash,intakeFingerprint} from './mercedes_cla_spec_sync.mjs';
import {TECHNICAL_FIELDS,buildSpecPlan as kiaPlan} from './kia_spec_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';
import {vehicleSlug} from '../src/vehicle-names.js';

const intake=JSON.parse(await readFile('tests/fixtures/mercedes_cla_specs.json','utf8'));
const now=new Date(Math.max(...intake.drafts.flatMap(r=>[Date.parse(r.source.fetched_at),Date.parse(r.price_evidence.order_source.fetched_at)])));
const db=new PGlite();
try{
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
 INSERT INTO canonical_models VALUES ('cla','Mercedes-Benz','Cla',null,now()),('outside','Other','Untouched',null,now());
 INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek) VALUES ('outside','outside','Untouched',123456);`);
 const migration=await readFile('database/migrations/020_price_only_refresh.sql','utf8');
 await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
 await db.exec(`CREATE TRIGGER invalidate_replaced_price_evidence BEFORE UPDATE OF price_sek,price_type,price_valid_until
 ON canonical_model_variants FOR EACH ROW EXECUTE FUNCTION public.invalidate_replaced_price_evidence();
 ALTER TABLE canonical_model_variants ADD CONSTRAINT price_proof_complete CHECK (
 num_nonnulls(price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id) IN (0,6));`);
 for(const [i,r]of intake.drafts.entries()){
  validateSpecDraft(r,now);
  await db.query(`INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,validation_status,price_sek,price_type,
    source_url,source_hash,updated_at) VALUES ($1,'cla',$2,'published',$3,'dealer_offer',$4,$5,now())`,
   [String(i),r.variant_name,r.price_evidence.value,r.price_evidence.source_url,'c'.repeat(64)]);
 }
 const joined=async()=>(await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
 const rows=await joined(),plan=buildSpecPlan(rows,intake,now);
 for(const mutate of [d=>d.drafts[0].facts.battery_kwh=85,d=>d.drafts[0].facts.dc_charge_kw=320,
  d=>d.drafts[0].facts.ac_charge_kw=22,d=>d.drafts[0].facts.wltp_range_km=615,
  d=>d.drafts[0].facts.boot_liters=506,d=>d.drafts[0].facts.seats=4,d=>d.drafts[2].facts.drivetrain='RWD',
  d=>d.drafts[2].facts.tow_kg=1500,d=>d.drafts[0].source.http_status=200,
  d=>d.drafts[0].source.retrieval_method='attributed_search_service_snapshot',
  d=>d.drafts[0].source.fetched_at='2020-01-01',d=>d.drafts[0].field_evidence.seats.source_hash='b'.repeat(64),
  d=>d.drafts[0].price_evidence.price_type='list_price',d=>d.drafts[0].price_evidence.value++,
  d=>d.drafts[0].price_evidence.stock_identity.year=2026,d=>d.drafts[0].replacement_variant_name='CLA 200 AMG',
  d=>d.drafts[0].variant_name='CLA 200 Shooting Brake',d=>d.drafts.pop()]){
   const invalid=structuredClone(intake);mutate(invalid);assert.throws(()=>buildSpecPlan(rows,invalid,now));
 }
 assert.throws(()=>kiaPlan(rows,intake,now));
 const wrongPrice=structuredClone(rows);wrongPrice[0].price_sek++;assert.throws(()=>buildSpecPlan(wrongPrice,intake,now));
 const before=(await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
 const models=(await db.query('SELECT * FROM canonical_models ORDER BY id')).rows;
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.variant_name LIKE 'CLA 350%' THEN RAISE EXCEPTION 'Fixture late failure'; END IF; RETURN NEW; END $$;
 CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 assert.deepEqual((await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows,before);
 assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
 assert.equal((await db.query('SELECT count(*)::int n FROM manufacturer_sources')).rows[0].n,0);
 await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
 const result=await applySpecPlan(db,plan,specPlanHash(plan),now);
 assert.equal(result.variants_updated,3);assert.equal(result.new_technical_values,27);assert.equal(result.models_changed,1);
 for(const r of (await joined()).filter(r=>r.id!=='outside')){
  const old=rows.find(o=>o.id===r.id);assert.equal(r.price_sek,old.price_sek);assert.equal(r.price_type,'dealer_offer');
  assert(r.price_source_quote&&r.price_refresh_batch_id);assert.match(r.variant_name,/\(beställningsbil\)$/);
  assert.equal(vehicleSlug(r.brand,r.model,r.variant_name),vehicleSlug(old.brand,old.model,old.variant_name));
  assert.match(specQualifications(r).practicalNote,/Monterad dragkrok ingår inte automatiskt/);
 }
 const sources=(await db.query('SELECT * FROM manufacturer_sources')).rows;
 assert.equal(sources.length,1);assert.equal(sources[0].http_status,null);
 assert.equal(sources[0].source_validation,'reachable_official_browser_source');
 const staged=(await db.query('SELECT * FROM extracted_variant_drafts')).rows;
 assert(staged.every(r=>r.validation_status==='published'&&r.extraction_payload.source_capture.http_status===null));
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 const fresh=structuredClone(intake);fresh.drafts[0].price_evidence.order_source.content_hash='d'.repeat(64);
 assert.deepEqual(intakeFingerprint(intake),intakeFingerprint(fresh));fresh.drafts[0].facts.ac_charge_kw=22;
 assert.notDeepEqual(intakeFingerprint(intake),intakeFingerprint(fresh));
 console.log(JSON.stringify({cla_spec_sync:'passed',three_complete_versions:true,truthful_dom_source_status:true,
  order_status_corrected_links_retained:true,real_price_trigger_rollback_replay:true,production_writes:0,paid_calls:0}));
}finally{await db.close();}
