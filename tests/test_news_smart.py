"""Synthetic smart adapter evidence, never provider or publication approval."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from news_pressrooms import document
from news_publisher_sources import primary_source, collect_bundle, bundle_errors
from news_publisher_selection import primary_identity_matches, subject_brands, candidate_assessment

NOW=datetime(2026,11,6,10,tzinfo=timezone.utc)
DATE='2026-11-03T08:00:00+00:00'
URL='https://media.smart.com/en-CEU/123456-smart-2-electric-model-update-for-europe/'
TITLE='smart #2 electric model update for Europe'
BODY=('The synthetic smart #2 electric car has preliminary equipment for Europe. '
      'Delivery follows homologation; this is not confirmation of Swedish availability. ')*5

def page(body=BODY):
    record={'@type':'NewsArticle','url':URL,'headline':TITLE,'datePublished':DATE,
            'dateModified':'2099-01-01','publisher':{'name':'smart'}}
    return (f'<link rel="canonical" href="{URL}"><meta property="og:title" content="{TITLE}">'
            f'<meta property="article:published_time" content="{DATE}">'
            '<script type="application/ld+json">'+json.dumps(record)+'</script>'
            f'<main><article><h1>{TITLE}</h1><div class="article-block__p">{body}</div>'
            '<div class="boilerplate-block">EXCLUDED_PROFILE</div><aside>EXCLUDED_CONTACT</aside>'
            '</article><section class="related-news">EXCLUDED_RELATED</section></main>')

class SmartSourceTests(unittest.TestCase):
    def test_declared_exact_european_source_preserves_original_qualifiers(self):
        source=primary_source(URL)
        self.assertEqual(source['id'],'smart-eu-press')
        self.assertTrue(source['primary_date_required'])
        value=document(page(),url=URL,adapter='smart_eu')
        self.assertEqual(value['published_at'],DATE)
        self.assertEqual(value['body'],BODY.strip())
        self.assertNotIn('EXCLUDED',value['body'])

    def test_other_hosts_locales_queries_and_missing_identity_are_rejected(self):
        for url in (URL+'?key=private',URL.replace('media.smart.com','media.smart.com.evil.example'),
                    URL.replace('/en-CEU/','/other/'),URL.replace('https:','http:')):
            self.assertIsNone(primary_source(url))
            with self.assertRaises(ValueError):document(page(),url=url,adapter='smart_eu')
        for html in (page().replace('rel="canonical"','rel="unknown"'),
                     page().replace('"name": "smart"','"name": "Someone Else"'),
                     page().replace('<h1>'+TITLE,'<h1>Wrong model'),
                     page().replace('"datePublished": "'+DATE+'"','"datePublished": "2099-01-01"')):
            with self.assertRaises(ValueError):document(html,url=URL,adapter='smart_eu')

    def test_hidden_ambiguous_or_missing_narrative_is_held(self):
        for html in (page(body=''),page()+page(),page().replace('<article>','<article hidden>'),
                     page().replace('<article>','<article aria-hidden="true">'),
                     page().replace('<article>','<article style="display:none">')):
            with self.assertRaises(ValueError):document(html,url=URL,adapter='smart_eu')
        html=page(body=BODY.replace('homologation','approval')).replace('</article>',
            '<p>Mandatory homologation qualification outside the narrative.</p></article>')
        with self.assertRaisesRegex(ValueError,'qualification'):document(html,url=URL,adapter='smart_eu')

    def test_single_official_bundle_uses_full_existing_snapshot_guards(self):
        collector=Mock();collector.fetch.return_value=(200,{},page(),URL)
        bundle=collect_bundle('smart-eu-press',URL,collector,feed_date=DATE,now=NOW)
        self.assertEqual(bundle_errors(bundle,NOW),[])
        self.assertEqual(bundle['evidence_basis'],'official_release')
        self.assertEqual(len(bundle['items']),1)
        self.assertEqual(collector.fetch.call_args.kwargs,{'editorial':True})

    def test_model_numbers_cannot_match_siblings_or_generic_smart_charging(self):
        self.assertEqual(subject_brands('BMW introduces smart charging'),{'bmw'})
        self.assertEqual(subject_brands('smart #2 electric car'),{'smart'})
        report={'payload':{'title':'smart #2 electric model update in Europe'}}
        wrong={'payload':{'title':'smart #5 electric model update in Europe','content':BODY}}
        self.assertFalse(primary_identity_matches(report,wrong))
        correct={'payload':{'title':'smart #2 electric model update in Europe','content':BODY}}
        self.assertTrue(primary_identity_matches(report,correct))
        report['payload']['title']='Volkswagen ID.7 electric model update in Europe'
        wrong['payload'].update(title='Volkswagen ID.4 electric model update in Europe',content=BODY)
        self.assertFalse(primary_identity_matches(report,wrong))

    def test_retail_opening_is_not_promoted_to_a_vehicle_launch(self):
        title='smart #2 Swiss Premiere at Opening of New Flagship Venue in Zurich'
        self.assertFalse(candidate_assessment({'title':title,'content':BODY,'published_at':DATE},NOW)['eligible'])

if __name__=='__main__':unittest.main()
