"""One template per verified publisher; no per-publisher paid admission tests."""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REGISTERED_PUBLISHERS = {s['id']: s for s in json.loads(
    (ROOT / 'data/news/sources.json').read_text(encoding='utf-8')) if s['kind'] == 'publisher'}


def publisher_templates(sources=None, templates=None):
    sources = sources if sources is not None else json.loads((ROOT / 'data/news/sources.json').read_text(encoding='utf-8'))
    templates = templates if templates is not None else json.loads((ROOT / 'data/news/publisher_templates.json').read_text(encoding='utf-8'))
    registered = {s['id']: s for s in sources if s['kind'] == 'publisher'}
    result = {}
    allowed = {'id', 'publisher_group', 'ownership_evidence_url', 'can_lead', 'body_class', 'body_attribute', 'article_path_pattern', 'metadata_triage_path_pattern', 'excluded_body_classes'}
    for supplied in templates:
        if set(supplied) - allowed:
            raise ValueError('publisher_template_cannot_override_registered_identity')
        row = {'can_lead': True, 'body_class': 'entry-content',
               'article_path_pattern': r'/(?!feed(?:/|$)|(?:about|privacy|contact)(?:[-/]|$))[^?#]+', **supplied}
        source = registered.get(row.get('id'))
        if not source or row['id'] in result:
            raise ValueError('publisher_template_identity_unknown_or_duplicate')
        if source.get('editorial_use') == 'discovery_only' or source.get('superseded_by'):
            raise ValueError('publisher_template_editorial_use_not_approved')
        website, proof = urlsplit(source['website']), urlsplit(row.get('ownership_evidence_url', ''))
        if (website.scheme != 'https' or proof.scheme != 'https' or proof.hostname != website.hostname
                or proof.username or proof.password or proof.port not in (None, 443)
                or not proof.path or proof.path == '/' or not re.fullmatch(r'[a-z0-9][a-z0-9_-]+', row.get('publisher_group', ''))
                or type(row.get('can_lead')) is not bool
                or not re.fullmatch(r'[a-z0-9_-]+', row.get('body_class', ''))):
            raise ValueError('publisher_template_ownership_or_layout_invalid')
        if source.get('publisher_group') and source['publisher_group'] != row['publisher_group']:
            raise ValueError('publisher_template_known_parent_group_conflict')
        if row.get('body_attribute') is not None and not re.fullmatch(r'data-[a-z][a-z0-9-]*', row['body_attribute']):
            raise ValueError('publisher_template_body_attribute_invalid')
        excluded = row.get('excluded_body_classes', [])
        if (not isinstance(excluded, list) or len(excluded) > 12 or
                any(not isinstance(v, str) or not re.fullmatch(r'[a-z0-9_-]{1,80}', v) for v in excluded) or
                row['body_class'] in excluded or len(set(excluded)) != len(excluded)):
            raise ValueError('publisher_template_excluded_classes_invalid')
        re.compile(row['article_path_pattern'])
        if row.get('metadata_triage_path_pattern') is not None:
            if not isinstance(row['metadata_triage_path_pattern'], str) or not row['metadata_triage_path_pattern'].startswith('/'):
                raise ValueError('publisher_template_triage_path_invalid')
            re.compile(row['metadata_triage_path_pattern'])
        result[row['id']] = {**source, **row}
    return result


PUBLISHERS = publisher_templates()
LEAD_SOURCES = frozenset(key for key, source in PUBLISHERS.items() if source['can_lead'])
