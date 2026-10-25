"""Narrow, lossless writing cards and source-bound additions; never article templates."""
import hashlib
import re


def plain(text):
    return ' '.join(str(text).split())


def neutral_facts(facts):
    result = []
    for fact in facts:
        statement = fact['statement']
        match = re.fullmatch(r'(?:Redan )?(.+?) har en (?:omfattande|rik) standardutrustning, däribland (.+?)[.]?', statement)
        if match:
            statement = match[1] + ' har som standard bland annat ' + match[2].rstrip('.') + '.'
        result.append({**fact, 'statement': statement,
                       **({'source_statement': fact['statement']} if statement != fact['statement'] else {})})
    return result


def writing_card(statement):
    """Only complete recognized statements become cards; unrecognized scope stays intact."""
    text = plain(statement).rstrip('.')
    number = r'(\d+(?:[,.]\d+)?)'
    match = re.fullmatch(r'Batteriet på ' + number + r' kWh \(netto\) ger en räckvidd på upp till ' + number + r' km \(WLTP\)', text)
    if match:
        return {'battery': {'kwh': match[1], 'capacity_basis': 'net'},
                'range': {'km': match[2], 'limit': 'up_to', 'measurement': 'WLTP'}}
    match = re.fullmatch(r'Batteriet på ' + number + r' kWh ger en räckvidd på upp till ' + number + r' km enligt WLTP', text)
    if match:
        return {'battery': {'kwh': match[1], 'capacity_basis': 'not_stated'},
                'range': {'km': match[2], 'limit': 'up_to', 'measurement': 'WLTP'}}
    match = re.fullmatch(r'Två effektnivåer erbjuds: ' + number + r' hk \(' + number + r' kW\) och ' + number + r' hk \(' + number + r' kW\)', text)
    if match:
        return {'motor_power_options': [{'hk': match[1], 'kw': match[2]}, {'hk': match[3], 'kw': match[4]}],
                'motor_power_option_meaning': 'offered_power_ratings_not_driver_selectable_modes'}
    match = re.fullmatch(r'DC-snabbladdning(?: sker)? med ' + number + r' kW från (\d+) till (\d+) procent på (cirka|ca) ' + number + r' minuter', text)
    if match:
        return {'charging': {'current': 'DC', 'power_kw': match[1], 'from_percent': match[2],
                             'to_percent': match[3], 'duration_minutes': match[5], 'duration_basis': 'approximate',
                             'power_basis': 'stated_not_explicit_maximum'}}
    match = re.fullmatch(r'AC-laddningskapaciteten är som mest ' + number + r' kW', text)
    if match:
        return {'charging': {'current': 'AC', 'power_kw': match[1], 'power_basis': 'explicit_maximum'}}
    match = re.fullmatch(r'Bagageutrymmesvolym: ' + number + r' liter \+ ' + number + r' liter frunk', text)
    if match:
        return {'cargo_liters': match[1], 'frunk_liters': match[2]}
    match = re.fullmatch(r'Bagaget rymmer (\d+) liter, frunken (\d+) liter och bagaget med baksätets ryggstöd nedfällt (\d+) liter', text)
    if match:
        return {'cargo_liters': match[1], 'frunk_liters': match[2],
                'folded_rear_backrest_cargo_liters': match[3]}
    match = re.fullmatch(r'(.+?) inleder nu förförsäljningen av (?:nya )?(.+?) med ett batteri på ' + number + r' kWh', text)
    if match:
        return {'event': 'preorders_open', 'manufacturer': match[1], 'model': match[2], 'battery_kwh': match[3]}
    match = re.fullmatch(r'(?:Nya )?(.+?) lanseras på den svenska marknaden vid månadsskiftet ([a-zåäö]+)/([a-zåäö]+)', text)
    if match:
        months = 'januari februari mars april maj juni juli augusti september oktober november december'.split()
        first, second = match[2], match[3]
        if (first not in months or second not in months or months[(months.index(first) + 1) % 12] != second
                or re.search(r'\b(?:(?:för)?väntas|tros|ska|kan|planeras|beräknas|troligen|preliminärt|eventuellt|kommer|möjligen|inte)\b', match[1], re.I)):
            return {'statement': statement}
        return {'event': 'market_launch', 'model': match[1], 'market': 'Sweden',
                'timing': {'boundary_months': [first, second], 'precision': 'month_boundary',
                           'year_basis': 'not_stated'}}
    match = re.fullmatch(
        r'(?:[Gg]rundversionen|[Ii]nstegsversionen) '
        r'(?P<version>[A-ZÅÄÖ][\w-]*(?: [A-ZÅÄÖ0-9][\w-]*){0,3}) har '
        r'(?P<standard>som standard bland annat )?parkeringssensorer fram och bak '
        r'samt smartphoneintegrering via (?:App Connect|”App Connect”|“App Connect”|"App Connect")', text)
    if match:
        return {'version': {'name': match['version'], 'role': 'entry_level'},
                'equipment_status': 'standard' if match['standard'] else 'stated',
                'equipment_includes': [
                    {'function': 'parking_sensors', 'positions': ['front', 'rear']},
                    {'function': 'smartphone_integration', 'system': 'App Connect'},
                ]}
    if text == 'De faktiska WLTP-värdena för räckvidd kan variera beroende på utrustning':
        return {'qualification': {'measurement': 'WLTP range', 'depends_on': ['equipment']}}
    if text == ('Tiden tills batteriet är fulladdat beror på laddinfrastrukturens effekt vid AC- och DC-laddning '
                'samt på batteriets laddningsnivå och utomhustemperaturen'):
        return {'qualification': {'measurement': 'time_until_full_charge', 'current': ['AC', 'DC'],
                                  'depends_on': ['charging_infrastructure_power', 'battery_charge_level', 'outdoor_temperature']}}
    return {'statement': statement}


def writer_plan(plan):
    def slot(value):
        return {key: item for key, item in value.items() if key != 'statements'} | {
            'facts': [writing_card(statement) for statement in value['statements']]}
    return {'version': plan['version'], 'title': slot(plan['title']), 'intro': slot(plan['intro']),
            'paragraphs': [slot(value) for value in plan['paragraphs']],
            'source_context': [slot(value) for value in plan['source_context']],
            'buyer_question': slot(plan['buyer_question'])}


def technical_evidence(fields, match):
    """Return only whole adjacent labelled fields, never an arbitrary word fragment."""
    labels = (r'Drivsystem|Batteristorlek \(netto\)|Effekt|Räckvidd \(WLTP\)|Maximalt vridmoment|'
              r'Acceleration, 0-100 km/h|Energiförbrukning, blandad körning WLTP|CO2-utsläpp, blandad körning|'
              r'DC-laddningskapacitet \(max\.\)|Laddningstid DC, 10-80 %|AC-laddningskapacitet \(max\.\)|'
              r'Topphastighet|Längd/bredd/höjd/axelavstånd|Max\. släpvagnsvikt|Tjänstevikt|Bagageutrymmesvolym')
    starts = [m.start() for m in re.finditer(r'(?<!\S)(?:' + labels + r'): ', fields)]
    if match.start() not in starts:
        return None
    ends = [*(start - 1 for start in starts[1:]), len(fields)]
    index = starts.index(match.start())
    if fields[starts[index]:ends[index]].strip() != match[0]:
        return None
    candidates = []
    for left in range(index + 1):
        for right in range(index, len(starts)):
            quote = fields[starts[left]:ends[right]].strip()
            count = len(quote.split())
            if 8 <= count <= 24:
                candidates.append(((count, index - left, right - left), quote))
    return min(candidates)[1] if candidates else None


def source_technical_facts(item, existing):
    """Recognized whole fields within one exact model/battery section; never guesses."""
    payload = item['payload']
    content = payload.get('content', '')
    if (payload.get('source_kind') != 'primary' or payload.get('access_status') != 'accessible'
            or payload.get('content_hash') != hashlib.sha256(content.encode()).hexdigest()
            or plain(content) != content):
        return []
    sections = list(re.finditer(r'Tekniska data för (?P<model>.+?) med (?P<battery>\d+(?:[,.]\d+)?) kWh-batteriet '
                               r'(?P<fields>.*?)(?=Räckvidden har fastställts|$)', content))
    if content.count('Tekniska data för ') != 1 or len(sections) != 1 or len(sections[0]['fields']) > 12000:
        return []
    section = sections[0]
    # Require the exact model AND battery in an existing statement; never borrow another model's table.
    scope_ok = any(plain(section['model']).casefold() in plain(f['statement']).casefold()
                   and re.search(r'(?<![\d,.])' + re.escape(section['battery']) + r' kWh\b', f['statement'])
                   for f in existing if f.get('item_id') == item['id'])
    if not scope_ok:
        return []
    heading = content[section.start():section.start('fields')].strip()
    if not 8 <= len(heading.split()) <= 24:
        return []
    fields = section['fields'].rstrip()
    boundary = r'(?= (?:Topphastighet|Max\. släpvagnsvikt|Tjänstevikt|Bagageutrymmesvolym|Längd/bredd/höjd/axelavstånd):|$)'
    patterns = {
        'ac_power': r'AC-laddningskapacitet \(max\.\): (?P<value>\d+(?:[,.]\d+)?) kW\b' + boundary,
        'braked_tow': r'Max\. släpvagnsvikt: (?P<value>\d+) kg \(bromsat, både (?P<slope1>\d+) % och (?P<slope2>\d+) % lutning\)' + boundary,
        'cargo': r'Bagageutrymmesvolym: (?P<value>\d+) liter \+ (?P<frunk>\d+) liter frunk '
                 r'\(med baksätets ryggstöd nedfällt: (?P<folded>\d{1,3}(?: \d{3})?|\d{4}) liter\)' + boundary,
    }
    result = []
    for kind, pattern in patterns.items():
        matches = list(re.finditer(pattern, fields))
        label = {'ac_power': 'AC-laddningskapacitet', 'braked_tow': 'Max. släpvagnsvikt',
                 'cargo': 'Bagageutrymmesvolym'}[kind]
        if len(matches) != 1 or fields.count(label) != 1:
            continue
        match = matches[0]
        value = float(match['value'].replace(',', '.'))
        if not 0 < value <= (100 if kind == 'ac_power' else 4000):
            continue
        if kind == 'cargo' and not (0 <= int(match['frunk']) <= 500
                                   and value <= int(match['folded'].replace(' ', '')) <= 4000):
            continue
        evidence = technical_evidence(fields, match)
        if not evidence or evidence not in content:
            continue
        if kind == 'cargo':
            folded = match['folded'].replace(' ', '')
            statement = (f'Bagaget rymmer {match["value"]} liter, frunken {match["frunk"]} liter och '
                         f'bagaget med baksätets ryggstöd nedfällt {folded} liter.')
            # A partly overlapping cargo fact must not gain a second prose home.
            if any(f.get('item_id') == item['id'] and re.search(r'bagage|bagaget|frunk|cargo|boot volume',
                                                              f['statement'], re.I) for f in existing):
                continue
        else:
            statement = (f'AC-laddningskapaciteten är som mest {match["value"]} kW.' if kind == 'ac_power' else
                         f'Den bromsade släpvagnsvikten är högst {match["value"]} kg vid både {match["slope1"]} och {match["slope2"]} procents lutning.')
        if any(f.get('item_id') == item['id'] and (f['statement'] == statement or
               (re.search(r'AC[- ]ladd\w*[^.!?]*' + re.escape(match['value']) + r' kW\b', f['statement'])
                if kind == 'ac_power' else (re.search(r'släpvagn\w*[^.!?]*' + re.escape(match['value']) + r' kg\b', f['statement'])
                                            if kind == 'braked_tow' else False)))
               for f in existing):
            continue
        digest = hashlib.sha256((heading + '\n' + match[0]).encode()).hexdigest()[:12]
        result.append({'id': item['id'] + ':t' + digest, 'statement': statement, 'evidence': evidence,
                       'field_evidence': match[0],
                       'scope_evidence': heading, 'scope': {'model': section['model'], 'battery_kwh': section['battery']},
                       'central': True, 'item_id': item['id'], 'publisher': payload['publisher'],
                       'source_hash': payload['content_hash'], 'origin': 'literal_technical_field', 'technical_field': kind})
    return result
