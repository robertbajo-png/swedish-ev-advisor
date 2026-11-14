import copy
import json
import sys
import unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cupra_born_specs_intake import extract,URLS
from variant_refresh import RefreshError


class BornSpecsTests(unittest.TestCase):
    def setUp(self):
        self.p=json.loads((Path(__file__).parent/'fixtures/cupra_born_source_packets.json').read_text(encoding='utf8'))
        self.now=max(datetime.fromisoformat(v['source']['fetched_at']) for v in self.p.values())

    def test_exact_current_vz_nine_facts_and_list_price(self):
        r=extract(self.p,self.now)[0]
        self.assertEqual(r['variant_name'],'Born VZ')
        self.assertEqual(r['facts'],dict(battery_kwh=79,drivetrain='RWD',ac_charge_kw=11,wltp_range_km=631,
            dc_charge_kw=183,wltp_consumption_kwh_100km=14.2,tow_kg=0,boot_liters=385,seats=5))
        self.assertEqual(r['price_evidence']['value'],596900)
        self.assertEqual(r['price_evidence']['price_type'],'list_price')
        self.assertEqual(r['model_facts'],{'body_type':'Halvkombi'})
        self.assertEqual(r['field_evidence']['wltp_range_km']['source_url'],URLS['technical'])
        self.assertEqual(r['field_evidence']['wltp_consumption_kwh_100km']['source_url'],URLS['energy'])

    def test_old_model_year_missing_discovery_and_other_engine_rejected(self):
        for mutate in [lambda p:p['index']['links'].remove(URLS['price']),
                       lambda p:p['manuals']['content']['modelYears'][0].update(modelYear='2026'),
                       lambda p:p['manuals']['content']['manuals'][0].update(manualId='CUPRA_K1_2026_14'),
                       lambda p:p['characteristics']['tables'][0][0].__setitem__(0,'170 kW/84 kWh elmotor')]:
            p=copy.deepcopy(self.p);mutate(p)
            with self.assertRaises(RefreshError):extract(p,self.now)

    def test_net_not_gross_onboard_not_cable_and_final_not_indicative(self):
        for label,value in [('Batteriets nettokapacitet\n(kWh)','84'),('Drivning','Fram'),
                            ('Maximal AC-laddningsef-\nfekt (kW)','22')]:
            p=copy.deepcopy(self.p)
            row=next(r for r in p['characteristics']['tables'][0] if r[0]==label);row[1]=value
            with self.subTest(label=label),self.assertRaises(RefreshError):extract(p,self.now)
        for label,column,value in [('Range (km)',3,'600 - 552'),('Range (km)',3,'627 - 538'),
                                   ('LINE-UP',3,'ENDURANCE (170kW/79kWh)'),
                                   ('Charging time DC 183kW 10-80% SoC (h)',2,'0:26'),
                                   ('Charging time DC 183kW 10-80% SoC (h)',3,'0:29')]:
            p=copy.deepcopy(self.p);next(r for r in p['technical']['table'] if r[0]==label)[column]=value
            with self.subTest(label=label,column=column),self.assertRaises(RefreshError):extract(p,self.now)

    def test_zero_requires_explicit_trailer_prohibition_not_carrier_75(self):
        for content in ['Maximal vertikal belastning 75 kg','Dragvikt –','Bilen är godkänd för dragkrok.']:
            p=copy.deepcopy(self.p);p['manual']['content']=content
            with self.subTest(content=content),self.assertRaises(RefreshError):extract(p,self.now)

    def test_wrong_price_consumption_or_swapped_seating_fails(self):
        for key,old,new in [('price','596 900','5 969'),('price','modellår 2027','modellår 2026'),
                            ('energy','14,2','14,1'),('energy','grundversion','utrustning'),
                            ('model','385 L','1267 L'),('model','Säten 5','Säten 4')]:
            p=copy.deepcopy(self.p)
            if isinstance(p[key]['content'],list):p[key]['content']=[t.replace(old,new) for t in p[key]['content']]
            else:p[key]['content']=p[key]['content'].replace(old,new)
            with self.subTest(key=key),self.assertRaises(RefreshError):extract(p,self.now)

    def test_source_access_hash_locale_and_freshness_fail_closed(self):
        for key in URLS:
            for patch in [dict(status='machine_reservation'),dict(http_status=403),dict(content_hash=''),
                          dict(final_url=URLS[key]+'?other=1'),
                          dict(fetched_at=(self.now-timedelta(minutes=16)).isoformat())]:
                p=copy.deepcopy(self.p);p[key]['source'].update(patch)
                with self.subTest(key=key,patch=patch),self.assertRaises(RefreshError):extract(p,self.now)


if __name__=='__main__':unittest.main()
