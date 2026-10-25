"""Render a private test artifact, never a website asset or publication command."""
from html import escape
from pathlib import Path

from news_http import canonical_url
from news_store import NewsStore, EDITORIAL_POLICY, artifact_hash
from news_editorial import EDITORIAL_RECIPE

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / 'data/local/news-pressroom-smoke-2026-10-21.sqlite'
OUTPUT = ROOT / 'data/local/release-data/news-smoke/article-preview.html'


def render(article, approved=False, offline_reference=False):
    p = article['payload']
    approved = approved and article['status'] == 'published' and not offline_reference
    checks = article.get('checks', [])
    validated = (not offline_reference and article['status'] == 'draft' and article.get('artifact_hash') == artifact_hash(p)
                 and p.get('editorial_recipe') == EDITORIAL_RECIPE and len(checks) == 3
                 and {c.get('kind') for c in checks} == {'evidence', 'editorial', 'originality'}
                 and all(c.get('passed') is True and c.get('artifact_hash') == article['artifact_hash']
                         and c.get('payload', {}).get('audit_performed') is True
                         and c.get('payload', {}).get('policy_version') == EDITORIAL_POLICY for c in checks))
    status = ('Offline-redigerad referens' if offline_reference else
              'Godk&auml;nd testartikel' if approved else
              'Validerat privat utkast' if validated else 'Utkast i karant&auml;n')
    notice = ('Offline-redigerad text. Inte slutgranskad eller publicerad.' if offline_reference else
              'Isolerat nyhetsmotortest. Inte publicerad p&aring; sajten.')
    paragraphs = ''.join('<p>' + escape(row['text']) + '</p>' for row in p['paragraphs'])
    sources = ''.join('<li><a href="' + escape(canonical_url(s['url']), quote=True) +
                      '" target="_blank" rel="noopener noreferrer">' + escape(s['publisher']) + '</a></li>'
                      for s in p['sources'])
    return f'''<!doctype html>
<html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{escape(p['title'])}</title>
<style>body{{margin:0;background:#f7f7f4;color:#171b1c;font:18px/1.65 system-ui,sans-serif}}
main{{max-width:760px;margin:auto;padding:48px 24px}}header{{border-bottom:1px solid #d4dbd8;padding-bottom:24px}}
h1{{font-size:36px;line-height:1.15;letter-spacing:0}}h2{{font-size:22px}}.intro{{font-size:21px}}
.status,a{{color:#245e5b}}.notice{{font-size:15px}}@media(max-width:520px){{h1{{font-size:30px}}main{{padding:24px 20px}}}}
</style><main><header><strong>Elbilsguiden</strong><p class="status">{status}</p>
<p class="notice">{notice}</p></header>
<article><h1>{escape(p['title'])}</h1><p class="intro">{escape(p['intro'])}</p>{paragraphs}</article>
<section><h2>K&auml;llor</h2><ul>{sources}</ul></section></main></html>'''


def main():
    store = NewsStore(DATABASE)
    try:
        articles = store.rows('news_articles')
        if not articles:
            raise SystemExit('No article available for preview')
        article = next((a for a in articles if a['status'] == 'published'), articles[-1])
        checks = [c for c in store.rows('news_quality_checks') if c['article_id'] == article['id']
                  and c['artifact_hash'] == article['artifact_hash']]
        approved = article['status'] == 'published' and {c['kind'] for c in checks if c['passed']} == {'evidence', 'editorial', 'originality'}
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(render(article, approved), encoding='utf-8')
        print(str(OUTPUT))
    finally:
        store.close()


if __name__ == '__main__':
    main()
