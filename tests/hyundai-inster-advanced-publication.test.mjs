import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {ADAPTER,MODEL,MATERIAL,VARIANT,facts,policy} from '../scripts/hyundai_inster_advanced_publication.mjs';
import {newModelAdapter} from '../scripts/new_model_adapters.mjs';
import {buildImagePlan,selectImageRegistryForPublic} from '../scripts/model_image_sync.mjs';
import {insterReleaseHash,proveInsterRelease} from '../scripts/hyundai_inster_advanced_release_scope.mjs';
import {applyInsterRelease} from '../scripts/new_model_publication.mjs';

function exact(){
  const config=policy.primaryUrl,stock='https://lager.hyundai.se/model/INSTER?customer=private';
  const dealer='https://hedinautomotive.se/bilar/kop-bil/258182/pc-nc-hyundai-inster-2027';
  const locator='https://www.hyundai.com/se/sv/tjanster/online-tjanster/hitta-aterforsaljare/hitta-agent.html';
  const manual='https://ownersmanual.hyundai.com/full_webhelp/AXEV/2027/sv_SE/idee195341dda.html';
  return {adapter:ADAPTER,model:MODEL,market:{row:{...policy.scopedDiscovery.market}},
    sources:[config,stock,'https://www.hyundai.com/se/sv/bilar/inster/design.html',manual,dealer,locator].map(final_url=>({final_url})),
    drafts:[{variant_name:VARIANT,manufacturer_identity:'SE|MY27|'+MATERIAL+'|FWD|4|17',facts:{...facts},
      identity_evidence:{model_year:2027,manufacturer_code:MATERIAL,wheels_inches:17,tech_package:true},
      price_evidence:{value:377900,price_type:'manufacturer_from',price_valid_until:null,source_url:stock},
      field_evidence:{dc_charge_kw:{factory_read:{operation:'Powertrains',key:'maxChargingPower',url:'https://org-eu-www.hyundai.com/eu/papi'}},
        seats:{source_url:dealer,authorization_evidence_url:locator,quote:'"car_seats":"4"'},tow_kg:{source_url:manual}}}]};
}

test('exact four-seat and decimal variant is registered for local rehearsal only',()=>{
  assert.equal(newModelAdapter(ADAPTER),policy);
  assert.equal(policy.localOnly,true);
  assert.equal(Object.keys(facts).length,9);
  assert.doesNotThrow(()=>policy.validateIntake(exact()));
});

test('reject swapped trim, price, hardware or seat evidence',()=>{
  for(const mutate of [
    d=>{d.identity_evidence.wheels_inches=15;},
    d=>{d.identity_evidence.tech_package=false;},
    d=>{d.facts.dc_charge_kw=85;},
    d=>{d.facts.seats=5;},
    d=>{d.price_evidence.value=354900;},
    d=>{d.price_evidence.value=385400;},
    d=>{d.field_evidence.dc_charge_kw.factory_read.key='evMaxPowerKw';},
    d=>{d.field_evidence.seats.authorization_evidence_url='https://example.test';},
  ]){
    const draft=exact();mutate(draft.drafts[0]);
    assert.throws(()=>policy.validateIntake(draft));
  }
});

test('do not transfer non-electric registration records to Inster',()=>{
  const i=exact();i.market.row.fuel_type_raw='BENSIN';
  assert.throws(()=>policy.validateIntake(i));
  assert.throws(()=>policy.scopedDiscovery.check({market_models:[{id:'elsewhere',canonical_model_id:'inster'}]},
    {id:'inster'},{id:'electric'}),/exact Inster/);
});

test('the shared license does not make the ID. Buzz or a different Inster photo interchangeable',()=>{
  const photo=JSON.parse(readFileSync(new URL('../src/inster-photo-policy.json',import.meta.url),'utf8'));
  const model={...MODEL,id:'inster-draft',validation_status:'draft'};
  const registry=image=>({schema_version:1,assets:[image]});
  const image={...photo,status:'documented',reviewed_at:'2026-11-23'};
  assert.deepEqual(selectImageRegistryForPublic([],registry(image)).assets,[]);
  assert.equal(buildImagePlan([model],[model],registry(image))[0].image_url,photo.asset_url);
  for(const wrong of [{credit:'Wrong credit'},{source_url:'https://commons.wikimedia.org/wiki/File:Inster_Cross.jpg'},
    {variant_names:[VARIANT]}]){
    assert.throws(()=>buildImagePlan([model],[model],registry({...image,...wrong})),/Inster/);
  }
});

test('the release seal binds model, deployed reader and main revision before any database work',async()=>{
  const scope={status:'inster_release_scope_private',publication_approved:false,plan:{adapter:ADAPTER}};
  const target={commit:'a'.repeat(40),reader_sha256:'b'.repeat(64)};
  const seal=insterReleaseHash(scope,target);
  for(const changed of [{...target,commit:'c'.repeat(40)},{...target,reader_sha256:'d'.repeat(64)}]){
    assert.notEqual(insterReleaseHash(scope,changed),seal);
    assert.throws(()=>proveInsterRelease(scope,null,changed,seal,new Date()),/exact reviewed Inster/);
  }
  const noAccess={query(){assert.fail('Invalid seal must not reach the database');}};
  await assert.rejects(applyInsterRelease(noAccess,null,scope,target,'e'.repeat(64)),/exact reviewed Inster/);
});
