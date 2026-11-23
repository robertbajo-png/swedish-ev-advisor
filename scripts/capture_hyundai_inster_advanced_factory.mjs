import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir,mkdtemp,readFile,realpath,stat,writeFile} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {MATERIAL,facts} from './hyundai_inster_advanced_publication.mjs';

const root=resolve(fileURLToPath(new URL('../',import.meta.url)));
assert.equal(await realpath(root),root);
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(root));
let release=root;
for(const subdir of ['data','local','release-data']){
  release=join(release,subdir);
  await mkdir(release,{recursive:true});
  assert.equal(await realpath(release),release);
}
const prefix='hyundai-inster-advanced-emissions-';
const [mode,target,...extra]=process.argv.slice(2);
assert(!extra.length&&((mode==='--replay'&&target)||(!mode&&!target)));
const replay=mode?resolve(target):null;
let saved;
async function readPacket(file,limit){
  const source=join(replay,file);
  assert.equal(await realpath(source),source);
  const info=await stat(source);
  assert(info.isFile()&&info.size>0&&info.size<=limit);
  return readFile(source);
}
if(replay){
  assert.equal(await realpath(replay),replay);
  assert.equal(dirname(replay),release);
  assert.match(basename(replay),new RegExp('^'+prefix+'[a-z0-9]+$','i'));
  saved=JSON.parse(await readPacket('report.json',10_000));
}

// Select only the fields used by the exact Swedish profile.
const queries={
  Trims:`query Trims($country: TrimmedString!, $language: TrimmedString!, $modelId: TrimmedString!, $service: TrimmedString!) {
    hppFscs2(country: $country, language: $language, modelId: $modelId, service: $service) {
      fsc modelId: modelCd trimName: trimNm trimId powertrainId powertrainNm fscPrice
      packages { pkgNm }
    }
  }`,
  EmissionQuery:`query EmissionQuery($country: TrimmedString!, $language: TrimmedString!, $fsc: TrimmedString!, $service: TrimmedString!) {
    hppCo2(country: $country, language: $language, fsc: $fsc, service: $service) {
      allElectricRange electricityConsumpCombined
    }
  }`,
  Powertrains:`query Powertrains($country: TrimmedString!, $language: TrimmedString, $modelId: TrimmedString!, $service: TrimmedString!, $trim: TrimmedString) {
    hppPowertrains(country: $country, language: $language, modelId: $modelId, service: $service, trim: $trim) {
      powertrainId powertrainNmEngine powertrainNmDrivetrain fuelTypeNm
      evBatteryCapacityKwh maxChargingPower evObcMaximumCapacity evMaxPowerKw
    }
  }`,
};
const endpoint='https://org-eu-www.hyundai.com/eu/papi';
const cap=1_000_000;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const base={country:'se',language:'sv',service:'S03'};
async function query(operationName,args){
  const query=queries[operationName];
  const body=JSON.stringify({operationName,query,variables:{...base,...args}});
  let bytes,fetched_at;
  if(replay){
    assert.equal((await readPacket(operationName+'-request.json',10_000)).toString(),body,'Read request changed');
    bytes=await readPacket(operationName+'-response.json',cap);
    fetched_at=saved.sources[operationName].fetched_at;
    assert.equal(new Date(fetched_at).toISOString(),fetched_at);
  }else{
    const response=await fetch(endpoint,{method:'POST',headers:{'content-type':'application/json',accept:'application/json'},
      body,redirect:'error',signal:AbortSignal.timeout(20000)});
    assert.equal(response.status,200,'Factory read refused: '+operationName);
    assert.match(response.headers.get('content-type')||'',/^application\/json\b/i);
    const reader=response.body.getReader();
    const chunks=[];
    let size=0;
    try {
      for(;;){
        const result=await reader.read();
        if(result.done)break;
        size+=result.value.length;
        assert(size<=cap,'Factory response exceeded size limit');
        chunks.push(result.value);
      }
    }finally{
      await reader.cancel();
    }
    bytes=Buffer.concat(chunks,size);
    fetched_at=new Date().toISOString();
  }
  assert(bytes.length>0&&bytes.length<=cap);
  const {data,errors}=JSON.parse(bytes);
  assert(!errors&&data,'Factory refused exact read: '+operationName);
  return {body,bytes,data,receipt:{fetched_at,url:endpoint,http_status:200,
    request_hash:hash(body),source_hash:hash(bytes)}};
}

const trims=await query('Trims',{modelId:'6X'});
const exact=trims.data.hppFscs2.filter(row=>row.fsc===MATERIAL);
assert.equal(exact.length,1);
const [trim]=exact;
assert.deepEqual([trim.modelId,trim.trimName,trim.trimId,trim.powertrainId,trim.powertrainNm,trim.fscPrice],
  ['6X','Advanced','TR0003','6XS5ZDZ7Z|1','49kWh',377900]);
const packages=trim.packages.map(row=>row.pkgNm);
assert.deepEqual([...packages].sort(),["17'' Aluminiumf\u00e4lgar",'Tech-paket']);
const emissions=await query('EmissionQuery',{fsc:MATERIAL});
const powertrains=await query('Powertrains',{modelId:'6X',trim:trim.trimId});
const matching=powertrains.data.hppPowertrains.filter(row=>row.powertrainId===trim.powertrainId);
assert.equal(matching.length,1);
const [power]=matching;
assert.deepEqual([power.fuelTypeNm,power.powertrainNmDrivetrain,power.powertrainNmEngine],['El','Framhjulsdrift','49kWh']);
const number=value=>{
  assert.match(String(value),/^\d+(?:[,.]\d+)?$/);
  return Number(String(value).replace(',','.'));
};
const readings={
  combined_wltp_km:number(emissions.data.hppCo2.allElectricRange),
  consumption_kwh_100km:number(emissions.data.hppCo2.electricityConsumpCombined),
  battery_kwh:number(power.evBatteryCapacityKwh),
  dc_charge_kw:number(power.maxChargingPower),
  ac_charge_kw:number(power.evObcMaximumCapacity),
};
assert.deepEqual(Object.values(readings),[facts.wltp_range_km,facts.wltp_consumption_kwh_100km,
  facts.battery_kwh,facts.dc_charge_kw,facts.ac_charge_kw],'Exact factory readings changed; review before updating');
const verified={Trims:trims,EmissionQuery:emissions,Powertrains:powertrains};
const report={status:'private_exact_swedish_advanced_emissions_hardware',material:MATERIAL,market:'SE',
  variant:'49 kWh Advanced Tech 17-inch',...readings,factory_price_excluding_optional_paint_sek:trim.fscPrice,
  packages,drivetrain:'FWD',motor_power_kw:number(power.evMaxPowerKw),
  sources:Object.fromEntries(Object.entries(verified).map(([name,{receipt}])=>[name,receipt])),
  publication_approved:false,database_writes:0,paid_calls:0};
const folder=replay??await mkdtemp(join(release,prefix));
if(replay)assert.deepEqual(report,saved,'Factory evidence changed');
else{
  for(const [name,{body,bytes}] of Object.entries(verified)){
    await writeFile(join(folder,name+'-request.json'),body,{flag:'wx'});
    await writeFile(join(folder,name+'-response.json'),bytes,{flag:'wx'});
  }
  await writeFile(join(folder,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
}
console.log(JSON.stringify({...report,folder,replay:!!replay}));
