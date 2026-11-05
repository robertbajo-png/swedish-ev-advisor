"""Safe operational outcome, without prompts, source bodies or credentials."""
import json
import os
from pathlib import Path
import re
from collections import Counter
from news_content_report import safe_reason
from news_publisher_selection import BRAND_PATTERNS


def summarize(result):
    status = result.get('status', 'unknown')
    if not isinstance(status, str) or not re.fullmatch(r'[a-z_]{1,80}', status): status = 'unknown'
    output = {'status': status, 'published': 1 if result.get('published') == 1 else 0,
              'held_candidates': len(result.get('skipped', [])),
              'review_performed': result.get('review_performed') is True}
    for field in ('cost_micro_usd', 'word_count'):
        value = result.get(field)
        if type(value) is int and value >= 0: output[field] = value
    reasons, gaps = Counter(), {}
    for candidate in result.get('skipped', []):
        values = candidate.get('reason', candidate.get('errors', []))
        for value in values if isinstance(values, list) else [values]:
            reasons[safe_reason(value)] += 1
        trace = candidate.get('discovery_trace', [])
        if not isinstance(trace, list): trace = []
        missing = any(isinstance(step, dict) and step.get('status') == 'no_matching_declared_authority' for step in trace)
        original_missing = any(safe_reason(value) == 'publisher_no_primary_or_independent_pair'
                              for value in (values if isinstance(values, list) else [values]))
        if missing or original_missing:
            kind = 'missing_authority' if missing else 'original_not_found'
            subjects = candidate.get('subjects', [])
            subjects = {s for s in subjects if isinstance(s,str) and s in BRAND_PATTERNS} if isinstance(subjects,list) else set()
            counts = gaps.setdefault(kind, Counter())
            for subject in subjects or {'unidentified_subject'}: counts[subject] += 1
    output['held_reasons'] = dict(reasons)
    output['source_gaps'] = {kind: dict(counts) for kind, counts in gaps.items()}
    return output


if __name__ == '__main__':
    path = Path('publisher-run-result.json')
    report = summarize(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else {
        'status': 'worker_not_completed', 'published': 0, 'review_performed': False}
    Path('news-operation-summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as handle:
            handle.write('## News operation\n\n```json\n' + json.dumps(report, indent=2) + '\n```\n')
    print(json.dumps(report))
