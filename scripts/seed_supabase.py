import argparse
import csv
import json
from pathlib import Path

from canonical_model_names import canonical_key_candidates, normalize
from supabase_client import SupabaseRestClient


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def bool_value(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def int_or_none(value: str):
    return None if value in ("", None) else int(value)


def canonical_id_for(canonical_ids: dict[tuple[str, str], str] | None, brand: str, model: str):
    if canonical_ids is None:
        return None
    for key in canonical_key_candidates(brand, model):
        if key in canonical_ids:
            return canonical_ids[key]
    return None


def first_value(row: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def source_title(row: dict) -> str:
    title = first_value(row, "title")
    if title:
        return title
    brand = first_value(row, "brand")
    model = first_value(row, "model")
    source_type = first_value(row, "source_type", default="official_source")
    return f"{brand} {model} {source_type}".strip()


def validation_status_value(value: str) -> str:
    return {
        "ready_for_ai_extraction": "queued",
    }.get(value, value or "draft")


def float_or_none(value: str | int | float | None):
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_source_seed_rows() -> list[dict]:
    paths = [
        ROOT / "data/canonical/manufacturer_sources_seed.csv",
        ROOT / "data/canonical/manufacturer_sources_validated.csv",
        ROOT / "data/canonical/manufacturer_sources_mvp_validated.csv",
        ROOT / "data/canonical/mvp_extraction_queue.csv",
        ROOT / "data/extraction/rendered_extraction_batch.csv",
    ]
    rows_by_url = {}
    for path in paths:
        if not path.exists():
            continue
        for row in read_csv(path):
            url = first_value(row, "url", "source_url")
            if not url:
                continue
            rows_by_url[url] = row
    return list(rows_by_url.values())


def build_market_model_rows() -> list[dict]:
    rows = []
    for row in read_csv(ROOT / "data/mobility-sweden/processed/market_models.csv"):
        rows.append(
            {
                "brand_raw": row["brand_raw"],
                "model_raw": row["model_raw"],
                "fuel_type_raw": row["fuel_type_raw"],
                "normalized_brand": row["normalized_brand"],
                "normalized_model": row["normalized_model"],
                "model_group": row["model_group"] or None,
                "needs_mapping": bool_value(row["needs_mapping"]),
                "first_seen_month": row["first_seen_month"] or None,
                "last_seen_month": row["last_seen_month"] or None,
                "registrations_last_month": int(row["registrations_last_month"]),
                "registrations_ytd": int(row["registrations_ytd"]),
                "registrations_12m": int_or_none(row["registrations_12m"]),
                "source_name": row["source_name"],
                "source_url": row["source_url"],
            }
        )
    return rows


def load_market_models(client: SupabaseRestClient) -> dict[tuple[str, str, str], str]:
    rows = build_market_model_rows()
    returned = client.upsert("market_models", rows, "normalized_brand,normalized_model,fuel_type_raw")
    return {(row["normalized_brand"], row["normalized_model"], row["fuel_type_raw"]): row["id"] for row in returned}


def build_monthly_stat_rows(market_ids: dict[tuple[str, str, str], str] | None = None) -> list[dict]:
    rows = []
    for row in read_csv(ROOT / "data/mobility-sweden/processed/market_model_monthly_stats.csv"):
        brand, model, fuel = row["market_model_key"].split(":", 2)
        market_id = market_ids[(brand, model, fuel)] if market_ids else f"{brand}:{model}:{fuel}"
        rows.append(
            {
                "market_model_id": market_id,
                "month": row["month"],
                "brand_raw": row["brand_raw"],
                "model_raw": row["model_raw"],
                "fuel_type_raw": row["fuel_type_raw"],
                "registrations": int(row["registrations"]),
            }
        )
    return rows


def load_monthly_stats(client: SupabaseRestClient, market_ids: dict[tuple[str, str, str], str]):
    rows = build_monthly_stat_rows(market_ids)
    client.upsert("market_model_monthly_stats", rows, "market_model_id,month,county,municipality", returning=False)


def build_canonical_model_rows() -> list[dict]:
    rows = []
    for row in read_csv(ROOT / "data/canonical/canonical_models_seed.csv"):
        rows.append(
            {
                "brand": row["brand"],
                "model": row["model"],
                "normalized_brand": row["normalized_brand"],
                "normalized_model": row["normalized_model"],
                "market_seen": bool_value(row["market_seen"]),
                "available_confirmed": bool_value(row["available_confirmed"]),
                "discontinued_candidate": bool_value(row["discontinued_candidate"]),
                "coming_or_low_volume": bool_value(row["coming_or_low_volume"]),
                "validation_status": row["validation_status"],
            }
        )
    return rows


def load_canonical_models(client: SupabaseRestClient) -> dict[tuple[str, str], str]:
    rows = build_canonical_model_rows()
    returned = client.upsert("canonical_models", rows, "normalized_brand,normalized_model")
    return {(row["normalized_brand"], row["normalized_model"]): row["id"] for row in returned}


def build_alias_rows(canonical_ids: dict[tuple[str, str], str] | None = None) -> list[dict]:
    resolved_aliases = {}
    resolved_path = ROOT / "data/canonical/model_aliases_resolved.csv"
    if resolved_path.exists():
        for row in read_csv(resolved_path):
            raw_key = (row.get("brand_raw", ""), row.get("model_raw", ""))
            canonical_brand = row.get("canonical_brand") or ""
            canonical_model = row.get("canonical_model") or ""
            if raw_key[0] and raw_key[1] and canonical_brand and canonical_model:
                resolved_aliases[raw_key] = (normalize(canonical_brand), normalize(canonical_model))

    rows = []
    for row in read_csv(ROOT / "data/canonical/model_aliases_seed.csv"):
        key = (row["normalized_brand"], row["normalized_model"])
        needs_mapping = bool_value(row["needs_mapping"])
        if canonical_ids is not None and not needs_mapping and key not in canonical_ids:
            key = resolved_aliases.get((row["brand_raw"], row["model_raw"]), key)
        canonical_model_id = None if needs_mapping or canonical_ids is None else canonical_ids.get(key)
        if canonical_ids is not None and not canonical_model_id:
            needs_mapping = True
        rows.append(
            {
                "canonical_model_id": canonical_model_id,
                "brand_raw": row["brand_raw"],
                "model_raw": row["model_raw"],
                "normalized_brand": key[0],
                "normalized_model": key[1],
                "alias_rule": row["alias_rule"],
                "model_group": row["model_group"] or None,
                "needs_mapping": needs_mapping,
                "confidence": float(row["confidence"]),
            }
        )
    return rows


def load_aliases(client: SupabaseRestClient, canonical_ids: dict[tuple[str, str], str]):
    rows = build_alias_rows(canonical_ids)
    client.upsert("model_aliases", rows, "normalized_brand,normalized_model", returning=False)


def build_source_rows(canonical_ids: dict[tuple[str, str], str] | None = None) -> list[dict]:
    rows = []
    for row in load_source_seed_rows():
        key = (normalize(row.get("brand", "")), normalize(row.get("model", "")))
        canonical_id = None if canonical_ids is None else canonical_ids.get(key)
        rows.append(
            {
                "canonical_model_id": canonical_id,
                "brand": row["brand"],
                "model": row["model"],
                "source_type": row["source_type"],
                "url": first_value(row, "url", "source_url"),
                "title": source_title(row),
                "country": first_value(row, "country", default="SE"),
                "language": first_value(row, "language", default="sv"),
                "extraction_status": validation_status_value(first_value(row, "extraction_status", "preflight_status", default="draft")),
                "extraction_confidence": float_or_none(first_value(row, "extraction_confidence")),
                "http_status": int_or_none(row.get("http_status", "")),
                "final_url": row.get("final_url") or None,
                "content_hash": first_value(row, "content_hash", "source_hash") or None,
                "fetched_at": row.get("fetched_at") or None,
                "source_validation": row.get("source_validation") or "needs_discovery",
                "is_primary": row.get("source_validation") == "reachable_official_model_source",
            }
        )
    return rows


def load_sources(client: SupabaseRestClient, canonical_ids: dict[tuple[str, str], str]):
    rows = build_source_rows(canonical_ids)
    client.upsert("manufacturer_sources", rows, "url", returning=False)


def build_extracted_draft_rows(canonical_ids: dict[tuple[str, str], str] | None = None) -> list[dict]:
    draft_path = ROOT / "data/extraction/extracted_variant_drafts.json"
    if not draft_path.exists():
        return []
    allowed_columns = {
        "canonical_model_id",
        "source_id",
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
        "source_quote",
        "source_hash",
        "extraction_confidence",
        "extraction_payload",
        "validation_status",
        "validation_errors",
    }
    rows = []
    for row in json.loads(draft_path.read_text(encoding="utf-8")):
        payload = {key: row.get(key) for key in allowed_columns if key in row}
        payload["canonical_model_id"] = canonical_id_for(canonical_ids, row["brand"], row["model"])
        rows.append(payload)
    return rows


def load_extracted_drafts(client: SupabaseRestClient, canonical_ids: dict[tuple[str, str], str]):
    rows = build_extracted_draft_rows(canonical_ids)
    if not rows:
        return
    client.upsert("extracted_variant_drafts", rows, "source_url,variant_name", returning=False)


def build_canonical_variant_rows(canonical_ids: dict[tuple[str, str], str] | None = None) -> list[dict]:
    variants_path = ROOT / "data/canonical/canonical_model_variants_seed.json"
    if not variants_path.exists():
        return []
    rows = []
    for row in json.loads(variants_path.read_text(encoding="utf-8")):
        canonical_id = canonical_id_for(canonical_ids, row["brand"], row["model"])
        if canonical_ids is not None and not canonical_id:
            continue
        payload = dict(row)
        payload.pop("brand", None)
        payload.pop("model", None)
        payload["canonical_model_id"] = canonical_id
        rows.append(payload)
    return rows


def load_canonical_variants(client: SupabaseRestClient, canonical_ids: dict[tuple[str, str], str]):
    rows = build_canonical_variant_rows(canonical_ids)
    if not rows:
        return
    client.upsert("canonical_model_variants", rows, "canonical_model_id,variant_name", returning=False)


def build_seed_plan() -> dict:
    market_models = build_market_model_rows()
    canonical_models = build_canonical_model_rows()
    sources = build_source_rows()
    source_statuses = {}
    for row in sources:
        source_statuses[row["extraction_status"]] = source_statuses.get(row["extraction_status"], 0) + 1
    return {
        "market_models": len(market_models),
        "market_model_monthly_stats": len(build_monthly_stat_rows()),
        "canonical_models": len(canonical_models),
        "model_aliases": len(build_alias_rows()),
        "manufacturer_sources": len(sources),
        "manufacturer_sources_by_status": dict(sorted(source_statuses.items())),
        "extracted_variant_drafts": len(build_extracted_draft_rows()),
        "canonical_model_variants": len(build_canonical_variant_rows()),
    }


def run_seed() -> dict:
    client = SupabaseRestClient()
    market_ids = load_market_models(client)
    load_monthly_stats(client, market_ids)
    canonical_ids = load_canonical_models(client)
    load_aliases(client, canonical_ids)
    load_sources(client, canonical_ids)
    load_extracted_drafts(client, canonical_ids)
    load_canonical_variants(client, canonical_ids)
    return {"market_models": len(market_ids), "canonical_models": len(canonical_ids)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Supabase with canonical EV pipeline data.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned row counts without connecting to Supabase.")
    args = parser.parse_args()

    if args.dry_run:
        print(json.dumps({"dry_run": True, **build_seed_plan()}, ensure_ascii=False, indent=2))
        return

    print(json.dumps(run_seed(), indent=2))


if __name__ == "__main__":
    main()
