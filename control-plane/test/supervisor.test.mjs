import test from 'node:test';
import assert from 'node:assert/strict';
import {Supervisor,creditDecision,validateConfig,parseExec,boundedText} from '../supervisor.mjs';
const start=Date.parse('2026-09-14T04:00:00Z');
const config=()=>({schema_version:1,service_id:'week-20260914',box_id:'sb_00000000-0000-0000-0000-000000000001',manifest_sha256:'a'.repeat(64),starts_at:new Date(start).toISOString(),ends_at:'2026-09-19T04:00:00Z',weekly_total_usd:'100',weekly_inference_usd:'92.5',cloud_budget_usd:'7.5',credit_floor_usd:'2'});
class Storage{
 constructor(){this.data=new Map();this.alarm=null;}
 async get(k){return structuredClone(this.data.get(k));}
 async put(k,v){this.data.set(k,structuredClone(v));}
 async list({prefix}){return new Map([...this.data].filter(([k])=>k.startsWith(prefix)));}
 async setAlarm(t){this.alarm=t;}
 async deleteAlarm(){this.alarm=null;}
}
const billing={balance:12000,balance_unavailable:false,has_metronome_customer:true,avg_cost_per_day:1000};
test('billing units, pending reservations, unknown balance, and actionable runway',()=>{
 const h={inference:{known_cost_usd:'5',committed_usd:'15'}};
 let d=creditDecision(billing,config(),h,start);assert.equal(d.balance_usd,120);assert.equal(d.usable_usd,77.5);assert.equal(d.allow,true);
 d=creditDecision({...billing,balance:1100},config(),h,start);assert.equal(d.allow,false);assert.equal(d.reason,'credit_low');
 assert.equal(creditDecision({...billing,balance_unavailable:true},config(),h,start).allow,false);
 assert.equal(creditDecision({...billing,balance:-1},config(),h,start).allow,false);
});
test('config rejects external authority, bad windows, and overallocated budgets',()=>{
 assert.equal(validateConfig(config()).service_id,config().service_id);
 for(const change of [{command:'anything'},{weekly_total_usd:'10'},{ends_at:'2027-01-01T00:00:00Z'},{box_id:'../../oops'},{weekly_total_usd:'NaN'}])assert.throws(()=>validateConfig({...config(),...change}));
});
test('bounded transport and explicit terminal exec receipts',async()=>{
 assert.deepEqual(parseExec('{"type":"started","exec_request_id":"one"}\n{"type":"stdout","data":"e30="}\n{"type":"exit","return_code":0}\n'),{output:'{}',code:0,started:'one'});
 assert.equal(parseExec('{"type":"started","exec_request_id":"one"}\n').code,null);
 await assert.rejects(()=>boundedText(new Response('oversized'),2),/oversized/);
});

test('native fetch is invoked without a controller receiver',async()=>{
 const c=new Supervisor(new Storage(),{}, {fetcher:async function(){assert.equal(this,undefined);return Response.json({ok:true});}});
 assert.deepEqual(await c.json('/v1/test'),{ok:true});
});

test('portable manual redirects never forward the Sail credential',async()=>{
 let calls=0;
 const c=new Supervisor(new Storage(),{SAIL_API_KEY:'test-key'},{fetcher:async(url,options)=>{calls++;assert.equal(options.redirect,'manual');return new Response(null,{status:302,headers:{Location:'https://untrusted.invalid/'}});}});
 await assert.rejects(()=>c.json('/v1/test'),/provider_http_302/);assert.equal(calls,1);
});
test('immutable enrollment, serialized duplicate ticks, and pending alarm before external I/O',async()=>{
 const s=new Storage();let calls=0;
 const c=new Supervisor(s,{}, {now:()=>start,fetcher:async()=>{calls++;assert.equal(s.alarm,start+60000);throw new Error('network');}});
 await c.configure(config());await assert.rejects(()=>c.configure({...config(),weekly_total_usd:'101'}));
 await Promise.all([c.tick(),c.tick()]);assert.equal(calls,3);assert.equal((await s.get('latest')).status,'needs_attention');assert.equal(s.alarm,start+60000);
});
test('unknown delivery is durable and never retried blindly',async()=>{
 const s=new Storage();let sends=0;const c=new Supervisor(s,{EMAIL:{send:async()=>{sends++;throw Error('unknown');}}},{now:()=>start});
 await c.alert('same','failure',{reason:'network'});await c.alert('same','failure',{reason:'network'});
 assert.equal(sends,1);assert.equal((await s.get('mail:same')).state,'unconfirmed');
});
test('planned sleep checks credit without waking or starting the worker',async()=>{
 const s=new Storage();const urls=[];
 const c=new Supervisor(s,{}, {now:()=>start-3600000,fetcher:async url=>{urls.push(url);return Response.json(billing);}});
 await c.configure(config());await s.put('control',{sleep_until:new Date(start).toISOString(),paused:false,spend_checked_at:start-3600000,compute_used_usd:0});
 await s.put('latest',{health:{inference:{known_cost_usd:'0',committed_usd:'0'}}});
 const r=await c.tick();assert.equal(r.status,'waiting');assert.equal(urls.length,1);assert.match(urls[0],/usage\/summary/);
});
test('live heartbeat does not trigger a restart; admission is written independently',async()=>{
 const s=new Storage(),calls=[];
 const health={status:'running',heartbeat_at:new Date(start).toISOString(),inference:{known_cost_usd:'1',committed_usd:'2'}};
 const probe={manifest_sha256:config().manifest_sha256,boot_id:'b',running:true,health,backup:{running:false,status:'complete',completed_at:new Date(start).toISOString()}};
 const c=new Supervisor(s,{}, {now:()=>start,fetcher:async(url,options)=>{calls.push({url,options});
  if(url.includes('usage/summary'))return Response.json(billing);
  if(url.includes('/spend?'))return Response.json({pricing_configured:true,sailboxes:[{sailbox_id:config().box_id,estimated_total_cost_usd_nanos:1000}]});
  if(url.includes('/files?'))return new Response('{}');
  if(url.endsWith('/exec'))return new Response(JSON.stringify({type:'stdout',data:Buffer.from(JSON.stringify(probe)).toString('base64')})+'\n'+JSON.stringify({type:'exit',return_code:0})+'\n');
  throw Error('unexpected');}});
 await c.configure(config());let r=await c.tick();assert.equal(r.status,'running');assert.equal(calls.length,4);
 const admission=JSON.parse(calls[2].options.body);assert.equal(admission.allow_new_research,true);assert.equal(admission.service_id,config().service_id);
});

function harness({at=start,running=true,balance=billing,compute=0,health={}}={}) {
 const s=new Storage(),calls=[],sent=[];
 const state={at,running,balance,compute,brokenBilling:false,brokenProbe:false,loseBootAck:false,
  health:{status:'running',heartbeat_at:new Date(at).toISOString(),progress_at:new Date(at).toISOString(),progress_timeout_seconds:600,inference:{known_cost_usd:'1',committed_usd:'2',reserved_usd:'5',unsettled_requests:0},...health},
  backup:{running:false,status:'complete',completed_at:new Date(at).toISOString()}};
 const stream=output=>new Response((output===undefined?'':JSON.stringify({type:'stdout',data:Buffer.from(JSON.stringify(output)).toString('base64')})+'\n')+JSON.stringify({type:'exit',return_code:0})+'\n');
 const c=new Supervisor(s,{EMAIL:{async send(message){sent.push(message);return {messageId:'test-message'};}}},{now:()=>state.at,fetcher:async(url,options={})=>{
  calls.push({url,options});
  if(url.includes('/usage/summary')){if(state.brokenBilling)throw Error('billing_network');return Response.json(state.balance);}
  if(url.includes('/spend?'))return Response.json({pricing_configured:true,sailboxes:[{sailbox_id:config().box_id,estimated_total_cost_usd_nanos:state.compute*1e9}]});
  if(url.includes('/files?'))return new Response('{}');
  if(url.endsWith('/sleep'))return Response.json({status:'sleeping'});
  if(url.endsWith('/exec')){
   const body=JSON.parse(options.body);
   if(Array.isArray(body.command)&&body.command.at(-1)==='probe'){
    if(state.brokenProbe)throw Error('probe_network');
    return stream({manifest_sha256:config().manifest_sha256,boot_id:'test-boot',running:state.running,health:state.health,backup:state.backup});
   }
   if(Array.isArray(body.command)&&body.command.at(-1)==='/workspace/host-stop.py')return stream();
   if(Array.isArray(body.command)&&body.command.at(-1)==='force-stop')return stream({stopped:true});
   if(typeof body.command==='string'&&body.command.includes('host-boot')&&state.loseBootAck){state.loseBootAck=false;throw Error('lost_ack');}
   if(body.background)return new Response(JSON.stringify({type:'started',exec_request_id:'test-exec'})+'\n');
  }
  throw Error('unexpected_request');
 }});
 return {c,s,state,calls,sent,advance(ms){state.at+=ms;},commands(){return calls.filter(r=>r.url.endsWith('/exec')).map(r=>JSON.parse(r.options.body));},files(){return calls.filter(r=>r.url.includes('/files?')).map(r=>JSON.parse(r.options.body));}};
}

test('absolute credit grants reserve cloud and active epochs without starving already funded requests',()=>{
 const health={inference:{known_cost_usd:'5',committed_usd:'7',reserved_usd:'10'}};
 const c={...config(),weekly_inference_usd:'90'};
 const d=creditDecision({...billing,balance:1500},c,health,start,3);
 assert.equal(d.max_inference_committed_usd,'15.00000000');
 assert.equal(d.max_additional_inference_usd,'5.00000000');
 assert.equal(d.outstanding_usd,2);
 const funded=creditDecision({...billing,balance:1000},c,health,start,3);
 assert.equal(funded.max_additional_inference_usd,'0.00000000');assert.equal(funded.allow,true);
});

test('funding runway uses research intensity rather than an unused technical ceiling',()=>{
 const c={...config(),weekly_total_usd:'1000',weekly_inference_usd:'992.5'};
 const h={inference:{known_cost_usd:'5',committed_usd:'7'},funding:{planned_inference_usd_per_day:24}};
 const d=creditDecision({...billing,avg_cost_per_day:100},c,h,start,3);
 assert(d.runway_days>4);assert.equal(d.warn,false);
 const intensive=creditDecision({...billing,avg_cost_per_day:100},c,{...h,funding:{planned_inference_usd_per_day:240}},start,3);
 assert(intensive.runway_days<1);assert.equal(intensive.warn,true);
});

test('an exhausted deployment ceiling cannot be repaired by asking for another deposit',()=>{
 const d=creditDecision(billing,config(),{inference:{known_cost_usd:'92.5',committed_usd:'92.5'}},start);
 assert.equal(d.allow,false);assert.equal(d.reason,'authorization_exhausted');
});

test('successful silent host stop is accepted and one low-credit episode sends one message',async()=>{
 const f=harness({balance:{...billing,balance:200}});await f.c.configure(config());
 await f.c.pause(true);await f.c.tick();
 assert(f.commands().some(c=>Array.isArray(c.command)&&c.command.at(-1)==='/workspace/host-stop.py'));
 assert.equal((await f.s.get('latest')).status,'stopping');
 const g=harness({balance:{...billing,balance:200}});await g.c.configure(config());await g.c.tick();g.advance(60000);await g.c.tick();
 assert.equal(g.sent.filter(m=>/funding needed/.test(m.subject)).length,1);
 assert.equal(g.files()[0].allow_new_research,false);
});

test('billing outage revokes admission but does not block a requested stop',async()=>{
 const f=harness();f.state.brokenBilling=true;await f.c.configure(config());await f.c.pause(true);
 await f.c.tick();assert.equal(f.files()[0].allow_new_research,false);assert.equal(f.files()[0].stop_requested,true);
 assert(f.commands().some(c=>Array.isArray(c.command)&&c.command.at(-1)==='/workspace/host-stop.py'));
});

test('low inference credit still recovers accounting under the separate cloud allocation',async()=>{
 const f=harness({running:false,balance:{...billing,balance:200}});await f.c.configure(config());await f.c.tick();
 assert.equal(f.files()[0].allow_new_research,false);
 assert(f.commands().some(c=>typeof c.command==='string'&&c.command.includes('host-boot')));
 assert.equal((await f.s.get('latest')).status,'starting');
});

test('paused service parks after a fresh backup and does not wake until explicit resume',async()=>{
 const f=harness();await f.c.configure(config());await f.c.pause(true);await f.c.tick();
 f.advance(120000);f.state.running=false;f.state.backup.completed_at=new Date(f.state.at).toISOString();await f.c.tick();
 assert.equal((await f.s.get('control')).parked,true);
 const before=f.calls.length;f.advance(60000);await f.c.tick();
 assert(f.calls.slice(before).every(r=>r.url.includes('/usage/summary')||r.url.includes('/spend?')));
 await f.c.pause(false);await f.c.tick();
 assert(f.commands().some(c=>typeof c.command==='string'&&c.command.includes('host-boot')));
});

test('pre-start service sleeps once and billing checks leave it asleep',async()=>{
 const f=harness({at:start-3600000,running:false});await f.c.configure(config());await f.c.tick();
 assert.equal((await f.s.get('control')).sleep_until,new Date(start).toISOString());
 const before=f.calls.length;f.advance(60000);await f.c.tick();
 assert(f.calls.slice(before).every(r=>r.url.includes('/usage/summary')));
 assert(!f.commands().some(c=>typeof c.command==='string'&&c.command.includes('host-boot')));
});

test('successful supervision sends one recovery notice and clears prior failures',async()=>{
 const f=harness({at:start-3600000});await f.c.configure(config());await f.s.put('control',{paused:false,failures:3});
 await f.c.tick();assert.equal((await f.s.get('control')).failures,0);
 assert.equal(f.sent.filter(m=>/service recovered/.test(m.subject)).length,1);
 f.advance(60000);await f.c.tick();assert.equal(f.sent.filter(m=>/service recovered/.test(m.subject)).length,1);
});

test('fixed week deadline sleeps even if progress stays live, backup stalls and probe fails',async()=>{
 const end=Date.parse(config().ends_at);
 const f=harness({at:end+300000});f.state.brokenBilling=true;f.state.brokenProbe=true;
 await f.c.configure(config());await f.c.tick();
 assert(f.calls.some(r=>r.url.endsWith('/sleep')));assert.equal((await f.s.get('control')).finished,true);assert.equal(f.s.alarm,null);
 assert(f.sent.some(m=>m.text.includes('shutdown_requires_reconciliation')));
 assert(!f.sent.some(m=>/week complete/.test(m.subject)));
});

test('measured cloud allowance exhaustion stops admissions and parks the resource',async()=>{
 const f=harness({compute:8});await f.c.configure(config());await f.c.tick();
 assert.equal(f.files()[0].allow_new_research,false);assert.equal(f.files()[0].stop_requested,true);
 f.advance(300000);f.state.running=false;f.state.backup.completed_at=new Date(f.state.at).toISOString();await f.c.tick();
 assert.equal((await f.s.get('control')).budget_parked,true);assert(f.sent.some(m=>m.text.includes('cloud_budget_exhausted')));
});

test('heartbeat thread cannot conceal stalled scheduling progress',async()=>{
 const f=harness({health:{progress_at:new Date(start-1800000).toISOString()}});await f.c.configure(config());
 for(let i=0;i<3;i++){f.state.health.heartbeat_at=new Date(f.state.at).toISOString();await f.c.tick();f.advance(60000);}
 assert(f.commands().some(c=>Array.isArray(c.command)&&c.command.at(-1)==='/workspace/host-stop.py'));
 assert(f.sent.some(m=>m.text.includes('research_progress_stalled')));
});

test('lost background start acknowledgement retries the exact durable operation',async()=>{
 const f=harness({running:false});f.state.loseBootAck=true;await f.c.configure(config());await f.c.tick();f.advance(60000);await f.c.tick();
 const boots=f.commands().filter(c=>typeof c.command==='string'&&c.command.includes('host-boot'));
 assert.equal(boots.length,2);assert.equal(boots[0].idempotency_key,boots[1].idempotency_key);
});


test('stalled coordinator escalates only after a two-minute graceful recovery window',async()=>{
 const f=harness({health:{progress_at:new Date(start-1800000).toISOString()}});await f.c.configure(config());
 for(let i=0;i<4;i++){f.state.health.heartbeat_at=new Date(f.state.at).toISOString();await f.c.tick();f.advance(60000);}
 assert(!f.commands().some(c=>Array.isArray(c.command)&&c.command.at(-1)==='force-stop'));
 f.state.health.heartbeat_at=new Date(f.state.at).toISOString();await f.c.tick();
 assert(f.commands().some(c=>Array.isArray(c.command)&&c.command.at(-1)==='force-stop'));
 f.advance(60000);f.state.running=false;await f.c.tick();
 assert(f.commands().some(c=>typeof c.command==='string'&&c.command.includes('host-boot')));
});
