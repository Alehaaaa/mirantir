import {MANIFEST,extras} from './protocol.js';
import {getCatalog,getMeta} from './catalogue.js';
import {getStreams} from './streams.js';
import {seal,unseal} from './security.js';

const HEADERS={
 'Access-Control-Allow-Origin':'*',
 'Access-Control-Allow-Methods':'GET,POST,OPTIONS',
 'Access-Control-Allow-Headers':'Content-Type',
 'Referrer-Policy':'no-referrer',
 'X-Content-Type-Options':'nosniff'
};
function json(data,status=200,privateData=false){
 return new Response(JSON.stringify(data),{status,headers:{...HEADERS,
  'Content-Type':'application/json; charset=utf-8',
  'Cache-Control':privateData?'no-store':'public, max-age=120'}});
}
function html(content,status=200){
 return new Response(content,{status,headers:{...HEADERS,
  'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store',
  'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"}});
}
function page(content){
 return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'+
 '<title>Mirantir Stremio</title><style>body{font:16px system-ui;background:#10141c;color:white;max-width:600px;margin:8vh auto;padding:20px}a{color:#8ac6ff}form{padding:20px;background:#1b2432;border-radius:12px}input,select,button{display:block;width:100%;padding:12px;margin:8px 0 20px;box-sizing:border-box}button{cursor:pointer}code{overflow-wrap:anywhere}small{color:#b4c3d5}</style>'+
 '<h1>Mirantir for Stremio</h1>'+content+'</html>';
}
const escapeHtml=text=>String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function configurePage(){
 return page('<p>Install the Mirantir movie and series catalogue. Streams require your own authorized debrid account.</p>'+
 '<form method="post" action="/configure"><label>Provider<select name="provider"><option value="none">Catalogue only</option>'+
 '<option value="rd">Real-Debrid</option><option value="ad">AllDebrid</option></select></label>'+
 '<label>Personal API key<input name="apiKey" type="password" maxlength="512" autocomplete="off"></label>'+
 '<label><input type="checkbox" name="hide4k" style="width:auto;display:inline"> Hide 4K</label>'+
 '<label><input type="checkbox" name="hideDv" style="width:auto;display:inline"> Hide Dolby Vision</label>'+
 '<button>Generate Stremio installation link</button></form><p><small>Your token is encrypted and the installation URL is a bearer secret. Do not share it.</small></p>');
}
async function configure(request,env){
 if(Number(request.headers.get('content-length')||0)>4096)
  return json({error:'Configuration too large'},413,true);
 const form=new URLSearchParams((await request.text()).slice(0,4096));
 const provider=form.get('provider')||'none';
 const apiKey=(form.get('apiKey')||'').trim();
 if(!['none','rd','ad'].includes(provider)||apiKey.length>512||(provider!=='none'&&!apiKey))
  return html(page('<p>Invalid provider or missing API key.</p><a href="/configure">Back</a>'),400);
 let url=new URL(request.url).origin+'/manifest.json';
 if(provider!=='none'){
  if(!env.CONFIG_KEY||env.CONFIG_KEY.length<32)
   return html(page('<p>Configure the Cloudflare CONFIG_KEY secret first.</p>'),503);
  const token=await seal({provider,apiKey,hide4k:form.has('hide4k'),hideDv:form.has('hideDv')},env.CONFIG_KEY);
  url=new URL(request.url).origin+'/c/'+token+'/manifest.json';
 }
 const stremio=url.replace(/^https?:\/\//,'stremio://');
 return html(page('<h2>Stremio configuration ready</h2><p><a href="'+escapeHtml(stremio)+'">Install in Stremio</a></p>'+
  '<p>Or paste the manifest URL:</p><p><code>'+escapeHtml(url)+'</code></p>'+
  '<p><small>Keep this link private if it contains your account settings.</small></p>'));
}
export default {
 async fetch(request,env){
  if(request.method==='OPTIONS')return new Response(null,{status:204,headers:HEADERS});
  try{
   const url=new URL(request.url);
   const parts=url.pathname.split('/').filter(Boolean);
   if(request.method==='GET'&&!parts.length)
    return html(page('<p>Cloudflare-hosted Stremio addon.</p><a href="/configure">Configure and install</a> · <a href="/manifest.json">Manifest</a>'));
   if(parts.length===1&&parts[0]==='configure'){
    if(request.method==='GET')return html(configurePage());
    if(request.method==='POST')return configure(request,env);
   }
   if(request.method!=='GET')return json({error:'Method not allowed'},405);
   if(parts.length===1&&parts[0]==='health'){
    if(!env.DB)return json({ok:true,catalogueReady:false,version:MANIFEST.version},200,true);
    const ready=!!(await env.DB.prepare("SELECT value FROM catalogue_state WHERE key='active_generation'").first())?.value;
    return json({ok:true,catalogueReady:ready,version:MANIFEST.version},200,true);
   }
   let configured=false,profile=null;
   if(parts[0]==='c'&&parts.length>=3){
    configured=true;
    profile=await unseal(parts[1],env.CONFIG_KEY);
    if(!profile)return json({error:'Invalid configuration'},401,true);
    parts.splice(0,2);
   }
   if(parts.length===1&&parts[0]==='manifest.json')return json(MANIFEST,200,configured);
   if(!env.DB)return json({error:'D1 catalogue binding unavailable'},503,configured);
   if(parts.length<3)return json({error:'Not found'},404,configured);
   const [resource,type]=parts;
   if(!['movie','series'].includes(type)||!['catalog','meta','stream'].includes(resource))
    return json({error:'Not found'},404,configured);
   const last=parts.at(-1);
   if(!last.endsWith('.json'))return json({error:'Not found'},404,configured);
   if(resource==='catalog'&&(parts.length===3||parts.length===4)){
    const id=parts[2].replace(/\.json$/,'');
    const extra=parts.length===4?last.slice(0,-5):'';
    return json(await getCatalog(env.DB,type,id,extras(extra,url.searchParams)),200,configured);
   }
   if(parts.length!==3)return json({error:'Not found'},404,configured);
   const id=decodeURIComponent(last.slice(0,-5));
   if(resource==='meta')return json(await getMeta(env.DB,type,id),200,configured);
   if(resource==='stream')return json(await getStreams(env.DB,type,id,profile),200,true);
   return json({error:'Not found'},404,configured);
  }catch{
   // Do not log configured URLs, provider keys or debrid responses.
   return json({error:'Internal server error'},500,true);
  }
 }
};
