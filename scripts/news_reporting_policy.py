"""Deterministic independence checks; editorial corroboration is not car verification."""
from datetime import datetime
import re
from urllib.parse import urlsplit

from news_editorial import normalize
from news_publisher_registry import PUBLISHERS, REGISTERED_PUBLISHERS
from news_publisher_selection import subject_terms

RECIPE = 'news-article-review-2026-11-v2'
HISTORICAL_RECIPES = frozenset(('news-publisher-short-2026-11-v1', RECIPE))
WIRE = {'reuters.com': 'Reuters', 'apnews.com': 'Associated Press', 'afp.com': 'AFP',
        'bloomberg.com': 'Bloomberg', 'xinhuanet.com': 'Xinhua'}


def same_event(left, right):
    a, b = left['payload'], right['payload']
    try:
        if abs((datetime.fromisoformat(a['published_at']) - datetime.fromisoformat(b['published_at'])).total_seconds()) > 3 * 86400:
            return False
    except (ValueError, KeyError, TypeError):
        return False
    def ids(text):
        return set(re.findall(r'\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]+\b', normalize(text)))
    ai, bi = ids(a['title']), ids(b['title'])
    if ai and bi and not ai & bi:
        return False
    def actions(text):
        text = normalize(text)
        return {name for name, pattern in {
            'launch': r'\b(?:launch\w*|unveil\w*|debut\w*)\b',
            'production': r'\b(?:production|factory|plant)\b',
            'recall': r'\brecall\w*\b',
            'price': r'\b(?:price\w*|discount\w*)\b',
            'test': r'\b(?:test\w*|review\w*)\b',
        }.items() if re.search(pattern, text)}
    aa, ba = actions(a['title']), actions(b['title'])
    if aa and ba and not aa & ba:
        return False
    at, bt = subject_terms(a['title']), subject_terms(b['title'])
    return len(at & bt) >= 2 and len(at & bt) / max(1, min(len(at), len(bt))) >= .3


def independence(left, right):
    errors = []
    sources = [PUBLISHERS.get(i['source_id']) for i in (left, right)]
    if not all(sources):
        return {'passed': False, 'errors': ['editorial_identity_not_verified']}
    if left['url'] == right['url'] or sources[0]['publisher_group'] == sources[1]['publisher_group']:
        errors.append('editorial_common_owner_or_same_article')
    if not same_event(left, right):
        errors.append('editorial_different_event')
    news_hosts = {urlsplit(s['website']).hostname.removeprefix('www.')
                  for s in [*PUBLISHERS.values(), *REGISTERED_PUBLISHERS.values()]} | set(WIRE)
    upstream = []
    bylines = []
    grams = []
    wires = []
    for item, source, other in ((left, sources[0], sources[1]), (right, sources[1], sources[0])):
        p = item['payload']
        if p.get('publisher_group') != source['publisher_group']:
            errors.append('editorial_owner_snapshot_changed')
        links = set(p.get('editorial_links', []))
        other_host = urlsplit(other['website']).hostname.removeprefix('www.')
        if any(urlsplit(u).hostname and urlsplit(u).hostname.removeprefix('www.') == other_host for u in links):
            errors.append('editorial_circular_citation')
        plain = normalize(p['content'])
        name = re.escape(normalize(other['name']))
        if re.search(r'\b(?:according to|reported by|reports? from|via|source|citing)\b.{0,55}\b' + name + r'\b', plain):
            errors.append('editorial_borrowed_reporting')
        upstream.append({u for u in links if urlsplit(u).hostname and urlsplit(u).hostname.removeprefix('www.') in news_hosts})
        wires.append({host for host, label in WIRE.items() if re.search(r'\b' + re.escape(normalize(label)) + r'\b', plain)})
        bylines.append(normalize(p.get('byline', '')))
        words = plain.split()
        grams.append({tuple(words[i:i+7]) for i in range(max(0, len(words)-6))})
    if upstream[0] & upstream[1] or wires[0] & wires[1]:
        errors.append('editorial_shared_upstream_or_wire')
    if bylines[0] and bylines[0] == bylines[1]:
        errors.append('editorial_same_author')
    if min(map(len, grams)) >= 50 and len(grams[0] & grams[1]) / min(map(len, grams)) >= .5:
        errors.append('editorial_copy_or_syndication')
    return {'passed': not errors, 'errors': sorted(set(errors)),
            'groups': [s['publisher_group'] for s in sources],
            'ownership_evidence': [s['ownership_evidence_url'] for s in sources],
            'basis': 'reported_not_independently_verified'}


def reported(bundle):
    return bundle.get('evidence_basis') == 'editorial_corroboration'
