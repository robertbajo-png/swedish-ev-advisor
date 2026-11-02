"""Bounded private inspection of declared originals; no AI or database writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from news_document_evidence import collect_document
from news_http import Collector, canonical_url
from smoke_news_engine import verified_context

ROOT = Path(__file__).resolve().parents[1]
MAX_DOCUMENTS = 3


def selection_urls(value):
    urls = []
    for item in value.get('candidates', []):
        for row in item.get('discovery_trace', []):
            if row.get('status') == 'needs_pdf_extraction' and isinstance(row.get('url'), str):
                urls.append(row['url'])
    return list(dict.fromkeys(urls))[:MAX_DOCUMENTS]


def archive_document(directory, raw, digest, kind):
    if hashlib.sha256(raw).hexdigest() != digest or kind not in ('html', 'pdf'):
        raise ValueError('document_archive_hash_mismatch')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (digest + '.' + kind)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('document_existing_archive_changed')
    else:
        with path.open('xb') as handle: handle.write(raw)
    return str(path)


def inspect(urls, collector, archive=None):
    result = []
    queue = [(url, None) for url in list(dict.fromkeys(urls))[:MAX_DOCUMENTS]]
    seen = set()
    while queue and len(seen) < MAX_DOCUMENTS:
        raw, origin = queue.pop(0)
        if raw in seen: continue
        seen.add(raw)
        try:
            url = canonical_url(raw)
            if raw != url: raise ValueError('canonical_document_url_required')
            document = collect_document(url, collector, archive)
            result.append({'status': 'prepared_not_verified', 'discovered_from': origin, **document})
            queue.extend((target, {'url': url, 'raw_sha256': document['snapshot']['raw_sha256']})
                         for target in document['linked_documents'] if target not in seen)
        except Exception as error:
            result.append({'url': raw, 'status': 'held', 'reason': type(error).__name__ + ':' + str(error)[:160],
                           'details': getattr(error, 'details', {}),
                           'publication_eligible': False})
    return {'prepared_at': datetime.now(timezone.utc).isoformat(), 'documents': result,
            'paid_calls': 0, 'database_writes': 0, 'publications': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--url')
    source.add_argument('--selection', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    if not destination.is_relative_to((ROOT / 'data/local/release-data').resolve()) or destination.suffix != '.json':
        parser.error('Document evidence must stay private as JSON under data/local/release-data')
    if args.selection:
        if args.selection.stat().st_size > 2_000_000: parser.error('Selection file too large')
        urls = selection_urls(json.loads(args.selection.read_text(encoding='utf-8')))
    else:
        urls = [args.url]
    directory = (destination.parent / 'documents').resolve()
    if not directory.is_relative_to((ROOT / 'data/local/release-data').resolve()):
        parser.error('Document archive must stay private under data/local/release-data')
    result = inspect(urls, Collector(tls_context=verified_context()),
                     lambda raw, digest, kind: archive_document(directory, raw, digest, kind))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'documents': [{'url': d['url'], 'status': d['status'], 'reason': d.get('reason')}
                                   for d in result['documents']], 'paid_calls': 0, 'publications': 0}))


if __name__ == '__main__': main()
