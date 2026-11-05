"""Analyze an owner's Search Console Pages CSV offline; no Google API or invented traffic."""
import argparse
import csv
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlsplit

NAMES = {'page': ('Top pages', 'Populäraste sidorna', 'Sidor', 'Page', 'Sida'),
         'clicks': ('Clicks', 'Klick'), 'impressions': ('Impressions', 'Exponeringar'),
         'ctr': ('CTR',), 'position': ('Position', 'Genomsnittlig position')}


def number(value):
    text = str(value).strip().replace('\u00a0', '').replace('\u202f', '').replace(' ', '').replace('%', '')
    if ',' in text and '.' in text:
        raise ValueError('Ambiguous number format')
    value = float(text.replace(',', '.'))
    if not 0 <= value < float('inf'):
        raise ValueError('Invalid negative or nonfinite metric')
    return value


def analyze(file, start, end):
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError('Invalid reporting period')
    with Path(file).open(encoding='utf-8-sig', newline='') as handle:
        sample = handle.read(8192)
        handle.seek(0)
        delimiter = ';' if sample.splitlines()[0].count(';') > sample.splitlines()[0].count(',') else ','
        reader = csv.DictReader(handle, delimiter=delimiter)
        keys = {key: next((name for name in names if name in (reader.fieldnames or [])), None) for key, names in NAMES.items()}
        if not all(keys.values()):
            raise ValueError('Expected a Search Console Pages export, not queries or visitor analytics')
        rows = []
        seen = set()
        for row in reader:
            page = row[keys['page']].strip()
            url = urlsplit(page)
            if url.scheme != 'https' or url.hostname not in {'elbilsagenten.se', 'www.elbilsagenten.se'} or url.username or url.password or page in seen:
                raise ValueError('Unexpected or duplicate page URL')
            seen.add(page)
            clicks, impressions = (number(row[keys[key]]) for key in ('clicks', 'impressions'))
            ctr, position = (number(row[keys[key]]) for key in ('ctr', 'position'))
            if not clicks.is_integer() or not impressions.is_integer() or clicks > impressions or ctr > 100:
                raise ValueError('Invalid Search Console metrics')
            # Recompute CTR to avoid decimal/percent ambiguity in the exported presentation.
            rows.append({'page': page, 'clicks': int(clicks), 'impressions': int(impressions),
                         'ctr': clicks / impressions if impressions else 0, 'average_position': position})
    opportunities = [row for row in rows if row['impressions'] >= 50 and row['ctr'] < .02 and 3 <= row['average_position'] <= 15]
    return {'period_start': start, 'period_end': end, 'source': 'owner_search_console_pages_csv',
            'has_search_data': any(row['impressions'] for row in rows), 'pages': rows,
            'snippet_review_candidates': sorted(opportunities, key=lambda row: row['impressions'], reverse=True)[:10],
            'note': 'Page-level search metrics are not unique visits, a site-wide total, or a traffic forecast.',
            'google_api_calls': 0, 'paid_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    private = (Path(__file__).resolve().parents[1] / 'data/local').resolve()
    if private not in destination.parents:
        raise ValueError('Search metrics must remain under ignored data/local')
    report = analyze(args.input, args.start, args.end)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report_saved': True, 'pages': len(report['pages']), 'has_search_data': report['has_search_data'], 'google_api_calls': 0}))


if __name__ == '__main__':
    main()
