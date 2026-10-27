"""Capture accepted manufacturer evidence privately. Reachability never publishes facts."""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from audit_catalog_sources import ROOT, SourceFetcher

OUT = ROOT / 'data/local/release-data/catalog-replacement-2026-10-27'
EXTRA = {
    'Kia': ['https://www.kia.com/se/kopa/prislista/'],
    'Toyota': ['https://www.toyota.se/bilar/bz4x/specifications'],
    'Renault': ['https://www.renault.se/personbilar/elbilar/r5-e-tech-electric/versioner-och-priser'],
    'Skoda': ['https://www.skoda.se/modeller/elroq/elroq', 'https://www.skoda.se/kopa/prislistor'],
}


def capture(url, brands, output=OUT, url_policy=None):
    captured = []
    fetcher = SourceFetcher(timeout=15, document_parser=lambda body, kind: captured.append(body), url_policy=url_policy)
    result = fetcher.fetch(url, set(brands))
    result.pop('document', None)
    result.update(requested_url=url, brands=sorted(brands), fetched_at=datetime.now(timezone.utc).isoformat())
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    output.mkdir(parents=True, exist_ok=True)
    if result['status'] == 'reachable':
        assert len(captured) == 1
        assert hashlib.sha256(captured[0]).hexdigest() == result['content_hash']
        extension = '.pdf' if 'pdf' in result['content_type'] else '.html'
        result['body_file'] = key + extension
        (output / result['body_file']).write_bytes(captured[0])
        (output / (key + '.txt')).write_text(result['text'], encoding='utf-8')
    (output / (key + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--brand')
    parser.add_argument('--url')
    args = parser.parse_args()
    if args.url and not args.brand:
        parser.error('--url requires --brand')
    catalog = json.loads((ROOT / 'public/data/public_ev_variants.json').read_text(encoding='utf-8'))
    sources = {}
    for row in catalog['records']:
        if not args.brand or args.brand == row['brand']:
            sources.setdefault(row['source_url'], set()).add(row['brand'])
    for brand, urls in EXTRA.items():
        if not args.brand or args.brand == brand:
            for url in urls:
                sources.setdefault(url, set()).add(brand)
    if args.url:
        sources = {args.url: {args.brand}}
    report = []
    for index, (url, brands) in enumerate(sources.items()):
        result = capture(url, brands)
        row = {key: result.get(key) for key in ('requested_url', 'brands', 'status', 'http_status', 'final_url', 'content_hash', 'body_file')}
        report.append(row)
        print(json.dumps(row, ensure_ascii=True), flush=True)
        if (index + 1) % 5 == 0:
            time.sleep(0.5)
    suffix = args.brand or 'all'
    (OUT / ('collection-' + suffix + '.json')).write_text(json.dumps({'sources': report, 'database_writes': 0, 'paid_calls': 0}, indent=2) + '\n')


if __name__ == '__main__':
    main()
