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
    // News (Oct 19, 2026; the event lane EVL-1), read only: Alpaca's Benzinga articles, the ENEWS events of
    // PREREG-EVL-1 (headline, summary, symbols, created_at, updated_at). One path, GET only.
    ['GET', /^v1beta1\/news$/],
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

/**
 * A venue's own per-order cap (`MAX_ORDER_USD_KALSHI`), in micro-dollars, or null when unset. Since Sept 26, 2026 (the
 * options-swarm run, Wave 5) the real Alpaca venue is capped by maximum loss (`account.mjs`), never by this or by
 * MAX_ORDER_USD: the gate does not read `MAX_ORDER_USD_ALPACA`, which wrangler.jsonc no longer sets.
 */
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
 * `structures` is the list of structure types the real Alpaca account may OPEN
 * (`admittedStructures(env)`); with none, every multi-leg open is refused. A multi-leg order is always
 * read by the structure rules (`structureNotional`), whatever the list: a priced structure answers
 * `{ micro, structure, opening }`, an open at its maximum loss, a close at zero (the router then admits
 * the close only when the account holds every leg it closes, `closeLegsHeldError`). A single-leg option
 * buy_to_close answers `{ micro: 0n, shortClose: true }`: the router admits it only when the account holds
 * that contract short (`shortCloseBody`, Sept 25, 2026).
 */
export function notional(venue, body, { reference = null, exit = false, structures = [] } = {}) {
  if (!body || typeof body !== 'object') return { error: 'An order body is required.' };
  if (venue === 'kalshi') return kalshiNotional(body, exit);
  if (venue === 'alpaca') {
    return isMultiLegOrder(body) ? structureNotional(body, structures) : alpacaNotional(body, reference);
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
//
// ONE exception, a buy with position_intent buy_to_close (Sept 25, 2026, the review of Deploy G, MAJOR 2):
// the buy-back of a SHORT leg a broken structure left on the real account (an uneven multi-leg fill, a long
// leg sold alone, an assignment). The book buys it back as one single-leg buy_to_close
// (`league/book.py` `_close_break_units`, `ltcm/adapters/alpaca.py` `submit`), and until today this rule
// refused that order as not long premium, so the House retried it every reading and the naked short stayed
// at the venue. It is answered `{ micro: 0n, shortClose: true }` here, never priced as an entry: the router
// admits it only after the account's positions show that contract held SHORT for at least `qty`
// (`shortCloseBody` + `closeLegsHeldError`), and then reserves it as an exit at one micro-dollar. A caller
// that forwards the zero instead is refused by the gate ("a positive notional"), so it fails closed.
function optionNotional(body) {
  if (parsePico(body.notional) !== null) return { error: 'An option order is sized in contracts, not dollars.' };
  const intent = String(body.position_intent || '');
  const side = String(body.side || '');
  const shortClose = side === 'buy' && intent === 'buy_to_close';
  if (!shortClose && !((side === 'buy' && intent === 'buy_to_open') || (side === 'sell' && intent === 'sell_to_close'))) {
    return { error: 'An option order must be buy with position_intent buy_to_open, or sell with sell_to_close: long premium only. (A buy with buy_to_close goes only to buy back a short leg the real account holds.)' };
  }
  if (String(body.type || '') !== 'limit') return { error: 'An option order must be a limit order.' };
  const qty = parsePico(body.qty);
  if (qty === null || qty <= 0n || qty % PICO !== 0n) return { error: 'Option qty must be a whole number of contracts.' };
  const limit = parsePico(body.limit_price);
  if (limit === null || limit <= 0n) return { error: 'An option order needs a positive limit price.' };
  // The buy-back's limit is not capped: a naked short must be bought back whatever it costs, and a dollar cap
  // would strand it exactly as the per-order cap stranded two perp shorts on Sept 18 (PURPOSE_HEADER above).
  if (shortClose) return { micro: 0n, shortClose: true };
  return { micro: picoToMicro(mulPico(qty, limit) * OPTION_MULTIPLIER) };
}

/**
 * A single-leg buy_to_close read as a one-leg close (`closeLegsHeldError`, `closedLegRows`): the contract it
 * buys back must be held SHORT for at least its `qty` (Sept 25, 2026, the review of Deploy G, MAJOR 2).
 */
export function shortCloseBody(body) {
  return { qty: body.qty, legs: [{ symbol: body.symbol, ratio_qty: '1', side: 'buy', position_intent: 'buy_to_close' }] };
}

/**
 * A single-leg sell_to_close read as a one-leg close (Sept 26, 2026 (the options-swarm run, Wave 5), the review's m14): the
 * contract it sells must be held LONG for at least its `qty`, available. Until today it was trusted to the venue, which a
 * margin account may take as a sale that opens a short.
 */
export function longCloseBody(body) {
  return { kind: 'sell_to_close', qty: body.qty, legs: [{ symbol: body.symbol, ratio_qty: '1', side: 'sell', position_intent: 'sell_to_close' }] };
}

/**
 * Why a single-leg option order may not OPEN on the real account, or null (Sept 26, 2026, Wave 5, the review's m7/m15). A
 * `buy_to_open` is a `long_call` or a `long_put` by the contract's right, and is admitted only when OPTION_STRUCTURES_REAL
 * (`admitted`) names that type; every other single-leg order is not an open and passes to the rules that read it.
 */
export function singleLegOpenError(body, admitted = []) {
  if (!body || typeof body !== 'object' || body.position_intent !== 'buy_to_open') return null;
  const parts = OCC_PARTS.exec(typeof body.symbol === 'string' ? body.symbol : '');
  if (!parts) return null;  // not a standard option symbol: the shape rules refuse it
  const type = parts[3] === 'C' ? 'long_call' : 'long_put';
  if (admitted.includes(type)) return null;
  return `${named(type).replace(/^a/, 'A')} is not admitted on the real account: OPTION_STRUCTURES_REAL admits ${admitted.length ? admitted.join(', ') : 'none'}.`;
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
//: A single contract bought to open, named by its right (Sept 26, 2026 (the options-swarm run, Wave 5), the review's
//: m7/m15): not one of the structure spec's types, so the real account opens one only when OPTION_STRUCTURES_REAL names it.
export const SINGLE_LEG_TYPES = ['long_call', 'long_put'];
//: Every name OPTION_STRUCTURES_REAL may carry.
export const REAL_TYPES = [...STRUCTURE_TYPES, ...SINGLE_LEG_TYPES];
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
 * the code): a comma- or space-separated list of the spec's type names, and since Sept 26, 2026
 * `long_call` and `long_put` for a single contract bought to open. A name that is not a type admits
 * nothing at all, so a typo can only ever close the route, never open more of it.
 */
export function admittedStructures(env = {}) {
  const raw = String(env.OPTION_STRUCTURES_REAL ?? '').trim();
  if (!raw || raw.toLowerCase() === 'off') return [];
  const names = raw.split(/[\s,]+/).filter(Boolean);
  if (names.some(name => !REAL_TYPES.includes(name))) return [];
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
 * `limit x 100 x qty`, a credit type `(K - credit) x 100 x qty`), a close at zero. An OPEN of a type the
 * account does not admit is refused. A CLOSE of any defined-risk type is priced whatever `admitted`
 * says (Sept 25, 2026, the review of g/money, MAJOR): it only takes risk off, and the router admits it
 * only when the account holds every leg it closes (`closeLegsHeldError`). Until then a close of a type
 * not listed was refused, so a gateway deployed back to "off" -- which `league.ci` makes the only
 * configuration while the constitution's O1 is off -- could never close a structure the account still
 * held, and it was carried into expiry.
 */
export function structureNotional(body, admitted = []) {
  const read = structureOrder(body);
  if (read.error) return { error: read.error };
  if (read.opening && !admitted.includes(read.type)) {
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
 * What `positions` (Alpaca's `GET v2/positions` rows) leave AVAILABLE to close, by symbol, in signed picounits: positive
 * long, negative short. `qty_available` (the part no open order commits) when the row carries it, never more than `qty`;
 * a row without it counts its `qty`; one that cannot be read leaves nothing; a row that contradicts itself holds nothing.
 */
export function availableHeld(positions) {
  const held = new Map();
  if (!Array.isArray(positions)) return held;
  for (const row of positions) {
    if (!row || typeof row !== 'object' || typeof row.symbol !== 'string') continue;
    const amount = parsePico(row.qty);
    if (amount === null || amount === 0n) continue;
    const sign = row.side === 'short' ? -1n : row.side === 'long' ? 1n : (amount < 0n ? -1n : 1n);
    if ((row.side === 'short' || row.side === 'long') && (amount < 0n) !== (sign < 0n)) continue;  // a row that contradicts itself holds nothing
    let magnitude = amount < 0n ? -amount : amount;
    if (row.qty_available !== undefined && row.qty_available !== null) {
      // Its sign is not relied on (only its size); one that cannot be read leaves nothing available.
      const available = parsePico(row.qty_available);
      const free = available === null ? 0n : (available < 0n ? -available : available);
      if (free < magnitude) magnitude = free;
    }
    if (magnitude === 0n) continue;
    held.set(row.symbol, (held.get(row.symbol) ?? 0n) + sign * magnitude);
  }
  return held;
}

/**
 * Why a multi-leg CLOSE may not go to the real account given its `positions` (Alpaca's `GET v2/positions` rows:
 * `{symbol, qty, qty_available, side}`, a short option reported with side "short" and a negative qty), or null when every
 * leg is held. `body` has already passed `structureOrder` as a close, or is a single-leg buy_to_close read as one leg
 * (`shortCloseBody`, the review of Deploy G).
 *
 * What a leg may close is what is AVAILABLE (the review of g/money, Sept 25, 2026): `qty_available`, the part not already
 * committed to an open order, when the row carries it (never more than `qty`); a row without it counts its `qty`. So a
 * second close of legs a resting close already sells is refused here, not only at the venue.
 */
export function closeLegsHeldError(body, positions) {
  if (!Array.isArray(positions)) return 'The account\'s positions could not be read as a list: a real close is not admitted unread.';
  const units = value => picoUnits(value < 0n ? -value : value);
  const qty = parsePico(body.qty);
  const held = availableHeld(positions);
  const short = [];
  for (const raw of body.legs) {
    const intent = LEG_INTENTS[raw.position_intent];
    const need = qty * (parsePico(raw.ratio_qty) / PICO);
    const have = held.get(raw.symbol) ?? 0n;
    const enough = intent.sign > 0 ? have >= need : -have >= need;
    if (!enough) {
      short.push(`${raw.symbol} ${intent.sign > 0 ? 'long' : 'short'} (${units(need)} needed, ${have === 0n ? 'none' : `${units(have)} ${have > 0n ? 'long' : 'short'}`} held)`);
    }
  }
  if (short.length === 0) return null;
  if (body.kind === 'stock') {
    return `A stock order on the real account must close shares it holds: ${short.join('; ')}. A sale of shares not held long would be a short sale, and a buy that covers no short would open a position: refused.`;
  }
  const what = body.order_class === 'mleg' ? 'A structure close must close legs'
    : body.kind === 'sell_to_close' ? 'A single-leg sell_to_close must sell a long leg'
      : 'A single-leg buy_to_close must buy back a short leg';
  return `${what} the real account holds: ${short.join('; ')}. A close of a leg not held would open a position: refused.`;
}

/** Picounits as a plain decimal (`5`, `-0.5`), exact: a count of contracts or shares for a sentence or a position row. */
export function picoUnits(value) {
  const sign = value < 0n ? '-' : '';
  const magnitude = value < 0n ? -value : value;
  const rest = magnitude % PICO;
  return `${sign}${magnitude / PICO}${rest === 0n ? '' : `.${String(rest).padStart(12, '0').replace(/0+$/, '')}`}`;
}

/**
 * The position rows a CLOSE admitted just now takes out of a cached reading (the review of g/money, Sept 25, 2026): each
 * leg's `qty x ratio_qty`, long legs down and short legs up, as side-less rows `closeLegsHeldError` reads by their sign. A
 * second close of the same legs within the cache's few seconds is then read against what is left, not what was there.
 */
export function closedLegRows(body) {
  const qty = parsePico(body.qty);
  return body.legs.map(raw => {
    // Exact (Sept 26, 2026, Wave 5): a stock close may be for fractional shares, which a whole count would round away.
    const need = qty * (parsePico(raw.ratio_qty) / PICO);
    return { symbol: raw.symbol, qty: picoUnits(LEG_INTENTS[raw.position_intent].sign > 0 ? -need : need) };
  });
}

// --- stock on the real account: assignment closes only (Sept 26, 2026 (the options-swarm run, Wave 5)) ---------------
// The plan's prune ("stock orders except the sale of assigned shares"), the cheap version: the real account trades
// options only, and the one stock order it may send is the close of shares an assignment left on it -- an American short
// leg assigned (SPY, QQQ, IWM and single names settle physically) becomes shares, long for a short put and short for a
// short call. So the only stock order admitted on `alpaca` is a SELL of a stock the account holds LONG (qty at most what
// it holds available) or a BUY that covers a stock it holds SHORT (qty at most the short), read from the account's
// signed positions like any real close (`closeLegsHeldError`), failing closed when they cannot be read. Such an order
// takes risk off: it is an exit (no dollar cap; counted in the day's orders; stopped by the kill switch). Every other
// stock order, and every crypto order, is refused. `alpaca-paper` is unchanged.
//
// Since Oct 10, 2026 (the review of the stock buys, MAJOR) a stock order's positions are read FRESH, never from the
// router's per-isolate cache (an isolate's cached reading could still show shares sold, or a short covered, through
// another isolate), and the Gate serializes stock closes as it serializes buys (`gate.mjs` `reserveStockClose`): a close
// is admitted only when its qty, plus the closes of the same symbol and side the Gate admitted that the reading may not
// show yet, is at most what the fresh reading leaves available (`closeAvailable`). So two sales of the same shares,
// through one isolate or two, cannot both go, and neither can a sale of shares already sold: nothing is a short sale.
// The design review of Oct 10, 2026: the open orders are read before the positions, and the Gate holds each close a
// minute after its answer, since the venue's positions can lag a filled sale while its order has left the open list.

/**
 * What a stock CLOSE of `symbol` on `side` may take by the venue's own readings (the design review of Oct 10, 2026):
 * `{ available }` (picounits) or `{ error, source }`. A sale closes shares held long, a buy covers shares held short. It is
 * the lower of what `positions` leave available (`availableHeld`: `qty_available`, which nets the venue's own open orders)
 * and the whole position less the open orders on the same side for the symbol (`orders`, read BEFORE the positions: an
 * order that fills between the two reads is counted in both, never in neither), never below zero. Fails closed: a list
 * that may be cut off (`ordersLimit` rows), or an open order on that side with no readable qty, is an error.
 */
export function closeAvailable(symbol, side, positions, orders, { ordersLimit = 500 } = {}) {
  if (!Array.isArray(orders)) return { error: 'the account\'s open orders were not a list', source: 'orders' };
  if (orders.length >= ordersLimit) return { error: `the account has ${orders.length} or more open orders, more than one reading lists`, source: 'orders' };
  const sign = side === 'sell' ? 1n : -1n;
  const free = (availableHeld(positions).get(symbol) ?? 0n) * sign;
  const whole = heldShares(symbol, positions) * sign;
  let open = 0n;
  for (const row of orders) {
    if (!row || typeof row !== 'object' || row.symbol !== symbol || row.side !== side) continue;
    const qty = parsePico(row.qty);
    if (qty === null || qty <= 0n) return { error: `the open ${side} order for ${symbol} has no qty to count it by`, source: 'orders' };
    const filled = parsePico(row.filled_qty ?? '0') ?? 0n;
    const done = filled > 0n ? filled : 0n;
    if (qty > done) open += qty - done;
  }
  const net = whole - open;
  const available = free < net ? free : net;
  return { available: available > 0n ? available : 0n };
}

/**
 * A stock order on the real account read as the close it must be: `{ body }` (a one-leg close in the shape
 * `closeLegsHeldError` and `closedLegRows` read, `kind: "stock"`), or `{ error }`. `body` has passed `alpacaShapeError`.
 */
export function realStockClose(body) {
  const symbol = String(body.symbol || '');
  if (CRYPTO_PAIR.test(symbol)) {
    return { error: 'Crypto is not traded on the real account: its only stock orders close shares an assignment left on it.' };
  }
  if (!STOCK_SYMBOL.test(symbol)) return { error: alpacaSymbolError(symbol) || 'An Alpaca order needs a top-level symbol.' };
  if (present(body, 'position_intent')) return { error: 'A stock order carries no position_intent: that field is an option order\'s.' };
  if (present(body, 'notional')) {
    return { error: 'A stock order on the real account is sized in shares (qty), never in dollars (notional): a close sells or covers at most what the account holds, and a buy is metered at qty x limit_price.' };
  }
  const qty = parsePico(body.qty);
  if (qty === null || qty <= 0n) return { error: 'Order qty is missing or not positive.' };
  if (body.type === 'limit') {
    const limit = parsePico(body.limit_price);
    if (limit === null || limit <= 0n) return { error: 'A limit order needs a positive limit price.' };
  }
  if (body.side !== 'sell' && body.side !== 'buy') return { error: 'A stock order is a buy or a sell.' };
  const intent = body.side === 'sell' ? 'sell_to_close' : 'buy_to_close';
  return { body: { kind: 'stock', qty: body.qty, legs: [{ symbol, ratio_qty: '1', side: body.side, position_intent: intent }] } };
}

// --- stock and ETF buys on the real account: long only, allow-listed, capped by the account (Oct 10, 2026) -------------
// The owner's goal of Oct 10, 2026: agent programs may trade ETFs, stocks and options with real money. An ETF position at
// most 50% of equity, a single stock at most 20%, at most 100% of equity invested in total, or up to the venue's overnight
// margin limit (2x) where the account offers margin; margin never for a short sale; no short sale at all; the kill switch,
// the daily stop and the drawdown stop stay; no hidden costs.
//
// So, beside the closes above, the real account admits ONE more stock order while STOCK_BUYS_REAL is "on": a BUY that opens
// or adds to a LONG position in a symbol of STOCK_UNIVERSE, read here from the order and judged by the router and the gate
// against the account's own reading (`account.readStockAccount`), its open orders and its positions, never against
// anything the House reports. The shape (`stockBuyOrder`): a limit order (a positive limit_price), time_in_force "day",
// qty in shares (fractional allowed, at most nine decimals, as Alpaca takes for fractionable assets), never notional. It is
// metered at qty x limit_price, rounded up: a buy fills at its limit or better, so nothing it spends is above that. The caps
// (`account.stockCaps`, judged in the gate in the step that reserves): this order alone at most the symbol's share of
// equity; the symbol's long market value, plus its open buy orders, plus buys admitted and not yet seen by the venue, plus
// this order, at most the same share; every long position's market value (options included) plus every open stock buy
// order plus this order at most equity x min(STOCK_MAX_EQUITY_MULTIPLE, the account's multiplier); and never above the
// account's buying power. A buy of a symbol the account holds SHORT is never this path: it is a cover, judged as a close
// above (at most the short), so no buy both covers and opens. A sale is always a close. Nothing here is ever a short sale.
//
// The review of Oct 10, 2026 tightened two of those caps. The book is a MARGIN line, not a gross one: options (and any
// other long the venue lends nothing on) are paid in full, so under Reg T's overnight 2x a book holds `stocks / 2 +
// options <= equity`; the cap is `stocks + options x m <= equity x m` with m = min(STOCK_MAX_EQUITY_MULTIPLE, the
// multiplier) (options at 1x while m <= 1: exactly the old cap on a cash account). And buying power is the LOWER of the
// venue's `buying_power` and its overnight `regt_buying_power` (on pattern-day-trader margin, multiplier 4,
// `buying_power` is the intraday figure, 4x, which bounds nothing overnight). A day's buys are capped too: at most
// STOCK_DAY_EQUITY_MULTIPLE (a ceiling of 4) x equity at qty x limit_price, cancelled buys included (`stock_day`): a
// gateway backstop under the House's daily and drawdown stops, against a looping release or a leaked runtime token.

//: The symbols a real stock buy may name: the broad index ETFs, the eleven SPDR sector ETFs, Treasuries and gold, and a
//: short named list of large US stocks. A constant the House and this gateway share in spirit; changing it is a reviewed
//: code change and a gateway deploy. `etf` symbols take the ETF share of equity, `stock` symbols the single-stock share.
export const STOCK_UNIVERSE = Object.freeze({
  SPY: 'etf', QQQ: 'etf', IWM: 'etf', DIA: 'etf',
  XLB: 'etf', XLC: 'etf', XLE: 'etf', XLF: 'etf', XLI: 'etf', XLK: 'etf', XLP: 'etf', XLRE: 'etf', XLU: 'etf', XLV: 'etf', XLY: 'etf',
  TLT: 'etf', GLD: 'etf',
  AAPL: 'stock', MSFT: 'stock', NVDA: 'stock', AMZN: 'stock', GOOGL: 'stock', META: 'stock', 'BRK.B': 'stock', JPM: 'stock',
  V: 'stock', UNH: 'stock', XOM: 'stock', JNJ: 'stock', PG: 'stock', MA: 'stock', HD: 'stock', AVGO: 'stock', LLY: 'stock',
  COST: 'stock',
  // The owner's AI build-out portfolio (Oct 23, 2026 restart): two leveraged funds and the single names the House did not list.
  SOXL: 'etf', NVDL: 'etf',
  MU: 'stock', TSM: 'stock', AMD: 'stock', SKHY: 'stock', ALAB: 'stock', LITE: 'stock', DELL: 'stock', VRT: 'stock', GEV: 'stock',
  SNDK: 'stock', INTC: 'stock', NBIS: 'stock', ASML: 'stock', BE: 'stock', PLTR: 'stock', CAMT: 'stock', IREN: 'stock', ASX: 'stock',
  AMAT: 'stock',
});

/** What STOCK_UNIVERSE says a symbol is: "etf", "stock", or null when it is not on the list. */
export const stockKind = symbol => (Object.prototype.hasOwnProperty.call(STOCK_UNIVERSE, symbol) ? STOCK_UNIVERSE[symbol] : null);

/** True when STOCK_BUYS_REAL is "on": anything else, unset or a typo, admits no real stock buy (closes go either way). */
export const stockBuysEnabled = (env = {}) => String(env.STOCK_BUYS_REAL ?? '').trim().toLowerCase() === 'on';

//: A share count as the venue takes it: a plain decimal, at most nine places (Alpaca's fractional precision).
const SHARE_QTY = /^\d{1,9}(\.\d{1,9})?$/;
//: A stock limit price: a plain decimal, at most four places (a penny at $1 and up, a hundredth of a cent under it).
const STOCK_LIMIT = /^\d{1,9}(\.\d{1,4})?$/;
const plain = value => (typeof value === 'number' && Number.isFinite(value) ? String(value) : value);

/**
 * A real-account stock BUY read as the long open it must be (Oct 10, 2026): `{ symbol, kind, micro }` (`micro` is
 * qty x limit_price in micro-dollars, rounded up) or `{ error }`. `body` has passed `alpacaShapeError` and
 * `realStockClose`; the account, its open orders and its positions are read only after this passes.
 */
export function stockBuyOrder(body) {
  if (!body || typeof body !== 'object' || body.side !== 'buy') return { error: 'A stock buy is a buy.' };
  const symbol = String(body.symbol || '');
  const kind = stockKind(symbol);
  if (!kind) {
    return { error: `${JSON.stringify(symbol.slice(0, 12))} is not on the real account's stock list: a real stock buy names one of ${Object.keys(STOCK_UNIVERSE).join(' ')}.` };
  }
  if (present(body, 'notional')) return { error: 'A real stock buy is sized in shares (qty), never in dollars (notional).' };
  if (present(body, 'position_intent')) return { error: 'A stock order carries no position_intent: that field is an option order\'s.' };
  if (body.type !== 'limit') {
    return { error: 'A real stock buy is a limit order: a market buy has no price of its own to meter it by, and fills wherever the book is.' };
  }
  if (body.time_in_force !== 'day') return { error: 'A real stock buy is a day order (time_in_force "day"): nothing rests past the session it was sized in.' };
  if (present(body, 'extended_hours') && typeof body.extended_hours !== 'boolean') return { error: 'extended_hours is true or false.' };
  if (present(body, 'order_class') && body.order_class !== 'simple') return { error: 'A real stock buy is a simple order.' };
  const rawQty = plain(body.qty);
  if (typeof rawQty !== 'string' || !SHARE_QTY.test(rawQty)) {
    return { error: 'A real stock buy\'s qty is a number of shares, at most nine decimal places (fractional shares as Alpaca takes them).' };
  }
  const qty = parsePico(rawQty);
  if (qty === null || qty <= 0n) return { error: 'Order qty is missing or not positive.' };
  const rawLimit = plain(body.limit_price);
  if (typeof rawLimit !== 'string' || !STOCK_LIMIT.test(rawLimit)) {
    return { error: 'A real stock buy needs a positive limit_price, at most four decimal places.' };
  }
  const limit = parsePico(rawLimit);
  if (limit === null || limit <= 0n) return { error: 'A real stock buy needs a positive limit_price, at most four decimal places.' };
  return { symbol, kind, micro: picoToMicro(mulPico(qty, limit)) };
}

/**
 * The signed number of shares (picounits) `positions` show for `symbol`: positive long, negative short, 0n when none. Read
 * like `closeLegsHeldError` reads a row (its `side`, else the sign of `qty`; a row that contradicts itself holds nothing),
 * from the whole `qty`, so a cached reading a close was just taken out of (`closedLegRows`) nets it.
 */
export function heldShares(symbol, positions) {
  if (!Array.isArray(positions)) return 0n;
  let net = 0n;
  for (const row of positions) {
    if (!row || typeof row !== 'object' || row.symbol !== symbol) continue;
    const amount = parsePico(row.qty);
    if (amount === null || amount === 0n) continue;
    if ((row.side === 'short' && amount > 0n) || (row.side === 'long' && amount < 0n)) continue;
    net += amount;
  }
  return net;
}

/**
 * Whether the venue lends on a long position row (Reg T: a US stock or ETF): a stock-shaped symbol whose `asset_class`,
 * when the row names one, is `us_equity`. An option, crypto, or anything else is paid in full: the book cap counts it at
 * the margin multiple (`gate.reserveStock`), which errs high for a row it cannot place.
 */
export const marginableRow = row => STOCK_SYMBOL.test(String(row?.symbol || ''))
  && (row.asset_class === undefined || row.asset_class === null || row.asset_class === 'us_equity');

/**
 * What the account already holds or has asked for, by the venue's own readings (Oct 10, 2026): `{ symbolMicro, totalMicro,
 * optionsMicro, openBuys }` or `{ error }`. `symbolMicro` is `symbol`'s long market value plus its open buy orders' remaining
 * notional; `totalMicro` is every long position's market value (stocks, ETFs and options alike: all of it is invested)
 * plus every open stock or ETF buy order's remaining notional (an option order is held to the option caps, and to buying
 * power at the venue); `optionsMicro` is the part of `totalMicro` the venue lends nothing on (long options and any other
 * long that is not a US stock or ETF, `marginableRow`), which the book cap weighs at the margin multiple. `openBuys` is
 * every open buy counted in `totalMicro` that names a `client_order_id`, as `{ client_order_id, symbol, micro }` (what it
 * counted): the Gate nets a buy it admitted and still holds against it, so the two count once (`gate.reserveStock`).
 * Fails closed: a long row with no readable market value, an open buy with no price (a market or stop buy), a symbol held
 * short, or a list that may be cut off (`ordersLimit` rows) is an error, never a guess.
 */
export function stockExposure(symbol, positions, orders, { ordersLimit = 500 } = {}) {
  if (!Array.isArray(positions)) return { error: 'the account\'s positions were not a list', source: 'positions' };
  if (!Array.isArray(orders)) return { error: 'the account\'s open orders were not a list', source: 'orders' };
  if (orders.length >= ordersLimit) return { error: `the account has ${orders.length} or more open orders, more than one reading lists`, source: 'orders' };
  let symbolMicro = 0n;
  let totalMicro = 0n;
  let optionsMicro = 0n;
  const openBuys = [];
  const short = new Set();
  for (const row of positions) {
    if (!row || typeof row !== 'object' || typeof row.symbol !== 'string') continue;
    const amount = parsePico(row.qty);
    if (amount === null || amount === 0n) continue;
    const isShort = row.side === 'short' || (row.side !== 'long' && amount < 0n);
    if ((row.side === 'short' && amount > 0n) || (row.side === 'long' && amount < 0n)) {
      return { error: `the position row for ${row.symbol} contradicts itself`, source: 'positions' };
    }
    if (isShort) {
      short.add(row.symbol);
      continue;
    }
    const value = parsePico(row.market_value);
    if (value === null || value < 0n) return { error: `the long position in ${row.symbol} has no readable market value`, source: 'positions' };
    const micro = picoToMicro(value);
    totalMicro += micro;
    if (!marginableRow(row)) optionsMicro += micro;
    if (row.symbol === symbol) symbolMicro += micro;
  }
  if (short.has(symbol)) return { error: `the account holds ${symbol} short: a buy of it covers the short, at most its size, and opens nothing`, short: true };
  for (const row of orders) {
    if (!row || typeof row !== 'object' || row.side !== 'buy') continue;
    const name = typeof row.symbol === 'string' ? row.symbol : '';
    // An option order (one leg or a structure) is held to the option caps; a cover of a short opens no long exposure.
    if (row.order_class === 'mleg' || isOptionSymbol(name) || name === '' || short.has(name)) continue;
    let remaining;
    const qty = parsePico(row.qty);
    if (qty !== null && qty > 0n) {
      const filled = parsePico(row.filled_qty ?? '0') ?? 0n;
      const left = qty - (filled > 0n ? filled : 0n);
      if (left <= 0n) continue;
      const price = parsePico(row.limit_price);
      if (price === null || price <= 0n) {
        return { error: `the open buy order for ${name} (${String(row.type || 'unknown').slice(0, 20)}) has no limit price to count it by`, source: 'orders' };
      }
      remaining = picoToMicro(mulPico(left, price));
    } else {
      const dollars = parsePico(row.notional);
      if (dollars === null || dollars <= 0n) return { error: `the open buy order for ${name} has neither a qty nor a notional to count it by`, source: 'orders' };
      remaining = picoToMicro(dollars);  // the whole notional, filled or not: errs high
    }
    totalMicro += remaining;
    if (name === symbol) symbolMicro += remaining;
    if (typeof row.client_order_id === 'string' && row.client_order_id !== '') {
      openBuys.push({ client_order_id: row.client_order_id, symbol: name, micro: remaining });
    }
  }
  return { symbolMicro, totalMicro, optionsMicro, openBuys };
}

// --- event-lane stock buys on the real account (release R2, gateway G2; PREREG-EVL-1 section 8) -----------------------
// The owner's goal of Oct 19, 2026: one lane, event-driven single US common stocks, long only, at most 10% of equity in
// any one name, at most 100% invested, no margin. The frozen pre-registration (docs/prereg/PREREG-EVL-1.md, section 8)
// says how its real entries go: limit-on-open or limit-on-close orders (`opg` / `cls`) at 1.25 x the previous SIP close,
// in WHOLE shares. Such a name is mostly NOT on STOCK_UNIVERSE (the lane trades whatever stock an event names), so while
// STOCK_EVENT_BUYS is "on" (and STOCK_BUYS_REAL with it: that switch stops every real stock buy) the real account admits
// one more kind of buy beside the list's: AN EVENT BUY, known by its own shape (`isEventBuy`: a buy whose time_in_force
// is `opg` or `cls`; the list's buys are day orders) and judged by its own rules before any of the list's caps:
// - its shape (`eventBuyOrder`): a US stock ticker that STOCK_UNIVERSE does not mark an ETF, a LIMIT order, `opg` or
//   `cls`, a whole number of shares, a positive limit_price of at most four decimals; never notional, never extended
//   hours, never a position_intent. Metered at qty x limit_price, rounded up, as every real stock buy is;
// - THE HOUSE'S ELIGIBLE LIST for the New York day (POST /v1/stock/eligible with the House's runtime token; lib/gate.mjs
//   `stockEligibleSet`): the names the House's universe test admitted for that session (PREREG-EVL-1 section 2: an
//   operating company's common stock, listed, $3 and up, $1M of ADV). The gateway cannot tell an ETF or an ETN from a
//   common stock by the venue's asset record, so only a name on the House's list goes, and only on the list's own day;
//   it is checked when the buy arrives and again in the step that reserves it;
// - ITS OWN CHECKS, read by this gateway with the real account's keys (`eventAssetError`, `eventBarFacts`), cached per
//   symbol per New York day: `v2/assets/<symbol>` says class us_equity, status active, tradable, on NYSE, NASDAQ, AMEX,
//   ARCA or BATS (never OTC); the SIP daily bars of the sessions before today put the previous close at $3 or more and
//   the mean close x volume of the last 20 sessions at $1,000,000 or more;
// - the limit at most 1.25 x that previous SIP close (`eventLimitError`): what the pre-registration's orders ask, never
//   a chase past it;
// - then every cap a real stock buy meets (`gate.reserveStock`), with ONE share for the name: the single-stock share of
//   equity, never above the goal's 10% (`account.STOCK_EVENT_SHARE_MAX`, a code ceiling whatever
//   STOCK_SINGLE_EQUITY_SHARE says), BOOK-WIDE: the name's long market value, its open buy orders, the buys this gateway
//   admitted and the venue does not show yet, and this order; the whole book at most equity x min(STOCK_MAX_EQUITY_MULTIPLE,
//   the account's multiplier); the account's buying power; the day's buys and order counts. The kill switch stops it
//   as it stops every order.
// A SALE of event shares is a close like any other (`realStockClose`, read fresh and serialized in the Gate): a market or
// limit sale of shares held long, with any time_in_force the venue takes (`opg`, `cls` and `day` alike), never a short
// sale. Nothing here is ever a short sale, a margin buy or a buy of a name the House did not list.

//: The time_in_force values of an event buy: the opening and the closing auction. A buy with any other is not one.
export const EVENT_TIFS = Object.freeze(['opg', 'cls']);
//: The listing exchanges an event buy's asset may name (PREREG-EVL-1 section 2; never OTC).
export const EVENT_EXCHANGES = Object.freeze(['NYSE', 'NASDAQ', 'AMEX', 'ARCA', 'BATS']);
//: The previous SIP close an event buy's name needs ($3.00) and the mean close x volume of its last sessions ($1,000,000).
export const EVENT_MIN_PRICE_PICO = 3n * PICO;
export const EVENT_MIN_ADV_PICO = 1000000n * PICO;
export const EVENT_ADV_SESSIONS = 20;
//: An event buy's limit is at most 5/4 (1.25 x) of the previous SIP close.
export const EVENT_LIMIT_NUM = 5n;
export const EVENT_LIMIT_DEN = 4n;
//: The most names one eligible list may carry (the lane's universe is computed for the issuers with events: tens a day).
export const EVENT_LIST_MAX = 5000;
//: An eligible list is for the New York day it is published on, or a session within this many days after it.
export const EVENT_LIST_DAYS_AHEAD = 7;
//: A whole share count as the venue takes it: 1 to 999,999,999, no decimals.
const WHOLE_SHARES = /^[1-9]\d{0,8}$/;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** True when STOCK_EVENT_BUYS is "on": anything else, unset or a typo, admits no event buy (sales go either way). */
export const stockEventBuysEnabled = (env = {}) => String(env.STOCK_EVENT_BUYS ?? '').trim().toLowerCase() === 'on';

/** True when `body` is an event buy's shape: a buy whose time_in_force is one of the auctions' (`EVENT_TIFS`). */
export const isEventBuy = body => Boolean(body) && typeof body === 'object' && body.side === 'buy'
  && EVENT_TIFS.includes(body.time_in_force);

/** The New York calendar day of an instant (`YYYY-MM-DD`): the day an eligible list and a cached reading belong to. */
export function nyDay(at) {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit',
      day: '2-digit' }).format(new Date(at));
  } catch {
    return new Date(at).toISOString().slice(0, 10);
  }
}

/**
 * A real-account EVENT BUY read as the auction order it must be (release R2): `{ symbol, qty, limit, micro, tif }` (`qty`
 * whole shares in picounits, `limit` picodollars, `micro` qty x limit_price rounded up) or `{ error }`. `body` has passed
 * `alpacaShapeError` and `realStockClose`; nothing of the account or the venue is read until this passes.
 */
export function eventBuyOrder(body) {
  if (!isEventBuy(body)) return { error: 'An event buy is a buy in the opening or the closing auction (time_in_force "opg" or "cls").' };
  const symbol = String(body.symbol || '');
  if (!STOCK_SYMBOL.test(symbol)) return { error: 'An event buy names a US stock ticker (AAPL, BRK.B).' };
  if (stockKind(symbol) === 'etf') {
    return { error: `${symbol} is an ETF: the event lane buys common stocks only (an ETF is bought, if ever, as a day order on the list).` };
  }
  if (present(body, 'notional')) return { error: 'An event buy is sized in whole shares (qty), never in dollars (notional).' };
  if (present(body, 'position_intent')) return { error: 'A stock order carries no position_intent: that field is an option order\'s.' };
  if (body.type !== 'limit') {
    return { error: 'An event buy is a limit order (limit-on-open or limit-on-close): a market order has no price of its own to meter it by.' };
  }
  if (present(body, 'extended_hours') && body.extended_hours !== false) {
    return { error: 'An event buy goes in the exchange\'s auction, never in extended hours.' };
  }
  if (present(body, 'order_class') && body.order_class !== 'simple') return { error: 'An event buy is a simple order.' };
  const rawQty = typeof body.qty === 'number' && Number.isSafeInteger(body.qty) ? String(body.qty) : body.qty;
  if (typeof rawQty !== 'string' || !WHOLE_SHARES.test(rawQty)) {
    return { error: 'An event buy\'s qty is a whole number of shares (the auctions take no fractional share).' };
  }
  const qty = parsePico(rawQty);
  const rawLimit = plain(body.limit_price);
  const limit = typeof rawLimit === 'string' && STOCK_LIMIT.test(rawLimit) ? parsePico(rawLimit) : null;
  if (limit === null || limit <= 0n) return { error: 'An event buy needs a positive limit_price, at most four decimal places.' };
  return { symbol, qty, limit, micro: picoToMicro(mulPico(qty, limit)), tif: body.time_in_force };
}

/**
 * Why the venue's asset record does not admit an event buy of `symbol`, or null (PREREG-EVL-1 section 2): class
 * us_equity, status active, tradable, listed on one of `EVENT_EXCHANGES`.
 */
export function eventAssetError(asset, symbol) {
  if (!asset || typeof asset !== 'object' || Array.isArray(asset)) return `the venue has no asset record for ${symbol}`;
  if (String(asset.symbol || '') !== symbol) return `the venue's asset record is not ${symbol}'s`;
  if (asset.class !== 'us_equity') return `${symbol} is not a US equity (class ${JSON.stringify(String(asset.class ?? '')).slice(0, 24)})`;
  if (asset.status !== 'active' || asset.tradable !== true) return `${symbol} is not active and tradable at the venue`;
  if (!EVENT_EXCHANGES.includes(asset.exchange)) {
    return `${symbol} is listed on ${JSON.stringify(String(asset.exchange ?? '')).slice(0, 24)}, not on ${EVENT_EXCHANGES.join(', ')}`;
  }
  return null;
}

/**
 * What the SIP daily bars of `symbol` say for an event buy on New York day `today`: `{ prevClose, adv, sessions, last }`
 * (picodollars: the last completed session's close and the mean close x volume of its last `EVENT_ADV_SESSIONS`
 * sessions, rounded down) or `{ error, cap }` (`stock_price`, `stock_adv`: a definite refusal; `bars`: the reading is
 * not one). Bars on `today` or later (a session still trading) are left out. Fails closed: a close or a volume that is
 * not a number, two bars on one day, or fewer than `EVENT_ADV_SESSIONS` sessions refuse.
 */
export function eventBarFacts(bars, today, symbol) {
  if (!Array.isArray(bars)) return { error: `the venue's daily bars of ${symbol} were not a list`, cap: 'bars' };
  const rows = [];
  const days = new Set();
  for (const bar of bars) {
    const at = Date.parse(String(bar?.t ?? ''));
    if (!Number.isFinite(at)) return { error: `a daily bar of ${symbol} has no time`, cap: 'bars' };
    const day = nyDay(at);
    if (day >= today) continue;
    if (days.has(day)) return { error: `the venue gave two daily bars of ${symbol} on ${day}`, cap: 'bars' };
    days.add(day);
    const close = parsePico(bar.c);
    const volume = parsePico(bar.v);
    if (close === null || close <= 0n || volume === null || volume < 0n) {
      return { error: `the daily bar of ${symbol} on ${day} has no readable close or volume`, cap: 'bars' };
    }
    rows.push({ day, close, volume });
  }
  rows.sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0));
  if (rows.length < EVENT_ADV_SESSIONS) {
    return { error: `${symbol} has ${rows.length} SIP daily bars before ${today}: an event buy needs ${EVENT_ADV_SESSIONS} sessions of them`, cap: 'stock_adv' };
  }
  const last = rows.slice(-EVENT_ADV_SESSIONS);
  const prevClose = last[last.length - 1].close;
  // Close x volume exactly (picodollars x picounits / PICO), summed, then the mean rounded DOWN: never above what it is.
  const adv = last.reduce((sum, row) => sum + (row.close * row.volume) / PICO, 0n) / BigInt(EVENT_ADV_SESSIONS);
  if (prevClose < EVENT_MIN_PRICE_PICO) {
    return { error: `${symbol}'s previous SIP close of $${picoUnits(prevClose)} is under the event lane's $3.00`, cap: 'stock_price' };
  }
  if (adv < EVENT_MIN_ADV_PICO) {
    return { error: `${symbol}'s ${EVENT_ADV_SESSIONS}-session SIP dollar volume of $${adv / PICO} a day is under the event lane's $1,000,000`, cap: 'stock_adv' };
  }
  return { prevClose, adv, sessions: rows.length, last: last[last.length - 1].day };
}

/** Why an event buy's limit (picodollars) is above 1.25 x the previous SIP close (picodollars), or null. */
export function eventLimitError(limit, prevClose, symbol = 'it') {
  if (typeof limit !== 'bigint' || typeof prevClose !== 'bigint' || prevClose <= 0n) return `no previous SIP close of ${symbol} to bound the limit by`;
  if (limit * EVENT_LIMIT_DEN > prevClose * EVENT_LIMIT_NUM) {
    return `an event buy of ${symbol} at $${picoUnits(limit)} is above 1.25 x its previous SIP close of $${picoUnits(prevClose)} ` +
           `($${picoUnits(prevClose * EVENT_LIMIT_NUM / EVENT_LIMIT_DEN)}): the pre-registered limit is never chased past`;
  }
  return null;
}

/**
 * THE HOUSE'S ELIGIBLE LIST as POSTed (`{ day, symbols }`), read against the New York day `today`: `{ day, symbols }`
 * (the symbols sorted, each once) or `{ error }`. The day is `today` or a later one within `EVENT_LIST_DAYS_AHEAD`; at
 * most `EVENT_LIST_MAX` names, each a US stock ticker that STOCK_UNIVERSE does not mark an ETF; no name twice.
 */
export function eligibleList(body, today) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { error: 'An eligible list is a JSON object {day, symbols}.' };
  const unknown = Object.keys(body).find(key => key !== 'day' && key !== 'symbols');
  if (unknown !== undefined) return { error: `An eligible list carries only day and symbols, not ${JSON.stringify(unknown.slice(0, 40))}.` };
  const { day, symbols } = body;
  if (typeof day !== 'string' || !ISO_DAY.test(day) || Number.isNaN(Date.parse(`${day}T12:00:00Z`))) {
    return { error: 'An eligible list names its New York day as YYYY-MM-DD.' };
  }
  const ahead = new Date(Date.parse(`${today}T12:00:00Z`) + EVENT_LIST_DAYS_AHEAD * 86400000).toISOString().slice(0, 10);
  if (day < today || day > ahead) return { error: `An eligible list is for ${today} or a day up to ${ahead}, not ${day}.` };
  if (!Array.isArray(symbols) || symbols.length > EVENT_LIST_MAX) {
    return { error: `An eligible list's symbols are a list of at most ${EVENT_LIST_MAX} tickers.` };
  }
  const seen = new Set();
  for (const symbol of symbols) {
    if (typeof symbol !== 'string' || !STOCK_SYMBOL.test(symbol)) {
      return { error: `${JSON.stringify(String(symbol).slice(0, 12))} is not a US stock ticker.` };
    }
    if (stockKind(symbol) === 'etf') return { error: `${symbol} is an ETF: the event lane lists common stocks only.` };
    if (seen.has(symbol)) return { error: `${symbol} is listed twice.` };
    seen.add(symbol);
  }
  return { day, symbols: [...seen].sort() };
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
