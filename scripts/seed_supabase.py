import csv
import json
import unicodedata
import re
from pathlib import Path

from supabase_client import SupabaseRestClient


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8")))


def bool_value(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def int_or_none(value: str):
    return None if value in ("", None) else int(value)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.upper())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def load_market_models(client: SupabaseRestClient) -> dict[tuple[str, str, str], str]:
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
    returned = client.upsert("market_models", rows, "normalized_brand,normalized_model,fuel_type_raw")
    return {(row["normalized_brand"], row["normalized_model"], row["fuel_type_raw"]): row["id"] for row in returned}


def load_monthly_stats(client: SupabaseRestClient, market_ids: dict[tuple[str, str, str], str]):
    rows = []
    for row in read_csv(ROOT / "data/mobility-sweden/processed/market_model_monthly_stats.csv"):
        brand, model, fuel = row["market_model_key"].split(":", 2)
        market_id = market_ids[(brand, model, fuel)]
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
    client.upsert("market_model_monthly_stats", rows, "market_model_id,month,county,municipality", returning=False)


def load_canonical_models(client: SupabaseRestClient) -> dict[tuple[str, str], str]:
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
    returned = client.upsert("canonical_models", rows, "normalized_brand,normalized_model")
    return {(row["normalized_brand"], row["normalized_model"]): row["id"] for row in returned}


def load_aliases(client: SupabaseRestClient, canonical_ids: dict[tuple[str, str], str]):
    rows = []
    for row in read_csv(ROOT / "data/canonical/model_aliases_seed.csv"):
        key = (row["normalized_brand"], row["normalized_model"])
        needs_mapping = bool_value(row["needs_mapping"])
        rows.append(
            {
                "canonical_model_id": None if needs_mapping else canonical_ids.get(key),
                "brand_raw": row["brand_raw"],
                "model_raw": row["model_raw"],
                "normalized_brand": row["normalized_brand"],
                "normalized_model": row["normalized_model"],
                "alias_rule": row["alias_rule"],
                "model_group": row["model_group"] or None,
                "needs_mapping": needs_mapping,
                "confidence": float(row["confidence"]),
            }
        )
    client.upsert("model_aliases", rows, "normalized_brand,normalized_model", returning=False)


def load_sources(client: SupabaseRestClient, canonical_ids: dict[tuple[str, str], str]):
    source_path = ROOT / "data/canonical/manufacturer_sources_validated.csv"
    if not source_path.exists():
        source_path = ROOT / "data/canonical/manufacturer_sources_seed.csv"
    rows = []
    for row in read_csv(source_path):
        key = (normalize(row.get("brand", "")), normalize(row.get("model", "")))
        canonical_id = canonical_ids.get(key)
        rows.append(
            {
                "canonical_model_id": canonical_id,
                "brand": row["brand"],
                "model": row["model"],
                "source_type": row["source_type"],
                "url": row["url"],
                "title": row["title"],
                "country": row["country"],
                "language": row["language"],
                "extraction_status": row["extraction_status"],
                "extraction_confidence": None,
                "http_status": int_or_none(row.get("http_status", "")),
                "final_url": row.get("final_url") or None,
                "content_hash": row.get("content_hash") or None,
                "fetched_at": row.get("fetched_at") or None,
                "source_validation": row.get("source_validation") or "needs_discovery",
                "is_primary": row.get("source_validation") == "reachable_official_model_source",
            }
        )
    client.upsert("manufacturer_sources", rows, "url", returning=False)


def load_extracted_drafts(client: SupabaseRestClient, canonical_ids: dict[tuple[str, str], str]):
    draft_path = ROOT / "data/extraction/extracted_variant_drafts.json"
    if not draft_path.exists():
        return
    rows = []
    for row in json.loads(draft_path.read_text(encoding="utf-8")):
        key = (normalize(row["brand"]), normalize(row["model"]))
        rows.append({**row, "canonical_model_id": canonical_ids.get(key)})
    client.upsert("extracted_variant_drafts", rows, "source_url,variant_name", returning=False)


def load_canonical_variants(client: SupabaseRestClient, canonical_ids: dict[tuple[str, str], str]):
    variants_path = ROOT / "data/canonical/canonical_model_variants_seed.json"
    if not variants_path.exists():
        return
    rows = []
    for row in json.loads(variants_path.read_text(encoding="utf-8")):
        key = (normalize(row["brand"]), normalize(row["model"]))
        canonical_id = canonical_ids.get(key)
        if not canonical_id:
            continue
        payload = dict(row)
        payload.pop("brand", None)
        payload.pop("model", None)
        payload["canonical_model_id"] = canonical_id
        rows.append(payload)
    client.upsert("canonical_model_variants", rows, "canonical_model_id,variant_name", returning=False)


def main() -> None:
    client = SupabaseRestClient()
    market_ids = load_market_models(client)
    load_monthly_stats(client, market_ids)
    canonical_ids = load_canonical_models(client)
    load_aliases(client, canonical_ids)
    load_sources(client, canonical_ids)
    load_extracted_drafts(client, canonical_ids)
    load_canonical_variants(client, canonical_ids)
    print(json.dumps({"market_models": len(market_ids), "canonical_models": len(canonical_ids)}, indent=2))


if __name__ == "__main__":
    main()
