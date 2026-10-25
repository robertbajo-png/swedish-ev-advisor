"""Offline evidence/syntax/schema regressions; mocked decisions are not LLM accuracy."""
import copy
import json
import re
import sys
import unittest
import os
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
import test_news_length as length
import trial_news_matrix as matrix
import trial_news_evidence_r22 as r22
from news_ai import NewsBudgetBlocked
from news_editorial import (AUDIT_SCHEMA, obj, article_preflight, audit_article, blocks, generate_article,
                            source_qualifier_facts, source_overlaps, validate_article)
from news_fact_brief import neutral_facts, source_technical_facts, technical_evidence, writing_card


class EvidenceWindowTests(unittest.TestCase):
    def test_short_ac_quote_uses_complete_fields_not_r21_trailing_fragment(self):
        item, facts = length.source()
        before = copy.deepcopy(item)
        field = next(f for f in source_technical_facts(item, facts) if f['technical_field'] == 'ac_power')
        self.assertEqual(field['field_evidence'], 'AC-laddningskapacitet (max.): 11 kW')
        self.assertEqual(field['evidence'], 'Laddningstid DC, 10-80 %: ca 24 minuter AC-laddningskapacitet (max.): 11 kW')
        self.assertIn(field['evidence'], item['payload']['content'])
        self.assertNotIn('%: ca 24 minuter AC', field['evidence'].split('Laddningstid')[0])
        self.assertEqual(item, before)

    def test_whole_sufficient_field_needs_no_unrelated_context(self):
        item, facts = length.source()
        for field in source_technical_facts(item, facts):
            self.assertTrue(8 <= len(field['evidence'].split()) <= 24)
            self.assertIn(field['field_evidence'], field['evidence'])
            if field['technical_field'] != 'ac_power':
                self.assertEqual(field['field_evidence'], field['evidence'])

    def test_short_or_unrecognized_context_cannot_be_padded_or_reordered(self):
        field = 'AC-laddningskapacitet (max.): 11 kW'
        pattern = re.compile(re.escape(field))
        self.assertIsNone(technical_evidence(field, pattern.search(field)))
        unknown = 'Unrecognized words before the incomplete field label ' + field
        self.assertIsNone(technical_evidence(unknown, pattern.search(unknown)))
        too_long = 'Drivsystem: ' + 'explicit ' * 30 + field
        self.assertIsNone(technical_evidence(too_long, pattern.search(too_long)))

    def test_altered_field_quote_fails_rederivation_even_with_valid_source_hash(self):
        item, initial = length.source()
        facts = neutral_facts(initial + source_technical_facts(item, initial) + source_qualifier_facts(item))
        field = next(f for f in facts if f.get('technical_field') == 'ac_power')
        field['field_evidence'] = field['field_evidence'].replace('11 kW', '22 kW')
        errors = validate_article(fixtures.draft(), facts, [item], None, 90)['evidence']
        self.assertIn('invalid_technical_scope:' + field['id'], errors)


class IndependentSyntaxTests(unittest.TestCase):
    def test_actual_sentence_forms_become_lossless_data_not_source_syntax(self):
        card = writing_card('Batteriet på 48 kWh ger en räckvidd på upp till 360 km enligt WLTP')
        self.assertEqual(card, {'battery': {'kwh': '48', 'capacity_basis': 'not_stated'},
                                'range': {'km': '360', 'limit': 'up_to', 'measurement': 'WLTP'}})
        charge = writing_card('DC-snabbladdning sker med 100 kW från 10 till 80 procent på cirka 24 minuter')
        self.assertEqual(charge['charging']['duration_minutes'], '24')
        self.assertEqual(charge['charging']['power_basis'], 'stated_not_explicit_maximum')
        self.assertEqual(writing_card('AC-laddningskapaciteten är som mest 11 kW')['charging'],
                         {'current': 'AC', 'power_kw': '11', 'power_basis': 'explicit_maximum'})
        for extra in [' endast i Tyskland', ' med förvärmt batteri', ' beroende på hjulstorlek']:
            text = 'Batteriet på 48 kWh ger en räckvidd på upp till 360 km enligt WLTP' + extra
            self.assertEqual(writing_card(text), {'statement': text})

    def test_copied_range_and_charge_stay_blocked_independent_reference_passes(self):
        item, initial = length.source()
        facts = neutral_facts(initial + source_technical_facts(item, initial) + source_qualifier_facts(item))
        output = length.brief.reference_output(facts)
        output['paragraphs'].pop(4)
        output['paragraphs'].append('Bakom baksätet är volymen 460 liter. Frunken rymmer separat 22 liter. '
                                    'När baksätets ryggstöd är fällt anges bagageutrymmet till 1 250 liter.')
        article = generate_article(facts, Mock(return_value=output))
        self.assertEqual(article_preflight(article, facts, [item], 90)['errors'], [])
        changed = copy.deepcopy(article)
        changed['paragraphs'][0]['text'] = length.brief.STATEMENTS[1]
        changed['paragraphs'][2]['text'] = length.brief.STATEMENTS[3]
        self.assertEqual({m['block_id'] for m in source_overlaps(changed, [item], limit=32, per_block_limit=1)}, {'p0', 'p2'})
        self.assertIn('source_wording_overlap:' + item['id'], article_preflight(changed, facts, [item], 90)['errors'])


class ReusableAuditSchemaTests(unittest.TestCase):
    def test_budget_probe_uses_real_serialization_without_a_reservation_or_provider(self):
        facts = fixtures.extraction()['facts']
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'unit-test-placeholder'}):
            result = r22.budget_probe(facts, fixtures.draft())
        self.assertEqual(set(result), {'swedish_ev_article', 'ev_news_independent_audit'})
        self.assertTrue(all(type(value) is int and value > 0 for value in result.values()))

    def test_references_expand_to_identical_required_rejection_and_acceptance_contracts(self):
        article = fixtures.draft()
        ai = Mock(return_value=fixtures.keyed_audit(fixtures.audit()))
        audit_article(article, fixtures.extraction()['facts'], ai)
        schema = ai.call_args.args[1]
        def expand(node):
            if isinstance(node, list):
                return [expand(child) for child in node]
            if not isinstance(node, dict):
                return node
            if '$ref' in node:
                return expand(schema['$defs'][node['$ref'].split('/')[-1]])
            return {key: expand(value) for key, value in node.items() if key != '$defs'}
        resolved = expand(schema)
        fact = {key: val for key, val in AUDIT_SCHEMA['properties']['facts']['items']['properties'].items() if key != 'id'}
        self.assertTrue(all(value == obj(fact) for value in resolved['properties']['facts']['properties'].values()))
        for block in blocks(article):
            accepted, rejected = resolved['properties']['blocks']['properties'][block['id']]['anyOf']
            expected = 'grounded_question' if block['kind'] == 'analysis' else 'evidence_supported'
            self.assertEqual(accepted['properties']['verdict']['enum'], [expected])
            self.assertEqual(accepted['properties']['supported']['enum'], [True])
            self.assertEqual(accepted['properties']['unsupported_claims']['maxItems'], 0)
            self.assertEqual(rejected['properties']['supported']['enum'], [False])
            self.assertEqual(rejected['properties']['unsupported_claims']['minItems'], 1)
            self.assertEqual(set(accepted['required']), set(rejected['required']))
        packet = json.loads(ai.call_args.args[2].split('\n')[-1])
        self.assertEqual(packet['facts'], fixtures.extraction()['facts'])

    def test_schema_size_reduction_does_not_drop_per_id_required_decisions(self):
        facts = [{'id': 'source:f' + str(n), 'statement': 'A supplied fact.', 'evidence': 'Its literal evidence.'} for n in range(12)]
        article = {'paragraphs': [{'text': 'Test prose.', 'kind': 'reporting', 'fact_ids': [f['id']]} for f in facts]}
        ai = Mock(return_value={'facts': {}, 'blocks': {}})
        audit_article(article, facts, ai)
        schema = ai.call_args.args[1]
        self.assertEqual(set(schema['properties']['facts']['required']), {f['id'] for f in facts})
        self.assertEqual(len(schema['properties']['blocks']['required']), 14)
        self.assertLess(len(json.dumps(schema)), 6000)

    def test_r22_cap_and_retry_do_not_reset_old_trial_or_raise_shared_limits(self):
        keys = ['RECIPE', 'TRIAL_ID', 'DATABASE', 'OUTPUT', 'MAX_MICRO_USD', 'MAX_REQUESTS',
                'REEXTRACT_MODEL', 'MODEL_INPUT', 'INCLUDE_MARKET', 'MAX_REVISIONS']
        with patch.multiple(matrix, **{key: getattr(matrix, key) for key in keys}):
            r22.configure()
            self.assertEqual(matrix.MAX_MICRO_USD, 24000)
            self.assertEqual(matrix.MAX_REQUESTS, 3)
            self.assertEqual(matrix.MAX_REVISIONS, 1)
            self.assertFalse(matrix.INCLUDE_MARKET)
            self.assertFalse(matrix.REEXTRACT_MODEL)
            self.assertNotEqual(matrix.TRIAL_ID, length.r21.PARENT_ID)
        remote = Mock()
        remote.get.return_value = {'payload': {'state': 'completed', 'owner_shutdown_verified': False}}
        with self.assertRaises(NewsBudgetBlocked):
            r22.model_input(remote)
        remote.put.assert_not_called()


if __name__ == '__main__':
    unittest.main()
