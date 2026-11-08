# Flexible Newsroom Policy

## API Schema And Approved Budget Follow-Up

The additional 2026-11-08 production request was rejected with HTTP 400,
`invalid_json_schema`, parameter `text.format.schema`, before a model response.
No new text or review was produced. The specific rejected schema rule is not
known because diagnostics deliberately retain only safe machine-readable fields.
Do not claim a confirmed model-quality problem or an actual zero charge.

The owner approved conservative closure of the full USD0.09145 reservation and
installation of migration 022 (USD0.50/day, USD10/month). The charge remains in
accounting with unknown actual use, and the failed URL stays excluded. No older
charges, canonical cars, published articles, model or one-publication/day cap change.

V3 now keeps untrusted headline text in the prompt, not an enum in the provider
schema. Exact event identity is still checked locally. Writer/reviewer provider
schemas retain strict object shape, required fields, enums and no extra properties,
but omit model-dependent numeric/array bounds. All those limits remain mandatory
in local precheck/review before publication; historical schema modules are unchanged.
This portability mitigation requires a fresh accepted API response before it can
be described as live-verified, not just an offline schema test.

The 2026-11-08 bounded run then obtained three completed, settled writer responses
without schema errors (USD0.025690 total). One 115-word IM Motors draft failed
precheck; the recall and advice cases declined. No independent review or new
publication occurred. These are not successful editorial release proofs.

The follow-up binds the writer's fixed `s0` event reference to the exact fetched
headline in the existing resolver. Raw provider output and all visible prose
remain unchanged. Literal numeric/unit checks combine complementary spans within
the SAME source; each separate newsroom still has to cover the whole fact, and
sensitive claims retain official/two-independent-newsroom requirements. Exact
source/hash/identity checks and final independent review remain mandatory.
Advice/how-to headlines are now filtered without AI. Historical rejected drafts
stay quarantined; these fixes never promote them or reset the daily attempt count.
867 offline news tests and the production build passed for this follow-up.

Official reference: https://developers.openai.com/api/docs/guides/structured-outputs

## Owner-Requested Additional Attempts

On 2026-11-08 the owner requested further paid attempts until a good result.
An explicit production invocation may use `run --max-candidates 6
--owner-approved-day YYYY-MM-DD`, for that exact current UTC day only. Six is
the TOTAL including earlier attempts, not six additional ones. Scheduled and
default work still use two. No private-trial expansion, budget reset, new money
exception, old URL retry or old-proof promotion. Full pair reservation,
unknown-usage stops, independent audit and one publication/day remain mandatory.

The v3 language follow-up recognizes an extracted showing/reveal as a generic
presentation only when the cited literal source also explicitly describes that
event. It never promotes a showing into orders, market launch or deliveries,
and does not accept statistics merely saying a number "shows" something. The
writer is also instructed to distinguish scale models from variants and cite
all facts needed for equipment/event/condition clauses. Historical recipe and
fact-plan modules are unchanged; previously failed texts remain quarantined.

Owner approval: implement all five proposed editorial relaxations. This affects
the shared article publisher, not canonical vehicle ingestion or historical trials.

## Implementation

1. Keep free source-based eligibility and priority (Sweden, Europe, international
   developments and recency) before provider calls. Remove post-writing numeric
   significance/Swedish-relevance thresholds. Scores remain honest diagnostics,
   not proof of factual correctness. Advertising, corporate calendar items,
   unrelated content, speculation, duplicate events and stale sources stay held.
2. Short news: 80-149 body words and at least two distinct supported facts.
   Standard: 150-250 words and at least three. Both allow up to six facts and
   one to five body paragraphs. The model should shorten, not pad. Body word
   count includes the intro, not the headline. No fake recommendations/analysis.
3. One registered official release is sufficient for attributed company claims,
   not independent measurements or verified Swedish availability. This existing
   route is retained, not replaced by a fabricated two-source bundle.
4. Prefer official corroboration, then a genuinely independent editorial pair.
   If unavailable, one approved newsroom may support explicitly attributed
   ordinary developments. Sensitive claims (performance, range, charging figures,
   safety, availability) require official evidence or complete matching support
   from two independent newsrooms. Every fact still needs literal evidence.
   Prices/campaigns remain on the separate, unchanged notice route.
5. Independent review judges the exact final article, source/fact consistency,
   clarity, originality and honest market/claim qualifications, not its numeric
   newsworthiness score. It reviews all supplied excerpts for contradictions,
   not only the ones selected by the writer. All facts/blocks must pass.

## Integration And Safeguards

- Version `news-article-review-2026-11-v3` prevents old proofs being reinterpreted
  as new approvals. v1/v2 remain in attempt history and never become retries.
- Single-newsroom bundles retain identity, content hash, original publication
  date, fetched date and attribution. They are visibly described as one newsroom,
  not two independent sources. Source refresh still re-fetches exact documents.
- Known conflicting original dates do not degrade to the one-newsroom fallback.
  An inaccessible original is not permission to invent its content or bypass
  source access rules. Unvalidated tables continue to quarantine.
- The scheduler chooses the shared v3 worker when enabled instead of spending
  its first candidate on the older fixed-format writer. Historical release
  proofs, legacy tests, notice switches and all production transaction guards
  are unchanged.
- Existing model, 2000/1300 output token caps, packet/evidence bounds, durable
  reservations/settlement, monetary limits, two candidates/day and one published
  article/day remain. No new key, service, migration or budget expansion.
- Public pages/export still read only published records. News never overwrites
  canonical car data. Article format is stored privately for traceability.

## Verification

Synthetic offline regressions cover short/standard lengths, distinct facts,
low honest relevance scores, single official/editorial sources, sensitive facts,
conflicting values, source identity/attribution, exact review/receipt binding,
old-policy exclusion, unchanged pair spending bounds and a complete private
writer/reviewer lifecycle. Full news regression suite and production build must
pass before merge. These are code checks, not real live AI reviews/publications.

No historic quarantined draft is released by this change. New publication still
requires a new eligible source, paid writer and separate reviewer with settled
receipts, exact fresh source revalidation and the existing transactional gates.

Local verification: 856 offline news tests, production Vite build and package
secret guard passed. No paid call, new public article or production data mutation is
part of implementing the policy; scheduled production uses it after reviewed
main CI. A successful live publication must be reported separately.

CI bootstrap: three attempts failed before tests because GitHub release assets
returned HTTP 504 for Bun. Install the official npm `bun@1.3.13` package in CI,
matching the locally tested runtime, rather than the mutable latest GitHub ZIP.
Use the same bootstrap for the news production/preview distributors so new
articles do not hit the identical download failure at upload. Targets, public-only
credentials and unchanged-snapshot conditions remain. This changes no application
dependencies, lockfile or test/publication gates.
