// The supervisor pass: what it looks at, what it fixes by itself, and the six things that are
// allowed to reach the owner's inbox.

import assert from 'node:assert/strict';
import test from 'node:test';

import { runWatchdog } from '../lib/watchdog.mjs';
import { createGate } from '../lib/gate.mjs';
import { compose, mime, encodeHeader, ALERT_KINDS } from '../lib/email.mjs';
import { memoryStore } from './helpers.mjs';

const NOW = Date.parse('2026-09-15T16:00:00Z');
const BOX = 'sb_00000000-0000-0000-0000-000000000000';
const CHECKPOINT = 'https://blakewoods.us/api/capital/checkpoint';

const ENV = {
  SAIL_API_KEY: 'sail-secret', SAILBOX_ID: BOX, CHECKPOINT_URL: CHECKPOINT,
  MAX_ORDER_USD: '50', MAX_DAY_USD: '400', MAX_DAY_ORDERS: '60',
};

const gateWith = (env = ENV, now = NOW) => createGate({ store: memoryStore(), env, now: () => now });

const reply = (body, status = 200) =>
  new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  });

const checkpointBody = (at, agoSeconds) => ({
  published_at: new Date(at - agoSeconds * 1000).toISOString(),
  floor: { equity: '4999.97', daily_pnl: '-12.50', cash: '4999.97' },
});

/** A `fetch` for the whole control plane: checkpoint, usage, box, resume and exec. */
function cloud({ ago = 60, balanceCents = 12000, status = 'running', resumeState = 'running', execOk = true } = {}) {
  const calls = [];
  // The published checkpoint ages with the clock the pass is run at, the way the real one does.
  let at = NOW;
  const fetcher = async (url, options = {}) => {
    calls.push({ url: String(url), method: options.method || 'GET', headers: options.headers || {}, body: options.body });
    const href = String(url);
    if (href.startsWith(CHECKPOINT)) return reply(checkpointBody(at, ago));
    if (href.includes('/v2/usage/summary')) return reply({ balance: balanceCents, period_spend: 412.5, range: '24h' });
    if (href.endsWith('/resume')) return reply({ sailbox_id: BOX, status: 'running', resume_state: resumeState });
    if (href.endsWith('/exec')) {
      return reply(execOk
        ? '{"type":"started","exec_request_id":"exec_9"}\n{"type":"exit","return_code":0}\n'
        : '{"type":"error","error_code":"permission_denied"}\n');
    }
    if (/\/v1\/sailboxes\/[^/]+$/.test(href)) return reply({ sailbox_id: BOX, status });
    return reply({}, 404);
  };
  return { fetcher, calls, at: value => { at = value; } };
}

function recorder() {
  const sent = [];
  return { sent, mailer: async message => void sent.push(message) };
}

test('a fresh checkpoint on a running box is left alone', async () => {
  const gate = gateWith();
  const { fetcher, calls } = cloud({ ago: 60 });
  const { mailer, sent } = recorder();
  const result = await runWatchdog({ gate, env: ENV, fetcher, mailer, now: NOW });
  assert.equal(result.action, 'ok');
  assert.equal(result.age_seconds, 60);
  assert.equal(sent.length, 0);
  assert.equal(calls.some(call => call.url.endsWith('/exec')), false);
  const status = gate.status(NOW);
  assert.equal(status.watchdog.last_action, 'ok');
  assert.equal(status.watchdog.last_check_at, '2026-09-15T16:00:00.000Z');
  assert.equal(status.sail.balance_usd, 120);
  assert.equal(status.sail.box_status, 'running');
});

test('Sail reports money in fractional cents, so 3106.14 is $31.06', async () => {
  const gate = gateWith();
  const { fetcher } = cloud({ balanceCents: 3106.14 });
  const { mailer, sent } = recorder();
  await runWatchdog({ gate, env: ENV, fetcher, mailer, now: NOW });
  assert.equal(gate.status(NOW).sail.balance_usd, 31.0614);
  // $21.06 above the reserve at $4.13 a day is five days of runway: the first, gentle warning.
  assert.equal(sent[0].subject, 'LTCM: 5.1 days of Sail credit left \u2014 top up when you can');
  assert.match(sent[0].text, /credit lasts 5\.1 days, to about 2026-09-20 /);
  assert.match(sent[0].text, /There is no daily cap/);
});

test('a checkpoint older than fifteen minutes restarts the box, once', async () => {
  const gate = gateWith();
  const { fetcher, calls, at } = cloud({ ago: 1200 });
  const first = await runWatchdog({ gate, env: ENV, fetcher, now: NOW });
  assert.equal(first.action, 'restarted');
  const exec = calls.find(call => call.url.endsWith('/exec'));
  assert.equal(exec.url, `https://sailbox-api.sailresearch.com/v1/sailboxes/${BOX}/exec`);
  assert.deepEqual(JSON.parse(exec.body), {
    command: ['sh', '-c', '/workspace/restart.sh'], timeout: 120, background: true,
    idempotency_key: `exec:ltcm-recover:${BOX}:${Math.floor(NOW / 1800000)}`,
  });
  assert.equal(exec.headers.Authorization, 'Bearer sail-secret');

  // Five minutes later the box has not published yet: the cooldown holds the second restart back.
  at(NOW + 300000);
  const later = await runWatchdog({ gate, env: ENV, fetcher, now: NOW + 300000 });
  assert.equal(later.action, 'cooldown');
  assert.equal(calls.filter(call => call.url.endsWith('/exec')).length, 1);

  // Thirty-one minutes later it may try again.
  at(NOW + 1860000);
  const again = await runWatchdog({ gate, env: ENV, fetcher, now: NOW + 1860000 });
  assert.equal(again.action, 'restarted');
});

test('the first stale pass restarts without mailing; a restart that did not help is mailed', async () => {
  const gate = gateWith();
  const { fetcher, at } = cloud({ ago: 1200 });
  const { mailer, sent } = recorder();
  const first = await runWatchdog({ gate, env: ENV, fetcher, mailer, now: NOW });
  assert.equal(first.action, 'restarted');
  assert.deepEqual(sent, [], 'a deploy or a fresh start must not page the owner');

  // Five minutes on, the floor has still not published: now the owner hears about it.
  at(NOW + 300000);
  const later = await runWatchdog({ gate, env: ENV, fetcher, mailer, now: NOW + 300000 });
  assert.equal(later.action, 'cooldown');
  assert.deepEqual(sent.map(message => message.subject), ['LTCM: the desks are not running']);
});

test('a restart that the box refused is mailed at once', async () => {
  const gate = gateWith();
  const { fetcher } = cloud({ ago: 1200, execOk: false });
  const { mailer, sent } = recorder();
  const result = await runWatchdog({ gate, env: ENV, fetcher, mailer, now: NOW });
  assert.equal(result.action, 'restart_failed');
  assert.deepEqual(sent.map(message => message.subject), ['LTCM: the desks are not running']);
});

test('a paused box with credit behind it is resumed and restarted, with no human step', async () => {
  const gate = gateWith();
  const { fetcher, calls } = cloud({ ago: 60, status: 'paused', balanceCents: 12000 });
  const result = await runWatchdog({ gate, env: ENV, fetcher, now: NOW });
  assert.equal(result.action, 'resumed');
  const resume = calls.find(call => call.url.endsWith('/resume'));
  assert.equal(resume.method, 'POST');
  assert.match(resume.headers['Idempotency-Key'], /^resume:ltcm-recover:/);
  assert.equal(calls.filter(call => call.url.endsWith('/exec')).length, 1, 'resume is followed by the restart');
  assert.equal(gate.status(NOW).sail.last_resume_state, 'running');
});

test('a paused box under the reserve is left paused and the owner is told', async () => {
  const gate = gateWith();
  const { fetcher, calls } = cloud({ ago: 60, status: 'paused', balanceCents: 800 });
  const { mailer, sent } = recorder();
  const result = await runWatchdog({ gate, env: ENV, fetcher, mailer, now: NOW });
  assert.equal(result.action, 'stopped_low_balance');
  assert.equal(calls.some(call => call.url.endsWith('/resume')), false);
  assert.deepEqual(sent.map(message => message.subject), [
    'LTCM: the desks have stopped — Sail credit is at the reserve',
    'LTCM: the desks are not running',
  ]);
});

test('a paused box with credit above the reserve is resumed even when the credit is short', async () => {
  // The floor throttles itself above the reserve; a stopped box would only forfeit the runway.
  const gate = gateWith();
  const { fetcher, calls } = cloud({ ago: 60, status: 'paused', balanceCents: 1500 });
  const result = await runWatchdog({ gate, env: ENV, fetcher, now: NOW });
  assert.equal(result.action, 'resumed');
  assert.equal(calls.some(call => call.url.endsWith('/resume')), true);
});

test('a floor that reports itself stopped is mailed as stopped, whatever the balance', async () => {
  const gate = gateWith();
  const { mailer, sent } = recorder();
  const { fetcher } = cloud();
  const stoppedFloor = async (url, options) => {
    if (String(url).startsWith(CHECKPOINT)) return reply({ ...checkpointBody(NOW, 60), budget: { spent_today_usd: '0', cap_usd: '0', mode: 'stopped' } });
    return fetcher(url, options);
  };
  await runWatchdog({ gate, env: ENV, fetcher: stoppedFloor, mailer, now: NOW });
  assert.deepEqual(sent.map(message => message.subject), ['LTCM: the desks have stopped — Sail credit is at the reserve']);
});

test('a terminated box is never resumed', async () => {
  const gate = gateWith();
  const { fetcher, calls } = cloud({ ago: 60, status: 'terminated' });
  const result = await runWatchdog({ gate, env: ENV, fetcher, now: NOW });
  assert.equal(result.action, 'box_unrecoverable');
  assert.equal(calls.some(call => call.url.endsWith('/resume') || call.url.endsWith('/exec')), false);
});

test('a resume that does not take is reported, and no restart is attempted on a dead box', async () => {
  const gate = gateWith();
  const { fetcher, calls } = cloud({ ago: 60, status: 'sleeping', resumeState: 'terminal_unavailable' });
  const result = await runWatchdog({ gate, env: ENV, fetcher, now: NOW });
  assert.equal(result.action, 'resume_failed');
  assert.equal(result.detail, 'terminal_unavailable');
  assert.equal(calls.some(call => call.url.endsWith('/exec')), false);
});

test('an exec that never confirms is a restart_failed, and still opens the cooldown', async () => {
  const gate = gateWith();
  const { fetcher } = cloud({ ago: 1200, execOk: false });
  const result = await runWatchdog({ gate, env: ENV, fetcher, now: NOW });
  assert.equal(result.action, 'restart_failed');
  assert.equal(result.detail, 'permission_denied');
  assert.equal(gate.watchdog().last_restart_at, '2026-09-15T16:00:00.000Z');
});

test('with no Sailbox configured the watchdog reports and does nothing else', async () => {
  const gate = gateWith({ ...ENV, SAILBOX_ID: '' });
  const { fetcher, calls } = cloud({ ago: 1200 });
  const result = await runWatchdog({ gate, env: { ...ENV, SAILBOX_ID: '' }, fetcher, now: NOW });
  assert.equal(result.action, 'stale_no_sailbox');
  assert.equal(calls.some(call => call.url.includes('/v1/sailboxes/')), false);
});

test('an unreachable checkpoint is recorded, not guessed at', async () => {
  const gate = gateWith();
  const down = { fetcher: async url => (String(url).startsWith(CHECKPOINT) ? reply({ error: 'no' }, 503) : reply({})) };
  assert.equal((await runWatchdog({ gate, env: ENV, fetcher: down.fetcher, now: NOW })).action, 'checkpoint_unreachable');
  const garbage = { fetcher: async url => (String(url).startsWith(CHECKPOINT) ? reply('not json') : reply({})) };
  assert.equal((await runWatchdog({ gate, env: ENV, fetcher: garbage.fetcher, now: NOW })).action, 'checkpoint_unreadable');
  const undated = { fetcher: async url => (String(url).startsWith(CHECKPOINT) ? reply({ floor: {} }) : reply({})) };
  assert.equal((await runWatchdog({ gate, env: ENV, fetcher: undated.fetcher, now: NOW })).action, 'checkpoint_unreadable');
});

test('a balance under the floor warns once, and under the critical line warns differently', async () => {
  const gate = gateWith();
  const { mailer, sent } = recorder();
  const low = cloud({ balanceCents: 4500 });
  await runWatchdog({ gate, env: ENV, fetcher: low.fetcher, mailer, now: NOW });
  assert.equal(sent.length, 1);
  // $35 above the reserve at $4.13 a day: eight days of runway, but under the $60 floor.
  assert.match(sent[0].subject, /8\.5 days of Sail credit left/);
  assert.match(sent[0].text, /Sail credit: \$45\.00; \$35\.00 of it is above the \$10\.00 reserve/);

  // Inside six hours, nothing more.
  low.at(NOW + 3600000);
  await runWatchdog({ gate, env: ENV, fetcher: low.fetcher, mailer, now: NOW + 3600000 });
  assert.equal(sent.length, 1);

  // The critical warning is its own kind, so it is not suppressed by the low one.
  const critical = cloud({ balanceCents: 1500 });
  critical.at(NOW + 3600000);
  await runWatchdog({ gate, env: ENV, fetcher: critical.fetcher, mailer, now: NOW + 3600000 });
  assert.equal(sent.length, 2);
  assert.match(sent[1].subject, /1\.2 days of Sail credit left — top up now/);
  assert.match(sent[1].text, /last warning before the floor throttles/);
});

test('the kill switch and exhausted caps each raise their own alert', async () => {
  const gate = gateWith();
  const { mailer, sent } = recorder();
  gate.setKill(true, NOW);
  for (let i = 0; i < 60; i += 1) gate.setKill(false, NOW), gate.reserve({ micro: '1000000' });
  gate.setKill(true, NOW);
  const { fetcher } = cloud();
  await runWatchdog({ gate, env: ENV, fetcher, mailer, now: NOW });
  assert.deepEqual(sent.map(message => message.subject), [
    'LTCM: the order gateway kill switch is engaged',
    "LTCM: today's order caps are used up",
  ]);
  assert.match(sent[1].text, /60 orders for \$60\.00 today/);
});

test('the digest goes out in the 21:00 UTC hour and carries the floor s own numbers', async () => {
  const gate = gateWith();
  const { mailer, sent } = recorder();
  const { fetcher, at } = cloud();
  const evening = Date.parse('2026-09-15T21:02:00Z');
  at(evening);
  await runWatchdog({ gate, env: ENV, fetcher, mailer, now: evening });
  assert.equal(sent.length, 1);
  assert.equal(sent[0].subject, 'LTCM daily: equity $4999.97, day P&L -$12.50');
  assert.match(sent[0].text, /Sail balance: \$120\.00; spend over 24h: \$4\.13; runway 26 days\./);
  assert.match(sent[0].text, /Box: running\. Kill switch: open\./);
  // The next tick five minutes later is inside the window, so it stays quiet.
  at(evening + 300000);
  await runWatchdog({ gate, env: ENV, fetcher, mailer, now: evening + 300000 });
  assert.equal(sent.length, 1);
});

test('a mail failure never takes the pass down', async () => {
  const gate = gateWith();
  const { fetcher } = cloud({ balanceCents: 100 });
  const angry = async () => {
    throw new Error('mail is down');
  };
  const result = await runWatchdog({ gate, env: ENV, fetcher, mailer: angry, now: NOW });
  assert.equal(result.action, 'ok');
  assert.deepEqual(gate.alerts(), {}, 'an alert that did not send is not recorded as sent');
  assert.equal(gate.watchdog().last_mail_error, 'Error');
});

test('with no mail binding the pass still runs and still records what it did', async () => {
  const gate = gateWith();
  const { fetcher } = cloud({ ago: 1200 });
  const result = await runWatchdog({ gate, env: ENV, fetcher, mailer: null, now: NOW });
  assert.equal(result.action, 'restarted');
  assert.deepEqual(result.alerts, []);
});

test('every alert composes a subject and a body, and nothing else does', () => {
  for (const kind of ALERT_KINDS) {
    const message = compose(kind, { balance_usd: 12, equity_usd: 100, daily_pnl_usd: 1, orders: 1, notional_usd: 2 });
    assert.ok(message.subject.startsWith('LTCM'), kind);
    assert.ok(message.text.includes('https://blakewoods.us/capital/'), kind);
  }
  assert.equal(compose('something_else', {}), null);
});

test('the MIME envelope is well formed and carries a non-ASCII subject safely', () => {
  const body = mime({
    subject: 'LTCM: Sail balance $15.00 — top up', text: 'line one\nline two\n',
    at: Date.parse('2026-09-15T16:00:00Z'), id: 'fixed',
  });
  assert.match(body, /^From: Long Term Capital Management <agent@blakewoods\.us>\r\n/);
  assert.match(body, /\r\nTo: <blakewoods98@gmail\.com>\r\n/);
  assert.match(body, /\r\nSubject: =\?UTF-8\?B\?[A-Za-z0-9+/=]+\?=\r\n/);
  assert.match(body, /\r\nMessage-ID: <fixed@blakewoods\.us>\r\n/);
  assert.match(body, /\r\nDate: Tue, 15 Sep 2026 16:00:00 \+0000\r\n/);
  assert.match(body, /\r\nContent-Transfer-Encoding: base64\r\n\r\n/);
  const [, encoded] = body.split('\r\n\r\n');
  assert.equal(Buffer.from(encoded.trim(), 'base64').toString('utf8'), 'line one\nline two\n');
  assert.equal(encodeHeader('plain ascii'), 'plain ascii');
});
