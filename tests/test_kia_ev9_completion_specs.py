import copy
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from kia_ev9_completion_intake import extract, VERSIONS
from variant_refresh import RefreshError
from prerender_static_routes import public_variant_routes


class Ev9CompletionTests(unittest.TestCase):
    def setUp(self):
        self.p = json.loads((Path(__file__).parent/'fixtures/kia_ev9_completion_packets.json').read_text(encoding='utf8'))
        self.now = max(datetime.fromisoformat(p['source']['fetched_at']) for p in self.p.values())

    def replace(self, key, old, new, page=None):
        p = copy.deepcopy(self.p)
        target = p[key]['pages'][page] if page is not None else p[key]['html']
        self.assertIn(old, target)
        if page is None:
            p[key]['html'] = target.replace(old, new)
        else:
            p[key]['pages'][page] = target.replace(old, new)
        return p

    def test_four_complete_exact_versions(self):
        rows = extract(self.p, self.now)
        self.assertEqual(len(rows), 4)
        for row, v in zip(rows, VERSIONS):
            self.assertEqual(row['variant_name'], v[0])
            self.assertEqual(len(row['facts']), 9)
            self.assertEqual(row['facts']['seats'], v[10])
            self.assertEqual(row['facts']['wltp_range_km'], v[6])
            self.assertEqual(row['facts']['wltp_consumption_kwh_100km'], v[7])
            self.assertEqual(row['facts']['ac_charge_kw'], 10.5)
            self.assertEqual(row['facts']['boot_liters'], 333)

    def test_same_generation_wheel_scope_not_gt_or_city(self):
        for old, new in [('Motoreffekt hk 218 384', 'Motoreffekt hk 218 508'),
            ('512 (19"), 505 (21")', '563 (19"), 512 (21")'),
            ('18,7 22,2 (19") 22,8 (21")', '18,7 22,8 (19") 22,2 (21")'),
            ('Batterikapacitet (kWh) 76.1 99.8', 'Batterikapacitet (kWh) 99.8 99.8')]:
            with self.subTest(old=old), self.assertRaises(RefreshError):
                extract(self.replace('technical', old, new, 2), self.now)

    def test_exact_seating_not_engine_category_or_doors(self):
        with self.assertRaises(RefreshError):
            extract(self.replace('specifications', '"number of seats": "6"', '"number of seats": "7"'), self.now)
        with self.assertRaises(RefreshError):
            extract(self.replace('specifications', '"bodyTypeCode": "W7|W6"', '"bodyTypeCode": "W7"'), self.now)

    def test_six_seat_boot_needs_explicit_all_upright_scope(self):
        with self.assertRaises(RefreshError):
            extract(self.replace('germany', 'Der Kia EV9.', 'Der Kia EV6.', 0), self.now)
        for old, new in [('max. 333', 'max. 828'), ('7 (optional: 6)', '7'),
            ('3.190 (6-Sitzer)', '3.190 (7-Sitzer)'), ('inkl. Ablagefach im Gepäckraumboden', 'bis Dachhöhe')]:
            with self.subTest(old=old), self.assertRaises(RefreshError):
                extract(self.replace('germany', old, new, 14), self.now)

    def test_exact_ac_dc_towing_not_station_unbraked_or_licence(self):
        for old, new in [('(kW) 10.5', '(kW) 11'), ('max 210kW', 'max 250kW'),
            ('450 / 900 750 / 2 500', '450 / 750 750 / 750')]:
            with self.subTest(old=old), self.assertRaises(RefreshError):
                extract(self.replace('technical', old, new, 2), self.now)

    def test_dated_six_seat_cash_price_wins_with_alternate_retained(self):
        row = extract(self.p, self.now)[3]
        self.assertEqual(row['price_evidence']['value'], 909900)
        self.assertEqual(row['price_evidence']['alternatives'][0]['value'], 897900)
        for key, old, new, page in [('price_pdf', '909,900 kr', '897,900 kr', 1),
            ('price_pdf', '2026-11-30', '2025-11-30', 0),
            ('specifications', '"price": "897900"', '"price": "909900"', None)]:
            with self.subTest(old=old), self.assertRaises(RefreshError):
                extract(self.replace(key, old, new, page), self.now)

    def test_sources_and_freshness(self):
        for key, value in [('status', 'blocked'), ('http_status', 403), ('content_hash', 'wrong'),
                           ('final_url', 'https://comparison.example/ev9')]:
            p = copy.deepcopy(self.p)
            p['technical']['source'][key] = value
            with self.subTest(key=key), self.assertRaises(RefreshError):
                extract(p, self.now)
        with self.assertRaises(RefreshError):
            extract(self.p, self.now+timedelta(days=1))

    def test_manufacturer_script_is_data_not_executed(self):
        with self.assertRaises(ValueError):
            extract(self.replace('specifications', '"number of seats": "6"', '"number of seats": alert(6)'), self.now)

    def test_qualified_initial_metadata(self):
        for draft in extract(self.p, self.now):
            row = {**draft, **draft['facts'], 'price_sek': draft['price_evidence']['value'],
                'validation_status': 'published', 'source_quote': ' | '.join(e['quote'] for e in draft['field_evidence'].values())}
            route = public_variant_routes([row])[0]
            self.assertIn('upp till', route['description'])
            props = route['json_ld'][0]['additionalProperty']
            self.assertEqual(next(p['value'] for p in props if p['name'] == 'AC-laddning'), '10.5 kW')


if __name__ == '__main__':
    unittest.main()
