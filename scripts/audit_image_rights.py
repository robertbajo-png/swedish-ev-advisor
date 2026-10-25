"""Offline rights inventory, separate from exact-model image identification."""
import argparse
import ast
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from verify_public_images import normalize_image_key, public_records

ROOT = Path(__file__).resolve().parents[1]
LICENSES = {'CC-BY-4.0': 'https://creativecommons.org/licenses/by/4.0/',
            'CC-BY-SA-4.0': 'https://creativecommons.org/licenses/by-sa/4.0/',
            'CC0-1.0': 'https://creativecommons.org/publicdomain/zero/1.0/'}


def https_url(value):
    try:
        parsed = urlsplit(value)
        return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password and parsed.port in (None, 443)
    except (TypeError, ValueError):
        return False


def rights_errors(asset, evidence, today=None):
    today = today or datetime.now(timezone.utc).date()
    if not evidence:
        return ['permission_evidence_missing']
    errors = []
    if evidence.get('asset_url') != asset['asset_url'] or evidence.get('model_key') != asset.get('model_key'):
        errors.append('exact_asset_or_model_mismatch')
    for field in ('source_url', 'evidence_url', 'license_url'):
        if not https_url(evidence.get(field)):
            errors.append('invalid_' + field)
    if evidence.get('status') != 'documented' or not str(evidence.get('evidence_quote', '')).strip():
        errors.append('permission_not_documented')
    if evidence.get('license_id') not in LICENSES or evidence.get('license_url') != LICENSES.get(evidence.get('license_id')):
        errors.append('license_requires_specific_review')
    for field in ('author', 'credit', 'changes'):
        if not str(evidence.get(field, '')).strip():
            errors.append('missing_' + field)
    try:
        if date.fromisoformat(evidence['reviewed_at']) > today:
            errors.append('future_review')
        if evidence.get('valid_until') and date.fromisoformat(evidence['valid_until']) < today:
            errors.append('permission_expired')
    except (ValueError, KeyError, TypeError):
        errors.append('invalid_review_date')
    return errors


def inventory(root=ROOT):
    root = Path(root)
    source = (root / 'src/main.jsx').read_text(encoding='utf-8')
    match = re.search(r'const officialModelImages = \{(.*?)\n\};', source, re.S)
    if not match:
        raise ValueError('image_inventory_layout_changed')
    lookup = ast.literal_eval('{' + match.group(1) + '}')
    assets = {}
    for row in public_records(root / 'public/data/public_ev_variants.json'):
        key = normalize_image_key(row['brand']) + '|' + normalize_image_key(row['model'])
        url = row.get('image_url') or lookup.get(key)
        if url:
            assets[(key, url)] = {'model_key': key, 'asset_url': url, 'surface': 'vehicle'}
    for css in sorted((root / 'src').glob('*.css')):
        for url in re.findall(r'url\([\"\']?(https://[^\"\')]+)', css.read_text(encoding='utf-8')):
            assets[(str(css.relative_to(root)), url)] = {'model_key': None, 'asset_url': url, 'surface': str(css.relative_to(root))}
    return list(assets.values())


def build_report(assets, registry, today=None):
    if registry.get('schema_version') != 1 or not isinstance(registry.get('assets'), list):
        raise ValueError('invalid_rights_registry')
    entries = {}
    for entry in registry['assets']:
        key = (entry.get('model_key'), entry.get('asset_url'))
        if key in entries:
            raise ValueError('duplicate_rights_evidence')
        entries[key] = entry
    checked = []
    for asset in assets:
        errors = rights_errors(asset, entries.get((asset.get('model_key'), asset['asset_url'])), today)
        checked.append({**asset, 'documented': not errors, 'errors': errors})
    return {'all_documented': bool(checked) and all(row['documented'] for row in checked),
            'assets': len(checked), 'documented': sum(row['documented'] for row in checked),
            'pending': sum(not row['documented'] for row in checked), 'checks': checked,
            'scope': 'Recorded evidence and exact asset binding, not a legal opinion or implicit manufacturer permission',
            'network_calls': 0, 'public_data_changed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build_report(inventory(), json.loads((ROOT / 'src/image-rights.json').read_text(encoding='utf-8')))
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.check and not report['all_documented']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
