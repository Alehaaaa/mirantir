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
async function cachedPublic(request,ctx,pathname,load){
 const cache=globalThis.caches?.default;
 if(!cache)return load();
 const key=new URL(request.url);key.pathname=pathname;
 let hit;
 try{hit=await cache.match(key.toString())}catch{return load()}
 if(hit)return hit;
 const response=await load();
 if(response.ok){
  const stored=new Response(response.body,response);
  stored.headers.set('Cache-Control','public, max-age=120, s-maxage=600');
  ctx?.waitUntil(cache.put(key.toString(),stored.clone()));
  return stored;
 }
 return response;
}
function html(content,status=200,nonce=''){
 return new Response(content,{status,headers:{...HEADERS,
  'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store',
  'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-"+nonce+
   "'; form-action 'self'; base-uri 'none'"}});
}
function page(content){
 return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'+
 '<meta name="theme-color" content="#12101d"><title>Mirantir for Stremio</title><style>'+
 ':root{color-scheme:dark;--bg:#0d0b15;--card:#191625;--card2:#211d30;--text:#f7f5ff;--muted:#aaa4bc;--purple:#7b5cff;--purple2:#9b7cff;--line:#312b45;--green:#53d6a6}*{box-sizing:border-box}body{margin:0;min-height:100vh;font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--text);background:radial-gradient(circle at 50% -15%,#302259 0,transparent 42%),linear-gradient(160deg,#0d0b15 0,#12101d 70%,#181128 100%);padding:48px 20px}main{width:min(680px,100%);margin:auto}.brand{display:flex;align-items:center;justify-content:center;gap:13px;margin-bottom:26px}.mark{display:grid;place-items:center;width:48px;height:48px;border-radius:15px;background:linear-gradient(145deg,var(--purple2),#5638dd);box-shadow:0 12px 35px #6e4cff55;font-size:24px}.brand strong{font-size:25px;letter-spacing:-.6px}.brand span{display:block;color:var(--muted);font-size:13px}.card{padding:30px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(145deg,#1c1829ee,#15121fee);box-shadow:0 24px 80px #0008;backdrop-filter:blur(14px)}h1,h2{margin:0 0 8px;letter-spacing:-.7px}h1{font-size:29px}h2{font-size:24px}.lead{color:var(--muted);margin:0 0 27px}.section{border-top:1px solid var(--line);padding-top:22px;margin-top:22px}.label,label>span{display:block;font-weight:650;margin-bottom:8px}input,select,button,.button{width:100%;min-height:48px;border:1px solid var(--line);border-radius:12px;background:#100e19;color:var(--text);padding:12px 14px;font:inherit;outline:none;transition:.18s ease}input:focus,select:focus{border-color:var(--purple2);box-shadow:0 0 0 3px #7b5cff26}select{appearance:none;background-image:linear-gradient(45deg,transparent 50%,#aaa4bc 50%),linear-gradient(135deg,#aaa4bc 50%,transparent 50%);background-position:calc(100% - 19px) 21px,calc(100% - 14px) 21px;background-size:5px 5px;background-repeat:no-repeat}.field{margin-bottom:19px}.api-help{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:-7px 0 20px;padding:12px 14px;border-radius:12px;background:#29213f;color:#dcd3ff}.api-help[hidden]{display:none}.api-help a{color:#bcaaff;font-weight:700;text-decoration:none;white-space:nowrap}.checks{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0 24px}.check{display:flex;align-items:center;gap:10px;padding:12px;border:1px solid var(--line);border-radius:12px;background:#12101b;cursor:pointer}.check input{width:18px;min-height:18px;margin:0;accent-color:var(--purple)}.check span{margin:0;font-weight:550}.button,button{display:inline-flex;align-items:center;justify-content:center;gap:9px;cursor:pointer;text-decoration:none;font-weight:750}.primary{border:0;background:linear-gradient(135deg,var(--purple2),#6041e8);box-shadow:0 10px 28px #7050ec3d}.primary:hover{filter:brightness(1.09);transform:translateY(-1px)}.secondary:hover{border-color:#6f5a9e;background:#181424}.actions{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:22px}.manifest{display:flex;align-items:center;min-height:50px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:#0e0c16;color:#bbb4ce;overflow:hidden}.manifest code{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}.notice{color:var(--muted);font-size:13px;margin:18px 0 0}.ready{display:inline-flex;align-items:center;gap:8px;color:var(--green);font-weight:700;margin-bottom:10px}.dot{width:8px;height:8px;border-radius:50%;background:currentColor;box-shadow:0 0 14px currentColor}.back{display:inline-block;color:#bcaaff;margin-top:22px;text-decoration:none}@media(max-width:540px){body{padding:24px 14px}.card{padding:22px}.checks,.actions{grid-template-columns:1fr}.brand{justify-content:flex-start}}</style>'+
 '<main><header class="brand"><div class="mark" aria-hidden="true">▶</div><div><strong>Mirantir</strong><span>for Stremio</span></div></header><section class="card">'+content+'</section></main></html>';
}
const escapeHtml=text=>String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const makeNonce=()=>crypto.randomUUID().replaceAll('-','');
function configurePage(nonce,profile=null,action='/configure'){
 const provider=profile?.provider||'none';
 const selected=value=>provider===value?' selected':'';
 const checked=value=>value?' checked':'';
 return page('<h1>Configure your addon</h1><p class="lead">Discover the Mirantir movie and series catalogue, then stream with your own debrid account.</p>'+
 '<form method="post" action="'+escapeHtml(action)+'"><div class="field"><label><span>Debrid provider</span><select id="provider" name="provider">'+
 '<option value="none"'+selected('none')+'>Catalogue only</option><option value="rd"'+selected('rd')+'>Real-Debrid</option><option value="ad"'+selected('ad')+'>AllDebrid</option></select></label></div>'+
 '<div id="apiHelp" class="api-help" hidden><span id="apiHint">Get the API key from your provider.</span><a id="apiLink" href="#" target="_blank" rel="noreferrer">Open API page ↗</a></div>'+
 '<div class="field"><label><span>Personal API key</span><input name="apiKey" type="password" maxlength="512" autocomplete="off" placeholder="'+(profile?'Current key retained if left blank':'Paste your private API key')+'"></label></div>'+
 '<div class="section"><span class="label">Stream filters</span><div class="checks">'+
 '<label class="check"><input type="checkbox" name="hide4k"'+checked(profile?.hide4k)+'><span>Hide 4K</span></label>'+
 '<label class="check"><input type="checkbox" name="hideDv"'+checked(profile?.hideDv)+'><span>Hide Dolby Vision</span></label></div></div>'+
 '<button class="primary" type="submit">Generate installation link <span aria-hidden="true">→</span></button></form>'+
 '<p class="notice">'+(profile?'Your current API key remains encrypted and is never displayed. Leave the field blank to keep it.':'Your API key is encrypted into the installation URL. Treat that URL like a password and never share it.')+'</p>'+
 '<script nonce="'+nonce+'">const p=document.querySelector("#provider"),h=document.querySelector("#apiHelp"),t=document.querySelector("#apiHint"),a=document.querySelector("#apiLink");const providers={rd:{name:"Real-Debrid",url:"https://real-debrid.com/apitoken"},ad:{name:"AllDebrid",url:"https://alldebrid.com/apikeys/"}};function update(){const v=providers[p.value];h.hidden=!v;if(v){t.textContent="Open "+v.name+" to copy your API key.";a.href=v.url}}p.addEventListener("change",update);update()</script>');
}
async function configure(request,env,currentProfile=null){
 if(Number(request.headers.get('content-length')||0)>4096)
  return json({error:'Configuration too large'},413,true);
 const form=new URLSearchParams((await request.text()).slice(0,4096));
 const provider=form.get('provider')||'none';
 const enteredKey=(form.get('apiKey')||'').trim();
 const apiKey=enteredKey||(currentProfile?.provider===provider?currentProfile.apiKey:'');
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
 const nonce=makeNonce();
 return html(page('<div class="ready"><span class="dot"></span>Configuration ready</div><h2>Add Mirantir to Stremio</h2>'+
  '<p class="lead">Open Stremio directly or copy the manifest link to install it on another device.</p>'+
  '<span class="label">Manifest URL</span><div class="manifest"><code id="manifestUrl">'+escapeHtml(url)+'</code></div>'+
  '<div class="actions"><a class="button primary" href="'+escapeHtml(stremio)+'">Open Stremio <span aria-hidden="true">↗</span></a>'+
  '<button id="copyLink" class="secondary" type="button">Copy link</button></div>'+
  '<p class="notice">Keep this link private if it contains your account settings.</p><a class="back" href="/configure">← Change configuration</a>'+
  '<script nonce="'+nonce+'">const b=document.querySelector("#copyLink"),u=document.querySelector("#manifestUrl").textContent;b.addEventListener("click",async()=>{try{await navigator.clipboard.writeText(u);b.textContent="Copied ✓"}catch{const r=document.createRange();r.selectNodeContents(document.querySelector("#manifestUrl"));getSelection().removeAllRanges();getSelection().addRange(r);b.textContent="Select and copy"}setTimeout(()=>b.textContent="Copy link",1800)})</script>'),200,nonce);
}
export default {
 async fetch(request,env,ctx){
  if(request.method==='OPTIONS')return new Response(null,{status:204,headers:HEADERS});
  try{
   const url=new URL(request.url);
   const parts=url.pathname.split('/').filter(Boolean);
   if(request.method==='GET'&&!parts.length)
    return html(page('<p>Cloudflare-hosted Stremio addon.</p><a href="/configure">Configure and install</a> · <a href="/manifest.json">Manifest</a>'));
   if(parts.length===1&&parts[0]==='configure'){
    if(request.method==='GET'){
     const nonce=makeNonce();return html(configurePage(nonce),200,nonce);
    }
    if(request.method==='POST')return configure(request,env);
   }
   const configuredPost=request.method==='POST'&&parts[0]==='c'&&parts.length===3&&parts[2]==='configure';
   if(request.method!=='GET'&&!configuredPost)return json({error:'Method not allowed'},405);
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
    const configToken=parts[1];
    parts.splice(0,2);
    if(parts.length===1&&parts[0]==='configure'){
     if(request.method==='GET'){
      const nonce=makeNonce();
      return html(configurePage(nonce,profile,'/c/'+configToken+'/configure'),200,nonce);
     }
     if(request.method==='POST')return configure(request,env,profile);
    }
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
    const cachePath='/catalog/'+type+'/'+id+'.json'+(extra?'/'+extra+'.json':'');
    return cachedPublic(request,ctx,cachePath,async()=>
     json(await getCatalog(env.DB,type,id,extras(extra,url.searchParams)),200,false));
   }
   if(parts.length!==3)return json({error:'Not found'},404,configured);
   const id=decodeURIComponent(last.slice(0,-5));
   if(resource==='meta')return cachedPublic(request,ctx,
    '/meta/'+type+'/'+encodeURIComponent(id)+'.json',async()=>
     json(await getMeta(env.DB,type,id),200,false));
   if(resource==='stream')return json(await getStreams(env.DB,type,id,profile),200,true);
   return json({error:'Not found'},404,configured);
  }catch{
   // Do not log configured URLs, provider keys or debrid responses.
   return json({error:'Internal server error'},500,true);
  }
 }
};
