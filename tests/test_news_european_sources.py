"""Synthetic source-layout and multilingual triage regressions, not live AI proofs."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_publisher_registry import PUBLISHERS, LEAD_SOURCES, publisher_templates
from news_publisher_sources import parse_publisher, publisher_url
from news_publisher_selection import candidate_assessment
from news_reporting_policy import independence
from news_engine import registry
from news_http import Collector
from news_store import stable_id

NOW = datetime(2026, 11, 2, 14, tzinfo=timezone.utc)
BEVOLT = 'https://www.bevolt.com/fr-fr/automobile/actualites/voitures-electriques/123-synthetic-electric-model/'
MOTOR = 'https://www.motor.no/bil/synthetic-electric-model/123456'
TEXT = ('Synthetic electric passenger vehicle article about a European model with documented test conditions. ' * 12)

def html(url, body, title='Synthetic electric vehicle news', date=NOW.isoformat()):
    return (f'<link rel="canonical" href="{url}"><meta property="og:title" content="{title}">'
            f'<meta property="article:published_time" content="{date}">'
            '<meta name="author" content="Synthetic reporter"><nav>UNRELATED NAVIGATION</nav>' + body)

class EuropeanSourceTests(unittest.TestCase):
    def test_verified_new_publishers_are_in_the_shared_production_templates(self):
        self.assertTrue({'bevolt', 'motor-no'} <= LEAD_SOURCES)
        self.assertEqual(PUBLISHERS['bevolt']['publisher_group'], 'brakson')
        self.assertEqual(PUBLISHERS['motor-no']['publisher_group'], 'naf')
        self.assertTrue(publisher_url('bevolt', BEVOLT))
        self.assertTrue(publisher_url('motor-no', MOTOR))
        for url in ['https://www.bevolt.com/fr-fr/a-propos/', BEVOLT.replace('/automobile/', '/energie/'),
                    BEVOLT + '?other=1']:
            self.assertFalse(publisher_url('bevolt', url))
        self.assertFalse(publisher_url('motor-no', MOTOR.replace('/bil/', '/reise/')))

    def test_attribute_template_excludes_related_articles_and_navigation(self):
        body = f'<article data-article-content>{TEXT}<article>UNRELATED TEASER</article></article><article>UNRELATED SIBLING</article>'
        parsed = parse_publisher(html(BEVOLT, body), BEVOLT, 'bevolt', now=NOW)
        self.assertEqual(parsed['content'], TEXT.strip())
        self.assertNotIn('UNRELATED', parsed['content'])

    def test_motor_body_class_excludes_the_many_teaser_articles(self):
        body = f'<article><section class="bodytext large-12">{TEXT}</section></article><article>UNRELATED SIBLING</article>'
        parsed = parse_publisher(html(MOTOR, body), MOTOR, 'motor-no', now=NOW)
        self.assertEqual(parsed['content'], TEXT.strip())
        self.assertEqual(parsed['byline'], 'Synthetic reporter')

    def test_ambiguous_bodies_dates_and_paywalls_still_hold(self):
        body = f'<article data-article-content>{TEXT}</article>'
        cases = [(html(BEVOLT, body + body), 'ambiguous'),
                 (html(BEVOLT, body) + '<meta itemprop="isAccessibleForFree" content="false">', 'paywall'),
                 (html(BEVOLT, body).replace('2026-11-02', '2025-11-02'), 'stale_report')]
        for page, reason in cases:
            with self.assertRaisesRegex(ValueError, reason): parse_publisher(page, BEVOLT, 'bevolt', now=NOW)
        with self.assertRaisesRegex(ValueError, 'feed_date_conflict'):
            parse_publisher(html(MOTOR, f'<div class="bodytext">{TEXT}</div>'), MOTOR, 'motor-no',
                            feed_date='2026-10-30T14:23:25Z', now=NOW)

    def test_rebranding_is_not_a_second_independent_publisher(self):
        with patch.dict('os.environ', {'NEWS_SOURCE_PROFILE': 'broad'}):
            sources = {s['id']: s for s in registry()}
        self.assertEqual(sources['automobile-propre']['publisher_group'], PUBLISHERS['bevolt']['publisher_group'])
        self.assertFalse(sources['automobile-propre']['enabled'])
        sources_for_test = deepcopy(PUBLISHERS)
        sources_for_test['old-bevolt'] = {**PUBLISHERS['bevolt'], 'id':'old-bevolt'}
        def item(source_id, url):
            return {'id':stable_id(url), 'url':url, 'source_id':source_id, 'payload':{
                'title':'Synthetic European battery project', 'published_at':NOW.isoformat(),
                'content':TEXT, 'publisher_group':'brakson'}}
        with patch('news_reporting_policy.PUBLISHERS', sources_for_test):
            self.assertIn('editorial_common_owner_or_same_article', independence(
                item('bevolt', BEVOLT), item('old-bevolt', BEVOLT + 'old/'))['errors'])

    def test_discovery_only_source_cannot_become_an_ai_template(self):
        source = {'id':'reserved', 'kind':'publisher', 'website':'https://reserved.example',
                  'editorial_use':'discovery_only'}
        template = {'id':'reserved', 'publisher_group':'reserved', 'ownership_evidence_url':'https://reserved.example/about/'}
        with self.assertRaisesRegex(ValueError, 'editorial_use_not_approved'):
            publisher_templates([source], [template])
        self.assertTrue({'electrive','electrek','cnevpost'}.isdisjoint(PUBLISHERS))

    def test_invalid_selector_attributes_do_not_broaden_capture(self):
        source = {'id':'synthetic', 'kind':'publisher', 'website':'https://source.example'}
        for attribute in ['class', 'id', '*', 'data-article-content onclick']:
            with self.assertRaisesRegex(ValueError, 'body_attribute_invalid'):
                publisher_templates([source], [{'id':'synthetic','publisher_group':'synthetic',
                    'ownership_evidence_url':'https://source.example/about/','body_attribute':attribute}])

    def test_shared_reporting_from_a_discovery_only_publisher_is_not_independence(self):
        from test_news_reported_articles import reported_fixture
        bundle, _, _ = reported_fixture()
        for item in bundle['items']:
            item['payload']['editorial_links'] = ['https://cnevpost.com/2026/11/02/synthetic-source/']
        self.assertIn('editorial_shared_upstream_or_wire', independence(*bundle['items'])['errors'])

    def test_norwegian_and_french_ev_news_can_enter_triage_without_inventing_sweden(self):
        for title in ['Ny elbil lanseres i Norge med bedre rekkevidde',
                      'Une nouvelle voiture electrique arrive en Europe',
                      'Essai du nouveau vehicule electrique en France']:
            result = candidate_assessment({'title':title,'published_at':NOW.isoformat()}, NOW)
            self.assertTrue(result['eligible'], (title,result))
            self.assertEqual(result['reason'], 'european_scope')

    def test_french_and_norwegian_prices_hybrids_and_rumours_are_not_ai_articles(self):
        for title in ['Le prix de la voiture electrique baisse en Europe',
                      'Elbil priser i Norge', 'Ny pris pa elbil i Norge', 'Une voiture electrique pourrait arriver en Europe',
                      'Nouvelle voiture hybride rechargeable en France', 'Ny ladbar hybrid i Norge']:
            self.assertFalse(candidate_assessment({'title':title,'published_at':NOW.isoformat()}, NOW)['eligible'], title)

    def test_production_collector_still_stops_reserved_articles_before_network(self):
        from urllib.robotparser import RobotFileParser
        rules = RobotFileParser(); rules.parse(['User-agent: GPTBot','Disallow: /','User-agent: *','Allow: /'])
        collector = Collector()
        with patch.object(collector, 'policy', return_value=rules), patch.object(collector, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'ai_mining_robots_reserved'):
                collector.fetch(BEVOLT, {'website':'https://www.bevolt.com'}, editorial=True)
        request.assert_not_called()

if __name__ == '__main__':
    unittest.main()
