"""Electra's English operator releases; no general canonical/date fallback."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

from news_http import MAX_BYTES, canonical_url, iso_date
from news_xpeng import VOID


class ReleaseText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.headings, self.dates, self.blocks = [], [], [], []
        self.mains = self.narratives = 0
        self.await_date = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get('class', '').split())
        main = tag == 'main' or any(t == 'main' for t, _, _ in self.stack)
        if tag == 'main': self.mains += 1
        prose = main and tag == 'div' and 'prose' in classes
        if prose:
            if any(kind == 'prose' for _, kind, _ in self.stack):
                raise ValueError('electra_nested_narrative')
            self.narratives += 1
        kind = 'prose' if prose else None
        if tag == 'h1' and main:
            self.headings.append([]); kind = 'heading'
        if tag == 'p' and main and self.await_date:
            self.await_date = False
            if {'body-sm', 'text-secondary-text'} <= classes:
                self.dates.append([]); kind = 'date'
        if (tag in {'p', 'li', 'h2', 'h3'} and any(k == 'prose' for _, k, _ in self.stack)
                and not any(k == 'block' for _, k, _ in self.stack)):
            self.blocks.append([]); kind = 'block'
        skip = tag in {'script', 'style', 'noscript', 'nav', 'footer', 'header', 'aside', 'figure', 'table'}
        skip = skip or 'hidden' in a or a.get('aria-hidden') == 'true'
        skip = skip or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', a.get('style', ''), re.I))
        if tag not in VOID: self.stack.append((tag, kind, skip))

    def handle_data(self, text):
        if any(skip for _, _, skip in self.stack): return
        for kind, target in [('heading', self.headings), ('date', self.dates), ('block', self.blocks)]:
            if target and any(k == kind for _, k, _ in self.stack): target[-1].append(text)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                if self.stack[i][1] == 'heading': self.await_date = True
                del self.stack[i:]
                break


def document(html, url):
    from news_pressrooms import PressDocument
    if len(html.encode()) > MAX_BYTES: raise ValueError('electra_document_too_large')
    parsed = urlsplit(canonical_url(url))
    if (url != canonical_url(url) or parsed.hostname != 'www.go-electra.com' or parsed.query
            or not re.fullmatch(r'/en/newsroom/(?!cat-|all-categories/)[a-z][a-z0-9-]+/', parsed.path)):
        raise ValueError('electra_article_outside_authority')
    state = PressDocument(); state.feed(html)
    # Verified Gatsby bug: /en/ is prepended to an already localized /en/ path.
    # Accept ONLY that exact duplicate for the requested slug, never another locale/host.
    duplicate = 'https://www.go-electra.com/en/' + parsed.path
    if len(state.canonicals) != 1 or state.canonicals[0] not in {url, duplicate}:
        raise ValueError('electra_canonical_conflict')
    websites = [v for v in state.jsonld if isinstance(v, dict) and v.get('@type') == 'WebSite']
    pages = [v for v in state.jsonld if isinstance(v, dict) and v.get('@type') == 'WebPage']
    if (len(websites) != 1 or websites[0].get('name') != 'Electra'
            or websites[0].get('url') != state.canonicals[0] or len(pages) != 1):
        raise ValueError('electra_structured_identity_conflict')
    text = ReleaseText(); text.feed(html)
    flat = lambda parts: ' '.join(' '.join(parts).split())
    title = state.meta.get('og:title', '').strip()
    if (text.mains != 1 or text.narratives != 1 or len(text.headings) != 1
            or not title or flat(text.headings[0]) != title or pages[0].get('name') != title):
        raise ValueError('electra_heading_or_narrative_conflict')
    if len(text.dates) != 1 or not re.fullmatch(r'[A-Z][a-z]{2} [1-9][0-9]?, 20[0-9]{2}', flat(text.dates[0])):
        raise ValueError('electra_original_date_missing')
    try:
        day = datetime.strptime(flat(text.dates[0]), '%b %d, %Y').replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError('electra_original_date_invalid') from exc
    parts = []
    for block in text.blocks:
        value = flat(block)
        if value in {'Electra Contacts:', 'Mercedes-Benz Contacts:', 'About Electra', 'About Mercedes-Benz'}: break
        if value: parts.append(value)
    # Preserve paragraph boundaries: a footnote must not merge into a quoted speaker's byline.
    body = '\n'.join(parts)
    dateline = re.search(r'\bParis, ([1-9][0-9]? [A-Z][a-z]+ 20[0-9]{2})\b', body)
    if not dateline or datetime.strptime(dateline[1], '%d %B %Y').date() != day.date():
        raise ValueError('electra_visible_date_conflict')
    for key in ('article:published_time', 'datePublished'):
        if state.meta.get(key) and (not iso_date(state.meta[key])
                or iso_date(state.meta[key])[:10] != day.date().isoformat()):
            raise ValueError('electra_original_date_conflict')
    if not 300 <= len(body.encode()) <= 45000: raise ValueError('electra_narrative_incomplete')
    return {'title': title, 'published_at': day.isoformat(), 'summary': state.meta.get('description', ''), 'body': body}
