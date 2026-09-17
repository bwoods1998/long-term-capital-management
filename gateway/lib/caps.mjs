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

// The only venue paths this gateway will sign. Everything the floor does is here; anything
// else, a batched order, a withdrawal, a key management call, is refused before signing, so
// a bug or a compromise on the box can at most do what the floor already does, inside the caps.
// The one funds move allowed is Kalshi's intra-account shard transfer: money between exchange
// shards of the owner's own account (crypto markets live on shard 2 and need collateral there),
// which cannot leave the account.
const SEGMENT = '[A-Za-z0-9._~%-]+';
export const VENUE_PATHS = {
  kalshi: [
    ['GET', /^portfolio\/(balance|positions|fills|settlements|deposits|withdrawals)$/],
    ['GET', /^portfolio\/orders(\/[A-Za-z0-9._~%-]+)?$/],
    ['GET', /^portfolio\/intra_exchange_instance_transfers?(\/[A-Za-z0-9._~%-]+)?$/],
    ['POST', /^portfolio\/intra_exchange_instance_transfer$/],
    ['GET', new RegExp(`^(markets|series|events)(\\/${SEGMENT}(\\/(orderbook|candlesticks|history|markets))?(\\/${SEGMENT})?)?$`)],
    ['GET', /^exchange\/(status|schedule)$/],
    ['POST', /^portfolio\/events\/orders$/],
    ['POST', /^portfolio\/orders$/],
    ['POST', /^account\/api_usage_level\/upgrade$/],
    ['DELETE', /^portfolio\/(events\/)?orders\/[A-Za-z0-9._~%-]+$/],
  ],
  coinbase: [
    // Funding reconciliation only; no deposit, withdrawal or transfer creation is exposed.
    ['GET', /^v2\/accounts(\/[A-Za-z0-9._~%-]+\/transactions)?$/],
    ['GET', /^api\/v3\/brokerage\/transaction_summary$/],
    ['GET', /^api\/v3\/brokerage\/accounts(\/[A-Za-z0-9._~%-]+)?$/],
    // Read-only derivatives state: whether the account can hold futures, and what it holds.
    ['GET', /^api\/v3\/brokerage\/cfm\/(balance_summary|positions(\/[A-Za-z0-9._~%-]+)?|intraday\/margin_setting)$/],
    ['GET', /^api\/v3\/brokerage\/best_bid_ask$/],
    ['GET', new RegExp(`^api\\/v3\\/brokerage\\/market\\/(products(\\/${SEGMENT}(\\/(candles|ticker))?)?|product_book)$`)],
    ['GET', /^api\/v3\/brokerage\/orders\/historical\/(fills|batch|[A-Za-z0-9._~%-]+)$/],
    ['POST', /^api\/v3\/brokerage\/orders$/],
    ['POST', /^api\/v3\/brokerage\/orders\/batch_cancel$/],
  ],
};

/** True when this gateway is willing to sign `method path` for `venue`. */
export function allowedVenuePath(venue, method, path) {
  const clean = normalizePath(path).split('?')[0];
  return (VENUE_PATHS[venue] || []).some(([m, pattern]) => m === method && pattern.test(clean));
}

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
export function notional(venue, body, { reference = null, contractSize = null } = {}) {
  if (!body || typeof body !== 'object') return { error: 'An order body is required.' };
  return venue === 'kalshi' ? kalshiNotional(body) : coinbaseNotional(body, reference, contractSize);
}

/** True for a Coinbase Financial Markets futures product id (`BIP-20DEC30-CDE`). */
export function isCoinbaseFuture(productId) {
  return /^[A-Z0-9]{1,12}-[0-9]{2}[A-Z]{3}[0-9]{2}-CDE$/.test(String(productId || '').toUpperCase());
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
// A CDE futures contract's `base_size` counts contracts, each `contractSize` of the underlying
// (nano BTC: 0.01), so the notional is size x contract size x price. The router reads the size
// from the venue's own product listing and refuses to price a future without it.
function coinbaseNotional(body, reference, contractSize = null) {
  const configuration = body.order_configuration;
  if (isCoinbaseFuture(body.product_id)) {
    const size = parsePico(contractSize);
    if (size === null || size <= 0n) return { error: 'Cannot price this futures order: the contract size is unknown.' };
  }
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
  const limit = parsePico(leg.limit_price);
  if (limit !== null && limit > 0n && (price === null || limit > price)) price = limit;
  if (price === null || price <= 0n) {
    return { error: `Cannot price this order: send a ${REFERENCE_HEADER} header or a quote_size.` };
  }
  let units = size;
  if (isCoinbaseFuture(body.product_id)) units = mulPico(size, parsePico(contractSize));
  return { micro: picoToMicro(mulPico(units, price)) };
}
