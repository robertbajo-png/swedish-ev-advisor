"""No provider calls: approved caps, retained usage and production compatibility."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_budget_policy as policy
from news_ai import NewsBudgetBlocked
import run_short_news as historical
import run_publisher_news as production

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)


class BudgetPolicyTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'enabled': True, 'publication_enabled': True, 'model': 'gpt-6-sol',
                    'daily_limit_micro_usd': 500000, 'monthly_limit_micro_usd': 10000000,
                    'daily_article_limit': 1, 'pricing_valid_until': '2026-11-21'}
        self.rows = []
        self.remote = Mock()
        self.remote.client.select.side_effect = lambda table, **kw: [copy.deepcopy(self.cfg)] if table == 'news_ai_config' else copy.deepcopy(self.rows)
        clock = patch.object(policy, 'datetime', wraps=datetime)
        self.clock = clock.start(); self.clock.now.return_value = NOW; self.addCleanup(clock.stop)

    def charge(self, value, date='2026-11-04T10:00:00+00:00', **extra):
        self.rows.append({'id': str(len(self.rows)), 'created_at': date, 'charged_micro_usd': value,
                          'settled_at': date, 'budget_closed_at': None, 'provider_status': 'completed', **extra})

    def test_old_and_new_exact_pairs_are_supported_during_deployment(self):
        for daily, monthly in policy.APPROVED_LIMITS:
            self.cfg.update(daily_limit_micro_usd=daily, monthly_limit_micro_usd=monthly)
            result = policy.budget(self.remote)
            self.assertTrue(result['allowed'])
            self.assertEqual(result['remaining_micro_usd'], daily)

    def test_mixed_unapproved_or_larger_caps_fail_closed(self):
        for daily, monthly in [(250000, 10000000), (500000, 5000000), (500001, 10000000),
                               (500000, 10000001), (True, 10000000), (0, 0)]:
            self.cfg.update(daily_limit_micro_usd=daily, monthly_limit_micro_usd=monthly)
            result = policy.budget(self.remote)
            self.assertFalse(result['config_valid'])
            self.assertFalse(result['allowed'])
            self.assertEqual(result['remaining_micro_usd'], 0)

    def test_existing_charges_are_not_reset_and_full_pair_must_fit(self):
        self.charge(20868, settled_at=None, budget_closed_at='2026-11-04T11:00:00+00:00', provider_status='reserved')
        self.charge(100000)
        self.charge(200000, date='2026-11-03T10:00:00+00:00')
        before = copy.deepcopy(self.rows)
        result = policy.budget(self.remote, 379132)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['day_spent_micro_usd'], 120868)
        self.assertEqual(result['month_spent_micro_usd'], 320868)
        self.assertFalse(policy.budget(self.remote, 379133)['allowed'])
        self.assertEqual(self.rows, before)
        self.remote.client.upsert.assert_not_called()
        self.remote.publish.assert_not_called()

    def test_monthly_limit_is_independent_and_usage_ambiguity_stops(self):
        self.charge(9900000, date='2026-11-03T10:00:00+00:00')
        self.assertEqual(policy.budget(self.remote)['remaining_micro_usd'], 100000)
        self.assertFalse(policy.budget(self.remote, 100001)['allowed'])
        self.charge(1000, settled_at=None)
        with self.assertRaises(NewsBudgetBlocked): policy.budget(self.remote)

    def test_activation_expiry_model_and_publication_limit_are_not_relaxed(self):
        for key, value in [('enabled', False), ('model', 'unpriced'), ('daily_article_limit', 2),
                           ('daily_article_limit', True), ('pricing_valid_until', '2026-11-04')]:
            with self.subTest(key=key), patch.dict(self.cfg, {key: value}):
                self.assertFalse(policy.budget(self.remote)['allowed'])
        with patch.dict(self.cfg, {'publication_enabled': False}):
            result = policy.budget(self.remote)
            self.assertTrue(result['allowed'])
            self.assertFalse(result['publication_enabled'])

    def test_current_publisher_uses_new_policy_without_changing_historical_budget_authority(self):
        self.assertIs(production.budget, policy.budget)
        self.assertTrue(production.budget(self.remote)['allowed'])
        self.assertFalse(historical.budget(self.remote)['allowed'])
        self.assertEqual(production.DAILY_CANDIDATE_LIMIT, 2)
        self.assertIn('news_budget_policy.py', production.HASH_FILES)


if __name__ == '__main__': unittest.main()
