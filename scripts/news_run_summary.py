"""Safe operational outcome, without prompts, source bodies or credentials."""
import json
import os
from pathlib import Path
import re


def summarize(result):
    status = result.get('status', 'unknown')
    if not isinstance(status, str) or not re.fullmatch(r'[a-z_]{1,80}', status): status = 'unknown'
    output = {'status': status, 'published': 1 if result.get('published') == 1 else 0,
              'held_candidates': len(result.get('skipped', [])),
              'review_performed': result.get('review_performed') is True}
    for field in ('cost_micro_usd', 'word_count'):
        value = result.get(field)
        if type(value) is int and value >= 0: output[field] = value
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
