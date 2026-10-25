"""Owner-run single AI-article release. No paid AI or persistent activation."""
import json
import re
from datetime import datetime, timezone

from news_ai import response_json
from news_short_articles import AI_ARTICLE_KINDS, RECIPE, precheck, review_check
from news_store import artifact_hash
from run_short_news import code_hash, matrix_valid, state_id


RECEIPT_FIELDS = ('id', 'stage', 'model', 'settled_at', 'provider_status', 'request_hash',
                  'response_payload', 'charged_micro_usd', 'input_tokens', 'output_tokens')


def source_snapshot_sql(article_id):
    key = "'" + article_id.replace("'", "''") + "'"
    fields = ','.join("'" + k + "',r." + k for k in RECEIPT_FIELDS)
    return f"""jsonb_build_object(
      'item',(select to_jsonb(i)-'updated_at' from public.news_items i where id=a.payload->'sources'->0->>'item_id'),
      'source',(select to_jsonb(s)-'updated_at' from public.news_sources s where id=a.payload->'short_brief'->'item'->>'source_id'),
      'cluster',(select to_jsonb(c)-'updated_at' from public.news_story_clusters c where id=a.cluster_id),
      'checks',(select coalesce(jsonb_agg(to_jsonb(q)-'updated_at' order by q.id),'[]'::jsonb) from public.news_quality_checks q where article_id={key}),
      'links',(select coalesce(jsonb_agg(to_jsonb(l)-'updated_at' order by l.id),'[]'::jsonb) from public.news_article_sources l where article_id={key}),
      'vehicles',(select coalesce(jsonb_agg(to_jsonb(v)-'updated_at' order by v.id),'[]'::jsonb) from public.news_vehicle_links v where article_id={key}),
      'receipts',(select coalesce(jsonb_agg(jsonb_build_object({fields}) order by r.id),'[]'::jsonb) from public.news_ai_requests r
        where r.id::text in (select jsonb_array_elements_text(a.payload->'live_request_ids'))))"""


def prepare_single_release(store, article_id, now=None):
    now = now or datetime.now(timezone.utc)
    gate = store.get('news_ingestion_runs', state_id())
    if not gate or not matrix_valid(store, gate['payload']) or gate['payload'].get('passed') is not True:
        raise ValueError('single_article_mixed_format_proofs_required')
    a = store.get('news_articles', article_id)
    if not a or a['status'] != 'draft' or not re.fullmatch(r'[a-f0-9]{64}', a['artifact_hash']):
        raise ValueError('single_article_requires_exact_draft')
    p = a['payload']
    if p.get('editorial_recipe') != RECIPE or p.get('short_brief', {}).get('kind') not in AI_ARTICLE_KINDS:
        raise ValueError('single_article_wrong_format')
    brief = p['short_brief']
    article = {k: p[k] for k in ('title', 'title_fact_ids', 'intro', 'intro_fact_ids', 'paragraphs')}
    checked = precheck(article, brief, now)
    if not checked['passed'] or review_check(p['independent_review'], article, brief):
        raise ValueError('single_article_validation_failed')
    ids = p.get('live_request_ids', [])
    from run_short_news import request_evidence
    rows = request_evidence(store, ids)
    if (not rows or response_json(rows[0]['response_payload']) != article
            or response_json(rows[1]['response_payload']) != p['independent_review']):
        raise ValueError('single_article_exact_provider_outputs_required')
    item = store.get('news_items', brief['item']['id'])
    if item['payload'] != brief['item']['payload']:
        raise ValueError('single_article_source_changed')
    def clean(row):
        return {k: v for k, v in row.items() if k != 'updated_at'}
    snapshot = {'item': clean(item), 'source': clean(store.get('news_sources', item['source_id'])),
        'cluster': clean(store.get('news_story_clusters', a['cluster_id'])),
        **{name: sorted([clean(r) for r in store.rows(table) if r['article_id'] == article_id], key=lambda r: r['id'])
           for name, table in [('checks', 'news_quality_checks'), ('links', 'news_article_sources'), ('vehicles', 'news_vehicle_links')]},
        'receipts': sorted([{k: r[k] for k in RECEIPT_FIELDS} for r in rows], key=lambda r: r['id'])}
    if (len(snapshot['checks']) != 3 or {r['kind'] for r in snapshot['checks']} != {'evidence','editorial','originality'}
            or any(not r['passed'] or r['artifact_hash'] != a['artifact_hash']
                   or r['payload'].get('errors') != [] or r['payload'].get('audit_performed') is not True
                   or r['payload'].get('reviewed_article_hash') != artifact_hash(article) for r in snapshot['checks'])):
        raise ValueError('single_article_exact_quality_gates_required')
    public = store.public_articles()
    if any(any(s.get('url') == item['url'] for s in old.get('sources', [])) for old in public):
        raise ValueError('single_article_event_already_published')
    if any(old['published_at'][:10] == now.date().isoformat() for old in public):
        raise ValueError('single_article_daily_limit')
    return {'article': a, 'snapshot': snapshot, 'gate': clean(gate), 'checked_at': now.isoformat(),
            'expected_public_count': len(public), 'word_count': checked['word_count']}


def single_article_sql(proof):
    """Generate a snapshot-pinned owner transaction; never executes it."""
    a, snapshot, gate = (proof[k] for k in ('article','snapshot','gate'))
    if a['status'] != 'draft' or gate['id'] != state_id() or gate['payload']['code_hash'] != code_hash():
        raise ValueError('single_article_preparation_changed')
    def literal(value):
        return "'" + value.replace("'", "''") + "'"
    def js(value):
        return literal(json.dumps(value, ensure_ascii=False)) + '::jsonb'
    key, count = literal(a['id']), proof['expected_public_count']
    if type(count) is not int or count < 0:
        raise ValueError('single_article_invalid_public_count')
    tag = '$single_ai_article$'
    while tag in json.dumps(proof, ensure_ascii=False):
        tag = tag[:-1] + '_x$'
    return f"""-- Owner approved ONE exact Firefly article. No paid AI or recurring activation.
begin;
set local standard_conforming_strings=on;
set local time zone 'UTC';
set local lock_timeout='10s';
set local statement_timeout='30s';
do {tag}
declare a public.news_articles;
begin
  perform pg_advisory_xact_lock(72716491);
  lock table public.news_articles,public.news_items,public.news_sources,public.news_story_clusters,
    public.news_quality_checks,public.news_article_sources,public.news_vehicle_links,public.news_ai_requests,
    public.news_ingestion_runs in share row exclusive mode;
  perform 1 from public.news_ai_config where id='production' for update;
  perform 1 from public.news_notice_release_config where id='production' for update;
  if not exists(select 1 from public.news_ai_config where id='production' and not enabled and not publication_enabled
    and model='gpt-6-sol' and daily_limit_micro_usd=250000 and monthly_limit_micro_usd=5000000
    and daily_article_limit=1 and pricing_valid_until>(now() at time zone 'UTC')::date)
    or not exists(select 1 from public.news_notice_release_config where id='production' and not enabled)
    or exists(select 1 from public.news_ai_requests where settled_at is null and budget_closed_at is null)
    then raise exception 'single_article_configuration_or_accounting_changed'; end if;
  if not exists(select 1 from public.news_ingestion_runs where id={literal(gate['id'])} and payload={js(gate['payload'])})
    then raise exception 'single_article_format_gate_changed'; end if;
  select * into a from public.news_articles where id={key} for update;
  if not found or a.status<>'draft' or a.artifact_hash<>{literal(a['artifact_hash'])}
    or a.slug<>{literal(a['slug'])} or a.cluster_id<>{literal(a['cluster_id'])}
    then raise exception 'single_article_artifact_changed'; end if;
  if {source_snapshot_sql(a['id'])} is distinct from {js(snapshot)}
    then raise exception 'single_article_source_checks_or_receipts_changed'; end if;
  if (a.payload->'short_brief'->'item'->'payload'->>'fetched_at')::timestamptz<clock_timestamp()-interval '1 day'
    or (a.payload->'short_brief'->'item'->'payload'->>'published_at')::timestamptz<clock_timestamp()-interval '7 days'
    then raise exception 'single_article_stale_source'; end if;
  if (select count(*) from public.public_news_articles)<>{count}
    or exists(select 1 from public.news_articles old where old.status='published'
      and (old.published_at>=date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'
        or exists(select 1 from jsonb_array_elements(old.payload->'sources') s where s->>'url'=a.payload->'sources'->0->>'url')))
    then raise exception 'single_article_duplicate_or_daily_limit'; end if;
  update public.news_ai_config set publication_enabled=true where id='production';
  perform public.publish_news_article({key},1);
  update public.news_ai_config set publication_enabled=false where id='production';
  if (select count(*) from public.public_news_articles)<>{count + 1}
    or not exists(select 1 from public.news_articles where id={key} and status='published')
    then raise exception 'single_article_unexpected_publication'; end if;
end {tag};
commit;
select a.id,a.slug,a.status,a.published_at,c.enabled as paid_ai_enabled,c.publication_enabled,
  n.enabled as notice_publication_enabled from public.news_articles a
  cross join public.news_ai_config c cross join public.news_notice_release_config n
  where a.id={key} and c.id='production' and n.id='production';
"""
