"""Single-source prose need not repeat the intro; provenance remains mandatory."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_publisher_articles as fixtures
from test_news_reported_articles import reported_fixture
from test_news_publisher_flexible_policy import single_fixture
from news_publisher_articles import writer_call, reviewer_call, precheck


class ReportedAttributionTests(unittest.TestCase):
    def test_exact_source_prefix_is_given_for_single_and_paired_reporting(self):
        for fixture, guidance in ((single_fixture, 'let that attribution carry through the body'),
                                  (reported_fixture, 'attribution in every paragraph')):
            bundle, packet, _ = fixture()
            _, _, prompt = writer_call(bundle)
            payload = json.loads(prompt.split('\n', 1)[1])
            expected = 'Enligt ' + ' och '.join(i['payload']['publisher'] for i in bundle['items'])
            self.assertEqual(payload['reported_attribution_prefix'], expected)
            self.assertIn('Begin the intro with the supplied reported_attribution_prefix', prompt)
            self.assertIn(guidance, prompt)
            audit_prompt = reviewer_call(bundle, packet)[2]
            self.assertEqual('Missing repeated attribution alone is not an error' in audit_prompt,
                             fixture is single_fixture)

    def test_intro_attribution_carries_only_in_single_source_body(self):
        for fixture in (single_fixture, reported_fixture):
            bundle, packet, _ = fixture()
            paragraph = packet['article']['paragraphs'][1]
            paragraph['text'] = paragraph['text'].removeprefix('Enligt medierna ').capitalize()
            checked = precheck(bundle, packet, fixtures.NOW)
            self.assertEqual(checked['passed'], fixture is single_fixture, checked)
            if fixture is reported_fixture:
                self.assertIn('publisher_reported_block_attribution_missing:p1', checked['errors'])

    def test_single_source_requires_named_intro_and_reported_headline(self):
        bundle, packet, _ = single_fixture()
        packet['article']['intro'] = packet['article']['intro'].replace('Enligt CarNewsChina ', '')
        packet['article']['title'] = packet['article']['title'].removeprefix('Rapporterat: ')
        checked = precheck(bundle, packet, fixtures.NOW)
        self.assertIn('publisher_reported_intro_attribution_missing', checked['errors'])
        self.assertIn('publisher_reported_headline_label_missing', checked['errors'])

    def test_primary_supported_route_does_not_get_editorial_only_instructions(self):
        bundle, _ = fixtures.fixture()
        prompt = writer_call(bundle)[2]
        payload = json.loads(prompt.split('\n', 1)[1])
        self.assertIsNone(payload['reported_attribution_prefix'])
        self.assertNotIn('Begin the intro with the supplied reported_attribution_prefix', prompt)


if __name__ == '__main__':
    unittest.main()
