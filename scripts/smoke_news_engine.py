"""Isolated live collection/editorial test. Never exports to public assets."""
import argparse
import json
import ssl
import subprocess
from pathlib import Path

from news_engine import collect, editorial, process_items, registry
from news_http import Collector
from news_store import NewsStore
from news_smoke_budget import TestAllowance
from refresh_verified_variants import save

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'data/local/news-smoke-2026-10-21.sqlite'
LEDGER = ROOT / 'data/local/news-smoke-ai-allowance.sqlite'
REPORT = ROOT / 'data/local/release-data/news-smoke/result.json'


def verified_context():
    context = ssl.create_default_context()
    # Supplement Python's Windows CA store with Node's maintained Mozilla roots.
    roots = json.loads(subprocess.check_output(
        ['node', '-p', 'JSON.stringify(require("node:tls").getCACertificates("bundled"))'], text=True))
    context.load_verify_locations(cadata='\n'.join(roots))
    return context


def run(live=False, pressrooms=False, retry_editorial=False):
    if retry_editorial and not (live and pressrooms):
        raise ValueError('editorial_retry_requires_isolated_live_pressroom_test')
    db = ROOT / 'data/local/news-pressroom-smoke-2026-10-21.sqlite' if pressrooms else DB
    report_path = REPORT.with_name('pressroom-result.json') if pressrooms else REPORT
    store = NewsStore(db)
    allowance = None
    try:
        sources, collector = registry(), Collector()
        if pressrooms:
            sources = [{**s, 'enabled': True} for s in sources
                       if s.get('kind') == 'primary' and s.get('collection_method') == 'pressroom_index']
            collector = Collector(tls_context=verified_context())
        collection = collect(store, sources, max_items=12, collector=collector, force=True)
        initial_count = len(store.rows('news_items'))
        repeat = collect(store, sources, max_items=12, collector=collector, force=True)
        report = {'database': str(db), 'public_writes': False, 'scheduler_enabled': False,
                  'collection': collection, 'repeat_new_items': repeat['new_items'],
                  'collected_before_repeat': initial_count, 'collected_after_repeat': len(store.rows('news_items'))}
        if live:
            call_limit = 20 if pressrooms else 6
            allowance = TestAllowance(LEDGER, max_calls=call_limit,
                                      response_dir=REPORT.parent / 'private-ai-responses', max_output=1500 if pressrooms else 4000)
            if retry_editorial:
                editorial(store, max_stories=1, ai=allowance, retry=True)
            for _ in range(24):
                if allowance.summary()['requests'] >= call_limit or any(a['status'] == 'published' for a in store.rows('news_articles')):
                    break
                result = process_items(store, sources, max_items=1, ai=allowance, collector=collector)
                editorial(store, max_stories=1, ai=allowance)
                state = allowance.summary()
                if not result or state['requests'] >= call_limit or any(a['status'] == 'published' for a in store.rows('news_articles')):
                    break
            report['allowance'] = allowance.summary()
        report['items'] = [{'source_id': row['source_id'], 'status': row['status'],
                            'reasons': row['payload'].get('quarantine_reasons', [])} for row in store.rows('news_items')]
        report['articles'] = [{'id': row['id'], 'status': row['status'], 'title': row['payload']['title']}
                              for row in store.rows('news_articles')]
        report['clusters'] = [{'event_key': row['event_key'], 'editorial_state': row['payload'].get('editorial_state'),
                              'reasons': row['payload'].get('quarantine_reasons', [])}
                             for row in store.rows('news_story_clusters')]
        report['quality_checks'] = [{'kind': row['kind'], 'passed': row['passed'],
                                     'errors': row['payload'].get('errors', [])} for row in store.rows('news_quality_checks')]
        save(report_path, report)
        print(json.dumps(report, ensure_ascii=True, indent=2))
    finally:
        if allowance:
            allowance.close()
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-ai', action='store_true', help='Use the owner-approved one-off USD 0.10 test allowance.')
    parser.add_argument('--pressrooms', action='store_true', help='Isolated official-source follow-up; same cumulative USD 0.10 ledger.')
    parser.add_argument('--retry-editorial', action='store_true', help='Retry the isolated quarantined draft; never bypass validation.')
    args = parser.parse_args()
    run(args.live_ai, args.pressrooms, args.retry_editorial)
