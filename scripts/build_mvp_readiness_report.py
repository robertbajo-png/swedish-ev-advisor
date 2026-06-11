import json
from datetime import datetime, timezone
from pathlib import Path

from build_mvp_coverage_report import build_report as build_coverage_report
from pipeline_status import build_status
from verify_supabase_public_contract import build_report as build_public_contract_report


ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "data/mvp/mvp_readiness_report.json"
OUT_MD = ROOT / "docs/mvp-readiness-report.md"


def status_label(ok: bool) -> str:
    return "OK" if ok else "BLOCKED"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"records": payload}


def build_advisor_data_report() -> dict:
    payload = read_json(ROOT / "public/data/public_ev_variants.json")
    records = payload.get("records", [])
    public_statuses = {"published", "published_reviewed"}
    errors = []
    for row in records:
        status = row.get("validation_status")
        if status not in public_statuses:
            errors.append(f"non_public_status:{row.get('brand')} {row.get('model')} {row.get('variant_name')}:{status}")
        if not row.get("source_url") or not row.get("source_hash"):
            errors.append(f"missing_source_evidence:{row.get('brand')} {row.get('model')} {row.get('variant_name')}")
    return {"public_rows": len(records), "errors": errors}


def build_validation_report() -> dict:
    canonical = read_json(ROOT / "data/canonical/canonical_model_variants_seed.json").get("records", [])
    exported = read_json(ROOT / "public/data/public_ev_variants.json").get("records", [])
    review = read_json(ROOT / "data/review/variant_review_queue.json").get("records", [])
    public_statuses = {"published", "published_reviewed"}
    errors = []

    for row in canonical:
        status = row.get("validation_status")
        if status not in public_statuses:
            errors.append(f"canonical_non_public_status:{row.get('brand')} {row.get('model')} {row.get('variant_name')}:{status}")
        if not row.get("source_url") or not row.get("source_hash") or not row.get("source_quote"):
            errors.append(f"published_missing_evidence:{row.get('brand')} {row.get('model')} {row.get('variant_name')}")

    review_keys = {
        (
            str(row.get("brand", "")).lower(),
            str(row.get("model", "")).lower(),
            str(row.get("variant_name", "")).lower(),
        )
        for row in review
    }
    for row in exported:
        status = row.get("validation_status")
        key = (
            str(row.get("brand", "")).lower(),
            str(row.get("model", "")).lower(),
            str(row.get("variant_name", "")).lower(),
        )
        if status not in public_statuses:
            errors.append(f"exported_non_public_status:{row.get('brand')} {row.get('model')} {row.get('variant_name')}:{status}")
        if key in review_keys:
            errors.append(f"review_row_exported_publicly:{row.get('brand')} {row.get('model')} {row.get('variant_name')}")

    return {
        "canonical_public_rows": len(canonical),
        "exported_public_rows": len(exported),
        "review_rows": len(review),
        "errors": errors,
    }


def build_report() -> dict:
    pipeline = build_status()
    coverage = build_coverage_report()
    validation = build_validation_report()
    advisor_data = build_advisor_data_report()
    public_contract = build_public_contract_report(check_remote=True)
    images = read_json(ROOT / "data/mvp/public_images_report.json")
    seo = read_json(ROOT / "data/mvp/programmatic_seo_report.json")

    checks = {
        "local_pipeline_ready": bool(pipeline["local_pipeline_ready"]),
        "public_contract_ok": bool(pipeline["public_contract_ok"]),
        "remote_public_contract_ok": bool(public_contract["contract_ok"]),
        "validation_contract_ok": not validation.get("errors"),
        "advisor_data_contract_ok": not advisor_data.get("errors"),
        "all_mvp_models_public": coverage["mvp_models"] == coverage["public_models"] and coverage["mvp_models"] >= 30,
        "strict_images_ok": not images.get("missing_model_image_keys") and not images.get("fallback_image_urls"),
        "supabase_ready_for_seed": bool(pipeline["supabase_preflight_ready_for_seed"]),
    }

    blocking = []
    if not checks["local_pipeline_ready"]:
        blocking.append(pipeline.get("blocker") or "local_pipeline_not_ready")
    if not checks["public_contract_ok"]:
        blocking.append("public_contract_failed")
    if not checks["remote_public_contract_ok"]:
        blocking.append("remote_public_contract_failed")
    if not checks["validation_contract_ok"]:
        blocking.extend(validation.get("errors", []))
    if not checks["advisor_data_contract_ok"]:
        blocking.extend(advisor_data.get("errors", []))
    if not checks["all_mvp_models_public"]:
        blocking.append("mvp_model_coverage_incomplete")
    if not checks["strict_images_ok"]:
        blocking.append("public_image_contract_failed")

    deployment_blocker = pipeline.get("deployment_blocker")
    if deployment_blocker is None and not checks["remote_public_contract_ok"]:
        deployment_blocker = "remote_public_contract_failed"
    if deployment_blocker:
        blocking.append(f"deployment:{deployment_blocker}")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "mvp_models": coverage["mvp_models"],
            "public_models": coverage["public_models"],
            "public_variants": coverage["public_variants"],
            "review_queue_variants": pipeline["review_queue_variants"],
            "local_status": status_label(not [item for item in blocking if not item.startswith("deployment:")]),
            "deployment_status": status_label(not deployment_blocker),
        },
        "checks": checks,
        "blocking_items": blocking,
        "pipeline": {
            "mode": pipeline["mode"],
            "phase_focus": pipeline["phase_focus"],
            "next_action": pipeline["next_action"],
            "deployment_next_action": pipeline["deployment_next_action"],
            "source_health": pipeline["source_health"],
            "seed_plan": pipeline["seed_plan"],
        },
        "coverage": {
            "coverage_by_status": coverage["coverage_by_status"],
            "highest_priority_next": coverage["highest_priority_next"],
        },
        "seo": {
            "expected_routes": seo.get("expected_routes"),
            "vehicle_routes": seo.get("vehicle_routes"),
            "errors": seo.get("errors"),
        },
        "remote_public_contract": public_contract.get("remote", {}),
    }


def write_markdown(report: dict) -> None:
    summary = report["summary"]
    checks = report["checks"]
    pipeline = report["pipeline"]
    blocking_items = report["blocking_items"]
    deployment_ready = report["summary"]["deployment_status"] == "OK"
    recommended_task = (
        "Deploy the latest frontend build, then verify the public URL, sitemap, car detail pages, compare page, and Supabase-backed public data."
        if deployment_ready
        else "Add Supabase credentials to `.env.local`, run the seed dry-run, then verify remote public views."
    )

    lines = [
        "# MVP Readiness Report",
        "",
        "Generated operational snapshot for the portable MVP pipeline.",
        "",
        "## Summary",
        "",
        f"- MVP models: {summary['mvp_models']}",
        f"- Public models: {summary['public_models']}",
        f"- Public variants: {summary['public_variants']}",
        f"- Review queue variants: {summary['review_queue_variants']}",
        f"- Local MVP status: `{summary['local_status']}`",
        f"- Supabase deployment status: `{summary['deployment_status']}`",
        "",
        "## Readiness Checks",
        "",
    ]

    for key, ok in checks.items():
        lines.append(f"- `{key}`: `{status_label(bool(ok))}`")

    lines.extend(["", "## Blocking Items", ""])
    if blocking_items:
        for item in blocking_items:
            lines.append(f"- `{item}`")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Source Health",
            "",
        ]
    )
    for status, count in pipeline["source_health"].items():
        lines.append(f"- `{status}`: {count}")

    lines.extend(
        [
            "",
            "## Next Actions",
            "",
            f"- Local next action: `{pipeline['next_action']}`",
            f"- Deployment next action: `{pipeline['deployment_next_action']}`",
            "",
            "Recommended immediate task: add Supabase credentials to `.env.local`, run the seed dry-run, then verify remote public views.",
        ]
    )
    lines[-1] = f"Recommended immediate task: {recommended_task}"

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = build_report()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
