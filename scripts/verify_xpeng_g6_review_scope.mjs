import assert from 'node:assert/strict';
import { readFile, realpath } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { parseArgs } from 'node:util';
import { publicationHash } from './new_model_publication.mjs';
import { proveG6ReviewScope } from './revalidate_xpeng_g6_release.mjs';

const {values} = parseArgs({options: {reviewed: {type: 'string'}, ui: {type: 'string'}, fresh: {type: 'string'}}});
assert(values.reviewed && values.ui && values.fresh);
const root = await realpath('data/local/release-data');
async function receipt(path, name, prefix) {
  const file = await realpath(path);
  assert.equal(dirname(dirname(file)), root);
  assert.equal(basename(file), name);
  assert(basename(dirname(file)).startsWith(prefix));
  return JSON.parse(await readFile(file, 'utf8'));
}
const reviewed = await receipt(values.reviewed, 'readback.json', 'xpeng-g6-readback-');
const fresh = await receipt(values.fresh, 'fresh-readback.json', 'xpeng-g6-release-review-');
const ui = await receipt(values.ui, 'report.json', 'xpeng-g6-ui-');
const captured = new Date(fresh.plan.intake.market.source.fetched_at);
proveG6ReviewScope(reviewed, fresh, ui, captured);
const cases = [
  ['fewer_browser_runs', (current, checked) => { checked.runs.pop(); }, /browser matrix/],
  ['not_a_review_receipt', current => { current.apply_allowed = true; }, /strictly equal/],
  ['new_parent_scope', current => {
    current.plan.expected_model.available_confirmed = !current.plan.expected_model.available_confirmed;
  }, /production scope changed/],
  ['price_change', current => { current.plan.intake.drafts[0].price_evidence.value -= 5000; }, /profiles or evidence changed/],
  ['technical_pdf_change', current => {
    current.plan.intake.sources.find(row => row.source_type === 'technical_pdf').content_hash = 'a'.repeat(64);
  }, /technical PDF changed/],
  ['workbook_change', current => { current.plan.intake.market.source.content_hash = 'a'.repeat(64); }, /market workbook changed/],
  ['photo_change', current => { current.plan.image.content_sha256 = 'a'.repeat(64); }, /production scope changed/],
  ['expiry', current => { current.evidence_expires_at = captured.toISOString(); }, /window expired/],
  ['reused_capture', current => { current.review_hash = reviewed.review_hash; }, /newly fetched/],
];
for (const [name, adjust, message] of cases) {
  const current = structuredClone(fresh), checked = structuredClone(ui);
  adjust(current, checked);
  current.plan_hash = publicationHash(current.plan);
  assert.throws(() => proveG6ReviewScope(reviewed, current, checked, captured), message, name);
}
const remoteState = join(root, basename(dirname(values.fresh)), 'release-review.json');
const saved = await receipt(remoteState, 'release-review.json', 'xpeng-g6-release-review-');
assert.equal(saved.fresh_plan_sha256, fresh.plan_hash);
assert.equal(saved.apply_allowed, false);
console.log(JSON.stringify({status: 'passed', rejection_cases: cases.length, historical_replay: true, production_writes: 0}));
