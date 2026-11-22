import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, relative, resolve, sep } from 'node:path';

export const inventoryBadge = /Tillg\u00e4nglighet (?:ej )?bekr\u00e4ftad|Aktuell tillg\u00e4nglighet \u00e4r inte separat bekr\u00e4ftad|Marknadsn\u00e4rvaro inneb\u00e4r inte/i;
const expectedHash = 'fbaf3035f6791e75ec133ef19ff0aa27f57ff6bd74a10ea6790a998df19b33aa';

export async function applyPrivateInventoryCopy(root,commit,input) {
  assert.match(commit,/^[a-f0-9]{40}$/);
  assert.equal(await realpath(root),root);
  const repository = await realpath('.');
  const release = await realpath(join(repository,'data/local/release-data'));
  assert.equal(release,join(repository,'data','local','release-data'));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  const prefix = relative(repository,root).split(sep).join('/');
  assert.match(prefix,/^data\/local\/release-data\/(?:cupra-tavascan-(?:vz-)?|xpeng-g9-)readback-[a-z0-9]+\/ui-[a-z0-9]+\/source$/i);
  const patchPath = await realpath(input);
  assert.equal(patchPath,resolve(input));
  assert.equal(dirname(dirname(patchPath)),release);
  assert.match(basename(dirname(patchPath)),/^public-inventory-copy-review-[a-f0-9]+$/);
  assert.equal(basename(patchPath),'public-inventory-copy.patch');
  const patch = await readFile(patchPath);
  assert.equal(createHash('sha256').update(patch).digest('hex'),expectedHash,'Review patch bytes changed');
  const git = (args,opts={})=>execFileSync('git',args,{cwd:repository,timeout:15000,windowsHide:true,...opts});
  const files = ['scripts/prerender_static_routes.py','src/main.jsx','src/vehicle-names.js','src/vehicle-ui.jsx'];
  const changed = git(['apply','--numstat','-'],{encoding:'utf8',input:patch}).trim().split(/\r?\n/)
    .map(row=>row.split('\t').at(-1)).sort();
  assert.deepEqual(changed,files);
  let baselineNames;
  for(const file of files) {
    const original = git(['show',commit+':'+file]);
    const target = join(root,file);
    assert.equal(await realpath(dirname(target)),dirname(target));
    if(file.startsWith('scripts/')) await writeFile(target,original,{flag:'wx'});
    else {
      assert.equal(await realpath(target),target);
      const archived = await readFile(target,'utf8');
      assert(archived.replace(/\r\n/g,'\n')===original.toString('utf8'),`Unexpected baseline content in ${file}`);
      await writeFile(target,original);
    }
    if(file==='src/vehicle-names.js') baselineNames = await import('data:text/javascript;base64,'+original.toString('base64'));
  }
  git(['apply','--check','--directory='+prefix,'-'],{input:patch});
  git(['apply','--directory='+prefix,'-'],{input:patch});
  return {inventoryPatchHash:expectedHash,baselineNames};
}
