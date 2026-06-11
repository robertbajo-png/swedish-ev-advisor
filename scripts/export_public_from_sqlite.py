import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from local_sqlite_db import DEFAULT_DB_PATH, connect, public_variant_rows


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "public/data/public_ev_variants.json"


def normalize_bool(value):
    return bool(value)


def export_rows(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    connection = connect(db_path)
    try:
        rows = public_variant_rows(connection)
    finally:
        connection.close()

    output = []
    for row in rows:
        output.append(
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
                "market_seen": normalize_bool(row.get("market_seen")),
                "available_confirmed": normalize_bool(row.get("available_confirmed")),
                "discontinued_candidate": normalize_bool(row.get("discontinued_candidate")),
                "coming_or_low_volume": normalize_bool(row.get("coming_or_low_volume")),
                "verified_at": row.get("review_promoted_at") or row.get("verified_at"),
            }
        )
    return output


def write_export(rows: list[dict], out_path: Path = DEFAULT_OUT) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "local_sqlite_public_ev_variants",
        "records": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export public EV variants from the local SQLite public view.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    rows = export_rows(args.db)
    write_export(rows, args.out)
    print(json.dumps({"exported": len(rows), "source": "local_sqlite_public_ev_variants", "out": str(args.out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
