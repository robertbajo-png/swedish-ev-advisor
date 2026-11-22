# CUPRA Tavascan: second-wave intake

20 November 2026. Private review only. This is not a replacement for a
first-pilot model or approval to add public variants.

## Swedish identity and prices

- The official [Mobility Sweden October report][market] links a workbook
  with an exact `CUPRA | TAVASCAN | EL` row: 63 in October and 692 YTD.
  It supports model discovery, not a model year, equipment level or
  availability claim.
- [CUPRA's documentation index][index] links two separate cash-price lists,
  dated 15 September 2026. The PDFs explicitly cover Swedish stock of the
  named model year and include VAT. Both are retained with source hashes.
  The MY25 price does not replace the MY26 price, and neither sheet proves
  that a specific car is currently available. No leasing or tow-hook price
  is treated as the purchase price.

| Swedish edition | Motor | Drive | MY26 stock list (SEK) | MY25 stock list (SEK) |
| --- | ---: | --- | ---: | ---: |
| Drive | 210 kW | RWD | 554,900 | 534,900 |
| VZ | 250 kW | AWD | 599,900 | 579,900 |
| VZ Drive | 250 kW | AWD | 619,900 | 599,900 |
| VZ Adrenaline | 250 kW | AWD | 669,900 | 649,900 |

The [Swedish model page][model] supports SUV coupe, five seats and 540 L
at model scope. The [October Swedish WLTP declaration][energy] gives
16.0 kWh/100 km for the 210 kW motor and 17.2-17.4 for the 250 kW motor.
The VZ interval is not assigned to trim or wheel size. The Swedish list's
77 kWh label alone is not a net/gross statement. [CUPRA's European press kit][tech]
is a technical lead, but its Endurance and VZ intervals do not establish the
specific Swedish equipment and model-year combinations. Nor should the new
global 58 kWh version be added from a press release without Swedish evidence.

## Model photo

The [Danish production launch][launch] links the [exact press photo][photo]
with per-image editorial terms. Visual review confirmed a production Tavascan
exterior, not the earlier concept. The full frame is retained with only
mechanical web resizing (2000 x 1123 to 1500 x 842). Credit SEAT & CUPRA
Danmark / pressbild. The pictured equipment is not attributed to a particular
Swedish trim. The source page, exact original URL and original byte hash are
restricted to `cupra|tavascan` and independent editorial use. No public image
file or lookup entry is added by this review.

## Swedish MY26 Drive technical cross-check

Volkswagen Group Sweden's stock site labels two exact new 2026 Tavascan
Drive Swedish Editions at [Bilia Nacka][drive-nacka] and [Moller Bil
Eskilstuna][drive-eskilstuna]. The factory edition, electric powertrain and
210 kW motor agree. The [dealer's separate listing][drive-dealer] reflects the
same Eskilstuna car, so these are two cars, not three independent tests.
The individual sources explicitly report 77 kWh net / 82 kWh gross, onboard
AC 11 kW, vehicle DC maximum 135 kW, 1,000 kg braking-rated towing at 12%, and
540 L cargo. None identifies the corresponding certified WLTP for that car.
Do not take the 750 kg unbraked entry or the 75 kg vertical load as towing.

The Eskilstuna cash offer agrees with the 554,900 SEK MY26 PDF row. The
534,900 SEK Nacka cash offer is an individual MY26 price, even though the
MY25 Drive price list contains the same number. The dealer's JSON-LD calls
the 210 kW car front-wheel drive and a station wagon; this conflicts with
CUPRA's [rear-drive offer description][offer-index] and [SUV-coupe model
description][model]. Reject those schema fields; retain separately corroborated
price/technical values. A live listing is not a claim about all versions.

The [MY26 Drive offer][offer-drive] names standard 19-inch wheels and advertises
up to 550 km at 554,900 SEK, but its 15.3 kWh/100 km consumes less on paper
than the October Swedish 210 kW declaration's 16.0. Keep the advertised range
and energy figure as leads until a matching homologated configuration resolves
the scope. The [VZ offer][offer-vz] mentions both MY25 and MY26 in its body;
do not resolve its year by price alone. The Tavascan [manual registry][manual]
lists MY24, MY25 and MY27, not MY26, so the MY27 table is not used for this
MY26 inference. The Drive hardware proof does not fill any VZ variant.

## Exact equipment and VZ model-year comparison

The [Linkoping importer stock page][drive-linkoping] specifically describes
a new Drive Swedish Edition MY26 with rear-wheel drive and 19-inch Vulcano
wheels (235/55 R19 front, 255/50 R19 rear). This is direct Swedish evidence
against the earlier incorrect dealer drivetrain label. The captured [Drive
offer][offer-drive] matches the MY26 price list and the wheel specification.
Its 550 km is an advertised maximum, not a homologated value for the exact
stock car. Its 15.3 kWh/100 km remains separate from the October declaration's
16.0 motor-level value. Do not present either as an exact paired WLTP profile.

Three [VZ][vz-base], [VZ Drive][vz-drive] and [VZ Adrenaline][vz-adrenaline]
stock pages confirm the named Swedish Edition **MY25** cars. Their 250 kW
AWD motor, 77/82 kWh net/gross, 1,200 kg braked at 12% and 540 L are retained
with the source and year. Their individual cash offers are separate from
financing and the MY26 list. In particular the lower finance-only amount on
the VZ Drive page is not that car's cash price or a general starting price.

The [Italian MY26 manufacturer sheet][italian] puts the 58 kWh version in
a separate 140 kW column. It distinguishes the 210/250 kW 77 kWh columns
but uses different wheels for the Italian Drive-equivalent entry and lists
1,800 kg braked for the Italian VZ. This is not the Swedish MY26 VZ rating.
The 135 kW in its DC timing row is charging-test context, not an explicitly
stated peak acceptance limit. Do not use any of these Italian numbers to
fill Swedish WLTP, price, towing, or unverified peak DC fields.

## Factory codes and the second Swedish price check

The importer stock pages' Swedish configuration state now binds the three
previous MY26 Drive cars to `KR1BCD` and the three reviewed MY25 VZ editions
to `KR1CED`. The full edition, model year and a matching individual stock
reference are required as well as the code. A powertrain code is not unique
to the trim or wheel equipment. All six current state records lack a
vehicle WLTP payload; do not read the 0 g/km CO2 figure as range or consumption.

The [Gavle importer page][drive-gavle] records another new Drive Swedish
Edition MY26 with `KR1BCD`. [Din Bil's page for the same car][gavle-dealer]
calls it Endurance, shows rear-wheel drive and independently lists a cash
price of SEK 554,900. The importer names the exact Swedish CUPRA outlet and
confirms the same amount, model code and technical scope. This is additional
corroboration for the official MY26 Drive from-price, not a second version,
release approval, or a guarantee about national stock. Treated as a dealer
offer, separate from the manufacturer price list and financing.

The rendered Swedish build page linked from the [model page][model] shows
552 km for a 210 kW rear-drive selection and 523 km for a 250 kW selection.
Its range disclaimer is preliminary and the visible cards do not bind those
figures to the captured model year or exact stock equipment. Do not substitute
552 for the 550 km sales claim, or pair the former with the dated motor-level
16.0 kWh/100 km. The historical indexed leasing result is not a live
certification source. No Swedish combined WLTP figures are promoted.

## Verification and remaining work

The seven-source packet `cupra-tavascan-review-r8xxnkps` contains the original
documents and structured review, and replay reproduced it unchanged. All 18
focused price, market and image tests and the Vite production build passed.
The verified-photo dry run reported `applied: false`, with no database writes.
The old broken source queue URL is replaced with the current manufacturer
model page. The ten-source packet `cupra-tavascan-review-m_n0t1c0` adds the
Drive stock evidence. Six focused tests and the Vite build passed. Next obtain
the exact Swedish Drive WLTP range/consumption and equivalent technical and
price evidence for the three VZ editions. Do not infer those facts from the
old VZ price list or market report. No database write, deployment or paid
API call.

The 16-source packet `cupra-tavascan-review-keoga81c` adds the Drive
equipment/offer and VZ year/market evidence. It retains `publication_approved:
false`. An exact Swedish technical declaration for MY26 VZ is still needed.

The succeeding 18-source packet `cupra-tavascan-review-fzwagatl` adds the
factory identity checks and the separate Gävle price corroboration. Both the new
and prior captures reproduce on replay. All 73 review tests and the Vite
production build passed. No database writes, paid calls or publication.

The fresh 19-source packet `cupra-tavascan-review-_5fy908l` adds the
[Finnish importer's technical comparison][finnish]. Its sheet is dated
2 March 2026, but the `KR1BCD` column is expressly model year 2025 B:
`TUR` has 550 km and 16.0 kWh/100 km; `TIM` has 541 km and 16.3 kWh/100 km.
The Finnish equipment sheet also names the same 19-inch Vulcano wheel and
tyre sizes seen on the Swedish Drive. This supports the equipment distinction,
not transfer of either WLTP value to Swedish MY26. The Swedish offer's up-to
range and consumption claim, and the Swedish motor-level consumption, remain
separately attributed. [Transportstyrelsen's public lookup][registry] returned
an error before showing technical data; no registry value was recorded.

The 12 focused review tests, local transactional publication regression and
Vite production build passed. Next request the combined WLTP fields on a
Swedish MY26 Drive technical declaration or Certificate of Conformity, tied to
the Swedish edition and wheel setup. Then repeat for the MY26 VZ editions.
Verified Swedish MY26 Drive price reference remains SEK 554,900. No database
writes, paid calls or publication.

## Drive MY26 base-edition profile

The fresh 18-source `cupra-tavascan-review-pho52ikr` packet additionally
requires the measurement footnote joined to the starred consumption row
on the exact [Swedish Drive MY26 offer][offer-drive]. The footnote states
combined WLTP for the base car. The numeric row explicitly uses kWh/100 km;
the generic fuel unit in the footnote is not applied to the EV figure.
Use **15.3 kWh/100 km** for private review of the standard 19-inch Drive
edition, ahead of 16.0 in the more general October motor declaration.
Preserve the alternative and its narrower ability to identify equipment.

The replayable profile contains eight of the nine technical fields, tied
to the exact Swedish MY26 `KR1BCD` Drive factory evidence, technical rows
for two stock units, and five-seat model data. The MY26 Swedish manufacturer
starting price remains SEK 554,900, cross-checked with the separate Gavle
cash offer. The headline's up-to 550 km is not the starred WLTP row;
the profile stores it only as an advertised maximum, not `wltp_range_km`.
That initial receipt holds the exact combined range. The separate stock
review below resolves it without mutating the original report or using it
for other editions.

## Drive MY26: exact combined WLTP from Swedish stock

The [CUPRA Eskilstuna][wltp-eskilstuna] and [CUPRA Kalmar][wltp-kalmar]
public detail pages show **553 km in combined driving**. For each distinct
unit, the browser's original stock response supplies MY26, the 210 kW rear
drive, 77 kWh net and the matching 19-inch front and rear tyres. The response
keeps 692 km city range separate. Volkswagen Group Sweden's corresponding
records match both the registration and the factory order number and identify
`KR1BCD` with Drive package `PF0` and Swedish Edition code `P80`.

Choose **553 km and 15.8 kWh/100 km** together from the two same-scope WLTP
datasets. Keep the original offer's 550 km maximum and 15.3 kWh/100 km as
alternatives. The distributor's generic front-drive field conflicts with
CUPRA's explicit motor/equipment and driving description for those same units;
it is retained as a rejected alternative. The individual cars' offer prices
are not used. The matched manufacturer's MY26 list and separate dealer check
still support **SEK 554,900 from**.

This closes the nine technical fields for the private MY26 Drive profile,
not the VZ or MY27 profiles. The separate isolated transaction below does
not grant owner release approval.
The fresh private receipt is `cupra-tavascan-stock-wltp-ngXLfk`. Its input
files are the two original stock responses and their matching importer HTML.
The 22 focused tests, shared transaction regression and Vite build passed.

```powershell
node scripts/cupra_tavascan_stock_wltp.mjs --capture cupra-tavascan-review-pho52ikr
node scripts/cupra_tavascan_stock_wltp.mjs --replay data/local/release-data/cupra-tavascan-stock-wltp-ngXLfk
node --test tests/cupra-tavascan-stock-wltp.test.mjs
```

## Drive MY26: isolated catalog insertion

The local-only `cupra_tavascan_drive_sweden_my26_local_v1` adapter uses all
nine technical fields from fresh exact receipts, the Swedish stock-list
price with the separate authorized Gavle price check, and the hashed,
model-scoped press photo. The production connector refuses this adapter.
The official October market row remains market evidence only.

Read-only Supabase confirms one existing empty Tavascan draft and the exact
resolved `CUPRA / TAVASCAN / EL` market identity. The anonymous view of an
isolated database matched all 84 rows on live and exact main `55f6e9d`.
Applying the plan in that database added exactly one row for Drive Swedish
Edition MY26, with 553 km combined and SEK 554,900 from, while preserving
all 84 preexisting public rows and earlier registration months. The test
verified the expected anonymous row before commit, access restrictions,
model-photo binding, late rollback and idempotent replay. The private
catalog and receipt are in `cupra-tavascan-readback-1LEOox`.

The private build of that catalog (`ui-MIQRQ7`) verified the published-shape
JSON, actual JPEG/WebP files, photo rights and credit, detail values and
price link. Playwright used the real built files at 320, 390, 768 and 1440
pixels with no substituted catalog response. Mobile text stays below the
image. The exact-main baseline still shows the old availability badge;
include the separately reviewed removal before publishing this candidate.

```powershell
node scripts/verify_cupra_tavascan_drive_local_publication.mjs --review data/local/release-data/cupra-tavascan-stock-wltp-WJxIOJ
node scripts/verify_cupra_tavascan_drive_ui.mjs --readback data/local/release-data/cupra-tavascan-readback-1LEOox
```

No database write or deployment outside the isolated copy. Do not release
the model, infer availability for the full grade, or add VZ and MY27 from
these receipts. A future release requires specific approval and a current,
reviewed production command, source recheck and exact-main CI.

## Configurator figures belong to MY27

The public [Swedish Drive configurator][drive-config] linked by the model
page identifies the selected 210 kW RWD Drive Swedish Edition as **MY27**.
Both the model year and the selected `KR1BCD` configuration key end in
2027; the factory wheel and currently selected wheel are the same 19-inch
Vulcano. Its WLTP payload reports **552 km and 15.8 kWh/100 km combined**.
The city's 691 km is a separate measurement. Keep these as configuration
observations with the manufacturer's qualifications; do not assign them to
the MY26 stock scope or pair them with its price, consumption or towing.
The same MY27 selection shows SEK 554,900 as its base and final configured
amount, with zero options charge and discount. It is a separate price
observation, not the MY26 cash offer or a confirmed MY27 list-price basis.
The MY27 response independently confirms 77 kWh usable battery, 11 kW
onboard AC, 540 L cargo and RWD. The fresh `cupra-tavascan-configurator-KoqD8Z`
receipt also binds **135 kW peak DC** to factory standard-equipment code
`MDCBLH2` for that exact Swedish MY27 selection. This is vehicle peak power,
not the rating of a charger used to quote a charging time. The response's
maximum towing field is null. Keep exact MY27 braked towing and seat count
open, and do not copy them from MY26.

The MY26 offer still gives an advertised maximum of 550 km, while the
model-family page displays up to 553 km. Neither was the evidence used for
the exact MY26 stock result above. The public Swedish registry returned an
error before providing technical results for the reviewed Gavle car.
Separately obtain the MY27 price basis,
approved WLTP and remaining technical facts before preparing a candidate.

The original private `cupra-tavascan-configurator-cPjn7b` packet records the public
configuration response hash and rendered range. Capture uses the normal
configurator and only observes its own request; there is no direct API call
from the script. Replay rejects a mismatched model year, trim, wheel,
market, measurement phase or units. The new receipt also rejects an absent,
ambiguous or mislabeled peak DC row. The original still replays unchanged.
No catalog, DB or public media changed.

```powershell
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --capture
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --replay data/local/release-data/cupra-tavascan-review-r8xxnkps
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --capture --with-swedish-drive-stock
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --replay data/local/release-data/cupra-tavascan-review-m_n0t1c0
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --capture --with-swedish-drive-stock --with-year-crosscheck
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --replay data/local/release-data/cupra-tavascan-review-keoga81c
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --capture --with-swedish-drive-stock --with-year-crosscheck --with-stock-identity
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --replay data/local/release-data/cupra-tavascan-review-fzwagatl
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --capture --with-swedish-drive-stock --with-year-crosscheck --with-stock-identity --with-nordic-crosscheck
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --replay data/local/release-data/cupra-tavascan-review-_5fy908l
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --capture --with-swedish-drive-stock --with-year-crosscheck --with-stock-identity --with-drive-profile
node scripts/run_python.mjs scripts/cupra_tavascan_review.py --replay data/local/release-data/cupra-tavascan-review-pho52ikr
node scripts/run_python.mjs -m unittest discover -s tests -p test_cupra_tavascan_review.py -v
node --test tests/cupra-tavascan-configurator.test.mjs
node scripts/cupra_tavascan_configurator.mjs --capture
node scripts/cupra_tavascan_configurator.mjs --replay data/local/release-data/cupra-tavascan-configurator-cPjn7b
```

[market]: https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober
[index]: https://www.cupraofficial.se/kopa/broschyrer-prislistor
[model]: https://www.cupraofficial.se/bilar/tavascan
[energy]: https://www.cupraofficial.se/content/dam/countries/se/cupra-website/broschyr/cupra-bransledeklaration-okt2026.pdf
[tech]: https://www.seat-cupra-mediacenter.com/CUPRA-Brand/presskits/new-cupra-tavascan-endurance/technical-data
[launch]: https://www.mynewsdesk.com/dk/seat-danmark/pressreleases/cupra-danmark-lancerer-skrap-pris-paa-tavascan-i-fire-spaendende-konfigurationer-3336201
[wltp-eskilstuna]: https://www.cupraofficial.se/kopa/bilar-i-lager/w/offer/new/U1dFNDAwNjAyMjIyMDI2ODY3NTU2=
[wltp-kalmar]: https://www.cupraofficial.se/kopa/bilar-i-lager/w/offer/new/U1dFNDA2OTUyMjIyMDI2ODY3NTY2=
[photo]: https://www.mynewsdesk.com/dk/seat-danmark/images/dsc00621-bred-punktum-jpg-3072079
[drive-nacka]: https://bilarilager.vwgroup.se/cupra/EWB33D
[drive-eskilstuna]: https://bilarilager.vwgroup.se/cupra/EZK46X
[drive-dealer]: https://mollerbil.se/bilar-i-lager/ezk46x
[offer-index]: https://www.cupraofficial.se/kopa/erbjudande/tavascan
[offer-drive]: https://www.cupraofficial.se/kopa/erbjudande/tavascan/privat/cupra-tavascan-77-kwh-2wd-286-hk
[offer-vz]: https://www.cupraofficial.se/kopa/erbjudande/tavascan/privat/cupra-tavascan-250-kw-vz-4wd
[manual]: https://www.cupraofficial.se/aga/instruktionsbocker/manual-details.manuals.tavascan
[drive-linkoping]: https://lagerbilar.vwgroup.se/cupra/DRX34F
[drive-gavle]: https://bilarilager.vwgroup.se/cupra/LYK12H
[drive-config]: https://www.cupraofficial.se/carshop/w/configuration?id=ePl9IIpVw_Cws2OQj6efq653kKEziucdfXxAgk7OLvoG-u4BbgZABKTDDYEISBtZAJG-e6SzIRAB6XBjIIIlAyyh5uii62fgCJRzMzRRMHQydAIxTc0UQMDRRSm2FgAeFiki&carline=CARLINE-GROUP-KR1
[gavle-dealer]: https://dinbil.se/cupra/bilar-i-lager/alla-bilar-i-lager/lyk12h
[vz-base]: https://bilarilager.vwgroup.se/cupra/HRB38A
[vz-drive]: https://bilarilager.vwgroup.se/cupra/BGR07F
[vz-adrenaline]: https://bilarilager.vwgroup.se/cupra/DNW03D
[italian]: https://www.cupraofficial.it/content/dam/countries/it/cupra-website/listini/2026/11/listino-tavascan-112026.pdf
[finnish]: https://api.k-auto.fi/priceCatalog/api/PriceCatalog/13a524b6-bec6-4cf2-89a2-40e7b800614c
[registry]: https://fordon-fu-regnr.transportstyrelsen.se/

## Guarded Drive MY26 Release

The registered adapter remains local-only in the generic insertion tool.
`scripts/publish_approved_cupra_tavascan.mjs` is the only dedicated release
entry point. Without an apply flag it verifies the exact local browser proof,
current main and anonymous production catalog, registered media hashes, a
fresh independently captured source packet, and the scoped read-only snapshot.
It emits a review hash. A review hash does not grant permission to publish.

```powershell
node scripts/publish_approved_cupra_tavascan.mjs --simulate --reviewed $reviewedPlan --ui $uiReport --fresh $freshStockReceipt --connector $projectReadConnector
```

The reviewed plan is the private `reviewed-plan.json` from a full local
readback, and the UI report must be from the build of that exact plan.
The fresh receipt is from a second capture of the approved Swedish sources,
not a replay of the reviewed capture. The 15-minute window is measured
from the oldest included source. PDF and market workbook digests must
match; dynamic page hashes can change only while the replayed factual
claims, identities, links, and quotes remain identical.

Simulation uses an isolated PGlite transaction and an in-memory export.
A future commissioned apply requires the owner's exact scope approval, the
four matching released media files and their registry entries in the local
release candidate, and a fresh unused private journal. Only that variant
can pass the anonymous precommit check. The separate export mode requires
the completed commit receipt and cannot write the database. If only the
attempt receipt exists, inspect committed state before any further action.
Sitemap, CI and live site verification remain separate from insertion.

### 22 November: code and media revalidated after XPENG G6

The exact Swedish Drive MY26 has nine verified fields, 553 km combined WLTP
and SEK 554,900 as CUPRA Sverige's list price. No VZ, MY27 or separate dealer
offer is released by this adapter. The checked tree preserves the G6 and
Renault support and adds the full-frame verified press photo with responsive
derivatives. The private site verified the image, specification text,
comparison action and absent retail badges at 320, 390, 768 and 1440 px.

The refreshed guarded command matched the public production catalog and
the separate source snapshots, then inserted one variant in PGlite without
changing the 87 prior rows. Bad scope, expired evidence, changed catalog,
wrong public identifiers and a late transaction failure were rejected.
Export recovery is idempotent. The production command additionally requires
exact current main and unchanged tracked code and media. No production write,
migration, paid API call or distribution was performed.
