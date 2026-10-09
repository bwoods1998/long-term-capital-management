"""THE PER-CLOSE FILL REPLAY (Oct 10, 2026; the readiness audit of Oct 9, its blocker B1 (c); the Done rule's item 4 as
amended by A1.1, pinned Oct 9): every real close of an agent program gets its own replay twin, so "live fills consistent
with their replay" is measured close by close instead of through a nightly replay that may not trade the day the real
program did.

WHY. Until this release the only replay a real close could be matched to was its program's NIGHTLY forward replay
(`gate.Gate.forward_ready`), matched by (version, entry day). That replay is the program's own run over the forward
days, and it drifts out of phase with the real account for good: a program that holds one position at a time (direction
v17 holds to expiry, `if len(ctx.positions) > 0: return []`) cannot enter on a day its replay is still holding, and any
live open the money table refused, or that did not fill, desyncs the two again. Pid 41 (opened Oct 9) has no twin that
way: v17's replay entered Oct 8 and holds to Oct 12. Rule 4 then passed with no replay evidence at all (B1).

WHAT A TWIN IS. The real trade's OWN orders, replayed on the gate image by the Gym's own engine and fill model, with no
change to league/gym or league/live (the execution fingerprint and the gate contract do not move: rule F0):
- a fixed Gym program, `PUPPET` (one source; its sha is in every record), whose PARAMS carry one real position: its
  contracts (strike, right, side, ratio and calendar days to expiry on the entry day), the open order's decision minute,
  limit price, size and time in force, and each later close order the venue received (its day, as the first leg's days
  to expiry then, its minute, limit and time in force; a House-forced one at the natural). It finds each contract in the
  image's chain at the entry minute by exact strike, right and expiry (`id`), sends the same open with the same limit,
  and replays the close orders on their own days and minutes. The House's expiry close on the expiry day is the Gym's
  own (`engine.Account._venue`, the live path's rule), so the puppet never sends one; neither does it send a close the
  gateway or the House refused (it never reached the venue);
- one Gym job a close: window "forward" cut to the trade's own sessions (its entry day to its exit day), on a gate box
  (`gate` reason `GATE_REASON`: the forward days live only on the gate image), at the priority under the nightly
  forward's. The Gym answers what it answers for every forward run (`results.view`): the run's days, its one trade's
  day, P&L and maximum loss, and its fill counts;
- the twin's verdict (`judge`): "priced" (one trade, entered on the real trade's entry day, over exactly the trade's
  NYSE sessions), "no_fill" (the open was sent and the fill model did not fill it: live filled what the model would not;
  never a gap, counted apart), "no_contract" (the image has no two-sided quote of a contract at the decision minute, or
  lacks the entry day), "unpriceable" (the trade cannot be replayed: a leg past the Gym's 60 days, a broken structure
  closed leg by leg, an order the book does not hold, a day missing inside the trade's sessions on the image; the reason
  is kept), or "failed" (the Gym job failed, or the image's files stop before the trade's last session: no verdict on
  the trade; asked again at most `attempts` times a ready day, and again on the next ready day's image). Only "failed"
  is ever asked again: a twin is final once judged (A1.4's final readings).
- the gap of a priced twin is the real trade's P&L per dollar of its maximum loss (the book's cash, as D5 reads it)
  minus the twin's, each over its own maximum loss; its exit is classified both ways (the Gym's from its fill counts,
  the book's from its close orders) and `exit_agrees` says whether they left the same way.

WHAT READS IT. The swarm store's kv `close_twins` ({pid: record}); the direction lane's operator report
(`league/ops/dlane_report.py` `replay_gap`) matches a close with a priced twin to it (a close without any twin record
falls back to the nightly (version, day) match exactly as before). Nothing here moves a band, a forward record, a trial
count or money: a twin is not a research run (no `runs` row, no trial), and its result reaches no agent.

THE SWITCH. `forward.twins` in swarm.json: {"max_jobs", "attempts"} (the defaults below); null or false switches it off
(no job, no read). It runs as its own round after the nightly forward (`league/swarm/loop.py` `Swarm.step`), at most
once per `forward.every_seconds` per ready day, and only while the guard allows the Gym.

WHY league/ops (Oct 10, 2026). Only the swarm's process holds the Gym pool, so the swarm's loop runs this round; the
code lives here, under the updater's wall (`ci.FORBIDDEN` names the whole of league/ops/), because it is the Done
meter's input: like the report that reads it, only the owner's deploy may change how a twin is made or judged, never an
automatic release (the engineer's harness change). It opens the forward days only through the gate's own door (a gate
box, the gate's reason), as the nightly forward does.

Standard library only (the pool's rule); the NYSE calendar from `ltcm.data` (`gate.sessions_between`'s source).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from ..swarm.pool import GymJob, PoolError

NY = ZoneInfo("America/New_York")
TWINS_KEY = "close_twins"
ATTEMPT_KEY = "close_twins_attempt"
GATE_REASON = "per-close fill replay"
PURPOSE = "twin"
#: Under the nightly forward replay's 5.0 (and the holdout look's): a twin waits behind every evidence job on the gate box.
PRIORITY = 4.0
#: A twin job's `family`: never a family's id (ids are `[a-z0-9-]`, `store._SLUG`; the dot keeps it a plain file stem for
#: the Gym's program archive), so the pool's "the family retired before dispatch" check (which reads the family) never
#: drops the twin of a retired family's close.
FAMILY_PREFIX = "twin."
LIVE_DB = "live.sqlite"
#: The verdicts that are final (never asked again); "failed" is asked again up to `attempts` times.
FINAL = ("priced", "no_fill", "no_contract", "unpriceable")
DEFAULTS = {"max_jobs": 12, "attempts": 3}
#: The Gym's session minutes: its open (09:30 ET) and the decision window a program with NEEDS start 571 and end 958 gets
#: (`engine.Account.decision_minutes`: the first minute after the open to three before the close).
OPEN_MIN = 570
FIRST_DECISION, LAST_DECISION = 571, 958
#: A PARAMS list holds at most 64 scalars (`gym.runtime._json_scalar`): close orders past this many are not replayed.
MAX_CLOSES = 60
#: The Gym's chain window: NEEDS "dte" is at most 60 calendar days.
MAX_DTE = 60
#: Book statuses of an order that never reached the venue: never replayed.
NOT_SENT = ("refused", "rejected", "pending")

#: The puppet: one real position replayed. Fixed source, its PARAMS are the trade (`plan`). Gym rules hold (math and
#: numpy, no date literal, PARAMS declared once): NEEDS is computed from PARAMS at load, as the runtime binds PARAMS first.
PUPPET = '''"""A per-close fill replay twin (league/ops/twins.py): one real position's own orders, replayed."""
import math
import numpy as np

PARAMS = {"root": "SPY", "type": "long_call", "qty": 1,
          "leg_strike": [0.0], "leg_call": [1], "leg_side": [1], "leg_ratio": [1], "leg_dte": [0],
          "open_minute": 571, "open_limit": 0.0, "open_natural": 0, "open_tif": -1,
          "close_expiry": [], "close_minute": [], "close_limit": [], "close_natural": [], "close_tif": [],
          "dte_lo": 0, "dte_hi": 60}
NEEDS = {"roots": [PARAMS["root"]], "dte": [PARAMS["dte_lo"], PARAMS["dte_hi"]], "band": 0.3, "cadence": 1,
         "history": 0, "start": 571, "end": 958}
STATE = {"session": 0, "last": -1, "tried": 0, "sent": []}


def contract(chain, strike, call, dte):
    hit = np.flatnonzero((chain.dte == dte) & (np.abs(chain.strike - strike) < 0.0005) & (chain.is_call == (call == 1)))
    if hit.size != 1:
        return -1
    return int(chain.id[hit[0]])


def opening(ctx, p):
    chain = ctx.chains.get(p["root"])
    if chain is None:
        return []
    legs = []
    for i in range(len(p["leg_strike"])):
        found = contract(chain, p["leg_strike"][i], p["leg_call"][i], p["leg_dte"][i])
        if found < 0:
            return []
        legs.append({"side": "long" if p["leg_side"][i] > 0 else "short", "ratio": int(p["leg_ratio"][i]), "id": found})
    intent = {"open": p["type"], "root": p["root"], "legs": legs, "qty": int(p["qty"]), "tag": "twin"}
    if p["open_natural"] == 1:
        intent["limit"] = "natural"
    else:
        intent["limit"] = {"price": float(p["open_limit"])}
    if p["open_tif"] >= 0:
        intent["tif"] = int(p["open_tif"])
    return [intent]


def closing(ctx, p):
    out = []
    for pos in ctx.positions:
        to_expiry = min([leg["dte"] for leg in pos["legs"]])
        for k in range(len(p["close_minute"])):
            if k in STATE["sent"] or p["close_expiry"][k] != to_expiry or p["close_minute"][k] != ctx.minute:
                continue
            STATE["sent"].append(k)
            for order in ctx.orders:
                if order["kind"] == "close" and order["position"] == pos["id"]:
                    out.append({"cancel": order["id"]})
            intent = {"close": pos["id"], "tag": "twin"}
            if p["close_natural"][k] == 1:
                intent["limit"] = "natural"
            else:
                intent["limit"] = {"price": float(p["close_limit"][k])}
            if p["close_tif"][k] >= 0:
                intent["tif"] = int(p["close_tif"][k])
            out.append(intent)
    return out


def decide(ctx):
    p = ctx.params
    if ctx.minute <= STATE["last"]:
        STATE["session"] = STATE["session"] + 1
    STATE["last"] = ctx.minute
    if STATE["session"] == 0 and STATE["tried"] == 0 and ctx.minute == p["open_minute"]:
        STATE["tried"] = 1
        return opening(ctx, p)
    return closing(ctx, p)
'''
PUPPET_SHA = hashlib.sha256(PUPPET.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------------- reading the book
def _loads(text: Any, default: Any) -> Any:
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text) if text not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def ny_day(epoch: Any) -> str | None:
    """The New York calendar day of an epoch (None when it is not a number)."""
    value = _num(epoch)
    if value is None:
        return None
    return dt.datetime.fromtimestamp(value, NY).date().isoformat()


def agent(position: Mapping[str, Any]) -> bool:
    """A swarm program's position on any real route (`:r`, `:t`, `:i`, ...): never a House route (`house:*`, the
    calibration round trips `:c`, the House live test `:h`), as the Done rule counts them (`economics.route_of`)."""
    family, instance = str(position.get("family") or ""), str(position.get("instance") or "")
    return bool(family) and not family.startswith("house:") and not instance.endswith((":c", ":h"))


def read_live(path: str | Path, *, since: float | None = None) -> dict[str, Any]:
    """The live book's closed agent positions (closed at or after `since`, epoch) and every order of each, read-only
    (`mode=ro`): {"positions": [row...], "orders": {pid: [row... by oid]}}. Raises `sqlite3.Error` when the book cannot be
    read (the round then says so and judges nothing)."""
    db = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True, timeout=5.0)
    db.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in db.execute("SELECT * FROM positions WHERE status='closed' ORDER BY pid")]
        positions = [r for r in rows if agent(r) and (since is None or (_num(r.get("closed_at")) or 0.0) >= since)]
        pids = [int(r["pid"]) for r in positions]
        orders: dict[int, list[dict[str, Any]]] = {pid: [] for pid in pids}
        for i in range(0, len(pids), 500):
            chunk = pids[i:i + 500]
            marks = ",".join("?" * len(chunk))
            for r in db.execute(f"SELECT * FROM orders WHERE pid IN ({marks}) ORDER BY oid", chunk):
                orders.setdefault(int(r["pid"]), []).append(dict(r))
        # An open order is tied to its position by the position's `info.order` too (a row written before its `pid` was).
        wanted = {int(o): int(r["pid"]) for r in positions for o in [(_loads(r.get("info"), {}) or {}).get("order")]
                  if isinstance(o, int) or (isinstance(o, str) and o.isdigit())}
        missing = [oid for oid, pid in wanted.items() if not any(int(x["oid"]) == oid for x in orders.get(pid, []))]
        for i in range(0, len(missing), 500):
            chunk = missing[i:i + 500]
            marks = ",".join("?" * len(chunk))
            for r in db.execute(f"SELECT * FROM orders WHERE oid IN ({marks}) ORDER BY oid", chunk):
                orders.setdefault(wanted[int(r["oid"])], []).append(dict(r))
        for rows_ in orders.values():
            rows_.sort(key=lambda o: int(o["oid"]))
        return {"positions": positions, "orders": orders}
    finally:
        db.close()


# ------------------------------------------------------------------------------------------------- the plan
def sessions(first: str, last: str) -> list[str] | None:
    """The NYSE sessions from `first` to `last` (ISO days, both included), by the calendar the House trades on
    (`ltcm.data.us_equity_session`); None when the calendar cannot say."""
    try:
        from ltcm.data import us_equity_session

        day, end = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
        out = []
        while day <= end:
            if us_equity_session(day) is not None:
                out.append(day.isoformat())
            day += dt.timedelta(days=1)
        return out
    except Exception:  # noqa: BLE001 - no calendar, no plan
        return None


def _minute(mi: Any) -> int | None:
    """A book minute (minutes since the open) as the Gym's decision minute (minutes since midnight ET, clamped into the
    Gym's decision window: a decision at the open's own minute is replayed at 09:31, the Gym's first)."""
    value = _num(mi)
    if value is None:
        return None
    return max(FIRST_DECISION, min(LAST_DECISION, OPEN_MIN + int(value)))


def _tif(raw: Any) -> int:
    value = _num(raw)
    return -1 if value is None or value < 0 else int(min(400, value))


def expiry_close(order: Mapping[str, Any], first_expiry: str) -> bool:
    """The House's expiry close (`league/live/step.py` `_expiry_close`: a forced close on the first leg's expiry day, its
    words "an expiring long call ..." or "expiring equity options ..."; with no words, one placed from 12:00 ET, the
    earliest the window opens on a half day). The Gym's venue makes its own (`engine.Account._venue`), so the puppet
    never replays one. Any other forced close (the House closing an orphan: "its program is gone") is replayed at the
    natural."""
    if not order.get("forced") or str(order.get("day") or "") != first_expiry:
        return False
    why = str(order.get("why") or "")
    if why:
        return "expiring" in why
    minute = _num(order.get("placed_minute"))
    return minute is not None and OPEN_MIN + minute >= 720


def live_exit(position: Mapping[str, Any], closes: Sequence[Mapping[str, Any]], first_expiry: str) -> str:
    """How the real trade left: "house_close" (the House's expiry close filled), "house_forced" (another House-forced
    close filled), "program_close", "expired", else the book's reason."""
    filled = [o for o in closes if int(o.get("filled_qty") or 0) > 0]
    if any(expiry_close(o, first_expiry) for o in filled):
        return "house_close"
    if any(o.get("forced") for o in filled):
        return "house_forced"
    if filled:
        return "program_close"
    reason = str(position.get("reason") or "")
    return "expired" if "expired" in reason else (reason[:80] or "unknown")


def plan(position: Mapping[str, Any], orders: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One real close as a twin job's inputs: {"pid", "ok", "why", "root", "type", "start", "end", "sessions", "params",
    "live"}. `ok` False (with `why`) when the trade cannot be replayed by the puppet."""
    pid = int(position["pid"])
    legs = _loads(position.get("legs"), [])
    info = _loads(position.get("info"), {}) or {}
    opened_day = str(position.get("opened_day") or "")
    out: dict[str, Any] = {"pid": pid, "ok": False, "why": None, "family": str(position.get("family") or ""),
                           "instance": str(position.get("instance") or ""), "root": str(position.get("root") or "").upper(),
                           "type": str(position.get("type") or ""), "start": opened_day or None, "end": None,
                           "first_expiry": None, "sessions": None, "params": None, "live": None}
    opened_qty = int(position.get("opened_qty") or 0)
    loss = (_num(position.get("max_loss_share")) or 0.0) * 100.0 * opened_qty
    cash = _num(position.get("cash"))
    live = {"cash": None if cash is None else round(cash, 2), "max_loss": round(loss, 2),
            "r": round(cash / loss, 5) if cash is not None and loss > 0 else None, "exit": None,
            "closed_at": _num(position.get("closed_at")), "reason": str(position.get("reason") or "")[:120]}
    out["live"] = live
    if not legs or not isinstance(legs, list) or not all(isinstance(x, Mapping) for x in legs):
        out["why"] = "the position's legs cannot be read"
        return out
    try:
        expiries = [str(x["expiry"]) for x in legs]
        days = [(dt.date.fromisoformat(e) - dt.date.fromisoformat(opened_day)).days for e in expiries]
        strikes = [float(x["strike"]) for x in legs]
        calls = [1 if x.get("is_call") else 0 for x in legs]
        sides = [1 if int(x.get("side") or 0) > 0 else -1 for x in legs]
        ratios = [int(x.get("ratio") or 1) for x in legs]
    except (KeyError, TypeError, ValueError):
        out["why"] = "a leg's expiry, strike or side cannot be read"
        return out
    first_expiry = min(expiries)
    out["first_expiry"] = first_expiry
    oid = info.get("order")
    opens = [o for o in orders if str(o.get("action")) == "open"]
    entry = next((o for o in opens if oid is not None and str(o.get("oid")) == str(oid)), None) or \
        next((o for o in opens if int(o.get("filled_qty") or 0) > 0), None)
    closes = [o for o in orders if str(o.get("action")) in ("close", "close_leg") and int(o.get("pid") or -1) == pid]
    live["exit"] = live_exit(position, [o for o in closes if o.get("action") == "close"], first_expiry)
    if entry is None:
        out["why"] = "the book holds no open order for this position"
        return out
    if any(o.get("action") == "close_leg" and str(o.get("status")) not in NOT_SENT for o in closes):
        out["why"] = "a broken structure's legs were closed one by one (close_leg): the puppet replays whole structures only"
        return out
    if min(days) < 0 or max(days) > MAX_DTE:
        out["why"] = f"a leg is {max(days)} days from expiry at entry: the Gym shows 0 to {MAX_DTE}"
        return out
    sent = [o for o in closes if o.get("action") == "close" and str(o.get("status")) not in NOT_SENT]
    filled = [o for o in sent if int(o.get("filled_qty") or 0) > 0]
    closed_day = ny_day(position.get("closed_at"))
    # The trade's last session: the day its last close filled; else (expired, or a close the venue made) its first leg's
    # expiry, or the day the book closed it if that came first.
    end = str(filled[-1].get("day")) if filled else min(first_expiry, closed_day or first_expiry)
    if end < opened_day:
        out["why"] = f"its exit day {end} is before its entry day {opened_day}"
        return out
    schedule = []
    for o in sent:
        day = str(o.get("day") or "")
        if expiry_close(o, first_expiry):
            continue  # the House's expiry close: the Gym's venue makes its own on the expiry day
        if day > end:
            continue
        try:
            to_expiry = (dt.date.fromisoformat(first_expiry) - dt.date.fromisoformat(day)).days
        except ValueError:
            continue
        minute = _minute(o.get("placed_minute"))
        limit = _num(o.get("limit_value"))
        if minute is None:
            continue
        natural = bool(o.get("forced")) or limit is None
        schedule.append((to_expiry, minute, 0.0 if natural else float(limit), 1 if natural else 0, _tif(o.get("tif"))))
    out["truncated_closes"] = max(0, len(schedule) - MAX_CLOSES)
    schedule = schedule[:MAX_CLOSES]
    minute = _minute(entry.get("placed_minute"))
    if minute is None:
        minute = _minute(position.get("opened_minute"))
    limit = _num(entry.get("limit_value"))
    qty = int(entry.get("qty") or opened_qty or 1)
    days_list = sessions(opened_day, end)
    if days_list is None:
        out.update(why="the NYSE calendar cannot say (asked again next pass)", retry=True)
        return out
    if not days_list or days_list[0] != opened_day:
        out["why"] = f"the NYSE calendar has no session on its entry day {opened_day}"
        return out
    out.update(ok=True, end=end, sessions=days_list, params={
        "root": out["root"], "type": out["type"], "qty": max(1, qty),
        "leg_strike": strikes, "leg_call": calls, "leg_side": sides, "leg_ratio": ratios, "leg_dte": days,
        "open_minute": minute, "open_limit": 0.0 if limit is None else float(limit), "open_natural": 1 if limit is None else 0,
        "open_tif": _tif(entry.get("tif")),
        "close_expiry": [s[0] for s in schedule], "close_minute": [s[1] for s in schedule],
        "close_limit": [s[2] for s in schedule], "close_natural": [s[3] for s in schedule],
        "close_tif": [s[4] for s in schedule],
        "dte_lo": min(days), "dte_hi": max(days)})
    return out


def job_for(p: Mapping[str, Any]) -> GymJob:
    """The Gym job of a plan: the puppet over the trade's own sessions on a gate box."""
    return GymJob(family=f"{FAMILY_PREFIX}{p['pid']}", version=None, code=PUPPET, params=dict(p["params"]), window="forward",
                  roots=(str(p["root"]),), purpose=PURPOSE, gate=GATE_REASON, start=str(p["start"]), end=str(p["end"]),
                  priority=PRIORITY)


# ------------------------------------------------------------------------------------------------- the verdict
def twin_exit(fills: Mapping[str, Any], *, last_day: str | None, first_expiry: str | None) -> str:
    """How the twin left, from the Gym's fill counts (`results.fill_stats`; a forward view carries no exit reason):
    "house_close" (the Gym's expiry close or its 15:30 liquidation), "settled" (cash-settled or exercised at the close),
    "program_close" (a replayed close order filled), "expired" (left to expire on its expiry day), else "window_end" (still
    open at the window's last minute: closed at the natural there, the engine's rule)."""
    if int(fills.get("liquidated") or 0) > 0:
        return "house_close"
    if int(fills.get("settled") or 0) + int(fills.get("exercised") or 0) > 0:
        return "settled"
    if int(fills.get("closes") or 0) > 0 and int(fills.get("filled") or 0) >= 2:
        return "program_close"
    if last_day is not None and first_expiry is not None and last_day >= first_expiry:
        return "expired"
    return "window_end"


AGREE = {"house_close": ("house_close",), "house_forced": ("program_close",), "program_close": ("program_close",),
         "expired": ("expired", "settled")}


def judge(p: Mapping[str, Any], result: Mapping[str, Any], *, at: float) -> dict[str, Any]:
    """The twin record of plan `p` from its Gym result (the module docstring's verdicts)."""
    rec = record(p, at=at)
    rec.update(image=result.get("gym_image"), bundle=result.get("gym_bundle"), fill_model=result.get("fill_model"),
               run_id=result.get("run_id"))
    if result.get("status") != "ok":
        rec.update(status="failed", why=f"the Gym run's status is {result.get('status')}: {str(result.get('reason') or '')[:200]}")
        return rec
    days = [str(row[0]) for row in result.get("daily") or [] if row]
    trades = [t for t in result.get("trades") or [] if isinstance(t, Mapping)]
    fills = dict(result.get("fills") or {})
    rec["fills"] = {k: fills.get(k) for k in ("orders", "opens", "closes", "filled", "partial_fills", "expired", "cancelled",
                                              "rejected", "liquidated", "settled", "exercised", "reject_reasons",
                                              "at_natural", "open_slip_half_spreads", "close_slip_half_spreads")}
    rec["days"] = days
    expected = list(p.get("sessions") or [])
    if not days or days[0] != p["start"]:
        rec.update(status="no_contract", why=f"the gate image has no {p['root']} day {p['start']} (its first is "
                                             f"{days[0] if days else 'none'})")
        return rec
    if days != expected:
        if days == expected[:len(days)]:
            # The image stops before the trade's last session (its ready day ahead of its files): a later image's.
            rec.update(status="failed", why=f"the image's {p['root']} days end {days[-1]}, before the trade's {expected[-1]}")
        else:
            rec.update(status="unpriceable", why=f"the image's {p['root']} days {days} are not the trade's NYSE sessions "
                                                 f"{expected}")
        return rec
    if not trades:
        if int(fills.get("opens") or 0) == 0:
            rec.update(status="no_contract", why="no two-sided quote of a leg at the decision minute on the image (or no "
                                                 "chain that minute): the open was not sent")
        else:
            rec.update(status="no_fill", why="the open was sent and the Gym's fill model did not fill it in its time in force")
        return rec
    if len(trades) != 1 or str(trades[0].get("day")) != p["start"]:
        rec.update(status="unpriceable", why=f"the twin made {len(trades)} trades, the first on {trades[0].get('day')}")
        return rec
    t = trades[0]
    pnl, loss = _num(t.get("pnl")), _num(t.get("max_loss"))
    if pnl is None or loss is None or loss <= 0:
        rec.update(status="unpriceable", why="the twin's trade has no P&L or maximum loss")
        return rec
    exit_ = twin_exit(fills, last_day=days[-1], first_expiry=p.get("first_expiry"))
    twin = {"pnl": round(pnl, 2), "max_loss": round(loss, 2), "r": round(pnl / loss, 5), "exit": exit_}
    rec.update(status="priced", why=None, twin=twin)
    live_r = (rec.get("live") or {}).get("r")
    rec["gap_r"] = None if live_r is None else round(float(live_r) - twin["r"], 5)
    live_exit_ = (rec.get("live") or {}).get("exit")
    rec["exit_agrees"] = exit_ in AGREE.get(str(live_exit_), ())
    return rec


def record(p: Mapping[str, Any], *, at: float) -> dict[str, Any]:
    """The fields every twin record carries, whatever its verdict."""
    return {"pid": int(p["pid"]), "family": p.get("family"), "instance": p.get("instance"), "root": p.get("root"),
            "type": p.get("type"), "start": p.get("start"), "end": p.get("end"), "first_expiry": p.get("first_expiry"),
            "live": dict(p.get("live") or {}),
            "puppet": PUPPET_SHA[:16], "at": dt.datetime.fromtimestamp(at, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": None, "why": None, "twin": None, "gap_r": None, "exit_agrees": None,
            "truncated_closes": int(p.get("truncated_closes") or 0)}


# ------------------------------------------------------------------------------------------------- the round
def cfg(settings: Mapping[str, Any]) -> dict[str, Any] | None:
    """The switch (`forward.twins`): None when it is null or false (off); else the defaults under what it sets."""
    raw = (settings.get("forward") or {}).get("twins", DEFAULTS)
    if raw is None or raw is False:
        return None
    out = dict(DEFAULTS)
    if isinstance(raw, Mapping):
        for key in DEFAULTS:
            value = raw.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 1:
                out[key] = int(value)
    return out


def records(store: Any) -> dict[str, dict[str, Any]]:
    """Every twin record ({str(pid): record}); {} when none or unreadable."""
    try:
        value = store.get(TWINS_KEY) or {}
    except Exception:  # noqa: BLE001 - no records: every close falls back
        return {}
    return {str(k): dict(v) for k, v in value.items() if isinstance(v, Mapping)} if isinstance(value, Mapping) else {}


class Twins:
    """The per-close fill replay's round (the module docstring)."""

    def __init__(self, store: Any, pool: Any, settings: Mapping[str, Any], *, root: str | Path, gate: Any,
                 clock: Callable[[], float] = time.time, since: float | None = None):
        self.store, self.pool, self.settings, self.root, self.gate, self.clock = store, pool, settings, Path(root), gate, clock
        self.since = since

    def cfg(self) -> dict[str, Any] | None:
        return cfg(self.settings)

    def inception(self) -> float:
        if self.since is not None:
            return float(self.since)
        from ..swarm import dlane

        return dt.datetime.fromisoformat(dlane.DONE["inception"].replace("Z", "+00:00")).timestamp()

    def due(self) -> bool:
        """On, a ready forward day on the gate image, and this ready day not tried within `forward.every_seconds`. Never
        raises (the main loop calls it every few seconds): a read that fails is "not due"."""
        try:
            if self.cfg() is None:
                return False
            target = self.gate.forward_target()
            if target is None:
                return False
            attempt = self.store.get(ATTEMPT_KEY) or {}
            every = float((self.settings.get("forward") or {}).get("every_seconds", 3600))
            return attempt.get("target") != target or self.clock() - float(attempt.get("at") or 0.0) >= every
        except Exception:  # noqa: BLE001 - the twins never stop the loop
            return False

    def pending(self, book: Mapping[str, Any], known: Mapping[str, Mapping[str, Any]], *, ready_day: str,
                attempts: int) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        """(plans to run now, records judged without a run): every closed agent position with no final record, whose
        exit day the image already holds; a plan that cannot be replayed is judged "unpriceable" at once. A failed twin
        is asked again at most `attempts` times on one ready day, and again from the next ready day (a new image)."""
        todo, judged = [], {}
        now = self.clock()
        for pos in book["positions"]:
            key = str(int(pos["pid"]))
            old = known.get(key) or {}
            tries = int(old.get("attempts") or 0) if old.get("ready_day") == ready_day else 0
            if old.get("status") in FINAL or tries >= attempts:
                continue
            p = plan(pos, book["orders"].get(int(pos["pid"]), []))
            if not p["ok"]:
                if not p.get("retry"):
                    judged[key] = {**record(p, at=now), "status": "unpriceable", "why": p["why"]}
                continue
            if str(p["end"]) > ready_day:
                continue  # the image does not hold its exit day yet: a later night's
            p["attempts"] = tries
            todo.append(p)
        return todo, judged

    def run(self) -> dict[str, Any]:
        settings = self.cfg()
        out: dict[str, Any] = {"jobs": 0, "judged": {}, "waiting": 0}
        if settings is None:
            return {**out, "off": True}
        target = self.gate.forward_target()
        if target is None:
            return {**out, "why": "no ready forward day on the gate image"}
        self.store.put(ATTEMPT_KEY, {"target": target, "at": self.clock()})
        try:
            book = read_live(self.root / LIVE_DB, since=self.inception())
        except Exception as exc:  # noqa: BLE001 - an unreadable book: nothing judged, said in the event
            out["error"] = f"the live book cannot be read: {type(exc).__name__}: {str(exc)[:200]}"
            self.store.event("swarm.twin", None, {"action": "round", **out})
            return out
        known = records(self.store)
        todo, judged = self.pending(book, known, ready_day=str(target["day"]), attempts=settings["attempts"])
        known.update(judged)
        out["waiting"] = max(0, len(todo) - settings["max_jobs"])
        todo = todo[: settings["max_jobs"]]
        if judged:
            self.store.put(TWINS_KEY, known)
        jobs = [(p, self.pool.submit(job_for(p))) for p in todo]
        from ..swarm import settings as settings_mod

        timeout = settings_mod.run_timeout(self.settings) + 600
        for p, job in jobs:
            key = str(p["pid"])
            try:
                result = self.pool.wait(job, timeout)
                rec = judge(p, result, at=self.clock())
            except PoolError as exc:
                # A job the pool failed (a box that erred twice, a root the image lacks that night) is no verdict on the
                # trade: asked again, on the next image too.
                rec = {**record(p, at=self.clock()), "status": "failed", "why": f"the Gym job failed: {str(exc)[:240]}"}
            if rec["status"] == "failed":
                rec.update(attempts=int(p.get("attempts") or 0) + 1, ready_day=str(target["day"]))
            known = records(self.store)
            known[key] = rec
            self.store.put(TWINS_KEY, known)
            out["jobs"] += 1
            out["judged"][rec["status"]] = out["judged"].get(rec["status"], 0) + 1
        for rec in judged.values():
            out["judged"][rec["status"]] = out["judged"].get(rec["status"], 0) + 1
        out["target"] = target
        self.store.event("swarm.twin", None, {"action": "round", **out, "puppet": PUPPET_SHA[:16]})
        return out


__all__ = ["Twins", "PUPPET", "PUPPET_SHA", "TWINS_KEY", "ATTEMPT_KEY", "GATE_REASON", "FINAL", "plan", "judge", "job_for",
           "read_live", "records", "cfg", "twin_exit", "live_exit", "expiry_close", "sessions", "agent"]
