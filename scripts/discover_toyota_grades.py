"""Read-only discovery of exact Toyota grade defaults, not publication evidence."""
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID

from refresh_verified_variants import save
from supabase_client import SupabaseRestClient
from toyota_price_intake import HTML_URL, ROOT, collect_configuration, extract_config
from variant_refresh import RefreshError

REPORT = ROOT / 'data/review/toyota_grade_discovery.json'


def identity(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise RefreshError('invalid_manufacturer_identity') from None
    return value


def discover(source, data, existing, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        age = (now - datetime.fromisoformat(source['fetched_at'])).total_seconds()
    except (KeyError, ValueError, TypeError):
        raise RefreshError('fresh_official_configuration_required') from None
    if (source.get('url') != HTML_URL or source.get('source_authority') != 'manufacturer'
            or source.get('source_validation') != 'reachable_official_model_source'
            or not re.fullmatch(r'[0-9a-f]{64}', source.get('content_hash', '')) or not -60 <= age <= 900):
        raise RefreshError('fresh_official_configuration_required')
    # This also rejects wrong markets/models and unsupported selected-car facts.
    extracted = extract_config(data, source)
    model_id = identity(data['car']['model']['id'])
    selected_grade = data['car']['grade']
    selected_grade_id = identity(selected_grade.get('id'))
    grades = data.get('grades', {}).get('items')
    if not isinstance(grades, list) or not 1 <= len(grades) <= 12:
        raise RefreshError('grade_registry_missing_or_excessive')
    by_id = {}
    for row in existing:
        manufacturer_id = row.get('manufacturer_variant_id')
        if manufacturer_id:
            identity(manufacturer_id)
            if manufacturer_id in by_id:
                raise RefreshError('duplicate_canonical_identity')
            by_id[manufacturer_id] = row
    jobs, grade_ids, default_ids, names = [], set(), set(), set()
    selected_seen = False
    for index, grade in enumerate(grades):
        grade_id, default_id = identity(grade.get('id')), identity(grade.get('defaultCarId'))
        name = grade.get('name')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9 +\-]{1,50}', name):
            raise RefreshError('unsupported_grade_identity')
        if grade_id in grade_ids or default_id in default_ids or name.casefold() in names:
            raise RefreshError('duplicate_grade_or_default_identity')
        grade_ids.add(grade_id); default_ids.add(default_id); names.add(name.casefold())
        selected = grade_id == selected_grade_id
        if selected:
            if name != selected_grade.get('name') or default_id != data['car']['id']:
                raise RefreshError('selected_grade_default_mismatch')
            selected_seen = True
        current = by_id.get(default_id)
        if current and (current.get('manufacturer_model_id') != model_id
                or current.get('manufacturer_config_version') != data['car']['model']['configVersion']):
            status = 'identity_conflict'
        elif current and current.get('validation_status') in ('published', 'published_reviewed'):
            status = 'identity_already_public'
        elif selected:
            status = 'exact_configuration_requires_publication_checks'
        else:
            status = 'needs_configuration_source'
        proof = {key: {'source_pointer': f'/grades/items/{index}/{key}', 'raw_value': grade[key],
                       'quote': json.dumps(grade[key], ensure_ascii=False)} for key in ('id', 'name', 'defaultCarId')}
        jobs.append({'job_id': hashlib.sha256(f'{model_id}|{grade_id}|{default_id}'.encode()).hexdigest(),
                     'grade': name, 'manufacturer_grade_id': grade_id, 'default_manufacturer_variant_id': default_id,
                     'manufacturer_model_id': model_id, 'manufacturer_config_version': data['car']['model']['configVersion'],
                     'status': status, 'discovered_from': HTML_URL, 'discovery_source_hash': source['content_hash'],
                     'discovered_at': source['fetched_at'], 'field_evidence': proof,
                     'configuration_source_url': HTML_URL if selected else None,
                     'selected_configuration_available': selected, 'publication_allowed': False})
    if not selected_seen:
        raise RefreshError('selected_grade_not_in_registry')
    legacy = [{'canonical_variant_id': row['id'], 'variant_name': row['variant_name'], 'status': 'needs_mapping',
               'reason': 'generation_identity_not_proven', 'auto_update_allowed': False}
              for row in existing if not row.get('manufacturer_variant_id')]
    return {'checked_at': source['fetched_at'], 'source_url': HTML_URL, 'source_hash': source['content_hash'],
            'scope': 'grade_defaults_not_complete_variant_coverage', 'grades': jobs,
            'grade_count': len(jobs), 'selected_variant_count': len(extracted),
            'unresolved_grade_count': sum(not job['selected_configuration_available'] for job in jobs),
            'legacy_mapping': legacy, 'remote_writes': False, 'canonical_writes': False,
            'published': 0, 'openai_calls': 0}


def run(client, source, data):
    models = client.select('canonical_models', 'id,brand,model,validation_status', {'brand': 'eq.Toyota', 'model': 'eq.bZ4X'})
    if len(models) != 1 or models[0]['validation_status'] == 'rejected':
        raise RefreshError('one_existing_canonical_model_required')
    rows = client.select('canonical_model_variants',
        'id,variant_name,manufacturer_variant_id,manufacturer_model_id,manufacturer_config_version,validation_status',
        {'canonical_model_id': 'eq.' + models[0]['id']})
    return discover(source, data, rows)


def main():
    source, data = collect_configuration()
    report = run(SupabaseRestClient(), source, data)
    save(REPORT, report)
    print(json.dumps({key: value for key, value in report.items() if key not in ('grades', 'legacy_mapping')}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        reason = str(error) if isinstance(error, RefreshError) else 'source_or_storage_error'
        previous = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {}
        previous['last_attempt'] = {'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'quarantined', 'reason': reason}
        save(REPORT, previous)
        print('Toyota grade discovery stopped safely: ' + reason)
        raise SystemExit(1)
