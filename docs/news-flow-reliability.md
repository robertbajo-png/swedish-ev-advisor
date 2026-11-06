# News Flow Reliability

Owner request, 2026-11-06: complete selection, original-source evidence and
independent writing improvements, then verify the production chain where needed.
Keep Sol selected, existing spending/attempt limits, canonical vehicles, historical
quarantines and all factual/originality/publication gates unchanged.

## Execution

1. Implemented: real rejection records identified European developments being
   judged only as Swedish-market news. Add a European development route with
   significance >= 0.65 and weighted coverage >= 70. Global thresholds remain
   0.8/75. Require visible actual market and independent scope review. Reject
   minor publicity, podcasts, reader questions, theft and venue openings.
2. Implemented: rank direct primary links by manufacturer and subject before the
   existing bounded fetches. Distinguish smart #2/#5 and ID.7/ID.4. Add the exact
   smart European pressroom with original date, identity and qualification guards.
   Wrong manufacturers cannot consume the two direct-link slots.
3. Implemented: shorter evidence-bound instructions, one article with distinct
   paragraphs and no repeated conclusion. Keep 150-250 words, the same token
   caps, literal evidence and independent reviewer. No rewriting/retry loop.
4. Verified implementation via PR #40 and exact current-main CI: 143 steps,
   including the unchanged PDF isolation tests, production build and browser QA.
   The normal production run completed with `no_eligible_new_source`, 32 held
   candidates, no paid model calls and no publication. Production GET/TLS checks
   passed. Future actual article/public delivery still requires fresh evidence
   and the existing approved workflows/allowances. No old draft is promoted.

Each result must distinguish offline fixtures, free source retrieval, actual
writer/reviewer receipts, publication and delivery. A green workflow is not proof
of a newly published article. Private diagnostics stay under ignored `data/local/`.

## Verification So Far

- Offline: eight coverage, 19 original-source discovery, six smart source/identity,
  eight writing, 19 official lifecycle and four broad-registry tests passed.
  The initial Windows-wide run covered 812 tests; its three isolated PDF parser
  timeouts passed in Linux without guard changes. Two stale fixture expectations
  were corrected and passed. A redundant slow local SSR render was stopped after
  the exact Linux build and full UI checks passed, not reported as a local pass.
- Free source check: smart index and an actual 2026-11-05 release were retrieved
  with normal TLS/access checks, original publication time and a saved hash in an
  isolated SQLite store. The customer-service announcement was correctly held
  as lacking a concrete EV development; accessibility is not article approval.
- No paid calls, publications, canonical vehicle writes, schema changes, budget
  changes or historical-draft promotions performed for these improvements.
- Production remains Sol. The separate Terra preparation branch is not included.

## Free Production-Queue Follow-Up

The actual eight-candidate preview made no AI calls or writes. It correctly held
all eight for inaccessible or insufficient exact primary/independent evidence.
It also exposed an overly broad discovery fallback: smart #2 searches could spend
bounded fetches on #5 index entries after strict matching had rejected them.
Apply the same disjoint-model check before that fallback, without increasing the
fetch/paid limits or promoting any of those held candidates. A follow-up regression
covers smart, VW, BMW and IM models, plus valid joint-model announcements.
Normalize explicit apostrophe-s before brand matching too: Unicode possessives
such as BYD's must not become an unidentified manufacturer after ASCII folding.

PR #40: https://github.com/robertbajo-png/swedish-ev-advisor/pull/40

Exact main CI: https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/42224481905

Normal production run (completed without an eligible new source or paid calls):
https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/42225294667
