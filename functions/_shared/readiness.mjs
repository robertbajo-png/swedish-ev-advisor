import { BUDGET_MODEL, PRICING_VERSION } from './ai-budget.mjs';
import { loadPublicVariants } from './http.mjs';

export async function checkReadiness(context, { loadVariants = loadPublicVariants, now = new Date() } = {}) {
  const env = context.env || {};
  const checks = { catalog: false, ai_configuration: env.AI_ENABLED !== 'true', budget_storage: env.AI_ENABLED !== 'true' };
  try { checks.catalog = (await loadVariants(context)).length > 0; } catch { /* Report availability without source bodies. */ }
  if (env.AI_ENABLED === 'true') {
    checks.ai_configuration = Boolean(env.OPENAI_API_KEY?.trim() && env.OPENAI_MODEL === BUDGET_MODEL
      && typeof env.AI_BUDGET_SALT === 'string' && env.AI_BUDGET_SALT.length >= 32);
    try {
      const row = await env.AI_BUDGET_DB.prepare(`SELECT enabled, daily_limit_micro, monthly_limit_micro,
        pricing_version, pricing_review_until FROM ai_budget_policy WHERE id = 1`).first();
      checks.budget_storage = Boolean(row && [0, 1].includes(row.enabled)
        && row.daily_limit_micro > 0 && row.daily_limit_micro <= 1000000
        && row.monthly_limit_micro > 0 && row.monthly_limit_micro <= 10000000
        && row.pricing_version === PRICING_VERSION
        && /^\d{4}-\d{2}-\d{2}$/.test(row.pricing_review_until || '')
        && row.pricing_review_until > now.toISOString().slice(0, 10));
    } catch { checks.budget_storage = false; }
  }
  return { ok: Object.values(checks).every(Boolean), checks,
    ai_enabled: env.AI_ENABLED === 'true', provider_tested: false, paid_calls: 0 };
}
