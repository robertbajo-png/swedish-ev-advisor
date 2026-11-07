"""Positive/negative synthetic selection cases, not live editorial approvals."""
import hashlib
from datetime import timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_coverage import coverage_scope
from news_primary_discovery import candidate_related
from news_publisher_selection import (candidate_assessment, literal_spans,
    passage_selection, primary_identity_matches)
from news_reporting_policy import same_event, independence
from news_publisher_articles import evidence_catalog, evidence_readiness, precheck, writer_call
from news_store import artifact_hash
import test_news_publisher_articles as fixtures
import test_news_reported_articles as reported_fixtures

NOW = fixtures.NOW


def item(title, content=''):
    return {'payload': {'title': title, 'content': content, 'published_at': NOW.isoformat()}}


def rehash(bundle):
    for row in bundle['items']:
        p = row['payload']
        p['content_hash'] = hashlib.sha256(p['content'].encode()).hexdigest()
    bundle['bundle_hash'] = artifact_hash({k: v for k, v in bundle.items() if k != 'bundle_hash'})


class SubjectSelectionTests(unittest.TestCase):
    def test_confirmed_launch_is_not_rejected_for_a_background_potential(self):
        row = item('BMW i3 electric car launches in Europe',
                   'Orders open in Europe this month. The company sees potential for future improvements.')
        self.assertTrue(candidate_assessment(row, NOW)['eligible'])
        for title, body in [
            ('BMW i3 electric car could launch in Europe', 'An unconfirmed report.'),
            ('Potential BMW i3 electric car launch in Europe', 'Orders could open later.'),
            ('BMW electric car plans for Europe', 'Rumours suggest a future launch.'),
            ('BMW electric car spotted in Europe', 'The prototype has not been announced.'),
        ]:
            self.assertEqual(candidate_assessment(item(title, body), NOW)['reason'],
                             'speculation_or_minor_sighting', title)

    def test_launch_with_incidental_price_can_be_read_but_price_stories_stay_held(self):
        for title in ('BMW i3 electric car launches in Switzerland from CHF 74,600',
                      'BMW unveils electric i3 in Europe, priced from EUR 50,000'):
            self.assertTrue(candidate_assessment(item(title, 'The BMW i3 is a battery-electric passenger car.'), NOW)['eligible'], title)
        for title in ('Tesla cuts EV prices in Sweden', 'BMW reveals new prices for electric cars in Europe',
                      'BMW launches electric car discount in Germany', 'BMW EV leasing offer in Europe',
                      'BMW i3 update with lower prices in Germany', 'BMW EV gets Australian price tag'):
            self.assertFalse(candidate_assessment(item(title), NOW)['eligible'], title)

    def test_european_network_development_does_not_require_fake_swedish_availability(self):
        for title in ('European rapid charging network expands to 800 stations',
                      'New partnership adds electric vehicle charging points across Europe'):
            row = item(title, 'The network provides rapid charging for electric passenger cars in Europe.')
            self.assertTrue(candidate_assessment(row, NOW)['eligible'])
            self.assertEqual(coverage_scope({'items': [row]}, NOW), 'european_development', title)
        for title in ('Electric car charging network bond issue in Europe',
                      'Electric car charging network award in Europe',
                      'Electric car charging network earnings in Europe'):
            self.assertEqual(coverage_scope({'items': [item(title)]}, NOW), 'regional', title)
        self.assertFalse(candidate_assessment(item('Electric car charging station opens in Australia'), NOW)['eligible'])

    def test_selection_still_requires_actual_ev_connection_and_freshness(self):
        row = item('European charging network expands to 800 stations')
        self.assertFalse(candidate_assessment(row, NOW)['eligible'])
        row = item('BMW electric car launches in Europe', 'Potential later changes are background only.')
        row['payload']['published_at'] = (NOW - timedelta(days=8)).isoformat()
        self.assertFalse(candidate_assessment(row, NOW)['eligible'])


class MultilingualEventTests(unittest.TestCase):
    LEFT = 'Volkswagen announces battery preheating rollout across older electric SUVs'
    RIGHT = 'Volkswagen active enfin le prechauffage des batteries sur ses anciens SUV electriques'

    def test_specific_cross_language_update_matches_without_translating_source_text(self):
        left, right = item(self.LEFT), item(self.RIGHT)
        self.assertTrue(same_event(left, right))
        self.assertTrue(primary_identity_matches(left, right))
        left['payload']['content'] = ''
        self.assertTrue(candidate_related(left, self.RIGHT))

    def test_cross_language_launch_needs_exact_model_and_market(self):
        self.assertTrue(same_event(item('BMW i3 electric car launches in Europe'),
                                   item('BMW i3 voiture electrique presentee en Europe')))
        for title in ('BMW iX3 voiture electrique presentee en Europe',
                      'BMW i3 voiture electrique rappelee en Europe',
                      'BMW i3 voiture electrique presentee en Chine'):
            self.assertFalse(same_event(item('BMW i3 electric car launches in Germany'), item(title)), title)
        self.assertFalse(same_event(item('smart #2 electric car launches in Europe'),
                                    item('smart #5 electric car launches in Europe')))

    def test_brand_or_generic_charging_topic_alone_is_not_an_event(self):
        for title in ('Volkswagen unveils new battery technology in Europe',
                      'Volkswagen updates charging software in Europe',
                      'BMW active le prechauffage des batteries sur ses anciens SUV electriques',
                      'Volkswagen lance des batteries solides en Europe'):
            self.assertFalse(same_event(item(self.LEFT), item(title)), title)
        self.assertFalse(same_event(item('Volkswagen ID.7 update in Europe'),
                                    item('Volkswagen ID.4 update in Europe')))
        self.assertFalse(same_event(item('BMW i3 V2G charging update in Europe'),
                                    item('BMW iX3 V2G charging update in Europe')))
        self.assertFalse(same_event(item('BMW i3 preheating rollout across older electric cars'),
                                    item('BMW active le prechauffage des batteries sur ses anciens SUV electriques')))
        self.assertFalse(same_event(item('BMW i3 V2G charging update in Europe'),
                                    item('BMW i3 battery preheating update in Europe')))

    def test_different_statistics_periods_are_not_corroboration(self):
        self.assertFalse(same_event(item('Volkswagen EV registrations October 2026'),
                                    item('Volkswagen EV registrations September 2026')))

    def test_cross_language_match_does_not_relax_independence_or_dates(self):
        bundle, _, _ = reported_fixtures.reported_fixture()
        left, right = bundle['items']
        left['payload']['title'], right['payload']['title'] = self.LEFT, self.RIGHT
        self.assertTrue(independence(left, right)['passed'])
        right['payload']['editorial_links'] = [left['url']]
        self.assertIn('editorial_circular_citation', independence(left, right)['errors'])
        right['payload']['published_at'] = (NOW - timedelta(days=4)).isoformat()
        self.assertFalse(same_event(left, right))


class StructuredEvidenceTests(unittest.TestCase):
    HEADER = 'BMW i3 RWD for Europe, preliminary technical specifications:'
    FIELDS = ['Battery capacity: 84 kWh.', 'DC peak: 350 kW.',
              'Range: up to 650 km WLTP.', 'Ordering opens: 1 November 2026.']

    def test_short_fields_keep_exact_model_variant_and_qualifying_header(self):
        text = self.HEADER + '\n' + '\n'.join(self.FIELDS)
        quotes = [text[a:b] for a, b in literal_spans(text)]
        contextual = [q for q in quotes if q.startswith(self.HEADER)]
        self.assertEqual(len(contextual), 4)
        self.assertTrue(all(8 <= len(q.split()) <= 45 and len(q) <= 350 for q in contextual))
        for field in self.FIELDS:
            self.assertTrue(any(field in q for q in contextual))
        selected = passage_selection(text, 'BMW i3 RWD electric car in Europe', 'BMW i3', 2400, primary=True)
        for a, b in selected['passage_offsets']:
            self.assertIn(text[a:b], selected['CONTENT'])

    def test_qualification_and_following_fields_stay_in_the_same_literal_window(self):
        caveat = 'Preliminary values depend on optional equipment.'
        text = self.HEADER + '\n' + self.FIELDS[0] + '\n' + caveat + '\n' + '\n'.join(self.FIELDS[1:])
        quotes = [text[a:b] for a, b in literal_spans(text) if text[a:b].startswith(self.HEADER)]
        self.assertEqual(len(quotes), 4)
        self.assertTrue(all(caveat in q for q in quotes))

    def test_real_html_text_shape_retains_model_bound_fields_without_inventing_newlines(self):
        from news_pressrooms import document
        html = '<div id="article-text"><h2>' + self.HEADER + '</h2><ul>' + ''.join(
            '<li>' + value + '</li>' for value in self.FIELDS) + '</ul></div>'
        text = document(html, exclude_tables=True)['body']
        self.assertNotIn('\n', text)
        quotes = [text[a:b] for a, b in literal_spans(text) if text[a:b].startswith(self.HEADER)]
        self.assertEqual(len(quotes), 4)
        self.assertTrue(any(self.FIELDS[-1] in quote for quote in quotes))

    def test_orphan_fields_unknown_headers_and_next_models_are_not_combined(self):
        orphan = '\n'.join(self.FIELDS)
        for text in (orphan, 'Technical specifications:\n' + orphan):
            self.assertEqual(list(literal_spans(text)), [])
        text = self.HEADER + '\n' + self.FIELDS[0] + '\n\nBMW iX3 AWD:\nDC peak: 400 kW.'
        quotes = [text[a:b] for a, b in literal_spans(text)]
        self.assertFalse(any('i3 RWD' in q and '400 kW' in q for q in quotes))
        flat = self.HEADER + ' ' + self.FIELDS[0] + ' BMW iX3 AWD from 2026: DC peak: 400 kW.'
        quotes = [flat[a:b] for a, b in literal_spans(flat)]
        self.assertFalse(any('i3 RWD' in q and '400 kW' in q for q in quotes))

    def test_contextual_fields_enter_catalog_but_tables_and_missing_facts_remain_held(self):
        bundle, packet = fixtures.fixture()
        bundle['items'][0]['payload']['title'] = 'BMW i3 RWD electric car launches in Europe from EUR 50,000'
        primary = bundle['items'][1]['payload']
        primary['title'] = 'BMW i3 RWD electric car launches in Europe'
        primary['content'] = self.HEADER + '\n' + '\n'.join(self.FIELDS)
        rehash(bundle)
        self.assertTrue(evidence_readiness(bundle, NOW)['ready'])
        self.assertTrue(any(ref['quote'].startswith(self.HEADER) for ref in evidence_catalog(bundle).values()))
        self.assertIn('omit prices', writer_call(bundle)[2].lower())
        primary['unvalidated_table_context'] = True
        rehash(bundle)
        self.assertIn('publisher_table_context_requires_validation', evidence_readiness(bundle, NOW)['errors'])
        primary.pop('unvalidated_table_context')
        primary['content'] = '\n'.join(self.FIELDS)
        rehash(bundle)
        self.assertIn('publisher_insufficient_literal_fact_material', evidence_readiness(bundle, NOW)['errors'])

    def test_incidental_price_never_becomes_an_ai_price_fact(self):
        for price in ('50000 EUR', 'CHF 74\u2019600', '$50000', '50000 \u20ac'):
            bundle, packet = fixtures.fixture()
            packet['extraction']['facts'][0]['statement'] += ' ' + price + '.'
            self.assertIn('publisher_price_fact_requires_notice:f1', precheck(bundle, packet, NOW)['errors'])
        bundle, packet = fixtures.fixture()
        packet['extraction']['facts'][0]['statement'] += ' 50000 EUR.'
        packet['extraction']['facts'][0]['statement'] = packet['extraction']['facts'][0]['statement'].replace('50000 EUR', '999 kWh')
        self.assertTrue(any('number_not_in_evidence' in e for e in precheck(bundle, packet, NOW)['errors']))
        packet['extraction']['facts'][0]['statement'] += ' Euro NCAP har gett bilen 5 stjarnor.'
        self.assertNotIn('publisher_price_fact_requires_notice:f1', precheck(bundle, packet, NOW)['errors'])


if __name__ == '__main__':
    unittest.main()
