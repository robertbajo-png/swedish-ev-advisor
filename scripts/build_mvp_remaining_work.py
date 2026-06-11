import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BROWSER_RENDERED_DOMAINS = {"tesla.com", "volvocars.com"}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def model_key(row: dict) -> tuple[str, str]:
    return row["brand"], row["model"]


def extracted_model_keys() -> set[tuple[str, str]]:
    rows = read_json(ROOT / "data/extraction/extracted_variant_drafts.json")
    return {(row["brand"], row["model"]) for row in rows}


def review_model_keys() -> set[tuple[str, str]]:
    rows = read_json(ROOT / "data/review/variant_review_queue.json")
    return {(row["brand"], row["model"]) for row in rows}


def blocked_preflight_by_model() -> dict[tuple[str, str], str]:
    output = {}
    for row in read_csv(ROOT / "data/extraction/mvp_extraction_preflight.csv"):
        if row.get("preflight_status") == "blocked":
            output[(row["brand"], row["model"])] = row.get("preflight_errors", "preflight_blocked")
    return output


def strategy_for(row: dict, extracted: set[tuple[str, str]], review: set[tuple[str, str]], preflight_blocked: dict[tuple[str, str], str]) -> tuple[str, str]:
    key = model_key(row)
    domain = row.get("source_domain", "")
    if key in extracted:
        return "done_or_in_review", "already_has_extracted_draft"
    if key in review:
        return "review", "has_variant_in_review_queue"
    if key in preflight_blocked:
        return "source_revalidation_or_new_source", preflight_blocked[key]
    if domain in BROWSER_RENDERED_DOMAINS or row.get("source_validation") == "unreachable_or_redirect_problem":
        return "browser_rendered_required", "raw_http_blocked_or_unstable"
    if row.get("source_validation") == "needs_discovery":
        return "source_discovery_required", "no_reachable_official_source"
    if row.get("source_type") == "manufacturer_configurator":
        return "configurator_extraction_required", "only_configurator_source_available"
    return "candidate_available", "needs_batch_selection"


def build_remaining_work(scope_rows: list[dict], queue_rows: list[dict]) -> list[dict]:
    queue_by_model = {model_key(row): row for row in queue_rows}
    extracted = extracted_model_keys()
    review = review_model_keys()
    preflight_blocked = blocked_preflight_by_model()
    rows = []
    for scope in scope_rows:
        key = model_key(scope)
        queue = queue_by_model.get(key, {})
        strategy, reason = strategy_for({**scope, **queue}, extracted, review, preflight_blocked)
        rows.append(
            {
                "rank": scope["rank"],
                "mvp_scope": scope["mvp_scope"],
                "brand": scope["brand"],
                "model": scope["model"],
                "registrations_ytd": scope["registrations_ytd"],
                "source_url": queue.get("url", scope.get("source_url", "")),
                "source_type": queue.get("source_type", ""),
                "source_validation": queue.get("source_validation", scope.get("source_validation", "")),
                "next_strategy": strategy,
                "reason": reason,
            }
        )
    rows.sort(key=lambda row: int(row["rank"]))
    return rows


def main() -> None:
    rows = build_remaining_work(
        read_csv(ROOT / "data/mvp/mvp_model_scope.csv"),
        read_csv(ROOT / "data/canonical/mvp_extraction_queue.csv"),
    )
    out_dir = ROOT / "data/mvp"
    write_csv(out_dir / "mvp_remaining_work.csv", rows)
    (out_dir / "mvp_remaining_work.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {}
    for row in rows:
        counts[row["next_strategy"]] = counts.get(row["next_strategy"], 0) + 1
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
