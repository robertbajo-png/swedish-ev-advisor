"""Synthetic offline evidence; reference prose is a test fixture, never production output."""
import copy
import hashlib
import json
import sys
import unittest
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_fact_brief import neutral_facts, source_technical_facts, writing_card, writer_plan
from news_editorial import (article_preflight, audit_article, blocks, build_fact_plan, fact_plan_errors,
                            generate_article, source_qualifier_facts, validate_article)
from news_engine import attach_cluster, editorial
from news_store import NewsStore

STATEMENTS = [
    'Tillverkaren inleder nu förförsäljningen av nya Testbil E1 med ett batteri på 48 kWh',
    'Batteriet på 48 kWh (netto) ger en räckvidd på upp till 360 km (WLTP)',
    'Två effektnivåer erbjuds: 130 hk (96 kW) och 160 hk (118 kW)',
    'DC-snabbladdning med 100 kW från 10 till 80 procent på cirka 24 minuter',
    'Nya Testbil E1 lanseras på den svenska marknaden vid månadsskiftet november/december',
    'Redan instegsversionen Trend har en omfattande standardutrustning, däribland parkeringssensorer fram och bak samt smartphoneintegrering via App Connect',
    'Bagageutrymmesvolym: 460 liter + 22 liter frunk',
]
CONTEXT = [
    'De faktiska WLTP-värdena för räckvidd kan variera beroende på utrustning.',
    'Tiden tills batteriet är fulladdat beror på laddinfrastrukturens effekt vid AC- och DC-laddning samt på batteriets laddningsnivå och utomhustemperaturen.',
]
TECHNICAL = ('Tekniska data för Testbil E1 med 48 kWh-batteriet '
             'Drivsystem: framhjulsdrift Laddningstid DC, 10-80 %: ca 24 minuter '
             'AC-laddningskapacitet (max.): 11 kW Topphastighet: 150 km/h '
             'Max. släpvagnsvikt: 900 kg (bromsat, både 8 % och 12 % lutning) '
             'Tjänstevikt: 1800 kg Räckvidden har fastställts enligt WLTP.')


def source_and_facts():
    item = fixtures.item()
    item['payload']['content'] = ' '.join(text.rstrip('.') + '.' for text in STATEMENTS + CONTEXT) + ' ' + TECHNICAL
    item['payload']['content_hash'] = hashlib.sha256(item['payload']['content'].encode()).hexdigest()
    facts = [{'id': 'f' + str(n), 'statement': text, 'evidence': text, 'item_id': item['id'], 'central': True}
             for n, text in enumerate(STATEMENTS)]
    facts[6]['evidence'] = STATEMENTS[6] + '. ' + CONTEXT[0]
    return item, facts


def reference_output(facts):
    plan = build_fact_plan(facts)
    return {'title': 'Förhandsbeställningen öppnar för Testbil E1',
            'intro': 'Nu går det att lägga en förhandsbeställning på Testbil E1. För Sverige är lanseringen planerad till övergången mellan november och december.',
            'paragraphs': [
                'Nettoinnehållet i batteriet är 48 kWh. För räckvidden anges högst 360 km, uppmätt enligt WLTP. Vald utrustning kan påverka WLTP-resultatet.',
                'Versionerna har olika motoreffekt. Det ena alternativet ger 96 kW, eller 130 hk. Det andra ger 118 kW, motsvarande 160 hk.',
                'Att höja laddningsnivån från 10 till 80 procent tar ungefär 24 minuter. Uppgiften gäller DC-laddning med 100 kW.',
                'Trend är instegsversionen. Sensorer för parkering finns både baktill och framtill. Smartphoneintegrering genom App Connect ingår också som standard.',
                'Lastvolymen är uppdelad mellan två utrymmen: bagaget rymmer 460 liter och frunken ytterligare 22 liter.',
                'För AC-laddning är den angivna övre effektgränsen 11 kW.',
                'Med bromsat släp är viktgränsen 900 kg. Gränsen gäller vid såväl 8 som 12 procents lutning.',
            ],
            'source_context': {slot['key']: 'Laddningsnivån, temperaturen utomhus och laddinfrastrukturens effekt påverkar tiden till fullt batteri. Detta gäller vid både AC och DC.'
                               for slot in plan['source_context']},
            'buyer_question': 'Hur långt behöver du kunna köra mellan dina laddstopp?'}


class NewsFactBriefTests(unittest.TestCase):
    def test_neutralization_keeps_features_and_original_provenance_without_mutation(self):
        _, facts = source_and_facts()
        original = copy.deepcopy(facts)
        cleaned = neutral_facts(facts)
        self.assertNotIn('omfattande', cleaned[5]['statement'])
        self.assertIn('parkeringssensorer fram och bak', cleaned[5]['statement'])
        self.assertEqual(cleaned[5]['source_statement'], original[5]['statement'])
        self.assertEqual(cleaned[5]['evidence'], original[5]['evidence'])
        self.assertEqual(facts, original)
        self.assertEqual(neutral_facts(cleaned), cleaned)

    def test_qualifiers_and_unrecognized_statements_are_not_summarized_or_stripped(self):
        for statement in ['Batteriet är större än förra årets version.',
                          'Batteriet på 48 kWh (brutto) ger en räckvidd på upp till 360 km (WLTP)',
                          STATEMENTS[1] + ' endast i Tyskland',
                          STATEMENTS[3] + ' med förvärmt batteri']:
            self.assertEqual(writing_card(statement), {'statement': statement})
            self.assertEqual(neutral_facts([{'id': 'f', 'statement': statement}])[0]['statement'], statement)

    def test_numeric_cards_keep_pairings_units_and_measurement_qualifications(self):
        self.assertEqual(writing_card(STATEMENTS[1])['range'], {'km': '360', 'limit': 'up_to', 'measurement': 'WLTP'})
        self.assertEqual(writing_card(STATEMENTS[1])['battery']['capacity_basis'], 'net')
        self.assertEqual(writing_card(STATEMENTS[2])['motor_power_options'],
                         [{'hk': '130', 'kw': '96'}, {'hk': '160', 'kw': '118'}])
        self.assertEqual(writing_card(STATEMENTS[3])['charging'],
                         {'current': 'DC', 'power_kw': '100', 'from_percent': '10', 'to_percent': '80',
                          'duration_minutes': '24', 'duration_basis': 'approximate',
                          'power_basis': 'stated_not_explicit_maximum'})

    def test_events_and_conditions_are_data_not_press_release_sentences(self):
        self.assertEqual(writing_card(STATEMENTS[0])['model'], 'Testbil E1')
        self.assertEqual(writing_card(STATEMENTS[4])['timing']['boundary_months'], ['november', 'december'])
        self.assertEqual(writing_card(CONTEXT[0])['qualification']['depends_on'], ['equipment'])
        card = writing_card(CONTEXT[1])['qualification']
        self.assertEqual(card['measurement'], 'time_until_full_charge')
        self.assertEqual(card['current'], ['AC', 'DC'])
        self.assertNotIn('consumption', json.dumps(card))

    def test_two_technical_fields_have_real_continuous_quotes_and_exact_scope(self):
        item, facts = source_and_facts()
        additions = source_technical_facts(item, facts)
        self.assertEqual([f['technical_field'] for f in additions], ['ac_power', 'braked_tow'])
        for fact in additions:
            self.assertIn(fact['evidence'], item['payload']['content'])
            self.assertTrue(8 <= len(fact['evidence'].split()) <= 24)
            self.assertIn(fact['scope_evidence'], item['payload']['content'])
            self.assertEqual(fact['scope'], {'model': 'Testbil E1', 'battery_kwh': '48'})
            self.assertEqual(fact['source_hash'], item['payload']['content_hash'])
        self.assertEqual(source_technical_facts(item, facts + additions), [])

    def test_technical_values_require_primary_accessible_hashed_sources(self):
        item, facts = source_and_facts()
        for field, value in [('source_kind', 'secondary'), ('access_status', 'blocked'), ('content_hash', '')]:
            changed = copy.deepcopy(item)
            changed['payload'][field] = value
            self.assertEqual(source_technical_facts(changed, facts), [])

    def test_other_model_battery_conflicts_and_invalid_units_are_not_borrowed(self):
        item, facts = source_and_facts()
        for before, after in [('Tekniska data för Testbil E1', 'Tekniska data för Annan bil'),
                              ('med 48 kWh-batteriet', 'med 88 kWh-batteriet'),
                              ('11 kW', '11 kWh'), ('900 kg', '9000 kg')]:
            changed = copy.deepcopy(item)
            changed['payload']['content'] = item['payload']['content'].replace(before, after)
            changed['payload']['content_hash'] = hashlib.sha256(changed['payload']['content'].encode()).hexdigest()
            additions = source_technical_facts(changed, facts)
            if 'Annan' in after or '88' in after:
                self.assertEqual(additions, [])
            else:
                self.assertEqual(len(additions), 1)
        changed = copy.deepcopy(item)
        changed['payload']['content'] += ' ' + TECHNICAL
        changed['payload']['content_hash'] = hashlib.sha256(changed['payload']['content'].encode()).hexdigest()
        self.assertEqual(source_technical_facts(changed, facts), [])

    def test_stale_hash_and_missing_model_scope_never_create_additions(self):
        item, facts = source_and_facts()
        item['payload']['content'] += ' An extra source sentence.'
        self.assertEqual(source_technical_facts(item, facts), [])
        item, facts = source_and_facts()
        self.assertEqual(source_technical_facts(item, []), [])
        self.assertEqual(source_technical_facts(item, [{**facts[0], 'item_id': 'another-item'}]), [])

    def test_unrecognized_field_qualifications_and_nested_model_sections_are_not_discarded(self):
        item, facts = source_and_facts()
        for before, after in [('11 kW Topphastighet', '11 kW endast Life Topphastighet'),
                              ('% lutning) Tjänstevikt', '% lutning) endast Life Tjänstevikt')]:
            changed = copy.deepcopy(item)
            changed['payload']['content'] = changed['payload']['content'].replace(before, after)
            changed['payload']['content_hash'] = hashlib.sha256(changed['payload']['content'].encode()).hexdigest()
            self.assertEqual(len(source_technical_facts(changed, facts)), 1)
        item['payload']['content'] = item['payload']['content'].replace('AC-laddningskapacitet',
            'Tekniska data för Annan bil med 80 kWh-batteriet AC-laddningskapacitet')
        item['payload']['content_hash'] = hashlib.sha256(item['payload']['content'].encode()).hexdigest()
        self.assertEqual(source_technical_facts(item, facts), [])

    def test_numeric_maximum_is_not_an_invented_comparison_and_marketing_is_blocked(self):
        item, facts = source_and_facts()
        facts += source_technical_facts(item, facts) + source_qualifier_facts(item)
        facts = neutral_facts(facts)
        article = generate_article(facts, Mock(return_value=reference_output(facts)))
        self.assertFalse(any(error.startswith('unverified_comparison:') for error in article_preflight(article, facts, [item], 90)['errors']))
        article['paragraphs'][3]['text'] += ' Den har rik standardutrustning.'
        self.assertIn('promotional_equipment_framing:p3', article_preflight(article, facts, [item], 90)['errors'])

    def test_duplicate_or_conflicting_fields_and_missing_braking_scope_are_rejected(self):
        item, facts = source_and_facts()
        for insertion in ['AC-laddningskapacitet (max.): 22 kW ', 'AC-laddningskapacitet (max.): 11 kW ']:
            changed = copy.deepcopy(item)
            changed['payload']['content'] = changed['payload']['content'].replace('Topphastighet:', insertion + 'Topphastighet:')
            changed['payload']['content_hash'] = hashlib.sha256(changed['payload']['content'].encode()).hexdigest()
            self.assertEqual([f['technical_field'] for f in source_technical_facts(changed, facts)], ['braked_tow'])
        item['payload']['content'] = item['payload']['content'].replace('bromsat, både 8 % och 12 % lutning', 'obromsat')
        item['payload']['content_hash'] = hashlib.sha256(item['payload']['content'].encode()).hexdigest()
        self.assertEqual([f['technical_field'] for f in source_technical_facts(item, facts)], ['ac_power'])

    def test_removed_scope_or_changed_source_hash_cannot_pass_final_validation(self):
        item, facts = source_and_facts()
        addition = source_technical_facts(item, facts)[0]
        for key, value in [('scope_evidence', 'Not in the source'), ('source_hash', 'changed')]:
            changed = {**addition, key: value}
            checks = validate_article(fixtures.draft(), [changed], [item], fixtures.audit([changed]), 90)
            self.assertIn('invalid_technical_scope:' + changed['id'], checks['evidence'])

    def test_offline_reference_is_long_enough_without_repeated_facts_or_process_filler(self):
        item, facts = source_and_facts()
        facts += source_technical_facts(item, facts) + source_qualifier_facts(item)
        facts = neutral_facts(facts)
        output = reference_output(facts)
        article = generate_article(facts, Mock(return_value=output))
        preflight = article_preflight(article, facts, [item], 90)
        self.assertEqual(preflight['errors'], [])
        self.assertTrue(150 <= preflight['word_count'] <= 220)
        self.assertEqual(fact_plan_errors(article, facts), [])
        audit = fixtures.audit(facts)
        audit['blocks'] = [{'id': b['id'], 'supported': True, 'reason': 'Offline fixture only', 'unsupported_claims': [],
                            'verdict': 'grounded_question' if b['kind'] == 'analysis' else 'evidence_supported'} for b in blocks(article)]
        self.assertEqual(validate_article(article, facts, [item], audit, 90), {'evidence': [], 'editorial': [], 'originality': []})

    def test_writer_does_not_receive_raw_marketing_or_private_source_evidence(self):
        item, facts = source_and_facts()
        facts += source_technical_facts(item, facts) + source_qualifier_facts(item)
        facts = neutral_facts(facts)
        ai = Mock(return_value=reference_output(facts))
        generate_article(facts, ai)
        prompt = ai.call_args.args[2]
        self.assertNotIn('omfattande standardutrustning', prompt)
        self.assertNotIn('scope_evidence', prompt)
        self.assertNotIn(STATEMENTS[1], prompt)
        self.assertNotIn(STATEMENTS[4], prompt)
        self.assertIn('capacity_basis', prompt)
        self.assertEqual(writer_plan(build_fact_plan(facts))['title']['fact_ids'], ['f0'])

    def test_diagnostic_summary_cannot_override_rejected_blocks(self):
        audit = fixtures.audit()
        audit['blocks'][2].update(supported=False, verdict='unsupported_claim', unsupported_claims=['Unsupported clause'])
        facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
        self.assertIn('block_audit_failed_or_incomplete', validate_article(fixtures.draft(), facts, [fixtures.item()], audit, 90)['evidence'])
        ai = Mock(return_value=fixtures.keyed_audit(audit))
        audit_article(fixtures.draft(), facts, ai)
        self.assertIn('no_unsupported_claims must be false', ai.call_args.args[2])

    def test_engine_uses_identical_curated_facts_for_writing_audit_and_private_receipt(self):
        item, initial = source_and_facts()
        extraction = fixtures.extraction()
        extraction.update(facts=initial, event={**extraction['event'], 'subject': 'Testbil E1'})
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, item, extraction)
            expected = [{**fact, 'id': item['id'] + ':f' + str(n), 'publisher': item['payload']['publisher']}
                        for n, fact in enumerate(initial)]
            expected += source_technical_facts(item, expected) + source_qualifier_facts(item)
            expected = neutral_facts(expected)
            seen = []
            def ai(name, schema, prompt):
                seen.append(name)
                if name == 'swedish_ev_article':
                    return reference_output(expected)
                packet = json.loads(prompt.split('\n')[-1])
                self.assertEqual(packet['facts'], expected)
                audit = fixtures.audit(expected)
                audit['blocks'] = [{'id': b['id'], 'supported': True, 'reason': 'Offline fixture only', 'unsupported_claims': [],
                                    'verdict': 'grounded_question' if b['kind'] == 'analysis' else 'evidence_supported'} for b in packet['blocks']]
                return fixtures.keyed_audit(audit)
            with patch('news_engine.models_for_news', return_value={}):
                result = editorial(store, ai=ai, publish=False)
            self.assertEqual(result[0]['status'], 'validated_draft')
            self.assertEqual(seen, ['swedish_ev_article', 'ev_news_independent_audit'])
            receipt = next(c for c in store.rows('news_quality_checks') if c['kind'] == 'evidence')
            self.assertEqual(receipt['payload']['fact_inventory'], expected)
            self.assertEqual(sum(f.get('origin') == 'literal_technical_field' for f in expected), 2)
            self.assertEqual(store.public_articles(), [])

    def test_scope_and_original_statement_changes_invalidate_the_plan_hash(self):
        item, facts = source_and_facts()
        facts = neutral_facts(facts + source_technical_facts(item, facts))
        original = build_fact_plan(facts)['hash']
        for key in ['scope_evidence', 'source_statement']:
            changed = copy.deepcopy(facts)
            index = -1 if key == 'scope_evidence' else 5
            changed[index][key] += ' changed'
            self.assertNotEqual(build_fact_plan(changed)['hash'], original)


if __name__ == '__main__':
    unittest.main()
