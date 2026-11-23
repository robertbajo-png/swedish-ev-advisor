import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync,realpathSync} from 'node:fs';
import {basename,dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {MACAN_MODEL} from './porsche_macan_scope.mjs';

export const ADAPTER='porsche_macan_xabaa1_private';
const identity='SE|MY27|XABAA1|RWD|5|20', variant='Electric RWD MY27';
const base='https://configurator.porsche.com/sv-SE/mode/model/XABAA1';
const urls={base,technical:base+'/specifications?tab=technical-data',equipment:base+'/specifications?tab=standard-equipment',
  comparison:'https://compare.porsche.com/sv-SE?model-series=macan'};
const imageKey='porsche|macan';
const imageHash='3097c517e11eb8ba4be5db10dec3fcaf8467d1d4b3e09fe8646b6e278c5662f6';
const photoSource='https://newsroom.porsche.com/de/pressemappen/der-neue-porsche-macan.html';
const assetId='pmdb:9458fb1b-7f83-4267-ba53-8d6321764b0a';
const root=realpathSync(fileURLToPath(new URL('../',import.meta.url)));
const privateRoot=join(root,'data','local','release-data');
const prices={value:970000,price_type:'manufacturer_from',price_valid_until:null};
const facts=Object.freeze({wltp_range_km:642,wltp_consumption_kwh_100km:16.7,battery_kwh:100,dc_charge_kw:270,
  ac_charge_kw:11,boot_liters:518,tow_kg:2000,seats:5,drivetrain:'RWD'});
const market={brand_raw:'PORSCHE',model_raw:'MACAN',fuel_type_raw:'EL',normalized_brand:'porsche',normalized_model:'macan',
  source_name:'Mobility Sweden',last_seen_month:'2026-10-01',registrations_last_month:43,registrations_ytd:367,needs_mapping:false};
const assetUrl='/private-rehearsal/porsche-macan-'+imageHash.slice(0,12)+'.jpg';
const fields=(row,expected)=>{for(const [k,v] of Object.entries(expected))assert.deepEqual(row?.[k],v,'Macan proof mismatch: '+k);};

function privateFolder(input,prefix){
  const folder=realpathSync(input);
  assert.equal(folder,resolve(input),'Require an unlinked Macan source packet');
  assert.equal(dirname(folder),privateRoot);
  assert(basename(folder).startsWith(prefix)&&!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(folder));
  return folder;
}

export function macanIntakeFromReplay(report,photoFolder){
  fields(report,{status:'macan_release_intake_verified_private',model:'Porsche Macan',variant,
    manufacturer_identity:identity,price_type:prices.price_type,price_valid_until:null,publication_approved:false,production_writes:0});
  assert(report.all_sources_within_15_minutes,'Fresh Macan source capture required');
  const photo=report.photo_candidate;
  fields(photo,{status:'verified_model_photo_private_only',asset_id:assetId,credit:'Porsche AG',
    source_url:photoSource,sha256:imageHash,catalog_use_confirmed:false,width:6000,height:4000});
  const sources=Object.entries(urls).map(([key,url])=>{
    const receipt=report.spec_sources[key];
    fields(receipt,{source_url:url,http_status:200});
    return {final_url:url,fetched_at:receipt.fetched_at,content_hash:receipt.content_hash,status:'reachable',http_status:200,
      source_type:key==='comparison'?'manufacturer_model_page':'manufacturer_configurator',
      country:'SE',language:'sv',source_authority:'manufacturer',source_name:'Porsche Sverige'};
  });
  const proof=(field,key,value)=>{
    const e=report.field_evidence[field],s=sources.find(row=>row.final_url===urls[key]);
    fields(e,{value,source_url:s.final_url,source_hash:s.content_hash,fetched_at:s.fetched_at});
    return {value,source_url:e.source_url,source_hash:e.source_hash,quote:e.quote,variant_name:variant};
  };
  const field_evidence=Object.fromEntries(Object.entries(facts).map(([k,value])=>[k,proof(k,
    ['ac_charge_kw','seats','drivetrain'].includes(k)?'equipment':'technical',value)]));
  fields(report.qualifications,{battery:'gross',range:'combined WLTP, standard 20-inch wheels',
    cargo:'rear cargo to the top of the rear seat backrest',towing:'braked, with the optional tow bar',ac:'standard on-board charger'});
  fields(report.market_discovery,market);
  const workbook=report.market_sources['market.xlsx'];
  fields(workbook,{final_url:report.market_discovery.source_url,status:'reachable',http_status:200,
    content_hash:'1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6'});
  const primary=sources[0];
  return {
    intake:{adapter:ADAPTER,model:MACAN_MODEL,sources,market:{row:report.market_discovery,source:workbook},
      model_evidence:{factory_code:'XABAA1',model_year:2027,market:'SE',source_url:base,source_hash:primary.content_hash},
      source_decisions:{private_rehearsal_only:true,qualifications:report.qualifications,market_is_not_spec_evidence:true},
      drafts:[{manufacturer_identity:identity,variant_name:variant,extraction_confidence:1,facts,
        identity_evidence:{market:'SE',model_year:2027,manufacturer_code:'XABAA1',wheels_inches:20},
        field_evidence,price_evidence:{...proof('price_sek','comparison',970000),...prices,
          corroboration:{source_url:base,source_hash:primary.content_hash,quote:'Grundpris 970 000 kr'}}}]},
    image:{model_key:imageKey,asset_url:assetUrl,source_url:photoSource,content_sha256:imageHash,
      credit:photo.credit,reviewed_at:photo.sources['photo.jpg'].fetched_at,status:'verified_model_photo_private_only',
      asset_id:assetId,catalog_use_confirmed:false,private_folder:photoFolder},
  };
}

export function readMacanRehearsal({specs,market,photo}){
  const specFolder=privateFolder(specs,'porsche-macan-my27-');
  const marketFolder=privateFolder(market,'porsche-macan-market-');
  const photoFolder=privateFolder(photo,'porsche-macan-photo-');
  const report=JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs','scripts/porsche_macan_release_intake.py',
    '--specs',specFolder,'--market',marketFolder,'--photo',photoFolder],
  {cwd:root,encoding:'utf8',timeout:120000,windowsHide:true}));
  return macanIntakeFromReplay(report,photoFolder);
}

function readPrivateMacanImage(image,intake,models){
  fields(image,{status:'verified_model_photo_private_only',asset_url:assetUrl,source_url:photoSource,
    asset_id:assetId,credit:'Porsche AG',catalog_use_confirmed:false});
  assert.equal(models.filter(row=>row.brand===intake.model.brand&&row.model===intake.model.model).length,1);
  const file=join(privateFolder(image.private_folder,'porsche-macan-photo-'),'photo.jpg');
  assert.equal(realpathSync(file),file,'Require the exact private Macan JPEG');
  return readFileSync(file);
}

function validateIntake(intake){
  fields(intake.model,MACAN_MODEL);
  fields(intake.market.row,market);
  assert.deepEqual(intake.sources.map(s=>s.final_url),Object.values(urls));
  assert.equal(intake.drafts.length,1);
  const [draft]=intake.drafts;
  fields(draft,{manufacturer_identity:identity,variant_name:variant,facts});
  fields(draft.identity_evidence,{model_year:2027,manufacturer_code:'XABAA1',wheels_inches:20});
  fields(draft.price_evidence,{...prices,source_url:urls.comparison});
  fields(draft.price_evidence.corroboration,{source_url:base,source_hash:intake.sources[0].content_hash});
}

function checkDiscovery(snapshot,model,marketRow){
  assert.equal(model.validation_status,'draft');
  assert(!snapshot.market_models.some(row=>row.id!==marketRow.id&&row.canonical_model_id===model.id),
    'Only the exact Macan electric market row may link to this model');
}

function verifyPublic(rows,plan){
  assert.equal(rows.length,1,'One exact Macan variant required in the test projection');
  const row=rows[0];
  fields(row,{brand:MACAN_MODEL.brand,model:MACAN_MODEL.model,body_type:'SUV',variant_name:variant,
    validation_status:'published',market_seen:true,available_confirmed:plan.expected_model.available_confirmed,
    source_url:base,price_type:prices.price_type,price_valid_until:null,price_source_url:urls.comparison,
    image_url:assetUrl,image_source_url:photoSource});
  fields(Object.fromEntries(Object.keys(facts).map(k=>[k,k==='drivetrain'?row[k]:Number(row[k])])),facts);
  assert.equal(Number(row.price_sek),prices.value);
}

export const policy={adapter:ADAPTER,primaryUrl:base,aliasRule:'mobility_sweden_exact_raw_name',maxVariants:1,
  imageKey,imageHash,localOnly:true,privateMediaOnly:true,readPrivateImage:readPrivateMacanImage,
  scopedDiscovery:{market:MACAN_MODEL,check:checkDiscovery},validateIntake,verifyPublic};
