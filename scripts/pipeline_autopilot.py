import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from shutil import which
from pathlib import Path

from build_next_extraction_plan import build_plan, summarize
from build_source_health_report import build_report as build_source_health_report
from pipeline_status import build_status
from preflight_next_sources import run as run_preflight_next
from refresh_local_pipeline import run as run_refresh
from resolve_blocked_models import build_resolutions, split_queues
from run_next_extraction import run as run_next_extraction
from supabase_client import load_local_env


ROOT = Path(__file__).resolve().parents[1]
AUTOPILOT_LOG = ROOT / "data/mvp/pipeline_autopilot_log.json"


def run_frontend_build(dry_run: bool = False) -> dict:
    if dry_run:
        return {"step": "frontend_build", "status": "dry_run"}
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
    node_path = os.environ.get("NODE")
    if not node_path and bundled.exists():
        node_path = str(bundled)
    if not node_path:
        node_path = which("node") or "node"
    vite_path = ROOT / "node_modules/vite/bin/vite.js"
    result = subprocess.run(
        [node_path, str(vite_path), "build"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return {
        "step": "frontend_build",
        "status": "ok" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def append_log(report: dict) -> None:
    AUTOPILOT_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(AUTOPILOT_LOG.read_text(encoding="utf-8")) if AUTOPILOT_LOG.exists() else []
    existing.append(report)
    AUTOPILOT_LOG.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def action(step: str, status: str, **kwargs) -> dict:
    return {"step": step, "status": status, **kwargs}


def run(max_cycles: int = 2, preflight_limit: int = 3, extraction_limit: int = 1, dry_run: bool = False, build: bool = True) -> dict:
    load_local_env()
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "max_cycles": max_cycles,
        "actions": [],
    }

    refresh = run_refresh(dry_run=dry_run)
    report["actions"].append(action("refresh_local_pipeline", "ok" if refresh.get("ok") else "failed", result=refresh))
    if not refresh.get("ok"):
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        report["ok"] = False
        append_log(report)
        return report

    for cycle in range(1, max_cycles + 1):
        plan = build_plan()
        summary = summarize(plan)
        report["actions"].append(action("plan", "ok", cycle=cycle, summary=summary))

        ready_count = summary["by_status"].get("ready_for_ai_extraction", 0)
        preflight_count = summary["by_status"].get("needs_preflight", 0)

        if ready_count and os.environ.get("OPENAI_API_KEY"):
            extraction = run_next_extraction(limit=extraction_limit, dry_run=dry_run)
            report["actions"].append(action("extract_next", "ok" if not extraction.get("errors") else "needs_attention", cycle=cycle, result=extraction))
            continue

        if ready_count and not os.environ.get("OPENAI_API_KEY"):
            report["actions"].append(
                action(
                    "extract_next",
                    "blocked_missing_openai_key",
                    cycle=cycle,
                    ready_models=[f"{row['brand']} {row['model']}" for row in plan if row["extraction_status"] == "ready_for_ai_extraction"][:extraction_limit],
                )
            )

        if preflight_count:
            preflight = run_preflight_next(limit=preflight_limit, dry_run=dry_run)
            report["actions"].append(action("preflight_next", "ok", cycle=cycle, result=preflight))
            if not dry_run:
                continue

        if not ready_count and not preflight_count:
            report["actions"].append(action("pipeline_queue", "no_ready_or_preflight_work", cycle=cycle))
            break

    source_health = build_source_health_report()
    blocker_resolutions = build_resolutions()
    blocker_queues = split_queues(blocker_resolutions)
    status = build_status()
    report["actions"].append(action("source_health", "ok", counts=source_health["counts"]))
    report["actions"].append(action("resolve_blockers", "ok", queues={key: len(value) for key, value in sorted(blocker_queues.items())}))
    report["actions"].append(action("pipeline_status", "ok", result=status))

    if build:
        build_result = run_frontend_build(dry_run=dry_run)
        report["actions"].append(build_result)
        if build_result["status"] == "failed":
            report["completed_at"] = datetime.now(timezone.utc).isoformat()
            report["ok"] = False
            append_log(report)
            return report

    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["ok"] = True
    append_log(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the portable EV data pipeline autopilot.")
    parser.add_argument("--max-cycles", type=int, default=2)
    parser.add_argument("--preflight-limit", type=int, default=3)
    parser.add_argument("--extraction-limit", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                max_cycles=args.max_cycles,
                preflight_limit=args.preflight_limit,
                extraction_limit=args.extraction_limit,
                dry_run=args.dry_run,
                build=not args.no_build,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
