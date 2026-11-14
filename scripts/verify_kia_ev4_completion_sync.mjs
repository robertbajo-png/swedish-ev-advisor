import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {buildSpecPlan,applySpecPlan,specPlanHash,validateSpecDraft,urls} from './kia_ev4_completion_sync.mjs';
import {TECHNICAL_FIELDS} from './kia_spec_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';
import {normalizePublicVariants} from '../functions/_shared/advisor-core.mjs';
import {matchAdvisorVariants,ruleRequirements} from '../src/advisor-matching.js';
const intake=JSON.parse(await readFile('tests/fixtures/kia_ev4_completion.json','utf8'));
const snapshot=JSON.parse(await readFile('public/data/public_ev_variants.json','utf8'));
const now=new Date(Math.max(...intake.drafts.flatMap(r=>[r.source,...r.supporting_sources].map(s=>Date.parse(s.fetched_at)))));
for(const row of intake.drafts)validateSpecDraft(row,now);
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
 INSERT INTO canonical_models VALUES('ev4','Kia','Ev4',null,now()),('outside','Kia','Ev3','SUV',now());
 INSERT INTO manufacturer_sources(id,canonical_model_id,brand,model,url,verified_at) VALUES
 ('legacy-price','ev4','Kia','EV4','https://www.kia.com/se/kopa/prislista/','2026-10-27'),
 ('outside-source','outside','Kia','Ev3','https://www.kia.com/se/nya-bilar/ev3/upptack/','2026-11-14'),
 ('shared-price',null,'Kia','*','https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf','2026-11-14');
 INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek,source_id,validation_status)
 VALUES('outside','outside','Outside EV3',123456,'outside-source','published');`);
 const migration=await readFile('database/migrations/020_price_only_refresh.sql','utf8');
 await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
 await db.exec(`CREATE TRIGGER invalidate_replaced_price_evidence BEFORE UPDATE OF price_sek,price_type,price_valid_until
 ON canonical_model_variants FOR EACH ROW EXECUTE FUNCTION public.invalidate_replaced_price_evidence();`);
 for(const [i,draft]of intake.drafts.entries()){
  const baseline=snapshot.records.find(r=>r.brand===draft.brand&&r.model===draft.model&&r.variant_name===draft.variant_name);assert(baseline);
  const names=['id','canonical_model_id','variant_name','validation_status','price_sek','price_type','price_valid_until',
   'price_source_url','price_source_hash','price_source_quote','price_verified_at','price_source_name',...fields];
  // Preserve the pre-completion scenario even once the real public snapshot is updated.
  const gaps=i<2?['ac_charge_kw','seats']:fields;
  const row={...baseline,id:'ev4-'+i,canonical_model_id:'ev4',price_valid_until:null,...Object.fromEntries(gaps.map(f=>[f,null]))};
  await db.query('INSERT INTO canonical_model_variants('+names.join(',')+') VALUES('+names.map((_,n)=>'$'+(n+1)).join(',')+')',names.map(f=>row[f]??null));
 }
 const joined=async()=>(await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
 const before=await joined(),models=(await db.query('SELECT * FROM canonical_models ORDER BY id')).rows;
 const sourcesBefore=(await db.query('SELECT * FROM manufacturer_sources ORDER BY id')).rows;
 const plan=buildSpecPlan(before,intake,now);
 for(const mutate of [r=>r.facts.ac_charge_kw=11,r=>r.facts.ac_charge_kw=22,r=>r.facts.wltp_range_km=584,
  r=>r.facts.battery_kwh=58.3,r=>r.facts.boot_liters=377,r=>r.facts.boot_liters=390,r=>r.facts.tow_kg=100,
  r=>r.facts.wltp_consumption_kwh_100km=19.2,r=>r.variant_name='EV4 GT Line AWD Long Range',
  r=>r.source.http_status=403,r=>r.source.fetched_at='2020-01-01',r=>r.supporting_sources.pop(),
  r=>r.field_evidence.ac_charge_kw.quote='22 kW',r=>r.price_evidence.value=20000,
  r=>r.price_evidence.price_type='campaign_price',r=>r.price_evidence.price_valid_until=null,
  r=>r.qualifications.gt_tyre_basis.quote='505 km for every tyre',r=>r.model_facts.body_type='Sedan']){
  const invalid=structuredClone(intake);mutate(invalid.drafts[2]);assert.throws(()=>buildSpecPlan(before,invalid,now));
 }
 assert.throws(()=>buildSpecPlan(before,{...intake,drafts:intake.drafts.slice(0,2)},now));
 await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Late fixture failure'; END $$;
 CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));assert.deepEqual(await joined(),before);
 assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
 assert.deepEqual((await db.query('SELECT * FROM manufacturer_sources ORDER BY id')).rows,sourcesBefore);
 await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
 const result=await applySpecPlan(db,plan,specPlanHash(plan),now);
 assert.equal(result.variants_updated,3);assert.equal(result.new_technical_values,13);assert.equal(result.prices_changed,0);assert.equal(result.models_changed,1);
 assert.deepEqual((await joined()).find(r=>r.id==='outside'),before.find(r=>r.id==='outside'));
 for(const id of ['legacy-price','outside-source'])assert.deepEqual((await db.query('SELECT * FROM manufacturer_sources WHERE id=$1',[id])).rows[0],sourcesBefore.find(s=>s.id===id));
 const current=(await joined()).filter(r=>r.canonical_model_id==='ev4').map(r=>({...r,
  price_valid_until:r.price_valid_until instanceof Date?r.price_valid_until.toISOString().slice(0,10):r.price_valid_until,
  ...Object.fromEntries(fields.filter(f=>f!=='drivetrain').map(f=>[f,Number(r[f])]))}));
 for(const r of current){assert.equal(r.ac_charge_kw,10.5);assert.equal(r.price_type,'list_price');assert.equal(r.price_valid_until,'2026-11-30');assert(r.price_refresh_batch_id);assert(!specQualifications(r).rangeIsTarget);}
 const gt=current.find(r=>r.variant_name.includes('(292hk)')),notes=specQualifications({...gt,image_url:'/media/vehicles/kia-ev4-press-0446f33614bd.jpg'});
 assert.match(notes.rangeNote,/Pirelli/);assert.match(notes.rangeNote,/473/);assert.match(notes.consumptionNote,/17,9/);
 assert.match(notes.practicalNote,/359/);assert.match(notes.practicalNote,/377/);assert.match(notes.imageNotice,/GT Line halvkombi/);
 assert(!notes.specSources.some(s=>s.url.startsWith(urls.technical)),'GT sources must not cite the GT Line technical table');
 assert(specQualifications(current.find(r=>r.variant_name==='EV4 GT Line FWD Long Range')).specSources.some(s=>s.url.startsWith(urls.technical)));
 const sources=(await db.query('SELECT * FROM manufacturer_sources')).rows;
 for(const url of [urls.energy,urls.price_pdf]){assert.equal(sources.find(s=>s.url===url).model,'*');assert.equal(sources.find(s=>s.url===url).canonical_model_id,null);}
 assert.equal(sources.find(s=>s.url===urls.price_pdf).id,'shared-price');assert.equal(sources.find(s=>s.url===urls.poland).country,'PL');
 assert.equal(sources.find(s=>s.url===urls.gt_germany).country,'DE');assert.equal(sources.find(s=>s.url===urls.gt).source_type,'manufacturer_model_page');
 const normalized=normalizePublicVariants(JSON.parse(JSON.stringify(current)));assert.equal(normalized.length,3);
 const requirements={...ruleRequirements({budget:800000,range:500,need:'allround'}),awd_required:true};
 assert.equal(matchAdvisorVariants(normalized,requirements,{asOf:'2026-11-14'}).matching_count,2);
 assert.equal(matchAdvisorVariants(normalized,requirements,{asOf:'2026-12-01'}).matching_count,0);
 assert.equal((await db.query('SELECT count(*)::int n FROM extracted_variant_drafts')).rows[0].n,3);
 await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
 console.log(JSON.stringify({kia_ev4_completion_sync:'passed',profiles:3,new_facts:13,decimal_ac:10.5,
  exact_gt_hatchback_and_tyre_boot_qualifiers:true,legacy_source_and_other_vehicle_preserved:true,
  shared_source_reused:true,real_price_trigger:true,rollback_replay:true,production_writes:0,paid_calls:0}));
}finally{await db.close();}
