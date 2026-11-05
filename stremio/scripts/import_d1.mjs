import {readFile,readdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
const folder=resolve(process.env.CATALOGUE_EXPORT_DIR||'.data/import');
const manifest=JSON.parse(await readFile(folder+'/manifest.json','utf8'));
if(!/^[a-f0-9]{24}$/.test(manifest.generation)||!manifest.counts.catalogue_items)
 throw new Error('Missing or invalid export generation');
const files=(await readdir(folder)).filter(x=>/^\d{4}-(reset|data|activate)\.sql$/.test(x)).sort();
if(files[0]!=='0000-reset.sql'||files.at(-1)!=='9999-activate.sql'||files.length<3)
 throw new Error('Incomplete staging export');
if(!process.env.CF_D1_DATABASE_ID&&!process.argv.includes('--local'))
 throw new Error('CF_D1_DATABASE_ID required for remote import');
await import('./config.mjs');
const location=process.argv.includes('--local')?'--local':'--remote';
function run(...args){
 const result=spawnSync(process.platform==='win32'?'npx.cmd':'npx',
  ['wrangler',...args],{encoding:'utf8',maxBuffer:20_000_000,env:process.env});
 if(result.status!==0||result.error)throw new Error('Wrangler D1 operation failed: '+
  ((result.stderr||result.stdout||'').slice(-2000)));
 return result.stdout;
}
run('d1','migrations','apply','mirantir-stremio',location,'--config','wrangler.generated.jsonc');
const state=JSON.parse(run('d1','execute','mirantir-stremio',location,
 '--config','wrangler.generated.jsonc','--json','--command',
 "SELECT value FROM catalogue_state WHERE key='active_generation'"));
if(state?.[0]?.results?.[0]?.value===manifest.generation&&!process.argv.includes('--force')){
 console.log('Catalogue already up-to-date');process.exit(0);
}
for(const file of files){
 console.log('Uploading '+file);
 run('d1','execute','mirantir-stremio',location,'--config','wrangler.generated.jsonc',
  '--file',folder+'/'+file);
}
console.log('Activated '+manifest.generation);
