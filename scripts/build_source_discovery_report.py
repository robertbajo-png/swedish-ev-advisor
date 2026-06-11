import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "data/mvp/source_discovery_phase4_report.json"
OUT_CSV = ROOT / "data/mvp/source_discovery_phase4_report.csv"
BRAND_RESOLVER_RULES = ROOT / "data/canonical/brand_source_resolver_rules.json"

ACCEPTED_SOURCE_TYPES = {
    "manufacturer_model_page",
    "manufacturer_price_list",
    "manufacturer_specs_page",
    "manufacturer_configurator",
    "manufacturer_rendered_model_page",
    "manufacturer_rendered_specs_page",
    "manufacturer_indexed_model_page",
    "manufacturer_official_override_source",
}
PUBLIC_STATUSES = {"published", "published_reviewed"}
APPROVED_SOURCE_VALIDATION = "reachable_official_model_source"
REJECTED_DOMAIN_HINTS = (
    "car.info",
    "ev-database",
    "wikipedia",
    "biluppgifter",
    "bytbil",
    "wayke",
    "blocket",
    "autouncle",
)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("records") or payload.get("rows") or []
    return payload


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
    return " ".join(str(value or "").strip().lower().split())


def canonical_model_alias(brand: str, model: str) -> str:
    brand_key = norm(brand)
    model_key_value = norm(model)
    if brand_key == "renault" and model_key_value in {"5 e-tech", "5 e tech", "r5 e-tech", "r5 e tech"}:
        return "5"
    return model_key_value


def model_key(row: dict) -> tuple[str, str]:
    brand = norm(row.get("brand"))
    model = row.get("model") or row.get("canonical_model")
    return brand, canonical_model_alias(brand, model)


def source_host(url: str) -> str:
    return urlparse(url or "").netloc.lower().replace("www.", "")


def clean_domain(value: str) -> str:
    return str(value or "").lower().replace("www.", "").strip("/")


def official_domain_matches(url: str, source_domain: str) -> bool:
    host = source_host(url)
    expected = clean_domain(source_domain)
    return bool(host and expected and (host == expected or host.endswith(f".{expected}")))


def public_model_keys() -> set[tuple[str, str]]:
    return {model_key(row) for row in read_json(ROOT / "public/data/public_ev_variants.json") if row.get("validation_status") in PUBLIC_STATUSES}


def resolver_rules() -> dict:
    if not BRAND_RESOLVER_RULES.exists():
        return {}
    return json.loads(BRAND_RESOLVER_RULES.read_text(encoding="utf-8"))


def group_by_model(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    output: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        output.setdefault(model_key(row), []).append(row)
    return output


def source_rank(row: dict) -> tuple[int, int, str]:
    type_rank = {
        "manufacturer_price_list": 0,
        "manufacturer_specs_page": 1,
        "manufacturer_rendered_specs_page": 1,
        "manufacturer_indexed_model_page": 2,
        "manufacturer_rendered_model_page": 2,
        "manufacturer_model_page": 3,
        "manufacturer_configurator": 4,
        "manufacturer_official_override_source": 5,
    }
    try:
        rank = int(str(row.get("research_rank") or row.get("rank") or 999).rstrip("abcdefghijklmnopqrstuvwxyz"))
    except ValueError:
        rank = 999
    return (type_rank.get(row.get("source_type"), 99), rank, row.get("url", ""))


def best_source(rows: list[dict]) -> dict | None:
    usable = [
        row
        for row in rows
        if row.get("source_validation") == APPROVED_SOURCE_VALIDATION
        and row.get("source_type") in ACCEPTED_SOURCE_TYPES
        and row.get("url")
    ]
    return sorted(usable, key=source_rank)[0] if usable else None


def build_report_rows() -> list[dict]:
    scope = read_csv(ROOT / "data/mvp/mvp_model_scope.csv")
    research = group_by_model(read_csv(ROOT / "data/canonical/manufacturer_sources_research_candidates.csv"))
    validated = group_by_model(read_csv(ROOT / "data/canonical/manufacturer_sources_mvp_validated.csv"))
    extraction = group_by_model(read_csv(ROOT / "data/canonical/mvp_extraction_queue.csv"))
    rendered = group_by_model(read_csv(ROOT / "data/extraction/rendered_extraction_batch.csv"))
    public_keys = public_model_keys()

    rows = []
    for item in scope:
        key = model_key(item)
        model_sources = [*validated.get(key, []), *rendered.get(key, [])]
        preferred = best_source(model_sources) or best_source(extraction.get(key, []))
        candidate_rows = research.get(key, [])
        validated_rows = validated.get(key, [])
        rendered_rows = [
            row for row in rendered.get(key, [])
            if row.get("source_validation") == APPROVED_SOURCE_VALIDATION
            and row.get("extraction_status") == "ready_for_ai_extraction"
        ]
        reachable_rows = [row for row in validated_rows if row.get("source_validation") == APPROVED_SOURCE_VALIDATION]
        blocked_rows = [row for row in validated_rows if row.get("source_validation") != APPROVED_SOURCE_VALIDATION]
        needs_mapping = "needs_mapping" in str(item.get("alias_rule", "")).lower()

        if key in public_keys:
            strategy = "published_mvp_source_complete"
        elif rendered_rows:
            strategy = "browser_or_indexed_source_ready"
        elif reachable_rows:
            strategy = "static_source_ready"
        elif needs_mapping:
            strategy = "quarantined_mapping"
        elif candidate_rows:
            strategy = "needs_source_validation_or_rendering"
        else:
            strategy = "needs_discovery"

        rows.append(
            {
                "rank": item.get("rank", ""),
                "mvp_scope": item.get("mvp_scope", ""),
                "brand": item.get("brand", ""),
                "model": item.get("model", ""),
                "registrations_ytd": item.get("registrations_ytd", ""),
                "candidate_count": len(candidate_rows),
                "validated_count": len(validated_rows),
                "reachable_official_count": len(reachable_rows),
                "rendered_ready_count": len(rendered_rows),
                "blocked_count": len(blocked_rows),
                "source_strategy": strategy,
                "preferred_source_type": preferred.get("source_type", "") if preferred else "",
                "preferred_source_url": preferred.get("url", "") if preferred else "",
                "preferred_source_domain": preferred.get("source_domain", "") if preferred else "",
                "preferred_source_hash": preferred.get("content_hash", "") if preferred else "",
                "public_model": str(key in public_keys).lower(),
            }
        )
    return rows


def validate_contract(report_rows: list[dict]) -> list[str]:
    errors = []
    scope_rows = read_csv(ROOT / "data/mvp/mvp_model_scope.csv")
    scope_keys = {model_key(row) for row in scope_rows}
    rules = resolver_rules()
    scope_brands = {row.get("brand", "") for row in scope_rows if row.get("brand")}

    for brand in sorted(scope_brands):
        if brand not in rules:
            errors.append(f"missing_brand_source_resolver_rule:{brand}")
            continue
        rule = rules[brand]
        if not rule.get("strategy"):
            errors.append(f"brand_resolver_missing_strategy:{brand}")
        if not rule.get("accepted_domains"):
            errors.append(f"brand_resolver_missing_domains:{brand}")
        if not rule.get("preferred_source_types"):
            errors.append(f"brand_resolver_missing_source_types:{brand}")

    extraction_rows = read_csv(ROOT / "data/canonical/mvp_extraction_queue.csv")
    rendered_rows = read_csv(ROOT / "data/extraction/rendered_extraction_batch.csv")
    all_source_rows = [
        *read_csv(ROOT / "data/canonical/manufacturer_sources_research_candidates.csv"),
        *read_csv(ROOT / "data/canonical/manufacturer_sources_mvp_validated.csv"),
        *extraction_rows,
        *rendered_rows,
    ]

    for row in all_source_rows:
        url = row.get("url", "")
        if any(hint in url.lower() for hint in REJECTED_DOMAIN_HINTS):
            errors.append(f"third_party_source_candidate:{row.get('brand')} {row.get('model')} {url}")
        if row.get("source_type") and row.get("source_type") not in ACCEPTED_SOURCE_TYPES:
            errors.append(f"unknown_source_type:{row.get('source_type')}:{url}")

    for row in extraction_rows:
        if model_key(row) not in scope_keys:
            errors.append(f"extraction_queue_outside_mvp_scope:{row.get('brand')} {row.get('model')}")
        if row.get("source_validation") != APPROVED_SOURCE_VALIDATION:
            errors.append(f"extraction_queue_non_official:{row.get('brand')} {row.get('model')}")
        if not official_domain_matches(row.get("url", ""), row.get("source_domain", "")):
            errors.append(f"extraction_queue_domain_mismatch:{row.get('brand')} {row.get('model')} {row.get('url')}")
        if not row.get("content_hash"):
            errors.append(f"extraction_queue_missing_hash:{row.get('brand')} {row.get('model')} {row.get('url')}")

    for row in rendered_rows:
        if row.get("source_validation") == APPROVED_SOURCE_VALIDATION and not row.get("content_hash"):
            errors.append(f"rendered_official_missing_hash:{row.get('brand')} {row.get('model')} {row.get('url')}")
        if row.get("source_validation") == APPROVED_SOURCE_VALIDATION and not row.get("source_text_path"):
            errors.append(f"rendered_official_missing_text:{row.get('brand')} {row.get('model')} {row.get('url')}")

    missing_discovery = [
        row for row in report_rows
        if row["candidate_count"] == 0
        and row["reachable_official_count"] == 0
        and row["rendered_ready_count"] == 0
    ]
    for row in missing_discovery:
        errors.append(f"mvp_model_without_source_candidate:{row['brand']} {row['model']}")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and optionally verify the Phase 4 source discovery report.")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    rows = build_report_rows()
    errors = validate_contract(rows)
    summary = {
        "mvp_models": len(rows),
        "public_models": sum(1 for row in rows if row["public_model"] == "true"),
        "models_with_candidates": sum(1 for row in rows if int(row["candidate_count"]) > 0),
        "models_with_reachable_official": sum(1 for row in rows if int(row["reachable_official_count"]) > 0),
        "models_with_rendered_ready": sum(1 for row in rows if int(row["rendered_ready_count"]) > 0),
        "brand_resolver_rules": len(resolver_rules()),
        "strategies": {},
        "errors": errors,
    }
    for row in rows:
        summary["strategies"][row["source_strategy"]] = summary["strategies"].get(row["source_strategy"], 0) + 1

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT_CSV, rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.verify and errors:
        sys.exit("Phase 4 source discovery contract failed")


if __name__ == "__main__":
    main()
