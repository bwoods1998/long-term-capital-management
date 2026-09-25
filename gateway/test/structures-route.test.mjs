// The multi-leg route through the front door (Sept 25, 2026): the practice account forwards every
// defined-risk structure unmetered and refuses every other option shape before signing; the real
// account refuses every multi-leg order unless OPTION_STRUCTURES_REAL admits its type, and then
// meters it at its maximum loss against the same caps as any order.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { NAKED_SHORT, UNCOVERED_RATIO } from '../lib/caps.mjs';
import { memoryStore, recorder, TOKEN } from './helpers.mjs';
import { occ, leg, mleg, closing, OPENS, BTO, STO, STC, BTC } from './structures-fixtures.mjs';

const NOW = Date.parse('2026-09-25T14:00:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';

const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN,
  GATEWAY_ADMIN_TOKEN: TOKEN + '-owner',
  ALPACA_KEY_ID: 'AK-TEST-KEY',
  ALPACA_SECRET_KEY: 'alpaca-secret-that-never-leaves-the-worker',
  ALPACA_PAPER_KEY_ID: 'PK-PAPER',
  ALPACA_PAPER_SECRET_KEY: 'paper-secret-held-by-the-worker',
  // As deployed (wrangler.jsonc, Sept 25, 2026).
  MAX_ORDER_USD: '75', MAX_ORDER_USD_ALPACA: '75', MAX_DAY_USD: '4000', MAX_DAY_ORDERS: '2000',
  CAP_TIMEZONE: 'America/New_York', PRODUCT_CACHE_MS: '0',
  ...extra,
});

const gateFor = settings => createGate({ store: memoryStore(), env: env(settings), now: () => NOW });

const post = (venue, body, headers = {}) => new Request(`${GATEWAY}/v1/${venue}/v2/orders`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${TOKEN}`, ...headers },
  body: typeof body === 'string' ? body : JSON.stringify(body),
});

const call = async (request, { settings, gate = gateFor(settings) } = {}) => {
  const tape = recorder({ status: 200, body: '{"id":"o-1","status":"accepted"}' });
  const response = await route(request, env(settings), { gate, fetcher: tape.fetcher, now: () => NOW });
  return { response, calls: tape.calls, gate, body: await response.clone().json().catch(() => null) };
};

const VERTICAL = [leg(occ(580), BTO), leg(occ(581), STO)];
const CREDIT_VERTICAL = [leg(occ(590), STO), leg(occ(591), BTO)];

test('the practice account takes every defined-risk structure, opened and closed, forwarded as sent and never metered', async () => {
  const gate = gateFor();
  await gate.setKill(true);  // practice is not stopped by the switch, as before
  for (const [type, legs, limit] of OPENS) {
    const credit = type.startsWith('credit') || type.startsWith('iron');
    for (const body of [mleg(legs, limit), mleg(closing(legs), credit ? '0.10' : '-0.05'), mleg(legs, limit, { qty: '25' })]) {
      const { response, calls } = await call(post('alpaca-paper', body), { gate });
      assert.equal(response.status, 200, `${type}: ${JSON.stringify(body.legs.map(row => row.position_intent))}`);
      assert.equal(calls.length, 1);
      assert.equal(calls[0].url, 'https://paper-api.alpaca.markets/v2/orders');
      assert.equal(calls[0].headers['APCA-API-KEY-ID'], 'PK-PAPER', 'never the live key');
      assert.deepEqual(JSON.parse(calls[0].body), body, 'forwarded exactly as sent');
    }
  }
  assert.equal((await gate.status()).today.orders, 0, 'practice is unmetered');
});

test('the practice account refuses a naked short, an uncovered ratio, a broken wing, a mis-signed vertical, a leg twice, mixed roots and legging', async () => {
  const cases = [
    [{ symbol: occ(580, 'P'), qty: '1', side: 'sell', type: 'limit', limit_price: '0.25', time_in_force: 'day', position_intent: STO }, /naked short/],
    [mleg([leg(occ(580, 'P'), STO), leg(occ(590), BTO)], '-0.40'), NAKED_SHORT],
    [mleg([leg(occ(590), STO), leg(occ(591), STO)], '-0.40'), NAKED_SHORT],
    [mleg([leg(occ(580), BTO), leg(occ(581), STO, '2')], '0.10'), UNCOVERED_RATIO],
    [mleg([leg(occ(580), BTO), leg(occ(581), STO, '2'), leg(occ(583), BTO)], '0.10'), /broken-wing/],
    [mleg([leg(occ(581), BTO), leg(occ(580), STO)], '0.40'), /Opening a credit_vertical takes in a credit.*wrong sign/],
    [mleg([leg(occ(580), BTO), leg(occ(580), STO)], '0.40'), /contract appears twice/],
    [mleg([leg(occ(580), BTO), leg(occ(581, 'C', '260928', 'QQQ'), STO)], '0.40'), /one underlying/],
    [mleg([leg(occ(580), STC), leg(occ(581), STO)], '-0.10'), /legging in or out/],
    [mleg([leg(occ(580), BTO), leg(occ(581), BTC)], '0.40'), /legging in or out/],
    [{ symbol: 'SPY', Legs: [leg(occ(580, 'P'), STO)], order_class: 'mleg', qty: '1', side: 'sell', type: 'limit', limit_price: '0.25' }, /own spelling/],
    ['{"symbol":"SPY","qty":"1"', /must be JSON/],
    ['', /must be JSON/],
  ];
  for (const [body, why] of cases) {
    const { response, calls, body: answer } = await call(post('alpaca-paper', body));
    assert.equal(response.status, 400, JSON.stringify(body));
    if (why instanceof RegExp) assert.match(answer.error, why);
    else assert.equal(answer.error, why);
    assert.equal(calls.length, 0, 'nothing is signed or forwarded');
  }
});

test('the practice account forwards the House\'s stock, crypto and single-leg option orders exactly as before', async () => {
  // The bodies ltcm/adapters/alpaca.py `submit` sends, far over any real-money cap.
  const house = extra => ({ qty: '400', side: 'buy', type: 'limit', limit_price: '10.00', time_in_force: 'day', client_order_id: 'oi-9', ...extra });
  for (const body of [
    house({ symbol: 'AAPL' }),
    house({ symbol: 'SPY', qty: '0.04', type: 'market', limit_price: undefined }),
    house({ symbol: 'BTC/USD', qty: '0.00015', time_in_force: 'gtc', limit_price: '64050.11' }),
    house({ symbol: 'AAPL', side: 'sell' }),
    house({ symbol: 'RIVN261002P00014000', qty: '5', limit_price: '0.14', position_intent: BTO }),
    house({ symbol: 'RIVN261002P00014000', qty: '5', side: 'sell', limit_price: '0.20', position_intent: STC }),
    house({ symbol: occ(580, 'P'), qty: '1', limit_price: '0.30', position_intent: BTC }),
  ]) {
    const text = JSON.stringify(body);
    const { response, calls, gate } = await call(post('alpaca-paper', text));
    assert.equal(response.status, 200, text);
    assert.equal(calls[0].body, text, 'the body goes out byte for byte');
    assert.equal((await gate.status()).today.orders, 0);
  }
  // Reads and cancels on practice are untouched.
  const cancel = await call(new Request(`${GATEWAY}/v1/alpaca-paper/v2/orders/abc`, { method: 'DELETE', headers: { Authorization: `Bearer ${TOKEN}` } }));
  assert.equal(cancel.response.status, 200);
});

test('the real account refuses every multi-leg order while OPTION_STRUCTURES_REAL is off', async () => {
  for (const settings of [{}, { OPTION_STRUCTURES_REAL: 'off' }, { OPTION_STRUCTURES_REAL: 'debit_verticle' }]) {
    for (const body of [mleg(VERTICAL, '0.70'), mleg(closing(VERTICAL), '-0.60')]) {
      for (const headers of [{}, { 'X-LTCM-Purpose': 'exit' }]) {
        const { response, calls, gate, body: answer } = await call(post('alpaca', body, headers), { settings });
        assert.equal(response.status, 400, JSON.stringify(settings));
        assert.match(answer.error, /Multi-leg, bracket, OCO and OTO orders/);
        assert.equal(calls.length, 0);
        assert.equal((await gate.status()).today.orders, 0);
      }
    }
  }
});

test('with OPTION_STRUCTURES_REAL="debit_vertical": a $0.70 vertical is metered at $70 and passes, $0.80 is refused over the cap, a credit vertical is not admitted, a close is metered at zero', async () => {
  const settings = { OPTION_STRUCTURES_REAL: 'debit_vertical' };
  const gate = gateFor(settings);

  const open = await call(post('alpaca', mleg(VERTICAL, '0.70')), { settings, gate });
  assert.equal(open.response.status, 200);
  assert.equal(open.calls.length, 1);
  assert.equal(open.calls[0].url, 'https://api.alpaca.markets/v2/orders');
  assert.equal(open.calls[0].headers['APCA-API-KEY-ID'], 'AK-TEST-KEY');
  assert.deepEqual(JSON.parse(open.calls[0].body), mleg(VERTICAL, '0.70'));
  assert.deepEqual((await gate.status()).today, { day: '2026-09-25', orders: 1, notional_usd: '70.00' });

  // $80 of maximum loss is over the $75 order cap, and a header calling the open an exit changes nothing.
  for (const headers of [{}, { 'X-LTCM-Purpose': 'exit' }]) {
    const over = await call(post('alpaca', mleg(VERTICAL, '0.80'), headers), { settings, gate });
    assert.equal(over.response.status, 403);
    assert.equal(over.body.cap, 'order');
    assert.equal(over.body.error, 'Order notional $80.00 exceeds the per-order cap of $75.00.');
    assert.equal(over.calls.length, 0);
  }

  const credit = await call(post('alpaca', mleg(CREDIT_VERTICAL, '-0.38')), { settings, gate });
  assert.equal(credit.response.status, 400);
  assert.equal(credit.body.error, 'A credit_vertical is not admitted on the real account: OPTION_STRUCTURES_REAL admits debit_vertical.');
  assert.equal(credit.calls.length, 0);

  // A close takes risk off: metered at zero (one micro-dollar, the least the gate records; health
  // rounds it up to a cent), counted as an order.
  const close = await call(post('alpaca', mleg(closing(VERTICAL), '-0.60')), { settings, gate });
  assert.equal(close.response.status, 200);
  assert.equal(close.calls.length, 1);
  assert.deepEqual((await gate.status()).today, { day: '2026-09-25', orders: 2, notional_usd: '70.01' });
  // A close at zero (the expiry-day close of a vertical bid at zero) passes the same way.
  assert.equal((await call(post('alpaca', mleg(closing(VERTICAL), '0')), { settings, gate })).response.status, 200);
  assert.equal((await gate.status()).today.orders, 3);

  // Every shape rule holds on the real account too.
  for (const [body, why] of [
    [mleg([leg(occ(580), BTO), leg(occ(581), STO, '2')], '0.10'), UNCOVERED_RATIO],
    [mleg([leg(occ(581), BTO), leg(occ(580), STO)], '0.40'), /wrong sign/],
    [mleg(VERTICAL, '-0.70'), /wrong sign/],
    [mleg(VERTICAL, '0.70', { symbol: 'SPY' }), /no top-level symbol/],
    [mleg(VERTICAL, '0.70', { type: 'market' }), /limit order/],
    [mleg([leg(occ(580), STC), leg(occ(581), STO)], '-0.10'), /legging/],
  ]) {
    const refused = await call(post('alpaca', body), { settings, gate });
    assert.equal(refused.response.status, 400, JSON.stringify(body));
    if (why instanceof RegExp) assert.match(refused.body.error, why);
    else assert.equal(refused.body.error, why);
    assert.equal(refused.calls.length, 0);
  }
  assert.equal((await gate.status()).today.orders, 3, 'no refusal reserved anything');
});

test('a structure close passes a spent day and a spent order cap, but not the kill switch', async () => {
  const settings = { OPTION_STRUCTURES_REAL: 'debit_vertical', MAX_DAY_USD: '100' };
  const gate = gateFor(settings);
  assert.equal((await call(post('alpaca', mleg(VERTICAL, '0.70')), { settings, gate })).response.status, 200);
  const second = await call(post('alpaca', mleg(VERTICAL, '0.70')), { settings, gate });
  assert.equal(second.response.status, 403);
  assert.equal(second.body.cap, 'day_notional');
  assert.equal((await call(post('alpaca', mleg(closing(VERTICAL), '-0.60')), { settings, gate })).response.status, 200);
  await gate.setKill(true);
  const halted = await call(post('alpaca', mleg(closing(VERTICAL), '-0.60')), { settings, gate });
  assert.equal(halted.response.status, 423);
  assert.equal(halted.calls.length, 0);
});

test('an admitted credit type is metered at its collateral less the credit', async () => {
  const settings = { OPTION_STRUCTURES_REAL: 'iron_condor,credit_vertical' };
  const condor = [leg(occ(579, 'P'), BTO), leg(occ(580, 'P'), STO), leg(occ(590), STO), leg(occ(591), BTO)];
  const one = await call(post('alpaca', mleg(condor, '-0.38')), { settings });
  assert.equal(one.response.status, 200);
  assert.equal((await one.gate.status()).today.notional_usd, '62.00');
  const two = await call(post('alpaca', mleg(condor, '-0.38', { qty: '2' })), { settings });
  assert.equal(two.response.status, 403);
  assert.equal(two.body.error, 'Order notional $124.00 exceeds the per-order cap of $75.00.');
  const vertical = await call(post('alpaca', mleg(CREDIT_VERTICAL, '-0.30')), { settings });
  assert.equal((await vertical.gate.status()).today.notional_usd, '70.00');
  // The debit vertical is not among these.
  assert.match((await call(post('alpaca', mleg(VERTICAL, '0.70')), { settings })).body.error, /debit_vertical is not admitted/);
});

test('the deployed configuration admits no structure on the real account', () => {
  // wrangler.jsonc is JSON with comments: the line itself is the check.
  const config = readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const lines = config.split('\n').filter(line => /"OPTION_STRUCTURES_REAL"/.test(line));
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^\s*"OPTION_STRUCTURES_REAL": "off",?\s*$/);
});
