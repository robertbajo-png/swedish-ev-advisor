import argparse
import asyncio
import csv
import hashlib
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = ROOT / "data/mvp/browser_render_queue.csv"
DEFAULT_CSV_OUT = ROOT / "data/extraction/browser_rendered_sources.csv"
DEFAULT_JSON_OUT = ROOT / "data/extraction/browser_rendered_sources.json"
MIN_TEXT_LENGTH = 500


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "mvp_scope",
        "brand",
        "model",
        "registrations_ytd",
        "source_url",
        "final_url",
        "source_domain",
        "render_status",
        "render_error",
        "source_hash",
        "source_text_length",
        "source_text_preview",
        "fetched_at",
        "extraction_status",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def domain_from_url(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def playwright_available():
    return importlib.util.find_spec("playwright") is not None


async def fetch_rendered_source(url, timeout_ms=30000):
    from playwright.async_api import async_playwright

    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 SwedishEVAdvisor/0.1",
            locale="sv-SE",
        )
        await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        text = clean_text(await page.locator("body").inner_text(timeout=timeout_ms))
        final_url = page.url
        await browser.close()
        return final_url, text


def blocked_row(row, status, error):
    return {
        "rank": row.get("rank", ""),
        "mvp_scope": row.get("mvp_scope", ""),
        "brand": row.get("brand", ""),
        "model": row.get("model", ""),
        "registrations_ytd": row.get("registrations_ytd", ""),
        "source_url": row.get("source_url", ""),
        "final_url": "",
        "source_domain": domain_from_url(row.get("source_url", "")),
        "render_status": status,
        "render_error": error,
        "source_hash": "",
        "source_text_length": 0,
        "source_text_preview": "",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "extraction_status": "blocked",
        "notes": "No public data is populated from this row until rendered official source text is captured and validated.",
    }


async def render_row(row, timeout_ms):
    try:
        final_url, text = await fetch_rendered_source(row["source_url"], timeout_ms=timeout_ms)
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        text_length = len(text)
        status = "rendered_source_ready" if text_length >= MIN_TEXT_LENGTH else "rendered_text_too_short"
        return {
            "rank": row.get("rank", ""),
            "mvp_scope": row.get("mvp_scope", ""),
            "brand": row.get("brand", ""),
            "model": row.get("model", ""),
            "registrations_ytd": row.get("registrations_ytd", ""),
            "source_url": row.get("source_url", ""),
            "final_url": final_url,
            "source_domain": domain_from_url(final_url or row.get("source_url", "")),
            "render_status": status,
            "render_error": "" if status == "rendered_source_ready" else "source_text_too_short",
            "source_hash": source_hash if status == "rendered_source_ready" else "",
            "source_text_length": text_length,
            "source_text_preview": text[:500],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "extraction_status": "queued" if status == "rendered_source_ready" else "blocked",
            "notes": "Rendered official source text captured for AI extraction staging.",
        }
    except Exception as error:
        return blocked_row(row, "render_failed", str(error))


async def build_rendered_sources(rows, limit=None, timeout_ms=30000, force_unavailable=False):
    queued = [row for row in rows if row.get("queue_status") == "queued"]
    queued.sort(key=lambda row: int(row.get("priority") or row.get("rank") or 999))
    if limit is not None:
        queued = queued[:limit]

    if force_unavailable or not playwright_available():
        return [
            blocked_row(
                row,
                "blocked_missing_playwright",
                "Playwright is not installed in this workspace; install/enable a browser runtime before rendering.",
            )
            for row in queued
        ]

    return [await render_row(row, timeout_ms) for row in queued]


def main():
    parser = argparse.ArgumentParser(description="Fetch official manufacturer pages that require browser rendering.")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--csv-out", default=str(DEFAULT_CSV_OUT))
    parser.add_argument("--json-out", default=str(DEFAULT_JSON_OUT))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args()

    rows = read_csv(Path(args.queue))
    rendered = asyncio.run(build_rendered_sources(rows, limit=args.limit, timeout_ms=args.timeout_ms))
    write_csv(Path(args.csv_out), rendered)
    write_json(Path(args.json_out), rendered)

    ready = sum(1 for row in rendered if row["render_status"] == "rendered_source_ready")
    print(f"Browser-render rows processed: {len(rendered)}")
    print(f"Rendered sources ready: {ready}")
    if ready == 0:
        print("No rendered source text was captured. This is expected if Playwright/browser runtime is unavailable.")


if __name__ == "__main__":
    main()
