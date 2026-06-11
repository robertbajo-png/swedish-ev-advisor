import csv
import json
from pathlib import Path

from canonical_model_names import canonical_model_lookup, canonicalize_model_row


ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "data/extraction/next_extraction_plan.csv"
OUT_JSON = ROOT / "data/extraction/next_extraction_plan.json"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("records", payload) if isinstance(payload, dict) else payload


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


def model_key(row: dict) -> str:
    return f"{row.get('brand', '').strip().lower()}|{row.get('model', '').strip().lower()}"


def canonical_plan_row(row: dict, lookup: dict[tuple[str, str], str]) -> dict:
    source_model = row.get("model", "")
    canonicalized = canonicalize_model_row(row, lookup)
    if canonicalized.get("model") != source_model:
        canonicalized = {
            **canonicalized,
            "source_model": source_model,
            "priority_reason": f"{row.get('priority_reason', '')}; canonical_alias:{source_model}->{canonicalized.get('model')}".strip("; "),
        }
    return canonicalized


def public_model_keys() -> set[str]:
    return {model_key(row) for row in read_json(ROOT / "public/data/public_ev_variants.json")}


def draft_model_keys() -> set[str]:
    rows = read_json(ROOT / "data/extraction/extracted_variant_drafts.json")
    rows += read_json(ROOT / "data/review/variant_review_queue.json")
    return {model_key(row) for row in rows}


def attempted_empty_source_keys() -> set[tuple[str, str, str, str]]:
    rows = read_json(ROOT / "data/extraction/extraction_attempts.json")
    return {
        (
            row.get("brand", "").strip().lower(),
            row.get("model", "").strip().lower(),
            row.get("url", ""),
            row.get("content_hash", ""),
        )
        for row in rows
        if row.get("status") in {"no_drafts_created", "error"}
    }


def source_attempt_key(row: dict) -> tuple[str, str, str, str]:
    return (
        row.get("brand", "").strip().lower(),
        row.get("model", "").strip().lower(),
        row.get("url", ""),
        row.get("content_hash", ""),
    )


def ready_static_rows() -> list[dict]:
    rows = []
    for row in read_csv(ROOT / "data/extraction/mvp_extraction_preflight.csv"):
        if row.get("preflight_status") != "ready_for_ai_extraction":
            continue
        rows.append(
            {
                "brand": row["brand"],
                "model": row["model"],
                "rank": int(row.get("research_rank") or 999),
                "source_type": row["source_type"],
                "url": row["url"],
                "source_domain": row["source_domain"],
                "source_file": "data/extraction/mvp_extraction_preflight.csv",
                "source_text_path": "",
                "content_hash": row["source_hash_current"] or row["content_hash"],
                "extraction_status": "ready_for_ai_extraction",
                "priority_reason": "static_source_preflight_ready",
            }
        )
    return rows


def model_source_key(row: dict) -> tuple[str, str, str]:
    return (row.get("brand", "").strip().lower(), row.get("model", "").strip().lower(), row.get("url", ""))


def preflighted_model_sources() -> set[tuple[str, str, str]]:
    rows = set()
    for row in read_csv(ROOT / "data/extraction/mvp_extraction_preflight.csv"):
        if not row.get("url"):
            continue
        errors = row.get("preflight_errors", "")
        if (
            row.get("preflight_status") == "blocked"
            and "source_hash_changed" in errors
            and "source_text_too_short" not in errors
            and "fetch_failed" not in errors
        ):
            continue
        rows.add(model_source_key(row))
    return rows


def queued_static_rows() -> list[dict]:
    rows = []
    seen = preflighted_model_sources()
    for row in read_csv(ROOT / "data/canonical/mvp_extraction_queue.csv"):
        if row.get("source_validation") != "reachable_official_model_source":
            continue
        if model_source_key(row) in seen:
            continue
        if row.get("source_type") not in {"manufacturer_specs_page", "manufacturer_model_page", "manufacturer_price_list"}:
            continue
        rows.append(
            {
                "brand": row["brand"],
                "model": row["model"],
                "rank": int(row.get("research_rank") or 999),
                "source_type": row["source_type"],
                "url": row["url"],
                "source_domain": row["source_domain"],
                "source_file": "data/canonical/mvp_extraction_queue.csv",
                "source_text_path": "",
                "content_hash": row.get("content_hash", ""),
                "extraction_status": "needs_preflight",
                "priority_reason": "reachable_official_source_not_preflighted",
            }
        )
    return rows


def ready_rendered_rows() -> list[dict]:
    rows = []
    for row in read_csv(ROOT / "data/extraction/rendered_extraction_batch.csv"):
        if row.get("extraction_status") != "ready_for_ai_extraction":
            continue
        rows.append(
            {
                "brand": row["brand"],
                "model": row["model"],
                "rank": int(row.get("research_rank") or 999),
                "source_type": row["source_type"],
                "url": row["url"],
                "source_domain": row["source_domain"],
                "source_file": "data/extraction/rendered_extraction_batch.csv",
                "source_text_path": row.get("source_text_path", ""),
                "content_hash": row["content_hash"],
                "extraction_status": "ready_for_ai_extraction",
                "priority_reason": "browser_rendered_text_ready",
            }
        )
    return rows


def blocked_rows() -> list[dict]:
    rows = []
    for row in read_csv(ROOT / "data/mvp/mvp_remaining_work.csv"):
        if row.get("next_strategy") in {"source_discovery_required", "browser_rendered_required", "configurator_extraction_required"}:
            rows.append(
                {
                    "brand": row["brand"],
                    "model": row["model"],
                    "rank": int(row.get("rank") or 999),
                    "source_type": row.get("source_type", ""),
                    "url": row.get("source_url", ""),
                    "source_domain": "",
                    "source_file": "",
                    "source_text_path": "",
                    "content_hash": "",
                    "extraction_status": "blocked",
                    "priority_reason": row.get("next_strategy", "blocked"),
                }
            )
    return rows


def build_plan(include_public: bool = False, include_existing_drafts: bool = False) -> list[dict]:
    canonical_lookup = canonical_model_lookup()
    public_keys = set() if include_public else public_model_keys()
    draft_keys = set() if include_existing_drafts else draft_model_keys()
    empty_attempts = attempted_empty_source_keys()
    by_model = {}

    status_priority = {"ready_for_ai_extraction": 0, "needs_preflight": 1, "blocked": 2}

    for raw_row in ready_rendered_rows() + ready_static_rows() + queued_static_rows() + blocked_rows():
        row = canonical_plan_row(raw_row, canonical_lookup)
        key = model_key(row)
        if key in public_keys or key in draft_keys:
            continue
        if source_attempt_key(row) in empty_attempts:
            continue
        current = by_model.get(key)
        if current is None or (status_priority.get(row["extraction_status"], 9), row["rank"]) < (
            status_priority.get(current["extraction_status"], 9),
            current["rank"],
        ):
            by_model[key] = row

    rows = list(by_model.values())
    status_rank = {"ready_for_ai_extraction": 0, "needs_preflight": 1, "blocked": 2}
    rows.sort(key=lambda row: (status_rank.get(row["extraction_status"], 9), row["rank"]))
    for index, row in enumerate(rows, start=1):
        row["plan_order"] = index
    return rows


def summarize(rows: list[dict]) -> dict:
    counts = {}
    for row in rows:
        key = row["extraction_status"]
        counts[key] = counts.get(key, 0) + 1
    return {
        "planned_models": len(rows),
        "by_status": dict(sorted(counts.items())),
        "next_ready": next((row for row in rows if row["extraction_status"] == "ready_for_ai_extraction"), None),
        "top_blocker": next((row for row in rows if row["extraction_status"] == "blocked"), None),
    }


def main() -> None:
    rows = build_plan()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT_CSV, rows)
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
