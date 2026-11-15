import assert from 'node:assert/strict';
export const ADAPTER='toyota_chr_plus_sweden_pilot_v1';
export const MODEL_ID='d3221898-3c90-4ee4-8e2e-f493b8e84ab6',VERSION='6.HD';
export const urls={model:'https://www.toyota.se/bilar/toyota-c-hr-plus',
 specifications:'https://www.toyota.se/bilar/toyota-c-hr-plus/specifications',
 price_pdf:'https://pdf.toyotasverigebroschyr.com/price-list/nya-toyota-c-hr'};
export const MARKET_URL='https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx';
export const profiles=[
 ['C-HR+ Active FWD 77 kWh 224 hk','dd36efb2-a7b9-4a02-82f8-94ca3f245507','Active','0ad8a6f6-9ed1-461c-839e-3b5dd2a11c3a','FWD',224,18,519900,607,13.4,11,750,'C-HR+ Active 18'],
 ['C-HR+ Active AWD 77 kWh 343 hk','8e1ce48d-02cc-4401-8c02-08c0f2e4d61b','Active','0ad8a6f6-9ed1-461c-839e-3b5dd2a11c3a','AWD',343,18,540900,548,14.4,11,1500,'C-HR+ Active AWD 18'],
 ['C-HR+ Executive AWD 77 kWh 343 hk','faa99752-7181-446b-91d8-74556b0f96b0','Executive','849be735-8d4a-45c8-a6d6-f73d5b47dbe3','AWD',343,20,593900,507,15.5,22,1500,'C-HR+ Executive AWD'],
];
const RANGE='*Räckvidden beror på utrustningsnivå – Active 2WD 18": 607 km, Active 2WD 20": 560 km, Active AWD 18": 548 km, Active AWD 20": 511 km, Executive AWD: 507 km.';
const GROSS='77 kWh-batteri avser bruttobatterikapacitet.';
const BOOT='Toyota C-HR+ är kompakt men rymlig och erbjuder 416 liter bagageutrymme';
export function validateIntake(intake){
 assert.equal(intake.adapter,ADAPTER);
 assert.deepEqual(intake.model,{brand:'Toyota',model:'C-Hr+',normalized_brand:'toyota',normalized_model:'c hr',body_type:'SUV'});
 assert.equal(intake.sources.length,3);
 const sources=new Map(intake.sources.map(s=>[s.final_url,s]));assert.deepEqual([...sources.keys()].sort(),Object.values(urls).sort());
 for(const[key,url]of Object.entries(urls)){
  const s=sources.get(url);assert.equal(s.key,key);assert.equal(s.shared,false);
  for(const[k,v]of Object.entries({source_type:key==='price_pdf'?'price_list_pdf':'manufacturer_page',source_name:'Toyota Sverige',
   source_authority:'manufacturer',country:'SE',language:'sv'}))assert.equal(s[k],v);
 }
 assert.deepEqual(intake.model_evidence,{body_type:{value:'SUV',quote:`${MODEL_ID} | Nya Toyota C-HR+ | SUV 5-d`,source_url:urls.specifications,source_hash:sources.get(urls.specifications).content_hash}});
 assert.equal(intake.drafts.length,3);
 for(const r of intake.drafts){
  const p=profiles.find(p=>p[0]===r.variant_name);assert(p,'Exact registered Swedish C-HR+ version required');
  const[name,id,grade,gid,drive,power,wheel,cash,km,consumption,ac,tow,pdfName]=p;
  assert.equal(r.manufacturer_identity,id);
  const facts={wltp_range_km:km,wltp_consumption_kwh_100km:consumption,battery_kwh:77,dc_charge_kw:150,
   ac_charge_kw:ac,boot_liters:416,tow_kg:tow,seats:5,drivetrain:drive};
  assert.deepEqual(r.facts,facts);assert.deepEqual(Object.keys(r.field_evidence).sort(),Object.keys(facts).sort());
  const cashText=cash.toLocaleString('en-US').replaceAll(',',' ');
  const pricePattern=new RegExp('^'+pdfName.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\s+Från:\\s+'+cashText+' kr\\s+Easy Billån från:\\s+[0-9 ]+ kr/mån\\s+Elförbrukning \\(WLTP\\):\\s+'+String(consumption).replace('.','\\.')+' kWh/100km$');
  assert(pricePattern.test(r.price_evidence.quote),'Exact cash panel, not a monthly payment or another grade');
  for(const[field,value]of Object.entries(facts)){
   const e=r.field_evidence[field];let url=urls.price_pdf,page=grade==='Active'?3:4,quote=r.price_evidence.quote;
   if(field==='wltp_range_km'){url=urls.model;page=null;quote=RANGE;}
   else if(field==='battery_kwh'){url=urls.model;page=null;quote=GROSS;}
   else if(field==='boot_liters'){url=urls.model;page=null;quote=BOOT;}
   else if(['ac_charge_kw','dc_charge_kw'].includes(field))quote=`Ombordladdare ${ac} kW AC | snabbladdning 150 kW DC`;
   else if(field==='tow_kg'){page=6;quote='Elmotor 224 hk, batteri 77 kWh | Elmotor 343 hk, batteri 77 kWh | Dragvikt bromsat släp (kg) 750 1500';}
   else if(field==='seats'){page=7;quote='Elmotor 224 hk, batteri 77 kWh | Elmotor 343 hk, batteri 77 kWh | Antal platser 5 5';}
   else if(field==='drivetrain'){
    if(grade==='Executive')quote=pdfName;
    else{url=urls.specifications;page=null;quote=`${MODEL_ID} | ${VERSION} | ${grade} | ${id} | ${drive==='FWD'?'Framhjulsdrift':'AWD'}`;}
   }
   assert.equal(e.value,value);assert.equal(e.variant_name,name);
   assert.equal(e.column_header,`Toyota C-HR+ | ${grade} | ${drive} | 77 kWh brutto | ${power} hk | ${wheel} tum`);
   for(const[k,v]of Object.entries({manufacturer_variant_id:id,manufacturer_model_id:MODEL_ID,config_version:VERSION,grade_id:gid,
    source_url:url,source_hash:sources.get(url).content_hash,quote,page}))assert.equal(e[k],v);
  }
  for(const[k,v]of Object.entries({value:cash,price_type:'list_price',price_valid_until:null,source_url:urls.price_pdf,
   source_hash:sources.get(urls.price_pdf).content_hash,page:grade==='Active'?3:4}))assert.equal(r.price_evidence[k],v);
 }
 const m=intake.market;assert.equal(m.source.final_url,MARKET_URL);assert.equal(m.sheet,'Elbil ranking');
 for(const[k,v]of Object.entries({brand_raw:'TOYOTA',model_raw:'C-HR+',normalized_brand:'toyota',normalized_model:'c hr',fuel_type_raw:'EL',needs_mapping:false,last_seen_month:'2026-10-01'}))assert.equal(m.row[k],v);
 assert(Number.isSafeInteger(m.row.registrations_last_month)&&m.row.registrations_last_month>0&&m.row.registrations_last_month<=m.row.registrations_ytd);
 assert.equal(m.row.source_url,MARKET_URL);assert.equal(m.row.source_name,'Mobility Sweden');assert(intake.source_decisions.length>=8);
}
export const policy={adapter:ADAPTER,validateIntake,primaryUrl:urls.specifications,imageKey:'toyota|c hr',
 imageHash:'39c5e82ee449b0b4424d5f8ddda24922ff80eadba6a54a90de9348d9e3788e1a',aliasRule:'mobility_sweden_exact_raw_name',maxVariants:3};
