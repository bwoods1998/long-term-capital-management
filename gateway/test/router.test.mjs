// The gateway's front door: who gets in, what gets signed, what gets counted, and what the caller
// is told when a cap refuses an order.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route, parseRoute } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { rsaKey, ed25519Key, decodeSegment, memoryStore, recorder, bearer, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-09-15T16:00:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';

const keys = { kalshi: await rsaKey(), coinbase: await ed25519Key() };

const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN,
  GATEWAY_ADMIN_TOKEN: TOKEN + '-owner',
  KALSHI_KEY_ID: 'a1b2c3',
  KALSHI_PRIVATE_KEY: keys.kalshi.pkcs8,
  COINBASE_KEY_NAME: 'organizations/o/apiKeys/k',
  COINBASE_API_SECRET: keys.coinbase.seed32,
  MAX_ORDER_USD: '50', MAX_DAY_USD: '400', MAX_DAY_ORDERS: '60', CAP_TIMEZONE: 'America/New_York',
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
const COINBASE_ORDER = {
  client_order_id: 'oi-2', product_id: 'BTC-USD', side: 'BUY',
  order_configuration: { limit_limit_gtc: { base_size: '0.0001', limit_price: '64050.11' } },
};

test('a caller cannot underprice a limit order with its reference header', async () => {
  const order = { ...COINBASE_ORDER, order_configuration: { limit_limit_gtc: { base_size: '1', limit_price: '60000' } } };
  const { response, calls } = await call(ask('POST', '/v1/coinbase/api/v3/brokerage/orders', { body: order, headers: { 'X-LTCM-Reference-Price': '0.01' } }));
  assert.equal(response.status, 403);
  assert.equal(calls.length, 0);
});

test('base-size market orders use an independent buffered venue price', async () => {
  const order = { ...COINBASE_ORDER, order_configuration: { market_market_ioc: { base_size: '0.0001' } } };
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify(options.method === 'GET' ? { price: '60000' } : { success: true }));
  };
  const { response, gate } = await call(ask('POST', '/v1/coinbase/api/v3/brokerage/orders', { body: order, headers: { 'X-LTCM-Reference-Price': '0.01' } }), { fetcher });
  assert.equal(response.status, 200);
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /market\/products\/BTC-USD$/);
  assert.equal((await gate.status()).today.notional_usd, '6.60');
});

test('market quote failure refuses the order before dispatch or reservation', async () => {
  const order = { ...COINBASE_ORDER, order_configuration: { market_market_ioc: { base_size: '0.0001' } } };
  const { response, calls, gate } = await call(ask('POST', '/v1/coinbase/api/v3/brokerage/orders', { body: order }), { reply: { status: 503, body: '{}' } });
  assert.equal(response.status, 503);
  assert.equal(calls.length, 1);
  assert.equal((await gate.status()).today.orders, 0);
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

test('a coinbase read carries a JWT bound to that one method and path', async () => {
  const { calls } = await call(ask('GET', '/v1/coinbase/api/v3/brokerage/accounts?limit=250'));
  assert.equal(calls[0].url, 'https://api.coinbase.com/api/v3/brokerage/accounts?limit=250');
  const [head, claims] = calls[0].headers.Authorization.slice('Bearer '.length).split('.');
  assert.equal(decodeSegment(head).alg, 'EdDSA');
  assert.equal(decodeSegment(claims).uri, 'GET api.coinbase.com/api/v3/brokerage/accounts');
  assert.equal(decodeSegment(claims).sub, 'organizations/o/apiKeys/k');
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

test('coinbase orders are priced from the reference header the caller sends', async () => {
  const gate = gateFor();
  const priced = await call(
    ask('POST', '/v1/coinbase/api/v3/brokerage/orders', {
      body: COINBASE_ORDER, headers: { 'X-LTCM-Reference-Price': '64050.11' },
    }),
    { gate },
  );
  assert.equal(priced.response.status, 200);
  assert.equal(gate.status(NOW).today.notional_usd, '6.41');

  // The same order at a price that puts it over the cap is refused.
  const refused = await call(
    ask('POST', '/v1/coinbase/api/v3/brokerage/orders', {
      body: { ...COINBASE_ORDER, order_configuration: { limit_limit_gtc: { base_size: '0.01', limit_price: '64050.11' } } },
      headers: { 'X-LTCM-Reference-Price': '64050.11' },
    }),
    { gate },
  );
  assert.equal(refused.response.status, 403);

  // A limit supplies its own enforceable ceiling without trusting a header.
  const unpriced = await call(ask('POST', '/v1/coinbase/api/v3/brokerage/orders', { body: COINBASE_ORDER }), { gate });
  assert.equal(unpriced.response.status, 200);
  assert.equal(unpriced.calls.length, 1);
});

test('reads and cancels always pass, whatever the counters say', async () => {
  const gate = gateFor({ MAX_DAY_ORDERS: '0' });
  for (const [method, path] of [
    ['GET', '/v1/kalshi/portfolio/balance'],
    ['DELETE', '/v1/kalshi/portfolio/events/orders/abc-123?market_ticker=KXBTC-26SEP1523-B75950&exchange_index=-1'],
    ['POST', '/v1/kalshi/portfolio/intra_exchange_instance_transfer'],  // a shard move is not an order
    ['GET', '/v1/coinbase/api/v3/brokerage/orders/historical/batch'],
    ['POST', '/v1/coinbase/api/v3/brokerage/orders/batch_cancel'],
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

  const unconfigured = await call(ask('GET', '/v1/coinbase/api/v3/brokerage/accounts'),
    { settings: { COINBASE_API_SECRET: '' } });
  assert.equal(unconfigured.response.status, 503);
  assert.match(unconfigured.body.error, /credentials for coinbase are unusable/);
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

test('the VM can fetch a Coinbase socket JWT with no uri claim and two minutes of life', async () => {
  const { response, body } = await call(ask('GET', '/v1/coinbase/ws-jwt'));
  assert.equal(response.status, 200);
  assert.equal(body.expires_in, 120);
  const [header, payload, signature] = body.jwt.split('.');
  const head = decodeSegment(header);
  const claims = decodeSegment(payload);
  assert.equal(head.alg, 'EdDSA');
  assert.equal(head.kid, 'organizations/o/apiKeys/k');
  assert.equal(typeof head.nonce, 'string');
  assert.deepEqual(Object.keys(claims).sort(), ['exp', 'iss', 'nbf', 'sub']);
  assert.equal(claims.iss, 'cdp');
  assert.equal(claims.sub, 'organizations/o/apiKeys/k');
  assert.equal(claims.exp - claims.nbf, 120);
  assert.equal(claims.nbf, Math.floor(NOW / 1000));
  const verified = await crypto.subtle.verify(
    { name: 'Ed25519' },
    keys.coinbase.publicKey,
    Buffer.from(signature.replace(/-/g, '+').replace(/_/g, '/'), 'base64'),
    new TextEncoder().encode(`${header}.${payload}`),
  );
  assert.equal(verified, true);
  // Two fetches are two tokens: a nonce per mint, never a reused JWT.
  const again = (await call(ask('GET', '/v1/coinbase/ws-jwt'))).body;
  assert.notEqual(again.jwt, body.jwt);
});

test('a missing credential turns a ws route into a 503, not a crash', async () => {
  const { response } = await call(ask('GET', '/v1/coinbase/ws-jwt'), { settings: { COINBASE_API_SECRET: '' } });
  assert.equal(response.status, 503);
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

test('only the documented routes and methods exist', async () => {
  assert.deepEqual(parseRoute('/v1/kalshi/portfolio/balance'), { venue: 'kalshi', path: 'portfolio/balance' });
  assert.equal(parseRoute('/v1/kalshi'), null);
  assert.equal(parseRoute('/v1/kalshi/'), null);
  assert.equal(parseRoute('/v1/alpaca/x'), null);
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
    ['POST', '/v1/coinbase/api/v3/brokerage/portfolios/move_funds', { amount: '1' }],
    ['GET', '/v1/coinbase/api/v3/brokerage/key_permissions', undefined],
    ['DELETE', '/v1/kalshi/portfolio/positions', undefined],
    ['POST', '/v1/kalshi/portfolio/balance', {}],
  ];
  for (const [method, path, body] of refused) {
    const response = await route(ask(method, path, body === undefined ? {} : { body }), env(), { gate, now: () => NOW });
    assert.equal(response.status, 403, `${method} ${path}`);
  }
  for (const [method, path] of [
    ['GET', '/v1/kalshi/portfolio/balance'], ['GET', '/v1/kalshi/markets?status=open&limit=5'],
    ['GET', '/v1/kalshi/markets/KXTEST-26/orderbook'], ['GET', '/v1/coinbase/api/v3/brokerage/accounts'],
    ['GET', '/v1/coinbase/api/v3/brokerage/market/products/BTC-USD/candles?granularity=ONE_HOUR'],
    ['DELETE', '/v1/kalshi/portfolio/orders/ord_1'], ['POST', '/v1/kalshi/account/api_usage_level/upgrade'],
  ]) {
    const { response } = await call(ask(method, path), { gate });
    assert.notEqual(response.status, 403, `${method} ${path}`);
  }
});
