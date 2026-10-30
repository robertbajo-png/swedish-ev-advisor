# Production Preparation: 2026-10-28

## Completed

- Existing Cloudflare account identity matches the authenticated CLI and dashboard.
- Created the free, isolated Pages project `elbilsagenten`, production branch `main`.
- Created D1 `elbilsagenten-ai-budget-production`, restricted to EU jurisdiction.
  Its ID is `206ce4df-f219-4d67-be24-e4b56f52a6be`.
- Applied the disabled production bootstrap. The schema matches the existing
  ledger; replay preserves policy limits, receipts and disabled state.
- Stored the owner-approved existing OpenAI key and a new independent budget salt
  as server-only Pages secrets. No secret was printed, committed or copied into
  public configuration. No paid provider request was made.
- Added a separate Wrangler production configuration. Both production and
  candidate environments have `AI_ENABLED=false`; preview CI remains unchanged.
- OpenAI dashboard metadata identifies the approved local key as `Elbilsval`,
  active in `Default project`, `proj_z3lwu0ue32E5vgfzyYLiTonW`, organization
  `org-ODCGNA4NvEhTyNadCift7ayy` (display name `Personal`). The local secret was
  compared in memory against its masked dashboard suffix; plaintext was not read
  into tool output. Sharing of API inputs/outputs, evaluation/fine-tuning data
  and Playground feedback is disabled for the organization, covering this
  project. API logging is enabled per call; application requests use `store=false`.
  Project residency is Global, not EU-only. No account settings were changed.
- Supabase dashboard confirms the existing project, a single owner and region
  `eu-west-2`, West Europe (London). Do not describe it as EU-resident.
- Loopia shows the exact registered domain `elbilsagenten.se`, parked and renewed
  through 2027-10-25. DNSSEC is enabled. No password, renewal or registrar setting
  was changed.
- Added the domain to Cloudflare's Free setup. Its non-authoritative scan imports
  six parking A records: apex, `www` and wildcard, each pointing to
  `194.9.94.85` and `194.9.94.86`. This is not proof of a complete zone export.
  Bot Preference Sync is off so the app's own robots policy is not rewritten.

## Limits And Remaining Gates

This is preparation, not a live domain release. Do not set the privacy-review
flag solely from successful authentication. Existing supplier-role, contract and
mailbox review still needs an accurate conclusion; Gmail is not verified Workspace.

Production spending remains disabled. Before enabling it, stop preview spending
and preserve the authorized total USD1/day and USD10/month, including already
charged or reserved costs. Separate databases must not double those allowances.
News AI, both publishers and scheduled article generation remain disabled.

Before nameserver changes, preserve the registrar baseline, handle the old DS
delegation with explicit owner approval and allow full parent-cache expiry.
Then associate the correct Pages custom domains, verify candidate deployment,
perform the controlled cutover and restore DNSSEC with the new provider's DS.
Never change `boleoai.se` or the working contact-mail route.

## Tests

- Three production-hosting offline regressions pass: isolated targets and AI-off
  settings; disabled/idempotent SQL with retained reservations; schema parity.
- Existing AI-budget suite passes real SQLite atomic/concurrent reservations,
  UTC rollover, both endpoints and fail-closed behavior, with zero provider calls.
- Previous exact-main application CI passed all 115 steps. The new hosting slice
  must pass its own reviewed CI before it is treated as delivered release code.

## Verified Candidate And Domain Handoff

- PR #11 merged as `aaaac588303b24a40cc350efbaf5d727ecbb1017`.
  PR run 40761522313 and exact-main run 40762278309 each passed all 116 steps.
- Deployed only the `release-candidate` branch of `elbilsagenten`, with AI off:
  `https://b0b88d27.elbilsagenten.pages.dev/` (alias:
  `https://release-candidate.elbilsagenten.pages.dev/`). No main production
  deployment or production custom domain is claimed.
- The existing HTTP checker passes all eight candidate checks with noindex.
  Additional real deployed checks verify exact catalog/news artifact bytes,
  30 models / 76 variants, healthy AI-disabled readiness, and eight actual
  desktop/mobile page states with no axe violations, overflow or page errors.
  The eight-state visual check makes no API POSTs. A separate two-POST check
  verifies real advisor and comparison endpoints return HTTP200 and
  `deterministic_fallback`, without paid inference.
- Build: 1,752 modules, 90 prerendered routes, 38 preserved redirects; SEO has
  zero errors. Client-asset scanning found none of the actual local server secrets.
- Private operational receipts/screenshots are under
  `data/local/release-data/production-candidate-proof-2026-10-28/`.

The owner explicitly confirmed that `elbilsagenten.se` has only parking and no
other mail/services, and approved temporary DNSSEC deactivation for the migration.
Loopia then confirmed `Dnssec-andring genomford` and shows Activate DNSSEC.
This supersedes the earlier enabled-state observation. Nameservers remain Loopia.
Cloudflare assigned `bingo.ns.cloudflare.com` and `yahir.ns.cloudflare.com`.

Before deactivation, a direct authoritative DS query returned TTL3600. Direct
non-recursive queries of ALL ten observed `.se` nameservers (a,b,c,f,g,i,m,x,y,z)
returned no DS and authoritative SOA between 20:43:07 and 20:43:10 UTC on
2026-10-28. Do not change nameservers before **21:43:11 UTC**, and re-check
authority, recursive resolvers and all other release gates first. This is an
earliest safe cache-expiry bound, not a promised activation or HTTPS completion.
Restore DNSSEC with Cloudflare's correct new DS after migration; never reuse
Loopia's old DS. No `boleoai.se` DNS or mail route has changed.

The owner confirmed the destination is ordinary free Gmail, not Workspace, and
approved preparing Proton Free instead. The free signup page is open in the
in-app browser, explicitly `plan=free`; the owner must enter the new credentials
and accept terms themselves. No Proton account, new destination verification or
forwarding change is claimed yet. Keep the working Gmail route until a verified
replacement and actual delivery proof exist. No provider subscription was bought.
The privacy release flag remains false pending the completed mailbox/supplier review.
