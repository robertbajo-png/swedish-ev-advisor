# GitHub preview delivery

## Current status

- Application and UI QA are implemented; CI passed for `13b9287`.
- Local Wrangler is not authenticated. Browser automation has no connected browser.
- No external Pages deployment has been verified. Production DNS is unchanged.

## Smallest useful next slice

1. Add a preview-only workflow, manually runnable from `main` and optionally
   triggered after successful main-branch CI.
2. Require successful CI for the exact commit, a configured Cloudflare project,
   and a branch distinct from that project's production branch before upload.
   A separate credential-free job checks CI before the credentialled job starts.
3. Build the existing validated canonical snapshot without database or AI keys.
   Check the preview runtime has no external-service credentials that would
   change that behaviour. Do not touch ingestion, news, DNS or database records.
4. Upload with pinned Wrangler, resolve the exact deployment through Cloudflare's
   structured API, and reuse the GET-only deployment checks including `noindex`.
5. Test guards with fixtures and run the production build. Only enable automatic
   deployment after the owner configures the scoped Cloudflare credential.

## One-time external prerequisite

The account owner must authorize Cloudflare access. A browser login alone does
not authorize local Wrangler or GitHub Actions. Store a Pages Edit token limited
to the intended account in GitHub's `preview` environment, never chat or Git.
The workflow will not create accounts, projects, tokens or DNS records.

## Scope

This is an initial UI/integration preview, not evidence of live LLM readiness.
The existing database-backed fallback remains explicitly labelled in the UI.
Server secrets, live Supabase alignment and bounded AI smoke tests remain
separate release gates.
