import csv
import json
from pathlib import Path

from seed_supabase import build_seed_plan
from supabase_preflight import build_report as build_supabase_preflight_report
from verify_supabase_public_contract import build_report as build_public_contract_report
from build_source_health_report import build_report as build_source_health_report
from resolve_blocked_models import build_resolutions, split_queues


ROOT = Path(__file__).resolve().parents[1]


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


def count_by(rows: list[dict], field: str) -> dict:
    counts = {}
    for row in rows:
        value = row.get(field) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def first_blocker(preflight: dict, public_contract: dict, *, require_supabase_env: bool = False) -> str | None:
    if not preflight["files_ready"]:
        return "missing_required_pipeline_files"
    if preflight["schema"]["unknown_variant_statuses"]:
        return "unknown_variant_statuses_in_seed_data"
    if preflight["schema"]["unknown_source_types"]:
        return "unknown_source_types_in_source_data"
    if preflight["schema"]["unknown_source_statuses"]:
        return "unknown_source_statuses_in_source_data"
    if preflight["data"]["public_status_errors"]:
        return "public_export_contains_non_public_status"
    if preflight["data"]["public_missing_source_hash"]:
        return "public_export_missing_source_hash"
    if not public_contract["contract_ok"]:
        return "local_public_contract_failed"
    if require_supabase_env and (not preflight["env"]["SUPABASE_URL"] or not preflight["env"]["SUPABASE_SERVICE_ROLE_KEY"]):
        return "supabase_service_env_missing"
    return None


def next_action(blocker: str | None) -> str:
    return {
        None: "run_supabase_seed_then_verify_public_views",
        "missing_required_pipeline_files": "regenerate_missing_pipeline_outputs",
        "unknown_variant_statuses_in_seed_data": "align_variant_statuses_with_database_enum",
        "unknown_source_types_in_source_data": "align_source_types_with_database_enum",
        "unknown_source_statuses_in_source_data": "map_source_statuses_to_validation_status_enum",
        "public_export_contains_non_public_status": "rerun_validation_and_public_export",
        "public_export_missing_source_hash": "quarantine_source_less_public_records",
        "local_public_contract_failed": "fix_public_export_before_remote_seed",
        "supabase_service_env_missing": "add_supabase_url_and_service_role_key_to_env_local",
    }[blocker]


def build_status() -> dict:
    mvp_scope = read_csv(ROOT / "data/mvp/mvp_model_scope.csv")
    remaining = read_csv(ROOT / "data/mvp/mvp_remaining_work.csv")
    review_queue = read_json(ROOT / "data/review/variant_review_queue.json")
    public_records = read_json(ROOT / "public/data/public_ev_variants.json")
    preflight = build_supabase_preflight_report(check_remote=False)
    public_contract = build_public_contract_report(check_remote=False)
    source_health = build_source_health_report()
    blocker_queues = split_queues(build_resolutions())
    local_blocker = first_blocker(preflight, public_contract)
    deployment_blocker = first_blocker(preflight, public_contract, require_supabase_env=True)

    return {
        "phase_focus": "Phase 9 operations/readiness with portable local MVP data",
        "mode": "local_portable_pipeline",
        "mvp_scope_models": len(mvp_scope),
        "mvp_remaining_by_strategy": count_by(remaining, "next_strategy"),
        "review_queue_variants": len(review_queue),
        "public_variants": len(public_records),
        "source_health": source_health["counts"],
        "blocker_queues": {key: len(value) for key, value in sorted(blocker_queues.items())},
        "seed_plan": build_seed_plan(),
        "local_pipeline_ready": local_blocker is None,
        "supabase_preflight_ready_for_seed": preflight["ready_for_seed"],
        "supabase_deployment_ready": deployment_blocker is None,
        "public_contract_ok": public_contract["contract_ok"],
        "blocker": local_blocker,
        "deployment_blocker": deployment_blocker,
        "next_action": next_action(local_blocker),
        "deployment_next_action": next_action(deployment_blocker),
    }


def main() -> None:
    print(json.dumps(build_status(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
