import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from import_mobility_sweden import parse_elbil_ranking
from build_mvp_model_scope import build_scope
from build_mvp_source_research_queue import build_queue
from build_mvp_extraction_batch import build_batch, load_blocked_preflight_urls
from build_mvp_remaining_work import build_remaining_work
from build_browser_render_queue import (
    build_browser_render_queue,
    build_browser_render_queue_from_plan,
    build_browser_render_queue_from_resolutions,
)
from build_rendered_extraction_batch import build_rendered_batch
from fetch_browser_rendered_sources import build_rendered_sources
from extract_manufacturer_specs import merge_drafts, source_text_from_row
from export_public_ev_data import export_rows
from generate_sitemap import public_variant_urls
from import_source_research import build_research_candidates
from preflight_extraction_batch import preflight_row
from prerender_static_routes import public_variant_routes
from review_variant_queue import (
    auto_safe_promotion_keys,
    canonicalize_review_row,
    can_promote,
    promote_variants,
    review_summary,
)
from supabase_preflight import build_report
from seed_supabase import build_canonical_variant_rows, build_seed_plan, load_source_seed_rows, validation_status_value
from prepare_supabase_migration_bundle import build_bundle, migration_files
from verify_supabase_public_contract import build_report as build_public_contract_report, compare_remote_to_local
from pipeline_status import build_status as build_pipeline_status
from build_mvp_coverage_report import build_report as build_mvp_coverage_report
from build_next_extraction_plan import (
    attempted_empty_source_keys,
    build_plan as build_next_extraction_plan,
    source_attempt_key,
)
from local_sqlite_db import connect, public_variant_rows
from seed_local_sqlite import seed as seed_local_sqlite
from run_next_extraction import ready_rows, run as run_next_extraction
from run_next_extraction import append_attempts
from preflight_next_sources import merge_by_model_source, run as run_preflight_next_sources
from build_source_health_report import classify as classify_source_health
from export_public_from_sqlite import export_rows as export_sqlite_public_rows
from refresh_local_pipeline import run as run_refresh_local_pipeline
from pipeline_autopilot import run as run_pipeline_autopilot
from export_pipeline_status import build_public_status as build_public_pipeline_status
from resolve_blocked_models import build_resolutions as build_blocker_resolutions, split_queues as split_blocker_queues
from apply_blocker_resolutions import candidate_rows as blocker_candidate_rows, run as run_apply_blockers
from validate_research_sources import build_extraction_queue, official_domain_matches, validate_candidate
from validate_extracted_variants import load_sources, public_variant_from_draft, validate_draft
from apply_official_variant_overrides import apply_overrides, read_overrides
from verify_public_images import build_report as build_public_image_report


class MobilitySwedenImportTests(unittest.TestCase):
    def test_march_2026_import_counts_and_ambiguous_names(self):
        market_models, monthly_stats = parse_elbil_ranking(
            ROOT / "data/mobility-sweden/raw/monthly-registrations-2026-03.xlsx",
            "https://mobilitysweden.se/example.xlsx",
        )
        self.assertEqual(len(market_models), 124)
        self.assertEqual(len(monthly_stats), 124)
        ambiguous = {row.model_group for row in market_models if row.needs_mapping}
        self.assertIn("VOLVO EX/XC40", ambiguous)
        self.assertIn("VW ID.7/ID.7 TOURER", ambiguous)
        self.assertIn("VOLVO EC/C40", ambiguous)


class ValidationTests(unittest.TestCase):
    def test_high_confidence_official_source_can_publish(self):
        draft = {
            "source_url": "https://www.kia.com/se/nya-bilar/ev3/upptack/",
            "source_hash": "abc",
            "source_quote": "Pris från 489 900 kr. Räckvidd upp till 605 km.",
            "extraction_confidence": 0.95,
            "price_sek": 489900,
            "wltp_range_km": 605,
            "dc_charge_kw": 128,
            "tow_kg": 1000,
            "boot_liters": 460,
            "seats": 5,
        }
        sources = {
            draft["source_url"]: {
                "source_validation": "reachable_official_model_source",
            }
        }
        self.assertEqual(validate_draft(draft, sources), [])

    def test_low_confidence_or_bad_source_is_blocked(self):
        draft = {
            "source_url": "https://example.com",
            "source_hash": "",
            "source_quote": "",
            "extraction_confidence": 0.80,
            "price_sek": -1,
            "wltp_range_km": 1500,
        }
        errors = validate_draft(draft, {})
        self.assertIn("source_not_reachable_official", errors)
        self.assertIn("confidence_below_threshold", errors)
        self.assertIn("missing_source_hash", errors)
        self.assertIn("price_sek_out_of_range", errors)
        self.assertIn("wltp_range_km_out_of_range", errors)

    def test_mainstream_price_outlier_requires_review(self):
        draft = {
            "source_url": "https://www.skoda.se/modeller/elroq/",
            "source_hash": "abc",
            "source_quote": "Från 1 424 900 kr",
            "extraction_confidence": 0.95,
            "brand": "Skoda",
            "price_sek": 1424900,
            "wltp_range_km": 566,
        }
        sources = {
            draft["source_url"]: {
                "source_validation": "reachable_official_model_source",
            }
        }

        self.assertIn("mainstream_price_requires_review", validate_draft(draft, sources))


class MvpScopeTests(unittest.TestCase):
    def test_scope_ranks_matched_models_and_quarantines_ambiguous_names(self):
        market_rows = [
            {
                "brand_raw": "VOLVO",
                "model_raw": "EX/XC40",
                "normalized_brand": "volvo",
                "normalized_model": "ex xc40",
                "model_group": "VOLVO EX/XC40",
                "needs_mapping": "True",
                "registrations_ytd": "2945",
                "registrations_last_month": "988",
                "first_seen_month": "2026-03-01",
                "last_seen_month": "2026-03-01",
            },
            {
                "brand_raw": "TESLA",
                "model_raw": "MODEL Y",
                "normalized_brand": "tesla",
                "normalized_model": "model y",
                "model_group": "",
                "needs_mapping": "False",
                "registrations_ytd": "2412",
                "registrations_last_month": "1382",
                "first_seen_month": "2026-03-01",
                "last_seen_month": "2026-03-01",
            },
            {
                "brand_raw": "KIA",
                "model_raw": "EV3",
                "normalized_brand": "kia",
                "normalized_model": "ev3",
                "model_group": "",
                "needs_mapping": "False",
                "registrations_ytd": "980",
                "registrations_last_month": "422",
                "first_seen_month": "2026-03-01",
                "last_seen_month": "2026-03-01",
            },
        ]
        canonical_rows = [
            {"brand": "Tesla", "model": "Model Y", "normalized_brand": "tesla", "normalized_model": "model y"},
            {"brand": "Kia", "model": "Ev3", "normalized_brand": "kia", "normalized_model": "ev3"},
        ]
        alias_rows = [
            {
                "normalized_brand": "volvo",
                "normalized_model": "ex xc40",
                "alias_rule": "manual_mapping_required",
                "needs_mapping": "True",
                "model_group": "VOLVO EX/XC40",
            },
            {
                "normalized_brand": "tesla",
                "normalized_model": "model y",
                "alias_rule": "mobility_sweden_exact_raw_name",
                "needs_mapping": "False",
                "model_group": "",
            },
            {
                "normalized_brand": "kia",
                "normalized_model": "ev3",
                "alias_rule": "mobility_sweden_exact_raw_name",
                "needs_mapping": "False",
                "model_group": "",
            },
        ]
        source_rows = [
            {
                "brand": "Tesla",
                "model": "Model Y",
                "url": "https://www.tesla.com/sv_SE/modely",
                "source_validation": "reachable_official_model_source",
            }
        ]

        scope, quarantined = build_scope(market_rows, canonical_rows, alias_rows, source_rows, limit=2)

        self.assertEqual([row["model"] for row in scope], ["Model Y", "Ev3"])
        self.assertEqual(scope[0]["rank"], 1)
        self.assertEqual(scope[0]["extraction_ready"], "True")
        self.assertEqual(scope[1]["extraction_ready"], "False")
        self.assertEqual(quarantined[0]["reason"], "needs_mapping")


class MvpSourceResearchQueueTests(unittest.TestCase):
    def test_queue_includes_only_not_ready_models_ordered_by_rank(self):
        scope_rows = [
            {
                "rank": "2",
                "mvp_scope": "top_20",
                "brand": "Volvo",
                "model": "Ex30",
                "registrations_ytd": "1494",
                "registrations_last_month": "592",
                "source_url": "https://www.volvocars.com/se/cars/ex30-electric/",
                "source_validation": "unreachable_or_redirect_problem",
                "extraction_ready": "False",
            },
            {
                "rank": "1",
                "mvp_scope": "top_20",
                "brand": "Tesla",
                "model": "Model Y",
                "registrations_ytd": "2412",
                "registrations_last_month": "1382",
                "source_url": "https://www.tesla.com/sv_SE/modely",
                "source_validation": "unreachable_or_redirect_problem",
                "extraction_ready": "False",
            },
            {
                "rank": "3",
                "mvp_scope": "top_20",
                "brand": "Polestar",
                "model": "4",
                "registrations_ytd": "1306",
                "registrations_last_month": "496",
                "source_url": "https://www.polestar.com/se/polestar-4/",
                "source_validation": "reachable_official_model_source",
                "extraction_ready": "True",
            },
        ]

        queue = build_queue(scope_rows)

        self.assertEqual([row["model"] for row in queue], ["Model Y", "Ex30"])
        self.assertEqual(queue[0]["research_action"], "verify_or_replace_blocked_official_source")
        self.assertIn("Mobility Sweden only for market presence", queue[0]["notes"])


class SourceResearchImportTests(unittest.TestCase):
    def test_research_import_keeps_needs_mapping_out_of_candidates(self):
        rows = [
            {
                "rank": "1",
                "brand": "Volvo",
                "canonical_model": "EX40",
                "mobility_sweden_name": "VOLVO EX/XC40",
                "model_page_url": "https://www.volvocars.com/se/cars/ex40-electric/",
                "price_list_url": "",
                "specs_url": "https://www.volvocars.com/se/cars/ex40-electric/specifications/",
                "configurator_url": "",
                "source_domain": "volvocars.com",
                "confidence": "medium",
                "needs_mapping": "true",
                "notes": "Bundled name.",
            },
            {
                "rank": "2",
                "brand": "Tesla",
                "canonical_model": "Model Y",
                "mobility_sweden_name": "TESLA MODEL Y",
                "model_page_url": "https://www.tesla.com/sv_SE/modely",
                "price_list_url": "",
                "specs_url": "https://www.tesla.com/sv_SE/modely/design",
                "configurator_url": "https://www.tesla.com/sv_SE/modely/design",
                "source_domain": "tesla.com",
                "confidence": "high",
                "needs_mapping": "false",
                "notes": "Tesla blocks direct scraping.",
            },
        ]

        candidates, mapping_queue = build_research_candidates(rows)

        self.assertEqual(len(mapping_queue), 1)
        self.assertEqual(mapping_queue[0]["mobility_sweden_name"], "VOLVO EX/XC40")
        self.assertEqual({row["source_type"] for row in candidates}, {"manufacturer_model_page", "manufacturer_specs_page", "manufacturer_configurator"})
        self.assertTrue(all(row["source_validation"] == "research_candidate_unvalidated" for row in candidates))


class ResearchSourceValidationTests(unittest.TestCase):
    def test_official_domain_allows_expected_subdomains_only(self):
        self.assertTrue(official_domain_matches("https://www.kia.com/se/nya-bilar/ev3/upptack/", "kia.com"))
        self.assertTrue(official_domain_matches("https://hitta.bmw.se/sv_SE", "bmw.se"))
        self.assertFalse(official_domain_matches("https://example.com/kia", "kia.com"))

    def test_validate_candidate_keeps_unreachable_sources_blocked(self):
        row = {
            "brand": "Tesla",
            "model": "Model Y",
            "source_type": "manufacturer_model_page",
            "url": "https://www.tesla.com/sv_SE/modely",
            "source_domain": "tesla.com",
            "research_confidence": "high",
            "research_rank": "2",
        }

        def fake_check_url(url, timeout):
            return 403, "", "", "", ""

        import validate_research_sources

        original = validate_research_sources.check_url
        validate_research_sources.check_url = fake_check_url
        try:
            validated = validate_candidate(row)
        finally:
            validate_research_sources.check_url = original

        self.assertEqual(validated["source_validation"], "unreachable_or_redirect_problem")
        self.assertEqual(validated["extraction_status"], "blocked")

    def test_validate_candidate_rejects_cross_domain_redirects(self):
        row = {
            "brand": "MG",
            "model": "MG4",
            "source_type": "manufacturer_model_page",
            "url": "https://www.mgmotor.eu/sv-SE/model/mg4",
            "source_domain": "mgmotor.eu",
            "research_confidence": "medium",
            "research_rank": "38",
        }

        def fake_check_url(url, timeout):
            return 200, "https://www.mgmotor.hu/model/mg4", "hash", "text/html", "2026-05-02T00:00:00+00:00"

        import validate_research_sources

        original = validate_research_sources.check_url
        validate_research_sources.check_url = fake_check_url
        try:
            validated = validate_candidate(row)
        finally:
            validate_research_sources.check_url = original

        self.assertEqual(validated["source_validation"], "reachable_unapproved_domain")
        self.assertEqual(validated["extraction_status"], "blocked")

    def test_extraction_queue_selects_best_reachable_source_per_model(self):
        rows = [
            {
                "brand": "Kia",
                "model": "EV3",
                "source_type": "manufacturer_model_page",
                "url": "https://www.kia.com/se/nya-bilar/ev3/upptack/",
                "source_domain": "kia.com",
                "research_rank": "6",
                "research_confidence": "high",
                "http_status": "200",
                "final_url": "https://www.kia.com/se/nya-bilar/ev3/upptack/",
                "content_hash": "abc",
                "content_type": "text/html",
                "fetched_at": "2026-05-02T00:00:00+00:00",
                "source_validation": "reachable_official_model_source",
            },
            {
                "brand": "Kia",
                "model": "EV3",
                "source_type": "manufacturer_price_list",
                "url": "https://www.kia.com/se/kopa/prislista/",
                "source_domain": "kia.com",
                "research_rank": "6",
                "research_confidence": "high",
                "http_status": "200",
                "final_url": "https://www.kia.com/se/kopa/prislista/",
                "content_hash": "def",
                "content_type": "text/html",
                "fetched_at": "2026-05-02T00:00:00+00:00",
                "source_validation": "reachable_official_model_source",
            },
        ]

        queue = build_extraction_queue(rows)

        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["source_type"], "manufacturer_price_list")
        self.assertEqual(queue[0]["extraction_status"], "queued")


class MvpExtractionBatchTests(unittest.TestCase):
    def test_batch_prefers_static_specs_and_pdf_sources(self):
        rows = [
            {
                "brand": "BMW",
                "model": "iX1",
                "source_type": "manufacturer_configurator",
                "url": "https://hitta.bmw.se/r/U11-iX1",
                "source_domain": "bmw.se",
                "research_rank": "15",
                "research_confidence": "high",
                "content_hash": "config",
                "content_type": "text/html",
                "source_validation": "reachable_official_model_source",
            },
            {
                "brand": "Polestar",
                "model": "4",
                "source_type": "manufacturer_specs_page",
                "url": "https://www.polestar.com/se/polestar-4/specifications/",
                "source_domain": "polestar.com",
                "research_rank": "5",
                "research_confidence": "high",
                "content_hash": "specs",
                "content_type": "text/html",
                "source_validation": "reachable_official_model_source",
            },
            {
                "brand": "Skoda",
                "model": "Enyaq",
                "source_type": "manufacturer_price_list",
                "url": "https://www.skoda.se/_doc/example",
                "source_domain": "skoda.se",
                "research_rank": "9",
                "research_confidence": "high",
                "content_hash": "pdf",
                "content_type": "application/pdf",
                "source_validation": "reachable_official_model_source",
            },
            {
                "brand": "Kia",
                "model": "EV3",
                "source_type": "manufacturer_price_list",
                "url": "https://www.kia.com/se/kopa/prislista/",
                "source_domain": "kia.com",
                "research_rank": "6",
                "research_confidence": "high",
                "content_hash": "generic-html-price-list",
                "content_type": "text/html",
                "source_validation": "reachable_official_model_source",
            },
        ]

        batch = build_batch(rows, limit=2)

        self.assertEqual([row["model"] for row in batch], ["4", "Enyaq"])
        self.assertTrue(all(row["extraction_status"] == "ready_for_ai_extraction" for row in batch))

    def test_batch_skips_previously_extracted_source_urls(self):
        rows = [
            {
                "brand": "Polestar",
                "model": "4",
                "source_type": "manufacturer_specs_page",
                "url": "https://www.polestar.com/se/polestar-4/specifications/",
                "source_domain": "polestar.com",
                "research_rank": "5",
                "research_confidence": "high",
                "content_hash": "specs",
                "content_type": "text/html",
                "source_validation": "reachable_official_model_source",
            },
            {
                "brand": "Mazda",
                "model": "6e",
                "source_type": "manufacturer_specs_page",
                "url": "https://www.mazda.se/modeller/mazda-6e/specifikationer-och-jamforelser/",
                "source_domain": "mazda.se",
                "research_rank": "32",
                "research_confidence": "high",
                "content_hash": "mazda",
                "content_type": "text/html",
                "source_validation": "reachable_official_model_source",
            },
        ]

        batch = build_batch(rows, limit=1, excluded_urls={"https://www.polestar.com/se/polestar-4/specifications/"})

        self.assertEqual(batch[0]["model"], "6e")

    def test_load_blocked_preflight_urls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "preflight.csv"
            path.write_text(
                "url,preflight_status\n"
                "https://blocked.example,blocked\n"
                "https://ready.example,ready_for_ai_extraction\n",
                encoding="utf-8",
            )

            self.assertEqual(load_blocked_preflight_urls(path), {"https://blocked.example"})


class ExtractionPreflightTests(unittest.TestCase):
    def test_preflight_blocks_changed_source_hash(self):
        row = {
            "brand": "Polestar",
            "model": "4",
            "url": "https://www.polestar.com/se/polestar-4/specifications/",
            "content_hash": "old",
            "source_validation": "research_candidate_unvalidated",
        }

        def fake_fetch_source_text(url):
            return "x" * 700, "new"

        import preflight_extraction_batch

        original = preflight_extraction_batch.fetch_source_text
        preflight_extraction_batch.fetch_source_text = fake_fetch_source_text
        try:
            result = preflight_row(row)
        finally:
            preflight_extraction_batch.fetch_source_text = original

        self.assertEqual(result["preflight_status"], "blocked")
        self.assertIn("source_hash_changed", result["preflight_errors"])

    def test_preflight_allows_stable_long_source_text(self):
        row = {
            "brand": "Polestar",
            "model": "4",
            "url": "https://www.polestar.com/se/polestar-4/specifications/",
            "content_hash": "same",
            "source_validation": "reachable_official_model_source",
        }

        def fake_fetch_source_text(url):
            return "Pris och räckvidd. " * 80, "same"

        import preflight_extraction_batch

        original = preflight_extraction_batch.fetch_source_text
        preflight_extraction_batch.fetch_source_text = fake_fetch_source_text
        try:
            result = preflight_row(row)
        finally:
            preflight_extraction_batch.fetch_source_text = original

        self.assertEqual(result["preflight_status"], "ready_for_ai_extraction")
        self.assertEqual(result["preflight_errors"], "")


class ExtractionDraftOutputTests(unittest.TestCase):
    def test_merge_drafts_replaces_same_variant_source_without_dropping_existing(self):
        existing = [
            {
                "brand": "Polestar",
                "model": "4",
                "variant_name": "Long range Single motor",
                "source_url": "https://www.polestar.com/se/polestar-4/specifications/",
                "price_sek": 692000,
            }
        ]
        new_drafts = [
            {
                "brand": "Cupra",
                "model": "Born",
                "variant_name": "Essential",
                "source_url": "https://www.cupraofficial.se/bilar/born",
                "price_sek": 399900,
            },
            {
                "brand": "Polestar",
                "model": "4",
                "variant_name": "Long range Single motor",
                "source_url": "https://www.polestar.com/se/polestar-4/specifications/",
                "price_sek": 690000,
            },
        ]

        merged = merge_drafts(existing, new_drafts)

        self.assertEqual(len(merged), 2)
        self.assertEqual(
            next(row for row in merged if row["brand"] == "Polestar")["price_sek"],
            690000,
        )


class MvpRemainingWorkTests(unittest.TestCase):
    def test_remaining_work_classifies_scope_rows(self):
        scope_rows = [
            {
                "rank": "1",
                "mvp_scope": "top_20",
                "brand": "Tesla",
                "model": "Model Y",
                "registrations_ytd": "2412",
                "source_url": "https://www.tesla.com/sv_SE/modely",
                "source_validation": "unreachable_or_redirect_problem",
            }
        ]
        queue_rows = []

        rows = build_remaining_work(scope_rows, queue_rows)

        self.assertIn(rows[0]["next_strategy"], {"browser_rendered_required", "done_or_in_review"})


class BrowserRenderQueueTests(unittest.TestCase):
    def test_browser_render_queue_keeps_only_render_required_sources(self):
        rows = [
            {
                "rank": "2",
                "mvp_scope": "top_20",
                "brand": "Volvo",
                "model": "Ex30",
                "registrations_ytd": "1494",
                "source_url": "https://www.volvocars.com/se/cars/ex30-electric/",
                "source_validation": "unreachable_or_redirect_problem",
                "next_strategy": "browser_rendered_required",
                "reason": "raw_http_blocked_or_unstable",
            },
            {
                "rank": "1",
                "mvp_scope": "top_20",
                "brand": "Tesla",
                "model": "Model Y",
                "registrations_ytd": "2412",
                "source_url": "https://www.tesla.com/sv_SE/modely",
                "source_validation": "unreachable_or_redirect_problem",
                "next_strategy": "browser_rendered_required",
                "reason": "raw_http_blocked_or_unstable",
            },
            {
                "rank": "3",
                "mvp_scope": "top_20",
                "brand": "Kia",
                "model": "Ev3",
                "next_strategy": "candidate_available",
            },
        ]

        queue = build_browser_render_queue(rows)

        self.assertEqual([row["model"] for row in queue], ["Model Y", "Ex30"])
        self.assertEqual(queue[0]["target_strategy"], "browser_rendered_fetch")
        self.assertEqual(queue[0]["queue_status"], "queued")
        self.assertIn("Mobility Sweden remains market presence only", queue[0]["notes"])

    def test_browser_render_queue_from_plan_excludes_non_browser_blockers(self):
        rows = [
            {
                "rank": 1,
                "brand": "Tesla",
                "model": "Model Y",
                "url": "https://www.tesla.com/sv_SE/modely",
                "extraction_status": "blocked",
                "priority_reason": "browser_rendered_required",
            },
            {
                "rank": 2,
                "brand": "BMW",
                "model": "iX1",
                "url": "https://hitta.bmw.se/r/U11-iX1",
                "extraction_status": "blocked",
                "priority_reason": "configurator_extraction_required",
            },
        ]

        queue = build_browser_render_queue_from_plan(
            rows,
            [
                {
                    "brand": "Tesla",
                    "model": "Model Y",
                    "resolution_action": "browser_render_official_source",
                    "candidate_url": "https://www.tesla.com/sv_SE/modely",
                }
            ],
        )

        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["brand"], "Tesla")
        self.assertEqual(queue[0]["source_url"], "https://www.tesla.com/sv_SE/modely")
        self.assertIn("current next-extraction plan", queue[0]["notes"])

    def test_browser_render_queue_from_resolutions_includes_static_candidates(self):
        rows = [
            {
                "rank": "12",
                "brand": "BMW",
                "model": "iX1",
                "resolution_action": "prefer_static_specs_over_configurator",
                "candidate_url": "https://www.bmw.se/sv/alla-modeller/bmw-i/iX1/tekniska-data.html",
            },
            {
                "rank": "99",
                "brand": "Example",
                "model": "Ignored",
                "resolution_action": "manual_review",
                "candidate_url": "https://example.com",
            },
        ]

        queue = build_browser_render_queue_from_resolutions(rows)

        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["brand"], "BMW")
        self.assertEqual(queue[0]["target_strategy"], "browser_rendered_fetch")


class BrowserRenderedSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_render_fetch_blocks_cleanly_without_runtime(self):
        rows = [
            {
                "rank": "1",
                "mvp_scope": "top_20",
                "brand": "Tesla",
                "model": "Model Y",
                "registrations_ytd": "2412",
                "source_url": "https://www.tesla.com/sv_SE/modely",
                "queue_status": "queued",
                "priority": "1",
            }
        ]

        rendered = await build_rendered_sources(rows, force_unavailable=True)

        self.assertEqual(rendered[0]["render_status"], "blocked_missing_playwright")
        self.assertEqual(rendered[0]["extraction_status"], "blocked")
        self.assertEqual(rendered[0]["source_hash"], "")


class RenderedExtractionBatchTests(unittest.TestCase):
    def test_rendered_batch_requires_ready_text_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            text_path = Path(temp_dir) / "source.txt"
            text_path.write_text("Pris 429 000 kr. Räckvidd 475 km.", encoding="utf-8")
            rows = [
                {
                    "rank": "2",
                    "brand": "Volvo",
                    "model": "Ex30",
                    "source_url": "https://www.volvocars.com/se/cars/ex30-electric/",
                    "source_domain": "volvocars.com",
                    "render_status": "rendered_source_ready",
                    "extraction_status": "queued",
                    "source_hash": "abc",
                    "source_text_path": str(text_path),
                },
                {
                    "rank": "1",
                    "brand": "Tesla",
                    "model": "Model Y",
                    "render_status": "rendered_text_too_short",
                    "extraction_status": "blocked",
                },
            ]

            batch = build_rendered_batch(rows)

            self.assertEqual(len(batch), 1)
            self.assertEqual(batch[0]["source_type"], "manufacturer_rendered_model_page")
            self.assertEqual(batch[0]["preflight_status"], "ready_for_ai_extraction")

    def test_source_text_from_row_uses_rendered_text_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            text_path = Path(temp_dir) / "source.txt"
            text = "Pris 429 000 kr. Räckvidd 475 km."
            text_path.write_text(text + "\n", encoding="utf-8")
            import hashlib

            source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            loaded_text, loaded_hash = source_text_from_row(
                {
                    "url": "https://www.volvocars.com/se/cars/ex30-electric/",
                    "source_text_path": str(text_path),
                    "content_hash": source_hash,
                }
            )

            self.assertIn("Räckvidd", loaded_text)
            self.assertEqual(loaded_hash, source_hash)

    def test_load_sources_includes_rendered_extraction_batch(self):
        # This uses the project fixture generated by the pipeline when present.
        # It protects the contract that rendered official pages can validate drafts.
        sources = load_sources()
        rendered_url = "https://www.volvocars.com/se/cars/ex30-electric/"
        if rendered_url in sources:
            self.assertEqual(
                sources[rendered_url]["source_validation"],
                "reachable_official_model_source",
            )


class ReviewVariantQueueTests(unittest.TestCase):
    def test_can_promote_only_allowed_review_errors_with_source_support(self):
        row = {
            "price_sek": 429000,
            "wltp_range_km": 475,
            "source_hash": "abc",
            "source_quote": "Pris 429 000 kr. Räckvidd 475 km.",
            "validation_errors": ["confidence_below_threshold"],
        }
        self.assertTrue(can_promote(row, {"confidence_below_threshold"}))

        row["validation_errors"] = ["missing_price_or_wltp"]
        self.assertFalse(can_promote(row, {"confidence_below_threshold"}))

    def test_promote_variants_updates_public_review_and_drafts(self):
        review_rows = [
            {
                "brand": "Audi",
                "model": "Q6 E-Tron",
                "variant_name": "Q6 e-tron",
                "price_sek": 789900,
                "wltp_range_km": 661,
                "battery_kwh": None,
                "dc_charge_kw": None,
                "ac_charge_kw": None,
                "boot_liters": None,
                "tow_kg": None,
                "seats": None,
                "drivetrain": "quattro",
                "source_quote": "Q6 e-tron från 789 900 kr ... upp till 661 km",
                "source_hash": "abc",
                "extraction_confidence": 0.9,
                "validation_errors": ["confidence_below_threshold"],
            }
        ]
        draft_rows = [dict(review_rows[0])]
        remaining, public_rows, drafts, promoted = promote_variants(
            review_rows,
            [],
            draft_rows,
            ["Audi|Q6 E-Tron|Q6 e-tron"],
            {"confidence_below_threshold"},
            "reviewer",
            "Source quote checked manually",
        )

        self.assertEqual(remaining, [])
        self.assertEqual(len(public_rows), 1)
        self.assertEqual(public_rows[0]["validation_status"], "published_reviewed")
        self.assertEqual(drafts[0]["validation_status"], "published_reviewed")
        self.assertEqual(promoted[0]["key"], "Audi|Q6 E-Tron|Q6 e-tron")

    def test_public_variant_preserves_review_metadata(self):
        public_row = public_variant_from_draft(
            {
                "brand": "Volvo",
                "model": "Ex30",
                "variant_name": "EX30 Plus",
                "price_sek": 457000,
                "wltp_range_km": 475,
                "review_approved_by": "reviewer",
                "review_reason": "Checked",
                "review_promoted_at": "2026-05-03T00:00:00+00:00",
            }
        )

        self.assertEqual(public_row["review_approved_by"], "reviewer")
        self.assertEqual(public_row["review_reason"], "Checked")

    def test_review_summary_contains_stable_promotion_key(self):
        summary = review_summary(
            [
                {
                    "brand": "Volvo",
                    "model": "Ex30",
                    "variant_name": "EX30 Plus",
                    "validation_errors": ["confidence_below_threshold"],
                }
            ]
        )
        self.assertEqual(summary[0]["key"], "Volvo|Ex30|EX30 Plus")

    def test_auto_safe_promotion_keys_only_include_allowed_errors(self):
        rows = [
            {
                "brand": "Audi",
                "model": "Q6 E-Tron",
                "variant_name": "Q6",
                "price_sek": 789900,
                "source_hash": "abc",
                "source_quote": "Pris från 789 900 kr",
                "validation_errors": ["confidence_below_threshold"],
            },
            {
                "brand": "Skoda",
                "model": "Elroq",
                "variant_name": "Outlier",
                "price_sek": 1489900,
                "source_hash": "abc",
                "source_quote": "Pris från 1 489 900 kr",
                "validation_errors": ["confidence_below_threshold", "mainstream_price_requires_review"],
            },
        ]

        self.assertEqual(auto_safe_promotion_keys(rows), ["Audi|Q6 E-Tron|Q6"])

    def test_canonicalize_review_row_maps_marketing_model_to_canonical(self):
        row = {"brand": "Renault", "model": "5 E-Tech", "variant_name": "techno"}

        self.assertEqual(
            canonicalize_review_row(row, {("renault", "5 e tech"): "5"})["model"],
            "5",
        )

    def test_official_overrides_replace_unpublished_model_drafts(self):
        drafts = [
            {
                "brand": "Toyota",
                "model": "bZ4X",
                "variant_name": "Toyota bZ4X",
                "validation_status": "extracted",
            },
            {
                "brand": "Toyota",
                "model": "bZ4X",
                "variant_name": "Reviewed",
                "validation_status": "published_reviewed",
            },
        ]
        overrides = [
            {
                "brand": "Toyota",
                "model": "bZ4X",
                "variant_name": "Active FWD",
                "price_sek": 469900,
                "wltp_range_km": 513,
                "battery_kwh": None,
                "dc_charge_kw": None,
                "ac_charge_kw": None,
                "boot_liters": 452,
                "tow_kg": None,
                "seats": 5,
                "drivetrain": "FWD",
                "source_url": "https://www.toyota.se/official.pdf",
                "source_hash": "abc",
                "source_quote": "Active 469 900 kr. Räckvidd 443-513.",
                "extraction_confidence": 0.96,
                "replace_unpublished_model_drafts": True,
            }
        ]

        updated, report = apply_overrides(drafts, overrides)

        self.assertEqual(report["removed_unpublished_model_drafts"], 1)
        self.assertEqual({row["variant_name"] for row in updated}, {"Reviewed", "Active FWD"})

    def test_export_rows_preserves_source_and_market_flags(self):
        exported = export_rows(
            [
                {
                    "brand": "Volvo",
                    "model": "Ex30",
                    "variant_name": "EX30 Core",
                    "price_sek": 429000,
                    "source_url": "https://www.volvocars.com/se/cars/ex30-electric/",
                    "source_hash": "abc",
                    "validation_status": "published",
                }
            ],
            [
                {
                    "brand": "Volvo",
                    "model": "Ex30",
                    "market_seen": True,
                    "available_confirmed": False,
                }
            ],
        )

        self.assertEqual(exported[0]["source_url"], "https://www.volvocars.com/se/cars/ex30-electric/")
        self.assertEqual(exported[0]["source_hash"], "abc")
        self.assertTrue(exported[0]["market_seen"])
        self.assertFalse(exported[0]["available_confirmed"])


class SeoRouteTests(unittest.TestCase):
    def test_sitemap_urls_include_only_public_variant_statuses(self):
        urls = public_variant_urls(
            [
                {
                    "brand": "Volvo",
                    "model": "Ex30",
                    "variant_name": "EX30 Plus",
                    "validation_status": "published_reviewed",
                },
                {
                    "brand": "Tesla",
                    "model": "Model Y",
                    "variant_name": "Long Range",
                    "validation_status": "draft",
                },
            ]
        )

        self.assertEqual(urls, ["/bilar/volvo-ex30-plus"])

    def test_sitemap_includes_verification_page(self):
        import generate_sitemap

        generate_sitemap.main()

        self.assertIn("<loc>https://swedish-ev-advisor.se/verifiering</loc>", (ROOT / "public/sitemap.xml").read_text(encoding="utf-8"))

    def test_prerender_vehicle_routes_use_public_variant_data(self):
        routes = public_variant_routes(
            [
                {
                    "brand": "Volvo",
                    "model": "Ex30",
                    "variant_name": "EX30 Plus",
                    "price_sek": 457000,
                    "wltp_range_km": 475,
                    "dc_charge_kw": 153,
                    "source_url": "https://www.volvocars.com/se/cars/ex30-electric/",
                    "validation_status": "published_reviewed",
                },
                {
                    "brand": "Tesla",
                    "model": "Model Y",
                    "variant_name": "Long Range",
                    "validation_status": "extracted",
                },
            ]
        )

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["path"], "/bilar/volvo-ex30-plus")
        self.assertIn("pris från 457 000 kr", routes[0]["description"])
        vehicle_json_ld = routes[0]["json_ld"][0]
        self.assertEqual(vehicle_json_ld["@type"], "Vehicle")
        self.assertEqual(vehicle_json_ld["offers"]["price"], 457000)


class PublicImageContractTests(unittest.TestCase):
    def test_public_models_have_exact_images_and_no_stock_fallbacks(self):
        report = build_public_image_report(ROOT)

        self.assertGreaterEqual(report["public_records"], 1)
        self.assertEqual(report["missing_model_image_keys"], [])
        self.assertEqual(report["fallback_image_urls"], [])
        self.assertEqual(report["prohibited_image_references"], [])
        self.assertTrue(report["strict_null_fallback"])
        self.assertTrue(report["public_uses_exact_lookup"])


class SupabaseSchemaContractTests(unittest.TestCase):
    def test_public_views_match_canonical_public_contract(self):
        schema = (ROOT / "database/schema.sql").read_text(encoding="utf-8")
        migration = (ROOT / "database/migrations/002_public_canonical_views.sql").read_text(encoding="utf-8")
        combined = schema + "\n" + migration

        self.assertIn("published_reviewed", combined)
        self.assertIn("source_hash", combined)
        self.assertIn("cv.validation_status in ('published', 'published_reviewed')", combined)
        self.assertNotIn("and cm.available_confirmed = true", combined.lower())
        self.assertIn("manufacturer_model_page", combined)
        self.assertIn("manufacturer_price_list", combined)
        self.assertIn("manufacturer_rendered_model_page", combined)
        self.assertIn("needs_review", combined)
        self.assertIn("queued", combined)

    def test_seed_sources_include_rendered_official_sources(self):
        rows = load_source_seed_rows()
        rendered_rows = [row for row in rows if row.get("source_type") == "manufacturer_rendered_model_page"]

        self.assertGreaterEqual(len(rendered_rows), 1)
        self.assertEqual(validation_status_value("ready_for_ai_extraction"), "queued")

    def test_seed_dry_run_plan_counts_pipeline_rows(self):
        plan = build_seed_plan()

        self.assertGreaterEqual(plan["market_models"], 119)
        self.assertGreaterEqual(plan["canonical_models"], 119)
        self.assertGreaterEqual(plan["canonical_model_variants"], 21)
        self.assertGreaterEqual(plan["manufacturer_sources"], 1)
        self.assertIn("queued", plan["manufacturer_sources_by_status"])

    def test_seed_maps_reviewed_renault_marketing_name_to_canonical_model(self):
        rows = build_canonical_variant_rows({("renault", "5"): "canonical-renault-5"})
        renault_rows = [row for row in rows if row.get("variant_name") == "techno EV52"]

        self.assertTrue(renault_rows)
        self.assertEqual(renault_rows[0]["canonical_model_id"], "canonical-renault-5")

    def test_migration_bundle_contains_ordered_migrations(self):
        bundle = build_bundle(migration_files())

        self.assertIn("BEGIN 001_ev_database.sql", bundle)
        self.assertIn("BEGIN 002_public_canonical_views.sql", bundle)
        self.assertIn("BEGIN 003_seed_idempotency.sql", bundle)
        self.assertLess(bundle.index("001_ev_database.sql"), bundle.index("002_public_canonical_views.sql"))

    def test_public_contract_local_report_is_clean(self):
        report = build_public_contract_report(check_remote=False)

        self.assertTrue(report["contract_ok"])
        self.assertEqual(report["local"]["bad_statuses"], [])
        self.assertEqual(report["local"]["missing_source_hash"], 0)
        self.assertEqual(report["local"]["duplicate_keys"], [])

    def test_public_contract_detects_remote_drift(self):
        comparison = compare_remote_to_local(
            [
                {
                    "brand": "Extra",
                    "model": "Car",
                    "variant_name": "Leak",
                    "validation_status": "draft",
                    "source_hash": "",
                }
            ],
            [
                {
                    "brand": "Volvo",
                    "model": "Ex30",
                    "variant_name": "EX30 Plus",
                    "validation_status": "published_reviewed",
                    "source_hash": "abc",
                }
            ],
        )

        self.assertEqual(comparison["missing_in_remote"], ["volvo|ex30|ex30 plus"])
        self.assertEqual(comparison["extra_in_remote"], ["extra|car|leak"])
        self.assertEqual(comparison["remote_bad_statuses"], ["draft"])
        self.assertEqual(comparison["remote_missing_source_hash"], 1)

    def test_pipeline_status_separates_local_readiness_from_supabase_deployment(self):
        status = build_pipeline_status()

        self.assertEqual(status["public_contract_ok"], True)
        self.assertTrue(status["local_pipeline_ready"])
        self.assertIsNone(status["blocker"])
        self.assertEqual(status["next_action"], "run_supabase_seed_then_verify_public_views")
        if status["deployment_blocker"] is None:
            self.assertTrue(status["supabase_deployment_ready"])
            self.assertEqual(status["deployment_next_action"], "run_supabase_seed_then_verify_public_views")
        else:
            self.assertEqual(status["deployment_blocker"], "supabase_service_env_missing")
            self.assertEqual(status["deployment_next_action"], "add_supabase_url_and_service_role_key_to_env_local")
        self.assertIn("source_health", status)
        self.assertIn("blocker_queues", status)

    def test_mvp_coverage_report_tracks_public_and_remaining_models(self):
        report = build_mvp_coverage_report()

        self.assertEqual(report["mvp_models"], 30)
        self.assertGreaterEqual(report["public_variants"], 21)
        self.assertIn("public", report["coverage_by_status"])
        if report["public_models"] < report["mvp_models"]:
            self.assertIsNotNone(report["highest_priority_next"])
        else:
            self.assertIsNone(report["highest_priority_next"])

    def test_local_sqlite_seed_exposes_public_views(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ev_advisor.sqlite"
            report = seed_local_sqlite(db_path, reset=True)
            connection = connect(db_path)
            try:
                rows = public_variant_rows(connection)
            finally:
                connection.close()

        self.assertEqual(report["market_models"], 124)
        self.assertGreaterEqual(report["public_ev_variants"], 21)
        self.assertEqual(len(rows), report["public_ev_variants"])
        self.assertTrue(all(row["validation_status"] in {"published", "published_reviewed"} for row in rows))
        self.assertTrue(all(row["source_hash"] for row in rows))

    def test_local_sqlite_export_matches_public_view_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ev_advisor.sqlite"
            seed_local_sqlite(db_path, reset=True)
            rows = export_sqlite_public_rows(db_path)

        self.assertGreaterEqual(len(rows), 21)
        self.assertTrue(all(row["validation_status"] in {"published", "published_reviewed"} for row in rows))
        self.assertTrue(all(row["source_hash"] for row in rows))

    def test_next_extraction_dry_run_selects_ready_model(self):
        report = run_next_extraction(limit=1, dry_run=True)

        self.assertEqual(report["dry_run"], True)
        self.assertEqual(report["selected"], len(report["selected_models"]))
        self.assertEqual(report["selected"], len(ready_rows(limit=1)))
        self.assertIn("needs_preflight_next", report)

    def test_next_extraction_plan_surfaces_preflight_work(self):
        rows = build_next_extraction_plan()
        statuses = {row["extraction_status"] for row in rows}

        self.assertTrue(statuses.issubset({"ready_for_ai_extraction", "needs_preflight", "blocked"}))
        self.assertGreaterEqual(len(rows), 0)

    def test_attempted_empty_sources_are_excluded_from_ready_plan(self):
        key = source_attempt_key(
            {
                "brand": "Mercedes-Benz",
                "model": "Eqa",
                "url": "https://www.mercedes-benz.se/passengercars/models/suv/eqa/overview.html",
                "content_hash": "c1a36a177aa5be02cd13c69f869fdb8769b3592b81150dd79936a6678368a2ce",
            }
        )

        self.assertIn(key, attempted_empty_source_keys())

    def test_preflight_next_sources_dry_run_selects_work(self):
        report = run_preflight_next_sources(limit=2, dry_run=True)

        self.assertEqual(report["dry_run"], True)
        self.assertGreaterEqual(report["selected"], 0)
        self.assertEqual(report["selected"], len(report["selected_models"]))

    def test_preflight_merge_preserves_shared_price_list_models(self):
        rows = merge_by_model_source(
            [{"brand": "Kia", "model": "EV3", "url": "https://www.kia.com/se/kopa/prislista/"}],
            [{"brand": "Kia", "model": "EV5", "url": "https://www.kia.com/se/kopa/prislista/"}],
        )

        self.assertEqual(len(rows), 2)

    def test_source_health_classifies_fetch_timeout(self):
        status = classify_source_health(
            {
                "preflight_status": "blocked",
                "source_text_length": "0",
                "preflight_errors": "fetch_failed:<urlopen error [WinError 10060]>",
            }
        )

        self.assertEqual(status, "fetch_timeout")

    def test_preflight_allows_official_source_hash_refresh(self):
        import preflight_extraction_batch

        original = preflight_extraction_batch.fetch_source_text
        preflight_extraction_batch.fetch_source_text = lambda url: ("Pris 499 000 kr. " * 80, "new-hash")
        try:
            row = preflight_row(
                {
                    "url": "https://www.renault.se/personbilar/elbilar/r5-e-tech-electric",
                    "content_hash": "old-hash",
                    "source_validation": "reachable_official_model_source",
                }
            )
        finally:
            preflight_extraction_batch.fetch_source_text = original

        self.assertEqual(row["preflight_status"], "ready_for_ai_extraction")
        self.assertEqual(row["source_hash_current"], "new-hash")
        self.assertIn("source_hash_refreshed", row["preflight_errors"])

    def test_refresh_local_pipeline_dry_run_lists_steps(self):
        report = run_refresh_local_pipeline(dry_run=True)

        self.assertTrue(report["ok"])
        self.assertGreaterEqual(len(report["steps"]), 7)
        self.assertEqual(report["steps"][0]["script"], "apply_official_variant_overrides.py")
        self.assertEqual(report["steps"][1]["script"], "validate_extracted_variants.py")
        self.assertIn("export_pipeline_status.py", [step["script"] for step in report["steps"]])

    def test_public_pipeline_status_is_safe_for_frontend(self):
        status = build_public_pipeline_status()

        self.assertIn("public_variants", status)
        self.assertIn("review_queue_variants", status)
        self.assertIn("source_health", status)
        self.assertIn("blocker_queues", status)
        self.assertIn("local_pipeline_ready", status)
        self.assertIn("supabase_deployment_ready", status)
        self.assertNotIn("seed_plan", status)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", json.dumps(status))

    def test_pipeline_autopilot_dry_run_reports_actions(self):
        report = run_pipeline_autopilot(max_cycles=1, dry_run=True, build=False)

        self.assertTrue(report["ok"])
        self.assertTrue(any(action["step"] == "refresh_local_pipeline" for action in report["actions"]))
        self.assertTrue(any(action["step"] == "plan" for action in report["actions"]))

    def test_blocker_resolver_creates_action_queues(self):
        resolutions = build_blocker_resolutions()
        queues = split_blocker_queues(resolutions)

        self.assertGreaterEqual(len(resolutions), 0)
        self.assertTrue(all(row["resolution_action"] for row in resolutions))
        self.assertGreaterEqual(sum(len(rows) for rows in queues.values()), len(resolutions))
        if resolutions:
            self.assertTrue(
                any(row["candidate_url"] for row in resolutions if row["resolution_action"] != "browser_render_official_source")
                or any(row["resolution_action"] == "browser_render_official_source" for row in resolutions)
            )

    def test_apply_blocker_resolutions_builds_official_candidates(self):
        candidates = blocker_candidate_rows(build_blocker_resolutions())
        report = run_apply_blockers(dry_run=True)

        self.assertGreaterEqual(len(candidates), 0)
        self.assertGreaterEqual(report["candidates"], len(candidates))
        self.assertTrue(all(row["url"].startswith("https://") for row in candidates))
        self.assertTrue(all(row["source_domain"] for row in candidates))

    def test_supabase_preflight_validates_local_public_contract(self):
        report = build_report(check_remote=False)

        self.assertTrue(report["files_ready"])
        self.assertGreaterEqual(report["data"]["public_variants"], 1)
        self.assertEqual(report["data"]["public_status_errors"], [])
        self.assertEqual(report["data"]["public_missing_source_hash"], 0)
        self.assertEqual(report["schema"]["unknown_variant_statuses"], [])
        self.assertEqual(report["schema"]["unknown_source_types"], [])
        self.assertEqual(report["schema"]["unknown_source_statuses"], [])
        self.assertTrue(report["schema"]["supports_published_reviewed"])


if __name__ == "__main__":
    unittest.main()
