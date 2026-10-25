"""Offline price-format routing, exact facts and unchanged publication boundaries."""
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_notice_facts import NoticeRejected, extract_notice
from news_notice_pipeline import prepare_notice
from news_notice_validation import review_notice
from news_notices import compose_notice, NOTICE_RECIPE, NOTICE_REVIEW
from news_store import NewsStore
import preview_news_price_notice as preview
from test_news_notices import MODEL, PRICES, VW, NOW, source


class PriceNoticeTests(unittest.TestCase):
    def test_pure_preparation_reuses_the_existing_source_bound_template(self):
        item = source(MODEL + PRICES)
        before = copy.deepcopy(item)
        article, review = prepare_notice(item, VW, kind='price', now=NOW)
        self.assertEqual(article, compose_notice(extract_notice(item, VW, kind='price', now=NOW)))
        self.assertEqual(item, before)
        self.assertTrue(review['passed'], review)
        self.assertEqual(review['method'], NOTICE_REVIEW)
        self.assertEqual(article['editorial_recipe'], NOTICE_RECIPE)
        self.assertLess(review['word_count'], 150)
        self.assertIn('cirkapriser', article['intro'])
        self.assertIn('Trend med 39 kWh och 116 hk', article['intro'])
        self.assertIn('359 000 kronor', article['intro'])
        self.assertEqual(article['notice_facts']['fields']['prices']['entries'][0]['value']['from_price'], True)

    def test_single_price_is_short_without_padding_or_a_150_word_floor(self):
        prices = PRICES[:PRICES.index('ID. Cross Life')] + 'Samtliga versioner finns i konfiguratorn.'
        article, review = prepare_notice(source(MODEL + prices), VW, kind='price', now=NOW)
        self.assertTrue(review['passed'])
        self.assertLess(review['word_count'], 80)
        self.assertEqual(len(article['paragraphs']), 1)
        self.assertNotIn('analysis', json.dumps(article))

    def test_changed_price_variant_campaign_or_source_cannot_pass_review(self):
        item = source(MODEL + PRICES)
        article, _ = prepare_notice(item, VW, kind='price', now=NOW)
        for before, after in [('359 000', '199 000'), ('Trend', 'Style'), ('cirkapriser', 'kampanjpriser')]:
            candidate = copy.deepcopy(article)
            candidate['intro'] = candidate['intro'].replace(before, after)
            self.assertFalse(review_notice(candidate, item, VW, now=NOW)['passed'])
        altered = copy.deepcopy(item)
        altered['payload']['content_hash'] = '0' * 64
        with self.assertRaises(NoticeRejected):
            prepare_notice(altered, VW, kind='price', now=NOW)

    def setup_files(self, root, item=None):
        private = root / 'private'
        private.mkdir()
        for path in ('public/data/news_articles.json', 'public/sitemap.xml'):
            file = root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'unchanged public artifact')
        manifest = private / 'source.json'
        manifest.write_text(json.dumps({'brief': {'kind': 'price', 'item': item or source(MODEL + PRICES),
            'source': VW}, 'article': {'intro': 'Rejected AI text with an invented price.'},
            'review': {'no_padding': False}}), encoding='utf-8')
        return private, manifest

    def test_offline_preview_cannot_call_provider_network_remote_store_or_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private, manifest = self.setup_files(root)
            original = manifest.read_bytes()
            with patch.object(preview, 'ROOT', root), patch.object(preview, 'PRIVATE', private), \
                    patch.dict(os.environ, {'NEWS_BACKEND': 'supabase'}), \
                    patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')), \
                    patch('news_ai.NewsAi.__call__', side_effect=AssertionError('Paid AI forbidden')), \
                    patch('news_store.SupabaseRestClient', side_effect=AssertionError('Remote store forbidden')), \
                    patch.object(NewsStore, 'publish', side_effect=AssertionError('Publishing forbidden')):
                result = preview.build(manifest, private / 'preview', now=NOW)
            report = json.loads((private / 'preview/report.json').read_text(encoding='utf-8'))
            self.assertTrue(result['passed'])
            self.assertEqual((result['provider_requests'], result['collector_requests'], result['published'], result['cost_usd']), (0, 0, 0, 0))
            self.assertFalse(report['ai_audit_performed'])
            self.assertFalse(report['historical_ai_result_reused'])
            self.assertEqual(report['private_staging']['status'], 'validated_draft')
            self.assertEqual(manifest.read_bytes(), original)
            self.assertNotIn('Rejected AI text', report['article']['intro'])
            self.assertTrue(report['public_outputs_unchanged'])
            self.assertEqual((root / 'public/data/news_articles.json').read_bytes(), b'unchanged public artifact')
            self.assertEqual((root / 'public/sitemap.xml').read_bytes(), b'unchanged public artifact')
            with closing(NewsStore(private / 'preview/private.sqlite', backend='sqlite')) as store:
                self.assertEqual(store.public_articles(), [])
                self.assertTrue(all(not c['payload']['audit_performed'] for c in store.rows('news_quality_checks')))
            html = (private / 'preview/index.html').read_text(encoding='utf-8')
            self.assertIn('inte en AI-slutgranskning', html)
            self.assertIn('Inget publicerat', html)

    def test_preview_clearly_limits_rows_but_rechecks_the_complete_price_table(self):
        extra = ('ID. Cross Life, 52 kWh-batteri, 211 hk (155 kW), 450 km räckvidd: från 469 000 kronor '
                 'ID. Cross Style, 52 kWh-batteri, 211 hk (155 kW), 449 km räckvidd: från 489 000 kronor ')
        item = source(MODEL + PRICES.replace('Samtliga versioner', extra + 'Samtliga versioner'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private, manifest = self.setup_files(root, item)
            with patch.object(preview, 'ROOT', root), patch.object(preview, 'PRIVATE', private):
                result = preview.build(manifest, private / 'preview', now=NOW)
            self.assertEqual((result['source_price_rows'], result['shown_price_rows']), (5, 3))
            self.assertIn('3 av 5 prisrader', (private / 'preview/index.html').read_text(encoding='utf-8'))
        conflicting = copy.deepcopy(item)
        row = 'ID. Cross Style, 52 kWh-batteri, 211 hk (155 kW), 449 km räckvidd: från 499 000 kronor '
        conflicting['payload']['content'] = conflicting['payload']['content'].replace('Samtliga versioner', row + 'Samtliga versioner')
        conflicting['payload']['content_hash'] = hashlib.sha256(conflicting['payload']['content'].encode()).hexdigest()
        with self.assertRaisesRegex(NoticeRejected, 'conflicting_variant_prices'):
            prepare_notice(conflicting, VW, kind='price', now=NOW)

    def test_public_paths_existing_artifacts_and_wrong_story_types_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private, manifest = self.setup_files(root)
            consumed = private / 'consumed-trial'
            consumed.mkdir()
            (consumed / 'report.json').write_bytes(b'keep historical result')
            with patch.object(preview, 'ROOT', root), patch.object(preview, 'PRIVATE', private):
                with self.assertRaisesRegex(ValueError, 'remain_private'):
                    preview.build(manifest, root / 'public/preview', now=NOW)
                with self.assertRaisesRegex(FileExistsError, 'overwrite_existing'):
                    preview.build(manifest, consumed, now=NOW)
                changed = json.loads(manifest.read_text(encoding='utf-8'))
                changed['brief']['kind'] = 'battery'
                manifest.write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'price_source_snapshot'):
                    preview.build(manifest, private / 'wrong', now=NOW)
            self.assertFalse((private / 'wrong').exists())
            self.assertEqual((consumed / 'report.json').read_bytes(), b'keep historical result')

    def test_old_or_unqualified_sources_never_become_new_validated_price_notices(self):
        for item in (source(MODEL), source(MODEL + PRICES.replace('rekommenderade cirkapriser', 'kampanjpriser'))):
            with self.assertRaises(NoticeRejected):
                prepare_notice(item, VW, kind='price', now=NOW)
        old = source(MODEL + PRICES)
        old['payload']['fetched_at'] = '2026-10-20T10:00:00+00:00'
        with self.assertRaisesRegex(NoticeRejected, 'stale_or_future_fetched'):
            prepare_notice(old, VW, kind='price', now=NOW)


if __name__ == '__main__':
    unittest.main()
