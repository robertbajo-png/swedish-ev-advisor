# Current Variant Replacement

The owner approved replacing incorrect or obsolete variants on 2026-10-27,
provided every model remains available and old links keep working. This is not
permission to copy old technical maxima into new trims or waive release gates.

## First Bounded Batch

- Kia EV3, EV4, EV5 AWD and EV9 RWD: exact complete version names and cash-price
  columns on Kia Sweden's price page, never financing amounts or generic starts.
- Polestar 4 **coupe**, not the new SUV: two exact drivetrain/price columns.
  The page's WLTP targets are deliberately not treated as certified ranges.
- Renault 5: the price PDF linked by the current official Swedish importer page.
  The CDN URL is accepted only with a fresh exact parent-link/hash relationship.
  Expired webpage campaigns and finance/service bundles are not imported.

These are basic price-only profiles. Every technical field remains null until
independently supported for that exact variant. They do not inherit old range,
charging, luggage, battery, drivetrain or towing values.

## Commands

```powershell
node scripts/run_python.mjs scripts/current_variant_intake.py
node scripts/refresh_current_variants.mjs --client-module <private-TLS-client-module>
node scripts/refresh_current_variants.mjs --client-module <private-TLS-client-module> --apply <prepared-plan-sha256>
```

The private server module exports `openSourceSnapshot` and `closeSourceSnapshot`.
It must authenticate with the existing strict-TLS, project-bound database client;
it is not a browser credential or a reason to expose a database URL. Dry-run is
the default. Evidence must be at most 15 minutes old. Apply fetches and extracts
the official documents again; changed price-document hashes, prices or exact-version rows stop
the operation. No paid AI call is used.

A discovery parent page may change navigation or marketing bytes while linking
the same PDF. Its new hash is retained in the private recollection receipt; it
cannot authorize different PDF bytes, a different parent/link, or changed facts.

## Transaction And History

The tested serializable transaction locks the canonical variant snapshot,
rejects concurrent edits and unexpected identities, writes validated extraction
staging, inserts new published profiles, and soft-retires only the explicitly
approved old variants to `needs_review`. Their original facts/evidence remain
intact. All models, images, availability flags and unrelated variants must be
byte-equivalent after normalization; the public model ID set cannot change.

Shared manufacturer-source timestamps are **not** refreshed globally, because
that could make another variant's older technical evidence appear current.
New price provenance uses the existing dedicated price fields. No schema,
permissions, RLS, passwords, budget or news-publication settings change.

Old slugs are generated into `src/vehicle-redirects.json`. Both SPA routing and
static 301/non-JavaScript fallbacks lead to the same model's filtered catalog,
not a guessed replacement engine or trim. Build rejects missing models,
duplicate/unsafe redirects and collisions with current variant URLs. Retired
URLs are excluded from the sitemap. Publication receipts and historical
snapshots stay in ignored local release data; never commit raw private exports.

If apply reports an error after a possible commit, inspect the committed receipt
and actual database state first. Do not blindly replay or overwrite staging
history. Replays reject existing new identities rather than duplicating them.

## Checks

`verify:current-intake`, `verify:current-variants`, and
`verify:vehicle-redirects` run offline. The PostgreSQL test uses PGlite with the
actual schema and verifies late-failure rollback, retained history, unchanged
shared-source dates, public/private access boundaries, and rejected replays.
These tests do not count as live source collection or public deployment.

## Applied Receipt: 2026-10-27

The first batch committed under plan
`71642a8a52871d86e10a3e701ca355331b63f6a70bd1ca9fe8dfe81e2d4b7c3d`:
20 exact price-only profiles published, 11 old variants retained privately as
`needs_review`, all 30 public model IDs preserved. The same two published news
articles and every news configuration field were unchanged. No paid AI calls,
password changes, schema changes or production-domain cutover occurred.

This receipt is a catalog correction, not a declaration that all remaining
prices, supplier privacy settings or full public-release gates are cleared.
