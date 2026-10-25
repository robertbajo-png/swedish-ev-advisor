"""Offered motor ratings are not driver-selectable operating modes."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
import test_news_fact_brief as brief
from news_editorial import article_preflight, audit_article, generate_article, validate_article
from news_editorial_language import power_option_errors
from news_fact_brief import neutral_facts, source_technical_facts, writing_card


class PowerTerminologyTests(unittest.TestCase):
    def setUp(self):
        self.fact = {'id': 'power', 'statement': 'Två effektnivåer erbjuds: 116 hk (85 kW) och 135 hk (99 kW)'}

    def test_cards_keep_pairings_and_explicit_option_not_mode_meaning(self):
        before = copy.deepcopy(self.fact)
        card = writing_card(self.fact['statement'])
        self.assertEqual(card['motor_power_options'], [{'hk': '116', 'kw': '85'}, {'hk': '135', 'kw': '99'}])
        self.assertEqual(card['motor_power_option_meaning'], 'offered_power_ratings_not_driver_selectable_modes')
        self.assertEqual(self.fact, before)
        for suffix in [' endast i Tyskland', ' med tillfällig boost', ' som valbara körlägen']:
            text = self.fact['statement'] + suffix
            self.assertEqual(writing_card(text), {'statement': text})

    def test_observed_mode_wording_and_selectable_mode_synonyms_fail(self):
        for text in ['Motorn erbjuds i två effektlägen: 116 hk eller 135 hk.',
                     'Föraren kan välja körläge med 85 kW.', 'Motorn har två power modes.',
                     'Motorn har valbara driving modes.']:
            block = {'id': 'p1', 'text': text, 'kind': 'reporting', 'fact_ids': ['power']}
            self.assertEqual(power_option_errors([block], [self.fact]), ['unsupported_motor_power_modes:p1'])

    def test_ratings_are_allowed_but_genuine_mode_facts_are_not_globally_banned(self):
        block = {'id': 'p1', 'text': 'Motoreffekten anges till antingen 116 hk (85 kW) eller 135 hk (99 kW).',
                 'kind': 'reporting', 'fact_ids': ['power']}
        self.assertEqual(power_option_errors([block], [self.fact]), [])
        block['text'] = 'Bilen har valbara körlägen enligt tillverkaren.'
        self.assertEqual(power_option_errors([block], [{'id': 'power', 'statement': 'Bilen har valbara körlägen.'}]), [])
        block['fact_ids'] = ['other']
        self.assertEqual(power_option_errors([block], [self.fact]), [])

    def test_deterministic_gate_rejects_mode_claim_even_with_positive_ai_audit(self):
        item, facts = brief.source_and_facts()
        facts = neutral_facts(facts + source_technical_facts(item, facts))
        article = generate_article(facts, Mock(return_value=brief.reference_output(facts)))
        article['paragraphs'][1]['text'] = 'Motorn erbjuds i två effektlägen: 130 hk (96 kW) eller 160 hk (118 kW).'
        self.assertIn('unsupported_motor_power_modes:p1', article_preflight(article, facts, [item], 90)['gate_errors']['evidence'])
        self.assertIn('unsupported_motor_power_modes:p1', validate_article(article, facts, [item], fixtures.audit(facts), 90)['evidence'])

    def test_writer_and_independent_reviewer_receive_distinction_not_extra_evidence(self):
        item, facts = brief.source_and_facts()
        facts = neutral_facts(facts + source_technical_facts(item, facts))
        writer = Mock(return_value=brief.reference_output(facts))
        article = generate_article(facts, writer)
        prompt = writer.call_args.args[2]
        self.assertIn('"motor_power_options":', prompt)
        self.assertIn('motor_power_option_meaning', prompt)
        self.assertIn('never driver-selectable', prompt)
        reviewer = Mock(return_value=fixtures.keyed_audit(fixtures.audit(facts)))
        audit_article(article, facts, reviewer)
        review = json.loads(reviewer.call_args.args[2].split('\n')[-1])
        examples = review['calibration_examples_not_evidence']
        self.assertTrue(any(e['source'] == 'Två effektnivåer erbjuds' and 'NOT equivalent' in e['scope'] for e in examples))
        self.assertEqual(review['facts'], facts)


if __name__ == '__main__':
    unittest.main()
