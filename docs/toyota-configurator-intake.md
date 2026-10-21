# Toyota Public Configurator Intake

## Inspection And Plan

The official Swedish specification page names the configurator resource/API and
the grade defaults. Its published JavaScript uses a read-only `data/se/sv` POST
with `fetchCarConfigCar` and `fetchCarConfigMotorization`. A direct deep link does
not render initialized data on the server, but the public data endpoint works
without authentication. No login, private API or access-rule bypass is needed.

This slice will:

1. Bind the exact public endpoint and request scope to a fresh Swedish official
   configuration, checking robots, reservations, response type/size and redirects.
2. Fetch Active Tech and Executive together, with exact model/grade/default IDs.
3. Extract price, battery, drive and certified scalar WLTP/consumption only;
   retain intervals and unsupported technical values as null.
4. Keep literal JSON-pointer evidence plus request/response hashes. Exclude
   financing, unrelated configuration and internal request logs from saved data.
5. Stage candidates privately as `needs_review` under a non-publishable source
   status. Never change canonical records, legacy identities or verification dates.
6. Test request scoping, identity tampering, evidence, unknowns, numeric limits,
   reservations, idempotent staging and concurrency; run build and CI.

## Publication Boundary

Migration 011 accepts one HTML source, not this POST/response evidence contract.
It will not be widened or bypassed by direct canonical writes. A separate tested
transactional publisher and a consumer-usable source link are required before
these API-backed drafts can be made public. Discovery is not publication.

No paid AI, database migration, DNS, UI or news changes are part of this intake.

## Result 2026-10-21

The live collector extracted four exact manufacturer identities and staged them
in Supabase as `needs_review`: Active Tech FWD/AWD and Executive FWD/AWD, all
with the 73.1 kWh battery. The two Executive WLTP values are intervals, so their
scalar range fields stay null. All four have cash prices; price classification,
DC/AC charging, towing, seats and boot volume stay null. No financing offer or
other grade's technical values were copied into a candidate.

Latest staging evidence: `2026-10-21T07:01:26.334258+00:00`, response hash
`20cd1128786b281432012648e43ab60f62ac727bd5cb8e8721ca238ab13d2a87`, request hash
`aa48653fd0ec2288fafd0bc2a2fdc3a3c11cebb19fe4ff42c96b2418f32f85dd`.
The source remains `needs_api_contract` with no verification date. Repeated live
runs retain exactly one private source and four drafts, not duplicate rows.

Only sanitized response fragments and the exact read-only request are saved in
private evidence. The response hash is of the received wire body, not the
sanitized JSON. JSON pointers replay against the preserved fragments; request
hashes distinguish this POST from other requests to the same endpoint. Full
internal request logs and financing data are not archived or committed.

The manufacturer script used to verify the request protocol was
`https://dxp-webcarconfig.toyota-europe.com/js/car-config-toyota-d90b32f.js`,
referenced by the official Swedish page. Runtime source authority is bound to
that page's exact configured resource/API, not a broad domain exception.

## Commands And Verification

- `catalog:toyota:configurator:dry-run`: fresh official page and public data
  request; local evidence/report only, no Supabase writes.
- `catalog:toyota:configurator:stage`: same checks followed by private staging.
  Creates use ignore-on-conflict, not overwriting upserts. Updates require the
  previous timestamp, adapter and quarantine state; reviewed data is protected.
- `verify:toyota-configurator`: thirteen offline tests; included in GitHub CI.

All 39 Toyota tests pass. The new cases cover wrong/mixed identity, stale or
unbound evidence, numeric limits, unsupported units, interval handling, JSON
duplicates/non-finite values, robots/reservations, request scope, sanitization,
concurrent review, duplicate-safe insertion and partial private-batch recovery.
The live repeat caught a source-vs-draft JSON column-name mismatch; it was fixed,
covered by table-specific assertions and verified by successful repeated PATCHes.

Canonical parity confirms all 29 fields unchanged across 67 public variants / 30
models. All seven private tables deny anonymous reads; service reads work.
Build and 77-URL SEO validation pass. No separate lint/typecheck is configured.
No preview upload is needed: no public data or UI changed. Paid AI calls: zero.

Changed files: `scripts/toyota_configurator_intake.py`,
`tests/test_toyota_configurator.py`, `package.json`, `.github/workflows/ci.yml`,
`data/review/toyota_configurator_intake.json`, this plan and deployment status.

## Next Recommended Slice

Build and test a separate transactional publisher for this exact request-bound
source group. Independently re-fetch/re-extract, check all manufacturer IDs and
literal pointers, reject stale/partial/conflicting groups, preserve absent
technical values and legacy records, and provide a consumer-usable manufacturer
source link distinct from the raw POST endpoint. Test role denials and rollback.
Any required database migration must be approved before execution. These four
drafts are not a public catalog expansion yet.
