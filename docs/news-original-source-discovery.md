# Original Source Discovery

Owner request: extend original-source discovery and verification without weakening
publication rules or increasing the shared budget.

## Execution Plan

1. Inspect actual held stories, outbound source links and approved authorities.
   Current gaps are a short host allowlist, two hardcoded discovery subjects,
   no reuse of the official metadata index and opaque rejection messages.
2. Add a declarative official-source registry and a bounded discovery chain:
   direct citations, existing official metadata, then relevant official indexes
   or feeds. Never guess URLs or fetch arbitrary model-selected domains.
3. Re-fetch candidate originals, verify authority, subject/model/date and source
   hashes, and retain discovery provenance. A found URL is not verified facts.
4. Add offline regressions for wrong models, old/future material, hostile URLs,
   reservations, bounded crawling, changed sources and diagnostic traces. Run
   all news tests, SQL guards and the production build.
5. Test permitted real sources without paid AI or publication, then use reviewed
   green-main CI for the existing automatic worker. Preserve all old attempts,
   publication guards, vehicle data, owner switches and budget ceilings.

## Boundaries

Official discovery does not grant extraction rights or publication approval.
Blocked articles are not replaced with cached/search-snippet text. Thin,
conflicting, stale or unparseable documents stay held. Canonical car data is
never updated from this news pipeline. No paid source-admission test is needed.

## Implemented

- Candidates come from direct article links, already collected official metadata
  and declared official indexes/feeds. New models do not require bespoke Python.
  The metadata shortcut still fetches the actual original; feed summaries never
  count as verified source facts.
- Existing VW, VW Sverige, BMW and ACEA registry paths are reusable, with explicit
  GM, PFA, OFV and AAA DATA authority/path profiles. A profile does not grant AI
  access or approve publication.
- The generic registry lookup uses at most two declared indexes/feeds; a report
  checks at most six original candidates, alongside the preserved legacy policy
  companion lookup. Official index responses/failures are reused within a run. No search
  provider, guessed URL generation or paid AI lookup is added.
- Hash-bound catalog/index provenance follows each matched original. Publication
  refreshes the exact reviewed documents, not a newly selected replacement.
  Matching article JSON-LD can provide publication dates; modified/fetch dates
  cannot. Explicit contradictory statistical periods are rejected.
- Known manufacturer/model mismatches cannot be hidden behind generic EV terms.
  A free preview exposed a GM-to-VW false match in the first version; it was not
  released or sent to AI. Regressions now reject it in selection and verification.
- Embedded recommendation/ad widgets are excluded. This removes unrelated model
  and source links found inside Motor's article scrollers.
- Read-only `run_publisher_news.py select` exposes bounded discovery traces and
  matched source hashes/dates. Holds distinguish missing authority, access
  reservation, wrong subject/date and unimplemented PDF extraction.

## Verification And Remaining Limits

The local suite passed 666 news tests, transactional SQL budget/publication
guards and the production build (90 routes, 76 vehicle routes). Synthetic
test successes are not live article approval.

Fresh previews made no paid calls and published nothing. GM's robots endpoint
remains unavailable and PFA declares an AI-mining reservation; both remain held.
Some queued stories still have no reachable matching original. PDF links can be
identified, but PDF/table extraction is not part of this HTML-first news slice.
Unsupported redirect/canonical changes remain held, never silently accepted.
