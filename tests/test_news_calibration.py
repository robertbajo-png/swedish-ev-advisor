"""Offline review-contract tests, not claims of LLM agreement with human labels."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
import trial_news_matrix as matrix
import trial_news_matrix_r20 as r20
from news_editorial import audit_article, validate_article, blocks, generate_article, claim_scope_errors
from news_editorial_language import TERMINOLOGY, REVIEW_CALIBRATION, power_bound_errors, current_type_errors
from news_fact_brief import writing_card


class EditorialCalibrationTests(unittest.TestCase):
    def test_r20_ac_capacity_and_charging_power_are_same_topic_not_an_unsupported_claim(self):
        facts = [{'id': 'ac', 'statement': 'AC-laddningskapaciteten är som mest 11 kW.'}]
        article = {'paragraphs': [{'text': 'Vid växelströmsladdning är laddeffekten som mest 11 kW.',
                                  'fact_ids': ['ac'], 'kind': 'reporting'}]}
        self.assertEqual(claim_scope_errors(article, facts), [])
        self.assertEqual(current_type_errors(blocks(article), facts), [])
        article['paragraphs'][0]['text'] = 'Vid likströmsladdning är laddeffekten som mest 11 kW.'
        self.assertEqual(current_type_errors(blocks(article), facts), ['unsupported_current_type:p0:DC'])

    def test_both_currents_are_permitted_only_when_the_own_statement_contains_both(self):
        facts = [{'id': 'q', 'statement': 'Tiden till full laddning beror på effekten vid AC- och DC-laddning.'}]
        article = {'paragraphs': [{'text': 'Effekten vid såväl växelström som likström påverkar tiden till fullt batteri.',
                                  'fact_ids': ['q'], 'kind': 'reporting'}]}
        self.assertEqual(current_type_errors(blocks(article), facts), [])
        facts[0]['statement'] = facts[0]['statement'].replace('AC- och DC', 'AC')
        self.assertEqual(current_type_errors(blocks(article), facts), ['unsupported_current_type:p0:DC'])

    def test_complete_cards_preserve_preorders_boundary_and_stated_not_max_power(self):
        card = writing_card('Test inleder nu förförsäljningen av Testbil E1 med ett batteri på 48 kWh')
        self.assertEqual(card['event'], 'preorders_open')
        timing = writing_card('Testbil E1 lanseras på den svenska marknaden vid månadsskiftet april/maj')
        self.assertEqual(timing['timing']['boundary_months'], ['april', 'maj'])
        charge = writing_card('DC-snabbladdning med 100 kW från 10 till 80 procent på cirka 24 minuter')['charging']
        self.assertEqual(charge['power_basis'], 'stated_not_explicit_maximum')
        self.assertEqual(charge['current'], 'DC')
        self.assertEqual(TERMINOLOGY['DC'], 'likström')
        self.assertEqual(TERMINOLOGY['AC'], 'växelström')

    def test_maximum_cannot_be_invented_but_current_synonym_is_not_a_new_claim(self):
        facts = [{'id': 'dc', 'statement': 'DC-snabbladdning med 100 kW från 10 till 80 procent på cirka 24 minuter'}]
        block = {'id': 'p0', 'kind': 'reporting', 'fact_ids': ['dc'],
                 'text': 'Med likström anges laddningen till 100 kW och ungefär 24 minuter från 10 till 80 procent.'}
        self.assertEqual(power_bound_errors([block], facts), [])
        for bound in ['högst', 'max', 'upp till']:
            block['text'] = 'Laddningen sker med ' + bound + ' 100 kW.'
            self.assertEqual(power_bound_errors([block], facts), ['unstated_power_maximum:p0'])
        # A truly cited explicit maximum is different from terminology guidance.
        facts.append({'id': 'max', 'statement': 'Effekten är högst 100 kW.'})
        block.update(text='Effekten är högst 100 kW.', fact_ids=['dc', 'max'])
        self.assertEqual(power_bound_errors([block], facts), [])

    def test_audit_packet_has_only_own_statement_bindings_and_calibration_is_not_evidence(self):
        facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
        original = copy.deepcopy(facts)
        article = fixtures.draft()
        ai = Mock(return_value=fixtures.keyed_audit(fixtures.audit(facts)))
        audit_article(article, facts, ai)
        packet = json.loads(ai.call_args.args[2].split('\n')[-1])
        self.assertEqual(packet['facts'], original)
        self.assertEqual(packet['calibration_examples_not_evidence'], REVIEW_CALIBRATION)
        self.assertEqual(packet['terminology_only_not_evidence'], TERMINOLOGY)
        for block in packet['blocks']:
            self.assertEqual(block['permitted_statements'], [f['statement'] for f in facts if f['id'] in block['fact_ids']])
        self.assertEqual(facts, original)
        self.assertIn('never require approval', ai.call_args.args[2])

    def test_term_calibration_cannot_override_a_negative_audit_or_fabricated_number(self):
        facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
        article = fixtures.draft()
        audit = fixtures.audit(facts)
        audit['blocks'][2].update(supported=False, verdict='unsupported_claim', unsupported_claims=['A precise rejected claim'])
        audit['no_unsupported_claims'] = False
        result = audit_article(article, facts, Mock(return_value=fixtures.keyed_audit(audit)))
        self.assertFalse(result['blocks'][2]['supported'])
        self.assertIn('block_audit_failed_or_incomplete', validate_article(article, facts, [fixtures.item()], result, 90)['evidence'])
        article['paragraphs'][0]['text'] += ' Kapaciteten är 999 kWh.'
        self.assertIn('unsupported_numeric_claim:p0', validate_article(article, facts, [fixtures.item()], fixtures.audit(facts), 90)['evidence'])

    def test_new_trial_cannot_inherit_invalid_old_scores_or_retry_metadata(self):
        original = {**fixtures.item(), 'cluster_id': 'old-event'}
        original['payload'].update(extraction={**fixtures.extraction(), 'sweden_relevance': 8.6},
                                   attempts=3, quarantine_reasons=['old error'], budget_retry_after='2099-01-01')
        before = copy.deepcopy(original)
        fresh = matrix.isolated_source_copy(original)
        self.assertEqual(fresh['status'], 'collected')
        self.assertIsNone(fresh['cluster_id'])
        self.assertNotIn('extraction', fresh['payload'])
        self.assertNotIn('budget_retry_after', fresh['payload'])
        self.assertEqual(fresh['payload']['content_hash'], original['payload']['content_hash'])
        self.assertEqual(original, before)

    def test_r20_keeps_budget_and_consumed_trial_identity_separate(self):
        keys = ['RECIPE', 'TRIAL_ID', 'DATABASE', 'OUTPUT', 'REEXTRACT_MODEL']
        original = {key: getattr(matrix, key) for key in keys}
        with patch.multiple(matrix, **original):
            r20.configure()
            self.assertTrue(matrix.REEXTRACT_MODEL)
            self.assertNotEqual(matrix.TRIAL_ID, original['TRIAL_ID'])
            self.assertEqual(matrix.MAX_MICRO_USD, 60000)
            self.assertEqual(matrix.MAX_REQUESTS, 9)
            self.assertEqual(matrix.RECIPE, 'news-editorial-recipe-2026-10-r20')


if __name__ == '__main__':
    unittest.main()
