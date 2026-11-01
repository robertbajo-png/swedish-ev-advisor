# Production Backup And Monitoring

## Scope

Owner-approved on 2026-11-01: bounded live advisor/compare verification, recurring
encrypted off-site database backup and operational alerts. The later explicit
news-activation decision is documented in `news-release.md`; notice publication
remains off. These operations jobs contain no OpenAI key, never activate news and
never call the advisor or comparison POST endpoints.

## Backup

`production-backup.yml` runs daily at 03:17 UTC and supports manual dispatch.
Its source is the exact existing Supabase session-pooler connection. The owner
explicitly authorized storage of this existing administrator-role connection in
the encrypted GitHub environment secret `production-operations/BACKUP_DATABASE_URL`.
The environment allows only main. A separate credential-free job requires green
CI for the exact main revision before the backup environment is accessed.

The existing role retains write permissions: runtime read-only options are not
a substitute for a database-enforced read-only role. Restrict repository and
workflow administration accordingly; this limitation was disclosed to the owner.
No OpenAI/service-role key or private decryption identity is stored in this
environment. The public age recipient is an environment variable, not a secret.

PostgreSQL 17 clients use the pinned Supabase CA with verify-full, a temporary
0600 passfile and read-only transactions. Preflight verifies upstream TLS and
that news is either fully paused or uses the exact approved active Sol policy
(one article/day, USD0.25/day, USD5/month); the notice switch stays off. The backup
records the actual state but never changes it. Dumps include schema, data, permissions and
password-free role definitions; archive listing is checked before encryption.
Only the age-encrypted tar archive is uploaded. Plaintext stays in the runner's
private temporary directory and is removed on exit. Failed encryption uploads
nothing. The inner manifest binds dump/roles by SHA-256.

Encrypted Actions artifacts are retained for 14 days, not forever. Only a fresh
artifact from an actually successful main backup workflow counts as protection.
Target recovery-point interval is 24 hours; GitHub schedules are best effort and
not an uptime or delivery guarantee. No paid hosting/storage plan is ordered.

This is a logical PostgreSQL backup, not PITR or a full Supabase service copy.
External Storage object bytes, deployment/provider secrets, Cloudflare D1,
external encryption roots and replication subscriptions/publications are excluded.
The previously tested isolated full-restore procedure remains in
`database-backup-restore.md`. Archive validation is not described as a daily
full database restore.

## Recovery

The private age identity is kept in the protected, ignored local security
directory recorded in the local execution receipt. Protect a separate offline
copy before relying on it after loss of this computer. Never put it in GitHub,
a public issue, an ordinary email or the backup artifact.

Download the chosen encrypted artifact from GitHub Actions. Decrypt with the
local `age -d -i <identity> -o <private-bundle> <archive.age>`, then inspect the
manifest and verify both file hashes before using the established isolated
PostgreSQL 17 restore procedure. Never restore into production as a test.
Hosting secrets and D1 spending history require their separate recovery paths;
never reset a spending ledger or turn AI on from an old backup.

## Health And Alerts

`production-monitor.yml` runs at minutes 11 and 41 UTC. GET-only checks cover
public pages, contact/privacy, dependency-aware AI/budget readiness and both www
redirects with preserved query parameters. TLS validation stays enabled. It also
checks for an encrypted backup no older than 36 hours from the correct successful
workflow. It does not buy test AI calls, publish, repair production or change DNS.

An actual failure creates one clearly marked GitHub issue assigned to the owner.
Repeated failures do not create duplicate issues; recovery comments and closes
the issue. Only genuine github-actions bot issues may suppress another alert.
A separate explicitly marked delivery-test issue exercises the notification path
without pretending the site is down. GitHub notification email delivery depends
on the owner's notification preferences; verify those separately before claiming
an email alert was delivered. Issues and workflow failures remain visible in
GitHub even if email delivery is disabled.

## Activation Evidence

Prepared code and passing fixtures alone do not prove recurring operation.
Record exact main CI, first real backup workflow, encrypted artifact identity,
download/decryption/hash checks, real monitor run and the marked alert delivery
test in the release notes. Enable only `PRODUCTION_BACKUP_ENABLED` and
`PRODUCTION_MONITOR_ENABLED` after the reviewed code/configuration is installed.
Never enable NEWS_AUTOMATION_ENABLED or NEWS_SHORT_ARTICLES_ENABLED as part of
this setup. A manual dispatch proves that job, not a scheduled cron trigger.
