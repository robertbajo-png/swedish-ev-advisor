"""International editorial relevance, independent of Swedish sales availability."""
from datetime import datetime, timezone
from news_editorial import relevance_score, valid_rating
from news_http import iso_date
from news_publisher_selection import candidate_assessment

INTERNATIONAL = {'international_vehicle_development', 'global_vehicle_technology'}


def international_scope(bundle, now=None):
    lead = bundle['items'][0]['payload']
    return candidate_assessment({**lead, 'summary': lead.get('content', '')[:4000]}, now)['reason'] in INTERNATIONAL


def coverage_score(bundle, extraction, now=None):
    now = now or datetime.now(timezone.utc)
    lead = bundle['items'][0]['payload']
    if not international_scope(bundle, now):
        return relevance_score(extraction, .8, lead['published_at'], now)
    significance = extraction.get('significance')
    date = iso_date(lead.get('published_at'))
    if not date or not valid_rating(significance):
        return 0
    age = (now - datetime.fromisoformat(date)).total_seconds() / 86400
    if not -1 / 24 <= age <= 7:
        return 0
    return round(100 * (.65 * significance + .2 * .8 + .15 * max(0, 1 - max(0, age) / 7)), 2)
