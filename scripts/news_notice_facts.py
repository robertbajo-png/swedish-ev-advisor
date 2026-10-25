"""Bounded official-source adapters. Unknown formats are not AI-guessed."""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlsplit

from news_http import iso_date
from news_statistics import source_statistical_facts

ADAPTERS = {'vw-sweden-press': 'www.vwgroup.se', 'acea': 'www.acea.auto'}
MONTHS = ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti',
          'september', 'oktober', 'november', 'december']
NUMBER = r'\d+(?:[,.]\d+)?'


class NoticeRejected(ValueError):
    pass


def plain(value):
    return ' '.join(value.split())


def source_errors(item, source, now=None):
    now = now or datetime.now(timezone.utc)
    p = item.get('payload', {})
    errors = []
    if (source.get('id') != item.get('source_id') or source.get('id') not in ADAPTERS
            or source.get('kind') != 'primary' or p.get('source_kind') != 'primary'):
        errors.append('unsupported_official_notice_adapter')
    host = ADAPTERS.get(source.get('id'))
    for url in (source.get('website', ''), item.get('url', ''), p.get('final_url', '')):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != host or parsed.username or parsed.password or parsed.port:
            errors.append('notice_source_domain_mismatch')
    expected_path = '/pc-registrations/' if source.get('id') == 'acea' else '/nyheter--media/pressmeddelanden/'
    if not urlsplit(item.get('url', '')).path.startswith(expected_path):
        errors.append('unsupported_notice_source_path')
    if p.get('publisher') != source.get('name') or p.get('access_status') != 'accessible':
        errors.append('notice_source_not_accessible_or_attributed')
    content = p.get('content', '')
    if not isinstance(content, str) or not content or p.get('content_hash') != hashlib.sha256(content.encode()).hexdigest():
        errors.append('notice_source_hash_mismatch')
    for key, age in [('published_at', timedelta(days=7)), ('fetched_at', timedelta(days=1))]:
        try:
            value = datetime.fromisoformat(iso_date(p.get(key)) or '')
            if not -timedelta(minutes=5) <= now-value <= age:
                errors.append('notice_stale_or_future_' + key)
        except (ValueError, TypeError):
            errors.append('notice_missing_' + key)
    return sorted(set(errors))


def number(value, minimum, maximum):
    value = Decimal(value.replace(' ', '').replace(',', '.'))
    if not value.is_finite() or not minimum <= value <= maximum:
        raise NoticeRejected('notice_numeric_bound_failed')
    return format(value, 'f')


def unique(text, pattern, required=True):
    matches = list(re.finditer(pattern, text))
    # Identical repeated fields are fine; competing values are not.
    signatures = {tuple(m.groupdict().items()) for m in matches}
    if len(signatures) > 1 or (required and not matches):
        raise NoticeRejected('notice_missing_or_conflicting_field')
    return matches[0] if matches else None


def proof(match, **values):
    return {'value': values, 'evidence': match[0], 'start': match.start(), 'end': match.end()}


def vw_facts(item):
    text = plain(item['payload']['content'])
    announcement = unique(text, r'Volkswagen inleder nu förförsäljningen av nya '
        r'(?P<model>ID\. (?:Cross|Polo|[0-9](?: Tourer)?)) med ett batteri på (?P<battery>' + NUMBER + r') kWh')
    model = announcement['model']
    if 'Volkswagen ' + model not in plain(item['payload'].get('title', '')):
        raise NoticeRejected('notice_model_not_in_title')
    battery = number(announcement['battery'], 10, 200)
    month_pattern = '|'.join(MONTHS)
    launch = unique(text, r'Nya ' + re.escape(model) + r' lanseras på den svenska marknaden vid månadsskiftet '
        r'(?P<first>' + month_pattern + r')/(?P<second>' + month_pattern + r')\.')
    if (MONTHS.index(launch['first'])+1) % 12 != MONTHS.index(launch['second']):
        raise NoticeRejected('notice_invalid_month_boundary')
    range_field = unique(text, r'Batteriet på (?P<battery>' + NUMBER + r') kWh \(netto\) ger en räckvidd på upp till '
                         r'(?P<range>\d+) km \(WLTP\)')
    if number(range_field['battery'], 10, 200) != battery:
        raise NoticeRejected('notice_battery_variant_conflict')
    fields = {
        'announcement': proof(announcement, model=model, battery_kwh=battery),
        'market_launch': proof(launch, market='SE', first=launch['first'], second=launch['second']),
        'battery_range': proof(range_field, battery_kwh=battery, capacity_basis='net',
                               range_km=number(range_field['range'], 50, 1200), range_basis='WLTP', range_limit='up_to'),
    }
    charging = unique(text, r'DC-snabbladdning med (?P<power>' + NUMBER + r') kW från (?P<low>\d+) till '
        r'(?P<high>\d+) procent på cirka (?P<minutes>' + NUMBER + r') minuter', required=False)
    if charging:
        low, high = int(charging['low']), int(charging['high'])
        if not 0 <= low < high <= 100:
            raise NoticeRejected('notice_invalid_charge_window')
        fields['charging'] = proof(charging, current='DC', power_kw=number(charging['power'], 20, 600),
            from_percent=low, to_percent=high, minutes=number(charging['minutes'], 3, 180), duration_basis='approximate')
    return {'subject': 'Volkswagen ' + model, 'brand': 'Volkswagen', 'model': model, 'fields': fields}


def prices(item, model):
    text = plain(item['payload']['content'])
    heading = unique(text, r'(?P<market>Följande versioner erbjuds nu på den svenska marknaden), '
                     r'med fastställda rekommenderade cirkapriser:', required=False)
    if not heading:
        return None
    end = text.find('Samtliga versioner', heading.end())
    if end < 0:
        raise NoticeRejected('notice_price_scope_not_closed')
    pattern = (re.escape(model) + r' (?P<trim>Trend|Life|Style), (?P<battery>' + NUMBER + r') kWh-batteri, '
        r'(?P<hp>\d+) hk \((?P<kw>\d+) kW\), (?P<range>\d+) km räckvidd: från (?P<price>\d{1,3}(?: \d{3})+) kronor'
        r'(?=\s+' + re.escape(model) + r' (?:Trend|Life|Style)|\s*$)')
    entries = {}
    matches = list(re.compile(pattern).finditer(text, heading.end(), end))
    names = list(re.finditer(re.escape(model) + r' (?:Trend|Life|Style)\b', text[heading.end():end]))
    if len(matches) != len(names):
        raise NoticeRejected('notice_unparsed_price_row_or_payment_period')
    for match in matches:
        values = {'model': model, 'trim': match['trim'], 'battery_kwh': number(match['battery'], 10, 200),
                  'power_hp': number(match['hp'], 20, 1500), 'power_kw': number(match['kw'], 10, 1200),
                  'range_km': number(match['range'], 50, 1200), 'amount': number(match['price'], 100000, 3000000),
                  'currency': 'SEK', 'market': 'SE', 'price_type': 'list_price', 'from_price': True}
        key = values['trim'] + ':' + values['battery_kwh']
        entry = {**proof(match, **values), 'scope_evidence': heading[0], 'scope_start': heading.start(), 'scope_end': heading.end()}
        if key in entries and entries[key]['value'] != values:
            raise NoticeRejected('notice_conflicting_variant_prices')
        entries[key] = entry
    if not entries:
        raise NoticeRejected('notice_no_scoped_variant_price')
    # Keep the complete table for conflict detection; render only three variants.
    return {'entries': list(entries.values())}


def statistics(item):
    facts = source_statistical_facts(item)
    by_metric = {(f['statistic']['powertrain'], f['statistic']['metric']): f for f in facts}
    wanted = [('battery-electric', 'market_share_percent'), ('battery-electric', 'units'),
              ('hybrid-electric', 'market_share_percent')]
    if any(key not in by_metric for key in wanted):
        raise NoticeRejected('notice_incomplete_literal_statistics')
    for key in [('plug-in-hybrid', 'market_share_percent'), ('all_powertrains', 'year_to_date_change_percent')]:
        if key in by_metric:
            wanted.append(key)
    scopes = {tuple((k, f['statistic'][k]) for k in ('market','period','year','through_month','denominator'))
              for f in facts}
    if len(scopes) != 1:
        raise NoticeRejected('notice_conflicting_statistical_scopes')
    return {'subject': 'EU personbilsregistreringar', 'brand': None, 'model': None,
            'fields': {'statistics': [by_metric[key] for key in wanted]}}


def extract_notice(item, source, kind=None, now=None):
    errors = source_errors(item, source, now)
    if errors:
        raise NoticeRejected(';'.join(errors))
    if item['source_id'] == 'acea':
        if kind not in (None, 'statistics'):
            raise NoticeRejected('notice_wrong_source_for_type')
        kind, packet = 'statistics', statistics(item)
    else:
        packet = vw_facts(item)
        price_fields = prices(item, packet['model'])
        kind = kind or ('price' if price_fields else 'model')
        if kind not in ('model', 'price') or (kind == 'price' and not price_fields):
            raise NoticeRejected('notice_no_qualified_price_or_model')
        if kind == 'price':
            packet['fields']['prices'] = price_fields
    p = item['payload']
    return {**packet, 'kind': kind, 'source_id': item['source_id'], 'item_id': item['id'],
            'source_url': item['url'], 'source_hash': p['content_hash'], 'publisher': p['publisher'],
            'source_title': p['title'], 'source_published_at': p['published_at']}
