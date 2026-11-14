import copy
import json
import sys
import unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from kia_ev4_completion_intake import extract,engine_data,VERSIONS
from variant_refresh import RefreshError
from prerender_static_routes import public_variant_routes


class Ev4CompletionTests(unittest.TestCase):
    def setUp(self):
        self.p=json.loads((Path(__file__).parent/'fixtures/kia_ev4_completion_packets.json').read_text(encoding='utf8'))
        self.now=max(datetime.fromisoformat(p['source']['fetched_at']) for p in self.p.values())

    def replace(self,key,old,new,page=None):
        p=copy.deepcopy(self.p)
        if page is None:
            self.assertIn(old,p[key]['html']);p[key]['html']=p[key]['html'].replace(old,new)
        else:
            self.assertIn(old,p[key]['pages'][page]);p[key]['pages'][page]=p[key]['pages'][page].replace(old,new)
        return p

    def test_three_exact_complete_hatchback_profiles(self):
        rows=extract(self.p,self.now);self.assertEqual(len(rows),3)
        for r,v in zip(rows,VERSIONS):
            with self.subTest(version=v[0]):
                self.assertEqual(r['variant_name'],v[0]);self.assertEqual(len(r['facts']),9)
                self.assertEqual(r['facts']['ac_charge_kw'],10.5);self.assertEqual(r['facts']['seats'],5)
                self.assertEqual(r['facts']['wltp_range_km'],v[6]);self.assertEqual(r['facts']['wltp_consumption_kwh_100km'],v[7])
                self.assertEqual(r['price_evidence']['value'],v[4]);self.assertEqual(r['model_facts'],{'body_type':'Halvkombi'})

    def test_nested_regular_and_flat_gt_engine_identity(self):
        self.assertEqual(len(engine_data(self.p['specifications']['html'])['engines']),2)
        self.assertEqual(len(engine_data(self.p['gt_specifications']['html'],True)['engines']),1)
        for key,old,new in [('specifications','7ZS6YGZ7Z-LX1_V00','7ZS6ZHZ7Z-LX1'),
            ('specifications','"number of seats":"5"','"number of seats":"7"'),
            ('gt_specifications','215 KW (292 hk)','195 KW (265 hk)'),
            ('specifications','"powerTrainModelName":"EV4"','"powerTrainModelName":"EV3"')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace(key,old,new),self.now)

    def test_fastback_and_other_models_are_not_hatchback(self):
        for key,old,new in [('specifications','"bodyTypeCode":"S6"','"bodyTypeCode":"F6"'),
            ('gt_specifications','"modelCode":"7Z"','"modelCode":"9V"'),
            ('poland',"vehicle_name = 'ev4'","vehicle_name = 'ev3'")]:
            with self.subTest(key=key),self.assertRaises(RefreshError):extract(self.replace(key,old,new),self.now)

    def test_19inch_sweden_values_not_model_maxima(self):
        for old,new in [('19" aluminiumfälgar','17" aluminiumfälgar'),('584 550','625 560'),('15.8 16.5','14.6 16.2')]:
            page=0 if 'aluminium' in old else 2
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace('technical',old,new,page),self.now)

    def test_gt_is_not_gt_line_or_another_energy_footer(self):
        for key,old,new,page in [('gt','505 km','584 km',None),('gt','215 kW / 292 hk','195 kW / 265 hk',None),
            ('energy','17,9 kWh','18,6 kWh',0),('gt_germany','215/292','195/265',10),
            ('gt_germany','Max. DC-Ladeleistung (kW) 128','Max. DC-Ladeleistung (kW) 350',10)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_standard_ac_and_gt_boot_basis_cannot_be_substituted(self):
        for key,old,new,page in [('poland','10,5 / 22 (opcja)','22',None),('poland','>359<','>377<',None),
            ('poland','>359<','>390<',None),('technical','(kW) 10.5','(kW) 11',2),
            ('gt_germany','473 (20" Michelin)/505 (20" Pirelli)','505 (20" Michelin)/505 (20" Pirelli)',11)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_paired_table_header_and_mobile_column_guards(self):
        for old,new in [('81,4 kWh AWD GT','81,4 kWh FWD'),('eut_tb1_content tb1_user_input tb1_sticky','orphan_header')]:
            p=self.replace('poland',old,new)
            if old.startswith('eut_tb1_content'):
                # Remove the first header table inside the electrical component.
                import re
                p['poland']['html']=re.sub(r'<div class="orphan_header">.*?</table>','<div class="orphan_header">',p['poland']['html'],flags=re.S)
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(p,self.now)

    def test_prices_period_and_engine_cash_values_bind(self):
        for key,old,new,page in [('price_pdf','711,900 kr','57,840 kr',0),('price_pdf','2026-11-30','2025-11-30',0),
            ('specifications','"price":"623400"','"price":"20000"',None)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_sources_and_literal_json_fail_closed(self):
        for field,value in [('http_status',403),('final_url','https://comparison.example/ev4'),('content_hash','invalid')]:
            p=copy.deepcopy(self.p);p['gt']['source'][field]=value
            with self.subTest(field=field),self.assertRaises(RefreshError):extract(p,self.now)
        with self.assertRaises(RefreshError):extract(self.p,self.now+timedelta(days=1))
        p=self.replace('gt_specifications','"number of seats":"5"','"number of seats":alert(5)')
        with self.assertRaises(ValueError):extract(p,self.now)

    def test_public_metadata_preserves_maximum_and_decimal_ac(self):
        for draft in extract(self.p,self.now):
            row={**draft,**draft['facts'],'price_sek':draft['price_evidence']['value'],'price_type':'list_price',
                'validation_status':'published','source_quote':' | '.join(p['quote'] for p in draft['field_evidence'].values())}
            route=public_variant_routes([row])[0];properties=route['json_ld'][0]['additionalProperty']
            self.assertEqual(properties[0]['name'],'WLTP-räckvidd, upp till');self.assertIn('upp till',route['description'])
            self.assertEqual(next(p['value'] for p in properties if p['name']=='AC-laddning'),'10.5 kW')


if __name__=='__main__':unittest.main()
