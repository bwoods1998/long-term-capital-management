// The caps by maximum loss on the real Alpaca account (Sept 26, 2026 (the options-swarm run, Wave 5)): an opening order
// may lose at most the lower of $1,000 and 15% of the account's equity; the day's opening maximum loss at most 100% of
// equity and never above $10,000; 300 orders a day, exits included; a credit structure opens only at $2,000 of equity.
// The equity is read by the gateway itself, and an open with no reading from the last two minutes is refused, while an
// exit never waits on it. The real account's only stock orders close shares it holds.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import {
  maxLossCaps, shareMillionths, orderCapMicro, dayCapMicro, freshEquity, readAccountEquity, refreshAccountEquity,
  percent, shareText, formatUsdDown, ACCOUNT_EQUITY_KEY, MAX_AGE_MS,
} from '../lib/account.mjs';
import { realStockClose, closeLegsHeldError, closedLegRows, picoUnits } from '../lib/caps.mjs';
import { createGate, DAY_KEY } from '../lib/gate.mjs';
import { route } from '../lib/router.mjs';
import { memoryStore, alpacaVenue, withEquity, TOKEN } from './helpers.mjs';
import { occ, leg, mleg, closing, OPENS, BTO, STO, STC } from './structures-fixtures.mjs';

const NOW = Date.parse('2026-09-28T14:00:00Z');  // a Monday, 10:00 in New York
const TODAY = '2026-09-28';
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const M = 1000000n;
/** Dollars as micro-dollars, exactly ("750.01" -> 750010000n). */
const usd = dollars => {
  const [whole, fraction = ''] = String(dollars).split('.');
  return BigInt(whole) * M + BigInt(fraction.padEnd(6, '0').slice(0, 6));
};

//: The vars as wrangler.jsonc deploys them (pinned against the file below).
const DEPLOYED = {
  MAX_ORDER_USD: '75', MAX_ORDER_USD_KALSHI: '75', MAX_DAY_USD: '4000', MAX_DAY_USD_ALPACA: '10000', MAX_DAY_ORDERS: '300', MAX_DAY_OPEN_ORDERS: '250',
  MAX_ORDER_MAX_LOSS_USD: '1000', MAX_ORDER_EQUITY_SHARE: '0.15', MAX_DAY_EQUITY_SHARE: '1.0', CREDIT_MIN_EQUITY_USD: '2000',
  EQUITY_CAP_MAX_AGE_MS: '120000', CAP_TIMEZONE: 'America/New_York',
};
const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN, ALPACA_KEY_ID: 'AK-REAL', ALPACA_SECRET_KEY: 'alpaca-real-secret',
  OPTION_STRUCTURES_REAL: 'debit_vertical,credit_vertical,iron_condor,iron_butterfly,long_butterfly',
  ...DEPLOYED, POSITIONS_CACHE_MS: '0', ...extra,
});
//: The deployed list with a single contract bought to open admitted too (not deployed: the review of Wave 5, m7/m15), for
//: the tests that exercise the caps on one contract.
const LONGS = { OPTION_STRUCTURES_REAL: 'debit_vertical,credit_vertical,iron_condor,iron_butterfly,long_butterfly,long_call,long_put' };
const gateAt = (settings = {}, clock = () => NOW) => createGate({ store: memoryStore(), env: env(settings), now: clock });
/** A gate with a fresh reading of `equity` dollars. */
const gateWith = (equity, settings = {}) => withEquity(gateAt(settings), equity, NOW);
const open = (gate, dollars, extra = {}) => gate.reserve({ micro: String(usd(dollars)), venue: 'alpaca', ...extra });
const exit = (gate, dollars = '0.000001') => gate.reserve({ micro: String(usd(dollars)), venue: 'alpaca', exit: true });

const post = (body, headers = {}, venue = 'alpaca') => new Request(`${GATEWAY}/v1/${venue}/v2/orders`, {
  method: 'POST', headers: { Authorization: `Bearer ${TOKEN}`, ...headers }, body: JSON.stringify(body),
});
const send = async (body, { settings = {}, gate = gateAt(settings), tape = alpacaVenue(), headers = {}, clock = () => NOW, venue = 'alpaca' } = {}) => {
  const response = await route(post(body, headers, venue), env(settings), { gate, fetcher: tape.fetcher, now: clock });
  return { response, status: response.status, body: await response.clone().json().catch(() => null), gate, tape };
};
/** A single-leg option buy of `qty` contracts at `limit` a share: limit x 100 x qty of maximum loss. */
const buy = (limit, qty = '1', extra = {}) => ({ symbol: 'SPY261016C00740000', qty, side: 'buy', type: 'limit', limit_price: limit,
  position_intent: 'buy_to_open', time_in_force: 'day', ...extra });
const VERTICAL = [leg(occ(580), BTO), leg(occ(581), STO)];
const HOLDING = [{ symbol: occ(580), qty: '5', side: 'long' }, { symbol: occ(581), qty: '-5', side: 'short' }];
const SHARES = [{ symbol: 'AAPL', qty: '100', qty_available: '100', side: 'long', asset_class: 'us_equity' }];
const SALE = { symbol: 'AAPL', qty: '100', side: 'sell', type: 'market', time_in_force: 'day', client_order_id: 'oi-assign-1' };

// ------------------------------------------------------------------------------------------------ the numbers

test('the deployed vars are the plan\'s: $1,000 or 15% an order, 100% of equity a day inside $10,000, 250 of 300 orders open, credit from $2,000, a two-minute reading', () => {
  const config = readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const deployed = name => {
    const lines = config.split('\n').filter(line => line.includes(`"${name}"`));
    return lines.length === 1 ? JSON.parse(/:\s*("(?:[^"\\]|\\.)*")/.exec(lines[0])[1]) : lines.length;
  };
  for (const [name, value] of Object.entries(DEPLOYED)) assert.equal(deployed(name), value, name);
  assert.equal(deployed('MAX_ORDER_USD_ALPACA'), 0, 'the $75 premium cap is gone from the deployed vars');
  const limits = maxLossCaps(DEPLOYED);
  assert.deepEqual(limits, { orderLimitMicro: usd('1000'), orderShare: 150000n, dayShare: M, dayLimitMicro: usd('10000'), creditMinMicro: usd('2000'),
    maxAgeMs: 120000, maxDayOpenOrders: 250 });
});

test('the caps come from vars, and a malformed or out-of-range value falls back to the documented default', () => {
  assert.deepEqual(maxLossCaps({}), { orderLimitMicro: usd('1000'), orderShare: 150000n, dayShare: M, dayLimitMicro: usd('10000'), creditMinMicro: usd('2000'),
    maxAgeMs: MAX_AGE_MS, maxDayOpenOrders: 250 });
  for (const raw of ['1.5', '-0.1', 'x', '', undefined, null]) assert.equal(shareMillionths(raw, 7n), 7n, String(raw));
  assert.equal(shareMillionths('0', 7n), 0n, 'zero is a share: the owner may close the route');
  assert.equal(shareMillionths(' 0.125 ', 7n), 125000n);
  assert.equal(maxLossCaps({ EQUITY_CAP_MAX_AGE_MS: '0' }).maxAgeMs, MAX_AGE_MS);
  assert.equal(maxLossCaps({ EQUITY_CAP_MAX_AGE_MS: 'soon' }).maxAgeMs, MAX_AGE_MS);
  assert.equal(maxLossCaps({ MAX_ORDER_MAX_LOSS_USD: '-5' }).orderLimitMicro, usd('1000'));
  assert.deepEqual([percent(150000n), percent(125000n), percent(M), shareText(150000n), shareText(M)], ['15%', '12.5%', '100%', '0.15', '1']);
  // Caps round down, never in the order's favour; negative equity is none.
  const limits = maxLossCaps({});
  assert.equal(orderCapMicro(limits, usd('3333.333333')), usd('499.999999'));
  assert.equal(orderCapMicro(limits, usd('10000')), usd('1000'));
  assert.equal(orderCapMicro(limits, -usd('50')), 0n);
  assert.equal(dayCapMicro(limits, usd('20000')), usd('10000'));
  assert.equal(dayCapMicro(limits, usd('481.65')), usd('481.65'));
  assert.equal(dayCapMicro(maxLossCaps({ MAX_DAY_USD_ALPACA: '300' }), usd('481.65')), usd('300'));
  assert.deepEqual([formatUsdDown(usd('750.009999')), formatUsdDown(-usd('0.001')), formatUsdDown(0n)], ['750.00', '-0.01', '0.00']);
});

// ------------------------------------------------------------------------------------------------ the gate

test('per order: an open at the cap passes and one cent over is refused; the cap is the lower of $1,000 and 15% of equity', () => {
  for (const [equity, cap] of [['5000.00', '750.00'], ['10000.00', '1000.00'], ['481.65', '72.24']]) {
    const gate = gateWith(equity);
    const over = open(gate, (Number(cap) + 0.01).toFixed(2));
    assert.equal(over.ok, false, equity);
    assert.deepEqual([over.status, over.cap], [403, 'order']);
    assert.match(over.error, new RegExp(`^Order maximum loss \\$${(Number(cap) + 0.01).toFixed(2).replace('.', '\\.')} exceeds the per-order cap of \\$${cap.replace('.', '\\.')} `));
    assert.equal(gate.status(NOW).today.orders, 0, 'a refusal spends nothing');
    assert.equal(open(gate, cap).ok, true, `${equity}: exactly the cap passes`);
  }
});

test('per day: the opening maximum loss accumulates to 100% of equity and one cent over is refused; exits are not counted in it', () => {
  const gate = gateWith('2000.00');  // $300 an order, $2,000 a day
  for (let i = 0; i < 6; i += 1) assert.equal(open(gate, '300').ok, true);
  assert.equal(open(gate, '200').ok, true);
  assert.equal(gate.maxLossStatus(NOW).day_open_max_loss_usd, '2000.00');
  const over = open(gate, '0.01');
  assert.deepEqual([over.ok, over.status, over.cap], [false, 403, 'day_max_loss']);
  assert.equal(over.error, 'Order maximum loss $0.01 would pass today\'s opening maximum-loss cap of $2000.00 (already $2000.00).');
  // Exits go on a spent day, of any size, and leave the opening maximum loss where it was.
  assert.equal(exit(gate).ok, true);
  assert.equal(exit(gate, '5000').ok, true, 'a $5,000 sell_to_close meets no dollar cap');
  assert.equal(gate.maxLossStatus(NOW).day_open_max_loss_usd, '2000.00');
  assert.equal(gate.status(NOW).today.orders, 9);
  // The next trading day starts at zero.
  const tomorrow = Date.parse('2026-09-29T14:00:00Z');
  withEquity(gate, '2000.00', tomorrow);
  assert.equal(gate.reserve({ micro: String(usd('300')), venue: 'alpaca', at: tomorrow }).ok, true);
});

test('MAX_DAY_USD_ALPACA is the backstop: at $20,000 of equity the day\'s opening maximum loss stops at $10,000', () => {
  const gate = gateWith('20000.00');
  for (let i = 0; i < 10; i += 1) assert.equal(open(gate, '1000').ok, true, String(i));
  const over = open(gate, '0.01');
  assert.equal(over.cap, 'day_max_loss');
  assert.match(over.error, /cap of \$10000\.00 \(already \$10000\.00\)/);
  assert.equal(gate.capsExhausted(NOW), true, 'the day is spent');
});

test('orders a day: 300, exits included; opens stop at 250; the 301st is refused whatever it is', () => {
  const gate = gateWith('100000.00');
  for (let i = 0; i < 125; i += 1) {
    assert.equal(open(gate, '1').ok, true);
    assert.equal(exit(gate).ok, true);
  }
  assert.equal(open(gate, '1').cap, 'day_open_orders', 'the last 50 are kept for exits');
  for (let i = 0; i < 50; i += 1) assert.equal(exit(gate).ok, true);
  const refused = exit(gate);
  assert.deepEqual([refused.ok, refused.status, refused.cap], [false, 403, 'day_orders']);
  assert.match(refused.error, /count cap of 300/);
  assert.equal(open(gate, '1').cap, 'day_open_orders');
  assert.equal(gate.maxLossStatus(NOW).orders_today, 300);
  assert.equal(gate.maxLossStatus(NOW).max_day_orders, 300);
});

test('a credit structure opens at $2,000.00 of equity and not at $1,999.99; a debit open needs no threshold', () => {
  const under = gateWith('1999.99');
  const refused = open(under, '62', { credit: true });
  assert.deepEqual([refused.ok, refused.status, refused.cap], [false, 403, 'credit_equity']);
  assert.equal(refused.error, 'A credit structure opens only while the real account\'s equity is at least $2000.00; it reads $1999.99.');
  assert.equal(open(under, '62').ok, true, 'the same maximum loss as a debit type');
  assert.equal(under.maxLossStatus(NOW).credit_opens_admitted, false);
  const at = gateWith('2000.00');
  assert.equal(open(at, '62', { credit: true }).ok, true);
  assert.equal(at.maxLossStatus(NOW).credit_opens_admitted, true);
});

test('no reading, a failed one, a stale one or one from well in the future refuses every open with a 503; exits pass', () => {
  const cases = [
    ['none', gate => gate],
    ['failed', gate => { gate.recordAccountEquity({ ok: false, at: NOW, error: 'alpaca account: HTTP 500' }); return gate; }],
    ['stale by a millisecond', gate => withEquity(gate, '5000.00', NOW, 120001)],
    ['from the future', gate => withEquity(gate, '5000.00', NOW + 60001)],
  ];
  for (const [name, make] of cases) {
    const gate = make(gateAt());
    for (const credit of [false, true]) {
      const refused = open(gate, '1', { credit });
      assert.deepEqual([refused.ok, refused.status, refused.cap], [false, 503, 'equity'], name);
      assert.match(refused.error, /has not been read in the last 120 seconds/);
    }
    assert.equal(exit(gate).ok, true, `${name}: an exit is never blocked by the reading`);
  }
  assert.equal(open(withEquity(gateAt(), '5000.00', NOW, 120000), '1').ok, true, 'exactly two minutes old is young enough');
  assert.equal(open(withEquity(gateAt(), '5000.00', NOW + 60000), '1').ok, true);
  assert.equal(open(withEquity(gateAt({ EQUITY_CAP_MAX_AGE_MS: '1000' }), '5000.00', NOW, 1001), '1').status, 503);
  // A negative equity is a reading: it admits no open, as a cap of zero.
  const negative = gateAt();
  negative.recordAccountEquity({ ok: true, at: NOW, equity_micro: String(-usd('12.50')) });
  assert.equal(open(negative, '0.01').cap, 'order');
  assert.equal(negative.maxLossStatus(NOW).equity.usd, '-12.50');
});

test('a refund gives an open\'s maximum loss back; a day row from before this deploy counts its notional as opened; the kill switch stops exits', () => {
  const gate = gateWith('1000.00');  // $150 an order
  const held = open(gate, '100');
  assert.equal(held.opening, String(usd('100')));
  assert.deepEqual(gate.refund(held), { ok: true });
  assert.equal(gate.maxLossStatus(NOW).day_open_max_loss_usd, '0.00');
  assert.equal(gate.status(NOW).today.orders, 0);
  // A row written by the code before the caps by maximum loss has no `alpaca_open`: its $400 is taken as opened (errs high).
  const store = memoryStore({ [DAY_KEY]: JSON.stringify({ day: TODAY, orders: 3, notional: String(usd('400')) }) });
  const upgraded = withEquity(createGate({ store, env: env(), now: () => NOW }), '500.00', NOW);
  assert.equal(upgraded.reserve({ micro: String(usd('75')), venue: 'alpaca' }).ok, true);
  assert.equal(upgraded.reserve({ micro: String(usd('25.01')), venue: 'alpaca' }).cap, 'day_max_loss');
  // A Kalshi order keeps the row's opening maximum loss as it was.
  assert.equal(upgraded.reserve({ micro: String(usd('1')), venue: 'kalshi' }).ok, true);
  assert.equal(JSON.parse(store.get(DAY_KEY)).alpaca_open, String(usd('475')));
  upgraded.setKill(true, NOW);
  assert.equal(upgraded.reserve({ micro: '1', venue: 'alpaca', exit: true }).status, 423);
});

test('the reading is stored in its own key, and never replaces the profit index\'s reading', () => {
  const store = memoryStore();
  const gate = createGate({ store, env: env(), now: () => NOW });
  assert.deepEqual(gate.recordAccountEquity({ ok: true, at: NOW, equity_micro: '5000000000' }), { ok: true, at: NOW, equity_micro: '5000000000' });
  assert.equal(ACCOUNT_EQUITY_KEY, 'alpaca-equity');
  assert.ok(store.map.has('alpaca-equity'));
  assert.equal(gate.equity(), null, 'the frontier profit index keeps its own reading');
  // Anything that is not a clean reading is stored as a failure.
  for (const bad of [null, { ok: true, at: NOW, equity_micro: '12.5' }, { ok: true, at: 'soon', equity_micro: '1' }, { ok: 'yes', at: NOW, equity_micro: '1' }]) {
    assert.equal(gate.recordAccountEquity(bad).ok, false, JSON.stringify(bad));
  }
});

// ------------------------------------------------------------------------------------------------ the reading

test('the account is read with the real key, read-only, no redirect followed; the reading rounds down', async () => {
  const tape = alpacaVenue({ account: { equity: '5694.3799999', cash: '10', status: 'ACTIVE' } });
  const row = await readAccountEquity(env(), { fetcher: tape.fetcher, now: () => NOW });
  assert.deepEqual(row, { ok: true, at: NOW, equity_micro: '5694379999' });
  const [call] = tape.calls;
  assert.deepEqual([call.url, call.method, call.redirect, call.headers['APCA-API-KEY-ID'], call.headers['APCA-API-SECRET-KEY']],
    ['https://api.alpaca.markets/v2/account', 'GET', 'manual', 'AK-REAL', 'alpaca-real-secret']);
  for (const [account, why] of [
    [500, /HTTP 500/], [302, /HTTP 302/], [{ cash: '10' }, /no equity field/], [{ equity: null }, /no equity field/],
    [{ equity: 'lots' }, /no equity field/], ['not json', /unreadable answer/], [new TypeError('fetch failed'), /fetch failed/],
  ]) {
    const failed = await readAccountEquity(env(), { fetcher: alpacaVenue({ account }).fetcher, now: () => NOW });
    assert.equal(failed.ok, false, String(why));
    assert.match(failed.error, /^alpaca account: /);
    assert.match(failed.error, why);
  }
  const unkeyed = alpacaVenue();
  assert.match((await readAccountEquity(env({ ALPACA_SECRET_KEY: '' }), { fetcher: unkeyed.fetcher, now: () => NOW })).error, /secret key is missing/);
  assert.equal(unkeyed.calls.length, 0);
  assert.equal(freshEquity({ ok: true, at: NOW, equity_micro: '5' }, NOW, 1000), 5n);
});

test('an open reads the account when the stored reading is older than two minutes, and not while it is younger', async () => {
  let clock = NOW;
  const gate = gateAt({}, () => clock);
  const tape = alpacaVenue();
  const at = () => clock;
  assert.equal((await send(mleg(VERTICAL, '0.10'), { gate, tape, clock: at })).status, 200);
  assert.equal(tape.accountReads().length, 1);
  clock = NOW + 120000;
  assert.equal((await send(mleg(VERTICAL, '0.10'), { gate, tape, clock: at })).status, 200);
  assert.equal(tape.accountReads().length, 1, 'two minutes old: used as it is');
  clock = NOW + 120001;
  assert.equal((await send(mleg(VERTICAL, '0.10'), { gate, tape, clock: at })).status, 200);
  assert.equal(tape.accountReads().length, 2, 'older: read again');
  assert.equal(gate.accountEquity().at, NOW + 120001);
  assert.equal(tape.orders().length, 3);
});

test('an unreadable account refuses an open with a 503 the House can retry: nothing is reserved or sent', async () => {
  for (const [account, why] of [[500, /HTTP 500/], [302, /HTTP 302/], [{ cash: '5' }, /no equity field/], ['not json', /unreadable answer/],
    [new TypeError('fetch failed'), /fetch failed/]]) {
    for (const body of [mleg(OPENS[6][1], OPENS[6][2]), mleg(VERTICAL, '0.50'), mleg(OPENS[4][1], OPENS[4][2])]) {
      const { status, body: answer, gate, tape, response } = await send(body, { tape: alpacaVenue({ account }) });
      assert.equal(status, 503, String(why));
      assert.equal(response.headers.get('Retry-After'), '30');
      assert.match(answer.error, /^Cannot read the real account's equity \(alpaca account: /);
      assert.match(answer.error, why);
      assert.match(answer.error, /no older than 120 seconds, so nothing was sent/);
      assert.equal(tape.orders().length, 0);
      assert.equal(gate.status(NOW).today.orders, 0);
    }
  }
  // Without the real keys the account cannot be read: no open goes.
  const unkeyed = await send(mleg(VERTICAL, '0.10'), { settings: { ALPACA_SECRET_KEY: '' } });
  assert.equal(unkeyed.status, 503);
  // A reading the gate itself finds stale (its own clock) is refused there too, with the same retry.
  const gate = gateAt();
  const stale = { accountEquity: async () => ({ ok: true, at: NOW, equity_micro: '5000000000' }), recordAccountEquity: async row => row,
    reserve: async request => gate.reserve(request), status: async () => gate.status() };
  const refused = await send(mleg(VERTICAL, '0.10'), { gate: stale });
  assert.equal(refused.status, 503);
  assert.equal(refused.body.cap, 'equity');
  assert.equal(refused.response.headers.get('Retry-After'), '30');
  assert.equal(refused.tape.orders().length, 0);
});

test('exits are never blocked by the equity read: closes, buy-backs, sells to close and stock closes go with the account unreadable, and never read it', async () => {
  const positions = [...HOLDING, { symbol: 'SPY260911C00586000', qty: '-1', side: 'short' }, { symbol: 'SPY261016C00740000', qty: '3', side: 'long' }, ...SHARES];
  const exits = [
    mleg(closing(VERTICAL), '-0.60'),
    { symbol: 'SPY260911C00586000', qty: '1', side: 'buy', position_intent: 'buy_to_close', type: 'limit', limit_price: '0.30', time_in_force: 'day' },
    buy('9.00', '3', { side: 'sell', position_intent: STC }),
    SALE,
  ];
  const gate = gateAt();
  for (const body of exits) {
    const tape = alpacaVenue({ account: new TypeError('fetch failed'), positions });
    const { status } = await send(body, { gate, tape });
    assert.equal(status, 200, JSON.stringify(body));
    assert.equal(tape.accountReads().length, 0);
    assert.equal(tape.orders().length, 1);
  }
  assert.equal(gate.maxLossStatus(NOW).day_open_max_loss_usd, '0.00', 'no exit counts as opened');
  assert.equal(gate.status(NOW).today.orders, 4);
});

// ------------------------------------------------------------------------------------------------ through the front door

test('per order through the front door: at $5,000 of equity a $750.00 open passes and $750.01 is refused, a structure or a single contract', async () => {
  const gate = gateAt(LONGS);
  const tape = alpacaVenue({ equity: '5000.00' });
  for (const [body, fits] of [
    [buy('7.5001'), false], [buy('7.50'), true],
    [mleg(VERTICAL, '0.750001', { qty: '10' }), false], [mleg(VERTICAL, '0.75', { qty: '10' }), true],
  ]) {
    const { status, body: answer } = await send(body, { gate, tape, settings: LONGS });
    assert.equal(status, fits ? 200 : 403, JSON.stringify(body));
    if (!fits) assert.match(answer.error, /exceeds the per-order cap of \$750\.00 \(the lower of \$1000\.00 and 15% of \$5000\.00 equity\)\.$/);
  }
  assert.equal(tape.orders().length, 2);
  assert.equal(gate.maxLossStatus(NOW).day_open_max_loss_usd, '1500.00');
});

test('the day\'s opening maximum loss accumulates through the front door; closes pass a spent day and are not counted in it', async () => {
  const gate = gateAt();
  const tape = alpacaVenue({ equity: '500.00', positions: [...HOLDING, ...SHARES] });  // $75 an order, $500 a day
  for (let i = 0; i < 6; i += 1) assert.equal((await send(mleg(VERTICAL, '0.75'), { gate, tape })).status, 200);
  assert.equal((await send(mleg(VERTICAL, '0.50'), { gate, tape })).status, 200);
  const over = await send(mleg(VERTICAL, '0.0001'), { gate, tape });
  assert.equal(over.status, 403);
  assert.equal(over.body.cap, 'day_max_loss');
  assert.match(over.body.error, /^Order maximum loss \$0\.01 would pass today's opening maximum-loss cap of \$500\.00 \(already \$500\.00\)\.$/);
  assert.equal((await send(mleg(closing(VERTICAL), '-0.60'), { gate, tape })).status, 200);
  assert.equal((await send(SALE, { gate, tape })).status, 200);
  const health = gate.maxLossStatus(NOW);
  assert.deepEqual([health.day_open_max_loss_usd, health.orders_today], ['500.00', 9]);
});

test('credit types open at $2,000.00 of the gateway\'s own reading and not at $1,999.99; debit types open under it', async () => {
  const credits = OPENS.filter(([type]) => ['credit_vertical', 'iron_condor', 'iron_butterfly'].includes(type));
  const debits = OPENS.filter(([type]) => ['debit_vertical', 'long_butterfly'].includes(type));
  for (const [type, legs, limit] of credits) {
    const under = await send(mleg(legs, limit), { tape: alpacaVenue({ equity: '1999.99' }) });
    assert.equal(under.status, 403, type);
    assert.equal(under.body.cap, 'credit_equity');
    assert.equal(under.tape.orders().length, 0);
    const at = await send(mleg(legs, limit), { tape: alpacaVenue({ equity: '2000.00' }) });
    assert.equal(at.status, 200, type);
  }
  for (const [type, legs, limit] of debits) {
    assert.equal((await send(mleg(legs, limit), { tape: alpacaVenue({ equity: '1999.99' }) })).status, 200, type);
  }
  // Calendars, diagonals, straddles and strangles are not in the deployed list (Alpaca closes them in no one order).
  for (const [type, legs, limit] of OPENS.filter(([t]) => ['calendar', 'diagonal', 'long_straddle', 'long_strangle'].includes(t))) {
    const refused = await send(mleg(legs, limit), { tape: alpacaVenue({ equity: '9000.00' }) });
    assert.equal(refused.status, 400, type);
    assert.match(refused.body.error, /is not admitted on the real account/);
  }
});

test('300 orders a day through the front door, exits included; opens stop at 250; the 301st is refused', async () => {
  const gate = gateAt();
  const tape = alpacaVenue({ equity: '100000.00', positions: [{ symbol: 'SPY261016C00740000', qty: '1000', side: 'long' }] });
  const sale = buy('0.01', '1', { side: 'sell', position_intent: STC });
  for (let i = 0; i < 125; i += 1) {
    assert.equal((await send(mleg(VERTICAL, '0.01'), { gate, tape })).status, 200);
    assert.equal((await send(sale, { gate, tape })).status, 200);
  }
  const shut = await send(mleg(VERTICAL, '0.01'), { gate, tape });
  assert.deepEqual([shut.status, shut.body.cap], [403, 'day_open_orders']);
  for (let i = 0; i < 50; i += 1) assert.equal((await send(sale, { gate, tape })).status, 200, `exit ${251 + i}`);
  for (const [body, cap] of [[sale, 'day_orders'], [mleg(VERTICAL, '0.01'), 'day_open_orders']]) {
    const refused = await send(body, { gate, tape });
    assert.equal(refused.status, 403);
    assert.equal(refused.body.cap, cap);
  }
  assert.equal(tape.orders().length, 300);
});

// ------------------------------------------------------------------------------------------------ stock: closes only

test('a stock sale of shares held long, and a buy covering a short, each up to what is held, go as exits; nothing else does', async () => {
  const long = SHARES;
  const short = [{ symbol: 'AAPL', qty: '-100', qty_available: '-100', side: 'short', asset_class: 'us_equity' }];
  const cases = [
    [SALE, long, 200],
    [{ ...SALE, type: 'limit', limit_price: '229.50', extended_hours: false }, long, 200],
    [{ ...SALE, qty: '101' }, long, /AAPL long \(101 needed, 100 long held\)/],
    [SALE, [{ ...long[0], qty_available: '40' }], /AAPL long \(100 needed, 40 long held\)/],
    [SALE, short, /AAPL long \(100 needed, 100 short held\)/],
    [{ ...SALE, side: 'buy' }, short, 200],
    [{ ...SALE, side: 'buy', type: 'limit', limit_price: '231' }, short, 200],
    [{ ...SALE, side: 'buy', qty: '101' }, short, /AAPL short \(101 needed, 100 short held\)/],
    [{ ...SALE, side: 'buy', qty: '1' }, long, /AAPL short \(1 needed, 100 long held\)/],
    [{ ...SALE, symbol: 'MSFT' }, long, /MSFT long \(100 needed, none held\)/],
    [{ ...SALE, qty: '0.5' }, [{ symbol: 'AAPL', qty: '0.5', side: 'long' }], 200],
    [{ ...SALE, qty: '0.6' }, [{ symbol: 'AAPL', qty: '0.5', side: 'long' }], /AAPL long \(0\.6 needed, 0\.5 long held\)/],
  ];
  for (const [body, positions, want] of cases) {
    const gate = gateAt();
    const tape = alpacaVenue({ positions, account: 500 });
    const { status, body: answer } = await send(body, { gate, tape });
    if (want === 200) {
      assert.equal(status, 200, JSON.stringify(body));
      assert.deepEqual(JSON.parse(tape.orders()[0].body), body, 'forwarded exactly as sent');
      assert.deepEqual(gate.status(NOW).today, { day: TODAY, orders: 1, notional_usd: '0.01' }, 'an exit at one micro-dollar');
    } else {
      assert.equal(status, 400, JSON.stringify(body));
      assert.match(answer.error, /^A stock order on the real account must close shares it holds: /);
      assert.match(answer.error, want);
      assert.equal(tape.orders().length, 0);
      assert.equal(gate.status(NOW).today.orders, 0);
    }
    assert.equal(tape.accountReads().length, 0, 'a close reads no equity');
  }
});

test('crypto, dollar-sized, intent-carrying and unpriced stock orders are refused before anything is read; the practice account is unchanged', async () => {
  for (const [body, why] of [
    [{ ...SALE, symbol: 'BTC/USD', qty: '0.001' }, /Crypto is not traded on the real account/],
    [{ ...SALE, side: 'buy', symbol: 'ETH/USD', qty: '0.1', time_in_force: 'gtc' }, /Crypto is not traded/],
    [{ symbol: 'AAPL', notional: '500', side: 'sell', type: 'market', time_in_force: 'day' }, /sized in shares \(qty\), never in dollars/],
    [{ ...SALE, position_intent: 'sell_to_close' }, /carries no position_intent/],
    [{ ...SALE, type: 'limit', limit_price: '0' }, /positive limit price/],
    [{ ...SALE, qty: '-5' }, /qty is missing or not positive/],
    [{ ...SALE, side: 'sell_short' }, /a buy or a sell/],
    [{ ...SALE, type: 'stop', stop_price: '1' }, /Only market and limit orders/],
  ]) {
    const tape = alpacaVenue({ positions: SHARES });
    const { status, body: answer, gate } = await send(body, { tape, headers: { 'X-LTCM-Purpose': 'exit' } });
    assert.equal(status, 400, JSON.stringify(body));
    assert.match(answer.error, why);
    assert.equal(tape.calls.length, 0, 'nothing read, nothing sent');
    assert.equal(gate.status(NOW).today.orders, 0);
  }
  // The practice account takes the House's stock and crypto orders exactly as before, unmetered.
  for (const body of [{ ...SALE, side: 'buy', type: 'limit', limit_price: '10' }, { ...SALE, symbol: 'BTC/USD', qty: '0.001' }]) {
    const tape = alpacaVenue();
    const practice = await send(body, { tape, venue: 'alpaca-paper', settings: { ALPACA_PAPER_KEY_ID: 'PK', ALPACA_PAPER_SECRET_KEY: 'paper-secret' } });
    assert.equal(practice.status, 200);
    assert.equal(tape.calls[0].url, 'https://paper-api.alpaca.markets/v2/orders');
    assert.equal(practice.gate.status(NOW).today.orders, 0);
  }
});

test('a stock close with its positions unread is a 424 that reserves nothing; the kill switch stops it; a second close is not sent from the cache', async () => {
  for (const positions of [503, 'not json', '{"positions":[]}', new TypeError('fetch failed')]) {
    const tape = alpacaVenue({ positions });
    const { status, body, gate } = await send(SALE, { tape });
    assert.equal(status, 424, String(positions));
    assert.match(body.error, /^Cannot check that the real account holds these shares: /);
    assert.equal(tape.orders().length, 0);
    assert.equal(gate.status(NOW).today.orders, 0);
  }
  const killed = gateAt();
  killed.setKill(true, NOW);
  const halted = await send(SALE, { gate: killed, tape: alpacaVenue({ positions: SHARES }) });
  assert.equal(halted.status, 423);
  assert.equal(halted.tape.orders().length, 0);
  // With a cache, the 100 shares sold leave the cached reading: a second sale of them within it is refused.
  const cached = { POSITIONS_CACHE_MS: '60000' };
  const gate = gateAt(cached);
  assert.equal((await send(SALE, { gate, settings: cached, tape: alpacaVenue({ positions: SHARES }) })).status, 200);
  const again = await send({ ...SALE, qty: '1' }, { gate, settings: cached, tape: alpacaVenue({ positions: SHARES }) });
  assert.equal(again.status, 400);
  assert.match(again.body.error, /AAPL long \(1 needed, none held\)/);
  assert.equal(again.tape.calls.length, 0, 'read from the cache, nothing sent');
  await send(SALE, { tape: alpacaVenue({ positions: [] }) });  // a read with the cache off empties it for what follows
});

test('the stock-close reading and the exact counts it uses', () => {
  assert.deepEqual(realStockClose(SALE), { body: { kind: 'stock', qty: '100', legs: [{ symbol: 'AAPL', ratio_qty: '1', side: 'sell', position_intent: 'sell_to_close' }] } });
  assert.equal(realStockClose({ ...SALE, side: 'buy' }).body.legs[0].position_intent, 'buy_to_close');
  assert.equal(realStockClose({ ...SALE, symbol: 'BRK.B' }).body.legs[0].symbol, 'BRK.B');
  assert.deepEqual([picoUnits(5n * 10n ** 12n), picoUnits(-(5n * 10n ** 11n)), picoUnits(0n)], ['5', '-0.5', '0']);
  const half = realStockClose({ ...SALE, qty: '0.5' }).body;
  assert.deepEqual(closedLegRows(half), [{ symbol: 'AAPL', qty: '-0.5' }]);
  assert.equal(closeLegsHeldError(half, [{ symbol: 'AAPL', qty: '0.5', side: 'long' }]), null);
  // Option legs read exactly as before: whole counts.
  assert.deepEqual(closedLegRows(mleg(closing(VERTICAL), '-0.60', { qty: '3' })), [{ symbol: occ(580), qty: '-3' }, { symbol: occ(581), qty: '3' }]);
});

// ------------------------------------------------------------------------------------------------ health

test('health reports the reading and its age, the per-order cap now, the day\'s opening maximum loss and its cap, credit opens, and 300 orders', async () => {
  let clock = NOW;
  const gate = gateAt({}, () => clock);
  const tape = alpacaVenue({ equity: '2500.00' });
  const health = async () => (await route(new Request(`${GATEWAY}/v1/health`, { headers: { Authorization: `Bearer ${TOKEN}` } }), env(),
    { gate, fetcher: tape.fetcher, now: () => clock })).json();
  assert.equal((await send(mleg(VERTICAL, '0.70'), { gate, tape, clock: () => clock })).status, 200);
  clock = NOW + 30000;
  const reads = tape.calls.length;
  let body = await health();
  assert.equal(tape.calls.length, reads, 'health reads no venue');
  assert.deepEqual(body.max_loss, {
    venue: 'alpaca',
    equity: { usd: '2500.00', read_at: '2026-09-28T14:00:00.000Z', age_seconds: 30, ok: true, error: null, fresh: true, max_age_seconds: 120 },
    order_cap_usd: '375.00', max_order_max_loss_usd: '1000.00', order_equity_share: '0.15',
    day_open_max_loss_usd: '70.00', day_open_cap_usd: '2500.00', day_equity_share: '1', max_day_usd_alpaca: '10000.00',
    opens_admitted: true, credit_opens_admitted: true, credit_min_equity_usd: '2000.00',
    orders_today: 1, max_day_open_orders: 250, max_day_orders: 300,
  });
  // Two minutes on, the reading is too old to open against until an order reads the account again.
  clock = NOW + 120001;
  body = await health();
  assert.deepEqual([body.max_loss.equity.fresh, body.max_loss.order_cap_usd, body.max_loss.day_open_cap_usd, body.max_loss.opens_admitted,
    body.max_loss.credit_opens_admitted, body.max_loss.equity.usd], [false, null, null, false, false, '2500.00']);
  // A failed reading says why; the kill switch admits no open.
  gate.recordAccountEquity({ ok: false, at: clock, error: 'alpaca account: HTTP 500' });
  body = await health();
  assert.deepEqual([body.max_loss.equity.ok, body.max_loss.equity.error, body.max_loss.equity.usd], [false, 'alpaca account: HTTP 500', null]);
  withEquity(gate, '2500.00', clock);
  gate.setKill(true, clock);
  body = await health();
  assert.deepEqual([body.max_loss.equity.fresh, body.max_loss.opens_admitted, body.max_loss.credit_opens_admitted], [true, false, false]);
});

test('the Durable Object exposes the account reading, its record in one transaction', () => {
  const source = readFileSync(new URL('../worker.mjs', import.meta.url), 'utf8');
  assert.match(source, /\baccountEquity\(\) \{ return this\.gate\.accountEquity\(\); \}/);
  assert.match(source, /\brecordAccountEquity\(reading\) \{ return this\.ctx\.storage\.transactionSync\(\(\) => this\.gate\.recordAccountEquity\(reading\)\); \}/);
});

test('refreshAccountEquity never throws: a gate that cannot answer is read around, and the open is judged by the gate', async () => {
  const broken = { accountEquity: async () => { throw new Error('rpc'); }, recordAccountEquity: async () => { throw new Error('rpc'); } };
  const reading = await refreshAccountEquity(env(), broken, { fetcher: alpacaVenue().fetcher, now: () => NOW });
  assert.deepEqual(reading, { ok: true, at: NOW, equity_micro: '5000000000' });
  const failed = await refreshAccountEquity(env(), broken, { fetcher: alpacaVenue({ account: 500 }).fetcher, now: () => NOW });
  assert.equal(failed.ok, false);
});

// ------------------------------------------------------------------------------------------------ the review (Sept 26, 2026)
// The adversarial review of Wave 5's gateway work: each test below failed on the code it reviewed.

const FIVE = 'debit_vertical,credit_vertical,iron_condor,iron_butterfly,long_butterfly';
const PUT = 'SPY261016P00600000';
const CALL = 'SPY261016C00740000';

test('REVIEW m7/m15: a single-leg buy_to_open is refused on the real account unless OPTION_STRUCTURES_REAL names long_call or long_put by its right', async () => {
  for (const [symbol, type] of [[CALL, 'long_call'], [PUT, 'long_put']]) {
    for (const headers of [{}, { 'X-LTCM-Purpose': 'exit' }]) {
      const tape = alpacaVenue();
      const refused = await send(buy('0.10', '1', { symbol }), { tape, headers });
      assert.equal(refused.status, 400, type);
      assert.equal(refused.body.error, `A ${type} is not admitted on the real account: OPTION_STRUCTURES_REAL admits ${FIVE.split(',').join(', ')}.`);
      assert.equal(tape.calls.length, 0, 'refused before anything is read or sent');
      assert.equal(refused.gate.status(NOW).today.orders, 0);
    }
  }
  // Named, the right it names opens, and only that one.
  for (const [named, call, put] of [['long_call', 200, 400], ['long_put', 400, 200], ['long_call,long_put', 200, 200]]) {
    const settings = { OPTION_STRUCTURES_REAL: `${FIVE},${named}` };
    assert.equal((await send(buy('0.10'), { settings })).status, call, `${named}: call`);
    assert.equal((await send(buy('0.10', '1', { symbol: PUT }), { settings })).status, put, `${named}: put`);
  }
  // The practice account takes it as before, unmetered.
  const practice = await send(buy('0.10'), { venue: 'alpaca-paper', settings: { ALPACA_PAPER_KEY_ID: 'PK', ALPACA_PAPER_SECRET_KEY: 'paper-secret' } });
  assert.equal(practice.status, 200);
  assert.equal(practice.gate.status(NOW).today.orders, 0);
});

test('REVIEW m14: a real single-leg sell_to_close must sell a contract held long for its qty (qty_available honoured); unread positions are a 424', async () => {
  const sell = qty => buy('0.40', qty, { side: 'sell', position_intent: STC });
  const cases = [
    [[{ symbol: CALL, qty: '3', side: 'long' }], '3', 200],
    [[{ symbol: CALL, qty: '3', side: 'long' }], '4', /SPY261016C00740000 long \(4 needed, 3 long held\)/],
    [[{ symbol: CALL, qty: '3', qty_available: '1', side: 'long' }], '3', /long \(3 needed, 1 long held\)/],
    [[{ symbol: CALL, qty: '-3', side: 'short' }], '1', /long \(1 needed, 3 short held\)/],
    [[], '1', /long \(1 needed, none held\)/],
  ];
  for (const [positions, qty, want] of cases) {
    const tape = alpacaVenue({ positions, account: 500 });
    const { status, body, gate } = await send(sell(qty), { tape });
    assert.equal(tape.accountReads().length, 0, 'an exit reads no equity');
    assert.equal(tape.positionReads().length, 1, 'it reads the positions');
    if (want === 200) {
      assert.equal(status, 200);
      assert.equal(tape.orders().length, 1);
      continue;
    }
    assert.equal(status, 400, JSON.stringify(positions));
    assert.match(body.error, /^A single-leg sell_to_close must sell a long leg the real account holds: /);
    assert.match(body.error, want);
    assert.equal(tape.orders().length, 0);
    assert.equal(gate.status(NOW).today.orders, 0);
  }
  for (const positions of [503, 'not json', new TypeError('fetch failed')]) {
    const tape = alpacaVenue({ positions });
    const unread = await send(sell('1'), { tape });
    assert.equal(unread.status, 424, String(positions));
    assert.equal(unread.body.cap, 'positions');
    assert.match(unread.body.error, /^Cannot check that the real account holds this contract long: /);
    assert.equal(tape.orders().length, 0);
  }
  // With a cache, the contracts sold leave the cached reading: a second sale of them within it is refused.
  const cached = { POSITIONS_CACHE_MS: '60000' };
  const gate = gateAt(cached);
  assert.equal((await send(sell('3'), { gate, settings: cached, tape: alpacaVenue({ positions: [{ symbol: CALL, qty: '3', side: 'long' }] }) })).status, 200);
  assert.equal((await send(sell('1'), { gate, settings: cached, tape: alpacaVenue({ positions: [{ symbol: CALL, qty: '3', side: 'long' }] }) })).status, 400);
  await send(sell('1'), { tape: alpacaVenue({ positions: [] }) });  // a read with the cache off empties it for what follows
});

test('REVIEW m8/m12: every refusal made before anything is forwarded that is a 5xx names its cap; the one that may hide an order names none', async () => {
  const kalshiOrder = { ticker: 'KXTEST-26', side: 'bid', count: '3.00', price: '0.6500', client_order_id: 'oi-1' };
  const ask = (path, init = {}) => new Request(`${GATEWAY}${path}`, { ...init, headers: { Authorization: `Bearer ${TOKEN}`, ...(init.headers || {}) } });
  const stale = gateAt();
  const staleStub = { accountEquity: async () => ({ ok: true, at: NOW, equity_micro: '5000000000' }), recordAccountEquity: async row => row,
    reserve: async request => stale.reserve(request), refund: async request => stale.refund(request) };
  const scenarios = [
    ['equity unreadable', () => send(mleg(VERTICAL, '0.50'), { tape: alpacaVenue({ account: 500 }) }), 503, 'equity'],
    ['equity stale at the gate', () => send(mleg(VERTICAL, '0.50'), { gate: staleStub }), 503, 'equity'],
    ['alpaca credentials, an open', () => send(mleg(VERTICAL, '0.50'), { settings: { ALPACA_SECRET_KEY: '' }, gate: gateWith('5000.00', { ALPACA_SECRET_KEY: '' }) }), 503, 'credentials'],
    ['alpaca credentials, a read', async () => {
      const response = await route(ask('/v1/alpaca/v2/account'), env({ ALPACA_SECRET_KEY: '' }), { gate: gateAt(), fetcher: alpacaVenue().fetcher, now: () => NOW });
      return { status: response.status, body: await response.json(), tape: alpacaVenue() };
    }, 503, 'credentials'],
    ['kalshi credentials, an order', async () => {
      const tape = alpacaVenue();
      const response = await route(ask('/v1/kalshi/portfolio/events/orders', { method: 'POST', body: JSON.stringify(kalshiOrder) }),
        env({ KALSHI_KEY_ID: 'k', KALSHI_PRIVATE_KEY: 'not a key' }), { gate: gateAt(), fetcher: tape.fetcher, now: () => NOW });
      return { status: response.status, body: await response.json(), tape };
    }, 503, 'credentials'],
    ['positions unread, a close', () => send(mleg(closing(VERTICAL), '-0.60'), { tape: alpacaVenue({ positions: 500 }) }), 424, 'positions'],
    ['positions unread, a buy-back', () => send({ symbol: 'SPY260911C00586000', qty: '1', side: 'buy', position_intent: 'buy_to_close', type: 'limit',
      limit_price: '0.30', time_in_force: 'day' }, { tape: alpacaVenue({ positions: 500 }) }), 424, 'positions'],
    ['positions unread, a stock close', () => send(SALE, { tape: alpacaVenue({ positions: 500 }) }), 424, 'positions'],
  ];
  for (const [name, run, status, cap] of scenarios) {
    const { status: got, body, tape } = await run();
    assert.equal(got, status, name);
    assert.equal(body.cap, cap, `${name}: the body names why nothing was sent`);
    assert.equal(tape.orders().length, 0, `${name}: nothing forwarded`);
  }
  assert.equal(stale.status(NOW).today.orders, 0);
  // No answer after dispatch may be an order the venue took: it names no cap, and keeps its reservation.
  const lost = await send(mleg(VERTICAL, '0.50'), { gate: gateWith('5000.00'),
    tape: { ...alpacaVenue(), fetcher: async () => { throw Object.assign(new Error('nope'), { name: 'TimeoutError' }); } } });
  assert.equal(lost.status, 502);
  assert.equal(lost.body.cap, undefined);
  assert.equal(lost.gate.status(NOW).today.orders, 1);
  // The Worker's own setup refusal, before any route, names its cap too.
  const source = readFileSync(new URL('../worker.mjs', import.meta.url), 'utf8');
  assert.match(source, /json\(\{ error: 'Gateway setup is incomplete\.', cap: 'setup' \}, 503\)/);
});

test('REVIEW C6/C10: exits keep room: an open stops once today\'s orders reach MAX_DAY_OPEN_ORDERS (250), exits go on to MAX_DAY_ORDERS (300)', async () => {
  assert.equal(maxLossCaps(DEPLOYED).maxDayOpenOrders, 250);
  for (const raw of [undefined, '', 'many', '-1']) assert.equal(maxLossCaps({ MAX_DAY_OPEN_ORDERS: raw }).maxDayOpenOrders, 250, String(raw));
  const gate = gateWith('100000.00');
  for (let i = 0; i < 125; i += 1) assert.equal(exit(gate).ok, true);
  for (let i = 0; i < 124; i += 1) assert.equal(open(gate, '1').ok, true);
  assert.equal(open(gate, '1').ok, true, 'the 250th order may still open');
  const shut = open(gate, '1');
  assert.deepEqual([shut.ok, shut.status, shut.cap], [false, 403, 'day_open_orders']);
  assert.equal(shut.error, 'Today\'s 250 orders leave no room to open: the last 50 of the day\'s 300 are kept for exits.');
  assert.deepEqual([gate.maxLossStatus(NOW).opens_admitted, gate.maxLossStatus(NOW).credit_opens_admitted], [false, false], 'health says so');
  for (let i = 0; i < 50; i += 1) assert.equal(exit(gate).ok, true, `exit ${251 + i}`);
  assert.equal(exit(gate).cap, 'day_orders');
  assert.equal(open(gate, '1').cap, 'day_open_orders');
  assert.equal(gate.maxLossStatus(NOW).max_day_open_orders, 250);
  // Kalshi keeps the whole day's count.
  const kalshi = gateWith('100000.00');
  for (let i = 0; i < 260; i += 1) assert.equal(exit(kalshi).ok, true);
  assert.equal(kalshi.reserve({ micro: String(usd('1')), venue: 'kalshi' }).ok, true);
});

test('REVIEW m17: MAX_DAY_USD is Kalshi\'s day notional ($4,000) again; the real account\'s opening maximum loss has MAX_DAY_USD_ALPACA ($10,000)', () => {
  assert.equal(maxLossCaps(DEPLOYED).dayLimitMicro, usd('10000'));
  assert.equal(maxLossCaps({}).dayLimitMicro, usd('10000'));
  const gate = gateWith('20000.00');
  for (let i = 0; i < 10; i += 1) assert.equal(open(gate, '1000').ok, true, 'MAX_DAY_USD ($4,000) does not bind the real account');
  assert.match(open(gate, '0.01').error, /cap of \$10000\.00 \(already \$10000\.00\)/);
  // Kalshi's $4,000 counts Kalshi alone: $10,000 opened on Alpaca leaves it whole.
  for (let i = 0; i < 80; i += 1) assert.equal(gate.reserve({ micro: String(usd('50')), venue: 'kalshi' }).ok, true, `kalshi ${i}`);
  const full = gate.reserve({ micro: String(usd('0.01')), venue: 'kalshi' });
  assert.equal(full.cap, 'day_notional');
  assert.match(full.error, /today's cap of \$4000\.00 \(already \$4000\.00\)/);
  assert.equal(gate.status(NOW).caps.max_day_usd, '4000.00');
  assert.equal(gate.maxLossStatus(NOW).max_day_usd_alpaca, '10000.00');
  // Each envelope binds its own venue only.
  const tight = gateWith('20000.00', { MAX_DAY_USD_ALPACA: '100' });
  assert.equal(open(tight, '100').ok, true);
  assert.equal(open(tight, '0.01').cap, 'day_max_loss');
  assert.equal(tight.reserve({ micro: String(usd('50')), venue: 'kalshi' }).ok, true);
  // A refunded Alpaca order gives its notional back to the Alpaca record, not to Kalshi's day.
  const back = gateWith('20000.00', { MAX_DAY_USD: '10' });
  const held = open(back, '500');
  back.refund(held);
  assert.equal(back.reserve({ micro: String(usd('10')), venue: 'kalshi' }).ok, true);
  // A row from before this deploy has no Alpaca notional: all of it is counted as Kalshi's (errs high).
  const store = memoryStore({ [DAY_KEY]: JSON.stringify({ day: TODAY, orders: 3, notional: String(usd('3999')), alpaca_open: '0' }) });
  const upgraded = createGate({ store, env: env(), now: () => NOW });
  assert.equal(upgraded.reserve({ micro: String(usd('1.01')), venue: 'kalshi' }).cap, 'day_notional');
});
