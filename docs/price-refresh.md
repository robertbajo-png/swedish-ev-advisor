# Price-Only Catalog Refresh

## Applied Status: 2026-10-27

Following the owner's continuation of the scoped operation, migration 020 was
installed in the existing Supabase project. Its exact reviewed SHA-256 is
`d14ea036e018782166879b03523254094f0de7ff0fb3adecdb2e9519430ddade`.
Only the existing official Skoda price-list record's missing authority was
classified as manufacturer; its technical hash, verification date and payload
were not refreshed. Canonical facts were checked unchanged after installation.

The official PDF was fetched again, and all four prices and the 2026-12-15 end
date matched the bounded expected matrix. Four private validated drafts were
published through the new atomic RPC in batch
`8a66ad79e948fc222666d8ee5157ddf3b984270079fbeccc34e2d6b93eba94ed`.
The exact price matrix below is now canonical, not just a fixture. The other 63
variants and all technical values, technical evidence, source verification
dates, market flags and prior review decisions are unchanged. Both ordinary
published and previously reviewed variants remain in their original status.

Independent read-only before/after checks confirm preserved ACLs and identical
news-table fingerprints, including budgets/usage receipts. News AI, article
publication and notice publication remain disabled. No paid AI call, budget
change, password change, news publication, DNS change or remote deployment took
place. Redacted installation/publication receipts and protected full comparison
snapshots are ignored under `data/local/release-data/price-release-2026-10-27/`.

The public canonical snapshot was synced from the public view: exactly four rows
changed, no model/variant was removed, and all new price columns are present.
There are still 30 models / 67 variants. Eight prices now have current evidence;
44 still require verification, down from 48. The pre-existing three-item local
review queue is retained. Privacy and image-rights release flags remain false.
This is not a production-site release or an updated external preview; pushing
the scoped code/snapshot through reviewed GitHub CI and preview distribution
remains the next delivery step.

## Scope And Plan

The owner chose to retain the complete launch catalog while verification is
completed. The release audit has 48 prices requiring recent evidence. Do not
hide those records, overwrite technical facts with price-only drafts, or make a
source's global verification date current after checking only a price.

This slice implements:

1. Separate canonical price URL, hash, quote, source name and verification date.
2. A private transactional publisher for the four exact Enyaq Solid Edition
   variants supported by the existing deterministic Swedish PDF adapter.
3. Local preparation by default; staging/publication only via explicit commands.
4. Public export, advisor context and UI support for separate price evidence.
5. Offline SQL/worker/consumer regression, build, SEO and responsive UI checks.

It does not authorize production DDL, source-registry changes, publication,
deployment, paid AI, news activation or a production-domain cutover.

## Data Contract

Migration `020_price_only_refresh.sql` adds these public view fields:

- `price_source_url`
- `price_source_hash`
- `price_source_quote`
- `price_source_name`
- `price_verified_at`

`price_refresh_batch_id` remains private on the canonical variant. Existing
public columns, view dependencies, ACLs and the RLS boundary are preserved.
Existing rows keep null price evidence; the migration does not change car facts
or mark any source verified. The fresh-install schema contains the same SQL.

The publisher updates only price, price classification, expiry and the separate
price-proof fields. It does not update `manufacturer_sources.verified_at`,
technical source/hash/quote, technical values, review status or market flags.
Other price writers invalidate superseded price-only proof automatically.

The public catalog exporter preserves existing snapshot hashes when the added
fields are absent/null. Partial or unsafe price proof fails closed. The release
check prefers the price-specific date when proof exists; a newer technical
verification cannot make stale or partial price evidence pass. UI and advisor
context retain the two sources separately, and old price quotes are not reused
as the updated vehicle summary. Static vehicle metadata exposes a separate price
source/date when available.

## Publication Guards

The first publisher is intentionally limited to the exact official URL
`https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660` and four known
Solid Edition variants. No approximate edition/variant aliases are accepted.
Requirements include:

- A reachable, fresh Swedish official PDF and recorded SHA-256.
- A classified manufacturer/importer registry entry for the same model.
- Four distinct existing published/reviewed variants, private validated drafts,
  confidence at least 0.92, source-bound row/column/edition/expiry evidence.
- A campaign price in the supported six-digit layout, nonexpired end date,
  no technical values in the draft, and price change no larger than 15%.
- Locked source/variant/draft rows, expected hashes/timestamps and a complete
  source group. Any failed target rolls back the entire transaction.
- Idempotent replay without timestamp changes or a new verification claim.
- Execute permission for the existing server role only, never public roles.

The private dry-run may extract from the exact fresh official PDF when a legacy
registry authority is null. It explicitly records that missing classification
and cannot stage or publish until it is resolved. Conflicting authorities,
models, markets or URLs are rejected, not normalized into an approval.

## Commands

```text
npm run catalog:skoda:prices:dry-run
npm run verify:price-refresh
npm run verify:price-refresh-worker
npm run verify:price-evidence
npm run verify:price-evidence-ui
```

The UI command uses the existing local preview by default. Append
`-- --isolated-server` to start and close a test-only local preview. It uses
clearly isolated transport fixtures, blocks provider calls and does not upload
screenshots or mutate canonical records.

Only after owner approval, migration installation and registry verification:

```text
npm run catalog:skoda:prices:stage
npm run catalog:skoda:prices:publish
npm run catalog:sync
```

Every publication invocation fetches the source again. A previous successful
dry-run or old saved fetch timestamp is not current publication evidence. If
owner approval names specific prices, recheck those values before staging.
Preparation packets and source text remain in ignored
`data/local/release-data/price-refresh/`; no credentials enter a packet.

An RPC transport failure is an unknown outcome, not proof that nothing was
published. The saved packet is marked unknown. Inspect the same private batch
and canonical target rows before any retry; do not create another batch or
claim a rollback from a missing response. SQL failures remain atomic.

## Live Read-Only Findings: 2026-10-27

Fresh official PDF extraction prepared these campaign prices privately:

| Exact Variant | SEK | Valid Through |
| --- | ---: | --- |
| Solid Edition 85 | 599500 | 2026-12-15 |
| Solid Edition 85x | 638500 | 2026-12-15 |
| Solid Edition 85x Sportline | 679900 | 2026-12-15 |
| Solid Edition RS | 689900 | 2026-12-15 |

Private batch `9ecacabcccca037f447ca276cf19eaa0ba63e5e66114842b6a4ecea51fb9c7ab`
records the real fetch and exact-column drafts. The existing registry identifies
the correct URL, model, Swedish country/language and price-list type, but its
`source_authority` is null. The batch is held for registry alignment; zero rows
were staged or published, zero production writes and zero paid AI calls.

At this initial checkpoint the production migration and four updates were
submitted separately for owner approval. This historical private preparation
was not publication. The later applied status above records the actual result.
The local backup
and isolated restore prerequisite has already passed; image rights, privacy,
production hosting/domain and encrypted off-site backup remain separate gates.

## Verification

The new SQL contract passes 24 rejected-batch cases, all-or-nothing rollback,
concurrency, replay, server-only access and exact preservation of technical facts
and verification dates. Five worker tests cover private preparation, stale fetch,
identity/authority conflicts, missing legacy authority, the staging boundary and
unknown RPC outcomes and changed operator-approved price matrices. The three existing intake tests and nine existing refresh
tests pass. Windows sandbox temporary-directory restrictions were worked around
by rerunning unchanged fixtures in an allowed local test directory.

The catalog, release-config, advisor, Functions runtime, simulated live-AI,
AI-budget/cost and database-security regressions pass. Production build and SEO
checks pass with 81 routes. The desktop/mobile transport-fixture UI pass
confirms distinct sources/dates, no stale price summary, no horizontal overflow
and zero axe violations. The visual review additionally separated the price date
from other facts in the specification section; the expanded final UI check also
passes at 1440x1000 and 390x844. Screenshots are private, simulated UI proof,
not a live price publication or a deployed candidate.

Before installation, read-only Supabase checks confirmed exact parity for all 67 variants, 30
public models, denied anonymous access to all seven private vehicle tables and
preserved service-role reads. The five new public price fields were absent at
that checkpoint. After the applied update, those columns are present and the
release check remains correctly blocked on privacy, image rights and 44 current
price-verification gaps. No release guard was bypassed or marked complete.

The final local safety pass also protects private `data/`, Cloudflare local
variables/state and backups from development-server HTTP access, without
replacing Vite's built-in secret rules. Eight synthetic HTTP probes pass,
including raw/@fs/encoded/case-varied paths; the actual public catalog and
frontend modules remain readable. No real backup was fetched. The production
build, all 81 SEO routes and both price-evidence UI viewports pass again with
this configuration. No external deployment or off-site backup was created.
