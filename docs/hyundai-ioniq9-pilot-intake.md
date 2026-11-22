# Hyundai IONIQ 9: Swedish seven-seat pilot

## Verified scope

The Swedish configurator identifies material `GOW7YCZ7ZHH530` as the
seven-seat Advanced AWD MY27 with 20-inch wheels. The Swedish price list and
factory trim response agree on SEK 850,900 before paint. The factory WLTP
response and Swedish technical table agree for the same wheels and grade.
The candidate uses a manufacturer starting price, not a list price, dealer
offer, campaign price or fixed structured product offer.

| Field | Value and basis | Evidence |
| --- | --- | --- |
| Price from | SEK 850,900 before paint | [Swedish price list][price] and exact factory trim |
| Range | 606 km combined WLTP, 20-inch wheels | [Technical PDF][tech] and exact factory WLTP |
| Energy use | 20.4 kWh/100 km combined WLTP | [Technical PDF][tech] and exact factory WLTP |
| Battery | 110.3 kWh as stated | [Swedish model page][model] |
| DC | 233 kW peak for the model's common 800 V hardware | [Swedish model page][model] |
| AC | 10.5 kW actual three-phase charging | [Technical PDF][tech] |
| Cargo | 338 L behind row three, no frunk | [Technical PDF][tech] |
| Towing | 2,500 kg braked with towing equipment | [Technical PDF][tech] |
| Seats | 7 | [Exact configuration][config] |
| Drivetrain | AWD | [Exact configuration][config] |

[Mobility Sweden][market] identifies the model only. October showed 43 units
for exact `HYUNDAI|IONIQ 9|EL` and 330 year-to-date. The existing March row
is preserved. The raw article, workbook, original sources, Swedish factory
requests and results have separate hashes.

The [Hyundai Motor Sweden press image][media] identifies IONIQ 9 as a model,
not the exact wheel or equipment version. Keep full frame and attribution.
The original 11,324 by 7,923 JPEG and the publisher's 746 by 522 WebP are
retained unaltered. A second advertised size was unavailable and is not
used. The smaller file was verified against the original frame.

## Local release rehearsal

- The tracked collector fetches the primary sources, captures two bounded
  read-only Swedish factory queries and verifies the pinned market workbook.
  The adopter replays the raw inputs and refuses an altered price, identity,
  image or incomplete record. No AI extraction is needed.
- The national price PDF was registered to IONIQ 5 earlier. The IONIQ 9
  transaction uses the existing evidence read-only, with matching owner,
  URL, status, authority and exact document hash.
- The isolated catalog grew from 104 to 105 variants. Every prior row
  matched, the previous month and all other sources remained intact,
  duplicate execution was a no-op, and forced late failure rolled back
  both staging and canonical records. The adapter remains local-only.
- The project build and targeted regressions passed. The local UI verified
  exact images at 320, 390 and 1440 px, no mobile overlap, the starting-price
  schema and comparison against a seven-seat Kia EV9. No production
  database, Pages, DNS, news or settings were changed.

Next: complete the staged reader CI and static SEO checks, then implement
the narrow fresh-source publisher bound to that staged deployment and
current catalog baseline. Run CI on the exact main commit
before a production insertion or distribution. No DC migration is necessary
for this 233 kW variant.

[config]: https://lager.hyundai.se/model/IONIQ%209/GOW7YCZ7ZHH530?customer=private&ext=R5P&int=NNB
[model]: https://www.hyundai.com/se/sv/bilar/ioniq9.html
[price]: https://dmassets.hyundai.com/is/content/hyundaiautoever/Hyundai_Sverige_Prislista_20261102pdf
[tech]: https://dmassets.hyundai.com/is/content/hyundaiautoever/250829_IONIQ9_TechSheetpdf-AFpdf
[market]: https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober
[media]: https://www.mynewsdesk.com/se/hyundai/images/hyundai-ioniq-9-2024-exterior-charging-fq-punkt-jpg-3276354
