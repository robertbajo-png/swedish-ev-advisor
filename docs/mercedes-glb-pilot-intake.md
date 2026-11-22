# Mercedes-Benz GLB Electric X244: Private Intake

Status on 21 November 2026: two complete Swedish MY27 source profiles,
one reviewed exact-generation press photo, and a successful isolated
insertion and rollback test. No production writes, public asset changes,
deployment or paid calls. The model is not released.

## Exact Swedish Scope

Both rows describe five-seat Advanced Edition models. The [Swedish model
page][model] provides the available specification tables and factory IDs;
the [Swedish price page][price] labels both starting prices separately.
Its amounts also match the model page's structured offers. Two exact
Swedish authorized dealer listings corroborate MY27 and the trim. They
are not the source of displayed prices or evidence of general availability.

| Verified field | 250+ Advanced Edition | 350 4MATIC Advanced Edition |
| --- | ---: | ---: |
| Factory configuration | `2446131_SE3` | `2446441_SE3` |
| Manufacturer starting price | 619,000 SEK | 659,000 SEK |
| Combined WLTP range | 631 km | 614 km |
| Combined WLTP consumption | 15.8 kWh/100 km | 15.9 kWh/100 km |
| Usable battery | 85 kWh | 85 kWh |
| Max DC charging | 320 kW | 320 kW |
| Standard AC charging | 11 kW | 11 kW |
| Rear luggage, five seats | 540 L | 540 L |
| Max braked towing, suitably equipped | 1,500 kg | 2,000 kg |
| Seats | 5 | 5 |
| Drivetrain | RWD | AWD |

Retain the combined WLTP/base-configuration qualifier. Do not include
the frunk in rear capacity, infer a fitted towbar, report optional AC as
standard, or substitute seven-seat figures. `manufacturer_from` is not an
exact transaction price or proof of meeting a hard budget. The included
charging voucher is not a pricing input. Hybrid X248, Anniversary Edition,
seven-seat configurations and other variants are out of scope.

## Market And Canonical Readback

The [October Mobility Sweden release][market] was verified against the
archived original workbook; exact row `MERCEDES | GLB | EL` has 187
October and 1,488 YTD registrations (priority rank 18). This is model-level
market evidence, not evidence of a trim, price or current availability.
The workbook SHA-256 is
`1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6`.
A read-only, repeatable-read Supabase snapshot independently confirmed
an existing `Mercedes-Benz | Glb` draft, its exact unambiguous alias, an
unlinked March 2026 electric market row and zero public GLB variants.
The October workbook was not imported in this step. The writer must
bind only the electric row and preserve other rows and historical months.

## Photo And Reproducibility

Mercedes-Benz Sverige's [electric GLB launch][launch] links the [reviewed
press photo][photo]. The original JPEG is 5,000 by 3,333 px. Visual review
confirmed the whole exterior of the electric X244; it represents the
model, not the exact equipment of either version. The per-image media
terms require the full, unaltered image. The asset policy therefore pins
the download and original SHA-256 and requires the embedded Mercedes-Benz
AG credit. Do not crop, retouch or re-encode the enrolled original. A
photo registration dry run passed without adding it to active mappings.

```powershell
node scripts/mercedes_glb_review.mjs --capture
node scripts/mercedes_glb_review.mjs --replay data/local/release-data/mercedes-glb-x244-review-0eO9Ju
node --test tests/mercedes-glb-review.test.mjs
```

The dated private capture carries HTTP receipts, hashes and field evidence.
The pinned candidate is in
`data/local/release-data/mercedes-glb-press-2026-11-21-pinned`.
Offline replay, source and photo-policy tests, the photo dry run and the
production build passed.

## Isolated Publication Rehearsal

The `mercedes_glb_electric_x244_sweden_my27` adapter is local-only.
The write function rejects a non-PGlite client before making any query.
A fresh capture included the workbook, linked publication and underlying
manufacturer and dealer receipts. The runner compared remote GitHub main
(`55f6e9d`), the live HTTPS export and the Postgres public view. They
matched at 84 variants. In the isolated copy, both approved-scope rows
appeared in the anonymous views before commit; all 84 previous rows
remained identical. One pre-existing historical month and an unlinked
synthetic non-electric row were preserved. Simulated hybrid linkage,
seven seats, ordinary-list-price substitution, changed image attribution
and stale sources were rejected. A forced failure after insertion rolled
back the model photo, both variant/staging rows, source writes and market
changes. Exact replay inserted nothing.

Migration 026 was exercised twice locally without changing existing rows.
Incomplete starting-price evidence failed the SQL constraints. Read-only
production inspection found neither starting-price evidence constraint:
migration 026 still requires separate approval and verification before a
release can store the selected `manufacturer_from` prices.

```powershell
node scripts/mercedes_glb_review.mjs --capture --include-market
node scripts/verify_mercedes_glb_local.mjs --review data/local/release-data/mercedes-glb-x244-review-NTs9Sh
node scripts/run_python.mjs scripts/mercedes_glb_press_web.py --replay data/local/release-data/mercedes-glb-press-web-5g_e2mia
```

The pressroom advertises two unchanged smaller web versions of its own
image. Both passed full-frame comparison against the pinned original:
746 x 497 (66,568 bytes) and 1782 x 1188 (338,174 bytes). Their URLs and
checksums are pinned to the GLB publisher entry. No generated crops,
stock images or production media changes.

## Browser Review And Release Gates

Both variant pages passed at 390 and 1440 px in a private production
build: exact title and variant, four hero metrics, correctly attributed
full-frame image, no mobile overlap or page overflow, and no old route
changes. The production renderer selected the 746 px image on mobile
and 1782 px on desktop. The comparison route and local comparison report
worked with both variants; there was no best-price marker or product
offer markup for starting prices. External requests and paid AI were
blocked in the browser test. Screenshots and the replayable report are
in `data/local/release-data/mercedes-glb-local-c6BMOA/ui-fcgAMf`.

```powershell
node scripts/verify_mercedes_glb_ui.mjs --readback data/local/release-data/mercedes-glb-local-c6BMOA --press-web data/local/release-data/mercedes-glb-press-web-5g_e2mia
```

The model is ready for private review, not a live write. The next gate
is hosted code CI, followed by a separate media decision, approval and
verification of migration 026, and a refreshed source and catalog check.
Require separate explicit publication approval and a guarded release
entry point; do not remove the local-only restriction from the generic
writer. The earlier Toyota and ID. Buzz releases were not touched.

## Scoped Main Package

`data/local/release-data/mercedes-glb-ci-1CTUdc/mercedes-glb-code.patch`
applies to exact GitHub main `55f6e9d30965ec5c82ed88e02e914777e4c052d6`.
The checked replay produced tree `6b3f7310088029979d507fca9026dbe5c721f6db`.
The patch is limited to the GLB collector, local-only writer support,
image policy, buyer qualifications, tested shared starting-price
support and migration 026. The original workspace index, all public
files, the news export and SEO data were untouched; there are no keys,
captured source files or public media files in the code patch.
The private `media/manifest.json` beside it binds the three exact
publisher files without staging them in Git.

From the packaged tree, a fresh source capture and a read-only
production snapshot reproduced the 84-to-86 rehearsal, including
anonymous readback, preserved existing rows, late rollback and no-op
replay. The GLB and starting-price unit tests, Kia EV2 and ID. Buzz
transaction regressions (including Toyota preservation), decision
metrics, image rights, production build and 98 existing static pages
passed locally. The private build with GLB passed both sizes again,
comparison and 100 static pages: both new canonical URLs distinguish
starting prices from Schema.org offers. The package-level `review.json`
binds the database, browser and media receipts. The read-only SQL check
found zero live migration-026 evidence constraints.

## Composed UI Review

The archived main still displayed the old availability badge, and the
separate inventory-copy patch missed three visible uses of "lagerbil" in
the BMW i4 technical notes and source label. The composed copy applies
that patch and replaces the leftover wording with neutral references to
the exact BMW example. The scope and meaning of its technical data,
source links, dealer price and legacy route are preserved.

`data/local/release-data/glb-composed-Wu2QSV/mercedes-glb-and-inventory-code.patch`
replays on the same exact main, producing tree
`88e2a4b3a0f59ca15be50a3fec2e635dc8a80fdd`. It is a code-only
alternative to the original GLB patch, not a separate data release.
The five-file `inventory-copy-verified.patch` is also available as the
delta from the original tested GLB tree. All existing public data, media
and news files remain byte-identical.

The composed production build passed both GLB detail pages at 320,
390 and 1440 px, including exact press-image sizes, no mobile overlap,
working technical and price source links, and no old status labels in
the open source panels. Comparison and the local comparison report
passed; the comparison fits the mobile viewport. The original BMW URL
was opened successfully, and all 84 prior variant URLs were preserved.
The 100-page static build produced 86 canonical vehicle pages, two new
GLB URLs with no false offers, and 40 redirects. Titles, descriptions
and vehicle schema names no longer use the retired inventory labels.
The private `review.json` binds the code patch and browser/static
results to the same isolated 86-row catalog.

## Guarded Release Command

`scripts/publish_approved_mercedes_glb.mjs` binds the isolated two-row
delta, exact UI, media and code to a private release scope. Preparation
does not open the database. With no write flag the command checks the
requested current main, exact live entry-bundle hash and three reviewed
photos, the anonymous public baseline, installed migration 026 and a new
replayed manufacturer/market capture. The expected reader hash must come
from the reviewed build, not be inferred from whichever bundle is live.

Only a separate exact approval can use `--commit-approved`. Require a
clean checkout and an unused private journal path. Recheck the anonymous
baseline and deployment, then check migration, alias, history and public
values again inside the locked transaction. The generic writer remains
local-only for this model. After a confirmed commit, `--export-approved`
uses the same approval and journal so the new variant IDs, price
provenance and untouched prior records can be checked. Export writes a
private catalog only; the command cannot deploy. A missing commit receipt
is not permission to try the write again.

The local command rehearsal used the production-shaped 84-row fixture
and PGlite for the actual writes. It rejected wrong approval, missing
migration, stale/changed sources, catalog drift and wrong exported IDs.
A forced late failure rolled everything back; only a confirmed receipt
could export. Hosted prerequisites were simulated in that positive
test. The real read-only CLI stopped at exact main, before connecting to
the database, because that revision lacks the required release code.
The clean candidate passed 11 unit tests, the existing ID. Buzz/Toyota
regression and its production build.

Hosted CI, separate media/support-code rollout, migration 026
approval/readback and exact publication approval remain. No branch,
PR, production write, API cost or deployment was created.

## Integrated Ford-Baseline Review

The scoped GLB reader and press assets now build on the verified Ford
manufacturer-from-price support without a second price contract. The
source, size/rights, exact five-seat display, anonymous ID and staged-media
tests passed, as did the production build and all 114 pages in the
unchanged 100-variant fixture. No GLB rows were put in a public export.
The fixture now retains the live Ioniq photo overrides and any published
manufacturer starting prices. A fresh post-Ford baseline and exact-main
transaction/browser rehearsal are required before release.

[model]: https://www.mercedes-benz.se/passengercars/models/suv/glb-electric/overview.html
[price]: https://www.mercedes-benz.se/passengercars/campaigns/laddning-ingaar.html
[market]: https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober
[launch]: https://www.mynewsdesk.com/se/mercedes-benz-sverige/pressreleases/nya-eldrivna-mercedes-benz-glb-visad-plats-foer-sju-och-faar-dra-upp-till-2000-kg-3420354
[photo]: https://www.mynewsdesk.com/se/mercedes-benz-sverige/images/nya-mercedes-benz-glb-2026-3376630
