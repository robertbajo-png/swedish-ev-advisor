import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


PIPELINE_STEPS = [
    ("apply_official_variant_overrides.py", "apply source-backed official variant corrections"),
    ("validate_extracted_variants.py", "validate drafts and canonical public variants"),
    ("export_public_ev_data.py", "export canonical JSON fallback"),
    ("seed_local_sqlite.py", "seed local SQLite database"),
    ("export_public_from_sqlite.py", "export public JSON from SQLite public view"),
    ("export_pipeline_status.py", "export public-safe pipeline status"),
    ("generate_sitemap.py", "generate sitemap and robots"),
]


def run_script(script: str, dry_run: bool = False) -> dict:
    if dry_run:
        return {"script": script, "status": "dry_run"}
    args = [sys.executable, str(ROOT / "scripts" / script)]
    if script == "seed_local_sqlite.py":
        args.append("--reset")
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return {
        "script": script,
        "status": "ok" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def run(dry_run: bool = False, include_prerender: bool = False) -> dict:
    steps = list(PIPELINE_STEPS)
    if include_prerender:
        steps.append(("prerender_static_routes.py", "prerender static SEO routes after frontend build"))

    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "steps": [],
    }
    for script, description in steps:
        result = run_script(script, dry_run=dry_run)
        result["description"] = description
        report["steps"].append(result)
        if result["status"] == "failed":
            report["completed_at"] = datetime.now(timezone.utc).isoformat()
            report["ok"] = False
            return report
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["ok"] = True
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the portable local EV data pipeline.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-prerender", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(dry_run=args.dry_run, include_prerender=args.include_prerender), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
