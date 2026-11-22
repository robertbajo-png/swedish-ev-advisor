import json
from news_public import news_routes
from site_info import info_routes
from generate_sitemap import public_variant_slug
import os
import re
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SITE_URL = os.environ.get("SITE_URL", "https://elbilsagenten.se").rstrip("/")
PUBLIC_STATUSES = {"published", "published_reviewed"}

SEGMENTS = {
    "familj": {
        "title": "Bästa elbilarna för familj | Elbilsagenten",
        "description": "Jämför verifierade elbilar för svenska familjer med fokus på lastutrymme, räckvidd, pris och vardagsbehov.",
    },
    "vinter": {
        "title": "Elbilar för vinter och längre resor | Elbilsagenten",
        "description": "Hitta elbilar som passar nordiskt väder, vinterkörning och längre resor med verifierade svenska källor.",
    },
    "dragkrok": {
        "title": "Elbilar med dragkrok | Elbilsagenten",
        "description": "Jämför elbilar med dragvikt för släp, cykelhållare och fritidsbehov på den svenska marknaden.",
    },
    "under-500000": {
        "title": "Elbilar under 500 000 kr | Elbilsagenten",
        "description": "Utforska verifierade elbilar i Sverige med prisnivå under 500 000 kr och tydliga kompromisser.",
    },
    "lang-rackvidd": {
        "title": "Elbilar med lång räckvidd | Elbilsagenten",
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
    if brand == "Volkswagen" and model_text == "Id. Buzz":
        model_text = "ID. Buzz"
    label = re.sub(r"\s*\((?:lagerbil|best\u00e4llningsbil)(?:\s+[a-z0-9]+)?\)\s*$",
                   "", str(variant_name or ""), flags=re.IGNORECASE)
    variant_text = strip_leading_brand(brand, label)
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
    og_type = 'article' if any(item.get('@type') == 'NewsArticle' for item in (json_ld if isinstance(json_ld, list) else [json_ld])) else 'website'
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
        f'\n    <meta property="og:type" content="{og_type}" />'
        f'\n    <meta property="og:title" content="{escape(title)}" />'
        f'\n    <meta property="og:description" content="{escape(description)}" />'
        f'\n    <meta property="og:url" content="{escape(canonical)}" />'
        f'\n    <meta property="og:image" content="{escape(SITE_URL)}/media/elbilsguiden-share.png" />'
        f'\n    <meta property="og:image:width" content="1200" />'
        f'\n    <meta property="og:image:height" content="630" />'
        f'\n    <meta property="og:image:alt" content="Elbilsagenten – hitta elbilen som passar dig" />'
        f'\n    <meta name="twitter:card" content="summary_large_image" />'
        f'\n    <meta name="twitter:image" content="{escape(SITE_URL)}/media/elbilsguiden-share.png" />'
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
            {"@type": "ListItem", "position": 1, "name": "Elbilsagenten", "item": SITE_URL},
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
                "url": f"{SITE_URL}/bilar/{public_variant_slug(row)}",
                "name": route_label(row),
            }
            for index, row in enumerate(rows[:12], start=1)
        ],
    }


def segment_rows(route_slug: str, rows: list[dict]) -> list[dict]:
    public_rows = [row for row in rows if row.get("validation_status") in PUBLIC_STATUSES]
    if route_slug == "familj":
        return sorted([row for row in public_rows if int(row.get('boot_liters') or 0) >= 450 and int(row.get('seats') or 0) >= 5], key=lambda row: int(row.get('boot_liters') or 0), reverse=True)
    if route_slug == "vinter":
        return sorted([row for row in public_rows if 'fyr' in str(row.get('drivetrain') or '').lower()], key=lambda row: int(row.get('wltp_range_km') or 0), reverse=True)
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

        path = f"/bilar/{public_variant_slug(row)}"
        price = format_price(row.get("price_sek"))
        wltp = row.get("wltp_range_km")
        range_display = wltp
        if (row.get('brand') == 'Polestar' and row.get('model') == '3' and row.get('variant_name') == 'Performance'
                and row.get('source_url') == 'https://www.polestar.com/se/polestar-3/specifications/'):
            certified = re.search(r'https://www\.polestar\.com/se/manual/polestar-3/2027/article/[^ |]+/ \| Performance \| '
                                  r'\d{3} \| (\d{3}) \| (\d{2},\d) \| \d{3} \| (\d{3}) \| (\d{2},\d)(?= \||$)',
                                  row.get('source_quote') or '')
            if (certified and int(certified[1]) == wltp and int(certified[3]) < wltp
                    and float(certified[4].replace(',', '.')) > float(certified[2].replace(',', '.'))):
                range_display = f'{certified[3]}\u2013{certified[1]}'
        range_label = 'Tillverkarens WLTP-räckviddsmål' if (row.get('brand') == 'Polestar' and row.get('model') == '4'
            and row.get('variant_name') == 'Dual motor' and 'Räckviddsmål (WLTP)' in row.get('source_quote', '')) else 'WLTP-räckvidd'
        if (row.get('brand') == 'Kia' and row.get('model') == 'Ev3'
                and row.get('variant_name') in ('EV3 Plus AWD Long Range', 'EV3 GT Line AWD Long Range')
                and re.search(r'9VW5YGZ7Z-(?:LX3|SX2)', row.get('source_quote', ''))
                and '(AWD, Preliminär information i väntan på homologering)' in row.get('source_quote', '')):
            range_label = 'Preliminärt WLTP-räckviddsmål'
        if (row.get('brand') == 'Kia' and row.get('model') == 'Ev4'
                and re.search(r'7ZS6(?:ZHZ7Z-LX1|YGZ7Z-LX1_V00|YGZ7Z-LX2)', row.get('source_quote', ''))):
            range_label = 'WLTP-räckvidd, upp till'
        if (row.get('brand') == 'Kia' and row.get('model') == 'Ev5'
                and re.search(r'X9W5(?:ZHZ7Z-LX1|YLZ7Z-(?:SX1|GX1)_V00|YRZ7Z-GX2)', row.get('source_quote', ''))):
            range_label = 'WLTP-räckvidd, upp till'
        if (row.get('brand') == 'Kia' and row.get('model') == 'Ev6'
                and re.search(r'ASW5(?:ZHZ7Z-TX1|YCZ7Z-TX1|YDZ7Z-GX2)', row.get('source_quote', ''))):
            range_label = 'WLTP-räckvidd, upp till'
        if (row.get('brand') == 'Kia' and row.get('model') == 'Ev9'
                and re.search(r'DOW[67](?:ZHZ7Z-LX2|YBZ7Z-(?:TX2|GX1|SX2))', row.get('source_quote', ''))):
            range_label = 'WLTP-räckvidd, upp till'
        if (row.get('brand') == 'Kia' and row.get('model') == 'Ev2'
                and re.search(r'6NW5ZFZ7Z-(?:TX2(?:_V00)?|LX1)', row.get('source_quote', ''))):
            range_label = 'WLTP-räckvidd, upp till'
        if (row.get('brand') == 'Toyota' and row.get('model') == 'C-Hr+'
                and 'Active 2WD 18": 607 km' in row.get('source_quote','') and 'Executive AWD: 507 km' in row.get('source_quote','')):
            range_label = 'WLTP-räckvidd, upp till'
        description_parts = [name]
        if price:
            price_label = {'list_price': 'listpris', 'campaign_price': 'kampanjpris', 'manufacturer_from': 'tillverkarens fr\u00e5npris', 'dealer_offer': 'återförsäljarerbjudande'}.get(row.get('price_type'), 'prisuppgift')
            description_parts.append(f"{price_label} {price}")
        if wltp:
            description_parts.append(f"{range_label} {range_display} km")
        description = ", ".join(description_parts) + ". Verifierade svenska källor och tydliga nyckeltal."

        properties = [
            metric_property("Tillverkarens fr\u00e5npris", row["price_sek"], "SEK") if price and row.get("price_type") == "manufacturer_from" else None,
            metric_property(range_label, range_display, "km"),
            metric_property("DC-laddning", row.get("dc_charge_kw"), "kW"),
            metric_property("AC-laddning", row.get("ac_charge_kw"), "kW"),
            metric_property("Batteri", row.get("battery_kwh"), "kWh"),
            metric_property("Bagageutrymme", row.get("boot_liters"), "liter"),
            metric_property("Dragvikt", row.get("tow_kg"), "kg"),
            metric_property("Säten", row.get("seats")),
            metric_property("Källa", row.get("source_url")),
        ]
        if row.get('price_source_url') and row.get('price_verified_at'):
            properties.extend([metric_property('Priskälla', row['price_source_url']),
                               metric_property('Pris verifierat', row['price_verified_at'][:10])])

        json_ld = {
            "@context": "https://schema.org",
            "@type": "Vehicle",
            "name": name,
            "brand": {"@type": "Brand", "name": row.get("brand", "")},
            "model": row.get("model", ""),
            "url": f"{SITE_URL}{path}",
            "additionalProperty": [item for item in properties if item],
        }
        if row.get("price_sek") and row.get("price_type") != "manufacturer_from":
            offer = {"@type": "Offer", "priceCurrency": "SEK", "price": row["price_sek"]}
            if row.get("available_confirmed") is True:
                offer["availability"] = "https://schema.org/InStock"
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.get("price_valid_until") or ""):
                offer["priceValidUntil"] = row["price_valid_until"]
            json_ld["offers"] = offer

        routes.append(
            {
                "path": path,
                "title": f"{name} – pris, räckvidd och specs | Elbilsagenten",
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
        "Elbilsagenten Sverige – hitta rätt elbil med AI",
        "Beskriv budget, körning och behov och få en shortlist med verifierade elbilar, tydliga kompromisser och källor.",
        "/",
        {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": "Elbilsagenten Sverige",
            "applicationCategory": "AutomotiveApplication",
            "operatingSystem": "Web",
            "url": SITE_URL,
        },
    )
    write_route("/", home)

    routes = [
        {
            "path": "/bilar",
            "title": "Jämför elbilar i Sverige | Elbilsagenten",
            "description": "Filtrera och jämför verifierade elbilar på den svenska marknaden med pris, räckvidd, laddning, dragvikt och källor.",
            "json_ld": {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Jämför elbilar i Sverige", "url": f"{SITE_URL}/bilar"},
        },
        {
            "path": "/jamfor",
            "title": "Jämför elbilar sida vid sida | Elbilsagenten",
            "description": "Skapa en beslutsrapport och jämför elbilar sida vid sida med AI-sammanfattning och verifierade nyckeltal.",
            "json_ld": {"@context": "https://schema.org", "@type": "WebPage", "name": "Jämför elbilar sida vid sida", "url": f"{SITE_URL}/jamfor"},
        },
        {
            "path": "/verifiering",
            "title": "Verifiering och datakvalitet | Elbilsagenten",
            "description": "Se hur Elbilsagenten använder Mobility Sweden, officiella svenska tillverkarkällor, AI-extraktion, validering och quarantine innan data visas publikt.",
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
                    "name": metadata["title"].replace(" | Elbilsagenten", ""),
                    "description": metadata["description"],
                    "url": f"{SITE_URL}/{route_slug}",
                },
                item_list_json_ld(f"/{route_slug}", metadata["title"].replace(" | Elbilsagenten", ""), segment_rows(route_slug, public_rows)),
            ],
        }
        for route_slug, metadata in SEGMENTS.items()
    )
    routes.extend(public_variant_routes(public_rows))
    routes.extend(news_routes(SITE_URL))
    routes.extend(info_routes(SITE_URL))

    for route in routes:
        html = inject_head(base_html, route["title"], route["description"], route["path"], route["json_ld"])
        if route.get("body_html"):
            html = html.replace('<div id="root"></div>', '<div id="root">' + route["body_html"] + '</div>')
        write_route(route["path"], html)

    from vehicle_redirects import write_vehicle_redirects
    redirects = write_vehicle_redirects(DIST, public_rows)
    print(f"Prerendered {len(routes) + 1} static route files and {redirects} retired-variant redirects in dist/")


if __name__ == "__main__":
    main()
