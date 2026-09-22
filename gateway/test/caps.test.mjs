// What the gateway will meter, and what it thinks an order is worth.

import assert from 'node:assert/strict';
import test from 'node:test';

import { createsOrder, notional, caps, normalizePath, allowedVenuePath, isOptionSymbol } from '../lib/caps.mjs';
import { formatUsd, parsePico, mulPico, picoToMicro } from '../lib/money.mjs';

const usd = micro => formatUsd(micro);

test('only the order-creating calls are metered', () => {
  assert.equal(createsOrder('kalshi', 'POST', 'portfolio/events/orders'), true);
  assert.equal(createsOrder('kalshi', 'POST', '/portfolio/orders/'), true);
  assert.equal(createsOrder('alpaca', 'POST', 'v2/orders'), true);
  // Reads and cancels always pass.
  assert.equal(createsOrder('kalshi', 'GET', 'portfolio/orders'), false);
  assert.equal(createsOrder('kalshi', 'DELETE', 'portfolio/events/orders/abc'), false);
  assert.equal(createsOrder('alpaca', 'DELETE', 'v2/orders/abc'), false);
  assert.equal(createsOrder('alpaca', 'GET', 'v2/orders'), false);
  // A venue this gateway does not serve creates nothing here.
  assert.equal(createsOrder('schwab', 'POST', 'v2/orders'), false);
  assert.equal(normalizePath('/a/b/'), 'a/b');
});

test('kalshi v2 orders are count x decimal-dollar price', () => {
  assert.equal(usd(notional('kalshi', { ticker: 'T', side: 'bid', count: '3.00', price: '0.6500' }).micro), '1.95');
  assert.equal(usd(notional('kalshi', { count: '100', price: '0.0125' }).micro), '1.25');
});

test('kalshi legacy orders are count x price in cents, and a market buy is its own ceiling', () => {
  assert.equal(usd(notional('kalshi', { count: 4, yes_price: 65 }).micro), '2.60');
  assert.equal(usd(notional('kalshi', { count: 4, no_price: 35 }).micro), '1.40');
  assert.equal(usd(notional('kalshi', { count: 7, buy_max_cost: 700 }).micro), '7.00');
  // No price of any kind: a contract can never settle above a dollar, so count dollars is the cap.
  assert.equal(usd(notional('kalshi', { count: 9 }).micro), '9.00');
});

test('kalshi refuses a body it cannot price', () => {
  assert.match(notional('kalshi', { price: '0.5' }).error, /count/);
  assert.match(notional('kalshi', { count: '0', price: '0.5' }).error, /count/);
  assert.match(notional('kalshi', null).error, /body/);
});

test('alpaca prices qty with the reference the router supplies', () => {
  const body = { symbol: 'BTC/USD', qty: '0.00015', side: 'buy', type: 'market' };
  assert.equal(usd(notional('alpaca', body, { reference: '64050.11' }).micro), '9.61');
  assert.match(notional('alpaca', body).error, /X-LTCM-Reference-Price/);
});

test('alpaca uses notional directly and falls back to a limit or stop price', () => {
  assert.equal(usd(notional('alpaca', { symbol: 'AAPL', notional: '25' }).micro), '25.00');
  assert.equal(usd(notional('alpaca', { qty: '0.5', limit_price: '60' }).micro), '30.00');
  assert.equal(usd(notional('alpaca', { qty: '0.5', stop_price: '60' }).micro), '30.00');
  // The dearest of the reference and the order's own prices: a header cannot underprice a limit.
  assert.equal(usd(notional('alpaca', { qty: '0.5', limit_price: '60' }, { reference: '0.01' }).micro), '30.00');
  assert.equal(usd(notional('alpaca', { qty: '0.5', limit_price: '60' }, { reference: '70' }).micro), '35.00');
  assert.equal(usd(notional('alpaca', { qty: '0.5', limit_price: '60', stop_price: '80' }).micro), '40.00');
  // A short sale is worth what it sells.
  assert.equal(usd(notional('alpaca', { qty: '2', side: 'sell', limit_price: '10' }).micro), '20.00');
});

test('alpaca refuses a body it cannot price, and an unknown venue is never priced', () => {
  assert.match(notional('alpaca', {}).error, /qty/);
  assert.match(notional('alpaca', { qty: '0', limit_price: '5' }).error, /qty/);
  assert.match(notional('alpaca', { qty: '-1', limit_price: '5' }).error, /qty/);
  assert.match(notional('alpaca', { qty: '1', limit_price: '0' }).error, /Cannot price/);
  assert.match(notional('alpaca', null).error, /body/);
  for (const venue of ['schwab', 'binance', '', undefined]) {
    const priced = notional(venue, { count: '1', price: '0.5', qty: '1', limit_price: '1', notional: '1' });
    assert.match(priced.error, /unknown venue/);
    assert.equal(priced.micro, undefined);
  }
});

test('caps come from vars, and a nonsense value falls back to the documented default', () => {
  const custom = caps({ MAX_ORDER_USD: '12.5', MAX_DAY_USD: '99', MAX_DAY_ORDERS: '7', CAP_TIMEZONE: 'UTC' });
  assert.equal(usd(custom.maxOrderMicro), '12.50');
  assert.equal(usd(custom.maxDayMicro), '99.00');
  assert.equal(custom.maxDayOrders, 7);
  assert.equal(custom.timezone, 'UTC');
  const fallback = caps({ MAX_ORDER_USD: 'nope', MAX_DAY_USD: '-5', MAX_DAY_ORDERS: '1e9999' });
  assert.equal(usd(fallback.maxOrderMicro), '50.00');
  assert.equal(usd(fallback.maxDayMicro), '400.00');
  assert.equal(fallback.maxDayOrders, 60);
  assert.equal(caps({}).timezone, 'America/New_York');
});

test('money is exact, and a partial cent always rounds against the order', () => {
  // 0.1 + 0.2 arithmetic has no place near a cap.
  assert.equal(usd(picoToMicro(mulPico(parsePico('0.1'), parsePico('0.2')))), '0.02');
  assert.equal(usd(picoToMicro(mulPico(parsePico('3'), parsePico('0.333333')))), '1.00');
  assert.equal(usd(1n), '0.01', 'a fraction of a cent is charged as a cent');
  assert.equal(parsePico('abc'), null);
  assert.equal(parsePico(Number.NaN), null);
});

test('account state is readable and never an order path', () => {
  assert.equal(allowedVenuePath('alpaca', 'GET', 'v2/account'), true);
  assert.equal(allowedVenuePath('alpaca', 'GET', 'v2/positions'), true);
  assert.equal(allowedVenuePath('alpaca', 'GET', 'v2/positions/AAPL'), true);
  assert.equal(allowedVenuePath('alpaca', 'POST', 'v2/account/configurations'), false);
  assert.equal(allowedVenuePath('alpaca', 'DELETE', 'v2/positions'), false);
  assert.equal(createsOrder('alpaca', 'GET', 'v2/account'), false);
  // A venue that is not served has no allowed path at all.
  assert.equal(allowedVenuePath('schwab', 'GET', 'v2/account'), false);
});

test('funding history is read-only and cannot move money', () => {
  for (const [venue, path] of [['kalshi', 'portfolio/deposits'], ['kalshi', 'portfolio/withdrawals'],
    ['alpaca', 'v2/account/activities'], ['alpaca', 'v2/account/activities/FILL']]) {
    assert.equal(allowedVenuePath(venue, 'GET', path), true);
    for (const method of ['POST', 'PUT', 'DELETE']) assert.equal(allowedVenuePath(venue, method, path), false);
    assert.equal(createsOrder(venue, 'GET', path), false);
  }
});

// ---------------------------------------------------------------------------------- options
const CALL = 'SPY261016C00740000';
const option = extra => ({ symbol: CALL, qty: '1', side: 'buy', type: 'limit', limit_price: '0.70', position_intent: 'buy_to_open', time_in_force: 'day', ...extra });

test('an option contract is a hundred shares: one contract at 0.70 spends $70, not 70 cents', () => {
  // Measured Sept 19, 2026: this was priced at qty x limit with no multiplier.
  assert.equal(usd(notional('alpaca', option()).micro), '70.00');
  assert.equal(usd(notional('alpaca', option({ qty: '3', limit_price: '0.25' })).micro), '75.00');
  assert.equal(usd(notional('alpaca', option({ side: 'sell', position_intent: 'sell_to_close', limit_price: '1.10' })).micro), '110.00');
});

test('an option order is long premium only: it opens by buying and closes by selling', () => {
  for (const bad of [
    { side: 'sell', position_intent: 'sell_to_open' },
    { side: 'sell', position_intent: 'buy_to_open' },
    { side: 'sell' , position_intent: undefined },
    { side: 'buy', position_intent: 'buy_to_close' },
    { position_intent: undefined },
  ]) assert.match(notional('alpaca', option(bad)).error, /long premium only/, JSON.stringify(bad));
});

test('an option order is one leg, a limit order, in whole contracts', () => {
  assert.match(notional('alpaca', option({ order_class: 'mleg' })).error, /Multi-leg/);
  assert.match(notional('alpaca', option({ legs: [] })).error, /Multi-leg/);
  assert.match(notional('alpaca', option({ type: 'market', limit_price: undefined })).error, /limit order/);
  assert.match(notional('alpaca', option({ limit_price: undefined })).error, /limit price/);
  assert.match(notional('alpaca', option({ qty: '0.5' })).error, /whole number/);
  assert.match(notional('alpaca', option({ qty: undefined, notional: '50' })).error, /contracts, not dollars/);
});

test('only an OCC symbol is an option', () => {
  for (const yes of [CALL, 'F260925P00012000', 'BRKB261016C00500000']) assert.ok(isOptionSymbol(yes), yes);
  for (const no of ['SPY', 'BTC/USD', 'SPY261016X00740000', 'spy261016c00740000', '', null, 'SPY261016C0074000']) assert.ok(!isOptionSymbol(no), String(no));
});

test('the gateway signs reads of option contracts and option data, and nothing that writes them', () => {
  for (const path of ['v2/options/contracts', 'v2/options/contracts/SPY261016C00740000', 'v1beta1/options/snapshots/SPY', 'v1beta1/options/snapshots',
    'v1beta1/options/quotes/latest', 'v1beta1/options/trades/latest', 'v1beta1/options/bars', 'v1beta1/options/trades']) assert.ok(allowedVenuePath('alpaca', 'GET', path), path);
  for (const [method, path] of [['POST', 'v2/options/contracts'], ['POST', 'v2/positions/SPY261016C00740000/exercise'], ['GET', 'v1beta1/options/meta/exchanges/../x'], ['POST', 'v1beta1/options/trades'], ['GET', 'v1beta1/options/trades/SPY'],
    ['DELETE', 'v2/positions'], ['GET', 'v1beta1/options/snapshots/SPY/extra']]) assert.ok(!allowedVenuePath('alpaca', method, path), `${method} ${path}`);
});

test('a v2 order is metered on the leg it trades, not the YES number on the wire', () => {
  // Buying NO at $0.96: the adapter sends the YES-scale ask 0.04, and it costs $0.96 a contract.
  assert.equal(usd(notional('kalshi', { ticker: 'T', side: 'ask', count: '10.00', price: '0.0400' }).micro), '9.60');
  assert.equal(usd(notional('kalshi', { ticker: 'T', side: 'ask', count: '100.00', price: '0.0400' }).micro), '96.00');
  // Buying YES is the wire's number.
  assert.equal(usd(notional('kalshi', { ticker: 'T', side: 'bid', count: '10.00', price: '0.9600' }).micro), '9.60');
  // Exits: selling YES rests on the ask at the YES price; selling NO rests on the bid at its complement.
  assert.equal(usd(notional('kalshi', { ticker: 'T', side: 'ask', count: '10.00', price: '0.9600' }, { exit: true }).micro), '9.60');
  assert.equal(usd(notional('kalshi', { ticker: 'T', side: 'bid', count: '10.00', price: '0.0400' }, { exit: true }).micro), '9.60');
  // A body without a book side keeps the old reading.
  assert.equal(usd(notional('kalshi', { count: '100', price: '0.0125' }).micro), '1.25');
});
