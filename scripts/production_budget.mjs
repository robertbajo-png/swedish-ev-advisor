import { PRICING_VERSION } from '../functions/_shared/ai-budget.mjs';

// Debit the new allowance, not historical receipts. The old ledger stays disabled.
export function productionHandover(snapshot, now = new Date()) {
  const day = now.toISOString().slice(0, 10);
  const checked = Date.parse(snapshot.checked_at_utc || '');
  if (snapshot.preview_enabled !== 0 || snapshot.production_enabled !== 0
      || snapshot.preview_unsettled !== 0
      || snapshot.production_reservations !== 0 || snapshot.day_utc !== day
      || !Number.isFinite(checked) || checked > now.getTime()
      || now.getTime() - checked > 120000
      || snapshot.pricing_version !== PRICING_VERSION
      || !/^\d{4}-\d{2}-\d{2}$/.test(snapshot.pricing_review_until || '')
      || !Number.isFinite(Date.parse(snapshot.pricing_review_until))
      || snapshot.pricing_review_until <= day) throw Error('Handover evidence is not current and disabled.');
  const { today_micro: daily, month_micro: monthly } = snapshot;
  if (!Number.isSafeInteger(daily) || !Number.isSafeInteger(monthly)
      || daily < 0 || monthly < daily || daily >= 1000000 || monthly >= 10000000) {
    throw Error('No verified remaining allowance.');
  }
  const dailyLimit = 1000000 - daily, monthlyLimit = 10000000 - monthly;
  return {
    daily_limit_micro: dailyLimit, monthly_limit_micro: monthlyLimit,
    previous_today_micro: daily, previous_month_micro: monthly,
    sql: `UPDATE ai_budget_policy SET enabled=1, daily_limit_micro=${dailyLimit}, monthly_limit_micro=${monthlyLimit}
WHERE id=1 AND enabled=0 AND daily_limit_micro=1000000 AND monthly_limit_micro=10000000
  AND pricing_version='${PRICING_VERSION}' AND pricing_review_until='${snapshot.pricing_review_until}'
  AND date('now')='${day}' AND NOT EXISTS (SELECT 1 FROM ai_budget_reservations)
RETURNING enabled,daily_limit_micro,monthly_limit_micro;`,
  };
}
