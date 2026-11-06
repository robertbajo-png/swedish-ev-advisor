"""Synthetic original-source discovery, never real AI or publication proof."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from news_http import canonical_url
from news_primary_discovery import discover, valid_edge, MAX_INDEXES
from news_publisher_sources import (collect_bundle, primary_source, PRIMARY_AUTHORITIES, fetch_primary,
    parse_publisher, bundle_errors, refresh_bundle, same_sources, OriginalSourceNotFound)
from news_publisher_selection import primary_identity_matches, reference_periods
from news_store import stable_id, artifact_hash
import test_news_publisher_articles as fixture

NOW=fixture.NOW
REPORT=fixture.REPORT_URL
ORIGINAL='https://www.volkswagen-newsroom.com/en/press-releases/synthetic-battery-project-99999'
INDEX='https://www.volkswagen-newsroom.com/en/press-releases'
TITLE='Volkswagen synthetic battery project for European electric cars'
BODY=('Volkswagen plans a synthetic battery project for European electric passenger cars. ' * 24)

def page(url,title=TITLE,body=BODY,date=NOW.isoformat()):
    return (f'<link rel="canonical" href="{url}"><meta property="og:title" content="{title}">'
            f'<meta property="article:published_time" content="{date}">'
            f'<article class="article_detail__content">{body}</article>')

def lead():
    return {'id':stable_id(REPORT),'url':REPORT,'source_id':'carnewschina',
            'payload':{'title':TITLE,'content':BODY,'published_at':NOW.isoformat()}}

def catalog(url=ORIGINAL):
    return {'id':stable_id(url),'url':url,'source_id':'vw-press','status':'collected',
            'payload':{'title':TITLE,'summary':BODY[:200],'published_at':NOW.isoformat(),'source_kind':'primary'}}

class FakeCollector:
    def __init__(self, documents): self.documents=documents; self.calls=[]
    def fetch(self,url,source,**kwargs):
        self.calls.append((url,kwargs))
        value=self.documents[url]
        if isinstance(value,Exception): raise value
        return 200,{},value,url

class OriginalDiscoveryTests(unittest.TestCase):
    def test_wrong_manufacturer_direct_links_do_not_crowd_out_actual_primary(self):
        from news_publisher_sources import PRIMARY_AUTHORITIES
        title='Toyota launches a synthetic electric car in Europe'
        original='https://media.toyota.co.uk/synthetic-electric-car-launch/'
        body=('Toyota describes a synthetic electric passenger car launch in Europe. '*25)
        wrong=[ORIGINAL,ORIGINAL.replace('99999','99998')]
        report_page=page(REPORT,title=title,body=body+''.join(f'<a href="{u}">Related release</a>' for u in wrong+[original]))
        c=FakeCollector({REPORT:report_page,original:page(original,title=title,body=body)})
        with patch('news_publisher_sources.fetch_primary') as fetch:
            from news_publisher_sources import item_from_document
            item=item_from_document(original,primary_source(original),{'title':title,'published_at':NOW.isoformat(),'content':body.strip()},NOW)
            fetch.return_value=(item,[])
            result=collect_bundle('carnewschina',REPORT,c,now=NOW)
        self.assertEqual([args[0][0] for args in fetch.call_args_list],[original])
        self.assertEqual(result['items'][1]['url'],original)
        self.assertEqual(bundle_errors(result,NOW),[])

    def test_direct_links_prioritize_exact_subject_before_bounded_fetches(self):
        matched=ORIGINAL.replace('synthetic-battery-project','volkswagen-id7-charging-update')
        irrelevant=ORIGINAL.replace('synthetic-battery-project','corporate-calendar')
        title='Volkswagen ID7 charging update for electric cars in Europe'
        body=('Volkswagen describes the ID7 charging update for electric passenger cars in Europe. '*20)
        html=page(REPORT,title=title,body=body+f'<a href="{irrelevant}">Unrelated</a><a href="{matched}">Original release</a>')
        c=FakeCollector({REPORT:html,matched:page(matched,title=title,body=body),irrelevant:ValueError('unrelated_source')})
        result=collect_bundle('carnewschina',REPORT,c,now=NOW)
        self.assertEqual(c.calls[1][0],matched)
        self.assertEqual(result['items'][1]['url'],matched)

    def test_known_other_manufacturer_does_not_consume_official_lookup_slots(self):
        item = lead()
        item['payload'].update(title='Toyota launches a synthetic electric car in China',
                               content='A Toyota electric passenger car. Volkswagen is mentioned only as background.')
        c=Mock()
        self.assertEqual(discover(item,c,PRIMARY_AUTHORITIES,[catalog()],trace=[]),[])
        c.fetch.assert_not_called()

    def test_declared_group_brands_joint_stories_and_neutral_authorities_remain_searchable(self):
        from news_primary_discovery import source_subject_matches
        group = primary_source('https://www.vwgroup.se/nyheter--media/pressmeddelanden/2026/11/synthetic/')
        item = lead()
        for brand in ('Volkswagen', 'Skoda', 'Cupra', 'Audi'):
            item['payload']['title'] = brand + ' launches an electric car in Sweden'
            self.assertTrue(source_subject_matches(item, group))
        item['payload']['title'] = 'Toyota launches an electric car in Sweden'
        self.assertFalse(source_subject_matches(item, group))
        self.assertTrue(source_subject_matches(item, {'name': 'ACEA'}))
        item['payload']['title'] = 'Toyota and Volkswagen announce a joint electric car project'
        self.assertTrue(source_subject_matches(item, group))

    def test_approved_official_registry_expands_without_a_model_specific_python_rule(self):
        for url,identity in [(ORIGINAL,'vw-press'),
            ('https://www.vwgroup.se/nyheter--media/pressmeddelanden/2026/11/synthetic/','vw-sweden-press'),
            ('https://www.acea.auto/pc-registrations/synthetic-registrations/','acea'),
            ('https://news.gm.com/home.detail.html/Pages/news/us/en/2026/nov/synthetic.html','gm-press')]:
            self.assertEqual(primary_source(url)['id'],identity)
        for url in ['https://news.gm.com.evil.example/home.detail.html/Pages/news/us/en/synthetic.html',
                    'http://news.gm.com/home.detail.html/Pages/news/us/en/synthetic.html',
                    ORIGINAL+'?redirect=https://127.0.0.1', 'https://127.0.0.1/private']:
            self.assertIsNone(primary_source(url))

    def test_reuses_official_metadata_and_fetches_the_original_not_the_feed_summary(self):
        c=FakeCollector({REPORT:page(REPORT),ORIGINAL:page(ORIGINAL)})
        result=collect_bundle('carnewschina',REPORT,c,now=NOW,corroborating_items=[catalog()])
        self.assertEqual([u for u,_ in c.calls],[REPORT,ORIGINAL])
        self.assertEqual(result['provenance'][0]['method'],'official_catalog')
        self.assertEqual(result['items'][1]['payload']['content_hash'],hashlib.sha256(BODY.strip().encode()).hexdigest())
        self.assertEqual(bundle_errors(result,NOW),[])
        self.assertTrue(all(options['editorial'] for _,options in c.calls))

    def test_discovers_a_new_model_from_an_official_index_and_retains_hash_provenance(self):
        index=f'<a href="{ORIGINAL}">{TITLE}</a>'
        c=FakeCollector({REPORT:page(REPORT),INDEX:index,ORIGINAL:page(ORIGINAL)})
        result=collect_bundle('carnewschina',REPORT,c,now=NOW)
        edge=result['provenance'][0]
        self.assertEqual(edge['method'],'official_discovery_index')
        self.assertEqual(edge['index_hash'],hashlib.sha256(index.encode()).hexdigest())
        self.assertEqual(bundle_errors(result,NOW),[])
        tampered=copy.deepcopy(edge);tampered['from_url']='https://unapproved.example/index'
        self.assertFalse(valid_edge(tampered,result['items'][0],PRIMARY_AUTHORITIES))

    def test_catalog_identity_and_hash_tampering_are_held(self):
        entries,_=self.discovery_from_catalog()
        edge=entries[0][1]
        for field in ('catalog_hash','from_url'):
            changed=copy.deepcopy(edge);changed[field]='tampered'
            self.assertFalse(valid_edge(changed,lead(),PRIMARY_AUTHORITIES))
        changed=copy.deepcopy(edge);changed['catalog_item']['source_id']='pretend-official'
        changed['catalog_hash']=artifact_hash(changed['catalog_item'])
        self.assertFalse(valid_edge(changed,lead(),PRIMARY_AUTHORITIES))

    def discovery_from_catalog(self):
        trace=[]
        return discover(lead(),Mock(),PRIMARY_AUTHORITIES,[catalog()],trace,indexes=False),trace

    def test_unknown_or_spoofed_metadata_is_not_fetched(self):
        c=Mock()
        wrong=catalog();wrong['source_id']='unapproved'
        private=catalog('https://127.0.0.1/private')
        self.assertEqual(discover(lead(),c,PRIMARY_AUTHORITIES,[wrong,private],indexes=False),[])
        c.fetch.assert_not_called()

    def test_wrong_models_and_different_explicit_statistical_periods_do_not_match(self):
        report={'payload':{'title':'BMW i3 electric car launches in Europe'}}
        self.assertFalse(primary_identity_matches(report,{'payload':{'title':'BMW iX3 electric SUV','content':BODY}}))
        report={'payload':{'title':'Volkswagen registrations October 2026','content':''}}
        target={'payload':{'title':'Volkswagen registrations September 2026','content':'Volkswagen registrations in September 2026.'}}
        self.assertFalse(primary_identity_matches(report,target))
        self.assertEqual(reference_periods('octobre 2026 oktober 2026 October 2026'),{(2026,10)})
        self.assertEqual(reference_periods('collected yesterday; October'),set())
        self.assertEqual(reference_periods('2026 1 000 registrations'),set())
        self.assertEqual(reference_periods('2026-10 and 2026/11'),{(2026,10),(2026,11)})

    def test_generic_ev_platform_words_never_match_gm_reporting_to_vw_releases(self):
        report={'payload':{'title':'GM has another go at EVs with a new generation platform and LMR battery'}}
        primary={'payload':{'title':'Volkswagen premieres a new electric model',
                            'publisher':'Volkswagen Newsroom',
                            'content':'A new generation platform and battery for electric cars. GM competitors are mentioned as background.'}}
        self.assertFalse(primary_identity_matches(report,primary))
        discovery_lead={'payload':{'title':report['payload']['title'],
            'content':'A new generation platform and battery for European electric passenger cars.',
            'published_at':NOW.isoformat()}}
        c=Mock()
        self.assertEqual(discover(discovery_lead,c,PRIMARY_AUTHORITIES,[catalog()],indexes=False),[])
        c.fetch.assert_not_called()
        primary['payload']['title']='A new generation platform and battery for electric cars'
        primary['payload']['content']='A new generation platform and battery for electric cars.'
        self.assertFalse(primary_identity_matches(report,primary))

    def test_joint_announcements_can_match_both_named_parties_but_not_an_absent_model(self):
        report={'payload':{'title':'BMW and Volkswagen announce a synthetic charging project'}}
        primary={'payload':{'title':'Volkswagen and BMW synthetic charging project',
                            'content':'Volkswagen and BMW describe the synthetic charging project.'}}
        self.assertTrue(primary_identity_matches(report,primary))
        report['payload']['title']='BMW i3 charging project'
        primary['payload'].update(title='BMW charging project',content='BMW describes a charging project with no exact model.')
        self.assertFalse(primary_identity_matches(report,primary))

    def test_old_or_future_original_is_not_made_new_by_a_fresh_report(self):
        for date,reason in [('2025-01-01T00:00:00+00:00','old_primary'),('2027-01-01T00:00:00+00:00','primary_after_report')]:
            report_page=page(REPORT,body=BODY+f'<a href="{ORIGINAL}">Original</a>')
            c=FakeCollector({REPORT:report_page,ORIGINAL:page(ORIGINAL,date=date),INDEX:'<p>Empty index</p>'})
            with self.assertRaises(OriginalSourceNotFound) as error: collect_bundle('carnewschina',REPORT,c,now=NOW)
            self.assertTrue(any(reason in str(t.get('reason','')) for t in error.exception.discovery_trace))

    def test_source_refresh_fetches_the_exact_two_documents_without_rediscovery(self):
        c=FakeCollector({REPORT:page(REPORT),ORIGINAL:page(ORIGINAL)})
        result=collect_bundle('carnewschina',REPORT,c,now=NOW,corroborating_items=[catalog()])
        c.calls=[]
        self.assertTrue(same_sources(result,refresh_bundle(result,c,now=NOW)))
        self.assertEqual([u for u,_ in c.calls],[REPORT,ORIGINAL])
        c.documents[ORIGINAL]=page(ORIGINAL,body=BODY+' Changed authoritative sentence.')
        self.assertFalse(same_sources(result,refresh_bundle(result,c,now=NOW)))

    def test_blocked_originals_retain_actionable_diagnostics_without_ai(self):
        c=FakeCollector({INDEX:ValueError('ai_mining_robots_reserved')})
        trace=[]
        self.assertEqual(discover(lead(),c,PRIMARY_AUTHORITIES,trace=trace),[])
        self.assertTrue(any('ai_mining_robots_reserved' in t.get('reason','') for t in trace))
        discover(lead(),c,PRIMARY_AUTHORITIES,trace=[])
        self.assertEqual(len(c.calls),1,'One source index is not repeatedly fetched for every report in the same run')

    def test_index_and_candidate_work_is_bounded_and_unknown_links_do_not_escape(self):
        registry={}
        documents={}
        for i in range(4):
            host=f'official-{i}.example'; url='https://'+host+'/index'
            registry[host]={'id':str(i),'kind':'primary','website':'https://'+host,
                'article_path_pattern':'/news/[^/]+','indexes':[url],'discovery_triggers':['battery']}
            documents[url]='<a href="https://127.0.0.1/private">Synthetic battery project</a>'
        c=FakeCollector(documents)
        self.assertEqual(discover(lead(),c,registry),[])
        self.assertEqual(len(c.calls),MAX_INDEXES)

    def test_pdf_is_identified_but_not_decoded_as_html_or_claimed_as_verified(self):
        c=Mock()
        with self.assertRaisesRegex(ValueError,'pdf_extraction_required'):
            fetch_primary('https://pfa-auto.fr/wp-content/uploads/2026/11/synthetic.pdf',c,NOW)
        c.fetch.assert_not_called()

    def test_structured_dates_are_article_specific_and_modification_is_not_publication(self):
        structured={'@type':'NewsArticle','url':ORIGINAL,'datePublished':NOW.isoformat(),'dateModified':'2027-01-01'}
        html=page(ORIGINAL).replace(f'<meta property="article:published_time" content="{NOW.isoformat()}">','')
        html+='<script type="application/ld+json">'+json.dumps(structured)+'</script>'
        c=FakeCollector({ORIGINAL:html})
        item,_=fetch_primary(ORIGINAL,c,NOW)
        self.assertEqual(item['payload']['published_at'],NOW.isoformat())
        conflicting=page(ORIGINAL)+'<script type="application/ld+json">'+json.dumps({**structured,'datePublished':'2025-01-01'})+'</script>'
        c.documents[ORIGINAL]=conflicting
        with self.assertRaisesRegex(ValueError,'primary_conflicting_dates'): fetch_primary(ORIGINAL,c,NOW)

    def test_recommendation_widgets_cannot_inject_spurious_brands_or_source_links(self):
        html=page(REPORT,body=BODY+'<div class="articlescroller"><a href="https://unapproved.example/">Unrelated Tesla</a></div> Original ending.')
        parsed=parse_publisher(html,REPORT,'carnewschina',now=NOW)
        self.assertNotIn('Tesla',parsed['content'])
        self.assertEqual(parsed['links'],[])
        self.assertTrue(parsed['content'].endswith('Original ending.'))

if __name__=='__main__': unittest.main()
