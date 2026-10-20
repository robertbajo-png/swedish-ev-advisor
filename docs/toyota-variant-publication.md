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

Implemented and tested locally. One fresh exact Toyota configuration has passed
the independent worker checks and is `validated` in private staging. The public
catalog still has 66 variants and is identical in all 29 fields. Migration 011
is prepared in a separate Supabase SQL tab, not executed. Owner approval was
requested before database execution. No new public Toyota row has been inserted.

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
- Build and 76-URL SEO validation pass. No separate lint/typecheck is configured.
- Required: owner-approved database migration, fresh initial publication,
  canonical export, build/CI and AI-preview publication with external checks.
- Deferred: remaining Toyota configurations, generic source-group refresh,
  legacy-generation retirement, model expansion, production/DNS and paid AI.

Changed files:
- `database/migrations/011_exact_toyota_variant_publication.sql`, `database/schema.sql`, `database/supabase_migration_bundle.sql`
- `scripts/publish_toyota_variants.py`, `scripts/toyota_price_intake.py`, `scripts/verify_toyota_publication.mjs`
- `tests/test_toyota_publication.py`, `package.json`, `.github/workflows/ci.yml`
- `data/review/toyota_publication_report.json`, this plan and related status docs
