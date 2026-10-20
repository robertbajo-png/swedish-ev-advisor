import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_toyota_intake import fixture, source
from discover_toyota_grades import discover, run
from variant_refresh import RefreshError

MODEL = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
GRADE = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
OTHER_GRADE = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
OTHER_CAR = '22222222-2222-4222-8222-222222222222'


def inputs():
    data = fixture()
    data['car']['model']['id'] = MODEL
    data['car']['grade']['id'] = GRADE
    data['grades'] = {'items': [
        {'name': 'Active', 'id': GRADE, 'defaultCarId': data['car']['id'], 'unrelatedToken': 'do-not-export'},
        {'name': 'Active Tech', 'id': OTHER_GRADE, 'defaultCarId': OTHER_CAR, 'gradeFeatures': ['not-variant-facts']}]}
    fresh = {**source(), 'fetched_at': datetime.now(timezone.utc).isoformat()}
    existing = [{'id': 'old', 'variant_name': 'Active FWD', 'manufacturer_variant_id': None},
                {'id': 'current', 'variant_name': 'Active FWD 58.7 kWh 170 hk',
                 'manufacturer_variant_id': data['car']['id'], 'manufacturer_model_id': MODEL,
                 'manufacturer_config_version': 'test', 'validation_status': 'published'}]
    return fresh, data, existing


class GradeDiscoveryTests(unittest.TestCase):
    def test_grade_defaults_are_not_vehicle_facts_or_publication_candidates(self):
        source, data, existing = inputs()
        before = copy.deepcopy((source, data, existing))
        report = discover(source, data, existing)
        self.assertEqual(report['grade_count'], 2)
        self.assertEqual(report['unresolved_grade_count'], 1)
        self.assertEqual(report['selected_variant_count'], 1)
        self.assertEqual(report['grades'][0]['status'], 'identity_already_public')
        other = report['grades'][1]
        self.assertEqual(other['status'], 'needs_configuration_source')
        self.assertIsNone(other['configuration_source_url'])
        self.assertFalse(other['publication_allowed'])
        self.assertEqual(report['published'], 0)
        self.assertFalse(report['canonical_writes'])
        for field in ('price_sek', 'wltp_range_km', 'tow_kg', 'battery_kwh'):
            self.assertNotIn(field, other)
        self.assertEqual((source, data, existing), before)

    def test_evidence_is_exact_pointer_based_and_sanitized(self):
        source, data, existing = inputs()
        report = discover(source, data, existing)
        for index, job in enumerate(report['grades']):
            for key, evidence in job['field_evidence'].items():
                self.assertEqual(evidence['source_pointer'], f'/grades/items/{index}/{key}')
                self.assertEqual(evidence['raw_value'], data['grades']['items'][index][key])
                self.assertEqual(json.loads(evidence['quote']), evidence['raw_value'])
            self.assertEqual(job['discovery_source_hash'], source['content_hash'])
        text = json.dumps(report)
        for forbidden in ('unrelatedToken', 'do-not-export', 'gradeFeatures', 'finance', 'monthly'):
            self.assertNotIn(forbidden, text)

    def test_stale_wrong_market_and_unapproved_source_stop(self):
        source, data, existing = inputs()
        for changes in ({'fetched_at': (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()},
                        {'fetched_at': '2024-01-01T00:00:00'}, {'url': 'https://www.toyota.se/bilar/bz4x-touring/specifications'},
                        {'source_authority': 'authorized_dealer'}, {'content_hash': 'invalid'}):
            with self.assertRaises(RefreshError): discover({**source, **changes}, data, existing)
        data['commonSettings']['country'] = 'us'
        with self.assertRaises(RefreshError): discover(source, data, existing)

    def test_duplicate_or_ambiguous_grade_identity_is_quarantined(self):
        source, data, existing = inputs()
        for change in ({'id': GRADE}, {'defaultCarId': data['car']['id']}, {'name': 'ACTIVE'}, {'id': 'not-uuid'}):
            bad = copy.deepcopy(data)
            bad['grades']['items'][1].update(change)
            with self.assertRaises(RefreshError): discover(source, bad, existing)
        with self.assertRaises(RefreshError): discover(source, data, existing + [existing[1]])

    def test_selected_grade_must_be_present_and_match_exact_default(self):
        source, data, existing = inputs()
        for mutate in (lambda d: d['car']['grade'].__setitem__('id', OTHER_GRADE),
                       lambda d: d['grades']['items'][0].__setitem__('defaultCarId', '33333333-3333-4333-8333-333333333333'),
                       lambda d: d['grades'].__setitem__('items', [])):
            bad = copy.deepcopy(data); mutate(bad)
            with self.assertRaises(RefreshError): discover(source, bad, existing)

    def test_existing_identity_conflict_and_legacy_mapping_never_update(self):
        source, data, existing = inputs()
        existing[1]['manufacturer_config_version'] = 'different'
        report = discover(source, data, existing)
        self.assertEqual(report['grades'][0]['status'], 'identity_conflict')
        self.assertEqual(report['legacy_mapping'][0]['status'], 'needs_mapping')
        self.assertFalse(report['legacy_mapping'][0]['auto_update_allowed'])

    def test_job_identity_is_stable_across_fresh_source_hashes(self):
        source, data, existing = inputs()
        a = discover(source, data, existing)
        b = discover({**source, 'content_hash': 'b'*64}, data, existing)
        self.assertEqual([job['job_id'] for job in a['grades']], [job['job_id'] for job in b['grades']])
        self.assertNotEqual(a['source_hash'], b['source_hash'])

    def test_worker_only_reads_the_exact_canonical_model(self):
        source, data, existing = inputs()
        calls = []

        class Client:
            def select(self, table, fields, filters):
                calls.append((table, fields, filters))
                if table == 'canonical_models':
                    return [{'id': 'model', 'brand': 'Toyota', 'model': 'bZ4X', 'validation_status': 'published'}]
                if table == 'canonical_model_variants': return existing
                raise AssertionError(table)

        report = run(Client(), source, data)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][2], {'canonical_model_id': 'eq.model'})
        self.assertFalse(report['remote_writes'])
        self.assertEqual(report['openai_calls'], 0)


if __name__ == '__main__': unittest.main()
