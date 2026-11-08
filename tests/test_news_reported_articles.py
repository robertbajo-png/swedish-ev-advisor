"""Synthetic two-editor tests. These do not constitute real editorial approvals."""
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
from news_publisher_registry import publisher_templates, PUBLISHERS
from news_publisher_sources import item_from_document, bundle_errors, parse_publisher, collect_bundle, refresh_bundle, same_sources
from news_reporting_policy import independence, same_event
from news_publisher_articles import (precheck, check_review, stage, evidence_readiness, pair_bound, LIMITS)
from news_ai import NewsAi
from news_store import NewsStore, artifact_hash
import test_news_publisher_articles as fixtures
import run_publisher_news as worker

NOW = fixtures.NOW
PEER_QUOTES = [
    'Electric passenger vehicle batteries are the focus of a planned European research project at Nordic Cells.',
    'Two different battery constructions will undergo comparison through one common laboratory methodology.',
    'Controlled conditions in an indoor laboratory are planned for both designs before development proceeds.',
    'The programme will record charging behaviour as well as repeated battery cycles during laboratory evaluation.',
    'A technical report is planned by the company following completion of the evaluation programme.',
    'Before the concluding report, researchers at an external university will examine the recorded measurement results.',
]


def reported_fixture():
    old, packet = fixtures.fixture()
    lead = copy.deepcopy(old['items'][0])
    peer = item_from_document(fixtures.REPORT_URL.replace('carnewschina.com', 'thedriven.io'), PUBLISHERS['thedriven'],
        {'title': 'European synthetic battery project', 'published_at': NOW.isoformat(),
         'content': ' '.join(PEER_QUOTES) + ' Additional synthetic European laboratory context for isolated source testing. ' * 8,
         'byline': 'Synthetic Peer Reporter'}, NOW)
    bundle = {'items': [lead, peer], 'evidence_basis': 'editorial_corroboration', 'support_fetch_errors': [],
              'provenance': [{'from_url': lead['url'], 'to_url': peer['url'], 'method': 'editorial_corroboration'}]}
    bundle['bundle_hash'] = artifact_hash(bundle)
    for i, fact in enumerate(packet['extraction']['facts']):
        fact['statement'] = 'Enligt CarNewsChina och The Driven ' + fact['statement'][0].lower() + fact['statement'][1:]
        fact['support'] = [{'source': 's0', 'quote': fixtures.QUOTES[i]}, {'source': 's1', 'quote': PEER_QUOTES[i]}]
    packet['article']['title'] = 'Rapporterat: europeiskt batteriprojekt hos Nordic Cells'
    packet['article']['intro'] = 'Enligt CarNewsChina och The Driven planerar Nordic Cells ett forskningsprojekt. ' + packet['article']['intro']
    for paragraph in packet['article']['paragraphs']:
        paragraph['text'] = 'Enligt medierna ' + paragraph['text'][0].lower() + paragraph['text'][1:]
    review = fixtures.accepted_review(bundle, packet)
    review.update(editorial_independence=True, reported_not_verified=True)
    return bundle, packet, review


def rehash(bundle):
    for item in bundle['items']:
        item['payload']['content_hash'] = hashlib.sha256(item['payload']['content'].encode()).hexdigest()
    bundle['bundle_hash'] = artifact_hash({k: v for k, v in bundle.items() if k != 'bundle_hash'})


class EditorialIndependenceTests(unittest.TestCase):
    def test_distinct_verified_teams_are_not_alone_sufficient_to_publish(self):
        bundle, packet, review = reported_fixture()
        self.assertTrue(independence(*bundle['items'])['passed'])
        self.assertEqual(bundle_errors(bundle, NOW), [])
        self.assertTrue(evidence_readiness(bundle, NOW)['ready'])
        result = precheck(bundle, packet, NOW)
        self.assertTrue(result['passed'], result)
        self.assertEqual(check_review(bundle, packet, review), [])
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'test.sqlite')) as store:
            row = stage(store, bundle, packet, review, [], now=NOW)
            self.assertEqual(row['status'], 'quarantined', 'Synthetic checks without real request receipts are not live approvals')
            with self.assertRaises(ValueError): store.publish(row['id'])

    def test_same_owner_or_same_author_is_not_independence(self):
        bundle, _, _ = reported_fixture()
        left, right = bundle['items']
        right['source_id'] = left['source_id']
        right['payload']['publisher_group'] = left['payload']['publisher_group']
        self.assertIn('editorial_common_owner_or_same_article', independence(left, right)['errors'])
        bundle, _, _ = reported_fixture()
        for item in bundle['items']: item['payload']['byline'] = 'Same Reporter'
        self.assertIn('editorial_same_author', independence(*bundle['items'])['errors'])

    def test_different_domains_cannot_override_registered_ownership(self):
        bundle, _, _ = reported_fixture()
        bundle['items'][1]['payload']['publisher_group'] = 'invented-independent-company'
        self.assertIn('editorial_owner_snapshot_changed', independence(*bundle['items'])['errors'])
        bundle, _, _ = reported_fixture()
        sister_sites = copy.deepcopy(PUBLISHERS)
        sister_sites['thedriven']['publisher_group'] = sister_sites['carnewschina']['publisher_group']
        bundle['items'][1]['payload']['publisher_group'] = sister_sites['carnewschina']['publisher_group']
        with patch('news_reporting_policy.PUBLISHERS', sister_sites):
            self.assertIn('editorial_common_owner_or_same_article', independence(*bundle['items'])['errors'])

    def test_circular_links_and_borrowed_attribution_are_rejected(self):
        for kind in ('link', 'attribution'):
            bundle, _, _ = reported_fixture()
            if kind == 'link':
                bundle['items'][1]['payload']['editorial_links'] = [bundle['items'][0]['url']]
            else:
                bundle['items'][1]['payload']['content'] += ' According to CarNewsChina the company described the project.'
            self.assertFalse(independence(*bundle['items'])['passed'], kind)

    def test_shared_wire_or_shared_editorial_upstream_cannot_count_twice(self):
        for kind in ('wire', 'url'):
            bundle, _, _ = reported_fixture()
            for item in bundle['items']:
                if kind == 'wire': item['payload']['content'] += ' Reuters reported the corporate statement.'
                else: item['payload']['editorial_links'] = ['https://apnews.com/article/synthetic-event']
            self.assertIn('editorial_shared_upstream_or_wire', independence(*bundle['items'])['errors'])

    def test_copied_and_syndicated_bodies_do_not_count_as_two_reports(self):
        bundle, _, _ = reported_fixture()
        bundle['items'][1]['payload']['content'] = bundle['items'][0]['payload']['content']
        self.assertIn('editorial_copy_or_syndication', independence(*bundle['items'])['errors'])

    def test_same_official_release_does_not_become_independent_measurement(self):
        bundle, packet, _ = reported_fixture()
        for item in bundle['items']:
            item['payload']['editorial_links'] = ['https://www.bmwgroup.com/en/news/general/2026/synthetic.html']
        self.assertTrue(independence(*bundle['items'])['passed'])
        packet['article']['paragraphs'][0]['text'] += ' Vi har verifierat uppgifterna.'
        rehash(bundle)
        self.assertTrue(any('presented_as_verified' in e for e in precheck(bundle, packet, NOW)['errors']))

    def test_different_model_or_old_event_is_held(self):
        for kind in ('model', 'date'):
            bundle, _, _ = reported_fixture()
            if kind == 'model':
                bundle['items'][0]['payload']['title'] = 'BMW i3 electric model launches in Europe'
                bundle['items'][1]['payload']['title'] = 'BMW iX3 electric model launches in Europe'
            else:
                bundle['items'][1]['payload']['published_at'] = (NOW - timedelta(days=5)).isoformat()
            self.assertFalse(same_event(*bundle['items']), kind)

    def test_ordinary_fact_can_use_one_literal_supporting_publication(self):
        bundle, packet, _ = reported_fixture()
        packet['extraction']['facts'][0]['support'] = packet['extraction']['facts'][0]['support'][:1]
        self.assertTrue(precheck(bundle, packet, NOW)['passed'])

    def test_conflicting_numbers_cannot_be_hidden_in_the_union_of_evidence(self):
        bundle, packet, _ = reported_fixture()
        fact = packet['extraction']['facts'][0]
        fact['statement'] += ' 90 kWh.'
        fact['support'][0]['quote'] += ' 90 kWh.'
        bundle['items'][0]['payload']['content'] += ' ' + fact['support'][0]['quote']
        rehash(bundle)
        errors = precheck(bundle, packet, NOW)['errors']
        self.assertIn('publisher_reported_fact_conflicting_numbers_or_units:f1', errors)

    def test_attribution_and_reported_headline_cannot_be_removed(self):
        for field in ('title', 'intro', 'paragraph'):
            bundle, packet, _ = reported_fixture()
            if field == 'title': packet['article']['title'] = 'Nordic Cells utvecklar batterier'
            if field == 'intro': packet['article']['intro'] = packet['article']['intro'].replace('CarNewsChina', '')
            if field == 'paragraph': packet['article']['paragraphs'][0]['text'] = packet['article']['paragraphs'][0]['text'].replace('Enligt medierna ', '')
            self.assertFalse(precheck(bundle, packet, NOW)['passed'], field)

    def test_reported_facts_cannot_be_promoted_to_swedish_availability(self):
        bundle, packet, _ = reported_fixture()
        packet['extraction']['facts'][0]['market'] = 'SE'
        self.assertIn('publisher_reported_swedish_scope_unsupported:f1', precheck(bundle, packet, NOW)['errors'])
        packet['extraction']['facts'][0]['market'] = 'GLOBAL'
        packet['extraction']['facts'][0]['statement'] += ' Modellen kommer till Sverige.'
        self.assertIn('publisher_reported_swedish_scope_unsupported:f1', precheck(bundle, packet, NOW)['errors'])

    def test_independent_review_must_confirm_both_independence_and_reported_status(self):
        for flag in ('editorial_independence', 'reported_not_verified'):
            bundle, packet, review = reported_fixture()
            review[flag] = False
            self.assertTrue(check_review(bundle, packet, review), flag)

    def test_full_reported_pair_fits_original_daily_ceiling_without_provider_calls(self):
        bundle, _, _ = reported_fixture()
        ai = NewsAi.__new__(NewsAi)
        ai.model, ai.output_limits = 'gpt-6-sol', LIMITS
        self.assertLess(pair_bound(ai, bundle), 250000)

    def test_reported_article_can_follow_the_same_reviewed_production_path(self):
        bundle, packet, review = reported_fixture()
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(fixtures, 'fixture', return_value=(bundle, packet)))
            stack.enter_context(patch.object(fixtures, 'accepted_review', return_value=review))
            remote, b, _, ai = fixtures.PublisherLifecycleTests().setup_environment(stack, folder)
            remote.put('news_items', {**b['items'][0], 'status': 'collected'})
            stack.enter_context(patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}))
            stack.enter_context(patch.object(worker, 'NewsAi', return_value=ai))
            stack.enter_context(patch.object(worker, 'collect_bundle', return_value=b))
            stack.enter_context(patch.object(worker, 'refresh_bundle', return_value=copy.deepcopy(b)))
            stack.enter_context(patch.object(worker, 'models_for_news', return_value={}))
            stack.enter_context(patch.object(worker, 'queue_verification'))
            stack.enter_context(patch.object(worker, 'export_public', return_value={}))
            result = worker.daily(remote, None)
            self.assertEqual(result['published'], 1, result)
            row = remote.public_articles()[0]
            self.assertTrue(row['title'].startswith('Rapporterat:'))
            self.assertTrue(all(source['kind'] == 'publisher' for source in row['sources']))
            self.assertEqual(ai.calls, ['swedish_ev_article', 'ev_news_independent_audit'])


class SharedPublisherTemplateTests(unittest.TestCase):
    def test_capture_and_refresh_use_a_matching_editorial_pair_without_primary_access(self):
        b, _, _ = reported_fixture()
        by_url = {item['url']: item for item in b['items']}
        class Collector:
            def fetch(self, url, source, **kwargs):
                p = by_url[url]['payload']
                css = PUBLISHERS[by_url[url]['source_id']]['body_class']
                html = f'<html><head><link rel="canonical" href="{url}"><meta property="og:title" content="{p["title"]}"><meta property="article:published_time" content="{p["published_at"]}"><meta name="author" content="{p.get("byline", "")}"></head><body><article class="{css}">{p["content"]}</article></body></html>'
                return 200, {}, html, url
        collector = Collector()
        with patch('news_publisher_sources.corroboration_candidates', side_effect=ValueError('robots_disallowed')):
            captured = collect_bundle('carnewschina', b['items'][0]['url'], collector,
                now=NOW, corroborating_items=[b['items'][1]])
        self.assertEqual(captured['evidence_basis'], 'editorial_corroboration')
        self.assertIn('robots_disallowed', ' '.join(captured['support_fetch_errors']))
        refreshed = refresh_bundle(captured, collector, now=NOW)
        self.assertTrue(same_sources(captured, refreshed))
        by_url[b['items'][1]['url']]['payload']['content'] += ' Another newly added factual sentence changes the source snapshot.'
        self.assertFalse(same_sources(captured, refresh_bundle(captured, collector, now=NOW)))

    def test_new_template_needs_no_publisher_specific_python(self):
        sources = [{'id': 'synthetic', 'name': 'Synthetic outlet', 'website': 'https://source.example', 'kind': 'publisher'}]
        template = {'id': 'synthetic', 'publisher_group': 'synthetic-editorial', 'ownership_evidence_url': 'https://source.example/about/',
                    'can_lead': True, 'body_class': 'entry-content', 'article_path_pattern': '/news/[a-z-]+/'}
        self.assertEqual(publisher_templates(sources, [template])['synthetic']['publisher_group'], 'synthetic-editorial')
        template['ownership_evidence_url'] = 'https://unrelated.example/about/'
        with self.assertRaises(ValueError): publisher_templates(sources, [template])

    def test_known_parent_and_registered_host_cannot_be_overridden(self):
        sources = [{'id': 'synthetic', 'name': 'Synthetic', 'website': 'https://source.example', 'kind': 'publisher',
                    'publisher_group': 'shared-parent'}]
        template = {'id': 'synthetic', 'publisher_group': 'pretend-independent', 'ownership_evidence_url': 'https://source.example/about/'}
        with self.assertRaises(ValueError): publisher_templates(sources, [template])
        template.update(publisher_group='shared-parent', website='https://another.example')
        with self.assertRaises(ValueError): publisher_templates(sources, [template])

    def test_semantic_article_fallback_reuses_the_same_parser(self):
        url = fixtures.REPORT_URL
        html = fixtures.PublisherSourceTests().html().replace('<div class="article_detail__content">', '<article>').replace('</div>', '</article>')
        parsed = parse_publisher(html, url, 'carnewschina', now=NOW)
        self.assertIn('Synthetic EV laboratory', parsed['content'])


if __name__ == '__main__':
    unittest.main()
