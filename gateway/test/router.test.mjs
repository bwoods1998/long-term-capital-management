// The gateway's front door: who gets in, what gets signed, what gets counted, and what the caller
// is told when a cap refuses an order.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route, parseRoute } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { rsaKey, memoryStore, recorder, bearer, TOKEN } from './helpers.mjs';

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
  assert.equal(first.response.headers.get('X-LTCM-Cost-USD'), '0.07', 'costs round up to the cent');
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
