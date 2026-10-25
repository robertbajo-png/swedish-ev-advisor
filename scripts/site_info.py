import os
import re
import json
from html import escape
from pathlib import Path

SITE_NAME = 'Elbilsagenten'
INFO_PATHS = ['/kontakt', '/integritet']


def privacy_html():
    content = json.loads((Path(__file__).resolve().parents[1] / 'src/privacy-content.json').read_text(encoding='utf-8'))
    sections = ''.join('<section><h2>' + escape(section['title']) + '</h2>'
                       + ''.join('<p>' + escape(text) + '</p>' for text in section['paragraphs'])
                       + '</section>' for section in content['sections'])
    references = ''.join('<p><a href="' + escape(link['url'], quote=True) + '">'
                         + escape(link['label']) + '</a></p>' for link in content['references'])
    return '<p>Uppdaterad ' + escape(content['updated']) + '</p>' + sections + '<h2>Mer information</h2>' + references


def image_credits_html():
    content = json.loads((Path(__file__).resolve().parents[1] / 'src/image-rights.json').read_text(encoding='utf-8'))
    return '<section id="bildkallor"><h2>Bildkällor</h2>' + ''.join(
        '<p><a href="' + escape(asset['source_url'], quote=True) + '">' + escape(asset['credit'])
        + '</a> · <a href="' + escape(asset['license_url'], quote=True) + '">' + escape(asset['license_id'])
        + '</a></p><p>' + escape(asset['changes']) + '</p>' for asset in content['assets']) + '</section>'


def info_routes(site_url, env=None):
    env = os.environ if env is None else env
    name = str(env.get('VITE_OPERATOR_NAME', '')).strip()
    email = str(env.get('VITE_CONTACT_EMAIL', '')).strip()
    configured = bool(2 <= len(name) <= 160 and not re.search(r'[\r\n]', name)
                      and len(email) <= 254 and re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', email)
                      and not re.search(r'@(?:example\.(?:com|org|net)|[^@]*\.(?:example|test))$', email, re.I))
    owner = (f'<p>{escape(name)}</p><p>{escape(email)}</p>' if configured else
             '<p>Förhandsversion. Ansvarig aktör och kontaktuppgifter fastställs före lansering.</p>')
    pages = [
        ('/kontakt', 'Kontakta oss.', 'Kontakta ansvarig aktör för Elbilsagenten med frågor, synpunkter och källbelagda rättelser av biluppgifter.',
         owner + '<h2>Hjälp oss rätta en uppgift</h2><p>Ange vilken bilvariant eller artikel det gäller och länka till aktuella tillverkaruppgifter.</p>' + image_credits_html(), 'ContactPage'),
        ('/integritet', 'Dina uppgifter.', 'Läs hur sökningar hanteras av Elbilsagenten och vilka tjänster som används för bilrådgivning, lagring och drift.',
         owner + privacy_html(), 'WebPage'),
    ]
    return [{'path': path, 'title': f'{title.rstrip(".")} | {SITE_NAME}', 'description': description,
             'json_ld': {'@context': 'https://schema.org', '@type': kind, 'name': title.rstrip('.'), 'url': site_url + path},
             'body_html': f'<article><h1>{escape(title)}</h1><p>{escape(description)}</p>{body}</article>'}
            for path, title, description, body, kind in pages]
