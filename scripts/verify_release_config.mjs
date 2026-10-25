import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { loadEnv } from 'vite';
import { operatorInfo, SITE_ORIGIN } from '../src/site-info.js';

export function auditReleaseConfig(env, catalog, now = new Date()) {
  const operator = operatorInfo(env);
  const rows = Array.isArray(catalog?.records) ? catalog.records : [];
  const today = now.toISOString().slice(0, 10);
  const stalePrices = rows.filter(row => {
    if (row.price_sek == null) return false;
    const verified = Date.parse(row.verified_at || '');
    return !Number.isFinite(verified) || verified > now.getTime() || now.getTime() - verified > 30 * 86400000
      || (row.price_valid_until && row.price_valid_until.slice(0, 10) < today);
  });
  const sourceSafe = rows.length > 0 && rows.every(row => ['published', 'published_reviewed'].includes(row.validation_status)
    && /^[a-f0-9]{64}$/i.test(row.source_hash || '') && /^https:\/\//.test(row.source_url || ''));
  const checks = {
    canonical_snapshot: catalog?.source === 'supabase_public_ev_variants' && sourceSafe,
    production_origin: (env.SITE_URL || SITE_ORIGIN).replace(/\/$/, '') === SITE_ORIGIN
      && (env.VITE_SITE_URL || SITE_ORIGIN).replace(/\/$/, '') === SITE_ORIGIN,
    operator_contact: operator.configured,
    privacy_review: env.PUBLIC_PRIVACY_REVIEWED === 'true',
    image_rights_review: env.PUBLIC_IMAGE_RIGHTS_REVIEWED === 'true',
    current_published_prices: stalePrices.length === 0,
    no_client_secrets: !Object.keys(env).some(name => /^VITE_.*(?:OPENAI_API_KEY|SERVICE_ROLE|CLOUDFLARE_API_TOKEN|AI_BUDGET_SALT)/.test(name) && env[name]),
  };
  return { configuration_ready: Object.values(checks).every(Boolean), checks,
    blockers: Object.entries(checks).filter(([, ok]) => !ok).map(([key]) => key),
    counts: { models: new Set(rows.map(r => r.brand + '|' + r.model)).size, variants: rows.length,
      prices_requiring_verification: stalePrices.length, prices_with_verification: rows.filter(r => r.price_sek != null).length - stalePrices.length },
    scope: 'Offline production configuration/data checks only; runtime, DNS, legal compliance and real-device proofs remain separate',
    paid_calls: 0, publications: 0, writes: 0 };
}

async function main() {
  const env = { ...loadEnv('production', process.cwd(), ''), ...process.env };
  const catalog = JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8'));
  const report = auditReleaseConfig(env, catalog);
  console.log(JSON.stringify(report, null, 2));
  if (process.argv.includes('--production') && !report.configuration_ready) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { console.error('Release configuration check failed; no secret values logged.'); process.exitCode = 1; });
}
