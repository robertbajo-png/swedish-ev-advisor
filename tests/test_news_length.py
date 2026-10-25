"""Synthetic offline cases. Mock reviews do not establish real reviewer accuracy."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
import test_news_fact_brief as brief
import trial_news_matrix as matrix
import trial_news_length_r21 as r21
from news_ai import NewsBudgetBlocked
from news_editorial import article_preflight, audit_article, blocks, generate_article, source_qualifier_facts, validate_article
from news_editorial_language import BUYER_QUESTION_CALIBRATION
from news_fact_brief import neutral_facts, source_technical_facts, writing_card
from news_store import NewsStore

CARGO = 'Bagageutrymmesvolym: 460 liter + 22 liter frunk (med baksätets ryggstöd nedfällt: 1 250 liter) '


def source():
    item, facts = brief.source_and_facts()
    facts = [f for f in facts if f['id'] != 'f6']
    content = item['payload']['content'].replace('Tjänstevikt: 1800 kg ', 'Tjänstevikt: 1800 kg ' + CARGO)
    item['payload'].update(content=content, content_hash=hashlib.sha256(content.encode()).hexdigest())
    return item, facts


class GroundedLengthTests(unittest.TestCase):
    def test_cargo_keeps_separate_volumes_folded_condition_quote_and_scope(self):
        item, facts = source()
        cargo = source_technical_facts(item, facts)[-1]
        self.assertEqual(cargo['technical_field'], 'cargo')
        self.assertIn('ryggstöd nedfällt 1250 liter', cargo['statement'])
        self.assertIn(cargo['evidence'], item['payload']['content'])
        self.assertTrue(8 <= len(cargo['evidence'].split()) <= 24)
        self.assertEqual(writing_card(cargo['statement']), {
            'cargo_liters': '460', 'frunk_liters': '22', 'folded_rear_backrest_cargo_liters': '1250'})
        self.assertEqual(cargo['scope'], {'model': 'Testbil E1', 'battery_kwh': '48'})
        self.assertEqual(source_technical_facts(item, facts + [cargo])[-1]['technical_field'], 'braked_tow')

    def test_unknown_qualifiers_duplicate_fields_and_implausible_values_fail_closed(self):
        for old, new in [('frunk (med', 'frunk endast Life (med'), ('1 250 liter)', '1 250 liter, endast Life)'),
                         ('22 liter frunk', '900 liter frunk'), ('1 250 liter)', '250 liter)'),
                         ('460 liter +', '460 kg +'), ('1 250 liter)', '1 250 liter) ' + CARGO),
                         ('Tekniska data för Testbil E1', 'Tekniska data för Annan bil')]:
            with self.subTest(new=new):
                item, facts = source()
                content = item['payload']['content'].replace(old, new)
                item['payload'].update(content=content, content_hash=hashlib.sha256(content.encode()).hexdigest())
                self.assertNotIn('cargo', [f['technical_field'] for f in source_technical_facts(item, facts)])

    def test_old_partial_cargo_fact_is_not_duplicated_to_inflate_length(self):
        item, facts = source()
        facts.append({'id': 'partial', 'item_id': item['id'], 'statement': 'Bagaget rymmer 460 liter.'})
        self.assertNotIn('cargo', [f['technical_field'] for f in source_technical_facts(item, facts)])

    def test_new_grounded_details_can_reach_length_without_weakening_short_article_gate(self):
        item, facts = source()
        facts = neutral_facts(facts + source_technical_facts(item, facts) + source_qualifier_facts(item))
        output = brief.reference_output(facts)
        output['paragraphs'].pop(4)
        output['paragraphs'].append('Bagageutrymmet rymmer 460 liter. Frunken har en separat volym på 22 liter. '
                                    'Med baksätets ryggstöd nedfällt anges bagagevolymen till 1 250 liter.')
        article = generate_article(facts, Mock(return_value=output))
        before = copy.deepcopy(article)
        check = article_preflight(article, facts, [item], 90)
        self.assertEqual(check['errors'], [])
        self.assertTrue(150 <= check['word_count'] <= 230)
        audit = fixtures.audit(facts)
        audit['blocks'] = [{'id': b['id'], 'supported': True, 'reason': 'Synthetic fixture only',
                            'verdict': 'grounded_question' if b['kind'] == 'analysis' else 'evidence_supported',
                            'unsupported_claims': []} for b in blocks(article)]
        self.assertEqual(validate_article(article, facts, [item], audit, 90),
                         {'evidence': [], 'editorial': [], 'originality': []})
        self.assertEqual(article, before)
        article['paragraphs'][0]['text'] = 'Kort text.'
        article['paragraphs'] = article['paragraphs'][:1]
        self.assertIn('word_count_outside_150_400', article_preflight(article, facts, [item], 90)['errors'])
        tampered = copy.deepcopy(facts)
        cargo = next(f for f in tampered if f.get('technical_field') == 'cargo')
        cargo['statement'] = cargo['statement'].replace('1250', '1450')
        self.assertIn('invalid_technical_scope:' + cargo['id'], validate_article(before, tampered, [item], None, 90)['evidence'])


class PersonalQuestionReviewTests(unittest.TestCase):
    def test_review_packet_separates_requested_personal_needs_from_hidden_factual_premises(self):
        facts = [{'id': 'range', 'statement': 'Räckvidden är 450 km enligt WLTP.', 'evidence': 'The actual supplied evidence.'}]
        for example in BUYER_QUESTION_CALIBRATION:
            with self.subTest(text=example['text']):
                article = {'paragraphs': [{'text': example['text'], 'kind': 'analysis', 'fact_ids': ['range']}]}
                ai = Mock(return_value={'facts': {}, 'blocks': {}})
                audit_article(article, facts, ai)
                packet = json.loads(ai.call_args.args[2].split('\n')[-1])
                self.assertEqual(packet['buyer_question_examples_not_evidence'], BUYER_QUESTION_CALIBRATION)
                question = packet['blocks'][-1]
                self.assertEqual(question['permitted_statements'], [facts[0]['statement']])
                self.assertEqual(question['question_review']['anchor_topics'], ['range'])
                self.assertIn('no automatic acceptance', question['question_review']['check'])
                self.assertEqual(packet['facts'], facts)

    def test_negative_semantic_verdict_is_never_overridden_for_a_question(self):
        facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
        article = fixtures.draft()
        audit = fixtures.audit(facts)
        audit['blocks'][-1].update(supported=False, verdict='unsupported_claim', unsupported_claims=['A factual promise'])
        audit['no_unsupported_claims'] = False
        returned = audit_article(article, facts, Mock(return_value=fixtures.keyed_audit(audit)))
        self.assertFalse(returned['blocks'][-1]['supported'])
        self.assertIn('block_audit_failed_or_incomplete', validate_article(article, facts, [fixtures.item()], returned, 90)['evidence'])


class LengthTrialTests(unittest.TestCase):
    def test_trial_has_lower_cap_one_case_no_rewrite_and_no_parent_reset(self):
        keys = ['RECIPE', 'TRIAL_ID', 'DATABASE', 'OUTPUT', 'MAX_MICRO_USD', 'MAX_REQUESTS',
                'REEXTRACT_MODEL', 'MODEL_INPUT', 'INCLUDE_MARKET', 'MAX_REVISIONS']
        original = {k: getattr(matrix, k) for k in keys}
        with patch.multiple(matrix, **original):
            r21.configure()
            self.assertEqual(matrix.MAX_MICRO_USD, 40000)
            self.assertEqual(matrix.MAX_REQUESTS, 3)
            self.assertEqual(matrix.MAX_REVISIONS, 0)
            self.assertFalse(matrix.INCLUDE_MARKET)
            self.assertFalse(matrix.REEXTRACT_MODEL)
            self.assertEqual(matrix.MODEL_INPUT, r21.model_input)
            self.assertNotEqual(matrix.TRIAL_ID, r21.PARENT_ID)
            self.assertNotEqual(matrix.DATABASE, r21.PARENT_DATABASE)

    def test_parent_extraction_is_read_only_and_invalid_old_scores_cannot_be_inherited(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'parent.sqlite'
            item = fixtures.item(matrix.MODEL_ITEM)
            item['payload']['extraction'] = fixtures.extraction()
            with closing(NewsStore(path)) as store:
                store.put('news_items', item)
            parent = {'state': 'completed', 'owner_shutdown_verified': True, 'production_unchanged': True,
                      'recipe': 'news-editorial-recipe-2026-10-r20',
                      'cases': [{'id': item['id'], 'content_hash': item['payload']['content_hash']}]}
            remote = Mock()
            remote.get.return_value = {'payload': parent}
            before = path.read_bytes()
            with patch.object(r21, 'PARENT_DATABASE', path):
                self.assertEqual(r21.model_input(remote)['payload'], item['payload'])
                self.assertEqual(path.read_bytes(), before)
                parent['owner_shutdown_verified'] = False
                with self.assertRaises(NewsBudgetBlocked):
                    r21.model_input(remote)
                parent['owner_shutdown_verified'] = True
                item['payload']['extraction']['sweden_relevance'] = 8.6
                with closing(NewsStore(path)) as store:
                    store.put('news_items', item)
                with self.assertRaisesRegex(ValueError, 'invalid_parent_extraction'):
                    r21.model_input(remote)
            remote.put.assert_not_called()


if __name__ == '__main__':
    unittest.main()
