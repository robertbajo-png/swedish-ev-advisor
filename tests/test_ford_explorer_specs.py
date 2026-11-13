import copy
import json
import sys
import unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ford_explorer_specs_intake import extract,PDF_URL
from variant_refresh import RefreshError


class ExplorerSpecsTests(unittest.TestCase):
    def setUp(self):
        self.packet=json.loads((Path(__file__).parent/'fixtures/ford_explorer_source_packets.json').read_text(encoding='utf-8'))
        self.now=max(datetime.fromisoformat(self.packet[k]['source']['fetched_at']) for k in ('pdf','premium','offers','cargo'))

    def extract(self,p=None):
        p=p or self.packet
        return extract(p['pdf']['content'],*[p[k]['content'] for k in ('premium','offers','cargo')],
                       {k:p[k]['source'] for k in ('pdf','premium','offers','cargo')},self.now)

    def test_two_exact_current_profiles_not_legacy_or_nordic(self):
        rows=self.extract()
        self.assertEqual([r['facts']['battery_kwh'] for r in rows],[79,77])
        self.assertEqual([r['facts']['wltp_range_km'] for r in rows],[572,519])
        self.assertEqual([r['facts']['dc_charge_kw'] for r in rows],[185,175])
        self.assertEqual([r['facts']['tow_kg'] for r in rows],[2000,2200])
        self.assertEqual([r['facts']['wltp_consumption_kwh_100km'] for r in rows],[15.5,17.3])
        for r in rows:
            self.assertEqual(len(r['facts']),9)
            self.assertEqual(r['facts']['ac_charge_kw'],11)
            self.assertEqual(r['facts']['boot_liters'],472)
            self.assertEqual(r['facts']['seats'],5)
            self.assertIn('MY27.25',r['replacement_variant_name'])

    def test_campaign_not_reference_or_leasing_and_shared_premium_expiry_required(self):
        rows=self.extract()
        self.assertEqual([r['price_evidence']['value'] for r in rows],[549000,569000])
        self.assertEqual([r['price_evidence']['reference_price'] for r in rows],[626000,686000])
        self.assertEqual([r['price_evidence']['price_type'] for r in rows],['campaign_price']*2)
        self.assertEqual(rows[0]['price_evidence']['price_valid_until'],'2026-12-30')
        self.assertEqual(rows[1]['price_evidence']['price_valid_until'],'2026-12-30')

    def test_old_model_year_swapped_columns_and_maximums_rejected(self):
        for old,new in [('MY27.25 - Premium Edition','MY25.75 - Premium Edition'),
                        ('79 kWh','77 kWh'),('572 15,5','602 14,6'),
                        ('185 kW DC-snabbladdning (RWD)','135 kW DC-snabbladdning (RWD)'),
                        ('LR AWD 2200 kg','LR AWD 1200 kg'),('549 000 kr','626 000 kr')]:
            p=copy.deepcopy(self.packet)
            p['pdf']['content']=[t.replace(old,new) for t in p['pdf']['content']]
            with self.subTest(old=old),self.assertRaises(RefreshError):self.extract(p)

    def test_named_explorer_cargo_not_capri_or_folded_seats(self):
        for old,new in [('472 liter 572 liter','572 liter 472 liter'),('Dimensioner Explorer® Capri®','Dimensioner Capri® Explorer®'),
                        ('472 liter','1460 liter')]:
            p=copy.deepcopy(self.packet);p['cargo']['content']=p['cargo']['content'].replace(old,new)
            with self.subTest(old=old),self.assertRaises(RefreshError):self.extract(p)
        row=self.extract()[0]
        self.assertEqual(row['field_evidence']['boot_liters']['source_url'],'https://www.ford.dk/koeb/kampagner/explorer-og-capri')
        self.assertEqual(row['field_evidence']['tow_kg']['source_url'],PDF_URL)

    def test_source_unavailable_stale_foreign_or_missing_hash_rejected(self):
        for patch in [dict(status='robots_denied_or_unavailable'),dict(http_status=403),
                      dict(final_url=PDF_URL.replace('fordsesite','other')),dict(content_hash=''),
                      dict(fetched_at=(self.now-timedelta(minutes=16)).isoformat())]:
            p=copy.deepcopy(self.packet);p['pdf']['source'].update(patch)
            with self.subTest(patch=patch),self.assertRaises(RefreshError):self.extract(p)

    def test_expired_awd_offer_and_missing_swedish_seating_fail_closed(self):
        for key,old,new in [('offers','2026-12-30','2026-01-01'),('premium','5 sittplatser','7 sittplatser'),
                            ('premium','RWD från 549 000','RWD från 5 495'),
                            ('premium','30 december 2026','31 december 2026')]:
            p=copy.deepcopy(self.packet);p[key]['content']=p[key]['content'].replace(old,new)
            with self.subTest(key=key),self.assertRaises(RefreshError):self.extract(p)


if __name__=='__main__':unittest.main()
