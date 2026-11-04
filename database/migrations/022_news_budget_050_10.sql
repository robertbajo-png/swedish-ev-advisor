-- Owner-approved budget increase only. No activation, spending or ledger reset.
do $$
declare cfg public.news_ai_config;
begin
  select * into cfg from public.news_ai_config where id='production' for update;
  if not found or cfg.model <> 'gpt-6-sol' or cfg.daily_article_limit <> 1
    or not ((cfg.daily_limit_micro_usd=250000 and cfg.monthly_limit_micro_usd=5000000)
         or (cfg.daily_limit_micro_usd=500000 and cfg.monthly_limit_micro_usd=10000000)) then
    raise exception 'Unexpected news configuration; budget change refused';
  end if;
  if exists(select 1 from public.news_ai_requests where (settled_at is null and budget_closed_at is null)
            or provider_status='accounting_anomaly') then
    raise exception 'Reconcile news usage before changing budgets';
  end if;
  if exists(select 1 from public.news_notice_release_config where enabled) then
    raise exception 'Unexpected notice activation; budget change refused';
  end if;

  alter table public.news_ai_config drop constraint if exists news_ai_config_daily_limit_micro_usd_check;
  alter table public.news_ai_config add constraint news_ai_config_daily_limit_micro_usd_check
    check (daily_limit_micro_usd between 0 and 500000);
  alter table public.news_ai_config drop constraint if exists news_ai_config_monthly_limit_micro_usd_check;
  alter table public.news_ai_config add constraint news_ai_config_monthly_limit_micro_usd_check
    check (monthly_limit_micro_usd between 0 and 10000000);

  if cfg.daily_limit_micro_usd=250000 then
    update public.news_ai_config set daily_limit_micro_usd=500000, monthly_limit_micro_usd=10000000,
      approval_note=concat_ws(E'\n',approval_note,'Owner approved USD0.50/day and USD10/month on 2026-11-04; all other controls preserved')
      where id='production';
  end if;
end $$;
