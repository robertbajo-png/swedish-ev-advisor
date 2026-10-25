"""Explicit owner-authorized private trial using the real shared Postgres budget."""
import hashlib
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from news_ai import NewsAi, NewsBudgetBlocked
from news_engine import collect, editorial, process_items, registry, hydrate_item, models_for_news
from news_editorial import validate_fact_extraction, partition_fact_extraction, extract_facts, event_key, EDITORIAL_RECIPE
from news_http import Collector
from news_store import NewsStore, EDITORIAL_POLICY, now_iso
from refresh_verified_variants import save
from smoke_news_engine import verified_context

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/local/release-data/news-production/private-trial-result.json'
CARRYOVER = '334bc264-6074-542c-9472-ea94e4869d48'
TRIAL_ARTICLE = '42c2a7ca-ba3e-543b-b452-aa987524008f'


def config_for_trial(client):
    cfg = client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if cfg['publication_enabled'] or not cfg['enabled']:
        raise NewsBudgetBlocked('private_trial_requires_ai_on_and_publication_off')
    if cfg['daily_limit_micro_usd'] != 250000 or cfg['monthly_limit_micro_usd'] != 5000000:
        raise NewsBudgetBlocked('private_trial_budget_mismatch')
    historical = client.select('news_ai_requests', columns='charged_micro_usd,provider_status', filters={'id': 'eq.' + CARRYOVER})
    if not historical or historical[0]['charged_micro_usd'] != 90416 or historical[0]['provider_status'] != 'historical_settled':
        raise NewsBudgetBlocked('private_trial_previous_cost_not_reconciled')
    return cfg


def revalidate_trial_evidence(store, sources, collector):
    article = store.get('news_articles', TRIAL_ARTICLE)
    if not article or article['status'] == 'published':
        raise ValueError('private_originality_trial_requires_unpublished_draft')
    source_map = {s['id']: s for s in sources}
    def recoverable(item):
        reasons = item['payload'].get('quarantine_reasons', [])
        return (item['status'] == 'quarantined' and item['payload'].get('rejected_refresh_extraction')
                and reasons and all(reason.startswith(('fact_number_not_in_evidence:', 'evidence_not_verbatim:')) for reason in reasons))
    items = [i for i in store.rows('news_items') if i['cluster_id'] == article['cluster_id'] and (i['status'] == 'processed' or recoverable(i))]
    if not items:
        raise ValueError('private_originality_trial_requires_verified_facts')
    result = []
    for old in items:
        current, _ = hydrate_item(store, old, source_map, collector)
        errors = validate_fact_extraction(current['payload']['extraction'], current)
        if current['payload']['content_hash'] != old['payload']['content_hash'] or errors:
            store.put('news_items', {**current, 'status': 'quarantined', 'payload': {**current['payload'],
                      'quarantine_reasons': ['trial_evidence_changed_or_invalid', *errors]}})
            raise ValueError('private_originality_trial_evidence_changed_or_invalid')
        store.put('news_items', {**current, 'status': 'processed'})
        result.append({'item_id': current['id'], 'source_hash_unchanged': True, 'facts_revalidated': True})
    return result


def refresh_trial_facts(store, ai):
    article = store.get('news_articles', TRIAL_ARTICLE)
    if not article or article['status'] == 'published':
        raise ValueError('private_fact_refresh_requires_unpublished_draft')
    cluster = store.get('news_story_clusters', article['cluster_id'])
    items = [i for i in store.rows('news_items') if i['cluster_id'] == article['cluster_id'] and i['status'] == 'processed']
    if not cluster or len(items) != 1:
        raise ValueError('private_fact_refresh_requires_one_verified_source')
    item = items[0]
    candidate = item['payload'].get('rejected_refresh_extraction')
    raw = candidate or extract_facts(item, list(models_for_news(store)), ai)
    extraction, rejected, errors = partition_fact_extraction(raw, item)
    if event_key(extraction['event']) != cluster['event_key']:
        errors.append('trial_refresh_changed_event_identity')
    if errors:
        store.put('news_items', {**item, 'status': 'quarantined', 'payload': {**item['payload'],
                  'quarantine_reasons': errors, 'rejected_refresh_extraction': raw}})
        raise ValueError('private_fact_refresh_invalid:' + ';'.join(errors))
    store.put('news_items', {**item, 'payload': {**item['payload'], 'extraction': extraction,
              'fact_quarantine': rejected, 'extraction_refreshed_at': now_iso(), 'extraction_recipe': EDITORIAL_RECIPE}})
    return [{'item_id': item['id'], 'status': 'refreshed_verified_facts', 'fact_count': len(extraction['facts']),
             'quarantined_fact_count': len(rejected), 'reused_rejected_candidate': bool(candidate)}]


def run(originality_trial=False, structured_audit_trial=False, length_review_trial=False, final_review_trial=False, qualified_source_trial=False, qualified_review_trial=False, whole_article_trial=False):
    if sum((originality_trial, structured_audit_trial, length_review_trial, final_review_trial, qualified_source_trial, qualified_review_trial, whole_article_trial)) > 1:
        raise ValueError('select_one_private_trial')
    originality_trial = originality_trial or structured_audit_trial or length_review_trial or final_review_trial or qualified_source_trial or qualified_review_trial or whole_article_trial
    if originality_trial and datetime.now(timezone.utc).date().isoformat() != '2026-10-21':
        raise ValueError('private_originality_trial_authorization_date_expired')
    request_ceiling = 25 if whole_article_trial else 24 if qualified_source_trial or qualified_review_trial else 21 if final_review_trial else 19 if length_review_trial else 15 if structured_audit_trial else 12 if originality_trial else 8
    output = OUTPUT.with_name('whole-article-trial-result.json' if whole_article_trial else 'qualified-review-trial-result.json' if qualified_review_trial else 'qualified-source-trial-result.json' if qualified_source_trial else 'length-final-review-r7-result.json' if final_review_trial else 'length-review-trial-result.json' if length_review_trial else
                              'structured-audit-trial-result.json' if structured_audit_trial else 'originality-trial-result.json') if originality_trial else OUTPUT
    os.environ['NEWS_SOURCE_PROFILE'] = 'official'
    os.environ['NEWS_BACKEND'] = 'supabase'
    store = NewsStore(backend='supabase')
    public_file = ROOT / 'public/data/news_articles.json'
    public_hash = hashlib.sha256(public_file.read_bytes()).hexdigest()
    initial_public = store.public_articles()
    report = {'started_at': now_iso(), 'policy': EDITORIAL_POLICY, 'recipe': EDITORIAL_RECIPE,
              'publish': False, 'public_export': False, 'maximum_cumulative_requests': request_ceiling}
    provider = NewsAi(store.client)
    try:
        report['configuration'] = config_for_trial(store.client)
        before = store.client.select('news_ai_requests', columns='id,charged_micro_usd')
        before_ids = {r['id'] for r in before}
        def guarded_ai(name, schema, prompt):
            config_for_trial(store.client)
            allowed_stages = {'swedish_ev_article', 'ev_news_independent_audit', 'ev_news_block_repair'}
            if length_review_trial:
                allowed_stages.add('ev_news_facts')
            if originality_trial and name not in allowed_stages:
                raise NewsBudgetBlocked('private_originality_trial_editorial_only')
            paid_attempts = store.client.select('news_ai_requests', columns='id', filters={
                'stage': 'neq.historical_isolated_test', 'created_at': 'gte.2026-10-21T00:00:00+00:00'})
            if len(paid_attempts) >= request_ceiling:
                raise NewsBudgetBlocked('private_trial_call_limit')
            return provider(name, schema, prompt)
        collector = Collector(tls_context=verified_context())
        sources = registry()
        if originality_trial:
            baseline = [r for r in before if r['id'] != CARRYOVER]
            minimum = 23 if whole_article_trial else 22 if qualified_review_trial else 20 if qualified_source_trial else 18 if final_review_trial else 14 if length_review_trial else 12 if structured_audit_trial else 8
            if not minimum <= len(baseline) <= request_ceiling:
                raise ValueError('private_originality_trial_previous_run_missing_or_limit_reached')
            report['source_verification'] = revalidate_trial_evidence(store, sources, collector)
            report['collection'] = {'skipped': 'reusing_refetched_and_revalidated_facts'}
        else:
            report['collection'] = collect(store, sources, collector=collector, max_items=5, force=True)
        report['rounds'] = []
        for _ in range(1 if originality_trial else 12):
            extraction = refresh_trial_facts(store, guarded_ai) if length_review_trial else [] if originality_trial else process_items(store, sources, max_items=1, ai=guarded_ai, collector=collector)
            assessment = editorial(store, max_stories=1, ai=guarded_ai, publish=False, retry=originality_trial,
                                   max_revisions=0 if final_review_trial or qualified_review_trial or whole_article_trial else 1,
                                   _only_articles={TRIAL_ARTICLE} if originality_trial else None)
            report['rounds'].append({'extraction': extraction, 'editorial': assessment})
            if any(r['status'] == 'validated_draft' for r in assessment):
                break
            if provider.stats['provider_requests'] >= 8:
                break
            pending = [r for r in store.rows('news_items') if r['status'] == 'collected']
            if not pending and not extraction:
                break
        articles = store.rows('news_articles')
        checks = store.rows('news_quality_checks')
        report['articles'] = [{'id': a['id'], 'status': a['status'], 'artifact_hash': a['artifact_hash'],
                               'payload': a['payload'], 'checks': [c for c in checks
                               if c['article_id'] == a['id'] and c['artifact_hash'] == a['artifact_hash']]} for a in articles]
        after = store.client.select('news_ai_requests', columns='id,stage,charged_micro_usd,settled_at,provider_status,input_tokens,output_tokens')
        new_rows = [r for r in after if r['id'] not in before_ids]
        report['trial_usage'] = new_rows
        report['new_charged_or_reserved_micro_usd'] = sum(r['charged_micro_usd'] for r in new_rows)
        report['ledger_total_micro_usd'] = sum(r['charged_micro_usd'] for r in after)
        report['provider_stats'] = provider.stats
        report['public_database_unchanged'] = store.public_articles() == initial_public
        report['public_file_unchanged'] = hashlib.sha256(public_file.read_bytes()).hexdigest() == public_hash
        report['publication_enabled'] = store.client.select('news_ai_config', columns='publication_enabled', filters={'id': 'eq.production'})[0]['publication_enabled']
        validated = {r['article_id'] for step in report['rounds'] for r in step['editorial'] if r['status'] == 'validated_draft'}
        report['passed'] = bool(validated) and report['public_database_unchanged'] and report['public_file_unchanged'] and not report['publication_enabled']
        report['finished_at'] = now_iso()
        save(output, report)
        print(json.dumps({k: v for k, v in report.items() if k not in ('articles', 'configuration')}, ensure_ascii=True, indent=2))
        print(json.dumps({'private_report': str(output), 'titles': [a['payload']['title'] for a in articles]}, ensure_ascii=True))
        return report['passed']
    finally:
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--originality-trial', action='store_true', help='Owner-authorized follow-up: four additional calls, private editorial only')
    mode.add_argument('--structured-audit-trial', action='store_true', help='Bounded completion: up to three further calls, unchanged shared budget')
    mode.add_argument('--length-review-trial', action='store_true', help='Owner-authorized factual coverage/length test: at most five additional calls, no publication')
    mode.add_argument('--final-review-trial', action='store_true', help='Bounded two-call completion after length test; no extraction, revision or publication')
    mode.add_argument('--qualified-source-trial', action='store_true', help='At most four further editorial calls using literal primary-source qualifiers; no publication')
    mode.add_argument('--qualified-review-trial', action='store_true', help='Two-call completion within the same 24-request ceiling, without automatic revision or publication')
    mode.add_argument('--whole-article-trial', action='store_true', help='Final two-call whole-text schema check within unchanged shared dollar limits; no revision or publication')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.originality_trial, args.structured_audit_trial, args.length_review_trial, args.final_review_trial, args.qualified_source_trial, args.qualified_review_trial, args.whole_article_trial) else 1)
