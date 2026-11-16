"""Offline selection accounting. No real provider, source, database or publication."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_fact_first_news as worker
from news_run_summary import summarize
from news_selection_report import collection_failure, held_candidate, selection_report
from test_news_fact_first import fixture


class SelectionReportTests(unittest.TestCase):
    def run_day(self, *, successful):
        bundle, *_ = fixture()
        item = bundle['items'][0]
        queue = []
        for index in range(4 if successful else 3):
            row = copy.deepcopy(item)
            row['id'] = 'candidate-' + str(index)
            row['url'] += '?private-token=must-not-leak-' + str(index)
            queue.append((row, {}))
        class Remote:
            def public_articles(self): return []
        with patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}), \
             patch.object(worker, 'qualification', return_value={'passed': True}), \
             patch.object(worker, 'previous_attempts', return_value=[]), \
             patch.object(worker, 'selection_queue', return_value=(queue, [])), \
             patch.object(worker, 'collect_bundle', side_effect=[TimeoutError('private source token'), bundle, bundle, bundle][:len(queue)]), \
             patch.object(worker.contract, 'readiness', side_effect=[
                 {'ready': False, 'errors': ['publisher_content_not_complete']},
                 {'ready': False, 'errors': ['fact_first_award_publicity_not_development']},
                 {'ready': True, 'errors': []}][:len(queue)-1]), \
             patch.object(worker, 'perform', return_value={'status': 'passed'}) as perform, \
             patch.object(worker, 'release', return_value={'status': 'validated_draft', 'published': 0}) as release:
            result = worker.daily(Remote(), None)
            self.assertEqual(perform.call_count, int(successful))
            self.assertEqual(release.call_count, int(successful))
        return result

    def test_three_pre_ai_stops_survive_a_later_success(self):
        result = self.run_day(successful=True)
        report = summarize(result)
        self.assertEqual(result['status'], 'validated_draft')
        self.assertEqual(report['held_candidates'], 3)
        self.assertEqual(report['held_stages'], {'collection': 1, 'evidence': 2})
        self.assertEqual(report['held_reasons'], {'source_fetch_timeout': 1,
            'publisher_content_not_complete': 1, 'fact_first_award_publicity_not_development': 1})
        self.assertEqual(report['selection_checked'], 4)
        self.assertEqual(report['ai_candidates_started'], 1)
        self.assertNotIn('private', json.dumps(result))

    def test_all_held_still_return_reasons_without_starting_ai(self):
        result = self.run_day(successful=False)
        self.assertEqual(result['status'], 'no_eligible_new_source')
        self.assertEqual(summarize(result)['held_candidates'], 3)
        self.assertEqual(result['ai_candidates_started'], 0)

    def test_bounded_details_never_truncate_the_full_counters(self):
        item = {'source_id': 'vw-press', 'payload': {'title': 'Volkswagen ID.7'}}
        held = [held_candidate(item, 'evidence', ['missing_official_evidence']) for _ in range(40)]
        result = selection_report({'status': 'no_eligible_new_source', 'published': 0}, held, checked=40)
        self.assertEqual(len(result['skipped']), 24)
        report = summarize(result)
        self.assertEqual(report['held_candidates'], 40)
        self.assertEqual(report['held_reasons'], {'missing_official_evidence': 40})
        self.assertEqual(report['held_stages'], {'evidence': 40})

    def test_source_lookup_gap_survives_without_urls_or_exception_prose(self):
        error = ValueError('publisher_no_primary_or_independent_pair:private token')
        error.discovery_trace = [{'stage': 'registry', 'status': 'no_matching_declared_authority',
                                  'url': 'https://secret.example/?key=private'}]
        item = {'source_id': 'vw-press', 'payload': {'title': 'Volkswagen ID.7'}}
        result = selection_report({'status': 'no_eligible_new_source'}, [collection_failure(item, error)])
        report = summarize(result)
        self.assertIn('missing_authority', report['source_gaps'])
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('secret.example', json.dumps(report))

    def test_malformed_aggregate_counts_cannot_inject_text_or_negative_numbers(self):
        report = summarize({'status': 'failed', 'held_reasons': {'bad token https://secret': 1, 'valid_reason': -1,
                            'another_reason': True}, 'held_stages': {'private data': 1, 'collection': -3}})
        self.assertEqual(report['held_reasons'], {'unclassified': 1})
        self.assertEqual(report['held_stages'], {})

    def test_wrapped_timeouts_are_identified_without_exposing_arbitrary_exception_tokens(self):
        from urllib.error import URLError
        item = {'source_id': 'vw-press', 'payload': {'title': 'Volkswagen ID.7'}}
        report = collection_failure(item, URLError(TimeoutError('onlylowercasesecret')))
        self.assertEqual(report['reason'], ['source_fetch_timeout'])
        report = collection_failure(item, ValueError('onlylowercasesecret'))
        self.assertEqual(report['reason'], ['source_fetch_failed'])
        self.assertNotIn('onlylowercasesecret', json.dumps(report))


if __name__ == '__main__':
    unittest.main()
