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
 * `structures` is the list of structure types the real Alpaca account admits
 * (`admittedStructures(env)`); with none, a multi-leg order is refused as it always was. A priced
 * structure answers `{ micro, structure, opening }`: an open at its maximum loss, a close at zero.
 */
export function notional(venue, body, { reference = null, exit = false, structures = [] } = {}) {
  if (!body || typeof body !== 'object') return { error: 'An order body is required.' };
  if (venue === 'kalshi') return kalshiNotional(body, exit);
  if (venue === 'alpaca') {
    return structures.length > 0 && isMultiLegOrder(body) ? structureNotional(body, structures) : alpacaNotional(body, reference);
  }
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

// Alpaca: `notional` is already the dollar amount. A `qty` is a quantity of the security. A limit
// order is priced at its own limit price (a reference can raise that, never lower it); a market
// order is priced only with the reference the router reads from the venue's own quote -- never
// from the VM that is asking us to authorize the spend. A short sale is worth what it sells, so
// the sign of the position never enters the notional.
/** An OCC option symbol: root, YYMMDD, C or P, strike x 1000 in eight digits (`SPY261016C00740000`). */
export const isOptionSymbol = symbol => /^[A-Z]{1,6}[0-9]{6}[CP][0-9]{8}$/.test(String(symbol || ''));

//: One listed option contract is 100 shares: its premium is quoted per share and paid a hundredfold.
const OPTION_MULTIPLIER = 100n;

// An option order is held to four rules the venue would not enforce for us. It is one leg (a
// multi-leg order's worth cannot be read from one price; `alpacaShapeError` refuses one before
// this is reached). It carries its own limit price (there is no independent quote to price a
// market order with). It is sized in contracts, never in dollars. And it is LONG PREMIUM ONLY: it
// opens by buying and closes by selling, which Alpaca itself then enforces from `position_intent`
// (a sell_to_close with nothing to close is rejected), so no order through this gateway can write
// an option, and the most an option position can lose is what was paid for it. Measured Sept 19,
// 2026: before this rule an option order was priced at qty x limit with no multiplier, a
// hundredth of what it spends.
function optionNotional(body) {
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

// The only Alpaca order this gateway prices is one instrument named by a top-level `symbol`.
// Found Sept 23, 2026: the option rules above applied only when the TOP-LEVEL symbol was an option
// symbol, so a multi-leg order (`order_class: "mleg"` with a `legs` array and no top-level symbol)
// fell through to the stock path and was priced at qty x limit, with no x100 and no long-premium
// check: a $210 debit spread was metered at $2.10 and a written put at $0.25, so a spread of about
// $7,500 fit under the $75 order cap. The House never builds such an order; the gateway is the
// boundary that must hold if the House does not. So the shape is checked before anything reads
// the symbol, here and in the router before it looks up a quote:
//   - no `order_class` other than "simple" (mleg, bracket, oco and oto all add orders or legs that
//     one price cannot meter) and no `legs` field of any kind;
//   - a `type` of "market" or "limit", the two the House sends (`ltcm/broker.py` ORDER_TYPES). A
//     stop, stop_limit or trailing_stop order fills at market once it triggers, and a trailing buy
//     triggers only after the price has risen, so nothing in its body bounds what it spends: a
//     trailing buy at 50% was metered at the ask and could not fill below one and a half times it.
//     A market order carries no `limit_price` (the venue ignores it, so it prices nothing), and a
//     limit order carries a positive one, checked where it is priced;
//   - only the fields listed below, spelled exactly so. A venue whose JSON decoder matches keys
//     case-insensitively (Go's does, and folds U+017F to "s" and U+212A to "k") would read
//     `Order_Class`, `LEGS` or a second `SYMBOL` that this check never saw;
//   - a top-level `symbol` spelled as exactly one of the three instruments the gateway prices: a
//     stock ticker, a crypto pair or a STANDARD OCC option symbol. An adjusted contract's OCC
//     symbol has a digit in its root (`XYZ1261016P00005000`) and may deliver other than 100
//     shares; spelled any looser way it was taken for a stock and a written put worth $5,000 was
//     metered at $50.00, so it is refused rather than priced;
//   - `qty` or `notional`, never both, checked where it is priced.
// Paper orders are never metered and never reach this check.
export const ALPACA_ORDER_FIELDS = new Set([
  'symbol', 'qty', 'notional', 'side', 'type', 'time_in_force', 'limit_price',
  'extended_hours', 'client_order_id', 'order_class', 'position_intent',
]);
//: The order types this gateway prices. Everything else is refused before a quote is read.
export const ALPACA_ORDER_TYPES = new Set(['market', 'limit']);
//: A US stock ticker, with an optional share class (`BRK.B`).
const STOCK_SYMBOL = /^[A-Z]{1,5}(\.[A-Z]{1,2})?$/;
//: A crypto pair in the venue's spelling (`BTC/USD`).
const CRYPTO_PAIR = /^[A-Z]{2,10}\/[A-Z]{3,4}$/;
//: What makes a symbol an option contract to the venue, whatever its root: YYMMDD, C or P, strike.
const OCC_TAIL = /[0-9]{6}[CP][0-9]{8}$/;

const present = (body, key) => body[key] !== undefined && body[key] !== null;

/** Why this gateway will not price an Alpaca order symbol, or null when it names one it prices. */
export function alpacaSymbolError(symbol) {
  if (typeof symbol !== 'string' || symbol === '') return 'An Alpaca order needs a top-level symbol.';
  if (isOptionSymbol(symbol) || STOCK_SYMBOL.test(symbol) || CRYPTO_PAIR.test(symbol)) return null;
  if (OCC_TAIL.test(symbol)) {
    return 'An Alpaca order symbol must be in the venue\'s own spelling, and an option must be a standard OCC symbol (a root of one to six capital letters, YYMMDD, C or P, an eight-digit strike): an adjusted contract is not priced here.';
  }
  return 'An Alpaca order symbol must be in the venue\'s own spelling: a stock ticker (AAPL, BRK.B), a crypto pair (BTC/USD) or a standard OCC option symbol.';
}

/** Why this gateway will not price an Alpaca order body, or null when its shape is one it prices. */
export function alpacaShapeError(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return 'An order body must be a JSON object.';
  const has = key => Object.prototype.hasOwnProperty.call(body, key);
  if ((has('order_class') && body.order_class !== 'simple') || has('legs')) {
    return 'Multi-leg, bracket, OCO and OTO orders (an order_class other than "simple", or legs) are not allowed through this gateway.';
  }
  if (typeof body.type !== 'string' || !ALPACA_ORDER_TYPES.has(body.type)) {
    return 'Only market and limit orders pass this gateway: a stop, stop_limit or trailing_stop order fills at market once it triggers, so nothing in it bounds what it spends.';
  }
  const unknown = Object.keys(body).find(key => !ALPACA_ORDER_FIELDS.has(key));
  if (unknown !== undefined) return `Order field ${JSON.stringify(unknown.slice(0, 40))} is not one this gateway prices.`;
  const symbol = alpacaSymbolError(body.symbol);
  if (symbol) return symbol;
  if (body.type === 'market' && present(body, 'limit_price')) {
    return 'A market order carries no limit_price: the venue does not hold it to one, so it cannot price the order.';
  }
  return null;
}

function alpacaNotional(body, reference) {
  const shape = alpacaShapeError(body);
  if (shape) return { error: shape };
  if (isOptionSymbol(body.symbol)) return optionNotional(body);
  if (present(body, 'qty') && present(body, 'notional')) return { error: 'An Alpaca order carries qty or notional, not both.' };
  if (present(body, 'notional')) {
    const dollars = parsePico(body.notional);
    if (dollars === null || dollars <= 0n) return { error: 'Order notional is not a positive dollar amount.' };
    return { micro: picoToMicro(dollars) };
  }
  const qty = parsePico(body.qty);
  if (qty === null || qty <= 0n) return { error: 'Order qty is missing or not positive.' };
  const ref = parsePico(reference);
  let price;
  if (body.type === 'limit') {
    price = parsePico(body.limit_price);
    if (price === null || price <= 0n) return { error: 'Cannot price this limit order: it needs a positive limit price.' };
    // The dearer of the order's own limit and a reference: a reference can raise it, never lower it.
    if (ref !== null && ref > price) price = ref;
  } else {
    // A market order: only the router's reference, read from the venue's own quote.
    price = ref;
    if (price === null || price <= 0n) return { error: 'Cannot price this market order: the gateway has no venue quote for it.' };
  }
  return { micro: picoToMicro(mulPico(qty, price)) };
}

// ------------------------------------------------------------ multi-leg structures (Sept 25, 2026)
// The options-desk run (`docs/goals/LTCM_OPTIONS_DESK.md`, amended by the owner at 06:01Z in
// `docs/runs/2026-09-25-options-desk.md`): the Alpaca PRACTICE account (`alpaca-paper`, options level
// 3, a margin account) may trade every level-3 DEFINED-RISK structure; the REAL account may trade only
// the types `OPTION_STRUCTURES_REAL` names, none by default, metered at maximum loss. Naked short legs,
// a ratio with an uncovered leg, and legging in or out are refused on both. `league/structures.py` is
// the House's implementation of the structure spec; this is the gateway's own reading of the same
// rules from the order the venue will actually receive, because the gateway is the boundary that must
// hold if the House does not. It is told no type: it finds the one type the legs form, or refuses.
//
// Alpaca's multi-leg order (https://docs.alpaca.markets/docs/options-level-3-trading, read Sept 25,
// 2026): `order_class: "mleg"`, `qty` (whole structures), `type`, `limit_price`, `time_in_force` and
// `legs` (the orders reference says "<= 4"), each `{symbol, ratio_qty, side, position_intent}`; no
// top-level `symbol` or `side` ("required for all order classes except for mleg"); leg ratios in
// lowest terms (GCD 1). The venue itself accepts an mleg order "only if all its legs are covered
// within the same MLeg order", but what it calls covered is its own margin rule, not the spec's types.
//
// THE SIGN OF `limit_price`. The orders reference (https://docs.alpaca.markets/reference/postorder,
// `limit_price`, read Sept 25, 2026): "In case of `mleg`, the limit_price parameter is expressed with
// the following notation: - A positive value indicates a debit, representing a cost or payment to be
// made. - A negative value signifies a credit, reflecting an amount to be received." alpaca-py's
// reference says the same (https://alpaca.markets/sdks/python/api_reference/trading/requests.html,
// `LimitOrderRequest.limit_price`), and a third party measured it live on Sept 17, 2026: a credit
// spread sent with a positive limit was taken as a debit
// (https://github.com/coleashcrafttrading-commits/tickaverager/pull/4). The level-3 guide's own
// iron-condor example sends "1.80", positive, for a short condor: it contradicts the reference and
// is not followed. So a debit is positive and a credit negative, and a limit whose sign disagrees with
// what the legs do is refused, never re-read: opening a credit structure at a positive limit would PAY
// to sell it (a loss of up to its collateral plus that debit), and closing a debit structure at one
// would pay to give it away. Zero says neither, and is refused.

//: The spec's types (`league/structures.py` DEBIT_TYPES and CREDIT_TYPES): every one has a loss
//: bounded by what it costs to hold.
export const DEBIT_STRUCTURES = ['debit_vertical', 'long_butterfly', 'calendar', 'diagonal', 'long_straddle', 'long_strangle'];
export const CREDIT_STRUCTURES = ['credit_vertical', 'iron_condor', 'iron_butterfly'];
export const STRUCTURE_TYPES = [...DEBIT_STRUCTURES, ...CREDIT_STRUCTURES];
//: The fields of a multi-leg order and of one leg, spelled exactly so (see ALPACA_ORDER_FIELDS on why).
export const STRUCTURE_ORDER_FIELDS = new Set(['order_class', 'qty', 'type', 'limit_price', 'time_in_force', 'legs', 'client_order_id']);
export const STRUCTURE_LEG_FIELDS = new Set(['symbol', 'ratio_qty', 'side', 'position_intent']);
//: A standard OCC symbol in parts: root, YYMMDD, C or P, the strike in thousandths of a dollar.
const OCC_PARTS = /^([A-Z]{1,6})([0-9]{6})([CP])([0-9]{8})$/;
//: A strike's thousandths as picodollars.
const PICO_PER_MILLI = 10n ** 9n;
//: What a leg's position_intent makes it: its side, long (+1) or short (-1) in the structure, and
//: whether it opens. A close names the structure's legs by what they were: selling to close a long
//: leg, buying to close a short one.
const LEG_INTENTS = {
  buy_to_open: { side: 'buy', sign: 1, opening: true },
  sell_to_open: { side: 'sell', sign: -1, opening: true },
  sell_to_close: { side: 'sell', sign: 1, opening: false },
  buy_to_close: { side: 'buy', sign: -1, opening: false },
};

export const NAKED_SHORT = 'A short leg with no long leg of its right covering it is a naked short: refused.';
export const UNCOVERED_RATIO = 'A ratio_qty other than a long butterfly\'s body of 2 leaves a leg uncovered: refused.';

/** True when an Alpaca body is a multi-leg order: it carries `legs`, or names the `mleg` class. */
export function isMultiLegOrder(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return false;
  return Object.prototype.hasOwnProperty.call(body, 'legs') || body.order_class === 'mleg';
}

/**
 * The structure types the real account admits, from `OPTION_STRUCTURES_REAL` ("off" by default in
 * `wrangler.jsonc`): a comma- or space-separated list of the spec's type names. A name that is not
 * a type admits nothing at all, so a typo can only ever close the route, never open more of it.
 */
export function admittedStructures(env = {}) {
  const raw = String(env.OPTION_STRUCTURES_REAL ?? '').trim();
  if (!raw || raw.toLowerCase() === 'off') return [];
  const names = raw.split(/[\s,]+/).filter(Boolean);
  if (names.some(name => !STRUCTURE_TYPES.includes(name))) return [];
  return [...new Set(names)];
}

const byCanonical = (a, b) => (a.expiry !== b.expiry ? (a.expiry < b.expiry ? -1 : 1)
  : a.right !== b.right ? (a.right < b.right ? -1 : 1)
    : a.strike !== b.strike ? (a.strike < b.strike ? -1 : 1)
      : a.sign - b.sign);

/**
 * The one spec type a set of legs forms, or why it forms none. Each leg is `{expiry: "YYMMDD",
 * right: "C"|"P", strike: <thousandths, BigInt>, sign: 1|-1, ratio: 1|2}` on one root, no contract
 * twice. The types are mutually exclusive, so the legs name at most one; the rules are
 * `league/structures.py` `classify`, read without being told the type. Answers `{type, collateral,
 * maxValue}` (picodollars a share; `maxValue` null where the value is unbounded) or `{error}`.
 */
export function classifyStructure(input) {
  if (!Array.isArray(input) || input.length < 2 || input.length > 4) return { error: 'A multi-leg order has two to four legs.' };
  const legs = [...input].sort(byCanonical);
  const longs = legs.filter(leg => leg.sign > 0);
  const shorts = legs.filter(leg => leg.sign < 0);
  if (shorts.some(short => !longs.some(long => long.right === short.right))) return { error: NAKED_SHORT };
  if (legs.some(leg => leg.ratio !== 1) && legs.length !== 3) return { error: UNCOVERED_RATIO };
  const expiries = new Set(legs.map(leg => leg.expiry));
  const rights = new Set(legs.map(leg => leg.right));
  const milli = value => value * PICO_PER_MILLI;
  const debit = type => ({ type, collateral: 0n, maxValue: null });

  if (legs.length === 2 && shorts.length === 0) {
    if (rights.size !== 2 || expiries.size !== 1) {
      return { error: 'Two long legs are a structure only as a long straddle or strangle, a call and a put of one expiry: refused.' };
    }
    return debit(legs[0].strike === legs[1].strike ? 'long_straddle' : 'long_strangle');
  }
  if (legs.length === 2) {
    // One long and one short of one right: the naked check above saw to the right.
    const [long] = longs;
    const [short] = shorts;
    const width = long.strike > short.strike ? long.strike - short.strike : short.strike - long.strike;
    if (long.expiry === short.expiry) {
      const longDearer = long.right === 'C' ? long.strike < short.strike : long.strike > short.strike;
      return longDearer
        ? { type: 'debit_vertical', collateral: 0n, maxValue: milli(width) }
        : { type: 'credit_vertical', collateral: milli(width), maxValue: milli(width) };
    }
    if (short.expiry > long.expiry) {
      return { error: 'A short leg that expires after the long leg covering it is naked once the long leg expires: refused.' };
    }
    if (long.strike === short.strike) return debit('calendar');
    const favourable = long.right === 'C' ? long.strike < short.strike : long.strike > short.strike;
    if (!favourable) {
      return { error: 'A diagonal whose long leg\'s strike is less favourable than its short leg\'s (a higher call, a lower put) can lose more than its debit: refused.' };
    }
    return debit('diagonal');
  }
  if (legs.length === 3) {
    const [low, mid, high] = legs; // one expiry and right: canonical order is by strike
    const shape = expiries.size === 1 && rights.size === 1
      && low.sign === 1 && low.ratio === 1 && mid.sign === -1 && mid.ratio === 2 && high.sign === 1 && high.ratio === 1;
    if (!shape && legs.some(leg => leg.ratio !== 1)) return { error: UNCOVERED_RATIO };
    if (!shape) {
      return { error: 'Three legs are a structure only as a long butterfly: one right and one expiry, long one low, short two middle (ratio_qty 2), long one high. Refused.' };
    }
    if (mid.strike - low.strike !== high.strike - mid.strike) {
      return { error: 'A broken-wing butterfly (unequal wings) can lose more than its debit: refused.' };
    }
    return { type: 'long_butterfly', collateral: 0n, maxValue: milli(mid.strike - low.strike) };
  }
  // Four legs: an iron condor or an iron butterfly, or nothing.
  const one = (right, sign) => legs.filter(leg => leg.right === right && leg.sign === sign);
  const [lp, sp, sc, lc] = [one('P', 1), one('P', -1), one('C', -1), one('C', 1)];
  const iron = expiries.size === 1 && [lp, sp, sc, lc].every(group => group.length === 1)
    && lp[0].strike < sp[0].strike && sc[0].strike < lc[0].strike && sp[0].strike <= sc[0].strike;
  if (!iron) {
    return { error: 'Four legs are a structure only as an iron condor or iron butterfly of one expiry: a long put below a short put, a short call below a long call, the short put at or below the short call. Refused.' };
  }
  const putWing = sp[0].strike - lp[0].strike;
  const callWing = lc[0].strike - sc[0].strike;
  const collateral = milli(putWing > callWing ? putWing : callWing);
  return { type: sp[0].strike === sc[0].strike ? 'iron_butterfly' : 'iron_condor', collateral, maxValue: collateral };
}

//: A type with its article, for a refusal that reads as a sentence.
const named = type => `${/^[aeiou]/.test(type) ? 'an' : 'a'} ${type}`;

const dollars = pico => {
  const cents = (pico < 0n ? -pico : pico) / (PICO / 100n);
  return `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
};

/**
 * A multi-leg order read as ONE defined-risk structure, or why it is not one.
 * Answers `{type, opening, collateral, limit, qty, maxLossMicro}` (picodollars a share, the signed
 * limit in Alpaca's convention, whole structures in picounits, and what an open can lose in all,
 * zero for a close), or `{error}`. Every rule here holds on the practice account and the real one.
 */
export function structureOrder(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { error: 'An order body must be a JSON object.' };
  const has = key => Object.prototype.hasOwnProperty.call(body, key);
  if (body.order_class !== 'mleg') return { error: 'An order with legs is a multi-leg order: order_class "mleg".' };
  if (has('symbol')) return { error: 'A multi-leg order has no top-level symbol: its legs name the contracts.' };
  const unknown = Object.keys(body).find(key => !STRUCTURE_ORDER_FIELDS.has(key));
  if (unknown !== undefined) {
    return { error: `Multi-leg order field ${JSON.stringify(unknown.slice(0, 40))} is not one this gateway reads: a multi-leg order is order_class, qty, type, limit_price, time_in_force, legs and client_order_id.` };
  }
  if (body.type !== 'limit') return { error: 'A multi-leg order is a limit order: a structure has no touch to take.' };
  if (body.time_in_force !== 'day') return { error: 'A multi-leg option order is a day order (time_in_force "day").' };
  const qty = parsePico(body.qty);
  if (qty === null || qty <= 0n || qty % PICO !== 0n) return { error: 'A multi-leg order\'s qty is a whole number of structures, at least one.' };
  const limit = parsePico(body.limit_price);
  if (limit === null) return { error: 'A multi-leg order needs a limit_price: its net a share, a debit positive and a credit negative (Alpaca\'s convention).' };
  if (!Array.isArray(body.legs) || body.legs.length < 2 || body.legs.length > 4) return { error: 'A multi-leg order has two to four legs.' };
  const legs = [];
  for (const raw of body.legs) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return { error: 'A leg is an object: symbol, ratio_qty, side and position_intent.' };
    const extra = Object.keys(raw).find(key => !STRUCTURE_LEG_FIELDS.has(key));
    if (extra !== undefined) {
      return { error: `Leg field ${JSON.stringify(extra.slice(0, 40))} is not one this gateway reads: a leg is symbol, ratio_qty, side and position_intent.` };
    }
    const parts = OCC_PARTS.exec(typeof raw.symbol === 'string' ? raw.symbol : '');
    if (!parts) {
      return { error: 'A leg names a standard OCC option symbol (a root of one to six capital letters, YYMMDD, C or P, an eight-digit strike): an adjusted contract is not read here.' };
    }
    const ratio = parsePico(raw.ratio_qty);
    if (ratio !== PICO && ratio !== 2n * PICO) return { error: 'A leg\'s ratio_qty is 1, or 2 for a long butterfly\'s body.' };
    const intent = Object.prototype.hasOwnProperty.call(LEG_INTENTS, raw.position_intent) ? LEG_INTENTS[raw.position_intent] : null;
    if (!intent) return { error: 'A leg names its position_intent: buy_to_open, sell_to_open, sell_to_close or buy_to_close.' };
    if (raw.side !== intent.side) return { error: `A ${raw.position_intent} leg is a ${intent.side}: its side says otherwise.` };
    legs.push({ symbol: parts[0], root: parts[1], expiry: parts[2], right: parts[3], strike: BigInt(parts[4]),
      sign: intent.sign, ratio: ratio === PICO ? 1 : 2, opening: intent.opening });
  }
  if (new Set(legs.map(leg => leg.root)).size !== 1) return { error: 'Every leg of a structure is on one underlying (one OCC root).' };
  if (new Set(legs.map(leg => leg.symbol)).size !== legs.length) return { error: 'A contract appears twice in one order.' };
  const opening = legs[0].opening;
  if (legs.some(leg => leg.opening !== opening)) {
    return { error: 'An order that opens some legs and closes others is legging in or out, or a roll: refused. A structure opens whole (every leg *_to_open) and closes whole (every leg *_to_close).' };
  }
  const shape = classifyStructure(legs);
  if (shape.error) return { error: shape.error };
  const { type, collateral, maxValue } = shape;
  const credit = CREDIT_STRUCTURES.includes(type);
  // Zero says neither debit nor credit. A close at zero can only give a worthless structure away (or
  // buy one back for nothing), which the expiry-day close of a structure bid at zero must be able to
  // send; an open at zero is refused, as `structures.held_limit` refuses it.
  if (limit === 0n && opening) {
    return { error: 'A structure is not opened at a net of zero: Alpaca\'s multi-leg limit_price is a debit positive and a credit negative, and zero says neither.' };
  }
  // Opening a debit structure or buying back a credit one pays (positive); the other two take in (negative).
  const pays = credit !== opening;
  if (limit !== 0n && (limit > 0n) !== pays) {
    const doing = opening ? `Opening ${named(type)} ${pays ? 'pays a debit' : 'takes in a credit'}`
      : `Closing ${named(type)} ${pays ? 'buys it back for a debit' : 'sells it for a credit'}`;
    return { error: `${doing}, which Alpaca's multi-leg limit_price writes as a ${pays ? 'positive' : 'negative'} number (a debit positive, a credit negative): a ${pays ? 'negative' : 'positive'} limit_price on it is the wrong sign, refused.` };
  }
  const magnitude = limit < 0n ? -limit : limit;
  if (credit && magnitude >= collateral) {
    return { error: `${opening ? 'A credit' : 'A buy-back'} of ${dollars(magnitude)} on ${named(type)} with ${dollars(collateral)} of collateral is not a defined-risk order: refused.` };
  }
  if (!credit && opening && maxValue !== null && magnitude >= maxValue) {
    return { error: `A debit of ${dollars(magnitude)} on ${named(type)} worth at most ${dollars(maxValue)} can never pay: refused.` };
  }
  // Maximum loss a share: the collateral plus the signed limit (a debit adds, a credit takes off).
  const perShare = credit ? collateral - magnitude : magnitude;
  const maxLossMicro = opening ? picoToMicro(mulPico(qty, perShare) * OPTION_MULTIPLIER) : 0n;
  return { type, opening, collateral, limit, qty, maxLossMicro };
}

/**
 * A multi-leg order on the REAL account, priced: an open at its maximum loss (a debit type
 * `limit x 100 x qty`, a credit type `(K - credit) x 100 x qty`), a close at zero; a type the account
 * does not admit is refused.
 */
export function structureNotional(body, admitted = []) {
  const read = structureOrder(body);
  if (read.error) return { error: read.error };
  if (!admitted.includes(read.type)) {
    return { error: `${named(read.type).replace(/^a/, 'A')} is not admitted on the real account: OPTION_STRUCTURES_REAL admits ${admitted.length ? admitted.join(', ') : 'none'}.` };
  }
  return { micro: read.maxLossMicro, structure: read.type, opening: read.opening };
}

// --- a real close holds its legs (Sept 25, 2026) --------------------------------------------------
// The review of the multi-leg route (MINOR 1, needed before the real switch): a real structure CLOSE takes risk off, so it
// is reserved as an exit at one micro-dollar, and it used to trust Alpaca to refuse closing legs the account does not hold.
// A sell_to_close of a contract not held long, or a buy_to_close of one not held short, is a new position under another
// name; the gateway is the boundary that must hold if the venue or the House does not. So before a real close is reserved,
// the account's positions (a signed GET v2/positions, read at most every few seconds) must hold every leg: a long leg long
// and a short leg short, at least the order's structures x the leg's ratio_qty contracts each. The practice account is
// unchanged: nothing is metered there, and the venue's own margin rules judge it.

/**
 * Why a multi-leg CLOSE may not go to the real account given its `positions` (Alpaca's `GET v2/positions` rows:
 * `{symbol, qty, side}`, a short option reported with side "short" and a negative qty), or null when every leg is held.
 * `body` has already passed `structureOrder` as a close.
 */
export function closeLegsHeldError(body, positions) {
  if (!Array.isArray(positions)) return 'The account\'s positions could not be read as a list: a real close is not admitted unread.';
  const qty = parsePico(body.qty);
  const held = new Map();
  for (const row of positions) {
    if (!row || typeof row !== 'object' || typeof row.symbol !== 'string') continue;
    const amount = parsePico(row.qty);
    if (amount === null || amount === 0n) continue;
    const sign = row.side === 'short' ? -1n : row.side === 'long' ? 1n : (amount < 0n ? -1n : 1n);
    if ((row.side === 'short' || row.side === 'long') && (amount < 0n) !== (sign < 0n)) continue;  // a row that contradicts itself holds nothing
    const magnitude = amount < 0n ? -amount : amount;
    held.set(row.symbol, (held.get(row.symbol) ?? 0n) + sign * magnitude);
  }
  const short = [];
  for (const raw of body.legs) {
    const intent = LEG_INTENTS[raw.position_intent];
    const need = qty * (parsePico(raw.ratio_qty) / PICO);
    const have = held.get(raw.symbol) ?? 0n;
    const enough = intent.sign > 0 ? have >= need : -have >= need;
    if (!enough) {
      const count = value => (value < 0n ? -value : value) / PICO;
      short.push(`${raw.symbol} ${intent.sign > 0 ? 'long' : 'short'} (${count(need)} needed, ${have === 0n ? 'none' : `${count(have)} ${have > 0n ? 'long' : 'short'}`} held)`);
    }
  }
  if (short.length === 0) return null;
  return `A structure close must close legs the real account holds: ${short.join('; ')}. A close of a leg not held would open a position: refused.`;
}

// --- the practice account ------------------------------------------------------------------------
// `alpaca-paper` is never metered (no money is behind it), but since Sept 25, 2026 its OPTION orders
// are held to the same defined-risk shapes: until then an order to the practice account was signed
// and forwarded with no check at all, so it would have taken a naked short or a ratio spread. What is
// not an option -- the House's stock and crypto orders -- passes exactly as before.

//: The fields the practice check decides on. A venue that matches keys case-insensitively would
//: read `Legs` or `SYMBOL` as one of these, so any other spelling of them is refused.
const PRACTICE_DECIDING_FIELDS = new Set(['symbol', 'legs', 'order_class', 'position_intent', 'side']);
//: Go's encoding/json folds ASCII case, and U+017F to "s" and U+212A to "k" (toLowerCase does that one).
const foldKey = key => key.toLowerCase().replace(/ſ/g, 's');
//: An option's OCC tail, read with everything but letters and digits taken out, so no case,
//: padding or separator the venue might forgive hides one.
const OPTION_TAIL_LOOSE = /[0-9]{6}[CP][0-9]{8}$/i;
//: An Alpaca asset id (a UUID, which a parser may take bare, braced or as a URN): it could name an
//: option contract without looking like one.
const isAssetId = symbol => /^[0-9a-f]{32}$/i.test(symbol.trim().replace(/^urn:uuid:/i, '').replace(/[{}-]/g, ''));
//: The single-leg option orders the practice account takes: a buy to open and a sell to close (long
//: premium, as the House trades today), and a buy to close, which can only buy back a short leg the
//: account already holds (the venue refuses a close of what is not held): the book's repair of an
//: unmatched short leg is exactly that order.
const PRACTICE_SINGLE_INTENTS = { buy_to_open: 'buy', sell_to_close: 'sell', buy_to_close: 'buy' };

/** Why the practice account's gateway will not forward an order body, or null when it passes. */
export function practiceOrderError(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return 'An order body must be a JSON object.';
  for (const key of Object.keys(body)) {
    const folded = foldKey(key);
    if (key !== folded && PRACTICE_DECIDING_FIELDS.has(folded)) {
      return `Order field ${JSON.stringify(key.slice(0, 40))} is not in the venue's own spelling: a venue that matches keys case-insensitively could read it as "${folded}", which this check decides on.`;
    }
  }
  if (isMultiLegOrder(body)) return structureOrder(body).error ?? null;
  const symbol = typeof body.symbol === 'string' ? body.symbol : '';
  if (OPTION_TAIL_LOOSE.test(symbol.replace(/[^A-Za-z0-9]/g, ''))) return practiceOptionError(body);
  if (isAssetId(symbol)) {
    return 'An order names its instrument by symbol, not by asset id: an asset id could name an option contract this check cannot read.';
  }
  return null;
}

function practiceOptionError(body) {
  const intent = body.position_intent;
  if (intent === 'sell_to_open') {
    return 'A single option sold to open is a naked short (a short leg with no long leg covering it): refused. A short leg is sold only inside a multi-leg order whose long legs cover it.';
  }
  const side = Object.prototype.hasOwnProperty.call(PRACTICE_SINGLE_INTENTS, intent) ? PRACTICE_SINGLE_INTENTS[intent] : null;
  if (!side) {
    return 'A single-leg option order names its position_intent (buy_to_open, sell_to_close or buy_to_close), so the venue never infers one: a sell it read as sell_to_open would be a naked short.';
  }
  if (body.side !== undefined && body.side !== side) return `A ${intent} order is a ${side}: its side says otherwise.`;
  return null;
}
