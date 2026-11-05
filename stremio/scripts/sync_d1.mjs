import {spawnSync} from 'node:child_process';

const npx=process.platform==='win32'?'npx.cmd':'npx';
const python=process.env.PYTHON||'python3';
function run(command,args,{allowFailure=false,quiet=false}={}){
 const result=spawnSync(command,args,{encoding:'utf8',maxBuffer:30_000_000,env:process.env});
 if((result.status!==0||result.error)&&!allowFailure)
  throw new Error('Command failed: '+command+' '+args.join(' ')+'\n'+(result.stderr||result.stdout||'').slice(-3000));
 if(!quiet&&result.stdout)process.stdout.write(result.stdout);
 return result;
}

run(process.execPath,['scripts/config.mjs','--production'],{quiet:true});
const stateResult=run(npx,['wrangler','d1','execute','mirantir-stremio','--remote',
 '--config','wrangler.generated.jsonc','--json','--command',
 "SELECT key,value FROM catalogue_state WHERE key IN ('active_generation','source_repo')"],
 {allowFailure:true,quiet:true});
let state={};
if(stateResult.status===0){
 try{
  const rows=JSON.parse(stateResult.stdout)?.[0]?.results||[];
  state=Object.fromEntries(rows.map(row=>[row.key,row.value]));
 }catch{ /* A missing/uninitialized database takes the full-sync path. */ }
}
const source=/^(?:[\w.-]+\/[\w.-]+|https:\/\/[^\s]+)$/.test(state.source_repo||'')
 ? state.source_repo:null;
const checkArgs=['scripts/export_catalogue.py','--check-only'];
if(source)checkArgs.push('--source-repo',source);
const check=run(python,checkArgs,{quiet:true});
const upstream=JSON.parse(check.stdout);
if(upstream.generation===state.active_generation){
 console.log('Catalogue unchanged at '+upstream.generation+'; skipped download, export and D1 writes');
 process.exit(0);
}
console.log('Catalogue changed: '+(state.active_generation||'none')+' -> '+upstream.generation);
const exportArgs=['scripts/export_catalogue.py','--output','.data/import'];
if(source)exportArgs.push('--source-repo',source);
run(python,exportArgs);
run(process.execPath,['scripts/import_d1.mjs']);
