import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.js';
import {MANIFEST,parseId} from '../src/protocol.js';
import {seal,unseal} from '../src/security.js';

const secret='test-key-that-has-at-least-32-characters';
const request=(path,options={})=>new Request('https://stremio.example'+path,options);
function db(){
 const queries=[];
 return {queries,prepare(sql){
  const args=[];const stmt={
   bind(...v){args.push(...v);return stmt;},
   async first(){
    queries.push({sql,args});
    if(sql.includes('catalogue_state'))return {value:'gen1'};
    return {kind:'movie',tmdb:123,title:'Example',poster:'/poster.jpg',genres:'Action#Comedy'};
   },
   async all(){
    queries.push({sql,args});
    if(sql.includes('catalogue_links'))return {results:[{quality:'1080p',audio:'EN',hoster_url:'https://example.com/file'}]};
    if(sql.includes('catalogue_episodes'))return {results:[{season:1,episode:2}]};
    return {results:[{kind:'movie',tmdb:123,title:'Example',poster:'/poster.jpg',genres:'Action'}]};
   }
  };return stmt;
 }};
}
test('manifest satisfies Stremio protocol',async()=>{
 const response=await worker.fetch(request('/manifest.json'),{DB:db()});
 assert.equal(response.status,200);
 assert.equal(response.headers.get('Access-Control-Allow-Origin'),'*');
 const data=await response.json();
 assert.equal(data.id,MANIFEST.id);
 assert.deepEqual(data.types,['movie','series']);
 assert.equal(data.catalogs.length,2);
});
test('config credentials are encrypted and never printed',async()=>{
 const form=new URLSearchParams({provider:'rd',apiKey:'secret-real-debrid-key'});
 const response=await worker.fetch(request('/configure',{method:'POST',body:form}),{DB:db(),CONFIG_KEY:secret});
 assert.equal(response.status,200);
 const html=await response.text();
 assert(!html.includes('secret-real-debrid-key'));
 assert.match(html,/href="stremio:\/\/stremio\.example\/c\//);
 assert.match(html,/>Open Stremio </);
 assert.match(html,/>Copy link</);
 assert.match(html,/id="manifestUrl"/);
 const nonce=html.match(/<script nonce="([a-f0-9]+)">/)[1];
 assert(response.headers.get('Content-Security-Policy').includes("script-src 'nonce-"+nonce+"'"));
 const token=html.match(/\/c\/([\w-]+)\/manifest\.json/)[1];
 assert.equal((await unseal(token,secret)).apiKey,'secret-real-debrid-key');
 const configured=await worker.fetch(request('/c/'+token+'/manifest.json'),{DB:db(),CONFIG_KEY:secret});
 assert.equal(configured.status,200);
 assert.equal(configured.headers.get('Cache-Control'),'no-store');
 assert.equal((await worker.fetch(request('/c/invalid/manifest.json'),{DB:db(),CONFIG_KEY:secret})).status,401);
});
test('configuration page links to the selected provider API pages',async()=>{
 const response=await worker.fetch(request('/configure'),{DB:db(),CONFIG_KEY:secret});
 assert.equal(response.status,200);
 const html=await response.text();
 assert.match(html,/https:\/\/real-debrid\.com\/apitoken/);
 assert.match(html,/https:\/\/alldebrid\.com\/apikeys\//);
 assert.match(html,/Open API page/);
 assert.match(html,/Generate installation link/);
 assert.match(html,/@media\(max-width:540px\)/);
});
test('movies and search use local D1 SQL and parameter binding',async()=>{
 const database=db();
 const response=await worker.fetch(request('/catalog/movie/mirantir-movies/search=Alien%26skip=40.json'),{DB:database});
 assert.equal(response.status,200);
 const result=await response.json();
 assert.equal(result.metas[0].id,'mirantir:movie:123');
 assert.deepEqual(database.queries.find(x=>x.sql.includes('LIKE')).args,['gen1','movie','%Alien%',40]);
});
test('meta, series IDs and empty unconfigured streams',async()=>{
 const database=db();
 assert.deepEqual(parseId('mirantir:series:456:1:2','series'),
  {kind:'series',tmdb:456,season:1,episode:2});
 const meta=await worker.fetch(request('/meta/movie/mirantir:movie:123.json'),{DB:database});
 assert.equal((await meta.json()).meta.name,'Example');
 const streams=await worker.fetch(request('/stream/movie/mirantir:movie:123.json'),{DB:database});
 assert.deepEqual(await streams.json(),{streams:[]});
});
test('configured debrid calls provider without exposing token in provider URL',async()=>{
 const token=await seal({provider:'rd',apiKey:'rd-test-token'},secret);
 const old=globalThis.fetch;let headers;
 globalThis.fetch=async(url,opts)=>{
  assert(!url.includes('rd-test-token'));
  headers=opts.headers;
  return Response.json({download:'https://cdn.example.com/video.mkv'});
 };
 try{
  const response=await worker.fetch(request('/c/'+token+'/stream/movie/mirantir:movie:123.json'),
   {DB:db(),CONFIG_KEY:secret});
  const streams=await response.json();
  assert.equal(streams.streams[0].url,'https://cdn.example.com/video.mkv');
  assert.equal(headers.Authorization,'Bearer rd-test-token');
 }finally{globalThis.fetch=old;}
});
