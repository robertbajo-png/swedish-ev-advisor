# News Release Runbook

## Release Scope

The limited release supports source-bound Swedish model/battery articles and
deterministic price notices. Sources, factual claims, independent review and exact
publication artifacts remain traceable. Uncertain or unsupported stories stay
private; news never overwrites canonical vehicle data.

The news model is configured as `gpt-6-sol`. Existing shared limits remain
USD0.25/day and USD5/month, with at most one article per UTC day across formats.
Limits are ceilings, not quotas. Provider calls require prior durable reservation
and actual usage reconciliation. An unresolved request blocks further paid work.
Never reset old charges, reuse closed permits or activate a worker to test it.

Model/battery articles use the 150-250-word short recipe with separate writing and
fact review. Price notices use the separate deterministic facts/re-render checks
and transactional notice publisher, not an AI article audit. The mixed-format
gate requires real settled model/battery proofs plus a validated price notice;
passing that gate is not owner authorization to activate or publish.

The two articles already published after separate approval are public fixtures,
not authorization to publish another article. Automatic news AI and both global
and notice publication switches remain OFF. Installation of SQL migrations and
changes to private owner configuration require separate approval.

## Private Preparation

Hybrid 200-350-word articles and BMW DC/AC preparation are separate private
formats. BMW scope retains peak versus average power, added versus total range,
net battery capacity and charge windows; AC preparation retains optional/future
equipment, German market, provisional values and AC input versus V2L output.
These formats have no implicit production publishing support.

Only an exact verified vehicle image or a neutral missing-image state is allowed.
Old publication dates are never refreshed by fetching a source again. Protected
source wording must not be translated wholesale or reused as an original article.

Synthetic tests/fixtures and test-runner source code are included in Git. Actual
live trial outputs, draft articles, authorization receipts, databases, raw source
captures and detailed private trial history are not part of this release package.
Old test-runner source files are retained where needed for regression/import
compatibility. Their presence is not permission to run a paid trial.

## Workflow Separation

- `ci.yml` runs offline checks/build/UI contracts. PR CI does not receive provider
  credentials, install remote migrations, deploy or activate production.
- `news.yml` is behind `NEWS_AUTOMATION_ENABLED`. Collection and notice staging
  are private/free. The short-article worker additionally requires
  `NEWS_SHORT_ARTICLES_ENABLED` and owner-controlled database switches. The first
  automatic editorial scope is VW Sweden models and Firefly battery stories;
  routine price-notice publishing is not connected to that worker yet.
- `news-distribution.yml` is separately behind `NEWS_DISTRIBUTION_ENABLED`. It
  only reads published news with an anon/publishable key and updates the existing
  `seekev-ai-preview` / `codex-ai-preview` branch, never DNS/production domains.
  It cannot write/publish articles or buy AI work. Recovery cannot generate a
  replacement article after an upload failure.

Distribution requires successful CI for the exact current main commit before
credentials. Double-read snapshot consistency and a pre-upload hash check prevent
publishing a stale build. Snapshot/run-attempt metadata identifies the exact upload.
Export, sitemap, article HTML and noindex are checked. Unchanged data skips setup,
installation and build, but the existing pages are still checked.

### Explicit Manual Redistribution

An owner-requested upload test/recovery may use the manual-only
`redistribute_snapshot_sha256` input. Its default is empty. A nonempty input must
be the exact normalized SHA-256 of both the currently published database records
and the already deployed preview. It is accepted only for `workflow_dispatch` on
`refs/heads/main`, with nonempty unchanged published content. Scheduled runs and
`workflow_run` events cannot use it. The real `changed` value remains false;
`redistribution_requested` and `upload_required` separately identify the replay.

This does not authorize an article, provider call, database write, alternate
project or production deployment. All exact-main green-CI, source double-read,
pre-upload hash, fixed preview target, workflow-attempt and noindex/HTML/sitemap
checks still apply. Never fake a data change to exercise the upload branch.
For an approved one-off test, enable only `NEWS_DISTRIBUTION_ENABLED`, dispatch
once with the verified hash, and restore its previous state after eligibility.
Keep all editorial flags and owner switches off. Inspect the actual upload step
and exact deployment receipt; a green unchanged/no-upload job is insufficient.

## Configuration Before Activation

Do not enable repository flags while an older news runner is installed on main.
Merge a reviewed green PR first, then verify repository/environment configuration.
This branch/PR is not approval for merge, installation or activation.

The distributor needs only public `SUPABASE_URL` / `SUPABASE_ANON_KEY`, plus the
existing preview environment's `CLOUDFLARE_ACCOUNT_ID` and appropriately scoped
`CLOUDFLARE_API_TOKEN`. It must not receive `OPENAI_API_KEY` or a service-role key.
No secret value belongs in Git, frontend build variables or workflow output.

The editorial worker uses server-only credentials under separate owner controls.
Keep the frontend's independently configured advisor model/budget unchanged.
Do not configure broad account permissions, new hosting, DNS or another AI key as
a workaround for an unverified CI configuration.

## Safe Checks

```powershell
node scripts/verify_news_package.mjs --self-test
node scripts/verify_news_package.mjs --staged
node scripts/verify_news_distribution.mjs
bun scripts/verify_news_distribution_workflow.mjs
node scripts/sync_news_snapshot.mjs
node scripts/run_python.mjs scripts/news_notice_preflight.py --remote --mode paused
```

The default snapshot command is read-only. Explicit `--write` changes only the
local build export and never publishes an article. Preflight is GET-only.
No private live-test artifact is required for offline CI; tests use synthetic
fixtures and mocked provider calls. Manual fixtures are not successful AI proofs.
The separate Mobility Sweden March import integration test runs only when its
optional local raw XLSX exists. A clean source export explicitly skips that one
test rather than distributing the raw file or pretending it was exercised.

Before requesting merge, verify the PR's exact commit/checks and included paths.
The index package guard rejects environment files (except `.env.example`), local
data, databases, private trial documents and recognizable real credentials. It
prints file names/reasons only, never suspected secret values.
