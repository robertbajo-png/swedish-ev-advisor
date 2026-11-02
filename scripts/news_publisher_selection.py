"""Free editorial triage and exact, bounded evidence passages; never approval."""
import re
from news_editorial import normalize
from news_http import require_recent_publication

EUROPE = r'\b(?:sweden|swedish|sverige|svensk\w*|nordic|scandinavia\w*|europe\w*|europa|europeisk\w*|eu|germany|german|france|french|norway|norwegian|norge|norsk\w*|francais\w*|allemagne|suede|finland|finnish|denmark|danish|britain|british|united kingdom|uk)\b'
VEHICLE = r'\b(?:evs?|bevs?|electric (?:passenger )?(?:cars?|vehicles?|suvs?|sedans?|hatch\w*)|battery electric|elbil\w*|(?:hel)?elektrisk\w* (?:bil\w*|personbil\w*|modell\w*|suv\w*)|eldriv\w* (?:bil\w*|personbil\w*)|(?:voitures?|vehicules?) electriques?|biler? elektrisk\w*)\b'
TECHNOLOGY = r'\b(?:sodium ion|solid state|battery chemistr\w*|energy density|lmr batter\w*|battery recycl\w*|cell to (?:pack|body)|superfast charg\w*|ultra fast charg\w*|800 volt|900 volt)\b'
LOCAL_BUSINESS = r'\b(?:dealers?|dealerships?|service network|local subsid\w*|rebates?|tax exemptions?|consumption tax|exempt\w*.*?tax|tax.*?exempt\w*|earnings|profits?|sales milestone|crosses.*?sales|factory|facilit\w*|plant|production line|off grid.*?station|charging station)\b'
SPECULATION = r'\b(?:rumou?rs?|rumeurs?|rykter?|pourrait|spotted|spy shots?|patent|teased|potential|may get|could launch|readers questions)\b'
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
BRAND_PATTERNS = {
    'general-motors':r'\b(?:gm|general motors|chevrolet|cadillac|gmc|buick|ultium)\b',
    'volkswagen':r'\b(?:volkswagen|vw)\b', 'bmw':r'\bbmw\b', 'renault':r'\brenault\b',
    'tesla':r'\btesla\b', 'volvo':r'\bvolvo\b', 'polestar':r'\bpolestar\b',
    'byd':r'\bbyd\b', 'xpeng':r'\bxpeng\b', 'nio':r'\bnio\b', 'gac':r'\bgac\b',
    'kia':r'\bkia\b', 'hyundai':r'\bhyundai\b', 'toyota':r'\btoyota\b', 'lexus':r'\blexus\b',
    'audi':r'\baudi\b', 'skoda':r'\bskoda\b', 'cupra':r'\bcupra\b',
    'mercedes':r'\b(?:mercedes|mercedes benz)\b', 'ford':r'\bford\b', 'nissan':r'\bnissan\b',
    'peugeot':r'\bpeugeot\b', 'citroen':r'\bcitroen\b', 'zeekr':r'\bzeekr\b',
}


def subject_brands(text):
    return {brand for brand,pattern in BRAND_PATTERNS.items() if re.search(pattern,normalize(text))}


def candidate_assessment(item, now=None):
    """Ranking is not a Swedish-market fact or a replacement for the AI audit."""
    p = item.get('payload', item)
    title = normalize(p.get('title', ''))
    text = title + ' ' + normalize(p.get('summary', ''))[:1200]
    try:
        require_recent_publication(p.get('published_at'), now)
    except (ValueError, TypeError):
        return {'eligible': False, 'priority': 0, 'reason': 'stale_or_missing_report_date'}
    europe = bool(re.search(EUROPE, title) or re.search(
        r'\b(?:for|in|across|to|into) (?:the )?(?:europe\w*|eu|sweden|sverige|germany|france|norway|finland|denmark|uk)\b', text))
    vehicle = bool(re.search(VEHICLE, text))
    if re.search(SPECULATION, text):
        return {'eligible': False, 'priority': 0, 'reason': 'speculation_or_minor_sighting'}
    if re.search(r'\b(?:hydrogen\w*|hydrogene|fuel cell|plug in hybrid|hybride rechargeable|ladbar hybrid|fullhybrid\w*|em p)\b', title):
        return {'eligible': False, 'priority': 0, 'reason': 'not_battery_ev_focus'}
    if re.search(STORAGE, text) and not re.search(r'\b(?:traction|passenger vehicle|electric car|electric vehicle)\w*\b', text):
        return {'eligible': False, 'priority': 0, 'reason': 'not_vehicle_energy_storage'}
    if not europe and (re.search(LOCAL_BUSINESS, title) or re.search(POLITICS, title)):
        return {'eligible': False, 'priority': 0, 'reason': 'regional_business_or_policy'}
    if re.search(r'\b(?:prices?|price tag|discount|prix|tarifs?|pris(?:er)?|rabatt\w*|\d+k|privatleasing\w*|leasing\w*|lease (?:deal|offer)\w*)\b', title):
        return {'eligible': False, 'priority': 0, 'reason':
                'price_notice_recipe_required' if re.search(EUROPE, title) else 'foreign_price_story'}
    if not vehicle:
        return {'eligible': False, 'priority': 0, 'reason': 'vehicle_connection_not_established'}
    if europe:
        sweden = bool(re.search(r'\b(?:sweden|swedish|sverige|svensk\w*|nordic|scandinavia\w*)\b', text))
        return {'eligible': True, 'priority': 100 if sweden else 80, 'reason': 'swedish_scope' if sweden else 'european_scope'}
    if re.search(TECHNOLOGY, text):
        return {'eligible': True, 'priority': 65, 'reason': 'global_vehicle_technology'}
    if re.search(r'\b(?:china|chinese|australia|australian|thailand|thai|uae|dubai)\b', text):
        return {'eligible': False, 'priority': 0, 'reason': 'regional_scope_without_european_change'}
    return {'eligible': True, 'priority': 40, 'reason': 'vehicle_update_needs_primary_relevance'}


def ranked_candidates(items, source_ids, attempted=(), now=None, *, hydrate_sources=()):
    """Look beyond the newest eight without increasing the number of paid calls."""
    excluded = set(attempted)
    accepted, held = [], []
    for item in items:
        if item.get('source_id') not in source_ids or item.get('status') != 'collected' or item['url'] in excluded:
            continue
        result = candidate_assessment(item, now)
        if item['source_id'] in hydrate_sources and result['reason'] == 'vehicle_connection_not_established':
            result = {'eligible': True, 'priority': 20, 'reason': 'official_content_triage_required'}
        if result['eligible']:
            accepted.append((item, result))
        else:
            held.append({'source_id': item['source_id'], 'url': item['url'], 'reason': result['reason']})
    accepted.sort(key=lambda pair: (pair[1]['priority'], pair[0]['payload']['published_at'], pair[0]['url']), reverse=True)
    return accepted[:8], held[:24]


def subject_terms(text):
    return {t for t in normalize(text).split() if len(t) >= 2 and not t.isdigit() and t not in STOP}


def literal_spans(text):
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
            if (asian and 20 <= len(quote) <= 160) or (8 <= len(quote.split()) <= 45 and len(quote) <= 350):
                yield begin, finish
        if match:
            start = match.end()


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
    target_brands = subject_brands(target['title'])
    if brands and target_brands and not brands & target_brands:
        return False
    if not brands and target_brands and not target_brands & subject_brands(report['payload'].get('content','')[:1200]):
        return False
    if brands and not brands & subject_brands(target['title']+' '+target['content']+' '+target.get('publisher','')):
        return False
    ids = set(re.findall(r'\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]+\b', normalize(title)))
    primary_ids = set(re.findall(r'\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]+\b', normalize(target['title'])))
    if ids and primary_ids and not ids & primary_ids:
        return False
    if ids and not ids & set(re.findall(r'\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]+\b',
                                       normalize(target['title']+' '+target['content']))):
        return False
    statistics = r'\b(?:registrations?|immatriculations?|nybilregistrering\w*|bilsalg\w*|sales|ventes)\b'
    if re.search(statistics, normalize(title + ' ' + report['payload'].get('content','')[:800])):
        a = reference_periods(title) or reference_periods(report['payload'].get('content','')[:2000])
        b = reference_periods(target['title']) or reference_periods(target['content'][:4000])
        if a and b and not a & b:
            return False
    terms = subject_terms(title)
    return len(terms & subject_terms(target['title'] + ' ' + target['content'])) >= 2


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
