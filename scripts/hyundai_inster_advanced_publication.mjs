import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,realpathSync,statSync} from 'node:fs';
import {basename,dirname,join,resolve} from 'node:path';

export const ADAPTER='hyundai_inster_advanced_tech_private';
export const MODEL=Object.freeze({brand:'Hyundai',model:'Inster',normalized_brand:'hyundai',normalized_model:'inster',body_type:'SUV'});
export const VARIANT='49 kWh Advanced Tech 17-tum MY27';
export const MATERIAL='6XS5ZDZ7ZHH09P';
const identity='SE|MY27|'+MATERIAL+'|FWD|4|17';
const manual='https://ownersmanual.hyundai.com/full_webhelp/AXEV/2027/sv_SE/idee195341dda.html';
const dealer='https://hedinautomotive.se/bilar/kop-bil/258182/pc-nc-hyundai-inster-2027';
const locator='https://www.hyundai.com/se/sv/tjanster/online-tjanster/hitta-aterforsaljare/hitta-agent.html';
const model='https://www.hyundai.com/se/sv/bilar/inster.html';
const config='https://lager.hyundai.se/model/INSTER/'+MATERIAL+'?customer=corporate&ext=SRM&int=NNB';
const stock='https://lager.hyundai.se/model/INSTER?customer=private';
const design='https://www.hyundai.com/se/sv/bilar/inster/design.html';
const api='https://org-eu-www.hyundai.com/eu/papi';
const metadata={
  [config]:'manufacturer_configurator',[stock]:'manufacturer_configurator',[design]:'manufacturer_model_page',
  [manual]:'manufacturer_model_page',[dealer]:'authorized_dealer_stock_page',[locator]:'manufacturer_model_page',
};
const photoPolicy=JSON.parse(readFileSync(new URL('../src/inster-photo-policy.json',import.meta.url),'utf8'));
const {model_key:imageKey,content_sha256:imageHash,source_url:imageSource,asset_url:assetUrl}=photoPolicy;
const sha=/^[a-f0-9]{64}$/;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const fields=(row,expected)=>{for(const [key,value] of Object.entries(expected))
  assert.deepEqual(row?.[key],value,'Inster exact source or variant changed: '+key);};
export const facts=Object.freeze({wltp_range_km:360,wltp_consumption_kwh_100km:15.1,battery_kwh:49,dc_charge_kw:85.3,
  ac_charge_kw:10.5,boot_liters:238,tow_kg:0,seats:4,drivetrain:'FWD'});
const marketFields={brand_raw:'HYUNDAI',model_raw:'INSTER',fuel_type_raw:'EL',normalized_brand:'hyundai',
  normalized_model:'inster',last_seen_month:'2026-10-01',registrations_last_month:2,registrations_ytd:118,needs_mapping:false};
const price={value:377900,price_type:'manufacturer_from',price_valid_until:null,source_url:stock};
const photoFields={...photoPolicy,status:'documented'};

function checkedFile(path,cap){
  assert.equal(realpathSync(path),path);
  const stat=statSync(path);
  assert(stat.isFile()&&stat.size>0&&stat.size<=cap);
  return readFileSync(path);
}

export function readInsterCapture(path,sourceRoot){
  const root=join(sourceRoot,'data','local','release-data'),folder=resolve(path);
  assert.equal(realpathSync(root),root);
  assert.equal(realpathSync(folder),folder);
  assert.equal(dirname(folder),root);
  assert.match(basename(folder),/^inster-advanced-intake-[a-z0-9_]+$/);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(folder));
  const bytes=checkedFile(join(folder,'intake.json'),100000);
  const r=JSON.parse(bytes);
  fields(r,{status:'inster_advanced_exact_intake_private',publication_approved:false,production_writes:0,
    variant_price:price.value,image_sha256:imageHash});
  fields(r.factory,{status:'private_exact_swedish_advanced_emissions_hardware',material:MATERIAL,market:'SE',
    combined_wltp_km:360,consumption_kwh_100km:15.1,factory_price_excluding_optional_paint_sek:377900,
    battery_kwh:49,dc_charge_kw:85.3,ac_charge_kw:10.5,drivetrain:'FWD',publication_approved:false});
  fields(r.cargo,{boot_liters:238,sliding_seats_up_max_liters:351,minimum_is_seats_farthest_rearward:true});
  fields(r.seats,{status:'inster_exact_advanced_seats_verified_private',material:MATERIAL,model_year:2027,wheels_inches:17,must_include_tech_package:true});
  fields(r.seats.seats,{value:4,source_url:dealer,authorization_evidence_url:locator});
  fields(r.tow,{value:0,source_url:manual});
  fields(r.market,marketFields);
  function receipt(url){
    const {raw_file,...receipt}=r.sources[url];
    fields(receipt,{final_url:url,status:'reachable',http_status:200});
    assert.equal(basename(raw_file),raw_file);
    assert.equal(hash(checkedFile(join(folder,raw_file),8000000)),receipt.content_hash);
    return receipt;
  }
  const sources=Object.entries(metadata).map(([url,source_type])=>({...receipt(url),source_type,country:'SE',language:'sv',
    source_authority:url===dealer?'authorized_dealer':'manufacturer',source_name:url===dealer?'Hedin Automotive':'Hyundai Sverige',
    authorization_evidence_url:url===dealer?locator:null}));
  const factoryReceipts={},factoryData={};
  for(const op of ['Trims','EmissionQuery','Powertrains']){
    const item=r.factory.sources[op];
    fields(item,{url:api,http_status:200});
    const request=checkedFile(join(folder,op+'-request.json'),100000),response=checkedFile(join(folder,op+'-response.json'),1000000);
    assert.equal(hash(request),item.request_hash);
    assert.equal(hash(response),item.source_hash);
    const parsed=JSON.parse(request);
    assert.match(parsed.query,new RegExp('^query '+op+'\\('));
    fields(parsed.variables,{country:'se',language:'sv',service:'S03'});
    if(op==='EmissionQuery')fields(parsed.variables,{fsc:MATERIAL});
    if(op==='Powertrains')fields(parsed.variables,{trim:'TR0003'});
    const {data,errors}=JSON.parse(response);
    assert(!errors&&data);
    factoryData[op]=data;
    factoryReceipts[op]=item;
  }
  const trims=factoryData.Trims.hppFscs2.filter(row=>row.fsc===MATERIAL);
  assert.equal(trims.length,1);
  fields(trims[0],{trimId:'TR0003',powertrainId:'6XS5ZDZ7Z|1',fscPrice:price.value});
  assert.deepEqual(trims[0].packages.map(row=>row.pkgNm).sort(),["17'' Aluminiumf\u00e4lgar",'Tech-paket']);
  const motors=factoryData.Powertrains.hppPowertrains.filter(row=>row.powertrainId===trims[0].powertrainId);
  assert.equal(motors.length,1);
  const evidence=(value,url,quote,extra={})=>({value,variant_name:VARIANT,quote,source_url:url,
    source_hash:sources.find(s=>s.final_url===url).content_hash,...extra});
  const viaApi=(k,operation,key)=>{
    const actual=(operation==='EmissionQuery'?factoryData.EmissionQuery.hppCo2:motors[0])[key];
    if(k==='drivetrain')assert.equal(actual,'Framhjulsdrift');
    else{
      assert.match(String(actual),/^\d+(?:[.,]\d+)?$/);
      assert.equal(Number(String(actual).replace(',','.')),facts[k]);
    }
    return evidence(facts[k],config,'Hyundai Sverige '+MATERIAL+' / '+operation+' / '+key+': '+actual,
      {factory_read:{operation,key,...factoryReceipts[operation]}});
  };
  const field_evidence={
    wltp_range_km:viaApi('wltp_range_km','EmissionQuery','allElectricRange'),
    wltp_consumption_kwh_100km:viaApi('wltp_consumption_kwh_100km','EmissionQuery','electricityConsumpCombined'),
    battery_kwh:viaApi('battery_kwh','Powertrains','evBatteryCapacityKwh'),
    dc_charge_kw:viaApi('dc_charge_kw','Powertrains','maxChargingPower'),
    ac_charge_kw:viaApi('ac_charge_kw','Powertrains','evObcMaximumCapacity'),
    drivetrain:viaApi('drivetrain','Powertrains','powertrainNmDrivetrain'),
    boot_liters:evidence(238,design,'baks\u00e4tena skjutas fram 16 centimeter, vilket ut\u00f6kar bagageutrymmet fr\u00e5n 238 till 351 liter',
      {scope:'rear seats upright and farthest rearward'}),
    tow_kg:evidence(0,manual,r.tow.quote,{scope:'trailer prohibited; 75 kg bike carrier is not towing'}),
    seats:evidence(4,dealer,r.seats.seats.source_quote,{authorization_evidence_url:locator,
      equipment_scope:r.seats.factory_equipment_scope,photo_visual_check:r.seats.photo_visual_check}),
  };
  assert.equal(field_evidence.tow_kg.source_hash,r.tow.source_hash);
  assert.equal(field_evidence.seats.source_hash,r.seats.seats.source_hash);
  const marketSource=receipt(r.market.source_url);
  assert.equal(marketSource.content_hash,'1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6');
  const imageFile=join(root,'hyundai-inster-photo-8de96424','inster-prime-original.jpg');
  assert.equal(r.image_file,imageFile);
  const intake={adapter:ADAPTER,model:MODEL,sources,market:{row:r.market,source:marketSource},
    model_evidence:{url:model,swedish_material:config,scope:'regular Inster, not Cross'},
    source_decisions:{factory_receipts:factoryReceipts,model:receipt(model),photo_model_only:true},
    drafts:[{variant_name:VARIANT,manufacturer_identity:identity,extraction_confidence:0.98,facts,field_evidence,
      identity_evidence:{market:'SE',manufacturer_code:MATERIAL,model_year:2027,wheels_inches:17,tech_package:true},
      price_evidence:{...evidence(price.value,stock,'MATNR '+MATERIAL+'; ZMSRP 377900; PACKAGEPRICE 23000; COLOR 7500 (tillval)'),
        ...price,factory_read:factoryReceipts.Trims}}]};
  return {intake,image:{...photoFields,reviewed_at:'2026-11-23',private_file:imageFile},receipt_sha256:hash(bytes)};
}

function validateIntake(i){
  fields(i.model,MODEL);
  fields(i.market.row,marketFields);
  assert.deepEqual(i.sources.map(s=>s.final_url),Object.keys(metadata));
  assert.equal(i.drafts.length,1);
  const d=i.drafts[0];
  fields(d,{variant_name:VARIANT,manufacturer_identity:identity,facts});
  fields(d.identity_evidence,{model_year:2027,manufacturer_code:MATERIAL,wheels_inches:17,tech_package:true});
  fields(d.price_evidence,price);
  fields(d.field_evidence.dc_charge_kw.factory_read,{operation:'Powertrains',key:'maxChargingPower',url:api});
  fields(d.field_evidence.seats,{source_url:dealer,authorization_evidence_url:locator,quote:'"car_seats":"4"'});
  fields(d.field_evidence.tow_kg,{source_url:manual});
}

function readPrivateImage(image){
  fields(image,photoFields);
  const file=image.private_file;
  assert.match(file,/[\\/]data[\\/]local[\\/]release-data[\\/]hyundai-inster-photo-8de96424[\\/]inster-prime-original\.jpg$/);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(file));
  return checkedFile(file,6000000);
}

function verifyPublic(rows,plan){
  assert.equal(rows.length,1);
  fields(rows[0],{brand:MODEL.brand,model:MODEL.model,variant_name:VARIANT,body_type:'SUV',
    source_url:config,price_source_url:stock,price_type:price.price_type,image_url:assetUrl,image_source_url:imageSource,
    market_seen:true,available_confirmed:plan.expected_model.available_confirmed,validation_status:'published'});
  for(const [k,v] of Object.entries({...facts,price_sek:price.value}))assert.equal(typeof v==='number'?Number(rows[0][k]):rows[0][k],v);
}

export const policy={adapter:ADAPTER,primaryUrl:config,aliasRule:'mobility_sweden_exact_raw_name',imageKey,imageHash,maxVariants:1,
  localOnly:true,mixedSources:true,validateIntake,readPrivateImage,verifyPublic,
  scopedDiscovery:{market:marketFields,check(snapshot,model,market){
    assert(!snapshot.market_models.some(r=>r.id!==market.id&&r.canonical_model_id===model.id),
      'Only exact Inster BEV registrations can be linked');
  }}};
