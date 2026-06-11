import argparse
import json
from pathlib import Path

from supabase_client import SupabaseRestClient


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STATUSES = {"published", "published_reviewed"}


def load_local_public_records() -> list[dict]:
    path = ROOT / "public" / "data" / "public_ev_variants.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("records", [])


def variant_key(row: dict) -> str:
    return "|".join([row.get("brand", ""), row.get("model", ""), row.get("variant_name", "")]).lower()


def build_local_report(local_records: list[dict]) -> dict:
    return {
        "public_variants": len(local_records),
        "bad_statuses": sorted({row.get("validation_status") for row in local_records if row.get("validation_status") not in PUBLIC_STATUSES}),
        "missing_source_hash": sum(1 for row in local_records if not row.get("source_hash")),
        "duplicate_keys": sorted(
            key for key in {variant_key(row) for row in local_records} if sum(1 for row in local_records if variant_key(row) == key) > 1
        ),
    }


def compare_remote_to_local(remote_records: list[dict], local_records: list[dict]) -> dict:
    remote_by_key = {variant_key(row): row for row in remote_records}
    local_by_key = {variant_key(row): row for row in local_records}
    return {
        "remote_public_variants": len(remote_records),
        "local_public_variants": len(local_records),
        "missing_in_remote": sorted(set(local_by_key) - set(remote_by_key)),
        "extra_in_remote": sorted(set(remote_by_key) - set(local_by_key)),
        "remote_bad_statuses": sorted({row.get("validation_status") for row in remote_records if row.get("validation_status") not in PUBLIC_STATUSES}),
        "remote_missing_source_hash": sum(1 for row in remote_records if not row.get("source_hash")),
    }


def fetch_remote_records(client: SupabaseRestClient) -> list[dict]:
    return client.select(
        "public_ev_variants",
        "brand,model,variant_name,validation_status,source_hash,source_url,price_sek,wltp_range_km",
    )


def build_report(check_remote: bool = True) -> dict:
    local_records = load_local_public_records()
    report = {
        "local": build_local_report(local_records),
        "remote": {"checked": False, "error": None},
        "contract_ok": False,
    }

    local_ok = (
        report["local"]["public_variants"] > 0
        and report["local"]["bad_statuses"] == []
        and report["local"]["missing_source_hash"] == 0
        and report["local"]["duplicate_keys"] == []
    )

    if not check_remote:
        report["contract_ok"] = local_ok
        return report

    report["remote"]["checked"] = True
    try:
        remote_records = fetch_remote_records(SupabaseRestClient())
        report["remote"].update(compare_remote_to_local(remote_records, local_records))
        report["contract_ok"] = (
            local_ok
            and report["remote"]["missing_in_remote"] == []
            and report["remote"]["extra_in_remote"] == []
            and report["remote"]["remote_bad_statuses"] == []
            and report["remote"]["remote_missing_source_hash"] == 0
        )
    except Exception as error:
        report["remote"]["error"] = str(error)
        report["contract_ok"] = False

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify that Supabase public views expose only canonical validated EV data.")
    parser.add_argument("--local-only", action="store_true", help="Check local public export without connecting to Supabase.")
    args = parser.parse_args()
    print(json.dumps(build_report(check_remote=not args.local_only), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
