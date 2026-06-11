import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

const ROOT = process.cwd();
const PUBLIC_STATUSES = new Set(['published', 'published_reviewed']);
const FORBIDDEN_DATA_SOURCES = [
  'data/extraction/extracted_variant_drafts.json',
  'data/review/variant_review_queue.json',
  'data/canonical/canonical_model_variants_seed.json',
  'extracted_variant_drafts',
  'variant_review_queue',
  'canonical_model_variants_seed',
];

function variantKey(row) {
  return `${row.brand || ''}|${row.model || ''}|${row.variant_name || ''}`.toLowerCase();
}

function hasForbiddenReference(sourceText) {
  return FORBIDDEN_DATA_SOURCES.filter((needle) => sourceText.includes(needle));
}

async function loadPublicRows() {
  const payload = JSON.parse(await readFile(join(ROOT, 'public/data/public_ev_variants.json'), 'utf8'));
  return payload.records || [];
}

function validatePublicRows(rows) {
  const seen = new Set();
  const errors = [];
  for (const row of rows) {
    const key = variantKey(row);
    if (seen.has(key)) errors.push(`duplicate_public_variant:${key}`);
    seen.add(key);
    if (!PUBLIC_STATUSES.has(row.validation_status)) errors.push(`non_public_status:${key}:${row.validation_status}`);
    if (!row.source_url || !row.source_hash || !row.source_quote) errors.push(`missing_evidence:${key}`);
    if (String(row.source_url).toLowerCase().includes('mobilitysweden')) errors.push(`mobility_sweden_used_as_spec_source:${key}`);
    for (const flag of ['market_seen', 'available_confirmed', 'discontinued_candidate', 'coming_or_low_volume']) {
      if (typeof row[flag] !== 'boolean') errors.push(`market_flag_not_boolean:${key}:${flag}`);
    }
  }
  return errors;
}

async function main() {
  const [serverSource, frontendSource, publicRows] = await Promise.all([
    readFile(join(ROOT, 'server/advisor_api.mjs'), 'utf8'),
    readFile(join(ROOT, 'src/main.jsx'), 'utf8'),
    loadPublicRows(),
  ]);

  const errors = [
    ...validatePublicRows(publicRows),
    ...hasForbiddenReference(serverSource).map((item) => `server_references_forbidden_source:${item}`),
    ...hasForbiddenReference(frontendSource).map((item) => `frontend_references_forbidden_source:${item}`),
  ];

  if (!serverSource.includes('public/data/public_ev_variants.json')) {
    errors.push('server_missing_public_export_read');
  }
  if (!serverSource.includes('PUBLIC_STATUSES')) {
    errors.push('server_missing_public_status_filter');
  }
  if (!serverSource.includes('Använd aldrig externa fakta') && !serverSource.includes('AnvÃ¤nd aldrig externa fakta')) {
    errors.push('advisor_prompt_missing_no_external_facts_rule');
  }
  if (!frontendSource.includes('public_ev_variants')) {
    errors.push('frontend_missing_public_view_reference');
  }

  const report = {
    public_rows: publicRows.length,
    public_statuses: [...new Set(publicRows.map((row) => row.validation_status))].sort(),
    source_contract: 'advisor_and_frontend_read_public_variants_only',
    errors,
  };
  console.log(JSON.stringify(report, null, 2));
  if (errors.length) process.exit(1);
}

await main();
