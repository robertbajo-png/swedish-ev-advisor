"""Bounded official-source facts -> locked writing -> independent review -> release."""
import argparse
import copy
import hashlib
import json
import os
from contextlib import closing
from datetime import datetime
from pathlib import Path

import news_fact_first as contract
from news_ai import NewsAi, NewsBudgetBlocked, response_json
from news_budget_policy import budget
from news_engine import collect, registry, export_public, models_for_news, queue_verification
from news_http import Collector
from news_publisher_articles import event_duplicate
from news_publisher_sources import collect_bundle, refresh_bundle, same_sources
from news_reporting_policy import HISTORICAL_RECIPES
from news_store import NewsStore, artifact_hash, stable_id, now_iso
from run_publisher_news import (selection_queue, new_receipt, code_hash as publisher_hash,
                                approved_candidate_limit)
from run_short_news import worker_lock, matrix_valid, load_state
from smoke_news_engine import verified_context
from supabase_client import load_local_env
from trial_news_hybrid_launch import ledger

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/local/release-data/news-fact-first'


def code_hash():
    return artifact_hash({'publisher': publisher_hash(), **{name: (ROOT / 'scripts' / name).read_text(
        encoding='utf-8').replace('\r\n', '\n') for name in ('news_fact_first.py', 'run_fact_first_news.py')}})


def previous_attempts(remote):
    return [r for r in remote.rows('news_ingestion_runs') if r['payload'].get('recipe') in HISTORICAL_RECIPES
            and r['payload'].get('kind') in ('short_daily', 'publisher_private_trial')]


def exact_receipts(remote, record, *, count=3):
    ids = record.get('request_ids', [])
    if count not in (2, 3) or len(ids) != count or len(set(ids)) != count:
        return None
    rows = remote.client.select('news_ai_requests', filters={'id': 'in.(' + ','.join(ids) + ')'})
    mapped = {r['id']: r for r in rows}
    if set(mapped) != set(ids):
        return None
    rows = [mapped[key] for key in ids]
    if ([r['stage'] for r in rows] != list(contract.LIMITS)[:count]
            or any(r['model'] != 'gpt-6-sol' or r['provider_status'] != 'completed' or not r['settled_at'] for r in rows)):
        return None
    outputs = [record['fact_output'], record['writer_output']]
    if count == 3: outputs.append(record['review'])
    if [response_json(r['response_payload']) for r in rows] != outputs:
        return None
    ai = NewsAi(remote.client, model='gpt-6-sol', cache_enabled=False, output_limits=contract.LIMITS)
    calls = [contract.extraction_call(record['bundle']), contract.writer_call(record['locked'])]
    if count == 3: calls.append(contract.review_call(record['bundle'], record['packet']))
    if any(row['request_hash'] != hashlib.sha256(json.dumps(ai.payload(*spec), ensure_ascii=False).encode()).hexdigest()
           for row, spec in zip(rows, calls)):
        return None
    return rows


def reviewed(remote, record, *, qualification_only=False):
    try:
        if (record.get('recipe') != contract.RECIPE or record.get('state') != 'passed'
                or not qualification_only and record.get('code_hash') != code_hash()):
            return False
        at = datetime.fromisoformat(record['checked_at'])
        locked = contract.lock_facts(record['bundle'], record['fact_output'], at)
        packet = contract.bind_article(locked, record['writer_output'])
        return (locked == record['locked'] and packet == record['packet']
                and contract.packet_check(record['bundle'], locked, record['writer_output'], at)['passed']
                and not contract.review_check(record['bundle'], packet, record['review'])
                and bool(exact_receipts(remote, record)))
    except (KeyError, ValueError, TypeError):
        return False


def perform(remote, bundle, *, private, ai=None, max_candidates=2, owner_day=None):
    limit = approved_candidate_limit(max_candidates, owner_day)
    ready = contract.readiness(bundle)
    if not ready['ready']:
        return {'status': 'held_before_ai', 'errors': ready['errors'], 'paid_calls': 0, 'published': 0}
    previous = previous_attempts(remote)
    url = bundle['items'][0]['url']
    if any(r['payload'].get('url') == url for r in previous):
        return {'status': 'historical_url_held', 'paid_calls': 0, 'published': 0}
    today = now_iso()[:10]
    kind = 'publisher_private_trial' if private else 'short_daily'
    used = sum(r['payload'].get('kind') == kind and r['payload'].get('started_at', '').startswith(today) for r in previous)
    if used >= (3 if private else limit):
        return {'status': 'private_trial_limit' if private else 'daily_attempt_limit', 'published': 0}
    if not matrix_valid(remote, load_state(remote)):
        raise ValueError('fact_first_existing_mixed_proof_required')
    ai = ai or NewsAi(remote.client, model='gpt-6-sol', cache_enabled=False, output_limits=contract.LIMITS)
    before = {r['id'] for r in ledger(remote.client)}
    bound = contract.pipeline_bound(ai, bundle)
    if not budget(remote, bound)['allowed']:
        return {'status': 'deferred_budget', 'required_micro_usd': bound, 'published': 0}
    identity = stable_id(contract.RECIPE + ':' + kind + ':' + url + ':' + today)
    record = {'kind': kind, 'recipe': contract.RECIPE, 'code_hash': code_hash(),
        'source_id': bundle['items'][0]['source_id'], 'url': url, 'started_at': now_iso(),
        'bundle': copy.deepcopy(bundle), 'state': 'running', 'status': 'running',
        'pipeline_bound_micro_usd': bound, 'request_ids': [], 'cost_micro_usd': 0,
        'review_performed': False, 'published': 0}
    if max_candidates != 2:
        record.update(owner_approved_day=owner_day, candidate_limit=max_candidates)
    remote.put('news_ingestion_runs', {'id': identity, 'payload': record})
    initial, digests, reserved = set(before), set(), 0

    def call(spec):
        nonlocal before, reserved
        amount = contract.call_bound(ai, spec)
        if reserved + amount > bound or not budget(remote, amount)['allowed']:
            raise NewsBudgetBlocked('fact_first_pipeline_bound_changed')
        digests.add(hashlib.sha256(json.dumps(ai.payload(*spec), ensure_ascii=False).encode()).hexdigest())
        value = ai(*spec)
        receipt = new_receipt(remote, before, spec[0])
        record['request_ids'].append(receipt['id'])
        reserved += amount
        before.add(receipt['id'])
        return value

    try:
        record['fact_output'] = call(contract.extraction_call(bundle))
        try:
            record['locked'] = contract.lock_facts(bundle, record['fact_output'])
        except ValueError as exc:
            record.update(state='quarantined', status='quarantined', errors=[str(exc)])
            return record
        # Persist the immutable validated packet before paying for any prose.
        remote.put('news_ingestion_runs', {'id': identity, 'payload': record})
        record['writer_output'] = call(contract.writer_call(record['locked']))
        record['packet'] = contract.bind_article(record['locked'], record['writer_output'])
        record['precheck'] = contract.packet_check(bundle, record['locked'], record['writer_output'])
        if not record['precheck']['passed']:
            record.update(state='quarantined', status='quarantined', errors=record['precheck']['errors'])
            return record
        record['review'] = call(contract.review_call(bundle, record['packet']))
        record.update(review_performed=True, checked_at=now_iso())
        errors = contract.review_check(bundle, record['packet'], record['review'])
        if errors:
            record.update(state='quarantined', status='quarantined', errors=errors)
            return record
        if not exact_receipts(remote, record):
            raise ValueError('fact_first_exact_three_receipts_required')
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        with closing(NewsStore(DIRECTORY / (identity + '.sqlite'))) as local:
            if contract.stage_article(local, record)['status'] != 'draft':
                raise ValueError('fact_first_local_stage_rejected')
        record.update(state='passed', status='passed', errors=[])
        return record
    except Exception as exc:
        record.update(state='failed', status='failed', error=type(exc).__name__ + ':' + str(exc)[:160])
        return record
    finally:
        try:
            rows = remote.client.select('news_ai_requests', columns='id,request_hash,charged_micro_usd,settled_at,provider_status', filters={'limit': 1000})
            if len(rows) >= 1000:
                raise ValueError('fact_first_receipts_truncated')
            own = [r for r in rows if r['id'] not in initial and r['request_hash'] in digests]
            record['cost_micro_usd'] = sum(r['charged_micro_usd'] for r in own)
            record['cost_status'] = 'settled' if all(r['settled_at'] for r in own) else 'reservation_retained_usage_unknown'
            record['observed_request_ids'] = [r['id'] for r in own]
        except Exception:
            record['cost_status'] = 'reconciliation_required_no_more_calls'
        record['finished_at'] = now_iso()
        remote.put('news_ingestion_runs', {'id': identity, 'payload': record})
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        (DIRECTORY / (identity + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')


def qualification(remote):
    # A registry/worker edit does not invalidate an unchanged, genuinely passed
    # audit. All three CURRENT request payloads, exact outputs and gates still match.
    approved = [r['payload'] for r in previous_attempts(remote)
                if reviewed(remote, r['payload'], qualification_only=True)]
    categories = {r['packet']['extraction']['category'] for r in approved
                  if contract.readiness(r['bundle'], datetime.fromisoformat(r['checked_at']))['ready']}
    private_count = sum(r['kind'] == 'publisher_private_trial' for r in approved)
    return {'passed': private_count >= 1 and len(categories) >= 2, 'categories': sorted(categories),
            'real_private_successes': private_count, 'real_approved_cases': len(approved), 'paid_calls': 0}


def complete_trial(remote, parent_id, collector, owner_day, *, ai=None):
    """Separately approved, one-time remaining review after a proven language-heuristic bug.

    Never a normal retry: no extraction, writing, text edits or publication. The
    original quarantine remains immutable and both old receipts must still match.
    """
    if owner_day != now_iso()[:10]:
        raise ValueError('fact_first_current_day_owner_approval_required')
    identity = stable_id(contract.RECIPE + ':language-review-completion:' + parent_id)
    old = remote.get('news_ingestion_runs', identity)
    if old:
        return {**old['payload'], 'reused_completion': True}
    parent = copy.deepcopy((remote.get('news_ingestion_runs', parent_id) or {}).get('payload', {}))
    if (parent.get('recipe') != contract.RECIPE or parent.get('kind') != 'publisher_private_trial'
            or parent.get('state') != 'quarantined' or parent.get('review_performed')
            or parent.get('errors') != ['publisher_not_swedish'] or parent.get('cost_status') != 'settled'
            or not exact_receipts(remote, parent, count=2)):
        raise ValueError('fact_first_completion_requires_exact_language_only_parent')
    b = parent['bundle']
    locked = contract.lock_facts(b, parent['fact_output'])
    checked = contract.packet_check(b, locked, parent['writer_output'])
    if (locked != parent['locked'] or contract.bind_article(locked, parent['writer_output']) != parent['packet']
            or not checked['passed']):
        raise ValueError('fact_first_completion_artifact_or_other_gate_changed')
    if not same_sources(b, refresh_bundle(b, collector)):
        raise ValueError('fact_first_completion_source_changed')
    today_private = sum(r['payload'].get('kind') == 'publisher_private_trial'
        and r['payload'].get('started_at', '').startswith(owner_day) for r in previous_attempts(remote))
    if today_private >= 3:
        return {'status': 'private_trial_limit', 'published': 0}
    before = {r['id'] for r in ledger(remote.client)}
    ai = ai or NewsAi(remote.client, model='gpt-6-sol', cache_enabled=False, output_limits=contract.LIMITS)
    spec = contract.review_call(b, parent['packet'])
    amount = contract.call_bound(ai, spec)
    if amount > 100000 or not budget(remote, amount)['allowed']:
        return {'status': 'deferred_budget', 'required_micro_usd': amount, 'published': 0}
    record = {**parent, 'completion_of': parent_id, 'code_hash': code_hash(), 'started_at': now_iso(),
        'state': 'running', 'status': 'running', 'errors': [], 'precheck': checked,
        'owner_approved_day': owner_day, 'reused_request_ids': list(parent['request_ids']),
        'review_cap_micro_usd': 100000, 'review_performed': False, 'published': 0}
    digest = hashlib.sha256(json.dumps(ai.payload(*spec), ensure_ascii=False).encode()).hexdigest()
    remote.put('news_ingestion_runs', {'id': identity, 'payload': record})
    try:
        record['review'] = ai(*spec)
        receipt = new_receipt(remote, before, 'ev_news_independent_audit')
        record['request_ids'].append(receipt['id'])
        record.update(review_performed=True, checked_at=now_iso())
        errors = contract.review_check(b, record['packet'], record['review'])
        if errors:
            record.update(state='quarantined', status='quarantined', errors=errors)
        elif not exact_receipts(remote, record):
            raise ValueError('fact_first_completion_receipts_changed')
        else:
            DIRECTORY.mkdir(parents=True, exist_ok=True)
            with closing(NewsStore(DIRECTORY / (identity + '.sqlite'))) as local:
                if contract.stage_article(local, record)['status'] != 'draft':
                    raise ValueError('fact_first_completion_local_gates_rejected')
            record.update(state='passed', status='passed')
    except Exception as exc:
        record.update(state='failed', status='failed', error=type(exc).__name__ + ':' + str(exc)[:160])
    finally:
        try:
            rows = remote.client.select('news_ai_requests', filters={'limit': 1000})
            if len(rows) >= 1000: raise ValueError('fact_first_receipts_truncated')
            own = [r for r in rows if r['id'] not in before and r['request_hash'] == digest]
            record['new_cost_micro_usd'] = sum(r['charged_micro_usd'] for r in own)
            record['cost_micro_usd'] = parent['cost_micro_usd'] + record['new_cost_micro_usd']
            record['observed_request_ids'] = [r['id'] for r in own]
            record['cost_status'] = 'settled' if all(r['settled_at'] for r in own) else 'reservation_retained_usage_unknown'
        except Exception:
            record['cost_status'] = 'reconciliation_required_no_more_calls'
        record['finished_at'] = now_iso()
        remote.put('news_ingestion_runs', {'id': identity, 'payload': record})
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        (DIRECTORY / (identity + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def release(remote, proof, collector):
    if proof.get('kind') != 'short_daily' or not reviewed(remote, proof):
        raise ValueError('fact_first_fresh_production_review_required')
    if not qualification(remote)['passed']:
        return {'status': 'qualification_required', 'published': 0}
    b = proof['bundle']
    if not contract.packet_check(b, proof['locked'], proof['writer_output'])['passed']:
        return {'status': 'candidate_stale_or_invalid', 'published': 0}
    if event_duplicate(remote, b, proof['packet']):
        return {'status': 'already_reported', 'published': 0}
    fresh = refresh_bundle(b, collector)
    if not same_sources(b, fresh):
        return {'status': 'source_changed_requires_new_review', 'published': 0}
    if not exact_receipts(remote, proof):
        raise ValueError('fact_first_receipts_changed')
    ledger(remote.client)
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if not cfg['publication_enabled'] or not cfg['enabled'] or cfg['daily_article_limit'] != 1:
        return {'status': 'publication_disabled', 'published': 0}
    # Same canonical-only context as the existing route; news never changes car facts.
    from news_editorial import normalize
    facts = ' ' + normalize(' '.join(f['statement'] for f in proof['packet']['extraction']['facts'])) + ' '
    source = ' ' + normalize(b['items'][0]['payload']['content']) + ' '
    related = [m for m in models_for_news(remote).values()
               if ' ' + normalize(m['brand'] + ' ' + m['model']) + ' ' in facts
               and ' ' + normalize(m['brand'] + ' ' + m['model']) + ' ' in source]
    row = contract.stage_article(remote, proof, related_models=related)
    if row['status'] != 'draft':
        raise ValueError('fact_first_release_stage_rejected')
    remote.publish(row['id'], daily_limit=1)
    queue_verification(remote, row, remote.get('news_story_clusters', row['cluster_id']), related)
    return {'status': 'published', 'published': 1, 'article_id': row['id'], 'slug': row['slug'],
            'word_count': proof['precheck']['word_count'], 'cost_micro_usd': proof['cost_micro_usd'],
            'review_performed': True, 'export': export_public(remote)}


def preview(remote, collector, sources=None):
    queue, held = selection_queue(remote, sources or contract.START_SOURCES)
    candidates = []
    for item, _ in queue:
        entry = {k: item[k] for k in ('source_id', 'url')}
        try:
            bundle = collect_bundle(item['source_id'], item['url'], collector, feed_date=item['payload']['published_at'])
            entry.update(contract.readiness(bundle))
        except Exception as exc:
            entry.update(ready=False, errors=[type(exc).__name__ + ':' + str(exc)[:130]])
        candidates.append(entry)
    return {'status': 'selection_preview', 'candidates': candidates, 'held': held, 'paid_calls': 0, 'published': 0}


def daily(remote, collector, max_candidates=2, owner_day=None, *, complete_qualification=False):
    approved_candidate_limit(max_candidates, owner_day)
    if os.environ.get('NEWS_PUBLISHER_ARTICLES_ENABLED') != 'true':
        return {'status': 'publisher_worker_disabled', 'published': 0}
    qualified = qualification(remote)
    if complete_qualification and owner_day != now_iso()[:10]:
        raise ValueError('fact_first_current_day_owner_approval_required')
    if not qualified['passed'] and not (complete_qualification and qualified['real_private_successes'] >= 1):
        return {'status': 'qualification_required', 'published': 0}
    if any(a['published_at'][:10] == now_iso()[:10] for a in remote.public_articles()):
        return {'status': 'daily_limit', 'published': 0}
    for row in previous_attempts(remote):
        proof = row['payload']
        if proof.get('kind') == 'short_daily' and reviewed(remote, proof) and contract.readiness(proof['bundle'])['ready']:
            result = release(remote, proof, collector)
            if result['status'] != 'already_reported':
                return result
    queue, held = selection_queue(remote, contract.START_SOURCES)
    last_rejection = None
    for item, _ in queue:
        try:
            bundle = collect_bundle(item['source_id'], item['url'], collector, feed_date=item['payload']['published_at'])
            if not contract.readiness(bundle)['ready']:
                continue
        except Exception:
            continue
        record = perform(remote, bundle, private=False, max_candidates=max_candidates, owner_day=owner_day)
        if record['status'] == 'passed':
            return release(remote, record, collector)
        if record['status'] != 'quarantined' or record.get('cost_status') != 'settled':
            return safe_result(record)
        last_rejection = safe_result(record)
    return {**(last_rejection or {'status': 'no_eligible_new_source', 'published': 0}),
            'held_candidates': len(held)}


def safe_result(record):
    return {k: record[k] for k in ('status', 'errors', 'error', 'cost_micro_usd', 'cost_status',
        'new_cost_micro_usd', 'request_ids', 'review_performed', 'precheck', 'published', 'required_micro_usd') if k in record}


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'select', 'collect', 'trial', 'complete-trial', 'run'))
    parser.add_argument('--source', choices=sorted(contract.START_SOURCES))
    parser.add_argument('--url')
    parser.add_argument('--max-candidates', type=int, default=2)
    parser.add_argument('--owner-approved-day')
    parser.add_argument('--parent-run', help='Exact private language-only quarantine; separate approval required')
    parser.add_argument('--complete-qualification', action='store_true',
                        help='Explicit owner-only production case after a real private success')
    args = parser.parse_args()
    if args.command not in ('run', 'complete-trial') and (args.max_candidates != 2 or args.owner_approved_day or args.complete_qualification):
        parser.error('Extended production limits apply only to run')
    if args.command == 'complete-trial' and (not args.parent_run or not args.owner_approved_day
            or args.max_candidates != 2 or args.complete_qualification):
        parser.error('Completion requires its exact parent and current owner day, no production options')
    with worker_lock(), closing(NewsStore(backend='supabase')) as remote:
        collector = Collector(tls_context=verified_context())
        if args.command == 'status':
            result = {'code_hash': code_hash(), 'budget': budget(remote), 'qualification': qualification(remote),
                      'sources': sorted(contract.START_SOURCES), 'paid_calls': 0, 'published': 0}
        elif args.command == 'collect':
            sources = [{**s, 'enabled': True, 'etag': None, 'last_modified': None}
                       for s in registry() if s['id'] in contract.START_SOURCES and (not args.source or s['id'] == args.source)]
            result = {**collect(remote, sources, collector, max_items=20, force=True), 'paid_calls': 0, 'published': 0}
        elif args.command == 'select':
            result = preview(remote, collector, {args.source} if args.source else None)
        elif args.command == 'complete-trial':
            result = safe_result(complete_trial(remote, args.parent_run, collector, args.owner_approved_day))
        elif args.command == 'trial':
            if not args.source or not args.url:
                parser.error('trial requires --source and --url')
            result = safe_result(perform(remote, collect_bundle(args.source, args.url, collector), private=True))
        else:
            result = daily(remote, collector, args.max_candidates, args.owner_approved_day,
                           complete_qualification=args.complete_qualification)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if result.get('status') == 'failed':
            raise SystemExit(1)


if __name__ == '__main__':
    main()
