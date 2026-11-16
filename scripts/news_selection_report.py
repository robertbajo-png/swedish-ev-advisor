"""Bounded, source-text-free diagnostics for selection before paid editorial work."""
from collections import Counter
import re

from news_content_report import safe_reason
from news_publisher_selection import subject_brands

STAGES = {'selection', 'collection', 'evidence'}
FETCH_REASONS = {'publisher_no_primary_or_independent_pair', 'robots_disallowed', 'tdm_reserved',
                 'publisher_content_not_complete', 'publisher_missing_publication_date',
                 'primary_identity_mismatch', 'publisher_fetch_failed'}


def held_candidate(item, stage, reasons, trace=()):
    values = reasons if isinstance(reasons, list) else [reasons]
    return {'source_id': item.get('source_id'), 'stage': stage if stage in STAGES else 'selection',
            'subjects': sorted(subject_brands(item.get('payload', {}).get('title', ''))),
            'reason': sorted({safe_reason(value) for value in values}) or ['unclassified'],
            'discovery_trace': safe_trace(trace)}


def safe_trace(trace):
    if not isinstance(trace, (list, tuple)):
        return []
    return [{key: safe_reason(step[key]) for key in ('stage', 'status') if key in step}
            for step in trace[:24] if isinstance(step, dict)]


def collection_failure(item, error):
    errors = (error, getattr(error, 'reason', None), getattr(error, '__cause__', None))
    timeout = any(isinstance(value, TimeoutError) or type(value).__name__ in (
        'ReadTimeout', 'ConnectTimeout', 'TimeoutException') for value in errors)
    reason = 'source_fetch_timeout' if timeout else 'source_fetch_failed'
    known = safe_reason(str(error))
    return held_candidate(item, 'collection', [reason] + ([known] if known in FETCH_REASONS else []),
                          getattr(error, 'discovery_trace', ()))


def selection_report(result, held, *, checked=0, attempted=0):
    reasons, stages = Counter(), Counter()
    details = []
    for entry in held:
        stage = entry.get('stage') if entry.get('stage') in STAGES else 'selection'
        stages[stage] += 1
        raw = entry.get('reason', entry.get('errors', []))
        codes = sorted({safe_reason(v) for v in (raw if isinstance(raw, list) else [raw])}) or ['unclassified']
        reasons.update(codes)
        safe = {'stage': stage, 'reason': codes}
        identity = entry.get('source_id', '')
        if isinstance(identity, str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,60}', identity):
            safe['source_id'] = identity
        # Preserve only known brand labels, never names inferred from error text.
        subjects = entry.get('subjects', [])
        safe['subjects'] = sorted(subject_brands(' '.join(v for v in subjects if isinstance(v, str)))) if isinstance(subjects, list) else []
        safe['discovery_trace'] = safe_trace(entry.get('discovery_trace'))
        if len(details) < 24:
            details.append(safe)
    return {**result, 'held_candidates': len(held), 'held_reasons': dict(reasons),
            'held_stages': dict(stages), 'skipped': details,
            'selection_checked': checked, 'ai_candidates_started': attempted}
