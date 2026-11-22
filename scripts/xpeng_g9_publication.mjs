import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ADAPTER = 'xpeng_g9_sweden_facelift_local_v1';
export const MODEL = {brand:'Xpeng',model:'G9',normalized_brand:'xpeng',normalized_model:'g9',body_type:'SUV'};
const root = realpathSync(fileURLToPath(new URL('..',import.meta.url)));
const modelKey = 'xpeng|g9';
const aliasRule = 'mobility_sweden_exact_raw_name';
const publisher = 'xpeng-g9-private-review';
const pressRoom = 'https://www.mynewsdesk.com/se/xpeng-motors-sweden-ab/';
const photoUrl = pressRoom+'images/nya-g9-1-punkt-jpeg-3270628';
const photoFolder = 'xpeng-g9-press-2026-11-21';
const imageHash = '3872869a55dd3c8eaf93aa0493f8f8f71df5bb26501b92ce7c0a109223d1e87a';
const imageReceiptHash = 'abc4b41a87b2d7aa7262295921de37e62683c8c6fbf7736885824678934721d0';
const imageFile = 'xpeng-g9-press-'+imageHash.slice(0,12)+'.jpg';
const primary = 'https://store.xpeng.com/se/configurator/new_G9';
const germanOrder = 'https://store.xpeng.com/de/configurator/new_G9';
const technical = 'https://s-cdn.xpeng.com/commoncms/prod/2026-11-06/1c654ffc82e9482998d66dd73529f8be.pdf';
const dealer = 'https://lecab.se/erbjudande/xpeng-g9/';
const locator = 'https://www.xpeng.com/se/find-us';
const launch = pressRoom+'pressreleases/nya-xpeng-g9-svenska-priser-och-foersaeljningsstart-3396460';
const workbook = 'https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx';
const assetUrl = '/media/vehicles/'+imageFile;
const source = (source_type, source_name, country='SE', language='sv', authorization_evidence_url=null) => ({
  source_type,source_name,country,language,authorization_evidence_url,shared:false,
  source_authority:authorization_evidence_url?'authorized_dealer':'manufacturer',
});
const sources = [
  ['config.html',primary,source('manufacturer_configurator','XPENG Sverige')],
  ['german.html',germanOrder,source('manufacturer_configurator','XPENG Deutschland','DE','de')],
  ['german.pdf',technical,source('technical_pdf','XPENG Deutschland','DE','de')],
  ['press.html',launch,source('manufacturer_page','XPENG Sverige')],
  ['dealer.html',dealer,source('authorized_dealer_model_page','Lecab Bil','SE','sv',locator)],
  ['appointment.json',locator,source('manufacturer_page','XPENG Sverige')],
];
const profiles = [
  ['RWD Standard Range',20,'EEAB','1676',719900,502,18.4,79,445,'RWD'],
  ['AWD Performance',21,'EECB','1641',849900,540,20.1,93.1,525,'AWD'],
].map(([trim,wheels,code,id,price,wltp,consumption,battery,dc,drive])=>({
  trim,wheels,identity:'E38bV$'+code,id,price,name:trim+' '+wheels+' tum',
  facts:{wltp_range_km:wltp,wltp_consumption_kwh_100km:consumption,battery_kwh:battery,dc_charge_kw:dc,
    ac_charge_kw:11,boot_liters:660,tow_kg:1500,seats:5,drivetrain:drive},
}));
const market = {brand_raw:'XPENG',model_raw:'G9',fuel_type_raw:'EL',normalized_brand:'xpeng',normalized_model:'g9',
  needs_mapping:false,last_seen_month:'2026-10-01',registrations_last_month:68,registrations_ytd:416,
  source_name:'Mobility Sweden',source_url:workbook};
const hash = bytes=>createHash('sha256').update(bytes).digest('hex');
const json = bytes=>JSON.parse(bytes.toString('utf8'));

function evidenceRoot() {
  const path = join(root,'data','local','release-data');
  assert.equal(realpathSync(path),path);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(path));
  return path;
}

function readEvidence(folder,filename) {
  assert.equal(basename(filename),filename);
  const path = join(folder,filename);
  assert.equal(realpathSync(path),path,'Linked G9 evidence is not allowed');
  return readFileSync(path);
}

export function readG9Image() {
  const folder = join(evidenceRoot(),photoFolder);
  const bytes = readEvidence(folder,'g9-mynewsdesk-3270628.json');
  assert.equal(hash(bytes),imageReceiptHash,'Reviewed G9 photo receipt changed');
  const receipt = json(bytes);
  assert.equal(receipt.source_url,photoUrl);
  assert.equal(receipt.publisher_id,publisher);
  assert.equal(receipt.model_key,modelKey);
  assert.equal(receipt.review_filename,imageFile);
  assert.equal(receipt.content_sha256,imageHash);
  assert.equal(hash(readEvidence(folder,receipt.metadata_sha256+'.html')),receipt.metadata_sha256);
  const image = Object.fromEntries(['model_key','source_url','evidence_url','evidence_quote','license_id','license_url',
    'author','credit','content_sha256','metadata_sha256','source_content_sha256','publisher_id','full_frame']
    .map(key=>[key,receipt[key]]));
  return {...image,asset_url:assetUrl,downloaded_from:receipt.asset_url,original_url:receipt.original_url,
    status:'documented',reviewed_at:'2026-11-21',reviewed_candidate_sha256:imageReceiptHash,
    usage_scope:'independent_vehicle_editorial',prohibited_uses:['advertising','commercial_promotion','endorsement'],
    model_image_notice:'Pressbild av G9 Black Edition. Standardutrustning kan skilja mellan versioner.'};
}

export function readPrivateG9Image(image) {
  assert.deepEqual(image,readG9Image(),'Require the exact G9 model photograph');
  const body = readEvidence(join(evidenceRoot(),photoFolder),imageFile);
  assert.equal(hash(body),imageHash);
  return body;
}

function requireFields(record,expected) {
  for(const [key,value] of Object.entries(expected)) assert.equal(record?.[key],value,'Unexpected G9 evidence: '+key);
}

function validateIntake(intake) {
  assert.equal(intake.adapter,ADAPTER);
  assert.deepEqual(intake.model,MODEL);
  assert.deepEqual(intake.market.row,market);
  assert.equal(intake.market.source.final_url,workbook);
  assert.equal(intake.market.sheet,'Elbil ranking');
  assert.equal(intake.sources.length,sources.length);
  const byUrl = new Map(intake.sources.map(row=>[row.final_url,row]));
  for(const [,url,meta] of sources) requireFields(byUrl.get(url),meta);
  const bind = (p,url,value)=>requireFields(p,{source_url:url,source_hash:byUrl.get(url).content_hash,value});
  bind(intake.model_evidence,primary,'SUV');
  assert.match(intake.model_evidence.quote,/\bG9\b.*\bSUV\b/);
  assert.equal(intake.drafts.length,2);
  for(const profile of profiles) {
    const draft = intake.drafts.find(row=>row.variant_name===profile.name);
    assert(draft,'Exact Swedish G9 factory configuration required');
    assert.equal(draft.manufacturer_identity,profile.identity);
    const {swedish,german,wheels} = draft.identity_evidence;
    bind(swedish,primary,profile.identity);
    bind(german,germanOrder,profile.identity);
    bind(wheels,primary,profile.wheels);
    requireFields(swedish,{market:'SE',version_id:profile.id});
    requireFields(german,{market:'DE'});
    assert.deepEqual(draft.facts,profile.facts);
    for(const [key,value] of Object.entries(profile.facts)) {
      bind(draft.field_evidence[key],key==='seats'?launch:key==='tow_kg'?technical:primary,value);
    }
    requireFields(draft.field_evidence.battery_kwh,{capacity_basis:'gross'});
    for(const key of ['wltp_range_km','wltp_consumption_kwh_100km']) requireFields(draft.field_evidence[key],{wheels_inches:profile.wheels});
    const tow = draft.field_evidence.tow_kg;
    requireFields(tow,{factory_version:profile.identity,scope:'braked_only_on_matched_factory_versions'});
    bind(tow.swedish_source,primary,1500);
    const price = draft.price_evidence;
    bind(price,primary,profile.price);
    requireFields(price,{price_type:'list_price',price_valid_until:null,scope:'manufacturer_base_cash_price'});
    bind(price.corroboration,dealer,profile.price);
    requireFields(price.corroboration,{authorization_url:locator,authorization_hash:byUrl.get(locator).content_hash});
    bind(price.authorization,locator,'Lecab Bil Karlstad');
    requireFields(price.authorization,{scope:'rendered_official_public_locator'});
  }
}

function verifyPublic(rows,plan) {
  assert.equal(rows.length,profiles.length);
  for(const {name,price,facts} of profiles) {
    const matching = rows.filter(row=>row.variant_name===name);
    assert.equal(matching.length,1);
    const primarySource = plan.intake.sources.find(s=>s.final_url===primary);
    requireFields(matching[0],{...facts,brand:MODEL.brand,model:MODEL.model,body_type:'SUV',
      validation_status:'published',price_sek:price,price_type:'list_price',source_url:primary,price_source_url:primary,
      source_hash:primarySource.content_hash,price_source_hash:primarySource.content_hash,
      image_url:plan.image.asset_url,image_source_url:plan.image.source_url,market_seen:true,
      ...Object.fromEntries(['available_confirmed','discontinued_candidate','coming_or_low_volume']
        .map(key=>[key,plan.expected_model[key]]))});
    assert.equal(Date.parse(matching[0].price_verified_at),Date.parse(primarySource.fetched_at));
  }
}

function prepare(review) {
  requireFields(review,{status:'private_g9_profile_review',model_key:modelKey,market:'SE',
    publication_approved:false,database_writes:0,photo_source:photoUrl});
  requireFields(review.market_index,{source_url:workbook,quote:'XPENG | G9 | EL',value:68,
    registrations_ytd:416,report_month:market.last_seen_month});
  assert.equal(Object.keys(review.variants).length,2);
  const receipt = (name,url)=>{
    requireFields(review.sources[name],{url});
    return {final_url:url,content_hash:review.sources[name].sha256,fetched_at:review.fetched_at[name],
      http_status:200,status:'reachable'};
  };
  const drafts = profiles.map(p=>{
    const row = review.variants[p.trim];
    return {variant_name:p.name,manufacturer_identity:row.manufacturer_identity.value,extraction_confidence:1,
      identity_evidence:{swedish:row.manufacturer_identity,german:row.engineering_identity,wheels:row.standard_wheels},
      facts:Object.fromEntries(Object.entries(row.facts).map(([key,proof])=>[key,proof.value])),
      field_evidence:Object.fromEntries(Object.entries(row.facts).map(([key,proof])=>[key,{...proof,variant_name:p.name}])),
      price_evidence:{...row.price,price_valid_until:null,corroboration:row.dealer_price,authorization:review.dealer_appointment}};
  });
  const standard = review.variants[profiles[0].trim].facts.drivetrain;
  return {adapter:ADAPTER,model:MODEL,model_evidence:{...standard,value:'SUV'},drafts,
    sources:sources.map(([file,url,meta])=>({...receipt(file,url),...meta})),
    market:{source:receipt('market.xlsx',workbook),row:market,sheet:'Elbil ranking'},
    source_decisions:Object.fromEntries(profiles.map(p=>[p.name,review.variants[p.trim].battery_decision]))};
}

export function readG9Capture(path) {
  const folder = realpathSync(path);
  assert.equal(folder,resolve(path));
  assert.equal(dirname(folder),evidenceRoot());
  assert.match(basename(folder),/^xpeng-g9-review-[a-z0-9_]+$/);
  const bytes = readEvidence(folder,'review.json');
  const replay = json(execFileSync(process.execPath,['scripts/run_python.mjs','scripts/xpeng_g9_review.py','--replay',folder],
    {cwd:root,timeout:90000,windowsHide:true}));
  assert.deepEqual([replay.sources,replay.variants,replay.core_fields,replay.publication_approved],[8,2,18,false]);
  assert.equal(hash(readEvidence(folder,'review.json')),hash(bytes));
  const intake = prepare(json(bytes));
  validateIntake(intake);
  return {intake,reviewHash:hash(bytes)};
}

export const policy = {adapter:ADAPTER,primaryUrl:primary,aliasRule,imageKey:modelKey,imageHash,maxVariants:2,
  mixedSources:true,localOnly:true,readPrivateImage:readPrivateG9Image,validateIntake,verifyPublic};
