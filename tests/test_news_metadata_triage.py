"""Free metadata recovery is not evidence, a paid trial or publication approval."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from news_publisher_registry import PUBLISHERS, publisher_templates
from news_publisher_selection import ranked_candidates, candidate_assessment, bounded_reading_queue
from news_publisher_sources import collect_bundle, PublisherContentHeld, item_from_document
from news_run_summary import summarize

NOW=datetime(2026,11,5,8,tzinfo=timezone.utc)
URL='https://www.motor.no/bil/synthetic-kia-ev2-test/999999'

def item(title='Motor har testet Kia EV2', url=URL):
    return {'source_id':'motor-no','url':url,'status':'collected',
            'payload':{'title':title,'summary':'','published_at':NOW.isoformat()}}


class MetadataTriageTests(unittest.TestCase):
    def test_approved_branded_vehicle_route_allows_only_bounded_free_content_triage(self):
        rows,held=ranked_candidates([item()],{'motor-no'},now=NOW,hydrate_publishers=PUBLISHERS)
        self.assertEqual(held,[])
        self.assertEqual(rows[0][1]['reason'],'publisher_content_triage_required')
        self.assertLess(rows[0][1]['priority'],40)
        self.assertFalse(candidate_assessment(item(),NOW)['eligible'])
        many=[item(url=URL.replace('999999',str(900000+i))) for i in range(20)]
        self.assertEqual(len(ranked_candidates(many,{'motor-no'},now=NOW,hydrate_publishers=PUBLISHERS)[0]),8)

    def test_date_history_prices_hybrids_speculation_and_other_routes_are_not_overridden(self):
        cases=[item('Kia EV2 priser i Sverige'),item('Kia plug-in hybrid'),item('Kia spotted testing'),
               item('Kia test',URL.replace('/bil/','/aktuelt/')),item('Unidentified vehicle test'),
               item(url=URL.replace('www.motor.no','evil.example')),item(url=URL+'?private=1')]
        stale=item();stale['payload']['published_at']=(NOW-timedelta(days=8)).isoformat();cases.append(stale)
        for row in cases:
            with self.subTest(row=row):
                self.assertEqual(ranked_candidates([row],{'motor-no'},now=NOW,hydrate_publishers=PUBLISHERS)[0],[])
        self.assertEqual(ranked_candidates([item()],{'motor-no'},[URL],NOW,hydrate_publishers=PUBLISHERS)[0],[])

    def test_french_body_styles_are_recognized_and_swedish_nominations_are_held(self):
        for kind in ('SUV','berline','crossover','citadine'):
            self.assertTrue(candidate_assessment({'title':f'Xpeng : nouveau {kind} \u00e9lectrique en Europe',
                'published_at':NOW.isoformat()},NOW)['eligible'])
        self.assertFalse(candidate_assessment({'title':'Cupra Raval till final i \u00c5rets Bil',
            'summary':'En elbil i Europa.', 'published_at':NOW.isoformat()},NOW)['eligible'])
        self.assertEqual(candidate_assessment({'title':'Renault pr\u00e9sente un v\u00e9hicule \u00e9lectrique pour les drones militaires',
            'published_at':NOW.isoformat()},NOW)['reason'],'outside_passenger_ev_scope')

    def test_thin_candidate_gets_one_existing_slot_without_displacing_officials_or_expanding_queue(self):
        reports=[{'source_id':'carnewschina','url':f'https://carnewschina.com/2026/11/05/synthetic-{i}/',
            'status':'collected','payload':{'title':'BMW electric car launches in Europe','published_at':NOW.isoformat()}}
            for i in range(10)]
        selected,_=ranked_candidates(reports+[item()],{'carnewschina','motor-no'},now=NOW,hydrate_publishers=PUBLISHERS)
        self.assertEqual(len(selected),8)
        self.assertIn(URL,[pair[0]['url'] for pair in selected])
        official=[({'source_id':'vw-press','url':f'https://official.example/{i}'},{'reason':'official_content_triage_required'}) for i in range(8)]
        self.assertEqual(bounded_reading_queue(official,selected,PUBLISHERS),official)
        merged=bounded_reading_queue(official[:1]+selected,selected,PUBLISHERS)
        self.assertEqual(len(merged),8);self.assertEqual(merged[0],official[0])
        self.assertIn(URL,[pair[0]['url'] for pair in merged])

    def test_content_without_vehicle_evidence_stops_before_original_lookup_or_provider(self):
        lead={'url':URL,'payload':{'title':'Motor har testet Kia EV2','published_at':NOW.isoformat(),
              'content':'A synthetic calendar and a company picnic. '*40}}
        with patch('news_publisher_sources.fetch_publisher',return_value=(lead,[])), \
                patch('news_publisher_sources.discover_originals') as original, \
                patch('news_ai.NewsAi.request') as provider:
            with self.assertRaises(PublisherContentHeld) as result:
                collect_bundle('motor-no',URL,Mock(),now=NOW,content_triage=True)
            self.assertEqual(result.exception.discovery_trace[0]['reason'],'vehicle_connection_not_established')
            original.assert_not_called();provider.assert_not_called()

    def test_valid_body_can_prepare_single_source_but_is_not_a_publication(self):
        lead=item_from_document(URL,PUBLISHERS['motor-no'],
            {'title':'Motor har testet Kia EV2','published_at':NOW.isoformat(),
             'content':'Kia EV2 is an electric passenger car for Europe. '*40},NOW)
        with patch('news_publisher_sources.fetch_publisher',return_value=(lead,[])), \
                patch('news_publisher_sources.discover_originals',return_value=[]), \
                patch('news_publisher_sources.corroboration_candidates',return_value=[]), \
                patch('news_ai.NewsAi.request') as provider:
            bundle=collect_bundle('motor-no',URL,Mock(),now=NOW,content_triage=True)
            self.assertEqual(bundle['evidence_basis'],'editorial_single_source')
            provider.assert_not_called()

    def test_unsupported_template_configuration_is_rejected(self):
        import json
        templates=json.loads((Path(__file__).resolve().parents[1]/'data/news/publisher_templates.json').read_text())
        templates[-1]['metadata_triage_path_pattern']='https://evil.example'
        with self.assertRaisesRegex(ValueError,'triage_path'):publisher_templates(templates=templates)

    def test_gap_summary_exposes_only_known_subjects_and_reason_counts(self):
        raw={'status':'no_eligible_new_source','skipped':[{'subjects':['nio','nio','Private secret prose',{'bad':1}],
            'reason':'OriginalSourceNotFound:publisher_no_primary_or_independent_pair:private detail',
            'discovery_trace':[{'status':'no_matching_declared_authority','url':'https://private.example/key'}]}]}
        report=summarize(raw)
        self.assertEqual(report['source_gaps'],{'missing_authority':{'nio':1}})
        self.assertNotIn('private',str(report).lower());self.assertNotIn('secret',str(report).lower())
        self.assertNotIn('https',str(report))
        self.assertEqual(summarize({'skipped':[{'subjects':'private','reason':'OriginalSourceNotFound:publisher_no_primary_or_independent_pair'}]})['source_gaps'],
                         {'original_not_found':{'unidentified_subject':1}})


if __name__=='__main__':unittest.main()
