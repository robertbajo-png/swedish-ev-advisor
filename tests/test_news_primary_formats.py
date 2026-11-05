"""Synthetic primary formats: rendered state and RSS are not publication approval."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from news_pressrooms import document, discover
from news_publisher_sources import primary_source, collect_bundle, bundle_errors, same_sources, refresh_bundle
from news_publisher_selection import primary_identity_matches

NOW=datetime(2026,11,5,8,tzinfo=timezone.utc)
DATE=NOW.isoformat()
NIO_URL='https://www.nio.com/news/20261105001'
TOYOTA_URL='https://media.toyota.co.uk/synthetic-electric-model/'
BODY='Synthetic electric passenger car evidence for an isolated source-format regression test. '*15
TITLE='Synthetic electric passenger car source'


def nio_state():
    return {'page':'/news/[id]','query':{'id':'20261105001'},'locale':'en_US','isFallback':False,
        'props':{'pageProps':{'news':{'brand':'nio','locale':'en_US','type':'news','status':'published','isDeleted':False,
            'urlPath':'/20261105001','title':TITLE,'content':'<p>'+BODY+'</p>',
            'publishedAt':DATE,'displayPublishedAt':DATE,'updatedAt':'2099-01-01T00:00:00Z'}}}}


def nio_page(state=None, visible=BODY, url=NIO_URL):
    return (f'<title>{TITLE} - News | NIO</title><link rel="canonical" href="{url}">'
        f'<main><h1>{TITLE}</h1><p>{visible}</p></main><script id="__NEXT_DATA__" type="application/json">'
        +json.dumps(state or nio_state())+'</script>')


def toyota_page(url=TOYOTA_URL, date=DATE, extra=''):
    ld={'@graph':[{'@type':'Article','mainEntityOfPage':{'@id':url},'datePublished':date,'dateModified':'2099-01-01'}]}
    return (f'<link rel="canonical" href="{url}"><meta property="og:title" content="{TITLE}">'
        '<script type="application/ld+json">'+json.dumps(ld)+'</script>'
        f'<main>Excluded main furniture.<div class="entry-content">{BODY}<aside>Excluded related prose</aside></div>{extra}</main>'
        '<time datetime="2099-01-01">Excluded unrelated date</time>')


def feed(date=DATE, url=TOYOTA_URL):
    return f'<rss><channel><item><title>{TITLE}</title><link>{url}</link><pubDate>{date}</pubDate></item></channel></rss>'


class PrimaryFormatTests(unittest.TestCase):
    def test_nio_exact_rendered_public_state_uses_publication_not_modification(self):
        parsed=document(nio_page(),url=NIO_URL,adapter='nio')
        self.assertEqual(parsed['published_at'],DATE);self.assertEqual(parsed['body'],BODY.strip())
        self.assertNotIn('2099',parsed['published_at'])
        state=nio_state();older=(NOW-timedelta(hours=12)).isoformat()
        state['props']['pageProps']['news']['publishedAt']=older
        self.assertEqual(document(nio_page(state),url=NIO_URL,adapter='nio')['published_at'],older)

    def test_nio_wrong_identity_drafts_deleted_locale_and_dates_are_rejected(self):
        for field,value in [('status','draft'),('isDeleted',True),('locale','zh_CN'),('urlPath','/other'),
                ('brand','unknown'),('publishedAt',None),('displayPublishedAt','2099-01-01T00:00:00Z')]:
            state=nio_state();state['props']['pageProps']['news'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):document(nio_page(state),url=NIO_URL,adapter='nio')
        state=nio_state();state['query']['id']='other'
        with self.assertRaises(ValueError):document(nio_page(state),url=NIO_URL,adapter='nio')
        for url in [NIO_URL+'?private=1',NIO_URL.replace('www.nio.com','www.nio.com.evil.example'),NIO_URL.replace('https:','http:')]:
            with self.assertRaises(ValueError):document(nio_page(),url=url,adapter='nio')

    def test_nio_hidden_state_missing_heading_and_duplicate_state_are_not_evidence(self):
        for page in [nio_page(visible='Only a short teaser.'),nio_page().replace('<h1>','<h2>').replace('</h1>','</h2>'),
                     nio_page()+nio_page(),nio_page().replace('</main>','</main><p>'+BODY+'</p>').replace('<p>'+BODY+'</p></main>','</main>')]:
            with self.assertRaises(ValueError):document(page,url=NIO_URL,adapter='nio')

    def test_nio_collection_uses_adapter_and_stale_states_do_not_become_new(self):
        source=primary_source(NIO_URL);c=Mock();c.fetch.return_value=(200,{},nio_page(),NIO_URL)
        index=f'<a href="{NIO_URL}">Synthetic source</a>'
        rows,errors=discover(index,source['indexes'][0],source,c,1,NOW)
        self.assertEqual(errors,[]);self.assertEqual(rows[0]['published_at'],DATE)
        state=nio_state();old=(NOW-timedelta(days=10)).isoformat()
        state['props']['pageProps']['news'].update(publishedAt=old,displayPublishedAt=old)
        c.fetch.return_value=(200,{},nio_page(state),NIO_URL)
        rows,errors=discover(index,source['indexes'][0],source,c,1,NOW)
        self.assertEqual(rows,[]);self.assertEqual(errors[0]['reason'],'ValueError:stale_report')

    def test_nio_existing_single_primary_bundle_and_refresh_remain_source_bound(self):
        c=Mock();c.fetch.return_value=(200,{},nio_page(),NIO_URL)
        bundle=collect_bundle('nio-press',NIO_URL,c,now=NOW)
        self.assertEqual(bundle_errors(bundle,NOW),[])
        self.assertTrue(same_sources(bundle,refresh_bundle(bundle,c,NOW)))
        state=nio_state();state['props']['pageProps']['news']['content']='<p>'+BODY+' New fact.</p>'
        c.fetch.return_value=(200,{},nio_page(state,visible=BODY+' New fact.'),NIO_URL)
        self.assertFalse(same_sources(bundle,refresh_bundle(bundle,c,NOW)))
        from run_publisher_news import HASH_FILES
        self.assertIn('news_nio.py',HASH_FILES)

    def test_strict_narrative_class_ignores_other_main_prose_and_related_time(self):
        parsed=document(toyota_page(),url=TOYOTA_URL,body_region='main',narrative_class='entry-content')
        self.assertEqual(parsed['body'],BODY.strip());self.assertEqual(parsed['published_at'],DATE)
        for page in [toyota_page(extra='<div class="entry-content">Ambiguous second narrative.</div>'),
                     toyota_page().replace('entry-content','unknown-content'),toyota_page(url=TOYOTA_URL+'other/')]:
            with self.assertRaises(ValueError):document(page,url=TOYOTA_URL,body_region='main',narrative_class='entry-content')
        with self.assertRaises(ValueError):document(toyota_page(),url=TOYOTA_URL,narrative_class='entry-content')

    def test_rss_official_index_requires_matching_actual_article_date_and_host(self):
        source=primary_source(TOYOTA_URL);c=Mock();c.fetch.return_value=(200,{},toyota_page(),TOYOTA_URL)
        rows,errors=discover(feed(),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(errors,[]);self.assertEqual(rows[0]['published_at'],DATE)
        c.fetch.assert_called_once_with(TOYOTA_URL,source,editorial=True)
        rows,errors=discover(feed((NOW-timedelta(days=1)).isoformat()),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(rows,[]);self.assertIn('date_conflict',errors[0]['reason'])
        c.reset_mock()
        rows,errors=discover(feed(url=TOYOTA_URL.replace('media.toyota.co.uk','evil.example')),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(rows,[]);c.fetch.assert_not_called()

    def test_empty_scoped_body_cannot_fall_back_to_page_furniture(self):
        page=toyota_page().replace(BODY,'').replace('Excluded main furniture.',BODY)
        c=Mock();c.fetch.return_value=(200,{},page,TOYOTA_URL)
        with self.assertRaisesRegex(ValueError,'primary_content_incomplete_or_oversized'):
            collect_bundle('toyota-uk-press',TOYOTA_URL,c,now=NOW)

    def test_rss_stale_metadata_conflicts_xml_entities_and_redirects_stay_held(self):
        source=primary_source(TOYOTA_URL);c=Mock()
        rows,errors=discover(feed((NOW-timedelta(days=9)).isoformat()),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(rows,[]);c.fetch.assert_not_called();self.assertIn('stale_report',errors[0]['reason'])
        with self.assertRaises(ValueError):discover('<!DOCTYPE rss>'+feed(),source['indexes'][0],source,c,1,NOW)
        conflict=feed().replace('</channel>','<item><title>Conflicting</title><link>'+TOYOTA_URL+'</link><pubDate>2026-11-04</pubDate></item></channel>')
        with self.assertRaises(ValueError):discover(conflict,source['indexes'][0],source,c,1,NOW)
        c.fetch.return_value=(200,{},toyota_page(),TOYOTA_URL+'other/')
        rows,errors=discover(feed(),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(rows,[]);self.assertIn('redirected',errors[0]['reason'])

    def test_recall_reporting_cannot_use_an_unrelated_launch_of_the_same_model(self):
        report={'payload':{'title':'Toyota recalls bZ4X electric cars in China','content':'A synthetic recall.'}}
        primary={'payload':{'title':'Toyota bZ4X electric car in China','content':'A synthetic launch in China.'}}
        self.assertFalse(primary_identity_matches(report,primary))
        primary['payload']['content']='Toyota confirms a recall of the bZ4X electric car in China.'
        self.assertTrue(primary_identity_matches(report,primary))
        report['payload']['title']='Toyota bZ4X electric cars in China \u53ec\u56de'
        primary['payload']['content']='Toyota launches the bZ4X electric car in China.'
        self.assertFalse(primary_identity_matches(report,primary))
        primary['payload']['content']='Toyota bZ4X electric car in China \u53ec\u56de'
        self.assertTrue(primary_identity_matches(report,primary))


if __name__=='__main__':unittest.main()
