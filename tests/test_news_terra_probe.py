"""Synthetic Terra transport/one-shot checks. No keys, paid calls or publication."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import trial_news_terra as trial
import test_news_publisher_articles as fixtures
from test_news_official_operation import fixture as official_fixture
from news_ai import NewsBudgetBlocked
from news_model_policy import SUPPORTED_MODELS
from news_store import artifact_hash


class TerraProbeTests(unittest.TestCase):
    def setUp(self):
        implicit_client = patch('news_ai.SupabaseRestClient', side_effect=AssertionError('offline_probe_created_database_client'))
        implicit_client.start()
        self.addCleanup(implicit_client.stop)
        self.bundle, self.packet = official_fixture()
        now = datetime.now(timezone.utc).isoformat()
        for item in self.bundle['items']:
            item['payload'].update(published_at=now, fetched_at=now)
        self.bundle['bundle_hash'] = artifact_hash({k: v for k, v in self.bundle.items() if k != 'bundle_hash'})
        self.packet['extraction']['event']['date'] = now[:10]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'private'
        self.source_file = Path(self.temp.name) / 'synthetic.json'
        self.source_file.write_text(json.dumps({'bundle': self.bundle, 'bundle_hash': artifact_hash(self.bundle)}), encoding='utf-8')
        self.remote = Mock()

    def prepare(self):
        with patch.object(trial, 'budget', return_value={'allowed': True}):
            result = trial.prepare(self.remote, self.source_file, self.directory)
        self.manifest = json.loads((self.directory / 'manifest.json').read_text(encoding='utf-8'))
        self.remote.client.select.return_value = [{'closed_at': None, 'manifest_hash': artifact_hash(self.manifest)}]
        return result

    def rpc(self, method, path, body):
        self.assertEqual(method, 'POST')
        if path == 'rpc/reserve_news_terra_test':
            return {'allowed': True, 'reserved_micro_usd': (body['input_bound'] * 5 + body['output_bound'] * 10 + 1) // 2}
        if path == 'rpc/settle_news_terra_test':
            return {'settled': True, 'charged_micro_usd': 1000}
        self.assertEqual(path, 'rpc/close_news_terra_test')
        return {'closed': True}

    def response(self, value):
        return {'status': 'completed', 'model': trial.MODEL, 'service_tier': 'default',
                'output': [{'content': [{'type': 'output_text', 'text': json.dumps(value)}]}]}

    def test_exact_model_stage_rates_and_no_provider_storage(self):
        body = trial.payload(('swedish_ev_article', {}, 'Synthetic text'))
        self.assertEqual(body['model'], 'gpt-6.1-terra')
        self.assertIs(body['store'], False)
        self.assertEqual(body['max_output_tokens'], 2000)
        self.assertEqual(body['reasoning']['effort'], 'low')
        self.assertEqual(body['prompt_cache_options'], {'mode': 'explicit', 'ttl': '30m'})
        bound = trial.request_contract(body)
        self.assertEqual(bound['maximum_micro_usd'], (bound['input_bound'] * 5 + 20000 + 1) // 2)
        self.assertNotIn(trial.MODEL, SUPPORTED_MODELS)
        for patch_value in ({'model': 'gpt-6-sol'}, {'service_tier': 'fast'}, {'store': True}, {'max_output_tokens': 2001}):
            with self.assertRaises(NewsBudgetBlocked):
                trial.request_contract({**body, **patch_value})

    def test_preparation_is_local_private_with_frozen_source_and_full_pair_budget(self):
        result = self.prepare()
        self.assertEqual(result['paid_calls'], 0)
        self.assertLessEqual(result['bounds']['total_micro_usd'], trial.CAP)
        self.assertFalse(self.manifest['publish'])
        self.remote.put.assert_not_called()
        self.remote.client._request.assert_not_called()
        with self.assertRaises(NewsBudgetBlocked):
            trial.prepare(self.remote, self.source_file, self.directory)

    def test_stale_or_changed_source_does_not_prepare(self):
        with patch.object(trial, 'evidence_readiness', return_value={'ready': False}):
            with self.assertRaises(NewsBudgetBlocked): trial.plan(self.bundle)
        source = json.loads(self.source_file.read_text(encoding='utf-8'))
        source['bundle_hash'] = 'changed'
        self.source_file.write_text(json.dumps(source), encoding='utf-8')
        with self.assertRaises(NewsBudgetBlocked): trial.prepare(self.remote, self.source_file, self.directory)
        self.remote.client._request.assert_not_called()

    def test_denied_reservation_cannot_call_provider(self):
        self.prepare()
        self.remote.client._request.return_value = {'allowed': False}
        transport = Mock()
        with self.assertRaises(NewsBudgetBlocked):
            trial.paid_call(self.remote, self.manifest, {'calls': []}, self.directory,
                           trial.writer_call(self.bundle), transport)
        transport.assert_not_called()

    def test_one_writer_and_independent_review_stay_in_sqlite_and_cannot_replay(self):
        self.prepare()
        output = fixtures.encoded_fixture(self.bundle, self.packet)
        transport = Mock(side_effect=[self.response(output), self.response({'synthetic_review': True})])
        self.remote.client._request.side_effect = self.rpc
        with patch.object(trial, 'refresh_bundle', return_value=self.bundle), \
             patch.object(trial, 'precheck', return_value={'passed': True, 'word_count': 160, 'errors': []}), \
             patch.object(trial, 'check_review', return_value=[]):
            result = trial.run(self.remote, self.directory, transport=transport)
        self.assertEqual(result['state'], 'passed_private')
        self.assertEqual(result['paid_calls'], 2)
        self.assertEqual(result['published'], 0)
        self.assertTrue(result['permit_closed'])
        self.remote.put.assert_not_called()
        self.assertTrue((self.directory / 'private.sqlite').exists())
        with self.assertRaises(NewsBudgetBlocked): trial.run(self.remote, self.directory, transport=transport)
        self.assertEqual(transport.call_count, 2)

    def test_failed_precheck_does_not_buy_a_review_or_rewrite(self):
        self.prepare()
        transport = Mock(return_value=self.response(fixtures.encoded_fixture(self.bundle, self.packet)))
        self.remote.client._request.side_effect = self.rpc
        with patch.object(trial, 'refresh_bundle', return_value=self.bundle), \
             patch.object(trial, 'precheck', return_value={'passed': False, 'word_count': 160, 'errors': ['synthetic_rejection']}):
            result = trial.run(self.remote, self.directory, transport=transport)
        self.assertEqual(result['state'], 'quarantined')
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(result['published'], 0)
        self.assertTrue(result['permit_closed'])

    def test_missing_permit_and_edited_code_cannot_buy(self):
        self.prepare()
        transport = Mock()
        self.remote.client.select.return_value = []
        with self.assertRaises(NewsBudgetBlocked): trial.run(self.remote, self.directory, transport=transport)
        with patch.object(trial, 'code_hash', return_value='different'):
            with self.assertRaises(NewsBudgetBlocked): trial.run(self.remote, self.directory, transport=transport)
        transport.assert_not_called()
        self.remote.client._request.assert_not_called()

    def test_changed_source_closes_permit_without_provider(self):
        self.prepare()
        self.remote.client._request.side_effect = self.rpc
        transport = Mock()
        with patch.object(trial, 'refresh_bundle', return_value=self.bundle), \
             patch.object(trial, 'same_sources', return_value=False):
            result = trial.run(self.remote, self.directory, transport=transport)
        self.assertEqual(result['state'], 'blocked_or_failed')
        self.assertEqual(result['paid_calls'], 0)
        self.assertTrue(result['permit_closed'])
        transport.assert_not_called()


if __name__ == '__main__': unittest.main()
