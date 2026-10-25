import os
import re
from html import escape

SITE_NAME = 'Elbilsagenten'
INFO_PATHS = ['/kontakt', '/integritet']


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
         owner + '<h2>Hjälp oss rätta en uppgift</h2><p>Ange vilken bilvariant eller artikel det gäller och länka till aktuella tillverkaruppgifter.</p>', 'ContactPage'),
        ('/integritet', 'Dina uppgifter.', 'Läs hur sökningar hanteras av Elbilsagenten och vilka tjänster som används för bilrådgivning, lagring och drift.',
         owner + '<h2>När du söker efter en bil</h2><p>När AI används skickas söktext och relevanta biluppgifter till OpenAI. Skriv inte känsliga personuppgifter i sökrutan.</p><h2>Drift och skydd</h2><p>Cloudflare levererar webbplatsen. Bil- och nyhetsuppgifter lagras i Supabase. Ansvar, lagringstider och leverantörsinställningar ska vara granskade före lansering.</p>', 'WebPage'),
    ]
    return [{'path': path, 'title': f'{title.rstrip(".")} | {SITE_NAME}', 'description': description,
             'json_ld': {'@context': 'https://schema.org', '@type': kind, 'name': title.rstrip('.'), 'url': site_url + path},
             'body_html': f'<article><h1>{escape(title)}</h1><p>{escape(description)}</p>{body}</article>'}
            for path, title, description, body, kind in pages]
