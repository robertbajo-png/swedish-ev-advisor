import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';

const db = new PGlite();
const body = { model: 'gpt-5.4-mini', service_tier: 'default', status: 'completed', output: [] };
const reserve = (overrides = {}) => db.query('select reserve_news_test_ai($1,$2,$3,$4,$5,$6,$7) r',
  [overrides.allowance || 'one-test', overrides.id || randomUUID(), overrides.stage || 'swedish_ev_article',
    overrides.model || 'gpt-5.4-mini', overrides.input ?? 20000, overrides.output ?? 2500, 'a'.repeat(64)]).then(r => r.rows[0].r);
const settle = id => db.query('select settle_news_ai($1,1000,1000,$2) r', [id, JSON.stringify(body)]).then(r => r.rows[0].r);
const denied = promise => assert.rejects(promise, e => e.code === '42501');
try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    grant usage on schema public to anon,authenticated,service_role;
    create table canonical_models(id uuid primary key);`);
  for (const file of ['007_news_engine.sql','012_news_release_guardrails.sql','013_news_unknown_usage_accounting.sql',
    '014_news_single_test_allowance.sql','014_news_single_test_allowance.sql']) {
    await db.exec(await readFile(new URL('../database/migrations/' + file, import.meta.url), 'utf8'));
  }
  await db.exec(`update news_ai_config set pricing_valid_until=current_date+30;
    insert into news_test_allowances(id,expires_at,maximum_micro_usd,maximum_requests,approval_note)
    values('one-test',clock_timestamp()+interval '1 hour',100000,3,'Owner approved at most USD 0.10 for this private test only.');`);
  for (const role of ['anon','authenticated']) {
    await db.exec('set role ' + role);
    await denied(reserve());
    await denied(db.query('select * from news_test_allowances'));
    await denied(db.query("select close_news_test_allowance('one-test')"));
    await db.exec('reset role');
  }
  await db.exec('set role service_role');
  await denied(db.exec("insert into news_test_allowances(id) values('unauthorized')"));
  await denied(db.exec('update news_test_allowances set maximum_micro_usd=100000'));
  await denied(db.exec('update news_ai_config set enabled=true'));
  assert.equal((await reserve({ allowance: 'missing' })).allowed, false);
  assert.equal((await reserve({ stage: 'ev_news_facts' })).allowed, false);
  assert.equal((await reserve({ model: 'another-model' })).allowed, false);
  const first = await reserve();
  assert.equal(first.allowed, true);
  assert.equal((await reserve()).reason, 'private_test_unresolved_accounting');
  assert.equal((await settle(first.request_id)).settled, true);
  assert.equal((await reserve({ id: first.request_id })).reason, 'news_request_already_reserved');
  for (let n=0; n<2; n++) { const r=await reserve(); assert.equal(r.allowed,true); await settle(r.request_id); }
  assert.equal((await reserve()).reason, 'private_test_allowance_exhausted');
  assert.equal(Number((await db.query("select sum(charged_micro_usd) n from news_ai_requests where test_allowance_id='one-test'")).rows[0].n), 15750);
  await db.exec(`reset role; truncate news_ai_requests;
    update news_test_allowances set maximum_micro_usd=20000,maximum_requests=3;
    set role service_role;`);
  assert.equal((await reserve()).reason, 'private_test_allowance_exhausted');
  await db.exec(`reset role; update news_test_allowances set maximum_micro_usd=100000,
    expires_at=clock_timestamp()-interval '1 minute',issued_at=clock_timestamp()-interval '2 minutes'; set role service_role;`);
  assert.equal((await reserve()).reason, 'private_test_allowance_inactive');
  await db.exec(`reset role; update news_test_allowances set issued_at=clock_timestamp(),expires_at=clock_timestamp()+interval '1 hour';
    update news_ai_config set publication_enabled=true; set role service_role;`);
  assert.equal((await reserve()).reason, 'private_test_requires_production_paused');
  await db.exec(`reset role; update news_ai_config set publication_enabled=false; set role service_role;`);
  assert.equal((await db.query("select close_news_test_allowance('one-test') r")).rows[0].r.closed,true);
  assert.equal((await reserve()).reason, 'private_test_allowance_inactive');
  const cfg=(await db.query('select * from news_ai_config')).rows[0];
  assert.equal(cfg.enabled,false); assert.equal(cfg.publication_enabled,false);
  assert.equal(Number(cfg.daily_limit_micro_usd),250000); assert.equal(Number(cfg.monthly_limit_micro_usd),5000000);
  console.log(JSON.stringify({news_test_allowance_ok:true,idempotent:true,owner_issued_only:true,
    ordinary_caps_unchanged:true,production_remains_off:true,strict_cost_and_call_bounds:true,
    reservations_and_settlement:true,expiry_and_close:true,public_denials:true}));
} finally { await db.close(); }
