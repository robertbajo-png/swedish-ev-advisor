import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from kia_ev2_intake import extract,PROFILES
from variant_refresh import RefreshError
from prerender_static_routes import public_variant_routes


class Ev2IntakeTests(unittest.TestCase):
    def setUp(self):
        d=json.loads((Path(__file__).parent/'fixtures/kia_ev2_packets.json').read_text(encoding='utf8'))
        self.p,self.market=d['packets'],d['market']
        self.now=max(datetime.fromisoformat(s['source']['fetched_at']) for s in [*self.p.values(),self.market])

    def changed(self,key,old,new,page=None):
        p=copy.deepcopy(self.p)
        value=p[key]['html'] if page is None else p[key]['pages'][page]
        self.assertIn(old,value)
        if page is None:p[key]['html']=value.replace(old,new)
        else:p[key]['pages'][page]=value.replace(old,new)
        return p

    def test_three_complete_exact_profiles(self):
        d=extract(self.p,self.market,self.now)
        self.assertEqual(len(d['drafts']),3)
        for r,p in zip(d['drafts'],PROFILES):
            self.assertEqual(r['manufacturer_identity'],p[1]);self.assertEqual(len(r['facts']),9)
            self.assertEqual(r['facts']['seats'],5);self.assertEqual(r['facts']['boot_liters'],362)
            self.assertEqual(r['facts']['wltp_range_km'],p[6]);self.assertEqual(r['price_evidence']['value'],p[4])

    def test_current_final_pdf_not_old_preliminary_brochure(self):
        for old,new,page in [('29 september 2026','18 mars 2026',0),
            ('MOTOR Standard Range Long Range','MOTOR Preliminär Long Range',2),
            ('Motoreffekt kW 107,8 99,5','Motoreffekt kW 107,8 107,8',2)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):
                extract(self.changed('technical',old,new,page),self.market,self.now)

    def test_standard_wheels_not_maximum_across_trims(self):
        for old,new in [('453 (16"), 439 (18") & 413 (19")','453 (16"), 453 (18") & 453 (19")'),
            ('LR =14,9 (16"), 15,2 (18") & 16,3 (19")','LR =14,9 (16"), 15,2 (18") & 14,9 (19")')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):
                extract(self.changed('technical',old,new,2),self.market,self.now)

    def test_five_seat_boot_not_four_seat_sliding_maximum_or_folded(self):
        for value in ['403','1201','15']:
            with self.subTest(value=value),self.assertRaises(RefreshError):
                extract(self.changed('technical','5 säten = 362','5 säten = '+value,2),self.market,self.now)

    def test_trim_ids_repeat_across_seating_and_need_exact_engine_pair(self):
        for old,new in [('"number of seats": "5"','"number of seats": "4"'),
            ('"maxPower": "99,5 kW / 135 hk"','"maxPower": "107,8 kW / 146,5 hk"'),
            ('"modelCode": "6N"','"modelCode": "9V"')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):
                extract(self.changed('specifications',old,new),self.market,self.now)

    def test_onboard_ac_peak_dc_and_braked_towing(self):
        for old,new in [('(kW) 10,5','(kW) 11'),('max kW 150 150','max kW 250 250'),
            ('bromsat släp 750 750','bromsat släp 0 0')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):
                extract(self.changed('technical',old,new,2),self.market,self.now)

    def test_cash_list_matches_exact_seating_not_lease_or_four_seat(self):
        for key,old,new,page in [('price_pdf','EV2 331,900 kr','EV2 3,495 kr',0),
            ('price_pdf','2026-11-30','2025-11-30',0),
            ('specifications','"price": "459900"','"price": "463900"',None)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):
                extract(self.changed(key,old,new,page),self.market,self.now)

    def test_exact_fresh_sources_and_market_not_a_spec_source(self):
        for key,value in [('http_status',403),('content_hash','invalid'),('final_url','https://comparison.example/ev2')]:
            p=copy.deepcopy(self.p);p['technical']['source'][key]=value
            with self.subTest(key=key),self.assertRaises(RefreshError):extract(p,self.market,self.now)
        for patch in [dict(needs_mapping=True),dict(fuel_type_raw='ELHYBRID'),dict(model_raw='EV3'),dict(registrations_last_month=0)]:
            m=copy.deepcopy(self.market);m['row'].update(patch)
            with self.subTest(patch=patch),self.assertRaises(RefreshError):extract(self.p,m,self.now)
        with self.assertRaises(RefreshError):extract(self.p,self.market,self.now+timedelta(days=1))

    def test_json_is_not_executable(self):
        with self.assertRaises(ValueError):
            extract(self.changed('specifications','"number of seats": "5"','"number of seats": alert(5)'),self.market,self.now)

    def test_initial_metadata_keeps_exact_values_and_maximum_qualification(self):
        for r in extract(self.p,self.market,self.now)['drafts']:
            row=dict(brand='Kia',model='Ev2',variant_name=r['variant_name'],**r['facts'],
                price_sek=r['price_evidence']['value'],validation_status='published',
                source_quote=' | '.join(e['quote'] for e in r['field_evidence'].values()))
            route=public_variant_routes([row])[0]
            self.assertIn('upp till',route['description'])
            self.assertEqual(next(p['value'] for p in route['json_ld'][0]['additionalProperty'] if p['name']=='AC-laddning'),'10.5 kW')


if __name__=='__main__':unittest.main()
