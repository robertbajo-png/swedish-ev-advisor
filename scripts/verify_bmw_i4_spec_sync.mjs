import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {validateSpecDraft,buildSpecPlan,applySpecPlan,specPlanHash,NAME} from './bmw_i4_spec_sync.mjs';
import {TECHNICAL_FIELDS,buildSpecPlan as kiaPlan} from './kia_spec_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';
import {fetchBmwPublic,BMW_URLS} from './bmw_i4_http.mjs';
const intake=JSON.parse(await readFile('tests/fixtures/bmw_i4_specs.json','utf8'));
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
 INSERT INTO canonical_models VALUES ('bmw','BMW','i4',null,now()),('other','Other','Untouched',null,now());
 INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek,price_type,validation_status,
 price_source_url,price_source_hash,price_source_quote,price_verified_at,updated_at) VALUES
 ('bmw','bmw','i4 eDrive40 M Sport Business Edition (lagerbil FW37556)',675900,'dealer_offer','published','https://hitta.bmw.se/r/G26E-i4/i4-eDrive40-WBY61HD030FW37556',repeat('a',64),'Existing price',now(),now()),
 ('outside','other','Untouched',123456,null,'draft',null,null,null,null,now());`);

 const joined=async()=>(await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
 const migration=await readFile('database/migrations/020_price_only_refresh.sql','utf8');
 await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
 await db.exec(`CREATE TRIGGER invalidate_replaced_price_evidence BEFORE UPDATE OF price_sek,price_type,price_valid_until
 ON canonical_model_variants FOR EACH ROW EXECUTE FUNCTION public.invalidate_replaced_price_evidence();`);
 const rows=await joined(),plan=buildSpecPlan(rows,intake,now);
 for(const mutate of [r=>r.facts.battery_kwh=81.1,r=>r.facts.wltp_range_km=613,r=>r.facts.dc_charge_kw=200,
  r=>r.facts.ac_charge_kw=22,r=>r.facts.tow_kg=75,r=>r.facts.boot_liters=1290,r=>r.facts.seats=4,
  r=>r.variant_name='i4 M60',r=>r.source.http_status=403,r=>r.source.fetched_at='2020-01-01',
  r=>r.field_evidence.tow_kg.quote='75 kg',r=>r.field_evidence.wltp_range_km.source_url=BMW_URLS.technical,
  r=>r.supporting_sources.pop(),r=>r.price_evidence.value=675900,r=>r.price_evidence.price_type='list_price']){
  const invalid=structuredClone(intake);mutate(invalid.drafts[0]);assert.throws(()=>buildSpecPlan(rows,invalid,now));
 }
 assert.throws(()=>buildSpecPlan(rows,{...intake,drafts:[...intake.drafts,...intake.drafts]},now));
 assert.throws(()=>kiaPlan(rows,intake,now));
 const changed=structuredClone(rows);changed.find(r=>r.id==='bmw').price_sek=650700;assert.throws(()=>buildSpecPlan(changed,intake,now));
 const before=await joined(),models=(await db.query('SELECT * FROM canonical_models ORDER BY id')).rows;
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Fixture late failure'; END $$;
 CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 assert.deepEqual(await joined(),before);assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
 assert.equal((await db.query('SELECT count(*)::int n FROM manufacturer_sources')).rows[0].n,0);
 await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
 const result=await applySpecPlan(db,plan,specPlanHash(plan),now);
 assert.equal(result.variants_updated,1);assert.equal(result.new_technical_values,9);assert.equal(result.prices_changed,1);assert.equal(result.models_changed,1);
 assert.deepEqual((await joined()).find(r=>r.id==='outside'),before.find(r=>r.id==='outside'));
 const current=(await joined()).find(r=>r.id==='bmw');assert.equal(current.price_type,'dealer_offer');
 assert.equal(current.variant_name,NAME);assert.equal(Number(current.price_sek),673900);assert(current.price_refresh_batch_id);
 assert.equal((await db.query('SELECT count(*)::int n FROM manufacturer_sources')).rows[0].n,2);
 const staged=(await db.query('SELECT * FROM extracted_variant_drafts')).rows[0];
 assert.equal(staged.validation_status,'published');assert.equal(staged.extraction_payload.previous_canonical.id,'bmw');
 const info=specQualifications(current);assert.equal(info.rangeInterval,null);assert.equal(info.consumptionInterval,'14,9–17,1 kWh/100 km');
 assert.match(info.practicalNote,/75 kg kultryck/);assert.match(info.consumptionNote,/inte ett individuellt/);assert.equal(info.specSources.length,2);
 assert.equal(specQualifications({...current,brand:'Other'}).consumptionInterval,null);
 assert.equal(specQualifications({...current,source_quote:''}).consumptionInterval,null);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 // Mock transport only: no network, credentials or paid requests.
 const response=(body,headers={})=>({status:200,url:BMW_URLS.technical,headers:new Headers({'content-type':'text/html',...headers}),body:new Response(body).body});
 let options;
 const http=await fetchBmwPublic('technical',{fetchImpl:async(_u,o)=>(options=o,response('<html>public</html>'))});
 assert.equal(options.method,'GET');assert.equal(options.redirect,'error');assert.equal(http.source.http_status,200);
 for(const r of [response('x',{'tdm-reservation':'1'}),response('x',{'content-type':'application/json'}),
  response('x',{'content-length':String(9*1024*1024)}),{...response('x'),status:403},{...response('x'),url:BMW_URLS.model}]){
  await assert.rejects(fetchBmwPublic('technical',{fetchImpl:async()=>r}));
 }
 await assert.rejects(fetchBmwPublic('unknown'));
 console.log(JSON.stringify({bmw_i4_sync:'passed',exact_vin_and_type:true,nine_facts:true,
  stock_not_type_range:true,type_consumption_qualified:true,price_replacement_with_invalidation:true,
  rollback_replay_scope:true,public_get_guards:true,production_writes:0,paid_calls:0}));
}finally{await db.close();}
