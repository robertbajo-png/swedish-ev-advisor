import assert from 'node:assert/strict';

export const POLICY='current_exact_variants_2026_10_v2';
const registry={
  'Skoda|Elroq':{retire:['60 Selection','85 Selection','85x Selection','RS'],
    url:'https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb',adapter:'skoda_elroq_explore_grid_v1',
    type:'price_list_pdf',names:['60 Selection','60 Sportline','85 Selection','85 Sportline','85x Selection','85x Sportline','RS'].map(name=>name+' Explore Edition')},
  'Cupra|Born':{retire:['Born'],url:'https://www.cupraofficial.se/bilar/born',adapter:'cupra_born_vz_html_v1',type:'manufacturer_model_page',names:['Born VZ']},
  'Mazda|6E':{retire:['Mazda 6e Takumi'],url:'https://www.mazda.se/modeller/mazda-6e/',adapter:'mazda6e_my27_embedded_grades_v1',
    type:'manufacturer_model_page',names:['Takumi MY2027','Homura Plus MY2027','Takumi Plus MY2027']},
  'Volkswagen|Id.3':{retire:['ID.3 Neo'],url:'https://www.volkswagen.se/sv/bygg-din-bil.html/__app/30355.app',
    adapter:'vw_id3_neo_trend_config_v1',type:'manufacturer_configurator',names:['ID.3 Neo Trend']},
  'Ford|Explorer':{retire:['Explorer Business Edition'],url:'https://www.ford.se/bilar/personbilar-och-suver/explorer',
    adapter:'ford_explorer_exact_drive_range_v1',type:'manufacturer_model_page',authority:'importer',names:['Explorer RWD 77 kWh','Explorer AWD 79 kWh']},
  'BMW|i4':{retire:['BMW i4 eDrive40 Gran Coupé','BMW i4 xDrive40'],url:'https://hitta.bmw.se/r/G26E-i4/i4-eDrive40-WBY61HD030FW37556',
    adapter:'exact_new_stock_cash_v1',type:'manufacturer_configurator',names:['i4 eDrive40 M Sport Business Edition (lagerbil FW37556)']},
  'Volvo|Es90':{retire:['ES90 Plus','ES90 Ultra'],url:'https://www.volvocarretail.se/bilar-i-lager/nya/volvo/es90/single-motor-extended-range-jwr04c',
    adapter:'exact_new_stock_cash_v1',type:'authorized_dealer_stock_page',authority:'authorized_dealer',sourceName:'Volvo Car Retail',
    names:['ES90 Single Motor Extended Range Ultra MY2026 (lagerbil JWR04C)']},
  'Volvo|Ex30':{retire:['EX30 Black Edition','EX30 Core','EX30 Cross Country','EX30 Plus','EX30 Ultra'],
    url:'https://www.volvocarretail.se/bilar-i-lager/nya/volvo/ex30/p5-long-range-01a0f17196c07c0eac58aa44aeea8ae4',
    adapter:'exact_new_stock_cash_v1',type:'authorized_dealer_stock_page',authority:'authorized_dealer',sourceName:'Volvo Car Retail',
    names:['EX30 P5 Long Range Core MY2027 (lagerbil)']},
  'Toyota|bZ4X':{retire:['Active AWD','Active FWD'],names:[]},
  'Zeekr|7X':{retire:['Core RWD','Long Range RWD','Privilege AWD'],url:'https://www.zeekr.eu/sv-se/models/7x',
    adapter:'zeekr7x_exact_spec_columns_v1',type:'manufacturer_specs_page',
    names:['Privilege AWD 100 kWh','Long Range RWD 100 kWh','Core RWD 75 kWh']},
  'Audi|A6 E-Tron':{retire:['A6 Sportback e-tron'],url:'https://lagerbilar.vwgroup.se/audi/RRR07B',adapter:'vwg_exact_new_stock_v1',
    authority:'importer',sourceName:'Volkswagen Group Sverige',type:'manufacturer_configurator',
    stock:['A6 Sportback e-tron','performance S-line 270 kW','RRR07B',2027],names:['A6 Sportback e-tron performance S-line 270 kW MY2027 (lagerbil RRR07B)']},
  'Volkswagen|Id.4':{retire:['ID.4 Pro Sweden Olympic Edition'],url:'https://lagerbilar.vwgroup.se/volkswagen/BSJ09L',adapter:'vwg_exact_new_stock_v1',
    authority:'importer',sourceName:'Volkswagen Group Sverige',type:'manufacturer_configurator',
    stock:['ID.4','PRO 4MOTION 220 KW/ 299 HK 77 KWH BATTERI,','BSJ09L',2027],names:['ID.4 Pro 4MOTION 77 kWh MY2027 (lagerbil BSJ09L)']},
  'Audi|Q6 E-Tron':{retire:['Q6 e-tron'],url:'https://www.bilia.se/bilar/sok-bil/audi/q6-e-tron/jce98y/',
    adapter:'exact_new_stock_cash_v1',type:'authorized_dealer_stock_page',authority:'authorized_dealer',sourceName:'Bilia Haninge Audi',
    names:['Q6 e-tron quattro SUV 315 kW MY2027 (lagerbil JCE98Y)']},
  'Mercedes-Benz|Cla':{retire:['CLA Advanced Edition'],url:'https://www.hoglundsbil.se/bilar?sort=0',
    adapter:'hoglund_exact_new_cla_stock_v1',type:'authorized_dealer_stock_page',authority:'authorized_dealer',sourceName:'Höglunds Bil',
    names:['CLA 200 Advanced Edition MY2027 (lagerbil)','CLA 250+ Advanced Edition MY2027 (lagerbil)','CLA 350 4MATIC Advanced Edition MY2027 (lagerbil)']},
};
const unknown=['wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','boot_liters','tow_kg','seats','drivetrain'];
export function validateRemainingProfile(row,now=new Date()) {
  const entry=registry[row.brand+'|'+row.model];
  assert(entry,'Unapproved remaining model');
  assert.equal(row.source_url,entry.url);
  assert.equal(row.source_type,entry.type);
  assert.equal(row.source_authority,entry.authority||'manufacturer');
  assert.equal(row.source_name,entry.sourceName||row.brand+' Sverige');
  assert(entry.names.includes(row.variant_name),'Exact approved current version required');
  assert.match(row.source_hash,/^[a-f0-9]{64}$/);
  const age=now.getTime()-Date.parse(row.fetched_at);
  assert(Number.isFinite(age)&&age>=-60000&&age<=900000,'Fresh source required');
  assert(row.extraction_confidence>=0.92&&row.extraction_confidence<=1);
  const payload=row.extraction_payload;
  assert.equal(payload.policy,POLICY);
  assert.equal(payload.adapter,entry.adapter);
  if(row.brand==='Zeekr') {
    assert.equal(row.price_sek,null);assert.equal(row.price_type,null);assert.equal(row.price_valid_until,null);
    assert.match(payload.context_hash,/^[a-f0-9]{64}$/);
    const fields={battery_kwh:['Batteri',/^([0-9]+) kWh$/,5,300],wltp_range_km:['Räckvidd, upp till',/^([0-9]+) Km$/,50,1200],
      tow_kg:['Dragvikt',/^([0-9]+) Kg$/,0,4000],boot_liters:['Lastutrymme',/^([0-9]+)L VDA$/,0,3000]};
    const header=row.variant_name.replace(/ [0-9]+ kWh$/,'');
    assert(['Privilege AWD','Long Range RWD','Core RWD'].includes(header));
    assert.equal(row.variant_name,header+' '+row.battery_kwh+' kWh');
    assert.deepEqual(Object.keys(payload.field_evidence).sort(),[...Object.keys(fields),'drivetrain'].sort());
    for(const [field,[label,pattern,min,max]] of Object.entries(fields)) {
      const evidence=payload.column_evidence[field];assert.equal(evidence.column,header);assert.equal(evidence.label,label);
      const match=evidence.text.match(pattern);assert(match);assert.equal(Number(match[1]),row[field]);
      assert(row[field]>=min&&row[field]<=max);
    }
    assert.equal(row.drivetrain,header.endsWith('AWD')?'AWD':'RWD');
    assert.deepEqual(payload.column_evidence.drivetrain,{column:header,label:'Motor',text:row.drivetrain==='AWD'?'Dubbel':'Enkel'});
    assert.equal(row.source_quote,[header,...Object.values(payload.column_evidence).map(value=>value.label+' '+value.text)].join(' | '));
    for(const field of unknown) {
      if(Object.hasOwn(fields,field)||field==='drivetrain')assert.deepEqual(payload.field_evidence[field],
        {quote:row.source_quote,variant:row.variant_name,value:row[field],source_url:row.source_url,source_hash:row.source_hash});
      else assert.equal(row[field],null,'Unverified charger station rating must not become vehicle DC power');
    }
    return row;
  }
  if(row.brand==='Ford') {
    assert.equal(row.price_sek,null);assert.equal(row.price_type,null);assert.equal(row.price_valid_until,null);
    const expected=row.variant_name==='Explorer RWD 77 kWh'?{wltp_range_km:602,battery_kwh:77,drivetrain:'RWD'}:{wltp_range_km:556,battery_kwh:79,drivetrain:'AWD'};
    assert.match(payload.context_hash,/^[a-f0-9]{64}$/);
    const expression=/^Men motormässigt då\? Ja, en laddning räcker – enligt WLTP – (\d+) kilometer vid blandad körning för den bakhjulsdrivna varianten med ett batteripaket på (\d+) kilowattimmar\. Den fyrhjulsdrivna versionen har ett batteri på (\d+) kilowattimmar och en räckvidd på (\d+) kilometer$/;
    const quote=row.source_quote.match(expression);
    assert(quote,'Exact motor/battery/range paragraph required');
    assert.deepEqual(quote.slice(1).map(Number),[602,77,79,556]);
    assert.deepEqual(Object.keys(payload.field_evidence).sort(),Object.keys(expected).sort());
    for(const field of unknown) {
      assert.equal(row[field],expected[field]??null);
      if(expected[field]!==undefined)assert.deepEqual(payload.field_evidence[field],{quote:row.source_quote,variant:row.variant_name,source_url:row.source_url,source_hash:row.source_hash,value:expected[field]});
    }
    return row;
  }
  assert(Number.isInteger(row.price_sek)&&row.price_sek>=100000&&row.price_sek<=3000000);
  for(const field of unknown)assert.equal(row[field],null,'No inherited technical maxima');
  assert.deepEqual(payload.field_evidence.price_sek,{quote:row.source_quote,variant:row.variant_name,source_url:row.source_url,source_hash:row.source_hash});
  if(entry.adapter==='hoglund_exact_new_cla_stock_v1') {
    assert.equal(row.price_type,'dealer_offer');assert.equal(row.price_valid_until,null);
    assert.match(payload.context_hash,/^[a-f0-9]{64}$/);assert.match(payload.source_pointer,/^\/props\/pageProps\/carsList\/[0-9]+$/);
    const titles={'19043773':['CLA 200 Advanced Edition MY2027 (lagerbil)','Mercedes-Benz CLA 200 Advanced Edition 3.95% RÄNTA'],
      '19003980':['CLA 250+ Advanced Edition MY2027 (lagerbil)','Mercedes-Benz CLA 250+ Advanced Edition 3.95% RÄNTA'],
      '19004063':['CLA 350 4MATIC Advanced Edition MY2027 (lagerbil)','Mercedes-Benz CLA 350 4MATIC Advanced Edition 3.95% RÄNTA']};
    const stock=payload.stock_row,exact=titles[stock.car_id];assert(exact);assert.equal(row.variant_name,exact[0]);
    assert.deepEqual(stock,{car_id:stock.car_id,name:exact[1],noveltyType:'new_car',year:2027,mileage:0,is_leasing:0,
      brand_name:'Mercedes-Benz',model_name:'CLA',body_type_name:'Sedan',fuel_type_name:'El',location_name:'Höglunds Bil',
      price:row.price_sek,car_exkl_moms:row.price_sek*4/5,sale_price:'',sale_car_exkl_moms:''});
    assert.equal(row.source_quote,JSON.stringify(stock));
    const auth=payload.authorization_review;
    assert.equal(row.authorization_evidence_url,'https://www.hoglundsbil.mercedes-benz.se/passengercars/startpage.html');
    assert.equal(auth.url,row.authorization_evidence_url);assert.equal(auth.reviewed_on,'2026-10-27');
    assert.equal(auth.method,'primary_manufacturer_page_review');assert.equal(auth.manufacturer_label,'Höglunds Bil | Mercedes-Benz Agent');
    assert.equal(auth.supporting_url,'https://www.hoglundsbil.se/anlaggningar/mobility-motors-norrtalje');
    assert.match(auth.supporting_hash,/^[a-f0-9]{64}$/);
    assert.equal(auth.quote,'Vi är en fullserviceanläggning som är auktoriserad återförsäljare av Mercedes och Mazda.');
    const age=now.getTime()-Date.parse(auth.fetched_at);assert(age>=-60000&&age<=900000);
    const reviewed=now.getTime()-Date.parse(auth.reviewed_on);assert(reviewed>=0&&reviewed<=30*86400000);
    return row;
  }
  if(entry.adapter==='vwg_exact_new_stock_v1') {
    assert.equal(row.price_type,'dealer_offer');assert.equal(row.price_valid_until,null);
    assert.match(payload.context_hash,/^[a-f0-9]{64}$/);assert.equal(payload.source_pointer,'/props/pageProps/car');
    assert.equal(payload.price_calculation,'advertised_cash_plus_mandatory_fee');
    const fee=payload.mandatory_fee_sek;
    assert(Number.isInteger(fee)&&fee>=0&&fee<=10000);
    const quotedFee=payload.fee_quote.match(/^(?:Administrationskostnad på ([0-9]+):- tillkommer|Reg avg på ([0-9]+)kr tillkommer\.)$/);
    assert(quotedFee);assert.equal(Number(quotedFee[1]||quotedFee[2]),fee);
    const cash=row.price_sek-fee;assert(cash>=100000);
    const [model,version,regNumber,modelYear]=entry.stock;
    assert.deepEqual(payload.stock_row,{brand:row.brand,model,version,regNumber,modelYear,used:false,mileage:0,unPublished:false,
      firstRegistrationDate:null,fuelType:'El',cash_price_sek:cash});
    assert.equal(row.source_quote,row.variant_name+' | Pris '+String(cash).replace(/\B(?=(\d{3})+(?!\d))/g,' ')+' kr | '+payload.fee_quote);
    return row;
  }
  if(entry.adapter==='exact_new_stock_cash_v1') {
    assert.equal(row.price_type,'dealer_offer');
    assert.match(payload.context_hash,/^[a-f0-9]{64}$/);
    assert.equal(row.source_quote,`${row.variant_name} | Kontantpris ${String(row.price_sek).replace(/\B(?=(\d{3})+(?!\d))/g,' ')} kr`);
    const car=payload.stock_car;
    assert.equal(car.brand.name,row.brand);
    assert.equal(car.url||row.source_url,row.source_url);
    const offers=Array.isArray(car.offers)?car.offers:[car.offers];
    let offer;
    if(row.brand==='BMW') {
      assert.equal(car.name,'i4 eDrive40');assert.equal(car.vehicleIdentificationNumber,'WBY61HD030FW37556');
      assert.equal(car.vehicleEngine.fuelType,'Elbil');
      const cash=offers.filter(item=>item.businessFunction==='http://purl.org/goodrelations/v1#Sell');
      assert.equal(cash.length,1);offer=cash[0];
      assert.equal(offer.seller.name,'Bilia Nacka');
      assert.equal(row.price_valid_until,offer.priceValidUntil);
      assert.match(row.price_valid_until,/^\d{4}-\d{2}-\d{2}$/);
      assert.equal(new Date(row.price_valid_until).toISOString().slice(0,10),row.price_valid_until);
      assert(row.price_valid_until>=now.toISOString().slice(0,10));
      assert.equal(row.authorization_evidence_url,null);
    } else if(row.brand==='Volvo') {
      const exact=row.model==='Es90'?['Volvo ES90','ES90 Single Motor Extended Range',2026,'SM Ext Ultra | Privatleasing 9490kr/mån']:['Volvo EX30','EX30 P5 Long Range',2027,'Core'];
      assert.deepEqual([car.name,car.model,car.vehicleModelDate,car.vehicleConfiguration],exact);
      assert.equal(car.vehicleEngine.fuelType,'El');
      assert.deepEqual(car.mileageFromOdometer,{'@type':'QuantitativeValue',unitCode:'KMT',value:0});
      assert.equal(offers.length,1);offer=offers[0];assert.equal(offer.seller.name,'Volvo Car Retail');
      assert.equal(row.price_valid_until,null);
      const auth='https://www.volvocars.com/se/l/studios/stockholm/';
      assert.equal(row.authorization_evidence_url,auth);
      assert.deepEqual(payload.authorization_review,{url:auth,reviewed_on:'2026-10-27',method:'primary_manufacturer_page_review',
        dealer:'Volvo Car Retail',quote:'Du kan också få rådgivning och beställa din bil direkt i studion.'});
      const authAge=now.getTime()-Date.parse(payload.authorization_review.reviewed_on);
      assert(authAge>=0&&authAge<=30*86400000,'Dealer authorization review must be current');
    } else {
      assert.equal(row.brand,'Audi');assert.equal(row.model,'Q6 E-Tron');
      assert.deepEqual([car.name,car.model,car.vehicleModelDate,car.vehicleIdentificationNumber,car.bodyType],
        ['Audi Q6 e-tron quattro','Q6 e-tron',2027,'WAUZZZGF3VA023430','SUV']);
      assert.equal(car.vehicleEngine.fuelType,'El');
      assert.deepEqual(car.mileageFromOdometer,{'@type':'QuantitativeValue',unitCode:'KMT',value:0});
      assert.equal(offers.length,1);offer=offers[0];
      assert.equal(offer.seller['@id'],'https://www.bilia.se/anlaggningar/haninge-audi#dealer');
      assert.equal(row.price_valid_until,null);
      assert.equal(row.authorization_evidence_url,'https://lagerbilar.vwgroup.se/audi');
      const auth=payload.authorization_review;
      assert.equal(auth.url,row.authorization_evidence_url);assert.equal(auth.method,'official_importer_network');
      assert.equal(auth.dealer,'Bilia Haninge Audi');assert.match(auth.source_hash,/^[a-f0-9]{64}$/);
      assert.match(auth.source_pointer,/^\/props\/pageProps\/carsWithFilter\/filter\/retailers\/[0-9]+\/value$/);
      assert.deepEqual(auth.network_entry,{uniqueId:'40584A',name:'Bilia Haninge Audi',brandCode:'A',locationIds:[]});
      const age=now.getTime()-Date.parse(auth.fetched_at);assert(age>=-60000&&age<=900000,'Fresh official dealer network evidence required');
    }
    const condition=offer.itemCondition||car.itemCondition;
    assert(['http://schema.org/NewCondition','https://schema.org/NewCondition'].includes(condition));
    assert(['http://schema.org/InStock','https://schema.org/InStock'].includes(offer.availability));
    assert.equal(offer.priceCurrency,'SEK');assert.equal(Number(offer.price),row.price_sek);
    return row;
  }
  const quote=row.source_quote.split(' | ');
  let amount;
  if(row.brand==='Skoda') {
    assert.equal(row.price_type,'campaign_price');
    assert.match(row.price_valid_until,/^\d{4}-\d{2}-\d{2}$/);
    assert(Number.isFinite(Date.parse(row.price_valid_until))&&new Date(row.price_valid_until).toISOString().slice(0,10)===row.price_valid_until,'Valid campaign date required');
    assert(row.price_valid_until>=now.toISOString().slice(0,10),'Campaign expired');
    assert.equal(quote.length,5);
    assert.equal(quote[0],'Škoda Elroq Explore Edition');
    const cell=payload.price_cell;
    assert.equal(cell.page,1);
    assert.equal(quote[1],cell.motor);
    assert.equal(quote[2],cell.trim);
    assert.equal(quote[3],cell.text);
    assert.equal(cell.column,['Selection','Sportline','RS'].indexOf(cell.trim));
    assert((cell.motor==='RS')===(cell.trim==='RS'),'Unavailable motor/trim combination');
    assert.equal(row.variant_name,cell.motor+(cell.motor==='RS'?'':' '+cell.trim)+' Explore Edition');
    assert.equal(quote[4],'Gäller tom '+row.price_valid_until);
    assert.deepEqual(payload.field_evidence.price_valid_until,{source_url:row.source_url,source_hash:row.source_hash,quote:quote[4],value:row.price_valid_until});
    assert(Array.isArray(cell.bbox)&&cell.bbox.length===4&&cell.bbox.every(Number.isFinite));
    assert(cell.bbox[0]>=389&&cell.bbox[2]<=566&&cell.bbox[2]-cell.bbox[0]>40&&cell.bbox[2]-cell.bbox[0]<90);
    assert(cell.bbox[1]>=145&&cell.bbox[3]<=222&&cell.bbox[3]>cell.bbox[1]);
    amount=quote[3].match(/^([0-9]{3})\s*([0-9]{3})\s*kr$/);
  } else {
    assert.equal(row.price_type,'list_price');assert.equal(row.price_valid_until,null);
    assert.match(payload.context_hash,/^[a-f0-9]{64}$/,'Source terms/model context required');
    if(row.brand==='Cupra') {assert.equal(quote.length,2);assert.equal(quote[0],'Born VZ');}
    else if(row.brand==='Mazda') {
      assert.equal(quote.length,3);assert.equal(quote[0],'2027 Mazda6e');
      assert.equal(row.variant_name,quote[1]+' MY2027');
      assert.match(payload.source_pointer,/^\/components\/[0-9]+\/submodules\/[0-9]+\/props\/cards\/[0-2]$/);
    } else {
      assert.equal(row.brand,'Volkswagen');assert.equal(quote.length,3);
      assert.equal(quote[0],'ID.3 Neo');assert.equal(quote[1],'Trend');
      assert.equal(payload.battery_options,1);
    }
    amount=quote.at(-1).match(/^(?:Från |Pris inkl\. moms )([0-9]{3})[. ]([0-9]{3}) kr$/);
  }
  assert(amount&&Number(amount[1]+amount[2])===row.price_sek,'Quoted exact-version cash price required');
  return row;
}

export const remainingRules={policy:POLICY,retired:Object.fromEntries(Object.entries(registry).map(([key,value])=>[key,value.retire])),validateProfile:validateRemainingProfile};
remainingRules.retained={'Toyota|bZ4X':['Active FWD 57.7 kWh 167 hk']};
remainingRules.validateRetention=(evidence,retained,now)=>{
  assert.equal(retained.length,1);assert.equal(retained[0].variant_name,'Active FWD 57.7 kWh 167 hk');
  assert.equal(retained[0].brand,'Toyota');assert.equal(retained[0].model,'bZ4X');
  assert.equal(evidence.source_url,'https://www.toyota.se/bilar/bz4x/specifications');
  assert.match(evidence.source_hash,/^[a-f0-9]{64}$/);assert.match(evidence.context_hash,/^[a-f0-9]{64}$/);
  const age=now.getTime()-Date.parse(evidence.fetched_at);assert(age>=-60000&&age<=900000);
  assert.equal(evidence.variant_name,retained[0].variant_name);
  for(const field of ['price_sek','wltp_range_km','battery_kwh','drivetrain']) {
    const value=retained[0][field];assert.notEqual(value,null);
    assert.equal(evidence[field],field==='drivetrain'?value:Number(value),'Current retained Toyota facts conflict with fresh configuration');
  }
  assert.equal(evidence.source_quote,'Elmotor 167 hk, batteri 57,7 kWh | Active | '+evidence.price_sek);
};
remainingRules.recollectedFacts=intake=>intake.groups.map(group=>{
  const value={...group};
  if(value.retention_evidence){value.retention_evidence={...value.retention_evidence};delete value.retention_evidence.fetched_at;delete value.retention_evidence.source_hash;}
  return {...value,profiles:group.profiles.map(({fetched_at,...profile})=>{
  const copy=structuredClone(profile);
  if(['Cupra','Mazda','Volkswagen','Ford','BMW','Volvo','Zeekr','Audi','Mercedes-Benz'].includes(copy.brand)) {
    // Fresh collector rechecks the full visible page or model-grade/legal JSON.
    // Other HTML bytes may vary; PDF bytes and material source context may not.
    delete copy.source_hash;
    for(const evidence of Object.values(copy.extraction_payload.field_evidence))delete evidence.source_hash;
    const auth=copy.extraction_payload.authorization_review;
    if(auth?.method==='official_importer_network'){delete auth.fetched_at;delete auth.source_hash;}
    if(copy.brand==='Mercedes-Benz')delete auth.fetched_at;
  }
  return copy;
})};});
remainingRules.freshProofs=true;
