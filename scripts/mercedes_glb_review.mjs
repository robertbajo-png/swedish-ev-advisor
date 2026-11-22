import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, realpath, stat, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { parse, parseFragment } from 'parse5';

const mb = 'https://www.mercedes-benz.se';
const dealer = 'https://www.hoglundsbil.se';
export const MODEL = mb + '/passengercars/models/suv/glb-electric/overview.html';
export const PRESS = 'https://www.mynewsdesk.com/se/mercedes-benz-sverige/pressreleases/nya-eldrivna-mercedes-benz-glb-visad-plats-foer-sju-och-faar-dra-upp-till-2000-kg-3420354';
export const URLS = {
  'model.html':MODEL, 'prices.html':mb+'/passengercars/campaigns/laddning-ingaar.html',
  'appointment.html':'https://www.hoglundsbil.mercedes-benz.se/passengercars/startpage.html',
  'dealer.html':dealer+'/anlaggningar/mobility-motors-norrtalje',
  'dealer-250.html':dealer+'/bil/mercedes-benz-glb-250-advanced-edition-2-95-ranta',
  'dealer-350.html':dealer+'/bil/mercedes-benz-glb-350-4matic-advanced-edition-2-95-ranta',
  'launch.html':PRESS,
};
export const MARKET_URLS = {
  'market.html':'https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober',
  'market.xlsx':'https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx',
};
export const GLB_MARKET = Object.freeze({
  brand_raw:'MERCEDES', model_raw:'GLB', fuel_type_raw:'EL', normalized_brand:'mercedes benz', normalized_model:'glb',
  last_seen_month:'2026-10-01', registrations_last_month:187, registrations_ytd:1488,
});
const agent = 'SwedishEVAdvisor/0.1';
const prefix = 'mercedes-glb-x244-review-';
const limit = 4_000_000;
const normalize = value => String(value ?? '').replace(/\s+/gu,' ').trim();
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function* nodes(node, predicate) {
  if (predicate(node)) yield node;
  for (const c of node.childNodes ?? []) yield* nodes(c,predicate);
}
const tag = (doc, name) => [...nodes(doc,n=>n.tagName === name)];
const attr = (n, k) => n?.attrs?.find(a=>a.name===k)?.value;
const rawScript = n => (n.childNodes ?? []).map(x=>x.value ?? '').join('');
const text = node => normalize(node.value ?? (
  ['style','script','noscript','template'].includes(node.tagName) ? '' : (node.childNodes ?? []).map(text).join(' ')
));
const one = (items, message) => {assert.equal(items.length,1,message); return items[0];};
const fields = (row, expected) => {
  for (const [k,v] of Object.entries(expected)) assert.deepEqual(row?.[k],v,'Unexpected GLB scope: '+k);
};
const identity = [
  {motor:'GLB 250+',code:'2446131_SE3',range:631,consumption:15.8,price:619000,tow:1500,drive:'RWD',
    swedishDrive:'Bakhjulsdrift',hp:'200 kW (272 hk)',dealerFile:'dealer-250.html',post:3523883},
  {motor:'GLB 350 4MATIC',code:'2446441_SE3',range:614,consumption:15.9,price:659000,tow:2000,drive:'AWD',
    swedishDrive:'Fyrhjulsdrift',hp:'260 kW (354 hk)',dealerFile:'dealer-350.html',post:3523888},
];

function page(body, url) {
  const doc = parse(body.toString('utf8'));
  assert.equal(attr(one(tag(doc,'html'),'Expected HTML root'),'lang'),'sv-SE');
  assert.deepEqual(tag(doc,'link').filter(n=>attr(n,'rel')==='canonical').map(n=>attr(n,'href')),[url]);
  return doc;
}

function ssr(doc) {
  const match = one(tag(doc,'script').map(rawScript).map(s=>/^\s*\(window\.ssrData \?\?= \{\}\)\["[a-f0-9]+"\] = (\{"mode":"full"[\s\S]+\});\s*$/.exec(s))
    .filter(Boolean), 'Expected one full GLB factory payload');
  return JSON.parse(match[1]);
}

function campaign(doc) {
  const block = one(tag(doc,'script').map(rawScript).filter(s=>s.includes('"anchorId":"glb-electric"') &&
    s.includes('"headline":"GLB Advanced Edition.')), 'Expected one GLB-specific official starting-price block');
  const match = /\]\s*=\s*(\{"payload":[\s\S]+\});?\s*$/.exec(block);
  assert(match,'Expected literal price payload');
  const payload = JSON.parse(match[1]).payload;
  assert.equal(payload.anchorId,'glb-electric');
  const textBlock = text(parseFragment(payload.subline));
  assert.match(textBlock,/^Listpriser:/,'A finance amount is not an official starting price');
  return textBlock;
}

function dealerOffer(body, i, proof) {
  const doc = parse(body.toString('utf8'));
  const next = one(tag(doc,'script').filter(n=>attr(n,'id')==='__NEXT_DATA__' && attr(n,'type')==='application/json'),
    'Require the primary dealer vehicle data');
  const car = JSON.parse(rawScript(next)).props?.pageProps?.car;
  const name = i.motor + ' Advanced Edition';
  fields(car,{databaseId:i.post,fuelTypes:{nodes:[{name:'El'}]},bodyTypes:{nodes:[{databaseId:11,name:'SUV'}]}});
  fields(car.bytbil,{carYearmodel:2027,carNoveltyType:'new_car',carPriceSek:String(i.price),carExklMoms:String(i.price*4/5)});
  assert.match(car.bytbil.carModeldescription,new RegExp('^'+name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+' (?:2[.,]95|3[.,]95)% R\\u00c4NTA$'));
  assert(text(parseFragment(car.bytbil.carInfo)).includes('Denna bil \u00e4r en best\u00e4llningsbil'));
  return proof(i.dealerFile,2027,JSON.stringify({post:car.databaseId,carModeldescription:car.bytbil.carModeldescription,
    carYearmodel:car.bytbil.carYearmodel,carPriceSek:car.bytbil.carPriceSek,fuelType:'El'}));
}

export function review(files, sourceReceipts, capturedAt) {
  const proof = (file,value,quote) => ({value,quote,source_url:URLS[file],source_hash:sourceReceipts[file].sha256});
  const doc = page(files['model.html'],MODEL);
  assert.deepEqual(tag(doc,'h1').map(text),['GLB Elektrisk']);
  const packaged = ssr(doc);
  fields(packaged.vehicle,{typeClass:'X244',modelName:'GLB',productType:'CAR',electrical:true,baumuster:'2446131',
    fcisVehicleId:'2446131_SE3-807_057',vehicleName:'GLB 250+ Advanced Edition'});
  fields(packaged.initialPrice,{currency:'SEK',configurationPrice:619000,startingPrice:619000});
  assert.equal(packaged.context.currentVehicleId,packaged.vehicle.initialVehicleId);
  const age = Date.parse(capturedAt) - Date.parse(packaged.fetchedAt);
  assert(Number.isFinite(age) && age >= -60000 && age <= 86_400_000,'Stale manufacturer factory response');
  const style = one(packaged.styles.filter(x=>x.id==='X244__MERCEDES_BENZ__PROGRESSIVE' || x.name==='Progressive'),
    'Expected one Progressive factory selection');
  assert.equal(style.vehicleName,'GLB 250+ Advanced Edition');
  const selected = [packaged.vehicle.initialVehicleId,style.featuredKeyFactsInformation.vehicleId];
  const data = packaged.technicalDataSheet;
  assert.deepEqual(Object.keys(data.models).sort(),identity.map(x=>x.code).sort(),'Do not widen scope to a new motor');
  assert.match(data.footnotes['1'],/WLTP/);
  assert.match(data.footnotes['1'],/Samtliga utsl\u00e4ppsv\u00e4rden g\u00e4ller bil i grundversion\./);
  const structured = one(tag(doc,'script').filter(n=>attr(n,'type')==='application/ld+json')
    .map(s=>JSON.parse(rawScript(s))).filter(o=>o?.['@id']===MODEL+'/#car'),'Expected the exact vehicle ProductGroup');
  fields(structured,{name:'GLB Elektrisk',model:'X244',bodyType:'SUV',url:MODEL});
  const prices = campaign(page(files['prices.html'],URLS['prices.html']));
  const table = one(tag(doc,'table').filter(t=>text(t).includes('Bagageutrymmesvolym') && text(t).includes('GLB 250+')),
    'Require a two-motor rendered technical table');
  const grid = tag(table,'tr').map(tr=>tr.childNodes.filter(n=>['td','th'].includes(n.tagName)).map(text));
  assert.deepEqual(grid[0],['',...identity.map(i=>i.motor)]);
  const authDoc = text(parse(files['appointment.html'].toString('utf8')));
  assert.match(authDoc,/H\u00f6glunds Bil/i,'Manufacturer appointment identity changed');
  const authorization = 'Vi \u00e4r en fullserviceanl\u00e4ggning som \u00e4r auktoriserad \u00e5terf\u00f6rs\u00e4ljare av Mercedes och Mazda.';
  assert(text(parse(files['dealer.html'].toString('utf8'))).includes(authorization),'Current dealer authorization missing');
  const launch = parse(files['launch.html'].toString('utf8'));
  assert.match(one(tag(launch,'h1'),'Expected exact importer launch release').childNodes.map(text).join(' '),
    /^Nya eldrivna Mercedes-Benz GLB visad\./);
  const photoCandidates = [...new Set(tag(launch,'a').map(n=>attr(n,'href'))
    .filter(u=>/^https:\/\/www\.mynewsdesk\.com\/se\/mercedes-benz-sverige\/images\/nya-mercedes-benz-glb-2026-\d+$/.test(u ?? '')))];
  assert(photoCandidates.length>0,'Missing importer-linked GLB photo candidates');
  const variants = identity.map((i,index) => {
    const name = i.motor+' Advanced Edition', candidate = data.models[i.code], column = index+1;
    assert.match(selected[index],new RegExp('^sv_SE__'+i.code+'__'));
    assert.match(selected[index],/(?:^|_)MJ-807(?:_|$)/);
    fields(candidate,{label:i.motor,filter:{'technicalInformation.engine.fuelTypeFilterGroup':'Electric'}});
    const values = candidate.technicalValueGroups.flatMap(group=>group.technicalValues);
    function cell(key,label,expected,footnotes = []) {
      const row=one(values.filter(r=>r.id==='technicalInformation.'+key),'Unique named supplier field: '+key);
      fields(row,{label,footnotes});
      assert.equal(normalize(row.value),expected);
      assert.equal(one(grid.filter(r=>r[0]===label),'Exact rendered field: '+label)[column],expected);
      return i.motor+' | '+label+' | '+expected;
    }
    cell('engine.fuelType','Br\u00e4nsletyp','Electric');
    cell('engine.enginePerformance','Motoreffekt',i.hp);
    const add = (value,key,label,expected,notes) => proof('model.html',value,cell(key,label,expected,notes));
    const offer = one(structured.hasVariant.filter(v=>v.name==='Mercedes-Benz '+name),'Require the exact Advanced Edition offer');
    assert.equal(offer.vehicleConfiguration,'Mercedes-Benz '+name+', '+i.swedishDrive+', 5 Sittplatser, 5 D\u00f6rrar, SUV');
    fields(offer.offers,{'@type':'AggregateOffer',lowPrice:i.price,priceCurrency:'SEK'});
    const priceQuote = name+' fr\u00e5n '+new Intl.NumberFormat('sv-SE').format(i.price).replace(/\u00a0/g,' ')+' kr';
    assert(prices.includes(priceQuote),'Current cash starting price lacks independent manufacturer publication');
    const confirmations = dealerOffer(files[i.dealerFile],i,proof);
    return {name,model_year:2027,market:'SE',manufacturer_code:i.code,model_year_marker:'MJ-807',
      configuration_id:selected[index],manufacturer_body:'X244',body_type:'SUV',fuel_type:'BEV',
      price_evidence:{...proof('prices.html',i.price,priceQuote),price_type:'manufacturer_from',price_valid_until:null,
        model_offer_evidence:proof('model.html',i.price,JSON.stringify({name:offer.name,lowPrice:i.price,priceCurrency:'SEK'}))},
      year_corroboration:confirmations,
      technical_facts:{
        wltp_range_km:add(i.range,'wltp.range.total.all.individual','Elektrisk r\u00e4ckvidd, blandad k\xf6rning',i.range+' km',['1']),
        wltp_consumption_kwh_100km:add(i.consumption,'wltp.consumption.total.primaryGear.individual','F\xf6rbrukning blandad k\xf6rning',
          String(i.consumption).replace('.',',')+' kWh/100km',['1']),
        battery_kwh:{...add(85,'engine.energyContent','Anv\xe4ndbart energiinneh\xe5ll batteri','85 kWh'),basis:'usable'},
        dc_charge_kw:add(320,'engine.chargingCapacityDC','Maximal laddeffekt DC','320 kW'),
        ac_charge_kw:add(11,'engine.chargingCapacityAC','Maximal laddeffekt AC','11 kW'),
        boot_liters:add(540,'dimensions.bootCapacityMin','Bagageutrymmesvolym','540 l'),
        tow_kg:{...add(i.tow,'weights.maximumTrailingLoadCombined','Till\xe5ten sl\xe4pvagnsvikt (bromsad sl\xe4pvagn vid 12 %)',
          index===0?'750 kg (1 500 kg)':'750 kg (2 000 kg)'),requires_towing_equipment:true},
        seats:add(5,'seats','Sittplatser','5'),
        drivetrain:add(i.drive,'engine.propulsion.name','Drivlina',i.swedishDrive),
      }};
  });
  return {status:'private_glb_x244_source_review',model:'GLB Electric',brand:'Mercedes-Benz',variants,
    wltp_qualification:data.footnotes['1'], photo_candidates:photoCandidates,
    dealer_authorization:{primary_url:URLS['appointment.html'],...proof('dealer.html',true,authorization)},
    held:['confirm the Mobility Sweden BEV alias against the live canonical draft','select and review exact exterior press image'],
    publication_approved:false,database_writes:0,paid_calls:0};
}

function marketReview(root, folder, files) {
  const doc = parse(files['market.html'].toString('utf8'));
  const links = tag(doc,'a').map(link=>attr(link,'href')).filter(Boolean);
  assert(links.some(href=>URL.canParse(href,MARKET_URLS['market.html']) &&
    new URL(href,MARKET_URLS['market.html']).href===MARKET_URLS['market.xlsx']), 'Exact official October workbook link required');
  assert.equal(sha(files['market.xlsx']), '1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6',
    'October workbook changed; review before using a new market receipt');
  const py = `import json, sys
sys.path.insert(0,"scripts")
from pathlib import Path
from import_mobility_sweden import parse_elbil_ranking
models, _ = parse_elbil_ranking(Path(sys.argv[1]), sys.argv[2])
row, = [m for m in models if (m.brand_raw,m.model_raw,m.fuel_type_raw)==("MERCEDES","GLB","EL")]
assert not row.needs_mapping and not row.model_group
print(json.dumps({key: getattr(row,key) for key in json.loads(sys.argv[3])}))`;
  const row = JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs','-c',py,join(folder,'market.xlsx'),
    MARKET_URLS['market.xlsx'],JSON.stringify(Object.keys(GLB_MARKET))],{cwd:root,windowsHide:true,timeout:90000}));
  assert.deepEqual(row,GLB_MARKET);
  return {sheet:'Elbil ranking',row};
}

const robotsFor = urls => Object.fromEntries([...new Set(Object.values(urls).map(url=>new URL(url).origin))]
  .map((origin,i)=>['robots-'+i+'.txt',origin+'/robots.txt']));
const request = async (url, type) => {
  const r = await fetch(url,{redirect:'error',headers:{'User-Agent':agent,'Accept-Language':'sv-SE,sv;q=0.9'},
    signal:AbortSignal.timeout(15000)});
  assert.equal(r.status,200,'Expected reachable source: '+url);
  assert.equal(r.url,url);
  assert.equal(r.headers.get('content-type')?.split(';')[0],type);
  assert.notEqual(r.headers.get('tdm-reservation'),'1');
  let size=0; const chunks=[];
  for await (const bytes of r.body) {
    size+=bytes.length;
    assert(size <= limit,'GLB source exceeds size limit');
    chunks.push(bytes);
  }
  const raw=Buffer.concat(chunks);
  if(type==='text/html') assert(!tag(parse(raw.toString('utf8')),'meta')
    .some(n=>attr(n,'name')?.toLowerCase()==='tdm-reservation'&&attr(n,'content')?.trim()==='1'));
  return raw;
};
function verifyRobots(root, files, robotNames, checkUrls) {
  const check = 'import json,sys; from urllib.robotparser import RobotFileParser; p=json.load(sys.stdin); r=RobotFileParser(); r.parse(p["robots"].splitlines()); assert all(r.can_fetch(p["agent"],u) for u in p["urls"])';
  for(const [name,url] of Object.entries(robotNames)){
    const origin=new URL(url).origin;
    execFileSync(process.execPath,['scripts/run_python.mjs','-c',check],{cwd:root,windowsHide:true,timeout:20000,
      input:JSON.stringify({agent,robots:files[name].toString('utf8'),urls:checkUrls.filter(u=>new URL(u).origin===origin)})});
  }
}
async function main() {
  const {values} = parseArgs({options:{capture:{type:'boolean'},replay:{type:'string'},'include-market':{type:'boolean'}}});
  assert(Boolean(values.capture)!==Boolean(values.replay));
  assert(!values['include-market']||values.capture,'Use --include-market with --capture');
  const root=await realpath(fileURLToPath(new URL('../',import.meta.url)));
  const out=join(root,'data','local','release-data');
  assert.equal(await realpath(out),out);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(out));
  const files={};
  let capturedAt, folder, saved;
  const read=async (name, allowEmpty=false)=>{
    const file=join(folder,name), info=await stat(file);
    assert.equal(await realpath(file),file);
    assert(info.isFile()&&(allowEmpty||info.size>0)&&info.size<=limit,'Invalid captured source: '+name);
    return readFile(file);
  };
  if(values.replay){
    folder=resolve(values.replay);
    assert.equal(await realpath(folder),folder);
    assert.equal(dirname(folder),out);
    assert.match(basename(folder),/^mercedes-glb-x244-review-[a-z0-9]+$/i);
    saved=JSON.parse(await read('review.json'));
  }
  const withMarket=values['include-market'] || Boolean(saved?.market_index);
  const sources=withMarket?{...URLS,...MARKET_URLS}:URLS;
  const robotNames=robotsFor(sources),known={...robotNames,...sources};
  if(values.capture){
    for(const [name,url] of Object.entries(robotNames))files[name]=await request(url,'text/plain');
    verifyRobots(root,files,robotNames,Object.values(sources));
    for(const [name,url] of Object.entries(sources))files[name]=await request(url,name.endsWith('.xlsx')?
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'text/html');
    capturedAt=new Date().toISOString();
  }else{
    for(const [name,url] of Object.entries(known))files[name]=await read(name,url===new URL('/robots.txt',MARKET_URLS['market.html']).href);
    verifyRobots(root,files,robotNames,Object.values(sources));
    capturedAt=saved.captured_at;
  }
  assert.equal(new Date(capturedAt).toISOString(),capturedAt);
  const receipts=Object.fromEntries(Object.entries(known).map(([name,url])=>[name,{url,sha256:sha(files[name]),http_status:200}]));
  const result={...review(files,receipts,capturedAt),sources:receipts,captured_at:capturedAt};
  if(!saved){
    folder=await mkdtemp(join(out,prefix));
    for(const [name,body] of Object.entries(files))await writeFile(join(folder,name),body,{flag:'wx'});
  }
  if(withMarket) {
    assert.equal(sha(await read('market.xlsx')),receipts['market.xlsx'].sha256);
    result.market_index=marketReview(root,folder,files);
  }
  if(saved)assert.deepEqual(result,saved,'Manufacturer or review bytes changed');
  else await writeFile(join(folder,'review.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:result.status,folder,variants:result.variants.length,
    fields:result.variants.reduce((n,variant)=>n+Object.keys(variant.technical_facts).length,0),
    photo_candidates:result.photo_candidates.length,publication_approved:false,database_writes:0}));
}

if (process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) await main().catch(err=>{
  console.error(JSON.stringify({status:'held',reason:err.message.split('\n')[0],location:err.stack?.split('\n').find(l=>l.includes('mercedes_glb_review.mjs')),database_writes:0}));
  process.exitCode=1;
});
