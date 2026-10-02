// The gate: the kill switch, the day's counters and the watchdog's record. All of it lives in one
// Durable Object, so a cap is checked and consumed in the same single-threaded step -- two desks
// submitting at once cannot both see the same remaining budget.
//
// `store` is a synchronous key/value view of the object's SQLite table. Keeping the decisions in
// this module rather than in the Durable Object class is what lets every rule below be tested
// without a Workers runtime.

import { caps, venueOrderCap } from './caps.mjs';
import { monthCapMicro } from './frontier.mjs';
import * as claude from './claude.mjs';
import * as equity from './equity.mjs';
import * as account from './account.mjs';
import { dayCap as pullDayCap, ENGINEER_PULLS_PER_DAY } from './github.mjs';
import { formatUsd, formatUsdMicro } from './money.mjs';
import { iso } from './http.mjs';
import * as typesafe from './typesafe.mjs';
import { DAY_CAP as webFetchDayCap } from './fetch.mjs';
import * as library from './library.mjs';
import { DAY_ZONE, MERGES_PER_DAY } from './merge.mjs';
import { DOCS_PER_DAY } from './desk.mjs';

/** The one Gate instance. A single object is what makes a cap a cap and not a per-isolate guess. */
export const GATE_OBJECT = 'gate-v1';

export const DAY_KEY = 'today';
export const KILL_KEY = 'kill';
export const WATCHDOG_KEY = 'watchdog';
export const SAIL_KEY = 'sail';
export const ALERTS_KEY = 'alerts';
const NOTICES_KEY = 'notices';
export const FRONTIER_KEY = 'frontier';
//: The frontier month that ended, as it stood when the next month's first call replaced it.
export const FRONTIER_PREVIOUS_KEY = 'frontier-previous';
export const PULLS_KEY = 'pulls';
export const TYPESAFE_KEY = 'typesafe-pilot-v1';
export const WEB_FETCH_KEY = 'web-fetch';
//: The research library's pace, lease and day (Sept 29, 2026; lib/library.mjs).
export const LIBRARY_KEY = 'library-v1';
//: Claude's funded meter (Sept 26, 2026, the swarm sprint): every call's cost or hold since the key was placed. Never reset.
export const CLAUDE_KEY = 'claude-funded-v1';
//: LTCM v3 (V3-A, WP8): the desk's docs commits and the engineer's merges, each a New York day's count and the last few;
//: the reviewer's verdicts by pull request and exact head commit; the admin log (kill, unkill, every admin-token call).
export const DOCS_KEY = 'github-docs-v1';
export const MERGES_KEY = 'github-merges-v1';
export const REVIEWS_KEY = 'github-reviews-v1';
//: The engineer's pull requests (V3-A, WP8b): a New York day's count of their own, apart from the other roles' UTC day.
export const ENGINEER_PULLS_KEY = 'github-engineer-pulls-v1';
export const ADMIN_LOG_KEY = 'admin-log-v1';
//: How many recent docs commits and merges the Gate keeps (and /v1/health shows); verdicts kept; admin entries kept.
const RECENT = 20;
const REVIEWS_KEPT = 200;
const ADMIN_KEPT = 50;
//: The admin log's entries /v1/health shows.
export const ADMIN_SHOWN = 20;
//: A funding notice's id is remembered this long (the House sends one per meter per ISO week; the gateway dedupes it
//: for a week and a day), every other notice's 48 hours.
const FUNDING_NOTICE_MS = 8 * 24 * 3600000;
const NOTICE_MS = 48 * 3600000;
const noticeKept = id => (typeof id === 'string' && /^funding/.test(id) ? FUNDING_NOTICE_MS : NOTICE_MS);

const read = (store, key, fallback) => {
  const raw = store.get(key);
  if (typeof raw !== 'string' || !raw) return fallback;
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
};
const write = (store, key, value) => store.set(key, JSON.stringify(value));

/** The floor's calendar day for an instant, e.g. `2026-09-15` in America/New_York. */
export function tradingDay(at, timezone) {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date(at));
  } catch {
    return new Date(at).toISOString().slice(0, 10);
  }
}

export function createGate({ store, env = {}, now = Date.now }) {
  const limits = caps(env);

  // The caps by maximum loss on the real Alpaca venue (Sept 26, 2026 (the options-swarm run, Wave 5); lib/account.mjs).
  const maxLoss = account.maxLossCaps(env);

  const counters = at => {
    const day = tradingDay(at, limits.timezone);
    const row = read(store, DAY_KEY, null);
    // A new trading day starts at zero; yesterday's row is simply replaced, never accumulated.
    if (!row || row.day !== day) return { day, orders: 0, notional: 0n, alpacaOpen: 0n, alpacaNotional: 0n };
    const notional = BigInt(row.notional || 0);
    const big = (value, fallback) => {
      try {
        return value === undefined || value === null ? fallback : BigInt(value);
      } catch {
        return fallback;
      }
    };
    // `alpaca_open`: today's OPENING maximum loss on the real Alpaca venue (Sept 26, 2026, Wave 5). A row written
    // before it existed, or one that cannot be read, counts its whole notional instead, which errs high.
    // `alpaca_notional`: everything the real Alpaca venue added to `notional` today, so that MAX_DAY_USD counts
    // Kalshi's alone (the review's m17). A row without it counts all of `notional` as Kalshi's, which errs high.
    return { day, orders: Number(row.orders) || 0, notional, alpacaOpen: big(row.alpaca_open, notional), alpacaNotional: big(row.alpaca_notional, 0n) };
  };

  const save = row => {
    if (typeof row.alpacaOpen !== 'bigint' || typeof row.alpacaNotional !== 'bigint') {
      throw new TypeError('a day row is saved with its Alpaca parts');
    }
    write(store, DAY_KEY, { day: row.day, orders: row.orders, notional: String(row.notional), alpaca_open: String(row.alpacaOpen),
      alpaca_notional: String(row.alpacaNotional) });
  };

  /** Today's notional on the venues MAX_DAY_USD caps: everything but the real Alpaca venue's (Kalshi's). */
  const kalshiNotional = row => (row.notional > row.alpacaNotional ? row.notional - row.alpacaNotional : 0n);

  /** How many of the day's orders may open: MAX_DAY_OPEN_ORDERS, never more than MAX_DAY_ORDERS. */
  const openOrdersCap = () => (maxLoss.maxDayOpenOrders < limits.maxDayOrders ? maxLoss.maxDayOpenOrders : limits.maxDayOrders);

  const killed = () => read(store, KILL_KEY, { on: false }).on === true;

  /** The reviewer's verdicts (V3-A, WP8), oldest first; a row that does not read is none. */
  const reviewRows = () => {
    const entries = read(store, REVIEWS_KEY, {})?.entries;
    return Array.isArray(entries) ? entries.filter(row => row && typeof row === 'object') : [];
  };

  /** One counted-a-day row (docs commits, merges; V3-A, WP8): today's count on New York's day and the last few. */
  const slotRow = (key, at) => {
    const row = read(store, key, {});
    const day = tradingDay(at, DAY_ZONE);
    return { day, count: row.day === day ? Number(row.count) || 0 : 0, next: Number(row.next) || 1,
      recent: Array.isArray(row.recent) ? row.recent.slice(-RECENT) : [] };
  };
  const slotReserve = (key, cap, capName, noun, at, what) => {
    const row = slotRow(key, at);
    if (row.count + 1 > cap) return { ok: false, status: 429, cap: capName, error: `Today's cap of ${cap} ${noun} is already reached.` };
    const id = row.next;
    write(store, key, { day: row.day, count: row.count + 1, next: id + 1,
      recent: [...row.recent, { id, at: iso(at), ...what, outcome: 'pending' }].slice(-RECENT) });
    return { ok: true, day: row.day, id, count: row.count + 1 };
  };
  // `refused` (GitHub answered no) and `existing` (a retry found what an earlier attempt made) made nothing, so their
  // place is given back; `committed`, `merged`, `opened` and `unknown` (nothing answered) keep it.
  const slotSettle = (key, { day, id, outcome, at, extra }) => {
    const row = slotRow(key, at);
    const known = ['committed', 'merged', 'opened', 'existing', 'refused', 'unknown'].includes(outcome) ? outcome : 'unknown';
    const giveBack = (known === 'refused' || known === 'existing') && day === row.day
      && row.recent.some(entry => entry.id === id && entry.outcome === 'pending');
    const recent = row.recent.map(entry => (entry.id === id ? { ...entry, outcome: known, ...extra } : entry));
    write(store, key, { day: row.day, count: giveBack ? Math.max(0, row.count - 1) : row.count, next: row.next, recent });
    return { ok: true, given_back: giveBack };
  };

  /** The last reading of the real account's equity (`account.readAccountEquity`), or null. */
  const accountReading = () => read(store, account.ACCOUNT_EQUITY_KEY, null);

  /** True once today's opening maximum loss on the real Alpaca venue has reached its cap (known only from a fresh reading). */
  const realDaySpent = (row, at) => {
    const equityMicro = account.freshEquity(accountReading(), at, maxLoss.maxAgeMs);
    return equityMicro !== null && row.alpacaOpen >= account.dayCapMicro(maxLoss, equityMicro);
  };

  /**
   * One order on the real Alpaca venue (Sept 26, 2026, Wave 5). An OPENING order (`exit` false) is judged by the stored
   * equity reading, which must be no older than EQUITY_CAP_MAX_AGE_MS here as well as in the router: a credit structure
   * (`credit`) only at CREDIT_MIN_EQUITY_USD or more; its maximum loss at most the lower of MAX_ORDER_MAX_LOSS_USD and
   * MAX_ORDER_EQUITY_SHARE of equity; the day's opening maximum loss with it at most MAX_DAY_EQUITY_SHARE of equity and
   * never above MAX_DAY_USD_ALPACA. An exit reads no equity and meets no dollar cap. Both count against MAX_DAY_ORDERS,
   * and no order opens once the day's orders reach MAX_DAY_OPEN_ORDERS, so the rest is kept for exits (the review's
   * C6/C10). MAX_ORDER_USD and MAX_DAY_USD are Kalshi's caps; this venue's orders are added to the day's notional as a
   * record, and kept apart in `alpaca_notional` so that they never spend Kalshi's day.
   */
  const reserveReal = ({ amount, at, exit, credit, row }) => {
    let equityMicro = null;
    if (!exit && row.orders >= openOrdersCap() && openOrdersCap() < limits.maxDayOrders) {
      return {
        ok: false, status: 403, cap: 'day_open_orders',
        error: `Today's ${row.orders} orders leave no room to open: the last ${limits.maxDayOrders - openOrdersCap()} of the ` +
               `day's ${limits.maxDayOrders} are kept for exits.`,
      };
    }
    if (!exit) {
      equityMicro = account.freshEquity(accountReading(), at, maxLoss.maxAgeMs);
      if (equityMicro === null) {
        return {
          ok: false, status: 503, cap: 'equity',
          error: `The real account's equity has not been read in the last ${Math.round(maxLoss.maxAgeMs / 1000)} seconds, ` +
                 'so an opening order cannot be sized against it: nothing was sent. Send it again.',
        };
      }
      if (credit && equityMicro < maxLoss.creditMinMicro) {
        return {
          ok: false, status: 403, cap: 'credit_equity',
          error: `A credit structure opens only while the real account's equity is at least $${formatUsd(maxLoss.creditMinMicro)}; ` +
                 `it reads $${account.formatUsdDown(equityMicro)}.`,
        };
      }
      const orderCap = account.orderCapMicro(maxLoss, equityMicro);
      if (amount > orderCap) {
        return {
          ok: false, status: 403, cap: 'order',
          error: `Order maximum loss $${formatUsd(amount)} exceeds the per-order cap of $${account.formatUsdDown(orderCap)} ` +
                 `(the lower of $${formatUsd(maxLoss.orderLimitMicro)} and ${account.percent(maxLoss.orderShare)} of ` +
                 `$${account.formatUsdDown(equityMicro)} equity).`,
        };
      }
    }
    if (row.orders + 1 > limits.maxDayOrders) {
      return {
        ok: false, status: 403, cap: 'day_orders',
        error: `Today's order count cap of ${limits.maxDayOrders} is already reached.`,
      };
    }
    if (!exit) {
      const dayCap = account.dayCapMicro(maxLoss, equityMicro);
      if (row.alpacaOpen + amount > dayCap) {
        return {
          ok: false, status: 403, cap: 'day_max_loss',
          error: `Order maximum loss $${formatUsd(amount)} would pass today's opening maximum-loss cap of ` +
                 `$${account.formatUsdDown(dayCap)} (already $${formatUsd(row.alpacaOpen)}).`,
        };
      }
    }
    const opening = exit ? 0n : amount;
    save({ day: row.day, orders: row.orders + 1, notional: row.notional + amount, alpacaOpen: row.alpacaOpen + opening,
      alpacaNotional: row.alpacaNotional + amount });
    return { ok: true, day: row.day, micro: String(amount), venue: 'alpaca', ...(exit ? {} : { opening: String(opening) }) };
  };

  return {
    caps: limits,

    killSwitch: () => killed(),

    /**
     * Engage or release the kill switch. Returns the new state. With `who` (`{ caller, route, method }`, the router's)
     * the change is written to the admin log too (V3-A, WP8): a release only once its entry is written (an entry that
     * cannot be written releases nothing), an engage whatever the log does (stopping is never gated).
     */
    setKill(on, at = now(), who = null) {
      const state = { on: on === true, at: iso(at) };
      const entry = who ? { caller: who.caller, action: on === true ? 'kill' : 'unkill', route: who.route, method: who.method, status: 200 } : null;
      if (entry && !state.on) this.adminRecord({ ...entry, at });
      write(store, KILL_KEY, state);
      if (entry && state.on) {
        try {
          this.adminRecord({ ...entry, at });
        } catch {
          // The switch is engaged; a log that cannot be written never undoes that.
        }
      }
      return state;
    },

    /**
     * One admin-log entry (V3-A, WP8): `caller` is `admin` (the owner's GATEWAY_ADMIN_TOKEN), `runtime` (the House's
     * GATEWAY_TOKEN) or `none` (no accepted token). A caller with no accepted token is counted, never listed, so a
     * stranger cannot push the owner's entries out of the list. No token, header or body is ever written here.
     */
    adminRecord({ caller, action, route, method, status, at = now() }) {
      const row = read(store, ADMIN_LOG_KEY, {});
      const counts = { total: 0, kill: 0, unkill: 0, admin_token: 0, unauthorized: 0, ...(row.counts || {}) };
      const who = ['admin', 'runtime'].includes(caller) ? caller : 'none';
      const what = ['kill', 'unkill'].includes(action) ? action : 'call';
      counts.total += 1;
      if (who === 'none') counts.unauthorized += 1;
      else if (what === 'kill' || what === 'unkill') counts[what] += 1;
      if (who === 'admin') counts.admin_token += 1;
      const entries = Array.isArray(row.entries) ? row.entries : [];
      const entry = {
        at: iso(at), caller: who, action: what,
        route: String(route || '').replace(/[^A-Za-z0-9/_.:-]/g, '?').slice(0, 80), method: String(method || '').replace(/[^A-Z]/g, '').slice(0, 8),
        status: Number.isInteger(status) ? status : null,
      };
      write(store, ADMIN_LOG_KEY, { counts, entries: who === 'none' ? entries.slice(-ADMIN_KEPT) : [...entries, entry].slice(-ADMIN_KEPT) });
      return entry;
    },

    /** The admin log for /v1/health: the counts since the log began and the last ADMIN_SHOWN entries, newest first. */
    adminLog() {
      const row = read(store, ADMIN_LOG_KEY, {});
      const counts = { total: 0, kill: 0, unkill: 0, admin_token: 0, unauthorized: 0, ...(row.counts || {}) };
      return { counts, last: (Array.isArray(row.entries) ? row.entries : []).slice(-ADMIN_SHOWN).reverse() };
    },

    /**
     * Consume `micro` dollars of today's budget for one order, or refuse.
     * Refusal is `{ ok: false, status, error }`; the caller forwards nothing. On the real Alpaca venue `micro` is an
     * open's maximum loss, judged by `reserveReal` (`credit` marks a credit structure's open, Sept 26, 2026, Wave 5).
     */
    reserve({ micro, at = now(), exit = false, venue = null, credit = false }) {
      if (killed()) {
        return { ok: false, status: 423, error: 'The kill switch is engaged; no orders are being forwarded.' };
      }
      const amount = BigInt(micro);
      if (amount <= 0n) return { ok: false, status: 400, cap: 'order', error: 'An order must have a positive notional.' };
      // The real Alpaca venue is capped by maximum loss against its own equity (Sept 26, 2026, Wave 5).
      if (venue === 'alpaca') return reserveReal({ amount, at, exit: exit === true, credit: credit === true, row: counters(at) });
      // A venue may carry a tighter per-order cap than the floor's (`MAX_ORDER_USD_<VENUE>`):
      // the accounts are a few hundred dollars each, and one order must never be one account.
      const venueCap = venueOrderCap(env, venue);
      const orderCap = venueCap !== null && venueCap < limits.maxOrderMicro ? venueCap : limits.maxOrderMicro;
      if (!exit && amount > orderCap) {
        return {
          ok: false, status: 403, cap: 'order',
          error: `Order notional $${formatUsd(amount)} exceeds the per-order cap of $${formatUsd(orderCap)}.`,
        };
      }
      const row = counters(at);
      if (row.orders + 1 > limits.maxDayOrders) {
        return {
          ok: false, status: 403, cap: 'day_orders',
          error: `Today's order count cap of ${limits.maxDayOrders} is already reached.`,
        };
      }
      const spent = kalshiNotional(row);
      if (!exit && spent + amount > limits.maxDayMicro) {
        return {
          ok: false, status: 403, cap: 'day_notional',
          error: `Order notional $${formatUsd(amount)} would pass today's cap of $${formatUsd(limits.maxDayMicro)} ` +
                 `(already $${formatUsd(spent)}).`,
        };
      }
      save({ day: row.day, orders: row.orders + 1, notional: row.notional + amount, alpacaOpen: row.alpacaOpen,
        alpacaNotional: row.alpacaNotional });
      return { ok: true, day: row.day, micro: String(amount) };
    },

    /**
     * Give back a reservation. Only ever called when the forward never reached the venue, so no
     * order can exist: a venue that answered at all keeps its reservation, because an unconfirmed
     * write is an order until reconciliation says otherwise.
     */
    refund({ day, micro, opening = null, venue = null, at = now() }) {
      const row = counters(at);
      if (row.day !== day) return { ok: false };
      const amount = BigInt(micro);
      // An opening reservation on the real Alpaca venue gives its maximum loss back to the day's opening cap too, and
      // any Alpaca reservation its notional back to the Alpaca record (never to Kalshi's day).
      const open = opening === null || opening === undefined ? 0n : BigInt(opening);
      const alpaca = venue === 'alpaca' ? amount : 0n;
      save({
        day: row.day,
        orders: Math.max(0, row.orders - 1),
        notional: row.notional > amount ? row.notional - amount : 0n,
        alpacaOpen: row.alpacaOpen > open ? row.alpacaOpen - open : 0n,
        alpacaNotional: row.alpacaNotional > alpaca ? row.alpacaNotional - alpaca : 0n,
      });
      return { ok: true };
    },

    /**
     * The frontier model's month. `frontierReserve` holds a call's worst-case cost against the
     * month's budget or refuses; `frontierSettle` replaces the hold with what the call cost.
     * A month is a UTC calendar month and starts at zero.
     *
     * `spent` is every call's cost or hold. `inflight` (Sept 24, 2026) is the part of it that is
     * still a hold: calls reserved and not yet settled, and calls cut off before they could settle
     * (a deploy or a crash mid-call), whose worst case stays in `spent` for good. `spent` falls
     * whenever a call settles below its worst case; `spent - inflight`, what is settled, rises,
     * except once: a hold the code before Sept 24, 2026 reserved was never counted in flight, so
     * when it settles below its worst case the settled figure falls by the difference. The House
     * meters OpenAI with both and keeps the highest settled figure (league/campaigns.py
     * `observe_month`).
     */
    frontierMonth(at = now()) {
      const month = new Date(at).toISOString().slice(0, 7);
      const row = read(store, FRONTIER_KEY, null);
      return row && row.month === month
        ? { month, spent: BigInt(row.spent || 0), inflight: BigInt(row.inflight || 0), calls: Number(row.calls) || 0,
          agents: row.agents && typeof row.agents === 'object' ? row.agents : {} }
        : { month, spent: 0n, inflight: 0n, calls: 0, agents: {} };
    },

    /**
     * The month before this one, as it stood when it ended: its `spent` and what of it was
     * settled, or null. The House carries it into its OpenAI meter, so the calls of a month's last
     * minutes are not lost when the month starts again at zero. Until the new month's first call
     * the stored row is still the old month; that call keeps it under `FRONTIER_PREVIOUS_KEY`.
     */
    frontierPrevious(at = now()) {
      const month = new Date(at).toISOString().slice(0, 7);
      const row = read(store, FRONTIER_KEY, null);
      const last = row && typeof row.month === 'string' && row.month < month ? row : read(store, FRONTIER_PREVIOUS_KEY, null);
      if (!last || typeof last.month !== 'string' || last.month >= month) return null;
      const spent = BigInt(last.spent || 0), inflight = BigInt(last.inflight || 0);
      return { month: last.month, spent, settled: spent > inflight ? spent - inflight : 0n };
    },

    /** The last reading of the real accounts (`equity.readEquity`), or null. */
    equity: () => read(store, equity.EQUITY_KEY, null),

    /** The last reading of the real Alpaca account's equity for the caps by maximum loss, or null (Sept 26, 2026, Wave 5). */
    accountEquity: () => accountReading(),

    recordAccountEquity(reading) {
      const row = reading && typeof reading === 'object' ? reading : { ok: false, at: now(), error: 'no reading' };
      const at = Number(row.at);
      const clean = row.ok === true && Number.isFinite(at) && /^-?\d{1,18}$/.test(String(row.equity_micro))
        ? { ok: true, at, equity_micro: String(row.equity_micro) }
        : { ok: false, at: Number.isFinite(at) ? at : now(), error: String(row.error || 'unreadable').slice(0, 200) };
      write(store, account.ACCOUNT_EQUITY_KEY, clean);
      return clean;
    },

    /** What `/v1/health` reports of the caps by maximum loss in force now (Sept 26, 2026, Wave 5). */
    maxLossStatus(at = now()) {
      const row = counters(at);
      const reading = accountReading();
      const equityMicro = account.freshEquity(reading, at, maxLoss.maxAgeMs);
      const stamp = Number(reading?.at);
      const readable = reading?.ok === true && /^-?\d{1,18}$/.test(String(reading.equity_micro));
      return {
        venue: 'alpaca',
        equity: {
          usd: readable ? account.formatUsdDown(BigInt(reading.equity_micro)) : null,
          read_at: Number.isFinite(stamp) ? iso(stamp) : null,
          age_seconds: Number.isFinite(stamp) ? Math.round((at - stamp) / 1000) : null,
          ok: reading ? reading.ok === true : null,
          error: reading && reading.ok !== true ? String(reading.error || 'unreadable') : null,
          fresh: equityMicro !== null,
          max_age_seconds: Math.round(maxLoss.maxAgeMs / 1000),
        },
        // Null while there is no fresh reading: then no opening order is admitted at all.
        order_cap_usd: equityMicro === null ? null : account.formatUsdDown(account.orderCapMicro(maxLoss, equityMicro)),
        max_order_max_loss_usd: formatUsd(maxLoss.orderLimitMicro),
        order_equity_share: account.shareText(maxLoss.orderShare),
        day_open_max_loss_usd: formatUsd(row.alpacaOpen),
        day_open_cap_usd: equityMicro === null ? null : account.formatUsdDown(account.dayCapMicro(maxLoss, equityMicro)),
        day_equity_share: account.shareText(maxLoss.dayShare),
        max_day_usd_alpaca: formatUsd(maxLoss.dayLimitMicro),
        opens_admitted: equityMicro !== null && !killed() && row.orders < openOrdersCap(),
        credit_opens_admitted: equityMicro !== null && equityMicro >= maxLoss.creditMinMicro && !killed() && row.orders < openOrdersCap(),
        credit_min_equity_usd: formatUsd(maxLoss.creditMinMicro),
        orders_today: row.orders,
        max_day_open_orders: openOrdersCap(),
        max_day_orders: limits.maxDayOrders,
      };
    },

    recordEquity(reading) {
      const row = reading && typeof reading === 'object' ? reading : { ok: false, at: now(), error: 'no reading' };
      const clean = row.ok === true && /^\d+$/.test(String(row.kalshi_micro)) && /^\d+$/.test(String(row.alpaca_micro))
        ? { ok: true, at: Number(row.at), kalshi_micro: String(row.kalshi_micro), alpaca_micro: String(row.alpaca_micro) }
        : { ok: false, at: Number(row.at) || now(), error: String(row.error || 'unreadable').slice(0, 200) };
      write(store, equity.EQUITY_KEY, clean);
      return clean;
    },

    /**
     * The month's cap: FRONTIER_MONTH_USD raised by a share of verified profit on the real accounts
     * (`equity.effectiveCap`), and exactly FRONTIER_MONTH_USD whenever that profit is not known.
     */
    frontierCap(at = now()) {
      return equity.effectiveCap(env, this.equity(), at);
    },

    frontierReserve({ micro, at = now() }) {
      const cap = this.frontierCap(at).capMicro;
      const amount = BigInt(micro);
      if (cap <= 0n) return { ok: false, status: 403, error: 'No frontier budget is configured.' };
      if (amount <= 0n) return { ok: false, status: 400, error: 'A call must have a positive worst-case cost.' };
      const row = this.frontierMonth(at);
      if (row.spent + amount > cap) {
        return {
          ok: false, status: 402, cap: 'frontier_month',
          error: `This call could cost $${formatUsd(amount)}; the month has $${formatUsd(cap > row.spent ? cap - row.spent : 0n)} left of $${formatUsd(cap)}.`,
        };
      }
      const stored = read(store, FRONTIER_KEY, null);
      if (stored && typeof stored.month === 'string' && stored.month !== row.month) write(store, FRONTIER_PREVIOUS_KEY, stored);
      write(store, FRONTIER_KEY, { month: row.month, spent: String(row.spent + amount), inflight: String(row.inflight + amount),
        calls: row.calls, agents: row.agents });
      // `tracked`: this hold is counted in flight, and its settle must release it from there.
      return { ok: true, month: row.month, micro: String(amount), tracked: true };
    },

    frontierSettle({ month, reserved, actual, agent = null, tracked = false, at = now() }) {
      const row = this.frontierMonth(at);
      if (row.month !== month) return { ok: false };
      const held = BigInt(reserved);
      // A call whose cost cannot be read keeps its whole reservation: unknown is not free.
      const cost = actual === null || actual === undefined ? held : BigInt(actual);
      const spent = row.spent - held + cost;
      // Only a hold reserved as tracked leaves the in-flight figure: a call the code before Sept 24,
      // 2026 reserved was never counted there, and an invocation of that code passes no `tracked`.
      const inflight = tracked === true ? (row.inflight > held ? row.inflight - held : 0n) : row.inflight;
      const agents = { ...row.agents };
      const name = typeof agent === 'string' && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(agent) ? agent : 'unattributed';
      agents[name] = String(BigInt(agents[name] || 0) + cost);
      write(store, FRONTIER_KEY, { month: row.month, spent: String(spent > 0n ? spent : 0n), inflight: String(inflight),
        calls: row.calls + 1, agents });
      return { ok: true, cost_usd: formatUsdMicro(cost) };
    },

    /**
     * Claude's funded meter (Sept 26, 2026, the swarm sprint; lib/claude.mjs). Unlike the frontier's month it never
     * starts again: CLAUDE_USD is what the owner funded, and `spent` is every call's cost or hold against it. `inflight`
     * is the part of `spent` still held. Each hold is kept by id (`holds`: its micro-dollars, when, and the House's
     * X-LTCM-Request id): a hold with no settlement after `claude.STALE_HOLD_MS` (the Worker died between reserve and
     * settle) is released to zero by the sweep, so a lost settlement never shrinks the funded total for good; a
     * settlement that arrives after its sweep still books its cost. `recent` is what became of the House's last requests
     * (held, settled, unknown, released), which the House reads to true up its own holds (`GET /v1/claude/request/<id>`).
     * `roles` and `agents` file each settled cost; `stops` and `geos` count the answers by stop reason and inference geo.
     */
    claudeMeter() {
      const row = read(store, CLAUDE_KEY, null) || {};
      const big = value => { try { return BigInt(value || 0); } catch { return 0n; } };
      const table = value => (value && typeof value === 'object' && !Array.isArray(value) ? value : {});
      return { spent: big(row.spent), inflight: big(row.inflight), calls: Number(row.calls) || 0, seq: Number(row.seq) || 0,
        agents: table(row.agents), roles: table(row.roles), stops: table(row.stops), geos: table(row.geos), holds: table(row.holds),
        recent: table(row.recent), swept: Number(row.swept) || 0, swept_micro: big(row.swept_micro),
        overruns: Number(row.overruns) || 0, overrun_micro: big(row.overrun_micro) };
    },

    _claudeWrite(row) {
      const recent = Object.entries(row.recent).sort((a, b) => (Number(b[1]?.at) || 0) - (Number(a[1]?.at) || 0)).slice(0, claude.RECENT_REQUESTS);
      write(store, CLAUDE_KEY, { spent: String(row.spent > 0n ? row.spent : 0n), inflight: String(row.inflight > 0n ? row.inflight : 0n),
        calls: row.calls, seq: row.seq, agents: row.agents, roles: row.roles, stops: row.stops, geos: row.geos, holds: row.holds,
        recent: Object.fromEntries(recent), swept: row.swept, swept_micro: String(row.swept_micro),
        overruns: row.overruns, overrun_micro: String(row.overrun_micro) });
    },

    /** Release every hold older than `claude.STALE_HOLD_MS` that no settlement replaced. Returns how many. */
    claudeSweep({ at = now() } = {}) {
      const row = this.claudeMeter();
      let n = 0;
      for (const [id, hold] of Object.entries(row.holds)) {
        if (!(at - Number(hold?.at) > claude.STALE_HOLD_MS)) continue;
        let micro = 0n;
        try { micro = BigInt(hold.micro); } catch { micro = 0n; }
        row.spent -= micro;
        row.inflight -= micro;
        row.swept += 1;
        row.swept_micro += micro;
        delete row.holds[id];
        if (hold.request) row.recent[hold.request] = { state: 'released', cost: '0', at };
        n += 1;
      }
      if (n) this._claudeWrite(row);
      return n;
    },

    /** Hold a Claude call's worst case against the funded total, or refuse. The kill switch stops Claude calls too. */
    claudeReserve({ micro, request = null, at = now() }) {
      if (killed()) return { ok: false, status: 423, cap: 'kill_switch', error: 'The kill switch is engaged; no Claude calls are being made.' };
      const cap = claude.capMicro(env);
      if (cap <= 0n) return { ok: false, status: 403, cap: 'claude_funded', error: 'No Claude budget is configured.' };
      const amount = BigInt(micro);
      if (amount <= 0n) return { ok: false, status: 400, error: 'A call must have a positive worst-case cost.' };
      this.claudeSweep({ at });
      const row = this.claudeMeter();
      if (row.spent + amount > cap) {
        return {
          ok: false, status: 402, cap: 'claude_funded',
          error: `This call could cost $${formatUsdMicro(amount)}; $${formatUsdMicro(cap > row.spent ? cap - row.spent : 0n)} is left of the $${formatUsd(cap)} funded.`,
        };
      }
      row.seq += 1;
      const id = `c${row.seq}`;
      const tag = claude.requestId(request);
      row.holds[id] = { micro: String(amount), at, ...(tag ? { request: tag } : {}) };
      if (tag) row.recent[tag] = { state: 'held', at };
      row.spent += amount;
      row.inflight += amount;
      this._claudeWrite(row);
      return { ok: true, micro: String(amount), id };
    },

    /**
     * Replace hold `id` with what the call cost (`actual`, micro-dollars); null keeps the whole hold as spent: unknown is
     * not free. A hold the sweep already released books only the settlement's cost (its worst case when unknown). A cost
     * above its own hold is an OVERRUN (Sept 29, 2026): the worst case failed to bound the call. It is booked in full and
     * counted (`overruns`, `overrun_usd` in `/v1/health`), and the House pauses its Claude research band on one.
     */
    claudeSettle({ id = null, reserved, actual, agent = null, role = null, stop = null, geo = null, at = now() }) {
      const row = this.claudeMeter();
      const hold = id !== null && Object.hasOwn(row.holds, id) ? row.holds[id] : null;
      const held = hold ? BigInt(hold.micro) : 0n;
      const cost = actual === null || actual === undefined ? BigInt(reserved) : BigInt(actual);
      if (hold) delete row.holds[id];
      if (hold && cost > held) {
        row.overruns += 1;
        row.overrun_micro += cost - held;
      }
      row.spent = row.spent - held + cost;
      row.inflight -= held;
      row.calls += 1;
      const slug = value => (typeof value === 'string' && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(value) ? value : 'unattributed');
      const add = (tableRow, name) => ({ ...tableRow, [name]: String(BigInt(tableRow[name] || 0) + cost) });
      row.agents = add(row.agents, slug(agent));
      row.roles = add(row.roles, slug(role));
      const stopName = typeof stop === 'string' && /^[a-z0-9_]{1,32}$/.test(stop) ? stop : 'none';
      row.stops = { ...row.stops, [stopName]: (Number(row.stops[stopName]) || 0) + 1 };
      if (typeof geo === 'string' && /^[a-z0-9_-]{1,16}$/.test(geo)) row.geos = { ...row.geos, [geo]: (Number(row.geos[geo]) || 0) + 1 };
      if (hold?.request) {
        row.recent[hold.request] = { state: actual === null || actual === undefined ? 'unknown' : 'settled', cost: String(cost), at };
      }
      this._claudeWrite(row);
      return { ok: true, cost_usd: formatUsdMicro(cost) };
    },

    /** What became of the House's request `request` (its X-LTCM-Request id): held, settled, unknown, released or absent. */
    claudeRequest(request) {
      const tag = claude.requestId(request);
      const entry = tag ? this.claudeMeter().recent[tag] : null;
      if (!entry) return { request: tag, state: 'absent' };
      let cost = null;
      try { cost = entry.cost === undefined ? null : formatUsdMicro(BigInt(entry.cost)); } catch { cost = null; }
      return { request: tag, state: entry.state, cost_usd: cost };
    },

    /** What `/v1/health` reports of Claude: the funded total, what is spent and held, and by whom. */
    claudeStatus(at = now()) {
      const row = this.claudeMeter();
      const cap = claude.capMicro(env);
      const usd = table => Object.fromEntries(Object.entries(table).map(([name, value]) => {
        try { return [name, formatUsdMicro(BigInt(value))]; } catch { return [name, null]; }
      }));
      const holds = Object.values(row.holds);
      return {
        // `cap_usd` is the owner's funded total, not a monthly allowance; `spent_usd` includes the holds in flight.
        funded: true, cap_usd: formatUsd(cap), spent_usd: formatUsdMicro(row.spent),
        settled_usd: formatUsdMicro(row.spent > row.inflight ? row.spent - row.inflight : 0n), inflight_usd: formatUsdMicro(row.inflight),
        remaining_usd: formatUsdMicro(cap > row.spent ? cap - row.spent : 0n), calls: row.calls,
        holds: holds.length, stale_holds: holds.filter(hold => at - Number(hold?.at) > claude.STALE_HOLD_MS).length,
        swept: row.swept, swept_usd: formatUsdMicro(row.swept_micro),
        overruns: row.overruns, overrun_usd: formatUsdMicro(row.overrun_micro),
        models: Object.keys(claude.priceTable(env)), configured: typeof env.CLAUDE_API_KEY === 'string' && env.CLAUDE_API_KEY.length > 0,
        by_role: usd(row.roles), by_agent: usd(row.agents), stops: row.stops, geos: row.geos,
      };
    },

    // Pilot commitments never reset with a calendar period or a deployment. An accepted id
    // is never sent upstream a second time, even after an interrupted/ambiguous response.
    typesafeStatus() {
      const row = read(store, TYPESAFE_KEY, { spent: '0', calls: 0, pending: 0, breaches: 0 });
      return { ...row, spent_usd: typesafe.money(row.spent), cap_usd: typesafe.money(typesafe.capMicro(env)),
        max_calls: typesafe.MAX_CALLS, persistent: env.TYPESAFE_PERSISTENT === 'true',
        ends: env.TYPESAFE_PERSISTENT === 'true' ? null : env.TYPESAFE_PILOT_END || null, model: typesafe.MODEL };
    },

    typesafeReserve({ id, digest, at = now() }) {
      if (typeof id !== 'string' || !/^[A-Za-z0-9:_-]{1,128}$/.test(id)
          || typeof digest !== 'string' || !/^[a-f0-9]{64}$/.test(digest)) {
        return { ok: false, status: 400, error: 'A stable request identity and digest are required.' };
      }
      const prior = read(store, `${TYPESAFE_KEY}:${id}`, null);
      if (prior) return { ok: false, status: 409, error: prior.digest === digest
        ? 'This request was already accepted; it will not be billed again.' : 'This request identity has different content.' };
      const end = Date.parse(env.TYPESAFE_PILOT_END || '');
      const cap = typesafe.capMicro(env), row = this.typesafeStatus();
      const windowOpen = env.TYPESAFE_PERSISTENT === 'true' || (Number.isFinite(end) && at < end);
      if (!windowOpen || cap <= 0n || row.breaches
          || row.calls >= typesafe.MAX_CALLS || BigInt(row.spent) + typesafe.RESERVATION_MICRO > cap) {
        return { ok: false, status: 402, cap: 'typesafe_pilot', error: 'The funded TypeSafe pilot allowance is unavailable.' };
      }
      write(store, TYPESAFE_KEY, { spent: String(BigInt(row.spent) + typesafe.RESERVATION_MICRO),
        calls: row.calls + 1, pending: row.pending + 1, breaches: row.breaches });
      write(store, `${TYPESAFE_KEY}:${id}`, { digest, at, status: 'pending' });
      return { ok: true, id, reserved: String(typesafe.RESERVATION_MICRO) };
    },

    typesafeSettle({ id, actual }) {
      const request = read(store, `${TYPESAFE_KEY}:${id}`, null);
      if (!request || request.status !== 'pending') return { ok: false };
      const cost = actual === null || actual === undefined ? typesafe.RESERVATION_MICRO : BigInt(actual);
      if (cost < 0n) return { ok: false };
      const row = this.typesafeStatus();
      write(store, TYPESAFE_KEY, { spent: String(BigInt(row.spent) - typesafe.RESERVATION_MICRO + cost),
        calls: row.calls, pending: row.pending - 1,
        breaches: row.breaches + (cost > typesafe.RESERVATION_MICRO ? 1 : 0) });
      write(store, `${TYPESAFE_KEY}:${id}`, { ...request, status: actual === null || actual === undefined ? 'unknown' : 'settled', cost: String(cost) });
      return { ok: true, cost_usd: typesafe.money(cost), cost_known: actual !== null && actual !== undefined };
    },

    /**
     * Pull requests opened today. The day is a UTC calendar day, GitHub's own, and starts at
     * zero. `pullReserve` takes one of the day's places or refuses, in the same step, so two
     * proposals at once cannot both take the last; `pullRefund` gives a place back, and is only
     * ever called for an attempt that made no new branch.
     */
    pullsToday(at = now()) {
      const row = read(store, PULLS_KEY, {});
      return row.day === iso(at).slice(0, 10) ? Number(row.count) || 0 : 0;
    },

    pullReserve({ at = now() } = {}) {
      const cap = pullDayCap(env);
      const count = this.pullsToday(at);
      if (count + 1 > cap) {
        return { ok: false, status: 429, cap: 'github_day', error: `Today's cap of ${cap} pull requests is already reached.` };
      }
      const day = iso(at).slice(0, 10);
      write(store, PULLS_KEY, { day, count: count + 1 });
      return { ok: true, day, count: count + 1 };
    },

    pullRefund({ day, at = now() } = {}) {
      if (day !== iso(at).slice(0, 10)) return { ok: false };
      write(store, PULLS_KEY, { day, count: Math.max(0, this.pullsToday(at) - 1) });
      return { ok: true };
    },

    /**
     * The desk's docs commits (`docsReserve`, cap DOCS_PER_DAY) and the engineer's merges (`mergeReserve`, cap
     * MERGES_PER_DAY), each counted on New York's day (V3-A, WP8). A reserve takes one of the day's places or refuses
     * in the same step, so two at once cannot both take the last; its settle records what became of it, and gives the
     * place back only when GitHub answered no (`refused`): an attempt nothing answered (`unknown`) may have committed
     * or merged, so it stays counted.
     */
    docsToday(at = now()) { return slotRow(DOCS_KEY, at).count; },
    docsReserve({ path = null, at = now() } = {}) {
      return slotReserve(DOCS_KEY, DOCS_PER_DAY, 'docs_day', 'docs commits', at, { path: typeof path === 'string' ? path.slice(0, 120) : null });
    },
    docsSettle({ day, id, outcome, commit = null, at = now() } = {}) {
      return slotSettle(DOCS_KEY, { day, id, outcome, at, extra: { commit: typeof commit === 'string' ? commit.slice(0, 64) : null } });
    },
    mergesToday(at = now()) { return slotRow(MERGES_KEY, at).count; },
    mergeReserve({ pr = null, sha = null, at = now() } = {}) {
      return slotReserve(MERGES_KEY, MERGES_PER_DAY, 'merge_day', 'merges', at, { pr, sha: typeof sha === 'string' ? sha.slice(0, 64) : null });
    },
    mergeSettle({ day, id, outcome, merge_sha = null, at = now() } = {}) {
      return slotSettle(MERGES_KEY, { day, id, outcome, at, extra: { merge_sha: typeof merge_sha === 'string' ? merge_sha.slice(0, 64) : null } });
    },
    /**
     * The engineer's pull requests (V3-A, WP8b; cap ENGINEER_PULLS_PER_DAY a New York day, apart from `pullReserve`'s
     * UTC day of the other roles). The settle's outcome is `opened` (a new branch), `existing` (a retry that found its
     * branch and pull request: given back), `refused` (GitHub answered no before any branch: given back) or `unknown`
     * (a branch may exist: kept).
     */
    engineerPullsToday(at = now()) { return slotRow(ENGINEER_PULLS_KEY, at).count; },
    engineerPullReserve({ branch = null, at = now() } = {}) {
      return slotReserve(ENGINEER_PULLS_KEY, ENGINEER_PULLS_PER_DAY, 'engineer_day', 'engineer pull requests', at,
        { branch: typeof branch === 'string' ? branch.slice(0, 120) : null });
    },
    engineerPullSettle({ day, id, outcome, pr = null, at = now() } = {}) {
      return slotSettle(ENGINEER_PULLS_KEY, { day, id, outcome, at, extra: { pr: Number.isSafeInteger(pr) ? pr : null } });
    },

    /**
     * The reviewer's verdict on one pull request at one exact head commit (V3-A, WP8): `reject` when a reject is
     * recorded (it is final for that commit), else `approve` when an approve is, else null.
     */
    reviewFor({ pr, sha } = {}) {
      const rows = reviewRows().filter(row => row?.pr === pr && row?.sha === sha);
      const reject = rows.find(row => row.verdict === 'reject');
      const decided = reject || rows.find(row => row.verdict === 'approve');
      return decided ? { verdict: decided.verdict, at: decided.at, reasons: decided.reasons } : { verdict: null };
    },
    /** Record a verdict. An approve after a reject of the same commit is refused; the same verdict again is a no-op. */
    reviewRecord({ pr, sha, verdict, reasons = [], at = now() } = {}) {
      const entries = reviewRows();
      const held = this.reviewFor({ pr, sha });
      if (held.verdict === 'reject' && verdict === 'approve') {
        return { ok: false, status: 409, refused: 'review_rejected', error: 'That commit was rejected; a revision is a new commit, reviewed again.' };
      }
      if (held.verdict === verdict) return { ok: true, verdict, at: held.at, duplicate: true };
      const entry = { pr, sha, verdict, reasons: reasons.map(reason => String(reason).slice(0, 1000)).slice(0, 20), at: iso(at) };
      write(store, REVIEWS_KEY, { entries: [...entries, entry].slice(-REVIEWS_KEPT) });
      return { ok: true, verdict, at: entry.at };
    },

    /**
     * What /v1/health shows of the desk's docs commits, the engineer's pull requests and merges, and the reviews (V3-A,
     * WP8 and WP8b).
     */
    autonomyStatus(at = now()) {
      const docs = slotRow(DOCS_KEY, at);
      const pulls = slotRow(ENGINEER_PULLS_KEY, at);
      const merges = slotRow(MERGES_KEY, at);
      const reviews = reviewRows();
      return {
        day: docs.day,
        docs: { commits: docs.count, cap: DOCS_PER_DAY, recent: docs.recent.slice(-5).reverse() },
        engineer_pulls: { count: pulls.count, cap: ENGINEER_PULLS_PER_DAY, recent: pulls.recent.slice(-5).reverse() },
        merges: { count: merges.count, cap: MERGES_PER_DAY, recent: merges.recent.slice(-5).reverse() },
        reviews: { recorded: reviews.length, approve: reviews.filter(row => row.verdict === 'approve').length,
          reject: reviews.filter(row => row.verdict === 'reject').length },
      };
    },

    /**
     * Pages research read today through `/v1/web/fetch` (lib/fetch.mjs), the floor's UTC day: the
     * count, and by agent. `webFetchReserve` takes one of the day's `DAY_CAP` places or refuses, in
     * the same step. The kill switch is not consulted: a page moves no money.
     */
    webFetchDay(at = now()) {
      const day = iso(at).slice(0, 10);
      const row = read(store, WEB_FETCH_KEY, {});
      return row.day === day
        ? { day, count: Number(row.count) || 0, by_agent: row.by_agent && typeof row.by_agent === 'object' ? row.by_agent : {} }
        : { day, count: 0, by_agent: {} };
    },

    webFetchReserve({ at = now(), agent = null } = {}) {
      const row = this.webFetchDay(at);
      if (row.count + 1 > webFetchDayCap) {
        return { ok: false, status: 429, cap: 'web_fetch_day', error: `Today's cap of ${webFetchDayCap} web fetches is already reached.` };
      }
      const by = { ...row.by_agent };
      const name = typeof agent === 'string' && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(agent) ? agent : 'unattributed';
      // Bounded: past 200 names a day, the rest are counted together.
      const key = Object.hasOwn(by, name) || Object.keys(by).length < 200 ? name : 'other';
      by[key] = (Number(by[key]) || 0) + 1;
      write(store, WEB_FETCH_KEY, { day: row.day, count: row.count + 1, by_agent: by });
      return { ok: true, day: row.day, count: row.count + 1 };
    },

    /**
     * The research library's upstream pace (Sept 29, 2026; lib/library.mjs): arXiv's terms allow one request every three
     * seconds and one connection at a time, across every machine we control, and arxiv.org's robots.txt a crawl delay of
     * 15 s. One row holds the day's upstream count (a UTC day, by host and by role), each host's last start, the one lease
     * in flight and the backoff after a 429 or 503. The lease, the starts and the backoff outlive the day.
     */
    libraryRow(at = now()) {
      const day = iso(at).slice(0, 10);
      const plain = value => (value && typeof value === 'object' && !Array.isArray(value) ? value : {});
      const row = plain(read(store, LIBRARY_KEY, {}));  // a row of another shape reads as none, never a throw
      const today = row.day === day;
      return {
        day,
        upstream: today ? Number(row.upstream) || 0 : 0,
        by_host: today ? plain(row.by_host) : {},
        by_role: today ? plain(row.by_role) : {},
        last: plain(row.last),
        inflight: row.inflight && typeof row.inflight === 'object' && Number(row.inflight.expires) > at ? row.inflight : null,
        backoff_until: Number(row.backoff_until) || 0,
        backoff_why: typeof row.backoff_why === 'string' ? row.backoff_why : null,
        seq: Number(row.seq) || 0,
      };
    },

    /**
     * A turn for one upstream request to `host`, decided and booked in the same step: `{ go: true, id }` when no library
     * request is in flight on any host, the host's last start is SPACING_MS ago, no backoff runs and the day's count is
     * under its cap (LIBRARY_DAY_UPSTREAM); else `{ go: false, wait_ms }` with nothing booked, or the day's cap. A lease
     * never released expires at its start plus the host's fetch timeout plus LEASE_SLACK_MS.
     */
    libraryAcquire({ host, role = null } = {}) {
      const at = now();
      if (!library.HOSTS.includes(host)) return { go: false, refused: 'host' };
      const row = this.libraryRow(at);
      if (row.inflight) {
        // A waiter asks again no sooner than its own host's spacing allows a start (at most POLL_MS ahead), and each
        // second only while a turn could come sooner, so a lease on its own host costs about one ask in three seconds,
        // not three, of the object every order reserve also goes through (review of #447). A fixed POLL_MS for every
        // waiter slept past most releases (a fetch takes about a second) and made queued reads miss their budget.
        const spacing = (Number(row.last[host]) || 0) + library.SPACING_MS[host] - at;
        const wait = spacing > 1000 ? Math.min(library.POLL_MS, spacing) : 1000;
        return { go: false, wait_ms: Math.max(250, Math.min(wait, Number(row.inflight.expires) - at)) };
      }
      if (row.backoff_until > at) return { go: false, wait_ms: row.backoff_until - at, backoff: true };
      const since = at - (Number(row.last[host]) || 0);
      if (since < library.SPACING_MS[host]) return { go: false, wait_ms: library.SPACING_MS[host] - since };
      const cap = library.dayCap(env);
      if (row.upstream >= cap) {
        return { go: false, status: 429, cap: 'library_day', error: `Today's cap of ${cap} library requests to arXiv is already reached.` };
      }
      const id = row.seq + 1;
      const name = typeof role === 'string' && /^[a-z0-9][a-z0-9_-]{0,31}$/.test(role) ? role : 'unattributed';
      const byRole = { ...row.by_role };
      const roleKey = Object.hasOwn(byRole, name) || Object.keys(byRole).length < 20 ? name : 'other';
      byRole[roleKey] = (Number(byRole[roleKey]) || 0) + 1;
      write(store, LIBRARY_KEY, {
        day: row.day, seq: id, upstream: row.upstream + 1, by_host: { ...row.by_host, [host]: (Number(row.by_host[host]) || 0) + 1 },
        by_role: byRole, last: { ...row.last, [host]: at },
        inflight: { id, host, at, expires: at + library.FETCH_TIMEOUT_MS[host] + library.LEASE_SLACK_MS },
        backoff_until: row.backoff_until, backoff_why: row.backoff_why,
      });
      return { go: true, id, upstream: row.upstream + 1 };
    },

    /** The lease `id` given back; a 403, 429 or 503 from arXiv (`library.BACKOFF_STATUSES`) starts a backoff of at least
     * BACKOFF_MS (its Retry-After when longer). */
    libraryRelease({ id, status = 0, retry_after_ms = null } = {}) {
      const at = now();
      const row = this.libraryRow(at);
      const raw = read(store, LIBRARY_KEY, {});
      const stored = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
      const mine = Boolean(stored.inflight) && typeof stored.inflight === 'object' && stored.inflight.id === id;
      const next = { ...stored, inflight: mine ? null : stored.inflight };
      if (library.BACKOFF_STATUSES.includes(status)) {
        const pause = Math.max(Number(retry_after_ms) || 0, library.BACKOFF_MS);
        next.backoff_until = Math.max(row.backoff_until, at + pause);
        next.backoff_why = `arXiv answered ${status} at ${iso(at)}`;
      }
      write(store, LIBRARY_KEY, next);
      return { ok: mine };
    },

    /** The `library` block of /v1/health and /v1/research/health. A stored field of the wrong shape reads as null (a
     * lease without its start once made `iso` throw, and /v1/health with it: review of #428, gateway F2). */
    libraryStatus(at = now()) {
      const row = this.libraryRow(at);
      const stamp = ms => (Number.isFinite(ms) && Math.abs(ms) <= 8.64e15 ? iso(ms) : null);
      return {
        day: row.day, upstream: row.upstream, cap: library.dayCap(env), by_host: row.by_host, by_role: row.by_role,
        in_flight: row.inflight ? { host: row.inflight.host, since: stamp(Number(row.inflight.at)) } : null,
        backoff_until: row.backoff_until > at ? stamp(row.backoff_until) : null, backoff_why: row.backoff_until > at ? row.backoff_why : null,
        spacing_ms: library.SPACING_MS, served_through: library.LAST_DAY,
        terms: 'arXiv API: at most one request every 3 s and one connection at a time, across all our machines; arxiv.org robots.txt: Crawl-delay 15',
      };
    },

    watchdog: () => read(store, WATCHDOG_KEY, { last_check_at: null, last_action: null, last_action_at: null }),

    recordWatchdog(patch) {
      const merged = { ...read(store, WATCHDOG_KEY, {}), ...patch };
      write(store, WATCHDOG_KEY, merged);
      return merged;
    },

    /** What the last pass learned about Sail: the credit balance, the box, the last resume. */
    sail: () => read(store, SAIL_KEY, {}),

    recordSail(patch) {
      const merged = { ...read(store, SAIL_KEY, {}), ...patch };
      write(store, SAIL_KEY, merged);
      return merged;
    },

    alerts: () => read(store, ALERTS_KEY, {}),

    /** Trade notices sent today (the floor's day), so a bug cannot mail a thousand times. */
    noticesToday(at = now()) {
      const row = read(store, NOTICES_KEY, {});
      return row.day === tradingDay(at, limits.timezone) ? Number(row.count) || 0 : 0;
    },

    noticeDelivered(id, at = now()) {
      if (!id) return false;
      const row = read(store, NOTICES_KEY, {});
      const sent = row.delivered?.[id];
      return Number.isFinite(sent) && at - sent >= 0 && at - sent < noticeKept(id);
    },

    recordNotice(at = now(), id = null) {
      if (this.noticeDelivered(id, at)) return this.noticesToday(at);
      const count = this.noticesToday(at) + 1;
      const row = read(store, NOTICES_KEY, {});
      const delivered = Object.fromEntries(Object.entries(row.delivered || {}).filter(([key, stamp]) => at - stamp < noticeKept(key)).slice(-2000));
      if (id) delivered[id] = at;
      write(store, NOTICES_KEY, { day: tradingDay(at, limits.timezone), count, delivered });
      return count;
    },

    /** True when this kind of alert has not been sent inside `everyMs`. */
    alertDue(kind, at = now(), everyMs) {
      const sent = Date.parse(read(store, ALERTS_KEY, {})[kind]?.at || '');
      return !Number.isFinite(sent) || at - sent >= everyMs;
    },

    recordAlert(kind, at = now(), detail = null) {
      const merged = { ...read(store, ALERTS_KEY, {}), [kind]: { at: iso(at), ...(detail ? { detail } : {}) } };
      write(store, ALERTS_KEY, merged);
      return merged[kind];
    },

    /** True once the day's own caps leave no room for another order. */
    capsExhausted(at = now()) {
      const row = counters(at);
      return row.orders >= limits.maxDayOrders || kalshiNotional(row) >= limits.maxDayMicro || realDaySpent(row, at);
    },

    /** The `/v1/health` body. */
    status(at = now()) {
      const row = counters(at);
      const watch = read(store, WATCHDOG_KEY, {});
      const sail = read(store, SAIL_KEY, {});
      return {
        ok: true,
        kill_switch: killed(),
        today: { day: row.day, orders: row.orders, notional_usd: formatUsd(row.notional) },
        notices_today: this.noticesToday(at),
        caps: {
          max_order_usd: formatUsd(limits.maxOrderMicro),
          max_day_usd: formatUsd(limits.maxDayMicro),
          max_day_orders: limits.maxDayOrders,
          timezone: limits.timezone,
        },
        caps_exhausted: row.orders >= limits.maxDayOrders || kalshiNotional(row) >= limits.maxDayMicro || realDaySpent(row, at),
        // The caps by maximum loss on the real Alpaca venue, as they stand now (Sept 26, 2026, Wave 5).
        max_loss: this.maxLossStatus(at),
        frontier: (() => {
          const month = this.frontierMonth(at);
          const { capMicro, parts } = this.frontierCap(at);
          const previous = this.frontierPrevious(at);
          return {
            // `cap_usd` is the cap in force (the House mirrors it); `profit_index` says how it was reached.
            month: month.month, spent_usd: formatUsd(month.spent), cap_usd: formatUsd(capMicro), calls: month.calls,
            // What of `spent_usd` is settled and what is still a hold (`frontierMonth`), to the
            // microdollar: the House's OpenAI meter checks the one against its own settled costs.
            settled_usd: formatUsdMicro(month.spent > month.inflight ? month.spent - month.inflight : 0n),
            inflight_usd: formatUsdMicro(month.inflight),
            previous: previous ? { month: previous.month, spent_usd: formatUsd(previous.spent), settled_usd: formatUsdMicro(previous.settled) } : null,
            base_cap_usd: formatUsd(monthCapMicro(env, at)), profit_index: parts,
            by_agent: Object.fromEntries(Object.entries(month.agents).map(([name, value]) => [name, formatUsd(BigInt(value))])),
          };
        })(),
        typesafe: this.typesafeStatus(),
        claude: this.claudeStatus(at),
        github: { day: iso(at).slice(0, 10), pull_requests: this.pullsToday(at), cap: pullDayCap(env) },
        web_fetch: (() => {
          const row = this.webFetchDay(at);
          return { day: row.day, fetches: row.count, cap: webFetchDayCap, by_agent: row.by_agent };
        })(),
        // The research library's pace and day (Sept 29, 2026): read from this object's own row, no upstream call. A fault
        // here is the block's own answer, never /v1/health's: the House reads a failed health as the kill switch
        // engaged, so a library row must never halt trading (review of #428, gateway F2).
        library: (() => {
          try {
            return this.libraryStatus(at);
          } catch {
            return { error: 'library status unreadable' };
          }
        })(),
        watchdog: {
          last_check_at: watch.last_check_at ?? null,
          last_action: watch.last_action ?? null,
          last_action_at: watch.last_action_at ?? null,
          last_restart_at: watch.last_restart_at ?? null,
          published_at: watch.published_at ?? null,
          age_seconds: watch.age_seconds ?? null,
        },
        sail: {
          balance_usd: sail.balance_usd ?? null,
          spend_usd: sail.spend_usd ?? null,
          range: sail.range ?? null,
          box_status: sail.box_status ?? null,
          checked_at: sail.checked_at ?? null,
          last_resume_at: sail.last_resume_at ?? null,
          last_resume_state: sail.last_resume_state ?? null,
          // The runway the watchdog computed on its last pass: what the owner is warned by.
          reserve_usd: sail.reserve_usd ?? null,
          spendable_usd: sail.spendable_usd ?? null,
          burn_usd_per_day: sail.burn_usd_per_day ?? null,
          runway_days: sail.runway_days ?? null,
          run_out_at: sail.run_out_at ?? null,
        },
        alerts: read(store, ALERTS_KEY, {}),
        // V3-A (WP8): the desk's docs commits, the engineer's merges and reviews, and the admin log. Each block is read
        // under its own guard: a malformed row is that block's error, never a failed /v1/health (which the House reads
        // as the kill switch engaged).
        autonomy: guarded(() => this.autonomyStatus(at), 'autonomy'),
        admin_log: guarded(() => this.adminLog(), 'admin log'),
      };
    },
  };
}

const guarded = (read, what) => {
  try {
    return read();
  } catch {
    return { error: `${what} status unreadable` };
  }
};
