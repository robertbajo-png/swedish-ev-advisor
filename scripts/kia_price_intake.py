"""Read exact full-version rows in Kia Sweden's cash price tables. No AI or publication."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from audit_catalog_sources import ROOT, SourceFetcher
from variant_refresh import Node, RefreshError, parse_document

URL = 'https://www.kia.com/se/kopa/prislista/'
ADAPTER = 'kia_sweden_exact_price_row_v1'


def token(value):
    return ''.join(character for character in str(value).casefold() if character.isalnum())


def extract_rows(document, source, held=None):
    if (source.get('status') != 'reachable' or source.get('http_status') != 200
            or source.get('final_url') != URL or not re.fullmatch('[a-f0-9]{64}', source.get('content_hash', ''))):
        raise RefreshError('unverified_kia_price_source')
    result = []
    for table in document.nodes('table'):
        captions = [node.text() for node in table.nodes('caption')]
        if len(captions) != 1 or not re.match(r'Prislista för Kia EV[0-9]', captions[0], re.I):
            continue
        heading_rows = [tr for tr in table.nodes('tr')
                        if list(tr.nodes('th')) and token(list(tr.nodes('th'))[0].text()) == 'modellochversion']
        if len(heading_rows) != 1:
            raise RefreshError('ambiguous_kia_table_headers')
        headings = [node.text() for node in heading_rows[0].nodes('th')]
        price_columns = [index for index, text in enumerate(headings) if token(text) == 'rekcirkaprisinklmoms']
        if len(price_columns) != 1 or not headings or token(headings[0]) != 'modellochversion':
            raise RefreshError('cash_price_column_not_identified')
        column = price_columns[0]
        for tr in table.nodes('tr'):
            cells = [node for node in tr.children if isinstance(node, Node) and node.tag in ('td', 'th')]
            if not cells or tr is heading_rows[0]:
                continue
            if len(cells) != len(headings) or any(node.attrs.get('colspan', '1') != '1' or node.attrs.get('rowspan', '1') != '1' for node in cells):
                raise RefreshError('ambiguous_kia_price_row')
            label = cells[0].text()
            amount = cells[column].text()
            match = re.fullmatch(r'([1-3] [0-9]{3} [0-9]{3}|[0-9]{3}\s*[0-9]{3})\s*(?:kr|SEK)?', amount, re.I)
            if not match:
                if held is not None:
                    held.append({'row_label': label, 'cash_price_text': amount, 'reason': 'unsupported_cash_price'})
                continue
            price = int(re.sub(r'\s', '', match.group(1)))
            if not 100000 <= price <= 3000000:
                raise RefreshError('invalid_cash_price')
            result.append(dict(row_label=label, row_key=token(label), price_sek=price,
                price_type='list_price', price_valid_until=None, source_url=URL,
                source_hash=source['content_hash'], price_verified_at=source['fetched_at'],
                source_name='Kia Sverige', extraction_confidence=0.99,
                source_quote=' | '.join([captions[0], label, headings[column], amount]),
                caption=captions[0], price_header=headings[column], adapter=ADAPTER))
    keys = [row['row_key'] for row in result]
    if not result or len(keys) != len(set(keys)):
        raise RefreshError('missing_or_duplicate_exact_versions')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/local/release-data/price-completion/kia-rows.json')
    args = parser.parse_args()
    fetched = SourceFetcher(document_parser=parse_document).fetch(URL, {'Kia'})
    if fetched.get('status') != 'reachable':
        raise RefreshError('kia_source_' + fetched.get('status', 'unknown'))
    source = {key: fetched.get(key) for key in ('status', 'http_status', 'final_url', 'content_hash', 'text_hash', 'content_type')}
    source['fetched_at'] = datetime.now(timezone.utc).isoformat()
    held = []
    rows = extract_rows(fetched['document'], source, held)
    payload = {'source': source, 'rows': rows, 'held': held, 'database_writes': 0, 'paid_calls': 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'rows': [{'version': row['row_label'], 'price': row['price_sek']} for row in rows],
                      'held': held, 'source_hash': source['content_hash'], 'database_writes': 0, 'paid_calls': 0}, ensure_ascii=True))


if __name__ == '__main__':
    main()
