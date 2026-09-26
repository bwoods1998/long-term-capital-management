import assert from 'node:assert/strict';
import test from 'node:test';
import { monthCapMicro } from '../lib/frontier.mjs';
import { createGate } from '../lib/gate.mjs';
import { memoryStore } from './helpers.mjs';

const SEPT = Date.parse('2026-09-30T23:59:59.999Z');
const OCT = Date.parse('2026-10-01T00:00:00Z');
const ENV = {
  FRONTIER_MONTH_USD: '707',
  FRONTIER_MONTH_MAX_USD: '707',
  FRONTIER_FUNDED_MONTH: '2026-09',
  COMPUTE_PROFIT_SHARE: '0.3',
  EQUITY_BASELINE_USD: '500',
};

test('confirmed credit is available in its funded UTC month and expires at the boundary', () => {
  const store = memoryStore();
  let at = SEPT;
  const gate = createGate({ store, env: ENV, now: () => at });
  assert.equal(gate.frontierReserve({ micro: '1000000' }).ok, true);
  assert.equal(gate.status().frontier.cap_usd, '707.00');
  at = OCT;
  // Even a fresh profitable account reading cannot create unfunded credit in October.
  gate.recordEquity({ ok: true, at, kalshi_micro: '0', alpaca_micro: '5000000000' });
  assert.equal(gate.frontierReserve({ micro: '1' }).ok, false);
  const status = gate.status().frontier;
  assert.equal(status.cap_usd, '0.00');
  assert.equal(status.base_cap_usd, '0.00');
  assert.equal(status.previous.spent_usd, '1.00');
});

test('malformed or noncurrent funding records fail closed; an explicit new month reopens its own allowance', () => {
  for (const month of ['', '2026-9', '2026-00', '2026-13', '2026-08', '2026-10', null]) {
    assert.equal(monthCapMicro({ ...ENV, FRONTIER_FUNDED_MONTH: month }, SEPT), 0n);
  }
  assert.equal(monthCapMicro(ENV, NaN), 0n);
  const gate = createGate({ store: memoryStore(), env: {
    ...ENV, FRONTIER_FUNDED_MONTH: '2026-10', FRONTIER_MONTH_USD: '25', FRONTIER_MONTH_MAX_USD: '25',
  }, now: () => OCT });
  assert.equal(gate.frontierReserve({ micro: '25000000' }).ok, true);
  assert.equal(gate.frontierReserve({ micro: '1' }).ok, false);
});
