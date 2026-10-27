# Release Progress: Images, Prices And Privacy

2026-10-27. Full release is still blocked; this is not a launch certificate.

## Completed

- Preserved all 30 public models and 67 public variants.
- Replaced all 30 model images with visually reviewed, locally served CC images,
  including author/licence/source attribution, revision evidence and byte hashes.
  The audit covers 31 distinct vehicle/CSS uses, all documented, none pending.
- Synced only canonical image fields in one scoped transaction. Variant facts
  were unchanged, and news AI/publication remained off.
- Added deterministic, exact-row Kia Sweden price extraction. Cash-price column
  identification is separate from leasing. Uncertain versions do not receive a
  new date simply because a model page is reachable.
- Updated seven existing variants, preserving technical facts/hashes/dates and
  canonical identity. Price evidence has its own source/hash/quote/date.
- Documented the owner's approved privacy purposes, legitimate-interests
  assessment for abuse protection and 90-day closed-contact retention policy.
  No mailbox deletion automation, new supplier agreement or privacy flag was
  silently enabled.

## Applied Kia Price Evidence

Official source: <https://www.kia.com/se/kopa/prislista/>.
Fresh source SHA-256:
`aa368ae0f5ccc40d00f227f85237c45a45f82120885732da9a2ea644258b7a2b`.
Applied plan:
`bb207d09741cebb3614253e377ef5e05952be8f12c3b7526f1e2933c68a0ac22`.

| Existing canonical variant | Exact source version | SEK incl. VAT |
| --- | --- | ---: |
| EV5 FWD | EV5 FWD Long Range | 554900 |
| EV6 AWD | EV6 AWD Long Range | 631400 |
| EV6 RWD | EV6 RWD Long Range | 596400 |
| EV6 GT | EV6 GT (650hk) AWD Long Range | 771400 |
| EV9 AWD | EV9 AWD 7-SITS Long Range | 819900 |
| EV9 AWD GT Line 6-sits | EV9 GT Line AWD 6-SITS Long Range | 909900 |
| EV9 AWD GT Line 7-sits | EV9 GT Line AWD 7-SITS Long Range | 889900 |

All seven are recommended cash/list prices, not leasing or campaign values. The
old GT Line figures had matched GT pricing instead; those were corrected rather
than rubber-stamped. No generic EV3/EV4 or ambiguous EV5 AWD mapping was published.

## Verification

- Production frontend build passed.
- Model-image transaction fixtures passed, including rollback, exact scope and
  non-image/variant preservation.
- Kia price transaction fixtures passed, including stale/concurrent data,
  independent evidence revalidation, wrong trim/price rejection and rollback.
- Four licensed-image tests, four existing rights tests, four Kia row tests and
  four site-information tests passed.
- Public catalog, separate price-evidence and exact-image contracts passed.
- PostgreSQL/PGlite access checks passed 84 denied operations; read-only remote
  access verified all seven internal vehicle tables denied to the anonymous role.
- Responsive proportions passed all 24 layouts, 320px through 1440px.
- Homepage, vehicle and price-evidence browser suites passed. Null and explicit
  zero remain distinct; failed or unknown images never become another car.

An earlier UI run correctly failed its frozen-export assertion because the
operator's price export occurred during that run; it was not recorded as a pass.
An older missing-image fixture assumed Audi had no image. It now explicitly tests
a failed image request and a nonexistent model instead of relying on live catalog
gaps. No production data was changed to satisfy those UI tests.

## Remaining Release Gates

- 15 price-bearing variants now have current evidence; 37 still require genuine
  verification. Some are trim identity conflicts, not just expired timestamps.
  Examples: generic EV3 base price versus Long Range WLTP; old Toyota MY23 price
  documents; Renault finance/service bundles; renamed Polestar/Skoda versions.
- The image-rights review is complete and its local release flag is true.
- The owner's privacy policy is documented, but provider/project account binding,
  applicable contractual/transfer arrangements and the actual Gmail product
  review remain unresolved. Chrome's provider tab could not be attached; this is
  not evidence that an account review succeeded. Privacy release flag stays off.
- DNS/custom-domain and open indexing remain deferred until the gates genuinely
  pass. No passwords, news switches, monetary ceilings or DNS were changed.

Paid AI calls and new article publications in this work: **zero**.
Next task: exact-variant/source remediation for the remaining 37 price records,
not date refreshes or release-gate exceptions.
