import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import trial_news_review as trial
from news_ai import NewsBudgetBlocked, MODEL
from news_store import artifact_hash


class NewsReviewTrialTests(unittest.TestCase):
    def setUp(self):
        date = patch('trial_news_review.require_date')
        self.date = date.start()
        self.addCleanup(date.stop)
        config = patch('trial_news_review.config_for_trial')
        self.config = config.start()
        self.addCleanup(config.stop)
        self.client = Mock()
        self.rows = []
        self.client.select.side_effect = lambda *args, **kwargs: self.rows
        self.wrapper = trial.TrialClient(self.client, ['old'])
        self.body = {'stage_key': 'swedish_ev_article', 'model_key': MODEL,
                     'input_bound': 1000, 'output_bound': 500}

    def reserve(self):
        return self.wrapper._request('POST', 'rpc/reserve_news_ai', self.body)

    def test_writing_trial_has_distinct_fixed_identity_output_and_smaller_cap(self):
        previous_id, previous_output = trial.TRIAL_ID, trial.OUTPUT
        with patch.multiple(trial, TRIAL_ID=previous_id, OUTPUT=previous_output,
                            MAX_MICRO_USD=trial.MAX_MICRO_USD, REQUIRED_RECIPE=None):
            trial.select_writing_trial()
            self.assertNotEqual(trial.TRIAL_ID, previous_id)
            self.assertNotEqual(trial.OUTPUT, previous_output)
            self.assertEqual(trial.REQUIRED_RECIPE, 'news-editorial-recipe-2026-10-r12')
            self.assertEqual(trial.MAX_MICRO_USD, 60000)
            self.rows = [{'id': 'old', 'charged_micro_usd': 251872},
                         {'id': 'new', 'charged_micro_usd': 57001}]
            with self.assertRaisesRegex(NewsBudgetBlocked, 'cost_limit'):
                self.reserve()
            self.client._request.assert_not_called()
            with self.assertRaisesRegex(NewsBudgetBlocked, 'no_format_continuation'):
                trial.run(Mock(), resume_format=True)

    def test_writing_trial_requires_prepared_recipe_contract(self):
        with patch.multiple(trial, TRIAL_ID=trial.TRIAL_ID, OUTPUT=trial.OUTPUT,
                            MAX_MICRO_USD=trial.MAX_MICRO_USD, REQUIRED_RECIPE=None):
            trial.select_writing_trial()
            store = Mock()
            store.get.return_value = {'payload': {'state': 'prepared', 'article_id': trial.TRIAL_ARTICLE,
                'authorization_date': trial.AUTHORIZED_DATE, 'maximum_requests': trial.MAX_REQUESTS,
                'maximum_micro_usd': trial.MAX_MICRO_USD, 'required_recipe': 'old-recipe'}}
            with self.assertRaisesRegex(NewsBudgetBlocked, 'recipe_contract_mismatch'):
                trial.run(store)
            store.put.assert_not_called()

    def test_new_writing_trial_never_resets_the_consumed_r12_identity(self):
        with patch.multiple(trial, TRIAL_ID=trial.TRIAL_ID, OUTPUT=trial.OUTPUT,
                            MAX_MICRO_USD=trial.MAX_MICRO_USD, REQUIRED_RECIPE=None):
            trial.select_writing_trial()
            old_id, old_output = trial.TRIAL_ID, trial.OUTPUT
            trial.select_independent_writing_trial()
            self.assertNotEqual(trial.TRIAL_ID, old_id)
            self.assertNotEqual(trial.OUTPUT, old_output)
            self.assertEqual(trial.MAX_MICRO_USD, 60000)
            self.assertEqual(trial.REQUIRED_RECIPE, 'news-editorial-recipe-2026-10-r13')
            store = Mock()
            store.get.return_value = {'payload': {'state': 'completed'}}
            with self.assertRaisesRegex(NewsBudgetBlocked, 'already_prepared_or_consumed'):
                trial.prepare(store)
            store.put.assert_not_called()

    def test_claim_grounding_trial_is_distinct_and_retains_the_small_cap(self):
        with patch.multiple(trial, TRIAL_ID=trial.TRIAL_ID, OUTPUT=trial.OUTPUT,
                            MAX_MICRO_USD=trial.MAX_MICRO_USD, REQUIRED_RECIPE=None):
            trial.select_independent_writing_trial()
            previous_id, previous_output = trial.TRIAL_ID, trial.OUTPUT
            trial.select_claim_grounding_trial()
            self.assertNotEqual(trial.TRIAL_ID, previous_id)
            self.assertNotEqual(trial.OUTPUT, previous_output)
            self.assertEqual(trial.MAX_MICRO_USD, 60000)
            self.assertEqual(trial.REQUIRED_RECIPE, 'news-editorial-recipe-2026-10-r14')

    def test_fact_plan_trial_cannot_reuse_the_consumed_grounding_trial(self):
        with patch.multiple(trial, TRIAL_ID=trial.TRIAL_ID, OUTPUT=trial.OUTPUT,
                            MAX_MICRO_USD=trial.MAX_MICRO_USD, REQUIRED_RECIPE=None):
            trial.select_claim_grounding_trial()
            previous_id, previous_output = trial.TRIAL_ID, trial.OUTPUT
            trial.select_fact_plan_trial()
            self.assertNotEqual(trial.TRIAL_ID, previous_id)
            self.assertNotEqual(trial.OUTPUT, previous_output)
            self.assertEqual(trial.MAX_MICRO_USD, 60000)
            self.assertEqual(trial.REQUIRED_RECIPE, 'news-editorial-recipe-2026-10-r15')

    def test_conservative_next_reservation_is_counted_before_provider_spend(self):
        self.rows = [{'id': 'old', 'charged_micro_usd': 224271}, {'id': 'new', 'charged_micro_usd': 97000}]
        self.reserve()
        self.client._request.assert_called_once()
        self.rows[1]['charged_micro_usd'] = 97001
        self.client._request.reset_mock()
        with self.assertRaisesRegex(NewsBudgetBlocked, 'cost_limit'):
            self.reserve()
        self.client._request.assert_not_called()

    def test_fact_brief_trial_cannot_reset_prior_language_trial_or_raise_cap(self):
        with patch.multiple(trial, TRIAL_ID=trial.TRIAL_ID, OUTPUT=trial.OUTPUT,
                            MAX_MICRO_USD=trial.MAX_MICRO_USD, REQUIRED_RECIPE=None):
            trial.select_language_editing_trial()
            previous_id, previous_output = trial.TRIAL_ID, trial.OUTPUT
            trial.select_fact_brief_trial()
            self.assertNotEqual(trial.TRIAL_ID, previous_id)
            self.assertNotEqual(trial.OUTPUT, previous_output)
            self.assertEqual(trial.MAX_MICRO_USD, 60000)
            self.assertEqual(trial.MAX_REQUESTS, 5)
            self.assertEqual(trial.REQUIRED_RECIPE, 'news-editorial-recipe-2026-10-r17')
            store = Mock()
            store.get.return_value = {'payload': {'state': 'completed'}}
            with self.assertRaisesRegex(NewsBudgetBlocked, 'already_prepared_or_consumed'):
                trial.prepare(store)
            store.put.assert_not_called()

    def test_language_trial_is_separate_and_cannot_reuse_fact_plan_authorization(self):
        with patch.multiple(trial, TRIAL_ID=trial.TRIAL_ID, OUTPUT=trial.OUTPUT,
                            MAX_MICRO_USD=trial.MAX_MICRO_USD, REQUIRED_RECIPE=None):
            trial.select_fact_plan_trial()
            previous_id, previous_output = trial.TRIAL_ID, trial.OUTPUT
            trial.select_language_editing_trial()
            self.assertNotEqual(trial.TRIAL_ID, previous_id)
            self.assertNotEqual(trial.OUTPUT, previous_output)
            self.assertEqual(trial.MAX_MICRO_USD, 60000)
            self.assertEqual(trial.REQUIRED_RECIPE, 'news-editorial-recipe-2026-10-r16')
            store = Mock()
            store.get.return_value = {'payload': {'state': 'completed'}}
            with self.assertRaisesRegex(NewsBudgetBlocked, 'already_prepared_or_consumed'):
                trial.prepare(store)
            store.put.assert_not_called()

    def test_all_new_attempts_including_unknown_usage_consume_request_limit(self):
        self.rows = [{'id': str(n), 'charged_micro_usd': 1} for n in range(trial.MAX_REQUESTS)]
        with self.assertRaisesRegex(NewsBudgetBlocked, 'request_limit'):
            self.reserve()
        self.client._request.assert_not_called()

    def test_only_priced_editorial_stages_and_budget_rpcs_are_allowed(self):
        for field, value in [('stage_key', 'ev_news_facts'), ('model_key', 'another-model'),
                             ('input_bound', True), ('output_bound', -1)]:
            original = self.body[field]
            self.body[field] = value
            with self.assertRaises(NewsBudgetBlocked):
                self.reserve()
            self.body[field] = original
        with self.assertRaisesRegex(NewsBudgetBlocked, 'budget_rpcs_only'):
            self.wrapper._request('POST', 'rpc/publish_news_article', {})
        with self.assertRaisesRegex(NewsBudgetBlocked, 'receipts_only'):
            self.wrapper.upsert('news_articles', [])
        self.client._request.assert_not_called()
        self.client.upsert.assert_not_called()

    def test_diagnostic_client_can_only_reserve_an_audit_within_the_original_cap(self):
        wrapper = trial.TrialClient(self.client, ['old'], stages={'ev_news_independent_audit'})
        with self.assertRaisesRegex(NewsBudgetBlocked, 'editorial_only'):
            wrapper._request('POST', 'rpc/reserve_news_ai', self.body)
        body = {**self.body, 'stage_key': 'ev_news_independent_audit'}
        wrapper._request('POST', 'rpc/reserve_news_ai', body)
        self.client._request.assert_called_once()

    def test_diagnostic_final_audit_is_single_use_and_cannot_approve_or_rewrite(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.multiple(trial, TRIAL_ID=trial.TRIAL_ID, OUTPUT=trial.OUTPUT,
                            MAX_MICRO_USD=trial.MAX_MICRO_USD, REQUIRED_RECIPE=None):
            trial.select_independent_writing_trial()
            public = Path(directory) / 'public.json'
            public.write_text('[]', encoding='utf-8')
            output = Path(directory) / 'report.json'
            article = {'id': trial.TRIAL_ARTICLE, 'cluster_id': 'cluster', 'status': 'quarantined',
                       'artifact_hash': 'unchanged', 'payload': {'relevance_score': 90, 'title': 'Unchanged private draft'}}
            row = {'id': 'paid-writer', 'charged_micro_usd': 12041, 'settled_at': 'known', 'provider_status': 'completed'}
            report = {'state': 'completed', 'passed': False, 'trial_id': trial.TRIAL_ID,
                      'required_recipe': trial.REQUIRED_RECIPE, 'maximum_requests': trial.MAX_REQUESTS,
                      'maximum_micro_usd': trial.MAX_MICRO_USD, 'baseline_request_ids': ['old'], 'trial_usage': [row],
                      'articles': [article], 'public_database_hash': artifact_hash([]),
                      'public_file_hash': trial.hashlib.sha256(public.read_bytes()).hexdigest()}
            output.write_text(json.dumps(report), encoding='utf-8')
            marker = {'payload': json.loads(json.dumps(report))}
            store = Mock(client=self.client)
            store.get.side_effect = lambda table, key: marker if table == 'news_ingestion_runs' else article
            check = {'article_id': trial.TRIAL_ARTICLE, 'artifact_hash': 'unchanged', 'kind': 'evidence',
                     'payload': {'fact_inventory': [{'id': 'f0', 'statement': 'Fact', 'evidence': 'Evidence'}]}}
            store.rows.side_effect = lambda table: [check] if table == 'news_quality_checks' else []
            store.public_articles.return_value = []
            self.client.select.side_effect = lambda table, **kwargs: [{'publication_enabled': False}] if table == 'news_ai_config' else [row]
            provider = Mock(stats={'provider_requests': 1})
            with patch('trial_news_review.OUTPUT', output), patch('trial_news_review.PUBLIC_FILE', public), \
                 patch('trial_news_review.NewsAi', return_value=provider), patch('trial_news_review.revalidate_trial_evidence'), \
                 patch('trial_news_review.Collector'), patch('trial_news_review.registry', return_value=[]), \
                 patch('trial_news_review.audit_article', return_value={'no_unsupported_claims': False}) as audit, \
                 patch('trial_news_review.validate_article', return_value={'originality': ['source_wording_overlap:item']}) as validate:
                article['artifact_hash'] = 'changed'
                with self.assertRaisesRegex(NewsBudgetBlocked, 'draft_changed'):
                    trial.diagnostic_final_audit(store)
                article['artifact_hash'] = 'unchanged'
                row['settled_at'] = None
                with self.assertRaisesRegex(NewsBudgetBlocked, 'usage_changed_or_unknown'):
                    trial.diagnostic_final_audit(store)
                row['settled_at'] = 'known'
                audit.assert_not_called()
                store.put.assert_not_called()
                check['payload']['audit_performed'] = True
                with self.assertRaisesRegex(NewsBudgetBlocked, 'already_reviewed'):
                    trial.diagnostic_final_audit(store)
                check['payload']['audit_performed'] = False
                result = trial.diagnostic_final_audit(store)
                self.assertFalse(result['passed'])
                self.assertFalse(result['diagnostic_final_review']['approval'])
                self.assertTrue(result['diagnostic_final_review']['audit_performed'])
                self.assertEqual(result['new_charged_or_reserved_micro_usd'], 12041)
                audit.assert_called_once_with(article['payload'], check['payload']['fact_inventory'], provider)
                self.assertEqual(validate.call_args.args[0], article['payload'])
                self.assertEqual({call.args[0] for call in store.put.call_args_list}, {'news_ingestion_runs'})
                store.publish.assert_not_called()
                marker['payload'] = store.put.call_args.args[1]['payload']
                with self.assertRaisesRegex(NewsBudgetBlocked, 'unused_matching_receipt'):
                    trial.diagnostic_final_audit(store)
                audit.assert_called_once()

    def test_config_and_authorization_are_rechecked_before_each_reservation(self):
        self.reserve()
        self.reserve()
        self.assertEqual(self.date.call_count, 2)
        self.assertEqual(self.config.call_count, 2)
        self.config.side_effect = NewsBudgetBlocked('publication enabled')
        self.client._request.reset_mock()
        with self.assertRaises(NewsBudgetBlocked):
            self.reserve()
        self.client._request.assert_not_called()

    def test_known_usage_can_still_settle_after_trial_date_expires(self):
        self.date.side_effect = NewsBudgetBlocked('date expired')
        self.wrapper._request('POST', 'rpc/settle_news_ai', {'request_key': 'known'})
        self.client._request.assert_called_once()

    def test_preparation_cannot_reset_an_existing_or_completed_trial(self):
        store = Mock()
        store.get.return_value = {'payload': {'state': 'completed'}}
        with patch('trial_news_review.revalidate_trial_evidence') as revalidate:
            with self.assertRaisesRegex(NewsBudgetBlocked, 'already_prepared_or_consumed'):
                trial.prepare(store)
        revalidate.assert_not_called()
        store.put.assert_not_called()

    def test_review_is_private_single_use_and_cannot_pass_without_current_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            public_file = Path(directory) / 'public.json'
            public_file.write_text('{"records":[]}', encoding='utf-8')
            marker = {'payload': {'state': 'prepared', 'article_id': trial.TRIAL_ARTICLE,
                       'authorization_date': trial.AUTHORIZED_DATE, 'maximum_requests': trial.MAX_REQUESTS,
                       'maximum_micro_usd': trial.MAX_MICRO_USD, 'baseline_request_ids': [],
                       'public_database_hash': artifact_hash([]),
                       'public_file_hash': trial.hashlib.sha256(public_file.read_bytes()).hexdigest()}}
            article = {'id': trial.TRIAL_ARTICLE, 'status': 'draft', 'artifact_hash': 'current',
                       'payload': {'title': 'A supported title', 'intro': 'An introduction', 'paragraphs': []}}
            store = Mock()
            store.get.side_effect = lambda table, key: marker if table == 'news_ingestion_runs' else article
            store.client = self.client
            store.public_articles.return_value = []
            store.rows.return_value = []
            self.client.select.side_effect = lambda table, **kwargs: [{'publication_enabled': False}] if table == 'news_ai_config' else []
            provider = Mock(stats={'provider_requests': 0})
            with patch('trial_news_review.PUBLIC_FILE', public_file), patch('trial_news_review.save') as save, \
                 patch('trial_news_review.NewsAi', return_value=provider), \
                 patch('trial_news_review.revalidate_trial_evidence', return_value=[]), \
                 patch('trial_news_review.registry', return_value=[]), patch('trial_news_review.Collector'), \
                 patch('trial_news_review.editorial', return_value=[{'status': 'validated_draft'}]) as editorial:
                report = trial.run(store)
            self.assertFalse(report['passed'])
            self.assertFalse(editorial.call_args.kwargs['publish'])
            self.assertEqual(editorial.call_args.kwargs['_only_articles'], {trial.TRIAL_ARTICLE})
            self.assertEqual(editorial.call_args.kwargs['max_revisions'], 1)
            store.publish.assert_not_called()
            self.assertTrue(report['public_database_unchanged'])
            self.assertTrue(report['public_file_unchanged'])
            self.assertEqual(store.put.call_args.args[1]['payload']['state'], 'completed')
            save.assert_called_once()

    def test_format_continuation_preserves_original_baseline_and_refuses_second_continuation(self):
        row = {'id': 'paid-format-call', 'charged_micro_usd': 5602, 'settled_at': 'known', 'provider_status': 'completed'}
        self.rows = [row]
        previous = {'state': 'completed', 'trial_usage': [row],
                    'editorial': [{'reason': 'ValueError:writer_block_alignment'}],
                    'authorization_date': trial.AUTHORIZED_DATE, 'article_id': trial.TRIAL_ARTICLE,
                    'maximum_requests': 5, 'maximum_micro_usd': 100000,
                    'public_file_hash': 'file', 'public_database_hash': 'database'}
        saved = {**previous, 'baseline_request_ids': ['old']}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            output.write_text(json.dumps(saved), encoding='utf-8')
            with patch('trial_news_review.OUTPUT', output):
                recovered = trial.resume_original(Mock(client=self.client), {'payload': previous})
                self.assertEqual(recovered['baseline_request_ids'], ['old'])
                self.assertEqual(recovered['trial_usage'], [row])
                previous['resume_count'] = 1
                with self.assertRaisesRegex(NewsBudgetBlocked, 'already_consumed'):
                    trial.resume_original(Mock(client=self.client), {'payload': previous})

    def test_format_continuation_rejects_unknown_or_changed_costs(self):
        row = {'id': 'paid-format-call', 'charged_micro_usd': 5602, 'settled_at': None, 'provider_status': 'reserved'}
        self.rows = [row]
        previous = {'state': 'completed', 'trial_usage': [row],
                    'editorial': [{'reason': 'ValueError:writer_block_alignment'}]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            output.write_text(json.dumps({**previous, 'baseline_request_ids': []}), encoding='utf-8')
            with patch('trial_news_review.OUTPUT', output):
                with self.assertRaisesRegex(NewsBudgetBlocked, 'usage_changed_or_unknown'):
                    trial.resume_original(Mock(client=self.client), {'payload': previous})

    def test_stop_verification_requires_both_switches_off_and_never_calls_ai(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / 'public.json'
            public.write_text('{"records":[]}', encoding='utf-8')
            report = {'state': 'completed', 'trial_usage': [], 'baseline_request_ids': [], 'passed': False,
                      'public_database_hash': artifact_hash([]), 'public_file_hash': trial.hashlib.sha256(public.read_bytes()).hexdigest(),
                      'public_database_unchanged': True, 'public_file_unchanged': True, 'publication_enabled': False,
                      'new_charged_or_reserved_micro_usd': 0}
            output = Path(directory) / 'report.json'
            output.write_text(json.dumps(report), encoding='utf-8')
            cfg = {'enabled': False, 'publication_enabled': False, 'daily_limit_micro_usd': 250000,
                   'monthly_limit_micro_usd': 5000000}
            self.client.select.side_effect = lambda table, **kwargs: [cfg] if table == 'news_ai_config' else []
            store = Mock(client=self.client)
            store.get.return_value = {'payload': report}
            store.public_articles.return_value = []
            self.date.side_effect = AssertionError('Shutdown must remain verifiable after authorization expires')
            with patch('trial_news_review.OUTPUT', output), patch('trial_news_review.PUBLIC_FILE', public), \
                 patch('trial_news_review.save'), patch('trial_news_review.NewsAi') as provider:
                self.assertTrue(trial.verify_stop(store)['owner_shutdown_verified'])
                for key in ['enabled', 'publication_enabled']:
                    cfg[key] = True
                    with self.assertRaisesRegex(NewsBudgetBlocked, 'shutdown_not_verified'):
                        trial.verify_stop(store)
                    cfg[key] = False
                provider.assert_not_called()
            self.client._request.assert_not_called()


class NewsWritingAuthorizationTests(unittest.TestCase):
    def test_recipe_change_cannot_reuse_writing_authorization(self):
        with patch('trial_news_review.datetime') as clock, \
             patch('trial_news_review.REQUIRED_RECIPE', 'news-editorial-recipe-2026-10-r12'), \
             patch('trial_news_review.EDITORIAL_RECIPE', 'news-editorial-recipe-2026-10-r13'):
            clock.now.return_value.date.return_value.isoformat.return_value = trial.AUTHORIZED_DATE
            with self.assertRaisesRegex(NewsBudgetBlocked, 'authorized_recipe_changed'):
                trial.require_date()


if __name__ == '__main__':
    unittest.main()
