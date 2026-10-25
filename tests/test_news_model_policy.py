"""Offline model migration checks; provider and database are test doubles."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_ai import MODEL, NewsAi, NewsBudgetBlocked
from news_model_policy import DEFAULT_MODEL, reservation_micro_usd, selected_model
from news_preflight import run


class NewsModelPolicyTests(unittest.TestCase):
    def test_sol_default_does_not_rewrite_historical_trial_pin(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(selected_model(), 'gpt-6-sol')
        self.assertEqual(MODEL, 'gpt-5.4-mini')
        self.assertEqual(reservation_micro_usd('gpt-6-sol', 1000, 500), 10000)
        self.assertEqual(reservation_micro_usd(MODEL, 1000, 500), 3000)
        for model in ('gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-luna', 'unpriced'):
            with self.assertRaises(ValueError):
                reservation_micro_usd(model, 1000, 500)

    def test_sol_writing_and_independent_review_keep_strict_bound_contracts(self):
        client, transport = Mock(), Mock()
        client.select.return_value = []
        client._request.side_effect = lambda method, path, body: {'allowed': True} if path.endswith('reserve_news_ai') else {'settled': True}
        transport.return_value = {'status': 'completed', 'model': DEFAULT_MODEL, 'service_tier': 'default',
            'usage': {'input_tokens': 100, 'output_tokens': 200},
            'output': [{'content': [{'type': 'output_text', 'text': '{"ok":true}'}]}]}
        with patch('news_ai.load_local_env'), patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True):
            for name, effort in [('ev_news_hybrid_launch_write', 'low'), ('ev_news_hybrid_launch_review', 'none')]:
                self.assertEqual(NewsAi(client, transport, cache_enabled=False)(name, {}, 'source facts'), {'ok': True})
                body = transport.call_args.args[0]
                self.assertEqual(body['model'], DEFAULT_MODEL)
                self.assertEqual(body['reasoning']['effort'], effort)
                self.assertEqual(body['prompt_cache_options'], {'mode': 'explicit', 'ttl': '30m'})
                self.assertEqual(body['max_output_tokens'], 2500)
                self.assertEqual(body['text']['format']['name'], name)
                self.assertTrue(body['text']['format']['strict'])
                self.assertFalse(body['store'])
                self.assertNotIn('previous_response_id', body)

    def test_pinned_model_mismatch_or_denied_server_contract_never_calls_provider(self):
        client, transport = Mock(), Mock()
        client.select.return_value = []
        client._request.return_value = {'allowed': False}
        with patch('news_ai.load_local_env'), patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True):
            with self.assertRaises(NewsBudgetBlocked):
                NewsAi(client, transport, model=MODEL)('swedish_ev_article', {}, 'facts')
            with self.assertRaises(NewsBudgetBlocked):
                NewsAi(client, transport)('swedish_ev_article', {}, 'facts')
        transport.assert_not_called()

    def test_preflight_accepts_priced_sol_but_requires_matching_server_and_keeps_publication_off(self):
        config = {'enabled': True, 'publication_enabled': False, 'model': DEFAULT_MODEL,
            'daily_limit_micro_usd': 250000, 'monthly_limit_micro_usd': 5000000,
            'daily_article_limit': 2, 'pricing_valid_until': '2099-01-01'}
        client = Mock()
        client.select.side_effect = lambda table, **_: [config] if table == 'news_ai_config' else []
        env = {'SUPABASE_URL': 'https://test.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': 'test', 'OPENAI_API_KEY': 'test'}
        with patch.dict(os.environ, env, clear=True), patch('news_preflight.load_local_env'), \
             patch('news_preflight.SupabaseRestClient', return_value=client):
            self.assertTrue(run(True, 'editorial')['ready'])
            self.assertIn('news_publication_disabled', run(True, 'publish')['errors'])
            config['model'] = MODEL
            self.assertIn('news_model_configuration_mismatch', run(True, 'editorial')['errors'])
        client._request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
