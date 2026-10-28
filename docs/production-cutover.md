# Production Cutover

## Verified Status: 2026-10-28

- Reviewed main: `9cac4b71cc2f8ffb44b7f0515c29ce83b972c669`, PR #9.
  PR and exact-main CI each passed 115 steps. Distribution 40609289080 passed.
- The existing AI preview passes the read-only HTTP deployment check: five app
  routes, health JSON, the 76-variant canonical export and sitemap. It is noindex.
- The public production origin still serves Loopia parking, not the app.
- The authenticated Cloudflare CLI lists only `seekev-ai-preview` and
  `seekev-preview`. D1 lists only `elbilsagenten-ai-budget-preview`. This does not
  establish an isolated production hosting/budget setup.
- A read-only query verified the preview's budget policy/reservation tables.
  The D1 listing's `num_tables: 0` is not evidence of an empty database.
- Preview readiness reports catalog/configuration/budget checks true, AI enabled,
  zero paid calls and `provider_tested: false`. This is configuration evidence,
  not a successful paid inference test.
- The production configuration gate still blocks on `privacy_review`.
  Browser and desktop control timed out; the owner was asked for a non-secret
  screenshot binding the OpenAI sharing settings to the actual organization/project.

## DNS Baseline And DNSSEC

Observed public apex and `www` records, not a full registrar-zone export:

- NS: `ns1.loopia.se`, `ns2.loopia.se`.
- A: `194.9.94.85`, `194.9.94.86` for apex and `www`.
- Apex MX, TXT, AAAA and CAA queries returned no records.
- Cloudflare and Google DNS-over-HTTPS both returned authenticated DS evidence:
  key tag `12412`, algorithm `8`, digest type `2`, TTL 3600.

**DNSSEC is active. Do not change nameservers while leaving the old delegation
signer record in place.** Inventory the actual registrar zone and DNSSEC controls,
preserve records and prepare rollback before any change. Public apex queries do
not discover every subdomain or mail record. Keep `boleoai.se` and its verified
contact-mail route outside this website cutover.

For an apex Pages domain, Cloudflare requires the zone and its nameservers in
the same Cloudflare account as the Pages project. An externally managed `www`
CNAME is a separate subdomain option, not a substitute apex configuration.
First associate custom domains with the intended Pages target; merely pointing
a CNAME at a preview can fail or route to an unintended production branch.

Reference: [Cloudflare Pages custom domains](https://developers.cloudflare.com/pages/configuration/custom-domains/).
Exact new nameservers and production target have not been allocated/approved;
do not invent them or attach the public domain to the AI-preview branch.

## Remaining Execution Order

1. Finish and document the account-specific supplier/privacy checks in
   `privacy-operations.md`. Owner policy approval is already recorded; do not
   repeat it or mistake a valid API key for a completed account review.
2. Verify/prepare isolated production Pages, D1 policy and server-only secrets
   on the existing account. Reuse the owner-approved local OpenAI key safely.
   Do not copy the preview budget/salt or grant preview CI new DNS/D1 permissions.
   Keep AI disabled until its bounded production setup has been verified.
3. Build from reviewed green main with `node scripts/build_release.mjs` after
   the actual gates pass. The guard must reject an incomplete release.
4. Deploy a noindex candidate and verify assets, public canonical data, HTTPS,
   budget readiness, rollback and security headers before the DNS cutover.
5. Preserve the registrar-zone baseline, handle the old DS/DNSSEC delegation in
   the registrar-supported order, associate apex/`www` with the right target and
   change only the approved domain records/nameservers. Do not affect mail.
6. Verify propagation/TLS, restore DNSSEC with the correct new DS when supported,
   confirm redirects and indexability, then run the production-only verification:

   ```text
   node scripts/verify_deployment.mjs https://elbilsagenten.se --production
   ```

The production check is GET-only. It requires the exact production origin,
one correct canonical per route, no HTML/header noindex, nosniff, the exact
approved canonical catalog hash/content and sitemap, the approved indexable
robots policy, and live catalog/AI-configuration/durable-budget readiness.
It rejects a redirect into preview and never calls the AI provider. This does
not replace the privacy gate, DNSSEC/registrar verification, rollback proof or
an explicitly authorized provider smoke test.

No DNS, nameserver, account permission, secret, production resource or budget
was changed during this preparation. News AI and both news publishers remain off.
