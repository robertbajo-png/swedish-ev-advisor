import copy
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from kia_ev6_completion_intake import extract, engine_data, VERSIONS
from variant_refresh import RefreshError
from prerender_static_routes import public_variant_routes


class Ev6CompletionTests(unittest.TestCase):
    def setUp(self):
        self.p = json.loads((Path(__file__).parent/'fixtures/kia_ev6_completion_packets.json').read_text(encoding='utf8'))
        self.now = max(datetime.fromisoformat(p['source']['fetched_at']) for p in self.p.values())

    def replace(self, key, old, new, page=None):
        packets = copy.deepcopy(self.p)
        if page is None:
            self.assertIn(old, packets[key]['html'])
            packets[key]['html'] = packets[key]['html'].replace(old, new)
        else:
            self.assertIn(old, packets[key]['pages'][page])
            packets[key]['pages'][page] = packets[key]['pages'][page].replace(old, new)
        return packets

    def test_three_complete_exact_profiles(self):
        rows = extract(self.p, self.now)
        self.assertEqual(len(rows), 3)
        for row, version in zip(rows, VERSIONS):
            self.assertEqual(row['variant_name'], version[0])
            self.assertEqual(len(row['facts']), 9)
            self.assertEqual(row['facts']['ac_charge_kw'], 10.5)
            self.assertEqual(row['facts']['seats'], 5)
            self.assertEqual(row['facts']['wltp_range_km'], version[5])
            self.assertEqual(row['facts']['wltp_consumption_kwh_100km'], version[6])
            self.assertEqual(row['facts']['drivetrain'], version[4])
            self.assertEqual(row['price_evidence']['value'], version[3])
            self.assertEqual(row['model_facts'], {'body_type': 'Crossover'})

    def test_current_84kwh_and_standard_wheels_not_old_or_optional(self):
        for old, new, page in [('20 augusti, 2026', '20 augusti, 2024', 0),
                ('Batterikapacitet (kWh) 84', 'Batterikapacitet (kWh) 77.4', 2),
                ('upp till 546**', 'upp till 522**', 2),
                ('15,9 17,0 19" / 17,7 20"', '15,9 17,7 19" / 17,0 20"', 2),
                ('DC snabbladdning max 258kW', 'DC snabbladdning max 350kW', 2)]:
            with self.subTest(old=old), self.assertRaises(RefreshError):
                extract(self.replace('technical', old, new, page), self.now)

    def test_nested_base_trim_has_two_motors_not_label_based_rwd(self):
        self.assertEqual(len(engine_data(self.p['specifications']['html'])['trims'][1]['enginesInTrim']), 2)
        for key, old, new in [('specifications', '"modelCode":"AS"', '"modelCode":"X9"'),
                ('specifications', '"bodyTypeCode":"W5"', '"bodyTypeCode":"S6"'),
                ('specifications', '"number of seats":"5"', '"number of seats":"7"'),
                ('gt_specifications', '478 KW (650 hk)', '239 KW (325 hk)'),
                ('gt_specifications', '"powerTrainModelName":"EV6 GT"', '"powerTrainModelName":"EV6"')]:
            with self.subTest(old=old), self.assertRaises(RefreshError):
                extract(self.replace(key, old, new), self.now)

    def test_gt_power_qualifications_and_450_not_city_range(self):
        for key, old, new, page in [('gt', '650 hk/478 kW', '650 hk/448 kW', None),
                ('gt', 'upp till 450 km', 'upp till 550 km', None),
                ('gt_germany', '448/609 [478/650]', '430/585', 9),
                ('gt_germany', 'Reichweite max. (km)2 450', 'Reichweite max. (km)2 550', 10),
                ('energy', 'EV6 GT Elmotor 650hk El Euro 6ax 20,9 kWh', 'EV6 GT Elmotor 585hk El Euro 6ax 20,9 kWh', 0)]:
            with self.subTest(old=old), self.assertRaises(RefreshError):
                extract(self.replace(key, old, new, page), self.now)

    def test_gt_boot_seats_up_not_folded_or_frunk(self):
        for value in ['1.250', '20', '100']:
            with self.subTest(value=value), self.assertRaises(RefreshError):
                extract(self.replace('gt_germany', 'Sitze in Normalposition, bis Fensterhöhe, max. 480',
                    'Sitze in Normalposition, bis Fensterhöhe, max. '+value, 10), self.now)

    def test_exact_ac_and_towing_not_supply_or_ball_load(self):
        for key, old, new, page in [('technical', '(kW) 10.5', '(kW) 11', 2),
                ('technical', '750 / 1800 750 / 1800', '750 / 1005 750 / 900', 2),
                ('gt_germany', '3-phasig (AC), 10,5 kW', '3-phasig (AC), 22 kW', 9),
                ('gt', 'Dragvikt: upp till 1 800 kg', 'Dragvikt: upp till 100 kg', None)]:
            with self.subTest(old=old), self.assertRaises(RefreshError):
                extract(self.replace(key, old, new, page), self.now)

    def test_cash_prices_not_plus_lease_or_paint(self):
        for key, old, new, page in [('price_pdf', 'EV6 RWD Long Range 596,400 kr', 'EV6 RWD Long Range 631,400 kr', 1),
                ('price_pdf', 'EV6 GT (650hk) AWD Long Range 771,400 kr', 'EV6 GT (650hk) AWD Long Range 12,360 kr', 1),
                ('price_pdf', '2026-11-30', '2025-11-30', 0),
                ('specifications', '"price":"596400"', '"price":"631400"', None)]:
            with self.subTest(old=old), self.assertRaises(RefreshError):
                extract(self.replace(key, old, new, page), self.now)

    def test_sources_are_exact_fresh_and_complete(self):
        for key, value in [('http_status', 403), ('final_url', 'https://comparison.example/ev6'), ('content_hash', 'invalid')]:
            packets = copy.deepcopy(self.p)
            packets['gt']['source'][key] = value
            with self.subTest(key=key), self.assertRaises(RefreshError):
                extract(packets, self.now)
        with self.assertRaises(RefreshError):
            extract(self.p, self.now+timedelta(days=1))
        packets = copy.deepcopy(self.p)
        del packets['gt_germany']
        with self.assertRaises(RefreshError):
            extract(packets, self.now)

    def test_engine_script_is_data_not_code(self):
        with self.assertRaises(ValueError):
            extract(self.replace('gt_specifications', '"number of seats":"5"', '"number of seats":alert(5)'), self.now)

    def test_metadata_preserves_maximum_and_decimal_ac(self):
        for draft in extract(self.p, self.now):
            row = {**draft, **draft['facts'], 'price_sek': draft['price_evidence']['value'], 'price_type': 'list_price',
                'validation_status': 'published', 'source_quote': ' | '.join(e['quote'] for e in draft['field_evidence'].values())}
            route = public_variant_routes([row])[0]
            properties = route['json_ld'][0]['additionalProperty']
            self.assertIn('upp till', route['description'])
            self.assertEqual(next(p['value'] for p in properties if p['name'] == 'AC-laddning'), '10.5 kW')


if __name__ == '__main__':
    unittest.main()
