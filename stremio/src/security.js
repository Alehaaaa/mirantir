const encoder=new TextEncoder(),decoder=new TextDecoder();
const b64=bytes=>btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const bytes=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));
async function key(secret){
 if(!secret||secret.length<32)throw new Error('CONFIG_KEY must be at least 32 characters');
 const digest=await crypto.subtle.digest('SHA-256',encoder.encode(secret));
 return crypto.subtle.importKey('raw',digest,'AES-GCM',false,['encrypt','decrypt']);
}
export async function seal(config,secret){
 const iv=crypto.getRandomValues(new Uint8Array(12));
 const value=encoder.encode(JSON.stringify({v:1,...config}));
 const cipher=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv},await key(secret),value));
 return b64(new Uint8Array([...iv,...cipher]));
}
export async function unseal(token,secret){
 if(!/^[\w-]{35,1500}$/.test(token||''))return null;
 try{
  const value=bytes(token);
  const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:value.slice(0,12)},await key(secret),value.slice(12));
  const config=JSON.parse(decoder.decode(plain));
  return config?.v===1&&['rd','ad'].includes(config.provider)&&typeof config.apiKey==='string'&&config.apiKey.length<=512 ? config:null;
 }catch{return null;}
}
