// What counts as an order, and what it is worth. A read or a cancel is never metered; only a call
// that can create an order is, and it is priced before it is forwarded, from the body the caller
// actually sent. A body this module cannot price is refused rather than passed through unpriced.

import { parsePico, centsToPico, mulPico, picoToMicro, parseUsdMicro, parseCount, PICO } from './money.mjs';

export const REFERENCE_HEADER = 'X-LTCM-Reference-Price';

/** The three paths that create an order, by venue. Everything else passes the caps untouched. */
export const ORDER_PATHS = {
  kalshi: ['portfolio/events/orders', 'portfolio/orders'],
  coinbase: ['api/v3/brokerage/orders'],
};

export const normalizePath = path => String(path || '').replace(/^\/+/, '').replace(/\/+$/, '');

/** True when `METHOD venue/path` is a call that can bring a new order into existence. */
export function createsOrder(venue, method, path) {
  if (String(method).toUpperCase() !== 'POST') return false;
  return (ORDER_PATHS[venue] || []).includes(normalizePath(path));
}

/** The caps in force, read from `vars`. A malformed value falls back to the documented default. */
export function caps(env = {}) {
  return {
    maxOrderMicro: parseUsdMicro(env.MAX_ORDER_USD, 50n * 1000000n),
    maxDayMicro: parseUsdMicro(env.MAX_DAY_USD, 400n * 1000000n),
    maxDayOrders: parseCount(env.MAX_DAY_ORDERS, 60),
    timezone: typeof env.CAP_TIMEZONE === 'string' && env.CAP_TIMEZONE ? env.CAP_TIMEZONE : 'America/New_York',
  };
}

/**
 * What one order is worth, in micro-dollars.
 * `{ micro }` when it can be priced, `{ error }` when it cannot -- which is a refusal, not a pass.
 */
export function notional(venue, body, { reference = null } = {}) {
  if (!body || typeof body !== 'object') return { error: 'An order body is required.' };
  return venue === 'kalshi' ? kalshiNotional(body) : coinbaseNotional(body, reference);
}

// Kalshi: count x price, in dollars. The v2 surface quotes decimal dollars (`price`); the legacy
// surface quotes integer cents (`yes_price` / `no_price`). A contract can never settle above
// $1.00, so a market order with no price of its own is worth at most its count in dollars.
function kalshiNotional(body) {
  const count = parsePico(body.count);
  if (count === null || count <= 0n) return { error: 'Order count is missing or not positive.' };
  let price = parsePico(body.price);
  if (price === null) price = centsToPico(body.yes_price);
  if (price === null) price = centsToPico(body.no_price);
  if (price === null) {
    const ceiling = centsToPico(body.buy_max_cost);
    if (ceiling !== null && ceiling > 0n) return { micro: picoToMicro(ceiling) };
    price = PICO; // an unpriced contract is capped at its $1.00 settlement value
  }
  if (price <= 0n) return { error: 'Order price is not positive.' };
  return { micro: picoToMicro(mulPico(count, price)) };
}

// Coinbase: a `quote_size` already is the dollar amount. A `base_size` is a quantity of the base
// asset, so it is priced with the reference the caller sends, falling back to its own limit price.
function coinbaseNotional(body, reference) {
  const configuration = body.order_configuration;
  if (!configuration || typeof configuration !== 'object') {
    return { error: 'Order configuration is missing.' };
  }
  const leg = Object.values(configuration).find(value => value && typeof value === 'object');
  if (!leg) return { error: 'Order configuration is empty.' };
  const quote = parsePico(leg.quote_size);
  if (quote !== null && quote > 0n) return { micro: picoToMicro(quote) };
  const size = parsePico(leg.base_size);
  if (size === null || size <= 0n) return { error: 'Order size is missing or not positive.' };
  let price = parsePico(reference);
  if (price === null || price <= 0n) price = parsePico(leg.limit_price);
  if (price === null || price <= 0n) {
    return { error: `Cannot price this order: send a ${REFERENCE_HEADER} header or a quote_size.` };
  }
  return { micro: picoToMicro(mulPico(size, price)) };
}
