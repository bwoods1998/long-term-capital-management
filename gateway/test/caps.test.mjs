// What the gateway will meter, and what it thinks an order is worth.

import assert from 'node:assert/strict';
import test from 'node:test';

import { createsOrder, notional, caps, normalizePath, allowedVenuePath } from '../lib/caps.mjs';
import { formatUsd, parsePico, mulPico, picoToMicro } from '../lib/money.mjs';

const usd = micro => formatUsd(micro);

test('only the three order-creating calls are metered', () => {
  assert.equal(createsOrder('kalshi', 'POST', 'portfolio/events/orders'), true);
  assert.equal(createsOrder('kalshi', 'POST', '/portfolio/orders/'), true);
  assert.equal(createsOrder('coinbase', 'POST', 'api/v3/brokerage/orders'), true);
  // Reads and cancels always pass.
  assert.equal(createsOrder('kalshi', 'GET', 'portfolio/orders'), false);
  assert.equal(createsOrder('kalshi', 'DELETE', 'portfolio/events/orders/abc'), false);
  assert.equal(createsOrder('coinbase', 'POST', 'api/v3/brokerage/orders/batch_cancel'), false);
  assert.equal(createsOrder('coinbase', 'GET', 'api/v3/brokerage/accounts'), false);
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

test('coinbase prices base_size with the reference header the caller sends', () => {
  const body = { order_configuration: { market_market_ioc: { base_size: '0.00015' } } };
  assert.equal(usd(notional('coinbase', body, { reference: '64050.11' }).micro), '9.61');
  assert.match(notional('coinbase', body).error, /X-LTCM-Reference-Price/);
});

test('coinbase uses quote_size directly and falls back to a limit price', () => {
  assert.equal(usd(notional('coinbase', { order_configuration: { market_market_ioc: { quote_size: '25' } } }).micro), '25.00');
  assert.equal(
    usd(notional('coinbase', { order_configuration: { limit_limit_gtc: { base_size: '0.5', limit_price: '60' } } }).micro),
    '30.00',
  );
  // The header wins over the order's own limit price: it is the live market, not the desk's wish.
  assert.equal(
    usd(notional('coinbase', { order_configuration: { limit_limit_gtc: { base_size: '0.5', limit_price: '60' } } },
      { reference: '80' }).micro),
    '40.00',
  );
});

// Sept 17, 2026: a resting entry the venue should cancel at a stated time is sent as
// limit_limit_gtd with an end_time. The caps must price it exactly as the same order sent GTC.
test('coinbase prices a limit_limit_gtd order the same as the same order GTC', () => {
  const gtc = { order_configuration: { limit_limit_gtc: { base_size: '0.0003', limit_price: '76000', post_only: true } } };
  const gtd = {
    order_configuration: {
      limit_limit_gtd: { base_size: '0.0003', limit_price: '76000', end_time: '2026-09-17T01:20:00Z', post_only: true },
    },
  };
  assert.equal(usd(notional('coinbase', gtd).micro), '22.80');
  assert.equal(notional('coinbase', gtd).micro, notional('coinbase', gtc).micro);
  assert.equal(
    notional('coinbase', gtd, { reference: '75000' }).micro,
    notional('coinbase', gtc, { reference: '75000' }).micro,
  );
});

test('coinbase refuses a configuration it cannot read', () => {
  assert.match(notional('coinbase', {}).error, /configuration/);
  assert.match(notional('coinbase', { order_configuration: {} }).error, /empty/);
  assert.match(notional('coinbase', { order_configuration: { market_market_ioc: {} } }).error, /size/);
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

test('derivatives state is readable and never an order path', () => {
  assert.equal(allowedVenuePath('coinbase', 'GET', 'api/v3/brokerage/cfm/balance_summary'), true);
  assert.equal(allowedVenuePath('coinbase', 'GET', 'api/v3/brokerage/cfm/positions'), true);
  assert.equal(allowedVenuePath('coinbase', 'GET', 'api/v3/brokerage/cfm/positions/BIP-20DEC30-CDE'), true);
  assert.equal(allowedVenuePath('coinbase', 'POST', 'api/v3/brokerage/cfm/sweeps/schedule'), false);
  assert.equal(createsOrder('coinbase', 'GET', 'api/v3/brokerage/cfm/balance_summary'), false);
});

test('funding history is read-only and cannot move money', () => {
  for (const [venue, path] of [['kalshi', 'portfolio/deposits'], ['kalshi', 'portfolio/withdrawals'],
    ['coinbase', 'v2/accounts'], ['coinbase', 'v2/accounts/account-id/transactions']]) {
    assert.equal(allowedVenuePath(venue, 'GET', path), true);
    for (const method of ['POST', 'PUT', 'DELETE']) assert.equal(allowedVenuePath(venue, method, path), false);
    assert.equal(createsOrder(venue, 'GET', path), false);
  }
});
