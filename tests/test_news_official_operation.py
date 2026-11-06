"""Synthetic official-first lifecycle, not a real provider or publication proof."""
import copy
from contextlib import closing, ExitStack
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_publisher_articles as fixtures
import test_news_original_discovery as pages
from news_publisher_sources import (collect_bundle, bundle_errors, official_lead_url, OFFICIAL_LEAD_SOURCES,
                                    item_from_document, primary_source, refresh_bundle, same_sources)
from news_publisher_articles import evidence_readiness, precheck, writer_call, stage, evidence_catalog
from news_publisher_selection import candidate_assessment, literal_spans
from news_store import NewsStore, artifact_hash
import run_publisher_news as worker
from news_run_summary import summarize

NOW = fixtures.NOW
URL = 'https://www.volkswagen-newsroom.com/en/press-releases/synthetic-battery-project-99997'
PUBLISHER_FIXTURE = fixtures.fixture


def fixture():
    old, packet = PUBLISHER_FIXTURE()
    item = item_from_document(URL, primary_source(URL), {
        'title': old['items'][0]['payload']['title'], 'published_at': NOW.isoformat(),
        'content': old['items'][1]['payload']['content']}, NOW)
    item['payload']['summary'] = item['payload']['content'][:500]
    bundle = {'items': [item], 'provenance': [], 'evidence_basis': 'official_release', 'support_fetch_errors': []}
    bundle['bundle_hash'] = artifact_hash(bundle)
    for fact in packet['extraction']['facts']:
        fact['support'][0]['source'] = 's0'
    packet['article']['intro'] = 'Enligt Volkswagen Newsroom ' + packet['article']['intro'][0].lower() + packet['article']['intro'][1:]
    return bundle, packet


class OfficialOperationTests(unittest.TestCase):
    def test_official_release_is_a_single_real_primary_not_a_fake_publisher_pair(self):
        b, p = fixture()
        self.assertEqual(bundle_errors(b, NOW), [])
        self.assertTrue(evidence_readiness(b, NOW)['ready'])
        self.assertTrue(precheck(b, p, NOW)['passed'], precheck(b, p, NOW))
        self.assertTrue(all(v['source'] == 's0' for v in evidence_catalog(b).values()))
        self.assertIn('ORIGINAL official release', writer_call(b)[2])

    def test_single_source_requires_explicit_official_authority_and_basis(self):
        self.assertIn('vw-sweden-press', OFFICIAL_LEAD_SOURCES)
        for url in [URL.replace('volkswagen-newsroom.com', 'volkswagen-newsroom.com.evil.example'),
                    URL + '?campaign=1', URL.replace('https:', 'http:')]:
            self.assertFalse(official_lead_url('vw-press', url))
        for change in ('basis', 'source_kind', 'source_id', 'second_source'):
            b, _ = fixture()
            if change == 'basis': b['evidence_basis'] = 'primary'
            elif change == 'second_source': b['items'].append(copy.deepcopy(b['items'][0]))
            elif change == 'source_id': b['items'][0]['source_id'] = 'carnewschina'
            else: b['items'][0]['payload']['source_kind'] = 'publisher'
            b['bundle_hash'] = artifact_hash({k: v for k, v in b.items() if k != 'bundle_hash'})
            self.assertTrue(bundle_errors(b, NOW), change)
        self.assertFalse(official_lead_url('aaa-data', 'https://www.aaa-data.fr/actualites/synthetic/'))

    def test_mobility_release_uses_actual_scoped_date_and_narrative_not_image_tables(self):
        from news_pressrooms import document, discover
        from news_publisher_sources import PRIMARY_AUTHORITIES
        url = 'https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/synthetic-registration-story'
        source = PRIMARY_AUTHORITIES['mobilitysweden.se']
        self.assertTrue(official_lead_url('mobility-sweden', url))
        self.assertFalse(official_lead_url('mobility-sweden', url.replace('/nyregistreringar-2026/', '/prognos/')))
        html = ('<meta property="og:title" content="Synthetic registration story">'
                '<nav>Unrelated news and dates</nav><div class="article">'
                '<p class="article_date">1 november 2026</p><div class="article_text">'
                '<p>' + ' '.join(fixtures.QUOTES) + '</p><img src="statistics.png">'
                '</div><div class="article_text"></div></div><footer>Unrelated footer</footer>')
        doc = document(html, exclude_tables=True)
        self.assertEqual(doc['published_at'], '2026-11-01T00:00:00+00:00')
        self.assertNotIn('Unrelated', doc['body'])
        self.assertNotIn('statistics.png', doc['body'])
        collector = pages.FakeCollector({url: html})
        b = collect_bundle('mobility-sweden', url, collector, now=NOW)
        self.assertEqual(b['items'][0]['payload']['content'], doc['body'])
        self.assertIn('registrations, not orders or sales', writer_call(b)[2])
        rows, errors = discover('<a href="' + url + '">Release</a>', source['indexes'][0], source, collector, 3, NOW)
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]['published_at'], doc['published_at'])
        for date in ('32 november 2026', '2 november 2025', '2 november 2027'):
            collector.documents[url] = html.replace('1 november 2026', date)
            with self.assertRaises(ValueError):
                collect_bundle('mobility-sweden', url, collector, now=NOW)

    def test_fresh_official_release_is_fetched_and_feed_dates_cannot_be_replaced(self):
        html = pages.page(URL, title='Synthetic battery project', body=' '.join(fixtures.QUOTES) * 2, date=NOW.isoformat())
        c = pages.FakeCollector({URL: html})
        b = collect_bundle('vw-press', URL, c, feed_date=NOW.isoformat(), now=NOW)
        self.assertEqual([i['url'] for i in b['items']], [URL])
        self.assertTrue(c.calls[0][1]['editorial'])
        self.assertTrue(same_sources(b, refresh_bundle(b, c, NOW)))
        with self.assertRaisesRegex(ValueError, 'feed_date_conflict'):
            collect_bundle('vw-press', URL, c, feed_date='2026-10-31T00:00:00Z', now=NOW)
        c.documents[URL] = html.replace(NOW.isoformat(), '2025-01-01T00:00:00Z')
        with self.assertRaisesRegex(ValueError, 'stale_report'):
            collect_bundle('vw-press', URL, c, now=NOW)

    def test_official_leads_enter_existing_queue_but_old_failed_urls_do_not(self):
        b, _ = fixture()
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'fixture.sqlite')) as store:
            store.put('news_items', {**b['items'][0], 'status': 'collected'})
            with patch.object(worker, 'now_iso', return_value=NOW.isoformat()):
                queue, _ = worker.selection_queue(store, worker.ARTICLE_LEAD_SOURCES)
                self.assertEqual([i['url'] for i, _ in queue], [URL])
                store.put('news_ingestion_runs', {'id': 'old-failed', 'payload': {
                    'recipe': worker.RECIPE, 'kind': 'short_daily', 'state': 'quarantined', 'url': URL}})
                self.assertEqual(worker.selection_queue(store, worker.ARTICLE_LEAD_SOURCES)[0], [])

    def test_official_attribution_and_real_provider_receipts_remain_required(self):
        b, p = fixture()
        original = copy.deepcopy(p)
        p['article']['intro'] = p['article']['intro'].replace('Enligt Volkswagen Newsroom ', '')
        self.assertIn('official_intro_attribution_missing', precheck(b, p, NOW)['errors'])
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'fixture.sqlite')) as store:
            row = stage(store, b, original, fixtures.accepted_review(b, original), [], now=NOW)
            self.assertEqual(row['status'], 'quarantined')
            with self.assertRaises(ValueError): store.publish(row['id'])

    def test_eight_publisher_candidates_cannot_starve_a_fresh_official_release(self):
        b, _ = fixture()
        b['items'][0]['payload'].update(title='Synthetic product announcement', summary='', content='')
        report, _ = fixtures.fixture()
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'fixture.sqlite')) as store:
            store.put('news_items', {**b['items'][0], 'status': 'collected'})
            for index in range(10):
                item = copy.deepcopy(report['items'][0])
                item['url'] = item['url'].replace('synthetic-battery-project', 'synthetic-' + str(index))
                item['id'] = worker.stable_id(item['url'])
                store.put('news_items', {**item, 'status': 'collected'})
            with patch.object(worker, 'now_iso', return_value=NOW.isoformat()):
                queue, _ = worker.selection_queue(store, worker.ARTICLE_LEAD_SOURCES)
            self.assertEqual(len(queue), 8)
            self.assertEqual(queue[0][0]['url'], URL)

    def test_unvalidated_table_context_is_not_bypassed_by_an_official_lead(self):
        b, p = fixture()
        b['items'][0]['payload']['unvalidated_table_context'] = True
        b['bundle_hash'] = artifact_hash({k: v for k, v in b.items() if k != 'bundle_hash'})
        self.assertFalse(evidence_readiness(b, NOW)['ready'])
        self.assertIn('publisher_table_context_requires_validation', precheck(b, p, NOW)['errors'])
        with self.assertRaisesRegex(ValueError, 'table_context'): writer_call(b)

    def test_swedish_ev_compounds_and_europa_are_triaged_without_promoting_hybrids_or_prices(self):
        data = {'title': 'Syntetisk elbilsutveckling i Europa', 'summary': 'Elbilsleveranserna i Sverige uppges ha utvecklats.',
                'published_at': NOW.isoformat()}
        self.assertTrue(candidate_assessment(data, NOW)['eligible'])
        for title in ('Ny fullhybriddrivlina i Europa', 'Nya priser pa elbilar i Sverige',
                      'Privatleasingerbjudande for elbilar i Sverige'):
            self.assertFalse(candidate_assessment({**data, 'title': title}, NOW)['eligible'])

    def test_thin_official_metadata_can_be_fetched_but_cannot_skip_content_triage(self):
        b, _ = fixture()
        b['items'][0]['payload'].update(title='Synthetic product announcement', summary='')
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'fixture.sqlite')) as store:
            store.put('news_items', {**b['items'][0], 'status': 'collected'})
            with patch.object(worker, 'now_iso', return_value=NOW.isoformat()):
                queue, _ = worker.selection_queue(store, worker.ARTICLE_LEAD_SOURCES)
            self.assertEqual(queue[0][1]['reason'], 'official_content_triage_required')
        b['items'][0]['payload']['content'] = 'Synthetic unrelated corporate calendar. ' * 30
        b['items'][0]['payload']['content_hash'] = hashlib.sha256(b['items'][0]['payload']['content'].encode()).hexdigest()
        b['bundle_hash'] = artifact_hash({k: v for k, v in b.items() if k != 'bundle_hash'})
        self.assertFalse(evidence_readiness(b, NOW)['ready'])

    def test_model_abbreviation_does_not_break_literal_identity_passages(self):
        text = 'Volkswagen ID. Polo is an electric passenger car for the European market. The vehicle is described in this synthetic source.'
        quotes = [text[a:b] for a, b in literal_spans(text)]
        self.assertIn('Volkswagen ID. Polo is an electric passenger car for the European market.', quotes)

    def test_pressroom_body_excludes_unrelated_page_text_and_table_values(self):
        from news_pressrooms import document
        html = '<main>Unrelated page text.<div id="article-text">' + ' '.join(fixtures.QUOTES) + '<table><tr><td>9999</td></tr></table></div></main>'
        self.assertNotIn('9999', document(html, exclude_tables=True)['body'])
        self.assertNotIn('Unrelated', document(html, exclude_tables=True)['body'])
        self.assertIn('9999', document(html)['body'], 'Historical parsing remains unchanged by default')

    def test_operational_summary_distinguishes_empty_runs_without_leaking_source_or_provider_bodies(self):
        result = summarize({'status': 'no_eligible_new_source', 'published': 0,
            'skipped': [{'url': 'https://private-fixture.example', 'content': 'Private synthetic source body'}],
            'writer_output': 'Private synthetic provider response', 'cost_micro_usd': 0})
        self.assertEqual(result['held_candidates'], 1)
        self.assertEqual(result['published'], 0)
        self.assertNotIn('Private', json.dumps(result))
        self.assertNotIn('https://', json.dumps(result))

    def test_official_article_uses_both_receipts_and_existing_one_per_day_publication(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(fixtures, 'fixture', side_effect=fixture))
            remote, b, _, ai = fixtures.PublisherLifecycleTests().setup_environment(stack, folder)
            remote.put('news_items', {**b['items'][0], 'status': 'collected'})
            stack.enter_context(patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}))
            stack.enter_context(patch.object(worker, 'NewsAi', return_value=ai))
            stack.enter_context(patch.object(worker, 'require_recent_publication'))
            stack.enter_context(patch.object(worker, 'collect_bundle', return_value=b))
            stack.enter_context(patch.object(worker, 'refresh_bundle', return_value=copy.deepcopy(b)))
            stack.enter_context(patch.object(worker, 'models_for_news', return_value={}))
            stack.enter_context(patch.object(worker, 'queue_verification'))
            stack.enter_context(patch.object(worker, 'export_public', return_value={'synthetic': True}))
            result = worker.daily(remote, None)
            self.assertEqual(result['status'], 'published', result)
            self.assertEqual(result['cost_micro_usd'], 2000)
            self.assertEqual(ai.calls, ['swedish_ev_article', 'ev_news_independent_audit'])
            self.assertEqual(worker.daily(remote, None)['status'], 'daily_limit')

    def test_official_source_never_skips_budget_or_independent_rejection(self):
        for allowance, corrupt in ((1, False), (250000, True)):
            with self.subTest(allowance=allowance), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                stack.enter_context(patch.object(fixtures, 'fixture', side_effect=fixture))
                remote, b, _, ai = fixtures.PublisherLifecycleTests().setup_environment(stack, folder,
                    allowance=allowance, corrupt=corrupt)
                result = worker.perform(remote, b, private=False, ai=ai)
                self.assertEqual(result['status'], 'deferred_budget' if allowance == 1 else 'quarantined')
                self.assertEqual(remote.public_articles(), [])
                self.assertEqual(len(ai.calls), 0 if allowance == 1 else 1)

    def test_supported_news_brand_does_not_require_a_published_model_record(self):
        b, p = fixture()
        p['extraction']['facts'][0]['statement'] = 'Volkswagen beskriver ett syntetiskt test for elbilar i Europa.'
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'fixture.sqlite')) as store:
            row = stage(store, b, p, fixtures.accepted_review(b, p), [], now=NOW)
            self.assertIn('Volkswagen', row['payload']['brands'])
            self.assertEqual(row['payload']['related_models'], [])

    def test_two_distinct_candidates_count_old_keys_without_changing_rejected_records(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = fixtures.PublisherLifecycleTests().setup_environment(stack, folder)
            old = {'kind': 'short_daily', 'recipe': worker.RECIPE, 'started_at': NOW.isoformat(),
                   'url': b['items'][0]['url'], 'state': 'quarantined', 'status': 'quarantined',
                   'cost_status': 'settled', 'cost_micro_usd': 1000}
            remote.put('news_ingestion_runs', {'id': 'historical-day-only-key', 'payload': old})
            self.assertTrue(worker.perform(remote, b, private=False, ai=ai)['reused_attempt'])
            self.assertEqual(ai.calls, [])
            second = copy.deepcopy(b)
            second['items'][0]['url'] += '-different'
            second['bundle_hash'] = artifact_hash({k: v for k, v in second.items() if k != 'bundle_hash'})
            stack.enter_context(patch.object(worker, 'bundle_errors', return_value=[]))
            stack.enter_context(patch.object(worker, 'evidence_readiness', return_value={'ready': True}))
            stack.enter_context(patch.object(worker, 'precheck', return_value={'passed': False, 'errors': ['synthetic-rejection']}))
            result = worker.perform(remote, second, private=False, ai=ai)
            self.assertEqual(result['status'], 'quarantined')
            self.assertEqual(len(ai.calls), 1)
            third = copy.deepcopy(second)
            third['items'][0]['url'] += '-third'
            self.assertEqual(worker.perform(remote, third, private=False, ai=ai)['status'], 'daily_attempt_limit')
            self.assertEqual(len(ai.calls), 1)
            self.assertEqual(remote.get('news_ingestion_runs', 'historical-day-only-key')['payload'], old)

    def test_daily_fallback_requires_settled_rejection_and_a_different_candidate(self):
        for cost_status in ('settled', None, 'reservation_retained_usage_unknown', 'reconciliation_required_no_more_calls'):
            with self.subTest(cost_status=cost_status), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                remote, b, _, _ = fixtures.PublisherLifecycleTests().setup_environment(stack, folder)
                second = copy.deepcopy(b)
                second['items'][0]['url'] += '-different'
                queue = [(b['items'][0], {}), (second['items'][0], {})]
                stack.enter_context(patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}))
                stack.enter_context(patch.object(worker, 'selection_queue', return_value=(queue, [])))
                stack.enter_context(patch.object(worker, 'collect_bundle', side_effect=[b, second]))
                stack.enter_context(patch.object(worker, 'require_recent_publication'))
                stack.enter_context(patch.object(worker, 'evidence_readiness', return_value={'ready': True}))
                rejection = {'status': 'quarantined', 'cost_status': cost_status, 'published': 0}
                perform = stack.enter_context(patch.object(worker, 'perform', side_effect=[rejection,
                    {'status': 'passed', 'packet': {}}]))
                stack.enter_context(patch.object(worker, 'event_duplicate', return_value=False))
                release = stack.enter_context(patch.object(worker, 'release', return_value={'status': 'published', 'published': 1}))
                result = worker.daily(remote, None)
                self.assertEqual(perform.call_count, 2 if cost_status == 'settled' else 1)
                self.assertEqual(release.call_count, 1 if cost_status == 'settled' else 0)
                self.assertEqual(result['published'], 1 if cost_status == 'settled' else 0)
                if cost_status == 'settled':
                    self.assertNotEqual(perform.call_args_list[0].args[1]['items'][0]['url'],
                                        perform.call_args_list[1].args[1]['items'][0]['url'])

    def test_two_prior_daily_attempts_stop_before_fetch_or_paid_work(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, _, _, ai = fixtures.PublisherLifecycleTests().setup_environment(stack, folder)
            for index in range(2):
                remote.put('news_ingestion_runs', {'id': 'old-key-' + str(index), 'payload': {
                    'kind': 'short_daily', 'recipe': 'historical-recipe', 'state': 'quarantined',
                    'started_at': NOW.isoformat(), 'url': 'synthetic-' + str(index)}})
            stack.enter_context(patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}))
            stack.enter_context(patch.object(worker, 'selection_queue', side_effect=AssertionError('No more source work')))
            self.assertEqual(worker.daily(remote, None)['status'], 'daily_attempt_limit')
            self.assertEqual(ai.calls, [])


if __name__ == '__main__': unittest.main()
