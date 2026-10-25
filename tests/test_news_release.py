import copy
import io
import json
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from collections import Counter
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_editorial import repetition_errors
from news_engine import attach_cluster, editorial, main
from news_store import NewsStore, EDITORIAL_POLICY
from news_ai import MODEL, NewsAi, NewsBudgetBlocked, NewsProviderError, NewsProviderResponse


def response():
    return {'model': MODEL, 'service_tier': 'default', 'status': 'completed',
            'usage': {'input_tokens': 200, 'output_tokens': 100},
            'output': [{'content': [{'type': 'output_text', 'text': '{"ok":true}'}]}]}


class NewsReleaseTests(unittest.TestCase):
    def test_repeated_final_specification_dump_is_rejected(self):
        paragraphs = [{'text': f'Distinct reporting passage {n}.', 'kind': 'reporting', 'fact_ids': [f'f{n}']} for n in range(3)]
        paragraphs.append({'text': 'Summary repeats every specification.', 'kind': 'reporting', 'fact_ids': ['f0','f1','f2','f3']})
        self.assertIn('repeated_fact_coverage:p3', repetition_errors({'paragraphs': paragraphs}))

    def test_intro_overlap_and_genuine_analysis_are_allowed(self):
        article = {'intro': 'Battery and charging overview.', 'intro_fact_ids': ['f0', 'f1'], 'paragraphs': [
            {'text': 'Battery technical detail.', 'kind': 'reporting', 'fact_ids': ['f0']},
            {'text': 'Charging technical detail.', 'kind': 'reporting', 'fact_ids': ['f1']},
            {'text': 'A conditional question for the buyer.', 'kind': 'analysis', 'fact_ids': ['f0','f1']}]}
        self.assertEqual(repetition_errors(article), [])

    def test_repeated_wording_cannot_hide_behind_new_citation_ids(self):
        text = ' '.join(f'word{n}' for n in range(30))
        paragraphs = [{'text': text, 'kind': 'reporting', 'fact_ids': [key]} for key in ['f0','f1']]
        self.assertIn('repeated_passage:p1', repetition_errors({'paragraphs': paragraphs}))

    def exercise_revision(self, successful, publish=True):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, fixtures.item(), fixtures.extraction())
            facts = [{**f, 'id': item['id'] + ':f' + str(i), 'item_id': item['id']} for i, f in enumerate(fixtures.extraction()['facts'])]
            calls = Counter()
            def ai(name, schema, prompt):
                calls[name] += 1
                bad = not successful or calls['swedish_ev_article'] == 1
                if name == 'swedish_ev_article':
                    draft = fixtures.draft()
                    draft['title_fact_ids'] = [facts[0]['id']]
                    draft['intro_fact_ids'] = [f['id'] for f in facts]
                    for p in draft['paragraphs']: p['fact_ids'] = [f['id'] for f in facts]
                    if bad: draft['paragraphs'][0]['text'] += ' Felaktig effekt är 999 kW.'
                    return fixtures.writer_result(draft)
                audit = fixtures.audit(facts)
                return fixtures.keyed_audit(audit)
            with patch('news_engine.models_for_news', return_value={}):
                publisher = Mock(wraps=store.publish)
                store.publish = publisher
                reports = editorial(store, ai=ai, publish=publish)
                expected = ('published' if publish else 'validated_draft') if successful else 'quarantined'
                self.assertEqual(reports[0]['status'], expected, reports)
                self.assertEqual(calls['swedish_ev_article'], 2)
                self.assertEqual(calls['ev_news_independent_audit'], 1 if successful else 0)
                before = calls.copy()
                next_report = editorial(store, ai=ai, retry=True, publish=publish)
                self.assertEqual(next_report, [{'article_id': reports[0]['article_id'], 'status': 'validated_draft'}]
                                 if successful and not publish else [])
                self.assertEqual(calls, before)
                if not publish:
                    publisher.assert_not_called()
                    self.assertEqual(store.public_articles(), [])
                    if successful:
                        self.assertEqual(editorial(store, ai=ai)[0]['status'], 'published')
                        self.assertEqual(calls, before)
            self.assertEqual(store.rows('news_articles')[0]['payload']['revision_count'], 1)
            store.close()

    def test_one_automatic_revision_audits_only_the_repaired_draft(self):
        self.exercise_revision(True)

    def test_failed_revision_stays_quarantined_across_future_runs(self):
        self.exercise_revision(False)

    def test_staging_repairs_and_validates_without_publication_then_resumes_without_ai(self):
        self.exercise_revision(True, publish=False)

    def test_stage_only_command_never_exports_public_files(self):
        with tempfile.TemporaryDirectory() as directory:
            argv = ['news_engine.py', 'run', '--backend', 'sqlite', '--db', str(Path(directory) / 'news.sqlite'), '--stage-only']
            with patch('sys.argv', argv), patch('news_engine.load_local_env'), patch('news_engine.registry', return_value=[]), \
                 patch('news_engine.collect', return_value={}), patch('news_engine.export_public') as exporter, \
                 patch('builtins.print') as printer, patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
                main()
                exporter.assert_not_called()
                self.assertIn('stage_only', printer.call_args.args[0])

    def test_old_policy_checks_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NewsStore(Path(directory) / 'news.sqlite')
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, fixtures.item(), fixtures.extraction())
            article = store.put('news_articles', {'id': 'a', 'cluster_id': item['cluster_id'], 'slug': 'test-news',
                                                'status': 'draft', 'payload': fixtures.draft()})
            for kind in ['evidence','editorial','originality']:
                store.put('news_quality_checks', {'id': kind, 'article_id': 'a', 'kind': kind,
                          'artifact_hash': article['artifact_hash'], 'passed': True, 'payload': {'policy_version': 'old'}})
            with self.assertRaisesRegex(ValueError, 'quality_gates'): store.publish('a')
            store.close()


class NewsAiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict('os.environ', {'OPENAI_API_KEY': 'test-not-a-real-key', 'NEWS_OPENAI_MODEL': MODEL})
        self.env.start(); self.addCleanup(self.env.stop)
        self.loader = patch('news_ai.load_local_env'); self.loader.start(); self.addCleanup(self.loader.stop)
        self.client = Mock()
        self.client.select.return_value = []
        self.client._request.side_effect = lambda method, path, body: {'allowed': True} if path.endswith('reserve_news_ai') else {'settled': True}
        self.transport = Mock(return_value=response())
        self.ai = NewsAi(self.client, self.transport)

    def test_reservation_precedes_provider_and_usage_is_settled(self):
        events = []
        def rpc(method, path, body):
            events.append(path)
            return {'allowed': True} if path.endswith('reserve_news_ai') else {'settled': True}
        self.client._request.side_effect = rpc
        self.transport.side_effect = lambda payload, **kwargs: (events.append('provider') or response())
        self.assertEqual(self.ai('swedish_ev_article', {}, 'facts'), {'ok': True})
        self.assertEqual(events, ['rpc/reserve_news_ai', 'provider', 'rpc/settle_news_ai'])
        payload = self.transport.call_args.args[0]
        self.assertEqual(payload['service_tier'], 'default')
        self.assertFalse(payload['store'])
        self.assertEqual(payload['max_output_tokens'], 2500)
        reserved_id = self.client._request.call_args_list[0].args[2]['request_key']
        self.assertEqual(self.transport.call_args.kwargs['request_id'], reserved_id)
        receipts = [call.args[1][0] for call in self.client.upsert.call_args_list]
        self.assertEqual([row['payload']['state'] for row in receipts], ['dispatch_pending', 'usage_observed', 'settled'])
        self.assertTrue(all(row['id'] == reserved_id for row in receipts))

    def test_missing_or_denied_budget_never_calls_provider(self):
        for outcome in [RuntimeError('schema missing'), {'allowed': False}, None]:
            self.client._request.side_effect = outcome if isinstance(outcome, Exception) else None
            self.client._request.return_value = outcome
            with self.assertRaises(NewsBudgetBlocked): self.ai('ev_news_facts', {}, 'facts')
        self.transport.assert_not_called()

    def test_unknown_usage_and_network_errors_keep_reservations(self):
        for output in [{}, {**response(), 'usage': {'input_tokens': True, 'output_tokens': 1}}]:
            self.transport.return_value = output
            self.client._request.reset_mock()
            with self.assertRaises(NewsBudgetBlocked): self.ai('ev_news_facts', {}, 'facts')
            self.assertEqual(self.client._request.call_count, 1)
        self.transport.side_effect = RuntimeError('network')
        self.client._request.reset_mock()
        with self.assertRaises(RuntimeError): self.ai('ev_news_facts', {}, 'facts')
        self.assertEqual(self.client._request.call_count, 1)

    def test_settlement_failure_does_not_return_generated_content(self):
        self.client._request.side_effect = [{'allowed': True}, RuntimeError('database unavailable')]
        with self.assertRaises(NewsBudgetBlocked): self.ai('ev_news_facts', {}, 'facts')

    def test_exact_completed_cache_resumes_without_a_paid_retry(self):
        self.client.select.return_value = [{'response_payload': response()}]
        self.assertEqual(self.ai('ev_news_facts', {}, 'same facts'), {'ok': True})
        self.transport.assert_not_called()
        self.client._request.assert_not_called()
        self.assertEqual(self.ai.stats['cache_hits'], 1)

    def test_unpriced_model_and_incomplete_output_are_rejected(self):
        with patch.dict('os.environ', {'NEWS_OPENAI_MODEL': 'another-model'}):
            with self.assertRaises(NewsBudgetBlocked): self.ai('ev_news_facts', {}, 'facts')
        self.transport.return_value = {**response(), 'status': 'incomplete'}
        with self.assertRaisesRegex(ValueError, 'incomplete'): self.ai('ev_news_facts', {}, 'facts')
        self.assertEqual(self.client._request.call_count, 2)

    def test_provider_http_diagnostics_reveal_status_not_secrets_or_response_text(self):
        with patch('news_ai.build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError('https://api.openai.com/v1/responses', 400,
                                                           'private-key-and-source-text', {}, None)
            with self.assertRaisesRegex(RuntimeError, 'news_provider_http_400_reservation_retained') as result:
                NewsAi.request({}, request_id='00000000-0000-4000-8000-000000000001')
        self.assertNotIn('private-key', str(result.exception))

    def test_provider_timeout_diagnostics_do_not_retry_or_refund_unknown_usage(self):
        with patch('news_ai.build_opener') as opener:
            opener.return_value.open.side_effect = URLError(TimeoutError('private connection details'))
            with self.assertRaisesRegex(RuntimeError, 'news_provider_timeout_reservation_retained'):
                NewsAi.request({}, request_id='00000000-0000-4000-8000-000000000001')
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_unsettled_request_blocks_new_spend_without_expiring_or_resetting_the_hold(self):
        self.client.select.side_effect = [[], [{'id': 'unresolved'}]]
        with self.assertRaisesRegex(NewsBudgetBlocked, 'requires_reconciliation'):
            self.ai('swedish_ev_article', {}, 'a changed prompt')
        self.transport.assert_not_called()
        self.client._request.assert_not_called()
        self.client.upsert.assert_not_called()
        filters = self.client.select.call_args.kwargs['filters']
        self.assertEqual(filters['settled_at'], 'is.null')
        self.assertEqual(filters['budget_closed_at'], 'is.null')
        self.assertNotIn('created_at', filters)
        self.assertNotIn('request_hash', filters)

    def test_missing_budget_closure_column_blocks_before_reservation_or_provider(self):
        self.client.select.side_effect = [[], RuntimeError('budget_closed_at column missing')]
        with self.assertRaisesRegex(NewsBudgetBlocked, 'budget_unavailable'):
            self.ai('swedish_ev_article', {}, 'facts')
        self.transport.assert_not_called()
        self.client._request.assert_not_called()
        self.client.upsert.assert_not_called()

    def test_receipt_must_be_saved_before_dispatch(self):
        self.client.upsert.side_effect = RuntimeError('database unavailable')
        with self.assertRaisesRegex(NewsBudgetBlocked, 'receipt_unavailable_reservation_retained'):
            self.ai('ev_news_facts', {}, 'facts')
        self.transport.assert_not_called()
        self.assertEqual(self.client._request.call_count, 1)

    def test_transport_errors_save_only_machine_metadata_and_never_retry_or_settle(self):
        self.transport.side_effect = NewsProviderError('http_400', {'http_status': 400, 'error_code': 'invalid_json_schema'})
        with self.assertRaises(NewsProviderError): self.ai('ev_news_facts', {}, 'private prompt')
        receipt = self.client.upsert.call_args.args[1][0]['payload']
        self.assertEqual(receipt['state'], 'provider_failed')
        self.assertEqual(receipt['error_code'], 'invalid_json_schema')
        self.assertNotIn('private prompt', json.dumps(receipt))
        self.assertNotIn('test-not-a-real-key', json.dumps(receipt))
        self.assertEqual(self.transport.call_count, 1)
        self.assertEqual(self.client._request.call_count, 1)

    def test_secondary_diagnostic_failure_does_not_mask_provider_error(self):
        self.client.upsert.side_effect = [[], RuntimeError('log unavailable')]
        self.transport.side_effect = NewsProviderError('timeout')
        with self.assertRaisesRegex(NewsProviderError, 'timeout_reservation_retained'):
            self.ai('ev_news_facts', {}, 'facts')
        self.assertEqual(self.transport.call_count, 1)

    def test_provider_header_and_safe_error_fields_are_retained_without_error_message(self):
        raw = json.dumps({'error': {'type': 'invalid_request_error', 'code': 'invalid_json_schema',
                         'param': 'text.format.schema', 'message': 'private prompt and API key'}}).encode()
        error = HTTPError('https://api.openai.com/v1/responses', 400, 'private error',
                          {'x-request-id': 'req_example_123'}, io.BytesIO(raw))
        with patch('news_ai.build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(NewsProviderError) as result:
                NewsAi.request({}, request_id='00000000-0000-4000-8000-000000000001')
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_header('X-client-request-id'), '00000000-0000-4000-8000-000000000001')
        self.assertEqual(result.exception.diagnostics, {'failure_kind': 'http_400', 'http_status': 400,
            'provider_request_id': 'req_example_123', 'error_type': 'invalid_request_error',
            'error_code': 'invalid_json_schema', 'error_param': 'text.format.schema'})
        self.assertNotIn('private', json.dumps(result.exception.diagnostics))

    def test_untrusted_provider_metadata_is_discarded(self):
        raw = json.dumps({'error': {'type': 'secret', 'code': 'secret', 'param': 'secret'}}).encode()
        with patch('news_ai.build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError('https://api.openai.com/v1/responses', 400, 'secret',
                                                            {'x-request-id': 'sk-private-key'}, io.BytesIO(raw))
            with self.assertRaises(NewsProviderError) as result:
                NewsAi.request({}, request_id='00000000-0000-4000-8000-000000000001')
        self.assertIsNone(result.exception.diagnostics['provider_request_id'])
        self.assertNotIn('secret', json.dumps(result.exception.diagnostics))
        self.assertNotIn('error_param', result.exception.diagnostics)

    def test_usage_survives_settlement_failure_in_private_receipt(self):
        self.client._request.side_effect = [{'allowed': True}, RuntimeError('database unavailable')]
        self.transport.return_value = NewsProviderResponse(response(), {'http_status': 200, 'provider_request_id': 'req_example'})
        with self.assertRaises(NewsBudgetBlocked): self.ai('ev_news_facts', {}, 'facts')
        receipt = self.client.upsert.call_args.args[1][0]['payload']
        self.assertEqual(receipt['state'], 'settlement_unavailable')
        self.assertEqual(receipt['input_tokens'], 200)
        self.assertEqual(receipt['output_tokens'], 100)
        self.assertEqual(receipt['provider_request_id'], 'req_example')

    def test_malformed_or_oversized_response_preserves_specific_error_and_request_id(self):
        for raw, kind in [(b'{broken', 'invalid_json'), (b'\xff', 'invalid_json'),
                          (b'[]', 'object_required'), (b'x' * 250001, 'response_too_large')]:
            with self.subTest(kind=kind), patch('news_ai.build_opener') as opener:
                reply = opener.return_value.open.return_value.__enter__.return_value
                reply.status = 200
                reply.headers = {'x-request-id': 'req_response'}
                reply.read.return_value = raw
                with self.assertRaisesRegex(NewsProviderError, kind) as result:
                    NewsAi.request({}, request_id='00000000-0000-4000-8000-000000000001')
                self.assertEqual(result.exception.diagnostics['provider_request_id'], 'req_response')
                self.assertEqual(opener.return_value.open.call_count, 1)

    def test_successful_transport_metadata_is_not_added_to_provider_response_body(self):
        with patch('news_ai.build_opener') as opener:
            reply = opener.return_value.open.return_value.__enter__.return_value
            reply.status = 200
            reply.headers = {'x-request-id': 'req_success'}
            reply.read.return_value = json.dumps(response()).encode()
            result = NewsAi.request({}, request_id='00000000-0000-4000-8000-000000000001')
        self.assertEqual(json.loads(json.dumps(result)), response())
        self.assertEqual(result.diagnostics, {'http_status': 200, 'provider_request_id': 'req_success'})

    def test_invalid_client_id_is_rejected_before_network(self):
        with patch('news_ai.build_opener') as opener:
            with self.assertRaises(ValueError): NewsAi.request({}, request_id='invalid\r\nheader')
            opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
