# News Release Runbook

## Release Scope

The limited release supports source-bound Swedish model/battery articles and
deterministic price notices. Sources, factual claims, independent review and exact
publication artifacts remain traceable. Uncertain or unsupported stories stay
private; news never overwrites canonical vehicle data.

The news model is configured as `gpt-6-sol`. The owner approved new shared limits
of USD0.50/day and USD10/month on 2026-11-04, with at most one article per UTC day
across formats. Install migration 022 only after separate approval and green CI;
until installation the original USD0.25/day and USD5/month remain in force.
See `docs/news-budget-policy.md` for deployment and historical-worker boundaries.
Limits are ceilings, not quotas. Provider calls require prior durable reservation
and actual usage reconciliation. An unresolved request blocks further paid work.
Never reset old charges, reuse closed permits or activate a worker to test it.

Model/battery articles use the 150-250-word short recipe with separate writing and
fact review. Price notices use the separate deterministic facts/re-render checks
and transactional notice publisher, not an AI article audit. The mixed-format
gate requires real settled model/battery proofs plus a validated price notice;
passing that gate is not owner authorization to activate or publish.

The two articles already published after separate approval are public fixtures,
not by themselves authorization to publish another article. On 2026-11-01 the
owner explicitly requested automatic news publication and approved storing the
existing editorial credentials in a separate main-restricted GitHub environment.
Activation requires the verified mixed-format proof and an exact approved budget pair. The
notice-specific switch remains OFF; this release only automates model/battery AI
articles. No private/failed draft is promoted. New SQL migrations still require
separate approval.

## Approved Automatic Operation

`news.yml` checks every four hours. An exact current-main CI check runs without
credentials before the main-only `production-news` environment becomes available.
It runs the existing short worker, not old private trials or the legacy free-form
publisher. The initial supported sources are Volkswagen Group Sverige and Firefly
China. Thin, inaccessible, stale or unsupported stories do not justify an article.
Each paid candidate gets one writer/reviewer pair and the existing three gates.
Rejected candidates stay quarantined. There is no daily article quota.

The owner also requested broader sources on 2026-11-01. The separate `broad`
collection profile checks 16 configured sources: electrive, InsideEVs, CnEVPost,
CarNewsChina, Electrek, Autocar, Auto Express, Bevolt, Motor, CleanTechnica,
The Driven, ICCT, ACEA, Volkswagen Newsroom, BMW PressClub and VW Sverige.
It verifies actual feeds/indexes and stores bounded metadata without paid AI.
Robots, TDM reservations, inaccessible feeds and paywalls remain hard stops;
configuration is not proof that a source currently permits collection or AI use.
Collection is NOT automatic editorial approval. The original short publisher
retains its reviewed source/format adapters. The owner-approved shared-template
publisher below handles additional articles; the legacy free-form publisher is
not enabled as a shortcut.

The 2026-11-02 European expansion adds Bevolt (formerly Automobile Propre) and
NAF-owned Motor to the shared article templates. The old Automobile Propre
identity remains disabled, with its successor recorded; cross-domain redirects
are not silently followed. Editorially reserved electrive/Electrek/CnEVPost stay
discovery-only, not AI evidence. See `docs/news-european-sources.md` for real
access results and source ownership/layout boundaries.

The 2026-11-05 source follow-up adds official Polestar news on
`https://www.polestar.com/global/news/` to the broad collection profile. Its
source-specific canonical slash and single-main/JSON-LD identity/date checks
do not relax freshness or the independent article audit. The live isolated
check found only old releases and made no paid requests or publications.
Volvo remains held. The later BYD Germany adapter uses the verified public list
query and canonical article/header/narrative checks, not generic whole-page text.
German customer offers, hybrid/price stories and speculation are held before
paid writing; canonical cars and existing publication/budget gates are unchanged.
See `docs/news-content-month.md` for the free live results and deferred Google work.

### Shared Article Review (Owner Approved 2026-11-02)

Explicitly configured official pressrooms may now start this same shared
article pipeline directly (`official_release`). Their real release is the
single primary source, not a fabricated publisher pair. Only named, date-required
pressroom authorities with `official_article_lead` may use this route. Feed
summaries are not evidence. Exact refresh, company attribution, literal fact
support, independent review, all three publication gates and the shared limits
still apply. Swedish EV metadata and bounded official candidate slots prevent
valid originals from being hidden behind an unproductive publisher queue.
The Actions job summary records the actual editorial outcome separately from
collection/distribution success, without exposing private source/provider bodies.

The owner approved `news-article-review-2026-11-v2`, replacing the extra per-source
admission round with review of each exact article. `run_publisher_news.py` does not change the
historical VW/Firefly code hash or accept their receipts as publisher proofs.
Source identity, ownership evidence and optional layout/path overrides live in
`data/news/publisher_templates.json`, backed by the existing source registry.
The common parser supports the configured body or a single semantic article;
it requires canonical URL, publication metadata and complete accessible text.
Unknown templates, ownership, layouts and access rights are held, never guessed.
Exact reachable primary links must match the approved host/path registry;
there is no AI-selected URL fetching or access-rule bypass.

The combined structured writer selects evidence IDs from deterministic literal
source spans and returns an atomic fact inventory and a new 150-250-word Swedish
article. Resolve IDs without changing any article wording; retain both the raw
provider output and resolved packet and compare them to actual provider receipts.
A separate independent reviewer checks every fact,
clause, attribution, originality and market qualification. Official evidence is
preferred. Otherwise every fact requires complete matching support from two
different verified editorial groups. Reject same-owner sites, borrowed/circular
attribution, shared wire/upstream stories and copied/syndicated text. The review
must separately confirm editorial independence and reported-not-verified status.
Shared official announcements are company claims, not independent measurements.
Reported articles use a `Rapporterat:` headline, name both sources in the intro
and retain attribution in every paragraph. They cannot claim our service has
verified Swedish availability or specifications. News never changes car data.
Old policy dates remain old; CLTC, WLTP, charging units and foreign currency/market
scope cannot be converted or presented as Swedish specifications. These reports
never update canonical car facts; exact existing model matches may only enqueue
manufacturer verification.

Before the first call, the entire bounded writer/reviewer pair must fit the actual
shared allowance. Each call still uses the durable reservation/settlement RPC.
Invalid drafts do not buy a review or rewrite. An ambiguous provider outcome keeps
its full reserved charge and blocks further paid work; it is never recorded as
zero actual cost. A story gets at most one private test attempt per UTC day;
at most three distinct private stories may be tried in total that day during this
rollout. A rejected story is not rewritten or retried to obtain an approval. The
same shared allowance applies to every trial and production request.

`trial` uses fresh sources, an isolated SQLite article store and private remote
receipts only; it cannot publish and successful private tests are not automatically
promoted. The main-only `NEWS_PUBLISHER_ARTICLES_ENABLED` worker requires exact
writer/reviewer outputs, completed settled receipts, current code/config hashes
and fresh source snapshots for EACH article. There is no separate paid publisher
admission test. The old qualification command is inert; its workflow step is
removed and its repository flag retired. Historical failed URLs remain excluded
across recipe changes. Unknown cost still blocks all subsequent paid work.
The normal `run` step follows the existing short worker, shares its global daily
attempt limit and transactional one-article-per-day ceiling, and may first reuse a
fresh fully audited production candidate without another paid call. Immediately before
publication it fetches the sources again; any changed source is held for a new
review. Distribution still uses only the public view and separate Pages credentials.
Routine rejected drafts are quarantined normal outcomes, not failing jobs or
owner approval requests. Accounting, source-integrity or provider failures still
stop the worker. Never automatically buy a rewrite of a rejected draft.

The templated publisher metadata window is explicitly 20 items per feed (at most two RSS
pages, deduplicated by URL), while other broad sources retain three. Widening this window once requires a full permitted feed
fetch rather than accepting a 304 for the old smaller window; normal polling and
conditional requests resume afterwards. This never increases paid attempt limits.
Both workers rank Swedish/European reports and substantive global vehicle
technology before recency. Regional business/policy, foreign offers, rumours,
stationary storage and unsupported subjects are held before writing. Ranking is
not a verified Swedish availability flag or a substitute for the relevance audit.

Evidence uses whole source passages selected across the captured document, with
exact original offsets and unchanged byte caps. Conditions, dates and technical
qualifications can come from later paragraphs; quotations cannot span omissions.
Subject mismatch, old-background-only primary material and insufficient literal
facts stop paid work. A blocked/unrelated direct source may only fall back to the
same explicitly approved official discovery paths, never a scraper bypass.
`run_publisher_news.py select` previews this queue and source readiness using
read-only database access and permitted web requests: no AI, writes or publishing.
The original-source expansion in `docs/news-original-source-discovery.md` reuses
official metadata and declared pressroom indexes/feeds, with bounded cached
lookups, hash-bound provenance and strict manufacturer/model/date matching.
Discovery traces distinguish reservations, wrong subjects and unsupported PDFs.
Publication refreshes the exact approved source documents, never a substituted
search result. A discovered URL is not by itself evidence for a factual claim.
The numeric, minimum-relevance, originality and separate review gates
are unchanged. The three rejected November 1 trials remain quarantined and consume
their original day/trial allowances; a code change is not permission to retry them.

The isolated 2026-11-01 collection check fetched eight working feeds/indexes and
one official index with no recent eligible release, discovering 16 new private
items without AI or production writes. Six endpoints were held for inaccessible
or invalid feeds, robots/mining restrictions, crawl delay or cross-domain redirect.
No access restriction was bypassed. Working metadata feeds do not prove article
full-text/AI reuse permission. The exact detailed response log stays local.

`news-production-distribution.yml` independently exports only public validated
news with the anon key, builds article HTML/sitemap and uploads only to the existing
`elbilsagenten` project/main branch. It reuses the existing Pages/public-read
credential environment, never the news server or OpenAI key. It preserves the
canonical catalog, runtime functions and advisor budget binding. The older preview
distributor retains its preview-only target. A delivery retry never buys another
article. The schedule also catches a missed post-publication deployment.

Owner controls: `NEWS_AUTOMATION_ENABLED`, `NEWS_SHORT_ARTICLES_ENABLED` and
`NEWS_PRODUCTION_DISTRIBUTION_ENABLED` in GitHub, plus the existing private
`news_ai_config.enabled/publication_enabled` switches. Disable both database
switches to stop all paid work/publication; distribution can continue safely.
The current pricing approval expires on 2026-11-21 UTC: the worker must stop paid
work then unless pricing is checked and explicitly renewed. Never extend it
silently, increase/reset budgets or remove the old unknown-cost reservation.

Encrypted read-only backups accept either fully paused news or an exact approved
Sol/one-per-day budget pair (USD0.25/USD5 or USD0.50/USD10). They record actual news state
without calling AI or modifying that state. Notice publication remains disabled.

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
