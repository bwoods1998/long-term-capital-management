// Profit-indexed compute (Sept 23, 2026).
//
// The frontier month's cap grows with verified profit on the real accounts:
//
//   cap = FRONTIER_MONTH_USD + COMPUTE_PROFIT_SHARE x max(0, venue_equity - EQUITY_BASELINE_USD)
//
// and never above FRONTIER_MONTH_MAX_USD when that is set. `venue_equity` is read here, through the
// venue keys this Worker already holds and nowhere else: Kalshi's cash plus the value of its
// positions (`GET /portfolio/balance`), and Alpaca's account equity (`GET /v2/account`). The House
// cannot report its own profit to buy itself compute. A reading is kept ten minutes.
//
// The old cap is the floor, and nothing here fails open: indexing that is not configured, a venue
// that does not answer, an answer without the field, or a reading older than twice its life all
// give exactly FRONTIER_MONTH_USD. Every amount is a BigInt of micro-dollars.

import { PICO, parsePico, parseUsdMicro, formatUsd } from './money.mjs';
import { monthCapMicro } from './frontier.mjs';
import * as kalshi from './kalshi.mjs';
import * as alpaca from './alpaca.mjs';

export const EQUITY_KEY = 'equity';
//: How long one reading of the accounts is used before it is read again.
export const CACHE_MS = 10 * 60 * 1000;
//: A reading older than this (no refresh succeeded or was tried) no longer raises the cap.
export const MAX_AGE_MS = 2 * CACHE_MS;
const MILLION = 1000000n;
//: Picodollars as micro, rounded DOWN: a reading of the accounts never errs high.
const floorMicro = pico => pico / MILLION;
const TIMEOUT_MS = 8000;

/** COMPUTE_PROFIT_SHARE as millionths (0.3 -> 300000n); 0n when unset, malformed or outside 0..1. */
export function shareMillionths(env = {}) {
  const pico = parsePico(String(env.COMPUTE_PROFIT_SHARE ?? '').trim());
  if (pico === null || pico <= 0n || pico > PICO) return 0n;
  return pico / MILLION;
}

/** Is profit indexing configured at all (a share and a baseline)? */
export function configured(env = {}) {
  return shareMillionths(env) > 0n && parseUsdMicro(env.EQUITY_BASELINE_USD, null) !== null;
}

/** A reading that may raise the cap: read successfully, and recently. */
export function usable(reading, at) {
  if (!reading || reading.ok !== true) return false;
  const age = at - Number(reading.at);
  return Number.isFinite(age) && age >= -60000 && age <= MAX_AGE_MS;
}

/** Is it time to read the accounts again? */
export function stale(reading, at) {
  const age = at - Number(reading?.at);
  return !reading || !Number.isFinite(age) || age < -60000 || age >= CACHE_MS;
}

/**
 * The month's cap and its parts. `reading` is the last stored `readEquity` result (or null).
 * `{ capMicro, parts }`, where `parts` is what `/v1/health` reports.
 */
export function effectiveCap(env = {}, reading = null, at = Date.now()) {
  const base = monthCapMicro(env);
  const share = shareMillionths(env);
  const baseline = parseUsdMicro(env.EQUITY_BASELINE_USD, null);
  const ceiling = parseUsdMicro(env.FRONTIER_MONTH_MAX_USD, null);
  const parts = {
    base_cap_usd: formatUsd(base),
    share: String(env.COMPUTE_PROFIT_SHARE ?? ''),
    baseline_usd: baseline === null ? null : formatUsd(baseline),
    max_cap_usd: ceiling === null ? null : formatUsd(ceiling),
    equity_usd: null, kalshi_usd: null, alpaca_usd: null, profit_usd: '0.00', bonus_usd: '0.00',
    read_at: reading?.at ? new Date(Number(reading.at)).toISOString() : null,
    read_ok: reading ? reading.ok === true : null,
    reason: null,
  };
  if (share === 0n || baseline === null) return { capMicro: base, parts: { ...parts, reason: 'profit indexing is not configured' } };
  if (base <= 0n) return { capMicro: base, parts: { ...parts, reason: 'no frontier month is configured; profit does not create one' } };
  if (!usable(reading, at)) {
    const why = !reading ? 'the accounts have not been read yet'
      : reading.ok !== true ? `the accounts could not be read: ${String(reading.error || 'unknown').slice(0, 160)}`
      : 'the last reading of the accounts is too old';
    return { capMicro: base, parts: { ...parts, reason: `${why}; the cap is FRONTIER_MONTH_USD` } };
  }
  const kalshiMicro = BigInt(reading.kalshi_micro), alpacaMicro = BigInt(reading.alpaca_micro);
  const equity = kalshiMicro + alpacaMicro;
  const profit = equity > baseline ? equity - baseline : 0n;
  const bonus = profit * share / MILLION;  // rounded down: a raise never rounds in the floor's favour
  let cap = base + bonus;
  if (ceiling !== null && cap > ceiling) cap = ceiling > base ? ceiling : base;
  return {
    capMicro: cap,
    parts: {
      ...parts, equity_usd: formatUsd(equity), kalshi_usd: formatUsd(kalshiMicro), alpaca_usd: formatUsd(alpacaMicro),
      profit_usd: formatUsd(profit), bonus_usd: formatUsd(cap - base),
      reason: profit > 0n ? (cap - base < bonus ? 'profit above the baseline, held to FRONTIER_MONTH_MAX_USD' : 'profit above the baseline')
        : 'no profit above the baseline',
    },
  };
}

/** Whole-account dollars: a decimal-dollar field if present, else integer cents. Null if neither. */
function kalshiMicro(dollars, cents) {
  const fromDollars = dollars === undefined || dollars === null ? null : parsePico(String(dollars));
  if (fromDollars !== null) return fromDollars < 0n ? null : floorMicro(fromDollars);
  if (Number.isSafeInteger(cents) && cents >= 0) return BigInt(cents) * 10000n;
  return null;
}

async function getJson(fetcher, url, headers) {
  const response = await fetcher(url, { method: 'GET', headers: { Accept: 'application/json', 'User-Agent': 'ltcm-gateway/1.0', ...headers },
    redirect: 'manual', signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

/**
 * Read both real accounts, read-only. `{ ok: true, at, kalshi_micro, alpaca_micro }` as strings of
 * micro-dollars, or `{ ok: false, at, error }`. Both must answer: half a reading is no reading.
 */
export async function readEquity(env, { fetcher = fetch, now = Date.now } = {}) {
  const at = now();
  try {
    if (!env.KALSHI_KEY_ID || !env.KALSHI_PRIVATE_KEY) throw new Error('kalshi is not configured');
    const headers = await kalshi.authHeaders({ keyId: env.KALSHI_KEY_ID, privateKeyPem: env.KALSHI_PRIVATE_KEY,
      method: 'GET', path: 'portfolio/balance', now: at });
    const row = await getJson(fetcher, kalshi.target('portfolio/balance'), headers).catch(error => { throw new Error(`kalshi balance: ${error.message}`); });
    const cash = kalshiMicro(row?.balance_dollars, row?.balance);
    if (cash === null) throw new Error('kalshi balance: no balance field');
    // Cash plus the positions' value (`portfolio_value` is the positions alone). Absent, it
    // counts as nothing: a reading errs low, never high.
    const positions = kalshiMicro(row?.portfolio_value_dollars, row?.portfolio_value) ?? 0n;

    const account = await getJson(fetcher, alpaca.target('v2/account'),
      alpaca.authHeaders({ keyId: env.ALPACA_KEY_ID, secretKey: env.ALPACA_SECRET_KEY }))
      .catch(error => { throw new Error(`alpaca account: ${error.message}`); });
    const equity = parsePico(String(account?.equity ?? ''));
    if (equity === null || equity < 0n) throw new Error('alpaca account: no equity field');
    return { ok: true, at, kalshi_micro: String(cash + positions), alpaca_micro: String(floorMicro(equity)) };
  } catch (error) {
    return { ok: false, at, error: String(error?.message || error?.name || 'read failed').slice(0, 200) };
  }
}

/** Read the accounts again when indexing is on and the stored reading is due. Never throws. */
export async function refresh(env, gate, { fetcher = fetch, now = Date.now } = {}) {
  if (!configured(env)) return null;
  try {
    const reading = await gate.equity();
    if (!stale(reading, now())) return reading;
    return await gate.recordEquity(await readEquity(env, { fetcher, now }));
  } catch {
    return null;  // the gate keeps whatever it had; an unusable reading gives the old cap
  }
}
