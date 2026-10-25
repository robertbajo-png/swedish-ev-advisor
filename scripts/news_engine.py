"""Automated news CLI: collection -> grounded editorial -> quality gates -> publication."""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from generate_sitemap import public_variant_slug
from news_editorial import (
    ai_json, audit_article, event_key, extract_facts, generate_article, normalize,
    relevance_score, validate_article, validate_fact_extraction, obj, STRING, BOOL,
    market_qualified_facts,
    repair_article, repair_source_wording,
    source_overlaps, article_preflight, EDITORIAL_RECIPE,
    partition_fact_extraction,
    source_qualifier_facts,
    build_fact_plan, blocks,
)
from news_http import Collector, PageText, canonical_url, iso_date, parse_feed, require_recent_publication
from news_store import NewsStore, now_iso, stable_id, artifact_hash, EDITORIAL_POLICY
from news_pressrooms import discover as discover_pressroom, document as press_document
from news_ai import NewsAi, NewsBudgetBlocked
from news_fact_brief import neutral_facts, source_technical_facts
from news_notice_pipeline import notice_sources, stage_notices
from supabase_client import load_local_env

ROOT = Path(__file__).resolve().parents[1]


def registry(path=None):
    sources = json.loads(Path(path or ROOT / "data/news/sources.json").read_text(encoding="utf-8"))
    profile = os.environ.get('NEWS_SOURCE_PROFILE', 'all')
    if profile not in ('all','official'):
        raise ValueError('unknown_news_source_profile')
    if profile == 'official':
        return [{**s, 'enabled': s['kind'] == 'primary' and s.get('collection_method') == 'pressroom_index'} for s in sources]
    return sources


def record_run(store, kind, report):
    store.put("news_ingestion_runs", {"id": stable_id(kind + now_iso()), "payload": {"kind": kind, "at": now_iso(), **report}})


def classify_metadata(title, summary):
    text = title + " " + summary
    brands = [brand for brand in ("Tesla", "Volvo", "Polestar", "Volkswagen", "BMW", "Audi", "Kia", "Hyundai", "BYD", "XPeng", "Nio", "Zeekr", "MG", "Renault", "Peugeot", "Toyota", "Lexus", "Nissan", "Ford", "Mercedes", "Skoda", "Porsche", "Mini", "Subaru", "Opel")
              if re.search(r"\b" + re.escape(brand) + r"\b", text, flags=re.I)]
    markets = [name for name, pattern in (("Sweden", r"\b(sweden|swedish|sverige)\b"), ("Europe", r"\b(europe|european|eu|germany|german|france|united kingdom|norway|denmark|finland)\b"), ("China", r"\b(china|chinese)\b"), ("US", r"\b(us|usa|american)\b")) if re.search(pattern, text, flags=re.I)]
    technology = [name for name, pattern in (("battery", r"batter|solid.state|lithium"), ("charging", r"charg|800.volt|800v"), ("efficiency", r"range|efficien|winter.test")) if re.search(pattern, text, flags=re.I)]
    priority = 4 * ("Sweden" in markets) + 2 * ("Europe" in markets) + len(technology)
    return {"brands": brands, "markets": markets, "technology": technology, "discovery_priority": priority}


def models_for_news(store):
    if store.backend == "supabase":
        models = store.client.select("public_ev_models")
        variants = store.client.select("public_ev_variants")
    else:
        models = json.loads((ROOT / "data/canonical/canonical_models_seed.json").read_text(encoding="utf-8"))
        variants = json.loads((ROOT / "public/data/public_ev_variants.json").read_text(encoding="utf-8"))["records"]
    valid = {(r["brand"], r["model"]) for r in variants}
    result = {}
    for model in models:
        if (model["brand"], model["model"]) not in valid:
            continue
        variant = next(v for v in variants if (v["brand"], v["model"]) == (model["brand"], model["model"]))
        key = model["brand"] + "|" + model["model"]
        result[key] = {"key": key, "brand": model["brand"], "model": model["model"],
                       "canonical_model_id": model.get("id"), "car_slug": public_variant_slug(variant)}
    return result


def collect(store, sources, collector=None, max_items=20, force=False):
    collector = collector or Collector()
    report = {"sources": [], "new_items": 0}
    known = {r["url"]: r for r in store.rows("news_items")}
    for config in sources:
        existing = store.get("news_sources", config["id"])
        source = {**(existing or {}).get("payload", {}), **config}
        store.put("news_sources", {"id": config["id"], "payload": source})
        if not source.get("enabled", source.get("priority", False)):
            continue
        previous = iso_date(source.get("checked_at"))
        if not force and previous and (datetime.now(timezone.utc) - datetime.fromisoformat(previous)).total_seconds() < source.get("poll_hours", 4) * 3600:
            continue
        entry = {"source_id": source["id"], "feed": None, "status": "no_verified_feed", "errors": []}
        pressroom = source.get('collection_method') == 'pressroom_index'
        for feed in source.get("indexes", []) if pressroom else source.get("feeds", []):
            try:
                conditional = {}
                if source.get("verified_feed") == feed:
                    if source.get("etag"):
                        conditional["If-None-Match"] = source["etag"]
                    if source.get("last_modified"):
                        conditional["If-Modified-Since"] = source["last_modified"]
                status, headers, xml, final = collector.fetch(feed, source, conditional)
                if status == 304:
                    entry.update(status="not_modified", feed=final)
                    break
                if pressroom:
                    rows, discovery_errors = discover_pressroom(xml, final, source, collector, max_items)
                    entry['errors'].extend(discovery_errors)
                else:
                    rows = parse_feed(xml, source)
                only_stale = pressroom and not rows and discovery_errors and all(
                    error['reason'] == 'ValueError:stale_report' for error in discovery_errors)
                if not rows and not only_stale:
                    raise ValueError("empty_feed")
                source.update(verified_feed=final, verified_at=now_iso(), etag=headers.get("ETag"), last_modified=headers.get("Last-Modified"))
                entry.update(status="verified_no_recent_items" if only_stale else "verified", feed=final, entries=len(rows))
                for row in rows[:max_items]:
                    if row["url"] in known:
                        continue
                    payload = {**row, "classification": classify_metadata(row["title"], row["summary"]),
                               "collected_at": now_iso(), "publisher": source["name"], "publisher_group": source.get("publisher_group") or source["id"],
                               "source_kind": source["kind"], "reliability": source["reliability"], "access_status": "unfetched"}
                    item = store.put("news_items", {"id": stable_id(row["url"]), "source_id": source["id"], "url": row["url"], "cluster_id": None, "status": "collected", "payload": payload})
                    known[row["url"]] = item
                    report["new_items"] += 1
                break
            except Exception as exc:
                entry["errors"].append({"feed": feed, "reason": type(exc).__name__ + ":" + str(exc)[:180]})
        source.update(checked_at=now_iso(), collection_status=entry["status"], diagnostics=entry["errors"])
        store.put("news_sources", {"id": source["id"], "payload": source})
        report["sources"].append(entry)
    record_run(store, "collection", report)
    return report


def hydrate_item(store, item, sources, collector):
    source = sources[item["source_id"]]
    require_recent_publication(item['payload'].get('published_at'))
    _, _, html, final = collector.fetch(item["url"], source, editorial=True)
    parser = PageText()
    parser.feed(html)
    if parser.paywall or re.search(r'"isAccessibleForFree"\s*:\s*false', html, flags=re.I):
        raise ValueError("paywall")
    content = parser.plain()
    if source.get('collection_method') == 'pressroom_index':
        doc = press_document(html)
        if not doc['published_at'] or doc['published_at'] != item['payload'].get('published_at'):
            raise ValueError('pressroom_publication_date_changed')
        content = doc['body'] or content
    if len(content.split()) < 120:
        raise ValueError("insufficient_accessible_content")
    if any(t in content.lower()[:800] for t in ("just a moment", "verify you are human", "access denied", "enable javascript and cookies")):
        raise ValueError("access_challenge")
    payload = {**item["payload"], "publisher_group": source.get("publisher_group") or source["id"],
               "content": content[:45000], "access_status": "accessible", "fetched_at": now_iso(), "final_url": final}
    import hashlib
    payload["content_hash"] = hashlib.sha256(content.encode()).hexdigest()
    require_recent_publication(payload.get('published_at'))
    item = store.put("news_items", {**item, "status": "ready", "payload": payload})
    primary_links = []
    for href in parser.links:
        try:
            url = canonical_url(urljoin(final, href))
        except ValueError:
            continue
        source_match = next((s for s in sources.values() if s["kind"] == "primary" and urlsplit(s["website"]).hostname.removeprefix("www.") == urlsplit(url).hostname.removeprefix("www.")), None)
        if source_match and urlsplit(url).path.strip("/") and len(primary_links) < 2:
            primary_links.append((url, source_match))
    return item, primary_links


def attach_cluster(store, item, extraction, ai=ai_json):
    key = event_key(extraction["event"])
    clusters = store.rows("news_story_clusters")
    cluster = next((r for r in clusters if r["event_key"] == key), None)
    candidates = [r for r in clusters if r["payload"]["event"]["action"] == extraction["event"]["action"]
                  and abs((datetime.fromisoformat(r["payload"]["event"]["date"]) - datetime.fromisoformat(extraction["event"]["date"])).days) <= 7]
    if len(candidates) > 40 and cluster is None:
        raise ValueError("event_candidate_window_requires_narrowing")
    if cluster is None and candidates:
        match = ai("news_event_identity", obj({"existing_cluster_id": STRING, "certain": BOOL, "reason": STRING}),
                   "Determine if this report covers EXACTLY the same announcement, price change, test or market release as an existing event. "
                   "Do not merge unrelated announcements about the same model. Use existing_cluster_id empty only if certainly a new event. "
                   "Set certain=false for ambiguous identity; that causes quarantine.\n" + json.dumps({
                       "new_event": extraction["event"], "facts": extraction["facts"],
                       "existing": [{"id": r["id"], **r["payload"]} for r in candidates[:40]],
                   }, ensure_ascii=False))
        if (not isinstance(match, dict) or type(match.get('certain')) is not bool
                or not isinstance(match.get('existing_cluster_id'), str)
                or not isinstance(match.get('reason'), str) or not match['reason'].strip()):
            raise ValueError('invalid_event_identity_response')
        if not match['certain']:
            raise ValueError("ambiguous_news_event_identity")
        if match.get("existing_cluster_id"):
            cluster = next((r for r in candidates if r["id"] == match["existing_cluster_id"]), None)
            if cluster is None:
                raise ValueError("invalid_existing_event_reference")
    if cluster is None:
        cluster = store.put("news_story_clusters", {"id": stable_id("news-event:" + key), "event_key": key, "payload": {"event": extraction["event"], "brands": extraction.get("brands", []), "created_at": now_iso()}})
    p = {**item["payload"], "extraction": extraction}
    return store.put("news_items", {**item, "cluster_id": cluster["id"], "status": "processed", "payload": p})


def process_items(store, sources, max_items=6, ai=ai_json, collector=None):
    collector = collector or Collector()
    source_map = {s["id"]: s for s in sources}
    for source in sources:
        if not store.get("news_sources", source["id"]):
            store.put("news_sources", {"id": source["id"], "payload": source})
    models = models_for_news(store)
    def retryable(row):
        if row["status"] == "collected":
            due = iso_date(row['payload'].get('budget_retry_after'))
            return not due or datetime.now(timezone.utc) >= datetime.fromisoformat(due)
        if row["status"] != "quarantined" or row["payload"].get("attempts", 0) >= 3:
            return False
        reason = " ".join(row["payload"].get("quarantine_reasons", []))
        retry_date = iso_date(row["payload"].get("retry_after"))
        due = not retry_date or datetime.now(timezone.utc) >= datetime.fromisoformat(retry_date)
        return due and any(t in reason for t in ("OPENAI_API_KEY_missing", "URLError", "HTTP Error 429", "HTTP Error 500", "HTTP Error 503"))
    queue = sorted((r for r in store.rows("news_items") if retryable(r)), key=lambda r: (
        r["payload"].get("classification", {}).get("discovery_priority", 0),
        r["payload"].get("published_at") or ""), reverse=True)[:max_items]
    result = []
    linked = set()
    for item in queue:
        try:
            published = iso_date(item["payload"].get("published_at"))
            if not published or (datetime.now(timezone.utc) - datetime.fromisoformat(published)).total_seconds() > 7 * 86400:
                store.put("news_items", {**item, "status": "irrelevant", "payload": {**item["payload"], "skip_reason": "missing_or_stale_publication_date"}})
                continue
            item, primary_links = hydrate_item(store, item, source_map, collector)
            # A budget stop during event matching must not buy the same facts again.
            signature = artifact_hash({
                'version': 'news-fact-checkpoint-v1', 'recipe': EDITORIAL_RECIPE, 'policy': EDITORIAL_POLICY,
                'source_id': item['source_id'], 'url': item['url'],
                'provenance': {key: item['payload'].get(key) for key in (
                    'content_hash', 'final_url', 'title', 'published_at', 'source_kind',
                    'publisher', 'publisher_group', 'reliability')},
                'model_keys': sorted(models),
            })
            checkpoint = item['payload'].get('fact_checkpoint')
            extraction = (checkpoint['extraction'] if isinstance(checkpoint, dict)
                          and checkpoint.get('signature') == signature
                          else extract_facts(item, list(models), ai))
            extraction, rejected_facts, errors = partition_fact_extraction(extraction, item)
            if rejected_facts:
                item = store.put('news_items', {**item, 'payload': {**item['payload'], 'fact_quarantine': rejected_facts}})
            if errors:
                raise ValueError(";".join(errors))
            item = store.put('news_items', {**item, 'payload': {**item['payload'],
                             'fact_checkpoint': {'signature': signature, 'extraction': extraction}}})
            item = attach_cluster(store, item, extraction, ai)
            processed = {"item_id": item["id"], "status": "processed", "cluster_id": item["cluster_id"]}
            result.append(processed)
            for url, source in primary_links:
                if url in linked or any(r["url"] == url for r in store.rows("news_items")):
                    continue
                linked.add(url)
                try:
                    # Primary release dates must come from the release, not the linking report.
                    _, _, html, _ = collector.fetch(url, source, editorial=True)
                    date_match = re.search(r'"datePublished"\s*:\s*"([^\"]+)"', html)
                    date = iso_date(date_match.group(1)) if date_match else None
                    if not date:
                        continue
                    p = {"title": source["name"], "published_at": date, "collected_at": now_iso(), "publisher": source["name"], "source_kind": "primary", "reliability": source["reliability"], "access_status": "unfetched"}
                    store.put("news_items", {"id": stable_id(url), "source_id": source["id"], "url": url, "cluster_id": None, "status": "collected", "payload": p})
                except Exception as exc:
                    processed.setdefault('primary_source_errors', []).append({
                        'url': url, 'reason': type(exc).__name__ + ':' + str(exc)[:180]})
        except NewsBudgetBlocked:
            from datetime import timedelta
            store.put('news_items', {**item, 'status': 'collected', 'payload': {**item['payload'],
                      'budget_retry_after': (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()}})
            result.append({'item_id': item['id'], 'status': 'deferred_budget'})
            break
        except Exception as exc:
            from datetime import timedelta
            p = {**item["payload"], "quarantine_reasons": [type(exc).__name__ + ":" + str(exc)[:300]],
                 "attempts": item["payload"].get("attempts", 0) + 1,
                 "retry_after": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()}
            if item.get("status") != "processed":
                store.put("news_items", {**item, "status": "quarantined", "payload": p})
            result.append({"item_id": item["id"], "status": "quarantined", "reason": p["quarantine_reasons"]})
    record_run(store, "fact_extraction", {"items": result})
    return result


def editorial(store, max_stories=3, ai=ai_json, retry=False, max_revisions=1, _revision=0, _only_articles=None, publish=True):
    if max_revisions not in (0, 1) or _revision not in (0, 1):
        raise ValueError('news_revision_limit_must_be_zero_or_one')
    models = models_for_news(store)
    reports = []
    for cluster in store.rows("news_story_clusters"):
        if len(reports) >= max_stories:
            break
        article_id = stable_id("article:" + cluster["id"])
        if _only_articles is not None and article_id not in _only_articles:
            continue
        old = store.get("news_articles", article_id)
        if old and old["status"] == "published":
            continue
        if publish and store.backend == 'supabase' and sum(a['status'] == 'published' and str(a.get('published_at','')).startswith(now_iso()[:10])
                                               for a in store.rows('news_articles')) >= 2:
            reports.append({'article_id': article_id, 'status': 'deferred_daily_limit'})
            break
        if old and old["status"] == "draft" and old['payload'].get('editorial_recipe') == EDITORIAL_RECIPE:
            passed = {c['kind'] for c in store.rows('news_quality_checks')
                      if c['article_id'] == article_id and c['passed'] and c['artifact_hash'] == old['artifact_hash']
                      and c['payload'].get('policy_version') == EDITORIAL_POLICY}
            if not publish and passed == {'evidence', 'editorial', 'originality'}:
                reports.append({'article_id': article_id, 'status': 'validated_draft'})
                continue
            if publish:
                try:
                    store.publish(article_id)
                    reports.append({"article_id": article_id, "status": "published"})
                    queue_verification(store, old, cluster, old["payload"].get("related_models", []))
                    continue
                except ValueError as exc:
                    if "daily_limit" in str(exc):
                        reports.append({"article_id": article_id, "status": "deferred_daily_limit"})
                        continue
        items = [i for i in store.rows("news_items") if i.get("cluster_id") == cluster["id"] and i["status"] == "processed"]
        fingerprint = "|".join(sorted(i["id"] + i["payload"]["content_hash"] for i in items))
        same_input = bool(old and old['payload'].get('input_fingerprint') == fingerprint
                          and old['payload'].get('editorial_policy') == EDITORIAL_POLICY
                          and old['payload'].get('editorial_recipe') == EDITORIAL_RECIPE)
        if same_input and any(check['article_id'] == article_id and check['artifact_hash'] == old['artifact_hash']
                              and 'independent_audit_invalid' in check['payload'].get('errors', [])
                              for check in store.rows('news_quality_checks')):
            continue
        revision = old['payload'].get('revision_count', 0) + 1 if same_input else _revision
        if same_input and (revision > 1 or (not retry and max_revisions == 0)):
            continue
        if not items:
            continue
        items.sort(key=lambda i: (i["payload"]["source_kind"] != "primary", -i["payload"]["reliability"]))
        items = items[:4]
        lead = items[0]
        score = relevance_score(lead["payload"]["extraction"], lead["payload"]["reliability"], lead["payload"]["published_at"])
        if score < 70:
            continue
        facts = []
        for item in items:
            for index, f in enumerate(item["payload"]["extraction"]["facts"]):
                facts.append({**f, "id": item["id"] + ":f" + str(index), "item_id": item["id"], "publisher": item["payload"]["publisher"]})
        facts = market_qualified_facts(facts)
        for item in items:
            facts.extend(source_technical_facts(item, facts))
            for fact in source_qualifier_facts(item):
                if not any(f['item_id'] == item['id'] and f['evidence'] == fact['evidence'] for f in facts):
                    facts.append(fact)
        facts = neutral_facts(facts)
        try:
            revising = same_input
            previous_checks = [check for check in store.rows('news_quality_checks')
                               if old and check['article_id'] == old['id'] and check['artifact_hash'] == old['artifact_hash']] if revising else []
            feedback = {'errors': [error for check in previous_checks for error in check['payload'].get('errors', [])],
                        'unsupported_blocks': [b for check in previous_checks
                                               for b in check['payload'].get('audit', {}).get('blocks', [])
                                               if b.get('supported') is False]}
            if revising and old:
                feedback['previous_draft'] = {k: old['payload'][k] for k in ('title', 'title_fact_ids', 'intro', 'intro_fact_ids', 'paragraphs')}
                feedback['source_overlaps'] = source_overlaps(old['payload'], items, limit=32, per_block_limit=1)
                feedback['draft_precheck'] = article_preflight(old['payload'], facts, items, score)
            targeted = (revising and old and 0 < len(feedback['unsupported_blocks']) <= 2
                        and set(feedback['errors']) <= {'block_audit_failed_or_incomplete', 'audit_no_unsupported_claims'}
                        and all(re.fullmatch(r'p[0-9]+', b['id']) for b in feedback['unsupported_blocks']))
            precheck_errors = feedback.get('draft_precheck', {}).get('errors', [])
            language_targets = [*feedback.get('source_overlaps', []),
                                *[{'block_id': error.split(':')[1], 'reason': error}
                                  for error in precheck_errors if error.startswith('unverified_comparison:')]]
            copied_blocks = {match['block_id'] for match in language_targets}
            source_repair = (revising and precheck_errors
                             and all(error.startswith(('source_wording_overlap:', 'unverified_comparison:')) for error in precheck_errors)
                             and 0 < len(copied_blocks) <= 3
                             and copied_blocks <= {block['id'] for block in blocks(old['payload'])})
            if source_repair:
                draft = repair_source_wording(old['payload'], facts, language_targets, ai)
            elif targeted:
                draft = repair_article(old['payload'], facts, feedback, ai)
            else:
                draft = generate_article(facts, ai, feedback)
            precheck = article_preflight(draft, facts, items, score)
            audit = audit_article(draft, facts, ai) if not precheck['errors'] else None
            checks = validate_article(draft, facts, items, audit, score)
            extracted_keys = {key for i in items for key in i["payload"]["extraction"].get("model_keys", [])}
            related = []
            evidence_text = normalize(" ".join(f["statement"] for f in facts))
            for key in sorted(extracted_keys & models.keys()):
                model = models[key]
                if normalize(model["brand"]) in evidence_text and normalize(model["model"]) in evidence_text:
                    related.append(model)
            source_refs = [{"item_id": i["id"], "url": i["url"], "publisher": i["payload"]["publisher"], "title": i["payload"]["title"], "published_at": i["payload"]["published_at"], "kind": i["payload"]["source_kind"]} for i in items]
            slug = "-".join(normalize(draft["title"]).split())[:100].rstrip("-") + "-" + article_id[:8]
            payload = {**draft, "editorial_policy": EDITORIAL_POLICY, "editorial_recipe": EDITORIAL_RECIPE, "revision_count": revision,
                       "category": lead["payload"]["extraction"]["category"], "brands": sorted({b for i in items for b in i["payload"]["extraction"].get("brands", [])}),
                       "sources": source_refs, "related_models": related, "relevance_score": score,
                       "input_fingerprint": fingerprint, "editorial_method": "AI-bearbetad nyhet med källgranskning", "image": None}
            article = store.put("news_articles", {"id": article_id, "cluster_id": cluster["id"], "slug": slug, "status": "draft", "published_at": None, "payload": payload})
            for source in source_refs:
                store.put("news_article_sources", {"id": stable_id(article_id + source["item_id"]), "article_id": article_id, "item_id": source["item_id"], "payload": source})
            for model in related:
                store.put("news_vehicle_links", {"id": stable_id(article_id + model["key"]), "article_id": article_id, "canonical_model_id": model.get("canonical_model_id"), "payload": model})
            for kind, errors in checks.items():
                store.put("news_quality_checks", {"id": stable_id(article_id + kind + article["artifact_hash"]), "article_id": article_id, "kind": kind, "artifact_hash": article["artifact_hash"], "passed": not errors, "payload": {"errors": errors, "audit": (audit or {}) if kind == "editorial" else {}, "fact_inventory": facts if kind == 'evidence' else [], "fact_plan": build_fact_plan(facts) if kind == 'evidence' and draft.get('fact_plan_hash') else None, "draft_precheck": precheck, "audit_performed": bool(audit), "checked_at": now_iso(), "policy_version": EDITORIAL_POLICY}})
            failures = [error for values in checks.values() for error in values]
            if failures:
                store.put("news_articles", {**article, "status": "quarantined"})
                reports.append({"article_id": article_id, "status": "quarantined", "reasons": failures})
                continue
            if not publish:
                reports.append({'article_id': article_id, 'status': 'validated_draft'})
                continue
            store.publish(article_id)
            queue_verification(store, article, cluster, related)
            reports.append({"article_id": article_id, "status": "published"})
        except NewsBudgetBlocked:
            reports.append({'article_id': article_id, 'status': 'deferred_budget'})
            break
        except Exception as exc:
            reason = type(exc).__name__ + ":" + str(exc)[:300]
            store.put("news_story_clusters", {**cluster, "payload": {**cluster["payload"], "editorial_state": "quarantined", "quarantine_reasons": [reason]}})
            reports.append({"cluster_id": cluster["id"], "status": "failed", "reason": reason})
    # Rewriting prose cannot repair a malformed review response.
    failed = {r['article_id'] for r in reports if r['status'] == 'quarantined'
              and not any(error.startswith('audit_contract_invalid:') or error == 'independent_audit_invalid'
                          for error in r.get('reasons', []))}
    if _revision < max_revisions and failed:
        repaired = editorial(store, max_stories=max_stories, ai=ai, retry=True, max_revisions=0,
                             _revision=1, _only_articles=failed, publish=publish)
        by_id = {r.get('article_id') or r.get('cluster_id'): r for r in repaired}
        reports = [by_id.get(r.get('article_id') or r.get('cluster_id'), r) for r in reports]
    record_run(store, "editorial", {"articles": reports})
    return reports


def queue_verification(store, article, cluster, related):
    action = cluster["payload"]["event"]["action"]
    if action not in {"launch", "price", "battery", "update", "recall"}:
        return
    for model in related:
        key = stable_id("verify:" + article["id"] + model["key"])
        if store.get("news_verification_requests", key):
            continue
        store.put("news_verification_requests", {"id": key, "article_id": article["id"], "status": "pending", "payload": {
            "model_key": model["key"], "brand": model["brand"], "model": model["model"],
            "reason": action, "requested_at": now_iso(), "source_policy": "official_swedish_manufacturer_importer_only",
        }})


def export_public(store, path=None):
    path = Path(path or ROOT / "public/data/news_articles.json")
    rows = store.public_articles()
    # Internal provenance and AI fact IDs stay in the private audit tables.
    public_keys = {"id", "slug", "published_at", "title", "intro", "paragraphs", "category", "brands", "sources", "related_models", "editorial_method", "image"}
    cleaned = [{k: v for k, v in r.items() if k in public_keys} for r in rows]
    for row in cleaned:
        row["paragraphs"] = [{"text": p["text"], "kind": p["kind"]} for p in row["paragraphs"]]
        row['sources'] = [{k: v for k, v in source.items()
                           if k in {'url', 'publisher', 'title', 'published_at', 'kind'}}
                          for source in row.get('sources', [])]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"generated_at": now_iso(), "records": cleaned}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"published": len(cleaned), "output": str(path)}


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["collect", "run", "notices", "export", "status", "verification-queue"])
    parser.add_argument('--format', choices=['notice', 'article'], default='notice',
                        help='Notices are private and free; legacy article mode must be requested explicitly')
    parser.add_argument("--backend", choices=["sqlite", "supabase"], default=os.environ.get("NEWS_BACKEND", "sqlite"))
    parser.add_argument("--db", type=Path)
    parser.add_argument("--max-items", type=int, default=6)
    parser.add_argument("--max-stories", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--retry", action="store_true")
    parser.add_argument('--stage-only', action='store_true', help='Validate private drafts without publishing or exporting public files')
    args = parser.parse_args()
    store = NewsStore(args.db, args.backend)
    try:
        if args.command in {"collect", "run", "notices"}:
            notices = args.command == 'notices' or (args.command == 'run' and args.format == 'notice')
            sources = notice_sources(registry()) if notices else registry()
            result = {"collection": collect(store, sources, max_items=20, force=args.force)}
            if notices:
                collector = Collector()
                source_map = {s['id']:s for s in sources}
                def refresh(item):
                    return hydrate_item(store, item, source_map, collector)[0]
                result['editorial'] = stage_notices(store, sources, models_for_news(store), max_items=args.max_items, refresh=refresh)
                result['editorial_status'] = 'private_notice_staging'
                result['ai_usage'] = {'provider_requests':0, 'cost_usd':0}
            elif args.command == "run":
                if not os.environ.get("OPENAI_API_KEY"):
                    result["editorial_status"] = "blocked_missing_OPENAI_API_KEY"
                    record_run(store, "editorial_blocked", {"reason": result["editorial_status"]})
                elif store.backend != 'supabase':
                    result['editorial_status'] = 'paid_news_requires_supabase_or_explicit_isolated_test'
                else:
                    ai = NewsAi(store.client)
                    result["extraction"] = process_items(store, registry(), max_items=max(0, min(args.max_items, 20)), ai=ai)
                    result["editorial"] = editorial(store, max_stories=max(0, min(args.max_stories, 2)),
                                                    retry=args.retry, ai=ai, publish=not args.stage_only)
                    result['ai_usage'] = ai.stats
            result["export"] = {'skipped': 'stage_only' if args.stage_only else 'private_notices'} if notices or args.stage_only else export_public(store)
        elif args.command == "export":
            result = export_public(store)
        elif args.command == "verification-queue":
            result = {"requests": [r for r in store.rows("news_verification_requests") if r["status"] == "pending"]}
        else:
            result = {"backend": store.backend, "counts": {t: len(store.rows(t)) for t in ("news_sources", "news_items", "news_story_clusters", "news_articles", "news_quality_checks")}, "runs": store.rows("news_ingestion_runs")[-5:]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
