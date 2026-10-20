# Toyota Grade Expansion

## Status And Missing Pieces

The canonical catalog has 67 variants, including one exact current bZ4X Active
identity. The manufacturer specification configuration also lists other grades
and their default car IDs, but it does not provide their prices/specifications.
Legacy Active FWD/AWD cannot be mapped from trim names alone.

## Smallest Useful Slice

1. Reuse the bounded, robots/TDM-aware Toyota collector and exact extractor.
2. Discover grades from the Swedish configuration with JSON-pointer evidence.
3. Reconcile manufacturer IDs using private read-only canonical queries.
4. Queue undiscovered configurations without constructing purported source URLs
   or copying selected-car facts into another grade. Do not publish or stage
   incomplete identities as vehicle variants.
5. Test stale sources, duplicate IDs, selected-grade mismatches, repeatability,
   secret exclusion and absence of remote writes; run existing tests/build.

No migration, paid AI, canonical writes, UI redesign or preview upload is needed
for this discovery-only slice. A grade default is not a complete variant list.

## Verified Result

The live read-only run at `2026-10-20T19:57:58.133033+00:00` found three grades:

- Active: its default manufacturer identity is already public.
- Active Tech: default identity discovered; exact configuration source unresolved.
- Executive: default identity discovered; exact configuration source unresolved.

Evidence and stable queue IDs are in `data/review/toyota_grade_discovery.json`.
Only grade names/IDs and literal field evidence are retained, not unrelated
embedded service settings. No source URL is invented for an unresolved grade.
The two legacy records remain `needs_mapping`; discovery is not retirement.

The browser connection timed out. A bounded direct configuration-route probe
also returned no initialized configuration and was not accepted as a source.
No prices or specifications were copied from Active to either queued grade.

Commands:

- `bun run catalog:toyota:discover-grades`: fresh official fetch, two private
  canonical SELECTs and a local review report only. No remote staging or writes.
- `bun run verify:toyota-grade-discovery`: eight offline regression tests.

All 26 Toyota tests pass, including stale/wrong-market rejection, exact evidence,
ID conflicts, stable queue identities and read-only operation. Build and 77-URL
SEO validation pass. Anonymous canonical parity confirms all 29 fields unchanged
across the same 67 public variants. CI includes the new suite. There is no
separate lint/typecheck command. The existing tested AI-preview stays unchanged.

Changed files: `scripts/discover_toyota_grades.py`,
`tests/test_toyota_grade_discovery.py`, `package.json`, `.github/workflows/ci.yml`,
`data/review/toyota_grade_discovery.json`, this plan and deployment status.

## Next Slice

Resolve each queued default through a manufacturer-provided link or functioning
public selector. Fetch its exact Swedish configuration, check selected car/grade/
model IDs and extract only that configuration's own facts. A broader publisher
must validate this provenance independently before any new canonical insert.
Do not widen migration 011's single-source contract as a shortcut. Retirement
of old-generation records remains a separate, evidence-backed operation.
