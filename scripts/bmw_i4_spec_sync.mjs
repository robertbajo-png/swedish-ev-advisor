import assert from 'node:assert/strict';
import {applySpecPlan as apply,buildSpecPlan as build,specPlanHash} from './kia_spec_sync.mjs';
import {BMW_URLS} from './bmw_i4_http.mjs';
export {specPlanHash};
export const ADAPTER='bmw_i4_sweden_61hd_v1';
export const NAME='i4 eDrive40 M Sport Business Edition (lagerbil FW37556)';
const vin='WBY61HD030FW37556',header='BMW i4 eDrive40 Gran Coupé | 61HD';
const fields={
 battery_kwh:[81.3,'Batterikapacitet [kWh] 81,3'],
 dc_charge_kw:[205,'Max. laddningseffekt DC [kW] 205'],
 ac_charge_kw:[11,'Max. laddningseffekt AC [kW] 11'],
 tow_kg:[1600,'Max. släpvagnsvikt (tillval), bromsad 12% / kultryck [kg] 1 600 / 75'],
 boot_liters:[470,'Bagagevolym [liter] 470–1 290'],
 wltp_consumption_kwh_100km:[14.9,'Elförbrukning, blandad körning (WLTP) [kWh/100 km] 17,1–14,9'],
 wltp_range_km:[588,'WLTP räckvidd 588 km','stock'],
 seats:[5,'Antal sittplatser 5','stock'],drivetrain:['RWD','Drivning Bakhjulsdriven','stock'],
};
export function validateSpecDraft(r,now=new Date()){
 assert.equal(r.adapter,ADAPTER);assert.equal(r.brand,'BMW');assert.equal(r.model,'i4');assert.equal(r.variant_name,NAME);
 assert.equal(r.source_resolution,'exact_stock_vin_61hd_not_21hd');
 assert(r.extraction_confidence>=0.92&&r.extraction_confidence<=1);
 assert.equal(r.source.final_url,BMW_URLS.technical);assert.equal(r.supporting_sources.length,1);
 assert.equal(r.supporting_sources[0].final_url,BMW_URLS.stock);
 const sources={technical:r.source,stock:r.supporting_sources[0]};
 for(const s of Object.values(sources)){
  assert.equal(s.status,'reachable');assert.equal(s.http_status,200);assert.match(s.content_hash,/^[a-f0-9]{64}$/);
  const age=now-Date.parse(s.fetched_at);assert(Number.isFinite(age)&&age>=-60000&&age<=900000);
 }
 assert.deepEqual(Object.keys(r.facts).sort(),Object.keys(fields).sort());
 assert.deepEqual(Object.keys(r.field_evidence).sort(),Object.keys(fields).sort());
 for(const [field,[value,quote,key='technical']]of Object.entries(fields)){
  assert.equal(r.facts[field],value);
  assert.deepEqual(r.field_evidence[field],{value,quote:(key==='technical'?header:vin)+' | '+quote,
   scope:key==='technical'?'manufacturer_type_61hd_not_21hd':'exact_stock_vin',page:null,column_header:header,
   variant_name:NAME,source_url:sources[key].final_url,source_hash:sources[key].content_hash});
 }
 assert.deepEqual(r.price_evidence,{value:673900,price_type:'dealer_offer',price_valid_until:'2026-12-31',
  source_url:BMW_URLS.stock,source_hash:sources.stock.content_hash,quote:vin+' | Kontantpris 673 900 kr',
  classification:'exact_new_stock_cash_offer_not_list_finance_or_zero_lease'});
 assert(now.toISOString().slice(0,10)<='2026-12-31');
 assert.deepEqual(r.model_facts,{body_type:'Coupé'});
 assert.deepEqual(r.model_field_evidence,{body_type:{value:'Coupé',quote:vin+' | bodyStyle COUPE',
  source_url:BMW_URLS.stock,source_hash:sources.stock.content_hash}});
 assert.deepEqual(r.held_fields,{});assert(r.source_decisions.length>=10);return r;
}
const eligible=old=>{
 assert.equal(old.variant_name,NAME);assert.equal(old.price_type,'dealer_offer');
 assert([675900,673900].includes(Number(old.price_sek)),'Only the documented stale stock offer may be replaced');
};
const priceFields=['price_sek','price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote',
 'price_verified_at','price_source_name','price_refresh_batch_id'];
const extras=(r,old)=>{
 eligible(old);const s=r.supporting_sources[0];
 return {price_sek:673900,price_type:'dealer_offer',price_valid_until:'2026-12-31',price_source_url:BMW_URLS.stock,
  price_source_hash:s.content_hash,price_source_quote:r.price_evidence.quote,price_source_name:'BMW Sverige / Bilia Nacka',
  price_verified_at:new Date(s.fetched_at).toISOString(),
  price_refresh_batch_id:specPlanHash({adapter:ADAPTER,evidence:r.price_evidence,verified:s.fetched_at})};
};
const policy={adapter:ADAPTER,validate:validateSpecDraft,sourceType:'manufacturer_model_page',sourceName:'BMW Sverige',
 sourceTitle:()=> 'BMW i4 eDrive40: svensk teknisk typ 61HD',lockKey:7240016,extraFields:['ac_charge_kw'],
 allowedBodyTypes:['Coupé'],modelFacts:r=>r.model_facts,canonicalFields:priceFields,canonicalExtras:extras,
 priceReplacement:(old,r)=>(eligible(old),r.price_evidence.value),priceRefresh:old=>(eligible(old),true),
 supportingSource:s=>s.final_url===BMW_URLS.stock?{model:'i4',shared:false,sourceType:'manufacturer_page',
  title:'BMW Sverige: exakt lagerbil FW37556 hos Bilia Nacka',country:'SE',language:'sv',sourceName:'BMW Sverige / Bilia Nacka'}:null};
export const buildSpecPlan=(rows,intake,now)=>{
 const p=build(rows,intake,now,policy);assert.equal(p.targets.length,1);extras(p.targets[0].draft,p.targets[0].expected);return p;
};
export const applySpecPlan=(client,plan,hash,now)=>apply(client,plan,hash,now,policy);
// Per-render source bytes may change. Recollection still validates every source and
// exact VIN/type/value/quote; retain all material facts in the comparison.
export const intakeFingerprint=intake=>intake.drafts.map(r=>JSON.parse(JSON.stringify(r,
 (key,value)=>['content_hash','source_hash','fetched_at'].includes(key)?undefined:value)));
