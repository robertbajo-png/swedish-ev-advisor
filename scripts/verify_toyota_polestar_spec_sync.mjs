import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';
import { ADAPTER, validateSpecDraft, buildSpecPlan, applySpecPlan, specPlanHash, intakeFingerprint } from './toyota_polestar_spec_sync.mjs';
import { TECHNICAL_FIELDS, buildSpecPlan as kiaPlan } from './kia_spec_sync.mjs';
import { specQualifications } from '../src/spec-qualifications.js';
import { normalizePublicVariants, deterministicAdvice } from '../functions/_shared/advisor-core.mjs';

const intake = JSON.parse(await readFile('tests/fixtures/toyota_polestar_specs.json', 'utf8'));
const now = new Date('2026-11-13T15:01:00Z');
const db = new PGlite();
try {
  const columns = [...TECHNICAL_FIELDS, 'ac_charge_kw'].map(f => f + (f === 'drivetrain' ? ' text' : ' numeric')).join(',');
  await db.exec(`CREATE TABLE canonical_models(id text primary key,brand text,model text,body_type text,updated_at timestamptz);
    CREATE TABLE canonical_model_variants(id text primary key,canonical_model_id text,variant_name text,validation_status text,
      review_approved_by text,review_promoted_at text,price_sek int,price_type text,price_valid_until date,
      price_source_url text,price_source_hash text,price_source_quote text,price_verified_at timestamptz,price_source_name text,price_refresh_batch_id text,
      ${columns},source_id text,source_url text,source_hash text,source_quote text,extraction_confidence numeric,updated_at timestamptz);
    CREATE TABLE manufacturer_sources(id text primary key default gen_random_uuid()::text,canonical_model_id text,brand text,model text,
      source_type text,url text unique,title text,country text,language text,fetched_at timestamptz,content_hash text,http_status int,
      final_url text,source_validation text,source_authority text,source_name text,extraction_status text,verified_at timestamptz,updated_at timestamptz);
    CREATE TABLE extracted_variant_drafts(canonical_model_id text,source_id text,brand text,model text,variant_name text,${columns},
      source_url text,source_hash text,source_quote text,extraction_confidence numeric,extraction_payload jsonb,validation_status text,
      validation_errors jsonb,updated_at timestamptz,unique(source_url,variant_name));
    INSERT INTO canonical_models VALUES ('outside','Other','Untouched',null,now());
    INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek) VALUES ('outside','outside','Untouched',123456);`);
  // Exercise the real price-invalidation trigger, not a permissive mock schema.
  const migration = await readFile('database/migrations/020_price_only_refresh.sql','utf8');
  await db.exec(migration.match(/create or replace function public\.invalidate_replaced_price_evidence\(\)[\s\S]*?\$price_invalidation\$;/)[0]);
  await db.exec(`create trigger invalidate_replaced_price_evidence before update of price_sek,price_type,price_valid_until
    on canonical_model_variants for each row execute function public.invalidate_replaced_price_evidence();
    alter table canonical_model_variants add constraint price_proof_complete check (
      num_nonnulls(price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id) in (0,6));`);
  const modelIds = new Set();
  for (const [i,row] of intake.drafts.entries()) {
    validateSpecDraft(row, now);
    const modelId = row.brand + row.model;
    if (!modelIds.has(modelId)) {
      modelIds.add(modelId);
      await db.query('INSERT INTO canonical_models VALUES ($1,$2,$3,null,now())', [modelId,row.brand,row.model]);
    }
    await db.query(`INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,validation_status,price_sek,source_url,source_hash,updated_at)
      VALUES ($1,$2,$3,'published',$4,$5,$6,now())`, [String(i),modelId,row.variant_name,row.price_evidence.value,row.source.final_url,'c'.repeat(64)]);
  }
  const joined = async () => (await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
  const rows = await joined(), plan = buildSpecPlan(rows,intake,now);
  for (const mutate of [d => d.drafts[0].facts.dc_charge_kw = 5.5, d => d.drafts[0].facts.seats = 7,
    d => d.drafts[0].price_evidence.value = 1, d => d.drafts[0].price_evidence.price_type = 'campaign_price',
    d => d.drafts[0].field_evidence.tow_kg.manufacturer_variant_id = 'wrong',
    d => d.drafts[0].source.fetched_at = '2020-01-01', d => d.drafts[1].variant_name = 'Standard range Single motor',
    d => d.drafts[1].field_evidence.tow_kg.column_header = 'Rear motor',
    d => d.drafts[4].source.final_url = d.drafts[4].source.final_url.replace('coupe','suv'),
    d => d.drafts[4].field_evidence.wltp_range_km.source_hash = 'd'.repeat(64),
    d => d.drafts[4].facts.ac_charge_kw = 22, d => d.drafts[4].facts.boot_liters = 1536,
    d => d.drafts[5].field_evidence.wltp_range_km.scope = 'certified_rear_motor_20_inch',
    d => d.drafts[5].field_evidence.wltp_consumption_kwh_100km.interval[1] = 19,
    d => d.drafts.push(d.drafts[0])]) {
    const invalid = structuredClone(intake); mutate(invalid);
    assert.throws(() => buildSpecPlan(rows, invalid, now));
  }
  assert.throws(() => kiaPlan(rows,intake,now));
  const changedPrice = structuredClone(rows); changedPrice.find(r => r.id === '0').price_sek++;
  assert.throws(() => buildSpecPlan(changedPrice,intake,now));
  const conflict = structuredClone(rows); conflict.find(r => r.id === '0').tow_kg = 1500;
  assert.throws(() => buildSpecPlan(conflict,intake,now));
  const before = (await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
  const models = (await db.query('SELECT * FROM canonical_models ORDER BY id')).rows;
  await db.exec(`CREATE FUNCTION fail_late() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
    IF NEW.variant_name = 'Dual motor' THEN RAISE EXCEPTION 'Fixture late failure'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_late();`);
  await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now));
  assert.deepEqual((await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows,before);
  assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows,models);
  assert.equal((await db.query('SELECT * FROM manufacturer_sources')).rows.length,0);
  await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
  const result = await applySpecPlan(db,plan,specPlanHash(plan),now);
  assert.equal(result.variants_updated,6); assert.equal(result.models_changed,3);
  const saved = await joined();
  assert(saved.filter(r => r.id !== 'outside').every(r => r.price_type === 'list_price' && r.price_source_hash === intake.drafts.find(d => d.variant_name === r.variant_name).source.content_hash));
  assert.equal(saved.find(r => r.id === 'outside').price_sek,123456);
  const staged = (await db.query('SELECT * FROM extracted_variant_drafts')).rows;
  assert(staged.every(r => r.validation_status === 'published' && r.extraction_payload.price_evidence));
  await assert.rejects(applySpecPlan(db,plan,specPlanHash(plan),now), 'Replay denied');
  const target = intake.drafts[5];
  const row = { ...target, ...target.facts, price_sek: target.price_evidence.value,
    source_quote: Object.values(target.field_evidence).map(p => p.quote).join(' | '), source_url: target.source.final_url,
    source_hash: target.source.content_hash, validation_status: 'published' };
  assert(specQualifications(row).rangeIsTarget);
  assert.equal(specQualifications(row).consumptionInterval,'19,0–21,7 kWh/100 km');
  const normalized = normalizePublicVariants([row]);
  assert.equal(normalized.length,1); assert(normalized[0].wltp_range_is_target);
  assert.equal(deterministicAdvice(normalized,{ prompt: 'Minst 550 km', range: 550 }).shortlist.length,0,
    'A target cannot prove a certified minimum-range requirement');
  const fresh = structuredClone(intake); fresh.drafts[0].source.content_hash = 'b'.repeat(64);
  assert.deepEqual(intakeFingerprint(fresh), intakeFingerprint(intake));
  fresh.drafts[0].facts.boot_liters++;
  assert.notDeepEqual(intakeFingerprint(fresh),intakeFingerprint(intake));
  console.log(JSON.stringify({ toyota_polestar_sync: 'passed', six_exact_versions: true, price_evidence: true,
    source_and_optional_equipment_guards: true, rollback_replay_and_scope: true, target_not_certified: true, production_writes: 0, paid_calls: 0 }));
} finally { await db.close(); }
