# EV Data Pipeline

The public advisor must only show canonical, validated EV data.

## Source Roles

Mobility Sweden is the Swedish market model index. It proves market presence and registration activity for passenger cars in Sweden.

Mobility Sweden is not a specification source. It must not be used for price, WLTP range, charging, battery, boot volume, tow capacity, trim levels, or equipment.

Official Swedish manufacturer/importer sources prove current availability, pricing, variants, and specifications.

Do not scrape specifications from third-party comparison sites. Do not publish unvalidated AI extraction.

## Flow

1. Collect or export Mobility Sweden new-registration data.
2. Filter for Swedish passenger cars with electric fuel type.
3. Aggregate by brand, raw model name, fuel type, and month.
4. Store model-level rollups in `market_models`.
5. Store monthly registration facts in `market_model_monthly_stats`.
6. Normalize brand and model names.
7. Match raw Mobility Sweden names to canonical models through `model_aliases`.
8. If a raw name is ambiguous, store it as `needs_mapping = true` or set `model_group`.
9. For matched or new models, discover official Swedish manufacturer/importer pages, price lists, technical PDFs, and configurators.
10. Store source URLs in `manufacturer_sources`.
11. Use AI structured extraction to produce draft variants, prices, and specs.
12. Validate extracted facts with hard rules before writing to canonical published records.
13. Only `published` canonical data is exposed to the public advisor.

## Ambiguous Names

Examples such as `ID.7/ID.7 Tourer` or `EX/XC40` should not be split unless there is a safe deterministic alias rule.

If the rule is uncertain:

- store `model_group`
- set `needs_mapping = true`
- do not create public canonical specs from the ambiguous record

## Availability Flags

Canonical models include:

- `market_seen`: seen in Mobility Sweden registration data
- `available_confirmed`: confirmed from official Swedish manufacturer/importer source
- `discontinued_candidate`: market registrations exist, but current official availability is not confirmed
- `coming_or_low_volume`: official source exists but registration volume is absent or very low

## Public Rule

The public AI advisor reads from canonical validated tables only:

`Mobility Sweden model discovery -> manufacturer source discovery -> AI extraction -> validation -> canonical EV database -> public AI advisor`

## Current Scraper

Run the current Mobility Sweden importer:

```bash
python scripts/import_mobility_sweden.py
```

It downloads the latest configured Mobility Sweden monthly report, parses the `Elbil ranking` sheet, and writes:

- `data/mobility-sweden/processed/market_models.csv`
- `data/mobility-sweden/processed/market_models.json`
- `data/mobility-sweden/processed/market_model_monthly_stats.csv`
- `data/mobility-sweden/processed/market_model_monthly_stats.json`

The importer intentionally extracts market activity only. It does not extract specs or prices.

Then build the canonical/source queues:

```bash
python scripts/build_source_queue.py
python scripts/validate_manufacturer_sources.py
```

Current first pass from the March 2026 Mobility Sweden report:

- 124 raw electric passenger-car market rows
- 119 canonical draft model rows
- 124 model aliases
- 119 manufacturer/importer source candidates
- 5 aliases requiring manual mapping
- 19 official model URLs currently reachable by the validator

Rows marked `needs_discovery` or `unreachable_or_redirect_problem` must not be used for extraction until a better official source URL is resolved.

## Supabase Setup

Apply the database migration:

```bash
supabase db push
```

Or run `database/migrations/001_ev_database.sql` in the Supabase SQL editor.

Seed Supabase with service-role credentials:

```bash
python scripts/import_mobility_sweden.py
python scripts/build_source_queue.py
python scripts/validate_manufacturer_sources.py
python scripts/seed_supabase.py
```

Required server-side environment variables:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

The service role key is only for local/server import scripts. The browser must only use:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

## Official Source Discovery

Run:

```bash
python scripts/discover_official_sources.py
```

This creates `data/canonical/manufacturer_sources_discovery_candidates.csv` for rows that still need better official source URLs. These candidates should be validated before extraction.

## AI Extraction And Validation

Run extraction only after sources are validated:

```bash
python scripts/extract_manufacturer_specs.py --limit 5
python scripts/validate_extracted_variants.py
python scripts/seed_supabase.py
```

Required extraction environment variables:

- `OPENAI_API_KEY`
- `OPENAI_MODEL` optional, defaults to `gpt-4.1-mini`

Extraction writes only to `data/extraction/extracted_variant_drafts.*`. Public canonical variants are written only by the validator when:

- source is `reachable_official_model_source`
- confidence is at least `0.92`
- source hash and source quote exist
- at least price or WLTP exists
- hard numeric validation passes
