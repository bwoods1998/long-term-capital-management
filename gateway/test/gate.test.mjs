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

test('the frontier month keeps the calls still unanswered apart from what is settled', () => {
  const gate = build({ ...ENV, FRONTIER_MONTH_USD: '100' });
  const read = () => { const m = gate.status().frontier; return [m.spent_usd, m.settled_usd, m.inflight_usd]; };
  const a = gate.frontierReserve({ micro: usd(5) });
  assert.equal(a.ok, true);
  assert.equal(a.tracked, true);
  assert.deepEqual(read(), ['5.00', '0.000000', '5.000000']);
  // It settles at $1.25 of its $5 worst case: the month falls, what is settled rises.
  assert.equal(gate.frontierSettle({ month: a.month, reserved: a.micro, actual: '1250000', tracked: a.tracked }).ok, true);
  assert.deepEqual(read(), ['1.25', '1.250000', '0.000000']);
  // A call whose cost is unknown keeps its whole worst case, and that is settled too.
  const b = gate.frontierReserve({ micro: usd(2) });
  gate.frontierSettle({ month: b.month, reserved: b.micro, actual: null, tracked: b.tracked });
  assert.deepEqual(read(), ['3.25', '3.250000', '0.000000']);
  // A call cut off before it could settle stays in flight: in the month, not in what is settled.
  gate.frontierReserve({ micro: usd(4) });
  assert.deepEqual(read(), ['7.25', '3.250000', '4.000000']);
});

test('a hold reserved before in-flight tracking settles without touching the in-flight figure', () => {
  // The month as the code before Sept 24, 2026 stored it: its $5 includes a $2 hold still in flight.
  const store = memoryStore({ frontier: JSON.stringify({ month: '2026-09', spent: '5000000', calls: 3, agents: {} }) });
  const gate = createGate({ store, env: { ...ENV, FRONTIER_MONTH_USD: '100' }, now: () => NOON });
  const read = () => { const m = gate.status().frontier; return [m.spent_usd, m.settled_usd, m.inflight_usd]; };
  assert.deepEqual(read(), ['5.00', '5.000000', '0.000000']);
  const fresh = gate.frontierReserve({ micro: usd(1) });
  // The old hold settles at $0.50 from an invocation of the old code, which passes no `tracked`.
  gate.frontierSettle({ month: '2026-09', reserved: usd(2), actual: '500000' });
  assert.deepEqual(read(), ['4.50', '3.500000', '1.000000']);
  gate.frontierSettle({ month: fresh.month, reserved: fresh.micro, actual: '100000', tracked: fresh.tracked });
  assert.deepEqual(read(), ['3.60', '3.600000', '0.000000']);
});

test('the month that ended is reported with its final, for the House s meter', () => {
  let at = Date.parse('2026-09-30T23:50:00Z');
  const gate = createGate({ store: memoryStore(), env: { ...ENV, FRONTIER_MONTH_USD: '100' }, now: () => at });
  assert.equal(gate.status().frontier.previous, null);
  const a = gate.frontierReserve({ micro: usd(3) });
  gate.frontierSettle({ month: a.month, reserved: a.micro, actual: '1250000', tracked: a.tracked });
  const late = gate.frontierReserve({ micro: usd(2) });  // in flight across midnight
  at = Date.parse('2026-10-01T00:01:00Z');
  let month = gate.status().frontier;
  assert.deepEqual([month.month, month.spent_usd, month.settled_usd], ['2026-10', '0.00', '0.000000']);
  assert.deepEqual(month.previous, { month: '2026-09', spent_usd: '3.25', settled_usd: '1.250000' });
  // Its month has ended: the late call's settle is refused and September keeps its worst case.
  assert.equal(gate.frontierSettle({ month: late.month, reserved: late.micro, actual: '100000', tracked: late.tracked }).ok, false);
  // The first October call replaces the stored month; September's final is kept beside it.
  gate.frontierReserve({ micro: usd(1) });
  month = gate.status().frontier;
  assert.equal(month.spent_usd, '1.00');
  assert.deepEqual(month.previous, { month: '2026-09', spent_usd: '3.25', settled_usd: '1.250000' });
  at = Date.parse('2026-11-02T00:00:00Z');
  assert.deepEqual(gate.status().frontier.previous, { month: '2026-10', spent_usd: '1.00', settled_usd: '0.000000' });
});
