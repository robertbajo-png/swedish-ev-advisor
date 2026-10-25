"""Synthetic, local-only hybrid launch regressions. No network/provider/public writes."""
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout, redirect_stderr
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from news_launch_hybrid import (HYBRID_POLICY, HybridRejected, brief_errors, launch_brief,
                                precheck_article, review_errors, reviewer_call, stage_offline_launch, writer_call)
from news_notice_pipeline import stage_notices
from news_store import NewsStore, artifact_hash
from preview_news_launch_hybrid import fixture_article, fixture_audit, fixture_input, main

DATA = json.loads((ROOT / 'tests/fixtures/news_hybrid_launch.json').read_text(encoding='utf-8'))
NOW = datetime.fromisoformat(DATA['published_at'])


def prepared(data=None):
    data = copy.deepcopy(data or DATA)
    items, sources = fixture_input(data)
    brief = launch_brief(items, sources, now=NOW)
    return items, sources, brief, fixture_article(data, brief)


def change_content(item, old, new):
    item['payload']['content'] = item['payload']['content'].replace(old, new)
    item['payload']['content_hash'] = hashlib.sha256(item['payload']['content'].encode()).hexdigest()


class HybridLaunchTests(unittest.TestCase):
    def test_rich_model_has_source_bound_diverse_facts_and_strict_writer_contract(self):
        items, _, brief, article = prepared()
        self.assertTrue(brief['article_eligible'])
        self.assertGreaterEqual(len(brief['facts']), 8)
        self.assertTrue(all(f['evidence'] in items[0]['payload']['content'] for f in brief['facts']))
        self.assertTrue(all(f['source_hash'] == items[0]['payload']['content_hash'] for f in brief['facts']))
        name, schema, prompt = writer_call(brief)
        self.assertEqual(name, 'ev_news_hybrid_launch_write')
        self.assertFalse(schema['additionalProperties'])
        self.assertIn('200-350', prompt)
        self.assertNotIn(items[0]['payload']['content'], prompt, 'Writer gets cards, not full source prose')
        self.assertEqual(brief_errors(brief, NOW), [])
        result = precheck_article(article, brief, NOW)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['word_count'], 222)

    def test_second_exact_model_reuses_adapter_without_borrowing_old_specs(self):
        items, sources, _, _ = prepared()
        change_content(items[0], 'ID. Cross', 'ID. Polo')
        items[0]['payload']['title'] = items[0]['payload']['title'].replace('ID. Cross', 'ID. Polo')
        brief = launch_brief(items, sources, now=NOW)
        self.assertEqual(brief['subject'], 'Volkswagen ID. Polo')
        self.assertNotIn('ID. Cross', json.dumps(brief))

    def test_writer_receives_month_boundary_and_exact_technical_scope(self):
        _, _, brief, _ = prepared()
        before = copy.deepcopy(brief)
        _, _, prompt = writer_call(brief)
        cards = {f['metric']: f for f in json.loads(prompt.split('\n', 1)[1])['FACT_CARDS']}
        timing = cards['market_launch']['card']['timing']
        self.assertEqual(timing['boundary_months'], ['november', 'december'])
        self.assertEqual(timing['precision'], 'month_boundary')
        self.assertEqual(timing['year_basis'], 'not_stated')
        for metric in ('technical:ac_power', 'technical:cargo', 'technical:braked_tow'):
            self.assertEqual(cards[metric]['scope'], {'model': 'ID. Cross', 'battery_kwh': '39'})
        self.assertEqual(cards['qualification:charging']['card']['qualification']['measurement'],
                         'time_until_full_charge')
        self.assertIn('Only buyer_context uses kind analysis', prompt)
        self.assertIn('never in visible text', prompt)
        self.assertEqual(brief, before, 'Prompt preparation must not edit source-bound facts')

    def test_writer_still_excludes_adjacent_table_fields_and_full_source_prose(self):
        items, _, brief, _ = prepared()
        _, _, prompt = writer_call(brief)
        cards = json.loads(prompt.split('\n', 1)[1])['FACT_CARDS']
        price = next(f['card'] for f in cards if f['topic'] == 'price')
        self.assertNotIn('power_kw', price)
        self.assertNotIn('range_km', price)
        ac = next(f for f in cards if f['metric'] == 'technical:ac_power')
        self.assertNotIn('evidence', ac)
        self.assertNotIn('Topphastighet', prompt)
        self.assertNotIn(items[0]['payload']['content'], prompt)

    def test_scoped_battery_identity_is_supported_but_invented_capacity_is_not(self):
        for capacity in ('39', '99'):
            _, _, brief, article = prepared()
            article['paragraphs'][3]['text'] += ' Dessa lastuppgifter g\u00e4ller versionen med ' + capacity + ' kWh.'
            result = precheck_article(article, brief, NOW)
            with self.subTest(capacity=capacity):
                self.assertEqual('hybrid_number_outside_bound_fact:p3' in result['errors'], capacity == '99')
                if capacity == '39':
                    self.assertTrue(result['passed'], result)

    def test_scoped_battery_number_does_not_authorize_a_charging_power(self):
        _, _, brief, article = prepared()
        paragraph = article['paragraphs'][2]
        paragraph['text'] = paragraph['text'].replace('11 kW', '39 kW')
        paragraph['text'] += ' AC-uppgiften g\u00e4ller batteriversionen med 39 kWh.'
        self.assertIn('hybrid_number_outside_bound_fact:p2', precheck_article(article, brief, NOW)['errors'])

    def test_thin_evidence_recommends_notice_without_any_writer_or_reviewer(self):
        items, sources, _, _ = prepared()
        content = items[0]['payload']['content']
        items[0]['payload']['content'] = content.split(' Följande versioner')[0]
        items[0]['payload']['content_hash'] = hashlib.sha256(items[0]['payload']['content'].encode()).hexdigest()
        writer, reviewer = Mock(), Mock()
        with tempfile.TemporaryDirectory() as tmp, closing(NewsStore(Path(tmp) / 'test.sqlite')) as store:
            result = stage_offline_launch(store, items, sources, writer, reviewer, now=NOW)
            self.assertEqual(result['status'], 'notice_recommended')
            self.assertEqual(store.rows('news_articles'), [])
            writer.assert_not_called(); reviewer.assert_not_called()

    def test_insufficient_brief_cannot_be_sent_to_writer_directly(self):
        _, _, brief, _ = prepared()
        brief['article_eligible'] = False
        with self.assertRaisesRegex(HybridRejected, 'thin_evidence'):
            writer_call(brief)

    def test_europe_only_tentative_or_wrong_model_launch_does_not_become_sweden(self):
        for old, new in [('svenska marknaden vid', 'europeiska marknaden vid'),
                         ('ID. Cross lanseras', 'ID. Polo lanseras'),
                         ('ID. Cross lanseras', 'ID. Cross förväntas lanseras'),
                         ('november/december', 'november/januari'), ('(netto)', '(brutto)')]:
            with self.subTest(change=(old, new)):
                items, sources, _, _ = prepared(); change_content(items[0], old, new)
                with self.assertRaises(HybridRejected): launch_brief(items, sources, now=NOW)

    def test_non_official_domain_unreachable_and_unsupported_adapters_rejected(self):
        for change in ('dealer', 'domain', 'blocked', 'redirect'):
            items, sources, _, _ = prepared()
            if change == 'dealer': sources[0]['kind'] = 'publisher'
            if change == 'domain': items[0]['url'] = items[0]['payload']['final_url'] = 'https://comparison.example/model'
            if change == 'blocked': items[0]['payload']['access_status'] = 'blocked'
            if change == 'redirect': items[0]['payload']['final_url'] = 'https://www.vwgroup.se/other/'
            with self.subTest(change=change), self.assertRaises(HybridRejected): launch_brief(items, sources, now=NOW)
        items, sources, _, _ = prepared()
        items[0]['source_id'] = sources[0]['id'] = 'new-unverified-adapter'
        with self.assertRaisesRegex(HybridRejected, 'adapter_required'): launch_brief(items, sources, now=NOW)

    def test_stale_future_or_hash_changed_evidence_blocks_preparation(self):
        for key, value in [('fetched_at', (NOW - timedelta(days=2)).isoformat()),
                           ('published_at', (NOW - timedelta(days=8)).isoformat()),
                           ('published_at', (NOW + timedelta(days=1)).isoformat()), ('content_hash', 'a' * 64)]:
            items, sources, _, _ = prepared(); items[0]['payload'][key] = value
            with self.subTest(key=key), self.assertRaises(HybridRejected): launch_brief(items, sources, now=NOW)

    def test_cross_source_variant_price_or_battery_conflicts_quarantine(self):
        for old, new in [('359 000', '459 000'), ('330 km (WLTP)', '331 km (WLTP)')]:
            items, sources, _, _ = prepared()
            second = copy.deepcopy(items[0]); second['id'] += '-second'
            second['url'] = second['payload']['final_url'] = second['url'].replace('offline-fixture/', 'second-fixture/')
            change_content(second, old, new)
            with self.subTest(change=new), self.assertRaisesRegex(HybridRejected, 'conflicting_fact'):
                launch_brief([*items, second], sources, now=NOW)

    def test_identical_corroboration_does_not_inflate_fact_count(self):
        items, sources, first, _ = prepared()
        second = copy.deepcopy(items[0]); second['id'] += '-second'
        second['url'] = second['payload']['final_url'] = second['url'].replace('offline-fixture/', 'second-fixture/')
        merged = launch_brief([*items, second], sources, now=NOW)
        self.assertEqual(len(merged['facts']), len(first['facts']))
        self.assertEqual(len(merged['sources']), 2)

    def test_workflow_metadata_does_not_change_fact_fingerprint(self):
        items, sources, before, _ = prepared()
        items[0].update(status='processed', cluster_id='private-workflow-id', updated_at=NOW.isoformat())
        items[0]['payload']['unused_extraction_metadata'] = {'review': 'pending'}
        after = launch_brief(items, sources, now=NOW)
        self.assertEqual(before['brief_hash'], after['brief_hash'])

    def test_ambiguous_technical_rows_do_not_silently_drop_a_conflict(self):
        items, sources, _, _ = prepared()
        change_content(items[0], 'Topphastighet:', 'AC-laddningskapacitet (max.): 22 kW Topphastighet:')
        with self.assertRaisesRegex(HybridRejected, 'ambiguous_technical_field'):
            launch_brief(items, sources, now=NOW)

    def test_fact_edits_and_changed_source_snapshots_require_rederivation(self):
        _, _, brief, article = prepared()
        brief['facts'][0]['card']['battery_kwh'] = '99'
        self.assertIn('hybrid_brief_or_evidence_changed', precheck_article(article, brief, NOW)['errors'])

    def test_missing_price_is_unknown_not_a_fabricated_zero(self):
        items, sources, _, _ = prepared()
        text = items[0]['payload']['content']
        price_part = text[text.index('Följande versioner'):text.index('Tekniska data')]
        change_content(items[0], price_part, '')
        brief = launch_brief(items, sources, now=NOW)
        self.assertTrue(brief['article_eligible'])
        self.assertFalse(any(f['topic'] == 'price' for f in brief['facts']))
        self.assertIn('Svenskt inköpspris är inte verifierat i detta underlag.', brief['unverified_in_this_brief'])

    def test_word_limits_exclude_headline(self):
        _, _, brief, article = prepared()
        for size in (199, 200, 350, 351):
            changed = copy.deepcopy(article)
            current = precheck_article(changed, brief, NOW)['word_count']
            words = changed['intro'].split()
            changed['intro'] = ' '.join(words[:len(words) + size - current]) if size < current else changed['intro'] + ' besked' * (size - current)
            check = precheck_article(changed, brief, NOW)
            self.assertEqual(check['word_count'], size)
            self.assertEqual('hybrid_body_word_count_outside_200_350' in check['errors'], size in (199, 351))

    def test_numeric_invention_cannot_use_adjacent_technical_table_values(self):
        _, _, brief, article = prepared()
        ac = next(f for f in brief['facts'] if f['metric'] == 'technical:ac_power')
        self.assertIn('39', ac['evidence'])
        self.assertNotIn('39', ac['statement'])
        article['paragraphs'][2]['text'] = article['paragraphs'][2]['text'].replace('11 kW', '39 kW')
        self.assertIn('hybrid_number_outside_bound_fact:p2', precheck_article(article, brief, NOW)['errors'])

    def test_wltp_net_and_charging_qualifications_cannot_be_lost(self):
        changes = [(1, 'högst 330', '330', 'hybrid_missing_wltp_upper_bound:p1'),
                   (1, 'enligt WLTP', '', 'hybrid_missing_wltp_upper_bound:p1'),
                   (1, 'användbara kapaciteten', 'kapaciteten', 'hybrid_missing_net_battery_basis:p1'),
                   (2, 'ungefärlig', 'uppgiven', 'hybrid_missing_charge_approximation:p2'),
                   (2, '10 och 80', '20 och 80', 'hybrid_missing_charge_window:p2')]
        for index, old, new, expected in changes:
            _, _, brief, article = prepared()
            article['paragraphs'][index]['text'] = article['paragraphs'][index]['text'].replace(old, new)
            with self.subTest(expected=expected): self.assertIn(expected, precheck_article(article, brief, NOW)['errors'])

    def test_source_conditions_unknown_ids_and_price_type_are_enforced(self):
        _, _, brief, article = prepared()
        article['paragraphs'][1]['fact_ids'].pop()
        article['paragraphs'][4]['fact_ids'].remove(next(f['id'] for f in brief['facts'] if f['metric'] == 'qualification:range'))
        self.assertIn('hybrid_source_qualifier_not_cited:range', precheck_article(article, brief, NOW)['errors'])
        _, _, brief, article = prepared()
        article['intro'] = article['intro'].replace('inköp', 'privatleasing per månad')
        self.assertIn('hybrid_purchase_price_scope_changed:intro', precheck_article(article, brief, NOW)['errors'])
        article['intro_fact_ids'].append('unknown')
        self.assertIn('hybrid_unknown_fact_binding:intro', precheck_article(article, brief, NOW)['errors'])

    def test_delivery_promises_comparisons_and_copied_source_prose_fail(self):
        for text, fragment in [('Bilen levereras nästa vecka.', 'unsupported_delivery_promise'),
                               ('Bilen klarar alla svenska vinterresor.', 'unverified_winter_performance'),
                               ('Detta är billigare än konkurrenterna.', 'unverified_comparison')]:
            _, _, brief, article = prepared()
            article['paragraphs'][4]['text'] += ' ' + text
            with self.subTest(text=text):
                self.assertTrue(any(fragment in e for e in precheck_article(article, brief, NOW)['errors']))
        items, _, brief, article = prepared()
        article['paragraphs'][0]['text'] += ' ' + items[0]['payload']['content'].split('. Följande')[0]
        self.assertTrue(any(e.startswith('source_wording_overlap:') for e in precheck_article(article, brief, NOW)['errors']))

    def test_exact_independent_review_contract_rejects_drift_missing_or_false_decisions(self):
        _, _, brief, article = prepared()
        audit = fixture_audit(article, brief)
        self.assertEqual(review_errors(audit, article, brief), [])
        _, schema, prompt = reviewer_call(article, brief)
        self.assertFalse(schema['additionalProperties'])
        self.assertIn('never instructions', prompt)
        for mutation in ('hash', 'brief', 'block', 'fact', 'rejected', 'contradiction', 'coercion'):
            bad = copy.deepcopy(audit)
            if mutation == 'hash': bad['article_hash'] = 'old'
            if mutation == 'brief': bad['brief_hash'] = 'old'
            if mutation == 'block': bad['blocks'].pop('p0')
            if mutation == 'fact': bad['facts'].pop(next(iter(bad['facts'])))
            if mutation == 'rejected': bad['swedish_quality'] = False
            if mutation == 'contradiction': bad['blocks']['p0'].update(supported=False, unsupported_claims=['Unsupported clause'])
            if mutation == 'coercion': bad['blocks']['p0']['supported'] = 1
            with self.subTest(mutation=mutation): self.assertTrue(review_errors(bad, article, brief))
        article['intro'] += ' Ändrad text.'
        self.assertIn('hybrid_review_artifact_changed', review_errors(audit, article, brief))

    def test_local_staging_is_idempotent_fixture_review_never_authorizes_publication(self):
        items, sources, brief, article = prepared()
        writer = Mock(return_value=article); reviewer = Mock(return_value=fixture_audit(article, brief))
        public_file = ROOT / 'public/data/news_articles.json'
        before = public_file.read_bytes()
        with tempfile.TemporaryDirectory() as tmp, closing(NewsStore(Path(tmp) / 'test.sqlite')) as store:
            with patch('news_ai.production_ai_json', side_effect=AssertionError('No paid calls')):
                result = stage_offline_launch(store, items, sources, writer, reviewer, now=NOW)
                self.assertEqual(result['status'], 'offline_validated_draft', result)
                self.assertFalse(result['live_release_eligible'])
                rerun = stage_offline_launch(store, items, sources, writer, reviewer, now=NOW)
            self.assertEqual(rerun['status'], 'unchanged_private_draft')
            writer.assert_called_once(); reviewer.assert_called_once()
            self.assertEqual(store.public_articles(), [])
            self.assertEqual(len(store.rows('news_articles')), 1)
            checks = store.rows('news_quality_checks')
            self.assertTrue(all(c['payload']['policy_version'] == HYBRID_POLICY and not c['payload']['audit_performed'] for c in checks))
            self.assertFalse(next(c for c in checks if c['kind'] == 'editorial')['passed'])
            with self.assertRaisesRegex(ValueError, 'quality_gates'): store.publish(result['article_id'])
            # Even forged green fixture checks cannot authorize the legacy policy.
            store.db.execute("update news_quality_checks set passed='1'"); store.db.commit()
            with self.assertRaisesRegex(ValueError, 'quality_gates'): store.publish(result['article_id'])
            store.db.execute('update news_notice_release_config set enabled=1,publication_enabled=1'); store.db.commit()
            private = store.get('news_articles', result['article_id'])
            with self.assertRaisesRegex(ValueError, 'release_checks_failed'):
                store.publish_notice(private['id'], private['artifact_hash'], private['payload'], {}, now=NOW)
            store.put('news_articles', {**private, 'payload': {**private['payload'], 'intro': private['payload']['intro'] + ' Ändrat.'}})
            stale = stage_offline_launch(store, items, sources, writer, reviewer, now=NOW)
            self.assertEqual(stale['status'], 'private_draft_requires_recheck')
            self.assertIn('hybrid_review_artifact_changed', stale['errors'])
        self.assertEqual(public_file.read_bytes(), before)

    def test_failed_precheck_skips_review_and_retains_private_quarantine(self):
        items, sources, _, article = prepared()
        article['intro'] += ' Priset är 999 kronor.'
        reviewer = Mock()
        with tempfile.TemporaryDirectory() as tmp, closing(NewsStore(Path(tmp) / 'test.sqlite')) as store:
            result = stage_offline_launch(store, items, sources, lambda *_: article, reviewer, now=NOW)
            reviewer.assert_not_called()
            self.assertEqual(result['status'], 'quarantined')
            self.assertEqual(store.get('news_articles', result['article_id'])['status'], 'quarantined')
            self.assertEqual(store.public_articles(), [])

    def test_negative_final_review_never_promotes_a_static_pass(self):
        items, sources, brief, article = prepared()
        audit = fixture_audit(article, brief)
        audit['blocks']['p4'].update(supported=False, unsupported_claims=['Unsupported buyer implication'])
        audit['no_unsupported_claims'] = False
        with tempfile.TemporaryDirectory() as tmp, closing(NewsStore(Path(tmp) / 'test.sqlite')) as store:
            result = stage_offline_launch(store, items, sources, lambda *_: article, lambda *_: audit, now=NOW)
            self.assertEqual(result['status'], 'quarantined')
            self.assertIn('hybrid_review_unsupported:p4', result['errors'])
            self.assertEqual(store.public_articles(), [])

    def test_remote_store_is_rejected_before_read_write_or_ai(self):
        remote = Mock(); remote.backend = 'supabase'
        with self.assertRaisesRegex(HybridRejected, 'local_store_required'):
            stage_offline_launch(remote, [], [], Mock(), Mock())
        remote.rows.assert_not_called(); remote.put.assert_not_called()

    def test_notices_are_unchanged_and_already_published_events_cannot_be_duplicated(self):
        items, sources, _, _ = prepared()
        with tempfile.TemporaryDirectory() as tmp, closing(NewsStore(Path(tmp) / 'test.sqlite')) as store:
            store.put('news_items', items[0])
            notice = stage_notices(store, sources, {}, now=NOW)[0]
            old = store.get('news_articles', notice['article_id'])
            stage_offline_launch(store, items, sources, now=NOW)
            self.assertEqual(store.get('news_articles', notice['article_id']), old)
            # Disposable SQLite fixture only: emulate an already-published notice.
            store.db.execute("update news_articles set status='published',published_at=? where id=?", (NOW.isoformat(), old['id'])); store.db.commit()
            writer, reviewer = Mock(), Mock()
            result = stage_offline_launch(store, items, sources, writer, reviewer, now=NOW)
            self.assertEqual(result['status'], 'already_reported_use_existing_notice')
            writer.assert_not_called(); reviewer.assert_not_called()
            self.assertEqual(len(store.rows('news_articles')), 1)
            alias = copy.deepcopy(items[0]); alias['id'] += '-alias'
            alias['url'] = alias['payload']['final_url'] = alias['url'].replace('offline-fixture/', 'alias-fixture/')
            repeated = stage_offline_launch(store, [alias], sources, writer, reviewer, now=NOW)
            self.assertEqual(repeated['status'], 'already_reported_use_existing_notice')
            writer.assert_not_called(); reviewer.assert_not_called()

    def test_cli_cannot_target_public_output_or_a_remote_backend(self):
        with self.assertRaisesRegex(ValueError, 'private_local_directory'):
            main(['--fixture', str(ROOT / 'tests/fixtures/news_hybrid_launch.json'), '--output', str(ROOT / 'public')])
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            main(['--fixture', str(ROOT / 'tests/fixtures/news_hybrid_launch.json'), '--backend', 'supabase'])


if __name__ == '__main__': unittest.main()
