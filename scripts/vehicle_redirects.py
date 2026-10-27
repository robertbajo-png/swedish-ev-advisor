"""Build safe retired-variant redirects to the same model's filtered catalog."""
import html
import json
import re
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]


def redirect_routes(registry, public_rows):
    from generate_sitemap import public_variant_slug
    if registry.get('schema_version') != 1 or not isinstance(registry.get('redirects'), list):
        raise ValueError('invalid_redirect_registry')
    identities = {(row['brand'], row['model']) for row in public_rows
                  if row.get('validation_status') in ('published', 'published_reviewed')}
    active = {public_variant_slug(row) for row in public_rows}
    seen = set()
    routes = []
    for row in registry['redirects']:
        slug, brand, model = row.get('slug'), row.get('brand'), row.get('model')
        if (not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug)
                or slug in seen or slug in active or (brand, model) not in identities
                or not isinstance(brand, str) or not isinstance(model, str)
                or not brand.strip() or not model.strip() or len(brand) > 60 or len(model) > 80
                or re.search(r'[\x00-\x1f<>|]', brand + model)):
            raise ValueError('unsafe_or_unresolved_model_redirect')
        seen.add(slug)
        routes.append(('/bilar/' + slug, '/bilar?' + urlencode({'brand': brand, 'query': model})))
    return routes


def write_vehicle_redirects(dist, public_rows, registry=None):
    registry = registry if registry is not None else json.loads((ROOT / 'src/vehicle-redirects.json').read_text(encoding='utf-8'))
    routes = redirect_routes(registry, public_rows)
    # Own only the marked block; preserve any unrelated deployment redirects.
    path = dist / '_redirects'
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    begin, end = '# BEGIN RETIRED VEHICLES', '# END RETIRED VEHICLES'
    existing = re.sub(re.escape(begin) + r'.*?' + re.escape(end) + r'\n?', '', existing, flags=re.S)
    lines = [begin]
    for old, target in routes:
        lines.extend([f'{old} {target} 301', f'{old}/ {target} 301'])
        folder = dist / old.lstrip('/')
        folder.mkdir(parents=True, exist_ok=True)
        escaped = html.escape(target, quote=True)
        (folder / 'index.html').write_text('<!doctype html><html lang="sv"><head><meta charset="utf-8">'
            '<meta name="robots" content="noindex"><meta http-equiv="refresh" content="0;url=' + escaped + '">'
            '<title>Se aktuella versioner | Elbilsagenten</title></head><body><a href="' + escaped + '">'
            'Se aktuella versioner</a></body></html>', encoding='utf-8')
    path.write_text(existing.rstrip() + ('\n' if existing.strip() else '') + '\n'.join([*lines, end]) + '\n', encoding='utf-8')
    return len(routes)
