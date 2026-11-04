"""Synthetic operational counts and private-output redaction."""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_content_report import content_report, remote_report, safe_reason

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
DATE = NOW.isoformat()


class ContentReportTests(unittest.TestCase):
    def test_counts_real_production_not_private_trials_and_never_prose(self):
        runs = [{'payload': {'kind': 'collection', 'at': DATE, 'new_items': 5,
                              'sources': [{'errors': [{'reason': 'ValueError:robots_disallowed:https://private.example/token'}]}]}},
                {'payload': {'kind': 'short_daily', 'started_at': DATE, 'state': 'quarantined',
                             'writer_output': {'PRIVATE': 'source text'}, 'review_performed': False,
                             'errors': ['publisher_source_overlap:p1', 'PRIVATE source prose']}},
                {'payload': {'kind': 'publisher_private_trial', 'started_at': DATE, 'state': 'passed'}},
                {'payload': {'kind': 'short_daily', 'started_at': '2026-10-01T00:00:00Z', 'state': 'passed'}}]
        report = content_report(runs, [{'published_at': DATE}, {'published_at': DATE, 'status': 'quarantined'}],
            [{'created_at': DATE, 'charged_micro_usd': 5000, 'settled_at': DATE}], now=NOW)
        self.assertEqual(report['funnel']['production_attempts'], 1)
        self.assertEqual(report['funnel']['discovered'], 5)
        self.assertEqual(report['funnel']['published'], 1)
        self.assertEqual(report['funnel']['writer_completed'], 1)
        self.assertEqual(report['cost']['charged_micro_usd'], 5000)
        for private in ('PRIVATE', 'source text', 'private.example', 'token'):
            self.assertNotIn(private, json.dumps(report))

    def test_unknown_cost_is_not_reported_as_free_or_settled(self):
        request = {'created_at': DATE, 'charged_micro_usd': None, 'settled_at': None, 'budget_closed_at': None}
        report = content_report([], [], [request], now=NOW)
        self.assertIsNone(report['cost']['charged_micro_usd'])
        self.assertFalse(report['cost']['valid'])
        request.update(charged_micro_usd=20868, budget_closed_at=DATE)
        self.assertTrue(content_report([], [], [request], now=NOW)['cost']['valid'])
        self.assertEqual(content_report([], [], [request], now=NOW)['cost']['charged_micro_usd'], 20868)

    def test_remote_report_only_projects_get_fields(self):
        class Client:
            def __init__(self): self.calls = []
            def select(self, table, columns, filters):
                self.calls.append((table, columns, filters))
                return []
        client = Client()
        report = remote_report(client, now=NOW)
        self.assertEqual(len(client.calls), 4)
        self.assertTrue(all(columns != '*' for _, columns, _ in client.calls))
        self.assertEqual((report['paid_calls'], report['database_writes'], report['publications']), (0, 0, 0))
        self.assertEqual(report['traffic']['status'], 'not_connected')

    def test_safe_reason_does_not_accept_sentences_or_credentials(self):
        self.assertEqual(safe_reason('ValueError:tdm_reserved:private'), 'tdm_reserved')
        self.assertEqual(safe_reason('A private prompt or token'), 'unclassified')

    def test_per_run_held_reasons_are_sanitized(self):
        from news_run_summary import summarize
        report = summarize({'status': 'no_eligible_new_source', 'skipped': [
            {'reason': ['publisher_primary_subject_mismatch', 'ValueError:robots_disallowed:https://private.example']},
            {'reason': 'A private source sentence'}]})
        self.assertEqual(report['held_reasons']['robots_disallowed'], 1)
        self.assertNotIn('private.example', json.dumps(report))


if __name__ == '__main__':
    unittest.main()
