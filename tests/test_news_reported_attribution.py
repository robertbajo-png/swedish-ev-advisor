"""Explicit writing guidance; missing provenance still fails before paid review."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_publisher_articles as fixtures
from test_news_reported_articles import reported_fixture
from test_news_publisher_flexible_policy import single_fixture
from news_publisher_articles import writer_call, precheck


class ReportedAttributionTests(unittest.TestCase):
    def test_exact_source_prefix_is_given_for_single_and_paired_reporting(self):
        for fixture in (single_fixture, reported_fixture):
            bundle, _, _ = fixture()
            _, _, prompt = writer_call(bundle)
            payload = json.loads(prompt.split('\n', 1)[1])
            expected = 'Enligt ' + ' och '.join(i['payload']['publisher'] for i in bundle['items'])
            self.assertEqual(payload['reported_attribution_prefix'], expected)
            self.assertIn('BEGIN the intro AND EACH paragraphs[i].text', prompt)
            self.assertIn('Intro attribution does not carry into a later paragraph', prompt)

    def test_missing_attribution_in_p1_still_fails_despite_attributed_intro(self):
        bundle, packet, _ = single_fixture()
        self.assertTrue(precheck(bundle, packet, fixtures.NOW)['passed'])
        paragraph = packet['article']['paragraphs'][1]
        self.assertTrue(paragraph['text'].startswith('Enligt medierna '))
        paragraph['text'] = paragraph['text'][len('Enligt medierna '):]
        checked = precheck(bundle, packet, fixtures.NOW)
        self.assertFalse(checked['passed'])
        self.assertIn('publisher_reported_block_attribution_missing:p1', checked['errors'])

    def test_primary_supported_route_does_not_get_editorial_only_instructions(self):
        bundle, _ = fixtures.fixture()
        prompt = writer_call(bundle)[2]
        payload = json.loads(prompt.split('\n', 1)[1])
        self.assertIsNone(payload['reported_attribution_prefix'])
        self.assertNotIn('BEGIN the intro AND EACH paragraphs[i].text', prompt)


if __name__ == '__main__':
    unittest.main()
