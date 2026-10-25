"""Offline short-format contracts. Synthetic responses are never live approval."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from news_ai import NewsAi
from news_launch_hybrid import REVIEW_FLAGS
from news_short_articles import (RECIPE, SOURCES, LIMITS, firefly_document, make_brief, writer_call,
    precheck, review_check, reviewer_call, stage, release, pair_bound, unsupported_absence_claim)
from news_store import NewsStore, artifact_hash, stable_id
from preview_news_launch_hybrid import fixture_input

NOW = datetime(2026, 10, 23, 16, tzinfo=timezone.utc)
CONTENT = ('firefly萤火虫正式发布长续航60kWh电池，CLTC综合续航里程可达560公里。'
    '搭载该电池的firefly萤火虫售价13.68万元起，采用BaaS电池租用方案购车价7.98万元起，电池租用服务费每月599元。'
    'firefly萤火虫提供60kWh长续航与42kWh标准续航两种电池方案。'
    '长续航60kWh电池支持存量用户永久升级，依托蔚来换电体系，让用户无需更换整车也能享受长续航升级。')


def china_item():
    url = 'https://www.firefly.com.cn/news/20261023001'
    return {'id': stable_id(url), 'source_id': 'firefly-china-press', 'url': url, 'status': 'ready', 'cluster_id': None,
        'payload': {'title': 'firefly 60kWh CLTC 560km', 'publisher': 'Firefly China', 'source_kind': 'primary',
            'published_at': NOW.isoformat(), 'fetched_at': NOW.isoformat(), 'final_url': url,
            'access_status': 'accessible', 'content': CONTENT, 'content_hash': hashlib.sha256(CONTENT.encode()).hexdigest()}}


def sample_article():
    return {'title': 'Firefly presenterar större batteri för den kinesiska marknaden', 'title_fact_ids': ['f1'],
        'intro': 'Firefly presenterar ett nytt batteri på 60 kWh i Kina, med upp till 560 kilometers räckvidd enligt den kinesiska körcykeln CLTC. Räckviddsuppgiften gäller alltså CLTC, inte den europeiska WLTP-körcykeln.',
        'intro_fact_ids': ['f1'], 'paragraphs': [
            {'text': 'Tillverkaren anger ett kinesiskt frånpris på 136 800 yuan för bilen med batteriet. Beloppet avser ett köp där batteriet ingår, inte bara bilens pris utan batteri. Priset är därmed kopplat till just det upplägget och anges i den kinesiska valutan.', 'fact_ids': ['f2'], 'kind': 'reporting'},
            {'text': 'Firefly erbjuder två batterialternativ i det kinesiska beskedet: 60 kWh för längre räckvidd och standardbatteriet på 42 kWh. Nuvarande ägare ska enligt företaget kunna göra en permanent uppgradering till det större batteriet. Det ska gå att göra genom Nios batteribytessystem utan att byta själva bilen.', 'fact_ids': ['f4', 'f5'], 'kind': 'reporting'},
            {'text': 'Ett annat upplägg är BaaS, där bilen i stället köps utan att batteriet ingår i köpesumman. Då anges ett frånpris på 79 800 yuan och en separat batterihyra på 599 yuan per månad. Månadsavgiften tillkommer alltså utöver bilens pris. Upplägget gäller också det kinesiska beskedet.', 'fact_ids': ['f3'], 'kind': 'reporting'}]}


def fixture_review(article, brief):
    from news_editorial import blocks
    ok = {'supported': True, 'reason': 'Synthetic offline fixture, not a real AI review.', 'unsupported_claims': []}
    return {'brief_hash': brief['brief_hash'], 'article_hash': artifact_hash(article),
        **{flag: True for flag in REVIEW_FLAGS}, 'facts': {f['id']: copy.deepcopy(ok) for f in brief['facts']},
        'blocks': {b['id']: copy.deepcopy(ok) for b in blocks(article)}}


class ShortArticlesTests(unittest.TestCase):
    def swedish_brief(self, kind='model'):
        data = json.loads((ROOT / 'tests/fixtures/news_hybrid_launch.json').read_text(encoding='utf-8'))
        if kind == 'price':
            data['content'] = data['content'].replace('Samtliga versioner',
                'ID. Cross Life, 39 kWh-batteri, 116 hk (85 kW), 330 km räckvidd: från 389 000 kronor Samtliga versioner')
        items, _ = fixture_input(data)
        return make_brief(items[0], kind, datetime.fromisoformat(data['published_at']))

    def test_selected_model_packet_does_not_turn_omitted_prices_into_missing_prices(self):
        brief = self.swedish_brief()
        self.assertIn('359 000 kronor', brief['item']['payload']['content'])
        self.assertFalse(any(f.get('topic') == 'price' for f in brief['facts']))
        self.assertEqual(brief['selection'], {'source_coverage': 'partial',
            'omitted_topics': ['price'], 'absence_claims_supported': False})
        price = self.swedish_brief('price')
        self.assertNotIn('price', price['selection']['omitted_topics'])
        self.assertFalse(price['selection']['absence_claims_supported'])

    def test_writer_gets_independent_event_structure_without_losing_source_evidence(self):
        brief = self.swedish_brief()
        before = copy.deepcopy(brief)
        prompt = writer_call(brief)[2]
        packet = json.loads(prompt.split('\n', 1)[1])
        self.assertIn('SELECTED fact packet', prompt)
        self.assertIn('Omitted facts do not prove absence', prompt)
        self.assertEqual(packet['selection'], brief['selection'])
        facts = {f['metric']: f for f in packet['facts']}
        self.assertIn('Öppnad förhandsbeställning', facts['announcement']['statement'])
        self.assertIn('39 kWh', facts['announcement']['statement'])
        self.assertIn('skiftet mellan november och december', facts['market_launch']['statement'])
        self.assertNotIn('Volkswagen inleder nu förförsäljningen', prompt)
        self.assertEqual(brief, before)
        self.assertIn('Volkswagen inleder nu förförsäljningen', brief['facts'][0]['evidence'])

    def test_absence_paraphrases_are_not_supported_by_a_partial_packet(self):
        rejected = [
            'Något svenskt pris framgår inte av de här uppgifterna.',
            'Det svenska priset anges inte i källan.',
            'Prisuppgifter saknas i underlaget.',
            'Källan saknar svenska prisuppgifter.',
            'Tillverkaren har ännu inte angett något svenskt pris.',
            'Något svenskt pris har inte publicerats.',
            'Priset är fortfarande okänt.',
            'Inget svenskt pris finns i underlaget.',
            'Det finns inga svenska prisuppgifter.',
            'Leveransdatum har inte bekräftats.',
            'Något leveransdatum framgår inte.',
            'Svensk lansering är inte verifierad i underlaget.',
        ]
        for text in rejected:
            with self.subTest(text=text):
                self.assertTrue(unsupported_absence_claim(text))

    def test_market_scope_price_qualifiers_and_payment_conditions_are_not_absence_claims(self):
        accepted = [
            'Priserna gäller Kina, inte Sverige.',
            'Batterihyran ingår inte i bilens köppris.',
            'Beloppen är rekommenderade cirkapriser, inte slutpriser.',
            'Det rekommenderade svenska cirkapriset anges från 359 000 kronor.',
            'Lanseringen planeras vid skiftet mellan november och december.',
            'Någon vinterräckvidd beräknas inte här.',
        ]
        for text in accepted:
            with self.subTest(text=text):
                self.assertFalse(unsupported_absence_claim(text))

    def test_absence_claim_is_blocked_in_title_intro_and_each_body_block(self):
        brief = make_brief(china_item(), 'battery', NOW)
        for target in ('title', 'intro', 0, 1, 2):
            article = sample_article()
            text = ' Något svenskt pris framgår inte av de här uppgifterna.'
            if isinstance(target, int):
                article['paragraphs'][target]['text'] += text
                block = 'p' + str(target)
            else:
                article[target] += text
                block = target
            with self.subTest(block=block):
                self.assertIn('short_unsupported_absence_claim:' + block, precheck(article, brief, NOW)['errors'])

    def test_historical_rejected_intro_still_fails_originality_and_now_absence_check(self):
        brief = self.swedish_brief()
        article = sample_article()
        article['title'] = 'Volkswagen öppnar förhandsbeställning av ID. Cross'
        article['intro'] = ('Volkswagen inleder nu förförsäljningen av nya ID. Cross med ett batteri på 39 kWh. '
            'Modellen ska lanseras på den svenska marknaden vid månadsskiftet november/december. '
            'Något svenskt pris framgår inte av de här uppgifterna.')
        checked = precheck(article, brief, NOW)
        self.assertIn('short_source_overlap:intro', checked['errors'])
        self.assertIn('short_unsupported_absence_claim:intro', checked['errors'])

    def test_review_is_told_selection_is_not_evidence_for_absence(self):
        brief = make_brief(china_item(), 'battery', NOW)
        prompt = reviewer_call(sample_article(), brief)[2]
        self.assertIn('A price/date/launch omitted from it is not missing from the source', prompt)
        packet = json.loads(prompt.split('\n', 1)[1])
        self.assertEqual(packet['selection'], brief['selection'])
        self.assertTrue(all(f['evidence'] for f in packet['facts']))

    def test_unrelated_negation_cannot_hide_an_invented_swedish_launch(self):
        brief = make_brief(china_item(), 'battery', NOW)
        article = sample_article()
        article['paragraphs'][0]['text'] += ' Svensk lansering sker nu.'
        self.assertIn('ingår, inte', article['paragraphs'][0]['text'])
        self.assertIn('short_sweden_availability_invented:p0', precheck(article, brief, NOW)['errors'])

    def test_chinese_facts_preserve_wan_currency_rent_and_cltc(self):
        brief = make_brief(china_item(), 'battery', NOW)
        self.assertEqual(brief['market'], 'CN')
        statements = ' '.join(f['statement'] for f in brief['facts'])
        for value in ('136800 yuan', '79800 yuan', '599 yuan per månad', 'CLTC, inte WLTP', 'Kina'):
            self.assertIn(value, statements)
        self.assertEqual(len(brief['facts']), 5)
        self.assertTrue(all(f['evidence'] in CONTENT for f in brief['facts']))

    def test_next_document_date_is_release_metadata_not_the_fetch_date(self):
        entry = {'link': '/news/20261023001', 'title': 'Firefly battery', 'content': '<p>' + CONTENT + '</p>',
            'status': 'published', 'isDeleted': False, 'displayPublishedAt': NOW.isoformat(), 'publish_time_str': '2026-10-23'}
        def html(value):
            return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({'props': {'article': value}}) + '</script>'
        doc = firefly_document(html(entry), china_item()['url'])
        self.assertEqual(doc['published_at'], NOW.isoformat())
        del entry['displayPublishedAt']
        with self.assertRaises(ValueError):
            firefly_document(html(entry), china_item()['url'])

    def test_wrong_url_hash_date_status_and_missing_facts_rejected(self):
        for change in ('url', 'hash', 'stale', 'future', 'blocked', 'missing'):
            item = china_item()
            if change == 'url': item['url'] = item['payload']['final_url'] = 'https://comparison.example/article'
            if change == 'hash': item['payload']['content_hash'] = 'a' * 64
            if change == 'stale': item['payload']['published_at'] = (NOW - timedelta(days=8)).isoformat()
            if change == 'future': item['payload']['published_at'] = (NOW + timedelta(days=1)).isoformat()
            if change == 'blocked': item['payload']['access_status'] = 'blocked'
            if change == 'missing':
                item['payload']['content'] = CONTENT.replace('13.68万元起', '未定')
                item['payload']['content_hash'] = hashlib.sha256(item['payload']['content'].encode()).hexdigest()
            with self.subTest(change=change), self.assertRaises(ValueError):
                make_brief(item, 'battery', NOW)

    def test_vw_price_qualifiers_and_launch_meaning_reach_writer(self):
        data = json.loads((ROOT / 'tests/fixtures/news_hybrid_launch.json').read_text(encoding='utf-8'))
        data['content'] = data['content'].replace('Samtliga versioner',
            'ID. Cross Life, 39 kWh-batteri, 116 hk (85 kW), 330 km räckvidd: från 389 000 kronor Samtliga versioner')
        items, _ = fixture_input(data)
        brief = make_brief(items[0], 'price', datetime.fromisoformat(data['published_at']))
        _, _, prompt = writer_call(brief)
        self.assertIn('rekommenderat svenskt cirkapris', prompt)
        self.assertNotIn('from på', prompt)
        self.assertIn('month boundary', prompt.lower())
        self.assertNotIn('year_basis', prompt)

    def test_valid_short_reporting_does_not_require_analysis(self):
        brief = make_brief(china_item(), 'battery', NOW)
        article = sample_article()
        checked = precheck(article, brief, NOW)
        self.assertTrue(checked['passed'], checked)
        self.assertTrue(150 <= checked['word_count'] <= 250)
        self.assertEqual(review_check(fixture_review(article, brief), article, brief), [])
        schema = writer_call(brief)[1]
        self.assertEqual(schema['properties']['paragraphs']['items']['properties']['kind']['enum'], ['reporting'])

    def test_wrong_price_measurement_or_sweden_promise_fails(self):
        brief = make_brief(china_item(), 'battery', NOW)
        for change, error in [('number', 'short_unsupported_number:'), ('currency', 'short_foreign_conversion_or_measurement:'),
                              ('cltc', 'short_range_basis_lost:'), ('availability', 'short_sweden_availability_invented:'),
                              ('id', 'short_unknown_citation:')]:
            article = sample_article()
            if change == 'number': article['paragraphs'][0]['text'] = article['paragraphs'][0]['text'].replace('136 800', '13 680')
            if change == 'currency': article['paragraphs'][0]['text'] = article['paragraphs'][0]['text'].replace('yuan', 'kronor')
            if change == 'cltc': article['intro'] = article['intro'].replace('CLTC', 'WLTP')
            if change == 'availability': article['paragraphs'][0]['text'] += ' Svensk lansering sker nu.'
            if change == 'id': article['intro_fact_ids'] = ['invented']
            with self.subTest(change=change):
                self.assertTrue(any(e.startswith(error) for e in precheck(article, brief, NOW)['errors']))

    def test_review_is_bound_to_exact_article_and_every_block(self):
        brief = make_brief(china_item(), 'battery', NOW)
        article = sample_article()
        audit = fixture_review(article, brief)
        article['intro'] += ' Förändrad text.'
        self.assertIn('hybrid_review_artifact_changed', review_check(audit, article, brief))
        del audit['blocks']['p0']
        self.assertIn('hybrid_review_incomplete:blocks', review_check(audit, article, brief))

    def test_fixture_or_failed_matrix_cannot_publish(self):
        brief = make_brief(china_item(), 'battery', NOW)
        article = sample_article()
        with tempfile.TemporaryDirectory() as tmp, closing(NewsStore(Path(tmp) / 'short.sqlite')) as store:
            row = stage(store, brief, article, fixture_review(article, brief), NOW)
            self.assertEqual(store.public_articles(), [])
            self.assertTrue(all(not q['passed'] for q in store.rows('news_quality_checks')))
            with self.assertRaisesRegex(ValueError, 'mixed_format_proofs'):
                release(store, row['id'], False, NOW)
            with self.assertRaisesRegex(ValueError, 'real_writer_and_review'):
                release(store, row['id'], True, NOW)

    def test_small_output_bounds_preserve_existing_budget_contract(self):
        ai = NewsAi(client=object(), model='gpt-6-sol', output_limits=LIMITS)
        brief = make_brief(china_item(), 'battery', NOW)
        self.assertEqual(ai.payload(*writer_call(brief))['max_output_tokens'], 1700)
        self.assertGreater(pair_bound(ai, brief), 0)
        with self.assertRaises(ValueError):
            NewsAi(client=object(), output_limits={'swedish_ev_article': 9999})

    def test_remote_release_rejects_missing_real_provider_receipts(self):
        brief = make_brief(china_item(), 'battery', NOW)
        article = sample_article()
        with tempfile.TemporaryDirectory() as tmp, closing(NewsStore(Path(tmp) / 'short.sqlite')) as local:
            row = stage(local, brief, article, fixture_review(article, brief), NOW, request_ids=['writer', 'review'])
            remote = Mock(); remote.backend = 'supabase'
            remote.get.side_effect = lambda table, key: row if table == 'news_articles' else brief['item']
            remote.public_articles.return_value = []
            remote.client.select.return_value = []
            with self.assertRaisesRegex(ValueError, 'provider_receipt_missing'):
                release(remote, row['id'], True, NOW)
            remote.publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
