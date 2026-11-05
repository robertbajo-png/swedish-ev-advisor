import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from search_console_report import analyze, number


class SearchConsoleReportTests(unittest.TestCase):
    def report(self, rows, header=('Top pages', 'Clicks', 'Impressions', 'CTR', 'Position'), delimiter=','):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'synthetic.csv'
            with file.open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.writer(handle, delimiter=delimiter)
                writer.writerow(header)
                writer.writerows(rows)
            return analyze(file, '2026-11-05', '2026-11-11')

    def test_english_pages_report_has_real_derived_ctr_not_visits(self):
        report = self.report([['https://elbilsagenten.se/familj', 1, 100, '1%', 8]])
        self.assertTrue(report['has_search_data'])
        self.assertEqual(report['pages'][0]['ctr'], .01)
        self.assertEqual(len(report['snippet_review_candidates']), 1)
        self.assertNotIn('visitors', report)

    def test_swedish_decimal_comma_and_semicolon(self):
        report = self.report([['https://elbilsagenten.se/bilar', 2, 80, '2,5%', '7,3']],
            ('Populäraste sidorna', 'Klick', 'Exponeringar', 'CTR', 'Position'), ';')
        self.assertEqual(report['pages'][0]['average_position'], 7.3)

    def test_zero_or_empty_export_is_not_an_estimate(self):
        for rows in ([], [['https://elbilsagenten.se/', 0, 0, '0%', 0]]):
            self.assertFalse(self.report(rows)['has_search_data'])

    def test_rejects_other_sites_duplicates_and_impossible_counts(self):
        good = ['https://elbilsagenten.se/', 1, 10, '10%', 4]
        for rows in ([['https://wrong.example/', 1, 10, '10%', 4]], [good, good], [['https://elbilsagenten.se/', 11, 10, '10%', 4]]):
            with self.assertRaises(ValueError): self.report(rows)

    def test_rejects_ambiguous_and_nonfinite_numbers(self):
        for value in ('1,234.5', 'nan', 'inf', '-1'):
            with self.assertRaises(ValueError): number(value)

    def test_does_not_mistake_queries_for_pages(self):
        with self.assertRaises(ValueError): self.report([], ('Top queries', 'Clicks', 'Impressions', 'CTR', 'Position'))


if __name__ == '__main__': unittest.main()
