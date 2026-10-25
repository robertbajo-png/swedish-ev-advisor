import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { checkReadiness } from '../functions/_shared/readiness.mjs';
import { onRequestGet, onRequest } from '../functions/health.js';
import { PRICING_VERSION } from '../functions/_shared/ai-budget.mjs';

const now = new Date('2026-10-25T12:00:00Z');
let dbReads = 0;
const policy = { enabled: 1, daily_limit_micro: 1000000, monthly_limit_micro: 10000000,
  pricing_version: PRICING_VERSION, pricing_review_until: '2026-11-19' };
const env = { AI_ENABLED: 'true', OPENAI_MODEL: 'gpt-5.4-mini', OPENAI_API_KEY: 'fixture-not-a-real-key',
  AI_BUDGET_SALT: 'fixture-salt-never-used-for-real-ip'.repeat(2),
  AI_BUDGET_DB: { prepare: sql => { assert(sql.startsWith('SELECT ')); return { first: async () => { dbReads++; return policy; } }; } } };
const options = { now, loadVariants: async () => [{}] };
assert((await checkReadiness({ env }, options)).ok);
for (const patch of [{ OPENAI_API_KEY: '' }, { OPENAI_MODEL: 'other' }, { AI_BUDGET_SALT: '' }, { AI_BUDGET_DB: null }]) {
  assert(!(await checkReadiness({ env: { ...env, ...patch } }, options)).ok);
}
for (const patch of [{ daily_limit_micro: 1000001 }, { monthly_limit_micro: 10000001 },
  { pricing_version: 'expired' }, { pricing_review_until: '2026-10-24' }, { pricing_review_until: '2026-10-25' }]) {
  const previous = { ...policy };
  Object.assign(policy, patch);
  assert(!(await checkReadiness({ env }, options)).ok);
  Object.assign(policy, previous);
}
policy.enabled = 0;
assert((await checkReadiness({ env }, options)).ok, 'Emergency stop remains a healthy, fail-closed policy');
assert(!(await checkReadiness({ env }, { ...options, loadVariants: async () => [] })).ok);
assert(!(await checkReadiness({ env }, { ...options, loadVariants: async () => { throw new Error('private fixture'); } })).ok);
assert((await checkReadiness({ env: { AI_ENABLED: 'false' } }, options)).ok);
const result = await onRequestGet();
assert.equal(result.status, 200);
assert.equal((await result.json()).service, 'seekev-api');
assert.equal(onRequest().status, 405);
const failure = await onRequestGet({ env: {}, request: new Request('https://fixture.invalid/health?readiness=1') });
assert.equal(failure.status, 503);
assert(!JSON.stringify(await failure.json()).includes('fixture-not-a-real-key'));
const headers = await readFile(new URL('../public/_headers', import.meta.url), 'utf8');
for (const value of ['X-Content-Type-Options: nosniff', 'X-Frame-Options: DENY', "frame-ancestors 'none'", 'must-revalidate']) assert(headers.includes(value));
console.log(JSON.stringify({ release_runtime_contract_ok: true, database_reads: dbReads, provider_calls: 0, writes: 0,
  scope: 'offline dependency fixtures; not a live provider or deployed header proof' }));
