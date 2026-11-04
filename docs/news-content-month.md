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

## Remaining Rollout

1. Pass offline regressions/build, review the isolated branch and require exact
   main CI before any credentialled distribution. No automatic merge or paid
   private admission tests are needed for individual publishers.
2. Verify the next normal production outcome and public delivery; do not retry
   historical rejected URLs. A month of real production/reading results cannot
   be replaced with fixtures or declared complete on implementation day.
3. Investigate structured/sitemap delivery for the three held pressrooms using
   permitted public endpoints. Keep them disabled until body/date/identity and
   source evidence actually validate. Do not bypass 403, logins or TDM policy.
4. Verify Search Console ownership and sitemap processing when owner access is
   available. Then measure indexing/impressions/clicks, not guessed visitors.
5. Use the weekly reports and genuinely published articles to evaluate the
   month before buying traffic. No external posts or new paid services here.

## Budget And Compatibility

The observed production pair is still USD0.25/day and USD5/month. Migration 022
requires its separate approval before the previously approved USD0.50/USD10
pair becomes active. Never reset existing usage or infer activated API credits.
Pricing approval expires 2026-11-21; paid work must stop then unless explicitly
renewed after price verification. Notice publication remains OFF. No canonical
car data, historical receipts or mixed-format proof hashes are changed.
