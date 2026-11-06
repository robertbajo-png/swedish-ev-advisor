"""Bounded publisher adapters and explicit primary-source corroboration."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from news_http import Collector, PageText, canonical_url, iso_date, require_recent_publication
from news_store import artifact_hash, stable_id
from news_publisher_selection import primary_identity_matches, subject_terms, candidate_assessment
from news_publisher_registry import PUBLISHERS, LEAD_SOURCES
from news_reporting_policy import independence, same_event, reported
from news_primary_discovery import (authorities, source_for, discover as discover_originals,
                                    valid_edge, source_subject_matches)
from news_pressrooms import document as primary_document, PressDocument
from news_document_evidence import html_document, valid_html_snapshot

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
PRIMARY_AUTHORITIES = authorities(PRIMARY_SOURCES)
OFFICIAL_LEAD_SOURCES = frozenset(s['id'] for s in PRIMARY_AUTHORITIES.values()
    if s.get('official_article_lead') is True and s.get('collection_method') == 'pressroom_index'
    and s.get('primary_date_required') is True)


class OriginalSourceNotFound(ValueError):
    def __init__(self, errors, trace):
        self.discovery_trace = trace[:24]
        super().__init__('publisher_no_primary_or_independent_pair:' + ','.join(errors)[:120])


class PublisherContentHeld(ValueError):
    def __init__(self, reason):
        self.discovery_trace = [{'stage': 'publisher_content_triage', 'status': 'held', 'reason': reason}]
        super().__init__('publisher_content_triage:' + reason)
CORROBORATION_RULES = (
    {'website': 'https://www.bmwgroup.com', 'triggers': (r'\bbmw\b', r'\bi3\b'),
     'index': 'https://www.bmwgroup.com/en/news.html', 'path_match': r'/[^/]*i3[^/]*\.html'},
    {'website': 'https://www.bmwgroup.com', 'triggers': (r'\bbmw\b', r'\bi3\b'),
     'references': ['https://www.bmwgroup.com/en/news/general/2026/bmwi3.html']},
    {'website': 'https://www.gacgroup.com', 'triggers': (r'\bgac\b', r'\binpow\b'),
     'index': 'https://www.gacgroup.com/th-th/news', 'path_match': r'battery.*plant|inpow'},
)
VOID = {'meta', 'link', 'br', 'hr', 'img', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track'}


class PublisherDocument(HTMLParser):
    def __init__(self, body_class=None, article_mode=False, body_attribute=None):
        super().__init__(convert_charrefs=True)
        self.body_class = body_class
        self.article_mode = article_mode
        self.body_attribute = body_attribute
        self.stack, self.parts, self.links, self.regions = [], [], [], []
        self.meta, self.canonicals, self.title_parts = {}, [], []
        self.paywall = False
        self.article_tables = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            key = a.get('property') or a.get('name')
            if key in ('article:published_time', 'og:title', 'author', 'article:author'):
                self.meta.setdefault(key, []).append(a.get('content', ''))
            if a.get('itemprop') == 'isAccessibleForFree' and a.get('content', '').lower() == 'false':
                self.paywall = True
        if tag == 'link' and 'canonical' in a.get('rel', '').split():
            self.canonicals.append(a.get('href', ''))
        active = ((self.body_class and self.body_class in a.get('class', '').split())
                  or (self.body_attribute and self.body_attribute in a)
                  or (self.article_mode and tag == 'article'))
        if tag == 'table' and any(p[1] for p in self.stack) and not any(p[2] for p in self.stack):
            self.article_tables += 1
        skip = tag in {'script', 'style', 'noscript', 'nav', 'footer', 'header', 'aside', 'figure', 'table'}
        skip = skip or (tag == 'article' and not active and any(p[1] for p in self.stack))
        skip = skip or bool({'comments', 'related-posts', 'sharedaddy', 'articlescroller', 'adunit', 'google-ad'}
                            & set(a.get('class', '').split()))
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
                    and re.fullmatch(source['article_path_pattern'], p.path)
                    and canonical_url(url) == url)
    except (ValueError, TypeError):
        return False


def primary_source(url):
    return source_for(url, PRIMARY_AUTHORITIES)


def official_lead_url(source_id, url):
    source = primary_source(url)
    return bool(source and source['id'] == source_id and source_id in OFFICIAL_LEAD_SOURCES
                and canonical_url(url) == url)


def article_lead_url(source_id, url):
    return publisher_url(source_id, url) or official_lead_url(source_id, url)


def official_release(bundle):
    return bundle.get('evidence_basis') == 'official_release'


def collect_official_release(source_id, url, collector, *, feed_date=None, now=None):
    if not official_lead_url(source_id, url):
        raise ValueError('unapproved_official_article_lead')
    item, _ = fetch_primary(url, collector, now)
    published = require_recent_publication(item['payload'].get('published_at'), now)
    if feed_date is not None and iso_date(feed_date) != published:
        raise ValueError('official_feed_date_conflict')
    bundle = {'items': [item], 'provenance': [], 'support_fetch_errors': [],
              'evidence_basis': 'official_release', 'discovery_trace': [
                  {'stage': 'official_release', 'url': url, 'status': 'source_matched'}]}
    bundle['bundle_hash'] = artifact_hash(bundle)
    if bundle_errors(bundle, now): raise ValueError('official_bundle_validation_failed')
    return bundle


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
    parser = PublisherDocument(PUBLISHERS[source_id]['body_class'],
                               body_attribute=PUBLISHERS[source_id].get('body_attribute'))
    parser.feed(html)
    if not parser.regions:
        generic = PublisherDocument(article_mode=True)
        generic.feed(html)
        if len(generic.regions) == 1:
            parser = generic
    if parser.paywall or re.search(r'"isAccessibleForFree"\s*:\s*false', html, re.I):
        raise ValueError('publisher_paywall')
    if {canonical_url(urljoin(url, v)) for v in parser.canonicals} != {url}:
        raise ValueError('publisher_canonical_changed_or_missing')
    if any(v and not iso_date(v) for v in parser.meta.get('article:published_time', [])):
        raise ValueError('publisher_publication_date_invalid')
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
            'unvalidated_table_context': bool(parser.article_tables),
            'byline': '; '.join(sorted(set(parser.meta.get('author', []) + parser.meta.get('article:author', [])))),
            'links': list(dict.fromkeys(canonical_url(urljoin(url, u)) for u in parser.links
                       if urljoin(url, u).startswith('https://')))}


def item_from_document(url, source, doc, now=None):
    return {'id': stable_id(url), 'source_id': source['id'], 'url': url, 'status': 'ready', 'cluster_id': None,
            'payload': {'title': doc['title'], 'published_at': doc.get('published_at'),
                'publisher': source['name'], 'publisher_group': source.get('publisher_group', source['id']), 'source_kind': source['kind'],
                'editorial_links': doc.get('links', []), 'byline': doc.get('byline', ''),
                'access_status': 'accessible', 'final_url': url, 'fetched_at': (now or datetime.now(timezone.utc)).isoformat(),
                'content': doc['content'], 'content_hash': hashlib.sha256(doc['content'].encode()).hexdigest(),
                **({'unvalidated_table_context': True} if doc.get('unvalidated_table_context') else {}),
                **({'document_evidence': doc['document_evidence']} if 'document_evidence' in doc else {})}}


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
    if urlsplit(url).path.lower().endswith('.pdf'):
        raise ValueError('primary_pdf_extraction_required')
    status, headers, html, final = collector.fetch(url, source, editorial=True)
    if status != 200 or final != url:
        raise ValueError('primary_inaccessible_or_redirected')
    if 'pdf' in str(headers.get('Content-Type', headers.get('content-type', ''))).lower() or html.startswith('%PDF'):
        raise ValueError('primary_pdf_extraction_required')
    parser = PublisherDocument()
    parser.feed(html)
    page = PageText()
    page.feed(html)
    if parser.paywall or page.paywall or re.search(r'"isAccessibleForFree"\s*:\s*false', html, re.I):
        raise ValueError('primary_paywall')
    content, document_evidence = html_document(html)
    if source['id'] in OFFICIAL_LEAD_SOURCES:
        scoped = primary_document(html, exclude_tables=True, url=url, body_region=source.get('body_region'),
                                  adapter=source.get('article_adapter'), narrative_class=source.get('narrative_class'))
        if source.get('body_region') or source.get('article_adapter'):
            content = scoped['body']
        else:
            content = scoped['body'] or content
    if len(content) < 300 or len(content.encode()) > 90000 or '\ufffd' in content:
        raise ValueError('primary_content_incomplete_or_oversized')
    if re.search(r'just a moment|verify you are human|access denied', content[:800], re.I):
        raise ValueError('primary_access_challenge')
    if any(v and not iso_date(v) for v in parser.meta.get('article:published_time', [])):
        raise ValueError('primary_publication_date_invalid')
    dates = {iso_date(v) for v in parser.meta.get('article:published_time', [])}
    dates.discard(None)
    if source.get('article_adapter'):
        dates.add(scoped['published_at'])
    if len(dates) > 1:
        raise ValueError('primary_conflicting_dates')
    structured_parser = PressDocument(); structured_parser.feed(html)
    def article_dates(node):
        if isinstance(node, list):
            for child in node: article_dates(child)
        elif isinstance(node, dict):
            kinds = node.get('@type', [])
            kinds = [kinds] if isinstance(kinds,str) else kinds
            identity_scoped = source.get('body_region') or source.get('article_adapter')
            declared = node.get('url') or node.get('mainEntityOfPage') or (
                node.get('@id') if identity_scoped else None)
            if isinstance(declared,dict): declared = declared.get('@id') or declared.get('url')
            matching = ((not declared and not identity_scoped) or
                        (isinstance(declared, str) and canonical_url(urljoin(url,declared)) == url))
            if matching and any(k in ('NewsArticle','Article','PressRelease') for k in kinds):
                if node.get('datePublished'):
                    value = iso_date(node['datePublished'])
                    if not value: raise ValueError('primary_publication_date_invalid')
                    dates.add(value)
            for child in node.values():
                if isinstance(child,(list,dict)): article_dates(child)
    for node in structured_parser.jsonld: article_dates(node)
    if not dates and structured_parser.date_parts:
        value = primary_document(html)['published_at']
        if value: dates.add(value)
    if len(dates) > 1:
        raise ValueError('primary_conflicting_dates')
    if source.get('primary_date_required') and not dates:
        raise ValueError('primary_publication_date_missing')
    title = next(iter(parser.meta.get('og:title', [])), '') or ' '.join(parser.title_parts).strip()
    if not title:
        raise ValueError('primary_title_missing')
    links = [canonical_url(urljoin(url, u)) for u in page.links if urljoin(url, u).startswith('https://')]
    doc = {'title': title, 'published_at': next(iter(dates), None), 'content': content, 'links':links,
           'document_evidence': document_evidence}
    return item_from_document(url, source, doc, now), links


def bundle_errors(bundle, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        items = bundle['items']
        official = official_release(bundle)
        if (not (len(items) == 1 if official else 2 <= len(items) <= 3)
                or len({i['url'] for i in items}) != len(items)):
            return ['publisher_distinct_report_and_primary_required']
        lead = items[0]
        if not (official_lead_url(lead['source_id'], lead['url']) if official else publisher_url(lead['source_id'], lead['url'])):
            return ['publisher_lead_invalid']
        require_recent_publication(lead['payload']['published_at'], now)
        edges = bundle['provenance']
        editorial = reported(bundle)
        if editorial:
            if len(items) != 2 or not independence(*items)['passed']:
                return ['publisher_editorial_independence_failed']
            if edges != [{'from_url': lead['url'], 'to_url': items[1]['url'], 'method': 'editorial_corroboration'}]:
                return ['publisher_editorial_provenance_invalid']
        seen = {lead['url']}
        if len(edges) != len(items) - 1:
            return ['publisher_primary_provenance_invalid']
        for item, edge in zip(items[1:], edges):
            if editorial:
                continue
            method = edge.get('method', 'publisher_link')
            allowed = False
            if method == 'publisher_link':
                allowed = set(edge) == {'from_url', 'to_url'} and edge['from_url'] in seen
            elif method in ('official_discovery_index', 'official_catalog'):
                allowed = valid_edge(edge, lead, PRIMARY_AUTHORITIES)
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
            source = PUBLISHERS.get(item['source_id']) if (index == 0 and not official) or editorial else primary_source(item['url'])
            if editorial:
                require_recent_publication(p['published_at'], now)
            if (not source or item['id'] != stable_id(item['url']) or source['id'] != item['source_id']
                    or p['publisher'] != source['name'] or p['source_kind'] != source['kind']
                    or p['access_status'] != 'accessible' or p['final_url'] != item['url']
                    or p['content_hash'] != hashlib.sha256(p['content'].encode()).hexdigest()
                    or not -timedelta(minutes=5) <= now - datetime.fromisoformat(p['fetched_at']) <= timedelta(days=1)):
                return ['publisher_source_snapshot_invalid']
            if 'document_evidence' in p and not valid_html_snapshot(p['document_evidence']):
                return ['publisher_document_snapshot_invalid']
        expected = {k: v for k, v in bundle.items() if k != 'bundle_hash'}
        if artifact_hash(expected) != bundle['bundle_hash']:
            return ['publisher_bundle_changed']
        return []
    except (KeyError, TypeError, ValueError):
        return ['publisher_bundle_invalid_or_stale']


def collect_bundle(source_id, url, collector, *, feed_date=None, now=None, corroborating_items=(), content_triage=False):
    if official_lead_url(source_id, url):
        return collect_official_release(source_id, url, collector, feed_date=feed_date, now=now)
    lead, links = fetch_publisher(source_id, url, collector, feed_date=feed_date, now=now)
    if content_triage:
        assessment = candidate_assessment({**lead['payload'], 'summary': lead['payload']['content'][:1200]}, now)
        if not assessment['eligible']:
            raise PublisherContentHeld(assessment['reason'])
    terms = subject_terms(lead['payload']['title'])
    direct_urls = [u for u in dict.fromkeys(links)
                   if (source := primary_source(u)) and source_subject_matches(lead, source)]
    direct_urls.sort(key=lambda u: len(terms & subject_terms(urlsplit(u).path.replace('-', ' '))), reverse=True)
    direct = [(u, {'from_url': lead['url'], 'to_url': u}) for u in direct_urls[:2]]
    items, provenance, errors, trace = [lead], [], [], []
    accepted, visited = [], set()
    for strategy in ('direct', 'catalog', 'legacy', 'indexes'):
        if len(visited) >= 6:
            trace.append({'stage':'official_discovery','status':'candidate_fetch_limit'})
            break
        try:
            if strategy == 'direct': candidates = direct
            elif strategy == 'legacy': candidates = corroboration_candidates(lead, collector)
            else:
                candidates = discover_originals(lead, collector, PRIMARY_AUTHORITIES,
                    corroborating_items, trace, indexes=strategy == 'indexes')
        except Exception as exc:
            errors.append(type(exc).__name__ + ':' + str(exc)[:100])
            trace.append({'stage':strategy,'status':'failed','reason':type(exc).__name__+':'+str(exc)[:100]})
            candidates = []
        for candidate, edge in candidates:
            if len(visited) >= 6: break
            if candidate in visited:
                continue
            visited.add(candidate)
            try:
                item, child_links = fetch_primary(candidate, collector, now)
                if not primary_identity_matches(lead, item):
                    raise ValueError('publisher_primary_subject_mismatch')
                date = item['payload'].get('published_at')
                if date:
                    gap = datetime.fromisoformat(lead['payload']['published_at']) - datetime.fromisoformat(date)
                    if gap > timedelta(days=30): raise ValueError('publisher_old_primary_background_only')
                    if gap < -timedelta(days=1): raise ValueError('publisher_primary_after_report')
                accepted.append((item, edge, child_links))
                trace.append({'stage':strategy,'url':candidate,'status':'source_matched'})
            except Exception as exc:
                errors.append(type(exc).__name__ + ':' + str(exc)[:100])
                trace.append({'stage':strategy,'url':candidate,'status':'held',
                              'reason':type(exc).__name__+':'+str(exc)[:120]})
        if accepted:
            break
    if accepted:
        terms = subject_terms(lead['payload']['title'])
        accepted.sort(key=lambda row: (row[0]['payload'].get('published_at') or '',
            len(terms & subject_terms(row[0]['payload']['title']))), reverse=True)
        item, edge, child_links = accepted[0]
        items.append(item)
        provenance.append(edge)
        # A linked official policy may point to the actual governing decision.
        if source_id == 'carnewschina' and item['source_id'] == 'china-tax':
            child = next((u for u in child_links if u != item['url'] and primary_source(u)
                          and urlsplit(u).hostname == urlsplit(item['url']).hostname), None)
            if child:
                try:
                    child_item, _ = fetch_primary(child, collector, now)
                    items.append(child_item)
                    provenance.append({'from_url': item['url'], 'to_url': child})
                except Exception as exc:
                    errors.append(type(exc).__name__ + ':' + str(exc)[:100])
    if len(items) < 2:
        candidates = [item for item in corroborating_items if item['source_id'] in PUBLISHERS
                      and item['source_id'] != source_id and publisher_url(item['source_id'], item['url'])
                      and same_event(lead, item)]
        candidates.sort(key=lambda item: item['payload'].get('published_at', ''), reverse=True)
        for candidate in candidates[:4]:
            try:
                peer, _ = fetch_publisher(candidate['source_id'], candidate['url'], collector,
                    feed_date=candidate['payload']['published_at'], now=now)
                checked = independence(lead, peer)
                if not checked['passed']:
                    errors.extend(checked['errors'])
                    continue
                items.append(peer)
                provenance.append({'from_url': lead['url'], 'to_url': peer['url'], 'method': 'editorial_corroboration'})
                break
            except Exception as exc:
                errors.append(type(exc).__name__ + ':' + str(exc)[:100])
        if len(items) < 2:
            raise OriginalSourceNotFound(errors, trace)
    result = {'items': items, 'provenance': provenance, 'support_fetch_errors': errors, 'discovery_trace':trace[:24]}
    result['evidence_basis'] = 'editorial_corroboration' if items[1]['payload']['source_kind'] == 'publisher' else 'primary'
    result['bundle_hash'] = artifact_hash(result)
    if bundle_errors(result, now):
        raise ValueError('publisher_bundle_validation_failed')
    return result


def same_sources(left, right):
    def identity(bundle):
        return [{k: i[k] for k in ('id', 'source_id', 'url')} | {'payload': {
            k: i['payload'].get(k) for k in ('title', 'published_at', 'content_hash', 'final_url',
                                           'publisher_group', 'editorial_links', 'byline', 'unvalidated_table_context')} | {
            'document_tables': i['payload'].get('document_evidence', {}).get('tables', [])}}
            for i in bundle['items']]
    return (identity(left) == identity(right) and left['provenance'] == right['provenance']
            and left.get('evidence_basis', 'primary') == right.get('evidence_basis', 'primary'))


def refresh_bundle(bundle, collector, now=None):
    fresh = []
    for old in bundle['items']:
        if old['payload']['source_kind'] == 'primary':
            item, _ = fetch_primary(old['url'], collector, now)
        else:
            item, _ = fetch_publisher(old['source_id'], old['url'], collector, feed_date=old['payload']['published_at'], now=now)
        fresh.append(item)
    result = {**bundle, 'items': fresh}
    result['bundle_hash'] = artifact_hash({k: v for k, v in result.items() if k != 'bundle_hash'})
    if bundle_errors(result, now):
        raise ValueError('publisher_refreshed_editorial_pair_invalid')
    return result
