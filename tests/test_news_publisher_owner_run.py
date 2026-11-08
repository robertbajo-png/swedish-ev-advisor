"""Synthetic owner-run limits and lexical-event checks; never paid approvals."""
import copy
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_publisher_news as worker
import test_news_publisher_articles as fixtures
from news_publisher_articles import publisher_scope_errors


class OwnerRunTests(unittest.TestCase):
    def test_default_limit_and_exact_date_required_for_more_candidates(self):
        with patch.object(worker, 'now_iso', return_value=fixtures.NOW.isoformat()):
            self.assertEqual(worker.approved_candidate_limit(), 2)
            self.assertEqual(worker.approved_candidate_limit(6, '2026-11-01'), 6)
            for limit, day in ((6, None), (6, '2026-10-31'), (6, '2026-11-02'), (7, '2026-11-01'),
                               (True, '2026-11-01'), (0, '2026-11-01')):
                with self.subTest(limit=limit, day=day), self.assertRaises(ValueError):
                    worker.approved_candidate_limit(limit, day)

    def setup(self, stack, folder, *, allowance=250000, previous=2):
        remote, b, p, ai = fixtures.PublisherLifecycleTests().setup_environment(stack, folder, allowance=allowance)
        for index in range(previous):
            remote.put('news_ingestion_runs', {'id': 'previous-' + str(index), 'payload': {
                'kind': 'short_daily', 'recipe': worker.RECIPE, 'state': 'quarantined',
                'started_at': fixtures.NOW.isoformat(), 'url': 'https://synthetic.invalid/old-' + str(index)}})
        remote.put('news_items', {**b['items'][0], 'status': 'collected'})
        stack.enter_context(patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}))
        stack.enter_context(patch.object(worker, 'NewsAi', return_value=ai))
        stack.enter_context(patch.object(worker, 'collect_bundle', return_value=b))
        stack.enter_context(patch.object(worker, 'refresh_bundle', return_value=copy.deepcopy(b)))
        stack.enter_context(patch.object(worker, 'models_for_news', return_value={}))
        stack.enter_context(patch.object(worker, 'queue_verification'))
        stack.enter_context(patch.object(worker, 'export_public', return_value={'synthetic': True}))
        return remote, b, ai

    def test_explicit_owner_run_counts_existing_attempts_and_still_needs_review(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, ai = self.setup(stack, folder)
            self.assertEqual(worker.daily(remote, None)['status'], 'daily_attempt_limit')
            self.assertEqual(ai.calls, [])
            result = worker.daily(remote, None, max_candidates=6, owner_day='2026-11-01')
            self.assertEqual(result['status'], 'published', result)
            self.assertEqual(ai.calls, ['swedish_ev_article', 'ev_news_independent_audit'])
            runs = [r['payload'] for r in remote.rows('news_ingestion_runs') if r['payload'].get('candidate_limit') == 6]
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]['owner_approved_day'], '2026-11-01')
            self.assertEqual(worker.daily(remote, None, max_candidates=6, owner_day='2026-11-01')['status'], 'daily_limit')

    def test_owner_run_cannot_exceed_six_or_spend_without_full_pair_allowance(self):
        for previous, allowance, expected in ((6, 250000, 'daily_attempt_limit'), (2, 1, 'deferred_budget')):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                remote, b, ai = self.setup(stack, folder, previous=previous, allowance=allowance)
                result = worker.daily(remote, None, max_candidates=6, owner_day='2026-11-01')
                self.assertEqual(result['status'], expected, result)
                self.assertEqual(ai.calls, [])

    def test_private_trials_do_not_inherit_production_attempt_override(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, ai = self.setup(stack, folder)
            with self.assertRaisesRegex(ValueError, 'private_trial_limit_unchanged'):
                worker.perform(remote, b, private=True, ai=ai, max_candidates=6, owner_day='2026-11-01')
            self.assertEqual(ai.calls, [])


class ShowingEventTests(unittest.TestCase):
    def article(self, text):
        return {'title': 'Syntetiskt underlag', 'title_fact_ids': ['f1'],
                'intro': 'Syntetisk ingress.', 'intro_fact_ids': ['f1'],
                'paragraphs': [{'text': text, 'fact_ids': ['f1'], 'kind': 'reporting'}]}

    def test_source_bound_showing_can_be_worded_as_generic_presentation(self):
        facts = [{'id': 'f1', 'statement': 'Tillverkaren har visat två skalmodeller.',
                  'evidence': 'The manufacturer unveiled two scale models of the planned vehicle.'}]
        self.assertEqual(publisher_scope_errors(self.article('Bilen har presenterats som skalmodell.'), facts), [])

    def test_showing_is_never_orders_launch_deliveries_or_an_unbound_announcement(self):
        facts = [{'id': 'f1', 'statement': 'Tillverkaren har visat två skalmodeller.',
                  'evidence': 'The manufacturer unveiled two scale models of the planned vehicle.'}]
        for text in ('Modellen kan beställas.', 'Modellen har lanserats.', 'Bilen levereras nu.'):
            self.assertTrue(publisher_scope_errors(self.article(text), facts), text)
        for statement, evidence in (('Siffrorna visar större intresse.', 'Measurements show increased interest.'),
                                    ('Tillverkaren planerar en modell.', 'The manufacturer unveiled the model.'),
                                    ('Tillverkaren har visat två skalmodeller.', 'There are two objects in a room.')):
            self.assertIn('claim_event_mismatch:p0:announcement', publisher_scope_errors(
                self.article('Bilen har presenterats som skalmodell.'),
                [{'id': 'f1', 'statement': statement, 'evidence': evidence}]))


if __name__ == '__main__':
    unittest.main()
