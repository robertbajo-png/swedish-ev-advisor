"""Matrix safety and genre/scope regressions. No network or paid provider calls."""
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
import trial_news_matrix as matrix
import trial_news_matrix_queue_fix as queue_fix
import trial_news_matrix_r19 as r19
from news_ai import NewsBudgetBlocked, MODEL
from news_editorial import statistics_market_errors, validate_article, validate_fact_extraction
from trial_news_review import TrialClient
from news_store import artifact_hash


class MatrixScopeTests(unittest.TestCase):
    def test_market_trial_cannot_promote_low_relevance_or_unquoted_numbers(self):
        item, extraction = fixtures.item(), fixtures.extraction()
        extraction['sweden_relevance'] = 0.35
        extraction['facts'][0]['statement'] += ' Registreringarna ökade 21.2 procent.'
        before = copy.deepcopy(extraction)
        errors = validate_fact_extraction(extraction, item)
        self.assertIn('insufficient_swedish_relevance', errors)
        self.assertIn('fact_number_not_in_evidence:f0', errors)
        self.assertEqual(extraction, before)

    def test_market_aliases_keep_eu_and_sweden_distinct(self):
        facts = [{'id': 'eu', 'statement': 'Battery-electric car registrations reached 22.7% of the EU market.'},
                 {'id': 'de', 'statement': 'Car registrations increased in Germany.'}]
        article = {'paragraphs': [{'kind': 'reporting', 'text': 'Andelen av nyregistreringarna i Sverige är 22.7%.', 'fact_ids': ['eu']}]}
        self.assertEqual(statistics_market_errors(article, facts), ['statistics_market_mismatch:p0:Sweden'])
        article['paragraphs'][0]['text'] = 'Andelen av nyregistreringarna i Europeiska unionen är 22.7%.'
        self.assertEqual(statistics_market_errors(article, facts), [])
        article['paragraphs'][0].update(text='Registreringarna ökar i Tyskland.', fact_ids=['de'])
        self.assertEqual(statistics_market_errors(article, facts), [])

    def test_uncited_market_fact_and_positive_audit_cannot_license_swedish_totals(self):
        facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
        facts[0]['statement'] = 'EU registrations increased this year.'
        facts.append({'id': 'sweden', 'statement': 'Swedish registrations increased.', 'evidence': 'Swedish registrations increased.', 'item_id': 'item'})
        article = fixtures.draft()
        article['title'] = 'Svenska registreringar ökar under året'
        article['title_fact_ids'] = ['f0']
        checks = validate_article(article, facts, [fixtures.item()], fixtures.audit(facts), 90)
        self.assertIn('statistics_market_mismatch:title:Sweden', checks['evidence'])

    def test_eu_is_not_the_same_statistical_area_as_all_europe(self):
        facts = [{'id': 'eu', 'statement': 'EU car registrations increased.'}]
        article = {'title': 'Registreringarna ökar i Europa', 'title_fact_ids': ['eu']}
        self.assertEqual(statistics_market_errors(article, facts), ['statistics_market_mismatch:title:Europe'])
        article = {'paragraphs': [{'kind': 'analysis', 'text': 'Hur påverkar det ditt eget bilval i Sverige?', 'fact_ids': ['eu']}]}
        self.assertEqual(statistics_market_errors(article, facts), [])


class MatrixSafetyTests(unittest.TestCase):
    def test_r19_uses_new_private_paths_with_same_budget_and_single_use_contract(self):
        original = {key: getattr(matrix, key) for key in ['TRIAL_ID', 'DATABASE', 'OUTPUT', 'RECIPE']}
        with patch.multiple(matrix, **original):
            r19.configure()
            self.assertNotEqual(matrix.TRIAL_ID, original['TRIAL_ID'])
            self.assertNotEqual(matrix.DATABASE, original['DATABASE'])
            self.assertNotEqual(matrix.OUTPUT, original['OUTPUT'])
            self.assertEqual(matrix.MAX_MICRO_USD, 60000)
            self.assertEqual(matrix.MAX_REQUESTS, 9)
            self.assertEqual(matrix.RECIPE, 'news-editorial-recipe-2026-10-r19')

    def test_two_case_run_preserves_production_and_stop_receipt_with_mixed_results(self):
        for successful in [True, False]:
            with self.subTest(successful=successful), tempfile.TemporaryDirectory() as directory:
                database = Path(directory) / 'matrix.sqlite'
                output, public = Path(directory) / 'report.json', Path(directory) / 'public.json'
                public.write_text('[]', encoding='utf-8')
                sources = {key: {**fixtures.SOURCE, 'id': key} for key in ['model-source', 'market-source']}
                with closing(matrix.PrivateMatrixStore(database)) as store:
                    for key, source in sources.items():
                        store.put('news_sources', {'id': key, 'payload': source})
                        item = {**fixtures.item(key), 'source_id': key, 'cluster_id': key + '-cluster',
                                'url': 'https://press.example.com/' + key}
                        item['payload']['extraction'] = fixtures.extraction()
                        if key == 'market-source':
                            item['payload']['extraction']['event']['action'] = 'market'
                        store.put('news_items', item)
                    cases = [matrix.contract(item) for item in store.rows('news_items')]
                cfg = {'enabled': True, 'publication_enabled': False, 'daily_limit_micro_usd': 250000, 'monthly_limit_micro_usd': 5000000}
                prepared = {'kind': 'private_news_matrix', 'state': 'prepared', 'trial_id': matrix.TRIAL_ID, 'recipe': matrix.RECIPE,
                    'cases': cases, 'maximum_micro_usd': 60000, 'maximum_requests': 9, 'baseline_request_ids': [],
                    'public_database_hash': artifact_hash([]), 'production_articles_hash': artifact_hash([]),
                    'public_file_hash': matrix.hashlib.sha256(public.read_bytes()).hexdigest(), 'source_config_hash': artifact_hash(sources)}
                output.write_text(json.dumps(prepared), encoding='utf-8')
                marker = {'payload': copy.deepcopy(prepared)}
                remote = Mock()
                remote.get.side_effect = lambda *args: marker
                remote.put.side_effect = lambda table, row: marker.update(payload=row['payload'])
                remote.public_articles.return_value = []
                remote.rows.return_value = []
                remote.client.select.side_effect = lambda table, **kwargs: [cfg] if table == 'news_ai_config' else []
                def editorial(store, **kwargs):
                    self.assertFalse(kwargs['publish'])
                    self.assertEqual(kwargs['max_revisions'], 1)
                    article_id = next(iter(kwargs['_only_articles']))
                    item = next(item for item in store.rows('news_items') if matrix.stable_id('article:' + item['cluster_id']) == article_id)
                    category = 'modeller' if item['source_id'] == 'model-source' else 'marknad'
                    passed = successful or category == 'modeller'
                    article = store.put('news_articles', {'id': article_id, 'cluster_id': item['cluster_id'], 'slug': item['id'],
                        'status': 'draft' if passed else 'quarantined', 'published_at': None,
                        'payload': {**fixtures.draft(), 'category': category}})
                    for kind in ['evidence', 'editorial', 'originality']:
                        store.put('news_quality_checks', {'id': article_id + kind, 'article_id': article_id,
                            'kind': kind, 'artifact_hash': article['artifact_hash'], 'passed': passed,
                            'payload': {'audit_performed': True}})
                    return [{'status': 'validated_draft' if passed else 'quarantined'}]
                provider = Mock(stats={'provider_requests': 0})
                def hydrate(store, item, *args):
                    return store.put('news_items', {**item, 'status': 'ready'}), []
                with patch.multiple(matrix, DATABASE=database, OUTPUT=output, PUBLIC_FILE=public), \
                     patch('trial_news_matrix.authorize'), patch('trial_news_matrix.NewsAi', return_value=provider), \
                     patch('trial_news_matrix.hydrate_item', side_effect=hydrate), \
                     patch('trial_news_matrix.editorial', side_effect=editorial):
                    result = matrix.run(remote, collector=Mock())
                    self.assertEqual(result['passed'], successful, result)
                    self.assertEqual(len(result['results']), 2)
                    self.assertTrue(result['production_unchanged'])
                    self.assertEqual({call.args[0] for call in remote.put.call_args_list}, {'news_ingestion_runs'})
                    cfg['enabled'] = False
                    self.assertTrue(matrix.verify_stop(remote)['owner_shutdown_verified'])
                    with self.assertRaisesRegex(NewsBudgetBlocked, 'unused_matching_preparation'):
                        matrix.run(remote, collector=Mock())
                provider.assert_not_called()

    def test_hydrated_collected_case_returns_to_extraction_queue_not_ready_limbo(self):
        with tempfile.TemporaryDirectory() as directory, closing(matrix.PrivateMatrixStore(Path(directory) / 'matrix.sqlite')) as store:
            item = {**fixtures.item(), 'status': 'ready'}
            store.put('news_items', item)
            def hydrate(store, item, *args):
                return store.put('news_items', {**item, 'status': 'ready'}), []
            with patch('trial_news_matrix.hydrate_item', side_effect=hydrate):
                refreshed = matrix.refresh_case(store, matrix.contract(item), {}, Mock())
            self.assertEqual(refreshed['status'], 'collected')
            self.assertEqual(store.get('news_items', item['id'])['status'], 'collected')

    def test_queue_fix_never_resets_or_reuses_a_parent_that_made_provider_calls(self):
        remote = Mock()
        for usage, count, cost in [([{'id': 'spent'}], 1, 1), ([], 1, 0), ([], 0, 1)]:
            remote.get.return_value = {'payload': {'state': 'completed', 'recipe': matrix.RECIPE,
                'owner_shutdown_verified': True, 'trial_usage': usage,
                'provider_stats': {'provider_requests': count}, 'new_charged_or_reserved_micro_usd': cost}}
            with self.assertRaisesRegex(NewsBudgetBlocked, 'verified_zero_call_parent'):
                queue_fix.configure(remote, preparing=True)
        remote.put.assert_not_called()

    def test_store_cannot_publish_even_when_called_with_approval(self):
        with tempfile.TemporaryDirectory() as directory, closing(matrix.PrivateMatrixStore(Path(directory) / 'matrix.sqlite')) as store:
            with self.assertRaisesRegex(ValueError, 'publication_forbidden'):
                store.publish('anything')
            self.assertEqual(store.public_articles(), [])

    def test_matrix_budget_contract_counts_all_new_attempts_including_unknown_usage(self):
        client, authorizer = Mock(), Mock()
        rows = [{'id': 'old', 'charged_micro_usd': 348663}, {'id': 'new', 'charged_micro_usd': 57000}]
        client.select.side_effect = lambda *args, **kwargs: rows
        wrapper = TrialClient(client, ['old'], stages={'ev_news_facts'}, maximum_requests=9,
                              maximum_micro_usd=60000, authorize=authorizer)
        body = {'stage_key': 'ev_news_facts', 'model_key': MODEL, 'input_bound': 1000, 'output_bound': 500}
        with patch('trial_news_review.config_for_trial'):
            wrapper._request('POST', 'rpc/reserve_news_ai', body)
            rows[1]['charged_micro_usd'] = 57001
            with self.assertRaisesRegex(NewsBudgetBlocked, 'cost_limit'):
                wrapper._request('POST', 'rpc/reserve_news_ai', body)
            rows[:] = [{'id': str(n), 'charged_micro_usd': 1, 'settled_at': None} for n in range(9)]
            with self.assertRaisesRegex(NewsBudgetBlocked, 'request_limit'):
                wrapper._request('POST', 'rpc/reserve_news_ai', body)
        client._request.assert_called_once()
        self.assertEqual(authorizer.call_count, 3)
        with self.assertRaisesRegex(NewsBudgetBlocked, 'budget_rpcs_only'):
            wrapper._request('POST', 'rpc/publish_news_article', {})
        with self.assertRaisesRegex(NewsBudgetBlocked, 'receipts_only'):
            wrapper.upsert('news_articles', [])

    def test_consumed_preparation_cannot_be_reset_and_never_calls_ai(self):
        remote = Mock()
        remote.get.return_value = {'payload': {'state': 'completed'}}
        with patch('trial_news_matrix.authorize'), patch('trial_news_matrix.NewsAi') as ai:
            with self.assertRaisesRegex(NewsBudgetBlocked, 'preparation_already_exists'):
                matrix.prepare(remote)
            ai.assert_not_called()
            remote.put.assert_not_called()

    def test_run_refuses_consumed_or_changed_manifest_before_any_provider_call(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            output.write_text(json.dumps({'state': 'completed'}), encoding='utf-8')
            remote = Mock()
            remote.get.return_value = {'payload': {'state': 'completed'}}
            with patch('trial_news_matrix.OUTPUT', output), patch('trial_news_matrix.authorize'), patch('trial_news_matrix.NewsAi') as ai:
                with self.assertRaisesRegex(NewsBudgetBlocked, 'unused_matching_preparation'):
                    matrix.run(remote)
                ai.assert_not_called()

    def test_source_contract_binds_text_date_extraction_and_metadata(self):
        item = fixtures.item()
        original = matrix.contract(item)
        for field, value in [('content_hash', 'changed'), ('published_at', 'changed'), ('publisher', 'Changed source'),
                             ('extraction', fixtures.extraction())]:
            changed = copy.deepcopy(item)
            changed['payload'][field] = value
            self.assertNotEqual(matrix.contract(changed), original)

    def test_production_drafts_are_protected_even_if_public_news_is_still_empty(self):
        remote = Mock()
        remote.public_articles.return_value = []
        remote.rows.return_value = [{'id': 'original', 'status': 'draft'}]
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / 'public.json'
            public.write_text('[]', encoding='utf-8')
            report = {'public_database_hash': artifact_hash([]),
                      'production_articles_hash': artifact_hash(remote.rows.return_value),
                      'public_file_hash': matrix.hashlib.sha256(public.read_bytes()).hexdigest()}
            with patch('trial_news_matrix.PUBLIC_FILE', public):
                matrix.assert_unchanged(remote, report)
                remote.rows.return_value[0]['status'] = 'quarantined'
                with self.assertRaisesRegex(NewsBudgetBlocked, 'production_surface_changed'):
                    matrix.assert_unchanged(remote, report)

    def test_diagnostic_audit_cannot_mutate_text_approve_gates_or_trigger_publication(self):
        with tempfile.TemporaryDirectory() as directory, closing(matrix.PrivateMatrixStore(Path(directory) / 'matrix.sqlite')) as store:
            item = {**fixtures.item(), 'cluster_id': 'cluster'}
            store.put('news_items', item)
            article = store.put('news_articles', {'id': 'article', 'cluster_id': 'cluster', 'slug': 'private', 'status': 'quarantined',
                'published_at': None, 'payload': {**fixtures.draft(), 'category': 'modeller', 'relevance_score': 90}})
            facts = [{**f, 'item_id': 'item'} for f in fixtures.extraction()['facts']]
            for kind in ['evidence', 'editorial', 'originality']:
                store.put('news_quality_checks', {'id': kind, 'article_id': 'article', 'kind': kind,
                    'artifact_hash': article['artifact_hash'], 'passed': False,
                    'payload': {'fact_inventory': facts if kind == 'evidence' else [], 'audit_performed': False}})
            before = copy.deepcopy(store.rows('news_articles'))
            with patch('trial_news_matrix.audit_article', return_value=fixtures.audit(facts)) as audit:
                result = matrix.final_review(store, article, Mock())
            self.assertTrue(result['audit_performed'])
            self.assertFalse(result['passed'])
            self.assertFalse(result['diagnostic_final_review']['approval'])
            self.assertEqual(store.rows('news_articles'), before)
            self.assertTrue(all(not check['passed'] for check in store.rows('news_quality_checks')))
            self.assertEqual(store.public_articles(), [])
            audit.assert_called_once()
            # A normal exact-artifact audit must never be charged for a second time.
            check = store.get('news_quality_checks', 'editorial')
            store.put('news_quality_checks', {**check, 'payload': {'audit_performed': True}})
            with patch('trial_news_matrix.audit_article') as second:
                self.assertTrue(matrix.final_review(store, article, Mock())['audit_performed'])
                second.assert_not_called()


if __name__ == '__main__':
    unittest.main()
