import {parseId,preview,mediaId} from './protocol.js';
async function active(db){
 return (await db.prepare("SELECT value FROM catalogue_state WHERE key='active_generation'").first())?.value||'';
}
export async function getCatalog(db,type,id,extra) {
 if(!((type==='movie'&&id==='mirantir-movies')||(type==='series'&&id==='mirantir-series')))
  return {metas:[]};
 const generation=await active(db);if(!generation)return {metas:[]};
 let sql='SELECT * FROM catalogue_items WHERE generation=? AND kind=?';
 const params=[generation,type];
 if(extra.search) {
  sql+=" AND title LIKE ? ESCAPE '\\'";
  params.push('%'+extra.search.replace(/[\\%_]/g,'\\$&')+'%');
 }
 sql+=' ORDER BY updated DESC,tmdb DESC LIMIT 60 OFFSET ?';
 params.push(extra.skip);
 const {results}=await db.prepare(sql).bind(...params).all();
 return {metas:(results||[]).map(preview)};
}
export async function getMeta(db,type,id){
 const key=parseId(id,type);if(!key||key.season!==null)return {meta:null};
 const gen=await active(db);if(!gen)return {meta:null};
 const row=await db.prepare('SELECT * FROM catalogue_items WHERE generation=? AND kind=? AND tmdb=?')
  .bind(gen,type,key.tmdb).first();
 if(!row)return {meta:null};
 const meta=preview(row);
 if(type==='series'){
  const {results}=await db.prepare('SELECT season,episode FROM catalogue_episodes WHERE generation=? AND tmdb=? ORDER BY season,episode LIMIT 1500')
   .bind(gen,key.tmdb).all();
  meta.videos=(results||[]).map(e=>({id:mediaId('series',key.tmdb)+':'+e.season+':'+e.episode,
   title:'Season '+e.season+', Episode '+e.episode,season:e.season,episode:e.episode}));
 }
 return {meta};
}
export async function getLinks(db,type,id){
 const key=parseId(id,type);
 if(!key||(type==='series'&&key.season===null))return [];
 const gen=await active(db);if(!gen)return [];
 const {results}=await db.prepare('SELECT quality,audio,info,hoster_url FROM catalogue_links WHERE generation=? AND kind=? AND tmdb=? AND season=? AND episode=? ORDER BY position LIMIT 12')
  .bind(gen,type,key.tmdb,key.season??0,key.episode??0).all();
 return results||[];
}
