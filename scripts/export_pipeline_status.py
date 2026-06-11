import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from build_next_extraction_plan import build_plan, summarize
from pipeline_status import build_status
from supabase_client import load_local_env


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "public/data/pipeline_status.json"


def build_public_status() -> dict:
    load_local_env()
    status = build_status()
    plan_summary = summarize(build_plan())
    has_ready_extraction = bool(plan_summary.get("next_ready"))
    automation_blocker = None
    if has_ready_extraction and not os.environ.get("OPENAI_API_KEY"):
        automation_blocker = "missing_openai_api_key"
    elif status.get("blocker"):
        automation_blocker = status.get("blocker")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "local_portable_pipeline",
        "public_variants": status["public_variants"],
        "review_queue_variants": status["review_queue_variants"],
        "mvp_scope_models": status["mvp_scope_models"],
        "source_health": status["source_health"],
        "blocker_queues": status["blocker_queues"],
        "next_ready_model": plan_summary.get("next_ready"),
        "top_blocker": plan_summary.get("top_blocker"),
        "automation_blocker": automation_blocker,
        "public_contract_ok": status["public_contract_ok"],
        "local_pipeline_ready": status["local_pipeline_ready"],
        "supabase_deployment_ready": status["supabase_deployment_ready"],
        "deployment_blocker": status["deployment_blocker"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export public-safe pipeline status for the frontend.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = build_public_status()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "public_variants": payload["public_variants"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
