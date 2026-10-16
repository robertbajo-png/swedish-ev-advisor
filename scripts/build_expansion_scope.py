import argparse
import csv
import json
from pathlib import Path

from canonical_model_names import normalize


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("records", []) if isinstance(payload, dict) else payload


def boolish(value) -> bool:
    return str(value or "").strip().lower() == "true"


def intish(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def model_key(brand, model) -> tuple[str, str]:
    return normalize(brand), normalize(model)


def build_expansion_scope(
    market_rows: list[dict],
    canonical_rows: list[dict],
    alias_rows: list[dict],
    public_variants: list[dict],
    start_rank: int = 31,
    end_rank: int = 60,
) -> tuple[list[dict], list[dict]]:
    canonical = {(row["normalized_brand"], row["normalized_model"]): row for row in canonical_rows}
    aliases = {(row["normalized_brand"], row["normalized_model"]): row for row in alias_rows}
    public_keys = {model_key(row.get("brand"), row.get("model")) for row in public_variants}
    ranked_market = sorted(
        market_rows,
        key=lambda row: (-intish(row.get("registrations_ytd")), -intish(row.get("registrations_last_month")), row.get("brand_raw", ""), row.get("model_raw", "")),
    )
    ranked: list[dict] = []
    quarantine: list[dict] = []

    for market_rank, market in enumerate(ranked_market, start=1):
        if market_rank < start_rank or market_rank > end_rank:
            continue
        key = (market.get("normalized_brand", ""), market.get("normalized_model", ""))
        alias = aliases.get(key)
        model = canonical.get(key)
        ambiguous = boolish(market.get("needs_mapping")) or boolish(alias.get("needs_mapping") if alias else True)
        if ambiguous or not alias or not model:
            quarantine.append({
                "brand_raw": market.get("brand_raw", ""),
                "model_raw": market.get("model_raw", ""),
                "normalized_brand": key[0],
                "normalized_model": key[1],
                "market_rank": market_rank,
                "reason": "needs_mapping" if ambiguous else "missing_alias_or_canonical_model",
                "model_group": market.get("model_group", ""),
            })
            continue
        ranked.append({
            "market_rank": market_rank,
            "wave": f"rank_{start_rank}_{end_rank}",
            "brand": model["brand"],
            "model": model["model"],
            "normalized_brand": key[0],
            "normalized_model": key[1],
            "registrations_ytd": intish(market.get("registrations_ytd")),
            "registrations_last_month": intish(market.get("registrations_last_month")),
            "registrations_12m": intish(market.get("registrations_12m")),
            "last_seen_month": market.get("last_seen_month", ""),
            "alias_rule": alias.get("alias_rule", ""),
        })

    scope = [
        row for row in ranked
        if model_key(row["brand"], row["model"]) not in public_keys
    ]
    return scope, quarantine


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a ranked expansion wave from Mobility Sweden market data.")
    parser.add_argument("--start-rank", type=int, default=31)
    parser.add_argument("--end-rank", type=int, default=60)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data/expansion")
    args = parser.parse_args()
    scope, quarantine = build_expansion_scope(
        read_csv(ROOT / "data/mobility-sweden/processed/market_models.csv"),
        read_csv(ROOT / "data/canonical/canonical_models_seed.csv"),
        read_csv(ROOT / "data/canonical/model_aliases_seed.csv"),
        read_json(ROOT / "data/canonical/canonical_model_variants_seed.json"),
        args.start_rank,
        args.end_rank,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "expansion_scope.csv", scope)
    write_csv(args.out_dir / "mapping_quarantine.csv", quarantine)
    (args.out_dir / "expansion_scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "mapping_quarantine.json").write_text(json.dumps(quarantine, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scope": len(scope), "quarantine": len(quarantine), "start_rank": args.start_rank, "end_rank": args.end_rank}, indent=2))


if __name__ == "__main__":
    main()
