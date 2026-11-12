import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from kia_specs_intake import extract, SOURCES
from variant_refresh import RefreshError


def fixture(model, text):
    return {'model': model, 'source': {'status': 'reachable', 'http_status': 200,
        'final_url': SOURCES[model], 'content_hash': 'a' * 64},
        'pages': [{'page': 3, 'width': 595, 'height': 842, 'text': text}]}


EV4 = '''Teknisk specifikation
MOTOR Long Range Long Range
FWD AWD
Batterikapacitet (kWh) 81.4
Bilens laddare (On Board Charger) (kW) 10.5
DC snabbladdning max kW 128
Max räckvidd (km) enligt WLTP (Upp till) 584 550
BAGAGEUTRYMME Baksäte uppfällt / nedfällt 435 / 1450 359 / 1370
FÖRBRUKNING Blandad, kWh/100km enligt WLTP 15.8 16.5
Max släpvagnsvikt, bromsat släp 1 000 1 500'''

EV3 = '''Teknisk specifikation
(AWD, Preliminär information i väntan på homologering)
MOTOR Standard Range Long Range
58.3kWh 81.4kWh
FWD FWD/AWD
Batterikapacitet (kWh) 58.3 81.4
Bilens laddare (On Board Charger) (kW) 10.5
DC snabbladdning max kW 101 128
Max räckvidd (km) enligt WLTP (Upp till) FWD 436 (17") 605 (17") & 563 (19")
BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv (liter) FWD 460 / 1251 / 25
Max släpvagnsvikt, bromsat släp 500 1 000 / 1500'''


class KiaSpecTests(unittest.TestCase):
    def test_columns_and_boot_volume_not_mixed(self):
        fwd = extract(fixture('Ev4', EV4), 'EV4 GT Line FWD Long Range')
        awd = extract(fixture('Ev4', EV4), 'EV4 GT Line AWD Long Range')
        self.assertEqual((fwd['facts']['wltp_range_km'], awd['facts']['wltp_range_km']), (584, 550))
        self.assertEqual((fwd['facts']['boot_liters'], awd['facts']['boot_liters']), (435, 359))
        self.assertEqual(awd['facts']['tow_kg'], 1500)
        self.assertEqual(awd['facts']['dc_charge_kw'], 128)  # Not the 350 kW charging station.

    def test_different_batteries_and_standard_wheels(self):
        sr = extract(fixture('Ev3', EV3), 'EV3 FWD')
        lr = extract(fixture('Ev3', EV3), 'EV3 FWD Long Range')
        gt_line = extract(fixture('Ev3', EV3), 'EV3 GT Line FWD Long Range')
        self.assertEqual((sr['facts']['battery_kwh'], lr['facts']['battery_kwh']), (58.3, 81.4))
        self.assertEqual((lr['facts']['wltp_range_km'], gt_line['facts']['wltp_range_km']), (605, 563))
        self.assertEqual(sr['facts']['tow_kg'], 500)

    def test_unknown_gt_and_preliminary_awd_do_not_inherit_standard_specs(self):
        for name in ['EV3 GT (292hk) AWD Long Range', 'EV3 Plus AWD Long Range', 'EV3 NEW']:
            with self.assertRaises(RefreshError):
                extract(fixture('Ev3', EV3), name)

    def test_ac_decimal_is_not_silently_rounded(self):
        row = extract(fixture('Ev4', EV4), 'EV4 GT Line FWD Long Range')
        self.assertNotIn('ac_charge_kw', row['facts'])
        self.assertEqual(row['held_fields']['ac_charge_kw']['value'], 10.5)

    def test_changed_market_layout_duplicate_rows_and_preliminary_values_hold(self):
        row = fixture('Ev4', EV4)
        broken = copy.deepcopy(row)
        broken['source']['final_url'] = SOURCES['Ev4'].replace('/se/sv/', '/de/de/')
        with self.assertRaises(RefreshError):
            extract(broken, 'EV4 GT Line FWD Long Range')
        for text in [EV4.replace('FWD AWD', 'AWD FWD'), EV4 + '\nDC snabbladdning max kW 128',
                     EV4.replace('MOTOR', 'Preliminär\nMOTOR')]:
            with self.assertRaises(RefreshError):
                extract(fixture('Ev4', text), 'EV4 GT Line FWD Long Range')

    def test_every_field_has_literal_source_bound_evidence(self):
        row = extract(fixture('Ev4', EV4), 'EV4 GT Line FWD Long Range')
        self.assertNotIn('price_sek', row['facts'])
        for field, value in row['facts'].items():
            evidence = row['field_evidence'][field]
            self.assertEqual(evidence['value'], value)
            self.assertIn(evidence['quote'], EV4)
            self.assertEqual(evidence['source_hash'], 'a' * 64)
            self.assertEqual(evidence['source_url'], SOURCES['Ev4'])


if __name__ == '__main__':
    unittest.main()
