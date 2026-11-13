"""Offline rights inventory, separate from exact-model image identification."""
import argparse
import ast
import json
import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from verify_public_images import normalize_image_key, public_records

ROOT = Path(__file__).resolve().parents[1]
LICENSES = {'CC-BY-4.0': 'https://creativecommons.org/licenses/by/4.0/',
            'CC-BY-SA-4.0': 'https://creativecommons.org/licenses/by-sa/4.0/',
            'CC0-1.0': 'https://creativecommons.org/publicdomain/zero/1.0/'}
POLESTAR_NOTICE = 'Content found in the Polestar media newsroom is intended for editorial use only and may not be used for any advertising or commercial purposes.'
PRESS_PUBLISHERS = json.loads((ROOT / 'src/press-image-publishers.json').read_text(encoding='utf-8'))


def reviewed_media_permission(evidence):
    policy = PRESS_PUBLISHERS.get(evidence.get('publisher_id'))
    if not policy or evidence.get('license_id') != policy['license_id']:
        return False
    source = urlsplit(evidence.get('source_url', ''))
    asset = urlsplit(evidence.get('downloaded_from', ''))
    return bool(evidence.get('model_key') in policy['model_keys']
        and source.scheme + '://' + source.netloc == policy['origin']
        and re.fullmatch(r'/images/[a-z0-9-]+-[0-9]+', source.path)
        and (not policy.get('approved_image_paths') or source.path in policy['approved_image_paths'])
        and not (evidence.get('model_key') == 'skoda|enyaq' and 'coup' in source.path)
        and not source.query and not source.fragment
        and evidence.get('evidence_url') == evidence.get('source_url')
        and evidence.get('license_url') == evidence.get('source_url')
        and evidence.get('evidence_quote') == policy['permission_excerpt'] + ' | ' + policy['condition_excerpt']
        and asset.scheme + '://' + asset.netloc == policy['asset_origin']
        and re.fullmatch(r'/image/upload/fl_attachment/[a-zA-Z0-9_-]+', asset.path)
        and not asset.query and not asset.fragment
        and evidence.get('usage_scope') == 'independent_vehicle_editorial'
        and evidence.get('full_frame') is True
        and all(re.fullmatch('[a-f0-9]{64}', evidence.get(name, '')) for name in ('metadata_sha256', 'source_content_sha256')))


def reviewed_press_permission(evidence):
    if evidence.get('license_id') != 'Polestar-editorial':
        return False
    source = urlsplit(evidence.get('source_url', ''))
    downloaded = urlsplit(evidence.get('downloaded_from', ''))
    match = re.fullmatch(r'/gallery/images/([0-9]+)', source.path)
    return bool(evidence.get('model_key') in ('polestar|2', 'polestar|4')
        and source.scheme == 'https' and source.netloc == 'media.polestar.com' and not source.query and not source.fragment
        and match and downloaded.scheme == 'https' and downloaded.netloc == source.netloc
        and re.fullmatch(r'/assets/images/(?:original|small)/' + match[1] + r'-[a-zA-Z0-9._-]+\.jpe?g', downloaded.path)
        and not downloaded.query and not downloaded.fragment
        and evidence.get('evidence_url') == 'https://media.polestar.com/copyright'
        and evidence.get('license_url') == evidence.get('evidence_url')
        and evidence.get('evidence_quote') == POLESTAR_NOTICE
        and evidence.get('usage_scope') == 'independent_vehicle_editorial'
        and evidence.get('prohibited_uses') == ['advertising', 'commercial_promotion', 'endorsement']
        and re.fullmatch('[a-f0-9]{64}', evidence.get('metadata_sha256', '')))


def reviewed_toyota_permission(evidence):
    from collect_toyota_press_photo import SOURCE, ASSET, NOTICE
    return bool(evidence.get('model_key') == 'toyota|bz4x'
        and evidence.get('license_id') == 'Toyota-editorial'
        and all(evidence.get(field) == SOURCE for field in ('source_url', 'evidence_url', 'license_url'))
        and evidence.get('downloaded_from') == ASSET and evidence.get('evidence_quote') == NOTICE
        and evidence.get('usage_scope') == 'independent_vehicle_editorial' and evidence.get('full_frame') is True
        and evidence.get('prohibited_uses') == ['advertising', 'commercial_promotion', 'endorsement']
        and all(re.fullmatch('[a-f0-9]{64}', evidence.get(field, '')) for field in ('metadata_sha256', 'source_content_sha256')))


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
    if not (reviewed_press_permission(evidence) or reviewed_media_permission(evidence) or reviewed_toyota_permission(evidence)) and (evidence.get('license_id') not in LICENSES or evidence.get('license_url') != LICENSES.get(evidence.get('license_id'))):
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


def image_lookup(root=ROOT):
    root = Path(root)
    structured = root / 'src/model-images.json'
    if structured.is_file():
        return json.loads(structured.read_text(encoding='utf-8'))
    source = (root / 'src/main.jsx').read_text(encoding='utf-8')
    match = re.search(r'const officialModelImages = \{(.*?)\n\};', source, re.S)
    if not match:
        raise ValueError('image_inventory_layout_changed')
    return ast.literal_eval('{' + match.group(1) + '}')


def inventory(root=ROOT, candidate_registry=False):
    root = Path(root)
    lookup = image_lookup(root)
    assets = {}
    for row in public_records(root / 'public/data/public_ev_variants.json'):
        key = normalize_image_key(row['brand']) + '|' + normalize_image_key(row['model'])
        url = lookup.get(key) if candidate_registry else row.get('image_url') or lookup.get(key)
        if url:
            assets[(key, url)] = {'model_key': key, 'asset_url': url, 'surface': 'vehicle'}
    for css in sorted((root / 'src').glob('*.css')):
        for url in re.findall(r'url\([\"\']?((?:https://|/media/vehicles/)[^\"\')]+)', css.read_text(encoding='utf-8')):
            matches = [key for key, value in lookup.items() if value == url]
            model_key = matches[0] if len(matches) == 1 else None
            assets[(str(css.relative_to(root)), url)] = {'model_key': model_key, 'asset_url': url, 'surface': str(css.relative_to(root))}
    return list(assets.values())


def build_report(assets, registry, today=None, root=ROOT):
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
        evidence = entries.get((asset.get('model_key'), asset['asset_url']))
        errors = rights_errors(asset, evidence, today)
        if asset['asset_url'].startswith('/'):
            url = asset['asset_url']
            path = Path(root) / 'public' / url.lstrip('/')
            valid_path = bool(re.fullmatch(r'/media/vehicles/[a-z0-9-]+-[a-f0-9]{12}\.jpg', url))
            if not valid_path or path.is_symlink() or not path.is_file():
                errors.append('local_image_missing_or_unsafe')
            elif not evidence or hashlib.sha256(path.read_bytes()).hexdigest() != evidence.get('content_sha256'):
                errors.append('local_image_hash_mismatch')
        checked.append({**asset, 'documented': not errors, 'errors': errors})
    return {'all_documented': bool(checked) and all(row['documented'] for row in checked),
            'assets': len(checked), 'documented': sum(row['documented'] for row in checked),
            'pending': sum(not row['documented'] for row in checked), 'checks': checked,
            'scope': 'Recorded evidence and exact asset binding, not a legal opinion or implicit manufacturer permission',
            'network_calls': 0, 'public_data_changed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--candidate-registry', action='store_true', help='Audit proposed lookup before a canonical image transaction; not public parity')
    args = parser.parse_args()
    report = build_report(inventory(candidate_registry=args.candidate_registry), json.loads((ROOT / 'src/image-rights.json').read_text(encoding='utf-8')))
    report['candidate_registry_only'] = args.candidate_registry
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.check and not report['all_documented']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
