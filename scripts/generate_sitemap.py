import json
import os
import re
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
SITE_URL = os.environ.get("SITE_URL", "https://swedish-ev-advisor.se").rstrip("/")
SEGMENTS = ["familj", "vinter", "dragkrok", "under-500000", "lang-rackvidd"]
PUBLIC_STATUSES = {"published", "published_reviewed"}


def slug(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9åäö]+", "-", value)
    return value.strip("-")


def normalize_name_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_vehicle_name_key(value: str, brand: str = "") -> str:
    brand_key = normalize_name_token(brand)
    parts = re.sub(r"\b(suv|sportback|edition|advanced|business)\b", " ", str(value or "").lower())
    parts = re.sub(r"[^a-z0-9]+", " ", parts).split()
    return "".join(part for part in parts if normalize_name_token(part) != brand_key)


def strip_leading_brand(brand: str, value: str) -> str:
    brand_text = str(brand or "").strip()
    text = str(value or "").strip()
    if not brand_text:
        return text
    return re.sub(rf"^{re.escape(brand_text)}\s+", "", text, flags=re.IGNORECASE).strip()


def display_model_name(brand: str, model: str, variant_name: str) -> str:
    model_text = str(model or "").strip()
    variant_text = strip_leading_brand(brand, variant_name)
    if not variant_text:
        return model_text

    normalized_model = normalize_name_token(model_text)
    normalized_variant = normalize_name_token(variant_text)
    vehicle_model = normalize_vehicle_name_key(model_text, brand)
    vehicle_variant = normalize_vehicle_name_key(variant_text, brand)
    if (
        not normalized_model
        or normalized_variant == normalized_model
        or normalized_variant.startswith(normalized_model)
        or (vehicle_model and (vehicle_variant == vehicle_model or vehicle_variant.startswith(vehicle_model)))
    ):
        return variant_text
    return f"{model_text} {variant_text}".strip()


def public_variant_slug(row: dict) -> str:
    return slug(f"{row.get('brand', '')} {display_model_name(row.get('brand', ''), row.get('model', ''), row.get('variant_name', ''))}")


def public_variant_urls(rows: list[dict]) -> list[str]:
    urls = []
    for row in rows:
        if row.get("validation_status") not in PUBLIC_STATUSES:
            continue
        variant_slug = public_variant_slug(row)
        if variant_slug:
            urls.append(f"/bilar/{variant_slug}")
    return urls


def load_public_variants() -> list[dict]:
    public_path = ROOT / "public/data/public_ev_variants.json"
    if public_path.exists():
        payload = json.loads(public_path.read_text(encoding="utf-8"))
        return payload.get("records", [])

    variants_path = ROOT / "data/canonical/canonical_model_variants_seed.json"
    if variants_path.exists():
        return json.loads(variants_path.read_text(encoding="utf-8"))

    return []


def car_urls() -> list[str]:
    return public_variant_urls(load_public_variants())


def render_url(path: str, priority: str) -> str:
    today = date.today().isoformat()
    return (
        "  <url>\n"
        f"    <loc>{escape(SITE_URL + path)}</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        "    <changefreq>weekly</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>"
    )


def main() -> None:
    paths = ["/", "/bilar", "/jamfor", "/verifiering", *[f"/{segment}" for segment in SEGMENTS], *car_urls()]
    seen = []
    for path in paths:
        if path not in seen:
            seen.append(path)
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path in seen:
        priority = "1.0" if path == "/" else "0.9" if path in ("/bilar", "/jamfor") else "0.8"
        xml.append(render_url(path, priority))
    xml.append("</urlset>")
    public_dir = ROOT / "public"
    public_dir.mkdir(exist_ok=True)
    (public_dir / "sitemap.xml").write_text("\n".join(xml), encoding="utf-8")
    (public_dir / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    print(f"Wrote {len(seen)} URLs to public/sitemap.xml")


if __name__ == "__main__":
    main()
