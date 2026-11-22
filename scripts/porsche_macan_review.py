"""Read-only evidence for the Swedish MY27 Macan Electric base configuration."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from audit_catalog_sources import SourceFetcher
from variant_refresh import Node, one, parse_document

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'data/local/release-data'
CODE = 'XABAA1'
BASE = f'https://configurator.porsche.com/sv-SE/mode/model/{CODE}'
SOURCES = {
    'base': BASE,
    'technical': BASE + '/specifications?tab=technical-data',
    'equipment': BASE + '/specifications?tab=standard-equipment',
    'comparison': 'https://compare.porsche.com/sv-SE?model-series=macan',
}
PRICE = 970000
TECHNICAL = {
    'wltp_range_km': ('R\u00e4ckvidd kombinerad (WLTP) - fordonsspecifik', '642 km', 642),
    'wltp_consumption_kwh_100km': ('Elektrisk f\u00f6rbrukning blandad (fordonsspecifik)', '16,7 kwh/100 km', 16.7),
    'battery_kwh': ('Bruttokapacitet batteri', '100,0 kWh', 100),
    'dc_charge_kw': ('Maximal laddningsstyrka vid direktstr\u00f6m (DC)', '270 kW', 270),
    'boot_liters': ('Bagagerumsvolym (upp till \u00f6verkant baks\u00e4te)', '518 l', 518),
    'tow_kg': ('Dragvikt (bromsad/obromsad)', '2 000 kg', 2000),
}
EQUIPMENT = {
    'wheels': ('20"-f\u00e4lg Macan', 'Sommard\u00e4ck 20-tum'),
    'ac_charge_kw': ('Ombordladdare 11 kW',),
    'seats': ('Komfortsportstolar fram (8-v\u00e4gs)', 'Baks\u00e4te 3-sits (2+1)'),
    'drivetrain': ('Bakhjulsdrift', 'Porsche E-Performance-drivlina med permanentmagnetisk synkronmotor p\u00e5 bakaxel'),
}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def configurator(bodies, kind):
    doc = parse_document(bodies[kind], 'text/html')
    canonical = one((n.attrs.get('href') for n in doc.nodes('link')
                     if n.attrs.get('rel') == 'canonical'), 'expected_one_configurator_canonical')
    value = one((n for n in doc.nodes('script') if n.attrs.get('type') == 'application/ld+json'),
                'expected_one_configurator_json_ld')
    product = one((item for item in json.loads(''.join(value.children))['@graph']
                   if item.get('@type') == ['Product', 'Car']), 'expected_one_configurator_car')
    if (canonical != SOURCES[kind].split('?')[0]
            or (product.get('url'), product.get('name'), product.get('model'), product.get('modelDate'),
                product.get('brand', {}).get('name')) != (SOURCES[kind], 'Macan', 'Macan', '2027', 'Porsche')):
        raise ValueError('wrong_swedish_macan_model_or_year')
    offer = product.get('offers', {})
    if (offer.get('price'), offer.get('priceCurrency')) != (str(PRICE), 'SEK'):
        raise ValueError('macan_base_price_changed')
    return doc, offer


def row_values(doc, label):
    values = set()
    for node in doc.nodes('p'):
        if node.text() != label:
            continue
        cols = [child for child in node.parent.children if isinstance(child, Node)]
        if len(cols) == 2 and cols[0] is node and cols[1].tag == 'p':
            values.add(cols[1].text())
    return values


def standard_headings(doc):
    return {n.text() for group in doc.nodes('icc-p-accordion') for n in group.nodes('h4')}


def check_comparison(body):
    doc = parse_document(body, 'text/html')
    if [n.attrs.get('href') for n in doc.nodes('link') if n.attrs.get('rel') == 'canonical'] != [SOURCES['comparison']]:
        raise ValueError('wrong_swedish_comparison')
    title = one((n for n in doc.nodes('h4') if n.text() == 'Macan'), 'expected_one_base_macan_card')
    card = title.parent
    while card and len(list(card.nodes('h4'))) == 1:
        text = card.text()
        if all(s in text for s in ('Fr\u00e5n 970 000 kr', '2027', 'Bakhjulsdrift', '642 km', '0 - 0 g/km')):
            return
        card = card.parent
    raise ValueError('macan_comparison_price_or_scope_changed')


def review(bodies):
    base, _ = configurator(bodies, 'base')
    technical, _ = configurator(bodies, 'technical')
    equipment, offers = configurator(bodies, 'equipment')
    check_comparison(bodies['comparison'])
    if row_values(base, 'Grundpris') != {'970 000 kr'} or row_values(base, 'Totalpris *') != {'970 000 kr'}:
        raise ValueError('macan_base_price_or_selected_options_changed')
    facts, evidence = {}, {}
    for field, (label, exact, value) in TECHNICAL.items():
        if row_values(technical, label) != {exact}:
            raise ValueError('macan_technical_value_changed:' + field)
        facts[field] = value
        evidence[field] = {'source': 'technical', 'snippet': label + ' ' + exact}
    if row_values(technical, 'Max. dragvikt (obromsad)') != {'750 kg'}:
        raise ValueError('macan_braked_tow_basis_changed')
    headings = standard_headings(equipment)
    for field, required in EQUIPMENT.items():
        if not set(required) <= headings:
            raise ValueError('macan_standard_equipment_changed:' + field)
    if {h for h in headings if h.startswith('Baks\u00e4te ')} != {EQUIPMENT['seats'][1]}:
        raise ValueError('macan_standard_seats_ambiguous')
    for name, price in [('Ombordladdare 22 kW', '17900'), ('Dragkrok, inf\u00e4llbar', '13700')]:
        if name in headings or not any(addon.get('name') == name and addon.get('price') == price
                                      and addon.get('priceCurrency') == 'SEK' for addon in offers.get('addOn', [])):
            raise ValueError('macan_optional_equipment_scope_changed')
    for field, value in {'ac_charge_kw': 11, 'seats': 5, 'drivetrain': 'RWD'}.items():
        facts[field] = value
        evidence[field] = {'source': 'equipment', 'snippet': ' | '.join(EQUIPMENT[field])}
    return {
        'status': 'macan_base_evidence_verified_private',
        'model_code': CODE, 'model_year': 2027, 'market': 'SE', 'wheels_inches': 20,
        'price_sek': PRICE, 'price_type': 'manufacturer_from',
        'price_evidence': {'source': 'comparison', 'snippet': 'Fr\u00e5n 970 000 kr',
                           'configurator_base_source': 'base'},
        'facts': facts, 'evidence': evidence,
        'qualifications': {'battery': 'gross', 'range': 'combined WLTP, standard 20-inch wheels',
                           'cargo': 'rear cargo to the top of the rear seat backrest',
                           'towing': 'braked, with the optional tow bar', 'ac': 'standard on-board charger'},
        'publication_approved': False, 'database_writes': 0, 'paid_calls': 0,
    }


def capture():
    if PRIVATE.resolve() != PRIVATE or any('onedrive' in part.lower() for part in PRIVATE.parts):
        raise ValueError('require_private_unlinked_evidence_directory')
    f = SourceFetcher(timeout=15, max_bytes=3_000_000, document_parser=lambda body, *_: body,
                      text_parser=lambda *_: '', url_policy=lambda url, brands:
                      url in SOURCES.values() and brands == {'Porsche'})
    bodies, receipts = {}, {}
    for kind, url in SOURCES.items():
        res = f.fetch(url, {'Porsche'})
        if (res['status'], res.get('http_status'), res.get('final_url')) != ('reachable', 200, url):
            raise ValueError(f'{kind}_source_unavailable:{res["status"]}')
        bodies[kind] = res['document']
        receipts[kind] = {'source_url': url, 'content_hash': sha(bodies[kind]),
                          'http_status': 200, 'fetched_at': datetime.now(timezone.utc).isoformat()}
    report = {**review(bodies), 'sources': receipts}
    PRIVATE.mkdir(parents=True, exist_ok=True)
    folder = Path(mkdtemp(prefix='porsche-macan-my27-', dir=PRIVATE))
    for kind, body in bodies.items():
        (folder / (kind + '.html')).write_bytes(body)
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    return folder, report


def replay(folder):
    folder = folder.resolve(strict=True)
    if folder.parent != PRIVATE or not folder.name.startswith('porsche-macan-my27-'):
        raise ValueError('require_private_macan_source_packet')
    report = json.loads((folder / 'report.json').read_text(encoding='utf8'))
    receipts = report['sources']
    if set(receipts) != set(SOURCES):
        raise ValueError('unexpected_macan_source_scope')
    bodies = {k: (folder / (k + '.html')).read_bytes() for k in SOURCES}
    for kind, url in SOURCES.items():
        r = receipts[kind]
        if (r.get('source_url'), r.get('http_status'), r.get('content_hash')) != (url, 200, sha(bodies[kind])):
            raise ValueError('macan_evidence_changed:' + kind)
    if report != {**review(bodies), 'sources': receipts}:
        raise ValueError('macan_replay_changed')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    args = parser.parse_args()
    folder, report = capture() if args.capture else (args.replay, replay(args.replay))
    print(json.dumps({'folder': str(folder), 'status': report['status'], 'price_sek': report['price_sek'],
                      'fields': len(report['facts']), 'production_writes': 0, 'publication_approved': False}))
