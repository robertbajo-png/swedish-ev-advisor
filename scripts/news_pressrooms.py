"""Bounded discovery from explicitly configured official pressroom indexes."""
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from news_http import PageText, canonical_url, iso_date, require_recent_publication, parse_feed


class PressDocument(HTMLParser):
    def __init__(self, exclude_tables=False, body_region=None, narrative_class=None):
        super().__init__()
        self.exclude_tables = exclude_tables
        self.body_region = body_region
        self.narrative_class = narrative_class
        self.narrative_count = 0
        self.region_count = 0
        self.canonicals = []
        self.meta = {}
        self.date_parts = []
        self.body_parts = []
        self.stack = []
        self.jsonld = []
        self.json_parts = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'link' and 'canonical' in a.get('rel', '').split():
            self.canonicals.append(a.get('href', ''))
        if tag == 'meta':
            self.meta[a.get('property') or a.get('name')] = a.get('content', '')
        if tag == 'time' and a.get('datetime') and not self.body_region:
            self.meta.setdefault('article:published_time', a['datetime'])
        if tag == 'script' and a.get('type') == 'application/ld+json':
            self.json_parts = []
        if tag not in {'meta', 'link', 'br', 'hr', 'img', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track'}:
            classes = set(a.get('class', '').split())
            body = (tag == self.body_region) if self.body_region else (
                a.get('id') == 'article-text' or {'article-page', 'pressrelease'} <= classes
                or {'cntnt', 'block-container'} <= classes or 'article_text' in classes)
            if body:
                self.region_count += 1
            if self.narrative_class:
                body = self.narrative_class in classes and any(t == self.body_region for t, _, _ in self.stack)
                if body:self.narrative_count += 1
            dated = bool({'date', 'pressrelease-date', 'article_date'} & classes)
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
        if any(tag in {'script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript'} for tag, _, _ in self.stack):
            return
        if self.exclude_tables and any(tag == 'table' for tag, _, _ in self.stack):
            return
        if any(body for _, body, _ in self.stack):
            self.body_parts.append(text)
        if any(date for _, _, date in self.stack):
            self.date_parts.append(text)


def document(html, *, exclude_tables=False, url=None, body_region=None, adapter=None, narrative_class=None):
    if adapter is not None:
        if adapter == 'byd_de':
            from news_byd import document as adapted_document
        elif adapter == 'nio':
            from news_nio import document as adapted_document
        else:raise ValueError('unsupported_pressroom_article_adapter')
        return adapted_document(html, url)
    if body_region is not None and body_region not in {'main', 'article'}:
        raise ValueError('unsupported_pressroom_body_region')
    if narrative_class is not None and (not body_region or not re.fullmatch(r'[a-z][a-z0-9_-]{1,79}', narrative_class)):
        raise ValueError('unsupported_pressroom_narrative_class')
    parser = PressDocument(exclude_tables=exclude_tables, body_region=body_region, narrative_class=narrative_class)
    parser.feed(html)
    if body_region:
        if not url or parser.region_count != 1:
            raise ValueError('pressroom_body_missing_or_ambiguous')
        if narrative_class and parser.narrative_count != 1:
            raise ValueError('pressroom_narrative_missing_or_ambiguous')
        if {canonical_url(urljoin(url, value)) for value in parser.canonicals} != {canonical_url(url)}:
            raise ValueError('pressroom_canonical_changed_or_missing')
    dates = [parser.meta.get('article:published_time'), parser.meta.get('datePublished')]
    matched_articles = []
    def walk(node):
        if isinstance(node, dict):
            kind = node.get('@type', [])
            kinds = [kind] if isinstance(kind, str) else kind
            declared = node.get('url') or node.get('mainEntityOfPage') or node.get('@id')
            if isinstance(declared, dict):
                declared = declared.get('@id') or declared.get('url')
            matches = not body_region or bool(isinstance(declared, str)
                and canonical_url(urljoin(url, declared)) == canonical_url(url))
            if matches and any(k in {'NewsArticle', 'Article', 'PressRelease'} for k in kinds):
                dates.append(node.get('datePublished'))
                if node.get('datePublished'):
                    matched_articles.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    for node in parser.jsonld:
        walk(node)
    if body_region:
        if not matched_articles or any(value and not iso_date(value) for value in dates):
            raise ValueError('pressroom_article_date_missing_or_invalid')
        if len({iso_date(value) for value in dates if value}) != 1:
            raise ValueError('pressroom_article_dates_conflict')
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
            full_swedish = re.fullmatch(r'(\d{1,2}) (januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december) (\d{4})', value.strip())
            if full_swedish:
                day, month, year = full_swedish.groups()
                months = 'januari februari mars april maj juni juli augusti september oktober november december'.split()
                try:
                    published = datetime(int(year), months.index(month)+1, int(day), tzinfo=timezone.utc).isoformat()
                    break
                except ValueError:
                    continue
    return {'title': parser.meta.get('og:title', '').strip(), 'published_at': published,
            'summary': parser.meta.get('description') or parser.meta.get('og:description') or '',
            'body': re.sub(r'\s+', ' ', ' '.join(parser.body_parts)).strip()}


def index_link(index_url, href, source):
    url = canonical_url(urljoin(index_url, href))
    parsed = urlsplit(url)
    if parsed.hostname != urlsplit(source['website']).hostname or parsed.query:
        raise ValueError('pressroom_index_link_outside_authority')
    if source.get('canonical_trailing_slash') is True and not parsed.path.endswith('/'):
        url = urlunsplit(parsed._replace(path=parsed.path + '/'))
    return url


def discover(index_html, index_url, source, collector, max_items, now=None):
    if source['kind'] != 'primary' or source.get('collection_method') != 'pressroom_index':
        raise ValueError('official_pressroom_required')
    if type(max_items) is not int or max_items < 0:
        raise ValueError('invalid_pressroom_limit')
    limit = min(max_items, 20)
    if not limit:
        return [], []
    if source.get('index_adapter') is not None:
        if source['index_adapter'] != 'byd_de': raise ValueError('unsupported_pressroom_index_adapter')
        from news_byd import discover as byd_discover
        return byd_discover(index_html, index_url, source, collector, limit, now)
    expected_dates = {}
    if source.get('index_format') == 'rss':
        feed_rows = parse_feed(index_html, source)[:50]
        links = [row['url'] for row in feed_rows]
        for row in feed_rows:
            if row['published_at']:
                old = expected_dates.setdefault(row['url'], row['published_at'])
                if old != row['published_at']:raise ValueError('official_feed_dates_conflict')
    elif source.get('index_format') is not None:
        raise ValueError('unsupported_pressroom_index_format')
    else:
        parser = PageText();parser.feed(index_html);links = parser.links
    urls = []
    for href in links:
        try:
            url = index_link(index_url, href, source)
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
            if url in expected_dates:require_recent_publication(expected_dates[url], now)
            status, _, html, final = collector.fetch(url, source, editorial=True)
            strict_identity = source.get('body_region') or source.get('article_adapter') or source.get('index_format')
            if status != 200 or (strict_identity and final != url):raise ValueError('pressroom_article_inaccessible_or_redirected')
            doc = document(html, url=final, body_region=source.get('body_region'), adapter=source.get('article_adapter'),
                           narrative_class=source.get('narrative_class'))
            if not doc['title'] or not doc['published_at']:
                raise ValueError('missing_release_title_or_date')
            require_recent_publication(doc['published_at'], now)
            if url in expected_dates and expected_dates[url] != doc['published_at']:
                raise ValueError('official_feed_article_date_conflict')
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
