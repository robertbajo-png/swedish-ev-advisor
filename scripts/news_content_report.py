"""Read-only rolling news report; never buys, publishes or exports private prose."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

from news_rss import publication_time
from supabase_client import SupabaseRestClient, load_local_env

SOURCE_STATES = {'verified', 'not_modified', 'verified_no_recent_items', 'no_verified_feed'}
PRODUCTION_KINDS = {'short_daily'}


def safe_reason(value):
    # Do not send exception messages, URL queries, text snippets or tokens to Actions.
    if not isinstance(value, str):
        return 'unclassified'
    value = re.sub(r'^(?:ValueError|OriginalSourceNotFound|RuntimeError):', '', value)
    token = value.split(':', 1)[0]
    return token if re.fullmatch(r'[a-z][a-z0-9_]{2,79}', token) else 'unclassified'


def content_report(runs, articles, requests, sources=(), *, now=None, days=7):
    now = now or datetime.now(timezone.utc)
    if type(days) is not int or not 1 <= days <= 31:
        raise ValueError('report_days_must_be_1_to_31')
    start = now - timedelta(days=days)
    def in_window(value):
        date = publication_time(value)
        return bool(date and start <= date <= now)
    attempts, collections = [], []
    for row in runs:
        p = row.get('payload', {})
        if p.get('kind') in PRODUCTION_KINDS and in_window(p.get('started_at')):
            attempts.append(p)
        if p.get('kind') == 'collection' and in_window(p.get('at')):
            collections.append(p)
    public = [r for r in articles if r.get('status', 'published') == 'published' and in_window(r.get('published_at'))]
    charged = [r for r in requests if in_window(r.get('created_at'))]
    invalid_charges = any(type(r.get('charged_micro_usd')) is not int or r['charged_micro_usd'] < 0 for r in charged)
    unresolved = sum(not r.get('settled_at') and not r.get('budget_closed_at')
                     or r.get('provider_status') == 'accounting_anomaly' for r in requests)
    reasons = Counter(safe_reason(e) for p in attempts for e in (p.get('errors') or [p.get('error')]) if e)
    collection_reasons = Counter(safe_reason(e.get('reason')) for p in collections
                                for s in p.get('sources', []) for e in s.get('errors', []))
    source_health = []
    for row in sources:
        p = row.get('payload', {})
        source_id = row.get('id', '')
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,60}', source_id) or not p.get('enabled', p.get('priority', False)):
            continue
        status = p.get('collection_status')
        source_health.append({'source_id': source_id, 'collection_status': status if status in SOURCE_STATES else 'unknown',
                              'editorial_evidence': 'not_assessed_by_collection_report',
                              'checked_at': p.get('checked_at') if publication_time(p.get('checked_at')) else None})
    return {'from_utc': start.isoformat(), 'to_utc': now.isoformat(),
        'funnel': {'discovered': sum(max(0, p.get('new_items', 0)) for p in collections if type(p.get('new_items')) is int),
                   'production_attempts': len(attempts),
                   'writer_completed': sum(bool(p.get('writer_output')) for p in attempts),
                   'independent_review_completed': sum(p.get('review_performed') is True for p in attempts),
                   'passed': sum(p.get('state') == 'passed' for p in attempts),
                   'quarantined': sum(p.get('state') == 'quarantined' or p.get('status') == 'quarantined' for p in attempts),
                   'published': len(public)},
        'rejection_reasons': dict(reasons.most_common()), 'collection_reasons': dict(collection_reasons.most_common()),
        'cost': {'charged_micro_usd': None if invalid_charges else sum(r['charged_micro_usd'] for r in charged),
                 'provider_requests': len(charged), 'unresolved_all_time': unresolved,
                 'valid': not invalid_charges and not unresolved},
        'source_health': sorted(source_health, key=lambda r: r['source_id']),
        'traffic': {'status': 'not_connected', 'note': 'See Cloudflare Web Analytics and Search Console; no visitor figures inferred.'},
        'paid_calls': 0, 'database_writes': 0, 'publications': 0}


def remote_report(client, days=7, now=None):
    # All interfaces below issue GET only; no provider, worker or publication imports.
    limit = 1000
    def rows(table, columns):
        result = []
        for offset in range(0, 100000, limit):
            batch = client.select(table, columns=columns, filters={'limit': limit, 'offset': offset, 'order': 'id.asc'})
            result.extend(batch)
            if len(batch) < limit:
                return result
        raise ValueError('content_report_truncated')
    return content_report(rows('news_ingestion_runs', 'id,payload'),
        rows('public_news_articles', 'id,published_at'),
        rows('news_ai_requests', 'id,created_at,charged_micro_usd,settled_at,budget_closed_at,provider_status'),
        rows('news_sources', 'id,payload'), days=days, now=now)


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remote', action='store_true', required=True)
    parser.add_argument('--days', type=int, default=7, choices=range(1, 32))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = remote_report(SupabaseRestClient(), args.days)
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as handle:
            handle.write('## News content: last ' + str(args.days) + ' days\n\n```json\n' + text + '```\n')
    print(text)


if __name__ == '__main__':
    main()
