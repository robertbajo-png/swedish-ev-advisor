# AGENTS.md

Permanent project rules for the Swedish EV Advisor codebase.

## Product Direction

- Build a public Swedish consumer service for comparing electric cars, not a private admin database.
- The main user-facing feature is an AI car advisor backed by verified canonical database records.
- The product should feel premium, Nordic, clean, bright, useful, and trustworthy.
- Prefer concrete recommendations, visible tradeoffs, sources, and comparison workflows over campaign-style marketing.
- Swedish copy is the default for all public UI.

## Data Authority

- Supabase/Postgres is the canonical database.
- Public UI and public APIs may read only canonical validated data through public views such as `public_ev_models` and `public_ev_variants`.
- Mobility Sweden is the Swedish market/model discovery source only.
- Mobility Sweden proves market presence and registration activity. It must not be treated as a price, specification, availability, or variant source.
- Official Swedish manufacturer/importer pages are the primary sources for prices, trims, technical specs, PDFs, configurators, and current availability.
- Do not scrape or use third-party comparison sites as price/spec sources.
- Public pages from verified authorized Swedish dealers may be used as secondary sources when the exact model/variant is identified and the dealer authorization evidence URL is stored.
- One authorized-dealer source may support a fact only when source URL, source hash, quote, confidence >= `0.92`, and every hard validation rule passes.
- Manufacturer/importer facts always supersede dealer facts for the same canonical variant.
- Dealer and campaign prices must remain distinguishable from ordinary list prices.

## Ingestion Model

- The database should be source-driven and automated.
- Build the first public MVP around the top 20-30 Swedish EV models by registration activity, then expand to the full Mobility Sweden-discovered model set after the pipeline is proven.
- Do not design normal manual data entry workflows for canonical car data.
- Human review is allowed for quarantined data, alias mapping, source approval, and final exception handling.
- Ambiguous Mobility Sweden names must be stored as `needs_mapping` or `model_group` until a deterministic alias rule exists.
- Raw market names must be matched to canonical models through `model_aliases`.

## AI Extraction Rules

- AI may extract structured data only from official Swedish manufacturer/importer sources.
- AI output must first be stored in staging tables such as `extracted_variant_drafts`.
- AI-extracted data is not public by default.
- Every extracted fact intended for publication must have source URL, source hash, confidence, and enough traceability for review.
- Use strict schemas for extracted fields: model, variant, price, WLTP range, battery, charging, boot volume, tow capacity, seats, drivetrain, source URL, source snippet, and confidence.

## Validation And Publishing

- Publish only canonical validated records.
- High-confidence autopublishing is allowed only when all conditions pass:
  - official source is reachable and accepted
  - extraction confidence is at or above the configured threshold, currently `0.92`
  - hard numeric validation rules pass
  - required source URL and source hash are present
  - the variant has at least price or WLTP range plus source evidence
- Uncertain, conflicting, blocked, low-confidence, or incomplete extraction results must go to quarantine/review, not public tables.
- Quarantine should preserve raw output, source metadata, validation errors, and suggested next actions.

## Public Surface Rules

- Public advisor context must include only canonical validated models and variants.
- Public pages may show Mobility Sweden-derived market flags, but never as specification evidence.
- Public pages should distinguish:
  - `market_seen`
  - `available_confirmed`
  - `discontinued_candidate`
  - `coming_or_low_volume`
- The UI must show clear source and verification signals for specs and prices.
- Never use a visually similar vehicle as an image fallback. Use an exact verified model image or the neutral missing-image state.

## Engineering Rules

- Public sitemap routes must ship visible content, headings and real links in
  the initial HTML, rendered from the same React views and validated public
  snapshots as the browser. Preserve hydration, deep-link filters and no-JS
  reading; never serve a crawler-only version or fabricate recommendations.
  Run `verify:static-content` and `verify:public-content-ui` after render changes.
  Responsive model-photo copies must remain hash-bound to the exact licensed
  original, with attribution/license links and an explicit format/size notice.
  Search Console discovery is not indexing; local lab timing is not field data.
  Owner exports and real search metrics stay under ignored `data/local/`.

- The 2026-11-04 content-month plan prioritizes broad international EV news before
  promotion, with minimal owner involvement. Substantive foreign vehicle launches
  and global vehicle technology may qualify on significance without a fabricated
  Swedish connection. Keep honest Swedish relevance scores, explicit foreign
  market/cycle/price qualifications and independent scope review. This does not
  relax factual, originality, access, spending or publication gates. Minor
  publicity and local offers are not quota filler. RSS/share briefs use only
  public articles; operational reports are read-only and exclude private prose.
  See `docs/news-content-month.md` for delivery status and remaining work.

- The 2026-11-06 selection refinement distinguishes substantive European vehicle
  developments from Swedish-market news. The European route needs significance
  >= 0.65 and weighted coverage >= 70, a concrete EV launch/update/recall or
  technology change, visible actual market and separate scope audit. Global
  international coverage retains significance >= 0.8 and coverage >= 75.
  Neither route establishes Swedish availability. Corporate brand names such as
  Nordic are not Swedish-market evidence. Fact, originality and spending gates
  remain unchanged; never retry old rejected/private URLs after a policy edit.
- Editorial triage distinguishes a speculative subject from incidental background
  wording, and a vehicle launch with a quoted price from a price/offer story.
  The article route still omits monetary facts; price notices keep their separate
  release switch. Concrete European charging-network developments may use the
  existing European scope, never imply Swedish availability or evade significance
  review. Cross-language event matching requires multiple explicit subject/action
  anchors, not a brand or generic charging term alone; conflicts in models,
  markets, periods and specific topics remain held. V2G/CO2/voltage are not models.
  Short field evidence must retain its exact contiguous model/variant header and
  qualifications, including in flattened HTML text. Orphan values and unvalidated
  tables remain held. No source text reconstruction, paid retry or proof promotion.
  Unknown/brandless report headlines may not borrow a manufacturer from competitor
  mentions in the body. A manufacturer-owned primary must share an explicit model
  identifier in both headlines, plus the manufacturer in the report. Apply this
  before discovery slots and in final artifact validation, not only before writing.
- smart Europe uses only declared `media.smart.com/en-CEU/` numeric article
  routes, one matching canonical/NewsArticle/main identity and original date.
  Preserve homologation and preliminary qualifications; exclude related links,
  hidden blocks and corporate boilerplate. Venue openings are not model launches.
  Model identifiers must distinguish smart #2/#5 and Volkswagen ID.7/ID.4.

- On 2026-11-04 the owner approved news ceilings of USD0.50/UTC day and
  USD10/UTC month, with the one-article and two-distinct-candidate limits unchanged.
  Migration 022 requires separate installation approval. Do not reset charges,
  renew pricing, activate switches or buy a test as part of this change.
  The current shared publisher uses `news_budget_policy.py`; deployment accepts
  the old and new exact pairs, never mixed or larger caps. Historical locked
  trial/short-worker budget code and mixed-content proof hashes stay unchanged.
  The old worker may conservatively defer under the new pair; do not rewrite
  its proof or spoof a config to expand its original spending authorization.
  Older monetary limits below describe the original rollout, not the new ceiling.

- News release operations follow `docs/news-release.md`; the older design is in
  `docs/news-engine-plan.md`. It may use international reporting for
  independent Swedish articles, with evidence-based automatic quality gates.
- Explicit official body regions require one matching region, exact canonical
  identity and matching article-specific publication metadata. Never use related
  article dates, dateModified or fetch time as publication. Only a declared
  source-specific trailing-slash link rule may normalize index links; host,
  query, TLS, reservation and evidence guards remain unchanged. Known other-car
  manufacturers must not consume original-source lookup slots for an unrelated
  branded story. Healthy but stale sources are quiet, not publication quotas.
- BYD Germany uses only its explicitly declared public news-list search (one
  fixed, uncredentialed, bounded POST; no redirects or pagination) and exact
  `/de/presse/` articles. The list is discovery only. Parse the one article
  header/date and declared narrative blocks; exclude corporate boilerplate and
  related material. Require canonical identity and matching list/article dates.
  German offers, hybrids, prices and rumours do not bypass editorial triage.
- Thin publisher metadata may allow free content triage only on a declared,
  exact-host vehicle route with a recognized brand. Preserve the eight-item
  reading queue and all freshness/history/price/hybrid/speculation exclusions.
  Reject non-EV bodies before original-source lookup; a route/brand is not EV
  evidence or permission for a paid call. Summaries expose only safe reason and
  known-brand counts, never private prose or credential-bearing URLs.
- NIO article state must be public, published, not deleted, exact canonical/
  query/locale identity and match the rendered main body and heading. Only
  original/display publication timestamps count. Official RSS and scoped
  narrative classes require actual article dates and unambiguous identity;
  unrelated time elements, modified dates and old feed rows are not new evidence.
  A recall needs recall evidence, not an unrelated launch of the same model.
- XPENG Swiss importer articles use only the exact declared pr.co host and
  six-digit article routes, with manufacturer appointment/legal-imprint evidence.
  Require exact canonical, one main/article, matching NewsArticle/visible title
  and original publication date. Collect explicit paragraph blocks, not company
  boilerplate, related stories, hidden text or image assets. The global XPENG
  homepage canonical is not an article identity and remains unapproved. Lexus
  Europe/UK use declared single narrative scopes and existing date guards.
  Regional sources never confirm Swedish availability or update canonical cars.
- News sources never overwrite canonical vehicle prices/specs. Enqueue official-source verification instead.
- News publication requires attribution, evidence, originality, duplicate checks and an independent audit; confidence alone is insufficient.
- Factual notices use short, deterministic source-bound templates, not free-form AI text.
  Use official pressrooms/ACEA, typed source-bound facts and three templates (model, price, registrations).
  Do not require 150 words or add buyer questions, comparisons or filler. A separate rule-based review
  must bind the exact rendered notice to source facts; it must not be described as an AI audit.
  Unsupported formats/conflicts go to quarantine. Legacy free-form articles retain their existing guards.
  Notices remain private until a separate release approval; do not enable paid AI or publication to test them.
  Notice publication must use its own transactional RPC with a fresh deterministic re-render,
  exact article/source/check snapshots and a private transaction-bound receipt. Both the global
  publication switch and notice-specific owner switch must be enabled; neither is worker-editable.
  Default notice release commands must be read-only dry-runs. Never treat notice checks as AI article audits.

- Hybrid launch articles are a separate, private/offline preparation track under
  the private-preparation rules in `docs/news-release.md`: 200-350 body words from sufficient source-bound
  model/Swedish-launch facts, with exact citations and a separate independent review.
  Keep the factual notices and their policy unchanged. Thin evidence stays a notice;
  uncertain markets/specs quarantine. Fixture review is never a real AI audit or
  publication approval. No implicit paid calls, legacy-policy promotion, production
  writes or publication without separate authorization and release support.

- The owner-selected news AI default is `gpt-6-sol` (migration 018). Use its
  verified standard/cache tariffs in the shared reservation/settlement contract.
  Do not rewrite historical mini/Luna/A-B trial pins or reuse consumed permits.
  A model change is not authorization for a paid trial, activation or publication.
  The car advisor's independently configured model and allowance are unchanged.

- The owner approved the unified short-article rollout on 2026-10-23:
  source-bound facts -> original Swedish article (150-250 body words) -> separate
  independent fact check. Analysis is optional, never padding. The new recipe
  uses the existing editorial policy/three publication gates, not notice checks
  or promotion of old failed hybrid drafts. Keep historical recipes unchanged.
  On 2026-10-24 the owner replaced the three-AI-case release requirement with
  `news-mixed-release-2026-10-v1`: real private model and battery AI articles
  with four exact settled writer/reviewer receipts, plus a price notice that
  passes independent deterministic source/re-render validation (no AI audit).
  Use a new format-policy gate identity; do not rewrite historical trials or
  promote the rejected AI price draft. Prices cannot use the AI article publisher;
  notices retain their separate transactional publisher and owner switch.
  Verifying the new format gate is not permission to spend, activate or publish.
  After separate owner release approval, publish at most ONE article per UTC day,
  including all formats.
  Existing USD0.25/day and USD5/month limits still apply. Budget exhaustion means
  defer, not another exception. No publication if a real test or gate fails.

- BMW charging support in `news_bmw_charging.py` is private preparation only:
  exact official source/variant, peak DC versus average power, range ADDED versus
  total range, battery basis, charging interval and US demonstration/commercial
  qualifications must remain source-bound. Unknown/conflicting layouts are held,
  not AI-guessed. Its deterministic preview review is NOT an AI audit or a new
  public notice recipe. Do not route it through either existing publisher, update
  canonical specifications or activate paid work/publication without a separate
  implementation and owner decision.
  The AC-option companion must preserve optional/future equipment, German market,
  preliminary technical data and AC input versus V2L output qualifications.
  Parsing an old captured body for shape regression never refreshes its source
  dates or permits an article. New charging formats are not MVP release blockers.

- News distribution is separate from article generation/publication. It may only
  read `public_news_articles` using an anon/publishable key, never a service key.
  Keep `NEWS_DISTRIBUTION_ENABLED` off until the reviewed code/configuration is
  installed. Require successful CI on the exact current main commit before any
  credentialled upload; target only `seekev-ai-preview` / `codex-ai-preview`.
  A distribution retry must never generate/buy/publish another article, change
  DNS/budgets or enable news-AI/publication. Keep previews noindex and bind the
  deployed snapshot to its exact workflow attempt, article HTML and sitemap.

- Owner-approved automatic production news has a separate fixed-target workflow,
  `news-production-distribution.yml`: public-view/anon reads only, exact current-main
  CI before credentials, existing `elbilsagenten` Pages project/main branch, unchanged
  catalog and advisor D1 binding. The older preview distributor remains preview-only.
  Editorial credentials belong only to the main-restricted `production-news` environment;
  never pass them to a build/deployment job. Publication still requires the existing
  mixed-format release proof, independent review, source checks and shared USD0.25/day,
  USD5/month and one-article/UTC-day limits. Missing/expired approvals fail closed.

- On 2026-11-02 the owner approved the simplified news-source policy. The new
  `news-article-review-2026-11-v2` recipe uses a shared declarative publisher
  template and article-level writer/reviewer checks, not a paid admission test
  for each publisher. Official evidence remains preferred. When unavailable,
  every reported fact needs literal support from two independently owned,
  attributable editorial sources, with visible attribution and a reported-not-
  verified presentation. Different domains alone do not prove independence:
  reject common ownership, circular citations, shared wire/upstream reporting,
  copied/syndicated text, conflicting facts or mismatched events. Shared official
  announcements are not independent measurements and must remain reported claims.
  Keep access/TDM rules, actual provider receipts, article quality gates,
  transaction limits and existing budgets. Never update canonical car data from
  editorial corroboration. Normal rejections are private outcomes, not owner
  approval requests. Do not retry historical failed URLs or rewrite old proofs.
  Explicitly enabled, date-required official pressrooms may start the same v2
  pipeline directly as `official_release`, with one actual primary source, not
  a fake publisher pair. Literal evidence, source attribution, separate review,
  exact refresh, table-context holds and all publication/budget gates still apply.
  At most two distinct production candidates may be attempted per UTC day within
  the same unchanged budget, including earlier short_daily attempts. A settled
  quality rejection may fall through to a different fresh candidate, never a
  rewrite/retry of the rejected URL. Unknown usage/provider/accounting failures
  stop paid work. The database still permits only one published article per day.
  The current v2 writer returns one complete 150-250-word article from its fact
  set within the unchanged 2000-token writer/1300-token reviewer caps. Earlier
  recorded two-alternative outputs remain readable without editing raw receipts,
  but new calls must not duplicate the article inside the same small output cap.
  Every fact/originality/length check and separate independent audit still applies.
  Incomplete responses stop paid work and remain charged; no continuation, rewrite
  or retry of old failed/private URLs. Old receipts/proofs are never promoted.

- Historical CarNewsChina/The Driven publisher shorts used the separate
  `news-publisher-short-2026-11-v1` recipe and per-publisher admission proofs.
  That admission process is retired, including its qualification worker/flag.
  Preserve all old receipts, quarantine and conservative charges; they are not v2
  approvals. Private tests never auto-publish. Resume only exact, still-fresh
  independently reviewed production attempts, never failed or private drafts.
  Literal evidence IDs, unchanged source hashes, full pair budget preflight and
  durable per-call reservation/settlement remain mandatory for v2. An old source
  announcement is never new just because another publisher discusses it today.

- Keep data pipeline code deterministic where possible and AI-assisted only where it adds value.
- Prefer idempotent import/upsert scripts over one-off local mutations.
- Use migrations for database schema changes.
- Keep service-role Supabase operations in scripts/server contexts only. Frontend must use anon/public read access.
- Internal vehicle tables must have RLS enabled and no table/column privileges for PUBLIC, anon or authenticated. Only filtered public views are readable by public roles, and they must remain read-only.
- Preserve the server ingestion role when hardening permissions. Run `verify:db-security` and the read-only `verify:db-access:remote` before declaring a database access issue resolved; never prove denials by mutating production records.
- Add focused tests for ingestion, source validation, extraction validation, publishing rules, and public data filtering.
- Do not commit secrets. Use `.env.example` for documented configuration.
- Both paid website endpoints must reserve a shared, durable AI allowance before contacting a provider. Missing budget infrastructure must fail closed to deterministic canonical results, never uncapped paid calls. See `docs/ai-budget.md`; do not raise spending limits without owner approval.
