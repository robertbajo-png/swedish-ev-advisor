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
from news_publisher_articles import publisher_scope_errors, writer_call, reviewer_call, precheck
from news_store import artifact_hash


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


class StableEventSchemaTests(unittest.TestCase):
    def test_portable_strict_schema_preserves_local_numeric_and_array_limits(self):
        from news_ai import NewsAi
        from news_editorial import RATING
        b, p = fixtures.fixture()
        ai = NewsAi.__new__(NewsAi)
        ai.model, ai.output_limits = 'gpt-6-sol', worker.LIMITS
        def inspect(node):
            if isinstance(node, dict):
                self.assertFalse({'minimum','maximum','minItems','maxItems'} & set(node))
                if 'properties' in node:
                    self.assertEqual(node['additionalProperties'], False)
                    self.assertEqual(set(node['required']), set(node['properties']))
                for value in node.values(): inspect(value)
            elif isinstance(node, list):
                for value in node: inspect(value)
        for call in (writer_call(b), reviewer_call(b,p)):
            inspect(call[1])
            self.assertTrue(ai.payload(*call)['text']['format']['strict'])
        self.assertEqual(RATING, {'type':'number','minimum':0,'maximum':1})
        for change in ('rating', 'facts', 'paragraphs', 'support'):
            invalid = copy.deepcopy(p)
            if change == 'rating': invalid['extraction']['significance'] = 9
            if change == 'facts': invalid['extraction']['facts'] *= 2
            if change == 'paragraphs': invalid['article']['paragraphs'] *= 2
            if change == 'support': invalid['extraction']['facts'][0]['support'] *= 3
            self.assertFalse(precheck(b,invalid,fixtures.NOW)['passed'],change)

    def test_untrusted_quoted_headline_is_input_data_not_json_schema(self):
        import json
        b, p = fixtures.fixture()
        title = 'Synthetic maker presents "taxi" version: \u00e9lectric cars'
        for item in b['items']: item['payload']['title'] = title
        b['bundle_hash'] = artifact_hash({k:v for k,v in b.items() if k != 'bundle_hash'})
        _, schema, prompt = writer_call(b)
        self.assertEqual(schema['properties']['extraction']['properties']['event']['properties']['subject'], {'type':'string'})
        self.assertNotIn(title, json.dumps(schema, ensure_ascii=False))
        self.assertEqual(json.loads(prompt.partition('\n')[2])['report_subject'], title)
        p['extraction']['event']['subject'] = title
        self.assertNotIn('publisher_event_identity_invalid', precheck(b, p, fixtures.NOW)['errors'])
        p['extraction']['event']['subject'] = 'A different event'
        self.assertIn('publisher_event_identity_invalid', precheck(b, p, fixtures.NOW)['errors'])


if __name__ == '__main__':
    unittest.main()
