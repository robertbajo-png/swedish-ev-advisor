import copy
import hashlib
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bmw_i4_specs_intake import extract, collect, NAME, URLS
from variant_refresh import RefreshError


class BmwI4SpecsTests(unittest.TestCase):
    def setUp(self):
        self.p=json.loads((Path(__file__).parent/'fixtures/bmw_i4_source_packets.json').read_text(encoding='utf8'))
        self.now=max(datetime.fromisoformat(v['source']['fetched_at'].replace('Z','+00:00')) for v in self.p.values())

    def changed(self,key,old,new):
        p=copy.deepcopy(self.p)
        self.assertIn(old,p[key]['html'])
        p[key]['html']=p[key]['html'].replace(old,new)
        p[key]['source']['content_hash']=hashlib.sha256(p[key]['html'].encode()).hexdigest()
        return p

    def test_exact_vin_61hd_not_older_edrive40(self):
        r=extract(self.p,self.now)[0]
        self.assertEqual(r['variant_name'],NAME)
        self.assertEqual(r['facts'],dict(battery_kwh=81.3,dc_charge_kw=205,ac_charge_kw=11,tow_kg=1600,
            boot_liters=470,wltp_consumption_kwh_100km=14.9,wltp_range_km=588,seats=5,drivetrain='RWD'))
        self.assertEqual(r['price_evidence']['value'],673900)
        self.assertEqual(r['price_evidence']['price_type'],'dealer_offer')
        self.assertEqual(r['field_evidence']['wltp_range_km']['source_url'],URLS['stock'])
        self.assertEqual(r['model_facts'],{'body_type':'Coupé'})

    def test_stock_identity_and_equipment_must_match(self):
        for old,new in [('WBY61HD030FW37556','WBY21HD030FW37556'),('"modelCode": "61HD"','"modelCode": "21HD"'),
                        ('"productionYear": 2026','"productionYear": 2025'),('"code": "3AC"','"code": "3AA"'),
                        ('"code": "ZMG"','"code": "ZMF"'),('"powerHp": 340','"powerHp": 335')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.changed('stock',old,new),self.now)

    def test_cash_not_lease_model_base_or_old_price(self):
        for old,new in [('673900','675900'),('673900','650700'),('673900','0'),('2026-12-31','2027-12-31'),
                        ('#Sell','#Lease'),('schema.org/InStock','schema.org/OutOfStock'),('673 900','675 900'),
                        ('schema.org/NewCondition','schema.org/UsedCondition'),('Bilia Nacka','Other seller')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.changed('stock',old,new),self.now)

    def test_exact_stock_range_not_model_maximum(self):
        for value in ['613','600','0']:
            with self.subTest(value=value),self.assertRaises(RefreshError):extract(self.changed('stock','588',value),self.now)

    def test_wrong_type_battery_and_load_columns_rejected(self):
        for old,new in [('81,3','81,1'),('205','200'),('1 600 / 75','75 / 1 600'),('470–1 290','1 290–470'),
                        ('17,1–14,9','19,1–16,1'),('cmp-technicaldata__wrapper--show','not-active'),('61HD','41HD')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.changed('technical',old,new),self.now)

    def test_source_hash_freshness_locale_access_fail_closed(self):
        for key in self.p:
            for update in [dict(content_hash='a'*64),dict(final_url=URLS[key]+'?locale=de'),dict(http_status=403),
                           dict(status='machine_reservation'),dict(fetched_at=(self.now-timedelta(minutes=16)).isoformat())]:
                p=copy.deepcopy(self.p);p[key]['source'].update(update)
                with self.subTest(key=key,update=update),self.assertRaises(RefreshError):extract(p,self.now)

    def test_robot_denial_never_fetches_content(self):
        import tempfile
        class Done:returncode=0
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);body=b'User-agent: *\nDisallow: /\n'
            (folder/'robots_bmw.body').write_bytes(body)
            (folder/'robots_bmw.json').write_text(json.dumps(dict(final_url='https://www.bmw.se/robots.txt',
                content_hash=hashlib.sha256(body).hexdigest())))
            with patch('bmw_i4_specs_intake.subprocess.run',return_value=Done()) as run:
                with self.assertRaisesRegex(RefreshError,'robots_disallows'):collect(folder)
                self.assertEqual(run.call_count,1)


if __name__=='__main__':unittest.main()
