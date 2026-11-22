-- Preserve the public contract while allowing a verified edition-specific photo.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

do $photo_contract$
declare
  public_view regclass := 'public.public_ev_variants'::regclass;
  variants regclass := 'public.canonical_model_variants'::regclass;
  existing_definition text;
  projection text;
begin
  if not (select relrowsecurity from pg_class where oid = variants)
    or has_any_column_privilege('anon', variants, 'SELECT')
    or has_any_column_privilege('authenticated', variants, 'SELECT') then
    raise exception 'Expected a private canonical variant table';
  end if;
  if not exists (select 1 from pg_class c join pg_roles r on r.oid = c.relowner
    where c.oid = public_view and (r.rolsuper or r.rolbypassrls)
      and coalesce(c.reloptions, array[]::text[]) @> array['security_barrier=true']
      and not coalesce(c.reloptions, array[]::text[]) @> array['security_invoker=true']) then
    raise exception 'Expected an owner-privileged public catalog view';
  end if;
  if (select count(*) from pg_attribute where attrelid = public_view and attnum > 0 and not attisdropped
    and attname in ('id','image_url','image_source_url','price_source_url')) <> 4 then
    raise exception 'Apply the catalog and price contracts first';
  end if;

  alter table public.canonical_model_variants
    add column if not exists variant_image_url text,
    add column if not exists variant_image_source_url text;
  if not exists (select 1 from pg_constraint where conrelid = variants
    and conname = 'canonical_variant_photo_complete') then
    alter table public.canonical_model_variants add constraint canonical_variant_photo_complete check (
      (variant_image_url is null and variant_image_source_url is null)
      or (variant_image_url is not null and variant_image_source_url is not null
        and variant_image_url ~ '^/media/vehicles/[a-z0-9-]+-[a-f0-9]{12}\.jpg$'
        and variant_image_source_url ~ '^https://[^/@?#[:space:]]+/[^@?#[:space:]]+$'));
  end if;

  existing_definition := regexp_replace(pg_get_viewdef(public_view, true), ';[[:space:]]*$', '');
  if position('variant_photo.variant_image_url' in existing_definition) > 0
    and position('variant_photo.variant_image_source_url' in existing_definition) > 0 then
    return;
  end if;
  if existing_definition like '%variant_photo.variant_image%' then
    raise exception 'Partial variant photo projection';
  end if;

  select string_agg(case attname
      when 'image_url' then 'coalesce(variant_photo.variant_image_url, base.image_url) as image_url'
      when 'image_source_url' then 'coalesce(variant_photo.variant_image_source_url, base.image_source_url) as image_source_url'
      else format('base.%I', attname)
    end, ', ' order by attnum) into projection
    from pg_attribute where attrelid = public_view and attnum > 0 and not attisdropped;
  execute 'create or replace view public.public_ev_variants with (security_barrier=true) as select '
    || projection || ' from (' || existing_definition || ') base'
    || ' join public.canonical_model_variants variant_photo on variant_photo.id=base.id';
end;
$photo_contract$;

create or replace function public.invalidate_variant_photo_on_identity_change()
returns trigger language plpgsql set search_path=pg_catalog,public as $variant_photo$
begin
  if row(new.canonical_model_id,new.variant_name) is distinct from row(old.canonical_model_id,old.variant_name)
    and row(new.variant_image_url,new.variant_image_source_url) is not distinct from
        row(old.variant_image_url,old.variant_image_source_url) then
    new.variant_image_url := null;
    new.variant_image_source_url := null;
  end if;
  return new;
end;
$variant_photo$;
revoke all on function public.invalidate_variant_photo_on_identity_change() from public,anon,authenticated;
drop trigger if exists invalidate_variant_photo_on_identity_change on public.canonical_model_variants;
create trigger invalidate_variant_photo_on_identity_change
  before update of canonical_model_id,variant_name on public.canonical_model_variants
  for each row execute function public.invalidate_variant_photo_on_identity_change();

notify pgrst, 'reload schema';
commit;
