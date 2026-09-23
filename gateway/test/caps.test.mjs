// What the gateway will meter, and what it thinks an order is worth.

import assert from 'node:assert/strict';
import test from 'node:test';

import { createsOrder, notional, caps, normalizePath, allowedVenuePath, isOptionSymbol, alpacaShapeError, alpacaSymbolError, ALPACA_ORDER_FIELDS } from '../lib/caps.mjs';
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
  assert.match(notional('alpaca', body).error, /no venue quote/);
});

test('alpaca uses notional directly and prices a limit order at its limit', () => {
  const aapl = extra => ({ symbol: 'AAPL', type: 'limit', ...extra });
  assert.equal(usd(notional('alpaca', aapl({ type: 'market', notional: '25' })).micro), '25.00');
  assert.equal(usd(notional('alpaca', aapl({ qty: '0.5', limit_price: '60' })).micro), '30.00');
  // The dearest of the reference and the order's own limit: a header cannot underprice a limit.
  assert.equal(usd(notional('alpaca', aapl({ qty: '0.5', limit_price: '60' }), { reference: '0.01' }).micro), '30.00');
  assert.equal(usd(notional('alpaca', aapl({ qty: '0.5', limit_price: '60' }), { reference: '70' }).micro), '35.00');
  // A short sale is worth what it sells.
  assert.equal(usd(notional('alpaca', aapl({ qty: '2', side: 'sell', limit_price: '10' })).micro), '20.00');
});

test('alpaca refuses a body it cannot price, and an unknown venue is never priced', () => {
  assert.match(notional('alpaca', { symbol: 'AAPL', type: 'limit', limit_price: '5' }).error, /qty/);
  assert.match(notional('alpaca', { symbol: 'AAPL', type: 'limit', qty: '0', limit_price: '5' }).error, /qty/);
  assert.match(notional('alpaca', { symbol: 'AAPL', type: 'limit', qty: '-1', limit_price: '5' }).error, /qty/);
  assert.match(notional('alpaca', { symbol: 'AAPL', type: 'limit', qty: '1', limit_price: '0' }).error, /Cannot price/);
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

// ------------------------------------------------------------------------- multi-leg (Sept 23)
// Found Sept 23, 2026: the option rules applied only when the TOP-LEVEL symbol was an option, so a
// multi-leg order with no top-level symbol was priced as a stock, qty x limit with no x100 and no
// long-premium check. These bodies are the ones that were measured.
const PUT = 'SPY261016P00600000';
const DEBIT_SPREAD = {
  order_class: 'mleg', qty: '1', type: 'limit', limit_price: '2.10', time_in_force: 'day',
  legs: [
    { symbol: CALL, ratio_qty: '1', side: 'buy', position_intent: 'buy_to_open' },
    { symbol: 'SPY261016C00745000', ratio_qty: '1', side: 'sell', position_intent: 'sell_to_open' },
  ],
};
const WRITTEN_PUT = {
  order_class: 'mleg', qty: '1', type: 'limit', limit_price: '0.25', time_in_force: 'day',
  legs: [{ symbol: PUT, ratio_qty: '1', side: 'sell', position_intent: 'sell_to_open' }],
};

test('a multi-leg order is never priced as a stock: the $210 spread and the written put are refused', () => {
  // On main these were metered at $2.10 and $0.25.
  for (const [name, body] of [['debit spread', DEBIT_SPREAD], ['written put', WRITTEN_PUT]]) {
    for (const extra of [{}, { symbol: 'SPY' }, { symbol: CALL }]) {
      const priced = notional('alpaca', { ...body, ...extra }, { reference: '500' });
      assert.match(priced.error ?? '', /Multi-leg/, `${name} ${JSON.stringify(extra)}`);
      assert.equal(priced.micro, undefined, `${name} ${JSON.stringify(extra)} was priced`);
    }
  }
  // Legs without an order_class, legs under "simple", an empty or non-array legs field, and an
  // order_class other than "simple" are all refused.
  const { order_class: _, ...legsAlone } = WRITTEN_PUT;
  for (const body of [legsAlone, { ...legsAlone, order_class: 'simple' }, { ...legsAlone, symbol: PUT, side: 'buy', position_intent: 'buy_to_open' }]) {
    assert.match(notional('alpaca', body).error ?? '', /Multi-leg/, JSON.stringify(body));
  }
  for (const legs of [[], {}, null, 'x']) {
    assert.match(notional('alpaca', { symbol: 'AAPL', qty: '1', limit_price: '1', legs }).error ?? '', /Multi-leg/, JSON.stringify(legs));
  }
  for (const orderClass of ['mleg', 'bracket', 'oco', 'oto', 'MLEG', '', null, 0]) {
    const body = { symbol: 'AAPL', qty: '1', side: 'buy', type: 'limit', limit_price: '1', order_class: orderClass };
    assert.match(notional('alpaca', body).error ?? '', /Multi-leg/, JSON.stringify(orderClass));
  }
});

test('a bracket, OCO or OTO order is refused: its child orders are not in the price', () => {
  const bracket = {
    symbol: 'AAPL', qty: '1', side: 'buy', type: 'limit', limit_price: '10', time_in_force: 'gtc',
    order_class: 'bracket', take_profit: { limit_price: '12' }, stop_loss: { stop_price: '9' },
  };
  assert.match(notional('alpaca', bracket).error ?? '', /Multi-leg, bracket/);
  // Child-order fields without an order_class are not fields this gateway prices either.
  const { order_class: _, ...bare } = bracket;
  assert.match(notional('alpaca', bare).error ?? '', /not one this gateway prices/);
});

test('an order field spelled any other way is refused, so a case-insensitive venue cannot read a leg this check never saw', () => {
  const stock = { symbol: 'AAPL', qty: '1', side: 'buy', type: 'limit', limit_price: '2.10', time_in_force: 'day' };
  for (const extra of [
    { Order_Class: 'mleg', LEGS: WRITTEN_PUT.legs },
    { ORDER_CLASS: 'mleg' },
    { 'leg\u017f': WRITTEN_PUT.legs },          // U+017F folds to "s" in Go's encoding/json
    { SYMBOL: PUT },                              // a second symbol the venue might read instead
    { Symbol: PUT },
    { 'position_intent ': 'sell_to_open' },
  ]) {
    const priced = notional('alpaca', { ...stock, ...extra });
    assert.match(priced.error ?? '', /not one this gateway prices/, JSON.stringify(extra));
    assert.equal(priced.micro, undefined);
  }
});

test('a body with no top-level symbol, or a symbol not in the venue spelling, is refused', () => {
  // On main a symbol-less limit order was priced as a stock at qty x limit.
  for (const symbol of [undefined, '', null, 123, ['SPY'], { s: 'SPY' }]) {
    const body = { qty: '1', side: 'buy', type: 'limit', limit_price: '60', ...(symbol === undefined ? {} : { symbol }) };
    const priced = notional('alpaca', body);
    assert.match(priced.error ?? '', /top-level symbol/, JSON.stringify(symbol));
    assert.equal(priced.micro, undefined);
  }
  // A lower-case or padded option symbol is not taken for a stock and priced without the x100.
  for (const symbol of ['spy261016p00600000', 'SPY   261016P00600000', ` ${PUT}`, `${PUT}\n`, 'aapl', 'BTC / USD']) {
    const body = { symbol, qty: '1', side: 'sell', type: 'limit', limit_price: '0.25', position_intent: 'sell_to_open', time_in_force: 'day' };
    const priced = notional('alpaca', body);
    assert.match(priced.error ?? '', /venue's own spelling/, JSON.stringify(symbol));
    assert.equal(priced.micro, undefined);
  }
  assert.match(notional('alpaca', []).error, /JSON object/);
});

test('ordinary stock, crypto and single-leg option orders are priced exactly as before', () => {
  // The bodies ltcm/adapters/alpaca.py sends: symbol, qty, side, type, time_in_force,
  // client_order_id, a limit price when there is one, and position_intent on an option.
  const house = extra => ({ qty: '1', side: 'buy', type: 'market', time_in_force: 'day', client_order_id: 'oi-7', ...extra });
  assert.equal(usd(notional('alpaca', house({ symbol: 'SPY', qty: '0.04' }), { reference: '660.00' }).micro), '26.40');
  assert.equal(usd(notional('alpaca', house({ symbol: 'IWM', qty: '3', type: 'limit', limit_price: '24.95' })).micro), '74.85');
  assert.equal(usd(notional('alpaca', house({ symbol: 'BRK.B', qty: '0.02', type: 'limit', limit_price: '480' })).micro), '9.60');
  assert.equal(usd(notional('alpaca', house({ symbol: 'LTC/USD', qty: '0.1923', type: 'limit', limit_price: '62.39', time_in_force: 'gtc' })).micro), '12.00');
  assert.equal(usd(notional('alpaca', house({ symbol: 'BTC/USD', qty: '0.00015', time_in_force: 'gtc' }), { reference: '64050.11' }).micro), '9.61');
  assert.equal(usd(notional('alpaca', house({ symbol: 'AAPL', notional: '25', qty: undefined })).micro), '25.00');
  assert.equal(usd(notional('alpaca', house({ symbol: 'AAPL', qty: '0.1', side: 'sell', extended_hours: false }), { reference: '230' }).micro), '23.00');
  const opt = extra => house({ symbol: 'RIVN261002P00014000', type: 'limit', limit_price: '0.14', position_intent: 'buy_to_open', ...extra });
  assert.equal(usd(notional('alpaca', opt()).micro), '14.00');
  assert.equal(usd(notional('alpaca', opt({ side: 'sell', position_intent: 'sell_to_close', limit_price: '0.20' })).micro), '20.00');
  assert.equal(usd(notional('alpaca', house({ symbol: 'SPY', qty: '0.04', order_class: 'simple' }), { reference: '660.00' }).micro), '26.40');
  // A single-leg option is still long premium only.
  assert.match(notional('alpaca', opt({ side: 'sell', position_intent: 'sell_to_open' })).error, /long premium only/);
});

test('"simple" is Alpaca\'s default order class, so naming it on a single-leg option changes nothing', () => {
  // Main refused any truthy order_class on an option; the one class that is a single order now
  // gets the single-leg option rules like an order that leaves the class out. The House sends none.
  const opt = extra => ({ symbol: 'RIVN261002P00014000', qty: '1', side: 'buy', type: 'limit', limit_price: '0.14', position_intent: 'buy_to_open', time_in_force: 'day', order_class: 'simple', ...extra });
  assert.equal(usd(notional('alpaca', opt()).micro), '14.00');
  assert.match(notional('alpaca', opt({ side: 'sell', position_intent: 'sell_to_open' })).error, /long premium only/);
});

// ------------------------------------------------------- review of the B0 fix (Sept 23, 2026)
// Each body below was forwarded by route() on the first B0 commit (and on main), metered far under
// what it can spend.

test('an adjusted option symbol is refused, never priced as a stock without the x100', () => {
  // Measured: a written put of 10 contracts at $5.00 (premium $5,000) was metered at $50.00.
  for (const symbol of ['TSLA1261016P00150000', 'XYZ1261016P00005000']) {
    for (const [side, intent] of [['sell', 'sell_to_open'], ['buy', 'buy_to_open'], ['sell', 'sell_to_close']]) {
      const body = { symbol, qty: '10', side, position_intent: intent, type: 'limit', limit_price: '5', time_in_force: 'day' };
      const priced = notional('alpaca', body);
      assert.match(priced.error ?? '', /standard OCC symbol/, `${symbol} ${intent}`);
      assert.equal(priced.micro, undefined, `${symbol} ${intent} was priced`);
      assert.match(alpacaShapeError(body) ?? '', /standard OCC symbol/);
    }
  }
  // Nor is anything else that is not a stock ticker, a crypto pair or a standard OCC symbol.
  for (const symbol of ['ABCDEFGHIJ1234567890', 'AAPLXY', 'AAPL1', 'BTC-USD', 'BTCUSD', 'A/B', 'SPY261016C0074000', '1INCH', 'BRK.BBB', 'BRK/B/C']) {
    const body = { symbol, qty: '10', side: 'buy', type: 'limit', limit_price: '5', time_in_force: 'day' };
    const priced = notional('alpaca', body);
    assert.match(priced.error ?? '', /venue's own spelling/, symbol);
    assert.equal(priced.micro, undefined, symbol);
  }
  // Every spelling the House sends still passes.
  for (const symbol of ['AAPL', 'F', 'GOOGL', 'BRK.B', 'BTC/USD', 'SHIB/USD', 'AAVE/USD', 'LTC/USD', 'RIVN261002P00014000', 'SPY261016C00740000']) {
    assert.equal(alpacaSymbolError(symbol), null, symbol);
  }
});

test('only market and limit orders are priced: stop, stop_limit and trailing_stop are refused', () => {
  // Measured: a buy stop at $0.01 was metered at $1.00 for 100 AAPL, and a trailing buy at 50%
  // (which cannot fill below 1.5 x the ask) at the ask.
  const aapl = { symbol: 'AAPL', side: 'buy', time_in_force: 'gtc' };
  for (const body of [
    { ...aapl, qty: '100', type: 'stop', stop_price: '0.01' },
    { ...aapl, qty: '100', type: 'stop_limit', stop_price: '0.01', limit_price: '0.01' },
    { ...aapl, qty: '0.29', type: 'trailing_stop', trail_percent: '50' },
    { ...aapl, qty: '0.29', type: 'trailing_stop', trail_price: '1000' },
    { ...aapl, qty: '1', limit_price: '5' },
    { ...aapl, qty: '1', type: 'LIMIT', limit_price: '5' },
    { ...aapl, qty: '1', type: ['limit'], limit_price: '5' },
  ]) {
    const priced = notional('alpaca', body, { reference: '230' });
    assert.match(priced.error ?? '', /Only market and limit orders/, JSON.stringify(body));
    assert.equal(priced.micro, undefined, JSON.stringify(body));
  }
  // A stop or trail field on a market or limit order is not a field this gateway prices.
  for (const extra of [{ stop_price: '0.01' }, { trail_price: '1' }, { trail_percent: '50' }]) {
    const priced = notional('alpaca', { ...aapl, qty: '1', type: 'limit', limit_price: '5', ...extra });
    assert.match(priced.error ?? '', /not one this gateway prices/, JSON.stringify(extra));
  }
  assert.ok(!ALPACA_ORDER_FIELDS.has('stop_price') && !ALPACA_ORDER_FIELDS.has('trail_price') && !ALPACA_ORDER_FIELDS.has('trail_percent'));
});

test('a market order is priced by the reference alone, and a limit order by a positive limit', () => {
  const market = { symbol: 'AAPL', qty: '100', side: 'buy', type: 'market', time_in_force: 'day' };
  // A market order with a price field: on main the router skipped the venue quote and this was $1.00.
  for (const limit_price of ['0.01', '0', 'x', 0]) {
    const priced = notional('alpaca', { ...market, limit_price }, { reference: '0.01' });
    assert.match(priced.error ?? '', /market order carries no limit_price/, JSON.stringify(limit_price));
    assert.equal(priced.micro, undefined);
  }
  // A limit order whose limit is not a positive price is not priced from the reference instead.
  for (const limit_price of [undefined, '0', 'x', '-1']) {
    const priced = notional('alpaca', { ...market, type: 'limit', limit_price }, { reference: '0.01' });
    assert.match(priced.error ?? '', /positive limit price/, JSON.stringify(limit_price));
    assert.equal(priced.micro, undefined);
  }
  // qty and notional are exclusive, and a notional is a positive dollar amount.
  assert.match(notional('alpaca', { ...market, notional: '0' }, { reference: '0.01' }).error ?? '', /not both/);
  assert.match(notional('alpaca', { ...market, notional: '5' }, { reference: '0.01' }).error ?? '', /not both/);
  const { qty: _, ...dollars } = market;
  assert.match(notional('alpaca', { ...dollars, notional: '0' }).error ?? '', /positive dollar/);
  assert.match(notional('alpaca', { ...dollars, notional: 'x' }).error ?? '', /positive dollar/);
  assert.equal(usd(notional('alpaca', { ...dollars, notional: '25' }).micro), '25.00');
  // The House's market order is priced from the reference the router read from the venue.
  assert.equal(usd(notional('alpaca', market, { reference: '253' }).micro), '25300.00');
});
