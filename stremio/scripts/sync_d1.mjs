import {spawnSync} from 'node:child_process';
import {access,copyFile,mkdir,readFile,rename,rm,writeFile} from 'node:fs/promises';

const npx=process.platform==='win32'?'npx.cmd':'npx';
const python=process.env.PYTHON||'python3';
const sourceDir='.data/source',baseDb=sourceDir+'/catalogue.sqlite',baseState=sourceDir+'/state.json';
const pendingDb=sourceDir+'/pending.sqlite',pendingState=sourceDir+'/pending-state.json';
const cacheMeta=sourceDir+'/cache.json',pendingMeta=sourceDir+'/pending.json';
function run(command,args,{allowFailure=false,quiet=false}={}){
 const result=spawnSync(command,args,{encoding:'utf8',maxBuffer:30_000_000,env:process.env});
 if((result.status!==0||result.error)&&!allowFailure)
  throw new Error('Command failed: '+command+' '+args.join(' ')+'\n'+(result.stderr||result.stdout||'').slice(-3000));
 if(!quiet&&result.stdout)process.stdout.write(result.stdout);
 return result;
}
const exists=async path=>access(path).then(()=>true,()=>false);
const readJson=async path=>JSON.parse(await readFile(path,'utf8'));
function d1(command,json=false){
 return run(npx,['wrangler','d1','execute','mirantir-stremio','--remote',
  '--config','wrangler.generated.jsonc',...(json?['--json']:[]),'--command',command],{quiet:true}).stdout;
}
function sourceArgs(db,state,source){
 const args=['scripts/sync_source.py','--db',db,'--state',state];
 if(source)args.push('--source-repo',source);return args;
}

run(process.execPath,['scripts/config.mjs','--production'],{quiet:true});
await mkdir(sourceDir,{recursive:true});
const rows=JSON.parse(d1("SELECT key,value FROM catalogue_state WHERE key IN ('active_generation','source_generation','source_repo')",true))?.[0]?.results||[];
const state=Object.fromEntries(rows.map(row=>[row.key,row.value]));
if(!/^[a-f0-9]{24}$/.test(state.active_generation||''))throw new Error('Live D1 catalogue is not initialized');
const knownGeneration=state.source_generation||state.active_generation;
const source=/^(?:[\w.-]+\/[\w.-]+|https:\/\/[^\s]+)$/.test(state.source_repo||'')?state.source_repo:null;

let upstream;
if(await exists(pendingMeta))upstream=await readJson(pendingMeta);
else{
 const checkArgs=['scripts/export_catalogue.py','--check-only'];if(source)checkArgs.push('--source-repo',source);
 upstream=JSON.parse(run(python,checkArgs,{quiet:true}).stdout);
}

if(!(await exists(baseDb))){
 console.log('Seeding verified upstream cache without rewriting D1');
 const seeded=JSON.parse(run(python,sourceArgs(baseDb,baseState,source),{quiet:true}).stdout);
 if(seeded.generation!==knownGeneration)
  throw new Error('Cannot bootstrap incremental cache: live D1 and upstream generations differ');
 d1("INSERT OR REPLACE INTO catalogue_state(key,value) VALUES('source_generation','"+seeded.generation+"')");
 await writeFile(cacheMeta,JSON.stringify({generation:seeded.generation})+'\n');
 console.log('Seeded source cache at '+seeded.generation);process.exit(0);
}

const cached=await readJson(cacheMeta).catch(()=>({}));
if(cached.generation!==knownGeneration)
 throw new Error('Cached source generation does not match D1; refusing an unsafe delta');
if(!(await exists(pendingMeta))&&upstream.generation===knownGeneration){
 console.log('Catalogue unchanged at '+upstream.generation+'; skipped download, export and D1 writes');
 process.exit(0);
}

if(!(await exists(pendingMeta))){
 console.log('Preparing incremental catalogue '+knownGeneration+' -> '+upstream.generation);
 await copyFile(baseDb,pendingDb);await copyFile(baseState,pendingState);
 const prepared=JSON.parse(run(python,sourceArgs(pendingDb,pendingState,source),{quiet:true}).stdout);
 if(prepared.generation!==upstream.generation)throw new Error('Upstream changed while preparing delta; retry next run');
 upstream=prepared;await writeFile(pendingMeta,JSON.stringify(prepared,null,2)+'\n');
}

run(python,['scripts/prepare_delta.py','--old',baseDb,'--new',pendingDb,
 '--output','.data/import','--data-generation',state.active_generation,
 '--source-generation',upstream.generation,'--source-repo',upstream.source]);
run(process.execPath,['scripts/import_d1.mjs']);
const imported=await readJson('.data/import/import-result.json');
if(imported.complete){
 await rename(pendingDb,baseDb);await rename(pendingState,baseState);
 await writeFile(cacheMeta,JSON.stringify({generation:upstream.generation})+'\n');
 await rm(pendingMeta,{force:true});
 console.log('Incremental catalogue update completed at '+upstream.generation);
}else console.log(`Incremental update paused at file ${imported.nextFile}/${imported.totalFiles}; resumes automatically`);
