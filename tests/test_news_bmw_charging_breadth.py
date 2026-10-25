"""Synthetic format regressions. Real historical sources remain private captures."""
import copy
import hashlib
import json
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_bmw_charging_breadth import MANIFEST, assess, run_cases, validate_cases
from news_bmw_charging import charging_layout, extract_charging, ChargingRejected
from test_news_bmw_charging import NOW, SOURCE, TEXT, item


FORMATS = [
    ('china_cltc_vehicle_specs', 'BMW iX3 long wheelbase', 'Range is measured in CLTC. DC charging is specified separately.'),
    ('v2g_offer', 'BMW and E.ON energy market offer', 'A tariff and a conditional bonus for Germany. Vehicle-to-grid operation.'),
    ('ac_option_update', 'BMW model updates', 'AC Charging Professional is available as an option. A 22 kW AC rating.'),
    ('provisional_vehicle_charging', 'The new BMW iX3 M60 xDrive', 'DC charging up to 400 kW. All figures are provisional. AC Charging Professional is standard. An optional M Sport package.'),
    ('charging_network', 'Holiday travel with BMW electric vehicles', 'BMW Charging network access and regional tariffs. No vehicle rating.'),
    ('vehicle_charging_specs', 'BMW electric vehicle', 'Maximum charging rate: 400 kW. Optional wheels. AC Charging Professional is standard.'),
    ('other_bmw_release', 'BMW starts production', 'A factory starts assembly of electric vehicles.'),
]


def html(title, text, published=None):
    published = NOW.isoformat() if published is None else published
    return (f'<html><head><meta property="og:title" content="{title}">'
            f'<meta property="article:published_time" content="{published}"></head>'
            f'<body><div id="article-text">{text}</div></body></html>')


def cases():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


class BmwChargingBreadthTests(unittest.TestCase):
    def test_six_distinct_official_global_article_ids_in_bounded_manifest(self):
        samples = cases()
        validate_cases(samples)
        self.assertEqual(len(samples), 6)
        self.assertEqual(len({c['expected_layout'] for c in samples}), 6)

    def test_different_charging_scopes_are_only_classification_hints(self):
        for expected, title, body in FORMATS:
            with self.subTest(layout=expected):
                self.assertEqual(charging_layout(title, body), expected)
                sample = item(body)
                sample['payload']['title'] = title
                result = assess(sample, SOURCE, NOW)
                self.assertEqual(result['status'], 'needs_adapter')
                self.assertNotIn('packet', result)
                self.assertNotIn('article', result)
                self.assertFalse(result['publication_supported'])

    def test_unrelated_optional_equipment_does_not_turn_standard_ac_into_option(self):
        text = 'Standard AC Charging Professional at 22 kW. The optional Sport package is available.'
        self.assertEqual(charging_layout('BMW electric vehicle', text), 'other_bmw_release')
        self.assertEqual(charging_layout('BMW updates', 'Optional AC Charging Professional at 22 kW.'), 'ac_option_update')

    def test_provisional_footnote_takes_precedence_over_other_option_mentions(self):
        text = ('AC Charging Professional is available as an option. DC charging up to 400 kW. '
                'All figures are provisional. No binding WLTP values are currently available.')
        self.assertEqual(charging_layout('The new BMW iX3', text), 'provisional_vehicle_charging')

    def test_demo_with_unparsed_conditions_is_quarantined_without_qualified_claims(self):
        for condition in ['All figures are provisional.', 'Preliminary figures.',
                          'The battery must be preconditioned.', 'Pre-conditioning is required.',
                          'Figures depend on battery temperature.', 'Ambient temperatures affect charging.',
                          'Only under optimal conditions.', 'Subject to homologation.']:
            with self.subTest(condition=condition):
                sample = item(TEXT + ' ' + condition)
                with self.assertRaisesRegex(ChargingRejected, 'unparsed_test_conditions'):
                    extract_charging(sample, SOURCE, NOW)
                self.assertEqual(assess(sample, SOURCE, NOW)['status'], 'quarantined')

    def test_historical_publication_is_never_replaced_by_fresh_fetch_date(self):
        for published in ['2025-09-10T09:00:00+00:00', '2026-01-21T19:00:00+00:00',
                          (NOW-timedelta(days=8)).isoformat()]:
            with self.subTest(published=published):
                sample = item()
                sample['payload']['published_at'] = published
                before = copy.deepcopy(sample)
                result = assess(sample, SOURCE, NOW)
                self.assertEqual(result['status'], 'held_stale')
                self.assertNotIn('article', result)
                self.assertEqual(result['published_at'], published)
                self.assertEqual(result['fetched_at'], NOW.isoformat())
                self.assertEqual(sample, before)

    def test_source_integrity_and_fetch_age_errors_are_not_hidden_by_old_publication(self):
        for mutate in [lambda p: p.update(content_hash='invalid'),
                       lambda p: p.update(access_status='blocked'),
                       lambda p: p.update(fetched_at=(NOW-timedelta(days=2)).isoformat()),
                       lambda p: p.update(final_url='https://example.com/redirect')]:
            sample = item()
            sample['payload']['published_at'] = '2025-09-10T09:00:00+00:00'
            mutate(sample['payload'])
            self.assertEqual(assess(sample, SOURCE, NOW)['status'], 'quarantined')

    def test_duplicate_article_under_different_slug_or_id_is_rejected(self):
        original = cases()[0]
        for duplicate in [dict(original), {**original, 'id': 'same-article-different-name',
                                          'url': original['url'].rsplit('/', 1)[0] + '/other-slug'}]:
            with self.assertRaisesRegex(ValueError, 'duplicate_case_or_article'):
                validate_cases([original, duplicate])

    def test_limits_domains_queries_fragments_and_regional_reprints_fail_before_fetch(self):
        originals = cases()
        invalid = [[], originals + [originals[0]], ['bad-shape']]
        for url in ['http://www.press.bmwgroup.com/global/article/detail/T0001EN/test',
                    'https://www.press.bmwgroup.com.evil.example/global/article/detail/T0001EN/test',
                    'https://127.0.0.1/global/article/detail/T0001EN/test',
                    originals[0]['url'] + '?language=en', originals[0]['url'] + '#anchor',
                    originals[0]['url'].replace('/global/', '/usa/'),
                    originals[0]['url'].replace('https://', 'https://user:secret@')]:
            invalid.append([{**originals[0], 'url': url}])
        for config in invalid:
            collector = Mock()
            with self.subTest(config=config), self.assertRaises(ValueError):
                run_cases(config, SOURCE, collector, lambda: NOW)
            collector.fetch.assert_not_called()

    def test_blocked_source_does_not_stop_remaining_free_checks(self):
        selected = cases()[:2]
        collector = Mock()
        collector.fetch.side_effect = [ValueError('tdm_reserved'),
            (200, {}, html(item()['payload']['title'], TEXT), selected[1]['url'])]
        report = run_cases(selected, SOURCE, collector, lambda: NOW)
        self.assertEqual(report['counts'], {'source_unavailable': 1, 'private_preview': 1})
        self.assertEqual(report['accessible_source_count'], 1)
        self.assertEqual(report['cases'][0]['reasons'], ['tdm_reserved'])
        self.assertEqual(collector.fetch.call_count, 2)
        self.assertTrue(all(call.kwargs == {'editorial': True} for call in collector.fetch.call_args_list))

    def test_original_document_and_hash_remain_bound_without_remote_ai_or_store(self):
        selected = cases()[:1]
        title = item()['payload']['title']
        collector = Mock()
        collector.fetch.return_value = (200, {}, html(title, TEXT), selected[0]['url'])
        with patch.dict(os.environ, {'NEWS_BACKEND': 'supabase'}), \
                patch('news_ai.NewsAi.__call__', side_effect=AssertionError('No paid calls')), \
                patch('news_store.NewsStore.put', side_effect=AssertionError('No staging')), \
                patch('news_store.NewsStore.publish', side_effect=AssertionError('No publishing')), \
                patch('supabase_client.SupabaseRestClient._request', side_effect=AssertionError('No remote database')):
            report = run_cases(selected, SOURCE, collector, lambda: NOW)
        row = report['cases'][0]
        self.assertEqual(row['status'], 'private_preview')
        self.assertTrue(row['review']['passed'])
        self.assertFalse(row['review']['ai_audit_performed'])
        self.assertFalse(row['review']['publication_supported'])
        self.assertEqual(row['item']['payload']['content_hash'], hashlib.sha256(TEXT.encode()).hexdigest())
        self.assertEqual(row['published_at'], NOW.isoformat())
        self.assertEqual((report['paid_calls'], report['cost_usd'], report['production_writes'], report['published']), (0, 0, 0, 0))

    def test_missing_or_future_publication_and_redirects_are_not_readiness_passes(self):
        selected = cases()[:1]
        for status, page, final in [(200, html('BMW charging', TEXT, 'invalid'), selected[0]['url']),
                                    (200, html('BMW charging', TEXT, (NOW+timedelta(days=2)).isoformat()), selected[0]['url']),
                                    (200, html('BMW charging', TEXT), selected[0]['url'] + '-changed'),
                                    (403, '', selected[0]['url'])]:
            collector = Mock()
            collector.fetch.return_value = status, {}, page, final
            report = run_cases(selected, SOURCE, collector, lambda: NOW)
            self.assertEqual(report['counts'], {'source_unavailable': 1})
            self.assertEqual(report['accessible_source_count'], 0)

    def test_stored_fetch_timestamp_is_not_renewed_on_offline_replay(self):
        sample = item()
        first = assess(sample, SOURCE, NOW)
        later = assess(sample, SOURCE, NOW+timedelta(days=2))
        self.assertEqual(first['status'], 'private_preview')
        self.assertEqual(later['status'], 'quarantined')
        self.assertEqual(later['fetched_at'], first['fetched_at'])
        self.assertEqual(later['content_hash'], first['content_hash'])


if __name__ == '__main__':
    unittest.main()
