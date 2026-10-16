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
