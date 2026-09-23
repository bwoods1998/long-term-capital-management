// The gate: the kill switch, the day's counters and the watchdog's record. All of it lives in one
// Durable Object, so a cap is checked and consumed in the same single-threaded step -- two desks
// submitting at once cannot both see the same remaining budget.
//
// `store` is a synchronous key/value view of the object's SQLite table. Keeping the decisions in
// this module rather than in the Durable Object class is what lets every rule below be tested
// without a Workers runtime.

import { caps, venueOrderCap } from './caps.mjs';
import { monthCapMicro } from './frontier.mjs';
import * as equity from './equity.mjs';
import { dayCap as pullDayCap } from './github.mjs';
import { formatUsd, formatUsdMicro } from './money.mjs';
import { iso } from './http.mjs';
import * as typesafe from './typesafe.mjs';

/** The one Gate instance. A single object is what makes a cap a cap and not a per-isolate guess. */
export const GATE_OBJECT = 'gate-v1';

export const DAY_KEY = 'today';
export const KILL_KEY = 'kill';
export const WATCHDOG_KEY = 'watchdog';
export const SAIL_KEY = 'sail';
export const ALERTS_KEY = 'alerts';
const NOTICES_KEY = 'notices';
export const FRONTIER_KEY = 'frontier';
export const PULLS_KEY = 'pulls';
export const TYPESAFE_KEY = 'typesafe-pilot-v1';

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

  const counters = at => {
    const day = tradingDay(at, limits.timezone);
    const row = read(store, DAY_KEY, null);
    // A new trading day starts at zero; yesterday's row is simply replaced, never accumulated.
    return row && row.day === day
      ? { day, orders: Number(row.orders) || 0, notional: BigInt(row.notional || 0) }
      : { day, orders: 0, notional: 0n };
  };

  const save = row => write(store, DAY_KEY, { day: row.day, orders: row.orders, notional: String(row.notional) });

  const killed = () => read(store, KILL_KEY, { on: false }).on === true;

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
     * Refusal is `{ ok: false, status, error }`; the caller forwards nothing.
     */
    reserve({ micro, at = now(), exit = false, venue = null }) {
      if (killed()) {
        return { ok: false, status: 423, error: 'The kill switch is engaged; no orders are being forwarded.' };
      }
      const amount = BigInt(micro);
      if (amount <= 0n) return { ok: false, status: 400, cap: 'order', error: 'An order must have a positive notional.' };
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
      if (!exit && row.notional + amount > limits.maxDayMicro) {
        return {
          ok: false, status: 403, cap: 'day_notional',
          error: `Order notional $${formatUsd(amount)} would pass today's cap of $${formatUsd(limits.maxDayMicro)} ` +
                 `(already $${formatUsd(row.notional)}).`,
        };
      }
      save({ day: row.day, orders: row.orders + 1, notional: row.notional + amount });
      return { ok: true, day: row.day, micro: String(amount) };
    },

    /**
     * Give back a reservation. Only ever called when the forward never reached the venue, so no
     * order can exist: a venue that answered at all keeps its reservation, because an unconfirmed
     * write is an order until reconciliation says otherwise.
     */
    refund({ day, micro, at = now() }) {
      const row = counters(at);
      if (row.day !== day) return { ok: false };
      const amount = BigInt(micro);
      save({
        day: row.day,
        orders: Math.max(0, row.orders - 1),
        notional: row.notional > amount ? row.notional - amount : 0n,
      });
      return { ok: true };
    },

    /**
     * The frontier model's month. `frontierReserve` holds a call's worst-case cost against the
     * month's budget or refuses; `frontierSettle` replaces the hold with what the call cost.
     * A month is a UTC calendar month and starts at zero.
     */
    frontierMonth(at = now()) {
      const month = new Date(at).toISOString().slice(0, 7);
      const row = read(store, FRONTIER_KEY, null);
      return row && row.month === month
        ? { month, spent: BigInt(row.spent || 0), calls: Number(row.calls) || 0, agents: row.agents && typeof row.agents === 'object' ? row.agents : {} }
        : { month, spent: 0n, calls: 0, agents: {} };
    },

    /** The last reading of the real accounts (`equity.readEquity`), or null. */
    equity: () => read(store, equity.EQUITY_KEY, null),

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
      write(store, FRONTIER_KEY, { month: row.month, spent: String(row.spent + amount), calls: row.calls, agents: row.agents });
      return { ok: true, month: row.month, micro: String(amount) };
    },

    frontierSettle({ month, reserved, actual, agent = null, at = now() }) {
      const row = this.frontierMonth(at);
      if (row.month !== month) return { ok: false };
      const held = BigInt(reserved);
      // A call whose cost cannot be read keeps its whole reservation: unknown is not free.
      const cost = actual === null || actual === undefined ? held : BigInt(actual);
      const spent = row.spent - held + cost;
      const agents = { ...row.agents };
      const name = typeof agent === 'string' && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(agent) ? agent : 'unattributed';
      agents[name] = String(BigInt(agents[name] || 0) + cost);
      write(store, FRONTIER_KEY, { month: row.month, spent: String(spent > 0n ? spent : 0n), calls: row.calls + 1, agents });
      return { ok: true, cost_usd: formatUsdMicro(cost) };
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
      return row.orders >= limits.maxDayOrders || row.notional >= limits.maxDayMicro;
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
        caps_exhausted: row.orders >= limits.maxDayOrders || row.notional >= limits.maxDayMicro,
        frontier: (() => {
          const month = this.frontierMonth(at);
          const { capMicro, parts } = this.frontierCap(at);
          return {
            // `cap_usd` is the cap in force (the House mirrors it); `profit_index` says how it was reached.
            month: month.month, spent_usd: formatUsd(month.spent), cap_usd: formatUsd(capMicro), calls: month.calls,
            base_cap_usd: formatUsd(monthCapMicro(env)), profit_index: parts,
            by_agent: Object.fromEntries(Object.entries(month.agents).map(([name, value]) => [name, formatUsd(BigInt(value))])),
          };
        })(),
        typesafe: this.typesafeStatus(),
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
