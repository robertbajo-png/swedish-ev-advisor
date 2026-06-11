import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "data/mvp/mvp_coverage_report.json"
OUT_MD = ROOT / "docs/mvp-coverage-report.md"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("records", payload) if isinstance(payload, dict) else payload


def key(row: dict) -> str:
    return f"{row.get('brand', '').lower()}|{row.get('model', '').lower()}"


def variant_counts(public_rows: list[dict]) -> dict[str, int]:
    counts = {}
    for row in public_rows:
        counts[key(row)] = counts.get(key(row), 0) + 1
    return counts


def classify(row: dict, public_count: int) -> str:
    if public_count > 0:
        return "public"
    if row.get("next_strategy") == "done_or_in_review":
        return "review_or_draft"
    if row.get("next_strategy") == "candidate_available":
        return "ready_for_static_extraction"
    if row.get("next_strategy") == "browser_rendered_required":
        return "needs_browser_rendered_extraction"
    if row.get("next_strategy") == "configurator_extraction_required":
        return "needs_configurator_extraction"
    if row.get("next_strategy") == "source_discovery_required":
        return "needs_source_discovery"
    return "unknown"


def build_report() -> dict:
    remaining = read_csv(ROOT / "data/mvp/mvp_remaining_work.csv")
    public_rows = read_json(ROOT / "public/data/public_ev_variants.json")
    counts = variant_counts(public_rows)
    rows = []
    status_counts = {}

    for row in remaining:
        public_count = counts.get(key(row), 0)
        status = classify(row, public_count)
        status_counts[status] = status_counts.get(status, 0) + 1
        rows.append(
            {
                "rank": int(row["rank"]),
                "brand": row["brand"],
                "model": row["model"],
                "registrations_ytd": int(row["registrations_ytd"]),
                "coverage_status": status,
                "public_variants": public_count,
                "next_strategy": row.get("next_strategy", ""),
                "source_url": row.get("source_url", ""),
                "reason": row.get("reason", ""),
            }
        )

    rows.sort(key=lambda row: row["rank"])
    return {
        "mvp_models": len(rows),
        "public_models": sum(1 for row in rows if row["coverage_status"] == "public"),
        "public_variants": len(public_rows),
        "coverage_by_status": dict(sorted(status_counts.items())),
        "highest_priority_next": next((row for row in rows if row["coverage_status"] != "public"), None),
        "rows": rows,
    }


def write_markdown(report: dict) -> None:
    lines = [
        "# MVP Coverage Report",
        "",
        "Top 30 Swedish EV model coverage based on Mobility Sweden market discovery and official manufacturer/importer sources.",
        "",
        f"- MVP models: {report['mvp_models']}",
        f"- Public models: {report['public_models']}",
        f"- Public variants: {report['public_variants']}",
        "",
        "## Coverage By Status",
        "",
    ]
    for status, count in report["coverage_by_status"].items():
        lines.append(f"- `{status}`: {count}")

    next_row = report["highest_priority_next"]
    if next_row:
        lines.extend(
            [
                "",
                "## Highest Priority Next",
                "",
                f"{next_row['rank']}. {next_row['brand']} {next_row['model']} - `{next_row['coverage_status']}`",
                f"Source: {next_row['source_url']}",
                f"Reason: {next_row['reason']}",
            ]
        )

    lines.extend(["", "## Model Detail", ""])
    for row in report["rows"]:
        lines.append(
            f"- {row['rank']}. {row['brand']} {row['model']}: `{row['coverage_status']}` "
            f"({row['public_variants']} public variants, {row['registrations_ytd']} YTD registrations)"
        )

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report)
    summary = {key: report[key] for key in ("mvp_models", "public_models", "public_variants", "coverage_by_status", "highest_priority_next")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
