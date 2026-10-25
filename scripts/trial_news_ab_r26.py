"""One frozen, private two-model benchmark. No publishing or production model change."""
import argparse
import copy
import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from news_ai import NewsAi, NewsBudgetBlocked
from news_editorial import (EDITORIAL_RECIPE, extract_facts, partition_fact_extraction, market_qualified_facts,
    source_qualifier_facts, generate_article, article_preflight, audit_article, validate_article, relevance_score)
from news_engine import hydrate_item, registry, models_for_news
from news_fact_brief import neutral_facts, source_technical_facts
from news_http import Collector
from news_store import NewsStore, artifact_hash, stable_id, now_iso
from refresh_verified_variants import save
from smoke_news_engine import verified_context
from supabase_client import load_local_env
from trial_news_matrix import PrivateMatrixStore

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-10-23'
TRIAL_ID = stable_id('private-news-ab-r26:' + DATE)
RECIPE = 'news-editorial-recipe-2026-10-r25-power-options'
CAP = 200000
REVIEW_MODEL = 'gpt-5.4-mini'
MODELS = [('full', 'gpt-5.4'), ('mini', 'gpt-5.4-mini')]
DIRECTORY = ROOT / 'data/local/release-data/news-production'
MANIFEST = DIRECTORY / ('ab-r26-manifest-' + DATE + '.json')
REPORT = DIRECTORY / ('ab-r26-result-' + DATE + '.json')
DATABASE = ROOT / ('data/local/news-ab-r26-' + DATE + '.sqlite')
SOURCE_DB = ROOT / 'data/local/news-breadth-r25-2026-10-23.sqlite'
PARENT = '84dac241-5af0-518f-a7a0-9169f90e6d1c'
ASSIGNMENTS = {
    'model': 'Report the announced model/power versions, range, charging and market timing. Do not invent omitted information.',
    'price': ('Report the actual announced Swedish purchase or leasing prices, exact variants and payment periods. '
              'Prioritize a fully market-qualified quote where available. Do not turn leasing into a purchase price, '
              'infer contract terms, claim a discount without a prior price or manufacture enough facts. '
              'If the evidence is insufficient, say so through the existing relevance/fact fields.'),
    'statistics': ('Report the EU registration release, preserving market, powertrain, year-to-date period and denominators. '
                   'Assess Swedish relevance independently; neither a benchmark label nor a target score is evidence.'),
}


def authorize():
    if datetime.now(timezone.utc).date().isoformat() != DATE or EDITORIAL_RECIPE != RECIPE:
        raise NewsBudgetBlocked('ab_date_or_recipe_changed')


def usage(client):
    rows = client.select('news_ai_requests', columns=(
        'id,created_at,stage,model,ab_test_id,ab_cell_key,charged_micro_usd,reserved_micro_usd,'
        'input_tokens,output_tokens,provider_status,settled_at,budget_closed_at'), filters={'limit': 1000})
    if len(rows) >= 1000 or any(type(r['charged_micro_usd']) is not int or r['charged_micro_usd'] < 0 for r in rows):
        raise NewsBudgetBlocked('ab_invalid_or_truncated_ledger')
    return rows


def paused(remote):
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if (cfg['enabled'] or cfg['publication_enabled'] or cfg['model'] != 'gpt-5.4-mini'
            or cfg['daily_limit_micro_usd'] != 250000 or cfg['monthly_limit_micro_usd'] != 5000000
            or cfg['pricing_valid_until'] <= DATE):
        raise NewsBudgetBlocked('ab_requires_paused_unchanged_configuration')
    return cfg


def budget(remote):
    authorize()
    cfg = paused(remote)
    rows = usage(remote.client)
    pending = [r['id'] for r in rows if not r['settled_at'] and not r['budget_closed_at']]
    day = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE))
    month = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE[:7]))
    return {'daily_used_micro_usd': day, 'monthly_used_micro_usd': month, 'pending': pending,
            'trial_cap_micro_usd': CAP, 'allowed': not pending and CAP <= min(
                cfg['daily_limit_micro_usd'] - day, cfg['monthly_limit_micro_usd'] - month)}


def surfaces(remote):
    return {'production_articles': artifact_hash(remote.rows('news_articles')),
            'public_news': artifact_hash(remote.public_articles()),
            'public_models': artifact_hash(remote.client.select('public_ev_models')),
            'public_variants': artifact_hash(remote.client.select('public_ev_variants')),
            'news_export': hashlib.sha256((ROOT / 'public/data/news_articles.json').read_bytes()).hexdigest()}


def manifest():
    data = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if (data['trial_id'] != TRIAL_ID or data['recipe'] != RECIPE or data['cap_micro_usd'] != CAP
            or data['models'] != [list(m) for m in MODELS] or data['review_model'] != REVIEW_MODEL
            or data['assignments'] != ASSIGNMENTS or data['max_requests'] != 18
            or data['publish'] is not False or data['cache'] is not False or data['revisions'] != 0
            or set(data['items']) != {'vw-sweden-press', 'acea'}):
        raise NewsBudgetBlocked('ab_frozen_manifest_changed')
    return data


def receipt(remote, report):
    save(REPORT, report)
    remote.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': {
        k: v for k, v in report.items() if k not in {'baseline_ids'}}})


def prepare(remote, collector=None):
    authorize()
    if MANIFEST.exists() or REPORT.exists() or DATABASE.exists() or remote.get('news_ingestion_runs', TRIAL_ID):
        raise NewsBudgetBlocked('ab_preparation_already_exists')
    ready = budget(remote)
    if not ready['allowed']:
        raise NewsBudgetBlocked('ab_insufficient_ordinary_allowance')
    parent = remote.get('news_ingestion_runs', PARENT)
    if not parent or not parent['payload'].get('owner_shutdown_verified') or parent['payload'].get('state') != 'completed':
        raise NewsBudgetBlocked('ab_requires_stopped_parent')
    sources = {s['id']: s for s in registry()}
    original = {}
    with closing(sqlite3.connect(SOURCE_DB.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        for source_id in ['vw-sweden-press', 'acea']:
            rows = db.execute('select id,source_id,url,cluster_id,status,payload from news_items where source_id=?', (source_id,)).fetchall()
            if len(rows) != 1:
                raise ValueError('ab_requires_one_frozen_source_per_publisher')
            row = dict(zip(['id','source_id','url','cluster_id','status','payload'], rows[0]))
            row['payload'] = json.loads(row['payload'])
            for key in ['extraction','fact_checkpoint','fact_quarantine','quarantine_reasons','attempts','retry_after','budget_retry_after']:
                row['payload'].pop(key, None)
            original[source_id] = {**row, 'status': 'collected', 'cluster_id': None}
    collector = collector or Collector(tls_context=verified_context())
    with closing(PrivateMatrixStore(DATABASE)) as store:
        for key, item in original.items():
            refreshed, _ = hydrate_item(store, item, sources, collector)
            if refreshed['payload']['content_hash'] != item['payload']['content_hash']:
                raise ValueError('ab_source_changed_before_freeze')
            original[key] = refreshed
    frozen = {'trial_id': TRIAL_ID, 'date': DATE, 'recipe': RECIPE, 'at': now_iso(),
              'cap_micro_usd': CAP, 'max_requests': 18, 'models': MODELS, 'review_model': REVIEW_MODEL,
              'assignments': ASSIGNMENTS, 'sources': sources, 'items': original,
              'model_keys': sorted(models_for_news(remote)), 'publish': False, 'cache': False, 'revisions': 0}
    save(MANIFEST, frozen)
    # Serialize/re-read once so tuple/list representation cannot change the manifest digest.
    frozen = manifest()
    report = {'trial_id': TRIAL_ID, 'state': 'prepared', 'manifest_hash': artifact_hash(frozen),
              'cap_micro_usd': CAP, 'max_requests': 18, 'baseline_ids': [r['id'] for r in usage(remote.client)],
              'baseline_surfaces': surfaces(remote), 'budget_before': ready, 'cells': [], 'publish': False}
    receipt(remote, report)
    return {k: v for k, v in report.items() if k != 'baseline_ids'}


class AbClient:
    def __init__(self, client, digest, cell):
        self.client, self.digest, self.cell = client, digest, cell

    def select(self, *args, **kwargs):
        return self.client.select(*args, **kwargs)

    def upsert(self, table, *args, **kwargs):
        if table != 'news_ingestion_runs':
            raise NewsBudgetBlocked('ab_receipts_only')
        return self.client.upsert(table, *args, **kwargs)

    def _request(self, method, path, body):
        if method != 'POST':
            raise NewsBudgetBlocked('ab_budget_rpcs_only')
        if path == 'rpc/reserve_news_ai':
            authorize()
            return self.client._request(method, 'rpc/reserve_news_ab_ai', {
                **body, 'permit_key': TRIAL_ID, 'manifest_digest': self.digest, 'cell_key': self.cell})
        if path == 'rpc/settle_news_ai':
            owned = self.client.select('news_ai_requests', columns='id', filters={
                'id': 'eq.' + body['request_key'], 'ab_test_id': 'eq.' + TRIAL_ID, 'ab_cell_key': 'eq.' + self.cell})
            if len(owned) != 1:
                raise NewsBudgetBlocked('ab_settlement_not_owned')
            return self.client._request(method, 'rpc/settle_news_ab_ai', body)
        raise NewsBudgetBlocked('ab_budget_rpcs_only')


def inventory(item, extraction):
    facts = [{**f, 'id': item['id'] + ':f' + str(n), 'item_id': item['id'],
              'publisher': item['payload']['publisher']} for n, f in enumerate(extraction['facts'])]
    facts = market_qualified_facts(facts)
    return neutral_facts(facts + source_technical_facts(item, facts) + source_qualifier_facts(item))


def genre_coverage(case, extraction, facts):
    if case == 'price':
        return extraction.get('category') == 'priser' and any(re.search(
            r'\b(?:kronor|SEK|euros?|EUR)\b', f['statement'], re.I) for f in market_qualified_facts(facts))
    if case == 'statistics':
        return extraction.get('category') == 'marknad' and sum(f.get('origin') == 'literal_statistical_field' for f in facts) >= 3
    return extraction.get('category') == 'modeller'


def run_cell(remote, frozen, case, label, model, store):
    cell = case + '-' + label
    client = AbClient(remote.client, artifact_hash(frozen), cell)
    candidate = NewsAi(client, model=model, cache_enabled=False)
    reviewer = NewsAi(client, model=REVIEW_MODEL, cache_enabled=False)
    item = copy.deepcopy(frozen['items']['acea' if case == 'statistics' else 'vw-sweden-press'])
    out = {'cell': cell, 'candidate_model': model, 'review_model': REVIEW_MODEL,
           'source_hash': item['payload']['content_hash'], 'source_url': item['url'], 'normal_passed': False}
    start = time.monotonic()
    def assigned(name, schema, prompt):
        return candidate(name, schema, 'EDITORIAL ASSIGNMENT (not source evidence):\n' + ASSIGNMENTS[case] + '\n' + prompt)
    try:
        extraction = extract_facts(item, frozen['model_keys'], assigned)
        accepted, rejected, errors = partition_fact_extraction(extraction, item)
        out.update(extraction=accepted, rejected_facts=rejected, extraction_errors=errors)
        # A low relevance score may be diagnosed privately; malformed factual inputs may not be promoted.
        structural = [e for e in errors if e != 'insufficient_swedish_relevance']
        if structural:
            out.update(stopped='invalid_extracted_facts')
            return out
        facts = inventory(item, accepted)
        if len(facts) < 3:
            out.update(stopped='insufficient_qualified_facts')
            return out
        draft = generate_article(facts, candidate)
        draft.update(category=accepted['category'], editorial_recipe=RECIPE, sources=[{
            'item_id': item['id'], 'url': item['url'], 'publisher': item['payload']['publisher'],
            'title': item['payload']['title'], 'published_at': item['payload']['published_at'], 'kind': 'primary'}])
        before = artifact_hash(draft)
        score = relevance_score(accepted, item['payload']['reliability'], item['payload']['published_at'],
                                now=datetime.fromisoformat(frozen['at']))
        precheck = article_preflight(draft, facts, [item], score)
        audit = audit_article(draft, facts, reviewer)
        if artifact_hash(draft) != before:
            raise ValueError('ab_reviewer_mutated_artifact')
        diagnostic = bool(errors or precheck['errors'])
        checks = validate_article(draft, facts, [item], None if diagnostic else audit, score)
        diagnostic_checks = validate_article(draft, facts, [item], audit, score)
        article = store.put('news_articles', {'id': stable_id(TRIAL_ID + ':' + cell), 'cluster_id': cell,
            'slug': 'private-ab-' + cell, 'status': 'quarantined', 'published_at': None, 'payload': draft})
        covered = genre_coverage(case, accepted, facts)
        out.update(article=article, fact_inventory=facts, relevance_score=score, word_count=precheck['word_count'],
            precheck=precheck, audit=audit, diagnostic_only=diagnostic, gate_errors=checks,
            diagnostic_gate_errors=diagnostic_checks, genre_covered=covered,
            normal_passed=not errors and not any(checks.values()) and covered)
    except NewsBudgetBlocked as exc:
        exc.partial_cell = out
        raise
    except Exception as exc:
        out['error'] = type(exc).__name__ + ':' + str(exc)[:240]
    finally:
        out.update(elapsed_seconds=round(time.monotonic()-start, 2), candidate_usage=candidate.stats, review_usage=reviewer.stats)
    return out


def run(remote, collector=None):
    authorize()
    frozen = manifest()
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    marker = remote.get('news_ingestion_runs', TRIAL_ID)
    if (not marker or report['state'] != 'prepared' or marker['payload'].get('state') != 'prepared'
            or report['manifest_hash'] != artifact_hash(frozen) or marker['payload']['manifest_hash'] != report['manifest_hash']):
        raise NewsBudgetBlocked('ab_requires_unused_matching_preparation')
    paused(remote)
    permits = remote.client.select('news_ab_test_permits', filters={'id': 'eq.' + TRIAL_ID})
    if len(permits) != 1 or permits[0]['closed_at'] or permits[0]['manifest_hash'] != report['manifest_hash']:
        raise NewsBudgetBlocked('ab_owner_permit_missing_or_closed')
    if surfaces(remote) != report['baseline_surfaces']:
        raise NewsBudgetBlocked('ab_production_changed_before_start')
    collector = collector or Collector(tls_context=verified_context())
    report.update(state='running', started_at=now_iso())
    receipt(remote, report)
    try:
        with closing(PrivateMatrixStore(DATABASE)) as store:
            for case in ASSIGNMENTS:
                original = frozen['items']['acea' if case == 'statistics' else 'vw-sweden-press']
                fresh, _ = hydrate_item(store, original, frozen['sources'], collector)
                if fresh['payload']['content_hash'] != original['payload']['content_hash']:
                    raise NewsBudgetBlocked('ab_source_changed_during_trial')
                for label, model in MODELS:
                    if artifact_hash(manifest()) != report['manifest_hash']:
                        raise NewsBudgetBlocked('ab_manifest_changed_during_trial')
                    try:
                        result = run_cell(remote, frozen, case, label, model, store)
                        report['cells'].append(result)
                    except NewsBudgetBlocked as exc:
                        report['cells'].append({**getattr(exc, 'partial_cell', {}), 'cell': case+'-'+label,
                            'normal_passed': False, 'stopped': str(exc), 'incomplete': True})
                        raise
                    receipt(remote, report)
            if store.public_articles():
                raise ValueError('ab_local_publication_forbidden')
    except Exception as exc:
        report['error'] = type(exc).__name__ + ':' + str(exc)[:240]
    finally:
        closed = remote.client._request('POST','rpc/close_news_ab_test',{'permit_key': TRIAL_ID})
        after = usage(remote.client)
        report['usage'] = [r for r in after if r.get('ab_test_id') == TRIAL_ID]
        unexpected = [r['id'] for r in after if r['id'] not in report['baseline_ids'] and r.get('ab_test_id') != TRIAL_ID]
        report.update(state='completed', finished_at=now_iso(), permit_closed=closed.get('closed') is True,
            charged_or_reserved_micro_usd=sum(r['charged_micro_usd'] for r in report['usage']),
            all_usage_settled=all(r['settled_at'] and r['provider_status']=='completed' for r in report['usage']),
            unexpected_requests=unexpected, production_unchanged=surfaces(remote)==report['baseline_surfaces'],
            complete=len(report['cells'])==6 and not any(c.get('incomplete') for c in report['cells']) and not report.get('error'))
        report['accounting_healthy'] = (report['all_usage_settled'] and len(report['usage']) <= 18
            and report['charged_or_reserved_micro_usd'] <= CAP and not unexpected)
        paused(remote)
        report['shutdown_verified'] = True
        receipt(remote, report)
    return summary(report)


def summary(report):
    return {k: v for k, v in report.items() if k not in {'baseline_ids','baseline_surfaces','cells'}} | {
        'cells': [{k: c[k] for k in ('cell','candidate_model','word_count','normal_passed','diagnostic_only','genre_covered','error','stopped','elapsed_seconds') if k in c}
                  for c in report['cells']]}


if __name__ == '__main__':
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['budget','prepare','run'])
    args = parser.parse_args()
    with closing(NewsStore(backend='supabase')) as remote:
        result = budget(remote) if args.mode=='budget' else prepare(remote) if args.mode=='prepare' else run(remote)
        print(json.dumps(result, ensure_ascii=True, indent=2))
