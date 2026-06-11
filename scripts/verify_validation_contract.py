import json
from pathlib import Path

from validate_extracted_variants import CONFIDENCE_THRESHOLD, RANGES, validate_draft, load_sources


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STATUSES = {"published", "published_reviewed"}


def read_json(path: Path, default):
    if not path.exists():
        return default
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("records", payload) if isinstance(payload, dict) else payload


def row_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("brand", "")).strip().lower(),
        str(row.get("model", "")).strip().lower(),
        str(row.get("variant_name", "")).strip().lower(),
    )


def numeric_errors(row: dict) -> list[str]:
    errors = []
    for field, (low, high) in RANGES.items():
        value = row.get(field)
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            errors.append(f"{field}_not_numeric")
            continue
        if numeric < low or numeric > high:
            errors.append(f"{field}_out_of_range")
    return errors


def main() -> None:
    drafts = read_json(ROOT / "data/extraction/extracted_variant_drafts.json", [])
    canonical_public = read_json(ROOT / "data/canonical/canonical_model_variants_seed.json", [])
    exported_public = read_json(ROOT / "public/data/public_ev_variants.json", [])
    review_rows = read_json(ROOT / "data/review/variant_review_queue.json", [])
    sources = load_sources()

    public_keys = {row_key(row) for row in exported_public}
    review_keys = {row_key(row) for row in review_rows}
    errors = []

    for row in canonical_public:
        if row.get("validation_status") not in PUBLIC_STATUSES:
            errors.append(f"canonical_non_public_status:{row_key(row)}:{row.get('validation_status')}")
        if row.get("validation_status") == "published" and float(row.get("extraction_confidence") or 0) < CONFIDENCE_THRESHOLD:
            errors.append(f"published_below_confidence:{row_key(row)}")
        if not row.get("source_url") or not row.get("source_hash") or not row.get("source_quote"):
            errors.append(f"published_missing_evidence:{row_key(row)}")
        if row.get("price_sek") is None and row.get("wltp_range_km") is None:
            errors.append(f"published_missing_price_or_wltp:{row_key(row)}")
        for numeric_error in numeric_errors(row):
            errors.append(f"{numeric_error}:{row_key(row)}")

    for row in exported_public:
        if row.get("validation_status") not in PUBLIC_STATUSES:
            errors.append(f"exported_non_public_status:{row_key(row)}:{row.get('validation_status')}")
        if row_key(row) in review_keys:
            errors.append(f"review_row_exported_publicly:{row_key(row)}")

    for row in review_rows:
        if not row.get("validation_errors"):
            errors.append(f"review_missing_validation_errors:{row_key(row)}")
        if row_key(row) in public_keys:
            errors.append(f"review_key_in_public_export:{row_key(row)}")

    for draft in drafts:
        status = draft.get("validation_status")
        if status == "published":
            validation_errors = validate_draft(draft, sources)
            if validation_errors:
                errors.append(f"published_draft_fails_validation:{row_key(draft)}:{','.join(validation_errors)}")
        elif status == "extracted" and not draft.get("validation_errors"):
            errors.append(f"extracted_draft_missing_errors:{row_key(draft)}")

    report = {
        "drafts": len(drafts),
        "canonical_public_rows": len(canonical_public),
        "exported_public_rows": len(exported_public),
        "review_rows": len(review_rows),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "public_statuses": sorted(PUBLIC_STATUSES),
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit("Validation contract failed")


if __name__ == "__main__":
    main()
