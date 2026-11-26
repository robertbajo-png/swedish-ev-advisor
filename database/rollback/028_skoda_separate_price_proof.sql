-- Roll back capability/code only. Never rewind an already published proof.
begin;
drop function if exists public.skoda_price_refresh_contract_v2();
drop function if exists public.publish_skoda_price_refresh_v2(jsonb);
notify pgrst,'reload schema';
commit;
