# News Content Month

Owner-approved direction, 2026-11-04: content first, broad international EV
coverage in Swedish, minimal owner effort, no paid marketing. Work towards 12-16
new useful articles across four independent source owners over 30 days. This is
not a quota or a traffic forecast. Preserve one publication and two distinct
production candidates per UTC day, original writing and independent review.

## Delivery And Acceptance

| Period | Deliverable | Acceptance |
| --- | --- | --- |
| Week 1 | Diagnose and repair the actual funnel | Counts distinguish collection, writing, independent review, publication and delivery; a real fresh article is needed before claiming live success. |
| Week 2 | Broaden usable original sources | Reuse working approved sources; inspect Volvo, Polestar, then BYD without bypassing access rules. A registered source is not verified evidence. |
| Week 3 | Discovery and reading | RSS, published article HTML, metadata and internal links; mobile regression; Search Console verification/submission where owner access is available. |
| Week 4 | Evaluate and prepare distribution | Rolling weekly costs/outcomes, useful topics and three dated share briefs from recent published articles; no automatic external posts. |

## Implemented Slice

- International launches/updates and significant vehicle battery technology can
  qualify without invented European availability. The Swedish relevance score
  stays honest. International significance must be at least 0.8 with a weighted
  score of at least 75; the original regional relevance route is unchanged.
- Foreign central facts require clear country/market context in the headline or
  introduction. International articles need a separate scope decision in the
  independent audit. Currency, test-cycle and literal-source rules still apply.
- Minor nominations/corporate-calendar stories are held before paid writing.
  A writer explicitly returning no relevant facts is recorded as an editorial
  refusal, never a malformed success or an excuse to buy a rewrite.
- `/nyheter/rss.xml` is generated during the existing SEO build, from the same
  validated public snapshot, with stable links/dates and at most 50 items.
  It contains introductions only, no private drafts/provider evidence. The
  news page and HTML head expose the feed. Distribution uses the existing build.
  The fixed-target distributor detects a missing/legacy/stale feed even when the
  article snapshot is unchanged, then verifies RSS after upload. A failed GET
  does not buy or publish another article; transient server errors stop delivery.
- `news_content_report.py --remote --days 7` performs GETs only, summarizes the
  real funnel and retained charges and redacts raw exception/source/provider
  text. The existing news Actions job stores it and shows it in its summary.
  Reports do not pretend that analytics/Search Console are already connected.
- `news_share_briefs.py` prepares up to three dated title/intro/link briefs from
  the last seven days of the public snapshot. If no recent articles exist it
  returns no briefs, not invented posts. The news job attaches the result; it
  never sends messages or posts to third-party services.

## First Read-Only Baseline: 2026-11-04

The public export still contains two October articles. The rolling seven-day
database report counted 253 discovered items, three production writers, three
quarantines and no completed independent review or new publication. Recorded
requests for the window total USD0.085778, including private/earlier test usage;
that number is not a claim that all six requests were production article calls.
No unresolved request was observed. The main rejection causes were wording
overlap, short text and an editorial response containing no facts. A free
selection check also found table-context holds, subject mismatches and access
reservations. None justify reducing the publication safeguards.

Free source inspection found Volvo HTTP 403, a Polestar client-rendered shell
without article metadata/text and client-rendered BYD indexes without extractable
release links. These three sources are NOT enabled as proven article sources.
Do not present these checks as successful editorial/live publication tests.
Private captures/reports stay under ignored `data/local/`.

## Verification Of This Slice

The production SEO build generated 90 routes, 38 retired-variant redirects and
the two-item RSS feed. Offline publisher regressions (49), wording regressions
(7), international coverage (5), RSS (6), reporting (5) and share briefs (2)
passed in targeted runs. Existing SQL publication, distribution and presentation
contracts passed. An isolated browser checked 1440px/390px news layouts, the RSS
link and endpoint with external requests blocked and no horizontal overflow.
No paid provider request or article publication was made by these checks.

The initial broad Windows suite ran 729 tests with two isolated PDF-parser
timeouts; a separate PDF rerun still hit the bounded child-process timeout.
The parser guard was not relaxed. Require Linux CI on the exact PR/main commit
before release, and do not describe the full local suite as clean.

## Delivery Status

### Source Follow-Up: 2026-11-05

The scheduled production and distribution jobs completed successfully overnight,
but no new eligible article or paid request was recorded. The rolling report
showed 262 discovered items; the same three historical production drafts remain
quarantined. This is a content-supply finding, not a successful new article.

Added the accessible official `www.polestar.com/global/news/` collection route,
not the client-only media host. Its explicitly configured single `main` region
requires exact canonical identity and article-specific JSON-LD publication dates;
related articles and modification timestamps cannot make a release new. The
observed canonical trailing slash is a declared source-specific link rule, not
permission for cross-host/query redirects. A fresh isolated source check passed
as `verified_no_recent_items`: all nine checked releases were older than seven
days. Body/date parsing is working, but no fresh article or AI review is claimed.

Discovery now excludes known other-manufacturer authorities before consuming
bounded lookup slots, while retaining joint announcements and neutral authorities.
Unrelated VW documents must not crowd out the original for a Toyota report.

Volvo still returns 403. BYD's own news component exposes a public read-only
search operation. The UK component returned no records; the German component's
actual declared parameters returned 53 listings, including a November release.
This is metadata discovery only: a bounded article-body/date adapter is not yet
verified or enabled. Neither source is enabled as proven article evidence. No workaround,
new service, paid model call, budget mutation or canonical-car write was used.
`check_news_sources.py --source polestar-news --max-items 3` repeats the free,
isolated readiness check without touching production news or provider accounting.

The explicit Volkswagen Group Sverige coverage retains Skoda, Cupra and Audi
lookups as well as Volkswagen. Joint-brand and neutral-authority lookups remain
possible; unrelated makers do not consume the bounded original-source slots.

The new region/identity tests (7), official discovery tests (17), broad-profile
tests (4) and publisher regressions (49) passed in targeted runs. The SEO build
again produced 90 routes, 38 redirects and the existing two-item feed. The broad
Windows run executed 743 tests and had three errors in the unchanged PDF-parser
tests (two explicit child-process timeouts and one dependent document result).
No timeout or publication guard was relaxed. The exact final PR and main Linux
CI must pass before normal credentialed production execution.

PR #33 subsequently passed all 134 steps on the exact PR and main commits.
The normal production job and both distributors succeeded. Polestar was recorded
as healthy but quiet in production; the run made no paid requests or new
publications. The canonical catalog retained all 76 variants and its prior hash.

### BYD Completion: 2026-11-05

The bounded German adapter now reads the actual index component configuration,
makes one uncredentialed public search query (page 1, at most 20 metadata rows),
and fetches at most `min(20, 3 * max_items)` candidate articles. It honors both
hosts' access policies, verified TLS, byte/delay bounds and no POST redirects.
It does not follow arbitrary endpoints from HTML or paginate through archives.

Article evidence comes only from exact canonical `/de/presse/` pages: one
`news-article` title/date header and explicit `news-text-block` narrative regions.
German publication dates must agree with the listing day. Corporate descriptions,
related stories and modification dates are not article evidence. Table-context
holds, literal evidence and independent writer/reviewer gates remain unchanged.
The adapter is included in the current publisher code identity, not any old proof.

A free isolated fresh check found one accessible release dated November 2 with
381 narrative words, and eight stale rows. It made no provider calls or public
writes. The available story is a German customer offer, not a new vehicle launch;
it is held before paid work. German vehicle/market/technology triage is supported,
with explicit exclusions for offers, hybrids, price recipes and rumours. A working
source parser is not an approved article. Checks for seven registered official
sources use batches of at most six; the existing per-batch safeguards remain.

Targeted BYD regressions (15), source-check regressions (7) and publisher tests
(49) passed offline. The SEO build still generates 90 routes, 38 redirects and
the existing RSS; no fake article or catalog change is used for release tests.

Google/Search Console is explicitly deferred by the owner on November 5. Do not
request another Google login, alter verification records or claim indexing.

### Continued Engineering: 2026-11-05

PR #34 completed BYD collection and German triage, with all 135 PR/main CI steps
and the production/distribution jobs passing. The actual November 2 BYD story
was held as a customer offer before paid work; no new article or charge resulted.

The next source/selection slice addresses observed gaps instead of lowering
quality rules. French SUV/body-style wording is recognized, Swedish nominations
are held, and fresh branded Motor articles on explicitly configured vehicle
routes may enter the existing eight-item free-reading queue despite thin RSS
descriptions. One existing publisher slot is reserved for recovery when needed,
without displacing official sources or increasing the queue. Clearly unrelated
drone/military stories are held. The actual body still needs EV evidence before original-source
lookup and every paid/writing/review/publication check. Dates, historical failed
URLs, prices, hybrids and speculation cannot use this metadata recovery path.

Operational summaries now aggregate known-brand original-source gaps as
`missing_authority` or `original_not_found`, without raw source prose/URLs.
They describe work remaining, not automatic approval or weakened verification.

Added the permitted NIO global pressroom: exact canonical, route/query/locale,
published/non-deleted state, rendered heading and main-body match are mandatory.
The original/display publication timestamps must agree within a day, with the
earlier timestamp used conservatively; modified,
created and URL dates are never substitutes. The current release has 99 words
and passes the actual v2 source/material precheck, not an AI audit. The free
source checker now tests official leads through that existing v2 collector,
while retaining the legacy word floor in the unchanged older extraction path.
Readability/material readiness is separate from verified facts/publication.

Added Toyota UK's verified RSS endpoint and exact Article metadata plus one
`entry-content` region in one `main`. RSS dates must match the fetched article;
stale metadata is held before a fetch, duplicates/conflicts and XML entities
fail closed. Related-gallery time elements cannot override Article publication.
The current qualifying EV item is old: a fresh capture of the October 27 page
produced 322 scoped words but remains stale, not a new live article. The feed is
healthy/quiet; NIO is accessible. An old NIO financial-release date conflict is
retained as a diagnostic, never corrected by using the fetch date.

These checks made zero provider calls/public writes. Toyota UK is not a Swedish
availability/price source; news never updates canonical cars. Recall reporting
cannot use a launch of the same model as recall evidence. Source access/identity,
literal facts, originality, exact refresh, independent review and both monetary/
publication limits remain in place. Require exact PR/main CI before operation.

Local verification: 18 new metadata/primary-format regression tests pass, as do
the existing publisher (49), pressroom (29), original-discovery (17), official
operation (19), broad-source (4) and readiness (8) suites. Strict empty article
bodies cannot fall back to page furniture; recall identity also checks Chinese
wording without ASCII normalization erasing it. The SEO production build passes
with 90 static routes and 38 existing redirects. These are offline/free source
checks, not six provider receipts or a published article. Full Linux CI remains
required on the exact release commit.

### XPENG And Lexus Original Sources: 2026-11-05

PR #35 is merged as `595bef2`, with all 137 PR/main CI steps and both distributors
passing. Production collected the new NIO source, but its delivery bulletin was
declined by the writer and remained quarantined. One settled call cost USD0.01253;
no independent review or publication occurred. Toyota UK was healthy but quiet.
The exact 76-variant catalog and existing limits were unchanged.

The next slice targets actual source-gap reports: XPENG and Lexus. XPENG's global
site is accessible but declares its homepage as article canonical and is not
approved by weakening identity rules. Instead, the Swiss importer's exact
`xpengswitzerland.pr.co` newsroom is declared with evidence of Hedin's appointment
by XPENG and its legal imprint on `xpeng-cars.ch`. No arbitrary pr.co newsroom is
trusted. Its public, declared Atom feed is discovery only; source dates, canonical,
one visible article/title and matching NewsArticle metadata remain mandatory.
Only explicit paragraph blocks are evidence, excluding company profile/contact,
copy/share tools, hidden elements, tables and related material. No images are used.

Lexus Europe and Lexus UK's public feed reuse scoped parsing: respectively one
`text_companyprofile` and one `entry-content` inside one main. Original Article
publication metadata must match the exact URL. Neither a UK/Swiss model launch
nor a foreign price confirms a Swedish variant, availability or price. Hybrid,
stale, price-only and thin/conflicting stories remain held by existing triage.
The broad registry now contains 24 configured sources, not 24 article approvals.

Free live collection: XPENG returns three accessible current variants of its
Swiss G9L launch (661-800 words), all held as foreign-price stories before AI.
Fresh English G9L/L05 fetch-and-refetch checks retain exact source hashes, with
751/456 scoped words respectively. Lexus Europe has only stale EV releases;
Lexus UK's valid RSS currently contains unrelated non-EV items. Report the latter
as healthy/quiet only when a real nonempty parsed feed has no matching routes;
malformed, cross-host and truly empty feeds remain failures. Structured-title
HTML entities are decoded once for comparison, preserving exact model identity.
The source checks made zero provider calls or public writes. All 157 targeted
regressions and the Vite production build pass; full Linux CI remains required.

No source-specific paid admission trial, key, permission, migration, canonical car
write, Google operation, spending increase or historical-proof change is included.
Run free source checks, offline regressions/build and exact PR/main CI before
normal owner-enabled production and fixed-target public distribution.

### Output-Size Follow-Up: 2026-11-05

PR #36 merged as `5f22a29` after 138 PR/main CI steps. Production verified the
XPENG importer and both quiet Lexus feeds. Its normal run then stopped on a new
Bevolt/XPENG candidate: the writer returned `incomplete/max_output_tokens` at the
existing 2000-token ceiling (311 reasoning tokens). The charge, USD0.025572, is
fully settled; total UTC-day news cost became USD0.038102. No review, article or
distribution occurred. The failed URL/receipt remain unchanged and are not retried.

The follow-up returns one complete article from the same source-bound fact set,
not two alternative full articles squeezed into that ceiling. Existing 2000/1300
writer/reviewer limits, 150-250 words, independent review and all quality gates
remain. Historical two-form outputs remain readable without changing their raw
receipts. This is a smaller response contract, not a new model or higher allowance.
An irrelevant/thin story may explicitly return `relevant=false`, `facts=[]` and
`article=null`, instead of a schema forcing it to fill an unsupported article.
The existing precheck still rejects that packet; relevant null articles cannot
pass. No reviewer is bought for a decline.

Failure summaries expose a fixed safe category and retain skipped-source gaps,
without raw exception messages, private prose or keys. Incomplete responses still
fail the run and cannot trigger a reviewer, continuation, repair or new candidate.
Both today's candidate slots are consumed; any verification run must defer before
paid work. No more paid attempts are authorized by this follow-up. Offline tests
do not prove that the next fresh production response will complete.

Offline verification passes 170 targeted regressions, including single-current
output and historical-alternative compatibility, literal evidence, incomplete
settlement/no-retry, the shared attempt limit and sanitized diagnostics. The SEO
build passes with 90 routes and 38 redirects. Exact PR/main CI is still required.

The observed limit behavior agrees with the
[official Responses reasoning documentation](https://developers.openai.com/api/docs/guides/reasoning):
the output ceiling includes reasoning, and reaching it may return an incomplete
response. We reduce requested output rather than increasing the existing ceiling.

### Continuing Operations

1. Pass offline regressions/build, review the isolated branch and require exact
   main CI before any credentialled distribution. No automatic merge or paid
   private admission tests are needed for individual publishers.
2. Verify the next normal production outcome and public delivery; do not retry
   historical rejected URLs. A month of real production/reading results cannot
   be replaced with fixtures or declared complete on implementation day.
3. Volvo remains held on HTTP 403, not a blocker to the working source set.
   Do not bypass access rules or present blocked sources as enabled evidence.
4. Search Console remains deferred until a new owner decision. Cloudflare traffic
   and real operational reports remain separate; infer no Google visitor figures.
5. Use the weekly reports and genuinely published articles to evaluate the
   month before buying traffic. No external posts or new paid services here.

## Budget And Compatibility

The observed production pair is still USD0.25/day and USD5/month. Migration 022
requires its separate approval before the previously approved USD0.50/USD10
pair becomes active. Never reset existing usage or infer activated API credits.
Pricing approval expires 2026-11-21; paid work must stop then unless explicitly
renewed after price verification. Notice publication remains OFF. No canonical
car data, historical receipts or mixed-format proof hashes are changed.
