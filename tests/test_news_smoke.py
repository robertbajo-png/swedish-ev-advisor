import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_smoke_budget import TestAllowance, cost, LIMIT_MICRO


def success(_):
    return {'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 100},
            'output': [{'content': [{'type': 'output_text', 'text': '{"ok":true}'}]}]}


class NewsSmokeTests(unittest.TestCase):
    def setUp(self):
        clock = patch('news_smoke_budget.datetime')
        self.clock = clock.start()
        self.clock.now.return_value = datetime(2026, 10, 21, tzinfo=timezone.utc)
        self.addCleanup(clock.stop)

    def test_expired_pricing_never_contacts_provider(self):
        self.clock.now.return_value = datetime(2026, 10, 22, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            transport = Mock(side_effect=success)
            budget = TestAllowance(Path(directory) / 'budget.sqlite', transport)
            with self.assertRaisesRegex(RuntimeError, 'expired'): budget('test', {}, 'small')
            transport.assert_not_called()
            budget.close()

    def test_accounting_anomaly_halts_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'budget.sqlite'
            result = success(None)
            result['usage']['output_tokens'] = 4001
            budget = TestAllowance(path, lambda _: result)
            with self.assertRaisesRegex(RuntimeError, 'exceeds_reservation'): budget('test', {}, 'small')
            budget.close()
            transport = Mock(side_effect=success)
            budget = TestAllowance(path, transport)
            with self.assertRaisesRegex(RuntimeError, 'halted'): budget('test', {}, 'small')
            transport.assert_not_called()
            budget.close()

    def test_durable_count_limit_and_actual_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'budget.sqlite'
            budget = TestAllowance(path, success)
            for _ in range(6): self.assertEqual(budget('test', {}, 'small'), {'ok': True})
            self.assertEqual(budget.summary()['charged_or_reserved_micro_usd'], 6 * cost(100, 100))
            budget.close()
            budget = TestAllowance(path, success)
            with self.assertRaisesRegex(RuntimeError, 'exhausted'): budget('test', {}, 'small')
            self.assertEqual(budget.summary()['requests'], 6)
            budget.close()

    def test_provider_failure_and_unknown_usage_keep_reservations(self):
        for transport in (lambda _: (_ for _ in ()).throw(RuntimeError('network')), lambda _: {}):
            with tempfile.TemporaryDirectory() as directory:
                budget = TestAllowance(Path(directory) / 'budget.sqlite', transport)
                with self.assertRaises(RuntimeError): budget('test', {}, 'small')
                state = budget.summary()
                self.assertEqual(state['settled'], 0)
                self.assertGreater(state['charged_or_reserved_micro_usd'], 0)
                self.assertLessEqual(state['charged_or_reserved_micro_usd'], LIMIT_MICRO)
                budget.close()

    def test_shared_pending_reservations_block_overspend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'budget.sqlite'
            first = TestAllowance(path)
            second = TestAllowance(path)
            payload = {'input': 'x' * 25000}
            first.reserve('test', payload)
            second.reserve('test', payload)
            with self.assertRaisesRegex(RuntimeError, 'exhausted'): first.reserve('test', payload)
            self.assertEqual(first.summary()['requests'], 2)
            self.assertLessEqual(second.summary()['charged_or_reserved_micro_usd'], LIMIT_MICRO)
            first.close()
            second.close()

    def test_approved_followup_keeps_previous_charges_and_same_dollar_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'budget.sqlite'
            first = TestAllowance(path, success)
            for _ in range(6): first('test', {}, 'small')
            previous = first.summary()['charged_or_reserved_micro_usd']
            first.close()
            second = TestAllowance(path, success, max_calls=12, response_dir=Path(directory) / 'responses')
            second('test', {}, 'small')
            self.assertEqual(second.summary()['requests'], 7)
            self.assertEqual(second.summary()['charged_or_reserved_micro_usd'], previous + cost(100, 100))
            self.assertEqual(second.summary()['limit_micro_usd'], LIMIT_MICRO)
            self.assertEqual(len(list((Path(directory) / 'responses').glob('*.json'))), 1)
            second.close()

    def test_oversized_prompt_never_contacts_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = Mock(side_effect=success)
            budget = TestAllowance(Path(directory) / 'budget.sqlite', transport)
            with self.assertRaisesRegex(RuntimeError, 'exhausted'): budget('test', {}, 'x' * 200000)
            transport.assert_not_called()
            self.assertEqual(budget.summary()['requests'], 0)
            budget.close()

    def test_no_test_export_to_public_or_remote_store(self):
        import smoke_news_engine as smoke
        self.assertIn('data/local/', smoke.DB.as_posix())
        self.assertIn('data/local/', smoke.REPORT.as_posix())
        self.assertIn('data/local/', smoke.LEDGER.as_posix())

    def test_free_smoke_never_constructs_paid_client_or_exports_public_data(self):
        import smoke_news_engine as smoke
        from news_store import NewsStore
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'test.sqlite'
            report = Path(directory) / 'report.json'
            with patch.object(smoke, 'DB', db), patch.object(smoke, 'REPORT', report), \
                 patch.object(smoke, 'registry', return_value=[]), patch.object(smoke, 'Collector'), \
                 patch.object(smoke, 'collect', return_value={'sources': [], 'new_items': 0}), \
                 patch.object(smoke, 'TestAllowance') as paid, patch.object(smoke, 'save') as save, \
                 patch('builtins.print'), patch.object(smoke, 'NewsStore', wraps=NewsStore) as store:
                smoke.run(live=False)
                paid.assert_not_called()
                store.assert_called_once_with(db)
                save.assert_called_once()
                args = save.call_args.args
                self.assertEqual(args[0], report)
                self.assertFalse(args[1]['public_writes'])
                self.assertFalse(args[1]['scheduler_enabled'])


if __name__ == '__main__': unittest.main()
