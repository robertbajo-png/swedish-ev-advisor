"""Exact XPENG Swiss importer newsroom articles, not the global site's home metadata."""
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

from news_http import canonical_url, MAX_BYTES


VOID = {'meta', 'link', 'br', 'hr', 'img', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track'}


class ReleaseText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.blocks, self.headings = [], [], []
        self.articles = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get('class', '').split())
        in_main = any(t == 'main' for t, _, _ in self.stack)
        in_article = any(t == 'article' for t, _, _ in self.stack)
        if tag == 'article' and in_main:
            self.articles += 1
        active = bool(in_main and in_article and tag == 'div' and 'article-block__p' in classes)
        if active and any(body for _, body, _ in self.stack):
            raise ValueError('xpeng_nested_narrative_blocks')
        if tag == 'h1' and in_main and in_article:
            self.headings.append([])
        if active:
            self.blocks.append([])
        skip = tag in {'script', 'style', 'noscript', 'nav', 'footer', 'header', 'aside', 'figure', 'table'}
        skip = skip or bool(classes & {'c-sideline-actions', 'boilerplate-block', 'boilerplate-text', 'related-news'})
        skip = skip or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
        skip = skip or bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)\b', attrs.get('style', ''), re.I))
        if tag not in VOID:
            self.stack.append((tag, active, skip))

    def handle_data(self, text):
        if any(skip for _, _, skip in self.stack):
            return
        if any(tag == 'h1' for tag, _, _ in self.stack) and self.headings:
            self.headings[-1].append(text)
        if any(body for _, body, _ in self.stack):
            self.blocks[-1].append(text)

    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def document(html, url):
    from news_pressrooms import document as scoped_document, PressDocument
    if len(html.encode()) > MAX_BYTES:
        raise ValueError('xpeng_document_too_large')
    parsed = urlsplit(canonical_url(url))
    if (url != canonical_url(url) or parsed.hostname != 'xpengswitzerland.pr.co' or parsed.query
            or not re.fullmatch(r'/[0-9]{6}-[a-z0-9-]+/', parsed.path)):
        raise ValueError('xpeng_article_outside_authority')
    metadata = scoped_document(html, url=url, body_region='main', exclude_tables=True)
    state = PressDocument(); state.feed(html)
    def articles(node):
        if isinstance(node, dict):
            kinds = node.get('@type', [])
            if isinstance(kinds, (str, list)) and 'NewsArticle' in ([kinds] if isinstance(kinds, str) else kinds):
                yield node
            for child in node.values():
                yield from articles(child)
        elif isinstance(node, list):
            for child in node:
                yield from articles(child)
    records = [article for node in state.jsonld for article in articles(node)]
    if (len(records) != 1 or records[0].get('url') != url
            or not isinstance(records[0].get('publisher'), dict)
            or records[0]['publisher'].get('name') != 'XPENG'):
        raise ValueError('xpeng_article_metadata_ambiguous')
    text = ReleaseText(); text.feed(html)
    flat = lambda parts: ' '.join(' '.join(parts).split())
    title = metadata['title']
    headline = records[0].get('headline')
    if (text.articles != 1 or len(text.headings) != 1 or flat(text.headings[0]) != flat([title])
            or not isinstance(headline, str) or flat([unescape(headline)]) != flat([title])):
        raise ValueError('xpeng_article_heading_conflict')
    body = ' '.join(flat(block) for block in text.blocks if flat(block))
    if not 300 <= len(body.encode()) <= 45000:
        raise ValueError('xpeng_narrative_missing_or_oversized')
    return {**metadata, 'body': body}
