# Shared News Source Policy

Owner approval: 2026-11-02. Simplify source onboarding and review each article,
without changing canonical car data, historical trial receipts or cost limits.

## Implementation

1. Move source-specific layouts/ownership to a declarative template registry.
   Reuse the same canonical/date/article-body and access checks. Unknown layouts,
   ownership or reuse permission are held, never guessed by AI.
2. Prefer official evidence; otherwise discover matching reports in the existing
   metadata index. Require two distinct verified editorial groups, no circular
   attribution, shared wire/reprint or mismatched event. Shared official releases
   remain reported company claims, not independent technical verification.
3. Bind every reported fact to literal evidence from both publications, preserve
   dates/markets/units and show attribution. Writing and a separate final review
   apply to the exact article. No extra paid source-admission round is required.
4. Replace automatic source qualification with the common article worker. Preserve
   USD0.25/day, USD5/month, one article and one automatic attempt per UTC day.
   Rejections stay private and do not fail normal operations; accounting/security
   errors still stop the worker. Failed historical URLs never automatically retry.
5. Test source identity, independence, evidence, publishing and budget contracts;
   run the full regression/build and exact-main CI before production operation.

## Operator Experience

An owner supplies a website. The assistant checks its public identity/feed/reuse
rules and adds one template entry, not a new extraction engine or paid test suite.
Ownership evidence belongs in configuration; unknown ownership cannot count as
one of two independent publications. Normal operation needs no article selection,
writing or approvals. Notify the owner only about publication or actionable errors.

The vehicle database retains its stronger manufacturer/importer validation policy.
Price notices retain their separate disabled publisher. News cannot confirm a
Swedish price, variant availability or specification in canonical tables.

## Offline Verification

On 2026-11-02, 639 news regression tests passed, including exact-article
publication with mocked provider receipts, dual-source attribution, conflicting
numbers, common ownership, circular reporting, private-test isolation and
historical rejection preservation. The automation contract and transactional SQL
checks passed. The production build generated 90 routes, including the unchanged
76 vehicle routes. These are offline tests, not real paid article approvals.

Initial templates cover CarNewsChina and The Driven as lead sources; CnEVPost
can corroborate a matching report. More registered publishers can use the same
template after identity, access rules and article layout have been checked.
An unreachable source or missing independent support is skipped, not presented
to the owner as another routine approval task.
