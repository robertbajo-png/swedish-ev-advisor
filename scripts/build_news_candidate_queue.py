"""Free private planning from collected official sources. Never calls AI or publishes."""
import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from news_editorial import normalize
from news_http import canonical_url, iso_date, require_recent_publication
from news_notice_pipeline import prepare_notice
from news_bmw_charging import prepare_bmw_charging, ChargingRejected
from news_short_articles import SOURCES, make_brief
from news_notice_preflight import all_rows
from refresh_verified_variants import save
from supabase_client import SupabaseRestClient

ROOT = Path(__file__).resolve().parents[1]
VW_HOSTS = {'www.vwgroup.se', 'www.volkswagen-newsroom.com'}


def launch_signature(title, url, published_at):
    """A possible same-event match, not permission to merge or publish either item."""
    if urlsplit(url).hostname not in VW_HOSTS:
        return None
    text = normalize(title)
    if not re.search(r'bestall|forsalj|ordered|pre.?sale|pre.?order', text):
        return None
    model = re.search(r'\bid\s+(cross|polo|[0-9](?:\s+tourer)?)\b', text)
    battery = re.findall(r'\b(\d+(?:[.,]\d+)?)\s*kwh\b', str(title), re.I)
    date = iso_date(published_at)
    if not model or len(set(battery)) != 1 or not date:
        return None
    capacity = Decimal(battery[0].replace(',', '.')).normalize()
    if not 10 <= capacity <= 200:
        return None
    return ('volkswagen', model[1], str(capacity), date[:10])


def published_references(articles):
    urls, signatures = {}, {}
    for row in articles:
        if row.get('status', 'published') != 'published' or not row.get('published_at'):
            continue
        p = row.get('payload', row)
        for ref in p.get('sources', []):
            try:
                url = canonical_url(ref['url'])
            except (KeyError, TypeError, ValueError):
                continue
            urls[url] = row['id']
            signature = launch_signature(ref.get('title', ''), url, ref.get('published_at'))
            if signature:
                signatures[signature] = row['id']
    return urls, signatures


def provenance_errors(item, source, now):
    p = item.get('payload', {})
    errors = []
    if (not source or source.get('kind') != 'primary' or source.get('id') != item.get('source_id')
            or p.get('source_kind') != 'primary' or p.get('publisher') != source.get('name')):
        return ['official_source_identity_missing']
    try:
        url, final = canonical_url(item['url']), canonical_url(p['final_url'])
        if url != final or urlsplit(url).hostname != urlsplit(canonical_url(source['website'])).hostname:
            errors.append('source_url_or_domain_changed')
        require_recent_publication(p.get('published_at'), now)
        fetched = datetime.fromisoformat(iso_date(p.get('fetched_at')) or '')
        if not -timedelta(minutes=5) <= now-fetched <= timedelta(days=1):
            errors.append('stale_or_future_fetch')
    except (KeyError, TypeError, ValueError) as exc:
        errors.append('invalid_source_metadata:' + str(exc)[:100])
    content = p.get('content')
    if (p.get('access_status') != 'accessible' or not isinstance(content, str) or not content
            or hashlib.sha256(content.encode()).hexdigest() != p.get('content_hash')):
        errors.append('source_not_accessible_or_hash_mismatch')
    return sorted(set(errors))


def build_queue(items, sources, published, now=None):
    now = now or datetime.now(timezone.utc)
    source_map = {s['id']: s for s in sources}
    urls, signatures = published_references(published)
    result = []
    for item in sorted(items, key=lambda i: (i['payload'].get('published_at') or '', i['id']), reverse=True):
        p = item['payload']
        entry = {'item_id': item['id'], 'source_id': item['source_id'], 'url': item['url'],
                 'title': p.get('title'), 'published_at': p.get('published_at'), 'formats': []}
        try:
            published_id = urls.get(canonical_url(item['url']))
        except ValueError:
            published_id = None
        if published_id:
            result.append({**entry, 'status': 'already_published', 'published_article_id': published_id})
            continue
        source = source_map.get(item['source_id'])
        errors = provenance_errors(item, source, now)
        if errors:
            result.append({**entry, 'status': 'quarantined', 'reasons': errors})
            continue
        entry['source_hash'] = p['content_hash']
        title = normalize(p.get('title', ''))
        hybrid = re.search(r'laddhybrid|plug.?in.?hybrid|\bphev\b', title)
        electric = re.search(r'\bbev\b|battery.?electric|batterielektr|\belbil', title)
        if hybrid:
            result.append({**entry, 'status': 'needs_topic_review' if electric else 'excluded_powertrain',
                           'reasons': ['mixed_powertrain_headline' if electric else 'plug_in_hybrid_not_bev_news']})
            continue
        signature = launch_signature(p.get('title', ''), item['url'], p.get('published_at'))
        if signature and signature in signatures:
            result.append({**entry, 'status': 'possible_duplicate', 'published_article_id': signatures[signature],
                           'reasons': ['same_official_model_battery_order_announcement_date']})
            continue
        adapter_errors = []
        if item['source_id'] == 'bmw-press':
            try:
                packet, article, review = prepare_bmw_charging(item, source, now)
                if review['passed']:
                    entry['formats'].append({'format': 'charging_preview', 'facts': packet, 'article': article,
                        'review': review, 'requires_separate_release_decision': True,
                        'ai_audit_performed': False, 'publication_supported': False})
                else:
                    result.append({**entry, 'status': 'quarantined', 'reasons': review['errors']})
                    continue
            except ChargingRejected as exc:
                result.append({**entry, 'status': 'quarantined', 'reasons': [str(exc)[:180]]})
                continue
            except (KeyError, TypeError, ValueError) as exc:
                adapter_errors.append(str(exc)[:160])
        if item['source_id'] in {'vw-sweden-press', 'acea'}:
            kind = 'statistics' if item['source_id'] == 'acea' else 'price'
            try:
                article, review = prepare_notice(item, source, kind=kind, now=now)
                if review['passed']:
                    entry['formats'].append({'format': kind + '_notice', 'article': article, 'review': review,
                        'requires_separate_release_decision': True, 'ai_audit_performed': False})
                else:
                    adapter_errors.extend(e for group in review['checks'].values() for e in group)
            except (KeyError, TypeError, ValueError) as exc:
                adapter_errors.append(str(exc)[:160])
        if item['source_id'] in SOURCES:
            kind = 'battery' if item['source_id'] == 'firefly-china-press' else 'model'
            try:
                entry['formats'].append({'format': 'ai_' + kind, 'brief': make_brief(item, kind, now),
                                        'paid_calls': 0, 'independent_review_performed': False})
            except (KeyError, TypeError, ValueError) as exc:
                adapter_errors.append(str(exc)[:160])
        status = 'private_candidate' if entry['formats'] else 'needs_adapter'
        result.append({**entry, 'status': status, 'adapter_errors': adapter_errors})
    return {'at': now.isoformat(), 'scope': 'private_preparation_not_publication_approval', 'items': result,
            'counts': {s: sum(e['status'] == s for e in result) for s in sorted({e['status'] for e in result})},
            'paid_calls': 0, 'cost_usd': 0, 'published': 0, 'production_writes': 0, 'release_authorized': False}


def read_cache(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        def rows(table):
            return [{**dict(row), 'payload': json.loads(row['payload'])} for row in db.execute('select * from ' + table)]
        return rows('news_items'), [r['payload'] for r in rows('news_sources')]


class ReadOnlyClient(SupabaseRestClient):
    def _request(self, method, *args, **kwargs):
        if method != 'GET':
            raise ValueError('candidate_queue_allows_only_remote_reads')
        return super()._request(method, *args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'data/local/news-source-readiness.sqlite')
    parser.add_argument('--remote', action='store_true', help='Read current published records; never write production')
    args = parser.parse_args()
    items, sources = read_cache(args.db)
    published = (all_rows(ReadOnlyClient(), 'public_news_articles') if args.remote else
                 json.loads((ROOT / 'public/data/news_articles.json').read_text(encoding='utf-8'))['records'])
    report = build_queue(items, sources, published)
    path = ROOT / 'data/local/release-data/news-source-readiness/candidate-queue.json'
    save(path, report)
    print(json.dumps({k: v for k, v in report.items() if k != 'items'} | {'report': str(path)}, indent=2))


if __name__ == '__main__':
    main()
