import copy
import hashlib
import io
import json
import tempfile
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import refresh_skoda_prices as worker
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

    def test_private_prepare_binds_full_document_and_vehicle_page(self):
        pages = [
            self.text,
            '2/3\nTillvalsutrustning\nMetalliclack från 0 kr\nErbjudandet är begränsat. Gäller tom 2026-06-16.\nrekommenderade cirkapriser.',
            '3/3\nStandardutrustning\nDragkrok'
        ]
        text = '\n'.join(pages).strip()
        source = {**self.source, 'text_hash': hashlib.sha256(text.encode('utf-8')).hexdigest()}
        prev = copy.deepcopy(self.previous)
        result = prepare(source, text, self.original, self.previous, self.now, document_pages=pages)
        self.assertEqual(result['published'], 0)
        self.assertEqual(result['staged'], 0)
        self.assertFalse(result['ready_for_publication'])
        self.assertEqual(self.previous, prev)
        self.assertTrue(all(r['price_valid_until'] == '2026-12-15' and r['dc_charge_kw'] is None for r in result['drafts']))
        self.assertTrue(all(r['extraction_payload']['field_evidence']['price_sek']['source_page'] == 1 for r in result['drafts']))
        with self.assertRaisesRegex(RefreshError, 'campaign_expiry_ambiguous'):
            prepare(source, text, self.original, self.previous, self.now)

    def test_documented_dry_run_entrypoint_reads_only_and_binds_exact_matrix(self):
        expiry = (datetime.now(timezone.utc).date() + timedelta(days=20)).isoformat()
        old_expiry = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        pages = [
            self.text.replace('2026-12-15', expiry),
            '2/3\nTillvalsutrustning\nMetalliclack från 0 kr\nErbjudandet är begränsat. Gäller tom ' + old_expiry + '.\nrekommenderade cirkapriser.',
            '3/3\nStandardutrustning\nDragkrok'
        ]
        text = '\n'.join(pages).strip()
        fetched = {**self.source, 'text': text, 'document': pages,
                   'text_hash': hashlib.sha256(text.encode('utf8')).hexdigest()}
        expected = {name: {'price_sek': 501000+i*50000, 'price_type': 'campaign_price',
                           'price_valid_until': expiry} for i, name in enumerate(NAMES.values())}
        reads = []
        test = self
        class ReadOnly:
            def select(self, table, columns, filters):
                reads.append(table)
                if table == 'manufacturer_sources':
                    return [test.original]
                if table == 'canonical_model_variants':
                    return test.previous
                raise AssertionError('unexpected read')
            def upsert(self, *args):
                raise AssertionError('dry run must never stage')
            def _request(self, *args):
                raise AssertionError('dry run must never publish')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            matrix_file = folder / 'matrix.json'
            matrix_file.write_text(json.dumps(expected), encoding='utf8')
            receipt_dir = folder / 'receipts'
            output = io.StringIO()
            with patch.object(worker, 'fetch_price_source', return_value=fetched), \
                 patch.object(worker, 'SupabaseRestClient', return_value=ReadOnly()), \
                 patch.object(worker, 'LOCAL', receipt_dir), \
                 patch.object(sys, 'argv', ['refresh_skoda_prices.py', '--expected-prices', str(matrix_file)]), \
                 redirect_stdout(output):
                worker.main()
            report = json.loads(output.getvalue())
            self.assertEqual(report['mode'], 'dry_run')
            self.assertEqual(report['staged'], 0)
            self.assertEqual(report['published'], 0)
            self.assertFalse(report['remote_writes'])
            self.assertEqual(reads, ['manufacturer_sources', 'canonical_model_variants'])
            receipts = list(receipt_dir.glob('*.json'))
            self.assertEqual(len(receipts), 1)
            receipt = json.loads(receipts[0].read_text(encoding='utf8'))
            self.assertEqual(receipt['source']['content_hash'], fetched['content_hash'])
            self.assertEqual(receipt['operation_result'], {'staged': 0, 'published': 0})
            self.assertTrue(all(d['extraction_payload']['field_evidence']['price_sek']['source_page'] == 1 for d in receipt['drafts']))

    def separate_previous(self):
        previous = copy.deepcopy(self.previous)
        for i, row in enumerate(previous):
            row.update(source_id='00000000-0000-4000-8000-000000000090',
                       source_url='https://www.skoda.se/modeller/enyaq/enyaq',
                       source_hash='c'*64, price_sek=501000+i*50000,
                       price_type='campaign_price', price_valid_until='2026-12-15',
                       price_source_url=URL, price_source_hash='d'*64,
                       price_source_quote='Earlier exact approved price proof',
                       price_source_name='Skoda Sverige',
                       price_verified_at='2026-09-01T10:15:00.123456+00:00',
                       price_refresh_batch_id='e'*64)
        return previous

    def test_existing_separate_price_proof_binds_both_evidence_lanes(self):
        previous = self.separate_previous()
        prepared = self.run_prepare(previous=previous)
        self.assertEqual(prepared['packet']['adapter'], worker.SEPARATE_ADAPTER)
        self.assertTrue(prepared['requires_separate_price_contract_v2'])
        self.assertFalse(prepared['ready_for_publication'])
        for target, row, draft in zip(prepared['packet']['targets'], previous, prepared['drafts']):
            self.assertEqual(target['expected_technical_source_id'], row['source_id'])
            self.assertEqual(target['expected_technical_source_url'], row['source_url'])
            self.assertEqual(target['expected_hash'], row['source_hash'])
            self.assertEqual(target['expected_price'], {k: row[k] for k in (*worker.PRICE_PROOF_FIELDS,*worker.PRICE_FACT_FIELDS)})
            self.assertEqual(draft['source_url'], URL)
            self.assertEqual(draft['source_id'], self.original['id'])
            self.assertEqual(draft['extraction_payload']['adapter'], worker.SEPARATE_ADAPTER)
            self.assertIsNone(draft['wltp_range_km'])

    def test_separate_group_never_falls_back_when_old_proof_or_facts_differ(self):
        for patch in [
            {'price_source_url':'https://www.skoda.se/modeller/enyaq/enyaq'},
            {'price_source_hash':'bad'}, {'price_source_quote':' '}, {'price_source_name':'other'},
            {'price_verified_at':None}, {'price_verified_at':'2026-10-27T12:01:00+00:00'},
            {'price_refresh_batch_id':None}, {'price_sek':500000},
            {'price_type':'list_price'}, {'price_valid_until':'2026-12-16'},
            {'source_id':None}, {'validation_status':'draft'}
        ]:
            previous=self.separate_previous()
            previous[-1].update(patch)
            with self.subTest(patch=patch), self.assertRaises(RefreshError):
                self.run_prepare(previous=previous)
        previous=self.separate_previous()
        for key in worker.PRICE_PROOF_FIELDS:
            previous[-1][key]=None
        previous[-1]['source_url']=URL
        with self.assertRaises(RefreshError):
            self.run_prepare(previous=previous)

    def test_v2_contract_probe_fails_before_staging_and_selects_exact_rpc(self):
        prepared=self.run_prepare(previous=self.separate_previous())
        class Client:
            def __init__(self, contract): self.contract=contract;self.calls=[]
            def _request(self, method, path, payload=None):
                self.calls.append((method,path))
                if method=='GET':
                    if isinstance(self.contract, Exception): raise self.contract
                    return self.contract
                assert method=='POST' and path=='rpc/publish_skoda_price_refresh_v2'
                assert payload['p_batch']['adapter']==worker.SEPARATE_ADAPTER
                assert len(payload['p_batch']['targets'])==4
                return {'published':4,'price_verified':True,'specifications_reverified':False}
            def select(self, table, fields, filters):
                self.calls.append(('GET',table)); return [{'price_verified_at':None}]
            def upsert(self, table, rows, conflict):
                self.calls.append(('POST',table))
                return [{**row, 'id': f'00000000-0000-4000-8000-00000000001{i}'} for i,row in enumerate(rows)]
        for bad in [RuntimeError('missing'),None,{'contract':'v1'},[],{'contract':worker.SEPARATE_ADAPTER,'publisher':'wrong'}]:
            client=Client(bad)
            with self.assertRaisesRegex(RefreshError,'migration_028'):
                stage_or_publish(client,prepared,publish=True)
            self.assertEqual(client.calls,[('GET','rpc/skoda_price_refresh_contract_v2')])
        client=Client(worker.SEPARATE_CONTRACT)
        self.assertEqual(stage_or_publish(client,prepared,publish=True)['published'],4)
        self.assertEqual(client.calls,[('GET','rpc/skoda_price_refresh_contract_v2'),('GET','public_ev_variants'),('POST','extracted_variant_drafts'),('POST','rpc/publish_skoda_price_refresh_v2')])

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
