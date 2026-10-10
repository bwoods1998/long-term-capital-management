// Real stock and ETF buys (Oct 10, 2026; the owner's goal: agent programs may trade ETFs, stocks and options with real
// money). While STOCK_BUYS_REAL is "on", the real account admits a LONG-ONLY buy of a listed symbol: a limit day order
// sized in shares, metered at qty x limit_price, an ETF position at most 50% of equity and a single stock at most 20%,
// the whole book at most equity x min(2, the account's multiplier) and never above its buying power, every figure read
// from the account by the gateway itself and failing closed. A sale is still only a close of shares held long, a buy of a
// symbol held short is still only a cover, the kill switch and the day's order counts stop a buy as they stop an option
// open, and the practice account is unchanged.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import {
  stockCaps, stockSymbolCapMicro, stockTotalCapMicro, multiplierMillionths, readStockAccount,
  STOCK_ETF_SHARE_MAX, STOCK_SINGLE_SHARE_MAX, STOCK_MULTIPLE_MAX,
} from '../lib/account.mjs';
import { STOCK_UNIVERSE, stockKind, stockBuysEnabled, stockBuyOrder, heldShares, stockExposure } from '../lib/caps.mjs';
import { createGate, STOCK_PENDING_KEY, STOCK_PENDING_MS, DAY_KEY } from '../lib/gate.mjs';
import { route } from '../lib/router.mjs';
import { memoryStore, alpacaVenue, TOKEN } from './helpers.mjs';

const NOW = Date.parse('2026-10-12T14:00:00Z');  // a Monday, 10:00 in New York
const TODAY = '2026-10-12';
const GATEWAY = 'https://ltcm-gateway.workers.dev';
const M = 1000000n;
const usd = dollars => {
  const [whole, fraction = ''] = String(dollars).split('.');
  return BigInt(whole) * M + BigInt(fraction.padEnd(6, '0').slice(0, 6));
};

//: The stock vars as wrangler.jsonc deploys them (pinned against the file below), beside the options caps.
const STOCK_VARS = { STOCK_BUYS_REAL: 'on', STOCK_ETF_EQUITY_SHARE: '0.5', STOCK_SINGLE_EQUITY_SHARE: '0.2', STOCK_MAX_EQUITY_MULTIPLE: '2' };
const env = (extra = {}) => ({
  GATEWAY_TOKEN: TOKEN, ALPACA_KEY_ID: 'AK-REAL', ALPACA_SECRET_KEY: 'alpaca-real-secret',
  OPTION_STRUCTURES_REAL: 'debit_vertical,long_butterfly,long_call,long_put',
  MAX_ORDER_USD: '75', MAX_DAY_USD: '4000', MAX_DAY_USD_ALPACA: '10000', MAX_DAY_ORDERS: '300', MAX_DAY_OPEN_ORDERS: '250',
  MAX_ORDER_MAX_LOSS_USD: '1000', MAX_ORDER_EQUITY_SHARE: '0.25', MAX_DAY_EQUITY_SHARE: '1.0', CREDIT_MIN_EQUITY_USD: '2000',
  EQUITY_CAP_MAX_AGE_MS: '120000', CAP_TIMEZONE: 'America/New_York',
  ...STOCK_VARS, POSITIONS_CACHE_MS: '0', ...extra,
});
const gateAt = (settings = {}, clock = () => NOW) => createGate({ store: memoryStore(), env: env(settings), now: clock });

/** A cash account of $10,000 (multiplier 1), its buying power its cash. */
const CASH = { equity: '10000.00', buying_power: '10000.00', multiplier: '1', status: 'ACTIVE' };
const MARGIN = { equity: '10000.00', buying_power: '20000.00', multiplier: '2', status: 'ACTIVE' };

const post = (body, venue = 'alpaca') => new Request(`${GATEWAY}/v1/${venue}/v2/orders`, {
  method: 'POST', headers: { Authorization: `Bearer ${TOKEN}` }, body: JSON.stringify(body),
});
const send = async (body, { settings = {}, gate = gateAt(settings), tape = alpacaVenue({ account: CASH }), clock = () => NOW, venue = 'alpaca' } = {}) => {
  const response = await route(post(body, venue), env(settings), { gate, fetcher: tape.fetcher, now: clock });
  return { response, status: response.status, body: await response.clone().json().catch(() => null), gate, tape };
};
/** A limit day buy of `qty` shares of `symbol` at `limit`. */
const buy = (symbol, qty, limit, extra = {}) => ({ symbol, qty, side: 'buy', type: 'limit', limit_price: limit, time_in_force: 'day',
  client_order_id: `buy-${symbol}-${qty}`, ...extra });
const long = (symbol, qty, marketValue, extra = {}) => ({ symbol, qty, qty_available: qty, side: 'long', market_value: marketValue,
  asset_class: 'us_equity', ...extra });
const restingBuy = (symbol, qty, limit, extra = {}) => ({ id: `o-${symbol}`, symbol, qty, filled_qty: '0', side: 'buy', type: 'limit',
  limit_price: limit, order_class: 'simple', status: 'new', ...extra });

const admitted = (result, message = '') => {
  assert.equal(result.status, 200, `${message} ${JSON.stringify(result.body)}`);
  assert.equal(result.tape.orders().length, 1, `${message}: forwarded once`);
};
const refused = (result, status, cap, pattern, message = '') => {
  assert.equal(result.status, status, `${message} ${JSON.stringify(result.body)}`);
  if (cap !== undefined) assert.equal(result.body.cap, cap, message);
  if (pattern) assert.match(result.body.error, pattern, message);
  assert.equal(result.tape.orders().length, 0, `${message}: nothing forwarded`);
  assert.equal(result.gate.status(NOW).today.orders, 0, `${message}: nothing reserved`);
};

// ------------------------------------------------------------------------------------------------ the numbers

test('the deployed stock vars are the owner\'s: buys on, an ETF 50% of equity, a single stock 20%, the book at most 2x', () => {
  const config = readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const deployed = name => {
    const lines = config.split('\n').filter(line => line.includes(`"${name}"`));
    return lines.length === 1 ? JSON.parse(/:\s*("(?:[^"\\]|\\.)*")/.exec(lines[0])[1]) : lines.length;
  };
  for (const [name, value] of Object.entries(STOCK_VARS)) assert.equal(deployed(name), value, name);
  assert.deepEqual(stockCaps(STOCK_VARS), { etfShare: 500000n, stockShare: 200000n, maxMultiple: 2000000n });
  assert.equal(stockBuysEnabled(STOCK_VARS), true);
});

test('the caps are ceilings: a var may lower a share or the multiple, never raise one past the owner\'s line', () => {
  assert.deepEqual(stockCaps({}), { etfShare: STOCK_ETF_SHARE_MAX, stockShare: STOCK_SINGLE_SHARE_MAX, maxMultiple: STOCK_MULTIPLE_MAX });
  assert.deepEqual(stockCaps({ STOCK_ETF_EQUITY_SHARE: '0.9', STOCK_SINGLE_EQUITY_SHARE: '1', STOCK_MAX_EQUITY_MULTIPLE: '4' }),
    { etfShare: 500000n, stockShare: 200000n, maxMultiple: 2000000n }, 'above a ceiling reads as the ceiling');
  for (const raw of ['x', '-0.1', '', null, undefined]) {
    assert.deepEqual(stockCaps({ STOCK_ETF_EQUITY_SHARE: raw, STOCK_SINGLE_EQUITY_SHARE: raw, STOCK_MAX_EQUITY_MULTIPLE: raw }),
      { etfShare: 500000n, stockShare: 200000n, maxMultiple: 2000000n }, `malformed ${String(raw)} reads as the ceiling`);
  }
  assert.deepEqual(stockCaps({ STOCK_ETF_EQUITY_SHARE: ' 0.25 ', STOCK_SINGLE_EQUITY_SHARE: '0.1', STOCK_MAX_EQUITY_MULTIPLE: '1' }),
    { etfShare: 250000n, stockShare: 100000n, maxMultiple: 1000000n });
  assert.deepEqual(stockCaps({ STOCK_ETF_EQUITY_SHARE: '0', STOCK_SINGLE_EQUITY_SHARE: '0', STOCK_MAX_EQUITY_MULTIPLE: '0' }),
    { etfShare: 0n, stockShare: 0n, maxMultiple: 0n }, 'zero closes the route');
  const limits = stockCaps({});
  assert.equal(stockSymbolCapMicro(limits, 'etf', usd('10000')), usd('5000'));
  assert.equal(stockSymbolCapMicro(limits, 'stock', usd('10000')), usd('2000'));
  assert.equal(stockSymbolCapMicro(limits, 'stock', usd('481.63')), usd('96.326'));
  assert.equal(stockSymbolCapMicro(limits, 'stock', usd('333.333333')), usd('66.666666'), 'rounded down, never in the order\'s favour');
  assert.equal(stockSymbolCapMicro(limits, 'etf', -usd('5')), 0n, 'negative equity caps nothing in');
  // The multiplier: 1 when unreadable or under 1; the book at the lower of it and the ceiling.
  assert.deepEqual(['1', '2', '4', 4, null, 'x', '0', '0.5'].map(multiplierMillionths), [M, 2n * M, 4n * M, 4n * M, M, M, M, M]);
  assert.equal(stockTotalCapMicro(limits, usd('10000'), M), usd('10000'));
  assert.equal(stockTotalCapMicro(limits, usd('10000'), 2n * M), usd('20000'));
  assert.equal(stockTotalCapMicro(limits, usd('10000'), 4n * M), usd('20000'), 'pattern-day-trader margin still caps the book at 2x');
  assert.equal(stockTotalCapMicro(stockCaps({ STOCK_MAX_EQUITY_MULTIPLE: '1' }), usd('10000'), 2n * M), usd('10000'));
  assert.equal(stockTotalCapMicro(limits, -usd('1'), 2n * M), 0n);
});

test('the switch: only "on" (any case, trimmed) admits buys; anything else, a typo included, admits none', () => {
  for (const raw of ['on', 'ON', ' On ']) assert.equal(stockBuysEnabled({ STOCK_BUYS_REAL: raw }), true, raw);
  for (const raw of ['off', '', 'yes', 'true', '1', 'onn', undefined, null]) assert.equal(stockBuysEnabled({ STOCK_BUYS_REAL: raw }), false, String(raw));
});

test('the list: 17 ETFs (the index four, the eleven SPDR sectors, TLT, GLD) and 18 large US stocks, each flagged', () => {
  const etfs = Object.keys(STOCK_UNIVERSE).filter(symbol => STOCK_UNIVERSE[symbol] === 'etf');
  const stocks = Object.keys(STOCK_UNIVERSE).filter(symbol => STOCK_UNIVERSE[symbol] === 'stock');
  assert.deepEqual(etfs, ['SPY', 'QQQ', 'IWM', 'DIA', 'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY', 'TLT', 'GLD']);
  assert.deepEqual(stocks, ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'BRK.B', 'JPM', 'V', 'UNH', 'XOM', 'JNJ', 'PG', 'MA', 'HD', 'AVGO', 'LLY', 'COST']);
  assert.ok(Object.isFrozen(STOCK_UNIVERSE));
  assert.deepEqual(['SPY', 'BRK.B', 'TSLA', 'spy', 'toString', '__proto__'].map(stockKind), ['etf', 'stock', null, null, null, null]);
});

// ------------------------------------------------------------------------------------------------ the shape

test('a real stock buy is a listed symbol, a limit day order with a positive limit, sized in shares (fractional to nine places)', () => {
  assert.deepEqual(stockBuyOrder(buy('SPY', '9', '500')), { symbol: 'SPY', kind: 'etf', micro: usd('4500') });
  assert.deepEqual(stockBuyOrder(buy('BRK.B', '0.5', '480.25')), { symbol: 'BRK.B', kind: 'stock', micro: usd('240.125') });
  assert.equal(stockBuyOrder(buy('AAPL', '0.333333333', '250.01')).micro, 83336667n, '$83.33666658..., rounded UP to the micro-dollar');
  assert.equal(stockBuyOrder(buy('AAPL', 2, 250.5)).micro, usd('501'), 'JSON numbers read as their decimals');
  assert.equal(stockBuyOrder(buy('SPY', '1', '0.5', { extended_hours: true })).micro, usd('0.5'));
  assert.equal(stockBuyOrder(buy('SPY', '1', '500', { order_class: 'simple' })).error, undefined);
  for (const [body, why] of [
    [buy('TSLA', '1', '200'), /"TSLA" is not on the real account's stock list/],
    [buy('BTC/USD', '1', '200'), /not on the real account's stock list/],
    [{ ...buy('SPY', '1', '500'), type: 'market', limit_price: undefined }, /a limit order/],
    [buy('SPY', '1', '500', { time_in_force: 'gtc' }), /a day order/],
    [buy('SPY', '1', '500', { time_in_force: 'ioc' }), /a day order/],
    [{ ...buy('SPY', '1', '500'), qty: undefined, notional: '500' }, /never in dollars \(notional\)/],
    [buy('SPY', '1', '0'), /positive limit_price/],
    [buy('SPY', '1', '-1'), /positive limit_price/],
    [buy('SPY', '1', '500.12345'), /at most four decimal places/],
    [buy('SPY', '1', '1e3'), /positive limit_price/],
    [{ ...buy('SPY', '1', '500'), limit_price: undefined }, /positive limit_price/],
    [buy('SPY', '0', '500'), /qty is missing or not positive/],
    [buy('SPY', '0.1234567891', '500'), /at most nine decimal places/],
    [buy('SPY', '-1', '500'), /at most nine decimal places/],
    [buy('SPY', 0.1 + 0.2, '500'), /at most nine decimal places/],
    [buy('SPY', '1', '500', { position_intent: 'buy_to_open' }), /no position_intent/],
    [buy('SPY', '1', '500', { extended_hours: 'yes' }), /true or false/],
    [buy('SPY', '1', '500', { side: 'sell' }), /A stock buy is a buy/],
  ]) {
    assert.match(stockBuyOrder(body).error ?? '', why, JSON.stringify(body));
  }
});

// ------------------------------------------------------------------------------------------------ admitted within the caps

test('within every cap a buy goes: forwarded exactly as sent, an open in the day\'s count, read fresh from the account', async () => {
  const gate = gateAt();
  const tape = alpacaVenue({ account: CASH });
  const etf = await send(buy('SPY', '10', '500'), { gate, tape });  // $5,000.00: exactly 50% of $10,000
  admitted(etf, 'an ETF at exactly its cap');
  assert.deepEqual(JSON.parse(tape.orders()[0].body), buy('SPY', '10', '500'));
  assert.equal(tape.orders()[0].url, 'https://api.alpaca.markets/v2/orders');
  assert.deepEqual([tape.accountReads().length, tape.openOrderReads().length, tape.positionReads().length], [1, 1, 2],
    'the account and its open orders once, the positions for the cover check and again fresh');
  assert.equal(tape.openOrderReads()[0].url, 'https://api.alpaca.markets/v2/orders?status=open&limit=500');
  for (const read of [...tape.accountReads(), ...tape.openOrderReads(), ...tape.positionReads()]) {
    assert.equal(read.method, 'GET');
    assert.equal(read.redirect, 'manual');
    assert.equal(read.headers['APCA-API-KEY-ID'], 'AK-REAL');
  }
  assert.deepEqual(gate.status(NOW).today, { day: TODAY, orders: 1, notional_usd: '5000.00' });
  assert.equal(gate.maxLossStatus(NOW).day_open_max_loss_usd, '0.00', 'a stock buy never spends the options\' opening maximum loss');
  assert.equal(gate.maxLossStatus(NOW).equity.usd, '10000.00', 'the reading is recorded for the option caps too');
  assert.equal(gate.status(NOW).stock_buys.day_buys_usd, '5000.00');
  assert.equal(gate.status(NOW).stock_buys.in_flight, 0, 'the venue answered: the buy left the in-flight ledger');

  const stock = await send(buy('AAPL', '8', '250'), { tape: alpacaVenue({ account: CASH }) });  // $2,000.00: exactly 20%
  admitted(stock, 'a single stock at exactly its cap');
  const fraction = await send(buy('BRK.B', '0.123456789', '480.25'), { tape: alpacaVenue({ account: CASH }) });
  admitted(fraction, 'fractional shares');
});

// ------------------------------------------------------------------------------------------------ refused over each cap

test('over the cap for one order: an ETF over 50% of equity, a stock over 20%, by one cent', async () => {
  for (const [body, message] of [
    [buy('QQQ', '10.0002', '500'), /^A buy of \$5000\.10 of QQQ exceeds the cap for an ETF of \$5000\.00 \(50% of \$10000\.00 equity\)\.$/],
    [buy('SPY', '1', '5000.01'), /\$5000\.01 of SPY exceeds the cap for an ETF of \$5000\.00/],
    [buy('MSFT', '1', '2000.01'), /^A buy of \$2000\.01 of MSFT exceeds the cap for a single stock of \$2000\.00 \(20% of \$10000\.00 equity\)\.$/],
  ]) {
    refused(await send(body), 403, 'stock_order', message, JSON.stringify(body));
  }
});

test('over the cap for one position: what is held, what rests on order (net of fills) and this buy, at most the symbol\'s share', async () => {
  const positions = [long('SPY', '6', '3000.00')];
  const openOrders = [restingBuy('SPY', '4', '500', { filled_qty: '2' })];  // $1,000 still resting
  const over = await send(buy('SPY', '2.00002', '500'), { tape: alpacaVenue({ account: CASH, positions, openOrders }) });  // $1,000.01
  refused(over, 403, 'stock_position',
    /^A buy of \$1000\.01 of SPY would take the position to \$5000\.01, past the cap for an ETF of \$5000\.00 \(50% of \$10000\.00 equity; held and on order \$4000\.00\)\.$/);
  admitted(await send(buy('SPY', '2', '500'), { tape: alpacaVenue({ account: CASH, positions, openOrders }) }), 'exactly to the cap');
  // Another symbol's position does not count against this one's cap (only against the book's).
  admitted(await send(buy('QQQ', '10', '500'), { tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' }, positions: [long('SPY', '6', '4900.00')] }) }),
    'QQQ beside a full SPY');
  // A single stock: 20% held is full.
  refused(await send(buy('NVDA', '0.01', '1'), { tape: alpacaVenue({ account: CASH, positions: [long('NVDA', '10', '2000.00')] }) }),
    403, 'stock_position', /past the cap for a single stock of \$2000\.00/);
});

test('over the cap for the book: every long position (options too) and open stock buy, at most equity x min(2, the multiplier)', async () => {
  const positions = [long('SPY', '8', '4000.00'), long('QQQ', '8', '4000.00'),
    { symbol: 'SPY261016C00740000', qty: '2', side: 'long', market_value: '1000.00', asset_class: 'us_option' }];
  const rich = power => ({ ...CASH, buying_power: power });
  // A cash account (multiplier 1): the book is 100% of equity.
  const over = await send(buy('AAPL', '4.00004', '250'), { tape: alpacaVenue({ account: rich('50000'), positions }) });  // $1,000.01
  refused(over, 403, 'stock_total', /^A buy of \$1000\.01 would take what the account holds and has on order to \$10000\.01, past its cap of \$10000\.00 \(1x \$10000\.00 equity; the account's multiplier is 1, STOCK_MAX_EQUITY_MULTIPLE 2\)\.$/);
  admitted(await send(buy('AAPL', '4', '250'), { tape: alpacaVenue({ account: rich('50000'), positions }) }), 'exactly 100%');
  // Open stock buys count; an option order and a cover do not (their own caps judge them).
  const openOrders = [restingBuy('IWM', '1', '200'), { ...restingBuy('SPY261016C00740000', '1', '5.00') },
    { id: 'm', order_class: 'mleg', symbol: '', side: 'buy', qty: '1', limit_price: '1.00' }];
  refused(await send(buy('AAPL', '3.20004', '250'), { tape: alpacaVenue({ account: rich('50000'), positions, openOrders }) }), 403, 'stock_total',
    /takes? what the account holds and has on order to \$10000\.01,/);
  admitted(await send(buy('AAPL', '3.2', '250'), { tape: alpacaVenue({ account: rich('50000'), positions, openOrders }) }),
    'exactly 100% with the resting IWM buy counted');
  admitted(await send(buy('AAPL', '3.20004', '250'), { tape: alpacaVenue({ account: rich('50000'), positions, openOrders: openOrders.slice(1) }) }),
    'without the IWM order the same buy fits');
  // A margin account: 2x; pattern-day-trader margin (4) still 2x; STOCK_MAX_EQUITY_MULTIPLE 1 takes margin away.
  const full = [long('SPY', '10', '5000.00'), long('QQQ', '10', '5000.00'), long('IWM', '25', '5000.00'), long('DIA', '10', '4000.00')];
  admitted(await send(buy('AAPL', '4', '250'), { tape: alpacaVenue({ account: { ...MARGIN, buying_power: '50000' }, positions: full }) }), 'margin: 2x');
  refused(await send(buy('AAPL', '4.00004', '250'), { tape: alpacaVenue({ account: { ...MARGIN, multiplier: '4', buying_power: '50000' }, positions: full }) }),
    403, 'stock_total', /past its cap of \$20000\.00 \(2x \$10000\.00 equity; the account's multiplier is 4, STOCK_MAX_EQUITY_MULTIPLE 2\)/);
  refused(await send(buy('AAPL', '0.004', '250'), { settings: { STOCK_MAX_EQUITY_MULTIPLE: '1' },
    tape: alpacaVenue({ account: { ...MARGIN, buying_power: '50000' }, positions: [long('SPY', '20', '10000.00')] }) }),
  403, 'stock_total', /past its cap of \$10000\.00 \(1x/);
  // No multiplier in the reading: no margin is assumed.
  refused(await send(buy('AAPL', '0.004', '250'), { tape: alpacaVenue({ account: { equity: '10000.00', buying_power: '50000' },
    positions: [long('SPY', '20', '10000.00')] }) }), 403, 'stock_total', /multiplier is 1/);
});

test('over the buying power: never more than the venue offers, margin included', async () => {
  const account = { ...MARGIN, buying_power: '1000.00' };
  refused(await send(buy('AAPL', '4.00004', '250'), { tape: alpacaVenue({ account }) }), 403, 'buying_power',
    /^A buy of \$1000\.01 exceeds the account's buying power of \$1000\.00: no margin past what the venue offers\.$/);
  admitted(await send(buy('AAPL', '4', '250'), { tape: alpacaVenue({ account }) }), 'exactly the buying power');
});

// ------------------------------------------------------------------------------------------------ in flight

test('buys the venue has not shown yet still count: a burst cannot pass a cap between two readings', async () => {
  let clock = NOW;
  const gate = gateAt({}, () => clock);
  const slow = () => alpacaVenue({ account: { ...CASH, buying_power: '50000' } });  // the venue shows none of the buys yet
  admitted(await send(buy('SPY', '6', '500'), { gate, tape: slow(), clock: () => clock }), 'the first $3,000');
  // Answered at NOW, read at NOW: a reading that began at most five seconds before the answer may not show it.
  const second = await send(buy('SPY', '4.00002', '500'), { gate, tape: slow(), clock: () => clock });
  assert.deepEqual([second.status, second.body.cap], [403, 'stock_position']);
  assert.match(second.body.error, /held and on order \$3000\.00\)/);
  admitted(await send(buy('SPY', '4', '500'), { gate, tape: slow(), clock: () => clock }), 'exactly to the cap with the first counted');
  // Six seconds on, the venue's own readings are what count: they show both buys, and the ledger no longer adds them.
  clock = NOW + 6000;
  const shown = alpacaVenue({ account: { ...CASH, buying_power: '50000' }, openOrders: [restingBuy('SPY', '10', '500')] });
  const full = await send(buy('SPY', '0.0002', '500'), { gate, tape: shown, clock: () => clock });
  assert.deepEqual([full.status, full.body.cap], [403, 'stock_position']);
  assert.match(full.body.error, /held and on order \$5000\.00\)/, 'counted once, from the venue');
  // The ledger keeps an answered buy only as long as a reading could miss it.
  assert.equal(gate.stockStatus(clock).in_flight, 0);
  assert.equal(gate.stockStatus(clock).day_buys_usd, '5000.00');
});

test('a buy whose forward got no answer counts for a minute; one that never left the gateway is given back', async () => {
  let clock = NOW;
  const gate = gateAt({}, () => clock);
  const lost = alpacaVenue({ account: { ...CASH, buying_power: '50000' } });
  const silent = { ...lost, fetcher: async (url, init = {}) => {
    if (init.method === 'POST') throw Object.assign(new Error('timeout'), { name: 'TimeoutError' });
    return lost.fetcher(url, init);
  } };
  const first = await send(buy('XLK', '20', '200'), { gate, tape: silent, clock: () => clock });  // $4,000
  assert.equal(first.status, 502, 'no answer: it may be an order');
  assert.equal(gate.stockStatus(clock).in_flight, 1);
  clock = NOW + 30000;
  const blocked = await send(buy('XLK', '5.00005', '200'), { gate, tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' } }), clock: () => clock });
  assert.deepEqual([blocked.status, blocked.body.cap], [403, 'stock_position'], 'the unanswered $4,000 still counts at 30 s');
  clock = NOW + STOCK_PENDING_MS + 1;
  admitted(await send(buy('XLK', '5.00005', '200'), { gate, tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' } }), clock: () => clock }),
    'after a minute the venue\'s own readings judge it');
  // A buy that could not be signed never reached the venue (the router refunds it before any dispatch): its place, its
  // dollars and its ledger entry are given back.
  const store = memoryStore();
  const bare = createGate({ store, env: env(), now: () => NOW });
  const ok = bare.reserve({ micro: String(usd('500')), venue: 'alpaca', stock: { symbol: 'SPY', equity_micro: String(usd('10000')),
    buying_power_micro: String(usd('10000')), multiplier: String(M), symbol_held_micro: '0', total_held_micro: '0', read_at: NOW } });
  assert.equal(ok.ok, true);
  assert.equal(bare.stockStatus(NOW).in_flight, 1);
  bare.refund({ ...ok, at: NOW });
  assert.equal(bare.stockStatus(NOW).in_flight, 0);
  assert.deepEqual([bare.status(NOW).today.orders, bare.stockStatus(NOW).day_buys_usd], [0, '0.00']);
  assert.equal(JSON.parse(store.get(STOCK_PENDING_KEY)).entries.length, 0);
});

// ------------------------------------------------------------------------------------------------ never a short sale

test('sales stay closes: only shares held long, at most what is held; nothing sold is ever a short sale', async () => {
  const sale = { symbol: 'SPY', qty: '10', side: 'sell', type: 'limit', limit_price: '501', time_in_force: 'day' };
  const positions = [long('SPY', '10', '5000.00')];
  const ok = await send(sale, { tape: alpacaVenue({ account: 500, positions }) });
  assert.equal(ok.status, 200);
  assert.equal(ok.tape.accountReads().length, 0, 'a close reads no account');
  assert.deepEqual(ok.gate.status(NOW).today, { day: TODAY, orders: 1, notional_usd: '0.01' }, 'an exit at one micro-dollar');
  for (const [body, held, why] of [
    [{ ...sale, qty: '10.5' }, positions, /SPY long \(10\.5 needed, 10 long held\)/],
    [sale, [], /SPY long \(10 needed, none held\)/],
    [sale, [{ ...positions[0], qty_available: '4' }], /SPY long \(10 needed, 4 long held\)/],
    [{ ...sale, symbol: 'TSLA' }, positions, /TSLA long \(10 needed, none held\)/],
  ]) {
    const result = await send(body, { tape: alpacaVenue({ account: CASH, positions: held }) });
    refused(result, 400, undefined, /^A stock order on the real account must close shares it holds: /, JSON.stringify(body));
    assert.match(result.body.error, why);
  }
});

test('a buy of a symbol held short is a cover, at most the short: no buy both covers and opens', async () => {
  const short = [{ symbol: 'AAPL', qty: '-100', qty_available: '-100', side: 'short', market_value: '-25000', asset_class: 'us_equity' }];
  const cover = await send({ symbol: 'AAPL', qty: '100', side: 'buy', type: 'market', time_in_force: 'day' }, { tape: alpacaVenue({ account: 500, positions: short }) });
  assert.equal(cover.status, 200, 'a market cover of the whole short goes, as before');
  assert.equal(cover.tape.accountReads().length, 0, 'a cover never waits on the account');
  for (const qty of ['101', '100.5']) {
    const over = await send(buy('AAPL', qty, '250'), { tape: alpacaVenue({ account: CASH, positions: short }) });
    refused(over, 400, undefined, new RegExp(`AAPL short \\(${qty.replace('.', '\\.')} needed, 100 short held\\)`), qty);
    assert.equal(over.tape.accountReads().length, 0);
  }
  // A short that appears between the first reading and the fresh one admits no open either.
  let reads = 0;
  const racing = alpacaVenue({ account: CASH, positions: () => (reads++ === 0 ? [] : short) });
  refused(await send(buy('AAPL', '1', '250'), { tape: racing }), 400, undefined, /A buy of AAPL is not admitted as an open: the account holds AAPL short/);
});

// ------------------------------------------------------------------------------------------------ the shape at the door

test('market, notional, unlisted, good-till-cancelled and option-intent buys are refused before any money read; crypto stays refused', async () => {
  for (const [body, why] of [
    [{ symbol: 'SPY', qty: '1', side: 'buy', type: 'market', time_in_force: 'day' }, /a limit order/],
    [{ symbol: 'SPY', notional: '500', side: 'buy', type: 'market', time_in_force: 'day' }, /never in dollars/],
    [{ symbol: 'SPY', notional: '500', side: 'buy', type: 'limit', limit_price: '500', time_in_force: 'day' }, /never in dollars/],
    [buy('TSLA', '1', '200'), /"TSLA" is not on the real account's stock list/],
    [buy('SPY', '1', '500', { time_in_force: 'gtc' }), /a day order/],
    [buy('SPY', '1', '500', { position_intent: 'buy_to_open' }), /no position_intent/],
    [buy('SPY', '1', '500', { type: 'stop', stop_price: '1' }), /Only market and limit orders/],
    [buy('BTC/USD', '0.01', '60000'), /Crypto is not traded on the real account/],
  ]) {
    const tape = alpacaVenue({ account: CASH });
    const result = await send(body, { tape });
    refused(result, 400, undefined, why, JSON.stringify(body));
    assert.equal(tape.accountReads().length + tape.openOrderReads().length, 0, `${JSON.stringify(body)}: no account or order read`);
  }
});

// ------------------------------------------------------------------------------------------------ failing closed

test('an account, open orders or positions that cannot be read refuse the buy with nothing reserved or sent, and say why', async () => {
  const cases = [
    ['account HTTP 500', { account: 500 }, 503, 'equity', /^Cannot read the real account \(alpaca account: HTTP 500\)/],
    ['account unreadable', { account: 'not json' }, 503, 'equity', /an unreadable answer/],
    ['account with no buying power', { account: { equity: '10000.00', multiplier: '1' } }, 503, 'equity', /no buying_power field/],
    ['account with no equity', { account: { buying_power: '10000.00' } }, 503, 'equity', /no equity field/],
    ['account read throws', { account: new TypeError('fetch failed') }, 503, 'equity', /fetch failed/],
    ['open orders HTTP 502', { openOrders: 502 }, 424, 'orders', /^Cannot read the real account's open orders: venue HTTP 502\.$/],
    ['open orders not a list', { openOrders: '{"orders":[]}' }, 424, 'orders', /not a list/],
    ['a full page of open orders', { openOrders: Array.from({ length: 500 }, (_, i) => restingBuy(`X${i}`, '1', '1')) }, 424, 'orders',
      /500 or more open orders/],
    ['an open market buy', { openOrders: [restingBuy('QQQ', '1', null, { type: 'market', limit_price: null })] }, 424, 'orders',
      /the open buy order for QQQ \(market\) has no limit price/],
    ['positions unread on the fresh read', { positions: (() => { let n = 0; return () => (n++ === 0 ? [] : 503); })() }, 424, 'positions',
      /^Cannot read the real account's positions: venue HTTP 503\.$/],
    ['positions unread at all', { positions: 503 }, 424, 'positions', /^Cannot check that the real account holds these shares/],
    ['a long position with no market value', { positions: [long('QQQ', '1', undefined)] }, 424, 'positions', /no readable market value/],
    ['a position row that contradicts itself', { positions: [{ symbol: 'QQQ', qty: '-1', side: 'long', market_value: '1' }] }, 424, 'positions',
      /contradicts itself/],
  ];
  for (const [name, venue, status, cap, why] of cases) {
    const result = await send(buy('SPY', '1', '500'), { tape: alpacaVenue({ account: CASH, ...venue }) });
    refused(result, status, cap, why, name);
    if (status === 503) assert.equal(result.response.headers.get('Retry-After'), '30', name);
    assert.equal(result.gate.stockStatus(NOW).in_flight, 0, name);
  }
});

test('the kill switch stops a buy, and the day\'s counts apply as for an option open; exits keep their room', async () => {
  const killed = gateAt();
  killed.setKill(true, NOW);
  const halted = await send(buy('SPY', '1', '500'), { gate: killed });
  refused(halted, 423, undefined, /kill switch is engaged/);
  assert.equal(killed.stockStatus(NOW).buys_admitted, false);
  assert.equal(killed.stockStatus(NOW).in_flight, 0);
  // Two of three orders may open; the third place is kept for an exit.
  const settings = { MAX_DAY_OPEN_ORDERS: '2', MAX_DAY_ORDERS: '3' };
  const gate = gateAt(settings);
  const tape = alpacaVenue({ account: { ...CASH, buying_power: '50000' }, positions: [long('IWM', '5', '1000.00')] });
  for (let i = 0; i < 2; i += 1) assert.equal((await send(buy('SPY', '1', '500'), { gate, tape, settings })).status, 200);
  const third = await send(buy('SPY', '1', '500'), { gate, tape, settings });
  assert.deepEqual([third.status, third.body.cap], [403, 'day_open_orders']);
  assert.equal(gate.stockStatus(NOW).buys_admitted, false);
  const sale = { symbol: 'IWM', qty: '5', side: 'sell', type: 'limit', limit_price: '200', time_in_force: 'day' };
  assert.equal((await send(sale, { gate, tape, settings })).status, 200, 'the exit still goes');
  assert.equal((await send(sale, { gate, tape, settings })).body.cap, 'day_orders');
});

test('with STOCK_BUYS_REAL off a buy is what it was: a cover of a short or refused; the gate refuses one that reaches it', async () => {
  for (const value of ['off', '', 'yes']) {
    const result = await send(buy('SPY', '1', '500'), { settings: { STOCK_BUYS_REAL: value }, tape: alpacaVenue({ account: CASH, positions: [long('SPY', '1', '500')] }) });
    refused(result, 400, undefined, /^A stock order on the real account must close shares it holds: SPY short \(1 needed, 1 long held\)/, value);
    assert.equal(result.tape.accountReads().length, 0);
  }
  const off = gateAt({ STOCK_BUYS_REAL: 'off' });
  const answer = off.reserve({ micro: String(usd('500')), venue: 'alpaca', stock: { symbol: 'SPY', equity_micro: String(usd('10000')),
    buying_power_micro: String(usd('10000')), multiplier: String(M), symbol_held_micro: '0', total_held_micro: '0', read_at: NOW } });
  assert.deepEqual([answer.ok, answer.status, answer.cap], [false, 403, 'stock_buys']);
});

test('the gate judges only what it can read: a malformed reading, an unlisted symbol or a stale one admits nothing', () => {
  const stock = (extra = {}) => ({ symbol: 'SPY', equity_micro: String(usd('10000')), buying_power_micro: String(usd('10000')),
    multiplier: String(M), symbol_held_micro: '0', total_held_micro: '0', read_at: NOW, ...extra });
  const reserve = (gate, extra, micro = usd('100')) => gate.reserve({ micro: String(micro), venue: 'alpaca', stock: stock(extra) });
  for (const extra of [{ symbol: 'TSLA' }, { equity_micro: '1.5' }, { buying_power_micro: undefined }, { multiplier: 'x' },
    { symbol_held_micro: null }, { total_held_micro: '' }, { read_at: 'soon' }]) {
    const answer = reserve(gateAt(), extra);
    assert.deepEqual([answer.ok, answer.status, answer.cap], [false, 400, 'stock'], JSON.stringify(extra));
  }
  for (const readAt of [NOW - 120001, NOW + 5001]) {
    const answer = reserve(gateAt(), { read_at: readAt });
    assert.deepEqual([answer.ok, answer.status, answer.cap], [false, 503, 'equity'], String(readAt - NOW));
  }
  const store = memoryStore();
  const gate = createGate({ store, env: env(), now: () => NOW });
  assert.equal(reserve(gate, {}, usd('5000')).ok, true, 'an ETF at its cap: the options per-order cap ($1,000) does not apply');
  assert.equal(reserve(gate, { symbol_held_micro: String(usd('5000')) }, 1n).cap, 'stock_position');
  // An exit flag never takes a buy around the stock caps: a reservation that carries a stock reading is an open.
  const flagged = gate.reserve({ micro: String(usd('5000.01')), venue: 'alpaca', exit: true, stock: stock() });
  assert.deepEqual([flagged.ok, flagged.cap], [false, 'stock_order']);
  assert.deepEqual(JSON.parse(store.get(DAY_KEY)), { day: TODAY, orders: 1, notional: String(usd('5000')), alpaca_open: '0',
    alpaca_notional: String(usd('5000')), alpaca_stock: String(usd('5000')) }, 'counted as an order, in the stock record, never in the options\' opening maximum loss');
});

test('the practice account is unchanged: its stock buys pass unmetered with no reading, whatever the list or the type', async () => {
  for (const body of [{ symbol: 'TSLA', qty: '3', side: 'buy', type: 'market', time_in_force: 'gtc' }, buy('SPY', '1000', '500')]) {
    const tape = alpacaVenue();
    const practice = await send(body, { tape, venue: 'alpaca-paper', settings: { ALPACA_PAPER_KEY_ID: 'PK', ALPACA_PAPER_SECRET_KEY: 'paper-secret' } });
    assert.equal(practice.status, 200);
    assert.equal(tape.calls.length, 1);
    assert.equal(tape.calls[0].url, 'https://paper-api.alpaca.markets/v2/orders');
    assert.equal(practice.gate.status(NOW).today.orders, 0);
  }
});

// ------------------------------------------------------------------------------------------------ the readings

test('the account reading for a buy: equity and buying power rounded down, the multiplier as read, nothing assumed', async () => {
  const tape = alpacaVenue({ account: { equity: '10000.0000009', buying_power: '19999.999999999', multiplier: '2' } });
  assert.deepEqual(await readStockAccount(env(), { fetcher: tape.fetcher, now: () => NOW }),
    { ok: true, at: NOW, equity_micro: '10000000000', buying_power_micro: '19999999999', multiplier: '2000000' });
  assert.equal(tape.calls[0].url, 'https://api.alpaca.markets/v2/account');
  const none = await readStockAccount(env({ ALPACA_SECRET_KEY: '' }), { fetcher: tape.fetcher, now: () => NOW });
  assert.deepEqual(none, { ok: false, at: NOW, error: 'alpaca account: alpaca secret key is missing' });
});

test('the exposure reading counts what is invested and on order, and refuses to guess', () => {
  const positions = [long('SPY', '2', '1000.00'), long('QQQ', '1', '400.000001'),
    { symbol: 'SPY261016C00740000', qty: '1', side: 'long', market_value: '250', asset_class: 'us_option' },
    { symbol: 'SPY261016C00750000', qty: '-1', side: 'short', market_value: '-100', asset_class: 'us_option' },
    { symbol: 'XOM', qty: '-3', side: 'short', market_value: '-330' }];
  const orders = [restingBuy('SPY', '3', '500', { filled_qty: '1' }), restingBuy('XOM', '3', '110'), restingBuy('TLT', '1', '90'),
    { id: 'n', symbol: 'GLD', notional: '100.5', filled_qty: '0.1', side: 'buy', type: 'market' },
    { id: 's', symbol: 'SPY', qty: '1', side: 'sell', type: 'market' }, restingBuy('SPY', '2', '500', { filled_qty: '2' })];
  assert.deepEqual(stockExposure('SPY', positions, orders), { symbolMicro: usd('2000'), totalMicro: usd('2840.500001') },
    'SPY: $1,000 held, $1,000 resting; the book: $1,650.000001 long (the option too), $1,190.50 on order; shorts, sells, covers and filled orders not');
  assert.deepEqual(stockExposure('XOM', positions, orders), { error: 'the account holds XOM short: a buy of it covers the short, at most its size, and opens nothing', short: true });
  assert.equal(stockExposure('SPY', null, []).source, 'positions');
  assert.equal(stockExposure('SPY', [], {}).source, 'orders');
  assert.equal(stockExposure('SPY', [], [{ id: 'x', symbol: 'IWM', side: 'buy', type: 'limit', qty: '1' }]).source, 'orders');
  assert.match(stockExposure('SPY', [], [{ id: 'x', symbol: 'IWM', side: 'buy', type: 'market' }]).error, /neither a qty nor a notional/);
  // Signed shares, netted the way a close reads them.
  assert.deepEqual([heldShares('XOM', positions), heldShares('SPY', positions), heldShares('TSLA', positions), heldShares('XOM', null)],
    [-3n * 10n ** 12n, 2n * 10n ** 12n, 0n, 0n]);
  assert.equal(heldShares('XOM', [...positions, { symbol: 'XOM', qty: '3' }]), 0n, 'a cover taken out of a cached reading nets the short');
});

test('health reports the stock route: the switch, the shares, the list, today\'s buys and those in flight', async () => {
  const gate = gateAt();
  assert.equal((await send(buy('XLE', '3', '90.5'), { gate })).status, 200);
  const response = await route(new Request(`${GATEWAY}/v1/health`, { headers: { Authorization: `Bearer ${TOKEN}` } }), env(), { gate, now: () => NOW });
  const body = await response.json();
  assert.deepEqual(body.stock_buys, {
    enabled: true, etf_equity_share: '0.5', stock_equity_share: '0.2', max_equity_multiple: '2',
    symbols: {
      etf: ['SPY', 'QQQ', 'IWM', 'DIA', 'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY', 'TLT', 'GLD'],
      stock: ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'BRK.B', 'JPM', 'V', 'UNH', 'XOM', 'JNJ', 'PG', 'MA', 'HD', 'AVGO', 'LLY', 'COST'],
    },
    day_buys_usd: '271.50', in_flight: 0, in_flight_usd: '0.00', buys_admitted: true,
  });
  assert.equal(gateAt({ STOCK_BUYS_REAL: 'off' }).status(NOW).stock_buys.enabled, false);
});

test('the Durable Object settles a stock buy in one transaction', () => {
  const source = readFileSync(new URL('../worker.mjs', import.meta.url), 'utf8');
  assert.match(source, /\bstockSettle\(request\) \{ return this\.ctx\.storage\.transactionSync\(\(\) => this\.gate\.stockSettle\(request\)\); \}/);
});
