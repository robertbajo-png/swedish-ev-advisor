"""Literal ACEA EU registration fields, not a general statistical inference engine."""
import hashlib
import re
import unicodedata
from urllib.parse import urlsplit

MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
          'September', 'October', 'November', 'December']
SV_MONTHS = ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti',
             'september', 'oktober', 'november', 'december']
WORDS = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve']
PCT = r'\d+(?:\.\d+)?'
COUNT = r'(?:\d{1,3}(?:,\d{3})+|\d+)'
ORIGIN = 'literal_statistical_field'


def source_statistical_facts(item):
    p = item['payload']
    content = p.get('content', '')
    url = urlsplit(item['url'])
    if (item.get('source_id') != 'acea' or p.get('source_kind') != 'primary'
            or p.get('access_status') != 'accessible' or url.scheme != 'https'
            or url.hostname not in {'www.acea.auto', 'acea.auto'}
            or not url.path.startswith('/pc-registrations/')
            or p.get('content_hash') != hashlib.sha256(content.encode()).hexdigest()):
        return []

    def one(pattern):
        found = list(re.finditer(pattern, content))
        return found[0] if len(found) == 1 else None

    base = one(r'Up until (?P<month>' + '|'.join(MONTHS) + r') (?P<year>20\d{2})\s*, '
               r'(?P<quote>battery-electric cars secured a (?P<value>' + PCT + r')% share of the EU market, '
               r'up from (?P<prior>' + PCT + r')% a year earlier)\.')
    if not base:
        return []
    month, year = base['month'], base['year']
    index = MONTHS.index(month)
    # Confirm the actual January-through-month period, not an isolated month/share.
    units = one(r'In the first ' + WORDS[index] + r' months of ' + year + r'\s*, '
                r'(?P<count>' + COUNT + r') new battery-electric cars were registered, capturing '
                + re.escape(base['value']) + r'% of the EU market'
                r'(?: and establishing them as the second most popular powertrain choice year-to-date)?\.')
    if not units or any(not 0 <= float(base[k]) <= 100 for k in ['value', 'prior']):
        return []
    scope_quote = content[base.start():base.start('quote')] + ' '.join(base['quote'].split()[:10])
    if not 8 <= len(scope_quote.split()) <= 24 or scope_quote not in content:
        return []
    common = {'market': 'EU', 'period': 'year_to_date', 'year': year,
              'through_month': month, 'denominator': 'new_passenger_car_registrations'}
    result = []

    def add(key, powertrain, quote, values):
        if not 8 <= len(quote.split()) <= 24 or quote not in content:
            return
        if any(not 0 <= float(value) <= (100 if 'share' in key else 100000000) for value in values.values()):
            return
        statistic = {**common, 'powertrain': powertrain, 'metric': key, 'values': values}
        value_text = '; '.join(name + '=' + value for name, value in values.items())
        statement = (f'EU new passenger car registrations; January-{month} {year}; '
                     f'{powertrain}; {key}: {value_text}.')
        digest = hashlib.sha256((statement + quote + scope_quote).encode()).hexdigest()[:12]
        result.append({'id': 's' + digest, 'statement': statement, 'evidence': quote,
                       'central': True, 'origin': ORIGIN, 'source_hash': p['content_hash'],
                       'scope_evidence': scope_quote, 'statistic': statistic})

    add('market_share_percent', 'battery-electric', base['quote'], {'current': base['value'], 'previous_same_period': base['prior']})
    # The grammatical prefix is complete evidence for the count/market/period;
    # ranking text after it is deliberately not extracted as another fact.
    count_quote = units[0].split(' and establishing')[0].rstrip('.')
    add('units', 'battery-electric', count_quote, {'current': units['count'].replace(',', '')})
    patterns = [
        ('market_share_percent', 'hybrid-electric',
         r'Hybrid-electric car registrations captured (?P<value>' + PCT + r')% of the market, remaining the preferred choice among EU consumers\.'),
        ('market_share_percent', 'petrol-and-diesel',
         r'At the same time, the combined market share of petrol and diesel cars fell to (?P<value>' + PCT + r')%, compared with (?P<prior>' + PCT + r')% a year earlier\.'),
        ('units', 'plug-in-hybrid',
         r'Plug-in-hybrid electric car registrations continued to grow, reaching (?P<value>' + COUNT + r') units in January-' + month + r' ' + year + r'\s*\.'),
        ('market_share_percent', 'plug-in-hybrid',
         r'New plug-in-hybrid electric cars represent (?P<value>' + PCT + r')% of EU registrations, up from (?P<prior>' + PCT + r')% over the same period in ' + str(int(year) - 1) + r'\.'),
    ]
    previous = base
    for key, powertrain, pattern in patterns:
        match = one(pattern)
        if powertrain in {'hybrid-electric', 'petrol-and-diesel'}:
            # These sentences inherit period/market only inside the contiguous block.
            if not match or not previous or content[previous.end():match.start()].strip():
                previous = None
                continue
            previous = match
        if match:
            values = {'current': match['value'].replace(',', '')}
            if 'prior' in match.groupdict():
                values['previous_same_period'] = match['prior']
            add(key, powertrain, match[0], values)
    hybrid_count = one(re.escape(month + ' ' + year) + r' YTD\S* figures also showed '
                       r'(?P<quote>new EU hybrid-electric car registrations rising to (?P<value>' + COUNT + r') units)')
    if hybrid_count:
        add('units', 'hybrid-electric', hybrid_count['quote'], {'current': hybrid_count['value'].replace(',', '')})
    total_growth = one(r'The (?P<quote>new EU passenger car market showed notable resilience, '
                       r'rising (?P<value>' + PCT + r')% year-to-date) despite a challenging macroeconomic environment')
    if total_growth:
        add('year_to_date_change_percent', 'all_powertrains', total_growth['quote'], {'current': total_growth['value']})
    return result if len(result) >= 3 else []


def valid_statistical_fact(fact, item):
    fields = ['statement', 'evidence', 'origin', 'source_hash', 'scope_evidence', 'statistic']
    return any(all(fact.get(key) == candidate.get(key) for key in fields)
               for candidate in source_statistical_facts(item))


def statistical_numbers(text):
    # Unambiguous Swedish thousands groups; a single comma stays a decimal mark.
    text = re.sub(r'(?<![\d.,])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?!\d|[.,]\d)',
                  lambda match: re.sub(r'\s', '', match[0]), text)
    return set(re.findall(r'(?<!\w)\d+(?:\.\d+)?', text.replace(',', '.')))


def statistical_scope_errors(blocks, facts):
    by_id = {fact['id']: fact for fact in facts}
    errors = []
    for block in blocks:
        cited = [by_id[key] for key in block.get('fact_ids', []) if key in by_id]
        scoped = [fact['statistic'] for fact in cited if fact.get('origin') == ORIGIN and fact.get('statistic')]
        if not scoped or block['kind'] == 'analysis':
            continue
        text = unicodedata.normalize('NFKD', block['text']).encode('ascii', 'ignore').decode().lower()
        periods = list(re.finditer(r'\bjanuari\s*(?:-|till(?: och med)?)\s*(' + '|'.join(SV_MONTHS) + r')\b', text))
        expected_ends = {SV_MONTHS[MONTHS.index(scope['through_month'])] for scope in scoped}
        if any(match[1] not in expected_ends for match in periods):
            errors.append('statistics_period_mismatch:' + block['id'])
        period_text = re.sub(r'\bjanuari\s*(?:-|till(?: och med)?)\s*(?:' + '|'.join(SV_MONTHS) + r')\b', 'year_to_date', text)
        if re.search(r'\b(?:i|under|enbart) (?:manaden )?(?:' + '|'.join(SV_MONTHS)
                + r')\b|\b(?:monthly|kvartal\w*|helaret)\b', period_text):
            errors.append('statistics_period_mismatch:' + block['id'])
        if re.search(r'bilbestand|bilar i trafik|begagnat|vehicle stock|used cars', text):
            errors.append('statistics_denominator_mismatch:' + block['id'])
        if re.search(r'forsaljning|\bsales\b', text):
            errors.append('statistics_metric_mismatch:' + block['id'])
        metrics = {scope['metric'] for scope in scoped}
        if metrics == {'units'} and re.search(r'%|procent|andel|\bshare\b', text):
            errors.append('statistics_metric_mismatch:' + block['id'])
        if metrics == {'year_to_date_change_percent'} and re.search(r'\bandel\w*|market share', text):
            errors.append('statistics_metric_mismatch:' + block['id'])
        if metrics == {'market_share_percent'} and re.search(r'\d+(?:[,.]\d+)? (?:nya )?(?:bilar|elbilar|personbilar)\b', text):
            errors.append('statistics_metric_mismatch:' + block['id'])
        mentioned = set()
        if re.search(r'laddhybrid|plug.in.hybrid', text):
            mentioned.add('plug-in-hybrid')
        without_plugin = re.sub(r'laddhybrid\w*|plug.in.hybrid\w*', '', text)
        if re.search(r'\bhybrid\w*', without_plugin):
            mentioned.add('hybrid-electric')
        if re.search(r'\belbil\w*|batterielektr|battery.electric', text):
            mentioned.add('battery-electric')
        if re.search(r'bensin|diesel|petrol', text):
            mentioned.add('petrol-and-diesel')
        for kind in sorted(mentioned - {scope['powertrain'] for scope in scoped}):
            errors.append('statistics_powertrain_mismatch:' + block['id'] + ':' + kind)
        if all(fact.get('origin') == ORIGIN for fact in cited) and re.search(
                r'\b(?:storsta|minsta|ledande|popularaste|largest|smallest|leading)\b|most popular', text):
            errors.append('statistics_unlicensed_ranking:' + block['id'])
    return errors
