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
TOYOTA_PRESS_IMAGES = json.loads((ROOT / 'src/toyota-press-images.json').read_text(encoding='utf-8'))
ID_BUZZ_PHOTO = json.loads((ROOT / 'src/id-buzz-photo-policy.json').read_text(encoding='utf-8'))
INSTER_PHOTO = json.loads((ROOT / 'src/inster-photo-policy.json').read_text(encoding='utf-8'))
MACAN_PHOTO = json.loads((ROOT / 'src/porsche-macan-photo-policy.json').read_text(encoding='utf-8'))


def reviewed_media_permission(evidence):
    policy = PRESS_PUBLISHERS.get(evidence.get('publisher_id'))
    if not policy or evidence.get('license_id') != policy['license_id']:
        return False
    source = urlsplit(evidence.get('source_url', ''))
    asset = urlsplit(evidence.get('downloaded_from', ''))
    return bool(evidence.get('model_key') in policy['model_keys']
        and source.scheme + '://' + source.netloc == policy['origin']
        and re.fullmatch(re.escape(policy.get('image_path_prefix', '/images/')) + r'[a-z0-9-]+-[0-9]+', source.path)
        and (not policy.get('approved_image_paths') or source.path in policy['approved_image_paths'])
        and not (evidence.get('model_key') == 'skoda|enyaq' and 'coup' in source.path)
        and not source.query and not source.fragment
        and evidence.get('evidence_url') == evidence.get('source_url')
        and evidence.get('license_url') == evidence.get('source_url')
        and evidence.get('evidence_quote') == policy['permission_excerpt'] + ' | ' + policy['condition_excerpt']
        and asset.scheme + '://' + asset.netloc == policy['asset_origin']
        and ('approved_asset_url' not in policy or evidence.get('downloaded_from') == policy['approved_asset_url'])
        and ('approved_source_sha256' not in policy or evidence.get('source_content_sha256') == policy['approved_source_sha256'])
        and (not policy.get('preserve_original_jpeg') or evidence.get('content_sha256') == evidence.get('source_content_sha256'))
        and re.fullmatch(r'/image/upload/fl_attachment/[a-zA-Z0-9_-]+', asset.path)
        and not asset.query and not asset.fragment
        and evidence.get('usage_scope') == 'independent_vehicle_editorial'
        and policy.get('placement') == evidence.get('placement')
        and (not policy.get('placement') or (evidence.get('author') == policy.get('asset_author')
            and evidence.get('credit') == policy.get('asset_credit')))
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
    policy = TOYOTA_PRESS_IMAGES.get(evidence.get('model_key'))
    if not policy:
        return False
    return bool(evidence.get('license_id') == 'Toyota-editorial'
        and all(evidence.get(field) == policy['source_url'] for field in ('source_url', 'evidence_url', 'license_url'))
        and evidence.get('downloaded_from') == policy['asset_url'] and evidence.get('evidence_quote') == policy['permission']
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
    if evidence.get('placement') and evidence.get('placement') != asset.get('surface'):
        errors.append('image_placement_scope_mismatch')
    if evidence.get('asset_url') != asset['asset_url'] or evidence.get('model_key') != asset.get('model_key'):
        errors.append('exact_asset_or_model_mismatch')
    for field in ('source_url', 'evidence_url', 'license_url'):
        if not https_url(evidence.get(field)):
            errors.append('invalid_' + field)
    if evidence.get('status') != 'documented' or not str(evidence.get('evidence_quote', '')).strip():
        errors.append('permission_not_documented')
    exact_buzz_photo = all(evidence.get(key) == value for key, value in ID_BUZZ_PHOTO.items())
    exact_inster_photo = (all(evidence.get(key) == value for key, value in INSTER_PHOTO.items())
                          and 'variant_names' not in evidence)
    exact_macan_photo = (all(evidence.get(key) == value for key, value in MACAN_PHOTO.items())
                         and 'variant_names' not in evidence)
    if evidence.get('model_key') == ID_BUZZ_PHOTO['model_key'] and not exact_buzz_photo:
        errors.append('exact_id_buzz_photo_required')
    if evidence.get('model_key') == INSTER_PHOTO['model_key'] and not exact_inster_photo:
        errors.append('exact_inster_photo_required')
    if evidence.get('model_key') == MACAN_PHOTO['model_key'] and not exact_macan_photo:
        errors.append('exact_macan_electric_photo_required')
    if not (exact_buzz_photo or exact_inster_photo or exact_macan_photo or reviewed_press_permission(evidence) or reviewed_media_permission(evidence) or reviewed_toyota_permission(evidence)) and (evidence.get('license_id') not in LICENSES or evidence.get('license_url') != LICENSES.get(evidence.get('license_id'))):
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
            group = assets.setdefault((key, url), {'model_key': key, 'asset_url': url, 'surface': 'vehicle',
                                                  'variant_names': [], 'image_source_urls': []})
            group['variant_names'].append(row.get('variant_name'))
            if url == row.get('image_url'):
                group['image_source_urls'].append(row.get('image_source_url'))
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
        if evidence and 'variant_names' in evidence:
            declared, actual = evidence['variant_names'], asset.get('variant_names')
            photo_sources = asset.get('image_source_urls', [])
            if (not isinstance(declared, list) or not declared or
                    any(not isinstance(name, str) or not name.strip() or name.strip() != name for name in declared) or
                    len(declared) != len(set(declared)) or not actual or
                    any(name not in declared for name in actual) or len(photo_sources) != len(actual) or
                    any(url != evidence.get('source_url') for url in photo_sources)):
                errors.append('missing_or_incorrect_variant_image_scope')
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


def validate_home_publisher_web(row, policy, proof, evidence_sha, content):
    """Pin the exact publisher's unchanged web bytes, never a locally encoded derivative."""
    display = row.get('publisher_display')
    expected = policy.get('publisher_web_display')
    source = next((item for item in proof['records'] if item['model_key'] == row['model_key']), None)
    selected = [v for v in source['variants'] if v.get('selected')] if source else []
    fields = ('source_url','width','height','sha256','bytes')
    if (not display or not expected or len(selected) != 1
            or display.get('evidence_sha256') != evidence_sha
            or any(display.get(k) != expected[k] or display.get(k) != selected[0][k] for k in fields)
            or display.get('url') != '/media/responsive/' + Path(row['asset_url']).stem + '-1782.webp'
            or display['width'] != 1782 or abs(display['height'] - round(1782 * row['height'] / row['width'])) > 1
            or selected[0]['file'] != Path(display['url']).name
            or not selected[0]['full_frame_comparison_passed']
            or not selected[0]['max_quadrant_mean_delta'] < 2
            or not selected[0]['max_edge_band_mean_delta'] < 3
            or source['original_sha256'] != row['source_content_sha256']
            or source['original_dimensions'] != [row['width'], row['height']]
            or source['page_sha256'] != row['metadata_sha256']
            or source['publisher_id'] != row['publisher_id']
            or source['source_url'] != row['source_url']
            or source['author'] != row['author'] or source['credit'] != row['credit']
            or proof.get('local_reencoding') is not False
            or content[8:12] != b'WEBP' or len(content) != display['bytes']
            or hashlib.sha256(content).hexdigest() != display['sha256']):
        raise ValueError('home_featured_publisher_web_mismatch')
    return {'model_key': row['model_key'], **display}


def home_featured_report(root=ROOT, today=None):
    """Separate editorial homepage assets: never add to the canonical model lookup."""
    root = Path(root)
    path = root / 'src/home-featured-photos.json'
    if not path.is_file():
        return None
    registry = json.loads(path.read_text(encoding='utf-8'))
    source_manifest = (root / 'data/review/home-featured-photo-source-candidates.json').read_bytes()
    source_manifest_sha = hashlib.sha256(source_manifest).hexdigest()
    sources = {row['model_key']: row for row in json.loads(source_manifest)}
    canonical = image_lookup(root)
    assets = []
    web_checks = []
    web_proof_file = root / 'data/review/home-featured-publisher-web-evidence.json'
    web_proof_raw = web_proof_file.read_bytes()
    web_sha = hashlib.sha256(web_proof_raw).hexdigest()
    web_proof = json.loads(web_proof_raw)
    for row in registry['assets']:
        policy = PRESS_PUBLISHERS.get(row.get('publisher_id'), {})
        key = row.get('model_key')
        source = sources.get(key, {})
        if (policy.get('placement') != 'home_featured'
                or row.get('placement') != 'home_featured'
                or row.get('replaces_only_home_image') != policy.get('replaces_only_home_image')
                or canonical.get(key) != row.get('replaces_only_home_image')
                or row.get('asset_url') in canonical.values()
                or row.get('title') is None
                or not re.fullmatch(policy.get('model_title_pattern', r'(?!)'), row['title'])
                or row.get('source_manifest_sha256') != source_manifest_sha
                or row.get('downloaded_from') != source.get('asset_url')
                or any(row.get(field) != source.get(field) for field in (
                    'source_url','release_source_url','release_metadata_sha256','evidence_url','license_url',
                    'license_id','evidence_quote','publisher_id','author','credit','original_url','content_sha256',
                    'source_content_sha256','metadata_sha256','width','height','full_frame','usage_scope','photographer_evidence',
                    'replaces_only_home_image','title'))
                or row.get('model_image_notice') != 'Pressbild. Utrustning kan skilja mellan versioner.'
                or row.get('prohibited_uses') != ['advertising','commercial_promotion','endorsement']):
            raise ValueError('home_featured_exact_photo_scope_mismatch')
        display_url = (row.get('publisher_display') or {}).get('url','')
        if not re.fullmatch(r'/media/responsive/[a-z0-9-]+-[a-f0-9]{12}-1782[.]webp', display_url):
            raise ValueError('home_featured_publisher_web_mismatch')
        display_path = root / 'public' / display_url.lstrip('/')
        if display_path.is_symlink() or not display_path.is_file():
            raise ValueError('home_featured_publisher_web_mismatch')
        web_checks.append(validate_home_publisher_web(row, policy, web_proof, web_sha, display_path.read_bytes()))
        assets.append({'model_key': key, 'asset_url': row['asset_url'], 'surface': 'home_featured'})
    if sorted(row['model_key'] for row in assets) != ['bmw|i4', 'ford|explorer']:
        raise ValueError('home_featured_exact_pair_required')
    report = build_report(assets, registry, today, root)
    report['publisher_web'] = web_checks
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--candidate-registry', action='store_true', help='Audit proposed lookup before a canonical image transaction; not public parity')
    args = parser.parse_args()
    report = build_report(inventory(candidate_registry=args.candidate_registry), json.loads((ROOT / 'src/image-rights.json').read_text(encoding='utf-8')))
    report['candidate_registry_only'] = args.candidate_registry
    featured = home_featured_report()
    if featured is not None:
        report['home_featured'] = featured
        report['checks'].extend(featured['checks'])
        report['assets'] += featured['assets']
        report['documented'] += featured['documented']
        report['pending'] += featured['pending']
        report['all_documented'] = report['all_documented'] and featured['all_documented']
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.check and not report['all_documented']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
