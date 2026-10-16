import argparse
import csv
import json
from pathlib import Path

from extract_manufacturer_specs import exact_wltp_consumption


ROOT = Path(__file__).resolve().parents[1]
DRAFTS_JSON = ROOT / "data/extraction/extracted_variant_drafts.json"
DRAFTS_CSV = ROOT / "data/extraction/extracted_variant_drafts.csv"
CANONICAL_JSON = ROOT / "data/canonical/canonical_model_variants_seed.json"
CANONICAL_CSV = ROOT / "data/canonical/canonical_model_variants_seed.csv"
MIN_CONFIDENCE = 0.92


def backfill_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    updated = []
    evidence = []
    for original in rows:
        row = dict(original)
        row.setdefault("wltp_consumption_kwh_100km", None)
        if isinstance(row.get("extraction_payload"), dict):
            row["extraction_payload"] = dict(row["extraction_payload"])
            for field in ("price_type", "price_valid_until", "wltp_consumption_kwh_100km"):
                row["extraction_payload"].setdefault(field, row.get(field))
        if row.get("wltp_consumption_kwh_100km") is not None:
            updated.append(row)
            continue
        if not row.get("source_hash") or not row.get("source_quote"):
            updated.append(row)
            continue
        if float(row.get("extraction_confidence") or 0) < MIN_CONFIDENCE:
            updated.append(row)
            continue

        value = exact_wltp_consumption(str(row["source_quote"]))
        if value is None:
            updated.append(row)
            continue

        row["wltp_consumption_kwh_100km"] = value
        if isinstance(row.get("extraction_payload"), dict):
            row["extraction_payload"] = {
                **row["extraction_payload"],
                "wltp_consumption_kwh_100km": value,
            }
        evidence.append(
            {
                "brand": row.get("brand"),
                "model": row.get("model"),
                "variant_name": row.get("variant_name"),
                "wltp_consumption_kwh_100km": value,
                "source_url": row.get("source_url"),
            }
        )
        updated.append(row)
    return updated, evidence


def write_json(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], excluded: set[str] | None = None) -> None:
    excluded = excluded or set()
    fields = []
    for row in rows:
        for key in row:
            if key not in excluded and key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def run(dry_run: bool = False) -> dict:
    drafts = json.loads(DRAFTS_JSON.read_text(encoding="utf-8"))
    canonical = json.loads(CANONICAL_JSON.read_text(encoding="utf-8"))
    updated_drafts, draft_evidence = backfill_rows(drafts)
    updated_canonical, canonical_evidence = backfill_rows(canonical)

    if not dry_run:
        write_json(DRAFTS_JSON, updated_drafts)
        write_csv(DRAFTS_CSV, updated_drafts, {"extraction_payload", "validation_errors"})
        write_json(CANONICAL_JSON, updated_canonical)
        write_csv(CANONICAL_CSV, updated_canonical)

    return {
        "dry_run": dry_run,
        "drafts_updated": len(draft_evidence),
        "canonical_variants_updated": len(canonical_evidence),
        "canonical_evidence": canonical_evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill unambiguous WLTP consumption from stored source quotes.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(dry_run=args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
