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
photographs by M 93 are a separate CC BY-SA 3.0 DE lead. Both original
downloads returned HTTP 429 during review. The file pages identify the
electric generation, but do not establish the exact drivetrain. Neither
image has been added to the catalog or marked as reviewed media.

```sh
node scripts/run_python.mjs scripts/porsche_macan_release_intake.py --capture-photo
node scripts/run_python.mjs scripts/porsche_macan_release_intake.py --specs <spec-packet> --market <market-packet> --photo <photo-packet>
```

The combined intake replays the original source packets and attaches
the exact quote, source URL, hash and fetch date to each of the nine
technical fields and the Swedish starting price. It reports freshness
without refreshing saved timestamps. It cannot publish or set image
rights. Remaining: clear image usage, rehearse the scoped insertion,
re-export and verify the car page in the browser.

[base]: https://configurator.porsche.com/sv-SE/mode/model/XABAA1
[technical]: https://configurator.porsche.com/sv-SE/mode/model/XABAA1/specifications?tab=technical-data
[equipment]: https://configurator.porsche.com/sv-SE/mode/model/XABAA1/specifications?tab=standard-equipment
[compare]: https://compare.porsche.com/sv-SE?model-series=macan
[market]: https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober
[press]: https://newsroom.porsche.com/de/pressemappen/der-neue-porsche-macan.html
[terms]: https://newsroom.porsche.com/de/bilder-videos/porsche-newsroom-nutzungshinweise.html
[commons-front]: https://commons.wikimedia.org/wiki/File:Porsche_Macan_(II)_%E2%80%93_f_22022025.jpg
[commons-rear]: https://commons.wikimedia.org/wiki/File:Porsche_Macan_(II)_%E2%80%93_h_22022025.jpg
