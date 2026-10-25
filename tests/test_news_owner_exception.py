"""Owner exception is single-scope, fail-closed and closed even after a failure."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import trial_news_owner_exception as trial
from news_ai import NewsBudgetBlocked


class OwnerExceptionTests(unittest.TestCase):
    def test_requests_use_only_the_scoped_reservation_rpc(self):
        client = Mock()
        client._request.return_value = {'allowed': False}
        wrapper = trial.ExceptionClient(client, [])
        body = {'stage_key': 'swedish_ev_article', 'request_key': 'request'}
        with patch.object(trial.matrix, 'authorize'):
            self.assertEqual(wrapper._request('POST', 'rpc/reserve_news_ai', body), {'allowed': False})
        client._request.assert_called_once_with('POST', 'rpc/reserve_news_test_ai',
                                               {'allowance_key': trial.TRIAL_ID, **body})

    def test_settlement_cannot_touch_another_trial(self):
        client = Mock()
        client.select.return_value = []
        wrapper = trial.ExceptionClient(client, [])
        with patch.object(trial.matrix, 'authorize'):
            with self.assertRaisesRegex(NewsBudgetBlocked, 'settlement_outside_scope'):
                wrapper._request('POST', 'rpc/settle_news_ai', {'request_key': 'another-trial'})
        client._request.assert_not_called()

    def test_allowance_is_closed_after_success(self):
        remote = Mock()
        remote.client._request.return_value = {'closed': True}
        with patch.object(trial.matrix, 'run', return_value={'passed': False}):
            self.assertEqual(trial.run(remote), {'passed': False})
        remote.client._request.assert_called_once_with('POST', 'rpc/close_news_test_allowance',
                                                       {'allowance_key': trial.TRIAL_ID})

    def test_allowance_is_closed_after_failure(self):
        remote = Mock()
        remote.client._request.return_value = {'closed': True}
        with patch.object(trial.matrix, 'run', side_effect=ValueError('source changed')):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                trial.run(remote)
        remote.client._request.assert_called_once()

    def test_shutdown_failure_is_visible(self):
        remote = Mock()
        remote.client._request.return_value = {'closed': False}
        with patch.object(trial.matrix, 'run', return_value={'passed': False}):
            with self.assertRaisesRegex(NewsBudgetBlocked, 'shutdown_not_verified'):
                trial.run(remote)

    def test_production_must_stay_disabled(self):
        remote = Mock()
        remote.client.select.return_value = [{'enabled': True, 'publication_enabled': False,
            'daily_limit_micro_usd': 250000, 'monthly_limit_micro_usd': 5000000}]
        with patch.object(trial.matrix, 'authorize'):
            with self.assertRaisesRegex(NewsBudgetBlocked, 'requires_unchanged_paused_production'):
                trial.paused(remote, False)


if __name__ == '__main__':
    unittest.main()
