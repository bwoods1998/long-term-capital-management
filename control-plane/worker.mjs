import {DurableObject} from 'cloudflare:workers';
import {timingSafeEqual} from 'node:crypto';
import {Supervisor,boundedText} from './supervisor.mjs';
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
function authorized(request,token) { if (typeof token!=='string'||token.length<32)return false;
 const a=Buffer.from(request.headers.get('Authorization')||''),b=Buffer.from('Bearer '+token);return a.length===b.length&&timingSafeEqual(a,b); }
export class PortfolioSupervisor extends DurableObject {
 constructor(ctx,env){super(ctx,env);this.controller=new Supervisor(ctx.storage,env);}
 async alarm(){await this.controller.tick();}
 async fetch(request){try{
  const u=new URL(request.url),path=u.pathname;
  if(path==='/v1/status'&&request.method==='GET')return json(await this.controller.status());
  if(path==='/v1/tick'&&request.method==='POST')return json(await this.controller.tick());
  if(path==='/v1/configure'&&request.method==='POST')return json(await this.controller.configure(JSON.parse(await boundedText(request,16000))));
  if(['/v1/pause','/v1/resume'].includes(path)&&request.method==='POST')return json(await this.controller.pause(path.endsWith('/pause')));
  return json({error:'not_found'},404);
 }catch{return json({error:'operation_failed'},409);}}
}
export default {
 async scheduled(controller,env){await env.SUPERVISOR.get(env.SUPERVISOR.idFromName('weekday-v1')).fetch('https://control/v1/tick',{method:'POST'});},
 async fetch(request,env){
  const url=new URL(request.url);
  if(url.search)return json({error:'not_found'},404);
  if(url.pathname.startsWith('/v1/backups/')) {
   if(!authorized(request,request.method==='PUT'?env.BACKUP_TOKEN:env.ADMIN_TOKEN))return json({error:'unauthorized'},401);
   const key=url.pathname.slice('/v1/backups/'.length);
   if(!/^[a-z0-9-]{8,64}\/[a-z0-9-]{8,80}\/[a-f0-9]{64}\.(?:gz|json)$/.test(key))return json({error:'invalid_key'},400);
   if(request.method==='PUT'){
    const hash=request.headers.get('X-Content-SHA256'),size=Number(request.headers.get('Content-Length'));
    if(!/^[a-f0-9]{64}$/.test(hash||'')||!key.endsWith(hash+'.gz')&&!key.endsWith(hash+'.json')||!Number.isSafeInteger(size)||size<1||size>64*1024*1024)return json({error:'invalid_artifact'},400);
    try{
     const existing=await env.BACKUPS.head(key);
     if(existing)return existing.size===size&&existing.customMetadata?.sha256===hash?json({stored:true,replayed:true}):json({error:'immutable_artifact'},409);
     await env.BACKUPS.put(key,request.body,{sha256:hash,httpMetadata:{contentType:key.endsWith('.gz')?'application/gzip':'application/json'},customMetadata:{sha256:hash}});
     return json({stored:true});
    }catch{return json({error:'backup_failed'},503);}
   }
   if(request.method==='GET'||request.method==='HEAD'){
    const object=request.method==='HEAD'?await env.BACKUPS.head(key):await env.BACKUPS.get(key);
    if(!object)return json({error:'not_found'},404);
    return new Response(request.method==='HEAD'?null:object.body,{headers:{'Content-Type':object.httpMetadata?.contentType||'application/octet-stream','Content-Length':String(object.size),'X-Content-SHA256':object.customMetadata?.sha256||'','Cache-Control':'no-store'}});
   }
   return json({error:'method_not_allowed'},405);
  }
  if(!authorized(request,env.ADMIN_TOKEN))return json({error:'unauthorized'},401);
  return env.SUPERVISOR.get(env.SUPERVISOR.idFromName('weekday-v1')).fetch(request);
 }
};
