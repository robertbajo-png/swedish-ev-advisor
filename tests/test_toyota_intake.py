import copy
import io
import json
import sys
import unittest
from html import escape
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_catalog_sources import SourceFetcher, allowed_url
from toyota_price_intake import (HTML_URL, MODEL_URL, PDF_URL, config_from_document,
    exact_link_policy, extract_config, legacy_mapping, parse_pdf, preserve_intake_state, stage_private)
from refresh_verified_variants import toyota_document_candidates
from variant_refresh import RefreshError, parse_document


def fixture():
    engine = {'id': 'engine', 'name': 'Elmotor 170 hk, batteri 58,7 kWh', 'certification': 2,
              'category': {'code': 'BEV'}, 'internalFuelCode': 'ELECTRIC'}
    drive = {'name': 'Framhjulsdrift'}
    price = {'cash': 510000, 'monthly': 4000, 'exclVat': 408000, 'discount': 490000, 'promotions': ['campaign']}
    variant = {'carId': '11111111-1111-4111-8111-111111111111', 'engine': engine, 'wheeldrive': drive, 'price': price,
               'specs': [{'internalCode': 'PERCOMBINED', 'unit': 'km', 'value': '450', 'certification': 2},
                         {'internalCode': 'ECCOMBINEDWLTP', 'unit': 'Wh/km', 'value': '148', 'certification': 2}]}
    return {'commonSettings': {'brand': 'toyota', 'country': 'se', 'language': 'sv'},
            'car': {'id': variant['carId'], 'initialized': True, 'grade': {'name': 'Active'}, 'price': price,
                    'model': {'name': 'Nya Toyota bZ4X', 'id': 'model', 'configVersion': 'test'},
                    'motorization': {'engine': engine, 'wheeldrive': drive}},
            'carConfigMotorization': {'initialized': True, 'motorization': [variant]},
            'specs': {'techSpecs': [{'data': [{'internalCode': 'TOWCAPBRK', 'unit': 'kg', 'value': '750'},
                                           {'internalCode': 'NRSEAT', 'unit': 'säten', 'value': '5'}]}]}}


def source():
    return {'url': HTML_URL, 'brand': 'Toyota', 'model': 'bZ4X', 'content_hash': 'a'*64,
            'source_type': 'manufacturer_specs_page', 'source_authority': 'manufacturer',
            'source_validation': 'reachable_official_model_source', 'fetched_at': '2026-10-20T12:00:00Z'}


def document(data):
    html = '<div id="fixture-data" style="display:none">' + escape(json.dumps(data)) + '</div>'
    return parse_document(html.encode(), 'text/html')


class ToyotaIntakeTests(unittest.TestCase):
    def test_link_authority_is_exact_fresh_and_not_a_domain_wildcard(self):
        doc = parse_document(f'<a href="{PDF_URL}">Prislista</a>'.encode(), 'text/html')
        official = {'status': 'reachable', 'final_url': MODEL_URL, 'content_hash': 'b'*64, 'document': doc}
        candidate = toyota_document_candidates(doc, MODEL_URL, 'b'*64)[0]
        policy = exact_link_policy(candidate, official)
        self.assertTrue(policy(PDF_URL, {'Toyota'}))
        self.assertFalse(allowed_url(PDF_URL, {'Toyota'}), 'No broad global domain approval')
        for target in [PDF_URL + '?x=1', PDF_URL + '#fragment', PDF_URL + '-touring', 'https://example.org/document.pdf']:
            self.assertFalse(policy(target, {'Toyota'}))
        self.assertFalse(policy(PDF_URL, {'Lexus'}))
        with self.assertRaises(RefreshError): exact_link_policy({**candidate, 'discovery_source_hash': 'c'*64}, official)
        with self.assertRaises(RefreshError): exact_link_policy(candidate, {**official, 'document': document({})})

    def test_config_requires_one_exact_initialized_swedish_model(self):
        data = fixture()
        self.assertEqual(config_from_document(document(data))['car']['grade']['name'], 'Active')
        for branch, field, value in [('commonSettings', 'country', 'us'), ('car', 'initialized', False),
                                     ('carConfigMotorization', 'initialized', False)]:
            bad = copy.deepcopy(data); bad[branch][field] = value
            with self.assertRaises(RefreshError): config_from_document(document(bad))
        with self.assertRaises(RefreshError): config_from_document(document({}))
        bad = copy.deepcopy(data); bad['car']['model']['name'] = 'Nya bZ4X Touring'
        with self.assertRaises(RefreshError): config_from_document(document(bad))

    def test_exact_variant_source_pointers_and_no_fake_list_or_charging_values(self):
        data = fixture()
        rows = extract_config(data, source())
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['price_sek'], 510000)
        self.assertEqual(row['wltp_range_km'], 450)
        self.assertEqual(row['wltp_consumption_kwh_100km'], 14.8)
        self.assertEqual(row['battery_kwh'], 58.7)
        self.assertEqual(row['tow_kg'], 750)
        for field in ['price_type', 'price_valid_until', 'dc_charge_kw', 'ac_charge_kw', 'boot_liters']:
            self.assertIsNone(row[field])
        self.assertEqual(row['validation_status'], 'needs_review')
        proof = row['extraction_payload']['field_evidence']['price_sek']
        self.assertEqual(proof['raw_value'], 510000)
        self.assertTrue(proof['source_pointer'].endswith('/price/cash'))
        self.assertEqual(proof['source_hash'], 'a'*64)
        self.assertEqual(row['source_quote'].split(' | ')[-1], '510000', 'Keep excerpts literal, without invented units')

    def test_intervals_preliminary_and_wrong_units_remain_null(self):
        for field, value in [('value', '440-460'), ('certification', 1), ('unit', 'miles')]:
            data = fixture(); data['carConfigMotorization']['motorization'][0]['specs'][0][field] = value
            self.assertIsNone(extract_config(data, source())[0]['wltp_range_km'])
        data = fixture(); data['carConfigMotorization']['motorization'][0]['specs'][1]['value'] = '148,5'
        self.assertIsNone(extract_config(data, source())[0]['wltp_consumption_kwh_100km'], 'Do not silently round into database precision')

    def test_identity_conflicts_duplicate_specs_and_hard_ranges_fail(self):
        for mutate in [lambda d: d['car'].__setitem__('id', 'different'),
                       lambda d: d['carConfigMotorization']['motorization'][0]['engine'].__setitem__('certification', 1),
                       lambda d: d['carConfigMotorization']['motorization'][0]['price'].__setitem__('exclVat', 1),
                       lambda d: d['carConfigMotorization']['motorization'][0]['specs'][0].__setitem__('value', '1500'),
                       lambda d: d['carConfigMotorization']['motorization'][0]['specs'].append(copy.deepcopy(d['carConfigMotorization']['motorization'][0]['specs'][0]))]:
            data = fixture(); mutate(data)
            with self.assertRaises(RefreshError): extract_config(data, source())

    def test_unselected_motorization_does_not_inherit_selected_specs(self):
        data = fixture(); other = copy.deepcopy(data['carConfigMotorization']['motorization'][0])
        other['carId'] = '22222222-2222-4222-8222-222222222222'
        other['engine']['name'] = 'Elmotor 230 hk, batteri 74,1 kWh'
        data['carConfigMotorization']['motorization'].append(other)
        row = extract_config(data, source())[1]
        self.assertIsNone(row['tow_kg']); self.assertIsNone(row['seats'])
        self.assertEqual(row['battery_kwh'], 74.1)

    def test_legacy_short_names_never_auto_map_even_with_one_candidate(self):
        rows = extract_config(fixture(), source())
        old = [{'variant_name': 'Active FWD', 'drivetrain': 'FWD', 'battery_kwh': None},
               {'variant_name': 'Active AWD', 'drivetrain': 'AWD', 'battery_kwh': None}]
        report = legacy_mapping(old, rows)
        self.assertEqual(len(report[0]['candidates']), 1)
        self.assertTrue(all(not item['auto_update_allowed'] for item in report))

    def test_private_staging_is_idempotent_and_never_writes_canonical_or_calls_rpc(self):
        rows = extract_config(fixture(), source())
        class Client:
            def __init__(self): self.writes = []
            def select(self, table, columns, filters):
                if table == 'canonical_models': return [{'id': 'model', 'validation_status': 'draft'}]
                return []
            def upsert(self, table, items, conflict):
                self.writes.append((table, conflict, items))
                return [{'id': 'source', **item} for item in items]
        client = Client()
        self.assertEqual(stage_private(client, source(), rows), 1)
        self.assertEqual(stage_private(client, source(), rows), 1)
        self.assertEqual({item[0] for item in client.writes}, {'manufacturer_sources', 'extracted_variant_drafts'})
        self.assertEqual(client.writes[1][2][0]['validation_status'], 'needs_review')

    def test_reviewed_sources_or_drafts_are_not_overwritten(self):
        class Client:
            def select(self, table, columns, filters):
                if table == 'canonical_models': return [{'id': 'model', 'validation_status': 'draft'}]
                if table == 'manufacturer_sources': return [{'canonical_model_id': 'model', 'verified_at': '2026-10-20'}]
                return []
            def upsert(self, *_): self.fail('Must stop before writes')
        with self.assertRaises(RefreshError): stage_private(Client(), source(), extract_config(fixture(), source()))

    def test_pdf_signature_and_metadata_reservation_before_text_extraction(self):
        from pypdf import PdfWriter
        with self.assertRaises(RefreshError): parse_pdf(b'<html>error</html>', 'application/pdf')
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
        writer.add_metadata({'/tdm-reservation': '1'})
        stream = io.BytesIO(); writer.write(stream)
        with self.assertRaisesRegex(RefreshError, 'machine_reservation'):
            parse_pdf(stream.getvalue(), 'application/pdf')

    def test_slow_stream_deadline_and_tdm_stop_before_parser(self):
        class Stream:
            def read1(self, _): return b'x'
        with patch('audit_catalog_sources.time.monotonic', side_effect=[0, 1, 3]):
            with self.assertRaises(TimeoutError): SourceFetcher(timeout=2).read_body(Stream())
        calls = []
        class Response:
            headers = {'content-type': 'application/pdf', 'tdm-reservation': '1'}
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, _): calls.append('read'); return b'%PDF-'
        fetcher = SourceFetcher(document_parser=lambda *_: calls.append('parse'))
        fetcher.robots_allowed = lambda _: True
        fetcher.opener.open = lambda *_args, **_kwargs: Response()
        self.assertEqual(fetcher.fetch(HTML_URL, {'Toyota'})['status'], 'machine_reservation')
        self.assertEqual(calls, [])

    def test_failed_pdf_and_successful_staging_history_survive_other_runs(self):
        prior = {'pdf': {'status': 'quarantined', 'reason': 'timeout'},
                 'last_successful_stage': {'rows': 1, 'fetched_at': 'earlier'}}
        current = preserve_intake_state({'staged': 0}, prior)
        self.assertEqual(current['pdf'], prior['pdf'])
        self.assertEqual(current['last_successful_stage'], prior['last_successful_stage'])
        current = preserve_intake_state({'staged': 1, 'checked_at': 'now', 'content_hash': 'a'*64}, prior)
        self.assertEqual(current['last_successful_stage']['fetched_at'], 'now')


if __name__ == '__main__': unittest.main()
