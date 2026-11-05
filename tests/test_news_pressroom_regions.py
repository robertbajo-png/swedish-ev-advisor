"""Synthetic source layouts; no provider requests or live editorial approvals."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_pressrooms import document, discover
from news_publisher_sources import primary_source, collect_bundle, bundle_errors

URL = 'https://www.polestar.com/global/news/synthetic-electric-model/'
NOW = datetime(2026, 11, 5, 6, tzinfo=timezone.utc)
BODY = 'Polestar presents a synthetic electric passenger car for an isolated regression test. ' * 16


def page(url=URL, date=NOW.isoformat(), *, identity=None, extra=(), region='main'):
    data = {'@type': 'NewsArticle', 'mainEntityOfPage': {'@type': 'Article', '@id': identity or url},
            'headline': 'Synthetic Polestar electric model', 'datePublished': date,
            'dateModified': '2099-01-01T00:00:00Z'}
    return (f'<link rel="canonical" href="{url}"><meta property="og:title" content="Synthetic Polestar electric model">'
            '<script type="application/ld+json">' + json.dumps([data, *extra]) + '</script>'
            '<nav>Excluded navigation</nav>' + f'<{region}><h1>Synthetic Polestar electric model</h1><p>{BODY}</p>'
            f'<aside>Excluded related stories</aside><table><tr><td>Held table value</td></tr></table></{region}>')


class PressroomRegionTests(unittest.TestCase):
    def test_one_explicit_region_uses_exact_article_identity_and_publication_not_modified(self):
        other = {'@type': 'NewsArticle', 'url': URL + '-unrelated', 'datePublished': '2024-01-01'}
        d = document(page(extra=[other]), url=URL, body_region='main', exclude_tables=True)
        self.assertEqual(d['published_at'], NOW.isoformat())
        self.assertIn('synthetic electric passenger car', d['body'])
        self.assertNotIn('Excluded', d['body'])
        self.assertNotIn('Held table', d['body'])

    def test_unknown_identity_canonical_dates_and_regions_fail_closed(self):
        cases = [page(identity=URL + '-other'), page(url=URL + '-other'), page(date='invalid'),
                 page(region='article'), page() + '<main>Ambiguous second body</main>',
                 page(extra=[{'@type': 'NewsArticle', 'url': URL, 'datePublished': '2026-11-04T00:00:00Z'}])]
        for html in cases:
            with self.subTest(html=hashlib.sha256(html.encode()).hexdigest()), self.assertRaises(ValueError):
                document(html, url=URL, body_region='main')

    def test_registered_exact_host_path_only_not_similar_models_or_arbitrary_urls(self):
        self.assertEqual(primary_source(URL)['id'], 'polestar-news')
        for url in [URL + '?redirect=private', URL.replace('polestar.com', 'polestar.com.evil.example'),
                    URL.replace('/global/news/', '/shop/'), URL.replace('https:', 'http:')]:
            self.assertIsNone(primary_source(url))

    def test_publisher_collection_ignores_unidentified_or_other_article_dates_too(self):
        extra = [{'@type': 'NewsArticle', '@id': URL + 'other/', 'datePublished': '2024-01-01'},
                 {'@type': 'NewsArticle', 'datePublished': '2025-01-01'}]
        class Collector:
            def fetch(self, url, source, **kwargs):
                return 200, {}, page(extra=extra), url
        bundle = collect_bundle('polestar-news', URL, Collector(), now=NOW)
        self.assertEqual(bundle_errors(bundle, NOW), [])
        self.assertEqual(bundle['items'][0]['payload']['published_at'], NOW.isoformat())

    def test_discovery_uses_typed_body_date_and_never_makes_old_articles_new(self):
        source = primary_source(URL)
        class Collector:
            def fetch(self, url, source, **kwargs):
                return 200, {}, page(date='2025-01-01T00:00:00Z'), url
        rows, errors = discover(f'<a href="{URL}">New car</a>', source['indexes'][0], source, Collector(), 1, NOW)
        self.assertEqual(rows, [])
        self.assertEqual(errors[0]['reason'], 'ValueError:stale_report')

    def test_tables_are_still_held_before_writing_despite_correct_source_layout(self):
        from news_publisher_articles import evidence_readiness
        class Collector:
            def fetch(self, url, source, **kwargs):
                return 200, {}, page(), url
        bundle = collect_bundle('polestar-news', URL, Collector(), now=NOW)
        self.assertEqual(bundle_errors(bundle, NOW), [])
        self.assertIn('publisher_table_context_requires_validation', evidence_readiness(bundle, NOW)['errors'])

    def test_declared_trailing_slash_alias_deduplicates_without_relaxing_the_authority(self):
        source = primary_source(URL)
        calls = []
        class Collector:
            def fetch(self, url, source, **kwargs):
                calls.append(url)
                return 200, {}, page(), url
        index = ''.join(f'<a href="{u}">Electric model</a>' for u in [URL.rstrip('/'), URL, URL + '?other=1',
                      URL.replace('polestar.com', 'polestar.com.evil.example')])
        rows, errors = discover(index, source['indexes'][0], source, Collector(), 3, NOW)
        self.assertEqual([r['url'] for r in rows], [URL])
        self.assertEqual(calls, [URL])
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
