import json
import os
import re
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SITE_URL = os.environ.get("SITE_URL", "https://swedish-ev-advisor.se").rstrip("/")
PUBLIC_STATUSES = {"published", "published_reviewed"}

SEGMENTS = {
    "familj": {
        "title": "Bästa elbilarna för familj | Elbilsguiden",
        "description": "Jämför verifierade elbilar för svenska familjer med fokus på lastutrymme, räckvidd, pris och vardagsbehov.",
    },
    "vinter": {
        "title": "Elbilar för vinter och längre resor | Elbilsguiden",
        "description": "Hitta elbilar som passar nordiskt väder, vinterkörning och längre resor med verifierade svenska källor.",
    },
    "dragkrok": {
        "title": "Elbilar med dragkrok | Elbilsguiden",
        "description": "Jämför elbilar med dragvikt för släp, cykelhållare och fritidsbehov på den svenska marknaden.",
    },
    "under-500000": {
        "title": "Elbilar under 500 000 kr | Elbilsguiden",
        "description": "Utforska verifierade elbilar i Sverige med prisnivå under 500 000 kr och tydliga kompromisser.",
    },
    "lang-rackvidd": {
        "title": "Elbilar med lång räckvidd | Elbilsguiden",
        "description": "Jämför elbilar med hög WLTP-räckvidd för pendling, semester och längre körning i Sverige.",
    },
}


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


def format_price(value) -> str:
    if value in (None, ""):
        return ""
    return f"{int(value):,}".replace(",", " ") + " kr"


def metric_property(name: str, value, unit: str = "") -> dict | None:
    if value in (None, ""):
        return None
    formatted = f"{value} {unit}".strip()
    return {"@type": "PropertyValue", "name": name, "value": formatted}


def inject_head(html: str, title: str, description: str, path: str, json_ld: dict | list[dict]) -> str:
    canonical = f"{SITE_URL}{path}"
    html = re.sub(r"<title>.*?</title>", f"<title>{escape(title)}</title>", html, count=1, flags=re.S)
    html = re.sub(
        r'<meta name="description" content=".*?"\s*/>',
        f'<meta name="description" content="{escape(description)}" />',
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(r'\s*<link rel="canonical" href=".*?"\s*/>', "", html, flags=re.S)
    html = re.sub(r'\s*<meta property="og:[^"]+" content=".*?"\s*/>', "", html, flags=re.S)
    html = re.sub(r'\s*<meta name="twitter:[^"]+" content=".*?"\s*/>', "", html, flags=re.S)
    html = re.sub(r'\s*<script type="application/ld\+json" data-prerender="page">.*?</script>', "", html, flags=re.S)
    payload = json.dumps(json_ld, ensure_ascii=False, separators=(",", ":")).replace("</script", "<\\/script")
    tags = (
        f'\n    <link rel="canonical" href="{escape(canonical)}" />'
        f'\n    <meta property="og:type" content="website" />'
        f'\n    <meta property="og:title" content="{escape(title)}" />'
        f'\n    <meta property="og:description" content="{escape(description)}" />'
        f'\n    <meta property="og:url" content="{escape(canonical)}" />'
        f'\n    <meta name="twitter:card" content="summary" />'
        f'\n    <meta name="twitter:title" content="{escape(title)}" />'
        f'\n    <meta name="twitter:description" content="{escape(description)}" />'
        f'\n    <script type="application/ld+json" data-prerender="page">{payload}</script>'
    )
    return html.replace("  </head>", f"{tags}\n  </head>", 1)


def write_route(path: str, html: str) -> None:
    if path == "/":
        target = DIST / "index.html"
    else:
        target = DIST / path.strip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")


def load_public_variants() -> list[dict]:
    public_path = ROOT / "public/data/public_ev_variants.json"
    if not public_path.exists():
        return []
    payload = json.loads(public_path.read_text(encoding="utf-8"))
    return payload.get("records", [])


def route_label(row: dict) -> str:
    return " ".join(
        part
        for part in [
            row.get("brand"),
            display_model_name(row.get("brand", ""), row.get("model", ""), row.get("variant_name", "")),
        ]
        if part
    )


def breadcrumb_json_ld(path: str, label: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Elbilsguiden", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": label, "item": f"{SITE_URL}{path}"},
        ],
    }


def item_list_json_ld(path: str, name: str, rows: list[dict]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "url": f"{SITE_URL}{path}",
        "numberOfItems": len(rows),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "url": f"{SITE_URL}/bilar/{slug(route_label(row))}",
                "name": route_label(row),
            }
            for index, row in enumerate(rows[:12], start=1)
        ],
    }


def segment_rows(route_slug: str, rows: list[dict]) -> list[dict]:
    public_rows = [row for row in rows if row.get("validation_status") in PUBLIC_STATUSES]
    if route_slug == "familj":
        return sorted(public_rows, key=lambda row: (int(row.get("boot_liters") or 0), int(row.get("seats") or 0), int(row.get("wltp_range_km") or 0)), reverse=True)
    if route_slug == "vinter":
        return sorted(public_rows, key=lambda row: ("fyr" in str(row.get("drivetrain") or "").lower(), int(row.get("wltp_range_km") or 0), int(row.get("dc_charge_kw") or 0)), reverse=True)
    if route_slug == "dragkrok":
        return sorted([row for row in public_rows if int(row.get("tow_kg") or 0) >= 1000], key=lambda row: int(row.get("tow_kg") or 0), reverse=True)
    if route_slug == "under-500000":
        return sorted([row for row in public_rows if row.get("price_sek") and int(row.get("price_sek")) <= 500000], key=lambda row: int(row.get("price_sek") or 9999999))
    if route_slug == "lang-rackvidd":
        return sorted([row for row in public_rows if int(row.get("wltp_range_km") or 0) >= 580], key=lambda row: int(row.get("wltp_range_km") or 0), reverse=True)
    return public_rows


def public_variant_routes(rows: list[dict]) -> list[dict]:
    routes = []
    for row in rows:
        if row.get("validation_status") not in PUBLIC_STATUSES:
            continue

        display_model = display_model_name(row.get("brand", ""), row.get("model", ""), row.get("variant_name", ""))
        name = " ".join(part for part in [row.get("brand"), display_model] if part)
        if not name:
            continue

        path = f"/bilar/{slug(name)}"
        price = format_price(row.get("price_sek"))
        wltp = row.get("wltp_range_km")
        description_parts = [name]
        if price:
            description_parts.append(f"pris från {price}")
        if wltp:
            description_parts.append(f"WLTP-räckvidd {wltp} km")
        description = ", ".join(description_parts) + ". Verifierade svenska källor och tydliga nyckeltal."

        properties = [
            metric_property("WLTP-räckvidd", row.get("wltp_range_km"), "km"),
            metric_property("DC-laddning", row.get("dc_charge_kw"), "kW"),
            metric_property("AC-laddning", row.get("ac_charge_kw"), "kW"),
            metric_property("Batteri", row.get("battery_kwh"), "kWh"),
            metric_property("Bagageutrymme", row.get("boot_liters"), "liter"),
            metric_property("Dragvikt", row.get("tow_kg"), "kg"),
            metric_property("Säten", row.get("seats")),
            metric_property("Källa", row.get("source_url")),
        ]

        json_ld = {
            "@context": "https://schema.org",
            "@type": "Vehicle",
            "name": name,
            "brand": {"@type": "Brand", "name": row.get("brand", "")},
            "model": row.get("model", ""),
            "url": f"{SITE_URL}{path}",
            "offers": {
                "@type": "Offer",
                "priceCurrency": "SEK",
                "price": row.get("price_sek"),
                "availability": "https://schema.org/InStock" if row.get("available_confirmed") else "https://schema.org/LimitedAvailability",
            },
            "additionalProperty": [item for item in properties if item],
        }

        routes.append(
            {
                "path": path,
                "title": f"{name} – pris, räckvidd och specs | Elbilsguiden",
                "description": description,
                "json_ld": [json_ld, breadcrumb_json_ld(path, name)],
            }
        )

    return routes


def main() -> None:
    source = DIST / "index.html"
    if not source.exists():
        raise SystemExit("Run the Vite build before prerendering routes.")

    base_html = source.read_text(encoding="utf-8")
    home = inject_head(
        base_html,
        "Elbilsguiden Sverige – hitta rätt elbil med AI",
        "Beskriv budget, körning och behov och få en shortlist med verifierade elbilar, tydliga kompromisser och källor.",
        "/",
        {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": "Elbilsguiden Sverige",
            "applicationCategory": "AutomotiveApplication",
            "operatingSystem": "Web",
            "url": SITE_URL,
        },
    )
    write_route("/", home)

    routes = [
        {
            "path": "/bilar",
            "title": "Jämför elbilar i Sverige | Elbilsguiden",
            "description": "Filtrera och jämför verifierade elbilar på den svenska marknaden med pris, räckvidd, laddning, dragvikt och källor.",
            "json_ld": {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Jämför elbilar i Sverige", "url": f"{SITE_URL}/bilar"},
        },
        {
            "path": "/jamfor",
            "title": "Jämför elbilar sida vid sida | Elbilsguiden",
            "description": "Skapa en beslutsrapport och jämför elbilar sida vid sida med AI-sammanfattning och verifierade nyckeltal.",
            "json_ld": {"@context": "https://schema.org", "@type": "WebPage", "name": "Jämför elbilar sida vid sida", "url": f"{SITE_URL}/jamfor"},
        },
        {
            "path": "/verifiering",
            "title": "Verifiering och datakvalitet | Elbilsguiden",
            "description": "Se hur Elbilsguiden använder Mobility Sweden, officiella svenska tillverkarkällor, AI-extraktion, validering och quarantine innan data visas publikt.",
            "json_ld": {"@context": "https://schema.org", "@type": "WebPage", "name": "Verifiering och datakvalitet", "url": f"{SITE_URL}/verifiering"},
        },
    ]
    public_rows = load_public_variants()
    routes.extend(
        {
            "path": f"/{route_slug}",
            "title": metadata["title"],
            "description": metadata["description"],
            "json_ld": [
                {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": metadata["title"].replace(" | Elbilsguiden", ""),
                    "description": metadata["description"],
                    "url": f"{SITE_URL}/{route_slug}",
                },
                item_list_json_ld(f"/{route_slug}", metadata["title"].replace(" | Elbilsguiden", ""), segment_rows(route_slug, public_rows)),
            ],
        }
        for route_slug, metadata in SEGMENTS.items()
    )
    routes.extend(public_variant_routes(public_rows))

    for route in routes:
        write_route(
            route["path"],
            inject_head(base_html, route["title"], route["description"], route["path"], route["json_ld"]),
        )

    print(f"Prerendered {len(routes) + 1} static route files in dist/")


if __name__ == "__main__":
    main()
