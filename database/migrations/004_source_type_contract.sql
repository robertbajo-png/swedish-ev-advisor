do $$ begin
  alter type source_type add value if not exists 'manufacturer_indexed_model_page';
  alter type source_type add value if not exists 'manufacturer_official_override_source';
exception
  when duplicate_object then null;
end $$;
