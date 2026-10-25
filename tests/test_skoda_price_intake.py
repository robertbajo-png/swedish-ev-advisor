import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from skoda_price_intake import URL, NAMES, extract_prices
from variant_refresh import RefreshError


class SkodaPriceTests(unittest.TestCase):
    def setUp(self):
        self.text = '''Škoda Enyaq Solid Edition
Prislista 8 oktober, 2026
Räckvidd KM (WLTP – estimerad)
Selection Sportline RS
Erbjudandet är begränsat och kan inte kombineras med andra rabatter och avtal. Gäller tom 2026-12-15.
85 286 572 155 0 501 000 kr – –
85x 299 572 157 0 551 000 kr – –
85x Sportline 299 565 159 0 – 601 000 kr
RS 340 558 161 0 – – 651 000 kr
Extrautrustning 2 000 kr'''
        self.source = {'url': URL, 'final_url': URL, 'brand': 'Skoda', 'model': 'Enyaq', 'content_hash': 'a' * 64}
        self.expected = [{'variant_name': name} for name in NAMES.values()]
        self.today = date(2026, 10, 25)

    def test_prices_remain_campaigns_and_estimated_specs_are_not_imported(self):
        drafts = extract_prices(self.text, self.source, self.expected, self.today)
        self.assertEqual([row['price_sek'] for row in drafts], [501000, 551000, 601000, 651000])
        for row in drafts:
            self.assertEqual(row['price_type'], 'campaign_price')
            self.assertEqual(row['price_valid_until'], '2026-12-15')
            self.assertEqual(row['validation_status'], 'extracted')
            self.assertIsNone(row['wltp_range_km'])
            self.assertIsNone(row['battery_kwh'])
            self.assertEqual(row['source_hash'], self.source['content_hash'])

    def test_unknown_edition_expiry_duplicate_and_layout_changes_are_held(self):
        for text in [self.text.replace('Solid Edition', 'Explore Edition'),
                     self.text.replace('Gäller tom 2026-12-15', 'Gäller tom 2026-10-24'),
                     self.text + '\nGäller tom 2027-01-01',
                     self.text + '\n85 286 572 155 0 501 000 kr – –',
                     self.text.replace('501 000 kr', '501 000 / 491 000 kr'),
                     self.text.replace('0 501 000 kr – –', '0 – 501 000 kr –'),
                     self.text.replace('Selection Sportline RS', 'RS Selection Sportline'),
                     self.text.replace('Erbjudandet är begränsat', 'Ordinarie pris')]:
            with self.subTest(text=text):
                with self.assertRaises(RefreshError):
                    extract_prices(text, self.source, self.expected, self.today)

    def test_source_group_identity_and_hash_cannot_be_guessed(self):
        for patch in [{'final_url': 'https://comparison.invalid/'}, {'model': 'Elroq'}, {'content_hash': ''}]:
            with self.assertRaises(RefreshError):
                extract_prices(self.text, {**self.source, **patch}, self.expected, self.today)
        with self.assertRaises(RefreshError):
            extract_prices(self.text, self.source, self.expected[:3], self.today)
