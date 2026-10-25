"""Unsupported comparative premises must fail even when an AI reviewer approves."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_editorial import (article_preflight, audit_article, comparison_errors,
                            repair_source_wording, validate_article)


class NewsComparisonTests(unittest.TestCase):
    def check(self, text, statement, extra=None):
        article = {'paragraphs': [{'text': text, 'kind': 'reporting', 'fact_ids': ['f']}]}
        return comparison_errors(article, [{'id': 'f', 'statement': statement}, *(extra or [])])

    def test_real_smaller_battery_modifier_is_not_supported_by_absolute_capacity(self):
        self.assertEqual(self.check('Den mindre batteriversionen har 37 kWh netto.',
                                    'Batteriet har 37 kWh netto.'),
                         ['unverified_comparison:p0:battery:smaller'])

    def test_absolute_figures_never_establish_advantages_or_rankings(self):
        for text, statement in [
            ('Batteriet är större.', 'Batteriet har 60 kWh.'),
            ('Den har längre räckvidd.', 'Räckvidden är 450 km.'),
            ('Den har lägre förbrukning.', 'Förbrukningen är 20 kWh per 100 km.'),
            ('Bilen är billigare.', 'Priset är 450000 kronor.'),
            ('Bilen laddar snabbare.', 'Laddtiden är 25 minuter.'),
            ('Räckvidden är bäst i klassen.', 'Räckvidden är 450 km.'),
            ('Modellen är klassledande.', 'Modellen har presenterats.'),
            ('The smaller battery has 37 kWh.', 'The battery has 37 kWh.'),
            ('Charging is faster.', 'Charging takes 25 minutes.')]:
            with self.subTest(text=text):
                self.assertTrue(self.check(text, statement))

    def test_comparisons_in_uncited_or_incidental_evidence_do_not_count(self):
        extra = [{'id': 'other', 'statement': 'Den mindre batteriversionen har 37 kWh.'}]
        self.assertTrue(self.check('Den mindre batteriversionen har 37 kWh.', 'Batteriet har 37 kWh.', extra))
        fact = {'id': 'f', 'statement': 'Batteriet har 37 kWh.',
                'evidence': 'Den mindre batteriversionen har 37 kWh.'}
        article = {'title': 'Den mindre batteriversionen', 'title_fact_ids': ['f']}
        self.assertTrue(comparison_errors(article, [fact]))

    def test_different_metric_direction_and_baseline_do_not_license_a_comparison(self):
        for text, statement in [
            ('Batteriet är mindre.', 'Batteriet är större.'),
            ('Batteriet är mindre.', 'Bagageutrymmet är mindre.'),
            ('Räckvidden är längre än hos modell B.', 'Räckvidden är längre än hos modell A.')]:
            with self.subTest(text=text, statement=statement):
                self.assertTrue(self.check(text, statement))

    def test_explicit_matching_comparison_is_not_automatically_rejected(self):
        self.assertEqual(self.check('Den mindre batteriversionen använder ett batteri på 37 kWh.',
                                    'Den mindre batteriversionen har 37 kWh.'), [])
        # Passing this lexical guard still requires the independent semantic audit.

    def test_questions_cannot_hide_a_comparative_vehicle_claim(self):
        for text in ['Passar den mindre batteriversionen din vardag?',
                     'Behöver du den billigare bilen?', 'Är den snabbare laddningen viktig för dig?']:
            self.assertTrue(self.check(text, 'Batteriet har 37 kWh.'))
        self.assertEqual(self.check('Behöver du längre räckvidd?', 'Räckvidden är 450 km.'), [])

    def test_plain_specifications_and_temperature_do_not_imply_competitive_claims(self):
        for text in ['Batteriet har 37 kWh netto.', 'Laddtiden är 25 minuter.',
                     'Laddningen påverkas när temperaturen blir lägre.',
                     'Bagageutrymmet finns bakom baksätet.']:
            self.assertEqual(self.check(text, text), [])

    def test_positive_audit_cannot_override_comparison_gate_or_mutate_input(self):
        article = fixtures.draft()
        article['paragraphs'][0]['text'] += ' Den mindre batteriversionen visas här.'
        original = copy.deepcopy(article)
        facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
        expected = 'unverified_comparison:p0:battery:smaller'
        self.assertIn(expected, article_preflight(article, facts, [fixtures.item()], 90)['errors'])
        self.assertIn(expected, validate_article(article, facts, [fixtures.item()], fixtures.audit(), 90)['evidence'])
        self.assertEqual(article, original)

    def test_language_repair_cannot_hide_new_comparisons_behind_original_citations(self):
        draft = fixtures.draft()
        revised = repair_source_wording(draft, fixtures.extraction()['facts'], [{'block_id': 'p0'}],
            Mock(return_value={'p0': 'Den mindre batteriversionen presenteras.'}))
        self.assertEqual(revised['paragraphs'][0]['fact_ids'], draft['paragraphs'][0]['fact_ids'])
        self.assertIn('unverified_comparison:p0:battery:smaller', comparison_errors(revised, fixtures.extraction()['facts']))

    def test_final_auditor_is_instructed_to_check_comparative_entities_and_scope(self):
        ai = Mock(return_value=fixtures.keyed_audit(fixtures.audit()))
        audit_article(fixtures.draft(), fixtures.extraction()['facts'], ai)
        prompt = ai.call_args.args[2]
        for instruction in ['smaller/larger battery version', 'exact compared entities',
                            'another variant, metric or period', 'hidden inside questions']:
            self.assertIn(instruction, prompt)


if __name__ == '__main__':
    unittest.main()
