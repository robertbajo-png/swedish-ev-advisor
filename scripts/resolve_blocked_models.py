import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/mvp/blocker_resolution"


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


def norm(value: str) -> str:
    return " ".join(str(value or "").lower().replace("-", " ").split())


def model_key(row: dict) -> tuple[str, str]:
    return norm(row.get("brand")), norm(row.get("model"))


def candidate_keys(row: dict) -> list[tuple[str, str]]:
    brand, model = model_key(row)
    keys = [(brand, model)]
    if model.endswith(" eq"):
        keys.append((brand, model.removesuffix(" eq").strip()))
    else:
        keys.append((brand, f"{model} eq".strip()))
    if model == "5":
        keys.append((brand, "5 e tech"))
    return list(dict.fromkeys(keys))


def research_candidates() -> dict[tuple[str, str], list[dict]]:
    rows = [row for row in read_csv(ROOT / "data/canonical/mvp_blockers_resolution.csv") if row.get("type") == "source_url"]
    output = {}
    for row in rows:
        output.setdefault(model_key(row), []).append(row)
    return output


def health_by_model() -> dict[tuple[str, str], list[dict]]:
    output = {}
    for row in read_csv(ROOT / "data/mvp/source_health_report.csv"):
        output.setdefault(model_key(row), []).append(row)
    return output


def best_research_candidate(row: dict, candidates: dict[tuple[str, str], list[dict]], source_types: set[str]) -> dict | None:
    rows = []
    for key in candidate_keys(row):
        rows.extend(candidates.get(key, []))
    usable = [
        item
        for item in rows
        if item.get("safe_to_use") in {"true", "conditional", "True"}
        and item.get("source_type") in source_types
        and item.get("url")
    ]
    usable.sort(
        key=lambda item: (
            0 if item.get("confidence") == "high" else 1,
            0 if item.get("verification_status", "").startswith(("verified", "url_corrected")) else 1,
            0 if item.get("source_type") in {"manufacturer_specs_page", "manufacturer_price_list"} else 1,
        )
    )
    return usable[0] if usable else None


def resolve_row(row: dict, candidates: dict[tuple[str, str], list[dict]], health: dict[tuple[str, str], list[dict]]) -> dict:
    reason = row.get("priority_reason", "")
    health_rows = health.get(model_key(row), [])
    health_statuses = {item.get("health_status") for item in health_rows}

    if "fetch_timeout" in health_statuses:
        return {
            **row,
            "resolution_action": "browser_render_or_retry_with_backoff",
            "resolution_reason": "official_source_fetch_timeout",
            "candidate_url": row.get("url", ""),
            "candidate_source_type": row.get("source_type", ""),
        }
    if "source_hash_refresh_needed" in health_statuses:
        return {
            **row,
            "resolution_action": "refresh_source_hash_then_preflight",
            "resolution_reason": "source_changed_but_text_is_long_enough",
            "candidate_url": row.get("url", ""),
            "candidate_source_type": row.get("source_type", ""),
        }
    if reason == "source_discovery_required":
        candidate = best_research_candidate(row, candidates, {"manufacturer_specs_page", "manufacturer_price_list", "manufacturer_model_page"})
        return {
            **row,
            "resolution_action": "validate_research_candidate",
            "resolution_reason": "needs_official_source_validation",
            "candidate_url": candidate.get("url", "") if candidate else "",
            "candidate_source_type": candidate.get("source_type", "") if candidate else "",
        }
    if reason == "configurator_extraction_required":
        candidate = best_research_candidate(row, candidates, {"manufacturer_specs_page", "manufacturer_model_page"})
        return {
            **row,
            "resolution_action": "prefer_static_specs_over_configurator",
            "resolution_reason": "configurator_only_currently_selected",
            "candidate_url": candidate.get("url", row.get("url", "")) if candidate else row.get("url", ""),
            "candidate_source_type": candidate.get("source_type", row.get("source_type", "")) if candidate else row.get("source_type", ""),
        }
    if reason == "browser_rendered_required":
        candidate = best_research_candidate(row, candidates, {"manufacturer_specs_page", "manufacturer_price_list", "manufacturer_model_page"})
        return {
            **row,
            "resolution_action": "browser_render_official_source",
            "resolution_reason": "raw_fetch_blocked_or_page_not_rendered",
            "candidate_url": candidate.get("url", row.get("url", "")) if candidate else row.get("url", ""),
            "candidate_source_type": candidate.get("source_type", row.get("source_type", "")) if candidate else row.get("source_type", ""),
        }
    return {
        **row,
        "resolution_action": "manual_review",
        "resolution_reason": "no_deterministic_resolution_rule",
        "candidate_url": row.get("url", ""),
        "candidate_source_type": row.get("source_type", ""),
    }


def build_resolutions() -> list[dict]:
    blocked = [row for row in read_csv(ROOT / "data/extraction/next_extraction_plan.csv") if row.get("extraction_status") == "blocked"]
    candidates = research_candidates()
    health = health_by_model()
    resolutions = [resolve_row(row, candidates, health) for row in blocked]
    resolutions.sort(key=lambda row: int(row.get("rank") or 999))
    return resolutions


def split_queues(rows: list[dict]) -> dict[str, list[dict]]:
    queues = {}
    for row in rows:
        queues.setdefault(row["resolution_action"], []).append(row)
    return queues


def main() -> None:
    rows = build_resolutions()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "blocked_model_resolutions.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT_DIR / "blocked_model_resolutions.csv", rows)
    queues = split_queues(rows)
    for action, action_rows in queues.items():
        write_csv(OUT_DIR / f"{action}.csv", action_rows)
    print(json.dumps({"blocked_models": len(rows), "queues": {key: len(value) for key, value in sorted(queues.items())}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
