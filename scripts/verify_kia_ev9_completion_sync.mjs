import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {buildSpecPlan,applySpecPlan,specPlanHash,urls} from './kia_ev9_completion_sync.mjs';
import {TECHNICAL_FIELDS} from './kia_spec_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';
const intake=JSON.parse(await readFile('tests/fixtures/kia_ev9_completion.json','utf8'));
const snapshot=JSON.parse(await readFile('public/data/public_ev_variants.json','utf8'));
const now=new Date(Math.max(...intake.drafts.flatMap(r=>[r.source,...r.supporting_sources].map(s=>Date.parse(s.fetched_at)))));
const fields=[...TECHNICAL_FIELDS,'ac_charge_kw'];
const columns=fields.map(f=>f+(f==='drivetrain'?' text':f==='ac_charge_kw'?' numeric(5,2)':' numeric')).join(',');
const db=new PGlite();
try{
 await db.exec(`CREATE TABLE canonical_models(id text primary key,brand text,model text,body_type text,updated_at timestamptz);
 CREATE TABLE canonical_model_variants(id text primary key,canonical_model_id text,variant_name text,validation_status text,
 review_approved_by text,review_promoted_at text,price_sek int,price_type text,price_valid_until date,
 price_source_url text,price_source_hash text,price_source_quote text,price_verified_at timestamptz,price_source_name text,price_refresh_batch_id text,
 ${columns},source_id text,source_url text,source_hash text,source_quote text,extraction_confidence numeric,updated_at timestamptz);
 CREATE TABLE manufacturer_sources(id text primary key default gen_random_uuid()::text,canonical_model_id text,brand text NOT NULL,model text NOT NULL,
 source_type text,url text unique,title text,country text,language text,fetched_at timestamptz,content_hash text,http_status int,
 final_url text,source_validation text,source_authority text,source_name text,extraction_status text,verified_at timestamptz,updated_at timestamptz);
 CREATE TABLE extracted_variant_drafts(canonical_model_id text,source_id text,brand text,model text,variant_name text,${columns},
 source_url text,source_hash text,source_quote text,extraction_confidence numeric,extraction_payload jsonb,validation_status text,
 validation_errors jsonb,updated_at timestamptz,unique(source_url,variant_name));
 INSERT INTO canonical_models VALUES('ev9','Kia','Ev9',null,now()),('outside','Kia','Ev6','Crossover',now());
 INSERT INTO manufacturer_sources(id,canonical_model_id,brand,model,url,verified_at) VALUES
 ('legacy-price','outside','Kia','EV4','https://www.kia.com/se/kopa/prislista/','2026-10-27'),
 ('shared-price',null,'Kia','*','https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf','2026-11-15'),
 ('legacy-model','ev9','Kia','EV9','https://www.kia.com/se/nya-bilar/ev9/upptack/','2026-11-12');
 INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,validation_status) VALUES('outside','outside','Outside EV6','published');`);
 const migration=await readFile('database/migrations/020_price_only_refresh.sql','utf8');
 await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
 await db.exec(`CREATE TRIGGER invalidate_replaced_price_evidence BEFORE UPDATE OF price_sek,price_type,price_valid_until
 ON canonical_model_variants FOR EACH ROW EXECUTE FUNCTION public.invalidate_replaced_price_evidence();`);
 for(const[i,draft]of intake.drafts.entries()){
  const baseline=snapshot.records.find(r=>r.brand===draft.brand&&r.model===draft.model&&r.variant_name===draft.variant_name);assert(baseline);
  const names=['id','canonical_model_id','variant_name','validation_status','price_sek','price_type','price_valid_until',
   'price_source_url','price_source_hash','price_source_quote','price_verified_at','price_source_name',...fields];
  const gaps=['ac_charge_kw','wltp_consumption_kwh_100km',...(draft.facts.seats===6?['boot_liters']:
   draft.variant_name==='EV9 AWD GT Line 7-sits'?[]:['seats'])];
  const row={...baseline,id:'ev9-'+i,canonical_model_id:'ev9',price_valid_until:null,...Object.fromEntries(gaps.map(f=>[f,null]))};
  await db.query('INSERT INTO canonical_model_variants('+names.join(',')+') VALUES('+names.map((_,n)=>'$'+(n+1)).join(',')+')',names.map(f=>row[f]??null));
 }
 const joined=async()=>(await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
 const before=await joined(),models=(await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,sources=(await db.query('SELECT * FROM manufacturer_sources ORDER BY id')).rows;
 const plan=buildSpecPlan(before,intake,now);
 for(const mutate of [r=>r.facts.ac_charge_kw=11,r=>r.facts.dc_charge_kw=250,r=>r.facts.boot_liters=828,
  r=>r.facts.seats=7,r=>r.facts.wltp_range_km=563,r=>r.facts.wltp_consumption_kwh_100km=22.2,
  r=>r.price_evidence.value=897900,r=>r.price_evidence.alternatives=[],r=>r.price_evidence.price_type='campaign_price',
  r=>r.field_evidence.boot_liters.source_url=urls.technical,r=>r.model_facts.body_type='SUV?',r=>r.source.http_status=403]){
  const invalid=structuredClone(intake);mutate(invalid.drafts[3]);assert.throws(()=>buildSpecPlan(before,invalid,now));
 }
 assert.throws(()=>buildSpecPlan(before,{...intake,drafts:intake.drafts.slice(0,3)},now));
 assert.throws(()=>buildSpecPlan(before,intake,new Date('2026-12-01')));
 const conflict=structuredClone(before);conflict.find(r=>r.variant_name==='EV9 AWD').battery_kwh=76.1;
 assert.throws(()=>buildSpecPlan(conflict,intake,now));
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Late fixture failure'; END $$;
 CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));assert.deepEqual(await joined(),before);
 assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
 assert.deepEqual((await db.query('SELECT * FROM manufacturer_sources ORDER BY id')).rows,sources);
 await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
 const result=await applySpecPlan(db,plan,specPlanHash(plan),now);
 assert.equal(result.variants_updated,4);assert.equal(result.new_technical_values,11);assert.equal(result.prices_changed,0);assert.equal(result.models_changed,1);
 const after=await joined();assert.deepEqual(after.find(r=>r.id==='outside'),before.find(r=>r.id==='outside'));
 for(const r of after.filter(r=>r.canonical_model_id==='ev9')){
  for(const f of fields)assert(r[f]!=null);
  assert.equal(Number(r.ac_charge_kw),10.5);assert(r.price_refresh_batch_id);assert.equal(r.price_type,'list_price');
  const notes=specQualifications({...r,seats:Number(r.seats),image_url:'/media/vehicles/kia-ev9-press-731db0e8f686.jpg'});
  assert.match(notes.rangeNote,/21-tumshjul/);assert.match(notes.practicalNote,/333/);assert.match(notes.imageNotice,/Kia EV9/);
  assert.equal(notes.specSources.some(s=>s.url.startsWith(urls.germany)),Number(r.seats)===6);
 }
 const saved=(await db.query('SELECT * FROM manufacturer_sources')).rows;
 assert.deepEqual(saved.find(s=>s.id==='legacy-price'),sources.find(s=>s.id==='legacy-price'));
 assert.equal(saved.find(s=>s.url===urls.price_pdf).id,'shared-price');assert.equal(saved.find(s=>s.url===urls.price_pdf).model,'*');
 assert.equal(saved.find(s=>s.url===urls.model).model,'EV9');assert.equal(saved.find(s=>s.url===urls.germany).country,'DE');
 const drafts=(await db.query('SELECT * FROM extracted_variant_drafts')).rows;assert.equal(drafts.length,4);
 const six=drafts.find(r=>r.variant_name==='EV9 AWD GT Line 6-sits');
 assert(JSON.stringify(six.extraction_payload).includes('897900'),'Alternate web price must remain traceable');
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 console.log(JSON.stringify({kia_ev9_completion_sync:'passed',profiles:4,new_facts:11,decimal_ac:10.5,
  real_price_trigger:true,seating_and_wheel_scope:true,price_alternate_retained:true,rollback_replay:true,production_writes:0,paid_calls:0}));
}finally{await db.close();}
