import assert from 'node:assert/strict';
import {mkdir,writeFile,unlink} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import path from 'node:path';
import {createServer,normalizePath,resolveConfig} from 'vite';

const root=process.cwd(),id=randomUUID();
const marker='SYNTHETIC_PRIVATE_FILE_PROBE_'+id;
const files=[`data/local/http-boundary-${id}.txt`,`data/review/http-boundary-${id}.txt`,`.dev.vars.http-boundary-${id}`,`.wrangler/http-boundary-${id}.txt`];
const created=[];
let server;
try {
  for(const name of files){const absolute=path.join(root,name);await mkdir(path.dirname(absolute),{recursive:true});await writeFile(absolute,marker,{flag:'wx'});created.push(absolute);}
  const defaults=await resolveConfig({configFile:false,envFile:false},'serve');
  server=await createServer({configLoader:'runner',logLevel:'silent',server:{host:'127.0.0.1',port:0,strictPort:true}});
  for(const pattern of defaults.server.fs.deny)assert(server.config.server.fs.deny.includes(pattern),'Built-in Vite deny rule lost');
  await server.listen();
  const base='http://127.0.0.1:'+server.httpServer.address().port;
  const publicResponse=await fetch(base+'/data/public_ev_variants.json');
  assert.equal(publicResponse.status,200);
  const catalog=await publicResponse.json();
  assert(catalog.records.length>0&&catalog.records.every(row=>['published','published_reviewed'].includes(row.validation_status)));
  const source=await fetch(base+'/src/main.jsx');assert.equal(source.status,200);await source.arrayBuffer();
  const routes=[...files.map(name=>'/'+name),'/'+files[0]+'?raw','/@fs/'+normalizePath(path.join(root,files[0])),
    '/%64ata/%6cocal/'+path.basename(files[0]),'/DATA/LOCAL/'+path.basename(files[0])];
  let blocked=0;
  for(const route of routes){
    const response=await fetch(new URL(route,base));const body=await response.text();
    assert(!body.includes(marker),'Private synthetic fixture was served');
    if(!route.startsWith('/DATA/')||process.platform==='win32')assert.equal(response.status,403,'Expected file denial: '+route);
    if(response.status===403)blocked++;
  }
  console.log(JSON.stringify({dev_file_boundary_ok:true,blocked_routes:blocked,public_canonical_catalog_available:true,frontend_source_available:true,builtin_secret_rules_preserved:true,synthetic_files_only:true,database_backups_read:0,provider_calls:0}));
}finally{
  try { await server?.close(); }
  finally { for(const absolute of created)await unlink(absolute).catch(error=>{if(error.code!=='ENOENT')throw error;}); }
}
