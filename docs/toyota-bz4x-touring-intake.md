# Toyota bZ4X Touring intake

23 November 2026. Source-reviewed and rehearsed as a **private draft**.
Production remains at 45 models and 108 public variants.

## Exact identity

[Toyota Sweden's model][model] and [configurator][specs] identify the Touring
kombi independently of the ordinary bZ4X. The exact Swedish Active Tech FWD
uses model ID `005b05cd-028a-4116-9df3-e6ee345cd7a8`, configuration
`4dd8d99a-24a0-4de3-b84f-bb4c6fbf1526`, version `6.HD`, 224 hp,
front drive and standard 235/60 R18 tyres. Do not infer a model year from
the day the model is marketed or take values from its AWD siblings.

The exact technical values are final combined WLTP **591 km** and
**14.0 kWh/100 km**, 74.7 kWh gross, 150 kW DC, 11 kW standard onboard AC,
669 L behind the upright rear seats, 750 kg braked towing and five seats.
Its Swedish recommended **starting price is SEK 569,900** including VAT.
The current linked [importer brochure][brochure] and the stock base
configuration agree. Option-inclusive configuration totals and monthly
finance amounts are not the starting price. The 1,500 kg rating on the
model overview applies to AWD only.

The official Mobility Sweden October workbook has one separate
`TOYOTA | BZ4X TOURING | EL` row, rank 23, 373 October and 1,159 YTD.
This does not establish the historical first month, the 12-month total
or confirmed availability. A read-only check found no Touring canonical
model, market row or alias in production; the existing bZ4X is distinct.

## Rehearsal and media

`scripts/toyota_bz4x_touring_review.py --capture` saves the original
official model, specifications, brochure and workbook separately.
`--replay` validates the same recorded hashes and capture date.
The real capture `toyota-touring-capture-3uo1o_qj` and all five identity,
price and WLTP regressions passed. The production-shaped isolated
rehearsal `scripts/verify_toyota_touring_draft.mjs` uses the real
108-variant baseline from a read-only snapshot. It creates a distinct
market row, October occurrence, alias, source rows and private variant
in PGlite, preserves all public variants, and verifies late rollback
and exact duplicate rejection. It cannot write to the remote database.

The visually checked [TTTNIS photo][media] has a CC0 license and shows a
complete bZ4X Touring from the front quarter. The pictured Z 4WD is a
Japanese configuration; label it as a model image with equipment and
drivetrain differing from Active Tech FWD. Original 5013 x 2894 JPEG:
`8482ada3c9ec2af8b83b64f9b6ca6137546cd4bb01ad55448c4a3143882793b3`,
private packet `toyota-touring-cc0-photo-eOfp40`. The narrow rear
photograph is not the selected display candidate.
The private `responsive-review.json` binds the original and full-frame
480, 800 and 1280 px WebP files, all decoded locally at their expected
dimensions. No site image registration or browser preview yet.

Next implement the exact identity bootstrap and reviewed publication
adapter, register the reviewed responsive media, and prove the complete
transaction and buyer page against current production before release.
No bulk reseed, paid AI, public export or production write was made.

[model]: https://www.toyota.se/bilar/bz4x-touring
[specs]: https://www.toyota.se/bilar/bz4x-touring/specifications
[brochure]: https://pdf.toyotasverigebroschyr.com/price-list/bz4x-touring
[media]: https://commons.wikimedia.org/wiki/File:Toyota_bZ4X_Touring_Z_4WD.jpg
