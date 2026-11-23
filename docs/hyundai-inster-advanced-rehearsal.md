# Hyundai Inster Advanced Tech 17-inch MY27

The private adapter is limited to Swedish material `6XS5ZDZ7ZHH09P`.
Only the 49 kWh Advanced with 17-inch wheels and the Tech package is
in scope. Essential, the 15-inch Advanced, and Cross are not substitutes.

| Field | Accepted value |
| --- | --- |
| Manufacturer starting price including both packages, before optional paint | 377,900 SEK |
| WLTP, combined | 360 km |
| WLTP consumption | 15.1 kWh/100 km |
| Battery capacity | 49 kWh |
| Peak DC / on-board AC | 85.3 kW / 10.5 kW |
| Luggage, rear seats upright and farthest back | 238 L (up to 351 L slid forward) |
| Trailer | 0 kg; the manual explicitly prohibits towing |
| Seats / drive | 4 / FWD |

The proof preserves the exact Swedish factory requests and responses as
separate records, even though they share an API endpoint. Human-readable
links open the exact Swedish configuration, stock pricing, cargo design
page, owner's manual and the authorized dealer's seat evidence. The Hedin
photo is used only to corroborate the four seats. The [licensed Inster
Prime photograph][photo] is model-level, with credit and a trim notice.
The support branch registers the four reviewed image files, but does not
add the car to the public catalog.

The October Mobility Sweden workbook is used only for the existing
resolved BEV alias and market history. It is not spec or price evidence.

```sh
node scripts/run_python.mjs scripts/prepare_hyundai_inster_advanced.py --seat-photo <reviewed-private-rear-photo> --model-photo <reviewed-local-model-photo>
node scripts/verify_hyundai_inster_advanced_local.mjs --intake <fresh-private-packet>
```

The isolated checkout can specify the original workspace's read-only
connector with `--client-module`. The collector needs only the two exact
reviewed photos under `data/local/release-data` and the checked-in scripts;
it fetches the rest, including the current listing that ties the private
rear photo to the sold configuration. The dealer photo is not exported.
For the three factory queries separately, run
`node scripts/capture_hyundai_inster_advanced_factory.mjs` and use
`--replay <saved-factory-packet>` to verify the resulting bytes.
The private packets are never checked in. The verifier reads the live baseline, closes the read-only
connection, and exercises the shared insertion in a new in-memory PGlite.

On 23 November 2026 the old schema refused insertion before writing
any rows. Applying migration 027 only in PGlite preserved all existing
values, rows and permissions. The full transaction added one local car
to the 105-variant baseline. Staging, canonical and anonymous readback
all returned exactly `85.3`. The existing Inster registration month
survived, modified alias/asset/variant snapshots were refused, the late
rollback restored the baseline, and exact replay was a no-op.

The rehearsal writes its hash-bound candidate catalog only under ignored
`data/local/`, separate from the checked-in public snapshot. The reviewed
Prime original and full-frame responsive sizes (480, 800, 1280 px) were
staged privately, with no change to the public image registry.

The browser rehearsal uses the exact hash-bound readback and image packet:

```sh
node scripts/verify_hyundai_inster_advanced_ui.mjs --readback <private-readback> --photo <private-photo-packet>
node scripts/run_python.mjs scripts/verify_hyundai_inster_advanced_static.py <private-ui-output>
```

Chromium verified 320, 390 and 1440 px, with the whole photo above the text on
mobile, a visible Prime image qualification and the licensed credit. It
displayed the manufacturer's starting price without a fixed JSON-LD offer,
360 km, 85.3 kW DC, 10.5 kW AC and the explicit lack of towing capability.
The comparison flow also showed the exact DC and trailer values next to
Kia EV2. Screenshots and the UI receipt are stored only with the private
readback. The local browser server has no API access.

The static rehearsal against the new capture on 23 November used the
current public sitemap and news export. It produced 125 URLs, retaining
all 124 existing URLs including all seven news articles. Only the exact
Inster URL was added, with no fixed-price offer.

### Production schema prerequisite

Migration 027 was applied on 23 November from main
`a25f5da08c1cf7c222fb439a23817bf04ca64fd6`. The runner verifies the
view and private-table inventories before commit and validates numeric
storage again afterward. Its late-failure test proved rollback, followed
by an exact local application and a no-op replay. The live result
preserved 105 public variants and all prior private data. A separate GET
check confirmed 42 public models, 105 public variants and denied
anonymous reads on all seven private tables. The prior encrypted backup
artifact was present; this was not a new restore test.

No Inster row has been inserted in production. Before that write, verify
the exact reader/media release, recheck the fresh source bundle and bind
the scoped insertion to the approved catalog baseline.

The first production read-only preflight stopped before writes because the
private plan had passed through a driver that rounded timestamps to
milliseconds and read numeric alias confidence as text. Use PostgreSQL's
exact JSON row projection in both the Inster rehearsal and its locked
transaction. The rehearsal asserts equality with the untouched live rows
before it saves a plan. A regression verifies that timestamps differing by
one microsecond are still distinct; no tolerance is added to the write guard.

### Scoped insertion

Use the rehearsal on the migrated production baseline to save the private
plan and baseline. Bind its candidate to the browser and static receipts:

```sh
node scripts/prepare_hyundai_inster_advanced_release.mjs --readback <private-readback> --ui <private-ui-output>
```

A local repeat with `--reviewed-scope <private-scope>` and a new intake
exercises the exact scoped transaction only inside PGlite. The 23 November
run used a fresh manufacturer intake and the migrated production baseline:
105 prior variants were unchanged, one Inster appeared privately with
85.3 kW, the historic market month survived, and exact replay was a no-op.
The production
operator command `publish_hyundai_inster_advanced.mjs` first runs read-only
with the reviewed scope, fresh intake, current-main commit and push CI run,
and the deployed reader hash. It verifies all four live media files,
catalog equality and migration 027. Its check emits the scope seal; passing
that exact seal with `--commit-seal` permits one guarded insertion and a
private journal. Use `--export-journal` in place of `--fresh` for the
subsequent validated export. Neither command deploys the site or invokes AI.

[photo]: https://commons.wikimedia.org/wiki/File:Hyundai_Inster_Prime_%E2%80%93_f_14022026.jpg
