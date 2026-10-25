"""Terminology for writing/review, never additional source evidence or approval."""
import re
import unicodedata

from news_fact_brief import writing_card
TERMINOLOGY = {
    'DC': 'likström',
    'AC': 'växelström',
    'preorders_open': 'förhandsbeställningarna öppnar; not delivery or general availability',
    'boundary_months': 'månadsskiftet or övergången mellan the named months; not a two-month window',
    'motor_power_options': 'offered effektnivåer or motoreffektalternativ; not selectable effektlägen or körlägen',
}

REVIEW_CALIBRATION = [
    {'source': 'DC-laddning', 'rendering': 'laddning med likström', 'scope': 'same current type, no new claim'},
    {'source': 'AC-laddning', 'rendering': 'laddning med växelström', 'scope': 'same current type, no new claim'},
    {'source': 'laddtiden beror på effekten vid AC- och DC-laddning',
     'rendering': 'effekten vid såväl AC som DC påverkar laddtiden', 'scope': 'both currents are already stated'},
    {'source': 'laddning med 80 kW', 'rendering': 'laddning med högst 80 kW',
     'scope': 'NOT equivalent: introduces an unstated upper bound'},
    {'source': 'förförsäljningen börjar', 'rendering': 'leveranserna börjar',
     'scope': 'NOT equivalent: changes the event'},
    {'source': 'lansering vid månadsskiftet april/maj', 'rendering': 'lansering under april och maj',
     'scope': 'NOT equivalent: broadens a boundary to a two-month window'},
    {'source': 'en andel på 30 procent', 'rendering': 'den största kategorin med 30 procent',
     'scope': 'NOT equivalent: adds an unlicensed ranking'},
    {'source': 'Två effektnivåer erbjuds', 'rendering': 'Motorn erbjuds i två effektlägen',
     'scope': 'NOT equivalent: offered power ratings do not establish driver-selectable operating modes'},
]

# Human-labelled rubric examples, never evidence for a generated story.
BUYER_QUESTION_CALIBRATION = [
    {'anchor': 'range', 'text': 'Hur långt behöver du kunna köra mellan dina laddstopp?',
     'label': 'grounded_question', 'reason': 'asks a personal distance, not what this car actually achieves'},
    {'anchor': 'charging', 'text': 'Hur mycket tid vill du avsätta för laddstopp på dina resor?',
     'label': 'grounded_question', 'reason': 'asks a personal time constraint, not a promised stop duration'},
    {'anchor': 'practicality', 'text': 'Vilket bagage behöver du få med på dina resor?',
     'label': 'grounded_question', 'reason': 'asks the reader about their cargo, not universal family suitability'},
    {'anchor': 'availability', 'text': 'När behöver du kunna ta emot din nästa bil?',
     'label': 'grounded_question', 'reason': 'asks a personal deadline, not a vehicle delivery date'},
    {'anchor': 'range', 'text': 'Hur passar det dig att bilen klarar alla vinterresor utan laddstopp?',
     'label': 'unsupported_claim', 'reason': 'presupposes real winter performance absent from a WLTP figure'},
    {'anchor': 'practicality', 'text': 'Passar den här bilen bäst för alla barnfamiljer?',
     'label': 'unsupported_advice', 'reason': 'introduces unsupported suitability and ranking'},
    {'anchor': 'range', 'text': 'Vill du spara pengar med den lägre förbrukningen?',
     'label': 'unsupported_claim', 'reason': 'range cannot establish efficiency, a comparison or lower cost'},
    {'anchor': 'availability', 'text': 'Vill du ha bilen som levereras nästa vecka?',
     'label': 'unsupported_claim', 'reason': 'a preorder or launch date does not prove a delivery promise'},
]


def power_bound_errors(blocks, facts):
    by_id = {fact['id']: fact for fact in facts}
    errors = []
    for block in blocks:
        cited = [by_id[key] for key in block.get('fact_ids', []) if key in by_id]
        for fact in cited:
            charging = writing_card(fact['statement']).get('charging', {})
            if charging.get('power_basis') != 'stated_not_explicit_maximum':
                continue
            value = re.escape(charging['power_kw']).replace(',', '[,.]').replace(r'\.', '[,.]')
            bound = r'(?:högst|max(?:imal(?:t|a)?)?|upp till|up to|maximum)\s+' + value + r'\s*kW\b'
            if re.search(bound, block['text'], re.I) and not any(re.search(bound, f['statement'], re.I) for f in cited):
                errors.append('unstated_power_maximum:' + block['id'])
    return list(dict.fromkeys(errors))


def power_option_errors(blocks, facts):
    by_id = {fact['id']: fact for fact in facts}
    errors = []
    for block in blocks:
        cited = [by_id[key] for key in block.get('fact_ids', []) if key in by_id]
        if any(writing_card(fact['statement']).get('motor_power_options') for fact in cited):
            if re.search(r'\b(?:effektläg\w*|körläg\w*|power[ -]modes?|driv(?:e|ing)[ -]modes?)\b', block['text'], re.I):
                errors.append('unsupported_motor_power_modes:' + block['id'])
    return errors


def current_type_errors(blocks, facts):
    def currents(text):
        plain = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
        return {key for key, pattern in {'AC': r'\bac\b|vaxelstrom', 'DC': r'\bdc\b|likstrom'}.items()
                if re.search(pattern, plain)}
    by_id = {fact['id']: fact for fact in facts}
    errors = []
    for block in blocks:
        if block['kind'] == 'analysis':
            continue
        allowed = set().union(*(currents(by_id[key]['statement']) for key in block.get('fact_ids', []) if key in by_id))
        if allowed:
            errors.extend('unsupported_current_type:' + block['id'] + ':' + key
                          for key in sorted(currents(block['text']) - allowed))
    return errors
