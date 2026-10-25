"""News-to-car integration: recheck approved official URLs without writing car facts."""
import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from news_engine import ROOT, record_run
from news_http import Collector
from news_store import NewsStore, now_iso


def source_rows(store):
    if store.backend == "supabase":
        rows = store.client.select("manufacturer_sources")
        models = {r["id"]: r for r in store.client.select("canonical_models")}
        return [{**r, "brand": models.get(r.get("canonical_model_id"), {}).get("brand"),
                 "model": models.get(r.get("canonical_model_id"), {}).get("model")} for r in rows]
    path = ROOT / "data/canonical/manufacturer_sources_seed.csv"
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def batch_rows(rows):
    if (not isinstance(rows, list) or any(not isinstance(row, dict)
            or any(not isinstance(row.get(key), str) or not row[key] for key in ('news_request_id', 'url'))
            for row in rows)):
        raise ValueError('invalid_news_verification_batch')
    return rows


def write_batch(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run(store, limit=3, collector=None):
    collector = collector or Collector()
    out = ROOT / "data/news/official_verification_batch.json"
    previous = batch_rows(json.loads(out.read_text(encoding='utf-8'))) if out.exists() else []
    requests = [r for r in store.rows("news_verification_requests") if r["status"] == "pending"][:limit]
    sources = source_rows(store)
    report = []
    for request in requests:
        p = request["payload"]
        matches = [s for s in sources if s.get("brand") == p["brand"] and s.get("model") == p["model"]
                   and s.get("source_authority", "manufacturer") in {"manufacturer", "importer"}
                   and s.get("source_validation") in {"reachable_official_model_source", "reachable_approved_source"}]
        diagnostics = []
        batch = []
        for source in matches[:2]:
            try:
                url = source["url"]
                website = "https://" + urlsplit(url).netloc
                _, _, content, final = collector.fetch(url, {"website": website}, editorial=True)
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                diagnostics.append({"url": url, "status": "checked", "content_hash": content_hash,
                                    "changed": content_hash != source.get("content_hash")})
                batch.append({"brand": p["brand"], "model": p["model"], "url": final,
                              "source_type": source.get("source_type"), "source_domain": urlsplit(url).hostname,
                              "content_hash": content_hash, "source_validation": source["source_validation"],
                              "source_authority": source.get("source_authority", "manufacturer"),
                              "news_request_id": request["id"], "extraction_status": "needs_preflight"})
            except Exception as exc:
                diagnostics.append({"url": source["url"], "status": "failed", "reason": type(exc).__name__ + ":" + str(exc)[:180]})
        status = "exported" if any(d["status"] == "checked" for d in diagnostics) else "failed"
        store.put("news_verification_requests", {**request, "status": status,
                  "payload": {**p, "checked_at": now_iso(), "diagnostics": diagnostics, 'source_batch': batch,
                              "result": "reextract_official_source" if status == "exported" else "official_source_unavailable"}})
        report.append({"id": request["id"], "status": status, "diagnostics": diagnostics})
    # The local projection is disposable; source handoffs survive in the private store.
    queued = {(row['news_request_id'], row['url']): row for row in previous}
    for request in store.rows('news_verification_requests'):
        if request['status'] == 'exported':
            for row in batch_rows(request['payload'].get('source_batch', [])):
                queued[(row['news_request_id'], row['url'])] = row
    try:
        write_batch(out, list(queued.values()))
    except OSError as exc:
        record_run(store, 'vehicle_source_verification', {'requests': report, 'handoff_status': 'failed',
                   'reason': type(exc).__name__ + ':' + str(exc)[:180]})
        raise
    record_run(store, "vehicle_source_verification", {"requests": report, 'queued_sources': len(queued)})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["sqlite", "supabase"], default="sqlite")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    store = NewsStore(backend=args.backend)
    try:
        print(json.dumps(run(store, max(0, min(args.limit, 10))), ensure_ascii=False, indent=2))
    finally:
        store.close()
