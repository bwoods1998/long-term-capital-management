"""FILLS AND TWINS of the forward record (release E3): the live-like re-price, the fill gap, intent agreement, A14.

Owner: D (league/ops/E3_INTERFACES.md). Protected. Called by the forward shadow's night (league/ops/forward_shadow.py:
`begin`, `on_run` after each program's write, `finish`; each call in its own try/except: a failure here never loses a
shadow day) and by the Done meter (league/ops/dlane_report.py `a14_of` -> `a14_reading`). It writes `fwd_fillgap`,
`fwd_ll`, `fwd_lotgap`, `fwd_twins` and `fwd_part` of `<state>/forward.sqlite` (league/ops/forward_db.py) and its
events; it reads the live book and the swarm store read-only. Report only: no engine fill model changes here.

THE TIMING TABLE AND THE LIVE-LIKE SERIES (D10; league/ops/fill_minutes.py). `official(day, sym, at)` = the store's raw
open or close; `drift_bp = (livelike / official - 1) * 1e4`: one `fwd_fillgap` row a (day, symbol, at), every store
symbol. The live-like series of a shadow run: for each lot, N_e = weight * capital and N_x = qty * exit_px (closed
lots); `pnl_ll(d) = r(d) * capital - sum over lots entered on d of N_e * delta_e + sum over lots exited on d of N_x *
delta_x`, delta = drift_bp / 1e4 at the lot's (day, symbol, at); r_ll(d) = pnl_ll(d) / capital (quantities held at
the official run's: first order). A day with a needed drift missing gets no `fwd_ll` row and one `no_minute` event
(once a (pid, day)); the row is written the night its minute arrives (the minutes job's backfill).

THE FILL GAP OF A CLOSED LIVE LOT (D11): its `eq_lots` row; its E1 twin record `equity_twins["eq:<lid>"]` (the swarm
store's kv, league/ops/twins.py), status "priced". `model_bp = twin["k"] * twin["hs_bp"]`. Cost-positive. Entry:
`entry_slip_bp` = the twin's; timing_entry_bp = (livelike(opened_day, sym, entry_at) / entry_official - 1) * 1e4;
exec_entry_bp = entry_slip_bp - timing_entry_bp. Exit: `exit_slip_bp` = the twin's; timing_exit_bp = (1 -
livelike(exit_day, sym, exit_at) / exit_official) * 1e4; exec_exit_bp = exit_slip_bp - timing_exit_bp. side_gap_bp =
((entry_slip_bp - model_bp) + (exit_slip_bp - model_bp)) / 2 (how much worse than the model, a side). `twin_gap_bp` =
the twin's `gap_bp` (about -side_gap_bp). Timing and execution are None when a minute is missing. A lot's row is
written once (the store is append-only), so while the minutes job may still fetch a missing file of its entry or
exit day (the last `fill_minutes.BACKFILL_SESSIONS` forward days) the row waits. PARTICIPATION of a
live instance I through day L: its twin run's lots and its live lots, both with entry days in
[next_session(d_first(I)), L]; a lot's key is (symbol, entry day, entry_at); `matched` = the multiset intersection,
`missed` = twin only, `extra` = live only; rate = matched / (matched + missed + extra).

INTENT AGREEMENT (D12). A live instance I is an `eq_instances` row; its registry key is its id less ":r". `d_first(I)`
= the latest session d with `schedule.moments(d).bars_at <= created_at(I)` (E1's own `_last_closed` rule). THE TWIN RUN
of I is D3's run of its registered program started flat at `next_session(d_first(I))` (`Shadow.run_from`; the
registry's own run began at registration and holds another book). BOTH SIDES READ THE SAME RULE (`keys_of`): of the
first `config.MAX_INTENTS` intents of a session, one whose `at` (default "open") is neither "open" nor "close" is
dropped; a buy is kept iff its symbol is one of the program's NEEDS symbols (whatever its size says); a sell is kept
iff it names a lot that side holds (a second sell of the same lot too); everything else (an intent that is not a
dict, a buy outside NEEDS, a sell of an unknown lot, a cancel) is dropped on both sides. Keys: a kept buy ->
"B|SYM|at"; a kept sell -> "S|SYM|at|<entry day>". Shadow keys of decision day d come from the answer of
`decider.kind("equity", "decide", {"jobs": [{"key", "inputs"}]})` on `elane_train.state_inputs(twin run)`'s inputs for
d (`shadow_intents`); live keys from I's `eq_intents` rows with `decided_day` = d (`live_intents`: kind "buy" AND
symbol in the instance's NEEDS symbols; kind "sell" AND `lid` NOT NULL, through `eq_lots.lid`; every other row is
dropped; a row's status is not read). No kept row is the empty set. agree(I, d) = (Counter(live keys) ==
Counter(shadow keys)). The row for d is written once `next_session(d)` has closed in the store (the live side is then
final), in day order from `d_first(I)`. UNREADABLE sessions get a row with `agree` NULL and its `why` (`UNREADABLE`),
and are left out of every share:
- "split" when a lot the twin holds at d has a "split" row in the twin run's `actions` for its symbol on a later day
  of its hold (`split_sessions`: `state_inputs` keeps the lot's post-split quantity against pre-split marks);
- "retired" from the session the House retired the instance at (`d_retired`: the same rule as `d_first`, on
  `retired_at`). The book retires or demotes an instance INSIDE that session's decide step, before it asks the
  program, so no live decision exists from then on: the House's exit rules close its lots at the next open, and its
  twin, which nobody retired, goes on trading. Such a session is not a disagreement of the program with its replay; it
  is shown, counted and left out. The rows run through the session before the instance's last lot closed (what
  D13's range needs); after that the instance has no twin run at all.
A twin run whose decides were interrupted (or whose run the child failed) writes no row that night, one
`twin_interrupted` event (once an (instance, night)), and is tried again the next. A registry `run_sha` that differs
from the instance's is a `twin_sha_mismatch` event and no twin; no registry row is `twin_unregistered` (each once an
instance). With the forward mode "off" (or settings that cannot be read) `begin`, `on_run` and `finish` write
nothing.

A DISAGREEMENT IS DATA, NEVER AN ERROR (THE BARS HASH, league/ops/forward_db.py; found after the spec, binding). The
vendor rounds adjustment=all prices to cents, so the as-of bars a live decision read and the store's are not always
byte-identical, and an intent can flip for that cause alone. Every `fwd_twins` row carries `shadow_bars`
(`forward_db.bars_hash` of the twin decision's inputs: `shadow_bars`) and `live_bars` (the same hash of the live
decision's bars; NULL when not known), and a row with `agree` 0 carries its `cause` (`cause`: "bars" when both are
known and differ, "program" when they are equal, "unknown" when the live one is not known). THE LIVE DECISION'S BARS
are in the book's `eq_bars` only until the next session's decide fetches the adjusted series again, so `finish` takes
the hash the night of the decision (`live_bars`: `ctx.inputs_from_fetch` on the book's raw and all rows through that
day) and keeps it in a `live_bars` event, once an (instance, day); the session's row, written a night later, reads
it. Nothing raises for a disagreement and A14's rule does not change: the session counts as not agreed, whatever its
cause, and the counts by cause are reported beside.

THE A14 READING (D13; `a14_reading`) of a Done checkpoint's counted closes C. C_eq = C's equity closes; with none it
does not apply (it holds). Gap: over C_eq's twin records that are final and priced, gap ok iff |mean(gap_bp)| <=
`forward_db.A14_GAP_BP` (None with no priced twin): the SIZE of the mean gap, either way. Intents: for each instance
I of C_eq, the sessions d with d_first(I) <= d <= previous_session(I's last counted exit day), less the unreadable
ones; share = agreed / all those sessions; intents ok iff share >= `forward_db.A14_AGREE` (a session with no
`fwd_twins` row is not agreed and counts in `missing`; None with no session). A14 holds iff gap ok is True and
intents ok is True. It is final iff every close of C_eq has a final twin and `missing` = 0. Unmeasured never holds.
`d_first(I)` is read as the day of the instance's first `fwd_twins` row (the rows are written in day order from it);
an instance with no row yet has every session from the one before its first counted lot's entry missing.

Standard library and numpy only.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from . import fill_minutes, forward_db
from .forward_db import ShadowRun

#: `fwd_twins.why` of an unreadable session (D12): a split during a hold; a session at or after the one the House
#: retired the instance at.
UNREADABLE = ("split", "retired")
#: Every key `a14_reading` returns, on every branch (a missing store included).
A14_KEYS = ("applies", "holds", "final", "why", "gap", "intents", "by_instance")
A14_GAP_KEYS = ("closes", "priced", "unpriced", "pending", "mean_gap_bp", "bound_bp", "ok")
#: `disagreed` and `causes` ({cause: sessions}, `forward_db.CAUSES`) are counted beside the share, never in its rule.
A14_INTENT_KEYS = ("instances", "sessions", "agreed", "missing", "unreadable", "share", "bound", "ok", "disagreed",
                   "causes")
A14_INSTANCE_KEYS = ("instance", "sessions", "agreed", "missing", "unreadable")
#: The live book and the swarm store under the state root (league/ops/twins.py's names).
LIVE_DB = "live.sqlite"
SWARM_DB = "swarm.sqlite"
#: The decider kind a twin's instance is loaded under, with the live book's own limits (league/equity/live.py).
KIND = "equity"
DECIDE_TIMEOUT, DECIDE_MAX_ERRORS = 1.0, 25
#: The real route's instance suffix (`league.equity.live.REAL_SUFFIX`): an instance's registry key is its id less it.
REAL_SUFFIX = ":r"
#: The child's failures of a twin's run (E1's `runner.RunFailed`, the decider's `DeciderError`), by class name as
#: league/swarm/elane_train.py names them: the House's, as an interrupted decide is.
RUN_FAILURES = ("RunFailed", "DeciderError", "BudgetSpent")
#: The receipt keys of `finish` (counts).
FINISH_KEYS = ("instances", "twins", "disagreed", "lots", "interrupted", "live_bars", "unreadable", "unregistered",
               "mismatched", "failed")
_MISSING = object()


class TwinInterrupted(RuntimeError):
    """A twin run's decides were interrupted (the child restarted, or an answer's `stats.calls` is not the sessions
    asked so far): the House's. One `twin_interrupted` event, no row for that instance that night."""


# ------------------------------------------------------------------------------------------------------ small helpers
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _iso(day: Any) -> str:
    if isinstance(day, dt.datetime):
        raise ValueError(f"a session day is a date or an ISO day, not the moment {day!r}")
    return day.isoformat() if isinstance(day, dt.date) else dt.date.fromisoformat(str(day)[:10]).isoformat()


def _date(day: Any) -> dt.date:
    return dt.date.fromisoformat(_iso(day))


def _days(ordinals: Any) -> list[str]:
    """ISO days of a `store.Bars`' or a `screen.Series`' int32 day ordinals."""
    from ..equity.store import from_ordinal

    return [from_ordinal(int(d)).isoformat() for d in ordinals]


def _cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`forward_db.cfg`, and the code defaults (mode "off") when the settings cannot be read."""
    try:
        return dict(forward_db.cfg(settings))
    except Exception:  # noqa: BLE001 - an unreadable block is "off"
        return dict(forward_db.DEFAULTS)


def _on(cfg: Mapping[str, Any], key: str) -> bool:
    """Whether the forward record is on (`mode` above "off") and its switch `key` is true."""
    return cfg.get("mode") in forward_db.MODES[1:] and cfg.get(key) is True


def _settings(root: str | Path, shadow: Any) -> Any:
    """The night's settings: the shadow's own (`Shadow(..., settings=)`), else the swarm's as the House reads them."""
    found = getattr(shadow, "settings", _MISSING)
    if found is not _MISSING:
        return found
    from ..swarm import settings as settings_mod

    return settings_mod.load(root)


def _sessions(first: dt.date, last: dt.date) -> list[str]:
    """The ISO sessions d with first <= d <= last (the equity calendar's)."""
    from ..equity import schedule

    out, day = [], first
    while day <= last:
        if schedule.is_session(day):
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def _decision_session(moment: float) -> dt.date:
    """The latest session d with `schedule.moments(d).bars_at <= moment` (the book's `_last_closed`): the decision
    session a tick at `moment` belongs to. ValueError when the calendar does not reach one."""
    from ..equity import schedule

    day = schedule.ny_day(moment)
    for _ in range(schedule.HORIZON_DAYS):
        m = schedule.moments(day)
        if m is not None and m.bars_at <= moment:
            return day
        day -= dt.timedelta(days=1)
    raise ValueError(f"no NYSE session's bars moment within {schedule.HORIZON_DAYS} days before {moment!r}")


def _lot_id(value: Any) -> int | None:
    """A lot id as a program names it: a whole number at or above zero (league/equity/program.py), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number != int(number) or number < 0:
        return None
    return int(number)


# ---------------------------------------------------------------------------------------------- D12: the one key rule
def d_first(instance_row: Mapping[str, Any]) -> dt.date:
    """D12: the latest session d with `schedule.moments(d).bars_at <= created_at` of an `eq_instances` row (16:25 ET
    and 08:00 the next morning name the same session)."""
    return _decision_session(float(instance_row["created_at"]))


def d_retired(instance_row: Mapping[str, Any]) -> dt.date | None:
    """The session an instance was retired or demoted at (`d_first`'s rule on its `retired_at`): the first session it
    has no live decision for. None while it is alive."""
    retired = _num(instance_row.get("retired_at"))
    return None if retired is None else _decision_session(retired)


def keys_of(intents: Sequence[Any], *, needs: Sequence[str], held: Mapping[Any, Mapping[str, Any]]) -> list[str]:
    """D12's ONE rule, used for both sides: the keys of one session's intents as a program gives them ({"buy": SYM,
    "at"} | {"sell": <lot id>, "at"} | {"cancel": ...}; the live side's `eq_intents` rows are read into that shape
    first). `needs`: the program's NEEDS symbols; `held`: {lot id: {"symbol", "entry_day"}} that side holds at the
    decision. A list (duplicates kept: the comparison is a multiset's)."""
    from ..equity import config

    names = {str(s).strip().upper() for s in needs or ()}
    lots = {}
    for lid, lot in (held or {}).items():
        lid = _lot_id(lid)
        if lid is not None and isinstance(lot, Mapping):
            lots[lid] = lot
    if isinstance(intents, Mapping):
        intents = [intents]
    if not isinstance(intents, (list, tuple)):
        return []
    out = []
    for raw in list(intents)[:config.MAX_INTENTS]:
        if not isinstance(raw, Mapping):
            continue
        at = raw.get("at", "open")
        if at not in fill_minutes.FILL_POINTS:
            continue
        if "buy" in raw:
            symbol = raw.get("buy")
            symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
            if symbol and symbol in names:
                out.append(f"B|{symbol}|{at}")
        elif "sell" in raw:
            lot = lots.get(_lot_id(raw.get("sell")))
            if lot is not None:
                out.append(f"S|{str(lot.get('symbol') or '').upper()}|{at}|{str(lot.get('entry_day') or '')}")
    return out


def agree(live: Sequence[str], shadow: Sequence[str]) -> bool:
    """`Counter(live) == Counter(shadow)`: two empty sessions agree."""
    return Counter(live or ()) == Counter(shadow or ())


def cause(agreed: bool | None, live: str | None, shadow: str | None) -> str | None:
    """`fwd_twins.cause` (`forward_db.CAUSES`): None unless `agreed` is False; then "unknown" when `live` or `shadow`
    is None, "bars" when they differ, "program" when they are equal."""
    if agreed is not False:
        return None
    if not live or not shadow:
        return "unknown"
    return "program" if str(live) == str(shadow) else "bars"


def participation(live_lots: Sequence[Mapping[str, Any]], twin_lots: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """D11's participation: {"matched", "missed", "extra", "rate"} over lots keyed (symbol, entry day, entry_at);
    `rate` None with no lot on either side."""
    def keys(lots: Sequence[Mapping[str, Any]]) -> Counter:
        return Counter((str(lot.get("symbol") or "").upper(), str(lot.get("entry_day") or lot.get("opened_day") or ""),
                        str(lot.get("entry_at") or "open")) for lot in lots or () if isinstance(lot, Mapping))

    live, twin = keys(live_lots), keys(twin_lots)
    matched = sum((live & twin).values())
    missed, extra = sum(twin.values()) - matched, sum(live.values()) - matched
    total = matched + missed + extra
    return {"matched": matched, "missed": missed, "extra": extra, "rate": matched / total if total else None}


# ------------------------------------------------------------------------------------------------- D12: the twin's side
def _decisions(run: ShadowRun) -> Iterator[tuple[str, Any, dict[int, dict[str, str]]]]:
    """(decision day, the Gym's inputs at that close, the lots the twin holds there: {lot id: {"symbol", "entry_day"}})
    for every decision of a twin run, through E2's `elane_train.state_inputs`."""
    from ..equity.store import from_ordinal
    from ..swarm import elane_train

    entry = {int(lot["lid"]): str(lot.get("entry_day") or "") for lot in (run.result.get("lots") or [])
             if isinstance(lot, Mapping) and _lot_id(lot.get("lid")) is not None}
    try:
        for inputs in elane_train.state_inputs(run):
            held = {int(p["id"]): {"symbol": str(p["symbol"]), "entry_day": entry.get(int(p["id"]), "")}
                    for p in inputs.positions}
            yield from_ordinal(int(inputs.days[-1])).isoformat(), inputs, held
    except elane_train.StateCheckInterrupted as exc:
        raise TwinInterrupted(f"the twin run does not fit its bars: {str(exc)[:200]}") from None


def _twin(decider: Any, run: ShadowRun) -> list[tuple[str, list[str], str]]:
    """[(decision day, the twin's keys, the bars hash of that decision)] of a twin run, in day order: one instance
    loaded once, one "decide" a session, dropped at the end. `TwinInterrupted` as `shadow_intents` says."""
    if decider is None:
        raise TwinInterrupted("the night carries no decider to ask the twin's decides of")
    program = run.program
    key = f"e3-twin:{program.key}"
    needs = [str(s) for s in (program.needs or {}).get("symbols") or ()]
    payload = {"code": str(program.code), "params": dict(program.params or {}), "name": str(program.key),
               "timeout": DECIDE_TIMEOUT, "max_errors": DECIDE_MAX_ERRORS}
    restarts = getattr(decider, "restarts", None)
    out: list[tuple[str, list[str], str]] = []
    asked = 0
    try:
        try:
            decider.kind_load(KIND, key, payload)
        except Exception as exc:  # noqa: BLE001 - the child's: the twin is tried again the next night
            raise TwinInterrupted(f"the twin's program did not load in the decider child ({type(exc).__name__})") \
                from None
        for day, inputs, held in _decisions(run):
            try:
                answer = decider.kind(KIND, "decide", {"jobs": [{"key": key, "inputs": inputs}]})
            except Exception as exc:  # noqa: BLE001 - the child failed (it was restarted: the instance lost its memory)
                raise TwinInterrupted(f"the decider child failed a twin's decide ({type(exc).__name__})") from None
            asked += 1
            if getattr(decider, "restarts", None) != restarts:
                raise TwinInterrupted("the decider child restarted during the twin's decides (its instance was "
                                      "reloaded with fresh memory)")
            results = answer.get("results") if isinstance(answer, Mapping) and answer.get("ok") else None
            row = results.get(key) if isinstance(results, Mapping) else None
            if not isinstance(row, Mapping) or row.get("missing"):
                raise TwinInterrupted("the twin's instance went missing in the decider child")
            if row.get("error"):
                raise TwinInterrupted(f"the child could not build a twin's ctx: {str(row.get('error'))[:160]}")
            stats = row.get("stats") if isinstance(row.get("stats"), Mapping) else {}
            calls = stats.get("calls")
            if not stats.get("disqualified") and (isinstance(calls, bool) or not isinstance(calls, int)
                                                  or calls != asked):
                # A disqualified instance answers nothing and counts no call; any other must have run every decide
                # it was asked since its load, or the child reloaded it with fresh memory.
                raise TwinInterrupted(f"the decider child reloaded the twin's instance (it answered its decide "
                                      f"{calls!r}, not {asked}): its memory was lost")
            out.append((day, keys_of(row.get("intents"), needs=needs, held=held), forward_db.bars_hash(inputs)))
    finally:
        try:
            decider.kind_drop(KIND, key)
        except Exception:  # noqa: BLE001 - a drop that fails leaves an instance a restart clears
            pass
    return out


def shadow_intents(decider: Any, run: ShadowRun) -> dict[str, list[str]]:
    """{decision day: keys} of a twin run: `decider.kind_load("equity", key, {"code", "params", "name", "timeout":
    1.0, "max_errors": 25})`, one "decide" a session on `elane_train.state_inputs(run)`'s inputs, `kind_drop` in
    `finally`. NEVER A SILENT RELOAD, as E2's restart check: after every decide `decider.restarts` is unchanged and
    the answer's `stats.calls` == the sessions asked so far, else `TwinInterrupted`."""
    return {day: keys for day, keys, _ in _twin(decider, run)}


def shadow_bars(run: ShadowRun) -> dict[str, str]:
    """{decision day: `forward_db.bars_hash`} of a twin run's decisions (`elane_train.state_inputs(run)`'s inputs; the
    parent's arithmetic, no child)."""
    return {day: forward_db.bars_hash(inputs) for day, inputs, _ in _decisions(run)}


def split_sessions(run: ShadowRun) -> set[str]:
    """D12's unreadable sessions of a twin run: the decision days d at which a lot the twin holds has a "split" row in
    the run's `actions` for its symbol on a later day of its hold."""
    days = _days(run.bars.days)
    index = {day: i for i, day in enumerate(days)}
    splits: dict[str, list[int]] = {}
    for action in run.result.get("actions") or []:
        if isinstance(action, Mapping) and action.get("kind") == "split" and str(action.get("day")) in index:
            splits.setdefault(str(action.get("symbol")), []).append(index[str(action.get("day"))])
    out: set[str] = set()
    for lot in run.result.get("lots") or []:
        if not isinstance(lot, Mapping) or str(lot.get("entry_day")) not in index:
            continue
        entry = index[str(lot.get("entry_day"))]
        leave = index.get(str(lot.get("exit_day"))) if lot.get("exit_day") else None
        for at in splits.get(str(lot.get("symbol")), ()):
            if entry < at and (leave is None or at <= leave):
                out.update(days[entry:at])
    return out


# ------------------------------------------------------------------------------------------------- D12: the live side
def _tables(db: sqlite3.Connection) -> set[str]:
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _kv(db: sqlite3.Connection, key: str) -> Any:
    row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    try:
        return json.loads(row[0]) if row else None
    except (TypeError, ValueError):
        return None


def _live_keys(rows: Sequence[Mapping[str, Any]], needs: Sequence[str]) -> dict[str, list[str]]:
    """{decided day: keys} of one instance's `eq_intents` rows in iid order, each joined to its lot (`lot_symbol`,
    `lot_day`): the rows read into a program's intent shape, then `keys_of`."""
    by_day: dict[str, tuple[list[dict[str, Any]], dict[int, dict[str, str]]]] = {}
    for row in rows:
        intents, held = by_day.setdefault(str(row["decided_day"]), ([], {}))
        kind = row["kind"]
        if kind == "buy":
            intents.append({"buy": row["symbol"], "at": row["at"]})
        elif kind == "sell":
            intents.append({"sell": row["lid"], "at": row["at"]})
            if row["lid"] is not None and row["lot_symbol"] is not None:
                held[int(row["lid"])] = {"symbol": str(row["lot_symbol"]), "entry_day": str(row["lot_day"] or "")}
        elif kind == "cancel":
            intents.append({"cancel": row["lid"]})
        # a "house_exit" row is the House's own exit rule, never an intent of the program: it is not read
    return {day: keys_of(intents, needs=needs, held=held) for day, (intents, held) in by_day.items()}


_INTENTS_SQL = ("SELECT i.iid, i.instance, i.decided_day, i.at, i.kind, i.symbol, i.lid, l.symbol AS lot_symbol, "
                "l.opened_day AS lot_day FROM eq_intents i LEFT JOIN eq_lots l ON l.lid = i.lid "
                "WHERE i.kind IN ('buy', 'sell', 'cancel'){where} ORDER BY i.iid")


def live_intents(live_path: str | Path, instance: str, *, needs: Sequence[str]) -> dict[str, list[str]]:
    """{decided day: keys} of a live instance from the book's `eq_intents` rows (read-only; D12's live rule)."""
    from . import guard

    def read(db: sqlite3.Connection) -> list[dict[str, Any]]:
        if not {"eq_intents", "eq_lots"} <= _tables(db):
            return []
        return guard.rows(db, _INTENTS_SQL.format(where=" AND i.instance=?"), (str(instance),))

    return _live_keys(guard.read(live_path, read), needs)


def _book_bars(db: sqlite3.Connection, instance: str, day: str, needs: Mapping[str, Any]) -> str | None:
    from ..equity import ctx as C
    from ..equity.program import Needs
    from . import guard

    if not {"eq_bars", "eq_instances", "kv"} <= _tables(db):
        return None
    decision = _kv(db, "eq_decision")
    if not isinstance(decision, Mapping) or str(decision.get("day")) != day:
        return None
    row = db.execute("SELECT last_decided_day FROM eq_instances WHERE id=?", (str(instance),)).fetchone()
    if row is None or str(row[0]) != day:
        return None     # the instance did not decide that day: there is no live decision to hash
    symbols = [str(s).strip().upper() for s in (needs or {}).get("symbols") or ()]
    shas = decision.get("shas") if isinstance(decision.get("shas"), Mapping) else {}
    start = str(decision.get("start") or "")
    if not symbols or not start:
        return None
    series: dict[str, dict[str, list[dict[str, Any]]]] = {name: {s: [] for s in symbols} for name in ("raw", "all")}
    for bar in guard.batched(db, "SELECT day, symbol, adjustment, o, h, l, c, v, sha FROM eq_bars WHERE day>=? AND "
                                 "day<=? AND symbol IN ({marks}) ORDER BY day", symbols, params=(start, day)):
        kept = (shas.get(bar["symbol"]) or {}).get(bar["adjustment"]) if isinstance(shas.get(bar["symbol"]), Mapping) \
            else None
        if bar["adjustment"] not in series or not kept or bar["sha"] != kept:
            return None     # a row another fetch wrote: the book no longer holds the series that decision read
        series[bar["adjustment"]][bar["symbol"]].append(
            {"t": bar["day"], **{k: None if bar[k] is None else float(bar[k]) for k in ("o", "h", "l", "c", "v")}})
    inputs = C.inputs_from_fetch(series["raw"], series["all"], day=day,
                                 needs=Needs(tuple(symbols), int((needs or {}).get("history") or 0),
                                             int((needs or {}).get("max_hold_sessions") or 1)),
                                 cash=0.0, equity=0.0, budget=0.0, caps={}, params={})
    return forward_db.bars_hash(inputs)


def live_bars(live_path: str | Path, instance: str, day: str, *, needs: Mapping[str, Any]) -> str | None:
    """`forward_db.bars_hash` of the bars the live decision of `day` read, from the book's `eq_bars` rows (raw and all,
    through `day`; `ctx.inputs_from_fetch` with the instance's NEEDS); None when the book does not hold them as that
    decision read them (a missing row, or the adjusted rows fetched again since: the book's `eq_decision` names
    another day)."""
    from . import guard

    try:
        return guard.read(live_path, lambda db: _book_bars(db, str(instance), _iso(day), needs))
    except Exception:  # noqa: BLE001 - not known: the row's cause then reads "unknown", never an error
        return None


def read_book(live_path: str | Path) -> dict[str, Any]:
    """The live book as the twins read it, in one read-only pass: {"instances": [`eq_instances` rows by id], "lots":
    {instance: [its `eq_lots` rows by lid]}, "intents": {instance: [its buy, sell and cancel rows by iid, each with
    its lot's symbol and day]}, "decision_day": the day of the book's `eq_decision`}. A book from before E1 (no
    `eq_instances`) is empty."""
    from . import guard

    def read(db: sqlite3.Connection) -> dict[str, Any]:
        tables = _tables(db)
        out: dict[str, Any] = {"instances": [], "lots": {}, "intents": {}, "decision_day": None}
        if "eq_instances" not in tables:
            return out
        out["instances"] = guard.rows(db, "SELECT id, family, version, lane, run_sha, band, last_decided_day, "
                                          "created_at, retired_at FROM eq_instances ORDER BY id")
        if "eq_lots" in tables:
            for lot in guard.rows(db, "SELECT lid, instance, symbol, entry_at, opened_day, status, exit_at, exit_day "
                                      "FROM eq_lots ORDER BY lid"):
                out["lots"].setdefault(str(lot["instance"]), []).append(lot)
            if "eq_intents" in tables:
                for row in guard.rows(db, _INTENTS_SQL.format(where="")):
                    out["intents"].setdefault(str(row["instance"]), []).append(row)
        if "kv" in tables:
            decision = _kv(db, "eq_decision")
            out["decision_day"] = str(decision.get("day")) if isinstance(decision, Mapping) and decision.get("day") \
                else None
        return out

    return guard.read(live_path, read)


def twin_records(root: str | Path) -> dict[str, dict[str, Any]]:
    """E1's equity twin records ({"eq:<lid>": record}: the swarm store's kv `equity_twins`, read-only); {} when the
    store or the key is absent."""
    from . import guard, twins

    path = Path(root) / SWARM_DB
    if not path.exists():
        return {}
    value = guard.read(path, lambda db: _kv(db, twins.EQUITY_TWINS_KEY) if "kv" in _tables(db) else None)
    return {str(k): dict(v) for k, v in value.items() if isinstance(v, Mapping)} if isinstance(value, Mapping) else {}


# ------------------------------------------------------------------------------------------ D10: the live-like series
def _livelike(run: ShadowRun, drift: Callable[[str, str, str], float | None], only: set[str] | None = None
              ) -> tuple[dict[str, float | None], dict[str, list[str]]]:
    """({day: r_ll | None}, {day: the symbols whose drift is missing}) over the run's sessions (those in `only` when
    given)."""
    from ..equity import config

    days = _days(run.series.days)
    wanted = [d for d in days if only is None or d in only]
    capital = float(Decimal(str(run.result.get("capital") or config.SLEEVE_USD)))
    if not (math.isfinite(capital) and capital > 0):
        raise ValueError("a run's capital is a positive number of dollars")
    terms: dict[str, list[float]] = {d: [] for d in wanted}
    missing: dict[str, list[str]] = {}

    def add(day: Any, symbol: str, at: Any, notional: float, sign: float) -> None:
        day = str(day)
        if day not in terms:
            return
        delta = drift(day, symbol, str(at or "open"))
        if delta is None or not math.isfinite(float(delta)) or not math.isfinite(notional):
            missing.setdefault(day, [])
            if symbol not in missing[day]:
                missing[day].append(symbol)
            return
        terms[day].append(sign * notional * float(delta) / 1e4)

    for lot in run.result.get("lots") or []:
        if not isinstance(lot, Mapping):
            continue
        symbol = str(lot.get("symbol") or "")
        add(lot.get("entry_day"), symbol, lot.get("entry_at"), float(lot.get("weight") or 0.0) * capital, -1.0)
        if lot.get("exit_day"):
            add(lot.get("exit_day"), symbol, lot.get("exit_at"),
                float(lot.get("qty") or 0.0) * float(lot.get("exit_px") or float("nan")), 1.0)
    r = {d: float(x) for d, x in zip(days, run.series.r)}
    return ({d: None if d in missing else (r[d] * capital + math.fsum(terms[d])) / capital for d in wanted}, missing)


def livelike_series(run: ShadowRun, drift: Callable[[str, str, str], float | None]) -> dict[str, float | None]:
    """{ISO day: r_ll} over the run's sessions (D10); `drift(day, symbol, at)` is the timing table's `drift_bp` (None:
    missing). A day with a needed drift missing is None."""
    return _livelike(run, drift)[0]


def _drift_of(db: sqlite3.Connection) -> Callable[[str, str, str], float | None]:
    """`drift(day, symbol, at)` from `fwd_fillgap`, one read a day."""
    cache: dict[str, dict[tuple[str, str], float]] = {}

    def drift(day: str, symbol: str, at: str) -> float | None:
        if day not in cache:
            cache[day] = {(str(r[0]), str(r[1])): float(r[2]) for r in db.execute(
                "SELECT symbol, at, drift_bp FROM fwd_fillgap WHERE day=?", (day,))}
        return cache[day].get((symbol, at))

    return drift


def begin(root: str | Path, db: sqlite3.Connection, shadow: Any, *, now: float) -> dict[str, Any]:
    """Before the night's runs: returns at once when `fill_minutes` is false; else the `fwd_fillgap` rows of every
    forward day that has a minutes file and none yet, every store symbol, both fill points (D10; `shadow.official`).
    {"days", "rows"} (counts)."""
    out = {"days": 0, "rows": 0}
    if not _on(_cfg(_settings(root, shadow)), "fill_minutes"):
        return out
    first, through = _iso(forward_db.t0()), _iso(shadow.through)
    symbols = sorted(str(s) for s in shadow.store.symbols())
    have = {str(r[0]): int(r[1]) for r in db.execute("SELECT day, COUNT(*) FROM fwd_fillgap GROUP BY day")}
    files = [d for d in fill_minutes.days_on_disk(root) if first <= d <= through]
    # A day with no row yet; and, among the last days the minutes job still backfills, one that lacks a row (the
    # store's official price may have come a night after the file).
    recent = set(files[-fill_minutes.BACKFILL_SESSIONS:])
    full = len(symbols) * len(fill_minutes.FILL_POINTS)
    for day in files:
        if have.get(day, 0) and not (day in recent and have[day] < full):
            continue
        doc = fill_minutes.read_day(root, day)
        if doc is None:
            continue
        rows = []
        for symbol in symbols:
            for at in fill_minutes.FILL_POINTS:
                official = _num(shadow.official(symbol, day, at))
                found = fill_minutes.livelike_of(doc, day, symbol, at)
                if official is None or official <= 0 or found is None:
                    continue
                price, field = found
                rows.append((day, symbol, at, official, price, (price / official - 1.0) * 1e4,
                             fill_minutes.bar_start(day, at).strftime(fill_minutes.STAMP), field))
        with db:
            before = db.total_changes
            db.executemany("INSERT OR IGNORE INTO fwd_fillgap(day, symbol, at, official, livelike, drift_bp, bar, "
                           "field) VALUES(?,?,?,?,?,?,?,?)", rows)
            written = db.total_changes - before
        if written:
            out["days"] += 1
            out["rows"] += written
    return out


def _engine_of(db: sqlite3.Connection, pid: int, days: Sequence[str]) -> int | None:
    """The engine id a run's re-price belongs to: the one the shadow wrote the run's last day under (the newest
    `fwd_days` row of that pid and day: the night writes a program's days, then calls `on_run`); with no such row,
    the newest engine id (`forward_db.engine_now`). The two differ only when an engine label has COME BACK (a
    rollback restores a label that already has its id while a newer id exists): the re-price then stays with the
    series it re-prices, never under an id that run was not written under."""
    if days:
        row = db.execute("SELECT engine FROM fwd_days WHERE pid=? AND day=? ORDER BY at DESC, engine DESC LIMIT 1",
                         (int(pid), str(days[-1]))).fetchone()
        if row is not None and row[0] is not None:
            return int(row[0])
    return forward_db.engine_now(db)


def on_run(db: sqlite3.Connection, run: ShadowRun, *, now: float, settings: Mapping[str, Any] | None) -> int:
    """After a program's write: 0 at once when `fill_minutes` is false; else the `fwd_ll` rows of the run's days that
    have none under the run's engine id (D10; `_engine_of`; a `no_minute` event once a (pid, day)); how many were
    written."""
    if not _on(_cfg(settings), "fill_minutes"):
        return 0
    pid = int(run.program.pid)
    days = _days(run.series.days)
    engine = _engine_of(db, pid, days)
    if engine is None:
        return 0
    have = {str(r[0]) for r in db.execute("SELECT day FROM fwd_ll WHERE pid=? AND engine=?", (pid, int(engine)))}
    todo = {d for d in days if d not in have}
    if not todo:
        return 0
    series, missing = _livelike(run, _drift_of(db), todo)
    rows = [(pid, day, int(engine), float(value), float(now)) for day, value in sorted(series.items())
            if value is not None and math.isfinite(value)]
    with db:
        before = db.total_changes
        db.executemany("INSERT OR IGNORE INTO fwd_ll(pid, day, engine, r_ll, at) VALUES(?,?,?,?,?)", rows)
        written = db.total_changes - before
        for day in sorted(missing):
            forward_db.event(db, "no_minute", pid=pid, day=day, at=float(now), once="minute",
                             payload={"why": "no send-minute price for a fill of that day: no live-like row yet",
                                      "symbols": sorted(missing[day])})
    return written


# ------------------------------------------------------------------------------------------------ D11: the fill gap
def lot_gap(lot: Mapping[str, Any], twin: Mapping[str, Any], livelike_entry: float | None,
            livelike_exit: float | None) -> dict[str, Any]:
    """D11's parts of one closed live lot (its `eq_lots` row, its priced E1 twin record, the two live-like prices):
    the `fwd_lotgap` columns `model_bp`, `entry_slip_bp`, `exit_slip_bp`, `timing_entry_bp`, `timing_exit_bp`,
    `exec_entry_bp`, `exec_exit_bp`, `side_gap_bp`, `twin_gap_bp`. Timing + execution = slip; timing and execution
    None when that side's live-like price is None."""
    from ..equity import config

    k, hs_bp = _num(twin.get("k")), _num(twin.get("hs_bp"))
    if hs_bp is None:
        try:
            hs_bp = config.half_spread(str(lot.get("symbol") or twin.get("symbol") or "")) * 1e4
        except KeyError:
            raise ValueError("the twin names no half-spread and its symbol is outside the universe") from None
    model = (config.K_BASE if k is None else k) * hs_bp
    entry_slip, exit_slip = _num(twin.get("entry_slip_bp")), _num(twin.get("exit_slip_bp"))
    entry_official, exit_official = _num(twin.get("entry_official")), _num(twin.get("exit_official"))
    out: dict[str, Any] = {"model_bp": round(model, 4), "entry_slip_bp": entry_slip, "exit_slip_bp": exit_slip,
                           "timing_entry_bp": None, "timing_exit_bp": None, "exec_entry_bp": None,
                           "exec_exit_bp": None, "side_gap_bp": None, "twin_gap_bp": _num(twin.get("gap_bp"))}
    ll_e, ll_x = _num(livelike_entry), _num(livelike_exit)
    if ll_e is not None and entry_official is not None and entry_official > 0:
        out["timing_entry_bp"] = round((ll_e / entry_official - 1.0) * 1e4, 4)
        if entry_slip is not None:
            out["exec_entry_bp"] = round(entry_slip - out["timing_entry_bp"], 4)
    if ll_x is not None and exit_official is not None and exit_official > 0:
        out["timing_exit_bp"] = round((1.0 - ll_x / exit_official) * 1e4, 4)
        if exit_slip is not None:
            out["exec_exit_bp"] = round(exit_slip - out["timing_exit_bp"], 4)
    if entry_slip is not None and exit_slip is not None:
        out["side_gap_bp"] = round(((entry_slip - model) + (exit_slip - model)) / 2.0, 4)
    return out


def _lot_gaps(root: Path, db: sqlite3.Connection, book: Mapping[str, Any], through: dt.date, now: float, *,
              fill: bool, pid_of: Callable[[str], int | None]) -> tuple[int, int]:
    """(rows written, lots whose row could not be made) over every closed live lot with a final priced E1 twin and no
    `fwd_lotgap` row."""
    from . import twins

    records = twin_records(root)
    done = {int(r[0]) for r in db.execute("SELECT lid FROM fwd_lotgap")}
    first = _iso(forward_db.t0())
    recent = (_sessions(through - dt.timedelta(days=fill_minutes.LOOKBACK_DAYS), through)
              [-fill_minutes.BACKFILL_SESSIONS:] or [through.isoformat()])[0]
    docs: dict[str, Any] = {}

    def doc_of(day: str) -> Any:
        if day not in docs:
            docs[day] = fill_minutes.read_day(root, day)
        return docs[day]

    rows, failed = [], 0
    for instance, lots in sorted(book.get("lots", {}).items()):
        for lot in lots:
            if str(lot.get("status")) != "closed" or int(lot["lid"]) in done:
                continue
            rec = records.get(twins.equity_key(lot["lid"]))
            if not rec or rec.get("final") is not True or rec.get("status") != "priced":
                continue
            try:
                symbol = str(lot.get("symbol") or rec.get("symbol") or "")
                opened, left = _iso(rec.get("opened_day") or lot.get("opened_day")), \
                    _iso(rec.get("exit_day") or lot.get("exit_day"))
                entry_at, exit_at = str(rec.get("entry_at") or lot.get("entry_at")), \
                    str(rec.get("exit_at") or lot.get("exit_at"))
                prices: list[float | None] = [None, None]
                if fill:
                    points = ((opened, entry_at), (left, exit_at))
                    if any(doc_of(day) is None and day >= max(first, recent) for day, _ in points):
                        continue    # the minutes job may still fetch that day: the row waits (it is written once)
                    for i, (day, at) in enumerate(points):
                        found = fill_minutes.livelike_of(doc_of(day), day, symbol, at) if doc_of(day) else None
                        prices[i] = None if found is None else found[0]
                gap = lot_gap(lot, rec, prices[0], prices[1])
            except (KeyError, TypeError, ValueError):
                failed += 1
                continue
            rows.append((int(lot["lid"]), str(instance), pid_of(str(instance)), symbol, opened, left, entry_at, exit_at,
                         gap["model_bp"], gap["entry_slip_bp"], gap["exit_slip_bp"], gap["timing_entry_bp"],
                         gap["timing_exit_bp"], gap["exec_entry_bp"], gap["exec_exit_bp"], gap["side_gap_bp"],
                         gap["twin_gap_bp"], float(now)))
    with db:
        before = db.total_changes
        db.executemany("INSERT OR IGNORE INTO fwd_lotgap(lid, instance, pid, symbol, opened_day, exit_day, entry_at, "
                       "exit_at, model_bp, entry_slip_bp, exit_slip_bp, timing_entry_bp, timing_exit_bp, "
                       "exec_entry_bp, exec_exit_bp, side_gap_bp, twin_gap_bp, at) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        return db.total_changes - before, failed


# ---------------------------------------------------------------------------------------------------- the night's end
def registry_key(instance: str) -> str:
    """A live instance's registry key: its id less ":r"."""
    instance = str(instance)
    return instance[:-len(REAL_SUFFIX)] if instance.endswith(REAL_SUFFIX) else instance


def _last_needed(lots: Sequence[Mapping[str, Any]], retired: dt.date) -> dt.date | None:
    """The last session a retired instance needs a `fwd_twins` row for: the session before its retirement, or the one
    before its last lot closed when that is later (D13 reads through it). None while a lot is still open."""
    from ..equity import schedule

    last = schedule.previous_session(retired)
    for lot in lots:
        if str(lot.get("status")) != "closed" or not lot.get("exit_day"):
            return None
        last = max(last, schedule.previous_session(_date(lot["exit_day"])))
    return last


def _one_instance(root: Path, db: sqlite3.Connection, shadow: Any, inst: Mapping[str, Any], book: Mapping[str, Any],
                  hashes: dict[tuple[str, str], str], out: dict[str, Any], *, now: float) -> None:
    from ..equity import schedule

    iid = str(inst["id"])
    program = forward_db.program(db, registry_key(iid))
    if program is None:
        forward_db.event(db, "twin_unregistered", at=float(now), once=iid, payload={
            "instance": iid, "why": "the live instance's key is not in the forward registry: no twin"})
        out["unregistered"] += 1
        return
    pid = int(program.pid)
    if str(program.run_sha) != str(inst.get("run_sha")):
        forward_db.event(db, "twin_sha_mismatch", pid=pid, at=float(now), once=iid, payload={
            "instance": iid, "why": "the registry's run sha is not the live instance's: no twin"})
        out["mismatched"] += 1
        return
    through = _date(shadow.through)
    night = through.isoformat()
    needs = [str(s) for s in (program.needs or {}).get("symbols") or ()]
    lots = book["lots"].get(iid, [])
    # THE LIVE DECISION'S BARS, taken while the book still holds them as that decision read them.
    decided = str(inst.get("last_decided_day") or "")
    if decided and decided == book.get("decision_day") and (iid, decided) not in hashes:
        found = live_bars(root / LIVE_DB, iid, decided, needs=program.needs)
        if found:
            hashes[(iid, decided)] = found
            if forward_db.event(db, "live_bars", pid=pid, day=decided, at=float(now), once=iid, payload={
                    "instance": iid, "bars": found, "why": "the bars hash of the live decision, taken that night"}):
                out["live_bars"] += 1
    first, retired = d_first(inst), d_retired(inst)
    end = schedule.previous_session(through)
    if retired is not None:
        stop = _last_needed(lots, retired)
        end = end if stop is None else min(end, stop)
    wanted = _sessions(first, end)
    have = {str(r[0]) for r in db.execute("SELECT day FROM fwd_twins WHERE instance=?", (iid,))}
    parted = db.execute("SELECT 1 FROM fwd_part WHERE instance=? AND through=?", (iid, night)).fetchone() is not None
    if not wanted or (all(day in have for day in wanted) and (parted or retired is not None)):
        return      # nothing to write yet, or everything this instance will ever need is written
    start = schedule.next_session(first)
    try:
        try:
            run = shadow.run_from(program, start)
        except Exception as exc:  # noqa: BLE001 - the child's failure is an interruption; the data's is the caller's
            if not any(base.__name__ in RUN_FAILURES for base in type(exc).__mro__):
                raise
            raise TwinInterrupted(f"the decider child failed the twin's run ({type(exc).__name__})") from None
        if run is None:
            return
        decisions = _twin(getattr(shadow, "decider", None), run)
    except TwinInterrupted as exc:
        forward_db.event(db, "twin_interrupted", pid=pid, day=night, at=float(now), once=iid, payload={
            "instance": iid, "why": str(exc)[:240]})
        out["interrupted"] += 1
        return
    live = _live_keys(book["intents"].get(iid, []), needs)
    unreadable = split_sessions(run)
    rows, kept = [], set(wanted)
    for day, keys, bars in decisions:
        if day not in kept or day in have:
            continue
        mine = live.get(day, [])
        if retired is not None and day >= retired.isoformat():
            agreed, why = None, "retired"
        elif day in unreadable:
            agreed, why = None, "split"
        else:
            agreed, why = agree(mine, keys), None
        seen = hashes.get((iid, day))
        rows.append((iid, day, pid, json.dumps(mine), json.dumps(keys), None if agreed is None else int(agreed), why,
                     float(now), seen, bars, cause(agreed, seen, bars)))
    last = min(through, retired) if retired is not None else through
    part = participation(
        [lot for lot in lots if start.isoformat() <= str(lot.get("opened_day") or "") <= last.isoformat()],
        [lot for lot in (run.result.get("lots") or []) if isinstance(lot, Mapping)
         and start.isoformat() <= str(lot.get("entry_day") or "") <= last.isoformat()])
    with db:    # one transaction an instance: its sessions in day order from d_first, and the night's participation
        db.executemany("INSERT OR IGNORE INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, "
                       "live_bars, shadow_bars, cause) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
        db.execute("INSERT OR IGNORE INTO fwd_part(instance, through, pid, matched, missed, extra, at) "
                   "VALUES(?,?,?,?,?,?,?)",
                   (iid, night, pid, part["matched"], part["missed"], part["extra"], float(now)))
    out["twins"] += len(rows)
    out["disagreed"] += sum(1 for row in rows if row[5] == 0)
    out["unreadable"] += sum(1 for row in rows if row[5] is None)


def finish(root: str | Path, db: sqlite3.Connection, shadow: Any, *, now: float) -> dict[str, Any]:
    """After the night's runs: skipped when `twins` is false or the live book is absent. For every `eq_instances` row:
    the `live_bars` event of its latest decision while the book still holds that decision's bars (once an (instance,
    day)); the twin run (`shadow.run_from`), its `fwd_twins` rows (D12, each with its two bars hashes and, when the
    sides disagree, its cause), one `fwd_part` row for `through`. For every closed live lot with a final priced E1
    twin and no `fwd_lotgap` row: its row (D11; timing and execution None when `fill_minutes` is false).
    {"instances", "twins", "disagreed", "lots", "interrupted", "live_bars"} (counts), with `FINISH_KEYS`' others
    beside ("unreadable", "unregistered", "mismatched", "failed") and, when an instance's twin could not be made,
    "errors" (ids and class names). It reads `shadow.through`, `shadow.run_from`, and the night's `decider` and
    `settings` as the shadow holds them; one instance's failure never costs another its rows."""
    root = Path(root)
    out: dict[str, Any] = {key: 0 for key in FINISH_KEYS}
    cfg = _cfg(_settings(root, shadow))
    if not _on(cfg, "twins"):
        return {**out, "skipped": "elane.forward.twins is false, or the forward mode is off"}
    if not (root / LIVE_DB).exists():
        return {**out, "skipped": "no live book"}
    book = read_book(root / LIVE_DB)
    hashes = {(str(e["payload"].get("instance")), str(e["day"])): str(e["payload"].get("bars"))
              for e in forward_db.events(db, "live_bars") if isinstance(e.get("payload"), Mapping)
              and e["payload"].get("bars")}
    errors: list[str] = []
    for inst in book["instances"]:
        out["instances"] += 1
        try:
            _one_instance(root, db, shadow, inst, book, hashes, out, now=now)
        except Exception as exc:  # noqa: BLE001 - one instance's twin never costs the others theirs, or the lots
            out["failed"] += 1
            errors.append(f"{str(inst.get('id'))[:60]}: {type(exc).__name__}")
    pids: dict[str, int | None] = {}

    def pid_of(instance: str) -> int | None:
        if instance not in pids:
            program = forward_db.program(db, registry_key(instance))
            pids[instance] = None if program is None else int(program.pid)
        return pids[instance]

    try:
        out["lots"], unmade = _lot_gaps(root, db, book, _date(shadow.through), float(now),
                                        fill=_on(cfg, "fill_minutes"), pid_of=pid_of)
        out["failed"] += unmade
    except Exception as exc:  # noqa: BLE001 - the lots' rows are made again the next night; the twins' rows stand
        out["failed"] += 1
        errors.append(f"lots: {type(exc).__name__}")
    if errors:
        out["errors"] = errors[:10]
    return out


# ------------------------------------------------------------------------------------------------ D13: the A14 reading
def _blank(*, applies: bool, holds: bool, final: bool, why: str | None) -> dict[str, Any]:
    return {"applies": applies, "holds": holds, "final": final, "why": why,
            "gap": {"closes": 0, "priced": 0, "unpriced": 0, "pending": 0, "mean_gap_bp": None,
                    "bound_bp": forward_db.A14_GAP_BP, "ok": None},
            "intents": {"instances": 0, "sessions": 0, "agreed": 0, "missing": 0, "unreadable": 0, "share": None,
                        "bound": forward_db.A14_AGREE, "ok": None, "disagreed": 0,
                        "causes": {name: 0 for name in forward_db.CAUSES}},
            "by_instance": []}


def _twin_rows(root: Path, instances: Sequence[str]) -> tuple[dict[str, dict[str, dict[str, Any]]], bool]:
    """({instance: {day: its `fwd_twins` row}}, whether the forward store was read) for the instances named."""
    from . import guard

    try:
        db = forward_db.open_db(root, readonly=True)
    except Exception:  # noqa: BLE001 - no forward store, or one that cannot be opened: unmeasured
        return {}, False
    try:
        rows = guard.batched(db, "SELECT instance, day, agree, why, cause FROM fwd_twins WHERE instance IN ({marks})",
                             list(instances))
    except Exception:  # noqa: BLE001 - a store that cannot be read is unmeasured, never an error of the Done meter
        return {}, False
    finally:
        db.close()
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row["instance"]), {})[str(row["day"])] = row
    return out, True


def a14_reading(root: str | Path, counted: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """THE A14 READING (D13, the module docstring) of a checkpoint's counted closes (`dlane_report.equity_closes`-shaped
    rows: it reads `equity`, `pid`, `instance`, `day`). ALWAYS a dict holding every key of `A14_KEYS`, with "gap":
    {`A14_GAP_KEYS`}, "intents": {`A14_INTENT_KEYS`} and "by_instance": [{`A14_INSTANCE_KEYS`}], on every branch (a
    missing store included). It opens the forward store and the swarm store read-only and NEVER RAISES for a missing
    store (unmeasured: holds False, final False)."""
    from ..equity import schedule

    closes = [c for c in counted or () if isinstance(c, Mapping) and c.get("equity")]
    if not closes:
        return _blank(applies=False, holds=True, final=True, why=None)
    out = _blank(applies=True, holds=False, final=False, why=None)
    root = Path(root)
    whys: list[str] = []
    # THE GAP: the mean of E1's twin gap over the closes whose twin is final and priced.
    gap = out["gap"]
    gap["closes"] = len(closes)
    try:
        records = twin_records(root)
    except Exception:  # noqa: BLE001 - a swarm store that cannot be read: every twin is pending
        records = {}
    gaps = []
    for close in closes:
        rec = records.get(str(close.get("pid") or ""))
        if not isinstance(rec, Mapping) or rec.get("final") is not True:
            gap["pending"] += 1
        elif rec.get("status") == "priced" and _num(rec.get("gap_bp")) is not None:
            gaps.append(_num(rec.get("gap_bp")))
        else:
            gap["unpriced"] += 1
    gap["priced"] = len(gaps)
    if gaps:
        gap["mean_gap_bp"] = round(math.fsum(gaps) / len(gaps), 4)
        gap["ok"] = abs(math.fsum(gaps) / len(gaps)) <= forward_db.A14_GAP_BP
        if not gap["ok"]:
            whys.append(f"the mean fill gap of {len(gaps)} priced closes is beyond the bound a side")
    else:
        whys.append(f"none of the {len(closes)} equity closes has a priced twin yet")
    # THE INTENTS: each instance's sessions from its first twin row through the session before its last counted exit.
    intents = out["intents"]
    by_instance: dict[str, list[Mapping[str, Any]]] = {}
    for close in closes:
        by_instance.setdefault(str(close.get("instance") or ""), []).append(close)
    rows, read = _twin_rows(root, sorted(by_instance))
    intents["instances"] = len(by_instance)
    for instance in sorted(by_instance):
        mine = {"instance": instance, "sessions": 0, "agreed": 0, "missing": 0, "unreadable": 0}
        out["by_instance"].append(mine)
        try:
            last = schedule.previous_session(max(_date(c.get("day")) for c in by_instance[instance]))
            found = sorted(day for day in rows.get(instance, {}) if day <= last.isoformat())
            if found:
                first = _date(found[0])
            else:   # no row yet: every session from the one before its first counted lot's entry is missing
                first = schedule.previous_session(min(_date(c.get("opened_day") or c.get("day"))
                                                      for c in by_instance[instance]))
            days = _sessions(first, last)
        except (TypeError, ValueError):
            mine["missing"] += 1    # its days cannot be read: unmeasured, never held
            mine["sessions"] += 1
            continue
        for day in days:
            row = rows.get(instance, {}).get(day)
            if row is None:
                mine["missing"] += 1
            elif row["agree"] is None:
                mine["unreadable"] += 1
                continue
            elif int(row["agree"]) == 1:
                mine["agreed"] += 1
            else:
                intents["disagreed"] += 1
                name = row["cause"] if row["cause"] in forward_db.CAUSES else "unknown"
                intents["causes"][name] += 1
            mine["sessions"] += 1
    for key in ("sessions", "agreed", "missing", "unreadable"):
        intents[key] = sum(row[key] for row in out["by_instance"])
    if intents["sessions"]:
        intents["share"] = round(intents["agreed"] / intents["sessions"], 6)
        intents["ok"] = intents["agreed"] >= forward_db.A14_AGREE * intents["sessions"] - 1e-9
        if not intents["ok"]:
            whys.append(f"the live and the shadow intents agree on {intents['agreed']} of {intents['sessions']} "
                        "counted sessions, under the bound")
    else:
        whys.append("no counted session has a twin to read")
    if intents["missing"]:
        whys.append(f"{intents['missing']} counted sessions have no twin row yet" if read else
                    "the forward record cannot be read: the twins are unmeasured")
    if gap["pending"]:
        whys.append(f"{gap['pending']} equity closes have no final twin yet")
    out["holds"] = gap["ok"] is True and intents["ok"] is True
    out["final"] = gap["pending"] == 0 and intents["missing"] == 0
    out["why"] = "; ".join(whys) or None
    return out


__all__ = ["UNREADABLE", "A14_KEYS", "A14_GAP_KEYS", "A14_INTENT_KEYS", "A14_INSTANCE_KEYS", "LIVE_DB", "SWARM_DB",
           "FINISH_KEYS", "TwinInterrupted", "begin", "on_run", "finish", "livelike_series", "lot_gap", "d_first",
           "d_retired", "keys_of", "shadow_intents", "shadow_bars", "live_bars", "cause", "split_sessions",
           "live_intents", "agree", "participation", "registry_key", "read_book", "twin_records", "a14_reading"]
