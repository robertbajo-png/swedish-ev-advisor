# Catalog Expansion With Complete Profiles

Owner request: 15 November 2026. Continue vehicle completion, defer new SEO
work, and plan broader coverage without repeating incomplete/incorrect imports.

## Current Baseline

- Supabase/Postgres remains canonical; the public snapshot is an export of
  validated public views, never a replacement authoring database.
- Released baseline: 30 models / 76 variants, 48 variants with all nine core
  technical fields after EV6. Existing prices and image evidence need their
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
| 1. EV9 completion | Database committed; release checks pending | Four exact existing versions,11 gaps filled, independent November price evidence refreshed with no amount changes. Guarded transaction and local responsive/accessible UI checks pass. Canonical total52/76 technically complete. CI/production verification pending; no new-model release implied. |
| 2. Fresh expansion scope | Planned | Import latest accessible monthly passenger-BEV export through the existing Mobility importer. Preserve raw names/month/source hash. Select ten new identities by YTD, latest month, recency, then source readiness; five per batch. Ambiguous groups remain mapping tasks. |
| 3. First five-model pilot | Planned | Official Swedish model/technical/price sources, exact variant matrix and complete release packets. Dry run, isolated SQL tests, current-source recheck, scoped transaction, anon readback, build and real-page/image QA before release. |
| 4. Second five-model wave | Planned | Reuse passing adapters/contracts; five more NEW models, not a lower quality threshold. Investigate failures independently; one blocked source must not stop other candidates. |
| 5. Repeatable operation | Planned | Reuse source discovery, hash/change queues and scoped refresh commands. Scheduled discovery/preparation is separate from canonical writes and deployment. Verify freshness, rights, rollback and run logs before enabling any new write schedule. |

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

Finish phase 1, then refresh phase 2's actual market export. Select the first
five research candidates from that fresh queue, preferring adapters/brands
already supported. Target ten additional complete models in two waves, then
review coverage before pursuing the remainder of ranks 31-60. Dates depend on
source availability; missing evidence is not permission to lower the release gate.
