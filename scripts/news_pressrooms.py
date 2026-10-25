"""Bounded discovery from explicitly configured official pressroom indexes."""
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from news_http import PageText, canonical_url, iso_date, require_recent_publication


class PressDocument(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.date_parts = []
        self.body_parts = []
        self.stack = []
        self.jsonld = []
        self.json_parts = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            self.meta[a.get('property') or a.get('name')] = a.get('content', '')
        if tag == 'time' and a.get('datetime'):
            self.meta.setdefault('article:published_time', a['datetime'])
        if tag == 'script' and a.get('type') == 'application/ld+json':
            self.json_parts = []
        if tag not in {'meta', 'link', 'br', 'hr', 'img', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track'}:
            classes = set(a.get('class', '').split())
            body = (a.get('id') == 'article-text' or {'article-page', 'pressrelease'} <= classes
                    or {'cntnt', 'block-container'} <= classes)
            dated = 'date' in classes or 'pressrelease-date' in classes
            self.stack.append((tag, body, dated))

    def handle_endtag(self, tag):
        if tag == 'script' and self.json_parts is not None:
            try:
                self.jsonld.append(json.loads(''.join(self.json_parts)))
            except ValueError:
                pass
            self.json_parts = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, text):
        if self.json_parts is not None:
            self.json_parts.append(text)
        if any(tag in {'script', 'style', 'nav', 'footer', 'header'} for tag, _, _ in self.stack):
            return
        if any(body for _, body, _ in self.stack):
            self.body_parts.append(text)
        if any(date for _, _, date in self.stack):
            self.date_parts.append(text)


def document(html):
    parser = PressDocument()
    parser.feed(html)
    dates = [parser.meta.get('article:published_time'), parser.meta.get('datePublished')]
    def walk(node):
        if isinstance(node, dict):
            kind = node.get('@type', [])
            kinds = [kind] if isinstance(kind, str) else kind
            if any(k in {'NewsArticle', 'Article', 'PressRelease'} for k in kinds):
                dates.append(node.get('datePublished'))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    for node in parser.jsonld:
        walk(node)
    published = next((iso_date(value) for value in dates if value and iso_date(value)), None)
    if not published:
        # BMW exposes a release-specific date span, not JSON-LD. Never use the fetch date.
        for value in parser.date_parts:
            match = re.fullmatch(r'\w{3} (\w{3}) (\d{1,2}) (\d{2}:\d{2}:\d{2}) (CEST|CET) (\d{4})', value.strip())
            if match:
                month, day, clock, zone, year = match.groups()
                dt = datetime.strptime(f'{month} {day} {clock} {year}', '%b %d %H:%M:%S %Y')
                published = dt.replace(tzinfo=timezone(timedelta(hours=2 if zone == 'CEST' else 1))).astimezone(timezone.utc).isoformat()
                break
            swedish = re.fullmatch(r'(\d{1,2}) (jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec) (\d{4})\s*\|\s*Pressmeddelande', value.strip())
            if swedish:
                day, month, year = swedish.groups()
                months = 'jan feb mar apr maj jun jul aug sep okt nov dec'.split()
                try:
                    published = datetime(int(year), months.index(month)+1, int(day), tzinfo=timezone.utc).isoformat()
                    break
                except ValueError:
                    continue
    return {'title': parser.meta.get('og:title', '').strip(), 'published_at': published,
            'summary': parser.meta.get('description') or parser.meta.get('og:description') or '',
            'body': re.sub(r'\s+', ' ', ' '.join(parser.body_parts)).strip()}


def discover(index_html, index_url, source, collector, max_items, now=None):
    if source['kind'] != 'primary' or source.get('collection_method') != 'pressroom_index':
        raise ValueError('official_pressroom_required')
    if type(max_items) is not int or max_items < 0:
        raise ValueError('invalid_pressroom_limit')
    limit = min(max_items, 20)
    if not limit:
        return [], []
    parser = PageText()
    parser.feed(index_html)
    urls = []
    for href in parser.links:
        try:
            url = canonical_url(urljoin(index_url, href))
            parsed = urlsplit(url)
            if parsed.hostname != urlsplit(index_url).hostname or parsed.query:
                continue
            if not re.fullmatch(source['article_path_pattern'], parsed.path):
                continue
            if source.get('topic_pattern') and not re.search(source['topic_pattern'], parsed.path, re.I):
                continue
            if url not in urls:
                urls.append(url)
        except ValueError:
            continue
    rows, errors, seen = [], [], set()
    # Rejected pages do not consume the result quota; network work stays bounded.
    for url in urls[:min(20, limit * 3)]:
        try:
            _, _, html, final = collector.fetch(url, source, editorial=True)
            doc = document(html)
            if not doc['title'] or not doc['published_at']:
                raise ValueError('missing_release_title_or_date')
            require_recent_publication(doc['published_at'], now)
            if final in seen:
                continue
            seen.add(final)
            rows.append({'url': final, 'title': doc['title'], 'published_at': doc['published_at'],
                         'summary': doc['summary'], 'content_hash': hashlib.sha256(html.encode()).hexdigest()})
            if len(rows) == limit:
                break
        except Exception as exc:
            errors.append({'url': url, 'reason': type(exc).__name__ + ':' + str(exc)[:180]})
    return sorted(rows, key=lambda row: row['published_at'], reverse=True), errors
