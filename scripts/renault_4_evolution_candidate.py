"""Capture and replay one exact Swedish Renault 4 Evolution candidate, never publishing."""

import argparse
import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from renault_4_review import (
    ALL_SOURCES, AUTH_RN, LIMIT, ROOT, SOURCES, VERSION_IDS, SourceFetcher,
    exact_rn_consumption, one, parse_document, review, stock_reference, unique_object,
)


DEALER = 'RN Automotive Tagene'
LOCATOR = 'https://www.renault.se/om-oss/aterforsaljare'
SOURCE_URLS = {**SOURCES, 'evolution-stock.html': ALL_SOURCES['evolution-stock.html'],
               'rn-dealer.html': ALL_SOURCES['rn-dealer.html'], 'locator.html': LOCATOR}


def dealer_appointment(raw):
    doc = parse_document(raw, 'text/html')
    canonical = [n.attrs.get('href') for n in doc.nodes('link') if n.attrs.get('rel') == 'canonical']
    if canonical != [LOCATOR]:
        raise ValueError('r4_official_dealer_locator_required')
    state = json.loads(one((''.join(n.children) for n in doc.nodes('script')
                            if n.attrs.get('id') == '__NEXT_DATA__' and n.attrs.get('type') == 'application/json'),
                           'r4_unique_dealer_locator_data_required'), object_pairs_hook=unique_object)
    if state.get('locale') != 'sv-SE' or state.get('query') != {'path': ['om-oss', 'aterforsaljare']}:
        raise ValueError('r4_swedish_dealer_locator_required')

    def rows(node):
        if isinstance(node, dict):
            if node.get('dealerId') == '75225600':
                yield node
            for child in node.values():
                yield from rows(child)
        elif isinstance(node, list):
            for item in node:
                yield from rows(item)

    entry = one(rows(state['props']['pageProps']['componentProps']), 'r4_exact_tagene_locator_entry_required')
    if (entry.get('name') != DEALER or entry.get('markerType') != 'sales'
            or entry.get('services', {}).get('RenaultPassengerCarSales') != 'True'):
        raise ValueError('r4_renault_passenger_car_sales_appointment_required')
    return {'value': DEALER, 'quote': DEALER + ' | 75225600 | RenaultPassengerCarSales: True',
            'source_url': LOCATOR, 'source_hash': hashlib.sha256(raw).hexdigest()}


def candidate(files, fetched, observed):
    if files.keys() != SOURCE_URLS.keys() or fetched.keys() != files.keys():
        raise ValueError('r4_complete_exact_evolution_sources_required')
    for timestamp in fetched.values():
        if not 0 <= (observed - datetime.fromisoformat(timestamp)).total_seconds() <= 900:
            raise ValueError('r4_evolution_simultaneous_source_capture_required')
    source_review = review({name: files[name] for name in SOURCES})
    version = source_review['swedish_current_ev52_versions']['EVOLUTION']
    card = source_review['manufacturer_exact_version_cards']['EVOLUTION']
    appointment = dealer_appointment(files['locator.html'])
    dealer = stock_reference(files, 'evolution-stock.html', 'rn-dealer.html', 'EVOLUTION', version,
                            {'car_id': '261900', 'car_model': '4 E-Tech', 'car_year': 2027,
                             'car_version': 'ELECTRIC EVOLUTION EV52 // Vinterhjul fr. 199kr/m\xe5n'},
                            DEALER, AUTH_RN, include_claims=True)
    official_price = version['price']
    cash = source_review['manufacturer_price_crosschecks']['EVOLUTION']
    if not dealer['cash_offer']['matches_manufacturer_amount'] or official_price['value'] != cash['value']:
        raise ValueError('r4_evolution_recommended_price_disagrees')
    km = dealer.get('equipment_wltp_reference', {})
    dc = dealer.get('equipment_dc_reference', {})
    if (km.get('value') != 407 or card['range_reference']['value'] != 407 or not card['matches_preliminary_range']
            or dc.get('value') != 100 or card['dc_observations']['price_list']['value'] != 100):
        raise ValueError('r4_evolution_exact_range_or_dc_changed')
    consumption = exact_rn_consumption(files, 'evolution-stock.html', dealer)
    hardware = source_review['shared_technical_evidence']
    return {'status': 'private_evolution_candidate', 'captured_at': observed.isoformat(), 'fetched_at': fetched,
            'sources': {name: {'url': SOURCE_URLS[name], 'sha256': hashlib.sha256(raw).hexdigest()}
                        for name, raw in files.items()},
            'identity': {'manufacturer_version_id': VERSION_IDS[0], 'powertrain': 'EV52 / 110 kW',
                         'model_year': dealer['model_year'], 'edition': dealer['identity'],
                         'year_scope': 'exact Swedish dealer MY27, not manufacturer factory-model-year confirmation'},
            'fields': {**{key: hardware[key] for key in ('battery_kwh', 'ac_charge_kw', 'boot_liters', 'tow_kg', 'seats')},
                       'dc_charge_kw': {**card['dc_observations']['price_list'], 'corroboration': dc},
                       'wltp_range_km': {**km, 'corroboration': card['range_reference']},
                       'wltp_consumption_kwh_100km': consumption, 'drivetrain': dealer['drivetrain']},
            'price': {**official_price, 'manufacturer_cash_crosscheck': cash, 'dealer_offer': dealer['cash_offer']},
            'appointment': appointment, 'body': source_review['body'], 'market': source_review['market_index'],
            'alternatives': {'generic_stock_km': dealer['wltp_range_observation'],
                             'version_card_dc': card['dc_observations']['version_card'],
                             'preliminary_wltp': version['preliminary_wltp_range'],
                             'stock_condition_issues': dealer['release_issues']},
            'publication_approved': False, 'production_writes': 0, 'paid_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--capture', action='store_true')
    modes.add_argument('--replay', type=Path)
    parser.add_argument('--emit', action='store_true', help='Include validated candidate data in replay output')
    args = parser.parse_args()
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    if root != ROOT.resolve() / 'data/local/release-data' or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', p, re.I) for p in root.parts):
        raise ValueError('r4_private_release_directory_required')
    if args.capture:
        fetcher = SourceFetcher(timeout=25, max_bytes=LIMIT, document_parser=lambda body, _: body,
                                text_parser=lambda *_: '', url_policy=lambda url, _: url in SOURCE_URLS.values())
        files, fetched = {}, {}
        for name, url in SOURCE_URLS.items():
            result = fetcher.fetch(url, {'Renault'})
            if (result['status'], result.get('http_status'), result.get('final_url')) != ('reachable', 200, url):
                raise ValueError('r4_evolution_source_unavailable: ' + url)
            files[name] = result['document']
            fetched[name] = datetime.now(timezone.utc).isoformat()
        packet = candidate(files, fetched, datetime.now(timezone.utc))
        folder = Path(tempfile.mkdtemp(prefix='renault-4-evolution-', dir=root))
        for name, raw in files.items():
            (folder / name).write_bytes(raw)
        (folder / 'candidate.json').write_text(json.dumps(packet, indent=2) + '\n', encoding='utf-8')
    else:
        folder = args.replay.resolve(strict=True)
        if folder != args.replay.absolute() or folder.parent != root or not re.fullmatch(r'renault-4-evolution-[a-z0-9_]+', folder.name):
            raise ValueError('r4_private_evolution_capture_required')

        def read(name):
            path = folder / name
            if path.resolve(strict=True) != path or not path.is_file() or not 0 < path.stat().st_size <= LIMIT:
                raise ValueError('r4_regular_capture_file_required')
            return path.read_bytes()

        saved = json.loads(read('candidate.json'), object_pairs_hook=unique_object)
        packet = candidate({name: read(name) for name in SOURCE_URLS}, saved['fetched_at'],
                           datetime.fromisoformat(saved['captured_at']))
        if saved != packet:
            raise ValueError('r4_evolution_capture_or_candidate_changed')
    print(json.dumps(packet if args.emit else {'output': str(folder / 'candidate.json'), 'publication_approved': False}))


if __name__ == '__main__':
    main()
