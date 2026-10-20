"""Read-only source audit. Fetching a page never verifies or publishes its facts."""
import argparse
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = 'SwedishEVAdvisor/0.1'
MAX_BYTES = 8 * 1024 * 1024
RULES = json.loads((ROOT / 'data/canonical/brand_source_resolver_rules.json').read_text(encoding='utf-8'))


def normalized(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value or ''))).strip().casefold()


def allowed_url(url, brands):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        domains = {domain.lower() for brand in brands for name, rule in RULES.items()
                   if name.casefold() == brand.casefold() for domain in rule.get('accepted_domains', [])}
        if not any(parsed.hostname == domain or parsed.hostname.endswith('.' + domain) for domain in domains):
            return False
        prefixes = {'tesla.com': ('/sv_se/',), 'volvocars.com': ('/se/',), 'polestar.com': ('/se/',),
                    'kia.com': ('/se/',), 'zeekr.eu': ('/sv-se/', '/se-se/')}
        for domain, paths in prefixes.items():
            if parsed.hostname == domain or parsed.hostname.endswith('.' + domain):
                return parsed.path.lower().startswith(paths)
        return True
    except (ValueError, AttributeError):
        return False


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def source_text(body, content_type):
    if 'pdf' in content_type or body.startswith(b'%PDF'):
        from pypdf import PdfReader
        return '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(body)).pages).strip()
    if 'html' not in content_type:
        raise ValueError('unsupported_content_type')
    parser = TextParser()
    parser.feed(body.decode('utf-8', errors='replace'))
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SourceFetcher:
    def __init__(self, timeout=10):
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())
        self.robots = {}

    def robots_allowed(self, url):
        parsed = urlsplit(url)
        origin = f'{parsed.scheme}://{parsed.netloc}'
        if origin not in self.robots:
            parser = RobotFileParser(origin + '/robots.txt')
            try:
                with self.opener.open(Request(origin + '/robots.txt', headers={'User-Agent': USER_AGENT}), timeout=self.timeout) as response:
                    data = response.read(512001)
                    if len(data) > 512000:
                        raise ValueError('robots_too_large')
                    parser.parse(data.decode('utf-8', errors='replace').splitlines())
            except HTTPError as error:
                if error.code != 404:
                    self.robots[origin] = None
                else:
                    parser.parse([])
                    self.robots[origin] = parser
            except (URLError, OSError, ValueError):
                self.robots[origin] = None
            else:
                self.robots[origin] = parser
        parser = self.robots[origin]
        return parser is not None and parser.can_fetch(USER_AGENT, url)

    def fetch(self, url, brands):
        current = url
        for _ in range(4):
            if not allowed_url(current, brands):
                return {'status': 'rejected_domain_or_market', 'final_url': current}
            if not self.robots_allowed(current):
                return {'status': 'robots_denied_or_unavailable', 'final_url': current}
            try:
                with self.opener.open(Request(current, headers={'User-Agent': USER_AGENT, 'Accept-Language': 'sv-SE,sv;q=0.9'}), timeout=self.timeout) as response:
                    if response.headers.get('tdm-reservation') == '1':
                        return {'status': 'machine_reservation', 'final_url': current}
                    body = response.read(MAX_BYTES + 1)
                    if len(body) > MAX_BYTES:
                        return {'status': 'source_too_large', 'final_url': current}
                    content_type = response.headers.get('content-type', '').lower()
                    text = source_text(body, content_type)
                    if re.search(r'<meta[^>]+name=["\']tdm-reservation["\'][^>]+content=["\']1["\']', body[:100000].decode('utf-8', errors='ignore'), re.I):
                        return {'status': 'machine_reservation', 'final_url': current}
                    return {'status': 'reachable', 'final_url': current, 'http_status': response.status,
                            'content_hash': hashlib.sha256(body).hexdigest(), 'text_hash': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                            'text': text, 'content_type': content_type}
            except HTTPError as error:
                if error.code in (301, 302, 303, 307, 308) and error.headers.get('Location'):
                    current = urljoin(current, error.headers['Location'])
                    continue
                return {'status': 'http_error', 'http_status': error.code, 'final_url': current}
            except (URLError, OSError, ValueError, ImportError):
                return {'status': 'fetch_or_parse_failed', 'final_url': current}
            except Exception:
                return {'status': 'parse_failed', 'final_url': current}
        return {'status': 'redirect_limit', 'final_url': current}


def assess_record(row, fetched, now=None):
    if fetched['status'] != 'reachable':
        return fetched['status']
    now = now or datetime.now(timezone.utc)
    valid_until = row.get('price_valid_until')
    if valid_until and valid_until[:10] < now.date().isoformat():
        return 'expired_price'
    dated = re.search(r'(20\d{2})[-_/](\d{2})[-_/](\d{2})', row['source_url'])
    if row.get('price_sek') is not None and dated:
        try:
            issued = datetime(*map(int, dated.groups()), tzinfo=timezone.utc)
            if (now - issued).days > 180:
                return 'dated_price_document_requires_current_source'
        except ValueError:
            return 'invalid_document_date'
    text = normalized(fetched.get('text'))
    if len(text) < 500:
        return 'rendered_content_required'
    variant = normalized(row.get('variant_name'))
    model = normalized(row.get('model'))
    if variant in (model, normalized(f"{row.get('brand')} {row.get('model')}")):
        return 'exact_variant_mapping_required'
    if variant not in text:
        return 'variant_scope_not_found'
    if re.search(r'prelimin[aä]r|certifiering v[aä]ntar', text):
        return 'preliminary_figures_require_reverification'
    quote = normalized(row.get('source_quote'))
    if not quote or quote not in text:
        return 'evidence_not_found'
    if row.get('source_hash') not in (fetched.get('content_hash'), fetched.get('text_hash')):
        return 'source_changed_evidence_present'
    return 'hash_and_evidence_unchanged'


def run(records, output_dir, fetcher=None, batch_size=5):
    fetcher = fetcher or SourceFetcher()
    groups = {}
    for row in records:
        groups.setdefault(row['source_url'], []).append(row)
    checked, jobs = [], []
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, (url, rows) in enumerate(sorted(groups.items())):
        result = fetcher.fetch(url, {row['brand'] for row in rows})
        text = result.pop('text', '')
        text_path = None
        if text:
            text_path = output_dir / (hashlib.sha256(url.encode()).hexdigest()[:16] + '.txt')
            text_path.write_text(text, encoding='utf-8')
        checked_at = datetime.now(timezone.utc).isoformat()
        item = {'source_url': url, 'brands': sorted({row['brand'] for row in rows}), 'checked_at': checked_at,
                'batch': index // batch_size + 1, 'variants': len(rows), **result}
        checked.append(item)
        for row in rows:
            reason = assess_record(row, {**result, 'text': text})
            identity = '|'.join(str(row.get(k, '')) for k in ('brand', 'model', 'variant_name'))
            jobs.append({'job_id': hashlib.sha256((identity + '|' + url).encode()).hexdigest(),
                         'brand': row['brand'], 'model': row['model'], 'variant_name': row['variant_name'],
                         'source_url': url, 'expected_hash': row.get('source_hash'), 'current_hash': result.get('content_hash'),
                         'current_text_hash': result.get('text_hash'), 'reason': reason, 'checked_at': checked_at,
                         'source_text_path': str(text_path.relative_to(ROOT)).replace('\\', '/') if text_path and text_path.is_relative_to(ROOT) else None,
                         'action': 'confirm_existing_evidence' if reason == 'hash_and_evidence_unchanged' else 'official_variant_reextraction',
                         'status': 'queued', 'public_data_changed': False})
        print(json.dumps({'source': url, 'status': result['status'], 'variants': len(rows)}, ensure_ascii=False), flush=True)
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'sources': checked, 'variants': len(records),
            'source_counts': dict(Counter(row['status'] for row in checked)),
            'evidence_counts': dict(Counter(row['reason'] for row in jobs)), 'jobs': jobs,
            'facts_verified': 0, 'remote_writes': False, 'openai_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'public/data/public_ev_variants.json').read_text(encoding='utf-8'))
    records = list(catalog['records'])
    quarantine = ROOT / 'data/review/catalog_reconciliation.json'
    if quarantine.exists():
        records += json.loads(quarantine.read_text(encoding='utf-8')).get('quarantine', [])
    if args.limit:
        urls = sorted({row['source_url'] for row in records})[:args.limit]
        records = [row for row in records if row['source_url'] in urls]
    report = run(records, ROOT / 'data/local/release-data/sources')
    report['public_catalog_source'] = catalog.get('source')
    report['public_catalog_sha256'] = catalog.get('catalog_sha256')
    (ROOT / 'data/mvp/release_source_audit.json').write_text(json.dumps({k: v for k, v in report.items() if k != 'jobs'}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'data/review/source_reverification_queue.json').write_text(json.dumps(report['jobs'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('sources', 'jobs')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
