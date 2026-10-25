"""The news worker may queue official verification, never edit vehicle facts."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import news_verification_worker as worker
from news_store import NewsStore


class VerificationHandoffTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'data/news').mkdir(parents=True)
        self.store = NewsStore(self.root / 'private.sqlite')
        self.output = self.root / 'data/news/official_verification_batch.json'
        self.source = {'brand': 'Test', 'model': 'EV', 'url': 'https://manufacturer.example/ev',
                       'source_authority': 'manufacturer', 'source_validation': 'reachable_official_model_source',
                       'source_type': 'model_page', 'content_hash': 'previous-hash'}
        self.collector = Mock()
        self.collector.fetch.side_effect = lambda url, *a, **kw: (200, {}, '<article>Official source</article>', url)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def request(self, key):
        return self.store.put('news_verification_requests', {'id': key, 'article_id': 'private-test-article',
            'status': 'pending', 'payload': {'brand': 'Test', 'model': 'EV', 'model_key': 'Test|EV'}})

    def run_worker(self, limit=3, sources=None):
        with patch.object(worker, 'ROOT', self.root), patch.object(worker, 'source_rows', return_value=sources or [self.source]):
            return worker.run(self.store, limit=limit, collector=self.collector)

    def batch(self):
        return json.loads(self.output.read_text(encoding='utf-8'))

    def test_subsequent_and_empty_runs_preserve_unconsumed_handoffs(self):
        self.request('first')
        self.request('second')
        self.run_worker(limit=1)
        first = self.store.get('news_verification_requests', 'first')
        self.assertEqual(len(first['payload']['source_batch']), 1)
        self.run_worker(limit=1)
        self.assertEqual({r['news_request_id'] for r in self.batch()}, {'first', 'second'})
        self.run_worker(limit=0)
        self.assertEqual({r['news_request_id'] for r in self.batch()}, {'first', 'second'})
        self.assertEqual(self.store.rows('news_articles'), [])

    def test_missing_projection_is_rebuilt_without_another_source_fetch(self):
        self.request('first')
        self.run_worker()
        expected = self.batch()
        self.output.unlink()
        self.collector.fetch.reset_mock()
        self.run_worker()
        self.assertEqual(self.batch(), expected)
        self.collector.fetch.assert_not_called()

    def test_failed_projection_write_keeps_durable_handoff_for_recovery(self):
        self.request('first')
        with patch.object(Path, 'replace', side_effect=OSError('disk unavailable')):
            with self.assertRaisesRegex(OSError, 'disk unavailable'):
                self.run_worker()
        self.assertEqual(len(self.store.get('news_verification_requests', 'first')['payload']['source_batch']), 1)
        self.collector.fetch.reset_mock()
        self.run_worker()
        self.assertEqual(len(self.batch()), 1)
        self.collector.fetch.assert_not_called()

    def test_failed_source_is_isolated_and_dealer_is_not_used_for_official_recheck(self):
        self.request('first')
        broken = {**self.source, 'url': 'https://manufacturer.example/broken'}
        dealer = {**self.source, 'source_authority': 'authorized_dealer', 'url': 'https://dealer.example/ev'}
        def fetch(url, *args, **kwargs):
            if url.endswith('/broken'):
                raise ValueError('robots_disallowed')
            return 200, {}, 'Official source', url
        self.collector.fetch.side_effect = fetch
        report = self.run_worker(sources=[dealer, broken, self.source])
        self.assertEqual(report[0]['status'], 'exported')
        self.assertEqual([d['status'] for d in report[0]['diagnostics']], ['failed', 'checked'])
        self.assertEqual(self.batch()[0]['url'], self.source['url'])
        self.assertTrue(all(call.args[0] != dealer['url'] for call in self.collector.fetch.call_args_list))
        self.assertEqual(self.batch()[0]['extraction_status'], 'needs_preflight')

    def test_legacy_local_batch_is_not_erased_by_an_empty_run(self):
        legacy = {**self.source, 'news_request_id': 'legacy', 'extraction_status': 'needs_preflight'}
        self.output.write_text(json.dumps([legacy]), encoding='utf-8')
        self.run_worker()
        self.assertEqual(self.batch(), [legacy])
        self.collector.fetch.assert_not_called()

    def test_malformed_projection_is_not_silently_overwritten(self):
        self.output.write_text('{"not": "a batch"}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'invalid_news_verification_batch'):
            self.run_worker()
        self.assertEqual(json.loads(self.output.read_text(encoding='utf-8')), {'not': 'a batch'})


if __name__ == '__main__':
    unittest.main()
