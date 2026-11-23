import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync,realpathSync} from 'node:fs';
import {basename,dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

export const ADAPTER='toyota_bz4x_touring_active_tech_fwd';
export const MODEL=Object.freeze({brand:'Toyota',model:'bZ4X Touring',normalized_brand:'toyota',normalized_model:'bz4x touring',body_type:'Kombi'});
export const VARIANT='Active Tech FWD';
export const RAW=Object.freeze({brand_raw:'TOYOTA',model_raw:'BZ4X TOURING',fuel_type_raw:'EL'});
export const MARKET=Object.freeze({...RAW,normalized_brand:'toyota',normalized_model:'bz4x touring',
  needs_mapping:false,model_group:null,source_name:'Mobility Sweden',last_seen_month:'2026-10-01',
  registrations_last_month:373,registrations_ytd:1159});
const marketHash='1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6';
const modelUrl='https://www.toyota.se/bilar/bz4x-touring';
const primaryUrl=modelUrl+'/specifications',pdf='https://pdf.toyotasverigebroschyr.com/price-list/bz4x-touring';
const photo=JSON.parse(readFileSync(new URL('../src/toyota-touring-photo-policy.json',import.meta.url),'utf8'));
const identity={country:'SE',car_id:'4dd8d99a-24a0-4de3-b84f-bb4c6fbf1526',
  model_id:'005b05cd-028a-4116-9df3-e6ee345cd7a8',grade_id:'984d769f-e823-4e3a-b421-b8fbdbbff93b',
  config_version:'6.HD',wheels_inches:18};
export const facts={wltp_range_km:591,wltp_consumption_kwh_100km:14,battery_kwh:74.7,dc_charge_kw:150,
  ac_charge_kw:11,boot_liters:669,tow_kg:750,seats:5,drivetrain:'FWD'};
const check=(value,expected)=>{
  for(const [key,item] of Object.entries(expected))assert.deepEqual(value?.[key],item,'Touring scope mismatch: '+key);
};
const cash={value:569900,source_url:pdf,price_type:'manufacturer_from',price_valid_until:null,page:3};

function touringIntake(report){
  check(report,{status:'private_touring_source_review',brand:MODEL.brand,model:MODEL.model,variant:VARIANT,
    factory_id:identity.car_id,body_type:MODEL.body_type,standard_wheel_inches:18,publication_approved:false,database_writes:0,paid_calls:0});
  const source=(final_url,file,extra={})=>({final_url,status:'reachable',http_status:200,
    fetched_at:report.fetched_at,content_hash:report.source_hashes[file],...extra});
  const manufacturer=(url,file,source_type)=>source(url,file,{source_type,source_name:'Toyota Sverige',
    source_authority:'manufacturer',country:'SE',language:'sv',shared:false});
  const intake={adapter:ADAPTER,model:MODEL,market:{row:report.market.row,
    source:source(report.market.source_url,'market.xlsx'),sheet:'Elbil ranking'},
    sources:[manufacturer(primaryUrl,'specifications.html','manufacturer_specs_page'),
      manufacturer(modelUrl,'model.html','manufacturer_model_page'),manufacturer(pdf,'brochure.pdf','price_list_pdf')],
    model_evidence:{...identity,source_url:primaryUrl,source_hash:report.source_hashes['specifications.html']},
    source_decisions:{model_year:'not asserted',battery:'gross',tow:'braked with towing equipment',
      wltp:'certification 2, combined, Swedish standard 18 inch Active Tech FWD',
      cargo:'rear seats upright',market:'separate October BEV entry; no inferred first registration or 12-month total'},
    drafts:[{manufacturer_identity:identity.car_id,variant_name:VARIANT,identity_evidence:identity,
      facts,extraction_confidence:1,price_evidence:{...report.cash_from,price_valid_until:null},
      field_evidence:Object.fromEntries(Object.entries(report.evidence).map(([field,proof])=>[field,{...proof,variant_name:VARIANT}]))}]};
  validateIntake(intake);
  return {intake,image:{...photo,status:'documented',reviewed_at:'2026-11-23'}};
}

export function readTouringCapture(input){
  const root=realpathSync(fileURLToPath(new URL('../',import.meta.url)));
  const folder=realpathSync(input);
  assert.equal(folder,resolve(input));
  assert.equal(dirname(folder),join(root,'data','local','release-data'));
  assert(/^toyota-touring-capture-[a-z0-9_]+$/i.test(basename(folder))&&!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(folder));
  const output=execFileSync(process.execPath,['scripts/run_python.mjs','scripts/toyota_bz4x_touring_review.py',
    '--replay',folder,'--verified-report'],{cwd:root,encoding:'utf8',timeout:120000,windowsHide:true});
  return touringIntake(JSON.parse(output.trim().split(/\r?\n/).at(-1)));
}

function validateIntake(intake){
  assert.deepEqual(intake.model,MODEL);
  check(intake.market.row,MARKET);
  check(intake.market.source,{final_url:intake.market.row.source_url,content_hash:marketHash});
  assert.deepEqual(intake.sources.map(s=>s.final_url),[primaryUrl,modelUrl,pdf]);
  assert.deepEqual(intake.sources.map(s=>s.source_type),['manufacturer_specs_page','manufacturer_model_page','price_list_pdf']);
  assert(intake.sources.every(s=>s.shared===false&&s.source_name==='Toyota Sverige'));
  assert.equal(intake.drafts.length,1);
  const [draft]=intake.drafts;
  check(draft,{manufacturer_identity:identity.car_id,variant_name:VARIANT,facts});
  assert.deepEqual(draft.identity_evidence,identity);
  assert.deepEqual(intake.model_evidence,{...identity,source_url:primaryUrl,source_hash:intake.sources[0].content_hash});
  check(draft.price_evidence,{...cash,source_hash:intake.sources[2].content_hash});
  for(const [field,value] of Object.entries(facts))
    check(draft.field_evidence[field],{value,source_url:primaryUrl,source_hash:intake.sources[0].content_hash,variant_name:VARIANT});
  assert.equal(intake.source_decisions.model_year,'not asserted');
}

function checkDiscovery(snapshot,model,market){
  assert.equal(model.validation_status,'draft');
  assert(!snapshot.market_models.some(row=>row.id!==market.id&&row.canonical_model_id===model.id));
}

function verifyPublic(rows,plan){
  assert.equal(rows.length,1,'One exact Touring variant required');
  const row=rows[0];
  check(row,{brand:MODEL.brand,model:MODEL.model,body_type:MODEL.body_type,variant_name:VARIANT,validation_status:'published',
    market_seen:true,available_confirmed:plan.expected_model.available_confirmed,source_url:primaryUrl,
    price_type:cash.price_type,price_valid_until:null,price_source_url:pdf,image_url:photo.asset_url,image_source_url:photo.source_url});
  check(Object.fromEntries(Object.keys(facts).map(k=>[k,k==='drivetrain'?row[k]:Number(row[k])])),facts);
  assert.equal(Number(row.price_sek),cash.value);
}

export const policy={adapter:ADAPTER,primaryUrl,imageHash:photo.content_sha256,imageKey:photo.model_key,
  aliasRule:'mobility_sweden_exact_raw_name',maxVariants:1,localOnly:true,
  scopedDiscovery:{market:MODEL,check:checkDiscovery},validateIntake,verifyPublic};
