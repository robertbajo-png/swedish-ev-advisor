import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {buildReplacementPlan,applyReplacementPlan,replacementPlanHash} from './current_variant_sync.mjs';
import {POLICY,remainingRules,validateRemainingProfile} from './remaining_variant_policy.mjs';

const now=new Date('2026-10-27T20:00:00Z');
const blank={price_valid_until:null,wltp_range_km:null,wltp_consumption_kwh_100km:null,battery_kwh:null,
  dc_charge_kw:null,ac_charge_kw:null,boot_liters:null,tow_kg:null,seats:null,drivetrain:null};
function profile(brand,model,name,url,adapter,type,quote,extra={}) {
  const row={...blank,brand,model,variant_name:name,source_url:url,source_hash:'a'.repeat(64),source_type:type,
    source_authority:'manufacturer',source_name:brand+' Sverige',price_type:'list_price',price_sek:599000,
    fetched_at:now.toISOString(),source_quote:quote,extraction_confidence:0.99,...extra};
  row.extraction_payload={policy:POLICY,adapter,field_evidence:{price_sek:{quote,variant:name,source_url:url,source_hash:row.source_hash}}};
  return row;
}
const rows=[];
for(const [motor,trim,column,y,left,right]of [
  ['60','Selection',0,148,390,453.5],['60','Sportline',1,148,453.5,510.2],
  ['85','Selection',0,168,390,453.5],['85','Sportline',1,168,453.5,510.2],
  ['85x','Selection',0,188,390,453.5],['85x','Sportline',1,188,453.5,510.2],['RS','RS',2,208,510.2,565]]) {
  const name=motor+(motor==='RS'?'':' '+trim)+' Explore Edition';
  const row=profile('Skoda','Elroq',name,'https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb',
    'skoda_elroq_explore_grid_v1','price_list_pdf','Škoda Elroq Explore Edition | '+motor+' | '+trim+' | 599 000 kr | Gäller tom 2026-12-15',
    {price_type:'campaign_price',price_valid_until:'2026-12-15'});
  row.extraction_payload.price_cell={page:1,motor,trim,column,text:'599 000 kr',bbox:[left,y,right,y+12]};
  row.extraction_payload.field_evidence.price_valid_until={source_url:row.source_url,source_hash:row.source_hash,quote:'Gäller tom 2026-12-15',value:'2026-12-15'};
  rows.push(row);
}
rows.push(profile('Cupra','Born','Born VZ','https://www.cupraofficial.se/bilar/born','cupra_born_vz_html_v1','manufacturer_model_page','Born VZ | Från 599.000 kr'));
rows.at(-1).extraction_payload.context_hash='b'.repeat(64);
for(const [index,name]of ['Takumi','Homura Plus','Takumi Plus'].entries()) {
  const row=profile('Mazda','6E',name+' MY2027','https://www.mazda.se/modeller/mazda-6e/','mazda6e_my27_embedded_grades_v1',
    'manufacturer_model_page','2027 Mazda6e | '+name+' | Från 599 000 kr');
  row.extraction_payload.source_pointer='/components/2/submodules/8/props/cards/'+index;rows.push(row);
  row.extraction_payload.context_hash='b'.repeat(64);
}
rows.push(profile('Volkswagen','Id.3','ID.3 Neo Trend','https://www.volkswagen.se/sv/bygg-din-bil.html/__app/30355.app',
  'vw_id3_neo_trend_config_v1','manufacturer_configurator','ID.3 Neo | Trend | Pris inkl. moms 599 000 kr'));
rows.at(-1).extraction_payload.context_hash='b'.repeat(64);rows.at(-1).extraction_payload.battery_options=1;
for(const [drive,battery,km]of [['RWD',77,602],['AWD',79,556]]) {
  const quote='Men motormässigt då? Ja, en laddning räcker – enligt WLTP – 602 kilometer vid blandad körning för den bakhjulsdrivna varianten med ett batteripaket på 77 kilowattimmar. Den fyrhjulsdrivna versionen har ett batteri på 79 kilowattimmar och en räckvidd på 556 kilometer';
  const row=profile('Ford','Explorer',`Explorer ${drive} ${battery} kWh`,'https://www.ford.se/bilar/personbilar-och-suver/explorer',
    'ford_explorer_exact_drive_range_v1','manufacturer_model_page',quote,{source_authority:'importer',price_sek:null,price_type:null,
      wltp_range_km:km,battery_kwh:battery,drivetrain:drive});
  row.extraction_payload.context_hash='b'.repeat(64);
  row.extraction_payload.field_evidence=Object.fromEntries(['wltp_range_km','battery_kwh','drivetrain'].map(field=>[field,
    {quote,variant:row.variant_name,source_url:row.source_url,source_hash:row.source_hash,value:row[field]}]));rows.push(row);
}
const ford=rows.at(-1);
const bmw=profile('BMW','i4','i4 eDrive40 M Sport Business Edition (lagerbil FW37556)',
  'https://hitta.bmw.se/r/G26E-i4/i4-eDrive40-WBY61HD030FW37556','exact_new_stock_cash_v1','manufacturer_configurator',
  'i4 eDrive40 M Sport Business Edition (lagerbil FW37556) | Kontantpris 599 000 kr',{price_type:'dealer_offer',price_valid_until:'2026-12-31',authorization_evidence_url:null});
bmw.extraction_payload.context_hash='b'.repeat(64);
bmw.extraction_payload.stock_car={brand:{name:'BMW'},name:'i4 eDrive40',vehicleIdentificationNumber:'WBY61HD030FW37556',
  vehicleEngine:{fuelType:'Elbil'},offers:[{businessFunction:'http://purl.org/goodrelations/v1#Sell',seller:{name:'Bilia Nacka'},
    price:599000,priceCurrency:'SEK',itemCondition:'http://schema.org/NewCondition',availability:'http://schema.org/InStock',priceValidUntil:'2026-12-31'}]};
rows.push(bmw);
const auth='https://www.volvocars.com/se/l/studios/stockholm/';
const volvo=profile('Volvo','Es90','ES90 Single Motor Extended Range Ultra MY2026 (lagerbil JWR04C)',
  'https://www.volvocarretail.se/bilar-i-lager/nya/volvo/es90/single-motor-extended-range-jwr04c','exact_new_stock_cash_v1','authorized_dealer_stock_page',
  'ES90 Single Motor Extended Range Ultra MY2026 (lagerbil JWR04C) | Kontantpris 599 000 kr',
  {price_type:'dealer_offer',source_authority:'authorized_dealer',source_name:'Volvo Car Retail',authorization_evidence_url:auth});
volvo.extraction_payload.context_hash='b'.repeat(64);
volvo.extraction_payload.authorization_review={url:auth,reviewed_on:'2026-10-27',method:'primary_manufacturer_page_review',
  dealer:'Volvo Car Retail',quote:'Du kan också få rådgivning och beställa din bil direkt i studion.'};
volvo.extraction_payload.stock_car={brand:{name:'Volvo'},name:'Volvo ES90',model:'ES90 Single Motor Extended Range',
  vehicleModelDate:2026,vehicleEngine:{fuelType:'El'},vehicleConfiguration:'SM Ext Ultra | Privatleasing 9490kr/mån',
  mileageFromOdometer:{'@type':'QuantitativeValue',unitCode:'KMT',value:0},itemCondition:'https://schema.org/NewCondition',
  offers:{price:599000,priceCurrency:'SEK',availability:'https://schema.org/InStock',seller:{name:'Volvo Car Retail'}}};
rows.push(volvo);
const ex30=structuredClone(volvo);
ex30.model='Ex30';ex30.variant_name='EX30 P5 Long Range Core MY2027 (lagerbil)';
ex30.source_url='https://www.volvocarretail.se/bilar-i-lager/nya/volvo/ex30/p5-long-range-01a0f17196c07c0eac58aa44aeea8ae4';
ex30.source_quote=ex30.variant_name+' | Kontantpris 599 000 kr';
ex30.extraction_payload.stock_car={...ex30.extraction_payload.stock_car,name:'Volvo EX30',model:'EX30 P5 Long Range',vehicleModelDate:2027,vehicleConfiguration:'Core'};
ex30.extraction_payload.field_evidence.price_sek={quote:ex30.source_quote,variant:ex30.variant_name,source_url:ex30.source_url,source_hash:ex30.source_hash};
rows.push(ex30);
for(const [header,battery,range]of [['Privilege AWD',100,545],['Long Range RWD',100,627],['Core RWD',75,482]]) {
  const row=profile('Zeekr','7X',header+' '+battery+' kWh','https://www.zeekr.eu/sv-se/models/7x',
    'zeekr7x_exact_spec_columns_v1','manufacturer_specs_page','',{price_sek:null,price_type:null,battery_kwh:battery,
      wltp_range_km:range,tow_kg:2000,boot_liters:539,drivetrain:header.endsWith('AWD')?'AWD':'RWD'});
  row.extraction_payload.context_hash='b'.repeat(64);
  row.extraction_payload.column_evidence=Object.fromEntries([
    ['battery_kwh','Batteri',battery+' kWh'],['wltp_range_km','Räckvidd, upp till',range+' Km'],['tow_kg','Dragvikt','2000 Kg'],
    ['boot_liters','Lastutrymme','539L VDA'],['drivetrain','Motor',row.drivetrain==='AWD'?'Dubbel':'Enkel']
  ].map(([field,label,text])=>[field,{column:header,label,text}]));
  row.source_quote=[header,...Object.values(row.extraction_payload.column_evidence).map(v=>v.label+' '+v.text)].join(' | ');
  row.extraction_payload.field_evidence=Object.fromEntries(Object.keys(row.extraction_payload.column_evidence).map(field=>[field,
    {quote:row.source_quote,variant:row.variant_name,value:row[field],source_url:row.source_url,source_hash:row.source_hash}]));rows.push(row);
}
for(const [brand,model,url,name,exact,version,reg]of [
  ['Audi','A6 E-Tron','https://lagerbilar.vwgroup.se/audi/RRR07B','A6 Sportback e-tron performance S-line 270 kW MY2027 (lagerbil RRR07B)','A6 Sportback e-tron','performance S-line 270 kW','RRR07B'],
  ['Volkswagen','Id.4','https://lagerbilar.vwgroup.se/volkswagen/BSJ09L','ID.4 Pro 4MOTION 77 kWh MY2027 (lagerbil BSJ09L)','ID.4','PRO 4MOTION 220 KW/ 299 HK 77 KWH BATTERI,','BSJ09L']]) {
  const row=profile(brand,model,name,url,'vwg_exact_new_stock_v1','manufacturer_configurator',name+' | Pris 599 000 kr | Administrationskostnad på 950:- tillkommer',
    {price_sek:599950,price_type:'dealer_offer',source_authority:'importer',source_name:'Volkswagen Group Sverige'});
  row.extraction_payload.context_hash='b'.repeat(64);row.extraction_payload.source_pointer='/props/pageProps/car';
  row.extraction_payload.mandatory_fee_sek=950;row.extraction_payload.fee_quote='Administrationskostnad på 950:- tillkommer';
  row.extraction_payload.price_calculation='advertised_cash_plus_mandatory_fee';
  row.extraction_payload.stock_row={brand,model:exact,version,regNumber:reg,modelYear:2027,used:false,mileage:0,unPublished:false,
    firstRegistrationDate:null,fuelType:'El',cash_price_sek:599000};rows.push(row);
}
const bilia=profile('Audi','Q6 E-Tron','Q6 e-tron quattro SUV 315 kW MY2027 (lagerbil JCE98Y)',
  'https://www.bilia.se/bilar/sok-bil/audi/q6-e-tron/jce98y/','exact_new_stock_cash_v1','authorized_dealer_stock_page',
  'Q6 e-tron quattro SUV 315 kW MY2027 (lagerbil JCE98Y) | Kontantpris 599 000 kr',
  {price_type:'dealer_offer',source_authority:'authorized_dealer',source_name:'Bilia Haninge Audi',authorization_evidence_url:'https://lagerbilar.vwgroup.se/audi'});
bilia.extraction_payload.context_hash='b'.repeat(64);
bilia.extraction_payload.stock_car={brand:{name:'Audi'},name:'Audi Q6 e-tron quattro',model:'Q6 e-tron',vehicleModelDate:2027,
  vehicleIdentificationNumber:'WAUZZZGF3VA023430',bodyType:'SUV',vehicleEngine:{fuelType:'El'},
  mileageFromOdometer:{'@type':'QuantitativeValue',unitCode:'KMT',value:0},itemCondition:'https://schema.org/NewCondition',
  offers:{price:599000,priceCurrency:'SEK',availability:'https://schema.org/InStock',seller:{'@id':'https://www.bilia.se/anlaggningar/haninge-audi#dealer'}}};
bilia.extraction_payload.authorization_review={url:'https://lagerbilar.vwgroup.se/audi',source_hash:'a'.repeat(64),fetched_at:now.toISOString(),
  method:'official_importer_network',dealer:'Bilia Haninge Audi',source_pointer:'/props/pageProps/carsWithFilter/filter/retailers/29/value',
  network_entry:{uniqueId:'40584A',name:'Bilia Haninge Audi',brandCode:'A',locationIds:[]}};
rows.push(bilia);
for(const [id,label,title]of [
  ['19043773','CLA 200 Advanced Edition MY2027 (lagerbil)','Mercedes-Benz CLA 200 Advanced Edition 3.95% RÄNTA'],
  ['19003980','CLA 250+ Advanced Edition MY2027 (lagerbil)','Mercedes-Benz CLA 250+ Advanced Edition 3.95% RÄNTA'],
  ['19004063','CLA 350 4MATIC Advanced Edition MY2027 (lagerbil)','Mercedes-Benz CLA 350 4MATIC Advanced Edition 3.95% RÄNTA']]) {
  const stock={car_id:id,name:title,noveltyType:'new_car',year:2027,mileage:0,is_leasing:0,brand_name:'Mercedes-Benz',model_name:'CLA',
    body_type_name:'Sedan',fuel_type_name:'El',location_name:'Höglunds Bil',price:599000,car_exkl_moms:479200,sale_price:'',sale_car_exkl_moms:''};
  const auth='https://www.hoglundsbil.mercedes-benz.se/passengercars/startpage.html';
  const row=profile('Mercedes-Benz','Cla',label,'https://www.hoglundsbil.se/bilar?sort=0','hoglund_exact_new_cla_stock_v1',
    'authorized_dealer_stock_page',JSON.stringify(stock),{price_type:'dealer_offer',source_authority:'authorized_dealer',source_name:'Höglunds Bil',authorization_evidence_url:auth});
  row.extraction_payload.stock_row=stock;row.extraction_payload.context_hash='b'.repeat(64);row.extraction_payload.source_pointer='/props/pageProps/carsList/4';
  row.extraction_payload.authorization_review={url:auth,reviewed_on:'2026-10-27',method:'primary_manufacturer_page_review',
    manufacturer_label:'Höglunds Bil | Mercedes-Benz Agent',supporting_url:'https://www.hoglundsbil.se/anlaggningar/mobility-motors-norrtalje',
    supporting_hash:'a'.repeat(64),fetched_at:now.toISOString(),quote:'Vi är en fullserviceanläggning som är auktoriserad återförsäljare av Mercedes och Mazda.'};
  rows.push(row);
}
for(const row of rows)validateRemainingProfile(row,now);
rows[0].extraction_confidence=0.95;
for(const mutate of [r=>r.price_type='list_price',r=>r.price_valid_until='2026-01-01',r=>r.wltp_range_km=567,
  r=>r.price_sek=600000,r=>r.extraction_confidence=0.5,r=>r.extraction_payload.price_cell.column=2,
  r=>r.source_url='https://comparison.invalid/',r=>r.price_valid_until='2026-99-99']) {
  const bad=structuredClone(rows[0]);mutate(bad);assert.throws(()=>validateRemainingProfile(bad,now));
}
for(const mutate of [r=>r.price_sek=549000,r=>r.dc_charge_kw=185,r=>r.wltp_range_km=602,
  r=>r.source_quote=r.source_quote.replace('556 kilometer','602 kilometer'),r=>delete r.extraction_payload.field_evidence.battery_kwh]) {
  const bad=structuredClone(ford);mutate(bad);assert.throws(()=>validateRemainingProfile(bad,now));
}
for(const mutate of [r=>r.authorization_evidence_url=null,r=>r.extraction_payload.stock_car.mileageFromOdometer.value=500,
  r=>r.extraction_payload.stock_car.itemCondition='https://schema.org/UsedCondition',r=>r.extraction_payload.stock_car.offers.priceCurrency='EUR',
  r=>r.extraction_payload.stock_car.offers.availability='https://schema.org/SoldOut',r=>r.price_type='list_price',
  r=>r.extraction_payload.authorization_review.reviewed_on='2026-01-01']) {
  const bad=structuredClone(volvo);mutate(bad);assert.throws(()=>validateRemainingProfile(bad,now));
}
for(const mutate of [r=>r.extraction_payload.authorization_review.network_entry.uniqueId='UNKNOWN',
  r=>r.extraction_payload.authorization_review.fetched_at='2026-01-01T00:00:00Z',r=>r.source_authority='manufacturer']) {
  const bad=structuredClone(bilia);mutate(bad);assert.throws(()=>validateRemainingProfile(bad,now));
}
const db=new PGlite();
try {
  await db.exec('create role anon;create role authenticated;create role service_role bypassrls;grant usage on schema public to anon,authenticated,service_role');
  await db.exec((await readFile(new URL('../database/schema.sql',import.meta.url),'utf8')).replace('create extension if not exists pgcrypto;',''));
  const groups=[];
  for(const [identity,retire]of Object.entries(remainingRules.retired)) {
    const [brand,model]=identity.split('|');
    const id=(await db.query('insert into canonical_models(brand,model,normalized_brand,normalized_model,market_seen) values($1,$2,$3,$4,true) returning id',
      [brand,model,brand.toLowerCase(),model.toLowerCase()])).rows[0].id;
    for(const name of retire)await db.query(`insert into canonical_model_variants(canonical_model_id,variant_name,price_sek,wltp_range_km,validation_status)
      values($1,$2,500000,600,'published')`,[id,name]);
    const group={brand,model,retire,profiles:rows.filter(row=>row.brand===brand&&row.model===model)};
    if(brand==='Toyota') {
      await db.query(`insert into canonical_model_variants(canonical_model_id,variant_name,price_sek,wltp_range_km,battery_kwh,drivetrain,validation_status)
        values($1,'Active FWD 57.7 kWh 167 hk',479900,444,57.7,'FWD','published')`,[id]);
      group.retention_evidence={source_url:'https://www.toyota.se/bilar/bz4x/specifications',source_hash:'a'.repeat(64),
        context_hash:'b'.repeat(64),fetched_at:now.toISOString(),variant_name:'Active FWD 57.7 kWh 167 hk',
        price_sek:479900,wltp_range_km:444,battery_kwh:57.7,drivetrain:'FWD',source_quote:'Elmotor 167 hk, batteri 57,7 kWh | Active | 479900'};
    }
    groups.push(group);
  }
  const variants=(await db.query('select v.*,m.brand,m.model from canonical_model_variants v join canonical_models m on m.id=v.canonical_model_id order by v.id')).rows;
  const plan=buildReplacementPlan(variants,{policy:POLICY,groups},now,remainingRules),hash=replacementPlanHash(plan);
  const unsafe=structuredClone(groups);unsafe.find(g=>g.brand==='Toyota').retention_evidence.price_sek=469900;
  assert.throws(()=>buildReplacementPlan(variants,{policy:POLICY,groups:unsafe},now,remainingRules));
  const noReplacement=structuredClone(groups);noReplacement[0].profiles=[];
  assert.throws(()=>buildReplacementPlan(variants,{policy:POLICY,groups:noReplacement},now,remainingRules));
  const incidental=structuredClone({groups});
  const html=incidental.groups.find(group=>group.brand==='Mazda').profiles[0];
  html.source_hash='c'.repeat(64);html.extraction_payload.field_evidence.price_sek.source_hash=html.source_hash;
  assert.deepEqual(remainingRules.recollectedFacts(incidental),remainingRules.recollectedFacts({groups}),'Only incidental HTML bytes can change after material context matches');
  for(const mutate of [g=>g[0].profiles[0].source_hash='d'.repeat(64),g=>g[2].profiles[0].extraction_payload.context_hash='d'.repeat(64),
    g=>g[2].profiles[0].price_sek=100000,g=>g.find(row=>row.brand==='Toyota').retention_evidence.price_sek=469900]) {
    const changed=structuredClone({groups});mutate(changed.groups);
    assert.notDeepEqual(remainingRules.recollectedFacts(changed),remainingRules.recollectedFacts({groups}));
  }
  const snapshot=async()=>(await db.query(`select jsonb_build_object('v',(select jsonb_agg(to_jsonb(v) order by id) from canonical_model_variants v),
    'd',(select jsonb_agg(to_jsonb(d) order by id) from extracted_variant_drafts d),'s',(select jsonb_agg(to_jsonb(s) order by id) from manufacturer_sources s)) as state`)).rows[0].state;
  const last=rows.at(-1);
  const collision=(await db.query('insert into extracted_variant_drafts(brand,model,variant_name,source_url) values($1,$2,$3,$4) returning id',
    [last.brand,last.model,last.variant_name,last.source_url])).rows[0].id;
  const before=await snapshot();
  await assert.rejects(applyReplacementPlan(db,plan,hash,now,remainingRules),/Staging identity exists/);
  assert.deepEqual(await snapshot(),before);
  await db.query('delete from extracted_variant_drafts where id=$1',[collision]);
  const result=await applyReplacementPlan(db,plan,hash,now,remainingRules);
  assert.equal(result.published,26);assert.equal(result.retired,26);assert.equal(result.models_preserved,14);
  assert.equal(Number((await db.query('select extraction_confidence from manufacturer_sources where url=$1',[rows[0].source_url])).rows[0].extraction_confidence),0.95);
  const campaigns=(await db.query("select price_type,price_valid_until::text as expiry,wltp_range_km from public_ev_variants where brand='Skoda'")).rows;
  assert.equal(campaigns.length,7);
  assert(campaigns.every(row=>row.price_type==='campaign_price'&&row.expiry==='2026-12-15'&&row.wltp_range_km===null));
  const fords=(await db.query("select variant_name,price_sek,price_type,price_source_url,price_verified_at,wltp_range_km,battery_kwh,drivetrain,dc_charge_kw from canonical_model_variants where validation_status='published' and variant_name like 'Explorer %' order by variant_name")).rows;
  assert.equal(fords.length,2);
  assert(fords.every(row=>row.price_sek===null&&row.price_type===null&&row.price_source_url===null&&row.price_verified_at===null&&row.dc_charge_kw===null));
  assert.equal(fords[0].wltp_range_km,556);assert.equal(Number(fords[0].battery_kwh),79);assert.equal(fords[0].drivetrain,'AWD');
  assert.equal(fords[1].wltp_range_km,602);assert.equal(Number(fords[1].battery_kwh),77);assert.equal(fords[1].drivetrain,'RWD');
  const dealer=(await db.query("select source_authority,authorization_evidence_url from manufacturer_sources where brand='Volvo'")).rows;
  assert.equal(dealer[0].source_authority,'authorized_dealer');assert.equal(dealer[0].authorization_evidence_url,auth);
  assert.equal((await db.query("select count(*)::int as n from public_ev_variants where brand='Toyota'")).rows[0].n,1);
  const after=await snapshot();
  await assert.rejects(applyReplacementPlan(db,plan,hash,now,remainingRules));assert.deepEqual(await snapshot(),after);
  console.log(JSON.stringify({remaining_variants_ok:true,real_postgres_rollback:true,campaign_not_list_price:true,
    calendar_date_preserved:true,estimated_specs_excluded:true,models_preserved:true,replay_safe:true,paid_calls:0,remote_writes:0}));
}finally{await db.close();}
