import assert from 'node:assert/strict';
import { test } from 'node:test';
import { normalizePublicVariants } from '../functions/_shared/advisor-core.mjs';
import { matchAdvisorVariants, ruleRequirements } from '../src/advisor-matching.js';
import { specQualifications } from '../src/spec-qualifications.js';

const manual = 'https://www.polestar.com/se/manual/polestar-3/2027/article/certified-wltp/';
const row = {id: 'isolated-polestar-fixture', brand: 'Polestar', model: '3', variant_name: 'Performance',
  validation_status: 'published', source_url: 'https://www.polestar.com/se/polestar-3/specifications/',
  source_hash: 'a'.repeat(64), source_quote: manual + ' | Performance | 742 | 601 | 20,5 | 649 | 524 | 23,1',
  price_sek: 999000, price_type: 'list_price', wltp_range_km: 601, wltp_consumption_kwh_100km: 20.5};

test('the certified combined interval excludes city range and follows the exact variant', () => {
  const qualified = specQualifications(row);
  assert.equal(qualified.rangeMinimum, 524);
  assert.equal(qualified.rangeInterval, '524\u2013601 km');
  assert.equal(qualified.consumptionInterval, '20,5\u201323,1 kWh/100 km');
  assert.equal(qualified.rangeIsTarget, false);
  for (const patch of [{variant_name: 'Dual motor'}, {wltp_range_km: 742},
    {source_quote: row.source_quote.replace('/2027/', '/2026/')}, {source_quote: 'Performance | 601 km'}]) {
    assert.equal(specQualifications({...row, ...patch}).rangeMinimum, null);
  }
});

test('normalized and raw advice never confirm an interval-dependent minimum', () => {
  for (const variants of [[row], normalizePublicVariants([row])]) {
    const match = range => matchAdvisorVariants(variants, ruleRequirements({budget: 1000000, range}));
    const result = match(524);
    assert.equal(result.matching_count, 1);
    assert(result.shortlist[0].reasons.some(reason => reason.includes('524\u2013601 km WLTP')));
    assert.deepEqual([match(525).matching_count, match(525).excluded_unknown_count], [0, 1]);
    assert.deepEqual([match(601).matching_count, match(601).excluded_unknown_count], [0, 1]);
    assert.match(match(600).interpreted_requirements.notes, /Exakt konfiguration/);
    assert.deepEqual([match(602).matching_count, match(602).excluded_unknown_count], [0, 0]);
  }
});
