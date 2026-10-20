# Toyota Current Price Intake

## Inspection And Scope

2026-10-20: canonical has two bZ4X Active FWD/AWD records from a 2024 MY23
price list. Battery identity is unknown, and their range excerpts are preliminary.
The current Swedish model page links directly to an extensionless PDF on
`pdf.toyotasverigebroschyr.com`. A generic trim-name alias cannot prove that a
current battery/power version is the same old canonical variant.

## Smallest Useful Slice

1. Re-discover the exact PDF link on Toyota's official Swedish model page.
2. Permit only that exact linked document, not the entire external domain.
   Preserve robots, redirect, size and TDM-reservation checks.
3. Attempt bounded PDF collection. If unavailable, use the official specification
   page's structured current-configuration JSON, with exact manufacturer car ID,
   battery, drivetrain, power, grade and source pointers. Do not invent PDF rows.
4. Save field-level evidence, hashes and discovery provenance in private staging.
   Keep all unresolved generation/identity mappings in quarantine. Do not merge
   model-level maxima, leasing payments or range intervals into variant facts.
5. Test access policy, malformed/old documents, price types and mapping ambiguity;
   check canonical parity, existing refresh regressions and build.

No canonical updates, availability changes, schema migration, paid AI, DNS or
news changes are part of this intake. Migration 010 remains restricted to the
previously inspected Polestar source. A publisher for new exact identities is a
separate, tested integration step, not an unrestricted service-role upsert.

## Status

Follow-up: publication preparation has independently validated a fresh source
configuration and the private candidate is now `validated`, not public. Migration
011 is tested/prepared but awaiting approval. See `docs/toyota-variant-publication.md`.
The results below describe the earlier intake stage.

Implemented and run against the live official source:

- One exact current configuration extracted and staged as `needs_review`:
  Active FWD 57.7 kWh 167 hk. This is a candidate, not a new public record.
- Source pointers bind each value to its exact manufacturer car ID and document
  hash. Cash price is not inferred from monthly payments or promotion totals.
  Price classification remains null: VAT arithmetic alone does not prove list price.
- Intervals/preliminary values remain null. DC/AC power and boot volume remain
  unknown when not present in this exact configuration. Only the selected car
  can contribute its specific towing/seating values to the draft.
- Both legacy Active FWD/AWD identities remain `needs_mapping`: battery identity
  is absent in the old records. No alias is inferred from grade or drivetrain.
- The linked PDF server allowed robots access and returned PDF headers but
  document body collection failed/timed out. Its unresolved job is quarantined
  and retained across unrelated runs. No PDF price-table extractor was completed
  or claimed verified; visual PDF review remains pending a successful download.
- Source collection now has a body-stream deadline. A missing SSR configuration
  may be retried once; access denials and TDM reservations are never bypassed.
- No canonical vehicle values, timestamps, flags, images or public views changed.
  No schema migration or paid AI request was needed.

## Commands And Remaining Work

- `catalog:toyota:dry-run`: local extraction only.
- `catalog:toyota:stage`: private source/draft upserts, never canonical writes.
- `node scripts/run_python.mjs scripts/toyota_price_intake.py --stage --check-pdf`:
  same intake plus a bounded fresh PDF attempt.
- `verify:toyota-intake`: offline regression tests.

Next recommended slice: a transactional publisher for a **new, fully identified**
variant, keeping old-generation identities separate. Require exact ID/battery/
power/grade evidence, source precedence, optimistic concurrency and public-role
denial tests. Obtain the remaining grade/motorization pages via official links
before claiming complete bZ4X coverage. Migration 010 must not be widened by an
unchecked client-side bypass. Replacement/retirement of old records is separate.

Changed files: `scripts/toyota_price_intake.py`, `scripts/audit_catalog_sources.py`,
`tests/test_toyota_intake.py`, `package.json`, `.github/workflows/ci.yml`,
`data/review/toyota_price_intake.json`, this plan and deployment/refresh status docs.

## Verification

- Twelve new intake tests plus all eight source-audit and nine exact-refresh
  tests pass. PostgreSQL transactional refresh/rollback and role-denial tests pass.
- Staging was run twice against Supabase; one private candidate exists, with
  `needs_review` and `canonical_identity_mapping_required`, not duplicate rows.
- The anonymous public view still matches all 29 fields of the 66-variant
  snapshot. All seven internal tables still deny public reads.
- Advisor data and AI cost-cap tests pass, with no real provider calls.
- Production build and 76-URL SEO validation pass. No public UI was changed,
  so the existing tested preview is intentionally not redeployed for this intake.
- GitHub CI runs the new test suite and installs its PDF test dependency.
  Full source/PDF attempts stay under ignored local storage, never public assets.
