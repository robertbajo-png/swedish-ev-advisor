# News Follow-Up17November2026

Ordinary budget only: USD0.50perUTCday, USD10month and one publication/day.
The16NovemberUSD5test ceiling expired unused and is not renewed implicitly.
No historical quarantine, charges, receipts or canonical vehicle data are reset.

| Phase | Status | Evidence |
| --- | --- | --- |
| Diagnose scheduled outcome | Verified | First17Novembercron consumed2candidates: missing p1attribution and an explicit writer decline. Both settled; USD0.021030today,0published,0unresolved. Later cron respected the2candidate limit. |
| Diagnose distribution | Verified | Run44097008710 used upload_required=false and failed only because the GET verifier read checkout-era sitemap XML instead of generating its expected artifact from the current validated snapshot. Existing website/public news were not missing. |
| Offline repair/tests | Passed |949offline news tests, production build and workflow guards passed. The new generator regression and3attribution tests preserve strict sitemap equality, per-block attribution and independent review. Real read-only qualification remains passed; remaining ordinary day budgetUSD0.478970. No new paid call. |
| CI and deployment verification | Preparing PR | Exact-head/current-main CI, then the existing distributor on an unchanged snapshot. No paid generation is needed to test delivery. |
| Additional fresh article attempts | Awaiting candidate-count approval | Only if separately approved: at most6TOTAL production candidates today, including the2already spent, within ordinary caps. Never retry either quarantined URL. Stop on the first publication or uncertain usage. |
