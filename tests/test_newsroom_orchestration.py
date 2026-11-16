"""Synthetic orchestration only. Never provider calls or publication approval."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_newsroom as newsroom


class NewsroomTests(unittest.TestCase):
    def invoke(self, result, broad=None, **options):
        remote, collector = object(), object()
        with patch.object(newsroom.official, 'daily', return_value=result) as primary, \
                patch.object(newsroom.publisher, 'daily', return_value=broad or {}) as secondary:
            output = newsroom.run(remote, collector, **options)
        return output, primary, secondary, remote, collector

    def test_only_empty_official_selection_without_ai_uses_broad_route(self):
        result = {'status': 'no_eligible_new_source', 'published': 0, 'ai_candidates_started': 0,
                  'held_candidates': 3, 'held_reasons': {'source_fetch_timeout': 1}}
        broad = {'status': 'published', 'published': 1, 'cost_micro_usd': 123,
                 'held_candidates': 5, 'review_performed': True}
        out, primary, secondary, remote, collector = self.invoke(result, broad)
        primary.assert_called_once_with(remote, collector, 2, None)
        secondary.assert_called_once_with(remote, collector, max_candidates=2, owner_day=None)
        self.assertEqual(out['editorial_route'], 'broad_article_review')
        self.assertEqual(out['published'], 1)
        self.assertEqual(out['held_candidates'], 5)
        self.assertEqual(out['official_selection']['held_candidates'], 3)
        self.assertEqual(out['cost_micro_usd'], 123)
        self.assertTrue(out['review_performed'])

    def test_budget_accounting_daily_review_and_qualification_stops_never_fall_through(self):
        for status in ('published', 'daily_limit', 'daily_attempt_limit', 'deferred_budget',
                       'deferred_budget_or_disabled', 'failed', 'running', 'quarantined',
                       'qualification_required', 'publication_disabled', 'publisher_worker_disabled',
                       'source_changed_requires_new_review', 'candidate_stale_or_invalid'):
            with self.subTest(status=status):
                out, _, secondary, _, _ = self.invoke({'status': status, 'published': 0,
                                                       'ai_candidates_started': 0})
                secondary.assert_not_called()
                self.assertEqual(out['status'], status)

    def test_unknown_or_nonzero_attempt_count_cannot_buy_fallback(self):
        for value in (None, 1, -1, False, '0'):
            with self.subTest(value=value):
                _, _, secondary, _, _ = self.invoke({'status': 'no_eligible_new_source',
                    'published': 0, 'ai_candidates_started': value})
                secondary.assert_not_called()

    def test_unknown_or_positive_publication_count_cannot_fall_through(self):
        for value in (None, 1, False):
            _, _, secondary, _, _ = self.invoke({'status': 'no_eligible_new_source',
                'published': value, 'ai_candidates_started': 0})
            secondary.assert_not_called()

    def test_explicit_bounded_owner_attempt_limit_is_forwarded_unchanged(self):
        _, primary, secondary, remote, collector = self.invoke(
            {'status': 'no_eligible_new_source', 'published': 0, 'ai_candidates_started': 0},
            {'status': 'quarantined', 'published': 0}, max_candidates=6, owner_day='2026-11-16')
        primary.assert_called_once_with(remote, collector, 6, '2026-11-16')
        secondary.assert_called_once_with(remote, collector, max_candidates=6, owner_day='2026-11-16')

    def test_primary_exception_is_not_a_reason_to_retry_paid_work(self):
        with patch.object(newsroom.official, 'daily', side_effect=RuntimeError('unknown_usage')), \
                patch.object(newsroom.publisher, 'daily') as secondary:
            with self.assertRaisesRegex(RuntimeError, 'unknown_usage'):
                newsroom.run(object(), object())
            secondary.assert_not_called()


if __name__ == '__main__':
    unittest.main()
