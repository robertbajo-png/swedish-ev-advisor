"""Private GPT-6 Luna probe contracts, with no real provider or database calls."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import trial_news_luna_r27 as trial
from news_ai import NewsBudgetBlocked
from news_store import artifact_hash
from test_news_notices import packet

CFG={'enabled':False,'publication_enabled':False,'model':'gpt-5.4-mini',
     'daily_limit_micro_usd':250000,'monthly_limit_micro_usd':5000000,'pricing_valid_until':'2026-11-21'}


def provider_response():
    return {'model':'gpt-6-luna','service_tier':'default','status':'completed',
            'usage':{'input_tokens':100,'output_tokens':50,'total_tokens':150,
                'input_tokens_details':{'cached_tokens':0,'cache_write_tokens':0}},
            'output':[{'content':[{'type':'output_text','text':json.dumps({
                'title':'Volkswagen presenterar en batteriversion', 'intro':'Den nya versionen presenteras.',
                'paragraphs':['Underlaget innehåller en svensk lansering.']})}]}]}


class LunaProbeTests(unittest.TestCase):
    def test_exact_requested_model_strict_schema_no_reasoning_no_implicit_cache_or_tools(self):
        facts,_,_=packet()
        body=trial.payload(facts)
        self.assertEqual(body['model'],'gpt-6-luna')
        self.assertEqual(body['reasoning'],{'effort':'none'})
        self.assertEqual(body['prompt_cache_options'],{'mode':'explicit','ttl':'30m'})
        self.assertFalse(body['store'])
        self.assertEqual(body['service_tier'],'default')
        self.assertEqual(body['max_output_tokens'],1200)
        self.assertTrue(body['text']['format']['strict'])
        self.assertNotIn('tools',body)

    def test_whole_three_call_worst_case_fits_before_authorization(self):
        contracts=[trial.request_contract(trial.payload(packet(kind)[0])) for kind in ['model','price','statistics']]
        self.assertLessEqual(sum(c['maximum_micro_usd'] for c in contracts),trial.CAP)
        for c in contracts:
            self.assertEqual(c['maximum_micro_usd'],(c['input_bound']+2*c['output_bound']+3)//4)
            self.assertEqual(c['output_bound'],1200)

    def test_real_usage_cost_accounts_for_both_write_lifetimes_without_double_counting(self):
        response=provider_response()
        response['usage']={'input_tokens':1000,'output_tokens':200,'input_tokens_details':{
            'cached_tokens':100,'cache_write_tokens':400,
            'cache_write_tokens_details':{'ttl_30m_tokens':300,'ttl_12h_tokens':100}}}
        self.assertEqual(trial.exact_cost(response),'0.0002135')
        response['usage']['input_tokens_details']['cache_write_tokens']=500
        with self.assertRaises(ValueError): trial.exact_cost(response)

    def test_diagnostic_checks_never_equal_publication_approval(self):
        facts,_,_=packet()
        article={'title':'Modellnyhet','intro':'Batteriet anges till 37 kWh.','paragraphs':['Bäst i klassen och 9999 kilometer.']}
        result=trial.diagnostics(article,facts)
        self.assertTrue(result['forbidden_evaluation'])
        self.assertIn('9999',result['unexpected_numbers'])
        self.assertFalse(result['publication_eligible'])
        self.assertFalse(result['independent_ai_audit'])

    def test_current_shared_caps_and_old_unknown_hold_are_not_replaced_by_trial_cap(self):
        remote=Mock()
        rows=[{'id':'old','created_at':'2026-10-22','charged_micro_usd':20868,'settled_at':None,
               'budget_closed_at':'owner_closed','provider_status':'unknown'}]
        remote.client.select.side_effect=lambda t,**kw:[CFG] if t=='news_ai_config' else rows
        with patch.object(trial,'authorize'):
            self.assertEqual(trial.readiness(remote)['month_used_micro_usd'],20868)
            rows[0].update(created_at=trial.DATE,charged_micro_usd=240000)
            with self.assertRaises(NewsBudgetBlocked): trial.readiness(remote)
            rows[0].update(charged_micro_usd=1,budget_closed_at=None)
            with self.assertRaises(NewsBudgetBlocked): trial.readiness(remote)
        remote.client._request.assert_not_called()

    def exercise_run(self, provider_failure=False):
        cases=[]
        for kind in ['model','price','statistics']:
            facts,_,_=packet(kind); body=trial.payload(facts)
            cases.append({'kind':kind,'facts':facts,'payload':body,'contract':trial.request_contract(body)})
        manifest={'trial_id':trial.TRIAL_ID,'model':trial.MODEL,'cap_micro_usd':trial.CAP,'max_requests':3,
                  'cases':cases,'maximum_all_requests_micro_usd':sum(c['contract']['maximum_micro_usd'] for c in cases)}
        initial={'trial_id':trial.TRIAL_ID,'state':'prepared','manifest_hash':artifact_hash(manifest),
                 'baseline_surfaces':{'same':True},'baseline_ids':[],'results':[]}
        remote=Mock(); rows=[]; events=[]
        def select(table,**kwargs):
            if table=='news_ai_config': return [copy.deepcopy(CFG)]
            if table=='news_luna_test_permits': return [{'closed_at':None,'manifest_hash':artifact_hash(manifest)}]
            return rows
        remote.client.select.side_effect=select
        remote.get.return_value={'payload':{'state':'prepared','manifest_hash':artifact_hash(manifest)}}
        def rpc(method,path,body):
            events.append(path)
            if path.endswith('reserve_news_luna_ai'):
                rows.append({'id':body['request_key'],'created_at':trial.DATE,'charged_micro_usd':2000,
                    'reserved_micro_usd':2000,'settled_at':None,'budget_closed_at':None,'provider_status':'reserved',
                    'model':trial.MODEL,'luna_case':body['case_key']})
                return {'allowed':True,'reserved_micro_usd':2000}
            if path.endswith('settle_news_luna_ai'):
                next(r for r in rows if r['id']==body['request_key']).update(
                    charged_micro_usd=35,settled_at='now',provider_status='completed',input_tokens=100,output_tokens=50)
                return {'settled':True,'charged_micro_usd':35}
            return {'closed':True}
        remote.client._request.side_effect=rpc
        def provider(body,**kwargs):
            events.append('provider')
            if provider_failure: raise RuntimeError('provider unavailable')
            return provider_response()
        with patch.object(trial,'authorize'),patch.object(Path,'read_text',autospec=True,side_effect=lambda *a,**k:json.dumps(
             manifest if a[0].name==trial.MANIFEST.name else initial)),patch.object(trial,'surfaces',return_value={'same':True}), \
             patch.object(trial,'receipt') as receipt:
            result=trial.run(remote,transport=provider)
        self.assertEqual(events[0],'rpc/reserve_news_luna_ai')
        self.assertEqual(events[1],'provider')
        self.assertEqual(events[-1],'rpc/close_news_luna_test')
        self.assertTrue(result['shutdown_verified'])
        self.assertTrue(result['production_unchanged'])
        self.assertTrue(result['budget_within_cap'])
        self.assertEqual(receipt.call_args.args[1]['state'],'completed')
        return result, events

    def test_three_requests_reserve_first_settle_close_and_never_mutate_public_surfaces(self):
        result,events=self.exercise_run()
        self.assertTrue(result['complete']); self.assertTrue(result['all_settled'])
        self.assertEqual(events.count('provider'),3)
        self.assertEqual(result['ledger_micro_usd'],105)

    def test_provider_failure_keeps_hold_closes_and_does_not_retry(self):
        result,events=self.exercise_run(True)
        self.assertFalse(result['complete']); self.assertFalse(result['all_settled'])
        self.assertEqual(events.count('provider'),1)
        self.assertEqual(result['ledger_micro_usd'],2000)


if __name__=='__main__': unittest.main()
