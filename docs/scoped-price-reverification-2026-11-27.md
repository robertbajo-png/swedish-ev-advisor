# Scoped price adjudication, 2026-11-27 (review candidate only)

This slice is separate from Sandsten PR #137. It must not be merged or installed
until independently reviewed and the owner approves the exact migration SHA,
including private history, the narrowly scoped public withheld indication and
the exact legacy price-source alignment. No production write has been made.

## Exact scope and genuine current evidence

- Seven Elroq Explore Edition campaign cash prices: 449500, 469900, 494900,
  510300, 544900, 559900, 591900 SEK, expiry 2026-12-15. Official 5 November
  PDF (hash-bound page 1) is linked by
  https://www.skoda.se/erbjudande/kampanj/erbjudande-elroq ; page 2's old June
  optional-equipment footer does not govern the vehicle table.
- ID.3 Neo Trend 409900; exact ID.4 BSJ09L 628550 **including** advertised
  627600 plus mandatory registration fee 950. Volvo ES90 JWR04C 819000 and
  EX30 P5 Long Range Core MY27 484000. No amount, price type or term changes.
- Audi A6 RRR07B returns 500, uncertain; Q6 JCE98Y returns 410. Neither is
  described as sold. They have no existing WLTP/technical numeric data, so
  merely clearing price previously failed the canonical export's price-or-WLTP
  invariant. Their exact identity, published status, market flags, technical
  source and original quote remain. Null current price/proof, explicit known
  withheld reason and observation date, historical quote labelled not current.
- Genuine service-role read: 146 private canonical rows; 13 exact targets.
  Current Elroq price registry has null authority/name and no linked technical
  references. Only 4 old needs_review Elroq rows point directly to its URL.
  Classify only that existing source as manufacturer / Skoda Sverige, in the
  same transaction, with all other source fields unchanged (incl verified_at,
  content hash, updated_at). Reject any other reference or alignment. No
  technical source is marked current. Archived before/after registry row.
- Double anonymous read: 109 public rows, identical
  d6eebbc11c22c3b5f0d99b6b9cbb9f09a2af3c8ad1c33439af656eab483aa619.
  Existing live record difference is only the 18 exact ISO-ms timestamp
  representations in nine unrelated rows; preserve only if raw canonical
  value remains identical. No hand-spliced release snapshot.
- A subsequent real read-only source collection and before/after private reads
  produced an exact 13-target feasibility plan in the ignored operator folder.
  It is not an approval or dispatch receipt; all source timestamps must be
  freshly collected again within 15 minutes at the actual application.

## Contract

029 installs a private history table (RLS, no public grants; existing service
role select/insert only) plus two existing-role invoker functions and appends
two optional public-view columns. Installation does not mutate data. These
columns are absent from older catalogs and omitted when null, preserving
unchanged row representations and old hash. Public withheld status is only
derived from a matching immutable archived after-row; it is not a price or a
new availability fact. Exporter admits no generic price-and-WLTP-empty row:
only the exact two known Audi stock identities with matching reason, source
and complete absence of current offer/proof. The 30-day gate is unchanged.

The bounded RPC verifies exact target identities, original complete proofs,
exact prices/semantics, source registry and fresh official proof/quote, full
private canonical baseline, and shared lock. It archives before/after proof,
including exact temporary registry alignment, atomically with the 11 proof
refreshes and 2 withdrawals. It verifies the entire resulting canonical table,
source registry and model table, and rolls back on a late failure. A previously
used batch may only replay with exact original receipt and unchanged state;
another batch fails. The existing role is not replaced; no user/API credential
permission has been opened. The new history relation has no delete/update grant
to service_role.

The read-only Python planner collects real registered sources (same robots and
authority guards), verifies content-addressed archived bytes, fee, exact
source quotes and all price-only fields. It has no production write entry point.
The eventual operator dispatch must reuse the existing narrowly restricted
SupabaseRestClient, allowing exactly one POST to
rpc/publish_scoped_price_reverification_20261127 with the exact prepared packet.
Do not use raw PATCH, generic replacement, old Enyaq/Kia route, or a hand-made
price snapshot. The caller must preserve a durable attempt marker before the
single POST. A failed transport is unknown: inspect original batch/history
and readback, never send a second operation as a recovery.

## Verification / release sequence

1. Coordinator independently reviews the exact candidate and the owner
   specifically approves installing migration 029 and the one-source alignment
   above. Validate current schema/ACL and existing operator SQL access without
   new permission; freeze actual live catalog/news/RSS/sitemap, current Pages
   deployment rollback ID, private and anonymous canonical baselines. If any
   change beyond reviewed scope, stop. Before migration and immediately after,
   confirm identical protected data and role grants, zero history rows. The
   immutable migration/rollback SHA must match reviewed bytes.
2. Read baseline with GET rpc/scoped_price_reverification_20261127_baseline
   twice, bind to the exact approved pre-write private baseline (matching
   deployed schema and real server JSON), and use fresh
   prepare_scoped_price_reverification_20261127.collect()/build_plan() under
   the approved scope. Allow the alignment parameter only after approval.
   Serialize packet and save an exclusive actual dispatch attempt receipt.
   The existing CLI/client transport may POST only the exact RPC / packet;
   unknown outcomes require original receipt reconciliation.
3. Require actual RPC success 11 refreshed / 2 withheld / alignment true,
   history 13 exact before/after rows and zero other data/tech/fact changes.
   Re-read anonymous canonical twice (new status fields must be present).
   Create scoped export receipt with prepareScopedPriceExportReceipt using
   genuine RPC/packet/history observations; run ordinary
   sync_public_catalog.mjs --scoped-price-reverification-receipt <receipt>
   dry-run and then --write. The export requires exact 13 row diff, remaining
   rows byte-identical, and permits only prior proven timestamp representation
   aliases. Test-only snapshots are never release inputs.
4. Review/CI exact price implementation PR separately from Sandsten; integrate
   only approved revisions and verified actual latest public data. Run normal
   production check/build and deploy with existing documented release guards,
   fresh rollback checkpoint and unchanged news/RSS/sitemap. Recheck current
   and historical price display and static/hydrated JSON-LD at the public
   origin. No paid request is needed.
5. Recovery: the reviewed 029 rollback disables its one-off execute capability,
   retaining private historical proof and the withheld public view state.
   Do not restore an unverified old offer as current. A price restoration
   requires a separately verified new exact-source publication. The normal
   site deployment rollback is independent; verify the previous deployment
   identifier before upload and preserve canonical data.

## Local tests and scope

- Existing price-refresh worker/Elroq intake, existing public catalog/price
  evidence and release-config tests pass. The new SQL/PGlite test runs the
  real schema plus exact migration, reproducing the observed nullable legacy
  source registry in disposable data only. It exercises 11/2, private history,
  another row and four historical rows preserved, exact aliases, readback,
  service-role write, anon view read, ACLs, exact replay and late rollback.
- Never install live DDL merely because this local test passes.
- Actual local Vite/static/SSR build and Playwright Edge on 320/390/768/1440:
  both Audi pages display Ej verifierat, no old prices in the vehicle view,
  no offers in static or hydrated Vehicle/Product JSON-LD, both historical
  source disclosures accessible. Fixture based on frozen live records with
  simulated withdrawal status; no actual DB mutation. Build includes the
  main branch's news snapshot, not a release artifact. It must never deploy.
- Pinned frontend skill 82d2c5b44ac234ec0f204f647562a4349d90ef43 (skill file
  SHA d367b2d22825d74c169475507e7ff109b81c1e9c20b2de3421fb19fcfbe3329b):
  retain product hierarchy, typography, photo geometry, colors and controls;
  clarify status with one short value and a consolidated source explanation,
  no new visual surface or decorative component.
