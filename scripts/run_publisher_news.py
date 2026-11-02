"""Bounded article-level review and publication using shared publisher templates."""
import argparse
import copy
import hashlib
import json
import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from news_ai import NewsAi, NewsBudgetBlocked, response_json
from news_engine import export_public, models_for_news, queue_verification
from news_editorial import normalize
from news_http import Collector, require_recent_publication
from news_publisher_sources import LEAD_SOURCES, collect_bundle, refresh_bundle, same_sources, bundle_errors, publisher_url
from news_publisher_articles import (RECIPE, LIMITS, PACKET_BYTES, writer_call, reviewer_call,
    pair_bound, precheck, check_review, stage, event_duplicate, evidence_readiness)
from news_publisher_articles import resolve_writer_output
from news_publisher_selection import ranked_candidates
from news_reporting_policy import HISTORICAL_RECIPES
from news_model_policy import reservation_micro_usd
from news_store import NewsStore, artifact_hash, stable_id, now_iso
from run_short_news import budget, matrix_valid, load_state, worker_lock, request_evidence
from smoke_news_engine import verified_context
from supabase_client import load_local_env
from trial_news_hybrid_launch import ledger

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/local/release-data/publisher-news'
HASH_FILES = ('news_publisher_sources.py', 'news_publisher_articles.py', 'run_publisher_news.py',
              'news_publisher_selection.py', 'news_publisher_registry.py', 'news_reporting_policy.py', 'news_primary_discovery.py',
              'news_engine.py', 'news_editorial.py', 'news_http.py', 'news_store.py', 'news_launch_hybrid.py')


def code_hash():
    files = {name: (ROOT / 'scripts' / name).read_text(encoding='utf-8').replace('\r\n', '\n') for name in HASH_FILES}
    files.update({name: (ROOT / name).read_text(encoding='utf-8').replace('\r\n', '\n')
                  for name in ('data/news/sources.json', 'data/news/publisher_templates.json')})
    return artifact_hash(files)


def reviewed_record(remote, proof):
    """Validate this exact article, not a paid admission proof for its publisher."""
    try:
        if (proof['source_id'] not in LEAD_SOURCES or proof['state'] != 'passed'
                or proof.get('kind') not in ('publisher_private_trial', 'short_daily')
                or proof['recipe'] != RECIPE or proof['code_hash'] != code_hash()
                or proof['bundle']['items'][0]['source_id'] != proof['source_id']):
            return None
        checked_at = datetime.fromisoformat(proof['checked_at'])
        if (not precheck(proof['bundle'], proof['packet'], checked_at)['passed']
                or check_review(proof['bundle'], proof['packet'], proof['review'])):
            return None
        receipts = request_evidence(remote, proof['request_ids'])
        if (not receipts or response_json(receipts[0]['response_payload']) != proof['writer_output']
                or resolve_writer_output(proof['bundle'], proof['writer_output']) != proof['packet']
                or response_json(receipts[1]['response_payload']) != proof['review']):
            return None
        return proof
    except (ValueError, KeyError, TypeError):
        return None


def actual_bound(ai, call):
    body = ai.payload(*call)
    return reservation_micro_usd(ai.model, len(json.dumps(body, ensure_ascii=False).encode()) + 4096,
                                 body['max_output_tokens'])


def new_receipt(remote, before, stage_name):
    rows = [r for r in ledger(remote.client) if r['id'] not in before]
    if (len(rows) != 1 or rows[0]['stage'] != stage_name or rows[0]['model'] != 'gpt-6-sol'
            or rows[0]['provider_status'] != 'completed' or not rows[0]['settled_at']):
        raise ValueError('publisher_exact_settled_receipt_missing')
    return rows[0]


def perform(remote, bundle, *, private, ai=None):
    """One writer/reviewer pair; deterministic failures never buy a rewrite."""
    if bundle_errors(bundle):
        raise ValueError('publisher_fresh_bundle_required')
    source_id = bundle['items'][0]['source_id']
    if source_id not in LEAD_SOURCES:
        raise ValueError('publisher_lead_template_required')
    today = now_iso()[:10]
    if private:
        previous = [r for r in remote.rows('news_ingestion_runs')
                    if r['payload'].get('kind') == 'publisher_private_trial'
                    and r['payload'].get('recipe') in HISTORICAL_RECIPES
                    and str(r['payload'].get('started_at', '')).startswith(today)]
        same = next((r for r in previous if r['payload'].get('url') == bundle['items'][0]['url']), None)
        if same:
            return {**same['payload'], 'reused_attempt': True, 'published': 0}
        if len(previous) >= 3:
            return {'status': 'private_trial_limit', 'source_id': source_id, 'published': 0}
    key = stable_id(RECIPE + (':private:' + source_id + ':' + bundle['items'][0]['url'] if private else ':daily') + ':' + today)
    old = remote.get('news_ingestion_runs', key)
    if old:
        return {**old['payload'], 'reused_attempt': True, 'published': 0}
    material = evidence_readiness(bundle)
    if not material['ready']:
        return {'status': 'held_before_ai', 'source_id': source_id, 'errors': material['errors'],
                'paid_calls': 0, 'published': 0}
    if not matrix_valid(remote, load_state(remote)):
        raise ValueError('publisher_existing_mixed_proof_required')
    ai = ai or NewsAi(remote.client, model='gpt-6-sol', cache_enabled=False, output_limits=LIMITS)
    limit = pair_bound(ai, bundle)
    allowance = budget(remote, limit)
    if not allowance['allowed']:
        return {'status': 'deferred_budget', 'source_id': source_id, 'published': 0,
                'required_micro_usd': limit, 'remaining_micro_usd': allowance['remaining_micro_usd']}
    record = {'kind': 'publisher_private_trial' if private else 'short_daily', 'recipe': RECIPE,
        'code_hash': code_hash(), 'source_id': source_id, 'started_at': now_iso(), 'state': 'running',
        'status': 'running', 'url': bundle['items'][0]['url'], 'bundle': copy.deepcopy(bundle),
        'pair_bound_micro_usd': limit, 'request_ids': [], 'cost_micro_usd': 0, 'published': 0}
    remote.put('news_ingestion_runs', {'id': key, 'payload': record})
    before = {r['id'] for r in ledger(remote.client)}
    initial_ids = set(before)
    digests = set()
    try:
        call = writer_call(bundle)
        digests.add(hashlib.sha256(json.dumps(ai.payload(*call), ensure_ascii=False).encode()).hexdigest())
        writer_output = ai(*call)
        receipt = new_receipt(remote, before, 'swedish_ev_article')
        record['request_ids'].append(receipt['id'])
        record['cost_micro_usd'] += receipt['charged_micro_usd']
        record['writer_output'] = writer_output
        packet = resolve_writer_output(bundle, writer_output)
        record['packet'] = packet
        checked = precheck(bundle, packet)
        record['precheck'] = checked
        if not checked['passed']:
            record.update(state='quarantined', status='quarantined', errors=checked['errors'], review_performed=False)
            return record
        # A pathological response cannot exceed the review bound reserved before writing.
        review_call = reviewer_call(bundle, packet)
        residual = limit - actual_bound(ai, writer_call(bundle))
        if actual_bound(ai, review_call) > residual or not budget(remote, actual_bound(ai, review_call))['allowed']:
            raise NewsBudgetBlocked('publisher_review_bound_or_shared_allowance_changed')
        before = {r['id'] for r in ledger(remote.client)}
        digests.add(hashlib.sha256(json.dumps(ai.payload(*review_call), ensure_ascii=False).encode()).hexdigest())
        review = ai(*review_call)
        receipt = new_receipt(remote, before, 'ev_news_independent_audit')
        record['request_ids'].append(receipt['id'])
        record['cost_micro_usd'] += receipt['charged_micro_usd']
        record.update(review=review, review_performed=True, checked_at=now_iso())
        errors = check_review(bundle, packet, review)
        if errors:
            record.update(state='quarantined', status='quarantined', errors=errors)
            return record
        receipts = request_evidence(remote, record['request_ids'])
        if (not receipts or response_json(receipts[0]['response_payload']) != writer_output
                or response_json(receipts[1]['response_payload']) != review):
            raise ValueError('publisher_provider_output_or_receipts_changed')
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        with closing(NewsStore(DIRECTORY / (key + '.sqlite'))) as local:
            local_row = stage(local, bundle, packet, review, record['request_ids'], writer_output=writer_output)
            if local_row['status'] != 'draft':
                raise ValueError('publisher_local_release_checks_failed')
        record.update(state='passed', status='passed', errors=[])
        return record
    except Exception as exc:
        record.update(state='failed', status='failed', error=type(exc).__name__ + ':' + str(exc)[:160])
        return record
    finally:
        # An incomplete provider response can be billed even when JSON decoding failed.
        try:
            rows = remote.client.select('news_ai_requests', columns='id,request_hash,charged_micro_usd,settled_at,provider_status',
                                        filters={'limit': 1000})
            if len(rows) >= 1000:
                raise ValueError('publisher_usage_log_truncated')
            own = [r for r in rows if r['id'] not in initial_ids and r['request_hash'] in digests]
            record['cost_micro_usd'] = sum(r['charged_micro_usd'] for r in own)
            record['cost_status'] = 'settled' if all(r['settled_at'] for r in own) else 'reservation_retained_usage_unknown'
            record['observed_request_ids'] = [r['id'] for r in own]
        except Exception:
            record['cost_status'] = 'reconciliation_required_no_more_calls'
        record['finished_at'] = now_iso()
        remote.put('news_ingestion_runs', {'id': key, 'payload': record})
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        (DIRECTORY / (key + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')


def release(remote, proof, collector):
    if proof.get('kind') != 'short_daily':
        raise ValueError('publisher_private_trial_cannot_publish')
    if not reviewed_record(remote, proof):
        raise ValueError('publisher_exact_article_review_required')
    b, packet = proof['bundle'], proof['packet']
    if not precheck(b, packet)['passed'] or check_review(b, packet, proof['review']):
        return {'status': 'candidate_stale_or_invalid', 'published': 0}
    if event_duplicate(remote, b, packet):
        return {'status': 'already_reported', 'published': 0}
    try:
        fresh = refresh_bundle(b, collector)
    except Exception as exc:
        return {'status': 'source_changed_requires_new_review', 'published': 0,
                'reason': type(exc).__name__ + ':' + str(exc)[:120]}
    if not same_sources(b, fresh):
        return {'status': 'source_changed_requires_new_review', 'published': 0}
    receipts = request_evidence(remote, proof['request_ids'])
    if (not receipts or response_json(receipts[0]['response_payload']) != proof['writer_output']
            or resolve_writer_output(b, proof['writer_output']) != packet
            or response_json(receipts[1]['response_payload']) != proof['review']):
        raise ValueError('publisher_release_receipts_changed')
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if not cfg['enabled'] or not cfg['publication_enabled'] or cfg['daily_article_limit'] != 1:
        return {'status': 'publication_disabled', 'published': 0}
    reported = normalize(' '.join(f['statement'] for f in packet['extraction']['facts']))
    source_text = normalize(b['items'][0]['payload']['content'])
    related = [m for m in models_for_news(remote).values()
               if ' ' + normalize(m['brand'] + ' ' + m['model']) + ' ' in ' ' + reported + ' '
               and ' ' + normalize(m['brand'] + ' ' + m['model']) + ' ' in ' ' + source_text + ' ']
    row = stage(remote, b, packet, proof['review'], proof['request_ids'], related_models=related,
                writer_output=proof['writer_output'])
    if row['status'] != 'draft':
        raise ValueError('publisher_release_stage_not_validated')
    remote.publish(row['id'], daily_limit=1)
    cluster = remote.get('news_story_clusters', row['cluster_id'])
    queue_verification(remote, row, cluster, related)
    return {'status': 'published', 'published': 1, 'article_id': row['id'], 'slug': row['slug'],
            'export': export_public(remote)}


def selection_queue(remote, sources, attempted=()):
    previous = {r['payload'].get('url') for r in remote.rows('news_ingestion_runs')
                if r['payload'].get('recipe') in HISTORICAL_RECIPES
                and r['payload'].get('kind') in ('publisher_private_trial', 'short_daily')}
    rows = [i for i in remote.rows('news_items') if publisher_url(i['source_id'], i['url'])]
    return ranked_candidates(rows, sources, previous | set(attempted), datetime.fromisoformat(now_iso()))


def preview_selection(remote, collector):
    queue, held = selection_queue(remote, LEAD_SOURCES)
    candidates = []
    for item, selection in queue:
        entry = {'source_id': item['source_id'], 'url': item['url'], 'selection': selection}
        try:
            bundle = collect_bundle(item['source_id'], item['url'], collector,
                                    feed_date=item['payload']['published_at'], corroborating_items=remote.rows('news_items'))
            entry.update(evidence_readiness(bundle))
            entry['discovery_trace'] = bundle.get('discovery_trace',[])
            entry['matched_sources'] = [{k:p[k] for k in ('url','source_id')} | {
                'content_hash':p['payload']['content_hash'],'published_at':p['payload'].get('published_at')}
                for p in bundle['items'][1:]]
        except Exception as exc:
            entry.update(ready=False, errors=[type(exc).__name__ + ':' + str(exc)[:140]])
            if hasattr(exc,'discovery_trace'): entry['discovery_trace'] = exc.discovery_trace
        candidates.append(entry)
    return {'status': 'selection_preview', 'candidates': candidates, 'held': held,
            'paid_calls': 0, 'published': 0, 'writes': 0}


def daily(remote, collector):
    if os.environ.get('NEWS_PUBLISHER_ARTICLES_ENABLED') != 'true':
        return {'status': 'publisher_worker_disabled', 'published': 0}
    if not matrix_valid(remote, load_state(remote)):
        raise ValueError('publisher_existing_mixed_proof_required')
    allowance = budget(remote)
    if not allowance['allowed'] or not allowance['publication_enabled']:
        return {'status': 'deferred_budget_or_disabled', 'published': 0}
    if any(a['published_at'][:10] == now_iso()[:10] for a in remote.public_articles()):
        return {'status': 'daily_limit', 'published': 0}
    runs = remote.rows('news_ingestion_runs')
    # Resume a fully reviewed production attempt; private tests are never auto-promoted.
    for row in runs:
        proof = row['payload']
        if (proof.get('kind') == 'short_daily' and proof.get('recipe') == RECIPE
                and proof.get('state') == 'passed' and reviewed_record(remote, proof)
                and not bundle_errors(proof['bundle']) and not event_duplicate(remote, proof['bundle'], proof['packet'])):
            result = release(remote, proof, collector)
            if result.get('published') or result['status'] not in ('already_reported', 'candidate_stale_or_invalid'):
                return result
    if any(r['payload'].get('kind') == 'short_daily'
           and str(r['payload'].get('started_at', '')).startswith(now_iso()[:10]) for r in remote.rows('news_ingestion_runs')):
        return {'status': 'daily_attempt_limit', 'published': 0}
    queue, skipped = selection_queue(remote, LEAD_SOURCES)
    for item, selection in queue:
        try:
            require_recent_publication(item['payload'].get('published_at'))
            bundle = collect_bundle(item['source_id'], item['url'], collector,
                                    feed_date=item['payload']['published_at'], corroborating_items=remote.rows('news_items'))
            material = evidence_readiness(bundle)
            if not material['ready']:
                skipped.append({'url': item['url'], 'reason': material['errors'],
                                'discovery_trace':bundle.get('discovery_trace',[])})
                continue
        except Exception as exc:
            skipped.append({'source_id': item['source_id'], 'url': item['url'], 'reason': str(exc)[:130],
                            'discovery_trace':getattr(exc,'discovery_trace',[])})
            continue
        record = perform(remote, bundle, private=False)
        if record['status'] != 'passed':
            return {k: v for k, v in record.items() if k in ('status', 'errors', 'error', 'cost_micro_usd', 'published')}
        if event_duplicate(remote, bundle, record['packet']):
            return {'status': 'duplicate_event_held', 'published': 0}
        return release(remote, record, collector)
    return {'status': 'no_eligible_new_source', 'published': 0, 'skipped': skipped}


def qualify(remote, collector):
    """Old automation cannot buy a retired per-publisher admission test."""
    return {'status': 'retired_source_qualification', 'paid_calls': 0, 'published': 0}


def main():
    load_local_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('inspect', 'trial', 'status', 'run', 'qualify', 'select'))
    p.add_argument('--source', choices=tuple(LEAD_SOURCES))
    p.add_argument('--url')
    args = p.parse_args()
    with worker_lock(), closing(NewsStore(backend='supabase')) as remote:
        collector = Collector(tls_context=verified_context())
        if args.command in ('inspect', 'trial'):
            if not args.source or not args.url:
                p.error('inspect/trial require --source and --url')
            bundle = collect_bundle(args.source, args.url, collector, corroborating_items=remote.rows('news_items'))
            if args.command == 'inspect':
                ai = NewsAi(remote.client, model='gpt-6-sol', output_limits=LIMITS)
                result = {'source': args.source, 'source_count': len(bundle['items']),
                    'evidence': evidence_readiness(bundle),
                    'pair_bound_micro_usd': pair_bound(ai, bundle), 'budget': budget(remote), 'paid_calls': 0, 'published': 0}
            else:
                record = perform(remote, bundle, private=True)
                result = {k: record[k] for k in ('status', 'source_id', 'cost_micro_usd', 'request_ids',
                          'errors', 'error', 'precheck', 'review_performed', 'published', 'required_micro_usd', 'remaining_micro_usd') if k in record}
        elif args.command == 'status':
            result = {'code_hash': code_hash(), 'budget': budget(remote),
                      'policy': RECIPE, 'source_templates': sorted(LEAD_SOURCES),
                      'publication_mode': 'per_article_review', 'paid_calls': 0, 'published': 0}
        elif args.command == 'qualify':
            result = qualify(remote, collector)
        elif args.command == 'select':
            result = preview_selection(remote, collector)
        else:
            result = daily(remote, collector)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if result.get('status') == 'failed' or (args.command == 'trial' and result.get('status') == 'quarantined'):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
