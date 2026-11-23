"""Replay the Swedish Advanced Tech 17-inch seating evidence without publishing it."""

import argparse
import hashlib
import json
import re
from html import unescape
from pathlib import Path
from manufacturer_embedded_data import ScriptData, unique_object
from variant_refresh import one, parse_document

ROOT = Path(__file__).resolve().parents[1]
MATERIAL = '6XS5ZDZ7ZHH09P'
DEALER = 'https://hedinautomotive.se'
BRANCH = '/anlaggningar/hedin-automotive-hyundai-danderyd'
SITE = 'https://hyundai.hedinautomotive.se/model/INSTER'
ASSET = '01a1f323-1e3d-78e3-8262-4aecc13137f9'
PHOTO_SHA = 'c65be46056cf1f5361bbc2677400485fcb0da31f639c27cdc81ffdfa15e38715'
SOURCES = {
    'listing': DEALER + '/bilar/kop-bil/258182/pc-nc-hyundai-inster-2027',
    'factory': SITE + '/' + MATERIAL + '?customer=private&dealerSite=hedinautomotive.se&ext=SRM&int=NNB',
    'variants': SITE + '?customer=private',
    'authority': 'https://www.hyundai.com/se/sv/tjanster/online-tjanster/hitta-aterforsaljare/hitta-agent.html',
}


def exact_factory_packages(body):
    def matches(value):
        if isinstance(value, dict):
            if value.get('MATNR') == MATERIAL:
                yield value
            for item in value.values():
                yield from matches(item)
        elif isinstance(value, list):
            for item in value:
                yield from matches(item)

    parser = ScriptData()
    parser.feed(body.decode('utf-8'))
    records = []
    for script in parser.scripts:
        frame = re.fullmatch(r'\s*self\.__next_f\.push\((.+)\);?\s*', script, re.S)
        if not frame or MATERIAL not in script:
            continue
        pair = json.loads(frame[1], object_pairs_hook=unique_object)
        if not isinstance(pair, list) or len(pair) != 2 or pair[0] != 1 or not isinstance(pair[1], str):
            continue
        for line in pair[1].splitlines():
            match = re.fullmatch(r'[0-9a-f]+:([\[{].*)', line)
            if match and MATERIAL in line:
                records.extend(matches(json.loads(match[1], object_pairs_hook=unique_object)))
    row = one(records, 'require_unique_factory_material_card')
    identity = tuple(row.get(key) for key in ('MODEX', 'MAKTX', 'PT_TYPE', 'ZZEXC', 'ZZINC', 'ZZEXX', 'ZZINX'))
    packages = row.get('PACKAGES') or []
    labels = {entry.get('PK_CODE'): unescape(entry.get('PK_DESC', '')) for entry in packages}
    if (identity != ('INSTER', '49kWh Advanced MY27', 'EV', 'SRM', 'NNB', 'Sienna Orange Metallic', 'Svart')
            or len(packages) != 2 or labels != {'PK0002': "17'' Aluminiumf\u00e4lgar", 'PK0005': 'Tech-paket'}):
        raise ValueError('factory_material_packages_changed')
    return row


def seat_proof(bodies, receipts, photo):
    locator = bodies['authority'].decode('utf-8')
    decoder = json.JSONDecoder(object_pairs_hook=unique_object)
    outlet = one((decoder.raw_decode(locator[m.start():])[0]
                  for m in re.finditer(r'\{\s*"id"\s*:\s*"C18AS26005"', locator)), 'require_hedin_authorization')
    if (outlet.get('fullDealerName'), outlet.get('outletType'), outlet.get('onlyService')) != ('Hyundai Danderyd', '3S', False):
        raise ValueError('hedin_sales_authorization_changed')
    if not any(site.get('url') == DEALER + '/' for site in outlet.get('website', [])):
        raise ValueError('hedin_dealer_url_changed')

    listing = parse_document(bodies['listing'], 'text/html')
    if not any(node.attrs.get('href') == BRANCH for node in listing.nodes('a')):
        raise ValueError('require_matching_hedin_branch')
    data = one((node for node in listing.nodes('script') if node.attrs.get('id') == '__NEXT_DATA__'),
               'require_one_hedin_vehicle_response')
    components = json.loads(''.join(data.children), object_pairs_hook=unique_object)['props']['pageProps']['componentProps']
    car = one((value['car'] for value in components.values()
               if isinstance(value, dict) and isinstance(value.get('car'), dict)), 'require_one_hedin_demonstrator')
    expected = {'car_id': '258182', 'car_brand': 'Hyundai', 'car_model': 'Inster', 'car_year': 2027,
                'car_version': '49kWh ADVANCED TECH-PAKET+17" PIXEL-SIENNA ORANGE - DEMO',
                'car_fuel': 'El', 'battery_size': 49, 'car_site_city': 'Danderyd',
                'car_site_id': 'a871d30547050e1000b28b42e36d438d', 'car_color': 'Orange', 'car_seats': '4'}
    if any(car.get(key) != value for key, value in expected.items()):
        raise ValueError('hedin_advanced_demo_seating_or_identity_changed')
    if ASSET not in json.dumps(car.get('car_images')) or hashlib.sha256(photo).hexdigest() != PHOTO_SHA:
        raise ValueError('reviewed_rear_photo_not_bound_to_this_demo')

    factory = parse_document(bodies['factory'], 'text/html')
    titles = [node.text() for node in factory.nodes('title')]
    layout = ['50:50 delat/f\u00e4llbart baks\u00e4te', 'Skjutbart baks\u00e4te i l\u00e4ngsled']
    if titles != ['INSTER \u00b7 49kWh Advanced MY27 | Hyundai Sverige'] or not set(layout) <= {n.text() for n in factory.nodes('li')}:
        raise ValueError('factory_advanced_seat_layout_changed')
    exact_factory_packages(bodies['variants'])

    return {
        'status': 'inster_exact_advanced_seats_verified_private', 'material': MATERIAL,
        'model_year': 2027, 'wheels_inches': 17, 'must_include_tech_package': True,
        'seats': {'value': 4, 'source_url': SOURCES['listing'], 'source_hash': receipts['listing']['sha256'],
                  'source_quote': '"car_seats":"4"', 'authorization_evidence_url': SOURCES['authority']},
        'factory_equipment_scope': {'source_url': SOURCES['factory'], 'rear_seat_quotes': layout,
                                    'package_index': SOURCES['variants']},
        'photo_visual_check': {'asset_id': ASSET, 'sha256': PHOTO_SHA, 'rear_positions': 2, 'private_only': True},
        'other_variants_unchanged': True, 'publication_approved': False, 'production_writes': 0,
    }


def replay(path):
    folder = path.absolute()
    root = ROOT / 'data/local/release-data'
    if (folder.resolve(strict=True) != folder or root not in folder.parents
            or not folder.name.startswith('inster-exact-interior-') or any('onedrive' in p.lower() for p in folder.parts)):
        raise ValueError('require_original_private_inster_capture')

    def read(name):
        file = folder / name
        if file.resolve(strict=True) != file:
            raise ValueError('private_inster_links_not_allowed')
        return file.read_bytes()

    receipts = json.loads(read('receipt.json'), object_pairs_hook=unique_object)
    bodies = {key: read(key + '.html') for key in SOURCES}
    for key, url in SOURCES.items():
        if (receipts[key]['source_url'], receipts[key]['sha256']) != (url, hashlib.sha256(bodies[key]).hexdigest()):
            raise ValueError('inster_seat_source_changed:' + key)
    return seat_proof(bodies, receipts, read('first-photo-4.jpg'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', type=Path, required=True)
    print(json.dumps(replay(parser.parse_args().replay)))
