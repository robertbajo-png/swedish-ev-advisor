import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';

const db = new PGlite();
const reserve = (o = {}) => db.query('select reserve_news_ab_ai($1,$2,$3,$4,$5,$6,$7,$8,$9) r',
  [o.permit || 'ab', o.manifest || 'b'.repeat(64), o.cell || 'model-full', o.id || randomUUID(),
    o.stage || 'swedish_ev_article', o.model || 'gpt-5.4', o.input ?? 1000, o.output ?? 1000,
    'a'.repeat(64)]).then(r => r.rows[0].r);
const settle = (id, model = 'gpt-5.4', input = 200, output = 100, extra = {}) => db.query(
  'select settle_news_ab_ai($1,$2,$3,$4) r', [id, input, output, JSON.stringify({model,
    service_tier: 'default', status: 'completed', usage: {input_tokens: input, output_tokens: output}, ...extra})]
).then(r => r.rows[0].r);
const denied = p => assert.rejects(p, e => e.code === '42501');
try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    grant usage on schema public to anon,authenticated,service_role;
    create table canonical_models(id uuid primary key);`);
  for (const file of ['007_news_engine.sql','012_news_release_guardrails.sql','013_news_unknown_usage_accounting.sql',
    '014_news_single_test_allowance.sql','015_news_private_ab_test.sql','015_news_private_ab_test.sql']) {
    await db.exec(await readFile(new URL('../database/migrations/' + file, import.meta.url),'utf8'));
  }
  await db.exec(`update news_ai_config set pricing_valid_until=current_date+30;
    insert into news_ab_test_permits(id,expires_at,maximum_micro_usd,manifest_hash,approval_note)
    values('ab',clock_timestamp()+interval '1 hour',200000,repeat('b',64),'Owner approved one private A/B test within the ordinary shared caps.');`);
  for (const role of ['anon','authenticated']) {
    await db.exec('set role ' + role);
    await denied(reserve());
    await denied(db.query('select * from news_ab_test_permits'));
    await denied(db.query("select close_news_ab_test('ab')"));
    await denied(settle(randomUUID()));
    await db.exec('reset role');
  }
  await db.exec('set role service_role');
  await denied(db.exec('update news_ab_test_permits set maximum_micro_usd=200000'));
  await denied(db.exec("insert into news_ab_test_permits(id) values('unauthorized')"));
  assert.equal((await reserve({permit:'missing'})).allowed,false);
  assert.equal((await reserve({manifest:'c'.repeat(64)})).allowed,false);
  for (const o of [{cell:'unknown-full'}, {stage:'ev_news_block_repair'}, {model:'another-model'},
    {cell:'model-mini'}, {stage:'ev_news_independent_audit'}, {input:0}]) {
    assert.equal((await reserve(o)).allowed,false);
  }
  const full = await reserve();
  assert.equal(full.allowed,true); assert.equal(Number(full.reserved_micro_usd),17500);
  assert.equal((await reserve({cell:'price-full'})).reason,'ab_unresolved_accounting');
  assert.equal((await settle(full.request_id,'gpt-5.4-2026-03-05')).charged_micro_usd,2000);
  assert.equal((await settle(full.request_id)).settled,true);
  assert.equal((await reserve()).reason,'ab_attempt_already_consumed');
  const mini = await reserve({cell:'model-mini',model:'gpt-5.4-mini'});
  assert.equal(Number(mini.reserved_micro_usd),5250);
  assert.equal(Number((await settle(mini.request_id,'gpt-5.4-mini')).charged_micro_usd),600);
  const audit = await reserve({stage:'ev_news_independent_audit',model:'gpt-5.4-mini'});
  assert.equal(audit.allowed,true); await settle(audit.request_id,'gpt-5.4-mini');
  await db.exec(`reset role; update news_ab_test_permits set maximum_micro_usd=3200; set role service_role;`);
  assert.equal((await reserve({cell:'price-full'})).reason,'ab_ordinary_budget_exhausted');
  await db.exec(`reset role; update news_ab_test_permits set maximum_micro_usd=200000;
    insert into news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,
      charged_micro_usd,provider_status,settled_at) values('${randomUUID()}','old','gpt-5.4-mini',repeat('d',64),1,1,240000,240000,'completed',now());
    set role service_role;`);
  assert.equal((await reserve({cell:'price-full'})).reason,'ab_ordinary_budget_exhausted');
  await db.exec(`reset role; delete from news_ai_requests where stage='old';
    update news_ai_config set enabled=true; set role service_role;`);
  assert.equal((await reserve({cell:'price-full'})).reason,'ab_requires_paused_unchanged_production');
  await db.exec(`reset role; update news_ai_config set enabled=false; set role service_role;`);
  const unknown = await reserve({cell:'price-full'});
  assert.equal((await settle(unknown.request_id,'gpt-5.4',200,100,{usage:{}})).reason,'ab_unknown_usage_reservation_retained');
  assert.equal((await db.query('select charged_micro_usd from news_ai_requests where id=$1',[unknown.request_id])).rows[0].charged_micro_usd,17500);
  assert.equal((await settle(unknown.request_id,'gpt-5.4-mini')).reason,'ab_unexpected_provider_pricing_halted');
  assert.equal((await reserve({cell:'statistics-full'})).allowed,false);
  // An observed charge is still settled after closure; closure is never a refund.
  assert.equal((await settle(unknown.request_id)).settled,true);
  assert.equal((await db.query("select close_news_ab_test('ab') r")).rows[0].r.closed,true);
  await denied(db.exec('update news_ai_config set enabled=true'));
  const cfg=(await db.query('select * from news_ai_config')).rows[0];
  assert.equal(cfg.enabled,false); assert.equal(cfg.publication_enabled,false);
  assert.equal(Number(cfg.daily_limit_micro_usd),250000); assert.equal(Number(cfg.monthly_limit_micro_usd),5000000);
  assert.equal(cfg.model,'gpt-5.4-mini');
  console.log(JSON.stringify({news_ab_budget_ok:true,idempotent:true,ordinary_caps_only:true,
    two_model_rates:true,common_reviewer:true,one_attempt_per_cell_stage:true,owner_only_issuance:true,
    unknown_usage_retained:true,model_mismatch_halts:true,production_off:true,public_denials:true}));
} finally { await db.close(); }
