import assert from 'node:assert/strict';
import { normalizePublicVariants, createAdvisorResult, createCompareResult } from '../functions/_shared/advisor-core.mjs';
import { createAiGuard } from '../functions/_shared/ai-guard.mjs';
import { readJsonRequest } from '../functions/_shared/http.mjs';
import { onRequestPost as advisorPost } from '../functions/api/advisor.js';
import { onRequestPost as comparePost } from '../functions/api/compare.js';
import { ruleRequirements } from '../src/advisor-matching.js';
import { budgetFixture } from './fixtures/ai-budget.mjs';

const fixturePermit = { reserve: async () => ({ settle: async () => {} }) };

// All provider responses are fixtures. This test never makes a network request.
const raw = {
  id: 'fixture-one', brand: 'Fixture', model: 'One', variant_name: 'Long Range',
  price_sek: 550000, price_type: 'campaign_price', price_valid_until: '2026-12-31',
  wltp_range_km: 520, dc_charge_kw: null, tow_kg: 0, boot_liters: 450,
  source_url: 'https://manufacturer.example/se/one', source_hash: 'fixture-hash',
  validation_status: 'published', market_seen: true, available_confirmed: 'false',
};
const variants = normalizePublicVariants([
  raw, { ...raw, id: 'fixture-two', model: 'Two', price_sek: null, validation_status: 'published_reviewed' },
  { ...raw, validation_status: 'draft' }, { ...raw, source_hash: '' },
  { ...raw, source_url: 'http://manufacturer.example' },
  { ...raw, source_url: 'https://user:password@manufacturer.example' },
  { ...raw, source_url: null }, { ...raw, variant_name: '' },
]);
assert.equal(variants.length, 2);
assert.equal(variants[0].available_confirmed, false);
assert.equal(variants[0].market_seen, true);
assert.equal(variants[0].dc_charge_kw, null);
assert.equal(variants[0].tow_kg, 0);
assert.equal(variants[1].price_sek, null);
const request = { prompt: 'Family car', budget: 600000, range: 500, need: 'familj' };
const adviceFixture = { ...ruleRequirements(request), budget_sek: null, min_wltp_range_km: null };
const compareFixture = {
  mode: 'openai', summary: 'Fixture comparison', reasons: ['Reason'], tradeoffs: ['Tradeoff'],
  winner: { variant_key: variants[0].variant_key, name: 'Wrong', decision_score: 500, source_url: 'https://wrong.example' },
  compared: variants.map((row, index) => ({ variant_key: row.variant_key, name: 'Wrong', decision_score: index ? -20 : 110,
    price_sek: 1, wltp_range_km: 9999, source_url: 'https://wrong.example' })),
};
let providerCalls = 0;
const provider = (fixture) => async (url, options) => {
  providerCalls++;
  assert.equal(url, 'https://api.openai.com/v1/responses');
  assert.equal(options.method, 'POST');
  assert.equal(options.redirect, 'manual');
  assert.equal(options.headers.authorization, 'Bearer fixture-only-key');
  assert.ok(options.signal instanceof AbortSignal);
  const body = JSON.parse(options.body);
  assert.equal(body.model, 'gpt-5.4-mini');
  assert.equal(body.store, false);
  assert.equal(body.text.format.type, 'json_schema');
  assert.equal(body.text.format.strict, true);
  const context = JSON.parse(body.input[1].content);
  if (body.text.format.name === 'ev_search_requirements') {
    assert.equal(body.max_output_tokens, 512);
    assert.deepEqual(Object.keys(context).sort(), ['form', 'prompt']);
    assert.ok(options.body.length < 6000);
    assert.ok(!options.body.includes(raw.source_url) && !options.body.includes('public_variants'));
    assert.equal(body.text.format.schema.properties.shortlist, undefined, 'AI must not select cars');
  } else {
    assert.equal(body.text.format.name, 'ev_compare_report');
    assert.equal(body.max_output_tokens, 2400);
    const rows = context.selected_public_variants;
    assert.equal(rows.length, 2);
    assert.equal(rows[0].available_confirmed, false);
    assert.equal(rows[0].price_type, 'campaign_price');
    assert.equal(rows[0].price_valid_until, '2026-12-31');
    assert.equal(rows[0].dc_charge_kw, null);
    assert.equal(rows[0].tow_kg, 0);
    assert.ok(rows.every((row) => ['published', 'published_reviewed'].includes(row.validation_status)));
  }
  return Response.json({ status: 'completed', output: [{ type: 'message', content: [{ type: 'output_text', text: JSON.stringify(fixture) }] }] });
};
const options = { variants, apiKey: 'fixture-only-key', budget: fixturePermit };
const advice = await createAdvisorResult({ ...options, request, fetchImpl: provider(adviceFixture) });
assert.equal(advice.mode, 'openai');
assert.equal(advice.shortlist.length, 1);
assert.equal(advice.shortlist[0].brand, raw.brand);
assert.equal(advice.shortlist[0].model, raw.model);
assert.equal(advice.shortlist[0].source_url, raw.source_url);
assert.ok(advice.shortlist[0].match_score <= 100);
assert.equal(advice.recommendation_method, 'database_rules');
assert.equal(advice.interpreted_requirements.budget_sek, 600000);
assert.ok(advice.shortlist[0].reasons[0].length <= 140);
const variantKeys = variants.map((row) => row.variant_key);
const compare = await createCompareResult({ ...options, variantKeys, fetchImpl: provider(compareFixture) });
assert.equal(compare.mode, 'openai');
assert.equal(compare.winner.decision_score, 100);
for (const [index, item] of compare.compared.entries()) {
  assert.equal(item.source_url, variants[index].source_url);
  assert.equal(item.price_sek, variants[index].price_sek);
  assert.equal(item.wltp_range_km, variants[index].wltp_range_km);
}
assert.equal(compare.compared[1].decision_score, 0);
const incompleteReport = await createCompareResult({ ...options, variantKeys, fetchImpl: provider({ ...compareFixture, compared: compareFixture.compared.slice(0, 1) }) });
assert.equal(incompleteReport.mode, 'deterministic_fallback');
const inventedWinner = await createCompareResult({ ...options, variantKeys, fetchImpl: provider({ ...compareFixture, winner: { variant_key: 'invented' } }) });
assert.equal(inventedWinner.mode, 'deterministic_fallback');
const inventedAdvice = await createAdvisorResult({ ...options, request, fetchImpl: provider({ ...adviceFixture, shortlist: [{ id: 'invented' }] }) });
assert.equal(inventedAdvice.mode, 'deterministic_fallback');
assert.equal((await createAdvisorResult({ ...options, request, fetchImpl: provider({ ...adviceFixture, budget_sek: -1 }) })).mode, 'deterministic_fallback');
const emptyMatches = await createAdvisorResult({ ...options, request, fetchImpl: provider({ ...adviceFixture, budget_sek: 100000 }) });
assert.equal(emptyMatches.mode, 'openai');
assert.equal(emptyMatches.shortlist.length, 0, 'No fabricated or over-budget substitute');
assert.equal((await createCompareResult({ ...options, variantKeys, fetchImpl: provider({ ...compareFixture, compared: [null] }) })).mode, 'deterministic_fallback');

const logged = [];
const originalError = console.error;
console.error = (...values) => logged.push(values.join(' '));
try {
  for (const fetchImpl of [
    async () => new Response(null, { status: 302, headers: { location: 'https://wrong.example' } }),
    async () => Response.json({ error: { message: 'SENSITIVE_PROVIDER_BODY' } }, { status: 401 }),
    async () => Response.json({ error: { type: 'insufficient_quota', message: 'SENSITIVE_PROVIDER_BODY' } }, { status: 429 }),
    async () => Response.json({ status: 'incomplete', output_text: JSON.stringify(adviceFixture) }),
    async () => Response.json({ status: 'completed', output: [{ content: [{ type: 'refusal', refusal: 'No' }] }] }),
    async () => Response.json({ output_text: 'not json' }),
    async () => { throw new Error('SENSITIVE_PROVIDER_BODY'); },
    async () => { throw new DOMException('Timed out', 'TimeoutError'); },
  ]) {
    assert.equal((await createAdvisorResult({ ...options, request, fetchImpl })).mode, 'deterministic_fallback');
    assert.equal((await createCompareResult({ ...options, variantKeys, fetchImpl })).mode, 'deterministic_fallback');
  }
} finally { console.error = originalError; }
assert.ok(logged.length >= 12);
assert.ok(logged.some((line) => line.includes('http_429_insufficient_quota')));
assert.ok(logged.every((line) => !line.includes('SENSITIVE') && !line.includes('fixture-only-key')));
const noFetch = async () => { assert.fail('No provider request should be made'); };
assert.equal((await createAdvisorResult({ ...options, apiKey: '', request, fetchImpl: noFetch })).mode, 'deterministic_fallback');
assert.equal((await createAdvisorResult({ ...options, request: { ...request, prompt: '' }, fetchImpl: noFetch })).interpretation_method, 'form');
assert.equal((await createAdvisorResult({ ...options, variants: [], request, fetchImpl: noFetch })).shortlist.length, 0);
assert.equal((await createAdvisorResult({ ...options, variants: [{ ...variants[0], validation_status: 'draft' }], request, fetchImpl: noFetch })).shortlist.length, 0);
assert.equal(await createCompareResult({ ...options, variantKeys: ['unknown'], fetchImpl: noFetch }), null);

const httpRequest = (overrides = {}) => new Request('https://preview.example/api/advisor', {
  method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://preview.example', 'cf-connecting-ip': '192.0.2.1', ...overrides }, body: '{}',
});
const env = { OPENAI_API_KEY: 'fixture-only-key' };
let now = 0;
const guard = createAiGuard({ now: () => now, limit: 2, maxConcurrent: 1, windowMs: 1000 });
const first = guard(httpRequest(), env);
assert.equal(first.response, undefined);
assert.equal(guard(httpRequest(), env).response.status, 429);
first.release(); first.release();
const second = guard(httpRequest(), env);
assert.equal(second.response, undefined);
second.release();
const limited = guard(httpRequest(), env).response;
assert.equal(limited.status, 429);
assert.equal(limited.headers.get('retry-after'), '1');
now = 1001;
const renewed = guard(httpRequest(), env);
assert.equal(renewed.response, undefined); renewed.release();
assert.equal(guard(httpRequest({ origin: 'https://other.example' }), env).response.status, 403);
assert.equal(guard(httpRequest({ 'content-type': 'text/plain' }), env).response.status, 415);
assert.equal(guard(httpRequest({ 'content-type': 'text/plain' }), {}).response, undefined);
const capped = createAiGuard({ now: () => now, maxClients: 1 });
const one = capped(httpRequest(), env); one.release();
assert.equal(capped(httpRequest({ 'cf-connecting-ip': '192.0.2.2' }), env).response.status, 429);
for (const body of ['null', '[]', '"string"', '123', '{broken', ' '.repeat(20001)]) {
  await assert.rejects(readJsonRequest(new Request('https://preview.example', { method: 'POST', body })));
}
assert.deepEqual(await readJsonRequest(httpRequest()), {});

const edgeEnv = { ...budgetFixture().env, ...env, ASSETS: { fetch: async () => Response.json({ records: [raw, { ...raw, id: 'fixture-two', model: 'Two', price_sek: null, validation_status: 'published_reviewed' }] }) } };
const originalFetch = globalThis.fetch;
const edgeRequest = (path, body) => new Request(`https://preview.example${path}`, {
  method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://preview.example', 'cf-connecting-ip': '192.0.2.10' }, body: JSON.stringify(body),
});
try {
  globalThis.fetch = provider(adviceFixture);
  const response = await advisorPost({ request: edgeRequest('/api/advisor', request), env: edgeEnv });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).mode, 'openai');
  globalThis.fetch = provider(compareFixture);
  const report = await comparePost({ request: edgeRequest('/api/compare', { variant_keys: variantKeys }), env: edgeEnv });
  assert.equal(report.status, 200);
  assert.equal((await report.json()).mode, 'openai');
  console.error = (...values) => logged.push(values.join(' '));
  assert.equal((await advisorPost({ request: edgeRequest('/api/advisor', []), env: edgeEnv })).status, 400);
  assert.equal((await comparePost({ request: edgeRequest('/api/compare', { variant_keys: ['unknown'] }), env: edgeEnv })).status, 400);
  assert.equal((await advisorPost({ request: edgeRequest('/api/advisor', null), env: edgeEnv })).status, 400);
  assert.equal((await advisorPost({ request: edgeRequest('/api/advisor', request), env: edgeEnv })).status, 429);
} finally { globalThis.fetch = originalFetch; console.error = originalError; }
assert.ok(logged.every((line) => !line.includes('fixture-only-key')));
console.log(JSON.stringify({ live_ai_contract_ok: true, simulated_provider_calls: providerCalls, real_provider_calls: 0, guard_ok: true, edge_routes_ok: true }));
