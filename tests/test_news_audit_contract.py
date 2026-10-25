"""Offline validation tests. No provider, network, publication or approval override."""
import copy
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_editorial import validate_article
from news_engine import attach_cluster, editorial
from news_store import NewsStore


class AuditContractTests(unittest.TestCase):
    def check(self, audit):
        facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
        return validate_article(fixtures.draft(), facts, [fixtures.item()], audit, 90)

    def test_valid_review_is_unchanged_and_still_passes(self):
        audit = fixtures.audit()
        original = copy.deepcopy(audit)
        self.assertEqual(self.check(audit), {'evidence': [], 'editorial': [], 'originality': []})
        self.assertEqual(audit, original)

    def test_positive_summary_cannot_contradict_negative_fact_or_block(self):
        for target in ['facts', 'blocks']:
            audit = fixtures.audit()
            audit[target][0]['supported'] = False
            if target == 'blocks':
                audit[target][0].update(verdict='unsupported_claim', unsupported_claims=['Unsupported launch promise'])
            original = copy.deepcopy(audit)
            result = self.check(audit)
            self.assertIn('audit_summary_contradicts_detailed_decisions', result['evidence'])
            self.assertIn(('fact' if target == 'facts' else 'block') + '_audit_failed_or_incomplete', result['evidence'])
            self.assertEqual(audit, original)

    def test_truthful_negative_summary_is_not_overridden_or_reported_as_contradictory(self):
        audit = fixtures.audit()
        audit['no_unsupported_claims'] = False
        audit['blocks'][0].update(supported=False, verdict='unsupported_claim', unsupported_claims=['A factual promise'])
        result = self.check(audit)
        self.assertNotIn('audit_summary_contradicts_detailed_decisions', result['evidence'])
        self.assertIn('block_audit_failed_or_incomplete', result['evidence'])
        self.assertIn('audit_no_unsupported_claims', result['editorial'])

    def test_wrong_root_or_collection_types_return_diagnostics_not_exceptions(self):
        for malformed in [[], '', True, 1, {'facts': []},
                          {**fixtures.audit(), 'facts': 'not a list'},
                          {**fixtures.audit(), 'blocks': {}},
                          {**fixtures.audit(), 'facts': [None]},
                          {**fixtures.audit(), 'blocks': ['not an object']}]:
            with self.subTest(value=malformed):
                result = self.check(malformed)
                self.assertTrue(any(e.startswith('audit_contract_invalid:') for e in result['evidence']))
        for result in self.check(None).values():
            self.assertIn('independent_audit_not_run', result)

    def test_boolean_fields_never_coerce_strings_or_numbers(self):
        for target, field in [(None, 'swedish_quality'), (None, 'no_unsupported_claims'),
                              ('facts', 'supported'), ('facts', 'central'), ('blocks', 'supported')]:
            for value in ['true', 'false', 0, 1, [], None]:
                audit = fixtures.audit()
                (audit if target is None else audit[target][0])[field] = value
                original = copy.deepcopy(audit)
                result = self.check(audit)
                self.assertTrue(any(e.startswith('audit_contract_invalid:') for e in result['evidence']), (target, field, value))
                self.assertEqual(audit, original)

    def test_unhashable_ids_and_malformed_reason_lists_fail_closed(self):
        mutations = [lambda a: a['facts'][0].update(id=[]),
                     lambda a: a['blocks'][0].update(id={}),
                     lambda a: a['facts'][0].update(corroborating_fact_ids=[{}]),
                     lambda a: a['blocks'][0].update(unsupported_claims=[None]),
                     lambda a: a['blocks'][0].update(reason=''),
                     lambda a: a.update(reasons='not a list'),
                     lambda a: a.update(reasons=[False])]
        for mutate in mutations:
            audit = fixtures.audit()
            mutate(audit)
            result = self.check(audit)
            self.assertTrue(any(e.startswith('audit_contract_invalid:') for e in result['evidence']))

    def test_unknown_corroboration_id_is_invalid_even_for_primary_facts(self):
        audit = fixtures.audit()
        audit['facts'][0]['corroborating_fact_ids'].append('invented-source-fact')
        self.assertIn('audit_unknown_corroborating_fact:f0', self.check(audit)['evidence'])

    def test_malformed_review_gets_quarantine_checks_instead_of_an_unexplained_crash(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            attach_cluster(store, fixtures.item(), fixtures.extraction())
            def writer(name, schema, prompt):
                self.assertEqual(name, 'swedish_ev_article')
                return fixtures.writer_result(fixtures.draft())
            with patch('news_engine.models_for_news', return_value={}), \
                 patch('news_engine.audit_article', return_value={'facts': 'malformed'}), \
                 patch.object(store, 'publish') as publisher:
                result = editorial(store, ai=writer, max_revisions=0, publish=False)
            self.assertEqual(result[0]['status'], 'quarantined')
            article = store.rows('news_articles')[0]
            self.assertEqual(article['status'], 'quarantined')
            checks = store.rows('news_quality_checks')
            self.assertEqual({c['kind'] for c in checks}, {'evidence', 'editorial', 'originality'})
            self.assertTrue(all(not c['passed'] for c in checks))
            self.assertTrue(any(e.startswith('audit_contract_invalid:') for c in checks for e in c['payload']['errors']))
            publisher.assert_not_called()
            self.assertEqual(store.public_articles(), [])

    def test_normal_retry_does_not_spend_on_rewriting_a_malformed_review(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            attach_cluster(store, fixtures.item(), fixtures.extraction())
            calls = []
            def writer(name, schema, prompt):
                calls.append(name)
                return fixtures.writer_result(fixtures.draft())
            with patch('news_engine.models_for_news', return_value={}), \
                 patch('news_engine.audit_article', return_value={'facts': 'malformed'}) as reviewer, \
                 patch.object(store, 'publish') as publisher:
                result = editorial(store, ai=writer, publish=True)
                self.assertEqual(editorial(store, ai=writer, retry=True, publish=True), [])
            self.assertEqual(result[0]['status'], 'quarantined')
            self.assertEqual(calls, ['swedish_ev_article'])
            self.assertEqual(reviewer.call_count, 1)
            publisher.assert_not_called()
            self.assertEqual(store.public_articles(), [])

    def test_a_new_recipe_can_recheck_without_erasing_previous_failed_evidence(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, fixtures.item(), fixtures.extraction())
            facts = [{**f, 'id': item['id'] + ':f' + str(n), 'item_id': item['id']}
                     for n, f in enumerate(fixtures.extraction()['facts'])]
            def writer(name, schema, prompt):
                return fixtures.writer_result(fixtures.draft())
            with patch('news_engine.models_for_news', return_value={}), \
                 patch('news_engine.audit_article', return_value={'facts': 'malformed'}):
                self.assertEqual(editorial(store, ai=writer, publish=False)[0]['status'], 'quarantined')
            previous_checks = copy.deepcopy(store.rows('news_quality_checks'))
            previous_hash = store.rows('news_articles')[0]['artifact_hash']
            with patch('news_engine.models_for_news', return_value={}), \
                 patch('news_engine.EDITORIAL_RECIPE', 'offline-new-recipe-fixture'), \
                 patch('news_engine.audit_article', return_value=fixtures.audit(facts)), \
                 patch.object(store, 'publish') as publisher:
                self.assertEqual(editorial(store, ai=writer, publish=False)[0]['status'], 'validated_draft')
            preserved = [check for check in store.rows('news_quality_checks') if check['artifact_hash'] == previous_hash]
            self.assertEqual(preserved, previous_checks)
            publisher.assert_not_called()
            self.assertEqual(store.public_articles(), [])


if __name__ == '__main__':
    unittest.main()
