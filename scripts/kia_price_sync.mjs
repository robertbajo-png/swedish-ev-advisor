import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

export const KIA_PRICE_URL = 'https://www.kia.com/se/kopa/prislista/';
export const KIA_PRICE_ALIASES = {
  'Ev5|EV5 FWD': 'EV5 FWD Long Range',
  'Ev6|EV6 AWD': 'EV6 AWD Long Range',
  'Ev6|EV6 RWD': 'EV6 RWD Long Range',
  'Ev6|EV6 GT': 'EV6 GT (650hk) AWD Long Range',
  'Ev9|EV9 AWD': 'EV9 AWD 7-SITS Long Range',
  'Ev9|EV9 AWD GT Line 6-sits': 'EV9 GT Line AWD 6-SITS Long Range',
  'Ev9|EV9 AWD GT Line 7-sits': 'EV9 GT Line AWD 7-SITS Long Range',
};
const token = value => String(value).toLowerCase().replace(/[^a-z0-9]/g, '');
const json = value => JSON.parse(JSON.stringify(value));
export const pricePlanHash = plan => createHash('sha256').update(JSON.stringify(plan)).digest('hex');
const priceFields = new Set(['price_sek', 'price_type', 'price_valid_until', 'price_source_url', 'price_source_hash',
  'price_source_quote', 'price_source_name', 'price_verified_at', 'price_refresh_batch_id', 'updated_at']);
const retained = row => Object.fromEntries(Object.entries(row).filter(([name]) => !priceFields.has(name)));

function fresh(source, now) {
  const age = now.getTime() - Date.parse(source.fetched_at);
  assert(source.status === 'reachable' && source.http_status === 200 && source.final_url === KIA_PRICE_URL);
  assert.match(source.content_hash, /^[a-f0-9]{64}$/);
  assert(Number.isFinite(age) && age >= -60000 && age <= 900000, 'Fresh source required');
}

export function buildKiaPricePlan(variants, intake, now = new Date()) {
  fresh(intake.source, now);
  const rows = new Map();
  for (const row of intake.rows) {
    assert(!rows.has(token(row.row_label)), 'Duplicate full version');
    rows.set(token(row.row_label), row);
  }
  const targets = Object.entries(KIA_PRICE_ALIASES).map(([identity, exact]) => {
    const [model, variant] = identity.split('|');
    const matches = variants.filter(v => v.brand === 'Kia' && v.model === model && v.variant_name === variant);
    assert.equal(matches.length, 1, 'Exact canonical variant required');
    const previous = json(matches[0]);
    assert(['published', 'published_reviewed'].includes(previous.validation_status));
    const row = rows.get(token(exact));
    assert(row && row.row_label === exact, 'Exact full-version price row required');
    assert.equal(row.adapter, 'kia_sweden_exact_price_row_v1');
    assert.equal(row.source_url, KIA_PRICE_URL);
    assert.equal(row.source_hash, intake.source.content_hash);
    assert.equal(row.price_verified_at, intake.source.fetched_at);
    assert.equal(row.price_type, 'list_price');
    assert.equal(row.price_valid_until, null);
    assert(row.extraction_confidence >= 0.92 && row.extraction_confidence <= 1);
    assert.equal(token(row.price_header), 'rekcirkaprisinklmoms');
    assert(row.caption.startsWith('Prislista för Kia ' + model.toUpperCase()));
    assert(Number.isInteger(row.price_sek) && row.price_sek >= 100000 && row.price_sek <= 3000000);
    const quote = row.source_quote.split(' | ');
    assert.equal(quote.length, 4);
    assert.deepEqual(quote.slice(0, 3), [row.caption, exact, row.price_header]);
    assert.match(quote[3], /^[0-9 ]+(?: kr| SEK)?$/);
    assert.equal(Number(quote[3].replace(/\s|kr|SEK/g, '')), row.price_sek);
    assert(previous.price_sek > 0 && Math.abs(row.price_sek / previous.price_sek - 1) <= 0.15, 'Large change requires quarantine');
    return { id: previous.id, expected: previous, fact: row };
  });
  return { adapter: 'kia_sweden_price_only_sync_v1', source: intake.source, targets: targets.sort((a, b) => a.id.localeCompare(b.id)) };
}

export async function applyKiaPricePlan(client, plan, expectedHash, now = new Date()) {
  assert.equal(pricePlanHash(plan), expectedHash, 'Prepared price plan changed');
  assert.equal(plan.adapter, 'kia_sweden_price_only_sync_v1');
  fresh(plan.source, now);
  assert.equal(plan.targets.length, 7);
  assert.equal(new Set(plan.targets.map(row => row.id)).size, 7, 'Duplicate canonical targets');
  assert.deepEqual(plan, buildKiaPricePlan(plan.targets.map(row => row.expected),
    { source: plan.source, rows: plan.targets.map(row => row.fact) }, now), 'Price proof must be independently revalidated');
  let committed = false;
  await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE READ WRITE');
  try {
    await client.query("SET LOCAL search_path=pg_catalog");
    await client.query("SET LOCAL lock_timeout='10s'");
    await client.query('SELECT pg_advisory_xact_lock(7240007)');
    const before = json((await client.query('SELECT * FROM public.canonical_model_variants ORDER BY id FOR UPDATE')).rows);
    const models = json((await client.query('SELECT * FROM public.canonical_models ORDER BY id')).rows);
    const byId = new Map(before.map(row => [row.id, row]));
    const modelById = new Map(models.map(row => [row.id, row]));
    for (const target of plan.targets) {
      // Joined brand/model are scope evidence, not columns on the variant table.
      const { brand, model, ...expected } = target.expected;
      assert.deepEqual(byId.get(target.id), expected, 'Concurrent price/specification change');
      assert.equal(modelById.get(expected.canonical_model_id)?.brand, brand);
      assert.equal(modelById.get(expected.canonical_model_id)?.model, model);
      const fact = target.fact;
      await client.query(`UPDATE public.canonical_model_variants SET price_sek=$1, price_type='list_price', price_valid_until=null,
        price_source_url=$2, price_source_hash=$3, price_source_quote=$4, price_source_name='Kia Sverige',
        price_verified_at=$5, price_refresh_batch_id=$6, updated_at=now() WHERE id=$7`,
        [fact.price_sek, KIA_PRICE_URL, plan.source.content_hash, fact.source_quote, plan.source.fetched_at, expectedHash, target.id]);
    }
    const after = json((await client.query('SELECT * FROM public.canonical_model_variants ORDER BY id')).rows);
    const targets = new Map(plan.targets.map(row => [row.id, row]));
    assert.equal(after.length, before.length);
    for (const row of after) {
      const target = targets.get(row.id);
      if (target) {
        assert.deepEqual(retained(row), retained(byId.get(row.id)), 'Technical facts/status changed');
        assert.equal(row.price_sek, target.fact.price_sek);
        assert.equal(row.price_source_hash, plan.source.content_hash);
      } else assert.deepEqual(row, byId.get(row.id), 'Out-of-scope variant changed');
    }
    assert.deepEqual(json((await client.query('SELECT * FROM public.canonical_models ORDER BY id')).rows), models);
    await client.query('COMMIT');
    committed = true;
    return { committed: true, prices_updated: 7, technical_facts_changed: 0, plan_sha256: expectedHash, paid_calls: 0 };
  } finally { if (!committed) await client.query('ROLLBACK'); }
}
