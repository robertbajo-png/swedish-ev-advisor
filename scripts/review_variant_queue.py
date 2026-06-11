import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from canonical_model_names import canonical_model_lookup, canonicalize_model_row, normalize
from validate_extracted_variants import public_variant_from_draft


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW = ROOT / "data/review/variant_review_queue.json"
DEFAULT_DRAFTS = ROOT / "data/extraction/extracted_variant_drafts.json"
DEFAULT_PUBLIC_JSON = ROOT / "data/canonical/canonical_model_variants_seed.json"
DEFAULT_PUBLIC_CSV = ROOT / "data/canonical/canonical_model_variants_seed.csv"
DEFAULT_SUMMARY_CSV = ROOT / "data/review/variant_review_summary.csv"
DEFAULT_LOG = ROOT / "data/review/variant_promotion_log.json"
DEFAULT_ALLOWED_ERRORS = {"confidence_below_threshold"}


def variant_key(row):
    return f"{row.get('brand', '')}|{row.get('model', '')}|{row.get('variant_name', '')}"


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalized_text(value):
    return normalize(value)


def canonicalize_review_row(row, lookup):
    return canonicalize_model_row(row, lookup)


def review_summary(review_rows):
    rows = []
    for row in review_rows:
        rows.append(
            {
                "key": variant_key(row),
                "brand": row.get("brand"),
                "model": row.get("model"),
                "variant_name": row.get("variant_name"),
                "price_sek": row.get("price_sek"),
                "wltp_range_km": row.get("wltp_range_km"),
                "source_url": row.get("source_url"),
                "extraction_confidence": row.get("extraction_confidence"),
                "validation_errors": ";".join(row.get("validation_errors") or []),
                "source_quote": row.get("source_quote"),
            }
        )
    return rows


def can_promote(row, allowed_errors):
    errors = set(row.get("validation_errors") or [])
    if not errors:
        return True
    if not errors.issubset(allowed_errors):
        return False
    if not row.get("source_hash") or not row.get("source_quote"):
        return False
    if row.get("price_sek") is None and row.get("wltp_range_km") is None:
        return False
    return True


def upsert_public_variant(public_rows, public_row):
    key = variant_key(public_row)
    kept = [row for row in public_rows if variant_key(row) != key]
    kept.append(public_row)
    return kept


def promote_variants(review_rows, public_rows, draft_rows, keys, allowed_errors, approved_by, reason):
    key_set = set(keys)
    promoted = []
    remaining_review = []
    promoted_at = datetime.now(timezone.utc).isoformat()
    canonical_lookup = canonical_model_lookup()

    for row in review_rows:
        key = variant_key(row)
        if key not in key_set:
            remaining_review.append(row)
            continue
        if not can_promote(row, allowed_errors):
            remaining_review.append(row)
            continue

        canonical_row = canonicalize_review_row(row, canonical_lookup)
        public_row = public_variant_from_draft(canonical_row)
        public_row["validation_status"] = "published_reviewed"
        public_row["review_approved_by"] = approved_by
        public_row["review_reason"] = reason
        public_row["review_promoted_at"] = promoted_at
        public_rows = upsert_public_variant(public_rows, public_row)
        promoted.append(
            {
                "key": key,
                "brand": row.get("brand"),
                "model": canonical_row.get("model"),
                "variant_name": row.get("variant_name"),
                "previous_validation_errors": row.get("validation_errors") or [],
                "approved_by": approved_by,
                "reason": reason,
                "promoted_at": promoted_at,
            }
        )

    promoted_keys = {row["key"] for row in promoted}
    for draft in draft_rows:
        if variant_key(draft) in promoted_keys:
            draft["validation_status"] = "published_reviewed"
            draft.update(canonicalize_review_row(draft, canonical_lookup))
            draft["review_approved_by"] = approved_by
            draft["review_reason"] = reason
            draft["review_promoted_at"] = promoted_at

    return remaining_review, public_rows, draft_rows, promoted


def auto_safe_promotion_keys(review_rows, allowed_errors=DEFAULT_ALLOWED_ERRORS):
    return [
        variant_key(row)
        for row in review_rows
        if can_promote(row, allowed_errors)
    ]


def main():
    parser = argparse.ArgumentParser(description="List or promote reviewed EV variant drafts.")
    parser.add_argument("--list", action="store_true", help="Write a review summary CSV.")
    parser.add_argument("--promote-key", action="append", default=[], help="Exact key: Brand|Model|Variant")
    parser.add_argument("--auto-safe", action="store_true", help="Promote rows that only fail allowed review errors.")
    parser.add_argument("--allow-error", action="append", default=[], help="Allowed validation error for promotion.")
    parser.add_argument("--approved-by", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    review_rows = read_json(DEFAULT_REVIEW, [])
    if args.auto_safe and not args.promote_key:
        args.promote_key = auto_safe_promotion_keys(review_rows, set(args.allow_error) if args.allow_error else set(DEFAULT_ALLOWED_ERRORS))

    if args.list or (not args.promote_key and not args.auto_safe):
        summary = review_summary(review_rows)
        write_csv(DEFAULT_SUMMARY_CSV, summary)
        print(f"Review rows: {len(summary)}")
        print(f"Wrote {DEFAULT_SUMMARY_CSV}")
        if not args.promote_key:
            return

    if not args.approved_by or not args.reason:
        raise RuntimeError("--approved-by and --reason are required when promoting review rows")

    allowed_errors = set(args.allow_error) if args.allow_error else set(DEFAULT_ALLOWED_ERRORS)
    public_rows = read_json(DEFAULT_PUBLIC_JSON, [])
    draft_rows = read_json(DEFAULT_DRAFTS, [])
    remaining_review, public_rows, draft_rows, promoted = promote_variants(
        review_rows=review_rows,
        public_rows=public_rows,
        draft_rows=draft_rows,
        keys=args.promote_key,
        allowed_errors=allowed_errors,
        approved_by=args.approved_by,
        reason=args.reason,
    )

    previous_log = read_json(DEFAULT_LOG, [])
    write_json(DEFAULT_REVIEW, remaining_review)
    write_json(DEFAULT_PUBLIC_JSON, public_rows)
    write_json(DEFAULT_DRAFTS, draft_rows)
    write_json(DEFAULT_LOG, previous_log + promoted)
    write_csv(DEFAULT_PUBLIC_CSV, public_rows)
    write_csv(DEFAULT_SUMMARY_CSV, review_summary(remaining_review))
    print(json.dumps({"promoted": len(promoted), "remaining_review": len(remaining_review)}, indent=2))


if __name__ == "__main__":
    main()
