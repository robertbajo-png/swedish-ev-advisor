"""Discover exact-model photo candidates. Never approve or publish an image."""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from verify_public_images import normalize_image_key
from audit_image_rights import LICENSES

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'data/local/release-data/licensed-images'
API = 'https://commons.wikimedia.org/w/api.php'
QUERIES = {
    'Audi|A6 E-Tron': '"Audi A6" "e-tron" Sportback front',
    'Audi|Q4 E-Tron': '"Audi Q4" "e-tron" front -Sportback',
    'Audi|Q6 E-Tron': '"Audi Q6" "e-tron" front',
    'BMW|i4': '"BMW i4" front -Polizei',
    'BMW|i5': '"BMW i5" G60 front -Touring',
    'BMW|iX1': '"BMW iX1" front',
    'BMW|iX3': '"BMW iX3" NA5',
    'Cupra|Born': '"Cupra Born" front',
    'Ford|Explorer': '"Ford Explorer" electric front',
    'Kia|Ev3': '"Kia EV3" front',
    'Kia|Ev4': '"Kia EV4" hatchback front',
    'Kia|Ev5': '"Kia EV5" front',
    'Kia|Ev6': '"Kia EV6" 2025 front',
    'Kia|Ev9': '"Kia EV9" front',
    'Mazda|6E': '"Mazda6e" front',
    'Mercedes-Benz|Cla': '"Mercedes-Benz CLA" C174',
    'Mercedes-Benz|Eqa': '"Mercedes-Benz EQA" front',
    'Polestar|2': '"Polestar 2" 2024 front',
    'Polestar|4': '"Polestar 4" front',
    'Renault|5': '"Renault 5" "E-Tech" front',
    'Skoda|Elroq': '"Skoda Elroq" front',
    'Skoda|Enyaq': '"Skoda Enyaq" 2025 front',
    'Tesla|Model 3': '"Tesla Model 3" Highland front',
    'Tesla|Model Y': '"Tesla Model Y" Juniper front',
    'Toyota|bZ4X': '"Toyota bZ4X" front',
    'Volkswagen|Id.3': '"Volkswagen ID.3" Neo',
    'Volkswagen|Id.4': '"Volkswagen ID.4" front',
    'Volvo|Es90': '"Volvo ES90" front',
    'Volvo|Ex30': '"Volvo EX30" front',
    'Zeekr|7X': '"Zeekr 7X" front',
}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = PlainText()
    parser.feed(str(value or ''))
    return ' '.join(' '.join(parser.parts).split())


def image_url(value):
    url = urlsplit(value or '')
    if url.scheme != 'https' or url.hostname not in ('upload.wikimedia.org', 'thumb.wikimedia.org') or url.username or url.password:
        raise ValueError('Unapproved image host')
    return urlunsplit((url.scheme, url.netloc, url.path, '', ''))


def canonical_license(license_id, value):
    expected = LICENSES.get(license_id)
    url = urlsplit(value or '')
    if (expected and url.scheme in ('http', 'https') and url.hostname == 'creativecommons.org'
            and not url.username and not url.password and not url.query and not url.fragment
            and url.path.rstrip('/') in (urlsplit(expected).path.rstrip('/'), urlsplit(expected).path.rstrip('/') + '/deed.en')):
        return expected
    return None


def discover(query, limit):
    params = {'action': 'query', 'generator': 'search', 'gsrsearch': 'filetype:bitmap ' + query,
              'gsrnamespace': '6', 'gsrlimit': str(limit), 'prop': 'imageinfo|info',
              'iiprop': 'url|extmetadata|size|sha1', 'iiurlwidth': '1280', 'format': 'json', 'maxlag': '5'}
    request = Request(API + '?' + urlencode(params), headers={
        'User-Agent': 'Elbilsagenten/0.1 (kontakt@boleoai.se; licensed model photo discovery)'})
    with urlopen(request, timeout=20) as response:
        body = response.read(3_000_001)
        if len(body) > 3_000_000:
            raise ValueError('Metadata response too large')
    data = json.loads(body)
    if data.get('error'):
        raise ValueError('Commons API rejected discovery')
    candidates = []
    for page in sorted(data.get('query', {}).get('pages', {}).values(), key=lambda p: p.get('index', 999)):
        info = page.get('imageinfo', [{}])[0]
        meta = info.get('extmetadata', {})
        field = lambda name: plain(meta.get(name, {}).get('value'))
        license_url = field('LicenseUrl').rstrip('/') + '/'
        license_id = field('LicenseShortName').replace(' ', '-').upper()
        license_parts = urlsplit(license_url)
        if (license_id == 'CC0' and license_parts.hostname == 'creativecommons.org'
                and license_parts.path.rstrip('/') in ('/publicdomain/zero/1.0', '/publicdomain/zero/1.0/deed.en')):
            license_id = 'CC0-1.0'
            license_url = 'https://creativecommons.org/publicdomain/zero/1.0/'
        normalized_license = canonical_license(license_id, license_url)
        approved = normalized_license is not None
        license_url = normalized_license or license_url
        try:
            asset = image_url(info.get('thumburl') or info.get('url'))
        except ValueError:
            continue
        candidates.append({'status': 'candidate_not_reviewed', 'title': page['title'],
            'asset_url': asset, 'original_url': image_url(info.get('url')),
            'source_url': info.get('descriptionurl'),
            'evidence_url': 'https://commons.wikimedia.org/w/index.php?' + urlencode({'title': page['title'], 'oldid': page['lastrevid']}),
            'revision': page['lastrevid'], 'source_sha1': info.get('sha1'),
            'license_id': license_id, 'license_url': license_url, 'license_eligible': approved,
            'license_statement': field('UsageTerms'), 'author': field('Artist'),
            'description': field('ImageDescription'), 'categories': field('Categories'),
            'source_credit': field('Credit'), 'restrictions': field('Restrictions'),
            'width': info.get('width'), 'height': info.get('height')})
    return {'query': query, 'fetched_at': datetime.now(timezone.utc).isoformat(),
            'api_response_sha256': hashlib.sha256(body).hexdigest(), 'candidates': candidates}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', help='Exact brand|model key; omitted means all current models')
    parser.add_argument('--query', help='Refine research for one exact canonical model; never an approval')
    parser.add_argument('--limit', type=int, default=5, choices=range(1, 11))
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'public/data/public_ev_variants.json').read_text(encoding='utf-8'))
    models = sorted({r['brand'] + '|' + r['model'] for r in catalog['records']})
    if args.model:
        if args.model not in models:
            raise ValueError('Model outside canonical catalog')
        models = [args.model]
    elif args.query:
        raise ValueError('A refined query requires one exact model')
    LOCAL.mkdir(parents=True, exist_ok=True)
    rows = []
    for model in models:
        brand, name = model.split('|', 1)
        key = normalize_image_key(brand) + '|' + normalize_image_key(name)
        try:
            result = {'model_key': key, 'brand': brand, 'model': name, **discover(args.query or QUERIES.get(model, model.replace('|', ' ') + ' front'), args.limit)}
            (LOCAL / (key.replace('|', '-') + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            rows.append(result)
            print(json.dumps({'model': model, 'candidates': [
                {'title': c['title'], 'license': c['license_id'], 'eligible': c['license_eligible']}
                for c in result['candidates']]}, ensure_ascii=True), flush=True)
        except Exception as error:
            result = {'model_key': key, 'status': 'discovery_failed', 'reason': type(error).__name__}
            rows.append(result)
            print(json.dumps(result), flush=True)
        time.sleep(0.25)
    if not args.model:
        (LOCAL / 'discovery.json').write_text(json.dumps({'models': rows, 'publications': 0, 'database_writes': 0}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
