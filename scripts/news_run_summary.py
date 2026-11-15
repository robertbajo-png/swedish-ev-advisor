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
    skipped = result.get('skipped', [])
    skipped = skipped if isinstance(skipped, list) else []
    held = result.get('held_candidates')
    output = {'status': status, 'published': 1 if result.get('published') == 1 else 0,
              'held_candidates': held if type(held) is int and held >= len(skipped) else len(skipped),
              'review_performed': result.get('review_performed') is True}
    for field in ('cost_micro_usd', 'word_count'):
        value = result.get(field)
        if type(value) is int and value >= 0: output[field] = value
    if status == 'failed':
        error = result.get('error')
        if error == 'ValueError:news_incomplete_ai_response':
            output['failure_kind'] = 'incomplete_provider_response'
        elif isinstance(error, str) and error.startswith('NewsBudgetBlocked:'):
            output['failure_kind'] = 'budget_or_accounting_failure'
        elif isinstance(error, str) and error.startswith('NewsProviderError:'):
            output['failure_kind'] = 'provider_failure'
        else:
            output['failure_kind'] = 'worker_failure'
    reasons, gaps = Counter(), {}
    for candidate in skipped:
        if not isinstance(candidate, dict):
            continue
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


def summarize_result_file(path, *, worker_failed=False):
    # Do not turn an upstream worker exception into a second, misleading JSON failure.
    fallback = {'status': 'worker_not_completed', 'published': 0, 'review_performed': False}
    try:
        raw = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        issue = 'missing'
    except (OSError, UnicodeError):
        issue = 'unreadable'
    else:
        if not raw.strip():
            issue = 'empty'
        else:
            try:
                result = json.loads(raw)
            except ValueError:
                result = None
            if isinstance(result, dict) and isinstance(result.get('status'), str):
                return summarize(result)
            issue = 'invalid'
    # The original failure remains visible in its workflow step; never copy raw output.
    if issue != 'missing' or worker_failed:
        fallback['result_file_issue'] = issue
    if worker_failed:
        fallback['failure_kind'] = 'upstream_worker_failure'
    return fallback


if __name__ == '__main__':
    report = summarize_result_file(Path('publisher-run-result.json'),
                                   worker_failed=os.environ.get('NEWS_PUBLISHER_WORKER_FAILED') == 'true')
    Path('news-operation-summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as handle:
            handle.write('## News operation\n\n```json\n' + json.dumps(report, indent=2) + '\n```\n')
    print(json.dumps(report))
