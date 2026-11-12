"""Explicit BMW PressPage adapter; old PressClub redirects are not followed."""
from datetime import datetime
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

from news_http import canonical_url, iso_date, MAX_BYTES
from news_xpeng import VOID


class Narrative(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.blocks, self.headings = [], [], []
        self.dates = {'pp_date_day': [], 'pp_date_month': [], 'pp_date_year': []}
        self.mains = self.date_regions = self.narratives = 0
        self.chrome_tables = self.unknown_tables = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get('class', '').split())
        if tag == 'main' and a.get('id') == 'pp-main': self.mains += 1
        main = tag == 'main' and a.get('id') == 'pp-main' or any(k == 'main' for _, k, _ in self.stack)
        kind = 'main' if tag == 'main' and a.get('id') == 'pp-main' else None
        if tag == 'aside' and 'pp-side-column' in classes:
            kind = 'sidebar'
        if tag == 'table':
            known_chrome = (bool({'table_flags', 'contact_text'} & classes) or a.get('id') == 'table_shareus')
            if known_chrome and any(k == 'sidebar' for _, k, _ in self.stack):
                self.chrome_tables += 1
            else:
                self.unknown_tables += 1
        if 'div_date_location' in classes:
            self.date_regions += 1; kind = 'date_region'
        if main and 'ppmodule_textblock' in classes:
            self.narratives += 1; kind = 'narrative'
        if main and tag == 'h1':
            self.headings.append([]); kind = 'heading'
        if any(k == 'date_region' for _, k, _ in self.stack):
            for name in self.dates:
                if name in classes:
                    self.dates[name].append([]); kind = name
        if tag in ('p', 'li', 'h2', 'h3', 'h4') and any(k == 'narrative' for _, k, _ in self.stack):
            if not any(k == 'block' for _, k, _ in self.stack):
                self.blocks.append([]); kind = 'block'
        skip = (tag in ('script', 'style', 'noscript', 'nav', 'footer', 'aside', 'figure', 'table')
                or 'text_boilerplate' in classes or 'hidden' in a or a.get('aria-hidden') == 'true'
                or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', a.get('style', ''), re.I)))
        if tag not in VOID: self.stack.append((tag, kind, skip))

    def handle_data(self, text):
        if any(skip for _, _, skip in self.stack): return
        for kind, target in [('heading', self.headings), ('block', self.blocks), *self.dates.items()]:
            if target and any(k == kind for _, k, _ in self.stack): target[-1].append(text)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def document(html, url):
    from news_pressrooms import PressDocument
    from news_editorial import normalize
    from news_publisher_selection import model_identifiers
    p = urlsplit(canonical_url(url))
    if (len(html.encode()) > MAX_BYTES or url != canonical_url(url) or p.query
            or p.hostname != 'newsroom.bmwgroup.com' or not re.fullmatch(r'/global/[a-z0-9_-]+/', p.path)):
        raise ValueError('bmw_newsroom_article_outside_authority')
    state = PressDocument(); state.feed(html)
    if state.canonicals != [url]: raise ValueError('bmw_newsroom_canonical_conflict')
    articles = [a for a in state.jsonld if isinstance(a, dict) and a.get('@type') == 'Article']
    if len(articles) != 1: raise ValueError('bmw_newsroom_article_identity_missing')
    article = articles[0]
    title = state.meta.get('og:title', '').strip()
    if (not title or article.get('headline') != title
            or article.get('mainEntityOfPage', {}).get('@id') != url
            or article.get('publisher', {}).get('name') != 'GLOBAL'):
        raise ValueError('bmw_newsroom_structured_identity_conflict')
    text = Narrative(); text.feed(html)
    if text.unknown_tables: raise ValueError('bmw_newsroom_unvalidated_table')
    flat = lambda parts: ' '.join(' '.join(parts).split())
    if text.mains != 1 or text.date_regions != 1 or text.narratives < 1 or len(text.headings) != 1:
        raise ValueError('bmw_newsroom_narrative_missing_or_ambiguous')
    heading = flat(text.headings[0])
    def bmw_models(value):
        return {m for m in model_identifiers(value) if re.fullmatch(r'i(?:x)?[1-9][0-9]?|ix|im|x[1-9]|m[1-9]', m)}
    a, b = bmw_models(title), bmw_models(heading)
    if a or b:
        matches = bool(a and a == b)
    else:
        left, right = set(normalize(title).split()), set(normalize(heading).split())
        matches = len(left & right) >= 4 and len(left & right) / max(1, min(len(left), len(right))) >= .8
    if not matches: raise ValueError('bmw_newsroom_visible_heading_conflict')
    try:
        original = datetime.fromisoformat(article['datePublished'])
        if original.tzinfo is None: raise ValueError('timezone_required')
        if any(len(parts) != 1 for parts in text.dates.values()): raise ValueError('visible_date_missing')
        visible = datetime.strptime(' '.join(flat(text.dates[key][0]) for key in text.dates), '%d %B %Y')
        if visible.date() != original.date(): raise ValueError('visible_date_conflict')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('bmw_newsroom_original_date_conflict') from exc
    body = '\n'.join(value for parts in text.blocks if (value := flat(parts)))
    if not 300 <= len(body.encode()) <= 45000: raise ValueError('bmw_newsroom_narrative_incomplete')
    return {'title': title, 'published_at': iso_date(article['datePublished']),
            'summary': state.meta.get('description', ''), 'body': body,
            'excluded_chrome_tables': text.chrome_tables}


def discover(index_html, index_url, source, collector, limit, now=None):
    """Recent-release cards in the index sidebar are discovery, never article evidence."""
    from news_http import PageText, require_recent_publication
    from news_pressrooms import index_link
    class Cards(HTMLParser):
        def __init__(self):
            super().__init__(); self.links = []
        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == 'a' and 'pp-block-item-container' in a.get('class', '').split() and a.get('href'):
                self.links.append(a['href'])
    regular, cards = PageText(), Cards()
    regular.feed(index_html); cards.feed(index_html)
    urls = []
    for href in regular.links + cards.links:
        try:
            url = index_link(index_url, href, source)
            if re.fullmatch(source['article_path_pattern'], urlsplit(url).path) and url not in urls:
                urls.append(url)
        except ValueError:
            continue
    rows, errors = [], []
    for url in urls[:20]:
        try:
            status, _, html, final = collector.fetch(url, source, editorial=True)
            if status != 200 or final != url: raise ValueError('bmw_newsroom_article_redirected')
            doc = document(html, url)
            require_recent_publication(doc['published_at'], now)
            rows.append({'url': url, 'title': doc['title'], 'published_at': doc['published_at'],
                         'summary': doc['summary'] or doc['body'][:400]})
            if len(rows) >= limit: break
        except Exception as exc:
            errors.append({'url': url, 'reason': type(exc).__name__ + ':' + str(exc)[:130]})
    return rows, errors
