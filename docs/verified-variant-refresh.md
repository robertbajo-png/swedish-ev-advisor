# Verified Variant Refresh

## Inspection And Scope

2026-10-20: release catalog parity is complete (66 canonical variants). The old
extractor can combine model-level maxima with a generic model name and infer
list price from a from-price. It must not run unattended for this refresh.
Canonical variants also have null source IDs, so updating a source timestamp
alone would not actually verify those variants.

Smallest useful slice: re-extract the three existing Polestar 2 variants from
the official Swedish specification table, preserving table-column identity and
field evidence. Inspect the changed Polestar 4 source but quarantine renamed or
preliminary variants. Discover Toyota's current price-list links; never reuse the
2024 PDF as a current price source or map a new battery version by name alone.
Mobility Sweden, model expansion, news, DNS and the AI spending policy are unchanged.

## Execution

1. Extend the existing robots/redirect/TDM-aware fetcher with an optional document
   parser. Parse real HTML table cells and definition lists, not flattened first
   numbers, scripts or invented responses. No paid AI is needed for this adapter.
2. Match exact existing variant headers. Every non-null field needs source URL,
   SHA-256, a literal excerpt and explicit variant/common-model scope. Intervals
   remain unknown, preliminary figures and renamed variants go to quarantine.
3. Reuse hard validation; add independent evidence, identity, data-loss and
   large-change checks. Keep missing price classification null.
4. Stage all results before publication. Add a service-role-only transactional
   refresh function: optimistic concurrency, exact source-group coverage,
   validated drafts, unchanged identities/market flags, all-or-nothing variant
   and source updates. No public role gains table or function access.
5. Test parser adversarial cases, stale/concurrent packets, partial batches,
   rollback, access control and idempotence. Prepare the migration for owner
   confirmation before executing it through the dashboard.
6. Publish only fully validated packets, export the anonymous canonical view,
   test/build/CI and update only the AI preview. Do not call the whole source
   freshness milestone complete after one batch.

## Current Results

- Implemented: semantic HTML tables/definition lists, exact header matching,
  literal field evidence and independent numeric/evidence checks. A plain
  from-price does not imply list price; WLTP consumption intervals remain null.
- Live run: three existing Polestar 2 variants were staged, validated and
  published through the transactional Supabase function. The source was fetched
  at `2026-10-20T17:31:38.226134+00:00`. Prices and technical values already
  matched; only source evidence/linkage, confidence and verification dates changed.
  No availability flags changed. The catalog remains 66 variants / 30 models.
- Two Polestar 4 updates are quarantined: the current table has different
  variant names. Existing public rows are untouched. Text elsewhere on that
  page is not used to infer an alias.
- Toyota's Swedish model page links to an extensionless price-list PDF at
  `https://pdf.toyotasverigebroschyr.com/price-list/toyota-bz4x`. Discovery preserves
  the official referring URL, label and hash. The external document host remains
  unapproved for automated extraction; no current Toyota price was published.
- Migration 010 and the same fresh-install function are tested in PostgreSQL /
  PGlite. Source-group coverage, staging, numeric limits, field evidence, stale
  packets, concurrency, late-error rollback, replay and role denials pass.
- Nine extraction/worker tests and eight source-audit tests pass. These include
  TDM reservations before extraction, regardless of meta-attribute order.
- Migration 010 was applied after explicit owner approval. Dashboard and remote
  checks confirm no anonymous/authenticated execution, server-role execution
  only, and all seven internal vehicle tables remain inaccessible publicly.
- Replaying the actual published packet returned `already_applied: true` without
  changing values or dates. The anonymous export matches all 29 public fields:
  `8d436119b4a289a3ed25117597cc9d31cdfc94c28f02720002ebf894c1b7c09d`.
  The three earlier local-only model profiles remain quarantined, not inserted.
- The follow-up read-only audit checked 33 source URLs: 17 reachable, 12 blocked
  or unavailable under robots rules, three HTTP errors and one fetch/parse failure.
  Three Polestar 2 rows have unchanged hashes and evidence. An audit is not a
  new fact verification and never advances verification dates.
- No paid OpenAI calls were made. Remaining 63 public variants were not refreshed
  in this batch; this does not complete catalog freshness or release readiness.
- Build, SEO and full GitHub CI passed for runtime
  `3ffb28262c2493736b512bdbb865aa9540bf0d13` (run `39467788570`), including all
  responsive/accessibility flows. The AI preview is published at
  https://a5c4f6b7.seekev-ai-preview.pages.dev/ and the stable preview alias.
  Both passed eight external GET checks and exact 29-field Supabase parity.
  The car page visibly shows the new verification date; missing values remain
  unknown. The remote budget emergency-stop exercise passed for both endpoints
  and restored the policy. Ledger unchanged: two settled requests / 2,636 micro-USD.
  There is no separate configured lint/typecheck command in this JS project.

## Commands

- `catalog:refresh:dry-run`: fresh fetch, local validation and Toyota discovery;
  no Supabase writes.
- `catalog:refresh:stage`: stage validated exact variants, no canonical writes.
- `catalog:refresh:publish`: re-fetch, revalidate, stage, then call the atomic
  server-only publisher. Missing migration, changed facts or failed validation
  prevent publication. A schema change still requires the normal approval process.
- `verify:variant-refresh` and `verify:variant-refresh-extraction`: offline tests.

Every run keeps unresolved groups in `data/review/variant_refresh_quarantine.json`.
An unrelated batch or local-only validation cannot clear quarantine. SQL
publication preserves all model availability flags and refuses to silently clear
existing facts or overwrite a reviewed exception. Before-images remain in the
private source payload and ignored local journal.

## Remaining Work

- Completed: canonical export, database access checks, build/CI, preview upload,
  external catalog parity and cost-cap regression. See `docs/deployment-status.md`.
- Required: verify the external Toyota document host and map exact current
  battery/trim versions before replacing the 2024 price records.
- Defer: paid extraction, new variants and broader manufacturer coverage.

The legacy bulk seed is for bootstrap only, not ongoing refresh. Normal updates
must use validated, exact-variant packets through the transactional publisher;
do not reseed older local files over newer canonical facts.

Full source documents and before-images stay in ignored local storage. Reports
must distinguish fetched, extracted, validated and actually published records.

Changed files:
- `scripts/audit_catalog_sources.py`, `scripts/variant_refresh.py`, `scripts/refresh_verified_variants.py`
- `database/migrations/010_atomic_variant_refresh.sql`, `database/schema.sql`, `database/supabase_migration_bundle.sql`
- `scripts/verify_variant_refresh.mjs`, `tests/test_variant_refresh.py`, `tests/test_catalog_sources.py`
- `package.json`, `.github/workflows/ci.yml`
- `data/review/variant_refresh_report.json`, `data/review/variant_refresh_quarantine.json`
- `public/data/public_ev_variants.json`, `data/review/catalog_reconciliation.json`
- `data/mvp/release_source_audit.json`, `data/review/source_reverification_queue.json`
- `docs/verified-variant-refresh.md`, `docs/deployment-status.md`
