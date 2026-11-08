"""Synthetic v3 policy regressions; no network, paid calls or live approvals."""
import copy
from contextlib import closing, ExitStack
from datetime import timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_publisher_articles as fixtures
from test_news_reported_articles import reported_fixture, rehash
from news_publisher_articles import (precheck, check_review, writer_call, reviewer_call,
                                    evidence_readiness, stage, pair_bound, LIMITS)
from news_reporting_policy import RECIPE, HISTORICAL_RECIPES, sensitive_fact
from news_publisher_sources import bundle_errors, refresh_bundle, same_sources
from news_ai import NewsAi
from news_store import NewsStore, artifact_hash
import run_publisher_news as worker


def single_fixture():
    bundle, packet, _ = reported_fixture()
    bundle['items'] = bundle['items'][:1]
    bundle['provenance'] = []
    bundle['evidence_basis'] = 'editorial_single_source'
    for fact in packet['extraction']['facts']:
        fact['support'] = fact['support'][:1]
        fact['statement'] = fact['statement'].replace(' och The Driven', '')
    packet['article']['intro'] = packet['article']['intro'].replace(' och The Driven', '')
    rehash(bundle)
    review = fixtures.accepted_review(bundle, packet)
    review['reported_not_verified'] = True
    return bundle, packet, review


def short_packet(packet):
    p = copy.deepcopy(packet)
    p['article']['paragraphs'] = p['article']['paragraphs'][:1]
    # Two source-grounded facts, one of which includes the shared method/conditions.
    facts = p['extraction']['facts']
    facts[1]['statement'] += ' ' + facts[2]['statement']
    facts[1]['support'] += facts[2]['support']
    p['extraction']['facts'] = facts[:2]
    p['article']['intro_fact_ids'] = ['f1', 'f2']
    p['article']['paragraphs'][0]['fact_ids'] = ['f2']
    return p


class FlexiblePublisherPolicyTests(unittest.TestCase):
    def test_new_recipe_preserves_history_without_promoting_old_proofs(self):
        self.assertNotEqual(RECIPE, 'news-article-review-2026-11-v2')
        self.assertIn('news-article-review-2026-11-v2', HISTORICAL_RECIPES)
        self.assertIsNone(worker.reviewed_record(None, {'source_id': 'carnewschina', 'state': 'passed',
            'kind': 'short_daily', 'recipe': 'news-article-review-2026-11-v2'}))

    def test_low_scores_do_not_veto_supported_news(self):
        b, p = fixtures.fixture()
        p['extraction'].update(significance=0, sweden_relevance=0)
        result = precheck(b, p, fixtures.NOW)
        self.assertTrue(result['passed'], result)
        self.assertEqual(precheck(b, p, fixtures.NOW + timedelta(days=8))['passed'], False)

    def test_short_news_accepts_two_facts_and_one_paragraph_without_padding(self):
        b, p = fixtures.fixture()
        p = short_packet(p)
        checked = precheck(b, p, fixtures.NOW)
        self.assertTrue(80 <= checked['word_count'] < 150)
        self.assertTrue(checked['passed'], checked)
        p['article']['paragraphs'] = fixtures.fixture()[1]['article']['paragraphs']
        self.assertIn('publisher_standard_article_needs_three_facts', precheck(b, p, fixtures.NOW)['errors'])

    def test_too_short_too_long_duplicate_or_unsupported_facts_still_fail(self):
        for kind in ('short', 'long', 'duplicate', 'number'):
            b, p = fixtures.fixture()
            if kind == 'short': p['article']['paragraphs'] = [{'text': 'Kort text.', 'fact_ids': ['f1'], 'kind': 'reporting'}]
            if kind == 'long': p['article']['intro'] += ' extra' * 260
            if kind == 'duplicate': p['extraction']['facts'][1]['statement'] = p['extraction']['facts'][0]['statement']
            if kind == 'number': p['extraction']['facts'][0]['statement'] += ' 999 kWh.'
            self.assertFalse(precheck(b, p, fixtures.NOW)['passed'], kind)

    def test_one_registered_newsroom_can_report_ordinary_developments(self):
        b, p, review = single_fixture()
        self.assertEqual(bundle_errors(b, fixtures.NOW), [])
        self.assertTrue(evidence_readiness(b, fixtures.NOW)['ready'])
        checked = precheck(b, p, fixtures.NOW)
        self.assertTrue(checked['passed'], checked)
        self.assertEqual(check_review(b, p, review), [])
        schema = reviewer_call(b, p)[1]
        self.assertNotIn('editorial_independence', schema['required'])
        self.assertIn('reported_not_verified', schema['required'])

    def test_sensitive_topics_require_more_than_a_single_editorial_source(self):
        b, p, _ = single_fixture()
        for statement in ('Bilen kan beställas i Sverige.', 'Bilen har upp till 600 km WLTP-räckvidd.',
                          'Laddning från 10 till 80 procent tar 20 minuter.', 'Batteriet rymmer 90 kWh.',
                          'Modellen återkallas på grund av brandrisk.', 'Förbrukningen är 14 kWh per 100 km.',
                          'Priset är 600000 kronor.', 'Bilen accelererar till 100 km i timmen på 5 sekunder.',
                          'Bilen erbjuds på den svenska marknaden.', 'Modellen lanseras i Sverige nästa år.'):
            with self.subTest(statement=statement):
                self.assertTrue(sensitive_fact({'statement': statement, 'range_cycle': 'NOT_APPLICABLE'}))
                changed = copy.deepcopy(p)
                changed['extraction']['facts'][0]['statement'] = 'Enligt CarNewsChina ' + statement
                self.assertIn('publisher_reported_fact_needs_two_editors:f1',
                              precheck(b, changed, fixtures.NOW)['errors'])

    def test_critical_fact_requires_two_sources_even_when_not_marked_central(self):
        b, p, _ = reported_fixture()
        f = p['extraction']['facts'][1]
        f['statement'] += ' Batterikapaciteten uppges vara 90 kWh.'
        f['support'] = f['support'][:1]
        self.assertFalse(f['central'])
        self.assertIn('publisher_reported_fact_needs_two_editors:f2', precheck(b, p, fixtures.NOW)['errors'])

    def test_a_primary_for_another_fact_does_not_validate_a_sensitive_editorial_detail(self):
        b, p = fixtures.fixture()
        f = p['extraction']['facts'][1]
        f['statement'] = 'Enligt CarNewsChina uppges batterikapaciteten vara 90 kWh.'
        f['support'][0]['source'] = 's0'
        self.assertIn('publisher_reported_fact_needs_two_editors:f2', precheck(b, p, fixtures.NOW)['errors'])

    def test_two_literal_sources_can_support_sensitive_fact_but_not_conflicting_values(self):
        b, p, review = reported_fixture()
        f = p['extraction']['facts'][0]
        f['statement'] += ' Batterikapaciteten uppges vara 90 kWh.'
        for i, ref in enumerate(f['support']):
            old_quote = ref['quote']
            ref['quote'] = ref['quote'].rstrip('.') + ' with a 90 kWh battery.'
            b['items'][i]['payload']['content'] = b['items'][i]['payload']['content'].replace(old_quote, ref['quote'])
        rehash(b)
        self.assertTrue(precheck(b, p, fixtures.NOW)['passed'], precheck(b, p, fixtures.NOW))
        old_quote = f['support'][1]['quote']
        f['support'][1]['quote'] = old_quote.replace('90', '80')
        b['items'][1]['payload']['content'] = b['items'][1]['payload']['content'].replace(old_quote, f['support'][1]['quote'])
        rehash(b)
        self.assertIn('publisher_reported_fact_conflicting_numbers_or_units:f1', precheck(b, p, fixtures.NOW)['errors'])

    def test_single_source_requires_attribution_registered_identity_and_exact_review(self):
        for kind in ('attribution', 'owner', 'review', 'hash', 'availability'):
            b, p, review = single_fixture()
            if kind == 'attribution': p['article']['intro'] = p['article']['intro'].replace('CarNewsChina', '')
            if kind == 'owner': b['items'][0]['payload']['publisher_group'] = 'invented'; rehash(b)
            if kind == 'availability': p['extraction']['facts'][0].update(market='SE')
            if kind == 'review': review['reported_not_verified'] = False
            if kind == 'hash': review['article_hash'] = 'changed'
            self.assertTrue(precheck(b, p, fixtures.NOW)['errors'] or check_review(b, p, review), kind)

    def test_single_source_local_stage_still_needs_both_receipts_and_clear_method(self):
        b, p, review = single_fixture()
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'test.sqlite')) as store:
            row = stage(store, b, p, review, [], now=fixtures.NOW)
            self.assertEqual(row['status'], 'quarantined')
            self.assertIn('en redaktion', row['payload']['editorial_method'])
            self.assertNotIn('två oberoende', row['payload']['editorial_method'])
            with self.assertRaises(ValueError): store.publish(row['id'], daily_limit=1)

    def test_same_budget_and_output_limits_cover_both_source_formats(self):
        ai = NewsAi.__new__(NewsAi)
        ai.model, ai.output_limits = 'gpt-6-sol', LIMITS
        for b in (fixtures.fixture()[0], single_fixture()[0]):
            self.assertLess(pair_bound(ai, b), 250000)
            prompt = writer_call(b)[2]
            self.assertIn('80-149', prompt)
            self.assertIn('150-250', prompt)
            self.assertIn('ONE complete', prompt)
        self.assertEqual(LIMITS, {'swedish_ev_article': 2000, 'ev_news_independent_audit': 1300})
        self.assertEqual(worker.DAILY_CANDIDATE_LIMIT, 2)

    def test_single_source_refresh_detects_changes_without_rediscovering_or_paying(self):
        b, _, _ = single_fixture()
        item = copy.deepcopy(b['items'][0])
        with patch('news_publisher_sources.fetch_publisher', return_value=(item, [])) as fetch:
            fresh = refresh_bundle(b, None, fixtures.NOW)
            self.assertTrue(same_sources(b, fresh))
            self.assertEqual(fetch.call_count, 1)
            item['payload']['content'] += ' An additional synthetic source sentence.'
            import hashlib
            item['payload']['content_hash'] = hashlib.sha256(item['payload']['content'].encode()).hexdigest()
            self.assertFalse(same_sources(b, refresh_bundle(b, None, fixtures.NOW)))

    def test_scheduler_prefers_new_policy_without_mutating_legacy_proofs(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/news.yml').read_text()
        self.assertIn("vars.NEWS_SHORT_ARTICLES_ENABLED == 'true' && vars.NEWS_PUBLISHER_ARTICLES_ENABLED != 'true'", workflow)
        self.assertIn("vars.NEWS_PUBLISHER_ARTICLES_ENABLED == 'true'", workflow)

    def test_length_boundaries_are_shared_by_precheck_and_wording(self):
        from news_publisher_articles import wording_errors
        for size in (79, 80, 149, 150, 250, 251):
            b, p = fixtures.fixture()
            p['article']['intro'] = ' '.join(['syntetiskt'] * (size - 2))
            p['article']['paragraphs'] = [{'text': 'ytterligare ord', 'fact_ids': ['f1'], 'kind': 'reporting'}]
            checked = precheck(b, p, fixtures.NOW)
            self.assertEqual(checked['word_count'], size)
            expected = size in (79, 251)
            self.assertEqual('publisher_word_count_outside_80_250' in checked['errors'], expected)
            self.assertEqual('publisher_word_count_outside_80_250' in wording_errors(b, p['article']), expected)

    def test_single_source_full_synthetic_worker_uses_separate_review(self):
        b, p, review = single_fixture()
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(fixtures, 'fixture', return_value=(b, p)))
            stack.enter_context(patch.object(fixtures, 'accepted_review', return_value=review))
            remote, bundle, _, ai = fixtures.PublisherLifecycleTests().setup_environment(stack, folder)
            result = worker.perform(remote, bundle, private=True, ai=ai)
            self.assertEqual(result['state'], 'passed', result)
            self.assertEqual(ai.calls, ['swedish_ev_article', 'ev_news_independent_audit'])
            self.assertEqual(remote.public_articles(), [])


if __name__ == '__main__':
    unittest.main()
