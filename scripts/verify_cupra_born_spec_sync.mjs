import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {validateSpecDraft,buildSpecPlan,applySpecPlan,specPlanHash,urls} from './cupra_born_spec_sync.mjs';
import {TECHNICAL_FIELDS,buildSpecPlan as kiaPlan} from './kia_spec_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';
import {decisionMetricsFor} from '../src/decision-metrics.js';
const intake=JSON.parse(await readFile('tests/fixtures/cupra_born_specs.json','utf8'));
const now=new Date(Math.max(...intake.drafts.flatMap(r=>[r.source,...r.supporting_sources].map(s=>Date.parse(s.fetched_at)))));
validateSpecDraft(intake.drafts[0],now);
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
 INSERT INTO canonical_models VALUES ('born','Cupra','Born',null,now()),('other','Other','Untouched',null,now());
 INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek,price_type,validation_status,
 price_source_url,price_source_hash,price_source_quote,price_verified_at,updated_at) VALUES
 ('born','born','Born VZ',596900,'list_price','published','https://www.cupraofficial.se/bilar/born',repeat('a',64),'Existing price',now(),now()),
 ('outside','other','Untouched',123456,null,'draft',null,null,null,null,now());`);
 const joined=async()=>(await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
 const rows=await joined(),plan=buildSpecPlan(rows,intake,now);
 for(const mutate of [r=>r.facts.battery_kwh=84,r=>r.facts.wltp_range_km=600,r=>r.facts.dc_charge_kw=185,
  r=>r.facts.ac_charge_kw=22,r=>r.facts.tow_kg=75,r=>r.facts.boot_liters=1267,r=>r.facts.seats=4,
  r=>r.variant_name='Born Endurance',r=>r.source.http_status=403,r=>r.source.fetched_at='2020-01-01',
  r=>r.field_evidence.tow_kg.quote='No number found',r=>r.field_evidence.wltp_range_km.source_url=urls.model,
  r=>r.supporting_sources.pop(),r=>r.price_evidence.value=5969,r=>r.price_evidence.price_type='campaign_price']){
  const invalid=structuredClone(intake);mutate(invalid.drafts[0]);assert.throws(()=>buildSpecPlan(rows,invalid,now));
 }
 assert.throws(()=>buildSpecPlan(rows,{...intake,drafts:[...intake.drafts,...intake.drafts]},now));
 assert.throws(()=>kiaPlan(rows,intake,now));
 const changed=structuredClone(rows);changed[0].price_sek=466900;assert.throws(()=>buildSpecPlan(changed,intake,now));
 const before=await joined(),models=(await db.query('SELECT * FROM canonical_models ORDER BY id')).rows;
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Fixture late failure'; END $$;
 CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 assert.deepEqual(await joined(),before);assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
 assert.equal((await db.query('SELECT count(*)::int n FROM manufacturer_sources')).rows[0].n,0);
 await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
 const result=await applySpecPlan(db,plan,specPlanHash(plan),now);
 assert.equal(result.variants_updated,1);assert.equal(result.new_technical_values,9);assert.equal(result.prices_changed,0);assert.equal(result.models_changed,1);
 assert.deepEqual((await joined()).find(r=>r.id==='outside'),before.find(r=>r.id==='outside'));
 const current=(await joined()).find(r=>r.id==='born');assert.equal(current.price_type,'list_price');
 assert.equal(current.variant_name,'Born VZ');assert.equal(Number(current.tow_kg),0);assert(current.price_refresh_batch_id);
 const sources=(await db.query('SELECT * FROM manufacturer_sources')).rows;
 assert.equal(sources.length,6);const global=sources.find(s=>s.url===urls.technical);
 assert.equal(global.country,'EU');assert.equal(global.language,'en');assert.equal(global.source_validation,'reachable_eu_official_source');
 assert.equal(global.source_type,'technical_pdf');
 const staged=(await db.query('SELECT * FROM extracted_variant_drafts')).rows[0];
 assert.equal(staged.validation_status,'published');assert.equal(staged.extraction_payload.previous_canonical.id,'born');
 assert.equal(staged.extraction_payload.source_decisions.length,8);
 const info=specQualifications(current);assert.equal(info.rangeInterval,'552–631 km');
 assert.match(info.practicalNote,/inte godkänd för släp/);assert.match(info.consumptionNote,/14,2/);assert.equal(info.specSources.length,4);
 assert.equal(specQualifications({...current,brand:'Other'}).rangeInterval,null);
 assert.equal(specQualifications({...current,source_quote:''}).rangeInterval,null);
 assert.match(decisionMetricsFor({...info,price:596900,priceType:'list_price',rangeVerified:631},[],now)[0].note,/övre gränsen/);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 console.log(JSON.stringify({cupra_born_sync:'passed',exact_my2027_vz:true,nine_facts:true,zero_explicit_not_missing:true,
  truthful_eu_locale_and_interval:true,price_unchanged:true,rollback_replay_scope:true,production_writes:0,paid_calls:0}));
}finally{await db.close();}
