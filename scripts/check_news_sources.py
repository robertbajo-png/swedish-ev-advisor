"""Free, isolated official-pressroom check. No AI, public export or Supabase writes."""
import argparse
import json
from pathlib import Path

from news_engine import collect, hydrate_item, registry
from news_http import Collector, require_recent_publication
from news_store import NewsStore, now_iso
from refresh_verified_variants import save
from smoke_news_engine import verified_context

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / 'data/local/news-source-readiness.sqlite'
REPORT = ROOT / 'data/local/release-data/news-source-readiness/result.json'


def check_sources(store, sources, collector, max_items=3):
    if store.backend != 'sqlite':
        raise ValueError('source_check_requires_isolated_sqlite')
    if type(max_items) is not int or not 1 <= max_items <= 5:
        raise ValueError('source_check_limit_must_be_1_to_5')
    sources = [{**source, 'enabled': True} for source in sources
               if source['kind'] == 'primary' and source.get('collection_method') == 'pressroom_index']
    if len(sources) > 6:
        raise ValueError('source_check_source_limit_exceeded')
    started = now_iso()
    collection = collect(store, sources, collector=collector, max_items=max_items, force=True)
    collection_status = {row['source_id']: row['status'] for row in collection['sources']}
    source_map = {source['id']: source for source in sources}
    candidates, excluded = [], []
    for item in store.rows('news_items'):
        if item['source_id'] not in source_map:
            continue
        try:
            require_recent_publication(item['payload'].get('published_at'))
            candidates.append(item)
        except ValueError as exc:
            excluded.append({'item_id': item['id'], 'reason': str(exc)})
    assessments = []
    for source in sources:
        queue = sorted([item for item in candidates if item['source_id'] == source['id']],
                       key=lambda item: item['payload']['published_at'], reverse=True)
        if not queue:
            healthy = collection_status.get(source['id']) in {'verified', 'verified_no_recent_items', 'not_modified'}
            assessments.append({'source_id': source['id'], 'status': 'no_recent_candidates' if healthy else 'source_unavailable'})
        for item in queue[:max_items]:
            try:
                hydrated, _ = hydrate_item(store, item, source_map, collector)
                payload = hydrated['payload']
                assessments.append({'source_id': source['id'], 'item_id': hydrated['id'],
                    'status': 'accessible', 'url': hydrated['url'], 'title': payload['title'],
                    'published_at': payload['published_at'], 'content_hash': payload['content_hash'],
                    'body_words': len(payload['content'].split()), 'facts_verified': False})
            except Exception as exc:
                assessments.append({'source_id': source['id'], 'item_id': item['id'], 'status': 'blocked',
                                    'reason': type(exc).__name__ + ':' + str(exc)[:180]})
    collection_ok = bool(collection['sources']) and all(row['status'] in {
        'verified', 'verified_no_recent_items', 'not_modified'} for row in collection['sources'])
    return {'started_at': started, 'finished_at': now_iso(), 'backend': 'sqlite', 'collection_ok': collection_ok,
            'collection': collection, 'assessments': assessments, 'excluded_cached_items': excluded,
            'accessible_sources': len({row['source_id'] for row in assessments if row['status'] == 'accessible'}),
            'ai_calls': 0, 'public_writes': False, 'publication_approved': False,
            'scope': 'source_content_readiness_only_not_editorial_verification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-items', type=int, default=3, help='At most 1-5 candidates per official source')
    args = parser.parse_args()
    store = NewsStore(DATABASE)
    try:
        report = check_sources(store, registry(), Collector(tls_context=verified_context()), args.max_items)
        save(REPORT, report)
        print(json.dumps({**report, 'private_report': str(REPORT)}, ensure_ascii=True, indent=2))
        return report['collection_ok'] and not any(row['status'] == 'blocked' for row in report['assessments'])
    finally:
        store.close()


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
