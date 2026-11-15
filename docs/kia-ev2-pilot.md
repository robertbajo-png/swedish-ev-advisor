# Kia EV2 New-Model Pilot

Owner approval: 15 November2026. Implement the safe insertion route and publish
only after complete source, database, image, build and actual-site verification.

## Scope

- Existing canonical draft/alias `Kia Ev2`, no current variants. Add three exact
  five-seat profiles: base Standard Range16inch, base Long Range16inch and
  GT Line Long Range19inch. Do not combine the4-seat boot maximum403L with
  these5-seat versions'362L, or the base453km with GT Line413km.
- Swedish primary sources: September29 technical PDF, literal engine-table JSON,
  current November1-30 cash price list and model page. No paid AI is needed.
- Official October Mobility Sweden row proves registration activity only. Merge
  only EV2's current month, preserving March history, alias and first-seen date;
  no invented12-month total or manufacturer-availability claim.
- Exact professional manufacturer press photo with per-image permission,
  unchanged full frame, credit and model/trim notice. No invented/generic image.

## Transaction Contract

The reusable publisher consumes a prepared, hashed packet through a registered,
source-specific adapter and the existing server-side TLS connection. It requires
one existing resolved canonical draft, exact alias, no conflicting existing
version, complete field evidence/current prices and an approved local photo.
It stages the validated packet, inserts only the intended versions, readbacks
all fields, binds a batch receipt, and commits atomically. Replays of that exact
applied packet verify the saved artifact without additional inserts. Collisions,
changed snapshots, stale evidence and partial prior inserts stop without edits.
All out-of-scope canonical rows, market rows, aliases, news and controls remain
unchanged. No new database functions/roles/permissions or schema changes planned.

## Status

Source-bound extraction and insertion code complete. Ten extraction tests and
two new-photo tests pass. The isolated PostgreSQL test uses the real schema,
price constraint and price invalidation trigger: three complete profiles,
27 technical facts, late rollback, exact replay, collisions, concurrent changes,
image/source/price binding and preserved market history all pass. Existing
image-sync, licensed-image and press-permission tests also pass. Pre-insertion
production build passes with the unchanged76-version public catalog.

Prepared a fresh read-only production plan at17:39UTC on15November. Its SHA-256
is `3630ddfe296f0150dbcdf47bc27ac4b01883eb0f8fdafdc2aa7d7a5135d39c82`.
Application must re-fetch all official sources, compare exact facts/identities
and bind the actual fresh hashes before committing. No paid AI calls or new
permissions. Actual insertion, anonymous export and web release are separate
steps and must not be inferred from this prepared plan.

## Actual Canonical Commit And Local QA

The guarded fresh-source transaction committed three new variants on15November
at17:42UTC, batch `da32651352cf45a7059c568ea280a1b94d970146f9321c6019fd7cdd26087608`.
Its private committed receipt is under
`data/local/release-data/kia-ev2-pilot-2026-11-15/publication/`.
It registered three model-scoped sources and reused the unchanged shared Kia
price source. All76 pre-existing public records are unchanged. The October EV2
market row was attached/merged; March history and unconfirmed availability remain.
News rows/controls were read before/after and unchanged. No migration was needed.

Anonymous public export is31models/79variants, SHA-256
`ac509bbce4c4e86191e9218c52621aadb6fc300118df98999f081a8227198c95`.
All three added versions have nine technical fields and current separate price
evidence:331900/381000/459900SEK,317/453/413km. Each has362L,750kg,
10.5kW AC/150kW DC and five seats.55/79variants now have all nine core fields.
An anonymous access check confirms private vehicle tables still deny access.

Post-export release build and93-route static-content/SEO contracts pass. Local
Playwright checked all three versions at320/390/768/1440px (12views), two Axe
audits, exact-photo decoding, no mobile text/image overlap, the three-version
picker/comparison and deterministic advisor requirements. No real AI calls.
Physical-phone testing is not claimed. CI and actual website deployment remain
separate final checks.

The screenshot test now explicitly scrolls/decode-checks lazy-loaded related
photographs before the full-page capture. The extra check passed after waiting
for the real load event; it was an early decode timing issue, not a substituted
or broken model photograph. Existing EV9's16-view regression also passes.

First PR CI attempt43742996008 stopped before EV2 tests because the clean
Linux runner lacked openpyxl (present in the desktop runtime). Added pinned
openpyxl3.1.5 and et-xmlfile2.0.0 to the source-intake dependency file. No source
or data rules were changed; retain the failed run rather than claiming it passed.

## Verified Production Release

- PR74 merged as `2c602ea5e06511e7007da9e23732963f89ac223f`.
- Passing PR CI43743379788 and exact-main CI43743875208:181 successful steps
  each. Source-intake workbook dependencies are now installed on clean runners.
- Existing fixed-target production distributor43744379952 passed; no new hosting,
  keys, permissions, DNS, budget or news-production changes.
- Actual `https://elbilsagenten.se/` verification completed
  `2026-11-15T18:03:44.042Z`: HTTPS, public catalog79rows, approved catalog hash,
  exact original photo SHA-256 and all three pages' initial Vehicle metadata.
- Production Playwright also passed all12views, two Axe audits, decoded hero and
  related photos, separated mobile image/text, version picker and comparison.
  Advisor checks use actual canonical records with the deterministic engine;
  no paid provider calls or new article publication was made by this release.
- Private receipts, screenshots and actual-site reports are retained under
  `data/local/release-data/kia-ev2-pilot-2026-11-15/`.

First five-model pilot progress:1/5 released. Next: Toyota C-HR+, with separate
electric identity/alias safeguards (normalization strips the plus), exact Swedish
versions/prices, full technical evidence and reviewed model imagery. Recomputed
October ranks1-60 research scope has16 remaining matched candidates and14 raw
mapping holds; neither is an automatic publication approval.
