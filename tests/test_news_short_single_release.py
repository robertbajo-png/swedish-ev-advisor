"""Single-article owner release preparation, using synthetic offline receipts."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import test_news_short_release_policy as fixtures
import run_short_news as worker
from news_short_articles import stage
from news_short_release import prepare_single_release, single_article_sql, RECEIPT_FIELDS
from news_store import NewsStore, TABLES, artifact_hash


class SingleArticleReleaseTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.MixedReleasePolicyTests()
        fixture.setUp()
        self.fixture = fixture
        self.tmp = tempfile.TemporaryDirectory()
        self.store = NewsStore(Path(self.tmp.name) / 'test.sqlite', backend='sqlite')
        self.store.client = fixture.remote.client
        for row in fixture.rows.values():
            row.update(request_hash='a' * 64, charged_micro_usd=1000, input_tokens=100, output_tokens=100)
        fixture.state['passed'] = True
        self.store.put('news_ingestion_runs', {'id': worker.state_id(), 'payload': fixture.state})
        case = fixture.state['cases']['battery']
        self.article = stage(self.store, case['brief'], case['article'], case['review'],
                             fixtures.NOW, request_ids=case['request_ids'])

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def prepare(self):
        return prepare_single_release(self.store, self.article['id'], fixtures.NOW)

    def test_preparation_reads_exact_draft_source_checks_and_real_shaped_receipts_only(self):
        before = {table: self.store.rows(table) for table in TABLES}
        with patch.object(self.store, 'publish') as publish, patch.object(worker, 'NewsAi') as ai:
            proof = self.prepare()
        self.assertEqual(proof['article']['id'], self.article['id'])
        self.assertEqual(len(proof['snapshot']['receipts']), 2)
        self.assertEqual(len(proof['snapshot']['checks']), 3)
        self.assertEqual(before, {table: self.store.rows(table) for table in TABLES})
        self.assertIn('request_hash', RECEIPT_FIELDS)
        self.assertNotIn('request_digest', RECEIPT_FIELDS)
        publish.assert_not_called(); ai.assert_not_called()

    def test_owner_sql_is_atomic_utc_pinned_and_never_enables_paid_ai_or_notices(self):
        sql = single_article_sql(self.prepare())
        self.assertIn("set local time zone 'UTC'", sql)
        self.assertIn('pg_advisory_xact_lock', sql)
        self.assertIn('r.id::text in', sql)
        self.assertIn('perform public.publish_news_article(', sql)
        self.assertLess(sql.index('set publication_enabled=true'), sql.index('perform public.publish_news_article('))
        self.assertLess(sql.index('perform public.publish_news_article('), sql.index('set publication_enabled=false'))
        self.assertIn('and not enabled and not publication_enabled', sql)
        self.assertIn('daily_article_limit=1', sql)
        self.assertNotIn('set enabled=true', sql)
        self.assertNotIn('update public.news_notice_release_config', sql)
        self.assertNotIn('insert into public.news_ai_requests', sql)

    def test_changed_source_or_failed_quality_gate_cannot_be_prepared(self):
        item = self.store.rows('news_items')[0]
        altered = copy.deepcopy(item)
        altered['payload']['content_hash'] = 'b' * 64
        self.store.put('news_items', altered)
        with self.assertRaisesRegex(ValueError, 'source_changed'):
            self.prepare()
        self.store.put('news_items', item)
        check = self.store.rows('news_quality_checks')[0]
        self.store.put('news_quality_checks', {**check, 'passed': False})
        with self.assertRaisesRegex(ValueError, 'exact_quality_gates'):
            self.prepare()

    def test_duplicate_or_today_publication_prevents_preparation(self):
        item = self.store.rows('news_items')[0]
        for record in ({'published_at': '2000-01-01T00:00:00+00:00', 'sources': [{'url': item['url']}]},
                       {'published_at': fixtures.NOW.isoformat(), 'sources': []}):
            with patch.object(self.store, 'public_articles', return_value=[record]), self.assertRaisesRegex(ValueError, 'already_published|daily_limit'):
                self.prepare()

    def test_price_or_quarantined_article_cannot_use_this_owner_publisher(self):
        self.store.put('news_articles', {**self.article, 'status': 'quarantined'})
        with self.assertRaisesRegex(ValueError, 'exact_draft'):
            self.prepare()
        changed = copy.deepcopy(self.article)
        changed['payload']['short_brief']['kind'] = 'price'
        self.store.put('news_articles', changed)
        with self.assertRaisesRegex(ValueError, 'wrong_format'):
            self.prepare()

    def test_receipt_change_or_rejected_format_gate_stops_preparation(self):
        self.fixture.rows['battery-review']['settled_at'] = None
        with patch.object(self.store, 'publish') as publish:
            with self.assertRaisesRegex(ValueError, 'mixed_format_proofs'):
                self.prepare()
            publish.assert_not_called()

    def test_changed_code_profile_and_invalid_public_count_stop_sql_generation(self):
        proof = self.prepare()
        altered = copy.deepcopy(proof)
        altered['gate']['payload']['code_hash'] = 'old-profile'
        with self.assertRaisesRegex(ValueError, 'preparation_changed'):
            single_article_sql(altered)
        proof['expected_public_count'] = True
        with self.assertRaisesRegex(ValueError, 'invalid_public_count'):
            single_article_sql(proof)


if __name__ == '__main__':
    unittest.main()
