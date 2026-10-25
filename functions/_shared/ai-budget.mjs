export const BUDGET_MODEL = 'gpt-5.4-mini';
export const PRICING_VERSION = 'gpt-5.4-mini-standard-2026-10-19';
const LIMITS = {
  advisor: { bytes: 10000, output: 512, reserve: 20000 },
  compare: { bytes: 24000, output: 2400, reserve: 50000 },
};

export const ANONYMIZE_CLIENTS_SQL = `UPDATE ai_budget_reservations
  SET client_hash = 'expired'
  WHERE created_at < unixepoch('now', 'start of day') AND client_hash <> 'expired'`;

// One primary write decides and reserves. Never split the check from the insert.
export const RESERVE_SQL = `
INSERT INTO ai_budget_reservations (id, kind, client_hash, reserved_micro, charged_micro)
SELECT ?1, ?2, ?3, ?4, ?4 FROM ai_budget_policy p
WHERE p.id = 1 AND p.enabled = 1 AND p.pricing_version = ?5
  AND date('now') < p.pricing_review_until
  AND ?4 + COALESCE((SELECT SUM(charged_micro) FROM ai_budget_reservations
    WHERE created_at >= unixepoch('now', 'start of day')), 0) <= p.daily_limit_micro
  AND ?4 + COALESCE((SELECT SUM(charged_micro) FROM ai_budget_reservations
    WHERE created_at >= unixepoch('now', 'start of month')), 0) <= p.monthly_limit_micro
  AND (SELECT COUNT(*) FROM ai_budget_reservations
    WHERE client_hash = ?3 AND created_at > unixepoch() - 60) < p.client_per_minute
  AND (SELECT COUNT(*) FROM ai_budget_reservations
    WHERE client_hash = ?3 AND created_at >= unixepoch('now', 'start of day')) < p.client_per_day
RETURNING id`;

export class AiBudgetError extends Error {
  constructor(code) { super(code); this.name = 'AiBudgetError'; this.budgetCode = code; }
}

export function requestAllowance(kind, body) {
  const limits = LIMITS[kind];
  const bytes = new TextEncoder().encode(JSON.stringify(body)).byteLength;
  if (!limits || body.model !== BUDGET_MODEL || body.service_tier !== 'default' || body.store !== false
    || body.max_output_tokens !== limits.output || bytes > limits.bytes
    || Object.keys(body).some((key) => !['model', 'store', 'service_tier', 'max_output_tokens', 'input', 'text'].includes(key))
    || !Array.isArray(body.input) || body.input.some((item) => typeof item.content !== 'string')) {
    throw new AiBudgetError('budget_policy');
  }
  return { ...limits, inputBound: bytes + 8192 };
}

export function usageCharge(payload, allowance) {
  const usage = payload?.usage;
  if (!usage) return null;
  const { input_tokens: input, output_tokens: output, total_tokens: total } = usage;
  const cached = usage.input_tokens_details?.cached_tokens ?? 0;
  if (payload.model !== BUDGET_MODEL && !/^gpt-5\.4-mini-\d{4}-\d{2}-\d{2}$/.test(payload.model || '')) return null;
  if (payload.service_tier !== 'default' || (usage.input_tokens_details?.cache_write_tokens ?? 0) !== 0
    || ![input, output, total, cached].every((n) => Number.isSafeInteger(n) && n >= 0)
    || cached > input || total !== input + output) return null;
  if (input > allowance.inputBound || output > allowance.output) throw new AiBudgetError('budget_usage_exceeded');
  const micro = Math.ceil(((input - cached) * 30 + cached * 3 + output * 180) / 40);
  if (micro > allowance.reserve) throw new AiBudgetError('budget_usage_exceeded');
  return micro;
}

async function clientHash(request, secret) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const day = new Date().toISOString().slice(0, 10);
  const ip = request.headers.get('cf-connecting-ip') || 'unknown';
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${day}|${ip}`));
  return Array.from(new Uint8Array(signature), (n) => n.toString(16).padStart(2, '0')).join('');
}

export function createAiBudget(env, request) {
  return {
    async reserve({ kind, body }) {
      const allowance = requestAllowance(kind, body);
      if (env.AI_ENABLED !== 'true') throw new AiBudgetError('budget_disabled');
      if (!env.AI_BUDGET_DB?.prepare || typeof env.AI_BUDGET_SALT !== 'string' || env.AI_BUDGET_SALT.length < 32) {
        throw new AiBudgetError('budget_unavailable');
      }
      const id = crypto.randomUUID();
      let row;
      try {
        await env.AI_BUDGET_DB.prepare(ANONYMIZE_CLIENTS_SQL).run();
        const hash = await clientHash(request, env.AI_BUDGET_SALT);
        row = await env.AI_BUDGET_DB.prepare(RESERVE_SQL).bind(id, kind, hash, allowance.reserve, PRICING_VERSION).first();
      } catch { throw new AiBudgetError('budget_unavailable'); }
      if (row?.id !== id) throw new AiBudgetError('budget_limited');
      return {
        async settle(payload) {
          try {
            const charge = usageCharge(payload, allowance);
            if (charge === null) return;
            await env.AI_BUDGET_DB.prepare(`UPDATE ai_budget_reservations
              SET charged_micro = ?1, settled = 1 WHERE id = ?2 AND settled = 0 AND ?1 <= reserved_micro`)
              .bind(charge, id).run();
          } catch (error) {
            // Uncertain calls keep their full reservation. Unexpected usage stops new spending.
            if (error?.budgetCode === 'budget_usage_exceeded') {
              await env.AI_BUDGET_DB.prepare('UPDATE ai_budget_policy SET enabled = 0 WHERE id = 1').run().catch(() => {});
            }
            console.error('AI budget settlement retained reservation.');
          }
        },
      };
    },
  };
}
