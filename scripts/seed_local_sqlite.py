import argparse
import json
from pathlib import Path

from local_sqlite_db import DEFAULT_DB_PATH, apply_schema, connect, fetch_id_map, public_variant_rows, upsert_rows
from seed_supabase import (
    build_alias_rows,
    build_canonical_model_rows,
    build_canonical_variant_rows,
    build_extracted_draft_rows,
    build_market_model_rows,
    build_monthly_stat_rows,
    build_source_rows,
)


def canonical_key_map(connection) -> dict[tuple[str, str], int]:
    return fetch_id_map(connection, "canonical_models", ["normalized_brand", "normalized_model"])


def market_key_map(connection) -> dict[tuple[str, str, str], int]:
    return fetch_id_map(connection, "market_models", ["normalized_brand", "normalized_model", "fuel_type_raw"])


def source_key_map(connection) -> dict[str, int]:
    return {row["url"]: row["id"] for row in connection.execute("select id, url from manufacturer_sources").fetchall()}


def normalize_monthly_rows(rows: list[dict], market_ids: dict[tuple[str, str, str], int]) -> list[dict]:
    normalized = []
    for row in rows:
        market_id = row["market_model_id"]
        if isinstance(market_id, str):
            brand, model, fuel = market_id.split(":", 2)
            market_id = market_ids[(brand, model, fuel)]
        normalized.append({**row, "market_model_id": market_id, "county": row.get("county") or "", "municipality": row.get("municipality") or ""})
    return normalized


def attach_source_ids(rows: list[dict], source_ids: dict[str, int]) -> list[dict]:
    output = []
    for row in rows:
        source_url = row.get("source_url")
        output.append({**row, "source_id": row.get("source_id") or source_ids.get(source_url)})
    return output


def seed(db_path: Path, reset: bool = False) -> dict:
    if reset and db_path.exists():
        db_path.unlink()

    connection = connect(db_path)
    apply_schema(connection)

    upsert_rows(connection, "market_models", build_market_model_rows(), ["normalized_brand", "normalized_model", "fuel_type_raw"])
    market_ids = market_key_map(connection)
    upsert_rows(
        connection,
        "market_model_monthly_stats",
        normalize_monthly_rows(build_monthly_stat_rows(), market_ids),
        ["market_model_id", "month", "county", "municipality"],
    )

    upsert_rows(connection, "canonical_models", build_canonical_model_rows(), ["normalized_brand", "normalized_model"])
    canonical_ids = canonical_key_map(connection)
    upsert_rows(connection, "model_aliases", build_alias_rows(canonical_ids), ["normalized_brand", "normalized_model"])
    upsert_rows(connection, "manufacturer_sources", build_source_rows(canonical_ids), ["url"])
    source_ids = source_key_map(connection)
    upsert_rows(connection, "extracted_variant_drafts", attach_source_ids(build_extracted_draft_rows(canonical_ids), source_ids), ["source_url", "variant_name"])
    upsert_rows(connection, "canonical_model_variants", attach_source_ids(build_canonical_variant_rows(canonical_ids), source_ids), ["canonical_model_id", "variant_name"])

    report = {
        "db_path": str(db_path),
        "market_models": connection.execute("select count(*) from market_models").fetchone()[0],
        "canonical_models": connection.execute("select count(*) from canonical_models").fetchone()[0],
        "manufacturer_sources": connection.execute("select count(*) from manufacturer_sources").fetchone()[0],
        "extracted_variant_drafts": connection.execute("select count(*) from extracted_variant_drafts").fetchone()[0],
        "canonical_model_variants": connection.execute("select count(*) from canonical_model_variants").fetchone()[0],
        "public_ev_variants": len(public_variant_rows(connection)),
    }
    connection.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a portable local SQLite database from canonical EV pipeline files.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    print(json.dumps(seed(args.db, reset=args.reset), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
