"""Synthetic fact-first regressions, never live editorial qualification."""
import copy
from contextlib import ExitStack, closing
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_fact_first as contract
import run_fact_first_news as worker
import test_news_publisher_articles as base
from test_news_official_operation import fixture as official_fixture
from news_ai import NewsAi
from news_publisher_articles import brief
from news_publisher_articles import precheck, stage
from news_reporting_policy import RECIPE as OLD_RECIPE
from news_store import NewsStore, artifact_hash

NOW = base.NOW


def fixture():
    bundle, packet = official_fixture()
    packet['extraction']['facts'] = packet['extraction']['facts'][:4]
    raw = base.encoded_fixture(bundle, packet)['extraction']
    locked = contract.lock_facts(bundle, raw, NOW)
    output = {
        'title': 'Nordic Cells planerar laboratorieprojekt om elbilsbatterier',
        'intro': 'Enligt Volkswagen Newsroom planerar Nordic Cells ett forskningsprojekt om batterier '
                 'för eldrivna personbilar i Europa.',
        'p0': 'Upplägget är att jämföra två olika batterikonstruktioner, med en och samma laboratoriemetod '
              'för båda alternativen.',
        'p1': 'Båda konstruktionerna ska undersökas inomhus under kontrollerade förhållanden, innan arbetet '
              'går vidare till ytterligare utveckling.',
        'p2': 'Programmet omfattar också laddningsmätningar och upprepade cykler i laboratoriet.'}
    bound = contract.bind_article(locked, output)
    review = base.accepted_review(bundle, bound)
    review['brief_hash'] = brief(bundle, bound, recipe=contract.RECIPE)['brief_hash']
    return bundle, raw, locked, output, review


class FactPacketTests(unittest.TestCase):
    def test_three_separate_contracts_and_fixed_citations(self):
        b, raw, locked, output, review = fixture()
        packet = contract.bind_article(locked, output)
        checked = contract.packet_check(b, locked, output, NOW)
        self.assertTrue(checked['passed'], checked)
        self.assertTrue(50 <= checked['word_count'] <= 120)
        self.assertEqual(contract.review_check(b, packet, review), [])
        self.assertEqual(list(contract.LIMITS), ['ev_news_facts', 'swedish_ev_article', 'ev_news_independent_audit'])
        self.assertEqual(packet['article']['paragraphs'][0]['fact_ids'], ['f2'])
        self.assertEqual(contract.writer_call(locked)[1]['required'], ['title', 'intro', 'p0', 'p1', 'p2'])
        self.assertNotIn('article', contract.extraction_call(b)[1]['properties'])
        self.assertNotIn('extraction', contract.writer_call(locked)[1]['properties'])

    def test_old_recipe_keeps_its_word_limit_and_receipt_contract(self):
        b, _, locked, output, review = fixture()
        packet = contract.bind_article(locked, output)
        self.assertIn('publisher_word_count_outside_80_250', precheck(b, packet, NOW)['errors'])
        self.assertNotEqual(contract.RECIPE, OLD_RECIPE)
        self.assertIn('hybrid_review_artifact_changed', __import__('news_publisher_articles').check_review(b, packet, review))

    def test_ten_offline_fact_and_prose_outcomes(self):
        cases = ('valid', 'unsupported_number', 'bad_evidence', 'wrong_event', 'wrong_source_hash',
                 'changed_lock', 'extra_slot', 'uncited_equipment', 'missing_attribution', 'too_short')
        for case in cases:
            with self.subTest(case=case):
                b, raw, locked, output, _ = fixture()
                if case == 'unsupported_number': raw['facts'][0]['statement'] += ' 999 kWh.'
                if case == 'bad_evidence': raw['facts'][0]['support'] = [{'evidence_id': 'invented'}]
                if case == 'wrong_event': raw['event']['date'] = '1999-01-01'
                if case == 'wrong_source_hash': b['bundle_hash'] = '0' * 64
                if case == 'changed_lock': locked['extraction']['facts'][0]['statement'] += ' Extra.'
                if case == 'extra_slot': output['p9'] = 'Unassigned prose.'
                if case == 'uncited_equipment': output['p0'] += ' Bilen har dessutom ny utrustning.'
                if case == 'missing_attribution': output['intro'] = output['intro'].replace('Enligt Volkswagen Newsroom ', '')
                if case == 'too_short': output['p0'] = 'Två batterier jämförs.'
                try:
                    if case in ('unsupported_number', 'bad_evidence', 'wrong_event'):
                        contract.lock_facts(b, raw, NOW)
                        passed = True
                    else:
                        passed = contract.packet_check(b, locked, output, NOW)['passed']
                except ValueError:
                    passed = False
                self.assertEqual(passed, case == 'valid', case)

    def test_source_context_and_conditions_reach_independent_reviewer(self):
        b, _, locked, output, _ = fixture()
        prompt = contract.review_call(b, contract.bind_article(locked, output))[2]
        self.assertIn('50-120', prompt)
        self.assertIn(b['items'][0]['payload']['content'][:70], prompt)
        self.assertIn('indoor', prompt)

    def test_maximal_pipeline_budget_is_preflighted(self):
        b, _, locked, output, _ = fixture()
        ai = NewsAi(client=object(), model='gpt-6-sol', output_limits=contract.LIMITS)
        bound = contract.pipeline_bound(ai, b)
        calls = [contract.extraction_call(b), contract.writer_call(locked),
                 contract.review_call(b, contract.bind_article(locked, output))]
        self.assertLessEqual(sum(contract.call_bound(ai, c) for c in calls), bound)
        self.assertLess(bound, 500000)

    def test_language_wordlist_is_diagnostic_not_a_short_article_veto(self):
        b, _, locked, output, _ = fixture()
        output = {key: 'Independent English fixture text with names Nordic Cells Volkswagen Newsroom and project details.'
                  for key in output}
        packet = contract.bind_article(locked, output)
        self.assertIn('publisher_not_swedish', precheck(b, packet, NOW)['errors'])
        self.assertNotIn('publisher_not_swedish', contract.packet_check(b, locked, output, NOW)['errors'])
        review = base.accepted_review(b, packet)
        review['brief_hash'] = brief(b, packet, recipe=contract.RECIPE)['brief_hash']
        review['swedish_quality'] = False
        self.assertIn('hybrid_review_rejected:swedish_quality', contract.review_check(b, packet, review))


class FactFirstLifecycleTests(unittest.TestCase):
    def environment(self, stack, folder, *, corruption=None, allowance=500000):
        b, raw, locked, output, review = fixture()
        store = NewsStore(Path(folder) / 'synthetic.sqlite')
        stack.callback(store.close)
        class Client:
            def __init__(self): self.receipts = []
            def select(self, table, **kwargs):
                if table != 'news_ai_requests': raise AssertionError(table)
                return self.receipts
        store.client = Client()
        class Ai:
            model = 'gpt-6-sol'
            output_limits = contract.LIMITS
            payload = NewsAi.payload
            def __init__(self): self.calls = []
            def __call__(self, name, schema, prompt):
                self.calls.append(name)
                if name == 'swedish_ev_article':
                    saved = store.rows('news_ingestion_runs')[0]['payload']
                    assert saved['locked'] == locked, 'Fact lock must be persisted BEFORE writing'
                value = copy.deepcopy({'ev_news_facts': raw, 'swedish_ev_article': output,
                                       'ev_news_independent_audit': review}[name])
                if corruption == 'facts' and name == 'ev_news_facts': value['facts'][0]['statement'] += ' 999 kWh.'
                if corruption == 'article' and name == 'swedish_ev_article': value['p0'] += ' 999 kWh.'
                payload = json.dumps(self.payload(name, schema, prompt), ensure_ascii=False).encode()
                store.client.receipts.append({'id': str(len(self.calls)), 'created_at': NOW.isoformat(),
                    'stage': name, 'model': self.model, 'settled_at': NOW.isoformat(), 'budget_closed_at': None,
                    'provider_status': 'completed', 'charged_micro_usd': 1000, 'reserved_micro_usd': 1000,
                    'request_hash': hashlib.sha256(payload).hexdigest(),
                    'response_payload': {'status': 'completed', 'output': [{'content': [
                        {'type': 'output_text', 'text': json.dumps(value, ensure_ascii=False)}]}]}})
                if corruption == 'unknown':
                    store.client.receipts[-1].update(settled_at=None, provider_status='reserved')
                    raise RuntimeError('Synthetic unknown use')
                return value
        original_readiness, original_lock = contract.readiness, contract.lock_facts
        original_check, original_stage = contract.packet_check, contract.stage_article
        stack.enter_context(patch.object(contract, 'readiness', side_effect=lambda bundle, now=None: original_readiness(bundle, now or NOW)))
        stack.enter_context(patch.object(contract, 'lock_facts', side_effect=lambda bundle, value, now=None: original_lock(bundle, value, now or NOW)))
        stack.enter_context(patch.object(contract, 'packet_check', side_effect=lambda bundle, lock, value, now=None: original_check(bundle, lock, value, now or NOW)))
        stack.enter_context(patch.object(contract, 'stage_article', side_effect=lambda st, record, **kw: original_stage(st, record, now=NOW, **kw)))
        stack.enter_context(patch.object(worker, 'matrix_valid', return_value=True))
        stack.enter_context(patch.object(worker, 'load_state', return_value={}))
        stack.enter_context(patch.object(worker, 'now_iso', return_value=NOW.isoformat()))
        stack.enter_context(patch.object(worker, 'DIRECTORY', Path(folder) / 'synthetic-records'))
        stack.enter_context(patch.object(worker, 'budget', side_effect=lambda st, required=0: {'allowed': required <= allowance}))
        return store, b, Ai()

    def test_exact_three_settled_calls_no_publication_and_no_retry(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, bundle, ai = self.environment(stack, folder)
            result = worker.perform(remote, bundle, private=True, ai=ai)
            self.assertEqual(result['status'], 'passed', result)
            self.assertTrue(worker.reviewed(remote, result))
            self.assertEqual(ai.calls, list(contract.LIMITS))
            self.assertEqual(result['cost_micro_usd'], 3000)
            self.assertEqual(remote.public_articles(), [])
            self.assertEqual(worker.perform(remote, bundle, private=True, ai=ai)['status'], 'historical_url_held')
            self.assertEqual(len(ai.calls), 3)
            remote.client.receipts[0]['request_hash'] = '0' * 64
            self.assertFalse(worker.reviewed(remote, result))
            result['writer_output']['p0'] += ' Altered text.'
            self.assertFalse(worker.reviewed(remote, result))

    def test_invalid_facts_stop_before_writer_and_invalid_prose_before_reviewer(self):
        for corruption, expected in [('facts', 1), ('article', 2)]:
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                remote, bundle, ai = self.environment(stack, folder, corruption=corruption)
                result = worker.perform(remote, bundle, private=True, ai=ai)
                self.assertEqual(result['status'], 'quarantined', result)
                self.assertEqual(len(ai.calls), expected)
                self.assertFalse(result['review_performed'])

    def test_whole_pipeline_must_fit_before_first_paid_call(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, bundle, ai = self.environment(stack, folder, allowance=1)
            result = worker.perform(remote, bundle, private=True, ai=ai)
            self.assertEqual(result['status'], 'deferred_budget')
            self.assertEqual(ai.calls, [])
            self.assertEqual(remote.rows('news_ingestion_runs'), [])

    def test_unknown_usage_keeps_charge_and_stops(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, bundle, ai = self.environment(stack, folder, corruption='unknown')
            result = worker.perform(remote, bundle, private=True, ai=ai)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['cost_status'], 'reservation_retained_usage_unknown')
            self.assertEqual(result['cost_micro_usd'], 1000)
            self.assertEqual(len(ai.calls), 1)

    def test_private_success_is_not_release_permission(self):
        with self.assertRaisesRegex(ValueError, 'fresh_production_review'):
            worker.release(None, {'kind': 'publisher_private_trial'}, None)

    def test_scheduler_cannot_buy_qualification_and_owner_completion_needs_today(self):
        with patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}), \
             patch.object(worker, 'qualification', return_value={'passed': False, 'real_private_successes': 0}), \
             patch.object(worker, 'perform', side_effect=AssertionError('No paid call')):
            self.assertEqual(worker.daily(None, None)['status'], 'qualification_required')
            with self.assertRaisesRegex(ValueError, 'current_day_owner'):
                worker.daily(None, None, complete_qualification=True)

    def test_two_types_require_real_reviewed_records_and_a_private_success(self):
        cases = [
            {'kind': 'publisher_private_trial', 'recipe': contract.RECIPE, 'state': 'passed',
             'checked_at': NOW.isoformat(), 'bundle': {}, 'packet': {'extraction': {'category': 'batterier'}}},
            {'kind': 'short_daily', 'recipe': contract.RECIPE, 'state': 'passed',
             'checked_at': NOW.isoformat(), 'bundle': {}, 'packet': {'extraction': {'category': 'laddning'}}}]
        class Remote:
            def rows(self, table): return [{'payload': p} for p in cases]
        with patch.object(worker, 'reviewed', return_value=False):
            self.assertFalse(worker.qualification(Remote())['passed'])
        with patch.object(worker, 'reviewed', return_value=True), \
             patch.object(contract, 'readiness', return_value={'ready': True}) as ready:
            self.assertTrue(worker.qualification(Remote())['passed'])
            self.assertEqual(ready.call_args[0][1], NOW, 'Historic qualification is checked at its real audit time')
            cases[1]['packet']['extraction']['category'] = 'batterier'
            self.assertFalse(worker.qualification(Remote())['passed'])

    def completion_parent(self, remote, bundle, ai):
        raw = ai(*contract.extraction_call(bundle))
        locked = contract.lock_facts(bundle, raw, NOW)
        parent = {'kind': 'publisher_private_trial', 'recipe': contract.RECIPE, 'state': 'quarantined',
            'status': 'quarantined', 'started_at': NOW.isoformat(), 'source_id': bundle['items'][0]['source_id'],
            'url': bundle['items'][0]['url'], 'bundle': bundle, 'fact_output': raw, 'locked': locked,
            'errors': ['publisher_not_swedish'], 'review_performed': False, 'cost_status': 'settled',
            'request_ids': ['1', '2'], 'cost_micro_usd': 2000, 'published': 0}
        remote.put('news_ingestion_runs', {'id': 'synthetic-parent', 'payload': parent})
        parent['writer_output'] = ai(*contract.writer_call(locked))
        parent['packet'] = contract.bind_article(locked, parent['writer_output'])
        remote.put('news_ingestion_runs', {'id': 'synthetic-parent', 'payload': parent})
        return copy.deepcopy(parent)

    def test_separately_approved_completion_buys_only_one_audit_and_preserves_parent(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, bundle, ai = self.environment(stack, folder)
            parent = self.completion_parent(remote, bundle, ai)
            stack.enter_context(patch.object(worker, 'refresh_bundle', return_value=copy.deepcopy(bundle)))
            result = worker.complete_trial(remote, 'synthetic-parent', None, NOW.date().isoformat(), ai=ai)
            self.assertEqual(result['status'], 'passed', result)
            self.assertEqual(ai.calls, list(contract.LIMITS))
            self.assertEqual(result['new_cost_micro_usd'], 1000)
            self.assertEqual(result['cost_micro_usd'], 3000)
            self.assertEqual(remote.get('news_ingestion_runs', 'synthetic-parent')['payload'], parent)
            self.assertTrue(worker.reviewed(remote, result))
            self.assertTrue(worker.complete_trial(remote, 'synthetic-parent', None,
                NOW.date().isoformat(), ai=ai)['reused_completion'])
            self.assertEqual(len(ai.calls), 3)
            self.assertEqual(remote.public_articles(), [])

    def test_completion_cannot_bypass_other_errors_changed_source_or_missing_owner_day(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, bundle, ai = self.environment(stack, folder)
            parent = self.completion_parent(remote, bundle, ai)
            with self.assertRaisesRegex(ValueError, 'current_day_owner'):
                worker.complete_trial(remote, 'synthetic-parent', None, None, ai=ai)
            parent['errors'] = ['unsupported_number']
            remote.put('news_ingestion_runs', {'id': 'synthetic-parent', 'payload': parent})
            with self.assertRaisesRegex(ValueError, 'language_only_parent'):
                worker.complete_trial(remote, 'synthetic-parent', None, NOW.date().isoformat(), ai=ai)
            parent['errors'] = ['publisher_not_swedish']
            remote.put('news_ingestion_runs', {'id': 'synthetic-parent', 'payload': parent})
            altered = copy.deepcopy(parent)
            altered['packet']['article']['title'] += ' altered'
            remote.put('news_ingestion_runs', {'id': 'synthetic-parent', 'payload': altered})
            with self.assertRaisesRegex(ValueError, 'artifact_or_other_gate_changed'):
                worker.complete_trial(remote, 'synthetic-parent', None, NOW.date().isoformat(), ai=ai)
            remote.put('news_ingestion_runs', {'id': 'synthetic-parent', 'payload': parent})
            changed = copy.deepcopy(bundle)
            changed['items'][0]['payload']['content_hash'] = '0' * 64
            stack.enter_context(patch.object(worker, 'refresh_bundle', return_value=changed))
            with self.assertRaisesRegex(ValueError, 'source_changed'):
                worker.complete_trial(remote, 'synthetic-parent', None, NOW.date().isoformat(), ai=ai)
            self.assertEqual(len(ai.calls), 2, 'No new audit was bought')


if __name__ == '__main__':
    unittest.main()
