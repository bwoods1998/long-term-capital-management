// Adversarial review of p/gateway 5bdf70e (Sept 25, 2026, the options-desk run): what the new
// practice check and the gated multi-leg route do to the House's real traffic, and where the
// real route's caps rest on the venue.
//
// `review-adapter-bodies.json` holds the exact bytes the House's Alpaca adapter writes for every
// practice order shape it can produce (stocks whole and fractional, market and limit; every crypto
// pair traded since Sept 18; single options on every root traded, entries and exits, every time in
// force; and, from origin/p/book ca68f8e, every structure type opened, closed, and closed by the
// House's expiry rule at its $0.01 floor), produced by running `ltcm/adapters/alpaca.py` itself over
// a capturing transport in gateway mode (`review_adapter_bodies.py`).

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { practiceOrderError } from '../lib/caps.mjs';
import { memoryStore, recorder, TOKEN } from './helpers.mjs';
import { occ, leg, mleg, closing, BTO, STO } from './structures-fixtures.mjs';

const NOW = Date.parse('2026-09-25T19:31:00Z');  // 15:31 New York: the House's structure close
const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner',
  ALPACA_KEY_ID: 'AK-TEST-KEY', ALPACA_SECRET_KEY: 'alpaca-secret', ALPACA_PAPER_KEY_ID: 'PK-PAPER', ALPACA_PAPER_SECRET_KEY: 'paper-secret',
  MAX_ORDER_USD: '75', MAX_ORDER_USD_ALPACA: '75', MAX_DAY_USD: '4000', MAX_DAY_ORDERS: '2000',
  CAP_TIMEZONE: 'America/New_York', PRODUCT_CACHE_MS: '0', OPTION_STRUCTURES_REAL: 'off', ...extra,
});
const send = async (venue, text, { settings = {}, gate, headers = {} } = {}) => {
  const theGate = gate ?? createGate({ store: memoryStore(), env: env(settings), now: () => NOW });
  const tape = recorder({ status: 200, body: '{"id":"o-1","status":"accepted"}' });
  const request = new Request(`https://ltcm-gateway.workers.dev/v1/${venue}/v2/orders`, {
    method: 'POST', headers: { Authorization: `Bearer ${TOKEN}`, ...headers }, body: text,
  });
  const response = await route(request, env(settings), { gate: theGate, fetcher: tape.fetcher, now: () => NOW });
  return { response, calls: tape.calls, gate: theGate, answer: await response.clone().json().catch(() => null) };
};

const ADAPTER = JSON.parse(readFileSync(new URL('./review-adapter-bodies.json', import.meta.url), 'utf8'));

test('every body the House\'s adapter writes for the practice account passes the new check, forwarded byte for byte', async () => {
  assert.ok(ADAPTER.length > 200);
  for (const row of ADAPTER) {
    assert.equal(practiceOrderError(JSON.parse(row.body)), null, `${row.from}: ${row.name}`);
    const { response, calls } = await send('alpaca-paper', row.body, { headers: { 'X-LTCM-Purpose': row.purpose } });
    assert.equal(response.status, 200, `${row.from}: ${row.name}`);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].body, row.body, 'the bytes go out as the adapter wrote them');
  }
});

test('the House\'s 15:30 expiry close at its $0.01 floor passes for every type on the practice account', async () => {
  const floor = ADAPTER.filter(row => row.name.startsWith('structure expiry close'));
  assert.equal(new Set(floor.map(row => row.name.split(' ')[3])).size, 9, 'every type of the spec');
  for (const row of floor) {
    const body = JSON.parse(row.body);
    assert.ok(body.legs.every(one => one.position_intent.endsWith('_to_close')));
    assert.equal((await send('alpaca-paper', row.body)).response.status, 200, row.name);
  }
});

// The real account with OPTION_STRUCTURES_REAL off, or any spelling that is not a type list: every
// #187 refusal holds, nothing is signed, nothing is reserved. (A differential run of 7,040 bodies x
// settings x headers x kill switch against origin/v/base's router found no difference at all.)
test('with the variable off, the real account refuses every multi-leg shape exactly as #187 did', async () => {
  const V = [leg(occ(580), BTO), leg(occ(581), STO)];
  const single = '"symbol":"SPY260928C00580000","qty":"1","side":"buy","type":"limit","limit_price":"0.50","time_in_force":"day","position_intent":"buy_to_open"';
  const bodies = [
    mleg(V, '0.70'), mleg(V, '0.70', { order_class: 'MLEG' }), mleg(V, '0.70', { order_class: 'Mleg' }),
    mleg([], '0.70'), mleg([V[0]], '0.70'), mleg(null, '0.70'), mleg(V, '0.70', { symbol: occ(580) }),
    mleg(closing(V), '-0.60'), mleg(closing(V), '0'),
    { ...JSON.parse(`{${single}}`), legs: V }, { ...JSON.parse(`{${single}}`), order_class: 'mleg' },
    `{${single},"order_class":"simple","order_class":"mleg"}`,
    `{"legs":${JSON.stringify(V)},${single}}`,
  ];
  for (const settings of [{}, { OPTION_STRUCTURES_REAL: undefined }, { OPTION_STRUCTURES_REAL: 'OFF' }, { OPTION_STRUCTURES_REAL: '' },
    { OPTION_STRUCTURES_REAL: 'none' }, { OPTION_STRUCTURES_REAL: 'debit_vertical,bogus' }, { OPTION_STRUCTURES_REAL: 'Debit_Vertical' }]) {
    for (const body of bodies) {
      const text = typeof body === 'string' ? body : JSON.stringify(body);
      const { response, calls, gate, answer } = await send('alpaca', text, { settings, headers: { 'X-LTCM-Purpose': 'exit' } });
      assert.equal(response.status, 400, `${JSON.stringify(settings)} ${text}`);
      assert.match(answer.error, /Multi-leg, bracket, OCO and OTO orders/);
      assert.equal(calls.length, 0);
      assert.equal((await gate.status()).today.orders, 0);
    }
  }
});

// MINOR, before OPTION_STRUCTURES_REAL is ever opened: a real "close" is read from the legs'
// position_intent alone and reserves one micro-dollar as an exit, whatever its size, so the dollar
// caps then rest entirely on Alpaca refusing a *_to_close leg the account does not hold. Alpaca's
// documentation does not say it enforces that on a multi-leg order's legs (its single-leg inference
// "position intent mismatch. inferred sell to close" is reported in alpacahq/Alpaca-API#250). A
// thousand debit verticals the account never held, "closed": the mirror is a thousand credit
// verticals, $100,000 of width, forwarded past a $75 order cap for $0.000001.
test('a real structure close of any size reserves one micro-dollar (the caps rest on the venue)', { todo: 'fix before OPTION_STRUCTURES_REAL is opened: confirm the legs are held (GET v2/positions) or meter the close' }, async () => {
  const settings = { OPTION_STRUCTURES_REAL: 'debit_vertical' };
  const close = mleg(closing([leg(occ(580), BTO), leg(occ(581), STO)]), '-0.01', { qty: '1000' });
  const { response, gate } = await send('alpaca', JSON.stringify(close), { settings });
  assert.equal(response.status, 400, 'a close of what the account does not hold is refused by the gateway');
  assert.equal((await gate.status()).today.notional_usd, '0.00');
});
