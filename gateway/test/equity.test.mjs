// Profit-indexed compute: the frontier month's cap grows with verified profit on the real
// accounts, read by this Worker through its own venue keys, and is exactly FRONTIER_MONTH_USD
// whenever that profit is not known.

import assert from 'node:assert/strict';
import test from 'node:test';

import { effectiveCap, readEquity, refresh, shareMillionths, configured, CACHE_MS, MAX_AGE_MS } from '../lib/equity.mjs';
import { createGate } from '../lib/gate.mjs';
import { route } from '../lib/router.mjs';
import { rsaKey, memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-09-23T08:00:00Z');
const key = await rsaKey();

const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN,
  KALSHI_KEY_ID: 'kalshi-key-id', KALSHI_PRIVATE_KEY: key.pkcs8,
  ALPACA_KEY_ID: 'AK-REAL', ALPACA_SECRET_KEY: 'alpaca-real-secret',
  FRONTIER_MONTH_USD: '374', COMPUTE_PROFIT_SHARE: '0.3', EQUITY_BASELINE_USD: '1017.75',
  ...extra,
});

/** A reading of the two accounts, in dollars, as the gate stores it. */
const reading = (kalshiUsd, alpacaUsd, at = NOW) => ({
  ok: true, at, kalshi_micro: String(Math.round(kalshiUsd * 1e6)), alpaca_micro: String(Math.round(alpacaUsd * 1e6)),
});

/** A venue pair answering the two read-only calls; `kalshi`/`alpaca` are bodies, statuses or errors. */
function venues({ kalshi = { balance: 60000, portfolio_value: 0 }, alpaca = { equity: '517.75', status: 'ACTIVE' } } = {}) {
  const calls = [];
  const answer = value => {
    if (value instanceof Error) throw value;
    if (typeof value === 'number') return new Response('{}', { status: value });
    return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  const fetcher = async (url, init = {}) => {
    calls.push({ url: String(url), method: init.method, headers: init.headers });
    if (String(url).startsWith('https://api.elections.kalshi.com/trade-api/v2/portfolio/balance')) return answer(kalshi);
    if (String(url) === 'https://api.alpaca.markets/v2/account') return answer(alpaca);
    if (String(url) === 'https://api.openai.com/v1/responses') {
      return new Response(JSON.stringify({ id: 'r', usage: { input_tokens: 10, output_tokens: 10 } }), { status: 200 });
    }
    return new Response('{"error":"unexpected"}', { status: 599 });
  };
  return { fetcher, calls };
}

test('the cap is the month plus the profit share of equity above the baseline, in micro-dollars', () => {
  // $600 at Kalshi and $517.75 at Alpaca is $100 above $1017.75: 30% of it is $30.
  const { capMicro, parts } = effectiveCap(env(), reading(600, 517.75), NOW);
  assert.equal(capMicro, 404_000_000n);
  assert.equal(parts.base_cap_usd, '374.00');
  assert.equal(parts.equity_usd, '1117.75');
  assert.equal(parts.profit_usd, '100.00');
  assert.equal(parts.bonus_usd, '30.00');
  assert.equal(parts.reason, 'profit above the baseline');
  // Exact to the micro-dollar, rounded down: $0.000011 of profit buys $0.000003, not $0.0000033.
  assert.equal(effectiveCap(env(), { ok: true, at: NOW, kalshi_micro: '517750011', alpaca_micro: '500000000' }, NOW).capMicro,
    374_000_003n);
});

test('equity at or below the baseline leaves the cap exactly where it was', () => {
  for (const [kalshi, alpaca] of [[517.75, 500], [400, 500], [0, 0]]) {
    const { capMicro, parts } = effectiveCap(env(), reading(kalshi, alpaca), NOW);
    assert.equal(capMicro, 374_000_000n, `${kalshi} + ${alpaca}`);
    assert.equal(parts.bonus_usd, '0.00');
  }
});

test('an unknown profit is no profit: failed, missing, stale or future readings give the old cap', () => {
  const base = 374_000_000n;
  assert.equal(effectiveCap(env(), null, NOW).capMicro, base);
  assert.equal(effectiveCap(env(), { ok: false, at: NOW, error: 'kalshi balance: HTTP 503' }, NOW).capMicro, base);
  assert.match(effectiveCap(env(), { ok: false, at: NOW, error: 'kalshi balance: HTTP 503' }, NOW).parts.reason, /could not be read: kalshi balance: HTTP 503/);
  assert.equal(effectiveCap(env(), reading(900, 900, NOW - MAX_AGE_MS - 1), NOW).capMicro, base);
  assert.equal(effectiveCap(env(), reading(900, 900, NOW + 5 * 60000), NOW).capMicro, base);
  assert.equal(effectiveCap(env(), reading(900, 900, NOW - MAX_AGE_MS), NOW).capMicro, base + 234_675_000n);
  // Not configured: no share, a share outside 0..1, or no baseline.
  for (const change of [{ COMPUTE_PROFIT_SHARE: '' }, { COMPUTE_PROFIT_SHARE: '1.5' }, { COMPUTE_PROFIT_SHARE: '-0.3' },
    { COMPUTE_PROFIT_SHARE: 'lots' }, { EQUITY_BASELINE_USD: '' }, { EQUITY_BASELINE_USD: '-1' }]) {
    assert.equal(effectiveCap(env(change), reading(900, 900), NOW).capMicro, base, JSON.stringify(change));
    assert.equal(configured(env(change)), false, JSON.stringify(change));
  }
  assert.equal(shareMillionths(env()), 300000n);
  assert.equal(shareMillionths(env({ COMPUTE_PROFIT_SHARE: '1' })), 1000000n);
  // No month at all is still no month: indexing never creates a budget from nothing.
  assert.equal(effectiveCap(env({ FRONTIER_MONTH_USD: '' }), reading(600, 517.75), NOW).capMicro, 0n);
  assert.equal(effectiveCap(env({ FRONTIER_MONTH_USD: '0' }), reading(600, 517.75), NOW).capMicro, 0n);
});

test('FRONTIER_MONTH_MAX_USD holds the raise, and never pushes the cap below the month', () => {
  assert.equal(effectiveCap(env({ FRONTIER_MONTH_MAX_USD: '390' }), reading(600, 517.75), NOW).capMicro, 390_000_000n);
  const held = effectiveCap(env({ FRONTIER_MONTH_MAX_USD: '390' }), reading(600, 517.75), NOW).parts;
  assert.match(held.reason, /held to FRONTIER_MONTH_MAX_USD/);
  assert.deepEqual([held.earned_usd, held.bonus_usd], ['30.00', '16.00']);
  // A ceiling at the month itself: profit is measured and reported, and buys nothing until funded.
  const funded = effectiveCap(env({ FRONTIER_MONTH_MAX_USD: '374' }), reading(600, 517.75), NOW);
  assert.equal(funded.capMicro, 374_000_000n);
  assert.deepEqual([funded.parts.earned_usd, funded.parts.bonus_usd], ['30.00', '0.00']);
  assert.equal(effectiveCap(env({ FRONTIER_MONTH_MAX_USD: '500' }), reading(600, 517.75), NOW).capMicro, 404_000_000n);
  assert.equal(effectiveCap(env({ FRONTIER_MONTH_MAX_USD: '100' }), reading(600, 517.75), NOW).capMicro, 374_000_000n);
});

test('the accounts are read with the venue keys, read-only: Kalshi cash plus positions, Alpaca equity', async () => {
  const { fetcher, calls } = venues({ kalshi: { balance: 55000, portfolio_value: 1234 }, alpaca: { equity: '512.3456789' } });
  const row = await readEquity(env(), { fetcher, now: () => NOW });
  assert.deepEqual(row, { ok: true, at: NOW, kalshi_micro: '562340000', alpaca_micro: '512345678' });  // rounded down
  assert.equal(calls.length, 2);
  assert.ok(calls.every(call => call.method === 'GET'));
  assert.equal(calls[0].headers['KALSHI-ACCESS-KEY'], 'kalshi-key-id');
  assert.ok(calls[0].headers['KALSHI-ACCESS-SIGNATURE']);
  assert.equal(calls[1].headers['APCA-API-KEY-ID'], 'AK-REAL');
  // The dollar fields win over cents when Kalshi sends both; absent positions count as nothing.
  const dollars = await readEquity(env(), { fetcher: venues({ kalshi: { balance: 1, balance_dollars: '600.1234', portfolio_value_dollars: '10.50' } }).fetcher, now: () => NOW });
  assert.equal(dollars.kalshi_micro, '610623400');
  const bare = await readEquity(env(), { fetcher: venues({ kalshi: { balance: 60000 } }).fetcher, now: () => NOW });
  assert.equal(bare.kalshi_micro, '600000000');
});

test('half a reading is no reading', async () => {
  for (const [shape, error] of [
    [{ kalshi: 503 }, /kalshi balance: HTTP 503/],
    [{ kalshi: { portfolio_value: 5 } }, /kalshi balance: no balance field/],
    [{ kalshi: new TypeError('network down') }, /kalshi balance: network down/],
    [{ alpaca: 401 }, /alpaca account: HTTP 401/],
    [{ alpaca: { cash: '500' } }, /alpaca account: no equity field/],
    [{ alpaca: { equity: '-3' } }, /alpaca account: no equity field/],
  ]) {
    const row = await readEquity(env(), { fetcher: venues(shape).fetcher, now: () => NOW });
    assert.equal(row.ok, false, JSON.stringify(shape));
    assert.match(row.error, error);
  }
  assert.match((await readEquity(env({ KALSHI_PRIVATE_KEY: '' }), { fetcher: venues().fetcher, now: () => NOW })).error, /kalshi is not configured/);
  assert.match((await readEquity(env({ ALPACA_SECRET_KEY: '' }), { fetcher: venues().fetcher, now: () => NOW })).error, /alpaca/);
});

test('health reports the cap in force from the stored reading and never reads the venues itself', async () => {
  // The House reads its kill switch from /v1/health on the order path and treats a slow answer as the
  // switch engaged, so health must never wait on two venue reads (Deploy 3 review, Sept 23, 2026).
  let clock = NOW;
  const settings = env();
  const gate = createGate({ store: memoryStore(), env: settings, now: () => clock });
  const tape = venues({ kalshi: { balance: 60000, portfolio_value: 0 } });
  const health = async () => (await route(new Request('https://gw/v1/health', { headers: { Authorization: `Bearer ${TOKEN}` } }),
    settings, { gate, fetcher: tape.fetcher, now: () => clock })).json();

  let body = await health();
  assert.equal(tape.calls.length, 0, 'health reads no venue');
  assert.equal(body.frontier.cap_usd, '374.00');  // nothing stored yet: the month

  // The frontier path refreshes the reading (at most every ten minutes); health then reports it.
  await refresh(settings, gate, { fetcher: tape.fetcher, now: () => clock });
  assert.equal(tape.calls.length, 2);
  body = await health();
  assert.equal(tape.calls.length, 2, 'still no venue read from health');
  assert.equal(body.frontier.cap_usd, '404.00');
  assert.equal(body.frontier.base_cap_usd, '374.00');
  assert.equal(body.frontier.profit_index.bonus_usd, '30.00');
  assert.equal(body.frontier.profit_index.equity_usd, '1117.75');
  assert.equal(body.frontier.profit_index.baseline_usd, '1017.75');

  clock += CACHE_MS - 1;
  await refresh(settings, gate, { fetcher: tape.fetcher, now: () => clock });
  assert.equal(tape.calls.length, 2, 'cached for ten minutes');

  // Ten minutes on, the venue does not answer: the cap falls back to the month at once.
  clock += 1;
  const failing = venues({ kalshi: 503 });
  await refresh(settings, gate, { fetcher: failing.fetcher, now: () => clock });
  body = await health();
  assert.equal(failing.calls.length, 1);
  assert.equal(body.frontier.cap_usd, '374.00');
  assert.equal(body.frontier.profit_index.read_ok, false);
  assert.match(body.frontier.profit_index.reason, /could not be read/);

  // Not configured: the accounts are never read, and health is exactly as before.
  const plain = venues();
  const off = { ...settings, COMPUTE_PROFIT_SHARE: '' };
  await refresh(off, createGate({ store: memoryStore(), env: off, now: () => clock }), { fetcher: plain.fetcher, now: () => clock });
  body = await (await route(new Request('https://gw/v1/health', { headers: { Authorization: `Bearer ${TOKEN}` } }),
    off, { gate: createGate({ store: memoryStore(), env: off, now: () => clock }), fetcher: plain.fetcher, now: () => clock })).json();
  assert.equal(plain.calls.length, 0);
  assert.equal(body.frontier.cap_usd, '374.00');
});

test('a frontier call is admitted against the raised cap, and refused against the month when profit is unknown', async () => {
  const settings = env({
    OPENAI_SECRET_KEY: 'sk-test', FRONTIER_MONTH_USD: '0.10', EQUITY_BASELINE_USD: '1000',
    FRONTIER_MODELS: JSON.stringify({ m: { input: 10, cached: 1, output: 50 } }),
  });
  // Worst case: (bytes + 4096) x $10 + 2000 x $50 per million, a little over $0.14: above the $0.10 month.
  const body = JSON.stringify({ model: 'm', input: 'Audit this.', max_output_tokens: 2000 });
  const ask = () => new Request('https://gw/v1/frontier/responses', { method: 'POST', body,
    headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' } });

  const unknown = createGate({ store: memoryStore(), env: settings, now: () => NOW });
  const refused = await route(ask(), settings, { gate: unknown, fetcher: venues({ alpaca: 500 }).fetcher, now: () => NOW });
  assert.equal(refused.status, 402);
  assert.equal((await refused.json()).cap, 'frontier_month');

  // $1 of profit at 30% is $0.30 more: the same call now fits.
  const gate = createGate({ store: memoryStore(), env: settings, now: () => NOW });
  const tape = venues({ kalshi: { balance: 50100 }, alpaca: { equity: '500' } });
  const admitted = await route(ask(), settings, { gate, fetcher: tape.fetcher, now: () => NOW });
  assert.equal(admitted.status, 200);
  assert.deepEqual(tape.calls.map(call => new URL(call.url).host), ['api.elections.kalshi.com', 'api.alpaca.markets', 'api.openai.com']);
  assert.equal((await gate.status()).frontier.cap_usd, '0.40');
});
