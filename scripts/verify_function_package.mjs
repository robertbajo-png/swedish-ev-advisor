import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdir, mkdtemp, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { functionSourceFiles } from './production_news_distribution.mjs';

assert(process.versions.bun, 'Run the isolated function package check with the existing Bun runtime');
const sha = execFileSync('git', ['rev-parse','HEAD'], { encoding:'utf8', windowsHide:true }).trim();
const files = functionSourceFiles(sha);
const parent = path.resolve('data/local/function-package-qa');
await mkdir(parent, { recursive:true });
const folder = await mkdtemp(path.join(parent, 'build-'));
for (const file of files) {
  await mkdir(path.dirname(path.join(folder,file)), { recursive:true });
  await writeFile(path.join(folder,file), execFileSync('git',['show',sha+':'+file], { windowsHide:true }));
}
await writeFile(path.join(folder,'package.json'), '{"type":"module"}\n');
const result = spawnSync(process.execPath, ['x','wrangler@4.154.0','pages','functions','build','functions',
  '--outdir',path.join(folder,'compiled')], { cwd:folder, windowsHide:true, stdio:'inherit', timeout:120000,
  env:{...process.env,WRANGLER_SEND_METRICS:'false',CLOUDFLARE_API_TOKEN:'',CLOUDFLARE_ACCOUNT_ID:'',OPENAI_API_KEY:'',SUPABASE_SERVICE_ROLE_KEY:''} });
assert.equal(result.status,0,'The isolated production function package must compile without repo-only dependencies');
const modulePath = path.join(folder,'src/spec-qualifications.js');
await rename(modulePath,modulePath+'.withheld');
try {
  const missing = spawnSync(process.execPath, ['x','wrangler@4.154.0','pages','functions','build','functions',
    '--outdir',path.join(folder,'negative')], { cwd:folder,windowsHide:true,encoding:'utf8',timeout:120000,
    env:{...process.env,WRANGLER_SEND_METRICS:'false',CLOUDFLARE_API_TOKEN:'',CLOUDFLARE_ACCOUNT_ID:'',OPENAI_API_KEY:'',SUPABASE_SERVICE_ROLE_KEY:''} });
  assert.notEqual(missing.status,0,'An omitted shared module must fail before upload');
  assert((missing.stderr||'').includes('spec-qualifications.js'));
} finally { await rename(modulePath+'.withheld',modulePath); }
console.log(JSON.stringify({isolated_function_package:'passed',missing_dependency_rejected:true,files:files.length,uploads:0,paid_calls:0,credentials_used:false}));
