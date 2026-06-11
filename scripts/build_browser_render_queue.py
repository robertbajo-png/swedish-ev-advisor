import argparse
import csv
import json
from pathlib import Path

from build_next_extraction_plan import build_plan


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMAINING_WORK = ROOT / "data/mvp/mvp_remaining_work.csv"
DEFAULT_RESOLUTIONS = ROOT / "data/mvp/blocker_resolution/blocked_model_resolutions.csv"
DEFAULT_CSV_OUT = ROOT / "data/mvp/browser_render_queue.csv"
DEFAULT_JSON_OUT = ROOT / "data/mvp/browser_render_queue.json"


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "mvp_scope",
        "brand",
        "model",
        "registrations_ytd",
        "source_url",
        "source_validation",
        "render_reason",
        "target_strategy",
        "queue_status",
        "priority",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def int_value(value):
    try:
        return int(str(value or "0").strip())
    except ValueError:
        return 0


def model_key(row):
    return (row.get("brand", "").strip().lower(), row.get("model", "").strip().lower())


def browser_candidate_urls(resolution_rows):
    candidates = {}
    for row in resolution_rows:
        if row.get("resolution_action") != "browser_render_official_source":
            continue
        if row.get("candidate_url"):
            candidates[model_key(row)] = row["candidate_url"]
    return candidates


def build_browser_render_queue_from_resolutions(resolution_rows, limit=None):
    allowed_actions = {
        "browser_render_official_source",
        "prefer_static_specs_over_configurator",
        "validate_research_candidate",
    }
    rows = [
        row
        for row in resolution_rows
        if row.get("resolution_action") in allowed_actions
        and row.get("candidate_url")
    ]
    rows.sort(key=lambda row: int_value(row.get("rank")))
    if limit is not None:
        rows = rows[:limit]

    queue = []
    for index, row in enumerate(rows, start=1):
        queue.append(
            {
                "rank": row.get("rank", ""),
                "mvp_scope": "top_30",
                "brand": row.get("brand", ""),
                "model": row.get("model", ""),
                "registrations_ytd": "",
                "source_url": row.get("candidate_url", ""),
                "source_validation": "",
                "render_reason": row.get("resolution_action", ""),
                "target_strategy": "browser_rendered_fetch",
                "queue_status": "queued",
                "priority": index,
                "notes": (
                    "Fetch candidate official source with a rendered browser. "
                    "Rendered text still goes through AI extraction and hard validation before public use."
                ),
            }
        )
    return queue


def build_browser_render_queue(remaining_rows, limit=None):
    candidates = [
        row
        for row in remaining_rows
        if row.get("next_strategy") == "browser_rendered_required"
    ]
    candidates.sort(key=lambda row: int_value(row.get("rank")))

    if limit is not None:
        candidates = candidates[:limit]

    queue = []
    for index, row in enumerate(candidates, start=1):
        queue.append(
            {
                "rank": row.get("rank", ""),
                "mvp_scope": row.get("mvp_scope", ""),
                "brand": row.get("brand", ""),
                "model": row.get("model", ""),
                "registrations_ytd": row.get("registrations_ytd", ""),
                "source_url": row.get("source_url", ""),
                "source_validation": row.get("source_validation", ""),
                "render_reason": row.get("reason", ""),
                "target_strategy": "browser_rendered_fetch",
                "queue_status": "queued",
                "priority": index,
                "notes": (
                    "Fetch with a rendered browser, then store source hash/text before AI extraction. "
                    "Mobility Sweden remains market presence only."
                ),
            }
        )

    return queue


def build_browser_render_queue_from_plan(plan_rows, resolution_rows=None, limit=None):
    candidate_urls = browser_candidate_urls(resolution_rows or [])
    candidates = [
        row
        for row in plan_rows
        if row.get("extraction_status") == "blocked"
        and row.get("priority_reason") == "browser_rendered_required"
        and row.get("url")
    ]
    candidates.sort(key=lambda row: int_value(row.get("rank")))

    if limit is not None:
        candidates = candidates[:limit]

    queue = []
    for index, row in enumerate(candidates, start=1):
        queue.append(
            {
                "rank": row.get("rank", ""),
                "mvp_scope": "top_30",
                "brand": row.get("brand", ""),
                "model": row.get("model", ""),
                "registrations_ytd": "",
                "source_url": candidate_urls.get(model_key(row), row.get("url", "")),
                "source_validation": "",
                "render_reason": row.get("priority_reason", ""),
                "target_strategy": "browser_rendered_fetch",
                "queue_status": "queued",
                "priority": index,
                "notes": (
                    "Fetch with a rendered browser from the current next-extraction plan. "
                    "Rows already public or in draft/review are excluded upstream."
                ),
            }
        )
    return queue


def main():
    parser = argparse.ArgumentParser(
        description="Build the MVP queue for official sources that require browser rendering."
    )
    parser.add_argument("--input", default=str(DEFAULT_REMAINING_WORK))
    parser.add_argument("--csv-out", default=str(DEFAULT_CSV_OUT))
    parser.add_argument("--json-out", default=str(DEFAULT_JSON_OUT))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--from-remaining", action="store_true")
    parser.add_argument("--from-resolutions", action="store_true")
    args = parser.parse_args()

    queue = (
        build_browser_render_queue(read_csv(Path(args.input)), limit=args.limit)
        if args.from_remaining
        else build_browser_render_queue_from_resolutions(read_csv(DEFAULT_RESOLUTIONS), limit=args.limit)
        if args.from_resolutions
        else build_browser_render_queue_from_plan(build_plan(), read_csv(DEFAULT_RESOLUTIONS), limit=args.limit)
    )
    write_csv(Path(args.csv_out), queue)
    write_json(Path(args.json_out), queue)
    print(f"Wrote {len(queue)} browser-render queue rows to {args.csv_out}")


if __name__ == "__main__":
    main()
