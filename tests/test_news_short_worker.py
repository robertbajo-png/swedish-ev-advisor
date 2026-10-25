"""Offline budget, one-per-day, proof and restart checks for the short-news worker."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_short_news as worker


class ShortWorkerTests(unittest.TestCase):
    def setUp(self):
        self.remote = Mock()
        self.cfg = {'enabled': True, 'publication_enabled': False, 'daily_limit_micro_usd': 250000,
            'monthly_limit_micro_usd': 5000000, 'daily_article_limit': 1, 'model': 'gpt-6-sol', 'pricing_valid_until': '2099-01-01'}
        self.remote.client.select.return_value = [self.cfg]

    def test_exhausted_daily_or_monthly_budget_never_grants_an_exception(self):
        day = datetime.now(timezone.utc).date().isoformat()
        for spent in (250000, 306898, 5000000):
            with self.subTest(spent=spent), patch.object(worker, 'ledger', return_value=[{'created_at': day, 'charged_micro_usd': spent}]):
                result = worker.budget(self.remote, required=1)
                self.assertFalse(result['allowed'])
                self.assertFalse(worker.budget(self.remote)['allowed'])
                self.assertEqual(result['remaining_micro_usd'], 0)
                self.assertIn('retry_after', result)
        self.remote.client._request.assert_not_called()

    def test_paused_wrong_model_higher_limits_or_wrong_daily_count_block(self):
        for field, value in [('enabled', False), ('model', 'other'), ('daily_limit_micro_usd', 999999),
                             ('monthly_limit_micro_usd', 9999999), ('daily_article_limit', 2)]:
            original = self.cfg[field]
            self.cfg[field] = value
            with self.subTest(field=field), patch.object(worker, 'ledger', return_value=[]):
                self.assertFalse(worker.budget(self.remote, 1000)['allowed'])
            self.cfg[field] = original

    def test_failed_or_interrupted_case_is_not_automatically_retried(self):
        for state in ('running', 'failed'):
            with self.subTest(state=state), patch.object(worker, 'prepare', return_value={'cases': {'model': {'state': state}}}), \
                    patch.object(worker, 'NewsAi') as ai:
                self.assertEqual(worker.run_matrix(self.remote, Mock())['status'], 'blocked_failed_or_interrupted_case')
                ai.assert_not_called()

    def test_missing_or_incomplete_matrix_never_releases_or_buys_an_article(self):
        for state in ({}, {'recipe': worker.RECIPE, 'code_hash': worker.code_hash(), 'cases': {}}):
            self.assertFalse(worker.matrix_valid(self.remote, state))
            with patch.object(worker, 'load_state', return_value=state), patch.object(worker, 'NewsAi') as ai:
                result = worker.daily(self.remote, Mock())
                self.assertEqual(result['status'], 'mixed_format_proofs_required')
                ai.assert_not_called()

    def test_first_failed_case_stops_before_buying_any_other_case(self):
        state = {'cases': {kind: {'state': 'prepared'} for kind in ('model', 'price', 'battery')}, 'passed': False}
        ai = Mock(side_effect=[{'title': 'Private trial'}, {'rejected': True}])
        with patch.object(worker, 'prepare', return_value=state), \
                patch.object(worker, 'NewsAi', return_value=ai), \
                patch.object(worker, 'fetch_item'), patch.object(worker, 'make_brief', return_value={}), \
                patch.object(worker, 'budget', return_value={'allowed': True}), \
                patch.object(worker, 'pair_bound', return_value=1), \
                patch.object(worker, 'ledger', return_value=[]), \
                patch.object(worker, 'checkpoint'), patch.object(worker, 'render_case'), \
                patch.object(worker, 'writer_call', return_value=('writer', {}, 'prompt')), \
                patch.object(worker, 'reviewer_call', return_value=('review', {}, 'prompt')), \
                patch.object(worker, 'precheck', return_value={'passed': False}), \
                patch.object(worker, 'review_check', return_value=['unsupported_claim']), \
                patch.object(worker, 'NewsStore'), patch.object(worker, 'stage'):
            result = worker.run_matrix(self.remote, Mock())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(ai.call_count, 2)
        self.assertEqual(state['cases']['model']['state'], 'failed')
        self.assertEqual(state['cases']['price']['state'], 'prepared')
        self.assertEqual(state['cases']['battery']['state'], 'prepared')

    def test_existing_publication_today_blocks_every_other_format_and_paid_work(self):
        self.cfg['publication_enabled'] = True
        self.remote.public_articles.return_value = [{'published_at': datetime.now(timezone.utc).isoformat()}]
        with patch.object(worker, 'load_state', return_value={}), patch.object(worker, 'matrix_valid', return_value=True), \
                patch.object(worker, 'release_from_matrix') as release, patch.object(worker, 'NewsAi') as ai:
            self.assertEqual(worker.daily(self.remote, Mock())['status'], 'daily_limit')
            release.assert_not_called(); ai.assert_not_called()

    def test_owner_activation_is_required_even_after_passed_tests(self):
        with patch.object(worker, 'load_state', return_value={}), patch.object(worker, 'matrix_valid', return_value=True):
            result = worker.daily(self.remote, Mock())
            self.assertEqual(result['status'], 'awaiting_owner_activation')
        self.remote.put.assert_not_called()
        self.remote.client._request.assert_not_called()

    def test_fake_duplicate_missing_or_unsettled_provider_proofs_rejected(self):
        self.assertIsNone(worker.request_evidence(self.remote, ['same', 'same']))
        self.remote.client.select.return_value = []
        self.assertIsNone(worker.request_evidence(self.remote, ['writer', 'review']))
        rows = [{'id': name, 'stage': stage, 'model': 'gpt-6-sol', 'settled_at': '2026-10-24', 'provider_status': 'completed'}
            for name, stage in [('writer', 'swedish_ev_article'), ('review', 'ev_news_independent_audit')]]
        self.remote.client.select.return_value = rows
        self.assertEqual(len(worker.request_evidence(self.remote, ['writer', 'review'])), 2)
        rows[1]['settled_at'] = None
        self.assertIsNone(worker.request_evidence(self.remote, ['writer', 'review']))

    def test_daily_collection_not_started_with_a_reusable_reviewed_candidate(self):
        self.cfg['publication_enabled'] = True
        self.remote.public_articles.return_value = []
        collector = Mock()
        with patch.object(worker, 'load_state', return_value={}), patch.object(worker, 'matrix_valid', return_value=True), \
                patch.object(worker, 'release_from_matrix', return_value={'published': 1}), patch.object(worker, 'NewsAi') as ai:
            self.assertEqual(worker.daily(self.remote, collector)['published'], 1)
            ai.assert_not_called(); collector.fetch.assert_not_called()

    def test_activation_sql_is_unavailable_before_real_matrix_pass(self):
        with patch.object(worker, 'load_state', return_value={}), self.assertRaisesRegex(ValueError, 'mixed_format_proofs'):
            worker.activation_sql(self.remote)
        self.remote.client._request.assert_not_called()

    def test_activation_sql_does_not_raise_budget_or_activate_notices(self):
        with patch.object(worker, 'load_state', return_value={}), patch.object(worker, 'matrix_valid', return_value=True):
            sql = worker.activation_sql(self.remote)
        self.assertIn('publication_enabled=true', sql)
        self.assertIn('daily_article_limit=1', sql)
        self.assertNotIn('set enabled=true', sql)
        self.assertNotIn('set daily_limit_micro_usd', sql)
        self.assertNotIn('update public.news_notice_release_config', sql)

    def test_changed_release_title_blocks_even_when_body_hash_is_unchanged(self):
        self.cfg['publication_enabled'] = True
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.remote.public_articles.return_value = [{'published_at': yesterday, 'sources': [{'url': worker.VW_URL}]}]
        old = {'content_hash': 'a' * 64, 'title': 'Old title', 'published_at': yesterday,
               'final_url': 'https://www.firefly.com.cn/news/20261023001'}
        item = {'source_id': 'firefly-china-press', 'url': old['final_url'], 'payload': old}
        state = {'cases': {'model': {'brief': {'item': {'url': worker.VW_URL}}},
                          'price': {'brief': {'item': {'url': worker.VW_URL}}},
                          'battery': {'brief': {'item': item}}}}
        fresh = copy.deepcopy(item); fresh['payload']['title'] = 'Changed title'
        with patch.object(worker, 'load_state', return_value=state), patch.object(worker, 'matrix_valid', return_value=True), \
                patch.object(worker, 'fetch_item', return_value=fresh), patch.object(worker, 'stage') as stage:
            result = worker.release_from_matrix(self.remote, Mock())
            self.assertEqual(result['status'], 'source_changed_requires_new_review')
            stage.assert_not_called()


if __name__ == '__main__':
    unittest.main()
