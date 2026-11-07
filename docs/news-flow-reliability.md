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

## Selection And Evidence Corrections, 2026-11-07

Current status: upstream selection/evidence can reject usable material before
writing. This change fixes those deterministic cases, not the model or budget.
Missing proof: a fresh independently reviewed production article from this exact
code. Offline acceptance and accessible content are not that proof.

Small implementation slices:

1. Subject selection: assess rumour language in the headline/opening rather than
   rejecting a confirmed launch for a later mention of potential. Accept a launch
   whose source headline includes an incidental price; keep price-change/offers
   held and explicitly exclude monetary facts from generated articles. Euro NCAP
   is not a currency amount. Require real EV evidence and the original fresh date.
2. Coverage: concrete European charging-network expansion/access developments use
   the existing European thresholds and independent scope review. Financing,
   awards, local non-European station openings and unproven vehicle connections
   do not qualify through this route.
3. Matching: reuse exact model identities and bounded multilingual event concepts.
   A specific update needs shared action/topic plus model or existing-fleet scope;
   a launch needs the exact model and actual European scope. Reject conflicting
   models, markets, reporting periods or topics. Technology labels such as V2G
   and CO2 cannot hide a model conflict. Ownership, copying, circular reporting,
   dates and per-fact dual-source evidence remain separately checked.
4. Evidence: collect short labelled fields only in exact contiguous windows with
   a recognized model header and its variant/conditions. Handle the real flattened
   HTML text shape without inserting invented newlines. Keep missing context,
   new-model boundaries, byte/word limits and unvalidated-table holds.

Changed files: `AGENTS.md`, this document,
`scripts/news_publisher_selection.py`, `scripts/news_reporting_policy.py`,
`scripts/news_publisher_articles.py`, and
`tests/test_news_publisher_selection_fixes.py` (already covered by the existing
publisher-test CI glob). No schema, vehicle, source-registry or UI changes.

Free source checks used the existing collector with normal TLS/access rules and
an isolated SQLite store; no Supabase writes, provider calls or publication:

- Mobility Sweden's 2 November October-registration release was accessible with
  a fresh original date and passed the pre-writing material gate. This is source
  readiness, not verified extracted facts or an approved article.
- Volkswagen's checked global releases were older than the seven-day window.
  Swedish VW award-finalist releases remained held as minor publicity.
- BMW's global index returned a cross-domain redirect and remained blocked.
- XPENG's Swiss English/Italian G9L releases were accessible but stayed held:
  the extracted English narrative did not establish the explicit EV connection
  required by this classifier; the Italian price-bearing headline did not qualify
  as a supported launch. No brand-only inference or guessed translation was used.
- Toyota UK's checked relevant release was stale. No fetch date replaced it.

Operational limits and production switches were not changed; historical rejected
URLs/proofs remain untouched. Next recommended task: current-main CI and then a
budget-checked, genuinely fresh writer/reviewer case through the existing worker,
not a retry of these old/private or previously rejected candidates.

Local verification: all 830 `test_news*.py` tests passed, including 15 new
positive/negative regressions, with no provider requests. `bun run build` passed
(the shell did not expose `npm`; no dependency install was needed). Scoped
`git diff --check` passed. No full-browser QA was needed for this backend-only
change; this is not a claim of a new article or deployment.

## Deployment Follow-Up, 2026-11-07

PR #42 was merged as `54ee99712e4d4312ed08a9b97ca588b3171d5f27` after
143 passing PR checks. All 143 exact-main CI checks also passed. Remote preflight
was ready: Sol, USD0.25/day and USD5/month, one article/day, no unsettled request,
USD0 spent this UTC day and USD0.1397 this month. Existing conservative historical
accounting remained intact. No activation or financial limit was changed.

The free current-queue inspection then exposed an additional incorrect primary
match: an unknown-brand Chery Tiggo report could match a Volkswagen release via
generic terms and a competitor mentioned in its body. No paid call was made.
Hold the live run until this upstream identity bug is corrected and checked:

- Use the actual registered publisher when a primary headline omits its brand.
- A brandless report may use a manufacturer primary only with the exact model
  identifier in both headlines and the manufacturer explicitly in its narrative.
  Body-only competitor mentions cannot establish the report subject.
- Apply the same rule to official discovery before spending bounded fetch slots,
  and recheck primary identity during final artifact validation as defense in depth.
- Preserve general institutional/battery stories and correctly model-anchored
  brandless headlines. Do not require a new hardcoded brand entry for each case.

This follow-up touches selection, primary discovery, article validation, their
regressions and project documentation only. It does not itself buy an article,
publish data, install a migration or retry a historical paid/private draft.
