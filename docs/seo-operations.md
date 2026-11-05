# Search And Public Content

## Baseline: 2026-11-05

Search Console domain ownership is verified. Google successfully read the
90-URL sitemap. Discovered URLs are not indexed-page counts. The initial
homepage inspection was unknown/not indexed; an extra manual submission failed
at Google's reCAPTCHA service even after one normal reload. Do not repeatedly
submit or weaken site/browser protection to bypass this. The sitemap is valid.

The five-page public HTML check found empty application roots on home, vehicle
and need pages; news already had basic text. The new build renders the same
React components for all canonical sitemap routes from published Supabase-view
snapshots, then hydrates that markup. No crawler-specific content, hidden SEO
paragraphs, private tables, invented recommendations or paid build calls.

Build: `bun run seo:build`. Release builds also run the same content renderer.
Guards: `bun run verify:static-content`, `bun run verify:public-content-ui`
(against an isolated local preview), plus the existing SEO and UI contracts.
Keep metadata, displayed specifications, campaign qualifications and nullable
values consistent. All 38 retired-variant links retain their existing redirects.

Model-photo derivatives are exact size/format copies of the reviewed originals,
not replacement models. `src/image-variants.json` binds each derivative to its
licensed original hash and its own hash. Original files, credits and license
links stay intact. Reproduce with
`node scripts/run_python.mjs scripts/prepare_responsive_images.py --write`.
The generic 1200x630 sharing image is original brand typography, not an
unlicensed car photo; reproduce with `node scripts/generate_share_image.mjs`.

## Weekly Search Review

1. In Search Console, review Pages for actual indexing/exclusion reasons, not
   just sitemap discovery. Verify a reported defect before changing code.
2. In Performance, compare complete seven-day periods with matching search,
   country and device filters. Record clicks, impressions, CTR, position and
   relevant pages. No forecast or visitor count may replace missing data.
3. When an actual Pages CSV is available, keep it under ignored `data/local/seo/`
   and run the offline analyzer below. Never commit account exports or search
   query data. No extra Google API key or OAuth delegation is required.
4. Review pages with meaningful impressions and low CTR for an accurate title
   and description. Do not keyword-stuff, invent prices or change facts merely
   to improve a score. Inspect landing-page usefulness before adding new URLs.
5. Check real Core Web Vitals in Search Console/Cloudflare when enough samples
   exist. `data/local/seo-qa/mobile-lab.json` is an isolated local observation,
   not field data, a PageSpeed score or a promise of Google rankings.

```powershell
node scripts/run_python.mjs scripts/search_console_report.py --input data/local/seo/pages.csv --start 2026-11-05 --end 2026-11-11 --output data/local/seo/week-1.json
```

Dashboard: https://search.google.com/search-console?resource_id=sc-domain%3Aelbilsagenten.se

Google setup does not install Analytics/Tag Manager or authorize paid ads,
automatic public posts, new credentials, broader permissions or budget changes.
There is no search-performance baseline yet; wait for actual reports.
