"""Offline incomplete-provider accounting; no retries, live calls or publication."""
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_news_publisher_articles as fixtures
import run_publisher_news as worker
from news_run_summary import summarize
from news_publisher_articles import writer_call, resolve_writer_output, precheck
from news_publisher_selection import primary_identity_matches, statistical_quantities


class ProviderOutcomeTests(unittest.TestCase):
    def test_delivery_statistics_cannot_use_an_unrelated_model_launch(self):
        report={'payload':{'title':'XPeng : 10 000 voitures livr\u00e9es en France en deux ans',
                           'content':'Synthetic French delivery statistics.'}}
        primary={'payload':{'title':'XPENG G9L lancement en Suisse',
                            'content':'XPENG propose un nouveau SUV familial. Deux ans de tests en Europe.'}}
        self.assertFalse(primary_identity_matches(report,primary))
        primary['payload'].update(title='XPENG delivery update in France',
            content='XPENG reports 30,000 deliveries in France over two years.')
        self.assertFalse(primary_identity_matches(report,primary))
        primary['payload']['content']='XPENG reports 10,000 deliveries in France over two years.'
        self.assertTrue(primary_identity_matches(report,primary))

    def test_grouped_counts_match_without_using_years_or_vehicle_model_digits(self):
        for text in ('10 000', '10,000', '10.000', '10\u00a0000', '10\u202f000', '10000'):
            self.assertEqual(statistical_quantities(text),{10000})
        self.assertEqual(statistical_quantities('2026 7 seats G9L 2027 10-80'),set())

    def test_statistical_period_mismatch_still_fails_when_counts_match(self):
        report={'payload':{'title':'XPENG deliveries reach 10,000 in October 2026','content':'Synthetic statistics.'}}
        primary={'payload':{'title':'XPENG delivery statistics September 2026',
                            'content':'XPENG reports 10,000 deliveries in September 2026.'}}
        self.assertFalse(primary_identity_matches(report,primary))

    def test_null_decline_is_explicit_but_can_never_bypass_article_requirements(self):
        bundle,packet=fixtures.fixture()
        schema=writer_call(bundle)[1]
        self.assertEqual(schema['properties']['article']['type'],['object','null'])
        self.assertIn('article=null',writer_call(bundle)[2])
        rejected=fixtures.encoded_fixture(bundle,packet)
        rejected['extraction'].update(relevant=False,facts=[])
        rejected['article']=None
        resolved=resolve_writer_output(bundle,rejected)
        checked=precheck(bundle,resolved,fixtures.NOW)
        self.assertFalse(checked['passed']);self.assertEqual(checked['word_count'],0)
        self.assertIn('publisher_editorial_declined',checked['errors'])
        relevant=copy.deepcopy(packet);relevant['article']=None
        self.assertFalse(precheck(bundle,relevant,fixtures.NOW)['passed'])

    def test_thin_story_decline_does_not_invent_an_article_or_buy_a_reviewer(self):
        encoder=fixtures.encoded_fixture
        def declined(bundle,packet):
            value=encoder(bundle,packet);value['extraction'].update(relevant=False,facts=[])
            return {**value,'article':None}
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote,b,_,ai=fixtures.PublisherLifecycleTests().setup_environment(stack,folder)
            stack.enter_context(patch.object(fixtures,'encoded_fixture',side_effect=declined))
            result=worker.perform(remote,b,private=False,ai=ai)
            self.assertEqual(result['state'],'quarantined')
            self.assertEqual(result['packet']['article'],None)
            self.assertEqual(ai.calls,['swedish_ev_article'])
            self.assertEqual(remote.rows('news_articles'),[])

    def test_settled_incomplete_writer_keeps_charge_and_never_buys_review_or_retry(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote,b,_,ai=fixtures.PublisherLifecycleTests().setup_environment(stack,folder)
            class Incomplete:
                model=ai.model
                output_limits=ai.output_limits
                payload=ai.payload
                def __call__(self,*args):
                    ai(*args)
                    remote.client.receipts[-1].update(provider_status='incomplete',output_tokens=2000,
                        response_payload={'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'},
                                          'output':[{'content':[{'type':'output_text','text':'{"unfinished":'}]}]})
                    raise ValueError('news_incomplete_ai_response')
            result=worker.perform(remote,b,private=False,ai=Incomplete())
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['cost_status'],'settled')
            self.assertEqual(result['cost_micro_usd'],1000)
            self.assertEqual(result['request_ids'],[])
            self.assertEqual(len(result['observed_request_ids']),1)
            self.assertEqual(ai.calls,['swedish_ev_article'])
            before=copy.deepcopy(remote.client.receipts)
            self.assertTrue(worker.perform(remote,b,private=False,ai=Incomplete())['reused_attempt'])
            self.assertEqual(remote.client.receipts,before)
            self.assertEqual(remote.rows('news_articles'),[])
            self.assertEqual(summarize(result)['failure_kind'],'incomplete_provider_response')

    def test_known_incomplete_cost_does_not_authorize_fallback_to_another_candidate(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote,b,_,_=fixtures.PublisherLifecycleTests().setup_environment(stack,folder)
            other=copy.deepcopy(b['items'][0]);other['url']+='-other'
            skipped=[{'source_id':'synthetic','reason':'publisher_no_primary_or_independent_pair',
                      'subjects':['xpeng'],'discovery_trace':[{'status':'no_matching_declared_authority'}]}]
            stack.enter_context(patch.dict('os.environ',{'NEWS_PUBLISHER_ARTICLES_ENABLED':'true'}))
            stack.enter_context(patch.object(worker,'selection_queue',return_value=([(b['items'][0],{}),(other,{})],skipped)))
            stack.enter_context(patch.object(worker,'collect_bundle',return_value=b))
            stack.enter_context(patch.object(worker,'require_recent_publication'))
            stack.enter_context(patch.object(worker,'evidence_readiness',return_value={'ready':True}))
            attempt=stack.enter_context(patch.object(worker,'perform',return_value={
                'status':'failed','cost_status':'settled','cost_micro_usd':1000,'published':0,
                'error':'ValueError:news_incomplete_ai_response'}))
            release=stack.enter_context(patch.object(worker,'release',side_effect=AssertionError('No publication')))
            result=worker.daily(remote,None)
            self.assertEqual(result['status'],'failed');attempt.assert_called_once();release.assert_not_called()
            self.assertEqual(result['skipped'],skipped)
            self.assertEqual(summarize(result)['source_gaps'],{'missing_authority':{'xpeng':1}})

    def test_failed_and_quarantined_attempts_share_the_same_two_candidate_limit(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote,_,_,ai=fixtures.PublisherLifecycleTests().setup_environment(stack,folder)
            for n,state in enumerate(('failed','quarantined')):
                remote.put('news_ingestion_runs',{'id':'old-'+str(n),'payload':{
                    'kind':'short_daily','state':state,'started_at':fixtures.NOW.isoformat(),'url':'old-'+str(n)}})
            stack.enter_context(patch.dict('os.environ',{'NEWS_PUBLISHER_ARTICLES_ENABLED':'true'}))
            stack.enter_context(patch.object(worker,'selection_queue',side_effect=AssertionError('No third attempt')))
            self.assertEqual(worker.daily(remote,None)['status'],'daily_attempt_limit')
            self.assertEqual(ai.calls,[])

    def test_failure_summary_never_echoes_exception_prose_or_credentials(self):
        cases=[('ValueError:news_incomplete_ai_response','incomplete_provider_response'),
               ('NewsProviderError:news_provider_http_401','provider_failure'),
               ('NewsBudgetBlocked:news_settlement_unavailable_reservation_retained','budget_or_accounting_failure'),
               ('RuntimeError:private prose sk-proj-test https://private.example/?key=secret','worker_failure')]
        for error,expected in cases:
            result=summarize({'status':'failed','error':error,'cost_micro_usd':1000,'published':0})
            self.assertEqual(result['failure_kind'],expected)
            self.assertEqual(result['status'],'failed');self.assertFalse(result['review_performed'])
            self.assertNotIn(error,json.dumps(result));self.assertNotIn('private.example',json.dumps(result))


if __name__=='__main__':unittest.main()
