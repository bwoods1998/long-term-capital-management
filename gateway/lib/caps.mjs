// What counts as an order, and what it is worth. A read or a cancel is never metered; only a call
// that can create an order is, and it is priced before it is forwarded, from the body the caller
// actually sent. A body this module cannot price is refused rather than passed through unpriced.

import { parsePico, centsToPico, mulPico, picoToMicro, parseUsdMicro, parseCount, PICO } from './money.mjs';

export const REFERENCE_HEADER = 'X-LTCM-Reference-Price';
// What the order is for. `exit` marks an order that closes or trims a position the floor holds;
// the dollar caps do not apply to it (Sept 18, 2026: two perp shorts sat past their stops for
// twenty minutes because the contract had grown past the per-order cap, and the day's cap was
// spent by the entries). The header is the floor's own claim, so a compromised VM could label an
// entry an exit: the order count cap still counts every order, and the owner accepts the risk.
export const PURPOSE_HEADER = 'X-LTCM-Purpose';

/** The paths that create an order, by venue. Everything else passes the caps untouched. */
export const ORDER_PATHS = {
  kalshi: ['portfolio/events/orders', 'portfolio/orders'],
  alpaca: ['v2/orders'],
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
  // Alpaca (Sept 19, 2026). Trading and market data share the credential and the allow-list;
  // the host follows the path. No transfers, no journals, no account configuration: the floor
  // reads its account, places and cancels orders, and reads quotes and bars.
  alpaca: [
    ['GET', /^v2\/account$/],
    ['GET', /^v2\/account\/activities$/],
    ['GET', /^v2\/account\/activities\/[A-Z_]{1,32}$/],
    ['GET', /^v2\/positions(\/[A-Za-z0-9._~%-]+)?$/],
    ['GET', /^v2\/orders(\/[A-Za-z0-9._~%-]+)?$/],
    ['GET', /^v2\/orders:by_client_order_id$/],
    ['GET', /^v2\/clock$/],
    ['GET', /^v2\/calendar$/],
    ['GET', /^v2\/assets(\/[A-Za-z0-9._~%-]+)?$/],
    ['POST', /^v2\/orders$/],
    ['DELETE', /^v2\/orders\/[A-Za-z0-9._~%-]+$/],
    // Market data, read only.
    ['GET', new RegExp(`^v2\\/stocks(\\/${SEGMENT})?\\/(quotes|trades|bars|snapshots?)(\\/latest)?$`)],
    ['GET', /^v2\/stocks\/snapshots$/],
    ['GET', /^v1beta3\/crypto\/[a-z]{2,4}\/(latest\/)?(quotes|trades|bars|snapshots)$/],
    // Listed options (Sept 19, 2026), read only: the contracts an underlying lists, and their
    // quotes, greeks and bars. Option ORDERS go through `v2/orders` like any other, under the
    // rules of `alpacaNotional` below (long premium only, a limit price, one leg).
    ['GET', /^v2\/options\/contracts(\/[A-Za-z0-9._~%-]+)?$/],
    ['GET', /^v1beta1\/options\/(quotes\/latest|trades\/latest|bars|snapshots)$/],
    // Historical option prints (Sept 22, 2026), read only: the options desk's replay history.
    // Alpaca has no historical option QUOTES endpoint, so there is nothing else to allow.
    ['GET', /^v1beta1\/options\/trades$/],
    ['GET', /^v1beta1\/options\/snapshots\/[A-Za-z0-9.]{1,12}$/],
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

/** A venue's own per-order cap (`MAX_ORDER_USD_ALPACA`), in micro-dollars, or null when unset. */
export function venueOrderCap(env = {}, venue) {
  if (typeof venue !== 'string' || !/^[a-z]{2,16}$/.test(venue)) return null;
  const raw = env[`MAX_ORDER_USD_${venue.toUpperCase()}`];
  if (raw === undefined || raw === null || raw === '') return null;
  const value = parseUsdMicro(raw, -1n);
  return value > 0n ? value : null;
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
export function notional(venue, body, { reference = null, exit = false } = {}) {
  if (!body || typeof body !== 'object') return { error: 'An order body is required.' };
  if (venue === 'kalshi') return kalshiNotional(body, exit);
  if (venue === 'alpaca') return alpacaNotional(body, reference);
  return { error: `Cannot price an order for an unknown venue: ${String(venue)}.` };
}

// Kalshi: count x price, in dollars. The v2 surface quotes decimal dollars (`price`); the legacy
// surface quotes integer cents (`yes_price` / `no_price`). A contract can never settle above
// $1.00, so a market order with no price of its own is worth at most its count in dollars.
//
// A v2 `price` is on the YES scale for BOTH legs, and `side` names the book side: "bid" buys YES
// (or sells NO), "ask" sells YES (or buys NO). Buying NO at $0.96 goes out as
// `side: "ask", price: "0.0400"` and costs $0.96 a contract. Metered on the wire's number it was
// counted at $0.04, so this independent cap let a NO buy through at up to 24 times its real
// principal (found Sept 22, 2026; the House's own book priced it right). The price is taken on
// the leg the order really trades: the complement for an entry on the ask and an exit on the bid.
function kalshiNotional(body, exit = false) {
  const count = parsePico(body.count);
  if (count === null || count <= 0n) return { error: 'Order count is missing or not positive.' };
  let price = parsePico(body.price);
  if (price !== null && price > 0n && price < PICO && (body.side === 'bid' || body.side === 'ask')
      && (body.side === 'ask') === !exit) {
    price = PICO - price;
  }
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

// Alpaca: `notional` is already the dollar amount. A `qty` is a quantity of the security, priced
// with its own limit price where there is one and otherwise with the reference the router reads
// from the venue's own quote -- never from the VM that is asking us to authorize the spend.
// A short sale is worth what it sells, so the sign of the position never enters the notional.
/** An OCC option symbol: root, YYMMDD, C or P, strike x 1000 in eight digits (`SPY261016C00740000`). */
export const isOptionSymbol = symbol => /^[A-Z]{1,6}[0-9]{6}[CP][0-9]{8}$/.test(String(symbol || ''));

//: One listed option contract is 100 shares: its premium is quoted per share and paid a hundredfold.
const OPTION_MULTIPLIER = 100n;

// An option order is held to four rules the venue would not enforce for us. It is one leg (a
// multi-leg order's worth cannot be read from one price). It carries its own limit price (there
// is no independent quote to price a market order with). It is sized in contracts, never in
// dollars. And it is LONG PREMIUM ONLY: it opens by buying and closes by selling, which Alpaca
// itself then enforces from `position_intent` (a sell_to_close with nothing to close is rejected),
// so no order through this gateway can write an option, and the most an option position can lose
// is what was paid for it. Measured Sept 19, 2026: before this rule an option order was priced
// at qty x limit with no multiplier, a hundredth of what it spends.
function optionNotional(body) {
  if (body.order_class || Array.isArray(body.legs)) return { error: 'Multi-leg option orders are not allowed through this gateway.' };
  if (parsePico(body.notional) !== null) return { error: 'An option order is sized in contracts, not dollars.' };
  const intent = String(body.position_intent || '');
  const side = String(body.side || '');
  if (!((side === 'buy' && intent === 'buy_to_open') || (side === 'sell' && intent === 'sell_to_close'))) {
    return { error: 'An option order must be buy with position_intent buy_to_open, or sell with sell_to_close: long premium only.' };
  }
  if (String(body.type || '') !== 'limit') return { error: 'An option order must be a limit order.' };
  const qty = parsePico(body.qty);
  if (qty === null || qty <= 0n || qty % PICO !== 0n) return { error: 'Option qty must be a whole number of contracts.' };
  const limit = parsePico(body.limit_price);
  if (limit === null || limit <= 0n) return { error: 'An option order needs a positive limit price.' };
  return { micro: picoToMicro(mulPico(qty, limit) * OPTION_MULTIPLIER) };
}

function alpacaNotional(body, reference) {
  if (isOptionSymbol(body.symbol)) return optionNotional(body);
  const dollars = parsePico(body.notional);
  if (dollars !== null && dollars > 0n) return { micro: picoToMicro(dollars) };
  const qty = parsePico(body.qty);
  if (qty === null || qty <= 0n) return { error: 'Order qty is missing or not positive.' };
  const limit = parsePico(body.limit_price);
  const stop = parsePico(body.stop_price);
  let price = parsePico(reference);
  for (const own of [limit, stop]) {
    // The dearest of the caller's own prices and the venue's: an order can fill at its limit.
    if (own !== null && own > 0n && (price === null || own > price)) price = own;
  }
  if (price === null || price <= 0n) {
    return { error: `Cannot price this order: send a ${REFERENCE_HEADER} header, a limit price or a notional.` };
  }
  return { micro: picoToMicro(mulPico(qty, price)) };
}
