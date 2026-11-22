import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readPolestar3Identity } from '../scripts/prepare_polestar_3_readback.mjs';
import { readPolestar3Plan } from '../scripts/verify_polestar_3_local.mjs';

function fixture(overrides = {}) {
  const data = {
    transaction_read_only: [{transaction_read_only: 'on'}],
    transaction_isolation: [{transaction_isolation: 'repeatable read'}],
    canonical_models: [{id: 'model-3', brand: 'Polestar', model: '3', body_type: null, validation_status: 'draft'}],
    model_aliases: [{id: 'alias-3', canonical_model_id: 'model-3', brand_raw: 'POLESTAR', model_raw: '3',
      alias_rule: 'mobility_sweden_exact_raw_name', needs_mapping: false}],
    market_models: [{id: 'market-3', canonical_model_id: null, brand_raw: 'POLESTAR', model_raw: '3', fuel_type_raw: 'EL',
      needs_mapping: false, first_seen_month: '2026-03-01', last_seen_month: '2026-03-01'}],
    market_model_monthly_stats: [{month: '2026-03-01', registrations: 42}],
    canonical_model_variants: [],
    public_ev_variants: [{count: 0}],
    ...overrides,
  };
  const queries = [];
  return {
    data, queries,
    async query(sql, params) {
      assert.match(sql, /^(SHOW|SELECT) /);
      const table = sql.match(/^(?:SHOW (\w+))|FROM public\.(\w+)/);
      const name = table[1] ?? table[2];
      assert(Object.hasOwn(data, name));
      queries.push({name, params});
      return {rows: data[name]};
    },
  };
}

test('binds the existing exact alias to the draft without rewriting unlinked market history', async () => {
  const client = fixture();
  const receipt = await readPolestar3Identity(client);
  assert.equal(receipt.status, 'polestar_3_identity_verified');
  assert.equal(receipt.alias.canonical_model_id, receipt.model.id);
  assert.equal(receipt.market.canonical_model_id, null);
  assert.deepEqual(receipt.nationwide_months, [{month: '2026-03-01', registrations: 42}]);
  assert.deepEqual([receipt.production_writes, receipt.publication_approved, receipt.public_variants], [0, false, 0]);
  assert.equal(client.queries.length, 8);
  assert.deepEqual(client.queries.find(q => q.name === 'market_model_monthly_stats').params, ['market-3']);
  assert.deepEqual(client.queries.find(q => q.name === 'model_aliases').params, ['polestar', '3']);
});

test('does not query vehicle data outside read-only repeatable read', async () => {
  for (const [key, value, failAt] of [
    ['transaction_read_only', 'off', 1], ['transaction_isolation', 'read committed', 2],
  ]) {
    const client = fixture({[key]: [{[key]: value}]});
    await assert.rejects(readPolestar3Identity(client), /transaction required|Repeatable read required/);
    assert.equal(client.queries.length, failAt);
  }
});

test('installs the calendar DATE parser before reading the release plan', async () => {
  const client = fixture({transaction_read_only:[{transaction_read_only:'off'}]});
  let parseDate;
  client.setTypeParser = (type, parser) => {
    assert.equal(type, 1082);
    assert.equal(client.queries.length, 0);
    parseDate = parser;
  };
  await assert.rejects(readPolestar3Plan(client), /Read-only transaction required/);
  assert.equal(parseDate('2026-03-01'), '2026-03-01');
});

test('rejects ambiguous aliases, contradictory market links and duplicate nationwide months', async () => {
  for (const [name, adjust, error] of [
    ['model_aliases', rows => { rows[0].needs_mapping = true; }, /unambiguous alias/],
    ['model_aliases', rows => { rows[0].model_raw = '3/4'; }, /raw alias changed/],
    ['market_models', rows => { rows[0].canonical_model_id = 'model-4'; }, /BEV source mapping changed/],
    ['market_model_monthly_stats', rows => { rows.push({...rows[0]}); }, /non-overlapping/],
    ['market_model_monthly_stats', rows => { rows[0].registrations = 0; }, /First Swedish activity/],
  ]) {
    const client = fixture();
    adjust(client.data[name]);
    await assert.rejects(readPolestar3Identity(client), error);
  }
});

test('holds any existing canonical or public variant for separate review', async () => {
  await assert.rejects(readPolestar3Identity(fixture({canonical_model_variants: [{id: 'unknown-existing'}]})), /Existing Polestar 3 variants/);
  await assert.rejects(readPolestar3Identity(fixture({public_ev_variants: [{count: 1}]})), /already in the public catalog/);
});
