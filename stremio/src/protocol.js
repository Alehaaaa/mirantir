export const MANIFEST = {
 id:'com.mirantir.stremio', version:'0.1.0', name:'Mirantir',
 description:'Movies and series from the Mirantir catalogue.',
 types:['movie','series'],
 catalogs:[
  {type:'movie',id:'mirantir-movies',name:'Mirantir • Movies',extra:[{name:'search',isRequired:false},{name:'skip',isRequired:false}]},
  {type:'series',id:'mirantir-series',name:'Mirantir • Series',extra:[{name:'search',isRequired:false},{name:'skip',isRequired:false}]}
 ],
 resources:['catalog',{name:'meta',types:['movie','series'],idPrefixes:['mirantir:']},
  {name:'stream',types:['movie','series'],idPrefixes:['mirantir:']}],
 behaviorHints:{configurable:true,configurationRequired:false}
};
export const mediaId = (kind,id) => 'mirantir:'+kind+':'+id;
export const image = (path,size='w500') => !path ? undefined :
  /^https?:\/\//.test(path) ? path : 'https://image.tmdb.org/t/p/'+size+path;
export function preview(row) {
 const result={id:mediaId(row.kind,row.tmdb),type:row.kind,name:row.title,
  poster:image(row.poster),background:image(row.background,'w1280'),
  description:row.plot||undefined,
  genres:(row.genres||'').split('#').map(x=>x.trim()).filter(Boolean)};
 if (row.release_date && /^\d{4}/.test(row.release_date))
  result.releaseInfo=row.release_date.slice(0,4);
 return result;
}
export function parseId(id,type) {
 const m=/^mirantir:(movie|series):(\d{1,12})(?::(\d{1,4}):(\d{1,4}))?$/.exec(id||'');
 if(!m||m[1]!==type||(type==='movie'&&m[3]!==undefined))return null;
 return {kind:type,tmdb:Number(m[2]),season:m[3]===undefined?null:Number(m[3]),
  episode:m[4]===undefined?null:Number(m[4])};
}
export function extras(fragment,query) {
 const params=new URLSearchParams(query);
 if(fragment) for(const [k,v] of new URLSearchParams(decodeURIComponent(fragment)))params.set(k,v);
 const skip=Math.min(10000,Math.max(0,Number.parseInt(params.get('skip')||'0',10)||0));
 return {skip,search:(params.get('search')||'').trim().slice(0,100)};
}
