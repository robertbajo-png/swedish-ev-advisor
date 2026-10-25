"""Idempotent private notice staging. No paid AI, exports, or publishing calls."""
from datetime import datetime, timezone

from news_notice_facts import ADAPTERS, NoticeRejected, extract_notice
from news_notice_validation import review_notice
from news_notices import NOTICE_RECIPE, compose_notice, exact_related_models, notice_event_key, notice_slug
from news_store import artifact_hash, stable_id, now_iso


def notice_sources(sources):
    return [{**s, 'enabled': True} for s in sources if s['id'] in ADAPTERS and s.get('kind')=='primary']


def prepare_notice(item, source, models=None, kind=None, now=None):
    """Pure preparation and separate rule review; no store, AI, network or release."""
    packet = extract_notice(item, source, kind=kind, now=now)
    payload = compose_notice(packet)
    payload['related_models'] = exact_related_models(packet, models or {})
    return payload, review_notice(payload, item, source, now=now)


def stage_notices(store, sources, models, max_items=6, refresh=None, now=None, item_ids=None):
    now = now or datetime.now(timezone.utc)
    source_map = {s['id']:s for s in sources}
    reports = []
    queue = sorted((i for i in store.rows('news_items') if item_ids is None or i['id'] in item_ids), key=lambda i:(
        i['status'] in ('collected','ready'), i['payload'].get('published_at') or '', i['id']), reverse=True)
    for item in queue:
        if len(reports) >= max(0, min(max_items, 20)):
            break
        if item['source_id'] not in source_map:
            continue
        source = source_map[item['source_id']]
        existing = next((a for a in store.rows('news_articles')
                         if any(s.get('item_id')==item['id'] or s.get('url')==item['url'] for s in a['payload'].get('sources', []))
                         and (a['status']=='published' or a['payload'].get('editorial_recipe')==NOTICE_RECIPE)), None)
        if existing and existing['status']=='published':
            reports.append({'item_id':item['id'], 'status':'already_published'})
            continue
        try:
            if refresh:
                item = refresh(item)
            payload, audit = prepare_notice(item, source, models, now=now)
            packet = payload['notice_facts']
            # Stable source-event identity, independent of the chosen notice angle.
            event_key = notice_event_key(packet)
            cluster_id = stable_id(event_key)
            peers = [i for i in store.rows('news_items') if i.get('cluster_id')==cluster_id and i['id']!=item['id']]
            if peers:
                raise NoticeRejected('notice_ambiguous_cross_source_event')
            article_id = stable_id('article:' + cluster_id)
            old = store.get('news_articles', article_id)
            if old and old['status']=='published':
                reports.append({'item_id':item['id'], 'status':'already_published'})
                continue
            if existing and existing['id'] != article_id:
                raise NoticeRejected('notice_changed_event_identity')
            store.put('news_sources', {'id':source['id'], 'payload':source})
            store.put('news_story_clusters', {'id':cluster_id, 'event_key':event_key, 'payload':{
                'event':{'subject':packet['subject'], 'action':{'model':'launch','price':'price','statistics':'market'}[packet['kind']],
                         'date':packet['source_published_at'][:10], 'description':'Official factual notice'},
                'notice_recipe':NOTICE_RECIPE}})
            store.put('news_items', {**item, 'status':'processed', 'cluster_id':cluster_id})
            slug = notice_slug(payload['title'], article_id)
            article = store.put('news_articles', {'id':article_id, 'cluster_id':cluster_id, 'slug':slug,
                'status':'draft' if audit['passed'] else 'quarantined', 'published_at':None, 'payload':payload})
            for ref in payload['sources']:
                store.put('news_article_sources', {'id':stable_id(article_id+ref['item_id']), 'article_id':article_id,
                    'item_id':ref['item_id'], 'payload':ref})
            for model in payload['related_models']:
                store.put('news_vehicle_links', {'id':stable_id(article_id+model['key']), 'article_id':article_id,
                    'canonical_model_id':model.get('canonical_model_id'), 'payload':model})
            for kind, errors in audit['checks'].items():
                store.put('news_quality_checks', {'id':stable_id(article_id+kind+article['artifact_hash']),
                    'article_id':article_id, 'kind':kind, 'artifact_hash':article['artifact_hash'], 'passed':not errors,
                    'payload':{'errors':errors, 'policy_version':NOTICE_RECIPE, 'notice_recipe':NOTICE_RECIPE,
                        'review_method':audit['method'], 'audit_performed':False,
                        'deterministic_review_performed':True, 'checked_at':now.isoformat(),
                        'source_hash':packet['source_hash'], 'reviewed_artifact_hash':audit['artifact_hash']}})
            reports.append({'item_id':item['id'], 'article_id':article_id,
                'status':'validated_draft' if audit['passed'] else 'quarantined',
                'kind':packet['kind'], 'word_count':audit['word_count'], 'checks':audit['checks']})
        except (ValueError, KeyError, TypeError) as exc:
            reason = type(exc).__name__+':'+str(exc)[:240]
            # Invalidate an older private draft when its current source stops passing.
            if existing and existing['status']!='published':
                store.put('news_articles', {**existing, 'status':'quarantined'})
            store.put('news_items', {**item, 'status':'quarantined', 'payload':{
                **item['payload'], 'notice_quarantine_reasons':[reason]}})
            reports.append({'item_id':item['id'], 'status':'quarantined', 'reason':reason})
    store.put('news_ingestion_runs', {'id':stable_id('notice-staging:'+now_iso()), 'payload':{
        'kind':'notice_staging', 'at':now_iso(), 'recipe':NOTICE_RECIPE, 'private':True,
        'provider_requests':0, 'published':0, 'items':reports}})
    return reports
