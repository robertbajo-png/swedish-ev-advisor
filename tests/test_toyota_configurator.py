import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_toyota_grade_discovery import inputs, OTHER_GRADE
from toyota_configurator_intake import (API_URL, RESOURCE, CAR, MOTORIZATION, REVIEW_REASON,
    build_request, registry_from, digest, encoded, extract_packet, request_data, sanitize_response, stage_private)
from toyota_price_intake import pointer_value
from source_policy import source_is_publishable
from variant_refresh import RefreshError


def fixture():
    source, data, _ = inputs()
    data['commonSettings'].update(resourcePath=RESOURCE, apiEndpoint=RESOURCE + '/v1/api', component='car-config')
    data['car']['body'] = {'id': 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'}
    data['grades']['items'].append({'id': 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', 'name': 'Executive',
                                  'defaultCarId': '33333333-3333-4333-8333-333333333333'})
    registry = registry_from(source, data)
    packet = build_request(registry)
    responses = []
    for group, grade in enumerate(registry['grades']):
        car_request, motor_request = packet['fetches'][group * 2:group * 2 + 2]
        variants = []
        for index in range(2):
            variant = copy.deepcopy(data['carConfigMotorization']['motorization'][0])
            variant['carId'] = grade['default_manufacturer_variant_id'] if not index else (
                '44444444-4444-4444-8444-444444444444' if not group else '55555555-5555-4555-8555-555555555555')
            variant['engine']['name'] = f"Elmotor {224 if not index else 343} hk, batteri 73,1 kWh"
            variant['wheeldrive'] = {'name': 'Framhjulsdrift' if not index else 'AWD', 'internalCode': '2WD' if not index else '4WD'}
            cash = 510000 + group * 50000 + index * 25000
            variant['price'].update(cash=cash, exclVat=cash / 1.25)
            if group:
                variant['specs'][0]['value'] = '450 - 500'
            variant['finance'] = {'disclaimer': 'not-price-evidence'}
            variants.append(variant)
        car = {'id': grade['default_manufacturer_variant_id'], 'model': copy.deepcopy(data['car']['model']),
               'grade': {'id': grade['manufacturer_grade_id'], 'name': grade['grade']},
               'body': copy.deepcopy(data['car']['body']), 'price': copy.deepcopy(variants[0]['price']),
               'motorization': {'engine': copy.deepcopy(variants[0]['engine']), 'wheeldrive': copy.deepcopy(variants[0]['wheeldrive'])}}
        for request, result in [(car_request, {'car': car}), (motor_request, variants)]:
            responses.append({**request, 'result': {'fetchResult': result, 'reqLogs': ['private-server-log'], 'errorLogs': []}})
    payload = {'fetches': responses, 'requestLog': 'do-not-store'}
    api_source = {'url': API_URL, 'source_type': 'manufacturer_configurator', 'source_validation': 'needs_api_contract',
                  'source_authority': 'manufacturer', 'brand': 'Toyota', 'model': 'bZ4X', 'country': 'SE', 'language': 'sv',
                  'http_status': 200, 'request_method': 'POST', 'request_hash': digest(packet), 'content_hash': digest(payload),
                  'fetched_at': datetime.now(timezone.utc).isoformat()}
    return registry, packet, payload, api_source


class Client:
    def __init__(self):
        self.sources, self.drafts, self.canonical, self.calls = [], [], [], []
        self.race = False

    def select(self, table, *_):
        if table == 'canonical_models': return [{'id': 'model', 'brand': 'Toyota', 'model': 'bZ4X', 'validation_status': 'published'}]
        return copy.deepcopy({'manufacturer_sources': self.sources, 'extracted_variant_drafts': self.drafts,
                              'canonical_model_variants': self.canonical}[table])

    def _request(self, method, table, payload, query, prefer):
        self.calls.append((method, table, copy.deepcopy(payload), query, prefer))
        assert table in ('manufacturer_sources', 'extracted_variant_drafts')
        target = self.sources if table == 'manufacturer_sources' else self.drafts
        if method == 'POST':
            assert prefer == 'resolution=ignore-duplicates,return=representation'
            assert 'on_conflict' in query
            if self.race: return []
            row = {**copy.deepcopy(payload), 'id': f'{table}-{len(target)}', 'updated_at': 'before'}
            target.append(row)
        else:
            assert method == 'PATCH'
            assert query['updated_at'].startswith('eq.')
            if table == 'manufacturer_sources':
                assert query['extracted_payload->>adapter'] == 'eq.toyota_public_configurator_v1'
                assert 'extraction_payload->>adapter' not in query
                assert query['verified_at'] == 'is.null' and query['source_validation'] == 'eq.needs_api_contract'
                assert query['verified_by'] == 'is.null'
            else:
                assert query['extraction_payload->>adapter'] == 'eq.toyota_public_configurator_v1'
                assert query['validation_status'] == 'eq.needs_review' and 'validation_errors' in query
            if self.race: return []
            row = next(row for row in target if query['id'] == 'eq.' + row['id'])
            row.update(copy.deepcopy(payload))
        return [copy.deepcopy(row)]


class Fetcher:
    def __init__(self, payload=None, content_type='application/json', reserved=False, allowed=True, body=None):
        self.timeout, self.calls, self.allowed = 20, [], allowed
        self.body = body if body is not None else encoded(payload or {})
        headers = Message(); headers['Content-Type'] = content_type
        if reserved: headers['tdm-reservation'] = '1'
        self.response = SimpleNamespace(headers=headers, status=200)
        self.opener = SimpleNamespace(open=self.open)

    def robots_allowed(self, url):
        assert url == API_URL
        return self.allowed

    def open(self, request, timeout):
        self.calls.append(request)
        response = self.response

        class Context:
            def __enter__(self): return response
            def __exit__(self, *_): pass

        return Context()

    def read_body(self, _): return self.body


class ToyotaConfiguratorTests(unittest.TestCase):
    def test_real_shapes_extract_four_exact_variants_without_inheriting_unknowns(self):
        registry, packet, payload, source = fixture()
        rows = extract_packet(registry, packet, payload, source)
        self.assertEqual(len(rows), 4)
        self.assertEqual([row['price_sek'] for row in rows], [510000, 535000, 560000, 585000])
        self.assertEqual(rows[0]['drivetrain'], 'FWD'); self.assertEqual(rows[1]['drivetrain'], 'AWD')
        self.assertEqual(rows[0]['battery_kwh'], 73.1)
        self.assertEqual(rows[0]['wltp_consumption_kwh_100km'], 14.8)
        self.assertEqual(rows[0]['wltp_range_km'], 450)
        self.assertIsNone(rows[2]['wltp_range_km']); self.assertIsNone(rows[3]['wltp_range_km'])
        for row in rows:
            for field in ('price_type', 'price_valid_until', 'dc_charge_kw', 'ac_charge_kw', 'boot_liters', 'tow_kg', 'seats'):
                self.assertIsNone(row[field])
            self.assertEqual(row['validation_status'], 'needs_review')
            self.assertEqual(row['validation_errors'], [REVIEW_REASON])
        self.assertFalse(source_is_publishable(source))

    def test_request_and_response_hashes_and_literal_pointers_survive_sanitization(self):
        registry, packet, payload, source = fixture()
        for item in payload['fetches']:
            if item['fetchType'] == MOTORIZATION:
                for variant in item['result']['fetchResult']:
                    variant['engine']['category']['unrelatedToken'] = 'not-retained'
        rows = extract_packet(registry, packet, payload, source)
        safe = sanitize_response(payload)
        self.assertEqual(extract_packet(registry, packet, safe, source), rows)
        for row in rows:
            for evidence in row['extraction_payload']['field_evidence'].values():
                self.assertEqual(pointer_value(payload, evidence['source_pointer']), evidence['raw_value'])
                self.assertEqual(pointer_value(safe, evidence['source_pointer']), evidence['raw_value'])
                self.assertEqual(json.loads(evidence['quote']), evidence['raw_value'])
                self.assertEqual(evidence['source_hash'], source['content_hash'])
                self.assertEqual(evidence['request_hash'], source['request_hash'])
        text = json.dumps(safe)
        for secret in ('private-server-log', 'do-not-store', 'not-price-evidence', 'monthly', 'promotions', 'not-retained'):
            self.assertNotIn(secret, text)

    def test_wrong_or_stale_provenance_is_rejected(self):
        registry, packet, payload, source = fixture()
        for change in ({'url': API_URL + '?x=1'}, {'country': 'US'}, {'request_method': 'GET'},
                       {'request_hash': 'b'*64}, {'source_validation': 'reachable_approved_source'},
                       {'fetched_at': (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()}):
            with self.assertRaises(RefreshError): extract_packet(registry, packet, payload, {**source, **change})
        registry['source']['fetched_at'] = '2024-01-01T00:00:00Z'
        with self.assertRaises(RefreshError): extract_packet(registry, packet, payload, source)
        s, data, _ = inputs(); data['commonSettings']['country'] = 'us'
        with self.assertRaises(RefreshError): registry_from(s, data)

    def test_response_order_scope_errors_and_missing_groups_stop(self):
        registry, packet, payload, source = fixture()
        for mutate in (lambda p: p['fetches'].reverse(), lambda p: p['fetches'].pop(),
                       lambda p: p['fetches'][0]['result'].__setitem__('errorLogs', ['failed']),
                       lambda p: p['fetches'][1].__setitem__('gradeId', OTHER_GRADE + 'x')):
            bad = copy.deepcopy(payload); mutate(bad)
            with self.assertRaises(RefreshError): extract_packet(registry, packet, bad, source)

    def test_exact_grade_model_body_price_and_drive_must_agree(self):
        registry, packet, payload, source = fixture()
        for branch, field, value in [('grade', 'name', 'Executive'), ('model', 'configVersion', 'other'),
                                     ('body', 'id', 'wrong'), ('price', 'cash', 100000),
                                     ('motorization', 'engine', {'id': 'engine', 'name': 'wrong label'}),
                                     ('motorization', 'wheeldrive', {'name': 'AWD'})]:
            bad = copy.deepcopy(payload)
            bad['fetches'][0]['result']['fetchResult']['car'][branch][field] = value
            with self.assertRaises(RefreshError): extract_packet(registry, packet, bad, source)

    def test_numeric_and_duplicate_identity_checks(self):
        registry, packet, payload, source = fixture()
        for mutate in (lambda v: v[1]['price'].__setitem__('cash', -1),
                       lambda v: v[1]['engine'].__setitem__('name', 'Elmotor 343 hk, batteri 999,1 kWh'),
                       lambda v: v[1]['specs'][0].__setitem__('value', '1300'),
                       lambda v: v[1]['wheeldrive'].__setitem__('internalCode', '2WD'),
                       lambda v: v[1].__setitem__('carId', v[0]['carId'])):
            bad = copy.deepcopy(payload); mutate(bad['fetches'][1]['result']['fetchResult'])
            with self.assertRaises(RefreshError): extract_packet(registry, packet, bad, source)

    def test_wrong_units_or_noncertified_range_stay_unknown(self):
        registry, packet, payload, source = fixture()
        for field, value in [('unit', 'miles'), ('certification', 1), ('value', '450.5')]:
            bad = copy.deepcopy(payload)
            bad['fetches'][1]['result']['fetchResult'][0]['specs'][0][field] = value
            self.assertIsNone(extract_packet(registry, packet, bad, source)[0]['wltp_range_km'])

    def test_http_only_posts_bounded_read_operations_without_credentials(self):
        registry, packet, payload, source = fixture()
        fetcher = Fetcher(payload)
        actual, metadata = request_data(packet, fetcher)
        self.assertEqual(actual, payload)
        self.assertEqual(metadata['request_hash'], digest(packet))
        request = fetcher.calls[0]
        self.assertEqual(request.full_url, API_URL); self.assertEqual(request.method, 'POST')
        self.assertEqual(json.loads(request.data), packet)
        self.assertNotIn('Authorization', request.headers)
        for mutate in (lambda p: p.__setitem__('customer', 'private'),
                       lambda p: p['fetches'][0].__setitem__('fetchType', 'saveCar'),
                       lambda p: p['fetches'][0].__setitem__('customerId', 'private'),
                       lambda p: p['fetches'][1].__setitem__('financeQuoteID', 'private')):
            bad = copy.deepcopy(packet); mutate(bad); fake = Fetcher(payload)
            with self.assertRaises(RefreshError): request_data(bad, fake)
            self.assertEqual(fake.calls, [])

    def test_robots_reservations_wrong_content_oversize_duplicate_keys_and_nan_stop(self):
        _, packet, _, _ = fixture()
        for fake in (Fetcher(allowed=False), Fetcher(reserved=True), Fetcher(content_type='text/html'),
                     Fetcher(body=b'{"fetches":[],"fetches":[]}'), Fetcher(body=b'{"x":NaN}')):
            with self.assertRaises(RefreshError): request_data(packet, fake)
        with patch('toyota_configurator_intake.MAX_BYTES', 10):
            with self.assertRaises(RefreshError): request_data(packet, Fetcher(body=b' '*11))

    def test_private_staging_is_idempotent_and_never_calls_canonical_writes(self):
        registry, packet, payload, source = fixture()
        evidence = sanitize_response(payload); rows = extract_packet(registry, packet, payload, source)
        client = Client()
        for _ in range(2):
            self.assertEqual(stage_private(client, registry, source, packet, evidence, rows), 4)
        self.assertEqual(len(client.sources), 1); self.assertEqual(len(client.drafts), 4)
        self.assertEqual(client.sources[0]['source_validation'], 'needs_api_contract')
        self.assertIsNone(client.sources[0].get('verified_at'))
        self.assertEqual({row['validation_status'] for row in client.drafts}, {'needs_review'})

    def test_tampered_or_reviewed_rows_and_public_identities_stop_before_write(self):
        registry, packet, payload, source = fixture()
        evidence = sanitize_response(payload); rows = extract_packet(registry, packet, payload, source)
        client = Client(); bad = copy.deepcopy(rows); bad[0]['price_sek'] = 600000
        with self.assertRaises(RefreshError): stage_private(client, registry, source, packet, evidence, bad)
        self.assertEqual(client.calls, [])
        stage_private(client, registry, source, packet, evidence, rows)
        for mutate in (lambda c: c.sources[0].__setitem__('verified_at', source['fetched_at']),
                       lambda c: c.sources[0].__setitem__('verified_by', 'reviewer'),
                       lambda c: c.drafts[0].__setitem__('validation_status', 'validated'),
                       lambda c: c.drafts[0]['extraction_payload'].__setitem__('manufacturer_variant_id', 'different'),
                       lambda c: c.canonical.append({'source_url': API_URL})):
            copy_client = copy.deepcopy(client); copy_client.calls = []; mutate(copy_client)
            with self.assertRaises(RefreshError): stage_private(copy_client, registry, source, packet, evidence, rows)
            self.assertEqual(copy_client.calls, [])
        client.calls = []
        with self.assertRaisesRegex(RefreshError, 'sanitized_evidence_required'):
            stage_private(client, registry, source, packet, payload, rows)
        self.assertEqual(client.calls, [])

    def test_insert_conflicts_and_midflight_review_stop_without_overwrite(self):
        registry, packet, payload, source = fixture()
        evidence = sanitize_response(payload); rows = extract_packet(registry, packet, payload, source)
        client = Client(); client.race = True
        with self.assertRaisesRegex(RefreshError, 'concurrent_private'):
            stage_private(client, registry, source, packet, evidence, rows)
        self.assertEqual(client.sources, []); self.assertEqual(client.drafts, [])
        client.race = False; stage_private(client, registry, source, packet, evidence, rows)
        before = copy.deepcopy(client.sources); client.race = True
        with self.assertRaisesRegex(RefreshError, 'concurrent_private'):
            stage_private(client, registry, source, packet, evidence, rows)
        self.assertEqual(client.sources, before)

    def test_partial_private_batch_recovers_without_duplicates_or_publication(self):
        registry, packet, payload, source = fixture()
        evidence = sanitize_response(payload); rows = extract_packet(registry, packet, payload, source)

        class InterruptedClient(Client):
            stopped = False

            def _request(self, method, table, payload, query, prefer):
                if table == 'extracted_variant_drafts' and len(self.drafts) == 2 and not self.stopped:
                    self.stopped = True
                    return []
                return super()._request(method, table, payload, query, prefer)

        client = InterruptedClient()
        with self.assertRaisesRegex(RefreshError, 'concurrent_private'):
            stage_private(client, registry, source, packet, evidence, rows)
        self.assertEqual(len(client.drafts), 2)
        self.assertFalse(source_is_publishable(client.sources[0]))
        stage_private(client, registry, source, packet, evidence, rows)
        self.assertEqual(len(client.drafts), 4)
        self.assertEqual({row['validation_status'] for row in client.drafts}, {'needs_review'})


if __name__ == '__main__': unittest.main()
