"""Offline launch phrasing keeps market, event and month-boundary precision."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_fact_brief as brief
from news_editorial import (article_preflight, build_fact_plan, generate_article,
                            source_qualifier_facts, validate_article, writing_style_errors)
from news_fact_brief import neutral_facts, source_technical_facts, writer_plan, writing_card
from news_store import artifact_hash
from preview_news_equipment_offline import polish_launch_reference, revise_reference

LAUNCH = 'ID. Cross lanseras på den svenska marknaden vid månadsskiftet november/december'
AWKWARD = 'Modellen lanseras i Sverige över övergången mellan november och december.'


class LaunchCardTests(unittest.TestCase):
    def test_month_boundary_is_not_a_date_or_an_entire_two_month_window(self):
        card = writing_card(LAUNCH)
        self.assertEqual(card['event'], 'market_launch')
        self.assertEqual(card['model'], 'ID. Cross')
        self.assertEqual(card['market'], 'Sweden')
        self.assertEqual(card['timing'], {'boundary_months': ['november', 'december'],
                                          'precision': 'month_boundary', 'year_basis': 'not_stated'})
        self.assertNotIn('delivery', json.dumps(card))

    def test_year_boundary_does_not_infer_calendar_years(self):
        card = writing_card(LAUNCH.replace('november/december', 'december/januari'))
        self.assertEqual(card['timing']['boundary_months'], ['december', 'januari'])
        self.assertEqual(card['timing']['year_basis'], 'not_stated')

    def test_invalid_or_nonadjacent_months_keep_the_full_statement(self):
        for pair in ['november/november', 'november/januari', 'december/november', 'snart/senare']:
            statement = LAUNCH.replace('november/december', pair)
            self.assertEqual(writing_card(statement), {'statement': statement})

    def test_uncertain_or_qualified_timing_is_not_promoted_to_a_firm_launch(self):
        for statement in [LAUNCH.replace(' lanseras ', ' väntas lanseras '),
                          LAUNCH.replace(' lanseras ', ' förväntas lanseras '),
                          LAUNCH.replace(' lanseras ', ' tros lanseras '),
                          LAUNCH.replace(' lanseras ', ' ska lanseras '),
                          LAUNCH.replace(' lanseras ', ' kan lanseras '),
                          LAUNCH + ' preliminärt', LAUNCH + ' 2027',
                          LAUNCH + ' beroende på godkännande']:
            self.assertEqual(writing_card(statement), {'statement': statement})

    def test_writer_plan_keeps_launch_citations_and_original_evidence(self):
        _, facts = brief.source_and_facts()
        original = copy.deepcopy(facts)
        plan = build_fact_plan(facts)
        writing = writer_plan(plan)
        launch = next(card for card in writing['intro']['facts'] if card.get('event') == 'market_launch')
        self.assertEqual(launch['timing']['precision'], 'month_boundary')
        self.assertEqual(writing['intro']['fact_ids'], plan['intro']['fact_ids'])
        self.assertEqual(facts, original)


class LaunchStyleTests(unittest.TestCase):
    def test_observed_launch_phrase_has_a_specific_offline_diagnostic(self):
        errors = writing_style_errors({'intro': AWKWARD, 'paragraphs': []})
        self.assertIn('awkward_launch_timing:intro', errors)

    def test_natural_month_boundary_forms_and_other_crossings_are_not_blocked(self):
        for text in ['Den svenska lanseringen sker vid skiftet mellan november och december.',
                     'Modellen lanseras i Sverige vid övergången mellan november och december.',
                     'Testbilen körde över övergången vid provbanan.',
                     'Lanseringen är klar. Testbilen körde över övergången vid provbanan.']:
            self.assertNotIn('awkward_launch_timing:intro', writing_style_errors({'intro': text, 'paragraphs': []}))


class OfflineLaunchReferenceTests(unittest.TestCase):
    def sample(self):
        item, initial = brief.source_and_facts()
        facts = neutral_facts(initial + source_technical_facts(item, initial) + source_qualifier_facts(item))
        output = brief.reference_output(facts)
        output['intro'] = 'Nu går det att lägga en förhandsbeställning på Testbil E1. ' + AWKWARD
        payload = generate_article(facts, Mock(return_value=output))
        original = {'id': 'original', 'status': 'quarantined', 'published_at': None,
                    'payload': payload, 'artifact_hash': artifact_hash(payload)}
        return item, facts, revise_reference(original, facts)

    def test_only_intro_changes_and_prior_reference_is_not_mutated(self):
        item, facts, reference = self.sample()
        original = copy.deepcopy(reference)
        revised = polish_launch_reference(reference, facts)
        self.assertEqual(reference, original)
        self.assertEqual(revised['payload']['paragraphs'], reference['payload']['paragraphs'])
        self.assertEqual(revised['payload']['intro_fact_ids'], reference['payload']['intro_fact_ids'])
        self.assertEqual(revised['payload']['title'], reference['payload']['title'])
        self.assertNotEqual(revised['artifact_hash'], reference['artifact_hash'])
        self.assertNotEqual(revised['id'], reference['id'])
        self.assertIn('Den svenska lanseringen sker vid skiftet mellan november och december.', revised['payload']['intro'])
        self.assertEqual(article_preflight(revised['payload'], facts, [item], 90)['errors'], [])

    def test_preorder_sentence_and_dotted_model_name_are_preserved_exactly(self):
        _, facts, reference = self.sample()
        prefix = 'Volkswagen öppnar förhandsbeställningarna för ID. Cross. '
        reference['payload']['intro'] = prefix + AWKWARD
        revised = polish_launch_reference(reference, facts)
        self.assertEqual(revised['payload']['intro'].split('Den svenska lanseringen')[0], prefix)
        self.assertNotIn('leverans', revised['payload']['intro'])

    def test_uncited_ambiguous_or_changed_timing_is_not_silently_rewritten(self):
        _, facts, reference = self.sample()
        changed = copy.deepcopy(reference)
        changed['payload']['intro_fact_ids'] = ['f0']
        with self.assertRaisesRegex(ValueError, 'one_cited_month_boundary'):
            polish_launch_reference(changed, facts)
        duplicate = {**next(fact for fact in facts if fact['id'] == 'f4'), 'id': 'other-launch'}
        changed['payload']['intro_fact_ids'] = ['f0', 'f4', 'other-launch']
        with self.assertRaisesRegex(ValueError, 'one_cited_month_boundary'):
            polish_launch_reference(changed, facts + [duplicate])
        changed = copy.deepcopy(reference)
        changed['payload']['intro'] = changed['payload']['intro'].replace('november och december', 'april och maj')
        with self.assertRaisesRegex(ValueError, 'clause_changed_or_ambiguous'):
            polish_launch_reference(changed, facts)

    def test_no_old_audit_is_reused_for_the_polished_reference(self):
        item, facts, reference = self.sample()
        reference['checks'] = ['A previous review is not approval for an edit']
        revised = polish_launch_reference(reference, facts)
        self.assertNotIn('checks', revised)
        checks = validate_article(revised['payload'], facts, [item], None, 90)
        self.assertTrue(all('independent_audit_not_run' in errors for errors in checks.values()))
        self.assertEqual(revised['status'], 'quarantined')
        self.assertIsNone(revised['published_at'])


if __name__ == '__main__':
    unittest.main()
