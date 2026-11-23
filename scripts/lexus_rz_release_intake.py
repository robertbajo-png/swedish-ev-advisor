"""Replay the evidence for the current Swedish RZ 350e FWD Executive only."""

import argparse
import dataclasses
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from import_mobility_sweden import parse_elbil_ranking
from lexus_rz_manual_evidence import MANUAL_BYTES, confirmed_tow, read_manual
from lexus_rz_nordic_crosscheck import NAMES, review as nordic_review, shared_charging_report
from lexus_rz_review import CONFIG_API, MODEL, PRICE, digest, private_capture, private_root, read_capture, replay_review
from manufacturer_embedded_data import unique_object
from porsche_macan_market import WORKBOOK, replay as replay_october

NAME = '350e Executive'
IDENTITY = (NAME, 'd032f909-69f8-45ea-bc22-7c6161ca2105', 'XEBM20L-AWDCSW', 'AB')
FACTS = {'wltp_range_km': 567, 'wltp_consumption_kwh_100km': 14.5, 'battery_kwh': 77,
         'dc_charge_kw': 150, 'ac_charge_kw': 22, 'boot_liters': 586, 'tow_kg': 750,
         'seats': 5, 'drivetrain': 'FWD'}
FOLDERS = {'swedish': 'lexus-rz-review', 'nordic': 'lexus-rz-nordic',
           'charging': 'lexus-rz-charging', 'manual': 'lexus-rz-manual', 'market': 'porsche-macan-market'}


def only(rows):
    row, = rows
    return row


def captured_json(folder):
    body = read_capture(folder, 'review.json', 100_000)
    return json.loads(body, object_pairs_hook=unique_object), digest(body)


def source(url, sha, at, kind, country='SE', language='sv', name='Lexus Sverige'):
    return {'final_url': url, 'content_hash': sha, 'fetched_at': at, 'source_type': kind,
            'country': country, 'language': language, 'source_authority': 'manufacturer', 'source_name': name,
            'http_status': 200, 'status': 'reachable'}


def build(root, packets, now):
    if set(packets) != set(FOLDERS):
        raise ValueError('rz_require_all_exact_evidence_packets')
    dirs = {key: private_capture(root, root / packets[key], prefix) for key, prefix in FOLDERS.items()}
    _, swedish = replay_review(root, dirs['swedish'])
    _, se_hash = captured_json(dirs['swedish'])
    dk, dk_hash = captured_json(dirs['nordic'])
    charging, _ = captured_json(dirs['charging'])
    if dk != nordic_review({name: read_capture(dirs['nordic'], name) for name in NAMES}, swedish, se_hash,
                           datetime.fromisoformat(dk['captured_at'])):
        raise ValueError('rz_reviewed_danish_capture_changed')
    if charging != shared_charging_report(read_capture(dirs['charging'], 'norwegian-sheet.pdf'), swedish, dk, dk_hash,
                                         datetime.fromisoformat(charging['captured_at'])):
        raise ValueError('rz_reviewed_norwegian_capture_changed')
    market_report = replay_october(dirs['market'])
    workbook_source = market_report['sources']['market.xlsx']
    values, months = parse_elbil_ranking(dirs['market'] / 'market.xlsx', WORKBOOK)
    exact = lambda row: (row.brand_raw, row.model_raw, row.fuel_type_raw) == ('LEXUS', 'RZ', 'EL')
    market = dataclasses.asdict(only(row for row in values if exact(row)))
    month = only(row for row in months if exact(row))
    if (market['last_seen_month'], market['registrations_last_month'], market['registrations_ytd'],
            market['model_group'], market['needs_mapping'], month.month, month.registrations) != (
            '2026-10-01', 50, 439, None, False, '2026-10-01', 50):
        raise ValueError('rz_october_model_only_market_identity_changed')
    variant = only(row for row in swedish['variants'] if row['variant'] == NAME)
    danish = only(row for row in dk['variants'] if row['variant'] == NAME)
    crosscheck = only(row for row in charging['variants'] if row['variant'] == NAME)
    for row, car_key in ((variant, 'car_id'), (danish, 'se_car_id'), (crosscheck, 'car_id')):
        if (row['variant'], row[car_key], row['type_code'], row['suffix']) != IDENTITY:
            raise ValueError('rz_exact_current_fwd_executive_configuration_required')
    standard, selected = variant['standard_configuration'], variant['technical_configuration']
    price = variant['facts']['price_sek']
    if (standard['car_id'], standard['standard_wheels_inches'], standard['cash_sek'],
            price['value'], price['source_url'], price['corroboration']['value'], price['corroboration']['source_url']) != (
            IDENTITY[1], 18, 599000, 599000, PRICE, 599000, MODEL):
        raise ValueError('rz_current_swedish_manufacturer_from_price_changed')
    if (crosscheck['dc_charge_kw'], danish['dc_kw'], crosscheck['dk_quote']) != (
            150, 150, danish['dc_quote']):
        raise ValueError('rz_same_hardware_dc_evidence_required')
    towing = confirmed_tow(read_manual(read_capture(dirs['manual'], 'manual.pdf', MANUAL_BYTES)), IDENTITY, 'FWD', {
        'swedish_configurator': {'quotes': selected['tow_limit_references']},
        'danish_reference_only': {'braked_kg': danish['braked_kg']},
    })
    if towing is None or towing['value'] != 750:
        raise ValueError('rz_reviewed_swedish_braked_towing_required')
    swedish_at, dk_at = swedish['captured_at'], dk['captured_at']
    receipt_times = [swedish_at, dk_at, charging['captured_at'], workbook_source['fetched_at']]
    observed = [datetime.fromisoformat(at) for at in receipt_times]
    if observed[:3] != sorted(observed[:3]) or any(not -60 <= (now-at).total_seconds() <= 900 for at in observed):
        raise ValueError('rz_fresh_ordered_manufacturer_and_market_receipts_required')
    primary = source(MODEL, price['corroboration']['source_hash'], swedish_at, 'manufacturer_model_page')
    list_pdf = source(PRICE, price['source_hash'], swedish_at, 'manufacturer_price_list')
    selected_se = source(CONFIG_API, selected['source_hash'], swedish_at, 'manufacturer_configurator')
    dc_evidence = charging['selected_source']
    selected_dk = source(dc_evidence['url'], dc_evidence['sha256'], dk_at,
                         'manufacturer_configurator', 'DK', 'da', 'Lexus Danmark')
    fields = {k: {'value': row['value'], 'source_url': row['source_url'], 'source_hash': row['source_hash'],
                  'quote': row['source_quote']} for k, row in variant['facts'].items() if k != 'price_sek'}
    fields['dc_charge_kw'] = {'value': 150, 'source_url': selected_dk['final_url'],
                              'source_hash': selected_dk['content_hash'], 'quote': crosscheck['dk_quote']}
    fields['tow_kg'] = {'value': 750, 'source_url': CONFIG_API,
                         'source_hash': selected['source_hash'], 'quote': only(selected['tow_limit_references'])}
    if {key: row['value'] for key, row in fields.items()} != FACTS:
        raise ValueError('rz_verified_350e_technical_profile_changed')
    return {
        'status': 'private_current_lexus_executive_intake', 'identity': list(IDENTITY),
        'sources': [primary, list_pdf, selected_se, selected_dk],
        'field_evidence': fields, 'market': {'row': market, 'source': workbook_source},
        'price_evidence': {'value': price['value'], 'source_url': MODEL, 'source_hash': primary['content_hash'],
                           'quote': price['corroboration']['source_quote'], 'price_type': 'manufacturer_from',
                           'price_valid_until': None, 'corroboration': {'source_url': PRICE,
                           'source_hash': price['source_hash'], 'quote': price['source_quote']}},
        'source_decisions': {
            'model_year': 'not asserted; current Swedish configuration identity only',
            'wltp': 'configuration value, not the generic model-page maximum; standard 18-inch wheels',
            'swedish_request_hash': selected['request_hash'],
            'danish_request_hash': dc_evidence['request_sha256'],
            'dc_corroboration': charging['corroboration'],
            'swedish_manual': {key: towing[key] for key in ('source_url', 'source_hash', 'source_quote', 'document_id', 'page', 'scope')},
        },
        'publication_approved': False, 'production_writes': 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', type=Path)
    for name in FOLDERS:
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    root = private_root()
    now = datetime.now(timezone.utc)
    if args.replay:
        if any(getattr(args, name) is not None for name in FOLDERS):
            parser.error('Replay uses its sealed evidence attachments')
        folder = private_capture(root, args.replay, 'lexus-rz-current')
        frozen = json.loads(read_capture(folder, 'intake.json', 100_000), object_pairs_hook=unique_object)
        report = build(root, frozen['packets'], now)
        if report != frozen['report']:
            raise ValueError('rz_current_executive_evidence_changed')
        print(json.dumps(report))
    else:
        paths = {key: getattr(args, key) for key in FOLDERS}
        if not all(paths.values()):
            parser.error('Provide the Swedish, Nordic, charging, manual and market packets')
        packets = {key: private_capture(root, value, FOLDERS[key]).name for key, value in paths.items()}
        report = build(root, packets, now)
        folder = Path(tempfile.mkdtemp(prefix='lexus-rz-current-', dir=root))
        (folder / 'intake.json').write_text(json.dumps({'packets': packets, 'report': report}, indent=2) + '\n', encoding='utf8')
        print(json.dumps({'folder': str(folder), 'status': report['status'], 'fields': len(report['field_evidence']),
                          'publication_approved': False, 'production_writes': 0}))


if __name__ == '__main__':
    main()
