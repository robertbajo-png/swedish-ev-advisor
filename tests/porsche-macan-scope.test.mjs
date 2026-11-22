import assert from 'node:assert/strict';
import {test} from 'node:test';
import {MACAN_MODEL,readMacanScope,verifyMacanScope} from '../scripts/porsche_macan_scope.mjs';

const raw = {brand_raw: 'PORSCHE', model_raw: 'MACAN'};
const keys = {normalized_brand: 'porsche', normalized_model: 'macan'};
const incoming = {...raw,...keys,fuel_type_raw:'EL',needs_mapping:false,last_seen_month:'2026-10-01',
  registrations_last_month:43,registrations_ytd:367};
const fixture = () => ({
  models:[{...MACAN_MODEL,id:'model',body_type:null,image_url:null,validation_status:'draft'}],
  aliases:[{...raw,...keys,canonical_model_id:'model',alias_rule:'mobility_sweden_exact_raw_name',
    model_group:null,needs_mapping:false,confidence:'1.0'}],
  market:[{...raw,...keys,id:'market',fuel_type_raw:'EL',source_name:'Mobility Sweden',
    canonical_model_id:null,model_group:null,needs_mapping:false,first_seen_month:'2026-03-01',last_seen_month:'2026-03-01'}],
  months:[{...raw,market_model_id:'market',fuel_type_raw:'EL',county:null,municipality:null,month:'2026-03-01',registrations:32}],
  variants:[],drafts:[],
});

test('Macan BEV is bound to existing draft and the original registration history', ()=>{
  const f=fixture();
  const expected=structuredClone(f);
  f.market.push({...f.market[0],id:'petrol-market',fuel_type_raw:'BENSIN'});
  assert.deepEqual(verifyMacanScope(f,incoming),{expected_model:expected.models[0],expected_alias:expected.aliases[0],
    expected_market:expected.market[0],expected_monthly:expected.months});
  assert.deepEqual(f.months,expected.months);
});

test('reject competing alias, historical wrong fuel, already staged or previously published car', ()=>{
  for (const mutate of [
    f=>f.aliases.push({...f.aliases[0]}),
    f=>f.market.push({...f.market[0],id:'petrol-market',fuel_type_raw:'BENSIN',canonical_model_id:'model'}),
    f=>{f.months[0].fuel_type_raw='BENSIN';},
    f=>f.drafts.push({}),
    f=>f.variants.push({}),
    f=>{f.market[0].last_seen_month='2026-11-01';},
    f=>f.models.push({...f.models[0],id:'duplicate',normalized_model:'macan electric'}),
  ]){
    const f=fixture();mutate(f);assert.throws(()=>verifyMacanScope(f,incoming));
  }
});

test('fail when an existing October market count does not agree with the workbook', ()=>{
  const f=fixture();
  f.months.push({...f.months[0],month:'2026-10-01',registrations:42});
  assert.throws(()=>verifyMacanScope(f,incoming),/Conflicting saved October/);
  f.months[1].registrations=43;
  assert.equal(verifyMacanScope(f,incoming).expected_monthly.length,2);
});

test('do not open a canonical query against a writable transaction', async()=>{
  await assert.rejects(readMacanScope({query:async sql=>{
    assert.equal(sql,'SHOW transaction_read_only');
    return {rows:[{transaction_read_only:'off'}]};
  }},incoming),/off/);
});
