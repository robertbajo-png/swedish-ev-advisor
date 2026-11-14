import copy
import json
import sys
import unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from kia_ev3_completion_intake import extract,engine_data,VERSIONS
from variant_refresh import RefreshError
from prerender_static_routes import public_variant_routes


class Ev3CompletionTests(unittest.TestCase):
    def test_search_metadata_preserves_preliminary_awd_and_decimal_ac(self):
        snapshot=json.loads((Path(__file__).resolve().parents[1]/'public/data/public_ev_variants.json').read_text(encoding='utf8'))
        rows=[r for r in snapshot['records'] if r['brand']=='Kia' and r['model']=='Ev3']
        self.assertEqual(len(rows),7)
        for row in rows:
            with self.subTest(variant=row['variant_name']):
                route=public_variant_routes([row])[0]
                properties=route['json_ld'][0]['additionalProperty']
                label='Preliminärt WLTP-räckviddsmål' if row['variant_name'] in ('EV3 Plus AWD Long Range','EV3 GT Line AWD Long Range') else 'WLTP-räckvidd'
                self.assertEqual(properties[0]['name'],label)
                self.assertEqual(properties[0]['value'],f"{row['wltp_range_km']} km")
                self.assertIn(label,route['description'])
                self.assertEqual(next(p['value'] for p in properties if p['name']=='AC-laddning'),'10.5 kW')

    def setUp(self):
        self.p=json.loads((Path(__file__).parent/'fixtures/kia_ev3_completion_packets.json').read_text(encoding='utf8'))
        self.now=max(datetime.fromisoformat(p['source']['fetched_at']) for p in self.p.values())

    def replace(self,key,old,new,page=None):
        p=copy.deepcopy(self.p);field='html' if page is None else 'pages'
        if page is None:
            self.assertIn(old,p[key][field]);p[key][field]=p[key][field].replace(old,new)
        else:
            self.assertIn(old,p[key][field][page]);p[key][field][page]=p[key][field][page].replace(old,new)
        return p

    def test_seven_exact_profiles_and_decimal_onboard_ac(self):
        rows=extract(self.p,self.now);self.assertEqual(len(rows),7)
        for r,v in zip(rows,VERSIONS):
            with self.subTest(version=v[0]):
                self.assertEqual(r['variant_name'],v[0]);self.assertEqual(len(r['facts']),9)
                self.assertEqual(r['facts']['ac_charge_kw'],10.5);self.assertEqual(r['facts']['seats'],5)
                self.assertEqual(r['facts']['wltp_range_km'],v[7]);self.assertEqual(r['facts']['wltp_consumption_kwh_100km'],v[8])
                self.assertEqual(r['price_evidence']['value'],v[4]);self.assertEqual(r['model_facts'],{'body_type':'SUV'})

    def test_17_and_19_inch_ranges_are_not_shared_maxima(self):
        for old,new in [('436 (17") 605 (17") & 563 (19")','605 (17") 605 (17") & 605 (19")'),
                        ('14,9 (17") & 16,2 (19")','16,2 (17") & 14,9 (19")')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace('technical',old,new,2),self.now)

    def test_awd_qualification_is_required_not_removed(self):
        p=self.replace('technical','(AWD, Preliminär information i väntan på homologering)','Slutlig',2)
        with self.assertRaises(RefreshError):extract(p,self.now)
        rows=extract(self.p,self.now)
        for r in rows:
            if 'AWD' in r['variant_name'] and '(292hk)' not in r['variant_name']:
                self.assertIn('Preliminär',r['field_evidence']['wltp_range_km']['quote'])

    def test_gt_is_not_gt_line_or_foreign_energy(self):
        gt=extract(self.p,self.now)[-1]
        self.assertEqual((gt['facts']['wltp_range_km'],gt['facts']['wltp_consumption_kwh_100km']),(532,17.1))
        for key,old,new,page in [('gt','532 km','501 km',None),('gt','215 kW / 292 hk','195 kW / 265 hk',None),
                                 ('energy','292hk AWD LR El Euro 6ax 17,1','292hk AWD LR El Euro 6ax 18,1',0),
                                 ('gt_germany','215/292','195/265',11)]:
            with self.subTest(key=key),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_no_rounding_optional_ac_or_wrong_folded_boot(self):
        for key,old,new,page in [('technical','(kW) 10.5','(kW) 11',2),('poland','10,5 / 22 (opcja)','22',None),
                                 ('poland','413 / 1 204','1 204 / 413',None),('technical','500 1 000 / 1500','80 1 000 / 1500',2)]:
            with self.subTest(key=key),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_price_engine_and_seats_bind_exact_variant(self):
        for key,old,new,page in [('specifications','"number of seats": "5"','"number of seats": "4"',None),
                                 ('gt_specifications','9VW5YGZ7Z-DX1','9VW5YGZ7Z-SX2',None),
                                 ('price_pdf','650,900 kr','20,000 kr',0),('price_pdf','2026-11-30','2026-12-30',0)]:
            with self.subTest(key=key),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_source_hash_locale_access_and_freshness(self):
        for key in self.p:
            for update in [dict(status='robots_disallowed'),dict(http_status=403),dict(content_hash=''),
                           dict(final_url=self.p[key]['source']['final_url']+'?other=1'),
                           dict(fetched_at=(self.now-timedelta(minutes=16)).isoformat())]:
                p=copy.deepcopy(self.p);p[key]['source'].update(update)
                with self.subTest(key=key,update=update),self.assertRaises(RefreshError):extract(p,self.now)

    def test_static_json_is_parsed_not_executed(self):
        for html in [self.p['specifications']['html'].replace('"modelName": "EV3"','"modelName": "EV3", "modelName": "EV9"'),
                     self.p['specifications']['html'].replace('eut.tableDatas["4"] = {','eut.tableDatas["4"] = (()=>({')]:
            with self.assertRaises(ValueError):engine_data(html)


if __name__=='__main__':unittest.main()
