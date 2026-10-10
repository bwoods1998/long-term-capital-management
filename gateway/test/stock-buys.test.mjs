// Real stock and ETF buys (Oct 10, 2026; the owner's goal: agent programs may trade ETFs, stocks and options with real
// money). While STOCK_BUYS_REAL is "on", the real account admits a LONG-ONLY buy of a listed symbol: a limit day order
// sized in shares, metered at qty x limit_price, an ETF position at most 50% of equity and a single stock at most 20%,
// the whole book at most equity x min(2, the account's multiplier) with long options weighed at that multiple (the venue
// lends nothing on them), never above the lower of its buying power and its overnight Reg T buying power, and the day's
// buys at most 4x equity, every figure read from the account by the gateway itself and failing closed. A sale is still
// only a close of shares held long, a buy of a symbol held short is still only a cover, both read fresh and serialized in
// the Gate (the review of Oct 10, 2026), the kill switch and the day's order counts stop a buy as they stop an option
// open, and the practice account is unchanged.

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import {
  stockCaps, stockSymbolCapMicro, stockTotalCapMicro, stockDayCapMicro, stockBookMicro, multiplierMillionths, readStockAccount,
  STOCK_ETF_SHARE_MAX, STOCK_SINGLE_SHARE_MAX, STOCK_MULTIPLE_MAX, STOCK_DAY_MULTIPLE_MAX,
} from '../lib/account.mjs';
import { STOCK_UNIVERSE, stockKind, stockBuysEnabled, stockBuyOrder, heldShares, stockExposure, availableHeld, closeAvailable, marginableRow } from '../lib/caps.mjs';
import { createGate, STOCK_PENDING_KEY, STOCK_PENDING_MS, STOCK_LEDGER_HOLD_MS, DAY_KEY } from '../lib/gate.mjs';
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
const STOCK_VARS = { STOCK_BUYS_REAL: 'on', STOCK_ETF_EQUITY_SHARE: '0.5', STOCK_SINGLE_EQUITY_SHARE: '0.2', STOCK_MAX_EQUITY_MULTIPLE: '2',
  STOCK_DAY_EQUITY_MULTIPLE: '4' };
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
const MARGIN = { equity: '10000.00', buying_power: '20000.00', regt_buying_power: '20000.00', multiplier: '2', status: 'ACTIVE' };

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

test('the deployed stock vars are the owner\'s: buys on, an ETF 50% of equity, a single stock 20%, the book at most 2x, a day 4x', () => {
  const config = readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8');
  const deployed = name => {
    const lines = config.split('\n').filter(line => line.includes(`"${name}"`));
    return lines.length === 1 ? JSON.parse(/:\s*("(?:[^"\\]|\\.)*")/.exec(lines[0])[1]) : lines.length;
  };
  for (const [name, value] of Object.entries(STOCK_VARS)) assert.equal(deployed(name), value, name);
  assert.deepEqual(stockCaps(STOCK_VARS), { etfShare: 500000n, stockShare: 200000n, maxMultiple: 2000000n, dayMultiple: 4000000n });
  assert.equal(stockBuysEnabled(STOCK_VARS), true);
});

test('the caps are ceilings: a var may lower a share or the multiple, never raise one past the owner\'s line', () => {
  assert.deepEqual(stockCaps({}), { etfShare: STOCK_ETF_SHARE_MAX, stockShare: STOCK_SINGLE_SHARE_MAX, maxMultiple: STOCK_MULTIPLE_MAX,
    dayMultiple: STOCK_DAY_MULTIPLE_MAX });
  assert.deepEqual(stockCaps({ STOCK_ETF_EQUITY_SHARE: '0.9', STOCK_SINGLE_EQUITY_SHARE: '1', STOCK_MAX_EQUITY_MULTIPLE: '4', STOCK_DAY_EQUITY_MULTIPLE: '9' }),
    { etfShare: 500000n, stockShare: 200000n, maxMultiple: 2000000n, dayMultiple: 4000000n }, 'above a ceiling reads as the ceiling');
  for (const raw of ['x', '-0.1', '', null, undefined]) {
    assert.deepEqual(stockCaps({ STOCK_ETF_EQUITY_SHARE: raw, STOCK_SINGLE_EQUITY_SHARE: raw, STOCK_MAX_EQUITY_MULTIPLE: raw, STOCK_DAY_EQUITY_MULTIPLE: raw }),
      { etfShare: 500000n, stockShare: 200000n, maxMultiple: 2000000n, dayMultiple: 4000000n }, `malformed ${String(raw)} reads as the ceiling`);
  }
  assert.deepEqual(stockCaps({ STOCK_ETF_EQUITY_SHARE: ' 0.25 ', STOCK_SINGLE_EQUITY_SHARE: '0.1', STOCK_MAX_EQUITY_MULTIPLE: '1', STOCK_DAY_EQUITY_MULTIPLE: '1.5' }),
    { etfShare: 250000n, stockShare: 100000n, maxMultiple: 1000000n, dayMultiple: 1500000n });
  assert.deepEqual(stockCaps({ STOCK_ETF_EQUITY_SHARE: '0', STOCK_SINGLE_EQUITY_SHARE: '0', STOCK_MAX_EQUITY_MULTIPLE: '0', STOCK_DAY_EQUITY_MULTIPLE: '0' }),
    { etfShare: 0n, stockShare: 0n, maxMultiple: 0n, dayMultiple: 0n }, 'zero closes the route');
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
  // The day: 4x equity, rounded down; none on negative equity.
  assert.equal(stockDayCapMicro(limits, usd('10000')), usd('40000'));
  assert.equal(stockDayCapMicro(stockCaps({ STOCK_DAY_EQUITY_MULTIPLE: '0.333333' }), usd('1')), 333333n);
  assert.equal(stockDayCapMicro(limits, -usd('1')), 0n);
  // The book as the cap weighs it: what the venue lends nothing on counts at the multiple, once at 1x or under.
  assert.equal(stockBookMicro(usd('50000'), usd('10000'), 2n * M), usd('60000'), '$40,000 of stock + $10,000 of options x 2');
  assert.equal(stockBookMicro(usd('50000'), usd('10000'), M), usd('50000'), 'a cash account: every dollar once');
  assert.equal(stockBookMicro(usd('50000'), usd('10000'), 500000n), usd('50000'), 'under 1x nothing is lent either');
  assert.equal(stockBookMicro(usd('50000'), 0n, 2n * M), usd('50000'));
  assert.equal(stockBookMicro(0n, 3n, 1500000n), 2n, 'the extra weight rounds up');
  // What the venue lends on: a US stock or ETF row; options, crypto and anything it cannot place are paid in full.
  assert.deepEqual([{ symbol: 'SPY', asset_class: 'us_equity' }, { symbol: 'BRK.B' }, { symbol: 'SPY261016C00740000', asset_class: 'us_option' },
    { symbol: 'SPY261016C00740000' }, { symbol: 'BTC/USD', asset_class: 'crypto' }, { symbol: 'SPY', asset_class: 'us_option' }].map(marginableRow),
  [true, true, false, false, false, false]);
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

test('the book is a margin line: long options take no margin, so they count at the multiple and the overnight 2x holds on pattern-day-trader margin', async () => {
  // The review of Oct 10, 2026 (P1): $30,000 equity on pattern-day-trader margin (multiplier 4), intraday buying power
  // $80,000, overnight Reg T buying power $40,000, a long SPY call worth $10,000 and $30,000 of ETFs. Reg T overnight holds
  // stocks / 2 + options <= equity: at most $40,000 of stock beside the call. A gross cap (stocks + options <= 2x) would
  // have admitted $50,000 and left a margin call.
  const account = { equity: '30000.00', buying_power: '80000.00', regt_buying_power: '40000.00', multiplier: '4', status: 'ACTIVE' };
  const positions = [{ symbol: 'SPY261016C00740000', qty: '20', side: 'long', market_value: '10000.00', asset_class: 'us_option' },
    long('SPY', '30', '15000.00'), long('QQQ', '30', '15000.00')];
  admitted(await send(buy('IWM', '50', '200'), { tape: alpacaVenue({ account, positions }) }), 'exactly the overnight line: $40,000 of stock, $10,000 of options');
  refused(await send(buy('IWM', '50.00005', '200'), { tape: alpacaVenue({ account, positions }) }), 403, 'stock_total',
    /^A buy of \$10000\.01 would take what the account holds and has on order to \$60000\.01, long options and other unmarginable positions \(\$10000\.00\) counted 2x: the venue lends nothing on them, past its cap of \$60000\.00 \(2x \$30000\.00 equity; the account's multiplier is 4, STOCK_MAX_EQUITY_MULTIPLE 2\)\.$/,
    'one cent over the overnight line, though the gross book ($50,000.01) is under 2x');
  // On a cash account an option counts once, as before.
  admitted(await send(buy('IWM', '25', '200'), { tape: alpacaVenue({ account: { equity: '30000.00', buying_power: '30000.00', multiplier: '1' },
    positions: [positions[0], long('SPY', '30', '15000.00')] }) }), 'cash: $20,000 of ETFs beside a $10,000 option, exactly 100%');
  refused(await send(buy('IWM', '25.00005', '200'), { tape: alpacaVenue({ account: { equity: '30000.00', buying_power: '30000.00', multiplier: '1' },
    positions: [positions[0], long('SPY', '30', '15000.00')] }) }), 403, 'stock_total', /to \$30000\.01, past its cap of \$30000\.00 \(1x/);
});

test('over the buying power: never more than the venue offers, margin included', async () => {
  const account = { ...MARGIN, buying_power: '1000.00' };
  refused(await send(buy('AAPL', '4.00004', '250'), { tape: alpacaVenue({ account }) }), 403, 'buying_power',
    /^A buy of \$1000\.01 exceeds the account's buying power of \$1000\.00: no margin past what the venue offers\.$/);
  admitted(await send(buy('AAPL', '4', '250'), { tape: alpacaVenue({ account }) }), 'exactly the buying power');
  // The overnight figure binds when it is the lower (pattern-day-trader margin: `buying_power` is intraday, 4x).
  const intraday = { equity: '10000.00', buying_power: '40000.00', regt_buying_power: '1000.00', multiplier: '4' };
  refused(await send(buy('AAPL', '4.00004', '250'), { tape: alpacaVenue({ account: intraday }) }), 403, 'buying_power',
    /buying power of \$1000\.00:/);
  admitted(await send(buy('AAPL', '4', '250'), { tape: alpacaVenue({ account: intraday }) }), 'exactly the overnight buying power');
  // And `buying_power` binds when it is the lower.
  refused(await send(buy('AAPL', '4.00004', '250'), { tape: alpacaVenue({ account: { ...MARGIN, buying_power: '1000.00', regt_buying_power: '9000.00' } }) }),
    403, 'buying_power', /buying power of \$1000\.00:/);
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
  // Six seconds on, the venue's open orders show both buys by their client_order_id: the ledger still holds them (the
  // account and positions may lag a fill), but each counts once, never as held and as open both.
  clock = NOW + 6000;
  const shown = alpacaVenue({ account: { ...CASH, buying_power: '50000' }, openOrders: [restingBuy('SPY', '6', '500', { client_order_id: 'buy-SPY-6' }),
    restingBuy('SPY', '4', '500', { id: 'o-SPY-2', client_order_id: 'buy-SPY-4' })] });
  const full = await send(buy('SPY', '0.0002', '500'), { gate, tape: shown, clock: () => clock });
  assert.deepEqual([full.status, full.body.cap], [403, 'stock_position']);
  assert.match(full.body.error, /held and on order \$5000\.00\)/, 'counted once, from the venue');
  // Both were answered: none is in flight, though the ledger holds them.
  assert.equal(gate.stockStatus(clock).in_flight, 0);
  assert.equal(gate.stockStatus(clock).day_buys_usd, '5000.00');
});

test('buys in flight count against the book and the buying power too, not only their own symbol', async () => {
  // The book: $5,000 of SPY and $4,000 of XLK the venue shows neither of, then XLE one cent past 100% of a cash account.
  const gate = gateAt();
  const slow = (account = { ...CASH, buying_power: '50000' }) => alpacaVenue({ account });
  admitted(await send(buy('SPY', '10', '500'), { gate, tape: slow() }), 'SPY $5,000');
  admitted(await send(buy('XLK', '20', '200'), { gate, tape: slow() }), 'XLK $4,000');
  const over = await send(buy('XLE', '10.0001', '100'), { gate, tape: slow() });  // $1,000.01
  assert.deepEqual([over.status, over.body.cap], [403, 'stock_total']);
  assert.match(over.body.error, /to \$10000\.01, past its cap of \$10000\.00 \(1x/);
  admitted(await send(buy('XLE', '10', '100'), { gate, tape: slow() }), 'exactly 100% with both in flight');
  // The buying power: $2,500 of SPY the venue does not show yet leaves $500 of $3,000.
  const second = gateAt();
  admitted(await send(buy('SPY', '5', '500'), { gate: second, tape: slow({ ...CASH, buying_power: '3000.00' }) }), 'SPY $2,500');
  const short = await send(buy('QQQ', '1.00002', '500'), { gate: second, tape: slow({ ...CASH, buying_power: '3000.00' }) });  // $500.01
  assert.deepEqual([short.status, short.body.cap], [403, 'buying_power']);
  assert.match(short.body.error, /^A buy of \$500\.01 exceeds the account's buying power of \$3000\.00 less \$2500\.00 of buys in flight: /);
  admitted(await send(buy('QQQ', '1', '500'), { gate: second, tape: slow({ ...CASH, buying_power: '3000.00' }) }), 'exactly the buying power left');
});

test('a buy that fills between two reads is counted twice, never not at all: open orders, then positions, then the account', async () => {
  // The design review of Oct 10, 2026: read the account first and the open orders after it, and a buy that fills between
  // the two has left the open list while the account was read before its debit. A $2,000 SPY buy placed earlier (not
  // this gate's: no ledger entry) fills after the Nth read; a buy of $3,000.01 more is one cent past the $5,000 cap if
  // the resting $2,000 is counted at all, and admitted only if it is counted nowhere.
  const resting = restingBuy('SPY', '4', '500', { client_order_id: 'earlier' });
  const filling = (after, { lag = false } = {}) => {
    let filled = after === 0;
    const reads = [];
    const tape = alpacaVenue({ account: { ...CASH, buying_power: '50000' }, openOrders: () => (filled ? [] : [resting]),
      positions: () => (filled && !lag ? [long('SPY', '4', '2000.00')] : []) });
    const fetcher = async (url, init = {}) => {
      const answer = await tape.fetcher(url, init);
      reads.push(/\/v2\/account$/.test(url) ? 'account' : /\/v2\/positions$/.test(url) ? 'positions' : /\/v2\/orders\?/.test(url) ? 'orders' : 'order');
      if (reads.length === after) filled = true;
      return answer;
    };
    return { ...tape, fetcher, reads };
  };
  for (const [after, counted] of [[0, '2000'], [1, '2000'], [2, '4000'], [3, '2000'], [4, '2000']]) {
    const tape = filling(after);
    refused(await send(buy('SPY', '6.00002', '500'), { tape }), 403, 'stock_position', new RegExp(`held and on order \\$${counted}\\.00\\)\\.$`),
      `filled after read ${after}`);
    assert.deepEqual(tape.reads, ['positions', 'orders', 'positions', 'account'], 'the cover check, then open orders, positions, the account');
  }
  // Positions that lag the fill (here they never show it): a fill any time after the reading began, with the open orders,
  // is still counted there. Read the old way, one between the account and the open orders was counted nowhere. (A fill
  // before the reading began is the ledger's: the next test.)
  for (const after of [2, 3, 4]) {
    refused(await send(buy('SPY', '6.00002', '500'), { tape: filling(after, { lag: true }) }), 403, 'stock_position',
      /held and on order \$2000\.00\)\.$/, `filled after read ${after}, positions lagging`);
  }
  admitted(await send(buy('SPY', '2', '500'), { tape: filling(2) }), 'counted twice ($4,000), $1,000 more still fits: high by the order, never low');
});

test('an admitted buy is held a minute after its answer: a fill the account and positions show late still counts', async () => {
  // Answered at NOW, then filled: it leaves the open orders, and the venue's positions and buying power do not show it yet.
  let clock = NOW;
  const gate = gateAt({}, () => clock);
  const lagging = () => alpacaVenue({ account: { ...CASH, buying_power: '3000.00' } });
  admitted(await send(buy('SPY', '6', '500'), { gate, tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' } }), clock: () => clock }), 'SPY $3,000');
  for (const at of [NOW + 6000, NOW + 30000, NOW + STOCK_LEDGER_HOLD_MS]) {
    clock = at;
    const position = await send(buy('SPY', '4.00002', '500'), { gate, tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' } }), clock: () => clock });
    assert.deepEqual([position.status, position.body.cap], [403, 'stock_position'], `${at - NOW} ms`);
    assert.match(position.body.error, /held and on order \$3000\.00\)\.$/);
    // The buying power the venue reports has not been debited for it either: the ledger still takes it off.
    const power = await send(buy('QQQ', '0.0002', '500'), { gate, tape: lagging(), clock: () => clock });
    assert.deepEqual([power.status, power.body.cap], [403, 'buying_power'], `${at - NOW} ms`);
    assert.match(power.body.error, /buying power of \$3000\.00 less \$3000\.00 of buys in flight/);
  }
  assert.equal(gate.stockStatus(clock).in_flight, 0, 'answered: held, not in flight');
  clock = NOW + STOCK_LEDGER_HOLD_MS + 1;
  admitted(await send(buy('SPY', '4.00002', '500'), { gate, tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' } }), clock: () => clock }),
    'a minute after its answer the venue\'s own readings judge it');
});

test('a held buy the open orders show counts once, the larger of the two, never as held and as open both', async () => {
  // Admitted at NOW as client_order_id "buy-SPY-6" ($3,000); ten seconds on the venue lists it.
  const setup = async () => {
    let clock = NOW;
    const gate = gateAt({}, () => clock);
    admitted(await send(buy('SPY', '6', '500'), { gate, tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' } }), clock: () => clock }), 'SPY $3,000');
    clock = NOW + 10000;
    return { gate, clock: () => clock };
  };
  const listed = (extra = {}) => restingBuy('SPY', '6', '500', { client_order_id: 'buy-SPY-6', ...extra });
  const judged = async (body, venue) => {
    const { gate, clock } = await setup();
    return send(body, { gate, clock, tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' }, ...venue }) });
  };
  // Refused with only the first buy reserved and nothing more sent.
  const over = (result, cap, pattern, message = '') => {
    assert.deepEqual([result.status, result.body.cap], [403, cap], `${message} ${JSON.stringify(result.body)}`);
    assert.match(result.body.error, pattern, message);
    assert.deepEqual([result.tape.orders().length, result.gate.status(NOW).today.orders], [0, 1], message);
  };
  // Resting in full: counted once ($3,000), so $2,000 more is exactly the cap and a cent more is past it.
  over(await judged(buy('SPY', '4.00002', '500'), { openOrders: [listed()] }), 'stock_position', /held and on order \$3000\.00\)\.$/);
  admitted(await judged(buy('SPY', '4', '500'), { openOrders: [listed()] }), 'exactly to the cap, the order counted once');
  // Partly filled: the open order shows $2,000 still resting and the position the $1,000 filled. The ledger keeps the
  // larger of its $3,000 and the open $2,000, so the filled part counts twice for the hold: high, never low.
  over(await judged(buy('SPY', '2.00002', '500'), { openOrders: [listed({ filled_qty: '2' })], positions: [long('SPY', '2', '1000.00')] }),
    'stock_position', /held and on order \$4000\.00\)\.$/);
  // Another client_order_id, or none, is another order: both count.
  for (const other of [listed({ client_order_id: 'someone-else' }), restingBuy('SPY', '6', '500')]) {
    over(await judged(buy('SPY', '0.0002', '500'), { openOrders: [other] }), 'stock_position', /held and on order \$6000\.00\)\.$/,
      JSON.stringify(other.client_order_id));
  }
  // The buying power the venue reports nets its open orders: a held buy it lists is not taken off it a second time.
  admitted(await judged(buy('QQQ', '6', '500'), { account: { ...CASH, buying_power: '3000.00' }, openOrders: [listed()] }),
    'buying power net of the resting buy, the ledger adding nothing');
  over(await judged(buy('QQQ', '0.0002', '500'), { account: { ...CASH, buying_power: '3000.00' } }), 'buying_power',
    /less \$3000\.00 of buys in flight/, 'not listed: the ledger takes it off');
  // The book: listed once.
  over(await judged(buy('XLK', '15.0001', '200'), { openOrders: [listed()], positions: [long('IWM', '20', '4000.00')] }), 'stock_total',
    /has on order to \$10000\.02,/);
  // In the Gate: an open order nets one held buy of its symbol and client_order_id at most, and a client_order_id the venue
  // would not take (over 128 characters) is never recorded to match.
  const stock = (extra = {}) => ({ symbol: 'SPY', equity_micro: String(usd('10000')), buying_power_micro: String(usd('50000')),
    multiplier: String(M), symbol_held_micro: '0', total_held_micro: '0', options_held_micro: '0', read_at: NOW, ...extra });
  const store = memoryStore();
  const gate = createGate({ store, env: env(), now: () => NOW });
  for (const client of ['dup', 'dup', 'x'.repeat(129)]) {
    assert.equal(gate.reserve({ micro: String(usd('1000')), venue: 'alpaca', at: NOW, stock: stock({ client_order_id: client }) }).ok, true);
  }
  assert.deepEqual(JSON.parse(store.get(STOCK_PENDING_KEY)).entries.map(entry => entry.client ?? null), ['dup', 'dup', null]);
  const seen = { symbol_held_micro: String(usd('1000')), total_held_micro: String(usd('1000')),
    open_buys: [{ client_order_id: 'dup', symbol: 'SPY', micro: String(usd('1000')) }, { client_order_id: 'x'.repeat(129), symbol: 'SPY', micro: String(usd('1000')) }] };
  // $1,000 open + $1,000 (the second "dup") + $1,000 (the long id) = $3,000 held and on order: $2,000.01 more is past $5,000.
  const past = gate.reserve({ micro: String(usd('2000.01')), venue: 'alpaca', at: NOW, stock: stock(seen) });
  assert.deepEqual([past.ok, past.cap], [false, 'stock_position']);
  assert.match(past.error, /held and on order \$3000\.00\)\.$/);
  // The same client_order_id on another symbol is not this buy.
  const elsewhere = gate.reserve({ micro: String(usd('1000.01')), venue: 'alpaca', at: NOW,
    stock: stock({ ...seen, open_buys: [{ client_order_id: 'dup', symbol: 'QQQ', micro: String(usd('1000')) }] }) });
  assert.match(elsewhere.error ?? '', /held and on order \$4000\.00\)/);
  // What the exposure reading lists for the Gate: every counted open buy that names a client_order_id, at what it counted.
  assert.deepEqual(stockExposure('SPY', [], [listed({ filled_qty: '2' }), restingBuy('QQQ', '1', '400'), { ...listed(), side: 'sell' },
    restingBuy('TLT', '1', '90', { client_order_id: '' })]).openBuys, [{ client_order_id: 'buy-SPY-6', symbol: 'SPY', micro: usd('2000') }]);
});

test('the boundaries admit: a reading exactly two minutes old or five seconds ahead, an answer exactly a minute before the reading still counted, 499 open orders', async () => {
  const stock = (extra = {}) => ({ symbol: 'SPY', equity_micro: String(usd('10000')), buying_power_micro: String(usd('10000')),
    multiplier: String(M), symbol_held_micro: '0', total_held_micro: '0', options_held_micro: '0', read_at: NOW, ...extra });
  for (const readAt of [NOW - 120000, NOW + 5000]) {
    const answer = gateAt().reserve({ micro: String(usd('100')), venue: 'alpaca', at: NOW, stock: stock({ read_at: readAt }) });
    assert.equal(answer.ok, true, String(readAt - NOW));
  }
  // An answer at NOW counts for a reading that began at NOW + STOCK_LEDGER_HOLD_MS, and no longer for one that began a
  // millisecond later; judged as late as the oldest reading the caps take, it is still in the ledger.
  const gate = gateAt();
  const first = gate.reserve({ micro: String(usd('4000')), venue: 'alpaca', at: NOW, stock: stock() });
  assert.equal(gate.stockSettle({ id: first.stock_id, at: NOW }).ok, true);
  const counted = gate.reserve({ micro: String(usd('1000.01')), venue: 'alpaca', at: NOW + STOCK_LEDGER_HOLD_MS + 120000,
    stock: stock({ read_at: NOW + STOCK_LEDGER_HOLD_MS }) });
  assert.deepEqual([counted.ok, counted.cap], [false, 'stock_position'], 'still counted at exactly a minute');
  const past = gate.reserve({ micro: String(usd('1000.01')), venue: 'alpaca', at: NOW + STOCK_LEDGER_HOLD_MS + 1,
    stock: stock({ read_at: NOW + STOCK_LEDGER_HOLD_MS + 1 }) });
  assert.equal(past.ok, true, 'a reading begun after that judges by the venue alone');
  // 499 open orders is a whole list; 500 may be cut off (refused above).
  const many = Array.from({ length: 499 }, (_, i) => restingBuy(`X${i}`, '1', '1'));
  admitted(await send(buy('SPY', '1', '500'), { tape: alpacaVenue({ account: CASH, openOrders: many }) }), '499 open orders');
});

test('one micro-dollar over a cap is over it, and "0" closes the route end to end', async () => {
  // $5,000.0000005, rounded up to $5,000.000001: one micro-dollar past an ETF's 50% of $10,000.
  assert.equal(stockBuyOrder(buy('SPY', '10.000000001', '500')).micro, usd('5000') + 1n);
  refused(await send(buy('SPY', '10.000000001', '500')), 403, 'stock_order', /^A buy of \$5000\.01 of SPY exceeds the cap for an ETF of \$5000\.00/);
  admitted(await send(buy('SPY', '10', '500')), 'exactly the cap');
  for (const [name, symbol] of [['STOCK_ETF_EQUITY_SHARE', 'SPY'], ['STOCK_SINGLE_EQUITY_SHARE', 'AAPL']]) {
    refused(await send(buy(symbol, '0.000000001', '1'), { settings: { [name]: '0' } }), 403, 'stock_order', /of \$0\.00 \(0% of \$10000\.00 equity\)\.$/, name);
  }
  refused(await send(buy('SPY', '0.000000001', '1'), { settings: { STOCK_MAX_EQUITY_MULTIPLE: '0' } }), 403, 'stock_total', /past its cap of \$0\.00 \(0x/);
  refused(await send(buy('SPY', '0.000000001', '1'), { settings: { STOCK_DAY_EQUITY_MULTIPLE: '0' } }), 403, 'stock_day', /past the day's cap of \$0\.00 \(0x/);
});

test('the day\'s buys are capped at STOCK_DAY_EQUITY_MULTIPLE x equity (a ceiling of 4), cancelled buys included: a backstop under the House\'s stops', async () => {
  let clock = NOW;
  const settings = { STOCK_DAY_EQUITY_MULTIPLE: '0.6' };
  const gate = gateAt(settings, () => clock);
  // The venue shows none of them (cancelled, say): each is judged alone against the book, but all count for the day.
  const tape = () => alpacaVenue({ account: { ...CASH, buying_power: '50000' } });
  admitted(await send(buy('SPY', '10', '500'), { gate, tape: tape(), settings, clock: () => clock }), '$5,000');
  clock += 6000;
  admitted(await send(buy('QQQ', '2', '500'), { gate, tape: tape(), settings, clock: () => clock }), '$1,000: the day at exactly $6,000');
  clock += 6000;
  const over = await send(buy('IWM', '0.0001', '100'), { gate, tape: tape(), settings, clock: () => clock });  // $0.01
  assert.deepEqual([over.status, over.body.cap, over.tape.orders().length], [403, 'stock_day', 0]);
  assert.match(over.body.error, /^A buy of \$0\.01 would take today's stock buys to \$6000\.01, past the day's cap of \$6000\.00 \(0\.6x \$10000\.00 equity, STOCK_DAY_EQUITY_MULTIPLE; every buy admitted today counts, a cancelled one too\)\.$/);
  // A new day starts at zero; a close is never a buy and never meets this cap.
  const sale = { symbol: 'SPY', qty: '1', side: 'sell', type: 'limit', limit_price: '501', time_in_force: 'day' };
  assert.equal((await send(sale, { gate, settings, clock: () => clock, tape: alpacaVenue({ positions: [long('SPY', '10', '5000.00')] }) })).status, 200);
  clock = NOW + 24 * 3600000;
  admitted(await send(buy('IWM', '0.0001', '100'), { gate, tape: tape(), settings, clock: () => clock }), 'the next day');
  // As deployed (4x): $40,000 a day on $10,000.
  assert.equal(gateAt().stockStatus(NOW).day_equity_multiple, '4');
});

test('a buy whose forward got no answer counts for two minutes; one that never left the gateway is given back', async () => {
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
  // Past STOCK_PENDING_MS it is held as if answered then: it may have filled at the forward's timeout, and the account
  // and positions lag. It is no longer "in flight" on /v1/health.
  clock = NOW + STOCK_PENDING_MS + 1;
  const held = await send(buy('XLK', '5.00005', '200'), { gate, tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' } }), clock: () => clock });
  assert.deepEqual([held.status, held.body.cap], [403, 'stock_position'], 'the unanswered $4,000 still counts a minute on');
  assert.equal(gate.stockStatus(clock).in_flight, 0);
  clock = NOW + STOCK_PENDING_MS + STOCK_LEDGER_HOLD_MS + 1;
  admitted(await send(buy('XLK', '5.00005', '200'), { gate, tape: alpacaVenue({ account: { ...CASH, buying_power: '50000' } }), clock: () => clock }),
    'after two minutes the venue\'s own readings judge it');
  // A buy that could not be signed never reached the venue (the router refunds it before any dispatch): its place, its
  // dollars and its ledger entry are given back.
  const store = memoryStore();
  const bare = createGate({ store, env: env(), now: () => NOW });
  const ok = bare.reserve({ micro: String(usd('500')), venue: 'alpaca', stock: { symbol: 'SPY', equity_micro: String(usd('10000')),
    buying_power_micro: String(usd('10000')), multiplier: String(M), symbol_held_micro: '0', total_held_micro: '0', options_held_micro: '0', read_at: NOW } });
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

// ------------------------------------------------------------------------------------------------ closes: fresh and serialized

test('a stock order never decides from a cached reading: a "cover" of a short that is gone is judged as an open, a sale of shares gone is refused', async () => {
  // The review of Oct 10, 2026 (probes 1 and 2): this isolate's cache, filled by an option close a moment ago, still shows
  // SPY short 2 and AAPL long 10; the venue is already flat in both (another isolate covered and sold).
  const settings = { POSITIONS_CACHE_MS: '60000' };
  const CALL = 'SPY261016C00740000';
  const before = [{ symbol: 'SPY', qty: '-2', qty_available: '-2', side: 'short', market_value: '-1400', asset_class: 'us_equity' },
    long('AAPL', '10', '2500.00'), { symbol: CALL, qty: '2', qty_available: '2', side: 'long', market_value: '200', asset_class: 'us_option' }];
  const after = [before[2]];
  let reads = 0;
  const account = { equity: '1000.00', buying_power: '2000.00', regt_buying_power: '2000.00', multiplier: '2' };
  const tape = alpacaVenue({ account, positions: () => (reads++ === 0 ? before : after) });
  const gate = gateAt(settings);
  const optionClose = { symbol: CALL, qty: '1', side: 'sell', type: 'limit', limit_price: '1.00', time_in_force: 'day', position_intent: 'sell_to_close' };
  assert.equal((await send(optionClose, { gate, tape, settings })).status, 200, 'the option close fills the cache');
  // 2 SPY at $700 is $1,400: 140% of $1,000, against an ETF's $500. From the cache it was a "cover" at one micro-dollar.
  const cover = await send(buy('SPY', '2', '700'), { gate, tape, settings });
  assert.deepEqual([cover.status, cover.body.cap], [403, 'stock_order'], JSON.stringify(cover.body));
  // 10 AAPL from the cache was a sale of shares held; at the venue it would be a short sale.
  const sale = await send({ symbol: 'AAPL', qty: '10', side: 'sell', type: 'market', time_in_force: 'day' }, { gate, tape, settings });
  assert.equal(sale.status, 400);
  assert.match(sale.body.error, /^A stock order on the real account must close shares it holds: AAPL long \(10 needed, none held\)/);
  assert.equal(tape.orders().length, 1, 'only the option close went');
  assert.equal(gate.status(NOW).today.orders, 1);
  await send(buy('SPY', '1', '1'), { tape: alpacaVenue({ account: CASH }) });  // the cache off again for what follows
});

test('two sales of the same shares at once: one goes, the other is refused in the Gate; a cover likewise, at most the short', async () => {
  // Probe 3: one isolate, two sales of the same 10 held shares in flight together. Each reads the venue fresh (10
  // available); the Gate admits the first and takes it off the second's reading.
  const gate = gateAt();
  const tape = alpacaVenue({ positions: [long('AAPL', '10', '2500.00')] });
  const sale = { symbol: 'AAPL', qty: '10', side: 'sell', type: 'market', time_in_force: 'day' };
  const both = await Promise.all([send(sale, { gate, tape }), send({ ...sale, type: 'limit', limit_price: '250' }, { gate, tape })]);
  assert.deepEqual(both.map(result => result.status).sort(), [200, 409]);
  const loser = both.find(result => result.status === 409);
  assert.equal(loser.body.cap, 'stock_close');
  assert.match(loser.body.error, /^A stock order on the real account must close shares it holds: AAPL long \(10 needed, 0 long left of 10 available once 10 already being closed by orders in flight are taken off\)\. A sale of shares not held long would be a short sale: refused\.$/);
  assert.equal(tape.orders().length, 1, 'ten shares sent, never twenty');
  assert.equal(gate.status(NOW).today.orders, 1);
  // Part of what is left goes: 10 held, 6 in flight, 4 more admitted, 0.000000001 more refused.
  const part = gateAt();
  const venue = alpacaVenue({ positions: [long('AAPL', '10', '2500.00')] });
  assert.equal((await send({ ...sale, qty: '6' }, { gate: part, tape: venue })).status, 200);
  assert.equal((await send({ ...sale, qty: '4' }, { gate: part, tape: venue })).status, 200);
  const extra = await send({ ...sale, qty: '0.000000001' }, { gate: part, tape: venue });
  assert.deepEqual([extra.status, extra.body.cap], [409, 'stock_close']);
  // A cover: 100 short, 60 in flight, 60 more refused, 40 admitted.
  const shorts = [{ symbol: 'XOM', qty: '-100', qty_available: '-100', side: 'short', market_value: '-11000', asset_class: 'us_equity' }];
  const covers = gateAt();
  const book = alpacaVenue({ positions: shorts });
  const cover = qty => ({ symbol: 'XOM', qty, side: 'buy', type: 'market', time_in_force: 'day' });
  assert.equal((await send(cover('60'), { gate: covers, tape: book })).status, 200);
  const twice = await send(cover('60'), { gate: covers, tape: book });
  assert.deepEqual([twice.status, twice.body.cap], [409, 'stock_close']);
  assert.match(twice.body.error, /XOM short \(60 needed, 40 short left of 100 available once 60 already being closed by orders in flight are taken off\)\. A buy that covers no short would open a position: refused\.$/);
  assert.equal((await send(cover('40'), { gate: covers, tape: book })).status, 200);
  assert.equal(book.accountReads().length, 0, 'a cover never waits on the account');
  // A sale and a cover are counted apart, and so are two symbols.
  assert.equal(covers.stockStatus(NOW).closes_in_flight, 0, 'all answered');
});

// The design review of Oct 10, 2026: the venue's positions can lag a filled sale while its order has left the open list.
// A close is held a minute after its answer, judged against the open orders (read first) and the positions together.
const sell = (symbol, qty, extra = {}) => ({ symbol, qty, side: 'sell', type: 'limit', limit_price: '250', time_in_force: 'day',
  client_order_id: `sell-${symbol}-${qty}`, ...extra });
const restingSell = (symbol, qty, extra = {}) => ({ id: `s-${symbol}-${qty}`, symbol, qty, filled_qty: '0', side: 'sell', type: 'limit',
  limit_price: '250', order_class: 'simple', status: 'new', client_order_id: `sell-${symbol}-${qty}`, ...extra });
/** A close refused with only what came before reserved and nothing more sent. */
const stopped = (result, status, pattern, message = '') => {
  assert.equal(result.status, status, `${message} ${JSON.stringify(result.body)}`);
  if (pattern) assert.match(result.body.error, pattern, message);
  assert.equal(result.tape.orders().length, 0, `${message}: nothing forwarded`);
};

test('a sale filled while the positions lag is not sold again within the minute: never a short sale; a cover likewise never over-buys', async () => {
  let clock = NOW;
  const gate = gateAt({}, () => clock);
  const venue = () => alpacaVenue({ positions: [long('AAPL', '10', '2500.00')] });  // the 10 shares as the venue still shows them
  assert.equal((await send(sell('AAPL', '10'), { gate, tape: venue(), clock: () => clock })).status, 200, 'the sale of all 10 goes and fills');
  // Twenty seconds on its order has left the open list, and the positions still show the 10 shares: a reading alone
  // would let them be sold again, which is a short sale.
  for (const at of [NOW + 20000, NOW + STOCK_LEDGER_HOLD_MS]) {
    clock = at;
    for (const qty of ['10', '0.000000001']) {
      stopped(await send(sell('AAPL', qty), { gate, tape: venue(), clock: () => clock }), 409,
        new RegExp(`^A stock order on the real account must close shares it holds: AAPL long \\(${qty.replace('.', '\\.')} needed, 0 long left of 10 available once 10 already being closed by orders in flight are taken off\\)\\. A sale of shares not held long would be a short sale: refused\\.$`),
        `${at - NOW} ms, ${qty}`);
    }
  }
  // Once the positions show it, the reading itself refuses.
  clock = NOW + STOCK_LEDGER_HOLD_MS + 1;
  stopped(await send(sell('AAPL', '10'), { gate, tape: alpacaVenue({ positions: [] }), clock: () => clock }), 400, /AAPL long \(10 needed, none held\)/);
  assert.equal(gate.status(clock).today.orders, 1, 'one sale in all');
  // A cover: 100 short, 60 covered and filled, the positions still showing 100 short. 40 more may go, never 60.
  clock = NOW;
  const covers = gateAt({}, () => clock);
  const short = () => alpacaVenue({ positions: [{ symbol: 'XOM', qty: '-100', qty_available: '-100', side: 'short', market_value: '-11000', asset_class: 'us_equity' }] });
  const cover = qty => ({ symbol: 'XOM', qty, side: 'buy', type: 'limit', limit_price: '110', time_in_force: 'day', client_order_id: `cover-${qty}` });
  assert.equal((await send(cover('60'), { gate: covers, tape: short(), clock: () => clock })).status, 200);
  clock = NOW + 30000;
  stopped(await send(cover('60'), { gate: covers, tape: short(), clock: () => clock }), 409,
    /XOM short \(60 needed, 40 short left of 100 available once 60 already being closed by orders in flight are taken off\)\. A buy that covers no short would open a position: refused\.$/);
  assert.equal((await send(cover('40'), { gate: covers, tape: short(), clock: () => clock })).status, 200, 'exactly the rest of the short');
  stopped(await send(cover('0.000000001'), { gate: covers, tape: short(), clock: () => clock }), 409, /0 short left of 100 available once 100/);
});

test('a partial sale leaves exactly the rest sellable, shown or not: in flight, filled with the positions current, filled with them lagging', async () => {
  // 10 held, 4 sold at NOW; ten seconds on, the venue shows it one of three ways. 6 more may go, and not a share past 6.
  const cases = [
    ['in flight: nothing shows it yet', { positions: [long('AAPL', '10', '2500.00')] }, 409],
    ['filled, the positions current', { positions: [long('AAPL', '6', '1500.00')] }, 400],
    ['filled, the positions lagging', { positions: [long('AAPL', '10', '2500.00')] }, 409],
  ];
  for (const [name, after, over] of cases) {
    const judged = async qty => {
      let clock = NOW;
      const gate = gateAt({}, () => clock);
      assert.equal((await send(sell('AAPL', '4'), { gate, tape: alpacaVenue({ positions: [long('AAPL', '10', '2500.00')] }), clock: () => clock })).status, 200);
      clock = NOW + 10000;
      return send(sell('AAPL', qty), { gate, tape: alpacaVenue(after), clock: () => clock });
    };
    stopped(await judged('6.000000001'), over, over === 409 ? /\(6\.000000001 needed, 6 long left of / : /6\.000000001 needed, 6 long held/, name);
    assert.equal((await judged('6')).status, 200, `${name}: exactly the rest`);
  }
});

test('a held sale the venue lists as an open order is counted once, never as held and as open both', async () => {
  // 10 held, 4 sold at NOW as client_order_id "sell-AAPL-4"; ten seconds on the venue lists it, resting or part filled,
  // with `qty_available` netting it or lagging it. 6 more may go every time: not 2, which is counting the 4 twice. The
  // Gate counts a shown sale by how far what is free has fallen since it was admitted, so one sent without a
  // client_order_id (the venue names it) is counted once too.
  const anonymous = { client_order_id: undefined };
  const cases = [
    ['resting, qty_available net of it', [restingSell('AAPL', '4')], [long('AAPL', '10', '2500.00', { qty_available: '6' })], 400],
    ['resting, qty_available lagging it', [restingSell('AAPL', '4')], [long('AAPL', '10', '2500.00')], 409],
    ['2 of 4 filled, the positions current', [restingSell('AAPL', '4', { filled_qty: '2' })], [long('AAPL', '8', '2000.00', { qty_available: '6' })], 400],
    ['2 of 4 filled, the positions lagging', [restingSell('AAPL', '4', { filled_qty: '2' })], [long('AAPL', '10', '2500.00', { qty_available: '8' })], 409],
    ['resting, sent with no client_order_id', [restingSell('AAPL', '4', { client_order_id: 'venue-named' })], [long('AAPL', '10', '2500.00')], 409, anonymous],
  ];
  for (const [name, openOrders, positions, over, first = {}] of cases) {
    const judged = async qty => {
      let clock = NOW;
      const gate = gateAt({}, () => clock);
      assert.equal((await send(sell('AAPL', '4', first), { gate, tape: alpacaVenue({ positions: [long('AAPL', '10', '2500.00')] }), clock: () => clock })).status, 200);
      clock = NOW + 10000;
      return send(sell('AAPL', qty), { gate, tape: alpacaVenue({ positions, openOrders }), clock: () => clock });
    };
    assert.equal((await judged('6')).status, 200, `${name}: exactly the rest`);
    stopped(await judged('6.000000001'), over, null, name);
  }
});

test('a fill of an older sale the ledger no longer holds hides no held one; open orders are read first and fail closed', async () => {
  // 10 held, a sale of 3 resting from long ago (the venue's qty_available nets it), and 7 sold at NOW. Then the old 3 fill
  // and the positions show it, while the 7 have filled and do not show yet: nothing is left. Compared with the bare
  // position (10 then, 7 now), the 3 that fell would hide the 7 still to show, and 3 more would be sold short.
  let clock = NOW;
  const gate = gateAt({}, () => clock);
  const before = alpacaVenue({ openOrders: [restingSell('AAPL', '3', { client_order_id: 'long-ago' })], positions: [long('AAPL', '10', '2500.00', { qty_available: '7' })] });
  stopped(await send(sell('AAPL', '7.000000001'), { gate, tape: before, clock: () => clock }), 400, /7\.000000001 needed, 7 long held/);
  assert.equal((await send(sell('AAPL', '7'), { gate, tape: before, clock: () => clock })).status, 200, 'all that is free');
  clock = NOW + 10000;
  const after = alpacaVenue({ positions: [long('AAPL', '7', '1750.00')] });
  stopped(await send(sell('AAPL', '0.000000001'), { gate, tape: after, clock: () => clock }), 409, /\(0\.000000001 needed, 0 long left of 7 available once 7 /);
  // Read the open orders before the positions: an order that fills between the two reads is counted in both, never in
  // neither. Here the old 3 fill between them: 4 are judged free, not 7.
  let filled = false;
  const racing = alpacaVenue({ openOrders: () => (filled ? [] : [restingSell('AAPL', '3', { client_order_id: 'long-ago' })]),
    positions: () => (filled ? [long('AAPL', '7', '1750.00')] : [long('AAPL', '10', '2500.00', { qty_available: '7' })]) });
  const fetcher = async (url, init = {}) => {
    const answer = await racing.fetcher(url, init);
    if (/\/v2\/orders\?/.test(url)) filled = true;
    return answer;
  };
  const free = closeAvailable('AAPL', 'sell', [long('AAPL', '7', '1750.00')], [restingSell('AAPL', '3')]);
  assert.deepEqual(free, { available: 4n * 10n ** 12n });
  const race = await send(sell('AAPL', '4.000000001'), { tape: { ...racing, fetcher } });
  stopped(race, 409, /\(4\.000000001 needed, 4 long left of 4 available once 0 /);
  assert.deepEqual(racing.calls.map(made => new URL(made.url).pathname), ['/v2/orders', '/v2/positions'], 'the open orders, then the positions');
  // What closeAvailable counts: open orders of the symbol on the same side, net of fills; never below zero; and it fails
  // closed on a list that may be cut off or an open order with no qty. A cover reads the open buys.
  const shortRow = { symbol: 'XOM', qty: '-100', qty_available: '-100', side: 'short' };
  assert.deepEqual(closeAvailable('XOM', 'buy', [shortRow], [{ symbol: 'XOM', side: 'buy', qty: '30', filled_qty: '10' }, restingSell('XOM', '5')]),
    { available: 80n * 10n ** 12n });
  assert.deepEqual(closeAvailable('AAPL', 'sell', [long('AAPL', '2', '500')], [restingSell('AAPL', '3'), { ...restingSell('AAPL', '9'), side: 'buy' }, restingSell('MSFT', '1')]),
    { available: 0n });
  assert.equal(closeAvailable('AAPL', 'sell', [], [{ symbol: 'AAPL', side: 'sell', notional: '100' }]).source, 'orders');
  assert.equal(closeAvailable('AAPL', 'sell', [], Array.from({ length: 500 }, () => restingSell('MSFT', '1'))).source, 'orders');
  assert.equal(closeAvailable('AAPL', 'sell', [], {}).source, 'orders');
  for (const [openOrders, why] of [[502, /^Cannot read the real account's open orders: venue HTTP 502\.$/],
    [[{ symbol: 'AAPL', side: 'sell', notional: '100', id: 'n' }], /^Cannot check what the real account has free to close: the open sell order for AAPL has no qty to count it by\.$/]]) {
    const result = await send(sell('AAPL', '1'), { tape: alpacaVenue({ openOrders, positions: [long('AAPL', '10', '2500.00')] }) });
    refused(result, 424, 'orders', why);
  }
});

test('a close is held a minute after its answer, two minutes with none; one that never left is given back', async () => {
  let clock = NOW;
  const gate = gateAt({}, () => clock);
  const sale = { symbol: 'AAPL', qty: '10', side: 'sell', type: 'limit', limit_price: '250', time_in_force: 'day' };
  const held = () => alpacaVenue({ positions: [long('AAPL', '10', '2500.00')] });
  // The venue refused the first sale (an answer all the same). The Gate holds every answered close for STOCK_LEDGER_HOLD_MS
  // (the design review of Oct 10, 2026): from its readings alone a refused sale and a filled one the positions do not
  // show yet look the same. A reading begun a minute after the answer judges alone.
  const refusing = alpacaVenue({ positions: [long('AAPL', '10', '2500.00')], order: 403 });
  assert.equal((await send(sale, { gate, tape: refusing, clock: () => clock })).status, 403, 'the venue\'s own refusal');
  assert.equal((await send(sale, { gate, tape: held(), clock: () => clock })).status, 409, 'at once: it may not show yet');
  clock = NOW + 5001;
  assert.equal((await send(sale, { gate, tape: held(), clock: () => clock })).status, 409, 'five seconds on: still held');
  clock = NOW + STOCK_LEDGER_HOLD_MS;
  assert.equal((await send(sale, { gate, tape: held(), clock: () => clock })).status, 409, 'exactly a minute on: still held');
  clock = NOW + STOCK_LEDGER_HOLD_MS + 1;
  assert.equal((await send(sale, { gate, tape: held(), clock: () => clock })).status, 200, 'a minute on, the venue judges');
  // A resting sale shows at the venue as shares no longer available: a second sale is refused by the reading itself.
  clock = NOW + STOCK_LEDGER_HOLD_MS + 6000;
  const resting = await send(sale, { gate, tape: alpacaVenue({ positions: [long('AAPL', '10', '2500.00', { qty_available: '0' })] }), clock: () => clock });
  assert.equal(resting.status, 400);
  assert.match(resting.body.error, /AAPL long \(10 needed, none held\)/);
  // No answer: it is held as if answered when STOCK_PENDING_MS ran out, two minutes in all.
  const silent = held();
  const lost = { ...silent, fetcher: async (url, init = {}) => {
    if (init.method === 'POST') throw Object.assign(new Error('timeout'), { name: 'TimeoutError' });
    return silent.fetcher(url, init);
  } };
  const quiet = gateAt({}, () => clock);
  const sent = clock;
  assert.equal((await send(sale, { gate: quiet, tape: lost, clock: () => clock })).status, 502);
  assert.equal(quiet.stockStatus(clock).closes_in_flight, 1);
  clock = sent + 30000;
  assert.equal((await send(sale, { gate: quiet, tape: held(), clock: () => clock })).status, 409, 'at 30 s');
  clock = sent + STOCK_PENDING_MS + 1;
  assert.equal((await send(sale, { gate: quiet, tape: held(), clock: () => clock })).status, 409, 'after a minute: still held');
  assert.equal(quiet.stockStatus(clock).closes_in_flight, 0, 'held, no longer in flight');
  clock = sent + STOCK_PENDING_MS + STOCK_LEDGER_HOLD_MS + 1;
  assert.equal((await send(sale, { gate: quiet, tape: held(), clock: () => clock })).status, 200, 'after two minutes');
  // A close that never reached the venue (refunded before any dispatch) leaves the ledger and the day's count.
  const store = memoryStore();
  const bare = createGate({ store, env: env(), now: () => NOW });
  const close = { symbol: 'AAPL', side: 'sell', qty: String(10n * 10n ** 12n), available: String(10n * 10n ** 12n), read_at: NOW };
  const ok = bare.reserve({ micro: '1', venue: 'alpaca', exit: true, stock_close: close });
  assert.equal(ok.ok, true);
  assert.equal(bare.stockStatus(NOW).closes_in_flight, 1);
  bare.refund({ ...ok, at: NOW });
  assert.deepEqual([bare.stockStatus(NOW).closes_in_flight, bare.status(NOW).today.orders], [0, 0]);
  assert.equal(bare.reserve({ micro: '1', venue: 'alpaca', exit: true, stock_close: close }).ok, true, 'its shares are available again');
});

test('the Gate judges a close only from a reading it can use: malformed, stale, or a buy and a close at once admit nothing', () => {
  const close = (extra = {}) => ({ symbol: 'AAPL', side: 'sell', qty: String(10n ** 12n), available: String(10n ** 12n), read_at: NOW, ...extra });
  for (const extra of [{ symbol: '' }, { side: 'short' }, { qty: '0' }, { qty: '-1' }, { qty: '1.5' }, { available: undefined }, { available: '-1' }, { read_at: 'x' }]) {
    const answer = gateAt().reserve({ micro: '1', venue: 'alpaca', exit: true, stock_close: close(extra) });
    assert.deepEqual([answer.ok, answer.status, answer.cap], [false, 400, 'stock'], JSON.stringify(extra));
  }
  for (const readAt of [NOW - 120001, NOW + 5001]) {
    const answer = gateAt().reserve({ micro: '1', venue: 'alpaca', exit: true, stock_close: close({ read_at: readAt }) });
    assert.deepEqual([answer.ok, answer.status, answer.cap], [false, 424, 'positions'], String(readAt - NOW));
  }
  const both = gateAt().reserve({ micro: '1', venue: 'alpaca', exit: true, stock_close: close(), stock: { symbol: 'SPY' } });
  assert.deepEqual([both.ok, both.status, both.cap], [false, 400, 'stock']);
  const killed = gateAt();
  killed.setKill(true, NOW);
  assert.equal(killed.reserve({ micro: '1', venue: 'alpaca', exit: true, stock_close: close() }).status, 423, 'the kill switch stops a close');
  // What a reading leaves to close: qty_available when given, signed by side.
  const held = availableHeld([long('AAPL', '10', '1', { qty_available: '4' }), { symbol: 'XOM', qty: '-3', side: 'short' }, { symbol: 'X', qty: '-1', side: 'long' }]);
  assert.deepEqual([...held.entries()], [['AAPL', 4n * 10n ** 12n], ['XOM', -3n * 10n ** 12n]]);
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
    ['margin account with no overnight buying power', { account: { equity: '10000.00', buying_power: '20000.00', multiplier: '2' } }, 503, 'equity',
      /no regt_buying_power field/],
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
  const tape = alpacaVenue({ account: { ...CASH, buying_power: '50000' }, positions: [long('IWM', '10', '2000.00')] });
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
    buying_power_micro: String(usd('10000')), multiplier: String(M), symbol_held_micro: '0', total_held_micro: '0', options_held_micro: '0', read_at: NOW } });
  assert.deepEqual([answer.ok, answer.status, answer.cap], [false, 403, 'stock_buys']);
});

test('the gate judges only what it can read: a malformed reading, an unlisted symbol or a stale one admits nothing', () => {
  const stock = (extra = {}) => ({ symbol: 'SPY', equity_micro: String(usd('10000')), buying_power_micro: String(usd('10000')),
    multiplier: String(M), symbol_held_micro: '0', total_held_micro: '0', options_held_micro: '0', read_at: NOW, ...extra });
  const reserve = (gate, extra, micro = usd('100')) => gate.reserve({ micro: String(micro), venue: 'alpaca', stock: stock(extra) });
  for (const extra of [{ symbol: 'TSLA' }, { equity_micro: '1.5' }, { buying_power_micro: undefined }, { multiplier: 'x' },
    { symbol_held_micro: null }, { total_held_micro: '' }, { options_held_micro: undefined }, { options_held_micro: '-1' },
    { options_held_micro: '1' }, { read_at: 'soon' }]) {
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
  const tape = alpacaVenue({ account: { equity: '10000.0000009', buying_power: '19999.999999999', regt_buying_power: '20000', multiplier: '2' } });
  assert.deepEqual(await readStockAccount(env(), { fetcher: tape.fetcher, now: () => NOW }),
    { ok: true, at: NOW, equity_micro: '10000000000', buying_power_micro: '19999999999', multiplier: '2000000' });
  assert.equal(tape.calls[0].url, 'https://api.alpaca.markets/v2/account');
  // The lower of the intraday and the overnight figure; a margin account without the overnight one is no reading.
  const read = async account => readStockAccount(env(), { fetcher: alpacaVenue({ account }).fetcher, now: () => NOW });
  assert.equal((await read({ equity: '10000', buying_power: '40000', regt_buying_power: '12000.5', multiplier: '4' })).buying_power_micro, '12000500000');
  assert.equal((await read({ equity: '10000', buying_power: '900', regt_buying_power: 12000, multiplier: '2' })).buying_power_micro, '900000000');
  assert.equal((await read({ equity: '10000', buying_power: '10000', multiplier: '1' })).buying_power_micro, '10000000000', 'cash: its cash, no overnight figure needed');
  for (const account of [{ equity: '10000', buying_power: '20000', multiplier: '2' }, { equity: '10000', buying_power: '40000', multiplier: '4' },
    { equity: '10000', buying_power: '10000', regt_buying_power: 'x', multiplier: '1' }, { equity: '10000', buying_power: '20000', regt_buying_power: {}, multiplier: '2' }]) {
    assert.deepEqual(await read(account), { ok: false, at: NOW, error: 'alpaca account: no regt_buying_power field' }, JSON.stringify(account));
  }
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
  assert.deepEqual(stockExposure('SPY', positions, orders), { symbolMicro: usd('2000'), totalMicro: usd('2840.500001'), optionsMicro: usd('250'), openBuys: [] },
    'SPY: $1,000 held, $1,000 resting; the book: $1,650.000001 long (the option too, $250 of it unmarginable), $1,190.50 on order; shorts, sells, covers and filled orders not');
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
    enabled: true, etf_equity_share: '0.5', stock_equity_share: '0.2', max_equity_multiple: '2', day_equity_multiple: '4',
    symbols: {
      etf: ['SPY', 'QQQ', 'IWM', 'DIA', 'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY', 'TLT', 'GLD'],
      stock: ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'BRK.B', 'JPM', 'V', 'UNH', 'XOM', 'JNJ', 'PG', 'MA', 'HD', 'AVGO', 'LLY', 'COST'],
    },
    day_buys_usd: '271.50', in_flight: 0, in_flight_usd: '0.00', closes_in_flight: 0, buys_admitted: true,
  });
  assert.equal(gateAt({ STOCK_BUYS_REAL: 'off' }).status(NOW).stock_buys.enabled, false);
});

test('the Durable Object settles a stock buy in one transaction', () => {
  const source = readFileSync(new URL('../worker.mjs', import.meta.url), 'utf8');
  assert.match(source, /\bstockSettle\(request\) \{ return this\.ctx\.storage\.transactionSync\(\(\) => this\.gate\.stockSettle\(request\)\); \}/);
});
