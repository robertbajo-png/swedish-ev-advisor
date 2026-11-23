"""Capture private Lexus engineering corroboration without promoting foreign values."""

import argparse
import io
import json
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from lexus_rz_review import (
    BODY_ID, CONFIG_CAPTURE, CONFIG_ORIGIN, EDITIONS, MODEL_ID, canonical_document, collect_configurator, digest, fetch_exact,
    get_one, only, private_capture, private_root, published_components, read_capture, replay_review, request_bytes,
    technical_operation, unique_object,
)

MODEL = 'https://www.lexus.dk/nye-biler/rz'
CONTENT = '/content/lexus/denmark/da/new-cars/rz'
API = CONFIG_ORIGIN + '/v1/api/data/dk/da'
NAMES = ('market-model.html', 'selected-configurations.json', 'selected-technical-specs.json')
DC_LABEL = '150 kW DC-lynoplader med CCS2-indgang'
BRAKED_LABEL = 'Total tr\u00e6kkapacitet, med bremser (kg)'
UNBRAKED_LABEL = 'Total tr\u00e6kkapacitet, uden bremser (kg)'
DRIVES = {'FWD': '4X2', 'AWD': '4X4'}
CAR_NAMES = {
    '350e': 'Lexus RZ SUV 350e 165 kW/77 kWh (224 hk) aut. gear Executive',
    '500e': 'Lexus RZ SUV 500e 280 kW/77 kWh (380 hk) aut. gear AWD Executive',
    '550e': 'Lexus RZ SUV 550e 300 kW/77 kWh (408 hk) aut. gear AWD F Sport',
}
CHARGING_SHEET = ('https://www.lexus.no/content/dam/lexus/nmsc/norway/documents/pricelists/'
                  'rz/RZ-Prisliste_November_2025_V1.pdf')
FACTORY_SHEET = ('https://newsroom.lexus.it/download/13011149-f516-401a-b1d7-eeead4151ea8/'
                 'rz_my26_listinoampspecifiche_def.pdf')


def factory_sheet_rows(page):
    lines = page.splitlines()
    compact = [' '.join(line.split()) for line in lines]
    if not {'LISTINO PREZZI RZ MC26', 'Del: 02/01/2026', 'In vigore da: 02/01/2026'} <= set(compact):
        raise ValueError('rz_it_model_year_document_scope_changed')
    start = only((i for i, line in enumerate(compact) if line.startswith('Codice Modello Trazione Katashiki Versione ')),
                 'rz_it_factory_column_header_missing')
    end = only((i for i, line in enumerate(compact) if i > start and line == 'Optional'), 'rz_it_factory_table_end_missing')
    rows = [re.split(r'\s{2,}', line.strip()) for line in lines[start + 1:end] if line.strip().startswith('RZ ')]
    scope = [(row[0], row[1], row[3]) for row in rows if len(row) == 7]
    if len(rows) != 3 or scope != [('RZ 350e 2WD MY26 EXE', 'FWD', 'RZ EXECUTIVE 2WD'),
                                   ('RZ 500e 4WD MY26 LUX', 'AWD', 'RZ LUXURY 4WD'),
                                   ('RZ 550e 4WD MY26 F-SPORT', 'AWD', 'RZ F-SPORT 4WD')]:
        raise ValueError('rz_it_factory_variant_order_or_grade_changed')
    codes = [row[2] for row in rows]
    if codes != ['XEBM20L-AWDCSW', 'XEBM25L-AWDLSW', 'XEBM25L-AWDSSW']:
        raise ValueError('rz_it_factory_type_codes_changed')
    return [row[:4] for row in rows]


def factory_year_report(raw, swedish, nordic, nordic_hash, observed):
    if not 0 <= (observed - datetime.fromisoformat(swedish['captured_at'])).total_seconds() <= 86400:
        raise ValueError('rz_fresh_swedish_capture_required')
    if not 0 <= (observed - datetime.fromisoformat(nordic['captured_at'])).total_seconds() <= 86400:
        raise ValueError('rz_fresh_danish_capture_required')
    pdf = PdfReader(io.BytesIO(raw))
    if len(pdf.pages) != 7:
        raise ValueError('rz_it_model_year_document_layout_changed')
    rows = factory_sheet_rows(pdf.pages[1].extract_text(extraction_mode='layout'))
    results = []
    for se, dk, edition, (label, drive, code, trim) in zip(swedish['variants'], nordic['variants'], EDITIONS, rows, strict=True):
        motor, grade, _, _, se_drive, se_code, suffix, car_id = edition
        if ((se['variant'], se['car_id'], se['type_code'], se['suffix']) != (f'{motor} {grade}', car_id, se_code, suffix)
                or (dk['variant'], dk['se_car_id'], dk['type_code'], dk['suffix']) != (se['variant'], car_id, se_code, suffix)
                or drive != se_drive):
            raise ValueError('rz_model_year_corroboration_identity_conflict')
        same_type = code == se_code
        results.append({'variant': se['variant'], 'type_code': se_code, 'suffix': suffix,
                        'factory_year_reference': 2026 if same_type else None,
                        'it_type_code': code, 'it_trim': trim, 'it_quote': f'{label} | {drive} | {code} | {trim}',
                        'reason': 'matching factory type code; Italian sheet does not identify Swedish suffix'
                                  if same_type else 'Italian 500e Luxury is not the Swedish 500e Executive'})
    return {'status': 'private_factory_model_year_reference', 'captured_at': observed.isoformat(),
            'source': {'url': FACTORY_SHEET, 'sha256': digest(raw), 'market': 'IT', 'page': 2, 'edition': '2026-01-02'},
            'swedish_review_sha256': nordic['swedish_review_sha256'], 'nordic_review_sha256': nordic_hash,
            'variants': results, 'publication_approved': False, 'database_writes': 0, 'paid_calls': 0}


def charging_sheet_row(page):
    lines = [' '.join(line.split()) for line in page.splitlines() if line.strip()]
    for expected in ('NYE LEXUS R Z', 'RZ 350e RZ 500e RZ 550e', 'EXECUTIVE LUXURY EXECUTIVE LUXURY F SPORT',
                     'EFFEKT 165 kW / 224 hk 280 kW / 380 hk 300 kW / 408 hk'):
        only((line for line in lines if line == expected), 'rz_no_charging_table_identity_changed')
    row = only((line for line in lines if line.startswith('LADEHASTIGHET ')), 'rz_no_charging_row_required')
    cells = re.fullmatch(r'LADEHASTIGHET (\d{2,3}) kW (\d{2,3}) kW (\d{2,3}) kW (\d{2,3}) kW (\d{2,3}) kW', row)
    if not cells:
        raise ValueError('rz_no_charging_cells_changed')
    return tuple(int(cells[i]) for i in (1, 3, 5)), row


def shared_charging_report(raw, swedish, nordic, nordic_hash, observed):
    for packet in (swedish, nordic):
        age = (observed - datetime.fromisoformat(packet['captured_at'])).total_seconds()
        if not 0 <= age <= 86400:
            raise ValueError('rz_charging_recent_se_and_dk_reviews_required')
    pdf = PdfReader(io.BytesIO(raw))
    if len(pdf.pages) != 6:
        raise ValueError('rz_no_charging_document_layout_changed')
    powers, quote = charging_sheet_row(pdf.pages[5].extract_text(extraction_mode='layout'))
    evidence = []
    for se, dk, power in zip(swedish['variants'], nordic['variants'], powers, strict=True):
        if ((se['car_id'], se['type_code'], se['suffix']) != (dk['se_car_id'], dk['type_code'], dk['suffix'])
                or se['variant'] != dk['variant'] or se['facts']['ac_charge_kw']['value'] != 22
                or se['facts']['battery_kwh']['value'] != 77 or dk['dc_kw'] != power or not 20 <= power <= 600):
            raise ValueError('rz_charging_hardware_or_identity_conflict')
        evidence.append({'car_id': se['car_id'], 'variant': se['variant'], 'type_code': se['type_code'], 'suffix': se['suffix'],
                         'dc_charge_kw': power, 'dk_quote': dk['dc_quote'],
                         'still_held': [field for field in se['held'] if field != 'dc_charge_kw']})
    return {'status': 'private_shared_dc_hardware_review', 'captured_at': observed.isoformat(),
            'nordic_review_sha256': nordic_hash, 'swedish_review_sha256': nordic['swedish_review_sha256'],
            'selected_source': {**nordic['sources'][NAMES[2]], 'market': 'DK'},
            'corroboration': {'url': CHARGING_SHEET, 'sha256': digest(raw), 'page': 6, 'market': 'NO', 'quote': quote},
            'scope': 'DC hardware only: exact SE/DK factory configuration and matching NO grade/engine charging row',
            'variants': evidence, 'publication_approved': False, 'database_writes': 0, 'paid_calls': 0}


def register(raw, swedish, observed):
    canonical_document(raw, MODEL, 'da')
    grades = published_components(raw, country='dk', language='da', content=CONTENT,
                                  names=('powertraincomparison',))['powertraincomparison']['gradesData']
    age = (observed - datetime.fromisoformat(grades['_date'])).total_seconds()
    if not -60 <= age <= 7 * 86400 or (grades['code'], grades['name'], grades['certification']) != ('rz', 'RZ', 'WLTP'):
        raise ValueError('rz_dk_exact_current_model_required')
    if len(swedish) != len(EDITIONS):
        raise ValueError('rz_se_three_variants_required')
    rows = []
    for variant, (motor, grade, _, engine_code, drive, chassis, suffix, se_car) in zip(swedish, EDITIONS, strict=True):
        if ((variant['car_id'], variant['type_code'], variant['suffix'], variant['engine_code'])
                != (se_car, chassis, suffix, engine_code) or 'technical_configuration' not in variant):
            raise ValueError('rz_se_exact_technical_configuration_required')
        engine = only((engine for row in grades['grades'] if row['name'].casefold() == grade.casefold()
                       for body in row['bodyTypes'] for engine in body['engines'] if engine['etwCode'] == engine_code),
                      'rz_dk_unique_engine_and_grade_required')
        config = engine['minPrice']['config']
        part = config['PSLS']['Suffix']
        active = date.fromisoformat(part['AvailableFromDate'][:10]) <= observed.date() < date.fromisoformat(part['AvailableToDate'][:10])
        if (not active or engine.get('seoIndex') is not True
                or get_one(grades['wheeldrives'], 'code', engine['wheeldrive'])['name'] != DRIVES[drive]
                or tuple(config[k] for k in ('Country', 'Language', 'Brand', 'ModelID')) != ('dk', 'da', 'lexus', MODEL_ID)
                or (part['Katashiki'], part['Code']) != (chassis, suffix)
                or not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', config['CarID'])
                or config['CarID'] in {edition[-1] for edition in EDITIONS}):
            raise ValueError('rz_dk_factory_identity_differs')
        rows.append((variant, motor, grade, config['CarID']))
    if len({row[-1] for row in rows}) != len(rows):
        raise ValueError('rz_dk_duplicate_base_configuration')
    return rows


def operations(actions):
    return {'component': 'car-config', 'fetches': actions}


def cabin_codes(motor):
    return ('1L1', 'FD21' if motor == '550e' else 'EA10')


def car_cabin(car):
    return (car['colour']['internalCode'], car['upholstery']['internalCode'])


def car_request(rows):
    return operations([{'fetchType': 'fetchCarConfigCar', 'modelId': MODEL_ID, 'carId': car_id,
                        'tyCodeConfig': None, 'isPro': False} for _, _, _, car_id in rows])


def response_rows(raw, packet):
    found = json.loads(raw, object_pairs_hook=unique_object).get('fetches')
    if not isinstance(found, list) or len(found) != len(EDITIONS):
        raise ValueError('rz_dk_exact_three_responses_required')
    for row, expected in zip(found, packet['fetches'], strict=True):
        result = row['result']
        if ({k: v for k, v in row.items() if k != 'result'} != expected or result.get('errorLogs') not in (None, [])
                or result.get('responseStatus') not in (None, 200) or not isinstance(result.get('fetchResult'), dict)):
            raise ValueError('rz_dk_response_does_not_match_request')
        yield result['fetchResult']


def specs_request(raw, rows):
    actions = []
    for result, (variant, motor, grade, cid) in zip(response_rows(raw, car_request(rows)), rows, strict=True):
        car = result['car']
        wheel = car['wheel']
        inches = variant['standard_configuration']['standard_wheels_inches']
        if (car['id'] != cid or car['grade']['name'].casefold() != grade.casefold() or car['body']['id'] != BODY_ID
                or car['name'] != CAR_NAMES[motor] or car.get('soldOut') is not False
                or car_cabin(car) != cabin_codes(motor)
                or wheel.get('standard') is not True or wheel['price']['cash'] != 0 or not wheel['name'].startswith(f'{inches}" ')):
            raise ValueError('rz_dk_base_configuration_differs')
        actions.append(technical_operation(car, allow_colour_surcharge=True))
    return operations(actions)


def corroboration(result, variant):
    if result.get('massValidationSpecs') != {'error': None, 'exceedingKilogram': 0, 'successful': True}:
        raise ValueError('rz_dk_technical_configuration_validation_failed')
    specs = [item for group in result['techSpecs'] for item in group['data']]

    def measure(code, unit, label=None):
        row = get_one(specs, 'internalCode', code)
        shown = row['value'].strip()
        if row['unit'] != unit or (label and row['name'] != label) or not re.fullmatch(r'\d{1,4}', shown):
            raise ValueError(f'rz_dk_exact_label_and_unit_required: {code}')
        return int(shown), f'{row["name"]}: {shown} {unit}'

    if (measure('BATCAP', 'kWh')[0] != variant['facts']['battery_kwh']['value']
            or measure('PERCOMBINED', 'km')[0] != variant['facts']['wltp_range_km']['value']
            or get_one(specs, 'internalCode', 'PERCOMBINED')['certification'] != 2
            or measure('ECCOMBINEDWHKM', 'Wh/km')[0] != round(variant['facts']['wltp_consumption_kwh_100km']['value'] * 10)):
        raise ValueError('rz_dk_technical_identity_mismatch')
    dc = get_one(result['standardEquipment'], 'code', '6624963a')
    if dc.get('standard') is not True or dc['name'] != DC_LABEL:
        raise ValueError('rz_dk_standard_dc_charger_changed')
    braked, braked_quote = measure('TOWCAPBRK', 'kg', BRAKED_LABEL)
    unbraked, unbraked_quote = measure('TOWCAPNOBRK', 'kg', UNBRAKED_LABEL)
    if not 0 <= unbraked <= min(750, braked) or braked > 4000:
        raise ValueError('rz_dk_invalid_towing_capacity')
    se_references = variant['technical_configuration']['tow_limit_references']
    reference = [re.fullmatch(r'Dragvikt, (?:max )?(\d{1,4})\s?kg', value) for value in se_references]
    if reference and (len(reference) != 1 or not reference[0] or int(reference[0][1]) != braked):
        raise ValueError('rz_dk_se_towing_conflict')
    return {'dc_kw': 150, 'dc_quote': dc['name'], 'braked_kg': braked, 'braked_quote': braked_quote,
            'unbraked_kg': unbraked, 'unbraked_quote': unbraked_quote, 'se_maximum_present': bool(reference)}


def review(docs, swedish, swedish_hash, observed):
    model, car, tech = (docs[name] for name in NAMES)
    rows = register(model, swedish['variants'], observed)
    packet = specs_request(car, rows)
    evidence = [{**corroboration(result, variant), 'variant': variant['variant'],
                 'se_car_id': variant['car_id'], 'dk_car_id': cid, 'type_code': variant['type_code'], 'suffix': variant['suffix']}
                for result, (variant, _, _, cid) in zip(response_rows(tech, packet), rows, strict=True)]
    return {'status': 'cross_market_corroboration_only', 'captured_at': observed.isoformat(),
            'swedish_review_sha256': swedish_hash, 'reference_market': 'DK', 'sources': {
                NAMES[0]: {'url': MODEL, 'sha256': digest(model)},
                NAMES[1]: {'url': API, 'sha256': digest(car), 'request_sha256': digest(request_bytes(car_request(rows)))},
                NAMES[2]: {'url': API, 'sha256': digest(tech), 'request_sha256': digest(request_bytes(packet))}},
            'variants': evidence, 'publication_approved': False, 'database_writes': 0, 'paid_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--capture', action='store_true')
    modes.add_argument('--replay', type=Path)
    parser.add_argument('--swedish-review', required=True, type=Path)
    supplement = parser.add_mutually_exclusive_group()
    supplement.add_argument('--qualify-charging', action='store_true')
    supplement.add_argument('--replay-charging', type=Path)
    supplement.add_argument('--qualify-factory-year', action='store_true')
    supplement.add_argument('--replay-factory-year', type=Path)
    args = parser.parse_args()
    if args.capture and (args.qualify_charging or args.replay_charging or args.qualify_factory_year or args.replay_factory_year):
        parser.error('Supplemental review requires replay of a pinned Nordic packet')
    root = private_root()
    swedish_folder, swedish = replay_review(root, args.swedish_review)
    configs = json.loads(read_capture(swedish_folder, CONFIG_CAPTURE), object_pairs_hook=unique_object)
    se_cabins = [car_cabin(selection['result']['fetchResult']['car']) for selection in configs['fetches']]
    if se_cabins != [cabin_codes(edition[0]) for edition in EDITIONS]:
        raise ValueError('rz_se_nordic_default_colour_or_upholstery_changed')
    se_hash = digest(read_capture(swedish_folder, 'review.json', 100_000))
    if args.capture:
        observed = datetime.now(timezone.utc)
        if not 0 <= (observed - datetime.fromisoformat(swedish['captured_at'])).total_seconds() <= 86400:
            raise ValueError('rz_fresh_swedish_capture_required')
        model = fetch_exact(MODEL, {'Lexus'})
        rows = register(model, swedish['variants'], observed)
        car = collect_configurator(car_request(rows), API, 'da-DK,da;q=0.9')
        tech = collect_configurator(specs_request(car, rows), API, 'da-DK,da;q=0.9')
        docs = dict(zip(NAMES, (model, car, tech), strict=True))
        packet = review(docs, swedish, se_hash, observed)
        folder = Path(tempfile.mkdtemp(prefix='lexus-rz-nordic-', dir=root))
        for name, body in docs.items():
            (folder / name).write_bytes(body)
        (folder / 'review.json').write_text(json.dumps(packet, indent=2) + '\n', encoding='utf-8')
    else:
        folder = private_capture(root, args.replay, 'lexus-rz-nordic')
        saved = json.loads(read_capture(folder, 'review.json', 100_000), object_pairs_hook=unique_object)
        packet = review({name: read_capture(folder, name) for name in NAMES}, swedish, se_hash,
                        datetime.fromisoformat(saved['captured_at']))
        if packet != saved:
            raise ValueError('rz_dk_capture_or_review_changed')
    if args.qualify_charging or args.replay_charging:
        dk_hash = digest(read_capture(folder, 'review.json', 100_000))
        if args.qualify_charging:
            raw = fetch_exact(CHARGING_SHEET, {'Lexus'})
            packet = shared_charging_report(raw, swedish, packet, dk_hash, datetime.now(timezone.utc))
            folder = Path(tempfile.mkdtemp(prefix='lexus-rz-charging-', dir=root))
            (folder / 'norwegian-sheet.pdf').write_bytes(raw)
            (folder / 'review.json').write_text(json.dumps(packet, indent=2) + '\n', encoding='utf-8')
        else:
            folder = private_capture(root, args.replay_charging, 'lexus-rz-charging')
            saved = json.loads(read_capture(folder, 'review.json', 100_000), object_pairs_hook=unique_object)
            packet = shared_charging_report(read_capture(folder, 'norwegian-sheet.pdf'), swedish, packet, dk_hash,
                                           datetime.fromisoformat(saved['captured_at']))
            if packet != saved:
                raise ValueError('rz_charging_capture_or_review_changed')
    if args.qualify_factory_year or args.replay_factory_year:
        dk_hash = digest(read_capture(folder, 'review.json', 100_000))
        if args.qualify_factory_year:
            raw = fetch_exact(FACTORY_SHEET, {'Lexus'})
            packet = factory_year_report(raw, swedish, packet, dk_hash, datetime.now(timezone.utc))
            folder = Path(tempfile.mkdtemp(prefix='lexus-rz-factory-year-', dir=root))
            (folder / 'italian-sheet.pdf').write_bytes(raw)
            (folder / 'review.json').write_text(json.dumps(packet, indent=2) + '\n', encoding='utf-8')
        else:
            folder = private_capture(root, args.replay_factory_year, 'lexus-rz-factory-year')
            saved = json.loads(read_capture(folder, 'review.json', 100_000), object_pairs_hook=unique_object)
            packet = factory_year_report(read_capture(folder, 'italian-sheet.pdf'), swedish, packet, dk_hash,
                                         datetime.fromisoformat(saved['captured_at']))
            if packet != saved:
                raise ValueError('rz_factory_year_capture_or_review_changed')
    print(json.dumps({'output': str(folder / 'review.json'), 'variants': len(packet['variants']),
                      'status': packet['status'], 'publication_approved': False}))


if __name__ == '__main__':
    main()
