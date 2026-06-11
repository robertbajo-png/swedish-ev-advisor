import argparse
import csv
import json
from pathlib import Path


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


def research_action(source_validation: str) -> str:
    if source_validation == "needs_discovery":
        return "find_official_swedish_model_or_price_source"
    if source_validation == "unreachable_or_redirect_problem":
        return "verify_or_replace_blocked_official_source"
    return "inspect_before_extraction"


def build_queue(scope_rows: list[dict], limit: int | None = None) -> list[dict]:
    queue = []
    for row in scope_rows:
        if row.get("extraction_ready") == "True":
            continue
        rank = int(row["rank"])
        queue.append(
            {
                "priority": rank,
                "mvp_scope": row["mvp_scope"],
                "brand": row["brand"],
                "model": row["model"],
                "registrations_ytd": row["registrations_ytd"],
                "registrations_last_month": row["registrations_last_month"],
                "current_source_url": row["source_url"],
                "current_source_validation": row["source_validation"],
                "research_action": research_action(row["source_validation"]),
                "accepted_source_types": "official Swedish model page; official Swedish price list PDF; official Swedish technical specs PDF; official Swedish configurator",
                "rejected_source_types": "third-party comparison sites; dealer listing pages; Mobility Sweden as spec source",
                "notes": "Use Mobility Sweden only for market presence. Do not extract specs until an official source is reachable and validated.",
            }
        )

    queue.sort(key=lambda item: item["priority"])
    return queue[:limit] if limit else queue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, default=Path("data/mvp/mvp_model_scope.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/mvp"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    queue = build_queue(read_csv(args.scope), args.limit)
    write_csv(args.out_dir / "mvp_source_research_queue.csv", queue)
    (args.out_dir / "mvp_source_research_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    top_10 = sum(1 for row in queue if row["mvp_scope"] == "top_20" and row["priority"] <= 10)
    print(f"MVP source research queue: {len(queue)}")
    print(f"Top-10 blockers in queue: {top_10}")


if __name__ == "__main__":
    main()
