import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from toyota_bz4x_touring_review import (CAR_ID, CHARGE, ENGINE_ID, ENGINE_NAME, FIELD_ROWS, GRADE_ID, MODEL_ID,
                                     PRECISION, verify_configuration)


def fixture():
    price = {'cash': 569900, 'exclVat': 455920, 'promotions': []}
    engine = {'id': ENGINE_ID, 'name': ENGINE_NAME, 'category': {'code': 'BEV'}, 'internalFuelCode': 'ELECTRIC'}
    drive = {'name': 'Framhjulsdrift', 'internalCode': '2WD'}
    grade = {'name': 'Active Tech', 'id': GRADE_ID, 'defaultCarId': CAR_ID}
    return {
        'commonSettings': {'brand': 'toyota', 'country': 'se', 'language': 'sv', 'component': 'car-config'},
        'car': {'id': CAR_ID, 'initialized': True, 'body': {'name': 'SUV Kombi'}, 'grade': grade,
                'model': {'id': MODEL_ID, 'name': 'Nya bZ4X Touring', 'defaultCar': CAR_ID,
                          'configVersion': PRECISION, 'steering': 'L'},
                'price': price | {}, 'motorization': {'engine': engine | {}, 'wheeldrive': drive | {}}},
        'grades': {'items': [grade]},
        'carConfigMotorization': {
            'initialized': True, 'motorization': [{'carId': CAR_ID, 'price': price | {},
                'engine': engine | {'certification': 2}, 'wheeldrive': drive | {},
                'specs': [{'internalCode': 'PERCOMBINED', 'value': '591', 'unit': 'km', 'certification': 2},
                          {'internalCode': 'ECCOMBINEDWLTP', 'value': '140', 'unit': 'Wh/km', 'certification': 2}]}]},
        'specs': {
            'techSpecs': [{'data': [{'internalCode': code, 'value': value, 'unit': unit, 'name': field}
                                    for field, code, value, unit, _ in FIELD_ROWS]
                                   + [{'internalCode': 'TYRSIZE', 'value': '235/60R18', 'unit': ''}]}],
            'standardEquipment': [{'name': CHARGE, 'standard': True}],
        },
    }


class TouringReviewTests(unittest.TestCase):
    def test_uses_nine_fields_and_fwd_towing(self):
        facts = verify_configuration(fixture())
        self.assertEqual({k: v[0] for k, v in facts.items()}, dict(wltp_range_km=591,
            wltp_consumption_kwh_100km=14, battery_kwh=74.7, ac_charge_kw=11, dc_charge_kw=150,
            drivetrain='FWD', tow_kg=750, seats=5, boot_liters=669))

    def test_does_not_mix_base_bz4x_with_touring_or_other_market(self):
        packet = fixture()
        packet['car']['model']['name'] = 'Nya Toyota bZ4X'
        with self.assertRaisesRegex(ValueError, 'identity_required'):
            verify_configuration(packet)
        packet = fixture()
        packet['commonSettings']['country'] = 'no'
        with self.assertRaisesRegex(ValueError, 'swedish_scope'):
            verify_configuration(packet)

    def test_disabled_when_range_is_not_final_combined_wltp(self):
        for change in ({'certification': -1}, {'value': '837'}, {'unit': 'mi'}):
            with self.subTest(change=change):
                packet = fixture()
                packet['carConfigMotorization']['motorization'][0]['specs'][0].update(change)
                with self.assertRaisesRegex(ValueError, 'final_wltp_required'):
                    verify_configuration(packet)

    def test_rejects_prices_with_options_or_campaigns(self):
        for change in ({'cash': 583800}, {'cash': 3958}, {'promotions': [{'code': 'deal'}]}):
            with self.subTest(change=change):
                packet = fixture()
                packet['car']['price'].update(change)
                with self.assertRaisesRegex(ValueError, 'base_cash'):
                    verify_configuration(packet)

    def test_rejects_other_drivetrain_or_optional_charger(self):
        packet = fixture()
        packet['carConfigMotorization']['motorization'][0]['wheeldrive']['internalCode'] = '4WD'
        with self.assertRaisesRegex(ValueError, 'motor_or_drive_changed'):
            verify_configuration(packet)
        packet = fixture()
        packet['specs']['standardEquipment'][0]['standard'] = False
        with self.assertRaisesRegex(ValueError, 'onboard_charger_required'):
            verify_configuration(packet)


if __name__ == '__main__':
    unittest.main()
