"""Entirely synthetic publisher/source fixtures; never live publication evidence."""
import copy
import hashlib
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_ai import NewsAi
from news_editorial import blocks
from news_launch_hybrid import REVIEW_FLAGS
from news_publisher_sources import (PUBLISHERS, parse_publisher, item_from_document, primary_source,
                                    bundle_errors, same_sources, publisher_url, collect_bundle)
from news_publisher_articles import (precheck, brief, check_review, stage, pair_bound, LIMITS,
                                     writer_call, reviewer_call, event_duplicate, evidence_catalog,
                                     resolve_writer_output, evidence_readiness)
from news_store import NewsStore, artifact_hash
import run_publisher_news as worker

NOW = datetime(2026, 11, 1, 16, tzinfo=timezone.utc)
REPORT_URL = 'https://carnewschina.com/2026/11/01/synthetic-battery-project/'
PRIMARY_URL = 'https://cop31.tr/news-detail/synthetic-battery-project'
QUOTES = [
    'Nordic Cells plans a battery research project for electric passenger cars in Europe.',
    'The project will compare two battery designs using the same laboratory procedure.',
    'Both battery designs will be examined under controlled indoor conditions before any further development.',
    'The research programme includes charging measurements and repeated laboratory cycling during the evaluation.',
    'The company will publish a technical report after the planned evaluation has finished.',
    'An external university team will review the recorded measurements before the final report.',
]
STATEMENTS = [
    'Nordic Cells planerar ett forskningsprojekt om batterier för europeiska elbilar.',
    'Projektet ska jämföra två batterikonstruktioner med samma laboratoriemetod.',
    'Båda konstruktionerna ska undersökas inomhus under kontrollerade förhållanden före fortsatt utveckling.',
    'Forskningsprogrammet omfattar laddningsmätningar och upprepade laboratoriecykler under utvärderingen.',
    'Företaget planerar att publicera en teknisk rapport när den planerade utvärderingen är avslutad.',
    'Ett externt universitetsteam ska granska registrerade mätningar innan slutrapporten skrivs.',
]


def fixture():
    source = PUBLISHERS['carnewschina']
    body = ' '.join(QUOTES) + ' ' + ' '.join(['Synthetic laboratory background for isolated parser regression only.'] * 8)
    doc = {'title': 'Synthetic battery project', 'published_at': NOW.isoformat(), 'content': body}
    lead = item_from_document(REPORT_URL, source, doc, NOW)
    lead['payload']['summary'] = body[:200]
    primary = item_from_document(PRIMARY_URL, primary_source(PRIMARY_URL), doc, NOW)
    bundle = {'items': [lead, primary], 'provenance': [{'from_url': REPORT_URL, 'to_url': PRIMARY_URL}],
              'support_fetch_errors': []}
    bundle['bundle_hash'] = artifact_hash(bundle)
    facts = [{'id': 'f' + str(i + 1), 'statement': statement, 'central': i == 0, 'market': 'EU',
              'range_cycle': 'NOT_APPLICABLE', 'support': [{'source': 's1', 'quote': QUOTES[i]}]}
             for i, statement in enumerate(STATEMENTS)]
    article = {
        'title': 'Nordic Cells planerar batteriprojekt för elbilar i Europa', 'title_fact_ids': ['f1'],
        'intro': 'Ett planerat forskningsarbete hos Nordic Cells ska handla om batterier för eldrivna personbilar i Europa. '
                 'Företagets besked gäller ett projekt där batterierna ska undersökas i laboratorium innan arbetet går vidare.',
        'intro_fact_ids': ['f1', 'f3'],
        'paragraphs': [
            {'text': 'Upplägget bygger på en jämförelse mellan två konstruktioner. För att genomföra undersökningen ska '
                     'forskarna använda samma laboratoriemetod för båda alternativen. Testerna är planerade att ske '
                     'inomhus, med kontrollerade förhållanden under den del av arbetet som beskrivs i beskedet. '
                     'De två batterikonstruktionerna ska på det sättet jämföras inom ramen för en och samma planerade undersökning.',
             'fact_ids': ['f2', 'f3'], 'kind': 'reporting'},
            {'text': 'Laddningsmätningar ingår i forskningsprogrammet tillsammans med upprepade cykler i laboratoriet. '
                     'De registrerade mätningarna ska sedan granskas av ett externt team från ett universitet. '
                     'Den granskningen är tänkt att komma före den slutliga rapporten från undersökningen.',
             'fact_ids': ['f4', 'f6'], 'kind': 'reporting'},
            {'text': 'När den planerade utvärderingen har avslutats avser företaget att publicera en teknisk rapport. '
                     'Rapporten kommer därmed efter själva undersökningen och den externa genomgången av mätningarna, '
                     'enligt den ordning som företaget har beskrivit för sitt planerade forskningsarbete.',
             'fact_ids': ['f5', 'f6'], 'kind': 'reporting'}]}
    packet = {'extraction': {'relevant': True, 'sweden_relevance': .9, 'significance': .9,
              'category': 'batterier', 'event': {'subject': doc['title'], 'action': 'battery', 'date': '2026-11-01'},
              'facts': facts}, 'article': article}
    return bundle, packet


def accepted_review(bundle, packet):
    b = brief(bundle, packet)
    decision = {'supported': True, 'reason': 'Synthetic fixture support, not a live review.', 'unsupported_claims': []}
    return {'brief_hash': b['brief_hash'], 'article_hash': artifact_hash(packet['article']),
            **{flag: True for flag in REVIEW_FLAGS},
            'facts': {f['id']: copy.deepcopy(decision) for f in b['facts']},
            'blocks': {b['id']: copy.deepcopy(decision) for b in blocks(packet['article'])}}


def encoded_fixture(bundle, packet):
    output = copy.deepcopy(packet)
    catalog = evidence_catalog(bundle)
    for fact in output['extraction']['facts']:
        fact['support'] = [{'evidence_id': next(key for key, value in catalog.items() if value == ref)}
                           for ref in fact['support']]
    return output


class PublisherSourceTests(unittest.TestCase):
    def html(self, source='carnewschina'):
        return ('<html><head><link rel="canonical" href="' + REPORT_URL + '">'
            '<meta property="og:title" content="Synthetic article">'
            '<meta property="article:published_time" content="' + NOW.isoformat() + '"></head>'
            '<body><nav>Unrelated navigation must not become evidence.</nav><div class="' + PUBLISHERS[source]['body_class'] + '">'
            + '<p>' + ('Synthetic EV laboratory evidence text for parser isolation. ' * 22) + '</p>'
            '<a href="' + PRIMARY_URL + '">Original source</a><aside>Excluded advertisement.</aside></div>'
            '<footer>Excluded footer.</footer></body></html>')

    def test_exact_publisher_hosts_and_paths(self):
        self.assertTrue(publisher_url('carnewschina', REPORT_URL))
        self.assertTrue(publisher_url('thedriven', REPORT_URL.replace('carnewschina.com', 'thedriven.io')))
        for url in [REPORT_URL.replace('carnewschina.com', 'carnewschina.com.evil.example'),
                    REPORT_URL.replace('https:', 'http:'), REPORT_URL + '?campaign=1',
                    REPORT_URL.replace('/2026/', '/category/')]:
            self.assertFalse(publisher_url('carnewschina', url))
        self.assertIsNone(primary_source('https://cop31.tr.evil.example/news-detail/synthetic'))
        self.assertIsNone(primary_source('https://cop31.tr/'))

    def test_article_specific_body_and_source_links(self):
        result = parse_publisher(self.html(), REPORT_URL, 'carnewschina', NOW.isoformat(), NOW)
        self.assertNotIn('navigation', result['content'])
        self.assertNotIn('advertisement', result['content'])
        self.assertNotIn('footer', result['content'])
        self.assertEqual(result['links'], [PRIMARY_URL])

    def test_both_publisher_layouts(self):
        html = self.html('thedriven').replace('carnewschina.com', 'thedriven.io')
        url = REPORT_URL.replace('carnewschina.com', 'thedriven.io')
        self.assertTrue(parse_publisher(html, url, 'thedriven', now=NOW)['content'])

    def test_stale_conflicting_redirected_and_paywalled_sources_fail(self):
        for old, new in [(REPORT_URL, REPORT_URL + 'changed'), ('2026-11-01', '2026-10-01'),
                         ('article_detail__content', 'unknown-layout'),
                         ('<body>', '<body><meta itemprop="isAccessibleForFree" content="false">')]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                parse_publisher(self.html().replace(old, new), REPORT_URL, 'carnewschina', now=NOW)
        with self.assertRaisesRegex(ValueError, 'feed_date_conflict'):
            parse_publisher(self.html(), REPORT_URL, 'carnewschina', (NOW - timedelta(hours=1)).isoformat(), NOW)

    def test_no_official_support_can_prepare_attributed_single_source_without_ai(self):
        class Collector:
            def fetch(_, url, source, **kwargs):
                return 200, {}, self.html().replace(PRIMARY_URL, 'https://unapproved.example/news'), url
        captured = collect_bundle('carnewschina', REPORT_URL, Collector(), now=NOW)
        self.assertEqual(captured['evidence_basis'], 'editorial_single_source')
        self.assertEqual(len(captured['items']), 1)

    def test_changed_source_hash_and_freshness_are_detected(self):
        b, _ = fixture()
        self.assertEqual(bundle_errors(b, NOW), [])
        for key in ('content', 'content_hash', 'publisher', 'final_url'):
            changed = copy.deepcopy(b)
            changed['items'][1]['payload'][key] += 'altered'
            self.assertTrue(bundle_errors(changed, NOW))
            self.assertFalse(same_sources(b, changed) if key in ('content_hash', 'final_url') else False)
        self.assertTrue(bundle_errors(b, NOW + timedelta(days=2)))


class PublisherArticleTests(unittest.TestCase):
    def test_synthetic_packet_passes_existing_language_and_scope_guards(self):
        b, p = fixture()
        result = precheck(b, p, NOW)
        self.assertTrue(result['passed'], result)
        self.assertTrue(150 <= result['word_count'] <= 250)
        self.assertEqual(check_review(b, p, accepted_review(b, p)), [])

    def test_literal_ids_resolve_without_modifying_a_single_article_word(self):
        b, p = fixture()
        raw = encoded_fixture(b, p)
        self.assertEqual(resolve_writer_output(b, raw), p)
        self.assertEqual(raw['article'], p['article'])
        raw['extraction']['facts'][0]['support'] = [{'evidence_id': 'invented'}]
        with self.assertRaisesRegex(ValueError, 'unknown_literal_evidence_id'):
            resolve_writer_output(b, raw)

    def test_central_facts_need_real_primary_quotes(self):
        b, p = fixture()
        p['extraction']['facts'][0]['support'][0]['source'] = 's0'
        self.assertIn('publisher_central_claim_needs_primary:f1', precheck(b, p, NOW)['errors'])

    def test_missing_changed_or_nonliteral_evidence_stops_article(self):
        for change in [dict(quote='An invented quotation not in the source document at all.'), dict(source='s99')]:
            b, p = fixture()
            p['extraction']['facts'][0]['support'][0].update(change)
            self.assertFalse(precheck(b, p, NOW)['passed'])

    def test_unrelated_numbers_units_and_swedish_prices_fail(self):
        for extra, expected in [(' 9999 kWh.', 'publisher_unsupported_block_number'),
                                (' 10 GWh.', 'publisher_block_unit_changed'),
                                (' Pris från kronor.', 'publisher_foreign_price_as_swedish')]:
            b, p = fixture()
            p['article']['paragraphs'][0]['text'] += extra
            self.assertTrue(any(e.startswith(expected) for e in precheck(b, p, NOW)['errors']))

    def test_wrong_scale_missing_citations_and_filler_fail(self):
        for change in ['scale', 'citation', 'length', 'absence']:
            b, p = fixture()
            if change == 'scale': p['extraction']['significance'] = 8
            if change == 'citation': p['article']['intro_fact_ids'] = ['unknown']
            if change == 'length': p['article']['paragraphs'] = []
            if change == 'absence': p['article']['paragraphs'][0]['text'] += ' Svenskt pris saknas.'
            self.assertFalse(precheck(b, p, NOW)['passed'], change)

    def test_changed_incomplete_or_rejected_review_cannot_pass(self):
        b, p = fixture()
        for change in ['hash', 'missing', 'rejected', 'contradictory']:
            review = accepted_review(b, p)
            if change == 'hash': review['article_hash'] = 'bad'
            if change == 'missing': del review['facts']['f1']
            if change == 'rejected': review['original_expression'] = False
            if change == 'contradictory': review['blocks']['intro']['unsupported_claims'] = ['Unverified clause']
            self.assertTrue(check_review(b, p, review), change)

    def test_budget_bound_covers_maximal_packet_without_contacting_provider(self):
        b, p = fixture()
        ai = NewsAi.__new__(NewsAi)
        ai.model, ai.output_limits = 'gpt-6-sol', LIMITS
        bound = pair_bound(ai, b)
        self.assertGreater(bound, 0)
        self.assertLess(bound, 250000)
        self.assertLessEqual(worker.actual_bound(ai, writer_call(b)) + worker.actual_bound(ai, reviewer_call(b, p)), bound)

    def test_sqlite_publication_requires_exact_review_gates_and_deduplicates_event(self):
        b, p = fixture()
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'test.sqlite')) as store:
            review = accepted_review(b, p)
            row = stage(store, b, p, review, ['synthetic-writer', 'synthetic-review'], now=NOW)
            self.assertEqual(row['status'], 'draft')
            self.assertEqual(store.public_articles(), [])
            # This is a synthetic local transaction check, NOT a live source proof.
            store.publish(row['id'], daily_limit=1)
            self.assertTrue(event_duplicate(store, b, p))
            self.assertEqual(len(store.public_articles()), 1)

    def test_fixture_review_without_provider_receipts_cannot_create_public_gates(self):
        b, p = fixture()
        with tempfile.TemporaryDirectory() as folder, closing(NewsStore(Path(folder) / 'test.sqlite')) as store:
            row = stage(store, b, p, accepted_review(b, p), [], now=NOW)
            self.assertEqual(row['status'], 'quarantined')
            with self.assertRaises(ValueError): store.publish(row['id'])

    def test_article_review_requires_exact_code_and_actual_provider_outputs(self):
        b, p = fixture()
        proof = {'source_id': 'carnewschina', 'state': 'passed', 'recipe': worker.RECIPE, 'kind': 'short_daily',
                 'code_hash': worker.code_hash(), 'bundle': b, 'packet': p,
                 'review': accepted_review(b, p), 'checked_at': NOW.isoformat(), 'request_ids': ['fake-a', 'fake-b']}
        class Remote:
            def get(self, *args): return {'payload': proof}
        with patch.object(worker, 'request_evidence', return_value=None):
            self.assertIsNone(worker.reviewed_record(Remote(), proof))
        with patch.object(worker, 'request_evidence', return_value=[
                {'response_payload': {'status': 'completed', 'output': []}},
                {'response_payload': {'status': 'completed', 'output': []}}]):
            self.assertIsNone(worker.reviewed_record(Remote(), proof))


class PublisherLifecycleTests(unittest.TestCase):
    def setup_environment(self, stack, folder, *, allowance=250000, corrupt=False, unknown=False):
        b, p = fixture()
        review = accepted_review(b, p)
        class Client:
            def __init__(self): self.receipts = []
            def select(self, table, **kwargs):
                if table == 'news_ai_config':
                    return [{'enabled': True, 'publication_enabled': True, 'model': 'gpt-6-sol',
                             'daily_limit_micro_usd': 250000, 'monthly_limit_micro_usd': 5000000,
                             'daily_article_limit': 1, 'pricing_valid_until': '2099-01-01'}]
                if table == 'news_ai_requests': return self.receipts
                raise AssertionError('Unexpected remote selection')
        remote = NewsStore(Path(folder) / 'remote-fixture.sqlite')
        stack.callback(remote.close)
        remote.client = Client()
        class Ai:
            model = 'gpt-6-sol'
            output_limits = LIMITS
            payload = NewsAi.payload
            def __init__(self): self.calls = []
            def __call__(self, name, schema, prompt):
                self.calls.append(name)
                value = encoded_fixture(b, p) if name == 'swedish_ev_article' else copy.deepcopy(review)
                if corrupt and name == 'swedish_ev_article':
                    value['article']['intro_fact_ids'] = ['unknown']
                raw = json.dumps(self.payload(name, schema, prompt), ensure_ascii=False).encode()
                remote.client.receipts.append({'id': str(len(self.calls)), 'created_at': NOW.isoformat(),
                    'stage': name, 'model': self.model, 'settled_at': NOW.isoformat(), 'budget_closed_at': None,
                    'provider_status': 'completed', 'charged_micro_usd': 1000,
                    'reserved_micro_usd': 1000, 'input_tokens': 100, 'output_tokens': 50,
                    'request_hash': hashlib.sha256(raw).hexdigest(),
                    'response_payload': {'status': 'completed', 'output': [{'content': [
                        {'type': 'output_text', 'text': json.dumps(value, ensure_ascii=False)}]}]}})
                if unknown:
                    remote.client.receipts[-1].update(settled_at=None, provider_status='reserved')
                    raise RuntimeError('Synthetic transport ambiguity; reservation must remain counted')
                return value
        ai = Ai()
        stack.enter_context(patch.object(worker, 'matrix_valid', return_value=True))
        stack.enter_context(patch.object(worker, 'bundle_errors', side_effect=lambda value: bundle_errors(value, NOW)))
        stack.enter_context(patch.object(worker, 'evidence_readiness', side_effect=lambda value: evidence_readiness(value, NOW)))
        stack.enter_context(patch.object(worker, 'precheck', side_effect=lambda bundle, packet, now=None: precheck(bundle, packet, now or NOW)))
        stack.enter_context(patch.object(worker, 'stage', side_effect=lambda st, bundle, packet, rev, ids, **kw:
                                              stage(st, bundle, packet, rev, ids, now=NOW, **kw)))
        stack.enter_context(patch.object(worker, 'now_iso', return_value=NOW.isoformat()))
        stack.enter_context(patch('news_store.now_iso', return_value=NOW.isoformat()))
        stack.enter_context(patch.object(worker, 'DIRECTORY', Path(folder) / 'private-fixtures'))
        stack.enter_context(patch.object(worker, 'budget', side_effect=lambda st, required=0: {
            'allowed': required <= allowance, 'remaining_micro_usd': allowance, 'publication_enabled': True}))
        return remote, b, p, ai

    def test_private_pair_is_idempotent_and_never_publishes(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = self.setup_environment(stack, folder)
            record = worker.perform(remote, b, private=True, ai=ai)
            self.assertEqual(record['state'], 'passed', record)
            self.assertEqual(record['cost_micro_usd'], 2000)
            self.assertIsNotNone(worker.reviewed_record(remote, record), 'Exact successful mock receipts must verify')
            self.assertEqual(remote.public_articles(), [])
            self.assertEqual(remote.rows('news_articles'), [], 'Private tests stay out of production article staging')
            again = worker.perform(remote, b, private=True, ai=ai)
            self.assertTrue(again['reused_attempt'])
            self.assertEqual(ai.calls, ['swedish_ev_article', 'ev_news_independent_audit'])

    def test_full_pair_must_fit_before_the_first_call(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = self.setup_environment(stack, folder, allowance=1)
            result = worker.perform(remote, b, private=True, ai=ai)
            self.assertEqual(result['status'], 'deferred_budget')
            self.assertEqual(ai.calls, [])
            self.assertEqual(remote.rows('news_ingestion_runs'), [])

    def test_bad_draft_does_not_buy_review_or_register_source_gate(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = self.setup_environment(stack, folder, corrupt=True)
            record = worker.perform(remote, b, private=True, ai=ai)
            self.assertEqual(record['status'], 'quarantined')
            self.assertEqual(record['cost_micro_usd'], 1000)
            self.assertEqual(ai.calls, ['swedish_ev_article'])
            self.assertFalse(any(r['payload'].get('kind') == 'publisher_source_proof' for r in remote.rows('news_ingestion_runs')))

    def test_approved_source_and_publication_day_are_checked_before_paid_work(self):
        class Remote:
            def public_articles(self): return [{'published_at': NOW.isoformat()}]
        with patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}), \
             patch.object(worker, 'matrix_valid', return_value=True), patch.object(worker, 'load_state', return_value={}), \
             patch.object(worker, 'budget', return_value={'allowed': True, 'publication_enabled': True}), \
             patch.object(worker, 'now_iso', return_value=NOW.isoformat()), \
             patch.object(worker, 'perform', side_effect=AssertionError('No paid call allowed')):
            self.assertEqual(worker.daily(Remote(), None)['status'], 'daily_limit')

    def test_an_unreviewed_candidate_cannot_publish_without_article_gates(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, _ = self.setup_environment(stack, folder)
            remote.put('news_items', {**b['items'][0], 'status': 'collected'})
            stack.enter_context(patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}))
            stack.enter_context(patch.object(worker, 'collect_bundle', return_value=b))
            stack.enter_context(patch.object(worker, 'perform', return_value={'status': 'quarantined', 'published': 0}))
            stack.enter_context(patch.object(worker, 'release', side_effect=AssertionError('A failed draft cannot publish')))
            self.assertEqual(worker.daily(remote, None)['status'], 'quarantined')
            self.assertEqual(remote.public_articles(), [])

    def test_unknown_usage_keeps_the_maximum_instead_of_reporting_zero(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = self.setup_environment(stack, folder, unknown=True)
            record = worker.perform(remote, b, private=True, ai=ai)
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['cost_micro_usd'], 1000)
            self.assertEqual(record['cost_status'], 'reservation_retained_usage_unknown')
            self.assertEqual(len(ai.calls), 1)
            self.assertEqual(remote.public_articles(), [])

    def test_retired_source_admission_cannot_spend_even_when_old_flag_is_on(self):
        with patch.dict('os.environ', {'NEWS_PUBLISHER_QUALIFICATION_ENABLED': 'true'}), \
             patch.object(worker, 'perform', side_effect=AssertionError('No paid call allowed')):
            self.assertEqual(worker.qualify(None, None)['status'], 'retired_source_qualification')

    def test_new_policy_keeps_historical_rejected_urls_out_of_the_queue(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = self.setup_environment(stack, folder)
            old = copy.deepcopy(b['items'][0])
            old['status'] = 'collected'
            old['url'] = REPORT_URL.replace('synthetic-battery-project', 'rejected-old-story')
            old['id'] = worker.stable_id(old['url'])
            remote.put('news_items', old)
            remote.put('news_items', {**b['items'][0], 'status': 'collected'})
            remote.put('news_ingestion_runs', {'id': 'previous-code-rejection', 'payload': {
                'kind': 'publisher_private_trial', 'recipe': 'news-publisher-short-2026-11-v1', 'code_hash': 'older',
                'url': old['url'], 'started_at': '2026-10-31T12:00:00+00:00', 'state': 'quarantined'}})
            queue, _ = worker.selection_queue(remote, worker.LEAD_SOURCES)
            self.assertEqual([item['url'] for item, _ in queue], [REPORT_URL])
            self.assertEqual(ai.calls, [])

    def test_source_admission_is_not_needed_for_a_valid_reviewed_production_article(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = self.setup_environment(stack, folder)
            remote.put('news_items', {**b['items'][0], 'status': 'collected'})
            stack.enter_context(patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}))
            stack.enter_context(patch.object(worker, 'NewsAi', return_value=ai))
            stack.enter_context(patch.object(worker, 'require_recent_publication'))
            stack.enter_context(patch.object(worker, 'collect_bundle', return_value=b))
            stack.enter_context(patch.object(worker, 'refresh_bundle', return_value=copy.deepcopy(b)))
            stack.enter_context(patch.object(worker, 'models_for_news', return_value={}))
            stack.enter_context(patch.object(worker, 'queue_verification'))
            stack.enter_context(patch.object(worker, 'export_public', return_value={'synthetic': True}))
            result = worker.daily(remote, None)
            self.assertEqual(result['status'], 'published', result)
            self.assertEqual(ai.calls, ['swedish_ev_article', 'ev_news_independent_audit'])
            self.assertEqual(worker.daily(remote, None)['status'], 'daily_limit')

    def test_manual_trial_cap_is_preserved_for_explicit_private_tests(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = self.setup_environment(stack, folder)
            for i in range(3):
                remote.put('news_ingestion_runs', {'id': str(i), 'payload': {
                    'kind': 'publisher_private_trial', 'recipe': worker.RECIPE,
                    'started_at': NOW.isoformat(), 'url': 'synthetic-' + str(i)}})
            self.assertEqual(worker.perform(remote, b, private=True, ai=ai)['status'], 'private_trial_limit')
            self.assertEqual(ai.calls, [])

    def test_private_success_is_not_automatically_promoted_to_publication(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            remote, b, _, ai = self.setup_environment(stack, folder)
            remote.put('news_items', {**b['items'][0], 'status': 'collected'})
            stack.enter_context(patch.dict('os.environ', {'NEWS_PUBLISHER_ARTICLES_ENABLED': 'true'}))
            private = worker.perform(remote, b, private=True, ai=ai)
            self.assertEqual(private['status'], 'passed')
            stack.enter_context(patch.object(worker, 'release', side_effect=AssertionError('Private test cannot auto-publish')))
            self.assertEqual(worker.daily(remote, None)['status'], 'no_eligible_new_source')
            self.assertEqual(len(ai.calls), 2)
            self.assertEqual(remote.public_articles(), [])

    def test_changed_primary_source_blocks_release_without_another_ai_call(self):
        b, p = fixture()
        changed = copy.deepcopy(b)
        changed['items'][1]['payload']['content_hash'] = 'b' * 64
        proof = {'source_id': 'carnewschina', 'kind': 'short_daily', 'bundle': b, 'packet': p,
                 'review': accepted_review(b, p), 'request_ids': ['synthetic-a', 'synthetic-b']}
        with patch.object(worker, 'reviewed_record', return_value=proof), \
             patch.object(worker, 'precheck', return_value={'passed': True}), \
             patch.object(worker, 'event_duplicate', return_value=False), \
             patch.object(worker, 'refresh_bundle', return_value=changed), \
             patch.object(worker, 'stage', side_effect=AssertionError('Do not stage changed evidence')):
            result = worker.release(object(), proof, None)
            self.assertEqual(result['status'], 'source_changed_requires_new_review')
            self.assertEqual(result['published'], 0)


if __name__ == '__main__':
    unittest.main()
