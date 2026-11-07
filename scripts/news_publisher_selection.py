"""Free editorial triage and exact, bounded evidence passages; never approval."""
import re
from urllib.parse import urlsplit
from news_editorial import normalize
from news_http import require_recent_publication, canonical_url

EUROPE = r'\b(?:sweden|swedish|sverige|svensk\w*|nordic|scandinavia\w*|europe\w*|europa|europaisch\w*|europeisk\w*|eu|germany|german|deutschland|deutsch\w*|france|french|norway|norwegian|norge|norsk\w*|francais\w*|allemagne|suede|finland|finnish|denmark|danish|britain|british|united kingdom|uk|switzerland|swiss|schweiz\w*|suisse|austria|austrian|osterreich\w*)\b'
VEHICLE = r'\b(?:evs?|bevs?|electric (?:passenger )?(?:cars?|vehicles?|models?|suvs?|sedans?|crossovers?|mpvs?|saloons?|hatch\w*)|battery electric|elbil\w*|(?:hel)?elektrisk\w* (?:bil\w*|personbil\w*|modell\w*|suv\w*)|eldriv\w* (?:bil\w*|personbil\w*)|(?:voitures?|vehicules?|suvs?|berlines?|crossovers?|monospaces?|citadines?) electriques?|biler? elektrisk\w*|elektroautos?|elektrofahrzeug\w*|elektromodell\w*|(?:voll|rein)?elektrisch\w* (?:autos?|fahrzeug\w*|modelle?|suv\w*))\b'
TECHNOLOGY = r'\b(?:sodium ion|solid state|battery chemistr\w*|energy density|lmr batter\w*|battery recycl\w*|cell to (?:pack|body)|superfast charg\w*|ultra fast charg\w*|800 volt|900 volt|festkorperbatter\w*|natrium ionen batter\w*|energiedichte)\b'
LOCAL_BUSINESS = r'\b(?:dealers?|dealerships?|service network|local subsid\w*|rebates?|tax exemptions?|consumption tax|exempt\w*.*?tax|tax.*?exempt\w*|earnings|profits?|sales milestone|crosses.*?sales|factory|facilit\w*|plant|production line|off grid.*?station|charging station)\b'
SPECULATION = r'\b(?:rumou?rs?|rumeurs?|rykter?|pourrait|spotted|spy shots?|patent|teased|potential|may get|could launch|readers questions|geruchte|erlkonig|konnte (?:kommen|starten|erhalten))\b'
LAUNCH = r'\b(?:launch\w*|unveil\w*|debut\w*|introduc\w*|reveal\w*|arrivera|debarque\w*|lancement\w*|presente\w*|prasentiert|weltpremiere|markteinfuhrung|marktstart|lanser\w*|presenterar)\b'
DEVELOPMENT = LAUNCH + r'|\b(?:update\w*|recall\w*|ruckruf\w*|modellpflege|uppdater\w*|aterkall\w*)\b'
CHARGING_NETWORK = r'\b(?:charg\w* (?:network\w*|stations?|points?|hubs?)|(?:rapid|fast|ultra fast) charg\w*|ladenetz\w*|ladesaul\w*|laddnat\w*|laddstation\w*|reseau\w* de recharge)\b'
NETWORK_CHANGE = r'\b(?:expand\w*|add\w*|open\w*|integrat\w*|connect\w*|roll\w* out|deploy\w*|access|acces|partnership|partenariat|offne\w*|erweiter\w*|utok\w*|oppna\w*|anslut\w*)\b'
PRICE_WORD = r'\b(?:prices?|pricing|price tag|discount\w*|prix|tarifs?|pris(?:er)?|preis\w*|rabatt\w*|\d+k|privatleasing\w*|leasing\w*|lease (?:deal|offer)\w*)\b'
PRICE = PRICE_WORD + r'|\b(?:chf|usd|eur|gbp|cny|rmb|aud|nok|dkk|sek)\s+\d'
PRICE_CHANGE = r'\b(?:cuts?|reduc\w*|discount\w*|rabatt\w*|senk\w*|sank\w*|hoj\w*|price (?:change\w*|increas\w*|drop\w*)|baisse\w*|hausse\w*|leasing\w*|lease (?:deal|offer)\w*)\b'
STORAGE = r'\b(?:bess|stationary storage|home batter\w*|balcony solar|grid storage)\b'
POLITICS = r'\b(?:coalition|election|electrification targets?|35 by 35|vows to scrap)\b'
STOP = set(('the a an and or for with from into over under first new next this that its as at of to in '
            'on by is are will has have been gets get says said reveals reveal announced announces '
            'launch launches launchs launched coming latest electric vehicle vehicles ev evs car cars '
            'battery batteries range charging production model models preview '
            'le la les un une des du de et en pour avec sur dans ce cette ces voiture voitures vehicule vehicules '
            'electrique electriques batterie batteries nouveau nouvelle nouveaux nouvelles '
            'og den det en et til med for som av fra pa bil biler elbil elbiler nye ny').split())
QUALIFICATION = re.compile(r'\b(?:preliminary|provisional|assum\w*|subject to|depending|conditions?|not final|wltp|cltc|epa|iso\d+|deliver\w*|production|orders?|available|from \d|autumn|spring|summer|winter)\b', re.I)
MANDATORY_QUALIFICATION = re.compile(r'\b(?:required|requires?|subject to|only available|selected markets|separate (?:customer )?charging contract)\b', re.I)
BRAND_PATTERNS = {
    'general-motors':r'\b(?:gm|general motors|chevrolet|cadillac|gmc|buick|ultium)\b',
    'volkswagen':r'\b(?:volkswagen|vw)\b', 'bmw':r'\bbmw\b', 'renault':r'\brenault\b',
    'tesla':r'\btesla\b', 'volvo':r'\bvolvo\b', 'polestar':r'\bpolestar\b',
    'byd':r'\bbyd\b', 'xpeng':r'\bxpeng\b', 'nio':r'\bnio\b', 'gac':r'\bgac\b',
    'kia':r'\bkia\b', 'hyundai':r'\bhyundai\b', 'toyota':r'\btoyota\b', 'lexus':r'\blexus\b',
    'audi':r'\baudi\b', 'skoda':r'\bskoda\b', 'cupra':r'\bcupra\b',
    'mercedes':r'\b(?:mercedes|mercedes benz)\b', 'ford':r'\bford\b', 'nissan':r'\bnissan\b',
    'peugeot':r'\bpeugeot\b', 'citroen':r'\bcitroen\b', 'zeekr':r'\bzeekr\b',
    'smart':r'\bsmart\s*(?:#\s*)?[1-9]\b|\bsmart (?:europe|automobile|mobility)\b',
}


def subject_brands(text):
    text = re.sub(r"(?<=\w)['\u2019]s\b", '', str(text), flags=re.I)
    return {brand for brand,pattern in BRAND_PATTERNS.items() if re.search(pattern,normalize(text))}


def assessment_text(payload):
    body = payload.get('content')
    material = body[:4000] if isinstance(body, str) and body else str(payload.get('summary') or '')[:1200]
    return normalize(payload.get('title', '')) + ' ' + normalize(material)


def vehicle_evidence(payload):
    text = assessment_text(payload)
    if re.search(VEHICLE, text):
        return True
    # Some releases describe the named BEV through powertrain facts, not an "electric" label.
    title = payload.get('title', '')
    models = model_identifiers(title)
    body = str(payload.get('content') or '')[:4000]
    if (len(subject_brands(title)) != 1 or len(models) != 1
            or not re.search(r'\b(?:suv|mpv|sedan|saloon|hatchback|crossover)\b', body, re.I)
            or re.search(r'\b(?:hybrid\w*|phev|fuel.cell|range.extender|combustion|petrol|diesel)\b', body, re.I)):
        return False
    def model_bound(pattern):
        return any(models == model_identifiers(body[max(0, m.start()-200):m.start()])
                   for m in re.finditer(pattern, body, re.I))
    return bool(model_bound(r'\bCO\s*2\s+emissions\s*:\s*0\s*g/km\b')
        and model_bound(r'\b\d{2,3}[- ]kWh\s+(?:[A-Z]+\s+){0,2}battery\b')
        and re.search(r'\b\d{3,4}[- ]volt architecture\b', body, re.I)
        and re.search(r'\bcharging\b', body, re.I))


def substantive_development(payload):
    """A concrete vehicle change, not geography or a brand name alone."""
    title = normalize(payload.get('title', ''))
    text = assessment_text(payload)
    if not vehicle_evidence(payload):
        return False
    opening = text[:1200]
    network_development = (re.search(CHARGING_NETWORK, opening) and re.search(NETWORK_CHANGE, opening)
        and not re.search(r'\b(?:earnings|profits?|financ\w*|bonds?|awards?|dividends?)\b', title))
    return bool(re.search(TECHNOLOGY, text) or re.search(DEVELOPMENT, title) or network_development)


def speculative_subject(payload):
    title = normalize(payload.get('title', ''))
    if re.search(SPECULATION, title):
        return True
    # A confirmed headline is not a rumour because a later paragraph discusses potential.
    opening = re.split(r'[.!?]\s|\n', str(payload.get('content') or payload.get('summary') or ''), maxsplit=1)[0]
    return not substantive_development(payload) and bool(re.search(SPECULATION, normalize(opening)))


def price_focused(title):
    """A launch with an incidental price is not a price-change/offer story."""
    return bool(re.search(PRICE, title) and
                (not re.search(LAUNCH, title) or re.search(PRICE_CHANGE, title)
                 or (re.search(PRICE_WORD, title) and not re.search(r'\bprice (?:from|at)\b', title))
                 or re.search(r'\b(?:new|updated|lower|higher|nya|nouveaux|neue) (?:prices?|priser|prix|preise)\b', title)))


def candidate_assessment(item, now=None):
    """Ranking is not a Swedish-market fact or a replacement for the AI audit."""
    p = item.get('payload', item)
    title = normalize(p.get('title', ''))
    text = assessment_text(p)
    try:
        require_recent_publication(p.get('published_at'), now)
    except (ValueError, TypeError):
        return {'eligible': False, 'priority': 0, 'reason': 'stale_or_missing_report_date'}
    europe = bool(re.search(EUROPE, title) or re.search(r'\bswiss (?:premiere|market launch)\b', text) or re.search(
        r'\b(?:for|in|across|to|into|fur) (?:the )?(?:europe\w*|europa|eu|sweden|sverige|germany|deutschland|france|norway|finland|denmark|uk)\b', text)
        or re.search(r'\bauf (?:dem|den) (?:deutschen|europaischen) markt\b', text))
    vehicle = vehicle_evidence(p)
    if speculative_subject(p):
        return {'eligible': False, 'priority': 0, 'reason': 'speculation_or_minor_sighting'}
    if re.search(r'\b(?:drones?|military|militaire\w*)\b', title):
        return {'eligible': False, 'priority': 0, 'reason': 'outside_passenger_ev_scope'}
    if re.search(r'\b(?:podcasts?|reader questions?|readers questions|lasarfrag\w*|vol|stolen|theft|stold\w*)\b', title):
        return {'eligible': False, 'priority': 0, 'reason': 'commentary_or_incident_not_vehicle_development'}
    if re.search(r'\b(?:opening|opens?|eroffnung)\b.*\b(?:store|venue|atelier|showroom)\b', title):
        return {'eligible': False, 'priority': 0, 'reason': 'local_offer_or_minor_publicity'}
    if re.search(r'\b(?:finalists?|shortlisted|nominated|nomination|agm|dividends?|till final|finalister|nominerad\w*)\b', title):
        return {'eligible': False, 'priority': 0, 'reason': 'minor_publicity_or_corporate_calendar'}
    if re.search(r'\b(?:kundenangebot\w*|aktionsangebot\w*|leasingangebot\w*|gewinnspiel\w*|roadshow\w*|handlerkonferenz\w*|filmproduktion\w*)\b', text):
        return {'eligible': False, 'priority': 0, 'reason': 'local_offer_or_minor_publicity'}
    if re.search(r'\b(?:hydrogen\w*|hydrogene|fuel cell|plug in hybrid|super hybrid|hybride rechargeable|ladbar hybrid|fullhybrid\w*|vollhybrid\w*|em p)\b', title):
        return {'eligible': False, 'priority': 0, 'reason': 'not_battery_ev_focus'}
    if re.search(STORAGE, text) and not re.search(r'\b(?:traction|passenger vehicle|electric car|electric vehicle)\w*\b', text):
        return {'eligible': False, 'priority': 0, 'reason': 'not_vehicle_energy_storage'}
    if not europe and (re.search(LOCAL_BUSINESS, title) or re.search(POLITICS, title)):
        return {'eligible': False, 'priority': 0, 'reason': 'regional_business_or_policy'}
    if price_focused(title):
        return {'eligible': False, 'priority': 0, 'reason':
                'price_notice_recipe_required' if re.search(EUROPE, title) else 'foreign_price_story'}
    if not vehicle:
        return {'eligible': False, 'priority': 0, 'reason': 'vehicle_connection_not_established'}
    if europe:
        sweden = bool(re.search(r'\b(?:sweden|swedish|sverige|svensk\w*)\b', text) or re.search(
            r'\b(?:in|for|across|to|i|till) (?:the )?(?:nordic (?:market\w*|region\w*|countr\w*|buyer\w*)|scandinavia\w*)\b', text))
        return {'eligible': True, 'priority': 100 if sweden else 80, 'reason': 'swedish_scope' if sweden else 'european_scope'}
    if re.search(TECHNOLOGY, text):
        return {'eligible': True, 'priority': 65, 'reason': 'global_vehicle_technology'}
    international = bool(re.search(r'\b(?:china|chinese|australia|australian|thailand|thai|uae|dubai|usa|united states|american|japan|japanese|korea|korean|india|indian)\b', text))
    if international:
        if re.search(r'\b(?:launch\w*|unveil\w*|debut\w*|introduc\w*|reveal\w*|update\w*|recall\w*|prasentiert|weltpremiere|markteinfuhrung|ruckruf|modellpflege)\b', title):
            return {'eligible': True, 'priority': 60, 'reason': 'international_vehicle_development'}
        return {'eligible': False, 'priority': 0, 'reason': 'regional_scope_without_substantive_development'}
    return {'eligible': True, 'priority': 40, 'reason': 'vehicle_update_needs_primary_relevance'}


def publisher_content_candidate(item, templates):
    """A recognized brand/approved vehicle route allows free reading, never EV proof."""
    source = templates.get(item.get('source_id'))
    if not source or not source.get('can_lead') or not source.get('metadata_triage_path_pattern'):
        return False
    try:
        url = canonical_url(item['url'])
        p = urlsplit(url)
        return bool(url == item['url'] and not p.query and p.hostname == urlsplit(source['website']).hostname
            and re.fullmatch(source['article_path_pattern'], p.path)
            and re.fullmatch(source['metadata_triage_path_pattern'], p.path)
            and subject_brands(item['payload']['title']))
    except (ValueError, TypeError, KeyError):
        return False


def bounded_reading_queue(queue, candidates, templates):
    """Reserve one existing reading slot for thin vehicle metadata, not a paid attempt."""
    selected = queue[:8]
    recovery = next((pair for pair in candidates if pair[1].get('reason') == 'publisher_content_triage_required'), None)
    if recovery and not any(pair[0]['url'] == recovery[0]['url'] for pair in selected):
        replace = next((i for i in range(len(selected)-1, -1, -1)
                        if selected[i][0]['source_id'] in templates), None)
        if replace is not None:selected[replace] = recovery
    return selected


def ranked_candidates(items, source_ids, attempted=(), now=None, *, hydrate_sources=(), hydrate_publishers=None):
    """Look beyond the newest eight without increasing the number of paid calls."""
    excluded = set(attempted)
    accepted, held = [], []
    for item in items:
        if item.get('source_id') not in source_ids or item.get('status') != 'collected' or item['url'] in excluded:
            continue
        result = candidate_assessment(item, now)
        if item['source_id'] in hydrate_sources and result['reason'] == 'vehicle_connection_not_established':
            result = {'eligible': True, 'priority': 20, 'reason': 'official_content_triage_required'}
        elif result['reason'] == 'vehicle_connection_not_established' and publisher_content_candidate(item, hydrate_publishers or {}):
            result = {'eligible': True, 'priority': 10, 'reason': 'publisher_content_triage_required'}
        if result['eligible']:
            accepted.append((item, result))
        else:
            held.append({'source_id': item['source_id'], 'url': item['url'], 'reason': result['reason'],
                         'subjects': sorted(subject_brands(item['payload']['title']))})
    accepted.sort(key=lambda pair: (pair[1]['priority'], pair[0]['payload']['published_at'], pair[0]['url']), reverse=True)
    return bounded_reading_queue(accepted, accepted, hydrate_publishers or {}), held[:24]


def subject_terms(text):
    return {t for t in normalize(text).split() if len(t) >= 2 and not t.isdigit() and t not in STOP}


def event_actions(text):
    text = normalize(text)
    return {name for name, pattern in {
        'launch': LAUNCH,
        'update': r'\b(?:update\w*|rollout|roll\w* out|activat\w*|active|deploy\w*|mise a jour|aktualis\w*|modellpflege|uppdater\w*)\b',
        'production': r'\b(?:production|factory|plant|fabrik\w*|fertigung|produktion|usine\w*)\b',
        'recall': r'\b(?:recall\w*|ruckruf\w*|rappel\w*|aterkall\w*)\b',
        'price': PRICE,
        'test': r'\b(?:test\w*|review\w*|essai\w*)\b',
        'market': r'\b(?:registrations?|immatriculations?|zulassung\w*|nybilregistrering\w*|sales|ventes)\b',
    }.items() if re.search(pattern, text)}


def event_topics(text):
    text = normalize(text)
    return {name for name, pattern in {
        'battery_preconditioning': r'\b(?:preheat\w*|precondition\w*|prechauff\w*|vorkondition\w*|forvarm\w*)\b',
        'bidirectional_charging': r'\b(?:v2g|v2h|bidirectional\w*|bidirektion\w*)\b',
        'solid_state': r'\b(?:solid state|festkorper\w*|batteries? solides?|fastfas\w*)\b',
        'sodium_ion': r'\b(?:sodium ion|natrium ion\w*)\b',
        'charging_network': CHARGING_NETWORK,
    }.items() if re.search(pattern, text)}


def event_markets(text):
    text = normalize(text)
    return {name for name, pattern in {
        'SE': r'\b(?:sweden|swedish|sverige|svensk\w*|suede)\b',
        'DE': r'\b(?:germany|german|deutsch\w*|allemagne)\b',
        'FR': r'\b(?:france|french|francais\w*)\b',
        'CN': r'\b(?:china|chinese|chine|chinois\w*|kina|kinesisk\w*)\b',
        'AU': r'\b(?:australia\w*|australie\w*|australien)\b',
        'CH': r'\b(?:switzerland|swiss|schweiz\w*|suisse)\b',
        'NO': r'\b(?:norway|norwegian|norge|norsk\w*)\b',
        'FI': r'\b(?:finland|finnish|finlande)\b',
        'DK': r'\b(?:denmark|danish|danmark|danemark)\b',
        'UK': r'\b(?:uk|britain|british|united kingdom|royaume uni)\b',
        'US': r'\b(?:usa|united states|american|etats unis)\b',
        'JP': r'\b(?:japan|japanese|japon\w*)\b',
        'KR': r'\b(?:korea\w*|coree\w*)\b',
        'IN': r'\b(?:india\w*|inde)\b',
    }.items() if re.search(pattern, text)}


def event_conflicts(left, right):
    for extract in (subject_brands, model_identifiers, event_actions, event_topics, event_markets, reference_periods):
        a, b = extract(left), extract(right)
        if a and b and not a & b:
            return True
    return False


def cross_language_event_matches(left, right):
    """Bounded concept matching, not translation, fact approval or independence."""
    if event_conflicts(left, right) or not subject_brands(left) & subject_brands(right):
        return False
    actions = event_actions(left) & event_actions(right)
    if not actions:
        return False
    left_models, right_models = model_identifiers(left), model_identifiers(right)
    if bool(left_models) != bool(right_models):
        return False
    models = left_models & right_models
    topics = event_topics(left) & event_topics(right)
    existing = r'\b(?:older|existing|anciens?|existants?|bestand\w*|alteren|befintlig\w*|aldre)\b'
    cohort = all(re.search(existing, normalize(t)) for t in (left, right))
    if topics and (models or cohort):
        return True
    # Generic launch/price words plus a brand alone cannot identify an event.
    return bool(models and 'launch' in actions and
                re.search(EUROPE, normalize(left)) and re.search(EUROPE, normalize(right)))


def _sentence_spans(text):
    """Whole sentences/clauses, with exact offsets in the unchanged captured text."""
    boundary = re.compile(r'(?<=[.!?;])\s+|(?<=[。！？；])|\n+')
    start = 0
    for match in list(boundary.finditer(text)) + [None]:
        if match and re.search(r'\b(?:ID|Dr|Mr|Mrs|Prof)\.$', text[:match.start()], re.I):
            continue
        end = match.start() if match else len(text)
        value = text[start:end]
        left, right = len(value) - len(value.lstrip()), len(value.rstrip())
        if right > left:
            begin, finish = start + left, start + right
            quote = text[begin:finish]
            asian = bool(re.search(r'[\u4e00-\u9fff\u0e00-\u0e7f]', quote))
            if not quote.endswith(':') and ((asian and 20 <= len(quote) <= 160)
                    or (8 <= len(quote.split()) <= 45 and len(quote) <= 350)):
                yield begin, finish
        if match:
            start = match.end()


def _structured_spans(text):
    """Keep short field lines with their literal model header and nearby caveats."""
    labels = r'(?:battery capacity|dc (?:peak|charging)|ac charging|range|ordering opens|batteriekapazitat|reichweite|rackvidd)'
    field = re.compile(r'^' + labels + r'\s*:', re.I)
    # HTML text extractors flatten list items. Split at literal field labels too,
    # keeping offsets into the unchanged text, not reconstructed line breaks.
    boundary = re.compile(r'\n+|(?<=[.:;!?])\s+(?=' + labels + r'\s*:)', re.I)
    lines, start = [], 0
    for match in list(boundary.finditer(text)) + [None]:
        end = match.start() if match else len(text)
        if text[start:end].strip():
            lines.append((start, end, text[start:end]))
        if match:
            start = match.end()
    for i, (begin, _, header) in enumerate(lines):
        title = header.strip()
        if (not title.endswith(':') or len(title) > 120
                or len(subject_brands(title)) != 1 or len(model_identifiers(title)) != 1):
            continue
        j = i + 1
        while j < min(i + 7, len(lines)):
            line_begin, end, line = lines[j]
            if '\n\n' in text[lines[j-1][1]:line_begin].replace('\r', ''):
                break
            if not field.match(line.strip()):
                break
            if subject_brands(line) and model_identifiers(line) - model_identifiers(title):
                break
            # A following qualification belongs to the field, not a separate fact.
            k = j + 1
            while k < len(lines) and not field.match(lines[k][2].strip()):
                gap = text[lines[k-1][1]:lines[k][0]].replace('\r', '')
                following = lines[k][2].strip()
                if ('\n\n' in gap or following.endswith(':') or not QUALIFICATION.search(following)
                        or (model_identifiers(following) and
                            not model_identifiers(title) & model_identifiers(following))):
                    break
                end = lines[k][1]
                k += 1
            start = begin + len(header) - len(header.lstrip())
            quote = text[start:end].rstrip()
            if len(quote) > 350 or len(quote.split()) > 45:
                break
            if 8 <= len(quote.split()) <= 45:
                yield start, start + len(quote)
            j = k


def literal_spans(text):
    """Exact narrative spans or model-bound contiguous field windows; never tables."""
    yield from sorted(set(_sentence_spans(text)) | set(_structured_spans(text)))


def passage_selection(content, report_title, source_title, byte_limit, *, primary=False):
    spans = list(literal_spans(content))
    terms = subject_terms(report_title)
    if not terms:
        terms = subject_terms(source_title)
    ranked = []
    for i, (start, end) in enumerate(spans):
        quote = content[start:end]
        overlap = len(terms & subject_terms(quote))
        score = overlap * 8 + (2 if re.search(r'\d', quote) else 0)
        if primary and MANDATORY_QUALIFICATION.search(quote):
            score += 100
        if overlap:
            score += 5 if primary and QUALIFICATION.search(quote) else 0
        ranked.append((score, i, start, end))
    # Preserve nearby conditions, dates and footnotes instead of just taking a prefix.
    contextual = set()
    for score, i, _, _ in sorted(ranked, reverse=True)[:3]:
        if score < 8:
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(spans):
                quote = content[slice(*spans[j])]
                if QUALIFICATION.search(quote):
                    contextual.add(j)
    ranked = [(score + (7 if i in contextual else 0), i, start, end) for score, i, start, end in ranked]
    selected, used = [], 0
    for score, i, start, end in sorted(ranked, key=lambda r: (-r[0], r[1])):
        size = len(content[start:end].encode()) + (5 if selected else 0)
        if used + size <= byte_limit:
            selected.append((start, end))
            used += size
    selected.sort()
    return {'CONTENT': '\n...\n'.join(content[start:end] for start, end in selected),
            'passage_offsets': [list(pair) for pair in selected]}


def primary_identity_matches(report, primary):
    title = report['payload']['title']
    target = primary['payload']
    brands = subject_brands(title)
    target_brands = subject_brands(target['title']) or subject_brands(target.get('publisher', ''))
    if brands and target_brands and not brands & target_brands:
        return False
    if not brands and target_brands:
        # A competitor mentioned in the report body cannot supply its subject.
        if (not model_identifiers(title) & model_identifiers(target['title'])
                or not target_brands & subject_brands(report['payload'].get('content','')[:1200])):
            return False
    if brands and not brands & subject_brands(target['title']+' '+target['content']+' '+target.get('publisher','')):
        return False
    recall = r'\b(?:recall\w*|aterkall\w*|rappel\w*|ruckruf\w*)\b'
    target_text = target['title']+' '+target['content']
    report_recall = re.search(recall, normalize(title)) or '\u53ec\u56de' in title
    target_recall = re.search(recall, normalize(target_text)) or '\u53ec\u56de' in target_text
    if report_recall and not target_recall:
        return False
    statistics = r'\b(?:registrations?|immatriculations?|nybilregistrering\w*|bilsalg\w*|sales|ventes|deliveries|delivered|livr\w*|ausliefer\w*|zulassung\w*)\b'
    if re.search(statistics, normalize(title)):
        if not re.search(statistics, normalize(target['title']+' '+target['content'][:1200])):
            return False
        counts = statistical_quantities(title)
        if counts and not counts <= statistical_quantities(target['title']+' '+target['content']):
            return False
    ids = model_identifiers(title)
    primary_ids = model_identifiers(target['title'])
    if ids and primary_ids and not ids & primary_ids:
        return False
    if ids and not ids & model_identifiers(target['title']+' '+target['content']):
        return False
    if re.search(statistics, normalize(title + ' ' + report['payload'].get('content','')[:800])):
        a = reference_periods(title) or reference_periods(report['payload'].get('content','')[:2000])
        b = reference_periods(target['title']) or reference_periods(target['content'][:4000])
        if a and b and not a & b:
            return False
    terms = subject_terms(title)
    return (len(terms & subject_terms(target['title'] + ' ' + target['content'])) >= 2
            or cross_language_event_matches(title, target['title']))


def model_identifiers(text):
    result = set(re.findall(r'\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]+\b', normalize(text)))
    result = {value for value in result if value not in {'v2g', 'v2h', 'v2l', 'v2x', 'co2', 'nox', 'l2', 'l3', 'l4'}
              and not re.fullmatch(r'(?:iso\d+|\d+(?:v|kw|kwh))', value)}
    result.update('smart'+number for number in re.findall(r'\bsmart\s*(?:#\s*)?([1-9])\b', text, re.I))
    result.update('id'+number for number in re.findall(r'\bid[\s.]*([1-9]\d?)\b', text, re.I))
    return result


def statistical_quantities(text):
    """Conservative matching of large headline counts, never published fact conversion."""
    tokens = re.findall(r'\b\d{1,3}(?:[ ,.\u00a0\u202f]\d{3})+\b|\b\d+\b', text)
    values = {int(re.sub(r'\D', '', token)) for token in tokens}
    return {value for value in values if value >= 100 and not 1900 <= value <= 2100}


def reference_periods(text):
    """Only explicit month/year pairs; collection dates are not reporting periods."""
    months = ('january janvier januar januari', 'february fevrier februar februari',
              'march mars marz', 'april avril', 'may mai maj', 'june juin juni',
              'july juillet juli', 'august aout augusti', 'september septembre',
              'october octobre oktober', 'november novembre', 'december decembre desember')
    found = {(int(y),int(m)) for y,m in re.findall(r'\b(20\d{2})[-/](0[1-9]|1[012])\b',text)}
    text = normalize(text)
    for month,names in enumerate(months,1):
        for year in re.findall(r'\b(?:'+ '|'.join(names.split()) + r')\s+(20\d{2})\b',text):
            found.add((int(year),month))
    return found
