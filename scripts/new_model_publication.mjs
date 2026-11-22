import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {newModelAdapter} from './new_model_adapters.mjs';
import {buildImagePlan} from './model_image_sync.mjs';
import {ADAPTER as ID_BUZZ_ADAPTER} from './volkswagen_id_buzz_publication.mjs';
import {ADAPTER as XPENG_G6_ADAPTER,assertXpG6PublicVariants} from './xpeng_g6_publication.mjs';
import {ADAPTER as XPENG_G9_ADAPTER} from './xpeng_g9_publication.mjs';
import {ADAPTER as RENAULT4_PAIR_ADAPTER,renault4LocatorRow} from './renault_4_pair_publication.mjs';
import {ADAPTER as TAVASCAN_ADAPTER} from './cupra_tavascan_drive_publication.mjs';
import {ADAPTER as POLESTAR3_ADAPTER} from './polestar_3_publication.mjs';
import {ADAPTER as IONIQ5_ADAPTER} from './hyundai_ioniq5_publication.mjs';
import {ADAPTER as PUMA_ADAPTER} from './ford_puma_gen_e_publication.mjs';
import {ADAPTER as GLB_ADAPTER} from './mercedes_glb_publication.mjs';
import {PUMA_ALIAS,PUMA_MODEL,planPumaIdentity,pumaIdentitySnapshot,writeReviewedPumaIdentity} from './ford_puma_identity.mjs';
import {MANUFACTURER_FROM_PRICE} from '../src/price-evidence.js';
import {catalogHash} from './sync_public_catalog.mjs';
import {catalogWithComparableTimes} from './isolated_catalog_review.mjs';
import {assertDcChargePower,assertDcStorageForDrafts} from './verify_exact_dc_migration.mjs';

export const CORE_FIELDS=['wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw',
 'ac_charge_kw','boot_liters','tow_kg','seats','drivetrain'];
const bounds={wltp_range_km:[50,1200],wltp_consumption_kwh_100km:[5,50],battery_kwh:[5,300],
 ac_charge_kw:[1,50],boot_liters:[50,3500],tow_kg:[0,4000],seats:[1,9]};
const plain=v=>JSON.parse(JSON.stringify(v));
export const publicationHash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const same=(a,b,message)=>assert.deepEqual(plain(a),plain(b),message);
const one=(rows,message)=>{assert.equal(rows.length,1,message);return rows[0];};
const fieldsEqual=(row,expected)=>{for(const[k,v]of Object.entries(expected))assert.equal(typeof v==='number'?Number(row[k]):row[k],v,'Saved field disagrees: '+k);};
const sourceMetadata=s=>({country:s.country??'SE',language:s.language??'sv',source_authority:s.source_authority??'manufacturer',
 authorization_evidence_url:s.authorization_evidence_url??null});
const savedSource=s=>({url:s.final_url,content_hash:s.content_hash,http_status:200,...sourceMetadata(s)});
const uuidFor=(adapter,model,identity)=>{
 const h=publicationHash({adapter,model,identity});return `${h.slice(0,8)}-${h.slice(8,12)}-5${h.slice(13,16)}-a${h.slice(17,20)}-${h.slice(20,32)}`;
};
const modelTargets=(intake,id)=>intake.drafts.map(draft=>({id:uuidFor(intake.adapter,id,draft.manufacturer_identity),draft}));
const fresh=(s,now)=>{
 assert.equal(s.status,'reachable');assert.equal(s.http_status,200);assert.match(s.content_hash,/^[a-f0-9]{64}$/);
 const age=now.getTime()-Date.parse(s.fetched_at);assert(Number.isFinite(age)&&age>=-60000&&age<=900000,'Fresh source capture required');
 const u=new URL(s.final_url);assert.equal(u.protocol,'https:');assert(!u.username&&!u.password&&!u.hash);
};
export function validateNewModelIntake(intake,now=new Date()){
 const policy=newModelAdapter(intake.adapter);policy.validateIntake(intake,now);
 assert(intake.drafts.length>0&&intake.drafts.length<=policy.maxVariants);
 const names=new Set(),identities=new Set(),sources=new Map(intake.sources.map(s=>[s.final_url,s]));
 assert.equal(sources.size,intake.sources.length,'Duplicate exact source URL');
 for(const s of [...intake.sources,intake.market.source])fresh(s,now);
 for(const s of intake.sources){
  const meta=sourceMetadata(s);
  if(!policy.mixedSources||s.shared||s.final_url===policy.primaryUrl){
   same(meta,{country:'SE',language:'sv',source_authority:'manufacturer',authorization_evidence_url:null},'Expected Swedish manufacturer evidence');
  }else if(meta.source_authority==='authorized_dealer'){
   const proof=sources.get(meta.authorization_evidence_url);
   assert(proof&&proof.country==='SE'&&proof.source_authority==='manufacturer','Require exact manufacturer authorization evidence');
  }
 }
 for(const r of intake.drafts){
  assert(!names.has(r.variant_name.toLowerCase())&&!identities.has(r.manufacturer_identity),'Duplicate version identity');
  names.add(r.variant_name.toLowerCase());identities.add(r.manufacturer_identity);
  assert(Number.isFinite(r.extraction_confidence)&&r.extraction_confidence>=0.92&&r.extraction_confidence<=1);
  same(Object.keys(r.facts).sort(),[...CORE_FIELDS].sort(),'A complete technical profile is mandatory');
  for(const[field,value]of Object.entries(r.facts)){
   if(field==='drivetrain')assert(['FWD','RWD','AWD'].includes(value));
   else if(field==='dc_charge_kw')assertDcChargePower(value);
   else{assert(Number.isFinite(value)&&value>=bounds[field][0]&&value<=bounds[field][1]);
    if(!['battery_kwh','ac_charge_kw','wltp_consumption_kwh_100km'].includes(field))assert(Number.isInteger(value));}
   const p=r.field_evidence[field];assert.equal(p.value,value);assert.equal(p.variant_name,r.variant_name);
   assert.equal(p.source_hash,sources.get(p.source_url)?.content_hash);assert(typeof p.quote==='string'&&p.quote.length>5);
  }
  const p=r.price_evidence;assert(Number.isInteger(p.value)&&p.value>=100000&&p.value<=3000000);
  assert(['list_price','campaign_price','dealer_offer'].includes(p.price_type)
   || ([PUMA_ADAPTER,GLB_ADAPTER].includes(policy.adapter)&&p.price_type===MANUFACTURER_FROM_PRICE&&p.price_valid_until===null));
  assert.equal(p.source_hash,sources.get(p.source_url)?.content_hash);assert(p.quote?.trim());
  if(p.price_valid_until)assert(p.price_valid_until>=now.toISOString().slice(0,10));
  if(p.price_type==='campaign_price')assert(p.price_valid_until);
 }
 return policy;
}
export function validateNewModelImage(models,intake,image){
 const policy=newModelAdapter(intake.adapter);
 assert.equal(image.model_key,policy.imageKey);assert.equal(image.content_sha256,policy.imageHash);
 buildImagePlan(models,[intake.model],{schema_version:1,assets:[image]});
 const body=policy.localOnly&&policy.readPrivateImage
  ?policy.readPrivateImage(image):readFileSync(new URL('../public'+image.asset_url,import.meta.url));
 assert.equal(createHash('sha256').update(body).digest('hex'),image.content_sha256,'Reviewed image bytes changed');
 assert(body[0]===255&&body[1]===216&&body[2]===255);
 for(const draft of intake.drafts){
  const variant=policy.variantPhoto?.(draft);
  if(!variant)continue;
  buildImagePlan(models,[intake.model],{schema_version:1,assets:[variant.image]});
  assert.equal(variant.image.content_sha256,draft.identity_evidence.reviewed_photo_sha256);
  assert.equal(variant.image.source_url,draft.identity_evidence.reviewed_photo_source);
  assert.equal(createHash('sha256').update(variant.body).digest('hex'),variant.image.content_sha256,'Reviewed variant image bytes changed');
  assert(variant.body[0]===255&&variant.body[1]===216&&variant.body[2]===255);
 }
 return image;
}
export function buildNewModelPlan(snapshot,intake,image,now=new Date()){
 const policy=validateNewModelIntake(intake,now),m=intake.model;
 const model=one(snapshot.canonical_models.filter(r=>r.normalized_brand===m.normalized_brand&&r.normalized_model===m.normalized_model),'One existing canonical discovery draft required');
 assert.equal(model.brand,m.brand);assert.equal(model.model,m.model);assert.notEqual(model.validation_status,'rejected');
 assert([null,m.body_type].includes(model.body_type));
 assert(!snapshot.canonical_model_variants.some(r=>r.canonical_model_id===model.id),'Existing variants need a separate refresh, not new-model publication');
 const alias=one(snapshot.model_aliases.filter(r=>r.normalized_brand===m.normalized_brand&&r.normalized_model===m.normalized_model),'One resolved alias required');
 assert.equal(alias.canonical_model_id,model.id);assert.equal(alias.needs_mapping,false);assert(!alias.model_group);
 assert.equal(alias.alias_rule,policy.aliasRule);assert(Number(alias.confidence)>=0.92);
 const scopedDiscovery=policy.scopedDiscovery;
 const marketKey=scopedDiscovery?.market??m;
 for(const field of ['brand_raw','model_raw'])assert.equal(alias[field],(scopedDiscovery?.alias??intake.market.row)[field],'Exact raw alias required: '+field);
 const market=one(snapshot.market_models.filter(r=>r.normalized_brand===marketKey.normalized_brand&&r.normalized_model===marketKey.normalized_model&&r.fuel_type_raw==='EL'),'One exact BEV market row required');
 assert(!market.needs_mapping&&!market.model_group);assert([null,model.id].includes(market.canonical_model_id));
 for(const f of ['brand_raw','model_raw'])assert.equal(market[f],intake.market.row[f]);
 scopedDiscovery?.check(snapshot,model,market);
 assert(!market.last_seen_month||market.last_seen_month<=intake.market.row.last_seen_month,'Do not overwrite a newer market index');
 validateNewModelImage(snapshot.canonical_models,intake,image);
 assert(!model.image_url||model.image_url===image.asset_url,'Existing model photo needs separate review');
 const relevant=snapshot.manufacturer_sources.filter(r=>intake.sources.some(s=>s.final_url===r.url));
 return plain({adapter:intake.adapter,expected_model:model,expected_alias:alias,expected_market:market,
  expected_monthly:snapshot.market_model_monthly_stats.filter(r=>r.market_model_id===market.id),expected_sources:relevant,
  intake,image,targets:modelTargets(intake,model.id)});
}
const TABLES=['canonical_model_variants','canonical_models','manufacturer_sources','extracted_variant_drafts',
 'model_aliases','market_models','market_model_monthly_stats'];
const DATE_FIELDS=new Set(['price_valid_until','first_seen_month','last_seen_month','month']);
function calendarDates(input){
 const rows=plain(input);
 for(const row of rows)for(const key of DATE_FIELDS)if(row[key]!=null){
  assert.match(row[key],/^\d{4}-\d{2}-\d{2}(?:T00:00:00\.000Z)?$/,'Unexpected SQL DATE representation');
  row[key]=row[key].slice(0,10);
 }
 return rows;
}
export async function publicationSnapshot(client,lock=false){
 const result={};for(const table of TABLES){
  result[table]=calendarDates((await client.query('SELECT * FROM public.'+table+' ORDER BY id'+(lock?' FOR UPDATE':''))).rows);
 }return result;
}
const variantPhotoFields=(intake,draft)=>{
 const variant=newModelAdapter(intake.adapter).variantPhoto?.(draft);
 return variant?{variant_image_url:variant.image.asset_url,variant_image_source_url:variant.image.source_url}:{};
};
const variantFacts=(draft,source,batch,intake)=>({...draft.facts,...variantPhotoFields(intake,draft),price_sek:draft.price_evidence.value,
 price_type:draft.price_evidence.price_type,price_valid_until:draft.price_evidence.price_valid_until,
 price_source_url:draft.price_evidence.source_url,price_source_hash:draft.price_evidence.source_hash,
 price_source_quote:draft.price_evidence.quote,price_source_name:intake.sources.find(s=>s.final_url===draft.price_evidence.source_url).source_name,
 price_verified_at:new Date(intake.sources.find(s=>s.final_url===draft.price_evidence.source_url).fetched_at).toISOString(),price_refresh_batch_id:batch,
 source_url:source.final_url,source_hash:source.content_hash,extraction_confidence:draft.extraction_confidence,validation_status:'published'});
const quoteFor=draft=>[...new Set(Object.values(draft.field_evidence).map(e=>e.source_url+' | '+e.quote))].join(' | ');
const receiptPayload=(plan,target,batch)=>({adapter:plan.adapter,publication_batch_id:batch,canonical_variant_id:target.id,
 manufacturer_identity:target.draft.manufacturer_identity,model:plan.intake.model,model_evidence:plan.intake.model_evidence,
 ...(target.draft.identity_evidence?{identity_evidence:target.draft.identity_evidence}:{}),
 field_evidence:target.draft.field_evidence,price_evidence:target.draft.price_evidence,
 market_evidence:plan.intake.market,image_evidence:plan.image,source_decisions:plan.intake.source_decisions,
 sources:plan.intake.sources});
export function rollingRegistrations(rows,month){
 const [y,m]=month.split('-').map(Number),end=y*12+m-1;
 let total=0;
 for(let i=end-11;i<=end;i++){
  const key=Math.floor(i/12)+'-'+String(i%12+1).padStart(2,'0')+'-01';
  const matches=rows.filter(r=>r.month===key&&r.county===null&&r.municipality===null);
  assert(matches.length<=1,'Ambiguous monthly totals');if(!matches.length)return null;
  assert(Number.isSafeInteger(matches[0].registrations)&&matches[0].registrations>=0);total+=matches[0].registrations;
 }return total;
}
const marketTotal=plan=>rollingRegistrations([...plan.expected_monthly.filter(r=>r.month!==plan.intake.market.row.last_seen_month),
 {month:plan.intake.market.row.last_seen_month,registrations:plan.intake.market.row.registrations_last_month,county:null,municipality:null}],plan.intake.market.row.last_seen_month);

export function assertIdBuzzReleaseScope(freshReport,approvedReport,approvedHash,now=new Date()){
 for(const report of [freshReport,approvedReport]){
  assert.equal(report.status,'ready_for_review');
  assert.equal(report.apply_allowed,false);
  assert.equal(report.production_writes,0);
  assert.equal(report.plan.adapter,ID_BUZZ_ADAPTER);
  assert.equal(report.plan.intake.adapter,ID_BUZZ_ADAPTER);
  assert.equal(report.plan.targets.length,2);
  assert.equal(report.plan_hash,publicationHash(report.plan));
 }
 assert.equal(approvedReport.plan_hash,approvedHash,'Wrong approved ID. Buzz scope');
 assert(Date.parse(freshReport.evidence_expires_at)>now.getTime(),'Fresh ID. Buzz evidence expired');
 const {plan:fresh}=freshReport,{plan:approved}=approvedReport;
 const without=(value,keys)=>JSON.parse(JSON.stringify(value,(key,entry)=>keys.includes(key)?undefined:entry));
 same(without(fresh.intake.market.source,['fetched_at']),without(approved.intake.market.source,['fetched_at']),'Reviewed market workbook changed');
 const captured=['fetched_at','content_hash','source_hash'];
 const releaseScope=({intake,targets,...scope})=>({...scope,
  intake:without(intake,captured),targets:without(targets,captured)});
 same(releaseScope(fresh),releaseScope(approved),'Reviewed facts, evidence, or production scope changed');
 validateNewModelIntake(fresh.intake,now);
}

export function applyIdBuzzRelease(client,freshReport,approvedReport,approvedHash,now=new Date()){
 assertIdBuzzReleaseScope(freshReport,approvedReport,approvedHash,now);
 return applyModelTransaction(client,freshReport.plan,freshReport.plan_hash,now,ID_BUZZ_ADAPTER);
}

export async function applyXpG6Release(client,freshReport,reviewedReport,ui,approvedHash,now=new Date(),baselineHash){
 assert.match(approvedHash??'',/^[a-f0-9]{64}$/,'Supply the exact approved G6 plan hash');
 assert.equal(reviewedReport.plan_hash,approvedHash,'Wrong approved G6 scope');
 const {proveG6ReviewScope}=await import('./revalidate_xpeng_g6_release.mjs');
 proveG6ReviewScope(reviewedReport,freshReport,ui,now);
 if(baselineHash===undefined){
  const {PGlite}=await import('@electric-sql/pglite');
  assert(client instanceof PGlite,'Require the reviewed production catalog hash before G6 apply');
 }else{
  assert.match(baselineHash,/^[a-f0-9]{64}$/);
  assert.equal(baselineHash,ui.main_review.baseline_sha256,'Unreviewed G6 catalog hash');
 }
 return applyModelTransaction(client,freshReport.plan,freshReport.plan_hash,now,XPENG_G6_ADAPTER,baselineHash);
}

async function anonymousProjection(client){
 await client.query('SET LOCAL ROLE anon');
 // JSONB retains SQL numeric types and avoids driver-specific calendar dates.
 const variants=(await client.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')).rows.map(r=>r.row);
 const models=(await client.query('SELECT to_jsonb(m) AS row FROM public.public_ev_models m ORDER BY id')).rows.map(r=>r.row);
 await client.query('RESET ROLE');
 return {variants,models};
}

async function verifyScopedReadback(client,plan,baseline,check,verifyDelta){
 const projection=await anonymousProjection(client),id=plan.expected_model.id;
 const variants=projection.variants.filter(row=>row.canonical_model_id===id);
 assert.deepEqual(variants.map(row=>row.id).sort(),plan.targets.map(t=>t.id).sort(),'Unexpected public variant IDs');
 check(variants,plan);
 const model=one(projection.models.filter(row=>row.id===id),'Reviewed model must be visible anonymously');
 fieldsEqual(model,{
  brand:plan.intake.model.brand,model:plan.intake.model.model,body_type:plan.intake.model.body_type,
  market_seen:true,
  ...Object.fromEntries(['available_confirmed','discontinued_candidate','coming_or_low_volume'].map(k=>[k,plan.expected_model[k]]))});
 assertPublicModelPhoto(model,plan);
 if(baseline){
  same(projection.variants.filter(row=>row.canonical_model_id!==id),baseline.variants,'Existing public variants changed');
  same(projection.models.filter(row=>row.id!==id),baseline.models,'Existing public models changed');
 }
 if(verifyDelta)verifyDelta(baseline.variants,projection.variants);
}

export async function applyRenault4PairRelease(client,fresh,reviewed,ui,approvedHash,now=new Date()){
 const {proveRenault4PairRelease,assertRenault4PairPublishedRows}=await import('./renault_4_pair_release_scope.mjs');
 proveRenault4PairRelease(reviewed,fresh,ui,approvedHash,now);
 return applyModelTransaction(client,fresh.plan,fresh.plan_hash,now,RENAULT4_PAIR_ADAPTER,undefined,
  {baselineHash:reviewed.database_baseline_hash,check:assertRenault4PairPublishedRows});
}

export async function applyTavascanDriveRelease(client,fresh,reviewed,ui,approval,now=new Date()){
 const {proveTavascanRelease,verifyTavascanProjection}=await import('./cupra_tavascan_release_scope.mjs');
 proveTavascanRelease(reviewed,fresh,ui,approval,now);
 return applyModelTransaction(client,fresh.plan,fresh.plan_hash,now,TAVASCAN_ADAPTER,undefined,{
  baselineHash:reviewed.public_projection_sha256,
  baselineError:'Public catalog changed inside the release transaction',
  verifyDelta:(before,after)=>verifyTavascanProjection(before,after,fresh.plan,reviewed.public_projection_sha256)});
}

export async function applyXpG9Release(client,fresh,reviewed,approval,now=new Date()){
 const {proveFreshG9Release,validateG9PostG6Delta}=await import('./xpeng_g9_release_review.mjs');
 proveFreshG9Release(reviewed,fresh,approval,now);
 assert.match(reviewed.database_baseline_sha256,/^[a-f0-9]{64}$/,'Require the reviewed public baseline');
 return applyModelTransaction(client,fresh.plan,fresh.plan_hash,now,XPENG_G9_ADAPTER,undefined,{
  baselineHash:reviewed.database_baseline_sha256,
  verifyDelta:(before,after)=>validateG9PostG6Delta(before,after,fresh.plan)});
}

export async function applyPolestar3Release(client,fresh,reviewed,scopeHash,now=new Date()){
 const {proveFreshPolestar3Release,validatePolestar3Delta}=await import('./polestar_3_release_scope.mjs');
 proveFreshPolestar3Release(reviewed,fresh,scopeHash,now);
 return applyModelTransaction(client,fresh.plan,fresh.plan_hash,now,POLESTAR3_ADAPTER,undefined,{
  baselineHash:reviewed.database_baseline_sha256,
  verifyDelta:(before,after)=>validatePolestar3Delta(before,after,fresh.plan)});
}

export function applyNewModelPlan(client,plan,expectedHash,now=new Date()){
 return applyModelTransaction(client,plan,expectedHash,now,null);
}

function assertPublicModelPhoto(model,plan){
 // Older model views omit photos; the canonical row and every public variant still require the exact photo.
 if(Object.hasOwn(model,'image_url')||Object.hasOwn(model,'image_source_url'))
  fieldsEqual(model,{image_url:plan.image.asset_url,image_source_url:plan.image.source_url});
}

async function verifyG6BeforeCommit(client,plan,baseline){
 const projection=await anonymousProjection(client),id=plan.expected_model.id;
 const variants=projection.variants.filter(row=>row.canonical_model_id===id);
 assert.deepEqual(variants.map(row=>row.id).sort(),plan.targets.map(t=>t.id).sort(),'G6 public variant IDs or visibility changed');
 assertXpG6PublicVariants(variants,plan);
 const model=one(projection.models.filter(row=>row.id===id),'G6 model must be visible anonymously');
 fieldsEqual(model,{
  brand:plan.intake.model.brand,model:plan.intake.model.model,body_type:plan.intake.model.body_type,
  market_seen:true,
  ...Object.fromEntries(['available_confirmed','discontinued_candidate','coming_or_low_volume'].map(k=>[k,plan.expected_model[k]]))});
 assertPublicModelPhoto(model,plan);
 if(baseline){
  same(projection.variants.filter(row=>row.canonical_model_id!==id),baseline.variants,'Existing public variants changed');
  same(projection.models.filter(row=>row.id!==id),baseline.models,'Existing public models changed');
 }
}

export async function applyIoniq5Release(client,fresh,reviewed,ui,approvedHash,now=new Date()){
 const {proveIoniq5ReleaseScope,assertIoniq5PublishedRows}=await import('./hyundai_ioniq5_release_scope.mjs');
 const {assertVariantPhotoInstalled}=await import('./verify_variant_photo_migration.mjs');
 proveIoniq5ReleaseScope(reviewed,fresh,ui,approvedHash,now);
 return applyModelTransaction(client,fresh.plan,fresh.plan_hash,now,IONIQ5_ADAPTER,undefined,{
  baselineHash:ui.baseline.database_baseline_sha256,requireMigration:assertVariantPhotoInstalled,check:assertIoniq5PublishedRows,
  baselineError:'Anonymous catalog changed before Ioniq 5 writes'});
}

export async function applyGlbRelease(client,fresh,scope,target,approvedHash,now=new Date()){
 const {proveGlbRelease,assertGlbPriceMigration,assertGlbPublishedRows}=await import('./mercedes_glb_release.mjs');
 proveGlbRelease(scope,fresh,target,approvedHash,now);
 return applyModelTransaction(client,fresh,publicationHash(fresh),now,GLB_ADAPTER,undefined,{
  baselineHash:scope.database_baseline_sha256,requireMigration:assertGlbPriceMigration,check:assertGlbPublishedRows,
  baselineError:'Anonymous catalog changed before GLB writes'});
}

async function applyModelTransaction(client,plan,expectedHash,now,approvedAdapter,baselineHash,scopedRelease=null){
 assert.equal(publicationHash(plan),expectedHash,'Prepared publication packet changed');
 const policy=validateNewModelIntake(plan.intake,now);
 assert(approvedAdapter===null||policy.adapter===approvedAdapter,'Approved adapter mismatch');
 if(policy.localOnly&&approvedAdapter===null){
  const {PGlite}=await import('@electric-sql/pglite');
  assert(client instanceof PGlite,'This pilot is restricted to a local PGlite database');
 }
 validateNewModelImage([plan.expected_model],plan.intake,plan.image);
 return modelWriteTransaction(client,()=>applyModelRows(client,plan,expectedHash,now,policy,approvedAdapter,baselineHash,scopedRelease));
}

async function modelWriteTransaction(client,write){
 let committed=false;
 await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE READ WRITE');
 try{
  await client.query('SET LOCAL search_path=pg_catalog');await client.query("SET LOCAL lock_timeout='10s'");
  await client.query('SELECT pg_advisory_xact_lock(7240040)');
  const result=await write();
  if(result.committed){await client.query('COMMIT');committed=true;}
  return result;
 }finally{if(!committed)await client.query('ROLLBACK');}
}

export async function applyPumaAtomicLocally(client,packet,expectedHash,now=new Date()){
 const {PGlite}=await import('@electric-sql/pglite');
 assert(client instanceof PGlite,'Atomic Puma rehearsal is restricted to local PGlite');
 assert(!client.isInTransaction(),'Atomic Puma rehearsal owns its transaction');
 return applyPumaAtomicTransaction(client,packet,expectedHash,now,null);
}

export async function applyPumaRelease(client,reviewed,fresh,commit,approval,now=new Date()){
 const {assertPumaPriceMigration,assertPumaPublishedRows,provePumaRelease}=await import('./ford_puma_release_scope.mjs');
 provePumaRelease(reviewed,fresh,commit,approval,now);
 return applyPumaAtomicTransaction(client,fresh,publicationHash(fresh),now,{
  requireMigration:assertPumaPriceMigration,check:assertPumaPublishedRows,
 });
}

async function applyPumaAtomicTransaction(client,packet,expectedHash,now,release){
 assert.equal(publicationHash(packet),expectedHash,'Prepared Puma packet changed');
 assert.equal(packet.status,'puma_atomic_rehearsal_only');
 assert.equal(packet.publication_approved,false);
 const {identity,intake,image}=packet;
 same(planPumaIdentity(identity.expected),identity,'Invalid reviewed Puma identity');
 const policy=validateNewModelIntake(intake,now);
 assert.equal(policy.adapter,PUMA_ADAPTER);
 assert.equal(policy.localOnly,true);
 assert.match(packet.baseline_sha256,/^[a-f0-9]{64}$/);
 const parent=identity.expected.models[0].id;
 const ids={model_id:uuidFor(PUMA_ADAPTER,parent,'canonical-bev-model'),alias_id:uuidFor(PUMA_ADAPTER,parent,'exact-bev-alias')};
 validateNewModelImage([{id:ids.model_id,...PUMA_MODEL}],intake,image);
 return modelWriteTransaction(client,async()=>{
  await release?.requireMigration(client);
  const before=await publicationSnapshot(client,true);
  const hasParent=before.canonical_models.some(row=>row.id===ids.model_id);
  if(release)assert(!hasParent,'Puma is already present; recover the committed release without inserting again');
  const projected=await anonymousProjection(client);
  assert.equal(catalogHash(catalogWithComparableTimes(projected.variants.filter(row=>row.canonical_model_id!==ids.model_id))),
   packet.baseline_sha256,'Anonymous catalog changed before the Puma transaction');
  let plan;
  if(hasParent){
   const model=one(before.canonical_models.filter(row=>row.id===ids.model_id),'Puma replay parent missing');
   const market=one(before.market_models.filter(row=>row.id===identity.market_id),'Puma replay market row missing');
   fieldsEqual(model,{...PUMA_MODEL,available_confirmed:false,discontinued_candidate:false,coming_or_low_volume:false});
   policy.scopedDiscovery.check(before,model,market);
   assert.equal(before.canonical_model_variants.filter(row=>row.canonical_model_id===ids.model_id).length,2,'Partial Puma replay');
   plan={adapter:PUMA_ADAPTER,intake,image,expected_model:model,expected_market:identity.expected.market.find(row=>row.id===identity.market_id),
    expected_monthly:identity.expected.months.filter(row=>row.market_model_id===identity.market_id),
    targets:modelTargets(intake,ids.model_id)};
  }else{
   same(await pumaIdentitySnapshot(client),identity.expected,'Puma identity changed before the transaction');
   same(before.manufacturer_sources.filter(row=>intake.sources.some(s=>s.final_url===row.url)),
    packet.expected_sources,'Puma source changed before the transaction');
   await writeReviewedPumaIdentity(client,identity,ids);
   plan=buildNewModelPlan(await publicationSnapshot(client,true),intake,image,now);
  }
  const written=await applyModelRows(client,plan,expectedHash,now,policy,PUMA_ADAPTER,undefined,
   release?{check:release.check,baselineHash:packet.baseline_sha256}:null);
  const after=await pumaIdentitySnapshot(client);
  fieldsEqual(one(after.aliases.filter(row=>row.id===ids.alias_id),'Exact Puma alias was not retained'),
   {...PUMA_ALIAS,canonical_model_id:ids.model_id});
  same(after.aliases.filter(row=>row.id!==ids.alias_id),identity.expected.aliases,'Legacy Puma alias changed');
  same(after.models.filter(row=>row.id!==ids.model_id),identity.expected.models,'Legacy Puma model changed');
  same(after.market.filter(row=>row.id!==identity.market_id),identity.expected.market.filter(row=>row.id!==identity.market_id),
   'Non-BEV Puma market state changed');
  const oldMonths=new Set(identity.expected.months.map(row=>row.id));
  same(after.months.filter(row=>oldMonths.has(row.id)),identity.expected.months,'Original Puma registration history changed');
  const month=one(after.months.filter(row=>row.market_model_id===identity.market_id&&row.month===intake.market.row.last_seen_month
   &&row.county===null&&row.municipality===null),'Exact October Puma registration missing');
  fieldsEqual(month,{brand_raw:'FORD',model_raw:'PUMA',fuel_type_raw:'EL',registrations:intake.market.row.registrations_last_month});
  same(after.months.filter(row=>!oldMonths.has(row.id)),oldMonths.has(month.id)?[]:[month],
   'Unexpected Puma registration rows in the transaction');
  return {...written,atomic_identity:true,alias_id:ids.alias_id,variant_plan:hasParent?null:plan};
 });
}

async function applyModelRows(client,plan,expectedHash,now,policy,approvedAdapter,baselineHash,scopedRelease){
  await assertDcStorageForDrafts(client,plan.intake.drafts);
  const modelId=plan.expected_model.id;
  const before=await publicationSnapshot(client,true),m=one(before.canonical_models.filter(r=>r.id===modelId),'Canonical parent missing');
  const existing=before.canonical_model_variants.filter(r=>r.canonical_model_id===modelId);
  const verifyG6=policy.adapter===XPENG_G6_ADAPTER;
  const g6Baseline=verifyG6&&!existing.length?await anonymousProjection(client):null;
  if(baselineHash!==undefined){
   assert(g6Baseline,'G6 release requires the original production catalog');
   assert.equal(catalogHash(g6Baseline.variants),baselineHash,'Anonymous catalog changed before G6 writes');
  }
  const renault4Release=approvedAdapter===RENAULT4_PAIR_ADAPTER;
  const check=scopedRelease?.check??policy.verifyPublic;
  if(scopedRelease){
   assert(!existing.length,'An approved release requires an unpublished canonical model');
   await scopedRelease.requireMigration?.(client);
  }
  const primary=plan.intake.sources.find(s=>s.final_url===policy.primaryUrl);assert(primary);
  if(existing.length){
   assert.equal(existing.length,plan.targets.length,'Partial/colliding publication');
   for(const field of ['brand','model','normalized_brand','normalized_model','available_confirmed','discontinued_candidate','coming_or_low_volume'])same(m[field],plan.expected_model[field],'Applied parent changed: '+field);
   fieldsEqual(m,{body_type:plan.intake.model.body_type,image_url:plan.image.asset_url,image_source_url:plan.image.source_url,market_seen:true});
   for(const t of plan.targets){
    const row=one(existing.filter(r=>r.id===t.id),'Different version identity');
    fieldsEqual(row,{...variantFacts(t.draft,primary,expectedHash,plan.intake),canonical_model_id:modelId,variant_name:t.draft.variant_name,source_quote:quoteFor(t.draft)});
    const saved=one(before.extracted_variant_drafts.filter(d=>d.canonical_model_id===modelId&&d.variant_name===t.draft.variant_name),'Missing published staging receipt');
    fieldsEqual(saved,{canonical_model_id:modelId,source_id:row.source_id,validation_status:'published'});same(saved.extraction_payload,receiptPayload(plan,t,expectedHash),'Applied evidence changed');
    const source=one(before.manufacturer_sources.filter(s=>s.id===row.source_id),'Missing exact source');assert.equal(source.url,primary.final_url);assert.equal(source.content_hash,primary.content_hash);
   }
   for(const source of plan.intake.sources)fieldsEqual(one(before.manufacturer_sources.filter(s=>s.url===source.final_url),'Missing saved source'),savedSource(source));
   const market=one(before.market_models.filter(r=>r.id===plan.expected_market.id),'Missing applied market row');
   fieldsEqual(market,{canonical_model_id:modelId,first_seen_month:plan.expected_market.first_seen_month||plan.intake.market.row.last_seen_month,last_seen_month:plan.intake.market.row.last_seen_month,
    registrations_last_month:plan.intake.market.row.registrations_last_month,registrations_ytd:plan.intake.market.row.registrations_ytd,
    registrations_12m:marketTotal(plan),source_url:plan.intake.market.source.final_url});
   if(verifyG6)await verifyG6BeforeCommit(client,plan);
   if(check)await verifyScopedReadback(client,plan,null,check);
   return{committed:false,already_applied:true,variants_inserted:0,canonical_variant_ids:plan.targets.map(t=>t.id),paid_calls:0};
  }
  same(m,plan.expected_model,'Concurrent model change');
  same(before.model_aliases.find(r=>r.id===plan.expected_alias.id),plan.expected_alias,'Concurrent alias change');
  same(before.market_models.find(r=>r.id===plan.expected_market.id),plan.expected_market,'Concurrent market change');
  same(before.market_model_monthly_stats.filter(r=>r.market_model_id===plan.expected_market.id),plan.expected_monthly,'Concurrent monthly change');
  same(before.manufacturer_sources.filter(r=>plan.intake.sources.some(s=>s.final_url===r.url)),plan.expected_sources,'Concurrent source change');
  // Revalidate the original resolved scope, not only the caller-provided hash.
  same(buildNewModelPlan(before,plan.intake,plan.image,now),plan,'Publication scope changed');
  const publicBefore=check?await anonymousProjection(client):null;
  if(scopedRelease)assert.equal(catalogHash(catalogWithComparableTimes(publicBefore.variants)),
   scopedRelease.baselineHash,scopedRelease.baselineError??'Anonymous catalog changed before scoped writes');
  if(publicBefore){
   assert(!publicBefore.models.some(row=>row.id===modelId),'Unexpected existing public model');
   assert(!publicBefore.variants.some(row=>row.canonical_model_id===modelId),'Unexpected existing public variants');
  }
  const changedSources=new Set(),newDraftIds=new Set(),sourceIds=new Map();
  for(const s of plan.intake.sources){
   const old=before.manufacturer_sources.find(r=>r.url===s.final_url);
   if(old?.canonical_model_id&&old.canonical_model_id!==modelId)assert(s.shared&&old.canonical_model_id===null,'Source belongs to another model');
   if(s.shared){
    if(!old&&renault4Release){
     const record={...renault4LocatorRow(s),title:'Renault Sverige: aterforsaljarregister',source_name:'Renault Sverige',
      fetched_at:s.fetched_at,verified_at:s.fetched_at,extraction_status:'validated'};
     const values=Object.values(record);
     const {rows:[inserted]}=await client.query(
      `INSERT INTO public.manufacturer_sources(${Object.keys(record).join(',')}) VALUES(${values.map((_,i)=>'$'+(i+1)).join(',')}) RETURNING id`,values);
     sourceIds.set(s.final_url,inserted.id);changedSources.add(inserted.id);continue;
    }
    if(renault4Release&&old)fieldsEqual(old,renault4LocatorRow(s));
    assert(old&&old.brand===plan.intake.model.brand&&old.model==='*'&&old.canonical_model_id===null);
    assert.equal(old.content_hash,s.content_hash,'Shared source needs separate refresh');assert.equal(old.http_status,200);assert.equal(old.source_authority,'manufacturer');
    assert.equal(old.country,'SE');assert.equal(old.language,'sv');assert.equal(old.final_url,s.final_url);
    assert.equal(old.source_validation,'reachable_official_model_source');
    sourceIds.set(s.final_url,old.id);continue;
   }
   assert(!old||old.brand===plan.intake.model.brand&&old.model===plan.intake.model.model);
   assert(!old||!before.canonical_model_variants.some(v=>v.source_id===old.id),'Existing source must not be overwritten');
   const meta=sourceMetadata(s);
   const result=await client.query(`INSERT INTO public.manufacturer_sources(canonical_model_id,brand,model,source_type,url,title,country,language,
    fetched_at,content_hash,http_status,final_url,source_validation,source_authority,source_name,extraction_status,verified_at,is_primary,authorization_evidence_url)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,200,$5,$11,$12,$13,'validated',$9,$14,$15)
    ON CONFLICT(url) DO UPDATE SET canonical_model_id=excluded.canonical_model_id,source_type=excluded.source_type,
     fetched_at=excluded.fetched_at,content_hash=excluded.content_hash,http_status=200,final_url=excluded.final_url,
     source_validation=excluded.source_validation,source_authority=excluded.source_authority,source_name=excluded.source_name,
     country=excluded.country,language=excluded.language,authorization_evidence_url=excluded.authorization_evidence_url,
     extraction_status='validated',verified_at=excluded.verified_at,is_primary=excluded.is_primary,updated_at=now() RETURNING id`,
    [modelId,plan.intake.model.brand,plan.intake.model.model,s.source_type,s.final_url,plan.intake.model.model+': versionsbundet underlag',
     meta.country,meta.language,s.fetched_at,s.content_hash,meta.source_authority==='authorized_dealer'?'reachable_authorized_dealer_model_source':'reachable_official_model_source',
     meta.source_authority,s.source_name,s.final_url===primary.final_url,meta.authorization_evidence_url]);
   sourceIds.set(s.final_url,result.rows[0].id);changedSources.add(result.rows[0].id);
  }
  for(const t of plan.targets){
   assert(!before.canonical_model_variants.some(r=>r.id===t.id),'Canonical ID collision');
   assert(!before.extracted_variant_drafts.some(r=>r.source_url===primary.final_url&&r.variant_name===t.draft.variant_name),'Staging collision requires separate review');
   const d=t.draft,sourceId=sourceIds.get(primary.final_url),q=quoteFor(d),payload=receiptPayload(plan,t,expectedHash);
   const cols=['canonical_model_id','source_id','brand','model','variant_name',...CORE_FIELDS,'price_sek','price_type','price_valid_until',
    'source_url','source_hash','source_quote','extraction_confidence','extraction_payload','validation_status','validation_errors'];
   const vals=[modelId,sourceId,plan.intake.model.brand,plan.intake.model.model,d.variant_name,...CORE_FIELDS.map(f=>d.facts[f]),d.price_evidence.value,
    d.price_evidence.price_type,d.price_evidence.price_valid_until,primary.final_url,primary.content_hash,q,d.extraction_confidence,JSON.stringify(payload),'validated','[]'];
   const staged=await client.query('INSERT INTO public.extracted_variant_drafts('+cols.join(',')+') VALUES('+vals.map((_,i)=>'$'+(i+1)).join(',')+') RETURNING id',vals);
   const fact=variantFacts(d,primary,expectedHash,plan.intake);
   const canonical={id:t.id,canonical_model_id:modelId,variant_name:d.variant_name,...fact,source_id:sourceId,source_quote:q};
   const names=Object.keys(canonical),values=Object.values(canonical);
   await client.query('INSERT INTO public.canonical_model_variants('+names.join(',')+',published_at) VALUES('+values.map((_,i)=>'$'+(i+1)).join(',')+',now())',values);
   await client.query("UPDATE public.extracted_variant_drafts SET validation_status='published',updated_at=now() WHERE id=$1",[staged.rows[0].id]);newDraftIds.add(staged.rows[0].id);
  }
  await client.query(`UPDATE public.canonical_models SET body_type=$1,image_url=$2,image_source_url=$3,image_verified_at=$4,
   market_seen=true,updated_at=now() WHERE id=$5`,[plan.intake.model.body_type,plan.image.asset_url,plan.image.source_url,now.toISOString(),modelId]);
  const marketId=plan.expected_market.id,mr=plan.intake.market.row,month=mr.last_seen_month;
  const monthly=before.market_model_monthly_stats.filter(r=>r.market_model_id===marketId),matching=monthly.filter(r=>r.month===month&&r.county===null&&r.municipality===null);
  assert(matching.length<=1);if(matching.length)assert.equal(matching[0].registrations,mr.registrations_last_month,'Conflicting monthly fact');
  else await client.query(`INSERT INTO public.market_model_monthly_stats(market_model_id,month,brand_raw,model_raw,fuel_type_raw,registrations)
   VALUES($1,$2,$3,$4,'EL',$5)`,[marketId,month,mr.brand_raw,mr.model_raw,mr.registrations_last_month]);
  const first=plan.expected_market.first_seen_month&&plan.expected_market.first_seen_month<month?plan.expected_market.first_seen_month:month;
  await client.query(`UPDATE public.market_models SET canonical_model_id=$1,first_seen_month=$2,last_seen_month=$3,
   registrations_last_month=$4,registrations_ytd=$5,registrations_12m=$8,source_url=$6,source_name='Mobility Sweden',imported_at=now(),updated_at=now() WHERE id=$7`,
   [modelId,first,month,mr.registrations_last_month,mr.registrations_ytd,plan.intake.market.source.final_url,marketId,marketTotal(plan)]);
  const after=await publicationSnapshot(client),newIds=new Set(plan.targets.map(t=>t.id));
  assert.equal(after.canonical_model_variants.length,before.canonical_model_variants.length+plan.targets.length);
  same(after.canonical_model_variants.filter(r=>!newIds.has(r.id)),before.canonical_model_variants,'Existing variants changed');
  same(after.canonical_models.filter(r=>r.id!==modelId),before.canonical_models.filter(r=>r.id!==modelId),'Other model changed');
  const savedModel=after.canonical_models.find(r=>r.id===modelId),allowedModel=new Set(['body_type','image_url','image_source_url','image_verified_at','market_seen','updated_at']);
  same(Object.fromEntries(Object.entries(savedModel).filter(([k])=>!allowedModel.has(k))),Object.fromEntries(Object.entries(m).filter(([k])=>!allowedModel.has(k))),'Model identity or availability changed');
  fieldsEqual(savedModel,{body_type:plan.intake.model.body_type,image_url:plan.image.asset_url,image_source_url:plan.image.source_url,market_seen:true});
  same(after.model_aliases,before.model_aliases,'Aliases changed');
  same(after.market_models.filter(r=>r.id!==marketId),before.market_models.filter(r=>r.id!==marketId),'Other market row changed');
  same(after.market_model_monthly_stats.filter(r=>r.market_model_id!==marketId),before.market_model_monthly_stats.filter(r=>r.market_model_id!==marketId),'Other monthly row changed');
  for(const old of monthly)same(after.market_model_monthly_stats.find(r=>r.id===old.id),old,'Historical month changed');
  same(after.manufacturer_sources.filter(r=>!changedSources.has(r.id)),before.manufacturer_sources.filter(r=>!changedSources.has(r.id)),'Other/shared source changed');
  same(after.extracted_variant_drafts.filter(r=>!newDraftIds.has(r.id)),before.extracted_variant_drafts,'Other staging row changed');
  for(const t of plan.targets){
   fieldsEqual(one(after.canonical_model_variants.filter(r=>r.id===t.id),'Missing inserted version'),{...variantFacts(t.draft,primary,expectedHash,plan.intake),variant_name:t.draft.variant_name,source_quote:quoteFor(t.draft)});
   const d=one(after.extracted_variant_drafts.filter(r=>newDraftIds.has(r.id)&&r.variant_name===t.draft.variant_name),'Missing saved staging');
   same(d.extraction_payload,receiptPayload(plan,t,expectedHash),'Saved evidence changed');assert.equal(d.validation_status,'published');
   fieldsEqual(d,{...t.draft.facts,price_sek:t.draft.price_evidence.value,price_type:t.draft.price_evidence.price_type,
    price_valid_until:t.draft.price_evidence.price_valid_until,source_url:primary.final_url,source_hash:primary.content_hash,source_quote:quoteFor(t.draft)});
  }
  for(const s of plan.intake.sources){
   const saved=one(after.manufacturer_sources.filter(r=>r.id===sourceIds.get(s.final_url)),'Missing saved source');
   fieldsEqual(saved,savedSource(s));
   if(s.shared&&renault4Release)fieldsEqual(saved,renault4LocatorRow(s));
  }
  fieldsEqual(one(after.market_models.filter(r=>r.id===marketId),'Missing saved market identity'),{canonical_model_id:modelId,
   first_seen_month:first,last_seen_month:month,registrations_last_month:mr.registrations_last_month,
   registrations_ytd:mr.registrations_ytd,registrations_12m:marketTotal(plan),source_url:plan.intake.market.source.final_url});
  validateNewModelImage(after.canonical_models,plan.intake,plan.image);
  if(approvedAdapter===ID_BUZZ_ADAPTER){
   await client.query('SET LOCAL ROLE anon');
   const {rows:models}=await client.query('SELECT id,market_seen,available_confirmed FROM public.public_ev_models WHERE id=$1',[modelId]);
   fieldsEqual(one(models,'The reviewed model must be publicly readable'),{market_seen:true,available_confirmed:m.available_confirmed});
   const variants=calendarDates((await client.query('SELECT * FROM public.public_ev_variants WHERE canonical_model_id=$1',[modelId])).rows);
   assert.equal(variants.length,2,'Only two reviewed variants may be public');
   for(const target of plan.targets){
    const expected=variantFacts(target.draft,primary,expectedHash,plan.intake);
    delete expected.price_refresh_batch_id;
    delete expected.price_verified_at;
    fieldsEqual(one(variants.filter(row=>row.id===target.id),'Missing reviewed public variant'),
     {...expected,variant_name:target.draft.variant_name,image_url:plan.image.asset_url,image_source_url:plan.image.source_url,
      available_confirmed:m.available_confirmed});
   }
   await client.query('RESET ROLE');
  }
  if(verifyG6)await verifyG6BeforeCommit(client,plan,g6Baseline);
  if(check)await verifyScopedReadback(client,plan,publicBefore,check,scopedRelease?.verifyDelta);
  return{committed:true,already_applied:false,variants_inserted:plan.targets.length,canonical_variant_ids:[...newIds],
   model_id:modelId,publication_batch_id:expectedHash,sources_changed:changedSources.size,paid_calls:0,
   ...(verifyG6||check?{anonymous_before_commit:true}:{})};
}
