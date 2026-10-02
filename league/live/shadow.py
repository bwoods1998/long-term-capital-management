"""The shadow book: every Candidate (and every family on real money) trades live quotes under the Gym's own fill rules.

The options-swarm run, Wave 5 (Sept 26, 2026; the plan's "Live" loop: "every Candidate trades the shadow book on live
OPRA quotes"). Its trades are the family's forward record from live sessions (`source "shadow"`), which with the nightly
replays and real trades sizes money. The record is only honest if the fills are the Gym's, so a `ShadowAccount` IS the
Gym's `league.gym.engine.Account` (subclassed only where a replay and a live session differ):

- the day it steps through is a `league.live.chains.LiveDay` (live chains as the store's grids);
- its program runs in the decider's child process (`league.live.decider`), so `_decide` is split in two: `job` builds
  exactly what the engine hands `build_ctx` (the positions and orders rows, cash, equity, buying power, the rules of
  the roots with a chain now) and `apply` turns the answer's intents into orders with the engine's own `_intent`;

Everything else is the engine's code, unchanged: a decision at minute m meets the NBBO of minute m + 1 at the natural
price (better only by the calibrated fill model's draw, keyed by contract and minute), size capped by the quoted size,
fees by the venue's table, the expiry cutoffs, the 15:30 liquidation of expiring equity positions, cash settlement of
XSP/SPXW and exercise of equity legs at the close, a day's working orders expiring at the close.

State: the accounts are written to `<root>/live-shadow.json` after every minute (`ShadowBook.save`), so a restart
resumes them, working orders and all.

THE PRACTICE CAPS (v3, Oct 2026): a practice account (`<family>@<version>:o`) holds what a Probe may hold, scaled to its
own shadow capital, from the constitution's `options_money.probe` (`money.Table`): at most `open_per_family` structures
open or working; no open whose maximum loss with its open and close fees passes max(`max_loss_share` x capital,
`floor_usd`); no open that takes the account's maximum loss at risk (open structures and working opens) past
`family_share` x capital. An open the engine made that passes a cap is withdrawn before it can work (the engine's counts
as if it was never sent) and refused: a practice `rejected` event with its reason, told to the program like any refusal,
never a program error. A Candidate's shadow (`:s`) keeps the engine's own rules.
"""

from __future__ import annotations

import functools
import math
import os
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import numpy as np

from ..gym import engine as E
from ..gym import fills as F
from ..gym import legs as L
from ..gym import venue as V
from ..gym.runtime import Needs
from .chains import LiveDay, from_ordinal
from .state import read_json, write_json_atomic

SHADOW_FILE = "live-shadow.json"
VERSION = 1


class _Inert:
    """The engine's runner slot: the program runs in the decider, never here."""

    disqualified: str | None = None

    def stats(self) -> dict:
        return {}


def needs_of(raw: Mapping[str, Any]) -> Needs:
    return Needs(tuple(raw["roots"]), int(raw["dte"][0]), int(raw["dte"][1]), float(raw["band"]), int(raw["cadence"]),
                 int(raw["history"]), int(raw["start"]), int(raw["end"]))


class ShadowAccount(E.Account):
    """One family instance's shadow book (the module docstring)."""

    def __init__(self, *, instance: str, family: str, needs: Needs, params: Mapping[str, Any], capital: float,
                 fill_model: F.FillModel | None = None, max_orders_day: int = 60):
        stub = SimpleNamespace(needs=needs, params=dict(params), start=lambda **_: _Inert())
        cfg = E.RunConfig(window="forward", roots=tuple(needs.roots), capital=float(capital),
                          fill_model=fill_model or F.FillModel(), max_orders_day=int(max_orders_day))
        super().__init__(stub, cfg, tuple(needs.roots))
        self.instance, self.family = instance, family
        #: This account's own identity, drawn when it is made and kept across restarts: its trade ids restart when an
        #: account is made again under the same instance key, so a record keyed by trade id also names the account.
        self.nonce = os.urandom(6).hex()
        self.exported = 0          # trades already handed to the forward record
        self.winding_down = False  # a superseded instance: no decisions, its positions closed at the natural
        self.began_day: int | None = None
        self.ended_day: int | None = None
        self.last_mi = -1          # the last minute of today this account was stepped through
        #: Positions the House closed winding the instance down (`wind_down`), not the program: the practice league's
        #: record keeps their P&L and leaves them out of its statistics (`league/live/observe.py`, `forced`).
        self.wound: set[int] = set()
        self.practice_events: list[dict] = []
        self.practice_next_event = 0
        self.practice_dropped_events = 0
        self.practice_evaluator: str | None = None
        self._practice_stamp: tuple[str | None, int | None] = (None, None)

    def practice_event(self, kind: str, body: Mapping[str, Any], *, day: LiveDay | None = None,
                       mi: int | None = None) -> None:
        """Private receipts only for practice accounts, retained in the saved shadow account until SQLite accepts them.
        The bound applies only during a prolonged ledger outage; discarded receipt count is explicit."""
        if not self.instance.endswith(":o"):
            return
        if day is not None:
            self._practice_stamp = (day.day.isoformat(), mi)
        self.practice_next_event += 1
        if len(self.practice_events) >= 10000:
            self.practice_dropped_events += 1
            return
        self.practice_events.append({"id": self.practice_next_event, "day": self._practice_stamp[0],
                                     "minute": self._practice_stamp[1], "kind": kind, **dict(body),
                                     "dropped_before": self.practice_dropped_events})

    def _reject(self, why: str, *, tell: bool = True) -> None:
        super()._reject(why, tell=tell)
        self.practice_event("rejected", {"reason": str(why)[:1000]})

    def _intent(self, day: LiveDay, mi: int, intent: Mapping[str, Any]) -> None:
        if not self.instance.endswith(":o"):
            return super()._intent(day, mi, intent)
        before = set(self.orders)
        self.practice_event("intent", {"intent": dict(intent)}, day=day, mi=mi)
        super()._intent(day, mi, intent)
        opens = [self.orders[oid] for oid in sorted(set(self.orders) - before) if self.orders[oid].order.action == "open"]
        if opens:
            why = self._practice_cap(opens)
            if why:
                for work in opens:
                    self._withdraw(work)
                raise L.Refused(why)
        for oid in set(self.orders) - before:
            work = self.orders[oid]
            self.practice_event("order", {"order": _working_state(work), "quotes": self._quotes(day, mi, work)},
                                day=day, mi=mi)

    def _practice_cap(self, opens: Sequence[E.Working]) -> str | None:
        """Why the practice caps (the module docstring) refuse these new opens, or None. Never raises: caps that cannot
        be read refuse the open."""
        try:
            (share, floor), open_max, family_share = _probe_caps()
            capital = float(self.cfg.capital)
            new = {w.oid for w in opens}
            working = [w for w in self.orders.values() if w.order.action == "open" and w.oid not in new]
            open_now = len(self.positions) + sum(1 for w in working if w.pid not in self.positions)
            if open_now + len(opens) > open_max:
                return f"practice cap: {open_now} structures open or working, the most a Probe holds is {open_max}"
            # As the real book's exposure: open structures and working opens at their maximum loss; the new open with
            # its open and close fees (the money table's `unit`).
            at_risk = sum(p.max_loss_share * V.MULTIPLIER * p.qty for p in self.positions.values()) + sum(
                w.order.max_loss_share * V.MULTIPLIER * w.remaining for w in working)
            cap = max(share * capital, floor)
            family = family_share * capital
            for work in opens:
                loss = work.order.max_loss_share * V.MULTIPLIER * work.order.qty + 2.0 * work.order.fees
                if not math.isfinite(loss) or loss > cap + 1e-9:
                    return f"practice cap: this open risks {loss:.2f} with fees, over the Probe's {cap:.2f} an open"
                at_risk += loss
            if not math.isfinite(at_risk) or at_risk > family + 1e-9:
                return (f"practice cap: {at_risk:.2f} of maximum loss would be at risk, over the Probe's {family:.2f} "
                        "a family")
            return None
        except Exception as exc:  # noqa: BLE001 - fail closed: no open without its caps read
            return f"practice cap: the Probe's caps could not be read ({type(exc).__name__})"

    def _withdraw(self, work: E.Working) -> None:
        """An open the practice caps refused, taken back before it can work: the engine's counts as if never sent."""
        self.orders.pop(work.oid, None)
        self.orders_today = max(0, self.orders_today - 1)
        for key in ("orders", "opens"):
            self.counts[key] = max(0, int(self.counts.get(key, 0)) - 1)

    @staticmethod
    def _quotes(day: LiveDay, mi: int, work: E.Working) -> list[dict]:
        chain = day.chains.get(work.order.root)
        if chain is None or not 0 <= mi < day.minutes:
            return []
        try:
            return [{"key": int(leg.key), "side": int(leg.side), "ratio": int(leg.ratio),
                     "bid": _num(float(chain.bid[mi, leg.idx])), "ask": _num(float(chain.ask[mi, leg.idx]))}
                    for leg in work.order.legs]
        except (IndexError, TypeError, ValueError):
            return []  # missing receipt quotes never change a fill already booked by the engine

    def _open_fill(self, day: LiveDay, mi: int, work: E.Working, price: float, qty: int, fees: float) -> None:
        super()._open_fill(day, mi, work, price, qty, fees)
        self._practice_fill(day, mi, work, price, qty, fees, "open")

    def _close_fill(self, day: LiveDay, mi: int, work: E.Working, price: float, qty: int, fees: float, reason: str) -> None:
        super()._close_fill(day, mi, work, price, qty, fees, reason)
        self._practice_fill(day, mi, work, price, qty, fees, reason)

    def _practice_fill(self, day: LiveDay, mi: int, work: E.Working, price: float, qty: int, fees: float, reason: str) -> None:
        if not self.instance.endswith(":o"):
            return
        mid = _num(work.order.mid)
        self.practice_event("fill", {"order_id": work.oid, "position": work.pid, "action": work.order.action,
            "price": price, "quantity": qty, "fees": fees, "reason": reason,
            "decision_mid": mid, "decision_natural": _num(work.order.natural),
            "slippage_to_decision_mid_usd": None if mid is None else
                (price - mid) * (1 if work.order.action == "open" else -1) * qty * V.MULTIPLIER,
            "quotes": self._quotes(day, mi, work)}, day=day, mi=mi)

    def _drop(self, work: E.Working, why: str) -> None:
        super()._drop(work, why)
        self.practice_event("order_end", {"order_id": work.oid, "reason": why, "filled": work.filled})

    # ------------------------------------------------------------------ the minute, in two halves
    def pre(self, day: LiveDay, mi: int) -> None:
        """The engine's step before the decision: working orders meet this minute's quotes, then the venue acts. The
        engine steps every minute; a live minute the House missed (a slow minute) still gets the venue's rules (the
        cutoffs act at their exact minute), with no quotes to fill against."""
        self._practice_stamp = (day.day.isoformat(), mi)
        last = getattr(self, "last_mi", -1)
        for skipped in range(max(0, last + 1), mi):
            self._venue(day, skipped)
        if self.orders:
            self._work(day, mi)
        self._venue(day, mi)
        self.last_mi = mi

    def job(self, day: LiveDay, mi: int) -> dict | None:
        """What `engine.Account._decide` hands `build_ctx`, for the decider; None when no root has a chain now."""
        roots = [r for r in self.roots if day.snapshot(r, mi) is not None]
        if not roots:
            return None
        positions = self._position_rows(day, mi)
        job = {"minute": day.open_min + mi, "open_minute": day.open_min, "close_minute": day.close_min,
               "weekday": day.weekday, "roots": roots, "positions": positions, "orders": self._order_rows(day, mi),
               "cash": self.cash, "equity": self.equity(), "budget": self.cfg.capital, "buying_power": self.buying_power(),
               "rules": {r: day.rules_rows[r] for r in roots}, "events": day.events, "events_next": day.events_next,
               "closed": list(self.closed_since), "rejects": list(self.rejects_since)}
        self.closed_since = []
        self.rejects_since = []
        return job

    def apply(self, day: LiveDay, mi: int, intents: Sequence[Mapping[str, Any]]) -> None:
        """The answer's intents as the engine's orders. Any intent that cannot become one is a refusal of that intent
        alone (the engine raises `Refused`; a malformed value, a NaN the JSON reply made None, raises TypeError or
        ValueError), never the minute's end: one program's bad intent costs no other program anything."""
        for intent in intents or []:
            try:
                self._intent(day, mi, dict(intent))
            except L.Refused as exc:
                self._reject(str(exc))
            except Exception as exc:  # noqa: BLE001 - a malformed intent is refused, never raised
                self._reject(f"a malformed intent: {type(exc).__name__}: {str(exc)[:160]}")

    def wind_down(self, day: LiveDay, mi: int) -> None:
        """Close everything at the natural, as orders arriving next minute (a superseded instance)."""
        self.winding_down = True
        for pos in list(self.positions.values()):
            if pos.closing:
                continue
            self.wound.add(int(pos.pid))
            try:
                self._intent(day, mi, {"close": pos.pid, "limit": "natural", "tag": "wind-down"})
            except L.Refused as exc:
                self._reject(str(exc))
        for work in list(self.orders.values()):
            if work.order.action == "open":
                self._drop(work, "cancelled")

    def new_trades(self) -> list[dict]:
        out = self.trades[self.exported:]
        self.exported = len(self.trades)
        return out

    # ------------------------------------------------------------------ state
    def to_state(self) -> dict:
        return {
            "instance": self.instance, "family": self.family, "needs": self.needs.as_dict(), "params": self.params,
            "capital": self.cfg.capital, "max_orders_day": self.cfg.max_orders_day, "cash": self.cash,
            "equity_prev": self.equity_prev, "next_id": self.next_id, "orders_today": self.orders_today,
            "session": self.session, "counts": self.counts, "reject_reasons": self.reject_reasons,
            "positions": [_position_state(p) for p in self.positions.values()],
            "orders": [_working_state(w) for w in self.orders.values()],
            "pending_shares": [[_position_state(p), root, shares, ref] for p, root, shares, ref in self.pending_shares],
            "trades": self.trades[self.exported:], "daily": self.daily[-30:], "fill_rows": self.fill_rows[-200:],
            "closed_since": self.closed_since, "rejects_since": self.rejects_since, "winding_down": self.winding_down,
            "began_day": self.began_day, "ended_day": self.ended_day, "last_mi": self.last_mi, "nonce": self.nonce,
            "wound": sorted(self.wound),
            "practice_events": self.practice_events, "practice_next_event": self.practice_next_event,
            "practice_dropped_events": self.practice_dropped_events,
            "practice_evaluator": self.practice_evaluator,
        }

    @classmethod
    def from_state(cls, row: Mapping[str, Any], fill_model: F.FillModel | None = None) -> "ShadowAccount":
        acc = cls(instance=row["instance"], family=row["family"], needs=needs_of(row["needs"]), params=row["params"],
                  capital=row["capital"], fill_model=fill_model, max_orders_day=row.get("max_orders_day", 60))
        acc.cash, acc.equity_prev = float(row["cash"]), float(row["equity_prev"])
        acc.next_id, acc.orders_today, acc.session = int(row["next_id"]), int(row["orders_today"]), int(row["session"])
        acc.counts.update(row.get("counts") or {})
        acc.reject_reasons = dict(row.get("reject_reasons") or {})
        acc.positions = {p.pid: p for p in (_position_from(x) for x in row.get("positions") or [])}
        acc.orders = {w.oid: w for w in (_working_from(x) for x in row.get("orders") or [])}
        acc.pending_shares = [(_position_from(p), root, float(shares), float(ref)) for p, root, shares, ref in row.get("pending_shares") or []]
        acc.trades = list(row.get("trades") or [])
        acc.exported = 0
        acc.daily = [tuple(x) for x in row.get("daily") or []]
        acc.fill_rows = [tuple(x) for x in row.get("fill_rows") or []]
        acc.closed_since = list(row.get("closed_since") or [])
        acc.rejects_since = list(row.get("rejects_since") or [])
        acc.winding_down = bool(row.get("winding_down"))
        acc.began_day, acc.ended_day = row.get("began_day"), row.get("ended_day")
        acc.last_mi = int(row.get("last_mi", -1))
        acc.nonce = str(row.get("nonce") or acc.nonce)
        acc.wound = {int(x) for x in row.get("wound") or [] if isinstance(x, int) and not isinstance(x, bool)}
        acc.practice_events = list(row.get("practice_events") or [])
        acc.practice_next_event = int(row.get("practice_next_event") or 0)
        acc.practice_dropped_events = int(row.get("practice_dropped_events") or 0)
        acc.practice_evaluator = row.get("practice_evaluator")
        return acc


@functools.lru_cache(maxsize=1)
def _probe_caps() -> tuple[tuple[float, float], int, float]:
    """((max_loss_share, floor_usd), open_per_family, family_share) of the constitution's `options_money.probe`, as the
    money table reads it (ValueError on a table outside its bounds: the practice caps then refuse every open)."""
    from .money import Table

    table = Table.from_constitution()
    return (float(table.probe_share), float(table.probe_floor)), int(table.probe_open), float(table.probe_family_share)


def _num(value: float) -> float | None:
    return None if value is None or (isinstance(value, float) and not math.isfinite(value)) else value


def _leg_state(leg: L.LegFill) -> list:
    return [int(leg.idx), int(leg.key), int(leg.side), int(leg.ratio), int(leg.dte), float(leg.strike), bool(leg.is_call)]


def _leg_from(x: Sequence[Any]) -> L.LegFill:
    return L.LegFill(int(x[0]), int(x[1]), int(x[2]), int(x[3]), int(x[4]), float(x[5]), bool(x[6]))


def _position_state(p: E.Position) -> dict:
    return {"pid": p.pid, "type": p.type, "root": p.root, "legs": [_leg_state(x) for x in p.legs], "keys": p.keys.tolist(),
            "expirations": p.expirations.tolist(), "qty": p.qty, "opened_qty": p.opened_qty, "entry": p.entry,
            "max_loss_share": p.max_loss_share, "collateral": p.collateral, "opened_day": p.opened_day,
            "opened_mi": p.opened_mi, "opened_session": p.opened_session, "info": p.info, "tag": p.tag, "note": p.note,
            "cash": p.cash, "fees": p.fees, "exit_value_qty": p.exit_value_qty, "exit_day": p.exit_day, "exit_mi": p.exit_mi,
            "reason": p.reason, "idx": None if p.idx is None else p.idx.tolist(), "last_mark": _num(p.last_mark),
            "closing": p.closing}


def _position_from(x: Mapping[str, Any]) -> E.Position:
    return E.Position(
        pid=int(x["pid"]), type=x["type"], root=x["root"], legs=tuple(_leg_from(v) for v in x["legs"]),
        keys=np.array(x["keys"], dtype=np.int64), expirations=np.array(x["expirations"], dtype=np.int64), qty=int(x["qty"]),
        opened_qty=int(x["opened_qty"]), entry=float(x["entry"]), max_loss_share=float(x["max_loss_share"]),
        collateral=float(x["collateral"]), opened_day=int(x["opened_day"]), opened_mi=int(x["opened_mi"]),
        opened_session=int(x["opened_session"]), info=dict(x.get("info") or {}), tag=x.get("tag") or "",
        note=x.get("note") or "", cash=float(x["cash"]), fees=float(x["fees"]), exit_value_qty=float(x["exit_value_qty"]),
        exit_day=int(x["exit_day"]), exit_mi=int(x["exit_mi"]), reason=x.get("reason") or "",
        idx=None if x.get("idx") is None else np.array(x["idx"], dtype=np.int64),
        last_mark=math.nan if x.get("last_mark") is None else float(x["last_mark"]), closing=int(x.get("closing") or 0))


def _working_state(w: E.Working) -> dict:
    o = w.order
    return {"oid": w.oid, "remaining": w.remaining, "placed_mi": w.placed_mi, "arrival_mi": w.arrival_mi,
            "expires_mi": w.expires_mi, "reserve_left": w.reserve_left, "pid": w.pid, "forced": w.forced, "filled": w.filled,
            "seen": w.seen, "aggressive": w.aggressive, "fill_flags_known": getattr(w, "fill_flags_known", True) is True,
            "order": {"action": o.action, "type": o.type, "root": o.root, "legs": [_leg_state(x) for x in o.legs], "qty": o.qty,
                      "limit": _num(o.limit), "natural": _num(o.natural), "mid": _num(o.mid), "max_loss_share": o.max_loss_share,
                      "collateral": o.collateral, "fees": o.fees, "reserve": o.reserve, "tif": o.tif, "tag": o.tag,
                      "note": o.note, "position": o.position, "extra": o.extra}}


def _working_from(x: Mapping[str, Any]) -> E.Working:
    o = x["order"]
    nan = lambda v: math.nan if v is None else float(v)  # noqa: E731
    order = L.Order(o["action"], o["type"], o["root"], tuple(_leg_from(v) for v in o["legs"]), int(o["qty"]), nan(o["limit"]),
                    nan(o["natural"]), nan(o["mid"]), float(o["max_loss_share"]), float(o["collateral"]), float(o["fees"]),
                    float(o["reserve"]), o["tif"], o.get("tag") or "", o.get("note") or "", o.get("position"),
                    dict(o.get("extra") or {}))
    valid_flags = type(x.get("seen")) is bool and type(x.get("aggressive")) is bool \
        and (not x["aggressive"] or x["seen"])
    work = E.Working(int(x["oid"]), order, int(x["remaining"]), int(x["placed_mi"]), int(x["arrival_mi"]),
                     None if x["expires_mi"] is None else int(x["expires_mi"]), float(x["reserve_left"]), int(x["pid"]),
                     bool(x["forced"]), int(x["filled"]),
                     seen=x["seen"] if valid_flags else False, aggressive=x["aggressive"] if valid_flags else False)
    # Old saves lost the first-quote classification. Keep their previous fallback without inferring it
    # from filled quantity; either resting or taking orders can partially fill. Preserve that uncertainty
    # across later saves for private execution evidence. The marker never participates in fill decisions.
    work.fill_flags_known = valid_flags and x.get("fill_flags_known", True) is True
    return work


class ShadowBook:
    """Every shadow account, by instance id, persisted as one JSON file."""

    def __init__(self, path: Any, *, fill_model: F.FillModel | None = None):
        self.path = path
        self.fill_model = fill_model or F.FillModel()
        self.accounts: dict[str, ShadowAccount] = {}
        self.day_ordinal: int | None = None
        raw = read_json(path, None)
        if isinstance(raw, dict) and raw.get("version") == VERSION:
            self.day_ordinal = raw.get("day")
            for row in raw.get("accounts") or []:
                try:
                    acc = ShadowAccount.from_state(row, self.fill_model)
                    self.accounts[acc.instance] = acc
                except (KeyError, TypeError, ValueError):
                    continue

    def save(self) -> None:
        write_json_atomic(self.path, {"version": VERSION, "day": self.day_ordinal,
                                      "accounts": [a.to_state() for a in self.accounts.values()]})


__all__ = ["ShadowAccount", "ShadowBook", "needs_of", "SHADOW_FILE"]
