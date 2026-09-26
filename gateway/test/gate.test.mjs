// The caps themselves: what is spent, what is refused, and how a day rolls over.

import assert from 'node:assert/strict';
import test from 'node:test';

import { createGate, tradingDay } from '../lib/gate.mjs';
import { memoryStore } from './helpers.mjs';

const ENV = { MAX_ORDER_USD: '50', MAX_DAY_USD: '400', MAX_DAY_ORDERS: '60', CAP_TIMEZONE: 'America/New_York' };
const NOON = Date.parse('2026-09-15T16:00:00Z'); // noon in New York
const usd = dollars => String(BigInt(Math.round(dollars * 100)) * 10000n);

const build = (env = ENV, at = NOON) => createGate({ store: memoryStore(), env, now: () => at });







test('the day rolls on the floor s own clock, not UTC', () => {
  // 01:00 UTC on the 16th is still the evening of the 15th in New York.
  assert.equal(tradingDay(Date.parse('2026-09-16T01:00:00Z'), 'America/New_York'), '2026-09-15');
  assert.equal(tradingDay(Date.parse('2026-09-16T01:00:00Z'), 'UTC'), '2026-09-16');
  assert.equal(tradingDay(Date.parse('2026-09-16T01:00:00Z'), 'Not/AZone'), '2026-09-16');
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
