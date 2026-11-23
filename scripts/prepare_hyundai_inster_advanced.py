"""Collect the exact Swedish Advanced dossier without database access."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from urllib.parse import urljoin

from audit_catalog_sources import SourceFetcher
from hyundai_inster_advanced_seats import MATERIAL, PHOTO_SHA, SOURCES as SEAT_SOURCES, exact_factory_packages, seat_proof
from import_mobility_sweden import parse_elbil_ranking
from manufacturer_embedded_data import unique_object
from variant_refresh import one, parse_document

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'data/local/release-data'
MODEL = 'https://www.hyundai.com/se/sv/bilar/inster.html'
CONFIG = f'https://lager.hyundai.se/model/INSTER/{MATERIAL}?customer=corporate&ext=SRM&int=NNB'
DESIGN = MODEL.removesuffix('.html') + '/design.html'
STOCK = 'https://lager.hyundai.se/model/INSTER?customer=private'
MANUAL = 'https://ownersmanual.hyundai.com/full_webhelp/AXEV/2027/sv_SE/'
REGISTRY = ('https://ownersmanual.hyundai.com/api/v2/hmc/model/owners-manuals'
            '?projectCode=AXEV&year=2027&langCode=sv_SE&countryCode=C18')
TOW = MANUAL + 'idee195341dda.html'
ARTICLE = ('https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/'
           'tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober')
WORKBOOK = ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
            'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
            'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx')
WORKBOOK_SHA = '1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6'
SLIDING = 'Skjutbart baks\u00e4te i l\u00e4ngsled'
CARGO = 'baks\u00e4tena skjutas fram 16 centimeter, vilket ut\u00f6kar bagageutrymmet fr\u00e5n 238 till 351 liter'
NO_TRAILER = ('Det \u00e4r inte till\u00e5tet att dra en sl\u00e4pvagn med detta fordon. '
              'Fordonet har ingen dragkapacitet och kan inte dra en sl\u00e4pvagn.')
BIKE_CARRIER = 'Till\u00e5ten lastkapacitet f\u00f6r cykelh\u00e5llarsystem: 75 kg'
GROUPS = {url: {'Hyundai'} for url in (MODEL, CONFIG, DESIGN, STOCK, REGISTRY, TOW, *SEAT_SOURCES.values())}
GROUPS.update({url: {'Mobility Sweden'} for url in (ARTICLE, WORKBOOK)})


def sha(body):
    return hashlib.sha256(body).hexdigest()


def local_file(path, limit):
    path = path.absolute()
    if (PRIVATE not in path.parents or path.resolve(strict=True) != path
            or not path.is_file() or not 0 < path.stat().st_size <= limit):
        raise ValueError('require_unlinked_private_inster_evidence')
    return path.read_bytes()


def verify_cargo(design, config):
    equipment = parse_document(config, 'text/html')
    title = 'INSTER \u00b7 49kWh Advanced MY27'
    titles = [node.text() for node in equipment.nodes('title')]
    og = [n.attrs.get('content') for n in equipment.nodes('meta') if n.attrs.get('property') == 'og:title']
    if titles != [title + ' | Hyundai Sverige'] or og != [title] or MATERIAL.encode() not in config:
        raise ValueError('inster_exact_swedish_material_required')
    if SLIDING not in {node.text() for node in equipment.nodes('li')}:
        raise ValueError('inster_exact_sliding_seat_required')
    document = parse_document(design, 'text/html')
    if not any(len(text) <= 240 and text.endswith(CARGO + '.') for tag in ('p', 'div')
               for text in (node.text() for node in document.nodes(tag))):
        raise ValueError('inster_sliding_seat_volumes_changed')
    return {'boot_liters': 238, 'sliding_seats_up_max_liters': 351, 'minimum_is_seats_farthest_rearward': True}


def verify_towing(registry, manual):
    item = json.loads(registry, object_pairs_hook=unique_object)['omManual']
    expected = {'webhelpDocId': 'D202607010201', 'webhelpManual': MANUAL + 'index.html',
                'webhelpToc': MANUAL + 'toc.html',
                'webhelpPubdate': {'firstdate': '20260701', 'lastdate': '20261029'}}
    if any(item.get(key) != value for key, value in expected.items()):
        raise ValueError('inster_swedish_my27_manual_changed')
    topic = parse_document(manual, 'text/html')
    title = 'Bogsering av sl\u00e4p'
    if ([n.attrs.get('lang') for n in topic.nodes('html')] != ['sv-SE']
            or [n.text() for n in topic.nodes('title')] != [title]
            or [n.text() for n in topic.nodes('h2')] != [title]
            or topic.text().count(NO_TRAILER) != 1 or topic.text().count(BIKE_CARRIER) != 1):
        raise ValueError('inster_swedish_my27_explicit_prohibition_missing')
    return {'value': 0, 'source_url': TOW, 'source_hash': sha(manual), 'quote': NO_TRAILER}


def fetch_sources():
    fetcher = SourceFetcher(timeout=18, max_bytes=8_000_000, document_parser=lambda body, *_: body,
                            text_parser=lambda *_: '', url_policy=lambda url, brands: GROUPS.get(url) == brands)
    raw, receipts = {}, {}
    for url, brands in GROUPS.items():
        result = fetcher.fetch(url, brands)
        if (result['status'], result.get('http_status'), result.get('final_url')) != ('reachable', 200, url):
            raise ValueError(f'inster_source_unavailable: {url}: {result["status"]}')
        body = raw[url] = result['document']
        receipts[url] = {'final_url': url, 'content_hash': sha(body), 'fetched_at': datetime.now(timezone.utc).isoformat(),
                         'status': 'reachable', 'http_status': 200}
    return raw, receipts


def collect(seat_photo, model_photo):
    if PRIVATE.resolve(strict=True) != PRIVATE or any('onedrive' in part.lower() for part in PRIVATE.parts):
        raise ValueError('require_unlinked_private_evidence_root')
    dealer_image = local_file(seat_photo, 6_000_000)
    image = local_file(model_photo, 6_000_000)
    expected_image = json.loads((ROOT / 'src/inster-photo-policy.json').read_text(encoding='utf-8'))['content_sha256']
    if sha(dealer_image) != PHOTO_SHA or sha(image) != expected_image:
        raise ValueError('inster_reviewed_photo_changed')
    factory = json.loads(subprocess.check_output(
        ['node', 'scripts/capture_hyundai_inster_advanced_factory.mjs'], cwd=ROOT, encoding='utf-8', timeout=90))
    packet = Path(factory.pop('folder'))
    if factory.pop('replay') or packet.parent != PRIVATE or not packet.name.startswith('hyundai-inster-advanced-emissions-'):
        raise ValueError('require_fresh_inster_factory_receipts')
    raw, receipts = fetch_sources()
    cargo = verify_cargo(raw[DESIGN], raw[CONFIG])
    tow = verify_towing(raw[REGISTRY], raw[TOW])
    seats = seat_proof({k: raw[url] for k, url in SEAT_SOURCES.items()},
                       {k: {'sha256': receipts[url]['content_hash']} for k, url in SEAT_SOURCES.items()}, dealer_image)
    stock = exact_factory_packages(raw[STOCK])
    if (stock.get('ZMSRP'), stock.get('PACKAGEPRICE'), stock.get('COLOR')) != ('377900', '23000', '7500'):
        raise ValueError('inster_configured_price_or_paint_changed')
    links = {urljoin(ARTICLE, n.attrs.get('href', '')) for n in parse_document(raw[ARTICLE], 'text/html').nodes('a')}
    if WORKBOOK not in links or sha(raw[WORKBOOK]) != WORKBOOK_SHA:
        raise ValueError('inster_exact_october_workbook_changed')
    folder = Path(mkdtemp(prefix='inster-advanced-intake-', dir=PRIVATE))
    workbook = folder / 'market.xlsx'
    workbook.write_bytes(raw[WORKBOOK])
    market_rows, months = parse_elbil_ranking(workbook, WORKBOOK)
    market = one((r for r in market_rows if (r.brand_raw, r.model_raw, r.fuel_type_raw) == ('HYUNDAI', 'INSTER', 'EL')),
                 'require_exact_separate_inster_market_row')
    if (market.last_seen_month, market.registrations_last_month, market.registrations_ytd, market.needs_mapping) != (
            '2026-10-01', 2, 118, False):
        raise ValueError('inster_market_evidence_changed')
    if not any((r.brand_raw, r.model_raw, r.fuel_type_raw, r.month, r.registrations) ==
               ('HYUNDAI', 'INSTER', 'EL', '2026-10-01', 2) for r in months):
        raise ValueError('inster_monthly_stat_missing')
    for index, (url, body) in enumerate(raw.items()):
        name = workbook.name if url == WORKBOOK else f'source-{index}.body'
        if url != WORKBOOK:
            (folder / name).write_bytes(body)
        receipts[url]['raw_file'] = name
    for operation in ('Trims', 'EmissionQuery', 'Powertrains'):
        for kind in ('request', 'response'):
            name = f'{operation}-{kind}.json'
            (folder / name).write_bytes(local_file(packet / name, 1_000_000))
    model_image = folder / 'inster-prime-original.jpg'
    model_image.write_bytes(image)
    report = {'status': 'inster_advanced_exact_intake_private', 'factory': factory, 'cargo': cargo,
              'seats': seats, 'tow': tow, 'variant_price': int(stock['ZMSRP']), 'market': vars(market),
              'sources': receipts, 'image_file': str(model_image), 'image_sha256': expected_image,
              'publication_approved': False, 'production_writes': 0}
    (folder / 'intake.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'folder': str(folder), 'status': report['status'], 'publication_approved': False,
                      'production_writes': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seat-photo', type=Path, required=True)
    parser.add_argument('--model-photo', type=Path, required=True)
    args = parser.parse_args()
    collect(args.seat_photo, args.model_photo)
