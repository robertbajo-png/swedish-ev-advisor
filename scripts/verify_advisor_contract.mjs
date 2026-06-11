import assert from 'node:assert/strict';
import {
  normalizeAdvisorResult,
  normalizeCompareReport,
} from '../server/advisor_api.mjs';

const variants = [
  {
    id: 'volvo-ex30-id',
    variant_key: 'Volvo|EX30|EX30 Plus',
    brand: 'Volvo',
    model: 'EX30',
    variant_name: 'EX30 Plus',
    price_sek: 457000,
    wltp_range_km: 475,
    dc_charge_kw: 153,
    boot_liters: 318,
    tow_kg: 1600,
    seats: 5,
    drivetrain: 'Bakhjulsdrift',
    source_url: 'https://www.volvocars.com/se/cars/ex30-electric/',
    source_hash: 'abc',
    validation_status: 'published_reviewed',
    available_confirmed: true,
  },
  {
    id: 'kia-ev3-id',
    variant_key: 'Kia|EV3|Long Range',
    brand: 'Kia',
    model: 'EV3',
    variant_name: 'Long Range',
    price_sek: 489900,
    wltp_range_km: 605,
    dc_charge_kw: 128,
    boot_liters: 460,
    tow_kg: 1000,
    seats: 5,
    drivetrain: 'Framhjulsdrift',
    source_url: 'https://www.kia.com/se/nya-bilar/ev3/upptack/',
    source_hash: 'def',
    validation_status: 'published',
    available_confirmed: false,
  },
];

const request = {
  prompt: 'Familjebil med dragkrok och lång räckvidd',
  budget: 620000,
  range: 520,
  need: 'familj',
};

const inventedAdvisorResponse = {
  mode: 'openai',
  interpreted_requirements: {
    budget_sek: 620000,
    min_wltp_range_km: 520,
    need: 'familj',
    notes: 'Test',
  },
  summary: 'Bäst för dig: Kia EV3. Tänk på: '.padEnd(520, 'väldigt lång text '),
  shortlist: [
    {
      id: 'invented-tesla',
      brand: 'Tesla',
      model: 'Model Z',
      variant_name: 'Fantasy',
      match_score: 99,
      reasons: ['Påhittad'],
      tradeoffs: ['Påhittad'],
      source_url: 'https://example.com',
    },
    {
      id: 'kia-ev3-id',
      brand: 'Wrong Brand',
      model: 'Wrong Model',
      variant_name: 'Wrong Variant',
      match_score: 88,
      reasons: ['Bra räckvidd '.repeat(40)],
      tradeoffs: ['Inte AWD '.repeat(40)],
      source_url: 'https://wrong.example.com',
    },
  ],
};

const normalizedAdvice = normalizeAdvisorResult(inventedAdvisorResponse, variants, request);
assert.equal(normalizedAdvice.mode, 'openai');
assert.equal(normalizedAdvice.shortlist.length, 1);
assert.equal(normalizedAdvice.shortlist[0].brand, 'Kia');
assert.equal(normalizedAdvice.shortlist[0].model, 'EV3');
assert.equal(normalizedAdvice.shortlist[0].source_url, 'https://www.kia.com/se/nya-bilar/ev3/upptack/');
assert.ok(normalizedAdvice.summary.length <= 360);
assert.match(normalizedAdvice.summary, /Bäst för dig:|Tänk på:|Alternativ:/);
assert.ok(normalizedAdvice.shortlist[0].reasons[0].length <= 140);
assert.ok(normalizedAdvice.shortlist[0].tradeoffs[0].length <= 140);

const fullyInventedAdvice = normalizeAdvisorResult(
  { ...inventedAdvisorResponse, shortlist: [inventedAdvisorResponse.shortlist[0]] },
  variants,
  request,
);
assert.equal(fullyInventedAdvice.mode, 'deterministic_fallback');
assert.ok(fullyInventedAdvice.shortlist.every((item) => variants.some((row) => row.id === item.id)));

const inventedCompareResponse = {
  mode: 'openai',
  winner: {
    variant_key: 'Tesla|Model Z|Fantasy',
    name: 'Tesla Model Z',
    decision_score: 99,
    source_url: 'https://example.com',
  },
  summary: 'Bäst val: Kia EV3. Tänk på: '.padEnd(520, 'väldigt lång text '),
  reasons: ['Kort skäl '.repeat(40)],
  tradeoffs: ['Kort kompromiss '.repeat(40)],
  compared: [
    {
      variant_key: 'Kia|EV3|Long Range',
      name: 'Wrong Name',
      decision_score: 90,
      price_sek: 1,
      wltp_range_km: 999,
      source_url: 'https://wrong.example.com',
    },
    {
      variant_key: 'Tesla|Model Z|Fantasy',
      name: 'Tesla Model Z',
      decision_score: 99,
      price_sek: 1,
      wltp_range_km: 999,
      source_url: 'https://example.com',
    },
  ],
};

const normalizedCompare = normalizeCompareReport(inventedCompareResponse, variants);
assert.equal(normalizedCompare.mode, 'openai');
assert.equal(normalizedCompare.winner.variant_key, 'Kia|EV3|Long Range');
assert.equal(normalizedCompare.winner.source_url, 'https://www.kia.com/se/nya-bilar/ev3/upptack/');
assert.equal(normalizedCompare.compared.length, 1);
assert.equal(normalizedCompare.compared[0].name, 'Kia EV3 Long Range');
assert.equal(normalizedCompare.compared[0].price_sek, 489900);
assert.ok(normalizedCompare.summary.length <= 360);
assert.match(normalizedCompare.summary, /Bäst val:|Tänk på:|Välj alternativet om:/);
assert.ok(normalizedCompare.reasons[0].length <= 150);
assert.ok(normalizedCompare.tradeoffs[0].length <= 150);

console.log(JSON.stringify({ advisor_contract_ok: true, compare_contract_ok: true }, null, 2));
