import copy,json,sys,unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from kia_ev5_completion_intake import extract,engine_data,VERSIONS
from variant_refresh import RefreshError
from prerender_static_routes import public_variant_routes

class Ev5CompletionTests(unittest.TestCase):
    def setUp(self):
        self.p=json.loads((Path(__file__).parent/'fixtures/kia_ev5_completion_packets.json').read_text(encoding='utf8'))
        self.now=max(datetime.fromisoformat(p['source']['fetched_at']) for p in self.p.values())

    def replace(self,key,old,new,page=None):
        p=copy.deepcopy(self.p)
        if page is None:
            self.assertIn(old,p[key]['html']);p[key]['html']=p[key]['html'].replace(old,new)
        else:
            self.assertIn(old,p[key]['pages'][page]);p[key]['pages'][page]=p[key]['pages'][page].replace(old,new)
        return p

    def test_all_five_complete_exact_profiles(self):
        rows=extract(self.p,self.now);self.assertEqual(len(rows),5)
        for r,v in zip(rows,VERSIONS):
            with self.subTest(variant=v[0]):
                self.assertEqual(r['variant_name'],v[0]);self.assertEqual(len(r['facts']),9)
                self.assertEqual(r['facts']['ac_charge_kw'],10.5);self.assertEqual(r['facts']['seats'],5)
                self.assertEqual(r['facts']['wltp_range_km'],v[6]);self.assertEqual(r['facts']['wltp_consumption_kwh_100km'],v[7])
                self.assertEqual(r['facts']['tow_kg'],v[8]);self.assertEqual(r['price_evidence']['value'],v[4])
                self.assertEqual(r['model_facts'],{'body_type':'SUV'})

    def test_my27_and_wheel_columns_not_generic_foreign_footer(self):
        for old,new,page in [('14 oktober 2026 (Modellår 2027)','4 november 2025',0),
            ('552km, (534km GT Line)','530km, (505km GT Line)',2),('513km, (491km GT Line)','484km, (491km GT Line)',2),
            ('16,0 (16,6 GT Line) 17,2 (18,1 GT Line)','16,9 (17,8 GT Line) 18,2 (18,1 GT Line)',2),
            ('DC snabbladdning max kW 150','DC snabbladdning max kW 350',2)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace('technical',old,new,page),self.now)

    def test_both_engine_tables_are_nested_and_exact_x9_w5(self):
        self.assertEqual(engine_data(self.p['gt_specifications']['html'],True)['engines'][0]['number of seats'],'5')
        for key,old,new in [('specifications','"bodyTypeCode":"W5"','"bodyTypeCode":"S6"'),
            ('gt_specifications','"modelCode":"X9"','"modelCode":"7Z"'),
            ('gt_specifications','225 KW (306 hk)','195 KW (265 hk)'),
            ('specifications','"number of seats":"5"','"number of seats":"7"'),
            ('gt_specifications','"powerTrainModelName":"EV5 GT"','"powerTrainModelName":"EV5"')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace(key,old,new),self.now)

    def test_panorama_has_own_price_and_documented_option_group(self):
        rows=extract(self.p,self.now);normal=rows[2];panorama=rows[3]
        self.assertEqual(normal['facts'],panorama['facts']);self.assertEqual(panorama['price_evidence']['value']-normal['price_evidence']['value'],12000)
        self.assertEqual(panorama['field_evidence']['wltp_range_km']['scope'],'swedish_my27_gt_line_panorama_option_group')
        for key,old,new,page in [('technical','Panoramaglastak - - T','Panoramaglastak - - -',1),
            ('price_pdf','EV5 GT Line Panorama AWD Long Range 670,900 kr','EV5 GT Line Panorama FWD Long Range 670,900 kr',1)]:
            with self.subTest(key=key),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_gt_does_not_borrow_regular_awd_or_city_and_folded_data(self):
        for key,old,new,page in [('gt','476 km','615 km',None),('gt','225 kW / 306 hk','195 kW / 265 hk',None),
            ('energy','18,6 kWh','17,2 kWh',0),('gt_germany','225/306','195/265',9),
            ('gt_germany','doppelten Bodens 566','doppelten Bodens 1650',10)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_standard_ac_not_optional_22_or_supply_11(self):
        for key,old,new,page in [('technical','(kW) 10.5','(kW) 11',2),
            ('poland_pdf','10.5 / 22 (z pakietem 22K)','22 (z pakietem 22K)',14),
            ('poland_pdf','217 265 306','217 265 292',14)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_dated_cash_price_not_embedded_or_lease_or_paint(self):
        for key,old,new,page in [('price_pdf','554,900 kr','553,900 kr',1),('price_pdf','700,900 kr','20,000 kr',1),
            ('price_pdf','2026-11-30','2025-11-30',0),('specifications','"price":"553900"','"price":"6495"',None)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.replace(key,old,new,page),self.now)

    def test_source_identity_and_freshness_fail_closed(self):
        for field,value in [('http_status',403),('final_url','https://comparison.example/ev5'),('content_hash','invalid')]:
            p=copy.deepcopy(self.p);p['gt']['source'][field]=value
            with self.subTest(field=field),self.assertRaises(RefreshError):extract(p,self.now)
        with self.assertRaises(RefreshError):extract(self.p,self.now+timedelta(days=1))

    def test_engine_script_is_data_not_executed_code(self):
        p=self.replace('gt_specifications','"number of seats":"5"','"number of seats":alert(5)')
        with self.assertRaises(ValueError):extract(p,self.now)

    def test_metadata_retains_maximum_and_decimal_ac(self):
        for d in extract(self.p,self.now):
            row={**d,**d['facts'],'price_sek':d['price_evidence']['value'],'price_type':'list_price','validation_status':'published',
                'source_quote':' | '.join(p['quote'] for p in d['field_evidence'].values())}
            route=public_variant_routes([row])[0];properties=route['json_ld'][0]['additionalProperty']
            self.assertEqual(properties[0]['name'],'WLTP-räckvidd, upp till');self.assertIn('upp till',route['description'])
            self.assertEqual(next(p['value'] for p in properties if p['name']=='AC-laddning'),'10.5 kW')

if __name__=='__main__':unittest.main()
