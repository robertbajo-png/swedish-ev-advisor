# Database Backup And Isolated Restore

This procedure creates a local logical PostgreSQL backup. It must never restore
into the production Supabase project. A public catalog export is not a database
backup, and a completed dump alone is not a successful recovery rehearsal.

## Safety Boundary

- Read the existing ignored local connection without printing it. Verify the
  project, session-pooler host/user/port, CA fingerprint and `verify-full` mode.
- Set `default_transaction_read_only=on` at connection startup and use a
  repeatable-read, read-only transaction for the source snapshot. Verify TLS
  for both client and upstream PostgreSQL before reading backup data.
- Keep the snapshot-exporting transaction open until the dump and source
  fingerprints finish. Pass that snapshot to `pg_dump --snapshot` so table
  contents and comparison hashes refer to the same database state.
- Supply the password only through a private temporary passfile. Do not use a
  credentialled URI in process arguments, logs, Docker environment values or
  shell history. Delete the passfile and client containers after the attempt.
- Restrict the local backup directory to the current Windows user, SYSTEM and
  Administrators. Keep all dumps, data-bearing logs and manifests out of Git.
- Git ignore rules are not HTTP access controls. The local Vite configuration
  also denies the repository's private `data/` tree, Cloudflare `.dev.vars*`
  files and `.wrangler/` state, while retaining Vite's installed secret-file
  defaults. `public/data/` remains readable. `verify:dev-file-boundary` checks
  eight normal/raw/filesystem/encoded/case-varied routes with harmless unique
  fixtures, never actual backups or credentials, and removes its fixtures and
  test server afterward. This is local development protection, not encryption.

## Backup Contents

Use the matching PostgreSQL major version. Export global role definitions with
`pg_dumpall --roles-only --no-role-passwords` and the database with `pg_dump
--format=custom`. Preserve object owners, ACLs, functions, constraints, triggers,
indexes, RLS policies, private staging/review records and usage ledgers.

The local runner intentionally excludes replication publications/subscriptions
and role passwords. Record these exclusions in its manifest. Do not copy a
production password into the restored cluster.

The dump includes database metadata/data for managed schemas where the source
role can read them. It does not back up external Storage object bytes, Edge
Functions, Cloudflare D1, hosting secrets, API/JWT keys, email/DNS configuration
or external Vault encryption root keys. These need separate recovery procedures.
No off-site or encrypted-at-rest backup is implied by private local file ACLs.

## Restore Rehearsal

1. Create a fresh Postgres 17 instance with the required Supabase extensions.
   Use a unique test-only container name and ownership label, `--network none`,
   no published ports and memory-backed database storage. Use Unix peer
   authentication and an independent local bootstrap administrator.
2. Verify the archive/role-file SHA-256 hashes before restoring. Recheck target
   identity, label, network isolation and empty published ports before any write.
3. Restore the password-free roles, then a new test database. Invoke `pg_restore`
   only through that exact container's Unix socket, with `--single-transaction`
   and `--exit-on-error`. Cleaning is allowed only inside this new test database.
4. Restore the protected supplemental metadata SQL before validation. Logical
   dumps do not reproduce every managed extension object's modified owner/ACL.
   The supplement must be bound to reference metadata whose hashes match the
   original source snapshot, and may run only inside the guarded test target.
5. Compare all captured table row counts/content hashes, sequence state and
   catalog-definition hashes with the exported source snapshot. Check owners,
   function definitions, constraints, indexes, views, RLS policies, triggers and
   captured grants; do not reduce checks to make a failed restore pass. PostgreSQL
   logical restore compacts dropped-column slots: compare every live column's
   name, type, nullability, identity/generated flags, default and logical order,
   rather than requiring physical `attnum` gaps to survive. Keep the original
   snapshot unchanged and record this expected physical difference explicitly.
6. Test `anon` and `authenticated` denials for the seven private vehicle tables,
   public-view reads and full server-role row visibility in the restored copy.
7. Remove only the labeled test/client containers and temporary credentials.
   Retain the protected archive and redacted receipt. Never prune unrelated
   Docker resources or use a production database rollback for a frontend issue.
8. Recheck the production public/private access boundary using GET/HEAD only.

## Completion Evidence

Require a successful dump, successful isolated restore, matching data/schema
checks and a recorded cleanup result. A timed-out/incomplete attempt must remain
explicitly failed, not be presented as a valid backup. Preserve previous valid
backups rather than overwriting them.

The current local execution is recorded in `docs/release-2026-10-25.md` and
private receipts under ignored `data/local/backups/`. The private runner is a
local operational tool, not an installed GitHub backup schedule or permission to
upload database contents elsewhere. Only a passing final receipt closes this
release prerequisite.

## References

- [PostgreSQL pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)
- [PostgreSQL pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)
- [Supabase backup scope](https://supabase.com/docs/guides/platform/backups)
- [Supabase restore requirements](https://supabase.com/docs/guides/self-hosting/restore-from-platform)
