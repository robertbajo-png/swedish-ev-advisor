import assert from 'node:assert/strict';
export const ADAPTER='kia_ev2_sweden_pilot_v1';
const base='https://www.kia.com';
export const urls={technical:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev2/kia-sweden-ev2-specification.pdf',
 model:base+'/se/nya-bilar/ev2/upptack/',specifications:base+'/se/nya-bilar/ev2/specifikationer/',
 price_pdf:base+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf'};
export const MARKET_URL='https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx';
export const profiles=[
 ['EV2 FWD 5-sits','6NW5ZFZ7Z-TX2',331900,42.2,317,15.1,16,'Elmotor FWD (El , Elektrisk);','107,8 kW / 146,5 hk'],
 ['EV2 FWD Long Range 5-sits','6NW5ZFZ7Z-TX2_V00',381000,61,453,14.9,16,'Elmotor FWD (El , Elektrisk); 99,5 KW (135 hk)','99,5 kW / 135 hk'],
 ['EV2 GT Line FWD Long Range 5-sits','6NW5ZFZ7Z-LX1',459900,61,413,16.3,19,'Elmotor FWD (El , Elektrisk); 99,5 KW (135 hk)','99,5 kW / 135 hk'],
];
const quotes={battery_kwh:'Batterikapacitet (kWh) 42,2 61',ac_charge_kw:'Bilens laddare (On Board Charger) (kW) 10,5',
 dc_charge_kw:'DC snabbladdning max kW 150 150',
 wltp_range_km:'Max räckvidd (km) enligt WLTP (Upp till) SR = 317 (16") & 308 (18") LR = 453 (16"), 439 (18") & 413 (19")',
 wltp_consumption_kwh_100km:'FÖRBRUKNING Blandad, kWh/100km enligt WLTP SR = 15,1 (16") & 15,5 (18") LR =14,9 (16"), 15,2 (18") & 16,3 (19")',
 boot_liters:'BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv (ej basversionen) 5 säten = 362 / 1201 / 15',
 tow_kg:'Max släpvagnsvikt, bromsat släp 750 750'};
export function validateIntake(intake,now=new Date()){
 assert.equal(intake.adapter,ADAPTER);
 assert.deepEqual(intake.model,{brand:'Kia',model:'Ev2',normalized_brand:'kia',normalized_model:'ev2',body_type:'SUV'});
 assert.equal(intake.sources.length,4);
 const sources=new Map(intake.sources.map(s=>[s.final_url,s]));
 assert.deepEqual([...sources.keys()].sort(),Object.values(urls).sort());
 for(const[key,url]of Object.entries(urls)){
  const s=sources.get(url);assert.equal(s.key,key);assert.equal(s.shared,key==='price_pdf');
  assert.equal(s.source_type,key==='technical'?'technical_pdf':key==='price_pdf'?'price_list_pdf':'manufacturer_page');
  assert.equal(s.source_name,'Kia Sverige');assert.equal(s.source_authority,'manufacturer');assert.equal(s.country,'SE');assert.equal(s.language,'sv');
 }
 assert.deepEqual(intake.model_evidence,{body_type:{value:'SUV',quote:'en självsäker och smart SUV',source_url:urls.model,source_hash:sources.get(urls.model).content_hash}});
 assert.equal(intake.drafts.length,3);
 for(const r of intake.drafts){
  const p=profiles.find(p=>p[0]===r.variant_name);assert(p,'Only three selected five-seat pilot profiles');
  const[name,engine,cash,battery,km,consumption,wheel,engineName,power]=p;
  assert.equal(r.manufacturer_identity,engine);
  const facts={wltp_range_km:km,wltp_consumption_kwh_100km:consumption,battery_kwh:battery,dc_charge_kw:150,
   ac_charge_kw:10.5,boot_liters:362,tow_kg:750,seats:5,drivetrain:'FWD'};
  assert.deepEqual(r.facts,facts);assert.deepEqual(Object.keys(r.field_evidence).sort(),Object.keys(facts).sort());
  for(const[field,value]of Object.entries(facts)){
   const e=r.field_evidence[field],json=['seats','drivetrain'].includes(field);
   assert.equal(e.value,value);assert.equal(e.variant_name,name);
   assert.equal(e.column_header,`${name} | ${engine} | ${wheel} tum | 5 sittplatser`);
   assert.equal(e.source_url,json?urls.specifications:urls.technical);
   assert.equal(e.source_hash,sources.get(e.source_url).content_hash);assert.equal(e.page,json?null:3);
   assert.equal(e.quote,json?`${engine} | ${engineName} | number of seats 5 | ${power}`:quotes[field]);
  }
  const pe=r.price_evidence;
  assert.equal(pe.value,cash);assert.equal(pe.price_type,'list_price');assert.equal(pe.price_valid_until,'2026-11-30');
  assert.equal(pe.source_url,urls.price_pdf);assert.equal(pe.source_hash,sources.get(urls.price_pdf).content_hash);assert.equal(pe.page,1);
  const priceName=wheel===19?'EV2 GT Line Long Range':battery===61?'EV2 Long Range':'EV2';
  assert(new RegExp('^'+priceName+' '+cash.toLocaleString('en-US')+' kr(?: [0-9,]+ kr)?$').test(pe.quote));
 }
 assert(now.toISOString().slice(0,10)>='2026-11-01'&&now.toISOString().slice(0,10)<='2026-11-30');
 const m=intake.market;assert.equal(m.source.final_url,MARKET_URL);assert.equal(m.sheet,'Elbil ranking');
 assert.match(m.cells,/^D([0-9]+),F\1,M\1$/);
 for(const[k,v]of Object.entries({brand_raw:'KIA',model_raw:'EV2',normalized_brand:'kia',normalized_model:'ev2',fuel_type_raw:'EL',needs_mapping:false,last_seen_month:'2026-10-01'}))assert.equal(m.row[k],v);
 assert(Number.isSafeInteger(m.row.registrations_last_month)&&m.row.registrations_last_month>0&&m.row.registrations_last_month<=m.row.registrations_ytd);
 assert.equal(m.row.source_url,MARKET_URL);assert.equal(m.row.source_name,'Mobility Sweden');
 assert(intake.source_decisions.length>=6);return intake;
}
export const policy={adapter:ADAPTER,validateIntake,primaryUrl:urls.technical,imageKey:'kia|ev2',
 imageHash:'42a663c6e0ce765ebc59d1865699e61c99909e4a1b3fe6f7b7f20204e63392d9',
 aliasRule:'mobility_sweden_exact_raw_name',maxVariants:3};
