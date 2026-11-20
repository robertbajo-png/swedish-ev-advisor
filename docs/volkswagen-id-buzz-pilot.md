# Volkswagen ID. Buzz: pilot source intake

2026-11-19. Phase 3 remains **2/5 released**. EX90 is still on hold. ID. Buzz
has a complete private review packet and a tested local insertion for two
variants, not an approved production publication batch.

## Scope and evidence

- The official October Mobility Sweden input has the electric passenger-car
  row `VW | ID. BUZZ | EL`: 147 October registrations and 910 January-October.
  This establishes market presence, not current prices, specs or orderability.
- A read-only Supabase check found the existing `volkswagen / id buzz` draft,
  exact alias `VW / ID. BUZZ` with `needs_mapping = false`, and no public
  variants. Reuse this identity; do not insert a second model or include Cargo.
- First scope: model-year 2027, short body, five standard seats, Sweden Olympic
  Edition. No long, six-seat, seven-seat, GTX or earlier-model-year values.
  The [Swedish importer's model page][model] shows the following exact cards:

| Variant | Cash starting price incl. VAT | Combined WLTP up to | Net battery | Advertised towing |
| --- | ---: | ---: | ---: | ---: |
| Pro RWD | SEK 589,900 | 450 km | 79 kWh | 1,200 kg |
| Pro 4MOTION AWD | SEK 625,900 | 419 km | 79 kWh | 1,800 kg |

- [SKVFS 2026:13][prices], p. 44, independently lists these exact short-wheelbase
  prices under `26VW0199` and `26VW0195`. Those are tax-list identifiers, not VW
  engine IDs. Importer price/availability remains primary; establish price type
  and recheck freshness in the eventual publish packet. Do not reuse prices from
  the other Olympic Editions, lease payments or older exact-name rows.
- The [Swedish technical page][technical] confirms the braked towing scope at
  a 12% gradient. It gives 1,121 L behind row two for the short Pro; the exact
  five-seat 4MOTION card states 1,131 L. Do not collapse those values or use
  folded-seat maximums. For any later seven-seat intake, 1,340 L behind the second
  row is not rear cargo with all seven seats in use.

## Repeatable capture

Run `node scripts/run_python.mjs scripts/volkswagen_id_buzz_preflight.py`.
It reuses the read-only, bounded source fetcher (robots and TDM checks), only
allows two exact Swedish importer URLs, and saves hashes, times and variant-bound
evidence in an ignored `data/local/release-data/volkswagen-id-buzz-*` folder.
The live run captured both HTML pages (HTTP 200) and two short-body cards.
The evidence is `needs_review` even on success; it does not produce a public
draft, call AI, write to Supabase or change a release. Identical generic rendered
text in the two direct configurator responses is not exact-variant evidence.

## Next release check

The Swedish configurator's Drivlina step showed these exact buildable selections
on 19 November. Both have 2,989 mm wheelbase, five seats, year 2027, sales group
74347, and configurator model version 2. Preserve the full configuration ID
including options when storing browser evidence.

| Configurator selection | Motor ID prefix | Motor | Combined WLTP range | Combined WLTP consumption | Cash incl. VAT |
| --- | --- | ---: | ---: | ---: | ---: |
| [Pro 5-Seats Sweden Olympic Edition][config-pro] | `EBBR7R` | 210 kW | 452 km | 19.60 kWh/100 km | SEK 589,900 |
| [Pro 4MOTION 5-Seats Sweden Olympic Edition][config-awd] | `EBBR5R` | 250 kW | 416 km | 21.50 kWh/100 km | SEK 625,900 |

`node scripts/volkswagen_id_buzz_configurator.mjs` checks current robots/TDM
access before rendering, then requires an exact model/engine/market/year/seating
match in the public chooser. It stores rendered text and hashes only as private
review evidence. The initial 19 November live run captured both exact
configurations, with intact text SHA-256 and zero held variants, in the ignored
`data/local/release-data/volkswagen-id-buzz-configurator-JWNZSb/` directory.
An earlier unavailable robots check stopped before rendering; a fresh robots
read explicitly allowed both paths before the successful run. Six Python
preflight and three Node configuration regression tests passed.

The Swedish configurator's summary and technical tabs confirm the figures above
for the selected cars with no extra-cost options. The expanded WLTP table
distinguishes 452/416 km combined from 609/558 km city. Use 452/416 in the
technical packet instead of 450/419 advertised on the model page: the former
are scoped to the configured version, option set, and price. The summary guard
compares the full configuration ID, interior, exterior, combined consumption,
VAT-inclusive and exclusive prices, no extra-cost options, and braked towing.
The automated summary rerun captured both versions, no holds, with independent
engine-text and summary hashes under the private
`data/local/release-data/volkswagen-id-buzz-configurator-pvIRPe/` directory.
The rendered text, summary and separate charging extract hashes were read back
and the two motor prefixes cross-checked. Six JS tests, eight Python tests and
the existing public-catalog contract passed. A successful capture is not the
same as venue/order confirmation or publication approval.

The exact-configurator weight section displayed 1,800 kg for *both* builds.
Do not import that observation as the RWD specification. The current Swedish
[model cards][model] and [braked towing table][technical] consistently assign
1,200 kg at 12% to short Pro RWD and 1,800 kg to short 4MOTION; the late-model
October French sheet confirms the same assignments in its p. 32 table. Select
1,200/1,800 from the Swedish technical table, preserving the conflicting
configurator evidence. Prefer the explicit Swedish drive breakdown and avoid
overstating the RWD limit. Add this specific disagreement to the eventual
publish adapter's tests, and revalidate it on source refresh.

For charging, the [official French MY2027 technical sheet][charging-fr],
updated 21 October 2026, p. 8, gives 11 kW AC and 183 kW DC for both exact
codes `EBBR7R` and `EBBR5R`, with the same 79 kWh net and 210/250 kW motors.
The original three-source review treated its 183 kW as the more exact value.
The later Finnish exact-code corroboration below supersedes that provisional
choice for the Swedish packet. The Swedish configurator's battery tab
does not give a vehicle maximum. Do not confuse charging test conditions with
vehicle limits. The French source may support charging hardware only, never
Swedish price, trim, seating, WLTP figures or availability. It is not a source
for French-market data in the public catalog either.

`node scripts/run_python.mjs scripts/volkswagen_id_buzz_preflight.py --capture-charging`
captured the manufacturer's cover and exact table with source hashes, pending
review, under `data/local/release-data/volkswagen-id-buzz-charging-qlue0s8x/`.
The guard excludes long wheelbase, wrong codes and columns and changed limits;
only the two charging fields are carried out of the French table.

### Automated Swedish technical checks

The fresh 19 November capture (`volkswagen-id-buzz-pju7i2df`) returned HTTP 200
for both Swedish sources. The preflight now requires the named drivetrain
columns and the short, braked 12% towing entries; those entries must agree
with the Swedish model cards. It also binds the 2,989 mm diagram to the model
FAQ's volume behind row two. Long-body, folded-seat and unbraked figures do
not qualify.

| Short, five-seat trim | Swedish braked towing at 12% | Cargo behind row two |
| --- | ---: | ---: |
| Pro RWD | 1,200 kg | 1,121 L |
| Pro 4MOTION AWD | 1,800 kg | 1,131 L (exact five-seat card) |

The [Swedish model FAQ][model] states 185 kW peak for the 79 kWh battery. The
[Finnish importer table][charging-fi] dated 18 June corroborates 185 kW for
both exact short, five-seat codes and lists 11 kW AC for the relevant grades.
Use the Swedish 185 kW value in the private candidate, not a rounded 183 kW.
Keep the October French 183 kW figure as an explicit competing claim; the
sources do not establish why it differs. The French and Finnish sources both
support 11 kW AC. Foreign price, WLTP and trim values are not carried over.

The [Swedish edition page][edition] and configuration summaries show cash
starting prices with VAT, but do not identify ordinary list prices or an
importer-wide campaign expiry. [Moller Bil's exact offers][dealer] publish the
same 589,900/625,900 SEK for the two five-seat versions through 31 December
2026. [Volkswagen's dealer profile][dealer-auth] confirms authorization.
The packet therefore selects `dealer_offer` with the named dealer and expiry;
it does not apply that expiry nationwide or to all Volkswagen prices.

### Private dry run

Run the configurator capture first, then replay its raw hashed evidence:

```powershell
node scripts/run_python.mjs scripts/volkswagen_id_buzz_review.py --configurator <fresh-private-capture> --photo <reviewed-local-original> --include-market
```

The 19 November run (`volkswagen-id-buzz-review-4vgnydjf`) re-read both exact
configurations, fetched six source documents, and created two nine-field
profiles. All six saved text hashes matched on readback. No database write,
new public variant, or AI call occurred. A replay rejects stale/missing access
receipts, changed raw files, and saved facts that differ from reparsing.

### Isolated insertion test

`bun run verify:id-buzz-local-publication` tests the new local-only adapter with
synthetic captures. To replay the actual archived configuration and source
captures, substitute a verified private review folder:

```powershell
node scripts/verify_id_buzz_local_publication.mjs --review <captured-review-directory> --readback <its-private-readback-json>
```

Both modes use in-memory PGlite and the real source and price schema constraints.
Use `--include-market` on the review command to include the official October
workbook instead of a simulated market import. It was retrieved again in
`volkswagen-id-buzz-review-27qhu1ug`: exactly `VW | ID. BUZZ | EL`, 147 October
registrations and 910 YTD. The workbook's SHA-256 is checked before the replay.
The receipt's time is used for local replay, not asserted to be fresh production
evidence. The test checks two exact
versions, eight sources, actual source countries and authority, separate price
evidence, competing charging and towing values, unchanged Toyota rows and
historical market data, rollback, idempotent replay, and rejection of altered
source metadata. The adapter cannot run through the production CLI or on a
remote client. Kia and Toyota still require Swedish manufacturer sources.

Before any production insertion, re-fetch the exact source evidence, read the
canonical model/alias and market history afresh, and check the selected
transaction separately. Do not reuse the simulated market import for launch.

### Read-only production preparation

Use a freshly captured packet that includes the official market workbook and
references the original configurator capture in the same evidence root:

```powershell
node scripts/prepare_id_buzz_readback.mjs --review data/local/release-data/volkswagen-id-buzz-review-rmhix6j3
```

The 19 November check saved `volkswagen-id-buzz-readback-ReczFp/readback.json`
under the ignored evidence directory. The two-version plan matched the real
ID. Buzz draft, exact raw alias, and one existing March historical row. No
existing variant, draft, or registered source conflicted. The ordinary PGlite
test also verifies that the preparation refuses a writable connection, an
existing duplicate draft, and an already populated model.

The hash is review evidence, not an apply token. The recorded evidence window
ended at `2026-11-19T19:41:45.622Z`. The command accepts no write/apply option,
requires a repeatable read-only transaction, checks the expected artifact
hashes, and leaves the production connector disabled for the ID. Buzz writer.
The second 19 November check saved `volkswagen-id-buzz-readback-V8AYOf/readback.json`.
It re-parsed the two original configurator captures and cross-checked every
reviewed range, consumption, cash-price corroboration and towing alternative
against the actual configuration identity, value and quote. The earlier
packet predates this requirement. The second check confirmed no collisions,
preserved March history and expired at `2026-11-19T20:21:09.202Z`.
Run a fresh capture and repeat the readback when preparing an approved release.

### Ready for separate release review

The final 19 November rehearsal used fresh public configurator capture
`volkswagen-id-buzz-configurator-U6xOJy`, the six re-fetched sources and actual
Mobility workbook in `volkswagen-id-buzz-review-oandb5a5`, and the scoped
production readback `volkswagen-id-buzz-readback-Gu3tC3/readback.json`. The
readback was checked as a repeatable read-only transaction; its short
apply-freshness window ended at `2026-11-19T21:01:11.074Z` and is not renewed by
local replay.

`--readback` recreates the actual model/alias/market/source scope in in-memory
PGlite and checks the exact plan before any local insertion. It installs the
real catalog view, vehicle-access and price-contract migrations. Both variants
were visible through the local anon view with the exact photo, named dealer,
offer price type, selected braked towing and WLTP. Staging stayed inaccessible
to anon. Late rollback, replay and collision checks passed; March history and
three unrelated C-HR+ fixture rows stayed unchanged.

Release reviewer: approve or reject the two short five-seat MY2027 profiles,
dealer offer and source-choice qualifications above, and the licensed model
photo. For a later approved production release, re-fetch and recheck the exact
sources and production scope, separately review the production connector and
transaction boundaries, and run exact-main CI before distribution. The current
adapter is intentionally local-only: no production apply token, remote writer,
canonical change, paid call or deployment was made.

### 20 November release preview

`volkswagen-id-buzz-configurator-G5e4lK` captured both exact configurations.
`volkswagen-id-buzz-review-1lwatyrp` re-fetched the technical and dealer sources
and October workbook. The read-only production check
`volkswagen-id-buzz-readback-Qr5SR8/readback.json` reproduced the draft, exact
alias and untouched March history. It was fresh until `2026-11-20T06:03:40.994Z`;
that timestamp is not a release approval and must not be extended locally.

| Short five-seat version | Cash offer, SEK incl. VAT | Exact configuration WLTP | Selected Swedish braked towing |
| --- | ---: | ---: | ---: |
| Pro RWD Sweden Olympic Edition MY2027 | 589,900 | 452 km | 1,200 kg |
| Pro 4MOTION Sweden Olympic Edition MY2027 | 625,900 | 416 km | 1,800 kg |

Both are named Moller Bil offers through 31 December 2026, not list prices.
The display distinguishes the offer, seller and end date. The 79 kWh net
battery, actual onboard AC, configuration-specific WLTP and towing basis are
qualified on the details page. The image is the licensed short-body Pro model
photo, not a picture of the advertised trim. Refresh or withdraw the offers
before their validity ends; taking a new screenshot does not refresh a price.

The isolated rehearsal exports `id-buzz-preview-catalog.json` beside the
private readback only after the local transaction, ACL, rollback and replay
checks pass. It adds exactly two rows from the **local** anon view to the
unchanged catalog export and never edits `public/data/public_ev_variants.json`.
The browser test uses only the local build and supplied catalog; it blocks API
and external requests. It checks the two detail pages at 320, 390, 768 and
1440 px, the comparison, the 1,500/1,801 kg advisor boundaries, the photo and
credit, and the separately sourced offer and expiry.
The final production build and all eight browser checks passed. The private
`volkswagen-id-buzz-ui-w0nn3z/report.json` and its four screenshots correspond
to `id-buzz-2026-11-20-final-build`. Intake, publication, catalog, image,
price, stable slug and release-guard tests also passed locally. No CI run on a
merged release commit or deployment has been performed.

```powershell
node scripts/verify_id_buzz_local_publication.mjs --review <review> --readback <readback.json> --preview
node scripts/verify_id_buzz_ui.mjs --catalog <id-buzz-preview-catalog.json> --build <private-vite-out-dir>
```

Still required: explicit release approval for these two variants. Keep the
current worktree's unrelated changes out of the release, re-fetch and compare
the exact sources before any write, review the model-specific production path,
then require exact-main CI and verified public readback before calling it live.

### Isolated release candidate

The candidate was separated from the pending work on base
`3dd625e616f15f9fb01cd933a5706c4a924ac257` (remote main at review time).
It includes neither the news, advisor nor Inster changes, and has no new public
catalog export. Tests against the isolated candidate passed: 15 Python intake
tests, 8 configurator tests, the local transaction, publication guard, price,
image, public view and database access checks, and the Vite production build.
The private browser report `volkswagen-id-buzz-ui-PTqJIS/report.json` records
the eight viewport checks, comparison and towing filters for the same build.
This is local release-review evidence, not an authorization to publish.

### Owner-approved release path

The 20 November approval covers only the two short five-seat MY2027 variants.
The new-model command still refuses this pilot by default. Its explicit
ID. Buzz release mode requires the approved readback hash, a freshly replayed
review and an unchanged canonical baseline. `--prepare-only` uses the existing
TLS-verified database connection in a read-only transaction and checks the
exact scope without writing. Before committing, the serializable transaction
also verifies both rows and their images, specifications and dated dealer
offers as the anonymous role. A failed check rolls back both variants.

Verify PR CI before invoking the write mode. After a successful commit, export
only the two added public-view rows, checking all preexisting rows against
the checked-in baseline. If the post-commit export fails, inspect the local
receipt and use `--export-only`; do not repeat the database mutation. The
final catalog commit must pass PR CI and current-main CI before triggering the
existing production distributor. Verify HTTPS, both routes, the model photo,
the exact prices and towing values after distribution. No AI calls or changes
to news configuration are required.

### Photo review

The original [short-body ID. Buzz Pro photo][photo] was downloaded privately,
matched to Commons' SHA-1 and visually inspected: correct passenger model,
front three-quarter view, full vehicle and plate already obscured in the source.
It is not an Olympic Edition or press image. Credit `M 93 / Wikimedia Commons`
and link [CC BY-SA 3.0 DE][photo-license]. Use only as a model image with a
notice that the shown equipment may differ. Preserve the full frame and license
when deriving responsive copies. The exact original and responsive derivatives
are registered in the local image inventory as a licensed model photo. The
regular image sync excludes this reviewed asset until ID. Buzz is public.
Original SHA-256: `00832a4a6a37ac1f8f88f2d2ea3a02ba3127638529184f517be224930e0f3f7d`.

No production collector or publisher has been enabled. No Toyota, EX90 or
production data changed.

[model]: https://www.volkswagen-transportbilar.se/sv/modeller/id-buzz.html
[edition]: https://www.volkswagen-transportbilar.se/sv/modeller/id-buzz/sweden-olympic-edition.html
[dealer]: https://mollerbil.se/erbjudanden/id-buzz-pro-sweden-olympic-edition
[dealer-auth]: https://www.volkswagen-transportbilar.se/sv/om-oss/transportmagasinet/foretag-och-forare/anpassa-transportbilen-efter-dina-behov.html
[technical]: https://www.volkswagen-transportbilar.se/sv/modeller/id-buzz/tekniska-data.html
[prices]: https://www4.skatteverket.se/download/18.64a0fae61a0b0a256b5c1c7/1794213825391/SKVFS%202026_13.pdf
[config-pro]: https://www.volkswagen-transportbilar.se/sv/bygg-din-bil.html/__app/72006/edition/pro.app
[config-awd]: https://www.volkswagen-transportbilar.se/sv/bygg-din-bil.html/__app/72006/edition/pro-4motion.app
[charging-fr]: https://www.volkswagen-utilitaires.fr/idhub/content/dam/onehub_nfz/importers/fr/documentation/fiches-tarifs/Tarif_ID_Buzz.pdf
[charging-fi]: https://api.k-auto.fi/priceCatalog/api/PriceCatalog/d1c60397-8685-48d3-b954-e08eb0b50361
[photo]: https://commons.wikimedia.org/wiki/File:VW_ID._Buzz_Pro_%E2%80%93_f_25012026.jpg
[photo-license]: https://creativecommons.org/licenses/by-sa/3.0/de/deed.en
