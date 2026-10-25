import json
import ssl
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_engine import collect, hydrate_item, classify_metadata
from news_http import Collector, require_recent_publication
from news_pressrooms import document, discover
from news_store import NewsStore
from news_editorial import generate_article, audit_article, market_qualified_facts, repair_article

SOURCE = {'id': 'official', 'name': 'Official Pressroom', 'website': 'https://press.example.com',
          'kind': 'primary', 'reliability': 0.98, 'enabled': True, 'collection_method': 'pressroom_index',
          'indexes': ['https://press.example.com/global/'], 'article_path_pattern': r'/global/article/detail/T[0-9]+EN/[^/]+',
          'topic_pattern': 'electric|batter'}
URL = 'https://press.example.com/global/article/detail/T123EN/electric-battery'
ARTICLE = ('<meta property="og:title" content="Electric battery news">'
           '<span class="date">Tue Oct 20 17:15:00 CEST 2026</span>'
           '<div id="article-text"><p>Battery cells improve efficiency.</p><script>ignore()</script></div>')


class PressroomTests(unittest.TestCase):
    def test_acea_content_container_uses_real_publication_date_and_excludes_navigation(self):
        html = ('<meta property="og:title" content="EU registrations">'
                '<meta property="article:published_time" content="2026-10-22T05:50:00Z">'
                '<nav>Subscribe and unrelated numbers</nav>'
                '<div class="cntnt block-container"><p>EU battery-electric registrations in January-September.</p>'
                '<script>ignored()</script><footer>Not article evidence</footer></div>')
        parsed = document(html)
        self.assertEqual(parsed['published_at'], '2026-10-22T05:50:00+00:00')
        self.assertEqual(parsed['body'], 'EU battery-electric registrations in January-September.')
        self.assertEqual(document('<div class="cntnt">Not a recognized article</div>')['body'], '')

    def setUp(self):
        self.now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        for module in ('news_engine', 'news_pressrooms'):
            clock = patch(module + '.require_recent_publication',
                          side_effect=lambda value, now=None: require_recent_publication(value, now or self.now))
            clock.start()
            self.addCleanup(clock.stop)

    def test_freshness_boundaries_use_publication_not_collection_time(self):
        now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        for delta in [timedelta(days=-7), timedelta(hours=1)]:
            value = (now + delta).isoformat()
            self.assertEqual(require_recent_publication(value, now), value)
        for value, reason in [((now - timedelta(days=7, seconds=1)).isoformat(), 'stale_report'),
                              ((now + timedelta(hours=1, seconds=1)).isoformat(), 'future_report'),
                              (None, 'missing_publication_date'), ('invalid', 'missing_publication_date')]:
            with self.assertRaisesRegex(ValueError, reason): require_recent_publication(value, now)

    def test_discovery_replaces_stale_or_invalid_candidates_with_fresh_results(self):
        now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        urls = [URL.replace('T123', 'T' + str(i)) for i in (123, 124, 125)]
        old = ARTICLE.replace('Tue Oct 20', 'Tue Oct 06')
        collector = Mock()
        collector.fetch.side_effect = [(200, {}, old, urls[0]), (200, {}, '<p>No metadata</p>', urls[1]),
                                       (200, {}, ARTICLE, urls[2])]
        index = ''.join('<a href="' + url + '">Link</a>' for url in urls)
        rows, errors = discover(index, SOURCE['indexes'][0], SOURCE, collector, 1, now)
        self.assertEqual([row['url'] for row in rows], [urls[2]])
        self.assertEqual([row['reason'] for row in errors], ['ValueError:stale_report', 'ValueError:missing_release_title_or_date'])
        self.assertEqual(collector.fetch.call_count, 3)

    def test_discovery_rejects_future_dates_and_bounds_bad_candidate_fetches(self):
        now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        index = ''.join('<a href="' + URL.replace('T123', 'T' + str(i)) + '">Link</a>' for i in range(30))
        collector = Mock()
        collector.fetch.return_value = (200, {}, ARTICLE.replace('Tue Oct 20', 'Thu Oct 29'), URL)
        rows, errors = discover(index, SOURCE['indexes'][0], SOURCE, collector, 1, now)
        self.assertEqual(rows, [])
        self.assertEqual(collector.fetch.call_count, 3)
        self.assertTrue(all(error['reason'] == 'ValueError:future_report' for error in errors))
        collector.reset_mock()
        discover(index, SOURCE['indexes'][0], SOURCE, collector, 100, now)
        self.assertEqual(collector.fetch.call_count, 20)

    def test_zero_limit_never_fetches_and_invalid_limits_are_rejected(self):
        collector = Mock()
        self.assertEqual(discover('<a href="' + URL + '">Link</a>', SOURCE['indexes'][0], SOURCE, collector, 0), ([], []))
        for value in [-1, True, 1.5]:
            with self.assertRaisesRegex(ValueError, 'invalid_pressroom_limit'):
                discover('', SOURCE['indexes'][0], SOURCE, collector, value)
        collector.fetch.assert_not_called()

    def test_redirected_duplicates_do_not_fill_the_result_quota(self):
        now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        urls = [URL.replace('T123', 'T' + str(i)) for i in (123, 124, 125)]
        collector = Mock()
        collector.fetch.side_effect = [(200, {}, ARTICLE, urls[0]), (200, {}, ARTICLE, urls[0]),
                                       (200, {}, ARTICLE, urls[2])]
        index = ''.join('<a href="' + url + '">Link</a>' for url in urls)
        rows, errors = discover(index, SOURCE['indexes'][0], SOURCE, collector, 2, now)
        self.assertEqual([row['url'] for row in rows], [urls[0], urls[2]])
        self.assertEqual(errors, [])

    def test_stale_only_pressroom_is_quiet_not_a_broken_feed(self):
        old = ARTICLE.replace('Tue Oct 20 17:15:00 CEST 2026', 'Tue Jan 20 17:15:00 CET 2026')
        collector = Mock()
        index = '<a href="' + URL + '">Electric news</a>'
        collector.fetch.side_effect = lambda url, *args, **kwargs: (200, {}, index if url.endswith('/global/') else old, url)
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            result = collect(store, [SOURCE], collector, max_items=1, force=True)
            self.assertEqual(result['sources'][0]['status'], 'verified_no_recent_items')
            self.assertEqual(result['sources'][0]['entries'], 0)
            self.assertEqual(store.rows('news_items'), [])

    def test_stale_or_future_hydration_does_not_fetch_or_mutate_items(self):
        for date in ['2020-01-01', '2090-01-01', None]:
            store, collector = Mock(), Mock()
            with self.assertRaises(ValueError):
                hydrate_item(store, {'source_id': SOURCE['id'], 'url': URL, 'payload': {'published_at': date}},
                             {SOURCE['id']: SOURCE}, collector)
            collector.fetch.assert_not_called()
            store.put.assert_not_called()

    def test_private_preview_cannot_label_quarantine_as_approved_or_render_markup(self):
        from render_news_smoke_preview import render
        article = {'status': 'quarantined', 'payload': {'title': '<script>unsafe</script>', 'intro': 'Test',
                   'paragraphs': [{'text': '<img src=x>'}], 'sources': [{'url': 'https://press.example.com/release', 'publisher': 'Official'}]}}
        html = render(article, approved=True)
        self.assertIn('Utkast i karant', html)
        self.assertNotIn('<script>unsafe', html)
        self.assertIn('&lt;img src=x&gt;', html)
        self.assertIn('noindex,nofollow', html)
        article['payload']['sources'][0]['url'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError): render(article)

    def test_targeted_repair_preserves_supported_blocks_and_requires_reaudit(self):
        previous = {'title': 'Supported headline', 'title_fact_ids': ['f0'], 'intro': 'Supported intro',
                    'intro_fact_ids': ['f0'], 'paragraphs': [{'text': 'Unsupported filler.', 'fact_ids': ['f0'], 'kind': 'reporting'},
                                                         {'text': 'Supported passage.', 'fact_ids': ['f1'], 'kind': 'analysis'}]}
        ai = Mock(return_value={'text': 'Supported replacement.', 'fact_ids': ['f0'], 'kind': 'reporting'})
        revised = repair_article(previous, [], {'unsupported_blocks': [{'id': 'p0', 'reason': 'unsupported'}]}, ai)
        self.assertEqual(revised['title'], previous['title'])
        self.assertEqual(revised['paragraphs'][1], previous['paragraphs'][1])
        self.assertEqual(previous['paragraphs'][0]['text'], 'Unsupported filler.')
        self.assertEqual(ai.call_args.args[0], 'ev_news_block_repair')
        ai.return_value['kind'] = 'analysis'
        with self.assertRaisesRegex(ValueError, 'repair_changed_editorial_kind'):
            repair_article(previous, [], {'unsupported_blocks': [{'id': 'p0', 'reason': 'unsupported'}]}, ai)

    def test_unqualified_foreign_price_is_not_passed_to_writer(self):
        unqualified = {'statement': 'The car costs 27,995 euros.', 'evidence': 'The new car is available from 27,995 euros.'}
        qualified = {**unqualified, 'evidence': 'The car starts at 27,995 euros in Germany.'}
        range_fact = {'statement': 'Range up to 324 km.', 'evidence': 'The battery offers a range of up to 324 km.'}
        self.assertEqual(market_qualified_facts([unqualified, qualified, range_fact]), [qualified, range_fact])

    def test_editorial_prompt_separates_citations_from_prose_and_keeps_evidence_gates(self):
        ai = Mock(return_value={'title': 'Test title', 'intro': 'Test intro',
                                'paragraphs': ['A supported test paragraph.'], 'source_context': {}, 'buyer_question': 'Test question?'})
        generate_article([{'id': 'f0', 'statement': 'A test fact.'}], ai)
        self.assertIn('Source IDs are immutable and attached by the backend', ai.call_args.args[2])
        self.assertIn('160-210 visible words', ai.call_args.args[2])
        self.assertIn('publication limit remains 150-400', ai.call_args.args[2])
        self.assertIn('without explicit evidence', ai.call_args.args[2])
        audit_article({}, [], ai)
        self.assertIn('reject implied local availability', ai.call_args.args[2])
        self.assertIn('Verify EVERY atomic fact', ai.call_args.args[2])
    def test_bmw_release_date_body_and_navigation_separation(self):
        result = document('<nav>Login</nav>' + ARTICLE + '<footer>Other announcements</footer>')
        self.assertEqual(result['published_at'], '2026-10-20T15:15:00+00:00')
        self.assertEqual(result['body'], 'Battery cells improve efficiency.')
        self.assertEqual(result['title'], 'Electric battery news')

    def test_jsonld_publication_not_modification_or_fetch_date(self):
        data = {'@graph': [{'@type': 'NewsArticle', 'datePublished': '2026-10-19T09:30:00+02:00',
                            'dateModified': '2026-10-21T10:00:00Z'}]}
        html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
        self.assertEqual(document(html)['published_at'], '2026-10-19T07:30:00+00:00')
        self.assertIsNone(document('<meta property="article:modified_time" content="2026-10-21">')['published_at'])

    def test_swedish_pressrelease_date_and_article_container(self):
        html = ('<nav>Other news</nav><meta property="og:title" content="Swedish release">'
                '<div class="page article-page pressrelease"><div class="pressrelease-date">'
                '19 okt 2026 | Pressmeddelande</div><h1>Swedish release</h1><p>Supported battery news.</p></div>'
                '<footer>Other announcements</footer>')
        result = document(html)
        self.assertEqual(result['published_at'], '2026-10-19T00:00:00+00:00')
        self.assertIn('Supported battery news.', result['body'])
        self.assertNotIn('Other announcements', result['body'])

    def test_unlabelled_swedish_date_or_modification_cannot_be_publication_date(self):
        for markup in ['<div>19 okt 2026 | Pressmeddelande</div>',
                       '<div class="pressrelease-date">19 okt 2026 | Uppdaterad</div>',
                       '<div class="pressrelease-date">31 feb 2026 | Pressmeddelande</div>']:
            self.assertIsNone(document(markup)['published_at'])

    def test_discovery_stays_same_host_exact_paths_no_media_duplicate(self):
        links = [URL, URL, URL + '?showMedia=photo', URL.replace('press.example.com', 'other.example'),
                 'https://press.example.com/global/article/detail/T124EN/sports', 'https://press.example.com/account']
        index = ''.join('<a href="' + url + '">Link</a>' for url in links)
        collector = Mock()
        collector.fetch.return_value = (200, {}, ARTICLE, URL)
        rows, errors = discover(index, SOURCE['indexes'][0], SOURCE, collector, 4)
        self.assertEqual(len(rows), 1)
        self.assertEqual(errors, [])
        collector.fetch.assert_called_once_with(URL, SOURCE, editorial=True)

    def test_missing_date_and_access_denial_are_not_bypassed(self):
        collector = Mock()
        collector.fetch.side_effect = [(200, {}, '<meta property="og:title" content="No date">', URL),
                                      ValueError('ai_mining_robots_reserved')]
        index = '<a href="' + URL + '">One</a><a href="' + URL.replace('T123', 'T125') + '">Two</a>'
        rows, errors = discover(index, SOURCE['indexes'][0], SOURCE, collector, 4)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 2)
        with self.assertRaisesRegex(ValueError, 'official_pressroom_required'):
            discover(index, SOURCE['indexes'][0], {**SOURCE, 'kind': 'publisher'}, collector, 4)

    def test_index_collection_is_idempotent_and_never_uses_ai(self):
        collector = Mock()
        index = '<a href="' + URL + '">Electric battery</a>'
        collector.fetch.side_effect = lambda url, *args, **kwargs: (200, {}, index if url.endswith('/global/') else ARTICLE, url)
        with tempfile.TemporaryDirectory() as directory:
            store = NewsStore(Path(directory) / 'news.sqlite')
            self.assertEqual(collect(store, [SOURCE], collector, force=True)['new_items'], 1)
            self.assertEqual(collect(store, [SOURCE], collector, force=True)['new_items'], 0)
            self.assertEqual(store.rows('news_articles'), [])
            self.assertEqual(store.rows('news_items')[0]['payload']['source_kind'], 'primary')
            store.close()

    def test_hydration_rejects_changed_pressroom_date(self):
        collector = Mock()
        collector.fetch.return_value = (200, {}, ARTICLE, URL)
        item = {'id': 'test', 'source_id': SOURCE['id'], 'url': URL,
                'payload': {'published_at': '2026-10-19T15:15:00+00:00'}}
        with self.assertRaisesRegex(ValueError, 'publication_date_changed'):
            hydrate_item(Mock(), item, {SOURCE['id']: SOURCE}, collector)

    def test_tls_cannot_disable_certificate_or_hostname_checks(self):
        with self.assertRaisesRegex(ValueError, 'verified_tls_required'):
            Collector(ssl._create_unverified_context())

    def test_german_market_hint_does_not_create_swedish_availability(self):
        result = classify_metadata('Electric car now on sale in Germany', '')
        self.assertIn('Europe', result['markets'])
        self.assertNotIn('Sweden', result['markets'])
        self.assertNotIn('available_confirmed', result)


if __name__ == '__main__':
    unittest.main()
