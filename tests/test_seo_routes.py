import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_sitemap
from generate_sitemap import public_variant_urls
from prerender_static_routes import public_variant_routes


class SeoRouteTests(unittest.TestCase):
    def test_sitemap_urls_include_only_public_variant_statuses(self):
        urls = public_variant_urls([
            {"brand": "Volvo", "model": "Ex30", "variant_name": "EX30 Plus", "validation_status": "published_reviewed"},
            {"brand": "Tesla", "model": "Model Y", "variant_name": "Long Range", "validation_status": "draft"},
        ])
        self.assertEqual(urls, ["/bilar/volvo-ex30-plus"])

    def test_sitemap_includes_verification_page(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(generate_sitemap, "ROOT", Path(folder)):
            generate_sitemap.main()
            self.assertIn(f"<loc>{generate_sitemap.SITE_URL}/verifiering</loc>",
                          (Path(folder) / "public/sitemap.xml").read_text(encoding="utf-8"))

    def test_prerender_vehicle_routes_use_public_variant_data(self):
        routes = public_variant_routes([
            {"brand": "Volvo", "model": "Ex30", "variant_name": "EX30 Plus", "price_sek": 457000,
             "wltp_range_km": 475, "dc_charge_kw": 153, "source_url": "https://www.volvocars.com/se/cars/ex30-electric/",
             "validation_status": "published_reviewed"},
            {"brand": "Tesla", "model": "Model Y", "variant_name": "Long Range", "validation_status": "extracted"},
        ])
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["path"], "/bilar/volvo-ex30-plus")
        self.assertIn("prisuppgift 457 000 kr", routes[0]["description"])
        vehicle = routes[0]["json_ld"][0]
        self.assertEqual(vehicle["@type"], "Vehicle")
        self.assertEqual(vehicle["offers"]["price"], 457000)

    def test_prerender_does_not_invent_offer_or_availability(self):
        row = {"brand": "Kia", "model": "Ev6", "variant_name": "RWD", "validation_status": "published"}
        self.assertNotIn("offers", public_variant_routes([row])[0]["json_ld"][0])
        for flag in (False, None, True):
            with self.subTest(available_confirmed=flag):
                vehicle = public_variant_routes([{**row, "price_sek": 600000, "available_confirmed": flag}])[0]["json_ld"][0]
                self.assertEqual(vehicle["offers"].get("availability"), "https://schema.org/InStock" if flag is True else None)

    def test_prerender_preserves_zero_and_price_expiry_not_missing_specs(self):
        row = {"brand": "Kia", "model": "Ev6", "variant_name": "RWD", "validation_status": "published",
               "price_sek": 600000, "price_valid_until": "2026-12-31", "tow_kg": 0, "dc_charge_kw": None}
        vehicle = public_variant_routes([row])[0]["json_ld"][0]
        self.assertEqual(vehicle["offers"]["priceValidUntil"], "2026-12-31")
        properties = {item["name"]: item["value"] for item in vehicle["additionalProperty"]}
        self.assertEqual(properties["Dragvikt"], "0 kg")
        self.assertNotIn("DC-laddning", properties)
