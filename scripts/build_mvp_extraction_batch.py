import argparse
import csv
import json
from pathlib import Path


STATIC_SOURCE_TYPES = {"manufacturer_specs_page", "manufacturer_model_page", "manufacturer_price_list"}


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


def rank_value(value: str) -> int:
    digits = "".join(char for char in str(value) if char.isdigit())
    return int(digits) if digits else 999


def source_score(row: dict) -> tuple[int, int, int]:
    source_type = row["source_type"]
    content_type = row.get("content_type", "").lower()
    if source_type == "manufacturer_specs_page":
        source_quality = 1
    elif source_type == "manufacturer_price_list" and "pdf" in content_type:
        source_quality = 2
    elif source_type == "manufacturer_model_page":
        source_quality = 3
    elif source_type == "manufacturer_price_list":
        source_quality = 4
    else:
        source_quality = 9
    confidence_penalty = 0 if row.get("research_confidence", "").lower() == "high" else 1
    return rank_value(row["research_rank"]), source_quality, confidence_penalty


def load_extracted_urls(paths: list[Path]) -> set[str]:
    urls = set()
    for path in paths:
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        urls.update(row.get("source_url", "") for row in rows)
    return {url for url in urls if url}


def load_blocked_preflight_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as handle:
        return {
            row["url"]
            for row in csv.DictReader(handle)
            if row.get("preflight_status") == "blocked"
        }


def build_batch(queue_rows: list[dict], limit: int, excluded_urls: set[str] | None = None) -> list[dict]:
    excluded_urls = excluded_urls or set()
    eligible = [
        row
        for row in queue_rows
        if row.get("source_validation") == "reachable_official_model_source"
        and row.get("source_type") in STATIC_SOURCE_TYPES
        and row.get("content_hash")
        and (row.get("source_type") != "manufacturer_price_list" or "pdf" in row.get("content_type", "").lower())
        and row.get("url") not in excluded_urls
    ]
    selected = sorted(eligible, key=source_score)[:limit]
    return [
        {
            "batch_order": index,
            "brand": row["brand"],
            "model": row["model"],
            "source_type": row["source_type"],
            "url": row["url"],
            "source_domain": row["source_domain"],
            "research_rank": row["research_rank"],
            "research_confidence": row["research_confidence"],
            "content_hash": row["content_hash"],
            "content_type": row["content_type"],
            "source_validation": row["source_validation"],
            "extraction_status": "ready_for_ai_extraction",
            "batch_reason": "static_reachable_official_source",
        }
        for index, row in enumerate(selected, start=1)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=Path("data/canonical/mvp_extraction_queue.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/extraction"))
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--include-previous", action="store_true")
    args = parser.parse_args()

    excluded_urls = set()
    if not args.include_previous:
        excluded_urls = load_extracted_urls(
            [
                args.out_dir / "extracted_variant_drafts.json",
                Path("data/review/variant_review_queue.json"),
            ]
        )
        excluded_urls.update(load_blocked_preflight_urls(args.out_dir / "mvp_extraction_preflight.csv"))
    batch = build_batch(read_csv(args.queue), args.limit, excluded_urls)
    write_csv(args.out_dir / "mvp_extraction_batch.csv", batch)
    (args.out_dir / "mvp_extraction_batch.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"MVP extraction batch: {len(batch)}")
    for row in batch:
        print(f"{row['batch_order']}. {row['brand']} {row['model']} - {row['source_type']}")


if __name__ == "__main__":
    main()
