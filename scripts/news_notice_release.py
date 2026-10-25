"""Read-only release review for deterministic notices. No provider or network calls."""
import json
import re
from datetime import datetime, timedelta, timezone

from news_notice_validation import review_notice
from news_notices import NOTICE_RECIPE, NOTICE_REVIEW, exact_related_models, notice_event_key, notice_slug
from news_store import artifact_hash, stable_id

CHECKS = {'evidence', 'editorial', 'originality'}


def single_release_sql(article, review, expected_public_count):
    """Prepare an owner-run single transaction, never a persistent activation window."""
    if (article.get('status') != 'draft' or review.get('passed') is not True
            or review.get('errors') != [] or review.get('artifact_hash') != article.get('artifact_hash')
            or review.get('method') != NOTICE_REVIEW or not review.get('snapshot')
            or not re.fullmatch(r'[a-f0-9]{64}', article.get('artifact_hash', ''))
            or type(expected_public_count) is not int or expected_public_count < 0):
        raise ValueError('single_notice_requires_exact_passed_draft')

    def literal(value):
        return "'" + value.replace("'", "''") + "'"

    key = literal(article['id'])
    digest = literal(article['artifact_hash'])
    payload = literal(json.dumps(article['payload'], ensure_ascii=False)) + '::jsonb'
    snapshot = literal(json.dumps(review['snapshot'], ensure_ascii=False)) + '::jsonb'
    tag = '$single_notice_release$'
    while any(tag in value for value in (key, digest, payload, snapshot)):
        tag = tag[:-1] + '_x$'
    return f"""-- Explicit owner approval required. One notice only; no paid AI or scheduler.
begin;
set local standard_conforming_strings=on;
set local lock_timeout='10s';
set local statement_timeout='30s';
do {tag}
declare result jsonb;
begin
  perform pg_advisory_xact_lock(72716491);
  perform 1 from public.news_ai_config where id='production' for update;
  perform 1 from public.news_notice_release_config where id='production' for update;
  if not exists(select 1 from public.news_ai_config where id='production'
    and not enabled and not publication_enabled and model in ('gpt-5.4-mini','gpt-6-sol')
    and daily_limit_micro_usd=250000 and monthly_limit_micro_usd=5000000
    and daily_article_limit=2) or not exists(select 1 from public.news_notice_release_config
    where id='production' and not enabled and daily_limit=2
    and policy='{NOTICE_RECIPE}' and review_method='{NOTICE_REVIEW}') then
    raise exception 'single_notice_requires_unchanged_paused_configuration';
  end if;
  if (select count(*) from public.public_news_articles)<>{expected_public_count} then
    raise exception 'single_notice_public_count_changed';
  end if;
  update public.news_ai_config set publication_enabled=true where id='production';
  update public.news_notice_release_config set enabled=true where id='production';
  result:=public.publish_news_notice({key},{digest},{payload},{snapshot});
  if result->'published' is distinct from 'true'::jsonb
    or result->'already_published' is distinct from 'false'::jsonb then
    raise exception 'single_notice_not_newly_published';
  end if;
  update public.news_notice_release_config set enabled=false where id='production';
  update public.news_ai_config set publication_enabled=false where id='production';
  if (select count(*) from public.public_news_articles)<>{expected_public_count + 1} then
    raise exception 'single_notice_unexpected_public_count';
  end if;
end {tag};
commit;
select id,slug,status,published_at from public.news_articles where id={key};
select enabled as paid_ai_enabled,publication_enabled from public.news_ai_config where id='production';
select enabled as notice_publication_enabled from public.news_notice_release_config where id='production';
"""


def notice_snapshot(store, article):
    refs = article['payload']['sources']
    if not isinstance(refs, list) or len(refs) != 1:
        raise ValueError('notice_requires_one_exact_source')
    item = store.get('news_items', refs[0]['item_id'])
    source = store.get('news_sources', item['source_id'])
    cluster = store.get('news_story_clusters', article['cluster_id'])
    checks = sorted((c for c in store.rows('news_quality_checks')
                     if c['article_id']==article['id'] and c['artifact_hash']==article['artifact_hash']), key=lambda c:c['kind'])
    links = [r for r in store.rows('news_article_sources') if r['article_id']==article['id']]
    vehicles = [r for r in store.rows('news_vehicle_links') if r['article_id']==article['id']]
    return {
        'item':{k:item[k] for k in ('id','source_id','url','cluster_id','status','payload')},
        'source':{k:source[k] for k in ('id','payload')},
        'cluster':{k:cluster[k] for k in ('id','event_key','payload')},
        'checks':[{k:c[k] for k in ('id','kind','artifact_hash','passed','payload')} for c in checks],
        'links':sorted(({k:r[k] for k in ('item_id','payload')} for r in links), key=lambda r:r['item_id']),
        'vehicles':sorted(({'canonical_model_id':r['canonical_model_id'],'payload':r['payload']} for r in vehicles),
                          key=lambda r:r['payload']['key']),
    }


def review_notice_release(store, article, models=None, now=None):
    now = now or datetime.now(timezone.utc)
    errors = []
    try:
        p = article['payload']
        if article['status'] != 'draft' or p.get('editorial_recipe') != NOTICE_RECIPE:
            raise ValueError('notice_release_requires_current_draft')
        snapshot = notice_snapshot(store, article)
        item, source, cluster = (snapshot[k] for k in ('item','source','cluster'))
        if item['status']!='processed' or item['cluster_id']!=article['cluster_id']:
            errors.append('notice_source_not_processed_in_event')
        if item['payload'].get('final_url')!=item['url']:
            errors.append('notice_canonical_source_url_changed')
        audit = review_notice(p, item, source['payload'], now=now)
        if not audit['passed']:
            errors.extend(e for group in audit['checks'].values() for e in group)
        packet = p['notice_facts']
        key = notice_event_key(packet)
        if (cluster['event_key']!=key or cluster['id']!=stable_id(key)
                or article['id']!=stable_id('article:'+cluster['id'])
                or cluster['payload'].get('notice_recipe')!=NOTICE_RECIPE):
            errors.append('notice_event_identity_mismatch')
        if article['slug']!=notice_slug(p['title'],article['id']):
            errors.append('notice_slug_requires_restage')
        if models is not None and any(m not in exact_related_models(packet, models) for m in p['related_models']):
            errors.append('notice_canonical_vehicle_link_changed')
        if snapshot['links'] != [{'item_id':packet['item_id'],'payload':p['sources'][0]}]:
            errors.append('notice_attribution_rows_mismatch')
        expected_vehicles = sorted(({'canonical_model_id':m.get('canonical_model_id'),'payload':m}
                                    for m in p['related_models']),key=lambda r:r['payload']['key'])
        if snapshot['vehicles']!=expected_vehicles:
            errors.append('notice_vehicle_rows_mismatch')
        checks = snapshot['checks']
        if len(checks)!=3 or {c['kind'] for c in checks}!=CHECKS:
            errors.append('notice_missing_release_checks')
        for c in checks:
            proof = c['payload']
            if (c['passed'] is not True or proof.get('policy_version')!=NOTICE_RECIPE
                    or proof.get('notice_recipe')!=NOTICE_RECIPE or proof.get('review_method')!=NOTICE_REVIEW
                    or proof.get('audit_performed') is not False or proof.get('deterministic_review_performed') is not True
                    or proof.get('errors')!=[] or proof.get('source_hash')!=packet['source_hash']
                    or proof.get('reviewed_artifact_hash')!=artifact_hash(p)):
                errors.append('notice_failed_or_mismatched_release_check')
            at = datetime.fromisoformat(proof.get('checked_at') or '')
            if not -timedelta(minutes=5) <= now-at <= timedelta(days=1):
                errors.append('notice_stale_release_check')
        for other in store.rows('news_articles'):
            if other['id']==article['id'] or other['status']!='published':
                continue
            old = other['payload']
            facts = old.get('notice_facts') or {}
            if (any(s.get('url')==packet['source_url'] or s.get('item_id')==packet['item_id'] for s in old.get('sources',[]))
                    or facts and notice_event_key(facts)==key):
                errors.append('notice_event_already_published')
        return {'passed':not errors,'errors':sorted(set(errors)), 'snapshot':snapshot,
                'artifact_hash':article['artifact_hash'], 'source_hash':packet['source_hash'],
                'method':NOTICE_REVIEW, 'checked_at':now.isoformat()}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return {'passed':False,'errors':sorted(set(errors+[type(exc).__name__+':'+str(exc)[:160]]))}


def publication_config(store):
    if store.backend=='supabase':
        cfg = store.client.select('news_ai_config',filters={'id':'eq.production'})
        notice = store.client.select('news_notice_release_config',filters={'id':'eq.production'})
        if len(cfg)!=1 or len(notice)!=1:
            raise ValueError('notice_release_configuration_missing')
        return {'publication_enabled':cfg[0]['publication_enabled'], 'enabled':notice[0]['enabled'],
                'daily_limit':min(cfg[0]['daily_article_limit'],notice[0]['daily_limit']),
                'policy':notice[0]['policy'], 'review_method':notice[0]['review_method']}
    row = store.db.execute('select * from news_notice_release_config where id=?',('production',)).fetchone()
    return {**dict(row),'enabled':bool(row['enabled']),'publication_enabled':bool(row['publication_enabled'])}
