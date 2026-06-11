import argparse
import csv
import json
from pathlib import Path
from urllib.parse import urlparse


SOURCE_FIELDS = [
    ("model_page_url", "manufacturer_model_page"),
    ("price_list_url", "manufacturer_price_list"),
    ("specs_url", "manufacturer_specs_page"),
    ("configurator_url", "manufacturer_configurator"),
]


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


def boolish(value: str | bool | None) -> bool:
    return str(value).strip().lower() == "true"


def host(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def build_research_candidates(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    candidates = []
    mapping_queue = []
    seen = set()

    for row in rows:
        needs_mapping = boolish(row.get("needs_mapping"))
        if needs_mapping:
            mapping_queue.append(
                {
                    "rank": row["rank"],
                    "brand": row["brand"],
                    "canonical_model": row["canonical_model"],
                    "mobility_sweden_name": row["mobility_sweden_name"],
                    "confidence": row["confidence"],
                    "source_domain": row["source_domain"],
                    "reason": "needs_canonical_alias_before_source_extraction",
                    "notes": row["notes"],
                }
            )
            continue

        for field, source_type in SOURCE_FIELDS:
            url = row.get(field, "").strip()
            if not url:
                continue
            key = (row["brand"], row["canonical_model"], source_type, url)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "brand": row["brand"],
                    "model": row["canonical_model"],
                    "source_type": source_type,
                    "url": url,
                    "source_domain": row["source_domain"],
                    "url_host": host(url),
                    "country": "SE",
                    "language": "sv",
                    "research_confidence": row["confidence"],
                    "research_rank": row["rank"],
                    "source_validation": "research_candidate_unvalidated",
                    "extraction_status": "needs_validation",
                    "extraction_confidence": "",
                    "notes": row["notes"],
                }
            )

    candidates.sort(key=lambda item: (int(str(item["research_rank"]).rstrip("abcdefghijklmnopqrstuvwxyz") or 999), item["brand"], item["model"], item["source_type"]))
    return candidates, mapping_queue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research", type=Path, default=Path("data/canonical/source_research_top30.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/canonical"))
    args = parser.parse_args()

    candidates, mapping_queue = build_research_candidates(read_csv(args.research))
    write_csv(args.out_dir / "manufacturer_sources_research_candidates.csv", candidates)
    write_csv(args.out_dir / "source_research_needs_mapping.csv", mapping_queue)
    (args.out_dir / "manufacturer_sources_research_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out_dir / "source_research_needs_mapping.json").write_text(
        json.dumps(mapping_queue, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    high = sum(1 for row in candidates if row["research_confidence"].lower() == "high")
    print(f"Research source candidates: {len(candidates)}")
    print(f"High-confidence candidates: {high}")
    print(f"Needs-mapping research rows: {len(mapping_queue)}")


if __name__ == "__main__":
    main()
