import assert from 'node:assert/strict';
import { PGlite } from '@electric-sql/pglite';
import { ADAPTER, applySpecPlan, buildSpecPlan, specPlanHash, TECHNICAL_FIELDS } from './kia_spec_sync.mjs';

const db = new PGlite();
const now = new Date('2026-11-12T12:00:00Z');
try {
  await db.exec(`CREATE TABLE canonical_models(id text primary key,brand text,model text,market_seen boolean);
    CREATE TABLE canonical_model_variants(id text primary key,canonical_model_id text,variant_name text,
      validation_status text,review_approved_by text,review_promoted_at text,price_sek int,price_type text,
      price_source_url text,price_source_hash text,price_source_quote text,price_verified_at text,
      ${TECHNICAL_FIELDS.map(field => field + (field === 'drivetrain' ? ' text' : ' numeric')).join(',')},
      ac_charge_kw int,source_id text,source_url text,source_hash text,source_quote text,
      extraction_confidence numeric,updated_at timestamptz);
    CREATE TABLE manufacturer_sources(id text primary key default gen_random_uuid()::text,
      canonical_model_id text,brand text,model text,source_type text,url text unique,title text,country text,
      language text,fetched_at timestamptz,content_hash text,http_status int,final_url text,source_validation text,
      source_authority text,source_name text,extraction_status text,verified_at timestamptz,updated_at timestamptz);
    CREATE TABLE extracted_variant_drafts(canonical_model_id text,source_id text,brand text,model text,variant_name text,
      ${TECHNICAL_FIELDS.map(field => field + (field === 'drivetrain' ? ' text' : ' numeric')).join(',')},
      source_url text,source_hash text,source_quote text,extraction_confidence numeric,extraction_payload jsonb,
      validation_status text,validation_errors jsonb,updated_at timestamptz,unique(source_url,variant_name));
    INSERT INTO canonical_models VALUES ('m','Kia','Ev4',true),('other','Other','Untouched',false);`);
  const intake = { adapter: ADAPTER, drafts: [] };
  for (const [index, drive] of ['FWD', 'AWD'].entries()) {
    const name = 'EV4 GT Line ' + drive + ' Long Range';
    await db.query(`INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,validation_status,
      price_sek,price_type,price_source_url,price_source_hash,price_source_quote,price_verified_at,
      source_url,source_hash,source_quote,extraction_confidence,updated_at)
      VALUES ($1,'m',$2,'published',600000,'list_price','https://www.kia.com/se/kopa/prislista/',$3,
      'Exact retained cash price','2026-11-01','https://www.kia.com/se/kopa/prislista/',$3,'Original evidence',0.99,now())`,
      [String(index), name, 'b'.repeat(64)]);
    const source = { final_url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev4/kia-sweden-ev4-specification.pdf',
      status: 'reachable', http_status: 200, content_hash: 'a'.repeat(64), fetched_at: now.toISOString() };
    const facts = { wltp_range_km: index ? 550 : 584, dc_charge_kw: 128, boot_liters: index ? 359 : 435,
      tow_kg: index ? 1500 : 1000, battery_kwh: 81.4, drivetrain: drive };
    const field_evidence = Object.fromEntries(Object.entries(facts).map(([field, value]) => [field,
      { value, quote: 'Offline typed evidence ' + field + ' ' + value, page: 3,
        column_header: 'Teknisk specifikation\nFWD AWD', technical_scope: 'lr_' + drive.toLowerCase(),
        wheel_inches: 19, variant_name: name, source_url: source.final_url, source_hash: source.content_hash }]));
    intake.drafts.push({ brand: 'Kia', model: 'Ev4', variant_name: name, adapter: ADAPTER,
      facts, field_evidence, held_fields: { ac_charge_kw: { value: 10.5 } }, extraction_confidence: 0.99, source });
  }
  const joined = () => db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id').then(result => result.rows);
  const rows = await joined();
  const plan = buildSpecPlan(rows, intake, now);
  for (const mutate of [value => value.drafts[0].facts.price_sek = 1,
    value => value.drafts[0].facts.dc_charge_kw = 999,
    value => value.drafts[0].field_evidence.tow_kg.source_hash = 'c'.repeat(64),
    value => value.drafts[0].variant_name = 'EV4 GT (292hk) AWD Long Range',
    value => value.drafts[0].source.fetched_at = '2020-01-01',
    value => value.drafts.push(value.drafts[0])]) {
    const copy = structuredClone(intake); mutate(copy);
    assert.throws(() => buildSpecPlan(rows, copy, now));
  }
  const before = (await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
  const stale = structuredClone(plan); stale.targets[0].expected.source_quote = 'Concurrent update';
  await assert.rejects(applySpecPlan(db, stale, specPlanHash(stale), now));
  const conflict = structuredClone(rows); conflict[0].wltp_range_km = 999;
  assert.throws(() => buildSpecPlan(conflict, intake, now));
  const retainedWithoutEvidence = structuredClone(rows); retainedWithoutEvidence[0].seats = 5;
  assert.throws(() => buildSpecPlan(retainedWithoutEvidence, intake, now), /retained technical field needs evidence/,
    'A source replacement must not reattribute an old unsupported field');
  await db.exec(`CREATE FUNCTION fail_second() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
    IF NEW.variant_name LIKE '%AWD%' THEN RAISE EXCEPTION 'Fixture late failure'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_second();`);
  await assert.rejects(applySpecPlan(db, plan, specPlanHash(plan), now));
  assert.deepEqual((await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows, before);
  assert.equal((await db.query('SELECT * FROM manufacturer_sources')).rows.length, 0, 'Source insert rolled back');
  assert.equal((await db.query('SELECT * FROM extracted_variant_drafts')).rows.length, 0, 'Draft insert rolled back');
  await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
  const result = await applySpecPlan(db, plan, specPlanHash(plan), now);
  assert.equal(result.variants_updated, 2);
  assert.equal(result.new_technical_values, 12);
  const after = (await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
  assert(after.every(row => row.price_sek === 600000 && row.price_source_hash === 'b'.repeat(64)));
  assert(after.every(row => row.ac_charge_kw === null && row.seats === null), 'Unknowns stay unknown');
  assert.equal(Number(after[0].wltp_range_km), 584);
  assert.equal(Number(after[1].wltp_range_km), 550);
  assert((await db.query('SELECT * FROM extracted_variant_drafts')).rows.every(row => row.validation_status === 'published'));
  await assert.rejects(applySpecPlan(db, plan, specPlanHash(plan), now), 'Old before-image cannot be replayed');
  console.log(JSON.stringify({ kia_spec_sync: 'passed', exact_scope: true, price_and_unknown_preservation: true,
    stale_and_late_failure_rollback: true, real_database_writes: 0, paid_calls: 0 }));
} finally { await db.close(); }
