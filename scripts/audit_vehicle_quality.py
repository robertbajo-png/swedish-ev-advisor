"""Measure canonical technical coverage and photography evidence without changing data."""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from verify_public_images import normalize_image_key, public_records

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('price_sek', 'wltp_range_km', 'battery_kwh', 'dc_charge_kw',
          'ac_charge_kw', 'tow_kg', 'boot_liters', 'seats', 'drivetrain', 'body_type')
CORE_FIELDS = ('price_sek', 'wltp_range_km', 'dc_charge_kw', 'tow_kg', 'boot_liters')


def present(value):
    return value is not None and value != ''


def build_report(records, rights, lookup, photo_reviews=None):
    grouped = defaultdict(list)
    for row in records:
        key = normalize_image_key(row['brand']) + '|' + normalize_image_key(row['model'])
        grouped[key].append(row)
    assets = {row['asset_url']: row for row in rights.get('assets', [])}
    reviews = (photo_reviews or {}).get('models', {})
    models = []
    for key, rows in sorted(grouped.items()):
        images = {row.get('image_url') or lookup.get(key) for row in rows}
        image = next(iter(images)) if len(images) == 1 else None
        evidence = assets.get(image, {})
        review = reviews.get(key, {})
        # A review of an older photo cannot approve a replacement's visual quality.
        reviewed = bool(image and review.get('asset_url') == image
                        and review.get('content_sha256') == evidence.get('content_sha256')
                        and review.get('status') == 'approved')
        variants = [{
            'variant_name': row['variant_name'],
            'missing_fields': [field for field in FIELDS if not present(row.get(field))],
            'missing_core_fields': [field for field in CORE_FIELDS if not present(row.get(field))],
            'source_url': row.get('source_url'),
            'source_hash_present': bool(row.get('source_hash')),
        } for row in rows]
        missing_count = sum(len(row['missing_core_fields']) for row in variants)
        models.append({
            'model_key': key, 'brand': rows[0]['brand'], 'model': rows[0]['model'],
            'variant_count': len(rows), 'missing_core_values': missing_count,
            'coverage': {field: sum(present(row.get(field)) for row in rows) for field in FIELDS},
            'image_url': image, 'image_consistent': len(images) == 1 and bool(image),
            'image_rights_documented': evidence.get('status') == 'documented',
            'professional_photo_reviewed': reviewed,
            'photo_action': 'accepted' if reviewed else 'professional_photo_review_required',
            'variants': variants,
        })
    return {
        'schema_version': 1, 'variants': len(records), 'models': len(models),
        'coverage': {field: {'present': sum(present(row.get(field)) for row in records),
                             'missing': sum(not present(row.get(field)) for row in records)}
                     for field in FIELDS},
        'complete_core_variants': sum(all(present(row.get(field)) for field in CORE_FIELDS) for row in records),
        'professional_photos_reviewed': sum(row['professional_photo_reviewed'] for row in models),
        'models_by_priority': sorted(models, key=lambda row: (-row['missing_core_values'], row['model_key'])),
        'network_calls': 0, 'database_writes': 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/review/vehicle_quality_report.json')
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    registry = ROOT / 'src/image-presentation.json'
    report = build_report(public_records(ROOT / 'public/data/public_ev_variants.json'),
        json.loads((ROOT / 'src/image-rights.json').read_text(encoding='utf-8')),
        json.loads((ROOT / 'src/model-images.json').read_text(encoding='utf-8')),
        json.loads(registry.read_text(encoding='utf-8')) if registry.exists() else None)
    report['audited_at'] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('variants', 'models', 'coverage',
        'complete_core_variants', 'professional_photos_reviewed', 'database_writes')}))
    if args.require_complete and (report['complete_core_variants'] != report['variants']
            or report['professional_photos_reviewed'] != report['models']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
