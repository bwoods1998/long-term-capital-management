"""CALENDAR-BLIND (PREREG-H, eligibility): a program is eligible for the relabeled deep store only when BOTH checks
find it reads no calendar.

Owner: R1. A relabeled segment puts 2001-08 bars on 2016-22 pseudo-dates: a program's prices, volumes, positions and
cash are the true ones, but its calendar fields (`config.CALENDAR_FIELDS`: ctx.weekday, ctx.session_of_month,
ctx.sessions_to_month_end, ctx.events, ctx.events_next) are the pseudo-dates'. A program that reads one would be
judged on scrambled dates, so it is not eligible.

(a) THE SCAN (`scan`): the program's syntax tree, for an attribute named like a calendar field (whatever object it
    is read from: `ctx.weekday`, `c.events_next`) and for a string constant that names one (`getattr(ctx,
    "weekday")`: league/gym/safety.py admits getattr with a literal name only, so a string is the only other way).
(b) THE BEHAVIOURAL TEST (`behaviour`): two labelings of ONE synthetic store (league/equity/synth.py: GBM with a
    split, dividends and a symbol that starts late, never market data) are run through the program, the store's own
    sessions from 2016-01-04 and the same arrays from 2019-06-05 (another weekday, month phase and event days). The
    program is blind only when its lots, its daily record and its summary are the same, session for session. This
    catches what a scan cannot (a reader the scan did not foresee).

(c) THE LEVEL TEST (`level`, REPORT-ONLY: the review of Oct 17): the first labeling's store again with every price
    times `config.LEVEL_PRICE` and every volume times `config.LEVEL_VOLUME`, same days. The relabel hides dates but not
    price or volume levels (SPY traded about $70-160 in 2001-08), and neither check above sees a program keyed on them.
    The program is level-blind when its entries and exits (session, symbol, fill point, tag) are the same. A level
    reader is counted in the captain's report beside the verdicts, never refused: PREREG-H names no such rule.

`behaviour` runs the program through a `run(store_root, start, end)` the caller hands in: on the House the
decider-isolated child (league/equity/runner.py `Isolated(...).train`), in tests the in-process decider. The stores
live in a temporary directory (`deep-blind-p<pid>-*`, league/deep/blocks.py `temp_prefix`: swept after a kill)
removed when the test ends.
"""

from __future__ import annotations

import ast
import datetime as dt
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..equity import store as estore
from ..equity import synth
from . import blocks, config, relabel

FIELDS = frozenset(config.CALENDAR_FIELDS)


def scan(code: str) -> list[str]:
    """Every calendar read the syntax tree shows, as "line N: <how>" (empty: none found). Code that does not parse
    is one finding (it is not judged blind)."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return ["the program does not parse"]
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FIELDS:
            found.append(f"line {node.lineno}: reads .{node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in FIELDS:
            found.append(f"line {node.lineno}: names {node.value!r}")
    return sorted(set(found), key=lambda text: (int(text.split(":")[0][5:]), text))


def _store(root: Path, symbols: Sequence[str]) -> list[dt.date]:
    """THE TEST'S SYNTHETIC STORE: `config.BEHAVIOUR_SESSIONS` sessions from 2016-01-04, the first symbol split 2:1
    and paying a dividend, every other symbol a dividend, the last of several starting late (NaN before)."""
    days = [d for d, _ in estore.nyse_sessions(dt.date(2016, 1, 4), dt.date(2019, 12, 31))][:config.BEHAVIOUR_SESSIONS]
    names = [str(s).upper() for s in symbols]
    splits = {names[0]: [(days[len(days) * 3 // 4], 2.0)]}
    dividends = {sym: [(days[i], 0.35 + 0.05 * k) for i in range(60, len(days), 63)] for k, sym in enumerate(names)}
    gaps = {names[-1]: days[:120]} if len(names) > 1 else {}
    synth.synthetic_store(root, symbols=names, start=days[0], end=days[-1], seed=config.BEHAVIOUR_SEED, drift=0.08,
                          vol=0.22, splits=splits, dividends=dividends, gaps=gaps)
    return days


def _days_to_index(value: Any, index: Mapping[str, int]) -> Any:
    """`value` with every ISO day replaced by its session index (lists and dicts walked)."""
    if isinstance(value, str) and value in index:
        return ("session", index[value])
    if isinstance(value, Mapping):
        return {k: _days_to_index(v, index) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_days_to_index(v, index) for v in value]
    return value


def comparable(result: Mapping[str, Any], days: Sequence[dt.date]) -> dict[str, Any]:
    """What must be the same on two labelings: the lots, the trades and the daily record with their days as session
    indices, the entry sessions, the summary and the corporate actions the engine read (every block keyed by a year
    or a date is left out)."""
    index = {d.isoformat(): i for i, d in enumerate(days)}
    keep = {name: result.get(name) for name in ("status", "lots", "trades", "daily", "entry_days", "summary",
                                                "actions")}
    return _days_to_index(keep, index)


def timing(result: Mapping[str, Any], days: Sequence[dt.date]) -> list[tuple[Any, ...]]:
    """The level test's comparison: each lot's (entry session, exit session, symbol, entry and exit fill points, tag),
    days as session indices: what a program decided, whatever the quantities and prices it filled at."""
    index = {d.isoformat(): i for i, d in enumerate(days)}
    return [(index.get(str(lot.get("entry_day"))), index.get(str(lot.get("exit_day"))), lot.get("symbol"),
             lot.get("entry_at"), lot.get("exit_at"), lot.get("tag")) for lot in result.get("lots") or ()]


def behaviour(code: str, params: Mapping[str, Any] | None, run: Callable[[Path, dt.date, dt.date], Mapping[str, Any]],
              *, symbols: Sequence[str], history: int, parent: str | Path | None = None,
              level: bool = False) -> dict[str, Any]:
    """THE BEHAVIOURAL TEST: {"blind": bool, "why": None | what differed, "level": None, or with `level` and a blind
    program the level test's answer (True: level-blind)}. `run(store_root, start, end)` returns the program's whole
    result over [start, end] of that store (at k 1.0). `parent`: where its directory is made (swept first)."""
    if parent is not None:
        blocks.sweep(parent)
    tmp = Path(tempfile.mkdtemp(prefix=blocks.temp_prefix("blind"), dir=None if parent is None else str(parent)))
    try:
        first = _store(tmp / "A", symbols)
        second = relabel.copy_onto(tmp / "A", tmp / "B", config.BEHAVIOUR_SECOND)
        lead = min(int(history) + 1, len(first) // 2)
        a = run(tmp / "A", first[lead], first[-1])
        b = run(tmp / "B", second.pseudo_days[lead], second.pseudo_days[-1])
        ca, cb = comparable(a, first), comparable(b, second.pseudo_days)
        if a.get("status") != "ok" or b.get("status") != "ok":
            return {"blind": False, "why": f"the test runs did not finish ({a.get('status')}, {b.get('status')})",
                    "level": None}
        for name in ca:
            if ca[name] != cb[name]:
                return {"blind": False, "why": f"its {name} differ between two labelings of one store", "level": None}
        seen = None
        if level:
            third = relabel.copy_onto(tmp / "A", tmp / "C", first[0], price=config.LEVEL_PRICE,
                                      volume=config.LEVEL_VOLUME)
            c = run(tmp / "C", third.pseudo_days[lead], third.pseudo_days[-1])
            seen = c.get("status") == "ok" and timing(a, first) == timing(c, third.pseudo_days)
        return {"blind": True, "why": None, "level": seen}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check(code: str, params: Mapping[str, Any] | None, run: Callable[[Path, dt.date, dt.date], Mapping[str, Any]], *,
          symbols: Sequence[str], history: int, parent: str | Path | None = None,
          level: bool = False) -> dict[str, Any]:
    """Both checks: {"blind", "scan" (the findings), "behaviour" (its answer, None when the scan already refused),
    "level" (the level test's answer with `level`, else None; None too when the program is not blind)}. The
    behavioural test runs only for a program the scan finds blind (it costs two runs; the level test a third)."""
    found = scan(code)
    if found:
        return {"blind": False, "scan": found, "behaviour": None, "level": None}
    seen = behaviour(code, params, run, symbols=symbols, history=history, parent=parent, level=level)
    return {"blind": bool(seen["blind"]), "scan": [], "behaviour": seen, "level": seen.get("level")}


__all__ = ["FIELDS", "scan", "comparable", "timing", "behaviour", "check"]
