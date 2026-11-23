import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync,realpathSync} from 'node:fs';
import {basename,dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readExactModelScope} from './porsche_macan_scope.mjs';

export const MODEL=Object.freeze({brand:'Lexus',model:'Rz',normalized_brand:'lexus',normalized_model:'rz',body_type:'SUV'});
export const VARIANT='350e Executive';
export const ADAPTER='lexus_rz_350e_current';
export const CAR_ID='d032f909-69f8-45ea-bc22-7c6161ca2105';
const TYPE='XEBM20L-AWDCSW',SUFFIX='AB',identity=['SE',TYPE,SUFFIX,CAR_ID].join('|');
const primaryUrl='https://www.lexus.se/new-cars/rz';
const pdf='https://www.lexus.se/content/dam/lexus/nmsc/sweden/documents/pris-och-utrustningslista/LSW_Pricelist_RZ_210x271_Q1-26_260318.pdf';
const configurator='https://dxp-webcarconfig.lexus-europe.com/v1/api/data/';
const urls=[primaryUrl,pdf,configurator+'se/sv',configurator+'dk/da'];
const manualUrl='https://customerportal.tweddle-aws.eu/content?id=16f0e745-02b7-40d0-a66c-119fa5d245f7&topicId=6ffb4817-75e3-46e8-932b-8ab5909d2c79&publicationType=OM';
const manualHash='a936c7038ddd8626138e40036736498e50802c2ea7a1fa370d30ece3968e7689';
const raw={brand_raw:'LEXUS',model_raw:'RZ',fuel_type_raw:'EL'};
const month='2026-10-01',registrations=50,ytd=439;
const market={...raw,normalized_brand:'lexus',normalized_model:'rz',source_name:'Mobility Sweden',
  last_seen_month:month,registrations_last_month:registrations,registrations_ytd:ytd,needs_mapping:false,model_group:null};
const scope={model:MODEL,raw,month,registrations,ytd,names:['rz','rz 350e','lexus rz'],label:'Lexus RZ'};
const modelPhoto=JSON.parse(readFileSync(new URL('../src/lexus-rz-photo-policy.json',import.meta.url),'utf8'));
const {model_key:imageKey,content_sha256:imageHash,asset_url:assetUrl,source_url:photoSource}=modelPhoto;
export const facts=Object.freeze({wltp_range_km:567,wltp_consumption_kwh_100km:14.5,battery_kwh:77,dc_charge_kw:150,
  ac_charge_kw:22,boot_liters:586,tow_kg:750,seats:5,drivetrain:'FWD'});
const from={value:599000,source_url:primaryUrl,price_type:'manufacturer_from',price_valid_until:null};
const exactIdentity={market:'SE',car_id:CAR_ID,type_code:TYPE,suffix:SUFFIX,wheels_inches:18};
const fields=(object,expected)=>{
  for(const [key,value] of Object.entries(expected))assert.deepEqual(object?.[key],value,'Lexus RZ proof mismatch: '+key);
};

export const readLexusScope=(db,incoming)=>readExactModelScope(db,incoming,scope);

export function lexusIntakeFromReplay(report){
  fields(report,{status:'private_current_lexus_executive_intake',identity:[VARIANT,CAR_ID,TYPE,SUFFIX],
    publication_approved:false,production_writes:0});
  const {sources,market,price_evidence,source_decisions}=report;
  const intake={adapter:ADAPTER,model:MODEL,sources,market,source_decisions,
    model_evidence:{...exactIdentity,source_url:primaryUrl,source_hash:sources[0].content_hash},
    drafts:[{manufacturer_identity:identity,variant_name:VARIANT,identity_evidence:exactIdentity,extraction_confidence:1,
      facts,price_evidence,field_evidence:Object.fromEntries(Object.entries(report.field_evidence)
        .map(([field,evidence])=>[field,{...evidence,variant_name:VARIANT}]))}]};
  validateIntake(intake);
  return {intake,image:{...modelPhoto,reviewed_at:'2026-11-23',status:'documented'}};
}

export function readLexusCapture(input){
  const root=realpathSync(fileURLToPath(new URL('../',import.meta.url)));
  const folder=realpathSync(input);
  assert.equal(folder,resolve(input));
  assert.equal(dirname(folder),join(root,'data','local','release-data'));
  assert(/^lexus-rz-current-[a-z0-9_]+$/i.test(basename(folder))&&!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(folder));
  const output=execFileSync(process.execPath,['scripts/run_python.mjs','scripts/lexus_rz_release_intake.py','--replay',folder],
    {cwd:root,encoding:'utf8',timeout:120000,windowsHide:true});
  return lexusIntakeFromReplay(JSON.parse(output.trim().split(/\r?\n/).at(-1)));
}

function validateIntake(intake){
  fields(intake.model,MODEL);
  fields(intake.market.row,market);
  fields(intake.market.source,{final_url:intake.market.row.source_url,content_hash:'1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6'});
  assert.deepEqual(intake.sources.map(s=>s.final_url),urls);
  assert.deepEqual(intake.sources.map(s=>[s.country,s.language,s.source_authority]),
    [['SE','sv','manufacturer'],['SE','sv','manufacturer'],['SE','sv','manufacturer'],['DK','da','manufacturer']]);
  assert.equal(intake.drafts.length,1);
  const [draft]=intake.drafts;
  fields(draft,{manufacturer_identity:identity,variant_name:VARIANT,facts});
  assert.deepEqual(draft.identity_evidence,exactIdentity,'Do not assert a Lexus model year');
  assert.deepEqual(intake.model_evidence,{...exactIdentity,source_url:primaryUrl,source_hash:intake.sources[0].content_hash});
  fields(draft.price_evidence,from);
  fields(draft.price_evidence.corroboration,{source_url:pdf,source_hash:intake.sources[1].content_hash});
  for(const [field,value] of Object.entries(facts)){
    const ix=field==='dc_charge_kw'?3:['ac_charge_kw','tow_kg'].includes(field)?2:0;
    fields(draft.field_evidence[field],{value,source_url:urls[ix],source_hash:intake.sources[ix].content_hash,variant_name:VARIANT});
  }
  fields(intake.source_decisions,{model_year:'not asserted; current Swedish configuration identity only'});
  fields(intake.source_decisions.swedish_manual,{source_url:manualUrl,source_hash:manualHash,document_id:'PZ471-9AS86-SV',
    page:748,scope:'max braked, with towing equipment'});
  fields(intake.source_decisions.dc_corroboration,{market:'NO'});
}

function checkDiscovery(snapshot,model,marketRow){
  assert.equal(model.validation_status,'draft');
  assert(!snapshot.market_models.some(row=>row.id!==marketRow.id&&row.canonical_model_id===model.id),
    'Only the exact Lexus RZ electric market row may link to this model');
}

function verifyPublic(rows,plan){
  assert.equal(rows.length,1,'One exact Lexus RZ variant required');
  const row=rows[0];
  fields(row,{brand:MODEL.brand,model:MODEL.model,body_type:MODEL.body_type,variant_name:VARIANT,validation_status:'published',
    market_seen:true,available_confirmed:plan.expected_model.available_confirmed,source_url:primaryUrl,
    price_type:from.price_type,price_valid_until:null,price_source_url:primaryUrl,image_url:assetUrl,image_source_url:photoSource});
  fields(Object.fromEntries(Object.keys(facts).map(key=>[key,key==='drivetrain'?row[key]:Number(row[key])])),facts);
  assert.equal(Number(row.price_sek),from.value);
}

export const policy={adapter:ADAPTER,primaryUrl,aliasRule:'mobility_sweden_exact_raw_name',maxVariants:1,
  imageKey,imageHash,localOnly:true,mixedSources:true,scopedDiscovery:{market:MODEL,check:checkDiscovery},validateIntake,verifyPublic};
