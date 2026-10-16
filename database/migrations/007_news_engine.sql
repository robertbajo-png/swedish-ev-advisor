-- News is a separate bounded context. Raw items/evidence are service-role only.
create table if not exists news_sources (
  id text primary key,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
create table if not exists news_ingestion_runs (
  id text primary key,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
create table if not exists news_story_clusters (
  id text primary key,
  event_key text not null unique,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
create table if not exists news_items (
  id text primary key,
  source_id text not null references news_sources(id),
  url text not null unique,
  cluster_id text references news_story_clusters(id),
  status text not null default 'collected' check (status in ('collected','ready','processed','quarantined','irrelevant')),
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
create table if not exists news_articles (
  id text primary key,
  cluster_id text not null unique references news_story_clusters(id),
  slug text not null unique check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  status text not null default 'draft' check (status in ('draft','quarantined','published')),
  artifact_hash text not null default '',
  published_at timestamptz,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
create table if not exists news_article_sources (
  id text primary key,
  article_id text not null references news_articles(id),
  item_id text not null references news_items(id),
  payload jsonb not null,
  updated_at timestamptz not null default now(),
  unique(article_id,item_id)
);
create table if not exists news_vehicle_links (
  id text primary key,
  article_id text not null references news_articles(id),
  canonical_model_id uuid references canonical_models(id),
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
create table if not exists news_quality_checks (
  id text primary key,
  article_id text not null references news_articles(id),
  kind text not null check (kind in ('evidence','editorial','originality')),
  artifact_hash text not null,
  passed boolean not null default false,
  payload jsonb not null,
  updated_at timestamptz not null default now(),
  unique(article_id,kind,artifact_hash)
);
create table if not exists news_verification_requests (
  id text primary key,
  article_id text not null references news_articles(id),
  status text not null default 'pending' check (status in ('pending','exported','completed','failed')),
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
create index if not exists news_items_pending on news_items(status,updated_at);
create index if not exists news_items_cluster on news_items(cluster_id);
create index if not exists news_articles_public on news_articles(published_at desc) where status='published';

do $$ declare t text; begin
  foreach t in array array['news_sources','news_ingestion_runs','news_items','news_story_clusters',
    'news_articles','news_article_sources','news_vehicle_links','news_quality_checks','news_verification_requests'] loop
    execute format('alter table %I enable row level security',t);
    execute format('revoke all on %I from anon, authenticated',t);
    execute format('grant all on %I to service_role',t);
  end loop;
end $$;

create or replace function news_guard_publication() returns trigger
language plpgsql set search_path = public, extensions as $$
begin
  new.artifact_hash := encode(digest(new.payload::text, 'sha256'),'hex');
  if tg_op = 'UPDATE' and old.status = 'published' and new.payload is distinct from old.payload then
    raise exception 'Published news payload is immutable; create a separately checked correction';
  end if;
  if new.status = 'published' then
    if (select count(distinct kind) from news_quality_checks
        where article_id=new.id and passed and artifact_hash=new.artifact_hash) <> 3 then
      raise exception 'Missing or stale news quality gates';
    end if;
    if not exists(select 1 from news_article_sources s join news_items i on i.id=s.item_id
      where s.article_id=new.id and i.status='processed' and i.payload->>'access_status'='accessible') then
      raise exception 'News must have accessible attributed evidence';
    end if;
    new.published_at := coalesce(new.published_at, now());
  end if;
  new.updated_at := now();
  return new;
end $$;
drop trigger if exists news_publication_guard on news_articles;
create trigger news_publication_guard before insert or update on news_articles
for each row execute function news_guard_publication();

-- Serialize publication and the global daily limit across runners.
create or replace function publish_news_article(article_key text, daily_limit integer default 5)
returns void language plpgsql security definer set search_path=public as $$
declare current_status text;
begin
  perform pg_advisory_xact_lock(72716491);
  select status into current_status from news_articles where id=article_key for update;
  if current_status='published' then return; end if;
  if current_status is distinct from 'draft' then raise exception 'Article not in draft state'; end if;
  if (select count(*) from news_articles where status='published'
      and published_at >= date_trunc('day', now() at time zone 'UTC') at time zone 'UTC') >= least(greatest(daily_limit,0),5) then
    raise exception 'News daily publication limit reached';
  end if;
  update news_articles set status='published' where id=article_key;
end $$;
revoke all on function publish_news_article(text,integer) from public, anon, authenticated;
grant execute on function publish_news_article(text,integer) to service_role;

create or replace view public_news_articles as
select id,slug,published_at,
  (payload - 'title_fact_ids' - 'intro_fact_ids' - 'input_fingerprint' - 'relevance_score') ||
  jsonb_build_object('paragraphs', coalesce((select jsonb_agg(p - 'fact_ids')
    from jsonb_array_elements(payload->'paragraphs') p),'[]'::jsonb)) as payload
from news_articles where status='published';
grant select on public_news_articles to anon,authenticated;
