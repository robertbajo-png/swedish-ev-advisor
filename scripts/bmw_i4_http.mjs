import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {pathToFileURL} from 'node:url';

export const BMW_URLS={
 robots_bmw:'https://www.bmw.se/robots.txt',robots_stock:'https://hitta.bmw.se/robots.txt',
 technical:'https://www.bmw.se/sv/alla-modeller/i-series/i4/bmw-i4-gran-coupe-technical-data.html',
 model:'https://www.bmw.se/sv/alla-modeller/i-series/i4/bmw-i4-gran-coupe.html',
 stock:'https://hitta.bmw.se/r/G26E-i4/i4-eDrive40-WBY61HD030FW37556',
};

// Public GET transport only. The Python caller validates fresh robots before content.
export async function fetchBmwPublic(key,{fetchImpl=fetch}={}){
 assert(Object.hasOwn(BMW_URLS,key),'Only registered BMW source URLs');
 const url=BMW_URLS[key],limit=key.startsWith('robots_')?512000:8*1024*1024;
 const response=await fetchImpl(url,{method:'GET',redirect:'error',signal:AbortSignal.timeout(35000),
  headers:{'user-agent':'SwedishEVAdvisor/0.1','accept-language':'sv-SE,sv;q=0.9'}});
 assert.equal(response.status,200,'Reachable public BMW source required');
 assert.equal(response.url,url,'No redirected source or locale');
 assert.notEqual(response.headers.get('tdm-reservation'),'1','Reserved source');
 const type=response.headers.get('content-type')||'';
 assert(key.startsWith('robots_')?/text\/plain/i.test(type):/text\/html/i.test(type),'Expected public source content type');
 if(response.headers.has('content-length'))assert(Number(response.headers.get('content-length'))<=limit,'Bounded source required');
 const reader=response.body.getReader(),parts=[];let size=0;
 try{
  for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;assert(size<=limit,'Bounded source required');parts.push(value);}
 }finally{await reader.cancel().catch(()=>{});}
 const body=Buffer.concat(parts);assert(body.length>0);
 return {body,source:{status:'reachable',http_status:response.status,final_url:url,
  content_hash:createHash('sha256').update(body).digest('hex'),fetched_at:new Date().toISOString(),content_type:type}};
}

if(import.meta.url===pathToFileURL(resolve(process.argv[1]||'')).href){
 const {values}=parseArgs({options:{key:{type:'string'},output:{type:'string'}}});
 try{
  assert(values.output);const r=await fetchBmwPublic(values.key),dir=resolve(values.output);await mkdir(dir,{recursive:true});
  await writeFile(resolve(dir,values.key+'.body'),r.body);
  await writeFile(resolve(dir,values.key+'.json'),JSON.stringify(r.source,null,2)+'\n');
  console.log(JSON.stringify({source:values.key,status:r.source.status,bytes:r.body.length,paid_calls:0}));
 }catch(e){console.error(JSON.stringify({error:e.name,source:values.key,reason:'Public BMW transport failed; no credential or provider body logged'}));process.exitCode=1;}
}
