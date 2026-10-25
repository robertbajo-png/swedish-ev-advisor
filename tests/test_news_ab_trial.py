"""Offline A/B contracts. These fixtures are not generated news or publication approval."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import trial_news_ab_r26 as trial
from news_ai import MODEL, NewsAi, NewsBudgetBlocked
from news_store import artifact_hash


class AbTrialTests(unittest.TestCase):
    def test_frozen_contract_contains_exact_models_no_publication_cache_or_revisions(self):
        frozen = {'trial_id': trial.TRIAL_ID, 'recipe': trial.RECIPE, 'cap_micro_usd': 200000,
                  'models': [list(m) for m in trial.MODELS], 'review_model': MODEL,
                  'assignments': trial.ASSIGNMENTS, 'max_requests': 18, 'publish': False,
                  'cache': False, 'revisions': 0, 'items': {'vw-sweden-press': {}, 'acea': {}}}
        with patch.object(Path, 'read_text', return_value=json.dumps(frozen)):
            self.assertEqual(trial.manifest(), frozen)
        for key, bad in [('publish', True), ('cache', True), ('revisions', 1), ('max_requests', 19),
                         ('review_model', 'gpt-5.4'), ('models', [['full', 'another-model']])]:
            with self.subTest(key=key), patch.object(Path, 'read_text', return_value=json.dumps({**frozen, key: bad})):
                with self.assertRaises(NewsBudgetBlocked): trial.manifest()
        self.assertEqual(set(trial.ASSIGNMENTS), {'model', 'price', 'statistics'})
        self.assertEqual(set(m for _, m in trial.MODELS), {MODEL, 'gpt-5.4'})

    def test_ab_reserves_only_through_private_permit_but_can_settle_after_expiry(self):
        client = Mock()
        client.select.return_value = [{'id': 'request'}]
        wrapped = trial.AbClient(client, 'a'*64, 'price-full')
        with patch.object(trial, 'authorize') as authorize:
            wrapped._request('POST', 'rpc/reserve_news_ai', {'model_key': 'gpt-5.4'})
            authorize.assert_called_once()
        args = client._request.call_args.args
        self.assertEqual(args[:2], ('POST', 'rpc/reserve_news_ab_ai'))
        self.assertEqual(args[2]['permit_key'], trial.TRIAL_ID)
        self.assertEqual(args[2]['cell_key'], 'price-full')
        with patch.object(trial, 'authorize', side_effect=NewsBudgetBlocked('expired')):
            wrapped._request('POST', 'rpc/settle_news_ai', {'request_key': 'request'})
        self.assertEqual(client._request.call_args.args[1], 'rpc/settle_news_ab_ai')
        with self.assertRaises(NewsBudgetBlocked): wrapped.upsert('news_articles', [])
        with self.assertRaises(NewsBudgetBlocked): wrapped._request('POST', 'rpc/publish_news_article', {})
        client.select.return_value = []
        with self.assertRaises(NewsBudgetBlocked): wrapped._request('POST', 'rpc/settle_news_ai', {'request_key': 'alien'})

    def test_default_model_unchanged_and_cacheless_full_model_reserves_before_dispatch(self):
        client = Mock()
        client.select.return_value = []
        events = []
        def rpc(method, path, body):
            events.append(path)
            return {'allowed': True} if path.endswith('reserve_news_ai') else {'settled': True}
        client._request.side_effect = rpc
        def transport(payload, **kwargs):
            events.append('provider')
            return {'model': payload['model'], 'status': 'completed', 'service_tier': 'default',
                    'usage': {'input_tokens': 50, 'output_tokens': 10},
                    'output': [{'content': [{'type': 'output_text', 'text': '{"ok":true}'}]}]}
        provider = Mock(side_effect=transport)
        with patch('news_ai.load_local_env'), patch.dict('os.environ', {'OPENAI_API_KEY': 'test', 'NEWS_OPENAI_MODEL': MODEL}):
            self.assertEqual(NewsAi(client).model, MODEL)
            ai = NewsAi(client, provider, model='gpt-5.4', cache_enabled=False)
            self.assertTrue(ai('swedish_ev_article', {}, 'same frozen evidence')['ok'])
            self.assertEqual(events, ['rpc/reserve_news_ai', 'provider', 'rpc/settle_news_ai'])
            self.assertEqual(client.select.call_count, 1)  # pending check only, never a cache lookup
            self.assertEqual(provider.call_args.args[0]['model'], 'gpt-5.4')
            self.assertEqual(client._request.call_args_list[0].args[2]['model_key'], 'gpt-5.4')
            with self.assertRaises(NewsBudgetBlocked): NewsAi(client, provider, model='gpt-other')('ev_news_facts', {}, 'x')
            self.assertEqual(provider.call_count, 1)

    def test_budget_retains_unknown_old_hold_and_ordinary_caps(self):
        remote = Mock()
        config = {'enabled': False, 'publication_enabled': False, 'model': MODEL,
                  'daily_limit_micro_usd': 250000, 'monthly_limit_micro_usd': 5000000,
                  'pricing_valid_until': '2026-11-21'}
        rows = [{'id': 'old', 'created_at': '2026-10-22', 'charged_micro_usd': 20868,
                 'settled_at': None, 'budget_closed_at': 'owner-conservative-close'}]
        remote.client.select.side_effect = lambda table, **kw: [config] if table=='news_ai_config' else rows
        with patch.object(trial, 'authorize'):
            self.assertEqual(trial.budget(remote)['monthly_used_micro_usd'], 20868)
            self.assertTrue(trial.budget(remote)['allowed'])
            rows[0].update(created_at=trial.DATE, charged_micro_usd=60000)
            self.assertFalse(trial.budget(remote)['allowed'])
            rows[0].update(charged_micro_usd=1, budget_closed_at=None)
            self.assertFalse(trial.budget(remote)['allowed'])
            config['enabled'] = True
            with self.assertRaises(NewsBudgetBlocked): trial.budget(remote)
        remote.client._request.assert_not_called()

    def test_same_source_and_assignment_both_models_common_blind_reviewer_and_failed_gate_stays_failed(self):
        item = {'id': 'item', 'url': 'https://official.example/news', 'payload': {'content_hash': 'a'*64,
                'publisher': 'Official', 'published_at': '2026-10-23T00:00:00+00:00', 'title': 'News', 'reliability': .9}}
        frozen = {'items': {'vw-sweden-press': item}, 'model_keys': ['id-cross'], 'at': '2026-10-23T09:00:00+00:00'}
        extraction = {'category': 'modeller', 'facts': []}
        fake = Mock(return_value=extraction)
        fake.stats = {'provider_requests': 0, 'cache_hits': 0}
        prompts = []
        def extract(source, keys, ai):
            prompts.append((artifact_hash(source), keys))
            return ai('ev_news_facts', {}, 'frozen source text')
        article = {'title': 'Independent text', 'paragraphs': [], 'intro': 'Intro'}
        review_prompts = []
        def audit(draft, facts, reviewer):
            review_prompts.append(copy.deepcopy(draft))
            return {'supported': True}
        store = Mock()
        store.put.side_effect = lambda table, row: copy.deepcopy(row)
        with patch.object(trial, 'NewsAi', return_value=fake) as factory, \
             patch.object(trial, 'extract_facts', side_effect=extract), \
             patch.object(trial, 'partition_fact_extraction', return_value=(extraction, [], ['insufficient_swedish_relevance'])), \
             patch.object(trial, 'inventory', return_value=[{'id':'f1'}, {'id':'f2'}, {'id':'f3'}]), \
             patch.object(trial, 'generate_article', side_effect=lambda *a: copy.deepcopy(article)), \
             patch.object(trial, 'article_preflight', return_value={'errors':['article_too_short'], 'word_count':137}), \
             patch.object(trial, 'relevance_score', return_value=.62), \
             patch.object(trial, 'audit_article', side_effect=audit), \
             patch.object(trial, 'validate_article', side_effect=lambda d,f,i,a,s: {'evidence': [] if a else ['independent_audit_not_run']}):
            for label, model in trial.MODELS:
                result = trial.run_cell(Mock(), frozen, 'model', label, model, store)
                self.assertFalse(result['normal_passed'])
                self.assertTrue(result['diagnostic_only'])
                self.assertEqual(result['gate_errors']['evidence'], ['independent_audit_not_run'])
        self.assertEqual(prompts[0], prompts[1])
        self.assertEqual(fake.call_args_list[0].args[2], fake.call_args_list[1].args[2])
        self.assertEqual(review_prompts[0], review_prompts[1])
        self.assertEqual([c.kwargs['model'] for c in factory.call_args_list], ['gpt-5.4', MODEL, MODEL, MODEL])
        self.assertTrue(all(not c.kwargs['cache_enabled'] for c in factory.call_args_list))
        self.assertTrue(all(c.args[1]['status']=='quarantined' and c.args[1]['published_at'] is None for c in store.put.call_args_list))
        self.assertNotIn('candidate_model', review_prompts[0])
        self.assertNotIn('candidate_model', item['payload'])

    def test_structural_fact_error_spends_nothing_on_writer_or_reviewer(self):
        fake = Mock(); fake.stats = {}
        item = {'id':'i', 'url':'u', 'payload':{'content_hash':'a', 'publisher':'P'}}
        with patch.object(trial, 'NewsAi', return_value=fake), \
             patch.object(trial, 'extract_facts', return_value={}), \
             patch.object(trial, 'partition_fact_extraction', return_value=({}, [], ['source_quote_not_found'])), \
             patch.object(trial, 'generate_article') as writer, patch.object(trial, 'audit_article') as reviewer:
            out = trial.run_cell(Mock(), {'items':{'acea':item}, 'model_keys':[]}, 'statistics', 'mini', MODEL, Mock())
        self.assertEqual(out['stopped'], 'invalid_extracted_facts')
        writer.assert_not_called(); reviewer.assert_not_called()

    def test_genre_requires_real_qualified_price_and_scoped_statistics(self):
        self.assertFalse(trial.genre_coverage('price', {'category':'priser'}, []))
        price = {'id':'p', 'statement':'I Sverige kostar privatleasing 2995 kronor per månad.',
                 'evidence':'I Sverige kostar privatleasing 2995 kronor per månad.'}
        self.assertTrue(trial.genre_coverage('price', {'category':'priser'}, [price]))
        self.assertFalse(trial.genre_coverage('price', {'category':'modeller'}, [price]))
        self.assertFalse(trial.genre_coverage('statistics', {'category':'marknad'}, []))
        self.assertTrue(trial.genre_coverage('statistics', {'category':'marknad'}, [{'origin':'literal_statistical_field'}]*3))


if __name__ == '__main__':
    unittest.main()
