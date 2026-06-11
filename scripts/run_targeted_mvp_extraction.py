import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from extract_manufacturer_specs import safe_extract, write_outputs
from supabase_client import load_local_env


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data/extraction/targeted_mvp_extraction_log.json"
BATCH_PATH = ROOT / "data/extraction/targeted_mvp_extraction_batch.csv"

SOURCE_PRIORITY = {
    "manufacturer_rendered_specs_page": 0,
    "manufacturer_rendered_model_page": 0,
    "manufacturer_specs_page": 0,
    "manufacturer_model_page": 1,
    "manufacturer_price_list": 2,
}

POST_STEPS = (
    "validate_extracted_variants.py",
    "export_public_ev_data.py",
    "seed_local_sqlite.py",
    "export_public_from_sqlite.py",
    "export_pipeline_status.py",
    "build_mvp_coverage_report.py",
    "generate_sitemap.py",
)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("records") or payload.get("variants") or payload.get("rows") or []
    return payload


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


def model_key(row: dict) -> str:
    return f"{row.get('brand', '').strip().lower()}|{row.get('model', '').strip().lower()}"


def public_model_keys() -> set[str]:
    return {model_key(row) for row in read_json(ROOT / "public/data/public_ev_variants.json")}


def draft_or_review_model_keys() -> set[str]:
    rows = read_json(ROOT / "data/extraction/extracted_variant_drafts.json")
    rows += read_json(ROOT / "data/review/variant_review_queue.json")
    return {model_key(row) for row in rows}


def coverage_rows() -> list[dict]:
    rows = read_json(ROOT / "data/mvp/mvp_coverage_report.json")
    if rows:
        return rows
    return read_csv(ROOT / "data/mvp/mvp_remaining_work.csv")


def remaining_candidate_keys(include_existing_drafts: bool = False) -> set[str]:
    public_keys = public_model_keys()
    existing_keys = set() if include_existing_drafts else draft_or_review_model_keys()
    keys = set()
    for row in coverage_rows():
        key = model_key(row)
        if not key or key == "|":
            continue
        status = row.get("coverage_status") or row.get("next_strategy") or ""
        if key in public_keys or key in existing_keys:
            continue
        if status in {"public", "done_or_in_review"}:
            continue
        if status in {
            "ready_for_static_extraction",
            "needs_source_discovery",
            "needs_browser_rendered_extraction",
            "candidate_available",
            "needs_batch_selection",
            "reachable_official_model_source",
        } or row.get("source_validation") == "reachable_official_model_source":
            keys.add(key)
    return keys


def official_sources() -> list[dict]:
    sources = []
    for path in (
        ROOT / "data/canonical/manufacturer_sources_mvp_validated.csv",
        ROOT / "data/canonical/manufacturer_sources_validated.csv",
        ROOT / "data/canonical/mvp_extraction_queue.csv",
        ROOT / "data/extraction/rendered_extraction_batch.csv",
    ):
        for row in read_csv(path):
            if row.get("source_validation") != "reachable_official_model_source":
                continue
            if row.get("source_type") not in SOURCE_PRIORITY:
                continue
            if not row.get("url"):
                continue
            sources.append(row)
    return sources


def selected_rows(limit: int | None = None, include_existing_drafts: bool = False) -> list[dict]:
    candidates = remaining_candidate_keys(include_existing_drafts=include_existing_drafts)
    by_model: dict[str, dict] = {}
    for row in official_sources():
        key = model_key(row)
        if key not in candidates:
            continue
        current = by_model.get(key)
        current_rank = SOURCE_PRIORITY.get(current.get("source_type", ""), 99) if current else 99
        row_rank = SOURCE_PRIORITY.get(row.get("source_type", ""), 99)
        if current is None or row_rank < current_rank:
            by_model[key] = {
                "brand": row.get("brand", ""),
                "model": row.get("model", ""),
                "source_type": row.get("source_type", ""),
                "url": row.get("url", ""),
                "source_domain": row.get("source_domain", ""),
                "content_hash": row.get("content_hash", ""),
                "source_text_path": row.get("source_text_path", ""),
                "source_validation": row.get("source_validation", ""),
            }
    rows = sorted(by_model.values(), key=lambda row: (row["brand"], row["model"]))
    return rows[:limit] if limit else rows


def run_post_steps() -> list[str]:
    completed = []
    for script in POST_STEPS:
        subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=True)
        completed.append(script)
    return completed


def append_log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(LOG_PATH.read_text(encoding="utf-8")) if LOG_PATH.exists() else []
    existing.append(entry)
    LOG_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(limit: int | None, dry_run: bool, include_existing_drafts: bool) -> dict:
    load_local_env()
    rows = selected_rows(limit=limit, include_existing_drafts=include_existing_drafts)
    write_csv(BATCH_PATH, rows)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "selected": len(rows),
        "selected_models": [f"{row['brand']} {row['model']}" for row in rows],
        "drafts_created": 0,
        "errors": [],
        "post_steps": [],
    }
    if dry_run or not rows:
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        append_log(report)
        return report
    if not os.environ.get("OPENAI_API_KEY"):
        report["errors"].append({"error": "OPENAI_API_KEY is required"})
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        append_log(report)
        return report

    drafts = []
    for row in rows:
        try:
            extracted = safe_extract(row)
            drafts.extend(extracted)
        except Exception as error:
            report["errors"].append(
                {
                    "brand": row["brand"],
                    "model": row["model"],
                    "url": row["url"],
                    "error": str(error),
                }
            )
    if drafts:
        write_outputs(drafts, append=True)
        report["drafts_created"] = len(drafts)
        report["post_steps"] = run_post_steps()
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    append_log(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run targeted AI extraction for remaining MVP models with official sources.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-existing-drafts", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.limit, args.dry_run, args.include_existing_drafts), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
