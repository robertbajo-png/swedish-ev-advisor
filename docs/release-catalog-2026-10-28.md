# Catalog Release: 2026-10-28

## Verified Database State

The owner approved replacing obsolete or mixed variants with exact current
source-bound variants while preserving all model identities and old links.
The real Supabase public views now contain 30 models and 76 published variants.
There are 56 prices, all within the release freshness window, and zero prices
requiring verification. This is not a claim that every model is orderable or
that every specification is known.

Catalog SHA-256:
`c91c8f884f8f222f3566b8d285bb3d5ea320a729c68a5ccfe81a21d74ee113c9`.

The remaining-model lane retired 26 legacy variants privately and created 26
exact profiles across 14 model groups. Original facts remain intact. The public
snapshot is exported from the canonical views, not the private staging files.
Model IDs, availability flags and verified model images were preserved.

- Skoda Elroq: seven exact Explore Edition campaign-price profiles, expiry
  2026-12-15. Preliminary PDF ranges were not promoted to verified WLTP.
- Cupra Born, Mazda 6e and Volkswagen ID.3: exact current trim/grade prices,
  without borrowing another version's specifications.
- Ford Explorer and Zeekr 7X: exact battery/drive WLTP profiles. Unverified
  prices and vehicle charging power remain null.
- Toyota bZ4X: retained the already verified current Active variant unchanged;
  retired the obsolete MY23 variants after fresh configuration checks.
- BMW i4, Volvo ES90/EX30, Audi A6/Q6, Volkswagen ID.4 and Mercedes CLA:
  exact new-stock cash offers. These are `dealer_offer`, not general list prices.
  Importer stock prices include the explicitly mandatory delivery fee.

Used, demo, sold, ICE, estate/sedan conflicts, leasing instalments, zero-valued
lease offers and unqualified campaigns were rejected. Dealer evidence is scoped
to the reviewed model/facility and authorization proof, not blanket approval of
all stock on a domain. Missing specifications remain null.

## Reusable Pipeline

- `catalog:remaining:collect` selects pending legacy identities from the current
  public snapshot and fetches permitted official/dealer sources.
- Public embedded JSON is parsed, never executed. Only proven incidental render
  IDs may be normalized; model, price, legal and material context changes stop
  the prepared operation. PDFs require the original byte hash.
- `refresh_current_variants.mjs --batch remaining` defaults to a dry run.
  Applying requires the exact prepared hash, a fresh source re-fetch, reviewed
  server-side policy and a project-bound server connection.
- Publication is serializable, guarded against replay/concurrent changes and
  rolls back on any staging collision. No unrelated variants, model data or
  shared historical source verification dates are refreshed.
- The completed default collection is a no-op: zero pending groups, zero held
  sources, no database writes and no AI calls.
- Migration 021 only adds the two already documented dealer source enum values
  missing from the live legacy database. It was tested twice for idempotence and
  applied without changing existing rows, policies or privileges.

## Navigation And UI

There are 38 retained-variant redirects to the same model's filtered catalog,
not an assumed successor drivetrain. Shared name normalization preserves the
real Audi Sportback URL and its historical duplicate-name alias. Model-filtered
entry links use the full supported price ceiling; canonical model names remain
searchable even when the displayed variant contains additional body-style words.

Comparison report names use the same model normalization. Price labels have a
consistent footer slot, so list/campaign/dealer prices share a baseline. Mobile
selection headings use two visual lines while keeping the full link text and
detail-page identity. The unchanged 24-layout size/alignment checks passed.

No model-photo fallback was introduced. Missing fields remain visibly unknown,
not zero. Campaign/dealer labels and price-specific verification evidence remain
separate from older technical facts.

## Verification

Local checks passed for the transactional current/remaining-variant contracts,
legacy enum alignment, eight remaining-intake cases and six stock-intake cases.
Coverage includes rollback, replay, exact trim binding, fees/VAT, new condition,
dealer authorization, calendar-date expiry and rejection of unsupported facts.

The production build generated 90 routes and 38 retired-variant redirects.
SEO verification found 90 sitemap URLs and no errors. Automated UI QA audited
22 desktop/mobile page states with no reported axe violations, plus keyboard,
320/640px reflow, missing-data and provider-outage behaviour. This does not replace
all manual accessibility checks. Browser tests block paid requests.

Four-viewport home and vehicle workflow tests also passed, including filters,
sorting, drawer focus, CSV, report error/reset, explicit zero versus null and
missing-photo behaviour. News/journal UI fixtures passed without changing the
published export. Edge recommendation tests now select actually qualifying
verified records rather than depend on catalog order, and separately reject
unknown WLTP against a minimum-range requirement.

The real read-only Supabase probe returned 30 public models and 76 variants;
all seven private vehicle tables denied anonymous reads. No production writes
were used to prove access denials.

A fresh logical backup and isolated PostgreSQL 17 restore passed at
2026-10-27T23:56:55Z: 63 tables, 1,622 rows, two sequences, 13 metadata
categories and 14 private-access denials verified. The restore had no network
or published ports; its container was removed. Source access was read-only.
The private local receipt is in
`data/local/backups/postgres-2026-10-28-6e9f4c28/reports/receipt.json`.
It is not an off-site/PITR backup and excludes external Storage objects,
platform secrets, role passwords and external encryption root keys.

## Release Boundary

No paid AI calls were made. The same two published news articles, disabled news
AI/publication/notice switches and USD 0.25/day / USD 5/month limits were retained.
No passwords, DNS, production domains or hosting services were changed.

The configuration check now has one remaining blocker: `privacy_review`.
Keep `PUBLIC_PRIVACY_REVIEWED` false until the account-specific checks in
`privacy-operations.md` are evidenced. A valid API key and `store=false` do not
prove project-sharing settings, supplier contracting details or Zero Data
Retention. The browser-control connection timed out, and the owner was asked
for a non-secret screenshot of the relevant OpenAI sharing settings.

GitHub CI, preview distribution and final external verification are separate
delivery gates. Do not interpret this catalog result as production-domain release.
