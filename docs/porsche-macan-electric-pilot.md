# Porsche Macan Electric: Swedish MY27 intake

Status: tech and price source review passed; not released. This packet is
for the Swedish rear-wheel-drive Macan, code `XABAA1`, on its standard
20-inch wheels. The [configurator][base] base and unmodified total prices
agree with the [Swedish comparison][compare] manufacturer's starting price
of SEK 970,000. Do not label it a fixed offer or use Advanced Sport's options.

The [exact technical panel][technical] confirms 642 km combined WLTP and
16.7 kWh/100 km for this configuration, a 100 kWh gross battery, 270 kW DC,
518 L of rear cargo and 2,000 kg braked towing with equipment. The
[standard equipment][equipment] confirms rear-wheel drive, two front
seats and three rear seats, and the 11 kW on-board charger. The 22 kW
charger and retractable tow bar are separate, paid options.

From the repository root:

```sh
node scripts/run_python.mjs scripts/porsche_macan_review.py --capture
node scripts/run_python.mjs scripts/porsche_macan_review.py --replay <private-folder>
node scripts/run_python.mjs -m unittest discover -s tests -p test_porsche_macan_review.py -v
```

Capture makes only bounded GETs to the four exact sources, using the existing
access and machine-reservation checks. It retains original HTML, timestamps,
hashes, scoped evidence and qualifications under ignored `data/local/`.
Replay recomputes the facts and checks all original byte hashes. Neither
invocation registers a source, publishes a variant or calls a paid API.

The production read-only identity check found one unresolved publication
draft, a resolved Macan alias, one unlinked March BEV market row and no
variant. Reuse those identities, preserve March, and bind the exact
October BEV row (43 registrations; rank 59). There is no new model row
to insert in parallel with the existing Macan draft.

The October [Mobility Sweden report][market] now has its own capture and
replay check. It requires the workbook linked by the publisher and the
exact BEV row (43 October, 367 YTD). October data is not a source for any
price, technical or availability value.

```sh
node scripts/run_python.mjs scripts/porsche_macan_market.py --capture
node scripts/porsche_macan_scope.mjs --market <private-folder> --rehearse
```

When running in an isolated checkout, pass `--client-module` pointing to
the existing project's read-only source connector. The scope command
checks the exact draft, alias and preserved national registration history.
The optional PGlite check reproduces that scope and the existing
105-variant public baseline. This is a read-only scope rehearsal, not
the insertion transaction or permission to publish.

The [Porsche press kit][press] links the separate base Macan gallery,
not the Macan 4S gallery. The gallery identifies press asset 297892,
credit Porsche AG. The uncropped 6000 x 4000 JPEG was independently
opened and verified. It is a 2024 model photo, not MY27 equipment proof.
The published [usage terms][terms] permit credited editorial reporting
and exclude advertising and other business use. They do not establish
permission to deploy this asset across the catalog, comparison and
recommendation surfaces. Keep it private unless the intended use is
covered; don't substitute a combustion Macan, 4S or Turbo.

The February 2025 [front][commons-front] and [rear][commons-rear]
photographs by M 93 are a separate CC BY-SA 3.0 DE source. Both originals
were subsequently fetched and visually verified as the electric XAB
generation. They do not establish the photographed drivetrain. The
front file is approved as a model-level image with that limitation
shown in the caption. The staged original and 480/800/1280 px derivatives
are hash-bound; do not distribute the Porsche pressroom copy through
the catalog. No variant is added by this media change.

```sh
node scripts/run_python.mjs scripts/porsche_macan_release_intake.py --capture-photo
node scripts/run_python.mjs scripts/porsche_macan_release_intake.py --specs <spec-packet> --market <market-packet>
```

The combined intake replays the original source packets and attaches
the exact quote, source URL, hash and fetch date to each of the nine
technical fields and the Swedish starting price. It reports freshness
without refreshing saved timestamps. It cannot publish or set image
rights.

### Atomic rehearsal on the canonical baseline

```sh
node scripts/verify_porsche_macan_local.mjs --specs <fresh-spec-packet> --market <fresh-market-packet> --photo <reviewed-licensed-photo-packet>
```

An isolated checkout can use `--client-module` with the existing project's
read-only source connector. The command reads the actual canonical draft,
resolved alias, existing Macan sources and history in a repeatable-read,
read-only transaction, and closes that connection before any trial writes.
The exact Macan adapter then exercises the shared model insertion transaction
in a new in-memory PGlite database. It rejects the production connector and
requires the exact licensed model photo; the older pressroom proof is not
eligible for this rehearsal. The candidate catalog is saved only under
`data/local/release-data` for browser and static route checks.

On 23 November the fresh source replay and private rehearsal added one
Macan to a 105-variant baseline. All nine fields and the starting price
were visible through the anonymous **local** view before commit. The
existing variants and March registration row stayed unchanged; the local
October row contains 43 registrations. Invalid price, identity, stale
evidence and attempts against a non-PGlite client were rejected. The late
failure restored the initial state and rerunning the exact committed plan
was a no-op. No production rows, public assets or site were changed.

A second rehearsal with fresh manufacturer and Mobility Sweden receipts
used the licensed XAB model image rather than the pressroom copy. It added
one Macan to the real 106-variant post-Inster baseline in isolation. It
kept Inster's fractional charging value, all prior variants and the
historical Macan market month. Rollback and exact no-op replay passed.

The private build was tested at 320, 390 and 1440 px. The buyer page
renders the licensed Macan photo without overlapping text on mobile,
labels the price as the manufacturer's starting price, and compares
against the existing Kia EV2. The battery note identifies the 100 kWh
as gross capacity; the towing note specifies a braked trailer and the
optional tow bar. The sitemap rehearsal adds only the Macan detail page
and retains all seven public news articles. Vehicle structured data
does not turn the starting price into a fixed offer.

```sh
node scripts/verify_hyundai_inster_advanced_ui.mjs --macan --readback <local-result> --photo <photo-packet>
node scripts/run_python.mjs scripts/verify_hyundai_inster_advanced_static.py <ui-result> --macan
node scripts/prepare_hyundai_inster_advanced_release.mjs --macan --readback <local-result> --ui <ui-result>
```

The Macan profile in the existing single-variant publisher defaults to
a read-only check. It requires newer official captures, the unchanged
canonical baseline, passing main CI, and a deployed reader with the
four exact image files. Only the matching seal admits the Macan
transaction. The anonymous view must show exactly one addition before
commit and again through a separate connection before the scoped export.
Do not substitute the private preview export for this readback.

[base]: https://configurator.porsche.com/sv-SE/mode/model/XABAA1
[technical]: https://configurator.porsche.com/sv-SE/mode/model/XABAA1/specifications?tab=technical-data
[equipment]: https://configurator.porsche.com/sv-SE/mode/model/XABAA1/specifications?tab=standard-equipment
[compare]: https://compare.porsche.com/sv-SE?model-series=macan
[market]: https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober
[press]: https://newsroom.porsche.com/de/pressemappen/der-neue-porsche-macan.html
[terms]: https://newsroom.porsche.com/de/bilder-videos/porsche-newsroom-nutzungshinweise.html
[commons-front]: https://commons.wikimedia.org/wiki/File:Porsche_Macan_(II)_%E2%80%93_f_22022025.jpg
[commons-rear]: https://commons.wikimedia.org/wiki/File:Porsche_Macan_(II)_%E2%80%93_h_22022025.jpg
