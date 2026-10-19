# Release Readiness: Elbilsagenten

Audit date: 2026-10-19. Decision: **NO-GO for an open public release**.
The functional preview is useful for testing, but is not production readiness.
No DNS, database permissions, credentials, published records or hosting bindings
were changed by the initial audit. No paid AI requests were made.
The owner subsequently authorized fixing item 1; migration 008 is now applied
and its access checks pass. The remaining release blockers are unchanged.
See `docs/vehicle-access-hardening.md`.

## Inspected Versions

- Repository: `98c63184935408d5876067862a4aaae8c1c007ff`, clean before audit.
- Latest repository CI: passed, Actions `39266654503`.
- Deployed runtime: `125d0e7e70b054c13ef66c3e237e5640332223da`.
- AI preview: https://codex-ai-preview.seekev-ai-preview.pages.dev/
- Its versioned URL: https://9b3fb8af.seekev-ai-preview.pages.dev/
- Cloudflare project inventory shows only `seekev-preview` and
  `seekev-ai-preview`, with no Git provider attached. The current rollout is
  preview-only; a production deployment has not been verified.

## Blocking Findings

### Resolved: Internal Database Tables Were Publicly Readable

Before the fix, read-only REST probes using the configured JWT with role `anon` returned
HTTP 200 and a record from each of `extracted_variant_drafts`,
`canonical_model_variants` and `manufacturer_sources`.
A separate filtered staging probe returned a non-published row with status
`extracted`. Raw staging records should not be accessible through the public
key, regardless of whether the website itself filters them correctly.

Only identifiers/status metadata were inspected; no payload was printed or
saved. No INSERT, UPDATE or DELETE permission was tested. Successful reads do
not establish whether anonymous writes are possible.

The vehicle migrations/schema do not explicitly revoke public access and
enable RLS for these internal tables. News migration 007 applies these controls
only to news tables. See `database/schema.sql:137`, `:177` and the migrations.

Resolution: migration 008 enables RLS on seven internal tables, removes public
table/column privileges, leaves the two filtered views read-only, and preserves
service-role ingestion. Anonymous REST reads now return 401/42501 for all seven
tables. The actual anon/authenticated SQL role checks pass, the same 66 public
variants remain readable, and before/after public-data hashes match.
Local PostgreSQL regression tests cover 84 denied operations, ingestion CRUD,
column grants, idempotence and rollback. This resolves access-boundary item 1,
not every release concern or possible historical unauthorized access.
Do not break the publication views when changing their underlying permissions.

Reference: [Supabase Data API security](https://supabase.com/docs/guides/api/securing-your-api)
and [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

### P1: No Shared AI Spending Limit

`functions/_shared/ai-guard.mjs:4` uses an in-memory Map per Worker isolate,
five requests per minute per client and two concurrent requests. It is not a
global quota, durable budget or reliable protection against distributed abuse.
Origin checks alone do not authenticate a server-to-server caller.

The advisor is much cheaper, but the separate paid comparison endpoint is
unchanged. Both endpoints need a shared, atomic quota and a fail-closed paid
request gate. Provider failure or quota exhaustion should keep safe database
functionality available without making more provider requests.

Release gate: exercise concurrent requests, multiple isolates, quota reset,
store failure and emergency AI disable. Record remaining production risks.

### P1: Data Freshness And Publication Parity Are Not Established

Current preview snapshot:

| Measurement | Result |
| --- | ---: |
| Models | 33 |
| Variants | 69 |
| Price present | 51 |
| WLTP present | 52 |
| Both price and WLTP present | 34 |
| DC charging present | 29 |
| Tow capacity present | 19 |
| Non-null verification date | 0 |
| Availability explicitly confirmed | 0 |

The export was generated on 2026-08-30, 50 days before this audit. That date
is not proof of when individual source facts were last verified. Every row
has a source URL/hash and published/reviewed status, but this does not establish
that a price is still current. Never fill missing verification dates with the
current date unless an actual source verification supports it.

An anonymous read of the remote public view returned 66 variants / 30 models,
all with public status and source hash. The shared rows have identical price
and WLTP. Missing remotely: Cupra Tavascan, Subaru Solterra and Volvo EX90.
The current preview uses the validated static snapshot, not a verified live
Supabase production configuration.

Release gate: choose one coherent source of published data, verify current
official sources for the launch scope, preserve unknowns as null, align
frontend/API/export and confirm the scheduled refresh and failure policy.
Missing fields alone need not block an MVP, but the promised searches must
have useful coverage and no unverifiable prices may be presented as current.

### P2: Production Identity, Configuration And Privacy Are Incomplete

- Live HTML title/brand still say Elbilsguiden. Canonical URLs and all sitemap
  hosts point to `seekev.se`, not `elbilsagenten.se`.
- Production environment, its secrets, custom-domain TLS, www redirect,
  indexing and rollback have not been tested. Do not attach the new domain
  directly to an unprepared preview-only configuration.
- No dedicated contact/privacy route or footer link exists in the inspected
  UI. Explain who operates the service, how free-text queries are sent to the
  AI provider and which storage/logging services are used. Operator/contact
  details must come from the owner, not be invented.
- Rotation of previously shared private credentials is not established by
  this audit. Never publish a service-role key in client code or hosting that
  only needs public reads. Do not revoke working credentials without a
  coordinated replacement and a verified rollback path.
- Production alerts, dependency-aware health checks, backup/restore and
  recovery procedures have not been verified. Current `/health` only reports
  that the Function is running; it does not probe Supabase or the AI provider.

## What Passed

- Latest repository CI is green and includes build, SEO and UI regressions:
  https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/39266654503
- All eight external deployment GET checks passed on the stable AI preview.
- Advisor matching, shared AI contracts, canonical data contract, image
  mapping contract and cost benchmark fixtures passed locally.
- External site QA passed 18 desktop/mobile page states with zero automated
  axe violations, keyboard checks and 320/640px reflow checks. API errors and
  news articles in this test use labelled transport fixtures, not real AI
  calls or public news publication. This is not a Safari/iOS/device sign-off.
- Latest bounded live AI proof is from the preceding deployment step, not a
  new paid test in this audit. Advisor interpretation and comparison worked
  against the published snapshot.
- Image lookup uses exact model mappings and a neutral missing-image state.
  Four model images are missing: Audi A6 e-tron, Cupra Tavascan, Kia EV6 and
  Volvo EX90. A missing image is preferable to a wrong-model image and need
  not block launch. This contract does not verify licensing or usage rights.

## Scope Decisions, Not Release Blockers

- News has zero published articles and automation remains paused. A vehicle
  advisor MVP can launch without a news service; do not advertise daily news
  or enable its paid workflow as part of domain setup.
- Do not add more models, features or redesigns to solve release readiness.
- Keep incomplete data honest rather than manufacturing specifications.
- Document acceptable image rights/attribution and test key flows on real
  iOS/Android devices before promoting the site broadly.

## Recommended Order

1. Completed: restrict private vehicle tables and test the public/private boundary.
2. Add shared request quotas, spending protection and emergency AI disable
   to advisor and comparison endpoints.
3. Refresh the launch dataset and reconcile Supabase/export/API consistency.
4. Apply Elbilsagenten identity and domain metadata; add owner-supplied
   contact details and accurate privacy information.
5. Prepare a separate production deployment, verify configuration, rollback,
   monitoring, public data and a bounded real AI smoke test.
6. Inventory existing domain DNS, mail and DNSSEC. Add the Cloudflare zone,
   then change Loopia nameservers, attach apex/www and verify HTTPS,
   redirects, deep links and search-engine metadata on the real domain.

Domain connection is authorized by the owner but deferred until the above
release blockers are addressed. Assigned Cloudflare nameservers must be read
from the actual zone; never guess them. No registrar transfer is necessary.
