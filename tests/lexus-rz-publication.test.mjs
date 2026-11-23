import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {applyLexusRelease,applyNewModelPlan,publicationHash,validateNewModelImage,validateNewModelIntake} from '../scripts/new_model_publication.mjs';
import {CAR_ID,facts,lexusIntakeFromReplay,policy,VARIANT} from '../scripts/lexus_rz_publication.mjs';
import {lexusReleaseHash,proveLexusRelease} from '../scripts/lexus_rz_release_scope.mjs';
import {selectImageRegistryForPublic} from '../scripts/model_image_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';
import {displayModelName,vehicleSlug} from '../src/vehicle-names.js';

const now=new Date('2026-11-23T05:00:00Z');
const pdf='https://www.lexus.se/content/dam/lexus/nmsc/sweden/documents/pris-och-utrustningslista/LSW_Pricelist_RZ_210x271_Q1-26_260318.pdf';
const api='https://dxp-webcarconfig.lexus-europe.com/v1/api/data/';
const source=(final_url,sha,country='SE',language='sv')=>({final_url,content_hash:sha.repeat(64),
  fetched_at:now.toISOString(),http_status:200,status:'reachable',country,language,source_authority:'manufacturer'});

function fixture(){
  const sources=[source(policy.primaryUrl,'1'),source(pdf,'2'),source(api+'se/sv','3'),source(api+'dk/da','4','DK','da')];
  const marketSource=source('https://mobilitysweden.se/test.xlsx','5');
  marketSource.content_hash='1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6';
  const proof=(i,value)=>({value,source_url:sources[i].final_url,source_hash:sources[i].content_hash,quote:'Exact source quote'});
  return {status:'private_current_lexus_executive_intake',identity:[VARIANT,CAR_ID,'XEBM20L-AWDCSW','AB'],
    publication_approved:false,production_writes:0,sources,
    market:{source:marketSource,row:{brand_raw:'LEXUS',model_raw:'RZ',fuel_type_raw:'EL',normalized_brand:'lexus',
      normalized_model:'rz',source_name:'Mobility Sweden',last_seen_month:'2026-10-01',registrations_last_month:50,
      registrations_ytd:439,needs_mapping:false,model_group:null,source_url:marketSource.final_url}},
    field_evidence:Object.fromEntries(Object.entries(facts).map(([field,value])=>[field,
      proof(field==='dc_charge_kw'?3:['ac_charge_kw','tow_kg'].includes(field)?2:0,value)])),
    price_evidence:{...proof(0,599000),price_type:'manufacturer_from',price_valid_until:null,corroboration:proof(1,599000)},
    source_decisions:{model_year:'not asserted; current Swedish configuration identity only',
      swedish_manual:{source_url:'https://customerportal.tweddle-aws.eu/content?id=16f0e745-02b7-40d0-a66c-119fa5d245f7&topicId=6ffb4817-75e3-46e8-932b-8ab5909d2c79&publicationType=OM',
        source_hash:'a936c7038ddd8626138e40036736498e50802c2ea7a1fa370d30ece3968e7689',
        document_id:'PZ471-9AS86-SV',page:748,scope:'max braked, with towing equipment'},dc_corroboration:{market:'NO'}},
  };
}

test('stage only the current Swedish 350e Executive and approved 350e model photo',()=>{
  const {intake,image}=lexusIntakeFromReplay(fixture());
  assert.equal(validateNewModelIntake(intake,now),policy);
  const [draft]=intake.drafts;
  assert.equal(draft.facts.wltp_range_km,567);
  assert.deepEqual(draft.identity_evidence,{market:'SE',car_id:CAR_ID,type_code:'XEBM20L-AWDCSW',suffix:'AB',wheels_inches:18});
  assert.equal(draft.price_evidence.source_url,policy.primaryUrl);
  assert.equal(draft.price_evidence.corroboration.source_url,pdf);
  const model={...intake.model,id:'lexus-draft',validation_status:'draft'};
  assert.deepEqual(validateNewModelImage([model],intake,image),image);
  assert.deepEqual(selectImageRegistryForPublic([],{schema_version:1,assets:[image]}).assets,[]);
  assert.throws(()=>validateNewModelImage([model],intake,{...image,variant_names:[VARIANT]}),/Version L/);
});

test('reject configuration, price and field or corroboration drift',()=>{
  for(const change of [
    p=>{p.identity[3]='PB';},
    p=>{p.field_evidence.wltp_range_km.value=590;},
    p=>{p.field_evidence.dc_charge_kw.source_url=p.sources[2].final_url;},
    p=>{p.field_evidence.tow_kg.value=1500;},
    p=>{p.price_evidence.value=662000;},
    p=>{p.price_evidence.corroboration.source_hash='0'.repeat(64);},
    p=>{p.source_decisions.swedish_manual.page=749;},
    p=>{p.market.row.registrations_last_month=51;},
  ]){
    const p=fixture();change(p);
    assert.throws(()=>lexusIntakeFromReplay(p),/Lexus RZ/);
  }
  const {intake}=lexusIntakeFromReplay(fixture());
  intake.drafts[0].identity_evidence={...intake.drafts[0].identity_evidence,model_year:2026};
  assert.throws(()=>validateNewModelIntake(intake,now),/Do not assert a Lexus model year/);
});

test('keep Lexus isolated until the distinct reviewed release and fresh evidence match',async()=>{
  const plan={adapter:policy.adapter,...lexusIntakeFromReplay(fixture()),targets:[]};
  const noAccess={query:()=>assert.fail('Unexpected remote query')};
  await assert.rejects(applyNewModelPlan(noAccess,plan,publicationHash(plan),now),/local PGlite/);
  const scope={status:'lexus_release_scope_private',publication_approved:false,plan,plan_sha256:publicationHash(plan)};
  const target={commit:'1'.repeat(40),reader_sha256:'2'.repeat(64)};
  const seal=lexusReleaseHash(scope,target);
  await assert.rejects(applyLexusRelease(noAccess,plan,scope,target,'9'.repeat(64),now),/exact reviewed Lexus RZ/);
  assert.throws(()=>proveLexusRelease(scope,plan,target,seal,now),/Capture official sources again/);
  const fresh=structuredClone(plan),later=new Date(+now+10000);
  for(const s of [...fresh.intake.sources,fresh.intake.market.source])s.fetched_at=later.toISOString();
  assert.doesNotThrow(()=>proveLexusRelease(scope,fresh,target,seal,later));
});

test('display the exact source qualifications and preserve the stable Lexus route',()=>{
  const image=JSON.parse(readFileSync(new URL('../src/lexus-rz-photo-policy.json',import.meta.url),'utf8'));
  const row={brand:'Lexus',model:'Rz',variant_name:VARIANT,source_url:policy.primaryUrl,image_url:image.asset_url};
  assert.equal(displayModelName(row.brand,row.model,VARIANT),'RZ 350e Executive');
  assert.equal(vehicleSlug(row.brand,row.model,VARIANT),'lexus-rz-350e-executive');
  const qualifications=specQualifications(row);
  assert.equal(qualifications.imageNotice,image.model_image_notice);
  assert.match(qualifications.consumptionNote,/77 kWh .*bruttokapacitet/);
  assert.match(qualifications.practicalNote,/750 kg avser bromsat/);
  assert.equal(specQualifications({...row,variant_name:'550e F SPORT'}).practicalNote,null);
});
