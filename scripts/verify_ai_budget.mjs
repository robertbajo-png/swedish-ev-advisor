import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { budgetFixture } from './fixtures/ai-budget.mjs';
import { createAiBudget, requestAllowance, usageCharge } from '../functions/_shared/ai-budget.mjs';
import { createAdvisorResult, createCompareResult, normalizePublicVariants } from '../functions/_shared/advisor-core.mjs';
import { onRequestPost as advisorPost } from '../functions/api/advisor.js';
import { onRequestPost as comparePost } from '../functions/api/compare.js';
import { ruleRequirements } from '../src/advisor-matching.js';

const request = (ip = '192.0.2.1', path = 'advisor', body = {}) => new Request(`https://preview.example/api/${path}`, {
  method: 'POST', headers: { origin: 'https://preview.example', 'content-type': 'application/json', 'cf-connecting-ip': ip }, body: JSON.stringify(body),
});
const body = (kind = 'advisor') => ({ model: 'gpt-5.4-mini', store: false, service_tier: 'default',
  max_output_tokens: kind === 'advisor' ? 512 : 2400, input: [{ role: 'user', content: 'Fixture' }], text: {} });
const reserve = (fixture, kind = 'advisor', ip) => createAiBudget(fixture.env, request(ip)).reserve({ kind, body: body(kind) });
const usage = (overrides = {}) => ({ model: 'gpt-5.4-mini-2026-03-17', service_tier: 'default',
  usage: { input_tokens: 1000, output_tokens: 100, total_tokens: 1100, input_tokens_details: { cached_tokens: 0 }, ...overrides } });
const rejected = (promise, code) => assert.rejects(promise, (error) => error.budgetCode === code);
const allowance = requestAllowance('advisor', body());
assert.equal(usageCharge(usage(), allowance), 1200);
assert.equal(usageCharge(usage({ input_tokens_details: { cached_tokens: 800 } }), allowance), 660);
assert.equal(usageCharge(usage({ output_tokens_details: { reasoning_tokens: 50 } }), allowance), 1200);
for (const invalid of [{}, { ...usage(), model: 'unknown' }, { ...usage(), service_tier: 'priority' },
  usage({ input_tokens: -1 }), usage({ output_tokens: 1.2 }), usage({ total_tokens: 500 }),
  usage({ input_tokens_details: { cached_tokens: 1001 } })]) assert.equal(usageCharge(invalid, allowance), null);
assert.throws(() => usageCharge(usage({ output_tokens: 513, total_tokens: 1513 }), allowance));
for (const change of [{ model: 'gpt-5.4' }, { service_tier: 'priority' }, { tools: [] }, { max_output_tokens: 513 },
  { input: [{ content: [{ type: 'input_image' }] }] }, { input: [{ content: 'x'.repeat(10000) }] }]) {
  assert.throws(() => requestAllowance('advisor', { ...body(), ...change }));
}

// Same primary ledger, independent budget objects and client identities, mixed endpoints.
const concurrent = budgetFixture();
concurrent.db.exec('UPDATE ai_budget_policy SET daily_limit_micro = 100000, monthly_limit_micro = 150000');
const permits = await Promise.allSettled(Array.from({ length: 30 }, (_, index) => reserve(concurrent, index % 2 ? 'compare' : 'advisor', `192.0.2.${index}`)));
assert.ok(permits.some((p) => p.status === 'fulfilled') && permits.some((p) => p.status === 'rejected'));
const initialSpend = concurrent.total();
assert.ok(initialSpend > 80000 && initialSpend <= 100000, 'Parallel requests never exceed the shared allowance');
await rejected(reserve(concurrent), 'budget_limited');
concurrent.setNow('2026-10-20T00:00:00Z');
await reserve(concurrent, 'compare');
assert.equal(concurrent.total(), initialSpend + 50000);
concurrent.setNow('2026-10-21T00:00:00Z');
await rejected(reserve(concurrent), 'budget_limited');
concurrent.setNow('2026-11-01T00:00:00Z');
await reserve(concurrent);
assert.equal(concurrent.total(), initialSpend + 70000, 'New UTC calendar month receives a fresh allowance');

const day = budgetFixture();
day.setNow('2026-10-19T23:59:59Z');
day.db.exec('UPDATE ai_budget_policy SET daily_limit_micro = 20000');
await reserve(day);
await rejected(reserve(day), 'budget_limited');
day.setNow('2026-10-20T00:00:00Z');
await reserve(day);
day.setNow('2026-11-19T00:00:00Z');
await rejected(reserve(day), 'budget_limited');

const settled = budgetFixture();
const permit = await reserve(settled);
assert.equal(settled.total(), 20000);
await permit.settle(usage());
assert.equal(settled.total(), 1200);
await permit.settle(usage({ output_tokens: 0, total_tokens: 1000 }));
assert.equal(settled.total(), 1200, 'Duplicate settlement cannot refund twice');
assert.equal(settled.rows()[0].settled, 1);
assert.match(settled.rows()[0].client_hash, /^[a-f0-9]{64}$/);
assert.ok(!JSON.stringify(settled.rows()).includes('192.0.2.1'));
for (let index = 0; index < 4; index++) await reserve(settled);
await rejected(reserve(settled), 'budget_limited');
await reserve(settled, 'compare', '192.0.2.2');
settled.setNow('2026-10-19T12:01:01Z');
await reserve(settled);
settled.db.exec('UPDATE ai_budget_policy SET client_per_day = 6');
await rejected(reserve(settled), 'budget_limited');
settled.db.exec('UPDATE ai_budget_policy SET enabled = 0');
await rejected(reserve(settled, 'compare', '192.0.2.3'), 'budget_limited');
settled.db.exec(readFileSync(new URL('../database/cloudflare/ai_budget.sql', import.meta.url), 'utf8'));
assert.equal(settled.db.prepare('SELECT enabled FROM ai_budget_policy').get().enabled, 0, 'Reapplying schema never re-enables spending');

const offline = { prepare() { throw new Error('SENSITIVE_DB_ERROR'); } };
for (const [env, code] of [[{}, 'budget_disabled'], [{ AI_ENABLED: 'true' }, 'budget_unavailable'],
  [{ ...settled.env, AI_BUDGET_DB: offline }, 'budget_unavailable'], [{ ...settled.env, AI_BUDGET_SALT: '' }, 'budget_unavailable']]) {
  await rejected(createAiBudget(env, request()).reserve({ kind: 'advisor', body: body() }), code);
}

const variants = normalizePublicVariants([{ id: 'fixture', brand: 'Fixture', model: 'One', variant_name: 'Base',
  source_url: 'https://manufacturer.example/se', source_hash: 'hash', validation_status: 'published', price_sek: 300000, wltp_range_km: 600 }]);
const query = { prompt: 'Familjebil under 600000 kr', budget: 600000, range: 400 };
const options = { apiKey: 'fixture-only', variants, request: query, variantKeys: variants.map((v) => v.variant_key) };
const logs = [];
const originalError = console.error;
const originalFetch = globalThis.fetch;
let paidCalls = 0;
const noFetch = async () => { paidCalls++; assert.fail('Budget-denied requests must not reach a provider'); };
console.error = (...args) => logs.push(args.join(' '));
try {
  for (const budget of [undefined, createAiBudget({}, request()), createAiBudget({ ...settled.env, AI_BUDGET_DB: offline }, request()), createAiBudget(settled.env, request())]) {
    const advice = await createAdvisorResult({ ...options, budget, fetchImpl: noFetch });
    const report = await createCompareResult({ ...options, budget, fetchImpl: noFetch });
    assert.equal(advice.mode, 'deterministic_fallback');
    assert.equal(report.mode, 'deterministic_fallback');
    assert.match(advice.ai_status, /^budget_/);
    assert.ok(advice.shortlist.length > 0 && report.compared.length > 0);
  }
  const failures = budgetFixture();
  for (const fetchImpl of [async () => { throw new DOMException('Timeout', 'TimeoutError'); }, async () => Response.json({}, { status: 429 }), async () => Response.json({})]) {
    await createAdvisorResult({ ...options, budget: createAiBudget(failures.env, request()), fetchImpl });
  }
  assert.equal(failures.total(), 60000, 'Unknown/failing requests retain all reservations');
  const faulty = budgetFixture();
  const partial = { ...faulty.env, AI_BUDGET_DB: { prepare(sql) { if (sql.includes('SET charged_micro')) throw new Error('SENSITIVE_SETTLEMENT'); return faulty.binding.prepare(sql); } } };
  await (await createAiBudget(partial, request()).reserve({ kind: 'advisor', body: body() })).settle(usage());
  assert.equal(faulty.total(), 20000);
  const incident = await reserve(faulty, 'advisor', '192.0.2.3');
  await incident.settle(usage({ output_tokens: 513, total_tokens: 1513 }));
  assert.equal(faulty.db.prepare('SELECT enabled FROM ai_budget_policy').get().enabled, 0);

  // Exercise both HTTP routes with a real ledger and fake provider, then exhaust it.
  const edge = budgetFixture();
  let successful = 0;
  globalThis.fetch = async () => {
    successful++;
    return Response.json({ ...usage(), status: 'completed', output_text: JSON.stringify(ruleRequirements(query)) });
  };
  const env = { ...edge.env, OPENAI_API_KEY: 'fixture-only', ASSETS: { fetch: async () => Response.json({ records: variants }) } };
  const result = await advisorPost({ env, request: request('192.0.2.11', 'advisor', query) });
  assert.equal((await result.json()).mode, 'openai');
  assert.equal(successful, 1);
  assert.equal(edge.total(), 1200);
  edge.db.exec('UPDATE ai_budget_policy SET monthly_limit_micro = 1200');
  globalThis.fetch = noFetch;
  for (const [handler, path, data] of [[advisorPost, 'advisor', query], [comparePost, 'compare', { variant_keys: options.variantKeys }]]) {
    const response = await handler({ env, request: request('192.0.2.12', path, data) });
    assert.equal(response.status, 200);
    const fallback = await response.json();
    assert.equal(fallback.mode, 'deterministic_fallback');
    assert.equal(fallback.ai_status, 'budget_limited');
    assert.ok(!JSON.stringify(fallback).includes('1200'));
  }
  assert.equal(paidCalls, 0);
} finally { console.error = originalError; globalThis.fetch = originalFetch; }
assert.ok(logs.every((line) => !/SENSITIVE|fixture-only|192\.0\.2/.test(line)));
console.log(JSON.stringify({ ai_budget_ok: true, sqlite_atomic_reservations: true, concurrency: 30,
  utc_rollovers: true, fail_closed: true, both_routes: true, real_provider_calls: 0 }));
