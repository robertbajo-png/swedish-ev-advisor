import assert from 'node:assert/strict';
import {applySpecPlan as apply,buildSpecPlan as build,specPlanHash} from './kia_spec_sync.mjs';
export {specPlanHash};
export const ADAPTER='kia_ev6_sweden_completion_v1';
const base='https://www.kia.com';
export const urls={
 technical:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev6/kia-sweden-ev6-specification.pdf',
 model:base+'/se/nya-bilar/ev6/upptack/',specifications:base+'/se/nya-bilar/ev6/technische-daten/',
 gt:base+'/se/nya-bilar/ev6-gt/upptack/',gt_specifications:base+'/se/nya-bilar/ev6-gt/specifikationer/',
 gt_germany:base+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV6-GT-Pricelist.pdf',
 energy:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf',
 price_pdf:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
};
export const versions=[
 ['EV6 RWD','ASW5ZHZ7Z-TX1',596400,'RWD',582,15.9,19],
 ['EV6 AWD','ASW5YCZ7Z-TX1',631400,'AWD',546,17.0,19],
 ['EV6 GT','ASW5YDZ7Z-GX2',771400,'AWD',450,20.9,21],
];
const quotes={battery_kwh:'Batterikapacitet (kWh) 84',ac_charge_kw:'Bilens laddare (On Board Charger) (kW) 10.5',
 dc_charge_kw:'DC snabbladdning max 258kW',wltp_range_km:'Max räckvidd (km) enligt WLTP upp till 582** upp till 546**',
 wltp_consumption_kwh_100km:'FÖRBRUKNING Blandad, kWh/100km enligt WLTP 15,9 17,0 19" / 17,7 20"',
 boot_liters:'BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv (liter) 480 / 1290 / 50 480 / 1290 / 20',
 tow_kg:'Max släpvagnsvikt (obromsat / bromsat släp) 750 / 1800 750 / 1800',drivetrain:'MOTOR Elmotor Elmotor RWD AWD'};
const gtBlock='Batterikapacitet: 84 kWh AWD - fyrhjulsdrift Räckvidd: upp till 450 km 12a Ultrasnabb laddning: 10-80 % på ner till 18 minuter 12b 0-100 km/h: 3,7 sekunder / 3,5 sekunder (med Launch Control aktiverat) Prestanda: 609 hk/448 kW samt vid Launch Control: 650 hk/478 kW Maxhastighet: 260 km/h Virtual Gear Shift / Adaptive Sound Design Dragvikt: upp till 1 800 kg';
const bodyQuote='Upptäck Kias snabbladdande crossover med en sportig design redan idag.';
const isGt=r=>r.variant_name==='EV6 GT';
export function validateSpecDraft(r,now=new Date()){
 assert.equal(r.adapter,ADAPTER);assert.equal(r.brand,'Kia');assert.equal(r.model,'Ev6');
 const profile=versions.find(p=>p[0]===r.variant_name);assert(profile,'Only the three existing EV6 profiles');
 const [name,engine,cash,drive,range,consumption,wheel]=profile,gt=isGt(r);
 assert.equal(r.source_resolution,'exact_swedish_ev6_84kwh_standard_19inch_and_separate_609_650hp_gt');
 assert(Number.isFinite(r.extraction_confidence)&&r.extraction_confidence>=0.92&&r.extraction_confidence<=1);
 assert.equal(r.source.final_url,gt?urls.gt:urls.technical);assert.equal(r.supporting_sources.length,7);
 const sources=new Map([r.source,...r.supporting_sources].map(s=>[s.final_url,s]));
 assert.deepEqual([...sources.keys()].sort(),Object.values(urls).sort());
 for(const s of sources.values()){
  assert.equal(s.status,'reachable');assert.equal(s.http_status,200);assert.match(s.content_hash,/^[a-f0-9]{64}$/);
  const age=now.getTime()-Date.parse(s.fetched_at);assert(Number.isFinite(age)&&age>=-60000&&age<=900000,'Fresh manufacturer source required');
 }
 const expected={battery_kwh:84,wltp_range_km:range,wltp_consumption_kwh_100km:consumption,
  dc_charge_kw:258,ac_charge_kw:10.5,tow_kg:1800,boot_liters:480,drivetrain:drive,seats:5};
 assert.deepEqual(r.facts,expected);assert.deepEqual(Object.keys(r.field_evidence).sort(),Object.keys(expected).sort());
 const engineName=gt?'Elmotor 650hk AWD (El , Elektrisk); 478 KW (650 hk)':drive==='AWD'
  ?'Elmotor 325hk AWD (El , Elektrisk); 239 KW (325 hk)':'Elmotor 228hk RWD (El , Elektrisk); 168 KW (229 hk)';
 for(const[field,value]of Object.entries(expected)){
  const p=r.field_evidence[field];assert.equal(p.value,value);assert.equal(p.variant_name,name);
  assert.equal(p.column_header,`${name} | ${engine} | ${wheel} tum`);assert.equal(sources.get(p.source_url)?.content_hash,p.source_hash);
  if(field==='seats'){
   assert.deepEqual([p.source_url,p.page,p.scope,p.quote],[gt?urls.gt_specifications:urls.specifications,null,
    'exact_swedish_nested_trim_engine',engine+' | '+engineName+' | number of seats 5']);
  }else if(!gt){
   assert.deepEqual([p.source_url,p.page,p.scope,p.quote],[urls.technical,3,'swedish_84kwh_base_trim_19inch',quotes[field]]);
  }else{
   const foreign={ac_charge_kw:[10,'Max. AC-Ladeleistung (kW) 3-phasig (AC), 10,5 kW'],
    dc_charge_kw:[10,'Max. DC-Ladeleistung (kW) 258'],
    boot_liters:[11,'Gepäckraumvolumen nach VDA (Liter), inkl. Ablagefach im Gepäckraumboden Sitze in Normalposition, bis Fensterhöhe, max. 480']}[field];
   if(foreign)assert.deepEqual([p.source_url,p.page,p.scope,p.quote],[urls.gt_germany,foreign[0],'german_same_84kwh_609_650hp_gt',foreign[1]]);
   else if(field==='wltp_consumption_kwh_100km')assert.deepEqual([p.source_url,p.page,p.scope,p.quote],
    [urls.energy,1,'swedish_october_gt_consumption','EV6 GT Elmotor 650hk El Euro 6ax 20,9 kWh']);
   else assert.deepEqual([p.source_url,p.page,p.scope,p.quote],[urls.gt,null,'swedish_same_gt_609hp_650hp_launch_control',gtBlock]);
  }
 }
 const pe=r.price_evidence;assert.equal(pe.value,cash);assert.equal(pe.price_type,'list_price');assert.equal(pe.price_valid_until,'2026-11-30');assert.equal(pe.page,2);
 assert.equal(pe.source_url,urls.price_pdf);assert.equal(pe.source_hash,sources.get(urls.price_pdf).content_hash);
 assert.equal(pe.classification,'dated_november_swedish_cash_list_and_matching_engine');
 const priceName=gt?'EV6 GT (650hk) AWD Long Range':name+' Long Range';
 assert(new RegExp('^'+priceName.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+' '+cash.toLocaleString('en-US')+' kr(?: [0-9,]+ kr)?$').test(pe.quote),'Exact Swedish cash row, never Plus, lease or paint');
 assert(now.toISOString().slice(0,10)>='2026-11-01'&&now.toISOString().slice(0,10)<='2026-11-30');
 assert.deepEqual(r.model_facts,{body_type:'Crossover'});assert.deepEqual(r.model_field_evidence,{body_type:{value:'Crossover',
  source_url:urls.model,source_hash:sources.get(urls.model).content_hash,quote:bodyQuote}});
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
const policy={adapter:ADAPTER,validate:validateSpecDraft,sourceType:r=>isGt(r)?'manufacturer_model_page':'technical_pdf',
 sourceName:'Kia Sverige',sourceTitle:r=>isGt(r)?'EV6 GT 84kWh: svenska modelluppgifter':'EV6 84kWh: svenska produktfakta',
 lockKey:7240016,extraFields:['ac_charge_kw'],modelFacts:r=>r.model_facts,allowedBodyTypes:['Crossover'],canonicalFields:priceFields,canonicalExtras:extras,
 resolveConflict:(field,old,value,previous,draft)=>field==='drivetrain'&&old==='GT'&&value==='AWD'&&
  previous.variant_name==='EV6 GT'&&isGt(draft)&&draft.source_resolution==='exact_swedish_ev6_84kwh_standard_19inch_and_separate_609_650hp_gt',
 supportingSource:s=>{
  const key=Object.keys(urls).find(k=>urls[k]===s.final_url);assert(key);
  const shared=['energy','price_pdf'].includes(key),legacy=['model','specifications'].includes(key);
  return{model:shared?'*':legacy?'EV6':'Ev6',shared,
   sourceType:key==='price_pdf'?'price_list_pdf':s.final_url.endsWith('.pdf')?'technical_pdf':'manufacturer_page',
   title:key==='price_pdf'?'Kia Sverige: prislista november2026':key==='energy'?'Kia Sverige: bränsledeklaration oktober2026':'EV6: versionsbundna tillverkaruppgifter',
   country:key==='gt_germany'?'DE':'SE',language:key==='gt_germany'?'de':'sv',sourceName:key==='gt_germany'?'Kia Tyskland':'Kia Sverige'};
 }};
export const buildSpecPlan=(rows,intake,now)=>{const plan=build(rows,intake,now,policy);assert.equal(plan.targets.length,3,'Reconcile all three EV6 versions');for(const t of plan.targets)extras(t.draft,t.expected);return plan;};
export const applySpecPlan=(client,plan,hash,now)=>apply(client,plan,hash,now,policy);
export const intakeFingerprint=intake=>intake.drafts.map(r=>JSON.parse(JSON.stringify(r,(key,value)=>['content_hash','source_hash','fetched_at'].includes(key)?undefined:value)));
