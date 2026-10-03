// The admin log (V3-A, WP8): every kill and unkill and every call that presents the owner's token, with its time and
// the caller's kind, in /v1/health as counts and the last twenty entries; never a token; never a gate on stopping.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route } from '../lib/router.mjs';
import { createGate, ADMIN_LOG_KEY, ADMIN_SHOWN } from '../lib/gate.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-05T16:00:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const OWNER = TOKEN + '-owner';
const env = { GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: OWNER, CAP_TIMEZONE: 'America/New_York' };
const ask = (method, path, token) => new Request(GATEWAY + path, { method, headers: token ? { Authorization: `Bearer ${token}` } : {} });
const call = async (gate, method, path, token, at = NOW) => {
  const response = await route(ask(method, path, token), env, { gate, now: () => at });
  return { response, body: await response.clone().json().catch(() => null) };
};
const gateOn = store => createGate({ store, env, now: () => NOW });

test('kill and unkill are logged with the time and the caller\'s kind; the owner\'s token may also kill', async () => {
  const gate = gateOn(memoryStore());
  assert.equal((await call(gate, 'POST', '/v1/kill', TOKEN)).body.kill_switch, true);
  assert.equal((await call(gate, 'POST', '/v1/unkill', OWNER, NOW + 60000)).body.kill_switch, false);
  const killed = await call(gate, 'POST', '/v1/kill', OWNER, NOW + 120000);
  assert.equal(killed.response.status, 200);
  assert.equal(killed.body.kill_switch, true, 'stopping is never gated: the owner\'s token stops too');
  const log = killed.body.admin_log;
  assert.deepEqual(log.counts, { total: 3, kill: 2, unkill: 1, admin_token: 2, unauthorized: 0 });
  assert.deepEqual(log.last, [
    { at: '2026-10-05T16:02:00.000Z', caller: 'admin', action: 'kill', route: '/v1/kill', method: 'POST', status: 200 },
    { at: '2026-10-05T16:01:00.000Z', caller: 'admin', action: 'unkill', route: '/v1/unkill', method: 'POST', status: 200 },
    { at: '2026-10-05T16:00:00.000Z', caller: 'runtime', action: 'kill', route: '/v1/kill', method: 'POST', status: 200 },
  ]);
});

test('the owner\'s token at any other route is refused and logged; a runtime unkill is refused and logged; a stranger writes nothing', async () => {
  const gate = gateOn(memoryStore());
  for (const [method, path] of [['GET', '/v1/health'], ['POST', '/v1/alpaca/v2/orders'], ['POST', '/v1/github/merge']]) {
    assert.equal((await call(gate, method, path, OWNER)).response.status, 401, path);
  }
  assert.equal((await call(gate, 'GET', '/v1/unkill', OWNER)).response.status, 405);
  assert.equal((await call(gate, 'POST', '/v1/unkill', TOKEN)).response.status, 401);
  for (const token of [null, 'wrong', TOKEN + 'x']) {
    assert.equal((await call(gate, 'POST', '/v1/unkill', token)).response.status, 401);
    assert.equal((await call(gate, 'POST', '/v1/kill', token)).response.status, 401);
  }
  // A stranger's call anywhere else writes nothing at all.
  assert.equal((await call(gate, 'GET', '/v1/health', 'wrong')).response.status, 401);
  // Neither the runtime token's GETs nor its orders are the admin log's business.
  const health = (await call(gate, 'GET', '/v1/health', TOKEN)).body;
  assert.equal(health.kill_switch, false);
  // A stranger at the switch is never written either: the Gate serializes the orders, and a flood must not queue there.
  assert.deepEqual(health.admin_log.counts, { total: 5, kill: 0, unkill: 0, admin_token: 4, unauthorized: 0 });
  assert.deepEqual(health.admin_log.last.map(entry => [entry.caller, entry.action, entry.method, entry.route, entry.status]), [
    ['runtime', 'call', 'POST', '/v1/unkill', 401],
    ['admin', 'call', 'GET', '/v1/unkill', 405],
    ['admin', 'call', 'POST', '/v1/github/merge', 401],
    ['admin', 'call', 'POST', '/v1/alpaca/v2/orders', 401],
    ['admin', 'call', 'GET', '/v1/health', 401],
  ]);
  const text = JSON.stringify(health.admin_log);
  for (const secret of [TOKEN, OWNER, 'Bearer']) assert.equal(text.includes(secret), false, secret);
});

test('the log keeps fifty entries, shows the newest twenty, and strangers cannot push the owner\'s entries out', async () => {
  const gate = gateOn(memoryStore());
  for (let n = 0; n < 30; n += 1) await call(gate, 'POST', '/v1/kill', TOKEN, NOW + n * 1000);
  await call(gate, 'POST', '/v1/unkill', OWNER, NOW + 31000);
  for (let n = 0; n < 200; n += 1) await call(gate, 'POST', '/v1/unkill', 'wrong');
  const log = gate.adminLog();
  assert.equal(log.last.length, ADMIN_SHOWN);
  assert.equal(log.last[0].action, 'unkill', 'the owner\'s release is still the newest entry');
  assert.equal(log.counts.unauthorized, 0, 'a stranger writes nothing to the Gate');
  // A route or a method a caller sends is never written raw.
  gate.adminRecord({ caller: 'admin', action: 'call', route: '/v1/x?token=<script>\n', method: 'get\n', status: 401, at: NOW });
  assert.deepEqual(gate.adminLog().last[0], { at: '2026-10-05T16:00:00.000Z', caller: 'admin', action: 'call', route: '/v1/x?token??script??', method: '', status: 401 });
});

test('a release whose log entry cannot be written releases nothing; an engage is never held back by the log', async () => {
  const store = memoryStore();
  let broken = false;
  const failing = { get: store.get, set: (key, value) => { if (broken && key === ADMIN_LOG_KEY) throw new Error('disk'); return store.set(key, value); } };
  const gate = gateOn(failing);
  broken = true;
  const killed = await call(gate, 'POST', '/v1/kill', TOKEN);
  assert.equal(killed.response.status, 200);
  assert.equal(killed.body.kill_switch, true, 'the switch is engaged though its entry was not written');
  const release = await call(gate, 'POST', '/v1/unkill', OWNER);
  assert.equal(release.response.status, 503);
  assert.equal(release.body.cap, 'setup');
  assert.equal(gate.status(NOW).kill_switch, true, 'still engaged');
  broken = false;
  assert.equal((await call(gate, 'POST', '/v1/unkill', OWNER)).body.kill_switch, false);
  assert.equal(gate.adminLog().counts.unkill, 1);
});

test('a malformed admin-log or autonomy row is its own block\'s error, never a failed /v1/health', async () => {
  for (const key of [ADMIN_LOG_KEY, 'github-merges-v1', 'github-docs-v1', 'github-reviews-v1']) {
    const store = memoryStore({ [key]: JSON.stringify({ counts: 7, entries: 'x', recent: 5, day: {}, count: 'NaN', next: [], ...(key === 'github-reviews-v1' ? { entries: 5 } : {}) }) });
    const gate = gateOn(store);
    const health = await call(gate, 'GET', '/v1/health', TOKEN);
    assert.equal(health.response.status, 200, key);
    assert.equal(health.body.kill_switch, false, key);
    assert.ok(health.body.admin_log && health.body.autonomy, key);
  }
  const throwing = gateOn(memoryStore());
  throwing.adminLog = () => { throw new Error('boom'); };
  throwing.autonomyStatus = () => { throw new Error('boom'); };
  const status = throwing.status(NOW);
  assert.deepEqual(status.admin_log, { error: 'admin log status unreadable' });
  assert.deepEqual(status.autonomy, { error: 'autonomy status unreadable' });
});
