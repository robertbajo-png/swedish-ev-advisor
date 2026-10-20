# Exact Toyota Variant Publication

## Inspection And Scope

The intake has one exact, source-backed candidate but no safe canonical insert
path. Migration 010 updates existing Polestar variants only. Legacy Toyota
Active FWD/AWD names lack battery/generation identity and must not be reused.

## Execution Plan

1. Add nullable manufacturer model/variant IDs and configuration version to the
   private canonical variant table. Preserve existing views, grants and RLS.
2. Add a service-only transactional publisher limited to the inspected Toyota
   Swedish specification URL. Require validated staging, fresh evidence, exact
   identity, source pointers, hard numeric rules and optimistic concurrency.
3. Independently re-extract a fresh, sanitized source configuration before
   validating/staging publication candidates. No cached success can masquerade
   as a fresh source. Never write canonical rows directly from the worker.
4. Test rollback, stale/conflicting packets, evidence tampering, role denials,
   unique identities, retries and unchanged legacy records/market flags.
5. Apply migration after owner confirmation. Publish only a passing first source
   group, export canonical data and test/build/CI before AI-preview upload.

This is initial publication, not a generic update/retirement function. An
already-public source cannot advance verification dates for other variants.
New source groups/configuration URLs and old-generation retirement remain separate.
No paid AI, DNS, news or unrelated product changes.

## Current Status

Migration 011 was installed in Supabase on 2026-10-20 after explicit owner
approval. The SQL readback confirmed anon/authenticated EXECUTE=false,
service_role EXECUTE=true and 66 unchanged public variants before publication.
The fresh worker then inserted one exact Toyota identity transactionally:
`Active FWD 57.7 kWh 167 hk`, manufacturer variant ID
`552b7e03-84d2-4b36-a5bb-87d84cb7d05c`.

The catalog now has 67 variants / 30 models. Its anonymous-view export matches
all 29 public fields, with SHA-256
`042806f32cc2cbcfe971d8c5f833f2f8a82701b66e9277bd9206dceaa2cbfb0e`.
The fresh source was verified at `2026-10-20T19:03:51.097915+00:00`, hash
`bb43334b585c1691f5e62719a08bbd0f3a9e0e99b29c94486de7845290e57fab`.
Cash price is 479900 SEK, WLTP 444 km, battery 57.7 kWh, consumption
13.9 kWh/100 km and towing 750 kg. Price classification, DC/AC charging,
boot volume and model image remain null; availability is not confirmed.
The existing 66 rows and three local-only quarantined profiles were preserved.

The RPC checks the original JSON pointers and conversions again in PostgreSQL,
not just the worker's confidence flag. It rejects partial source groups,
unapproved sources, unsupported fields, stale packets, changed drafts and
existing identities. The canonical insert, draft publication and source
verification commit together or roll back together. Replay returns the same IDs
without changing dates. It never changes legacy rows or model availability.

## Commands

- `catalog:toyota:publication:dry-run`: fresh source + database reads, no writes.
- `catalog:toyota:publication:prepare`: conditional private-draft updates only.
- `catalog:toyota:publish`: fresh validation/preparation followed by the RPC.
  Requires migration 011; no direct canonical upsert fallback exists.
- `verify:toyota-publication`: PostgreSQL/PGlite transaction and role tests.
- `verify:toyota-publication-worker`: six offline worker tests.

Fresh packets expire after 15 minutes. Do not replay an old prepared packet as
new evidence. An already-public exact identity is detected read-only; changed
facts/identities require the separate refresh workflow. No missing field is
filled from another motorization, model maxima, leasing or previous generation.

## Verification And Remaining Work

- Migration is idempotent and mirrored exactly in fresh schema and migration bundle.
- Transaction rollback, source-pointer tampering, identity collisions, numeric
  limits, source/draft concurrency and public-role denials pass in PostgreSQL.
- Six publication-worker, twelve Toyota-intake, nine existing-refresh and eight
  source-audit tests pass. Existing migration/security/catalog/AI-budget tests pass.
- Anonymous Supabase parity and all seven private-table denials pass after staging.
- The installed RPC replay returned inserted=0/already_applied=true; a before/
  after comparison proved all public fields and dates unchanged across 67 rows.
- All 18 Toyota tests and PostgreSQL transaction tests pass again after migration.
- Build and 77-URL SEO validation pass. No separate lint/typecheck is configured.
- Remaining delivery check: exact-commit CI and AI-preview publication followed
  by external parity and free budget-stop verification.
- Deferred: remaining Toyota configurations, generic source-group refresh,
  legacy-generation retirement, model expansion, production/DNS and paid AI.

Changed files:
- `database/migrations/011_exact_toyota_variant_publication.sql`, `database/schema.sql`, `database/supabase_migration_bundle.sql`
- `scripts/publish_toyota_variants.py`, `scripts/toyota_price_intake.py`, `scripts/verify_toyota_publication.mjs`
- `tests/test_toyota_publication.py`, `package.json`, `.github/workflows/ci.yml`
- `data/review/toyota_publication_report.json`, this plan and related status docs
