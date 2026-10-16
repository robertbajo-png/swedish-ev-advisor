# Automated Swedish EV News Engine

## Inspection and scope

The app is React/Vite (`src/main.jsx`), with Python ingestion scripts, Supabase
REST utilities, Postgres migrations and validated static exports. News is a
separate bounded context. Vehicle ingestion continues unchanged; news may only
enqueue verification requests and link existing canonical model identities.

## Phase 1: Collection

- Versioned registry: six priority publishers, expansion publishers and primary sources.
- Verify actual XML feed responses, robots rules, HTTP/meta TDM reservations and redirects.
- Bounded requests, conditional fetches, per-source polling intervals, isolated failures.
- Stable source/item IDs, canonical URLs, hashes, dates and persistent ingestion logs.
- Never circumvent paywalls, authentication, challenges or access reservations.
- Store private evidence separately from public articles. No syndicated images.

Exit: idempotent RSS/Atom ingestion and duplicate protection, with source failures recorded.

## Phase 2: Editorial and publication

- Extract atomic facts with verbatim evidence spans and named entities in strict JSON.
- Match events across publishers using entity/action/date fingerprints plus AI event matching.
- Score Sweden relevance 40%, significance 25%, source reliability 20%, recency 15%.
- Prefer primary links found in reporting; never describe foreign prices as Swedish prices.
- Generate 150-400 original Swedish words; every paragraph and headline references fact IDs.
- A separate AI audit checks every claim, Swedish quality, event identity and originality.
- Deterministic gates check evidence substrings, dates, numerical claims, source identity,
  attribution, word count, source-text overlap, event uniqueness and audit completeness.
- Publication is transactional, bound to the checked article hash and unique event key.
- Failure means quarantine with explicit reasons. AI confidence never authorizes publication.
- Default ceiling five articles per UTC day, no minimum, no quota filler.

Exit: automatic publication only for fully supported stories; retries and quarantine are inspectable.

## Phase 3: Public integration

- `/nyheter`: featured story, latest stories, brand and category filters, accessible empty states.
- `/nyheter/[slug]`: original text, dates, direct source links, related canonical vehicles.
- Three latest stories on home and `Senaste nytt om denna bil` on matching detail pages.
- Public view or validated static snapshot only; no browser access to raw source content.
- NewsArticle JSON-LD, article prerender and sitemap from published news only.

Exit: responsive routes and public metadata verified without invented example articles.

## Phase 4: Intelligence and operations

- Model launch/price/spec signals create deduplicated source verification requests.
- Scheduled runner consumes published car identities; separate worker exports official-source
  verification requests for the existing pipeline. No automatic canonical overwrites.
- Configurable four-hour schedule, bounded per-run AI work, run logs and daily ceiling.
- Expand source registry only after feed/policy verification. Market analysis needs multiple
  validated statistical primary sources and is deferred until enough evidence exists.

## Operations

Supabase/Postgres is canonical in production. SQLite is an isolated development/test
adapter, not a second production database. Apply migration 007 before running with
`--backend supabase`. Server secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
OPENAI_API_KEY, NEWS_OPENAI_MODEL (falls back to OPENAI_MODEL).
Workflow uses the existing runner and public export; static hosting must rebuild after
publication or read the live `public_news_articles` view. There is no manual article approval.
Failed source policies, failed extraction and conflicting evidence all remain unpublished.

## Verification

Offline fixture tests cover RSS/Atom, malformed feeds, URL safety, TDM/robots,
idempotency, event duplicates, source attribution, factual/numeric grounding,
originality, quarantine, daily limits, publication races, public filtering and model links.
Live collection verifies endpoints without bypasses. Frontend build and desktop/mobile
screenshots cover listing, article, filters, empty states and navigation.

## Rollout criteria

1. Apply migration and configure scheduled runner secrets.
2. Run collection and inspect source-policy diagnostics.
3. Run bounded editorial batch and inspect machine quality reports.
4. Verify public view and deployed article URLs, sources and refresh behavior.
5. Monitor quarantine and source failures; add sources rather than lowering evidence gates.

No claim of production activation until migration, scheduler and publication have actually run.
