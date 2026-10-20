# Release Data Refresh

## Status And Scope

Inspected 2026-10-20: Supabase public view has 66 variants, while the deployed
SQLite-derived snapshot has 69. The three local-only rows are model-level
profiles for Cupra Tavascan, Subaru Solterra and Volvo EX90. They must not be
silently inserted as exact, currently verified variants. Apparent differences
in price classification and two consumption fields were caused by absent remote
columns, not conflicting verified facts.
The remote view and underlying tables are missing six previously planned public
columns. Missing nullable columns are reported explicitly and exported as unknown,
not inferred from local seeds. Migration 009 adds the missing compatibility fields
without dropping views, altering ACLs or changing existing vehicle facts. The
owner explicitly approved execution, and migration 009 was applied through the
Supabase dashboard on 2026-10-20. The result was 66 public variants and all six
new contract columns. Anonymous private-table denials and server-role reads were
rechecked afterwards.

Supabase/Postgres remains canonical. Mobility Sweden is only the market index;
this task does not extend model discovery or enable the paused news service.

Missing pieces:
- Completed locally: release snapshot parity across browser, API and SEO.
- Completed: complete, anonymous public-view exports with content fingerprints.
- Completed: current source checks and an explicit re-extraction queue.
- Still required: exact-variant re-extraction and validation of current facts.
- Completed: publish the tested snapshot to the AI preview after green CI.
- Defer: new models, paid extraction, DNS, branding and production activation.

## Execution Plan

1. Fetch only `public_ev_variants` using a verified public credential, complete
   pagination and strict validation. Compare every public field, not only counts.
2. Write an atomic, fingerprinted snapshot from that view. Preserve local-only
   records and disagreements in a private reconciliation report, not public data.
3. Pin browser/API to the same deployment snapshot. CI rejects locally generated
   candidates masquerading as the Supabase release snapshot.
4. Re-fetch official sources in bounded batches, respecting robots and redirects.
   Keep fetch timestamps separate from fact verification. Changed/blocked/ambiguous
   evidence becomes a source re-verification job; it never overwrites public facts.
5. Test malformed/partial exports, evidence validation, field-level differences,
   stale source handling, fallback, build/SEO and consumer workflows.

## Commands And Safeguards

- `catalog:sync` reads Supabase with anon/publishable credentials only. Never
  configure a service-role credential as a public key. Empty, truncated, invalid
  or unstable reads cannot replace the committed release snapshot.
- `catalog:check` compares the full public contract without modifying anything.
- `catalog:audit` checks manufacturer source evidence, without OpenAI calls or
  Supabase writes. HTTP 200 alone never changes `verified_at` or confirms availability.
- `verify:catalog` is offline and validates the checked-in snapshot and exporter.
- Normal ingestion may still produce local candidates. Only a canonical public-view
  export passes the release gate. Publish verified ingestion results to Postgres
  before exporting them for a new site deployment.

No date is invented from an export time. No missing price type is defaulted to
list price. No current price is inferred from a monthly leasing advertisement.

## Results And Remaining Work

- Canonical export: 66 variants / 30 models. All 29 public fields match the
  anonymous Supabase view; no missing contract columns remain after migration.
- The three local-only profiles remain in `data/review/catalog_reconciliation.json`
  with `needs_review`. Repeated exports preserve this queue until canonical
  publication, rather than silently discarding or publishing the profiles.
- Source audit: 33 distinct official URLs across the 66 canonical variants and
  three quarantined profiles. 18 were readable, 12 denied by robots or unavailable
  for robots checks, and three returned HTTP errors. These are access results,
  not fact verification results.
- Every profile has a follow-up job. Findings include a 2024 Toyota price PDF,
  preliminary range figures and missing exact-variant evidence. No existing
  vehicle facts, verification dates or availability flags were changed by the
  audit. No paid AI calls were made.
- Audit reports carry the input catalog fingerprint. Full fetched source text is
  kept only in ignored local cache files, not public assets or Git.
- Unknown price classification is labelled `Prisuppgift`, not list price. Only
  confirmed list prices feed list-price value metrics; price comparisons do not
  highlight a cheapest winner when the price types are unknown or incompatible.

Next recommended slice: process the accessible exact-variant jobs in bounded
batches through the existing extraction/validation pipeline. Replace dated price
sources first. Keep unresolved rows and model-level maxima in quarantine. A
successful HTTP response or unchanged page hash alone must never advance a fact's
verification date or make a model available-confirmed.

Main changed files: `scripts/sync_public_catalog.mjs`,
`scripts/audit_catalog_sources.py`, `database/migrations/009_public_catalog_contract.sql`,
`public/data/public_ev_variants.json`, browser/API snapshot configuration and
focused catalog/migration/source-audit tests. Build, SEO and responsive consumer
workflow checks passed before preview publication.

Published runtime: `2a909c950232a1bdb667b4610a0a8ad3ee72cdcd`, green CI run
`39405643007`, https://61462c44.seekev-ai-preview.pages.dev/.
The stable alias https://codex-ai-preview.seekev-ai-preview.pages.dev/ points to
the same release. Both passed all eight external GET checks. Deployed 29-field
catalog parity against Supabase was rechecked; fingerprint
`c3aa59cbd8ff0daad5cfc41134d121b786ee1d507e7195577e5aa60ac0632ba6`.
The remote AI emergency-stop exercise passed for both routes and restored the
preview policy; the ledger stayed unchanged at two settled requests / 2,636
micro-USD. No paid provider requests were needed for this data slice.

Checks passed locally: public catalog contract and live 29-field parity;
idempotent migration against legacy and current PostgreSQL fixtures with unchanged
ACLs/facts/dependencies; seven source-audit unit tests; database access tests;
advisor/matching/Cloudflare/AI budget/TCO/deployment contracts; build and 76-URL
SEO export; homepage/vehicle/journal flows on four viewport sizes; 24 proportion
checks; 18 accessibility page states with zero automated violations. AI checks
use mocks, not paid provider calls. No separate typecheck/lint command is
configured in this JavaScript project.

Changed files for this slice:
- `.env.example`, `.gitignore`, `.github/workflows/ci.yml`, `package.json`, `wrangler.toml`
- `src/main.jsx`, `src/home.jsx`, `src/vehicle-ui.jsx`, `functions/_shared/http.mjs`
- `database/migrations/009_public_catalog_contract.sql`, `database/supabase_migration_bundle.sql`
- `scripts/sync_public_catalog.mjs`, `scripts/audit_catalog_sources.py`, `scripts/prerender_static_routes.py`
- `scripts/verify_public_catalog.mjs`, `scripts/verify_catalog_migration.mjs`, `scripts/verify_home_ui.mjs`, `scripts/verify_vehicle_ui.mjs`, `tests/test_catalog_sources.py`
- `public/data/public_ev_variants.json`, `public/sitemap.xml`, `data/mvp/programmatic_seo_report.json`
- `data/mvp/release_source_audit.json`, `data/review/catalog_reconciliation.json`, `data/review/source_reverification_queue.json`
- `docs/release-data-refresh.md`, `docs/deployment-status.md`
