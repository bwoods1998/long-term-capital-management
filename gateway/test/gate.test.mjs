// The caps themselves: what is spent, what is refused, and how a day rolls over.

import assert from 'node:assert/strict';
import test from 'node:test';

import { createGate, tradingDay } from '../lib/gate.mjs';
import { memoryStore } from './helpers.mjs';

const ENV = { MAX_ORDER_USD: '50', MAX_DAY_USD: '400', MAX_DAY_ORDERS: '60', CAP_TIMEZONE: 'America/New_York' };
const NOON = Date.parse('2026-09-15T16:00:00Z'); // noon in New York
const usd = dollars => String(BigInt(Math.round(dollars * 100)) * 10000n);

const build = (env = ENV, at = NOON) => createGate({ store: memoryStore(), env, now: () => at });

test('an order inside every cap is reserved and counted', () => {
  const gate = build();
  const decision = gate.reserve({ micro: usd(12.5) });
  assert.equal(decision.ok, true);
  assert.equal(decision.day, '2026-09-15');
  const status = gate.status();
  assert.deepEqual(status.today, { day: '2026-09-15', orders: 1, notional_usd: '12.50' });
  assert.deepEqual(status.caps, {
    max_order_usd: '50.00', max_day_usd: '400.00', max_day_orders: 60, timezone: 'America/New_York',
  });
  assert.equal(status.kill_switch, false);
  assert.deepEqual(status.watchdog, {
    last_check_at: null, last_action: null, last_action_at: null,
    last_restart_at: null, published_at: null, age_seconds: null,
  });
  assert.equal(status.caps_exhausted, false);
  assert.deepEqual(status.alerts, {});
  assert.equal(status.sail.balance_usd, null);
});

test('the per-order cap refuses one large order without spending the day', () => {
  const gate = build();
  const decision = gate.reserve({ micro: usd(50.01) });
  assert.equal(decision.ok, false);
  assert.equal(decision.status, 403);
  assert.equal(decision.cap, 'order');
  assert.match(decision.error, /\$50\.01 exceeds the per-order cap of \$50\.00/);
  assert.equal(gate.status().today.orders, 0);
  // Exactly at the cap is allowed; a cap is a ceiling, not a fence.
  assert.equal(gate.reserve({ micro: usd(50) }).ok, true);
});

test('the daily notional cap stops the order that would pass it, not the one that reached it', () => {
  const gate = build();
  for (let i = 0; i < 8; i += 1) assert.equal(gate.reserve({ micro: usd(50) }).ok, true);
  assert.equal(gate.status().today.notional_usd, '400.00');
  const refused = gate.reserve({ micro: usd(0.01) });
  assert.equal(refused.status, 403);
  assert.equal(refused.cap, 'day_notional');
  assert.match(refused.error, /already \$400\.00/);
});

test('the daily order count cap is independent of notional', () => {
  const gate = build({ ...ENV, MAX_DAY_ORDERS: '3' });
  for (let i = 0; i < 3; i += 1) assert.equal(gate.reserve({ micro: usd(1) }).ok, true);
  const refused = gate.reserve({ micro: usd(1) });
  assert.equal(refused.cap, 'day_orders');
  assert.match(refused.error, /count cap of 3/);
  assert.equal(gate.status().today.notional_usd, '3.00');
});

test('the kill switch refuses every order with 423 and survives a read of the status', () => {
  const gate = build();
  assert.deepEqual(gate.setKill(true, NOON), { on: true, at: '2026-09-15T16:00:00.000Z' });
  const refused = gate.reserve({ micro: usd(1) });
  assert.equal(refused.status, 423);
  assert.match(refused.error, /kill switch is engaged/);
  assert.equal(gate.status().kill_switch, true);
  gate.setKill(false, NOON);
  assert.equal(gate.reserve({ micro: usd(1) }).ok, true);
  assert.equal(gate.status().kill_switch, false);
});

test('a new trading day starts at zero and never inherits yesterday', () => {
  const store = memoryStore();
  let at = NOON;
  const gate = createGate({ store, env: ENV, now: () => at });
  gate.reserve({ micro: usd(40) });
  assert.equal(gate.status().today.notional_usd, '40.00');
  at = Date.parse('2026-09-16T16:00:00Z');
  assert.deepEqual(gate.status().today, { day: '2026-09-16', orders: 0, notional_usd: '0.00' });
  assert.equal(gate.reserve({ micro: usd(50) }).ok, true);
  assert.equal(gate.status().today.notional_usd, '50.00');
});

test('the day rolls on the floor s own clock, not UTC', () => {
  // 01:00 UTC on the 16th is still the evening of the 15th in New York.
  assert.equal(tradingDay(Date.parse('2026-09-16T01:00:00Z'), 'America/New_York'), '2026-09-15');
  assert.equal(tradingDay(Date.parse('2026-09-16T01:00:00Z'), 'UTC'), '2026-09-16');
  assert.equal(tradingDay(Date.parse('2026-09-16T01:00:00Z'), 'Not/AZone'), '2026-09-16');
});

test('a reservation is given back only when the order never left', () => {
  const gate = build();
  const reservation = gate.reserve({ micro: usd(30) });
  assert.equal(gate.refund(reservation).ok, true);
  assert.deepEqual(gate.status().today, { day: '2026-09-15', orders: 0, notional_usd: '0.00' });
  // A refund aimed at another day changes nothing.
  gate.reserve({ micro: usd(30) });
  assert.equal(gate.refund({ day: '2026-01-01', micro: usd(30) }).ok, false);
  assert.equal(gate.status().today.notional_usd, '30.00');
});

test('an order with no notional is refused before it can be counted', () => {
  const gate = build();
  const refused = gate.reserve({ micro: '0' });
  assert.equal(refused.status, 400);
  assert.equal(gate.status().today.orders, 0);
});

test('the watchdog record is readable through the same object', () => {
  const gate = build();
  gate.recordWatchdog({ last_check_at: 'a', last_action: 'ok', last_action_at: 'a' });
  gate.recordWatchdog({ last_restart_at: 'b' });
  assert.equal(gate.watchdog().last_restart_at, 'b');
  assert.equal(gate.status().watchdog.last_action, 'ok');
  assert.equal(gate.status().watchdog.last_restart_at, 'b');
});

test('an alert of one kind is due again only after its window', () => {
  const gate = build();
  const hour = 3600000;
  assert.equal(gate.alertDue('sail_balance_low', NOON, 6 * hour), true);
  gate.recordAlert('sail_balance_low', NOON);
  assert.equal(gate.alertDue('sail_balance_low', NOON + 5 * hour, 6 * hour), false);
  assert.equal(gate.alertDue('sail_balance_low', NOON + 6 * hour, 6 * hour), true);
  // Kinds are independent: a balance warning does not silence a kill-switch one.
  assert.equal(gate.alertDue('kill_switch_engaged', NOON, 6 * hour), true);
  assert.equal(gate.status().alerts.sail_balance_low.at, '2026-09-15T16:00:00.000Z');
});

test('caps_exhausted turns true when either daily cap is reached', () => {
  const byCount = build({ ...ENV, MAX_DAY_ORDERS: '2' });
  assert.equal(byCount.capsExhausted(NOON), false);
  byCount.reserve({ micro: usd(1) });
  byCount.reserve({ micro: usd(1) });
  assert.equal(byCount.capsExhausted(NOON), true);
  assert.equal(byCount.status().caps_exhausted, true);

  const byNotional = build({ ...ENV, MAX_DAY_USD: '50' });
  byNotional.reserve({ micro: usd(50) });
  assert.equal(byNotional.capsExhausted(NOON), true);
});

test('what the last pass learned about Sail is readable from the status', () => {
  const gate = build();
  gate.recordSail({ checked_at: 'now', balance_usd: 31.06, box_status: 'running' });
  gate.recordSail({ last_resume_at: 'then', last_resume_state: 'running' });
  assert.deepEqual(gate.status().sail, {
    balance_usd: 31.06, spend_usd: null, range: null, box_status: 'running',
    checked_at: 'now', last_resume_at: 'then', last_resume_state: 'running',
    reserve_usd: null, spendable_usd: null, burn_usd_per_day: null, runway_days: null, run_out_at: null,
  });
});

test('an exit skips the dollar caps but still counts as an order', () => {
  const gate = build();
  for (let i = 0; i < 8; i += 1) assert.equal(gate.reserve({ micro: usd(50) }).ok, true);
  assert.equal(gate.reserve({ micro: usd(1) }).ok, false, 'the day is spent');
  const exit = gate.reserve({ micro: usd(275), exit: true });
  assert.equal(exit.ok, true, 'a stop on a $275 contract goes through the $50 order cap and the spent day');
  assert.equal(gate.status(NOON).today.orders, 9);
  const full = build({ ...ENV, MAX_DAY_ORDERS: '1' });
  assert.equal(full.reserve({ micro: usd(1) }).ok, true);
  assert.equal(full.reserve({ micro: usd(1), exit: true }).ok, false, 'the order count cap binds exits too');
});
