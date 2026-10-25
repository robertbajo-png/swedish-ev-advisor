import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from news_http import PageText, Collector, SafeRedirect, canonical_url, parse_feed, reserved
from news_store import NewsStore, artifact_hash, stable_id, EDITORIAL_POLICY
from news_editorial import event_key, relevance_score, validate_article, validate_fact_extraction
from news_engine import attach_cluster, classify_metadata, collect, editorial, export_public, queue_verification

DATE = datetime.now(timezone.utc).isoformat()
SOURCE = {"id": "test-primary", "name": "Tillverkaren", "website": "https://press.example.com", "feeds": ["https://press.example.com/feed"], "kind": "primary", "reliability": 0.98, "priority": True}
CONTENT = (
    "The manufacturer introduces an updated electric model for European customers today. "
    "The new battery design improves efficiency during regular everyday driving. "
    "Orders for the European market will open later this year. "
)
STATEMENTS = [
    "Tillverkaren presenterar en uppdaterad elbil för kunder i Europa.",
    "Den nya batterikonstruktionen förbättrar effektiviteten vid vardagskörning.",
    "Beställningar på den europeiska marknaden öppnar senare under året.",
]
EVIDENCE = [s + "." for s in CONTENT.strip().split(". ")]
EVIDENCE[-1] = EVIDENCE[-1].rstrip(".") + "."


def item(key="item", kind="primary"):
    return {"id": key, "source_id": SOURCE["id"], "url": "https://press.example.com/release", "status": "processed", "cluster_id": None,
            "payload": {"content": CONTENT, "content_hash": artifact_hash(CONTENT), "access_status": "accessible", "title": "Electric model for Europe", "publisher": SOURCE["name"], "source_kind": kind, "reliability": 0.98, "published_at": DATE}}


def extraction():
    return {"relevant": True, "sweden_relevance": 0.9, "significance": 0.85, "category": "modeller",
            "event": {"subject": "manufacturer", "action": "launch", "date": DATE[:10], "description": "European electric model update"},
            "brands": [], "model_keys": [], "swedish_relevance_reason": "European buyers",
            "facts": [{"id": f"f{i}", "statement": s, "evidence": EVIDENCE[i], "central": i == 0} for i, s in enumerate(STATEMENTS)]}


def draft():
    return {
        "title": "Uppdaterad elbil får ny batterikonstruktion i Europa", "title_fact_ids": ["f0", "f1"],
        "intro": "Tillverkaren har presenterat en uppdaterad elbil för europeiska kunder. En ny batterikonstruktion ska ge bättre effektivitet i vardagen, medan beställningarna väntas öppna senare under året.", "intro_fact_ids": ["f0", "f1", "f2"],
        "paragraphs": [
            {"text": "Beskedet gäller den europeiska marknaden. Tillverkaren kopplar uppdateringen till förbättrad effektivitet vid vanlig körning och beskriver batteriets konstruktion som en del av förändringen. Presentationen ger därmed en första bild av vad som står i fokus när modellen uppdateras. Beställningarna ska enligt beskedet öppna senare under året, vilket är nästa angivna steg för europeiska kunder.", "fact_ids": ["f0", "f1", "f2"], "kind": "reporting"},
            {"text": "För svenska elbilsköpare kan utvecklingen vara relevant när fler europeiska alternativ jämförs. Effektivitet är en aspekt att väga in, men det går ännu inte att dra slutsatser om vilken bil som passar bäst enbart utifrån presentationen. Den som överväger modellen kan därför invänta mer konkret information inför beställningsstarten. Ett framtida bilval behöver också utgå från de egna behoven och vilka uppgifter som faktiskt finns tillgängliga för den aktuella versionen.", "fact_ids": ["f0", "f1", "f2"], "kind": "analysis"},
        ],
    }


def audit(facts=None):
    facts = facts or extraction()["facts"]
    return {"swedish_quality": True, "original_expression": True, "swedish_relevance": True, "event_consistent": True,
            "no_invented_quotes": True, "no_unsupported_claims": True, "reasons": [],
            "facts": [{"id": f["id"], "supported": True, "central": bool(f.get("central")), "reason": "Supported by evidence", "corroborating_fact_ids": [f["id"]]} for f in facts],
            "blocks": [{"id": b, "supported": True, "reason": "Supported",
                        "verdict": 'grounded_question' if b == 'p1' else 'evidence_supported',
                        "unsupported_claims": []} for b in ("title", "intro", "p0", "p1")]}


def keyed_audit(value):
    return {**value, 'facts': {f['id']: {k: v for k, v in f.items() if k != 'id'} for f in value['facts']},
            'blocks': {b['id']: {k: v for k, v in b.items() if k != 'id'} for b in value['blocks']}}


def writer_result(value, context=None):
    reporting = [p for p in value['paragraphs'] if p['kind'] == 'reporting']
    question = next(p for p in value['paragraphs'] if p['kind'] == 'analysis')
    context = context or {}
    return {'title': value['title'], 'intro': value['intro'],
            'paragraphs': [p['text'] for p in reporting],
            'source_context': {key: block['text'] for key, block in context.items()},
            'buyer_question': question['text']}


class FeedTests(unittest.TestCase):
    def test_rss_atom_and_tracking_urls(self):
        rss = '<rss><channel><item><title>EV news</title><link>https://press.example.com/a?utm_source=x</link><pubDate>Thu, 15 Oct 2026 12:00:00 GMT</pubDate><description>EV details</description></item></channel></rss>'
        atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>EV news</title><link href="https://press.example.com/a"/><published>2026-10-15T12:00:00Z</published><summary>EV details</summary></entry></feed>'
        self.assertEqual(parse_feed(rss, SOURCE)[0]["url"], parse_feed(atom, SOURCE)[0]["url"])
        self.assertEqual(parse_feed(atom, SOURCE)[0]["published_at"], "2026-10-15T12:00:00+00:00")

    def test_rejects_non_feed_entities_and_cross_domain_links(self):
        for text in ('<html></html>', '<!DOCTYPE x><rss/>'):
            with self.assertRaises(ValueError): parse_feed(text, SOURCE)
        self.assertEqual(parse_feed('<rss><item><title>X</title><link>https://elsewhere.example/x</link></item></rss>', SOURCE), [])

    def test_url_and_tdm_reservations(self):
        for url in ('http://example.com', 'https://user:pass@example.com', 'file:///tmp/x', 'https://example.com:9000'):
            with self.assertRaises(ValueError): canonical_url(url)
        self.assertTrue(reserved({"TDM-Reservation": "1"}))
        self.assertTrue(reserved({}, '<meta content="1" name="tdm-reservation">'))
        self.assertTrue(reserved({"Content-Signal": "ai-input=no"}))
        self.assertFalse(reserved({}, '<article>Ordinary reporting</article>'))

    def test_collection_is_idempotent_and_failure_isolated(self):
        class FakeCollector:
            def fetch(self, url, source, conditional=None):
                if source["id"] == "broken": raise ValueError("robots_disallowed")
                return 200, {"ETag": "abc"}, '<rss><item><title>EV news</title><link>https://press.example.com/a</link></item></rss>', url
        with tempfile.TemporaryDirectory() as directory:
            store = NewsStore(Path(directory) / "news.sqlite")
            sources = [{**SOURCE, "id": "broken"}, SOURCE]
            first = collect(store, sources, FakeCollector(), force=True)
            second = collect(store, sources, FakeCollector(), force=True)
            self.assertEqual(first["new_items"], 1)
            self.assertEqual(second["new_items"], 0)
            self.assertEqual(first["sources"][0]["status"], "no_verified_feed")
            self.assertEqual(len(store.rows("news_items")), 1)
            store.close()

    def test_robots_denial_prevents_request(self):
        policy = RobotFileParser(); policy.parse(['User-agent: *', 'Disallow: /private'])
        collector = Collector()
        with patch.object(collector, 'policy', return_value=policy), patch.object(collector, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'robots_disallowed'):
                collector.fetch('https://press.example.com/private', SOURCE)
            request.assert_not_called()

    def test_article_body_preferred_over_navigation_and_related_cards(self):
        body = ' '.join(['original article content'] * 40)
        parser = PageText()
        parser.feed('<nav>menu</nav><article>' + body + '</article><aside>Different story</aside>')
        self.assertEqual(parser.plain(), body)
        self.assertNotIn('Different story', parser.plain())

    def test_metadata_classification_prioritizes_sweden_without_adding_specs(self):
        result = classify_metadata('Kia announces battery update for Sweden and Europe', '')
        self.assertEqual(result['brands'], ['Kia'])
        self.assertIn('Sweden', result['markets'])
        self.assertIn('battery', result['technology'])
        self.assertGreater(result['discovery_priority'], 0)
        self.assertNotIn('price', result)


class QualityTests(unittest.TestCase):
    def facts(self):
        return [{**f, "item_id": "item"} for f in extraction()["facts"]]

    def test_grounded_primary_article_passes(self):
        self.assertEqual(validate_fact_extraction(extraction(), item()), [])
        self.assertEqual(validate_article(draft(), self.facts(), [item()], audit(), 90), {"evidence": [], "editorial": [], "originality": []})

    def test_fabricated_evidence_and_numeric_claim_fail(self):
        e = extraction(); e["facts"][0]["evidence"] = "invented evidence with many words that are not in this source"
        self.assertIn("evidence_not_verbatim:f0", validate_fact_extraction(e, item()))
        d = draft(); d["intro"] += " Räckvidden är 999 kilometer."
        errors = validate_article(d, self.facts(), [item()], audit(), 90)
        self.assertIn("unsupported_numeric_claim:intro", errors["evidence"])

    def test_unsupported_attribution_audit_and_copying_fail(self):
        d = draft(); d["paragraphs"][0]["text"] += " " + CONTENT
        a = audit(); a["facts"].pop()
        errors = validate_article(d, self.facts(), [item()], a, 90)
        self.assertTrue(errors["originality"])
        self.assertIn("fact_audit_failed_or_incomplete", errors["evidence"])
        d = draft(); d["title_fact_ids"] = ["invented"]
        self.assertIn("unsupported_block:title", validate_article(d, self.facts(), [item()], audit(), 90)["evidence"])

    def test_single_publisher_and_low_relevance_fail(self):
        errors = validate_article(draft(), self.facts(), [item(kind="publisher")], audit(), 20)
        self.assertTrue(any("central_claim_needs_primary" in e for e in errors["evidence"]))
        self.assertIn("low_relevance_score", errors["editorial"])

    def test_matching_reports_from_distinct_publishers_can_corroborate(self):
        one = item(kind='publisher')
        two = {**item('second', kind='publisher'), 'source_id': 'different-publisher'}
        facts = self.facts() + [{**self.facts()[0], 'id': 'second-fact', 'item_id': 'second'}]
        a = audit(facts)
        a['facts'][0]['corroborating_fact_ids'] = ['f0', 'second-fact']
        a['facts'][-1]['corroborating_fact_ids'] = ['f0', 'second-fact']
        errors = validate_article(draft(), facts, [one, two], a, 90)
        self.assertEqual(errors['evidence'], [])

    def test_publishers_in_same_group_are_not_independent(self):
        one = item(kind='publisher'); one['payload']['publisher_group'] = 'same-group'
        two = {**item('second', kind='publisher'), 'source_id': 'different-publisher'}
        two['payload']['publisher_group'] = 'same-group'
        facts = self.facts() + [{**self.facts()[0], 'id': 'second-fact', 'item_id': 'second'}]
        a = audit(facts)
        for f in a['facts']: f['corroborating_fact_ids'] = ['f0', 'second-fact']
        errors = validate_article(draft(), facts, [one, two], a, 90)
        self.assertTrue(any('needs_primary_or_corroboration' in e for e in errors['evidence']))

    def test_inaccessible_source_cannot_be_used(self):
        source = item(); source['payload']['access_status'] = 'blocked'
        self.assertIn('inaccessible_evidence:f0', validate_article(draft(), self.facts(), [source], audit(), 90)['evidence'])

    def test_score_weights_and_missing_date(self):
        self.assertAlmostEqual(relevance_score({"sweden_relevance": 1, "significance": 1}, 1, DATE), 100, delta=.01)
        self.assertEqual(relevance_score(extraction(), .98, None), 0)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = NewsStore(Path(self.directory.name) / "news.sqlite")
        self.store.put("news_sources", {"id": SOURCE["id"], "payload": SOURCE})

    def tearDown(self):
        self.store.close(); self.directory.cleanup()

    def article(self):
        i = attach_cluster(self.store, item(), extraction())
        a = self.store.put("news_articles", {"id": "article", "cluster_id": i["cluster_id"], "slug": "en-elbilsnyhet", "status": "draft", "payload": draft(), "published_at": None})
        self.store.put("news_article_sources", {"id": "link", "article_id": a["id"], "item_id": i["id"], "payload": {"url": i["url"]}})
        return a

    def gates(self, article):
        for kind in ("evidence", "editorial", "originality"):
            self.store.put("news_quality_checks", {"id": kind, "article_id": article["id"], "kind": kind, "artifact_hash": article["artifact_hash"], "passed": True, "payload": {'policy_version': EDITORIAL_POLICY}})

    def test_no_publication_without_all_gates_or_with_stale_checks(self):
        a = self.article()
        with self.assertRaisesRegex(ValueError, "quality_gates"): self.store.publish(a["id"])
        self.gates(a)
        a["payload"]["title"] = "Annan rubrik som kräver ny kontroll"
        self.store.put("news_articles", a)
        with self.assertRaisesRegex(ValueError, "quality_gates"): self.store.publish(a["id"])
        self.assertEqual(self.store.public_articles(), [])

    def test_idempotent_publish_and_immutable_article(self):
        a = self.article(); self.gates(a); self.store.publish(a["id"]); self.store.publish(a["id"])
        self.assertEqual(len(self.store.public_articles()), 1)
        a["payload"]["title"] = "Edited after publication"
        with self.assertRaisesRegex(ValueError, "immutable"): self.store.put("news_articles", a)

    def test_duplicate_event_merges_publishers(self):
        a = attach_cluster(self.store, item(), extraction())
        b = attach_cluster(self.store, {**item("other"), "url": "https://press.example.com/another"}, extraction())
        self.assertEqual(a["cluster_id"], b["cluster_id"])
        self.assertEqual(len(self.store.rows("news_story_clusters")), 1)

    def test_ambiguous_nearby_event_is_quarantined(self):
        e = extraction(); e['brands'] = ['Testbrand']
        attach_cluster(self.store, item(), e)
        other = copy.deepcopy(e); other['event']['subject'] = 'another subject'
        def uncertain(name, schema, prompt): return {'certain': False, 'existing_cluster_id': '', 'reason': 'Ambiguous'}
        with self.assertRaisesRegex(ValueError, 'ambiguous_news_event_identity'):
            attach_cluster(self.store, {**item('other'), 'url': 'https://press.example.com/other'}, other, uncertain)
        self.assertEqual(len(self.store.rows('news_story_clusters')), 1)

    def test_daily_limit_and_public_export(self):
        a = self.article(); self.gates(a)
        with self.assertRaisesRegex(ValueError, "daily_limit"): self.store.publish(a["id"], daily_limit=0)
        path = Path(self.directory.name) / "public.json"
        self.assertEqual(export_public(self.store, path)["published"], 0)

    def test_end_to_end_editorial_and_repeat_are_idempotent(self):
        i = attach_cluster(self.store, item(), extraction())
        facts = [{**f, "id": i["id"] + ":f" + str(n), "item_id": i["id"]} for n, f in enumerate(extraction()["facts"])]
        def fake_ai(name, schema, prompt):
            if name == "swedish_ev_article":
                d = draft()
                d["title_fact_ids"] = ["item:f0", "item:f1"]
                d["intro_fact_ids"] = [f["id"] for f in facts]
                for p in d["paragraphs"]: p["fact_ids"] = [f["id"] for f in facts]
                return writer_result(d)
            return keyed_audit(audit(facts))
        with patch("news_engine.models_for_news", return_value={}):
            reports = editorial(self.store, ai=fake_ai)
            self.assertEqual(reports[0]["status"], "published", reports)
            self.assertEqual(editorial(self.store, ai=fake_ai), [])
        self.assertEqual(len(self.store.public_articles()), 1)
        path = Path(self.directory.name) / "public.json"
        export_public(self.store, path)
        public = json.loads(path.read_text(encoding="utf-8"))["records"][0]
        self.assertNotIn("input_fingerprint", public)
        self.assertNotIn("fact_ids", public["paragraphs"][0])

    def test_failed_editorial_does_not_publish(self):
        attach_cluster(self.store, item(), extraction())
        def broken(name, schema, prompt): raise RuntimeError('AI temporarily unavailable')
        with patch('news_engine.models_for_news', return_value={}):
            result = editorial(self.store, ai=broken)
        self.assertEqual(result[0]['status'], 'failed')
        self.assertEqual(self.store.public_articles(), [])
        self.assertEqual(self.store.rows('news_story_clusters')[0]['payload']['editorial_state'], 'quarantined')

    def test_news_only_queues_verification(self):
        a = self.article()
        cluster = self.store.get("news_story_clusters", a["cluster_id"])
        queue_verification(self.store, a, cluster, [{"key": "Kia|EV6", "brand": "Kia", "model": "EV6"}])
        queue_verification(self.store, a, cluster, [{"key": "Kia|EV6", "brand": "Kia", "model": "EV6"}])
        requests = self.store.rows("news_verification_requests")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["payload"]["source_policy"], "official_swedish_manufacturer_importer_only")


if __name__ == "__main__":
    unittest.main()
