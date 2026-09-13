// Fixed cloud operations only. Agent outputs cannot supply commands or authority.
export const API = 'https://sailbox-api.sailresearch.com';
export const INFERENCE = 'https://api.sailresearch.com';
const iso = ms => new Date(ms).toISOString();
const finite = v => typeof v === 'number' && Number.isFinite(v) && v >= 0;
export const dollars = value => { if (typeof value !== 'number' && (typeof value !== 'string' || !/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value))) throw new Error('invalid_money'); const n = Number(value); if (!finite(n)) throw new Error('invalid_money'); return n; };
const grant = value => (Math.floor(Math.max(0,value) * 1e8) / 1e8).toFixed(8);
export function validateConfig(c) {
  if (!c || c.schema_version !== 1 || !/^[a-z0-9-]{8,64}$/.test(c.service_id || '')
    || !/^sb_[0-9a-f-]{36}$/.test(c.box_id || '') || !/^[a-f0-9]{64}$/.test(c.manifest_sha256 || '')) throw new Error('invalid_config');
  const start = Date.parse(c.starts_at), end = Date.parse(c.ends_at);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || end - start > 8 * 86400000) throw new Error('invalid_window');
  for (const name of ['weekly_total_usd','weekly_inference_usd','cloud_budget_usd','credit_floor_usd']) dollars(c[name]);
  if (dollars(c.weekly_total_usd) <= 0 || dollars(c.weekly_total_usd) > 10000
    || dollars(c.weekly_inference_usd) + dollars(c.cloud_budget_usd) > dollars(c.weekly_total_usd)
    || dollars(c.credit_floor_usd) < 1) throw new Error('invalid_budget');
  if (Object.keys(c).some(k => !['schema_version','service_id','box_id','manifest_sha256','starts_at','ends_at',
    'weekly_total_usd','weekly_inference_usd','cloud_budget_usd','credit_floor_usd'].includes(k))) throw new Error('unknown_config');
  return c;
}
export function creditDecision(summary, c, health = {}, at = Date.now(), cloudRemaining = 0) {
  if (!summary || summary.balance_unavailable || summary.has_metronome_customer !== true || !finite(summary.balance)) return {allow:false, reason:'billing_unavailable', max_inference_committed_usd:'0', max_additional_inference_usd:'0'};
  const balance = summary.balance / 100; // Sail billing fields are fractional US cents.
  const committed = dollars(health.inference?.committed_usd ?? health.inference_committed_usd ?? 0);
  const reserved = Math.max(committed, dollars(health.inference?.reserved_usd ?? committed));
  const known = dollars(health.inference?.known_cost_usd ?? health.inference_known_usd ?? 0);
  const outstanding = Math.max(0, committed - known);
  const absolute = Math.max(0, Math.min(dollars(c.weekly_inference_usd), known + balance - dollars(c.credit_floor_usd) - dollars(cloudRemaining)));
  const usable = Math.max(0, absolute - reserved);
  const requestRoom = Math.max(0, absolute - committed);
  const hours = Math.max(1, (Date.parse(c.ends_at) - Math.max(at, Date.parse(c.starts_at))) / 3600000);
  // A technical ceiling is not a forecast of purposeful spending. Use the
  // guest's current evaluated research intensity when it is available.
  const proposedRate = health.funding?.planned_inference_usd_per_day;
  const plannedPerDay = finite(proposedRate) ? Math.min(proposedRate, Math.max(0, dollars(c.weekly_inference_usd) - reserved) / hours * 24)
    : Math.min(24, Math.max(0, dollars(c.weekly_inference_usd) - reserved) / hours * 24);
  const measuredPerDay = finite(summary.avg_cost_per_day) ? summary.avg_cost_per_day / 100 : 0;
  const burn = Math.max(plannedPerDay, measuredPerDay);
  const runway = burn > 0 ? Math.max(0, balance - outstanding - dollars(c.credit_floor_usd) - cloudRemaining) / burn : null;
  const exhausted = dollars(c.weekly_inference_usd) - committed < .1;
  return {allow:requestRoom >= .1, reason:requestRoom >= .1 ? 'ready' : exhausted ? 'authorization_exhausted' : 'credit_low', balance_usd:balance,
    outstanding_usd:outstanding, usable_usd:usable, runway_days:runway,
    max_inference_committed_usd:grant(absolute), max_additional_inference_usd:grant(usable),
    warn:requestRoom < .1 || (runway !== null && runway < 2)};
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
    const r = await this.fetcher(base + path, {...options, redirect:'error', signal:AbortSignal.timeout(45000),
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
      complete:'Portfolio week complete',paused:'Portfolio service paused'};
    const lines = [titles[kind] + '.', ''];
    if (details.reason && /^[a-z0-9_]{1,64}$/.test(details.reason)) lines.push('Reason: ' + details.reason + '.');
    if (finite(details.balance_usd)) lines.push('Sail balance: $' + details.balance_usd.toFixed(2) + '.');
    if (finite(details.runway_days)) lines.push('Estimated research runway: ' + details.runway_days.toFixed(1) + ' days.');
    if (kind === 'credit_low') lines.push('Add Sail credit to keep research running. The service detects funding automatically; no restart is needed: https://app.sailresearch.com/');
    if (kind === 'complete' && details.health?.inference) {
      const totals = details.health.inference;
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
    const latest = {as_of:iso(at),service_id:c.service_id,health:previous?.health,backup:previous?.backup};
    const start = Date.parse(c.starts_at), end = Date.parse(c.ends_at), ended = at >= end;
    const save = async () => { await this.s.put('control',control); await this.s.put('latest',latest); return latest; };
    const sleep = async wake => this.json('/v1/sailboxes/'+c.box_id+'/sleep',{method:'POST',body:JSON.stringify(wake ? {wake_at:iso(wake)} : {})});
    const fail = async reason => { control.failures=(control.failures||0)+1;latest.status='needs_attention';latest.reason_code=reason;
      if (control.failures>=3) await this.alert(c.service_id+':failure:'+iso(at).slice(0,10),'failure',{reason}); };
    // Billing outages revoke admission; they never prevent stop, backup or cleanup.
    let summary = null;
    try { summary = await this.json('/v2/usage/summary?range=7d',{},INFERENCE); }
    catch { latest.billing_status='unavailable'; }
    if (!control.spend_checked_at || at-control.spend_checked_at >= 3600000) {
      try {
        const usage = await this.json('/v1/sailboxes/spend?sailbox_id='+c.box_id);
        const row = usage.sailboxes?.find(box => box.sailbox_id===c.box_id);
        const nanos = row?.estimated_total_cost_usd_nanos;
        if (usage.pricing_configured !== true || !finite(nanos)) throw new Error('compute_spend_unavailable');
        control.compute_used_usd = Math.max(control.compute_used_usd || 0,nanos/1e9);
        control.spend_checked_at=at;
      } catch { latest.compute_status='unavailable'; }
    }
    const computeKnown = control.spend_checked_at !== undefined;
    const computeExhausted = computeKnown && control.compute_used_usd >= dollars(c.cloud_budget_usd);
    latest.compute_used_usd=control.compute_used_usd ?? null;
    let credit;
    try { credit = creditDecision(summary,c,previous?.health || {},at,Math.max(0,dollars(c.cloud_budget_usd)-(control.compute_used_usd||0))); }
    catch { credit = creditDecision(null,c); }
    if (!computeKnown) credit = {...credit,allow:false,reason:'billing_unavailable'};
    latest.credit=credit;
    // One notice per funding episode. A low balance must not send a second runway email.
    const fundingIssue = !credit.allow || credit.warn;
    if (fundingIssue && !control.credit_alerted && !ended && !control.paused) {
      await this.alert(c.service_id+':credit:'+(control.credit_episode||0),credit.reason==='billing_unavailable'?'billing_unavailable':credit.reason==='authorization_exhausted'?'failure':'credit_low', {...credit,reason:credit.reason});
      control.credit_alerted=true;
    } else if (!fundingIssue && control.credit_alerted) {control.credit_alerted=false;control.credit_episode=(control.credit_episode||0)+1;}
    if (control.parked && control.paused && !ended) {latest.status='paused';return save();}
    if (control.budget_parked && !ended) {latest.status='needs_attention';latest.reason_code='cloud_budget_exhausted';return save();}
    if (control.sleep_until && at < Date.parse(control.sleep_until) && !control.paused && !ended && !computeExhausted) {
      latest.status='waiting';return save();
    }
    delete control.sleep_until;
    const stopping = ended || control.paused || computeExhausted;
    if (stopping && !control.stop_started_at) {control.stop_started_at=iso(at);await this.s.put('control',control);}
    const forceAt = ended ? end+300000 : stopping ? Date.parse(control.stop_started_at)+300000 : Infinity;
    try {
      const reason = ended?'week_complete':control.paused?'manual_pause':computeExhausted?'cloud_budget_exhausted':at<start?'scheduled_wait':credit.reason==='ready'?null:credit.reason==='credit_low'?'funding_needed':'recovering';
      const admission = {schema_version:1,service_id:c.service_id,updated_at:iso(at),
        allow_new_research:credit.allow && !stopping && at>=start,reason_code:reason,
        max_inference_committed_usd:credit.max_inference_committed_usd,
        max_additional_inference_usd:credit.max_additional_inference_usd,
        stop_requested:stopping && !ended};
      await this.file(c,'/workspace/config/admission.json',admission);
      const probe = await this.exec(c,['python3','/workspace/portfolio_runtime/supervisor_guest.py','probe']);
      if (probe.manifest_sha256!==c.manifest_sha256 || typeof probe.running!=='boolean' || typeof probe.boot_id!=='string' || !/^[a-zA-Z0-9-]{1,100}$/.test(probe.boot_id)) throw new Error('manifest_mismatch');
      latest.health=probe.health;latest.backup=probe.backup;
      const health=probe.health || {}, backup=probe.backup || {};
      const backupTime=Date.parse(backup.completed_at), backupAge=Number.isFinite(backupTime)?Math.max(0,at-backupTime):Infinity;
      const requestPending=Number(health.inference?.pending_requests ?? health.inference?.unsettled_requests ?? 0);
      const stopAge=stopping?at-Date.parse(control.stop_started_at):0;
      if (stopping && probe.running && !control.stop_sent && (!ended || at>=forceAt)) {
        await this.exec(c,['python3','/workspace/host-stop.py']);
        control.stop_sent=true;await this.s.put('control',control);
      }
      if (stopping) latest.status='stopping';
      else if (at<start) latest.status='waiting';
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
      } else if (!stopping && !backup.running && !backupDue && (at<start || (health.status==='waiting' && Date.parse(health.next_wake_at)-at>300000))) {
        const wake=at<start?start:Math.min(end,Date.parse(health.next_wake_at));
        await sleep(wake);control.sleep_until=iso(wake);
      }
    } catch (error) {
      const reason=/^[a-z0-9_]{1,64}$/.test(error?.message||'')?error.message:'supervisor_failure';
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
