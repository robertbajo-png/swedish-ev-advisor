"""Private BMW AC-option preparation. No AI, canonical writes or publisher."""
import re
from datetime import datetime, timezone
from decimal import Decimal

from news_bmw_charging import (VARIANT, NUMBER, ChargingNotSupported, ChargingRejected,
                               evidence, number, one, validate_source)
from news_notices import sv
from news_store import artifact_hash

RECIPE = 'news-bmw-ac-option-private-2026-10-v1'
REVIEW = 'bmw_ac_option_source_review_v1'


def parse_ac_option(text):
    """Text-shape regression helper, not source validation or article approval."""
    block = one(text,
        r'The BMW (?P<model>iX[1-9]) \(BMW (?P<variant>' + VARIANT + r'):'
        r'[^?]{1,1200}?\) will in future offer the AC charging Professional option\. '
        r'This supports AC charging at up to (?P<ac_kw>' + NUMBER + r') kW '
        r'and also includes the Vehicle-to-Load function\. '
        r'The vehicle can then be used as a mobile power bank and supply external '
        r'electrical devices with up to (?P<v2l_kw>' + NUMBER + r') kW of power\.', 'ac_option_block')
    if not block['variant'].casefold().startswith(block['model'].casefold() + ' '):
        raise ChargingRejected('bmw_ac_option_model_variant_conflict')
    ac_kw, v2l_kw = number(block['ac_kw'], 1, 44), number(block['v2l_kw'], Decimal('0.1'), 25)
    market = one(text, r'All descriptions of model variants, equipment, technical data, consumption '
        r'and emission values are for vehicles as offered on the (?P<market>German) market\.', 'ac_market_qualification')
    preliminary = one(text, r'All technical data are (?P<status>preliminary)\.', 'ac_preliminary_qualification')
    # Unsupported competing ratings/standard-equipment claims must not silently
    # override the exact optional-equipment block, even in a mixed-model update.
    ratings = {number(m, 1, 1000) for m in re.findall(
        r'\bAC charging (?:at up to |rate of |at )(' + NUMBER + r') kW\b', text, re.I)}
    if ratings != {ac_kw} or re.search(
            r'\bAC charging Professional\b[^.!?]{0,140}\bstandard\b|'
            r'\bstandard\b[^.!?]{0,140}\bAC charging Professional\b', text, re.I):
        raise ChargingRejected('bmw_ac_option_conflicting_equipment_or_rating')
    if re.search(r'\bpre-?condition(?:ing|ed)\b|\b(?:battery|ambient) temperatures?\b|'
                 r'\b(?:ideal|optimal) conditions\b|subject to (?:approval|homologation)', text, re.I):
        raise ChargingRejected('bmw_ac_option_unparsed_conditions')
    return {'ac_option': evidence(block, {'variant': 'BMW ' + block['variant'],
                'equipment': 'AC Charging Professional', 'equipment_status': 'announced_future_option',
                'current': 'AC', 'max_kw': ac_kw, 'power_limit': 'up_to',
                'v2l_max_kw': v2l_kw, 'v2l_direction': 'vehicle_to_external_devices_not_battery_charging'}),
            'market': evidence(market, {'country': 'DE'}),
            'qualification': evidence(preliminary, {'technical_data_status': 'preliminary'})}


def extract_ac_option(item, source, now=None):
    now = now or datetime.now(timezone.utc)
    validate_source(item, source, now)
    p = item['payload']
    if not re.fullmatch(r'BMW model updates, (?:spring|summer|autumn|winter) \d{4}\.?', p.get('title', ''), re.I):
        raise ChargingNotSupported('bmw_ac_option_update_layout_requires_adapter')
    fields = parse_ac_option(p['content'])
    return {'recipe': RECIPE, 'subject': fields['ac_option']['value']['variant'], 'fields': fields,
        'source': {'item_id': item['id'], 'source_id': source['id'], 'url': item['url'],
            'publisher': source['name'], 'title': p['title'], 'published_at': p['published_at'],
            'fetched_at': p['fetched_at'], 'hash': p['content_hash']},
        'selection': {'coverage': 'partial', 'absence_claims_supported': False,
            'no_inference_for': ['Swedish_availability', 'Swedish_prices', 'standard_equipment',
                                'DC_charging', 'charging_duration', 'canonical_vehicle_specs']}}


def render_ac_private(packet):
    f, ref = packet['fields'], packet['source']
    ac = f['ac_option']['value']
    return {'editorial_recipe': RECIPE, 'status': 'private_preview', 'publication_supported': False,
        'title': f"BMW aviserar AC-tillval f\u00f6r {packet['subject'].removeprefix('BMW ')}",
        'intro': f"BMW beskriver ett kommande tillval f\u00f6r {packet['subject']}: AC Charging Professional.",
        'paragraphs': [
            {'text': f"Med tillvalet anger BMW upp till {sv(ac['max_kw'])} kW vid laddning med v\u00e4xelstr\u00f6m (AC).", 'kind': 'reporting', 'fact_ids': ['ac_option']},
            {'text': f"Tillvalet omfattar ocks\u00e5 Vehicle-to-Load, som kan f\u00f6rs\u00f6rja externa elektriska apparater med upp till {sv(ac['v2l_max_kw'])} kW. Den effekten avser str\u00f6muttaget, inte laddningen av bilens batteri.", 'kind': 'reporting', 'fact_ids': ['ac_option']},
            {'text': 'Uppgifterna g\u00e4ller den tyska marknaden. BMW betecknar de tekniska v\u00e4rdena som prelimin\u00e4ra.', 'kind': 'reporting', 'fact_ids': ['market', 'qualification']},
        ], 'intro_fact_ids': ['ac_option'], 'category': 'laddning', 'brands': ['BMW'],
        'related_models': [], 'image': None,
        'sources': [{k: ref[k] for k in ('url', 'publisher', 'title', 'published_at')}],
        'editorial_method': 'Privat regelbaserad AC-notis, inte AI-granskad'}


def review_ac_private(article, packet, item, source, now=None):
    errors = []
    try:
        expected = extract_ac_option(item, source, now)
        if packet != expected:
            errors.append('bmw_ac_option_facts_changed')
        if article != render_ac_private(expected):
            errors.append('bmw_ac_option_preview_changed')
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc)[:180])
    try:
        count = len(' '.join([article.get('intro', ''), *[p['text'] for p in article.get('paragraphs', [])]]).split())
    except (KeyError, TypeError, AttributeError):
        count = 0
        errors.append('bmw_ac_option_invalid_preview_shape')
    return {'method': REVIEW, 'passed': not errors, 'errors': errors,
        'article_hash': artifact_hash(article), 'source_hash': item.get('payload', {}).get('content_hash'),
        'word_count': count, 'ai_audit_performed': False, 'publication_supported': False}


def prepare_ac_option(item, source, now=None):
    packet = extract_ac_option(item, source, now)
    article = render_ac_private(packet)
    return packet, article, review_ac_private(article, packet, item, source, now)
