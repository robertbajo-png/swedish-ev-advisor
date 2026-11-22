import assert from 'node:assert/strict';

const dcRelations = [
  'canonical_model_variants',
  'extracted_variant_drafts',
  'public_ev_variants',
];

export function assertDcChargePower(value) {
  assert(typeof value === 'number' && value >= 20 && value <= 600
    && /^\d+(?:\.\d{1,2})?$/.test(String(value)),
  'Require DC power from 20 to 600 kW with at most two decimal places');
}

export async function assertDcStorageForDrafts(client, drafts) {
  if (drafts.some(draft => !Number.isInteger(draft.facts.dc_charge_kw))) {
    await assertExactDcInstalled(client);
  }
}

// A numeric typmod can round before a check constraint sees the original value.
export async function assertExactDcInstalled(client) {
  const { rows } = await client.query(`
    SELECT c.relname AS name, c.relkind AS kind,
      pg_catalog.format_type(a.atttypid, a.atttypmod) AS storage,
      con.convalidated AS checked,
      pg_catalog.pg_get_expr(con.conbin, con.conrelid, true) AS predicate
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
      AND a.attname='dc_charge_kw' AND NOT a.attisdropped
    LEFT JOIN pg_catalog.pg_constraint con ON con.conrelid=c.oid
      AND con.conname='exact_dc_charge_kw' AND con.contype='c'
    WHERE n.nspname='public' AND c.relname=ANY($1::text[])
    ORDER BY c.relname`, [dcRelations]);
  assert.deepEqual(rows.map(row => row.name), dcRelations, 'Require all three exact DC projections');
  for (const row of rows) {
    assert.equal(row.storage, 'numeric', 'Migration 027 is required for exact DC: ' + row.name);
    if (row.name === 'public_ev_variants') {
      assert.equal(row.kind, 'v');
      continue;
    }
    assert.equal(row.kind, 'r');
    assert.equal(row.checked, true, 'Require validated exact DC constraint: ' + row.name);
    const predicate = row.predicate?.replace(/\s+/g, ' ').replace(/'(20|600)'::numeric/g, '$1::numeric');
    assert.equal(predicate,
      'dc_charge_kw IS NULL OR dc_charge_kw >= 20::numeric AND dc_charge_kw <= 600::numeric AND dc_charge_kw = trunc(dc_charge_kw, 2)',
      'Unexpected exact DC constraint: ' + row.name);
  }
}
