import assert from 'node:assert/strict';
import {applySpecPlan as apply,buildSpecPlan as build,specPlanHash} from './kia_spec_sync.mjs';
export {specPlanHash};
export const ADAPTER='kia_ev5_sweden_completion_v1';
const base='https://www.kia.com';
export const urls={technical:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev5/kia-sweden-ev5-specification.pdf',
 specifications:base+'/se/nya-bilar/ev5/specifikationer/',gt_specifications:base+'/se/nya-bilar/ev5-gt/specifikationer/',
 gt:base+'/se/nya-bilar/ev5-gt/upptack/',model:base+'/se/nya-bilar/ev5/upptack/',
 energy:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf',
 price_pdf:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
 poland_pdf:base+'/content/dam/kwcms/kme/pl/pl/assets/contents/utility/Price_list/ev5/Cennik_EV5_MY26-1_RP26_2026-06-18.pdf',
 gt_germany:base+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV5-GT-Preisliste.pdf'};
export const versions=[
 ['EV5 FWD','X9W5ZHZ7Z-LX1',18,554900,'FWD',552,16.0,1200],
 ['EV5 Plus AWD Long Range','X9W5YLZ7Z-SX1_V00',18,624900,'AWD',513,17.2,1800],
 ['EV5 GT Line AWD Long Range','X9W5YLZ7Z-GX1_V00',19,658900,'AWD',491,18.1,1800],
 ['EV5 GT Line Panorama AWD Long Range','X9W5YLZ7Z-GX1_V00',19,670900,'AWD',491,18.1,1800],
 ['EV5 GT (306hk) AWD Long Range','X9W5YRZ7Z-GX2',20,700900,'AWD',476,18.6,1800],
];
const gtBlock='EV5 GT Batterikapacitet: 81.4 kWh Laddningstid (min. DC 10-80%): 30 minuter Motoreffekt: 225 kW / 306 hk Max släpvagnsvikt, bromsat släp: 1,800 kg 0-100 km/h: 6.2 sekunder Toppfart: 180 km/h Max räckvidd (km) enligt WLTP (Upp till): 476 km';
const quotes={battery_kwh:'Batterikapacitet (kWh) 81.4 81.4',ac_charge_kw:'Bilens laddare (On Board Charger) (kW) 10.5',
 dc_charge_kw:'DC snabbladdning max kW 150',boot_liters:'BAGAGEUTRYMME Baksäte uppfällt / Nedfällt / Frunk 566 / 1 650 / 44',
 tow_kg:'Max släpvagnsvikt, bromsat släp 1 200 1 800',drivetrain:'FWD AWD',
 wltp_consumption_kwh_100km:'FÖRBRUKNING Blandad, kWh/100km enligt WLTP 16,0 (16,6 GT Line) 17,2 (18,1 GT Line)'};
const isGt=r=>r.variant_name==='EV5 GT (306hk) AWD Long Range';
export function validateSpecDraft(r,now=new Date()){
 assert.equal(r.adapter,ADAPTER);assert.equal(r.brand,'Kia');assert.equal(r.model,'Ev5');
 const profile=versions.find(p=>p[0]===r.variant_name);assert(profile,'Only five existing Swedish EV5 profiles');
 const [name,engine,wheel,cash,drive,range,consumption,tow]=profile,gt=isGt(r),panorama=name.includes('Panorama');
 assert.equal(r.source_resolution,'exact_swedish_ev5_my27_powertrain_wheel_and_panorama_not_gt_line_as_gt');
 assert(typeof r.extraction_confidence==='number'&&Number.isFinite(r.extraction_confidence)&&r.extraction_confidence>=0.92&&r.extraction_confidence<=1);
 assert.equal(r.source.final_url,gt?urls.gt:urls.technical);assert.equal(r.supporting_sources.length,7);
 const sources=new Map([r.source,...r.supporting_sources].map(s=>[s.final_url,s]));
 assert.deepEqual([...sources.keys()].sort(),Object.values(urls).filter(u=>u!==(gt?urls.technical:urls.gt)).sort());
 for(const s of sources.values()){
  assert.equal(s.status,'reachable');assert.equal(s.http_status,200);assert.match(s.content_hash,/^[a-f0-9]{64}$/);
  const age=now.getTime()-Date.parse(s.fetched_at);assert(Number.isFinite(age)&&age>=-60000&&age<=900000,'Fresh exact manufacturer evidence required');
 }
 const expected={battery_kwh:81.4,wltp_range_km:range,wltp_consumption_kwh_100km:consumption,
  dc_charge_kw:150,ac_charge_kw:10.5,tow_kg:tow,boot_liters:566,drivetrain:drive,seats:5};
 assert.deepEqual(r.facts,expected);assert.deepEqual(Object.keys(r.field_evidence).sort(),Object.keys(expected).sort());
 const engineName=gt?'Elmotor 306hk AWD (El , Elektrisk); 225 KW (306 hk)':drive==='AWD'?'Elmotor 265hk AWD (El , Elektrisk); 195 KW (265 hk)':'Elmotor 218hk FWD (El , Elektrisk); 160 KW (218 hk)';
 for(const[field,value]of Object.entries(expected)){
  const p=r.field_evidence[field];assert.equal(p.value,value);assert.equal(p.variant_name,name);
  assert.equal(p.column_header,`${name} | ${engine} | ${wheel} tum`);assert.equal(sources.get(p.source_url)?.content_hash,p.source_hash);
  if(field==='seats'){
   assert.equal(p.source_url,gt?urls.gt_specifications:urls.specifications);assert.equal(p.page,null);
   assert.equal(p.scope,panorama?'exact_swedish_nested_engine_and_panorama_option':'exact_swedish_nested_trim_engine');
   assert.equal(p.quote,engine+' | '+engineName+' | number of seats 5');
  }else if(!gt){
   assert.equal(p.source_url,urls.technical);assert.equal(p.page,3);
   assert.equal(p.scope,panorama?'swedish_my27_gt_line_panorama_option_group':'swedish_my27_powertrain_and_standard_wheels');
   assert.equal(p.quote,field==='wltp_range_km'?'Max räckvidd (km) enligt WLTP (Upp till): '+drive+(drive==='FWD'?' 552km, (534km GT Line)':' 513km, (491km GT Line)'):quotes[field]);
  }else{
   const cross={ac_charge_kw:['poland_pdf',15,'polish_same_306hp_gt_standard_not_22K','81.4 kWh AWD GT | Maksymalna moc ładowarki pokładowej [kW] 10.5 / 22 (z pakietem 22K)'],
    dc_charge_kw:['gt_germany',10,'german_same_225kw_gt_nominal_peak','Motor 81,4 kWh AWD | Leistung max. (kW/PS) 225/306 | Max. DC-Ladeleistung (kW) 150'],
    boot_liters:['gt_germany',11,'german_same_gt_seats_up_including_double_floor','Motor 81,4 kWh AWD | Laderaumvolumen bei aufgestellter Rücksitzbank, mit Einrechnung des doppelten Bodens 566'],
    wltp_consumption_kwh_100km:['energy',1,'swedish_october_306hp_gt_not_204hp_footer','EV5 | Elmotor 306hk AWD LR | 18,6 kWh'],
    drivetrain:['gt_specifications',null,'exact_swedish_nested_gt_drivetrain',engine+' | '+engineName]}[field];
   if(cross)assert.deepEqual([p.source_url,p.page,p.scope,p.quote],[urls[cross[0]],...cross.slice(1)]);
   else{assert.equal(p.source_url,urls.gt);assert.equal(p.page,null);assert.equal(p.scope,'swedish_306hp_gt_not_gt_line');assert.equal(p.quote,gtBlock);}
  }
 }
 const pe=r.price_evidence;assert.equal(pe.value,cash);assert.equal(pe.price_type,'list_price');assert.equal(pe.price_valid_until,'2026-11-30');assert.equal(pe.page,2);
 assert.equal(pe.source_url,urls.price_pdf);assert.equal(pe.source_hash,sources.get(urls.price_pdf).content_hash);
 assert.equal(pe.classification,'dated_november_swedish_list_not_undated_engine_or_lease');
 assert(pe.quote.startsWith((name==='EV5 FWD'?'EV5 FWD Long Range':name)+' '+cash.toLocaleString('en-US')+' kr'));
 const alternate=r.price_alternative,key=gt?'gt_specifications':'specifications';
 assert.deepEqual(alternate,{source_url:urls[key],source_hash:sources.get(urls[key]).content_hash,engine_code:engine,
  embedded_price:(panorama?658900:cash)-1000,reason:panorama?'undated_base_trim_price_excludes_panorama_total':'undated_engine_price_1000_below_dated_november_pdf'});
 assert.deepEqual(pe.alternative,alternate,'Preserve the exact rejected price observation in staging');
 assert(now.toISOString().slice(0,10)>='2026-11-01'&&now.toISOString().slice(0,10)<='2026-11-30');
 assert.deepEqual(r.model_facts,{body_type:'SUV'});assert.deepEqual(r.model_field_evidence,{body_type:{value:'SUV',source_url:urls.model,
  source_hash:sources.get(urls.model).content_hash,quote:'Upptäck Kia EV5 AWD, en el-SUV med gott om utrymme'}});
 assert.deepEqual(r.held_fields,{});assert(r.source_decisions.length>=11);return r;
}
const priceFields=['price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote','price_verified_at','price_source_name','price_refresh_batch_id'];
const extras=(r,old)=>{
 assert.equal(Number(old.price_sek),r.price_evidence.value);assert.equal(old.price_type,'list_price');assert([null,'2026-11-30'].includes(old.price_valid_until));
 const s=r.supporting_sources.find(s=>s.final_url===urls.price_pdf);
 return{price_type:'list_price',price_valid_until:'2026-11-30',price_source_url:urls.price_pdf,price_source_hash:s.content_hash,
  price_source_quote:r.price_evidence.quote,price_source_name:'Kia Sverige',price_verified_at:new Date(s.fetched_at).toISOString(),
  price_refresh_batch_id:specPlanHash({adapter:ADAPTER,evidence:r.price_evidence,verified:s.fetched_at})};
};
const policy={adapter:ADAPTER,validate:validateSpecDraft,sourceType:r=>isGt(r)?'manufacturer_model_page':'technical_pdf',
 sourceName:'Kia Sverige',sourceTitle:r=>isGt(r)?'EV5 GT 306hk: svenska modelluppgifter':'EV5 MY2027: svenska produktfakta',
 lockKey:7240016,extraFields:['ac_charge_kw'],modelFacts:r=>r.model_facts,canonicalFields:priceFields,canonicalExtras:extras,
 supportingSource:s=>{
  const key=Object.keys(urls).find(k=>urls[k]===s.final_url);if(!key||['gt','technical'].includes(key))return null;
  const shared=['energy','price_pdf'].includes(key),legacy=['model','specifications'].includes(key);
  return{model:shared?'*':legacy?'EV5':'Ev5',shared,sourceType:key==='price_pdf'?'price_list_pdf':s.final_url.endsWith('.pdf')?'technical_pdf':'manufacturer_page',
   title:key==='energy'?'Kia Sverige: bränsledeklaration oktober2026':key==='price_pdf'?'Kia Sverige: prislista november2026':'EV5: versionsbundna tillverkaruppgifter',
   country:key==='poland_pdf'?'PL':key==='gt_germany'?'DE':'SE',language:key==='poland_pdf'?'pl':key==='gt_germany'?'de':'sv',
   sourceName:key==='poland_pdf'?'Kia Polen':key==='gt_germany'?'Kia Tyskland':'Kia Sverige'};
 }};
export const buildSpecPlan=(rows,intake,now)=>{const p=build(rows,intake,now,policy);assert.equal(p.targets.length,5,'Reconcile all five EV5 profiles together');for(const t of p.targets)extras(t.draft,t.expected);return p;};
export const applySpecPlan=(client,plan,hash,now)=>apply(client,plan,hash,now,policy);
export const intakeFingerprint=intake=>intake.drafts.map(r=>JSON.parse(JSON.stringify(r,(key,value)=>['content_hash','source_hash','fetched_at'].includes(key)?undefined:value)));
