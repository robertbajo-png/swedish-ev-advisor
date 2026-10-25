"""Synthetic offline references, never model responses or publication approval."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_fact_brief as brief
from news_editorial import article_preflight, build_fact_plan, generate_article, source_overlaps, source_qualifier_facts, validate_article
from news_fact_brief import neutral_facts, source_technical_facts, writer_plan, writing_card
from news_store import artifact_hash
from preview_news_equipment_offline import output_directory, revise_reference
from render_news_smoke_preview import render

ACTUAL_FORM = 'Grundversionen Trend har parkeringssensorer fram och bak samt smartphoneintegrering via App Connect'


class EquipmentCardTests(unittest.TestCase):
    def test_actual_statement_is_not_returned_as_a_ready_made_sentence(self):
        card = writing_card(ACTUAL_FORM)
        self.assertEqual(card, {
            'version': {'name': 'Trend', 'role': 'entry_level'}, 'equipment_status': 'stated',
            'equipment_includes': [
                {'function': 'parking_sensors', 'positions': ['front', 'rear']},
                {'function': 'smartphone_integration', 'system': 'App Connect'},
            ]})
        self.assertNotIn('fram och bak samt smartphoneintegrering', json.dumps(card, ensure_ascii=False))

    def test_explicit_standard_status_is_preserved_without_inventing_it(self):
        statement = neutral_facts([{'statement': brief.STATEMENTS[5]}])[0]['statement']
        card = writing_card(statement)
        self.assertEqual(card['equipment_status'], 'standard')
        self.assertEqual(card['equipment_includes'], writing_card(ACTUAL_FORM)['equipment_includes'])
        self.assertNotEqual(writing_card(ACTUAL_FORM)['equipment_status'], 'standard')

    def test_complete_version_name_is_kept_and_combined_versions_are_not_guessed(self):
        card = writing_card(ACTUAL_FORM.replace('Trend', 'Core RWD'))
        self.assertEqual(card['version']['name'], 'Core RWD')
        ambiguous = ACTUAL_FORM.replace('Trend', 'Trend och Life')
        self.assertEqual(writing_card(ambiguous), {'statement': ambiguous})

    def test_unknown_conditions_and_features_are_not_stripped(self):
        for suffix in [' endast i Tyskland', ' mot pristillägg', ' beroende på utrustningspaket',
                       ' samt backkamera', ' trådlöst', ' från årsmodell 2027']:
            for statement in [ACTUAL_FORM, ACTUAL_FORM.replace('har ', 'har som standard bland annat ', 1)]:
                with self.subTest(suffix=suffix, statement=statement):
                    changed = statement + suffix
                    self.assertEqual(writing_card(changed), {'statement': changed})

    def test_unrecognized_sensor_position_or_system_keeps_the_whole_statement(self):
        for before, after in [('fram och bak', 'endast bak'), ('App Connect', 'ett annat system'),
                              ('parkeringssensorer', 'parkeringskamera')]:
            changed = ACTUAL_FORM.replace(before, after)
            self.assertEqual(writing_card(changed), {'statement': changed})

    def test_writer_plan_keeps_fact_bindings_and_leaves_source_facts_untouched(self):
        _, original = brief.source_and_facts()
        original[5]['statement'] = ACTUAL_FORM
        facts = copy.deepcopy(original)
        plan = build_fact_plan(facts)
        writing = writer_plan(plan)
        equipment = next(slot for slot in writing['paragraphs'] if slot['fact_ids'] == ['f5'])
        self.assertEqual(equipment['facts'][0]['equipment_status'], 'stated')
        self.assertNotIn(ACTUAL_FORM, json.dumps(writing, ensure_ascii=False))
        self.assertEqual(facts, original)
        self.assertEqual(plan['hash'], build_fact_plan(facts)['hash'])

    def test_copied_equipment_still_fails_while_independent_reference_passes(self):
        item, initial = brief.source_and_facts()
        initial[5]['statement'] = ACTUAL_FORM
        facts = neutral_facts(initial + source_technical_facts(item, initial) + source_qualifier_facts(item))
        output = brief.reference_output(facts)
        output['paragraphs'][3] = ACTUAL_FORM + '.'
        copied = generate_article(facts, Mock(return_value=output))
        self.assertEqual({row['block_id'] for row in source_overlaps(copied, [item], limit=32)}, {'p3'})
        self.assertIn('source_wording_overlap:' + item['id'], article_preflight(copied, facts, [item], 90)['errors'])
        independent = copy.deepcopy(copied)
        independent['paragraphs'][3]['text'] = ('Trend är grundversionen och har parkeringssensorer både baktill och framtill. '
                                               'Smartphoneintegreringen sker genom App Connect.')
        self.assertEqual(independent['paragraphs'][3]['fact_ids'], ['f5'])
        self.assertEqual(article_preflight(independent, facts, [item], 90)['errors'], [])
        self.assertEqual(source_overlaps(independent, [item]), [])


class OfflineReferenceTests(unittest.TestCase):
    def sample(self):
        item, initial = brief.source_and_facts()
        initial[5]['statement'] = ACTUAL_FORM
        facts = neutral_facts(initial + source_technical_facts(item, initial) + source_qualifier_facts(item))
        output = brief.reference_output(facts)
        output['paragraphs'][3] = ACTUAL_FORM + '.'
        payload = generate_article(facts, Mock(return_value=output))
        payload['sources'] = [{'url': 'https://press.example.com/release', 'publisher': 'Offline fixture'}]
        article = {'id': 'original', 'status': 'quarantined', 'payload': payload,
                   'artifact_hash': artifact_hash(payload), 'checks': ['old review must not travel with edits']}
        return item, facts, article

    def test_only_equipment_text_changes_and_original_evidence_is_untouched(self):
        item, facts, article = self.sample()
        before = copy.deepcopy((facts, article))
        revised = revise_reference(article, facts)
        self.assertEqual((facts, article), before)
        self.assertNotEqual(revised['id'], article['id'])
        self.assertNotEqual(revised['artifact_hash'], article['artifact_hash'])
        self.assertNotIn('checks', revised)
        self.assertEqual(revised['payload']['sources'], article['payload']['sources'])
        for index, paragraph in enumerate(article['payload']['paragraphs']):
            self.assertEqual(revised['payload']['paragraphs'][index]['fact_ids'], paragraph['fact_ids'])
            if index != 3:
                self.assertEqual(revised['payload']['paragraphs'][index], paragraph)
        self.assertEqual(article_preflight(revised['payload'], facts, [item], 90)['errors'], [])

    def test_offline_edit_does_not_reuse_old_audit_or_approve_publication(self):
        item, facts, article = self.sample()
        revised = revise_reference(article, facts)
        checks = validate_article(revised['payload'], facts, [item], None, 90)
        self.assertTrue(all('independent_audit_not_run' in errors for errors in checks.values()))
        self.assertEqual(revised['status'], 'quarantined')
        self.assertIsNone(revised['published_at'])

    def test_published_missing_or_ambiguous_equipment_is_not_silently_edited(self):
        _, facts, article = self.sample()
        with self.assertRaisesRegex(ValueError, 'quarantined_draft'):
            revise_reference({**article, 'status': 'published'}, facts)
        for selected in [[], facts + [{**facts[5], 'id': 'another-equipment-fact'}]]:
            changed = copy.deepcopy(article)
            if selected:
                changed['payload']['paragraphs'].append({'text': 'Other', 'kind': 'reporting', 'fact_ids': ['another-equipment-fact']})
            with self.assertRaisesRegex(ValueError, 'one_exact_equipment_slot'):
                revise_reference(changed, selected)

    def test_private_preview_cannot_claim_approval(self):
        _, facts, article = self.sample()
        revised = revise_reference(article, facts)
        html = render({**revised, 'status': 'published'}, approved=True, offline_reference=True)
        self.assertIn('Offline-redigerad referens', html)
        self.assertIn('Inte slutgranskad eller publicerad.', html)
        self.assertNotIn('Godk&auml;nd testartikel', html)
        with self.assertRaisesRegex(ValueError, 'output_must_be_private'):
            output_directory(Path(__file__).resolve().parents[1] / 'public')


if __name__ == '__main__':
    unittest.main()
