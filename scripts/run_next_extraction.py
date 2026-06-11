import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from build_next_extraction_plan import build_plan, summarize
from extract_manufacturer_specs import safe_extract, write_outputs
from supabase_client import load_local_env


ROOT = Path(__file__).resolve().parents[1]
RUN_LOG = ROOT / "data/extraction/extraction_run_log.json"
ATTEMPTS_LOG = ROOT / "data/extraction/extraction_attempts.json"


def write_batch(path: Path, rows: list[dict]) -> None:
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


def ready_rows(limit: int | None = None) -> list[dict]:
    rows = [row for row in build_plan() if row["extraction_status"] == "ready_for_ai_extraction"]
    return rows[:limit] if limit else rows


def needs_preflight_rows(limit: int | None = None) -> list[dict]:
    rows = [row for row in build_plan() if row["extraction_status"] == "needs_preflight"]
    return rows[:limit] if limit else rows


def run_python_script(script: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / script)], check=True, cwd=ROOT)


def append_log(entry: dict) -> None:
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(RUN_LOG.read_text(encoding="utf-8")) if RUN_LOG.exists() else []
    existing.append(entry)
    RUN_LOG.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_attempts(attempts: list[dict]) -> None:
    if not attempts:
        return
    ATTEMPTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(ATTEMPTS_LOG.read_text(encoding="utf-8")) if ATTEMPTS_LOG.exists() else []
    by_key = {
        (row.get("brand"), row.get("model"), row.get("url"), row.get("content_hash")): row
        for row in existing
    }
    for row in attempts:
        by_key[(row.get("brand"), row.get("model"), row.get("url"), row.get("content_hash"))] = row
    ATTEMPTS_LOG.write_text(json.dumps(list(by_key.values()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(limit: int | None = None, dry_run: bool = False) -> dict:
    load_local_env()
    selected = ready_rows(limit)
    batch_path = ROOT / "data/extraction/next_extraction_batch.csv"
    write_batch(batch_path, selected)

    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "selected": len(selected),
        "selected_models": [f"{row['brand']} {row['model']}" for row in selected],
        "needs_preflight_next": [f"{row['brand']} {row['model']}" for row in needs_preflight_rows(limit=5)],
        "drafts_created": 0,
        "errors": [],
        "post_steps": [],
        "plan_summary": summarize(build_plan()),
    }

    if dry_run or not selected:
        append_log(report)
        return report

    if not os.environ.get("OPENAI_API_KEY"):
        report["errors"].append({"error": "OPENAI_API_KEY is required for non-dry-run extraction"})
        append_log(report)
        return report

    drafts = []
    attempts = []
    for row in selected:
        try:
            extracted = safe_extract(row)
            drafts.extend(extracted)
            attempts.append(
                {
                    "attempted_at": datetime.now(timezone.utc).isoformat(),
                    "brand": row["brand"],
                    "model": row["model"],
                    "url": row["url"],
                    "content_hash": row.get("content_hash", ""),
                    "drafts_created": len(extracted),
                    "status": "drafts_created" if extracted else "no_drafts_created",
                }
            )
        except Exception as error:
            report["errors"].append({"brand": row["brand"], "model": row["model"], "url": row["url"], "error": str(error)})
            attempts.append(
                {
                    "attempted_at": datetime.now(timezone.utc).isoformat(),
                    "brand": row["brand"],
                    "model": row["model"],
                    "url": row["url"],
                    "content_hash": row.get("content_hash", ""),
                    "drafts_created": 0,
                    "status": "error",
                    "error": str(error),
                }
            )

    append_attempts(attempts)
    report["attempts"] = attempts
    if drafts:
        write_outputs(drafts, append=True)
        report["drafts_created"] = len(drafts)
        for script in ("validate_extracted_variants.py", "export_public_ev_data.py", "seed_local_sqlite.py", "export_public_from_sqlite.py"):
            run_python_script(script)
            report["post_steps"].append(script)

    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    append_log(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the next ready official-source extraction batch.")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(limit=args.limit, dry_run=args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
