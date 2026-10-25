import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

export function packageErrors(path, body) {
  const errors = [];
  const p = path.replaceAll('\\', '/');
  if ((/(^|\/)\.env(?:\.|$)/.test(p) && p !== '.env.example') || /(^|\/)\.dev\.vars/.test(p)) errors.push('environment_file');
  if (/^(?:data\/local\/|data\/mobility-sweden\/raw\/|\.wrangler\/|dist\/)|\.(?:sqlite(?:-[\w]+)?|sqlite3|db|pem|key|pfx)$/i.test(p)) errors.push('private_or_generated_artifact');
  if (/^docs\/news-(?:engine-(?:smoke-test|operations)|hybrid-launch-plan)\.md$/.test(p)) errors.push('private_trial_history');
  if (Buffer.byteLength(body) > 2000000) errors.push('oversized_package_file');
  if (/sk-(?:proj-|svcacct-)[A-Za-z0-9_-]{24,}|\bsk-[A-Za-z0-9]{32,}|sb_secret_[A-Za-z0-9_-]{20,}|github_pat_[A-Za-z0-9_]{30,}|\bgh[pousr]_[A-Za-z0-9]{30,}/.test(body)) errors.push('credential_pattern');
  for (const token of body.match(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g) || []) {
    try {
      const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
      if (payload.role !== 'anon') errors.push('nonpublic_jwt');
    } catch { errors.push('unrecognized_jwt'); }
  }
  if (p.startsWith('tests/fixtures/') && p.endsWith('.json')) {
    try {
      const fixture = JSON.parse(body);
      if (fixture.fixture !== true || !/synthetic/i.test(fixture.fixture_description || '')) errors.push('fixture_not_explicitly_synthetic');
    } catch { errors.push('invalid_fixture_json'); }
  }
  return [...new Set(errors)];
}

function selfTest() {
  for (const path of ['.env', '.env.local', 'data/local/report.json', 'data/local/private.sqlite',
    'backup.sqlite', 'server.key', 'data/mobility-sweden/raw/source.xlsx',
    'docs/news-engine-operations.md', 'docs/news-engine-smoke-test.md']) assert(packageErrors(path, '').length > 0);
  assert.deepEqual(packageErrors('.env.example', 'OPENAI_API_KEY=your-openai-key'), []);
  assert.deepEqual(packageErrors('scripts/example.py', "token = os.environ.get('OPENAI_API_KEY')"), []);
  assert(packageErrors('file.txt', 'sk-proj-' + 'X'.repeat(60)).includes('credential_pattern'));
  const jwt = (role) => 'eyJhbGciOiJIUzI1NiJ9.' + Buffer.from(JSON.stringify({ role })).toString('base64url') + '.testsignature';
  assert(packageErrors('file.txt', jwt('service_role')).includes('nonpublic_jwt'));
  assert.deepEqual(packageErrors('file.txt', jwt('anon')), []);
  assert.deepEqual(packageErrors('tests/fixtures/example.json', JSON.stringify({ fixture: true, fixture_description: 'Synthetic fixture' })), []);
  assert(packageErrors('tests/fixtures/private.json', '{}').length > 0);
  return { news_package_guard_self_test_ok: true, paid_calls: 0, publications: 0 };
}

function staged() {
  const names = execFileSync('git', ['diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean);
  assert(names.length > 0, 'No staged release package to verify');
  const rejected = [];
  for (const path of names) {
    const body = execFileSync('git', ['show', ':' + path], { encoding: 'utf8', maxBuffer: 3000000 });
    const errors = packageErrors(path, body);
    if (errors.length) rejected.push({ path, errors });
  }
  console.log(JSON.stringify({ news_staged_package_ok: rejected.length === 0, files_checked: names.length, rejected,
    secret_values_printed: false, paid_calls: 0, publications: 0 }, null, 2));
  assert.equal(rejected.length, 0, 'Release package contains blocked files or credential patterns');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv[2] === '--self-test') console.log(JSON.stringify(selfTest()));
    else if (process.argv[2] === '--staged') staged();
    else throw new Error('Usage: node scripts/verify_news_package.mjs --self-test|--staged');
  } catch (error) {
    console.error(error.name === 'AssertionError' ? error.message : 'Package verification failed; file contents and credential values are not logged.');
    process.exitCode = 1;
  }
}
