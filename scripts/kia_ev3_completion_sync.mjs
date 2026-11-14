import assert from 'node:assert/strict';
import {applySpecPlan as apply,buildSpecPlan as build,specPlanHash} from './kia_spec_sync.mjs';
export {specPlanHash};
export const ADAPTER='kia_ev3_sweden_completion_v1';
const base='https://www.kia.com';
export const urls={
 technical:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev3/Faktablad-Kia-EV3.pdf',
 specifications:base+'/se/nya-bilar/ev3/specifikationer/',gt_specifications:base+'/se/nya-bilar/ev3-gt/specifikationer/',
 gt:base+'/se/nya-bilar/ev3-gt/upptack/',
 energy:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf',
 price_pdf:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
 poland:base+'/pl/modele/ev3/dane-techniczne/',
 gt_germany:base+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV3-GT-Preisliste.pdf',
};
export const versions=[
 ['EV3 FWD','9VW5ZHZ7Z-TX1',17,434900,'FWD',58.3,436,14.9,101,500,460],
 ['EV3 FWD Long Range','9VW5ZHZ7Z-LX1',17,508300,'FWD',81.4,605,14.9,128,1000,460],
 ['EV3 Plus FWD Long Range','9VW5ZHZ7Z-LX2',17,540300,'FWD',81.4,605,14.9,128,1000,460],
 ['EV3 GT Line FWD Long Range','9VW5ZHZ7Z-SX1',19,590300,'FWD',81.4,563,16.2,128,1000,460],
 ['EV3 Plus AWD Long Range','9VW5YGZ7Z-LX3',19,575300,'AWD',81.4,572,15.8,128,1500,413],
 ['EV3 GT Line AWD Long Range','9VW5YGZ7Z-SX2',19,625300,'AWD',81.4,572,15.8,128,1500,413],
 ['EV3 GT (292hk) AWD Long Range','9VW5YGZ7Z-DX1',20,650900,'AWD',81.4,532,17.1,128,1500,413],
];
const gtBlock='EV3 GT Batterikapacitet: 81.4 kWh Laddningstid (min. DC 10-80%): 31 minuter Motoreffekt: 215 kW / 292 hk Max släpvagnsvikt, bromsat släp: 1,500 kg 0-100 km/h: 5.7 sekunder Toppfart: 170 km/h Max räckvidd (km) enligt WLTP (Upp till): 532 km';
const preliminary='(AWD, Preliminär information i väntan på homologering)';
const isGt=r=>r.variant_name==='EV3 GT (292hk) AWD Long Range';
export function validateSpecDraft(r,now=new Date()){
 assert.equal(r.adapter,ADAPTER);assert.equal(r.brand,'Kia');assert.equal(r.model,'Ev3');
 const s=versions.find(s=>s[0]===r.variant_name);assert(s,'Only seven exact existing EV3 identities');
 const [name,engine,wheel,cash,drive,battery,range,consumption,dc,tow,boot]=s,gt=isGt(r);
 assert.equal(r.source_resolution,'current_swedish_exact_ev3_trim_not_gt_line_as_gt');
 assert(r.extraction_confidence>=0.92&&r.extraction_confidence<=1);
 assert.equal(r.source.final_url,gt?urls.gt:urls.technical);assert.equal(r.supporting_sources.length,6);
 const sources=new Map([r.source,...r.supporting_sources].map(s=>[s.final_url,s]));
 assert.deepEqual([...sources.keys()].sort(),Object.values(urls).filter(u=>u!==(gt?urls.technical:urls.gt)).sort());
 for(const s of sources.values()){
  assert.equal(s.status,'reachable');assert.equal(s.http_status,200);assert.match(s.content_hash,/^[a-f0-9]{64}$/);
  const age=now-Date.parse(s.fetched_at);assert(Number.isFinite(age)&&age>=-60000&&age<=900000);
 }
 assert.deepEqual(r.facts,{...(gt?{wltp_range_km:range,battery_kwh:battery,tow_kg:tow,drivetrain:drive,dc_charge_kw:dc,ac_charge_kw:10.5,boot_liters:boot}
  :{battery_kwh:battery,dc_charge_kw:dc,ac_charge_kw:10.5,wltp_range_km:range,tow_kg:tow,boot_liters:boot,drivetrain:drive}),wltp_consumption_kwh_100km:consumption,seats:5});
 assert.deepEqual(Object.keys(r.field_evidence).sort(),Object.keys(r.facts).sort());
 const quoteFor={battery_kwh:'Batterikapacitet (kWh) 58.3 81.4',dc_charge_kw:'DC snabbladdning max kW 101 128',
  ac_charge_kw:'Bilens laddare (On Board Charger) (kW) 10.5',
  wltp_range_km:'Max räckvidd (km) enligt WLTP (Upp till) '+(drive==='AWD'?'AWD 572 (19")':'FWD 436 (17") 605 (17") & 563 (19")'),
  tow_kg:'Max släpvagnsvikt, bromsat släp 500 1 000 / 1500',
  boot_liters:drive==='AWD'?'Baksäte uppfällt / nedfällt / under framhuv (liter) AWD 413 / 1204 / 25':'BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv (liter) FWD 460 / 1251 / 25',
  drivetrain:'FWD FWD/AWD'};
 for(const [field,value]of Object.entries(r.facts)){
  const p=r.field_evidence[field];assert.equal(p.value,value);assert.equal(p.variant_name,name);
  assert.equal(p.column_header,`${name} | ${engine} | ${wheel} tum`);assert.equal(sources.get(p.source_url)?.content_hash,p.source_hash);
  if(field==='seats'){
   assert.equal(p.source_url,gt?urls.gt_specifications:urls.specifications);assert.equal(p.scope,'exact_swedish_engine_trim');assert.equal(p.page,null);
   assert.equal(p.quote,engine+' | '+(gt?'Elmotor AWD (El , Elektrisk); 215 KW (292 hk)':drive==='AWD'?'Elmotor AWD (El , Elektrisk); 195 KW (265 hk)':'Elmotor 204hk FWD (El , Elektrisk); 150 KW (204 hk)')+' | number of seats 5');
  }else if(field==='wltp_consumption_kwh_100km'){
   assert.equal(p.source_url,drive==='FWD'?urls.technical:urls.energy);assert.equal(p.page,drive==='FWD'?3:1);
   assert.equal(p.scope,drive==='FWD'?'swedish_fwd_exact_17_or_19_wheel':'swedish_october_powertrain_not_foreign_wltp');
   assert.equal(p.quote,drive==='FWD'?'Blandad, kWh/100km enligt WLTP FWD 1 4,9 (17") 14,9 (17") & 16,2 (19")':gt?'EV3 | Elmotor 292hk AWD LR | 17,1 kWh':'EV3 | Elmotor 265hk AWD LR | 15,8 kWh');
  }else if(!gt){
   assert.equal(p.source_url,urls.technical);assert.equal(p.page,3);
   assert.equal(p.scope,drive==='AWD'?'swedish_265hp_awd_preliminary':'swedish_final_fwd_wheel_column');
   assert.equal(p.quote,(drive==='AWD'?preliminary+' | ':'')+quoteFor[field]);
  }else{
   const expected={dc_charge_kw:['gt_germany',12,'german_same_gt_nominal_peak','Motor 81,4 kWh AWD GT | Leistung max. (kW/PS) 215/292 | Max. DC-Ladeleistung (kW) 128'],
    ac_charge_kw:['poland',null,'polish_same_292hp_gt_standard_not_optional_22','81,4 kWh AWD GT | Max. moc ładowarki pokładowej AC [kW] 10,5 / 22 (opcja)'],
    boot_liters:['poland',null,'polish_same_gt_seats_up_not_folded','81,4 kWh AWD GT | Pojemność bagażnika tył [l] 413 / 1 204']}[field];
   if(expected)assert.deepEqual([p.source_url,p.page,p.scope,p.quote],[urls[expected[0]],...expected.slice(1)]);
   else{
    assert.equal(p.source_url,urls.gt);assert.equal(p.page,null);assert.equal(p.scope,'swedish_292hp_gt_not_gt_line');
    assert.equal(p.quote,field==='drivetrain'?'EV3 GT är utrustad med fyrhjulsdrift (AWD) med dubbla elmotorer och ett batteri på 81,4 kWh':gtBlock);
   }
  }
 }
 const pe=r.price_evidence;assert.equal(pe.value,cash);assert.equal(pe.price_type,'list_price');assert.equal(pe.price_valid_until,'2026-11-30');
 assert.equal(pe.source_url,urls.price_pdf);assert.equal(pe.source_hash,sources.get(urls.price_pdf).content_hash);
 assert.equal(pe.classification,'november_swedish_list_inclusive_vat_not_lease_or_paint');
 assert(pe.quote.startsWith(name+' '+cash.toLocaleString('en-US')+' kr'));assert(now.toISOString().slice(0,10)>='2026-11-01'&&now.toISOString().slice(0,10)<='2026-11-30');
 assert.deepEqual(r.model_facts,{body_type:'SUV'});assert.deepEqual(r.model_field_evidence,{body_type:{value:'SUV',
  quote:'vehicle_name '+(gt?'ev3gt':'ev3')+' | vehicle_type suv---stadsjeep',source_url:gt?urls.gt_specifications:urls.specifications,
  source_hash:sources.get(gt?urls.gt_specifications:urls.specifications).content_hash}});
 assert.deepEqual(r.held_fields,{});assert(r.source_decisions.length>=11);return r;
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
 sourceName:'Kia Sverige',sourceTitle:r=>isGt(r)?'EV3 GT 292hk: svenska modelluppgifter':'EV3: svenska produktfakta 16 september2026',
 lockKey:7240016,extraFields:['ac_charge_kw'],allowedBodyTypes:['SUV'],modelFacts:r=>r.model_facts,
 canonicalFields:priceFields,canonicalExtras:extras,
 supportingSource:s=>{
  const key=Object.keys(urls).find(k=>urls[k]===s.final_url);if(!key||['gt','technical'].includes(key))return null;
  const shared=['energy','price_pdf'].includes(key);
  return {model:shared?null:key==='specifications'?'EV3':'Ev3',shared,sourceType:key==='price_pdf'?'price_list_pdf':s.final_url.endsWith('.pdf')?'technical_pdf':'manufacturer_page',
   title:key==='energy'?'Kia Sverige: bränsledeklaration oktober2026':key==='price_pdf'?'Kia Sverige: prislista november2026':'EV3: versionsbundna tillverkaruppgifter',
   country:key==='poland'?'PL':key==='gt_germany'?'DE':'SE',language:key==='poland'?'pl':key==='gt_germany'?'de':'sv',
   sourceName:key==='poland'?'Kia Polen':key==='gt_germany'?'Kia Tyskland':'Kia Sverige'};
 }};
export const buildSpecPlan=(rows,intake,now)=>{
 const p=build(rows,intake,now,policy);assert.equal(p.targets.length,7,'Reconcile all seven EV3 versions together');
 for(const t of p.targets)extras(t.draft,t.expected);return p;
};
export const applySpecPlan=(client,plan,hash,now)=>apply(client,plan,hash,now,policy);
export const intakeFingerprint=intake=>intake.drafts.map(r=>JSON.parse(JSON.stringify(r,
 (key,value)=>['content_hash','source_hash','fetched_at'].includes(key)?undefined:value)));
