import copy
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_preflight import run
from news_engine import registry


class NewsPreflightTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'SUPABASE_URL': 'https://test.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': 'test-key',
            'OPENAI_API_KEY': 'test-key', 'NEWS_OPENAI_MODEL': 'gpt-5.4-mini',
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        loader = patch('news_preflight.load_local_env')
        loader.start()
        self.addCleanup(loader.stop)
        self.cfg = {
            'enabled': False, 'publication_enabled': False, 'daily_limit_micro_usd': 250000,
            'monthly_limit_micro_usd': 5000000, 'daily_article_limit': 2, 'model': 'gpt-5.4-mini',
            'pricing_valid_until': (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat(),
        }
        self.client = Mock()
        self.client.select.side_effect = lambda table, **kwargs: [copy.deepcopy(self.cfg)] if table == 'news_ai_config' else []
        factory = patch('news_preflight.SupabaseRestClient', return_value=self.client)
        factory.start()
        self.addCleanup(factory.stop)

    def test_offline_configuration_is_not_release_ready(self):
        self.assertFalse(run()['ready'])
        self.client.select.assert_not_called()

    def test_collection_can_run_without_ai_key_or_activation(self):
        os.environ.pop('OPENAI_API_KEY')
        result = run(remote=True, mode='collect')
        self.assertTrue(result['ready'], result)
        self.assertFalse(result['budget']['enabled'])

    def test_disabled_switches_block_paid_publication(self):
        result = run(remote=True)
        self.assertFalse(result['ready'])
        self.assertIn('news_budget_disabled', result['errors'])
        self.assertIn('news_publication_disabled', result['errors'])

    def test_unsettled_usage_warns_collection_but_blocks_editorial_and_publication(self):
        self.cfg.update(enabled=True, publication_enabled=True)
        pending = {'id': 'unresolved', 'stage': 'swedish_ev_article', 'created_at': '2026-10-01', 'charged_micro_usd': 20868}
        self.client.select.side_effect = lambda table, **kwargs: ([copy.deepcopy(self.cfg)] if table == 'news_ai_config'
            else [pending] if table == 'news_ai_requests' and kwargs.get('filters', {}).get('settled_at') == 'is.null' else [])
        result = run(remote=True, mode='collect')
        self.assertTrue(result['ready'], result)
        self.assertEqual(result['oldest_unsettled_request'], pending)
        self.assertIn('news_unsettled_request_requires_reconciliation', result['warnings'])
        for mode in ['editorial', 'publish']:
            result = run(remote=True, mode=mode)
            self.assertFalse(result['ready'])
            self.assertIn('news_unsettled_request_requires_reconciliation', result['errors'])

    def test_editorial_can_be_enabled_without_publication(self):
        self.cfg['enabled'] = True
        self.assertTrue(run(remote=True, mode='editorial')['ready'])
        self.assertFalse(run(remote=True)['ready'])

    def test_conservative_closure_warns_without_claiming_known_usage_or_enabling_publication(self):
        self.cfg['enabled'] = True
        closed = {'id': 'owner-reviewed', 'created_at': '2026-10-01', 'stage': 'swedish_ev_article',
                  'charged_micro_usd': 20868, 'budget_closed_at': '2026-10-02'}
        self.client.select.side_effect = lambda table, **kwargs: ([copy.deepcopy(self.cfg)] if table == 'news_ai_config'
            else [closed] if table == 'news_ai_requests' and kwargs.get('filters', {}).get('budget_closed_at') == 'not.is.null' else [])
        result = run(remote=True, mode='editorial')
        self.assertTrue(result['ready'], result)
        self.assertIsNone(result['oldest_unsettled_request'])
        self.assertEqual(result['latest_conservative_budget_closure'], closed)
        self.assertIn('unknown_usage_full_reservation_still_counted', result['warnings'])
        self.assertFalse(result['budget']['publication_enabled'])
        self.assertIn('news_publication_disabled', run(remote=True, mode='publish')['errors'])
        self.client._request.assert_not_called()
        self.client.upsert.assert_not_called()

    def test_missing_budget_closure_migration_fails_closed_even_for_collection_preflight(self):
        def select(table, **kwargs):
            if 'budget_closed_at' in kwargs.get('filters', {}):
                raise RuntimeError('budget_closed_at column missing')
            return [copy.deepcopy(self.cfg)] if table == 'news_ai_config' else []
        self.client.select.side_effect = select
        result = run(remote=True, mode='collect')
        self.assertFalse(result['ready'])
        self.assertIn('news_schema_unavailable:RuntimeError', result['errors'])
        self.client._request.assert_not_called()
        self.client.upsert.assert_not_called()

    def test_missing_configuration_or_schema_is_not_ready(self):
        self.client.select.side_effect = lambda table, **kwargs: []
        self.assertIn('news_budget_configuration_missing', run(remote=True)['errors'])
        self.client.select.side_effect = RuntimeError('database unavailable')
        self.assertIn('news_schema_unavailable:RuntimeError', run(remote=True)['errors'])

    def test_expired_pricing_or_raised_budget_prevents_publication(self):
        self.cfg.update(enabled=True, publication_enabled=True)
        self.assertTrue(run(remote=True)['ready'])
        for key, value, error in [
            ('daily_limit_micro_usd', 250001, 'news_budget_outside_owner_approval'),
            ('monthly_limit_micro_usd', 5000001, 'news_budget_outside_owner_approval'),
            ('pricing_valid_until', '2000-01-01', 'news_pricing_expired'),
            ('model', 'unpriced-model', 'news_model_unpriced'),
        ]:
            previous = self.cfg[key]
            self.cfg[key] = value
            result = run(remote=True)
            self.assertFalse(result['ready'], result)
            self.assertIn(error, result['errors'])
            self.cfg[key] = previous

    def test_official_source_profile_never_enables_secondary_publishers(self):
        with patch.dict(os.environ, {'NEWS_SOURCE_PROFILE': 'official'}):
            sources = registry()
        enabled = [source for source in sources if source['enabled']]
        self.assertGreaterEqual(len(enabled), 2)
        for source in enabled:
            self.assertEqual(source['kind'], 'primary')
            self.assertEqual(source['collection_method'], 'pressroom_index')

    def test_invalid_source_profile_fails_closed(self):
        with patch.dict(os.environ, {'NEWS_SOURCE_PROFILE': 'typo'}):
            with self.assertRaises(ValueError): registry()


if __name__ == '__main__':
    unittest.main()
