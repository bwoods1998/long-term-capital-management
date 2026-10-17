// The Tiingo daily route (`GET /v1/tiingo/daily/<SYM>/prices`, release R1, the deep key): who may ask, the 16-ETF and
// 1999-01-04..2019-12-31 allowlist, what is forwarded and what is answered. Every upstream here is a stand-in and the
// token is invented: the suite touches no network and never reads the owner's TIINGO_TOKEN.

import assert from 'node:assert/strict';
import test from 'node:test';

import { route } from '../lib/router.mjs';
import { createGate } from '../lib/gate.mjs';
import * as tiingo from '../lib/tiingo.mjs';
import { memoryStore, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-17T20:00:00Z');
const GATEWAY = 'https://ltcm-gateway.bw.workers.dev';
const FAKE_TIINGO = 'tiingo-test-token-invented-0123456789';
const env = { GATEWAY_TOKEN: TOKEN, GATEWAY_ADMIN_TOKEN: TOKEN + '-owner', TIINGO_TOKEN: FAKE_TIINGO };

// Invented bars: three days, a dividend on the second (the vendor's factor steps there) and nothing else.
const BARS = [
  { date: '2005-01-03T00:00:00.000Z', open: 10, high: 11, low: 9.5, close: 10.5, volume: 1000, adjOpen: 5, adjHigh: 5.5,
    adjLow: 4.75, adjClose: 5.25, adjVolume: 2000, divCash: 0, splitFactor: 1 },
  { date: '2005-01-04T00:00:00.000Z', open: 10.4, high: 10.9, low: 10.1, close: 10.6, volume: 1100, adjOpen: 5.2,
    adjHigh: 5.45, adjLow: 5.05, adjClose: 5.35, adjVolume: 2200, divCash: 0.1, splitFactor: 1 },
  { date: '2005-01-05T00:00:00.000Z', open: 10.6, high: 10.8, low: 10.2, close: 10.4, volume: 900, adjOpen: 5.35,
    adjHigh: 5.45, adjLow: 5.15, adjClose: 10.4 * (5.35 / 10.6), adjVolume: 1800, divCash: 0, splitFactor: 1 },
];

const reply = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function upstream(answer = () => reply(BARS)) {
  const calls = [];
  return { calls, fetcher: async (url, options = {}) => { calls.push({ url: String(url), ...options }); return answer(String(url), options); } };
}

const ask = (path, { token = TOKEN, method = 'GET' } = {}) =>
  new Request(GATEWAY + path, { method, headers: token ? { Authorization: `Bearer ${token}` } : {} });

async function call(path, { answer, options, environment = env } = {}) {
  const tape = upstream(answer);
  const gate = createGate({ store: memoryStore(), env: environment, now: () => NOW });
  const response = await route(ask(path, options), environment, { gate, fetcher: tape.fetcher, now: () => NOW });
  const text = await response.clone().text();
  return { response, calls: tape.calls, text, body: (() => { try { return JSON.parse(text); } catch { return null; } })() };
}

const PATH = '/v1/tiingo/daily/SPY/prices?startDate=2005-01-03&endDate=2005-01-05';

test('only the runtime token may ask, and only with GET', async () => {
  for (const token of [null, 'wrong', TOKEN + '-owner']) {
    const { response, calls } = await call(PATH, { options: { token } });
    assert.equal(response.status, 401);
    assert.equal(calls.length, 0);
  }
  const post = await call(PATH, { options: { method: 'POST' } });
  assert.equal(post.response.status, 405);
  assert.equal(post.calls.length, 0);
});

test('a symbol outside the 16 ETFs is refused before the token is touched', async () => {
  for (const symbol of ['XLC', 'AAPL', 'BRKB', 'VTI', 'SPYX']) {
    const { response, calls, body } = await call(`/v1/tiingo/daily/${symbol}/prices?startDate=2005-01-03&endDate=2005-01-05`);
    assert.equal(response.status, 403, symbol);
    assert.equal(body.cap, 'symbol');
    assert.equal(calls.length, 0);
  }
  assert.equal(tiingo.SYMBOLS.length, 16);
  assert.ok(!tiingo.SYMBOLS.includes('XLC'));
  const odd = await call('/v1/tiingo/daily/SPY.B/prices?startDate=2005-01-03&endDate=2005-01-05');
  assert.equal(odd.response.status, 404);
  assert.equal(odd.calls.length, 0);
});

test('no day of 2020 on, none before 1999-01-04, and only real ordered days', async () => {
  const windows = [['2019-12-31', '2020-01-02'], ['2020-01-02', '2020-12-31'], ['2025-01-02', '2025-12-31'],
    ['2026-01-02', '2026-10-09'], ['1998-12-31', '1999-01-08'], ['2005-01-05', '2005-01-03'], ['2001-13-01', '2001-12-31'],
    ['20010102', '2001-12-31'], ['2001-02-30', '2001-03-31'], [null, '2001-03-31'], ['2001-01-02', null]];
  for (const [start, end] of windows) {
    const query = new URLSearchParams();
    if (start) query.set('startDate', start);
    if (end) query.set('endDate', end);
    const { response, calls, body } = await call(`/v1/tiingo/daily/SPY/prices?${query}`);
    assert.equal(response.status, 403, `${start}..${end}`);
    assert.equal(body.cap, 'window');
    assert.equal(calls.length, 0);
  }
  for (const [start, end] of [['1999-01-04', '2001-04-06'], ['2001-04-09', '2008-12-31'], ['2016-01-04', '2019-12-31']]) {
    assert.equal(tiingo.refusal('spy', start, end), null, `${start}..${end}`);
  }
});

test('without the owner token the route is not configured, and nothing is asked', async () => {
  for (const TIINGO_TOKEN of [undefined, '', 'short']) {
    const { response, calls, body } = await call(PATH, { environment: { ...env, TIINGO_TOKEN } });
    assert.equal(response.status, 503);
    assert.equal(body.cap, 'setup');
    assert.equal(calls.length, 0);
  }
});

test('the request forwarded and the answer: raw bars and events, the adjusted columns dropped', async () => {
  const { response, calls, body, text } = await call(PATH);
  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  const sent = new URL(calls[0].url);
  assert.equal(sent.origin + sent.pathname, 'https://api.tiingo.com/tiingo/daily/spy/prices');
  assert.deepEqual(Object.fromEntries(sent.searchParams), { startDate: '2005-01-03', endDate: '2005-01-05',
    resampleFreq: 'daily', format: 'json' });
  assert.equal(calls[0].headers.Authorization, `Token ${FAKE_TIINGO}`);
  assert.equal(calls[0].method, 'GET');
  assert.equal(body.symbol, 'SPY');
  assert.deepEqual(body.rows.map(r => Object.keys(r).sort()), body.rows.map(() => [...tiingo.KEPT, 'factorStep'].sort()));
  assert.deepEqual(body.rows.map(r => r.date), ['2005-01-03', '2005-01-04', '2005-01-05']);
  assert.deepEqual(body.rows.map(r => r.factorStep), [false, true, false], 'the vendor factor moved on the dividend day');
  assert.deepEqual(body.rows.map(r => r.divCash), [0, 0.1, 0]);
  assert.ok(!/adj/i.test(text), 'no adjusted column leaves the gateway');
  assert.ok(!text.includes(FAKE_TIINGO), 'the token never comes back');
});

test('an upstream answer the route will not pass along is a 502 that names no secret', async () => {
  const cases = [
    () => reply({ detail: 'Invalid token.' }, 401),
    () => reply({ not: 'a list' }),
    () => reply([{ ...BARS[0], date: '2020-01-02' }]),
    () => reply([{ ...BARS[0], close: 'n/a' }]),
    () => reply([BARS[1], BARS[0]]),
    () => { throw new Error(`connect failed with ${FAKE_TIINGO}`); },
  ];
  for (const answer of cases) {
    const { response, text } = await call(PATH, { answer });
    assert.equal(response.status, 502);
    assert.ok(!text.includes(FAKE_TIINGO));
  }
});

test('the route is the gateway\'s own and is protected with league/deep/', async () => {
  const { MERGE_FORBIDDEN, protectedRefusal } = await import('../lib/protected.mjs');
  assert.ok(MERGE_FORBIDDEN.includes('league/deep/'));
  for (const path of ['league/deep/gate.py', 'League/Deep/Blocks.py', 'league/deep.py', 'gateway/lib/tiingo.mjs']) {
    assert.ok(protectedRefusal(path), path);
  }
  assert.equal(protectedRefusal('league/deep_notes.md'), null);
  assert.ok(tiingo.isTiingoPath('/v1/tiingo/daily/SPY/prices'));
  assert.ok(!tiingo.isTiingoPath('/v1/research/search'));
});
