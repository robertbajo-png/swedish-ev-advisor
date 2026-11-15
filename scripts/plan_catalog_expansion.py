"""Read-only expansion inventory; never author or publish vehicle data."""
import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from build_expansion_scope import build_expansion_scope, read_csv

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('wltp_range_km', 'wltp_consumption_kwh_100km', 'battery_kwh',
          'dc_charge_kw', 'ac_charge_kw', 'tow_kg', 'boot_liters', 'seats', 'drivetrain')
PUBLIC = {'published', 'published_reviewed'}


def inventory(market, models, aliases, records, as_of, start=31, end=60):
    if not 1 <= start <= end or end - start >= 200:
        raise ValueError('bounded_rank_window_required')
    public = [r for r in records if r.get('validation_status') in PUBLIC]
    scope, held = build_expansion_scope(market, models, aliases, public, start, end)
    for row in scope:
        try:
            seen = date.fromisoformat(row['last_seen_month'])
            age = (as_of.replace(day=1).year-seen.year)*12 + as_of.month-seen.month
            current = 0 <= age <= 2
        except (ValueError, TypeError):
            current = False
        row['status'] = 'research_only' if current else 'needs_market_refresh'
        row['publication_approved'] = False
    gaps = []
    for r in public:
        missing = [f for f in FIELDS if r.get(f) is None or r.get(f) == '']
        if missing:
            gaps.append({'brand': r['brand'], 'model': r['model'],
                         'variant_name': r['variant_name'], 'missing_fields': missing})
    return dict(as_of=as_of.isoformat(), rank_window=[start, end],
                public_models=len({(r['brand'], r['model']) for r in public}),
                public_variants=len(public), complete_technical_variants=len(public)-len(gaps),
                research_candidates=scope, mapping_quarantine=held, technical_gaps=gaps,
                database_writes=0, paid_calls=0, publication_approved=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-rank', type=int, default=31)
    parser.add_argument('--end-rank', type=int, default=60)
    parser.add_argument('--as-of', type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument('--output', type=Path, default=ROOT/'data/local/catalog-expansion-preflight.json')
    args = parser.parse_args()
    records = json.loads((ROOT/'public/data/public_ev_variants.json').read_text(encoding='utf8'))['records']
    report = inventory(read_csv(ROOT/'data/mobility-sweden/processed/market_models.csv'),
        read_csv(ROOT/'data/canonical/canonical_models_seed.csv'),
        read_csv(ROOT/'data/canonical/model_aliases_seed.csv'), records, args.as_of,
        args.start_rank, args.end_rank)
    local = (ROOT/'data/local').resolve()
    if not args.output.resolve().is_relative_to(local):
        raise ValueError('private_report_must_stay_under_data_local')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps({k: report[k] for k in ('as_of', 'public_models', 'public_variants',
        'complete_technical_variants', 'database_writes', 'paid_calls')} | {
        'research_candidates': len(report['research_candidates']),
        'needs_market_refresh': sum(r['status']=='needs_market_refresh' for r in report['research_candidates']),
        'mapping_quarantine': len(report['mapping_quarantine'])}))


if __name__ == '__main__':
    main()
