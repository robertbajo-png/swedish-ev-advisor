"""Prepare dated link briefs from recent public articles, never post or call AI."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from html import unescape
from pathlib import Path
from news_rss import ROOT, publication_time, render_feed
import xml.etree.ElementTree as ET


def share_briefs(rows, *, now=None, days=7):
    now = now or datetime.now(timezone.utc)
    if type(days) is not int or not 1 <= days <= 31:
        raise ValueError('share_days_must_be_1_to_31')
    feed = ET.fromstring(render_feed(rows, now=now))
    minimum = now - timedelta(days=days)
    dates = {r.get('slug'): publication_time(r.get('published_at')) for r in rows if isinstance(r, dict)}
    briefs = []
    for item in feed.findall('channel/item'):
        link = item.findtext('link')
        date = dates.get(link.rstrip('/').rsplit('/', 1)[-1])
        if date and minimum <= date <= now:
            briefs.append({'title': item.findtext('title'), 'intro': unescape(item.findtext('description')),
                           'published_at': date.isoformat(), 'url': link})
        if len(briefs) == 3:
            break
    return {'briefs': briefs, 'external_posts': 0, 'paid_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'public/data/news_articles.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = share_briefs(json.loads(args.snapshot.read_text(encoding='utf-8')).get('records', []))
    text = json.dumps(result, ensure_ascii=True, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
