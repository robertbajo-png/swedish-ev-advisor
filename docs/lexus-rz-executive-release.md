# Lexus RZ 350e Executive

The scoped addition is the current Swedish FWD Executive: configurator
car `d032f909-69f8-45ea-bc22-7c6161ca2105`, type `XEBM20L-AWDCSW`,
suffix `AB`, standard 18-inch wheels. Neither the heading nor the
saved variant identity claims a model year. The Swedish family-level
year and foreign brochures do not prove the year of this configuration.

| Field | Verified value |
| --- | --- |
| Manufacturer starting price | 599,000 SEK |
| WLTP combined range and consumption | 567 km; 14.5 kWh/100 km |
| Battery | 77 kWh gross |
| Maximum DC / standard AC | 150 kW / 22 kW |
| Rear cargo / braked towing | 586 L to the luggage cover / 750 kg with towing equipment |
| Seats / drivetrain | 5 / FWD |

Use the exact Swedish configurator figures, not the model-page range
maximum, a foreign market's consumption, or a monthly payment. The
[Swedish model page][model] and independently fetched price PDF agree
on the starting price. The scoped Danish configuration and Norwegian
technical sheet corroborate the same 150 kW charging hardware; Swedish
pricing and WLTP are never inherited from there. The reviewed Swedish
handbook corroborates the selected configurator's towing figure.
Mobility Sweden's 50 October registrations and 439 YTD belong to the
RZ model only, not this grade or a specification record. Keep the
other two private RZ variants out of this transaction.

The [CC0 model image][photo] is a 350e Version L in Japan, credited to
TTTNIS. It must not be presented as Swedish Executive equipment.
The original stays unchanged, with three full-frame responsive sizes.

## Private Rehearsal

Collect the established Swedish source bundle with
`lexus_rz_review.py --capture --with-technical-specs`, then collect
the exact Nordic configuration and qualify its charging proof using
`lexus_rz_nordic_crosscheck.py`. The release intake also needs the
hash-pinned Swedish manual and the verified October workbook packet.
Pass those five packets to `lexus_rz_release_intake.py` and use its
recorded folder:

```sh
node scripts/verify_porsche_macan_local.mjs --lexus --fresh <private-intake>
node scripts/verify_hyundai_inster_advanced_ui.mjs --lexus --readback <local-result>
node scripts/run_python.mjs scripts/verify_hyundai_inster_advanced_static.py <ui-result> --lexus
node scripts/prepare_hyundai_inster_advanced_release.mjs --lexus --readback <local-result> --ui <ui-result>
```

The scoped publisher requires the exact tested main and deployed reader,
an unchanged anonymous baseline, all four verified image files and
freshly recaptured sources. Keep the staged and verified private
catalogs out of the public export. Only the post-commit anonymous
readback is eligible for the single-model catalog update.

[model]: https://www.lexus.se/new-cars/rz
[photo]: https://commons.wikimedia.org/wiki/File:Lexus_RZ350e_Version_L.jpg
