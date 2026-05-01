# Swedish EV Advisor

Premium Swedish AI-powered EV comparison service.

The service uses Mobility Sweden as the Swedish market model index and official Swedish manufacturer/importer sources for prices and specifications.

## Pipeline

```bash
python scripts/import_mobility_sweden.py
python scripts/build_source_queue.py
python scripts/validate_manufacturer_sources.py
python scripts/seed_supabase.py
python scripts/extract_manufacturer_specs.py --limit 5
python scripts/validate_extracted_variants.py
python scripts/seed_supabase.py
```

## Frontend

```bash
bun install
bun run dev
```

## Environment

Copy `.env.example` and set:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`

Public UI reads only from Supabase public views when configured.
