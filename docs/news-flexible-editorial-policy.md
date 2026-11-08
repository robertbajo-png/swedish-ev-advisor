# Flexible Newsroom Policy

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
