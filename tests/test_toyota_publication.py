import copy
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_toyota_intake import fixture, source
from publish_toyota_variants import check_new_identity, prepare_packet
from toyota_price_intake import HTML_URL, extract_config
from variant_refresh import RefreshError


def fresh_source():
    return {**source(), 'fetched_at': datetime.now(timezone.utc).isoformat()}


class Client:
    def __init__(self):
        self.calls = []
        self.source = {'id': 'source', 'canonical_model_id': 'model', 'brand': 'Toyota', 'model': 'bZ4X',
            'country': 'SE', 'language': 'sv', 'source_authority': 'manufacturer', 'http_status': 200,
            'source_validation': 'reachable_official_model_source', 'updated_at': '2026-10-20T12:00:00Z', 'content_hash': 'a'*64}
        self.canonical = []
        row = extract_config(fixture(), fresh_source())[0]
        self.drafts = [{**row, 'id': 'draft', 'source_id': 'source', 'canonical_model_id': 'model', 'updated_at': 'before'}]
        self.conflict = False

    def select(self, table, *_):
        if table == 'manufacturer_sources': return [self.source]
        if table == 'canonical_models': return [{'id': 'model', 'brand': 'Toyota', 'model': 'bZ4X', 'validation_status': 'draft'}]
        if table == 'canonical_model_variants': return self.canonical
        if table == 'extracted_variant_drafts': return self.drafts
        raise AssertionError(table)

    def _request(self, method, table, payload, query, prefer):
        self.calls.append((method, table, copy.deepcopy(payload), query, prefer))
        assert method == 'PATCH' and table == 'extracted_variant_drafts'
        assert query['id'] == 'eq.draft' and 'updated_at' in query and 'validation_status' in query
        if self.conflict: return []
        self.drafts[0].update(payload)
        return self.drafts


class ToyotaPublicationTests(unittest.TestCase):
    def test_dry_run_does_not_write_and_requires_fresh_exact_source(self):
        client = Client()
        result, packet = prepare_packet(client, fresh_source(), fixture())
        self.assertEqual(result['status'], 'validated_local_only')
        self.assertEqual(client.calls, [])
        self.assertEqual(packet['source_id'], 'source')
        for bad in [{**fresh_source(), 'fetched_at': '2024-01-01T00:00:00Z'}, {**fresh_source(), 'url': 'https://example.org/'},
                    {**fresh_source(), 'fetched_at': '2026-10-20T12:00:00'}]:
            with self.assertRaises(RefreshError): prepare_packet(client, bad, fixture())

    def test_preparation_only_patches_private_validated_staging_with_cas(self):
        client = Client()
        with tempfile.TemporaryDirectory() as directory, patch('publish_toyota_variants.LOCAL', Path(directory)):
            result, packet = prepare_packet(client, fresh_source(), fixture(), write=True)
            self.assertEqual(result['status'], 'prepared')
            self.assertEqual(client.calls[0][2]['validation_status'], 'validated')
            self.assertEqual(client.calls[0][2]['validation_errors'], [])
            self.assertIn('source_configuration', client.drafts[0]['extraction_payload'])
            self.assertEqual(packet['targets'][0]['expected_updated_at'], client.drafts[0]['updated_at'])
            self.assertTrue((Path(directory)/'publication-batch.json').exists())

    def test_reviewed_uncertain_and_conflicting_drafts_cannot_be_promoted(self):
        for mutate in [lambda c: c.drafts[0].__setitem__('validation_status', 'rejected'),
                       lambda c: c.drafts[0].__setitem__('validation_errors', ['conflicting_source']),
                       lambda c: c.drafts[0].__setitem__('price_sek', 100000),
                       lambda c: c.source.__setitem__('source_authority', 'authorized_dealer'),
                       lambda c: c.drafts[0]['extraction_payload'].__setitem__('manufacturer_variant_id', 'other')]:
            client = Client(); mutate(client)
            with self.assertRaises(RefreshError): prepare_packet(client, fresh_source(), fixture(), write=True)
            self.assertEqual(client.calls, [])

    def test_concurrent_staging_change_stops_before_any_publication(self):
        client = Client(); client.conflict = True
        with self.assertRaisesRegex(RefreshError, 'concurrent_private_draft_change'):
            prepare_packet(client, fresh_source(), fixture(), write=True)
        self.assertEqual(len(client.calls), 1)

    def test_already_public_identity_is_read_only_and_fact_conflicts_are_quarantined(self):
        client = Client()
        row = extract_config(fixture(), fresh_source())[0]
        client.canonical = [{**row, 'id': 'canonical', 'validation_status': 'published',
            'source_id': 'source', 'manufacturer_model_id': row['extraction_payload']['manufacturer_model_id'],
            'manufacturer_config_version': row['extraction_payload']['model_config_version'],
            'manufacturer_variant_id': row['extraction_payload']['manufacturer_variant_id']}]
        result, packet = prepare_packet(client, fresh_source(), fixture(), write=True)
        self.assertEqual(result['status'], 'already_public'); self.assertIsNone(packet)
        self.assertEqual(client.calls, [])
        client.canonical[0]['battery_kwh'] = 70
        with self.assertRaisesRegex(RefreshError, 'separate_refresh'): prepare_packet(client, fresh_source(), fixture())

    def test_wrong_market_or_other_existing_source_cannot_be_used(self):
        client = Client(); data = fixture(); data['commonSettings']['country'] = 'us'
        with self.assertRaises(RefreshError): prepare_packet(client, fresh_source(), data)
        client.canonical = [{'variant_name': 'Different', 'source_url': HTML_URL}]
        with self.assertRaisesRegex(RefreshError, 'complete_refresh'): prepare_packet(client, fresh_source(), fixture())


if __name__ == '__main__': unittest.main()
