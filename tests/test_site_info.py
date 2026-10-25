import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from site_info import info_routes, INFO_PATHS


class SiteInfoTests(unittest.TestCase):
    def test_missing_operator_is_not_invented(self):
        routes = info_routes('https://fixture.invalid', {})
        self.assertEqual([row['path'] for row in routes], INFO_PATHS)
        self.assertTrue(all('Förhandsversion' in row['body_html'] for row in routes))

    def test_contact_is_escaped_and_has_own_metadata(self):
        routes = info_routes('https://fixture.invalid', {'VITE_OPERATOR_NAME': '<script>fixture</script>', 'VITE_CONTACT_EMAIL': 'contact@fixture.invalid'})
        self.assertNotIn('<script>', routes[0]['body_html'])
        self.assertIn('&lt;script&gt;', routes[0]['body_html'])
        self.assertEqual(routes[0]['json_ld']['@type'], 'ContactPage')
        self.assertNotEqual(routes[0]['title'], routes[1]['title'])

    def test_placeholder_and_header_injection_are_rejected(self):
        for email in ['name@example.com', 'name@fixture.test', 'x\r\nBcc:a@b.se']:
            routes = info_routes('https://fixture.invalid', {'VITE_OPERATOR_NAME': 'Fixture', 'VITE_CONTACT_EMAIL': email})
            self.assertIn('Förhandsversion', routes[0]['body_html'])


if __name__ == '__main__':
    unittest.main()
