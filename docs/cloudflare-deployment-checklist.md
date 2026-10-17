# SeekEV deployment checklist

## 1. Cloudflare Pages project

For the initial UI preview, use section 7 first. No custom domain or DNS change
is required. The following Git integration setup is for the eventual main site.

1. Sign in to the intended Cloudflare account. Leave registrar nameservers unchanged until the preview and release gates pass.
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

## 7. Repeatable GitHub UI preview

`Publish Pages preview` can be run from GitHub Actions on `main`. It requires a
green `Verify SeekEV` run for the exact commit. It does not create projects,
change DNS, upload source maps, sync databases or run the news engine.

One-time setup by the account owner:

1. Create or select a Pages project for UI previews, preferably `seekev-preview`.
   Keep its production branch as `main`, not `codex-ui-preview`. The actual
   upload always targets the non-production branch `codex-ui-preview`.
2. Under repository Settings > Environments, create `preview`. Store
   `CLOUDFLARE_API_TOKEN` as an environment secret there. Limit the token to
   Cloudflare Pages Edit for the intended account; do not grant DNS access.
   Never send this token through chat or put it in a file tracked by Git.
3. Under repository Settings > Secrets and variables > Actions > Variables, set
   `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_PAGES_PROJECT`.
4. Leave AI and Supabase credentials out of this project's preview runtime. The
   first preview uses the already validated canonical snapshot for both browser
   and API. Its recommendations are explicitly database-backed fallback, not a
   claimed live LLM integration. Existing production bindings are not changed.
5. After CI is green, run `Publish Pages preview`. Its summary contains the
   verified deployment link. A public URL is not considered verified until the
   GET-only app, API, canonical-data, sitemap and `noindex` checks pass.
6. Optionally set repository variable `PREVIEW_DEPLOY_ENABLED=true` to repeat
   this process automatically after successful main-branch push CI. It remains
   disabled by default. Pull requests and forks do not trigger an upload.

The helper checks deployment metadata from Cloudflare's API: exact commit,
branch, successful preview status, clean checkout and the project-specific
`pages.dev` URL. Provider response bodies and credentials are not printed.

Contract test: `bun run verify:pages-preview`. This uses fixtures and does not
contact Cloudflare, create credentials, publish assets or make AI calls.

References: [Cloudflare CI upload](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/)
and [deployment metadata](https://developers.cloudflare.com/api/resources/pages/subresources/projects/subresources/deployments/methods/list/).
