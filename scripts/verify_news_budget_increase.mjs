import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';

const db = new PGlite();
const sql = name => readFile(new URL('../database/migrations/' + name, import.meta.url), 'utf8');
const migration = await sql('022_news_budget_050_10.sql');
const config = async () => (await db.query('select * from news_ai_config')).rows[0];
const permissions = async () => (await db.query(`select relname,relacl::text,relrowsecurity from pg_class
  where relnamespace='public'::regnamespace and relname in ('news_ai_config','news_ai_requests','news_articles') order by relname`)).rows;
const routines = async () => (await db.query(`select proname,pg_get_functiondef(oid) as definition,proacl::text
  from pg_proc where pronamespace='public'::regnamespace order by proname`)).rows;
const reserve = async () => (await db.query('select reserve_news_ai($1,$2,$3,$4,$5,$6) r',
  [randomUUID(), 'swedish_ev_article', 'gpt-6-sol', 1000, 500, 'a'.repeat(64)])).rows[0].r;
const denied = promise => assert.rejects(promise, e => e.code === '42501');
const plain = x => JSON.parse(JSON.stringify(x));
async function fixtureCharge(amount) {
  const id = randomUUID();
  await db.query(`insert into news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,
    reserved_micro_usd,charged_micro_usd,settled_at,provider_status) values($1,'budget_fixture','gpt-6-sol',$2,
    1000,500,$3,$3,now(),'completed')`, [id,'c'.repeat(64),amount]);
  return id;
}

try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    grant usage on schema public to anon,authenticated,service_role;
    create table canonical_models(id uuid primary key, brand text, model text);
    insert into canonical_models values('00000000-0000-4000-8000-000000000001','Unchanged','Vehicle');
    create view public_ev_variants as select * from canonical_models;`);
  for (const name of ['007_news_engine.sql','012_news_release_guardrails.sql','013_news_unknown_usage_accounting.sql',
                      '017_news_notice_publication.sql','018_news_gpt6_sol.sql']) await db.exec(await sql(name));
  await db.exec(`update news_ai_config set enabled=true,publication_enabled=true,daily_article_limit=1,pricing_valid_until=current_date+30`);
  const unknown = randomUUID();
  await db.query(`insert into news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,
    charged_micro_usd,budget_closed_at,budget_closed_by,budget_closure_note) values($1,'swedish_ev_article','gpt-5.4-mini',$2,
    1000,500,20868,20868,now(),'postgres','Synthetic conservative old maximum')`, [unknown, 'b'.repeat(64)]);
  const before = {config: plain(await config()), usage: (await db.query('select * from news_ai_requests')).rows,
                  vehicles: (await db.query('select * from canonical_models')).rows,
                  permissions: await permissions(), routines: await routines()};
  await db.exec(migration);
  const after = plain(await config());
  assert.equal(Number(after.daily_limit_micro_usd), 500000);
  assert.equal(Number(after.monthly_limit_micro_usd), 10000000);
  for (const key of Object.keys(before.config).filter(k => !['daily_limit_micro_usd','monthly_limit_micro_usd','approval_note'].includes(k))) {
    assert.deepEqual(after[key], before.config[key], key + ' must not change');
  }
  assert.deepEqual((await db.query('select * from news_ai_requests')).rows, before.usage);
  assert.deepEqual((await db.query('select * from canonical_models')).rows, before.vehicles);
  assert.deepEqual(await permissions(), before.permissions);
  assert.deepEqual(await routines(), before.routines);
  assert.equal((await db.query('select enabled from news_notice_release_config')).rows[0].enabled, false);
  await db.exec(migration);
  assert.deepEqual(plain(await config()), after, 'Idempotent install must not rewrite notes or switches');
  for (const [field, value] of [['daily_limit_micro_usd',500001], ['monthly_limit_micro_usd',10000001]]) {
    await assert.rejects(db.exec(`update news_ai_config set ${field}=${value}`), e => e.code === '23514');
  }
  for (const role of ['anon','authenticated','service_role']) {
    await db.exec('set role ' + role);
    await denied(db.exec('update news_ai_config set daily_limit_micro_usd=500001'));
    await denied(db.exec(migration));
    await db.exec('reset role');
  }

  // Evaluate the backup's actual generated read-only SQL, not a duplicate predicate.
  const probe = spawnSync(process.execPath, ['scripts/run_python.mjs', '-c',
    'import sys; sys.path.insert(0,"scripts"); from production_backup import preflight_sql; print(preflight_sql())'],
    {encoding: 'utf8', windowsHide: true, timeout: 45000});
  assert.equal(probe.status, 0, 'Backup SQL fixture must load without credentials/network');
  const backupState = async () => (await db.exec(probe.stdout)).find(r => r.rows?.[0]?.json_build_object)?.rows[0].json_build_object;
  assert.equal((await backupState()).news_safe, true);
  await db.exec('update news_ai_config set daily_limit_micro_usd=250000');
  assert.equal((await backupState()).news_safe, false, 'Mixed active caps are not an approved backup boundary');
  await db.exec('update news_ai_config set monthly_limit_micro_usd=5000000');
  assert.equal((await backupState()).news_safe, true);
  await db.exec('update news_ai_config set daily_limit_micro_usd=500000,monthly_limit_micro_usd=10000000');

  await assert.rejects(db.query('update news_ai_requests set charged_micro_usd=300000 where id=$1', [unknown]), /immutable/);
  await fixtureCharge(279132);
  await db.exec('set role service_role');
  const allowed = await reserve();
  assert.equal(allowed.allowed, true, 'New ordinary daily allowance works beyond the old USD0.25 ceiling');
  assert.equal(allowed.reserved_micro_usd, 10000);
  assert.equal((await reserve()).reason, 'news_unresolved_accounting');
  await db.exec('reset role');
  await assert.rejects(db.exec(migration), /Reconcile news usage/);
  await db.query(`delete from news_ai_requests where id<>$1 and settled_at is null`, [unknown]);
  const extra = await fixtureCharge(199001);
  await db.exec('set role service_role');
  assert.equal((await reserve()).reason, 'news_budget_exhausted');
  await db.exec('reset role');
  await db.query('delete from news_ai_requests where id=$1', [extra]);
  await db.exec('update news_ai_config set monthly_limit_micro_usd=300001; set role service_role');
  assert.equal((await reserve()).reason, 'news_budget_exhausted', 'Monthly ceiling remains independent');
  await db.exec('reset role');
  assert.deepEqual((await db.query('select * from news_ai_requests where id=$1', [unknown])).rows, before.usage);
  console.log(JSON.stringify({news_budget_increase: 'passed', idempotent: true, daily_usd: 0.5, monthly_usd: 10,
    retained_usage: true, no_activation_or_price_changes: true, publication_limit_preserved: true,
    acl_and_publish_routines_unchanged: true, backup_profiles_verified: true, paid_calls: 0, production_writes: 0}));
} catch (error) {
  console.error(JSON.stringify({news_budget_increase:'failed',code:error.code,
    check:String(error.message).slice(0,300),paid_calls:0,production_writes:0}));
  process.exitCode=1;
} finally { await db.close(); }
