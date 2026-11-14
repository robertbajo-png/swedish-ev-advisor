import assert from 'node:assert/strict';
import {applySpecPlan as apply,buildSpecPlan as build,specPlanHash} from './kia_spec_sync.mjs';
export {specPlanHash};
export const ADAPTER='cupra_born_sweden_my2027_v1';
export const base='https://www.cupraofficial.se';
export const urls={
 characteristics:base+'/datamanual-manual/manuals/cupra/se-se/CUPRA_Born_Datos_tecnicos_03_26_SE.pdf',
 price:base+'/content/dam/countries/se/cupra-website/prislistor/born/cupra-born-modellar-27.pdf',
 energy:base+'/content/dam/countries/se/cupra-website/broschyr/cupra-bransledeklaration-okt2026.pdf',
 manual:base+'/datamanual-manual/manuals/cupra/se-se/CUPRA_Born_03_26_SE.pdf',
 model:base+'/bilar/born',
 technical:'https://www.seat-cupra-mediacenter.com/content/dam/seat-media-center/models-all-brands/cupra-models/cupra-born/technical-data/New_CUPRA_Born_Technical_Data_26.pdf',
};
const header='VZ (240kW/79kWh)';
const fields={
 battery_kwh:[79,'characteristics','240 kW/84 kWh elmotor | Batteriets nettokapacitet (kWh) 79','sv_my2027_vz_net_and_onboard',3],
 drivetrain:['RWD','characteristics','240 kW/84 kWh elmotor | Drivning Bak','sv_my2027_vz_net_and_onboard',3],
 ac_charge_kw:[11,'characteristics','240 kW/84 kWh elmotor | Maximal AC-laddningsef- fekt (kW) 11','sv_my2027_vz_net_and_onboard',3],
 wltp_range_km:[631,'technical',header+' | Range (km) 631 - 552','final_global_vz_wltp_interval_maximum',1],
 dc_charge_kw:[183,'technical','ENDURANCE (170kW/79kWh) / VZ (240kW/79kWh) | Charging time DC 183kW 10-80% SoC (h) 0:29','final_shared_79kwh_peak_dc_not_58kwh',1],
 wltp_consumption_kwh_100km:[14.2,'energy','Born 79 kWh Batteri 240 kW / 326 hk – 14,2 0 | grundversion | WLTP','swedish_october_vz_grundversion',1],
 tow_kg:[0,'manual','Bilen är inte godkänd för dragkrok.','explicit_not_approved_for_trailers_not_missing',290],
 boot_liters:[385,'model','Bagagerumsvolym 385 L','current_swedish_born',null],
 seats:[5,'model','Säten 5','current_swedish_born',null],
};
export function validateSpecDraft(r,now=new Date()){
 assert.equal(r.adapter,ADAPTER);assert.equal(r.brand,'Cupra');assert.equal(r.model,'Born');assert.equal(r.variant_name,'Born VZ');
 assert.equal(r.source_resolution,'exact_my2027_swedish_vz_final_technical_data');
 assert(r.extraction_confidence>=0.92&&r.extraction_confidence<=1);
 assert.equal(r.source.final_url,urls.characteristics);assert.equal(r.supporting_sources.length,5);
 const sources=new Map([r.source,...r.supporting_sources].map(s=>[s.final_url,s]));
 assert.deepEqual([...sources.keys()].sort(),Object.values(urls).sort());
 for(const s of sources.values()){
  assert.equal(s.status,'reachable');assert.equal(s.http_status,200);assert.match(s.content_hash,/^[a-f0-9]{64}$/);
  const age=now-Date.parse(s.fetched_at);assert(Number.isFinite(age)&&age>=-60000&&age<=900000);
 }
 assert.deepEqual(Object.keys(r.facts).sort(),Object.keys(fields).sort());
 assert.deepEqual(Object.keys(r.field_evidence).sort(),Object.keys(fields).sort());
 for(const [field,[value,key,quote,scope,page]]of Object.entries(fields)){
  assert.equal(r.facts[field],value);
  assert.deepEqual(r.field_evidence[field],{value,quote,scope,page,column_header:header,variant_name:'Born VZ',
   source_url:urls[key],source_hash:sources.get(urls[key]).content_hash});
 }
 assert.deepEqual(r.price_evidence,{value:596900,price_type:'list_price',price_valid_until:null,
  source_url:urls.price,source_hash:sources.get(urls.price).content_hash,
  quote:'Born VZ 79 kWh 240 kW (326 hk) 596 900:–',classification:'swedish_my2027_vz_including_vat_not_lease_or_accessory'});
 assert.deepEqual(r.model_facts,{body_type:'Halvkombi'});
 assert.deepEqual(r.model_field_evidence,{body_type:{value:'Halvkombi',quote:'kombisedan',source_url:urls.model,source_hash:sources.get(urls.model).content_hash}});
 assert.deepEqual(r.held_fields,{});assert(r.source_decisions.length>=8);
 return r;
}
const priceFields=['price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote',
 'price_verified_at','price_source_name','price_refresh_batch_id'];
const extras=(r,old)=>{
 assert.equal(Number(old.price_sek),596900,'Keep the existing exact VZ price; do not overwrite another profile');
 assert.equal(old.price_type,'list_price');const s=r.supporting_sources.find(s=>s.final_url===urls.price);
 return {price_type:'list_price',price_valid_until:null,price_source_url:urls.price,price_source_hash:s.content_hash,
  price_source_quote:r.price_evidence.quote,price_source_name:'CUPRA Sverige',price_verified_at:new Date(s.fetched_at).toISOString(),
  price_refresh_batch_id:specPlanHash({adapter:ADAPTER,evidence:r.price_evidence,verified:s.fetched_at})};
};
const policy={adapter:ADAPTER,validate:validateSpecDraft,sourceType:'technical_pdf',sourceName:'CUPRA Sverige',
 sourceTitle:()=> 'Born VZ MY2027: svenska tekniska data, upplaga 03.26',lockKey:7240016,
 extraFields:['ac_charge_kw'],allowedBodyTypes:['Halvkombi'],modelFacts:r=>r.model_facts,
 canonicalFields:priceFields,canonicalExtras:extras,
 supportingSource:s=>Object.values(urls).includes(s.final_url)?{
  model:'Born',shared:false,sourceType:s.final_url===urls.price?'price_list_pdf':s.final_url.endsWith('.pdf')?'technical_pdf':'manufacturer_page',
  title:s.final_url===urls.technical?'New CUPRA Born: internationell slutlig VZ-tabell':'Born: aktuella svenska tillverkaruppgifter',
  country:s.final_url===urls.technical?'EU':'SE',language:s.final_url===urls.technical?'en':'sv',
  sourceName:s.final_url===urls.technical?'CUPRA internationellt':'CUPRA Sverige'}:null};
export const buildSpecPlan=(rows,intake,now)=>{
 const p=build(rows,intake,now,policy);assert.equal(p.targets.length,1,'Only the existing Born VZ profile');
 extras(p.targets[0].draft,p.targets[0].expected);return p;
};
export const applySpecPlan=(client,plan,hash,now)=>apply(client,plan,hash,now,policy);
