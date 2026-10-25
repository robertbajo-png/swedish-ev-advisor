"""Synthetic AC-option fixtures; not real specifications, AI proofs or releases."""
import copy
import hashlib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_bmw_ac_option import (RECIPE, REVIEW, extract_ac_option, parse_ac_option,
                                prepare_ac_option, review_ac_private)
from news_bmw_charging import ChargingRejected, ChargingNotSupported, prepare_bmw_charging
from build_news_candidate_queue import build_queue
from news_notice_release import single_release_sql
from news_short_articles import release
from test_news_bmw_charging import SOURCE, URL

NOW = datetime(2026, 10, 25, 10, tzinfo=timezone.utc)
BLOCK = ('The BMW iX3 (BMW iX3 50 xDrive: energy consumption 18.0 kWh/100 km (WLTP); '
         'electric range: 600 km (WLTP)) will in future offer the AC charging Professional option. '
         'This supports AC charging at up to 22 kW and also includes the Vehicle-to-Load function. '
         'The vehicle can then be used as a mobile power bank and supply external electrical '
         'devices with up to 3.7 kW of power.')
MARKET = ('All descriptions of model variants, equipment, technical data, consumption and emission '
          'values are for vehicles as offered on the German market.')
PRELIMINARY = 'All technical data are preliminary.'
TEXT = 'Munich. BMW iX1 has a different range. ' + BLOCK + ' ' + MARKET + ' ' + PRELIMINARY


def item(text=TEXT):
    return {'id': 'synthetic-bmw-ac-option', 'source_id': SOURCE['id'], 'url': URL,
        'status': 'ready', 'payload': {'title': 'BMW model updates, spring 2026.',
            'publisher': SOURCE['name'], 'source_kind': 'primary', 'final_url': URL,
            'published_at': NOW.isoformat(), 'fetched_at': NOW.isoformat(),
            'content': text, 'content_hash': hashlib.sha256(text.encode()).hexdigest(),
            'access_status': 'accessible'}}


class BmwAcOptionTests(unittest.TestCase):
    def test_ac_input_v2l_output_future_option_market_and_provisional_status_are_separate(self):
        packet = extract_ac_option(item(), SOURCE, NOW)
        ac = packet['fields']['ac_option']['value']
        self.assertEqual(packet['subject'], 'BMW iX3 50 xDrive')
        self.assertEqual((ac['current'], ac['max_kw'], ac['power_limit']), ('AC', '22', 'up_to'))
        self.assertEqual((ac['v2l_max_kw'], ac['v2l_direction']),
                         ('3.7', 'vehicle_to_external_devices_not_battery_charging'))
        self.assertEqual(ac['equipment_status'], 'announced_future_option')
        self.assertEqual(packet['fields']['market']['value'], {'country': 'DE'})
        self.assertEqual(packet['fields']['qualification']['value'], {'technical_data_status': 'preliminary'})
        self.assertFalse(packet['selection']['absence_claims_supported'])
        self.assertIn('Swedish_availability', packet['selection']['no_inference_for'])
        self.assertNotIn('dc_kw', ac)
        self.assertNotIn('price', ac)

    def test_exact_variant_and_values_are_not_hardcoded(self):
        sample = item(TEXT.replace('iX3', 'iX5').replace('50 xDrive', '60 xDrive')
                      .replace('22 kW', '11 kW').replace('3.7 kW', '2.3 kW'))
        packet, article, reviewed = prepare_ac_option(sample, SOURCE, NOW)
        self.assertEqual(packet['subject'], 'BMW iX5 60 xDrive')
        self.assertEqual(packet['fields']['ac_option']['value']['max_kw'], '11')
        self.assertIn('11 kW', article['paragraphs'][0]['text'])
        self.assertIn('2,3 kW', article['paragraphs'][1]['text'])
        self.assertTrue(reviewed['passed'], reviewed)

    def test_each_fact_has_literal_offsets_and_original_source_hash_and_date(self):
        sample = item()
        packet = extract_ac_option(sample, SOURCE, NOW)
        for fact in packet['fields'].values():
            self.assertEqual(TEXT[fact['start']:fact['end']], fact['quote'])
        self.assertEqual(packet['source']['hash'], sample['payload']['content_hash'])
        self.assertEqual(packet['source']['published_at'], NOW.isoformat())

    def test_market_and_preliminary_qualification_are_required_not_guessed(self):
        for text in [TEXT.replace(MARKET, ''), TEXT.replace('German market', 'Swedish market'),
                     TEXT.replace(PRELIMINARY, ''), TEXT.replace('are preliminary', 'are final')]:
            with self.subTest(text=text), self.assertRaises(ChargingRejected):
                extract_ac_option(item(text), SOURCE, NOW)

    def test_other_model_ranges_in_mixed_updates_are_not_extracted(self):
        text = TEXT + ' A plug-in hybrid has a 450 kW engine and 85 km range. Another car charges at 400 kW DC.'
        packet = extract_ac_option(item(text), SOURCE, NOW)
        ac = packet['fields']['ac_option']['value']
        self.assertEqual((ac['max_kw'], ac['v2l_max_kw']), ('22', '3.7'))
        self.assertNotIn('range_km', ac)
        self.assertNotIn('engine_kw', ac)

    def test_conflicting_variant_block_rating_or_standard_equipment_is_rejected(self):
        for text in [TEXT.replace('The BMW iX3 (BMW iX3', 'The BMW iX5 (BMW iX3'),
                     TEXT + ' ' + BLOCK.replace('22 kW', '11 kW'),
                     TEXT + ' AC charging at up to 11 kW.',
                     TEXT + ' AC Charging Professional is standard equipment.',
                     TEXT + ' Standard equipment includes AC Charging Professional.']:
            with self.subTest(text=text), self.assertRaises(ChargingRejected):
                extract_ac_option(item(text), SOURCE, NOW)

    def test_numeric_limits_units_and_current_type_are_not_coerced(self):
        for before, after in [('22 kW', '0 kW'), ('22 kW', '100 kW'),
                              ('3.7 kW', '-1 kW'), ('3.7 kW', '50 kW'),
                              ('22 kW', '22 kWh'), ('3.7 kW', '3.7 kWh'),
                              ('supports AC charging', 'supports DC charging')]:
            with self.subTest(change=after), self.assertRaises(ChargingRejected):
                extract_ac_option(item(TEXT.replace(before, after)), SOURCE, NOW)

    def test_additional_unparsed_test_conditions_are_held(self):
        for clause in ['Battery temperature affects the figure.', 'Pre-conditioning is required.',
                       'Figures apply under optimal conditions.', 'Subject to homologation.']:
            with self.subTest(clause=clause), self.assertRaisesRegex(ChargingRejected, 'unparsed_conditions'):
                extract_ac_option(item(TEXT + ' ' + clause), SOURCE, NOW)

    def test_old_source_cannot_produce_preview_even_if_text_shape_is_recognized(self):
        sample = item()
        sample['payload']['published_at'] = '2026-01-28T07:00:00+00:00'
        self.assertIn('ac_option', parse_ac_option(TEXT))
        with self.assertRaisesRegex(ChargingRejected, 'stale_report'):
            prepare_ac_option(sample, SOURCE, NOW)
        queued = build_queue([sample], [SOURCE], [], NOW)
        self.assertEqual(queued['items'][0]['status'], 'quarantined')
        self.assertEqual(queued['items'][0]['formats'], [])

    def test_wrong_hash_identity_url_or_fetch_age_is_rejected(self):
        for mutate in [lambda i: i['payload'].update(content_hash='changed'),
                       lambda i: i['payload'].update(publisher='Dealer'),
                       lambda i: i['payload'].update(fetched_at=(NOW-timedelta(days=2)).isoformat()),
                       lambda i: i['payload'].update(access_status='blocked'),
                       lambda i: i.update(url='https://example.com/car')]:
            sample = item(); mutate(sample)
            with self.assertRaises(ChargingRejected):
                prepare_ac_option(sample, SOURCE, NOW)

    def test_unknown_layout_does_not_borrow_a_supported_ac_recipe(self):
        sample = item()
        sample['payload']['title'] = 'BMW offers faster charging'
        with self.assertRaises(ChargingNotSupported):
            prepare_ac_option(sample, SOURCE, NOW)

    def test_private_preview_and_candidate_queue_preserve_every_qualification(self):
        sample = item(); before = copy.deepcopy(sample)
        with patch('news_ai.NewsAi.__call__', side_effect=AssertionError('No paid calls')), \
                patch('news_store.NewsStore.put', side_effect=AssertionError('No staging')), \
                patch('news_store.NewsStore.publish', side_effect=AssertionError('No publication')):
            packet, article, review = prepare_bmw_charging(sample, SOURCE, NOW)
            queued = build_queue([sample], [SOURCE], [], NOW)
        self.assertEqual(sample, before)
        self.assertEqual(article['editorial_recipe'], RECIPE)
        self.assertEqual(article['status'], 'private_preview')
        self.assertFalse(article['publication_supported'])
        self.assertTrue(review['passed'], review)
        self.assertEqual(review['method'], REVIEW)
        self.assertFalse(review['ai_audit_performed'])
        text = ' '.join([article['intro'], *[p['text'] for p in article['paragraphs']]])
        for phrase in ['kommande tillval', '22 kW', '3,7 kW', 'tyska marknaden', 'prelimin\u00e4ra']:
            self.assertIn(phrase, text)
        self.assertEqual(article['related_models'], [])
        self.assertIsNone(article['image'])
        self.assertEqual(queued['items'][0]['status'], 'private_candidate')
        self.assertEqual(queued['items'][0]['formats'][0]['facts'], packet)
        self.assertFalse(queued['items'][0]['formats'][0]['publication_supported'])

    def test_changed_packet_prose_or_source_fails_independent_rule_review(self):
        sample = item()
        packet, article, _ = prepare_ac_option(sample, SOURCE, NOW)
        for mutate in [lambda a: a.update(title='Nu standard i Sverige'),
                       lambda a: a['paragraphs'][2].update(text='Slutliga svenska uppgifter.'),
                       lambda a: a.update(publication_supported=True),
                       lambda a: a.update(paragraphs=['malformed'])]:
            changed = copy.deepcopy(article); mutate(changed)
            self.assertFalse(review_ac_private(changed, packet, sample, SOURCE, NOW)['passed'])
        changed_packet = copy.deepcopy(packet)
        changed_packet['fields']['market']['value']['country'] = 'SE'
        self.assertFalse(review_ac_private(article, changed_packet, sample, SOURCE, NOW)['passed'])
        self.assertFalse(review_ac_private(article, packet, item(TEXT.replace('22 kW', '11 kW')), SOURCE, NOW)['passed'])

    def test_both_production_publishers_reject_private_ac_recipe(self):
        _, article, review = prepare_ac_option(item(), SOURCE, NOW)
        store = Mock()
        store.get.return_value = {'status': 'draft', 'payload': article}
        with self.assertRaisesRegex(ValueError, 'validated_draft'):
            release(store, 'private-ac', True, NOW)
        with self.assertRaisesRegex(ValueError, 'exact_passed_draft'):
            single_release_sql({'status': 'draft', 'payload': article}, review, 0)
        store.publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
