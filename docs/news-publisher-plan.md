# Publisher Article Expansion

Owner request, 2026-11-01: implement, test and connect CarNewsChina and The Driven
within the existing shared news allowance. No car data or historical proofs change.

## Current State

Both feeds and article access have been checked. Discovery already runs in GitHub
Actions; the two-source short publisher cannot consume these reports. Keep its
exact proof/hash and approved formats unchanged.

## Implementation

1. Add bounded source adapters: exact publisher hosts/date paths, article-specific
   publication metadata, accessible article text, canonical URL, SHA-256 and fresh
   collection. Respect robots/TDM/paywalls; never use a challenge page or refresh
   an old publication date. Locate corroborating official sources through a narrow,
   verified registry, not arbitrary AI-selected URLs.
2. Add a separate short format. Combine structured fact selection and a 150-250
   word original Swedish draft in one paid writer call, followed by a separate
   independent fact/originality review. Every claim has exact literal evidence;
   central claims require approved official support. Evidence IDs resolve to exact
   deterministic source spans; retain the raw writer output for receipt comparison.
   Foreign
   market/currency/driving-cycle/charging qualifications must be preserved. Thin
   or Sweden-irrelevant evidence is held before buying a draft where possible.
3. Reuse durable reservations, settlement, three quality gates and transactional
   publication. Validate actual provider outputs/receipts, exact source/draft
   hashes, duplicate events and the global one-article-per-UTC-day limit. Price
   notices, failed old trials and existing source proofs are not promoted.
4. Test synthetic adapters, evidence, originality, freshness, deduplication,
   accounting, publication and worker integration offline. Run fresh private
   source trials only after these pass and only if the full bounded call pair
   fits the unchanged USD0.25/day and USD5/month allowance. Failed trials stay
   quarantined; no automatic paid rewrite loop or budget exception.
5. Require a real successful source-specific proof before that adapter can publish
   in the existing main-only GitHub job. A separately armed private qualification
   step may try at most one different fresh story per UTC day within the same budget
   and global daily attempt marker. It never retries a previously tested URL or
   publishes a candidate. Reuse separate public-read-only production distribution.
   Run CI/build and verify actual flags, receipts and delivery.

## Reporting

Record actual paid costs, source/receipt IDs, held reasons and deployment results
privately. Public runbooks contain operational rules, not private article drafts,
keys or trial authorizations. Distinguish a configured adapter, a passed live
proof and a genuinely published article. Never claim one as another.
