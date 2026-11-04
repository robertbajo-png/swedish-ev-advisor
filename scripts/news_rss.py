"""Deterministic RSS from the published snapshot; no collection, AI or database writes."""
import json
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ATOM = 'http://www.w3.org/2005/Atom'
ET.register_namespace('atom', ATOM)


def publication_time(value):
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.astimezone(timezone.utc) if date.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def render_feed(rows, site='https://elbilsagenten.se', now=None):
    site = site.rstrip('/')
    url = urlsplit(site)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.port not in (None, 443) or url.path or url.query or url.fragment):
        raise ValueError('rss_requires_https_site_origin')
    now = now or datetime.now(timezone.utc)
    eligible = []
    for row in rows:
        if not isinstance(row, dict) or row.get('status', 'published') != 'published':
            continue
        date = publication_time(row.get('published_at'))
        if (not date or date > now or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', str(row.get('slug', '')))
                or not all(isinstance(row.get(k), str) and row[k].strip()
                           and not re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', row[k])
                           for k in ('title', 'intro'))):
            continue
        eligible.append((date, row))
    eligible.sort(key=lambda pair: (pair[0], pair[1]['slug']), reverse=True)
    root = ET.Element('rss', version='2.0')
    channel = ET.SubElement(root, 'channel')
    for key, value in (('title', 'Elbilsagenten \u2013 elbilsnyheter'), ('link', site + '/nyheter/'),
                       ('description', 'Internationella elbilsnyheter p\u00e5 svenska: nya modeller, batterier och teknik.'),
                       ('language', 'sv-SE')):
        ET.SubElement(channel, key).text = value
    ET.SubElement(channel, '{' + ATOM + '}link', href=site + '/nyheter/rss.xml', rel='self', type='application/rss+xml')
    if eligible:
        ET.SubElement(channel, 'lastBuildDate').text = format_datetime(eligible[0][0], usegmt=True)
    seen = set()
    for date, row in eligible:
        if row['slug'] in seen:
            continue
        seen.add(row['slug'])
        if len(seen) > 50:
            break
        item = ET.SubElement(channel, 'item')
        link = site + '/nyheter/' + row['slug'] + '/'
        for key, value in (('title', row['title']), ('link', link), ('description', escape(row['intro'])),
                           ('pubDate', format_datetime(date, usegmt=True))):
            ET.SubElement(item, key).text = value
        ET.SubElement(item, 'guid', isPermaLink='true').text = link
    return ET.tostring(root, encoding='utf-8', xml_declaration=True).decode() + '\n'


def write_feed(snapshot=None, output=None, site='https://elbilsagenten.se'):
    snapshot = Path(snapshot or ROOT / 'public/data/news_articles.json')
    rows = json.loads(snapshot.read_text(encoding='utf-8')).get('records', []) if snapshot.exists() else []
    target = Path(output or ROOT / 'public/nyheter/rss.xml')
    text = render_feed(rows, site)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    return {'rss_items': len(ET.fromstring(text).findall('channel/item')), 'output': str(target)}
