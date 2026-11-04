"""Offline alternative selection never supplies an AI/publication approval."""
import copy
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_publisher_articles as fixtures
from news_publisher_articles import (LIMITS, PACKET_BYTES, resolve_writer_output, writer_call,
                                      wording_errors, precheck, pair_bound)
from news_ai import NewsAi
import run_publisher_news as worker


class WordingSelectionTests(unittest.TestCase):
    def alternatives(self):
        bundle, packet = fixtures.fixture()
        raw = fixtures.encoded_fixture(bundle, packet)
        bad = copy.deepcopy(raw['article'])
        bad['paragraphs'][0]['text'] = fixtures.QUOTES[0] + ' ' + bad['paragraphs'][0]['text']
        return bundle, packet, {'extraction': raw['extraction'], 'articles': [bad, raw['article']]}

    def test_one_bounded_writer_returns_two_forms_not_extra_calls_or_a_looser_gate(self):
        b, _, _ = self.alternatives()
        _, schema, prompt = writer_call(b)
        self.assertEqual(schema['properties']['articles']['minItems'], 2)
        self.assertEqual(schema['properties']['articles']['maxItems'], 2)
        self.assertEqual(LIMITS, {'swedish_ev_article': 2000, 'ev_news_independent_audit': 1300})
        self.assertEqual(PACKET_BYTES, 6500)
        self.assertIn('SAME facts', prompt)
        self.assertIn('an inventory, not finished article prose', prompt)
        self.assertIn('Do not solve overlap by adding unsupported explanation', prompt)
        ai = NewsAi.__new__(NewsAi); ai.model, ai.output_limits = 'gpt-6-sol', LIMITS
        self.assertLess(pair_bound(ai, b), 250000)

    def test_original_second_form_selected_without_mutating_the_recorded_response(self):
        b, p, raw = self.alternatives()
        before = copy.deepcopy(raw)
        selected = resolve_writer_output(b, raw)
        self.assertEqual(selected, p)
        self.assertTrue(precheck(b, selected, fixtures.NOW)['passed'])
        self.assertEqual(raw, before)
        self.assertTrue(any('source_overlap' in e for e in wording_errors(b, raw['articles'][0])))

    def test_both_bad_forms_stay_rejected_and_no_facts_are_reconstructed(self):
        b, _, raw = self.alternatives()
        raw['articles'][1] = copy.deepcopy(raw['articles'][0])
        selected = resolve_writer_output(b, raw)
        self.assertFalse(precheck(b, selected, fixtures.NOW)['passed'])
        raw['extraction']['facts'][0]['support'] = [{'evidence_id': 'invented'}]
        with self.assertRaisesRegex(ValueError, 'unknown_literal_evidence_id'):
            resolve_writer_output(b, raw)

    def test_alternative_count_and_unknown_shapes_fail_closed(self):
        for count in (0, 1, 3):
            b, _, raw = self.alternatives()
            raw['articles'] = [raw['articles'][0]] * count
            with self.assertRaisesRegex(ValueError, 'alternative_count'):
                resolve_writer_output(b, raw)
        b, _, raw = self.alternatives(); raw['unverified'] = True
        with self.assertRaisesRegex(ValueError, 'output_shape'):
            resolve_writer_output(b, raw)

    def test_selected_original_wording_still_fails_unsupported_facts(self):
        b, _, raw = self.alternatives()
        raw['articles'][1]['paragraphs'][0]['text'] += ' 9999 kWh.'
        selected = resolve_writer_output(b, raw)
        self.assertFalse(precheck(b, selected, fixtures.NOW)['passed'])

    def test_statistical_padding_fails_without_removing_source_qualifications(self):
        b, p = fixtures.fixture()
        for text in ('Siffrorna beskriver darmed bade antal och andelar.',
                     'De periodandelarna galler alltsa en langre tidsrymd.',
                     'Det ar manadens samlade registreringar som ligger bakom andelarna.'):
            bad = copy.deepcopy(p['article']); bad['paragraphs'][0]['text'] += ' ' + text
            self.assertTrue(any('statistical_padding' in e for e in wording_errors(b, bad)))
        original = copy.deepcopy(p['article'])
        original['paragraphs'][0]['text'] += ' Siffrorna ar avrundade enligt kallan.'
        self.assertFalse(any('statistical_padding' in e for e in wording_errors(b, original)))

    def test_exact_selected_artifact_keeps_separate_receipts_and_private_trial_boundary(self):
        original_encoder = fixtures.encoded_fixture
        def encoded(bundle, packet):
            raw = original_encoder(bundle, packet)
            bad = copy.deepcopy(raw['article']); bad['intro'] = fixtures.QUOTES[0]
            return {'extraction': raw['extraction'], 'articles': [bad, raw['article']]}
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(fixtures, 'encoded_fixture', side_effect=encoded))
            remote, b, p, ai = fixtures.PublisherLifecycleTests().setup_environment(stack, folder)
            record = worker.perform(remote, b, private=True, ai=ai)
            self.assertEqual(record['state'], 'passed', record)
            self.assertEqual(record['packet'], p)
            self.assertEqual(ai.calls, ['swedish_ev_article', 'ev_news_independent_audit'])
            self.assertEqual(len(record['request_ids']), 2)
            self.assertEqual(len(record['writer_output']['articles']), 2)
            self.assertIsNotNone(worker.reviewed_record(remote, record))
            self.assertEqual(remote.public_articles(), [])


if __name__ == '__main__': unittest.main()
