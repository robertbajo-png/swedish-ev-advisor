# Vehicle Quality Overhaul

Owner request: 2026-11-12. Improve the actual vehicle photography and technical
coverage, not just the colors. Preserve all 30 models and existing deep links.

## Phase Tracker

## Ford Explorer Batch (2026-11-13)

| Step | Status | Acceptance |
| --- | --- | --- |
| 1. Exact-version research | Complete | Current Swedish linked price list 8 / 2026, MY27.25 Premium Edition; exact RWD 79 / AWD 77 kWh and current campaign evidence. |
| 2. Facts and photography | Committed | Two nine-field profiles, twelve filled gaps, two dated campaign prices, SUV classification and reviewed European electric Explorer press photo. Canonical IDs retained. |
| 3. Regression and visual QA | Passed locally | Six extraction tests, real price-trigger/rollback/replay tests, previous adapters, 90 built routes, twelve six-width Ford checks, four dedicated and 22 general Axe audits pass. Mobile/desktop screenshots inspected. |
| 4. Publication | In progress | Package a reviewed PR, require exact-main CI, then use the existing production workflow and actual public HTTPS/data/photo checks. |

Keep the two canonical identities and old deep links when replacing obsolete
versions with documented current successors. Never combine a new model year's
price with the old powertrain's battery, range or charging. No paid AI, schema,
news, budget or infrastructure changes are part of this batch.

- The old model-page prose, obsolete PDF link and cached search snippets mix
  years/editions. The live public manufacturer JSON links price list 8, MY27.25,
  with only the two Premium Edition versions. Use RWD 79 kWh / 572 km / 15.5
  kWh/100 km and AWD 77 kWh / 519 km / 17.3. Do not borrow Nordic maxima 602/553.
- Current Swedish PDF charging is RWD 185 / AWD 175 kW DC, 11 kW AC; braked
  towing is 2000/2200 kg. Prefer those exact local MY27.25 figures over old
  135/185 kW, 1000/1200 kg or foreign charging tables. Retain all alternatives
  and selection reasons in staging; the obsolete profiles are replaced, not
  described as the very same historical batteries.
- Swedish Premium page confirms five seats and SUV identity. Boot volume
  472 L comes only from the named Explorer column in Ford Denmark's current
  European model table. Capri's 572 L and folded-seat 1460 L are rejected.
  Keep country DK/language da and a visible separate source link/qualification.
  Swiss/German PDF research was not imported because direct robots retrieval
  was unavailable; do not present search-cached PDF text as a fetched source.
- Cash Edition offers 549000/569000 remain campaign prices, not leasing
  payments or ordinary reference prices 626000/686000. Both use the common
  Premium Edition offer page's 30 December 2026 validity; RWD is explicitly
  included on that page and AWD also has an exact dated offer card. No date
  is borrowed from Capri or the monthly lease term. Source excerpts stay bound.
- Adopt only the visually reviewed Ford Sweden photograph
  `2023_FORD_NewElectricExplorer_1`, per-image media-use permission, full frame,
  credit and responsive derivatives. It is a European electric Explorer model
  press photo, not a claim of exact Swedish MY27.25 paint/wheels/equipment.
- Preserve canonical IDs and all 76 public profiles. Old `rwd-77-kwh` and
  `awd-79-kwh` URLs go to the Ford Explorer catalog using the existing retired
  link policy, not a silent redirect claiming the old drivetrain is unchanged.
- The first canonical transaction refused the DATE readback and rolled back
  before commit. Node-postgres represents DATE as local midnight by default;
  JSON UTC serialization can then move its calendar day. The refresh connection
  now configures the DATE-only (OID 1082) parser to retain calendar text, leaving
  timestamps and TLS untouched. A dedicated parser regression and the unchanged
  campaign-date constraint are mandatory. No missing date or evidence guard is
  relaxed to make this batch publish.
- Read-only real-driver diagnosis confirmed that the default parser returned
  `2026-12-29T23:00:00.000Z` for SQL DATE `2026-12-30`; the corrected per-connection
  parser returns the exact `2026-12-30` text. The subsequent canonical transaction
  committed both profiles, twelve missing technical values, two prices, four
  source records and one body classification. News records/controls were equal
  before and after. IDs and the unrelated quarantined Business Edition are kept.
- The local image preflight initially exceeded its 30-second subprocess limit,
  before connecting to the database. Running the unchanged full rights/bytes
  audit independently passed all 31 surfaces without errors. Allow a bounded
  120 seconds for that same mandatory audit; no permission check is skipped.
- The image transaction updated only the Explorer model. The approved public
  export still contains 76 versions across 30 models: only the two Ford rows
  differ from the prior snapshot, and all other 74 are equal. Core completeness
  is now 43/76 and professionally reviewed model photos 14/30; this is not a
  claim that the other brands are finished. Four photo files are hash-verified.
- Local Ford checks cover both versions at 320/375/390/430/768/1440px. All
  technical sections and price-qualified metrics are complete, each old URL
  reaches current model choices, and no horizontal overflow or runtime errors
  occur. Mobile photos remain full-frame above the copy with a 24px content
  gap. All four Ford and 22 general Axe audits have zero violations. Filtering,
  sorting, comparison, CSV, report-error handling and static/hydrated route
  checks pass. The isolated, concurrently loaded local performance observations
  are not production field measurements or a claimed performance improvement.

## Mercedes-Benz CLA Batch (2026-11-13)

| Step | Status | Acceptance |
| --- | --- | --- |
| 1. Exact-version research | Complete | Live Swedish C174 manufacturer technical dialog, 37 rows / three exact powertrains, and freshly checked MY2027 Advanced Edition order offers. |
| 2. Facts and photography | Committed | 27 missing technical values, one Sedan classification and exact electric-sedan press photo. Three unchanged cash offers remain dealer offers; corrected order-car names retain their indexed URLs and canonical IDs. |
| 3. Regression and visual QA | Passed locally | Six extraction tests, real-trigger transaction/rollback/replay, previous brand adapters, rights, 90 built routes, 18 six-width CLA checks, six dedicated and 22 general Axe audits pass. |
| 4. Publication | Complete | PR #63 merged; all 160 PR and exact-main CI steps passed. Production run 43511244723 succeeded; actual HTTPS, 76-record parity, four photo hashes, 18 detail checks and six CLA Axe audits passed. |

Preserve all 76 published identities and existing links. No paid AI, migrations,
news activity, budget or infrastructure changes are part of this vehicle batch.

- Normal direct fetching of Mercedes' robots file was refused by its bot filter.
  The connected ordinary Chrome browser returned both the actual robots rules
  (model route allowed) and current manufacturer page without a challenge or
  security bypass. The named public technical dialog was captured, then reloaded
  and all 37 rows compared before applying. Indexed search text and Finnish trim
  values were research only; neither was imported. A DOM capture's hash binds its
  normalized table, identity and robots evidence, NOT alleged original HTML bytes.
  Its unobserved HTTP status stays null with `reachable_official_browser_source`;
  previous direct-fetch adapters still require their actual HTTP 200 evidence.
- Exact columns: CLA 200 = 58 kWh, 528 km, 12.7 kWh/100 km, 200 kW DC;
  CLA 250+ = 85 kWh, 772 km, 12.6, 320 kW; CLA 350 4MATIC = 85 kWh,
  751 km, 13.1, 320 kW. All have 11 kW AC, 405 L rear boot and five seats.
  Drive is RWD/RWD/AWD. Use combined range, not city figures or generic hero
  maxima; AC equipment is not the optional charger/cable's 22 kW rating.
- Braked towing is the manufacturer's equipment-qualified maximum in parentheses:
  1500/1500/1800 kg. Preserve the raw 750 kg (maximum) entries and visible equipment
  warning. No fitted towbar, VIN-specific homologation or guaranteed real range
  is claimed. Manufacturer WLTP figures are the model-table reference configuration.
- Höglunds' exact three offer pages explicitly say the cars are order cars, not
  physically in stock. Correct canonical display names to `(beställningsbil)`;
  JS, sitemap and prerender preserve each existing `-lagerbil` URL for the same
  car, rather than redirecting to an assumed successor. Prices 559000/599000/639000
  remain dealer offers, not manufacturer list prices. Expired financing campaign
  prose is not imported as a current finance offer or a cash-price expiry.
- Real canonical transaction committed three versions / 27 missing facts and one
  model body type, with staged per-field evidence and independent price provenance.
  A separate image transaction updated only the same CLA model. No paid calls or
  news-control/article changes. 76 versions / 30 models retained; complete core
  profiles now 41/76 and professionally reviewed photos 13/30. Other brands remain
  open work, not claimed complete. Sources and receipts are local under
  `data/local/release-data/mercedes-cla-quality-2026-11-13/`.
- Local visual checks cover each version at 320/375/390/430/768/1440px. All
  photographs decode, all four new files match their hashes, technical sections
  and price-qualified metrics are complete, and no overflow or runtime errors
  occur. Mobile photos keep their full aspect ratio above the text; actual
  mobile/desktop screenshots were inspected. All 28 Axe audits have zero
  violations. General filtering, drawer/keyboard, sorting, comparison, CSV,
  report errors and explicit-zero-versus-null regressions also pass.
- The first UI run found a separate frontend ID conversion that broke corrected
  CLA URLs. Both hydrated IDs and generated paths now use the shared stable
  URL policy; the unchanged regression passes. A private Axe harness initially
  used the wrong browser-context API, then passed after correcting the harness.
  No product assertion was weakened. The complete 76-record comparison shows
  only the three CLA rows changed, with all three price amounts unchanged.
- The first remote CI run exposed the existing intermittent footer-focus overlap
  at 640px. Native focus scrolling could finish after the single animation-frame
  correction. The shared handler now rechecks for at most 250ms, stops on moved
  focus/disconnected overlay and keeps instant reduced-motion-safe scrolling.
  A deterministic delayed-scroll regression and the original geometric browser
  assertions remain mandatory; do not classify a rerun alone as a fix.
- Released through PR #63 as main
  `84e0093db24044a549e6d4bb424e5f7f63efb471`. Both final CI runs passed all
  160 steps, including the original footer-focus assertions after the bounded
  correction. Existing production distribution `43511244723` succeeded.
  At `2026-11-13T21:32:28.711Z`, actual public GET checks matched all 76 approved
  records and all four new image hashes. Three CLA pages passed six widths
  (18 checks) and six additional Axe audits without violations, overflow or
  runtime errors. Mobile/desktop screenshots were visually reviewed. HTTPS,
  indexability, sitemap, API health and budget-storage readiness also passed;
  no provider was contacted. The complete release receipt is attached to PR #63.
- CLA is complete within the current catalog fields: all three technical
  profiles, independent dealer cash offers, Sedan classification and exact-model
  press photograph are present. Preserve configuration/equipment qualifications.
  The wider catalog remains unfinished (41/76 core-complete, 13/30 professionally
  reviewed photos). Next recommended new-brand batch: Ford Explorer. No paid
  AI, new articles, news-control, budget, schema or infrastructure changes were
  made in this vehicle update.

## Mazda 6e / Renault 5 Batch (2026-11-13)

| Step | Status | Acceptance |
| --- | --- | --- |
| 1. Exact-version research | Complete | Current Swedish 78 kWh MY2027 Mazda PDF and Renault November 10 / October-production PDF, exact battery/grade columns. |
| 2. Facts and photography | Committed | 54 formerly missing technical facts, six unchanged independently reverified list prices, two body classifications and two exact-model press photos. All 76 versions retained; news unchanged. |
| 3. Regression and visual QA | Passed locally | Extraction, real-trigger transactional rollback/replay, previous brand adapters, prices, rights, build/90 routes and 36 six-width detail checks pass. Filter/compare/CSV/null handling pass. |
| 4. Publication | Complete | PR #62 merged; all 157 PR and exact-main CI steps passed. Production run 43500699789 succeeded; actual public HTTPS, 76-record parity, eight photo hashes and 36 detail-page checks passed. |

Mazda's MY2027 battery is not the previous 68.8/80 kWh powertrain. Do not
borrow the previous year's range, consumption or charging performance. Renault
40/52 kWh values must stay bound to their exact grade/battery column. This batch
does not authorize paid AI, news changes, migrations or infrastructure changes.

- Swedish MY2027 Mazda PDF: 78 kWh, 560 km combined WLTP, 16.1 kWh/100 km,
  200 kW DC, 11 kW three-phase AC, 1500 kg tow and 336 L rear boot below shelf.
  Do not substitute city-cycle consumption, the calculator's stale 16.6 figure,
  inconsistent 7.2 kW equipment caption, 466 L roof-height volume or 72 L frunk.
- Mazda seating is explicitly five across all three grades in the manufacturer's
  European MY2027/78 kWh sheet. Only seating comes from that German source.
  The adapter follows its exact observed robots.txt -> robots.txt/ redirect;
  404 keeps existing no-file semantics, while denial, foreign redirects or 5xx stop.
- Renault exact grade ranges: evolution 40=320, techno 52=424, iconic five 52=421.
  The common 52 kWh consumption interval stays 14.1-14.2, visibly qualified;
  cost calculations use the lower endpoint, not an invented exact grade figure.
- Renault's manufacturer E-Tech-generation technical dialog supplies only
  front-drive architecture and five-door Berline -> Halvkombi classification.
  Its older foreign prices/ranges are never imported. European supporting sources
  retain their actual DE/de locale instead of being mislabelled Swedish.
- Press photos: Mazda MY2027 exterior 3540810 and Renault 5 exterior 3172684.
  Interior/detail shots and the time-limited Mazda people shot were rejected as
  primary model photos during visual selection. Retain full photographic frames.
- Canonical commit filled all nine technical fields on all six versions. The
  legacy source spelling 6e is retained and bound to the exact same canonical
  parent 6E, not accepted through broad case-insensitive matching. The initial
  source-identity refusal rolled back completely; an explicit regression now
  reproduces that historical source row. Two body types and two images committed
  separately through existing transactions. Prices changed: zero; paid calls: zero.
- Coverage after this batch: 38/76 complete core profiles and 12/30 professionally
  reviewed model photos. This is not a claim that the other brands are complete.
- Local rendered checks cover every new version at 320/375/390/430/768/1440px,
  exact photograph files and full-frame aspect ratio, >=16px photo/copy gap,
  no navigation overlap, no horizontal overflow, complete technical sections and
  value metrics. Group consumption qualification is now visible beside its
  specification, not just in a calculator tooltip. No client runtime errors.
- Released as main `441ae8d2f5847d7d15d2aeedacc8e3ad06bbe6e9` through the
  existing production distribution workflow, run `43500699789`. Public checks
  completed at `2026-11-13T20:23:24.545Z`: all 76 records equal the approved
  snapshot, all eight new image files match their recorded hashes, and all six
  Mazda/Renault pages pass at 320/375/390/430/768/1440px. Ordinary HTTPS, routes,
  sitemap and readiness checks pass; no provider calls were made. Actual public
  mobile and desktop screenshots were visually reviewed. Sources, full frames,
  photo credits and Renault's consumption qualification remain visible.
- PR #62 contains the verified release receipt. Private source captures,
  transactional receipts, screenshots and `production-verification.json` remain
  under `data/local/release-data/mazda-renault-quality-2026-11-13/`. This batch
  is complete without paid AI, article publication or infrastructure changes.
  Next recommended batch: Mercedes-Benz CLA's remaining exact-version facts and
  professional photography. The wider catalog is not yet complete.

## Overall Tracker

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

### Toyota And Polestar Batch, 13 November

1. Source collection and version matching: complete. Scope is all six current
   public versions across Toyota bZ4X, Polestar 2 and Polestar 4 coupe. Refresh
   Swedish model/specification pages, exact configurator/manual data and current
   price evidence. Resolve conflicts by exact version/model year; preserve source
   intervals, wheel/equipment conditions and any preliminary status.
2. Completeness and media: complete. Fill all nine technical fields, independent
   price classification/evidence and body type. Replace the pre-facelift bZ4X
   photo with an exact current-model manufacturer press image; revalidate the
   existing Polestar press images rather than replacing suitable media needlessly.
3. Guarded publication: complete. Stage exact-source facts, run extraction and SQL
   rollback/scope regressions, then apply only the six variants/three models,
   preserving every other vehicle and all news/AI/budget controls.
4. Release: complete. Export canonical public views, build, visual/accessibility
   and no-JS regression checks, exact-main CI, existing production deployment and
   actual public GET/image/mobile verification. No paid AI calls are needed.

- Committed six exact-version profiles: 27 new technical values, three model body
  classifications and fresh independent price evidence. All six amounts are
  unchanged. The public catalog remains 76 versions / 30 models; other canonical
  versions, news articles and news controls were verified unchanged.
- Toyota uses the initialized Swedish Active FWD 57.7 kWh / 167 hp configuration,
  not the generic AWD maximum. Standard AC 11/DC 150 kW comes from its selected
  standard-equipment list; braked tow 750 kg, five seats and rear boot 452 litres
  retain exact configuration/model evidence. The current manufacturer's cash
  price matches its VAT-exclusive base price and has no cash promotions; finance
  interest offers are not vehicle discounts.
- Polestar 2 uses all three exact columns, common 82 kWh/205 DC/11 AC/407-litre
  rear boot and the Swedish seating manual. Its body is sourced as Fastback.
  Polestar 4 is the coupe, not the newly introduced SUV body: rear boot 526
  litres from the current Swedish page, not old 500-litre or folded-seat figures;
  standard AC 11 kW is separate from the 22 kW option. Towing remains variant-
  specific, 1500/2000 kg. Rear motor's certified 620 km comes from the current
  coupe manual for 20-inch wheels. Dual motor's 590 km is explicitly a
  manufacturer WLTP target, labelled as such in UI/structured metadata, not
  allowed to prove an advisor's certified minimum-range requirement or win a
  direct measured-range comparison. Consumption intervals remain visible;
  the TCO explicitly labels its lower-bound assumption.
- The first two technical transactions rolled back at the price evidence
  readback: migration 020's trigger correctly cleared incomplete reclassification
  evidence. The updater now supplies its source-bound price refresh batch ID,
  without changing or disabling the trigger. Regression tests install the REAL
  trigger from migration 020 and verify price evidence, late-failure rollback,
  unchanged out-of-scope rows and replay rejection. No partial technical writes.
- Toyota now has a visually reviewed, current European FWD manufacturer press
  photo, full-frame 2560x1708, with the Toyota UK gallery's explicit editorial
  permission and source credit. Swedish pressroom terms were not assumed to
  grant republication where their general clauses were contradictory. Polestar
  photos 4690/6083 were fetched again: identical bytes, exact MY26 Polestar 2 and
  Polestar 4 coupe identities; retained rather than needlessly replaced.
- Local checks pass: new five extraction/media tests, six-version SQL regression,
  unchanged Kia/Skoda SQL and extraction tests, price/advisor contracts, 90 static
  and rendered routes, eight no-JS/hydrated checks, 22 Axe audits with zero
  violations and all-version vehicle UI interactions. Actual built six-version
  pages pass 36 checks at 320/375/390/430/768/1440px, no mobile photo/text/navigation
  overlap or horizontal overflow, no technical gaps. All twelve batch photo
  files match their recorded hashes. A lazy-image decode race in the UI test now
  waits for the real image load before decoding; failed assets still fail.
- Coverage after this batch: range 53, DC 45, tow 41, boot 48, battery 43, AC 22,
  seats 28, drivetrain 52 and body 17 of 76. These include the explicitly labelled
  Polestar range target; do not describe that target as certified. Prices remain
  56/76, complete core-card profiles 32/76, professionally reviewed model photos
  10/30. Other brands remain active research, not silently claimed complete.
- PR #60 merged as `64111f01e893e1bf5bd57f7864446d57fe29862d` after all
  155 PR and exact-main CI steps passed. Production run `43488409146` failed
  before uploading: its isolated function package omitted the new shared
  `spec-qualifications.js` module. No replacement site was deployed by that run.
  PR #61 adds the exact missing dependency, a shared explicit package inventory,
  actual isolated-package compilation in CI (including a negative omitted-module
  regression) and pre-credential compilation of the real deployment package.
  No extra data writes or AI/article activity are needed to retry distribution.
- Final release: PR #61 merged as `a27e5aafb52ae368e1f4c16ca4cea4b23e2b14e6`.
  All 155 PR checks and all 155 exact-main checks passed, including isolated
  production-package compilation and intentional missing-module rejection.
  Production distribution `43490914376` succeeded. At 19:21 UTC on 13 November,
  actual `https://elbilsagenten.se/` passed ordinary TLS/GET/readiness checks.
  All 76 deployed records match the approved snapshot, all twelve batch image
  files match their hashes, and all six Toyota/Polestar pages pass the full
  320/375/390/430/768/1440px matrix: no technical gaps, wrong-model replacements,
  mobile image/copy/navigation overlap, horizontal overflow or runtime errors.
  Production screenshots were visually reviewed; source frames and credits are
  preserved. The target qualifier also survives the real table/CSV workflow.
- Verified release receipts are attached to GitHub PRs #60 and #61. Private
  source captures, before-images, SQL receipts and 36 public-page geometry checks
  remain under `data/local/release-data/toyota-polestar-quality-2026-11-13/`.
  No paid AI calls, additional article generation/publication, news-switch,
  budget, DNS, email, key or permission changes were made for this batch.
- Next recommended data batch: Mazda 6e and Renault 5, each currently carrying
  twelve missing core values across three public versions. Reuse exact Swedish
  manufacturer technical sources and professional model photography. Keep the
  separate Kia decimal-AC compatibility work and other remaining brands visible;
  this completion applies to Toyota bZ4X and Polestar 2/4, not the whole catalog.

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
  historical DC resolution pass locally. All 152 PR and 152 exact-main CI steps
  passed, alongside 90 static routes and 22 Axe audits with no violations.
- Released via PR #58, main `df10f543068443253ca59d59e3a390675ce584ff`.
  Production distribution `43421403212` succeeded. At 2026-11-13 12:02 UTC,
  public GET/TLS checks matched all 76 approved records and all eight new photo
  files byte-for-byte. Real public Skoda pages passed at 320/375/390/430/768/1440px:
  no mobile image/copy/navigation overlap, full frame, 24px copy gap, no horizontal
  overflow and no missing values in their technical sections. Desktop cinematic
  layout remains intact. Detailed receipts/screenshots are kept under ignored
  `data/local/release-data/skoda-quality-2026-11-13/`.
- Skoda batch is complete. The whole catalog is not: retain the remaining gaps
  as active source research and continue next with Toyota/Polestar. Do not hide
  models, invent values or treat an unverified photo as professionally reviewed.
- Final visual follow-up: remove avoidable empty decision metrics where a valid
  campaign/dealer price and WLTP already exist. Label the actual price type and
  expiry, never as list price or running cost; unknown/expired inputs remain
  rejected. Pure regression tests, the all-version UI suite, build and 90 static
  routes pass. PR #59 merged as `e5692867d8ffcd66625089fbbc3ae985b65a58c7`.
  All 153 exact-main CI steps passed after one complete rerun of an intermittent
  pre-existing 320px footer-focus check; retain that failure for follow-up rather
  than weakening its assertion. Production run `43425469841` passed on attempt 2:
  initial immediate post-upload verification saw the previous HTML, then the
  unchanged verifier and full guarded workflow passed once the new HTML was live.
  Public 12:32 UTC checks confirmed all eight image hashes, all 76 records,
  complete Skoda technical sections and non-empty explicitly labelled campaign
  price metrics across the same mobile/desktop matrix. No additional DB writes,
  paid calls, article publication or news/budget/DNS changes in this follow-up.

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
