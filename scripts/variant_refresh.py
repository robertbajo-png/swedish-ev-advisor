"""Exact-column manufacturer extraction; no model maxima or LLM guesses."""
import math
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from audit_catalog_sources import normalized
from validate_extracted_variants import validate_draft

FACT_FIELDS = ('price_sek', 'price_type', 'price_valid_until', 'wltp_range_km',
               'wltp_consumption_kwh_100km', 'battery_kwh', 'dc_charge_kw',
               'ac_charge_kw', 'boot_liters', 'tow_kg', 'seats', 'drivetrain')
HIDDEN = {'script', 'style', 'noscript', 'template'}
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class RefreshError(ValueError):
    pass


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: object = None

    def text(self):
        if self.tag in HIDDEN or 'hidden' in self.attrs or self.attrs.get('aria-hidden') == 'true':
            return ''
        return re.sub(r'\s+', ' ', ' '.join(child.text() if isinstance(child, Node) else child
                                           for child in self.children)).strip()

    def nodes(self, tag):
        if self.tag in HIDDEN or 'hidden' in self.attrs or self.attrs.get('aria-hidden') == 'true':
            return
        for child in self.children:
            if isinstance(child, Node):
                if child.tag == tag:
                    yield child
                yield from child.nodes(tag)


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_document(body, content_type):
    if 'html' not in content_type:
        raise RefreshError('html_document_required')
    parser = DocumentParser()
    parser.feed(body.decode('utf-8', errors='replace'))
    return parser.root


def one(items, reason):
    values = list(items)
    if len(values) != 1:
        raise RefreshError(reason)
    return values[0]


def exact_number(text, pattern):
    match = re.fullmatch(pattern, text, re.I)
    if not match:
        raise RefreshError('ambiguous_or_unsupported_value')
    return float(match.group(1).replace(' ', '').replace('\u00a0', '').replace(',', '.'))


def definition(document, label):
    term = one((node for node in document.nodes('dt') if normalized(node.text()) == normalized(label)),
               'missing_or_ambiguous_common_field')
    siblings = [node for node in term.parent.children if isinstance(node, Node)]
    following = siblings[siblings.index(term) + 1:]
    value = one((node for node in following if node.tag == 'dd'), 'definition_value_missing')
    if re.search(r'tillval|prelimin|paketet', normalized(value.text())):
        raise RefreshError('conditional_common_field')
    return term.text(), value.text()


def extract_polestar(document, source, expected):
    """Only an unchanged set of exact table headers may map to existing variants."""
    names = {normalized(row['variant_name']): row['variant_name'] for row in expected}
    if len(names) != len(expected) or not names:
        raise RefreshError('duplicate_or_empty_variant_scope')
    tables = []
    for table in document.nodes('table'):
        headings = [node.text() for node in table.nodes('th')]
        if len(headings) == len(names) and set(map(normalized, headings)) == set(names):
            tables.append((table, headings))
    table, headings = one(tables, 'exact_variant_headers_not_found')
    if any(cell.attrs.get(span, '1') != '1' for tag in ('th', 'td')
           for cell in table.nodes(tag) for span in ('colspan', 'rowspan')):
        raise RefreshError('table_shape_changed')
    rows = {}
    for tr in table.nodes('tr'):
        cells = list(tr.nodes('td'))
        if not cells:
            continue
        if len(cells) != len(headings):
            raise RefreshError('table_shape_changed')
        labels = [one(cell.nodes('label'), 'table_cell_label_missing').text() for cell in cells]
        if len(set(map(normalized, labels))) != 1:
            raise RefreshError('table_labels_disagree')
        key = re.sub(r'[0-9]+$', '', normalized(labels[0])).strip()
        if key in rows:
            raise RefreshError('duplicate_specification_row')
        rows[key] = cells

    price_key = one((key for key in rows if key in ('pris från', 'listpris')), 'exact_price_row_missing')
    range_key = one((key for key in rows if key == 'räckvidd'), 'certified_range_row_missing')
    for required in ('drivlina', 'dragvikt'):
        if required not in rows:
            raise RefreshError('required_variant_field_missing')

    common = {
        'battery_kwh': (*definition(document, 'Batterikapacitet'), r'400 V litiumjonbatteri, ([0-9]+(?:[.,][0-9]+)?) kWh kapacitet, [0-9]+ moduler'),
        'dc_charge_kw': (*definition(document, 'DC-laddning'), r'(?:Upp till )?([0-9]+) kW'),
        'boot_liters': (*definition(document, 'Volym (uppfällda säten)'), r'([0-9 ]+) liter, inklusive under golvet'),
    }
    ac_term = one((node.text() for node in document.nodes('dt')
                   if re.fullmatch(r'[0-9]+ kW AC laddningstid.*', node.text())), 'common_ac_power_missing')
    ac = exact_number(ac_term, r'([0-9]+) kW AC laddningstid.*')
    extracted = []
    for column, heading in enumerate(headings):
        row = {field: None for field in FACT_FIELDS}
        evidence = {}

        def cell_value(key):
            cell = rows[key][column]
            label = one(cell.nodes('label'), 'cell_label_missing').text()
            text = cell.text()
            if not text.startswith(label + ' '):
                raise RefreshError('cell_value_missing')
            return text[len(label):].strip(), text

        for field_name, key, pattern in (
            ('price_sek', price_key, r'([0-9 ]+) kr'),
            ('wltp_range_km', range_key, r'(?:Upp till )?([0-9]+) km'),
            ('tow_kg', 'dragvikt', r'(?:Upp till )?([0-9 ]+) kg'),
        ):
            value, excerpt = cell_value(key)
            row[field_name] = int(exact_number(value, pattern))
            evidence[field_name] = {'quote': excerpt, 'scope': 'variant_column', 'column_header': heading}
        if price_key == 'listpris':
            row['price_type'] = 'list_price'
            evidence['price_type'] = evidence['price_sek']
        row['drivetrain'], excerpt = cell_value('drivlina')
        if row['drivetrain'] not in ('Bakhjulsdrift', 'Fyrhjulsdrift', 'Framhjulsdrift'):
            raise RefreshError('unsupported_drivetrain')
        evidence['drivetrain'] = {'quote': excerpt, 'scope': 'variant_column', 'column_header': heading}
        for field_name, (label, value, pattern) in common.items():
            row[field_name] = exact_number(value, pattern)
            if field_name != 'battery_kwh':
                row[field_name] = int(row[field_name])
            evidence[field_name] = {'quote': label + ' ' + value, 'scope': 'common_model'}
        row['ac_charge_kw'] = int(ac)
        evidence['ac_charge_kw'] = {'quote': ac_term, 'scope': 'common_model'}
        for item in evidence.values():
            item.update(source_url=source['url'], source_hash=source['content_hash'])
        row.update(brand=source['brand'], model=source['model'], variant_name=names[normalized(heading)],
                   source_url=source['url'], source_hash=source['content_hash'],
                   source_quote=' | '.join([heading] + list(dict.fromkeys(item['quote'] for item in evidence.values()))),
                   extraction_confidence=0.99, extraction_payload={'adapter': 'polestar_table_v1', 'field_evidence': evidence},
                   validation_status='extracted')
        extracted.append(row)
    return extracted


def evidence_value(field_name, quote):
    patterns = {
        'price_sek': r'(?:Pris från|Listpris) ([0-9 ]+) kr',
        'wltp_range_km': r'Räckvidd[¹²³0-9]* (?:Upp till )?([0-9]+) km',
        'tow_kg': r'Dragvikt (?:Upp till )?([0-9 ]+) kg',
        'dc_charge_kw': r'DC-laddning (?:Upp till )?([0-9]+) kW',
        'ac_charge_kw': r'([0-9]+) kW AC laddningstid.*',
        'boot_liters': r'Volym \(uppfällda säten\) ([0-9 ]+) liter, inklusive under golvet',
        'battery_kwh': r'Batterikapacitet 400 V litiumjonbatteri, ([0-9]+(?:[.,][0-9]+)?) kWh kapacitet, [0-9]+ moduler',
    }
    if field_name == 'drivetrain':
        match = re.fullmatch(r'Drivlina (Bakhjulsdrift|Fyrhjulsdrift|Framhjulsdrift)', quote)
        return match.group(1) if match else None
    if field_name == 'price_type':
        return 'list_price' if quote.startswith('Listpris ') else None
    try:
        return exact_number(quote, patterns[field_name])
    except (RefreshError, KeyError):
        return None


def refresh_errors(draft, source, document, previous):
    errors = validate_draft(draft, {source['url']: source})
    if (draft.get('brand'), draft.get('model'), draft.get('variant_name')) != (
            previous.get('brand'), previous.get('model'), previous.get('variant_name')):
        errors.append('identity_changed')
    evidence = draft.get('extraction_payload', {}).get('field_evidence', {})
    text = normalized(document.text())
    for field_name in FACT_FIELDS:
        value = draft.get(field_name)
        if previous.get(field_name) is not None and value is None:
            errors.append('would_clear_existing_' + field_name)
        if value is None:
            continue
        item = evidence.get(field_name, {})
        if (item.get('source_url') != source['url'] or item.get('source_hash') != source['content_hash']
                or not item.get('quote') or normalized(item['quote']) not in text
                or item.get('scope') not in ('variant_column', 'common_model')):
            errors.append('unsupported_' + field_name)
        if item.get('scope') == 'variant_column' and normalized(item.get('column_header')) != normalized(draft['variant_name']):
            errors.append('wrong_variant_' + field_name)
        if evidence_value(field_name, item.get('quote', '')) != value:
            errors.append('value_evidence_mismatch_' + field_name)
        if isinstance(value, (int, float)) and (isinstance(value, bool) or not math.isfinite(value)):
            errors.append('non_finite_' + field_name)
    for field_name in ('price_sek', 'wltp_range_km'):
        before, after = previous.get(field_name), draft.get(field_name)
        if before and after and abs(after / before - 1) > 0.15:
            errors.append('large_change_' + field_name)
    if not re.fullmatch(r'[0-9a-f]{64}', draft.get('source_hash', '')):
        errors.append('invalid_source_hash')
    return sorted(set(errors))
