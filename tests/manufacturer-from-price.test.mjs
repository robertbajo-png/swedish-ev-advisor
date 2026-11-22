import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createCompareResult, normalizePublicVariants } from '../functions/_shared/advisor-core.mjs';
import { normalizeCatalog } from '../scripts/sync_public_catalog.mjs';
import { ruleAdvice } from '../src/advisor-matching.js';
import { decisionMetricsFor } from '../src/decision-metrics.js';
import { MANUFACTURER_FROM_PRICE, priceOfferEnd, priceTypeLabel } from '../src/price-evidence.js';
import { calculateTco } from '../src/tco.js';

const source = 'https://www.ford.se/bilar/personbilar-och-suver/puma-gen-e';
const row = {
  id: 'puma-starting-price-fixture', brand: 'Ford', model: 'Puma Gen-E', variant_name: '168 hk',
  validation_status: 'published', source_url: source, source_hash: 'a'.repeat(64), source_quote: 'Synthetic variant proof.',
  extraction_confidence: 1, market_seen: true, available_confirmed: false, discontinued_candidate: false, coming_or_low_volume: false,
  price_type: MANUFACTURER_FROM_PRICE, price_sek: 389000, price_valid_until: null, wltp_range_km: 417,
  price_source_url: source, price_source_hash: 'b'.repeat(64), price_source_quote: 'Synthetic displayed starting price.',
  price_source_name: 'Ford Sverige', price_verified_at: '2026-11-21T00:00:00.000Z',
};

test('exports a distinct starting price only with complete price evidence', () => {
  assert.equal(priceTypeLabel(MANUFACTURER_FROM_PRICE), 'Tillverkarens fr\u00e5npris');
  assert.equal(priceOfferEnd(MANUFACTURER_FROM_PRICE, '2026-12-31'), null);
  assert.equal(normalizeCatalog([row])[0].price_type, MANUFACTURER_FROM_PRICE);
  assert.equal(normalizePublicVariants([row])[0].price_type, MANUFACTURER_FROM_PRICE);
  for (const patch of [{price_source_hash: null}, {price_valid_until: '2026-12-31'}, {price_sek: null}]) {
    const bad = {...row, ...patch};
    assert.throws(() => normalizeCatalog([bad]), /price.*evidence/i);
    assert.deepEqual(normalizePublicVariants([bad]), []);
  }
});

test('starting price is not a hard-budget match or a final-cost input', () => {
  const possible = ruleAdvice([row], {budget: 390000, range: 400});
  assert.equal(possible.matching_count, 0);
  assert.equal(possible.excluded_unknown_count, 1);
  assert.match(possible.interpreted_requirements.notes, /fr\u00e5npris bekr\u00e4ftar inte slutpriset/i);
  const tooExpensive = ruleAdvice([row], {budget: 380000, range: 400});
  assert.deepEqual([tooExpensive.matching_count, tooExpensive.excluded_unknown_count], [0, 0]);
  assert.equal(ruleAdvice([{...row, price_type: 'list_price'}], {budget: 390000, range: 400}).matching_count, 1);
  const car = {price: row.price_sek, priceType: row.price_type, rangeVerified: row.wltp_range_km};
  assert(decisionMetricsFor(car).slice(0, 2).every(metric => metric.value === 'Uppgift saknas'));
  assert.equal(calculateTco(car).reason, 'manufacturer_from_only');
});

test('comparison involving a starting price does not rank by price or call the provider', async () => {
  const rows = normalizePublicVariants([row, {...row, id: 'list-fixture', variant_name: 'Premium',
    price_type: 'list_price', price_sek: 500000, wltp_range_km: 500}]);
  const result = await createCompareResult({variantKeys: rows.map(r => r.variant_key), variants: rows, apiKey: 'unused-fixture',
    fetchImpl: () => assert.fail('Price-incomparable comparison must not invoke a provider')});
  assert.match(result.summary, /bara tekniska v\u00e4rden/);
  assert.equal(result.winner.variant_key, rows[1].variant_key);
  assert.deepEqual(result.compared.map(r => r.price_sek), [500000, 389000]);
});
