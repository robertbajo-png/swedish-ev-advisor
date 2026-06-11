import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VARIANTS = ROOT / "data/canonical/canonical_model_variants_seed.json"
DEFAULT_MODELS = ROOT / "data/canonical/canonical_models_seed.json"
DEFAULT_OUT = ROOT / "public/data/public_ev_variants.json"
PUBLIC_STATUSES = {"published", "published_reviewed"}


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_key(brand, model):
    return f"{str(brand).strip().lower()}|{str(model).strip().lower()}"


def export_rows(variants, models):
    model_flags = {
        normalize_key(row.get("brand"), row.get("model")): row
        for row in models
    }
    rows = []
    for row in variants:
        if row.get("validation_status") not in PUBLIC_STATUSES:
            continue
        flags = model_flags.get(normalize_key(row.get("brand"), row.get("model")), {})
        rows.append(
            {
                "brand": row.get("brand"),
                "model": row.get("model"),
                "variant_name": row.get("variant_name"),
                "price_sek": row.get("price_sek"),
                "wltp_range_km": row.get("wltp_range_km"),
                "battery_kwh": row.get("battery_kwh"),
                "dc_charge_kw": row.get("dc_charge_kw"),
                "ac_charge_kw": row.get("ac_charge_kw"),
                "boot_liters": row.get("boot_liters"),
                "tow_kg": row.get("tow_kg"),
                "seats": row.get("seats"),
                "drivetrain": row.get("drivetrain"),
                "source_url": row.get("source_url"),
                "source_hash": row.get("source_hash"),
                "source_quote": row.get("source_quote"),
                "extraction_confidence": row.get("extraction_confidence"),
                "validation_status": row.get("validation_status"),
                "market_seen": bool(flags.get("market_seen", True)),
                "available_confirmed": bool(flags.get("available_confirmed", True)),
                "discontinued_candidate": bool(flags.get("discontinued_candidate", False)),
                "coming_or_low_volume": bool(flags.get("coming_or_low_volume", False)),
                "verified_at": row.get("review_promoted_at") or row.get("verified_at"),
            }
        )
    rows.sort(key=lambda row: (row.get("brand") or "", row.get("model") or "", row.get("variant_name") or ""))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Export canonical public EV variants for static frontend fallback.")
    parser.add_argument("--variants", default=str(DEFAULT_VARIANTS))
    parser.add_argument("--models", default=str(DEFAULT_MODELS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    rows = export_rows(read_json(Path(args.variants), []), read_json(Path(args.models), []))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "canonical_model_variants_seed",
        "records": rows,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported public EV variants: {len(rows)}")
    print(out_path)


if __name__ == "__main__":
    main()
