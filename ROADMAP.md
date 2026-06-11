# ROADMAP.md

Phased implementation roadmap for Swedish EV Advisor.

## MVP Scope

The first public version should focus on the top 20-30 Swedish EV models by recent Mobility Sweden registration activity. The goal is to prove the complete automated pipeline on the models users are most likely to compare first. After the data flow is reliable, expand the same process to the full Mobility Sweden-discovered model set.

MVP principles:
- Prioritize high-volume, currently relevant models.
- Do not manually enter normal car data just to fill gaps.
- It is better to publish fewer validated models than many uncertain records.
- Keep low-confidence, conflicting, or ambiguous data in quarantine.

## Phase 0 - Project Guardrails

Goal: Lock the product, data, and execution rules before adding more features.

Deliverables:
- `AGENTS.md` with permanent project rules.
- `ROADMAP.md` with phases 0-9.
- `PLANS.md` with the execution template.
- Clear rule that public UI reads only canonical validated data.

Exit criteria:
- Future work can be evaluated against source authority, validation, and publishing rules.

## Phase 1 - Canonical Database Foundation

Goal: Make Supabase/Postgres the durable source of truth.

Deliverables:
- Complete migrations for canonical models, variants, market models, aliases, manufacturer sources, staging drafts, validation errors, and public views.
- Row-level security and read-only public views.
- Service-role-only import/upsert scripts.
- Seed data load path for local and Supabase environments.

Exit criteria:
- Public app can read from `public_ev_models` and `public_ev_variants`.
- Non-validated staging rows cannot appear publicly.

## Phase 2 - Mobility Sweden Market Discovery

Goal: Use Mobility Sweden only to discover Swedish market presence.

Deliverables:
- Repeatable Mobility Sweden import.
- Filter for Swedish passenger EVs.
- Aggregate brand/model/month into `market_models` and `market_model_monthly_stats`.
- Normalize raw names.
- Mark ambiguous grouped names as `needs_mapping` or `model_group`.

Exit criteria:
- Mobility Sweden data populates market presence fields only.
- No price/spec fields are filled from Mobility Sweden.

## Phase 3 - Alias And Canonical Draft Creation

Goal: Convert market-discovered names into canonical model drafts safely.

Deliverables:
- Rank matched models by recent registration activity and select an MVP scope of top 20-30 models for source discovery and extraction.
- Deterministic alias matching through `model_aliases`.
- Canonical draft creation for matched models.
- Quarantine queue for ambiguous names such as grouped model labels.
- Tests for ambiguous mappings and deterministic matches.

Exit criteria:
- Matched market models create/update canonical drafts.
- Ambiguous names never silently publish.

## Phase 4 - Manufacturer Source Discovery

Goal: Find official Swedish manufacturer/importer sources for the MVP model set first, then expand coverage.

Deliverables:
- Automated discovery candidates for model pages, price lists, technical PDFs, and configurators, starting with the top 20-30 models.
- `manufacturer_sources` rows with URL, source type, HTTP status, content hash, validation status, and last fetch time.
- Domain allowlist/validation logic for official Swedish/importer domains.
- Blocked or broken URLs marked `needs_discovery`.

Exit criteria:
- Extraction queue contains only reachable accepted official sources.
- No third-party comparison sources enter extraction.

## Phase 5 - AI Structured Extraction

Goal: Extract variant, price, and spec data from official sources into staging for the MVP model set first.

Deliverables:
- `extract_manufacturer_specs.py` with HTML/PDF text extraction and chunking.
- OpenAI structured extraction with strict JSON schema.
- Staging writes to `extracted_variant_drafts`.
- Source URL, source hash, snippet, confidence, and raw payload stored.

Exit criteria:
- AI output for the top 20-30 model set is reproducible enough to audit.
- AI output remains non-public until validation/publishing.

## Phase 6 - Validation, Quarantine, And Autopublishing

Goal: Promote only reliable extracted facts into canonical public tables.

Deliverables:
- Hard validation rules for price, WLTP, battery, charging, tow, boot, seats, and required evidence.
- Conflict detection against existing canonical values.
- High-confidence autopublishing when confidence >= `0.92` and all rules pass.
- Quarantine/review status for uncertain, conflicting, incomplete, blocked, or low-confidence data.

Exit criteria:
- Valid high-confidence records publish automatically.
- Any failed condition prevents public exposure and creates reviewable diagnostics.

## Phase 7 - Public Advisor Data Contract

Goal: Ensure the AI advisor uses only canonical validated records.

Deliverables:
- Public read API/view contract for advisor context.
- Advisor retrieval/filtering against published variants only.
- Market flags visible as context but not as spec evidence.
- Source citations in advisor responses.

Exit criteria:
- Advisor cannot access staging/quarantine data.
- Recommendations include validated records and source-aware tradeoffs.

## Phase 8 - Programmatic SEO And Public Pages

Goal: Make the tool discoverable without becoming a media site.

Deliverables:
- Per-car pages generated from canonical validated records.
- Segment pages such as family, winter, towing, budget, and long range.
- Route-specific title, meta description, canonical, sitemap, and JSON-LD.
- Static/prerendered HTML for indexable routes.

Exit criteria:
- Google can discover indexable pages from sitemap.
- Search pages do not expose unvalidated data.

## Phase 9 - Operations, Monitoring, And Review Workflow

Goal: Keep data fresh, trustworthy, and maintainable.

Deliverables:
- Scheduled imports and source refreshes.
- Monitoring for source changes, hash changes, validation failures, and stale records.
- Review workflow for quarantine and conflicting data.
- Audit logs for publication decisions.
- Generated MVP readiness report that summarizes coverage, public-data contracts, source health, and deployment blockers.
- Deployment checklist for Supabase migrations, environment variables, build, sitemap, and prerender.

Exit criteria:
- The database can stay current with minimal manual work.
- Humans review exceptions, not normal data entry.
