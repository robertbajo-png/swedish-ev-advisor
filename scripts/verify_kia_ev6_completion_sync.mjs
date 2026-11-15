import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {buildSpecPlan,applySpecPlan,specPlanHash,validateSpecDraft,urls} from './kia_ev6_completion_sync.mjs';
import {TECHNICAL_FIELDS} from './kia_spec_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';
import {normalizePublicVariants} from '../functions/_shared/advisor-core.mjs';
import {matchAdvisorVariants,ruleRequirements} from '../src/advisor-matching.js';
const intake=JSON.parse(await readFile('tests/fixtures/kia_ev6_completion.json','utf8'));
const snapshot=JSON.parse(await readFile('public/data/public_ev_variants.json','utf8'));
const now=new Date(Math.max(...intake.drafts.flatMap(r=>[r.source,...r.supporting_sources].map(s=>Date.parse(s.fetched_at)))));
for(const draft of intake.drafts)validateSpecDraft(draft,now);
const db=new PGlite();
try{
 const fields=[...TECHNICAL_FIELDS,'ac_charge_kw'];
 const columns=fields.map(f=>f+(f==='drivetrain'?' text':f==='ac_charge_kw'?' numeric(5,2)':' numeric')).join(',');
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
 INSERT INTO canonical_models VALUES('ev6','Kia','Ev6',null,now()),('outside','Kia','Ev5','SUV',now());
 INSERT INTO manufacturer_sources(id,canonical_model_id,brand,model,url,verified_at) VALUES
 ('legacy-price','outside','Kia','EV4','https://www.kia.com/se/kopa/prislista/','2026-10-27'),
 ('outside-source','outside','Kia','Ev5','https://www.kia.com/se/nya-bilar/ev5/specifikationer/','2026-11-14'),
 ('shared-price',null,'Kia','*','https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf','2026-11-14'),
 ('legacy-model','ev6','Kia','EV6','https://www.kia.com/se/nya-bilar/ev6/upptack/','2026-11-12');
 INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek,source_id,validation_status)
 VALUES('outside','outside','Outside EV5',123456,'outside-source','published');`);
 const migration=await readFile('database/migrations/020_price_only_refresh.sql','utf8');
 await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
 await db.exec(`CREATE TRIGGER invalidate_replaced_price_evidence BEFORE UPDATE OF price_sek,price_type,price_valid_until
 ON canonical_model_variants FOR EACH ROW EXECUTE FUNCTION public.invalidate_replaced_price_evidence();`);
 for(const[i,draft]of intake.drafts.entries()){
  const baseline=snapshot.records.find(r=>r.brand===draft.brand&&r.model===draft.model&&r.variant_name===draft.variant_name);assert(baseline);
  const names=['id','canonical_model_id','variant_name','validation_status','price_sek','price_type','price_valid_until',
   'price_source_url','price_source_hash','price_source_quote','price_verified_at','price_source_name',...fields];
  const gt=draft.variant_name==='EV6 GT',gaps=gt?fields.filter(f=>f!=='drivetrain'):['ac_charge_kw','seats','wltp_consumption_kwh_100km'];
  const row={...baseline,id:'ev6-'+i,canonical_model_id:'ev6',price_valid_until:null,...Object.fromEntries(gaps.map(f=>[f,null])),
   ...(gt?{drivetrain:'GT'}:{})};
  await db.query('INSERT INTO canonical_model_variants('+names.join(',')+') VALUES('+names.map((_,n)=>'$'+(n+1)).join(',')+')',names.map(f=>row[f]??null));
 }
 const joined=async()=>(await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
 const before=await joined(),models=(await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,sourcesBefore=(await db.query('SELECT * FROM manufacturer_sources ORDER BY id')).rows;
 const plan=buildSpecPlan(before,intake,now);
 for(const mutate of [r=>r.facts.ac_charge_kw=11,r=>r.facts.dc_charge_kw=350,r=>r.facts.wltp_range_km=550,
  r=>r.facts.battery_kwh=77.4,r=>r.facts.boot_liters=1250,r=>r.facts.tow_kg=100,r=>r.facts.drivetrain='GT',
  r=>r.variant_name='EV6 AWD',r=>r.source.http_status=403,r=>r.source.fetched_at='2020-01-01',
  r=>r.supporting_sources.pop(),r=>r.field_evidence.ac_charge_kw.quote='22 kW',r=>r.price_evidence.value=12360,
  r=>r.price_evidence.price_type='campaign_price',r=>r.price_evidence.quote='EV6 PLUS AWD Long Range 771,400 kr',
  r=>r.price_evidence.page=1,r=>r.model_facts.body_type='SUV']){
  const invalid=structuredClone(intake);mutate(invalid.drafts[2]);assert.throws(()=>buildSpecPlan(before,invalid,now));
 }
 assert.throws(()=>buildSpecPlan(before,{...intake,drafts:intake.drafts.slice(0,2)},now));
 const badPrior=structuredClone(before);badPrior.find(r=>r.variant_name==='EV6 RWD').drivetrain='GT';
 assert.throws(()=>buildSpecPlan(badPrior,intake,now),'GT-to-AWD resolution must not apply to regular RWD');
 const conflict=structuredClone(before);conflict.find(r=>r.variant_name==='EV6 GT').battery_kwh=77.4;
 assert.throws(()=>buildSpecPlan(conflict,intake,now),'Unrelated technical conflicts stay held');
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Late fixture failure'; END $$;
 CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));assert.deepEqual(await joined(),before);
 assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
 assert.deepEqual((await db.query('SELECT * FROM manufacturer_sources ORDER BY id')).rows,sourcesBefore);
 await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
 const result=await applySpecPlan(db,plan,specPlanHash(plan),now);
 assert.equal(result.variants_updated,3);assert.equal(result.new_technical_values,14);assert.equal(result.prices_changed,0);assert.equal(result.models_changed,1);
 assert.deepEqual((await joined()).find(r=>r.id==='outside'),before.find(r=>r.id==='outside'));
 for(const id of ['legacy-price','outside-source'])assert.deepEqual((await db.query('SELECT * FROM manufacturer_sources WHERE id=$1',[id])).rows[0],sourcesBefore.find(s=>s.id===id));
 const current=(await joined()).filter(r=>r.canonical_model_id==='ev6').map(r=>({...r,
  price_valid_until:r.price_valid_until instanceof Date?r.price_valid_until.toISOString().slice(0,10):r.price_valid_until,
  ...Object.fromEntries(fields.filter(f=>f!=='drivetrain').map(f=>[f,Number(r[f])]))}));
 for(const r of current){assert.equal(r.ac_charge_kw,10.5);assert.equal(r.price_type,'list_price');assert.equal(r.price_valid_until,'2026-11-30');assert(r.price_refresh_batch_id);}
 const gt=current.find(r=>r.variant_name==='EV6 GT'),notes=specQualifications({...gt,image_url:'/media/vehicles/kia-ev6-press-5e19a7dc0d49.jpg'});
 assert.equal(gt.drivetrain,'AWD');assert.match(notes.rangeNote,/550 km/);assert.match(notes.consumptionNote,/609 hk/);
 assert.match(notes.practicalNote,/480/);assert.match(notes.imageNotice,/EV6 Baseline/);
 assert(!notes.specSources.some(s=>s.url.startsWith(urls.technical)));
 assert.match(specQualifications(current.find(r=>r.variant_name==='EV6 AWD')).consumptionNote,/17,0/);
 const sources=(await db.query('SELECT * FROM manufacturer_sources')).rows;
 for(const url of [urls.energy,urls.price_pdf]){assert.equal(sources.find(s=>s.url===url).model,'*');assert.equal(sources.find(s=>s.url===url).canonical_model_id,null);}
 assert.equal(sources.find(s=>s.url===urls.model).model,'EV6');assert.equal(sources.find(s=>s.url===urls.price_pdf).id,'shared-price');
 assert.equal(sources.find(s=>s.url===urls.gt_germany).country,'DE');
 assert.equal((await db.query('SELECT * FROM extracted_variant_drafts')).rows.length,3);
 const normalized=normalizePublicVariants(JSON.parse(JSON.stringify(current)));
 const requirements={...ruleRequirements({budget:800000,range:450,need:'allround'}),awd_required:true};
 assert.equal(matchAdvisorVariants(normalized,requirements,{asOf:'2026-11-15'}).matching_count,2);
 assert.equal(matchAdvisorVariants(normalized,requirements,{asOf:'2026-12-01'}).matching_count,0);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 console.log(JSON.stringify({kia_ev6_completion_sync:'passed',profiles:3,new_facts:14,decimal_ac:10.5,
  gt_drivetrain_resolved:true,exact_standard_wheels_and_gt_scope:true,real_price_trigger:true,rollback_replay:true,production_writes:0,paid_calls:0}));
}finally{await db.close();}
