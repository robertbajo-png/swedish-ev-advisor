import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_vehicle_quality import build_report, present


class VehicleQualityTests(unittest.TestCase):
    def test_explicit_zero_is_present_but_unknown_is_not(self):
        self.assertTrue(present(0))
        self.assertFalse(present(None))
        self.assertFalse(present(''))

    def test_variant_gaps_are_not_filled_from_another_trim(self):
        rows = [dict(brand='Kia', model='EV3', variant_name='Standard', tow_kg=500),
                dict(brand='Kia', model='EV3', variant_name='Long Range', tow_kg=None)]
        report = build_report(rows, {}, {})
        self.assertEqual(report['models'], 1)
        self.assertEqual(report['coverage']['tow_kg'], {'present': 1, 'missing': 1})
        self.assertIn('tow_kg', report['models_by_priority'][0]['variants'][1]['missing_fields'])

    def test_license_does_not_approve_photo_quality(self):
        rows = [dict(brand='Kia', model='EV3', variant_name='Standard', image_url='/old.jpg')]
        rights = {'assets': [dict(asset_url='/old.jpg', status='documented', content_sha256='a')]}
        report = build_report(rows, rights, {})
        self.assertTrue(report['models_by_priority'][0]['image_rights_documented'])
        self.assertEqual(report['professional_photos_reviewed'], 0)
        review = {'models': {'kia|ev3': dict(asset_url='/old.jpg', status='approved', content_sha256='a')}}
        self.assertEqual(build_report(rows, rights, {}, review)['professional_photos_reviewed'], 1)
        rows[0]['image_url'] = '/new.jpg'
        self.assertEqual(build_report(rows, rights, {}, review)['professional_photos_reviewed'], 0)


if __name__ == '__main__':
    unittest.main()
