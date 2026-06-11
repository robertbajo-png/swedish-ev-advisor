import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERRIDES_PATH = ROOT / "data/canonical/official_variant_overrides.csv"
DRAFTS_PATH = ROOT / "data/extraction/extracted_variant_drafts.json"


NUMBER_FIELDS = {
    "price_sek": int,
    "wltp_range_km": int,
    "battery_kwh": float,
    "dc_charge_kw": int,
    "ac_charge_kw": int,
    "boot_liters": int,
    "tow_kg": int,
    "seats": int,
    "extraction_confidence": float,
}


def read_overrides(path: Path = OVERRIDES_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            parsed = {}
            for key, value in row.items():
                if key == "replace_unpublished_model_drafts":
                    parsed[key] = str(value).lower() == "true"
                elif key in NUMBER_FIELDS:
                    parsed[key] = None if value in ("", None) else NUMBER_FIELDS[key](value)
                else:
                    parsed[key] = value or None
            rows.append(parsed)
        return rows


def draft_from_override(row: dict) -> dict:
    return {
        "brand": row["brand"],
        "model": row["model"],
        "variant_name": row["variant_name"],
        "price_sek": row.get("price_sek"),
        "wltp_range_km": row.get("wltp_range_km"),
        "battery_kwh": row.get("battery_kwh"),
        "dc_charge_kw": row.get("dc_charge_kw"),
        "ac_charge_kw": row.get("ac_charge_kw"),
        "boot_liters": row.get("boot_liters"),
        "tow_kg": row.get("tow_kg"),
        "seats": row.get("seats"),
        "drivetrain": row.get("drivetrain"),
        "source_url": row["source_url"],
        "source_quote": row["source_quote"],
        "source_hash": row["source_hash"],
        "extraction_confidence": row["extraction_confidence"],
        "extraction_payload": {
            "source": "official_variant_overrides",
            "variant_name": row["variant_name"],
        },
        "validation_status": "extracted",
        "validation_errors": None,
    }


def variant_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("brand", "")).strip().lower(),
        str(row.get("model", "")).strip().lower(),
        str(row.get("variant_name", "")).strip().lower(),
    )


def model_key(row: dict) -> tuple[str, str]:
    return (
        str(row.get("brand", "")).strip().lower(),
        str(row.get("model", "")).strip().lower(),
    )


def apply_overrides(drafts: list[dict], overrides: list[dict]) -> tuple[list[dict], dict]:
    replace_models = {model_key(row) for row in overrides if row.get("replace_unpublished_model_drafts")}
    kept = []
    removed = 0
    for draft in drafts:
        if model_key(draft) in replace_models and draft.get("validation_status") != "published_reviewed":
            removed += 1
            continue
        kept.append(draft)

    by_key = {variant_key(draft): draft for draft in kept}
    for override in overrides:
        draft = draft_from_override(override)
        by_key[variant_key(draft)] = draft

    return list(by_key.values()), {"overrides": len(overrides), "removed_unpublished_model_drafts": removed, "drafts": len(by_key)}


def main() -> None:
    drafts = json.loads(DRAFTS_PATH.read_text(encoding="utf-8")) if DRAFTS_PATH.exists() else []
    overrides = read_overrides()
    updated, report = apply_overrides(drafts, overrides)
    DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRAFTS_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
