import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {validateSpecDraft,buildSpecPlan,applySpecPlan,specPlanHash,intakeFingerprint} from './ford_explorer_spec_sync.mjs';
import {TECHNICAL_FIELDS,buildSpecPlan as kiaPlan} from './kia_spec_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';
import {vehicleRedirect} from '../src/vehicle-redirects.js';
import {useCalendarDateText} from './refresh_kia_specs.mjs';
let dateParser;
useCalendarDateText({setTypeParser:(oid,parse)=>{assert.equal(oid,1082);dateParser=parse;}});
assert.equal(dateParser('2026-12-30'),'2026-12-30','A campaign date never becomes the previous UTC day');
assert.throws(()=>useCalendarDateText({}),/DATE parser/);
const intake=JSON.parse(await readFile('tests/fixtures/ford_explorer_specs.json','utf8'));
const now=new Date(Math.max(...intake.drafts.flatMap(r=>[r.source,...r.supporting_sources].map(s=>Date.parse(s.fetched_at)))));
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
 INSERT INTO canonical_models VALUES ('explorer','Ford','Explorer',null,now()),('outside','Other','Untouched',null,now());
 INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek) VALUES ('outside','outside','Untouched',123456);`);
 const migration=await readFile('database/migrations/020_price_only_refresh.sql','utf8');
 await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
 await db.exec(`CREATE TRIGGER invalidate_replaced_price_evidence BEFORE UPDATE OF price_sek,price_type,price_valid_until
 ON canonical_model_variants FOR EACH ROW EXECUTE FUNCTION public.invalidate_replaced_price_evidence();
 ALTER TABLE canonical_model_variants ADD CONSTRAINT price_proof_complete CHECK (
 num_nonnulls(price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id)=0 OR
 (num_nonnulls(price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id)=6 AND
 price_sek IS NOT NULL AND price_type IS NOT NULL AND (price_type <> 'campaign_price' OR price_valid_until IS NOT NULL)));`);
 for(const [i,r]of intake.drafts.entries()){
  validateSpecDraft(r,now);
  await db.query(`INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,validation_status,
    wltp_range_km,battery_kwh,drivetrain,source_url,source_hash,updated_at) VALUES ($1,'explorer',$2,'published',$3,$4,$5,$6,$7,now())`,
    [String(i),r.variant_name,i===0?602:556,i===0?77:79,i===0?'RWD':'AWD',
     'https://www.ford.se/bilar/personbilar-och-suver/explorer','c'.repeat(64)]);
 }
 const joined=async()=>(await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
 const rows=await joined(),plan=buildSpecPlan(rows,intake,now);
 for(const mutate of [d=>d.drafts[0].facts.battery_kwh=77,d=>d.drafts[0].facts.wltp_range_km=602,
  d=>d.drafts[1].facts.dc_charge_kw=185,d=>d.drafts[0].facts.ac_charge_kw=2.3,
  d=>d.drafts[0].facts.boot_liters=572,d=>d.drafts[1].facts.tow_kg=1200,d=>d.drafts[0].facts.seats=7,
  d=>d.drafts[0].source.http_status=403,d=>d.drafts[0].source.fetched_at='2020-01-01',
  d=>d.drafts[0].field_evidence.boot_liters.source_hash='b'.repeat(64),d=>d.drafts[0].supporting_sources.pop(),
  d=>d.drafts[0].price_evidence.price_type='list_price',d=>d.drafts[0].price_evidence.value=5595,
  d=>d.drafts[0].price_evidence.value=626000,d=>d.drafts[0].price_evidence.price_valid_until=null,
  d=>d.drafts[0].price_evidence.campaign_source_url='https://www.ford.se/capri',
  d=>d.drafts[0].replacement_variant_name='Explorer Nordic Edition',d=>d.drafts[0].variant_name='Explorer PHEV',d=>d.drafts.pop()]){
   const invalid=structuredClone(intake);mutate(invalid);assert.throws(()=>buildSpecPlan(rows,invalid,now));
 }
 assert.throws(()=>kiaPlan(rows,intake,now));
 const changed=structuredClone(rows);changed[0].price_sek=490000;assert.throws(()=>buildSpecPlan(changed,intake,now));
 const differentYear=structuredClone(rows);differentYear[1].wltp_range_km=566;assert.throws(()=>buildSpecPlan(differentYear,intake,now));
 const before=(await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
 const models=(await db.query('SELECT * FROM canonical_models ORDER BY id')).rows;
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.variant_name LIKE 'Explorer AWD%' THEN RAISE EXCEPTION 'Fixture late failure'; END IF; RETURN NEW; END $$;
 CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 assert.deepEqual((await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows,before);
 assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
 assert.equal((await db.query('SELECT count(*)::int n FROM manufacturer_sources')).rows[0].n,0);
 await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
 const result=await applySpecPlan(db,plan,specPlanHash(plan),now);
 assert.equal(result.variants_updated,2);assert.equal(result.new_technical_values,12);assert.equal(result.prices_changed,2);assert.equal(result.models_changed,1);
 for(const r of (await joined()).filter(r=>r.id!=='outside')){
  const old=rows.find(o=>o.id===r.id);assert(r.price_source_quote&&r.price_refresh_batch_id);
  assert.match(r.variant_name,/Premium Edition.*MY27\.25$/);assert.equal(r.price_type,'campaign_price');
  assert.equal(new Date(r.price_valid_until).toISOString().slice(0,10),'2026-12-30');
  const info=specQualifications(r);assert.match(info.practicalNote,/danska/);assert(info.practicalSource);
  const legacy=old.variant_name==='Explorer RWD 77 kWh'?'ford-explorer-rwd-77-kwh':'ford-explorer-awd-79-kwh';
  assert.equal(vehicleRedirect(legacy),'/bilar?brand=Ford&query=Explorer');
 }
 const sources=(await db.query('SELECT * FROM manufacturer_sources')).rows;assert.equal(sources.length,4);
 const danish=sources.find(s=>s.country==='DK');assert(danish);assert.equal(danish.language,'da');assert.equal(danish.source_validation,'reachable_eu_official_source');
 const staged=(await db.query('SELECT * FROM extracted_variant_drafts')).rows;
 assert(staged.every(r=>r.validation_status==='published'&&r.extraction_payload.price_evidence.reference_price>r.extraction_payload.price_evidence.value));
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 const fresh=structuredClone(intake);fresh.drafts[0].source.content_hash='d'.repeat(64);
 assert.deepEqual(intakeFingerprint(intake),intakeFingerprint(fresh));fresh.drafts[0].facts.boot_liters=532;
 assert.notDeepEqual(intakeFingerprint(intake),intakeFingerprint(fresh));
 console.log(JSON.stringify({ford_spec_sync:'passed',two_current_versions:true,campaign_not_list_or_leasing:true,
  real_price_trigger_rollback_replay:true,old_links_retained:true,truthful_danish_locale:true,production_writes:0,paid_calls:0}));
}finally{await db.close();}
