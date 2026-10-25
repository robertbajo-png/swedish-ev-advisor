import copy
import json
import re
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_editorial import generate_article, source_overlaps, validate_article, EDITORIAL_RECIPE, audit_article, draft_diagnostics, article_preflight, writer_schema, ARTICLE_SCHEMA, extract_facts, partition_fact_extraction, deterministic_article_checks, blocks, build_fact_plan, fact_plan_errors
from news_ai import response_json
from news_engine import attach_cluster, editorial
from news_store import NewsStore


class OriginalityAndAuditTests(unittest.TestCase):
    def facts(self):
        return [{**fact, 'item_id': 'item'} for fact in fixtures.extraction()['facts']]

    def check(self, article=None, audit=None):
        return validate_article(article or fixtures.draft(), self.facts(), [fixtures.item()], audit or fixtures.audit(), 90)

    def test_writer_uses_fact_inventory_not_evidence_or_raw_source(self):
        ai = Mock(return_value=fixtures.writer_result(fixtures.draft()))
        generate_article(self.facts(), ai)
        prompt = ai.call_args.args[2]
        brief = json.loads(prompt.split('\nFACT_PLAN:\n')[1])
        self.assertEqual(brief['title']['fact_ids'], ['f0'])
        self.assertNotIn('provenance', brief)
        self.assertNotIn(fixtures.CONTENT, prompt)
        self.assertIn('eight consecutive source words', prompt)

    def test_writer_schema_does_not_force_paragraph_length_or_irrelevant_citations(self):
        schema = writer_schema()['properties']
        paragraphs = schema['paragraphs']
        self.assertEqual((paragraphs['minItems'], paragraphs['maxItems']), (1, 1))
        self.assertNotIn('citations', schema)
        article = schema
        self.assertNotIn('pattern', article['intro'])
        pattern = article['buyer_question']['pattern']
        self.assertTrue(re.fullmatch(pattern, 'Vilka av dessa egenskaper passar dina behov?'))
        self.assertFalse(re.fullmatch(pattern, 'Vad passar dig? Vad prioriterar du?'))
        self.assertFalse(re.fullmatch(pattern, 'Vad passar dig?\n\nExtra text'))
        self.assertFalse(re.fullmatch(pattern, 'Räcker 324 km för dig?'))
        self.assertNotIn('pattern', ARTICLE_SCHEMA['properties']['intro'])
        self.assertNotIn('word_count', schema)

    def test_uncited_extra_block_cannot_hide_outside_the_word_count(self):
        result = fixtures.writer_result(fixtures.draft())
        result['buyer_question'] += '\n\nAn extra uncited paragraph.'
        with self.assertRaisesRegex(ValueError, 'writer_block_alignment'):
            generate_article(self.facts(), Mock(return_value=result))

    def test_writer_cannot_inject_its_own_citation_ids(self):
        result = fixtures.writer_result(fixtures.draft())
        result['citations'] = {'paragraphs': [['f0', 'f0']]}
        with self.assertRaisesRegex(ValueError, 'writer_extra_or_missing_fields'):
            generate_article(self.facts(), Mock(return_value=result))

    def test_short_factual_paragraph_can_stand_alone_without_padding(self):
        draft = fixtures.draft()
        draft['paragraphs'][0].update(text='En kort sakuppgift.', fact_ids=['f0'])
        result = fixtures.writer_result(draft)
        article = generate_article(self.facts(), Mock(return_value=result))
        self.assertEqual(article['paragraphs'][0]['text'], 'En kort sakuppgift.')

    def test_whole_article_round_trip_preserves_words_and_block_citations(self):
        draft = fixtures.draft()
        result = fixtures.writer_result(draft)
        article = generate_article(self.facts(), Mock(return_value=result))
        self.assertEqual([b['text'] for b in blocks(article)], [b['text'] for b in blocks(draft)])
        self.assertEqual(article['fact_plan_hash'], build_fact_plan(self.facts())['hash'])
        self.assertEqual(fact_plan_errors(article, self.facts()), [])
        self.assertEqual(draft_diagnostics(article, [fixtures.item()])['word_count'],
                         sum(len(b['text'].split()) for b in blocks(draft)))

    def test_extra_paragraph_or_root_field_cannot_be_silently_dropped(self):
        result = fixtures.writer_result(fixtures.draft())
        result['paragraphs'].append('An uncited extra paragraph.')
        with self.assertRaisesRegex(ValueError, 'writer_block_alignment'):
            generate_article(self.facts(), Mock(return_value=result))
        result = fixtures.writer_result(fixtures.draft())
        result['extra_question'] = 'Another uncited question?'
        with self.assertRaisesRegex(ValueError, 'writer_extra_or_missing_fields'):
            generate_article(self.facts(), Mock(return_value=result))

    def test_failed_draft_is_not_reused_as_a_writing_template(self):
        ai = Mock(return_value=fixtures.writer_result(fixtures.draft()))
        generate_article(self.facts(), ai, {'previous_draft': {'title': 'SHOULD_NOT_BE_A_TEMPLATE'},
                                         'source_overlaps': [{'phrase': 'bad copied wording'}]})
        prompt = ai.call_args.args[2]
        self.assertNotIn('SHOULD_NOT_BE_A_TEMPLATE', prompt)
        self.assertIn('bad copied wording', prompt)

    def test_fact_selection_seeks_distinct_details_and_retains_evidence_rules(self):
        ai = Mock(return_value={})
        extract_facts(fixtures.item(), [], ai)
        prompt = ai.call_args.args[2]
        self.assertIn('across the whole release', prompt)
        self.assertIn('practical capacity', prompt)
        self.assertIn('8-24 words', prompt)
        self.assertIn('country/market', prompt)

    def test_invalid_atomic_fact_can_be_quarantined_without_rewriting_valid_facts(self):
        extraction = fixtures.extraction()
        bad = {**extraction['facts'][0], 'id': 'bad', 'statement': extraction['facts'][0]['statement'] + ' 999'}
        extraction['facts'].append(bad)
        original = copy.deepcopy(extraction)
        accepted, rejected, errors = partition_fact_extraction(extraction, fixtures.item())
        self.assertEqual(errors, [])
        self.assertEqual(accepted['facts'], original['facts'][:-1])
        self.assertEqual(rejected[0]['fact'], bad)
        self.assertIn('fact_number_not_in_evidence:bad', rejected[0]['errors'])
        self.assertEqual(extraction, original)

    def test_fact_partition_never_excuses_invalid_events_or_too_few_good_facts(self):
        extraction = fixtures.extraction()
        extraction['facts'][0]['statement'] += ' 999'
        _, rejected, errors = partition_fact_extraction(extraction, fixtures.item())
        self.assertTrue(rejected)
        self.assertIn('insufficient_or_excessive_facts', errors)
        extraction['event']['subject'] = 'A different car not in this source'
        accepted, rejected, errors = partition_fact_extraction(extraction, fixtures.item())
        self.assertEqual(accepted, extraction)
        self.assertFalse(rejected)
        self.assertIn('event_subject_not_in_source', errors)

    def test_copied_phrases_are_located_and_still_rejected(self):
        article = fixtures.draft()
        article['paragraphs'][0]['text'] += ' ' + fixtures.CONTENT
        diagnostics = source_overlaps(article, [fixtures.item()], limit=2)
        self.assertEqual(len(diagnostics), 2)
        self.assertEqual(diagnostics[0]['block_id'], 'p0')
        self.assertEqual(len(diagnostics[0]['phrase'].split()), 8)
        self.assertIn('source_wording_overlap:item', self.check(article)['originality'])

    def test_conditional_analysis_passes_but_cannot_hide_unverified_numbers(self):
        self.assertEqual(self.check()['evidence'], [])
        article = fixtures.draft()
        article['paragraphs'][1]['text'] += ' Kan du anvanda bilens rackvidd pa 999 kilometer?'
        self.assertIn('unsupported_numeric_claim:p1', self.check(article)['evidence'])

    def test_acceptance_cannot_contradict_a_rejected_clause_or_verdict(self):
        for edit in [{'unsupported_claims': ['Invented delivery promise']}, {'verdict': 'unsupported_claim'}]:
            audit = fixtures.audit()
            audit['blocks'][0].update(edit)
            self.assertIn('audit_decision_inconsistent:title', self.check(audit=audit)['evidence'])

    def test_a_buyer_question_verdict_cannot_authorize_reporting(self):
        audit = fixtures.audit()
        audit['blocks'][0]['verdict'] = 'grounded_question'
        self.assertIn('audit_block_kind_mismatch:title', self.check(audit=audit)['editorial'])

    def test_rejected_analysis_needs_an_identifiable_claim_and_never_auto_passes(self):
        audit = fixtures.audit()
        audit['blocks'][-1].update(supported=False, verdict='unsupported_advice', unsupported_claims=[])
        audit['no_unsupported_claims'] = False
        errors = self.check(audit=audit)
        self.assertIn('audit_rejection_not_specific:p1', errors['evidence'])
        self.assertIn('block_audit_failed_or_incomplete', errors['evidence'])

    def test_duplicate_audit_ids_cannot_replace_complete_decisions(self):
        audit = fixtures.audit()
        audit['blocks'].append(copy.deepcopy(audit['blocks'][0]))
        self.assertIn('duplicate_block_audit_ids', self.check(audit=audit)['evidence'])

    def test_keyed_audit_schema_requires_each_real_block_exactly_once(self):
        ai = Mock(return_value=fixtures.keyed_audit(fixtures.audit()))
        result = audit_article(fixtures.draft(), self.facts(), ai)
        schema = ai.call_args.args[1]
        self.assertEqual(schema['properties']['blocks']['type'], 'object')
        self.assertEqual(set(schema['properties']['blocks']['required']), {'title','intro','p0','p1'})
        self.assertFalse(schema['properties']['blocks']['additionalProperties'])
        decision = schema['properties']['blocks']['properties']['p1']
        accepted, rejected = schema['$defs'][decision['$ref'].split('/')[-1]]['anyOf']
        self.assertEqual(accepted['properties']['supported']['enum'], [True])
        self.assertEqual(accepted['properties']['verdict']['enum'], ['grounded_question'])
        self.assertEqual(accepted['properties']['unsupported_claims']['maxItems'], 0)
        self.assertEqual(rejected['properties']['supported']['enum'], [False])
        self.assertEqual(rejected['properties']['unsupported_claims']['minItems'], 1)
        self.assertEqual(len(result['blocks']), 4)
        self.assertEqual(self.check(audit=result)['evidence'], [])

    def test_duplicate_json_properties_are_rejected_not_overwritten(self):
        with self.assertRaisesRegex(ValueError, 'duplicate_json_field'):
            response_json({'status': 'completed', 'output': [{'content': [
                {'type': 'output_text', 'text': '{"blocks":{"p0":true,"p0":false}}'}]}]})

    def test_short_draft_is_detected_before_spending_on_audit(self):
        diagnostics = draft_diagnostics({'title': 'Short title', 'intro': 'Short introduction',
                                         'paragraphs': [{'text': 'Short body', 'kind': 'reporting', 'fact_ids': ['f0']}]}, [fixtures.item()])
        self.assertIn('word_count_outside_150_400', diagnostics['errors'])
        self.assertEqual(diagnostics['required_words'], [150,400])

    def test_skipped_audit_never_counts_as_passing_quality_checks(self):
        checks = validate_article(fixtures.draft(), self.facts(), [fixtures.item()], None, 90)
        for kind in checks:
            self.assertIn('independent_audit_not_run', checks[kind])
        self.assertFalse(any('audit_decision_missing' in error for errors in checks.values() for error in errors))

    def test_preflight_and_final_validation_share_every_deterministic_check(self):
        mutations = [lambda a: a['paragraphs'][0].update(text=a['paragraphs'][0]['text'] + ' 999'),
                     lambda a: a['paragraphs'].append(copy.deepcopy(a['paragraphs'][0])),
                     lambda a: a.update(title='Too short'),
                     lambda a: a['paragraphs'][0].update(text=a['paragraphs'][0]['text'] + ' https://example.com')]
        for mutate in mutations:
            article = fixtures.draft()
            mutate(article)
            preflight = article_preflight(article, self.facts(), [fixtures.item()], 90)
            self.assertTrue(preflight['errors'])
            self.assertTrue(preflight['independent_audit_required'])
            final = validate_article(article, self.facts(), [fixtures.item()], None, 90)
            self.assertEqual(preflight['gate_errors'], {kind: [e for e in errors if e != 'independent_audit_not_run']
                                                       for kind, errors in final.items()})

    def test_clean_preflight_never_replaces_an_independent_audit(self):
        draft = fixtures.draft()
        self.assertEqual(article_preflight(draft, self.facts(), [fixtures.item()], 90)['errors'], [])
        self.assertEqual(deterministic_article_checks(draft, self.facts(), [fixtures.item()], 90),
                         {'evidence': [], 'editorial': [], 'originality': []})
        for errors in validate_article(draft, self.facts(), [fixtures.item()], None, 90).values():
            self.assertIn('independent_audit_not_run', errors)

    def test_unsupported_number_is_quarantined_without_spending_on_audit(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, fixtures.item(), fixtures.extraction())
            calls = []
            def ai(name, schema, prompt):
                calls.append(name)
                if name != 'swedish_ev_article':
                    self.fail('A deterministic failure must not trigger a paid audit')
                draft = fixtures.draft()
                draft['title_fact_ids'] = ['item:f0']
                draft['intro_fact_ids'] = ['item:f0', 'item:f1', 'item:f2']
                for p in draft['paragraphs']: p['fact_ids'] = ['item:f0', 'item:f1', 'item:f2']
                draft['paragraphs'][0]['text'] += ' 999'
                return fixtures.writer_result(draft)
            with patch('news_engine.models_for_news', return_value={}):
                reports = editorial(store, ai=ai, publish=False, max_revisions=0)
            self.assertEqual(calls, ['swedish_ev_article'])
            self.assertEqual(reports[0]['status'], 'quarantined')
            self.assertIn('unsupported_numeric_claim:p0', reports[0]['reasons'])
            for check in store.rows('news_quality_checks'):
                self.assertFalse(check['passed'])
                self.assertFalse(check['payload']['audit_performed'])
                self.assertIn('unsupported_numeric_claim:p0', check['payload']['draft_precheck']['errors'])
            self.assertEqual(store.public_articles(), [])

    def test_known_copy_is_rewritten_before_independent_audit_is_called(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, fixtures.item(), fixtures.extraction())
            facts = [{**f, 'id': 'item:f' + str(n), 'item_id': 'item'} for n, f in enumerate(fixtures.extraction()['facts'])]
            calls = []
            def ai(name, schema, prompt):
                calls.append(name)
                if name == 'swedish_ev_article':
                    draft = fixtures.draft()
                    draft['title_fact_ids'] = [facts[0]['id']]
                    draft['intro_fact_ids'] = [f['id'] for f in facts]
                    for p in draft['paragraphs']: p['fact_ids'] = [f['id'] for f in facts]
                    draft['paragraphs'][0]['text'] += ' ' + fixtures.CONTENT
                    return fixtures.writer_result(draft)
                if name == 'ev_news_block_repair':
                    self.assertIn('source_overlaps', prompt)
                    return {'p0': fixtures.draft()['paragraphs'][0]['text']}
                return fixtures.keyed_audit(fixtures.audit(facts))
            with patch('news_engine.models_for_news', return_value={}):
                self.assertEqual(editorial(store, ai=ai, publish=False)[0]['status'], 'validated_draft')
            self.assertEqual(calls, ['swedish_ev_article', 'ev_news_block_repair', 'ev_news_independent_audit'])
            self.assertEqual(store.public_articles(), [])

    def test_recipe_change_allows_one_new_cycle_without_reusing_old_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NewsStore(Path(directory) / 'news.sqlite')
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, fixtures.item(), fixtures.extraction())
            facts = [{**f, 'id': item['id'] + ':f' + str(n), 'item_id': item['id']} for n, f in enumerate(fixtures.extraction()['facts'])]
            def ai(name, schema, prompt):
                if name == 'swedish_ev_article':
                    draft = fixtures.draft()
                    draft['title_fact_ids'] = [facts[0]['id']]
                    draft['intro_fact_ids'] = [f['id'] for f in facts]
                    for p in draft['paragraphs']: p['fact_ids'] = [f['id'] for f in facts]
                    return fixtures.writer_result(draft)
                return fixtures.keyed_audit(fixtures.audit(facts))
            with patch('news_engine.models_for_news', return_value={}):
                first = editorial(store, ai=ai, publish=False)[0]
                old = store.get('news_articles', first['article_id'])
                old['payload'].update(editorial_recipe='old-recipe', revision_count=1)
                store.put('news_articles', {**old, 'status': 'quarantined'})
                trial_ai = Mock(side_effect=ai)
                result = editorial(store, ai=trial_ai, retry=True, publish=False)[0]
                self.assertEqual(result['status'], 'validated_draft')
                self.assertEqual(trial_ai.call_count, 2)
                article = store.get('news_articles', result['article_id'])
                self.assertEqual(article['payload']['editorial_recipe'], EDITORIAL_RECIPE)
                self.assertEqual(article['payload']['revision_count'], 0)
                trial_ai.reset_mock()
                editorial(store, ai=trial_ai, publish=False)
                trial_ai.assert_not_called()
                self.assertEqual(store.public_articles(), [])
            store.close()


if __name__ == '__main__':
    unittest.main()
