import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync, realpathSync, statSync} from 'node:fs';
import {basename, dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {GLB_MARKET, MARKET_URLS, MODEL as primary, URLS} from './mercedes_glb_review.mjs';
import {MANUFACTURER_FROM_PRICE} from '../src/price-evidence.js';

const root = realpathSync(fileURLToPath(new URL('../', import.meta.url)));
export const ADAPTER = 'mercedes_glb_electric_x244_sweden_my27';
export const MODEL = Object.freeze({brand:'Mercedes-Benz', model:'Glb',
  normalized_brand:'mercedes benz', normalized_model:'glb', body_type:'SUV'});
const imageKey = 'mercedes benz|glb', publisherId = 'mercedes-glb-se-private-review';
const press = JSON.parse(readFileSync(new URL('../src/press-image-publishers.json', import.meta.url), 'utf8'))[publisherId];
const photoUrl = press.origin + press.approved_image_paths[0];
const filename = 'mercedes-benz-glb-press-' + press.approved_source_sha256.slice(0,12) + '.jpg';
const reviewedPhoto = 'b580aab4f8bd1c484f3006c9a39db3a4b7292f1297b0e3429515b636a9c0f6b9';
const profile = [
  ['GLB 250+ Advanced Edition','2446131_SE3',619000,631,15.8,1500,'RWD','dealer-250.html'],
  ['GLB 350 4MATIC Advanced Edition','2446441_SE3',659000,614,15.9,2000,'AWD','dealer-350.html'],
].map(([name,code,price,wltp_range_km,wltp_consumption_kwh_100km,tow_kg,drivetrain,yearProof])=>({
  name,code,price,yearProof,identity:'SE|MY27|X244|'+code+'|5',
  facts:{wltp_range_km,wltp_consumption_kwh_100km,tow_kg,drivetrain,battery_kwh:85,
    dc_charge_kw:320,ac_charge_kw:11,boot_liters:540,seats:5},
}));
const sourceTypes = {'model.html':'manufacturer_model_page','prices.html':'manufacturer_price_list',
  'appointment.html':'manufacturer_page','dealer-250.html':'authorized_dealer_model_page',
  'dealer-350.html':'authorized_dealer_model_page'};
const metadata = name => {
  const dealer = name.startsWith('dealer-');
  return {country:'SE', language:'sv', source_type:sourceTypes[name], shared:false,
    source_name:dealer?'Mobility Motors: H\u00f6glunds Bil':'Mercedes-Benz Sverige',
    source_authority:dealer?'authorized_dealer':'manufacturer',
    authorization_evidence_url:dealer?URLS['appointment.html']:null};
};
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
function fields(row, expected) {
  for (const [key,value] of Object.entries(expected)) assert.deepEqual(row?.[key],value,'GLB scope changed: '+key);
}
function privateRoot() {
  const folder=join(root,'data','local','release-data');
  assert.equal(realpathSync(folder),folder);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(folder));
  return folder;
}
function evidence(folder, name, limit) {
  assert.equal(basename(name),name);
  const path=join(folder,name);
  assert.equal(realpathSync(path),path);
  const info=statSync(path);
  assert(info.isFile()&&info.size>0&&info.size<=limit);
  return readFileSync(path);
}
const photoDir = () => join(privateRoot(),'mercedes-glb-press-2026-11-21-pinned');
export function readGlbImage() {
  const bytes=evidence(photoDir(),'glb-mynewsdesk-3376630.json',32768);
  assert.equal(hash(bytes),reviewedPhoto,'Reviewed press photo receipt changed');
  const r=JSON.parse(bytes);
  fields(r,{model_key:imageKey,publisher_id:publisherId,source_url:photoUrl,evidence_url:photoUrl,
    license_url:photoUrl,license_id:press.license_id,asset_url:press.approved_asset_url,original_url:press.approved_asset_url,
    full_frame:true,review_filename:filename,width:5000,height:3333,author:press.asset_author,credit:press.asset_author+' / pressbild',
    content_sha256:press.approved_source_sha256,source_content_sha256:press.approved_source_sha256,
    evidence_quote:press.permission_excerpt+' | '+press.condition_excerpt});
  assert.match(r.metadata_sha256,/^[a-f0-9]{64}$/);
  assert.equal(hash(evidence(photoDir(),r.metadata_sha256+'.html',2_000_000)),r.metadata_sha256);
  const keys=['model_key','publisher_id','source_url','evidence_url','license_url','license_id','evidence_quote','full_frame',
    'content_sha256','source_content_sha256','metadata_sha256','author','credit','original_url'];
  return {...Object.fromEntries(keys.map(key=>[key,r[key]])),status:'documented',reviewed_at:'2026-11-21',
    asset_url:'/media/vehicles/'+filename,downloaded_from:r.asset_url,reviewed_candidate_sha256:reviewedPhoto,
    usage_scope:'independent_vehicle_editorial',prohibited_uses:['advertising','commercial_promotion','endorsement'],
    model_image_notice:'Pressbild av eldrivna GLB. Utrustningen kan skilja mellan versioner.'};
}
export function readPrivateGlbImage(image) {
  assert.deepEqual(image,readGlbImage(),'Require the exact unaltered GLB press photo');
  return evidence(photoDir(),filename,12_000_000);
}

export function readGlbCapture(path) {
  const folder=realpathSync(path);
  assert.equal(folder,resolve(path));
  assert.equal(dirname(folder),privateRoot());
  assert.match(basename(folder),/^mercedes-glb-x244-review-[a-z0-9]+$/i);
  const bytes=evidence(folder,'review.json',100_000);
  execFileSync(process.execPath,['scripts/mercedes_glb_review.mjs','--replay',folder],
    {cwd:root,timeout:90000,windowsHide:true});
  assert.equal(hash(evidence(folder,'review.json',100_000)),hash(bytes));
  const r=JSON.parse(bytes);
  fields(r,{status:'private_glb_x244_source_review',model:'GLB Electric',brand:MODEL.brand,
    publication_approved:false,database_writes:0,paid_calls:0});
  assert(r.photo_candidates.includes(photoUrl),'Importer launch must still link the exact press image');
  const receipt = name => {
    const source=r.sources[name];
    fields(source,{url:URLS[name]??MARKET_URLS[name],http_status:200});
    return {final_url:source.url,content_hash:source.sha256,fetched_at:r.captured_at,status:'reachable',http_status:200};
  };
  const drafts=profile.map(p=>{
    const row=r.variants.find(v=>v.name===p.name);
    const {model_offer_evidence:corroboration,...price}=row.price_evidence;
    return {variant_name:p.name,manufacturer_identity:p.identity,extraction_confidence:1,
      facts:Object.fromEntries(Object.entries(row.technical_facts).map(([key,proof])=>[key,proof.value])),
      field_evidence:Object.fromEntries(Object.entries(row.technical_facts).map(([key,proof])=>
        [key,{...proof,variant_name:p.name}])),
      price_evidence:{...price,scope:'swedish_advanced_edition_manufacturer_from',corroboration},
      identity_evidence:{model_year:row.model_year,model_year_marker:row.model_year_marker,configuration_id:row.configuration_id,
        manufacturer_code:row.manufacturer_code,vehicle_series:row.manufacturer_body,market:row.market,fuel:row.fuel_type,
        year_corroboration:row.year_corroboration}};
  });
  const model_evidence={value:'SUV',source_url:primary,source_hash:receipt('model.html').content_hash,
    quote:'GLB Elektrisk | X244 | SUV'};
  const intake={adapter:ADAPTER,model:MODEL,model_evidence,drafts,
    sources:Object.keys(sourceTypes).map(name=>({...receipt(name),...metadata(name)})),
    source_decisions:{wltp_qualification:r.wltp_qualification,dealer_authorization:r.dealer_authorization,
      photo_launch:receipt('launch.html')},
    market:{sheet:r.market_index.sheet,
      row:{...r.market_index.row,needs_mapping:false,source_name:'Mobility Sweden',source_url:MARKET_URLS['market.xlsx']},
      source:{...receipt('market.xlsx'),source_name:'Mobility Sweden',source_type:'mobility_sweden_export'},
      article:receipt('market.html')}};
  validateIntake(intake);
  return {intake,reviewHash:hash(bytes)};
}

function validateIntake(intake) {
  fields(intake,{adapter:ADAPTER,model:MODEL});
  assert.equal(intake.sources.length,Object.keys(sourceTypes).length);
  const sources=new Map(intake.sources.map(s=>[s.final_url,s]));
  for (const name of Object.keys(sourceTypes)) fields(sources.get(URLS[name]),metadata(name));
  const bind=(proof,name,value)=>{
    const source=URLS[name];
    fields(proof,{value,source_url:source,source_hash:sources.get(source).content_hash});
    assert(typeof proof.quote==='string'&&proof.quote.length>5);
  };
  bind(intake.model_evidence,'model.html','SUV');
  fields(intake.market,{sheet:'Elbil ranking',
    row:{...GLB_MARKET,needs_mapping:false,source_name:'Mobility Sweden',source_url:MARKET_URLS['market.xlsx']}});
  fields(intake.market.source,{final_url:MARKET_URLS['market.xlsx'],source_type:'mobility_sweden_export',
    content_hash:'1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6'});
  fields(intake.market.article,{final_url:MARKET_URLS['market.html'],http_status:200,status:'reachable',
    fetched_at:intake.market.source.fetched_at});
  assert.match(intake.market.article.content_hash,/^[a-f0-9]{64}$/);
  assert.match(intake.source_decisions.wltp_qualification,/Samtliga utsl\u00e4ppsv\u00e4rden g\u00e4ller bil i grundversion\./);
  assert.equal(intake.drafts.length,profile.length);
  for (const p of profile) {
    const row=intake.drafts.find(d=>d.variant_name===p.name);
    fields(row,{manufacturer_identity:p.identity,facts:p.facts,extraction_confidence:1});
    const i=row.identity_evidence;
    fields(i,{model_year:2027,model_year_marker:'MJ-807',manufacturer_code:p.code,vehicle_series:'X244',market:'SE',fuel:'BEV'});
    assert(i.configuration_id.startsWith('sv_SE__'+p.code+'__')&&/(?:^|_)MJ-807(?:_|$)/.test(i.configuration_id));
    bind(i.year_corroboration,p.yearProof,2027);
    for(const [key,value] of Object.entries(p.facts)) bind(row.field_evidence[key],'model.html',value);
    assert.equal(row.field_evidence.battery_kwh.basis,'usable');
    assert.equal(row.field_evidence.tow_kg.requires_towing_equipment,true);
    bind(row.price_evidence,'prices.html',p.price);
    bind(row.price_evidence.corroboration,'model.html',p.price);
    const amount=new Intl.NumberFormat('sv-SE').format(p.price).replace(/\u00a0/g,' ');
    fields(row.price_evidence,{scope:'swedish_advanced_edition_manufacturer_from',price_type:MANUFACTURER_FROM_PRICE,
      price_valid_until:null,quote:p.name+' fr\u00e5n '+amount+' kr'});
  }
}

function checkDiscovery(snapshot,model,market) {
  assert(!snapshot.market_models.some(row=>row.id!==market.id && row.canonical_model_id===model.id),
    'Only the exact EL row may use the electric GLB canonical model');
}
function verifyPublic(rows,plan) {
  assert.equal(rows.length,profile.length);
  for (const p of profile) {
    const matching=rows.filter(r=>r.variant_name===p.name);
    assert.equal(matching.length,1);
    fields(matching[0],{...p.facts,brand:MODEL.brand,model:MODEL.model,body_type:MODEL.body_type,source_url:primary,
      price_type:MANUFACTURER_FROM_PRICE,price_sek:p.price,price_source_url:URLS['prices.html'],price_valid_until:null,
      validation_status:'published',market_seen:true,available_confirmed:plan.expected_model.available_confirmed,
      image_url:plan.image.asset_url,image_source_url:photoUrl});
  }
}
export const policy={adapter:ADAPTER,primaryUrl:primary,aliasRule:'mobility_sweden_exact_raw_name',imageKey,
  imageHash:press.approved_source_sha256,maxVariants:2,localOnly:true,mixedSources:true,readPrivateImage:readPrivateGlbImage,
  scopedDiscovery:{market:GLB_MARKET,check:checkDiscovery},validateIntake,verifyPublic};
