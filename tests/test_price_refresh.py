import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from refresh_skoda_prices import prepare, stage_or_publish, PricePublicationUncertain, check_expected_prices
from skoda_price_intake import URL, NAMES
from variant_refresh import RefreshError


class PriceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
        self.source = {'url': URL, 'final_url': URL, 'brand': 'Skoda', 'model': 'Enyaq',
                       'status': 'reachable', 'http_status': 200, 'content_type': 'application/pdf',
                       'content_hash': 'b'*64, 'fetched_at': self.now.isoformat()}
        self.original = {'id': '00000000-0000-4000-8000-000000000001',
                         'canonical_model_id': '00000000-0000-4000-8000-000000000002',
                         'url': URL, 'brand': 'Skoda', 'model': 'Enyaq', 'country': 'SE', 'language': 'sv',
                         'source_authority': 'manufacturer', 'content_hash': 'a'*64, 'updated_at': self.now.isoformat()}
        self.previous = [{'id': f'00000000-0000-4000-8000-00000000000{i+3}',
                          'canonical_model_id': self.original['canonical_model_id'], 'variant_name': name,
                          'source_url': URL, 'source_hash': 'a'*64, 'updated_at': self.now.isoformat(),
                          'validation_status': 'published', 'price_sek': 500000+i*50000, 'dc_charge_kw': 185}
                         for i, name in enumerate(NAMES.values())]
        self.text = '''Škoda Enyaq Solid Edition
Selection Sportline RS
Erbjudandet är begränsat och gäller tom 2026-12-15.
85 286 572 155 0 501 000 kr – –
85x 299 572 157 0 551 000 kr – –
85x Sportline 299 565 159 0 – 601 000 kr
RS 340 558 161 0 – – 651 000 kr'''

    def run_prepare(self, **changes):
        return prepare(changes.get('source', self.source), self.text,
                       changes.get('original', self.original), changes.get('previous', self.previous), self.now)

    def test_private_packet_never_blends_old_technical_facts_into_fresh_price_drafts(self):
        before = copy.deepcopy(self.previous)
        packet = self.run_prepare()
        self.assertFalse(packet['ready_for_publication'])
        self.assertEqual(packet['published'], 0)
        self.assertTrue(all(target['draft_id'] is None for target in packet['packet']['targets']))
        self.assertTrue(all(row['dc_charge_kw'] is None and row['wltp_range_km'] is None for row in packet['drafts']))
        self.assertEqual(self.previous, before)
        self.assertEqual(packet['packet']['batch_id'], self.run_prepare()['packet']['batch_id'])

    def test_stale_fetch_wrong_group_authority_and_large_changes_fail_closed(self):
        for patch in [{'fetched_at': '2026-10-27T11:00:00+00:00'}, {'fetched_at': '2026-10-27T13:00:00+00:00'},
                      {'fetched_at': '2026-10-27T12:00:00'}, {'status': 'blocked'}, {'http_status': 403},
                      {'content_type': 'text/html'}, {'final_url': 'https://dealer.invalid/'}, {'content_hash': ''}]:
            with self.subTest(source=patch), self.assertRaises(RefreshError):
                self.run_prepare(source={**self.source, **patch})
        for patch in [{'source_authority': 'authorized_dealer'}, {'model': 'Elroq'}, {'country': 'DE'}, {'id': 'bad'}]:
            with self.subTest(original=patch), self.assertRaises(RefreshError):
                self.run_prepare(original={**self.original, **patch})
        for patch in [{'price_sek': 100000}, {'validation_status': 'draft'}, {'canonical_model_id': 'other'},
                      {'source_url': 'https://dealer.invalid/'}, {'source_hash': None}, {'id': self.previous[0]['id']}]:
            previous = copy.deepcopy(self.previous)
            previous[-1].update(patch)
            with self.subTest(previous=patch), self.assertRaises(RefreshError):
                self.run_prepare(previous=previous)

    def test_staging_and_publishing_use_only_existing_private_staging_and_rpc(self):
        class Client:
            def __init__(self):
                self.writes = []
            def select(self, table, fields, filters):
                return [{'price_verified_at': None}]
            def upsert(self, table, rows, conflict):
                self.writes.append(table)
                return [{**row, 'id': f'00000000-0000-4000-8000-00000000001{i}'} for i, row in enumerate(rows)]
            def _request(self, method, path, payload):
                self.writes.append(path)
                assert method == 'POST' and len(payload['p_batch']['targets']) == 4
                return {'published': 4, 'price_verified': True, 'specifications_reverified': False}
        client = Client()
        prepared = self.run_prepare()
        self.assertEqual(stage_or_publish(client, prepared)['published'], 0)
        self.assertEqual(client.writes, ['extracted_variant_drafts'])
        self.assertEqual(stage_or_publish(client, prepared, publish=True)['published'], 4)
        self.assertEqual(client.writes[-1], 'rpc/publish_skoda_price_refresh')
        for response in [None, [], '', 4, {}, {'published': 4},
                         {'published': 4, 'price_verified': True, 'specifications_reverified': True}]:
            client._request = lambda *args, result=response: result
            with self.subTest(response=response), self.assertRaisesRegex(PricePublicationUncertain, 'reconcile_saved_batch'):
                stage_or_publish(client, prepared, publish=True)
        client._request = lambda *args: (_ for _ in ()).throw(TimeoutError('synthetic lost response'))
        with self.assertRaises(PricePublicationUncertain):
            stage_or_publish(client, prepared, publish=True)
        client.writes.clear()
        client.select = lambda *args: (_ for _ in ()).throw(RuntimeError('missing migration'))
        with self.assertRaisesRegex(RefreshError, 'migration_020_required'):
            stage_or_publish(client, prepared, publish=True)
        self.assertEqual(client.writes, [])

    def test_missing_legacy_authority_allows_private_extraction_but_never_staging(self):
        prepared = self.run_prepare(original={**self.original, 'source_authority': None})
        self.assertEqual(len(prepared['drafts']), 4)
        self.assertTrue(prepared['requires_source_registry_alignment'])
        class NoRequests:
            def select(self, *args):
                raise AssertionError('No remote request permitted')
            def upsert(self, *args):
                raise AssertionError('No remote write permitted')
        with self.assertRaisesRegex(RefreshError, 'source_registry_authority_missing'):
            stage_or_publish(NoRequests(), prepared, publish=True)

    def test_operator_price_scope_cannot_change_between_dry_run_and_publication(self):
        drafts = self.run_prepare()['drafts']
        expected = {row['variant_name']: {key: row[key] for key in ('price_sek', 'price_type', 'price_valid_until')} for row in drafts}
        check_expected_prices(drafts, expected)
        for patch in [{'price_sek': drafts[0]['price_sek'] + 100}, {'price_type': 'list_price'}, {'price_valid_until': '2027-01-01'}]:
            changed = copy.deepcopy(drafts)
            changed[0].update(patch)
            with self.assertRaisesRegex(RefreshError, 'operator_approved_scope'):
                check_expected_prices(changed, expected)


if __name__ == '__main__':
    unittest.main()
