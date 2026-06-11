import argparse
import csv
import json
from pathlib import Path
from urllib.parse import urlparse

from validate_research_sources import build_extraction_queue, validate_candidate


ROOT = Path(__file__).resolve().parents[1]
RESOLUTIONS_CSV = ROOT / "data/mvp/blocker_resolution/blocked_model_resolutions.csv"
VALIDATED_CSV = ROOT / "data/canonical/manufacturer_sources_mvp_validated.csv"
VALIDATED_JSON = ROOT / "data/canonical/manufacturer_sources_mvp_validated.json"
QUEUE_CSV = ROOT / "data/canonical/mvp_extraction_queue.csv"
QUEUE_JSON = ROOT / "data/canonical/mvp_extraction_queue.json"
APPLIED_CSV = ROOT / "data/mvp/blocker_resolution/applied_source_candidates.csv"
APPLIED_JSON = ROOT / "data/mvp/blocker_resolution/applied_source_candidates.json"


ACTION_TO_CONFIDENCE = {
    "prefer_static_specs_over_configurator": "high",
    "validate_research_candidate": "medium",
}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
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


def source_domain_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def candidate_rows(resolutions: list[dict]) -> list[dict]:
    rows = []
    for row in resolutions:
        action = row.get("resolution_action")
        if action not in ACTION_TO_CONFIDENCE:
            continue
        candidate_url = row.get("candidate_url", "").strip()
        if not candidate_url:
            continue
        rows.append(
            {
                "brand": row["brand"],
                "model": row["model"],
                "source_type": row.get("candidate_source_type") or "manufacturer_model_page",
                "url": candidate_url,
                "source_domain": source_domain_from_url(candidate_url),
                "research_rank": row.get("rank") or "999",
                "research_confidence": ACTION_TO_CONFIDENCE[action],
                "blocker_resolution_action": action,
                "blocker_resolution_reason": row.get("resolution_reason", ""),
            }
        )
    rows.sort(key=lambda row: (int(row["research_rank"]), row["brand"], row["model"], row["url"]))
    return rows


def merge_key(row: dict) -> tuple[str, str, str]:
    return (
        row.get("brand", "").strip().lower(),
        row.get("model", "").strip().lower(),
        row.get("url", "").strip(),
    )


def merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    rows = {merge_key(row): row for row in existing if row.get("url")}
    for row in new_rows:
        rows[merge_key(row)] = row
    return list(rows.values())


def run(dry_run: bool = False, timeout: int = 12) -> dict:
    candidates = candidate_rows(read_csv(RESOLUTIONS_CSV))
    report = {
        "dry_run": dry_run,
        "candidates": len(candidates),
        "selected_models": [f"{row['brand']} {row['model']}" for row in candidates],
        "validated": 0,
        "reachable": 0,
        "queue_models": 0,
    }
    if dry_run:
        return report

    validated = [validate_candidate(row, timeout=timeout) for row in candidates]
    merged_validated = merge_rows(read_csv(VALIDATED_CSV), validated)
    queue = build_extraction_queue(merged_validated)

    write_csv(APPLIED_CSV, validated)
    APPLIED_JSON.write_text(json.dumps(validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(VALIDATED_CSV, merged_validated)
    VALIDATED_JSON.write_text(json.dumps(merged_validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(QUEUE_CSV, queue)
    QUEUE_JSON.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report["validated"] = len(validated)
    report["reachable"] = sum(1 for row in validated if row.get("source_validation") == "reachable_official_model_source")
    report["queue_models"] = len(queue)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate source candidates produced by blocker resolution queues.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(run(dry_run=args.dry_run, timeout=args.timeout), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
