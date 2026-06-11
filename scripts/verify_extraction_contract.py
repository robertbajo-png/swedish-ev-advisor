import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from extract_manufacturer_specs import MAX_SOURCE_CHARS, STRICT_EXTRACTION_SCHEMA, chunk_source_text


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STATUSES = {"published", "published_reviewed"}
ALLOWED_DRAFT_STATUSES = {"extracted", "published", "published_reviewed"}
REQUIRED_VARIANT_FIELDS = {
    "variant_name",
    "price_sek",
    "wltp_range_km",
    "battery_kwh",
    "dc_charge_kw",
    "ac_charge_kw",
    "boot_liters",
    "tow_kg",
    "seats",
    "drivetrain",
    "source_quote",
    "confidence",
}
REJECTED_DOMAIN_HINTS = (
    "car.info",
    "ev-database",
    "wikipedia",
    "biluppgifter",
    "bytbil",
    "wayke",
    "blocket",
    "autouncle",
)


def read_json(path: Path):
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("records") or payload.get("rows") or payload.get("variants") or []
    return payload


def source_domain(url: str) -> str:
    return urlparse(url or "").netloc.lower().replace("www.", "")


def validate_schema() -> list[str]:
    errors = []
    if STRICT_EXTRACTION_SCHEMA.get("additionalProperties") is not False:
        errors.append("root_schema_allows_additional_properties")
    variants = STRICT_EXTRACTION_SCHEMA.get("properties", {}).get("variants", {})
    item = variants.get("items", {})
    if item.get("additionalProperties") is not False:
        errors.append("variant_schema_allows_additional_properties")
    required = set(item.get("required", []))
    if required != REQUIRED_VARIANT_FIELDS:
        errors.append(f"variant_schema_required_mismatch:{sorted(REQUIRED_VARIANT_FIELDS - required)}")
    if STRICT_EXTRACTION_SCHEMA.get("required") != ["variants"]:
        errors.append("root_schema_required_mismatch")
    chunks = chunk_source_text("a " * (MAX_SOURCE_CHARS + 5000), max_chars=MAX_SOURCE_CHARS)
    if len(chunks) < 2:
        errors.append("chunking_does_not_split_large_sources")
    if any(len(chunk) > MAX_SOURCE_CHARS for chunk in chunks):
        errors.append("chunking_exceeds_max_source_chars")
    return errors


def validate_drafts() -> list[str]:
    errors = []
    drafts = read_json(ROOT / "data/extraction/extracted_variant_drafts.json")
    for index, draft in enumerate(drafts):
        label = f"{draft.get('brand')} {draft.get('model')} {draft.get('variant_name')}"
        if draft.get("validation_status") not in ALLOWED_DRAFT_STATUSES:
            errors.append(f"draft_invalid_status:{label}:{draft.get('validation_status')}")
        for field in ("brand", "model", "variant_name", "source_url", "source_hash", "source_quote", "extraction_confidence"):
            if draft.get(field) in (None, ""):
                errors.append(f"draft_missing_{field}:{label}")
        payload = draft.get("extraction_payload")
        if not isinstance(payload, dict):
            errors.append(f"draft_missing_payload:{label}")
        elif payload.get("source") != "official_variant_overrides":
            missing_payload_fields = REQUIRED_VARIANT_FIELDS - set(payload.keys())
            if missing_payload_fields:
                errors.append(f"draft_payload_missing_fields:{label}:{sorted(missing_payload_fields)}")
        if any(hint in str(draft.get("source_url", "")).lower() for hint in REJECTED_DOMAIN_HINTS):
            errors.append(f"draft_uses_third_party_source:{label}:{draft.get('source_url')}")
        if not source_domain(draft.get("source_url", "")):
            errors.append(f"draft_source_url_invalid:{label}:{index}")
    return errors


def validate_public_export() -> list[str]:
    errors = []
    public_rows = read_json(ROOT / "public/data/public_ev_variants.json")
    for row in public_rows:
        label = f"{row.get('brand')} {row.get('model')} {row.get('variant_name')}"
        if row.get("validation_status") not in PUBLIC_STATUSES:
            errors.append(f"public_row_not_published:{label}:{row.get('validation_status')}")
        for field in ("source_url", "source_hash", "source_quote", "extraction_confidence"):
            if row.get(field) in (None, ""):
                errors.append(f"public_missing_{field}:{label}")
        if any(hint in str(row.get("source_url", "")).lower() for hint in REJECTED_DOMAIN_HINTS):
            errors.append(f"public_uses_third_party_source:{label}:{row.get('source_url')}")
    return errors


def validate_review_queue() -> list[str]:
    errors = []
    review_rows = read_json(ROOT / "data/review/variant_review_queue.json")
    public_keys = {
        (row.get("brand"), row.get("model"), row.get("variant_name"), row.get("source_url"))
        for row in read_json(ROOT / "public/data/public_ev_variants.json")
    }
    for row in review_rows:
        key = (row.get("brand"), row.get("model"), row.get("variant_name"), row.get("source_url"))
        if key in public_keys:
            errors.append(f"review_row_also_public:{row.get('brand')} {row.get('model')} {row.get('variant_name')}")
        if not row.get("validation_errors"):
            errors.append(f"review_row_missing_validation_errors:{row.get('brand')} {row.get('model')} {row.get('variant_name')}")
    return errors


def main() -> None:
    errors = [
        *validate_schema(),
        *validate_drafts(),
        *validate_public_export(),
        *validate_review_queue(),
    ]
    report = {
        "schema_strict": not validate_schema(),
        "drafts": len(read_json(ROOT / "data/extraction/extracted_variant_drafts.json")),
        "public_rows": len(read_json(ROOT / "public/data/public_ev_variants.json")),
        "review_rows": len(read_json(ROOT / "data/review/variant_review_queue.json")),
        "max_source_chars": MAX_SOURCE_CHARS,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        sys.exit("Extraction contract failed")


if __name__ == "__main__":
    main()
