import assert from 'node:assert/strict';
import { MODEL, VARIANT } from './cupra_tavascan_drive_publication.mjs';
import { buildNewModelPlan } from './new_model_publication.mjs';

export async function readTavascanDriveScope(client,intake,image,now) {
  assert.equal((await client.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
  assert.equal((await client.query('SHOW transaction_isolation')).rows[0].transaction_isolation,'repeatable read');
  const query = async (sql,args) => JSON.parse(JSON.stringify((await client.query(sql,args)).rows));
  const identity = [MODEL.normalized_brand,MODEL.normalized_model];
  const canonical_models = await query(`SELECT m.* FROM public.canonical_models m
    WHERE m.normalized_brand=$1 AND m.normalized_model=$2`,identity);
  assert.equal(canonical_models.length,1,'Tavascan discovery draft missing or ambiguous');
  const [model] = canonical_models;
  assert.equal(model.validation_status,'draft');
  const model_aliases = await query(`SELECT a.* FROM public.model_aliases a
    WHERE a.normalized_brand=$1 AND a.normalized_model=$2`,identity);
  const market_models = await query(`SELECT m.* FROM public.market_models m
    WHERE m.normalized_brand=$1 AND m.normalized_model=$2 AND m.fuel_type_raw='EL'`,identity);
  assert.equal(market_models.length,1,'Tavascan market identity missing or ambiguous');
  const market_model_monthly_stats = await query(`SELECT s.* FROM public.market_model_monthly_stats s
    WHERE s.market_model_id=$1 ORDER BY s.id`,[market_models[0].id]);
  const expected = intake.market.row;
  const current = market_model_monthly_stats.filter(s=>s.month===expected.last_seen_month && s.county===null && s.municipality===null);
  assert(current.length<=1,'Ambiguous October total');
  if(current.length) assert.equal(current[0].registrations,expected.registrations_last_month);
  const canonical_model_variants = await query(`SELECT v.* FROM public.canonical_model_variants v
    WHERE v.canonical_model_id=$1`,[model.id]);
  const urls = intake.sources.map(s=>s.final_url);
  const manufacturer_sources = await query(`SELECT s.* FROM public.manufacturer_sources s
    WHERE s.url=ANY($1::text[]) ORDER BY s.id`,[urls]);
  for(const row of manufacturer_sources) {
    assert.equal(row.brand,MODEL.brand);
    assert.equal(row.model,MODEL.model);
    assert([null,model.id].includes(row.canonical_model_id),'Existing source belongs to another model');
  }
  const plan = buildNewModelPlan({canonical_models,model_aliases,market_models,market_model_monthly_stats,
    canonical_model_variants,manufacturer_sources},intake,image,now);
  assert.equal((await client.query('SELECT id FROM public.canonical_model_variants WHERE id=$1 OR source_id=ANY($2::uuid[])',
    [plan.targets[0].id,manufacturer_sources.map(s=>s.id)])).rows.length,0,'Existing variant uses the target or its sources');
  assert.equal((await client.query('SELECT id FROM public.extracted_variant_drafts WHERE source_url=ANY($1::text[]) AND variant_name=$2',
    [urls,VARIANT])).rows.length,0,'Existing staged variant needs separate review');
  return plan;
}
