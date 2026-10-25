-- Owner-only exception handling. Retains the full reservation, never invents usage.
alter table public.news_ai_requests
  add column if not exists budget_closed_at timestamptz,
  add column if not exists budget_closed_by text,
  add column if not exists budget_closure_note text;

do $$ begin
  if not exists(select 1 from pg_constraint where conrelid='public.news_ai_requests'::regclass
                and conname='news_unknown_usage_budget_closure') then
    alter table public.news_ai_requests add constraint news_unknown_usage_budget_closure check (
      (budget_closed_at is null and budget_closed_by is null and budget_closure_note is null)
      or (budget_closed_at is not null and budget_closed_by is not null and budget_closure_note is not null
          and length(btrim(budget_closure_note)) between 20 and 500
          and settled_at is null and input_tokens is null and output_tokens is null
          and response_payload is null and provider_status='reserved'
          and reserved_micro_usd > 0 and charged_micro_usd=reserved_micro_usd)
    );
  end if;
end $$;

comment on column public.news_ai_requests.budget_closed_at is
  'Owner accepted the full reservation as budget cost. NOT known provider usage or an invoice.';

create or replace function public.guard_news_budget_closure() returns trigger
language plpgsql set search_path=pg_catalog,public as $$
begin
  if old.budget_closed_at is not null then
    if tg_op='DELETE' or new is distinct from old then
      raise exception 'news_conservative_budget_closure_immutable';
    end if;
  end if;
  if tg_op='DELETE' then return old; end if;
  return new;
end $$;
drop trigger if exists news_budget_closure_immutable on public.news_ai_requests;
create trigger news_budget_closure_immutable before update or delete on public.news_ai_requests
for each row execute function public.guard_news_budget_closure();
revoke all on function public.guard_news_budget_closure() from public,anon,authenticated,service_role;

create or replace function public.close_news_unknown_usage_budget(
  request_key uuid, expected_reservation bigint, expected_digest text, approval_note text
) returns jsonb language plpgsql set search_path=pg_catalog,public as $$
declare req public.news_ai_requests; cfg public.news_ai_config;
begin
  perform pg_advisory_xact_lock(72716492);
  if approval_note is null or length(btrim(approval_note)) not between 20 and 500 then
    raise exception 'news_budget_closure_approval_note_required';
  end if;
  select * into req from public.news_ai_requests where id=request_key for update;
  if not found then raise exception 'news_budget_closure_request_missing'; end if;
  if expected_reservation is null or expected_reservation <= 0 or expected_digest is null
    or expected_digest !~ '^[a-f0-9]{64}$' or req.request_hash is distinct from expected_digest
    or req.reserved_micro_usd is distinct from expected_reservation
    or req.charged_micro_usd is distinct from expected_reservation then
    raise exception 'news_budget_closure_request_mismatch';
  end if;
  if req.budget_closed_at is not null then
    if req.budget_closure_note is distinct from btrim(approval_note) then
      raise exception 'news_budget_closure_approval_mismatch';
    end if;
    return jsonb_build_object('budget_closed',true,'already_closed',true,'usage_known',false,
                             'counted_micro_usd',req.charged_micro_usd);
  end if;
  select * into cfg from public.news_ai_config where id='production' for update;
  if not found or cfg.enabled or cfg.publication_enabled then
    raise exception 'news_budget_closure_requires_paused_engine';
  end if;
  if req.created_at > clock_timestamp()-interval '5 minutes' then
    raise exception 'news_budget_closure_request_too_recent';
  end if;
  if req.settled_at is not null or req.input_tokens is not null or req.output_tokens is not null
    or req.response_payload is not null or req.provider_status <> 'reserved' then
    raise exception 'news_budget_closure_requires_unknown_usage';
  end if;
  if exists(select 1 from public.news_ingestion_runs where id=request_key::text
    and payload->>'kind'='news_ai_request'
    and (payload->>'input_tokens' is not null or payload->>'output_tokens' is not null)) then
    raise exception 'news_known_usage_requires_normal_settlement';
  end if;
  update public.news_ai_requests set budget_closed_at=clock_timestamp(),budget_closed_by=current_user,
    budget_closure_note=btrim(approval_note) where id=request_key;
  return jsonb_build_object('budget_closed',true,'already_closed',false,'usage_known',false,
                           'counted_micro_usd',req.charged_micro_usd);
end $$;

-- Invoker function: no app role can approve, refund, reset or rewrite a request.
revoke all on function public.close_news_unknown_usage_budget(uuid,bigint,text,text)
  from public,anon,authenticated,service_role;
