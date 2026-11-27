-- Disable the one-off writer only. Preserve the archive and explicit withheld
-- state: restoring stale historical offers is not a rollback of this operation.
begin;
revoke execute on function public.publish_scoped_price_reverification_20261127(jsonb) from service_role;
commit;
