"""Offline contracts, not a claim that real price/statistics writing passes."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import trial_news_breadth_r25 as trial
import trial_news_matrix as matrix
from news_ai import NewsBudgetBlocked


class BreadthTrialTests(unittest.TestCase):
    def test_fresh_marker_two_categories_six_calls_no_rewrites_no_old_grant(self):
        names = ['DATE', 'RECIPE', 'TRIAL_ID', 'DATABASE', 'OUTPUT', 'MAX_MICRO_USD', 'MAX_REQUESTS',
                 'REEXTRACT_MODEL', 'MODEL_INPUT', 'INCLUDE_MARKET', 'MAX_REVISIONS', 'EXPECTED_CATEGORIES']
        with patch.multiple(matrix, **{name: getattr(matrix, name) for name in names}):
            trial.configure()
            self.assertEqual(matrix.RECIPE, matrix.EDITORIAL_RECIPE)
            self.assertEqual(matrix.MAX_MICRO_USD, 100000)
            self.assertEqual(matrix.MAX_REQUESTS, 6)
            self.assertEqual(matrix.MAX_REVISIONS, 0)
            self.assertTrue(matrix.REEXTRACT_MODEL)
            self.assertEqual(matrix.expected_categories(), {'priser', 'marknad'})
            self.assertNotIn(matrix.TRIAL_ID, {'2c2869db-70cf-5a4a-a798-a3d6d050612a', '7faef11d-c13c-5695-a79d-843a1388e0f4'})
            self.assertEqual(trial.r21.PARENT_ID, matrix.stable_id('private-news-matrix-r20:2026-10-22'))

    def test_budget_keeps_old_unknown_cost_and_denies_pending_or_insufficient_room(self):
        remote = Mock()
        cfg = {'enabled': False, 'publication_enabled': False, 'daily_limit_micro_usd': 250000,
               'monthly_limit_micro_usd': 5000000, 'model': trial.MODEL, 'pricing_valid_until': '2026-11-21'}
        rows = [{'created_at': '2026-10-22', 'charged_micro_usd': 20868, 'settled_at': None, 'budget_closed_at': 'closed'}]
        remote.client.select.side_effect = lambda table, **kwargs: [cfg] if table == 'news_ai_config' else rows
        with patch('trial_news_matrix.authorize'), patch.object(matrix, 'MAX_MICRO_USD', 100000):
            result = trial.check_budget(remote)
            self.assertTrue(result['allowed'])
            self.assertEqual(result['monthly_used_micro_usd'], 20868)
            rows[0].update(created_at=trial.DATE, charged_micro_usd=160000)
            self.assertFalse(trial.check_budget(remote)['allowed'])
            rows[0].update(charged_micro_usd=1, budget_closed_at=None)
            self.assertFalse(trial.check_budget(remote)['allowed'])
            rows[0]['charged_micro_usd'] = -1
            with self.assertRaisesRegex(NewsBudgetBlocked, 'invalid_or_truncated'):
                trial.check_budget(remote)
        remote.client._request.assert_not_called()
        remote.put.assert_not_called()

    def test_coverage_needs_an_actual_market_qualified_price_not_just_category(self):
        def article(category, facts):
            return {'artifact_hash': 'a', 'payload': {'category': category}, 'checks': [
                {'kind': 'evidence', 'artifact_hash': 'a', 'payload': {'fact_inventory': facts}}]}
        prices = [{'id': 'price', 'statement': 'I Sverige kostar privatleasing från 2995 kronor per månad.',
                   'evidence': 'I Sverige kostar privatleasing från 2995 kronor per månad.'}]
        statistics = [{'origin': 'literal_statistical_field'}] * 3
        report = {'articles': [article('priser', prices), article('marknad', statistics)]}
        self.assertTrue(trial.coverage(report)['passed'])
        before = copy.deepcopy(report)
        report['articles'][0]['checks'][0]['payload']['fact_inventory'] = []
        self.assertFalse(trial.coverage(report)['passed'])
        report = before
        report['articles'][0]['checks'][0]['artifact_hash'] = 'old'
        self.assertFalse(trial.coverage(report)['passed'])

    def test_breadth_does_not_promote_a_failed_normal_gate(self):
        report = {'passed': False, 'articles': []}
        with patch('trial_news_matrix.run'), patch.object(Path, 'read_text', return_value='{}'), \
             patch('trial_news_breadth_r25.json.loads', return_value=report), \
             patch('trial_news_breadth_r25.coverage', return_value={'passed': True}), \
             patch('trial_news_matrix.receipt') as receipt:
            self.assertFalse(trial.run(Mock())['passed'])
            self.assertFalse(receipt.call_args.args[1]['passed'])


if __name__ == '__main__':
    unittest.main()
