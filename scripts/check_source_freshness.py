import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "data/mvp/source_freshness_report.json"
OUT_CSV = ROOT / "data/mvp/source_freshness_report.csv"
STATIC_SOURCE_TYPES = {
    "manufacturer_model_page",
    "manufacturer_price_list",
    "manufacturer_specs_page",
}
SKIP_SOURCE_TYPES = {
    "manufacturer_configurator",
    "manufacturer_rendered_model_page",
    "manufacturer_rendered_specs_page",
    "manufacturer_indexed_model_page",
    "manufacturer_official_override_source",
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


def fetch_hash(url: str, timeout: int) -> tuple[str, int | None, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "swedish-ev-advisor/0.1 (+https://swedish-ev-advisor.se)",
            "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.6",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            return hashlib.sha256(body).hexdigest(), response.status, response.headers.get("content-type", "")
    except HTTPError as error:
        return "", error.code, ""
    except (TimeoutError, URLError, OSError):
        return "", None, ""


def candidate_sources() -> list[dict]:
    rows = []
    seen = set()
    for path in (
        ROOT / "data/canonical/mvp_extraction_queue.csv",
        ROOT / "data/canonical/manufacturer_sources_mvp_validated.csv",
    ):
        for row in read_csv(path):
            if row.get("source_validation") != "reachable_official_model_source":
                continue
            key = row.get("url")
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append(row)
    rows.sort(key=lambda row: (row.get("brand", ""), row.get("model", ""), row.get("source_type", ""), row.get("url", "")))
    return rows


def check_sources(limit: int | None, timeout: int, verify: bool) -> dict:
    rows = candidate_sources()
    if limit:
        rows = rows[:limit]

    checked = []
    counts = {}
    for row in rows:
        source_type = row.get("source_type", "")
        existing_hash = row.get("content_hash", "")
        status = "skipped_non_static"
        current_hash = ""
        http_status = ""
        content_type = ""

        if source_type in STATIC_SOURCE_TYPES and existing_hash:
            current_hash, fetched_status, content_type = fetch_hash(row["url"], timeout)
            http_status = "" if fetched_status is None else str(fetched_status)
            if not current_hash:
                status = "fetch_failed"
            elif current_hash == existing_hash:
                status = "fresh"
            else:
                status = "source_hash_changed"
        elif source_type in SKIP_SOURCE_TYPES:
            status = "skipped_rendered_or_configurator"
        elif not existing_hash:
            status = "missing_stored_hash"

        counts[status] = counts.get(status, 0) + 1
        checked.append(
            {
                "brand": row.get("brand", ""),
                "model": row.get("model", ""),
                "source_type": source_type,
                "url": row.get("url", ""),
                "stored_hash": existing_hash,
                "current_hash": current_hash,
                "http_status": http_status,
                "content_type": content_type,
                "freshness_status": status,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    errors = []
    if verify:
        errors = [
            f"{row['freshness_status']}:{row['brand']} {row['model']} {row['url']}"
            for row in checked
            if row["freshness_status"] in {"source_hash_changed", "missing_stored_hash"}
        ]

    report = {"checked": len(checked), "counts": dict(sorted(counts.items())), "errors": errors, "rows": checked}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT_CSV, checked)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Check freshness of reachable official static source hashes.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    report = check_sources(limit=args.limit, timeout=args.timeout, verify=args.verify)
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, ensure_ascii=False, indent=2))
    if args.verify and report["errors"]:
        raise SystemExit("Source freshness contract failed")


if __name__ == "__main__":
    main()
