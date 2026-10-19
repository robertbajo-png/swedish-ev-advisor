import assert from 'node:assert/strict';
import { tokenCost, runBenchmark, SEARCHES } from './benchmark_advisor_cost.mjs';
import { normalizePublicVariants } from '../functions/_shared/advisor-core.mjs';
import { ruleRequirements } from '../src/advisor-matching.js';

const usage = { input_tokens: 10000, input_tokens_details: { cached_tokens: 0 }, output_tokens: 1000, output_tokens_details: { reasoning_tokens: 400 } };
assert.equal(tokenCost(usage, 'gpt-5.4-mini', 'default'), 0.012);
assert.equal(tokenCost({ ...usage, input_tokens_details: { cached_tokens: 8000 } }, 'gpt-5.4-mini-2026-03-17', 'default'), 0.0066);
for (const invalid of [null, {}, { ...usage, input_tokens: -1 }, { ...usage, output_tokens: 1.5 }, { ...usage, input_tokens_details: { cached_tokens: 10001 } }, { ...usage, input_tokens_details: { cached_tokens: 0, cache_write_tokens: 1 } }]) {
  assert.throws(() => tokenCost(invalid, 'gpt-5.4-mini', 'default'));
}
assert.throws(() => tokenCost(usage, 'gpt-5.4', 'default'));
assert.throws(() => tokenCost(usage, 'gpt-5.4-mini', 'priority'));
const variants = normalizePublicVariants([{ id: 'fixture', brand: 'Fixture', model: 'One', variant_name: 'Base', source_url: 'https://manufacturer.example/se', source_hash: 'fixture-hash', validation_status: 'published', price_sek: 300000, wltp_range_km: 600 }]);
let calls = 0;
const valid = async () => {
  calls++;
  return Response.json({ status: 'completed', model: 'gpt-5.4-mini', service_tier: 'default', usage, output_text: JSON.stringify({
    ...ruleRequirements(), budget_sek: null, min_wltp_range_km: null,
  }) });
};
const five = await runBenchmark({ variants, apiKey: 'fixture-only', fetchImpl: valid });
assert.equal(calls, 5);
assert.equal(five.provider_calls, 5);
assert.ok(five.results.every((r) => r.mode === 'openai' && r.calculated_cost_usd === 0.012 && r.canonical_identity_and_sources_ok));
await assert.rejects(runBenchmark({ variants, apiKey: 'fixture', searches: [...SEARCHES, SEARCHES[0]], fetchImpl: valid }));
const oldError = console.error;
console.error = () => {};
try {
  const failed = await runBenchmark({ variants, apiKey: 'fixture', fetchImpl: async () => Response.json({}, { status: 429 }) });
  assert.equal(failed.provider_calls, 1);
  assert.equal(failed.results[0].calculated_cost_usd, null);
  const refused = await runBenchmark({ variants, apiKey: 'fixture', fetchImpl: async () => Response.json({ model: 'gpt-5.4-mini', service_tier: 'default', usage }) });
  assert.equal(refused.provider_calls, 1);
  assert.equal(refused.results[0].mode, 'deterministic_fallback');
  assert.equal(refused.results[0].calculated_cost_usd, 0.012);
} finally { console.error = oldError; }
console.log(JSON.stringify({ cost_benchmark_contract_ok: true, real_provider_requests: 0, five_call_limit: true, cached_tokens_accounted_for: true, reasoning_not_double_counted: true }));
