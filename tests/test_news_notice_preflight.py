"""Notice deployment reads do not require or dispatch an OpenAI request."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from news_notice_preflight import run


class NoticePreflightTests(unittest.TestCase):
    def setUp(self):
        self.cfg={'id':'production','enabled':False,'publication_enabled':False,'model':'gpt-5.4-mini',
                  'daily_limit_micro_usd':250000,'monthly_limit_micro_usd':5000000,'daily_article_limit':2}
        self.notice={'id':'production','enabled':False,'daily_limit':2,'policy':'news-notice-2026-10-v1',
                     'review_method':'deterministic_typed_notice_v1'}
        self.ledger=[]
        self.client=Mock()
        self.client.select.side_effect=lambda table,**kw: copy.deepcopy(
            [self.cfg] if table=='news_ai_config' else [self.notice] if table=='news_notice_release_config'
            else self.ledger if table=='news_ai_requests' else [])
        self.client._request.return_value={'paths':{'/rpc/publish_news_notice':{'post':{}}}}

    def test_explicit_remote_flag_is_required(self):
        result=run(client=self.client)
        self.assertFalse(result['ready']);self.client.select.assert_not_called()

    def test_paused_readiness_requires_no_ai_key_and_never_writes(self):
        with patch.dict('os.environ',{},clear=True),patch('news_ai.NewsAi.request',side_effect=AssertionError('no AI')):
            result=run(True,client=self.client)
        self.assertTrue(result['ready'],result)
        self.assertFalse(result['global_config']['enabled'])
        self.assertEqual(set(result['fingerprints']),{'public_news_articles','public_ev_models','public_ev_variants','news_ai_requests'})
        self.client._request.assert_called_once_with('GET','')
        self.client.upsert.assert_not_called()
        self.assertEqual(result['writes'],0);self.assertEqual(result['cost_usd'],0)

    def test_missing_migration_is_reported_without_losing_baseline_or_leaking_http_body(self):
        old=self.client.select.side_effect
        def select(table,**kw):
            if table=='news_notice_release_config': raise RuntimeError('HTTP secret-do-not-print')
            return old(table,**kw)
        self.client.select.side_effect=select
        result=run(True,client=self.client)
        self.assertFalse(result['schema_installed']);self.assertFalse(result['ready'])
        self.assertTrue(result['remote_checked']);self.assertEqual(len(result['fingerprints']),4)
        self.assertNotIn('secret-do-not-print',json.dumps(result))

    def test_partial_install_with_no_rpc_is_not_ready(self):
        self.client._request.return_value={'paths':{}}
        result=run(True,client=self.client)
        self.assertIn('notice_publication_rpc_not_visible_to_worker',result['errors'])

    def test_release_and_paused_modes_cannot_confuse_activation(self):
        self.assertFalse(run(True,'release',self.client)['ready'])
        self.cfg['publication_enabled']=True
        self.assertFalse(run(True,'release',self.client)['ready'])
        self.notice['enabled']=True
        self.assertTrue(run(True,'release',self.client)['ready'])
        self.assertFalse(run(True,'paused',self.client)['ready'])
        self.cfg['enabled']=True
        self.assertFalse(run(True,'release',self.client)['ready'])

    def test_old_unknown_hold_remains_counted_and_visible_in_fingerprint(self):
        self.ledger.append({'id':'old','charged_micro_usd':20868,'reserved_micro_usd':20868,
                            'settled_at':None,'budget_closed_at':'owner-closed','provider_status':'unknown'})
        result=run(True,client=self.client)
        self.assertTrue(result['ready']);self.assertIn('old_unknown_maximum_cost_remains_in_ledger',result['warnings'])
        self.assertEqual(result['fingerprints']['news_ai_requests']['count'],1)
        before=result['fingerprints']['news_ai_requests']['sha256']
        self.ledger[0]['charged_micro_usd']=0
        self.assertNotEqual(run(True,client=self.client)['fingerprints']['news_ai_requests']['sha256'],before)
        self.client.upsert.assert_not_called()

    def test_budget_model_and_policy_changes_fail_closed(self):
        for row,key,value in [(self.cfg,'model','gpt-6-luna'),(self.cfg,'daily_limit_micro_usd',500000),
                              (self.notice,'policy','other'),(self.notice,'daily_limit',0)]:
            original=row[key];row[key]=value
            with self.subTest(key=key): self.assertFalse(run(True,client=self.client)['ready'])
            row[key]=original


if __name__=='__main__': unittest.main()
