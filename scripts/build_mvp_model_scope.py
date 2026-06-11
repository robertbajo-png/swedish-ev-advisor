import argparse
import csv
import json
from pathlib import Path


DEFAULT_LIMIT = 30


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def boolish(value: str | bool | None) -> bool:
    return str(value).strip().lower() == "true"


def intish(value: str | int | None) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def key(row: dict) -> tuple[str, str]:
    return row["normalized_brand"], row["normalized_model"]


def source_status_by_model(rows: list[dict]) -> dict[tuple[str, str], dict]:
    status = {}
    for row in rows:
        status[(row["brand"].strip().lower(), row["model"].strip().lower())] = row
    return status


def build_scope(
    market_rows: list[dict],
    canonical_rows: list[dict],
    alias_rows: list[dict],
    source_rows: list[dict],
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[dict], list[dict]]:
    canonical_by_key = {key(row): row for row in canonical_rows}
    alias_by_key = {key(row): row for row in alias_rows}
    source_by_display = source_status_by_model(source_rows)
    candidates = []
    quarantined = []

    for market in market_rows:
        alias = alias_by_key.get(key(market))
        canonical = canonical_by_key.get(key(market))
        registrations_ytd = intish(market.get("registrations_ytd"))
        registrations_last_month = intish(market.get("registrations_last_month"))
        needs_mapping = boolish(market.get("needs_mapping")) or boolish(alias.get("needs_mapping") if alias else False)

        if needs_mapping or not alias or not canonical:
            quarantined.append(
                {
                    "brand_raw": market["brand_raw"],
                    "model_raw": market["model_raw"],
                    "normalized_brand": market["normalized_brand"],
                    "normalized_model": market["normalized_model"],
                    "registrations_ytd": registrations_ytd,
                    "registrations_last_month": registrations_last_month,
                    "reason": "needs_mapping" if needs_mapping else "missing_alias_or_canonical_model",
                    "model_group": market.get("model_group") or (alias or {}).get("model_group") or "",
                }
            )
            continue

        source = source_by_display.get((canonical["brand"].strip().lower(), canonical["model"].strip().lower()), {})
        candidates.append(
            {
                "rank": 0,
                "mvp_scope": "",
                "brand": canonical["brand"],
                "model": canonical["model"],
                "brand_raw": market["brand_raw"],
                "model_raw": market["model_raw"],
                "normalized_brand": market["normalized_brand"],
                "normalized_model": market["normalized_model"],
                "registrations_ytd": registrations_ytd,
                "registrations_last_month": registrations_last_month,
                "first_seen_month": market["first_seen_month"],
                "last_seen_month": market["last_seen_month"],
                "alias_rule": alias["alias_rule"],
                "source_url": source.get("url", ""),
                "source_validation": source.get("source_validation", source.get("extraction_status", "needs_discovery")),
                "extraction_ready": str(source.get("source_validation") == "reachable_official_model_source"),
            }
        )

    candidates.sort(key=lambda row: (-row["registrations_ytd"], -row["registrations_last_month"], row["brand"], row["model"]))
    for index, row in enumerate(candidates, start=1):
        row["rank"] = index
        row["mvp_scope"] = "top_20" if index <= 20 else "top_30" if index <= limit else "later_expansion"

    return candidates[:limit], quarantined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--market-models", type=Path, default=Path("data/mobility-sweden/processed/market_models.csv"))
    parser.add_argument("--canonical-models", type=Path, default=Path("data/canonical/canonical_models_seed.csv"))
    parser.add_argument("--aliases", type=Path, default=Path("data/canonical/model_aliases_seed.csv"))
    parser.add_argument("--sources", type=Path, default=Path("data/canonical/manufacturer_sources_validated.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/mvp"))
    args = parser.parse_args()

    scope, quarantined = build_scope(
        read_csv(args.market_models),
        read_csv(args.canonical_models),
        read_csv(args.aliases),
        read_csv(args.sources) if args.sources.exists() else [],
        args.limit,
    )
    write_csv(args.out_dir / "mvp_model_scope.csv", scope)
    write_csv(args.out_dir / "mvp_mapping_quarantine.csv", quarantined)
    (args.out_dir / "mvp_model_scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "mvp_mapping_quarantine.json").write_text(
        json.dumps(quarantined, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ready = sum(1 for row in scope if row["extraction_ready"] == "True")
    print(f"MVP model scope: {len(scope)}")
    print(f"Extraction-ready official sources: {ready}")
    print(f"Quarantined mapping rows: {len(quarantined)}")


if __name__ == "__main__":
    main()
