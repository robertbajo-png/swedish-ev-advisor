# EV News Engine: implementation and operation

## Current verified state (2026-10-15)

- Phase 1 collection implemented and exercised against real publishers.
- Five XML endpoints verified: electrive `/feed/`, InsideEVs `/rss/news/all/`,
  CnEVPost `/feed/`, CarNewsChina `/feed/`, Electrek `/feed/`.
- 90 source items collected privately. Autocar `/rss` returned an empty/non-XML
  response and remains unverified. No alternate aggregator is used to bypass it.
- Phase 2 implemented; 23 offline tests exercise evidence, independent audit,
  originality, publication, quarantine, deduplication and daily limits.
- Actual LLM generation has NOT run: OPENAI_API_KEY is missing in local configuration.
- Supabase host `eutcryxbitudllcnpnex.supabase.co` fails DNS resolution here.
  Migration 007 has NOT been applied to the remote project or transaction-tested there.
- Phase 3 routes and integrations implemented, with desktop/mobile fixture tests.
  No fictional sample articles have been added to the public export.
- Phase 4 model-change verification queue and official-source worker implemented.
  Market statistical analysis and wider primary feed discovery remain future work.
- Scheduler is delivered as a GitHub Actions workflow and remains paused by
  default. Both scheduled and manual runs require the repository Actions variable
  `NEWS_AUTOMATION_ENABLED=true`, in addition to secrets and migrations.

## Production startup

1. Restore/confirm the existing Supabase project and reachable URL.
2. Apply `database/migrations/007_news_engine.sql` after migrations 001-006.
   The generated migration bundle includes all seven in order. Do not apply only
   the snapshot vehicle schema: news lives in its own migration.
3. Configure GitHub Actions secrets `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
   `OPENAI_API_KEY`. Optional model variable: `NEWS_OPENAI_MODEL`.
4. Run `npm run news:preflight -- --remote` in the worker environment.
5. Run `npm run news:run -- --backend supabase --max-items 6 --max-stories 2`.
6. Inspect `news_ingestion_runs`, `news_quality_checks` and source diagnostics.
7. Verify published rows through the anon-readable `public_news_articles` view.
8. Explicitly enable the repository Actions variable `NEWS_AUTOMATION_ENABLED`
   with value `true` when production startup is approved. The workflow checks
   every four hours at minute 17, UTC. Leave the variable unset or `false` to
   keep the engine paused. There is no editorial approval step or article quota.
9. Frontend needs the existing `VITE_SUPABASE_URL` and anon key for live news.
   For static article HTML/sitemap updates configure a hosting deploy hook in
   `NEWS_DEPLOY_HOOK`, plus `NEWS_BUILD_SYNC=1` and server-only Supabase credentials
   on the hosting build. The build pulls only the published view.

## Commands

```sh
npm run news:collect -- --backend sqlite --force
npm run news:run -- --backend supabase --max-items 8 --max-stories 3
npm run news:export -- --backend supabase
npm run news:status -- --backend supabase
npm run news:preflight -- --remote
npm run news:verification-queue -- --backend supabase
npm run news:verify-vehicles -- --backend supabase --limit 3
npm run verify:news
npm run verify:news-ui
```

SQLite is a development/test adapter in `data/local/news.sqlite`, ignored by Git.
Worker secrets are never browser environment variables. Every source runs in
isolation; invalid XML, forbidden access, TDM reservations, stale/missing dates,
missing evidence and ambiguous events create diagnostics rather than public news.

## Editorial gates

- 150-400 Swedish words, no invented quotes or arbitrary URLs in generated text.
- At least three source-supported facts; each evidence span is verbatim.
- Central facts require a primary source or audit-confirmed corroboration from
  distinct publishers. Corroboration must retain the same event and qualifiers.
- Headline, introduction and every paragraph cite known fact IDs privately.
- Deterministic numeric grounding and source-wording overlap checks.
- Separate structured AI audit must cover every fact and every text block.
- Three passing gate records bind to the exact article hash.
- Transactional publication, unique event and slug, global maximum five per UTC day.
- Published article content is immutable. A correction workflow remains future work;
  do not edit published payloads without a new checked correction process.

## Vehicle integration boundary

Only existing canonical model identities are linked. News creates a deduplicated
`news_verification_requests` row for launches, prices, batteries, updates or recalls.
The scheduled verification worker checks approved Swedish manufacturer/importer
URLs and records hash changes. Its output is
`data/news/official_verification_batch.json`, for the existing extraction/preflight
pipeline. It never treats publisher claims as canonical car specifications.
Automatic promotion of these follow-up batches remains subject to the existing
vehicle validation pipeline; no news code updates canonical car fields.

## Deployment limits still requiring live verification

- Postgres migration/RLS/RPC behavior against the restored project.
- Real model extraction and independent audit quality on a bounded live batch.
- Semantic deduplication quality across actual sources and event naming differences.
- Source rights/access status may change; current reachable RSS does not authorize
  unrestricted reuse. The collector checks robots, TDM metadata and access state.
- Publisher independence beyond separate source IDs needs ongoing registry review.
- Source expansion, statistical market analysis, correction handling and retention.

## Files changed for this feature

New files:

- `docs/news-engine-plan.md`
- `docs/news-engine-operations.md`
- `data/news/sources.json`
- `data/news/health_report.json`
- `database/migrations/007_news_engine.sql`
- `scripts/news_http.py`
- `scripts/news_store.py`
- `scripts/news_editorial.py`
- `scripts/news_engine.py`
- `scripts/news_public.py`
- `scripts/news_preflight.py`
- `scripts/news_report.py`
- `scripts/news_verification_worker.py`
- `scripts/export_news_build.py`
- `scripts/verify_news_ui.mjs`
- `tests/test_news.py`
- `src/news.jsx`
- `src/news.css`
- `public/data/news_articles.json`
- `.github/workflows/news.yml`

Updated integration files:

- `AGENTS.md`
- `ROADMAP.md`
- `.env.example`
- `.gitignore`
- `.github/workflows/ci.yml`
- `package.json`
- `src/main.jsx`
- `scripts/generate_sitemap.py`
- `scripts/prerender_static_routes.py`
- `scripts/verify_programmatic_seo.py`
- `database/supabase_migration_bundle.sql` (generated)
- `public/sitemap.xml` (generated)
- `data/mvp/programmatic_seo_report.json` (generated)

Existing unrelated worktree changes were preserved.
