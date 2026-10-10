// The caps by maximum loss, and the real account's equity they follow (Sept 26, 2026 (the options-swarm run, Wave 5)).
//
// The plan (`docs/goals/LTCM_OPTIONS_SWARM.md`, "Money"): sizing is by MAXIMUM LOSS, never by premium, and the
// gateway's caps follow the account. On the real Alpaca venue (`alpaca`) an OPENING order may lose at most the lower
// of MAX_ORDER_MAX_LOSS_USD ($1,000) and MAX_ORDER_EQUITY_SHARE (15%) of the account's equity; the day's opening
// maximum loss, this order included, at most MAX_DAY_EQUITY_SHARE (100%) of equity and never above MAX_DAY_USD_ALPACA (the
// owner's whole $10,000 envelope; MAX_DAY_USD is Kalshi's own day again, the review's m17). No order opens once the
// day's orders reach MAX_DAY_OPEN_ORDERS (250): the rest of MAX_DAY_ORDERS (300) is kept for exits (the review's C6/C10). A credit structure opens only while equity is at least CREDIT_MIN_EQUITY_USD
// ($2,000): under it Alpaca's account is "limited margin". The $75 premium cap (`MAX_ORDER_USD_ALPACA`) is gone.
//
// The equity is read HERE, through the real account's own keys (`GET v2/account`, field `equity`), never taken from
// the House: the House cannot raise its own caps by reporting a larger account. The reading is stored in the gate's
// Durable Object (`ACCOUNT_EQUITY_KEY`) and read again on the order path when it is older than EQUITY_CAP_MAX_AGE_MS
// (two minutes). An opening order with no reading that young is refused (a 503 the House sends again): nothing fails
// open. Exits never wait on this read, and are never refused for want of it.
//
// It is independent of `equity.mjs`, the Kalshi-plus-Alpaca reading behind the frontier month's profit index, which
// keeps its own key, its own ten-minute life and its own rules. Every amount is a BigInt of micro-dollars.

import { PICO, parsePico, parseUsdMicro, parseCount } from './money.mjs';
import * as alpaca from './alpaca.mjs';

//: The gate's key for the last reading of the real account's equity.
export const ACCOUNT_EQUITY_KEY = 'alpaca-equity';
//: A reading older than this admits no opening order: the order path reads the account again first.
export const MAX_AGE_MS = 120_000;
//: A reading stamped this far in the future (a clock that moved) is still taken; beyond it, none is.
const FUTURE_SKEW_MS = 60_000;
const MILLION = 1000000n;
const TIMEOUT_MS = 8000;

/** A share of equity in millionths (0.15 -> 150000n), from 0 to 1; `fallback` when unset or malformed. */
export function shareMillionths(raw, fallback) {
  const pico = parsePico(typeof raw === 'string' ? raw.trim() : raw);
  if (pico === null || pico < 0n || pico > PICO) return fallback;
  return pico / MILLION;
}

//: The orders a day that may open (MAX_DAY_OPEN_ORDERS unset): the rest of MAX_DAY_ORDERS is kept for exits.
export const DAY_OPEN_ORDERS = 250;

/** The caps by maximum loss in force, from `vars`. A malformed value falls back to its documented default. */
export function maxLossCaps(env = {}) {
  const age = parseCount(env.EQUITY_CAP_MAX_AGE_MS, MAX_AGE_MS);
  const openOrders = env.MAX_DAY_OPEN_ORDERS;
  return {
    orderLimitMicro: parseUsdMicro(env.MAX_ORDER_MAX_LOSS_USD, 1000n * MILLION),
    orderShare: shareMillionths(env.MAX_ORDER_EQUITY_SHARE, 150000n),
    dayShare: shareMillionths(env.MAX_DAY_EQUITY_SHARE, MILLION),
    // The real account's own absolute day envelope (the review's m17): MAX_DAY_USD is Kalshi's day notional.
    dayLimitMicro: parseUsdMicro(env.MAX_DAY_USD_ALPACA, 10000n * MILLION),
    creditMinMicro: parseUsdMicro(env.CREDIT_MIN_EQUITY_USD, 2000n * MILLION),
    maxAgeMs: age > 0 ? age : MAX_AGE_MS,
    // Unset is the default; "0" is a choice (no order opens).
    maxDayOpenOrders: openOrders === undefined || openOrders === null || String(openOrders).trim() === ''
      ? DAY_OPEN_ORDERS : parseCount(openOrders, DAY_OPEN_ORDERS),
  };
}

/** `equity x share`, rounded down: a cap never rounds in the order's favour. Negative equity is none. */
const ofEquity = (equityMicro, share) => (equityMicro > 0n ? equityMicro * share / MILLION : 0n);

/** One opening order's cap: the lower of MAX_ORDER_MAX_LOSS_USD and MAX_ORDER_EQUITY_SHARE of equity. */
export function orderCapMicro(limits, equityMicro) {
  const byEquity = ofEquity(equityMicro, limits.orderShare);
  return byEquity < limits.orderLimitMicro ? byEquity : limits.orderLimitMicro;
}

/** The day's opening maximum loss cap: MAX_DAY_EQUITY_SHARE of equity, never above MAX_DAY_USD_ALPACA. */
export function dayCapMicro(limits, equityMicro) {
  const byEquity = ofEquity(equityMicro, limits.dayShare);
  return byEquity < limits.dayLimitMicro ? byEquity : limits.dayLimitMicro;
}

/**
 * The equity of a reading the caps may use at `at`, as micro-dollars, or null: read successfully, and no older than
 * `maxAgeMs`. A failed reading, a stale one, one from well in the future or a malformed row is no reading.
 */
export function freshEquity(reading, at, maxAgeMs) {
  if (!reading || reading.ok !== true || !/^-?\d{1,18}$/.test(String(reading.equity_micro))) return null;
  const age = at - Number(reading.at);
  if (!Number.isFinite(age) || age < -FUTURE_SKEW_MS || age > maxAgeMs) return null;
  return BigInt(reading.equity_micro);
}

/** Picodollars as micro, rounded DOWN (toward minus infinity): a reading of the account never errs high. */
const floorMicro = pico => (pico >= 0n ? pico / MILLION : -((-pico + MILLION - 1n) / MILLION));

/** `GET v2/account` with the real key pair, read-only, no redirect followed: the venue's account object, or a throw. */
async function fetchAccount(env, fetcher) {
  const headers = alpaca.authHeaders({ keyId: env.ALPACA_KEY_ID, secretKey: env.ALPACA_SECRET_KEY });
  const response = await fetcher(alpaca.target('v2/account'), {
    method: 'GET', headers: { Accept: 'application/json', 'User-Agent': 'ltcm-gateway/1.0', ...headers },
    redirect: 'manual', signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const account = await response.json().catch(() => { throw new Error('an unreadable answer'); });
  return account && typeof account === 'object' && !Array.isArray(account) ? account : {};
}

/** An account field as picodollars, or null (`string` or `number` only). */
const accountPico = raw => (typeof raw === 'string' || typeof raw === 'number' ? parsePico(raw) : null);

/**
 * Read the real account's equity, read-only: `GET v2/account` with the real key pair, no redirect followed (the
 * request carries the real account's keys). `{ ok: true, at, equity_micro }` or `{ ok: false, at, error }`.
 */
export async function readAccountEquity(env, { fetcher = fetch, now = Date.now } = {}) {
  const at = now();
  try {
    const equity = accountPico((await fetchAccount(env, fetcher)).equity);
    if (equity === null) throw new Error('no equity field');
    return { ok: true, at, equity_micro: String(floorMicro(equity)) };
  } catch (error) {
    return { ok: false, at, error: `alpaca account: ${String(error?.message || error?.name || 'read failed')}`.slice(0, 200) };
  }
}

// --- the stock caps (Oct 10, 2026) ----------------------------------------------------------------------------------
// The owner's goal of Oct 10, 2026 (`caps.mjs`, "stock and ETF buys on the real account"): an ETF position at most 50% of
// equity, a single stock at most 20%, at most 100% of equity invested in total or up to the venue's overnight margin
// limit (2x) where the account offers margin. Those are CEILINGS in this code: a var may lower a share or the multiple
// (to close the route, "0"), never raise one past the owner's line; a malformed value reads as the ceiling's default.

//: The owner's ceilings, in millionths: an ETF 50% of equity, a single stock 20%, the whole book 2x equity.
export const STOCK_ETF_SHARE_MAX = 500000n;
export const STOCK_SINGLE_SHARE_MAX = 200000n;
export const STOCK_MULTIPLE_MAX = 2n * MILLION;
//: The day's real stock buys, at qty x limit_price (cancelled ones included), at most this many times equity (the review
//: of Oct 10, 2026): a gateway backstop under the House's daily and drawdown stops, which live only in House code. Four
//: is two full turnovers of a book at its 2x line; a var may lower it ("0" closes the route), never raise it.
export const STOCK_DAY_MULTIPLE_MAX = 4n * MILLION;

/** A share or multiple in millionths from 0 to `max`; `max` when unset or malformed, `max` when above it. */
function capped(raw, max) {
  const pico = parsePico(typeof raw === 'string' ? raw.trim() : raw);
  if (pico === null || pico < 0n) return max;
  const millionths = pico / MILLION;
  return millionths > max ? max : millionths;
}

/**
 * The stock caps in force, from `vars`: STOCK_ETF_EQUITY_SHARE, STOCK_SINGLE_EQUITY_SHARE, STOCK_MAX_EQUITY_MULTIPLE,
 * STOCK_DAY_EQUITY_MULTIPLE.
 */
export function stockCaps(env = {}) {
  return {
    etfShare: capped(env.STOCK_ETF_EQUITY_SHARE, STOCK_ETF_SHARE_MAX),
    stockShare: capped(env.STOCK_SINGLE_EQUITY_SHARE, STOCK_SINGLE_SHARE_MAX),
    maxMultiple: capped(env.STOCK_MAX_EQUITY_MULTIPLE, STOCK_MULTIPLE_MAX),
    dayMultiple: capped(env.STOCK_DAY_EQUITY_MULTIPLE, STOCK_DAY_MULTIPLE_MAX),
  };
}

/** The day's stock buys cap: equity x STOCK_DAY_EQUITY_MULTIPLE, rounded down. */
export function stockDayCapMicro(limits, equityMicro) {
  return equityMicro > 0n ? equityMicro * limits.dayMultiple / MILLION : 0n;
}

/** One symbol's cap: its kind's share of equity (an "etf" the ETF share, anything else the single-stock share), rounded down. */
export function stockSymbolCapMicro(limits, kind, equityMicro) {
  return ofEquity(equityMicro, kind === 'etf' ? limits.etfShare : limits.stockShare);
}

/**
 * The account's multiplier as the caps take it, in millionths: Alpaca's `multiplier` ("1" a cash or limited-margin
 * account, "2" Reg T margin, "4" pattern-day-trader margin), and 1 when it cannot be read: no margin is ever assumed.
 */
export function multiplierMillionths(raw) {
  const pico = accountPico(raw);
  if (pico === null || pico < PICO) return MILLION;
  return pico / MILLION;
}

/** The book's margin multiple: the lower of STOCK_MAX_EQUITY_MULTIPLE and the account's multiplier (millionths). */
export function stockMultiple(limits, multiplier) {
  return multiplier < limits.maxMultiple ? multiplier : limits.maxMultiple;
}

/** The whole book's cap: equity x the lower of STOCK_MAX_EQUITY_MULTIPLE and the account's multiplier, rounded down. */
export function stockTotalCapMicro(limits, equityMicro, multiplier) {
  return equityMicro > 0n ? equityMicro * stockMultiple(limits, multiplier) / MILLION : 0n;
}

/**
 * The book as the cap weighs it (the review of Oct 10, 2026): `totalMicro` (everything long, plus resting stock buys,
 * plus buys in flight, plus this one) with the part the venue lends nothing on (`optionsMicro`, inside `totalMicro`)
 * weighted at the margin multiple instead of once. Under Reg T's overnight line a book holds `stocks / m + options <=
 * equity`, i.e. `stocks + options x m <= equity x m`; at a multiple of 1 or less nothing is lent and every dollar counts
 * once. The extra weight rounds up: the book never reads smaller than it is.
 */
export function stockBookMicro(totalMicro, optionsMicro, multiple) {
  if (multiple <= MILLION || optionsMicro <= 0n) return totalMicro;
  return totalMicro + (optionsMicro * (multiple - MILLION) + MILLION - 1n) / MILLION;
}

/**
 * Read what a real stock buy is judged by, read-only, fresh every time (Oct 10, 2026): `{ ok: true, at, equity_micro,
 * buying_power_micro, multiplier }` (`multiplier` in millionths, as a string) or `{ ok: false, at, error }`. Buying power
 * is the venue's own, which nets its open orders: the LOWER of `buying_power` and the overnight `regt_buying_power` (the
 * review of Oct 10, 2026: on pattern-day-trader margin, multiplier 4, `buying_power` is the intraday figure, 4 x
 * (last_equity - maintenance_margin), which bounds nothing held overnight). An account with no readable equity or buying
 * power is no reading, and so is a margin account (multiplier above 1) with no readable `regt_buying_power`.
 */
export async function readStockAccount(env, { fetcher = fetch, now = Date.now } = {}) {
  const at = now();
  try {
    const account = await fetchAccount(env, fetcher);
    const equity = accountPico(account.equity);
    if (equity === null) throw new Error('no equity field');
    let power = accountPico(account.buying_power);
    if (power === null) throw new Error('no buying_power field');
    const multiplier = multiplierMillionths(account.multiplier);
    // A cash account (multiplier 1) borrows nothing, so its `buying_power` (its cash) needs no overnight figure beside it;
    // one that is sent must still read.
    const given = account.regt_buying_power !== undefined && account.regt_buying_power !== null;
    const overnight = given ? accountPico(account.regt_buying_power) : null;
    if (overnight === null && (given || multiplier > MILLION)) throw new Error('no regt_buying_power field');
    if (overnight !== null && overnight < power) power = overnight;
    return { ok: true, at, equity_micro: String(floorMicro(equity)), buying_power_micro: String(floorMicro(power)),
      multiplier: String(multiplier) };
  } catch (error) {
    return { ok: false, at, error: `alpaca account: ${String(error?.message || error?.name || 'read failed')}`.slice(0, 200) };
  }
}

/**
 * The reading an opening order is judged by: the stored one while it is young enough, else a new read, recorded in
 * the gate whatever it found. Never throws; the caller refuses the open unless `freshEquity` finds an equity in it.
 */
export async function refreshAccountEquity(env, gate, { fetcher = fetch, now = Date.now } = {}) {
  const { maxAgeMs } = maxLossCaps(env);
  let stored = null;
  try {
    stored = await gate.accountEquity();
  } catch {
    stored = null;
  }
  if (freshEquity(stored, now(), maxAgeMs) !== null) return stored;
  const reading = await readAccountEquity(env, { fetcher, now });
  try {
    return await gate.recordAccountEquity(reading);
  } catch {
    return reading;  // unrecorded: the gate still holds the old reading, and refuses the open by it
  }
}

/** A share as a percentage for a sentence: 150000n -> "15%", 125000n -> "12.5%". */
export function percent(millionths) {
  const whole = millionths / 10000n;
  const rest = millionths % 10000n;
  return rest === 0n ? `${whole}%` : `${whole}.${String(rest).padStart(4, '0').replace(/0+$/, '')}%`;
}

/** A share as the decimal it was configured as: 150000n -> "0.15", 1000000n -> "1". */
export function shareText(millionths) {
  const rest = millionths % MILLION;
  return rest === 0n ? String(millionths / MILLION) : `${millionths / MILLION}.${String(rest).padStart(6, '0').replace(/0+$/, '')}`;
}

/** Micro-dollars as dollars and cents, rounded DOWN: how a cap or a reading is reported, never above what it is. */
export function formatUsdDown(micro) {
  const value = BigInt(micro ?? 0n);
  const cents = value >= 0n ? value / 10000n : -((-value + 9999n) / 10000n);
  const sign = cents < 0n ? '-' : '';
  const absolute = cents < 0n ? -cents : cents;
  return `${sign}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`;
}
