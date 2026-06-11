# AGENTS.md

Permanent project rules for the Swedish EV Advisor codebase.

## Product Direction

- Build a public Swedish consumer service for comparing electric cars, not a private admin database.
- The main user-facing feature is an AI car advisor backed by verified canonical database records.
- The product should feel premium, Nordic, clean, bright, useful, and trustworthy.
- Prefer concrete recommendations, visible tradeoffs, sources, and comparison workflows over campaign-style marketing.
- Swedish copy is the default for all public UI.

## Data Authority

- Supabase/Postgres is the canonical database.
- Public UI and public APIs may read only canonical validated data through public views such as `public_ev_models` and `public_ev_variants`.
- Mobility Sweden is the Swedish market/model discovery source only.
- Mobility Sweden proves market presence and registration activity. It must not be treated as a price, specification, availability, or variant source.
- Official Swedish manufacturer/importer pages are the primary sources for prices, trims, technical specs, PDFs, configurators, and current availability.
- Do not scrape or use third-party comparison sites as price/spec sources.

## Ingestion Model

- The database should be source-driven and automated.
- Build the first public MVP around the top 20-30 Swedish EV models by registration activity, then expand to the full Mobility Sweden-discovered model set after the pipeline is proven.
- Do not design normal manual data entry workflows for canonical car data.
- Human review is allowed for quarantined data, alias mapping, source approval, and final exception handling.
- Ambiguous Mobility Sweden names must be stored as `needs_mapping` or `model_group` until a deterministic alias rule exists.
- Raw market names must be matched to canonical models through `model_aliases`.

## AI Extraction Rules

- AI may extract structured data only from official Swedish manufacturer/importer sources.
- AI output must first be stored in staging tables such as `extracted_variant_drafts`.
- AI-extracted data is not public by default.
- Every extracted fact intended for publication must have source URL, source hash, confidence, and enough traceability for review.
- Use strict schemas for extracted fields: model, variant, price, WLTP range, battery, charging, boot volume, tow capacity, seats, drivetrain, source URL, source snippet, and confidence.

## Validation And Publishing

- Publish only canonical validated records.
- High-confidence autopublishing is allowed only when all conditions pass:
  - official source is reachable and accepted
  - extraction confidence is at or above the configured threshold, currently `0.92`
  - hard numeric validation rules pass
  - required source URL and source hash are present
  - the variant has at least price or WLTP range plus source evidence
- Uncertain, conflicting, blocked, low-confidence, or incomplete extraction results must go to quarantine/review, not public tables.
- Quarantine should preserve raw output, source metadata, validation errors, and suggested next actions.

## Public Surface Rules

- Public advisor context must include only canonical validated models and variants.
- Public pages may show Mobility Sweden-derived market flags, but never as specification evidence.
- Public pages should distinguish:
  - `market_seen`
  - `available_confirmed`
  - `discontinued_candidate`
  - `coming_or_low_volume`
- The UI must show clear source and verification signals for specs and prices.

## Engineering Rules

- Keep data pipeline code deterministic where possible and AI-assisted only where it adds value.
- Prefer idempotent import/upsert scripts over one-off local mutations.
- Use migrations for database schema changes.
- Keep service-role Supabase operations in scripts/server contexts only. Frontend must use anon/public read access.
- Add focused tests for ingestion, source validation, extraction validation, publishing rules, and public data filtering.
- Do not commit secrets. Use `.env.example` for documented configuration.
