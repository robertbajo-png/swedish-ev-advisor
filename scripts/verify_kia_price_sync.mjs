import assert from 'node:assert/strict';
import { PGlite } from '@electric-sql/pglite';
import { buildKiaPricePlan, applyKiaPricePlan, KIA_PRICE_ALIASES, KIA_PRICE_URL, pricePlanHash } from './kia_price_sync.mjs';

const db = new PGlite();
const now = new Date('2026-10-27T12:00:00Z');
try {
  await db.exec(`CREATE TABLE canonical_models (id text primary key, brand text, model text);
    CREATE TABLE canonical_model_variants (id text primary key, canonical_model_id text, variant_name text,
      price_sek int, price_type text, price_valid_until text, price_source_url text, price_source_hash text,
      price_source_quote text, price_source_name text, price_verified_at text, price_refresh_batch_id text,
      updated_at timestamptz, wltp_range_km int, source_hash text, validation_status text);
    INSERT INTO canonical_models VALUES ('Ev5','Kia','Ev5'),('Ev6','Kia','Ev6'),('Ev9','Kia','Ev9');`);
  const intake = { source: { status: 'reachable', http_status: 200, final_url: KIA_PRICE_URL,
    content_hash: 'a'.repeat(64), fetched_at: now.toISOString() }, rows: [] };
  let index = 0;
  for (const [identity, label] of Object.entries(KIA_PRICE_ALIASES)) {
    const [model, name] = identity.split('|');
    await db.query(`INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,price_sek,price_type,
      updated_at,wltp_range_km,source_hash,validation_status) VALUES ($1,$2,$3,500000,'list_price',now(),500,'original-technical-proof','published')`,
      [String(++index), model, name]);
    const caption = 'Prislista för Kia ' + model.toUpperCase();
    const header = 'Rek. cirkapris inkl. moms';
    intake.rows.push({ row_label: label, source_url: KIA_PRICE_URL, source_hash: intake.source.content_hash,
      price_verified_at: intake.source.fetched_at, adapter: 'kia_sweden_exact_price_row_v1',
      price_type: 'list_price', price_valid_until: null, extraction_confidence: 0.99, price_header: header,
      caption, price_sek: 510000, source_quote: [caption, label, header, '510 000 kr'].join(' | ') });
  }
  const joined = (await db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id')).rows;
  const plan = buildKiaPricePlan(joined, intake, now);
  for (const mutate of [p => p.rows[0].price_sek = 520000, p => p.rows[0].row_label += ' Plus',
    p => p.rows[0].price_type = 'campaign_price', p => p.source.fetched_at = '2020-01-01',
    p => p.rows[0].source_hash = 'b'.repeat(64), p => p.rows.push(p.rows[0])]) {
    const invalid = structuredClone(intake); mutate(invalid);
    assert.throws(() => buildKiaPricePlan(joined, invalid, now));
  }
  const before = (await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
  const wrong = structuredClone(plan); wrong.targets[0].expected.source_hash = 'changed';
  await assert.rejects(applyKiaPricePlan(db, wrong, pricePlanHash(wrong), now));
  assert.deepEqual((await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows, before);
  const bypass = structuredClone(plan); bypass.targets[0].fact.price_sek = 1;
  await assert.rejects(applyKiaPricePlan(db, bypass, pricePlanHash(bypass), now));
  const result = await applyKiaPricePlan(db, plan, pricePlanHash(plan), now);
  assert.equal(result.prices_updated, 7);
  const after = (await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
  assert(after.every(row => row.price_sek === 510000 && row.wltp_range_km === 500 && row.source_hash === 'original-technical-proof'));
  await assert.rejects(applyKiaPricePlan(db, plan, pricePlanHash(plan), now));
  console.log(JSON.stringify({ kia_price_sync: 'passed', proof_and_scope_guards: true, rollback: true,
    technical_evidence_preserved: true, actual_database_writes: 0, paid_calls: 0 }));
} finally { await db.close(); }
