import assert from 'node:assert/strict';
import { applySpecPlan as apply, buildSpecPlan as build, specPlanHash, TECHNICAL_FIELDS } from './kia_spec_sync.mjs';
export { specPlanHash };
export const ADAPTER = 'toyota_polestar_sweden_specs_v1';
const root = 'https://www.polestar.com/se/';
const scopes = { 'Toyota|bZ4X': ['Active FWD 57.7 kWh 167 hk'],
  'Polestar|2': ['Long range Single motor', 'Long range Dual motor', 'Long range Dual motor med Performance-paketet'],
  'Polestar|4': ['Rear motor', 'Dual motor'] };
const sources = { 'Toyota|bZ4X': 'https://www.toyota.se/bilar/bz4x/specifications',
  'Polestar|2': root + 'polestar-2/specifications/',
  'Polestar|4': root + 'polestar-4-models/polestar-4-coupe/specifications/' };
const support = {
  'Toyota|bZ4X': ['https://www.toyota.se/bilar/bz4x'],
  'Polestar|2': [root + 'polestar-2/', root + 'manual/polestar-2/2026/article/946775eb53a5592fc0a8015165dbd2b8/'],
  'Polestar|4': [root + 'news/suv-vs-suv-coupe-what-is-the-difference/', root + 'manual/polestar-4-coupe/2027/article/0ed816eed33d98cac0a8cc377bc12bc7-32882fb459557dbec0a8b097072c55bf-8664b2fa77a7e089c0a8296870d1a409/'],
};
const key = row => row.brand + '|' + row.model;
const num = text => Number(text.replaceAll(' ', '').replace(',', '.'));
const sourceName = row => row.brand + ' Sverige';
const canonicalFields = ['price_type','price_valid_until','price_source_url','price_source_hash',
  'price_source_quote','price_verified_at','price_source_name','price_refresh_batch_id'];
function fresh(source, now) {
  assert.equal(source.status, 'reachable'); assert.equal(source.http_status, 200);
  assert.match(source.content_hash, /^[a-f0-9]{64}$/);
  const age = now - Date.parse(source.fetched_at);
  assert(Number.isFinite(age) && age >= -60000 && age <= 900000, 'Fresh manufacturer evidence required');
}

export function validateSpecDraft(row, now = new Date()) {
  assert.equal(row.adapter, ADAPTER);
  const identity = key(row);
  assert(scopes[identity]?.includes(row.variant_name), 'Exact existing version required');
  assert.equal(row.source_resolution, 'owner_2026_11_13_exact_version_current_sources');
  assert(row.extraction_confidence >= 0.92 && row.extraction_confidence <= 1);
  fresh(row.source, now); assert.equal(row.source.final_url, sources[identity]);
  const registered = new Map([[row.source.final_url, row.source.content_hash]]);
  assert(Array.isArray(row.supporting_sources));
  for (const extra of row.supporting_sources) {
    assert(support[identity].includes(extra.final_url)); fresh(extra, now);
    assert(!registered.has(extra.final_url)); registered.set(extra.final_url, extra.content_hash);
  }
  const fields = [...TECHNICAL_FIELDS, 'ac_charge_kw'].sort();
  assert.deepEqual(Object.keys(row.facts).sort(), fields, 'Nine complete technical fields required');
  assert.deepEqual(Object.keys(row.field_evidence).sort(), fields);
  for (const [field, value] of Object.entries(row.facts)) {
    const proof = row.field_evidence[field];
    assert.equal(proof.value, value); assert.equal(proof.variant_name, row.variant_name);
    assert.equal(registered.get(proof.source_url), proof.source_hash);
    assert(typeof proof.quote === 'string' && proof.quote.length > 5);
    if (field === 'drivetrain') assert(['FWD','Bakhjulsdrift','Fyrhjulsdrift'].includes(value));
    else {
      const bounds = { wltp_range_km: [50,1200], wltp_consumption_kwh_100km: [5,50], battery_kwh: [10,250],
        dc_charge_kw: [20,600], ac_charge_kw: [1,50], boot_liters: [50,3500], tow_kg: [0,4000], seats: [1,9] }[field];
      assert(typeof value === 'number' && Number.isFinite(value) && value >= bounds[0] && value <= bounds[1]);
      if (!['battery_kwh','wltp_consumption_kwh_100km'].includes(field)) assert(Number.isInteger(value));
    }
    if (row.brand === 'Toyota') {
      if (proof.scope === 'selected_manufacturer_config') {
        assert.equal(proof.manufacturer_variant_id, '552b7e03-84d2-4b36-a5bb-87d84cb7d05c');
        assert(proof.quote.startsWith('Elmotor 167 hk, batteri 57,7 kWh | Active | '));
        assert(proof.quote.includes(proof.source_pointer + ' = '));
        assert(proof.source_pointer.startsWith('/carConfigMotorization/motorization/0/') || proof.source_pointer.startsWith('/specs/techSpecs/'));
        const raw = proof.raw_value;
        const wanted = field === 'drivetrain' ? raw === 'Framhjulsdrift' ? 'FWD' : null
          : field === 'battery_kwh' ? num(/batteri ([0-9]+,[0-9]+) kWh/.exec(raw)?.[1] || '')
          : num(String(raw)) / (field === 'wltp_consumption_kwh_100km' ? 10 : 1);
        assert.equal(value, wanted);
      } else if (['ac_charge_kw','dc_charge_kw'].includes(field)) {
        assert.equal(proof.quote, 'Ombordladdare 11 kW AC och kapacitet för snabbladdning 150 kW DC');
        assert.equal(value, field === 'ac_charge_kw' ? 11 : 150);
      } else {
        assert.equal(field, 'boot_liters'); assert.equal(value, 452);
        assert.equal(proof.source_url, support[identity][0]);
        assert(proof.quote.includes('bagageutrymmet erbjuder 452 liters lastkapacitet.'));
      }
    } else {
      const p4 = row.model === '4';
      if (proof.scope.startsWith('exact_variant_') || proof.scope === 'manufacturer_wltp_target')
        assert.equal(proof.column_header, row.variant_name);
      if (field === 'wltp_range_km') {
        if (p4 && row.variant_name === 'Rear motor') {
          assert.equal(proof.scope, 'certified_rear_motor_20_inch');
          assert.equal(proof.source_url, support[identity][1]);
          assert.equal(proof.quote, 'Bakre motor | 20-tumsdäck 620 17,8'); assert.equal(value, 620);
        } else {
          assert.equal(proof.scope, p4 ? 'manufacturer_wltp_target' : 'exact_variant_wltp');
          assert.equal(value, num(/(?:Räckvidd[²]?|Räckviddsmål \(WLTP\)[²]?) (?:Upp till )?([0-9]+) km/.exec(proof.quote)?.[1] || ''));
          assert(p4 === proof.quote.startsWith('Räckviddsmål'));
        }
      } else if (field === 'wltp_consumption_kwh_100km') {
        const match = /^Energikonsumtion \(WLTP\)² ([0-9]+,[0-9]+)[–-]([0-9]+,[0-9]+) kWh\/100 km$/.exec(proof.quote);
        assert(match); assert.deepEqual(proof.interval, [num(match[1]),num(match[2])]);
        assert.equal(value, proof.interval[0]); assert(value <= proof.interval[1]);
        assert.equal(proof.scope, 'exact_variant_wltp_interval_lower_bound');
      } else if (field === 'battery_kwh') {
        assert.equal(value, num(/(?:, |batteri )([0-9]+) kWh kapacitet/.exec(proof.quote)?.[1] || ''));
        assert(proof.quote.startsWith(p4 ? 'Batteri 400-V Litiumjonbatteri' : 'Batterikapacitet 400 V litiumjonbatteri'));
      } else if (field === 'dc_charge_kw') assert.equal(value, num(/^DC-laddning Upp till ([0-9]+) kW$/.exec(proof.quote)?.[1] || ''));
      else if (field === 'ac_charge_kw') {
        assert.equal(value, 11);
        assert(p4 ? proof.quote === 'AC-laddning 11 kW 22 kW (tillval)' : proof.quote.startsWith('11 kW AC laddningstid (3-fas 16A AC)'));
      } else if (field === 'boot_liters') {
        assert.equal(proof.scope, 'model_rear_boot_seats_up');
        assert.equal(value, p4 ? 526 : 407);
        assert.equal(proof.quote, p4 ? '526 liters lastkapacitet med uppfällt baksäte, inklusive under lastgolvet'
          : 'Volym (uppfällda säten) 407 liter, inklusive under golvet');
      } else if (field === 'tow_kg') assert.equal(value, num(/^Drag(?:vikt|kraft) Upp till ([0-9 ]+) kg$/.exec(proof.quote)?.[1] || ''));
      else if (field === 'drivetrain') {
        assert.equal(proof.quote, 'Drivlina ' + value);
        assert.equal(value, row.variant_name.includes('Dual') ? 'Fyrhjulsdrift' : 'Bakhjulsdrift');
      } else if (field === 'seats') {
        assert.equal(value, 5); assert.equal(proof.source_url, support[identity][p4 ? 0 : 1]);
        assert.equal(proof.quote, p4 ? 'Båda bilarna är rymliga, med gott om plats för fem personer och deras bagage' : 'Polestar 2 har fem säten.');
      }
    }
  }
  assert.deepEqual(row.held_fields, {});
  const body = row.brand === 'Polestar' && row.model === '2' ? 'Fastback' : 'SUV';
  assert.deepEqual(row.model_facts, { body_type: body });
  const proof = row.model_field_evidence.body_type;
  assert.equal(proof.value, body); assert.equal(registered.get(proof.source_url), proof.source_hash);
  assert.equal(proof.quote, row.brand === 'Toyota' ? 'En elegant SUV' : row.model === '2'
    ? 'En fastback som är designad för körglädje och elektrisk prestanda.' : 'Polestar 4 är en SUV-coupé');
  const price = row.price_evidence;
  assert.equal(price.source_url, row.source.final_url); assert.equal(price.source_hash, row.source.content_hash);
  assert.equal(price.price_type, 'list_price'); assert.equal(price.price_valid_until, null);
  assert.equal(price.classification, 'current_exact_variant_base_cash_price_not_finance_or_discount');
  assert(Number.isInteger(price.value) && price.value >= 100000 && price.value <= 3000000);
  if (row.brand === 'Polestar') {
    assert.equal(price.value, num(new RegExp('^' + row.variant_name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ' \\| Pris från ([0-9 ]+) kr$').exec(price.quote)?.[1] || ''));
  } else {
    assert(price.quote.startsWith('Elmotor 167 hk, batteri 57,7 kWh | Active | ' + price.value));
    assert(price.quote.includes('selected price.cash=' + price.value));
    assert.equal(num(/price.exclVat=([0-9]+(?:\.[0-9]+)?)/.exec(price.quote)?.[1] || '') * 1.25, price.value);
    assert(price.quote.endsWith('promotions=[]'));
  }
  return row;
}

const policy = { adapter: ADAPTER, validate: validateSpecDraft, sourceType: 'manufacturer_model_page', sourceName,
  sourceTitle: row => row.brand + ' ' + row.model + ' svenska tekniska uppgifter', lockKey: 7240016,
  extraFields: ['ac_charge_kw'], allowedBodyTypes: ['SUV','Fastback'], modelFacts: row => row.model_facts,
  supportingSource: (source, row) => support[key(row)].includes(source.final_url)
    ? { model: row.model, sourceType: 'manufacturer_page', title: row.brand + ' ' + row.model + ' kompletterande modelluppgifter', shared: false } : null,
  priceRefresh: (previous, row) => Number(previous.price_sek) === row.price_evidence.value &&
    (!previous.price_type || previous.price_type === 'list_price') && !previous.price_valid_until,
  canonicalFields,
  canonicalExtras: (row, previous) => {
    assert.equal(Number(previous.price_sek), row.price_evidence.value, 'Price changes require a separate price reconciliation');
    assert(!previous.price_type || previous.price_type === 'list_price'); assert(!previous.price_valid_until);
    return { price_type: 'list_price', price_valid_until: null, price_source_url: row.price_evidence.source_url,
      price_source_hash: row.price_evidence.source_hash, price_source_quote: row.price_evidence.quote,
      price_verified_at: new Date(row.source.fetched_at).toISOString(), price_source_name: sourceName(row),
      price_refresh_batch_id: specPlanHash({ adapter: ADAPTER, price_evidence: row.price_evidence, fetched_at: row.source.fetched_at }) };
  },
};
export const buildSpecPlan = (rows, intake, now) => {
  const plan = build(rows, intake, now, policy);
  for (const target of plan.targets) policy.canonicalExtras(target.draft, target.expected);
  return plan;
};
export const applySpecPlan = (client, plan, hash, now) => apply(client, plan, hash, now, policy);

// Toyota's rendered page contains transient client state. Re-fetch, re-parse and
// bind NEW raw hashes, while requiring identical exact facts/quotes/identity.
export const intakeFingerprint = intake => intake.drafts.map(row => JSON.parse(JSON.stringify(row,
  (name, value) => ['content_hash','source_hash','http_preflight_hash','fetched_at'].includes(name) ? undefined : value)));
