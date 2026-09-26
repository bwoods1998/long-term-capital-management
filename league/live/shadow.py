"""The shadow book: every Candidate (and every family on real money) trades live quotes under the Gym's own fill rules.

The options-swarm run, Wave 5 (Sept 26, 2026; the plan's "Live" loop: "every Candidate trades the shadow book on live
OPRA quotes"). Its trades are the family's forward record from live sessions (`source "shadow"`), which with the nightly
replays and real trades sizes money. The record is only honest if the fills are the Gym's, so a `ShadowAccount` IS the
Gym's `league.gym.engine.Account` (subclassed only where a replay and a live session differ):

- the day it steps through is a `league.live.chains.LiveDay` (live chains as the store's grids);
- its program runs in the decider's child process (`league.live.decider`), so `_decide` is split in two: `job` builds
  exactly what the engine hands `build_ctx` (the positions and orders rows, cash, equity, buying power, the rules of
  the roots with a chain now) and `apply` turns the answer's intents into orders with the engine's own `_intent`;
- `_trade_row` is the engine's with the date helper taken from here (the engine's imports pyarrow, which the House has
  not).

Everything else is the engine's code, unchanged: a decision at minute m meets the NBBO of minute m + 1 at the natural
price (better only by the calibrated fill model's draw, keyed by contract and minute), size capped by the quoted size,
fees by the venue's table, the expiry cutoffs, the 15:30 liquidation of expiring equity positions, cash settlement of
XSP/SPXW and exercise of equity legs at the close, a day's working orders expiring at the close.

State: the accounts are written to `<root>/live-shadow.json` after every minute (`ShadowBook.save`), so a restart
resumes them, working orders and all.
"""

from __future__ import annotations

import math
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
        self.exported = 0          # trades already handed to the forward record
        self.winding_down = False  # a superseded instance: no decisions, its positions closed at the natural
        self.began_day: int | None = None
        self.ended_day: int | None = None
        self.last_mi = -1          # the last minute of today this account was stepped through

    # ------------------------------------------------------------------ the minute, in two halves
    def pre(self, day: LiveDay, mi: int) -> None:
        """The engine's step before the decision: working orders meet this minute's quotes, then the venue acts. The
        engine steps every minute; a live minute the House missed (a slow minute) still gets the venue's rules (the
        cutoffs act at their exact minute), with no quotes to fill against."""
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
        for intent in intents or []:
            try:
                self._intent(day, mi, dict(intent))
            except L.Refused as exc:
                self._reject(str(exc))

    def wind_down(self, day: LiveDay, mi: int) -> None:
        """Close everything at the natural, as orders arriving next minute (a superseded instance)."""
        self.winding_down = True
        for pos in list(self.positions.values()):
            if pos.closing:
                continue
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

    def _trade_row(self, pos: E.Position) -> dict:
        max_loss = pos.max_loss_share * V.MULTIPLIER * pos.opened_qty
        exit_value = pos.exit_value_qty / pos.opened_qty if pos.opened_qty else math.nan
        return {
            "id": pos.pid, "root": pos.root, "type": pos.type, "tag": pos.tag, "qty": pos.opened_qty,
            "legs": [{"dte": leg.dte, "strike": leg.strike, "right": "C" if leg.is_call else "P",
                      "side": "long" if leg.side > 0 else "short", "ratio": leg.ratio} for leg in pos.legs],
            "day": from_ordinal(pos.opened_day).isoformat(), "entry_minute": pos.info.get("minute"),
            "filled_minute": pos.info.get("filled_minute"),
            "exit_day": from_ordinal(pos.exit_day).isoformat() if pos.exit_day else None,
            "exit_minute": pos.exit_mi + pos.info.get("open_min", 570) if pos.exit_mi else None,
            "sessions_held": self.session - pos.opened_session,
            "entry": round(pos.entry, 4), "exit": None if not math.isfinite(exit_value) else round(exit_value, 4),
            "max_loss": round(max_loss, 2), "fees": round(pos.fees, 2), "pnl": round(pos.cash, 2),
            "return_on_max_loss": round(pos.cash / max_loss, 4) if max_loss > 0 else None,
            "exit_reason": pos.reason, "note": pos.note,
        }

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
            "began_day": self.began_day, "ended_day": self.ended_day, "last_mi": self.last_mi,
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
        return acc


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
    return E.Working(int(x["oid"]), order, int(x["remaining"]), int(x["placed_mi"]), int(x["arrival_mi"]),
                     None if x["expires_mi"] is None else int(x["expires_mi"]), float(x["reserve_left"]), int(x["pid"]),
                     bool(x["forced"]), int(x["filled"]))


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
