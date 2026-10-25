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

- News release operations follow `docs/news-release.md`; the older design is in
  `docs/news-engine-plan.md`. It may use international reporting for
  independent Swedish articles, with evidence-based automatic quality gates.
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

- Keep data pipeline code deterministic where possible and AI-assisted only where it adds value.
- Prefer idempotent import/upsert scripts over one-off local mutations.
- Use migrations for database schema changes.
- Keep service-role Supabase operations in scripts/server contexts only. Frontend must use anon/public read access.
- Internal vehicle tables must have RLS enabled and no table/column privileges for PUBLIC, anon or authenticated. Only filtered public views are readable by public roles, and they must remain read-only.
- Preserve the server ingestion role when hardening permissions. Run `verify:db-security` and the read-only `verify:db-access:remote` before declaring a database access issue resolved; never prove denials by mutating production records.
- Add focused tests for ingestion, source validation, extraction validation, publishing rules, and public data filtering.
- Do not commit secrets. Use `.env.example` for documented configuration.
- Both paid website endpoints must reserve a shared, durable AI allowance before contacting a provider. Missing budget infrastructure must fail closed to deterministic canonical results, never uncapped paid calls. See `docs/ai-budget.md`; do not raise spending limits without owner approval.
