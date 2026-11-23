import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtemp,readFile,realpath,writeFile} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {createInsterReleaseScope} from './hyundai_inster_advanced_release_scope.mjs';
import {createMacanReleaseScope} from './porsche_macan_release_scope.mjs';

const {values}=parseArgs({options:{readback:{type:'string'},ui:{type:'string'},macan:{type:'boolean'}}});
assert(values.readback&&values.ui);
const root=await realpath('.');
const release=join(root,'data','local','release-data');
assert.equal(await realpath(release),release);
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
const dir=resolve(values.readback),uiDir=resolve(values.ui);
assert.equal(dirname(dir),release);
assert.equal(dirname(uiDir),dir);
assert.match(basename(dir),values.macan?/^porsche-macan-local-[a-z0-9]+$/i:/^inster-advanced-local-[a-z0-9]+$/i);
assert.match(basename(uiDir),/^ui-[a-z0-9]+$/i);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const bytes=async path=>{assert.equal(await realpath(path),path);return readFile(path);};
const json=async path=>JSON.parse(await bytes(path));
const [report,plan,baseline,candidate,ui,seo]=await Promise.all([
  ...['report','plan','baseline-catalog','candidate-catalog'].map(name=>json(join(dir,name+'.json'))),
  ...['ui-report','seo-report'].map(name=>json(join(uiDir,name+'.json'))),
]);
assert.equal(candidate.status,'local_only');
assert.equal(candidate.publication_approved,false);
const preview=join(uiDir,'source');
const path=plan.image.asset_url;
assert.equal(path,values.macan?'/media/vehicles/porsche-macan-electric-7a1901acfdb4.jpg'
  :'/media/vehicles/hyundai-inster-74c89ece773a.jpg');
const variants=(await json(join(preview,'src/image-variants.json')))[path];
assert.equal(variants.source_sha256,plan.image.content_sha256);
const media=[{url:path,sha256:variants.source_sha256},...variants.variants.map(({url,sha256})=>({url,sha256}))];
const scope=(values.macan?createMacanReleaseScope:createInsterReleaseScope)({
  plan,report,ui,seo,baseline:values.macan?baseline:baseline.records,candidate:candidate.records,media});
for(const asset of media){
  for(const source of [root,preview]){
    assert.equal(sha(await bytes(join(source,'public',asset.url.slice(1)))),asset.sha256,
      'Vehicle media changed since rehearsal: '+asset.url);
  }
}
const folder=await mkdtemp(join(release,values.macan?'macan-release-scope-':'inster-advanced-scope-')),file=join(folder,'scope.json');
await writeFile(file,JSON.stringify(scope,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({status:scope.status,file,candidate_sha256:scope.candidate_sha256,
  vehicle_delta:1,production_writes:0,publication_approved:false}));
