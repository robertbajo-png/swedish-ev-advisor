"""Synthetic mixed-format proofs. Fixtures are never actual provider approval."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_short_news as worker
from news_short_articles import make_brief, precheck, release
from news_store import artifact_hash, stable_id
from preview_news_launch_hybrid import fixture_input
from test_news_short_articles import china_item, fixture_review, sample_article, NOW
from test_news_notices import MODEL, PRICES, VW, source


def model_case():
    data = json.loads((ROOT / 'tests/fixtures/news_hybrid_launch.json').read_text(encoding='utf-8'))
    items, _ = fixture_input(data)
    brief = make_brief(items[0], 'model', NOW)
    ids = {f['metric']: f['id'] for f in brief['facts']}
    article = {'title': 'Volkswagen ID. Cross med 39 kWh kan f\u00f6rhandsbest\u00e4llas',
        'title_fact_ids': [ids['announcement']],
        'intro': 'Volkswagen har \u00f6ppnat f\u00f6rhandsbest\u00e4llningen av ID. Cross med 39 kWh-batteri. Den svenska marknadsintroduktionen \u00e4r planerad till skiftet mellan november och december. Det \u00e4r den batteriversionen som de angivna uppgifterna om r\u00e4ckvidd, laddning och utrymmen g\u00e4ller.',
        'intro_fact_ids': [ids['announcement'], ids['market_launch']], 'paragraphs': [
            {'text': 'Batteriets nettokapacitet \u00e4r 39 kWh och den angivna r\u00e4ckvidden \u00e4r upp till 330 kilometer enligt WLTP. Det \u00e4r ett maxv\u00e4rde enligt k\u00f6rcykeln, inte en uppgift om hur l\u00e5ngt bilen alltid g\u00e5r i praktiken. Det faktiska WLTP-v\u00e4rdet kan ocks\u00e5 variera med bilens utrustning.',
             'fact_ids': [ids['battery_range'], ids['qualification:range']], 'kind': 'reporting'},
            {'text': 'Vid DC-snabbladdning anges en effekt p\u00e5 95 kW och ungef\u00e4r 25 minuter f\u00f6r att ladda batteriet fr\u00e5n 10 till 80 procent. F\u00f6r AC-laddning \u00e4r den h\u00f6gsta angivna effekten 11 kW. Tidsuppgiften f\u00f6r snabbladdning g\u00e4ller d\u00e4rmed det angivna laddningsintervallet, inte en laddning till fullt batteri.',
             'fact_ids': [ids['charging'], ids['technical:ac_power']], 'kind': 'reporting'},
            {'text': 'Bagageutrymmet rymmer 450 liter och det fr\u00e4mre f\u00f6rvaringsutrymmet, frunken, ytterligare 15 liter. Med baks\u00e4tets ryggst\u00f6d nedf\u00e4llt anges bagagevolymen till 1 300 liter. F\u00f6r ID. Cross med 39 kWh-batteri \u00e4r den h\u00f6gsta bromsade sl\u00e4pvagnsvikten 1 000 kilo, b\u00e5de vid 8 och 12 procents lutning.',
             'fact_ids': [ids['technical:cargo'], ids['technical:braked_tow']], 'kind': 'reporting'}]}
    return {'format': 'ai_article', 'state': 'passed', 'brief': brief, 'article': article,
        'review': fixture_review(article, brief), 'request_ids': ['model-writer', 'model-review'],
        'finished_at': NOW.isoformat()}


class MixedReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        battery_brief = make_brief(china_item(), 'battery', NOW)
        battery = sample_article()
        self.state = {'recipe': worker.RECIPE, 'format_policy': worker.FORMAT_POLICY,
            'code_hash': worker.code_hash(), 'passed': False, 'cases': {
                'model': model_case(),
                'battery': {'format': 'ai_article', 'state': 'passed', 'brief': battery_brief,
                    'article': battery, 'review': fixture_review(battery, battery_brief),
                    'request_ids': ['battery-writer', 'battery-review'], 'finished_at': NOW.isoformat()},
                'price': worker.price_proof(source(MODEL + PRICES), VW, NOW)}}
        self.rows = {}
        for kind in worker.AI_KINDS:
            case = self.state['cases'][kind]
            for identity, stage, value in zip(case['request_ids'],
                    ['swedish_ev_article', 'ev_news_independent_audit'], [case['article'], case['review']]):
                self.rows[identity] = {'id': identity, 'stage': stage, 'model': 'gpt-6-sol',
                    'settled_at': NOW.isoformat(), 'provider_status': 'completed',
                    'response_payload': {'status': 'completed', 'output': [{'content': [{
                        'type': 'output_text', 'text': json.dumps(value)}]}]}}
        self.remote = Mock()
        self.remote.client.select.side_effect = lambda table, **kw: [self.rows[i] for i in
            kw['filters']['id'].removeprefix('in.(').removesuffix(')').split(',') if i in self.rows]

    def test_two_exact_ai_pairs_and_short_rule_review_satisfy_the_new_format_gate(self):
        self.assertTrue(precheck(self.state['cases']['model']['article'], self.state['cases']['model']['brief'], NOW)['passed'])
        self.assertTrue(worker.matrix_valid(self.remote, self.state))
        self.assertLess(self.state['cases']['price']['review']['word_count'], 150)
        self.assertFalse(self.state['cases']['price']['ai_audit_performed'])
        self.assertEqual(len(self.rows), 4)
        self.remote.put.assert_not_called()

    def test_old_policy_changed_code_or_missing_format_is_not_a_pass(self):
        for mutate in (lambda s: s.pop('format_policy'), lambda s: s.update(code_hash='old'),
                       lambda s: s['cases'].pop('price'), lambda s: s['cases']['model'].pop('format')):
            state = copy.deepcopy(self.state)
            mutate(state)
            self.assertFalse(worker.matrix_valid(self.remote, state))
        self.assertNotEqual(worker.state_id(), stable_id(worker.RECIPE + ':three-cases:' + worker.code_hash()))
        self.assertNotEqual(worker.DIRECTORY.name, 'news-short-rollout')

    def test_ai_price_pass_cannot_substitute_for_a_deterministic_notice(self):
        self.state['cases']['price'] = copy.deepcopy(self.state['cases']['model'])
        self.state['cases']['price']['brief']['kind'] = 'price'
        self.assertFalse(worker.matrix_valid(self.remote, self.state))

    def test_false_ai_review_flags_remain_blocking(self):
        for kind in worker.AI_KINDS:
            state = copy.deepcopy(self.state)
            state['cases'][kind]['review']['no_padding'] = False
            self.assertFalse(worker.matrix_valid(self.remote, state))

    def test_price_review_must_not_claim_ai_audit_or_borrow_ai_request_ids(self):
        for field, value in [('ai_audit_performed', True), ('request_ids', ['model-writer', 'model-review'])]:
            state = copy.deepcopy(self.state)
            state['cases']['price'][field] = value
            self.assertFalse(worker.matrix_valid(self.remote, state))

    def test_modified_price_text_review_source_or_market_fails(self):
        mutations = [lambda c: c['article'].update(intro='An invented offer.'),
                     lambda c: c['review'].update(passed=False),
                     lambda c: c['review'].update(method='ai_confidence'),
                     lambda c: c['item']['payload'].update(content_hash='0' * 64),
                     lambda c: c['source'].update(website='https://comparison.example')]
        for mutate in mutations:
            state = copy.deepcopy(self.state)
            mutate(state['cases']['price'])
            self.assertFalse(worker.matrix_valid(self.remote, state))

    def test_missing_unsettled_duplicate_or_modified_provider_receipts_fail(self):
        for mutation in ('missing', 'unsettled', 'modified', 'duplicate'):
            rows = copy.deepcopy(self.rows)
            state = copy.deepcopy(self.state)
            if mutation == 'missing': self.rows.pop('model-review')
            if mutation == 'unsettled': self.rows['model-review']['settled_at'] = None
            if mutation == 'modified': self.rows['model-writer']['response_payload']['output'][0]['content'][0]['text'] = '{}'
            if mutation == 'duplicate': state['cases']['battery']['request_ids'] = state['cases']['model']['request_ids']
            self.assertFalse(worker.matrix_valid(self.remote, state))
            self.rows = rows

    def test_failed_or_running_ai_case_cannot_be_promoted(self):
        for status in ('failed', 'running', 'quarantined'):
            state = copy.deepcopy(self.state)
            state['cases']['model']['state'] = status
            self.assertFalse(worker.matrix_valid(self.remote, state))

    def test_price_step_never_constructs_an_ai_client_or_publishes(self):
        state = copy.deepcopy(self.state)
        state['cases']['price']['state'] = 'prepared'
        with patch.object(worker, 'prepare', return_value=state), patch.object(worker, 'NewsAi') as ai, \
                patch.object(worker, 'fetch_item', return_value=source(MODEL + PRICES)), \
                patch.object(worker, 'price_proof', side_effect=lambda item, config: worker_price(item, config, NOW)), \
                patch.object(worker, 'checkpoint'), patch.object(worker, 'render_case'):
            result = worker.run_matrix(self.remote, Mock())
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['published'], 0)
        ai.assert_not_called()
        self.assertEqual(state['cases']['price']['request_ids'], [])
        self.remote.publish.assert_not_called()

    def test_price_proof_needs_only_one_typed_price_not_four_ai_facts(self):
        prices = PRICES[:PRICES.index('ID. Cross Life')] + 'Samtliga versioner finns i konfiguratorn.'
        proof = worker.price_proof(source(MODEL + prices), VW, NOW)
        self.assertEqual(proof['state'], 'passed')
        self.assertEqual(proof['request_ids'], [])
        self.assertEqual(proof['cost_micro_usd'], 0)

    def write_trial(self, directory, case):
        directory.mkdir()
        manifest = {'brief': case['brief'], 'code_hash': 'original-trial-profile'}
        report = {'state': 'completed', 'quality_passed': True, 'shutdown_verified': True,
            'publication': False, 'manifest_hash': artifact_hash(manifest), 'trial_id': directory.name,
            **{k: case[k] for k in ('article', 'review', 'request_ids', 'finished_at')}}
        (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (directory / 'report.json').write_text(json.dumps(report), encoding='utf-8')

    def test_frozen_proof_verification_is_read_only_and_never_promotes_failed_ai_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kind in worker.AI_KINDS:
                self.write_trial(root / kind, self.state['cases'][kind])
            price = root / 'price.json'
            price.write_text(json.dumps({'brief': {'kind': 'price', 'item': source(MODEL + PRICES), 'source': VW},
                'article': {'intro': 'Rejected AI price prose.'}, 'review': {'no_padding': False}}), encoding='utf-8')
            before = {p: p.read_bytes() for p in root.rglob('*.json')}
            with patch.object(worker, 'NewsAi') as ai, patch.object(worker, 'checkpoint') as checkpoint:
                verified = worker.verify_private_proofs(self.remote, root / 'model', root / 'battery', price, NOW)
            self.assertTrue(verified['passed'])
            self.assertFalse(verified['release_authorized'])
            self.assertEqual((verified['paid_calls'], verified['published']), (0, 0))
            self.assertNotIn('Rejected AI price prose.', json.dumps(verified['cases']['price']))
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*.json')})
            ai.assert_not_called(); checkpoint.assert_not_called()
            self.remote.put.assert_not_called(); self.remote.publish.assert_not_called()

    def test_rejected_ai_trial_or_changed_manifest_is_not_accepted_as_an_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_trial(root / 'model', self.state['cases']['model'])
            report_path = root / 'model/report.json'
            report = json.loads(report_path.read_text())
            for field, value in [('quality_passed', False), ('manifest_hash', 'forged')]:
                rejected = {**report, field: value}
                report_path.write_text(json.dumps(rejected), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'unchanged_successful_private_trial'):
                    worker.verify_private_proofs(self.remote, root / 'model', root / 'battery', root / 'price', NOW)

    def test_ai_publisher_rejects_price_even_with_a_claimed_format_pass(self):
        remote = Mock()
        for status, error in [('quarantined', 'validated_draft'), ('draft', 'price_requires_deterministic_notice')]:
            remote.get.return_value = {'status': status, 'payload': {'editorial_recipe': worker.RECIPE,
                'short_brief': {'kind': 'price'}}}
            with self.assertRaisesRegex(ValueError, error):
                release(remote, 'old-price', True, NOW)
        remote.publish.assert_not_called()

    def test_explicit_private_registration_never_overwrites_an_existing_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'proofs.json'
            path.write_text(json.dumps(self.state), encoding='utf-8')
            for old in ({'payload': {'state': 'failed'}}, {'payload': {'state': 'passed'}}):
                self.remote.get.return_value = old
                with patch.object(worker, 'checkpoint') as checkpoint, \
                        self.assertRaisesRegex(ValueError, 'already_exists_do_not_replace'):
                    worker.register_verified_proofs(self.remote, path)
                checkpoint.assert_not_called()
            self.remote.get.return_value = None
            with patch.object(worker, 'checkpoint') as checkpoint, patch.object(worker, 'NewsAi') as ai:
                state = worker.register_verified_proofs(self.remote, path)
            self.assertTrue(state['passed'])
            self.assertFalse(state['release_authorized'])
            checkpoint.assert_called_once_with(self.remote, state)
            ai.assert_not_called()
            self.remote.publish.assert_not_called()
            self.remote.client._request.assert_not_called()

    def test_proof_validation_cannot_enable_owner_flags_or_release_price_via_ai_publisher(self):
        with patch.object(worker, 'load_state', return_value=self.state):
            sql = worker.activation_sql(self.remote)
        self.assertIn(worker.FORMAT_POLICY, sql)
        self.assertIn("->'price'->>'format'='price_notice'", sql)
        self.assertIn("->'price'->'request_ids'='[]'::jsonb", sql)
        self.assertIn('Requires separate owner release approval', sql)
        self.assertNotIn('set enabled=true', sql)
        self.assertNotIn('update public.news_notice_release_config', sql)
        self.remote.client._request.assert_not_called()
        self.remote.put.assert_not_called()


worker_price = worker.price_proof


if __name__ == '__main__':
    unittest.main()
