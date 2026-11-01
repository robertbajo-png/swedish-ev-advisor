"""Bounded publisher adapters and explicit primary-source corroboration."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from news_http import Collector, PageText, canonical_url, iso_date, require_recent_publication
from news_store import artifact_hash, stable_id

PUBLISHERS = {
    'carnewschina': {'id': 'carnewschina', 'name': 'CarNewsChina',
        'website': 'https://carnewschina.com', 'kind': 'publisher', 'reliability': .8,
        'feeds': ['https://carnewschina.com/feed/'], 'body_class': 'article_detail__content'},
    'thedriven': {'id': 'thedriven', 'name': 'The Driven', 'website': 'https://thedriven.io',
        'kind': 'publisher', 'reliability': .8, 'feeds': ['https://thedriven.io/feed/'],
        'body_class': 'entry-content'},
}
# Approved identity/path pairs, not an arbitrary hyperlink or an AI-selected URL.
PRIMARY_SOURCES = {
    'fgk.chinatax.gov.cn': ('china-tax', 'State Taxation Administration of China', r'/zcfgk/[^?#]+/content\.html'),
    'cop31.tr': ('cop31', 'COP31 Presidency', r'/news-detail/[a-z0-9-]+'),
    'acceleratingtozero.org': ('accelerating-to-zero', 'Accelerating to Zero Coalition', r'/(?:the-declaration|progress/[^?#]+)/'),
    'www.energy.gov': ('us-energy', 'U.S. Department of Energy', r'/cmei/vehicles/articles/[^/?#]+'),
    'www.volkswagen-newsroom.com': ('vw-press', 'Volkswagen Newsroom', r'/en/press-releases/[^/?#]+-\d+'),
    'www.press.bmwgroup.com': ('bmw-press', 'BMW Group PressClub', r'/global/article/detail/T\d+EN/[^/?#]+'),
    'www.bmwgroup.com': ('bmw-group', 'BMW Group', r'/en/news/general/20\d{2}/[a-z0-9-]+\.html'),
    'www.gacgroup.com': ('gac-group', 'GAC Group', r'/th-th/news/article/[a-z0-9-]+'),
}
CORROBORATION_RULES = (
    {'website': 'https://www.bmwgroup.com', 'triggers': (r'\bbmw\b', r'\bi3\b'),
     'references': ['https://www.bmwgroup.com/en/news/general/2026/bmwi3.html']},
    {'website': 'https://www.gacgroup.com', 'triggers': (r'\bgac\b', r'\binpow\b'),
     'index': 'https://www.gacgroup.com/th-th/news', 'path_match': r'battery.*plant|inpow'},
)
VOID = {'meta', 'link', 'br', 'hr', 'img', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track'}


class PublisherDocument(HTMLParser):
    def __init__(self, body_class=None):
        super().__init__(convert_charrefs=True)
        self.body_class = body_class
        self.stack, self.parts, self.links, self.regions = [], [], [], []
        self.meta, self.canonicals, self.title_parts = {}, [], []
        self.paywall = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            key = a.get('property') or a.get('name')
            if key in ('article:published_time', 'og:title'):
                self.meta.setdefault(key, []).append(a.get('content', ''))
            if a.get('itemprop') == 'isAccessibleForFree' and a.get('content', '').lower() == 'false':
                self.paywall = True
        if tag == 'link' and 'canonical' in a.get('rel', '').split():
            self.canonicals.append(a.get('href', ''))
        active = self.body_class and self.body_class in a.get('class', '').split()
        skip = tag in {'script', 'style', 'noscript', 'nav', 'footer', 'header', 'aside', 'figure'}
        skip = skip or bool({'comments', 'related-posts', 'sharedaddy'} & set(a.get('class', '').split()))
        if tag == 'a' and a.get('href') and any(p[1] for p in self.stack) and not any(p[2] for p in self.stack):
            self.links.append(a['href'])
        if tag not in VOID:
            self.stack.append((tag, active, skip))
            if active:
                self.regions.append([])

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, text):
        if any(t == 'title' for t, _, _ in self.stack):
            self.title_parts.append(text)
        if not any(p[2] for p in self.stack):
            if any(p[1] for p in self.stack):
                self.regions[-1].append(text)
            self.parts.append(text)


def publisher_url(source_id, url):
    source = PUBLISHERS.get(source_id)
    try:
        p = urlsplit(canonical_url(url))
        return bool(source and p.hostname == urlsplit(source['website']).hostname and not p.query
                    and re.fullmatch(r'/20\d{2}/\d{2}/\d{2}/[a-z0-9-]+/', p.path)
                    and canonical_url(url) == url)
    except (ValueError, TypeError):
        return False


def primary_source(url):
    try:
        p = urlsplit(canonical_url(url))
        entry = PRIMARY_SOURCES.get(p.hostname)
        if not entry or p.query or not re.fullmatch(entry[2], p.path):
            return None
        return {'id': entry[0], 'name': entry[1], 'website': 'https://' + p.hostname,
                'kind': 'primary', 'reliability': .98}
    except (ValueError, TypeError):
        return None


def matching_rules(lead):
    title = lead['payload']['title'].lower()
    return [r for r in CORROBORATION_RULES if all(re.search(p, title, re.I) for p in r['triggers'])]


def corroboration_candidates(lead, collector):
    result = []
    for rule in matching_rules(lead):
        if rule.get('references'):
            result.extend((u, {'from_url': rule['website'], 'to_url': u, 'method': 'approved_model_reference'})
                          for u in rule['references'])
            continue
        source = {'website': rule['website']}
        status, _, html, final = collector.fetch(rule['index'], source, editorial=True)
        if status != 200 or final != rule['index']:
            continue
        parser = PageText()
        parser.feed(html)
        for href in parser.links:
            try:
                url = canonical_url(urljoin(final, href))
                if (urlsplit(url).hostname == urlsplit(rule['website']).hostname and primary_source(url)
                        and re.search(rule['path_match'], urlsplit(url).path, re.I)
                        and not any(old[0] == url for old in result)):
                    result.append((url, {'from_url': final, 'to_url': url, 'method': 'official_index',
                                         'index_hash': hashlib.sha256(html.encode()).hexdigest()}))
            except ValueError:
                continue
    return result[:2]


def parse_publisher(html, url, source_id, feed_date=None, now=None):
    if not publisher_url(source_id, url):
        raise ValueError('publisher_url_outside_adapter')
    parser = PublisherDocument(PUBLISHERS[source_id]['body_class'])
    parser.feed(html)
    if parser.paywall or re.search(r'"isAccessibleForFree"\s*:\s*false', html, re.I):
        raise ValueError('publisher_paywall')
    if {canonical_url(urljoin(url, v)) for v in parser.canonicals} != {url}:
        raise ValueError('publisher_canonical_changed_or_missing')
    dates = {iso_date(v) for v in parser.meta.get('article:published_time', [])}
    if len(dates) != 1 or None in dates:
        raise ValueError('publisher_publication_date_missing_or_conflicting')
    published = next(iter(dates))
    require_recent_publication(published, now)
    if feed_date is not None and iso_date(feed_date) != published:
        raise ValueError('publisher_feed_date_conflict')
    titles = set(parser.meta.get('og:title', []))
    if len(titles) != 1 or not next(iter(titles)).strip():
        raise ValueError('publisher_title_missing_or_conflicting')
    if len(parser.regions) != 1:
        raise ValueError('publisher_article_body_missing_or_ambiguous')
    content = ' '.join(' '.join(parser.regions[0]).split())
    if len(content.split()) < 120 or len(content.encode()) > 60000 or '\ufffd' in content:
        raise ValueError('publisher_content_incomplete_or_oversized')
    if re.search(r'just a moment|verify you are human|access denied', content[:800], re.I):
        raise ValueError('publisher_access_challenge')
    return {'title': next(iter(titles)).strip(), 'published_at': published, 'content': content,
            'links': list(dict.fromkeys(canonical_url(urljoin(url, u)) for u in parser.links
                       if urljoin(url, u).startswith('https://')))}


def item_from_document(url, source, doc, now=None):
    return {'id': stable_id(url), 'source_id': source['id'], 'url': url, 'status': 'ready', 'cluster_id': None,
            'payload': {'title': doc['title'], 'published_at': doc.get('published_at'),
                'publisher': source['name'], 'publisher_group': source['id'], 'source_kind': source['kind'],
                'access_status': 'accessible', 'final_url': url, 'fetched_at': (now or datetime.now(timezone.utc)).isoformat(),
                'content': doc['content'], 'content_hash': hashlib.sha256(doc['content'].encode()).hexdigest()}}


def fetch_publisher(source_id, url, collector=None, *, feed_date=None, now=None):
    if not publisher_url(source_id, url):
        raise ValueError('publisher_url_outside_adapter')
    source = PUBLISHERS[source_id]
    status, _, html, final = (collector or Collector()).fetch(url, source, editorial=True)
    if status != 200 or final != url:
        raise ValueError('publisher_inaccessible_or_redirected')
    doc = parse_publisher(html, url, source_id, feed_date, now)
    return item_from_document(url, source, doc, now), doc['links']


def fetch_primary(url, collector, now=None):
    source = primary_source(url)
    if not source:
        raise ValueError('unapproved_primary_url')
    status, _, html, final = collector.fetch(url, source, editorial=True)
    if status != 200 or final != url:
        raise ValueError('primary_inaccessible_or_redirected')
    parser = PublisherDocument()
    parser.feed(html)
    page = PageText()
    page.feed(html)
    if parser.paywall or page.paywall or re.search(r'"isAccessibleForFree"\s*:\s*false', html, re.I):
        raise ValueError('primary_paywall')
    content = page.plain()
    if len(content) < 300 or len(content.encode()) > 90000 or '\ufffd' in content:
        raise ValueError('primary_content_incomplete_or_oversized')
    if re.search(r'just a moment|verify you are human|access denied', content[:800], re.I):
        raise ValueError('primary_access_challenge')
    dates = {iso_date(v) for v in parser.meta.get('article:published_time', [])}
    dates.discard(None)
    if len(dates) > 1:
        raise ValueError('primary_conflicting_dates')
    title = next(iter(parser.meta.get('og:title', [])), '') or ' '.join(parser.title_parts).strip()
    if not title:
        raise ValueError('primary_title_missing')
    doc = {'title': title, 'published_at': next(iter(dates), None), 'content': content}
    links = [canonical_url(urljoin(url, u)) for u in page.links if urljoin(url, u).startswith('https://')]
    return item_from_document(url, source, doc, now), links


def bundle_errors(bundle, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        items = bundle['items']
        if not 2 <= len(items) <= 3 or len({i['url'] for i in items}) != len(items):
            return ['publisher_distinct_report_and_primary_required']
        lead = items[0]
        if not publisher_url(lead['source_id'], lead['url']):
            return ['publisher_lead_invalid']
        require_recent_publication(lead['payload']['published_at'], now)
        edges = bundle['provenance']
        seen = {lead['url']}
        if len(edges) != len(items) - 1:
            return ['publisher_primary_provenance_invalid']
        for item, edge in zip(items[1:], edges):
            method = edge.get('method', 'publisher_link')
            allowed = False
            if method == 'publisher_link':
                allowed = set(edge) == {'from_url', 'to_url'} and edge['from_url'] in seen
            for rule in matching_rules(lead):
                if method == 'approved_model_reference':
                    allowed = (set(edge) == {'from_url', 'to_url', 'method'} and edge['from_url'] == rule['website']
                               and item['url'] in rule.get('references', []))
                elif method == 'official_index':
                    allowed = (set(edge) == {'from_url', 'to_url', 'method', 'index_hash'}
                               and edge['from_url'] == rule.get('index')
                               and bool(re.fullmatch(r'[a-f0-9]{64}', edge['index_hash']))
                               and bool(re.search(rule.get('path_match', r'(?!)'), urlsplit(item['url']).path, re.I)))
                if allowed:
                    break
            if not allowed or edge['to_url'] != item['url']:
                return ['publisher_primary_provenance_invalid']
            seen.add(item['url'])
        for index, item in enumerate(items):
            p = item['payload']
            source = PUBLISHERS.get(item['source_id']) if index == 0 else primary_source(item['url'])
            if (not source or item['id'] != stable_id(item['url']) or source['id'] != item['source_id']
                    or p['publisher'] != source['name'] or p['source_kind'] != source['kind']
                    or p['access_status'] != 'accessible' or p['final_url'] != item['url']
                    or p['content_hash'] != hashlib.sha256(p['content'].encode()).hexdigest()
                    or not -timedelta(minutes=5) <= now - datetime.fromisoformat(p['fetched_at']) <= timedelta(days=1)):
                return ['publisher_source_snapshot_invalid']
        expected = {k: v for k, v in bundle.items() if k != 'bundle_hash'}
        if artifact_hash(expected) != bundle['bundle_hash']:
            return ['publisher_bundle_changed']
        return []
    except (KeyError, TypeError, ValueError):
        return ['publisher_bundle_invalid_or_stale']


def collect_bundle(source_id, url, collector, *, feed_date=None, now=None):
    lead, links = fetch_publisher(source_id, url, collector, feed_date=feed_date, now=now)
    candidates = [(u, {'from_url': lead['url'], 'to_url': u})
                  for u in list(dict.fromkeys(u for u in links if primary_source(u)))[:2]]
    if not candidates:
        candidates = corroboration_candidates(lead, collector)
    items, provenance, errors = [lead], [], []
    for candidate, edge in candidates:
        try:
            item, child_links = fetch_primary(candidate, collector, now)
            items.append(item)
            provenance.append(edge)
            # A linked official policy may point to the actual governing decision.
            if source_id == 'carnewschina' and item['source_id'] == 'china-tax' and len(items) < 3:
                child = next((u for u in child_links if u != candidate and primary_source(u)
                              and urlsplit(u).hostname == urlsplit(candidate).hostname), None)
                if child:
                    try:
                        item, _ = fetch_primary(child, collector, now)
                        items.append(item)
                        provenance.append({'from_url': candidate, 'to_url': child})
                    except Exception as exc:
                        errors.append(type(exc).__name__ + ':' + str(exc)[:100])
            break
        except Exception as exc:
            errors.append(type(exc).__name__ + ':' + str(exc)[:100])
    if len(items) < 2:
        raise ValueError('publisher_no_accessible_primary_support:' + ','.join(errors)[:120])
    result = {'items': items, 'provenance': provenance, 'support_fetch_errors': errors}
    result['bundle_hash'] = artifact_hash(result)
    if bundle_errors(result, now):
        raise ValueError('publisher_bundle_validation_failed')
    return result


def same_sources(left, right):
    def identity(bundle):
        return [{k: i[k] for k in ('id', 'source_id', 'url')} | {'payload': {
            k: i['payload'][k] for k in ('title', 'published_at', 'content_hash', 'final_url')}} for i in bundle['items']]
    return identity(left) == identity(right) and left['provenance'] == right['provenance']
