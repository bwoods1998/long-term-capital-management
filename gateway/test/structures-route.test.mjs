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
  CAP_TIMEZONE: 'America/New_York', PRODUCT_CACHE_MS: '0', POSITIONS_CACHE_MS: '0',
  ...extra,
});

const gateFor = settings => createGate({ store: memoryStore(), env: env(settings), now: () => NOW });

const post = (venue, body, headers = {}) => new Request(`${GATEWAY}/v1/${venue}/v2/orders`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${TOKEN}`, ...headers },
  body: typeof body === 'string' ? body : JSON.stringify(body),
});

//: What the real account holds unless a test says otherwise (`GET v2/positions`): five of the vertical below, as Alpaca
//: reports them (a short option with side "short" and a negative qty).
const HOLDING = [{ symbol: occ(580), qty: '5', side: 'long', asset_class: 'us_option' },
  { symbol: occ(581), qty: '-5', side: 'short', asset_class: 'us_option' }];
const isPositions = url => url.endsWith('/v2/positions');

// `calls` are the orders forwarded; `reads` the positions read (a real structure close reads them first, Sept 25, 2026).
const call = async (request, { settings, gate = gateFor(settings), positions = HOLDING } = {}) => {
  const tape = recorder(url => (isPositions(url)
    ? (positions instanceof Error ? Promise.reject(positions)
      : new Response(typeof positions === 'string' ? positions : JSON.stringify(positions),
        { status: positions?.status ?? 200, headers: { 'Content-Type': 'application/json' } }))
    : new Response('{"id":"o-1","status":"accepted"}', { status: 200, headers: { 'Content-Type': 'application/json' } })));
  const response = await route(request, env(settings), { gate, fetcher: tape.fetcher, now: () => NOW });
  return { response, calls: tape.calls.filter(c => !isPositions(c.url)), reads: tape.calls.filter(c => isPositions(c.url)), gate,
    body: await response.clone().json().catch(() => null) };
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

// --- a real close must close legs the account holds (Sept 25, 2026; the route's review, MINOR 1) ---------------------------

test('a real structure close is admitted only when the account holds every leg, read from its signed positions', async () => {
  const settings = { OPTION_STRUCTURES_REAL: 'debit_vertical' };
  const gate = gateFor(settings);
  const close = mleg(closing(VERTICAL), '-0.60');
  const ok = await call(post('alpaca', close), { settings, gate });
  assert.equal(ok.response.status, 200);
  assert.equal(ok.calls.length, 1, 'the close is forwarded');
  assert.equal(ok.reads.length, 1, 'after one positions read');
  assert.equal(ok.reads[0].url, 'https://api.alpaca.markets/v2/positions');
  assert.equal(ok.reads[0].method, 'GET');
  assert.equal(ok.reads[0].headers['APCA-API-KEY-ID'], 'AK-TEST-KEY', 'the REAL account, signed like every call');
  assert.deepEqual((await gate.status()).today, { day: '2026-09-25', orders: 1, notional_usd: '0.01' });

  const cases = [
    [[], /SPY260928C00580000 long \(1 needed, none held\); SPY260928C00581000 short \(1 needed, none held\)/],
    [[HOLDING[0]], /SPY260928C00581000 short \(1 needed, none held\)/],
    // The short leg held LONG: buying it "to close" would add to it, not close it.
    [[HOLDING[0], { symbol: occ(581), qty: '5', side: 'long' }], /SPY260928C00581000 short \(1 needed, 5 long held\)/],
    // The long leg held short (a leg sold to close would open a naked short).
    [[{ symbol: occ(580), qty: '-1', side: 'short' }, HOLDING[1]], /SPY260928C00580000 long \(1 needed, 1 short held\)/],
    // A row that contradicts itself (side long, a negative qty) holds nothing.
    [[{ symbol: occ(580), qty: '-1', side: 'long' }, HOLDING[1]], /SPY260928C00580000 long \(1 needed, none held\)/],
  ];
  for (const [positions, why] of cases) {
    const refused = await call(post('alpaca', close), { settings, gate, positions });
    assert.equal(refused.response.status, 400, JSON.stringify(positions));
    assert.match(refused.body.error, why);
    assert.match(refused.body.error, /A close of a leg not held would open a position: refused\./);
    assert.equal(refused.calls.length, 0, 'nothing is forwarded');
  }
  // Three structures closed with two held; then with three held (a side-less row read by its sign).
  const three = mleg(closing(VERTICAL), '-0.60', { qty: '3' });
  const two = [{ symbol: occ(580), qty: '2', side: 'long' }, { symbol: occ(581), qty: '-2', side: 'short' }];
  assert.match((await call(post('alpaca', three), { settings, gate, positions: two })).body.error, /long \(3 needed, 2 long held\)/);
  const bare = [{ symbol: occ(580), qty: '3' }, { symbol: occ(581), qty: '-3' }];
  assert.equal((await call(post('alpaca', three), { settings, gate, positions: bare })).response.status, 200);
  assert.equal((await gate.status()).today.orders, 2, 'no refusal reserved anything');
});

test('a butterfly close needs two of its body held short for each structure', async () => {
  const settings = { OPTION_STRUCTURES_REAL: 'long_butterfly' };
  const fly = [leg(occ(580), BTO), leg(occ(581), STO, '2'), leg(occ(582), BTO)];
  const close = mleg(closing(fly), '-0.10');
  const held = qty => [{ symbol: occ(580), qty: '1', side: 'long' }, { symbol: occ(581), qty: String(-qty), side: 'short' },
    { symbol: occ(582), qty: '1', side: 'long' }];
  const one = await call(post('alpaca', close), { settings, positions: held(1) });
  assert.equal(one.response.status, 400);
  assert.match(one.body.error, /SPY260928C00581000 short \(2 needed, 1 short held\)/);
  assert.equal((await call(post('alpaca', close), { settings, positions: held(2) })).response.status, 200);
});

test('positions that cannot be read admit no real close, and reserve nothing', async () => {
  const settings = { OPTION_STRUCTURES_REAL: 'debit_vertical' };
  const gate = gateFor(settings);
  const close = mleg(closing(VERTICAL), '-0.60');
  for (const [positions, why] of [
    [{ status: 500 }, /venue HTTP 500/],
    ['{"positions":[]}', /not a list/],
    ['not json', /unreadable venue answer/],
    [new TypeError('fetch failed'), /TypeError/],
  ]) {
    const answer = await call(post('alpaca', close), { settings, gate, positions });
    assert.equal(answer.response.status, 503, String(why));
    assert.match(answer.body.error, /Cannot check that the real account holds this structure's legs/);
    assert.match(answer.body.error, why);
    assert.equal(answer.calls.length, 0);
  }
  assert.equal((await gate.status()).today.orders, 0);
});

test('an open, the practice account and every single-leg order read no positions', async () => {
  const settings = { OPTION_STRUCTURES_REAL: 'debit_vertical' };
  const open = await call(post('alpaca', mleg(VERTICAL, '0.70')), { settings, positions: [] });
  assert.equal(open.response.status, 200);
  assert.equal(open.reads.length, 0);
  for (const body of [mleg(closing(VERTICAL), '-0.60'), mleg(VERTICAL, '0.70')]) {
    const practice = await call(post('alpaca-paper', body), { settings, positions: [] });
    assert.equal(practice.response.status, 200, 'practice is unchanged: the venue judges what it holds');
    assert.equal(practice.reads.length, 0);
  }
  const single = await call(post('alpaca', { symbol: 'RIVN261002P00014000', qty: '1', side: 'sell', type: 'limit', limit_price: '0.20',
    time_in_force: 'day', position_intent: STC }), { settings, positions: [] });
  assert.equal(single.reads.length, 0, 'a single contract\'s close is unchanged');
});

test('the positions are read at most once in a few seconds (POSITIONS_CACHE_MS)', async () => {
  const settings = { OPTION_STRUCTURES_REAL: 'debit_vertical', POSITIONS_CACHE_MS: '60000' };
  const gate = gateFor(settings);
  const close = mleg(closing(VERTICAL), '-0.60');
  const first = await call(post('alpaca', close), { settings, gate });
  const second = await call(post('alpaca', close), { settings, gate, positions: [] });  // the cached reading holds the legs
  assert.deepEqual([first.response.status, first.reads.length, second.response.status, second.reads.length], [200, 1, 200, 0]);
  // With the cache off the account is read again, and an empty account admits no close.
  const fresh = await call(post('alpaca', close), { settings: { OPTION_STRUCTURES_REAL: 'debit_vertical' }, gate, positions: [] });
  assert.deepEqual([fresh.response.status, fresh.reads.length], [400, 1]);
});
