// The caps by maximum loss, and the real account's equity they follow (Sept 26, 2026 (the options-swarm run, Wave 5)).
//
// The plan (`docs/goals/LTCM_OPTIONS_SWARM.md`, "Money"): sizing is by MAXIMUM LOSS, never by premium, and the
// gateway's caps follow the account. On the real Alpaca venue (`alpaca`) an OPENING order may lose at most the lower
// of MAX_ORDER_MAX_LOSS_USD ($1,000) and MAX_ORDER_EQUITY_SHARE (15%) of the account's equity; the day's opening
// maximum loss, this order included, at most MAX_DAY_EQUITY_SHARE (100%) of equity and never above MAX_DAY_USD (the
// owner's whole $10,000 envelope). A credit structure opens only while equity is at least CREDIT_MIN_EQUITY_USD
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

/** The caps by maximum loss in force, from `vars`. A malformed value falls back to its documented default. */
export function maxLossCaps(env = {}) {
  const age = parseCount(env.EQUITY_CAP_MAX_AGE_MS, MAX_AGE_MS);
  return {
    orderLimitMicro: parseUsdMicro(env.MAX_ORDER_MAX_LOSS_USD, 1000n * MILLION),
    orderShare: shareMillionths(env.MAX_ORDER_EQUITY_SHARE, 150000n),
    dayShare: shareMillionths(env.MAX_DAY_EQUITY_SHARE, MILLION),
    creditMinMicro: parseUsdMicro(env.CREDIT_MIN_EQUITY_USD, 2000n * MILLION),
    maxAgeMs: age > 0 ? age : MAX_AGE_MS,
  };
}

/** `equity x share`, rounded down: a cap never rounds in the order's favour. Negative equity is none. */
const ofEquity = (equityMicro, share) => (equityMicro > 0n ? equityMicro * share / MILLION : 0n);

/** One opening order's cap: the lower of MAX_ORDER_MAX_LOSS_USD and MAX_ORDER_EQUITY_SHARE of equity. */
export function orderCapMicro(limits, equityMicro) {
  const byEquity = ofEquity(equityMicro, limits.orderShare);
  return byEquity < limits.orderLimitMicro ? byEquity : limits.orderLimitMicro;
}

/** The day's opening maximum loss cap: MAX_DAY_EQUITY_SHARE of equity, never above MAX_DAY_USD (`maxDayMicro`). */
export function dayCapMicro(limits, equityMicro, maxDayMicro) {
  const byEquity = ofEquity(equityMicro, limits.dayShare);
  return byEquity < maxDayMicro ? byEquity : maxDayMicro;
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

/**
 * Read the real account's equity, read-only: `GET v2/account` with the real key pair, no redirect followed (the
 * request carries the real account's keys). `{ ok: true, at, equity_micro }` or `{ ok: false, at, error }`.
 */
export async function readAccountEquity(env, { fetcher = fetch, now = Date.now } = {}) {
  const at = now();
  try {
    const headers = alpaca.authHeaders({ keyId: env.ALPACA_KEY_ID, secretKey: env.ALPACA_SECRET_KEY });
    const response = await fetcher(alpaca.target('v2/account'), {
      method: 'GET', headers: { Accept: 'application/json', 'User-Agent': 'ltcm-gateway/1.0', ...headers },
      redirect: 'manual', signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const account = await response.json().catch(() => { throw new Error('an unreadable answer'); });
    const raw = account && typeof account === 'object' ? account.equity : undefined;
    const equity = typeof raw === 'string' || typeof raw === 'number' ? parsePico(raw) : null;
    if (equity === null) throw new Error('no equity field');
    return { ok: true, at, equity_micro: String(floorMicro(equity)) };
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
