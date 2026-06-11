import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RENDERED_SOURCES = ROOT / "data/extraction/browser_rendered_sources.csv"
DEFAULT_CSV_OUT = ROOT / "data/extraction/rendered_extraction_batch.csv"
DEFAULT_JSON_OUT = ROOT / "data/extraction/rendered_extraction_batch.json"


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "batch_order",
        "brand",
        "model",
        "source_type",
        "url",
        "source_domain",
        "research_rank",
        "research_confidence",
        "content_hash",
        "content_type",
        "source_validation",
        "preflight_status",
        "source_text_path",
        "extraction_status",
        "batch_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_rendered_batch(rendered_rows, limit=None):
    ready_rows = [
        row
        for row in rendered_rows
        if row.get("render_status") == "rendered_source_ready"
        and row.get("extraction_status") == "queued"
        and row.get("source_hash")
        and row.get("source_text_path")
        and Path(row["source_text_path"]).exists()
    ]
    ready_rows.sort(key=lambda row: int(row.get("rank") or 999))
    if limit is not None:
        ready_rows = ready_rows[:limit]

    return [
        {
            "batch_order": index,
            "brand": row["brand"],
            "model": row["model"],
            "source_type": "manufacturer_rendered_model_page",
            "url": row["source_url"],
            "source_domain": row["source_domain"],
            "research_rank": row["rank"],
            "research_confidence": "high",
            "content_hash": row["source_hash"],
            "content_type": "text/plain; rendered",
            "source_validation": "reachable_official_model_source",
            "preflight_status": "ready_for_ai_extraction",
            "source_text_path": row["source_text_path"],
            "extraction_status": "ready_for_ai_extraction",
            "batch_reason": "browser_rendered_official_source",
        }
        for index, row in enumerate(ready_rows, start=1)
    ]


def main():
    parser = argparse.ArgumentParser(description="Build AI extraction batch from rendered official source text.")
    parser.add_argument("--source-file", default=str(DEFAULT_RENDERED_SOURCES))
    parser.add_argument("--csv-out", default=str(DEFAULT_CSV_OUT))
    parser.add_argument("--json-out", default=str(DEFAULT_JSON_OUT))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    batch = build_rendered_batch(read_csv(Path(args.source_file)), limit=args.limit)
    write_csv(Path(args.csv_out), batch)
    write_json(Path(args.json_out), batch)
    print(f"Rendered extraction batch: {len(batch)}")
    for row in batch:
        print(f"{row['batch_order']}. {row['brand']} {row['model']}")


if __name__ == "__main__":
    main()
