import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from kia_price_intake import extract_rows, URL
from variant_refresh import parse_document, RefreshError


class KiaPricesTests(unittest.TestCase):
    def setUp(self):
        self.source = {'status': 'reachable', 'http_status': 200, 'final_url': URL,
                       'content_hash': 'a' * 64, 'fetched_at': '2026-10-27T12:00:00Z'}
        self.html = '<table><caption>Prislista för Kia EV6 med fullständiga versionsnamn</caption><tr><th>Modell och version</th><th>Rek. cirkapris inkl. moms</th><th>Privatleasing från/mån</th></tr><tr><td>EV6 AWD Long Range</td><td>631 400 kr</td><td>4 995 kr</td></tr></table>'

    def extract(self, html=None, source=None):
        return extract_rows(parse_document((html or self.html).encode(), 'text/html'), source or self.source)

    def test_cash_price_not_lease_and_full_version_bound_to_quote(self):
        row = self.extract()[0]
        self.assertEqual(row['price_sek'], 631400)
        self.assertEqual(row['price_type'], 'list_price')
        self.assertEqual(row['row_label'], 'EV6 AWD Long Range')
        self.assertIn('EV6 AWD Long Range', row['source_quote'])
        self.assertNotIn('4 995', row['source_quote'])

    def test_bad_source_incomplete_or_ambiguous_columns_fail(self):
        for patch in [{'status': 'blocked'}, {'final_url': 'https://dealer.invalid/'}, {'content_hash': ''}]:
            with self.subTest(patch=patch), self.assertRaises(RefreshError):
                self.extract(source={**self.source, **patch})
        for text in [self.html.replace('Rek. cirkapris inkl. moms', 'Kampanjpris'),
                     self.html.replace('631 400 kr', 'Från 631 400 kr'),
                     self.html.replace('631 400 kr', '-100 kr'),
                     self.html + self.html,
                     self.html.replace('<td>631', '<td colspan="2">631')]:
            with self.subTest(text=text), self.assertRaises(RefreshError):
                self.extract(text)

    def test_accessible_row_headers_are_not_extra_column_headers(self):
        row = self.extract(self.html.replace('<td>EV6 AWD Long Range</td>', '<th scope="row">EV6 AWD Long Range</th>'))[0]
        self.assertEqual(row['price_sek'], 631400)

    def test_seven_digit_cash_prices_still_have_hard_limits(self):
        self.assertEqual(self.extract(self.html.replace('631 400 kr', '1 012 900 kr'))[0]['price_sek'], 1012900)
        with self.assertRaises(RefreshError):
            self.extract(self.html.replace('631 400 kr', '3 012 900 kr'))


if __name__ == '__main__':
    unittest.main()
