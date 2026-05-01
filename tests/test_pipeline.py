import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from import_mobility_sweden import parse_elbil_ranking
from validate_extracted_variants import validate_draft


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


if __name__ == "__main__":
    unittest.main()
