"""Capture and replay the exact October Mobility Sweden BEV market row."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from urllib.parse import urljoin

from audit_catalog_sources import SourceFetcher
from import_mobility_sweden import parse_elbil_ranking
from porsche_macan_review import PRIVATE, sha
from variant_refresh import one, parse_document

ARTICLE = ('https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/'
           'tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober')
WORKBOOK = ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
            'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
            'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx')
WORKBOOK_SHA = '1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6'
MONTH = '2026-10-01'
RAW = ('PORSCHE', 'MACAN', 'EL')
FILES = {'article.html': ARTICLE, 'market.xlsx': WORKBOOK}


def exact_row(rows, stats):
    key = lambda r: (r.brand_raw, r.model_raw, r.fuel_type_raw)
    row = one((r for r in rows if key(r) == RAW), 'one_exact_macan_bev_model_required')
    monthly = one((r for r in stats if key(r) == RAW), 'one_exact_macan_bev_month_required')
    if (row.normalized_brand, row.normalized_model, row.model_group, row.needs_mapping,
            row.last_seen_month, row.registrations_last_month, row.registrations_ytd) != (
                'porsche', 'macan', None, False, MONTH, 43, 367):
        raise ValueError('macan_october_market_identity_changed')
    if (monthly.market_model_key, monthly.month, monthly.registrations) != ('porsche:macan:EL', MONTH, 43):
        raise ValueError('macan_october_monthly_stat_changed')
    fields = ('brand_raw', 'model_raw', 'fuel_type_raw', 'normalized_brand', 'normalized_model',
              'last_seen_month', 'registrations_last_month', 'registrations_ytd', 'needs_mapping')
    return {**{field: getattr(row, field) for field in fields},
            'source_url': WORKBOOK, 'source_name': 'Mobility Sweden'}


def review(article, workbook):
    doc = parse_document(article, 'text/html')
    links = {urljoin(ARTICLE, n.attrs.get('href', '')) for n in doc.nodes('a')}
    if WORKBOOK not in links or sha(workbook.read_bytes()) != WORKBOOK_SHA:
        raise ValueError('require_the_linked_exact_october_workbook')
    models, stats = parse_elbil_ranking(workbook, WORKBOOK)
    return {
        'status': 'macan_market_evidence_verified_private', 'sheet': 'Elbil ranking',
        'row': exact_row(models, stats), 'publication_approved': False, 'database_writes': 0,
    }


def capture():
    if PRIVATE.resolve() != PRIVATE or any('onedrive' in part.lower() for part in PRIVATE.parts):
        raise ValueError('require_private_unlinked_evidence_directory')
    fetcher = SourceFetcher(timeout=15, max_bytes=6_000_000, document_parser=lambda body, *_: body,
                            text_parser=lambda *_: '', url_policy=lambda url, brands:
                            url in FILES.values() and brands == {'Mobility Sweden'})
    bodies, receipts = {}, {}
    for name, url in FILES.items():
        res = fetcher.fetch(url, {'Mobility Sweden'})
        if (res['status'], res.get('http_status'), res.get('final_url')) != ('reachable', 200, url):
            raise ValueError('macan_market_source_unavailable:' + res['status'])
        bodies[name] = res['document']
        receipts[name] = {'final_url': url, 'http_status': 200, 'status': 'reachable',
                          'fetched_at': datetime.now(timezone.utc).isoformat(), 'content_hash': sha(bodies[name])}
    PRIVATE.mkdir(parents=True, exist_ok=True)
    folder = Path(mkdtemp(prefix='porsche-macan-market-', dir=PRIVATE))
    for name, data in bodies.items():
        (folder / name).write_bytes(data)
    report = {**review(bodies['article.html'], folder / 'market.xlsx'), 'sources': receipts}
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    return folder, report


def replay(folder):
    folder = folder.resolve(strict=True)
    if folder.parent != PRIVATE or not folder.name.startswith('porsche-macan-market-'):
        raise ValueError('require_private_macan_market_packet')
    report = json.loads((folder / 'report.json').read_text(encoding='utf8'))
    receipts = report['sources']
    if set(receipts) != set(FILES):
        raise ValueError('unexpected_macan_market_scope')
    bodies = {name: (folder / name).read_bytes() for name in FILES}
    for name, url in FILES.items():
        r = receipts[name]
        if (r.get('final_url'), r.get('http_status'), r.get('status'), r.get('content_hash')) != (
                url, 200, 'reachable', sha(bodies[name])):
            raise ValueError('macan_market_bytes_or_source_changed')
    if report != {**review(bodies['article.html'], folder / 'market.xlsx'), 'sources': receipts}:
        raise ValueError('macan_market_replay_changed')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    args = parser.parse_args()
    folder, report = capture() if args.capture else (args.replay, replay(args.replay))
    print(json.dumps({**report, 'folder': str(folder)}))
