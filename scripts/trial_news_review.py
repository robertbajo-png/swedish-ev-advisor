"""One owner-authorized, single-use private review trial. Never publishes or exports."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from news_ai import NewsAi, NewsBudgetBlocked, MODEL
from news_engine import editorial, registry
from news_http import Collector
from news_store import NewsStore, EDITORIAL_POLICY, artifact_hash, now_iso, stable_id
from news_editorial import EDITORIAL_RECIPE, blocks, audit_article, validate_article
from refresh_verified_variants import save
from smoke_news_engine import verified_context
from supabase_client import load_local_env
from trial_news_release import TRIAL_ARTICLE, config_for_trial, revalidate_trial_evidence

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_DATE = '2026-10-22'
TRIAL_ID = stable_id('private-news-review-trial:' + AUTHORIZED_DATE)
MAX_REQUESTS = 5
MAX_MICRO_USD = 100000
OUTPUT = ROOT / 'data/local/release-data/news-production/review-trial-2026-10-22.json'
PUBLIC_FILE = ROOT / 'public/data/news_articles.json'
REQUIRED_RECIPE = None


def select_writing_trial():
    """A separately authorized single-use r12 trial, not a reset of the review trial."""
    global TRIAL_ID, MAX_MICRO_USD, OUTPUT, REQUIRED_RECIPE
    TRIAL_ID = stable_id('private-news-writing-r12:' + AUTHORIZED_DATE)
    MAX_MICRO_USD = 60000
    OUTPUT = ROOT / 'data/local/release-data/news-production/writing-r12-trial-2026-10-22.json'
    REQUIRED_RECIPE = 'news-editorial-recipe-2026-10-r12'


def select_independent_writing_trial():
    """Owner-authorized r13 test, retaining all previous trial charges and markers."""
    global TRIAL_ID, MAX_MICRO_USD, OUTPUT, REQUIRED_RECIPE
    TRIAL_ID = stable_id('private-news-writing-r13:' + AUTHORIZED_DATE)
    MAX_MICRO_USD = 60000
    OUTPUT = ROOT / 'data/local/release-data/news-production/writing-r13-trial-2026-10-22.json'
    REQUIRED_RECIPE = 'news-editorial-recipe-2026-10-r13'


def select_claim_grounding_trial():
    """Owner-authorized r14 grounding/question trial; earlier receipts remain consumed."""
    global TRIAL_ID, MAX_MICRO_USD, OUTPUT, REQUIRED_RECIPE
    TRIAL_ID = stable_id('private-news-writing-r14:' + AUTHORIZED_DATE)
    MAX_MICRO_USD = 60000
    OUTPUT = ROOT / 'data/local/release-data/news-production/writing-r14-trial-2026-10-22.json'
    REQUIRED_RECIPE = 'news-editorial-recipe-2026-10-r14'


def select_fact_plan_trial():
    """Owner-authorized r15 trial after broad offline fact-plan regression tests."""
    global TRIAL_ID, MAX_MICRO_USD, OUTPUT, REQUIRED_RECIPE
    TRIAL_ID = stable_id('private-news-writing-r15:' + AUTHORIZED_DATE)
    MAX_MICRO_USD = 60000
    OUTPUT = ROOT / 'data/local/release-data/news-production/writing-r15-trial-2026-10-22.json'
    REQUIRED_RECIPE = 'news-editorial-recipe-2026-10-r15'


def select_language_editing_trial():
    """Owner-authorized r16 trial; never resets prior receipts or global allowances."""
    global TRIAL_ID, MAX_MICRO_USD, OUTPUT, REQUIRED_RECIPE
    TRIAL_ID = stable_id('private-news-writing-r16:' + AUTHORIZED_DATE)
    MAX_MICRO_USD = 60000
    OUTPUT = ROOT / 'data/local/release-data/news-production/writing-r16-trial-2026-10-22.json'
    REQUIRED_RECIPE = 'news-editorial-recipe-2026-10-r16'


def select_fact_brief_trial():
    """Owner-authorized r17 trial after offline evidence and prose regression."""
    global TRIAL_ID, MAX_MICRO_USD, OUTPUT, REQUIRED_RECIPE
    TRIAL_ID = stable_id('private-news-writing-r17:' + AUTHORIZED_DATE)
    MAX_MICRO_USD = 60000
    OUTPUT = ROOT / 'data/local/release-data/news-production/writing-r17-trial-2026-10-22.json'
    REQUIRED_RECIPE = 'news-editorial-recipe-2026-10-r17'


def require_date():
    if datetime.now(timezone.utc).date().isoformat() != AUTHORIZED_DATE:
        raise NewsBudgetBlocked('private_review_authorization_date_expired')
    if REQUIRED_RECIPE and EDITORIAL_RECIPE != REQUIRED_RECIPE:
        raise NewsBudgetBlocked('private_review_authorized_recipe_changed')


def ledger(client):
    return client.select('news_ai_requests', columns=(
        'id,stage,charged_micro_usd,reserved_micro_usd,provider_status,'
        'input_tokens,output_tokens,settled_at,budget_closed_at'), filters={'limit': 1000})


class TrialClient:
    def __init__(self, client, baseline_ids, stages=None, *, maximum_requests=None, maximum_micro_usd=None, authorize=None):
        self.client = client
        self.baseline_ids = set(baseline_ids)
        self.stages = stages if stages is not None else {'swedish_ev_article', 'ev_news_independent_audit', 'ev_news_block_repair'}
        self.maximum_requests = maximum_requests
        self.maximum_micro_usd = maximum_micro_usd
        self.authorize = authorize

    def select(self, *args, **kwargs):
        return self.client.select(*args, **kwargs)

    def upsert(self, table, *args, **kwargs):
        if table != 'news_ingestion_runs':
            raise NewsBudgetBlocked('private_review_receipts_only')
        return self.client.upsert(table, *args, **kwargs)

    def _request(self, method, path, body):
        if method != 'POST' or path not in ('rpc/reserve_news_ai', 'rpc/settle_news_ai'):
            raise NewsBudgetBlocked('private_review_budget_rpcs_only')
        if path == 'rpc/reserve_news_ai':
            (self.authorize or require_date)()
            config_for_trial(self.client)
            if body.get('stage_key') not in self.stages:
                raise NewsBudgetBlocked('private_review_editorial_only')
            if body.get('model_key') != MODEL:
                raise NewsBudgetBlocked('private_review_model_mismatch')
            bounds = [body.get('input_bound'), body.get('output_bound')]
            if any(type(value) is not int or value <= 0 for value in bounds):
                raise NewsBudgetBlocked('private_review_invalid_reservation')
            new_rows = [row for row in ledger(self.client) if row['id'] not in self.baseline_ids]
            # Same conservative standard-tier rates as the authoritative reserve RPC.
            maximum = (bounds[0] * 3 + bounds[1] * 18 + 3) // 4
            if len(new_rows) >= (MAX_REQUESTS if self.maximum_requests is None else self.maximum_requests):
                raise NewsBudgetBlocked('private_review_request_limit')
            if sum(row['charged_micro_usd'] for row in new_rows) + maximum > (MAX_MICRO_USD if self.maximum_micro_usd is None else self.maximum_micro_usd):
                raise NewsBudgetBlocked('private_review_cost_limit')
        return self.client._request(method, path, body)


def prepare(store):
    require_date()
    if store.get('news_ingestion_runs', TRIAL_ID):
        raise NewsBudgetBlocked('private_review_already_prepared_or_consumed')
    cfg = store.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if (cfg['enabled'] or cfg['publication_enabled'] or cfg['daily_limit_micro_usd'] != 250000
            or cfg['monthly_limit_micro_usd'] != 5000000):
        raise NewsBudgetBlocked('private_review_preparation_requires_paused_unchanged_budget')
    if store.client.select('news_ai_requests', columns='id', filters={
            'settled_at': 'is.null', 'budget_closed_at': 'is.null', 'limit': 1}):
        raise NewsBudgetBlocked('private_review_unresolved_usage')
    evidence = revalidate_trial_evidence(store, registry(), Collector(tls_context=verified_context()))
    baseline = ledger(store.client)
    payload = {'kind': 'private_news_review_trial', 'state': 'prepared', 'at': now_iso(),
               'trial_id': TRIAL_ID, 'required_recipe': REQUIRED_RECIPE,
               'authorization_date': AUTHORIZED_DATE, 'article_id': TRIAL_ARTICLE,
               'maximum_requests': MAX_REQUESTS, 'maximum_micro_usd': MAX_MICRO_USD,
               'baseline_request_ids': [row['id'] for row in baseline],
               'public_file_hash': hashlib.sha256(PUBLIC_FILE.read_bytes()).hexdigest(),
               'public_database_hash': artifact_hash(store.public_articles()),
               'source_verification': evidence, 'publish': False, 'public_export': False}
    store.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': payload})
    return {key: value for key, value in payload.items() if key != 'baseline_request_ids'}


def resume_original(store, marker):
    previous = marker['payload']
    if previous.get('state') != 'completed' or previous.get('resume_count', 0) != 0:
        raise NewsBudgetBlocked('private_review_format_continuation_already_consumed')
    if (len(previous.get('trial_usage', [])) != 1
            or not any(row.get('reason') == 'ValueError:writer_block_alignment' for row in previous.get('editorial', []))):
        raise NewsBudgetBlocked('private_review_format_continuation_not_applicable')
    saved = json.loads(OUTPUT.read_text(encoding='utf-8'))
    for key in ('authorization_date', 'article_id', 'maximum_requests', 'maximum_micro_usd',
                'public_file_hash', 'public_database_hash', 'trial_usage'):
        if saved.get(key) != previous.get(key):
            raise NewsBudgetBlocked('private_review_saved_receipt_mismatch')
    rows = [row for row in ledger(store.client) if row['id'] not in saved['baseline_request_ids']]
    if rows != previous['trial_usage'] or any(not row['settled_at'] or row['provider_status'] != 'completed' for row in rows):
        raise NewsBudgetBlocked('private_review_continuation_usage_changed_or_unknown')
    return saved


def run(store, resume_format=False):
    require_date()
    if REQUIRED_RECIPE and resume_format:
        raise NewsBudgetBlocked('private_writing_trial_has_no_format_continuation')
    marker = store.get('news_ingestion_runs', TRIAL_ID)
    if not marker or (not resume_format and marker['payload'].get('state') != 'prepared'):
        raise NewsBudgetBlocked('private_review_requires_unused_preparation')
    original = resume_original(store, marker) if resume_format else marker['payload']
    if (original.get('article_id') != TRIAL_ARTICLE or original.get('authorization_date') != AUTHORIZED_DATE
            or original.get('maximum_requests') != MAX_REQUESTS or original.get('maximum_micro_usd') != MAX_MICRO_USD):
        raise NewsBudgetBlocked('private_review_preparation_contract_mismatch')
    if REQUIRED_RECIPE and (original.get('trial_id') != TRIAL_ID or original.get('required_recipe') != REQUIRED_RECIPE):
        raise NewsBudgetBlocked('private_writing_trial_recipe_contract_mismatch')
    config_for_trial(store.client)
    provider = NewsAi(TrialClient(store.client, original['baseline_request_ids']))
    original_keys = {'kind', 'trial_id', 'required_recipe', 'authorization_date', 'article_id', 'maximum_requests', 'maximum_micro_usd',
                     'baseline_request_ids', 'public_file_hash', 'public_database_hash', 'source_verification',
                     'publish', 'public_export', 'at'}
    report = {**{key: value for key, value in original.items() if key in original_keys},
              'state': 'running', 'started_at': now_iso(), 'policy': EDITORIAL_POLICY,
              'recipe': EDITORIAL_RECIPE, 'passed': False, 'owner_shutdown_required': True}
    if resume_format:
        report['resume_count'] = 1
        report['previous_attempts'] = [{key: value for key, value in original.items()
                                       if key not in {'articles', 'baseline_request_ids'}}]
    store.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': report})
    try:
        report['source_verification'] = revalidate_trial_evidence(store, registry(), Collector(tls_context=verified_context()))
        if artifact_hash(store.public_articles()) != original['public_database_hash']:
            raise NewsBudgetBlocked('private_review_public_database_changed_before_start')
        if hashlib.sha256(PUBLIC_FILE.read_bytes()).hexdigest() != original['public_file_hash']:
            raise NewsBudgetBlocked('private_review_public_file_changed_before_start')
        report['editorial'] = editorial(store, max_stories=1, ai=provider, retry=True,
                                        max_revisions=1, _only_articles={TRIAL_ARTICLE}, publish=False)
    except Exception as exc:
        report['error'] = type(exc).__name__ + ':' + str(exc)[:180]
    finally:
        after = ledger(store.client)
        new_rows = [row for row in after if row['id'] not in original['baseline_request_ids']]
        report['trial_usage'] = new_rows
        report['new_charged_or_reserved_micro_usd'] = sum(row['charged_micro_usd'] for row in new_rows)
        report['ledger_total_micro_usd'] = sum(row['charged_micro_usd'] for row in after)
        report['provider_stats'] = provider.stats
        report['public_database_unchanged'] = artifact_hash(store.public_articles()) == original['public_database_hash']
        report['public_file_unchanged'] = hashlib.sha256(PUBLIC_FILE.read_bytes()).hexdigest() == original['public_file_hash']
        cfg = store.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
        report['publication_enabled'] = cfg['publication_enabled']
        article = store.get('news_articles', TRIAL_ARTICLE)
        checks = [check for check in store.rows('news_quality_checks')
                  if check['article_id'] == TRIAL_ARTICLE and check['artifact_hash'] == article['artifact_hash']]
        passing = {check['kind'] for check in checks if check['passed']
                   and check['payload'].get('policy_version') == EDITORIAL_POLICY}
        report['articles'] = [{**article, 'word_count': sum(len(block['text'].split()) for block in blocks(article['payload'])),
                               'checks': checks}]
        report['passed'] = (any(row['status'] == 'validated_draft' for row in report.get('editorial', []))
                            and passing == {'evidence', 'editorial', 'originality'}
                            and report['public_database_unchanged'] and report['public_file_unchanged']
                            and not report['publication_enabled'] and article['status'] == 'draft')
        report.update(state='completed', finished_at=now_iso())
        save(OUTPUT, report)
        store.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': {key: value for key, value in report.items()
                                                                 if key not in {'articles', 'baseline_request_ids'}}})
    return {key: value for key, value in report.items() if key not in {'articles', 'baseline_request_ids'}}


def verify_stop(store):
    report = json.loads(OUTPUT.read_text(encoding='utf-8'))
    marker = store.get('news_ingestion_runs', TRIAL_ID)
    if not marker or marker['payload'].get('state') != 'completed' or marker['payload'].get('trial_usage') != report.get('trial_usage'):
        raise NewsBudgetBlocked('private_review_stop_receipt_mismatch')
    cfg = store.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if (cfg['enabled'] or cfg['publication_enabled'] or cfg['daily_limit_micro_usd'] != 250000
            or cfg['monthly_limit_micro_usd'] != 5000000):
        raise NewsBudgetBlocked('private_review_shutdown_not_verified')
    current = [row for row in ledger(store.client) if row['id'] not in report['baseline_request_ids']]
    if sorted(current, key=lambda row: row['id']) != sorted(report['trial_usage'], key=lambda row: row['id']):
        raise NewsBudgetBlocked('private_review_usage_changed_after_trial')
    if (artifact_hash(store.public_articles()) != report['public_database_hash']
            or hashlib.sha256(PUBLIC_FILE.read_bytes()).hexdigest() != report['public_file_hash']):
        raise NewsBudgetBlocked('private_review_public_surface_changed')
    report.update(owner_shutdown_required=False, owner_shutdown_verified=True,
                  ai_enabled_after_trial=False, shutdown_verified_at=now_iso())
    save(OUTPUT, report)
    store.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': {key: value for key, value in report.items()
                                                              if key not in {'articles', 'baseline_request_ids'}}})
    return {key: report[key] for key in ('passed', 'owner_shutdown_verified', 'new_charged_or_reserved_micro_usd',
                                        'public_database_unchanged', 'public_file_unchanged', 'publication_enabled')}


def diagnostic_final_audit(store):
    """One requested diagnostic audit of an unchanged scoped failure; no rewriting or approval."""
    require_date()
    if REQUIRED_RECIPE not in {'news-editorial-recipe-2026-10-r13', 'news-editorial-recipe-2026-10-r14', 'news-editorial-recipe-2026-10-r15', 'news-editorial-recipe-2026-10-r16', 'news-editorial-recipe-2026-10-r17'}:
        raise NewsBudgetBlocked('private_final_audit_requires_scoped_writing_trial')
    report = json.loads(OUTPUT.read_text(encoding='utf-8'))
    marker = store.get('news_ingestion_runs', TRIAL_ID)
    if (not marker or marker['payload'].get('state') != 'completed' or report.get('passed') is not False
            or report.get('final_review_state') or marker['payload'].get('final_review_state')
            or report.get('trial_id') != TRIAL_ID or report.get('required_recipe') != REQUIRED_RECIPE
            or report.get('maximum_requests') != MAX_REQUESTS or report.get('maximum_micro_usd') != MAX_MICRO_USD
            or marker['payload'].get('trial_usage') != report.get('trial_usage')):
        raise NewsBudgetBlocked('private_final_audit_requires_unused_matching_receipt')
    current = [row for row in ledger(store.client) if row['id'] not in report['baseline_request_ids']]
    if (sorted(current, key=lambda row: row['id']) != sorted(report['trial_usage'], key=lambda row: row['id'])
            or any(not row['settled_at'] or row['provider_status'] != 'completed' for row in current)):
        raise NewsBudgetBlocked('private_final_audit_usage_changed_or_unknown')
    article = store.get('news_articles', TRIAL_ARTICLE)
    if (article['status'] != 'quarantined' or article['artifact_hash'] != report['articles'][0]['artifact_hash']
            or article['payload'] != report['articles'][0]['payload']):
        raise NewsBudgetBlocked('private_final_audit_draft_changed')
    checks = [check for check in store.rows('news_quality_checks') if check['article_id'] == TRIAL_ARTICLE
              and check['artifact_hash'] == article['artifact_hash'] and check['kind'] == 'evidence']
    if len(checks) != 1 or not checks[0]['payload'].get('fact_inventory'):
        raise NewsBudgetBlocked('private_final_audit_missing_fact_inventory')
    if checks[0]['payload'].get('audit_performed'):
        raise NewsBudgetBlocked('private_final_audit_already_reviewed')
    facts = checks[0]['payload']['fact_inventory']
    config_for_trial(store.client)
    provider = NewsAi(TrialClient(store.client, report['baseline_request_ids'], stages={'ev_news_independent_audit'}))
    report.update(final_review_state='running', owner_shutdown_required=True, owner_shutdown_verified=False)
    store.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': {key: value for key, value in report.items()
                                                              if key not in {'articles', 'baseline_request_ids'}}})
    try:
        revalidate_trial_evidence(store, registry(), Collector(tls_context=verified_context()))
        if (artifact_hash(store.public_articles()) != report['public_database_hash']
                or hashlib.sha256(PUBLIC_FILE.read_bytes()).hexdigest() != report['public_file_hash']):
            raise NewsBudgetBlocked('private_final_audit_public_surface_changed')
        items = [item for item in store.rows('news_items') if item['cluster_id'] == article['cluster_id']]
        audit = audit_article(article['payload'], facts, provider)
        report['diagnostic_final_review'] = {'artifact_hash': article['artifact_hash'], 'audit': audit,
            'gate_errors': validate_article(article['payload'], facts, items, audit, article['payload']['relevance_score']),
            'audit_performed': True, 'diagnostic_only': True, 'approval': False}
    except Exception as exc:
        report['final_review_error'] = type(exc).__name__ + ':' + str(exc)[:180]
    finally:
        after = ledger(store.client)
        report['trial_usage'] = [row for row in after if row['id'] not in report['baseline_request_ids']]
        report['new_charged_or_reserved_micro_usd'] = sum(row['charged_micro_usd'] for row in report['trial_usage'])
        report['ledger_total_micro_usd'] = sum(row['charged_micro_usd'] for row in after)
        report['final_review_provider_stats'] = provider.stats
        report['public_database_unchanged'] = artifact_hash(store.public_articles()) == report['public_database_hash']
        report['public_file_unchanged'] = hashlib.sha256(PUBLIC_FILE.read_bytes()).hexdigest() == report['public_file_hash']
        report['publication_enabled'] = store.client.select('news_ai_config', filters={'id': 'eq.production'})[0]['publication_enabled']
        report.update(final_review_state='completed', final_review_completed_at=now_iso(), passed=False)
        save(OUTPUT, report)
        store.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': {key: value for key, value in report.items()
                                                                  if key not in {'articles', 'baseline_request_ids'}}})
    return {key: value for key, value in report.items() if key not in {'articles', 'baseline_request_ids'}}


if __name__ == '__main__':
    load_local_env()
    os.environ['NEWS_SOURCE_PROFILE'] = 'official'
    os.environ['NEWS_BACKEND'] = 'supabase'
    parser = argparse.ArgumentParser(description=__doc__)
    profile = parser.add_mutually_exclusive_group()
    profile.add_argument('--writing-r12', action='store_true', help='Separate single-use r12 writing/audit trial, maximum USD 0.06; never publishes')
    profile.add_argument('--writing-r13', action='store_true', help='Separate single-use r13 writing/audit trial, maximum USD 0.06; never publishes')
    profile.add_argument('--writing-r14', action='store_true', help='Separate single-use r14 grounding/question trial, maximum USD 0.06; never publishes')
    profile.add_argument('--writing-r15', action='store_true', help='Separate single-use r15 fact-plan trial, maximum USD 0.06; never publishes')
    profile.add_argument('--writing-r16', action='store_true', help='Single-use r16 language/comparison trial, maximum USD 0.06; never publishes')
    profile.add_argument('--writing-r17', action='store_true', help='Single-use r17 factual-brief trial, maximum USD 0.06; never publishes')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--resume-format', action='store_true', help='One continuation of a known settled format failure; original cost/call bounds are retained')
    mode.add_argument('--verify-stop', action='store_true', help='Read-only budget/public checks and private receipt; never calls AI')
    mode.add_argument('--final-audit', action='store_true', help='Single scoped diagnostic audit within original cap; no rewriting, gate approval or publication')
    args = parser.parse_args()
    if args.writing_r12:
        select_writing_trial()
    elif args.writing_r13:
        select_independent_writing_trial()
    elif args.writing_r14:
        select_claim_grounding_trial()
    elif args.writing_r15:
        select_fact_plan_trial()
    elif args.writing_r16:
        select_language_editing_trial()
    elif args.writing_r17:
        select_fact_brief_trial()
    store = NewsStore(backend='supabase')
    try:
        result = (prepare(store) if args.prepare else verify_stop(store) if args.verify_stop else
                  diagnostic_final_audit(store) if args.final_audit else run(store, args.resume_format))
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(0 if args.prepare or args.verify_stop or result.get('passed') else 1)
    finally:
        store.close()
