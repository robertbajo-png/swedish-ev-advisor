import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from vehicle_redirects import redirect_routes, write_vehicle_redirects


class VehicleRedirectTests(unittest.TestCase):
    def setUp(self):
        self.registry = {'schema_version': 1, 'redirects': [{'slug': 'kia-ev3', 'brand': 'Kia', 'model': 'Ev3'}]}
        self.rows = [{'brand': 'Kia', 'model': 'Ev3', 'variant_name': 'EV3 FWD', 'validation_status': 'published'}]

    def test_same_model_catalog_not_an_assumed_successor(self):
        self.assertEqual(redirect_routes(self.registry, self.rows), [('/bilar/kia-ev3', '/bilar?brand=Kia&query=Ev3')])

    def test_reject_injection_duplicate_active_slug_or_missing_model(self):
        for entry in [{'slug': '//evil.invalid'}, {'slug': 'kia-ev3-fwd'}, {'brand': 'Other'}, {'model': '<script>'}]:
            with self.assertRaises(ValueError):
                redirect_routes({'schema_version': 1, 'redirects': [{**self.registry['redirects'][0], **entry}]}, self.rows)
        with self.assertRaises(ValueError):
            redirect_routes({**self.registry, 'redirects': self.registry['redirects'] * 2}, self.rows)

    def test_idempotent_static_redirects_and_non_js_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            dist = Path(folder)
            (dist / '_redirects').write_text('/unrelated /other 302\n')
            for _ in range(2):
                self.assertEqual(write_vehicle_redirects(dist, self.rows, self.registry), 1)
            text = (dist / '_redirects').read_text()
            self.assertEqual(text.count('# BEGIN RETIRED VEHICLES'), 1)
            self.assertIn('/unrelated /other 302', text)
            self.assertIn('/bilar/kia-ev3/ /bilar?brand=Kia&query=Ev3 301', text)
            self.assertIn('noindex', (dist / 'bilar/kia-ev3/index.html').read_text())


if __name__ == '__main__':
    unittest.main()
