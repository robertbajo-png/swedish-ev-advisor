import assert from 'node:assert/strict';
import { decisionMetricsFor } from '../src/decision-metrics.js';
const now = new Date('2026-11-13T12:00:00Z');
const car = { price: 449500, priceType: 'campaign_price', priceValidUntil: '2026-12-15', rangeVerified: 444 };
for (const [priceType, name] of [['campaign_price', 'Kampanjpris'], ['list_price', 'Listpris'], ['dealer_offer', 'Återförsäljarerbjudande']]) {
  const metrics = decisionMetricsFor({ ...car, priceType }, [car, { rangeVerified: 556 }], now);
  assert.equal(metrics[0].value, '98.8 km');
  assert.equal(metrics[1].value, '1 012 kr/km');
  assert.equal(metrics[2].value, '-56 km');
  assert(metrics.slice(0, 2).every(metric => metric.note.startsWith(name + ', giltigt till 2026-12-15')));
  assert(metrics[1].note.endsWith('Inte körkostnad.'));
}
for (const patch of [{ price: null }, { price: 0 }, { price: NaN }, { priceType: null }, { rangeVerified: null }, { priceValidUntil: '2026-11-12' }])
  assert(decisionMetricsFor({ ...car, ...patch }, [], now).slice(0, 2).every(metric => metric.value === 'Uppgift saknas'));
assert.match(decisionMetricsFor({ ...car, priceValidUntil: '2026-11-12' }, [], now)[0].note, /gått ut/);
assert.notEqual(decisionMetricsFor({ ...car, priceValidUntil: '2026-11-13' }, [], now)[0].value, 'Uppgift saknas');
console.log(JSON.stringify({ decision_metrics: 'passed', explicit_price_types: true, expired_unknown_and_missing_guard: true, paid_calls: 0 }));
