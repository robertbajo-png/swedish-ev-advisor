import argparse
import csv
import json
from pathlib import Path

from extract_manufacturer_specs import fetch_source_text


MIN_TEXT_LENGTH = 500


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


def preflight_row(row: dict) -> dict:
    try:
        text, source_hash = fetch_source_text(row["url"])
        hash_matches = source_hash == row.get("content_hash")
        text_length = len(text)
        source_is_official = row.get("source_validation") == "reachable_official_model_source"
        status = "ready_for_ai_extraction" if source_is_official and text_length >= MIN_TEXT_LENGTH else "blocked"
        errors = []
        if not hash_matches and status != "ready_for_ai_extraction":
            errors.append("source_hash_changed")
        if not hash_matches and status == "ready_for_ai_extraction":
            errors.append("source_hash_refreshed")
        if text_length < MIN_TEXT_LENGTH:
            errors.append("source_text_too_short")
        if not source_is_official:
            errors.append("source_not_reachable_official")
        return {
            **row,
            "preflight_status": status,
            "source_hash_current": source_hash,
            "source_hash_matches": str(hash_matches),
            "source_text_length": text_length,
            "source_text_preview": text[:500],
            "preflight_errors": ";".join(errors),
        }
    except Exception as error:
        return {
            **row,
            "preflight_status": "blocked",
            "source_hash_current": "",
            "source_hash_matches": "False",
            "source_text_length": 0,
            "source_text_preview": "",
            "preflight_errors": f"fetch_failed:{error}",
        }


def build_preflight(rows: list[dict]) -> list[dict]:
    return [preflight_row(row) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, default=Path("data/extraction/mvp_extraction_batch.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/extraction"))
    args = parser.parse_args()

    rows = build_preflight(read_csv(args.batch))
    write_csv(args.out_dir / "mvp_extraction_preflight.csv", rows)
    (args.out_dir / "mvp_extraction_preflight.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ready = sum(1 for row in rows if row["preflight_status"] == "ready_for_ai_extraction")
    print(f"Preflighted sources: {len(rows)}")
    print(f"Ready for AI extraction: {ready}")


if __name__ == "__main__":
    main()
