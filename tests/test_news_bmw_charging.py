"""Synthetic charging-demo fixtures, not real vehicle specs or publication approval."""
import copy
import hashlib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_bmw_charging import (extract_charging, prepare_bmw_charging, review_private,
                              ChargingRejected, ChargingNotSupported, RECIPE, REVIEW)
from build_news_candidate_queue import build_queue
from news_short_articles import release
from news_notice_release import single_release_sql

NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
SOURCE = {'id': 'bmw-press', 'name': 'BMW Group PressClub', 'website': 'https://www.press.bmwgroup.com',
          'kind': 'primary', 'collection_method': 'pressroom_index'}
URL = SOURCE['website'] + '/global/article/detail/T0000001EN/synthetic-charging-test'
TEXT = ('Laguna Hills / USA. BMW Group, IONNA and Alpitronic join forces to demonstrate High-Power-Charging '
        'as a part of an International Media Event. '
        'Faster Charging for the iX3 50 xDrive means: up to 420 kW peak DC Charging Power '
        'and adding a range of up to 190 miles (305 km) in only 12 minutes (WLTP). '
        'Charging the 100 kWh battery pack (net) from 15 to 75 per cent takes just 24 minutes. '
        'The 420 kW experience is a technology demonstration and does not represent charging hardware '
        'commercially available in the U.S. today.')


def item(text=TEXT):
    return {'id': 'synthetic-bmw-item', 'source_id': SOURCE['id'], 'url': URL, 'status': 'ready',
        'payload': {'title': 'High-Power-Charging: up to 420 kW for the new BMW iX3 50 xDrive',
            'publisher': SOURCE['name'], 'source_kind': 'primary', 'access_status': 'accessible',
            'final_url': URL, 'content': text, 'content_hash': hashlib.sha256(text.encode()).hexdigest(),
            'published_at': NOW.isoformat(), 'fetched_at': NOW.isoformat()}}


class BmwChargingTests(unittest.TestCase):
    def test_peak_added_range_battery_and_charge_window_keep_distinct_scopes(self):
        packet = extract_charging(item(), SOURCE, NOW)
        c = packet['fields']['charging']['value']
        self.assertEqual(packet['subject'], 'BMW iX3 50 xDrive')
        self.assertEqual((c['current'], c['peak_kw'], c['power_basis'], c['power_limit']),
                         ('DC', '420', 'peak_not_average', 'up_to'))
        self.assertEqual((c['range_added_km'], c['range_added_minutes'], c['range_measurement']), ('305', '12', 'WLTP'))
        self.assertEqual(c['range_metric'], 'range_added_not_total_range')
        self.assertEqual((c['battery_kwh'], c['battery_basis']), ('100', 'net'))
        self.assertEqual((c['from_percent'], c['to_percent'], c['charge_minutes']), (15, 75, '24'))
        self.assertNotIn('total_range_km', c)
        self.assertNotIn('average_kw', c)

    def test_us_demonstration_and_noncommercial_hardware_qualification_are_mandatory(self):
        packet = extract_charging(item(), SOURCE, NOW)
        self.assertEqual(packet['fields']['location']['value']['country'], 'US')
        self.assertEqual(packet['fields']['event']['value']['evidence_basis'], 'manufacturer_report')
        status = packet['fields']['commercial_scope']['value']['status']
        self.assertIn('demonstration_not_commercially_available', status)
        for text in (TEXT.split('The 420 kW experience')[0], TEXT.replace('USA.', 'Sweden.'),
                     TEXT.replace('does not represent', 'represents')):
            with self.assertRaises(ChargingRejected):
                extract_charging(item(text), SOURCE, NOW)

    def test_each_fact_has_literal_offsets_and_exact_source_provenance(self):
        sample = item()
        packet = extract_charging(sample, SOURCE, NOW)
        for fact in packet['fields'].values():
            self.assertEqual(TEXT[fact['start']:fact['end']], fact['quote'])
        self.assertEqual(packet['source']['hash'], sample['payload']['content_hash'])
        self.assertEqual(packet['source']['published_at'], NOW.isoformat())
        self.assertFalse(packet['selection']['absence_claims_supported'])
        self.assertIn('canonical_vehicle_specs', packet['selection']['no_inference_for'])

    def test_model_headline_peak_or_demo_peak_conflicts_are_rejected(self):
        candidates = [item(TEXT.replace('iX3 50 xDrive', 'iX5 60 xDrive')),
                      item(TEXT.replace('up to 420 kW peak', 'up to 450 kW peak')),
                      item(TEXT.replace('The 420 kW experience', 'The 450 kW experience')),
                      item(TEXT + ' The same vehicle is charging with up to 440 kW.')]
        for sample in candidates:
            with self.assertRaises(ChargingRejected):
                extract_charging(sample, SOURCE, NOW)

    def test_vehicle_power_is_not_replaced_by_standalone_charger_rating(self):
        packet = extract_charging(item(TEXT + ' An unrelated charger has a 1000 kW nameplate rating.'), SOURCE, NOW)
        self.assertEqual(packet['fields']['charging']['value']['peak_kw'], '420')
        with self.assertRaises(ChargingRejected):
            extract_charging(item(TEXT + ' Another vehicle can charge at up to 600 kW.'), SOURCE, NOW)

    def test_conflicting_second_charging_block_is_not_silently_selected(self):
        block = TEXT[TEXT.index('Faster Charging'):TEXT.index('The 420 kW experience')]
        with self.assertRaises(ChargingRejected):
            extract_charging(item(TEXT + ' ' + block.replace('24 minutes', '18 minutes')), SOURCE, NOW)

    def test_numeric_limits_charge_windows_and_test_cycles_fail_closed(self):
        for before, after in [('420 kW peak', '900 kW peak'), ('100 kWh', '0 kWh'),
                              ('305 km', '1800 km'), ('12 minutes', '0 minutes'),
                              ('24 minutes', '-1 minutes'), ('15 to 75', '80 to 10'),
                              ('15 to 75', '10 to 110'), ('(WLTP)', '(CLTC)'), ('(net)', '(gross)')]:
            with self.subTest(change=after), self.assertRaises(ChargingRejected):
                extract_charging(item(TEXT.replace(before, after)), SOURCE, NOW)

    def test_wrong_publisher_domain_hash_date_access_or_redirect_is_rejected(self):
        mutations = [lambda i: i['payload'].update(content_hash='fake'),
                     lambda i: i['payload'].update(access_status='blocked'),
                     lambda i: i['payload'].update(publisher='Comparison site'),
                     lambda i: i['payload'].update(published_at=(NOW-timedelta(days=8)).isoformat()),
                     lambda i: i['payload'].update(fetched_at=(NOW-timedelta(days=2)).isoformat()),
                     lambda i: i['payload'].update(published_at=(NOW+timedelta(days=1)).isoformat()),
                     lambda i: i['payload'].update(final_url=URL + '/changed'),
                     lambda i: i.update(url='https://dealer.example/charging')]
        for mutate in mutations:
            sample = item(); mutate(sample)
            with self.assertRaises(ChargingRejected):
                extract_charging(sample, SOURCE, NOW)
        for config in [{**SOURCE, 'kind': 'publisher'}, {**SOURCE, 'website': 'https://dealer.example'}]:
            with self.assertRaises(ChargingRejected):
                extract_charging(item(), config, NOW)

    def test_noncharging_bmw_news_needs_its_own_adapter(self):
        sample = item()
        sample['payload']['title'] = 'BMW starts battery production'
        with self.assertRaises(ChargingNotSupported):
            extract_charging(sample, SOURCE, NOW)
        result = build_queue([sample], [SOURCE], [], NOW)
        self.assertEqual(result['items'][0]['status'], 'needs_adapter')

    def test_private_swedish_preview_preserves_scope_without_ai_or_publication(self):
        sample = item(); before = copy.deepcopy(sample)
        with patch('news_ai.NewsAi.__call__', side_effect=AssertionError('Paid calls forbidden')), \
                patch('news_store.NewsStore.put', side_effect=AssertionError('Staging forbidden')), \
                patch('news_store.NewsStore.publish', side_effect=AssertionError('Publishing forbidden')):
            packet, article, reviewed = prepare_bmw_charging(sample, SOURCE, NOW)
            queue = build_queue([sample], [SOURCE], [], NOW)
        self.assertEqual(sample, before)
        self.assertTrue(reviewed['passed'], reviewed)
        self.assertEqual(reviewed['method'], REVIEW)
        self.assertFalse(reviewed['ai_audit_performed'])
        self.assertEqual(article['status'], 'private_preview')
        self.assertEqual(article['editorial_recipe'], RECIPE)
        self.assertFalse(article['publication_supported'])
        self.assertIn('USA', article['title'])
        text = ' '.join(p['text'] for p in article['paragraphs'])
        self.assertIn('15 till 75', text)
        self.assertIn('24 minuter', text)
        self.assertIn('305 kilometers tillf\u00f6rd', text)
        self.assertIn('inte bilens totala', text)
        self.assertNotIn('Sverige', text)
        self.assertNotIn('kronor', text)
        self.assertEqual(queue['items'][0]['status'], 'private_candidate')
        self.assertFalse(queue['items'][0]['formats'][0]['publication_supported'])
        self.assertEqual((queue['paid_calls'], queue['published'], queue['production_writes']), (0, 0, 0))

    def test_modified_article_fields_facts_or_source_fail_separate_rule_review(self):
        sample = item()
        packet, article, _ = prepare_bmw_charging(sample, SOURCE, NOW)
        for mutate in [lambda a: a.update(title='BMW laddar i Sverige'),
                       lambda a: a.update(publication_supported=True),
                       lambda a: a['paragraphs'][0].update(text='Full laddning tar 24 minuter.'),
                       lambda a: a.update(paragraphs=['bad shape']),
                       lambda a: a.update(image='https://example.com/unlicensed.jpg')]:
            altered = copy.deepcopy(article); mutate(altered)
            self.assertFalse(review_private(altered, packet, sample, SOURCE, NOW)['passed'])
        forged = copy.deepcopy(packet)
        forged['fields']['charging']['value']['peak_kw'] = '600'
        self.assertFalse(review_private(article, forged, sample, SOURCE, NOW)['passed'])
        changed_source = item(TEXT.replace('305 km', '315 km'))
        self.assertFalse(review_private(article, packet, changed_source, SOURCE, NOW)['passed'])

    def test_conflicting_supported_source_is_quarantined_not_paid_fallback(self):
        queue = build_queue([item(TEXT.replace('The 420 kW experience', 'The 600 kW experience'))], [SOURCE], [], NOW)
        self.assertEqual(queue['items'][0]['status'], 'quarantined')
        self.assertEqual(queue['items'][0]['formats'], [])
        self.assertEqual(queue['paid_calls'], 0)

    def test_private_preview_is_rejected_by_both_existing_publishers(self):
        _, article, reviewed = prepare_bmw_charging(item(), SOURCE, NOW)
        store = Mock()
        store.get.return_value = {'status': 'draft', 'payload': article}
        with self.assertRaisesRegex(ValueError, 'validated_draft'):
            release(store, 'private-bmw', True, NOW)
        with self.assertRaisesRegex(ValueError, 'exact_passed_draft'):
            single_release_sql({'status': 'draft', 'payload': article}, reviewed, 0)
        store.publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
