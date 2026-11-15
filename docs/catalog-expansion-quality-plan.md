# Catalog Expansion With Complete Profiles

Owner request: 15 November 2026. Continue vehicle completion, defer new SEO
work, and plan broader coverage without repeating incomplete/incorrect imports.

## Current Baseline

- Supabase/Postgres remains canonical; the public snapshot is an export of
  validated public views, never a replacement authoring database.
- Current released baseline:31models/79variants,55variants with all nine core
  technical fields after the EV2 pilot. Previous EV9 baseline was30/76 and52
  complete. EV2 release was verified15November18:03UTC. Prices and image evidence need their
  own freshness/rights checks; technical completeness alone is not release-ready.
- The existing expansion runner uses legacy seed/state files and a broad seed
  postprocess. Do not run its write/sync mode against production for this wave.
- The retained Mobility Sweden file describes March 2026, not today's market.
  Its ranking is useful for research only until a newer dated export is imported.
- Count NEW canonical model identities, not trim rows, pictures or existing
  models rediscovered under another name. Retain current public models/URLs.

## Phased Execution

| Phase | Status | Output and exit condition |
| --- | --- | --- |
| 0. Inventory | Complete | Tested read-only preflight against the current public snapshot:30models/76versions,24 research candidates from ranks31-60, three mapping holds. All24 require a newer market export. Never described as source-ready or publication-ready. |
| 1. EV9 completion | Complete | Four exact existing versions,11 gaps filled, independent November price evidence refreshed with no amount changes. Guarded transaction,178 PR CI steps,178 exact-main steps and production checks passed. Deployed through PR73/run43737114773, verified15November16:45UTC and16 real responsive pages. Total52/76 technically complete; no new-model release implied. |
| 2. Fresh expansion scope | Research prepared | Official October workbook fetched and parsed privately:135 BEV rows. Within current ranks1-60,17 matched not-yet-public candidates and14 raw mapping holds. Raw workbook hash and dated report retained. No production market/model writes. Reconcile aliases and preserve historical months before promoting this index. |
| 3. First five-model pilot | 1/5 released; C-HR+ committed/local QA passed | EV2 is live through PR74. C-HR+ adds three complete source-bound profiles; anonymous catalog32/82 and all79 old records unchanged. Local build/12 responsive views/advisor/comparison/Axe checks pass; C-HR+ CI and actual release remain. Three later pilot models need their own evidence packets. |
| 4. Second five-model wave | Planned | Reuse passing adapters/contracts; five more NEW models, not a lower quality threshold. Investigate failures independently; one blocked source must not stop other candidates. |
| 5. Repeatable operation | Planned | Reuse source discovery, hash/change queues and scoped refresh commands. Scheduled discovery/preparation is separate from canonical writes and deployment. Verify freshness, rights, rollback and run logs before enabling any new write schedule. |

### Fresh Scope And Proposed Batches

The official October2026 workbook was obtained on15November from
[Mobility Sweden's November2 release](https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober).
Its SHA-256 is
`1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6`.
Keep the old March capture as history, not the current ranking. Fresh reports
and workbook remain in ignored `data/local/release-data/catalog-expansion-2026-11-15/`.
After EV2, a separate post-pilot report retains16 matched research candidates
and14 raw mapping holds in current ranks1-60. These are not source-ready models.

- Proposed pilot: Kia EV2, Toyota C-HR+, Volvo EX90, Volkswagen ID. Buzz, MG4.
- Proposed second wave: CUPRA Tavascan, XPENG G6, Hyundai Ioniq 5, Lexus RZ,
  Renault 4. Reorder if actual official-source readiness supports another choice.
- These are research priorities, not five approved exact variants. Mercedes
  GLB and other ambiguous generation/alias identities need explicit EV identity
  resolution before joining a release batch. Fourteen held raw rows also include
  already represented model groups; they are not fourteen new missing models.
- Start with two or three useful, independently evidenced versions per model
  where offered: entry, long-range and AWD. Do not fabricate such versions or
  mix their specs to meet a portfolio template.
- Existing-model completion continues separately; the remaining older catalog
  gaps do not block releasing a genuinely complete new model.

### Required Before Any New-Model Write

The completion transaction only updates existing versions; migration011 inserts
only exact Toyota identities. Neither is a generic new-model publisher. Before
phase3 writes, implement/test a scoped stage-to-canonical insertion adapter using
existing database utilities and safeguards, not an expanded Toyota exception or
the legacy bulk reseeder. Bind expected model/variant identities, evidence hashes,
alias decisions and photo evidence to one prepared batch; require fresh readback,
idempotence, collision rejection, whole-batch rollback and preserved unrelated rows.
Any necessary migration/permission change is a separate reviewed step, not implied
by this plan. No such schema or permission changes were made for EV9.

Monthly market promotion must merge history: preserve earliest first_seen_month,
store each brand/model/month once, retain source URL/hash and only compute12m
registrations when all required months exist. The single-month importer is not
proof of twelve months of history and must not reset old first-seen dates.
Set last_seen_month from actual positive monthly registrations, not merely a
new workbook containing a zero-registration row. Keep report_month/source age
separate from observed activity and from manufacturer-confirmed orderability.

## Correct From The Start

Every proposed new variant needs a source-bound identity packet:

1. Brand, canonical model, body/generation/model year, trim, motor/engine ID,
   battery, driven axles, seating and wheel/equipment scope. Alias rules must
   resolve to this identity; never assemble a model's cheapest price with its
   longest-range motor. GT is not GT Line; six seats are not seven.
2. All nine technical fields: WLTP range, combined consumption, battery capacity,
   DC peak, actual onboard AC, braked towing, rear boot with seats upright,
   seats and drivetrain. Also source the model body type. Store conditions and
   units: WLTP vs EPA/CLTC, city vs combined, net vs gross, optional vs standard,
   seats-up vs folded/frunk, estimated vs homologated. Do not silently convert
   a target or rounded charger rating into a certified specification.
3. Independent current Swedish price evidence: exact variant, VAT-inclusive
   cash price, list/campaign/dealer classification, original date and expiry
   when published. A leasing payment is never a vehicle price. Manufacturer
   list prices take precedence; dealer offers remain visibly separate.
4. Per-field URL, actual content hash/fetch timestamp, literal quote/page/table
   header, normalized value and extraction method. Deterministic parsing first;
   strict AI extraction only when necessary and within a separately available
   budget. AI confidence >=0.92 is necessary, never sufficient.
5. Exact-model professional image with source, license/permission, credit,
   full-frame/hash-bound derivatives and visual identity review. Use a visible
   equipment notice for a model photo that is not the exact trim. A missing or
   wrong image blocks this wave's photo-ready acceptance, not another-car fallback.
6. Separate Swedish market presence and current orderability evidence. A BEV
   registration proves neither current availability nor the individual variant.

Official Swedish manufacturer/importer evidence is primary. Authorized Swedish
dealers need independently saved appointment evidence and exact-version facts;
no generic listings/comparison sites. Exact-version official European technical
supplements may resolve a genuinely shared hardware fact only with an explicit
country/scope decision and regression test, as in the existing completion
adapters. Never import foreign prices or claim Swedish availability from them.

Conflicts are resolved by exact generation/year/version, final technical scope,
date and source authority. Keep alternatives and the selection reason in staging.
Unresolved facts stay a research task in quarantine, not a fabricated completion.

## Release Gate For New Models

The existing minimum public-data contract (price OR range) stays unchanged for
backward compatibility. This expansion wave deliberately has a stricter
acceptance checklist: all nine fields, sourced body, current exact Swedish price
and approved photo. Missing/unannounced prices or specifications defer a new
candidate; do not hide existing models or invent placeholders to pass the gate.

- Staged packet -> hard bounds and identity/unit/price/image checks -> isolated
  rollback/replay/concurrency tests -> fresh fetch -> narrow canonical transaction.
- Preserve old IDs/routes, prices outside scope, source history, news and controls.
  No bulk production reseed/reset or wholesale seed-to-Supabase overwrite.
- Verify through anonymous public views that only the approved rows changed.
- Test catalog/advisor filters, decimal AC, compare, missing/zero semantics,
  320/390/768/1440px geometry, source credits and actual image decoding.
- Build and CI on the exact main commit before existing production distribution;
  check HTTPS, deployed catalog hash and real detail pages afterwards.
- A batch report names discovered, source-ready, fully validated, quarantined,
  database-committed and actually deployed counts separately. No quota publishing.

## First Useful Automation

`scripts/plan_catalog_expansion.py` produces a read-only, dated research report
using the CURRENT published snapshot, not the legacy variant seed. It ranks
market rows, excludes already public canonical identities, identifies stale
market evidence and unresolved aliases, and counts current technical gaps.
Its queue is NOT publication approval or proof of source readiness. Reports stay
under ignored `data/local/`; it makes no network/AI/database calls.

The retained research list includes ID. Buzz, EX90, iX, MG4, Polestar 3, Lexus RZ,
C-HR+, G6, Inster and Ioniq 5. These are candidates, not a confirmed November
ranking or an automatic promise to import all their variants. Phase2 must
revalidate the order and exact current Swedish versions before choosing five.

Run:

```powershell
node scripts/run_python.mjs scripts/plan_catalog_expansion.py
```

## Next Concrete Task

### EV2 Pilot Execution

| Slice | Status | Verification required |
| --- | --- | --- |
| Schema and source inspection | Complete | Existing EV2 canonical draft and deterministic alias exist; no variants. Swedish September29 technical PDF, current November prices and 6N/W5/W4 engine table found. |
| Source-bound extraction | Complete | Three exact five-seat engines: base SR16inch, base LR16inch, GT Line LR19inch; all nine facts, separate prices and a reviewed professional exact-model press photo. Ten extraction tests pass. |
| Safe new-version transaction | Committed and read back | Fresh official sources; three canonical/staging rows, three model sources and EV2 October market merge only. Private receipt saved;76 old public records, aliases, historical March month, shared sources and news unchanged. No migration/bulk seed. |
| Local and CI verification | Complete | New extraction/publication/photo tests, image/public contracts and93-route production build pass.181 PR CI steps and181 exact-main steps pass.12responsive detail views, two Axe audits, exact-photo decode, advisor, filters/picker and three-way comparison pass locally and on production. |
| Production release | Complete | PR74/main2c602ea5e06511e7007da9e23732963f89ac223f; existing production distributor43744379952. Actual HTTPS,79-row catalog, exact-photo hash and all three initial metadata pages verified2026-11-15T18:03:44Z; responsive production checks also pass. |

Toyota C-HR+ now has a separate registered adapter,27 technical facts, three
current Swedish list prices and a reviewed exact-model professional photograph.
Guarded canonical insertion and local regressions pass. Finish its exact-main CI,
existing production distribution and actual-site readback before marking2/5 live.
The existing normalizer drops the plus sign: do not confuse C-HR+ EV with C-HR
hybrid based only on the normalized key. Require exact raw alias/electric model
identity before adapting insertion. Then continue EX90, ID. Buzz and MG4 as
source-ready evidence permits. EV2 approval does not preapprove these models.
Target ten additional complete models in two waves, then
review coverage before pursuing the remainder of ranks 31-60. Dates depend on
source availability; missing evidence is not permission to lower the release gate.
