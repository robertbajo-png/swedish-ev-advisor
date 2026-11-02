# European News Sources

Owner request: 2026-11-02. Extend the existing shared-template pipeline, not a
new editorial engine, service, budget, schema or paid admission process.

## Scope And Sequence

1. Inspect the source registry and test real feeds, article access and ownership.
2. Add reachable sources through the shared identity/layout templates. Preserve
   access restrictions, exact dates and canonical URLs; unknown layouts hold.
3. Test extraction boundaries and multilingual selection, then run all news
   regressions, transactional SQL checks and the production build.
4. Merge only reviewed green CI. Run the existing automatic workflow on the exact
   green main version, with unchanged budgets and publication rules.

## Active Additions

- Bevolt, the successor to Automobile Propre, has a working same-host RSS feed
  at `https://www.bevolt.com/feed/rss/`. Its own announcement confirms the name
  change. Keep the historical Automobile Propre identity and records; do not
  follow arbitrary cross-domain redirects or count the two names as independent
  publishers. Both belong to the BRAKSON group.
- Motor has a working public RSS feed at
  `https://www.motor.no/?lab_viewport=rss`. Its contact page identifies NAF as
  owner. This provides Nordic reporting and tests; Motor and NAF are not two
  independent editorial groups. NAF's own dynamic El Prix index has no usable
  static article list and is not falsely advertised as an active news feed.

Bevolt is limited to automotive news and tests, excluding its energy/two-wheel
sections. Motor is limited to article routes, excluding travel/category pages.
Use the exact `data-article-content` region or `bodytext` class respectively,
not every semantic article (which includes unrelated recommendation teasers).
French/Norwegian EV terms enter the existing free relevance selection; prices,
hybrids and speculation are still held. Publication retains the actual relevance,
source evidence, originality and independent-review gates.

## Held Sources

The free 2026-11-02 probes found editorial robot reservations at electrive,
Electrek and CnEVPost; InsideEVs article requests returned HTTP 403. They are not
new article-production sources. Publicly accessible permitted metadata can still
be discovered. CnEVPost's former corroboration template is removed so its current
reservation cannot be mistaken for usable AI evidence. Feed access is never a
substitute for article access. Auto Express's feed was robots-disallowed and
CleanTechnica's crawl delay exceeded the existing bounded run limit.

No login, proxy, search snippet, cached blocked text or feed body bypass is used.
All original failed trial URLs, charges and receipts remain unchanged. Sources
never update canonical car specifications or prices. Existing USD0.25/day,
USD5/month and one article per UTC day are unchanged; no extra paid source trial
is needed.

## Identity References

- Bevolt's own announcement:
  https://www.bevolt.com/fr-fr/automobile/actualites/voitures-electriques/344646-bevolt-nouveau-nom-automobile-propre/
- Bevolt's identity: https://www.bevolt.com/fr-fr/a-propos/
- Automobile Propre's ownership: https://www.automobile-propre.com/mentions-legales/
- Motor ownership: https://www.motor.no/aktuelt/kontakt-oss/103104

Private live captures/access reports stay under ignored `data/local/`. Committed
tests are synthetic; they are not real AI approvals or published articles.

## Verification

The local 2026-11-02 run passed all 651 news tests, automation guards and
transactional publication/budget SQL checks. The production build generated 90
routes, preserving all 76 vehicle routes. Four real permitted article captures
(two per new publisher) passed the common parser with original publication dates,
bylines and source hashes. Motor's conflicting feed/page dates remain a hold,
not an instruction to use the newer date. These parser checks made no paid AI
calls and do not constitute live editorial approval.
