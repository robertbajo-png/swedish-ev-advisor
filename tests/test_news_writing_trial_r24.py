"""Offline safeguards for the separately authorized private r24 trial."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import trial_news_matrix as matrix
import trial_news_writing_r24 as trial
from news_ai import NewsBudgetBlocked
from news_store import stable_id, EDITORIAL_POLICY, artifact_hash
from render_news_smoke_preview import render


class WritingTrialR24Tests(unittest.TestCase):
    def test_new_day_marker_database_and_recipe_do_not_reuse_the_closed_exception(self):
        names = ['DATE', 'RECIPE', 'TRIAL_ID', 'DATABASE', 'OUTPUT', 'MAX_MICRO_USD', 'MAX_REQUESTS',
                 'REEXTRACT_MODEL', 'MODEL_INPUT', 'INCLUDE_MARKET', 'MAX_REVISIONS']
        with patch.multiple(matrix, **{name: getattr(matrix, name) for name in names}):
            trial.configure()
            self.assertEqual(matrix.DATE, '2026-10-23')
            self.assertEqual(matrix.RECIPE, trial.RECIPE)
            self.assertEqual(matrix.MAX_MICRO_USD, 60000)
            self.assertEqual(matrix.MAX_REQUESTS, 2)
            self.assertEqual(matrix.MAX_REVISIONS, 0)
            self.assertFalse(matrix.INCLUDE_MARKET)
            self.assertFalse(matrix.REEXTRACT_MODEL)
            self.assertEqual(matrix.MODEL_INPUT, trial.model_input)
            self.assertNotEqual(matrix.TRIAL_ID, '2c2869db-70cf-5a4a-a798-a3d6d050612a')
            self.assertNotEqual(matrix.TRIAL_ID, trial.PARENT_ID)
            self.assertNotEqual(matrix.DATABASE, trial.PARENT_DATABASE)

    def test_frozen_fact_parent_stays_on_october_22_after_trial_date_changes(self):
        remote = Mock()
        with patch('trial_news_length_r21.model_input', return_value={'validated': True}) as old:
            self.assertEqual(trial.PARENT_ID, stable_id('private-news-matrix-r20:2026-10-22'))
            self.assertEqual(trial.model_input(remote), {'validated': True})
            old.assert_called_once_with(remote)
            with patch.object(trial.r21, 'PARENT_ID', 'new-date-parent'):
                with self.assertRaisesRegex(NewsBudgetBlocked, 'frozen_parent'):
                    trial.model_input(remote)
        remote.put.assert_not_called()

    def budget_case(self, rows):
        remote = Mock()
        cfg = {'enabled': False, 'publication_enabled': False, 'daily_limit_micro_usd': 250000,
               'monthly_limit_micro_usd': 5000000, 'model': trial.MODEL, 'pricing_valid_until': '2026-11-21'}
        remote.client.select.side_effect = lambda table, **kwargs: [cfg] if table == 'news_ai_config' else rows
        item = {'id': 'item', 'payload': {'publisher': 'Official', 'extraction': {'facts': []}}}
        reference = {'state': 'completed', 'owner_shutdown_verified': True, 'test_allowance_closed': True,
                     'articles': [{'payload': {}}]}
        with patch('trial_news_matrix.authorize'), patch('trial_news_writing_r24.model_input', return_value=item), \
             patch('trial_news_writing_r24.source_technical_facts', return_value=[]), \
             patch('trial_news_writing_r24.source_qualifier_facts', return_value=[]), \
             patch('trial_news_writing_r24.json.loads', return_value=reference), patch.object(Path, 'read_text', return_value='{}'), \
             patch('trial_news_writing_r24.budget_probe', return_value={'writer': 25000, 'audit': 30000}):
            result = trial.check_budget(remote)
        remote.put.assert_not_called()
        remote.client._request.assert_not_called()
        return result

    def test_requires_both_full_reservations_and_preserves_unknown_old_cost(self):
        row = {'id': 'old', 'created_at': '2026-10-22', 'charged_micro_usd': 20868,
               'settled_at': None, 'budget_closed_at': '2026-10-22'}
        result = self.budget_case([row])
        self.assertTrue(result['allowed'])
        self.assertEqual(result['monthly_used_micro_usd'], 20868)
        self.assertEqual(result['daily_used_micro_usd'], 0)
        row.update(created_at=trial.DATE, charged_micro_usd=200000)
        self.assertFalse(self.budget_case([row])['allowed'])

    def test_unsettled_unknown_truncated_or_negative_ledger_fails_closed(self):
        row = {'id': 'pending', 'created_at': trial.DATE, 'charged_micro_usd': 1000,
               'settled_at': None, 'budget_closed_at': None}
        self.assertFalse(self.budget_case([row])['allowed'])
        for rows in [[{**row, 'charged_micro_usd': -1}], [row] * 1000]:
            with self.assertRaisesRegex(NewsBudgetBlocked, 'invalid_or_truncated'):
                self.budget_case(rows)

    def test_private_preview_requires_three_current_hash_bound_reviewed_checks(self):
        article = {'status': 'draft', 'artifact_hash': 'hash', 'payload': {
            'title': 'Privat prov', 'intro': 'Testtext.', 'paragraphs': [], 'sources': [],
            'editorial_recipe': matrix.EDITORIAL_RECIPE}, 'checks': [
                {'kind': kind, 'passed': True, 'artifact_hash': 'hash', 'payload': {
                    'audit_performed': True, 'policy_version': EDITORIAL_POLICY}}
                for kind in ['evidence', 'editorial', 'originality']]}
        article['artifact_hash'] = artifact_hash(article['payload'])
        for check in article['checks']:
            check['artifact_hash'] = article['artifact_hash']
        self.assertIn('Validerat privat utkast', render(article))
        self.assertNotIn('Godk&auml;nd testartikel', render(article))
        self.assertIn('Inte publicerad', render(article))
        article['checks'][0]['artifact_hash'] = 'older-text'
        self.assertNotIn('Validerat privat utkast', render(article))
        article['checks'][0]['artifact_hash'] = article['artifact_hash']
        article['checks'][0]['passed'] = False
        self.assertNotIn('Validerat privat utkast', render(article))
        article['checks'][0]['passed'] = True
        article['payload']['intro'] = 'Changed after review.'
        self.assertNotIn('Validerat privat utkast', render(article))
        self.assertNotIn('Validerat privat utkast', render(article, offline_reference=True))


if __name__ == '__main__':
    unittest.main()
