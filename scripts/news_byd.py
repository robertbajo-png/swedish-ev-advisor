"""Strict BYD Germany pressroom adapter. Listings discover; article bodies prove."""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from news_http import AGENT, EditorialPolicy, canonical_url, iso_date, require_recent_publication, reserved

WEBSITE = 'https://www.byd.com'
INDEX = WEBSITE + '/de/news-und-presse'
QUERY = 'https://cms-api.byd.com/es-global/search'
ARTICLE_PATH = r'/de/presse/[a-z0-9-]+'
VOID = {'meta', 'link', 'br', 'hr', 'img', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track'}
MONTHS = 'Januar Februar M\u00e4rz April Mai Juni Juli August September Oktober November Dezember'.split()


def article_url(url):
    p = urlsplit(canonical_url(url))
    if canonical_url(url) != url or p.hostname != 'www.byd.com' or p.query or not re.fullmatch(ARTICLE_PATH, p.path):
        raise ValueError('byd_article_outside_authority')
    return url


class BydDocument(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.canonicals, self.datasets = [], [], []
        self.articles, self.titles, self.dates, self.blocks, self.meta = 0, [], [], [], {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get('class', '').split())
        if tag == 'link' and 'canonical' in a.get('rel', '').split(): self.canonicals.append(a.get('href', ''))
        if tag == 'meta': self.meta.setdefault(a.get('property') or a.get('name'), []).append(a.get('content', ''))
        if tag == 'div' and 'top' in classes and any('m07-news-list' in c for _, c, _ in self.stack):
            self.datasets.append({k: a.get(k) for k in ('data-url', 'data-brand-name', 'data-site-name', 'data-type')})
        if tag == 'article' and 'news-article' in classes: self.articles += 1
        header = any(t == 'article' and 'news-article' in c for t, c, _ in self.stack)
        slot = None
        if header and tag == 'h1': self.titles.append([]); slot = self.titles[-1]
        if header and 'article-meta' in classes: self.dates.append([]); slot = self.dates[-1]
        if 'news-text-container' in classes and any(t == 'section' and 'news-text-block' in c for t, c, _ in self.stack):
            if any(s is not None for _, _, s in self.stack): raise ValueError('byd_nested_body_region')
            self.blocks.append([]); slot = self.blocks[-1]
            if len(self.blocks) > 20: raise ValueError('byd_body_region_limit')
        if tag not in VOID: self.stack.append((tag, classes, slot))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]; break

    def handle_data(self, text):
        if any(t in ('script', 'style', 'nav', 'footer', 'aside', 'noscript', 'table') for t, _, _ in self.stack): return
        if any(c & {'article-content', 'm14-news-swiper', 'news-list-mount-root-container'} for _, c, _ in self.stack): return
        for _, _, slot in self.stack:
            if slot is not None: slot.append(text)


def document(html, url):
    article_url(url)
    p = BydDocument(); p.feed(html)
    if p.canonicals != [url]: raise ValueError('byd_canonical_changed_or_missing')
    if (p.articles != 1 or len(p.titles) != 1 or len(p.dates) != 1 or not p.blocks
            or any(slot is not None or (tag == 'article' and 'news-article' in classes) for tag, classes, slot in p.stack)):
        raise ValueError('byd_article_layout_missing_or_ambiguous')
    flat = lambda parts: re.sub(r'\s+', ' ', ' '.join(parts)).strip()
    match = re.fullmatch(r'[^,|]{1,80}, (\d{1,2})\. (' + '|'.join(MONTHS) + r') (\d{4}) \| Pressemitteilung', flat(p.dates[0]))
    if not match: raise ValueError('byd_article_date_missing_or_invalid')
    day, month, year = match.groups()
    published = datetime(int(year), MONTHS.index(month)+1, int(day), tzinfo=timezone.utc).isoformat()
    titles = p.meta.get('og:title', [])
    if len(titles) != 1 or not titles[0].strip() or not flat(p.titles[0]): raise ValueError('byd_article_title_missing_or_ambiguous')
    timestamps = []
    for value in p.meta.get('article:published_time', []):
        if not iso_date(value) or iso_date(value)[:10] != published[:10]: raise ValueError('byd_article_dates_conflict')
        timestamps.append(iso_date(value))
    if len(set(timestamps)) > 1: raise ValueError('byd_article_dates_conflict')
    if timestamps: published = timestamps[0]
    body = flat([flat(parts) for parts in p.blocks])
    if len(body.encode()) > 90000: raise ValueError('byd_body_too_large')
    return {'title': titles[0].strip(), 'published_at': published,
            'summary': next(iter(p.meta.get('description') or p.meta.get('og:description') or [''])),
            'body': body}


def listing(html, index_url, source, collector):
    if (index_url != INDEX or source.get('id') != 'byd-de-press' or source.get('website') != WEBSITE
            or source.get('kind') != 'primary' or source.get('index_adapter') != 'byd_de'):
        raise ValueError('byd_official_index_required')
    p = BydDocument(); p.feed(html)
    expected = {'data-url': QUERY, 'data-brand-name': 'byd', 'data-site-name': 'de', 'data-type': 'news'}
    if p.datasets != [expected] or p.canonicals != [INDEX]: raise ValueError('byd_index_configuration_changed')
    robots = collector.policy('https://cms-api.byd.com')
    policy = EditorialPolicy(robots)
    if not policy.can_fetch(AGENT, QUERY): raise ValueError('robots_disallowed')
    delay = robots.crawl_delay(AGENT) or 1
    if delay > 30: raise ValueError('crawl_delay_exceeds_run_budget')
    time.sleep(max(0, delay - (time.monotonic() - collector.last_fetch.get('cms-api.byd.com', 0))))
    payload = {'brandName': 'byd', 'siteName': 'de', 'type': 'news', 'page': 1, 'size': 20,
               'text': '', 'sortField': 'date', 'tags': []}
    status, headers, body, final = collector.request(QUERY, 'cms-api.byd.com',
        {'Content-Type': 'application/json'}, policy, data=json.dumps(payload).encode())
    if status != 200 or final != QUERY: raise ValueError('byd_listing_inaccessible_or_redirected')
    if reserved(headers, body): raise ValueError('tdm_reserved')
    response = json.loads(body)
    if (not isinstance(response, dict) or type(response.get('code')) is not int or response['code'] != 0
            or response.get('isSuccess') is not True):
        raise ValueError('byd_listing_failed')
    data = response.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('records'), list) or len(data['records']) > 20:
        raise ValueError('byd_listing_shape_or_limit')
    return data['records']


def discover(html, index_url, source, collector, max_items, now=None):
    if type(max_items) is not int or max_items < 0: raise ValueError('invalid_pressroom_limit')
    if not max_items: return [], []
    records = listing(html, index_url, source, collector)
    rows, errors, seen = [], [], set()
    for row in records[:min(20, max_items * 3)]:
        url = INDEX
        try:
            if not isinstance(row, dict): raise ValueError('byd_listing_row_invalid')
            raw_url, date = row.get('url'), row.get('date')
            if (row.get('type') != 'news' or not isinstance(raw_url, str) or len(raw_url) > 500
                    or not isinstance(date, str) or not re.fullmatch(r'20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', date)):
                raise ValueError('byd_listing_row_invalid')
            url = article_url(urljoin(WEBSITE, raw_url))
            if url in seen: continue
            seen.add(url)
            require_recent_publication(date[:10], now)
            status, _, body, final = collector.fetch(url, source, editorial=True)
            if status != 200 or final != url: raise ValueError('byd_article_inaccessible_or_redirected')
            doc = document(body, url)
            require_recent_publication(doc['published_at'], now)
            if doc['published_at'][:10] != date[:10]: raise ValueError('byd_listing_article_date_conflict')
            if len(doc['body'].split()) < 120: raise ValueError('insufficient_accessible_content')
            rows.append({'url': url, 'title': doc['title'], 'published_at': doc['published_at'],
                         'summary': doc['summary'], 'content_hash': hashlib.sha256(body.encode()).hexdigest()})
            if len(rows) == min(20, max_items): break
        except Exception as error:
            errors.append({'url': url, 'reason': type(error).__name__ + ':' + str(error)[:160]})
    return sorted(rows, key=lambda row: row['published_at'], reverse=True), errors
