import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hyundai_inster_advanced_seats as review


def fixture():
    car = {'car_id': '258182', 'car_brand': 'Hyundai', 'car_model': 'Inster', 'car_year': 2027,
           'car_version': '49kWh ADVANCED TECH-PAKET+17" PIXEL-SIENNA ORANGE - DEMO',
           'car_fuel': 'El', 'battery_size': 49, 'car_site_city': 'Danderyd',
           'car_site_id': 'a871d30547050e1000b28b42e36d438d', 'car_color': 'Orange', 'car_seats': '4',
           'car_images': [review.ASSET]}
    data = {'props': {'pageProps': {'componentProps': {'details': {'car': car}}}}}
    listing = f'<a href="{review.BRANCH}">Hedin</a><script id="__NEXT_DATA__">{json.dumps(data)}</script>'
    authority = {'id': 'C18AS26005', 'fullDealerName': 'Hyundai Danderyd',
                 'outletType': '3S', 'onlyService': False, 'website': [{'url': review.DEALER + '/'}]}
    factory = ('<title>INSTER &middot; 49kWh Advanced MY27 | Hyundai Sverige</title>'
               '<li>50:50 delat/f&auml;llbart baks&auml;te</li><li>Skjutbart baks&auml;te i l&auml;ngsled</li>')
    row = {'MATNR': review.MATERIAL, 'MODEX': 'INSTER', 'MAKTX': '49kWh Advanced MY27', 'PT_TYPE': 'EV', 'ZZEXC': 'SRM',
           'ZZINC': 'NNB', 'ZZEXX': 'Sienna Orange Metallic', 'ZZINX': 'Svart',
           'PACKAGES': [{'PK_CODE': 'PK0002', 'PK_DESC': "17'' Aluminiumf&auml;lgar"},
                        {'PK_CODE': 'PK0005', 'PK_DESC': 'Tech-paket'}]}
    frame = json.dumps([1, '5:' + json.dumps({'list': [row]})])
    index = f'<script>self.__next_f.push({frame})</script>'
    return {'listing': listing.encode(), 'authority': json.dumps(authority).encode(),
            'factory': factory.encode(), 'variants': index.encode()}


class AdvancedSeatsTests(unittest.TestCase):
    def check(self, bodies):
        photo = b'private photo test fixture'
        receipts = {'listing': {'sha256': hashlib.sha256(bodies['listing']).hexdigest()}}
        with patch.object(review, 'PHOTO_SHA', hashlib.sha256(photo).hexdigest()):
            return review.seat_proof(bodies, receipts, photo)

    def test_exact_package_and_dealer_seat_record_remain_private(self):
        evidence = self.check(fixture())
        self.assertEqual(evidence['seats']['value'], 4)
        self.assertEqual(evidence['material'], review.MATERIAL)
        self.assertTrue(evidence['must_include_tech_package'])
        self.assertFalse(evidence['publication_approved'])
        self.assertTrue(evidence['photo_visual_check']['private_only'])

    def test_reject_changed_vehicle_or_seating(self):
        for old, new in ((b'2027', b'2026'), (b'17\\"', b'15\\"'), (b'"car_seats": "4"', b'"car_seats": "5"')):
            with self.subTest(old=old):
                data = fixture()
                self.assertIn(old, data['listing'])
                data['listing'] = data['listing'].replace(old, new)
                with self.assertRaisesRegex(ValueError, 'hedin_advanced_demo_seating_or_identity_changed'):
                    self.check(data)

    def test_reject_seat_image_change_and_fixed_layout(self):
        for key, old, new, reason in (
            ('listing', review.ASSET.encode(), b'wrong-media', 'reviewed_rear_photo_not_bound'),
            ('factory', b'Skjutbart', b'Fast', 'factory_advanced_seat_layout_changed'),
            ('variants', b'Tech-paket', b'Annat paket', 'factory_material_packages_changed'),
        ):
            with self.subTest(key=key):
                data = fixture()
                data[key] = data[key].replace(old, new)
                with self.assertRaisesRegex(ValueError, reason):
                    self.check(data)


if __name__ == '__main__':
    unittest.main()
