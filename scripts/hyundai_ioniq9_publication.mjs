import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync,realpathSync,statSync} from 'node:fs';
import {basename,dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {MANUFACTURER_FROM_PRICE} from '../src/price-evidence.js';

const root=realpathSync(fileURLToPath(new URL('../',import.meta.url)));
export const ADAPTER='hyundai_ioniq9_advanced_sweden_my27';
export const MODEL=Object.freeze({brand:'Hyundai',model:'Ioniq 9',normalized_brand:'hyundai',normalized_model:'ioniq 9',body_type:'SUV'});
export const VARIANT='Advanced AWD 7-sits MY27';
const material='GOW7YCZ7ZHH530';
const identity='SE|MY27|'+material+'|AWD|7|20';
const publisherId='hyundai-ioniq9-se-editorial';
const press=JSON.parse(readFileSync(new URL('../src/press-image-publishers.json',import.meta.url),'utf8'))[publisherId];
const photoUrl=press.origin+press.approved_image_paths[0];
const imageKey='hyundai|ioniq 9';
const imageUrl='/media/vehicles/hyundai-ioniq-9-press-'+press.approved_source_sha256.slice(0,12)+'.jpg';
const dm='https://dmassets.hyundai.com/is/content/hyundaiautoever/';
const modelUrl='https://www.hyundai.com/se/sv/bilar/ioniq9.html';
const hpp='https://org-eu-www.hyundai.com/eu/papi';
const types={model:'manufacturer_model_page',config:'manufacturer_configurator',price:'price_list_pdf',
  technical:'technical_pdf'};
const urls={model:modelUrl,config:'https://lager.hyundai.se/model/IONIQ%209/'+material+'?customer=private&ext=R5P&int=NNB',
  price:dm+'Hyundai_Sverige_Prislista_20261102pdf',technical:dm+'250829_IONIQ9_TechSheetpdf-AFpdf',
  downloads:'https://www.hyundai.com/se/sv/bilar/ioniq9/tekniska-data-nedladdningar.html',press:photoUrl,
  photo:press.approved_asset_url,factory_wltp:hpp,factory_trim:hpp,
  market:'https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober',
  workbook:'https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx'};
const webHash='7e75436a099d0532501198666d6715ae50165d6942eeac91f8c779d6403cb0e0';
const marketHash='1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6';
const marketRow={brand_raw:'HYUNDAI',model_raw:'IONIQ 9',fuel_type_raw:'EL',normalized_brand:'hyundai',
  normalized_model:'ioniq 9',last_seen_month:'2026-10-01',registrations_last_month:43,registrations_ytd:330,needs_mapping:false};
const configQuote='IONIQ 9 \u00b7 7s AWD 110kWh Advanced MY27';
const modelQuote='helelektrisk SUV med tre s\u00e4tesrader';
const priceQuote='AWD 110kWh Advanced 2,04 - 0 850 900 kr';
const specs={
  wltp_range_km:[606,'technical','20" \u2013 Upp till 606 km \u2013'],
  wltp_consumption_kwh_100km:[20.4,'technical','19" / 20": 20,4 / 21": 20,6'],
  battery_kwh:[110.3,'model','110,3 kWh'],
  dc_charge_kw:[233,'model','233 kW',{scope:'shared IONIQ 9 800V hardware'}],
  ac_charge_kw:[10.5,'technical','Trefas: 11 (10,5)',{scope:'actual three-phase 10.5 kW'}],
  boot_liters:[338,'technical','Bagagevolym bakom 3:e s\u00e4tesraden l (VDA 211) 338',{scope:'all seven seats up, no frunk'}],
  tow_kg:[2500,'technical','Sl\u00e4pvagnsvikt med broms 1 600 2 500 2 500',{requires_towing_equipment:true,scope:'braked AWD'}],
  seats:[7,'config',configQuote],drivetrain:['AWD','config',configQuote],
};
const facts=Object.freeze(Object.fromEntries(Object.entries(specs).map(([key,[value]])=>[key,value])));
const equipment={model_year:2027,manufacturer_code:material,market:'SE',fuel:'BEV',wheels_inches:20};
const priceScope={price_type:MANUFACTURER_FROM_PRICE,price_valid_until:null,scope:'swedish_advanced_manufacturer_from_before_paint'};
const sha=/^[a-f0-9]{64}$/;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const fields=(row,wanted)=>{
  for(const [key,value] of Object.entries(wanted))assert.deepEqual(row?.[key],value,'IONIQ 9 scope changed: '+key);
};
const evidence=(folder,name,limit)=>{
  assert.equal(basename(name),name);
  const path=join(folder,name);
  assert.equal(realpathSync(path),path);
  const info=statSync(path);
  assert(info.isFile()&&info.size>0&&info.size<=limit);
  return readFileSync(path);
};
function privateRoot(){
  const folder=join(root,'data','local','release-data');
  assert.equal(realpathSync(folder),folder);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(folder));
  return folder;
}
const metadata=name=>({country:'SE',language:'sv',source_type:types[name],shared:false,
  source_name:'Hyundai Sverige',source_authority:'manufacturer',authorization_evidence_url:null});
const receipt=(r,name)=>{
  const s=r.sources[name];
  fields(s,{source_url:urls[name],http_status:200});
  assert.match(s.content_hash,sha);
  assert(Number.isFinite(Date.parse(s.fetched_at)));
  return {final_url:s.source_url,content_hash:s.content_hash,fetched_at:s.fetched_at,status:'reachable',http_status:200};
};
const proof=(r,value,name,quote)=>({value,quote,source_url:urls[name],source_hash:receipt(r,name).content_hash});
const publicationMarket={...marketRow,source_name:'Mobility Sweden',source_url:urls.workbook};
const imageMetadata=metadata_sha256=>({model_key:imageKey,publisher_id:publisherId,status:'documented',
  source_url:photoUrl,evidence_url:photoUrl,license_url:photoUrl,license_id:'Manufacturer-media-use',
  evidence_quote:press.permission_excerpt+' | '+press.condition_excerpt,full_frame:true,
  content_sha256:press.approved_source_sha256,source_content_sha256:press.approved_source_sha256,
  metadata_sha256,author:press.asset_author,credit:press.asset_author+' / pressbild',reviewed_at:'2026-11-22',
  asset_url:imageUrl,downloaded_from:urls.photo,usage_scope:'independent_vehicle_editorial',
  prohibited_uses:['advertising','commercial_promotion','endorsement'],
  model_image_notice:'Pressbild av IONIQ 9. Utrustningen kan skilja mellan versioner.'});

export function readIoniq9Capture(path){
  const folder=realpathSync(resolve(path));
  assert.equal(folder,resolve(path));
  assert.equal(dirname(folder),privateRoot());
  assert.match(basename(folder),/^hyundai-ioniq9-advanced-[0-9a-z_]+$/);
  const bytes=evidence(folder,'report.json',50_000);
  execFileSync(process.execPath,['scripts/run_python.mjs','scripts/hyundai_ioniq9_review.py','--replay',folder],
    {cwd:root,timeout:120_000,windowsHide:true});
  assert.equal(hash(evidence(folder,'report.json',50_000)),hash(bytes));
  const r=JSON.parse(bytes);
  fields(r,{material,model_year:2027,wheels_inches:20,price_sek:850900,facts,photo_status:'whole_frame_verified',
    publication_approved:false,database_writes:0,paid_calls:0});
  fields(r.market_index,{sheet:'Elbil ranking',row:marketRow});
  const intake={adapter:ADAPTER,model:MODEL,model_evidence:proof(r,'SUV','model',modelQuote),
    sources:Object.keys(types).map(name=>({...receipt(r,name),...metadata(name)})),
    drafts:[{variant_name:VARIANT,manufacturer_identity:identity,extraction_confidence:1,facts,
      field_evidence:Object.fromEntries(Object.entries(specs).map(([key,[value,name,quote,scope]])=>
        [key,{...proof(r,value,name,quote),variant_name:VARIANT,...scope}])),
      price_evidence:{...proof(r,850900,'price',priceQuote),...priceScope},
      identity_evidence:{...equipment,configuration:proof(r,material,'config',configQuote)}}],
    source_decisions:{...Object.fromEntries(['factory_trim','factory_wltp'].map(name=>
      [name,{...receipt(r,name),request_hash:r.sources[name].request_hash}])),
      downloads:receipt(r,'downloads'),wltp_qualification:'combined WLTP, base 20-inch wheels'},
    market:{sheet:'Elbil ranking',row:publicationMarket,
      source:{...receipt(r,'workbook'),source_name:'Mobility Sweden',source_type:'mobility_sweden_export'},
      article:receipt(r,'market')}};
  fields(receipt(r,'photo'),{content_hash:press.approved_source_sha256});
  const rendition=r.publisher_responsive_variants['746'];
  fields(rendition,{width:746,height:522,sha256:webHash,file:'photo-746.webp'});
  const image=imageMetadata(receipt(r,'press').content_hash);
  validateIntake(intake);
  return {intake,image,reviewHash:hash(bytes),rendition};
}

function readPrivateImage(image){
  assert.deepEqual(image,imageMetadata(image.metadata_sha256),'Require the reviewed model-level Hyundai image');
  return evidence(join(root,'public','media','vehicles'),basename(imageUrl),12_000_000);
}

function validateIntake(intake){
  fields(intake,{adapter:ADAPTER,model:MODEL});
  assert.equal(intake.sources.length,Object.keys(types).length);
  const sources=new Map(intake.sources.map(s=>[s.final_url,s]));
  for(const name of Object.keys(types))fields(sources.get(urls[name]),metadata(name));
  const bind=(p,value,name,quote)=>fields(p,{value,quote,source_url:urls[name],source_hash:sources.get(urls[name]).content_hash});
  bind(intake.model_evidence,'SUV','model',modelQuote);
  assert.equal(intake.drafts.length,1);
  const [row]=intake.drafts;
  fields(row,{variant_name:VARIANT,manufacturer_identity:identity,extraction_confidence:1,facts});
  fields(row.identity_evidence,equipment);
  bind(row.identity_evidence.configuration,material,'config',configQuote);
  for(const [key,[value,name,quote,scope]] of Object.entries(specs)){
    bind(row.field_evidence[key],value,name,quote);
    fields(row.field_evidence[key],scope??{});
  }
  bind(row.price_evidence,850900,'price',priceQuote);
  fields(row.price_evidence,priceScope);
  fields(intake.market,{sheet:'Elbil ranking',row:publicationMarket});
  fields(intake.market.source,{final_url:urls.workbook,content_hash:marketHash,source_type:'mobility_sweden_export'});
  fields(intake.market.article,{final_url:urls.market,http_status:200,status:'reachable'});
  assert.match(intake.market.article.content_hash,sha);
  for(const name of ['factory_trim','factory_wltp','downloads']){
    const source=intake.source_decisions[name];
    fields(source,{final_url:urls[name],http_status:200,status:'reachable'});
    if(name!=='downloads')assert.match(source.request_hash,sha);
    assert.match(source.content_hash,sha);
  }
}

function verifyPublic(rows,plan){
  assert.equal(rows.length,1);
  fields(rows[0],{...facts,brand:MODEL.brand,model:MODEL.model,body_type:MODEL.body_type,variant_name:VARIANT,
    price_sek:850900,price_type:MANUFACTURER_FROM_PRICE,price_source_url:urls.price,price_valid_until:null,
    source_url:urls.model,market_seen:true,available_confirmed:plan.expected_model.available_confirmed,
    validation_status:'published',image_url:imageUrl,image_source_url:photoUrl});
}

function reuseEvidenceSource(source,saved,snapshot){
  if(source.final_url!==urls.price)return false;
  // The national price list is already registered to IONIQ 5. Keep it untouched.
  const parent=snapshot.canonical_models.find(row=>row.id===saved?.canonical_model_id);
  fields(parent,{brand:'Hyundai',normalized_brand:'hyundai',normalized_model:'ioniq 5'});
  fields(saved,{brand:'Hyundai',model:parent.model,url:urls.price,final_url:urls.price,
    source_type:'price_list_pdf',source_authority:'manufacturer',country:'SE',language:'sv',
    http_status:200,content_hash:source.content_hash,source_validation:'reachable_official_model_source'});
  return true;
}

export const policy={adapter:ADAPTER,primaryUrl:urls.model,aliasRule:'mobility_sweden_exact_raw_name',imageKey,
  imageHash:press.approved_source_sha256,maxVariants:1,localOnly:true,readPrivateImage,validateIntake,verifyPublic,reuseEvidenceSource,
  scopedDiscovery:{market:marketRow,check(snapshot,model,market){
    assert(!snapshot.market_models.some(row=>row.id!==market.id&&row.canonical_model_id===model.id),
      'Only the exact BEV market row may link to IONIQ 9');
  }}};
