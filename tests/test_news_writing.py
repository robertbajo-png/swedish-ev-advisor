import copy
import json
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_editorial import (article_preflight, generate_article, repair_article,
                            repair_source_wording, source_overlaps, EDITORIAL_RECIPE,
                            validate_article, writing_inventory, writing_style_errors)
from news_engine import attach_cluster, editorial
from news_store import NewsStore


class NewsWritingTests(unittest.TestCase):
    def test_known_vague_wltp_and_tautological_question_fail_without_changing_the_text(self):
        draft = fixtures.draft()
        draft['paragraphs'] = [
            {'kind': 'reporting', 'text': 'Den angivna WLTP-räckvidden gäller beroende på utrustning.'},
            {'kind': 'analysis', 'text': 'Behöver du en räckvidd som räcker mellan dina laddstopp?'},
        ]
        original = copy.deepcopy(draft)
        self.assertEqual(writing_style_errors(draft), ['unclear_wltp_qualification:p0', 'tautological_buyer_question:p1'])
        self.assertEqual(draft, original)
        draft['paragraphs'][0]['text'] = 'Vald utrustning kan påverka bilens WLTP-räckvidd.'
        draft['paragraphs'][1]['text'] = 'Hur långt behöver du kunna köra mellan laddningarna?'
        self.assertEqual(writing_style_errors(draft), [])

    def test_known_process_prose_and_empty_framing_are_identified(self):
        article = fixtures.draft()
        article['paragraphs'] = [
            {'text': 'Det här blocket förklarar att utrustningen kan påverka räckvidden.', 'kind': 'reporting'},
            {'text': 'Det här blocket förklarar att laddtiden beror på utomhustemperaturen.', 'kind': 'reporting'},
            {'text': 'Det är de uppgifter som anges för bilen i samband med förförsäljningen av nya ID. Cross.', 'kind': 'reporting'},
        ]
        self.assertEqual(writing_style_errors(article), [
            'internal_writing_commentary:p0', 'internal_writing_commentary:p1', 'empty_information_framing:p2'])

    def test_direct_conditions_and_normal_attribution_are_allowed(self):
        article = fixtures.draft()
        article['paragraphs'] = [
            {'text': 'Vald utrustning kan påverka utfallet i WLTP-provet.', 'kind': 'reporting'},
            {'text': 'Temperaturen och batteriets laddningsnivå påverkar laddtiden.', 'kind': 'reporting'},
            {'text': 'Tillverkaren uppger att beställningarna öppnar i Sverige under hösten.', 'kind': 'reporting'},
            {'text': 'Det här batteriblocket visas på företagets teknikdag.', 'kind': 'reporting'},
        ]
        self.assertEqual(writing_style_errors(article), [])

    def test_internal_field_labels_are_never_consumer_prose(self):
        article = fixtures.draft()
        for text in ['This paragraph explains the specifications.', 'source_context: ett villkor',
                     'Detta stycke beskriver vad som är viktigt.']:
            article['intro'] = text
            self.assertIn('internal_writing_commentary:intro', writing_style_errors(article))

    def test_shared_checks_reject_procedural_text_without_deleting_or_approving_it(self):
        article = fixtures.draft()
        article['paragraphs'][0]['text'] += ' Det här blocket förklarar hur batteriet används.'
        original = copy.deepcopy(article)
        facts = [{**fact, 'item_id': 'item'} for fact in fixtures.extraction()['facts']]
        error = 'internal_writing_commentary:p0'
        precheck = article_preflight(article, facts, [fixtures.item()], 90)
        final = validate_article(article, facts, [fixtures.item()], fixtures.audit(), 90)
        self.assertIn(error, precheck['errors'])
        self.assertIn(error, final['editorial'])
        self.assertTrue(precheck['independent_audit_required'])
        self.assertEqual(article, original)

    def test_writing_brief_separates_news_detail_from_direct_qualifications(self):
        facts = fixtures.extraction()['facts']
        facts.append({'id': 'q0', 'statement': 'A complete supplied measurement qualification.',
                      'origin': 'literal_source_qualifier', 'evidence': 'PRIVATE_EVIDENCE'})
        inventory = writing_inventory(facts)
        self.assertEqual(inventory[0]['placement'], 'reporting')
        self.assertEqual(inventory[-1]['placement'], 'source_context')
        self.assertTrue(all(set(fact) == {'id', 'statement', 'placement', 'claim_topics', 'item_id',
                                         'qualification_topic', 'statistic'} for fact in inventory))
        ai = Mock(return_value=fixtures.writer_result(fixtures.draft()))
        generate_article(fixtures.extraction()['facts'], ai)
        prompt = ai.call_args.args[2]
        for instruction in ['one home', 'not a list of specifications', 'State the condition itself',
                            'shorter grounded article for quarantine', '150-400', 'exactly ONE']:
            self.assertIn(instruction, prompt)
        self.assertNotIn(fixtures.CONTENT, prompt)
        self.assertIn("Changing punctuation or a few synonyms", prompt)

    def test_targeted_repair_excludes_evidence_fields_and_keeps_other_blocks(self):
        draft = fixtures.draft()
        original = copy.deepcopy(draft)
        facts = fixtures.extraction()['facts']
        facts[0]['evidence'] = 'PRIVATE_EVIDENCE_NOT_FOR_THE_WRITER'
        ai = Mock(return_value={**draft['paragraphs'][0], 'text': 'En direkt, underbyggd sakuppgift.'})
        result = repair_article(draft, facts, {'unsupported_blocks': [{'id': 'p0', 'reason': 'redundant framing'}]}, ai)
        prompt = ai.call_args.args[2]
        brief = json.loads(prompt.split('\n')[-1])['FACTS']
        self.assertEqual(brief, writing_inventory(facts))
        self.assertNotIn('PRIVATE_EVIDENCE_NOT_FOR_THE_WRITER', prompt)
        self.assertEqual(result['paragraphs'][1], original['paragraphs'][1])
        self.assertEqual(draft, original)

    def test_process_prose_is_quarantined_before_a_paid_audit_and_retries_remain_bounded(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, fixtures.item(), fixtures.extraction())
            draft = fixtures.draft()
            ids = [item['id'] + ':f' + str(n) for n in range(3)]
            draft['title_fact_ids'] = draft['intro_fact_ids'] = ids
            for paragraph in draft['paragraphs']:
                paragraph['fact_ids'] = ids
            draft['paragraphs'][0]['text'] += ' Det här blocket förklarar vad som förändras.'
            writer = Mock(return_value=fixtures.writer_result(draft))
            with patch('news_engine.models_for_news', return_value={}), patch('news_engine.audit_article') as audit:
                result = editorial(store, ai=writer, publish=False)
                self.assertEqual(result[0]['status'], 'quarantined')
                self.assertIn('internal_writing_commentary:p0', result[0]['reasons'])
                self.assertEqual(writer.call_count, 2)
                self.assertEqual(editorial(store, ai=writer, retry=True, publish=False), [])
                self.assertEqual(writer.call_count, 2)
                audit.assert_not_called()
            self.assertEqual(store.public_articles(), [])
            for check in store.rows('news_quality_checks'):
                self.assertFalse(check['payload']['audit_performed'])

    def test_source_repair_preserves_citations_other_blocks_and_input(self):
        draft = fixtures.draft()
        original = copy.deepcopy(draft)
        facts = fixtures.extraction()['facts']
        for fact in facts:
            fact['evidence'] = 'PRIVATE_EVIDENCE_NOT_FOR_WRITING'
        ai = Mock(return_value={'p0': 'Tillverkaren beskriver en förändrad konstruktion för batteriet.'})
        result = repair_source_wording(draft, facts, [{'block_id': 'p0', 'phrase': 'source phrase'}], ai)
        self.assertEqual(result['paragraphs'][0]['fact_ids'], original['paragraphs'][0]['fact_ids'])
        self.assertEqual(result['paragraphs'][1], original['paragraphs'][1])
        self.assertEqual(result['title'], original['title'])
        self.assertEqual(draft, original)
        self.assertNotIn('PRIVATE_EVIDENCE_NOT_FOR_WRITING', ai.call_args.args[2])
        self.assertEqual(ai.call_args.args[0], 'ev_news_block_repair')
        self.assertEqual(set(ai.call_args.args[1]['properties']), {'p0'})

    def test_source_repair_cannot_change_blocks_or_hide_new_paragraphs(self):
        draft = fixtures.draft()
        facts = fixtures.extraction()['facts']
        for target in ['p999', 'p0']:
            candidate = copy.deepcopy(draft)
            if target == 'p0':
                candidate['paragraphs'][0]['kind'] = 'invalid'
            with self.assertRaises(ValueError):
                repair_source_wording(candidate, facts, [{'block_id': target}], Mock())
        for result in [{'p0': 'Text', 'p1': 'Unrequested change'}, {'p0': 'Text\n\nHidden block'}, {'p0': ''}]:
            with self.assertRaises(ValueError):
                repair_source_wording(draft, facts, [{'block_id': 'p0'}], Mock(return_value=result))
        revised = repair_source_wording(draft, facts, [{'block_id': 'p0'}], Mock(return_value={'p0': 'Batteriet ger 999 km räckvidd.'}))
        self.assertIn('unsupported_numeric_claim:p0', article_preflight(revised,
            [{**f, 'item_id': 'item'} for f in facts], [fixtures.item()], 90)['errors'])

    def test_intro_title_and_body_can_be_repaired_without_changing_any_bindings(self):
        draft = fixtures.draft()
        draft['fact_plan_hash'] = 'unchanged-plan'
        original = copy.deepcopy(draft)
        replacements = {'title': 'Ny konstruktion presenteras för den europeiska elbilen',
                        'intro': 'Den uppdaterade bilen har presenterats för Europa.',
                        'p0': 'Tillverkaren beskriver en ändring av batteriets konstruktion.'}
        ai = Mock(return_value=replacements)
        revised = repair_source_wording(draft, fixtures.extraction()['facts'],
                                        [{'block_id': key} for key in replacements], ai)
        self.assertEqual(draft, original)
        self.assertEqual(revised['fact_plan_hash'], draft['fact_plan_hash'])
        for key in ['title_fact_ids', 'intro_fact_ids']:
            self.assertEqual(revised[key], original[key])
        self.assertEqual(revised['paragraphs'][0]['fact_ids'], original['paragraphs'][0]['fact_ids'])
        self.assertEqual(revised['paragraphs'][1], original['paragraphs'][1])
        self.assertEqual(set(ai.call_args.args[1]['properties']), set(replacements))
        for instruction in ['separate the order-opening event', 'lead with duration', 'Absolute specifications do not prove']:
            self.assertIn(instruction, ai.call_args.args[2])
        with self.assertRaisesRegex(ValueError, 'one_to_three_existing_blocks'):
            repair_source_wording(draft, fixtures.extraction()['facts'],
                                 [{'block_id': key} for key in ['title', 'intro', 'p0', 'p1']], ai)

    def test_intro_and_comparison_errors_use_one_bounded_edit_and_audit_exact_final_text(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, fixtures.item(), fixtures.extraction())
            good = fixtures.draft()
            ids = [item['id'] + ':f' + str(n) for n in range(3)]
            good['title_fact_ids'] = good['intro_fact_ids'] = ids
            for paragraph in good['paragraphs']:
                paragraph['fact_ids'] = ids
            bad = copy.deepcopy(good)
            bad['intro'] += ' ' + fixtures.CONTENT
            bad['paragraphs'][0]['text'] += ' Den mindre batteriversionen presenteras.'
            ai = Mock(return_value={'intro': good['intro'], 'p0': good['paragraphs'][0]['text']})
            facts = [{**f, 'id': ids[n], 'item_id': item['id']} for n, f in enumerate(fixtures.extraction()['facts'])]
            with patch('news_engine.models_for_news', return_value={}), \
                 patch('news_engine.generate_article', return_value=bad) as generate, \
                 patch('news_engine.audit_article', return_value=fixtures.audit(facts)) as audit:
                result = editorial(store, ai=ai, publish=False)
                self.assertEqual(result[0]['status'], 'validated_draft')
                generate.assert_called_once()
                ai.assert_called_once()
                audit.assert_called_once()
                self.assertEqual(audit.call_args.args[0], good)
                self.assertEqual(store.rows('news_articles')[0]['payload']['revision_count'], 1)
                self.assertEqual(store.public_articles(), [])

    def test_source_repair_can_rewrite_a_buyer_question_without_repeating_figures(self):
        draft = fixtures.draft()
        text = 'När behöver du kunna beställa din nästa bil?'
        ai = Mock(return_value={'p1': text})
        revised = repair_source_wording(draft, fixtures.extraction()['facts'], [{'block_id': 'p1'}], ai)
        self.assertEqual(revised['paragraphs'][0], draft['paragraphs'][0])
        self.assertEqual(revised['paragraphs'][1], {**draft['paragraphs'][1], 'text': text})
        for invalid in ['Räcker 324 km för dig?', 'Vad passar dig? Vad väljer du?', 'Bilen passar alla.']:
            with self.assertRaisesRegex(ValueError, 'invalid_buyer_question'):
                repair_source_wording(draft, fixtures.extraction()['facts'], [{'block_id': 'p1'}], Mock(return_value={'p1': invalid}))

    def test_overlap_diagnostics_cover_distinct_blocks_not_only_one_long_list(self):
        article = fixtures.draft()
        text = fixtures.CONTENT
        article['paragraphs'] = [{'text': text, 'kind': 'reporting'}, {'text': text, 'kind': 'reporting'}]
        matches = source_overlaps(article, [fixtures.item()], limit=32, per_block_limit=1)
        self.assertEqual([m['block_id'] for m in matches], ['p0', 'p1'])

    def test_source_revision_is_bounded_and_only_final_text_can_be_audited(self):
        for successful in [True, False]:
            with self.subTest(successful=successful), tempfile.TemporaryDirectory() as directory, \
                 closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
                store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
                item = attach_cluster(store, fixtures.item(), fixtures.extraction())
                good = fixtures.draft()
                ids = [item['id'] + ':f' + str(n) for n in range(3)]
                good['title_fact_ids'] = good['intro_fact_ids'] = ids
                for paragraph in good['paragraphs']:
                    paragraph['fact_ids'] = ids
                bad = copy.deepcopy(good)
                bad['paragraphs'][0]['text'] += ' ' + fixtures.CONTENT
                ai = Mock(return_value={'p0': (good if successful else bad)['paragraphs'][0]['text']})
                facts = [{**f, 'id': ids[n], 'item_id': item['id']} for n, f in enumerate(fixtures.extraction()['facts'])]
                with patch('news_engine.models_for_news', return_value={}), \
                     patch('news_engine.generate_article', return_value=bad) as generate, \
                     patch('news_engine.audit_article', return_value=fixtures.audit(facts)) as audit:
                    result = editorial(store, ai=ai, publish=False)
                    self.assertEqual(result[0]['status'], 'validated_draft' if successful else 'quarantined')
                    generate.assert_called_once()
                    ai.assert_called_once()
                    if successful:
                        audit.assert_called_once()
                        self.assertEqual(audit.call_args.args[0], good)
                    else:
                        audit.assert_not_called()
                        self.assertEqual(editorial(store, ai=ai, retry=True, publish=False), [])
                        ai.assert_called_once()
                    self.assertEqual(store.rows('news_articles')[0]['payload']['revision_count'], 1)
                    self.assertEqual(store.public_articles(), [])

    def test_changed_recipe_never_repairs_using_stale_audit_feedback(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            attach_cluster(store, fixtures.item(), fixtures.extraction())
            with patch('news_engine.models_for_news', return_value={}), \
                 patch('news_engine.generate_article', return_value=fixtures.draft()) as generate, \
                 patch('news_engine.audit_article', return_value=fixtures.audit()):
                editorial(store, publish=False, max_revisions=0)
                old = store.rows('news_articles')[0]
                old['payload'].update(editorial_recipe='old-recipe', revision_count=1)
                store.put('news_articles', old)
                generate.reset_mock()
                editorial(store, publish=False, retry=True, max_revisions=0)
                self.assertEqual(generate.call_args.args[2]['errors'], [])
                self.assertNotIn('previous_draft', generate.call_args.args[2])
                self.assertEqual(store.rows('news_articles')[0]['payload']['editorial_recipe'], EDITORIAL_RECIPE)


if __name__ == '__main__':
    unittest.main()
