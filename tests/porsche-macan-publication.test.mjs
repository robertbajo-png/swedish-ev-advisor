import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {macanIntakeFromReplay,policy} from '../scripts/porsche_macan_publication.mjs';
import {applyNewModelPlan,publicationHash,validateNewModelImage,validateNewModelIntake} from '../scripts/new_model_publication.mjs';
import {buildImagePlan,selectImageRegistryForPublic} from '../scripts/model_image_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';

const now=new Date('2026-11-23T00:00:00Z'),fetched_at=now.toISOString();
const base='https://configurator.porsche.com/sv-SE/mode/model/XABAA1';
const comparison='https://compare.porsche.com/sv-SE?model-series=macan';
function fixture(){
  const receipts=Object.fromEntries(Object.entries({base,technical:base+'/specifications?tab=technical-data',
    equipment:base+'/specifications?tab=standard-equipment',comparison}).map(([key,source_url],i)=>
    [key,{source_url,content_hash:String(i).repeat(64),fetched_at,http_status:200}]));
  const facts={wltp_range_km:[642,'technical'],wltp_consumption_kwh_100km:[16.7,'technical'],battery_kwh:[100,'technical'],
    dc_charge_kw:[270,'technical'],ac_charge_kw:[11,'equipment'],boot_liters:[518,'technical'],tow_kg:[2000,'technical'],
    seats:[5,'equipment'],drivetrain:['RWD','equipment'],price_sek:[970000,'comparison']};
  return {status:'macan_release_intake_verified_private',model:'Porsche Macan',variant:'Electric RWD MY27',
    manufacturer_identity:'SE|MY27|XABAA1|RWD|5|20',price_type:'manufacturer_from',price_valid_until:null,publication_approved:false,
    production_writes:0,all_sources_within_15_minutes:true,spec_sources:receipts,
    field_evidence:Object.fromEntries(Object.entries(facts).map(([field,[value,key]])=>[field,
      {value,quote:'Test evidence '+field,fetched_at,source_url:receipts[key].source_url,source_hash:receipts[key].content_hash}])),
    qualifications:{battery:'gross',range:'combined WLTP, standard 20-inch wheels',cargo:'rear cargo to the top of the rear seat backrest',
      towing:'braked, with the optional tow bar',ac:'standard on-board charger'},
    market_discovery:{brand_raw:'PORSCHE',model_raw:'MACAN',fuel_type_raw:'EL',normalized_brand:'porsche',normalized_model:'macan',
      source_url:'https://mobilitysweden.se/test.xlsx',source_name:'Mobility Sweden',last_seen_month:'2026-10-01',
      registrations_last_month:43,registrations_ytd:367,needs_mapping:false},
    market_sources:{'market.xlsx':{final_url:'https://mobilitysweden.se/test.xlsx',status:'reachable',http_status:200,fetched_at,
      content_hash:'1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6'}},
    photo_candidate:{status:'verified_model_photo_private_only',asset_id:'pmdb:9458fb1b-7f83-4267-ba53-8d6321764b0a',credit:'Porsche AG',
      source_url:'https://newsroom.porsche.com/de/pressemappen/der-neue-porsche-macan.html',sha256:policy.imageHash,
      catalog_use_confirmed:false,width:6000,height:4000,sources:{'photo.jpg':{fetched_at}}}};
}

test('exact Macan packet binds the nine facts and manufacturer starting price to separate receipts',()=>{
  const {intake,image}=macanIntakeFromReplay(fixture(),'not-a-real-photo-folder');
  assert.equal(validateNewModelIntake(intake,now),policy);
  assert.equal(intake.drafts[0].price_evidence.source_url,comparison);
  assert.equal(intake.drafts[0].price_evidence.corroboration.source_url,base);
  assert.equal(intake.drafts[0].price_evidence.price_type,'manufacturer_from');
  assert.equal(Object.keys(intake.drafts[0].facts).length,9);
  assert.match(image.asset_url,/^\/private-rehearsal\//);
});

test('reject changed identity, price, source or editorial scope',()=>{
  for(const mutate of [
    r=>{r.manufacturer_identity='SE|MY27|different|AWD|5|20';},
    r=>{r.field_evidence.price_sek.value=980000;},
    r=>{r.field_evidence.wltp_range_km.source_url=r.market_discovery.source_url;},
    r=>{r.photo_candidate.catalog_use_confirmed=true;},
    r=>{r.all_sources_within_15_minutes=false;},
  ]){
    const r=fixture();mutate(r);
    assert.throws(()=>macanIntakeFromReplay(r,'not-a-real-photo-folder'));
  }
});

test('do not accept a public asset route or missing private JPEG',()=>{
  const {intake,image}=macanIntakeFromReplay(fixture(),'not-a-real-photo-folder');
  assert.throws(()=>validateNewModelImage([intake.model],intake,{...image,asset_url:'/media/vehicles/example.jpg'}),/asset_url/);
  assert.throws(()=>validateNewModelImage([intake.model],intake,image),{code:'ENOENT'});
});

test('Macan rehearsal refuses non-PGlite connections before any query',async()=>{
  const plan=macanIntakeFromReplay(fixture(),'not-a-real-photo-folder');
  await assert.rejects(applyNewModelPlan({query:()=>assert.fail('Attempted a remote query')},plan,publicationHash(plan),now),
    /local PGlite/);
});

test('accept only the licensed electric Macan photo and never as proof of a trim',()=>{
  const proof=JSON.parse(readFileSync(new URL('../src/porsche-macan-photo-policy.json',import.meta.url),'utf8'));
  const asset={...proof,reviewed_at:'2026-11-23',status:'documented'};
  const model={id:'macan-draft',brand:'Porsche',model:'Macan',validation_status:'draft'};
  const registry=entry=>({schema_version:1,assets:[entry]});
  assert.deepEqual(selectImageRegistryForPublic([],registry(asset)).assets,[]);
  assert.equal(buildImagePlan([model],[model],registry(asset))[0].image_url,proof.asset_url);
  assert.equal(specQualifications({...model,image_url:proof.asset_url}).imageNotice,proof.model_image_notice);
  assert.notEqual(specQualifications({...model,model:'Cayenne',image_url:proof.asset_url}).imageNotice,proof.model_image_notice);
  for(const patch of [{credit:'other'}, {content_sha256:'0'.repeat(64)}, {variant_names:['Electric RWD MY27']}])
    assert.throws(()=>buildImagePlan([model],[model],registry({...asset,...patch})),/Macan/);
});
