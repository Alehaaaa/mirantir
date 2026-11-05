import {getLinks} from './catalogue.js';
import {mediaId} from './protocol.js';
function allowed(link,config){
 const quality=(link.quality||'')+' '+(link.info||'');
 return !(config.hide4k&&/\b(?:4k|2160p|uhd)\b/i.test(quality)) &&
  !(config.hideDv&&/\b(?:dolby[ .-]?vision|dv)\b/i.test(quality));
}
async function unlock(link,config){
 let response;
 if(config.provider==='rd'){
  response=await fetch('https://api.real-debrid.com/rest/1.0/unrestrict/link',{
   method:'POST',headers:{Authorization:'Bearer '+config.apiKey,'Content-Type':'application/x-www-form-urlencoded'},
   body:new URLSearchParams({link}),signal:AbortSignal.timeout(12000)});
 }else{
  response=await fetch('https://api.alldebrid.com/v4/link/unlock',{
   method:'POST',headers:{Authorization:'Bearer '+config.apiKey,
    'Content-Type':'application/x-www-form-urlencoded'},
   body:new URLSearchParams({link}),signal:AbortSignal.timeout(12000)});
 }
 if(!response.ok)return null;
 const data=await response.json();
 const target=config.provider==='rd'?data.download:(data.status==='success'?data.data?.link:null);
 return typeof target==='string'&&/^https?:\/\//i.test(target)?target:null;
}
async function resolveId(type,id){
 if(id?.startsWith('mirantir:'))return id;
 const match=/^(tt\d{5,12})(?::(\d{1,4}):(\d{1,4}))?$/.exec(id||'');
 if(!match||(type==='movie'&&match[2]!==undefined))return null;
 try{
  const response=await fetch('https://v3-cinemeta.strem.io/meta/'+type+'/'+match[1]+'.json',{
   headers:{Accept:'application/json'},signal:AbortSignal.timeout(6000)});
  if(!response.ok)return null;
  const data=await response.json();
  const tmdb=Number(data.meta?.moviedb_id);
  if(!Number.isSafeInteger(tmdb)||tmdb<1)return null;
  return mediaId(type,tmdb)+(match[2]===undefined?'':':'+Number(match[2])+':'+Number(match[3]));
 }catch{return null;}
}
export async function getStreams(db,type,id,config){
 if(!config?.apiKey)return {streams:[]};
 const resolved=await resolveId(type,id);
 if(!resolved)return {streams:[]};
 const entries=(await getLinks(db,type,resolved)).filter(x=>allowed(x,config)).slice(0,5);
 const streams=[];
 for(const e of entries){
  try{
   const url=await unlock(e.hoster_url,config);
   if(url)streams.push({name:'Mirantir '+config.provider.toUpperCase(),
    title:[e.quality,e.audio,e.info].filter(Boolean).join(' • ').slice(0,180),url});
  }catch{ /* A failed hoster should not break other sources. */ }
 }
 return {streams};
}
