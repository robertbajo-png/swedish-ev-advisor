"""Private source-document preparation, never facts or publication approval."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from news_http import MAX_BYTES, PageText, reserved, canonical_url
from news_store import artifact_hash

MAX_PAGES = 12
MAX_TEXT = 90000
MAX_TABLES = 20
MAX_ROWS = 100
MAX_COLUMNS = 20
PARSER_TIMEOUT = 12


class DocumentHeld(ValueError):
    def __init__(self, reason, **details):
        super().__init__(reason)
        self.details = details


class TableDocument(HTMLParser):
    """Keep cells and explicit spans; never infer a market, period or unit."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.table, self.row, self.cell = [], None, None, None
        self.depth = 0
        self.caption = False
        self.foot = False
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag == 'table':
            self.depth += 1
            if self.depth > 1:
                self.table['errors'].append('nested_table')
                return
            if len(self.tables) >= MAX_TABLES:
                raise ValueError('document_table_limit')
            self.table = {'caption': [], 'rows': [], 'errors': []}
        if self.depth != 1:
            return
        if tag == 'caption': self.caption = True
        if tag == 'tfoot': self.foot = True
        if tag == 'tr':
            if self.row is not None: self.table['errors'].append('unclosed_row')
            if len(self.table['rows']) >= MAX_ROWS: raise ValueError('document_row_limit')
            self.row = []
            self.table['rows'].append(self.row)
        if tag in ('td', 'th'):
            if self.row is None or self.cell is not None:
                self.table['errors'].append('ambiguous_cell')
                return
            if len(self.row) >= MAX_COLUMNS: raise ValueError('document_column_limit')
            spans = {}
            for name in ('rowspan', 'colspan'):
                raw = a.get(name, '1')
                if not re.fullmatch(r'[1-9][0-9]?', raw):
                    self.table['errors'].append('invalid_cell_span')
                    raw = '1'
                spans[name] = int(raw)
                if spans[name] != 1: self.table['errors'].append('spanning_cells_need_adapter')
            self.cell = {'kind': tag, 'scope': a.get('scope', ''), 'footnote': self.foot,
                         **spans, 'text': []}
            self.row.append(self.cell)

    def handle_data(self, data):
        if self.depth != 1 or self.skip: return
        target = self.table['caption'] if self.caption else self.cell['text'] if self.cell else None
        if target is not None:
            target.append(data)
            if sum(len(t) for t in target) > 2000: raise ValueError('document_cell_limit')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'): self.skip = max(0, self.skip - 1)
        if tag == 'table' and self.depth:
            if self.depth == 1:
                if self.cell is not None or self.row is not None: self.table['errors'].append('unclosed_table_cell')
                if self.caption: self.table['errors'].append('unclosed_caption')
                self.tables.append(self.table)
                self.table, self.row, self.cell = None, None, None
                self.caption, self.foot = False, False
            self.depth -= 1
            return
        if self.depth != 1: return
        if tag == 'caption': self.caption = False
        if tag == 'tfoot': self.foot = False
        if tag in ('td', 'th'): self.cell = None
        if tag == 'tr': self.row = None

    def snapshot(self):
        if self.depth: raise ValueError('document_unclosed_table')
        result = []
        for table in self.tables:
            rows = [[{**c, 'text': ' '.join(' '.join(c['text']).split())} for c in row] for row in table['rows']]
            errors = set(table['errors'])
            if not rows or not rows[0] or len({len(row) for row in rows}) != 1:
                errors.add('ragged_or_empty_table')
            if not rows or not all(c['kind'] == 'th' for c in rows[0]):
                errors.add('explicit_column_headers_required')
            value = {'caption': ' '.join(' '.join(table['caption']).split()), 'rows': rows,
                     'status': 'held_ambiguous' if errors else 'prepared_not_verified',
                     'errors': sorted(errors)}
            result.append({**value, 'table_hash': artifact_hash(value)})
        return result


class NarrativeText(PageText):
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self.skip += 1
        super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        super().handle_endtag(tag)
        if tag == 'table': self.skip = max(0, self.skip - 1)


def html_document(html):
    if len(html.encode()) > MAX_BYTES: raise ValueError('document_too_large')
    parser = TableDocument(); parser.feed(html)
    narrative = NarrativeText(); narrative.feed(html)
    value = {'format': 'html', 'raw_sha256': hashlib.sha256(html.encode()).hexdigest(),
             'tables': parser.snapshot(), 'status': 'prepared_not_verified'}
    return narrative.plain(), {**value, 'snapshot_hash': artifact_hash(value)}


def valid_html_snapshot(value):
    try:
        return (set(value) == {'format', 'raw_sha256', 'tables', 'status', 'snapshot_hash'}
            and value['format'] == 'html' and value['status'] == 'prepared_not_verified'
            and bool(re.fullmatch(r'[a-f0-9]{64}', value['raw_sha256']))
            and isinstance(value['tables'], list) and len(value['tables']) <= MAX_TABLES
            and value['snapshot_hash'] == artifact_hash({k: v for k, v in value.items() if k != 'snapshot_hash'})
            and all(table['table_hash'] == artifact_hash({k: v for k, v in table.items() if k != 'table_hash'})
                    for table in value['tables']))
    except (TypeError, KeyError, ValueError):
        return False


def parse_pdf_bytes(raw):
    """Called in a bounded child process, not in the editorial worker."""
    if not raw.startswith(b'%PDF-') or len(raw) > MAX_BYTES:
        raise ValueError('document_invalid_or_oversized_pdf')
    from pypdf import PdfReader
    import pdfplumber
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted: raise ValueError('document_encrypted_pdf')
    root = reader.trailer['/Root']
    if any(key in root for key in ('/OpenAction', '/AA', '/AcroForm')):
        raise ValueError('document_active_pdf')
    names = root.get('/Names', {})
    if hasattr(names, 'get_object'): names = names.get_object()
    if any(key in names for key in ('/JavaScript', '/EmbeddedFiles')):
        raise ValueError('document_active_pdf')
    if not 1 <= len(reader.pages) <= MAX_PAGES: raise ValueError('document_page_limit')
    metadata = str(reader.metadata or '')
    if re.search(r'noai|notdm|tdm.reservation.{0,20}(?:1|true)|ai.input\s*=\s*no', metadata, re.I):
        raise ValueError('tdm_reserved')
    if reader.xmp_metadata is not None:
        stream = root.get('/Metadata')
        if stream and re.search(rb'noai|notdm|tdm.reservation.{0,80}(?:1|true)|ai.input\s*=\s*no',
                                stream.get_object().get_data(), re.I | re.S):
            raise ValueError('tdm_reserved')
    pages, used, tables = [], 0, 0
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for number, (page, geometry) in enumerate(zip(reader.pages, pdf.pages), 1):
            if page.get('/AA'): raise ValueError('document_active_pdf')
            for annotation in page.get('/Annots', []):
                annotation = annotation.get_object()
                action = annotation.get('/A')
                if hasattr(action, 'get_object'): action = action.get_object()
                if (annotation.get('/AA') or annotation.get('/Subtype') != '/Link'
                        or (action and (action.get('/S') != '/URI' or action.get('/Next')
                            or urlsplit(str(action.get('/URI', ''))).scheme not in ('https', 'http', 'mailto')))):
                    raise ValueError('document_annotated_pdf_requires_review')
            text = page.extract_text(extraction_mode='layout') or ''
            used += len(text)
            if used > MAX_TEXT: raise ValueError('document_text_limit')
            if len(text.split()) < 8 or '\ufffd' in text or '\x00' in text:
                raise ValueError('document_scanned_or_unreadable_pdf')
            grids = []
            for table in geometry.find_tables():
                tables += 1
                if tables > MAX_TABLES: raise ValueError('document_table_limit')
                rows = table.extract()
                if len(rows) > MAX_ROWS or any(len(row) > MAX_COLUMNS for row in rows):
                    raise ValueError('document_table_size_limit')
                if any(cell is not None and len(cell) > 2000 for row in rows for cell in row):
                    raise ValueError('document_cell_limit')
                value = {'page': number, 'bbox': list(table.bbox), 'cells': rows,
                         'status': 'needs_header_period_unit_validation'}
                grids.append({**value, 'table_hash': artifact_hash(value)})
            pages.append({'page': number, 'layout_text': text,
                          'text_sha256': hashlib.sha256(text.encode()).hexdigest(), 'tables': grids})
    value = {'format': 'pdf', 'raw_sha256': hashlib.sha256(raw).hexdigest(), 'pages': pages,
             'status': 'prepared_not_verified',
             'metadata_title': str((reader.metadata or {}).get('/Title', ''))[:500],
             'publication_date': None}
    # PDF creation/modification metadata is deliberately not a publication date.
    return {**value, 'snapshot_hash': artifact_hash(value)}


def inspect_pdf(raw):
    if not isinstance(raw, bytes) or not raw.startswith(b'%PDF-') or len(raw) > MAX_BYTES:
        raise ValueError('document_invalid_or_oversized_pdf')
    env = {k: v for k, v in os.environ.items() if k in ('SystemRoot', 'WINDIR', 'PATH', 'TEMP', 'TMP')}
    try:
        result = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--parse-pdf'],
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=PARSER_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        raise ValueError('document_parser_timeout') from error
    if result.returncode or len(result.stdout) > 1_000_000:
        raise ValueError('document_parser_failed_or_resource_limit')
    output = json.loads(result.stdout)
    if output.get('error'): raise ValueError(output['error'])
    if (output.get('raw_sha256') != hashlib.sha256(raw).hexdigest()
            or output.get('snapshot_hash') != artifact_hash({k: v for k, v in output.items() if k != 'snapshot_hash'})):
        raise ValueError('document_snapshot_hash_mismatch')
    return output


def collect_document(url, collector, archive=None):
    from news_publisher_sources import primary_source
    source = primary_source(url)
    if not source: raise ValueError('unapproved_primary_document_url')
    status, headers, raw, final = collector.fetch_bytes(url, source)
    if status != 200 or final != url:
        raise DocumentHeld('document_inaccessible_or_redirected', http_status=status, final_url=final)
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES: raise ValueError('document_too_large')
    kind = next((v.lower().split(';')[0].strip() for k, v in headers.items() if k.lower() == 'content-type'), '')
    if reserved(headers): raise ValueError('tdm_reserved')
    linked = []
    if kind == 'application/pdf' and raw.startswith(b'%PDF-'):
        snapshot = inspect_pdf(raw)
    elif kind in ('text/html', 'application/xhtml+xml') and not url.lower().endswith('.pdf'):
        html = raw.decode('utf-8', errors='strict')
        if reserved(headers, html): raise ValueError('tdm_reserved')
        page = PageText(); page.feed(html)
        if page.paywall or re.search(r'"isAccessibleForFree"\s*:\s*false', html, re.I):
            raise ValueError('document_paywall')
        text, snapshot = html_document(html)
        if re.search(r'just a moment|verify you are human|access denied', text[:800], re.I):
            raise ValueError('document_access_challenge')
        for href in page.links:
            try:
                target = canonical_url(urljoin(url, href))
                authority = primary_source(target)
                if (authority and authority['id'] == source['id'] and urlsplit(target).path.lower().endswith('.pdf')
                        and target not in linked):
                    linked.append(target)
            except (TypeError, ValueError): continue
            if len(linked) >= MAX_TABLES: break
    else:
        raise ValueError('document_type_mismatch')
    evidence_path = archive(raw, snapshot['raw_sha256'], snapshot['format']) if archive else None
    return {'url': url, 'source_id': source['id'], 'publisher': source['name'],
            'http_status': status, 'content_type': kind, 'snapshot': snapshot,
            'archive_path': evidence_path, 'linked_documents': linked, 'publication_eligible': False}


if __name__ == '__main__' and sys.argv[1:] == ['--parse-pdf']:
    # Linux CI/production enforces a memory/CPU ceiling as well as the parent timeout.
    if sys.platform != 'win32':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    try:
        print(json.dumps(parse_pdf_bytes(sys.stdin.buffer.read(MAX_BYTES + 1)), ensure_ascii=True))
    except Exception as error:
        name = str(error) if isinstance(error, ValueError) and re.fullmatch(r'[a-z_]+', str(error)) else 'document_unparseable_pdf'
        print(json.dumps({'error': name}))
