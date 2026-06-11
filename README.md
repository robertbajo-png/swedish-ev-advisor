# Swedish EV Advisor

Premium Swedish AI-powered EV comparison service.

The service uses Mobility Sweden as the Swedish market model index and official Swedish manufacturer/importer sources for prices and specifications.

## Pipeline

```bash
npm run mvp:scope
npm run mvp:sources
npm run mvp:validate-sources
npm run mvp:extraction-batch
npm run mvp:preflight-extraction
npm run mvp:browser-queue
npm run mvp:browser-fetch
npm run mvp:rendered-extraction-batch
npm run mvp:export-public
```

The npm scripts run through `scripts/run_python.mjs`, which finds a local Python runtime or the bundled Codex Python runtime on Windows.

Check the current pipeline state at any time:

```bash
npm run pipeline:status
npm run mvp:readiness
npm run pipeline:refresh
npm run pipeline:auto
```

`pipeline:refresh` validates extracted drafts, refreshes canonical/public JSON, seeds local SQLite, exports the SQLite public view for the frontend, and regenerates sitemap/robots.
`pipeline:auto` runs the local refresh, plans next work, preflights available official sources, runs AI extraction only when `OPENAI_API_KEY` exists, reports blockers, and builds the frontend.
`mvp:readiness` writes `docs/mvp-readiness-report.md` and `data/mvp/mvp_readiness_report.json` with the current MVP coverage, public-data contracts, source health, and deployment blockers.

Run the next ready official-source extraction batch:

```bash
npm run mvp:next-extraction
npm run mvp:preflight-next:dry-run
npm run mvp:preflight-next
npm run mvp:extract-next:dry-run
npm run mvp:extract-next
```

The non-dry-run extraction requires `OPENAI_API_KEY` in `.env.local`. After successful extraction it runs validation, public export, and local SQLite seed.

## Supabase

The pipeline is portable. Use local SQLite for MVP work, then move the same canonical model to Postgres/Supabase or another hosted Postgres later.

Local database:

```bash
npm run db:local:reset
npm run db:local:export-public
```

This creates `data/local/ev_advisor.sqlite` and exposes the same public views: `public_ev_models` and `public_ev_variants`.
The export command writes the public SQLite view back to `public/data/public_ev_variants.json` for the frontend and advisor API.

Generate the SQL bundle and apply it in Supabase SQL Editor:

```bash
npm run supabase:migration-bundle
npm run supabase:preflight
npm run supabase:seed:dry-run
npm run supabase:seed
npm run supabase:verify-public
```

`supabase:seed:dry-run` does not connect to Supabase. It reports the row counts and source statuses that would be imported.
`supabase:verify-public` compares the Supabase public view with the local public export and fails the contract if unvalidated or source-less records leak into public data.

See `docs/supabase-deployment-checklist.md` for the exact deployment sequence.

## Frontend

```bash
bun install
bun run dev
```

## Local Advisor API

```bash
copy .env.example .env.local
npm run advisor
```

The advisor API reads `.env.local` or `.env` at startup. These files are ignored by Git. Set `OPENAI_API_KEY` there to enable OpenAI responses for `/api/advisor` and `/api/compare`; without it, the API uses deterministic fallback responses from published canonical data.

Default model: `gpt-5.4-mini`. Use `gpt-5.4-nano` only when lowest possible cost/latency is more important than recommendation nuance.

## Environment

Copy `.env.example` and set:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`

Public UI reads only from Supabase public views when configured.
