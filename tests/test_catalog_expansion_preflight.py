import copy
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from plan_catalog_expansion import inventory, FIELDS


class ExpansionPreflightTests(unittest.TestCase):
    def setUp(self):
        self.market = [dict(brand_raw='KIA', model_raw='EV9', normalized_brand='kia',
            normalized_model='ev9', registrations_ytd='10', registrations_last_month='1',
            needs_mapping='False', last_seen_month='2026-10-01')]
        self.models = [dict(brand='Kia', model='Ev9', normalized_brand='kia', normalized_model='ev9')]
        self.aliases = [dict(normalized_brand='kia', normalized_model='ev9', needs_mapping='False')]
        self.row = dict(brand='Kia', model='Ev9', variant_name='EV9 RWD', validation_status='published',
            **dict.fromkeys(FIELDS, 1))
        self.row['tow_kg'] = 0

    def report(self, rows, market=None):
        return inventory(market or self.market, self.models, self.aliases, rows, date(2026, 11, 15), 1, 1)

    def test_current_public_snapshot_excludes_existing_model(self):
        result = self.report([self.row])
        self.assertEqual(result['research_candidates'], [])
        self.assertEqual(result['complete_technical_variants'], 1)

    def test_drafts_do_not_hide_new_model(self):
        result = self.report([dict(self.row, validation_status='draft')])
        self.assertEqual(result['public_variants'], 0)
        self.assertEqual(result['research_candidates'][0]['status'], 'research_only')
        self.assertFalse(result['research_candidates'][0]['publication_approved'])

    def test_stale_future_or_missing_market_month_cannot_approve(self):
        for month in ('2026-03-01', '2026-12-01', '', 'unknown'):
            market = [dict(self.market[0], last_seen_month=month)]
            self.assertEqual(self.report([], market)['research_candidates'][0]['status'], 'needs_market_refresh')

    def test_ambiguous_identity_quarantines(self):
        result = self.report([], [dict(self.market[0], needs_mapping='True')])
        self.assertEqual(result['research_candidates'], [])
        self.assertEqual(result['mapping_quarantine'][0]['reason'], 'needs_mapping')

    def test_report_is_inert_and_zero_is_not_missing(self):
        row = dict(self.row, ac_charge_kw=None)
        before = copy.deepcopy(row)
        result = self.report([row])
        self.assertEqual(result['technical_gaps'][0]['missing_fields'], ['ac_charge_kw'])
        self.assertEqual(row, before)
        self.assertEqual((result['database_writes'], result['paid_calls']), (0, 0))
        self.assertFalse(result['publication_approved'])

    def test_bounded_ranking(self):
        for start, end in ((0, 5), (5, 1), (1, 500)):
            with self.assertRaises(ValueError):
                inventory([], [], [], [], date(2026, 11, 15), start, end)


if __name__ == '__main__':
    unittest.main()
