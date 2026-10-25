import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';

const db = new PGlite();
const migration = await readFile(new URL('../database/migrations/012_news_release_guardrails.sql', import.meta.url), 'utf8');
const accounting = await readFile(new URL('../database/migrations/013_news_unknown_usage_accounting.sql', import.meta.url), 'utf8');
const initial = await readFile(new URL('../database/migrations/007_news_engine.sql', import.meta.url), 'utf8');
const notices = await readFile(new URL('../database/migrations/017_news_notice_publication.sql', import.meta.url), 'utf8');
const policy = 'news-editorial-2026-10-v2';
const body = { model: 'gpt-5.4-mini', service_tier: 'default', status: 'completed', output: [] };
const reserve = (id = randomUUID()) => db.query('select reserve_news_ai($1,$2,$3,$4,$5,$6) as r',
  [id, 'ev_news_facts', 'gpt-5.4-mini', 1000, 500, 'a'.repeat(64)]).then(r => ({ id, ...r.rows[0].r }));
const settle = (id, input, output, response = body) => db.query('select settle_news_ai($1,$2,$3,$4) as r',
  [id, input, output, JSON.stringify(response)]).then(r => r.rows[0].r);
const closureNote = 'Owner approved retaining the full reservation in budget; actual provider usage remains unknown.';
const closeUnknown = (id, amount = 3000, digest = 'a'.repeat(64), note = closureNote) => db.query(
  'select close_news_unknown_usage_budget($1,$2,$3,$4) as r', [id, amount, digest, note]).then(r => r.rows[0].r);
const denied = promise => assert.rejects(promise, e => e.code === '42501');
const resetBudget = async () => {
  await db.exec(`reset role; truncate news_ai_requests;
    update news_ai_config set enabled=true, publication_enabled=false,
    daily_limit_micro_usd=250000,monthly_limit_micro_usd=5000000,pricing_valid_until=current_date+30`);
};
const publish = id => db.query('select publish_news_article($1)', [id]);
const makeDraft = async (id, { stale = false, inaccessible = false, extraSource = false } = {}) => {
  await db.query('insert into news_story_clusters(id,event_key,payload) values($1,$1,$2)', [id, '{}']);
  const item = `item-${id}`;
  const url = `https://press.example.com/${id}`;
  await db.query("insert into news_items(id,source_id,url,status,payload) values($1,'official',$2,'processed',$3)",
    [item, url, JSON.stringify({ access_status: inaccessible ? 'blocked' : 'accessible', content_hash: 'verified-hash' })]);
  const payload = { title: 'Swedish test article', intro: 'Supported introduction', secret_internal: 'private',
    title_fact_ids: ['private-id'], editorial_policy: policy,
    paragraphs: [{ text: 'First supported paragraph', kind: 'reporting', fact_ids: ['private-id'] },
      { text: 'Second supported paragraph', kind: 'analysis', fact_ids: ['private-id'] }],
    sources: [{ item_id: item, url, publisher: 'Official', title: 'Release' },
      ...(extraSource ? [{ item_id: 'missing', url: 'https://press.example.com/missing' }] : [])] };
  const article = (await db.query("insert into news_articles(id,cluster_id,slug,status,payload,published_at) values($1,$1,$1,'draft',$2,'1900-01-01') returning artifact_hash",
    [id, JSON.stringify(payload)])).rows[0];
  await db.query('insert into news_article_sources(id,article_id,item_id,payload) values($1,$2,$3,$4)', [`link-${id}`, id, item, '{}']);
  for (const kind of ['evidence', 'editorial', 'originality']) {
    await db.query('insert into news_quality_checks(id,article_id,kind,artifact_hash,passed,payload) values($1,$2,$3,$4,true,$5)',
      [`${id}-${kind}`, id, kind, stale ? 'stale-hash' : article.artifact_hash, JSON.stringify({ policy_version: policy })]);
  }
};

try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls; create role outsider;
    grant usage on schema public to anon,authenticated,service_role,outsider;
    create table canonical_models(id uuid primary key, name text, brand text, model text);
    insert into canonical_models values('00000000-0000-4000-8000-000000000001','Untouched vehicle','Untouched','Vehicle');
    create view public_ev_variants as select * from canonical_models;`);
  const vehicles = (await db.query('select * from canonical_models')).rows;
  await db.exec(initial);
  await db.exec(migration);
  await db.exec(migration);
  await db.exec(accounting);
  await db.exec(accounting);
  await db.exec(notices);
  assert.deepEqual((await db.query('select * from canonical_models')).rows, vehicles);
  const config = (await db.query('select * from news_ai_config')).rows[0];
  assert.equal(config.enabled, false);
  assert.equal(config.publication_enabled, false);
  assert.equal(Number(config.daily_limit_micro_usd), 250000);
  assert.equal(Number(config.monthly_limit_micro_usd), 5000000);
  const readinessSql = await readFile(new URL('../database/checks/news_release_readiness.sql', import.meta.url), 'utf8');
  const readiness = (await db.query(readinessSql)).rows;
  for (const check of readiness.slice(0, 7)) assert.equal(check.result, 'true', check.check_name);
  for (const name of ['12 Unknown usage closure owner-only', '13 Unknown usage fully counted']) {
    assert.equal(readiness.find(check => check.check_name === name).result, 'true', name);
  }

  for (const role of ['anon', 'authenticated', 'outsider']) {
    await db.exec(`set role ${role}`);
    for (const table of ['news_sources','news_items','news_articles','news_quality_checks','news_ai_config','news_ai_requests']) {
      await denied(db.query(`select * from ${table}`));
    }
    await denied(reserve());
    await denied(closeUnknown(randomUUID()));
    await denied(publish('none'));
    await denied(db.query("update public_news_articles set slug='unsafe'"));
    if (role !== 'outsider') assert.equal((await db.query('select * from public_news_articles')).rows.length, 0);
    await db.exec('reset role');
  }
  await db.exec('set role service_role');
  assert.equal((await reserve()).allowed, false);
  await denied(db.query('update news_ai_config set enabled=true'));
  await denied(db.query('delete from news_ai_requests'));
  await denied(db.query("insert into news_ai_requests(id) values(gen_random_uuid())"));
  await denied(closeUnknown(randomUUID()));
  await denied(db.query('update news_ai_requests set budget_closed_at=now()'));
  await resetBudget();
  await db.exec('update news_ai_config set daily_limit_micro_usd=7000; set role service_role');
  const batch = await Promise.all(Array.from({ length: 10 }, () => reserve()));
  const granted = batch.filter(r => r.allowed);
  assert.equal(granted.length, 2);
  assert.equal((await reserve(granted[0].id)).reason, 'news_request_already_reserved');
  assert.equal((await settle(granted[0].id, 100, 100)).charged_micro_usd, 525);
  assert.equal((await settle(granted[0].id, 100, 100)).settled, true);
  assert.equal((await reserve()).allowed, true);
  assert.equal((await reserve()).allowed, false);
  const unknown = await settle(granted[1].id, null, null);
  assert.equal(unknown.settled, false);
  assert.equal(Number((await db.query('select charged_micro_usd from news_ai_requests where id=$1', [granted[1].id])).rows[0].charged_micro_usd), 3000);

  await resetBudget();
  await reserve();
  await db.exec("update news_ai_requests set created_at=date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'-interval '1 minute'; update news_ai_config set daily_limit_micro_usd=3000");
  assert.equal((await reserve()).allowed, true);
  assert.equal((await reserve()).allowed, false);
  await resetBudget();
  await reserve();
  await db.exec("update news_ai_config set monthly_limit_micro_usd=3000");
  assert.equal((await reserve()).allowed, false);
  await db.exec("update news_ai_requests set created_at=date_trunc('month',now() at time zone 'UTC') at time zone 'UTC'-interval '1 minute'");
  assert.equal((await reserve()).allowed, true);
  await resetBudget();
  await db.exec('update news_ai_config set pricing_valid_until=current_date');
  assert.equal((await reserve()).reason, 'news_pricing_expired');
  await resetBudget();
  const anomaly = await reserve();
  assert.equal((await settle(anomaly.id, 2000, 600)).settled, false);
  assert.equal((await reserve()).reason, 'news_budget_disabled');
  await resetBudget();
  const wrongTier = await reserve();
  assert.equal((await settle(wrongTier.id, 10, 10, { ...body, service_tier: 'priority' })).settled, false);
  assert.equal((await reserve()).reason, 'news_budget_disabled');

  await resetBudget();
  const known = await reserve();
  assert.equal((await settle(known.id, 1000, 500)).charged_micro_usd, 3000);
  await db.exec('reset role; update news_ai_config set enabled=false,publication_enabled=false');
  await db.query("update news_ai_requests set created_at=clock_timestamp()-interval '10 minutes' where id=$1", [known.id]);
  await assert.rejects(closeUnknown(known.id), /requires_unknown_usage/);

  await resetBudget();
  const held = await reserve();
  await db.exec('reset role; update news_ai_config set enabled=false,publication_enabled=false');
  await assert.rejects(closeUnknown(held.id, 3000, 'b'.repeat(64)), /request_mismatch/);
  await assert.rejects(closeUnknown(held.id, 2999), /request_mismatch/);
  await assert.rejects(closeUnknown(held.id, 3000, 'a'.repeat(64), 'too short'), /approval_note_required/);
  await assert.rejects(closeUnknown(randomUUID()), /request_missing/);
  await assert.rejects(closeUnknown(held.id), /request_too_recent/);
  await db.query("update news_ai_requests set created_at=clock_timestamp()-interval '10 minutes' where id=$1", [held.id]);
  const original = (await db.query('select to_jsonb(r) as r from news_ai_requests r where id=$1', [held.id])).rows[0].r;
  const originalConfig = (await db.query('select to_jsonb(c) as c from news_ai_config c')).rows[0].c;
  await db.exec('update news_ai_config set enabled=true');
  await assert.rejects(closeUnknown(held.id), /requires_paused_engine/);
  await db.exec('update news_ai_config set enabled=false,publication_enabled=true');
  await assert.rejects(closeUnknown(held.id), /requires_paused_engine/);
  await db.exec('update news_ai_config set publication_enabled=false');
  await db.query('insert into news_ingestion_runs(id,payload) values($1,$2)',
    [held.id, JSON.stringify({ kind: 'news_ai_request', state: 'usage_observed', input_tokens: 100, output_tokens: 100 })]);
  await assert.rejects(closeUnknown(held.id), /known_usage_requires_normal_settlement/);
  await db.query('delete from news_ingestion_runs where id=$1', [held.id]);
  const closed = await closeUnknown(held.id);
  assert.equal(closed.budget_closed, true);
  assert.equal(closed.usage_known, false);
  assert.equal(closed.counted_micro_usd, 3000);
  assert.equal((await closeUnknown(held.id)).already_closed, true);
  await assert.rejects(closeUnknown(held.id, 3000, 'a'.repeat(64), closureNote + ' changed'), /approval_mismatch/);
  const retained = (await db.query('select to_jsonb(r) as r from news_ai_requests r where id=$1', [held.id])).rows[0].r;
  assert.ok(retained.budget_closed_at);
  assert.ok(retained.budget_closed_by);
  assert.equal(retained.budget_closure_note, closureNote);
  for (const key of Object.keys(original).filter(key => !key.startsWith('budget_clos'))) {
    assert.deepEqual(retained[key], original[key], key);
  }
  assert.deepEqual((await db.query('select to_jsonb(c) as c from news_ai_config c')).rows[0].c, originalConfig);
  await db.exec(accounting);
  assert.deepEqual((await db.query('select to_jsonb(r) as r from news_ai_requests r where id=$1', [held.id])).rows[0].r, retained);
  await assert.rejects(db.query('delete from news_ai_requests where id=$1', [held.id]), /closure_immutable/);
  await assert.rejects(db.query('update news_ai_requests set budget_closed_at=null where id=$1', [held.id]), /closure_immutable/);
  await db.exec('set role service_role');
  await denied(closeUnknown(held.id));
  await assert.rejects(settle(held.id, 100, 100), /closure_immutable/);
  const pendingSql = 'select id from news_ai_requests where settled_at is null and budget_closed_at is null';
  assert.equal((await db.query(pendingSql)).rows.length, 0);
  assert.equal(Number((await db.query('select sum(charged_micro_usd) as amount from news_ai_requests')).rows[0].amount), 3000);
  await db.exec('reset role; update news_ai_config set enabled=true');
  const next = await reserve();
  assert.equal(next.allowed, true);
  assert.deepEqual((await db.query(pendingSql)).rows.map(row => row.id), [next.id]);
  assert.equal(Number((await db.query('select sum(charged_micro_usd) as amount from news_ai_requests')).rows[0].amount), 6000);
  await resetBudget();

  await db.exec("reset role; insert into news_sources(id,payload) values('official','{}')");
  await makeDraft('first');
  await assert.rejects(publish('first'), /publication disabled/);
  await db.exec('update news_ai_config set publication_enabled=true');
  await makeDraft('stale', { stale: true });
  await assert.rejects(publish('stale'), /quality gates/);
  await makeDraft('blocked', { inaccessible: true });
  await assert.rejects(publish('blocked'), /source evidence/);
  await makeDraft('missing-source', { extraSource: true });
  await assert.rejects(publish('missing-source'), /source evidence/);
  await db.exec("update news_quality_checks set payload='{}' where article_id='first'");
  await assert.rejects(publish('first'), /quality gates/);
  await db.query('update news_quality_checks set payload=$1 where article_id=$2', [JSON.stringify({ policy_version: policy }), 'first']);
  await db.exec('set role service_role');
  await publish('first');
  await publish('first');
  const article = (await db.query("select * from news_articles where id='first'")).rows[0];
  assert.ok(new Date(article.published_at).getFullYear() > 2000);
  await assert.rejects(db.query("update news_articles set status='draft' where id='first'"), /immutable/);
  await denied(db.query("delete from news_articles where id='first'"));
  await db.exec('reset role');
  await makeDraft('second');
  await publish('second');
  await makeDraft('third');
  await assert.rejects(db.query("update news_articles set status='published' where id='third'"), /daily publication limit/);
  await db.exec('set role anon');
  const publicRows = (await db.query('select * from public_news_articles')).rows;
  assert.equal(publicRows.length, 2);
  const visible = publicRows[0].payload;
  assert.equal(visible.secret_internal, undefined);
  assert.equal(visible.title_fact_ids, undefined);
  assert.equal(visible.sources[0].item_id, undefined);
  assert.equal(visible.paragraphs[0].fact_ids, undefined);
  assert.deepEqual(visible.paragraphs.map(p => p.text), ['First supported paragraph', 'Second supported paragraph']);
  console.log(JSON.stringify({ news_release_sql_ok: true, idempotent: true, vehicle_data_unchanged: true,
    shared_budget: true, period_rollover: true, fail_closed: true, public_denials: true, publication_gates: true,
    owner_only_unknown_usage: true, conservative_cost_retained: true, unknown_usage_not_fabricated: true }));
} finally { await db.close(); }
