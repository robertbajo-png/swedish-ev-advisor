import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { MODEL, URLS, review } from '../scripts/mercedes_glb_review.mjs';
import { policy } from '../scripts/mercedes_glb_publication.mjs';
import { specQualifications } from '../src/spec-qualifications.js';

const at = '2026-11-21T18:00:00.000Z';
const editions = [
  ['GLB 250+', '2446131_SE3', 3523883, 619000, 'Bakhjulsdrift'],
  ['GLB 350 4MATIC', '2446441_SE3', 3523888, 659000, 'Fyrhjulsdrift'],
];
const rows = [
  ['engine.fuelType','Br\u00e4nsletyp','Electric','Electric'],
  ['engine.enginePerformance','Motoreffekt','200 kW (272 hk)','260 kW (354 hk)'],
  ['wltp.range.total.all.individual','Elektrisk r\u00e4ckvidd, blandad k\xf6rning','631 km','614 km'],
  ['wltp.consumption.total.primaryGear.individual','F\xf6rbrukning blandad k\xf6rning','15,8 kWh/100km','15,9 kWh/100km'],
  ['engine.energyContent','Anv\xe4ndbart energiinneh\xe5ll batteri','85 kWh','85 kWh'],
  ['engine.chargingCapacityDC','Maximal laddeffekt DC','320 kW','320 kW'],
  ['engine.chargingCapacityAC','Maximal laddeffekt AC','11 kW','11 kW'],
  ['dimensions.bootCapacityMin','Bagageutrymmesvolym','540 l','540 l'],
  ['weights.maximumTrailingLoadCombined','Till\xe5ten sl\xe4pvagnsvikt (bromsad sl\xe4pvagn vid 12 %)','750 kg (1 500 kg)','750 kg (2 000 kg)'],
  ['seats','Sittplatser','5','5'],
  ['engine.propulsion.name','Drivlina','Bakhjulsdrift','Fyrhjulsdrift'],
];
const vehicleId = code => 'sv_SE__'+code+'__LE-L_MJ-807_PC-FIXTURE';
const page = (url,contents) => `<html lang="sv-SE"><link rel="canonical" href="${url}">${contents}</html>`;

function fixture({mutateFactory,mutateProduct,mutatePrice,mutateTable,mutateOrder}={}) {
  const factory = {mode:'full',fetchedAt:at,vehicle:{typeClass:'X244',modelName:'GLB',productType:'CAR',electrical:true,
    baumuster:'2446131',fcisVehicleId:'2446131_SE3-807_057',vehicleName:'GLB 250+ Advanced Edition',
    initialVehicleId:vehicleId(editions[0][1])},initialPrice:{currency:'SEK',configurationPrice:619000,startingPrice:619000},
    context:{currentVehicleId:vehicleId(editions[0][1])},styles:[{id:'X244__MERCEDES_BENZ__PROGRESSIVE',
      name:'Progressive',vehicleName:'GLB 250+ Advanced Edition',featuredKeyFactsInformation:{vehicleId:vehicleId(editions[1][1])}}],
    technicalDataSheet:{footnotes:{'1':'WLTP. Samtliga utsl\u00e4ppsv\u00e4rden g\u00e4ller bil i grundversion.'},models:
      Object.fromEntries(editions.map(([label,code],i)=>[code,{label,filter:{'technicalInformation.engine.fuelTypeFilterGroup':'Electric'},
        technicalValueGroups:[{technicalValues:rows.map(([id,label,...values])=>({id:'technicalInformation.'+id,label,value:values[i],
          footnotes:id.startsWith('wltp.')?['1']:[]}))}]}]))}};
  const product = {'@id':MODEL+'/#car',name:'GLB Elektrisk',model:'X244',bodyType:'SUV',url:MODEL,
    hasVariant:editions.map(([model,,,price,drive])=>({name:'Mercedes-Benz '+model+' Advanced Edition',
      vehicleConfiguration:'Mercedes-Benz '+model+' Advanced Edition, '+drive+', 5 Sittplatser, 5 D\u00f6rrar, SUV',
      offers:{'@type':'AggregateOffer',lowPrice:price,priceCurrency:'SEK'}}))};
  const campaign = {payload:{anchorId:'glb-electric',headline:'GLB Advanced Edition.<br>',
    subline:'<p>Listpriser:<br>GLB 250+ Advanced Edition fr\xe5n 619 000 kr<br>GLB 350 4MATIC Advanced Edition fr\xe5n 659 000 kr</p>'}};
  const table = [['','GLB 250+','GLB 350 4MATIC'],...rows.map(r=>r.slice(1))];
  mutateFactory?.(factory); mutateProduct?.(product); mutatePrice?.(campaign); mutateTable?.(table);
  const html = '<h1>GLB Elektrisk</h1><table>'+table.map(row=>'<tr>'+row.map(value=>'<td>'+value+'</td>').join('')+'</tr>').join('')+'</table>'
    +'<script>(window.ssrData ??= {})["abc"] = '+JSON.stringify(factory)+';</script>'
    +'<script type="application/ld+json">'+JSON.stringify(product)+'</script>';
  const raw={'model.html':page(MODEL,html),'prices.html':page(URLS['prices.html'],
    "<script>(window.test)['abc'] = "+JSON.stringify(campaign)+";</script>"),
    'appointment.html':'<title>H\xf6glunds Bil</title>',
    'dealer.html':'<p>Vi \xe4r en fullserviceanl\xe4ggning som \xe4r auktoriserad \xe5terf\xf6rs\xe4ljare av Mercedes och Mazda.</p>',
    'launch.html':'<h1>Nya eldrivna Mercedes-Benz GLB visad.</h1><a href="https://www.mynewsdesk.com/se/mercedes-benz-sverige/images/nya-mercedes-benz-glb-2026-3376630">Foto</a>'};
  for (const [[model,,post,price],file] of editions.map((row,i)=>[row,i===0?'dealer-250.html':'dealer-350.html'])){
    const car = {databaseId:post,fuelTypes:{nodes:[{name:'El'}]},bodyTypes:{nodes:[{databaseId:11,name:'SUV'}]},
      bytbil:{carYearmodel:2027,carNoveltyType:'new_car',carPriceSek:String(price),carExklMoms:String(price*4/5),
        carModeldescription:model+' Advanced Edition 3.95% R\xc4NTA',carInfo:'<p>Denna bil \xe4r en best\xe4llningsbil</p>'}};
    mutateOrder?.(car);
    raw[file]='<script type="application/json" id="__NEXT_DATA__">'+JSON.stringify({props:{pageProps:{car}}})+'</script>';
  }
  const files=Object.fromEntries(Object.entries(raw).map(([name,body])=>[name,Buffer.from(body)]));
  const sources=Object.fromEntries(Object.entries(files).map(([name,body])=>[name,{sha256:createHash('sha256').update(body).digest('hex')}]));
  return review(files,sources,at);
}

test('builds exact complete five-seat X244 Advanced Edition profiles without declaring a final cash quote', () => {
  const report=fixture();
  const vals=report.variants.map(({technical_facts:f,price_evidence:p})=>
    [Object.keys(f).length,f.wltp_range_km.value,f.wltp_consumption_kwh_100km.value,f.seats.value,
      f.boot_liters.value,f.tow_kg.value,f.ac_charge_kw.value,f.drivetrain.value,p.value,p.price_type]);
  assert.deepEqual(vals,[[9,631,15.8,5,540,1500,11,'RWD',619000,'manufacturer_from'],
    [9,614,15.9,5,540,2000,11,'AWD',659000,'manufacturer_from']]);
  assert(!report.publication_approved);
  assert.equal(report.photo_candidates.length,1);
});

test('rejects X248 hybrid, seven seats, a different factory edition or a stale snapshot', () => {
  for (const mutate of [
    {mutateFactory:s=>{s.vehicle.typeClass='X248';}},
    {mutateFactory:s=>{s.styles[0].featuredKeyFactsInformation.vehicleId=vehicleId('2446441_SE4');}},
    {mutateFactory:s=>{s.fetchedAt='2026-11-19T18:00:00.000Z';}},
    {mutateProduct:p=>{p.hasVariant[1].vehicleConfiguration=p.hasVariant[1].vehicleConfiguration.replace('5 Sittplatser','7 Sittplatser');}},
    {mutateOrder:o=>{o.bytbil.carYearmodel=2026;}},
    {mutateOrder:o=>{o.fuelTypes.nodes[0].name='Bensin';}},
  ]) assert.throws(()=>fixture(mutate));
});

test('rejects a missing combined WLTP qualifier, drifted visible specs and campaign-only pricing', () => {
  for (const mutate of [
    {mutateFactory:s=>{s.technicalDataSheet.footnotes['1']='Town range';}},
    {mutateTable:t=>{t.find(row=>row[0].startsWith('Elektrisk'))[1]='798 km';}},
    {mutateTable:t=>{t.find(row=>row[0]==='Maximal laddeffekt AC')[1]='22 kW';}},
    {mutatePrice:p=>{p.payload.subline=p.payload.subline.replace('Listpriser:', 'Privatleasing:');}},
    {mutatePrice:p=>{p.payload.subline=p.payload.subline.replace('659 000', '644 000');}},
  ]) assert.throws(()=>fixture(mutate));
});

test('keeps other fuel rows separate from the X244 discovery link', () => {
  const model={id:'electric'}, market={id:'exact-bev',fuel_type_raw:'EL',canonical_model_id:null};
  const hybrid={id:'same-name-hybrid',fuel_type_raw:'BENSIN/EL',canonical_model_id:null};
  const check=(rows)=>policy.scopedDiscovery.check({market_models:rows},model,market);
  check([market,hybrid]);
  assert.throws(()=>check([market,{...hybrid,canonical_model_id:model.id}]),/exact EL row/);
  assert.equal(policy.localOnly,true);
});

test('applies five-seat GLB buyer qualifications only to the exact electric variant', () => {
  const row={brand:'Mercedes-Benz',model:'Glb',seats:5,variant_name:'GLB 250+ Advanced Edition',source_url:MODEL,
    image_url:'/media/vehicles/mercedes-benz-glb-press-01ba09303394.jpg'};
  const notes=specQualifications(row);
  assert.match(notes.rangeNote,/Blandad WLTP.*fem/);
  assert.match(notes.consumptionNote,/85 kWh.*11 kW.*320 kW/);
  assert.match(notes.practicalNote,/540 liter.*bromsat/);
  assert.match(notes.imageNotice,/Utrustningen kan skilja/);
  for (const other of [{seats:7},{variant_name:'GLB 200'},{source_url:MODEL.replace('glb-electric','glb')}]) {
    for (const field of ['rangeNote','practicalNote','imageNotice']) assert.equal(specQualifications({...row,...other})[field],null);
  }
});
