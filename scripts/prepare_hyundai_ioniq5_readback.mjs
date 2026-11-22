import assert from 'node:assert/strict';
import { ADAPTER } from './hyundai_ioniq5_publication.mjs';
import { buildNewModelPlan, validateNewModelIntake } from './new_model_publication.mjs';

export async function prepareIoniq5Readback(client, intake, image, now = new Date()) {
  assert.equal(intake.adapter, ADAPTER);
  assert(validateNewModelIntake(intake, now).localOnly);
  const dateFields = ['first_seen_month', 'last_seen_month', 'month'];
  const rows = async (sql, args) => JSON.parse(JSON.stringify((await client.query(sql, args)).rows)).map(row => {
    for (const field of dateFields) if (row[field] != null) {
      assert.match(row[field], /^\d{4}-\d{2}-\d{2}(?:T00:00:00\.000Z)?$/);
      row[field] = row[field].slice(0, 10);
    }
    return row;
  });
  assert.equal((await rows('SHOW transaction_read_only'))[0].transaction_read_only, 'on', 'Read-only transaction required');
  assert.equal((await rows('SHOW transaction_isolation'))[0].transaction_isolation, 'repeatable read', 'Repeatable read required');
  const modelKey = ['hyundai', 'ioniq 5'];
  const canonical_models = await rows('SELECT * FROM public.canonical_models WHERE normalized_brand=$1 AND normalized_model=$2', modelKey);
  assert.equal(canonical_models.length, 1);
  const target = canonical_models[0];
  assert.equal(target.validation_status, 'draft');
  const model_aliases = await rows('SELECT * FROM public.model_aliases WHERE normalized_brand=$1 AND normalized_model=$2 ORDER BY id', modelKey);
  const market_models = await rows("SELECT * FROM public.market_models WHERE normalized_brand=$1 AND normalized_model=$2 AND fuel_type_raw='EL'", modelKey);
  assert.equal(market_models.length, 1);
  const market_model_monthly_stats = await rows('SELECT * FROM public.market_model_monthly_stats WHERE market_model_id=$1 ORDER BY id', [market_models[0].id]);
  const sourceUrls = intake.sources.map(row => row.final_url);
  const manufacturer_sources = await rows('SELECT * FROM public.manufacturer_sources WHERE url=ANY($1::text[]) ORDER BY id', [sourceUrls]);
  for (const source of manufacturer_sources) {
    assert.equal(source.brand, target.brand);
    assert.equal(source.model, target.model, 'Existing source belongs to another model or requires a separate shared-source check');
    assert([null, target.id].includes(source.canonical_model_id));
  }
  const canonical_model_variants = await rows('SELECT * FROM public.canonical_model_variants WHERE canonical_model_id=$1 ORDER BY id', [target.id]);
  assert.equal(canonical_model_variants.length, 0);
  const plan = buildNewModelPlan({ canonical_models, canonical_model_variants, model_aliases, market_models,
    market_model_monthly_stats, manufacturer_sources }, intake, image, now);
  assert.equal((await rows('SELECT id FROM public.canonical_model_variants WHERE id=ANY($1::uuid[]) OR source_id=ANY($2::uuid[])',
    [plan.targets.map(t => t.id), manufacturer_sources.map(s => s.id)])).length, 0);
  assert.equal((await rows('SELECT id FROM public.extracted_variant_drafts WHERE source_url=ANY($1::text[]) AND variant_name=ANY($2::text[])',
    [sourceUrls, intake.drafts.map(row => row.variant_name)])).length, 0);
  return plan;
}
