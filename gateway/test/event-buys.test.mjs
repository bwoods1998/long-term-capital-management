// The event lane's real buys (release R2, gateway G2; PREREG-EVL-1 section 8). While STOCK_EVENT_BUYS is "on" (and
// STOCK_BUYS_REAL with it), the real account admits a whole-share limit-on-open or limit-on-close buy ("opg" / "cls") of a
// US common stock the House's eligible list names for the New York day, checked again against the venue's own asset
// record and SIP daily bars (price >= $3, 20-session ADV >= $1M), its limit at most 1.25 x the previous SIP close,
// metered at qty x limit, held book-wide to 10% of equity a name, inside every other stock cap, stopped by the kill
// switch. "off" ships. Sales of the shares are closes like any other, in any time in force the venue takes.

import assert from 'node:assert/strict';
import test, { beforeEach } from 'node:test';
import { readFileSync } from 'node:fs';

import { PICO } from '../lib/money.mjs';
import {
  EVENT_TIFS, EVENT_EXCHANGES, EVENT_ADV_SESSIONS, EVENT_LIST_MAX, isEventBuy, stockEventBuysEnabled, eventBuyOrder,
  eventAssetError, eventBarFacts, eventLimitError, eligibleList, nyDay,
} from '../lib/caps.mjs';
import { stockCaps, stockEventShare, stockSymbolCapMicro, STOCK_EVENT_SHARE_MAX } from '../lib/account.mjs';
import { createGate, STOCK_ELIGIBLE_KEY } from '../lib/gate.mjs';
import { route, forgetEventFacts } from '../lib/router.mjs';
import { memoryStore, alpacaVenue, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-12T13:20:00Z');  // a Monday, 09:20 in New York: inside the opg send window
const TODAY = '2026-10-12';
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const M = 1000000n;
const usd = dollars => {
  const [whole, fraction = ''] = String(dollars).split('.');
  return BigInt(whole) * M + BigInt(fraction.padEnd(6, '0').slice(0, 6));
};

//: The vars as wrangler.jsonc deploys them, with the event lane's buys switched on (the owner's step at the first Probe).
const DEPLOYED = { STOCK_BUYS_REAL: 'on', STOCK_ETF_EQUITY_SHARE: '0.5', STOCK_SINGLE_EQUITY_SHARE: '0.2', STOCK_MAX_EQUITY_MULTIPLE: '1',
  STOCK_DAY_EQUITY_MULTIPLE: '4', STOCK_EVENT_BUYS: 'off' };
const ON = { STOCK_EVENT_BUYS: 'on' };
const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN, ALPACA_KEY_ID: 'AK-REAL', ALPACA_SECRET_KEY: 'alpaca-real-secret',
  OPTION_STRUCTURES_REAL: 'debit_vertical,long_butterfly,long_call,long_put',
  MAX_ORDER_USD: '75', MAX_DAY_USD: '4000', MAX_DAY_USD_ALPACA: '10000', MAX_DAY_ORDERS: '300', MAX_DAY_OPEN_ORDERS: '250',
  MAX_ORDER_MAX_LOSS_USD: '1000', MAX_ORDER_EQUITY_SHARE: '0.25', MAX_DAY_EQUITY_SHARE: '1.0', CREDIT_MIN_EQUITY_USD: '2000',
  EQUITY_CAP_MAX_AGE_MS: '120000', CAP_TIMEZONE: 'America/New_York', ...DEPLOYED, POSITIONS_CACHE_MS: '0', ...extra,
});
const gateAt = (settings = {}, clock = () => NOW, store = memoryStore()) => createGate({ store, env: env(settings), now: clock });
// Each case starts from a fresh isolate's readings: the router keeps an event buy's asset and bars for the day.
beforeEach(() => forgetEventFacts());
const listed = (gate, symbols, day = TODAY) => gate.stockEligibleSet({ day, symbols, sha: 'test', at: NOW });

/** A cash account of $10,000 (multiplier 1), its buying power its cash. */
const CASH = { equity: '10000.00', buying_power: '10000.00', multiplier: '1', status: 'ACTIVE' };
const MARGIN = { equity: '10000.00', buying_power: '20000.00', regt_buying_power: '20000.00', multiplier: '2', status: 'ACTIVE' };

/** Weekday sessions before `day` (no holiday in the span the tests use), newest last. */
function sessionsBefore(day, n) {
  const out = [];
  let at = Date.parse(`${day}T12:00:00Z`);
  while (out.length < n) {
    at -= 86400000;
    const weekday = new Date(at).getUTCDay();
    if (weekday !== 0 && weekday !== 6) out.unshift(new Date(at).toISOString().slice(0, 10));
  }
  return out;
}
/** SIP daily bars as the venue answers them: `n` sessions before TODAY at `close` and `volume` (and today's, still trading). */
const dailyBars = ({ n = 25, close = 40, volume = 100000, today = true, last = null } = {}) => ({
  symbol: 'X', next_page_token: null,
  bars: [...sessionsBefore(TODAY, n).map((day, i, all) => ({ t: `${day}T04:00:00Z`, o: close, h: close, l: close,
    c: i === all.length - 1 && last !== null ? last : close, v: volume, n: 10, vw: close })),
  ...(today ? [{ t: `${TODAY}T04:00:00Z`, o: 1, h: 1, l: 1, c: 1, v: 1, n: 1, vw: 1 }] : [])],
});
const asset = (symbol, extra = {}) => ({ id: `id-${symbol}`, class: 'us_equity', exchange: 'NASDAQ', symbol, status: 'active',
  tradable: true, marginable: true, shortable: true, fractionable: true, ...extra });

const json = value => new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
/**
 * The real account as `alpacaVenue` plays it, and beside it the two readings an event buy makes: `GET v2/assets/<sym>`
 * answers `assets[sym]` (a body, an HTTP status, or an Error) and `GET v2/stocks/<sym>/bars` answers `bars[sym]`.
 */
function eventVenue({ assets = {}, bars = {}, ...rest } = {}) {
  const base = alpacaVenue({ account: CASH, ...rest });
  const reads = [];
  const answer = value => {
    if (value instanceof Error) return Promise.reject(value);
    if (typeof value === 'number') return new Response('{}', { status: value, headers: { 'Content-Type': 'application/json' } });
    if (value === undefined) return new Response('{"message":"not found"}', { status: 404, headers: { 'Content-Type': 'application/json' } });
    return json(value);
  };
  const fetcher = async (url, init = {}) => {
    const text = String(url);
    const clean = text.split('?')[0];
    const assetMatch = /\/v2\/assets\/([^/]+)$/.exec(clean);
    if (assetMatch && (init.method || 'GET') === 'GET') {
      reads.push({ kind: 'asset', url: text, ...init });
      return answer(assets[decodeURIComponent(assetMatch[1])]);
    }
    const barsMatch = /\/v2\/stocks\/([^/]+)\/bars$/.exec(clean);
    if (barsMatch && (init.method || 'GET') === 'GET') {
      reads.push({ kind: 'bars', url: text, ...init });
      return answer(bars[decodeURIComponent(barsMatch[1])]);
    }
    return base.fetcher(url, init);
  };
  return { ...base, fetcher, reads, assetReads: () => reads.filter(r => r.kind === 'asset'), barReads: () => reads.filter(r => r.kind === 'bars') };
}
/** A venue where `symbol` qualifies: an active NASDAQ common stock with 25 sessions at $40 x 100,000 shares ($4M a day). */
const good = (symbol = 'ACME', extra = {}) => eventVenue({ assets: { [symbol]: asset(symbol) }, bars: { [symbol]: dailyBars() }, ...extra });

const post = body => new Request(`${GATEWAY}/v1/alpaca/v2/orders`, { method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, body: JSON.stringify(body) });
const send = async (body, { settings = ON, gate = null, tape = good(), clock = () => NOW, list = ['ACME'] } = {}) => {
  const g = gate ?? gateAt(settings, clock);
  if (gate === null && list) listed(g, list);
  const response = await route(post(body), env(settings), { gate: g, fetcher: tape.fetcher, now: clock });
  return { response, status: response.status, body: await response.clone().json().catch(() => null), gate: g, tape };
};
/** A whole-share limit-on-open buy of `qty` shares of `symbol` at `limit`. */
const opg = (symbol, qty, limit, extra = {}) => ({ symbol, qty, side: 'buy', type: 'limit', limit_price: limit, time_in_force: 'opg',
  client_order_id: `lq-ev-${symbol}-${qty}`, ...extra });
const cls = (symbol, qty, limit, extra = {}) => opg(symbol, qty, limit, { time_in_force: 'cls', ...extra });
const long = (symbol, qty, marketValue) => ({ symbol, qty, qty_available: qty, side: 'long', market_value: marketValue, asset_class: 'us_equity' });

const admitted = (result, message = '') => {
  assert.equal(result.status, 200, `${message} ${JSON.stringify(result.body)}`);
  assert.equal(result.tape.orders().length, 1, `${message}: forwarded once`);
};
const refused = (result, status, cap, pattern, message = '', { before = 0 } = {}) => {
  assert.equal(result.status, status, `${message} ${JSON.stringify(result.body)}`);
  if (cap !== undefined) assert.equal(result.body.cap, cap, message);
  if (pattern) assert.match(result.body.error, pattern, message);
  assert.equal(result.tape.orders().length, 0, `${message}: nothing forwarded`);
  assert.equal(result.gate.status(NOW).today.orders, before, `${message}: nothing reserved`);
};

// ------------------------------------------------------------------------------------------------ the switch and the numbers

test('the deployed event switch is "off", and only "on" (any case, trimmed) turns it on', () => {
  const config = readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const lines = config.split('\n').filter(line => line.includes('"STOCK_EVENT_BUYS"'));
  assert.equal(lines.length, 1);
  assert.equal(JSON.parse(/:\s*("(?:[^"\\]|\\.)*")/.exec(lines[0])[1]), 'off');
  for (const raw of ['on', 'ON', ' On ']) assert.equal(stockEventBuysEnabled({ STOCK_EVENT_BUYS: raw }), true, raw);
  for (const raw of ['off', '', 'yes', 'true', '1', 'onn', undefined, null]) assert.equal(stockEventBuysEnabled({ STOCK_EVENT_BUYS: raw }), false, String(raw));
  assert.deepEqual(EVENT_TIFS, ['opg', 'cls']);
  assert.deepEqual(EVENT_EXCHANGES, ['NYSE', 'NASDAQ', 'AMEX', 'ARCA', 'BATS']);
  assert.equal(EVENT_ADV_SESSIONS, 20);
});

test('an event name\'s share is the single-stock share and never above the goal\'s 10% of equity, whatever the var says', () => {
  assert.equal(STOCK_EVENT_SHARE_MAX, 100000n);
  assert.equal(stockEventShare(stockCaps(DEPLOYED)), 100000n, 'STOCK_SINGLE_EQUITY_SHARE 0.2: still 10%');
  assert.equal(stockEventShare(stockCaps({ STOCK_SINGLE_EQUITY_SHARE: '0.1' })), 100000n);
  assert.equal(stockEventShare(stockCaps({ STOCK_SINGLE_EQUITY_SHARE: '0.05' })), 50000n, 'a lower var lowers it');
  assert.equal(stockEventShare(stockCaps({ STOCK_SINGLE_EQUITY_SHARE: '0' })), 0n, 'zero closes it');
  assert.equal(stockSymbolCapMicro(stockCaps(DEPLOYED), 'event', usd('10000')), usd('1000'));
  assert.equal(stockSymbolCapMicro(stockCaps(DEPLOYED), 'stock', usd('10000')), usd('2000'), 'the list\'s stocks keep their share');
  assert.equal(stockSymbolCapMicro(stockCaps(DEPLOYED), 'event', usd('1884.15')), usd('188.415'));
});

// ------------------------------------------------------------------------------------------------ the shape

test('an event buy is a whole-share limit order in the opening or the closing auction, of a stock that is no ETF', () => {
  assert.equal(isEventBuy(opg('ACME', '3', '50')), true);
  assert.equal(isEventBuy(cls('ACME', '3', '50')), true);
  assert.equal(isEventBuy({ ...opg('ACME', '3', '50'), time_in_force: 'day' }), false, 'a day buy is the list\'s, not the lane\'s');
  assert.equal(isEventBuy({ ...opg('ACME', '3', '50'), side: 'sell' }), false, 'a sale is a close');
  assert.equal(isEventBuy(null), false);
  assert.deepEqual(eventBuyOrder(opg('ACME', '3', '50.25')), { symbol: 'ACME', qty: 3n * PICO, limit: 50250000000000n, micro: usd('150.75'), tif: 'opg' });
  assert.deepEqual(eventBuyOrder(cls('BRK.B', 1, '480.1234')).micro, usd('480.1234'), 'a JSON integer qty reads as its count');
  assert.equal(eventBuyOrder(opg('ACME', '3', '50', { extended_hours: false, order_class: 'simple' })).error, undefined);
  for (const [body, why] of [
    [opg('ACME', '1.5', '50'), /whole number of shares/],
    [opg('ACME', '0', '50'), /whole number of shares/],
    [opg('ACME', '-1', '50'), /whole number of shares/],
    [opg('ACME', 1.5, '50'), /whole number of shares/],
    [opg('ACME', '01', '50'), /whole number of shares/],
    [opg('ACME', '1000000000', '50'), /whole number of shares/],
    [{ ...opg('ACME', '1', '50'), qty: undefined, notional: '50' }, /never in dollars/],
    [{ ...opg('ACME', '1', '50'), type: 'market', limit_price: undefined }, /a limit order/],
    [opg('ACME', '1', '50', { extended_hours: true }), /never in extended hours/],
    [opg('ACME', '1', '50', { position_intent: 'buy_to_open' }), /no position_intent/],
    [opg('ACME', '1', '0'), /positive limit_price/],
    [opg('ACME', '1', '50.12345'), /at most four decimal places/],
    [opg('SPY', '1', '500'), /SPY is an ETF/],
    [opg('BTC/USD', '1', '50'), /US stock ticker/],
    [opg('acme', '1', '50'), /US stock ticker/],
  ]) {
    assert.match(eventBuyOrder(body).error ?? '', why, JSON.stringify(body));
  }
});

test('the House\'s eligible list: its day (today or a week ahead), at most 5,000 tickers, no ETF, none twice, sorted', () => {
  assert.deepEqual(eligibleList({ day: TODAY, symbols: ['ZZZ', 'ACME', 'BRK.B'] }, TODAY), { day: TODAY, symbols: ['ACME', 'BRK.B', 'ZZZ'] });
  assert.deepEqual(eligibleList({ day: '2026-10-19', symbols: [] }, TODAY), { day: '2026-10-19', symbols: [] });
  for (const [body, why] of [
    [null, /a JSON object/],
    [[], /a JSON object/],
    [{ day: TODAY, symbols: ['ACME'], extra: 1 }, /only day and symbols/],
    [{ day: '2026-10-11', symbols: ['ACME'] }, /for 2026-10-12 or a day up to 2026-10-19, not 2026-10-11/],
    [{ day: '2026-10-20', symbols: ['ACME'] }, /up to 2026-10-19/],
    [{ day: '12/10/2026', symbols: ['ACME'] }, /YYYY-MM-DD/],
    [{ day: TODAY, symbols: 'ACME' }, /a list of at most 5000/],
    [{ day: TODAY, symbols: Array.from({ length: EVENT_LIST_MAX + 1 }, (_, i) => `A${String.fromCharCode(65 + (i % 26))}`) }, /at most 5000/],
    [{ day: TODAY, symbols: ['acme'] }, /not a US stock ticker/],
    [{ day: TODAY, symbols: ['QQQ'] }, /QQQ is an ETF/],
    [{ day: TODAY, symbols: ['ACME', 'ACME'] }, /listed twice/],
  ]) {
    assert.match(eligibleList(body, TODAY).error ?? '', why, JSON.stringify(body)?.slice(0, 80));
  }
});

test('the venue\'s asset record admits only an active, tradable US equity on a listed exchange', () => {
  assert.equal(eventAssetError(asset('ACME'), 'ACME'), null);
  for (const exchange of EVENT_EXCHANGES) assert.equal(eventAssetError(asset('ACME', { exchange }), 'ACME'), null, exchange);
  for (const [record, why] of [
    [null, /no asset record/],
    [asset('OTHER'), /not ACME's/],
    [asset('ACME', { class: 'crypto' }), /not a US equity/],
    [asset('ACME', { status: 'inactive' }), /not active and tradable/],
    [asset('ACME', { tradable: false }), /not active and tradable/],
    [asset('ACME', { exchange: 'OTC' }), /listed on "OTC"/],
    [asset('ACME', { exchange: 'CRYPTO' }), /listed on "CRYPTO"/],
  ]) {
    assert.match(eventAssetError(record, 'ACME') ?? '', why, JSON.stringify(record));
  }
});

test('the SIP daily bars: the previous close at least $3.00 and the last 20 sessions\' mean dollar volume at least $1,000,000', () => {
  const facts = eventBarFacts(dailyBars().bars, TODAY, 'ACME');
  assert.equal(facts.prevClose, 40n * PICO);
  assert.equal(facts.adv, 4000000n * PICO);
  assert.equal(facts.sessions, 25, 'today\'s bar, still trading, is left out');
  assert.equal(facts.last, '2026-10-09');
  // The boundaries are admitted: exactly $3.00 and exactly $1,000,000 a day.
  assert.equal(eventBarFacts(dailyBars({ close: 3, volume: 333334 }).bars, TODAY, 'X').error, undefined);
  assert.equal(eventBarFacts(dailyBars({ close: 10, volume: 100000 }).bars, TODAY, 'X').error, undefined, '$1,000,000 exactly');
  assert.equal(eventBarFacts(dailyBars({ close: 10, volume: 100000, last: 2.99 }).bars, TODAY, 'X').cap, 'stock_price');
  assert.match(eventBarFacts(dailyBars({ close: 10, volume: 99999 }).bars, TODAY, 'X').error, /under the event lane's \$1,000,000/);
  assert.equal(eventBarFacts(dailyBars({ close: 10, volume: 99999 }).bars, TODAY, 'X').cap, 'stock_adv');
  assert.equal(eventBarFacts(dailyBars({ n: 19 }).bars, TODAY, 'X').cap, 'stock_adv', 'fewer than 20 sessions');
  assert.match(eventBarFacts(dailyBars({ n: 19 }).bars, TODAY, 'X').error, /19 SIP daily bars before 2026-10-12/);
  // Only the LAST 20 sessions count: an old quiet month does not hold a name back, an old busy one does not let it in.
  const quietThenBusy = dailyBars({ n: 25, volume: 100000 }).bars.map((bar, i) => (i < 5 ? { ...bar, v: 1 } : bar));
  assert.equal(eventBarFacts(quietThenBusy, TODAY, 'X').adv, 4000000n * PICO);
  const busyThenQuiet = dailyBars({ n: 25, volume: 10 }).bars.map((bar, i) => (i < 5 ? { ...bar, v: 10 ** 9 } : bar));
  assert.equal(eventBarFacts(busyThenQuiet, TODAY, 'X').cap, 'stock_adv');
  // A reading that is not one: no list, a bar with no time, two bars on one day, an unreadable close or volume.
  assert.equal(eventBarFacts(null, TODAY, 'X').cap, 'bars');
  assert.equal(eventBarFacts([{ c: 1, v: 1 }], TODAY, 'X').cap, 'bars');
  const twice = dailyBars().bars;
  assert.equal(eventBarFacts([...twice, { ...twice[3] }], TODAY, 'X').cap, 'bars');
  assert.equal(eventBarFacts(dailyBars().bars.map((bar, i) => (i === 3 ? { ...bar, c: 'x' } : bar)), TODAY, 'X').cap, 'bars');
  assert.equal(eventBarFacts(dailyBars().bars.map((bar, i) => (i === 3 ? { ...bar, v: -1 } : bar)), TODAY, 'X').cap, 'bars');
});

test('the limit is at most 1.25 x the previous SIP close, exactly', () => {
  assert.equal(eventLimitError(50n * PICO, 40n * PICO, 'ACME'), null, '$50.00 on a $40.00 close: exactly 1.25x');
  assert.match(eventLimitError(50000100000000n, 40n * PICO, 'ACME'), /above 1\.25 x its previous SIP close of \$40/);
  assert.equal(eventLimitError(4162500000000n, 3330000000000n, 'X'), null, '$4.1625 on $3.33');
  assert.match(eventLimitError(4170000000000n, 3330000000000n, 'X'), /above 1\.25/);
  assert.match(eventLimitError(1n, 0n, 'X'), /no previous SIP close/);
  assert.equal(nyDay(Date.parse('2026-10-12T03:59:00Z')), '2026-10-11', 'New York days, not UTC days');
  assert.equal(nyDay(NOW), TODAY);
});

// ------------------------------------------------------------------------------------------------ through the router

test('"off" ships: an event buy is refused before anything is read, and so it is while STOCK_BUYS_REAL is off', async () => {
  for (const settings of [{}, { STOCK_EVENT_BUYS: 'on', STOCK_BUYS_REAL: 'off' }]) {
    const result = await send(opg('ACME', '2', '50'), { settings });
    refused(result, 403, 'stock_event_buys', /Event buys are off \((STOCK_EVENT_BUYS|STOCK_BUYS_REAL) is not "on"\): nothing was read or sent\./,
      JSON.stringify(settings));
    assert.equal(result.tape.calls.length + result.tape.reads.length, 0, 'not one reading of the account or the venue');
  }
  // The shape is judged before the switch: a malformed buy says why it is malformed.
  refused(await send(opg('ACME', '1.5', '50'), { settings: {} }), 400, undefined, /whole number of shares/);
});

test('within every rule an event buy goes: forwarded exactly as sent, read from the venue with the real keys, an open in the day\'s count', async () => {
  const gate = gateAt(ON);
  listed(gate, ['ACME']);
  const tape = good();
  const result = await send(opg('ACME', '2', '50'), { gate, tape });  // $100.00, at exactly 1.25 x the $40 close
  admitted(result);
  assert.deepEqual(JSON.parse(tape.orders()[0].body), opg('ACME', '2', '50'));
  assert.equal(tape.orders()[0].url, 'https://api.alpaca.markets/v2/orders');
  const [assetRead] = tape.assetReads();
  const [barsRead] = tape.barReads();
  assert.equal(assetRead.url, 'https://api.alpaca.markets/v2/assets/ACME', 'the asset from the trading host');
  const bars = new URL(barsRead.url);
  assert.equal(`${bars.origin}${bars.pathname}`, 'https://data.alpaca.markets/v2/stocks/ACME/bars', 'the bars from the data host');
  assert.deepEqual(Object.fromEntries([...bars.searchParams].filter(([k]) => k !== 'end')),
    { timeframe: '1Day', start: '2026-08-28', feed: 'sip', adjustment: 'raw', limit: '1000' });
  assert.ok(Date.parse(bars.searchParams.get('end')) <= NOW - 16 * 60000, 'the SIP end is 16 minutes back (the Basic plan)');
  for (const read of [assetRead, barsRead, ...tape.accountReads(), ...tape.openOrderReads(), ...tape.positionReads()]) {
    assert.equal(read.method, 'GET');
    assert.equal(read.redirect, 'manual');
    assert.equal(read.headers['APCA-API-KEY-ID'], 'AK-REAL');
  }
  assert.deepEqual(gate.status(NOW).today, { day: TODAY, orders: 1, notional_usd: '100.00' });
  assert.equal(gate.status(NOW).stock_buys.day_buys_usd, '100.00', 'metered at qty x limit');
  assert.equal(gate.maxLossStatus(NOW).day_open_max_loss_usd, '0.00', 'never the options\' opening maximum loss');
  // A limit-on-close buy goes the same way, and a name of STOCK_UNIVERSE's stocks too (its day buys stay the list's).
  admitted(await send(cls('ACME', '1', '49.99')));
  admitted(await send(opg('AAPL', '1', '250'), { list: ['AAPL'], tape: eventVenue({ assets: { AAPL: asset('AAPL') }, bars: { AAPL: dailyBars({ close: 200, volume: 10 ** 6 }) } }) }));
});

test('the House\'s eligible list decides which names may go, and only on its own New York day', async () => {
  refused(await send(opg('ACME', '1', '50'), { list: null }), 403, 'stock_eligible', /has published no eligible list/);
  refused(await send(opg('ACME', '1', '50'), { list: ['OTHER'] }), 403, 'stock_eligible', /ACME is not on the House's eligible list of 2026-10-12/);
  const stale = gateAt(ON);
  listed(stale, ['ACME'], '2026-10-09');
  refused(await send(opg('ACME', '1', '50'), { gate: stale }), 403, 'stock_eligible', /is for 2026-10-09, not 2026-10-12/);
  const early = gateAt(ON);
  listed(early, ['ACME'], '2026-10-13');
  refused(await send(opg('ACME', '1', '50'), { gate: early }), 403, 'stock_eligible', /is for 2026-10-13, not 2026-10-12/);
  // No venue was read for a name off the list.
  const off = await send(opg('ACME', '1', '50'), { list: ['OTHER'] });
  assert.equal(off.tape.reads.length + off.tape.calls.length, 0);
});

test('THE GATE RE-CHECKS THE LIST in the step that reserves: a list replaced after the router read it is the one that counts', () => {
  const gate = gateAt(ON);
  listed(gate, ['ACME']);
  const stock = { symbol: 'ACME', event: true, equity_micro: String(usd('10000')), buying_power_micro: String(usd('10000')),
    multiplier: String(M), symbol_held_micro: '0', total_held_micro: '0', options_held_micro: '0', read_at: NOW, open_buys: [], statuses: [] };
  listed(gate, ['OTHER']);
  const refusedHere = gate.reserve({ micro: String(usd('100')), venue: 'alpaca', stock, at: NOW });
  assert.deepEqual([refusedHere.ok, refusedHere.status, refusedHere.cap], [false, 403, 'stock_eligible']);
  assert.match(refusedHere.error, /ACME is not on the House's eligible list/);
  listed(gate, ['ACME', 'OTHER']);
  assert.equal(gate.reserve({ micro: String(usd('100')), venue: 'alpaca', stock, at: NOW }).ok, true);
  // An ETF of the list is never an event buy, even when a stock fact says "event"; and off is off in the gate too.
  assert.equal(gate.reserve({ micro: '1', venue: 'alpaca', stock: { ...stock, symbol: 'SPY' }, at: NOW }).cap, 'stock');
  const closed = gateAt({});
  closed.stockEligibleSet({ day: TODAY, symbols: ['ACME'], sha: 'x', at: NOW });
  assert.equal(closed.reserve({ micro: String(usd('100')), venue: 'alpaca', stock, at: NOW }).cap, 'stock_event_buys');
});

test('the venue\'s asset record must admit the name: active, tradable, a US equity on a listed exchange', async () => {
  for (const [record, why] of [
    [asset('ACME', { status: 'inactive' }), /not active and tradable/],
    [asset('ACME', { tradable: false }), /not active and tradable/],
    [asset('ACME', { exchange: 'OTC' }), /listed on "OTC"/],
    [asset('ACME', { class: 'us_option' }), /not a US equity/],
  ]) {
    forgetEventFacts();
    const tape = eventVenue({ assets: { ACME: record }, bars: { ACME: dailyBars() } });
    const result = await send(opg('ACME', '1', '50'), { tape });
    refused(result, 403, 'stock_asset', why);
    assert.equal(tape.barReads().length, 0, 'no bars read for a name the asset already refuses');
  }
  // A reading that could not be made sends nothing and is a 424 the House sends again: never a verdict.
  for (const failure of [500, 404, new Error('reset')]) {
    forgetEventFacts();
    const tape = eventVenue({ assets: { ACME: failure }, bars: { ACME: dailyBars() } });
    refused(await send(opg('ACME', '1', '50'), { tape }), 424, 'asset', /Cannot read the venue's asset record of ACME/);
  }
});

test('the bars must admit the name: $3 and up, $1M a day of SIP dollar volume over 20 sessions; an unread reading is a 424', async () => {
  const bars = value => {
    forgetEventFacts();
    return eventVenue({ assets: { ACME: asset('ACME') }, bars: { ACME: value } });
  };
  refused(await send(opg('ACME', '1', '3.5'), { tape: bars(dailyBars({ close: 10, volume: 10 ** 6, last: 2.99 })) }), 403, 'stock_price', /under the event lane's \$3\.00/);
  refused(await send(opg('ACME', '1', '50'), { tape: bars(dailyBars({ close: 10, volume: 99999 })) }), 403, 'stock_adv', /under the event lane's \$1,000,000/);
  refused(await send(opg('ACME', '1', '50'), { tape: bars(dailyBars({ n: 12 })) }), 403, 'stock_adv', /needs 20 sessions/);
  refused(await send(opg('ACME', '1', '50'), { tape: bars(500) }), 424, 'bars', /Cannot read the SIP daily bars of ACME/);
  refused(await send(opg('ACME', '1', '50'), { tape: bars({ bars: 'x' }) }), 424, 'bars', /were not a list/);
});

test('the limit is never above 1.25 x the previous SIP close; at exactly 1.25x it goes', async () => {
  refused(await send(opg('ACME', '1', '50.01')), 403, 'stock_limit', /above 1\.25 x its previous SIP close of \$40/);
  admitted(await send(opg('ACME', '1', '50.00')));
  admitted(await send(opg('ACME', '1', '30')), 'a lower limit is the program\'s own choice');
});

test('a name\'s asset and bars are read once a New York day; a verdict is kept, a failed reading is not', async () => {
  const gate = gateAt(ON);
  listed(gate, ['ACME', 'CHEAP']);
  const tape = eventVenue({ assets: { ACME: asset('ACME'), CHEAP: asset('CHEAP') },
    bars: { ACME: dailyBars(), CHEAP: dailyBars({ close: 2 }) } });
  admitted(await send(opg('ACME', '1', '50', { client_order_id: 'a-1' }), { gate, tape }));
  assert.equal((await send(opg('ACME', '1', '50', { client_order_id: 'a-2' }), { gate, tape })).status, 200);
  assert.deepEqual([tape.assetReads().filter(r => r.url.endsWith('/ACME')).length, tape.barReads().filter(r => r.url.includes('/ACME/')).length], [1, 1]);
  for (let i = 0; i < 2; i += 1) assert.equal((await send(opg('CHEAP', '1', '2.5', { client_order_id: `c-${i}` }), { gate, tape })).body.cap, 'stock_price');
  assert.equal(tape.barReads().filter(r => r.url.includes('/CHEAP/')).length, 1, 'the refusal is kept for the day');
  // The next New York day reads again.
  const tomorrow = () => NOW + 86400000;
  const gate2 = gateAt(ON, tomorrow);
  gate2.stockEligibleSet({ day: '2026-10-13', symbols: ['ACME'], sha: 'x', at: tomorrow() });
  await send(opg('ACME', '1', '50', { client_order_id: 'a-3' }), { gate: gate2, tape, clock: tomorrow });
  assert.equal(tape.assetReads().filter(r => r.url.endsWith('/ACME')).length, 2);
  // A reading that failed is asked again at the next send.
  const flaky = eventVenue({ assets: { FLAKY: 503 }, bars: { FLAKY: dailyBars() } });
  const gate3 = gateAt(ON);
  listed(gate3, ['FLAKY']);
  for (let i = 0; i < 2; i += 1) await send(opg('FLAKY', '1', '50', { client_order_id: `f-${i}` }), { gate: gate3, tape: flaky });
  assert.equal(flaky.assetReads().length, 2);
});

// ------------------------------------------------------------------------------------------------ the caps

test('THE GOAL\'S 10% A NAME, BOOK-WIDE: held + resting buys + buys in flight + this one, at most 10% of equity', async () => {
  // $10,000 equity: at most $1,000 of ACME, whatever STOCK_SINGLE_EQUITY_SHARE (0.2 deployed) allows a list stock.
  admitted(await send(opg('ACME', '20', '50')), '$1,000.00: exactly 10%');
  refused(await send(opg('ACME', '21', '47.62')), 403, 'stock_order', /exceeds the cap for an event-lane stock \(book-wide\) of \$1000\.00 \(10% of \$10000\.00 equity\)/);
  const held = good('ACME', { positions: [long('ACME', '20', '900.00')] });
  admitted(await send(opg('ACME', '2', '50'), { tape: held }), '$900 held + $100 = 10%');
  refused(await send(opg('ACME', '3', '50'), { tape: good('ACME', { positions: [long('ACME', '20', '900.00')] }) }), 403, 'stock_position',
    /would take the position to \$1050\.00, past the cap for an event-lane stock \(book-wide\) of \$1000\.00 \(10% of \$10000\.00 equity; held and on order \$900\.00\)/);
  const resting = good('ACME', { openOrders: [{ id: 'o-1', client_order_id: 'other-1', symbol: 'ACME', qty: '10', filled_qty: '0', side: 'buy', type: 'limit', limit_price: '50', order_class: 'simple', status: 'new' }] });
  refused(await send(opg('ACME', '11', '50'), { tape: resting }), 403, 'stock_position', /held and on order \$500\.00/);
  // A buy admitted and not yet shown by the venue counts too (two programs' sends in the same minute).
  const gate = gateAt(ON);
  listed(gate, ['ACME']);
  admitted(await send(opg('ACME', '12', '50', { client_order_id: 'p1' }), { gate, tape: good() }));
  refused(await send(opg('ACME', '9', '50', { client_order_id: 'p2' }), { gate, tape: good() }), 403, 'stock_position', /would take the position to \$1050\.00/,
    'in flight', { before: 1 });
  // The same at the var's own 10%, and a lower var lowers it.
  admitted(await send(opg('ACME', '20', '50'), { settings: { ...ON, STOCK_SINGLE_EQUITY_SHARE: '0.1' } }));
  refused(await send(opg('ACME', '11', '50'), { settings: { ...ON, STOCK_SINGLE_EQUITY_SHARE: '0.05' } }), 403, 'stock_order', /\(5% of \$10000\.00 equity\)/);
});

test('NO MARGIN: the whole book at most 1x equity on a margin account; buying power and the day\'s line hold too', async () => {
  const full = [long('BIG', '90', '9000.00')];
  admitted(await send(opg('ACME', '20', '50'), { tape: good('ACME', { account: MARGIN, positions: full }) }), '$9,000 + $1,000 = 1x');
  refused(await send(opg('ACME', '20', '50'), { tape: good('ACME', { account: MARGIN, positions: [long('BIG', '90', '9000.01')] }) }),
    403, 'stock_total', /to \$10000\.01, past its cap of \$10000\.00 \(1x \$10000\.00 equity; the account's multiplier is 2, STOCK_MAX_EQUITY_MULTIPLE 1\)/);
  refused(await send(opg('ACME', '20', '50'), { tape: good('ACME', { account: { ...CASH, buying_power: '999.99' } }) }), 403, 'buying_power');
  refused(await send(opg('ACME', '20', '50'), { settings: { ...ON, STOCK_DAY_EQUITY_MULTIPLE: '0.05' } }), 403, 'stock_day');
});

test('THE KILL SWITCH stops an event buy like every order; it never stops the list\'s publication', async () => {
  const gate = gateAt(ON);
  listed(gate, ['ACME']);
  gate.setKill(true, NOW);
  refused(await send(opg('ACME', '1', '50'), { gate, tape: good() }), 423, undefined, /kill switch is engaged/);
  const published = await route(new Request(`${GATEWAY}/v1/stock/eligible`, { method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` },
    body: JSON.stringify({ day: TODAY, symbols: ['ACME', 'BETA'] }) }), env(ON), { gate, now: () => NOW });
  assert.equal(published.status, 200);
});

test('an event buy of a symbol the account holds short is refused as an open: it never covers', async () => {
  const short = good('ACME', { positions: [{ symbol: 'ACME', qty: '-5', side: 'short', market_value: '-200.00', asset_class: 'us_equity' }] });
  refused(await send(opg('ACME', '5', '50'), { tape: short }), 400, undefined, /not admitted as an open: the account holds ACME short/);
});

// ------------------------------------------------------------------------------------------------ sales of event shares

test('SALES OF EVENT SHARES: market and limit sales in the opening and closing auctions are closes of shares held, nothing more', async () => {
  const held = () => good('ACME', { positions: [long('ACME', '20', '900.00')] });
  for (const tif of ['cls', 'opg', 'day']) {
    for (const body of [{ symbol: 'ACME', qty: '20', side: 'sell', type: 'market', time_in_force: tif },
      { symbol: 'ACME', qty: '20', side: 'sell', type: 'limit', limit_price: '30', time_in_force: tif }]) {
      // A sale goes whatever STOCK_EVENT_BUYS says: off as deployed here.
      const result = await send(body, { settings: {}, tape: held(), list: null });
      admitted(result, `${tif} ${body.type}`);
      assert.deepEqual(JSON.parse(result.tape.orders()[0].body), body);
      assert.equal(result.gate.status(NOW).stock_buys.day_buys_usd, '0.00', 'a sale is never metered as a buy');
    }
  }
  refused(await send({ symbol: 'ACME', qty: '21', side: 'sell', type: 'market', time_in_force: 'cls' }, { settings: {}, tape: held() }),
    400, undefined, /must close shares it holds: ACME long \(21 needed, 20 long held\)/);
  refused(await send({ symbol: 'ACME', qty: '1', side: 'sell', type: 'market', time_in_force: 'cls' }, { settings: {}, tape: good() }),
    400, undefined, /must close/);
  const killed = gateAt({});
  killed.setKill(true, NOW);
  refused(await send({ symbol: 'ACME', qty: '20', side: 'sell', type: 'market', time_in_force: 'cls' }, { gate: killed, tape: held() }),
    423, undefined, /kill switch/);
});

// ------------------------------------------------------------------------------------------------ the list's route and health

test('POST /v1/stock/eligible stores the House\'s list with its sha; GET and /v1/health show its day, count and sha, never its names', async () => {
  const store = memoryStore();
  const gate = gateAt(ON, () => NOW, store);
  const call = (method, body, token = TOKEN) => route(new Request(`${GATEWAY}/v1/stock/eligible`, {
    method, headers: token ? { Authorization: `Bearer ${token}` } : {}, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }), env(ON), { gate, now: () => NOW });
  assert.equal((await call('POST', { day: TODAY, symbols: ['ACME'] }, null)).status, 401);
  assert.equal((await call('POST', { day: TODAY, symbols: ['ACME'] }, 'wrong-token-that-is-long-enough-0000000000')).status, 401);
  assert.equal((await call('DELETE')).status, 405);
  const bad = await call('POST', { day: TODAY, symbols: ['SPY'] });
  assert.deepEqual([bad.status, (await bad.json()).cap], [400, 'stock_eligible']);
  const answer = await call('POST', { day: TODAY, symbols: ['ZETA', 'ACME'] });
  assert.equal(answer.status, 200);
  const stored = await answer.json();
  const { createHash } = await import('node:crypto');
  const sha = createHash('sha256').update(`${TODAY}:ACME,ZETA`).digest('hex');
  assert.deepEqual(stored, { ok: true, day: TODAY, count: 2, sha, at: '2026-10-12T13:20:00.000Z' });
  assert.deepEqual(JSON.parse(store.get(STOCK_ELIGIBLE_KEY)).symbols, ['ACME', 'ZETA'], 'kept sorted, in the Gate alone');
  assert.deepEqual(await (await call('GET')).json(), { day: TODAY, count: 2, sha, at: '2026-10-12T13:20:00.000Z' });
  const health = await (await route(new Request(`${GATEWAY}/v1/health`, { headers: { Authorization: `Bearer ${TOKEN}` } }), env(ON), { gate, now: () => NOW })).json();
  assert.deepEqual(health.stock_buys.event_buys, { enabled: true, equity_share: '0.1', eligible: { day: TODAY, count: 2, sha, at: '2026-10-12T13:20:00.000Z' }, admitted: true });
  assert.equal(JSON.stringify(health).includes('ZETA'), false, 'the names stay in the Gate');
  // A list of an earlier day than the one held is refused; the same day's replaces it; a later day's replaces it.
  await call('POST', { day: '2026-10-13', symbols: ['NEXT'] });
  const earlier = await call('POST', { day: TODAY, symbols: ['ACME'] });
  assert.deepEqual([earlier.status, (await earlier.json()).cap], [409, 'stock_eligible']);
  assert.equal((await (await call('GET')).json()).day, '2026-10-13');
  assert.equal((await call('POST', { day: '2026-10-13', symbols: ['NEXT', 'MORE'] })).status, 200);
  assert.equal((await (await call('GET')).json()).count, 2);
});

test('the Durable Object stores the list in one transaction and reads it without a write', () => {
  const source = readFileSync(new URL('../worker.mjs', import.meta.url), 'utf8');
  assert.match(source, /\bstockEligibleSet\(request\) \{ return this\.ctx\.storage\.transactionSync\(\(\) => this\.gate\.stockEligibleSet\(request\)\); \}/);
  assert.match(source, /\bstockEligibleStatus\(\) \{ return this\.gate\.stockEligibleStatus\(\); \}/);
  assert.match(source, /\bstockEligibleHas\(request\) \{ return this\.gate\.stockEligibleHas\(request\); \}/);
});

test('the list\'s own buys are as they were: a day buy of a name off STOCK_UNIVERSE is refused, a list stock\'s day buy goes', async () => {
  const day = { symbol: 'ACME', qty: '2', side: 'buy', type: 'limit', limit_price: '50', time_in_force: 'day', client_order_id: 'd-1' };
  refused(await send(day), 400, undefined, /"ACME" is not on the real account's stock list/);
  const tape = eventVenue({});
  admitted(await send({ ...day, symbol: 'AAPL', limit_price: '250' }, { tape, list: null }));
  assert.equal(tape.reads.length, 0, 'no asset or bars read for the list\'s own buy');
});
