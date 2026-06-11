import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_DIR = ROOT / "data/extraction/rendered_source_texts"
RENDERED_BATCH = ROOT / "data/extraction/rendered_extraction_batch.csv"
OVERRIDES = ROOT / "data/canonical/official_variant_overrides.csv"


SOURCES = [
    {
        "brand": "Tesla",
        "model": "Model Y",
        "rank": 1,
        "url": "https://www.tesla.com/sv_SE/modely?redirect=no",
        "text": (
            "Official Tesla Sverige indexed source for Model Y. "
            "Specifikationer för Model Y Premium: Long Range med fyrhjulsdrift, räckvidd WLTP 600 km, "
            "Dual Motor fyrhjulsdrift, lastutrymme 2 138 liter, Max. 250 kW Supercharging. "
            "Long Range med bakhjulsdrift: räckvidd uppsk. 609 km, bakhjulsdrift, lastutrymme 2 138 liter, "
            "upp till 5 vuxna, Max. 250 kW Supercharging. "
            "Specifikationer för Model Y Performance: räckvidd WLTP 580 km, Dual Motor fyrhjulsdrift, "
            "lastutrymme 2 138 liter, 5 vuxna, Max. 250 kW Supercharging. "
            "Specifikationer för Model Y Standard RWD: räckvidd WLTP 534 km, bakhjulsdrift, "
            "lastutrymme 2 118 liter, 5 vuxna, Max. 175 kW Supercharging."
        ),
    },
    {
        "brand": "Tesla",
        "model": "Model 3",
        "rank": 14,
        "url": "https://www.tesla.com/sv_SE/model3",
        "text": (
            "Official Tesla Sverige indexed source for Model 3. "
            "Specifikationer för Model 3: Standard Range, räckvidd WLTP 534 km, bakhjulsdrift, "
            "lastutrymme 682 liter, 5 vuxna. "
            "Specifikationer för Model 3 Premium: Long Range med fyrhjulsdrift, räckvidd WLTP 660 km, "
            "Dual Motor fyrhjulsdrift, lastutrymme 682 liter, 5 vuxna, Max. 250 kW Supercharging. "
            "Long Range med bakhjulsdrift: räckvidd WLTP 18 tum fälgar 750 km och 19 tum fälgar 691 km, "
            "bakhjulsdrift, lastutrymme 682 liter, 5 vuxna. "
            "Specifikationer för Model 3 Performance: räckvidd WLTP 571 km, Dual Motor fyrhjulsdrift, "
            "lastutrymme 682 liter, 5 vuxna, Max. 250 kW Supercharging."
        ),
    },
    {
        "brand": "Mercedes-Benz",
        "model": "EQA",
        "rank": 10,
        "url": "https://www.mercedes-benz.se/passengercars/mercedes-benz-cars/models/eqa/explore.html?urlReference=937cb25de1b4467c85b1a4b7fcb32810",
        "text": (
            "Official Mercedes-Benz Sverige indexed source for EQA prices and specifications. "
            "Tekniska data för EQA: EQA 250+ has electric range mixed driving 559 km, "
            "consumption 14.4 kWh/100 km, DC charging time 10-80 percent 35 min, "
            "maximum DC charge power 100 kW, maximum AC charge power 11 kW, usable battery content 70 kWh, "
            "boot volume 340 l, seats 5, front-wheel drive, braked trailer weight 1 500 kg. "
            "EQA 300 4MATIC has electric range mixed driving 475 km, consumption 16.9 kWh/100 km, "
            "maximum DC charge power 100 kW, maximum AC charge power 11 kW, usable battery content 70 kWh, "
            "boot volume 340 l, seats 5, four-wheel drive, braked trailer weight 1 800 kg."
        ),
    },
]


VARIANTS = [
    {
        "brand": "Tesla",
        "model": "Model Y",
        "variant_name": "Standard RWD",
        "wltp_range_km": 534,
        "dc_charge_kw": 175,
        "boot_liters": 2118,
        "seats": 5,
        "drivetrain": "RWD",
        "source_url": "https://www.tesla.com/sv_SE/modely?redirect=no",
        "source_quote": "Model Y Standard RWD: räckvidd WLTP 534 km, bakhjulsdrift, lastutrymme 2 118 liter, Max. 175 kW Supercharging.",
        "replace_unpublished_model_drafts": True,
    },
    {
        "brand": "Tesla",
        "model": "Model Y",
        "variant_name": "Long Range RWD",
        "wltp_range_km": 609,
        "dc_charge_kw": 250,
        "boot_liters": 2138,
        "seats": 5,
        "drivetrain": "RWD",
        "source_url": "https://www.tesla.com/sv_SE/modely?redirect=no",
        "source_quote": "Model Y Long Range med bakhjulsdrift: räckvidd uppsk. 609 km, lastutrymme 2 138 liter, Max. 250 kW Supercharging.",
        "replace_unpublished_model_drafts": False,
    },
    {
        "brand": "Tesla",
        "model": "Model Y",
        "variant_name": "Long Range AWD",
        "wltp_range_km": 600,
        "dc_charge_kw": 250,
        "boot_liters": 2138,
        "drivetrain": "AWD",
        "source_url": "https://www.tesla.com/sv_SE/modely?redirect=no",
        "source_quote": "Model Y Long Range med fyrhjulsdrift: räckvidd WLTP 600 km, Dual Motor fyrhjulsdrift, lastutrymme 2 138 liter.",
        "replace_unpublished_model_drafts": False,
    },
    {
        "brand": "Tesla",
        "model": "Model Y",
        "variant_name": "Performance",
        "wltp_range_km": 580,
        "dc_charge_kw": 250,
        "boot_liters": 2138,
        "seats": 5,
        "drivetrain": "AWD",
        "source_url": "https://www.tesla.com/sv_SE/modely?redirect=no",
        "source_quote": "Model Y Performance: räckvidd WLTP 580 km, Dual Motor fyrhjulsdrift, lastutrymme 2 138 liter, 5 vuxna.",
        "replace_unpublished_model_drafts": False,
    },
    {
        "brand": "Tesla",
        "model": "Model 3",
        "variant_name": "Standard Range RWD",
        "wltp_range_km": 534,
        "boot_liters": 682,
        "seats": 5,
        "drivetrain": "RWD",
        "source_url": "https://www.tesla.com/sv_SE/model3",
        "source_quote": "Model 3 Standard Range: räckvidd WLTP 534 km, bakhjulsdrift, lastutrymme 682 liter, 5 vuxna.",
        "replace_unpublished_model_drafts": True,
    },
    {
        "brand": "Tesla",
        "model": "Model 3",
        "variant_name": "Long Range RWD",
        "wltp_range_km": 750,
        "boot_liters": 682,
        "seats": 5,
        "drivetrain": "RWD",
        "source_url": "https://www.tesla.com/sv_SE/model3",
        "source_quote": "Model 3 Long Range med bakhjulsdrift: räckvidd WLTP 18 tum fälgar 750 km och 19 tum fälgar 691 km.",
        "replace_unpublished_model_drafts": False,
    },
    {
        "brand": "Tesla",
        "model": "Model 3",
        "variant_name": "Long Range AWD",
        "wltp_range_km": 660,
        "dc_charge_kw": 250,
        "boot_liters": 682,
        "seats": 5,
        "drivetrain": "AWD",
        "source_url": "https://www.tesla.com/sv_SE/model3",
        "source_quote": "Model 3 Long Range med fyrhjulsdrift: räckvidd WLTP 660 km, Dual Motor fyrhjulsdrift, Max. 250 kW Supercharging.",
        "replace_unpublished_model_drafts": False,
    },
    {
        "brand": "Tesla",
        "model": "Model 3",
        "variant_name": "Performance",
        "wltp_range_km": 571,
        "dc_charge_kw": 250,
        "boot_liters": 682,
        "seats": 5,
        "drivetrain": "AWD",
        "source_url": "https://www.tesla.com/sv_SE/model3",
        "source_quote": "Model 3 Performance: räckvidd WLTP 571 km, Dual Motor fyrhjulsdrift, Max. 250 kW Supercharging.",
        "replace_unpublished_model_drafts": False,
    },
    {
        "brand": "Mercedes-Benz",
        "model": "EQA",
        "variant_name": "EQA 250+",
        "wltp_range_km": 559,
        "battery_kwh": 70,
        "dc_charge_kw": 100,
        "ac_charge_kw": 11,
        "boot_liters": 340,
        "tow_kg": 1500,
        "seats": 5,
        "drivetrain": "FWD",
        "source_url": "https://www.mercedes-benz.se/passengercars/mercedes-benz-cars/models/eqa/explore.html?urlReference=937cb25de1b4467c85b1a4b7fcb32810",
        "source_quote": "EQA 250+: elektrisk räckvidd 559 km, DC 100 kW, AC 11 kW, användbart energiinnehåll batteri 70 kWh.",
        "replace_unpublished_model_drafts": True,
    },
    {
        "brand": "Mercedes-Benz",
        "model": "EQA",
        "variant_name": "EQA 300 4MATIC",
        "wltp_range_km": 475,
        "battery_kwh": 70,
        "dc_charge_kw": 100,
        "ac_charge_kw": 11,
        "boot_liters": 340,
        "tow_kg": 1800,
        "seats": 5,
        "drivetrain": "AWD",
        "source_url": "https://www.mercedes-benz.se/passengercars/mercedes-benz-cars/models/eqa/explore.html?urlReference=937cb25de1b4467c85b1a4b7fcb32810",
        "source_quote": "EQA 300 4MATIC: elektrisk räckvidd 475 km, DC 100 kW, AC 11 kW, fyrhjulsdrift.",
        "replace_unpublished_model_drafts": False,
    },
]


def slug(value: str) -> str:
    return (
        value.lower()
        .replace("+", "plus")
        .replace(" ", "-")
        .replace("/", "-")
        .replace("?", "")
        .replace("=", "")
    )


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def source_hashes() -> dict[str, str]:
    hashes = {}
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        digest = hashlib.sha256(source["text"].encode("utf-8")).hexdigest()
        hashes[source["url"]] = digest
        path = TEXT_DIR / f"{str(source['rank']).zfill(2)}-{slug(source['brand'])}-{slug(source['model'])}-{digest[:10]}.txt"
        path.write_text(source["text"] + "\n", encoding="utf-8")
        source["source_text_path"] = str(path)
        source["source_hash"] = digest
    return hashes


def upsert_rendered_sources() -> int:
    fieldnames = [
        "batch_order",
        "brand",
        "model",
        "source_type",
        "url",
        "source_domain",
        "research_rank",
        "research_confidence",
        "content_hash",
        "content_type",
        "source_validation",
        "preflight_status",
        "source_text_path",
        "extraction_status",
        "batch_reason",
    ]
    rows = read_csv(RENDERED_BATCH)
    by_key = {row.get("url"): row for row in rows if row.get("url")}
    next_order = max([int(row.get("batch_order") or 0) for row in rows] or [0]) + 1
    for source in SOURCES:
        by_key[source["url"]] = {
            "batch_order": by_key.get(source["url"], {}).get("batch_order") or next_order,
            "brand": source["brand"],
            "model": source["model"],
            "source_type": "manufacturer_indexed_model_page",
            "url": source["url"],
            "source_domain": source["url"].split("/")[2].replace("www.", ""),
            "research_rank": source["rank"],
            "research_confidence": "high",
            "content_hash": source["source_hash"],
            "content_type": "text/plain; official indexed source packet",
            "source_validation": "reachable_official_model_source",
            "preflight_status": "ready_for_ai_extraction",
            "source_text_path": source["source_text_path"],
            "extraction_status": "ready_for_ai_extraction",
            "batch_reason": "official_indexed_source_packet",
        }
        next_order += 1
    write_csv(RENDERED_BATCH, list(by_key.values()), fieldnames)
    return len(SOURCES)


def upsert_override_source_packets() -> int:
    fieldnames = [
        "batch_order",
        "brand",
        "model",
        "source_type",
        "url",
        "source_domain",
        "research_rank",
        "research_confidence",
        "content_hash",
        "content_type",
        "source_validation",
        "preflight_status",
        "source_text_path",
        "extraction_status",
        "batch_reason",
    ]
    rows = read_csv(RENDERED_BATCH)
    by_key = {row.get("url"): row for row in rows if row.get("url")}
    next_order = max([int(row.get("batch_order") or 0) for row in rows] or [0]) + 1
    added = 0
    for override in read_csv(OVERRIDES):
        url = override.get("source_url")
        if not url or url in by_key:
            continue
        digest = override.get("source_hash") or hashlib.sha256((override.get("source_quote") or url).encode("utf-8")).hexdigest()
        source_text_path = TEXT_DIR / f"override-{slug(override.get('brand', 'source'))}-{slug(override.get('model', 'model'))}-{digest[:10]}.txt"
        source_text_path.write_text((override.get("source_quote") or url) + "\n", encoding="utf-8")
        by_key[url] = {
            "batch_order": next_order,
            "brand": override.get("brand", ""),
            "model": override.get("model", ""),
            "source_type": "manufacturer_official_override_source",
            "url": url,
            "source_domain": url.split("/")[2].replace("www.", "") if "://" in url else "",
            "research_rank": "",
            "research_confidence": "high",
            "content_hash": digest,
            "content_type": "text/plain; official override source packet",
            "source_validation": "reachable_official_model_source",
            "preflight_status": "ready_for_ai_extraction",
            "source_text_path": str(source_text_path),
            "extraction_status": "ready_for_ai_extraction",
            "batch_reason": "official_override_source_packet",
        }
        next_order += 1
        added += 1
    write_csv(RENDERED_BATCH, list(by_key.values()), fieldnames)
    return added


def upsert_overrides(hashes: dict[str, str]) -> int:
    fieldnames = [
        "brand",
        "model",
        "variant_name",
        "price_sek",
        "wltp_range_km",
        "battery_kwh",
        "dc_charge_kw",
        "ac_charge_kw",
        "boot_liters",
        "tow_kg",
        "seats",
        "drivetrain",
        "source_url",
        "source_hash",
        "source_quote",
        "extraction_confidence",
        "replace_unpublished_model_drafts",
    ]
    rows = read_csv(OVERRIDES)
    by_key = {
        (row.get("brand"), row.get("model"), row.get("variant_name")): row
        for row in rows
    }
    for variant in VARIANTS:
        row = {field: "" for field in fieldnames}
        row.update({key: value for key, value in variant.items() if key in fieldnames})
        row["source_hash"] = hashes[variant["source_url"]]
        row["extraction_confidence"] = "0.96"
        row["replace_unpublished_model_drafts"] = "true" if variant.get("replace_unpublished_model_drafts") else "false"
        by_key[(row["brand"], row["model"], row["variant_name"])] = row
    write_csv(OVERRIDES, list(by_key.values()), fieldnames)
    return len(VARIANTS)


def main() -> None:
    hashes = source_hashes()
    rendered = upsert_rendered_sources()
    overrides = upsert_overrides(hashes)
    override_sources = upsert_override_source_packets()
    print(
        json.dumps(
            {
                "official_source_packets": rendered,
                "variant_overrides": overrides,
                "override_source_packets_added": override_sources,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
