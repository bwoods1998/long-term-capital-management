// The gate: the kill switch, the day's counters and the watchdog's record. All of it lives in one
// Durable Object, so a cap is checked and consumed in the same single-threaded step -- two desks
// submitting at once cannot both see the same remaining budget.
//
// `store` is a synchronous key/value view of the object's SQLite table. Keeping the decisions in
// this module rather than in the Durable Object class is what lets every rule below be tested
// without a Workers runtime.

import { caps } from './caps.mjs';
import { monthCapMicro } from './frontier.mjs';
import * as account from './account.mjs';
import { dayCap as pullDayCap } from './github.mjs';
import { formatUsd, formatUsdMicro } from './money.mjs';
import { iso } from './http.mjs';

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

  /** How many of the day's orders may open: MAX_DAY_OPEN_ORDERS, never more than MAX_DAY_ORDERS. */
  const openOrdersCap = () => (maxLoss.maxDayOpenOrders < limits.maxDayOrders ? maxLoss.maxDayOpenOrders : limits.maxDayOrders);

  const killed = () => read(store, KILL_KEY, { on: false }).on === true;

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

    /** Engage or release the kill switch. Returns the new state. */
    setKill(on, at = now()) {
      const state = { on: on === true, at: iso(at) };
      write(store, KILL_KEY, state);
      return state;
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
      return { ok: false, status: 403, cap: 'venue', error: 'Only the real Alpaca options account is metered here.' };
    },

    /**
     * Give back a reservation. Only ever called when the forward never reached the venue, so no
     * order can exist: a venue that answered at all keeps its reservation, because an unconfirmed
     * write is an order until reconciliation says otherwise.
     */
    refund({ day, micro, opening = null, venue = null, at = now() }) {
      if (venue !== 'alpaca') return { ok: false };
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

    // Compute credit is owner-funded and expires at its explicit UTC month boundary.
    frontierCap(at = now()) {
      return { capMicro: monthCapMicro(env, at) };
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
      return Number.isFinite(sent) && at - sent >= 0 && at - sent < 48 * 3600000;
    },

    recordNotice(at = now(), id = null) {
      if (this.noticeDelivered(id, at)) return this.noticesToday(at);
      const count = this.noticesToday(at) + 1;
      const row = read(store, NOTICES_KEY, {});
      const delivered = Object.fromEntries(Object.entries(row.delivered || {}).filter(([, stamp]) => at - stamp < 48 * 3600000).slice(-2000));
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
      return row.orders >= limits.maxDayOrders || realDaySpent(row, at);
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
          max_day_orders: limits.maxDayOrders,
          timezone: limits.timezone,
        },
        caps_exhausted: row.orders >= limits.maxDayOrders || realDaySpent(row, at),
        // The caps by maximum loss on the real Alpaca venue, as they stand now (Sept 26, 2026, Wave 5).
        max_loss: this.maxLossStatus(at),
        frontier: (() => {
          const month = this.frontierMonth(at);
          const { capMicro } = this.frontierCap(at);
          const previous = this.frontierPrevious(at);
          return {
            // `cap_usd` is the cap in force (the House mirrors it); `profit_index` says how it was reached.
            month: month.month, spent_usd: formatUsd(month.spent), cap_usd: formatUsd(capMicro), calls: month.calls,
            // What of `spent_usd` is settled and what is still a hold (`frontierMonth`), to the
            // microdollar: the House's OpenAI meter checks the one against its own settled costs.
            settled_usd: formatUsdMicro(month.spent > month.inflight ? month.spent - month.inflight : 0n),
            inflight_usd: formatUsdMicro(month.inflight),
            previous: previous ? { month: previous.month, spent_usd: formatUsd(previous.spent), settled_usd: formatUsdMicro(previous.settled) } : null,
            base_cap_usd: formatUsd(monthCapMicro(env, at)),
            by_agent: Object.fromEntries(Object.entries(month.agents).map(([name, value]) => [name, formatUsd(BigInt(value))])),
          };
        })(),
        github: { day: iso(at).slice(0, 10), pull_requests: this.pullsToday(at), cap: pullDayCap(env) },
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
      };
    },
  };
}
