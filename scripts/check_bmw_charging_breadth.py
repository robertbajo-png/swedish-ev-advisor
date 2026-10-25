"""Free, private BMW source-format breadth check; no AI, database or publisher."""
import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from news_bmw_charging import (HOST, ChargingNotSupported, ChargingRejected,
                               charging_layout, prepare_bmw_charging, validate_source)
from news_http import Collector, canonical_url, require_recent_publication
from news_pressrooms import document
from smoke_news_engine import verified_context

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'data/news/bmw_charging_breadth_cases.json'
PRIVATE_ROOT = ROOT / 'data/local/release-data'
LAYOUTS = {'high_power_demonstration', 'china_cltc_vehicle_specs', 'v2g_offer',
           'ac_option_update', 'provisional_vehicle_charging', 'charging_network',
           'vehicle_charging_specs', 'other_bmw_release'}


def validate_cases(cases):
    if not isinstance(cases, list) or not 1 <= len(cases) <= 6:
        raise ValueError('bmw_breadth_requires_1_to_6_cases')
    ids, articles = set(), set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError('bmw_breadth_invalid_case')
        url = case.get('url', '')
        parsed = urlsplit(url)
        match = re.fullmatch(r'/global/article/detail/(T\d+EN)/[^/]+', parsed.path)
        if (canonical_url(url) != url or parsed.hostname != HOST or parsed.query
                or parsed.fragment or not match):
            raise ValueError('bmw_breadth_official_global_url_required')
        name = case.get('id', '')
        if (not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,70}', name)
                or case.get('expected_layout') not in LAYOUTS):
            raise ValueError('bmw_breadth_invalid_case')
        if name in ids or match[1] in articles:
            raise ValueError('bmw_breadth_duplicate_case_or_article')
        ids.add(name)
        articles.add(match[1])


def assess(item, source, now):
    """Keep original timestamps. Historical inputs remain holds, not new news."""
    p = item.get('payload', {})
    layout = charging_layout(p.get('title', ''), p.get('content', ''))
    base = {'layout_hint': layout, 'publication_supported': False,
            'published_at': p.get('published_at'), 'fetched_at': p.get('fetched_at'),
            'content_hash': p.get('content_hash')}
    try:
        validate_source(item, source, now)
        packet, article, review = prepare_bmw_charging(item, source, now)
        if not review['passed']:
            return {**base, 'status': 'quarantined', 'reasons': review['errors']}
        return {**base, 'status': 'private_preview', 'packet': packet,
                'article': article, 'review': review}
    except ChargingNotSupported as exc:
        return {**base, 'status': 'needs_adapter', 'reasons': [str(exc)]}
    except ChargingRejected as exc:
        # Only a valid historical publication date earns a stale classification.
        # Other malformed metadata must not be mistaken for an ordinary age hold.
        reason = str(exc)
        stale = reason == 'bmw_charging_invalid_source_metadata:stale_report'
        return {**base, 'status': 'held_stale' if stale else 'quarantined', 'reasons': [reason]}


def run_cases(cases, source, collector, clock=None):
    validate_cases(cases)
    if (source.get('id') != 'bmw-press' or source.get('name') != 'BMW Group PressClub'
            or source.get('website') != 'https://' + HOST or source.get('kind') != 'primary'):
        raise ValueError('bmw_breadth_official_registry_source_required')
    clock = clock or (lambda: datetime.now(timezone.utc))
    results = []
    for case in cases:
        row = {**case, 'publication_supported': False}
        try:
            status, _, html, final = collector.fetch(case['url'], source, editorial=True)
            fetched = clock()
            if status != 200 or final != case['url']:
                raise ValueError('bmw_breadth_http_status_or_redirect_changed')
            doc = document(html)
            if not doc['title'] or not doc['body'] or not doc['published_at']:
                raise ValueError('bmw_breadth_missing_title_body_or_publication_date')
            # Validate the original date, but permit old sources in the private
            # corpus. The real adapter below must still reject them as news.
            try:
                require_recent_publication(doc['published_at'], fetched)
            except ValueError as exc:
                if str(exc) != 'stale_report':
                    raise
            item = {'id': 'bmw-breadth-' + case['id'], 'source_id': source['id'],
                'url': case['url'], 'status': 'private_source_capture',
                'payload': {'title': doc['title'], 'content': doc['body'],
                    'content_hash': hashlib.sha256(doc['body'].encode()).hexdigest(),
                    'publisher': source['name'], 'source_kind': source['kind'],
                    'published_at': doc['published_at'], 'fetched_at': fetched.isoformat(),
                    'access_status': 'accessible', 'final_url': final}}
            result = assess(item, source, fetched)
            row.update(result, item=item, html_hash=hashlib.sha256(html.encode()).hexdigest(),
                       layout_matches_expected=result['layout_hint'] == case['expected_layout'])
        except Exception as exc:
            # A blocked or changed source must not prevent the remaining cases.
            # Avoid echoing HTTP bodies/credentials from external error messages.
            reason = str(exc) if type(exc) is ValueError else type(exc).__name__
            row.update(status='source_unavailable', reasons=[reason[:180]])
        results.append(row)
    return {'at': clock().isoformat(), 'scope': 'private_source_format_breadth_not_release_approval',
        'cases': results, 'counts': dict(Counter(r['status'] for r in results)),
        'accessible_source_count': sum('item' in r for r in results),
        'layout_mismatches': [r['id'] for r in results if r.get('layout_matches_expected') is False],
        'paid_calls': 0, 'cost_usd': 0, 'production_writes': 0, 'published': 0,
        'publication_supported': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    output = (args.output or PRIVATE_ROOT / ('news-bmw-charging-breadth-' + now.strftime('%Y-%m-%dT%H%M%SZ'))).resolve()
    if not output.is_relative_to(PRIVATE_ROOT.resolve()) or output == PRIVATE_ROOT.resolve():
        raise ValueError('bmw_breadth_output_requires_private_release_data_subdirectory')
    # Never replace a previous trial or its original evidence.
    output.mkdir(parents=True, exist_ok=False)
    cases = json.loads(MANIFEST.read_text(encoding='utf-8'))
    sources = json.loads((ROOT / 'data/news/sources.json').read_text(encoding='utf-8'))
    source = next(s for s in sources if s['id'] == 'bmw-press')
    report = run_cases(cases, source, Collector(tls_context=verified_context()))
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'} |
                     {'private_report': str(output / 'report.json')}, indent=2))
    return report['accessible_source_count'] == len(cases) and not report['layout_mismatches']


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
