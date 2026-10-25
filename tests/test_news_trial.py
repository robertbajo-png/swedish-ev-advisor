import sys
import copy
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_ai import NewsBudgetBlocked
from trial_news_release import config_for_trial, revalidate_trial_evidence, refresh_trial_facts
from news_editorial import event_key
import test_news as fixtures


class PrivateNewsTrialTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'enabled': True, 'publication_enabled': False,
                    'daily_limit_micro_usd': 250000, 'monthly_limit_micro_usd': 5000000}
        self.history = [{'charged_micro_usd': 90416, 'provider_status': 'historical_settled'}]
        self.client = Mock()
        self.client.select.side_effect = lambda table, **kwargs: [self.cfg] if table == 'news_ai_config' else self.history

    def test_private_trial_requires_previous_charges_to_be_counted(self):
        self.assertEqual(config_for_trial(self.client), self.cfg)
        for historical in [[], [{'charged_micro_usd': 0, 'provider_status': 'historical_settled'}],
                           [{'charged_micro_usd': 90416, 'provider_status': 'reserved'}]]:
            self.history = historical
            with self.assertRaises(NewsBudgetBlocked): config_for_trial(self.client)

    def test_publication_enabled_or_ai_disabled_stops_trial(self):
        for flags in [(True, True), (False, False), (False, True)]:
            self.cfg.update(enabled=flags[0], publication_enabled=flags[1])
            with self.assertRaises(NewsBudgetBlocked): config_for_trial(self.client)

    def test_different_budget_cannot_silently_change_approved_test_scope(self):
        for field, value in [('daily_limit_micro_usd', 250001), ('monthly_limit_micro_usd', 5000001)]:
            original = self.cfg[field]
            self.cfg[field] = value
            with self.assertRaises(NewsBudgetBlocked): config_for_trial(self.client)
            self.cfg[field] = original

    def trial_store(self):
        store = Mock()
        store.get.return_value = {'status': 'quarantined', 'cluster_id': 'event'}
        old = fixtures.item()
        old['cluster_id'] = 'event'
        old['payload']['extraction'] = fixtures.extraction()
        store.rows.return_value = [old]
        return store, old

    def test_refetched_unchanged_evidence_can_reuse_validated_facts_without_ai(self):
        store, old = self.trial_store()
        with patch('trial_news_release.hydrate_item', return_value=(copy.deepcopy(old), [])):
            result = revalidate_trial_evidence(store, [fixtures.SOURCE], Mock())
        self.assertTrue(result[0]['source_hash_unchanged'])
        self.assertEqual(store.put.call_args.args[1]['status'], 'processed')
        store.publish.assert_not_called()

    def test_changed_source_hash_is_quarantined_instead_of_reusing_old_claims(self):
        store, old = self.trial_store()
        changed = copy.deepcopy(old)
        changed['payload']['content_hash'] = 'changed'
        with patch('trial_news_release.hydrate_item', return_value=(changed, [])):
            with self.assertRaisesRegex(ValueError, 'evidence_changed_or_invalid'):
                revalidate_trial_evidence(store, [fixtures.SOURCE], Mock())
        self.assertEqual(store.put.call_args.args[1]['status'], 'quarantined')

    def test_reused_facts_still_require_verbatim_evidence(self):
        store, old = self.trial_store()
        changed = copy.deepcopy(old)
        changed['payload']['extraction']['facts'][0]['evidence'] = 'Invented evidence nowhere in the original source document at all.'
        with patch('trial_news_release.hydrate_item', return_value=(changed, [])):
            with self.assertRaisesRegex(ValueError, 'evidence_changed_or_invalid'):
                revalidate_trial_evidence(store, [fixtures.SOURCE], Mock())
        self.assertEqual(store.put.call_args.args[1]['status'], 'quarantined')

    def refresh_store(self):
        store, item = self.trial_store()
        extraction = fixtures.extraction()
        store.get.side_effect = [{'status': 'quarantined', 'cluster_id': 'event'},
                                 {'event_key': event_key(extraction['event'])}]
        return store, item, extraction

    def test_refresh_uses_normal_extraction_and_saves_only_valid_same_event_facts(self):
        store, item, extraction = self.refresh_store()
        with patch('trial_news_release.extract_facts', return_value=extraction) as extractor, \
             patch('trial_news_release.models_for_news', return_value={}):
            result = refresh_trial_facts(store, Mock())
        extractor.assert_called_once()
        self.assertEqual(result[0]['fact_count'], len(extraction['facts']))
        saved = store.put.call_args.args[1]
        self.assertEqual(saved['payload']['extraction'], extraction)
        self.assertEqual(saved['cluster_id'], 'event')
        self.assertEqual(saved['status'], 'processed')
        store.publish.assert_not_called()

    def test_refresh_rejects_invalid_evidence_and_changed_event_without_overwriting_old_facts(self):
        for change in ['evidence', 'event']:
            store, item, extraction = self.refresh_store()
            if change == 'evidence':
                extraction['facts'][0]['evidence'] = 'Invented unsupported fact evidence not found in the source.'
            else:
                extraction['event']['action'] = 'price'
            with patch('trial_news_release.extract_facts', return_value=extraction), \
                 patch('trial_news_release.models_for_news', return_value={}):
                with self.assertRaisesRegex(ValueError, 'private_fact_refresh_invalid'):
                    refresh_trial_facts(store, Mock())
            saved = store.put.call_args.args[1]
            self.assertEqual(saved['status'], 'quarantined')
            self.assertEqual(saved['payload']['extraction'], item['payload']['extraction'])
            self.assertEqual(saved['payload']['rejected_refresh_extraction'], extraction)
            store.publish.assert_not_called()

    def test_refetched_candidate_can_resume_without_another_paid_extraction(self):
        store, item, extraction = self.refresh_store()
        bad = {**extraction['facts'][0], 'id': 'bad', 'statement': extraction['facts'][0]['statement'] + ' 999'}
        candidate = copy.deepcopy(extraction)
        candidate['facts'].append(bad)
        item['payload']['rejected_refresh_extraction'] = candidate
        with patch('trial_news_release.extract_facts') as extractor:
            result = refresh_trial_facts(store, Mock())
        extractor.assert_not_called()
        self.assertEqual(result[0]['quarantined_fact_count'], 1)
        self.assertTrue(result[0]['reused_rejected_candidate'])
        self.assertEqual(store.put.call_args.args[1]['payload']['extraction'], extraction)


if __name__ == '__main__':
    unittest.main()
