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
