import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,relative,sep} from 'node:path';
import {PGlite} from '@electric-sql/pglite';
import {buildSpecPlan,applySpecPlan,specPlanHash,validateSpecDraft,urls} from './kia_ev3_completion_sync.mjs';
import {TECHNICAL_FIELDS} from './kia_spec_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';
import {matchAdvisorVariants,ruleRequirements} from '../src/advisor-matching.js';
const intake=JSON.parse(await readFile('tests/fixtures/kia_ev3_completion.json','utf8'));
const snapshot=JSON.parse(await readFile('public/data/public_ev_variants.json','utf8'));
const now=new Date(Math.max(...intake.drafts.flatMap(r=>[r.source,...r.supporting_sources].map(s=>Date.parse(s.fetched_at)))));
for(const r of intake.drafts)validateSpecDraft(r,now);
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
 INSERT INTO canonical_models VALUES('ev3','Kia','Ev3',null,now()),('outside','Kia','EV4',null,now());
 INSERT INTO manufacturer_sources(id,canonical_model_id,brand,model,url,verified_at) VALUES
 ('legacy-price','outside','Kia','EV4','https://www.kia.com/se/kopa/prislista/','2026-10-27'),
 ('legacy-specs','ev3','Kia','EV3','https://www.kia.com/se/nya-bilar/ev3/specifikationer/','2026-10-27');
 INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek,source_id,validation_status)
 VALUES('outside','outside','Outside',123456,'legacy-price','published');`);
 const migration=await readFile('database/migrations/020_price_only_refresh.sql','utf8');
 await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
 await db.exec(`CREATE TRIGGER invalidate_replaced_price_evidence BEFORE UPDATE OF price_sek,price_type,price_valid_until
 ON canonical_model_variants FOR EACH ROW EXECUTE FUNCTION public.invalidate_replaced_price_evidence();`);
 for(const [i,r]of intake.drafts.entries()){
  const baseline=snapshot.records.find(x=>x.brand===r.brand&&x.model===r.model&&x.variant_name===r.variant_name);assert(baseline);
  const fields=['id','canonical_model_id','variant_name','validation_status','price_sek','price_type','price_valid_until',
   'price_source_url','price_source_hash','price_source_quote','price_verified_at','price_source_name',...TECHNICAL_FIELDS,'ac_charge_kw'];
  const row={...baseline,id:'ev3-'+i,canonical_model_id:'ev3'};
  await db.query('INSERT INTO canonical_model_variants('+fields.join(',')+') VALUES('+fields.map((_,i)=>'$'+(i+1)).join(',')+')',fields.map(f=>row[f]??null));
 }
 const joined=async()=>(await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
 const rows=await joined(),plan=buildSpecPlan(rows,intake,now);
 for(const mutate of [r=>r.facts.ac_charge_kw=11,r=>r.facts.ac_charge_kw=22,r=>r.facts.battery_kwh=84,
  r=>r.facts.wltp_range_km=605,r=>r.facts.tow_kg=80,r=>r.facts.boot_liters=1204,r=>r.facts.wltp_consumption_kwh_100km=18.1,
  r=>r.variant_name='EV3 GT Line AWD Long Range',r=>r.source.http_status=403,r=>r.source.fetched_at='2020-01-01',
  r=>r.field_evidence.ac_charge_kw.quote='22 kW',r=>r.supporting_sources.pop(),r=>r.price_evidence.price_type='campaign_price',
  r=>r.price_evidence.value=20000,r=>r.price_evidence.price_valid_until=null]){
  const invalid=structuredClone(intake);mutate(invalid.drafts[6]);assert.throws(()=>buildSpecPlan(rows,invalid,now));
 }
 assert.throws(()=>buildSpecPlan(rows,{...intake,drafts:intake.drafts.slice(0,6)},now));
 const invalid=structuredClone(intake);invalid.drafts[4].field_evidence.wltp_range_km.quote=invalid.drafts[4].field_evidence.wltp_range_km.quote.replace('(AWD, Preliminär information i väntan på homologering) | ','');
 assert.throws(()=>buildSpecPlan(rows,invalid,now));
 const before=await joined(),models=(await db.query('SELECT * FROM canonical_models ORDER BY id')).rows;
 const legacy=(await db.query("SELECT * FROM manufacturer_sources WHERE id='legacy-price'")).rows;
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Late fixture failure'; END $$;
 CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));assert.deepEqual(await joined(),before);
 assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
 await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
 const result=await applySpecPlan(db,plan,specPlanHash(plan),now);
 assert.equal(result.variants_updated,7);assert.equal(result.new_technical_values,39);assert.equal(result.prices_changed,0);assert.equal(result.models_changed,1);
 assert.deepEqual((await joined()).find(r=>r.id==='outside'),before.find(r=>r.id==='outside'));
 assert.deepEqual((await db.query("SELECT * FROM manufacturer_sources WHERE id='legacy-price'")).rows,legacy);
 const current=(await joined()).filter(r=>r.canonical_model_id==='ev3').map(r=>({...r,
  price_valid_until:r.price_valid_until instanceof Date?r.price_valid_until.toISOString().slice(0,10):r.price_valid_until,
  ...Object.fromEntries([...TECHNICAL_FIELDS,'ac_charge_kw'].filter(f=>f!=='drivetrain').map(f=>[f,Number(r[f])]))}));
 for(const r of current){assert.equal(r.ac_charge_kw,10.5);assert.equal(r.price_type,'list_price');assert(r.price_refresh_batch_id);assert.equal(String(r.price_valid_until).slice(0,10),'2026-11-30');}
 const sources=(await db.query('SELECT * FROM manufacturer_sources')).rows;
 assert.equal(sources.find(s=>s.url===urls.poland).country,'PL');assert.equal(sources.find(s=>s.url===urls.poland).language,'pl');
 assert.equal(sources.find(s=>s.url===urls.gt).source_type,'manufacturer_model_page');
 assert.equal(sources.find(s=>s.url===urls.technical).source_type,'technical_pdf');
 assert.equal(sources.find(s=>s.url===urls.energy).canonical_model_id,null);
 const target=current.find(r=>r.variant_name==='EV3 Plus AWD Long Range');assert(specQualifications(target).rangeIsTarget);
 assert.match(specQualifications(target).rangeNote,/preliminär/);
 const gt=current.find(r=>r.variant_name.includes('(292hk)'));assert(!specQualifications(gt).rangeIsTarget);assert.match(specQualifications(gt).consumptionNote,/17,1/);
 const requirements={...ruleRequirements({budget:700000,range:500,need:'allround'}),awd_required:true};
 const matched=matchAdvisorVariants(current,requirements,{asOf:'2026-11-14'});
 assert.equal(matched.matching_count,1);assert.equal(matched.excluded_unknown_count,2);assert.equal(matched.shortlist[0].variant_name,gt.variant_name);
 assert.equal(matchAdvisorVariants(current,{...requirements,awd_required:false,min_wltp_range_km:null},{asOf:'2026-12-01'}).matching_count,0);
 assert.equal((await db.query('SELECT count(*)::int n FROM extracted_variant_drafts')).rows[0].n,7);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 if(process.argv.includes('--preview')){
  const folder=resolve('data/local/release-data/kia-ev3-completion-2026-11-14');
  assert(!relative(resolve('data/local'),folder).startsWith('..'+sep));await mkdir(folder,{recursive:true});
  const names=['price_sek','price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote','price_verified_at','price_source_name',
   ...TECHNICAL_FIELDS,'ac_charge_kw','source_url','source_hash','source_quote','extraction_confidence','validation_status'];
  const records=snapshot.records.map(old=>{
   const r=current.find(r=>r.brand===old.brand&&r.model===old.model&&r.variant_name===old.variant_name);if(!r)return old;
   return {...old,...Object.fromEntries(names.map(k=>[k,r[k]])),body_type:'SUV',source_name:'Kia Sverige',verified_at:intake.drafts[0].source.fetched_at};
  });
  await writeFile(resolve(folder,'isolated-canonical-preview.json'),JSON.stringify({source:'isolated_postgres_fixture_not_production',records},null,2)+'\n');
 }
 console.log(JSON.stringify({kia_ev3_completion_sync:'passed',profiles:7,new_facts:39,decimal_ac:10.5,
  gt_not_gt_line:true,preliminary_excluded_from_hard_range:true,foreign_locale_and_price_isolation:true,
  real_price_trigger:true,rollback_replay:true,production_writes:0,paid_calls:0}));
}finally{await db.close();}
