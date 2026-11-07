"""Synthetic Electra layout cases, not live writer/reviewer receipts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from news_pressrooms import document
from news_publisher_sources import primary_source, collect_bundle, bundle_errors
from news_publisher_articles import evidence_readiness

URL = 'https://www.go-electra.com/en/newsroom/synthetic-charging-partnership/'
TITLE = 'Electra expands electric vehicle charging access across Europe'
BODY = ('<p>Paris, 3 November 2026</p><p>Electra expands its charging network for electric passenger cars across Europe.</p>'
        '<p>The company describes new station access through the vehicle and the charging application.</p>'
        '<p>Drivers may reserve compatible charging points before arriving at an eligible station.</p>'
        '<p>The service requires a separate charging contract with a selected third party provider.</p>'
        '<p>These are operator claims and do not establish availability in the Swedish market.</p>')
NOW = datetime(2026,11,7,tzinfo=timezone.utc)


def page(canonical=None):
    canonical = canonical or 'https://www.go-electra.com/en//en/newsroom/synthetic-charging-partnership/'
    return (f'<link rel="canonical" href="{canonical}"><meta property="og:title" content="{TITLE}">'
        '<script type="application/ld+json">'+json.dumps({'@type':'WebSite','name':'Electra','url':canonical})+'</script>'
        '<script type="application/ld+json">'+json.dumps({'@type':'WebPage','name':TITLE})+'</script>'
        f'<main><h1>{TITLE}</h1><div><p class="body-sm text-secondary-text">Nov 3, 2026</p></div>'
        '<div>EXCLUDED_PROMOTION</div><div class="prose">'+BODY+
        '<p hidden>EXCLUDED_HIDDEN</p><h2>Electra Contacts:</h2><p>EXCLUDED_CONTACT</p></div></main>')


class ElectraTests(unittest.TestCase):
    def test_exact_page_identity_known_prefix_bug_and_qualifications(self):
        for canonical in (URL, 'https://www.go-electra.com/en/'+URL.split('go-electra.com')[1]):
            doc=document(page(canonical),url=URL,adapter='electra_en')
            self.assertEqual(doc['published_at'],'2026-11-03T00:00:00+00:00')
            self.assertIn('separate charging contract',doc['body'])
            self.assertNotIn('EXCLUDED',doc['body'])

    def test_unknown_canonical_repairs_and_mismatched_identity_are_rejected(self):
        for canonical in (URL+'?x=1',URL.replace('synthetic-','other-'),URL.replace('/en/','/fr/'),
                          URL.replace('go-electra.com','go-electra.com.evil.example')):
            with self.assertRaises(ValueError): document(page(canonical),url=URL,adapter='electra_en')
        for html in (page().replace('"name": "Electra"','"name": "Someone Else"'),
                     page().replace('<h1>'+TITLE,'<h1>Other headline'),page()+page()):
            with self.assertRaises(ValueError): document(html,url=URL,adapter='electra_en')

    def test_missing_conflicting_dates_and_hidden_or_duplicate_narratives_are_held(self):
        for html in (page().replace('Nov 3, 2026','Nov 4, 2026'),page().replace('Nov 3, 2026',''),
                     page().replace('Paris, 3 November 2026','Paris, 4 November 2026'),
                     page().replace('class="prose"','class="prose" hidden'),
                     page().replace('</main>','<div class="prose">Other narrative</div></main>')):
            with self.assertRaises(ValueError): document(html,url=URL,adapter='electra_en')
        with self.assertRaises(ValueError): document(page(),url=URL.replace('/en/','/fr/'),adapter='electra_en')

    def test_original_source_uses_normal_access_snapshot_and_article_material_gates(self):
        self.assertEqual(primary_source(URL)['id'],'electra-news')
        collector=Mock();collector.fetch.return_value=(200,{},page(),URL)
        bundle=collect_bundle('electra-news',URL,collector,now=NOW)
        self.assertEqual(bundle_errors(bundle,NOW),[])
        checked=evidence_readiness(bundle,NOW)
        self.assertTrue(checked['ready'],checked)
        self.assertEqual(collector.fetch.call_args.kwargs,{'editorial':True})
        from run_publisher_news import HASH_FILES
        self.assertIn('news_electra.py',HASH_FILES)


if __name__=='__main__': unittest.main()
