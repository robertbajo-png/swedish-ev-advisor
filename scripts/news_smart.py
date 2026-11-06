"""Exact smart European PR.co releases, with original identity and qualifications."""
import re
from html import unescape
from urllib.parse import urlsplit

from news_http import canonical_url, MAX_BYTES
from news_xpeng import ReleaseText


def document(html, url):
    from news_pressrooms import document as scoped_document, PressDocument
    parsed = urlsplit(canonical_url(url))
    if (len(html.encode()) > MAX_BYTES or url != canonical_url(url)
            or parsed.hostname != 'media.smart.com' or parsed.query
            or not re.fullmatch(r'/en-CEU/[0-9]{6}-[a-z0-9-]+/', parsed.path)):
        raise ValueError('smart_article_outside_authority')
    metadata = scoped_document(html, url=url, body_region='main', exclude_tables=True)
    state = PressDocument(); state.feed(html)
    def articles(node):
        if isinstance(node, dict):
            kinds = node.get('@type', [])
            if isinstance(kinds, (str, list)) and 'NewsArticle' in ([kinds] if isinstance(kinds, str) else kinds):
                yield node
            for child in node.values(): yield from articles(child)
        elif isinstance(node, list):
            for child in node: yield from articles(child)
    records = [record for node in state.jsonld for record in articles(node)]
    if (len(records) != 1 or records[0].get('url') != url
            or not isinstance(records[0].get('publisher'), dict)
            or records[0]['publisher'].get('name') != 'smart'):
        raise ValueError('smart_article_metadata_ambiguous')
    text = ReleaseText(); text.feed(html)
    flat = lambda parts: ' '.join(' '.join(parts).split())
    title = metadata['title']
    if (text.articles != 1 or len(text.headings) != 1 or flat(text.headings[0]) != flat([title])
            or not isinstance(records[0].get('headline'), str)
            or flat([unescape(records[0]['headline'])]) != flat([title])):
        raise ValueError('smart_article_heading_conflict')
    body = ' '.join(flat(block) for block in text.blocks if flat(block))
    if not 300 <= len(body.encode()) <= 45000:
        raise ValueError('smart_narrative_missing_or_oversized')
    if 'homologation' in metadata['body'].lower() and 'homologation' not in body.lower():
        raise ValueError('smart_qualification_not_in_narrative')
    return {**metadata, 'body': body}
