# Vehicle Quality Overhaul

Owner request: 2026-11-12. Improve the actual vehicle photography and technical
coverage, not just the colors. Preserve all 30 models and existing deep links.

## Phase Tracker

| Phase | Status | Deliverable / acceptance |
| --- | --- | --- |
| 1. Inventory | Complete | Repeatable per-model missing-field and image-quality report; source queues and baseline counts. |
| 2. Photography | In progress | Professional exact-model photos, source-specific rights evidence, visual review, local optimized assets and no unrelated fallback. |
| 3. Specifications | First batch committed | 16 Kia variants refreshed from five Swedish technical PDFs; 81 missing values filled. Remaining brands still queued. |
| 4. Presentation and release | Testing | Model-first grid and exact-version picker, discreet accessible credits, consistent photo framing; deployment follows QA. |

## Baseline

The public canonical snapshot has 76 variants, 30 models and 15 brands.
Presence counts, not assertions of fresh verification:

| Field | Present / 76 |
| --- | --- |
| Price | 56 |
| WLTP range | 27 |
| Battery | 17 |
| Peak DC charging | 16 |
| AC charging | 8 |
| Towing | 15 |
| Boot volume | 20 |
| Seats | 12 |
| Drivetrain | 29 |
| Body type | 0 |

All 30 model photos have documented exact-model Creative Commons evidence, but
rights and identity do not establish photographic quality. The first listing
cards use a rear-view parking-lot Polestar photo, repeat the same model, and put
several credit lines between the photo and its identity. Many newer exact-price
profiles intentionally have null technical facts: replacing them with marketing
maxima from a different version would repeat the old data-quality problem.

## Execution Rules

- Inspect relevant files and sources before each batch; record what is still missing.
- Prefer official pressroom photography with explicit applicable usage terms.
  Public availability alone is not permission. Where unavailable, use a genuinely
  strong licensed photograph of the exact generation/body style, never a similar
  vehicle, generated photograph or unlicensed configurator image.
- Save image identity, source URL, permission evidence, credit, content hash,
  review date, framing and any expiry. Review the actual image before promotion.
- Collect current Swedish manufacturer specification tables, technical PDFs and
  configurator output. Verified authorized dealers remain secondary evidence.
- Bind every technical value to its exact variant and source excerpt/hash. Keep
  gross/net battery, WLTP cycle, braked towing, peak/average charging and optional
  equipment separate. A model-wide maximum is not a variant specification.
- Extend existing deterministic adapters and canonical transaction utilities;
  stage and validate first. Do not update public JSON independently of Postgres.
- Do not clear existing verified values or invent missing ones. Conflicts and
  unresolved version identities remain explicitly held for verification.
- Use no paid news calls for this work. News scheduling, publishing safeguards,
  ordinary spending caps, DNS and email are outside this overhaul.
- Test each useful slice. Record measured coverage, changed files, remaining
  gaps and the next task. Do not call the whole overhaul complete after one brand.

## Batch Order

1. Highest-visibility photography and reusable image evidence/presentation.
2. Kia / Skoda technical gaps (largest number of price-only variants).
3. Polestar / Toyota / remaining manufacturer groups with reusable official tables.
4. Full per-model sweep, image and field provenance checks, public-view parity,
   responsive/accessibility checks, build and preview/release verification.

## Work Log

- 2026-11-12: inspected production listing, canonical snapshot, image manifests,
  exact-model rights pipeline and existing variant-refresh transactions. No
  canonical data, image files, budget controls or news switches changed yet.
- Inventory script and three regression tests added. Only three of 76 variants
  currently have all five core card values. Rights evidence is not silently
  treated as photographic-quality approval.
- Swedish Kia PDF paths were incorrectly outside the source audit's Swedish
  path boundary. Added only the exact `/content/dam/kwcms/kme/se/sv/` prefix;
  other countries, language paths and other brands still fail. Nine source tests
  pass. Fresh EV3/EV4 PDFs collected with hashes and structured page/word data.
- Owner requested proceeding with press images. Keep their documented editorial
  restrictions and credit; do not relabel them as Creative Commons or use them
  as advertising/brand endorsements.
- Canonical Kia batch committed transactionally: 16 exact variants, five sources,
  81 new technical values, no price/availability/model changes and no paid calls.
  A follow-up preserved explicit source evidence for the two existing EV9 seating
  values. Staging and per-field excerpts retain PDF page/column/wheel context.
- Current coverage: WLTP 40/76 (was 27), DC 32/76 (16), towing 28/76 (15),
  boot 34/76 (20), battery 30/76 (17), drivetrain 39/76 (29).
  Core-card completeness is 18/76, previously 3/76. Prices remain 56/76.
- Do not round Kia's 10.5 kW AC value into the current integer column. It remains
  held pending a separately tested numeric-column compatibility migration.
  Preliminary EV3 AWD, GT/GT Line mismatches and undocumented six-seat boot
  volumes also remain held, not borrowed from another version.
- Reviewed seven manufacturer press photos: Polestar 2/4 and Kia EV3/4/5/6/9.
  Full-frame Kia media assets retain their whole photographic frame, hash-bound
  derivatives, individual evidence and compact source credit. Rejected interior
  photos are not promoted as model-card exterior photography.
- Catalog grid now groups by exact brand/model and offers matching variants in a
  labelled select; all versions remain separate in the table and comparison.
  JSON-LD uses the displayed selected variant, not a hidden or unfiltered version.
- Offline checks passed: 27 focused Python tests, isolated Postgres transaction
  regressions, advisor/public-image contracts, 90 rendered routes, desktop/tablet/
  390px/320px vehicle and advisor flows, plus 22 Axe audits with zero violations.
  The first PR CI exposed an obsolete redirect assertion requiring Kia EV3's
  technical values to remain null; it now checks the current canonical values.
  Separate explicit-zero/null transport fixtures remain enforced.
- Native version selects remain disabled in no-JavaScript HTML until hydration:
  a reader cannot change the version name while keeping another version's data.
- PR #56 passed all 150 CI steps after the redirect assertion was updated. Final
  EV6 photography/no-JS reading follow-up is tested again before release.
