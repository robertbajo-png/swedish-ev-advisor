# Vehicle Database Access Boundary

Implemented and applied to the owner's existing Supabase project on 2026-10-19.
Scope: release-readiness item 1 only. No DNS, vehicle content, AI quota,
credentials, news activation or frontend hosting configuration was changed.

## Initial Status And Missing Pieces

The seven internal vehicle tables and two public views were owned by postgres.
RLS was disabled and anon/authenticated had broad table grants, including write
privileges. Anonymous REST probes could read a non-published extraction row.
The website's row filtering did not prevent direct access through the Data API.

## Implemented Slice

Migration `database/migrations/008_vehicle_access_boundary.sql` runs atomically:

- Verify that the existing public views use a trusted owner, not invoker rights.
  Abort on an unexpected configuration instead of weakening it.
- Enable RLS on canonical models/variants, extraction drafts, manufacturer
  sources, market models, monthly statistics and aliases.
- Revoke all table and explicit column grants from PUBLIC, anon/authenticated.
- Preserve service-role SELECT/INSERT/UPDATE/DELETE and its existing RLS bypass.
- Keep the existing filtered public views, schema and row predicates unchanged.
  Add a security barrier and make them SELECT-only for public roles.
- Make future postgres-owned public tables/views private by default. A migration
  must explicitly grant public reads when that is intended.
- Assert the permission matrix before commit and reload the PostgREST schema.

Fresh installs use the same block in `database/schema.sql`; the ordered migration
bundle now includes 008. Only 008, not the entire bundle, was run on the live
project. Existing news migrations and data were not reapplied.

## Verified Live

| Check | Result |
| --- | --- |
| Internal tables | 7/7 anonymous reads denied, HTTP 401 with PostgreSQL 42501 |
| Actual SQL roles | anon + authenticated cannot read any internal table |
| Public views | Both roles can still read filtered models and variants |
| Public rows | 30 models / 66 variants, unchanged |
| Server role | Read access remains; migration asserts all four CRUD privileges |
| Internal row counts | All seven counts unchanged |
| Public content | Full before/after SHA-256 values match |

Public model hash:
`5b0eb4eb4c0b1869c04aceebd711c2822e4ce07f75337f02f1d51f3a84cae5b6`.

Public variant hash:
`b21e69e40a06377136b71375bd3f1c6f2503d0732669976b58cdbbd4467a3cab`.

Only permission DDL was applied remotely. Mutation denial and successful server
writes are exercised in a disposable local PostgreSQL database, never against
real vehicle records. The live SQL check is read-only and rolls back its role
settings. It is saved at `database/tests/vehicle_access.sql`.

## Automated Verification

```text
bun run verify:db-security
bun run verify:db-access
bun run verify:db-access:remote
```

The first command runs real PostgreSQL via the development-only PGlite engine:
84 denied operations across public roles, published-only views, explicit column
grant cleanup, server ingestion CRUD, data preservation, idempotence, default
privileges, accidental-grant RLS protection and unexpected-view rollback.

The second tests the remote checker with fixtures and no network requests.
The third uses only GET requests and the configured public key. Append
`--service` when running the script directly to check server reads too:

```text
node scripts/verify_supabase_access.mjs --remote --service
```

The checker validates credential roles, requires permission errors rather than
accepting empty arrays or bad JWTs, and never logs credentials/provider bodies.
Project credentials remain in ignored local environment files. CI runs only the
local engine/fixture checks, without database credentials or paid AI requests.

## Remaining Work

Release item 1 is resolved. Next: shared AI cost protection. The 66/69 database
difference, source freshness, new domain/brand, privacy/contact information and
production rollout remain separate tasks. No claim is made about historical
unauthorized access, credential rotation or a complete platform security audit.
Future migration authors must retain this boundary; an owner can still change
Postgres permissions deliberately.

References: [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api)
and [PostgreSQL view privileges](https://www.postgresql.org/docs/current/sql-createview.html).
