"""Synthetic headline-context tests; never a paid audit or publication proof."""
import copy
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_publisher_articles as fixtures
from test_news_publisher_flexible_policy import single_fixture
from test_news_reported_articles import rehash
from news_publisher_articles import (evidence_catalog, evidence_readiness, precheck,
    writer_call, reviewer_call, resolve_writer_output, writing_evidence_plan,
    stage, check_review)
from news_publisher_sources import same_sources, collect_bundle, OriginalSourceNotFound
from news_publisher_selection import primary_identity_matches
from news_primary_discovery import candidate_related
from news_publisher_sources import parse_publisher, PUBLISHERS
from news_publisher_registry import publisher_templates
from news_store import NewsStore


def context_fixture():
    b, p, _ = single_fixture()
    title = 'Nordic Cells launches synthetic battery research programme for electric cars in China'
    old = p['extraction']['facts'][0]['support'][0]['quote']
    body = old.replace(' in Europe', '')
    item = b['items'][0]['payload']
    item['title'] = title
    item['content'] = item['content'].replace(old, body)
    item['summary'] = item['content'][:400]
    for fact in p['extraction']['facts']:
        fact['market'] = 'CN'
        fact['statement'] = fact['statement'].replace('europeiska', 'kinesiska')
    p['extraction']['facts'][0]['support'] = [
        {'source': 's0', 'quote': title}, {'source': 's0', 'quote': body}]
    p['extraction']['event']['subject'] = title
    article = p['article']
    article['title'] = article['title'].replace('Europa', 'Kina')
    article['intro'] = article['intro'].replace('Europa', 'Kina')
    for paragraph in article['paragraphs']:
        paragraph['text'] = paragraph['text'].replace('Europa', 'Kina')
    rehash(b)
    return b, p


class HeadlineContextTests(unittest.TestCase):
    def test_exact_headline_and_body_jointly_support_model_and_market(self):
        b, p = context_fixture()
        catalog = evidence_catalog(b)
        self.assertEqual(catalog['s0h0']['quote'], b['items'][0]['payload']['title'])
        self.assertNotIn(catalog['s0h0']['quote'], b['items'][0]['payload']['content'])
        result = precheck(b, p, fixtures.NOW)
        self.assertTrue(result['passed'], result)
        output = fixtures.encoded_fixture(b, p)
        original = copy.deepcopy(output)
        self.assertEqual(resolve_writer_output(b, output), p)
        self.assertEqual(output, original)

    def test_headline_alone_never_replaces_body_or_sensitive_corroboration(self):
        b, p = context_fixture()
        fact = p['extraction']['facts'][0]
        fact['support'] = fact['support'][:1]
        errors = precheck(b, p, fixtures.NOW)['errors']
        self.assertIn('publisher_headline_requires_body_support:f1', errors)
        fact['statement'] += ' Batteriet rymmer 90 kWh.'
        self.assertIn('publisher_reported_fact_needs_two_editors:f1', precheck(b, p, fixtures.NOW)['errors'])

    def test_context_title_cannot_pad_readiness_or_hide_changed_title(self):
        b, _ = context_fixture()
        self.assertEqual(writing_evidence_plan(b)['headline_context'],
                         [{'evidence_id': 's0h0', 'explicit_markets': ['CN']}])
        changed = copy.deepcopy(b)
        changed['items'][0]['payload']['title'] += ' changed'
        rehash(changed)
        self.assertFalse(same_sources(b, changed))
        b['items'][0]['payload']['content'] = 'The synthetic vehicle research project has one literal narrative sentence for this isolated test.'
        rehash(b)
        checked = evidence_readiness(b, fixtures.NOW)
        self.assertLess(checked['total_passages'], len(evidence_catalog(b)))
        self.assertIn('publisher_insufficient_literal_fact_material', checked['errors'])

    def test_modified_headline_quote_is_not_source_evidence(self):
        b, p = context_fixture()
        p['extraction']['facts'][0]['support'][0]['quote'] += ' in Sweden'
        self.assertIn('publisher_evidence_not_literal:f1', precheck(b, p, fixtures.NOW)['errors'])

    def test_source_headline_context_is_not_permission_to_copy_its_wording(self):
        b, p = context_fixture()
        p['article']['title'] = 'Rapporterat: ' + b['items'][0]['payload']['title']
        self.assertIn('publisher_source_overlap:title', precheck(b, p, fixtures.NOW)['errors'])

    def test_mandatory_body_conditions_take_all_twelve_slots_before_headline(self):
        b, _ = context_fixture()
        b['items'][0]['payload']['content'] = ' '.join(
            f'For this battery project, procedure {i} is required before laboratory work begins.'
            for i in range(12))
        rehash(b)
        catalog = evidence_catalog(b)
        self.assertEqual(len(catalog), 12)
        self.assertNotIn('s0h0', catalog)
        self.assertTrue(all('is required' in ref['quote'] for ref in catalog.values()))

    def test_writer_receives_plan_and_reviewer_sees_exact_title_with_body(self):
        import json
        b, p = context_fixture()
        _, schema, prompt = writer_call(b)
        data = json.loads(prompt.partition('\n')[2])
        self.assertEqual(data['writing_evidence_plan']['claim_policy'], 'ordinary_attributed_only')
        self.assertTrue(data['writing_evidence_plan']['body_required_per_source'])
        self.assertEqual(data['literal_evidence']['s0h0']['quote'], b['items'][0]['payload']['title'])
        self.assertNotIn(b['items'][0]['payload']['title'], json.dumps(schema))
        review_data = json.loads(reviewer_call(b, p)[2].partition('\n')[2])
        self.assertEqual(review_data['sources'][0]['title'], b['items'][0]['payload']['title'])
        self.assertTrue(review_data['sources'][0]['CONTENT'])

    def test_single_newsroom_recall_is_held_for_free(self):
        b, _ = context_fixture()
        b['items'][0]['payload']['title'] = 'Toyota recalls its electric passenger cars in China after a battery defect'
        rehash(b)
        checked = evidence_readiness(b, fixtures.NOW)
        self.assertIn('publisher_recall_needs_primary_or_two_editors', checked['errors'])

    def test_synthetic_context_still_needs_exact_independent_review_and_receipts(self):
        b, p = context_fixture()
        review = fixtures.accepted_review(b, p)
        review.update(reported_not_verified=True, international_scope_supported=True)
        # Freeze this synthetic scope; the Nov 1 fixture must not age with the host.
        with patch('news_publisher_articles.international_scope', return_value=True):
            self.assertEqual(check_review(b, p, review), [])
            with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'context.sqlite')) as store:
                row = stage(store, b, p, review, [], now=fixtures.NOW)
                self.assertEqual(row['status'], 'quarantined')
                with self.assertRaises(ValueError):
                    store.publish(row['id'], daily_limit=1)
            review['original_expression'] = False
            self.assertTrue(check_review(b, p, review))


class PublisherBodyBoundaryTests(unittest.TestCase):
    def test_declared_promotion_newsletter_and_related_blocks_are_not_article_evidence(self):
        url = fixtures.REPORT_URL
        narrative = 'This synthetic electric vehicle research report contains the actual narrative and its conditions. ' * 16
        excluded = ''.join('<div class="' + name + '"><a href="https://unrelated.example/story">'
                           'Unrelated Europe newsletter and recommended story.</a></div>'
                           for name in PUBLISHERS['carnewschina']['excluded_body_classes'])
        for root in ('<div class="article_detail__content">', '<article>'):
            html = ('<link rel="canonical" href="' + url + '">'
                    '<meta property="article:published_time" content="' + fixtures.NOW.isoformat() + '">'
                    '<meta property="og:title" content="Synthetic source boundaries">' + root +
                    '<p>' + narrative + '</p>' + excluded + ('</article>' if root == '<article>' else '</div>'))
            parsed = parse_publisher(html, url, 'carnewschina', now=fixtures.NOW)
            self.assertEqual(parsed['content'], narrative.strip())
            self.assertEqual(parsed['links'], [])

    def test_exclusion_configuration_is_bounded_and_cannot_hide_the_body_root(self):
        base = {'id': 'carnewschina', 'publisher_group': 'carnewschina',
                'ownership_evidence_url': 'https://carnewschina.com/about-us/',
                'body_class': 'article_detail__content'}
        for excluded in ('*', ['article_detail__content'], ['a'] * 13, ['a', 'a'], [7], ['div > p']):
            with self.subTest(excluded=excluded), self.assertRaisesRegex(ValueError, 'excluded_classes_invalid'):
                publisher_templates(templates=[{**base, 'excluded_body_classes': excluded}])
        self.assertEqual(publisher_templates(templates=[{**base, 'excluded_body_classes': ['newsletter']}])
                         ['carnewschina']['excluded_body_classes'], ['newsletter'])


class PrimaryEventContextTests(unittest.TestCase):
    def test_manufacturer_corporate_story_does_not_become_a_model_original_from_body_mentions(self):
        report = {'payload': {'title': 'Smart #2 electric car launches in China', 'content': 'Smart presents its city car.'}}
        title = 'Smart strengthens customer services with a new communications team'
        summary = 'Smart #2 launches in China. This background sentence is not the subject of the corporate announcement.'
        primary = {'payload': {'title': title, 'content': summary, 'publisher': 'smart Europe'}}
        self.assertFalse(primary_identity_matches(report, primary))
        self.assertFalse(candidate_related(report, title, summary, publisher='smart Europe'))

    def test_same_brand_and_model_do_not_override_different_country_or_event(self):
        report = {'payload': {'title': 'Smart #2 electric car launches in China', 'content': 'Smart presents the model in China.'}}
        for title in ('Smart #2 electric car premieres in Switzerland',
                      'Smart #2 electric car recall in China'):
            primary = {'payload': {'title': title, 'content': 'Smart #2 electric car information.', 'publisher': 'smart Europe'}}
            self.assertFalse(primary_identity_matches(report, primary))
            self.assertFalse(candidate_related(report, title, primary['payload']['content'], publisher='smart Europe'))

    def test_unrelated_old_document_is_not_a_date_conflict_but_actual_old_original_is(self):
        b, _ = context_fixture()
        lead = b['items'][0]
        original = copy.deepcopy(fixtures.fixture()[0]['items'][1])
        original['payload']['published_at'] = (fixtures.NOW - timedelta(days=40)).isoformat()
        for matching in (False, True):
            original['payload']['title'] = lead['payload']['title'].replace('China', 'China' if matching else 'Switzerland')
            with patch('news_publisher_sources.fetch_publisher', return_value=(lead, [original['url']])), \
                 patch('news_publisher_sources.fetch_primary', return_value=(original, [])), \
                 patch('news_publisher_sources.discover_originals', return_value=[]), \
                 patch('news_publisher_sources.corroboration_candidates', return_value=[]):
                if matching:
                    with self.assertRaises(OriginalSourceNotFound):
                        collect_bundle('carnewschina', lead['url'], None, now=fixtures.NOW)
                else:
                    result = collect_bundle('carnewschina', lead['url'], None, now=fixtures.NOW)
                    self.assertEqual(result['evidence_basis'], 'editorial_single_source')
                    self.assertIn('publisher_primary_subject_mismatch', ' '.join(result['support_fetch_errors']))


if __name__ == '__main__':
    unittest.main()
