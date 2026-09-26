// The gateway's front door: who gets in, what gets signed, what gets counted, and what the caller
// is told when a cap refuses an order.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route, parseRoute } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import { composeNotice, RELEASE_DRAWDOWN } from '../lib/email.mjs';
import { memoryStore, recorder, bearer, fakeGitHub, alpacaVenue, withEquity, TOKEN, GITHUB_REPO, GITHUB_TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-09-15T16:00:00Z');
const GATEWAY = 'https://ltcm-gateway.workers.dev';


const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN,
  GATEWAY_ADMIN_TOKEN: TOKEN + '-owner',
  ALPACA_KEY_ID: 'AK-TEST-KEY',
  ALPACA_SECRET_KEY: 'alpaca-secret-that-never-leaves-the-worker',
  MAX_ORDER_USD: '50', MAX_DAY_USD: '400', MAX_DAY_ORDERS: '60', CAP_TIMEZONE: 'America/New_York', POSITIONS_CACHE_MS: '0',
  // These tests' real account admits a single contract bought to open (not deployed: the review of Wave 5, m7/m15, pins
  // its refusal in maxloss.test.mjs), so the caps can be exercised on one contract.
  OPTION_STRUCTURES_REAL: 'long_call,long_put',
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

const ALPACA_ORDER = { symbol: 'AAPL', qty: '1', side: 'buy', type: 'limit', time_in_force: 'day', limit_price: '6.00', client_order_id: 'oi-2' };
const ALPACA_MARKET = { symbol: 'AAPL', qty: '2', side: 'buy', type: 'market', time_in_force: 'day' };
//: A single-leg option buy on the real account: $0.06 x 100 x 1 = $6.00 of maximum loss.
const OPTION_BUY = { symbol: 'SPY261016C00740000', qty: '1', side: 'buy', type: 'limit', time_in_force: 'day', limit_price: '0.06', position_intent: 'buy_to_open', client_order_id: 'oi-4' };

test('a stock order on the real account that closes nothing is refused, whatever its headers say: nothing is reserved or forwarded', async () => {
  // Sept 26, 2026 (the options-swarm run, Wave 5): the real account's only stock orders close assigned shares. Until
  // today this buy was priced at its limit (a reference header could raise it, never lower it) against a $50 cap.
  const tape = alpacaVenue({ positions: [] });
  const order = { ...ALPACA_ORDER, limit_price: '60.00' };
  const { response, body, gate } = await call(ask('POST', '/v1/alpaca/v2/orders',
    { body: order, headers: { 'X-LTCM-Reference-Price': '0.01', 'X-LTCM-Purpose': 'exit' } }), { fetcher: tape.fetcher });
  assert.equal(response.status, 400);
  assert.match(body.error, /^A stock order on the real account must close shares it holds: AAPL short \(1 needed, none held\)\./);
  assert.equal(tape.orders().length, 0);
  assert.equal(tape.accountReads().length, 0);
  assert.equal(gate.status(NOW).today.orders, 0);
});

test('a stock close on the real account reads no quote: a market sale of shares held long goes as an exit after one positions read', async () => {
  const tape = alpacaVenue({ positions: [{ symbol: 'AAPL', qty: '100', qty_available: '100', side: 'long', asset_class: 'us_equity' }] });
  const sale = { symbol: 'AAPL', qty: '100', side: 'sell', type: 'market', time_in_force: 'day' };
  const { response, gate } = await call(ask('POST', '/v1/alpaca/v2/orders', { body: sale, headers: { 'X-LTCM-Reference-Price': '0.01' } }),
    { fetcher: tape.fetcher });
  assert.equal(response.status, 200);
  assert.deepEqual(tape.calls.map(made => made.url), ['https://api.alpaca.markets/v2/positions', 'https://api.alpaca.markets/v2/orders']);
  assert.equal(tape.calls[0].headers['APCA-API-KEY-ID'], 'AK-TEST-KEY', 'the positions are read with the venue credential');
  assert.deepEqual(JSON.parse(tape.calls[1].body), sale);
  assert.deepEqual((await gate.status()).today, { day: '2026-09-15', orders: 1, notional_usd: '0.01' }, 'an exit at one micro-dollar');
});

test('positions that cannot be read admit no stock close (a 424 that reserves nothing), and a symbol that is not one is refused unread', async () => {
  const sale = { symbol: 'AAPL', qty: '2', side: 'sell', type: 'market', time_in_force: 'day' };
  const unread = alpacaVenue({ positions: 503 });
  const { response, body, gate } = await call(ask('POST', '/v1/alpaca/v2/orders', { body: sale }), { fetcher: unread.fetcher });
  assert.equal(response.status, 424);
  assert.match(body.error, /Cannot check that the real account holds these shares: venue HTTP 503/);
  assert.equal(unread.orders().length, 0);
  assert.equal((await gate.status()).today.orders, 0);
  const odd = alpacaVenue();
  const refused = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { ...sale, symbol: 'AAPL?x=1' } }), { fetcher: odd.fetcher });
  assert.equal(refused.response.status, 400);
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
    max_day_orders: 60, timezone: 'America/New_York',
  });
  // The caps by maximum loss (Sept 26, 2026, Wave 5): with no reading of the account yet, no open is admitted.
  assert.equal(body.max_loss.equity.fresh, false);
  assert.equal(body.max_loss.order_cap_usd, null);
  assert.equal(body.max_loss.opens_admitted, false);
  assert.deepEqual(Object.keys(body.watchdog).sort(),
    ['age_seconds', 'last_action', 'last_action_at', 'last_check_at', 'last_restart_at', 'published_at']);
  assert.ok('sail' in body && 'alerts' in body);
});







test('a single-leg option buy on the real account is metered at its own limit x 100 x qty: the reference header changes nothing', async () => {
  const gate = gateFor();
  const tape = alpacaVenue();
  const buy = { ...OPTION_BUY, symbol: 'RIVN261002P00014000', qty: '2', limit_price: '0.14' };
  for (const reference of ['0.01', '500']) {
    const priced = await call(ask('POST', '/v1/alpaca/v2/orders', { body: buy, headers: { 'X-LTCM-Reference-Price': reference } }),
      { gate, fetcher: tape.fetcher });
    assert.equal(priced.response.status, 200, reference);
  }
  assert.equal(gate.status(NOW).today.notional_usd, '56.00', '2 x $0.14 x 100, twice');
  assert.equal(gate.status(NOW).max_loss.day_open_max_loss_usd, '56.00');
  assert.equal(tape.accountReads().length, 1, 'the second open is sized from the first one\'s reading');
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

  // An option buy is priced from its own limit, x 100: 4 contracts at $0.10 is $40 of maximum loss, sized against the
  // account's equity, which the gateway read itself with the real key (Sept 26, 2026, Wave 5).
  const tape = alpacaVenue();
  const limit = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { ...OPTION_BUY, qty: '4', limit_price: '0.10' } }), { fetcher: tape.fetcher });
  assert.equal(limit.response.status, 200);
  assert.equal(JSON.parse(tape.orders()[0].body).symbol, 'SPY261016C00740000');
  assert.equal((await limit.gate.status()).today.notional_usd, '40.00');
  const [reading] = tape.accountReads();
  assert.deepEqual([reading.url, reading.method, reading.redirect, reading.headers['APCA-API-KEY-ID']], ['https://api.alpaca.markets/v2/account', 'GET', 'manual', 'AK-TEST-KEY']);

  // The same order for 400 contracts ($4,000) is over the per-order cap and never reaches the venue.
  const big = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { ...OPTION_BUY, qty: '400', limit_price: '0.10' } }), { fetcher: tape.fetcher });
  assert.equal(big.response.status, 403);
  assert.equal(big.body.cap, "order");
  assert.equal(tape.orders().length, 1);

  // A stock market buy covers no short the account holds: refused, and no quote is read for it.
  const market = await call(ask('POST', '/v1/alpaca/v2/orders', {
    body: { symbol: 'AAPL', qty: '2', side: 'buy', type: 'market', time_in_force: 'day' },
    headers: { 'X-LTCM-Reference-Price': '0.01' },
  }), { fetcher: tape.fetcher });
  assert.equal(market.response.status, 400);
  assert.ok(tape.calls.every(made => !made.url.includes('/quotes/')), 'no quote is read');
  assert.equal(tape.orders().length, 1);

  // A path this gateway does not sign, and a venue write that is not an order path.
  assert.equal((await call(ask('POST', '/v1/alpaca/v2/account/configurations'))).response.status, 403);
  assert.equal((await call(ask('DELETE', '/v1/alpaca/v2/positions'))).response.status, 403);

  // Without the secret the gateway refuses rather than sending an unauthenticated order.
  const bare = await call(ask('GET', '/v1/alpaca/v2/account'), { settings: { ALPACA_SECRET_KEY: '' } });
  assert.equal(bare.response.status, 503);
  assert.match(bare.body.error, /alpaca/);
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


test('a live_stop notice tells the owner which stop tripped, with the House\'s sentence, the equity and the time, and counts against the day', async () => {
  // Sept 26, 2026 (the options-swarm run, Wave 5): the House posts one when a stop trips on real money.
  const facts = stop => ({ kind: 'live_stop', stop, text: `The ${stop} stop tripped.`, equity: '4210.55', at: '2026-09-28T15:02:11.000Z' });
  for (const [stop, subject] of [
    ['drawdown', 'LTCM: real money paused (drawdown)'],
    ['daily', 'LTCM: no new real entries today (daily stop)'],
    ['reconciliation', 'LTCM: real entries frozen (reconciliation)'],
    ['assignment', 'LTCM: real entries frozen (assignment)'],
  ]) {
    const message = composeNotice(facts(stop));
    assert.equal(message.subject, subject);
    assert.match(message.text, new RegExp(`^The ${stop} stop tripped\\.\\n\\nEquity: \\$4210\\.55\\.\\nAt: 2026-09-28T15:02:11\\.000Z\\.\\n`));
    assert.equal(message.text.includes(RELEASE_DRAWDOWN), stop === 'drawdown', `${stop}: the release line is the drawdown's alone`);
    assert.ok(message.text.includes('https://blakewoods.us/capital/'));
  }
  assert.equal(RELEASE_DRAWDOWN, 'Exits go on; the Gym keeps running. Release the drawdown pause on the box with python3 -m league.live --root /workspace/state --release-drawdown.');
  // The House's sentence is clipped at 1,500 characters; an equity that is not a decimal is not echoed; a stop not named is refused.
  const long = composeNotice({ ...facts('daily'), text: 'x'.repeat(2000), equity: '1e9<script>' });
  assert.ok(long.text.startsWith(`${'x'.repeat(1500)}\n`));
  assert.match(long.text, /Equity: unknown\./);
  for (const stop of ['kill', 'DRAWDOWN', '', undefined, 'drawdown)\nBcc: x']) assert.equal(composeNotice({ ...facts('daily'), stop }), null, String(stop));

  // Through /v1/notify: mailed, and counted against NOTIFY_MAX_PER_DAY like any notice.
  const gate = gateFor();
  const sent = [];
  const options = { gate, now: () => NOW, mailer: async message => void sent.push(message) };
  const capped = env({ NOTIFY_MAX_PER_DAY: '2' });
  for (const stop of ['drawdown', 'assignment']) {
    const response = await route(ask('POST', '/v1/notify', { body: facts(stop) }), capped, options);
    assert.equal(response.status, 200, stop);
  }
  assert.deepEqual(sent.map(message => message.subject), ['LTCM: real money paused (drawdown)', 'LTCM: real entries frozen (assignment)']);
  assert.equal((await route(ask('POST', '/v1/notify', { body: facts('daily') }), capped, options)).status, 429);
  const unknown = await route(ask('POST', '/v1/notify', { body: facts('panic') }), env(), options);
  assert.equal(unknown.status, 400);
  assert.equal(sent.length, 2);
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

test('a provider capacity refusal bills nothing; a server error, an edge error or a cut-off answer keeps its worst case', async () => {
  const settings = {
    OPENAI_SECRET_KEY: 'test-key', FRONTIER_MONTH_USD: '10',
    FRONTIER_MODELS: JSON.stringify({ 'frontier-test': { input: 10, cached: 1, output: 50 } }),
  };
  const gate = gateFor(settings);
  const body = { model: 'frontier-test', input: 'Audit this candidate.', max_output_tokens: 1000 };
  const answer = (status, text, type = 'application/json') => async () => new Response(text, { status, headers: { 'Content-Type': type } });
  const month = async () => (await gate.status()).frontier;
  const micro = usd => BigInt(Math.round(Number(usd) * 1e6));

  // Sept 22, 2026: OpenAI answered two calls "server_is_overloaded" and the month kept each one's
  // whole worst case ($2.02 for one), for requests the provider says it lacked the capacity to process.
  const overloaded = JSON.stringify({ error: { message: 'Our servers are currently overloaded. Please try again later.',
    type: 'service_unavailable_error', param: null, code: 'server_is_overloaded' } });
  const refused = await call(ask('POST', '/v1/frontier/responses', { body }), { settings, gate, fetcher: answer(503, overloaded) });
  assert.equal(refused.response.status, 503);
  assert.equal(refused.response.headers.get('X-LTCM-Cost-USD'), '0.000000');
  let now = await month();
  assert.deepEqual([now.spent_usd, now.settled_usd, now.inflight_usd, now.calls], ['0.00', '0.000000', '0.000000', 1]);

  // A server error can come after the model has worked; an edge's 502 or 503 is not the provider's answer.
  for (const [status, text, type] of [
    [500, JSON.stringify({ error: { message: 'The server had an error while processing your request.', type: 'server_error' } }), 'application/json'],
    [503, '<html><body>503 Service Temporarily Unavailable</body></html>', 'text/html'],
    [502, '<html><body>502 Bad Gateway</body></html>', 'text/html'],
    [503, JSON.stringify({ error: { message: 'Upstream failure', type: 'server_error' } }), 'application/json'],
  ]) {
    const before = micro((await month()).settled_usd);
    const kept = await call(ask('POST', '/v1/frontier/responses', { body }), { settings, gate, fetcher: answer(status, text, type) });
    assert.equal(kept.response.status, status);
    const cost = kept.response.headers.get('X-LTCM-Cost-USD');
    assert.notEqual(cost, '0.000000', `${status} ${text} keeps its worst case`);
    now = await month();
    assert.equal(micro(now.settled_usd) - before, micro(cost), 'and it is settled, not left in flight');
    assert.equal(now.inflight_usd, '0.000000');
  }

  // An answer cut off while its body was read: until Sept 24, 2026 the exception escaped before the
  // settle ("error code: 1101") and the hold was left in flight for the rest of the month.
  const cut = async () => new Response(new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('{"id":"r1",')); controller.error(new Error('reset')); },
  }), { status: 200 });
  const before = micro((await month()).settled_usd);
  const broken = await call(ask('POST', '/v1/frontier/responses', { body }), { settings, gate, fetcher: cut });
  assert.equal(broken.response.status, 502);
  now = await month();
  assert.equal(now.inflight_usd, '0.000000', 'settled at its worst case, not left in flight');
  assert.ok(micro(now.settled_usd) > before);
  assert.equal(now.calls, 6, 'the refusal, the four kept and the cut-off one are all counted');

  // An answered call leaves nothing in flight, and what it cost is what is settled.
  const usage = { input_tokens: 100, output_tokens: 10 };
  const good = await call(ask('POST', '/v1/frontier/responses', { body }), { settings, gate,
    fetcher: async () => new Response(JSON.stringify({ model: body.model, usage }), { status: 200 }) });
  assert.equal(good.response.status, 200);
  const after = await month();
  assert.equal(micro(after.settled_usd) - micro(now.settled_usd), micro(good.response.headers.get('X-LTCM-Cost-USD')));
  assert.equal(after.inflight_usd, '0.000000');
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
    assert.match(refused.body.error, /multi-leg/i);  // the structure rules' refusal (Sept 25, 2026), before any quote
    assert.equal(refused.calls.length, 0, 'no quote read and nothing forwarded');
    assert.equal((await refused.gate.status()).today.orders, 0);
  }
  // A symbol-less single order is refused for its symbol, before the router's quote lookup.
  const bare = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { qty: '1', side: 'buy', type: 'limit', limit_price: '60', time_in_force: 'day' } }));
  assert.equal(bare.response.status, 400);
  assert.match(bare.body.error, /top-level symbol/);
  assert.equal(bare.calls.length, 0);
  // The House's own orders pass as before.
  const ok = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { ...ALPACA_ORDER, symbol: 'RIVN261002P00014000', limit_price: '0.14', position_intent: 'buy_to_open' } }),
    { fetcher: alpacaVenue().fetcher });
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
  // Sept 26, 2026, Wave 5: a stock market order on the real account is the sale of shares it holds, read from its
  // positions, never priced from a quote; one sized in dollars is refused (a close is sized in shares).
  const tape = alpacaVenue({ positions: [{ symbol: 'AAPL', qty: '0.1', side: 'long' }] });
  const ok = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { ...aapl, qty: '0.1', side: 'sell', type: 'market' }, headers }), { fetcher: tape.fetcher });
  assert.equal(ok.response.status, 200);
  assert.deepEqual(tape.calls.map(made => new URL(made.url).pathname), ['/v2/positions', '/v2/orders']);
  const dollars = await call(ask('POST', '/v1/alpaca/v2/orders', { body: { symbol: 'AAPL', notional: '25', side: 'sell', type: 'market', time_in_force: 'day' }, headers }), { fetcher: tape.fetcher });
  assert.equal(dollars.response.status, 400);
  assert.match(dollars.body.error, /sized in shares \(qty\), never in dollars/);
  assert.equal(tape.orders().length, 1);
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
  const order = { ...OPTION_BUY, qty: '400', limit_price: '10.00' };
  const placed = await call(ask('POST', '/v1/alpaca-paper/v2/orders', { body: order }), { settings, gate });
  assert.equal(placed.response.status, 200);
  assert.equal(placed.calls[0].url, 'https://paper-api.alpaca.markets/v2/orders');
  assert.equal((await gate.status()).today.orders, 0);
  // The live venue is still stopped by the same switch, and the path rules are shared.
  withEquity(gate, '5000.00', NOW);
  assert.equal((await call(ask('POST', '/v1/alpaca/v2/orders', { body: OPTION_BUY }), { settings, gate })).response.status, 423);
  assert.equal((await call(ask('POST', '/v1/alpaca-paper/v2/account/configurations'), { settings })).response.status, 403);
  assert.equal((await call(ask('GET', '/v1/alpaca-paper/v2/account'), { settings: { ALPACA_PAPER_SECRET_KEY: '' } })).response.status, 503);
});

// --- pull requests -------------------------------------------------------------------------------

const GITHUB = { GITHUB_TOKEN, GITHUB_REPO };
const PROPOSAL = {
  role: 'engineer', slug: 'variance-helper', title: 'Add the variance helper',
  body: 'Pure arithmetic helper with synthetic regression checks.',
  files: [{ path: 'league/tools/variance_helper.py', content: 'EDGE = 0.04\n' }],
};
const numbered = n => ({ ...PROPOSAL, slug: `candidate-${n}`, files: [{ path: `league/tools/candidate_${n}.py`, content: `N = ${n}\n` }] });


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
    ['engineer', 'league/ci.py'], ['engineer', 'league/tools/../constitution.py'], ['engineer', 'gateway/worker.mjs'],
    ['engineer', '.github/workflows/ci.yml'], ['engineer', 'league/game.json'], ['engineer', 'league/ledger.py'], ['engineer', 'league/swarm/private.py'],
  ]) {
    // The engineer's bad file rides behind a good one: one refused path refuses the proposal.
    const files = [...(role === 'engineer' ? PROPOSAL.files : []), { path, content: 'x\n' }];
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
  const heavy = { ...PROPOSAL, files: [0, 1, 2, 3, 4].map(n => ({ path: `league/tools/heavy_${n}.py`, content: 'x'.repeat(60 * 1024) })) };
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
