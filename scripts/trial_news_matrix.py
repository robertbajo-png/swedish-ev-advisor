"""Single-use, owner-scoped multi-source evaluation. No production article writes."""
import argparse
import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from news_ai import NewsAi, NewsBudgetBlocked
from news_editorial import EDITORIAL_RECIPE, audit_article, blocks, validate_article, validate_fact_extraction
from news_engine import attach_cluster, collect, editorial, hydrate_item, process_items, registry
from news_http import Collector, require_recent_publication
from news_store import NewsStore, artifact_hash, now_iso, stable_id
from refresh_verified_variants import save
from smoke_news_engine import verified_context
from supabase_client import load_local_env
from trial_news_review import TrialClient, ledger

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-10-22'
RECIPE = 'news-editorial-recipe-2026-10-r18'
TRIAL_ID = stable_id('private-news-matrix-r18:' + DATE)
MAX_MICRO_USD = 60000
MAX_REQUESTS = 9
REEXTRACT_MODEL = False
MODEL_INPUT = None
INCLUDE_MARKET = True
MAX_REVISIONS = 1
EXPECTED_CATEGORIES = None
DATABASE = ROOT / 'data/local/news-matrix-r18-2026-10-22.sqlite'
OUTPUT = ROOT / 'data/local/release-data/news-production/matrix-r18-trial-2026-10-22.json'
PUBLIC_FILE = ROOT / 'public/data/news_articles.json'
MODEL_ITEM = '8bd04eca-a817-59da-9177-2fa2b1c21878'
BMW_ITEM = 'c91bb573-f585-5311-81bb-71cef80d18b0'


class PrivateMatrixStore(NewsStore):
    def __init__(self, path):
        super().__init__(path, backend='sqlite')

    def publish(self, *args, **kwargs):
        raise ValueError('matrix_publication_forbidden')


def authorize():
    if datetime.now(timezone.utc).date().isoformat() != DATE or EDITORIAL_RECIPE != RECIPE:
        raise NewsBudgetBlocked('matrix_authorization_expired_or_recipe_changed')


def switches(remote, enabled):
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if (cfg['enabled'] is not enabled or cfg['publication_enabled']
            or cfg['daily_limit_micro_usd'] != 250000 or cfg['monthly_limit_micro_usd'] != 5000000):
        raise NewsBudgetBlocked('matrix_switches_or_limits_mismatch')


def public_hash(remote):
    return artifact_hash(remote.public_articles())


def article_hash(remote):
    return artifact_hash(remote.rows('news_articles'))


def contract(item):
    p = item['payload']
    return {'id': item['id'], 'source_id': item['source_id'], 'url': item['url'],
            'published_at': p['published_at'], 'content_hash': p['content_hash'],
            'extraction_hash': artifact_hash(p.get('extraction')),
            'metadata_hash': artifact_hash({k: p.get(k) for k in ['title', 'publisher', 'publisher_group', 'source_kind', 'reliability', 'classification']})}


def receipt(remote, report):
    save(OUTPUT, report)
    remote.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': {
        key: value for key, value in report.items() if key not in {'articles', 'baseline_request_ids'}}})


def isolated_source_copy(item):
    discarded = {'extraction', 'fact_quarantine', 'quarantine_reasons', 'attempts', 'retry_after', 'budget_retry_after'}
    return {**item, 'status': 'collected', 'cluster_id': None,
            'payload': {key: value for key, value in item['payload'].items() if key not in discarded}}


def expected_categories():
    return set(EXPECTED_CATEGORIES) if EXPECTED_CATEGORIES is not None else ({'modeller', 'marknad'} if INCLUDE_MARKET else {'modeller'})


def prepare(remote, collector=None, switch_check=None):
    authorize()
    if remote.get('news_ingestion_runs', TRIAL_ID) or OUTPUT.exists() or DATABASE.exists():
        raise NewsBudgetBlocked('matrix_preparation_already_exists')
    (switch_check or switches)(remote, False)
    if remote.client.select('news_ai_requests', columns='id', filters={
            'settled_at': 'is.null', 'budget_closed_at': 'is.null', 'limit': 1}):
        raise NewsBudgetBlocked('matrix_unresolved_usage')
    collector = collector or Collector(tls_context=verified_context())
    sources = {source['id']: source for source in registry()}
    checks = []
    with closing(PrivateMatrixStore(DATABASE)) as store:
        for key in ['vw-sweden-press', 'acea', 'bmw-press']:
            store.put('news_sources', {'id': key, 'payload': sources[key]})
        original = MODEL_INPUT(remote) if MODEL_INPUT else remote.get('news_items', MODEL_ITEM)
        if not original or original['status'] != 'processed':
            raise ValueError('matrix_requires_verified_model_facts')
        item, _ = hydrate_item(store, isolated_source_copy(original) if REEXTRACT_MODEL else original, sources, collector)
        if item['payload']['content_hash'] != original['payload']['content_hash']:
            raise ValueError('matrix_model_evidence_changed_or_invalid')
        if not REEXTRACT_MODEL:
            if validate_fact_extraction(item['payload']['extraction'], item):
                raise ValueError('matrix_model_evidence_changed_or_invalid')
            attach_cluster(store, item, item['payload']['extraction'])
        checks.append({'source_id': item['source_id'], 'status': 'accessible', 'role': 'model_case'})
        collection, cases = {}, [contract(item)]
        if INCLUDE_MARKET:
            collection = collect(store, [{**sources['acea'], 'enabled': True}], collector, max_items=1, force=True)
            candidates = [row for row in store.rows('news_items') if row['source_id'] == 'acea' and row['status'] == 'collected']
            if len(candidates) != 1:
                raise ValueError('matrix_requires_one_recent_acea_report:' + json.dumps(collection))
            market, _ = hydrate_item(store, candidates[0], sources, collector)
            checks.append({'source_id': 'acea', 'status': 'accessible', 'role': 'market_case'})
            cases.insert(0, contract(market))
        # An existing quarantined US demonstration is an access/scope probe only.
        probe = remote.get('news_items', BMW_ITEM)
        try:
            if not probe:
                raise ValueError('missing_probe')
            probe, _ = hydrate_item(store, probe, sources, collector)
            store.put('news_items', {**probe, 'status': 'quarantined', 'payload': {
                **probe['payload'], 'quarantine_reasons': ['matrix_access_probe_only_not_selected'], 'attempts': 3}})
            checks.append({'source_id': 'bmw-press', 'status': 'accessible',
                           'role': 'access_probe_only', 'editorial_reviewed': False,
                           'limitation': 'US demonstration does not prove Swedish commercial availability'})
        except Exception as exc:
            checks.append({'source_id': 'bmw-press', 'status': 'blocked', 'reason': type(exc).__name__ + ':' + str(exc)[:160]})
        source_config_hash = artifact_hash({row['id']: row['payload'] for row in store.rows('news_sources')})
    report = {'kind': 'private_news_matrix', 'trial_id': TRIAL_ID, 'recipe': RECIPE, 'authorization_date': DATE,
              'state': 'prepared', 'at': now_iso(), 'maximum_micro_usd': MAX_MICRO_USD, 'maximum_requests': MAX_REQUESTS,
              'reextract_model': REEXTRACT_MODEL,
              'include_market': INCLUDE_MARKET, 'max_revisions': MAX_REVISIONS,
              'expected_categories': sorted(expected_categories()),
              'cases': cases, 'source_checks': checks, 'collection': collection, 'source_config_hash': source_config_hash,
              'baseline_request_ids': [row['id'] for row in ledger(remote.client)],
              'public_database_hash': public_hash(remote), 'production_articles_hash': article_hash(remote),
              'public_file_hash': hashlib.sha256(PUBLIC_FILE.read_bytes()).hexdigest(),
              'publish': False, 'public_export': False, 'passed': False}
    # Keep the original baseline in the preparation marker; later receipts never reset it.
    save(OUTPUT, report)
    remote.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': report})
    return {k: v for k, v in report.items() if k != 'baseline_request_ids'}


def assert_unchanged(remote, report):
    if (public_hash(remote) != report['public_database_hash'] or article_hash(remote) != report['production_articles_hash']
            or hashlib.sha256(PUBLIC_FILE.read_bytes()).hexdigest() != report['public_file_hash']):
        raise NewsBudgetBlocked('matrix_production_surface_changed')


def refresh_case(store, case, sources, collector):
    item = store.get('news_items', case['id'])
    if contract(item) != case:
        raise ValueError('matrix_frozen_source_changed')
    require_recent_publication(item['payload']['published_at'])
    refreshed, _ = hydrate_item(store, item, sources, collector)
    if contract(refreshed) != case:
        raise ValueError('matrix_live_source_changed')
    if item['status'] == 'processed':
        if validate_fact_extraction(refreshed['payload'].get('extraction'), refreshed):
            raise ValueError('matrix_refreshed_facts_invalid')
        return attach_cluster(store, refreshed, refreshed['payload']['extraction'])
    # Hydration writes ready; the production extractor consumes collected items.
    return store.put('news_items', {**refreshed, 'status': 'collected'})


def final_review(store, article, provider):
    checks = [c for c in store.rows('news_quality_checks') if c['article_id'] == article['id'] and c['artifact_hash'] == article['artifact_hash']]
    evidence = next(c for c in checks if c['kind'] == 'evidence')
    reviewed = any(c['payload'].get('audit_performed') for c in checks)
    diagnostic = None
    if not reviewed:
        before = artifact_hash(article)
        facts = evidence['payload']['fact_inventory']
        items = [i for i in store.rows('news_items') if i['cluster_id'] == article['cluster_id']]
        audit = audit_article(article['payload'], facts, provider)
        diagnostic = {'audit': audit, 'diagnostic_only': True, 'approval': False,
                      'gate_errors': validate_article(article['payload'], facts, items, audit, article['payload']['relevance_score'])}
        if artifact_hash(store.get('news_articles', article['id'])) != before:
            raise ValueError('matrix_final_review_mutated_article')
    return {'article_id': article['id'], 'source_id': next(i['source_id'] for i in store.rows('news_items') if i['cluster_id'] == article['cluster_id']),
            'status': article['status'], 'artifact_hash': article['artifact_hash'], 'category': article['payload']['category'],
            'word_count': sum(len(block['text'].split()) for block in blocks(article['payload'])),
            'audit_performed': reviewed or diagnostic is not None, 'diagnostic_final_review': diagnostic,
            'passed': article['status'] == 'draft' and len(checks) == 3 and all(c['passed'] for c in checks)}


def run(remote, collector=None, switch_check=None, client_factory=None):
    authorize()
    report = json.loads(OUTPUT.read_text(encoding='utf-8'))
    marker = remote.get('news_ingestion_runs', TRIAL_ID)
    if not marker or marker['payload'] != report or report.get('state') != 'prepared':
        raise NewsBudgetBlocked('matrix_requires_unused_matching_preparation')
    if (report.get('trial_id') != TRIAL_ID or report.get('recipe') != RECIPE or report.get('maximum_micro_usd') != MAX_MICRO_USD
            or report.get('maximum_requests') != MAX_REQUESTS or len(report.get('cases', [])) != (2 if INCLUDE_MARKET else 1)
            or report.get('include_market', True) is not INCLUDE_MARKET or report.get('max_revisions', 1) != MAX_REVISIONS
            or report.get('expected_categories', sorted(expected_categories())) != sorted(expected_categories())
            or report.get('reextract_model', False) is not REEXTRACT_MODEL):
        raise NewsBudgetBlocked('matrix_preparation_contract_mismatch')
    (switch_check or switches)(remote, True)
    assert_unchanged(remote, report)
    provider = NewsAi((client_factory or TrialClient)(remote.client, report['baseline_request_ids'],
        stages={'ev_news_facts', 'swedish_ev_article', 'ev_news_independent_audit', 'ev_news_block_repair'},
        maximum_requests=MAX_REQUESTS, maximum_micro_usd=MAX_MICRO_USD, authorize=authorize))
    collector = collector or Collector(tls_context=verified_context())
    report.update(state='running', started_at=now_iso(), results=[], articles=[], owner_shutdown_required=True)
    receipt(remote, report)
    try:
        with closing(PrivateMatrixStore(DATABASE)) as store:
            sources = {row['id']: row['payload'] for row in store.rows('news_sources')}
            if artifact_hash(sources) != report['source_config_hash']:
                raise ValueError('matrix_frozen_source_configuration_changed')
            for case in report['cases']:
                item = refresh_case(store, case, sources, collector)
                if item['status'] != 'processed':
                    extraction = process_items(store, [sources[case['source_id']]], max_items=1, ai=provider, collector=collector)
                    report.setdefault('extraction', []).extend(extraction)
                current = store.get('news_items', case['id'])
                if current['status'] != 'processed':
                    report['results'].append({'source_id': case['source_id'], 'status': current['status'],
                        'passed': False, 'audit_performed': False, 'reason': current['payload'].get('quarantine_reasons', [])})
                    continue
                article_id = stable_id('article:' + current['cluster_id'])
                report.setdefault('editorial', []).extend(editorial(store, max_stories=1, ai=provider, retry=True,
                    max_revisions=MAX_REVISIONS, _only_articles={article_id}, publish=False))
                article = store.get('news_articles', article_id)
                if article is None:
                    report['results'].append({'source_id': case['source_id'], 'status': 'no_article', 'passed': False, 'audit_performed': False})
                    continue
                report['results'].append(final_review(store, article, provider))
            report['articles'] = [{**article, 'checks': [c for c in store.rows('news_quality_checks')
                                   if c['article_id'] == article['id'] and c['artifact_hash'] == article['artifact_hash']]}
                                  for article in store.rows('news_articles')]
            if store.public_articles():
                raise ValueError('matrix_local_publication_forbidden')
        expected = expected_categories()
        report['passed'] = (len(report['results']) == len(expected) and all(row['passed'] and row['audit_performed'] for row in report['results'])
                            and {row.get('category') for row in report['results']} == expected
                            and len({row['source_id'] for row in report['results']}) == len(expected))
    except Exception as exc:
        report.update(passed=False, error=type(exc).__name__ + ':' + str(exc)[:220])
    finally:
        after = ledger(remote.client)
        report['trial_usage'] = [row for row in after if row['id'] not in report['baseline_request_ids']]
        report['new_charged_or_reserved_micro_usd'] = sum(row['charged_micro_usd'] for row in report['trial_usage'])
        report['ledger_total_micro_usd'] = sum(row['charged_micro_usd'] for row in after)
        report['provider_stats'] = provider.stats
        report['publication_enabled'] = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]['publication_enabled']
        if (report['publication_enabled'] or report['new_charged_or_reserved_micro_usd'] > MAX_MICRO_USD
                or len(report['trial_usage']) > MAX_REQUESTS
                or any(not row['settled_at'] or row['provider_status'] != 'completed' for row in report['trial_usage'])):
            report['passed'] = False
        try:
            assert_unchanged(remote, report)
            report['production_unchanged'] = True
        except NewsBudgetBlocked:
            report.update(production_unchanged=False, passed=False)
        report.update(state='completed', finished_at=now_iso())
        receipt(remote, report)
    return {k: v for k, v in report.items() if k not in {'articles', 'baseline_request_ids'}}


def verify_stop(remote, switch_check=None):
    report = json.loads(OUTPUT.read_text(encoding='utf-8'))
    marker = remote.get('news_ingestion_runs', TRIAL_ID)
    if not marker or marker['payload'].get('state') != 'completed' or marker['payload'].get('trial_usage') != report.get('trial_usage'):
        raise NewsBudgetBlocked('matrix_stop_receipt_mismatch')
    (switch_check or switches)(remote, False)
    assert_unchanged(remote, report)
    current = [row for row in ledger(remote.client) if row['id'] not in report['baseline_request_ids']]
    if sorted(current, key=lambda r: r['id']) != sorted(report['trial_usage'], key=lambda r: r['id']):
        raise NewsBudgetBlocked('matrix_usage_changed')
    report.update(owner_shutdown_verified=True, owner_shutdown_required=False, shutdown_verified_at=now_iso())
    receipt(remote, report)
    return {k: report[k] for k in ['passed', 'results', 'new_charged_or_reserved_micro_usd', 'owner_shutdown_verified', 'production_unchanged', 'publication_enabled']}


if __name__ == '__main__':
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--verify-stop', action='store_true')
    args = parser.parse_args()
    remote = NewsStore(backend='supabase')
    try:
        result = prepare(remote) if args.prepare else run(remote) if args.run else verify_stop(remote)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(0 if args.prepare or args.verify_stop or result.get('passed') else 1)
    finally:
        remote.close()
