import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ADAPTER = 'renault_4_evolution_sweden_local_v1';
export const MODEL = {brand: 'Renault', model: '4', normalized_brand: 'renault', normalized_model: '4', body_type: 'SUV'};
const name = 'Evolution EV52';
const versionId = 'cd7efc7a-2549-4f9f-aa73-7c0d3a70dbad';
const base = 'https://www.renault.se/personbilar/elbilar/r4-e-tech-electric';
const versions = base + '/versioner-och-priser';
const priceUrl = 'https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/renaultsesite/cardocuments/prislista-renault-4-e-tech-electric.pdf';
const dealer = 'https://rnautomotive.se/bilar/261900/pc-nc-renault-4-e-tech-2027';
const locator = 'https://www.renault.se/om-oss/aterforsaljare';
const press = 'https://renault.mynewsdesk.com/pressreleases/renault-4-e-tech-electric-nu-till-foersaeljning-i-sverige-3401914';
const imageSource = 'https://renault.mynewsdesk.com/images/r-dam-1606012-punkt-jpg-3309218';
const imageFile = 'renault-4-press-08f8b8956c0a.jpg';
const imageHash = '08f8b8956c0afdfacea4f70aa629210ec3d3a0e62c3ce592a9293a83a1c26c6f';
const receiptHash = '1ad66a4f559d6cc4e02bc0075aac143debbc3e3173a4d64e9e3ddaf92b00c475';
const root = fileURLToPath(new URL('..', import.meta.url));
const sha = b => createHash('sha256').update(b).digest('hex');
const qualifiedFacts = {wltp_range_km:407,wltp_consumption_kwh_100km:15.2,battery_kwh:52,dc_charge_kw:100,
  ac_charge_kw:11,boot_liters:420,tow_kg:750,seats:5,drivetrain:'FWD'};
const sources = new Map([
  [versions, ['versions.html', 'manufacturer_model_page']], [priceUrl, ['prices.pdf', 'price_list_pdf']],
  [press, ['press.html', 'importer_page']], [locator, ['locator.html', 'manufacturer_model_page']],
  [dealer, ['evolution-stock.html', 'authorized_dealer_stock_page']],
]);
const factsSource = {...Object.fromEntries(Object.keys(qualifiedFacts).map(key => [key,priceUrl])),
  wltp_range_km:dealer,wltp_consumption_kwh_100km:dealer,drivetrain:dealer};

function readPhoto(name) {
  const base = join(realpathSync(root), 'data', 'local', 'release-data', 'renault-4-press-mmt5psl3');
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(base));
  const path = join(base,name);
  assert.equal(realpathSync(path),path);
  const bytes = readFileSync(path);
  assert(bytes.length > 0 && bytes.length < 12_000_000);
  return bytes;
}

export function readEvolutionImage() {
  const bytes = readPhoto('4-mynewsdesk-3309218.json');
  assert.equal(sha(bytes),receiptHash);
  const {title, review_filename, asset_url, original_url, width, height, original_width, original_height,
    collected_at, status, ...receipt} = JSON.parse(bytes);
  assert.equal(title,'R-DAM_1606012.jpg');
  assert.equal(review_filename,imageFile);
  assert.equal(receipt.model_key,'renault|4');
  assert.equal(receipt.source_url,imageSource);
  assert.equal(receipt.content_sha256,imageHash);
  assert.equal(sha(readPhoto(receipt.metadata_sha256 + '.html')),receipt.metadata_sha256);
  assert.equal(sha(readPhoto(imageFile)),imageHash);
  return {...receipt,status:'documented',reviewed_at:collected_at.slice(0,10),asset_url:'/media/vehicles/'+imageFile,
    original_url,downloaded_from:asset_url,usage_scope:'independent_vehicle_editorial',
    prohibited_uses:['advertising','commercial_promotion','endorsement'],
    model_image_notice:'Pressbild. Utrustning kan skilja mellan versioner.'};
}

export function readEvolutionCapture(path) {
  const r = JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs','scripts/renault_4_evolution_candidate.py',
    '--replay',resolve(path),'--emit'], {cwd:root,encoding:'utf8',timeout:120000,maxBuffer:300000,windowsHide:true}));
  return evolutionIntakeFromReplay(r);
}

export function evolutionIntakeFromReplay(r) {
  assert.equal(r.status,'private_evolution_candidate');
  assert.equal(r.publication_approved,false);
  const named = (url,type,fetched_at,content_hash) => ({final_url:url,source_type:type,status:'reachable',http_status:200,
    source_name:url===dealer?'RN Automotive Tagene':'Renault Sverige',country:'SE',language:'sv',shared:url===locator,
    source_authority:url===dealer?'authorized_dealer':'manufacturer',authorization_evidence_url:url===dealer?locator:null,
    fetched_at,content_hash});
  const details = [...sources].map(([url,[key,type]]) => {
    const s = r.sources[key];assert.equal(s.url,url);return named(url,type,r.fetched_at[key],s.sha256);
  });
  const source = r.sources['market.xlsx'];
  const field_evidence = Object.fromEntries(Object.entries(r.fields).map(([key,p])=>[key,{...p,variant_name:name}]));
  const intake = {adapter:ADAPTER,model:MODEL,sources:details,model_evidence:r.body,
    market:{source:{...named(source.url,'mobility_sweden_export',r.fetched_at['market.xlsx'],source.sha256),source_name:'Mobility Sweden'},
      row:{brand_raw:'RENAULT',model_raw:'4',fuel_type_raw:'EL',normalized_brand:'renault',normalized_model:'4',
        last_seen_month:r.market.report_month,registrations_last_month:r.market.value,registrations_ytd:r.market.registrations_ytd},
      sheet:'Elbil ranking'},
    drafts:[{variant_name:name,manufacturer_identity:versionId+'/EV52/MY27',identity_evidence:{...r.identity,appointment:r.appointment},
      extraction_confidence:0.99,facts:Object.fromEntries(Object.entries(field_evidence).map(([key,p])=>[key,p.value])),field_evidence,
      price_evidence:{...r.price,price_valid_until:null}}],
    source_decisions:r.alternatives};
  return {intake,now:new Date(r.captured_at)};
}

function validateIntake(intake) {
  assert.deepEqual(intake.model,MODEL);
  assert.equal(intake.sources.length,sources.size);
  for (const source of intake.sources) {
    assert.equal(source.source_type,sources.get(source.final_url)?.[1]);
    assert.equal(source.shared,source.final_url===locator);
    assert.equal(source.source_authority,source.final_url===dealer?'authorized_dealer':'manufacturer');
    assert.equal(source.authorization_evidence_url,source.final_url===dealer?locator:null);
  }
  assert.equal(intake.drafts.length,1);
  const [draft] = intake.drafts;
  assert.equal(draft.variant_name,name);
  assert.equal(draft.manufacturer_identity,versionId+'/EV52/MY27');
  assert.deepEqual(draft.facts,qualifiedFacts);
  const proof = (p,url,value) => {
    assert.equal(p?.value,value);
    assert.equal(p.source_url,url);
    assert.equal(p.source_hash,intake.sources.find(s=>s.final_url===url)?.content_hash);
    assert(typeof p.quote==='string' && p.quote.trim().length > 5);
  };
  for (const [field,url] of Object.entries(factsSource)) proof(draft.field_evidence[field],url,qualifiedFacts[field]);
  proof(draft.field_evidence.wltp_range_km.corroboration,versions,407);
  proof(draft.field_evidence.dc_charge_kw.corroboration,dealer,100);
  proof(draft.identity_evidence.appointment,locator,'RN Automotive Tagene');
  proof(draft.identity_evidence.model_year,dealer,2027);
  proof(intake.model_evidence,press,'crossover');
  proof(draft.price_evidence,priceUrl,414900);
  proof(draft.price_evidence.manufacturer_cash_crosscheck,versions,414900);
  proof(draft.price_evidence.dealer_offer,dealer,414900);
  assert.equal(draft.price_evidence.price_type,'list_price');
  assert.equal(draft.price_evidence.price_valid_until,null);
  assert.equal(draft.price_evidence.dealer_offer.price_type,'dealer_offer');
  const {source,row} = intake.market;
  assert.equal(new URL(source.final_url).origin,'https://mobilitysweden.se');
  assert.match(decodeURIComponent(new URL(source.final_url).pathname),/\/M\u00e5nadsrapport Nyregistreringar okt 2026\.xlsx$/);
  assert.deepEqual(row,{brand_raw:'RENAULT',model_raw:'4',fuel_type_raw:'EL',normalized_brand:'renault',normalized_model:'4',
    last_seen_month:'2026-10-01',registrations_last_month:20,registrations_ytd:430});
}

export const policy = {adapter:ADAPTER,validateIntake,primaryUrl:priceUrl,imageKey:'renault|4',imageHash,
  aliasRule:'mobility_sweden_exact_raw_name',maxVariants:1,mixedSources:true,localOnly:true,
  readPrivateImage(image) {
    assert.deepEqual(image,readEvolutionImage());
    return readPhoto(imageFile);
  }, verifyPublic(rows,plan) {
    assert.equal(rows.length,1);
    const [r] = rows;
    for (const [field,value] of Object.entries(qualifiedFacts)) assert.equal(r[field],value,field);
    assert.equal(r.variant_name,name);
    assert.equal(r.price_sek,414900);
    assert.equal(r.price_type,'list_price');
    assert.equal(r.price_source_url,priceUrl);
    assert.equal(r.image_url,plan.image.asset_url);
    assert.equal(r.image_source_url,imageSource);
    assert.equal(r.available_confirmed,plan.expected_model.available_confirmed);
  }};
