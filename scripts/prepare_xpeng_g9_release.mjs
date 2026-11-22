import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { catalogHash } from './sync_public_catalog.mjs';
import { g9ApprovalHash, prepareG9ReleaseReview } from './xpeng_g9_release_review.mjs';

const {values} = parseArgs({options:{readback:{type:'string'},ui:{type:'string'}}});
assert(values.readback&&values.ui,'Supply the G9 post-live-G6 readback and its browser report');
const root = await realpath('.');
const evidence = await realpath('data/local/release-data');
assert.equal(evidence,join(root,'data','local','release-data'));
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(evidence));
const unlinked = async value=>{
  const absolute = resolve(value);
  assert.equal(await realpath(absolute),absolute,'Linked release evidence is not accepted');
  return absolute;
};
const folder = await unlinked(values.readback);
assert.equal(dirname(folder),evidence);
assert.match(basename(folder),/^xpeng-g9-readback-[a-z0-9]+$/i);
const uiFile = await unlinked(values.ui);
const uiRoot = dirname(uiFile);
assert.equal(dirname(uiRoot),folder);
assert.match(basename(uiRoot),/^ui-[a-z0-9]+$/i);
assert.equal(basename(uiFile),'ui-report.json');
const json = async file=>JSON.parse(await readFile(await unlinked(file),'utf8'));
const report = await json(join(folder,'report.json'));
assert.equal(report.g6_evidence,'live_catalog_and_view','The private G6 rehearsal cannot be used for a production review');
const plan = await json(join(folder,'g9-plan.json'));
const baseline = (await json(join(folder,'main-source/public/data/public_ev_variants.json'))).records;
const candidate = (await json(join(folder,'candidate-catalog.json'))).records;
const ui = await json(uiFile);
const reviewed = prepareG9ReleaseReview({report,ui,plan,baseline,candidate});
assert.equal(execFileSync('git',['ls-remote','origin','refs/heads/main'],{cwd:root,encoding:'utf8',timeout:20000}).trim(),
  reviewed.commit+'\trefs/heads/main','GitHub main changed after the G9 review');
const live = await fetch('https://elbilsagenten.se/data/public_ev_variants.json',{redirect:'error',signal:AbortSignal.timeout(15000)});
assert(live.ok);
assert.equal(catalogHash((await live.json()).records),reviewed.baseline_sha256,'The public catalog changed after the G9 review');
const digest = bytes=>createHash('sha256').update(bytes).digest('hex');
const built = await json(join(uiRoot,'dist/data/public_ev_variants.json'));
assert.equal(catalogHash(built.records),reviewed.candidate_sha256);
for(const {url,sha256} of reviewed.ui.g9_media) {
  assert.match(url,/^\/media\/(?:vehicles|responsive)\/xpeng-g9-press-[a-z0-9.-]+$/);
  assert.equal(digest(await readFile(await unlinked(join(uiRoot,'dist',url.slice(1))))),sha256,'G9 built photo bytes changed');
}
const output = await mkdtemp(join(evidence,'xpeng-g9-release-review-'));
const approval = g9ApprovalHash(reviewed);
await writeFile(join(output,'release-review.json'),JSON.stringify({status:'ready_for_owner_review',
  reviewed_scope_sha256:approval,reviewed,publication_approved:false,production_writes:0},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({status:'ready_for_owner_review',output,preserved:reviewed.preserved,added:2,
  reviewed_scope_sha256:approval,publication_approved:false,production_writes:0}));
