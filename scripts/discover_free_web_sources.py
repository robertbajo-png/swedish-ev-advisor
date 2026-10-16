import argparse
import csv
import hashlib
import html.parser
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from canonical_model_names import normalize
from source_policy import source_policy_errors, source_url_matches_model


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "swedish-ev-advisor/0.2 (+source-discovery)"


class LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in {"a", "link"}:
            return
        for key, value in attrs:
            if key == "href" and value:
                self.links.append(value)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def fetch(url: str, timeout: int = 15) -> tuple[int, str, bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.5"})
    with urlopen(request, timeout=timeout) as response:
        return response.status, response.geturl(), response.read(), response.headers.get("content-type", "")


def sitemap_urls(content: bytes) -> list[str]:
    root = ET.fromstring(content)
    return [node.text.strip() for node in root.iter() if node.tag.endswith("loc") and node.text]


def html_links(content: bytes, base_url: str) -> list[str]:
    parser = LinkParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    return [urljoin(base_url, link) for link in parser.links]


def same_domain(url: str, allowed_domain: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    allowed = allowed_domain.lower().removeprefix("www.")
    return host == allowed or host.endswith(f".{allowed}")


def model_tokens(model: str) -> list[str]:
    ignored = {"electric", "e", "tech", "passenger"}
    return [token for token in normalize(model).split() if len(token) > 1 and token not in ignored]


def url_score(url: str, model: str) -> int:
    value = normalize(url)
    tokens = model_tokens(model)
    if not tokens or not all(token in value for token in tokens):
        return 0
    score = 10 + len(tokens) * 4
    for marker in ("sv", "se", "sverige", "model", "modeller", "bilar", "electric", "elbil"):
        if marker in value:
            score += 1
    lower_url = url.lower()
    if any(marker in lower_url for marker in (".se/", "/se/", "/sv-se/", "/sv_se/", "/sweden/")):
        score += 12
    if any(marker in lower_url for marker in ("/canarias/", "/es-es/", "/de-de/", "/fr-fr/", "/it-it/", "/nl-nl/")):
        score -= 30
    for marker in ("used", "begagnad", "news", "nyheter", "support", "privacy"):
        if marker in value:
            score -= 5
    return score


def source_market(final_url: str, content: bytes) -> tuple[str, str]:
    parsed = urlparse(final_url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    if any(marker in path for marker in ("/canarias/", "/es-es/", "/de-de/", "/fr-fr/", "/it-it/", "/nl-nl/")):
        return "foreign", ""
    decoded = content[:200000].decode("utf-8", errors="replace").lower()
    swedish_text = sum(marker in decoded for marker in ("räckvidd", "pris från", "bygg din", "återförsäljare")) >= 2
    if host.endswith(".se") or any(marker in path for marker in ("/se/", "/sv-se/", "/sv_se/", "/sweden/")) or swedish_text:
        return "SE", "sv"
    return "EU", "en"


def infer_source_type(url: str, authority: str) -> str:
    lower = url.lower()
    if authority == "authorized_dealer":
        return "authorized_dealer_stock_page" if any(token in lower for token in ("lager", "stock", "vehicle", "bil/")) else "authorized_dealer_model_page"
    if lower.endswith(".pdf") or "prislista" in lower or "price-list" in lower:
        return "manufacturer_price_list"
    if any(token in lower for token in ("spec", "technical", "teknisk")):
        return "manufacturer_specs_page"
    if any(token in lower for token in ("config", "bygg-din", "build")):
        return "manufacturer_configurator"
    return "manufacturer_model_page"


def verified_page_image(content: bytes, final_url: str, model: str) -> str:
    raw = content.decode("utf-8", errors="replace")
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    title = re.sub(r"\s+", " ", title_match.group(1)).lower() if title_match else ""
    tokens = model_tokens(model)
    if not tokens or not all(token in normalize(title) for token in tokens):
        return ""
    patterns = (
        r'(?is)<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'(?is)<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'(?is)<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
    )
    for pattern in patterns:
        match = re.search(pattern, raw)
        if not match:
            continue
        image_url = urljoin(final_url, match.group(1).replace("&amp;", "&"))
        lower = image_url.lower()
        if image_url.startswith(("http://", "https://")) and not any(token in lower for token in ("logo", "icon", "avatar", "placeholder")):
            return image_url
    return ""


def discover_domain_urls(domain: str, model: str, timeout: int) -> list[str]:
    base = f"https://www.{domain.strip().removeprefix('www.')}"
    found: set[str] = set()
    sitemap_indexes: list[str] = []
    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            _, final_url, content, content_type = fetch(urljoin(base, path), timeout)
            if "xml" in content_type or content.lstrip().startswith(b"<"):
                urls = sitemap_urls(content)
                found.update(url for url in urls if same_domain(url, domain))
                sitemap_indexes.extend(url for url in urls if url.lower().endswith((".xml", ".xml.gz")))
            else:
                found.update(url for url in html_links(content, final_url) if same_domain(url, domain))
        except (HTTPError, URLError, TimeoutError, ET.ParseError, ValueError):
            continue
    for sitemap_url in sitemap_indexes[:8]:
        if sitemap_url.lower().endswith(".gz"):
            continue
        try:
            _, _, content, _ = fetch(sitemap_url, timeout)
            found.update(url for url in sitemap_urls(content) if same_domain(url, domain))
        except (HTTPError, URLError, TimeoutError, ET.ParseError, ValueError):
            continue
    if not found:
        try:
            _, final_url, content, _ = fetch(base, timeout)
            found.update(url for url in html_links(content, final_url) if same_domain(url, domain))
        except (HTTPError, URLError, TimeoutError):
            pass
    return sorted(
        (url for url in found if url_score(url, model) > 0 and not urlparse(url).path.lower().endswith((".xml", ".xml.gz")) and "sitemap" not in urlparse(url).path.lower()),
        key=lambda url: (-url_score(url, model), len(url)),
    )


def explicit_rule_urls(rule: dict, model: str) -> list[str]:
    patterns = rule.get("explicit_patterns", {})
    path = next((value for name, value in patterns.items() if normalize(name) == normalize(model)), None)
    domains = rule.get("accepted_domains", [])
    if not path or not domains:
        return []
    return [urljoin(f"https://www.{domains[0].removeprefix('www.')}", path)]


def validate_candidate(candidate: dict, timeout: int) -> dict:
    errors = source_policy_errors(candidate)
    if errors:
        return {**candidate, "source_validation": "rejected_source_policy", "extraction_status": "blocked", "validation_errors": "|".join(errors)}
    try:
        status, final_url, content, content_type = fetch(candidate["url"], timeout)
        exact_match = source_url_matches_model(final_url, candidate["model"])
        market, language = source_market(final_url, content)
        approved = 200 <= status < 400 and exact_match and market != "foreign"
        validation = (
            "reachable_approved_source" if candidate["source_authority"] == "authorized_dealer"
            else "reachable_official_model_source" if market == "SE"
            else "reachable_eu_official_source"
        )
        return {
            **candidate,
            "country": market if market != "foreign" else candidate.get("country", ""),
            "language": language or candidate.get("language", ""),
            "http_status": status,
            "final_url": final_url,
            "content_hash": hashlib.sha256(content).hexdigest(),
            "content_type": content_type,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_validation": validation if approved else "foreign_market_source" if market == "foreign" else "model_identity_not_confirmed",
            "extraction_status": "queued" if approved else "needs_review",
            "validation_errors": "" if approved else "foreign_market_not_allowed" if market == "foreign" else "exact_model_not_confirmed",
            "image_url": verified_page_image(content, final_url, candidate["model"]) if approved and "html" in content_type.lower() else "",
            "image_source_url": final_url if approved else "",
            "image_verified_at": datetime.now(timezone.utc).isoformat() if approved else "",
        }
    except HTTPError as error:
        return {**candidate, "http_status": error.code, "source_validation": "unreachable_or_redirect_problem", "extraction_status": "blocked", "validation_errors": f"http_{error.code}"}
    except (URLError, TimeoutError) as error:
        return {**candidate, "http_status": "", "source_validation": "needs_discovery", "extraction_status": "blocked", "validation_errors": type(error).__name__}


def existing_candidates(scope_row: dict, rows: list[dict]) -> list[dict]:
    key = (normalize(scope_row["brand"]), normalize(scope_row["model"]))
    return [
        row for row in rows
        if (normalize(row.get("brand")), normalize(row.get("model"))) == key
        and row.get("url")
        and "ev_advisor_discovery_query=" not in row["url"]
        and "google.com/search" not in row["url"]
    ]


def dealer_candidates(scope_row: dict, dealers: list[dict], timeout: int) -> list[dict]:
    output = []
    for dealer in dealers:
        brands = {normalize(brand) for brand in dealer.get("brands", [])}
        if normalize(scope_row["brand"]) not in brands:
            continue
        for url in discover_domain_urls(dealer["domain"], scope_row["model"], timeout)[:2]:
            output.append({
                "brand": scope_row["brand"], "model": scope_row["model"], "url": url,
                "source_type": infer_source_type(url, "authorized_dealer"), "source_authority": "authorized_dealer",
                "source_name": dealer["name"], "authorization_evidence_url": dealer["authorization_evidence_url"],
                "country": "SE", "language": "sv", "research_rank": scope_row["market_rank"],
            })
    return output


def discover(scope: list[dict], rules: dict, existing_sources: list[dict], dealers: list[dict], timeout: int = 15) -> list[dict]:
    results: list[dict] = []
    normalized_rules = {normalize(brand): rule for brand, rule in rules.items()}
    for row in scope:
        validated: list[dict] = []
        for candidate in existing_candidates(row, existing_sources):
            candidate.setdefault("source_authority", "manufacturer")
            candidate.setdefault("source_name", candidate.get("brand"))
            candidate.setdefault("authorization_evidence_url", "")
            candidate.setdefault("research_rank", row["market_rank"])
            validated.append(validate_candidate(candidate, timeout))

        if not any(source.get("source_validation") in {"reachable_official_model_source", "reachable_eu_official_source", "reachable_approved_source"} for source in validated):
            rule = normalized_rules.get(normalize(row["brand"]), {})
            for url in explicit_rule_urls(rule, row["model"]):
                candidate = {
                    "brand": row["brand"], "model": row["model"], "url": url,
                    "source_type": infer_source_type(url, "manufacturer"), "source_authority": "manufacturer",
                    "source_name": row["brand"], "authorization_evidence_url": "", "country": "SE", "language": "sv",
                    "research_rank": row["market_rank"],
                }
                validated.append(validate_candidate(candidate, timeout))
            for domain in rule.get("accepted_domains", []):
                for url in discover_domain_urls(domain, row["model"], timeout)[:3]:
                    candidate = {
                        "brand": row["brand"], "model": row["model"], "url": url,
                        "source_type": infer_source_type(url, "manufacturer"), "source_authority": "manufacturer",
                        "source_name": row["brand"], "authorization_evidence_url": "", "country": "SE", "language": "sv",
                        "research_rank": row["market_rank"],
                    }
                    validated.append(validate_candidate(candidate, timeout))

        for candidate in dealer_candidates(row, dealers, timeout):
            validated.append(validate_candidate(candidate, timeout))

        if not validated:
            results.append({
                "brand": row["brand"], "model": row["model"], "url": "", "source_type": "manufacturer_model_page",
                "source_authority": "manufacturer", "source_name": row["brand"], "authorization_evidence_url": "",
                "research_rank": row["market_rank"], "source_validation": "needs_discovery", "extraction_status": "blocked",
                "validation_errors": "no_free_web_candidate",
            })
            continue
        results.extend(validated)
    return results


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover free manufacturer and authorized-dealer web sources.")
    parser.add_argument("--scope", type=Path, default=ROOT / "data/expansion/expansion_scope.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data/expansion/expansion_sources.csv")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    scope = json.loads(args.scope.read_text(encoding="utf-8"))
    if args.limit:
        scope = scope[: args.limit]
    rules = json.loads((ROOT / "data/canonical/brand_source_resolver_rules.json").read_text(encoding="utf-8"))
    dealers = json.loads((ROOT / "data/canonical/authorized_dealers.json").read_text(encoding="utf-8")).get("dealers", [])
    existing = read_csv(ROOT / "data/canonical/manufacturer_sources_seed.csv") + read_csv(ROOT / "data/canonical/manufacturer_sources_validated.csv")
    rows = discover(scope, rules, existing, dealers, timeout=args.timeout)
    write_csv(args.out, rows)
    ready = sum(row.get("source_validation") in {"reachable_official_model_source", "reachable_eu_official_source", "reachable_approved_source"} for row in rows)
    print(json.dumps({"models": len(scope), "sources": len(rows), "ready_sources": ready, "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
