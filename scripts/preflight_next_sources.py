import argparse
import csv
import json
from pathlib import Path

from build_next_extraction_plan import build_plan
from preflight_extraction_batch import preflight_row


ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "data/extraction/mvp_extraction_preflight.csv"
OUT_JSON = ROOT / "data/extraction/mvp_extraction_preflight.json"


def read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_preflight_row(row: dict) -> dict:
    return {
        "batch_order": row["plan_order"],
        "brand": row["brand"],
        "model": row["model"],
        "source_type": row["source_type"],
        "url": row["url"],
        "source_domain": row["source_domain"],
        "research_rank": row["rank"],
        "research_confidence": "high",
        "content_hash": row["content_hash"],
        "content_type": "",
        "source_validation": "reachable_official_model_source",
        "extraction_status": "ready_for_ai_extraction",
        "batch_reason": row["priority_reason"],
    }


def merge_key(row: dict) -> tuple[str, str, str]:
    return (row.get("brand", ""), row.get("model", ""), row.get("url", ""))


def merge_by_model_source(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    rows = {merge_key(row): row for row in existing if row.get("url")}
    for row in new_rows:
        rows[merge_key(row)] = row
    return list(rows.values())


def run(limit: int = 3, dry_run: bool = False) -> dict:
    selected = [row for row in build_plan() if row["extraction_status"] == "needs_preflight"][:limit]
    report = {
        "dry_run": dry_run,
        "selected": len(selected),
        "selected_models": [f"{row['brand']} {row['model']}" for row in selected],
        "ready": 0,
        "blocked": 0,
    }
    if dry_run:
        return report

    preflighted = [preflight_row(to_preflight_row(row)) for row in selected]
    report["ready"] = sum(1 for row in preflighted if row.get("preflight_status") == "ready_for_ai_extraction")
    report["blocked"] = sum(1 for row in preflighted if row.get("preflight_status") == "blocked")
    merged = merge_by_model_source(read_existing(OUT_CSV), preflighted)
    write_csv(OUT_CSV, merged)
    OUT_JSON.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight the next reachable official sources from the extraction plan.")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(limit=args.limit, dry_run=args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
