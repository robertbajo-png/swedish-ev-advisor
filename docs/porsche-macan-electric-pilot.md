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

Remaining: verify a permitted model photo and rehearse the scoped
insertion, re-export and browser release. Never use a combustion
Macan, Macan 4S or Turbo as a substitute image. The [Porsche Sweden launch
gallery][press] is a source to review, not yet a permission receipt.

[base]: https://configurator.porsche.com/sv-SE/mode/model/XABAA1
[technical]: https://configurator.porsche.com/sv-SE/mode/model/XABAA1/specifications?tab=technical-data
[equipment]: https://configurator.porsche.com/sv-SE/mode/model/XABAA1/specifications?tab=standard-equipment
[compare]: https://compare.porsche.com/sv-SE?model-series=macan
[press]: https://via.tt.se/pressmeddelande/3561876/porsche-fordubblar-modellutbudet-av-sin-elektriska-suv-macan?lang=sv&publisherId=1995911
