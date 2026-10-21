"""Private, request-bound extraction from Toyota's public Swedish configurator."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.request import Request

from audit_catalog_sources import MAX_BYTES, USER_AGENT, SourceFetcher, normalized
from discover_toyota_grades import discover, identity
from refresh_verified_variants import save
from supabase_client import SupabaseRestClient
from toyota_price_intake import HTML_URL, LOCAL, ROOT, collect_configuration, numeric, pointer_value
from validate_extracted_variants import validate_draft
from variant_refresh import FACT_FIELDS, RefreshError

RESOURCE = 'https://dxp-webcarconfig.toyota-europe.com'
API_URL = RESOURCE + '/v1/api/data/se/sv'
REVIEW_REASON = 'official_api_publication_contract_required'
REPORT = ROOT / 'data/review/toyota_configurator_intake.json'
CAR = 'fetchCarConfigCar'
MOTORIZATION = 'fetchCarConfigMotorization'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def registry_from(source, data):
    jobs = discover(source, data, [])['grades']
    common = data['commonSettings']
    if (common.get('resourcePath') != RESOURCE or common.get('apiEndpoint') != RESOURCE + '/v1/api'
            or common.get('component') != 'car-config'):
        raise RefreshError('official_configurator_endpoint_not_proven')
    return {'source': source, 'manufacturer_model_id': identity(data['car']['model']['id']),
            'version': data['car']['model']['configVersion'], 'body_id': identity(data['car']['body']['id']),
            'grades': [{key: job[key] for key in ('grade', 'manufacturer_grade_id', 'default_manufacturer_variant_id')}
                       for job in jobs if not job['selected_configuration_available']]}


def build_request(registry):
    grades = registry['grades']
    if not 1 <= len(grades) <= 5:
        raise RefreshError('bounded_grade_scope_required')
    fetches, ids, names, defaults = [], set(), set(), set()
    model_id, body_id = identity(registry['manufacturer_model_id']), identity(registry['body_id'])
    for grade in grades:
        gid, cid, name = identity(grade['manufacturer_grade_id']), identity(grade['default_manufacturer_variant_id']), grade['grade']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9 +\-]{1,50}', name):
            raise RefreshError('unsupported_grade_identity')
        if gid in ids or cid in defaults or name.casefold() in names:
            raise RefreshError('duplicate_grade_scope')
        ids.add(gid); defaults.add(cid); names.add(name.casefold())
        fetches.extend([
            {'fetchType': CAR, 'modelId': model_id, 'carId': cid, 'tyCodeConfig': None, 'isPro': False},
            {'fetchType': MOTORIZATION, 'modelId': model_id, 'bodyTypeId': body_id,
             'gradeId': gid, 'carId': cid, 'financeQuoteID': '', 'isPro': False}])
    return {'component': 'car-config', 'fetches': fetches}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RefreshError('duplicate_json_key')
        result[key] = value
    return result


def validate_request(packet):
    fetches = packet.get('fetches')
    if (set(packet) != {'component', 'fetches'} or packet['component'] != 'car-config'
            or not isinstance(fetches, list) or not 2 <= len(fetches) <= 10 or len(fetches) % 2):
        raise RefreshError('unsupported_configurator_operation')
    model_ids, body_ids, grade_ids, car_ids = set(), set(), set(), set()
    for index in range(0, len(fetches), 2):
        car, motor = fetches[index:index + 2]
        if (set(car) != {'fetchType', 'modelId', 'carId', 'tyCodeConfig', 'isPro'}
                or set(motor) != {'fetchType', 'modelId', 'bodyTypeId', 'gradeId', 'carId', 'financeQuoteID', 'isPro'}
                or car['fetchType'] != CAR or motor['fetchType'] != MOTORIZATION
                or car['tyCodeConfig'] is not None or car['isPro'] is not False or motor['isPro'] is not False
                or motor['financeQuoteID'] != '' or car['modelId'] != motor['modelId'] or car['carId'] != motor['carId']):
            raise RefreshError('unsupported_configurator_operation')
        mid, bid = identity(car['modelId']), identity(motor['bodyTypeId'])
        gid, cid = identity(motor['gradeId']), identity(car['carId'])
        if gid in grade_ids or cid in car_ids:
            raise RefreshError('duplicate_grade_scope')
        model_ids.add(mid); body_ids.add(bid); grade_ids.add(gid); car_ids.add(cid)
    if len(model_ids) != 1 or len(body_ids) != 1:
        raise RefreshError('mixed_model_or_body_request')


def request_data(packet, fetcher=None):
    validate_request(packet)
    fetcher = fetcher or SourceFetcher(timeout=20)
    if not fetcher.robots_allowed(API_URL):
        raise RefreshError('configurator_robots_denied_or_unavailable')
    # Only the two read operations assembled above are allowed; no saved cars,
    # financing, customer identifiers or arbitrary fetch types are sent.
    with fetcher.opener.open(Request(API_URL, data=encoded(packet), method='POST', headers={
            'User-Agent': USER_AGENT, 'Content-Type': 'application/json', 'Accept-Language': 'sv-SE,sv;q=0.9'}),
            timeout=fetcher.timeout) as response:
        if response.headers.get('tdm-reservation') == '1':
            raise RefreshError('configurator_machine_reservation')
        if response.status != 200 or response.headers.get_content_type() != 'application/json':
            raise RefreshError('configurator_json_response_required')
        body = fetcher.read_body(response)
        if not body or len(body) > MAX_BYTES:
            raise RefreshError('configurator_response_size')
        payload = json.loads(body.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=reject_non_finite)
    return payload, {'url': API_URL, 'source_authority': 'manufacturer', 'source_type': 'manufacturer_configurator',
                     'source_validation': 'needs_api_contract', 'brand': 'Toyota', 'model': 'bZ4X',
                     'country': 'SE', 'language': 'sv', 'http_status': 200, 'request_method': 'POST',
                     'request_hash': digest(packet), 'content_hash': hashlib.sha256(body).hexdigest(),
                     'fetched_at': datetime.now(timezone.utc).isoformat()}


def reject_non_finite(_):
    raise RefreshError('non_finite_json')


def fresh_source(source):
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(source['fetched_at'])).total_seconds()
    except (KeyError, ValueError, TypeError):
        raise RefreshError('fresh_configurator_evidence_required') from None
    if (not -60 <= age <= 900 or not re.fullmatch(r'[0-9a-f]{64}', source.get('content_hash', ''))):
        raise RefreshError('fresh_configurator_evidence_required')


def extract_packet(registry, packet, payload, source):
    fresh_source(registry['source']); fresh_source(source)
    if (registry['source'].get('url') != HTML_URL or registry['source'].get('source_authority') != 'manufacturer'
            or registry['source'].get('source_validation') != 'reachable_official_model_source'
            or registry['source'].get('brand') != 'Toyota' or registry['source'].get('model') != 'bZ4X'
            or source.get('url') != API_URL or source.get('request_method') != 'POST'
            or source.get('brand') != 'Toyota' or source.get('model') != 'bZ4X'
            or source.get('source_type') != 'manufacturer_configurator'
            or source.get('country') != 'SE' or source.get('language') != 'sv'
            or source.get('source_validation') != 'needs_api_contract'
            or source.get('source_authority') != 'manufacturer' or source.get('http_status') != 200
            or packet != build_request(registry) or source.get('request_hash') != digest(packet)):
        raise RefreshError('unbound_configurator_request')
    responses = payload.get('fetches')
    if not isinstance(responses, list) or len(responses) != len(packet['fetches']):
        raise RefreshError('incomplete_configurator_response')
    for expected, actual in zip(packet['fetches'], responses):
        if ({key: value for key, value in actual.items() if key != 'result'} != expected
                or not isinstance(actual.get('result'), dict) or actual['result'].get('errorLogs')):
            raise RefreshError('configurator_response_scope_or_error')
    rows, all_ids = [], set()
    for group, grade in enumerate(registry['grades']):
        car_index, motor_index = group * 2, group * 2 + 1
        car = responses[car_index]['result'].get('fetchResult', {}).get('car', {})
        variants = responses[motor_index]['result'].get('fetchResult')
        if (car.get('id') != grade['default_manufacturer_variant_id']
                or car.get('grade', {}).get('id') != grade['manufacturer_grade_id']
                or car.get('grade', {}).get('name') != grade['grade']
                or car.get('model', {}).get('id') != registry['manufacturer_model_id']
                or car.get('model', {}).get('configVersion') != registry['version']
                or normalized(car.get('model', {}).get('name')) != 'nya toyota bz4x'
                or car.get('body', {}).get('id') != registry['body_id']
                or not isinstance(variants, list) or not 1 <= len(variants) <= 12):
            raise RefreshError('selected_grade_model_or_body_mismatch')
        selected = [variant for variant in variants if variant.get('carId') == car['id']]
        if (len(selected) != 1 or selected[0].get('price', {}).get('cash') != car.get('price', {}).get('cash')
                or selected[0].get('engine', {}).get('id') != car.get('motorization', {}).get('engine', {}).get('id')
                or selected[0].get('engine', {}).get('name') != car.get('motorization', {}).get('engine', {}).get('name')
                or selected[0].get('wheeldrive') != car.get('motorization', {}).get('wheeldrive')):
            raise RefreshError('selected_motorization_mismatch')
        for index, variant in enumerate(variants):
            vid = identity(variant.get('carId'))
            if vid in all_ids:
                raise RefreshError('duplicate_configurator_variant_identity')
            all_ids.add(vid)
            engine, drive = variant.get('engine', {}), variant.get('wheeldrive', {})
            label = engine.get('name', '')
            match = re.fullmatch(r'Elmotor ([0-9]+) hk, batteri ([0-9]+,[0-9]+) kWh', label)
            drive_code = {('Framhjulsdrift', '2WD'): 'FWD', ('AWD', '4WD'): 'AWD',
                          ('Fyrhjulsdrift', '4WD'): 'AWD'}.get((drive.get('name'), drive.get('internalCode')))
            if (not match or engine.get('category', {}).get('code') != 'BEV'
                    or engine.get('internalFuelCode') != 'ELECTRIC' or engine.get('certification') != 2 or not drive_code):
                raise RefreshError('unsupported_configurator_engine_or_drive')
            power, battery = int(match[1]), float(match[2].replace(',', '.'))
            if not 1 <= power <= 2000 or not 5 <= battery <= 300:
                raise RefreshError('configurator_engine_out_of_range')
            row, proof = {field: None for field in FACT_FIELDS}, {}
            base = f'/fetches/{motor_index}/result/fetchResult/{index}'

            def fact(field, path, value, conversion=None):
                raw = pointer_value(payload, path)
                row[field] = value
                proof[field] = {'source_pointer': path, 'raw_value': raw, 'quote': encoded(raw).decode(),
                    'manufacturer_variant_id': vid, 'source_url': API_URL, 'source_hash': source['content_hash'],
                    'request_hash': source['request_hash'], 'conversion': conversion}

            price = variant.get('price', {})
            cash = numeric(price.get('cash'))
            if not cash.is_integer() or numeric(price.get('exclVat')) * 1.25 != cash:
                raise RefreshError('swedish_vat_price_mismatch')
            fact('price_sek', base + '/price/cash', int(cash))
            fact('battery_kwh', base + '/engine/name', battery, 'battery_from_exact_engine_label')
            fact('drivetrain', base + '/wheeldrive/internalCode', drive_code, 'manufacturer_drive_code')
            for field, code, unit in [('wltp_range_km', 'PERCOMBINED', 'km'),
                                      ('wltp_consumption_kwh_100km', 'ECCOMBINEDWLTP', 'Wh/km')]:
                specs = [(i, spec) for i, spec in enumerate(variant.get('specs', [])) if spec.get('internalCode') == code]
                if len(specs) > 1:
                    raise RefreshError('conflicting_configurator_specs')
                if not specs:
                    continue
                spec_index, spec = specs[0]
                if spec.get('certification') != 2 or spec.get('unit') != unit:
                    continue
                try:
                    value = numeric(spec.get('value'))
                except RefreshError:
                    continue
                if not value.is_integer():
                    continue
                consumption = field == 'wltp_consumption_kwh_100km'
                fact(field, f'{base}/specs/{spec_index}/value', value / 10 if consumption else int(value),
                     'Wh_per_km_to_kWh_per_100km' if consumption else None)
            row.update(brand='Toyota', model='bZ4X', variant_name=f"{grade['grade']} {drive_code} {battery:g} kWh {power} hk",
                       source_url=API_URL, source_hash=source['content_hash'], source_quote=f"{label} | {grade['grade']} | {int(cash)}",
                       extraction_confidence=0.99, validation_status='needs_review', validation_errors=[REVIEW_REASON],
                       extraction_payload={'adapter': 'toyota_public_configurator_v1', 'publication_allowed': False,
                           'manufacturer_variant_id': vid, 'manufacturer_model_id': registry['manufacturer_model_id'],
                           'manufacturer_grade_id': grade['manufacturer_grade_id'], 'model_config_version': registry['version'],
                           'discovered_from': HTML_URL, 'discovery_source_hash': registry['source']['content_hash'],
                           'request_method': 'POST', 'request_hash': source['request_hash'], 'field_evidence': proof})
            errors = validate_draft(row, {API_URL: source})
            # The source deliberately fails publication policy; retain that
            # quarantine while rejecting every independent fact-validation error.
            if 'source_not_publishable' not in errors or set(errors) - {'source_not_publishable'}:
                raise RefreshError('hard_validation_failed:' + ','.join(errors))
            rows.append(row)
    if len({row['variant_name'] for row in rows}) != len(rows):
        raise RefreshError('duplicate_configurator_variant_name')
    return rows


def sanitize_response(payload):
    def engine(value):
        result = {key: value[key] for key in ('id', 'name', 'certification', 'internalFuelCode') if key in value}
        result['category'] = {'code': value['category']['code']}
        return result

    def drive(value):
        return {key: value[key] for key in ('name', 'internalCode')}

    result = []
    for item in payload['fetches']:
        output = {key: value for key, value in item.items() if key != 'result'}
        data = item['result']['fetchResult']
        if item['fetchType'] == CAR:
            car = data['car']
            data = {'car': {'id': car['id'], 'model': {key: car['model'][key] for key in ('id', 'name', 'configVersion')},
                           'grade': {key: car['grade'][key] for key in ('id', 'name')}, 'body': {'id': car['body']['id']},
                           'price': {'cash': car['price']['cash']},
                           'motorization': {'engine': {key: car['motorization']['engine'][key] for key in ('id', 'name')},
                                            'wheeldrive': drive(car['motorization']['wheeldrive'])}}}
        else:
            data = [{'carId': variant['carId'], 'engine': engine(variant['engine']), 'wheeldrive': drive(variant['wheeldrive']),
                     'price': {key: variant['price'][key] for key in ('cash', 'exclVat')},
                     'specs': [{key: spec[key] for key in ('internalCode', 'certification', 'unit', 'value') if key in spec}
                               for spec in variant.get('specs', [])]} for variant in data]
        output['result'] = {'fetchResult': data, 'errorLogs': []}
        result.append(output)
    return {'fetches': result}


def private_write(client, table, payload, old=None, conflict=None):
    if table not in ('manufacturer_sources', 'extracted_variant_drafts'):
        raise RefreshError('private_intake_table_required')
    if old:
        payload_column = 'extracted_payload' if table == 'manufacturer_sources' else 'extraction_payload'
        query = {'id': 'eq.' + old['id'], 'updated_at': 'eq.' + old['updated_at'],
                 payload_column + '->>adapter': 'eq.toyota_public_configurator_v1'}
        if table == 'manufacturer_sources':
            query.update(extraction_status='eq.needs_review', source_validation='eq.needs_api_contract',
                         verified_at='is.null', verified_by='is.null')
        else:
            query.update(validation_status='eq.needs_review', validation_errors='eq.' + encoded([REVIEW_REASON]).decode())
        rows = client._request('PATCH', table, {**payload, 'updated_at': datetime.now(timezone.utc).isoformat()},
                               query=query, prefer='return=representation')
    else:
        rows = client._request('POST', table, payload, query={'on_conflict': conflict},
                               prefer='resolution=ignore-duplicates,return=representation')
    if len(rows or []) != 1:
        raise RefreshError('concurrent_private_intake_change')
    return rows[0]


def stage_private(client, registry, source, packet, evidence, rows):
    if evidence != sanitize_response(evidence):
        raise RefreshError('sanitized_evidence_required')
    if rows != extract_packet(registry, packet, evidence, source):
        raise RefreshError('private_rows_do_not_match_evidence')
    models = client.select('canonical_models', '*', {'brand': 'eq.Toyota', 'model': 'eq.bZ4X'})
    if (len(models) != 1 or models[0]['validation_status'] == 'rejected'
            or models[0]['brand'] != 'Toyota' or models[0]['model'] != 'bZ4X'):
        raise RefreshError('one_existing_canonical_model_required')
    model_id = models[0]['id']
    existing = client.select('manufacturer_sources', '*', {'url': 'eq.' + API_URL})
    staged = client.select('extracted_variant_drafts', '*', {'source_url': 'eq.' + API_URL})
    public = client.select('canonical_model_variants', '*', {'canonical_model_id': 'eq.' + model_id})
    incoming = {row['extraction_payload']['manufacturer_variant_id'] for row in rows}
    if any(row.get('manufacturer_variant_id') in incoming or row.get('source_url') == API_URL for row in public):
        raise RefreshError('existing_public_identity_requires_separate_refresh')
    if len(existing) > 1 or any(item.get('canonical_model_id') != model_id or item.get('verified_at') or item.get('verified_by')
            or item.get('source_validation') != 'needs_api_contract' or item.get('extraction_status') != 'needs_review'
            or (item.get('extracted_payload') or {}).get('adapter') != 'toyota_public_configurator_v1' for item in existing):
        raise RefreshError('reviewed_or_unrelated_source_must_not_be_overwritten')
    if any(item.get('validation_status') != 'needs_review' or item.get('validation_errors') != [REVIEW_REASON]
            or (item.get('extraction_payload') or {}).get('adapter') != 'toyota_public_configurator_v1'
            or item.get('canonical_model_id') != model_id for item in staged):
        raise RefreshError('reviewed_or_unrelated_draft_must_not_be_overwritten')
    names = {row['variant_name'] for row in rows}
    if any(item['variant_name'] not in names for item in staged):
        raise RefreshError('changed_source_group_requires_review')
    incoming_by_name = {row['variant_name']: row for row in rows}
    for old in staged:
        new = incoming_by_name[old['variant_name']]
        for key in ('manufacturer_variant_id', 'manufacturer_model_id', 'manufacturer_grade_id', 'model_config_version'):
            if old['extraction_payload'].get(key) != new['extraction_payload'][key]:
                raise RefreshError('private_identity_change_requires_review')
        for field in ('price_sek', 'wltp_range_km'):
            if old.get(field) and new.get(field) and abs(new[field] / old[field] - 1) > 0.15:
                raise RefreshError('large_staging_change_requires_review')
    stored = private_write(client, 'manufacturer_sources', {
        'canonical_model_id': model_id, 'brand': 'Toyota', 'model': 'bZ4X', 'source_type': 'manufacturer_configurator',
        'url': API_URL, 'country': 'SE', 'language': 'sv', 'fetched_at': source['fetched_at'],
        'content_hash': source['content_hash'], 'http_status': 200, 'final_url': API_URL,
        'source_validation': 'needs_api_contract', 'source_authority': 'manufacturer', 'source_name': 'Toyota Sverige',
        'extraction_status': 'needs_review', 'validation_errors': [REVIEW_REASON], 'extraction_confidence': 0.99,
        'extracted_payload': {'adapter': 'toyota_public_configurator_v1', 'publication_allowed': False,
                              'registry': registry, 'request': packet, 'request_hash': source['request_hash'], 'evidence_document': evidence}},
        old=existing[0] if existing else None, conflict='url')
    by_name = {item['variant_name']: item for item in staged}
    for row in rows:
        private_write(client, 'extracted_variant_drafts', {**row, 'source_id': stored['id'], 'canonical_model_id': model_id},
                      old=by_name.get(row['variant_name']), conflict='source_url,variant_name')
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', action='store_true')
    args = parser.parse_args()
    source, data = collect_configuration()
    registry = registry_from(source, data)
    packet = build_request(registry)
    payload, api_source = request_data(packet)
    rows = extract_packet(registry, packet, payload, api_source)
    evidence = sanitize_response(payload)
    for row in rows:
        for proof in row['extraction_payload']['field_evidence'].values():
            if pointer_value(evidence, proof['source_pointer']) != proof['raw_value']:
                raise RefreshError('sanitized_evidence_pointer_mismatch')
    save(LOCAL / 'configurator-evidence.json', {'registry': registry, 'request': packet,
                                               'source': api_source, 'response': evidence})
    save(LOCAL / 'configurator-drafts.json', rows)
    staged = stage_private(SupabaseRestClient(), registry, api_source, packet, evidence, rows) if args.stage else 0
    report = {'checked_at': api_source['fetched_at'], 'source_url': API_URL, 'source_hash': api_source['content_hash'],
              'request_method': 'POST',
              'discovered_from': HTML_URL, 'discovery_source_hash': source['content_hash'],
              'request_hash': api_source['request_hash'], 'status': 'needs_review', 'reason': REVIEW_REASON,
              'candidates': [{key: row[key] for key in ('variant_name', 'price_sek', 'wltp_range_km', 'battery_kwh', 'drivetrain')}
                             for row in rows], 'extracted': len(rows), 'staged': staged, 'published': 0,
              'canonical_writes': False, 'remote_writes': args.stage, 'openai_calls': 0}
    save(REPORT, report)
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        reason = str(error) if isinstance(error, RefreshError) else 'source_or_storage_error'
        previous = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'published': 0}
        previous['last_attempt'] = {'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'quarantined', 'reason': reason}
        save(REPORT, previous)
        print('Toyota configurator intake stopped safely: ' + reason)
        raise SystemExit(1)
