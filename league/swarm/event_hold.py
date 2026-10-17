"""THE EVENT HOLD (the captain's A25 R1, adopted 13:42Z Oct 11, 2026; built in release 1023a during the checkpoint-15
freeze, to be deployed only once checkpoint 15 is final).

THE RULE, AS ADOPTED: "a program that reads fomc, cpi or jobs takes no Validation, no look and no seat until the tables
cover its windows (the captain keeps the hold at Validation rather than refusing the code: an event idea may still be
researched on Train; cents of model dollars, stated)". R1 moves no id.

WHY. `ctx.events` and `ctx.events_next` read three flags from static tables (league/gym/events.py `FOMC`, `CPI`,
`JOBS`), and `flags_for` is plain set membership: past a table's last row its flag reads False on every session, in
the Gym and live alike (cpi after 2026-09-11, jobs after 2026-09-04, fomc after 2026-12-09, as this release finds
them). A program that conditions on cpi or jobs was judged on Train and Validation with the flag set on its release
days, and live it would trade a different rule: the flag never fires. Nothing caught it: the replay intent match reads
the same blank table. The edge hunt (Oct 16, 2026, K3) found the hold adopted and never built; no alive program read
cpi or jobs that day, in either lane, and five equity readers had been born in about nine hours. The release's review
(a read-only census at about 05:30Z Oct 17) found 12 alive cpi or jobs readers, all in Train: births, Train,
Validation and looks go on until the deploy, so a reader can reach a seat BEFORE the hold ships, and the hold then
holds it AT its seat (opens stop, exits go on; the EquityBook keeps its seat held, league/equity/live.py
`_held_seats`). The deploy waits on a counts-only census of event readers by lane and band (docs/operations.md,
Release 1023a). The tables are an
identity file (the equity identity, the options execution fingerprint and the Gym bundle), so they are extended only
by a calendar release (A25 R2), never here.

WHAT "READS" MEANS (`reads`): read from the program's own source, statically and conservatively (never run). A flag is
read when the program subscripts `events` or `events_next` with it (`ctx.events["cpi"]`), asks `.get("cpi")` of
either, or tests `"cpi" in` either, through any name bound to either (`ev = ctx.events`) or `getattr(ctx,
"events")`, or THE GUARD `ctx.events or {}` (or `dict()`, `None`: the same dict or an empty one). Its TRUTH ALONE reads
no flag (`if ctx.events:`, `not`, `bool()`, an `and` operand that is not the last: the dict always holds every flag;
the review's finding 5). ANY OTHER USE READS EVERY FLAG: the dict walked or copied (`.items()`, `.values()`, `any(...)`,
`dict(...)`), handed to a function or returned, subscripted by a name, `getattr` with a name that is no constant,
`vars(...)`, `__dict__` or `__getattribute__`. Source that does not parse reads every flag (fail closed). The calendar
sentence tells authors so (`CALENDAR`). A program that only ever names
`monthly_opex`, `quarter_end` or `half_day` reads none of the three: those come from the calendar and hold everywhere.

WHAT "COVERS ITS WINDOWS" MEANS (`hold`): a program's windows are its Validation, its sealed look and its seat. The
last of them is live trading, which runs from today on, so the tables cover a program's windows only while every
held flag it reads has its table's last row on or after today (the House's UTC date). A flag whose table ends before
today holds it: cpi and jobs now, and fomc from 2026-12-10, until a calendar release adds rows; then the hold lifts by
itself (the rule reads the tables, never a list of its own). Mechanical: no setting, no captain's choice of who.

WHERE IT HOLDS (each before anything is spent, recorded or paid; nothing is retired, refused or sold on it):
- an equity Validation: league/swarm/elane.py `validate` answers it refused before any run (no try is recorded, so
  the lineage keeps its one try);
- an equity look: league/swarm/elane.py `look` waits before the sealed run (no look spent, no refusal row, no bad
  gate outcome), as R-SEC's forward-only hold does;
- an options Validation: league/swarm/tournament.py `Tournament.validate` queues no job and judges no recorded or
  inherited result for it (`event_held` in its answer);
- an options look: league/swarm/gate.py `Gate.run` waits after every free check and before anything is paid;
- every seat (league/swarm/bands.py): an equity Candidate is seatless (`equity_seating`, the roster report), an
  options Candidate takes no roster seat (`seating`), and no running row is returned for a held program (`read`, the
  options lanes' tuition rows and THE INCUBATOR's facts included). A program already at Probe or Sized keeps its seat
  and its lots (A50a (4): a holder is never displaced, so no close is manufactured); with no row its OPENS STOP AND
  ITS EXITS GO ON (the EquityBook reads `bands.equity_seat_withdrawn`: "held"; an options instance with no row runs on
  exits only).

WHAT IT NEVER DOES. It moves no id (league/gym/events.py is read, never written), never touches FWD1-R's pinned
registry or its judging (league/ops/forward_screen.py reads nothing of it: whether forward judging of an event reader
should be held or annotated is the owner's question), and changes no screen, bar, FP rate, money rule or stop.
Holding a program it does not need to hold costs that program its wait, never a try, a look or a lot.

Standard library only.
"""

from __future__ import annotations

import ast
import datetime as dt
import functools
import time
from typing import Any, Mapping

#: The flags the hold reads for (A25 R1): those from a static table with a last row. The calendar's own flags
#: (`monthly_opex`, `quarter_end`, `half_day`) hold everywhere and are never held for.
FLAGS = ("fomc", "cpi", "jobs")
#: The family-state key of a hold the swarm recorded at Validation or at the look (`note`): {version, flags, stage, at}.
STATE_KEY = "event_hold"
#: The stages `note` records a hold at.
STAGES = ("validation", "look")
#: The name the gate's waiting line begins with (league/swarm/elane.py `look`, league/swarm/gate.py `Gate.run`).
NAME = "THE EVENT HOLD (A25 R1)"
_VIEWS = ("events", "events_next")
_DYNAMIC = ("vars", "__dict__", "__getattribute__")


def _event_names() -> tuple[str, ...]:
    from ..gym.events import EVENT_NAMES

    return tuple(EVENT_NAMES)


def tables() -> dict[str, frozenset[dt.date]]:
    """The three tables a held flag is read from (league/gym/events.py), read, never written."""
    from ..gym import events

    return {"fomc": frozenset(events.FOMC), "cpi": frozenset(events.CPI), "jobs": frozenset(events.JOBS)}


def table_ends() -> dict[str, dt.date | None]:
    """Each held flag's table's last row (None for an empty table: it covers nothing)."""
    return {flag: (max(rows) if rows else None) for flag, rows in tables().items()}


def today_utc(now: float | None = None) -> dt.date:
    """The House's UTC date (`now`: epoch seconds, else the clock)."""
    return dt.datetime.fromtimestamp(time.time() if now is None else float(now), dt.timezone.utc).date()


# ------------------------------------------------------------------------------------------------------- the reading
def _empty(node: ast.AST) -> bool:
    """An empty literal a guard falls back to: `{}`, `dict()` or `None`."""
    if isinstance(node, ast.Dict):
        return not node.keys
    if isinstance(node, ast.Constant):
        return node.value is None
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict" \
        and not node.args and not node.keywords


def _is_guard(node: ast.AST, aliases: set[str]) -> bool:
    """THE GUARD (release 1023a, the review's finding 5): `ctx.events or {}` (or `dict()`, `None`) is the same dict,
    which is never empty, or an empty one: it is the view, read by whatever reads it."""
    return isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and len(node.values) >= 2 \
        and _is_view(node.values[0], aliases) and all(_empty(v) for v in node.values[1:])


def _truth_only(node: ast.AST, parent: ast.AST | None) -> bool:
    """A view whose truth alone is used (release 1023a, the review's finding 5): the test of an `if`, `while`, `assert`,
    conditional expression or comprehension filter, `not` or `bool()` of it, or an `and` operand that is not the
    last. The dict always holds every flag (league/gym/events.py `EventCalendar.flags`), so its truth reads none;
    an `or` operand or the last `and` operand is the expression's value (handed on: every flag)."""
    if isinstance(parent, (ast.If, ast.While, ast.IfExp, ast.Assert)):
        return parent.test is node
    if isinstance(parent, ast.comprehension):
        return any(cond is node for cond in parent.ifs)
    if isinstance(parent, ast.UnaryOp):
        return isinstance(parent.op, ast.Not)
    if isinstance(parent, ast.Call):
        return isinstance(parent.func, ast.Name) and parent.func.id == "bool" and len(parent.args) == 1 \
            and parent.args[0] is node and not parent.keywords
    if isinstance(parent, ast.BoolOp):
        return isinstance(parent.op, ast.And) and parent.values[-1] is not node
    return False


def _is_view(node: ast.AST, aliases: set[str]) -> bool:
    if isinstance(node, ast.Attribute) and node.attr in _VIEWS:
        return True
    if isinstance(node, ast.NamedExpr) and _is_view(node.value, aliases):
        return True  # `(ev := ctx.events)["cpi"]`: the walrus is the view too
    if _is_guard(node, aliases):
        return True  # `ev = ctx.events or {}`: the guard is the view too
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr" \
            and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value in _VIEWS:
        return True
    return isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in aliases


def _constant_str(node: Any) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


@functools.lru_cache(maxsize=512)
def _reads(code: str) -> frozenset[str]:
    every = frozenset(_event_names())
    try:
        tree = ast.parse(code)
    except Exception:  # noqa: BLE001 - source that does not parse reads every flag (fail closed)
        return every
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    # Dynamic reaches into ctx read every flag: a getattr whose name is no constant, vars(), __dict__,
    # __getattribute__, or the word "events" itself anywhere but a getattr's constant name.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr" \
                and len(node.args) >= 2 and _constant_str(node.args[1]) is None:
            return every
        if isinstance(node, ast.Name) and node.id in _DYNAMIC:
            return every
        if isinstance(node, ast.Attribute) and node.attr in _DYNAMIC:
            return every
        if _constant_str(node) in _VIEWS:
            parent = parents.get(node)
            if not (isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == "getattr"
                    and len(parent.args) >= 2 and parent.args[1] is node):
                return every
    # Names bound to a view (`ev = ctx.events`, `ev: dict = ...`, `(ev := ctx.events)`), to a fixed point.
    aliases: set[str] = set()
    while True:
        before = len(aliases)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and _is_view(node.value, aliases):
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        return every  # a view unpacked or stored into something else
                    aliases.add(target.id)
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None \
                    and _is_view(node.value, aliases):
                if not isinstance(node.target, ast.Name):
                    return every
                aliases.add(node.target.id)
        if len(aliases) == before:
            break
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not _is_view(node, aliases):
            continue
        parent = parents.get(node)
        if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and getattr(parent, "value", None) is node:
            continue  # the alias's own binding, read through the alias above
        if parent is not None and _is_guard(parent, aliases) and parent.values[0] is node:
            continue  # the view inside its guard, read through the guard (itself a view)
        if _truth_only(node, parent):
            continue  # its truth alone: the dict always holds every flag, so no flag is read
        if isinstance(parent, ast.Subscript) and parent.value is node:
            key = _constant_str(parent.slice)
            if key is None:
                return every
            keys.add(key)
        elif isinstance(parent, ast.Attribute) and parent.value is node:
            if parent.attr == "get":
                call = parents.get(parent)
                key = _constant_str(call.args[0]) if isinstance(call, ast.Call) and call.func is parent and call.args \
                    else None
                if key is None:
                    return every
                keys.add(key)
            elif parent.attr in every:
                keys.add(parent.attr)
            else:
                return every  # .items(), .values(), .keys(), .copy(), ...: every flag
        elif isinstance(parent, ast.Compare) and node in parent.comparators \
                and all(isinstance(op, (ast.In, ast.NotIn)) for op in parent.ops) \
                and _constant_str(parent.left) is not None and len(parent.comparators) == 1:
            keys.add(str(_constant_str(parent.left)))
        else:
            return every  # walked, handed on, compared whole, unpacked: every flag
    return frozenset(keys & every)


def reads(code: Any) -> frozenset[str]:
    """The event flags a program's source reads (the module docstring, WHAT "READS" MEANS): a subset of
    league/gym/events.py `EVENT_NAMES`, every one of them for source that is no text or does not parse."""
    if not isinstance(code, str):
        return frozenset(_event_names())
    try:
        return _reads(code)
    except Exception:  # noqa: BLE001 - a reading that fails reads every flag (fail closed)
        return frozenset(_event_names())


# ------------------------------------------------------------------------------------------------------- the hold
def words(flags: Any, ends: Mapping[str, Any]) -> str:
    """The hold in the House's words (rules and the tables' own dates only: no figure of any program)."""
    names = [str(f) for f in flags]
    said = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    dates = [str(ends.get(f) or "no row") for f in names]
    end = dates[0] if len(dates) == 1 else f"{', '.join(dates[:-1])} and {dates[-1]}"
    table = "whose table (league/gym/events.py) ends" if len(names) == 1 else "whose tables (league/gym/events.py) end"
    return (f"{NAME}: its program reads {said}, {table} {end}, before today: it takes no Validation, no look and no "
            "seat until a calendar release covers its windows (it may still be researched on Train)")


def hold(code: Any, *, today: dt.date | None = None) -> dict[str, Any] | None:
    """THE EVENT HOLD of one program (the module docstring): None when its windows are covered (it reads no held flag,
    or every held flag it reads has a table row on or after `today`, the House's UTC date by default), else {flags (the
    held flags it reads whose tables end before today, in `FLAGS` order), ends {flag: the table's last row}, today,
    why (`words`)}. Never raises: a reading that fails reads every flag."""
    try:
        read = reads(code)
        day = today if isinstance(today, dt.date) else today_utc()
        ends = table_ends()
        late = [f for f in FLAGS if f in read and (ends.get(f) is None or ends[f] < day)]
        if not late:
            return None
        shown = {f: (ends[f].isoformat() if ends.get(f) is not None else None) for f in late}
        return {"flags": late, "ends": shown, "today": day.isoformat(), "why": words(late, shown)}
    except Exception:  # noqa: BLE001 - fail closed: every held flag, no date read
        late = list(FLAGS)
        return {"flags": late, "ends": {f: None for f in late}, "today": None,
                "why": words(late, {f: None for f in late})}


#: THE CALENDAR SENTENCE (release 1023a; the edge hunt's 3c item 8 (iv)): what the equity births' AGENDA and every
#: equity family's Train brief say of the tables, with each table's own last row (`calendar_text`). Rules and the
#: tables' dates only: no figure of any program, no outcome.
CALENDAR = ("THE EVENT CALENDAR (league/gym/events.py, what ctx.events and ctx.events_next read): cpi reads False on "
            "every session after {cpi}, jobs after {jobs} and fomc after {fomc}, in the Gym and live alike, until a "
            "calendar release adds rows (and on every session before the tables' first rows, all of 2016). False there "
            "says nothing about the day. A program that reads cpi, jobs or fomc may still be researched on Train, and "
            "THE EVENT HOLD gives it no Validation, no look and no seat while a flag it reads is past its table's last "
            "row. Walking, copying or handing on the dict, or a key that is no constant, reads every flag; name each "
            "flag you read (ctx.events['cpi'], .get('half_day')).")


def calendar_text() -> str:
    """THE CALENDAR SENTENCE (`CALENDAR`) with the tables' own last rows ("" when they cannot be read)."""
    try:
        ends = table_ends()
        return CALENDAR.format(**{f: (ends[f].isoformat() if ends.get(f) is not None else "its first row")
                                  for f in FLAGS})
    except Exception:  # noqa: BLE001 - the sentence is left out rather than said wrong
        return ""


def note(store: Any, fid: str, n: Any, held: Mapping[str, Any], *, stage: str, clock: Any = None) -> bool:
    """Record a hold the swarm applied at `stage` ("validation" | "look") ONCE: the family's state `STATE_KEY`
    {version, flags, stage, at} and one private `swarm.gate` event {action "event_hold", ...}, written only when the
    state does not already say the same version, flags and stage. True when it wrote. Never raises (a record that
    cannot be written is written at the next round's hold)."""
    try:
        fam = store.family(str(fid)) or {}
        state = fam.get("state") if isinstance(fam.get("state"), Mapping) else {}
        kept = state.get(STATE_KEY) if isinstance(state.get(STATE_KEY), Mapping) else {}
        version = int(n) if n is not None else None
        flags = [str(f) for f in held.get("flags") or []]
        if kept.get("version") == version and list(kept.get("flags") or []) == flags and kept.get("stage") == stage:
            return False
        at = float(clock()) if callable(clock) else time.time()
        store.set_state(str(fid), **{STATE_KEY: {"version": version, "flags": flags, "stage": stage, "at": at}})
        store.event("swarm.gate", str(fid), {"action": "event_hold", "stage": stage, "version": version,
                                             "flags": flags, "ends": dict(held.get("ends") or {}),
                                             "why": str(held.get("why") or "")[:400]})
        return True
    except Exception:  # noqa: BLE001 - a record only: the hold itself stands whatever is written
        return False


__all__ = ["FLAGS", "STATE_KEY", "STAGES", "NAME", "CALENDAR", "tables", "table_ends", "today_utc", "reads", "hold", "words",
           "calendar_text", "note"]
