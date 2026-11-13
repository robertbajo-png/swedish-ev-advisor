import assert from 'node:assert/strict';
import {applySpecPlan as apply,buildSpecPlan as build,specPlanHash,TECHNICAL_FIELDS} from './kia_spec_sync.mjs';
export {specPlanHash};
export const ADAPTER='ford_explorer_sweden_my2725_v1';
const premium='https://www.ford.se/bilar/personbilar-och-suver/explorer/explorer-premium-edition';
const pdf='https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/fordsesite/cardocuments/explorer/prislista-explorer-premium-edition.pdf';
const offers='https://www.ford.se/erbjudanden/privatperson';
const cargo='https://www.ford.dk/koeb/kampagner/explorer-og-capri';
const scopes=[['Explorer RWD 77 kWh','RWD',79,572,15.5,185,2000,626000,549000,602,77],
 ['Explorer AWD 79 kWh','AWD',77,519,17.3,175,2200,686000,569000,556,79]];
const name=s=>`Explorer Premium Edition ${s[1]} ${s[2]} kWh MY27.25`;
const scope=r=>scopes.find(s=>[s[0],name(s)].includes(r.variant_name));
const number=v=>Number(v.replaceAll(' ','').replace(',','.'));
const priceFields=['price_sek','price_type','price_valid_until','price_source_url','price_source_hash',
 'price_source_quote','price_verified_at','price_source_name','price_refresh_batch_id','variant_name'];
export function validateSpecDraft(r,now=new Date()){
 assert.equal(r.adapter,ADAPTER);assert.equal(r.brand,'Ford');assert.equal(r.model,'Explorer');
 const s=scope(r);assert(s,'Two exact existing Ford profiles only');
 const [,drive,battery,range,consumption,dc,tow,reference,cash]=s;
 assert.equal(r.replacement_variant_name,name(s));
 assert.equal(r.source_resolution,'owner_2026_11_13_current_exact_version_replacement');
 assert(r.extraction_confidence>=0.92&&r.extraction_confidence<=1);
 assert.equal(r.source.final_url,pdf);assert.equal(r.supporting_sources.length,3);
 const sources=new Map([r.source,...r.supporting_sources].map(s=>[s.final_url,s]));
 assert.deepEqual([...sources.keys()].sort(),[pdf,premium,offers,cargo].sort());
 for(const source of sources.values()){
  assert.equal(source.status,'reachable');assert.equal(source.http_status,200);
  assert.match(source.content_hash,/^[a-f0-9]{64}$/);
  const age=now-Date.parse(source.fetched_at);assert(Number.isFinite(age)&&age>=-60000&&age<=900000);
 }
 assert.deepEqual(r.facts,{wltp_range_km:range,wltp_consumption_kwh_100km:consumption,battery_kwh:battery,
  drivetrain:drive,ac_charge_kw:11,dc_charge_kw:dc,tow_kg:tow,seats:5,boot_liters:472});
 assert.deepEqual(Object.keys(r.field_evidence).sort(),[...TECHNICAL_FIELDS,'ac_charge_kw'].sort());
 const rowFields=['wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','drivetrain'];
 const header=`Explorer ${drive}, Long Range (${battery} kWh) Premium Edition`;
 for(const [field,value]of Object.entries(r.facts)){
  const p=r.field_evidence[field];assert.equal(p.value,value);assert.equal(p.variant_name,r.variant_name);
  assert.equal(p.column_header,header);assert.equal(sources.get(p.source_url)?.content_hash,p.source_hash);
  if(rowFields.includes(field)){
   assert.equal(p.source_url,pdf);assert.equal(p.page,1);assert.equal(p.scope,'exact_swedish_my2725_premium_row');
   assert(p.quote.startsWith(header+' '+(drive==='RWD'?'286 hk (210 kW)':'340 hk (250 kW)')));
   const m=/ (\d+) ([0-9,]+) 360 kr 2 [0-9 ]+ kr ([0-9 ]+) kr ([0-9 ]+) kr$/.exec(p.quote);assert(m);
   assert.deepEqual([number(m[1]),number(m[2]),number(m[3]),number(m[4])],[range,consumption,reference,cash]);
  }else if(field==='boot_liters'){
   assert.equal(p.source_url,cargo);assert.equal(p.page,null);assert.equal(p.scope,'european_explorer_named_cargo_table_not_capri');
   assert.equal(p.quote,'Dimensioner Explorer® Capri® Bagagerum 472 liter 572 liter Bagagerum med sæder lagt ned 1.460 liter 1.510 liter');
  }else if(field==='seats'){
   assert.equal(p.source_url,premium);assert.equal(p.page,null);assert.equal(p.scope,'current_swedish_electric_explorer');assert.equal(p.quote,'5 sittplatser');
  }else{
   assert.equal(p.source_url,pdf);assert.equal(p.page,2);
   const expected={ac_charge_kw:['11 kW 3-fasladdare (Ombordladdare)','current_my2725_onboard_ac'],
    dc_charge_kw:[`Upp till ${dc} kW DC-snabbladdning (${drive})`,'current_swedish_my2725_peak_dc'],
    tow_kg:['Dragvikt: LR RWD 2000 kg / LR AWD 2200 kg (MY27.25)','current_swedish_my2725_braked_towing']}[field];
   assert.deepEqual([p.quote,p.scope],expected);
  }
 }
 assert.deepEqual(r.model_facts,{body_type:'SUV'});const body=r.model_field_evidence.body_type;
 assert.equal(body.value,'SUV');assert.equal(body.source_url,premium);assert.equal(body.source_hash,sources.get(premium).content_hash);
 assert.equal(body.quote,'Explorer Premium Edition | Car.Tags | Personbilar SUV | El');
 const p=r.price_evidence;assert.equal(p.value,cash);assert.equal(p.reference_price,reference);
 assert.equal(p.price_type,'campaign_price');assert.equal(p.price_valid_until,'2026-12-30');
 assert(now.toISOString().slice(0,10)<='2026-12-30');
 assert.equal(p.source_url,pdf);assert.equal(p.source_hash,r.source.content_hash);
 assert.equal(p.quote,'Rek. pris / Rek. Edition pris | '+r.field_evidence.battery_kwh.quote);
 assert.equal(p.classification,'swedish_premium_edition_offer_not_reference_or_leasing');
 assert.equal(p.campaign_source_url,drive==='AWD'?offers:premium);
 assert.equal(p.campaign_source_hash,sources.get(p.campaign_source_url).content_hash);
 if(drive==='AWD'){
  assert(p.campaign_quote.startsWith('Explorer Premium Edition AWD PRIVATLEASING Från 5 595 kr/mån* KAMPANJPRIS Från 569 000 kr '));
  assert(p.campaign_quote.endsWith('ERBJUDANDET GILTIGT TILL 2026-12-30'));
  assert(now.toISOString().slice(0,10)<='2026-12-30');
 }else assert.equal(p.campaign_quote,'Erbjudandet giltligt till och med 30 december 2026. | Explorer Premium Edition finns även som RWD från 549 000 kr.');
 assert.deepEqual(r.held_fields,{});assert(r.source_decisions.length>=8);
 return r;
}
const eligible=(old,r)=>{
 const s=scope(r);assert(s);
 assert([s[0],name(s)].includes(old.variant_name));
 assert(old.price_sek==null||Number(old.price_sek)===s[8]&&old.price_type==='campaign_price');
 return s;
};
const extras=(r,old)=>{
 eligible(old,r);
 return {variant_name:r.replacement_variant_name,price_sek:r.price_evidence.value,price_type:'campaign_price',
  price_valid_until:r.price_evidence.price_valid_until,price_source_url:pdf,price_source_hash:r.source.content_hash,
  price_source_quote:r.price_evidence.quote,price_source_name:'Ford Sverige',price_verified_at:new Date(r.source.fetched_at).toISOString(),
  price_refresh_batch_id:specPlanHash({adapter:ADAPTER,evidence:r.price_evidence,verified:r.source.fetched_at})};
};
const policy={adapter:ADAPTER,validate:validateSpecDraft,sourceType:'technical_pdf',sourceName:'Ford Sverige',
 sourceTitle:()=> 'Explorer Premium Edition MY27.25, svensk prislista 8 / 2026',lockKey:7240016,
 extraFields:['ac_charge_kw'],allowedBodyTypes:['SUV'],modelFacts:r=>r.model_facts,
 canonicalFields:priceFields,canonicalExtras:extras,replacementVariantName:(_old,r)=>r.replacement_variant_name,
 priceReplacement:(old,r)=>(eligible(old,r),r.price_evidence.value),
 priceRefresh:(old,r)=>(eligible(old,r),true),
 resolveConflict:(field,prior,_next,old,r)=>{
  const s=eligible(old,r);
  return old.variant_name===s[0]&&['wltp_range_km','battery_kwh'].includes(field)&&Number(prior)===s[field==='wltp_range_km'?9:10];
 },
 supportingSource:s=>[premium,offers,cargo].includes(s.final_url)?{model:'Explorer',shared:false,sourceType:'manufacturer_page',
  title:s.final_url===cargo?'Explorer: europeisk bagagevolym, Ford Danmark':'Explorer Premium Edition: svenska modell- och erbjudandeuppgifter',
  country:s.final_url===cargo?'DK':'SE',language:s.final_url===cargo?'da':'sv',
  sourceName:s.final_url===cargo?'Ford Danmark':'Ford Sverige'}:null};
export const buildSpecPlan=(rows,intake,now)=>{
 const p=build(rows,intake,now,policy);assert.equal(p.targets.length,2,'Reconcile both current Explorer profiles together');
 for(const t of p.targets)extras(t.draft,t.expected);return p;
};
export const applySpecPlan=(client,plan,hash,now)=>apply(client,plan,hash,now,policy);
export const intakeFingerprint=intake=>intake.drafts.map(r=>JSON.parse(JSON.stringify(r,
 (key,value)=>['content_hash','source_hash','campaign_source_hash','fetched_at'].includes(key)?undefined:value)));
