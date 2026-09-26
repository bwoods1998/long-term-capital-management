"""The House's live options step: live chains, the shadow book, the paper proof, the real route, reconciliation, stops.

The options-swarm run, Wave 5 (Sept 26, 2026; the plan's "Live" loop and "Money"). `OptionsLive` is `House.options_live`
(`league/house.py` `PLUGGABLE_STEPS`). The House's tick only keeps it alive and reads its summary; the work runs on its
own thread, once a minute, a few seconds after each minute of the New York session starts (09:30-16:00; 13:00 on a
half day), so a slow House tick never delays a fill and a slow minute never delays the House:

1. The families (`league/live/families.py`, every five minutes): which programs run live, as which instances. A
   Candidate runs a SHADOW instance; a Probe or Sized family a shadow and a REAL instance; a family that passed
   validation but not yet its holdout a real TUITION instance (1-lot orders only to measure fills; never evidence) while
   real money is on. The live path moves candidate <-> probe <-> sized by the money table (`league/live/money.py`).
   A superseded or dropped shadow instance winds down (its positions closed at the natural); a real one goes to exits
   only until it is flat (its program stays in the live state so it can still close what it holds).
2. The chains: each root's option chain through the gateway (one read a minute a root, filtered to the expiries and
   strikes the live programs need), the underlying (stock snapshots; XSP and SPXW from put-call parity), into the day's
   grids (`league/live/chains.py`).
3. The shadow book: the Gym's own `Account` per shadow instance (`league/live/shadow.py`): working orders meet this
   minute's quotes, the venue acts, and the instances due to decide are asked.
4. The real account: its equity, orders (fills booked to families) and positions (reconciled), the stops, the kill
   switch, the expiry-day rules, the tif expiries; then the real instances due to decide are asked.
5. One batch to the decider (`league/live/decider.py`); the answers become shadow orders (the engine's `_intent`) and
   real orders (sized by the money table, through the order path, `league/live/real.py`).
6. Forward records: closed shadow trades (`shadow`) and real trades (`real`; tuition never) to the swarm.

Real opens need every one of: `config.json` `real_money`; the grant `options-swarm-20260928` active on the money digest
in force (`House.grant`); the gateway's kill switch off; no stop tripped (`money.Stops`); reconciliation clean; the
paper proof passed this session or before (`live.require_paper_proof`); the House not paused; the family's band (or
tuition) and the instance live. Exits need only the kill switch off.
"""

from __future__ import annotations

import datetime as dt
import math
import threading
import time
import traceback
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

import numpy as np

from ..gym import fills as F
from ..gym import legs as L
from ..gym.engine import settlement_level
from ..gym import venue as V
from ..gym.ctx import order_row, position_row
from . import money as M
from .chains import LiveDay, from_ordinal, ordinal, session_minutes, trading_days_around, uses_parity
from .decider import DeciderError, ProgramRefused, MAX_BATCH_SECONDS
from .families import MemoryFamilies
from .paper import PaperProof
from .real import RealBook, RLeg, RPosition, real_legs
from .shadow import SHADOW_FILE, ShadowAccount, ShadowBook, needs_of
from .state import STATE_FILE, LiveState
from .venue import OPTION_EVENTS, Account, MarketData, VenueError, occ_parts, occ_symbol, parse_time, stock_price

NEW_YORK = ZoneInfo("America/New_York")
FAMILIES_EVERY = 300.0
ACTIVITIES_EVERY = 300.0
FLOWS_EVERY = 300.0
BROKEN_RESEND_MINUTES = 3    # a broken structure's leg is sent alone at most this often
EXIT_PREEMPT_SECONDS = 120.0
DECIDER_ORPHAN_SECONDS = 300.0
MINUTE_OFFSET = 3.0          # seconds into each minute the live step runs
DEFAULTS = {
    "enabled": True,
    "thread": True,              # the minute thread (tests drive `minute()` themselves)
    "shadow_capital": 10000.0,
    "require_paper_proof": True,
    "read_band_margin": 0.01,
    "read_dte_margin": 2,
    "decide_timeout": 1.0,
    "max_errors": 25,
    "decider_memory_mb": 2048,
    "instance_orders_day": 60,   # a real instance's orders a day, opens and closes (the Gym's `max_orders_day`)
}


@dataclass
class Instance:
    key: str
    family: str
    version: int
    kind: str                    # shadow | real
    code: str
    params: dict
    run_sha: str = ""
    band: str = ""
    tuition: bool = False
    mode: str = "live"           # live | exit_only | wind_down
    needs: Any = None
    error: str = ""
    fatal: bool = False          # the program will not run again (refused, or disqualified): the House closes what it holds
    stats: dict = field(default_factory=dict)
    error_since: float | None = None
    retried_at: float = float("-inf")


def ny(t: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(t, NEW_YORK)


def epoch_of(day: dt.date, minute: int) -> float:
    return dt.datetime.combine(day, dt.time(minute // 60, minute % 60), NEW_YORK).timestamp()


class OptionsLive:
    """`House.options_live` (the module docstring)."""

    def __init__(self, root: str | Path, *, market: MarketData, real: Account | None, paper: Account | None,
                 families: Any = None, grant: Any = None, kill_switch: Callable[[], bool] | None = None,
                 decider: Any = None, table: M.Table | None = None, config: Mapping[str, Any] | None = None,
                 real_money: bool = False, performance: Mapping[str, Any] | None = None,
                 clock: Callable[[], float] = time.time, record: Callable[..., Any] | None = None,
                 alert: Callable[[str, str], Any] | None = None, notify: Callable[[Mapping[str, Any]], Any] | None = None,
                 fill_model: F.FillModel | None = None):
        self.root = Path(root)
        self.settings = {**DEFAULTS, **dict(config or {})}
        self.market, self.real, self.paper = market, real, paper
        self.families = families if families is not None else MemoryFamilies()
        self.grant, self.kill_switch = grant, kill_switch
        self.table = table or M.Table.from_constitution()
        self.real_money = bool(real_money) and real is not None
        self.clock = clock
        self._record = record
        self._alert = alert
        self.notify = notify
        if decider is None:
            from .decider import Decider

            decider = Decider(timeout=float(self.settings["decide_timeout"]), max_errors=int(self.settings["max_errors"]),
                              memory_mb=int(self.settings["decider_memory_mb"]), log=self.root / "live-decider.log")
        self.decider = decider
        self.state = LiveState(self.root / STATE_FILE, clock=clock)
        self.shadow = ShadowBook(self.root / SHADOW_FILE, fill_model=fill_model or F.FillModel.load())
        self.book = RealBook(self.state, real, self.table, clock=clock, record=self.record) if real is not None else None
        self.proof = PaperProof(self.state, paper, record=self.record, clock=clock) if paper is not None else None
        perf = dict(performance or {})
        self.start_at = str(perf.get("start_at") or "")
        start_equity = M.D(perf.get("start_equity") or 0)
        self.stops = M.Stops.from_state(self.state.get("stops"), start_equity)
        self.instances: dict[str, Instance] = {}
        self.day: LiveDay | None = None
        self.house_open = True
        self.summary: dict[str, Any] = {"state": "idle"}
        self.account_row: dict[str, Any] | None = None
        self._account_at: float | None = None
        self.flows: M.FlowBook | None = None
        self._families_at = float("-inf")
        self._activities_at = float("-inf")
        self._activities_changed = False
        self._stock_held = False
        self._flows_at = float("-inf")
        self._last_minute: tuple[str, int] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._rows: list[dict] = []
        #: pid -> {forced, why, intent, day}: exits waiting for their contracts (another order works on them), kept in
        #: the live state so a restart does not lose one the program was told the House sends.
        self.pending_exits: dict[int, dict] = {int(k): dict(v) for k, v in (self.state.get("pending_exits", {}) or {}).items()}
        self._decision_end = time.monotonic() + MAX_BATCH_SECONDS
        self._restore_real_instances()

    # ------------------------------------------------------------------ plumbing
    def record(self, kind: str, payload: Mapping[str, Any], agent: str | None = None) -> None:
        self.state.event(kind, payload)
        if self._record is not None:
            try:
                self._record(kind, dict(payload), agent)
            except Exception:  # noqa: BLE001 - the ledger's trouble never stops trading
                pass

    def alert(self, level: str, text: str) -> None:
        if self._alert is not None:
            try:
                self._alert(level, text)
            except Exception:  # noqa: BLE001
                pass

    def _tell_owner(self, stop: str, text: str) -> None:
        if self.notify is None:
            return
        try:
            self.notify({"kind": "live_stop", "stop": stop, "text": text[:1500],
                         "equity": str(self.account_row.get("equity")) if self.account_row else None,
                         "at": dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc).isoformat()})
        except Exception as exc:  # noqa: BLE001
            self.alert("warning", f"the owner could not be told of the {stop} stop ({type(exc).__name__})")

    # ------------------------------------------------------------------ the House's side
    def tick(self, house: Any, *, open_for_business: bool = True) -> dict:
        """Called once a House tick: keeps the minute thread alive; returns the last minute's summary."""
        self.house_open = bool(open_for_business)
        if (self.settings.get("enabled", True) and self.settings.get("thread", True)
                and (self._thread is None or not self._thread.is_alive())):
            self.start()
        with self._lock:
            return dict(self.summary)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="options-live", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
        try:
            self.decider.close()
        except Exception:  # noqa: BLE001
            pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = self.clock()
            wait = 60.0 - (now % 60.0) + MINUTE_OFFSET
            if wait >= 60.0:
                wait -= 60.0
            if self._stop.wait(wait):
                return
            try:
                self.minute()
            except Exception as exc:  # noqa: BLE001 - the next minute tries again
                self.alert("warning", f"the live options step failed ({type(exc).__name__}: {str(exc)[:200]})")
                self.state.event("live.error", {"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-2000:]})

    # ------------------------------------------------------------------ one minute
    def owner_actions(self) -> None:
        """What the owner asked for with `python -m league.live` (the live state's key-values, read every minute): the
        drawdown pause released, an assignment's latch cleared. Only the owner's command writes them."""
        ask = self.state.get("owner_release_drawdown")
        if ask and self.stops.drawdown_tripped:
            self.record("live.stop", {"stop": "drawdown", "released": True, "why": self.stops.drawdown_why,
                                      "by": str(ask.get("by") or "the owner")})
            self.stops.release_drawdown()
            self.state.put("stops", self.stops.as_state())
        if ask:
            self.state.execute("DELETE FROM kv WHERE key='owner_release_drawdown'")
        ask = self.state.get("owner_clear_assignment")
        if ask:
            latch = self.state.get("assignment_latch")
            if latch:
                self.record("live.stop", {"stop": "assignment", "released": True, "why": latch.get("why")})
            self.state.execute("DELETE FROM kv WHERE key IN ('assignment_latch', 'owner_clear_assignment')")

    def minute(self) -> dict:
        """One pass: the session's minute, the close's bookkeeping, or the quiet hours' reconciliation."""
        now = self.clock()
        # Loads, recovery, decisions and drops share one budget; leave five seconds before the next wall minute for
        # applying answers, exports and persistence. A late data/account read consumes that same allowance.
        self._decision_end = time.monotonic() + max(0.0, min(MAX_BATCH_SECONDS, 60.0 - now % 60.0 - 5.0))
        self.owner_actions()
        local = ny(now)
        today = local.date()
        session = session_minutes(today)
        m = local.hour * 60 + local.minute
        out: dict[str, Any] = {"at": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds")}
        if session is None:
            out["state"] = "closed"
            self._quiet(now, out)
            return self._done(out)
        open_min, close_min = session
        if m < open_min:
            out["state"] = "before the open"
            self._quiet(now, out)
            return self._done(out)
        day = self._ensure_day(today, open_min, close_min)
        mi = m - open_min
        if mi >= day.minutes - 1:
            if mi == day.minutes - 1 and self._last_minute != (today.isoformat(), mi):
                # The close's own row: read it, and step the shadow book through its last minute (one behind).
                self._last_minute = (today.isoformat(), mi)
                self._closing_minute(day, mi, now, out)
            out["state"] = "after the close"
            self._end_of_day(day, out)
            self._quiet(now, out)
            return self._done(out)
        if self._last_minute == (today.isoformat(), mi):
            out["state"] = "minute already done"
            return self._done(out)
        self._last_minute = (today.isoformat(), mi)
        out["state"] = "session"
        out["minute"] = open_min + mi
        self._session_minute(day, mi, now, out)
        return self._done(out)

    def _done(self, out: dict) -> dict:
        with self._lock:
            self.summary = out
        return out

    # ------------------------------------------------------------------ the day
    def _ensure_day(self, today: dt.date, open_min: int, close_min: int) -> LiveDay:
        if self.day is not None and self.day.day == today:
            return self.day
        # A day the House never saw close: its shadow accounts end it without data (the engine's rule).
        if self.shadow.day_ordinal is not None and self.shadow.day_ordinal < ordinal(today):
            old = from_ordinal(self.shadow.day_ordinal)
            stale = LiveDay(old, 570, 960, trading_days=trading_days_around(old))
            for acc in self.shadow.accounts.values():
                if acc.ended_day != self.shadow.day_ordinal and acc.began_day == self.shadow.day_ordinal:
                    acc.end_day(stale, last=False)
                    acc.ended_day = self.shadow.day_ordinal
            self._export_shadow()
        days = trading_days_around(today)
        self.day = LiveDay(today, open_min, close_min, trading_days=days, session=lambda d: session_minutes(d) or (570, 960))
        self.shadow.day_ordinal = ordinal(today)
        self._missed_close(today)
        self.shadow.save()
        return self.day

    def _missed_close(self, today: dt.date) -> None:
        """Real positions whose expiry passed while the House was not there to see the close: an index structure is
        settled at its intrinsic value on the last level the House recorded for it (an approximation of the official
        settlement, said so); an equity one waits for the venue's expiry, exercise or assignment events."""
        if self.book is None:
            return
        levels = self.state.get("levels", {}) or {}
        for pos in list(self.book.positions.values()):
            if pos.qty <= 0 or pos.expiry >= today.isoformat() or pos.status == "awaiting_expiry":
                continue
            level = float((levels.get(pos.root) or [float("nan")])[0])
            if V.is_index(pos.root) and math.isfinite(level) and not pos.info.get("broken"):
                value = sum(leg.side * leg.ratio * _intrinsic(leg, level) for leg in pos.legs)
                self.book.settle(pos, value, "settled at the last recorded level (the House missed the close)")
            elif pos.status != "awaiting_expiry":
                pos.status = "awaiting_expiry"
                self.book._save_position(pos)
            self.alert("warning", f"live: {pos.family}'s {pos.type} expired while the House was away: {pos.status}")
        self._export_real()

    def _history(self, day: LiveDay, root: str, level: float, spy: float) -> None:
        """The prior sessions' daily bars of `root`, read once a day when the root is first read. XSP and SPXW from
        SPY's, scaled by the index level over SPY's price at that reading: the venue has no index history."""
        if root in day.history:
            return
        source = "SPY" if uses_parity(root) else root
        if source not in day.history:
            day.history[source] = []
            try:
                start = (day.day - dt.timedelta(days=100)).isoformat()
                bars = self.market.bars([source], timeframe="1Day", start=start,
                                        end=(day.day - dt.timedelta(days=1)).isoformat())
                day.history[source] = [(float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"])) for r in bars.get(source) or []
                                       if all(k in r for k in ("o", "h", "l", "c"))][-60:]
            except Exception as exc:  # noqa: BLE001 - programs then see no history for it today
                self.alert("warning", f"live: {source}'s daily history could not be read ({type(exc).__name__})")
        if uses_parity(root):
            if not (math.isfinite(level) and math.isfinite(spy) and spy > 0):
                return
            ratio = level / spy
            day.history[root] = [tuple(x * ratio for x in row) for row in day.history.get("SPY", [])]

    # ------------------------------------------------------------------ families and instances
    def _restore_real_instances(self) -> None:
        for r in self.state.rows("SELECT * FROM instances WHERE retired_at IS NULL"):
            inst = Instance(r["id"], r["family"], int(r["version"] or 0), "real", r["code"], dict(json_or(r["params"], {})),
                            r["run_sha"] or "", r["band"] or "", bool(r["tuition"]), r["mode"] or "live")
            if str(r.get("why") or "").startswith(("disqualified:", "the program does not load:", "its decider could not recover")):
                inst.error, inst.fatal, inst.mode = r["why"], True, "exit_only"
                self.instances[inst.key] = inst
                continue
            self._load(inst)

    def _load(self, inst: Instance) -> bool:
        inst.retried_at = self.clock()
        try:
            info = self.decider.load(inst.key, inst.code, inst.params, inst.family, budget_seconds=self._decision_budget())
            inst.needs = needs_of(info["needs"])
            inst.run_sha = info.get("run_sha") or inst.run_sha
            inst.error = ""
            inst.error_since = None
        except ProgramRefused as exc:
            inst.error = f"the program does not load: {str(exc)[:200]}"
            inst.fatal = True
        except DeciderError as exc:
            inst.error = f"the decider failed: {str(exc)[:200]}"
            if inst.error_since is None:
                inst.error_since = self.clock()
        self.instances[inst.key] = inst
        return not inst.error

    def _decision_budget(self) -> float:
        return max(0.0, self._decision_end - time.monotonic())

    def _real_on(self) -> bool:
        return self.real_money and self.book is not None

    def _grant(self) -> dict | None:
        if self.grant is None:
            return None
        try:
            return self.grant.current()
        except Exception:  # noqa: BLE001
            return None

    def sizing_equity(self) -> Decimal | None:
        """The lower of the account's equity and the grant's capital; None when either is unknown."""
        grant = self._grant()
        if not self.account_row or not grant or not grant.get("active"):
            return None
        equity = M.D(self.account_row["equity"])
        capital = M.D((grant.get("policy") or {}).get("capital_usd") or 0)
        return min(equity, capital)

    def sync_families(self, now: float, *, force: bool = False) -> None:
        # Retired and superseded programs still own exits. Recover them even when no current swarm row wants them.
        for inst in list(self.instances.values()):
            if (inst.kind != "real" or inst.fatal or not inst.error.startswith("the decider failed")
                    or self.book is None or not (self.book.instance_positions(inst.key) or self.book.instance_orders(inst.key))):
                continue
            if inst.error_since is None:
                inst.error_since = now
            if now - inst.error_since >= DECIDER_ORPHAN_SECONDS:
                inst.fatal = True
                inst.error = "its decider could not recover for five minutes: the House closes its positions"
                inst.mode = "exit_only"
                self._persist_instance(inst)
                self.alert("error", f"live: {inst.family}: {inst.error}")
            elif now - inst.retried_at >= 60:
                self._load(inst)
        self._cancel_inactive_opens()
        if not force and now - self._families_at < FAMILIES_EVERY:
            return
        self._families_at = now
        try:
            rows = self.families.read()
        except Exception as exc:  # noqa: BLE001 - the live set stays as it was
            self.alert("warning", f"live: the swarm's bands could not be read ({type(exc).__name__}: {str(exc)[:160]})")
            return
        equity = self.sizing_equity()
        wanted: dict[str, tuple[dict, str, bool]] = {}
        for row in rows:
            fid, band = str(row.get("family") or ""), str(row.get("band") or "")
            if not fid:
                continue
            version = int(row.get("version") or 0)
            if band in ("candidate", "probe", "sized"):
                band = self._move_band(row, equity)
                wanted[f"{fid}@{version}:s"] = (row, "shadow", False)
                if band in ("probe", "sized") and self._real_on() and self._real_eligible(fid):
                    wanted[f"{fid}@{version}:r"] = (dict(row, band=band), "real", False)
            elif (band == "gym" and row.get("validation_passed") and not row.get("holdout_passed") and self._real_on()
                  and self.table.tuition_day > 0 and row.get("structure") in self.table.real_types):
                wanted[f"{fid}@{version}:t"] = (row, "real", True)
        for key, (row, kind, tuition) in wanted.items():
            if kind == "real":
                saved = self.state.rows("SELECT why FROM instances WHERE id=?", (key,))
                if saved and str(saved[0]["why"] or "").startswith(("disqualified:", "the program does not load:",
                                                                     "its decider could not recover")):
                    continue
            inst = self.instances.get(key)
            if inst is not None and not inst.fatal and inst.error.startswith("the decider failed"):
                if now - inst.retried_at >= 60:
                    self._load(inst)
            if inst is None:
                inst = Instance(key, str(row["family"]), int(row.get("version") or 0), kind, str(row.get("code") or ""),
                                dict(row.get("params") or {}), str(row.get("run_sha") or ""), str(row.get("band") or ""), tuition)
                if not self._load(inst):
                    self.record("live.instance", {"instance": key, "family": inst.family, "error": inst.error}, agent=inst.family)
                    continue
                if kind == "shadow" and key not in self.shadow.accounts:
                    self.shadow.accounts[key] = ShadowAccount(instance=key, family=inst.family, needs=inst.needs,
                                                              params=inst.params, capital=float(self.settings["shadow_capital"]),
                                                              fill_model=self.shadow.fill_model)
                if kind == "real":
                    self._persist_instance(inst)
                self.record("live.instance", {"instance": key, "family": inst.family, "kind": kind, "band": inst.band,
                                              "tuition": tuition, "state": "started"}, agent=inst.family)
            else:
                inst.band = str(row.get("band") or inst.band)
                if inst.mode != "live" and kind == "real" and not inst.fatal:
                    inst.mode = "live"
                    self._persist_instance(inst)
                elif kind == "real":
                    self._persist_instance(inst)
        for key, inst in list(self.instances.items()):
            if key in wanted or inst.mode != "live":
                continue
            if inst.kind == "shadow":
                inst.mode = "wind_down"
            else:
                inst.mode = "exit_only"
                self._persist_instance(inst)
            self.record("live.instance", {"instance": key, "family": inst.family, "state": inst.mode}, agent=inst.family)
        self._cancel_inactive_opens()

    def _cancel_inactive_opens(self) -> None:
        if self.book is None:
            return
        for order in list(self.book.orders.values()):
            inst = self.instances.get(order.instance)
            if order.action == "open" and (inst is None or inst.mode != "live" or inst.error or inst.fatal):
                why = "its family left the real band or its program is unavailable"
                if self.book.cancel(order, why):
                    self.book._reject(order.instance, f"your open was cancelled: {why}")

    def _move_band(self, row: dict, equity: Decimal | None) -> str:
        """The live path's band move for a Candidate, Probe or Sized family (the money table)."""
        fid, band = row["family"], row["band"]
        forward_meta = row.get("forward") or {}
        try:
            forward = self.families.forward_rows(fid)
            fwd = M.forward_stats(forward, self.table.sized_confidence,
                                  negative=forward_meta.get("negative") if isinstance(forward_meta, Mapping) else None,
                                  version=row.get("version"))
        except Exception:  # noqa: BLE001
            self._families_at = float("-inf")
            return "unavailable"  # no evidence is no authority for a real instance; keep its existing exits
        grant = self._grant()
        if not self._real_on() or not grant or not grant.get("active") or equity is None:
            # No band moves while real money cannot trade (off, no active grant) or the account is unread: a move now
            # would only be undone, and a Probe trades from the session after its move (`_real_eligible`).
            return band
        new, why = M.band_for(self.table, row, equity, fwd, probe_sessions=self._probe_sessions(fid, band))
        try:
            confirmed = self.families.confirm_band(row, new, why, forward, at=self.clock())
        except Exception as exc:  # noqa: BLE001 - no real eligibility on an unconfirmed snapshot
            self.alert("warning", f"live: {fid}'s money band could not be confirmed ({type(exc).__name__})")
            confirmed = False
        if not confirmed:
            self._families_at = float("-inf")
            return "stale"
        if new != band:
            try:
                self.record("live.band", {"family": fid, "from": band, "to": new, "why": why}, agent=fid)
                if band == "candidate" and new in ("probe", "sized"):
                    moves = dict(self.state.get("band_moves", {}) or {})
                    moves[fid] = {"band": new, "at": self.clock()}   # onto real money: it trades from the next session
                    self.state.put("band_moves", moves)
            except Exception as exc:  # noqa: BLE001 - the band stays; tried again at the next refresh
                self.alert("warning", f"live: {fid}'s band could not be moved to {new} ({type(exc).__name__})")
                return band
        elif why and new == "candidate":
            # Held shadow-only: the reason is recorded once a day (the plan: "else shadow-only, with the reason recorded").
            told = dict(self.state.get("held_told", {}) or {})
            today = ny(self.clock()).date().isoformat()
            if told.get(fid) != today:
                told[fid] = today
                self.state.put("held_told", told)
                self.record("live.band", {"family": fid, "from": band, "to": band, "held": True, "why": why}, agent=fid)
        return new

    def _probe_sessions(self, fid: str, band: str) -> int:
        """Whole sessions a Probe family has spent at Probe (opened after its move there and closed since): the Probe
        is a real stage before Sized (`sized.min_probe_sessions`). A Probe with no recorded move counts from now."""
        if band != "probe":
            return 0
        now = self.clock()
        rec = (self.state.get("band_moves", {}) or {}).get(fid)
        try:
            promoted = self.families.promoted_at(fid)
        except Exception:  # no verified history means zero proven Probe sessions
            return 0
        stamps = ([float(rec["at"])] if rec and rec.get("band") in ("probe", "sized") else [])
        stamps += [promoted] if promoted is not None else []
        if stamps:
            since = max(stamps)
        else:
            # A Probe the live path did not move there itself (no record): its time at Probe counts from when it is first
            # seen at Probe (kept apart from `band_moves`, which decides when real money may start).
            seen = dict(self.state.get("probe_since", {}) or {})
            if fid not in seen:
                seen[fid] = now
                self.state.put("probe_since", seen)
            since = float(seen[fid])
        day, end, count = ny(since).date(), ny(now).date(), 0
        while day <= end:
            session = session_minutes(day)
            if session is not None and epoch_of(day, session[0]) >= since and epoch_of(day, session[1]) <= now:
                count += 1
            day += dt.timedelta(days=1)
        return count

    def _real_eligible(self, fid: str) -> bool:
        """A family moved to Probe (or Sized) trades real money from the session AFTER its move (the plan's Probe row:
        "real from its next session"): its move must precede the open of the current (or next) session."""
        move = (self.state.get("band_moves", {}) or {}).get(fid)
        now = self.clock()
        try:
            promoted = self.families.promoted_at(fid)
        except Exception:
            return False
        stamps = ([float(move["at"])] if move else []) + ([promoted] if promoted is not None else [])
        if not stamps:
            # Legacy/missing promotion metadata never confers same-session entry authority. Persist first sight so
            # restart keeps the waiting period, while an existing position retains its exit-only program.
            seen = dict(self.state.get("real_first_seen", {}) or {})
            if fid not in seen:
                seen[fid] = now
                self.state.put("real_first_seen", seen)
            stamps = [float(seen[fid])]
        since = max(stamps)
        day = ny(now).date()
        for _ in range(10):
            session = session_minutes(day)
            if session is not None and (day > ny(now).date() or now < epoch_of(day, session[1])):
                return since < epoch_of(day, session[0])
            day += dt.timedelta(days=1)
        return False

    def _persist_instance(self, inst: Instance) -> None:
        import json

        self.state.upsert("instances", {"id": inst.key, "family": inst.family, "version": inst.version, "run_sha": inst.run_sha,
                                        "code": inst.code, "params": json.dumps(inst.params, sort_keys=True), "band": inst.band,
                                        "tuition": int(inst.tuition), "mode": inst.mode, "created_at": self.clock(),
                                        "retired_at": None, "why": inst.error or None}, "id")

    def _retire_finished(self) -> None:
        for key, inst in list(self.instances.items()):
            if inst.kind == "shadow" and inst.mode == "wind_down":
                acc = self.shadow.accounts.get(key)
                if acc is None or (not acc.positions and not acc.orders):
                    if acc is not None:
                        self._export_one(acc)
                    self.shadow.accounts.pop(key, None)
                    self.decider.drop(key, budget_seconds=self._decision_budget())
                    self.instances.pop(key, None)
            elif inst.kind == "real" and inst.mode == "exit_only" and self.book is not None:
                if not self.book.instance_positions(key) and not self.book.instance_orders(key):
                    self.state.execute("UPDATE instances SET retired_at=? WHERE id=?", (self.clock(), key))
                    self.decider.drop(key, budget_seconds=self._decision_budget())
                    self.instances.pop(key, None)

    # ------------------------------------------------------------------ chains
    def _roots(self) -> dict[str, tuple[int, int, float]]:
        """Each root to read now, with the read window: (dte low, dte high, band)."""
        out: dict[str, list[float]] = {}
        for inst in self.instances.values():
            if inst.needs is None:
                continue
            for root in inst.needs.roots:
                w = out.setdefault(root, [inst.needs.dte_min, inst.needs.dte_max, inst.needs.band])
                w[0], w[1], w[2] = min(w[0], inst.needs.dte_min), max(w[1], inst.needs.dte_max), max(w[2], inst.needs.band)
        for acc in self.shadow.accounts.values():
            for pos in acc.positions.values():
                out.setdefault(pos.root, [0, 0, 0.02])
        if self.book is not None:
            for pos in self.book.positions.values():
                out.setdefault(pos.root, [0, 0, 0.02])
        if self.proof is not None and not self.proof.passed():
            w = out.setdefault("SPY", [1, 7, 0.01])
            w[1] = max(w[1], 7)
        margin_dte, margin_band = int(self.settings["read_dte_margin"]), float(self.settings["read_band_margin"])
        return {r: (int(max(0, w[0])), int(min(60, w[1] + margin_dte)), float(min(0.30, w[2] + margin_band))) for r, w in out.items()}

    def _read(self, day: LiveDay, mi: int, roots: Mapping[str, tuple[int, int, float]], out: dict) -> None:
        open_epoch = epoch_of(day.day, day.open_min)
        stocks = [r for r in roots if not uses_parity(r)] + (["SPY"] if any(uses_parity(r) for r in roots) and "SPY" not in roots else [])
        prices: dict[str, float] = {}
        if stocks:
            try:
                rows = self.market.stocks(stocks)
                prices = {s: stock_price(rows.get(s) or {}, not_before=open_epoch) for s in stocks}
            except Exception as exc:  # noqa: BLE001
                out.setdefault("data_errors", []).append(f"stocks: {type(exc).__name__}: {str(exc)[:120]}")
        held = self._held_symbols()
        changed = False
        levels = dict(self.state.get("levels", {}) or {})
        for root, (lo, hi, band) in roots.items():
            chain = day.chain(root)
            if not uses_parity(root):
                spot = prices.get(root, float("nan"))
            else:
                known = chain.underlying.price[: mi + 1]
                known = known[np.isfinite(known)]
                spot = float(known[-1]) if known.size else self._index_guess(root, prices)
            try:
                if math.isfinite(spot) and spot > 0:
                    rows = self.market.chain(root, expiry_from=(day.day + dt.timedelta(days=lo)).isoformat(),
                                             expiry_to=(day.day + dt.timedelta(days=hi)).isoformat(),
                                             strike_from=spot * (1 - band), strike_to=spot * (1 + band))
                else:
                    rows = self.market.chain(root, expiry_from=(day.day + dt.timedelta(days=lo)).isoformat(),
                                             expiry_to=(day.day + dt.timedelta(days=min(hi, lo + 1))).isoformat())
                extra = [s for s in held.get(root, ()) if s not in rows]
                if extra:
                    rows.update(self.market.contracts(extra))
            except Exception as exc:  # noqa: BLE001 - this root has no snapshot this minute
                out.setdefault("data_errors", []).append(f"{root}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            changed |= chain.record(mi, rows, open_epoch=open_epoch)
            level = chain.parity(mi, spot) if uses_parity(root) else spot
            chain.set_price(mi, level)
            if math.isfinite(level):
                levels[root] = [level, self.clock()]
            self._history(day, root, level, prices.get("SPY", float("nan")))
        if levels:
            self.state.put("levels", levels)
        if changed:
            day.remap(self.shadow.accounts.values())
        out["data_calls"] = self.market.minute_calls.used()

    def _index_guess(self, root: str, prices: Mapping[str, float]) -> float:
        spy = prices.get("SPY", float("nan"))
        if not math.isfinite(spy):
            return float("nan")
        return spy * (10.0 if root in ("SPXW", "SPX") else 1.0)

    def _held_symbols(self) -> dict[str, set[str]]:
        """Every contract a book holds or works, real AND shadow: read each minute whatever the programs' windows (in
        the Gym NEEDS limits only what a program sees; fills, marks and closes use the whole chain)."""
        out: dict[str, set[str]] = {}
        for acc in self.shadow.accounts.values():
            for pos in acc.positions.values():
                for leg, exp in zip(pos.legs, pos.expirations):
                    out.setdefault(pos.root, set()).add(occ_symbol(pos.root, from_ordinal(int(exp)).isoformat(), leg.is_call, leg.strike))
            for work in acc.orders.values():
                for leg in work.order.legs:
                    exp = self.day.ordinal + leg.dte if self.day is not None else None
                    if exp is not None:
                        out.setdefault(work.order.root, set()).add(
                            occ_symbol(work.order.root, from_ordinal(exp).isoformat(), leg.is_call, leg.strike))
        if self.book is not None:
            for pos in self.book.positions.values():
                out.setdefault(pos.root, set()).update(leg.symbol for leg in pos.legs)
            for order in self.book.orders.values():
                out.setdefault(order.root, set()).update(leg.symbol for leg in order.legs)
        if self.proof is not None:
            out.setdefault("SPY", set()).update(self.proof.held_symbols())
        return out

    # ------------------------------------------------------------------ the session minute
    def _session_minute(self, day: LiveDay, mi: int, now: float, out: dict) -> None:
        day.advance(mi)
        if self.real is not None:
            self._read_account(out)
        self.sync_families(now)
        roots = self._roots()
        self._read(day, mi, roots, out)
        jobs: list[dict] = []
        shadow_due = self._shadow_jobs(day, mi - 1, jobs)
        real_due: dict[str, Instance] = {}
        if self.book is not None:
            self._real_pre(day, mi, now, out)
        self._paper_proof(day, mi, out)
        if self.book is not None:
            for key, inst in self.instances.items():
                if inst.kind != "real" or inst.error or inst.needs is None:
                    continue
                if mi not in self._schedule(inst, day):
                    continue
                job = self._real_job(inst, day, mi)
                if job is not None:
                    job["mi"] = mi
                    jobs.append(job)
                    real_due[key] = inst
        results = self._decide(day, jobs, out)
        for key, acc in shadow_due.items():
            answer = results.get(key) or {}
            self._isolated(key, lambda: (self._stats(key, answer), self._shadow_intents(key, acc, day, mi - 1, answer.get("intents") or [])))
        for key, inst in real_due.items():
            answer = results.get(key) or {}
            self._isolated(key, lambda: (self._stats(key, answer),
                                         self._real_intents(inst, day, mi, answer.get("intents") or [], out)))
        self._export_shadow()
        self._export_real()
        self._retire_finished()
        self.shadow.save()
        out["shadow"] = {"instances": len(self.shadow.accounts), "decided": len(shadow_due),
                         "open": sum(len(a.positions) for a in self.shadow.accounts.values())}
        if self.book is not None:
            out["real"] = {"instances": sum(1 for i in self.instances.values() if i.kind == "real"), "decided": len(real_due),
                           "open": len(self.book.positions), "working": len(self.book.orders), "frozen": self.book.frozen or None,
                           "orders_today": self.book.count_today(day.day.isoformat())}
        out["blocked"] = self.real_block() or None

    def _shadow_jobs(self, day: LiveDay, smi: int, jobs: list[dict]) -> dict[str, ShadowAccount]:
        """The shadow book steps ONE MINUTE BEHIND the wall clock: at wall minute m it steps minute m - 1, so the Gym's
        engine, which reads the minute after a decision to judge a passive fill (adverse selection), finds that row
        recorded, exactly as it does in a replay of a stored day. Returns the accounts deciding at `smi`."""
        due: dict[str, ShadowAccount] = {}
        if smi < 0:
            return due
        for key, acc in list(self.shadow.accounts.items()):
            inst = self.instances.get(key)
            if acc.began_day != day.ordinal:
                acc.begin_day(day)
                acc.began_day = day.ordinal
                acc.last_mi = -1
            if smi <= acc.last_mi:
                continue
            if inst is not None and inst.mode == "live":
                try:
                    with self.families.admit_open(self._entry_identity(inst), real=False) as allowed:
                        if not allowed:
                            inst.mode = "wind_down"
                except Exception:  # noqa: BLE001 - missing entry permission never blocks an owned exit
                    inst.mode = "wind_down"
                    acc._reject("its entry eligibility could not be read")
            try:
                if inst is None or inst.mode == "wind_down":
                    acc.wind_down(day, smi)  # withdraw old shadow opens before this minute can fill them
                acc.pre(day, smi)
            except Exception as exc:  # noqa: BLE001 - one account's trouble stays its own
                self._isolated(key, lambda exc=exc: (_ for _ in ()).throw(exc))
                continue
            if inst is None or inst.mode == "wind_down" or acc.winding_down:
                if not acc.winding_down or any(not p.closing for p in acc.positions.values()):
                    acc.wind_down(day, smi)
                continue
            if inst.error or smi not in acc.decision_minutes(day):
                continue
            job = acc.job(day, smi)
            if job is not None:
                job["key"], job["mi"] = key, smi
                jobs.append(job)
                due[key] = acc
        return due

    @staticmethod
    def _entry_identity(inst: Instance) -> dict[str, Any]:
        return {"family": inst.family, "version": inst.version, "code": inst.code, "params": inst.params,
                "band": inst.band, "tuition": inst.tuition}

    def _shadow_intents(self, key: str, acc: ShadowAccount, day: LiveDay, mi: int,
                        intents: Iterable[Mapping[str, Any]]) -> None:
        inst = self.instances.get(key)
        for intent in intents:
            if isinstance(intent, Mapping) and "open" in intent:
                if inst is None or inst.mode != "live":
                    acc._reject("its family or version is no longer eligible to open")
                    continue
                try:
                    with self.families.admit_open(self._entry_identity(inst), real=False) as allowed:
                        if allowed:
                            acc.apply(day, mi, [intent])
                        else:
                            inst.mode = "wind_down"
                            acc._reject("its family or version is no longer eligible to open")
                except Exception:  # noqa: BLE001 - the rest of this batch may contain an owned close
                    inst.mode = "wind_down"
                    acc._reject("its entry eligibility could not be read")
            else:
                acc.apply(day, mi, [intent])  # owned closes and cancellations do not need entry permission
        if inst is None or inst.mode == "wind_down":
            acc.wind_down(day, mi)

    def _decide(self, day: LiveDay, jobs: list[dict], out: dict) -> dict[str, dict]:
        if not jobs:
            return {}
        minutes = {job["mi"] for job in jobs}
        snaps = {(r, m): day.snapshot(r, m) for r in day.chains for m in minutes}
        snaps = {k: v for k, v in snaps.items() if v is not None}
        histories = {inst.needs.history for inst in self.instances.values() if inst.needs is not None}
        unders = {(r, h, m): day.under(r, m, h) for (r, m) in snaps for h in histories}
        try:
            jobs.sort(key=lambda job: self.instances[job["key"]].kind != "real")
            return self.decider.decide(snaps, unders, jobs, budget_seconds=self._decision_budget())
        except DeciderError as exc:
            out["decider"] = str(exc)[:200]
            self.alert("warning", f"live: {exc}")
            return {}

    def _closing_minute(self, day: LiveDay, mi: int, now: float, out: dict) -> None:
        """16:00 (13:00 on a half day): the close's row read, the shadow book's last minute stepped (and asked, as
        the engine asks a program at its last decision minute); no real decision."""
        day.advance(mi)
        self._read(day, mi, self._roots(), out)
        jobs: list[dict] = []
        due = self._shadow_jobs(day, mi - 1, jobs)
        results = self._decide(day, jobs, out)
        for key, acc in due.items():
            answer = results.get(key) or {}
            self._isolated(key, lambda: (self._stats(key, answer), self._shadow_intents(key, acc, day, mi - 1, answer.get("intents") or [])))
        self._export_shadow()
        self.shadow.save()

    def _isolated(self, key: str, work: Callable[[], Any]) -> None:
        """One instance's part of the minute: whatever it raises stays its own (the rest of the minute goes on)."""
        try:
            work()
        except Exception as exc:  # noqa: BLE001
            self.alert("warning", f"live: {key}'s minute failed ({type(exc).__name__}: {str(exc)[:160]})")
            self.state.event("live.error", {"instance": key, "error": f"{type(exc).__name__}: {exc}",
                                            "trace": traceback.format_exc()[-2000:]})

    def _stats(self, key: str, answer: Mapping[str, Any]) -> None:
        inst = self.instances.get(key)
        if inst is None:
            return
        if answer.get("missing") and not inst.error:
            # The decider lost the program (a restart whose reload failed): loaded again at the next families pass.
            inst.error = "the decider failed: the program was not loaded in the decider"
            inst.error_since = self.clock()
            self._families_at = float("-inf")
        if isinstance(answer.get("stats"), Mapping):
            inst.stats = dict(answer["stats"])
            if inst.stats.get("disqualified") and not inst.fatal:
                inst.error, inst.fatal = f"disqualified: {inst.stats['disqualified']}", True
                if inst.kind == "real":
                    inst.mode = "exit_only"
                    self._persist_instance(inst)
                self.record("live.instance", {"instance": key, "family": inst.family, "error": inst.error}, agent=inst.family)
        if inst.error:
            self._cancel_inactive_opens()

    def _schedule(self, inst: Instance, day: LiveDay) -> set[int]:
        needs = inst.needs
        first = max(needs.start, day.open_min + 1) - day.open_min
        last = min(needs.end - day.open_min, day.minutes - 3)
        return set(range(first, last + 1, needs.cadence)) if first <= last else set()

    # ------------------------------------------------------------------ the real account's minute
    def _real_pre(self, day: LiveDay, mi: int, now: float, out: dict) -> None:
        book = self.book
        assert book is not None and self.real is not None
        today = day.day.isoformat()
        try:
            rows = self.real.orders(status="all", after=dt.datetime.fromtimestamp(epoch_of(day.day, 0), dt.timezone.utc).isoformat())
            foreign = book.ingest(rows)
            book.look_up(today=today, seen=[str(r.get("client_order_id") or "") for r in rows])
        except Exception as exc:  # noqa: BLE001
            foreign = None
            out.setdefault("venue_errors", []).append(f"orders: {type(exc).__name__}: {str(exc)[:120]}")
        try:
            positions = self.real.positions()
        except Exception as exc:  # noqa: BLE001
            positions = None
            out.setdefault("venue_errors", []).append(f"positions: {type(exc).__name__}: {str(exc)[:120]}")
        self._activities(now)
        if self._activities_changed:
            positions = self._positions_again(out)
        if positions is not None and foreign is not None:
            before = book.frozen
            book.reconcile(positions, foreign, day=day.day, after_close=False, shares=self.state.get("shares", {}) or {})
            if book.frozen and not before:
                self.alert("error", f"live: real entries frozen: {book.frozen}")
                self._tell_owner("reconciliation", book.frozen)
        funding_confirmed = False
        if self._flows(now) and self.flows is not None and (
                self.stops.flow_rows != self.flows.rows or self.stops.flow_transition_at is not None):
            # A newly executed funding activity may post after this minute's first account read. Bracket a fresh
            # equity read with two matching funding snapshots before allowing either stop to latch on that equity.
            funding_before = self.flows.rows
            self._read_account(out)
            if self.account_row is not None:
                self._flows_at = float("-inf")
                funding_confirmed = self._flows(self.clock()) and self.flows.rows == funding_before
        if self.account_row is not None:
            try:
                before = (self.stops.daily_tripped, self.stops.drawdown_tripped)
                self.stops.observe(self.table, at=self._account_at if self._account_at is not None else now,
                                   day=today, equity=M.D(self.account_row["equity"]),
                                   last_equity=M.D(self.account_row.get("last_equity") or self.account_row["equity"]),
                                   flows=self.flows, funding_confirmed=funding_confirmed)
                self.state.put("stops", self.stops.as_state())
                if self.stops.drawdown_tripped and not before[1]:
                    self.alert("error", f"live: {self.stops.drawdown_why}; real money paused")
                    self.record("live.stop", {"stop": "drawdown", "why": self.stops.drawdown_why})
                    self._tell_owner("drawdown", self.stops.drawdown_why)
                if self.stops.daily_tripped and not before[0]:
                    self.alert("error", f"live: {self.stops.daily_why}; no new real entry today")
                    self.record("live.stop", {"stop": "daily", "why": self.stops.daily_why})
                    self._tell_owner("daily", self.stops.daily_why)
                if self.stops.provisional and self.flows is not None:
                    self._flows_at = float("-inf")  # read the flows again at once: a breach waits on them
            except (ValueError, ArithmeticError) as exc:
                out.setdefault("venue_errors", []).append(f"stops: {exc}")
        self._venue_rules(day, mi, out)

    def _paper_proof(self, day: LiveDay, mi: int, out: dict) -> None:
        """The paper venue proves its route while real execution remains disabled, including recovery."""
        if self.proof is not None and not self.proof.passed() and "SPY" in day.chains:
            try:
                out["paper_proof"] = self.proof.step(day=day.day.isoformat(), mi=mi, snap=day.snapshot("SPY", mi), chain=day.chains["SPY"]).get("status")
            except Exception as exc:  # noqa: BLE001
                out["paper_proof"] = f"error: {type(exc).__name__}"

    def _read_account(self, out: dict) -> None:
        try:
            self.account_row = self.real.account()
            self._account_at = self.clock()
        except Exception as exc:  # noqa: BLE001
            self.account_row = None
            out.setdefault("venue_errors", []).append(f"account: {type(exc).__name__}: {str(exc)[:120]}")

    def _positions_again(self, out: dict) -> list[dict] | None:
        try:
            return self.real.positions()
        except Exception as exc:  # noqa: BLE001
            out.setdefault("venue_errors", []).append(f"positions: {type(exc).__name__}: {str(exc)[:120]}")
            return None

    def _flows(self, now: float) -> bool:
        if self.real is None or not self.start_at or now - self._flows_at < FLOWS_EVERY:
            return False
        self._flows_at = now
        from ltcm.performance import ALPACA_FUNDING

        try:
            rows = self.real.activities(sorted(ALPACA_FUNDING), after=self.start_at)
            read_at = self.clock()
            flows, unsettled, pending_amounts = [], [], []
            start = parse_time(self.start_at) or 0.0
            for r in rows:
                when = parse_time(r.get("transaction_time") or r.get("created_at") or (str(r.get("date")) + "T00:00:00Z"))
                amount = M.D(r.get("net_amount") or 0)
                status = str(r.get("status") or "executed").lower()
                if when is None or when <= start or status in ("canceled", "cancelled", "failed", "rejected"):
                    continue
                if status not in ("executed", "complete", "completed"):
                    # As `ltcm.performance` reads funding: only a settled flow is netted; a pending one settles nothing.
                    unsettled.append(f"{r.get('activity_type')} {amount} {status}")
                    pending_amounts.append(amount)
                    continue
                flows.append((when, amount))
            closes = []
            d = ny(now).date()
            for back in range(0, 10):
                day = d - dt.timedelta(days=back)
                session = session_minutes(day)
                if session is not None:
                    closes.append(epoch_of(day, session[1]))
            self.flows = M.FlowBook(read_at=read_at, rows=tuple(sorted(flows)), closes=tuple(sorted(closes)),
                                    unsettled=tuple(unsettled), pending_amounts=tuple(pending_amounts))
            return True
        except Exception as exc:  # noqa: BLE001 - the stops wait on a reading (provisional only)
            self.alert("warning", f"live: the account's funding could not be read ({type(exc).__name__}: {str(exc)[:120]})")
            return False

    def _activities(self, now: float) -> None:
        """Assignments and exercises (OPASN, OPEXC): the account now holds shares it cannot carry, and a structure is
        broken. Real entries freeze, the owner is told, and the shares are closed at once (the only stock order the
        live path sends)."""
        self._activities_changed = False
        if self.real is None or now - self._activities_at < ACTIVITIES_EVERY:
            return
        self._activities_at = now
        # Read from a cursor (the latest event's day, less a day) once one is stored, never again from the reset: the ids
        # seen are kept by day and pruned with it, so an old assignment is never read twice however many events follow.
        # Before the first event, from the reset itself (`start_at`): an event before it is not this run's.
        cursor = str(self.state.get("activities_cursor") or "")
        seen: dict[str, str] = dict(self.state.get("activities_seen_by_day", {}) or {})
        since = parse_time(self.start_at) if self.start_at else None
        after = (dt.date.fromisoformat(cursor) - dt.timedelta(days=1)).isoformat() if cursor else (self.start_at or None)
        try:
            rows = self.real.activities(list(OPTION_EVENTS), after=after)
        except Exception as exc:  # noqa: BLE001
            self.alert("warning", f"live: option events could not be read ({type(exc).__name__})")
            return

        def event_day(r: Mapping[str, Any]) -> str:
            return str(r.get("date") or r.get("transaction_time") or "")[:10]

        def this_runs(r: Mapping[str, Any]) -> bool:
            if since is not None:
                stamp = parse_time(r.get("transaction_time"))
                if stamp is not None and stamp <= since:
                    return False
                # A dated event on the reset's own day cannot be placed before or after it: it is taken (an assignment
                # missed costs more than one handled twice; the owner is told either way).
                if stamp is None and event_day(r) and event_day(r) < str(self.start_at)[:10]:
                    return False
            return not cursor or not event_day(r) or event_day(r) >= str(after)

        fresh = [r for r in rows if str(r.get("id")) not in seen and this_runs(r)]
        for r in fresh:
            seen[str(r.get("id"))] = event_day(r)
            kind, symbol = str(r.get("activity_type")), str(r.get("symbol") or "").upper()
            self.record("live.option_event", {"kind": kind, "symbol": symbol, "qty": str(r.get("qty")), "_row": dict(r)})
            contracts = abs(int(M.D(r.get("qty") or 0)))
            if self.book is not None and contracts:
                value = 0.0
                if kind in ("OPASN", "OPEXC"):
                    value = self._intrinsic_now(symbol)
                found = self.book.remove_contracts(symbol, contracts, value_share=value,
                                                   why={"OPEXP": "expired", "OPASN": "assigned", "OPEXC": "exercised"}.get(kind, kind))
                if found < contracts and kind != "OPEXP":
                    self.record("live.alert", {"what": f"{kind} of {contracts} {symbol}: the book held {found}"})
            if kind in ("OPASN", "OPEXC"):
                why = f"{'an assignment' if kind == 'OPASN' else 'an exercise'} on {symbol} ({r.get('qty')} contracts)"
                self.state.put("assignment_latch", {"why": why, "at": now})
                self.alert("error", f"live: {why}: real entries frozen until it is resolved; its shares are closed and the "
                                    "structure's other legs closed alone")
                self._tell_owner("assignment", why)
        days = [d for d in seen.values() if d]
        if days:
            cursor = max(days + ([cursor] if cursor else []))
            floor = (dt.date.fromisoformat(cursor) - dt.timedelta(days=3)).isoformat()
            seen = {k: d for k, d in seen.items() if not d or d >= floor}
            self.state.put("activities_cursor", cursor)
        self.state.put("activities_seen_by_day", seen)
        self._activities_changed = bool(fresh)
        self._close_shares()
        self._resolve_latch()

    def _intrinsic_now(self, symbol: str) -> float:
        """An option's intrinsic value a share at the underlying's price now (0 when it cannot be read)."""
        parts = occ_parts(symbol)
        if parts is None:
            return 0.0
        root, _, is_call, strike = parts
        try:
            if uses_parity(root):
                chain = self.day.chains.get(root) if self.day is not None else None
                prices = chain.underlying.price[np.isfinite(chain.underlying.price)] if chain is not None else np.zeros(0)
                level = float(prices[-1]) if prices.size else float("nan")
            else:
                level = stock_price(self.market.stocks([root]).get(root) or {})
        except Exception:  # noqa: BLE001
            level = float("nan")
        if not math.isfinite(level):
            return 0.0
        return max(0.0, level - strike) if is_call else max(0.0, strike - level)

    def _resolve_latch(self) -> None:
        """An assignment's latch lifts by itself once it is resolved: no broken structure left, no shares held, and a
        clean reconciliation (the owner has been told either way; `--clear-assignment` lifts it by hand)."""
        latch = self.state.get("assignment_latch")
        if not latch or self.book is None:
            return
        broken = [p for p in self.book.positions.values() if p.info.get("broken")]
        shares = self.state.get("shares", {}) or {}
        if not broken and not any(shares.values()) and not self._stock_held and not self.book.frozen and not self.book.mismatch:
            self.state.execute("DELETE FROM kv WHERE key='assignment_latch'")
            self.record("live.stop", {"stop": "assignment", "released": True, "why": f"resolved: {latch.get('why')}"})

    def _close_shares(self) -> None:
        """Any stock position on the account (an assignment's or an exercise's) closed at once with a market order."""
        if self.real is None:
            return
        try:
            positions = self.real.positions()
            working = {str(o.get("symbol") or "").upper() for o in self.real.orders(status="open")}
        except Exception:  # noqa: BLE001
            self._stock_held = True   # unread: not known to be clear
            return
        self._stock_held = any(str(r.get("asset_class")) == "us_equity" and M.D(r.get("qty") or 0) != 0 for r in positions)
        for row in positions:
            if str(row.get("asset_class")) != "us_equity" or str(row.get("symbol") or "").upper() in working:
                continue
            qty = M.D(row.get("qty") or 0)
            if qty == 0:
                continue
            side = "sell" if str(row.get("side")) != "short" and qty > 0 else "buy"
            body = {"symbol": str(row["symbol"]), "qty": str(abs(qty)), "side": side, "type": "market", "time_in_force": "day",
                    "client_order_id": f"lv-shares-{str(row['symbol']).lower()}-{int(self.clock())}"}
            answer = self.real.submit(body, exit=True)
            self.record("live.shares", {"symbol": row["symbol"], "qty": str(qty), "side": side, "ok": answer.ok,
                                        "error": answer.error})

    def _venue_rules(self, day: LiveDay, mi: int, out: dict) -> None:
        """Expiry-day closes, the open cutoff's cancels, tif expiries, and orphans' closes (exits: the kill switch only)."""
        book = self.book
        assert book is not None
        minute = day.open_min + mi
        today = day.day.isoformat()
        killed = self._killed()
        for order in list(book.orders.values()):
            if order.status != "working" or order.venue_id is None:
                continue
            rules = day.rules.get(order.root) or V.rules_for(order.root, open_minute=day.open_min, close_minute=day.close_min)
            expiring = any(leg.expiry == today for leg in order.legs)
            age = mi - order.placed_minute if order.day == today else 10_000
            if order.action == "open" and expiring and minute >= rules.open_cutoff:
                book.cancel(order, "the open cutoff for expiring contracts")
            elif order.action == "close" and not order.forced and expiring and minute >= rules.close_cutoff:
                book.cancel(order, "the close cutoff for expiring contracts (the Gym drops it there too)")
            elif order.tif is not None and age >= max(1, order.tif) and (not order.forced or order.action == "close_leg"):
                book.cancel(order, f"its time in force ({order.tif} minutes) ran out")
            elif order.action == "open" and (shut := self.real_block(opening=True)) and not shut.startswith("the account could not be read"):
                book.cancel(order, f"real entries are shut: {shut}")
        if killed:
            out["kill_switch"] = True
            return
        self._pending_exits(day, mi, out)
        for pos in sorted(book.positions.values(), key=lambda p: (not p.info.get("broken"), p.pid)):
            if pos.qty > 0 and pos.info.get("broken"):
                self._close_broken(pos, day, mi, out)
                continue
            if pos.qty <= 0 or pos.status != "open":
                continue
            rules = day.rules.get(pos.root) or V.rules_for(pos.root, open_minute=day.open_min, close_minute=day.close_min)
            inst = self.instances.get(pos.instance)
            orphan = inst is None or inst.fatal
            expiring = pos.expiry == today
            force_why = self._expiry_close(pos, day, mi, minute)
            if not force_why and orphan:
                force_why = f"its program is gone ({inst.error if inst else 'no instance'}): the House closes it"
            if not force_why:
                continue
            if minute >= rules.close_cutoff and expiring:
                if not pos.info.get("cutoff_told"):
                    pos.info["cutoff_told"] = True
                    self.alert("error", f"live: {pos.family}'s {pos.type} expiring today is still open past the close cutoff")
                continue
            working = book.closing_order(pos.pid)
            if working is not None:
                if not working.forced:
                    # A program's own close (a mid or better limit, a day order) never stands in the House's way.
                    book.cancel(working, f"the House closes it: {force_why}")
                elif mi - working.placed_minute >= 1:
                    book.cancel(working, "re-priced at the natural")
                continue
            # One position's failure never stops the other forced closes.
            self._isolated(pos.instance, lambda pos=pos, why=force_why: self._send_close(pos, day, mi, forced=True, why=why, out=out))

    def _expiry_close(self, pos: RPosition, day: LiveDay, mi: int, minute: int) -> str:
        """Why the House closes this expiring equity structure itself now, or "": in the window before the close cutoff
        (`expiry_close_lead_minutes`) with a leg in or near the money, or no underlying price to tell. One predicate for
        the House's forced close (`_venue_rules`) and for refusing a program's own close of it (`_real_intent`)."""
        rules = day.rules.get(pos.root) or V.rules_for(pos.root, open_minute=day.open_min, close_minute=day.close_min)
        today = day.day.isoformat()
        if not (pos.expiry == today and rules.kind == "equity"
                and rules.close_cutoff - self.table.expiry_close_lead_minutes <= minute):
            return ""
        snap = day.snapshot(pos.root, mi)
        spot = snap.spot if snap is not None else float("nan")
        near = [leg.symbol for leg in pos.legs if leg.expiry == today and _near_money(leg, spot, float(self.table.near_money_share))]
        if near or not math.isfinite(spot):
            return (f"expiring equity options with a leg in or near the money ({', '.join(near) or 'no price'}): "
                    f"closed before {rules.close_cutoff // 60}:{rules.close_cutoff % 60:02d} ET")
        return ""

    def _program_close_refusal(self, pos: RPosition, day: LiveDay, mi: int) -> str | None:
        """The expiry rules a program's own close meets (arriving at the next minute, as the Gym's does): the House's
        expiry close has it, or closing orders on expiring contracts have ended."""
        minute = day.open_min + mi + 1
        if self._expiry_close(pos, day, mi, minute):
            return "close: the House is closing this expiring structure (a leg in or near the money) at the natural"
        rules = day.rules.get(pos.root)
        if rules is not None and pos.expiry == day.day.isoformat() and minute >= rules.close_cutoff:
            return (f"expiry cutoff: closing orders on expiring contracts end at {rules.close_cutoff // 60}:"
                    f"{rules.close_cutoff % 60:02d} ET")
        return None

    def _pending_exits(self, day: LiveDay, mi: int, out: dict) -> None:
        """Exits waiting for their contracts (another family's open being cancelled for them, or another close): sent as
        soon as the stream is free, before any new open."""
        book = self.book
        assert book is not None
        if not self.pending_exits:
            return
        today = day.day.isoformat()
        for pid, want in sorted(self.pending_exits.items(), key=lambda item: (not item[1].get("forced"), item[1].get("queued_at", 0))):
            # Taken off the list first: `_send_close` puts it back only when its contracts are still busy (it waits on).
            self.pending_exits.pop(pid, None)
            pos = book.positions.get(pid)
            if pos is None or pos.qty <= 0 or book.closing_order(pid) is not None:
                continue
            if want.get("day") != today:
                why = "your close waited past the session's end for its contracts and was dropped: send it again"
            elif pos.info.get("broken"):
                why = f"close: this structure is broken ({pos.info['broken']}): the House closes its legs"
            elif not want.get("forced") and (late := self._program_close_refusal(pos, day, mi)):
                why = late                                 # the rules a program's close meets, as when it was sent
            else:
                try:
                    why = self._send_close(pos, day, mi, forced=bool(want.get("forced")), why=str(want.get("why") or ""),
                                           out=out, intent=want.get("intent"), pending=True, queued_at=want.get("queued_at"))
                except Exception as exc:  # noqa: BLE001 - one waiting exit never stops the minute (or the others)
                    why = f"the waiting close failed: {type(exc).__name__}: {str(exc)[:160]}"
                    self.state.event("live.error", {"instance": pos.instance, "error": why,
                                                    "trace": traceback.format_exc()[-2000:]})
            if why is None or pid in self.pending_exits:
                continue                                   # sent, or still waiting for its contracts
            if not want.get("forced"):
                # Refused now for another reason: the program is told, as for any refused close (it may send it again).
                book._reject(pos.instance, why)
                self.record("live.refusal", {"instance": pos.instance, "family": pos.family, "why": why[:300],
                                             "_intent": {k: v for k, v in (want.get("intent") or {}).items() if k != "note"}},
                            agent=pos.family)
        self._save_pending()

    def _save_pending(self) -> None:
        self.state.put("pending_exits", {str(k): v for k, v in self.pending_exits.items()})

    def _pending_symbols(self) -> set[str]:
        if self.book is None:
            return set()
        return {leg.symbol for pid in self.pending_exits for leg in (self.book.positions[pid].legs if pid in self.book.positions else [])}

    def _close_broken(self, pos: RPosition, day: LiveDay, mi: int, out: dict) -> None:
        """A structure an assignment, exercise or expiry broke: each leg it still holds closed alone at the touch. Every
        SHORT leg first (bought back at its ask), and no long leg is sold while any short leg is still held, sent, busy
        or unpriced: a long leg sold first would leave a naked short. Then the long legs (sold at the bid; one bid at
        nothing is left to expire, worthless and riskless). A leg is sent at most every `BROKEN_RESEND_MINUTES`."""
        book = self.book
        assert book is not None
        chain, snap = day.chains.get(pos.root), day.snapshot(pos.root, mi)
        now = self.clock()
        # When each leg was last sent (epoch seconds): a gap of `BROKEN_RESEND_MINUTES` whatever the day.
        sent_at = dict(pos.info.get("leg_sent") or {})
        shorts = [leg for leg in pos.legs if leg.side < 0 and book.leg_remaining(pos, leg) > 0]
        todo = shorts or [leg for leg in pos.legs if leg.side > 0 and book.leg_remaining(pos, leg) > 0]
        for leg in todo:
            left = book.leg_remaining(pos, leg)
            if self._yield_contracts(pos, [leg], forced=True, queued_at=now):
                continue
            if leg.symbol in book.busy() or now - float(sent_at.get(leg.symbol, float("-inf"))) < BROKEN_RESEND_MINUTES * 60 - 1:
                continue
            if chain is None or snap is None:
                continue
            i = chain.column(leg.symbol)
            price = float(snap.bid[i] if leg.side > 0 else snap.ask[i]) if i >= 0 else float("nan")
            if not math.isfinite(price) or price <= 0:
                continue
            sent = book.new_order(instance=pos.instance, family=pos.family, action="close_leg", type_=pos.type, root=pos.root,
                                  legs=[RLeg(leg.symbol, leg.side, 1, leg.is_call, leg.strike, leg.expiry, leg.key)], qty=left,
                                  limit_value=price, tif=1, day=day.day.isoformat(), minute=mi, pid=pos.pid, forced=True,
                                  why=f"broken structure: {pos.info.get('broken')}")
            book.send(sent)
            sent_at[leg.symbol] = now
            out.setdefault("orders", []).append({"oid": sent.oid, "family": pos.family, "action": "close_leg", "status": sent.status})
        if sent_at != (pos.info.get("leg_sent") or {}):
            pos.info["leg_sent"] = sent_at
            book._save_position(pos)

    def _yield_contracts(self, pos: RPosition, legs: list[RLeg], *, forced: bool, queued_at: float) -> bool:
        book = self.book
        assert book is not None
        blockers = book.blockers(legs, pid=pos.pid)
        for other in blockers:
            if other.action == "open" or (not other.forced and (forced or self.clock() - queued_at >= EXIT_PREEMPT_SECONDS)):
                why = "an exit needs this contract"
                if book.cancel(other, why):
                    book._reject(other.instance, f"your {other.action} was cancelled: {why}")
        return bool(blockers)

    def _send_close(self, pos: RPosition, day: LiveDay, mi: int, *, forced: bool, why: str, out: dict,
                    intent: Mapping[str, Any] | None = None, pending: bool = False,
                    queued_at: float | None = None) -> str | None:
        book = self.book
        assert book is not None
        rules = day.rules.get(pos.root) or V.rules_for(pos.root, open_minute=day.open_min, close_minute=day.close_min)
        if pos.expiry == day.day.isoformat() and day.open_min + mi >= rules.close_cutoff:
            self.pending_exits.pop(pos.pid, None)
            return "expiry cutoff: the waiting close cannot be sent after the close cutoff"
        if queued_at is None:
            queued_at = float(self.pending_exits.get(pos.pid, {}).get("queued_at", self.clock()))
        if self._yield_contracts(pos, pos.legs, forced=forced, queued_at=queued_at):
            self.pending_exits[pos.pid] = {"forced": forced, "why": why, "intent": dict(intent) if intent else None,
                                           "day": day.day.isoformat(), "queued_at": queued_at}
            self._save_pending()
            return "the close waits for its contracts (another order works on them); the House sends it"
        chain = day.chains.get(pos.root)
        if chain is None:
            return "no chain for this root now"
        idx = chain.index_of(np.array([leg.key for leg in pos.legs], dtype=np.int64))
        if (idx < 0).any():
            return "a leg of this position is not in today's chain"
        snap = day.snapshot(pos.root, mi)
        if forced:
            # A forced close must go even when this minute's read failed: the latest minute of the last five whose
            # quotes cover every leg prices it (the concession grows each try).
            for back in range(0, 6):
                candidate = day.snapshot(pos.root, mi - back) if mi - back >= 0 else None
                if candidate is not None and bool(np.isfinite(candidate.bid[idx]).all() and np.isfinite(candidate.ask[idx]).all()):
                    snap = candidate
                    break
        if snap is None:
            return "no chain for this root now"
        legs = tuple(L.LegFill(int(i), leg.key, leg.side, leg.ratio, 0, leg.strike, leg.is_call) for leg, i in zip(pos.legs, idx))
        rules = day.rules[pos.root]
        try:
            order = L.resolve_close(dict(intent or {"close": pos.pid, "limit": "natural"}), pos.type, legs, pos.qty, snap, rules,
                                    position=pos.pid)
        except L.Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - a malformed close is refused, never raised into the minute
            return f"a malformed close: {type(exc).__name__}: {str(exc)[:160]}"
        value = order.limit
        if forced:
            tries = int(pos.info.get("forced_tries") or 0)
            value = round(order.natural - 0.01 * min(10, tries), 2)
            pos.info["forced_tries"] = tries + 1
            book._save_position(pos)
        # A close's limit stays one the gateway takes: a debit structure is never paid to be given away (its close
        # receives zero at worst), and a credit structure's buy-back stays under its collateral.
        if pos.type in L.CREDIT:
            value = max(value, round(-(pos.collateral - 0.01), 2))
        else:
            value = max(0.0, value)
        refusal = book.path_refusal(pos.legs, opening=False, day=day.day.isoformat(), house=forced)
        if refusal:
            return refusal
        if self._killed():
            return "the gateway's kill switch is engaged"
        # An exit is never refused on the instance's order budget (it limits opens); it is charged when it went.
        tif = order.tif if not forced else None
        sent = book.new_order(instance=pos.instance, family=pos.family, action="close", type_=pos.type, root=pos.root,
                              legs=list(pos.legs), qty=order.qty, limit_value=value, tif=tif, day=day.day.isoformat(),
                              minute=mi, pid=pos.pid, forced=forced, fees_est=order.fees, why=why)
        book.send(sent)
        if not forced and sent.dispatched:
            self._instance_spent(pos.instance, day)
        out.setdefault("orders", []).append({"oid": sent.oid, "family": pos.family, "action": "close", "status": sent.status})
        return None if sent.status in ("working", "filled", "unknown") else f"{sent.status}: {sent.answer.get('error')}"

    def _instance_budget(self, instance: str, day: LiveDay) -> bool:
        """A real instance's orders a day, as the Gym allows a program (`instance_orders_day`, the engine's 60): charged
        for every order that reached the venue (`dispatched`: not a House or gateway refusal), checked for opens only."""
        row = self.state.get("instance_orders", {}) or {}
        used = int((row.get("counts") or {}).get(instance, 0)) if row.get("day") == day.day.isoformat() else 0
        return used < int(self.settings["instance_orders_day"])

    def _instance_spent(self, instance: str, day: LiveDay) -> None:
        row = self.state.get("instance_orders", {}) or {}
        if row.get("day") != day.day.isoformat():
            row = {"day": day.day.isoformat(), "counts": {}}
        row["counts"][instance] = int(row["counts"].get(instance, 0)) + 1
        self.state.put("instance_orders", row)

    # ------------------------------------------------------------------ the real instances
    def _real_job(self, inst: Instance, day: LiveDay, mi: int) -> dict | None:
        book = self.book
        assert book is not None
        roots = [r for r in inst.needs.roots if day.snapshot(r, mi) is not None]
        if not roots:
            return None
        rows = []
        unrealized = 0.0
        for pos in book.instance_positions(inst.key):
            chain = day.chains.get(pos.root)
            snap = day.snapshot(pos.root, mi)
            idx = chain.index_of(np.array([leg.key for leg in pos.legs], dtype=np.int64)) if chain is not None else np.full(len(pos.legs), -1)
            legs = [L.LegFill(int(i), leg.key, leg.side, leg.ratio, 0, leg.strike, leg.is_call) for leg, i in zip(pos.legs, idx)]
            mark = natural = math.nan
            if snap is not None and (idx >= 0).all():
                mark = L.mid_value(snap, legs)
                natural = L.natural_value(snap, legs, "close")[0]
            if math.isfinite(mark):
                unrealized += (mark - pos.entry) * V.MULTIPLIER * pos.qty
            leg_rows = [{"id": int(i), "dte": (dt.date.fromisoformat(leg.expiry) - day.day).days, "strike": leg.strike,
                         "is_call": leg.is_call, "side": "long" if leg.side > 0 else "short", "ratio": leg.ratio}
                        for leg, i in zip(pos.legs, idx)]
            opened = dt.date.fromisoformat(pos.opened_day)
            held_days = max(0, len([d for d in trading_days_around(day.day, before=40, after=0) if opened < d <= day.day]))
            held = held_days * 390 + (mi - (pos.opened_minute if held_days == 0 else 0))
            rows.append(position_row(pid=pos.pid, type_=pos.type, root=pos.root, qty=pos.qty, legs=leg_rows, entry=pos.entry,
                                     max_loss=pos.max_loss, mark=mark, natural=natural, held_minutes=held, held_days=held_days,
                                     tag=pos.tag))
        orders = [order_row(oid=o.oid, kind=o.action, type_=o.type, root=o.root, qty=o.qty, filled=o.filled_qty,
                            limit=o.limit_value, age_minutes=(mi - o.placed_minute) if o.day == day.day.isoformat() else 390,
                            position=o.pid, tag=o.why[:80]) for o in book.instance_orders(inst.key)]
        capital = float(self.settings["shadow_capital"])
        at_risk = sum(p.max_loss for p in book.instance_positions(inst.key))
        return {"key": inst.key, "minute": day.open_min + mi, "open_minute": day.open_min, "close_minute": day.close_min,
                "weekday": day.weekday, "roots": roots, "positions": rows, "orders": orders, "cash": capital - at_risk,
                "equity": capital + unrealized, "budget": capital, "buying_power": max(0.0, capital - at_risk - book.reserved()),
                "rules": {r: day.rules_rows[r] for r in roots}, "events": day.events, "events_next": day.events_next,
                "closed": book.closed_since.pop(inst.key, []), "rejects": book.rejects_since.pop(inst.key, [])}

    def _killed(self) -> bool:
        if self.kill_switch is None:
            return False
        try:
            return bool(self.kill_switch())
        except Exception:  # noqa: BLE001 - unreadable counts as engaged
            return True

    def real_block(self, *, opening: bool = True) -> str | None:
        """Why no new real ENTRY may go now (None: they may). Exits need only the kill switch off."""
        if not self._real_on():
            return "real money is off (config.json real_money)"
        grant = self._grant()
        if not grant or not grant.get("active"):
            return "the grant options-swarm-20260928 is not active on the money rules in force"
        if self._killed():
            return "the gateway's kill switch is engaged"
        blocked = self.stops.blocked()
        if blocked:
            return blocked
        if self.book is not None and self.book.frozen:
            return f"reconciliation: {self.book.frozen}"
        if self.state.rows("SELECT pid FROM positions WHERE status='unpriced_close' LIMIT 1"):
            return "reconciliation: expired positions are flat but their venue fill values are still unread"
        latch = self.state.get("assignment_latch")
        if latch:
            return f"{latch.get('why')}: the owner clears it (python3 -m league.live --root <state> --clear-assignment)"
        if self.settings.get("require_paper_proof", True) and (self.proof is None or not self.proof.passed()):
            return "the paper account has not yet proved the multi-leg route this run"
        if not self.house_open:
            return "the House is paused"
        if self.account_row is None:
            return "the account could not be read this minute"
        return None

    def _real_intents(self, inst: Instance, day: LiveDay, mi: int, intents: Iterable[Mapping[str, Any]], out: dict) -> None:
        book = self.book
        assert book is not None
        for intent in intents:
            try:
                why = self._real_intent(inst, day, mi, dict(intent), out)
            except L.Refused as exc:
                why = str(exc)
            except Exception as exc:  # noqa: BLE001 - one malformed intent is refused alone, never the minute's end
                why = f"a malformed intent: {type(exc).__name__}: {str(exc)[:160]}"
            if why:
                book._reject(inst.key, why)
                self.record("live.refusal", {"instance": inst.key, "family": inst.family, "why": why[:300],
                                             "_intent": {k: v for k, v in intent.items() if k != "note"}}, agent=inst.family)

    def _real_intent(self, inst: Instance, day: LiveDay, mi: int, intent: dict, out: dict) -> str | None:
        book = self.book
        assert book is not None
        today = day.day.isoformat()
        minute = day.open_min + mi + 1
        if "cancel" in intent:
            order = book.orders.get(intent["cancel"]) if isinstance(intent["cancel"], int) else None
            if order is None or order.instance != inst.key or order.forced:
                return "cancel: no such working order"
            # Withdrawing an open needs no exit room (and the gateway does not count a cancel): only a close's cancel
            # meets the House's forced-exit reserve.
            refusal = book.count_refusal(len(order.legs), day=today) if order.action != "open" else None
            if refusal:
                return refusal
            book.cancel(order, "the program cancelled it")
            return None
        if "close" in intent:
            pos = book.positions.get(intent["close"]) if isinstance(intent["close"], int) else None
            if pos is None or pos.instance != inst.key or pos.qty <= 0:
                return "close: no such open position"
            if book.closing_order(pos.pid) is not None:
                return "close: this position already has a working close (cancel it first)"
            if pos.info.get("broken"):
                return f"close: this structure is broken ({pos.info['broken']}): the House closes its legs"
            late = self._program_close_refusal(pos, day, mi)
            if late:
                return late
            return self._send_close(pos, day, mi, forced=False, why=str(intent.get("note") or intent.get("tag") or "program")[:200],
                                    out=out, intent=intent)
        if "open" not in intent:
            return "an intent has one of open, close or cancel"
        if inst.mode != "live":
            return f"this instance closes only ({inst.mode}): its family left the real band"
        if inst.error or inst.fatal:
            return f"this program is unavailable: {inst.error}"
        blocked = self.real_block(opening=True)
        if blocked:
            return blocked
        root = str(intent.get("root") or (inst.needs.roots[0] if len(inst.needs.roots) == 1 else "")).upper()
        if root not in inst.needs.roots:
            return f"open: root {root or '?'} is not one this program trades"
        snap = day.snapshot(root, mi)
        chain = day.chains.get(root)
        if snap is None or chain is None:
            return f"open: no {root} chain now"
        rules = day.rules[root]
        unit_intent = {k: v for k, v in intent.items() if k not in ("qty", "max_loss")}
        unit_intent["qty"] = 1
        order = L.resolve_open(unit_intent, snap, rules, buying_power=float("inf"))
        equity_now = M.D(self.account_row["equity"])
        sizing = self.sizing_equity()
        if sizing is None:
            return "no sizing equity (the grant or the account)"
        why = self.table.type_allowed(order.type, equity_now)
        if why:
            return why
        if any(leg.dte == 0 for leg in order.legs) and minute >= rules.open_cutoff:
            return f"expiry cutoff: no new opening order on an expiring contract from {rules.open_cutoff // 60}:{rules.open_cutoff % 60:02d} ET"
        legs = real_legs(order, chain)
        top = _max_value(order.type, legs)
        if order.type in L.DEBIT and top is not None and order.limit >= top - 1e-9:
            return f"a debit of {order.limit:.2f} on a {order.type} worth at most {top:.2f} can never pay"
        unit = M.D(round(order.max_loss_share * V.MULTIPLIER + 2 * order.fees, 2))
        family_rows = self.families.forward_rows(inst.family) if not inst.tuition else []
        fwd = M.forward_stats(family_rows, self.table.sized_confidence, version=inst.version) if not inst.tuition else None
        if fwd is not None and (fwd.negative or (inst.band == "sized" and (not M.sized_ok(self.table, fwd) or fwd.real_bad))):
            self._families_at = float("-inf")
            return "its current forward evidence no longer qualifies for this real band"
        week_start = (day.day - dt.timedelta(days=day.day.weekday())).isoformat()
        plan = M.plan_open(self.table, band=inst.band, tuition=inst.tuition, equity=sizing, unit=unit, fwd=fwd,
                           exposure=book.exposure(inst.family, day=today, week_start=week_start))
        if plan.qty < 1:
            return plan.reason
        qty = plan.qty
        prices = [float(snap.ask[leg.idx] if leg.side > 0 else snap.bid[leg.idx]) for leg in order.legs]
        fees = L.order_fees(root, order.legs, prices, qty, "open")
        max_loss = order.max_loss_share * V.MULTIPLIER * qty
        reserve = (max_loss + 2 * fees) * (1 + float(self.table.bp_buffer))
        free = float(M.D(self.account_row.get("options_buying_power") or 0)) - book.reserved()
        if reserve > free + 1e-9:
            return f"buying power: it reserves {reserve:.2f} (maximum loss, fees and {self.table.bp_buffer:.0%}); {max(0.0, free):.2f} is free"
        waiting = sorted({leg.symbol for leg in legs} & self._pending_symbols())
        if waiting:
            return f"an exit is waiting for {', '.join(waiting)}: no new open on it"
        refusal = book.path_refusal(legs, opening=True, day=today)
        if refusal:
            return refusal
        if not self._instance_budget(inst.key, day):
            return f"order budget: {int(self.settings['instance_orders_day'])} orders a day (the Gym's)"
        tif = order.tif
        identity = dict(self._entry_identity(inst), forward_rows=family_rows)
        with self.families.admit_open(identity, real=True) as allowed:
            if allowed:
                sent = book.new_order(instance=inst.key, family=inst.family, action="open", type_=order.type, root=root, legs=legs,
                                      qty=qty, limit_value=order.limit, tif=tif, day=today, minute=mi, reserve=reserve,
                                      max_loss=max_loss, fees_est=fees, tuition=inst.tuition,
                                      why=str(intent.get("note") or intent.get("tag") or "")[:200])
        if not allowed:
            inst.mode = "exit_only"
            self._persist_instance(inst)
            self._cancel_inactive_opens()
            return "its family or version is no longer eligible to open"
        book.send(sent)
        if sent.dispatched:
            self._instance_spent(inst.key, day)
        out.setdefault("orders", []).append({"oid": sent.oid, "family": inst.family, "action": "open", "qty": qty,
                                             "status": sent.status, "sizing": plan.reason})
        return None if sent.status in ("working", "filled", "unknown") else f"{sent.status}: {sent.answer.get('error')}"

    # ------------------------------------------------------------------ forward records
    def _export_one(self, acc: ShadowAccount) -> None:
        trades = acc.new_trades()
        if not trades:
            return
        version = _version_of(acc.instance)
        rows = [{"id": f"{acc.instance}:{t['id']}", "day": t["day"], "pnl": t["pnl"], "max_loss": t["max_loss"], "version": version}
                for t in trades]
        try:
            self.families.add_forward(acc.family, "shadow", rows)
        except Exception as exc:  # noqa: BLE001 - kept to be sent again
            acc.exported -= len(trades)
            self.alert("warning", f"live: {acc.family}'s shadow trades could not reach the forward record ({type(exc).__name__})")

    def _export_shadow(self) -> None:
        for acc in self.shadow.accounts.values():
            self._export_one(acc)

    def _export_real(self) -> None:
        if self.book is None:
            return
        # Position ids follow opens, not closes. Backfill every unacknowledged row, including rows the former
        # max-pid cursor missed; the swarm deduplicates a retried export by its stable trade id.
        rows = self.book.closed_trades(unexported=True)
        for row in rows:
            if not row["tuition"]:
                try:
                    self.families.add_forward(row["family"], "real", [{**row, "version": _version_of(row.get("instance") or "")}])
                except Exception as exc:  # noqa: BLE001
                    self.alert("warning", f"live: a real trade could not reach the forward record ({type(exc).__name__})")
                    return
            self.state.execute("INSERT OR IGNORE INTO forward_exports(pid, exported_at) VALUES(?,?)",
                               (int(row["pid"]), self.clock()))

    # ------------------------------------------------------------------ the close and the quiet hours
    def _end_of_day(self, day: LiveDay, out: dict) -> None:
        if self.state.get("ended_day") == day.day.isoformat():
            return
        for acc in self.shadow.accounts.values():
            if acc.began_day == day.ordinal and acc.ended_day != day.ordinal:
                acc.end_day(day, last=False)
                acc.ended_day = day.ordinal
        self._export_shadow()
        if self.book is not None:
            today = day.day.isoformat()
            for pos in list(self.book.positions.values()):
                if pos.qty <= 0 or pos.expiry != today:
                    continue
                if pos.info.get("broken"):
                    pos.status = "awaiting_expiry"
                    self.book._save_position(pos)
                    continue
                chain = day.chains.get(pos.root)
                level = settlement_level(chain.underlying) if chain is not None else float("nan")
                if not math.isfinite(level):
                    pos.status = "awaiting_expiry"
                    self.book._save_position(pos)
                    continue
                value = sum(leg.side * leg.ratio * _intrinsic(leg, level) for leg in pos.legs if leg.expiry == today)
                itm = [leg for leg in pos.legs if _intrinsic(leg, level) >= 0.01]
                if V.is_index(pos.root) and all(leg.expiry == today for leg in pos.legs):
                    self.book.settle(pos, value, "settled")
                else:
                    pos.status = "awaiting_expiry"
                    pos.info["expiry_intrinsic_estimate"] = value
                    self.book._save_position(pos)
                    if itm:
                        self.alert("warning", f"live: {pos.family}'s {pos.type} expired with a leg in the money: awaiting venue events or liquidation fills")
            self._export_real()
        self.state.put("ended_day", day.day.isoformat())
        self.shadow.save()
        out["ended"] = day.day.isoformat()

    def _quiet(self, now: float, out: dict) -> None:
        """Outside the session: the families (so the site's bands stay current) and, every few minutes, the account's
        orders read (a day order that ended), option events and physical expired-leg reconciliation."""
        self.sync_families(now)
        if self.book is None or now - float(self.state.get("quiet_at", 0) or 0) < 900:
            return
        self.state.put("quiet_at", now)
        today = ny(now).date()
        self._missed_close(today)
        try:
            rows = self.real.orders(status="all", after=dt.datetime.fromtimestamp(now - 3 * 86400, dt.timezone.utc).isoformat())
            foreign = self.book.ingest(rows)
            self.book.look_up(today=today.isoformat(), seen=[str(r.get("client_order_id") or "") for r in rows])
            positions = self.real.positions()
            self.account_row = self.real.account()
        except Exception as exc:  # noqa: BLE001
            out["venue_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        self._activities(now)
        if "venue_error" not in out:
            if self._activities_changed:
                positions = self._positions_again(out)
            if positions is not None:
                self._reconcile_expiry(rows, positions, today, out)
                self.book.reconcile(positions, foreign, day=today, after_close=True,
                                    shares=self.state.get("shares", {}) or {}, include_expired=True)
                self._export_real()

    def _reconcile_expiry(self, orders: list[dict], positions: list[dict], today: dt.date, out: dict) -> None:
        book = self.book
        assert book is not None and self.real is not None
        if not any(p.status == "awaiting_expiry" for p in book.positions.values()) and not self.state.rows(
                "SELECT pid FROM positions WHERE status='unpriced_close' LIMIT 1"):
            return
        known = {str(r["venue_id"]) for r in self.state.rows("SELECT venue_id FROM orders WHERE venue_id IS NOT NULL")}
        try:
            activities = self.real.activities(["FILL"], after=self.start_at or None)
        except Exception as exc:  # noqa: BLE001 - order fills may still resolve it; unpriced rows remain visible
            activities = []
            out["expiry_fill_error"] = type(exc).__name__
        fills = []
        activity_orders = {str(r.get("order_id")) for r in activities if r.get("order_id")}
        for r in activities:
            if str(r.get("order_id")) in known or not r.get("id"):
                continue
            key = f"order:{r['order_id']}:{r.get('symbol')}" if r.get("order_id") else f"activity:{r['id']}"
            fills.append({"id": key, "symbol": str(r.get("symbol") or ""),
                          "side": r.get("side"), "qty": r.get("qty"), "price": r.get("price"),
                          "at": parse_time(r.get("transaction_time"))})
        for order in orders:
            if (str(order.get("id")) in known or str(order.get("id")) in activity_orders
                    or str(order.get("client_order_id") or "").startswith("lv-")):
                continue
            for leg in order.get("legs") or [order]:
                fills.append({"id": f"order:{order.get('id')}:{leg.get('symbol')}", "symbol": str(leg.get("symbol") or ""),
                              "side": leg.get("side"), "qty": leg.get("filled_qty"), "price": leg.get("filled_avg_price"),
                              "at": parse_time(leg.get("filled_at") or order.get("filled_at"))})
        combined = {}
        for f in fills:
            try:
                qty, price = M.D(f["qty"]), M.D(f["price"])
                if f["at"] is not None and qty > 0 and qty == int(qty) and price >= 0 and occ_parts(f["symbol"]):
                    previous = combined.get(f["id"])
                    if previous:
                        total = previous["qty"] + int(qty)
                        previous["price"] = (previous["qty"] * previous["price"] + int(qty) * float(price)) / total
                        previous["qty"] = total
                        previous["at"] = min(previous["at"], f["at"])
                    else:
                        combined[f["id"]] = {**f, "qty": int(qty), "price": float(price)}
            except (TypeError, ValueError, ArithmeticError):
                continue
        held = {str(r.get("symbol")): int(M.D(r.get("qty") or 0)) for r in positions if occ_parts(str(r.get("symbol") or ""))}
        for message in book.recover_expired(held, sorted(combined.values(), key=lambda f: (f["at"], f["id"])), day=today.isoformat()):
            self.alert("warning", f"live: {message}")
            self.record("live.expiry_reconciliation", {"what": message})
        out["unpriced_closes"] = len(self.state.rows("SELECT pid FROM positions WHERE status='unpriced_close'"))

    # ------------------------------------------------------------------ what the site shows
    def site_inputs(self) -> dict:
        """Open structures (real and shadow) for the site's schema 2: what each is, whose, what it can lose, its P&L at
        the last mark. Never a price, a strike, a quote or a leg's code."""
        rows = []
        if self.book is not None:
            for pos in list(self.book.positions.values()):
                if pos.qty <= 0:
                    continue
                rows.append({"id": f"real:{pos.pid}", "agent": pos.family, "underlying": pos.root, "structure": pos.type,
                             "legs": len(pos.legs), "expiry": pos.expiry, "quantity": pos.qty, "real": True,
                             "opened_at": dt.datetime.fromtimestamp(pos.opened_at, dt.timezone.utc).isoformat(),
                             "max_loss_usd": round(pos.max_loss, 2), "pnl_usd": _pnl(pos, self.day)})
        for acc in list(self.shadow.accounts.values()):
            for pos in list(acc.positions.values()):
                mark = pos.last_mark
                rows.append({"id": f"shadow:{acc.instance}:{pos.pid}", "agent": acc.family, "underlying": pos.root,
                             "structure": pos.type, "legs": len(pos.legs),
                             "expiry": from_ordinal(int(pos.expirations.min())).isoformat(), "quantity": pos.qty, "real": False,
                             "opened_at": None, "max_loss_usd": round(pos.max_loss_share * V.MULTIPLIER * pos.qty, 2),
                             "pnl_usd": round((mark - pos.entry) * V.MULTIPLIER * pos.qty, 2) if math.isfinite(mark) else None})
        return {"structures": rows}

    def health(self) -> dict:
        with self._lock:
            summary = dict(self.summary)
        return {"summary": summary, "blocked": self.real_block(), "stops": self.stops.as_state(),
                "frozen": self.book.frozen if self.book is not None else None,
                "paper_proof": self.proof.status() if self.proof is not None else None,
                "instances": {k: {"family": i.family, "kind": i.kind, "band": i.band, "mode": i.mode, "error": i.error or None,
                                  "tuition": i.tuition} for k, i in self.instances.items()}}


def _version_of(instance: str) -> int | None:
    """The program version an instance key names (`<family>@<version>:<kind>`)."""
    try:
        return int(str(instance).rsplit("@", 1)[1].split(":", 1)[0])
    except (IndexError, ValueError):
        return None


def json_or(text: Any, default: Any) -> Any:
    import json

    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


def _intrinsic(leg: RLeg, level: float) -> float:
    return max(0.0, level - leg.strike) if leg.is_call else max(0.0, leg.strike - level)


def _near_money(leg: RLeg, spot: float, share: float) -> bool:
    """In the money, or within `share` of spot on the out-of-the-money side."""
    if not math.isfinite(spot) or spot <= 0:
        return True
    if leg.is_call:
        return spot >= leg.strike * (1.0 - share)
    return spot <= leg.strike * (1.0 + share)


def _max_value(type_: str, legs: Iterable[RLeg]) -> float | None:
    legs = list(legs)
    strikes = sorted(leg.strike for leg in legs)
    if type_ == "debit_vertical":
        return strikes[-1] - strikes[0]
    if type_ == "long_butterfly":
        return strikes[1] - strikes[0]
    return None


def _pnl(pos: RPosition, day: LiveDay | None) -> float | None:
    if day is None or pos.root not in day.chains:
        return None
    chain = day.chains[pos.root]
    idx = chain.index_of(np.array([leg.key for leg in pos.legs], dtype=np.int64))
    if (idx < 0).any():
        return None
    rows = [m for m in range(chain.m - 1, -1, -1) if np.isfinite(chain.bid[m, idx]).all() and np.isfinite(chain.ask[m, idx]).all()]
    if not rows:
        return None
    m = rows[0]
    mark = sum(leg.side * leg.ratio * 0.5 * (chain.bid[m, i] + chain.ask[m, i]) for leg, i in zip(pos.legs, idx))
    return round((float(mark) - pos.entry) * V.MULTIPLIER * pos.qty, 2)


__all__ = ["OptionsLive", "Instance", "DEFAULTS"]
