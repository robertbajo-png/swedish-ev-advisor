import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mercedes_cla_specs_intake import extract, validate_capture, MODEL_URL
from variant_refresh import RefreshError
from generate_sitemap import public_variant_slug

FIXTURES=Path(__file__).parent/'fixtures'


class ClaSpecsTests(unittest.TestCase):
    def setUp(self):
        self.packet=json.loads((FIXTURES/'mercedes_cla_source_packets.json').read_text(encoding='utf-8'))
        self.now=datetime.fromisoformat(self.packet['capture']['captured_at'].replace('Z','+00:00'))

    def extract(self,p=None):
        p=p or self.packet
        return extract(p['capture'],p['offers'],p['details'],self.now)

    def test_three_complete_swedish_electric_profiles_and_distinct_price_evidence(self):
        rows=self.extract()
        self.assertEqual([r['facts']['battery_kwh'] for r in rows],[58,85,85])
        self.assertEqual([r['facts']['wltp_range_km'] for r in rows],[528,772,751])
        self.assertEqual([r['facts']['wltp_consumption_kwh_100km'] for r in rows],[12.7,12.6,13.1])
        self.assertEqual([r['facts']['dc_charge_kw'] for r in rows],[200,320,320])
        self.assertEqual([r['facts']['tow_kg'] for r in rows],[1500,1500,1800])
        self.assertEqual([r['facts']['drivetrain'] for r in rows],['RWD','RWD','AWD'])
        for r in rows:
            self.assertEqual(len(r['facts']),9)
            self.assertEqual(r['facts']['ac_charge_kw'],11)
            self.assertEqual(r['facts']['boot_liters'],405)
            self.assertEqual(r['facts']['seats'],5)
            self.assertIsNone(r['source']['http_status'])
            self.assertEqual(r['source']['retrieval_method'],'connected_browser_dom')
            self.assertNotEqual(r['price_evidence']['source_url'],MODEL_URL)
            self.assertEqual(r['price_evidence']['price_type'],'dealer_offer')
            self.assertIn('(beställningsbil)',r['replacement_variant_name'])

    def test_identity_freshness_robots_and_tdm_fail_closed(self):
        for patch in [dict(url=MODEL_URL.replace('saloon','estate')),dict(canonical='https://other.invalid/'),
                      dict(h1='CLA Shooting Brake'),dict(lang='de-DE'),dict(tdm_reservation='1'),
                      dict(retrieval_method='attributed_search_service_snapshot'),dict(http_status=200),
                      dict(robots='User-agent: *\nDisallow: /'),
                      dict(captured_at=(self.now-timedelta(minutes=16)).isoformat())]:
            with self.subTest(patch=patch),self.assertRaises((RefreshError,ValueError)):
                validate_capture({**self.packet['capture'],**patch},self.now)

    def test_column_swaps_hybrid_and_missing_values_are_held(self):
        for operation in ('header','fuel','missing','power_unit','tow_basis'):
            p=copy.deepcopy(self.packet)
            if operation=='header':p['capture']['rows'][0][1:3]=['CLA 250+','CLA 200']
            if operation=='fuel':next(r for r in p['capture']['rows'] if r[0]=='Bränsletyp')[1]='Bensin'
            if operation=='missing':p['capture']['rows'].pop()
            if operation=='power_unit':next(r for r in p['capture']['rows'] if r[0].startswith('Maximal laddeffekt AC'))[1]='6,5 h'
            if operation=='tow_basis':next(r for r in p['capture']['rows'] if r[0].startswith('Tillåten släpvagnsvikt'))[1]='750 kg'
            with self.subTest(operation=operation),self.assertRaises((RefreshError,KeyError)):
                self.extract(p)

    def test_only_same_my2027_order_offers_can_be_completed(self):
        for field,value in [('carYearmodel',2026),('carPriceSek','100000'),('carInfo','Bilen finns i lager'),
                            ('carEquipment','Laddningssystem AC 22kW')]:
            p=copy.deepcopy(self.packet)
            p['details']['19043773']['car']['bytbil'][field]=value
            with self.subTest(field=field),self.assertRaises(RefreshError):self.extract(p)

    def test_capture_hash_binds_the_actual_table_and_qualifications(self):
        rows=self.extract()
        p=copy.deepcopy(self.packet)
        next(r for r in p['capture']['rows'] if r[0]=='Tillåten taklast')[1]='1 kg'
        changed=self.extract(p)
        self.assertNotEqual(rows[0]['source']['content_hash'],changed[0]['source']['content_hash'])
        self.assertEqual(rows[0]['facts'],changed[0]['facts'])
        for r in rows:
            evidence=r['field_evidence']['tow_kg']
            self.assertIn('750 kg (',evidence['quote'])
            self.assertEqual(evidence['scope'],'maximum_braked_towing_with_required_equipment')

    def test_corrected_offer_labels_keep_the_same_indexed_detail_urls(self):
        for r in self.extract():
            self.assertEqual(public_variant_slug(r),public_variant_slug({**r,'variant_name':r['replacement_variant_name']}))


if __name__=='__main__':unittest.main()
