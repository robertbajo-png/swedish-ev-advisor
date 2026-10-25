import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';

const index = new URL('../dist/index.html', import.meta.url);
const before = await readFile(index, 'utf8').catch(() => null);
const result = spawnSync(process.execPath, ['scripts/build_release.mjs'], { encoding: 'utf8',
  env: { ...process.env, VITE_OPERATOR_NAME: '', VITE_CONTACT_EMAIL: '',
    PUBLIC_PRIVACY_REVIEWED: 'false', PUBLIC_IMAGE_RIGHTS_REVIEWED: 'false' }, windowsHide: true });
assert.equal(result.status, 1, 'Unconfigured release must stop before building');
const report = JSON.parse(result.stdout.trim());
assert.equal(report.configuration_ready, false);
assert(report.blockers.includes('operator_contact'));
assert.equal(await readFile(index, 'utf8').catch(() => null), before, 'Blocked build must not alter the existing preview');
console.log(JSON.stringify({ release_build_guard_ok: true, paid_calls: 0, writes: 0, deployments: 0 }));
