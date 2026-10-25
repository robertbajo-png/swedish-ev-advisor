"""Offline collection, resumability and public projection regressions."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.request import Request
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from news_ai import NewsBudgetBlocked
from news_engine import attach_cluster, export_public, process_items
from news_http import Collector, SafeRedirect
from news_store import NewsStore
from test_news import CONTENT, DATE, SOURCE, extraction, item


def robots(lines):
    policy = RobotFileParser()
    policy.parse(lines)
    return policy


class RedirectPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = robots(['User-agent: GPTBot', 'Disallow: /reserved',
                              'User-agent: CCBot', 'Disallow: /cc-reserved',
                              'User-agent: *', 'Allow: /'])

    def test_editorial_final_url_cannot_bypass_mining_reservation(self):
        collector = Collector()
        with patch.object(collector, 'policy', return_value=self.policy), \
                patch.object(collector, 'request', return_value=(200, {}, '<article>text</article>', 'https://press.example.com/reserved')), \
                patch('news_http.time.sleep'):
            with self.assertRaisesRegex(ValueError, 'ai_mining_robots_reserved'):
                collector.fetch('https://press.example.com/open', SOURCE, editorial=True)

    def test_reserved_intermediate_redirect_is_blocked_before_following(self):
        collector = Collector()
        def redirecting_request(url, host, headers=None, policy=None):
            redirect = SafeRedirect(host, policy)
            with patch('news_http.safe_host', side_effect=lambda url, host: url):
                redirect.redirect_request(Request(url), None, 302, 'Found', {}, 'https://press.example.com/reserved')
            return 200, {}, '', 'https://press.example.com/open-again'
        with patch.object(collector, 'policy', return_value=self.policy), \
                patch.object(collector, 'request', side_effect=redirecting_request), patch('news_http.time.sleep'):
            with self.assertRaisesRegex(ValueError, 'ai_mining_robots_reserved'):
                collector.fetch('https://press.example.com/open', SOURCE, editorial=True)

    def test_ccbot_reservation_is_also_checked_at_final_url(self):
        collector = Collector()
        with patch.object(collector, 'policy', return_value=self.policy), \
                patch.object(collector, 'request', return_value=(200, {}, '', 'https://press.example.com/cc-reserved')), \
                patch('news_http.time.sleep'):
            with self.assertRaisesRegex(ValueError, 'ai_mining_robots_reserved'):
                collector.fetch('https://press.example.com/open', SOURCE, editorial=True)

    def test_metadata_collection_keeps_its_own_agent_policy(self):
        collector = Collector()
        with patch.object(collector, 'policy', return_value=self.policy), \
                patch.object(collector, 'request', return_value=(200, {}, '', 'https://press.example.com/reserved')), \
                patch('news_http.time.sleep'):
            self.assertEqual(collector.fetch('https://press.example.com/open', SOURCE)[0], 200)

    def test_allowed_editorial_redirect_still_works(self):
        collector = Collector()
        with patch.object(collector, 'policy', return_value=self.policy), \
                patch.object(collector, 'request', return_value=(200, {}, '', 'https://press.example.com/allowed')), \
                patch('news_http.time.sleep'):
            self.assertEqual(collector.fetch('https://press.example.com/open', SOURCE, editorial=True)[0], 200)

    def test_tdm_reservation_on_redirect_response_is_not_discarded(self):
        redirect = SafeRedirect('press.example.com')
        with patch('news_http.safe_host', side_effect=lambda url, host: url):
            with self.assertRaisesRegex(ValueError, 'tdm_reserved'):
                redirect.redirect_request(Request('https://press.example.com/open'), None, 302, 'Found',
                                          {'TDM-Reservation': '1'}, 'https://press.example.com/allowed')


class CollectionCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = NewsStore(Path(self.directory.name) / 'private.sqlite')
        self.html = '<article>' + CONTENT * 5 + '</article>'
        self.collector = Mock()
        self.collector.fetch.side_effect = lambda url, *args, **kwargs: (200, {}, self.html, url)
        seed = extraction()
        seed['event']['subject'] = 'updated model'
        self.existing = attach_cluster(self.store, {**item('seed'), 'url': SOURCE['website'] + '/seed'}, seed)
        self.store.put('news_items', {**item(), 'status': 'collected'})
        self.calls = []
        self.block_identity = True

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def ai(self, name, schema, prompt):
        self.calls.append(name)
        if name == 'ev_news_facts':
            return extraction()
        if name == 'news_event_identity':
            if self.block_identity:
                raise NewsBudgetBlocked('test_budget_limit')
            return {'certain': True, 'existing_cluster_id': self.existing['cluster_id'], 'reason': 'Same announcement'}
        raise AssertionError('Unexpected AI stage: ' + name)

    def run_items(self):
        with patch('news_engine.models_for_news', return_value={}):
            return process_items(self.store, [SOURCE], ai=self.ai, collector=self.collector)

    def defer_then_allow(self):
        self.assertEqual(self.run_items()[0]['status'], 'deferred_budget')
        row = self.store.get('news_items', 'item')
        self.store.put('news_items', {**row, 'payload': {**row['payload'], 'budget_retry_after': None}})
        self.block_identity = False

    def test_budget_retry_reuses_facts_only_after_refetch_and_revalidation(self):
        self.defer_then_allow()
        self.assertEqual(self.run_items()[0]['status'], 'processed')
        self.assertEqual(self.calls.count('ev_news_facts'), 1)
        self.assertEqual(self.calls.count('news_event_identity'), 2)
        self.assertEqual(self.collector.fetch.call_count, 2)
        self.assertEqual(self.store.get('news_items', 'item')['cluster_id'], self.existing['cluster_id'])
        self.assertEqual(self.store.rows('news_articles'), [])

    def test_changed_content_invalidates_checkpoint(self):
        self.defer_then_allow()
        self.html = self.html.replace('</article>', '<p>A new manufacturer clarification changes the source.</p></article>')
        self.assertEqual(self.run_items()[0]['status'], 'processed')
        self.assertEqual(self.calls.count('ev_news_facts'), 2)

    def test_source_reservation_on_retry_blocks_checkpoint_use(self):
        self.defer_then_allow()
        self.collector.fetch.side_effect = ValueError('tdm_reserved')
        self.assertEqual(self.run_items()[0]['status'], 'quarantined')
        self.assertEqual(self.calls, ['ev_news_facts', 'news_event_identity'])
        self.assertEqual(self.store.rows('news_articles'), [])

    def test_changed_model_scope_invalidates_checkpoint(self):
        self.defer_then_allow()
        with patch('news_engine.models_for_news', return_value={'New|EV': {}}):
            report = process_items(self.store, [SOURCE], ai=self.ai, collector=self.collector)
        self.assertEqual(report[0]['status'], 'processed')
        self.assertEqual(self.calls.count('ev_news_facts'), 2)

    def test_changed_recipe_invalidates_checkpoint(self):
        self.defer_then_allow()
        with patch('news_engine.EDITORIAL_RECIPE', 'a-new-private-recipe'):
            self.assertEqual(self.run_items()[0]['status'], 'processed')
        self.assertEqual(self.calls.count('ev_news_facts'), 2)

    def test_corrupt_checkpoint_cannot_skip_fact_validation(self):
        self.defer_then_allow()
        row = self.store.get('news_items', 'item')
        row['payload']['fact_checkpoint']['extraction']['facts'][0]['evidence'] = 'invented source span with enough words to look like evidence'
        self.store.put('news_items', row)
        report = self.run_items()
        self.assertEqual(report[0]['status'], 'quarantined')
        self.assertEqual(self.calls.count('news_event_identity'), 1)
        self.assertEqual(self.store.rows('news_articles'), [])

    def test_malformed_identity_response_cannot_merge_reports(self):
        extraction_value = extraction()
        valid = {'certain': True, 'existing_cluster_id': self.existing['cluster_id'], 'reason': 'Same event'}
        invalid = [{**valid, 'certain': 'false'}, {**valid, 'certain': 1},
                   {**valid, 'existing_cluster_id': None}, {**valid, 'reason': []}, None]
        for index, response in enumerate(invalid):
            with self.subTest(response=response):
                candidate = {**item('candidate-' + str(index)), 'url': SOURCE['website'] + '/candidate-' + str(index)}
                with self.assertRaisesRegex(ValueError, 'invalid_event_identity_response'):
                    attach_cluster(self.store, candidate, extraction_value, lambda *args: response)
                self.assertIsNone(self.store.get('news_items', candidate['id']))
        self.assertEqual(len(self.store.rows('news_story_clusters')), 1)

    def test_certain_separate_event_is_not_merged_by_model_alone(self):
        candidate = {**item('distinct-event'), 'url': SOURCE['website'] + '/distinct-event'}
        match = lambda *args: {'certain': True, 'existing_cluster_id': '', 'reason': 'Separate announcement'}
        attached = attach_cluster(self.store, candidate, extraction(), match)
        self.assertNotEqual(attached['cluster_id'], self.existing['cluster_id'])
        self.assertEqual(len(self.store.rows('news_story_clusters')), 2)

    def test_followup_failure_does_not_misreport_processed_item_or_skip_next_link(self):
        self.block_identity = False
        self.html += '<a href="https://press.example.com/broken">First</a><a href="https://press.example.com/second">Second</a>'
        def fetch(url, *args, **kwargs):
            if url.endswith('/broken'):
                raise ValueError('tdm_reserved')
            if url.endswith('/second'):
                return 200, {}, '<script type="application/ld+json">' + json.dumps({'datePublished': DATE}) + '</script>', url
            return 200, {}, self.html, url
        self.collector.fetch.side_effect = fetch
        report = self.run_items()
        self.assertEqual([r['status'] for r in report], ['processed'])
        self.assertEqual(self.store.get('news_items', 'item')['status'], 'processed')
        self.assertIn('tdm_reserved', report[0]['primary_source_errors'][0]['reason'])
        self.assertTrue(any(r['url'].endswith('/second') for r in self.store.rows('news_items')))


class PublicSourceProjectionTests(unittest.TestCase):
    def test_export_removes_nested_private_source_fields(self):
        store = Mock()
        source = {'url': SOURCE['website'] + '/release', 'publisher': SOURCE['name'], 'title': 'Release',
                  'published_at': DATE, 'kind': 'primary', 'item_id': 'private-item', 'content_hash': 'private-hash',
                  'extraction': {'facts': ['private']}}
        record = {'id': 'article', 'slug': 'article', 'published_at': DATE, 'title': 'Rubrik',
                  'intro': 'Ingress', 'paragraphs': [{'text': 'Text', 'kind': 'reporting', 'fact_ids': ['private-fact']}],
                  'sources': [source], 'input_fingerprint': 'private'}
        store.public_articles.return_value = [copy.deepcopy(record)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'isolated-export.json'
            export_public(store, path)
            exported = json.loads(path.read_text(encoding='utf-8'))['records'][0]
        self.assertEqual(set(exported['sources'][0]), {'url', 'publisher', 'title', 'published_at', 'kind'})
        self.assertNotIn('fact_ids', exported['paragraphs'][0])
        self.assertNotIn('input_fingerprint', exported)
        self.assertEqual(store.public_articles.return_value[0], record)


if __name__ == '__main__':
    unittest.main()
