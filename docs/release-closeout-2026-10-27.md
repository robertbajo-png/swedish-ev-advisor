# Release Close-Out: 2026-10-27

## Execution Plan

The owner requested completion of the remaining release work without routine
step-by-step handoffs. Preserve the full catalog, existing routes and budgets.
Do not make paid AI calls, enable news generation/publication, change passwords,
or waive evidence requirements to meet a deadline.

1. Inspect current changes against main; isolate the reviewed price-evidence,
   public snapshot and local-file safety changes from unrelated working files.
2. Recheck official catalog sources, image permission evidence and privacy
   prerequisites. Keep unsupported changes private; do not equate a successful
   fetch with fact verification or permission to reproduce an image.
3. Run focused regressions, build, SEO and desktop/mobile checks. Submit a scoped
   PR, require successful CI on its exact head, and review before merging.
4. After successful main CI, redistribute only the two already published news
   articles and the reviewed frontend to the existing noindex AI preview.
5. Independently verify the deployed catalog, article count, source/date display,
   health, security headers and noindex. Public production cutover remains
   conditional on all launch gates, not on successful preview distribution.

## Verified Baseline

- Supabase and the local public snapshot retain 30 models and 67 variants.
- Four Enyaq campaign prices have separate, fresh price evidence. Technical
  facts, their historical dates and the other 63 variants were checked unchanged.
- Eight of 52 non-null prices have current verification; 44 remain unresolved.
- A real logical backup and isolated restore have passed. It is a local recovery
  point, not an encrypted off-site backup or a full hosted Supabase replica.
- News AI, article publication and notice publication remain disabled. No paid
  AI call is part of this close-out.

## Fresh Source Findings

The read-only audit completed at 2026-10-27T10:36:01Z against canonical snapshot
`f97ae7d75178764994bb4bd33942eaae0452c5dd4cf5a142c27403659dc4651b`.
It checked 34 distinct official URLs covering the 67 public variants and three
existing quarantined variants: 19 reachable, 12 robots-denied/unavailable and
three HTTP errors. It verified zero facts and performed zero remote writes.
The ignored source captures and local review queue retain individual reasons.

Prioritize the unresolved prices by exact-variant evidence, not page reachability:

- Kia: distinguish exact drivetrain, battery and trim prices from model-level
  starting prices. A shared starting price does not verify AWD and RWD variants.
- Polestar 4: the specifications route now redirects to a coupe page with
  different variant labels. Do not silently map old Long range variants to it.
- Skoda Elroq: Explore Edition is not a deterministic alias for old Selection
  variants. The Enyaq-only publisher must not be reused for Elroq.
- Toyota: the reachable 2024 MY23 price PDF does not establish a current offer.
  Preserve its model-year identity; do not relabel it as the current generation.
- Renault and Zeekr: bind any fresh price to the complete exact variant, price
  classification and evidence before staging. Do not reuse old quotes as proof.
- Volvo returned HTTP errors. Other blocked sources remain queued; do not bypass
  robots restrictions or use comparison sites to fill the gaps.

## Image Rights

The offline inventory reports 30 asset uses: one documented and 29 pending.
These include two CSS background uses, not 30 distinct vehicle photographs.
The existing EQA Commons license/credit remains documented. No asset was removed,
replaced with a different model or declared licensed without evidence.

Kia's [Swedish website terms](https://www.kia.com/se/forbehall-villkor/) do not
provide blanket commercial reuse permission. Its separately licensed press
assets would need exact asset/permission binding before replacing current photos.
Manufacturer ownership or a working CDN URL is not permission evidence.

The owner's earlier choice to keep the complete catalog while waiting for
verification remains in effect. Do not switch to a reduced release or silently
replace all unresolved images with placeholders.

## Privacy And Production Boundary

Public operator/contact details and incoming contact-mail delivery are verified.
Technical safeguards include store=false, no app chat history, protected daily
visitor hashes, bounded AI spending and no public access to internal tables.
These do not themselves establish the operator's legal basis, email retention
policy or completed supplier/transfer review. Keep the privacy release flag off.

Reference documents for the remaining operator review:

- [Cloudflare DPA](https://www.cloudflare.com/cloudflare-customer-dpa/).
- [Supabase DPA](https://supabase.com/legal/customer-resources/data-processing-addendum).
- The existing privacy page and its actual provider/account evidence.

No production-domain cutover, new hosting service, paid plan, new credential,
off-site database upload or AI activation is authorized by a passing preview.
The existing release guard must continue to reject incomplete production builds.

## Delivery Scope

The code delivery contains migration 020 and fresh-schema parity, the bounded
Skoda publisher/worker, separate public price evidence, UI/advisor/export/SEO
integration, the actual four-row snapshot update and their regression tests.
It also denies private data and Cloudflare local files on the development HTTP
server while preserving access to public/data and Vite's default secret rules.

Migration 020 and the four prices are already applied in Supabase. CI/deployment
must not apply that migration again or run a publisher. Private backup/restore
helpers, source captures, credentials, trial databases and unrelated news history
are excluded from this delivery.

Record actual PR, CI and deployment results after they occur; this plan is not
proof of a remote upload or public launch.

Final code review additionally found a malformed/null RPC-response edge case.
It now remains an unknown publication outcome, never a reported zero-row result.
Regression covers null, array, string, numeric, incomplete and contradictory
responses. No real publication was attempted to test this behavior.
