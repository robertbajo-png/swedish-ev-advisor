# SeekEV deployment checklist

## 1. Cloudflare Pages project

1. Add `seekev.se` to Cloudflare and replace the registrar nameservers with the two nameservers Cloudflare provides.
2. In Workers & Pages, create a Pages project from the GitHub repository `robertbajo-png/swedish-ev-advisor`.
3. Use `bun run seo:build` as the build command and `dist` as the output directory.
4. Use `/` as the root directory.

The checked-in `wrangler.toml` defines the Pages project name, output directory, compatibility date, and non-secret OpenAI model setting.

## 2. Build variables

Configure these for both production and preview builds:

```text
SITE_URL=https://seekev.se
VITE_SITE_URL=https://seekev.se
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_PUBLIC_ANON_KEY
```

## 3. Pages Functions runtime variables

Configure these for both production and preview runtime environments:

```text
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=YOUR_PUBLIC_ANON_KEY
OPENAI_MODEL=gpt-5.4-mini
```

Add `OPENAI_API_KEY` as an encrypted secret. Do not add `SUPABASE_SERVICE_ROLE_KEY` to Cloudflare; the public advisor only needs the read-only public view and anon key.

## 4. Custom domains

1. Add `seekev.se` as the primary custom domain for the Pages project.
2. Add `www.seekev.se` and redirect it permanently to `https://seekev.se`.
3. Keep Cloudflare proxying enabled and wait for the universal SSL certificate to become active.

## 5. Production checks

Verify these URLs after the first deployment:

```text
https://seekev.se/
https://seekev.se/bilar
https://seekev.se/jamfor
https://seekev.se/health
https://seekev.se/sitemap.xml
```

Then submit `https://seekev.se/sitemap.xml` in Google Search Console and verify that advisor and comparison requests return HTTP 200.

## 6. Preview and release gates

Use a non-production branch for the preview. Do not move the registrar DNS or
attach the production domain until the preview has been checked.

```text
npm run verify:deployment -- https://YOUR_PREVIEW.pages.dev --expect-preview
```

This performs GET checks only: app HTML, deep links, JSON health, published and
source-bound car export, and sitemap. It rejects parking pages, HTML in place of
API responses, and redirects from a public address to localhost. It makes no AI
requests. See Cloudflare's [preview deployment documentation](https://developers.cloudflare.com/pages/configuration/preview-deployments/).

For the separate, bounded advisor/compare smoke test, set
`ADVISOR_API_BASE_URL` to the preview origin and run `npm run smoke:advisor`.
It performs two POST requests and may incur two AI calls when the server has an
AI key. Set `SMOKE_REQUIRE_AI=1` to reject deterministic fallback as a release
result. A successful database fallback is not proof that the LLM is configured.

Local credentials belong in ignored `.dev.vars*` / `.env*` files, never Git.
Keep Cloudflare's `.wrangler/` runtime/cache directory ignored as well.
