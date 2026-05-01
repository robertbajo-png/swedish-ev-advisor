import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIDENCE_THRESHOLD = 0.92


RANGES = {
    "price_sek": (100000, 3000000),
    "wltp_range_km": (50, 1200),
    "dc_charge_kw": (20, 600),
    "ac_charge_kw": (1, 50),
    "boot_liters": (50, 3500),
    "tow_kg": (0, 4000),
    "seats": (1, 9),
}


def load_sources() -> dict[str, dict]:
    path = ROOT / "data/canonical/manufacturer_sources_validated.csv"
    if not path.exists():
        return {}
    return {row["url"]: row for row in csv.DictReader(path.open(encoding="utf-8"))}


def validate_draft(draft: dict, sources: dict[str, dict]) -> list[str]:
    errors = []
    source = sources.get(draft.get("source_url"))
    if not source or source.get("source_validation") != "reachable_official_model_source":
        errors.append("source_not_reachable_official")
    if float(draft.get("extraction_confidence") or 0) < CONFIDENCE_THRESHOLD:
        errors.append("confidence_below_threshold")
    if not draft.get("source_hash"):
        errors.append("missing_source_hash")
    if not draft.get("source_quote"):
        errors.append("missing_source_quote")
    if draft.get("price_sek") is None and draft.get("wltp_range_km") is None:
        errors.append("missing_price_or_wltp")

    for field, (low, high) in RANGES.items():
        value = draft.get(field)
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


def public_variant_from_draft(draft: dict) -> dict:
    return {
        "brand": draft["brand"],
        "model": draft["model"],
        "variant_name": draft["variant_name"],
        "price_sek": draft.get("price_sek"),
        "wltp_range_km": draft.get("wltp_range_km"),
        "battery_kwh": draft.get("battery_kwh"),
        "dc_charge_kw": draft.get("dc_charge_kw"),
        "ac_charge_kw": draft.get("ac_charge_kw"),
        "boot_liters": draft.get("boot_liters"),
        "tow_kg": draft.get("tow_kg"),
        "seats": draft.get("seats"),
        "drivetrain": draft.get("drivetrain"),
        "source_quote": draft.get("source_quote"),
        "extraction_confidence": draft.get("extraction_confidence"),
        "validation_status": "published",
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    draft_path = ROOT / "data/extraction/extracted_variant_drafts.json"
    if not draft_path.exists():
        raise RuntimeError("No extracted drafts found. Run scripts/extract_manufacturer_specs.py first.")
    drafts = json.loads(draft_path.read_text(encoding="utf-8"))
    sources = load_sources()
    published = []
    review = []
    updated_drafts = []

    for draft in drafts:
        errors = validate_draft(draft, sources)
        draft["validation_errors"] = errors
        if errors:
            draft["validation_status"] = "extracted"
            review.append(draft)
        else:
            draft["validation_status"] = "published"
            published.append(public_variant_from_draft(draft))
        updated_drafts.append(draft)

    out_dir = ROOT / "data/canonical"
    review_dir = ROOT / "data/review"
    out_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    (ROOT / "data/extraction/extracted_variant_drafts.json").write_text(
        json.dumps(updated_drafts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "canonical_model_variants_seed.json").write_text(
        json.dumps(published, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (review_dir / "variant_review_queue.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(out_dir / "canonical_model_variants_seed.csv", published)
    print(json.dumps({"published": len(published), "needs_review": len(review)}, indent=2))


if __name__ == "__main__":
    main()
