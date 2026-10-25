"""Offline synthetic stories: source binding tests, not claims of live editorial quality."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_editorial import (build_fact_plan, generate_article, writer_schema, fact_plan_errors,
                            claim_scope_errors, validate_article, blocks, repair_source_wording)
from news_fact_plan import planned_bindings


STORIES = {
    'model_launch': [
        'Testbil öppnar förförsäljningen av en ny modell i Sverige.',
        'Modellen lanseras på den svenska marknaden under november.',
        'Batteriet rymmer 60 kWh och WLTP-räckvidden är 450 km.',
        'DC-snabbladdning erbjuds med en effekt på 120 kW.',
        'Bagageutrymmet i den nya modellen rymmer 500 liter.',
        'Parkeringssensorer ingår i utrustningen för den aktuella versionen.'],
    'price_change': [
        'Det svenska priset för Testbil sänks till 450000 kronor.',
        'Det nya priset gäller enbart den bakhjulsdrivna versionen.',
        'WLTP-räckvidden för denna version är angiven till 480 km.',
        'Batteriets kapacitet för den aktuella versionen är 70 kWh.',
        'Snabbladdning stöds med en effekt på högst 150 kW.',
        'Bagageutrymmet rymmer 490 liter med de bakre sätena uppfällda.'],
    'battery_technology': [
        'Tillverkaren presenterar en ny batterikonstruktion för europeiska elbilar.',
        'Den nya konstruktionen har en kapacitet på 80 kWh.',
        'Cellernas energitäthet anges i underlaget till 250 Wh per kg.',
        'Den nya fabriken ligger enligt företaget i norra Tyskland.',
        'Företaget avser att börja tillverka cellerna under nästa år.',
        'Laddtiden för det visade batteriet uppges vara 25 minuter.'],
    'charging_network': [
        'Operatören presenterar en utbyggnad av laddstationer i södra Sverige.',
        'Utbyggnaden omfattar enligt operatören sammanlagt 40 nya laddpunkter.',
        'DC-snabbladdning ska erbjudas med en effekt på 300 kW.',
        'Anläggningarna kommer enligt underlaget att ha kontaktlös kortbetalning.',
        'De nya laddpunkterna placeras på fem redan befintliga rastplatser.',
        'De fem platserna ligger längs två större svenska huvudvägar.'],
    'winter_test': [
        'Testorganisationen presenterar resultaten från sitt vintertest av Testbil.',
        'Den uppmätta räckvidden under vintertestet var 320 kilometer.',
        'Temperaturen vid starten av testet var minus 10 grader.',
        'Bilens officiella WLTP-räckvidd är angiven till 450 kilometer.',
        'Förbrukningen under det redovisade testet var 23 kWh per 100 km.',
        'Den aktuella testbilen hade enligt protokollet dubbfria vinterdäck.'],
    'market_statistics': [
        'Branschorganisationen presenterar statistik över svenska nyregistreringar för september.',
        'Antalet nya registrerade elbilar under månaden uppgick till 12000.',
        'Elbilarnas andel av nyregistreringarna under samma månad var 40 procent.',
        'Statistiken avser nya personbilar registrerade på den svenska marknaden.',
        'Organisationen redovisar antalet nyregistrerade laddhybrider som en separat kategori.',
        'Sammanställningen bygger på registreringar under månadens samtliga kalenderdagar.'],
    'software_update': [
        'Tillverkaren presenterar en programuppdatering för europeiska versioner av Testbil.',
        'Uppdateringen ändrar visningen av laddstationer i bilens navigationssystem.',
        'Navigationssystemet visar stationernas öppettider när sådana uppgifter finns tillgängliga.',
        'Den nya programversionen har enligt tillverkaren beteckningen 3.2.',
        'Installationen sker genom bilens befintliga trådlösa uppdateringsfunktion.',
        'Bilen måste stå parkerad under den aktuella installationen.'],
    'recall': [
        'Tillverkaren presenterar en återkallelse av en begränsad serie Testbil.',
        'Återkallelsen omfattar enligt företaget totalt 1200 bilar i Europa.',
        'Felet gäller enligt företaget en kontakt i bilens laddsystem.',
        'Berörda ägare ska enligt företaget få ett brev med instruktioner.',
        'Åtgärden genomförs enligt underlaget på tillverkarens auktoriserade verkstäder.',
        'Tillverkaren uppger att den beskrivna åtgärden inte kostar ägaren något.'],
}


def facts_for(key):
    return [{'id': key + ':f' + str(n), 'statement': text, 'evidence': text,
             'item_id': 'source-' + key, 'central': True}
            for n, text in enumerate(STORIES[key])]


def response_for(plan):
    return {'title': plan['title']['statements'][0], 'intro': ' '.join(plan['intro']['statements']),
            'paragraphs': [' '.join(slot['statements']) for slot in plan['paragraphs']],
            'source_context': {slot['key']: ' '.join(slot['statements']) for slot in plan['source_context']},
            'buyer_question': 'Hur passar den uppgiften med dina egna behov?'}


class NewsFactPlanTests(unittest.TestCase):
    def test_unique_same_source_range_qualifier_has_one_preplanned_home(self):
        facts = facts_for('model_launch')
        facts.append({'id': 'q-range', 'statement': 'Den angivna WLTP-räckvidden varierar med utrustningen.',
                      'evidence': 'A literal source condition about range and equipment.',
                      'item_id': facts[2]['item_id'], 'origin': 'literal_source_qualifier', 'qualification_topic': 'range'})
        original = copy.deepcopy(facts)
        plan = build_fact_plan(facts)
        target = next(slot for slot in plan['paragraphs'] if facts[2]['id'] in slot['fact_ids'])
        self.assertEqual(target['fact_ids'], [facts[2]['id'], 'q-range'])
        self.assertFalse(plan['source_context'])
        self.assertEqual(sum('q-range' in ids for ids in planned_bindings(plan).values()), 1)
        article = generate_article(facts, Mock(return_value=response_for(plan)))
        self.assertEqual(claim_scope_errors(article, facts), [])
        self.assertEqual(facts, original)

    def test_other_source_or_ambiguous_range_qualifier_is_not_borrowed(self):
        for other_source in [True, False]:
            facts = facts_for('model_launch')
            if not other_source:
                facts.append({**facts[2], 'id': 'second-variant', 'statement': 'En annan variants WLTP-räckvidd är 520 km.'})
            facts.append({'id': 'q', 'statement': 'WLTP-räckvidden varierar med utrustningen.', 'evidence': 'Source qualification.',
                          'item_id': 'other' if other_source else facts[2]['item_id'],
                          'origin': 'literal_source_qualifier', 'qualification_topic': 'range'})
            plan = build_fact_plan(facts)
            self.assertEqual(plan['source_context'][0]['fact_ids'], ['q'])
            self.assertTrue(all('q' not in slot['fact_ids'] for slot in plan['paragraphs']))

    def test_small_brief_qualifier_never_mutates_intro_or_input(self):
        facts = facts_for('model_launch')[:3]
        facts.append({'id': 'q', 'statement': 'WLTP-räckvidden varierar med utrustningen.', 'evidence': 'Source qualification.',
                      'item_id': facts[2]['item_id'], 'origin': 'literal_source_qualifier', 'qualification_topic': 'range'})
        original = copy.deepcopy(facts)
        plan = build_fact_plan(facts)
        self.assertNotIn('q', plan['intro']['fact_ids'])
        self.assertIn('q', plan['paragraphs'][0]['fact_ids'])
        self.assertEqual(facts, original)

    def test_small_shared_paragraph_with_two_variants_is_still_ambiguous(self):
        facts = [facts_for('model_launch')[2]]
        facts.append({**facts[0], 'id': 'other-range', 'statement': 'Den andra versionens WLTP-räckvidd är 520 km.'})
        facts.append({'id': 'q', 'statement': 'WLTP-räckvidden varierar med utrustningen.', 'evidence': 'Source qualification.',
                      'item_id': facts[0]['item_id'], 'origin': 'literal_source_qualifier', 'qualification_topic': 'range'})
        plan = build_fact_plan(facts)
        self.assertEqual(plan['source_context'][0]['fact_ids'], ['q'])
        self.assertNotIn('q', plan['paragraphs'][0]['fact_ids'])

    def test_eight_story_types_have_complete_deterministic_source_bindings(self):
        for key in STORIES:
            with self.subTest(story=key):
                facts = facts_for(key)
                original = copy.deepcopy(facts)
                plan = build_fact_plan(facts)
                ai = Mock(return_value=response_for(plan))
                article = generate_article(facts, ai)
                self.assertEqual(fact_plan_errors(article, facts), [])
                self.assertEqual(claim_scope_errors(article, facts), [])
                self.assertEqual({b['id']: b['fact_ids'] for b in blocks(article)}, planned_bindings(plan))
                covered = {key for ids in planned_bindings(plan).values() for key in ids}
                self.assertEqual(covered, {f['id'] for f in facts})
                self.assertEqual(plan, build_fact_plan(copy.deepcopy(facts)))
                self.assertEqual(facts, original)
                self.assertNotIn('citations', ai.call_args.args[1]['properties'])

    def test_wrong_title_or_borrowed_citation_fails_every_story(self):
        for key in STORIES:
            with self.subTest(story=key):
                facts = facts_for(key)
                article = generate_article(facts, Mock(return_value=response_for(build_fact_plan(facts))))
                article['title_fact_ids'] = [facts[-1]['id']]
                self.assertIn('fact_plan_citation_mismatch', fact_plan_errors(article, facts))
                article['fact_plan_hash'] = 'changed'
                self.assertIn('fact_plan_hash_mismatch', fact_plan_errors(article, facts))

    def test_order_opening_launch_and_delivery_are_distinct_events(self):
        facts = facts_for('model_launch')
        for text, fact, expected in [
            ('Testbil öppnar för beställningar i Sverige.', facts[1], 'order_open'),
            ('Testbil lanseras i Sverige.', facts[0], 'market_launch'),
            ('Leveranser av Testbil börjar nu.', facts[0], 'deliveries')]:
            article = {'title': text, 'title_fact_ids': [fact['id']]}
            self.assertIn('claim_event_mismatch:title:' + expected, claim_scope_errors(article, facts))
        plan = build_fact_plan(facts)
        self.assertEqual(plan['title']['fact_ids'], [facts[0]['id']])
        self.assertNotIn(facts[1]['id'], plan['title']['fact_ids'])

    def test_plan_changes_when_fact_or_source_evidence_changes(self):
        facts = facts_for('winter_test')
        original = build_fact_plan(facts)['hash']
        for field in ['statement', 'evidence', 'item_id']:
            changed = copy.deepcopy(facts)
            changed[0][field] += ' changed'
            self.assertNotEqual(build_fact_plan(changed)['hash'], original)

    def test_empty_duplicate_or_whitespace_facts_never_call_the_writer(self):
        for facts in [[], [{'id': 'f', 'statement': '  '}],
                      [{'id': 'f', 'statement': 'Fact'}, {'id': 'f', 'statement': 'Other fact'}]]:
            ai = Mock()
            with self.assertRaises(ValueError):
                generate_article(facts, ai)
            ai.assert_not_called()

    def test_writer_cannot_add_source_ids_fields_or_unplanned_paragraphs(self):
        facts = facts_for('price_change')
        response = response_for(build_fact_plan(facts))
        for bad in [{**response, 'title_fact_ids': ['invented']},
                    {**response, 'paragraphs': response['paragraphs'] + ['Extra uncited reporting.']}]:
            with self.assertRaises(ValueError):
                generate_article(facts, Mock(return_value=bad))

    def test_changed_plan_roles_or_omitted_block_remain_blocked(self):
        facts = facts_for('charging_network')
        article = generate_article(facts, Mock(return_value=response_for(build_fact_plan(facts))))
        article['paragraphs'][-1]['kind'] = 'reporting'
        self.assertIn('fact_plan_role_mismatch', fact_plan_errors(article, facts))
        article['paragraphs'].pop(0)
        self.assertIn('fact_plan_citation_mismatch', fact_plan_errors(article, facts))

    def test_passing_audit_cannot_override_changed_plan_bindings(self):
        facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
        article = generate_article(facts, Mock(return_value=fixtures.writer_result(fixtures.draft())))
        article['title_fact_ids'] = ['f2']
        checks = validate_article(article, facts, [fixtures.item()], fixtures.audit(), 90)
        self.assertIn('fact_plan_citation_mismatch', checks['evidence'])

    def test_wording_repair_keeps_the_plan_hash_and_all_source_bindings(self):
        facts = facts_for('market_statistics')
        article = generate_article(facts, Mock(return_value=response_for(build_fact_plan(facts))))
        revised = repair_source_wording(article, facts, [{'block_id': 'p0'}],
                                        Mock(return_value={'p0': 'Antalet redovisas för den aktuella månaden.'}))
        self.assertEqual(revised['fact_plan_hash'], article['fact_plan_hash'])
        self.assertEqual(fact_plan_errors(revised, facts), [])

    def test_evidence_and_provenance_are_not_exposed_in_the_writer_plan(self):
        facts = facts_for('battery_technology')
        facts[0]['evidence'] = 'PRIVATE_EVIDENCE_MARKER'
        ai = Mock(return_value=response_for(build_fact_plan(facts)))
        generate_article(facts, ai)
        prompt = ai.call_args.args[2]
        plan = json.loads(prompt.split('\nFACT_PLAN:\n')[1])
        self.assertNotIn('provenance', plan)
        self.assertNotIn('PRIVATE_EVIDENCE_MARKER', prompt)


if __name__ == '__main__':
    unittest.main()
