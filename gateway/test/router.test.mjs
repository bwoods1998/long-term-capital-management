// The gateway's front door: who gets in, what gets signed, what gets counted, and what the caller
// is told when a cap refuses an order.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route, parseRoute } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { rsaKey, memoryStore, recorder, bearer, fakeGitHub, TOKEN, GITHUB_REPO, GITHUB_TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-09-15T16:00:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';

const keys = { kalshi: await rsaKey() };

const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN,
  GATEWAY_ADMIN_TOKEN: TOKEN + '-owner',
  KALSHI_KEY_ID: 'a1b2c3',
  KALSHI_PRIVATE_KEY: keys.kalshi.pkcs8,
  ALPACA_KEY_ID: 'AK-TEST-KEY',
  ALPACA_SECRET_KEY: 'alpaca-secret-that-never-leaves-the-worker',
  MAX_ORDER_USD: '50', MAX_DAY_USD: '400', MAX_DAY_ORDERS: '60', CAP_TIMEZONE: 'America/New_York', PRODUCT_CACHE_MS: '0',
  ...extra,
});

const gateFor = settings => createGate({ store: memoryStore(), env: env(settings), now: () => NOW });

const ask = (method, path, { body, headers = {}, token = TOKEN } = {}) =>
  new Request(GATEWAY + path, {
    method,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...headers },
    ...(body === undefined ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) }),
  });

const call = async (request, { settings, gate = gateFor(settings), reply, fetcher } = {}) => {
  const tape = fetcher ? { fetcher, calls: [] } : recorder(reply);
  const response = await route(request, env(settings), { gate, fetcher: tape.fetcher, now: () => NOW });
  return { response, calls: tape.calls, gate, body: await response.clone().json().catch(() => null) };
};

const KALSHI_ORDER = { ticker: 'KXTEST-26', side: 'bid', count: '3.00', price: '0.6500', client_order_id: 'oi-1' };
const ALPACA_ORDER = { symbol: 'AAPL', qty: '1', side: 'buy', type: 'limit', time_in_force: 'day', limit_price: '6.00', client_order_id: 'oi-2' };
const ALPACA_MARKET = { symbol: 'AAPL', qty: '2', side: 'buy', type: 'market', time_in_force: 'day' };

test('a caller cannot underprice a limit order with its reference header', async () => {
  const order = { ...ALPACA_ORDER, limit_price: '60.00' };
  const { response, body, calls } = await call(ask('POST', '/v1/alpaca/v2/orders', { body: order, headers: { 'X-LTCM-Reference-Price': '0.01' } }));
  assert.equal(response.status, 403);
  assert.equal(body.cap, 'order');
  assert.equal(calls.length, 0);
});

test('market orders use an independent buffered venue price', async () => {
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify(options.method === 'GET' ? { symbol: 'AAPL', quote: { ap: 3, bp: 2.9 } } : { id: 'o1' }));
  };
  const { response, gate } = await call(ask('POST', '/v1/alpaca/v2/orders', { body: ALPACA_MARKET, headers: { 'X-LTCM-Reference-Price': '0.01' } }), { fetcher });
  assert.equal(response.status, 200);
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /data\.alpaca\.markets\/v2\/stocks\/AAPL\/quotes\/latest$/);
  assert.equal(calls[0].options.headers['APCA-API-KEY-ID'], 'AK-TEST-KEY', 'the quote is fetched with the venue credential');
  assert.equal((await gate.status()).today.notional_usd, '6.60');
});

test('market quote failure refuses the order before dispatch or reservation', async () => {
  const { response, calls, gate } = await call(ask('POST', '/v1/alpaca/v2/orders', { body: ALPACA_MARKET }), { reply: { status: 503, body: '{}' } });
  assert.equal(response.status, 503);
  assert.equal(calls.length, 1);
  assert.equal((await gate.status()).today.orders, 0);

  // A quote with no price in it is no quote, and a symbol that is not one is never looked up.
  const empty = await call(ask('POST', '/v1/alpaca/v2/orders', { body: ALPACA_MARKET }), { reply: { status: 200, body: '{"quote":{}}' } });
  assert.equal(empty.response.status, 503);
  assert.equal((await empty.gate.status()).today.orders, 0);
  const odd = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { ...ALPACA_MARKET, symbol: 'AAPL?x=1' } }));
  assert.equal(odd.response.status, 400);
  assert.equal(odd.calls.length, 0);
});

test('a request without the right bearer token learns nothing else', async () => {
  for (const token of [null, 'wrong', TOKEN.slice(0, -1), TOKEN + 'x']) {
    const { response, body } = await call(ask('GET', '/v1/health', { token }));
    assert.equal(response.status, 401);
    assert.deepEqual(body, { error: 'Unauthorized.' });
    assert.equal(response.headers.get('WWW-Authenticate'), 'Bearer');
  }
  // A deployment with no token, or a short one, accepts nothing at all.
  for (const GATEWAY_TOKEN of [undefined, '', 'short']) {
    const response = await route(ask('GET', '/v1/health'), { ...env(), GATEWAY_TOKEN }, { gate: gateFor() });
    assert.equal(response.status, 401);
  }
});

test('health reports the caps, the counters, the kill switch and the watchdog', async () => {
  const { response, body } = await call(ask('GET', '/v1/health'));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  assert.equal(body.ok, true);
  assert.equal(body.kill_switch, false);
  assert.deepEqual(body.today, { day: '2026-09-15', orders: 0, notional_usd: '0.00' });
  assert.deepEqual(body.caps, {
    max_order_usd: '50.00', max_day_usd: '400.00', max_day_orders: 60, timezone: 'America/New_York',
  });
  assert.deepEqual(Object.keys(body.watchdog).sort(),
    ['age_seconds', 'last_action', 'last_action_at', 'last_check_at', 'last_restart_at', 'published_at']);
  assert.ok('sail' in body && 'alerts' in body);
});

test('a kalshi read is signed and forwarded verbatim, query and all', async () => {
  const { response, calls } = await call(
    ask('GET', '/v1/kalshi/portfolio/orders?status=resting&limit=200'),
    { reply: { status: 200, body: '{"orders":[]}' } },
  );
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://api.elections.kalshi.com/trade-api/v2/portfolio/orders?status=resting&limit=200');
  assert.equal(calls[0].headers['KALSHI-ACCESS-KEY'], 'a1b2c3');
  assert.equal(calls[0].headers['KALSHI-ACCESS-TIMESTAMP'], String(NOW));
  const verified = await crypto.subtle.verify(
    { name: 'RSA-PSS', saltLength: 32 },
    keys.kalshi.publicKey,
    Buffer.from(calls[0].headers['KALSHI-ACCESS-SIGNATURE'], 'base64'),
    new TextEncoder().encode(`${NOW}GET/trade-api/v2/portfolio/orders`),
  );
  assert.equal(verified, true, 'the signature covers the prefixed path without its query');
  assert.equal(response.status, 200);
  assert.equal(await response.text(), '{"orders":[]}');
});

test('the venue s own status and body come back untouched', async () => {
  const { response, body } = await call(
    ask('GET', '/v1/kalshi/portfolio/balance'),
    { reply: { status: 403, body: '{"error":{"code":"forbidden"}}' } },
  );
  assert.equal(response.status, 403);
  assert.deepEqual(body, { error: { code: 'forbidden' } });
});

test('an order inside the caps is counted once and forwarded', async () => {
  const { response, calls, gate } = await call(ask('POST', '/v1/kalshi/portfolio/events/orders', { body: KALSHI_ORDER }));
  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(JSON.parse(calls[0].body).client_order_id, 'oi-1', 'the body is forwarded as sent');
  assert.deepEqual(gate.status(NOW).today, { day: '2026-09-15', orders: 1, notional_usd: '1.95' });
});

test('an order over the per-order cap is refused before anything is signed', async () => {
  const { response, body, calls, gate } = await call(
    ask('POST', '/v1/kalshi/portfolio/events/orders', { body: { ...KALSHI_ORDER, count: '100', price: '0.9900' } }),
  );
  assert.equal(response.status, 403);
  assert.equal(body.cap, 'order');
  assert.match(body.error, /\$99\.00 exceeds the per-order cap of \$50\.00/);
  assert.equal(calls.length, 0, 'nothing reached the venue');
  assert.equal(gate.status(NOW).today.orders, 0, 'and nothing was spent');
});

test('a NO buy is capped at what it really costs, not the YES price on the wire', async () => {
  // 100 NO at $0.96 goes out as side "ask" at 0.0400: it costs $96, over the cap.
  const { response, body, calls } = await call(
    ask('POST', '/v1/kalshi/portfolio/events/orders', { body: { ...KALSHI_ORDER, side: 'ask', count: '100', price: '0.0400' } }),
  );
  assert.equal(response.status, 403);
  assert.equal(body.cap, 'order');
  assert.match(body.error, /\$96\.00 exceeds the per-order cap/);
  assert.equal(calls.length, 0, 'nothing reached the venue');
});

test('an exit order passes the per-order cap when the header says so', async () => {
  const { response, calls } = await call(
    ask('POST', '/v1/kalshi/portfolio/events/orders', { body: { ...KALSHI_ORDER, count: '100', price: '0.9900' }, headers: { 'X-LTCM-Purpose': 'exit' } }),
  );
  assert.equal(response.status, 200);
  assert.equal(calls.length, 1, 'the exit reached the venue');
});

test('a reference header can raise what a limit order is worth, never lower it', async () => {
  const gate = gateFor();
  const priced = await call(
    ask('POST', '/v1/alpaca/v2/orders', { body: ALPACA_ORDER, headers: { 'X-LTCM-Reference-Price': '6.41' } }),
    { gate },
  );
  assert.equal(priced.response.status, 200);
  assert.equal(gate.status(NOW).today.notional_usd, '6.41');

  // The same order at a size that puts it over the cap is refused.
  const refused = await call(
    ask('POST', '/v1/alpaca/v2/orders', { body: { ...ALPACA_ORDER, qty: '10' }, headers: { 'X-LTCM-Reference-Price': '6.41' } }),
    { gate },
  );
  assert.equal(refused.response.status, 403);

  // A limit supplies its own enforceable ceiling without trusting a header.
  const unpriced = await call(ask('POST', '/v1/alpaca/v2/orders', { body: ALPACA_ORDER }), { gate });
  assert.equal(unpriced.response.status, 200);
  assert.equal(unpriced.calls.length, 1);
  assert.equal(gate.status(NOW).today.notional_usd, '12.41');
});

test('the caps, the exit purpose and the kill switch are the same on every venue', async () => {
  const big = { ...ALPACA_ORDER, qty: '100', limit_price: '0.99' };
  const refused = await call(ask('POST', '/v1/alpaca/v2/orders', { body: big }));
  assert.equal(refused.response.status, 403);
  assert.match(refused.body.error, /\$99\.00 exceeds the per-order cap of \$50\.00/);
  const exit = await call(ask('POST', '/v1/alpaca/v2/orders', { body: big, headers: { 'X-LTCM-Purpose': 'exit' } }));
  assert.equal(exit.response.status, 200);
  assert.equal(exit.calls.length, 1, 'the exit reached the venue');
  assert.equal((await exit.gate.status()).today.orders, 1, 'and still counts as an order');

  const gate = gateFor();
  await call(ask('POST', '/v1/kill'), { gate });
  const killed = await call(ask('POST', '/v1/alpaca/v2/orders', { body: ALPACA_ORDER }), { gate });
  assert.equal(killed.response.status, 423);
  assert.equal(killed.calls.length, 0);
  assert.equal((await call(ask('DELETE', '/v1/alpaca/v2/orders/abc-123'), { gate })).response.status, 200, 'a cancel still passes');
});

test('a reservation is refunded when signing fails, and kept when the venue does not answer', async () => {
  for (const [path, body, settings] of [
    ['/v1/alpaca/v2/orders', ALPACA_ORDER, { ALPACA_SECRET_KEY: '' }],
    ['/v1/kalshi/portfolio/events/orders', KALSHI_ORDER, { KALSHI_PRIVATE_KEY: 'not a key' }],
  ]) {
    const unsigned = await call(ask('POST', path, { body }), { settings });
    assert.equal(unsigned.response.status, 503, path);
    assert.match(unsigned.body.error, /credentials for (alpaca|kalshi) are unusable/);
    assert.equal(unsigned.calls.length, 0);
    assert.deepEqual((await unsigned.gate.status()).today, { day: '2026-09-15', orders: 0, notional_usd: '0.00' }, 'nothing was dispatched, so nothing is spent');
  }

  const gate = gateFor();
  const silent = await call(ask('POST', '/v1/alpaca/v2/orders', { body: ALPACA_ORDER }),
    { gate, fetcher: async () => { throw Object.assign(new Error('nope'), { name: 'TimeoutError' }); } });
  assert.equal(silent.response.status, 502);
  assert.match(silent.body.error, /alpaca API did not answer/);
  assert.deepEqual(gate.status(NOW).today, { day: '2026-09-15', orders: 1, notional_usd: '6.00' });
});

test('reads and cancels always pass, whatever the counters say', async () => {
  const gate = gateFor({ MAX_DAY_ORDERS: '0' });
  for (const [method, path] of [
    ['GET', '/v1/kalshi/portfolio/balance'],
    ['DELETE', '/v1/kalshi/portfolio/events/orders/abc-123?market_ticker=KXBTC-26SEP1523-B75950&exchange_index=-1'],
    ['POST', '/v1/kalshi/portfolio/intra_exchange_instance_transfer'],  // a shard move is not an order
    ['GET', '/v1/alpaca/v2/orders?status=open'],
    ['DELETE', '/v1/alpaca/v2/orders/abc-123'],
  ]) {
    const { response, calls } = await call(ask(method, path, { body: method === 'POST' ? { order_ids: ['x'] } : undefined }),
      { gate, settings: { MAX_DAY_ORDERS: '0' } });
    assert.equal(response.status, 200, `${method} ${path}`);
    assert.equal(calls.length, 1, `${method} ${path} reached the venue`);
  }
  assert.equal(gate.status(NOW).today.orders, 0);
});

test('the kill switch stops orders with 423 and leaves everything else alone', async () => {
  const gate = gateFor();
  const killed = await call(ask('POST', '/v1/kill'), { gate });
  assert.equal(killed.response.status, 200);
  assert.equal(killed.body.kill_switch, true);

  const order = await call(ask('POST', '/v1/kalshi/portfolio/events/orders', { body: KALSHI_ORDER }), { gate });
  assert.equal(order.response.status, 423);
  assert.match(order.body.error, /kill switch is engaged/);
  assert.equal(order.calls.length, 0);

  const read = await call(ask('GET', '/v1/kalshi/portfolio/balance'), { gate });
  assert.equal(read.response.status, 200);

  const denied = await call(ask('POST', '/v1/unkill'), { gate });
  assert.equal(denied.response.status, 401, 'the VM cannot release the owner kill switch');
  const released = await call(ask('POST', '/v1/unkill', { token: TOKEN + '-owner' }), { gate });
  assert.equal(released.body.kill_switch, false);
  assert.equal((await call(ask('POST', '/v1/kalshi/portfolio/events/orders', { body: KALSHI_ORDER }), { gate })).response.status, 200);
});

test('an ambiguous venue submission keeps its reservation', async () => {
  const gate = gateFor();
  const { response, body } = await call(
    ask('POST', '/v1/kalshi/portfolio/events/orders', { body: KALSHI_ORDER }),
    { gate, fetcher: async () => { throw Object.assign(new Error('nope'), { name: 'TimeoutError' }); } },
  );
  assert.equal(response.status, 502);
  assert.match(body.error, /kalshi API did not answer/);
  assert.deepEqual(gate.status(NOW).today, { day: '2026-09-15', orders: 1, notional_usd: '1.95' });
});

test('a venue that answers badly keeps its reservation: an unconfirmed write is an order', async () => {
  const gate = gateFor();
  const { response } = await call(
    ask('POST', '/v1/kalshi/portfolio/events/orders', { body: KALSHI_ORDER }),
    { gate, reply: { status: 503, body: 'upstream is unwell' } },
  );
  assert.equal(response.status, 503);
  assert.equal(gate.status(NOW).today.orders, 1);
});

test('an order body that is not JSON is refused, and so is a missing credential', async () => {
  const bad = await call(ask('POST', '/v1/kalshi/portfolio/events/orders', { body: 'not json' }));
  assert.equal(bad.response.status, 400);
  assert.match(bad.body.error, /must be JSON/);

  const unconfigured = await call(ask('GET', '/v1/kalshi/portfolio/balance'),
    { settings: { KALSHI_PRIVATE_KEY: '' } });
  assert.equal(unconfigured.response.status, 503);
  assert.match(unconfigured.body.error, /credentials for kalshi are unusable/);
  assert.equal(unconfigured.calls.length, 0);
});

test('the VM can fetch Kalshi WebSocket handshake headers, signed over the ws path, never the key', async () => {
  const { response, body } = await call(ask('GET', '/v1/kalshi/ws-auth'));
  assert.equal(response.status, 200);
  assert.equal(body.path, '/trade-api/ws/v2');
  assert.equal(body.expires_in, 30);
  assert.equal(body.headers['KALSHI-ACCESS-KEY'], 'a1b2c3');
  assert.equal(body.headers['KALSHI-ACCESS-TIMESTAMP'], String(NOW));
  const verified = await crypto.subtle.verify(
    { name: 'RSA-PSS', saltLength: 32 },
    keys.kalshi.publicKey,
    Buffer.from(body.headers['KALSHI-ACCESS-SIGNATURE'], 'base64'),
    new TextEncoder().encode(`${NOW}GET/trade-api/ws/v2`),
  );
  assert.equal(verified, true);
  assert.equal(JSON.stringify(body).includes('PRIVATE KEY'), false);
  assert.equal((await call(ask('POST', '/v1/kalshi/ws-auth'))).response.status, 405);
  assert.equal((await call(ask('GET', '/v1/kalshi/ws-auth', { token: 'wrong' }))).response.status, 401);
});

test('a missing credential turns a ws route into a 503, not a crash', async () => {
  const kalshi = await call(ask('GET', '/v1/kalshi/ws-auth'), { settings: { KALSHI_PRIVATE_KEY: '' } });
  assert.equal(kalshi.response.status, 503);
});

test('the Kalshi tier upgrade is forwarded as a plain write and never counted as an order', async () => {
  const gate = gateFor();
  const { response, calls } = await call(ask('POST', '/v1/kalshi/account/api_usage_level/upgrade', { body: {} }), { gate });
  assert.equal(response.status, 200);
  assert.equal(calls[0].url, 'https://api.elections.kalshi.com/trade-api/v2/account/api_usage_level/upgrade');
  assert.equal(calls[0].method, 'POST');
  assert.ok(calls[0].headers['KALSHI-ACCESS-SIGNATURE']);
  assert.equal(gate.status(NOW).today.orders, 0, 'an upgrade is not an order');
});

test('alpaca is keyed inside the worker, hosted by path, and priced before it is sent', async () => {
  // A read: the two headers are added here and the VM never sees them.
  const read = await call(ask('GET', '/v1/alpaca/v2/account'));
  assert.equal(read.response.status, 200);
  assert.equal(read.calls[0].url, 'https://api.alpaca.markets/v2/account');
  assert.equal(read.calls[0].headers['APCA-API-KEY-ID'], 'AK-TEST-KEY');
  assert.equal(read.calls[0].headers['APCA-API-SECRET-KEY'], 'alpaca-secret-that-never-leaves-the-worker');

  // Market data is the same credential on the other host.
  const quotes = await call(ask('GET', '/v1/alpaca/v2/stocks/AAPL/quotes/latest?feed=iex'));
  assert.equal(quotes.calls[0].url, 'https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest?feed=iex');

  // A limit order is priced from its own limit: 4 x $10 is inside the $50 per-order cap.
  const limit = await call(ask('POST', '/v1/alpaca/v2/orders', {
    body: { symbol: 'AAPL', qty: '4', side: 'buy', type: 'limit', time_in_force: 'day', limit_price: '10.00' },
  }));
  assert.equal(limit.response.status, 200);
  assert.equal(JSON.parse(limit.calls[0].body).symbol, 'AAPL');
  assert.equal((await limit.gate.status()).today.notional_usd, '40.00');

  // The same order for 400 shares is over the per-order cap and never reaches the venue.
  const big = await call(ask('POST', '/v1/alpaca/v2/orders', {
    body: { symbol: 'AAPL', qty: '400', side: 'buy', type: 'limit', time_in_force: 'day', limit_price: '10.00' },
  }));
  assert.equal(big.response.status, 403);
  assert.equal(big.body.cap, "order");
  assert.equal(big.calls.length, 0);

  // A market order carries no price, so the gateway reads the venue's own quote and prices
  // the order 10% through the ask; the VM's claim about the price is never used.
  const market = await call(ask('POST', '/v1/alpaca/v2/orders', {
    body: { symbol: 'AAPL', qty: '2', side: 'buy', type: 'market', time_in_force: 'day' },
    headers: { 'X-LTCM-Reference-Price': '0.01' },
  }), {
    fetcher: async (url, init) => {
      if (String(url).includes('/quotes/latest')) return new Response(JSON.stringify({ symbol: 'AAPL', quote: { ap: 12, bp: 11.9 } }), { status: 200 });
      return new Response(JSON.stringify({ id: 'o1' }), { status: 200 });
    },
  });
  assert.equal(market.response.status, 200);
  assert.equal((await market.gate.status()).today.notional_usd, '26.40', '2 x 12 x 1.10, the venue price, not the caller s');

  // A path this gateway does not sign, and a venue write that is not an order path.
  assert.equal((await call(ask('POST', '/v1/alpaca/v2/account/configurations'))).response.status, 403);
  assert.equal((await call(ask('DELETE', '/v1/alpaca/v2/positions'))).response.status, 403);

  // Without the secret the gateway refuses rather than sending an unauthenticated order.
  const bare = await call(ask('GET', '/v1/alpaca/v2/account'), { settings: { ALPACA_SECRET_KEY: '' } });
  assert.equal(bare.response.status, 503);
  assert.match(bare.body.error, /alpaca/);
});

test('only the documented routes and methods exist', async () => {
  assert.deepEqual(parseRoute('/v1/kalshi/portfolio/balance'), { venue: 'kalshi', path: 'portfolio/balance' });
  assert.equal(parseRoute('/v1/kalshi'), null);
  assert.equal(parseRoute('/v1/kalshi/'), null);
  assert.deepEqual(parseRoute('/v1/alpaca/v2/account'), { venue: 'alpaca', path: 'v2/account' });
  assert.equal(parseRoute('/v1/schwab/accounts'), null, 'a venue this gateway holds no key for');
  // The Coinbase venue was removed on Sept 19, 2026: its paths are not routes any more.
  assert.equal(parseRoute('/v1/coinbase/api/v3/brokerage/accounts'), null);
  const gone = await call(ask('GET', '/v1/coinbase/api/v3/brokerage/accounts'));
  assert.equal(gone.response.status, 404);
  assert.equal(gone.calls.length, 0);
  assert.equal((await call(ask('GET', '/v1/coinbase/ws-jwt'))).response.status, 404);
  assert.equal((await call(ask('POST', '/v1/coinbase/api/v3/brokerage/orders', { body: {} }))).response.status, 404);
  assert.equal(parseRoute('/v1/kalshi/../../secret'), null, 'no traversal out of the venue path');

  assert.equal((await call(ask('GET', '/v1/unknown'))).response.status, 404);
  assert.equal((await call(ask('GET', '/'))).response.status, 404);
  assert.equal((await call(ask('GET', '/v1/kill'))).response.status, 405);
  assert.equal((await call(ask('PUT', '/v1/kalshi/portfolio/balance'))).response.status, 405);
  assert.equal((await call(ask('POST', '/v1/health'))).response.status, 405);
});

test('notice RPC methods are awaited and retries of a delivered notice are deduplicated', async () => {
  const local = gateFor();
  const gate = Object.fromEntries(['noticesToday', 'noticeDelivered', 'recordNotice'].map(name => [name, async (...args) => local[name](...args)]));
  let sent = 0;
  const options = { gate, now: () => NOW, mailer: async () => { sent += 1; } };
  const facts = { kind: 'test', notice_id: 'notice:stable-id' };
  assert.equal((await (await route(ask('POST', '/v1/notify', { body: facts }), env({ NOTIFY_MAX_PER_DAY: '1' }), options)).json()).notices_today, 1);
  assert.equal((await (await route(ask('POST', '/v1/notify', { body: facts }), env({ NOTIFY_MAX_PER_DAY: '1' }), options)).json()).duplicate, true);
  assert.equal((await route(ask('POST', '/v1/notify', { body: { ...facts, notice_id: 'notice:second' } }), env({ NOTIFY_MAX_PER_DAY: '1' }), options)).status, 429);
  assert.equal(sent, 1);
});

test('the Durable Object exposes every notification RPC method', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../worker.mjs', import.meta.url), 'utf8');
  for (const name of ['noticesToday', 'noticeDelivered', 'recordNotice']) assert.match(source, new RegExp(`\\b${name}\\([^)]*\\) \\{ return this\\.gate\\.${name}\\(`));
});

test('a trade notice is composed from the floor\'s facts, mailed once, and counted against the day', async () => {
  const sent = [];
  const mailer = async message => void sent.push(message);
  const gate = gateFor();
  const facts = {
    kind: 'trade', desk_name: 'Mullins', instrument: 'KXFED-26SEP-T3.75', venue: 'kalshi', side: 'buy', quantity: '20',
    price: '0.56', fee: '0.14', purpose: 'entry', rationale: 'Hot CPI put a hike at 93%; the market asked 89%.',
    engine: 'approved', critic: 'approve: sized inside the mandate', target_price: '0.95', stop_price: '0.40',
    time_stop_at: '2026-09-17T18:00:00.000Z', story_url: 'https://blakewoods.us/capital/desk/?id=mullins#story-oi-1',
  };
  const request = ask('POST', '/v1/notify', { body: facts });
  const response = await route(request, env(), { gate, now: () => NOW, mailer });
  const body = await response.json();
  assert.equal(response.status, 200, JSON.stringify(body));
  assert.equal(body.sent, true);
  assert.equal(body.notices_today, 1);
  assert.equal(sent[0].subject, 'LTCM: Mullins bought 20 KXFED-26SEP-T3.75 at $0.56');
  assert.match(sent[0].text, /Why, in the desk's words:\nHot CPI put a hike at 93%/);
  assert.match(sent[0].text, /Risk engine: approved\./);
  assert.match(sent[0].text, /Exit plan: target \$0\.95, stop \$0\.40, out by 2026-09-17T18:00:00\.000Z\./);
  assert.match(sent[0].text, /story-oi-1/);

  const settled = await route(ask('POST', '/v1/notify', { body: { kind: 'settled', desk_name: 'Mullins', instrument: 'KXFED-26SEP-T3.75', result: 'yes', quantity: '20', held_for_hours: '26', entry_price: '0.56', exit_price: '1.00', pnl: '8.66', rationale: 'Hike at 93%.' } }), env(), { gate, now: () => NOW, mailer });
  assert.equal(settled.status, 200);
  assert.equal(sent[1].subject, "LTCM: Mullins's KXFED-26SEP-T3.75 settled +$8.66");

  // Bad bodies are refused, not mailed; without a mail binding the answer says so.
  assert.equal((await route(ask('POST', '/v1/notify', { body: { kind: 'panic' } }), env(), { gate, now: () => NOW, mailer })).status, 400);
  assert.equal((await route(ask('GET', '/v1/notify'), env(), { gate, now: () => NOW, mailer })).status, 405);
  const unbound = await (await route(ask('POST', '/v1/notify', { body: { kind: 'test' } }), env(), { gate, now: () => NOW })).json();
  assert.equal(unbound.sent, false);
  assert.equal(sent.length, 2);

  // The day's cap holds: two more notices at a cap of four, then 429.
  const capped = env({ NOTIFY_MAX_PER_DAY: '4' });
  for (let i = 0; i < 2; i += 1) assert.equal((await route(ask('POST', '/v1/notify', { body: { kind: 'test' } }), capped, { gate, now: () => NOW, mailer })).status, 200);
  const over = await route(ask('POST', '/v1/notify', { body: { kind: 'test' } }), capped, { gate, now: () => NOW, mailer });
  assert.equal(over.status, 429);
  assert.equal(over.headers.get('Retry-After'), '3600');
  assert.equal(sent.length, 4);
});

test('the gateway signs only the venue paths the floor uses; everything else is refused before signing', async () => {
  const gate = gateFor();
  const refused = [
    ['POST', '/v1/kalshi/portfolio/orders/batched', KALSHI_ORDER],
    ['POST', '/v1/alpaca/v2/account/configurations', { suspend_trade: false }],
    ['GET', '/v1/alpaca/v2/wallets/transfers', undefined],
    ['DELETE', '/v1/kalshi/portfolio/positions', undefined],
    ['POST', '/v1/kalshi/portfolio/balance', {}],
  ];
  for (const [method, path, body] of refused) {
    const response = await route(ask(method, path, body === undefined ? {} : { body }), env(), { gate, now: () => NOW });
    assert.equal(response.status, 403, `${method} ${path}`);
  }
  for (const [method, path] of [
    ['GET', '/v1/kalshi/portfolio/balance'], ['GET', '/v1/kalshi/markets?status=open&limit=5'],
    ['GET', '/v1/kalshi/markets/KXTEST-26/orderbook'], ['GET', '/v1/alpaca/v2/account'],
    ['GET', '/v1/alpaca/v1beta3/crypto/us/latest/quotes?symbols=BTC%2FUSD'],
    ['DELETE', '/v1/kalshi/portfolio/orders/ord_1'], ['POST', '/v1/kalshi/account/api_usage_level/upgrade'],
  ]) {
    const { response } = await call(ask(method, path), { gate });
    assert.notEqual(response.status, 403, `${method} ${path}`);
  }
});

test('the frontier model is metered: reserved at its worst case, settled at its real cost, capped by the month', async () => {
  const settings = {
    OPENAI_SECRET_KEY: 'sk-test-key-that-never-leaves-the-worker',
    FRONTIER_MONTH_USD: '0.50',
    FRONTIER_MODELS: JSON.stringify({ 'frontier-test': { input: 10, cached: 1, output: 50 } }),
  };
  const gate = gateFor(settings);
  const usage = { input_tokens: 2000, input_tokens_details: { cached_tokens: 1000 }, output_tokens: 1000 };
  const seen = [];
  const fetcher = async (url, init) => { seen.push({ url, init }); return new Response(JSON.stringify({ id: 'r1', usage }), { status: 200 }); };
  const body = { model: 'frontier-test', input: 'Audit this candidate.', max_output_tokens: 1000 };

  const first = await call(ask('POST', '/v1/frontier/responses', { body, headers: { 'X-LTCM-Agent': 'auditor' } }), { settings, gate, fetcher });
  assert.equal(first.response.status, 200);
  assert.equal(seen[0].url, 'https://api.openai.com/v1/responses');
  assert.equal(seen[0].init.headers.Authorization, 'Bearer sk-test-key-that-never-leaves-the-worker');
  // 1000 fresh x $10 + 1000 cached x $1 + 1000 out x $50, per million: $0.061.
  assert.equal(first.response.headers.get('X-LTCM-Cost-USD'), '0.061000', 'meter receipts retain microdollars');
  let status = await gate.status();
  assert.equal(status.frontier.spent_usd, '0.07');
  assert.deepEqual(status.frontier.by_agent, { auditor: '0.07' });
  assert.equal(status.frontier.cap_usd, '0.50');

  // A call whose worst case does not fit in what is left of the month never leaves.
  const before = seen.length;
  const greedy = await call(ask('POST', '/v1/frontier/responses', { body: { ...body, max_output_tokens: 16000 } }), { settings, gate, fetcher });
  assert.equal(greedy.response.status, 402);
  assert.equal(greedy.body.cap, 'frontier_month');
  assert.equal(seen.length, before);

  // Unpriced models, streaming, and calls with no output bound are refused before any spend.
  for (const bad of [{ ...body, model: 'mystery-model' }, { ...body, stream: true }, { ...body, background: true }, { model: 'frontier-test', input: 'x' }]) {
    const refused = await call(ask('POST', '/v1/frontier/responses', { body: bad }), { settings, gate, fetcher });
    assert.ok([400, 403].includes(refused.response.status), JSON.stringify(bad));
  }
  assert.equal(seen.length, before);

  // A provider refusal bills nothing; a call that never answers keeps its whole reservation.
  const refusedUpstream = await call(ask('POST', '/v1/frontier/responses', { body }), { settings, gate, fetcher: async () => new Response('{"error":{"message":"bad"}}', { status: 400 }) });
  assert.equal(refusedUpstream.response.status, 400);
  assert.equal((await gate.status()).frontier.spent_usd, '0.07');
  const silent = await call(ask('POST', '/v1/frontier/responses', { body }), { settings, gate, fetcher: async () => { throw new Error('timeout'); } });
  assert.equal(silent.response.status, 502);
  assert.notEqual((await gate.status()).frontier.spent_usd, '0.07', 'unknown is not free');

  // No key, no budget: refused.
  assert.equal((await call(ask('POST', '/v1/frontier/responses', { body }), { settings: { ...settings, OPENAI_SECRET_KEY: '' } })).response.status, 503);
  assert.equal((await call(ask('POST', '/v1/frontier/responses', { body }), { settings: { ...settings, FRONTIER_MONTH_USD: '' } })).response.status, 403);
  assert.equal((await call(ask('GET', '/v1/frontier/responses'), { settings })).response.status, 405);
});

test('a tiny Luna call does not manufacture a budget breach by rounding its receipt to cents', async () => {
  const settings = {
    OPENAI_SECRET_KEY: 'test-key', FRONTIER_MONTH_USD: '1',
    FRONTIER_MODELS: JSON.stringify({ 'gpt-5.6-luna': {
      input: .25, cached: .02, output: 1.2, long_input: .5, long_cached: .04, long_output: 1.8,
    } }),
  };
  const store = memoryStore();
  const gate = createGate({ env: env(settings), store, now: () => NOW });
  const body = { model: 'gpt-5.6-luna', input: 'Classify this claim.', max_output_tokens: 1500 };
  const usage = { input_tokens: 201, output_tokens: 63 };
  const fetcher = async () => new Response(JSON.stringify({ model: body.model, usage }));
  const { response } = await call(ask('POST', '/v1/frontier/responses', { body }), { settings, gate, fetcher });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('X-LTCM-Cost-USD'), '0.000126');
  assert.equal(gate.frontierMonth(NOW).spent, 126n);
  assert.ok(Number(response.headers.get('X-LTCM-Cost-USD')) < 0.005,
    'a sub-cent reservation must cover the same amount reported to the campaign');
});

test('cache hints reach OpenAI byte for byte and a cache read settles cheaper than a write', async () => {
  const settings = {
    OPENAI_SECRET_KEY: 'test-key', FRONTIER_MONTH_USD: '1',
    FRONTIER_MODELS: JSON.stringify({ 'gpt-5.6-luna': {
      input: .25, uncached: .2, cached: .02, output: 1.2, long_input: .5, long_uncached: .4, long_cached: .04, long_output: 1.8,
    } }),
  };
  const gate = createGate({ env: env(settings), store: memoryStore(), now: () => NOW });
  const seen = [];
  const body = { model: 'gpt-5.6-luna', max_output_tokens: 100, prompt_cache_key: 'research:openai_luna:v2',
    prompt_cache_options: { mode: 'explicit', ttl: '30m' },
    input: [{ role: 'developer', content: [{ type: 'input_text', text: 'rules', prompt_cache_breakpoint: { mode: 'explicit' } }] },
      { role: 'user', content: 'now' }] };
  const reply = usage => async (url, init) => { seen.push(init.body); return new Response(JSON.stringify({ model: body.model, usage })); };
  const write = await call(ask('POST', '/v1/frontier/responses', { body }), { settings, gate,
    fetcher: reply({ input_tokens: 10000, output_tokens: 0, input_tokens_details: { cached_tokens: 0, cache_write_tokens: 10000 } }) });
  const read = await call(ask('POST', '/v1/frontier/responses', { body }), { settings, gate,
    fetcher: reply({ input_tokens: 10000, output_tokens: 0, input_tokens_details: { cached_tokens: 10000, cache_write_tokens: 0 } }) });
  assert.equal(write.response.status, 200);
  assert.equal(JSON.parse(seen[0]).prompt_cache_key, 'research:openai_luna:v2');
  assert.deepEqual(JSON.parse(seen[0]), body);
  assert.equal(write.response.headers.get('X-LTCM-Cost-USD'), '0.002500');
  assert.equal(read.response.headers.get('X-LTCM-Cost-USD'), '0.000200');
  const refused = await call(ask('POST', '/v1/frontier/responses', { body: { ...body, prompt_cache_key: 'no spaces allowed' } }),
    { settings, gate, fetcher: reply({}) });
  assert.equal(refused.response.status, 400);
  assert.equal(seen.length, 2, 'a malformed hint never reaches the provider');
});

test('a venue may carry a tighter per-order cap than the floor', async () => {
  const settings = { MAX_ORDER_USD: '50', MAX_ORDER_USD_ALPACA: '20' };
  const order = qty => ({ symbol: 'AAPL', qty, side: 'buy', type: 'limit', time_in_force: 'day', limit_price: '10.00' });
  assert.equal((await call(ask('POST', '/v1/alpaca/v2/orders', { body: order('2') }), { settings })).response.status, 200);
  const refused = await call(ask('POST', '/v1/alpaca/v2/orders', { body: order('3') }), { settings });
  assert.equal(refused.response.status, 403);
  assert.match(refused.body.error, /per-order cap of \$20\.00/);
  // An exit is never trapped by a dollar cap.
  assert.equal((await call(ask('POST', '/v1/alpaca/v2/orders', { body: order('3'), headers: { 'X-LTCM-Purpose': 'exit' } }), { settings })).response.status, 200);
});

test('a multi-leg order is refused before its symbol is quoted, priced or reserved, exits included', async () => {
  // Sept 23, 2026: on main the written put was forwarded to the venue metered at $0.25, and the
  // market spread under a stock symbol was quoted as SPY and forwarded.
  const legs = [{ symbol: 'SPY261016P00600000', ratio_qty: '1', side: 'sell', position_intent: 'sell_to_open' }];
  const writtenPut = { order_class: 'mleg', qty: '1', type: 'limit', limit_price: '0.25', time_in_force: 'day', legs };
  const marketSpread = { symbol: 'SPY', order_class: 'mleg', qty: '1', side: 'buy', type: 'market', time_in_force: 'day', legs };
  const quote = (url, init) => new Response(JSON.stringify(init.method === 'GET' ? { symbol: 'SPY', quote: { ap: 1, bp: 0.99 } } : { id: 'o1' }));
  for (const [body, headers] of [[writtenPut, {}], [writtenPut, { 'X-LTCM-Purpose': 'exit' }], [marketSpread, {}]]) {
    const refused = await call(ask('POST', '/v1/alpaca/v2/orders', { body, headers }), { reply: quote });
    assert.equal(refused.response.status, 400, JSON.stringify(body));
    assert.match(refused.body.error, /Multi-leg/);
    assert.equal(refused.calls.length, 0, 'no quote read and nothing forwarded');
    assert.equal((await refused.gate.status()).today.orders, 0);
  }
  // A symbol-less single order is refused for its symbol, before the router's quote lookup.
  const bare = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { qty: '1', side: 'buy', type: 'limit', limit_price: '60', time_in_force: 'day' } }));
  assert.equal(bare.response.status, 400);
  assert.match(bare.body.error, /top-level symbol/);
  assert.equal(bare.calls.length, 0);
  // The House's own orders pass as before.
  const ok = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { ...ALPACA_ORDER, symbol: 'RIVN261002P00014000', limit_price: '0.14', position_intent: 'buy_to_open' } }));
  assert.equal(ok.response.status, 200);
  assert.equal((await ok.gate.status()).today.notional_usd, '14.00');
});

test('an adjusted option symbol is refused before it is quoted, priced or forwarded', async () => {
  // Sept 23, 2026 review: each of these was forwarded, metered at $50.00; the written put's premium is $5,000.
  for (const symbol of ['TSLA1261016P00150000', 'XYZ1261016P00005000']) {
    for (const [side, position_intent] of [['sell', 'sell_to_open'], ['buy', 'buy_to_open']]) {
      const body = { symbol, qty: '10', side, position_intent, type: 'limit', limit_price: '5', time_in_force: 'day' };
      const refused = await call(ask('POST', '/v1/alpaca/v2/orders', { body }));
      assert.equal(refused.response.status, 400, `${symbol} ${position_intent}`);
      assert.match(refused.body.error, /standard OCC symbol/);
      assert.equal(refused.calls.length, 0, 'no quote read and nothing forwarded');
      assert.equal((await refused.gate.status()).today.orders, 0);
    }
  }
});

test('a market order is priced by the venue quote, never by a price field or the VM header', async () => {
  // Sept 23, 2026 review: a truthy limit_price or stop_price, even "0" or "x", skipped the venue
  // quote and the VM's X-LTCM-Reference-Price then priced 100 AAPL at $1.00; each was forwarded.
  const quote = (url, init) => new Response(JSON.stringify(init.method === 'GET' ? { symbol: 'AAPL', quote: { ap: 230, bp: 229.9 } } : { id: 'o1' }));
  const headers = { 'X-LTCM-Reference-Price': '0.01' };
  const aapl = { symbol: 'AAPL', qty: '100', side: 'buy', time_in_force: 'day' };
  for (const body of [
    { ...aapl, type: 'market', limit_price: '0.01' },
    { ...aapl, type: 'market', limit_price: '0' },
    { ...aapl, type: 'market', limit_price: 'x' },
    { ...aapl, type: 'limit', limit_price: '0' },
    { ...aapl, type: 'limit', limit_price: 'x' },
    { ...aapl, type: 'market', notional: '0' },
    { ...aapl, type: 'stop', stop_price: '0.01' },
    { ...aapl, type: 'market', stop_price: '0.01' },
  ]) {
    const refused = await call(ask('POST', '/v1/alpaca/v2/orders', { body, headers }), { reply: quote });
    assert.equal(refused.response.status, 400, JSON.stringify(body));
    assert.equal(refused.calls.length, 0, `${JSON.stringify(body)}: no quote read and nothing forwarded`);
    assert.equal((await refused.gate.status()).today.orders, 0);
  }
  // The House's market order is still quoted by the venue and priced 10% through the ask; the header is ignored.
  const ok = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { ...aapl, qty: '0.1', type: 'market' }, headers }), { reply: quote });
  assert.equal(ok.response.status, 200);
  assert.equal(ok.calls.length, 2);
  assert.equal((await ok.gate.status()).today.notional_usd, '25.30', '0.1 x 230 x 1.10');
  // A market order in dollars needs no quote: its notional is what it spends.
  const dollars = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { symbol: 'AAPL', notional: '25', side: 'buy', type: 'market', time_in_force: 'day' }, headers }), { reply: quote });
  assert.equal(dollars.response.status, 200);
  assert.equal(dollars.calls.length, 1, 'forwarded without a quote');
  assert.equal((await dollars.gate.status()).today.notional_usd, '25.00');
});

test('a trailing_stop, stop or stop_limit order is refused before any quote is read', async () => {
  // Sept 23, 2026 review: a trailing buy at 50% was metered at the ask ($73.37 for 0.29 AAPL at $230)
  // and passed the cap, though it cannot fill below about $345 a share.
  const quote = (url, init) => new Response(JSON.stringify(init.method === 'GET' ? { symbol: 'AAPL', quote: { ap: 230, bp: 229.9 } } : { id: 'o1' }));
  const aapl = { symbol: 'AAPL', qty: '0.29', side: 'buy', time_in_force: 'gtc' };
  for (const body of [
    { ...aapl, type: 'trailing_stop', trail_percent: '50' },
    { ...aapl, type: 'trailing_stop', trail_price: '1000' },
    { ...aapl, type: 'stop', stop_price: '0.01' },
    { ...aapl, type: 'stop_limit', stop_price: '0.01', limit_price: '0.01' },
  ]) {
    for (const headers of [{}, { 'X-LTCM-Purpose': 'exit' }]) {
      const refused = await call(ask('POST', '/v1/alpaca/v2/orders', { body, headers }), { reply: quote });
      assert.equal(refused.response.status, 400, JSON.stringify(body));
      assert.match(refused.body.error, /Only market and limit orders/);
      assert.equal(refused.calls.length, 0, 'no quote read and nothing forwarded');
      assert.equal((await refused.gate.status()).today.orders, 0);
    }
  }
});

test('the paper account is its own venue: paper keys, paper host, no caps, no kill switch', async () => {
  const settings = { ALPACA_PAPER_KEY_ID: 'PK-PAPER', ALPACA_PAPER_SECRET_KEY: 'paper-secret-held-by-the-worker' };
  const read = await call(ask('GET', '/v1/alpaca-paper/v2/account'), { settings });
  assert.equal(read.calls[0].url, 'https://paper-api.alpaca.markets/v2/account');
  assert.equal(read.calls[0].headers['APCA-API-KEY-ID'], 'PK-PAPER', 'never the live key');
  const data = await call(ask('GET', '/v1/alpaca-paper/v2/stocks/AAPL/quotes/latest'), { settings });
  assert.equal(data.calls[0].url, 'https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest');

  // An order far over the real-money cap goes through, is not counted, and ignores the kill switch.
  const gate = gateFor(settings);
  await gate.setKill(true);
  const order = { symbol: 'AAPL', qty: '400', side: 'buy', type: 'limit', time_in_force: 'day', limit_price: '10.00' };
  const placed = await call(ask('POST', '/v1/alpaca-paper/v2/orders', { body: order }), { settings, gate });
  assert.equal(placed.response.status, 200);
  assert.equal(placed.calls[0].url, 'https://paper-api.alpaca.markets/v2/orders');
  assert.equal((await gate.status()).today.orders, 0);
  // The live venue is still stopped by the same switch, and the path rules are shared.
  assert.equal((await call(ask('POST', '/v1/alpaca/v2/orders', { body: { ...order, qty: '1' } }), { settings, gate })).response.status, 423);
  assert.equal((await call(ask('POST', '/v1/alpaca-paper/v2/account/configurations'), { settings })).response.status, 403);
  assert.equal((await call(ask('GET', '/v1/alpaca-paper/v2/account'), { settings: { ALPACA_PAPER_SECRET_KEY: '' } })).response.status, 503);
});

// --- pull requests -------------------------------------------------------------------------------

const GITHUB = { GITHUB_TOKEN, GITHUB_REPO };
const PROPOSAL = {
  role: 'architect', slug: 'kalshi-weather-favorites', title: 'Add the Kalshi weather favorites strategy',
  body: 'Favorites above 90 cents settled yes 97% of the time in the replay.',
  files: [{ path: 'league/strategies/kalshi_weather_favorites.py', content: 'EDGE = 0.04\n' }],
};
const numbered = n => ({ ...PROPOSAL, slug: `candidate-${n}`, files: [{ path: `league/strategies/candidate_${n}.py`, content: `N = ${n}\n` }] });

test('a proposal becomes a branch and a pull request, and the reply is all the VM ever holds of GitHub', async () => {
  const hub = fakeGitHub();
  const { response, body, gate } = await call(ask('POST', '/v1/github/pr', { body: PROPOSAL }), { settings: GITHUB, fetcher: hub.fetcher });
  assert.equal(response.status, 200, JSON.stringify(body));
  assert.deepEqual(Object.keys(body), ['ok', 'branch', 'number', 'url', 'head']);
  assert.match(body.branch, /^merton\/architect\/kalshi-weather-favorites-[0-9a-f]{8}$/);
  assert.equal(body.number, 41);
  assert.equal(body.url, `https://github.com/${GITHUB_REPO}/pull/41`);
  assert.equal(body.head, hub.refs.get(body.branch));
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  assert.equal(JSON.stringify(body).includes(GITHUB_TOKEN), false);

  assert.equal(hub.calls.at(-1).key, 'POST /pulls');
  assert.deepEqual(hub.calls.at(-1).body, {
    title: PROPOSAL.title, head: body.branch, base: 'main',
    body: `${PROPOSAL.body}\n\n---\n\nOpened by Merton (architect) through the LTCM gateway.`,
  });
  assert.ok(hub.calls.every(made => made.headers.Authorization === `Bearer ${GITHUB_TOKEN}`), 'GitHub sees the GitHub token');
  assert.ok(hub.calls.every(made => !JSON.stringify(made).includes(TOKEN)), 'and never the gateway s own');
  assert.deepEqual((await gate.status()).github, { day: '2026-09-15', pull_requests: 1, cap: 12 });
  assert.deepEqual((await gate.status()).today, { day: '2026-09-15', orders: 0, notional_usd: '0.00' }, 'a proposal is not an order');
});

test('the GitHub routes need the gateway token like every other route, and no other', async () => {
  const hub = fakeGitHub();
  for (const token of [null, 'wrong', TOKEN.slice(0, -1), GITHUB_TOKEN, TOKEN + '-owner']) {
    for (const request of [ask('POST', '/v1/github/pr', { body: PROPOSAL, token }), ask('GET', '/v1/github/pr/41', { token })]) {
      const { response, body } = await call(request, { settings: GITHUB, fetcher: hub.fetcher });
      assert.equal(response.status, 401, String(token));
      assert.deepEqual(body, { error: 'Unauthorized.' });
    }
  }
  assert.equal(hub.calls.length, 0, 'GitHub heard nothing');
});

test('without the token or the repository the GitHub routes are a 503 and nothing is sent', async () => {
  for (const settings of [{}, { GITHUB_TOKEN }, { GITHUB_REPO }, { GITHUB_TOKEN: '', GITHUB_REPO }, { GITHUB_TOKEN, GITHUB_REPO: 'not-a-repository' }]) {
    const hub = fakeGitHub();
    for (const request of [ask('POST', '/v1/github/pr', { body: PROPOSAL }), ask('GET', '/v1/github/pr/41')]) {
      const { response, body, gate } = await call(request, { settings, fetcher: hub.fetcher });
      assert.equal(response.status, 503);
      assert.deepEqual(body, { error: 'GitHub is not configured.' });
      assert.equal((await gate.status()).github.pull_requests, 0);
    }
    assert.equal(hub.calls.length, 0);
  }
});

test('a proposal is refused before GitHub hears of it: the path by name, the rest by shape', async () => {
  const hub = fakeGitHub();
  const send = body => call(ask('POST', '/v1/github/pr', { body }), { settings: GITHUB, fetcher: hub.fetcher });
  for (const [role, path] of [
    ['architect', 'league/ci.py'], ['architect', 'league/strategies/../constitution.py'], ['architect', 'gateway/worker.mjs'],
    ['toolsmith', '.github/workflows/ci.yml'], ['operator', 'league/game.json'], ['designer', 'league/ledger.py'], ['teacher', 'league/strategies/x.py'],
  ]) {
    // The architect's bad file rides behind a good one: one refused path refuses the proposal.
    const files = [...(role === 'architect' ? PROPOSAL.files : []), { path, content: 'x\n' }];
    const { response, body, gate } = await send({ ...PROPOSAL, role, files });
    assert.equal(response.status, 403, `${role} ${path}`);
    assert.equal(body.path, path);
    assert.ok(body.error.includes(`"${path}"`), body.error);
    assert.equal((await gate.status()).github.pull_requests, 0, 'a refused proposal takes no place in the day');
  }
  assert.equal((await send({ ...PROPOSAL, role: 'janitor' })).response.status, 400);
  assert.equal((await send({ ...PROPOSAL, slug: 'No Spaces' })).response.status, 400);
  assert.equal((await send({ ...PROPOSAL, files: [] })).response.status, 400);
  assert.equal((await send({ ...PROPOSAL, files: Array.from({ length: 13 }, (_, n) => numbered(n).files[0]) })).response.status, 400);
  assert.equal((await send({ ...PROPOSAL, files: [{ ...PROPOSAL.files[0], content: 'x'.repeat(64 * 1024 + 1) }] })).response.status, 400);
  assert.equal((await send('not json')).response.status, 400);
  assert.equal((await send([PROPOSAL])).response.status, 400);
  // Five files, each inside its own ceiling, are together over the request s 256 KiB.
  const heavy = { ...PROPOSAL, files: [0, 1, 2, 3, 4].map(n => ({ path: `league/strategies/heavy_${n}.py`, content: 'x'.repeat(60 * 1024) })) };
  assert.equal((await send(heavy)).response.status, 413);
  assert.equal(hub.calls.length, 0, 'GitHub heard none of it');

  assert.equal((await call(ask('GET', '/v1/github/pr'), { settings: GITHUB })).response.status, 405);
  assert.equal((await call(ask('POST', '/v1/github/pr/41'), { settings: GITHUB })).response.status, 405);
  // There is no merge route, and nothing else under /v1/github either.
  for (const [method, path] of [['POST', '/v1/github/pr/41/merge'], ['PUT', '/v1/github/pr/41/merge'], ['POST', '/v1/github/merge'], ['GET', '/v1/github/pr/0'], ['GET', '/v1/github/pr/abc'], ['GET', '/v1/github/repos']]) {
    assert.equal((await call(ask(method, path), { settings: GITHUB, fetcher: hub.fetcher })).response.status, 404, `${method} ${path}`);
  }
  assert.equal(hub.calls.length, 0);
});

test('twelve pull requests a UTC day, then 429; a retry and a GitHub outage take no place', async () => {
  const hub = fakeGitHub();
  const gate = gateFor(GITHUB);
  const send = (body, options = {}) => call(ask('POST', '/v1/github/pr', { body }), { settings: GITHUB, gate, fetcher: hub.fetcher, ...options });
  for (let n = 1; n <= 11; n += 1) assert.equal((await send(numbered(n))).response.status, 200, `proposal ${n}`);

  // The same proposal again is the same pull request and is not counted twice.
  const again = await send(numbered(3));
  assert.equal(again.response.status, 200);
  assert.equal(again.body.number, 43);
  assert.equal((await gate.status()).github.pull_requests, 11);
  // GitHub down before any branch exists: a 502, and the place is given back.
  const down = await send(numbered(99), { fetcher: async () => { throw new Error('unreachable'); } });
  assert.equal(down.response.status, 502);
  assert.equal((await gate.status()).github.pull_requests, 11);

  assert.equal((await send(numbered(12))).response.status, 200);
  const before = hub.calls.length;
  const over = await send(numbered(13));
  assert.equal(over.response.status, 429);
  assert.equal(over.body.cap, 'github_day');
  assert.match(over.body.error, /cap of 12 pull requests/);
  assert.equal(over.response.headers.get('Retry-After'), '3600');
  assert.equal(hub.calls.length, before, 'the thirteenth never reached GitHub');
  assert.equal((await send(numbered(3))).response.status, 429, 'at the cap even a retry waits: the check comes before the call');
  // Watching is never capped.
  assert.equal((await call(ask('GET', '/v1/github/pr/43'), { settings: GITHUB, gate, fetcher: hub.fetcher })).response.status, 200);

  // The next UTC day starts at zero.
  const tomorrow = await route(ask('POST', '/v1/github/pr', { body: numbered(13) }), env(GITHUB), { gate, fetcher: hub.fetcher, now: () => NOW + 24 * 3600000 });
  assert.equal(tomorrow.status, 200);
  assert.equal(hub.pulls.length, 13);

  // The owner s deploy may lower the day, to nothing if need be.
  const off = await call(ask('POST', '/v1/github/pr', { body: PROPOSAL }), { settings: { ...GITHUB, GITHUB_MAX_PULLS_PER_DAY: '0' }, fetcher: hub.fetcher });
  assert.equal(off.response.status, 429);
});

test('a branch that was made is counted even when its pull request failed, and the retry is free', async () => {
  const gate = gateFor(GITHUB);
  let broken = true;
  const hub = fakeGitHub({ script: key => (broken && key === 'POST /pulls' ? new Response(JSON.stringify({ message: `Server Error ${GITHUB_TOKEN}` }), { status: 500 }) : undefined) });
  const failed = await call(ask('POST', '/v1/github/pr', { body: PROPOSAL }), { settings: GITHUB, gate, fetcher: hub.fetcher });
  assert.equal(failed.response.status, 502);
  assert.match(failed.body.error, /^GitHub answered HTTP 500 \(pull request\): Server Error \[redacted\]$/);
  assert.equal((await failed.response.text()).includes(GITHUB_TOKEN), false);
  assert.equal((await gate.status()).github.pull_requests, 1);

  broken = false;
  const healed = await call(ask('POST', '/v1/github/pr', { body: PROPOSAL }), { settings: GITHUB, gate, fetcher: hub.fetcher });
  assert.equal(healed.response.status, 200);
  assert.equal(healed.body.head, hub.refs.get(healed.body.branch));
  assert.equal((await gate.status()).github.pull_requests, 1, 'one branch, one place');
});

test('the kill switch does not stop a proposal or the watching of one: they move no money', async () => {
  const hub = fakeGitHub();
  const gate = gateFor(GITHUB);
  await call(ask('POST', '/v1/kill'), { gate });
  assert.equal((await gate.status()).kill_switch, true);
  assert.equal((await call(ask('POST', '/v1/kalshi/portfolio/events/orders', { body: KALSHI_ORDER }), { gate })).response.status, 423);

  const opened = await call(ask('POST', '/v1/github/pr', { body: PROPOSAL }), { settings: GITHUB, gate, fetcher: hub.fetcher });
  assert.equal(opened.response.status, 200);
  const watched = await call(ask('GET', `/v1/github/pr/${opened.body.number}`), { settings: GITHUB, gate, fetcher: hub.fetcher });
  assert.equal(watched.response.status, 200);
  assert.equal((await gate.status()).kill_switch, true, 'and neither of them released it');
});

test('the VM watches CI through the gateway: one pull request, its head and its checks', async () => {
  const hub = fakeGitHub();
  const gate = gateFor(GITHUB);
  const opened = await call(ask('POST', '/v1/github/pr', { body: PROPOSAL }), { settings: GITHUB, gate, fetcher: hub.fetcher });
  const watch = () => call(ask('GET', `/v1/github/pr/${opened.body.number}`), { settings: GITHUB, gate, fetcher: hub.fetcher });

  const waiting = await watch();
  assert.equal(waiting.response.status, 200);
  assert.deepEqual(waiting.body, {
    number: 41, state: 'open', merged: false, mergeable_state: 'clean', head: opened.body.head,
    checks: { total: 0, completed: 0, failed: 0, conclusion: 'pending' },
  });
  hub.checks = { total_count: 3, check_runs: [{ status: 'completed', conclusion: 'success' }, { status: 'in_progress', conclusion: null }, { status: 'queued', conclusion: null }] };
  assert.deepEqual((await watch()).body.checks, { total: 3, completed: 1, failed: 0, conclusion: 'pending' });
  hub.checks = { total_count: 3, check_runs: [{ status: 'completed', conclusion: 'success' }, { status: 'completed', conclusion: 'skipped' }, { status: 'completed', conclusion: 'success' }] };
  assert.deepEqual((await watch()).body.checks, { total: 3, completed: 3, failed: 0, conclusion: 'success' });
  hub.checks.check_runs[2].conclusion = 'failure';
  assert.deepEqual((await watch()).body.checks, { total: 3, completed: 3, failed: 1, conclusion: 'failure' });

  // The workflow merged it: the VM learns that here too, since nothing here can merge.
  Object.assign(hub.pulls[0], { state: 'closed', merged: true, mergeable_state: 'unknown' });
  const merged = await watch();
  assert.equal(merged.body.state, 'closed');
  assert.equal(merged.body.merged, true);
  assert.equal((await gate.status()).github.pull_requests, 1, 'watching is free');

  assert.equal((await call(ask('GET', '/v1/github/pr/999'), { settings: GITHUB, fetcher: hub.fetcher })).response.status, 404);
  const down = await call(ask('GET', '/v1/github/pr/41'), { settings: GITHUB, fetcher: async () => { throw new Error(GITHUB_TOKEN); } });
  assert.equal(down.response.status, 502);
  assert.deepEqual(down.body, { error: 'GitHub did not answer (pull request).' });
});

test('the Durable Object exposes the pull request counter, each step in one transaction', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../worker.mjs', import.meta.url), 'utf8');
  for (const name of ['pullReserve', 'pullRefund']) {
    assert.match(source, new RegExp(`\\b${name}\\(request\\) \\{ return this\\.ctx\\.storage\\.transactionSync\\(\\(\\) => this\\.gate\\.${name}\\(request\\)\\); \\}`));
  }
  // The router awaits them, so the stub s promises work as well as the gate s plain values.
  const local = gateFor(GITHUB);
  const stub = Object.fromEntries(['pullReserve', 'pullRefund', 'status'].map(name => [name, async (...args) => local[name](...args)]));
  const hub = fakeGitHub();
  assert.equal((await call(ask('POST', '/v1/github/pr', { body: PROPOSAL }), { settings: GITHUB, gate: stub, fetcher: hub.fetcher })).response.status, 200);
  assert.equal((await call(ask('POST', '/v1/github/pr', { body: PROPOSAL }), { settings: GITHUB, gate: stub, fetcher: hub.fetcher })).response.status, 200);
  assert.equal(local.status(NOW).github.pull_requests, 1);
});

test('the failure read is a GET behind the gateway token, and nothing else at that path', async () => {
  const hub = fakeGitHub();
  const { response } = await call(ask('GET', '/v1/github/pr/41/failures', { token: 'wrong' }), { settings: GITHUB, fetcher: hub.fetcher });
  assert.equal(response.status, 401);
  assert.equal((await call(ask('POST', '/v1/github/pr/41/failures'), { settings: GITHUB, fetcher: hub.fetcher })).response.status, 405);
  assert.equal(hub.calls.length, 0, 'GitHub heard nothing');
  assert.equal((await call(ask('GET', '/v1/github/pr/41/failures'), { settings: {}, fetcher: hub.fetcher })).response.status, 503);
  const missing = await call(ask('GET', '/v1/github/pr/41/failures'), { settings: GITHUB, fetcher: hub.fetcher });
  assert.equal(missing.response.status, 404, 'no such pull request on the fake');
});
