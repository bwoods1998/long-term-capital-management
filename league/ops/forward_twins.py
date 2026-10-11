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
(once a (pid, day)).

THE FILL GAP OF A CLOSED LIVE LOT (D11): its `eq_lots` row; its E1 twin record `equity_twins["eq:<lid>"]` (the swarm
store's kv, league/ops/twins.py), status "priced". `model_bp = twin["k"] * twin["hs_bp"]`. Cost-positive. Entry:
`entry_slip_bp` = the twin's; timing_entry_bp = (livelike(opened_day, sym, entry_at) / entry_official - 1) * 1e4;
exec_entry_bp = entry_slip_bp - timing_entry_bp. Exit: `exit_slip_bp` = the twin's; timing_exit_bp = (1 -
livelike(exit_day, sym, exit_at) / exit_official) * 1e4; exec_exit_bp = exit_slip_bp - timing_exit_bp. side_gap_bp =
((entry_slip_bp - model_bp) + (exit_slip_bp - model_bp)) / 2 (how much worse than the model, a side). `twin_gap_bp` =
the twin's `gap_bp` (about -side_gap_bp). Timing and execution are None when a minute is missing. PARTICIPATION of a
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
final). UNREADABLE sessions get a row with `agree` NULL and its `why`, and are left out of every share: "split" when
a lot the twin holds at d has a "split" row in the twin run's `actions` for its symbol on a later day of its hold
(`split_sessions`). A twin run whose decides were interrupted writes no row that night and is tried again the next.
A registry `run_sha` that differs from the instance's is a `twin_sha_mismatch` event and no twin; no registry row is
`twin_unregistered` (each once an instance).

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

Standard library and numpy only.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .forward_db import ShadowRun

#: `fwd_twins.why` of an unreadable session (D12).
UNREADABLE = ("split",)
#: Every key `a14_reading` returns, on every branch (a missing store included).
A14_KEYS = ("applies", "holds", "final", "why", "gap", "intents", "by_instance")
A14_GAP_KEYS = ("closes", "priced", "unpriced", "pending", "mean_gap_bp", "bound_bp", "ok")
#: `disagreed` and `causes` ({cause: sessions}, `forward_db.CAUSES`) are counted beside the share, never in its rule.
A14_INTENT_KEYS = ("instances", "sessions", "agreed", "missing", "unreadable", "share", "bound", "ok", "disagreed",
                   "causes")
A14_INSTANCE_KEYS = ("instance", "sessions", "agreed", "missing", "unreadable")


class TwinInterrupted(RuntimeError):
    """A twin run's decides were interrupted (the child restarted, or an answer's `stats.calls` is not the sessions
    asked so far): the House's. One `twin_interrupted` event, no row for that instance that night."""


def begin(root: str | Path, db: sqlite3.Connection, shadow: Any, *, now: float) -> dict[str, Any]:
    """Before the night's runs: returns at once when `fill_minutes` is false; else the `fwd_fillgap` rows of every
    forward day that has a minutes file and none yet, every store symbol, both fill points (D10; `shadow.official`).
    {"days", "rows"} (counts)."""
    raise NotImplementedError("D: league/ops/forward_twins.py begin")


def on_run(db: sqlite3.Connection, run: ShadowRun, *, now: float, settings: Mapping[str, Any] | None) -> int:
    """After a program's write: 0 at once when `fill_minutes` is false; else the `fwd_ll` rows of the run's days that
    have none (D10; a `no_minute` event once a (pid, day)); how many were written."""
    raise NotImplementedError("D: league/ops/forward_twins.py on_run")


def finish(root: str | Path, db: sqlite3.Connection, shadow: Any, *, now: float) -> dict[str, Any]:
    """After the night's runs: skipped when `twins` is false or the live book is absent. For every `eq_instances` row:
    the `live_bars` event of its latest decision while the book still holds that decision's bars (once an (instance,
    day)); the twin run (`shadow.run_from`), its `fwd_twins` rows (D12, each with its two bars hashes and, when the
    sides disagree, its cause), one `fwd_part` row for `through`. For every closed live lot with a final priced E1
    twin and no `fwd_lotgap` row: its row (D11; timing and execution None when `fill_minutes` is false).
    {"instances", "twins", "disagreed", "lots", "interrupted", "live_bars"} (counts)."""
    raise NotImplementedError("D: league/ops/forward_twins.py finish")


def livelike_series(run: ShadowRun, drift: Callable[[str, str, str], float | None]) -> dict[str, float | None]:
    """{ISO day: r_ll} over the run's sessions (D10); `drift(day, symbol, at)` is the timing table's `drift_bp` (None:
    missing). A day with a needed drift missing is None."""
    raise NotImplementedError("D: league/ops/forward_twins.py livelike_series")


def lot_gap(lot: Mapping[str, Any], twin: Mapping[str, Any], livelike_entry: float | None,
            livelike_exit: float | None) -> dict[str, Any]:
    """D11's parts of one closed live lot (its `eq_lots` row, its priced E1 twin record, the two live-like prices):
    the `fwd_lotgap` columns `model_bp`, `entry_slip_bp`, `exit_slip_bp`, `timing_entry_bp`, `timing_exit_bp`,
    `exec_entry_bp`, `exec_exit_bp`, `side_gap_bp`, `twin_gap_bp`. Timing + execution = slip; timing and execution
    None when that side's live-like price is None."""
    raise NotImplementedError("D: league/ops/forward_twins.py lot_gap")


def d_first(instance_row: Mapping[str, Any]) -> dt.date:
    """D12: the latest session d with `schedule.moments(d).bars_at <= created_at` of an `eq_instances` row (16:25 ET
    and 08:00 the next morning name the same session)."""
    raise NotImplementedError("D: league/ops/forward_twins.py d_first")


def keys_of(intents: Sequence[Any], *, needs: Sequence[str], held: Mapping[Any, Mapping[str, Any]]) -> list[str]:
    """D12's ONE rule, used for both sides: the keys of one session's intents as a program gives them ({"buy": SYM,
    "at"} | {"sell": <lot id>, "at"} | {"cancel": ...}; the live side's `eq_intents` rows are read into that shape
    first). `needs`: the program's NEEDS symbols; `held`: {lot id: {"symbol", "entry_day"}} that side holds at the
    decision. A list (duplicates kept: the comparison is a multiset's)."""
    raise NotImplementedError("D: league/ops/forward_twins.py keys_of")


def shadow_intents(decider: Any, run: ShadowRun) -> dict[str, list[str]]:
    """{decision day: keys} of a twin run: `decider.kind_load("equity", key, {"code", "params", "name", "timeout":
    1.0, "max_errors": 25})`, one "decide" a session on `elane_train.state_inputs(run)`'s inputs, `kind_drop` in
    `finally`. NEVER A SILENT RELOAD, as E2's restart check: after every decide `decider.restarts` is unchanged and
    the answer's `stats.calls` == the sessions asked so far, else `TwinInterrupted`."""
    raise NotImplementedError("D: league/ops/forward_twins.py shadow_intents")


def shadow_bars(run: ShadowRun) -> dict[str, str]:
    """{decision day: `forward_db.bars_hash`} of a twin run's decisions (`elane_train.state_inputs(run)`'s inputs; the
    parent's arithmetic, no child)."""
    raise NotImplementedError("D: league/ops/forward_twins.py shadow_bars")


def live_bars(live_path: str | Path, instance: str, day: str, *, needs: Mapping[str, Any]) -> str | None:
    """`forward_db.bars_hash` of the bars the live decision of `day` read, from the book's `eq_bars` rows (raw and all,
    through `day`; `ctx.inputs_from_fetch` with the instance's NEEDS); None when the book does not hold them as that
    decision read them (a missing row, or the adjusted rows fetched again since: the book's `eq_decision` names
    another day)."""
    raise NotImplementedError("D: league/ops/forward_twins.py live_bars")


def cause(agreed: bool | None, live: str | None, shadow: str | None) -> str | None:
    """`fwd_twins.cause` (`forward_db.CAUSES`): None unless `agreed` is False; then "unknown" when `live` or `shadow`
    is None, "bars" when they differ, "program" when they are equal."""
    raise NotImplementedError("D: league/ops/forward_twins.py cause")


def split_sessions(run: ShadowRun) -> set[str]:
    """D12's unreadable sessions of a twin run: the decision days d at which a lot the twin holds has a "split" row in
    the run's `actions` for its symbol on a later day of its hold."""
    raise NotImplementedError("D: league/ops/forward_twins.py split_sessions")


def live_intents(live_path: str | Path, instance: str, *, needs: Sequence[str]) -> dict[str, list[str]]:
    """{decided day: keys} of a live instance from the book's `eq_intents` rows (read-only; D12's live rule)."""
    raise NotImplementedError("D: league/ops/forward_twins.py live_intents")


def agree(live: Sequence[str], shadow: Sequence[str]) -> bool:
    """`Counter(live) == Counter(shadow)`: two empty sessions agree."""
    raise NotImplementedError("D: league/ops/forward_twins.py agree")


def participation(live_lots: Sequence[Mapping[str, Any]], twin_lots: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """D11's participation: {"matched", "missed", "extra", "rate"} over lots keyed (symbol, entry day, entry_at);
    `rate` None with no lot on either side."""
    raise NotImplementedError("D: league/ops/forward_twins.py participation")


def a14_reading(root: str | Path, counted: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """THE A14 READING (D13, the module docstring) of a checkpoint's counted closes (`dlane_report.equity_closes`-shaped
    rows: it reads `equity`, `pid`, `instance`, `day`). ALWAYS a dict holding every key of `A14_KEYS`, with "gap":
    {`A14_GAP_KEYS`}, "intents": {`A14_INTENT_KEYS`} and "by_instance": [{`A14_INSTANCE_KEYS`}], on every branch (a
    missing store included). It opens the forward store and the swarm store read-only and NEVER RAISES for a missing
    store (unmeasured: holds False, final False)."""
    raise NotImplementedError("D: league/ops/forward_twins.py a14_reading")


__all__ = ["UNREADABLE", "A14_KEYS", "A14_GAP_KEYS", "A14_INTENT_KEYS", "A14_INSTANCE_KEYS", "TwinInterrupted", "begin",
           "on_run", "finish", "livelike_series", "lot_gap", "d_first", "keys_of", "shadow_intents", "shadow_bars",
           "live_bars", "cause", "split_sessions", "live_intents", "agree", "participation", "a14_reading"]
