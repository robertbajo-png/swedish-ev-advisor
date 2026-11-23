# EU CoC cross-market research

23 November 2026. `scripts/ev_ecoc_source_review.py` examines the public
[ASTRA eDatenblatt][astra] export. It selects only technical fields from
the named Volvo EX90 and BMW iX xDrive45 battery-electric passenger-car
cohorts. It groups identical technical rows, does not retain VINs or raw
rows, and does not write to the catalog. The exact combined pure-electric
WLTP fields are distinct from city range and older generic range fields.
Tests cover duplicate or missing headings, separate wheel/energy pairs,
no identifier retention and partial input.

The whole 871,362,543-byte export exceeded the six-minute capture
limit and produced no report. The explicit 16 MB offset mode verifies
the exact response bounds and uses the same ETag for the header and data.
It records header/data hashes and `full_scan: false`; a sample cannot
show that an unmatched configuration is absent from the source.

The samples at the tail and offset 840,000,000 had no matching entries.
The targeted sample at offset **690,000,000** found 15 iX xDrive45
records and 37 EX90 records, grouped into 35 complete technical rows.
The BMW 20-inch records are 586-600 km, 179-184 Wh/km and span different
certified versions and masses. None confirms A20B's 602 km / 178 Wh/km
pair or identifies the Swedish option set. The Volvo results are older
300/380 kW, two-axle variants, not the reviewed 245 kW Single Motor
or the latest 800 V Twin variants. Keep all Swedish holds.

The [EEA 2025 provisional dataset][eea] corroborates Swedish BMW
xDrive45 type `BMWi-N`, variant `41CF`, approval
`e1*2018/858*00109*07`. It reports multiple consumption values across
versions `0AA5A000` and `0AB5A000`. It does not tie a WLTP pair to
the current Swedish A20B configuration. In that export `Erwltp (g/km)`
is not vehicle electric range. No registry value filled a catalog field.

[astra]: https://opendata.astra.admin.ch/ivzod/3000-eDatenblatt/
[eea]: https://sdi.eea.europa.eu/catalogue/srv/api/records/b4044b06-2e6b-4f8e-a6e6-66e0e98bb0dd?language=eng
