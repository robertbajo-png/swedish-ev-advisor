import assert from 'node:assert/strict';
import {applySpecPlan as apply,buildSpecPlan as build,specPlanHash} from './kia_spec_sync.mjs';
export {specPlanHash};
export const ADAPTER='kia_ev4_sweden_completion_v1';
const base='https://www.kia.com';
export const urls={
 technical:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev4/kia-sweden-ev4-specification.pdf',
 specifications:base+'/se/nya-bilar/ev4/specs/',gt_specifications:base+'/se/nya-bilar/ev4-gt/specifications/',gt:base+'/se/nya-bilar/ev4-gt/upptack/',
 energy:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf',
 price_pdf:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
 poland:base+'/pl/modele/ev4/dane-techniczne/',
 gt_germany:base+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV4-GT-Preisliste.pdf'};
export const versions=[
 ['EV4 GT Line FWD Long Range','7ZS6ZHZ7Z-LX1',19,623400,'FWD',584,15.8,1000,435],
 ['EV4 GT Line AWD Long Range','7ZS6YGZ7Z-LX1_V00',19,658400,'AWD',550,16.5,1500,359],
 ['EV4 GT (292hk) AWD Long Range','7ZS6YGZ7Z-LX2',20,711900,'AWD',505,17.9,1500,359],
];
const gtBlock='EV4 GT Batterikapacitet: 81.4 kWh Laddningstid (min. DC 10-80%): 31 minutes Motoreffekt: 215 kW / 292 hk Max släpvagnsvikt, bromsat släp: 1,500 kg Acceleration (0-100 km/h) : 5.6 sekunder Max räckvidd (km) enligt WLTP (Upp till): 505 km';
const quotes={battery_kwh:'Batterikapacitet (kWh) 81.4',ac_charge_kw:'Bilens laddare (On Board Charger) (kW) 10.5',
 dc_charge_kw:'DC snabbladdning max kW 128',wltp_range_km:'Max räckvidd (km) enligt WLTP (Upp till) 584 550',
 wltp_consumption_kwh_100km:'FÖRBRUKNING Blandad, kWh/100km enligt WLTP 15.8 16.5',
 boot_liters:'BAGAGEUTRYMME Baksäte uppfällt / nedfällt 435 / 1450 359 / 1370',tow_kg:'Max släpvagnsvikt, bromsat släp 1 000 1 500',drivetrain:'FWD AWD'};
const isGt=r=>r.variant_name==='EV4 GT (292hk) AWD Long Range';
export function validateSpecDraft(r,now=new Date()){
 assert.equal(r.adapter,ADAPTER);assert.equal(r.brand,'Kia');assert.equal(r.model,'Ev4');
 const profile=versions.find(p=>p[0]===r.variant_name);assert(profile,'Only three exact current hatchback profiles');
 const [name,engine,wheel,cash,drive,range,consumption,tow,boot]=profile,gt=isGt(r);
 assert.equal(r.source_resolution,'exact_swedish_ev4_hatchback_my27_not_fastback_or_gt_line_as_gt');
 assert(typeof r.extraction_confidence==='number'&&Number.isFinite(r.extraction_confidence)&&r.extraction_confidence>=0.92&&r.extraction_confidence<=1);
 assert.equal(r.source.final_url,gt?urls.gt:urls.technical);assert.equal(r.supporting_sources.length,6);
 const sources=new Map([r.source,...r.supporting_sources].map(s=>[s.final_url,s]));
 assert.deepEqual([...sources.keys()].sort(),Object.values(urls).filter(u=>u!==(gt?urls.technical:urls.gt)).sort());
 for(const s of sources.values()){
  assert.equal(s.status,'reachable');assert.equal(s.http_status,200);assert.match(s.content_hash,/^[a-f0-9]{64}$/);
  const age=now.getTime()-Date.parse(s.fetched_at);assert(Number.isFinite(age)&&age>=-60000&&age<=900000,'Fresh exact manufacturer evidence required');
 }
 const expected={battery_kwh:81.4,wltp_range_km:range,wltp_consumption_kwh_100km:consumption,
  dc_charge_kw:128,ac_charge_kw:10.5,tow_kg:tow,boot_liters:boot,drivetrain:drive,seats:5};
 assert.deepEqual(r.facts,expected);assert.deepEqual(Object.keys(r.field_evidence).sort(),Object.keys(expected).sort());
 for(const [field,value]of Object.entries(expected)){
  const p=r.field_evidence[field];assert.equal(p.value,value);assert.equal(p.variant_name,name);
  assert.equal(p.column_header,`${name} | ${engine} | ${wheel} tum`);assert.equal(sources.get(p.source_url)?.content_hash,p.source_hash);
  const engineName=gt?'Elmotor AWD (El , Elektrisk); 215 KW (292 hk)':drive==='AWD'?'Elmotor AWD (El , Elektrisk); 195 KW (265 hk)':'Elmotor 204hk FWD (El , Elektrisk); 150 KW (204 hk)';
  if(field==='seats'){
   assert.equal(p.source_url,gt?urls.gt_specifications:urls.specifications);assert.equal(p.page,null);
   assert.equal(p.scope,gt?'exact_swedish_flat_gt_trim_engine':'exact_swedish_nested_trim_engine');
   assert.equal(p.quote,engine+' | '+engineName+' | number of seats 5');
  }else if(!gt){
   assert.equal(p.source_url,urls.technical);assert.equal(p.page,3);assert.equal(p.scope,'swedish_my27_gt_line_19inch_column');assert.equal(p.quote,quotes[field]);
  }else{
   const cross={wltp_consumption_kwh_100km:['energy',1,'swedish_october_gt_not_generic_footer','EV4 | Elmotor 292hk AWD LR | 17,9 kWh'],
    dc_charge_kw:['gt_germany',11,'german_same_gt_nominal_peak_not_supply_rating','Motor 81,4 kWh AWD GT | Leistung max. (kW/PS) 215/292 | Max. DC-Ladeleistung (kW) 128'],
    ac_charge_kw:['poland',null,'polish_same_gt_standard_not_optional_22','81,4 kWh AWD GT | Max. moc ładowarki pokładowej AC [kW] 10,5 / 22 (opcja)'],
    boot_liters:['poland',null,'polish_same_gt_not_390_awd_or_377_double_floor','81,4 kWh AWD GT | Pojemność bagażnika [l] 359'],
    drivetrain:['gt_specifications',null,'exact_swedish_flat_gt_drivetrain',engine+' | '+engineName]}[field];
   if(cross)assert.deepEqual([p.source_url,p.page,p.scope,p.quote],[urls[cross[0]],...cross.slice(1)]);
   else{assert.equal(p.source_url,urls.gt);assert.equal(p.page,null);assert.equal(p.scope,'swedish_292hp_gt_not_gt_line');assert.equal(p.quote,gtBlock);}
  }
 }
 const pe=r.price_evidence;assert.equal(pe.value,cash);assert.equal(pe.price_type,'list_price');assert.equal(pe.price_valid_until,'2026-11-30');
 assert.equal(pe.source_url,urls.price_pdf);assert.equal(pe.source_hash,sources.get(urls.price_pdf).content_hash);
 assert.equal(pe.classification,'november_swedish_list_inclusive_vat_not_lease_or_paint');assert(pe.quote.startsWith(name+' '+cash.toLocaleString('en-US')+' kr'));
 assert(now.toISOString().slice(0,10)>='2026-11-01'&&now.toISOString().slice(0,10)<='2026-11-30');
 assert.deepEqual(r.model_facts,{body_type:'Halvkombi'});assert.deepEqual(r.model_field_evidence,{body_type:{value:'Halvkombi',
  quote:'EV4 | 7Z/S6 | Halvkombins design baktill.',source_url:urls.specifications,source_hash:sources.get(urls.specifications).content_hash}});
 for(const [key,quote]of Object.entries({gt_tyre_basis:'Reichweite2, max. (km) 473 (20" Michelin)/505 (20" Pirelli)',
  gt_boot_basis:'Laderaumvolumen bei aufgestellter Rücksitzbank, mit Einrechnung des doppelten Bodens 377'}))
  assert.deepEqual(r.qualifications[key],{source_url:urls.gt_germany,source_hash:sources.get(urls.gt_germany).content_hash,page:12,quote});
 assert.deepEqual(r.held_fields,{});assert(r.source_decisions.length>=12);return r;
}
const priceFields=['price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote','price_verified_at','price_source_name','price_refresh_batch_id'];
const extras=(r,old)=>{
 assert.equal(Number(old.price_sek),r.price_evidence.value);assert.equal(old.price_type,'list_price');assert([null,'2026-11-30'].includes(old.price_valid_until));
 const s=r.supporting_sources.find(s=>s.final_url===urls.price_pdf);
 return {price_type:'list_price',price_valid_until:'2026-11-30',price_source_url:urls.price_pdf,price_source_hash:s.content_hash,
  price_source_quote:r.price_evidence.quote,price_source_name:'Kia Sverige',price_verified_at:new Date(s.fetched_at).toISOString(),
  price_refresh_batch_id:specPlanHash({adapter:ADAPTER,evidence:r.price_evidence,verified:s.fetched_at})};
};
const policy={adapter:ADAPTER,validate:validateSpecDraft,sourceType:r=>isGt(r)?'manufacturer_model_page':'technical_pdf',
 sourceName:'Kia Sverige',sourceTitle:r=>isGt(r)?'EV4 GT 292hk: svenska modelluppgifter':'EV4 GT Line MY2027: svenska produktfakta',
 lockKey:7240016,extraFields:['ac_charge_kw'],allowedBodyTypes:['Halvkombi'],modelFacts:r=>r.model_facts,canonicalFields:priceFields,canonicalExtras:extras,
 supportingSource:s=>{
  const key=Object.keys(urls).find(k=>urls[k]===s.final_url);if(!key||['gt','technical'].includes(key))return null;
  const shared=['energy','price_pdf'].includes(key);
  return {model:shared?'*':'Ev4',shared,sourceType:key==='price_pdf'?'price_list_pdf':s.final_url.endsWith('.pdf')?'technical_pdf':'manufacturer_page',
   title:key==='energy'?'Kia Sverige: bränsledeklaration oktober2026':key==='price_pdf'?'Kia Sverige: prislista november2026':'EV4: versionsbundna tillverkaruppgifter',
   country:key==='poland'?'PL':key==='gt_germany'?'DE':'SE',language:key==='poland'?'pl':key==='gt_germany'?'de':'sv',
   sourceName:key==='poland'?'Kia Polen':key==='gt_germany'?'Kia Tyskland':'Kia Sverige'};
 }};
export const buildSpecPlan=(rows,intake,now)=>{const p=build(rows,intake,now,policy);assert.equal(p.targets.length,3,'Reconcile all three EV4 versions together');for(const t of p.targets)extras(t.draft,t.expected);return p;};
export const applySpecPlan=(client,plan,hash,now)=>apply(client,plan,hash,now,policy);
export const intakeFingerprint=intake=>intake.drafts.map(r=>JSON.parse(JSON.stringify(r,(key,value)=>['content_hash','source_hash','fetched_at'].includes(key)?undefined:value)));
