"""Synthetic importer/pressroom regressions; fixtures never approve publication."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_pressrooms import document, discover
from news_publisher_sources import primary_source, collect_bundle, bundle_errors, same_sources, refresh_bundle
from news_primary_discovery import discover as original_discovery, valid_edge
from news_publisher_selection import candidate_assessment
from news_engine import collect
from news_store import NewsStore

NOW = datetime(2026, 11, 5, 8, tzinfo=timezone.utc)
DATE = (NOW-timedelta(days=1)).isoformat()
URL = 'https://xpengswitzerland.pr.co/123456-synthetic-electric-family-suv/'
TITLE = 'XPENG introduces a synthetic electric family SUV for Europe'
BODY = ('Synthetic source evidence says European vehicle details remain preliminary. '
        'Swiss equipment and launch dates are not confirmed for Swedish buyers. ')*5


def page(url=URL, date=DATE, body=BODY, extra='', record=None):
    record = record or {'@type': 'NewsArticle', 'url': url, 'datePublished': date,
        'dateModified': '2099-01-01', 'headline': TITLE, 'publisher': {'name': 'XPENG'}}
    return (f'<link rel="canonical" href="{url}"><meta property="og:title" content="{TITLE}">'
        f'<meta property="article:published_time" content="{date}">'
        '<script type="application/ld+json">'+json.dumps(record)+'</script>'
        f'<main><article class="container"><h1>{TITLE}</h1><time datetime="{date[:10]}">Original day</time>'
        f'<div class="article-block article-block__p">{body}'
        '<div class="c-sideline-actions">EXCLUDED_SHARING</div>'
        '<table><tr><td>EXCLUDED_TABLE_NUMBER 9999 km</td></tr></table></div>'
        '<div class="boilerplate-block"><div class="article-block__p">EXCLUDED_COMPANY_PROFILE</div></div>'
        '<aside>EXCLUDED_CONTACT</aside></article>'
        '<section class="related-news"><time datetime="2099-01-01">Future related date</time>'
        '<div class="article-block__p">EXCLUDED_RELATED</div></section>'+extra+'</main>')


def lexus_page(url, body_class, body=BODY, date=DATE):
    record = {'@type': 'Article', 'mainEntityOfPage': {'@id': url}, 'datePublished': date,
              'dateModified': '2099-01-01', 'headline': TITLE}
    return (f'<link rel="canonical" href="{url}"><meta property="og:title" content="{TITLE}">'
        '<script type="application/ld+json">'+json.dumps(record)+'</script>'
        f'<main>EXCLUDED_NAVIGATION<div class="{body_class}">{body}</div>'
        '<aside>EXCLUDED_CONTACT</aside><time datetime="2099-01-01">Related day</time></main>')


def atom(date=DATE, url=URL):
    return ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>'+TITLE+'</title>'
        '<link rel="alternate" href="'+url+'"/><published>'+date+'</published>'
        '<updated>2099-01-01T00:00:00Z</updated></entry></feed>')


class XpengLexusTests(unittest.TestCase):
    def test_importer_identity_has_explicit_evidence_and_no_arbitrary_prco_hosts(self):
        source = primary_source(URL)
        self.assertEqual(source['id'], 'xpeng-ch-press')
        self.assertEqual(source['covered_brands'], ['XPeng'])
        self.assertEqual(len(source['identity_evidence_urls']), 2)
        for bad in (URL.replace('xpengswitzerland','someoneelse'), URL+'?token=secret',
                    URL.replace('/123456-', '/tags/')):
            self.assertIsNone(primary_source(bad))
        self.assertIsNone(primary_source('https://www.xpeng.com/news/0123456789abcdef0123456789abcdef'))

    def test_importer_parser_keeps_qualifiers_not_boilerplate_tables_or_related_dates(self):
        parsed = document(page(), url=URL, adapter='xpeng_ch')
        self.assertEqual(parsed['body'], BODY.strip())
        self.assertEqual(parsed['published_at'], DATE)
        self.assertNotIn('EXCLUDED', parsed['body'])
        self.assertIn('not confirmed for Swedish', parsed['body'])
        html=page().replace('property="og:title" content="XPENG introduces',
                            'property="og:title" content="XPENG\u00a0 introduces')
        self.assertEqual(document(html,url=URL,adapter='xpeng_ch')['body'],BODY.strip())

    def test_schema_entities_are_decoded_once_without_changing_model_identity(self):
        title=TITLE+" 'synthetic'"
        html=page().replace(TITLE,title)
        encoded=html.replace('"headline": "'+title+'"','"headline": "'+title.replace("'",'&#39;')+'"')
        self.assertEqual(document(encoded,url=URL,adapter='xpeng_ch')['body'],BODY.strip())
        with self.assertRaises(ValueError):
            document(encoded.replace('&#39;','&amp;#39;'),url=URL,adapter='xpeng_ch')

    def test_canonical_route_heading_and_structured_identity_must_match(self):
        cases = [page().replace('rel="canonical"', 'rel="unknown"'),
            page().replace('href="'+URL+'"','href="https://xpengswitzerland.pr.co/"'),
            page().replace('<h1>'+TITLE,'<h1>Wrong model'),
            page().replace('"name": "XPENG"','"name": "Unrelated"'),
            page().replace('"url": "'+URL+'"','"url": "'+URL+'other/"'),
            page().replace('"headline": "'+TITLE+'"','"headline": "Wrong model"')]
        for html in cases:
            with self.subTest(html=html[:90]), self.assertRaises(ValueError):
                document(html, url=URL, adapter='xpeng_ch')
        for url in (URL+'?private=1', URL.replace('https:','http:'), URL.replace('pr.co','pr.co.evil.example')):
            with self.assertRaises(ValueError): document(page(), url=url, adapter='xpeng_ch')

    def test_duplicates_missing_hidden_or_nested_body_cannot_become_evidence(self):
        cases = [page(body=''), page()+page(),
            page().replace('class="container"','class="container" hidden'),
            page().replace('class="container"','class="container" style="display: none"'),
            page().replace('class="container"','class="container" aria-hidden="true"'),
            page().replace('<h1>'+TITLE+'</h1>', '<h1>'+TITLE+'</h1><h1>'+TITLE+'</h1>'),
            page(body='<div class="article-block__p">'+BODY+'</div>')]
        for html in cases:
            with self.subTest(html=html[-80:]), self.assertRaises(ValueError):
                document(html, url=URL, adapter='xpeng_ch')

    def test_modification_and_feed_updates_never_refresh_an_old_original(self):
        old=(NOW-timedelta(days=10)).isoformat()
        self.assertEqual(document(page(date=old),url=URL,adapter='xpeng_ch')['published_at'],old)
        source=primary_source(URL);c=Mock();c.fetch.return_value=(200,{},page(date=old),URL)
        rows,errors=discover(atom(old),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(rows,[]);c.fetch.assert_not_called()
        self.assertIn('stale_report',errors[0]['reason'])
        rows,errors=discover(atom(),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(rows,[]);self.assertIn('stale_report',errors[0]['reason'])
        with self.assertRaises(ValueError):
            document(page().replace('"datePublished": "'+DATE+'"','"datePublished": "2099-01-01"'),url=URL,adapter='xpeng_ch')

    def test_multiple_or_nonorganizational_article_metadata_is_rejected(self):
        record={'@type':'NewsArticle','url':URL,'datePublished':DATE,
                'headline':TITLE,'publisher':{'name':'XPENG'}}
        duplicate=page(extra='<script type="application/ld+json">'+json.dumps(record)+'</script>')
        malformed=page(record={**record,'publisher':'XPENG'})
        for html in (duplicate,malformed):
            with self.assertRaises(ValueError):document(html,url=URL,adapter='xpeng_ch')

    def test_atom_collection_bundle_and_exact_refresh_use_existing_guards(self):
        source=primary_source(URL);c=Mock();c.fetch.return_value=(200,{},page(),URL)
        rows,errors=discover(atom(),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(errors,[]);self.assertEqual(rows[0]['published_at'],DATE)
        bundle=collect_bundle(source['id'],URL,c,now=NOW)
        self.assertEqual(bundle_errors(bundle,NOW),[])
        self.assertTrue(same_sources(bundle,refresh_bundle(bundle,c,NOW)))
        c.fetch.return_value=(200,{},page(body=BODY+' A changed source fact.'),URL)
        self.assertFalse(same_sources(bundle,refresh_bundle(bundle,c,NOW)))
        from run_publisher_news import HASH_FILES
        self.assertIn('news_xpeng.py',HASH_FILES)

    def test_feed_conflict_redirect_and_foreign_host_do_not_enter_collection(self):
        source=primary_source(URL);c=Mock();c.fetch.return_value=(200,{},page(),URL+'other/')
        rows,errors=discover(atom(),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(rows,[]);self.assertIn('redirected',errors[0]['reason'])
        c.reset_mock();rows,errors=discover(atom(url=URL.replace('pr.co','pr.co.evil.example')),source['indexes'][0],source,c,1,NOW)
        self.assertEqual(rows,[]);c.fetch.assert_not_called()

    def test_original_lookup_is_bounded_and_requires_exact_provenance(self):
        lead={'payload':{'title':TITLE,'content':BODY,'published_at':DATE}}
        registry={'xpengswitzerland.pr.co':primary_source(URL)}
        c=Mock();c.fetch.return_value=(200,{},atom(),registry['xpengswitzerland.pr.co']['indexes'][0])
        rows=original_discovery(lead,c,registry)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0][0],URL)
        self.assertTrue(valid_edge(rows[0][1],lead,registry))
        c.fetch.assert_called_once()
        self.assertFalse(valid_edge({**rows[0][1],'to_url':URL.replace('pr.co','evil.example')},lead,registry))

    def test_lexus_scopes_reuse_existing_parser_without_unrelated_dates_or_furniture(self):
        for url,kind in [('https://newsroom.lexus.eu/synthetic-lexus-electric-suv/','text_companyprofile'),
                         ('https://media.lexus.co.uk/synthetic-lexus-electric-suv/','entry-content')]:
            source=primary_source(url)
            parsed=document(lexus_page(url,kind),url=url,body_region=source['body_region'],narrative_class=source['narrative_class'])
            self.assertEqual(parsed['body'],BODY.strip());self.assertEqual(parsed['published_at'],DATE)
            for html in [lexus_page(url,'wrong-scope'),lexus_page(url,kind).replace('</main>',f'<div class="{kind}">{BODY}</div></main>')]:
                with self.assertRaises(ValueError):document(html,url=url,body_region='main',narrative_class=kind)
        self.assertIsNone(primary_source('https://media.lexus.co.uk/category/corporate/'))
        self.assertIsNone(primary_source('https://newsroom.lexus.eu/lexus-nx/'))

    def test_regional_prices_and_hybrids_still_do_not_buy_ai_articles(self):
        for title,summary in [('XPENG SUV prices announced in Switzerland','Electric family car'),
                ('Lexus reveals a new plug-in hybrid SUV in Europe','New electrified car'),
                ("XPENG electric SUV now available from CHF 74'600",'European debut'),
                ("XPENG SUV elettrico ordinabile da CHF 74'600",'New electric family car'),
                ("XPENG SUV electrique commandable a partir de CHF 74'600",'European debut')]:
            self.assertFalse(candidate_assessment({'title':title,'summary':summary,'published_at':DATE},NOW)['eligible'])

    def test_valid_but_out_of_scope_rss_is_quiet_not_a_broken_source(self):
        source={**primary_source('https://media.lexus.co.uk/synthetic-lexus-electric-suv/'),'enabled':True}
        feed='<rss><channel><item><title>Unrelated tennis event</title><link>https://media.lexus.co.uk/tennis-event/</link><pubDate>'+DATE+'</pubDate></item></channel></rss>'
        c=Mock();c.fetch.return_value=(200,{},feed,source['indexes'][0])
        with tempfile.TemporaryDirectory() as folder:
            store=NewsStore(Path(folder)/'news.sqlite')
            try:
                result=collect(store,[source],c,force=True)
                self.assertEqual(result['sources'][0]['status'],'verified_no_recent_items')
                self.assertEqual(result['new_items'],0);self.assertEqual(store.rows('news_articles'),[])
                c.fetch.assert_called_once()
                for bad in ('<html>Not a feed</html>','<rss><channel></channel></rss>'):
                    c.fetch.return_value=(200,{},bad,source['indexes'][0])
                    self.assertEqual(collect(store,[source],c,force=True)['sources'][0]['status'],'no_verified_feed')
            finally:store.close()


if __name__=='__main__':unittest.main()
