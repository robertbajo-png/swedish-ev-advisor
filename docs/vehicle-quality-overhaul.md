# Vehicle Quality Overhaul

Owner request: 2026-11-12. Improve the actual vehicle photography and technical
coverage, not just the colors. Preserve all 30 models and existing deep links.

## Phase Tracker

| Phase | Status | Deliverable / acceptance |
| --- | --- | --- |
| 1. Inventory | Complete | Repeatable per-model missing-field and image-quality report; source queues and baseline counts. |
| 2. Photography | In progress | Professional exact-model photos, source-specific rights evidence, visual review, local optimized assets and no unrelated fallback. |
| 3. Specifications | First batch committed | 16 Kia variants refreshed from five Swedish technical PDFs; 81 missing values filled. Remaining brands still queued. |
| 4. Presentation and release | First batch released | Model-first grid, exact-version picker and seven press photos verified on production. Remaining brand batches are still open. |

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
- Final follow-up passed all 150 PR CI steps and all 150 exact-main CI steps.
  PR #56 merged as `16a95aa2abc1e9c99d56edba28836d9c74b267ab`.
  Existing production distribution run `43327896861` succeeded. No new articles
  or paid calls were requested by distribution. Production GET checks passed for
  routes, canonical snapshot, sitemap, robots and advisor budget readiness.
- 2026-11-12 23:23 UTC: checked the actual production bytes of all seven new
  photos and 21 responsive files, plus the 76-row canonical export. Every hash
  matched the reviewed release; the two published news articles were unchanged.
  Receipts remain under ignored `data/local/release-data/vehicle-quality-2026-11-12/`.

## Remaining Batches

### Skoda Batch, 13 November

- Source discovery and collection: complete. Exact Swedish Elroq Explore Edition
  and Enyaq Solid Edition MY2027 pages, current edition price PDFs and official
  MY2027 technical release were fetched with hashes and per-field evidence.
- Owner-directed conflict resolution: choose current edition's version-specific
  FAQ over estimated price-list ranges, generic hero maxima and old DC equipment
  text. Enyaq RS changes from historical 185 kW to the current FAQ's 165 kW.
  Preserve the old canonical record in staging; do not reuse its automated review.
- Consumption: current PDF motor rows are retained as standard-equipment values,
  not personalized wheel/option measurements. Correct their erroneous l/100 km
  header against the manufacturer's explicit Wh/km declaration, divide by ten
  for kWh/100 km and label the qualification in details, comparisons and TCO.
- Canonical transaction: committed 11 versions, 98 previously missing values and
  one source-adjudicated DC update. Every version has all nine supported technical
  fields plus its independent price evidence. No prices or out-of-scope rows
  changed; no paid calls or news-control/article changes.
- A separately revalidated follow-up fills both canonical model body types from
  their exact Swedish manufacturer descriptions; model image/market metadata
  remain unchanged. Both model updates committed through the tested rollback
  transaction; all 11 public Skoda versions now also have a sourced SUV body type.
- Photography transaction: two exact-model manufacturer press photos committed,
  Elroq studio exterior and facelift Enyaq SUV (not Coupe). Keep full frames,
  source credits, permission records and hash-bound responsive derivatives.
- Public snapshot: 76 versions / 30 models retained. Core-card completeness is
  now 29/76 (18 before this batch). WLTP 51, DC 42, towing 39, boot 45, battery 41,
  AC 19, seating 23 and drivetrain 50. Nine model photos have professional review;
  the other 21 remain the next photography work, not falsely marked finished.
- Tests: source extraction, bounds, exact variant binding, unit conversion,
  seating context, preserved prices, rollback, replay prevention and the narrow
  historical DC resolution pass locally. UI/regression CI and deployment are in
  progress; do not describe this batch as released until public checks pass.

- 2026-11-13: Skoda research paused for the owner's mobile EV5 layout report.
  The detail photo is now an in-flow, full-frame image at widths up to 800px;
  copy, badges, actions and key figures follow below it on a solid background.
  Desktop cinematic presentation is unchanged. Added geometric regressions for
  EV5/EV6 at 320/375/390/430/768px, including source aspect ratio, no dark overlay
  and a minimum gap between the image and all copy. Build, visual review and
  deployment checks are required before calling this correction released.
- Mobile correction released through PR #57 as
  `b5beac6e1e197e4edc2adb6eed3b55eeba5838d6` after 150 exact-main CI steps passed.
  Production distribution `43376077766` succeeded. Actual public EV5 checks at
  320/375/390/430/768px confirmed a full-frame photo, no navigation/copy overlap,
  a 24px content gap and no horizontal overflow; 820/1440px retained the desktop
  cinematic layout. HTTPS/route checks, 90 static pages and 22 Axe audits passed.
  All 76 canonical variants are unchanged. No paid calls or database/news changes.

- This is the first delivered batch, not a claim that every field/model is done.
  Twenty-three model photos still need professional-photo review/replacement.
- After releasing Skoda Elroq/Enyaq, prioritize remaining Polestar/Toyota and other brands.
  The fresh Swedish Elroq price list labels its range values as estimated;
  the current Polestar 4 page labels its range as a target. Preserve those
  qualifications and seek final exact-version evidence instead of laundering
  these figures into certified WLTP fields.
- Reconcile the remaining 25 missing WLTP, 34 DC, 37 towing and 31 boot values;
  20 variants still lack a verified price. Keep each gap explicit until its
  exact-version source passes validation. No model has been removed to improve
  the coverage figures.
- Review an AC numeric-column compatibility migration separately, then publish
  source-exact decimal AC facts. Do not round or alter schema in an image batch.
