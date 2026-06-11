# Supabase Deployment Checklist

Use this checklist when moving the portable local MVP database to hosted Supabase/Postgres.

## 1. Create Supabase Project

- Create a new Supabase project.
- Keep the database password in a password manager.
- Copy the project URL, anon key, and service role key.
- Never expose the service role key in frontend code.

## 2. Configure Local Environment

Create or update `.env.local`:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-public-anon-key
```

`SUPABASE_SERVICE_ROLE_KEY` is only for import scripts. `VITE_SUPABASE_ANON_KEY` is the browser-safe read key.

## 3. Apply Database Schema

Generate the migration bundle:

```bash
npm run supabase:migration-bundle
```

Open `database/supabase_migration_bundle.sql`, paste it into the Supabase SQL Editor, and run it.

## 4. Preflight Before Seeding

```bash
npm run mvp:readiness
npm run supabase:preflight
npm run supabase:seed:dry-run
```

Expected local status:

- 30 public MVP models.
- 66 public variants.
- Public contract OK.
- No public row without source hash.
- Only deployment blocker should be missing Supabase credentials before `.env.local` is complete.

## 5. Seed Supabase

```bash
npm run supabase:seed
npm run supabase:verify-public
```

The seed writes canonical tables, staging drafts, market presence rows, aliases, and official source rows. Public UI/API must read only `public_ev_models` and `public_ev_variants`.

## 6. Frontend Deployment

Set production frontend env vars:

```bash
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-public-anon-key
VITE_SITE_URL=https://your-domain.example
```

Then run:

```bash
npm run phase8:complete
```

Deploy `dist/` to the chosen host.

## 7. Post-Deploy Checks

- Open `/`, `/bilar`, `/jamfor`, `/verifiering`, and at least one `/bilar/[slug]`.
- Verify that missing values show `Uppgift saknas`, not `0`.
- Verify that source links open official Swedish manufacturer/importer pages.
- Verify sitemap and direct detail URLs return HTTP 200.
- Run `npm run mvp:readiness` again and archive the generated `docs/mvp-readiness-report.md`.

## Current Blocker

The local MVP pipeline is ready. Remote deployment is blocked until `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are added locally and the schema bundle is applied in Supabase.
