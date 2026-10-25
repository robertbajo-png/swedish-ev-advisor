"""Bounded BMW charging-demonstration facts and private previews. No publisher or AI."""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlsplit

from news_http import canonical_url, iso_date, require_recent_publication
from news_notices import sv
from news_store import artifact_hash

RECIPE = 'news-bmw-charging-private-2026-10-v1'
REVIEW = 'bmw_charging_source_review_v1'
HOST = 'www.press.bmwgroup.com'
NUMBER = r'\d+(?:[.,]\d+)?'
VARIANT = r'iX[1-9] M?\d{2,3} (?:xDrive|sDrive)'


class ChargingNotSupported(ValueError):
    pass


class ChargingRejected(ValueError):
    pass


def validate_source(item, source, now):
    p = item.get('payload', {})
    if (source.get('id') != 'bmw-press' or item.get('source_id') != 'bmw-press'
            or source.get('kind') != 'primary' or p.get('source_kind') != 'primary'
            or source.get('name') != 'BMW Group PressClub' or p.get('publisher') != source['name']):
        raise ChargingRejected('bmw_charging_official_source_required')
    try:
        url = canonical_url(item['url'])
        website = canonical_url(source['website'])
        if (url != item['url'] or p.get('final_url') != url or urlsplit(url).hostname != HOST
                or urlsplit(url).query or urlsplit(url).fragment or website.rstrip('/') != 'https://' + HOST
                or not re.fullmatch(r'/global/article/detail/T\d+EN/[^/]+', urlsplit(url).path)):
            raise ValueError('source_url')
        fetched = datetime.fromisoformat(iso_date(p.get('fetched_at')) or '')
        if not -timedelta(minutes=5) <= now-fetched <= timedelta(days=1):
            raise ValueError('source_fetch_age')
    except (KeyError, TypeError, ValueError) as exc:
        raise ChargingRejected('bmw_charging_invalid_source_metadata:' + str(exc)[:100]) from exc
    content = p.get('content')
    if (p.get('access_status') != 'accessible' or not isinstance(content, str) or not content
            or hashlib.sha256(content.encode()).hexdigest() != p.get('content_hash')):
        raise ChargingRejected('bmw_charging_source_hash_or_access_invalid')
    try:
        require_recent_publication(p.get('published_at'), now)
    except ValueError as exc:
        raise ChargingRejected('bmw_charging_invalid_source_metadata:' + str(exc)[:100]) from exc


def one(text, pattern, reason):
    found = list(re.finditer(pattern, text, re.I))
    if not found or len({tuple(m.groupdict().items()) for m in found}) != 1:
        raise ChargingRejected('bmw_charging_missing_or_conflicting_' + reason)
    return found[0]


def number(value, minimum, maximum):
    value = Decimal(value.replace(',', '.'))
    if not value.is_finite() or not minimum <= value <= maximum:
        raise ChargingRejected('bmw_charging_numeric_bounds')
    return format(value.normalize(), 'f')


def evidence(match, value):
    return {'value': value, 'quote': match[0], 'start': match.start(), 'end': match.end()}


def charging_layout(title, content):
    """Triage hints only: no values, freshness override or publication approval."""
    title, content = str(title).casefold(), str(content).casefold()
    if ('join forces to demonstrate high-power-charging' in content
            or 'technology demonstration' in content and 'faster charging for the' in content):
        return 'high_power_demonstration'
    if 'long wheelbase' in title and 'cltc' in content:
        return 'china_cltc_vehicle_specs'
    if ('v2g' in title or 'vehicle-to-grid' in title or 'e.on' in title
            and re.search(r'\btariff|\bbonus|\bcontract', content)):
        return 'v2g_offer'
    if 'provisional' in content and re.search(r'\bcharging|\bcharge', content):
        return 'provisional_vehicle_charging'
    if re.search(r'\boptional\b[^.]{0,160}\bac charging professional\b|'
                 r'\bac charging professional\b[^.]{0,160}\boption(?:al)?\b', content):
        return 'ac_option_update'
    if ('charging network' in content and ('holiday travel' in title or 'network' in title)):
        return 'charging_network'
    if re.search(r'\bdc charging|\bmaximum charging', content):
        return 'vehicle_charging_specs'
    return 'other_bmw_release'


def extract_charging(item, source, now=None):
    now = now or datetime.now(timezone.utc)
    validate_source(item, source, now)
    p, title = item['payload'], item['payload'].get('title', '')
    if not re.search(r'\bcharging\b', title, re.I):
        raise ChargingNotSupported('bmw_charging_headline_not_supported')
    layout = charging_layout(title, p['content'])
    if layout != 'high_power_demonstration':
        raise ChargingNotSupported('bmw_charging_layout_requires_adapter:' + layout)
    if re.search(r'\bprovisional\b|\bpreliminary\b|\bpre-?condition(?:ing|ed)\b|'
                 r'\b(?:battery|ambient) temperatures?\b|\b(?:ideal|optimal) conditions\b|'
                 r'subject to (?:approval|homologation)', p['content'], re.I):
        raise ChargingRejected('bmw_charging_unparsed_test_conditions')
    headline = one(title, r'up to (?P<power>' + NUMBER + r') kW for the new BMW (?P<variant>' + VARIANT + r')\b', 'headline_scope')
    variant = headline['variant']
    text = p['content']
    location = one(text, r'\A(?P<city>[A-Za-z][A-Za-z ]{1,60}) / USA\.', 'us_event_location')
    event = one(text, r'BMW Group, IONNA and Alpitronic join forces to demonstrate High-Power-Charging '
                r'as a part of an International Media Event\.', 'demonstration_event')
    block = one(text, r'Faster Charging for the (?P<variant>' + VARIANT + r') means: up to '
        r'(?P<power>' + NUMBER + r') kW peak DC Charging Power and adding a range of up to '
        r'(?P<miles>' + NUMBER + r') miles \((?P<km>' + NUMBER + r') km\) in only '
        r'(?P<gain_minutes>' + NUMBER + r') minutes \((?P<cycle>[A-Za-z]+)\)\. '
        r'Charging the (?P<battery>' + NUMBER + r') kWh battery pack \((?P<basis>[A-Za-z]+)\) from '
        r'(?P<low>\d+) to (?P<high>\d+) per cent takes just (?P<minutes>' + NUMBER + r') minutes\.', 'vehicle_charging_block')
    qualification = one(text, r'The (?P<power>' + NUMBER + r') kW experience is a technology demonstration '
        r'and does not represent charging hardware commercially available in the U\.S\. today\.', 'commercial_scope')
    power = number(block['power'], 20, 600)
    if (variant.casefold() != block['variant'].casefold()
            or number(headline['power'], 20, 600) != power or number(qualification['power'], 20, 600) != power):
        raise ChargingRejected('bmw_charging_variant_or_power_conflict')
    # Additional stated maxima are not silently treated as this vehicle's rating.
    maxima = {number(m, 20, 2000) for m in re.findall(r'up to (' + NUMBER + r') kW\b', text, re.I)}
    if maxima != {power}:
        raise ChargingRejected('bmw_charging_ambiguous_power_scope')
    if block['cycle'].upper() != 'WLTP' or block['basis'].casefold() != 'net':
        raise ChargingRejected('bmw_charging_measurement_or_capacity_basis_unsupported')
    low, high = int(block['low']), int(block['high'])
    if not 0 <= low < high <= 100:
        raise ChargingRejected('bmw_charging_invalid_charge_window')
    fields = {
        'event': evidence(event, {'kind': 'technology_demonstration', 'participants': ['BMW Group', 'IONNA', 'Alpitronic'],
                                  'evidence_basis': 'manufacturer_report'}),
        'location': evidence(location, {'city': location['city'], 'country': 'US'}),
        'charging': evidence(block, {'variant': 'BMW ' + variant, 'current': 'DC', 'peak_kw': power,
            'power_limit': 'up_to', 'power_basis': 'peak_not_average',
            'range_added_km': number(block['km'], 1, 1500), 'range_added_miles': number(block['miles'], 1, 1000),
            'range_added_limit': 'up_to', 'range_measurement': 'WLTP', 'range_metric': 'range_added_not_total_range',
            'range_added_minutes': number(block['gain_minutes'], 1, 120),
            'battery_kwh': number(block['battery'], 10, 250), 'battery_basis': 'net',
            'from_percent': low, 'to_percent': high, 'charge_minutes': number(block['minutes'], 1, 180)}),
        'commercial_scope': evidence(qualification, {'country': 'US',
            'status': 'demonstration_not_commercially_available_charging_hardware_at_source_date'}),
    }
    return {'recipe': RECIPE, 'subject': 'BMW ' + variant, 'fields': fields,
        'source': {'item_id': item['id'], 'source_id': source['id'], 'url': item['url'], 'publisher': source['name'],
                   'title': title, 'published_at': p['published_at'], 'fetched_at': p['fetched_at'], 'hash': p['content_hash']},
        'selection': {'coverage': 'partial', 'absence_claims_supported': False,
                      'no_inference_for': ['Swedish_availability', 'Swedish_prices', 'total_vehicle_range',
                                           'charging_curve', 'average_charging_power', 'canonical_vehicle_specs']}}


def render_private(packet):
    f, ref = packet['fields'], packet['source']
    c, location, subject = f['charging']['value'], f['location']['value'], packet['subject']
    return {'editorial_recipe': RECIPE, 'status': 'private_preview', 'publication_supported': False,
        'title': f"BMW uppger upp till {sv(c['peak_kw'])} kW vid ladddemonstration i USA",
        'intro': f"BMW har tillsammans med IONNA och Alpitronic demonstrerat snabbladdning f\u00f6r {subject} i {location['city']}, USA. Den uppgivna toppeffekten f\u00f6r likstr\u00f6msladdning \u00e4r upp till {sv(c['peak_kw'])} kW.",
        'paragraphs': [
            {'text': f"F\u00f6r bilens batteri p\u00e5 {sv(c['battery_kwh'])} kWh netto anger BMW {sv(c['charge_minutes'])} minuter fr\u00e5n {c['from_percent']} till {c['to_percent']} procents laddniv\u00e5.", 'kind': 'reporting', 'fact_ids': ['charging']},
            {'text': f"Tillverkaren anger ocks\u00e5 upp till {sv(c['range_added_km'])} kilometers tillf\u00f6rd r\u00e4ckvidd enligt WLTP p\u00e5 {sv(c['range_added_minutes'])} minuter. Det \u00e4r tillf\u00f6rd r\u00e4ckvidd under laddning, inte bilens totala r\u00e4ckvidd.", 'kind': 'reporting', 'fact_ids': ['charging']},
            {'text': 'BMW beskriver laddningen som en teknikdemonstration som inte motsvarar laddh\u00e5rdvara som var kommersiellt tillg\u00e4nglig i USA n\u00e4r pressmeddelandet publicerades.', 'kind': 'reporting', 'fact_ids': ['commercial_scope']},
        ],
        'category': 'laddning', 'brands': ['BMW'], 'related_models': [], 'image': None,
        'intro_fact_ids': ['event', 'location', 'charging'],
        'sources': [{k: ref[k] for k in ('url', 'publisher', 'title', 'published_at')}],
        'editorial_method': 'Privat regelbaserad laddnyhet, inte AI-granskad'}


def review_private(article, packet, item, source, now=None):
    errors = []
    try:
        expected = extract_charging(item, source, now)
        if packet != expected:
            errors.append('bmw_charging_facts_changed')
        if article != render_private(expected):
            errors.append('bmw_charging_preview_changed')
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc)[:180])
    try:
        count = len(' '.join([article.get('intro', ''), *[p['text'] for p in article.get('paragraphs', [])]]).split())
    except (KeyError, TypeError, AttributeError):
        count = 0
        errors.append('bmw_charging_invalid_preview_shape')
    return {'method': REVIEW, 'passed': not errors, 'errors': errors,
        'article_hash': artifact_hash(article), 'source_hash': item.get('payload', {}).get('content_hash'),
        'word_count': count,
        'ai_audit_performed': False, 'publication_supported': False}


def prepare_bmw_charging(item, source, now=None):
    p = item.get('payload', {})
    if charging_layout(p.get('title', ''), p.get('content', '')) == 'ac_option_update':
        from news_bmw_ac_option import prepare_ac_option
        return prepare_ac_option(item, source, now)
    packet = extract_charging(item, source, now)
    article = render_private(packet)
    return packet, article, review_private(article, packet, item, source, now)
