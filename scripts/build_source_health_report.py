import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "data/mvp/source_health_report.json"
OUT_CSV = ROOT / "data/mvp/source_health_report.csv"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def classify(row: dict) -> str:
    errors = row.get("preflight_errors", "")
    if row.get("preflight_status") == "ready_for_ai_extraction":
        return "ready"
    if "WinError 10060" in errors or "timed out" in errors.lower():
        return "fetch_timeout"
    if "source_hash_changed" in errors and row.get("source_text_length", "0").isdigit() and int(row["source_text_length"]) >= 500:
        return "source_hash_refresh_needed"
    if "source_text_too_short" in errors:
        return "source_text_too_short"
    if "fetch_failed" in errors:
        return "fetch_failed"
    return "blocked_other"


def build_report() -> dict:
    rows = []
    counts = {}
    for row in read_csv(ROOT / "data/extraction/mvp_extraction_preflight.csv"):
        status = classify(row)
        counts[status] = counts.get(status, 0) + 1
        rows.append(
            {
                "brand": row.get("brand", ""),
                "model": row.get("model", ""),
                "url": row.get("url", ""),
                "source_type": row.get("source_type", ""),
                "preflight_status": row.get("preflight_status", ""),
                "health_status": status,
                "source_text_length": row.get("source_text_length", ""),
                "preflight_errors": row.get("preflight_errors", ""),
            }
        )
    rows.sort(key=lambda row: (row["health_status"], row["brand"], row["model"]))
    return {"counts": dict(sorted(counts.items())), "rows": rows}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    report = build_report()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT_CSV, report["rows"])
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
