import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_editorial import claim_scope_errors, claim_topics, generate_article, validate_article, writing_inventory


class NewsClaimScopeTests(unittest.TestCase):
    def article(self, text, ids):
        return {'paragraphs': [{'text': text, 'fact_ids': ids, 'kind': 'reporting'}]}

    def test_real_failed_consumption_clause_cannot_cite_launch_timing(self):
        facts = [{'id': 'launch', 'statement': 'Modellen lanseras på den svenska marknaden i november.'}]
        article = self.article('Förbrukning och räckvidd kan påverkas av utrustningsnivån.', ['launch'])
        self.assertEqual(claim_scope_errors(article, facts), [
            'claim_scope_mismatch:p0:consumption', 'claim_scope_mismatch:p0:equipment',
            'claim_scope_mismatch:p0:range'])

    def test_correct_fact_elsewhere_does_not_support_this_block(self):
        facts = [{'id': 'launch', 'statement': 'Beställningarna öppnar under hösten.'},
                 {'id': 'range', 'statement': 'Räckvidden uppgår till 400 km enligt WLTP.'}]
        wrong = self.article('WLTP-räckvidden är 400 km.', ['launch'])
        self.assertIn('claim_scope_mismatch:p0:range', claim_scope_errors(wrong, facts))
        wrong['paragraphs'][0]['fact_ids'] = ['range']
        self.assertEqual(claim_scope_errors(wrong, facts), [])

    def test_r18_wltp_qualification_must_cite_its_own_fact_not_just_range(self):
        facts = [{'id': 'range', 'statement': 'Batteriet har 37 kWh och räckvidden är upp till 324 km enligt WLTP.'},
                 {'id': 'qualifier', 'statement': 'Angiven WLTP-räckvidd varierar med bilens utrustning.'}]
        article = self.article('Räckvidden anges till upp till 324 km enligt WLTP. Den kan variera med utrustningen.', ['range'])
        self.assertIn('claim_scope_mismatch:p0:equipment', claim_scope_errors(article, facts))
        article['paragraphs'][0]['fact_ids'].append('qualifier')
        self.assertEqual(claim_scope_errors(article, facts), [])

    def test_incidental_evidence_is_not_a_licensed_claim(self):
        facts = [{'id': 'f0', 'statement': 'Lanseringen sker under hösten.',
                  'evidence': 'Launch in autumn. Consumption and range figures appear in adjacent evidence.'}]
        self.assertEqual(claim_scope_errors(self.article('Förbrukningen har ändrats.', ['f0']), facts),
                         ['claim_scope_mismatch:p0:consumption'])
        self.assertEqual(writing_inventory(facts)[0]['claim_topics'], ['availability'])

    def test_concrete_scope_can_be_combined_from_the_blocks_actual_citations(self):
        facts = [{'id': 'battery', 'statement': 'Batteriet har 60 kWh och räckvidden är 400 km.'},
                 {'id': 'charging', 'statement': 'DC-snabbladdningen har en laddtid på 25 minuter.'}]
        article = self.article('Batteriets kapacitet är 60 kWh. Räckvidden är 400 km och laddtiden är 25 minuter.',
                               ['battery', 'charging'])
        self.assertEqual(claim_scope_errors(article, facts), [])
        self.assertEqual(claim_scope_errors(self.article('Har din vardag behov av längre räckvidd?', ['battery']), facts), [])

    def test_efficiency_does_not_automatically_license_consumption_claims(self):
        facts = [{'id': 'f0', 'statement': 'A new battery construction improves efficiency.'}]
        self.assertEqual(claim_scope_errors(self.article('Förbrukningen blir lägre.', ['f0']), facts),
                         ['claim_scope_mismatch:p0:consumption'])
        self.assertEqual(claim_topics('prismatic battery cells'), set())

    def test_even_a_passing_mock_audit_cannot_override_a_topic_mismatch(self):
        article = fixtures.draft()
        article['paragraphs'][0]['text'] += ' Förbrukningen är låg.'
        original = copy.deepcopy(article)
        facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
        checks = validate_article(article, facts, [fixtures.item()], fixtures.audit(), 90)
        self.assertIn('claim_scope_mismatch:p0:consumption', checks['evidence'])
        self.assertEqual(article, original)

    def test_topic_match_alone_never_replaces_independent_review(self):
        facts = [{'id': 'f0', 'statement': 'Räckvidden är 400 km.', 'evidence': 'Räckvidden är 400 km.'}]
        article = self.article('Räckvidden är bäst i klassen.', ['f0'])
        self.assertEqual(claim_scope_errors(article, facts), [])
        # Topic equality cannot establish comparisons, causality or actual semantic support.
        self.assertIn('independent_audit_not_run', validate_article(article, facts, [], None, 90)['evidence'])

    def test_writer_brief_binds_each_clause_and_question_to_its_own_fact(self):
        ai = Mock(return_value=fixtures.writer_result(fixtures.draft()))
        generate_article(fixtures.extraction()['facts'], ai)
        prompt = ai.call_args.args[2]
        for instruction in ['OWN cited statements', 'Fact IDs are not general source endorsements',
                            'ONE practical personal decision', 'without repeating numbers', 'question contains no digits']:
            self.assertIn(instruction, prompt)


if __name__ == '__main__':
    unittest.main()
