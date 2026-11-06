import {readFile,readdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';

const folder=resolve(process.env.CATALOGUE_EXPORT_DIR||'.data/import');
const manifest=JSON.parse(await readFile(folder+'/manifest.json','utf8'));
if(!/^[a-f0-9]{24}$/.test(manifest.generation))throw new Error('Invalid export generation');
if(!process.env.CF_D1_DATABASE_ID&&!process.argv.includes('--local'))
 throw new Error('CF_D1_DATABASE_ID required for remote import');
await import('./config.mjs');
const location=process.argv.includes('--local')?'--local':'--remote';
const writeBudget=Number(process.env.D1_WRITE_BUDGET||Infinity);
function run(...args){
 const result=spawnSync(process.platform==='win32'?'npx.cmd':'npx',
  ['wrangler',...args],{encoding:'utf8',maxBuffer:20_000_000,env:process.env});
 if(result.status!==0||result.error)throw new Error('Wrangler D1 operation failed: '+
  ((result.stderr||result.stdout||'').slice(-2000)));
 return result.stdout;
}
function execute(command,json=false){
 return run('d1','execute','mirantir-stremio',location,'--config','wrangler.generated.jsonc',
  ...(json?['--json']:[]),'--command',command);
}
async function result(complete,extra={}){
 const value={complete,generation:manifest.generation,...extra};
 await writeFile(folder+'/import-result.json',JSON.stringify(value,null,2)+'\n');
 console.log(JSON.stringify(value));
}

run('d1','migrations','apply','mirantir-stremio',location,'--config','wrangler.generated.jsonc');
const stateRows=JSON.parse(execute('SELECT key,value FROM catalogue_state',true))?.[0]?.results||[];
const state=Object.fromEntries(stateRows.map(row=>[row.key,row.value]));

if(manifest.mode==='delta'){
 if(manifest.data_generation!==state.active_generation)
  throw new Error('Delta targets a different live catalogue generation');
 if(state.source_generation===manifest.generation){
  await result(true,{filesApplied:0,estimatedWrites:0});
 }else{
  const files=manifest.files||[];
  if(!files.every(file=>/^\d{4}-data\.sql$/.test(file.name)&&Number.isSafeInteger(file.writes)))
   throw new Error('Invalid delta file manifest');
  let next=0;
  if(state.delta_generation===manifest.generation)
   next=Math.max(0,Number.parseInt(state.delta_next_file||'0',10)||0);
  else execute("INSERT OR REPLACE INTO catalogue_state(key,value) VALUES"+
   `('delta_generation','${manifest.generation}'),('delta_next_file','0')`);
  let used=4,applied=0;
  while(next<files.length){
   const file=files[next];
   if(used+file.writes+4>writeBudget)break;
   console.log('Applying delta '+file.name+' (estimated '+file.writes+' indexed writes)');
   run('d1','execute','mirantir-stremio',location,'--config','wrangler.generated.jsonc',
    '--file',folder+'/'+file.name);
   next++;applied++;used+=file.writes+2;
   execute("INSERT OR REPLACE INTO catalogue_state(key,value) VALUES('delta_next_file',"+
    `'${next}')`);
  }
  if(next===files.length){
   const repo=String(manifest.source).replaceAll("'","''");
   execute("INSERT OR REPLACE INTO catalogue_state(key,value) VALUES"+
    `('source_generation','${manifest.generation}'),('source_repo','${repo}');`+
    "DELETE FROM catalogue_state WHERE key IN ('delta_generation','delta_next_file')");
   await result(true,{filesApplied:applied,estimatedWrites:used});
  }else{
   if(!applied&&files[next]?.writes+8>writeBudget)
    throw new Error('A delta chunk is larger than the daily D1 write budget');
   await result(false,{filesApplied:applied,nextFile:next,totalFiles:files.length,estimatedWrites:used});
  }
 }
}else{
 if(!manifest.counts?.catalogue_items)throw new Error('Missing full export counts');
 const estimatedWrites=manifest.counts.catalogue_items*4+
  manifest.counts.catalogue_episodes*2+manifest.counts.catalogue_links*3;
 if(Number.isFinite(writeBudget)&&estimatedWrites>writeBudget)
  throw new Error(`Full import needs up to ${estimatedWrites.toLocaleString()} indexed row writes, `+
   `above the configured ${writeBudget.toLocaleString()} safety budget; live catalogue left unchanged`);
 const files=(await readdir(folder)).filter(x=>/^\d{4}-(reset|data|activate)\.sql$/.test(x)).sort();
 if(files[0]!=='0000-reset.sql'||files.at(-1)!=='9999-activate.sql'||files.length<3)
  throw new Error('Incomplete staging export');
 if(state.active_generation===manifest.generation&&!process.argv.includes('--force')){
  await result(true,{filesApplied:0,estimatedWrites:0});
 }else{
  for(const file of files){
   console.log('Uploading '+file);
   run('d1','execute','mirantir-stremio',location,'--config','wrangler.generated.jsonc',
    '--file',folder+'/'+file);
  }
  await result(true,{filesApplied:files.length,estimatedWrites});
 }
}
