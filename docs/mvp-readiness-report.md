# MVP Readiness Report

Generated operational snapshot for the portable MVP pipeline.

## Summary

- MVP models: 30
- Public models: 30
- Public variants: 66
- Review queue variants: 1
- Local MVP status: `BLOCKED`
- Supabase deployment status: `BLOCKED`

## Readiness Checks

- `local_pipeline_ready`: `OK`
- `public_contract_ok`: `OK`
- `remote_public_contract_ok`: `BLOCKED`
- `validation_contract_ok`: `OK`
- `advisor_data_contract_ok`: `OK`
- `all_mvp_models_public`: `OK`
- `strict_images_ok`: `OK`
- `supabase_ready_for_seed`: `OK`

## Blocking Items

- `remote_public_contract_failed`
- `deployment:remote_public_contract_failed`

## Source Health

- `fetch_timeout`: 3
- `ready`: 6
- `source_hash_refresh_needed`: 1
- `source_text_too_short`: 1

## Next Actions

- Local next action: `run_supabase_seed_then_verify_public_views`
- Deployment next action: `run_supabase_seed_then_verify_public_views`

Recommended immediate task: Add Supabase credentials to `.env.local`, run the seed dry-run, then verify remote public views.
