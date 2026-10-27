import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from current_variant_intake import extract_kia, extract_polestar4, extract_renault5, POLESTAR_URL, RENAULT_PARENT
from variant_refresh import RefreshError, parse_document


class CurrentVariantTests(unittest.TestCase):
    def source(self, url):
        return {'status': 'reachable', 'http_status': 200, 'final_url': url, 'content_hash': 'a' * 64,
                'fetched_at': '2026-10-27T20:00:00+00:00'}

    def test_exact_polestar_columns_ignore_range_targets(self):
        body = '<table><tr><th>Rear motor</th><th>Dual motor</th></tr><tr>'
        body += '<td><label>Pris från</label> 619 000 kr</td><td><label>Pris från</label> 649 000 kr</td></tr>'
        body += '<tr><td><label>Räckviddsmål (WLTP)</label> 620 km</td><td>590 km</td></tr></table>'
        doc = parse_document(body.encode(), 'text/html')
        rows = extract_polestar4(doc, self.source(POLESTAR_URL))[0]['profiles']
        self.assertEqual([row['price_sek'] for row in rows], [619000, 649000])
        for row in rows:
            self.assertIsNone(row['wltp_range_km'])
            self.assertIsNone(row['dc_charge_kw'])
        with self.assertRaises(RefreshError):
            extract_polestar4(doc, self.source(POLESTAR_URL.replace('coupe', 'suv')))
        with self.assertRaises(RefreshError):
            extract_polestar4(parse_document(body.replace('649 000 kr', '649 000 kr vid finansiering').encode(), 'text/html'), self.source(POLESTAR_URL))

    def test_renault_cash_columns_not_financing_bundles_or_preliminary_ranges(self):
        text = ('Renault 5 E-Tech Electric\nEVOLUTION TECHNO ICONIC FIVE\n'
            '5 E-Tech electric 40 120 311 0 14,6 AC 11 kW + DC 80 kW 364 900 kr - -\n'
            '5 E-Tech electric 52 150 407-410 0 15,1-15,2 AC 11 kW + DC 100 kW - 414 900 kr 449 900 kr\n'
            'Samtliga priser är rekommenderade cirkapriser.\nFinansiering 373252 kr\nRÄCKVIDD (PREL. DATA)')
        source = self.source('https://fixture.invalid/prices.pdf')
        source.update(discovered_from=RENAULT_PARENT, discovery_source_hash='b' * 64)
        profiles = extract_renault5(text, source)[0]['profiles']
        self.assertEqual([row['price_sek'] for row in profiles], [364900, 414900, 449900])
        self.assertTrue(all(row['wltp_range_km'] is None for row in profiles))
        with self.assertRaises(RefreshError):
            extract_renault5(text + '\n' + text, source)
        with self.assertRaises(RefreshError):
            extract_renault5(text, {**source, 'discovered_from': 'https://dealer.invalid/'})

    def test_kia_cash_row_scope_and_no_inherited_specs(self):
        from kia_price_intake import URL
        labels = ['EV3 FWD', 'EV4 GT Line FWD Long Range', 'EV5 FWD Long Range',
                  'EV5 Plus AWD Long Range', 'EV9 RWD 7-SITS', 'EV9 AWD 7-SITS Long Range']
        tables = []
        for model in ['EV3', 'EV4', 'EV5', 'EV9']:
            tables.append('<table><caption>Prislista för Kia ' + model + '</caption><tr>'
                '<th>Modell och version</th><th>Rek. cirkapris inkl. moms</th><th>Leasing</th></tr>'
                + ''.join('<tr><td>' + label + '</td><td>599 000 kr</td><td>3990 kr/mån</td></tr>'
                    for label in labels if label.startswith(model)) + '</table>')
        groups = extract_kia(parse_document(''.join(tables).encode(), 'text/html'), self.source(URL))
        self.assertEqual([len(group['profiles']) for group in groups], [1, 1, 1, 1])
        self.assertEqual(groups[2]['profiles'][0]['variant_name'], 'EV5 Plus AWD Long Range')
        self.assertTrue(all(row['battery_kwh'] is None for group in groups for row in group['profiles']))


if __name__ == '__main__':
    unittest.main()
