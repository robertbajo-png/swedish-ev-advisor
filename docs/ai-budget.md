# Shared AI budget

## Implementation plan

1. Add a private D1 policy and atomic reservation ledger, separate from vehicle data.
2. Require a reservation at the shared provider boundary for advisor and comparison.
3. Settle verified usage conservatively; retain reservations after uncertain failures.
4. Test concurrency, UTC boundaries, missing bindings, kill switch and both routes.
5. Deploy only the AI preview, then run two bounded live checks and inspect the ledger.

## Policy

- Default: USD 1 per UTC day and USD 10 per UTC calendar month, shared by both endpoints.
- Amounts use integer microdollars. Hosting, VAT and other OpenAI projects/scripts are excluded.
- Only `gpt-5.4-mini`, standard service tier, text-only structured Responses are permitted.
- Maximum output: advisor 512 tokens, comparison 2,400 tokens. No tools or automatic retries.
- Reserve USD 0.02/advisor or USD 0.05/comparison before contacting OpenAI.
- Requests including schemas are limited to 10,000/24,000 UTF-8 bytes respectively.
  Reservations cover those byte bounds plus 8,192 input-token overhead at the reviewed rates.
  This is a conservative application allowance, not a provider-guaranteed invoice ceiling.
- Rates reviewed 2026-10-19: input USD 0.75, cached input USD 0.075 and output USD 4.50 per million tokens.
  Paid calls expire on 2026-11-19 UTC until the policy's pricing review is renewed.
- Reduce the charge only after validating provider model, tier and token accounting.
  Timeouts, errors, malformed/missing usage and settlement failures retain the full reservation.
- No refunds on unverified usage, public quota-management endpoints, client-provided costs or automatic limit increases.
- A daily HMAC of the Cloudflare-supplied IP limits each visitor to 5 paid calls/minute
  and 50/day across isolates. Raw IPs, questions and responses are never stored in D1.
- Missing binding/salt, unknown model, disabled/expired policy or D1 failure means no paid call.
  Canonical database results remain available and are identified as non-AI results.
- Local Node development has no D1 binding and therefore cannot make paid calls.
  Use Pages local development with a local D1 instance for controlled budget tests.

## Operations

Changed surfaces: `functions/_shared/ai-budget.mjs`, shared advisor core/HTTP
options and both API routes; `database/cloudflare/ai_budget.sql` and `wrangler.toml`;
local Node comparison routing; budget/AI contract tests, benchmark allowance and CI.
The remote verification script is an operator-only tool, not deployed app logic.

`database/cloudflare/ai_budget.sql` is D1/SQLite only, never a Supabase migration.
Its idempotent seed does not reset existing limits, spending, kill switch or expiry.
The private binding is `AI_BUDGET_DB`; `AI_BUDGET_SALT` is a preview secret of at least 32 characters.
The existing UI-only preview is not redeployed or given secrets. Production is disabled by default.

Inspect privately with Wrangler `d1 execute elbilsagenten-ai-budget-preview --remote --command`:

```sql
SELECT enabled, daily_limit_micro, monthly_limit_micro, pricing_review_until FROM ai_budget_policy;
SELECT date(created_at, 'unixepoch') AS day, kind, count(*) AS requests,
       sum(charged_micro) / 1000000.0 AS accounted_usd,
       sum(settled) AS settled_requests
FROM ai_budget_reservations GROUP BY day, kind;
```

Emergency stop (takes effect on every subsequent reservation, including old isolates):

```sql
UPDATE ai_budget_policy SET enabled = 0 WHERE id = 1;
```

Change limits only with explicit owner approval. Do not delete current-month reservations.
Old rows may be removed after 62 days. Rotating the HMAC secret resets visitor quotas,
not the shared spending totals. Do not log or expose it.

Read-only operator verification (set `WRANGLER_BIN` to your installed Wrangler CLI):

```powershell
node scripts/verify_ai_budget_remote.mjs
```

Adding `--exercise` briefly pauses the AI preview, verifies that both endpoints
return canonical fallback without new reservations, then restores the policy in
`finally`. It refuses to enable an already paused policy. This check needs private
Cloudflare account access; it is not a public status endpoint or a production monitor.

## Verified Deployment: 2026-10-20

- Runtime: `40173d026c388b95c22db431cf33d84a4ee15169`.
- [Green CI](https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/39283393585).
- [Stable AI preview](https://codex-ai-preview.seekev-ai-preview.pages.dev/).
- [Versioned preview](https://817fd8cc.seekev-ai-preview.pages.dev/).
- Private EU D1 database and preview-only random HMAC salt are configured.
  No Supabase credentials were transferred and no DNS or vehicle records changed.
- Remote emergency-stop exercise passed for advisor and comparison, with no new
  reservations or provider calls; the enabled policy was restored and re-read.
- Two real Responses calls on 2026-10-20 returned `mode: openai` and canonical
  identities/sources. D1 recorded exactly two settled requests: advisor 686 and
  comparison 1,950 microdollars, total USD 0.002636 after upward microdollar rounding.
  These are usage-based accounting amounts at reviewed prices, not an invoice read.
- All eight deployment GET checks pass on both current URLs, including 69 published
  variants and noindex. Local budget, SQLite concurrency/UTC/failure, API, database,
  build/SEO, six UI suites and 23 news fixture tests passed. News remains paused.
- Old uncapped AI deployments `e36a3640` and `9b3fb8af` were deleted. Their API GETs
  now return 404, and the project inventory contains only the budgeted deployment.
- Never roll back to an uncapped version. Rebuild a budgeted commit or disable AI.
  The separate UI-only preview was not redeployed. Production AI remains disabled.

This resolves the preview's shared spending-control blocker, not overall release
readiness. Data freshness/parity, production identity/privacy, credential rotation
and production/domain configuration still need their own verification.

The standalone, explicitly invoked cost benchmark uses its own bounded in-process
allowance and is not charged against the deployed D1 ledger. Vehicle extraction and
news workers are separate, not activated or covered by this website budget.

Sources: [model pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[Pages bindings](https://developers.cloudflare.com/pages/functions/bindings/),
[D1 database API](https://developers.cloudflare.com/d1/worker-api/d1-database/).
