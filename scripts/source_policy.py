from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse


OFFICIAL_AUTHORITIES = {"manufacturer", "importer"}
APPROVED_SOURCE_VALIDATIONS = {"reachable_official_model_source", "reachable_eu_official_source", "reachable_approved_source"}
DEALER_SOURCE_TYPES = {"authorized_dealer_model_page", "authorized_dealer_stock_page"}
BLOCKED_COMPARISON_DOMAINS = {
    "car.info",
    "ev-database.org",
    "automobile-catalog.com",
    "ultimatespecs.com",
}


def hostname(url: str) -> str:
    return urlparse(str(url or "")).netloc.lower().removeprefix("www.")


def is_blocked_comparison_domain(url: str) -> bool:
    host = hostname(url)
    return any(host == domain or host.endswith(f".{domain}") for domain in BLOCKED_COMPARISON_DOMAINS)


def identity_tokens(model: str) -> list[str]:
    raw = str(model or "")
    normalized = unicodedata.normalize("NFKD", raw.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = [token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) > 1 or token.isdigit()]
    tokens = [token for token in tokens if token not in {"electric", "tech", "passenger"}]
    if "+" in raw:
        tokens.append("plus")
    return tokens


def source_url_matches_model(url: str, model: str) -> bool:
    normalized_url = re.sub(r"[^a-z0-9]+", "", str(url or "").lower().replace("+", "plus"))
    return bool(identity_tokens(model)) and all(token in normalized_url for token in identity_tokens(model))


def source_policy_errors(source: dict) -> list[str]:
    errors: list[str] = []
    authority = str(source.get("source_authority") or "manufacturer").strip().lower()
    source_type = str(source.get("source_type") or "").strip()
    url = str(source.get("url") or source.get("source_url") or "").strip()

    if not url.startswith(("http://", "https://")):
        errors.append("invalid_source_url")
    if "ev_advisor_discovery_query=" in url or "google.com/search" in url:
        errors.append("discovery_query_not_source")
    if urlparse(url).path.lower().endswith((".xml", ".xml.gz")) or "sitemap" in urlparse(url).path.lower():
        errors.append("sitemap_not_content_source")
    if is_blocked_comparison_domain(url):
        errors.append("comparison_site_not_allowed")
    if authority not in OFFICIAL_AUTHORITIES | {"authorized_dealer", "public_authority"}:
        errors.append("unsupported_source_authority")
    if authority == "authorized_dealer":
        if source_type not in DEALER_SOURCE_TYPES:
            errors.append("dealer_source_type_required")
        evidence = str(source.get("authorization_evidence_url") or "").strip()
        if not evidence.startswith(("http://", "https://")):
            errors.append("dealer_authorization_evidence_required")
        if not source.get("source_name"):
            errors.append("dealer_source_name_required")
    identity_source_types = {
        "manufacturer_page", "importer_page", "model_page", "specs_page", "configurator",
        "manufacturer_specs_page", "manufacturer_model_page", "manufacturer_configurator",
        "manufacturer_rendered_model_page", "manufacturer_indexed_model_page",
        "authorized_dealer_model_page", "authorized_dealer_stock_page",
    }
    if source_type in identity_source_types and source.get("model") and not source_url_matches_model(url, source.get("model")):
        errors.append("source_url_model_mismatch")
    return errors


def source_is_publishable(source: dict) -> bool:
    return (
        not source_policy_errors(source)
        and source.get("source_validation") in APPROVED_SOURCE_VALIDATIONS
    )


def source_priority(source: dict) -> tuple[int, int]:
    authority = str(source.get("source_authority") or "manufacturer").lower()
    authority_rank = {"manufacturer": 0, "importer": 1, "public_authority": 2, "authorized_dealer": 3}.get(authority, 9)
    source_type = str(source.get("source_type") or "")
    type_rank = {
        "manufacturer_price_list": 0,
        "price_list_pdf": 0,
        "technical_pdf": 1,
        "manufacturer_specs_page": 2,
        "manufacturer_model_page": 3,
        "authorized_dealer_model_page": 4,
        "authorized_dealer_stock_page": 5,
    }.get(source_type, 6)
    return authority_rank, type_rank
