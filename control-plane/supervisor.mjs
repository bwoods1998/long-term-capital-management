// Fixed cloud operations only. Agent outputs cannot supply commands or authority.
import {createHash} from 'node:crypto';
export const API = 'https://sailbox-api.sailresearch.com';
export const INFERENCE = 'https://api.sailresearch.com';
const iso = ms => new Date(ms).toISOString();
const finite = v => typeof v === 'number' && Number.isFinite(v) && v >= 0;
const availableCredit = c => c.spending_mode==='available_credit';
export const dollars = value => { if (typeof value !== 'number' && (typeof value !== 'string' || !/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value))) throw new Error('invalid_money'); const n = Number(value); if (!finite(n)) throw new Error('invalid_money'); return n; };
const grant = value => (Math.floor(Math.max(0,value) * 1e8) / 1e8).toFixed(8);
const failureCode = error => error?.message === 'Illegal invocation' ? 'fetch_illegal_invocation'
  : /AbortSignal\.timeout/.test(error?.message || '') ? 'timeout_api_unavailable'
  : /^[a-z0-9_]{1,64}$/.test(error?.message || '') ? error.message
  : error?.name === 'SyntaxError' ? 'invalid_provider_json' : error?.name === 'TypeError' ? 'transport_type_error' : 'supervisor_failure';
export function validateConfig(c) {
  if (!c || c.schema_version !== 1 || !/^[a-z0-9-]{8,64}$/.test(c.service_id || '')
    || !/^sb_[0-9a-f-]{36}$/.test(c.box_id || '') || !/^[a-f0-9]{64}$/.test(c.manifest_sha256 || '')) throw new Error('invalid_config');
  const start = Date.parse(c.starts_at), end = Date.parse(c.ends_at);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || end - start > 8 * 86400000) throw new Error('invalid_window');
  for (const name of ['cloud_budget_usd','credit_floor_usd']) dollars(c[name]);
  if (dollars(c.cloud_budget_usd)<=0||dollars(c.credit_floor_usd)<1) throw new Error('invalid_budget');
  if (c.spending_mode!==undefined&&!availableCredit(c)) throw new Error('invalid_spending_mode');
  if (availableCredit(c)) {
    if (Object.hasOwn(c,'weekly_total_usd')||Object.hasOwn(c,'weekly_inference_usd')) throw new Error('fixed_budget_in_credit_mode');
  } else if (dollars(c.weekly_total_usd) <= 0 || dollars(c.weekly_total_usd) > 10000
    || dollars(c.weekly_inference_usd) + dollars(c.cloud_budget_usd) > dollars(c.weekly_total_usd)
    || dollars(c.credit_floor_usd) < 1) throw new Error('invalid_budget');
  if (Object.keys(c).some(k => !['schema_version','service_id','box_id','manifest_sha256','starts_at','ends_at',
    'weekly_total_usd','weekly_inference_usd','cloud_budget_usd','credit_floor_usd','rehearsal','spending_mode'].includes(k))) throw new Error('unknown_config');
  if (c.rehearsal !== undefined) {
    const r=c.rehearsal, a=Date.parse(r?.starts_at), b=Date.parse(r?.ends_at);
    const fields=availableCredit(c)?'ends_at,starts_at':'ends_at,inference_budget_usd,session_inference_budget_usd,starts_at';
    if (!r || Object.keys(r).sort().join(',')!==fields
      || !Number.isFinite(a)||!Number.isFinite(b)||b-a<3600000||b-a>8*3600000||b>start||end-a>7*86400000) throw new Error('invalid_rehearsal');
    if (!availableCredit(c)&&(dollars(r.inference_budget_usd)<=0||dollars(r.inference_budget_usd)>Math.min(10,dollars(c.weekly_inference_usd))
      || dollars(r.session_inference_budget_usd)<=0||dollars(r.session_inference_budget_usd)>Math.min(2,dollars(r.inference_budget_usd)))) throw new Error('invalid_rehearsal');
  }
  return c;
}
export function creditDecision(summary, c, health = {}, at = Date.now(), cloudRemaining = 0) {
  if (!summary || summary.balance_unavailable || summary.has_metronome_customer !== true || !finite(summary.balance)) return {allow:false, reason:'billing_unavailable', max_inference_committed_usd:'0', max_additional_inference_usd:'0'};
  const balance = summary.balance / 100; // Sail billing fields are fractional US cents.
  const committed = dollars(health.inference?.committed_usd ?? health.inference_committed_usd ?? 0);
  const reserved = Math.max(committed, dollars(health.inference?.reserved_usd ?? committed));
  const known = dollars(health.inference?.known_cost_usd ?? health.inference_known_usd ?? 0);
  const outstanding = Math.max(0, committed - known);
  const ceiling=availableCredit(c)?Infinity:dollars(c.weekly_inference_usd);
  const absolute = Math.max(0, Math.min(ceiling, known + balance - dollars(c.credit_floor_usd) - dollars(cloudRemaining)));
  const usable = Math.max(0, absolute - reserved);
  const requestRoom = Math.max(0, absolute - committed);
  const hours = Math.max(1, (Date.parse(c.ends_at) - Math.max(at, Date.parse(c.starts_at))) / 3600000);
  // A technical ceiling is not a forecast of purposeful spending. Use the
  // guest's current evaluated research intensity when it is available.
  const proposedRate = health.funding?.planned_inference_usd_per_day;
  const plannedPerDay = availableCredit(c)?0:finite(proposedRate) ? Math.min(proposedRate, Math.max(0, dollars(c.weekly_inference_usd) - reserved) / hours * 24)
    : Math.min(24, Math.max(0, dollars(c.weekly_inference_usd) - reserved) / hours * 24);
  const measuredPerDay = finite(summary.avg_cost_per_day) ? summary.avg_cost_per_day / 100 : 0;
  // Only elapsed scheduled research time belongs in the deployment rate:
  // future weekdays and the rehearsal-to-week gap are not operating hours.
  const elapsed=(begin,end)=>Math.max(0,Math.min(at,Date.parse(end))-Date.parse(begin));
  const activeHours=(elapsed(c.starts_at,c.ends_at)+(c.rehearsal?elapsed(c.rehearsal.starts_at,c.rehearsal.ends_at):0))/3600000;
  const deploymentPerDay=availableCredit(c)?known*24/Math.max(1,activeHours):0;
  const observedPerDay=Math.max(measuredPerDay,deploymentPerDay);
  const burn = Math.max(plannedPerDay, observedPerDay);
  const runway = burn > 0 ? Math.max(0, balance - outstanding - dollars(c.credit_floor_usd) - cloudRemaining) / burn : null;
  const exhausted = !availableCredit(c)&&dollars(c.weekly_inference_usd) - committed < .1;
  return {allow:requestRoom >= .1, reason:requestRoom >= .1 ? 'ready' : exhausted ? 'authorization_exhausted' : 'credit_low', balance_usd:balance,
    outstanding_usd:outstanding, usable_usd:usable, runway_days:runway, observed_inference_usd_per_day:observedPerDay,
    max_inference_committed_usd:grant(absolute), max_additional_inference_usd:grant(usable),
    warn:requestRoom < .1 || (runway !== null && runway < 2)};
}
export function hostReserve(usage, box, c, at) {
  const rates=usage.rates||{}, keys=['vcpu_second_usd_nanos','memory_gib_second_usd_nanos','state_disk_gib_second_usd_nanos'];
  if (box?.sailbox_id!==c.box_id||keys.some(k=>!Number.isSafeInteger(rates[k])||rates[k]<0)
    ||['vcpu_count','memory_mib','state_disk_size_gib'].some(k=>!Number.isSafeInteger(box[k])||box[k]<=0)) throw new Error('compute_reserve_unavailable');
  // Reserve the actual resource ceilings through the fixed shutdown boundary.
  // This is a funding reservation, never a stop at an arbitrary dollar amount.
  const seconds=Math.max(0,Math.ceil((Date.parse(c.ends_at)+300000-at)/1000));
  const value=(rates[keys[0]]*box.vcpu_count+rates[keys[1]]*box.memory_mib/1024+rates[keys[2]]*box.state_disk_size_gib)*seconds/1e9;
  if (!finite(value)) throw new Error('compute_reserve_unavailable');
  return value;
}
export async function boundedText(response, maximum = 256 * 1024) {
  const reader = response.body?.getReader(); if (!reader) return '';
  const chunks = []; let size = 0;
  while (true) { const {done,value} = await reader.read(); if (done) break; size += value.byteLength;
    if (size > maximum) { await reader.cancel(); throw new Error('oversized_response'); } chunks.push(value); }
  return Buffer.concat(chunks).toString('utf8');
}
export function parseExec(text) {
  let output = '', code = null, started = null;
  for (const line of text.trim().split('\n')) {
    if (!line.trim()) continue;
    const event = JSON.parse(line);
    if (event.type === 'started') started = event.exec_request_id;
    if (event.type === 'stdout') output += Buffer.from(event.data, 'base64').toString('utf8');
    if (event.type === 'exit') code = event.return_code;
    if (event.type === 'error') throw new Error('remote_exec_failed');
  }
  return {output,code,started};
}
export class Supervisor {
  constructor(storage, env, {fetcher = fetch, now = Date.now} = {}) { this.s = storage; this.env = env; this.fetcher = fetcher; this.now = now; this.tail = Promise.resolve(); }
  serial(fn) { const p = this.tail.then(fn); this.tail = p.catch(() => {}); return p; }
  async request(path, options = {}, base = API) {
    // Workers' native fetch must not receive a Supervisor instance as `this`.
    const fetcher = this.fetcher;
    const r = await fetcher(base + path, {...options, redirect:'manual', signal:AbortSignal.timeout(45000),
      headers:{'Authorization':'Bearer ' + this.env.SAIL_API_KEY,'Content-Type':'application/json',...options.headers}});
    if (!r.ok) { r.body?.cancel(); throw new Error('provider_http_' + r.status); }
    return r;
  }
  async json(path, options, base) { return JSON.parse(await boundedText(await this.request(path, options, base))); }
  async file(c, path, body) {
    const url = '/v1/sailboxes/' + c.box_id + '/files?path=' + encodeURIComponent(path);
    const r = await this.request(url + (body === undefined ? '' : '&mode=384'), body === undefined ? {} :
      {method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:JSON.stringify(body)});
    return body === undefined ? JSON.parse(await boundedText(r)) : (await r.arrayBuffer(), true);
  }
  async exec(c, command, {background=false, id, timeout=30}={}) {
    const body = {command,timeout, ...(background ? {background:true} : {}), ...(id ? {idempotency_key:id} : {})};
    const r = await this.request('/v1/sailboxes/' + c.box_id + '/exec', {method:'POST',body:JSON.stringify(body)});
    if (background) { // Detach after the durable exec identity arrives; never wait for the workload.
      const reader = r.body.getReader(), decoder = new TextDecoder(); let buffer = '';
      try { while (true) { const {done,value} = await reader.read(); if (done) break;
        buffer += decoder.decode(value,{stream:true}); if (buffer.length > 32000) throw new Error('invalid_exec_receipt');
        let pos; while ((pos = buffer.indexOf('\n')) >= 0) { const line = buffer.slice(0,pos); buffer = buffer.slice(pos+1);
          if (!line.trim()) continue; const e = JSON.parse(line); if (e.type === 'started') return {started:e.exec_request_id};
          if (e.type === 'error') throw new Error('remote_exec_failed'); }
      } throw new Error('exec_unconfirmed'); } finally { await reader.cancel().catch(() => {}); }
    }
    const result = parseExec(await boundedText(r));
    if (result.code !== 0) throw new Error('remote_exec_failed');
    return result.output.trim() ? JSON.parse(result.output) : {};
  }
  async alert(id, kind, details = {}) {
    const key = 'mail:' + id; if (await this.s.get(key)) return;
    const titles = {credit_low:'Sail funding needed',billing_unavailable:'Sail balance unavailable',
      failure:'Portfolio service needs attention',recovered:'Portfolio service recovered',backup:'Portfolio backup needs attention',
      complete:'Portfolio week complete',paused:'Portfolio service paused',rehearsal:'Portfolio rehearsal complete'};
    const lines = [titles[kind] + '.', ''];
    if (details.reason && /^[a-z0-9_]{1,64}$/.test(details.reason)) lines.push('Reason: ' + details.reason + '.');
    if (finite(details.balance_usd)) lines.push('Sail balance: $' + details.balance_usd.toFixed(2) + '.');
    if (finite(details.runway_days)) lines.push('Estimated research runway: ' + details.runway_days.toFixed(1) + ' days.');
    if (kind === 'credit_low') lines.push('Add Sail credit to keep research running. The service detects funding automatically; no restart is needed: https://app.sailresearch.com/');
    if (kind === 'recovered') lines.push('Cloud supervision is healthy again. The service will continue within its scheduled window.');
    if (kind === 'rehearsal') {
      lines.push('The rehearsal has ended and its inference requests are settled. The same paper portfolio continues into the scheduled week.');
      if (Number.isFinite(Date.parse(details.next_start_at))) lines.push('Scheduled week begins: '+new Date(details.next_start_at).toLocaleString('en-US',{timeZone:'America/Los_Angeles',dateStyle:'medium',timeStyle:'short'})+' Pacific.');
    }
    const totals=kind==='rehearsal'?details.health?.rehearsal?.inference:details.health?.inference;
    if (['complete','rehearsal'].includes(kind) && totals) {
      if (Number.isSafeInteger(totals.completed) && Number.isSafeInteger(totals.requests)) lines.push('Research: ' + totals.completed + ' completed / ' + totals.requests + ' requests.');
      try { lines.push('Recorded inference cost: $' + dollars(totals.known_cost_usd).toFixed(2) + '.'); } catch {}
      lines.push('Review the paper portfolio and dated decisions below. Research activity alone does not establish investment improvement.');
    }
    lines.push('', 'https://blakewoods.us/portfolio/', 'https://github.com/bwoods1998/portfolio-agent');
    // Persist before send. Ambiguous delivery is never automatically repeated.
    await this.s.put(key, {kind,state:'sending',at:iso(this.now())});
    try {
      const r = await this.env.EMAIL.send({from:'agent@blakewoods.us',to:'blakewoods98@gmail.com',subject:'Portfolio Agent — '+titles[kind],text:lines.join('\n')});
      await this.s.put(key,{kind,state:r?.messageId ? 'accepted' : 'unconfirmed',at:iso(this.now())});
    } catch { await this.s.put(key,{kind,state:'unconfirmed',at:iso(this.now())}); }
  }
  async configure(c) {
    validateConfig(c);
    return this.serial(async () => {
      const prior = await this.s.get('config');
      if (prior && JSON.stringify(prior) !== JSON.stringify(c)) throw new Error('service_already_configured');
      await this.s.put('config',c); if (!await this.s.get('control')) await this.s.put('control',{paused:false,failures:0});
      await this.s.setAlarm(this.now()+1000); return {configured:true,service_id:c.service_id};
    });
  }
  async replace(body) {
    if (!body || Object.keys(body).sort().join(',')!=='config,previous_service_id,readiness') throw new Error('invalid_replacement');
    const c=validateConfig(body.config), receipt=body.readiness;
    if (!receipt || Object.keys(receipt).sort().join(',')!=='manifest_sha256,previous_backup_manifest_key,ready,seed_verified'
      || receipt.ready!==true||receipt.seed_verified!==true||receipt.manifest_sha256!==c.manifest_sha256) throw new Error('replacement_not_ready');
    return this.serial(async()=>{
      const prior=await this.s.get('config'), control=await this.s.get('control'), latest=await this.s.get('latest');
      if (prior?.service_id===c.service_id) {
        const done=await this.s.get('replacement:'+c.service_id);
        if (done && done.previous_service_id===body.previous_service_id && JSON.stringify(prior)===JSON.stringify(c)
          && JSON.stringify(done.readiness)===JSON.stringify(receipt)) return {replaced:true,replayed:true,service_id:c.service_id};
        throw new Error('replacement_identity_reused');
      }
      if (!prior || prior.service_id!==body.previous_service_id || prior.box_id===c.box_id
        || await this.s.get('archive:'+c.service_id) || await this.s.get('replacement:'+c.service_id)) throw new Error('replacement_identity_changed');
      const count=await this.s.get('replacement_count')||0;
      if (count>=12) throw new Error('replacement_limit');
      const backup=latest?.backup, stopped=Date.parse(control?.stop_started_at), completed=Date.parse(backup?.completed_at);
      if (control?.paused!==true||control?.parked!==true||latest?.status!=='paused'||!Number.isFinite(stopped)
        ||backup?.status!=='complete'||backup.running!==false||!Number.isFinite(completed)||completed<stopped
        ||receipt.previous_backup_manifest_key!==backup.manifest_key
        || Number(latest?.health?.inference?.pending_requests ?? 0)!==0
        || Number(latest?.health?.inference?.unsettled_requests ?? 0)!==0) throw new Error('previous_service_not_parked');
      const oldBox=await this.json('/v1/sailboxes/'+prior.box_id);
      if (oldBox.sailbox_id!==prior.box_id||!['sleeping','paused'].includes(oldBox.status)) throw new Error('previous_box_not_asleep');
      const key=backup.manifest_key;
      if (typeof key!=='string'||!key.startsWith(prior.service_id+'/')||!new RegExp('^[a-z0-9-]{8,64}/[a-z0-9-]{8,80}/[a-f0-9]{64}\\.json$').test(key)) throw new Error('backup_identity_changed');
      const object=await this.env.BACKUPS.get(key);
      if (!object||object.size>2*1024*1024) throw new Error('backup_unavailable');
      const raw=await boundedText(object,2*1024*1024), hash=createHash('sha256').update(raw).digest('hex');
      if (!key.endsWith('/'+hash+'.json')||object.customMetadata?.sha256!==hash) throw new Error('backup_integrity_failed');
      const manifest=JSON.parse(raw);
      if (manifest.schema_version!==1||manifest.service_id!==prior.service_id||manifest.completed_at!==backup.completed_at
        ||manifest.snapshot_id!==key.split('/')[1]||!Array.isArray(manifest.files)||!manifest.files.length||manifest.files.length>4000) throw new Error('backup_integrity_failed');
      for (const name of ['paper.sqlite','research.sqlite','requests.sqlite']) if (!manifest.files.some(row=>['state/'+name,'state/seed/'+name].includes(row.path))) throw new Error('backup_missing_ledger');
      for(let i=0;i<manifest.files.length;i+=20) await Promise.all(manifest.files.slice(i,i+20).map(async row=>{
        if (!/^[a-f0-9]{64}$/.test(row.compressed_sha256||'')||row.object_key!==prior.service_id+'/'+manifest.snapshot_id+'/'+row.compressed_sha256+'.gz'
          ||!Number.isSafeInteger(row.compressed_bytes)||row.compressed_bytes<1) throw new Error('backup_integrity_failed');
        const head=await this.env.BACKUPS.head(row.object_key);
        if (!head||head.size!==row.compressed_bytes||head.customMetadata?.sha256!==row.compressed_sha256) throw new Error('backup_artifact_missing');
      }));
      const admission=await this.file(c,'/workspace/config/admission.json');
      const probe=await this.exec(c,['python3','/workspace/portfolio_runtime/supervisor_guest.py','probe']);
      if (admission.service_id!==c.service_id||admission.allow_new_research!==false||probe.running!==false
        ||probe.manifest_sha256!==c.manifest_sha256||Number(probe.health?.inference?.pending_requests??0)!==0
        ||Number(probe.health?.inference?.unsettled_requests??0)!==0) throw new Error('replacement_not_stopped');
      const at=iso(this.now());
      await this.s.transaction(async store=>{
        await store.put('archive:'+prior.service_id,{archived_at:at,config:prior,control,latest});
        await store.put('replacement:'+c.service_id,{at,previous_service_id:prior.service_id,readiness:receipt});
        await store.put('replacement_count',count+1);
        await store.put('config',c);await store.put('control',{paused:false,failures:0});
        await store.put('latest',{as_of:at,service_id:c.service_id,status:'waiting'});
        // SQLite storage operations participate in this transaction; the
        // legacy transaction facade need not expose the alarm methods.
        await this.s.setAlarm(this.now()+1000);
      });
      return {replaced:true,service_id:c.service_id};
    });
  }
  async status() { return {config:await this.s.get('config'),control:await this.s.get('control'),latest:await this.s.get('latest'),
    mails:Object.fromEntries(await this.s.list({prefix:'mail:',limit:50}))}; }
  async pause(value) { return this.serial(async () => { const v = await this.s.get('control') || {}; v.paused = value;
    delete v.last_tick; delete v.sleep_until; delete v.parked; delete v.stop_started_at; delete v.stop_sent; delete v.stop_backup_after;
    await this.s.put('control',v); await this.s.setAlarm(this.now()+1000); return {paused:value}; }); }
  tick() { return this.serial(() => this._tick()); }
  async _tick() {
    const c = await this.s.get('config'); if (!c) return {configured:false};
    const at = this.now(), control = await this.s.get('control') || {paused:false,failures:0};
    if (control.finished) return {finished:true};
    if (at - (control.last_tick ?? 0) < 45000) { await this.s.setAlarm((control.last_tick || at) + 60000); return {throttled:true}; }
    control.last_tick = at; await this.s.put('control',control);
    await this.s.setAlarm(at + 60000); // Durable recovery before any external work.
    const previous = await this.s.get('latest');
    const hadFailure = (control.failures || 0) > 0;
    const latest = {as_of:iso(at),service_id:c.service_id,health:previous?.health,backup:previous?.backup};
    const weekStart=Date.parse(c.starts_at), start=Date.parse(c.rehearsal?.starts_at||c.starts_at), end=Date.parse(c.ends_at), ended=at>=end;
    const rehearsalActive=!!c.rehearsal&&at>=start&&at<Date.parse(c.rehearsal.ends_at);
    const rehearsalGap=!!c.rehearsal&&at>=Date.parse(c.rehearsal.ends_at)&&at<weekStart;
    const save = async () => { await this.s.put('control',control); await this.s.put('latest',latest); return latest; };
    const recovered = async () => { if (!hadFailure) return; control.failures=0;
      await this.alert(c.service_id+':recovered:'+(control.recovery_episode||0),'recovered');
      control.recovery_episode=(control.recovery_episode||0)+1; };
    const sleep = async wake => this.json('/v1/sailboxes/'+c.box_id+'/sleep',{method:'POST',body:JSON.stringify(wake ? {wake_at:iso(wake)} : {})});
    const fail = async reason => { control.failures=(control.failures||0)+1;latest.status='needs_attention';latest.reason_code=reason;
      if (control.failures>=3) await this.alert(c.service_id+':failure:'+iso(at).slice(0,10),'failure',{reason}); };
    // Billing outages revoke admission; they never prevent stop, backup or cleanup.
    let summary = null;
    try { summary = await this.json('/v2/usage/summary?range=7d',{},INFERENCE); }
    catch (error) { latest.billing_status='unavailable';latest.billing_reason_code=failureCode(error); }
    if (!control.spend_checked_at || at-control.spend_checked_at >= 3600000) {
      try {
        const usage = await this.json('/v1/sailboxes/spend?sailbox_id='+c.box_id);
        const row = usage.sailboxes?.find(box => box.sailbox_id===c.box_id);
        const nanos = row?.estimated_total_cost_usd_nanos;
        if (usage.pricing_configured !== true || !finite(nanos)) throw new Error('compute_spend_unavailable');
        control.compute_used_usd = Math.max(control.compute_used_usd || 0,nanos/1e9);
        if (availableCredit(c)) {
          const box=await this.json('/v1/sailboxes/'+c.box_id);
          control.compute_reserve_usd=hostReserve(usage,box,c,at);
        }
        control.spend_checked_at=at;
      } catch (error) { latest.compute_status='unavailable';latest.compute_reason_code=failureCode(error); }
    }
    const computeKnown = finite(control.compute_used_usd);
    const computeExhausted = !availableCredit(c) && computeKnown && control.compute_used_usd >= dollars(c.cloud_budget_usd);
    latest.compute_used_usd=control.compute_used_usd ?? null;
    const cloudRemaining=availableCredit(c)?Math.max(0,control.compute_reserve_usd??dollars(c.cloud_budget_usd)):Math.max(0,dollars(c.cloud_budget_usd)-(control.compute_used_usd||0));
    latest.compute_reserved_usd=cloudRemaining;
    let credit;
    try { credit = creditDecision(summary,c,previous?.health || {},at,cloudRemaining); }
    catch { credit = creditDecision(null,c); }
    if (rehearsalActive&&!availableCredit(c)) {
      try {
        const h=previous?.health||{}, r=h.rehearsal?.inference||{};
        const remaining=Math.max(0,dollars(c.rehearsal.inference_budget_usd)-dollars(r.committed_usd??0));
        const absolute=Math.min(dollars(credit.max_inference_committed_usd),dollars(h.inference?.committed_usd??0)+remaining);
        credit={...credit,max_inference_committed_usd:grant(absolute),max_additional_inference_usd:grant(Math.min(dollars(credit.max_additional_inference_usd),Math.max(0,dollars(c.rehearsal.inference_budget_usd)-dollars(r.reserved_usd??r.committed_usd??0))))};
        const cloudRemaining=Math.max(0,dollars(c.cloud_budget_usd)-(control.compute_used_usd||0));
        if (credit.allow&&credit.balance_usd-credit.outstanding_usd-cloudRemaining-dollars(c.credit_floor_usd)>=remaining) credit={...credit,warn:false};
        if (remaining<.1) credit={...credit,allow:false,reason:'rehearsal_budget_exhausted',warn:false};
      } catch {credit={...credit,allow:false,reason:'billing_unavailable'};}
    }
    if (!computeKnown||(availableCredit(c)&&(latest.compute_status==='unavailable'||!finite(control.compute_reserve_usd)))) credit = {...credit,allow:false,reason:'billing_unavailable',max_inference_committed_usd:'0',max_additional_inference_usd:'0'};
    latest.credit=credit;
    // One notice per funding episode. A low balance must not send a second runway email.
    const fundingIssue = credit.reason!=='rehearsal_budget_exhausted'&&(!credit.allow || (credit.warn && at>=start));
    if (fundingIssue && !control.credit_alerted && !ended && !control.paused) {
      await this.alert(c.service_id+':credit:'+(control.credit_episode||0),credit.reason==='billing_unavailable'?'billing_unavailable':credit.reason==='authorization_exhausted'?'failure':'credit_low', {...credit,reason:credit.reason});
      control.credit_alerted=true;
    } else if (!fundingIssue && control.credit_alerted) {control.credit_alerted=false;control.credit_episode=(control.credit_episode||0)+1;}
    if (control.parked && control.paused && !ended) {latest.status='paused';return save();}
    if (control.budget_parked && !ended) {latest.status='needs_attention';latest.reason_code='cloud_budget_exhausted';return save();}
    if (control.sleep_until && at < Date.parse(control.sleep_until) && !control.paused && !ended && !computeExhausted) {
      latest.status='waiting';if(credit.allow&&!latest.billing_status&&!latest.compute_status)await recovered();return save();
    }
    delete control.sleep_until;
    const stopping = ended || control.paused || computeExhausted;
    if (stopping && !control.stop_started_at) {control.stop_started_at=iso(at);await this.s.put('control',control);}
    const forceAt = ended ? end+300000 : stopping ? Date.parse(control.stop_started_at)+300000 : Infinity;
    try {
      const reason = ended?'week_complete':control.paused?'manual_pause':computeExhausted?'cloud_budget_exhausted':at<start||rehearsalGap||credit.reason==='rehearsal_budget_exhausted'?'scheduled_wait':credit.reason==='ready'?null:credit.reason==='credit_low'?'funding_needed':'recovering';
      // The guest's immutable contracts require canonical whole-second UTC.
      const admission = {schema_version:1,service_id:c.service_id,updated_at:iso(at).replace(/\.\d{3}Z$/, 'Z'),
        allow_new_research:credit.allow && !stopping && at>=start && !rehearsalGap,reason_code:reason,
        max_inference_committed_usd:credit.max_inference_committed_usd,
        max_additional_inference_usd:credit.max_additional_inference_usd,
        stop_requested:stopping && !ended};
      await this.file(c,'/workspace/config/admission.json',admission);
      const probe = await this.exec(c,['python3','/workspace/portfolio_runtime/supervisor_guest.py','probe']);
      if (probe.manifest_sha256!==c.manifest_sha256 || typeof probe.running!=='boolean' || typeof probe.boot_id!=='string' || !/^[a-zA-Z0-9-]{1,100}$/.test(probe.boot_id)) throw new Error('manifest_mismatch');
      latest.health=probe.health;latest.backup=probe.backup;
      const health=probe.health || {}, backup=probe.backup || {};
      const rehearsal=health.rehearsal, rehearsalCompleted=Date.parse(rehearsal?.completed_at);
      const rehearsalDone=!!c.rehearsal&&rehearsal?.status==='complete'&&rehearsal.starts_at===c.rehearsal.starts_at&&rehearsal.ends_at===c.rehearsal.ends_at
        &&Number.isFinite(rehearsalCompleted)&&rehearsalCompleted>=Date.parse(c.rehearsal.ends_at)&&rehearsalCompleted<=at
        &&Number(rehearsal.unsettled_requests??rehearsal.inference?.unsettled_requests??NaN)===0;
      if (rehearsalDone) await this.alert(c.service_id+':rehearsal-complete','rehearsal',{next_start_at:c.starts_at,health});
      const backupTime=Date.parse(backup.completed_at), backupAge=Number.isFinite(backupTime)?Math.max(0,at-backupTime):Infinity;
      const requestPending=Number(health.inference?.pending_requests ?? health.inference?.unsettled_requests ?? 0);
      const stopAge=stopping?at-Date.parse(control.stop_started_at):0;
      if (stopping && probe.running && !control.stop_sent && (!ended || at>=forceAt)) {
        await this.exec(c,['python3','/workspace/host-stop.py']);
        control.stop_sent=true;await this.s.put('control',control);
      }
      if (stopping) latest.status='stopping';
      else if (at<start||(rehearsalGap&&rehearsalDone)) latest.status='waiting';
      else if (!probe.running && computeKnown && !computeExhausted) {
        // Inference funding gates new requests, not accepted-ID recovery or
        // paper accounting. Their bounded host allocation is separate.
        // Intent is persisted before I/O; retry the same operation after an unknown result.
        if (!control.boot_intent || control.boot_intent.confirmed) control.boot_intent={id:c.service_id+'-boot-'+probe.boot_id+'-'+at,at:iso(at),confirmed:false};
        await this.s.put('control',control);
        await this.exec(c,'exec python3 /workspace/host-boot.py',{background:true,id:control.boot_intent.id,timeout:Math.max(60,Math.ceil((end-at)/1000)+300)});
        control.boot_intent.confirmed=true;latest.status='starting';
      } else if (probe.running) {
        const heartbeat=Date.parse(health.heartbeat_at), progress=Date.parse(health.progress_at || health.heartbeat_at);
        const progressLimit=finite(health.progress_timeout_seconds)?Math.max(300,Math.min(1800,health.progress_timeout_seconds))*1000:600000;
        const stale=!Number.isFinite(heartbeat)||heartbeat>at+60000||at-heartbeat>300000||!Number.isFinite(progress)||progress>at+60000||at-progress>progressLimit;
        if (stale) {
          control.failures=(control.failures||0)+1;latest.status='stale';
          if (control.failures>=3) {
            if (!control.recovery_started_at) {control.recovery_started_at=iso(at);await this.s.put('control',control);}
            if (at-Date.parse(control.recovery_started_at)>=120000) await this.exec(c,['python3','/workspace/portfolio_runtime/supervisor_guest.py','force-stop']);
            else await this.exec(c,['python3','/workspace/host-stop.py']);
            latest.status='recovering';
            await this.alert(c.service_id+':stale:'+iso(at).slice(0,10),'failure',{reason:'research_progress_stalled'});
          }
        } else {latest.status=health.status||'running';control.failures=0;delete control.recovery_started_at;}
      } else latest.status=credit.allow?'waiting':'needs_attention';
      if (health.reason_code && health.status==='needs_attention') await this.alert(c.service_id+':service:'+health.reason_code,'failure',{reason:health.reason_code});
      // Backups get a durable intent. An uncertain acknowledgement retries exactly
      // that operation; running jobs are never replaced with a newly minted ID.
      const stopNeedsBackup=stopping&&!probe.running&&(!Number.isFinite(backupTime)||backupTime<Date.parse(control.stop_started_at));
      const backupDue=!backup.running&&(backupAge>1800000||stopNeedsBackup);
      if (backupDue && at<forceAt) {
        if (control.backup_intent && (Number.isFinite(backupTime)&&backupTime>=Date.parse(control.backup_intent.at))) control.backup_intent=null;
        if (control.backup_intent?.confirmed && at-Date.parse(control.backup_intent.at)>900000) control.backup_intent=null;
        if (!control.backup_intent) control.backup_intent={id:c.service_id+'-backup-'+at,at:iso(at),confirmed:false};
        await this.s.put('control',control);
        await this.exec(c,'cd /workspace && exec python3 -m portfolio_runtime.supervisor_guest backup',{background:true,id:control.backup_intent.id,timeout:900});
        control.backup_intent.confirmed=true;
      }
      if (backup.status==='failed'||(backupAge>7200000&&previous?.backup)) await this.alert(c.service_id+':backup:'+iso(at).slice(0,10),'backup',{reason:'backup_unavailable'});
      const finalBackup=Number.isFinite(backupTime)&&backupTime>=Date.parse(control.stop_started_at || 0)&&!backup.running;
      if (stopping && !probe.running && finalBackup && stopAge>=120000) {
        await sleep();
        const settled=Number.isFinite(requestPending)&&requestPending===0;
        if (ended) {
          control.finished=true;latest.status=settled?'complete':'needs_attention';
          await this.alert(c.service_id+':complete',settled?'complete':'failure',{reason:settled?'week_complete':'unsettled_requests_retained',health});await this.s.deleteAlarm();
        } else if (computeExhausted) {control.budget_parked=true;latest.status='needs_attention';await this.alert(c.service_id+':cloud','failure',{reason:'cloud_budget_exhausted'});}
        else {control.parked=true;latest.status='paused';await this.alert(c.service_id+':paused','paused');}
      } else if (stopping && at>=forceAt) {
        await sleep();latest.status='needs_attention';latest.reason_code='shutdown_requires_reconciliation';
        if (ended) {control.finished=true;await this.s.deleteAlarm();}
        else if (computeExhausted) control.budget_parked=true;
        else control.parked=true;
        await this.alert(c.service_id+':forced-stop','failure',{reason:'shutdown_requires_reconciliation'});
      } else if (!stopping && !backup.running && !backupDue && (at<start || (rehearsalGap&&rehearsalDone) || (health.status==='waiting' && !rehearsalGap && requestPending===0 && Date.parse(health.next_wake_at)-at>300000))) {
        const wake=at<start?start:rehearsalGap&&rehearsalDone?weekStart:Math.min(end,Date.parse(health.next_wake_at));
        await sleep(wake);control.sleep_until=iso(wake);
      }
      if(!stopping&&credit.allow&&!latest.billing_status&&!latest.compute_status&&['waiting','running'].includes(latest.status))await recovered();
    } catch (error) {
      const reason=failureCode(error);
      await fail(reason);
      // A broken file/exec/backup API cannot prevent the independently available
      // sleep endpoint from enforcing the final stop boundary.
      if (stopping && at>=forceAt) {
        try {await sleep();if(ended){control.finished=true;await this.s.deleteAlarm();}else if(computeExhausted)control.budget_parked=true;else control.parked=true;
          await this.alert(c.service_id+':forced-stop','failure',{reason:'shutdown_requires_reconciliation'});}
        catch {await this.alert(c.service_id+':shutdown','failure',{reason:'cloud_shutdown_unconfirmed'});}
      }
    }
    return save();
  }
}
