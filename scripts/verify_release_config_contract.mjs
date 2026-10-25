import assert from 'node:assert/strict';
import { auditReleaseConfig } from './verify_release_config.mjs';
import { operatorInfo, SITE_ORIGIN } from '../src/site-info.js';

const now = new Date('2026-10-25T12:00:00Z');
const env = { SITE_URL: SITE_ORIGIN, VITE_SITE_URL: SITE_ORIGIN, VITE_OPERATOR_NAME: 'Test operator',
  VITE_CONTACT_EMAIL: 'contact@fixture.invalid', PUBLIC_PRIVACY_REVIEWED: 'true', PUBLIC_IMAGE_RIGHTS_REVIEWED: 'true' };
const row = { brand: 'Fixture', model: 'Model', variant_name: 'Exact', price_sek: 500000,
  verified_at: '2026-10-24T10:00:00Z', source_hash: 'a'.repeat(64), source_url: 'https://manufacturer.invalid/se/model', validation_status: 'published' };
const catalog = { source: 'supabase_public_ev_variants', records: [row] };
let checks = 0;
const ok = value => { assert(value); checks++; };
ok(auditReleaseConfig(env, catalog, now).configuration_ready);
ok(!auditReleaseConfig({}, catalog, now).configuration_ready);
for (const patch of [{ VITE_OPERATOR_NAME: '' }, { VITE_CONTACT_EMAIL: 'name@example.com' }, { VITE_CONTACT_EMAIL: 'x\r\nBcc:a@b.se' },
  { PUBLIC_PRIVACY_REVIEWED: 'false' }, { PUBLIC_IMAGE_RIGHTS_REVIEWED: 'false' }, { SITE_URL: 'https://wrong.invalid' }, { VITE_OPENAI_API_KEY: 'synthetic-not-real' }]) {
  ok(!auditReleaseConfig({ ...env, ...patch }, catalog, now).configuration_ready);
}
for (const patch of [{ verified_at: null }, { verified_at: '2026-08-01T00:00:00Z' }, { verified_at: '2026-11-01T00:00:00Z' },
  { price_valid_until: '2026-10-24' }, { source_hash: '' }, { validation_status: 'draft' }]) {
  ok(!auditReleaseConfig(env, { ...catalog, records: [{ ...row, ...patch }] }, now).configuration_ready);
}
ok(auditReleaseConfig(env, { ...catalog, records: [{ ...row, price_sek: null, verified_at: null }] }, now).configuration_ready);
ok(!auditReleaseConfig(env, { ...catalog, source: 'local_draft' }, now).configuration_ready);
ok(!auditReleaseConfig(env, { ...catalog, records: [] }, now).configuration_ready);
ok(operatorInfo(env).emailHref === 'mailto:contact@fixture.invalid');
console.log(JSON.stringify({ release_config_contract_ok: true, checks, network: 'offline_fixtures_only', paid_calls: 0, publications: 0 }));
