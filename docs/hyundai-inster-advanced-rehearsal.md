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
No photo has been registered for live Inster use here.

The October Mobility Sweden workbook is used only for the existing
resolved BEV alias and market history. It is not spec or price evidence.

```sh
node scripts/verify_hyundai_inster_advanced_local.mjs --intake <fresh-private-packet>
```

The isolated checkout can specify the original workspace's read-only
connector with `--client-module`. The fresh private packet is assembled
from local source tools and verified raw receipts. Its three Swedish
factory queries can now be captured independently of any saved request
templates: run `node scripts/capture_hyundai_inster_advanced_factory.mjs`
and use `--replay <saved-factory-packet>` to verify the resulting bytes.
The remaining source assembly still depends on local tooling, and the
private packets are never checked in. The verifier reads the live baseline, closes the read-only
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
```

Chromium verified 320, 390 and 1440 px, with the whole photo above the text on
mobile, a visible Prime image qualification and the licensed credit. It
displayed the manufacturer's starting price without a fixed JSON-LD offer,
360 km, 85.3 kW DC, 10.5 kW AC and the explicit lack of towing capability.
The comparison flow also showed the exact DC and trailer values next to
Kia EV2. Screenshots and the UI receipt are stored only with the private
readback. The local browser server has no API access.

Production still did not have the verified decimal migration. No production
write, licensed photo upload or deployment occurred. Before release,
package the fresh capture and media in the normal release workflow,
then verify migration 027 and the exact scoped production write independently.

[photo]: https://commons.wikimedia.org/wiki/File:Hyundai_Inster_Prime_%E2%80%93_f_14022026.jpg
