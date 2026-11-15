import assert from 'node:assert/strict';
import {applySpecPlan as apply,buildSpecPlan as build,specPlanHash} from './kia_spec_sync.mjs';
export {specPlanHash};
export const ADAPTER='kia_ev9_sweden_completion_v1';
const base='https://www.kia.com';
export const urls={
 technical:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev9/kia-sweden-ev9-gtline-specification.pdf',
 model:base+'/se/nya-bilar/ev9/upptack/',specifications:base+'/se/nya-bilar/ev9/specifications/',
 germany:base+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV9-Preisliste.pdf',
 price_pdf:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
};
export const versions=[
 ['EV9 RWD 7-SITS','DOW7ZHZ7Z-LX2',701900,701900,'RWD',443,18.7,76.1,900,7,19],
 ['EV9 AWD','DOW7YBZ7Z-TX2',819900,819900,'AWD',512,22.2,99.8,2500,7,19],
 ['EV9 AWD GT Line 7-sits','DOW7YBZ7Z-GX1',889900,889900,'AWD',505,22.8,99.8,2500,7,21],
 ['EV9 AWD GT Line 6-sits','DOW6YBZ7Z-SX2',909900,897900,'AWD',505,22.8,99.8,2500,6,21],
];
const quotes={battery_kwh:'Batterikapacitet (kWh) 76.1 99.8',ac_charge_kw:'Bilens laddare (On Board Charger) (kW) 10.5',
 dc_charge_kw:'DC snabbladdning max 210kW',wltp_range_km:'Max räckvidd (km) enligt WLTP (upp till) upp till 443* * upp till 512 (19"), 505 (21")**',
 wltp_consumption_kwh_100km:'FÖRBRUKNING Blandad, kWh/100km enligt WLTP 18,7 22,2 (19") 22,8 (21")',
 tow_kg:'Max släpvagnsvikt (obromsat / bromsat släp) 450 / 900 750 / 2 500',
 boot_liters:'BAGAGEUTRYMME 2-sits / 5-sits / 7-sits / under framhuv (liter) 2 318 / 828 / 333 / 52',
 drivetrain:'MOTOR Standard Range Long Range RWD AWD'};
const boot6='Alle Sitze in Normalposition, bis Fensterhöhe, max. 333';
const body='Kia EV9 är en robust, rymlig och helt elektrifierad SUV';
export function validateSpecDraft(r,now=new Date()){
 assert.equal(r.adapter,ADAPTER);assert.equal(r.brand,'Kia');assert.equal(r.model,'Ev9');
 const p=versions.find(v=>v[0]===r.variant_name);assert(p,'Only four exact existing EV9 profiles');
 const [name,engine,cash,webCash,drive,km,consumption,battery,tow,seats,wheel]=p;
 assert.equal(r.source_resolution,'swedish_ev9_218_384hp_19_21inch_separate_six_seven_seats');
 assert(Number.isFinite(r.extraction_confidence)&&r.extraction_confidence>=0.92&&r.extraction_confidence<=1);
 assert.equal(r.source.final_url,urls.technical);assert.equal(r.supporting_sources.length,4);
 const sources=new Map([r.source,...r.supporting_sources].map(s=>[s.final_url,s]));
 assert.deepEqual([...sources.keys()].sort(),Object.values(urls).sort());
 for(const s of sources.values()){
  assert.equal(s.status,'reachable');assert.equal(s.http_status,200);assert.match(s.content_hash,/^[a-f0-9]{64}$/);
  const age=now.getTime()-Date.parse(s.fetched_at);assert(Number.isFinite(age)&&age>=-60000&&age<=900000);
 }
 const expected={battery_kwh:battery,ac_charge_kw:10.5,dc_charge_kw:210,wltp_range_km:km,
  wltp_consumption_kwh_100km:consumption,tow_kg:tow,boot_liters:333,drivetrain:drive,seats};
 assert.deepEqual(r.facts,expected);assert.deepEqual(Object.keys(r.field_evidence).sort(),Object.keys(expected).sort());
 const engineName=name==='EV9 AWD GT Line 7-sits'?'Elmotor 384hk AWD (El , Elektrisk);':
  seats===6?'Elmotor 384hk AWD (El , Elektrisk); 283 KW (384 hk)':drive==='AWD'
   ?'Elmotor 384hk AWD (El , Elektrisk); 282 KW (384 hk)':'Elmotor 218hk RWD (El , Elektrisk); 160 KW (218 hk)';
 for(const[field,value]of Object.entries(expected)){
  const e=r.field_evidence[field];assert.equal(e.value,value);assert.equal(e.variant_name,name);
  assert.equal(e.column_header,`${name} | ${engine} | ${wheel} tum | ${seats} sittplatser`);
  assert.equal(sources.get(e.source_url)?.content_hash,e.source_hash);
  const binding=field==='seats'?[urls.specifications,null,'exact_swedish_flat_trim_engine',engine+' | '+engineName+' | number of seats '+seats]:
   field==='boot_liters'&&seats===6?[urls.germany,15,'german_same_ev9_all_six_seats_upright_vda',boot6]:
    [urls.technical,3,'swedish_standard_wheels_and_seating',quotes[field]];
  assert.deepEqual([e.source_url,e.page,e.scope,e.quote],binding);
 }
 const pe=r.price_evidence;assert.equal(pe.value,cash);assert.equal(pe.price_type,'list_price');assert.equal(pe.price_valid_until,'2026-11-30');
 assert.equal(pe.page,2);assert.equal(pe.source_url,urls.price_pdf);assert.equal(pe.source_hash,sources.get(urls.price_pdf).content_hash);
 assert.equal(pe.classification,'dated_november_swedish_cash_over_undated_engine');
 const priceName=drive==='RWD'?'EV9 RWD 7-SITS':name.includes('GT Line')?`EV9 GT Line AWD ${seats}-SITS Long Range`:'EV9 AWD 7-SITS Long Range';
 assert(new RegExp('^'+priceName+' '+cash.toLocaleString('en-US')+' kr(?: [0-9,]+ kr)?$').test(pe.quote));
 assert.deepEqual(pe.alternatives,[{value:webCash,source_url:urls.specifications,
  source_hash:sources.get(urls.specifications).content_hash,quote:engine+' | price '+webCash}]);
 assert(now.toISOString().slice(0,10)>='2026-11-01'&&now.toISOString().slice(0,10)<='2026-11-30');
 assert.deepEqual(r.model_facts,{body_type:'SUV'});assert.deepEqual(r.model_field_evidence,{body_type:{value:'SUV',
  source_url:urls.model,source_hash:sources.get(urls.model).content_hash,quote:body}});
 assert.deepEqual(r.held_fields,{});assert(r.source_decisions.length>=10);return r;
}
const priceFields=['price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote','price_verified_at','price_source_name','price_refresh_batch_id'];
const extras=(r,old)=>{
 assert.equal(Number(old.price_sek),r.price_evidence.value);assert.equal(old.price_type,'list_price');assert([null,'2026-11-30'].includes(old.price_valid_until));
 const source=r.supporting_sources.find(s=>s.final_url===urls.price_pdf);
 return{price_type:'list_price',price_valid_until:'2026-11-30',price_source_url:urls.price_pdf,price_source_hash:source.content_hash,
  price_source_quote:r.price_evidence.quote,price_source_name:'Kia Sverige',price_verified_at:new Date(source.fetched_at).toISOString(),
  price_refresh_batch_id:specPlanHash({adapter:ADAPTER,evidence:r.price_evidence,verified:source.fetched_at})};
};
const policy={adapter:ADAPTER,validate:validateSpecDraft,sourceType:'technical_pdf',sourceName:'Kia Sverige',
 sourceTitle:()=> 'EV9: svenska produktfakta och versionsbundna sittplatser',lockKey:7240016,
 extraFields:['ac_charge_kw'],modelFacts:r=>r.model_facts,canonicalFields:priceFields,canonicalExtras:extras,
 supportingSource:s=>{
  const key=Object.keys(urls).find(k=>urls[k]===s.final_url);assert(key);
  return{model:key==='price_pdf'?'*':key==='germany'?'Ev9':'EV9',shared:key==='price_pdf',
   sourceType:key==='price_pdf'?'price_list_pdf':key==='germany'?'technical_pdf':'manufacturer_page',
   title:key==='price_pdf'?'Kia Sverige: prislista november2026':'EV9: exakt versions- och sittplatsunderlag',
   country:key==='germany'?'DE':'SE',language:key==='germany'?'de':'sv',sourceName:key==='germany'?'Kia Tyskland':'Kia Sverige'};
 }};
export const buildSpecPlan=(rows,intake,now)=>{const plan=build(rows,intake,now,policy);assert.equal(plan.targets.length,4);for(const t of plan.targets)extras(t.draft,t.expected);return plan;};
export const applySpecPlan=(client,plan,hash,now)=>apply(client,plan,hash,now,policy);
export const intakeFingerprint=intake=>intake.drafts.map(r=>JSON.parse(JSON.stringify(r,(k,v)=>['content_hash','source_hash','fetched_at'].includes(k)?undefined:v)));
