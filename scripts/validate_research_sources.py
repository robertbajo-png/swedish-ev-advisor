import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SOURCE_PRIORITY = {
    "manufacturer_price_list": 1,
    "manufacturer_specs_page": 2,
    "manufacturer_model_page": 3,
    "manufacturer_configurator": 4,
}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def rank_value(value: str) -> int:
    match = re.match(r"(\d+)", str(value))
    return int(match.group(1)) if match else 999


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
    return brand, canonical_model_alias(brand, row.get("model"))


def mvp_scope_keys(scope_path: Path) -> set[tuple[str, str]]:
    if not scope_path.exists():
        return set()
    return {model_key(row) for row in read_csv(scope_path)}


def clean_host(value: str) -> str:
    return value.lower().replace("www.", "").strip("/")


def official_domain_matches(url: str, source_domain: str) -> bool:
    url_host = clean_host(urlparse(url).netloc)
    expected = clean_host(source_domain)
    return url_host == expected or url_host.endswith(f".{expected}")


def check_url(url: str, timeout: int) -> tuple[int | None, str, str, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "swedish-ev-advisor/0.1 (+https://swedish-ev-advisor.se)",
            "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.6",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            return (
                response.status,
                response.geturl(),
                hashlib.sha256(body).hexdigest(),
                response.headers.get("content-type", ""),
                datetime.now(timezone.utc).isoformat(),
            )
    except HTTPError as error:
        return error.code, "", "", "", ""
    except (TimeoutError, URLError):
        return None, "", "", "", ""


def validate_candidate(row: dict, timeout: int = 12) -> dict:
    status, final_url, content_hash, content_type, fetched_at = check_url(row["url"], timeout)
    official_domain = official_domain_matches(row["url"], row["source_domain"]) and (
        not final_url or official_domain_matches(final_url, row["source_domain"])
    )
    reachable = bool(status and 200 <= status < 400)
    source_validation = (
        "reachable_official_model_source"
        if reachable and official_domain
        else "reachable_unapproved_domain"
        if reachable
        else "unreachable_or_redirect_problem"
        if status
        else "needs_discovery"
    )
    return {
        **row,
        "official_domain_match": str(official_domain),
        "http_status": "" if status is None else status,
        "final_url": final_url,
        "content_hash": content_hash,
        "content_type": content_type,
        "fetched_at": fetched_at,
        "source_validation": source_validation,
        "extraction_status": "queued" if source_validation == "reachable_official_model_source" else "blocked",
    }


def build_extraction_queue(validated_rows: list[dict], scope_keys: set[tuple[str, str]] | None = None) -> list[dict]:
    reachable = [
        row for row in validated_rows
        if row["source_validation"] == "reachable_official_model_source"
        and (not scope_keys or model_key(row) in scope_keys)
    ]
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in reachable:
        grouped.setdefault((row["brand"], row["model"]), []).append(row)

    queue = []
    for (brand, model), rows in grouped.items():
        best = sorted(
            rows,
            key=lambda row: (
                rank_value(row["research_rank"]),
                SOURCE_PRIORITY.get(row["source_type"], 99),
                0 if row["research_confidence"].lower() == "high" else 1,
            ),
        )[0]
        queue.append(
            {
                "brand": brand,
                "model": model,
                "source_type": best["source_type"],
                "url": best["url"],
                "source_domain": best["source_domain"],
                "research_rank": best["research_rank"],
                "research_confidence": best["research_confidence"],
                "http_status": best["http_status"],
                "final_url": best["final_url"],
                "content_hash": best["content_hash"],
                "content_type": best["content_type"],
                "fetched_at": best["fetched_at"],
                "source_validation": best["source_validation"],
                "extraction_status": "queued",
                "queue_reason": "best_reachable_official_source_for_model",
            }
        )

    queue.sort(key=lambda row: (rank_value(row["research_rank"]), row["brand"], row["model"]))
    return queue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path, default=Path("data/canonical/manufacturer_sources_research_candidates.csv"))
    parser.add_argument("--scope", type=Path, default=Path("data/mvp/mvp_model_scope.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/canonical"))
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    rows = read_csv(args.source_file)
    rows.sort(key=lambda row: (rank_value(row["research_rank"]), SOURCE_PRIORITY.get(row["source_type"], 99)))
    if args.limit:
        rows = rows[: args.limit]

    validated = [validate_candidate(row, args.timeout) for row in rows]
    queue = build_extraction_queue(validated, mvp_scope_keys(args.scope))
    write_csv(args.out_dir / "manufacturer_sources_mvp_validated.csv", validated)
    write_csv(args.out_dir / "mvp_extraction_queue.csv", queue)
    (args.out_dir / "manufacturer_sources_mvp_validated.json").write_text(
        json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out_dir / "mvp_extraction_queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Validated research candidates: {len(validated)}")
    print(f"Reachable official candidates: {sum(1 for row in validated if row['source_validation'] == 'reachable_official_model_source')}")
    print(f"MVP extraction queue models: {len(queue)}")


if __name__ == "__main__":
    main()
