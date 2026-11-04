"""Offline selection/evidence regressions. Synthetic data is not a live proof."""
import copy
from contextlib import closing, ExitStack
from datetime import timedelta
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_engine
import run_publisher_news as worker
from news_publisher_selection import (candidate_assessment, ranked_candidates,
    passage_selection, primary_identity_matches)
from news_publisher_articles import evidence_readiness, source_views, evidence_catalog, precheck
from news_publisher_sources import collect_bundle
from news_store import NewsStore, artifact_hash, stable_id
import test_news_publisher_articles as fixtures

NOW = fixtures.NOW


def report(title, *, source='carnewschina', summary='', days=0, slug='synthetic'):
    return {'id': stable_id(title), 'url': f'https://{source + ".com" if source == "carnewschina" else "thedriven.io"}/2026/11/01/{slug}/',
            'source_id': source, 'status': 'collected', 'cluster_id': None,
            'payload': {'title': title, 'summary': summary, 'published_at': (NOW - timedelta(days=days)).isoformat()}}


class PublisherSelectionTests(unittest.TestCase):
    def test_sweden_and_europe_rank_ahead_of_newer_regional_news(self):
        rows = [report('GAC battery plant opens in Thailand'),
                report('New BMW electric sedan launches in Europe', source='thedriven', days=2, slug='europe'),
                report('Volvo electric SUV launches in Sweden', days=3, slug='sweden')]
        selected, held = ranked_candidates(rows, {'carnewschina', 'thedriven'}, now=NOW)
        self.assertEqual([x['payload']['title'] for x, _ in selected], [rows[2]['payload']['title'], rows[1]['payload']['title']])
        self.assertEqual(held[0]['reason'], 'regional_business_or_policy')

    def test_a_good_older_report_is_not_hidden_behind_eight_new_local_reports(self):
        rows = [report(f'BYD factory opens in China {i}', slug=f'local-{i}') for i in range(12)]
        useful = report('BMW electric vehicle update for Sweden', days=4)
        selected, _ = ranked_candidates(rows + [useful], {'carnewschina'}, now=NOW)
        self.assertEqual(selected[0][0], useful)

    def test_global_vehicle_battery_innovation_is_not_rejected_for_its_origin(self):
        item = report('CATL unveils sodium-ion technology for electric passenger cars',
                      summary='New cell chemistry and energy density for EV batteries.')
        result = candidate_assessment(item, NOW)
        self.assertTrue(result['eligible'])
        self.assertEqual(result['reason'], 'global_vehicle_technology')

    def test_brand_origin_does_not_turn_an_australian_dealer_story_into_european_news(self):
        item = report('BMW dealer network expands across Australia',
                      summary='German manufacturer BMW is adding dealerships in Sydney.')
        self.assertFalse(candidate_assessment(item, NOW)['eligible'])

    def test_foreign_price_and_european_price_news_do_not_use_ai_short_publisher(self):
        for title, summary in [('Ferrari EV gets Australian price tag', 'This EV is also sold in Europe.'),
                               ('Tesla cuts EV prices in Sweden', '')]:
            self.assertFalse(candidate_assessment(report(title, summary=summary), NOW)['eligible'])

    def test_rumours_stationary_storage_hydrogen_and_domestic_policy_are_held(self):
        for title in ['BMW EV spotted testing in Germany', 'CATL sodium-ion BESS for balcony solar',
                      'Toyota hydrogen car at Australian festival',
                      'China exempts sodium-ion batteries from consumption tax',
                      'Ambitious electrification targets require electric vehicles']:
            self.assertFalse(candidate_assessment(report(title), NOW)['eligible'], title)

    def test_wltp_does_not_prove_european_availability(self):
        item = report('BYD electric sedan launches in China', summary='Up to 700 km WLTP range.')
        result = candidate_assessment(item, NOW)
        self.assertTrue(result['eligible'])
        self.assertEqual(result['reason'], 'international_vehicle_development')
        self.assertFalse(candidate_assessment(report('Chery Tiggo receives a safety rating in Europe'), NOW)['eligible'],
                         'A manufacturer name alone does not identify a battery-electric vehicle')

    def test_stale_future_and_previously_attempted_items_never_enter_paid_queue(self):
        for days in [8, -1]:
            self.assertFalse(candidate_assessment(report('BMW electric car launches in Sweden', days=days), NOW)['eligible'])
        item = report('BMW electric car launches in Sweden')
        self.assertEqual(ranked_candidates([item], {'carnewschina'}, [item['url']], NOW)[0], [])

    def test_passages_retain_exact_dates_and_qualifications_beyond_the_prefix(self):
        identity = 'The new BMW i3 is an electric passenger car for the European market.'
        main = 'BMW i3 production starts in August 2026 at the Munich manufacturing plant.'
        range_quote = 'The BMW i3 offers up to 900 kilometres of range in the WLTP cycle.'
        condition = 'These BMW i3 WLTP values are provisional and depend on the selected vehicle equipment.'
        content = ('Unrelated website navigation and investor information. ' * 300) + '\n' + '\n'.join([identity, main, range_quote, condition])
        selected = passage_selection(content, 'New BMW i3 electric car range for Europe', 'The new BMW i3', 1100, primary=True)
        self.assertLessEqual(len(selected['CONTENT'].encode()), 1100)
        self.assertTrue(all(q in selected['CONTENT'] for q in [main, range_quote, condition]))
        for start, end in selected['passage_offsets']:
            self.assertIn(content[start:end], selected['CONTENT'])
        self.assertTrue(any(start > 1400 for start, _ in selected['passage_offsets']))

    def test_quotes_do_not_cross_omitted_passages_or_split_foreign_sentences(self):
        b, _ = fixtures.fixture()
        catalog = evidence_catalog(b)
        for ref in catalog.values():
            self.assertIn(ref['quote'], b['items'][int(ref['source'][1:])]['payload']['content'])
            self.assertNotIn('...', ref['quote'])
        content = '这是一个完全合成的电池技术测试句子，用于隔离字符边界回归检查。' * 3
        selected = passage_selection(content, 'Synthetic battery technology', 'Synthetic', 500, primary=True)
        for start, end in selected['passage_offsets']:
            self.assertTrue(content[start:end].endswith('。'))
        for view in source_views(b):
            self.assertLessEqual(len(view['CONTENT'].encode()), 1400 if view['id'] == 's0' else 1600)

    def test_wrong_model_primary_is_not_corroboration(self):
        lead = report('BMW i3 electric car launches in Europe')
        primary = {'payload': {'title': 'BMW iX3 electric SUV', 'content': 'BMW presents its electric iX3 for Europe.'}}
        self.assertFalse(primary_identity_matches(lead, primary))

    def test_an_accessible_but_wrong_primary_does_not_hide_a_matching_source(self):
        url = fixtures.REPORT_URL
        wrong = 'https://www.bmwgroup.com/en/news/general/2026/ix3.html'
        correct = 'https://www.bmwgroup.com/en/news/general/2026/bmwi3.html'
        body = 'BMW i3 is an electric passenger car for Europe. ' * 30
        class Collector:
            def __init__(self): self.calls = []
            def fetch(self, requested, source, **kwargs):
                self.calls.append(requested)
                title = 'BMW iX3 electric SUV' if requested == wrong else 'BMW i3 electric sedan for Europe'
                links = f'<a href="{wrong}">Background</a><a href="{correct}">Exact model</a>' if requested == url else ''
                html = f'<html><head><link rel="canonical" href="{requested}"><meta property="og:title" content="{title}"><meta property="article:published_time" content="{NOW.isoformat()}"></head><body><article class="article_detail__content">{body}{links}</article></body></html>'
                return 200, {}, html, requested
        collector = Collector()
        bundle = collect_bundle('carnewschina', url, collector, now=NOW)
        self.assertEqual(bundle['items'][1]['url'], correct)
        self.assertIn(wrong, collector.calls)
        self.assertIn('publisher_primary_subject_mismatch', ' '.join(bundle['support_fetch_errors']))

    def test_approved_discovery_is_tried_when_a_direct_primary_is_blocked(self):
        url = fixtures.REPORT_URL.replace('carnewschina.com', 'thedriven.io')
        blocked = 'https://www.press.bmwgroup.com/global/article/detail/T00000EN/synthetic'
        reference = 'https://www.bmwgroup.com/en/news/general/2026/bmwi3.html'
        body = 'BMW i3 is an electric passenger car for Europe. ' * 30
        class Collector:
            def fetch(self, requested, source, **kwargs):
                if requested == blocked:
                    raise ValueError('robots_disallowed')
                links = f'<a href="{blocked}">Pressroom</a>' if requested == url else ''
                html = f'<html><head><link rel="canonical" href="{requested}"><meta property="og:title" content="BMW i3 electric car for Europe"><meta property="article:published_time" content="{NOW.isoformat()}"></head><body><article class="entry-content">{body}{links}</article></body></html>'
                return 200, {}, html, requested
        edge = {'from_url': 'https://www.bmwgroup.com', 'to_url': reference, 'method': 'approved_model_reference'}
        with patch('news_publisher_sources.corroboration_candidates', return_value=[(reference, edge)]):
            bundle = collect_bundle('thedriven', url, Collector(), now=NOW)
        self.assertEqual(bundle['items'][1]['url'], reference)
        self.assertEqual(bundle['provenance'], [edge])

    def test_primary_dates_and_fact_density_are_checked_before_writing(self):
        for kind in ['old', 'future', 'thin', 'wrong-model']:
            b, _ = fixtures.fixture()
            p = b['items'][1]['payload']
            if kind == 'old': p['published_at'] = (NOW - timedelta(days=60)).isoformat()
            if kind == 'future': p['published_at'] = (NOW + timedelta(days=5)).isoformat()
            if kind == 'thin': p['content'] = fixtures.QUOTES[0]
            if kind == 'wrong-model':
                b['items'][0]['payload']['title'] = 'BMW i3 electric car launches in Europe'
                p.update(title='BMW iX3 electric SUV', content='BMW iX3 production for Europe is planned at the factory.')
            p['content_hash'] = hashlib.sha256(p['content'].encode()).hexdigest()
            b['bundle_hash'] = artifact_hash({k: v for k, v in b.items() if k != 'bundle_hash'})
            self.assertFalse(evidence_readiness(b, NOW)['ready'], kind)

    def test_preselection_does_not_relax_actual_relevance_or_fact_validation(self):
        b, p = fixtures.fixture()
        self.assertTrue(evidence_readiness(b, NOW)['ready'])
        p['extraction']['sweden_relevance'] = .4
        self.assertIn('publisher_insufficient_swedish_relevance', precheck(b, p, NOW)['errors'])
        p['extraction']['facts'][0]['statement'] += ' 999 kWh.'
        self.assertTrue(any('number_not_in_evidence' in e for e in precheck(b, p, NOW)['errors']))

    def test_thin_source_cannot_buy_even_the_writer_call(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = fixtures.PublisherLifecycleTests().setup_environment(stack, folder)
            p = b['items'][1]['payload']
            p['content'] = fixtures.QUOTES[0]
            p['content_hash'] = hashlib.sha256(p['content'].encode()).hexdigest()
            b['bundle_hash'] = artifact_hash({k: v for k, v in b.items() if k != 'bundle_hash'})
            result = worker.perform(remote, b, private=True, ai=ai)
            self.assertEqual(result['status'], 'held_before_ai')
            self.assertEqual(ai.calls, [])
            self.assertEqual(remote.rows('news_ingestion_runs'), [])

    def test_selection_preview_does_not_write_publish_or_instantiate_provider(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, _ = fixtures.PublisherLifecycleTests().setup_environment(stack, folder)
            remote.put('news_items', {**b['items'][0], 'status': 'collected'})
            stack.enter_context(patch.object(worker, 'collect_bundle', return_value=b))
            stack.enter_context(patch.object(worker, 'NewsAi', side_effect=AssertionError('Free preview cannot call AI')))
            stack.enter_context(patch.object(worker, 'evidence_readiness', side_effect=lambda value: evidence_readiness(value, NOW)))
            stack.enter_context(patch.object(remote, 'put', side_effect=AssertionError('Preview must not write')))
            result = worker.preview_selection(remote, None)
            self.assertTrue(result['candidates'][0]['ready'])
            self.assertEqual((result['paid_calls'], result['published'], result['writes']), (0, 0, 0))


class PublisherCollectionWindowTests(unittest.TestCase):
    def test_a_ten_item_feed_has_one_bounded_second_page_without_duplicate_items(self):
        source = {'id': 'carnewschina', 'name': 'Synthetic', 'website': 'https://carnewschina.com',
                  'kind': 'publisher', 'enabled': True, 'feeds': ['https://carnewschina.com/feed/'], 'reliability': .8}
        class Collector:
            def __init__(self): self.calls = []
            def fetch(self, url, config, conditional=None):
                self.calls.append(url)
                indexes = range(8, 18) if '?paged=2' in url else range(10)
                items = ''.join(f'<item><title>Synthetic electric car {i}</title><link>https://carnewschina.com/2026/11/01/synthetic-{i}/</link><pubDate>Sun, 01 Nov 2026 12:00:00 GMT</pubDate></item>' for i in indexes)
                return 200, {}, '<rss><channel>' + items + '</channel></rss>', url
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'collection.sqlite')) as store:
            collector = Collector()
            result = news_engine.collect(store, [source], collector, max_items=3, publisher_lookback=20)
            self.assertEqual(result['new_items'], 18)
            self.assertEqual(collector.calls, [source['feeds'][0], source['feeds'][0] + '?paged=2'])

    def test_twenty_metadata_items_only_for_selected_publishers_and_one_safe_expansion(self):
        sources = [{'id': key, 'name': key, 'website': 'https://' + host, 'kind': 'publisher',
                    'enabled': True, 'feeds': ['https://' + host + '/feed/'], 'reliability': .8}
                   for key, host in [('carnewschina', 'carnewschina.com'), ('thedriven', 'thedriven.io'), ('other', 'other.example')]]
        class Collector:
            def __init__(self): self.calls = []
            def fetch(self, url, source, conditional):
                self.calls.append((source['id'], dict(conditional)))
                entries = ''.join(f'<item><title>Synthetic electric car {i}</title><link>{source["website"]}/2026/11/01/synthetic-{i}/</link><pubDate>Sun, 01 Nov 2026 12:00:00 GMT</pubDate><description>Synthetic EV metadata.</description></item>' for i in range(25))
                return 200, {'ETag': 'synthetic-etag'}, '<rss><channel>' + entries + '</channel></rss>', url
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'collection.sqlite')) as store:
            collector = Collector()
            self.assertEqual(news_engine.collect(store, sources, collector, max_items=3)['new_items'], 9)
            for key in ('carnewschina', 'thedriven'):
                old = store.get('news_sources', key)
                old['payload']['collected_window'] = 20  # Previous implementation read only one ten-item page.
                store.put('news_sources', old)
            report = news_engine.collect(store, sources, collector, max_items=3, publisher_lookback=20)
            self.assertEqual(report['new_items'], 34)
            self.assertEqual(len([r for r in store.rows('news_items') if r['source_id'] == 'other']), 3)
            self.assertEqual(collector.calls[-2:], [('carnewschina', {}), ('thedriven', {})], 'A larger window must not reuse a 304 from the old smaller window')
            self.assertEqual(news_engine.collect(store, sources, collector, max_items=3, publisher_lookback=20)['new_items'], 0)
            self.assertEqual(len(collector.calls), 5, 'The normal polling interval is restored after widening once')

    def test_zero_item_limit_cannot_be_overridden_by_the_publisher_window(self):
        source = {'id': 'carnewschina', 'name': 'Synthetic', 'website': 'https://carnewschina.com',
                  'kind': 'publisher', 'enabled': True, 'feeds': ['https://carnewschina.com/feed/'], 'reliability': .8}
        class Collector:
            def fetch(self, url, source, conditional):
                return 200, {}, '<rss><channel><item><title>Synthetic EV</title><link>https://carnewschina.com/test/</link><pubDate>Sun, 01 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>', url
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'collection.sqlite')) as store:
            self.assertEqual(news_engine.collect(store, [source], Collector(), max_items=0, publisher_lookback=20)['new_items'], 0)
            self.assertEqual(store.rows('news_items'), [])


if __name__ == '__main__':
    unittest.main()
