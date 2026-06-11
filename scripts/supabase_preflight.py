import csv
import json
import os
import re
from pathlib import Path

from supabase_client import SupabaseRestClient, load_local_env


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STATUSES = {"published", "published_reviewed"}
REQUIRED_FILES = [
    ROOT / "database/migrations/001_ev_database.sql",
    ROOT / "database/migrations/002_public_canonical_views.sql",
    ROOT / "data/canonical/canonical_models_seed.csv",
    ROOT / "data/canonical/canonical_model_variants_seed.json",
    ROOT / "public/data/public_ev_variants.json",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def extract_enum_values(sql: str, type_name: str) -> set[str]:
    values = set()
    create_match = re.search(rf"create type {type_name} as enum \((.*?)\);", sql, flags=re.S | re.I)
    if create_match:
        values.update(re.findall(r"'([^']+)'", create_match.group(1)))
    values.update(re.findall(rf"alter type {type_name} add value if not exists '([^']+)'", sql, flags=re.I))
    return values


def load_schema_contract() -> tuple[set[str], set[str], str]:
    sql_parts = [path.read_text(encoding="utf-8") for path in sorted((ROOT / "database/migrations").glob("*.sql"))]
    sql = "\n".join(sql_parts)
    return extract_enum_values(sql, "validation_status"), extract_enum_values(sql, "source_type"), sql


def source_rows() -> list[dict]:
    paths = [
        ROOT / "data/canonical/manufacturer_sources_seed.csv",
        ROOT / "data/canonical/manufacturer_sources_mvp_validated.csv",
        ROOT / "data/canonical/manufacturer_sources_validated.csv",
        ROOT / "data/canonical/mvp_extraction_queue.csv",
        ROOT / "data/extraction/rendered_extraction_batch.csv",
    ]
    rows = []
    for path in paths:
        if path.exists():
            rows.extend(read_csv(path))
    return rows


def validation_status_value(value: str | None) -> str:
    return {
        "ready_for_ai_extraction": "queued",
    }.get(value or "", value or "")


def build_report(check_remote: bool = False) -> dict:
    load_local_env()
    validation_statuses, source_types, sql = load_schema_contract()
    variants = json.loads((ROOT / "data/canonical/canonical_model_variants_seed.json").read_text(encoding="utf-8"))
    public_payload = json.loads((ROOT / "public/data/public_ev_variants.json").read_text(encoding="utf-8"))
    public_records = public_payload.get("records", [])
    sources = source_rows()

    missing_files = [str(path.relative_to(ROOT)) for path in REQUIRED_FILES if not path.exists()]
    unknown_variant_statuses = sorted({row.get("validation_status") for row in variants if row.get("validation_status") not in validation_statuses})
    unknown_source_types = sorted({row.get("source_type") for row in sources if row.get("source_type") not in source_types})
    unknown_source_statuses = sorted(
        {
            validation_status_value(row.get("extraction_status") or row.get("preflight_status"))
            for row in sources
            if validation_status_value(row.get("extraction_status") or row.get("preflight_status")) not in validation_statuses
        }
    )
    public_status_errors = sorted({row.get("validation_status") for row in public_records if row.get("validation_status") not in PUBLIC_STATUSES})
    public_missing_source_hash = sum(1 for row in public_records if not row.get("source_hash"))

    report = {
        "files_ready": not missing_files,
        "missing_files": missing_files,
        "env": {
            "SUPABASE_URL": bool(os.environ.get("SUPABASE_URL")),
            "SUPABASE_SERVICE_ROLE_KEY": bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
            "VITE_SUPABASE_URL": bool(os.environ.get("VITE_SUPABASE_URL")),
            "VITE_SUPABASE_ANON_KEY": bool(os.environ.get("VITE_SUPABASE_ANON_KEY")),
        },
        "data": {
            "canonical_variants": len(variants),
            "public_variants": len(public_records),
            "public_missing_source_hash": public_missing_source_hash,
            "public_status_errors": public_status_errors,
        },
        "schema": {
            "has_public_views": "public_ev_variants" in sql and "public_ev_models" in sql,
            "supports_published_reviewed": "published_reviewed" in validation_statuses,
            "unknown_variant_statuses": unknown_variant_statuses,
            "unknown_source_types": unknown_source_types,
            "unknown_source_statuses": unknown_source_statuses,
        },
        "remote": {"checked": False, "public_ev_variants_reachable": None, "error": None},
    }

    if check_remote and report["env"]["SUPABASE_URL"] and report["env"]["SUPABASE_SERVICE_ROLE_KEY"]:
        report["remote"]["checked"] = True
        try:
            client = SupabaseRestClient()
            rows = client.select("public_ev_variants", "brand,model,variant_name,validation_status", {"limit": "1"})
            report["remote"]["public_ev_variants_reachable"] = isinstance(rows, list)
        except Exception as error:
            report["remote"]["public_ev_variants_reachable"] = False
            report["remote"]["error"] = str(error)

    blocking_errors = [
        bool(missing_files),
        bool(unknown_variant_statuses),
        bool(unknown_source_types),
        bool(unknown_source_statuses),
        bool(public_status_errors),
        public_missing_source_hash > 0,
    ]
    report["ready_for_seed"] = not any(blocking_errors) and report["env"]["SUPABASE_URL"] and report["env"]["SUPABASE_SERVICE_ROLE_KEY"]
    return report


def main() -> None:
    report = build_report(check_remote=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
