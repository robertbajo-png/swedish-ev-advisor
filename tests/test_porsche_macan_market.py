import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import porsche_macan_market as macan


def october():
    raw = dict(brand_raw='PORSCHE', model_raw='MACAN', fuel_type_raw='EL')
    return SimpleNamespace(**raw, normalized_brand='porsche', normalized_model='macan',
                           model_group=None, needs_mapping=False, last_seen_month='2026-10-01',
                           registrations_last_month=43, registrations_ytd=367), \
        SimpleNamespace(**raw, month='2026-10-01', market_model_key='porsche:macan:EL', registrations=43)


class MacanMarketTests(unittest.TestCase):
    def test_verifies_only_the_exact_electric_row(self):
        row, month = october()
        petrol = SimpleNamespace(**{**vars(row), 'fuel_type_raw': 'BENSIN'})
        self.assertEqual(macan.exact_row([petrol, row], [month])['registrations_last_month'], 43)
        self.assertEqual(macan.exact_row([petrol, row], [month])['source_name'], 'Mobility Sweden')
        with self.assertRaisesRegex(ValueError, 'exact_macan_bev_model'):
            macan.exact_row([petrol], [month])

    def test_rejects_ambiguous_model_or_other_report_month(self):
        for change, value in (('needs_mapping', True), ('model_group', 'MACAN/CAYENNE'), ('last_seen_month', '2026-11-01')):
            row, month = october()
            setattr(row, change, value)
            with self.assertRaisesRegex(ValueError, 'october_market_identity_changed'):
                macan.exact_row([row], [month])

    def test_rejects_duplicate_or_disagreeing_rows(self):
        row, month = october()
        with self.assertRaisesRegex(ValueError, 'exact_macan_bev_model'):
            macan.exact_row([row, row], [month])
        with self.assertRaisesRegex(ValueError, 'exact_macan_bev_month'):
            macan.exact_row([row], [month, month])
        month.registrations = 44
        with self.assertRaisesRegex(ValueError, 'monthly_stat_changed'):
            macan.exact_row([row], [month])

    def test_replay_requires_linked_workbook_and_unmodified_bytes(self):
        with tempfile.TemporaryDirectory() as path:
            book = Path(path) / 'market.xlsx'
            book.write_bytes(b'example workbook')
            sha = macan.sha(book.read_bytes())
            row, month = october()
            article = f'<a href="{macan.WORKBOOK}">October workbook</a>'.encode()
            with patch.object(macan, 'WORKBOOK_SHA', sha), patch.object(macan, 'parse_elbil_ranking', return_value=([row], [month])):
                self.assertFalse(macan.review(article, book)['publication_approved'])
                with self.assertRaisesRegex(ValueError, 'linked_exact_october_workbook'):
                    macan.review(b'<a href="/elsewhere.xlsx">October workbook</a>', book)
                book.write_bytes(b'different workbook')
                with self.assertRaisesRegex(ValueError, 'linked_exact_october_workbook'):
                    macan.review(article, book)
