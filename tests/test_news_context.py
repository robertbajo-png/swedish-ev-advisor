import copy
from contextlib import closing
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_editorial import source_qualifier_facts, validate_article, writer_schema, generate_article
from news_engine import attach_cluster, editorial
from news_store import NewsStore, artifact_hash

RANGE = 'The stated WLTP range varies with equipment and the selected configuration.'
CHARGING = 'Charging duration depends on the initial battery state of charge and ambient temperature.'


class NewsSourceContextTests(unittest.TestCase):
    def item(self):
        item = fixtures.item()
        item['payload']['content'] += RANGE + ' ' + CHARGING
        item['payload']['content_hash'] = artifact_hash(item['payload']['content'])
        return item

    def test_qualifiers_are_literal_versioned_primary_source_facts(self):
        item = self.item()
        facts = source_qualifier_facts(item)
        self.assertEqual([f['evidence'] for f in facts], [RANGE, CHARGING])
        for fact in facts:
            self.assertEqual(fact['statement'], fact['evidence'])
            self.assertEqual(fact['source_hash'], item['payload']['content_hash'])
            self.assertIn(fact['evidence'], item['payload']['content'])
            self.assertEqual(fact['item_id'], item['id'])
            self.assertTrue(8 <= len(fact['evidence'].split()) <= 24)

    def test_secondary_inaccessible_and_unversioned_sources_cannot_supply_context(self):
        for field, value in [('source_kind', 'secondary'), ('access_status', 'blocked'), ('content_hash', '')]:
            item = self.item()
            item['payload'][field] = value
            self.assertEqual(source_qualifier_facts(item), [])

    def test_missing_caveats_are_never_invented_from_specifications(self):
        self.assertEqual(source_qualifier_facts(fixtures.item()), [])
        item = self.item()
        item['payload']['content'] = 'The range is 500 km and charging takes 20 minutes. Equipment is standard.'
        self.assertEqual(source_qualifier_facts(item), [])

    def test_overlong_caveats_are_not_cut_into_out_of_context_fragments(self):
        item = self.item()
        item['payload']['content'] = 'The WLTP range varies with equipment ' + ' '.join(['qualifier'] * 25) + '.'
        self.assertEqual(source_qualifier_facts(item), [])

    def test_context_is_bounded_and_ids_are_deterministic(self):
        item = self.item()
        item['payload']['content'] += ' The measured WLTP range varies with equipment and also varies with temperature.'
        first = source_qualifier_facts(item)
        self.assertEqual(len(first), 2)
        self.assertEqual(first, source_qualifier_facts(copy.deepcopy(item)))

    def test_context_blocks_are_required_and_citations_are_known_ids_only(self):
        facts = fixtures.extraction()['facts'] + source_qualifier_facts(self.item())
        root = writer_schema(facts)['properties']
        context = root['source_context']
        self.assertEqual(set(context['required']), {f['id'] for f in facts[-2:]})
        self.assertTrue(all(group['type'] == 'string' for group in context['properties'].values()))
        self.assertNotIn('citations', root)
        self.assertEqual(root['paragraphs']['minItems'], root['paragraphs']['maxItems'])

    def test_missing_source_explanation_is_rejected_not_silently_omitted(self):
        facts = fixtures.extraction()['facts'] + source_qualifier_facts(self.item())
        with self.assertRaisesRegex(ValueError, 'writer_source_context_missing_or_invalid'):
            generate_article(facts, Mock(return_value=fixtures.writer_result(fixtures.draft())))

    def test_no_facts_never_triggers_a_paid_writer(self):
        ai = Mock()
        with self.assertRaisesRegex(ValueError, 'news_no_factual_inventory'):
            generate_article([], ai)
        ai.assert_not_called()

    def test_source_context_still_needs_independent_fact_and_block_review(self):
        item = self.item()
        facts = [{**f, 'item_id': item['id']} for f in fixtures.extraction()['facts']] + source_qualifier_facts(item)
        checks = validate_article(fixtures.draft(), facts, [item], fixtures.audit(), 90)
        self.assertIn('fact_audit_failed_or_incomplete', checks['evidence'])

    def test_writer_auditor_and_private_evidence_receipt_use_the_same_inventory(self):
        with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory) / 'news.sqlite')) as store:
            store.put('news_sources', {'id': fixtures.SOURCE['id'], 'payload': fixtures.SOURCE})
            item = attach_cluster(store, self.item(), fixtures.extraction())
            inventory = [{**f, 'id': item['id'] + ':f' + str(n), 'item_id': item['id'], 'publisher': item['payload']['publisher']}
                         for n, f in enumerate(fixtures.extraction()['facts'])] + source_qualifier_facts(item)
            def ai(name, schema, prompt):
                if name == 'swedish_ev_article':
                    self.assertIn(RANGE, prompt)
                    self.assertIn(CHARGING, prompt)
                    draft = fixtures.draft()
                    draft['title_fact_ids'] = [inventory[0]['id']]
                    draft['intro_fact_ids'] = [f['id'] for f in inventory[:3]]
                    for block in draft['paragraphs']:
                        block['fact_ids'] = [f['id'] for f in inventory[:3]]
                    explanations = ['Vald utrustning och bilens konfiguration kan ge olika resultat i WLTP-provet.',
                                    'Batteriets utgangslage och temperaturen i omgivningen paverkar hur lang tid laddningen tar.']
                    context = {f['id']: {'kind': 'reporting', 'fact_ids': [f['id']], 'text': text}
                               for f, text in zip(inventory[-2:], explanations)}
                    return fixtures.writer_result(draft, context)
                self.assertIn(RANGE, prompt)
                audit = fixtures.audit(inventory)
                audit['blocks'] = [{'id': key, 'supported': True, 'reason': 'Fixture evidence', 'unsupported_claims': [],
                                    'verdict': 'grounded_question' if key == 'p3' else 'evidence_supported'}
                                   for key in ['title', 'intro', 'p0', 'p1', 'p2', 'p3']]
                return fixtures.keyed_audit(audit)
            with patch('news_engine.models_for_news', return_value={}):
                result = editorial(store, ai=ai, publish=False)
            self.assertEqual(result[0]['status'], 'validated_draft')
            receipt = next(row for row in store.rows('news_quality_checks') if row['kind'] == 'evidence')
            self.assertEqual(receipt['payload']['fact_inventory'], inventory)
            article = store.rows('news_articles')[0]
            self.assertEqual(receipt['payload']['fact_plan']['hash'], article['payload']['fact_plan_hash'])
            self.assertNotIn('fact_plan', article['payload'])
            self.assertEqual(store.public_articles(), [])
