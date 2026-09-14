import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {gzipSync} from 'node:zlib';
import {Supervisor,creditDecision,validateConfig,parseExec,boundedText,hostReserve,RELEASE_PROBE} from '../supervisor.mjs';
const start=Date.parse('2026-09-14T04:00:00Z');
const config=()=>({schema_version:1,service_id:'week-20260914',box_id:'sb_00000000-0000-0000-0000-000000000001',manifest_sha256:'a'.repeat(64),starts_at:new Date(start).toISOString(),ends_at:'2026-09-19T04:00:00Z',weekly_total_usd:'100',weekly_inference_usd:'92.5',cloud_budget_usd:'7.5',credit_floor_usd:'2'});
class Storage{
 constructor(){this.data=new Map();this.alarm=null;}
 async get(k){return structuredClone(this.data.get(k));}
 async put(k,v){this.data.set(k,structuredClone(v));}
 async list({prefix}){return new Map([...this.data].filter(([k])=>k.startsWith(prefix)));}
 async setAlarm(t){this.alarm=t;}
 async deleteAlarm(){this.alarm=null;}
 async transaction(fn){
  const before=structuredClone(this.data), alarm=this.alarm;
  const facade=Object.freeze({get:k=>this.get(k),put:(k,v)=>this.put(k,v),delete:async k=>this.data.delete(k),list:options=>this.list(options)});
  try{return await fn(facade);}catch(e){this.data=before;this.alarm=alarm;throw e;}
 }
}
const billing={balance:12000,balance_unavailable:false,has_metronome_customer:true,avg_cost_per_day:1000};
const rates={vcpu_second_usd_nanos:4167,memory_gib_second_usd_nanos:2222,state_disk_gib_second_usd_nanos:194};
function availableConfig() {
 const c={...rehearsalConfig(),spending_mode:'available_credit'};
 delete c.weekly_total_usd;delete c.weekly_inference_usd;
 delete c.rehearsal.inference_budget_usd;delete c.rehearsal.session_inference_budget_usd;
 return c;
}
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
  if(url.includes('/spend?'))return Response.json({pricing_configured:true,rates:state.brokenRates?{}:rates,sailboxes:[{sailbox_id:config().box_id,estimated_total_cost_usd_nanos:state.compute*1e9}]});
  if(url.endsWith('/v1/sailboxes/'+config().box_id)){
   if(state.brokenMetadata)throw Error('metadata_network');
   return Response.json({sailbox_id:config().box_id,vcpu_count:1,memory_mib:2048,state_disk_size_gib:32});
  }
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

const rehearsalConfig=()=>({...config(),rehearsal:{starts_at:new Date(start-8*3600000).toISOString(),ends_at:new Date(start-3*3600000).toISOString(),inference_budget_usd:'10',session_inference_budget_usd:'2'}});

test('written admission timestamps round-trip through the actual Python guest parser',async()=>{
 for(const millis of [123,999]) {
  const at=start+millis, f=harness({at});
  await f.c.configure(availableConfig());await f.c.tick();
  const admission=f.files()[0];
  assert.equal(admission.allow_new_research,true);
  const parsed=execFileSync('python3',['-c',
   'from portfolio_runtime.contracts import timestamp; import sys; print(int(timestamp(sys.argv[1]).timestamp()))',admission.updated_at],
   {cwd:new URL('../..',import.meta.url),encoding:'utf8'});
  assert.equal(Number(parsed),Math.floor(at/1000));
  const age=at-Number(parsed)*1000;
  assert(age>=0&&age<1000); // Never future-dated, and inside the guest freshness bound.
 }
});

test('repeated guest errors alert despite fresh heartbeat and advancing progress',async()=>{
 for(const reason of ['runtime_error','data_unavailable']){
  const f=harness({health:{status:'needs_attention',reason_code:reason}});
  await f.c.configure(config());
  for(let tick=0;tick<5;tick++){
   if(tick)f.advance(60000);
   f.state.health.heartbeat_at=new Date(f.state.at).toISOString();
   f.state.health.progress_at=new Date(f.state.at).toISOString();
   const result=await f.c.tick();
   assert.equal(result.status,'needs_attention');
  }
  assert.equal(f.sent.length,1);
  assert.match(f.sent[0].subject,/service needs attention/);
  assert.ok(f.sent[0].text.includes('Reason: '+reason+'.'));
  assert.equal((await f.s.get('mail:'+config().service_id+':service:'+reason)).state,'accepted');
  assert.equal(f.commands().filter(c=>Array.isArray(c.command)&&['/workspace/host-stop.py','force-stop'].includes(c.command.at(-1))).length,0);
 }
});

test('service errors notify once per episode across restarts, then notify again after observed recovery',async()=>{
 const f=harness({health:{status:'needs_attention',reason_code:'runtime_error'}});
 await f.c.configure(config());await f.c.tick();
 assert.equal(f.sent.filter(m=>/service needs attention/.test(m.subject)).length,1);
 // Recreate the controller with the same durable storage, as on deployment.
 f.c=new Supervisor(f.s,f.c.env,{now:()=>f.state.at,fetcher:f.c.fetcher});
 for(let i=0;i<3;i++){
  f.advance(60000);f.state.health.heartbeat_at=new Date(f.state.at).toISOString();f.state.health.progress_at=new Date(f.state.at).toISOString();await f.c.tick();
 }
 assert.equal(f.sent.length,1);
 assert.equal((await f.s.get('control')).service_failure_active,true);
 // A stale supposedly healthy process is not proof of recovery.
 f.advance(60000);f.state.health.status='running';f.state.health.reason_code=null;
 f.state.health.heartbeat_at=new Date(f.state.at-400000).toISOString();await f.c.tick();
 assert.equal((await f.s.get('control')).service_failure_active,true);
 f.advance(60000);f.state.health.heartbeat_at=new Date(f.state.at).toISOString();f.state.health.progress_at=new Date(f.state.at).toISOString();await f.c.tick();
 assert.equal((await f.s.get('control')).service_failure_active,false);
 assert.equal((await f.s.get('control')).service_failure_episode,1);
 assert.equal(f.sent.filter(m=>/service recovered/.test(m.subject)).length,1);
 f.advance(60000);f.state.health.status='needs_attention';f.state.health.reason_code='runtime_error';
 f.state.health.heartbeat_at=new Date(f.state.at).toISOString();f.state.health.progress_at=new Date(f.state.at).toISOString();await f.c.tick();
 assert.equal(f.sent.filter(m=>/service needs attention/.test(m.subject)).length,2);
 assert.equal((await f.s.get('mail:'+config().service_id+':service:runtime_error:1')).state,'accepted');
 f.advance(60000);await f.c.tick();assert.equal(f.sent.filter(m=>/service needs attention/.test(m.subject)).length,2);
});

test('legacy service failure receipts remain protected and ambiguous delivery is not retried',async()=>{
 const f=harness({health:{status:'needs_attention',reason_code:'data_unavailable'}});await f.c.configure(config());
 await f.s.put('mail:'+config().service_id+':service:data_unavailable',{kind:'failure',state:'unconfirmed',at:new Date(start-60000).toISOString()});
 await f.c.tick();assert.equal(f.sent.length,0);
 // A failed probe does not count as service recovery.
 f.advance(60000);f.state.brokenProbe=true;await f.c.tick();assert.equal((await f.s.get('control')).service_failure_active,true);
 f.state.brokenProbe=false;f.advance(60000);f.state.health.status='waiting';f.state.health.reason_code='scheduled_wait';
 f.state.health.heartbeat_at=new Date(f.state.at).toISOString();f.state.health.progress_at=new Date(f.state.at).toISOString();await f.c.tick();
 assert.equal((await f.s.get('control')).service_failure_active,false);
 f.c.env.EMAIL.send=async()=>{f.sent.push({subject:'ambiguous service failure'});throw Error('delivery unknown');};
 f.advance(60000);f.state.health.status='needs_attention';f.state.health.reason_code='data_unavailable';await f.c.tick();
 const mail=await f.s.get('mail:'+config().service_id+':service:data_unavailable:1');assert.equal(mail.state,'unconfirmed');
 const count=f.sent.length;f.advance(60000);await f.c.tick();assert.equal(f.sent.length,count);
});

test('a healthy upgrade probe retires old service alert identities before a new occurrence',async()=>{
 const f=harness();await f.c.configure(config());
 await f.s.put('mail:'+config().service_id+':service:runtime_error',{kind:'failure',state:'accepted',at:new Date(start-60000).toISOString()});
 await f.c.tick();assert.equal(f.sent.length,0);
 assert.equal((await f.s.get('control')).service_failure_episode,1);
 f.advance(60000);f.state.health.status='needs_attention';f.state.health.reason_code='runtime_error';await f.c.tick();
 assert.equal(f.sent.length,1);assert.equal((await f.s.get('mail:'+config().service_id+':service:runtime_error:1')).state,'accepted');
});

test('available-credit configuration has no fixed week or rehearsal dollar authority',()=>{
 const c=availableConfig();assert.equal(validateConfig(c).spending_mode,'available_credit');
 for(const change of [{weekly_inference_usd:'100'},{weekly_total_usd:'100'},
   {rehearsal:{...c.rehearsal,inference_budget_usd:'10'}},{spending_mode:'anything'}])assert.throws(()=>validateConfig({...c,...change}));
});

test('available-credit grants subtract outstanding and reserved work, and top-ups expand headroom',()=>{
 const c=availableConfig(), h={inference:{known_cost_usd:'300',committed_usd:'325',reserved_usd:'350'}};
 const d=creditDecision({...billing,balance:25000},c,h,start,7);
 assert.equal(d.max_inference_committed_usd,'541.00000000');assert.equal(d.max_additional_inference_usd,'191.00000000');
 assert.equal(d.outstanding_usd,25);assert.equal(d.allow,true);
 const topup=creditDecision({...billing,balance:35000},c,h,start,7);
 assert.equal(topup.max_additional_inference_usd,'291.00000000');
 const empty=creditDecision({...billing,balance:3400},c,h,start,7);
 assert.equal(empty.allow,false);assert.equal(empty.reason,'credit_low');
 assert.equal(creditDecision({...billing,balance_unavailable:true},c,h,start,7).allow,false);
});

test('available-credit runway uses observed burn rather than balance or proposed spending',()=>{
 const c=availableConfig(), h={funding:{planned_inference_usd_per_day:1000000}};
 const d=creditDecision({...billing,balance:12000,avg_cost_per_day:100},c,h,start,7);
 assert.equal(d.runway_days,111);assert.equal(d.warn,false);
 const idle=creditDecision({...billing,avg_cost_per_day:0},c,h,start,7);
 assert.equal(idle.runway_days,null);assert.equal(idle.warn,false);
});

test('observed twenty-dollar first hour warns before available credit is exhausted',()=>{
 const c=availableConfig();delete c.rehearsal;
 const h={inference:{known_cost_usd:'20',committed_usd:'20'}};
 const d=creditDecision({...billing,balance:10000,avg_cost_per_day:196},c,h,start+3600000,7);
 assert.equal(d.observed_inference_usd_per_day,480);
 assert.equal(d.runway_days,91/480);assert.equal(d.warn,true);assert.equal(d.allow,true);
 assert.equal(d.reason,'ready');
 const firstSecond=creditDecision({...billing,balance:10000,avg_cost_per_day:0},c,h,start+1000,7);
 assert.equal(firstSecond.observed_inference_usd_per_day,480);
});

test('rehearsal gap and future week never dilute measured deployment spending',()=>{
 const c=availableConfig(), h={inference:{known_cost_usd:'20',committed_usd:'20'}}, summary={...billing,avg_cost_per_day:0};
 const firstHour=creditDecision(summary,c,h,start-7*3600000,7);
 assert.equal(firstHour.observed_inference_usd_per_day,480);
 const ended=creditDecision(summary,c,h,start-3*3600000,7);
 const gap=creditDecision(summary,c,h,start-3600000,7);
 assert.equal(ended.observed_inference_usd_per_day,96);
 assert.equal(gap.observed_inference_usd_per_day,96);assert.equal(gap.runway_days,ended.runway_days);
 const weekHour=creditDecision(summary,c,h,start+3600000,7);
 assert.equal(weekHour.observed_inference_usd_per_day,80); // Five rehearsal hours + one actual weekday hour.
 const noCost=creditDecision(summary,c,{inference:{known_cost_usd:'0',committed_usd:'0'}},start-7*3600000,7);
 assert.equal(noCost.observed_inference_usd_per_day,0);assert.equal(noCost.runway_days,null);assert.equal(noCost.warn,false);
});

test('dynamic host reservation uses real resource ceilings through the shutdown grace',()=>{
 const c=availableConfig(), box={sailbox_id:c.box_id,vcpu_count:1,memory_mib:2048,state_disk_size_gib:32};
 const reserve=hostReserve({rates},box,c,start);
 assert.equal(reserve,(4167+2*2222+32*194)*(5*86400+300)/1e9);
 assert.equal(hostReserve({rates},box,c,Date.parse(c.ends_at)+300000),0);
 assert.throws(()=>hostReserve({rates:{}},box,c,start),/reserve/);
 assert.throws(()=>hostReserve({rates},{...box,sailbox_id:'other'},c,start),/reserve/);
});

test('available-credit rehearsal is not capped at ten dollars and compute reserve overrun does not stop it',async()=>{
 const c=availableConfig(), at=start-7*3600000;
 const f=harness({at,compute:9,health:{inference:{known_cost_usd:'300',committed_usd:'301',reserved_usd:'302'},rehearsal:{inference:{known_cost_usd:'30',committed_usd:'31'}}}});
 await f.c.configure(c);await f.c.tick();
 assert.equal(f.files()[0].allow_new_research,true);assert(Number(f.files()[0].max_additional_inference_usd)>100);
 assert.equal(f.files()[0].stop_requested,false);assert.equal((await f.s.get('control')).budget_parked,undefined);
 assert((await f.s.get('latest')).compute_reserved_usd>6);
 assert(!f.commands().some(c=>Array.isArray(c.command)&&c.command.at(-1)==='/workspace/host-stop.py'));
});

test('missing current host rates or metadata closes credit admission without blocking stop or recovery',async()=>{
 for(const flag of ['brokenRates','brokenMetadata']) {
   const f=harness({running:false});f.state[flag]=true;await f.c.configure(availableConfig());await f.c.tick();
   assert.equal(f.files()[0].allow_new_research,false);assert.equal(f.files()[0].max_additional_inference_usd,'0');
   assert(f.commands().some(c=>typeof c.command==='string'&&c.command.includes('host-boot')));
   await f.c.pause(true);f.state.running=true;await f.c.tick();
   assert(f.commands().some(c=>Array.isArray(c.command)&&c.command.at(-1)==='/workspace/host-stop.py'));
 }
});
test('rehearsal config preserves the week and accepts only a bounded explicit prelude',()=>{
 const c=rehearsalConfig();assert.equal(validateConfig(c).starts_at,config().starts_at);
 for(const change of [{ends_at:c.starts_at,starts_at:new Date(start-9*3600000).toISOString()},
   {ends_at:new Date(start+1000).toISOString()},{session_inference_budget_usd:'11'},{inference_budget_usd:'0'},{command:'anything'}]) {
  assert.throws(()=>validateConfig({...c,rehearsal:{...c.rehearsal,...change}}));
 }
});

test('Sunday rehearsal admits within its own cap before the unchanged weekday start',async()=>{
 const c=rehearsalConfig(), f=harness({at:start-7*3600000});await f.c.configure(c);await f.c.tick();
 assert.equal(f.files()[0].allow_new_research,true);
 assert.equal(f.files()[0].max_inference_committed_usd,'10.00000000');
 assert.equal((await f.s.get('config')).starts_at,config().starts_at);
 assert(!f.commands().some(c=>typeof c.command==='string'&&c.command.includes('host-boot')));
});

test('rehearsal completion emails once, denies gap admission, and sleeps until the original week',async()=>{
 const c=rehearsalConfig(), at=start-2*3600000;
 const f=harness({at,health:{status:'waiting',next_wake_at:c.starts_at,rehearsal:{...c.rehearsal,status:'complete',completed_at:new Date(at-60000).toISOString(),unsettled_requests:0,inference:{completed:11,requests:12,known_cost_usd:'1.23'}}}});
 await f.c.configure(c);await f.c.tick();
 assert.equal(f.files()[0].allow_new_research,false);
 assert.equal((await f.s.get('control')).sleep_until,undefined);
 assert.equal(f.commands().filter(c=>typeof c.command==='string'&&c.command.includes('supervisor_guest backup')).length,1);
 assert(!f.calls.some(r=>r.url.endsWith('/sleep')));
 f.advance(60000);f.state.backup.completed_at=new Date(f.state.at).toISOString();
 f.state.backup.manifest_key=c.service_id+'/snapshot-complete/'+ 'b'.repeat(64)+'.json';
 await f.c.tick();
 assert.equal((await f.s.get('control')).sleep_until,c.starts_at);
 assert.equal((await f.s.get('control')).rehearsal_backup.manifest_key,f.state.backup.manifest_key);
 assert.equal((await f.s.get('control')).finished,undefined);
 assert.equal(f.sent.filter(m=>/rehearsal complete/.test(m.subject)).length,1);
 assert(f.sent.some(m=>m.text.includes('9:00 PM Pacific')));
 assert(f.sent.some(m=>m.text.includes('11 completed / 12 requests')&&m.text.includes('$1.23')));
 assert(!f.sent.some(m=>/week complete/.test(m.subject)));
 const before=f.calls.length;f.advance(60000);await f.c.tick();
 assert(f.calls.slice(before).every(r=>r.url.includes('/usage/summary')));
 assert.equal(f.sent.filter(m=>/rehearsal complete/.test(m.subject)).length,1);
 f.advance(start-f.state.at);f.state.health.heartbeat_at=new Date(start).toISOString();f.state.health.progress_at=new Date(start).toISOString();f.state.health.status='running';
 await f.c.tick();assert.equal(f.files().at(-1).allow_new_research,true);
 assert.equal(f.sent.filter(m=>/rehearsal complete/.test(m.subject)).length,1);
});

test('a previously sleeping completed rehearsal wakes only for its missing final backup',async()=>{
 const c=availableConfig(),at=start-2*3600000;
 const health={status:'waiting',next_wake_at:c.starts_at,rehearsal:{...c.rehearsal,status:'complete',completed_at:new Date(at-60000).toISOString(),unsettled_requests:0}};
 const f=harness({at,running:false,health});await f.c.configure(c);
 f.state.backup.completed_at=new Date(at-120000).toISOString();
 await f.s.put('control',{paused:false,sleep_until:c.starts_at,backup_intent:{id:'old-backup',at:new Date(at-180000).toISOString(),confirmed:true}});
 await f.s.put('latest',{status:'waiting',health:f.state.health,backup:f.state.backup});
 await f.c.tick();
 assert.equal(f.files()[0].allow_new_research,false);
 assert.equal(f.files()[0].stop_requested,false);
 assert(!f.commands().some(c=>typeof c.command==='string'&&c.command.includes('host-boot')));
 assert.equal(f.commands().filter(c=>typeof c.command==='string'&&c.command.includes('supervisor_guest backup')).length,1);
 assert.equal((await f.s.get('control')).sleep_until,undefined);
 assert(!f.calls.some(r=>r.url.endsWith('/sleep')));
 f.advance(60000);f.state.backup={running:true,status:'running'};await f.c.tick();
 assert(!f.calls.some(r=>r.url.endsWith('/sleep')));
 f.advance(60000);f.state.backup={running:false,status:'complete',completed_at:new Date(f.state.at).toISOString(),manifest_key:c.service_id+'/snapshot-final/'+ 'c'.repeat(64)+'.json'};
 await f.c.tick();
 assert.equal((await f.s.get('control')).sleep_until,c.starts_at);
 assert.equal((await f.s.get('control')).rehearsal_backup.requested_at,new Date(at).toISOString());
 const before=f.calls.length;f.advance(60000);await f.c.tick();
 assert(f.calls.slice(before).every(r=>r.url.includes('/usage/summary')));
 assert.equal(f.sent.filter(m=>/rehearsal complete/.test(m.subject)).length,1);
});

test('a snapshot begun before completion cannot certify final rehearsal records',async()=>{
 const c=availableConfig(),at=start-2*3600000,marker=new Date(at-60000).toISOString();
 const f=harness({at,running:false,health:{status:'waiting',rehearsal:{...c.rehearsal,status:'complete',completed_at:marker,unsettled_requests:0}}});
 await f.c.configure(c);
 f.state.backup.manifest_key=c.service_id+'/snapshot-before/'+ 'd'.repeat(64)+'.json';
 await f.s.put('control',{paused:false,backup_intent:{id:'before-marker',at:new Date(at-120000).toISOString(),confirmed:true}});
 await f.c.tick();
 assert.equal((await f.s.get('control')).rehearsal_backup,undefined);
 assert.equal((await f.s.get('control')).sleep_until,undefined);
 assert.equal(f.commands().filter(c=>typeof c.command==='string'&&c.command.includes('supervisor_guest backup')).length,1);
 // Neither a failed snapshot nor a manifest from another service is sufficient.
 f.advance(60000);f.state.backup={running:false,status:'failed',completed_at:new Date(f.state.at).toISOString()};await f.c.tick();
 assert.equal((await f.s.get('control')).sleep_until,undefined);
 f.advance(60000);f.state.backup={running:false,status:'complete',completed_at:new Date(f.state.at).toISOString(),manifest_key:'another-service/snapshot-final/'+ 'e'.repeat(64)+'.json'};await f.c.tick();
 assert.equal((await f.s.get('control')).rehearsal_backup,undefined);
 assert.equal((await f.s.get('control')).sleep_until,undefined);
 assert(!f.calls.some(r=>r.url.endsWith('/sleep')));
});

test('funded bounded rehearsal avoids irrelevant weekly runway warnings while low credit still alerts',async()=>{
 const c=rehearsalConfig();
 const f=harness({at:start-7*3600000,balance:{...billing,balance:3000,avg_cost_per_day:11100}});
 await f.c.configure(c);await f.c.tick();assert.equal(f.files()[0].allow_new_research,true);
 assert.equal(f.sent.length,0);
 const g=harness({at:start-7*3600000,balance:{...billing,balance:500,avg_cost_per_day:11100}});
 await g.c.configure(c);await g.c.tick();assert.equal(g.files()[0].allow_new_research,false);
 assert(g.sent.some(m=>/paused for funding/.test(m.subject)));
});

test('unsettled rehearsal never sends completion and still recovers receipts during the gap',async()=>{
 const c=rehearsalConfig(), at=start-2*3600000;
 const f=harness({at,running:false,health:{rehearsal:{...c.rehearsal,status:'settling',completed_at:null,unsettled_requests:1}}});
 await f.c.configure(c);await f.c.tick();
 assert.equal(f.files()[0].allow_new_research,false);
 assert(f.commands().some(c=>typeof c.command==='string'&&c.command.includes('host-boot')));
 assert(!f.sent.some(m=>/rehearsal complete|week complete/.test(m.subject)));
 f.advance(60000);f.state.running=true;f.state.health.status='waiting';f.state.health.next_wake_at=c.starts_at;
 f.state.health.heartbeat_at=new Date(f.state.at).toISOString();f.state.health.progress_at=new Date(f.state.at).toISOString();
 await f.c.tick();assert(!f.calls.some(r=>r.url.endsWith('/sleep')));
});

async function replacementHarness() {
 const f=harness({at:start-3600000,running:false});await f.c.configure(config());
 const old=config(), next={...rehearsalConfig(),service_id:'week-20260914-v3',box_id:'sb_00000000-0000-0000-0000-000000000003',manifest_sha256:'c'.repeat(64)};
 const at=new Date(f.state.at-1000).toISOString(), snapshot='snapshot-20260913-abcd';
 const files=['paper.sqlite','research.sqlite','requests.sqlite'].map((name,i)=>({path:'state/seed/'+name,compressed_sha256:String(i+1).repeat(64),compressed_bytes:50,object_key:old.service_id+'/'+snapshot+'/'+String(i+1).repeat(64)+'.gz'}));
 const manifest={schema_version:1,service_id:old.service_id,snapshot_id:snapshot,completed_at:at,files};
 const raw=JSON.stringify(manifest),hash=createHash('sha256').update(raw).digest('hex'),key=old.service_id+'/'+snapshot+'/'+hash+'.json';
 f.c.env.BACKUPS={get:async k=>k===key?{body:new Response(raw).body,size:Buffer.byteLength(raw),customMetadata:{sha256:hash}}:null,head:async k=>{const row=files.find(r=>r.object_key===k);return row?{size:row.compressed_bytes,customMetadata:{sha256:row.compressed_sha256}}:null;}};
 await f.s.put('control',{paused:true,parked:true,stop_started_at:new Date(f.state.at-60000).toISOString(),failures:3,boot_intent:{id:'old'},credit_episode:7});
 await f.s.put('latest',{status:'paused',health:null,backup:{running:false,status:'complete',completed_at:at,manifest_key:key}});
 f.c.json=async()=>({sailbox_id:old.box_id,status:'sleeping'});
 f.c.file=async()=>({service_id:next.service_id,allow_new_research:false});
 f.c.exec=async()=>({manifest_sha256:next.manifest_sha256,running:false,health:null});
 return {...f,body:{previous_service_id:old.service_id,config:next,readiness:{ready:true,manifest_sha256:next.manifest_sha256,seed_verified:true,previous_backup_manifest_key:key}}};
}

test('replacement archives one stopped enrollment atomically and resets all old operational state',async()=>{
 const f=await replacementHarness();await f.c.replace(f.body);
 assert.equal((await f.s.get('config')).service_id,f.body.config.service_id);
 assert.deepEqual(await f.s.get('control'),{paused:false,failures:0});
 assert.equal((await f.s.get('archive:'+config().service_id)).control.boot_intent.id,'old');
 assert.equal((await f.s.get('latest')).health,undefined);
 assert.equal(f.s.alarm,f.state.at+1000);
 assert.equal((await f.c.replace(f.body)).replayed,true);
 assert.equal(await f.s.get('replacement_count'),1);
});

test('replacement refuses active, unreconciled, missing-backup, changed-seed and already-running candidates',async()=>{
 for(const mutate of [
   async f=>f.s.put('control',{...(await f.s.get('control')),paused:false}),
   async f=>f.s.put('control',{...(await f.s.get('control')),parked:false}),
   async f=>f.s.put('latest',{...(await f.s.get('latest')),health:{inference:{unsettled_requests:1}}}),
   async f=>{f.c.json=async()=>({sailbox_id:config().box_id,status:'running'});},
   async f=>{f.c.env.BACKUPS.head=async()=>null;},
   async f=>{f.body.readiness.previous_backup_manifest_key='wrong';},
   async f=>{f.c.exec=async()=>({manifest_sha256:f.body.config.manifest_sha256,running:true});},
   async f=>{f.c.file=async()=>({service_id:f.body.config.service_id,allow_new_research:true});},
   async f=>f.s.put('replacement_count',12),
 ]) {
   const f=await replacementHarness();await mutate(f);await assert.rejects(()=>f.c.replace(f.body));
   assert.equal((await f.s.get('config')).service_id,config().service_id);
   assert.equal(await f.s.get('archive:'+config().service_id),undefined);
 }
});

test('replacement transaction failure cannot half-switch the active controller',async()=>{
 const f=await replacementHarness(), original=f.s.put.bind(f.s);
 f.s.put=async(k,v)=>{if(k==='control')throw Error('storage_failed');return original(k,v);};
 await assert.rejects(()=>f.c.replace(f.body),/storage_failed/);
 assert.equal((await f.s.get('config')).service_id,config().service_id);
 assert.equal(await f.s.get('archive:'+config().service_id),undefined);
});

test('replacement schedules through SQLite storage when its transaction facade has no alarm API',async()=>{
 const f=await replacementHarness(), transaction=f.s.transaction.bind(f.s);let checked=false;
 f.s.transaction=fn=>transaction(async store=>{
   assert.deepEqual(Object.keys(store).sort(),['delete','get','list','put']);
   assert.equal(store.setAlarm,undefined);checked=true;return fn(store);
 });
 await f.c.replace(f.body);
 assert.equal(checked,true);assert.equal(f.s.alarm,f.state.at+1000);
 assert.equal((await f.s.get('config')).service_id,f.body.config.service_id);
});

test('SQLite transaction rolls back replacement and top-level alarm together after scheduling failure',async()=>{
 const f=await replacementHarness(), previousAlarm=f.state.at+300000;
 await f.s.setAlarm(previousAlarm);
 const setAlarm=f.s.setAlarm.bind(f.s);
 f.s.setAlarm=async value=>{await setAlarm(value);throw Error('alarm_storage_failed');};
 await assert.rejects(()=>f.c.replace(f.body),/alarm_storage_failed/);
 assert.equal(f.s.alarm,previousAlarm);
 assert.equal((await f.s.get('config')).service_id,config().service_id);
 assert.equal(await f.s.get('archive:'+config().service_id),undefined);
 assert.equal(await f.s.get('replacement_count'),undefined);
});

async function releaseHarness({sharedObjects=false}={}) {
 const f=harness({at:start-3600000,running:false});
 const canonical=value=>JSON.stringify(value,(_key,item)=>item&&typeof item==='object'&&!Array.isArray(item)
   ?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
 const hash=raw=>createHash('sha256').update(raw).digest('hex');
 const descriptor=raw=>({bytes:Buffer.byteLength(raw),sha256:hash(raw)});
 const old=config(), run={schema_version:1,kind:'weekday_service',service_id:old.service_id,spending_mode:'available_credit',
   week_starts_at:old.starts_at,week_ends_at:old.ends_at,state_dir:'/workspace/state'};
 const runRaw=canonical(run);
 const host={schema_version:1,role:'coordinator',deadline:old.ends_at,files:{'config/run.json':descriptor(runRaw),
   'portfolio_runtime/provider.py':descriptor('timeout = 45\n'),
   'portfolio_runtime/supervisor_guest.py':descriptor('# fixed probe\n'),'data/evidence.json':descriptor('{}')}};
 old.manifest_sha256=hash(canonical(host));
 const live=structuredClone(host);live.files['portfolio_runtime/provider.py']=descriptor('timeout = 600\n');
 const at=new Date(f.state.at-1000).toISOString(), snapshot='snapshot-release-20260913';
 const packed=new Map(), rows=[];
 for(const [path,value] of Object.entries({'host-manifest.json':canonical(host),'config/run.json':runRaw,
   'state/paper.sqlite':'paper fixture with pending decision','state/seed/research.sqlite':'immutable research fixture',
   'state/epochs/one/requests.sqlite':'pending inference holds','state/seed/requests.sqlite':'old receipts'})) {
   const raw=Buffer.from(value), zip=gzipSync(raw), h=hash(zip), key=old.service_id+'/'+(sharedObjects?'snapshot-prior-confirmed':snapshot)+'/'+h+'.gz';
   rows.push({path,...descriptor(raw),compressed_sha256:h,compressed_bytes:zip.length,object_key:key});packed.set(key,zip);
 }
 const backup={schema_version:1,service_id:old.service_id,snapshot_id:snapshot,completed_at:at,files:rows};
 const backupRaw=canonical(backup), backupHash=hash(backupRaw), key=old.service_id+'/'+snapshot+'/'+backupHash+'.json';
 f.c.env.BACKUPS={get:async k=>{
   const raw=k===key?Buffer.from(backupRaw):packed.get(k);return raw?{body:new Response(raw).body,size:raw.length,
     customMetadata:{sha256:k===key?backupHash:rows.find(row=>row.object_key===k).compressed_sha256}}:null;
 },head:async k=>{const raw=packed.get(k),row=rows.find(row=>row.object_key===k);
   return raw?{size:raw.length,customMetadata:{sha256:row.compressed_sha256}}:null;}};
 await f.c.configure(old);
 await f.s.put('control',{paused:true,parked:true,stop_started_at:new Date(f.state.at-60000).toISOString(),failures:2,
   stop_sent:true,credit_episode:3,boot_intent:{id:'existing'},last_tick:f.state.at-60000});
 const health={service_id:old.service_id,inference:{pending_requests:8,unsettled_requests:8,committed_usd:'22',reserved_usd:'100',known_cost_usd:'2'}};
 await f.s.put('latest',{status:'paused',health,backup:{running:false,status:'complete',completed_at:at,manifest_key:key}});
 const admission={service_id:old.service_id,allow_new_research:false,stop_requested:true};
 const resources={sailbox_id:old.box_id,vcpu_count:1,memory_mib:2048,state_disk_size_gib:32};
 const probe={manifest_sha256:hash(canonical(live)),running:false,health};
 f.c.json=async path=>{assert.equal(path,'/v1/sailboxes/'+old.box_id);return resources;};
 f.c.file=async(c,path)=>{assert.equal(c.box_id,old.box_id);
   if(path==='/workspace/config/admission.json')return admission;
   if(path==='/workspace/host-manifest.json')return live;
   assert.equal(path,'/workspace/config/run.json');return run;};
 f.c.exec=async(c,command)=>{assert.equal(c.box_id,old.box_id);
   assert.deepEqual(command,['python3','-c',RELEASE_PROBE]);return probe;};
 const body={previous_manifest_sha256:old.manifest_sha256,manifest_sha256:probe.manifest_sha256,previous_backup_manifest_key:key};
 return {...f,body,old,host,run,live,probe,admission,resources,packed,rows,
   refresh(){body.manifest_sha256=hash(canonical(live));probe.manifest_sha256=body.manifest_sha256;}};
}

test('same-box release preserves paused control and every pending hold, archives prior contract and replays exactly',async()=>{
 const f=await releaseHarness(), control=await f.s.get('control'), latest=await f.s.get('latest');
 const result=await f.c.release(f.body);assert.equal(result.released,true);
 assert.deepEqual(await f.s.get('config'),{...f.old,manifest_sha256:f.body.manifest_sha256});
 assert.deepEqual(await f.s.get('control'),control);assert.deepEqual(await f.s.get('latest'),latest);
 const archive=await f.s.get('release-archive:'+f.old.service_id+':'+f.old.manifest_sha256);
 assert.deepEqual(archive.config,f.old);assert.deepEqual(archive.manifest,f.host);
 assert.equal(archive.latest.health.inference.unsettled_requests,8);
 const receipt=await f.s.get('release:'+f.old.service_id+':'+f.body.manifest_sha256);
 assert.deepEqual(receipt.changed_files,['portfolio_runtime/provider.py']);assert.equal(f.s.alarm,f.state.at+1000);
 f.c.exec=async()=>{throw Error('must_not_repeat_external_verification');};
 assert.equal((await f.c.release({...f.body})).replayed,true);
 await assert.rejects(()=>f.c.release({...f.body,previous_backup_manifest_key:'different'}),/identity/);
 await assert.rejects(()=>f.c.release({previous_manifest_sha256:f.body.manifest_sha256,manifest_sha256:f.old.manifest_sha256,
   previous_backup_manifest_key:f.body.previous_backup_manifest_key}),/identity/);
});

test('release rejects active writers, changed service contracts and missing or stale post-stop backups',async()=>{
 for(const mutate of [
   async f=>f.s.put('control',{...(await f.s.get('control')),paused:false}),
   async f=>f.s.put('control',{...(await f.s.get('control')),parked:false}),
   async f=>f.s.put('latest',{...(await f.s.get('latest')),status:'running'}),
   async f=>f.s.put('control',{...(await f.s.get('control')),stop_started_at:new Date(f.state.at).toISOString()}),
   async f=>{f.body.previous_manifest_sha256='f'.repeat(64);},
   async f=>{f.body.previous_backup_manifest_key='different';},
   async f=>{f.body.service_id='other-service';},
   async f=>{f.c.env.BACKUPS.head=async()=>null;},
   async f=>{f.probe.running=true;},
   async f=>{f.body.manifest_sha256='f'.repeat(64);},
   async f=>{f.admission.allow_new_research=true;},
   async f=>{f.admission.stop_requested=false;},
   async f=>{f.admission.service_id='different-service';},
   async f=>{f.resources.state_disk_size_gib=64;},
   async f=>{f.run.service_id='changed-service';},
   async f=>{f.run.week_ends_at='2027-01-01T00:00:00Z';},
   async f=>{f.live.deadline='2027-01-01T00:00:00Z';f.refresh();},
   async f=>{f.live.role='researcher';f.refresh();},
   async f=>{delete f.live.files['data/evidence.json'];f.refresh();},
   async f=>{f.live.files['config/run.json'].sha256='f'.repeat(64);f.refresh();},
   async f=>{f.live.files['data/evidence.json'].sha256='f'.repeat(64);f.refresh();},
 ]) {
   const f=await releaseHarness();await mutate(f);await assert.rejects(()=>f.c.release(f.body));
   assert.deepEqual(await f.s.get('config'),f.old);
   assert.equal(await f.s.get('release-archive:'+f.old.service_id+':'+f.old.manifest_sha256),undefined);
 }
});

test('release accepts verified same-service shared backup objects and does not run newly installed helper code',async()=>{
 const f=await releaseHarness({sharedObjects:true});
 f.live.files['portfolio_runtime/supervisor_guest.py'].sha256='f'.repeat(64);f.refresh();
 await f.c.release(f.body);
 assert.equal((await f.s.get('config')).manifest_sha256,f.body.manifest_sha256);
 assert.deepEqual((await f.s.get('release:'+f.old.service_id+':'+f.body.manifest_sha256)).changed_files,
   ['portfolio_runtime/provider.py','portfolio_runtime/supervisor_guest.py']);
 assert(!RELEASE_PROBE.includes('portfolio_runtime'));assert(!RELEASE_PROBE.includes('exec('));
 const proof=execFileSync('python3',['-c',
   "import fcntl,json,pathlib,subprocess,sys,tempfile\nwith tempfile.TemporaryDirectory() as tmp:\n p=pathlib.Path(tmp)/'lock';p.touch()\n code=sys.argv[1].replace('/workspace/state/coordinator.lock',str(p))\n assert json.loads(subprocess.check_output([sys.executable,'-c',code]))=={'running':False}\n with p.open('r+') as f:\n  fcntl.flock(f,fcntl.LOCK_EX)\n  assert json.loads(subprocess.check_output([sys.executable,'-c',code]))=={'running':True}\nprint('verified')",RELEASE_PROBE],{encoding:'utf8'});
 assert.equal(proof.trim(),'verified');
});

test('release checks compressed and uncompressed backup bytes instead of trusting metadata',async()=>{
 for(const mode of ['compressed','plain']) {
   const f=await releaseHarness(), row=f.rows.find(row=>row.path==='host-manifest.json');
   if(mode==='compressed')f.packed.get(row.object_key)[15]^=1;
   else {
     const get=f.c.env.BACKUPS.get.bind(f.c.env.BACKUPS), key=f.body.previous_backup_manifest_key;
     const manifest=JSON.parse(await boundedText(await get(key)));
     manifest.files.find(item=>item.path===row.path).sha256='f'.repeat(64);
     const raw=JSON.stringify(manifest),hash=createHash('sha256').update(raw).digest('hex'),nextKey=key.replace(/[a-f0-9]{64}\.json$/,hash+'.json');
     f.c.env.BACKUPS.get=async key=>key===nextKey?{body:new Response(raw).body,size:Buffer.byteLength(raw),customMetadata:{sha256:hash}}:get(key);
     f.body.previous_backup_manifest_key=nextKey;const latest=await f.s.get('latest');latest.backup.manifest_key=nextKey;await f.s.put('latest',latest);
   }
   await assert.rejects(()=>f.c.release(f.body),/backup_integrity/);assert.deepEqual(await f.s.get('config'),f.old);
 }
});

test('release storage or alarm failure atomically restores manifest, archive, receipt and paused state',async()=>{
 for(const failure of ['config','alarm']) {
   const f=await releaseHarness(), before=structuredClone(f.s.data), previousAlarm=f.s.alarm;
   if(failure==='config') {const put=f.s.put.bind(f.s);f.s.put=async(k,v)=>{if(k==='config')throw Error('storage_failed');return put(k,v);};}
   else {const alarm=f.s.setAlarm.bind(f.s);f.s.setAlarm=async at=>{await alarm(at);throw Error('alarm_failed');};}
   await assert.rejects(()=>f.c.release(f.body),/failed/);
   assert.deepEqual(f.s.data,before);assert.equal(f.s.alarm,previousAlarm);
 }
});

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
 assert.equal(g.sent.filter(m=>/funding/.test(m.subject)).length,1);
 assert.equal(g.files()[0].allow_new_research,false);
});

test('an early runway warning cannot suppress the later blocked-funding email, and top-ups reset that episode',async()=>{
 const f=harness({balance:{...billing,balance:2000,avg_cost_per_day:100000}});
 await f.c.configure(availableConfig());await f.c.tick();
 assert.equal(f.sent.filter(m=>/Sail funding needed/.test(m.subject)).length,1);
 assert.equal(f.files().at(-1).allow_new_research,true);
 f.state.balance={...billing,balance:100,avg_cost_per_day:100000};f.advance(60000);await f.c.tick();
 assert.equal(f.files().at(-1).allow_new_research,false);
 assert.equal(f.sent.filter(m=>/research paused for funding/.test(m.subject)).length,1);
 f.advance(60000);await f.c.tick();assert.equal(f.sent.filter(m=>/research paused for funding/.test(m.subject)).length,1);
 f.state.balance={...billing,balance:500000,avg_cost_per_day:100000};f.advance(60000);await f.c.tick();
 assert.equal(f.files().at(-1).allow_new_research,true);
 f.state.balance={...billing,balance:100,avg_cost_per_day:100000};f.advance(60000);await f.c.tick();
 assert.equal(f.sent.filter(m=>/research paused for funding/.test(m.subject)).length,2);
});

test('week completion does not claim settlement while terminal request cost holds remain unknown',async()=>{
 const end=Date.parse(config().ends_at),f=harness({at:end,running:false,
   health:{inference:{pending_requests:0,unsettled_requests:2,known_cost_usd:'10',committed_usd:'12'}}});
 await f.c.configure(availableConfig());await f.c.tick();f.advance(120000);await f.c.tick();
 assert.equal((await f.s.get('latest')).status,'needs_attention');
 assert.equal((await f.s.get('control')).finished,true);
 assert(f.sent.some(m=>m.text.includes('unsettled_requests_retained')));
 assert(!f.sent.some(m=>m.subject.includes('week complete')));
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
