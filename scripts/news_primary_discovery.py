"""Free bounded official-source discovery. Candidates are not verified claims."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from news_http import canonical_url, parse_feed, iso_date
from datetime import datetime, timedelta
from news_publisher_selection import (subject_terms, primary_identity_matches, subject_brands,
                                      model_identifiers, event_conflicts)
from news_store import artifact_hash, stable_id
from news_pressrooms import index_link

ROOT = Path(__file__).resolve().parents[1]
MAX_INDEXES = 2
MAX_CANDIDATES = 6


def authorities(legacy):
    """Explicit host/path policy plus existing primary registry, not AI URLs."""
    result = {host: {'id': row[0], 'name': row[1], 'website': 'https://' + host,
        'article_path_pattern': row[2], 'kind': 'primary', 'reliability': .98}
        for host, row in legacy.items()}
    for row in json.loads((ROOT / 'data/news/sources.json').read_text(encoding='utf-8')):
        if row['kind'] != 'primary' or not row.get('article_path_pattern'):
            continue
        parsed = urlsplit(row['website'])
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError('invalid_official_source_registry')
        old = result.get(parsed.hostname)
        if old and old['id'] != row['id']:
            raise ValueError('official_source_identity_conflict')
        re.compile(row['article_path_pattern'])
        if 'covered_brands' in row:
            brands = row['covered_brands']
            if not isinstance(brands, list) or not brands or any(
                    not isinstance(brand, str) or len(subject_brands(brand)) != 1 for brand in brands):
                raise ValueError('invalid_official_source_brands')
        for expression in row.get('discovery_triggers', []): re.compile(expression)
        for index in row.get('indexes', []) + row.get('feeds', []):
            if urlsplit(canonical_url(index)).hostname != parsed.hostname:
                raise ValueError('official_source_index_outside_authority')
        result[parsed.hostname] = {**(old or {}), **row, 'reliability': .98}
    return result


def source_for(url, registry):
    try:
        parsed = urlsplit(canonical_url(url))
        source = registry.get(parsed.hostname)
        if source and not parsed.query and re.fullmatch(source['article_path_pattern'], parsed.path):
            return source
    except (TypeError, ValueError):
        pass
    return None


class IndexLinks(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.current = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            self.current = {'href': a['href'], 'parts': []}
    def handle_data(self, text):
        if self.current is not None: self.current['parts'].append(text)
    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.links.append((self.current['href'], ' '.join(self.current['parts'])[:300]))
            self.current = None


def related(lead, title, summary='', publisher=''):
    return primary_identity_matches(lead, {'payload': {'title': title, 'content': summary, 'publisher': publisher}})


def candidate_related(lead, title, summary='', url='', *, publisher=''):
    """Broader discovery only; fetched documents must pass the strict match too."""
    if event_conflicts(lead['payload']['title'], title, explicit_markets=True):
        return False
    a_brands = subject_brands(lead['payload']['title'])
    b_brands = subject_brands(title) or subject_brands(publisher)
    if a_brands and b_brands and not a_brands & b_brands: return False
    report_models, candidate_models = model_identifiers(lead['payload']['title']), model_identifiers(title)
    if report_models and subject_brands(publisher) and not report_models & candidate_models:
        return False
    if report_models and candidate_models and not report_models & candidate_models:
        return False
    if not a_brands and b_brands and not report_models & candidate_models:
        return False
    if related(lead,title,summary,publisher): return True
    def terms(text):
        result=subject_terms(text)
        if re.search(r'bilsalg|nybilregistrering|immatriculation|registrations?|marche automobile',text,re.I):
            result.add('topic:registrations')
        return result
    a=terms(lead['payload']['title']+' '+lead['payload']['content'][:3500])
    b=terms(title+' '+summary+' '+urlsplit(url).path)
    return len(a & b)>=2


def source_subject_matches(lead, source):
    target = subject_brands(lead['payload']['title'])
    authority = subject_brands(source.get('name', '') + ' ' + ' '.join(source.get('covered_brands', [])))
    return not target or not authority or bool(target & authority)


def discover(lead, collector, registry, metadata=(), trace=None, *, indexes=True):
    """Metadata reuse first, then at most two actual official indexes/feeds."""
    trace = trace if trace is not None else []
    cache = getattr(collector,'_official_news_indexes',None)
    if not isinstance(cache,dict):
        cache = {}; collector._official_news_indexes = cache
    ranked, seen = [], set()
    terms = subject_terms(lead['payload']['title'])
    def add(url, title, summary, edge, priority):
        source = source_for(url, registry)
        if (not source or not source_subject_matches(lead, source) or url in seen
                or not candidate_related(lead,title,summary,url,publisher=source['name'])):
            return
        seen.add(url)
        score = len(terms & subject_terms(title + ' ' + summary))
        ranked.append((priority, score, url, edge))

    for item in metadata:
        p = item.get('payload', {})
        if not isinstance(p,dict) or not isinstance(p.get('title'),str): continue
        summary=p.get('summary') or ''
        if not isinstance(summary,str): continue
        source = source_for(item.get('url'), registry)
        if (not source or source['id'] != item.get('source_id') or p.get('source_kind') != 'primary'
                or item.get('id') != stable_id(item['url'])):
            continue
        record = {'id':item['id'], 'source_id':item['source_id'], 'url':item['url'],
                  'title':p.get('title',''), 'published_at':p.get('published_at'),
                  'summary':summary[:1000]}
        if not candidate_related(lead,record['title'],record['summary'],item['url'],publisher=source['name']): continue
        date=iso_date(record['published_at'])
        if date:
            gap=datetime.fromisoformat(lead['payload']['published_at'])-datetime.fromisoformat(date)
            if gap > timedelta(days=30) or gap < -timedelta(days=1):
                trace.append({'stage':'official_catalog','url':item['url'],'status':'publication_date_mismatch'})
                continue
        add(item['url'],record['title'],record['summary'],
            {'method':'official_catalog','from_url':source['website'],'to_url':item['url'],
             'catalog_item':record,'catalog_hash':artifact_hash(record)}, 2)
    if ranked:
        trace.append({'stage':'official_catalog','status':'candidates','count':len(ranked)})
    text = lead['payload']['title'] + ' ' + lead['payload']['content'][:14000]
    sources = [s for s in registry.values() if source_subject_matches(lead, s) and s.get('discovery_triggers')
               and all(re.search(p,text,re.I) for p in s['discovery_triggers'])]
    index_count = 0 if indexes else MAX_INDEXES
    for source in sources:
        for endpoint, kind in [(u,'index') for u in source.get('indexes', [])] + [(u,'feed') for u in source.get('feeds', [])]:
            if index_count >= MAX_INDEXES: break
            index_count += 1
            try:
                if endpoint not in cache:
                    try: cache[endpoint] = collector.fetch(endpoint,source,editorial=True)
                    except Exception as error: cache[endpoint] = error
                if isinstance(cache[endpoint],Exception): raise cache[endpoint]
                status,_,body,final = cache[endpoint]
                if status != 200 or final != endpoint:
                    raise ValueError('official_index_inaccessible_or_redirected')
                digest = hashlib.sha256(body.encode()).hexdigest()
                before = len(ranked)
                if kind == 'feed' or source.get('index_format') == 'rss':
                    rows = [(r['url'],r['title'],r['summary']) for r in parse_feed(body,source)[:50]]
                else:
                    parser = IndexLinks();parser.feed(body)
                    rows = [(urljoin(final,u),title,'') for u,title in parser.links[:1000]]
                for raw,title,summary in rows:
                    try:
                        url = index_link(final, raw, source)
                        if urlsplit(url).hostname != urlsplit(source['website']).hostname: continue
                        if urlsplit(url).path.lower().endswith('.pdf'):
                            if source_for(url,registry) and candidate_related(lead,title,summary,url):
                                trace.append({'stage':'official_document','url':url,'status':'needs_pdf_extraction'})
                            continue
                        add(url,title,summary,{'method':'official_discovery_index','from_url':endpoint,
                            'to_url':url,'index_hash':digest,'link_title':title,'link_summary':summary[:1000]},1)
                    except (TypeError,ValueError): continue
                trace.append({'stage':'official_'+kind,'url':endpoint,'status':'searched','candidates':len(ranked)-before})
            except Exception as error:
                trace.append({'stage':'official_'+kind,'url':endpoint,'status':'blocked',
                              'reason':type(error).__name__+':'+str(error)[:120]})
        if index_count >= MAX_INDEXES: break
    ranked.sort(key=lambda row:(-row[0],-row[1],row[2]))
    if not sources and not ranked:
        trace.append({'stage':'official_discovery','status':'no_matching_declared_authority'})
    return [(url,edge) for _,_,url,edge in ranked[:MAX_CANDIDATES]]


def valid_edge(edge, lead, registry):
    try:
        source = source_for(edge['to_url'],registry)
        if not source: return False
        if edge.get('method') == 'official_discovery_index':
            return (set(edge)=={'method','from_url','to_url','index_hash','link_title','link_summary'}
                and edge['from_url'] in source.get('indexes',[])+source.get('feeds',[])
                and bool(re.fullmatch(r'[a-f0-9]{64}',edge['index_hash']))
                and isinstance(edge['link_title'],str) and len(edge['link_title'])<=300
                and isinstance(edge['link_summary'],str) and len(edge['link_summary'])<=1000
                and candidate_related(lead,edge['link_title'],edge['link_summary'],edge['to_url']))
        if edge.get('method') == 'official_catalog':
            record=edge['catalog_item']
            return (set(edge)=={'method','from_url','to_url','catalog_item','catalog_hash'}
                and set(record)=={'id','source_id','url','title','published_at','summary'}
                and edge['from_url']==source['website'] and record['url']==edge['to_url']
                and record['id']==stable_id(edge['to_url']) and record['source_id']==source['id']
                and artifact_hash(record)==edge['catalog_hash']
                and candidate_related(lead,record['title'],record['summary'],edge['to_url']))
    except (KeyError,TypeError,ValueError): return False
    return False
