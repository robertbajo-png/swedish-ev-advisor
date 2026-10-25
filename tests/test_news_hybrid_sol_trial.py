"""Offline checks for the one-off Sol allowance; no provider or production access."""
import copy
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import trial_news_hybrid_sol as sol
from news_ai import NewsBudgetBlocked
from news_launch_hybrid import launch_brief,writer_call,reviewer_call
from preview_news_launch_hybrid import fixture_input,fixture_article


class SolHybridTrialTests(unittest.TestCase):
    def setUp(self):
        names=('DATE','MODEL','TRIAL_ID','CAP','DIRECTORY','MANIFEST','REPORT','DATABASE','ARTICLE_BYTES',
               'authorize','code_hash','readiness','payload','request_bound','whole_trial_bound','paid_call')
        old={n:getattr(sol.base,n) for n in names}
        self.addCleanup(lambda:[setattr(sol.base,n,v) for n,v in old.items()])
        old_id=sol.TRIAL_ID
        self.addCleanup(lambda:setattr(sol,'TRIAL_ID',old_id))
        sol.configure()
        data=json.loads((ROOT/'tests/fixtures/news_hybrid_launch.json').read_text(encoding='utf-8'))
        items,sources=fixture_input(data)
        self.brief=launch_brief(items,sources,now=datetime.fromisoformat(data['published_at']))
        self.article=fixture_article(data,self.brief)
        self.remote=Mock()
        self.cfg={'enabled':False,'publication_enabled':False,'model':'gpt-6-sol',
            'daily_limit_micro_usd':250000,'monthly_limit_micro_usd':5000000,'pricing_valid_until':'2026-11-21'}
        self.remote.client.select.side_effect=lambda table,**_: [copy.deepcopy(self.cfg)] if table=='news_ai_config' else [{'enabled':False}]

    def test_fresh_identity_and_same_evidence_contract_with_correct_sol_tariffs(self):
        self.assertNotEqual(sol.TRIAL_ID,'abd97001-f06d-59e3-856c-38075f6698ba')
        self.assertEqual(sol.base.CAP,370000)
        call=sol.payload(writer_call(self.brief))
        bound=sol.request_bound(call)
        self.assertEqual(call['model'],'gpt-6-sol')
        self.assertEqual(call['prompt_cache_options'],{'mode':'explicit','ttl':'30m'})
        self.assertEqual(bound['maximum_micro_usd'],bound['input_bound']*5+25000)
        total=sol.whole_trial_bound(self.brief)
        self.assertLessEqual(total['total'],370000)
        self.assertGreater(total['review'],sol.request_bound(sol.payload(reviewer_call(self.article,self.brief)))['maximum_micro_usd'])

    def test_owner_exception_never_enables_production_and_month_cap_is_not_extended(self):
        row={'id':'old','created_at':sol.DATE,'charged_micro_usd':203796}
        with patch.object(sol,'authorize'),patch.object(sol.base,'ledger',return_value=[row]):
            result=sol.readiness(self.remote,True,360000)
            self.assertEqual(result['ordinary_daily_limit_micro_usd'],250000)
            self.assertEqual(result['ordinary_monthly_limit_micro_usd'],5000000)
            self.cfg['enabled']=True
            with self.assertRaises(NewsBudgetBlocked): sol.readiness(self.remote,False)
            self.cfg['enabled']=False
            row['charged_micro_usd']=4990000
            with self.assertRaises(NewsBudgetBlocked): sol.readiness(self.remote,False,10001)

    def test_scope_probe_has_fresh_identity_and_private_output_with_unchanged_cap(self):
        original_id=sol.TRIAL_ID
        original_directory=sol.base.DIRECTORY
        sol.configure(scope_probe=True)
        self.assertNotEqual(sol.TRIAL_ID,original_id)
        self.assertNotEqual(sol.base.DIRECTORY,original_directory)
        self.assertIn('data/local/release-data/news-hybrid-sol-scope-live-',sol.base.DIRECTORY.as_posix())
        self.assertEqual(sol.base.CAP,370000)
        self.assertEqual(sol.base.ARTICLE_BYTES,6300)
        self.assertEqual(sol.payload(writer_call(self.brief))['max_output_tokens'],2500)
        self.assertLessEqual(sol.whole_trial_bound(self.brief)['total'],370000)
        sol.configure()
        self.assertEqual(sol.TRIAL_ID,original_id)
        self.assertEqual(sol.base.DIRECTORY,original_directory)
        self.assertEqual(sol.base.ARTICLE_BYTES,7000)

    def test_wrong_or_repeated_stage_blocks_before_reserve(self):
        report={'results':[]}
        with patch.object(sol,'authorize'),self.assertRaises(NewsBudgetBlocked):
            sol.paid_call(self.remote,report,reviewer_call(self.article,self.brief))
        self.remote.client._request.assert_not_called()

    def test_wrong_server_tariff_never_dispatches(self):
        report={'results':[],'baseline_ids':[],'baseline_surfaces':{},'manifest_hash':'a'*64,
                'bounds':sol.whole_trial_bound(self.brief)}
        self.remote.client._request.return_value={'allowed':True,'reserved_micro_usd':1}
        transport=Mock()
        with patch.object(sol,'authorize'),patch.object(sol,'readiness'),patch.object(sol.base,'ledger',return_value=[]), \
             patch.object(sol.base,'production_surfaces',return_value={}),self.assertRaises(NewsBudgetBlocked):
            sol.paid_call(self.remote,report,writer_call(self.brief),transport)
        transport.assert_not_called()

    def test_durable_pending_receipt_required_before_provider(self):
        report={'results':[],'baseline_ids':[],'baseline_surfaces':{},'manifest_hash':'a'*64,
                'bounds':sol.whole_trial_bound(self.brief)}
        self.remote.client._request.return_value={'allowed':True,'reserved_micro_usd':report['bounds']['writer']}
        transport=Mock()
        with patch.object(sol,'authorize'),patch.object(sol,'readiness'),patch.object(sol.base,'ledger',return_value=[]), \
             patch.object(sol.base,'production_surfaces',return_value={}),patch.object(sol.base,'receipt',side_effect=RuntimeError), \
             self.assertRaises(RuntimeError):
            sol.paid_call(self.remote,report,writer_call(self.brief),transport)
        transport.assert_not_called()
        self.assertEqual(report['results'][0]['state'],'dispatch_pending')

    def test_every_exit_closes_only_this_new_permit(self):
        self.remote.client._request.return_value={'closed':True}
        with patch.object(sol,'ORIGINAL_RUN',side_effect=NewsBudgetBlocked('provider failed')),self.assertRaises(NewsBudgetBlocked):
            sol.run(self.remote)
        self.remote.client._request.assert_called_once_with('POST','rpc/close_news_sol_test',{'permit_key':sol.TRIAL_ID})


if __name__=='__main__': unittest.main()
