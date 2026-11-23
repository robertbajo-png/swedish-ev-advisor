"""Capture and replay the Swedish Lexus RZ's exact grade/engine evidence, privately."""

import argparse
import hashlib
import io
import json
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote
from urllib.request import Request

from PIL import Image
from pypdf import PdfReader

from audit_catalog_sources import ROOT, USER_AGENT, SourceFetcher
from discover_licensed_images import image_url
from manufacturer_embedded_data import ScriptData, unique_object
from variant_refresh import parse_document

MODEL = 'https://www.lexus.se/new-cars/rz'
SPECS = MODEL + '/specifications'
PRICE = ('https://www.lexus.se/content/dam/lexus/nmsc/sweden/documents/pris-och-utrustningslista/'
         'LSW_Pricelist_RZ_210x271_Q1-26_260318.pdf')
CONTENT = '/content/lexus/sweden/sv/new-cars/rz'
GRID = CONTENT + '/jcr:content/root/responsivegrid-top/'
MODEL_ID = 'd8ec0864-e0cb-4f08-9e8a-1261ee3b2d22'
BODY_ID = '4045302a-5701-44a0-bceb-a160f390a68b'
CONFIG_ORIGIN = 'https://dxp-webcarconfig.lexus-europe.com'
CONFIG_API = CONFIG_ORIGIN + '/v1/api/data/se/sv'
CONFIG_CAPTURE = 'selected-configurations.json'
SPECS_CAPTURE = 'selected-technical-specs.json'
AC_EQUIPMENT = '22kW (3-fas) AC-snabbladdare med Typ 2/Mennekes-kontakt'
LIMIT = 12_000_000
SOURCES = {'model.html': MODEL, 'price.pdf': PRICE, 'specs.html': SPECS}
PHOTO_TITLE = 'File:Lexus RZ 550e (XEBM25) IMG 5164.jpg'
PHOTO_PAGE = 'https://commons.wikimedia.org/wiki/File:Lexus_RZ_550e_(XEBM25)_IMG_5164.jpg'
PHOTO_PATH = 'https://upload.wikimedia.org/wikipedia/commons/6/6a/Lexus_RZ_550e_(XEBM25)_IMG_5164.jpg'
PHOTO_LICENSE = 'https://creativecommons.org/licenses/by-sa/4.0/'
PHOTO_SHA1 = '7b069c95bcf7fc146fb77e239852f569a2f06384'
EDITIONS = (
    ('350e', 'Executive', 'ex-rz 350e', '2XM-2EL-1AT2WD', 'FWD', 'XEBM20L-AWDCSW', 'AB',
     'd032f909-69f8-45ea-bc22-7c6161ca2105'),
    ('500e', 'Executive', 'ex-rz 500e', '2XM-2EL11AT4WD', 'AWD', 'XEBM25L-AWDCSW', 'PB',
     '3f19b266-d5b1-46e1-8bd9-e22a253f8474'),
    ('550e', 'F SPORT', 'fs-rz 550e', '2XM-2EL21AT4WD', 'AWD', 'XEBM25L-AWDSSW', '0C',
     'ad4ac264-f4de-43c8-93fc-e7999de39e58'),
)
FIELDS = {
    'wltp_range_km': ('evrange', 'PERCOMBINED', 'km', 'WLTP', 50, 1200),
    'wltp_consumption_kwh_100km': ('eleccomsum', 'ECCOMBINEDKWH100KM', 'kWh/100km', 'WLTP', 5, 60),
    'battery_kwh': ('charging', 'BATCAP', 'kWh', None, 5, 300),
    'seats': ('intdim', 'NRSEAT', 's\u00e4ten', None, 1, 9),
    'boot_liters': ('loadcap', 'Luggage capacity (up to tonneau cover) l', 'l', None, 50, 3500),
}


def only(rows, reason):
    rows = list(rows)
    if len(rows) != 1:
        raise ValueError(reason)
    return rows[0]


def get_one(rows, key, value):
    return only((row for row in rows if row.get(key) == value), f'rz_unique_{key}_required: {value}')


def digest(body):
    return hashlib.sha256(body).hexdigest()


def price_columns(text):
    rows = [re.split(r'\s{2,}', line.strip()) for line in text.splitlines() if line.strip()]
    header = ['UTRUSTNINGSNIV\u00c5', 'RZ 350e', 'RZ 500e', 'RZ 550e']
    if rows.count(header) != 1 or rows.count(['SEK inkl. moms']) != 1 or ['TILLVAL'] not in rows:
        raise ValueError('rz_exact_swedish_price_columns_required')
    first, stop = rows.index(header), rows.index(['TILLVAL'])
    if not first < rows.index(['SEK inkl. moms']) < stop:
        raise ValueError('rz_vat_scope_not_bound_to_columns')
    prices = {}
    for index, (motor, grade, *_) in enumerate(EDITIONS, 1):
        row = only((r for r in rows[first:stop] if r[0] == grade), 'rz_exact_trim_price_required')
        if len(row) != 4 or not re.fullmatch(r'[1-9]\d{2} \d{3}', row[index]):
            raise ValueError('rz_cash_amount_missing_or_shifted')
        prices[motor] = (int(row[index].replace(' ', '')), ' | '.join(row), ' | '.join(header))
    return prices


def price_pdf(body):
    if not body.startswith(b'%PDF-'):
        raise ValueError('rz_swedish_pdf_required')
    pages = PdfReader(io.BytesIO(body)).pages
    if len(pages) != 3:
        raise ValueError('rz_price_document_changed')
    return price_columns(pages[1].extract_text(extraction_mode='layout') or '')


def canonical_document(body, url, language='sv'):
    doc = parse_document(body, 'text/html')
    if ([x.attrs.get('href') for x in doc.nodes('link') if x.attrs.get('rel') == 'canonical'] != [url]
            or [x.attrs.get('lang') for x in doc.nodes('html')] != [language]):
        raise ValueError('rz_exact_swedish_document_required')
    return doc


def published_components(body, *, country='se', language='sv', content=CONTENT,
                         names=('powertraincomparison', 'cargrid')):
    parser = ScriptData()
    parser.feed(body.decode('utf-8'))
    scripts = [(a.get('id'), text) for a, text in zip(parser.script_attrs, parser.scripts, strict=True)
               if a.get('type') == 'application/json']
    context = json.loads(only((text for id_, text in scripts if id_ == 'server-data-manifest'), 'rz_manifest_required'),
                         object_pairs_hook=unique_object)['appContext']
    exact = {'brand': 'lexus', 'country': country, 'locale': language, 'page': content, 'runmode': 'publish', 'preview': False}
    if any(context.get(k) != v for k, v in exact.items()):
        raise ValueError('rz_market_or_publication_context_changed')
    components = {}
    for name in names:
        key = content + '/jcr:content/root/responsivegrid-top/' + name
        objects = (json.loads(text, object_pairs_hook=unique_object) for id_, text in scripts
                   if id_ and id_.startswith('payload-') and json.dumps(key)[1:-1] in text)
        components[name] = only((p['preload'][key]['data'] for p in objects if key in p.get('preload', {})),
                                f'rz_exact_component_required: {name}')
    return components


def field_rows(engine):
    result = {}
    for field, (category, code, unit, cycle, minimum, maximum) in FIELDS.items():
        spec = get_one(engine['specs'], 'id', category)
        item = get_one(spec['items'], 'code', code)
        shown = item.get('value')
        pattern = r'\d{1,4}(?:[.,]\d{1,2})?' if field == 'wltp_consumption_kwh_100km' else r'\d{1,4}'
        if (item.get('unit') != unit or (cycle and item.get('certification') != cycle)
                or not isinstance(shown, str) or not re.fullmatch(pattern, shown)):
            raise ValueError(f'rz_technical_unit_or_cycle_changed: {field}')
        value = float(shown.replace(',', '.')) if field == 'wltp_consumption_kwh_100km' else int(shown)
        if not minimum <= value <= maximum:
            raise ValueError(f'rz_technical_value_out_of_range: {field}')
        result[field] = (value, f'{code}: {shown} {unit}')
    return result


def detail_state(body):
    doc = canonical_document(body, SPECS)
    states = (json.loads(''.join(n.children), object_pairs_hook=unique_object) for n in doc.nodes('div')
              if n.attrs.get('data-cpdqm') == 'ignore' and n.attrs.get('id', '').endswith('-data'))
    return only((s for s in states if 'car' in s and 'specs' in s), 'rz_exact_detail_state_required')


def technical_field_rows(groups):
    return field_rows({'specs': [
        {'id': group['internalCode'].lower(), 'items': [
            {**r, 'code': r['internalCode'], 'certification': 'WLTP' if r['certification'] == 2 else None}
            for r in group['data']]} for group in groups
    ]})


def single_detail(body, configuration):
    detail = detail_state(body)
    settings, car = detail['commonSettings'], detail['car']
    if (tuple(settings.get(k) for k in ('brand', 'country', 'language', 'component')) != ('lexus', 'se', 'sv', 'car-config')
            or (car.get('id'), car.get('name'), car.get('certification')) != (configuration['car_id'], 'RZ 350e FWD EXECUTIVE', 2)
            or car['model']['id'] != MODEL_ID or car['grade']['name'] != 'Executive' or car.get('soldOut') is not False
            or car['price']['cash'] != configuration['facts']['price_sek']['value'] or car['price']['promotions']):
        raise ValueError('rz_detail_does_not_match_350e_cash_configuration')
    wheel = car['wheel']
    if wheel.get('standard') is not True or wheel['price']['cash'] != 0 or not wheel['name'].startswith('18" '):
        raise ValueError('rz_standard_350e_wheels_changed')
    tow = get_one(detail['specs']['standardEquipment'], 'code', 'fd19fbd3')
    if tow.get('standard') is not True or tow.get('name') != 'Dragvikt, max 750kg':
        raise ValueError('rz_350e_towing_wording_changed')
    values = technical_field_rows(detail['specs']['techSpecs'])
    if any(value != configuration['facts'][field]['value'] for field, (value, _) in values.items()):
        raise ValueError('rz_350e_standard_configuration_technical_conflict')
    source_hash = digest(body)
    result = {'source_url': SPECS, 'source_hash': source_hash, 'car_id': car['id'], 'standard_wheels': wheel['name'],
              'confirmed_technical_rows': {field: label for field, (_, label) in values.items()},
              'tow_limit_reference': tow['name'], 'scope': '350e base configuration; not explicit braked rating'}
    chargers = [row for row in detail['specs']['standardEquipment'] if row.get('code') == 'a4918819']
    if chargers:
        charger = only(chargers, 'rz_exact_standard_ac_charger_required')
        if charger.get('standard') is not True or charger.get('name') != AC_EQUIPMENT:
            raise ValueError('rz_350e_standard_ac_charger_changed')
        result['ac_charge_kw'] = {'value': 22, 'source_url': SPECS, 'source_hash': source_hash,
                                 'source_quote': charger['name'], 'car_id': car['id']}
    return result


def configuration_request(detail):
    settings = detail_state(detail)['commonSettings']
    expected = {'resourcePath': CONFIG_ORIGIN, 'apiEndpoint': CONFIG_ORIGIN + '/v1/api',
                'country': 'se', 'language': 'sv', 'brand': 'lexus', 'component': 'car-config'}
    if any(settings.get(k) != v for k, v in expected.items()):
        raise ValueError('rz_exact_public_configurator_endpoint_required')
    return {'component': 'car-config', 'fetches': [
        {'fetchType': 'fetchCarConfigCar', 'modelId': MODEL_ID, 'carId': edition[-1],
         'tyCodeConfig': None, 'isPro': False} for edition in EDITIONS
    ]}


def request_bytes(packet):
    return json.dumps(packet, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()


def collect_configurations(detail):
    return collect_configurator(configuration_request(detail))


def collect_configurator(packet, url=CONFIG_API, language='sv-SE,sv;q=0.9'):
    fetcher = SourceFetcher(timeout=20)
    if not fetcher.robots_allowed(url):
        raise ValueError('rz_configurator_robots_denied_or_unavailable')
    # Call only the public read operations built from the registered factory IDs.
    request = Request(url, data=request_bytes(packet), method='POST',
                      headers={'User-Agent': USER_AGENT, 'Content-Type': 'application/json',
                               'Accept-Language': language})
    with fetcher.opener.open(request, timeout=fetcher.timeout) as response:
        if (response.status != 200 or response.geturl() != url
                or response.headers.get('tdm-reservation') == '1'
                or response.headers.get_content_type() != 'application/json'):
            raise ValueError('rz_configurator_response_not_available_for_review')
        content = fetcher.read_body(response)
    if not 0 < len(content) <= LIMIT:
        raise ValueError('rz_configurator_response_size')
    return content


def match_configurations(raw, detail, variants):
    packet = configuration_request(detail)
    return configuration_facts(json.loads(raw, object_pairs_hook=unique_object), packet, variants, digest(raw))


def configuration_facts(payload, packet, variants, source_hash):
    responses = payload.get('fetches')
    if not isinstance(responses, list) or len(responses) != len(EDITIONS) or len(variants) != len(EDITIONS):
        raise ValueError('rz_exact_three_configurator_responses_required')
    result = {}
    for expected, actual, edition, variant in zip(packet['fetches'], responses, EDITIONS, variants, strict=True):
        motor, grade, _code, _engine, drive, _type, _suffix, car_id = edition
        if {key: val for key, val in actual.items() if key != 'result'} != expected or actual['result'].get('errorLogs') != []:
            raise ValueError('rz_configurator_response_identity_mismatch')
        car = actual['result']['fetchResult']['car']
        label = f'RZ {motor} {drive} {grade.upper()}'
        price = variant['facts']['price_sek']['value']
        if ((car.get('id'), car.get('name'), car.get('certification')) != (car_id, label, 2)
                or (variant.get('car_id'), variant.get('variant')) != (car_id, f'{motor} {grade}')
                or car['model']['id'] != MODEL_ID or car['body']['id'] != BODY_ID
                or car['grade']['name'] != grade or car.get('soldOut') is not False
                or car['price']['cash'] != price or car['price'].get('promotions')):
            raise ValueError('rz_configurator_does_not_match_swedish_price_and_engine')
        wheel = car['wheel']
        inches = 20 if motor == '550e' else 18
        if wheel.get('standard') is not True or wheel['price']['cash'] != 0 or not wheel['name'].startswith(f'{inches}" '):
            raise ValueError('rz_configurator_standard_wheel_scope_changed')
        result[variant['variant']] = {'source_url': CONFIG_API, 'source_hash': source_hash,
            'request_hash': digest(request_bytes(packet)), 'source_method': 'POST',
            'car_id': car_id, 'model_id': MODEL_ID, 'configuration_version': car['model']['configVersion'],
            'standard_wheels_inches': inches, 'source_quote': wheel['name'], 'cash_sek': price,
            'scope': 'exact Swedish base configuration; no model year or availability inferred'}
    return result


def technical_operation(car, *, allow_colour_surcharge=False):
    colour, upholstery = car['colour'], car['upholstery']
    if (car['model']['id'] != MODEL_ID or car['model']['internalCode'] != 'rz' or car.get('certification') != 2
            or car['motorization']['engine']['category']['code'] != 'BEV'
            or type(car['shortId']) is not int or not 1 <= car['shortId'] <= 999999
            or (not allow_colour_surcharge and colour['price']['cash'] != 0)
            or upholstery['price']['cash'] != 0
            or any(not re.fullmatch(r'[A-Z0-9]{2,8}', item['internalCode']) for item in (colour, upholstery))):
        raise ValueError('rz_technical_request_base_configuration_required')
    return {'fetchType': 'fetchCarConfigSpecs', 'body': {
        'model': MODEL_ID, 'car': car['id'], 'modelCode': 'rz', 'certification': 2, 'ecoTag': 'electric',
        'carShortId': car['shortId'], 'colourCode': colour['internalCode'], 'upholsteryCode': upholstery['internalCode'],
        'packs': [], 'serviceProducts': [], 'options': [], 'accessories': []}}


def technical_request(configurations, detail, variants):
    packet = configuration_request(detail)
    payload = json.loads(configurations, object_pairs_hook=unique_object)
    configuration_facts(payload, packet, variants, digest(configurations))
    return {'component': 'car-config', 'fetches': [
        technical_operation(row['result']['fetchResult']['car']) for row in payload['fetches']]}


def technical_facts(raw, packet, variants):
    responses = json.loads(raw, object_pairs_hook=unique_object).get('fetches')
    if not isinstance(responses, list) or len(responses) != len(EDITIONS):
        raise ValueError('rz_exact_three_technical_responses_required')
    source = {'source_url': CONFIG_API, 'source_hash': digest(raw),
              'request_hash': digest(request_bytes(packet)), 'source_method': 'POST'}
    reports = {}
    for expected, response, variant in zip(packet['fetches'], responses, variants, strict=True):
        if {key: val for key, val in response.items() if key != 'result'} != expected:
            raise ValueError('rz_technical_response_identity_mismatch')
        result = response['result']
        data = result.get('fetchResult')
        if (not isinstance(data, dict) or result.get('errorLogs') not in (None, [])
                or result.get('responseStatus') not in (None, 200)
                or data.get('massValidationSpecs') != {'error': None, 'exceedingKilogram': 0, 'successful': True}):
            raise ValueError('rz_technical_configuration_validation_failed')
        for field, (value, _) in technical_field_rows(data['techSpecs']).items():
            if value != variant['facts'][field]['value']:
                raise ValueError(f'rz_technical_variant_conflict: {field}')
        equipment = data['standardEquipment']
        ac = get_one(equipment, 'code', 'a4918819')
        if ac.get('standard') is not True or ac.get('name') != AC_EQUIPMENT:
            raise ValueError('rz_technical_standard_ac_charger_changed')
        exact_source = {**source, 'car_id': variant['car_id']}
        # A generic maximum is not a braked rating; missing is not zero.
        tow = [row['name'] for row in equipment if row.get('standard') is True
               and isinstance(row.get('name'), str) and re.match(r'^Dragvikt\b', row['name'])]
        reports[variant['variant']] = {**exact_source, 'scope': 'exact Swedish base configuration',
            'ac_charge_kw': {**exact_source, 'source_quote': ac['name'], 'value': 22},
            'tow_limit_references': tow}
    return reports, {**source, 'scope': 'read-only public technical specs; no optional equipment'}


def review(model, prices, details, captured, configurations=None, technical=None):
    doc = canonical_document(model, MODEL)
    if [n.text() for n in doc.nodes('h1')] != ['RZ'] or PRICE not in {n.attrs.get('href') for n in doc.nodes('a')}:
        raise ValueError('rz_current_product_and_price_link_required')
    components = published_components(model)
    grades = components['powertraincomparison']['gradesData']
    visual = get_one(components['cargrid']['visuals']['models'], 'id', MODEL_ID)
    if ((grades['code'], grades['name'], grades['certification'], visual['name'], visual['code'])
            != ('rz', 'RZ', 'WLTP', 'RZ', 'RZ')):
        raise ValueError('rz_facelift_grade_table_required')
    updated = datetime.fromisoformat(grades['_date'])
    age = (captured - updated).total_seconds()
    if not -60 <= age <= 7 * 86400:
        raise ValueError('rz_current_manufacturer_data_required')
    prices_by_motor = price_pdf(prices)
    variants = []
    for motor, grade, code, etw, drive, type_code, suffix, car_id in EDITIONS:
        row = get_one(grades['grades'], 'code', code)
        body = get_one(row['bodyTypes'], 'code', 'ac4')
        engine = get_one(body['engines'], 'etwCode', etw)
        case = get_one(visual['cars'], 'id', car_id)
        power = get_one(grades['wheeldrives'], 'code', engine['wheeldrive'])['name']
        drive_row = get_one(get_one(engine['specs'], 'id', 'trans')['items'], 'code', 'Drive')
        price = engine['minPrice']
        config = price['config']
        identity = config['PSLS']['Suffix']
        name = f'RZ {motor} {drive} {grade.upper()}'
        if (row['name'] != grade or body['name'] != 'SUV 5-d' or case['name'] != name or power != drive or drive_row['value'] != drive
                or get_one(grades['fuelTypes'], 'id', engine['fuel'])['name'] != 'El' or engine.get('seoIndex') is not True
                or tuple(config.get(k) for k in ('Country', 'Brand', 'Language', 'ModelID', 'CarID')) != ('se', 'lexus', 'sv', MODEL_ID, car_id)
                or (identity.get('Katashiki'), identity.get('Code')) != (type_code, suffix)
                or not date.fromisoformat(identity['AvailableFromDate'][:10]) <= captured.date() < date.fromisoformat(identity['AvailableToDate'][:10])):
            raise ValueError('rz_exact_current_engine_and_swedish_configuration_required')
        amount, quote, columns = prices_by_motor[motor]
        if (type(price['listWithDiscount']) is not int or price['listWithDiscount'] != amount or config['TotalPrice'] != amount
                or price['netWithDiscount'] + price['taxWithDiscount'] != amount):
            raise ValueError('rz_current_engine_cash_price_disagrees_with_pdf')

        def proof(value, label, url=MODEL, raw=model, **scope):
            return {'value': value, 'source_url': url, 'source_hash': digest(raw), 'source_quote': label, 'car_id': car_id, **scope}

        fields = {key: proof(value, label) for key, (value, label) in field_rows(engine).items()}
        fields['drivetrain'] = proof(drive, f'Drive: {drive}')
        fields['price_sek'] = proof(amount, quote, PRICE, prices, price_type='list_price', columns=columns,
                                    corroboration=proof(amount, f'{name} | minPrice.config.TotalPrice: {amount} SEK'))
        variants.append({'variant': f'{motor} {grade}', 'car_id': car_id, 'engine_code': etw,
                         'type_code': type_code, 'suffix': suffix, 'body_type': 'SUV', 'facts': fields,
                         'held': ['model_year', 'ac_charge_kw', 'dc_charge_kw', 'tow_kg', 'complete_wheel_scope']})
    single = single_detail(details, variants[0])
    variants[0]['held'].remove('complete_wheel_scope')
    if 'ac_charge_kw' in single:
        variants[0]['facts']['ac_charge_kw'] = single['ac_charge_kw']
        variants[0]['held'].remove('ac_charge_kw')
    result = {'status': 'review_complete_held', 'captured_at': captured.isoformat(), 'manufacturer_data_date': updated.isoformat(),
            'model': 'Lexus RZ', 'market': 'SE', 'variants': variants, 'single_configuration': single,
            'sources': {name: {'source_url': url, 'source_hash': digest(raw)}
                        for (name, url), raw in zip(SOURCES.items(), (model, prices, details), strict=True)},
            'publication_approved': False, 'database_writes': 0, 'paid_calls': 0}
    if configurations is not None:
        config = match_configurations(configurations, details, variants)
        for variant in variants:
            if 'complete_wheel_scope' in variant['held']:
                variant['held'].remove('complete_wheel_scope')
            variant['standard_configuration'] = config[variant['variant']]
        result['sources'][CONFIG_CAPTURE] = {'source_url': CONFIG_API,
            'source_hash': digest(configurations), 'request_hash': digest(request_bytes(configuration_request(details))),
            'source_method': 'POST', 'scope': 'read-only public selected configuration'}
    if technical is not None:
        if configurations is None:
            raise ValueError('rz_technical_specs_require_exact_configurations')
        selected, source = technical_facts(technical, technical_request(configurations, details, variants), variants)
        for variant in variants:
            evidence = selected[variant['variant']]
            variant['technical_configuration'] = evidence
            variant['facts']['ac_charge_kw'] = evidence['ac_charge_kw']
            if 'ac_charge_kw' in variant['held']:
                variant['held'].remove('ac_charge_kw')
        result['sources'][SPECS_CAPTURE] = source
    return result


def fetch_exact(url, brand):
    result = SourceFetcher(timeout=20, max_bytes=LIMIT, url_policy=lambda u, brands: u == url and brands == brand,
                           text_parser=lambda *_: '', document_parser=lambda body, _: body).fetch(url, brand)
    if result['status'] != 'reachable' or result.get('http_status') != 200 or result.get('final_url') != url:
        raise ValueError(f'rz_source_unavailable: {result["status"]}, {url}')
    return result['document']


def photo_url(metadata):
    doc = parse_document(metadata, 'text/html')
    title = only((n.text() for n in doc.nodes('h1')), 'rz_commons_title_required')
    author = only((n.parent.text() for n in doc.nodes('td') if n.attrs.get('id') == 'fileinfotpl_aut'), 'rz_commons_author_required')
    links = {n.attrs.get('href') for n in doc.nodes('a')}
    if (re.sub(r'^File\s*:\s*', 'File:', title) != PHOTO_TITLE or author != 'Author Alexander Migl'
            or not ({PHOTO_LICENSE, PHOTO_LICENSE + 'deed.en'} & links)
            or 'Attribution-Share Alike 4.0 International' not in doc.text()):
        raise ValueError('rz_commons_photo_identity_or_terms_changed')
    asset = image_url(only({n.attrs.get('href') for n in doc.nodes('a') if n.text() == 'Original file'}, 'rz_commons_asset_required'))
    if unquote(asset) != PHOTO_PATH:
        raise ValueError('rz_commons_exact_photo_required')
    return asset


def capture_photo(root):
    metadata = fetch_exact(PHOTO_PAGE, set())
    asset = photo_url(metadata)
    body = fetch_exact(asset, set())
    if hashlib.sha1(body).hexdigest() != PHOTO_SHA1:
        raise ValueError('rz_commons_file_revision_changed')
    with Image.open(io.BytesIO(body)) as photo:
        if photo.format != 'JPEG' or photo.size != (4410, 2584):
            raise ValueError('rz_commons_exact_image_dimensions_required')
        photo.verify()
    folder = Path(tempfile.mkdtemp(prefix='lexus-rz-photo-', dir=root))
    (folder / 'original.jpg').write_bytes(body)
    (folder / 'commons.html').write_bytes(metadata)
    candidate = {'status': 'candidate_not_reviewed', 'model_key': 'lexus|rz', 'depicts': 'Lexus RZ 550e F SPORT (XEBM25)',
                 'source_url': PHOTO_PAGE, 'asset_url': asset, 'author': 'Alexander Migl', 'license_id': 'CC-BY-SA-4.0',
                 'license_url': PHOTO_LICENSE, 'content_sha256': digest(body), 'metadata_sha256': digest(metadata),
                 'width': 4410, 'height': 2584, 'file': 'original.jpg', 'publication_approved': False}
    (folder / 'candidate.json').write_text(json.dumps(candidate, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(folder / 'candidate.json'), 'publication_approved': False}))


def private_root():
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    if root != ROOT.resolve() / 'data/local/release-data' or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', x, re.I) for x in root.parts):
        raise ValueError('rz_private_release_directory_required')
    return root


def private_capture(root, path, prefix):
    folder = path.resolve(strict=True)
    if folder != path.absolute() or folder.parent != root or not re.fullmatch(prefix + r'-[a-z0-9_]+', folder.name):
        raise ValueError('rz_private_capture_required')
    return folder


def read_capture(folder, name, limit=LIMIT):
    file = folder / name
    if file.resolve(strict=True) != file or not file.is_file() or not 0 < file.stat().st_size <= limit:
        raise ValueError('rz_invalid_capture_file')
    return file.read_bytes()


def replay_review(root, path):
    folder = private_capture(root, path, 'lexus-rz-review')
    saved = json.loads(read_capture(folder, 'review.json', 100_000), object_pairs_hook=unique_object)
    configuration = read_capture(folder, CONFIG_CAPTURE) if CONFIG_CAPTURE in saved['sources'] else None
    technical = read_capture(folder, SPECS_CAPTURE) if SPECS_CAPTURE in saved['sources'] else None
    report = review(*(read_capture(folder, name) for name in SOURCES), datetime.fromisoformat(saved['captured_at']), configuration, technical)
    if saved != report:
        raise ValueError('rz_capture_or_review_changed')
    return folder, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    mode.add_argument('--photo', action='store_true')
    parser.add_argument('--with-configurations', action='store_true', help='Also collect the three selected Swedish configurations')
    parser.add_argument('--with-technical-specs', action='store_true', help='Read exact technical specs for all three configurations')
    args = parser.parse_args()
    if (args.with_configurations or args.with_technical_specs) and not args.capture:
        parser.error('Live source options require --capture')
    root = private_root()
    if args.photo:
        capture_photo(root)
        return
    if args.capture:
        docs = {name: fetch_exact(url, {'Lexus'}) for name, url in SOURCES.items()}
        captured = datetime.now(timezone.utc)
        configuration = collect_configurations(docs['specs.html']) if args.with_configurations or args.with_technical_specs else None
        report = review(*docs.values(), captured, configuration)
        if args.with_technical_specs:
            packet = technical_request(configuration, docs['specs.html'], report['variants'])
            technical = collect_configurator(packet)
            report = review(*docs.values(), captured, configuration, technical)
            docs[SPECS_CAPTURE] = technical
        if configuration is not None:
            docs[CONFIG_CAPTURE] = configuration
        folder = Path(tempfile.mkdtemp(prefix='lexus-rz-review-', dir=root))
        for name, body in docs.items():
            (folder / name).write_bytes(body)
        (folder / 'review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    else:
        folder, report = replay_review(root, args.replay)
    print(json.dumps({'output': str(folder / 'review.json'), 'variants': len(report['variants']), 'publication_approved': False}))


if __name__ == '__main__':
    main()
