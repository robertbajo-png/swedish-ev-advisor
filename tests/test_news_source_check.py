import copy
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_news_sources import check_sources
from news_store import NewsStore
from test_news_pressrooms import SOURCE, URL


def collector_for(source, blocked=False, date=None):
    collector = Mock()
    date = date or datetime.now(timezone.utc).isoformat()
    body = '<meta property="og:title" content="Electric battery for Europe"><meta property="article:published_time" content="' + date + '">'
    body += '<div id="article-text">' + 'Source-supported article text. ' * 60 + '</div>'
    index = '<a href="' + URL + '">Electric battery</a>'
    def fetch(url, config, *args, **kwargs):
        if blocked and not url.endswith('/global/'):
            raise ValueError('ai_mining_robots_reserved')
        return 200, {}, index if url.endswith('/global/') else body, url
    collector.fetch.side_effect = fetch
    return collector


class SourceCheckTests(unittest.TestCase):
    def test_private_check_is_idempotent_and_never_runs_ai_or_writes_supabase(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store, \
             patch('news_engine.editorial') as editorial, patch('news_engine.process_items') as extract, \
             patch('news_ai.NewsAi.request') as provider, patch('news_store.SupabaseRestClient') as remote, \
             patch('news_ai.SupabaseRestClient') as allowance_client, \
             patch.dict('os.environ', {'NEWS_BACKEND': 'supabase', 'OPENAI_API_KEY': 'not-a-real-key'}):
            source = copy.deepcopy(SOURCE)
            collector = collector_for(source)
            first = check_sources(store, [source], collector, 1)
            second = check_sources(store, [source], collector, 1)
            self.assertEqual(first['collection']['new_items'], 1)
            self.assertEqual(second['collection']['new_items'], 0)
            self.assertTrue(first['collection_ok'])
            self.assertEqual(first['accessible_sources'], 1)
            self.assertFalse(first['public_writes'])
            self.assertFalse(first['publication_approved'])
            self.assertEqual(first['ai_calls'], 0)
            self.assertFalse(first['assessments'][0]['facts_verified'])
            self.assertNotIn('content', first['assessments'][0])
            self.assertTrue(first['assessments'][0]['content_hash'])
            self.assertEqual(store.rows('news_articles'), [])
            self.assertEqual(store.rows('news_story_clusters'), [])
            for stub in [provider, remote, allowance_client, editorial, extract]: stub.assert_not_called()
            self.assertEqual(source, SOURCE)

    def test_source_failure_does_not_stop_other_sources(self):
        other = {**SOURCE, 'id': 'blocked', 'website': 'https://blocked.example.com', 'indexes': ['https://blocked.example.com/global/']}
        normal = collector_for(SOURCE)
        collector = Mock()
        def fetch(url, source, *args, **kwargs):
            if source['id'] == 'blocked': raise ValueError('robots_disallowed')
            return normal.fetch(url, source, *args, **kwargs)
        collector.fetch.side_effect = fetch
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            result = check_sources(store, [other, SOURCE], collector, 1)
            self.assertEqual(result['accessible_sources'], 1)
            self.assertFalse(result['collection_ok'])
            self.assertEqual(result['assessments'][0]['status'], 'source_unavailable')
            self.assertEqual(result['assessments'][1]['status'], 'accessible')
            self.assertEqual(store.rows('news_articles'), [])

    def test_secondary_publishers_are_excluded_and_production_stores_rejected(self):
        store, collector = Mock(backend='supabase'), Mock()
        with self.assertRaisesRegex(ValueError, 'isolated_sqlite'): check_sources(store, [SOURCE], collector)
        store.put.assert_not_called()
        collector.fetch.assert_not_called()
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            result = check_sources(store, [{**SOURCE, 'kind': 'publisher'}], collector)
            self.assertEqual(result['assessments'], [])
            self.assertFalse(result['collection_ok'])
        collector.fetch.assert_not_called()

    def test_limits_cannot_create_an_unbounded_crawl(self):
        store, collector = Mock(backend='sqlite'), Mock()
        for value in [0, 6, True, -1]:
            with self.assertRaisesRegex(ValueError, '1_to_5'): check_sources(store, [SOURCE], collector, value)
        with self.assertRaisesRegex(ValueError, 'source_limit'):
            check_sources(store, [{**SOURCE, 'id': str(i)} for i in range(7)], collector)
        store.put.assert_not_called()
        collector.fetch.assert_not_called()

    def test_stale_cached_content_is_not_reported_as_ready(self):
        collector = collector_for(SOURCE)
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_items', {'id': 'old', 'source_id': SOURCE['id'], 'url': URL + '-old', 'cluster_id': None,
                      'status': 'ready', 'payload': {'published_at': '2020-01-01', 'content': 'old cached content'}})
            result = check_sources(store, [SOURCE], collector, 1)
            self.assertEqual(result['excluded_cached_items'], [{'item_id': 'old', 'reason': 'stale_report'}])
            self.assertEqual(result['accessible_sources'], 1)
            self.assertEqual(store.get('news_items', 'old')['status'], 'ready')

    def test_quiet_source_does_not_require_an_article_quota(self):
        collector = collector_for(SOURCE, date='2020-01-01T00:00:00Z')
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            result = check_sources(store, [SOURCE], collector, 1)
            self.assertTrue(result['collection_ok'])
            self.assertEqual(result['assessments'], [{'source_id': SOURCE['id'], 'status': 'no_recent_candidates'}])
            self.assertEqual(result['accessible_sources'], 0)
            self.assertEqual(result['ai_calls'], 0)


if __name__ == '__main__':
    unittest.main()
