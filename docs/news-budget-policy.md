# News Budget Policy

The owner approved USD0.50 per UTC day and USD10 per UTC month on 2026-11-04.
Migration 022 changes only the budget constraints and configured limits. It does
not enable AI, publication or notices, change pricing validity/model, reset any
usage, issue a trial permit or publish an article. The one-article daily ceiling
and two-distinct-candidate ceiling are unchanged. API credits are not assumed to
be active, unlimited or cash-free; these are gross usage ceilings regardless of
how the API organization pays.

## Deployment

1. Test and deploy code that accepts the old and new exact budget pairs.
2. Keep historical trial code/permits and the original mixed-content proof pinned.
3. Obtain separate owner approval to install migration 022. Reject unknown
   configuration, unresolved usage or unexpected notice activation.
4. Apply the migration through the existing verified-TLS owner connection in one
   transaction. Check that only limits/approval note and their constraints change.
5. Read back production config, remaining allowance, historical charges, public
   articles and canonical catalog. No paid test is needed for a budget change.

The active shared article worker reads `news_budget_policy.py`; preflight and
encrypted read-only backups accept either approved pair during rollout. Mixed
pairs or larger limits fail closed. The old pinned short/trial worker retains its
original USD0.25/USD5 guard and conservatively defers under the new pair; it does
not acquire new spending authority. Current shared-template production continues
using its existing sources, exact evidence and independent per-article review.
No historical proof hash or request payload is rewritten to expand a budget.

At 2026-11-04 11:17 UTC the database showed USD0 spent that day and USD0.076824
that month. The increase is headroom, not a remedy for missing evidence or poor
writing. Routine source and quality rejections remain quarantined.
