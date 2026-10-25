import json
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_news(path=None):
    path = Path(path or ROOT / "public/data/news_articles.json")
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8")).get("records", [])
    return [r for r in rows if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", r.get("slug", "")) and r.get("published_at")]


def news_paths():
    return ["/nyheter", *["/nyheter/" + r["slug"] for r in load_news()]]


def news_routes(site):
    rows = load_news()
    result = [{"path": "/nyheter", "title": "Elbilsnyheter – modeller, teknik och marknad | Elbilsagenten",
               "description": "Internationella elbilsnyheter med svenska perspektiv, tydliga källor och koppling till ditt nästa bilval.",
               "json_ld": {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Elbilsnyheter", "url": site + "/nyheter"},
               "body_html": '<section><h1>Elbilsnyheter</h1>' + ''.join(f'<article><h2><a href="/nyheter/{escape(r["slug"])}">{escape(r["title"])}</a></h2><p>{escape(r["intro"])}</p></article>' for r in rows) + '</section>'}]
    for r in rows:
        path = "/nyheter/" + r["slug"]
        text = [r["intro"], *[p["text"] for p in r["paragraphs"]]]
        sources = [s for s in r["sources"] if s["url"].startswith("https://")]
        body = f'<article><h1>{escape(r["title"])}</h1><time datetime="{escape(r["published_at"])}">{escape(r["published_at"][:10])}</time>'
        body += ''.join(f'<p>{escape(p)}</p>' for p in text)
        body += '<h2>Källor</h2><ul>' + ''.join(f'<li><a href="{escape(s["url"], quote=True)}">{escape(s["publisher"])}</a></li>' for s in sources) + '</ul></article>'
        result.append({"path": path, "title": r["title"] + " | Elbilsagenten", "description": r["intro"], "body_html": body,
                       "json_ld": {"@context": "https://schema.org", "@type": "NewsArticle", "headline": r["title"], "description": r["intro"],
                                   "datePublished": r["published_at"], "inLanguage": "sv-SE", "url": site + path,
                                   "author": {"@type": "Organization", "name": "Elbilsagenten"},
                                   "publisher": {"@type": "Organization", "name": "Elbilsagenten"},
                                   "citation": [s["url"] for s in sources], "articleBody": "\n\n".join(text)}})
    return result
