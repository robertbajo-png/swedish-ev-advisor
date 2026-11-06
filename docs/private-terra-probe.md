# Private Terra Probe

## Scope

This is a private, owner-authorized comparison of `gpt-6.1-terra` using the
existing publisher writer, literal evidence checks and independent review.
It cannot publish, activate a switch or change the production model. The
production `SUPPORTED_MODELS`, old Sol/Luna/A-B proofs and settlement functions
are unchanged. Do not use their historical permits for this probe.

Verified on 2026-11-06: the existing account's read-only model lookup returned
HTTP 200 for Terra. This is access verification, not a paid quality test.
Official rates per million tokens: input USD1, output USD5, cached input USD0.05,
30-minute cache writes USD1.25 and 12-hour writes USD2.50. Sources:
https://developers.openai.com/api/docs/models/gpt-6.1-terra and
https://developers.openai.com/api/docs/pricing.

## Preconditions

- Obtain separate owner approval before installing migration 023 or issuing a
  test permit. Migration 022 is unrelated and remains separately unapproved.
- Install only `023_private_terra_news_probe.sql`, after local SQL guards pass.
  It adds an owner-issued private permit and separate reservation/settlement
  functions. No vehicle/article records, caps, production switches or historical
  request charges are updated by the migration.
- The owner issues one exact manifest-bound permit for at most two hours and
  USD0.10 total. The service role cannot issue permits or modify the allowance.
- Require a fresh, accessible source bundle passing existing authority, identity,
  date, provenance, literal evidence and readiness rules. Do not relabel an old
  release or buy another attempt against a rejected historical URL.
- Preserve the current shared USD0.25/day, USD5/month and one-publication/day
  configuration. Both test calls count in the shared ledger and allowance.
  The entire private allowance must fit before the writer reservation.
- Unknown usage or a failed reservation stops the test. Retain the conservative
  charge and report the problem; never reset accounting or automatically retry.

## Procedure

`trial_news_terra.py prepare --source-file ... --directory ...` freezes the
source, writer hash, code hash and worst-case writer/reviewer bounds under
ignored `data/local/`. It makes no provider or publication call. The reviewer
packet is additionally bounded to 4,000 UTF-8 bytes for this small private
budget; a larger packet is a private-bound failure, not evidence of bad prose.

After owner-issued authorization, `run --directory ...` refreshes the source
again, requires unchanged evidence, reserves before each call, and stores raw
responses and results only in private JSON/SQLite plus the protected cost
ledger. The writer has 2,000 output tokens; the independent review has 1,300.
There is one attempt per stage, no rewrite and no continuation. A failed
deterministic precheck does not purchase a reviewer. The exact final packet
must pass the existing independent fact/block review; confidence is not enough.
The permit closes after the attempt. `passed_private` is not a publication
approval, a production-model change or a real test result from a fixture.

## Verification

`node scripts/verify_news_terra_budget.mjs` exercises an isolated PGlite database:
public denials, owner-only issuance, exact bounds, replay/expiry/closure,
ordinary caps, cache tariffs, unknown usage and production-state preservation.

`node scripts/run_python.mjs -m unittest discover -s tests -p test_news_terra_probe.py -v`
uses explicitly synthetic official-source/transport fixtures. No provider or
production writes occur. Payload construction does not need database credentials;
the suite rejects any implicit database-client initialization. The existing publisher and coverage suites remain
required. Private source bodies, manifests, databases and provider outputs
must never be included in the source package or public news export.

## Current Preparation

Offline SQL and eight probe regressions pass. The fresh approved official queue
had no eligible item; the bounded eight-item broader queue also produced no
ready, corroborated bundle. No Terra generation call or Supabase migration has
been made. Access and fixture results do not establish Terra's actual writing
quality. A genuine live result remains pending owner approval and valid source
material; do not manufacture one to complete a checklist.
