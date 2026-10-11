"""The `contam_probe` job: a recall probe of each model route, one route a week, by era (release E3, D16).

Owner: E (league/ops/E3_INTERFACES.md). Protected. Saturday 00:10Z (the start of the UTC day, E2's `usd_day` line
still whole); paid, never retried. It asks a model route what it remembers of the market, to say how far a
generator's knowledge reaches into the eras the screens are calibrated on. Truth stays on the House: the probe is an
ops job, never a swarm round, and only AGGREGATES reach `<state>/contamination.json` (0600): never a per-question
truth or outcome (the Provider's own store keeps each request and answer, House only: said, not hidden).

THE QUESTIONS (`questions`, `recall_questions`) are built from symbol names and the calendar only (pure of prices: a
prompt is identical whatever the prices, and carries no truth and no score).
- S1: an index ETF's month ("Did X finish <Month YYYY> higher or lower than it finished the month before?").
- S2: another ETF against SPY, a month ("Did X return more or less than SPY in <Month YYYY>?"). S3: a stock against
  SPY, a month. S4: any non-SPY symbol against SPY, a week ("... in the week ending <date>?").
- Eras (`ERAS`): "2016-24", "2025", "2026H1".
- A CELL IS A FULL GRID (`grid`): in each (stratum, era), K = min(the stratum's symbols, `SYMBOLS_PER_CELL`), the K
  symbols first by `sha256(f"contam-1|{stratum}|{era}|{sym}")`; P = min(the era's periods, floor(`questions_per_cell`
  / K)), the P periods first by `sha256(f"contam-1|{stratum}|{era}|{period}")`; every (symbol, period) of the grid is
  asked: the same questions every probe and for every route.
- R2021, the reserve recall: 24 questions "State SPY's total return in <Month YYYY> to the nearest percent",
  2020-01..2021-12.

TRUTH (`truth`), on the House: the sign of the as-of close ratio over the period (S1), or of the difference of the two
ratios (S2-S4); a zero is a tie, dropped; a pair with no truth is left out of every share.

A CELL'S SCORE (`score`): n = answered non-ties, acc = correct / n, `base` = the larger share of one truth among them,
m = acc - base (agreement beyond a constant answer), the Wilson 95% interval (lo, hi) as description only (`wilson`).
p_perm (`perm_p`) = (1 + the number of `PERMUTATIONS` permutations pi of the cell's P periods, seeded
`sha256("contam-1|perm|" + stratum + "|" + era)`, for which the share of answers equal to truth(symbol, pi(period))
is >= acc) / (`PERMUTATIONS` + 1): truths move by whole period, so a constant answer scores 1 and same-period symbols
move together. `readable` iff at least 80% were answered, P >= 6 and the truths themselves as the answers (a perfect
answerer) have p_perm <= 0.05 (else the cell cannot show recall: six months that all rose). `recalled` iff readable
and p_perm <= 0.05. The recall: `rho` = Pearson of stated against true; `p_perm` = the share of `PERMUTATIONS`
permutations of the truths (seeded `sha256("contam-1|perm")`) with rho at least as large; and the sign accuracy.

THE FILE: {"version": "contam-1", "routes": {route: {"at", "model", "usd", "probes", "attempted_at", "idle", "cells":
{stratum: {era: {n, correct, ties, skipped, periods, symbols, acc, base, m, lo, hi, p_perm, readable, recalled}}},
"recall": {n, rho, p_perm, sign_acc}, "partial": {"probe_n", "qset", "usd", "cells", "recall"}}}, "history": [the last
24 route results]}.

THE JOB (`run`): skipped when the mode is "off", no route is due (`due`), or E2's day leaves it no dollar
(`elane_yield.room(store, settings, now)`: THE BOUND below). One route a run: `router = models.build_router(ctx.root, store, settings, config=ctx.config)`; routes =
`elane_yield.routes(settings, router)`. FIRST it writes the route's `attempted_at` and `idle` + 1 (`idle`: its
attempts in a row that added no cell; a cell written sets it to 0), so a route that cannot move goes to the back of
the line and never blocks the others. `probe_n` = 1 + the route's `probes` (its completed probes, a counter never
truncated). Cell by cell in a fixed order, then the recall: each batch `elane_yield.ask_on(router, route, role=ROLE,
system=SYSTEM, user=..., key=KEY, max_output=2000, effort="low")` with `KEY =
f"{KEY_PREFIX}:{route.key}:{probe_n}:{h}"`, h = the first 12 hex of sha256(the batch's user text); booked `elane_yield.book(store, f"probe:{route.key}", usd=...,
known=..., purpose="probe", answered=..., now=now)` (rows of their own, inside E2's day line; that function counts a
purpose it does not name under `usd_research`). THE KEY: the Provider answers a request key it has seen from its
store, at $0. So a resumed probe (the same `probe_n`) re-reads its own batches for nothing; a new probe (`probe_n` +
1) asks afresh and is billed; a batch whose questions changed has another hash and never meets an old answer. A cell
whose batches are all in is scored and written at once to `routes[route].partial` (aggregates only, with `probe_n`,
`qset` and the dollars so far); a partial with another `qset` is dropped. The run stops asking once its booked
dollars reach its bound or `ASK_SECONDS` have passed; the next run of that route goes on from the partial. When every
cell and the recall are in, the result is published (`at`, `model`, `usd`, `cells`, `recall`), `probes` + 1, `idle` 0,
`partial` removed, `history` appended. Truths and answers are dropped before every write. A `MissingData` (the store
being rewritten) ends the run with the cells already scored kept and the billed dollars booked.

AS BUILT, beside the words above.
- THE BOUND of a run's dollars is min(`usd_run`, E2's room for the UTC day when the run starts), and a run is skipped
  only when that room is zero. The probe's dollars are E2's (booked inside its day's line), so a run never takes
  more than the day has left; where E2's day line is under `usd_run` (E2 holds its day to a share of the swarm's
  Sail model line), a probe moves on by what each Saturday's line gives it and finishes over the next weeks, where
  "skipped while the room is under `usd_run`" would have skipped every run and told nobody.
- THE KEY's prefix is E2's own (`KEY_PREFIX`, "swarm:elane:probe"): the swarm tells the equity lanes' model dollars
  from the options researchers' by a request key that begins "swarm:elane:" (league/swarm/elane_yield.py; the
  loop's hourly pace), so the probe's dollars sit in the equity lanes' meters and one probe does not pause every
  options researcher for the hour after it. What makes a key repeat or not is unchanged: the route, `probe_n` and
  the batch's hash.
- THE UNIVERSE is the House's (`league.ops.equity_data.universe()`: every symbol the daily store is fetched for). S1's
  symbols are its index ETFs; S2's every ETF but SPY; S3's the stocks; S4's every symbol but SPY.
- A PERIOD (`periods`) is a calendar month ("YYYY-MM") or, for S4, an ISO week named by the day it ends on; it belongs
  to the era its last session falls in. Its return runs from the last session BEFORE it (`first`) to its own last
  session (`last`), so a period with no session before it in the store's calendar (January 2016, and 2016's first
  week) is not in any grid.
- A cell's `skipped` counts the questions with no usable answer, and "answered" in `readable` is the share of the
  cell's questions with one. A question whose truth is missing or a tie stays in the grid (the permutation needs it
  whole) and enters no share.
- THE TIMES in the file (`at`, `attempted_at`) are ISO text (`league.ops.schedule.iso`); `due` reads either that or
  epoch seconds. A published route also carries `newly_recalled` (the "stratum/era" cells recalled now and not in its
  result before), which CP1 reads; a partial is kept from a route's first billed call, so its dollars are whole.
- THE ALERTS the job raises itself (`ctx.alert`; ids, counts and names only): CP2 (warning) when the route's `idle`
  reaches `IDLE_ALARM`, CP1 (info) for each 2025 or 2026H1 cell newly recalled. A call that fails ends the run for
  that route ("stopped": "error"; its billed dollars booked); the next run goes on from the partial.
- ONE ROUTE, ONE MODEL. The router sends a Sail profile outside the asap window to its fallback profile while that
  window is stalled (league/swarm/models.py `sail_fallback`), and the fallback may be another model. An answer another
  profile gave is not the probed route's memory: it is read by no score, its dollars are booked on the row of the
  route that gave it ("probe:sail:<profile>", as E2 books a fallback's answer), and the run ends ("stopped":
  "fallback"). The route adds no cell that run, so it goes to the back of the line and CP2 says so at the third.
- THE ANSWERS' PARSE (`parse`) reads the array with the most usable answers of those a reply holds (a fence or a
  sentence around it changes nothing), and of a reply cut before its array ends the whole entries before the cut.
- ANSWERS FIRST, THEN TRUTH: a cell's truths are read only once all its batches are in, so no truth exists while a
  prompt is built. A store that cannot be opened with the gate's capability fails the job BEFORE the route is marked
  (the House's, never the route's).

SETTINGS (`cfg`, `mode`): `elane.contam.*` (`DEFAULTS`, `BOUNDS`); a malformed value is its code default; an
unreadable block is "off". The receipt holds `route`, `usd` and `finished`. Standard library and numpy only.
"""

from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
import math
import time
import weakref
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

FILE = "contamination.json"
VERSION = "contam-1"
#: The reason the job mints its `EquityGateCapability` with (truth after 2025 reads sealed days).
GATE_REASON = "contamination-probe"
#: era -> (first day, last day).
ERAS: dict[str, tuple[dt.date, dt.date]] = {
    "2016-24": (dt.date(2016, 1, 4), dt.date(2024, 12, 31)),
    "2025": (dt.date(2025, 1, 2), dt.date(2025, 12, 31)),
    "2026H1": (dt.date(2026, 1, 2), dt.date(2026, 6, 30)),
}
STRATA = ("S1", "S2", "S3", "S4")
#: The reserve recall's name in the file, and its months.
RECALL = "R2021"
RECALL_MONTHS = ((2020, 1), (2021, 12))
#: The role the probe's questions carry on a route (its cache key and the router's books).
ROLE = "elane_probe"
#: What every request key of the probe begins with: the equity lanes' own mark in the swarm's spend rows.
KEY_PREFIX = "swarm:elane:probe"
SYMBOLS_PER_CELL = 8
PERMUTATIONS = 2000
#: No new call after this many seconds of a run (the Provider bounds a call at 900 s; the job's wall is 3,300).
ASK_SECONDS = 2300
#: A cell is readable only with this share answered, this many periods and a perfect answerer at or under `ALPHA`.
READABLE_ANSWERED = 0.80
READABLE_PERIODS = 6
ALPHA = 0.05
#: The file keeps this many route results in `history`.
HISTORY = 24
MODES = ("off", "record")
#: `elane.contam.*` (policy.json ships "record"; the code default is "off"). `usd_run`: dollars a run (one route);
#: `every_days`: a route is probed again after this; `batch`: questions a call.
DEFAULTS: dict[str, Any] = {"mode": "off", "usd_run": 3.0, "every_days": 28, "batch": 20, "questions_per_cell": 120}
BOUNDS: dict[str, tuple[float, float]] = {"usd_run": (0.0, 10.0), "every_days": (7, 90), "batch": (5, 40),
                                          "questions_per_cell": (20, 200)}
#: The one fixed system text of every probe call.
SYSTEM = ("You are answering a memory quiz about past United States market history. Answer from memory alone; you "
          "have no tools and no data. When you are unsure, give your best guess: answer every item, never skip one "
          "and never explain. Reply with a JSON array only, one entry an item, in the order asked.")


#: The symbol every relative question is asked against.
AGAINST = "SPY"
#: The two answers of a stratum's questions, the first for a positive truth.
WORDS: dict[str, tuple[str, str]] = {"S1": ("higher", "lower"), "S2": ("more", "less"), "S3": ("more", "less"),
                                     "S4": ("more", "less")}
#: A period's kind by stratum (S4 asks by week).
WEEKLY = ("S4",)
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
#: The recall questions' era label (the reserve years; never a cell's era).
RECALL_ERA = "2020-21"
#: A route whose attempts in a row that added no cell reach this is CP2.
IDLE_ALARM = 3
#: The eras whose newly recalled cells are CP1 (the windows the screens judge on).
JUDGED_ERAS = ("2025", "2026H1")
#: The keys of a cell and of the recall in the file: aggregates only.
CELL_KEYS = ("n", "correct", "ties", "skipped", "periods", "symbols", "acc", "base", "m", "lo", "hi", "p_perm",
             "readable", "recalled")
RECALL_KEYS = ("n", "rho", "p_perm", "sign_acc")
#: A probe call's output bound and effort.
MAX_OUTPUT = 2000
EFFORT = "low"
#: `parse` tries this many opening brackets of a reply for its array of answers.
ARRAY_STARTS = 32
_Z95 = 1.959963984540054


# ------------------------------------------------------------------------------------------------------------ settings
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane.contam` in the swarm's settings: every key of `DEFAULTS`, each value inside its bound; a malformed value
    is its code default; an unreadable block is `DEFAULTS` (mode "off")."""
    out = dict(DEFAULTS)
    lane = settings.get("elane") if isinstance(settings, Mapping) else None
    block = lane.get("contam") if isinstance(lane, Mapping) else None
    if not isinstance(block, Mapping):
        return out
    if isinstance(block.get("mode"), str) and block["mode"] in MODES:
        out["mode"] = block["mode"]
    for key, (lo, hi) in BOUNDS.items():
        x = _num(block.get(key))
        if x is None or not lo <= x <= hi:
            continue
        if isinstance(DEFAULTS[key], int):
            if x.is_integer():
                out[key] = int(x)
        else:
            out[key] = x
    return out


def mode(settings: Mapping[str, Any] | None) -> str:
    """`cfg(settings)["mode"]`: "off" | "record"."""
    return cfg(settings)["mode"]


# ------------------------------------------------------------------------------------------------------- the questions
def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@functools.lru_cache(maxsize=32)
def _span_periods(first: dt.date, last: dt.date, weekly: bool) -> tuple[tuple[str, str, str], ...]:
    """(period, the last session before it, its last session) of every month (or ISO week) whose last session lies in
    [first, last], oldest first; the calendar is `league.equity.store.nyse_sessions` and nothing else. A period with
    no session before it in that calendar (the calendar's first month and week) is left out."""
    from ..equity.store import FIRST_YEAR, nyse_sessions

    start = max(first - dt.timedelta(days=45), dt.date(FIRST_YEAR, 1, 1))
    days = [d for d, _ in nyse_sessions(start, last + dt.timedelta(days=10))]
    groups: dict[tuple[int, int], list[int]] = {}
    for i, day in enumerate(days):
        key = tuple(day.isocalendar()[:2]) if weekly else (day.year, day.month)
        groups.setdefault(key, []).append(i)  # type: ignore[arg-type]
    out = []
    for key, members in groups.items():
        end = days[members[-1]]
        if not first <= end <= last or members[0] == 0:
            continue
        name = end.isoformat() if weekly else f"{key[0]:04d}-{key[1]:02d}"
        out.append((name, days[members[0] - 1].isoformat(), end.isoformat()))
    return tuple(out)


def periods(stratum: str, era: str) -> list[tuple[str, str, str]]:
    """Every period of a stratum's kind in an era, oldest first: (period, first, last), `first` the last session
    before the period and `last` its own last session (ISO days). Months for S1-S3 and the recall ("YYYY-MM"), ISO
    weeks for S4 (the day the week ends on). KeyError for an era that is none of `ERAS` (the recall's is its own)."""
    if stratum == RECALL:
        (y0, m0), (y1, m1) = RECALL_MONTHS
        last = (dt.date(y1 + (m1 == 12), m1 % 12 + 1, 1) - dt.timedelta(days=1))
        return list(_span_periods(dt.date(y0, m0, 1), last, False))
    if stratum not in STRATA:
        raise KeyError(f"no stratum {stratum!r}; one of {', '.join(STRATA)}")
    first, last = ERAS[era]
    return list(_span_periods(first, last, stratum in WEEKLY))


def stratum_symbols(symbols: Mapping[str, str], stratum: str) -> list[str]:
    """The symbols a stratum asks about, in the universe's order: S1 the index ETFs; S2 every ETF but SPY; S3 the
    stocks; S4 every symbol but SPY."""
    from ..equity import config

    names = [(str(sym).strip().upper(), str(klass)) for sym, klass in symbols.items()]
    if stratum == "S1":
        return [s for s, _ in names if s in config.INDEX_ETFS]
    if stratum == "S2":
        return [s for s, klass in names if klass == config.ETF and s != AGAINST]
    if stratum == "S3":
        return [s for s, klass in names if klass == config.STOCK]
    if stratum == "S4":
        return [s for s, _ in names if s != AGAINST]
    raise KeyError(f"no stratum {stratum!r}; one of {', '.join(STRATA)}")


def grid(symbols: Mapping[str, str], stratum: str, era: str, *, per_cell: int) -> tuple[list[str], list[str]]:
    """D16's full grid of one cell: (its K symbols, its P periods), each in hash order. `symbols`: {symbol: class}
    (the House universe); a month period is "YYYY-MM", a week period the ISO day it ends on."""
    names = stratum_symbols(symbols, stratum)
    k = min(len(names), SYMBOLS_PER_CELL)
    if not k:
        return [], []
    chosen = sorted(names, key=lambda sym: _digest(f"{VERSION}|{stratum}|{era}|{sym}"))[:k]
    every = [name for name, _, _ in periods(stratum, era)]
    p = min(len(every), max(0, int(per_cell)) // k)
    return chosen, sorted(every, key=lambda period: _digest(f"{VERSION}|{stratum}|{era}|{period}"))[:p]


def _month_words(period: str) -> str:
    return f"{MONTHS[int(period[5:7]) - 1]} {period[:4]}"


def _text(stratum: str, symbol: str, period: str) -> str:
    if stratum == RECALL:
        return f"State {symbol}'s total return in {_month_words(period)} to the nearest percent."
    if stratum == "S1":
        return f"Did {symbol} finish {_month_words(period)} higher or lower than it finished the month before?"
    if stratum in WEEKLY:
        return f"Did {symbol} return more or less than {AGAINST} in the week ending {period}?"
    return f"Did {symbol} return more or less than {AGAINST} in {_month_words(period)}?"


def _question(stratum: str, era: str, symbol: str, period: str, first: str, last: str) -> dict[str, Any]:
    return {"id": f"{stratum}|{era}|{symbol}|{period}", "stratum": stratum, "era": era, "symbol": symbol,
            "against": None if stratum in ("S1", RECALL) else AGAINST, "first": first, "last": last, "period": period,
            "text": _text(stratum, symbol, period)}


def questions(symbols: Mapping[str, str], *, per_cell: int) -> list[dict[str, Any]]:
    """Every question of every cell, in a fixed order: {"id", "stratum", "era", "symbol", "against", "first", "last",
    "period", "text"}. Pure of prices: names and the calendar only."""
    out = []
    for stratum in STRATA:
        for era in ERAS:
            names, chosen = grid(symbols, stratum, era, per_cell=per_cell)
            bounds = {name: (first, last) for name, first, last in periods(stratum, era)}
            for period in chosen:
                for symbol in names:
                    out.append(_question(stratum, era, symbol, period, *bounds[period]))
    return out


def recall_questions() -> list[dict[str, Any]]:
    """R2021's 24 questions (SPY's total return a month, 2020-01..2021-12), shaped as `questions`' rows."""
    return [_question(RECALL, RECALL_ERA, AGAINST, name, first, last) for name, first, last in periods(RECALL, RECALL_ERA)]


def qset(questions: Sequence[Mapping[str, Any]]) -> str:
    """The sha256 of the questions' ids, in order: a partial made on another set is dropped."""
    return _digest("\n".join(str(q["id"]) for q in questions))


# ------------------------------------------------------------------------------------------------------------ the truth
#: The as-of closes read so far, by store: {(symbol, window): {ISO day: close}} (a truth reads the same SPY close for
#: every symbol of a period; a window is sliced once a symbol).
_CLOSES: "weakref.WeakKeyDictionary[Any, dict[tuple[str, str], dict[str, float]]]" = weakref.WeakKeyDictionary()


def _close(store: Any, symbol: str, day: str) -> float | None:
    """The adjustment=all close of `symbol` on `day` (an as-of close ratio between two days is the ratio of these),
    None when the store holds no such bar. A store being rewritten raises `MissingData`; a sealed day without the
    gate's capability `StoreRefused`."""
    from ..equity import config
    from ..equity.store import from_ordinal, window_of

    window = window_of(dt.date.fromisoformat(day))
    if window not in config.WINDOWS or symbol not in store.symbols():
        return None
    try:
        held = _CLOSES.setdefault(store, {})
    except TypeError:  # a store that cannot be weakly referenced (a test's stand-in): no cache
        held = {}
    if (symbol, window) not in held:
        bars = store.bars((symbol,), window, history=0)
        column = bars.adj[symbol][:, 3]
        held[(symbol, window)] = {from_ordinal(int(d)).isoformat(): float(c) for d, c in zip(bars.days, column)
                                  if math.isfinite(float(c)) and float(c) > 0}
    return held[(symbol, window)].get(day)


def truth(store: Any, question: Mapping[str, Any]) -> str | float | None:
    """A question's truth from the House's store (`EquityStore` with the capability): "higher" | "lower" (S1), "more"
    | "less" (S2-S4), the percent return (R2021), "tie" for a zero, None when a price is missing. Never written."""
    stratum = str(question["stratum"])

    def ratio(symbol: Any) -> float | None:
        a = _close(store, str(symbol), str(question["first"]))
        b = _close(store, str(symbol), str(question["last"]))
        return None if a is None or b is None else b / a

    own = ratio(question["symbol"])
    if own is None:
        return None
    if stratum == RECALL:
        return (own - 1.0) * 100.0
    if stratum == "S1":
        gap = own - 1.0
    else:
        other = ratio(question.get("against") or AGAINST)
        if other is None:
            return None
        gap = own - other
    return "tie" if gap == 0 else WORDS[stratum][0 if gap > 0 else 1]


# ----------------------------------------------------------------------------------------------- the prompt, the answers
def prompt(batch: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    """(`SYSTEM`, the user text) of one batch of questions: numbered items, no truth, no score, no price."""
    strata = {str(q["stratum"]) for q in batch}
    if len(strata) != 1:
        raise ValueError("a batch asks one stratum's questions")
    stratum, n = strata.pop(), len(batch)
    if stratum == RECALL:
        lead = (f"For each of the {n} items below, state the total return in percent to the nearest whole percent, as a "
                f"number (for example 3 or -2). Reply with a JSON array of {n} numbers only, in the order asked.")
    else:
        a, b = WORDS[stratum]
        lead = (f"For each of the {n} items below, answer with one word: \"{a}\" or \"{b}\". Reply with a JSON array of "
                f"{n} strings only, in the order asked.")
    return SYSTEM, lead + "\n\n" + "\n".join(f"{i}. {q['text']}" for i, q in enumerate(batch, 1))


def _answer(stratum: str, entry: Any) -> Any:
    if isinstance(entry, Mapping):
        entry = entry.get("answer", next(iter(entry.values()), None) if len(entry) == 1 else None)
    if stratum == RECALL:
        if isinstance(entry, str):
            try:
                entry = float(entry.strip().rstrip("%").strip().replace("+", ""))
            except ValueError:
                return None
        return _num(entry)
    if not isinstance(entry, str):
        return None
    word = entry.strip().strip(".\"'").lower()
    return word if word in WORDS[stratum] else None


def parse(text: Any, batch: Sequence[Mapping[str, Any]]) -> list[Any]:
    """The batch's answers from a model's reply, one an item in order (None for an item not answered, or for all when
    the reply holds no JSON array). A model may write a fence or a sentence around its array: of the arrays the reply
    holds (the first `ARRAY_STARTS` brackets are tried), the one with the most usable answers is read, the earliest on
    a tie. A reply CUT before its array ends (a route's answer cut at its output bound) gives the whole entries before
    the cut; the items after it are not answered."""
    none: list[Any] = [None] * len(batch)
    if not isinstance(text, str):
        return none

    def read(data: Any) -> list[Any] | None:
        if not isinstance(data, list):
            return None
        out = [_answer(str(q["stratum"]), entry) for q, entry in zip(batch, data)]
        return out + none[len(out):]

    decoder = json.JSONDecoder()
    starts = [i for i, ch in enumerate(text) if ch == "["][:ARRAY_STARTS]
    best: list[Any] | None = None
    for start in starts:
        try:
            got = read(decoder.raw_decode(text, start)[0])
        except ValueError:
            continue
        if got is not None and (best is None or sum(a is not None for a in got) > sum(a is not None for a in best)):
            best = got
    if best is None and starts:  # no array ends: the entries before the cut
        cut = text.rfind(",")
        if cut > starts[0]:
            try:
                best = read(json.loads(text[starts[0]:cut] + "]"))
            except ValueError:
                best = None
    return best if best is not None else none


# ------------------------------------------------------------------------------------------------------------ the score
def wilson(k: int, n: int) -> tuple[float, float]:
    """The Wilson 95% interval (lo, hi) of k of n ((0.0, 1.0) when n is 0)."""
    if n <= 0:
        return 0.0, 1.0
    share = k / n
    z2 = _Z95 * _Z95
    centre = (share + z2 / (2 * n)) / (1 + z2 / n)
    half = _Z95 * math.sqrt(share * (1 - share) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, centre - half), min(1.0, centre + half)


@functools.lru_cache(maxsize=64)
def _permutations(seed: str, n: int) -> tuple[tuple[int, ...], ...]:
    """`PERMUTATIONS` permutations of range(n), drawn by a counter hash of `seed` (the same on every Python): the
    i-th orders the positions by sha256(seed|i|position)."""
    return tuple(tuple(sorted(range(n), key=lambda j: hashlib.sha256(f"{seed}|{i}|{j}".encode()).digest()))
                 for i in range(PERMUTATIONS))


def perm_p(answers: Sequence[Any], truths: Sequence[Any], periods: Sequence[str], *, seed: str) -> float:
    """D16's p_perm of one cell: answers and truths a question, `periods` each question's period; the cell's periods
    are permuted whole, `PERMUTATIONS` times, seeded by `seed`.

    The rows are a FULL GRID in period order: every period holds the same number of questions, the j-th of each the
    same symbol (ValueError otherwise). Under a permutation pi the question (period p, symbol j) is held against the
    truth of (pi(p), j); a pair with no answer, no truth or a tie enters neither side of the share. The observed share
    and each permuted one are compared as exact fractions."""
    import numpy as np

    if not len(answers) == len(truths) == len(periods):
        raise ValueError("answers, truths and periods are one a question")
    rows: dict[str, list[int]] = {}
    for i, period in enumerate(periods):
        rows.setdefault(str(period), []).append(i)
    if len({len(members) for members in rows.values()}) > 1:
        raise ValueError("the cell is not a full grid: its periods hold different numbers of questions")
    if not rows:
        return 1.0
    codes: dict[Any, int] = {}

    def code(value: Any) -> int:
        return -1 if value is None or value == "tie" else codes.setdefault(value, len(codes))

    a = np.array([[code(answers[i]) for i in members] for members in rows.values()], dtype=np.int64)
    t = np.array([[code(truths[i]) for i in members] for members in rows.values()], dtype=np.int64)
    valid = (a >= 0) & (t >= 0)
    correct, n = int(((a == t) & valid).sum()), int(valid.sum())
    if not n:
        return 1.0
    moved = t[np.array(_permutations(str(seed), len(rows)), dtype=np.int64)]      # (permutations, periods, symbols)
    held = (a[None, :, :] >= 0) & (moved >= 0)
    c = ((a[None, :, :] == moved) & held).sum(axis=(1, 2))
    m = held.sum(axis=(1, 2))
    count = int(((m > 0) & (c * n >= correct * m)).sum())                          # exact: integers on both sides
    return (1 + count) / (PERMUTATIONS + 1)


def _pearson(pairs: Sequence[tuple[float, float]]) -> float | None:
    n = len(pairs)
    if n < 3:
        return None
    mx = math.fsum(x for x, _ in pairs) / n
    my = math.fsum(y for _, y in pairs) / n
    sxx = math.fsum((x - mx) ** 2 for x, _ in pairs)
    syy = math.fsum((y - my) ** 2 for _, y in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return math.fsum((x - mx) * (y - my) for x, y in pairs) / math.sqrt(sxx * syy)


def _score_recall(answers: Sequence[Any], truths: Sequence[Any]) -> dict[str, Any]:
    pairs = [(float(a), float(t)) for a, t in zip(answers, truths) if _num(a) is not None and _num(t) is not None]
    n = len(pairs)
    rho = _pearson(pairs)
    p = None
    if rho is not None:
        stated, true = [x for x, _ in pairs], [y for _, y in pairs]
        count = 0
        for order in _permutations(_digest(f"{VERSION}|perm"), n):
            other = _pearson(list(zip(stated, (true[j] for j in order))))
            count += int(other is not None and other >= rho - 1e-12)
        p = count / PERMUTATIONS
    sign = [(x > 0) - (x < 0) == (y > 0) - (y < 0) for x, y in pairs]
    return {"n": n, "rho": None if rho is None else round(rho, 4), "p_perm": None if p is None else round(p, 6),
            "sign_acc": round(sum(sign) / n, 4) if n else None}


def score(questions: Sequence[Mapping[str, Any]], answers: Sequence[Any], truths: Sequence[Any]) -> dict[str, Any]:
    """One cell's aggregates (the module docstring): {n, correct, ties, skipped, periods, symbols, acc, base, m, lo,
    hi, p_perm, readable, recalled}; for R2021's questions {n, rho, p_perm, sign_acc}. Never a per-question row."""
    if not questions or not len(questions) == len(answers) == len(truths):
        raise ValueError("a score takes a cell's questions with one answer and one truth each")
    stratum = str(questions[0]["stratum"])
    if stratum == RECALL:
        return _score_recall(answers, truths)
    era = str(questions[0]["era"])
    named = [str(q["period"]) for q in questions]
    usable = [t is not None and t != "tie" for t in truths]
    pairs = [(a, t) for a, t, ok in zip(answers, truths, usable) if ok and a is not None]
    n = len(pairs)
    correct = sum(a == t for a, t in pairs)
    skipped = sum(a is None for a in answers)
    acc = correct / n if n else None
    base = max(Counter(t for _, t in pairs).values()) / n if n else None
    lo, hi = wilson(correct, n)
    seed = _digest(f"{VERSION}|perm|{stratum}|{era}")
    p = perm_p(answers, truths, named, seed=seed) if n else None
    # A perfect answerer (the truths themselves as the answers) must clear the test, or the cell cannot show recall.
    perfect = perm_p([t if ok else None for t, ok in zip(truths, usable)], truths, named, seed=seed)
    count = len(set(named))
    readable = bool((len(questions) - skipped) / len(questions) >= READABLE_ANSWERED and count >= READABLE_PERIODS
                    and perfect <= ALPHA)
    return {"n": n, "correct": correct, "ties": sum(t == "tie" for t in truths), "skipped": skipped, "periods": count,
            "symbols": len({str(q["symbol"]) for q in questions}), "acc": None if acc is None else round(acc, 4),
            "base": None if base is None else round(base, 4),
            "m": None if acc is None or base is None else round(acc - base, 4), "lo": round(lo, 4), "hi": round(hi, 4),
            "p_perm": None if p is None else round(p, 6), "readable": readable,
            "recalled": bool(readable and p is not None and p <= ALPHA)}


# ------------------------------------------------------------------------------------------------------------- the file
def _epoch(value: Any) -> float | None:
    from . import schedule

    try:
        return schedule.epoch(value)
    except (TypeError, ValueError):
        return None


def read(root: str | Path) -> dict[str, Any]:
    """`<root>/contamination.json` as the job keeps it ({"version", "routes", "history"}); a missing, unreadable or
    other-versioned file is an empty one."""
    from .context import read_json

    doc = read_json(Path(root) / FILE, None)
    if not isinstance(doc, dict) or doc.get("version") != VERSION:
        return {"version": VERSION, "routes": {}, "history": []}
    routes = doc.get("routes")
    history = doc.get("history")
    return {"version": VERSION,
            "routes": {str(k): dict(v) for k, v in (routes if isinstance(routes, dict) else {}).items() if isinstance(v, dict)},
            "history": [dict(h) for h in (history if isinstance(history, list) else []) if isinstance(h, dict)][-HISTORY:]}


def due(doc: Mapping[str, Any] | None, routes: Sequence[str], *, now: float, every_days: float) -> str | None:
    """The route to probe now, None when none is due. Among the routes with no result or one older than `every_days`:
    first a route whose probe is under way and moving (a `partial`, `idle` 0), the oldest `attempted_at` first, so a
    probe that costs more than one run's dollars finishes in the next weeks; then the one whose max(`at`,
    `attempted_at`) is oldest (never tried first)."""
    held = doc.get("routes") if isinstance(doc, Mapping) and isinstance(doc.get("routes"), Mapping) else {}
    never = float("-inf")
    rows = []
    for order, key in enumerate(routes):
        row = held.get(key) if isinstance(held.get(key), Mapping) else {}
        at, tried = _epoch(row.get("at")), _epoch(row.get("attempted_at"))
        if at is not None and float(now) - at < float(every_days) * 86400.0:
            continue
        moving = isinstance(row.get("partial"), Mapping) and not row.get("idle")
        rows.append({"key": str(key), "order": order, "moving": moving, "tried": never if tried is None else tried,
                     "last": max(never if at is None else at, never if tried is None else tried)})
    if not rows:
        return None
    moving = [r for r in rows if r["moving"]]
    if moving:
        return min(moving, key=lambda r: (r["tried"], r["order"]))["key"]
    return min(rows, key=lambda r: (r["last"], r["order"]))["key"]


# -------------------------------------------------------------------------------------------------------------- the job
class Probe:
    """One run of the job on one route (the module docstring), over what `run` opens: the swarm store (it books the
    dollars), the swarm's settings, the model router, the House's equity store opened with the gate's capability, and
    the universe. `clock` times the run for `ASK_SECONDS` (monotonic); the file's times are `ctx.now()`."""

    def __init__(self, ctx: Any, *, store: Any, settings: Mapping[str, Any] | None, router: Any, equity: Any,
                 symbols: Mapping[str, str], clock: Callable[[], float] = time.monotonic):
        self.ctx = ctx
        self.root = Path(ctx.root)
        self.store = store
        self.settings = settings
        self.router = router
        self.equity = equity
        self.symbols = dict(symbols)
        self.clock = clock

    def write(self, doc: Mapping[str, Any]) -> None:
        from .context import write_json

        write_json(self.root / FILE, doc)

    def run(self) -> dict[str, Any]:
        from ..equity.store import MissingData, StoreRefused
        from ..swarm import elane_yield
        from . import schedule

        c = cfg(self.settings)
        if c["mode"] == "off":
            return {"status": "skipped", "why": "elane.contam.mode is off"}
        if c["usd_run"] <= 0:
            return {"status": "skipped", "why": "elane.contam.usd_run is zero: a probe may spend nothing"}
        now = float(self.ctx.now())
        served = {r.key: r for r in elane_yield.routes(self.settings, self.router)}
        doc = read(self.root)
        key = due(doc, list(served), now=now, every_days=c["every_days"])
        if key is None:
            return {"status": "skipped", "why": "no route is due a probe"}
        room = float(elane_yield.room(self.store, self.settings, now))
        bound = round(min(float(c["usd_run"]), room), 6)  # THE BOUND: never more than E2's day has left
        if not bound > 0:
            return {"status": "skipped", "why": "E2's model dollars for the day are spent: no room for a probe "
                                                "(elane.e2.usd_day)"}
        route = served[key]
        row = dict(doc["routes"].get(key) or {})
        probe_n = 1 + (int(row["probes"]) if isinstance(row.get("probes"), int) and not isinstance(row.get("probes"), bool)
                       and row["probes"] > 0 else 0)
        asked_of = questions(self.symbols, per_cell=c["questions_per_cell"])
        recall = recall_questions()
        mine = qset([*asked_of, *recall])
        partial = row.get("partial") if isinstance(row.get("partial"), Mapping) else None
        if partial is None or partial.get("qset") != mine or partial.get("probe_n") != probe_n \
                or not isinstance(partial.get("cells"), Mapping):
            partial = None  # another question set, or another probe's: dropped
        row.pop("partial", None)
        cells: dict[str, dict[str, Any]] = {s: dict(e) for s, e in ((partial or {}).get("cells") or {}).items()
                                            if isinstance(e, Mapping)}
        kept_recall = (partial or {}).get("recall") if isinstance((partial or {}).get("recall"), Mapping) else None
        before = _num((partial or {}).get("usd")) or 0.0
        answered_as = (partial or {}).get("model") if isinstance((partial or {}).get("model"), str) else None
        # FIRST the attempt: a route that cannot move goes to the back of the line.
        row["attempted_at"] = schedule.iso(now)
        row["idle"] = (int(row["idle"]) if isinstance(row.get("idle"), int) and not isinstance(row.get("idle"), bool)
                       else 0) + 1
        if partial is not None:
            row["partial"] = {"probe_n": probe_n, "qset": mine, "usd": round(before, 6), "model": answered_as,
                              "cells": cells, "recall": kept_recall}
        doc["routes"][key] = row
        self.write(doc)

        began = self.clock()
        state: dict[str, Any] = {"spent": 0.0, "asked": 0, "stopped": None, "error": None, "model": answered_as,
                                 "scored": 0}

        def save() -> None:
            row["partial"] = {"probe_n": probe_n, "qset": mine, "usd": round(before + state["spent"], 6),
                              "model": state["model"], "cells": cells, "recall": kept_recall}
            doc["routes"][key] = row
            self.write(doc)

        def ask(batch: Sequence[Mapping[str, Any]]) -> list[Any] | None:
            """One batch's answers, or None once the run stopped asking (`state["stopped"]` says why)."""
            if round(state["spent"], 6) >= bound:  # dollars to the ledger's own six places
                state["stopped"] = "usd"
                return None
            if self.clock() - began >= ASK_SECONDS:
                state["stopped"] = "time"
                return None
            system, user = prompt(batch)
            call = f"{KEY_PREFIX}:{route.key}:{probe_n}:{_digest(user)[:12]}"
            try:
                answer = elane_yield.ask_on(self.router, route, role=ROLE, system=system, user=user, key=call,
                                            max_output=MAX_OUTPUT, effort=EFFORT)
            except Exception as exc:  # noqa: BLE001 - the route could not answer: its billed dollars booked, the run ends
                billed = math.fsum(_num(b.get("cost_usd")) or 0.0 for b in getattr(exc, "billed", []) or []
                                   if isinstance(b, Mapping)) + max(0.0, _num(getattr(exc, "held_usd", 0.0)) or 0.0)
                elane_yield.book(self.store, f"probe:{route.key}", usd=billed, known=True, purpose="probe",
                                 answered=False, now=now)
                state["spent"] += billed
                state["stopped"], state["error"] = "error", f"{type(exc).__name__}: {str(exc)[:160]}"
                return None
            usd, known = elane_yield.answer_usd(answer)
            moved = answer.get("sail_fallback") if isinstance(answer, Mapping) else None
            other = str(moved.get("to") or "") if isinstance(moved, Mapping) else ""
            if route.kind == "sail" and other and other != route.name:
                # ANOTHER PROFILE ANSWERED (the router's own window fallback): not this route's memory. Its dollars go
                # to the row of the route that gave it, as E2 books them; no score reads the answer; the run ends.
                elane_yield.book(self.store, f"probe:sail:{other}", usd=usd, known=known, purpose="probe",
                                 answered=True, now=now)
                state["spent"] += usd
                state["stopped"] = "fallback"
                state["error"] = f"the router's window fallback answered on sail:{other}, not on {route.key}"
                return None
            elane_yield.book(self.store, f"probe:{route.key}", usd=usd, known=known, purpose="probe", answered=True,
                             now=now)
            state["spent"] += usd
            state["asked"] += 1
            if isinstance(answer, Mapping) and isinstance(answer.get("model"), str) and answer["model"]:
                state["model"] = answer["model"]
            return parse(answer.get("text") if isinstance(answer, Mapping) else None, batch)

        def cell(batch_of: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
            """A cell's aggregates once all its batches are in: answers first, then its truths (dropped with them)."""
            answers: list[Any] = []
            for i in range(0, len(batch_of), c["batch"]):
                got = ask(batch_of[i:i + c["batch"]])
                if got is None:
                    return None
                answers.extend(got)
            try:
                truths = [truth(self.equity, q) for q in batch_of]
            except (MissingData, StoreRefused) as exc:  # the store is being rewritten: what is scored so far stays
                state["stopped"], state["error"] = "data", f"{type(exc).__name__}: {str(exc)[:160]}"
                return None
            return score(batch_of, answers, truths)

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for q in asked_of:
            grouped.setdefault((q["stratum"], q["era"]), []).append(q)
        for (stratum, era), batch_of in grouped.items():
            if era in cells.get(stratum, {}):
                continue
            scored = cell(batch_of)
            if scored is None:
                break
            cells.setdefault(stratum, {})[era] = scored
            state["scored"] += 1
            row["idle"] = 0
            save()
        if state["stopped"] is None and kept_recall is None:
            scored = cell(recall)
            if scored is not None:
                kept_recall = scored
                state["scored"] += 1
                row["idle"] = 0
                save()
        finished = state["stopped"] is None and kept_recall is not None and all(
            era in cells.get(stratum, {}) for stratum, era in grouped)
        usd = round(before + state["spent"], 6)
        if finished:
            earlier = row.get("cells") if isinstance(row.get("cells"), Mapping) else {}
            newly = [f"{s}/{e}" for s, eras in cells.items() for e, got in eras.items() if got.get("recalled")
                     and not ((earlier.get(s) or {}).get(e) or {}).get("recalled")]
            result = {"at": schedule.iso(now), "model": state["model"] or route.name, "usd": usd, "cells": cells,
                      "recall": kept_recall}
            row.update(result)
            row.update(probes=probe_n, idle=0, newly_recalled=newly)
            row.pop("partial", None)
            doc["routes"][key] = row
            doc["history"] = [*doc["history"], {"route": key, "probe_n": probe_n, **result}][-HISTORY:]
            self.write(doc)
            for name in newly:
                if name.split("/", 1)[1] in JUDGED_ERAS:
                    self.ctx.alert("info", f"CP1: the contamination probe of route {key} newly reads cell {name} as recalled")
        elif state["spent"] > 0 or "partial" in row:
            save()  # the dollars so far stay with the probe they bought
        if row["idle"] >= IDLE_ALARM:
            self.ctx.alert("warning", f"CP2: the contamination probe's route {key} added no cell in its last "
                                      f"{int(row['idle'])} attempts")
        out = {"route": key, "probe": probe_n, "usd": round(state["spent"], 6), "bound": round(bound, 6),
               "finished": finished, "cells": state["scored"], "asked": state["asked"], "stopped": state["stopped"]}
        if state["error"]:
            out["error"] = state["error"]
        return out


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (the module docstring; league/ops/registry.py). The receipt: {"route", "probe" (its number), "usd",
    "bound" (the run's dollars at most), "finished", "cells" (scored this run), "asked", "stopped" ("usd" | "time" |
    "error" | "data" | "fallback" | None)} and, when a call or the store failed or another profile answered,
    "error"."""
    from ..equity.store import STORE_DIR, EquityStore, MissingData, StoreRefused, mint_equity_gate_capability
    from ..swarm import settings as settings_mod
    from . import equity_data

    root = Path(ctx.root)
    settings = settings_mod.load(root, config=ctx.config)
    if mode(settings) == "off":
        return {"status": "skipped", "why": "elane.contam.mode is off"}
    if not (root / "swarm.sqlite").exists():
        return {"status": "skipped", "why": "no swarm store yet"}
    try:  # the House's own parts first: a store that cannot be read marks no route and costs nothing
        EquityStore(root / STORE_DIR)  # absent or being rewritten: `MissingData`, before the capability is asked for
        equity = EquityStore(root / STORE_DIR, gate=mint_equity_gate_capability(root / STORE_DIR, GATE_REASON))
    except (MissingData, StoreRefused) as exc:
        return {"status": "failed", "error": f"the equity store cannot be read ({type(exc).__name__}): {str(exc)[:200]}"}
    from ..swarm.models import build_router
    from ..swarm.store import SwarmStore

    store = SwarmStore(root)
    try:
        router = build_router(root, store, settings, config=ctx.config)
        return Probe(ctx, store=store, settings=settings, router=router, equity=equity,
                     symbols=equity_data.universe()).run()
    finally:
        store.close()


__all__ = ["FILE", "VERSION", "GATE_REASON", "ERAS", "STRATA", "RECALL", "RECALL_MONTHS", "ROLE", "SYMBOLS_PER_CELL",
           "PERMUTATIONS", "ASK_SECONDS", "READABLE_ANSWERED", "READABLE_PERIODS", "ALPHA", "HISTORY", "MODES",
           "DEFAULTS", "BOUNDS", "SYSTEM", "KEY_PREFIX", "AGAINST", "WORDS", "RECALL_ERA", "IDLE_ALARM", "JUDGED_ERAS", "CELL_KEYS",
           "RECALL_KEYS", "cfg", "mode", "periods", "stratum_symbols", "grid", "questions", "recall_questions", "qset",
           "truth", "prompt", "parse", "wilson", "perm_p", "score", "read", "due", "Probe", "run"]
