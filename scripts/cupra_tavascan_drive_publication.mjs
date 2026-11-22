import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readDriveWltpEvidence, samples } from './cupra_tavascan_stock_wltp.mjs';

export const ADAPTER = 'cupra_tavascan_drive_sweden_my26_local_v1';
export const MODEL = {brand:'Cupra',model:'Tavascan',normalized_brand:'cupra',normalized_model:'tavascan',body_type:'SUV'};
export const VARIANT = 'Drive Swedish Edition MY26';
export const FACTS = {wltp_range_km:553,wltp_consumption_kwh_100km:15.8,battery_kwh:77,dc_charge_kw:135,
  ac_charge_kw:11,boot_liters:540,tow_kg:1000,seats:5,drivetrain:'RWD'};
const factory = 'KR1BCD/P80/PF0/MY26/19';
const modelUrl = 'https://www.cupraofficial.se/bilar/tavascan';
const priceUrl = 'https://www.cupraofficial.se/content/dam/countries/se/cupra-website/prislistor/tavascan/cupra-tavascan-modellar-26.pdf';
const dealerUrl = 'https://dinbil.se/cupra/bilar-i-lager/alla-bilar-i-lager/lyk12h';
const dealerProof = 'https://bilarilager.vwgroup.se/cupra/LYK12H';
const wheelUrl = 'https://lagerbilar.vwgroup.se/cupra/DRX34F';
const mainHardware = 'https://bilarilager.vwgroup.se/cupra/EWB33D';
const supportHardware = 'https://bilarilager.vwgroup.se/cupra/EZK46X';
const imageSource = 'https://www.mynewsdesk.com/dk/seat-danmark/images/dsc00621-bred-punktum-jpg-3072079';
const imageFile = 'cupra-tavascan-press-9c79705e02a2.jpg';
const imageHash = '9c79705e02a2ca65b8a9aeefc2718b83272453dd132c509c576e4262dd38a697';
const photoReceiptHash = 'c4b89fe9bb4cb209a801f8b30546fff96d7b7529e2685fd36e1afd420fadbb44';
const root = fileURLToPath(new URL('..', import.meta.url));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const sourceRules = new Map([
  [priceUrl,'price_list_pdf'], [modelUrl,'manufacturer_model_page'],
  [dealerUrl,'authorized_dealer_stock_page'], [dealerProof,'importer_page'],
  [wheelUrl,'importer_page'], [mainHardware,'importer_page'], [supportHardware,'importer_page'],
  ...samples.flatMap(s=>[[s.page,'manufacturer_model_page'],[s.importer,'importer_page']]),
]);
const marketRow = {brand_raw:'CUPRA',model_raw:'TAVASCAN',fuel_type_raw:'EL',normalized_brand:'cupra',normalized_model:'tavascan',
  last_seen_month:'2026-10-01',registrations_last_month:63,registrations_ytd:692};
const sourceForField = {wltp_range_km:samples[0].page,wltp_consumption_kwh_100km:samples[0].page,drivetrain:wheelUrl,seats:modelUrl,
  ...Object.fromEntries(['battery_kwh','dc_charge_kw','ac_charge_kw','boot_liters','tow_kg'].map(key=>[key,mainHardware]))};

function readPhoto(name) {
  const directory = join(realpathSync(root),'data','local','release-data','cupra-tavascan-press-2026-11-20');
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(directory));
  const path = join(directory,name);
  assert.equal(realpathSync(path),path);
  const raw = readFileSync(path);
  assert(raw.length>0 && raw.length<12_000_000);
  return raw;
}

export function readDriveImage() {
  const raw = readPhoto('tavascan-mynewsdesk-3072079.json');
  assert.equal(sha(raw),photoReceiptHash);
  const {title,review_filename,asset_url,original_url,width,height,original_width,original_height,collected_at,status,...photo}=JSON.parse(raw);
  assert.equal(title,'DSC00621_bred.jpg');
  assert.equal(review_filename,imageFile);
  assert.equal(photo.model_key,'cupra|tavascan');
  assert.equal(photo.source_url,imageSource);
  assert.equal(photo.content_sha256,imageHash);
  assert.equal(sha(readPhoto(`${photo.metadata_sha256}.html`)),photo.metadata_sha256);
  assert.equal(sha(readPhoto(imageFile)),imageHash);
  return {...photo,status:'documented',reviewed_at:collected_at.slice(0,10),asset_url:'/media/vehicles/'+imageFile,
    original_url,downloaded_from:asset_url,usage_scope:'independent_vehicle_editorial',
    prohibited_uses:['advertising','commercial_promotion','endorsement'],model_image_notice:'Pressbild. Utrustning kan skilja mellan versioner.'};
}

const fact = p => ({...p,quote:p.source_quote});

export async function readDriveCapture(path) {
  const {receipt,base,capture_sha256} = await readDriveWltpEvidence(path);
  assert.equal(receipt.profile.held.length,0);
  assert.equal(receipt.publication_approved,false);
  const profile = receipt.profile;
  const price = {...fact(profile.price),price_type:'list_price',price_valid_until:null,dealer_offer:fact(profile.separate_dealer_price_proof)};
  const authority = fact(base.swedish_factory_stock_scope.independent_gavle_price_support.importer_named_dealer);
  const sources = new Map();
  const register = (proof,seen) => {
    const url = proof.source_url, type = sourceRules.get(url);
    assert(type,'Unknown Tavascan evidence URL');
    const entry = {final_url:url,source_type:type,status:'reachable',http_status:200,
      source_name:url===dealerUrl?'Din Bil / CUPRA G\u00e4vle':'CUPRA Sverige',country:'SE',language:'sv',shared:false,
      source_authority:url===dealerUrl?'authorized_dealer':'manufacturer',authorization_evidence_url:url===dealerUrl?dealerProof:null,
      fetched_at:seen,content_hash:proof.source_hash};
    if(sources.has(url)) assert.deepEqual(entry,sources.get(url));
    else sources.set(url,entry);
  };
  register(price,base.captured_at);register(price.dealer_offer,base.captured_at);register(authority,base.captured_at);
  const body = fact(base.model_facts.body_type);
  register(body,base.captured_at);
  const measurements = receipt.inputs.map(({observation})=>({...observation.importer_identity.identity.model_code,
    stock_reference:observation.plate,model_year:observation.model_year,order:observation.importer_identity.order,
    packages:observation.importer_identity.equipment_codes,tyre_quote:observation.wheel_quote}));
  for(const item of measurements) register(item,receipt.captured_at);
  const wltpKeys = ['wltp_range_km','wltp_consumption_kwh_100km'];
  const field_evidence = Object.fromEntries(Object.entries(profile.technical_fields).map(([key,p])=>{
    const at = wltpKeys.includes(key)?receipt.captured_at:base.captured_at;
    register(p,at);
    if(p.corroboration) register(p.corroboration,at);
    return [key,{...fact(p),...(p.corroboration?{corroboration:fact(p.corroboration)}:{}),variant_name:VARIANT}];
  }));
  const market = base.market_index;
  const intake = {adapter:ADAPTER,model:MODEL,sources:[...sources.values()],model_evidence:body,
    market:{source:{final_url:market.workbook_url,source_type:'mobility_sweden_export',source_name:'Mobility Sweden',status:'reachable',
      http_status:200,content_hash:market.source_hash,fetched_at:base.captured_at},sheet:'Elbil ranking',
    row:{...marketRow,last_seen_month:market.report_month,registrations_last_month:market.registrations_month,registrations_ytd:market.registrations_ytd}},
    drafts:[{variant_name:VARIANT,manufacturer_identity:factory,extraction_confidence:0.99,field_evidence,price_evidence:price,
      facts:Object.fromEntries(Object.entries(field_evidence).map(([key,p])=>[key,p.value])),
      identity_evidence:{standard_wheels:fact(profile.standard_wheel_inches),measurements,authorized_outlet:authority}}],
    source_decisions:{offer_range:profile.advertised_max_range_only,offer_consumption:profile.alternative_manufacturer_offer_consumption,
      generic_motor_consumption:profile.alternative_motor_level_consumption,
      unsupported_importer_drivetrain:receipt.inputs.map(input=>input.observation.importer_identity.importer_drive_type_reference),
      decision:profile.decision}};
  assert.equal(market.raw_alias,'CUPRA | TAVASCAN | EL');
  return {intake,capture_sha256,now:new Date(receipt.captured_at)};
}

function validateIntake(intake) {
  assert.deepEqual(intake.model,MODEL);
  const sources = new Map(intake.sources.map(s=>[s.final_url,s]));
  assert.equal(sources.size,sourceRules.size);
  for(const [url,type] of sourceRules) {
    const source = sources.get(url);
    assert.equal(source?.source_type,type);assert.equal(source.shared,false);
    assert.equal(source.source_authority,url===dealerUrl?'authorized_dealer':'manufacturer');
    assert.equal(source.authorization_evidence_url,url===dealerUrl?dealerProof:null);
    assert.equal(source.country,'SE');assert.equal(source.language,'sv');
  }
  assert.equal(intake.drafts.length,1);
  const [draft] = intake.drafts;
  assert.deepEqual([draft.variant_name,draft.manufacturer_identity],[VARIANT,factory]);
  assert.deepEqual(draft.facts,FACTS);
  function proof(p,url,value) {
    assert.equal(p.value,value);
    assert.equal(p.source_url,url);
    assert.equal(p.source_hash,sources.get(url)?.content_hash);
    assert(typeof p.quote==='string' && p.quote.length>5);
  }
  for(const [key,url] of Object.entries(sourceForField)) {
    const p=draft.field_evidence[key];
    proof(p,url,FACTS[key]);
    if(p.corroboration || url===mainHardware || url===samples[0].page)
      proof(p.corroboration,url===mainHardware?supportHardware:samples[1].page,FACTS[key]);
  }
  proof(intake.model_evidence,modelUrl,'SUV');
  const id = draft.identity_evidence;
  proof(id.standard_wheels,wheelUrl,19);
  proof(id.authorized_outlet,dealerProof,'CUPRA G\u00e4vle');
  assert.deepEqual(id.measurements.map(r=>r.stock_reference),samples.map(s=>s.plate));
  for(const [i,s] of samples.entries()) {
    const p=id.measurements[i];
    assert.deepEqual([p.model_year,p.value,p.source_url,p.source_hash,p.order],
      [2026,'KR1BCD',s.importer,sources.get(s.importer).content_hash,s.id.slice(-13)]);
    assert.deepEqual(p.packages,['P80','PF0','YC1']);
    assert.match(p.tyre_quote,/235\/55 R19 fram och 255\/50 R19 bak/);
  }
  const p=draft.price_evidence;
  proof(p,priceUrl,554900);proof(p.dealer_offer,dealerUrl,554900);
  assert.deepEqual([p.model_year,p.source_date,p.price_type,p.price_valid_until,p.dealer_offer.price_type],
    [2026,'2026-09-15','list_price',null,'dealer_offer']);
  assert.deepEqual(intake.market.row,marketRow);
  assert.equal(intake.market.sheet,'Elbil ranking');
  assert.equal(new URL(intake.market.source.final_url).origin,'https://mobilitysweden.se');
  assert.match(decodeURIComponent(new URL(intake.market.source.final_url).pathname),/\/M\u00e5nadsrapport Nyregistreringar okt 2026\.xlsx$/);
}

export const policy = {adapter:ADAPTER,validateIntake,primaryUrl:priceUrl,imageKey:'cupra|tavascan',imageHash,
  aliasRule:'mobility_sweden_exact_raw_name',maxVariants:1,mixedSources:true,localOnly:true,
  readPrivateImage(image) {
    assert.deepEqual(image,readDriveImage());
    return readPhoto(imageFile);
  }, verifyPublic(rows,plan) {
    assert.equal(rows.length,1);
    const [row] = rows;
    for(const [key,value] of Object.entries(FACTS)) assert.equal(row[key],value,key);
    assert.deepEqual([row.variant_name,row.price_sek,row.price_type,row.price_source_url,row.image_url,row.image_source_url,row.available_confirmed],
      [VARIANT,554900,'list_price',priceUrl,plan.image.asset_url,imageSource,plan.expected_model.available_confirmed]);
  }};
