import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from apply_expansion_sources import merge_sources, read_csv, write_csv
from build_expansion_scope import build_expansion_scope, read_csv as read_scope_csv, read_json
from discover_free_web_sources import discover, url_score
from extract_manufacturer_specs import safe_extract, write_outputs
from source_policy import source_is_publishable, source_priority
from supabase_client import load_local_env


ROOT = Path(__file__).resolve().parents[1]
EXPANSION_DIR = ROOT / "data/expansion"
STATE_PATH = EXPANSION_DIR / "expansion_wave_state.json"


def run_script(script: str, *args: str) -> dict:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT, text=True, capture_output=True)
    return {
        "script": script,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def node_executable() -> str:
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
    return os.environ.get("NODE") or (str(bundled) if bundled.exists() else "node")


def render_missing_sources(batch: list[dict], discovered: list[dict], timeout: int) -> tuple[list[dict], list[dict]]:
    selected = best_sources_by_model(discovered)
    queue = []
    priority = 1
    for scope_row in batch:
        key = model_key(scope_row)
        if key in selected:
            continue
        candidates = [
            row for row in discovered
            if model_key(row) == key
            and row.get("source_authority", "manufacturer") in {"manufacturer", "importer"}
            and row.get("url")
            and url_score(row["url"], row["model"]) > 0
            and "ev_advisor_discovery_query=" not in row["url"]
            and "sitemap" not in row["url"].lower()
        ]
        if not candidates:
            continue
        candidate = candidates[0]
        queue.append({
            "rank": scope_row["market_rank"], "mvp_scope": scope_row["wave"], "brand": scope_row["brand"],
            "model": scope_row["model"], "registrations_ytd": scope_row["registrations_ytd"],
            "source_url": candidate["url"], "source_validation": candidate.get("source_validation", ""),
            "render_reason": "free_web_http_blocked_or_dynamic", "target_strategy": "browser_rendered_fetch",
            "queue_status": "queued", "priority": priority,
            "notes": "Rendered exact official model page; still requires extraction and hard validation.",
        })
        priority += 1
    if not queue:
        return [], []

    queue_path = EXPANSION_DIR / "browser_render_queue.csv"
    rendered_csv = EXPANSION_DIR / "browser_rendered_sources.csv"
    rendered_json = EXPANSION_DIR / "browser_rendered_sources.json"
    rendered_batch_csv = EXPANSION_DIR / "rendered_extraction_batch.csv"
    rendered_batch_json = EXPANSION_DIR / "rendered_extraction_batch.json"
    write_csv(queue_path, queue)
    render = subprocess.run(
        [node_executable(), str(ROOT / "scripts/fetch_browser_rendered_sources.mjs"), "--queue", str(queue_path),
         "--csv-out", str(rendered_csv), "--json-out", str(rendered_json), "--timeout-ms", str(max(15000, timeout * 1000))],
        cwd=ROOT, text=True, capture_output=True,
    )
    actions = [{"script": "fetch_browser_rendered_sources.mjs", "ok": render.returncode == 0, "returncode": render.returncode, "stdout": render.stdout.strip(), "stderr": render.stderr.strip()}]
    if render.returncode != 0:
        return [], actions
    build = run_script(
        "build_rendered_extraction_batch.py", "--source-file", str(rendered_csv), "--csv-out", str(rendered_batch_csv),
        "--json-out", str(rendered_batch_json),
    )
    actions.append(build)
    batch_keys = {model_key(row) for row in batch}
    rendered_rows = []
    if build["ok"]:
        for row in read_csv(rendered_batch_csv):
            if model_key(row) not in batch_keys:
                continue
            rendered_rows.append({
                **row,
                "source_authority": "manufacturer",
                "source_name": row.get("brand"),
                "authorization_evidence_url": "",
                "http_status": "200",
                "extraction_status": "queued",
            })
    return rendered_rows, actions


def model_key(row: dict) -> str:
    return f"{row.get('brand')}|{row.get('model')}"


def load_rules() -> dict:
    return json.loads((ROOT / "data/canonical/brand_source_resolver_rules.json").read_text(encoding="utf-8"))


def load_dealers() -> list[dict]:
    return json.loads((ROOT / "data/canonical/authorized_dealers.json").read_text(encoding="utf-8")).get("dealers", [])


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"completed_models": [], "attempts": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def published_expansion_models() -> set[str]:
    path = ROOT / "data/canonical/canonical_model_variants_seed.json"
    if not path.exists():
        return set()
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {
        model_key(row) for row in rows
        if row.get("validation_status") in {"published", "published_reviewed"}
    }


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_scope_in_memory(start_rank: int, end_rank: int) -> tuple[list[dict], list[dict]]:
    return build_expansion_scope(
        read_scope_csv(ROOT / "data/mobility-sweden/processed/market_models.csv"),
        read_scope_csv(ROOT / "data/canonical/canonical_models_seed.csv"),
        read_scope_csv(ROOT / "data/canonical/model_aliases_seed.csv"),
        read_json(ROOT / "data/canonical/canonical_model_variants_seed.json"),
        start_rank,
        end_rank,
    )


def best_sources_by_model(rows: list[dict]) -> dict[str, dict]:
    selected: dict[str, dict] = {}
    for row in rows:
        if not source_is_publishable(row):
            continue
        key = model_key(row)
        if key not in selected or source_priority(row) < source_priority(selected[key]):
            selected[key] = row
    return selected


def batched(rows: list[dict], size: int):
    for index in range(0, len(rows), size):
        yield rows[index:index + size]


def postprocess(sync_supabase: bool, build_frontend: bool) -> list[dict]:
    actions = []
    for script, args in (
        ("validate_extracted_variants.py", ()),
        ("export_public_ev_data.py", ()),
        ("seed_local_sqlite.py", ("--reset",)),
        ("export_public_from_sqlite.py", ()),
        ("generate_sitemap.py", ()),
    ):
        result = run_script(script, *args)
        actions.append(result)
        if not result["ok"]:
            return actions
    if sync_supabase:
        seed_result = run_script("seed_supabase.py")
        actions.append(seed_result)
        if seed_result["ok"]:
            actions.append(run_script("verify_supabase_public_contract.py"))
    if build_frontend:
        node = os.environ.get("NODE") or str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
        vite = ROOT / "node_modules/vite/bin/vite.js"
        result = subprocess.run([node, str(vite), "build"], cwd=ROOT, text=True, capture_output=True)
        actions.append({"script": "vite build", "ok": result.returncode == 0, "returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()})
    return actions


def run(
    start_rank: int = 31,
    end_rank: int = 60,
    batch_size: int = 5,
    max_batches: int | None = None,
    timeout: int = 15,
    dry_run: bool = False,
    sync_supabase: bool = True,
    build_frontend: bool = True,
    browser_render: bool = True,
) -> dict:
    load_local_env()
    scope, quarantine = build_scope_in_memory(start_rank, end_rank)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "start_rank": start_rank,
        "end_rank": end_rank,
        "batch_size": batch_size,
        "scope_models": len(scope),
        "quarantined_models": len(quarantine),
        "dry_run": dry_run,
        "batches": [],
        "postprocess": [],
    }
    if dry_run:
        report["planned_models"] = [model_key(row) for row in scope]
        report["supabase_sync_planned"] = sync_supabase
        report["ok"] = True
        return report

    EXPANSION_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(EXPANSION_DIR / "expansion_scope.csv", scope)
    write_csv(EXPANSION_DIR / "mapping_quarantine.csv", quarantine)
    (EXPANSION_DIR / "expansion_scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (EXPANSION_DIR / "mapping_quarantine.json").write_text(json.dumps(quarantine, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state = load_state()
    completed = set(state.get("completed_models", [])) & published_expansion_models()
    pending = [row for row in scope if model_key(row) not in completed]
    existing_sources = read_csv(ROOT / "data/canonical/manufacturer_sources_seed.csv") + read_csv(ROOT / "data/canonical/manufacturer_sources_validated.csv")
    expansion_sources = read_csv(EXPANSION_DIR / "expansion_sources.csv")
    rules = load_rules()
    dealers = load_dealers()

    for batch_index, batch in enumerate(batched(pending, batch_size), start=1):
        if max_batches is not None and batch_index > max_batches:
            break
        discovered = discover(batch, rules, existing_sources + expansion_sources, dealers, timeout=timeout)
        render_actions = []
        if browser_render:
            rendered, render_actions = render_missing_sources(batch, discovered, timeout)
            discovered.extend(rendered)
        expansion_sources = merge_sources(expansion_sources, discovered)
        write_csv(EXPANSION_DIR / "expansion_sources.csv", expansion_sources)
        selected = best_sources_by_model(discovered)
        batch_report = {"batch": batch_index, "models": [model_key(row) for row in batch], "sources": len(discovered), "drafts": 0, "errors": [], "render_actions": render_actions}
        drafts = []
        for row in batch:
            key = model_key(row)
            source = selected.get(key)
            if not source:
                batch_report["errors"].append({"model": key, "error": "no_publishable_free_web_source"})
                continue
            try:
                extracted = safe_extract(source)
                if not extracted:
                    raise RuntimeError("source_produced_no_variants")
                drafts.extend(extracted)
                completed.add(key)
            except Exception as error:
                batch_report["errors"].append({"model": key, "url": source.get("url"), "error": str(error)})
        if drafts:
            write_outputs(drafts, append=True)
        batch_report["drafts"] = len(drafts)
        report["batches"].append(batch_report)
        state.setdefault("attempts", []).append({**batch_report, "at": datetime.now(timezone.utc).isoformat()})
        state["completed_models"] = sorted(completed)
        save_state(state)

    apply_result = run_script("apply_expansion_sources.py")
    report["postprocess"].append(apply_result)
    if apply_result["ok"]:
        has_supabase = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
        report["postprocess"].extend(postprocess(sync_supabase and has_supabase, build_frontend))
        report["supabase_sync"] = "completed" if sync_supabase and has_supabase else "skipped_missing_credentials_or_disabled"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["ok"] = all(action.get("ok", True) for action in report["postprocess"])
    (EXPANSION_DIR / "expansion_run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the free-web expansion wave in restartable batches.")
    parser.add_argument("--start-rank", type=int, default=31)
    parser.add_argument("--end-rank", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-supabase", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--no-browser-render", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(
        start_rank=args.start_rank,
        end_rank=args.end_rank,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        timeout=args.timeout,
        dry_run=args.dry_run,
        sync_supabase=not args.no_supabase,
        build_frontend=not args.no_build,
        browser_render=not args.no_browser_render,
    ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
