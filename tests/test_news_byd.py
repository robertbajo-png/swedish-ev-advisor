"""Synthetic BYD shapes only; source readiness never implies AI/publication approval."""
import json
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request
from urllib.robotparser import RobotFileParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_byd import INDEX, QUERY, WEBSITE, document, listing
from news_engine import collect
from news_http import Collector, SafeRedirect
from news_pressrooms import discover
from news_publisher_sources import primary_source, collect_bundle, bundle_errors, refresh_bundle, same_sources
from news_store import NewsStore

URL = WEBSITE + '/de/presse/synthetic-electric-model'
NOW = datetime(2026, 11, 5, 9, tzinfo=timezone.utc)
BODY = 'Synthetic BYD electric vehicle battery facts for an isolated offline regression. ' * 15
INDEX_HTML = f'<link rel="canonical" href="{INDEX}"><div class="m07-news-list"><div class="top" data-url="{QUERY}" data-brand-name="byd" data-site-name="de" data-type="news"></div></div>'


def article(date='Offenbach, 5. November 2026 | Pressemitteilung', body=BODY):
    return (f'<link rel="canonical" href="{URL}"><meta property="og:title" content="Synthetic BYD electric car">'
            '<article class="news-article"><header><h1>Synthetic BYD electric car</h1>'
            f'<div class="article-meta">{date}</div></header></article>'
            f'<section class="news-text-block"><div class="news-text-container">{body}</div></section>'
            '<div class="article-content">Excluded corporate boilerplate.</div><aside>Excluded unrelated dates 2099.</aside>')


def row(url=URL, date='2026-11-05 09:00:00'):
    return {'type': 'news', 'url': url, 'date': date, 'title': 'Discovery only, never proof.'}


class FakeCollector(Collector):
    def __init__(self, records=None):
        super().__init__()
        robots = RobotFileParser(); robots.parse(['User-agent: *', 'Allow: /'])
        self.policy = Mock(return_value=robots)
        self.request = Mock(return_value=(200, {}, json.dumps({'code': 0, 'isSuccess': True,
             'data': {'records': records if records is not None else [row()], 'total': 9999}}), QUERY))
        self.html = article()
        self.fetch = Mock(side_effect=lambda url, *a, **k: (200, {}, INDEX_HTML if url == INDEX else self.html, url))


class BydTests(unittest.TestCase):
    def setUp(self):
        self.source = primary_source(URL)
        self.sleep = patch('news_byd.time.sleep'); self.sleep.start(); self.addCleanup(self.sleep.stop)

    def test_exact_article_header_and_narrative_exclude_company_and_related_material(self):
        parsed = document(article(), URL)
        self.assertEqual(parsed['body'], BODY.strip())
        self.assertEqual(parsed['published_at'], '2026-11-05T00:00:00+00:00')
        self.assertNotIn('Excluded', parsed['body'])
        self.assertNotIn('Excluded', document(article(body=BODY+'<div class="article-content">Excluded company facts.</div>'),URL)['body'])
        self.assertEqual(document(article('Berlin, 2. M\u00e4rz 2026 | Pressemitteilung'), URL)['published_at'][:10], '2026-03-02')

    def test_unknown_ambiguous_or_incomplete_layouts_fail_closed(self):
        pages = [article().replace(URL, URL+'-other'), article().replace('article-meta','unknown-date'), article().replace('</article>',''),
                 article()+'<article class="news-article"></article>', article().replace('news-text-container','unknown-body'),
                 article().replace('<h1>', '<h2>').replace('</h1>', '</h2>'),
                 article('Berlin, 31. Februar 2026 | Pressemitteilung'),
                 article().replace('</header>', '<div class="article-meta">Berlin, 4. November 2026 | Pressemitteilung</div></header>')]
        for html in pages:
            with self.subTest(html=html[:100]), self.assertRaises(ValueError): document(html, URL)

    def test_old_release_is_not_refreshed_by_metadata_or_fetch_time(self):
        c=FakeCollector([row(date='2020-01-01 09:00:00')])
        rows, errors=discover(INDEX_HTML, INDEX, self.source, c, 1, NOW)
        self.assertEqual(rows, []); self.assertEqual(errors[0]['reason'], 'ValueError:stale_report')
        c.fetch.assert_not_called()
        with self.assertRaisesRegex(ValueError,'dates_conflict'):
            document(article()+'<meta property="article:published_time" content="2099-01-01">',URL)

    def test_one_declared_public_query_is_bounded_read_only_and_uses_no_credentials(self):
        c=FakeCollector()
        self.assertEqual(len(listing(INDEX_HTML,INDEX,self.source,c)),1)
        c.request.assert_called_once()
        args, kwargs=c.request.call_args
        self.assertEqual(args[:2],(QUERY,'cms-api.byd.com'))
        self.assertEqual(args[2],{'Content-Type':'application/json'})
        payload=json.loads(kwargs['data'])
        self.assertEqual(payload,{'brandName':'byd','siteName':'de','type':'news','page':1,'size':20,'text':'','sortField':'date','tags':[]})
        c.policy.assert_called_once_with('https://cms-api.byd.com')

    def test_changed_dataset_or_authority_cannot_issue_a_query(self):
        for html,url,source in [(INDEX_HTML.replace(QUERY,'https://evil.example/query'),INDEX,self.source),
                (INDEX_HTML,INDEX+'?x=1',self.source), (INDEX_HTML,INDEX,{**self.source,'kind':'publisher'}),
                (INDEX_HTML+INDEX_HTML,INDEX,self.source), (INDEX_HTML.replace('data-site-name="de"','data-site-name="uk"'),INDEX,self.source)]:
            c=FakeCollector()
            with self.assertRaises(ValueError): listing(html,url,source,c)
            c.request.assert_not_called()

    def test_robots_mining_reservations_and_excessive_delay_prevent_the_query(self):
        for lines in [['User-agent: *','Disallow: /'],['User-agent: GPTBot','Disallow: /','User-agent: *','Allow: /'],
                      ['User-agent: *','Allow: /','Crawl-delay: 60']]:
            c=FakeCollector(); robots=RobotFileParser();robots.parse(lines);c.policy.return_value=robots
            with self.assertRaises(ValueError): listing(INDEX_HTML,INDEX,self.source,c)
            c.request.assert_not_called()

    def test_query_redirect_reserved_failure_and_malformed_responses_are_held(self):
        bad=[(200,{},'{}',QUERY), (200,{},json.dumps({'code':0,'isSuccess':False,'data':{'records':[]}}),QUERY),
             (200,{},json.dumps({'code':0,'isSuccess':True,'data':{'records':[row()]*21}}),QUERY),
             (200,{'TDM-Reservation':'1'},'{}',QUERY), (200,{},'{}',QUERY+'/other')]
        for response in bad:
            c=FakeCollector();c.request.return_value=response
            with self.assertRaises(ValueError): listing(INDEX_HTML,INDEX,self.source,c)

    def test_post_queries_never_follow_redirects_or_change_into_get_requests(self):
        req=Request(QUERY,data=b'{}')
        with patch('news_http.safe_host') as resolver, self.assertRaisesRegex(ValueError,'post_query_redirect'):
            SafeRedirect('cms-api.byd.com').redirect_request(req,None,302,'Found',{},QUERY+'/other')
        resolver.assert_not_called()

    def test_shared_transport_sends_the_exact_body_as_post_with_bounded_verified_transport(self):
        response=Mock(status=200,headers={'Content-Type':'application/json'},url=QUERY)
        response.read.return_value=b'{}'
        context=Mock();context.__enter__=Mock(return_value=response);context.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=context
        with patch('news_http.safe_host',side_effect=lambda url,host:url), \
                patch('news_http.build_opener',return_value=opener),patch('news_http.time.sleep'):
            result=Collector().request(QUERY,'cms-api.byd.com',{'Content-Type':'application/json'},data=b'{"page":1}')
        request=opener.open.call_args.args[0]
        self.assertEqual(request.get_method(),'POST');self.assertEqual(request.data,b'{"page":1}')
        self.assertFalse(request.has_header('Authorization'))
        self.assertEqual(result[3],QUERY);response.read.assert_called_once_with(2000001)

    def test_deduplication_exact_authority_and_listing_article_date_agreement(self):
        c=FakeCollector([row(),row(),row(url=URL.replace('www.byd.com','evil.example')),row(url=URL+'?x=1')])
        rows, errors=discover(INDEX_HTML,INDEX,self.source,c,3,NOW)
        self.assertEqual([r['url'] for r in rows],[URL]);self.assertEqual(len(errors),2)
        c.fetch.assert_called_once_with(URL,self.source,editorial=True)
        self.assertEqual(len(rows[0]['content_hash']),64)
        c=FakeCollector([row(date='2026-11-04 09:00:00')])
        rows, errors=discover(INDEX_HTML,INDEX,self.source,c,1,NOW)
        self.assertEqual(rows,[]);self.assertIn('date_conflict',errors[0]['reason'])

    def test_malformed_rows_and_zero_limit_cannot_fetch_article_urls(self):
        c=FakeCollector([None,row(date=None),row(url='/de/shop/private'),row(url=URL+'#fragment')])
        rows, errors=discover(INDEX_HTML,INDEX,self.source,c,2,NOW)
        self.assertEqual(rows,[]);self.assertEqual(len(errors),4);c.fetch.assert_not_called()
        c=FakeCollector()
        self.assertEqual(discover(INDEX_HTML,INDEX,self.source,c,0,NOW),([],[]));c.request.assert_not_called()

    def test_existing_official_publisher_and_refresh_keep_exact_source_hashes(self):
        c=FakeCollector()
        bundle=collect_bundle('byd-de-press',URL,c,now=NOW)
        self.assertEqual(bundle_errors(bundle,NOW),[])
        self.assertEqual(bundle['items'][0]['payload']['content'],BODY.strip())
        self.assertTrue(same_sources(bundle,refresh_bundle(bundle,c,NOW)))
        c.html=article(body=BODY+' Changed original statement.')
        self.assertFalse(same_sources(bundle,refresh_bundle(bundle,c,NOW)))

    def test_collection_remains_idempotent_metadata_only_without_provider_or_publication(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory)/'private.sqlite')) as store, \
                patch('news_ai.NewsAi.request') as provider, patch('news_http.datetime', wraps=datetime) as clock:
            clock.now.return_value = NOW
            source={**self.source,'enabled':True};c=FakeCollector()
            self.assertEqual(collect(store,[source],c,1,True)['new_items'],1)
            self.assertEqual(collect(store,[source],c,1,True)['new_items'],0)
            self.assertEqual(store.rows('news_articles'),[]);provider.assert_not_called()
            self.assertNotIn('content',store.rows('news_items')[0]['payload'])

    def test_table_context_is_held_and_adapter_is_bound_into_the_code_identity(self):
        from news_publisher_articles import evidence_readiness
        from run_publisher_news import HASH_FILES
        c=FakeCollector();c.html=article(body=BODY+'<table><tr><td>999 kWh</td></tr></table>')
        bundle=collect_bundle('byd-de-press',URL,c,now=NOW)
        self.assertIn('publisher_table_context_requires_validation',evidence_readiness(bundle,NOW)['errors'])
        self.assertNotIn('999',bundle['items'][0]['payload']['content'])
        self.assertIn('news_byd.py',HASH_FILES)

    def test_german_vehicle_news_can_be_triaged_but_offers_hybrids_prices_and_rumours_cannot(self):
        from news_publisher_selection import candidate_assessment
        def assess(title,summary=''):
            return candidate_assessment({'title':title,'summary':summary,'published_at':NOW.isoformat()},NOW)
        for title in ['Synthetisches Elektroauto startet in Deutschland',
                      'BYD pr\u00e4sentiert neues Elektroauto in China',
                      'Festk\u00f6rperbatterie f\u00fcr Elektrofahrzeuge in China vorgestellt']:
            self.assertTrue(assess(title)['eligible'], title)
        self.assertEqual(assess('BYD pr\u00e4sentiert neues Elektroauto in China')['reason'],'international_vehicle_development')
        self.assertEqual(assess('Neues Elektroauto', 'Ein neues Modell auf dem deutschen Markt.')['reason'],'european_scope')
        for title in ['Elektroauto: Kundenangebot in Deutschland', 'Preise f\u00fcr Elektroauto in Deutschland',
                      'Ger\u00fcchte: neues Elektroauto in China', 'BYD Super-Hybrid in Europa',
                      'Elektroauto-Roadshow in Deutschland', 'BYD H\u00e4ndlerkonferenz in Deutschland']:
            self.assertFalse(assess(title)['eligible'], title)
        self.assertEqual(assess('BYD und E.ON: Laden zuhause', 'Ein Kundenangebot f\u00fcr vollelektrische Modelle.')['reason'],
                         'local_offer_or_minor_publicity')


if __name__=='__main__': unittest.main()
