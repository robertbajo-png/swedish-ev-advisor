"""Offline trial safety checks: no network, paid calls, or production writes."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import trial_news_hybrid_launch as trial
from news_ai import NewsBudgetBlocked
from news_launch_hybrid import launch_brief, reviewer_call, writer_call
from news_store import artifact_hash
from preview_news_launch_hybrid import fixture_article, fixture_input


class HybridLiveTrialTests(unittest.TestCase):
    def setUp(self):
        data = json.loads((ROOT / 'tests/fixtures/news_hybrid_launch.json').read_text(encoding='utf-8'))
        from datetime import datetime
        items, sources = fixture_input(data)
        self.brief = launch_brief(items, sources, now=datetime.fromisoformat(data['published_at']))
        self.article = fixture_article(data, self.brief)
        self.remote = Mock()
        self.cfg = {'enabled': False, 'publication_enabled': False, 'model': trial.MODEL,
            'daily_limit_micro_usd': 250000, 'monthly_limit_micro_usd': 5000000,
            'pricing_valid_until': '2026-11-21'}
        self.rows = []
        self.remote.client.select.side_effect = lambda table, **_: (
            [copy.deepcopy(self.cfg)] if table == 'news_ai_config' else [{'enabled': False}]
            if table == 'news_notice_release_config' else copy.deepcopy(self.rows))

    def test_existing_model_strict_hybrid_schema_and_separate_budget_classes(self):
        for call in (writer_call(self.brief), reviewer_call(self.article, self.brief)):
            body = trial.payload(call)
            self.assertEqual(body['model'], 'gpt-5.4-mini')
            self.assertEqual(body['text']['format']['name'], call[0])
            self.assertTrue(body['text']['format']['strict'])
            self.assertFalse(body['store'])
            self.assertNotIn('previous_response_id', body)
        self.assertEqual(trial.STAGES['ev_news_hybrid_launch_review'][0], 'ev_news_independent_audit')

    def test_whole_trial_reserves_for_both_stages_before_writing(self):
        bounds = trial.whole_trial_bound(self.brief)
        self.assertEqual(bounds['total'], bounds['writer'] + bounds['review'])
        self.assertLess(bounds['total'], trial.CAP)
        real = trial.request_bound(trial.payload(reviewer_call(self.article, self.brief)))
        self.assertGreater(bounds['review'], real['maximum_micro_usd'])

    def test_review_bound_covers_long_schema_valid_nested_json(self):
        article = copy.deepcopy(self.article)
        article['paragraphs'] = [copy.deepcopy(article['paragraphs'][0]) for _ in range(7)]
        ids = [f['id'] for f in self.brief['facts']][:5]
        for p in article['paragraphs']:
            p['fact_ids'] = ids
            p['text'] = ('Åäö och\\\"\n' * 30)
        self.assertLess(len(json.dumps(article, ensure_ascii=False).encode()), trial.ARTICLE_BYTES)
        bound = trial.request_bound(trial.payload(reviewer_call(article, self.brief)))
        self.assertLessEqual(bound['maximum_micro_usd'], trial.whole_trial_bound(self.brief)['review'])

    def test_shared_caps_pending_and_notice_switch_fail_closed(self):
        with patch.object(trial, 'authorize'):
            self.assertEqual(trial.readiness(self.remote, False)['unresolved'], 0)
            self.cfg['publication_enabled'] = True
            with self.assertRaises(NewsBudgetBlocked):
                trial.readiness(self.remote, False)
            self.cfg['publication_enabled'] = False
            self.rows = [{'id': 'pending', 'created_at': trial.DATE, 'charged_micro_usd': 2,
                'settled_at': None, 'budget_closed_at': None, 'provider_status': 'reserved'}]
            with self.assertRaises(NewsBudgetBlocked):
                trial.readiness(self.remote, False)

    def test_insufficient_daily_budget_blocks_whole_trial(self):
        self.rows = [{'id': 'old', 'created_at': trial.DATE, 'charged_micro_usd': 240000,
                'settled_at': 'done', 'budget_closed_at': None, 'provider_status': 'completed'}]
        with patch.object(trial, 'authorize'), self.assertRaises(NewsBudgetBlocked):
            trial.readiness(self.remote, False, trial.whole_trial_bound(self.brief)['total'])
        self.remote.client._request.assert_not_called()

    def test_stage_order_retries_and_receipt_before_provider(self):
        report = {'results': [], 'baseline_ids': [], 'baseline_surfaces': {},
                  'bounds': trial.whole_trial_bound(self.brief)}
        with patch.object(trial, 'authorize'):
            with self.assertRaises(NewsBudgetBlocked):
                trial.paid_call(self.remote, report, reviewer_call(self.article, self.brief))
        self.remote.client._request.assert_not_called()
        self.remote.client._request.return_value = {'allowed': True, 'reserved_micro_usd': 20000}
        transport = Mock()
        with patch.object(trial, 'authorize'), patch.object(trial, 'readiness'), \
             patch.object(trial, 'ledger', return_value=[]), patch.object(trial, 'production_surfaces', return_value={}), \
             patch.object(trial, 'receipt', side_effect=RuntimeError('receipt unavailable')):
            with self.assertRaises(RuntimeError):
                trial.paid_call(self.remote, report, writer_call(self.brief), transport)
        transport.assert_not_called()
        self.assertEqual(report['results'][0]['state'], 'dispatch_pending')

    def test_actual_settlement_then_exact_response_parsing(self):
        report = {'results': [], 'baseline_ids': [], 'baseline_surfaces': {},
                  'bounds': trial.whole_trial_bound(self.brief)}
        response = {'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 200},
            'output': [{'content': [{'type': 'output_text', 'text': json.dumps(self.article)}]}]}
        self.remote.client._request.side_effect = [
            {'allowed': True, 'reserved_micro_usd': report['bounds']['writer']},
            {'settled': True, 'charged_micro_usd': 975}]
        with patch.object(trial, 'authorize'), patch.object(trial, 'readiness'), \
             patch.object(trial, 'ledger', return_value=[]), patch.object(trial, 'production_surfaces', return_value={}), \
             patch.object(trial, 'receipt') as receipt:
            result = trial.paid_call(self.remote, report, writer_call(self.brief), Mock(return_value=response))
        self.assertEqual(artifact_hash(result), artifact_hash(self.article))
        self.assertEqual(report['results'][0]['charged_micro_usd'], 975)
        self.assertEqual(receipt.call_count, 3)
        self.assertEqual(self.remote.client._request.call_args.args[1], 'rpc/settle_news_ai')

    def test_unknown_usage_retains_reservation_without_settlement(self):
        report = {'results': [], 'baseline_ids': [], 'baseline_surfaces': {},
                  'bounds': trial.whole_trial_bound(self.brief)}
        self.remote.client._request.return_value = {'allowed': True, 'reserved_micro_usd': 20000}
        with patch.object(trial, 'authorize'), patch.object(trial, 'readiness'), \
             patch.object(trial, 'ledger', return_value=[]), patch.object(trial, 'production_surfaces', return_value={}), \
             patch.object(trial, 'receipt'), self.assertRaises(NewsBudgetBlocked):
            trial.paid_call(self.remote, report, writer_call(self.brief), Mock(return_value={'usage': {}}))
        self.assertEqual(self.remote.client._request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
