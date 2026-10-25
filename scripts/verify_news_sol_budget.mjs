import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';

const db = new PGlite();
const sql = async name => readFile(new URL(`../database/migrations/${name}`, import.meta.url), 'utf8');
const migration = await sql('018_news_gpt6_sol.sql');
const reserve = (model='gpt-6-sol', input=1000, output=500, stage='ev_news_hybrid_launch_write') => {
  const id = randomUUID();
  return db.query('select reserve_news_ai($1,$2,$3,$4,$5,$6) r', [id,stage,model,input,output,'a'.repeat(64)])
    .then(r => ({id,...r.rows[0].r}));
};
const response = (input=1000, output=100, cached=0, w30=0, w12=0) => ({
  model:'gpt-6-sol', service_tier:'default', status:'completed',
  usage:{input_tokens:input,output_tokens:output,total_tokens:input+output,
    input_tokens_details:{cached_tokens:cached,cache_write_tokens:w30+w12,
      ...(w30+w12 ? {cache_write_tokens_details:{ttl_30m_tokens:w30,ttl_12h_tokens:w12}} : {})}}, output:[]
});
const settle = (id, body=response(), input=body.usage.input_tokens, output=body.usage.output_tokens) => db.query(
  'select settle_news_ai($1,$2,$3,$4) r', [id,input,output,JSON.stringify(body)]).then(r => r.rows[0].r);
const denied = p => assert.rejects(p, e => e.code==='42501');
const reset = async () => db.exec(`reset role; truncate news_ai_requests;
  update news_ai_config set enabled=true, publication_enabled=false,model='gpt-6-sol',
    daily_limit_micro_usd=250000,monthly_limit_micro_usd=5000000,pricing_valid_until=current_date+30;
  set role service_role;`);

try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    grant usage on schema public to anon,authenticated,service_role;
    create table canonical_models(id uuid primary key, brand text, model text);
    insert into canonical_models values('00000000-0000-4000-8000-000000000001','Untouched','Vehicle');
    create view public_ev_variants as select * from canonical_models;`);
  for (const file of ['007_news_engine.sql','012_news_release_guardrails.sql','013_news_unknown_usage_accounting.sql','017_news_notice_publication.sql']) await db.exec(await sql(file));
  const unknown = randomUUID();
  await db.query(`insert into news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,
    charged_micro_usd,budget_closed_at,budget_closed_by,budget_closure_note) values($1,'swedish_ev_article','gpt-5.4-mini',$2,1000,500,20868,20868,now(),'postgres','Preserve unknown maximum')`, [unknown,'b'.repeat(64)]);
  const baseline = (await db.query('select * from news_ai_requests')).rows;
  const vehicles = (await db.query('select * from canonical_models')).rows;
  await db.exec(migration);
  await db.exec(migration);
  assert.deepEqual((await db.query('select * from news_ai_requests')).rows,baseline);
  assert.deepEqual((await db.query('select * from canonical_models')).rows,vehicles);
  const cfg = (await db.query('select * from news_ai_config')).rows[0];
  assert.equal(cfg.model,'gpt-6-sol');
  assert.equal(cfg.enabled,false); assert.equal(cfg.publication_enabled,false);
  assert.equal(Number(cfg.daily_limit_micro_usd),250000); assert.equal(Number(cfg.monthly_limit_micro_usd),5000000);
  assert.equal((await db.query('select enabled from news_notice_release_config')).rows[0].enabled,false);
  for (const role of ['anon','authenticated']) {
    await db.exec(`set role ${role}`);
    await denied(reserve()); await denied(db.query('select * from news_ai_requests'));
    await denied(db.query('update news_ai_config set enabled=true'));
    await db.exec('reset role');
  }
  await db.exec('set role service_role');
  assert.equal((await reserve()).reason,'news_budget_disabled');
  await denied(db.query("update news_ai_config set model='gpt-5.4-mini'"));
  await denied(db.query('delete from news_ai_requests'));

  await reset();
  assert.equal((await reserve('gpt-5.4-mini')).allowed,false);
  assert.equal((await reserve('gpt-6.1-sol')).allowed,false);
  const first = await reserve();
  assert.equal(first.reserved_micro_usd,10000);
  assert.equal((await reserve()).reason,'news_unresolved_accounting');
  assert.equal((await settle(first.id)).charged_micro_usd,3000);
  assert.equal((await settle(first.id)).settled,true);
  assert.equal((await settle(first.id,{...response(),status:'incomplete'})).settled,false);
  for (const [cached,w30,w12,expected] of [[100,300,100,3270],[0,0,1000,6000],[1000,0,0,1200],[0,0,0,3000]]) {
    const req = await reserve(); assert.equal(req.allowed,true);
    assert.equal((await settle(req.id,response(1000,100,cached,w30,w12))).charged_micro_usd,expected);
  }
  await reset();
  const missing = await reserve();
  const incomplete = response(); delete incomplete.usage.input_tokens_details.cache_write_tokens;
  assert.equal((await settle(missing.id,incomplete)).settled,false);
  assert.equal(Number((await db.query('select charged_micro_usd from news_ai_requests where id=$1',[missing.id])).rows[0].charged_micro_usd),10000);
  await reset();
  const mismatch = await reserve();
  assert.equal((await settle(mismatch.id,response(),999,100)).settled,false);
  const malformed = response(); malformed.usage.input_tokens_details.cache_write_tokens=20;
  assert.equal((await settle(mismatch.id,malformed)).settled,false);
  await reset();
  const wrong = await reserve();
  assert.equal((await settle(wrong.id,{...response(),model:'gpt-6.1-sol'})).settled,false);
  assert.equal((await reserve()).reason,'news_budget_disabled');
  await reset();
  const fast = await reserve();
  assert.equal((await settle(fast.id,{...response(),service_tier:'fast'})).settled,false);
  assert.equal((await reserve()).reason,'news_budget_disabled');
  await reset();
  const anomaly = await reserve();
  assert.equal((await settle(anomaly.id,response(2000,600))).settled,false);
  assert.equal((await reserve()).reason,'news_budget_disabled');
  await reset();
  const hold = await reserve();
  await db.exec('reset role');
  await db.query("update news_ai_requests set charged_micro_usd=240001,reserved_micro_usd=240001,budget_closed_at=now(),budget_closed_by='postgres',budget_closure_note='Preserve full prior maximum' where id=$1",[hold.id]);
  await db.exec('set role service_role');
  assert.equal((await reserve()).reason,'news_budget_exhausted');
  assert.equal((await settle(hold.id)).reason,'news_budget_closed_hold_preserved');
  await db.exec('reset role; update news_ai_config set enabled=false');
  const before = (await db.query('select * from news_ai_requests')).rows;
  await db.exec(migration);
  assert.deepEqual((await db.query('select * from news_ai_requests')).rows,before);
  await db.exec("update news_ai_config set enabled=true,model='gpt-5.4-mini'; set role service_role");
  const old = await reserve('gpt-5.4-mini');
  assert.equal(old.reserved_micro_usd,3000);
  assert.equal((await settle(old.id,{model:'gpt-5.4-mini',service_tier:'default',status:'completed'},100,100)).charged_micro_usd,525);
  console.log(JSON.stringify({news_sol_budget_ok:true,default_off:true,caps_unchanged:true,
    old_ledger_preserved:true,no_vehicle_changes:true,cache_tiers_priced:true,unknown_usage_held:true,
    mismatches_fail_closed:true,public_denials:true,legacy_settlement:true,paid_calls:0}));
} finally { await db.close(); }
