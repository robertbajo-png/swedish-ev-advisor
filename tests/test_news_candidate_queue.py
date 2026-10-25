"""Private, free source routing. No fixtures are live publication evidence."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_news_candidate_queue import build_queue, launch_signature, ReadOnlyClient
from test_news_notices import VW, ACEA, MODEL, PRICES, source, NOW
from test_news_statistics import TEXT as STAT_TEXT

EN = {'id': 'vw-press', 'kind': 'primary', 'name': 'Volkswagen Newsroom',
      'website': 'https://www.volkswagen-newsroom.com'}


def english_item():
    item = source(MODEL, EN)
    item['url'] = item['payload']['final_url'] = EN['website'] + '/en/press-releases/id-cross-can-now-be-ordered-with-a-37-kwh-battery-20754'
    item['payload']['title'] = 'Affordable and versatile: ID. Cross can now be ordered with a 37 kWh battery'
    return item


def published():
    return [{'id': 'published-vw', 'published_at': NOW.isoformat(), 'sources': [{
        'url': VW['website'] + '/nyheter--media/pressmeddelanden/2026/10/published/',
        'title': 'Nya Volkswagen ID. Cross kan nu best\u00e4llas med ett batteri p\u00e5 37 kWh',
        'published_at': NOW.isoformat()}]}]


class CandidateQueueTests(unittest.TestCase):
    def test_same_event_in_another_language_is_held_not_merged_or_paid(self):
        result = build_queue([english_item()], [EN], published(), NOW)
        entry = result['items'][0]
        self.assertEqual(entry['status'], 'possible_duplicate')
        self.assertEqual(entry['published_article_id'], 'published-vw')
        self.assertEqual(entry['formats'], [])
        self.assertEqual((result['paid_calls'], result['published'], result['production_writes']), (0, 0, 0))

    def test_other_date_model_battery_or_nonofficial_domain_does_not_merge(self):
        original = launch_signature('ID. Cross can now be ordered with a 37 kWh battery', EN['website'], NOW.isoformat())
        for title, url, date in [
                ('ID. Cross can now be ordered with a 52 kWh battery', EN['website'], NOW.isoformat()),
                ('ID. Polo can now be ordered with a 37 kWh battery', EN['website'], NOW.isoformat()),
                ('ID. Cross can now be ordered with a 37 kWh battery', EN['website'], '2026-10-22'),
                ('ID. Cross can now be ordered with a 37 kWh battery', 'https://comparison.example', NOW.isoformat())]:
            self.assertNotEqual(launch_signature(title, url, date), original)
        self.assertIsNone(launch_signature('ID. Cross with 37 and 52 kWh', EN['website'], NOW.isoformat()))

    def test_exact_published_url_never_enters_extraction(self):
        item = source(MODEL + PRICES)
        old = [{'id': 'old', 'published_at': NOW.isoformat(), 'sources': [{'url': item['url']}]}]
        with patch('build_news_candidate_queue.prepare_notice') as notice, patch('build_news_candidate_queue.make_brief') as brief:
            result = build_queue([item], [VW], old, NOW)
        self.assertEqual(result['items'][0]['status'], 'already_published')
        notice.assert_not_called(); brief.assert_not_called()

    def test_plugin_hybrid_is_not_mistaken_for_battery_electric_news(self):
        item = source(MODEL)
        for title, status in [('Skoda Kodiaq iV ny laddhybriddrivlina', 'excluded_powertrain'),
                              ('New plug-in hybrid model', 'excluded_powertrain'),
                              ('Battery electric and plug-in hybrid models compared', 'needs_topic_review')]:
            item['payload']['title'] = title
            result = build_queue([item], [VW], [], NOW)
            self.assertEqual(result['items'][0]['status'], status)
            self.assertEqual(result['items'][0]['formats'], [])

    def test_official_statistic_notice_is_private_and_never_an_ai_audit(self):
        item = source(STAT_TEXT, ACEA)
        result = build_queue([item], [ACEA], [], NOW)
        entry = result['items'][0]
        self.assertEqual(entry['status'], 'private_candidate')
        fmt = entry['formats'][0]
        self.assertEqual(fmt['format'], 'statistics_notice')
        self.assertTrue(fmt['review']['passed'])
        self.assertFalse(fmt['ai_audit_performed'])
        self.assertTrue(fmt['requires_separate_release_decision'])
        self.assertFalse(result['release_authorized'])

    def test_free_price_preparation_and_ai_fact_packet_do_not_generate_ai_text(self):
        import json
        from preview_news_launch_hybrid import fixture_input
        data = json.loads((Path(__file__).parent / 'fixtures/news_hybrid_launch.json').read_text(encoding='utf-8'))
        items, _ = fixture_input(data)
        with patch('news_ai.NewsAi.__call__', side_effect=AssertionError('Paid AI forbidden')):
            result = build_queue(items, [VW], [], NOW)
        formats = {f['format']: f for f in result['items'][0]['formats']}
        self.assertIn('price_notice', formats)
        self.assertIn('ai_model', formats)
        self.assertFalse(formats['ai_model']['independent_review_performed'])
        self.assertNotIn('article', formats['ai_model'])

    def test_old_blocked_forged_or_wrong_domain_content_is_quarantined(self):
        for mutate in [lambda i: i['payload'].update(content_hash='forged'),
                       lambda i: i['payload'].update(access_status='blocked'),
                       lambda i: i['payload'].update(fetched_at='2020-01-01'),
                       lambda i: i['payload'].update(published_at='2020-01-01'),
                       lambda i: i['payload'].update(final_url='https://elsewhere.example/news')]:
            item = source(MODEL + PRICES)
            mutate(item)
            result = build_queue([item], [VW], [], NOW)
            self.assertEqual(result['items'][0]['status'], 'quarantined')
            self.assertEqual(result['items'][0]['formats'], [])

    def test_unsupported_but_accessible_official_source_waits_for_an_adapter(self):
        item = english_item()
        result = build_queue([item], [EN], [], NOW)
        self.assertEqual(result['items'][0]['status'], 'needs_adapter')
        self.assertEqual(result['items'][0]['formats'], [])

    def test_input_artifacts_are_unchanged_and_remote_writes_are_impossible(self):
        item = source(MODEL + PRICES)
        before = copy.deepcopy(item)
        build_queue([item], [VW], [], NOW)
        self.assertEqual(item, before)
        client = object.__new__(ReadOnlyClient)
        for method in ('POST', 'PATCH', 'DELETE'):
            with self.assertRaisesRegex(ValueError, 'only_remote_reads'):
                client._request(method, 'news_articles')


if __name__ == '__main__':
    unittest.main()
