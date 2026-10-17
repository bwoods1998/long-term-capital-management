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

THE FILE: {"version": "contam-1", "routes": {route: {"at", "model", "usd", "probes", "attempts", "attempted_at",
"first_attempted_at", "idle", "cells": {stratum: {era: {n, correct, ties, skipped, periods, symbols, acc, base, m, lo,
hi, p_perm, readable, recalled}}}, "recall": {n, rho, p_perm, sign_acc}, "partial": {"probe_n", "qset", "usd",
"batch_usd", "cells", "recall"}}}, "history": [the last 24 route results]}.

THE PANEL STRATA (release E4, package B's patch 18; the captain's A22 (3): the probe before a panel look). Three more
strata, `PANEL_STRATA`, asked only when the job is handed A PLAN (`probe(ctx, panel=...)`; `run(ctx)` hands none and
is release E3's probe to the byte). This module reads nothing of the panel: release E3's seal lets it import no
module of league/xs, so the plan (release E4's league/ops/contam_xs.py, which in its turn imports nothing of this
module: the forward record's own seal) is the one that opens the panel store, under the capability this job mints,
and this module owns EVERY WORD OF A PROMPT. NOT WIRED: `run(ctx)`, the House's job, hands no plan; the two lines
that would hand it one need an allowance in E3's seal test, which is the captain's to give (the patch is in the
captain's scratch; league/xs/E4_INTERFACES.md section 14).
- P4: an index member against its sector's fund, a month ("Did X return more or less than the Select Sector SPDR
  fund of its sector in <Month YYYY>?"); P5: the same, a week ("... in the week ending <date>?"); P6: the House
  panel factors, a month (`FACTORS`: momentum, short-term reversal and beta, each the top third of the index against
  the bottom third: "In <Month YYYY>, did the equally weighted third of S&P 500 stocks ... return more or less than
  the third ...?"). THE FUND IS NOT NAMED: the House's sector is statistical, read from prices, and a prompt is
  built from names and the calendar only; the truth is against the fund of the House's sector at the period's base.
- THE PLAN HANDS IN NAMES AND PERIODS, NEVER A WORD (`panel_questions`): `plan.names(stratum, era)` (P4 and P5: the
  members asked about, each a ticker by `NAME`: capitals and at most one dot, so no figure can ride in one; P6's
  names are `FACTORS`, this module's own) and `plan.periods(stratum, era)` (period names, each one of this module's
  own calendar `periods(stratum, era)`; the plan leaves out what the panel cannot be asked: its reserve and its
  history years). A name or a period outside that is a ValueError before any route is marked. A cell is a full grid
  under THE SAME HASH RULE as E3's (`sha256(f"contam-1|{stratum}|{era}|{name}")`), the same for every route.
- TRUTH: `plan.truths(a cell's questions)`, "more" | "less" | "tie" | None each, asked only once the cell's answers
  are all in, as E3's are. The cells are scored by `score` and kept under their stratum in `cells`, in E3's shape
  (aggregates only). The panel's cells are asked AFTER E3's own, then the recall; a result is published when every
  cell asked is in, so a plan's result carries the three strata.
- A partial keeps `panel_qset` (the sha of the panel's questions) beside `qset`, which stays E3's own questions'
  sha: a panel question set that moved (a membership revision) drops the partial's PANEL cells and nothing of E3's;
  with no plan the panel cells of a partial are dropped (the lane was switched off) and none is published.
- A ROUTE WHOSE PUBLISHED RESULT LACKS A PANEL STRATUM THE PLAN NOW ASKS IS DUE AT ONCE (`_owing`): its result is not
  whole, and a panel look of its programs waits on it. STATED COST: that route's E3 cells are asked again with it,
  inside the same dollars a run (`usd_run` and E2's day, unchanged).
- AFTER A PUBLISH the plan is told (`plan.published(doc)`: it writes the look's permit, two words a cell). A permit
  that cannot be written is a warning and `permit` False in the receipt; the result stays published. After any other
  run that had a plan `probe` tells it again with the file as it stands, so a permit lost is made again.
- The receipt gains `panel` (the panel cells this probe asks) and, on a publish, `permit`; with no plan neither.

THE DEEP ERAS (release R1, the history-expansion plan A58: "contam_probe gains the eras 2001-08 and 2010-15"). Two
more eras, `DEEP_ERAS`, asked only while the House holds a deep store whose audit passed (league/ops/equity_deep.py
writes no other): without one the probe is release E3's (with its panel strata) to the byte. Their cells are E3's strata S1, S2 and S4
on the ETFs with a deep history (league/deep/config.py `DEEP_UNIVERSE`; S3, the stocks, has none), under THE SAME
HASH RULE and the same words, months and ISO weeks of THE DEEP CALENDAR (league/deep/calendar.py: the repo's
pre-2022 rules plus the 2001, 2004, 2007 and 2012 closures). Truth is the deep store's (`_DeepTruth`): the ratio of
two adjustment=all closes rebuilt from the raw closes and the events (league/deep/blocks.py `as_of_closes`), the
2001-08 era's from its history and sealed spans under a `DeepGateCapability` this job mints for
"contamination-probe", the 2010-15 era's from the open span alone; truths are read once a cell's answers are in, and
dropped with them, as E3's are. The partial keeps `deep_qset` beside `qset` (a deep question set that moved drops
the deep cells and nothing else); a route whose published result lacks a deep era while the store is there is due
at once, as a route that lacks a panel stratum is. S3's eligibility reads a route's 2001-08 cells from the file
(league/ops/deep_report.py `strong_recall`, which imports nothing of this module: the forward record's seal).

THE JOB (`run`): skipped when the mode is "off", no route is due (`due`), or E2's day leaves it no dollar
(`elane_yield.room(store, settings, now)`: THE BOUND below). One route a run: `router =
models.build_router(ctx.root, store, settings, config=ctx.config)`; routes = `elane_yield.routes(settings, router)`.
FIRST it writes the route's `attempted_at` and `idle` + 1 (`idle`: its attempts in a row that added no cell; a cell
written sets it to 0), so a route that cannot move goes to the back of the line and never blocks the others.
`probe_n` = 1 + the route's `probes` (its completed probes, a counter never truncated); `attempt` = the route's
`attempts` + 1 (its runs, a counter never truncated either, written with the mark before any call). Cell by cell in a
fixed order, then the recall: each batch `elane_yield.ask_on(router, route, role=ROLE, system=SYSTEM, user=...,
key=KEY, max_output=2000, effort="low")` with `KEY = f"{KEY_PREFIX}:{route.key}:{probe_n}:{attempt}:{h}"`, h = the
first 12 hex of sha256(the batch's user text); booked `elane_yield.book(store, f"probe:{route.key}", usd=...,
known=..., purpose="probe", answered=..., now=now)` (rows of their own, inside E2's day line; that function counts a
purpose it does not name under `usd_research`). A cell whose batches are all in is scored and written at once to
`routes[route].partial` (aggregates only, with `probe_n`, `qset`, the dollars so far and `batch_usd`, the dearest
batch the probe has paid for); a partial with another `qset` is dropped. The run stops asking once its booked dollars
reach its bound or `ASK_SECONDS` have passed; the next run of that route goes on from the partial. When every cell and
the recall are in, the result is published (`at`, `model`, `usd`, `cells`, `recall`), `probes` + 1, `idle` 0,
`partial` removed, `history` appended. Truths and answers are dropped before every write. A `MissingData` (the store
being rewritten) ends the run with the cells already scored kept and the billed dollars booked.

A KEY IS ASKED ONCE (the review of the build; the first build repeated a resumed probe's keys to "re-read its batches
at $0", which the router does not do). On the real router a repeated request key is answered from the Provider's
stored row WITH THAT ROW'S ORIGINAL COST (ltcm/provider.py; league/swarm/models.py books nothing twice, but the
answer carries the dollars again), and the swarm's loop blanks the stored responses of settled calls older than an
hour (`ModelRouter.compact`): a week later the re-read text is empty. A repeated key would so be booked a second time
on E2's ledger and against the run's own bound, and its cell scored with every answer of that batch missing. So:
- every run has keys of its own (`attempt`): a run never sends a key an earlier run sent. What a resumed probe keeps
  is its SCORED CELLS (the partial); a cell a stop cut is asked again whole by the next run, under that run's keys,
  and paid for again. STATED COST: at most one cell's batches a stop.
- to keep that rare, A CELL IS BEGUN ONLY WHEN THE RUN CAN PAY FOR IT: its batches at `batch_usd` (the dearest batch
  this probe has paid for, kept in the partial; unknown before the probe's first batch) must fit both what is left of
  the run's bound and E2's day as it stands. Otherwise the run stops there ("stopped": "usd") with its dollars unspent.
- a key the swarm's spend rows already carry (`elane_yield.booked_for`: the file was lost and the counters began
  again, say) is NOT asked: the run ends ("stopped": "error") and the next run's keys are new.
- an answer with no text is no answer (a call that produced nothing, or a stored row whose response was blanked): its
  dollars are booked, the run ends ("stopped": "error"), and no cell is scored on it. A model that answers and skips
  items is another matter: those are the cell's `skipped`.

AS BUILT, beside the words above.
- THE BOUND of a run's dollars is min(`usd_run`, E2's room for the UTC day when the run starts), and a run is skipped
  only when that room is zero. The probe's dollars are E2's (booked inside its day's line), so a run never takes
  more than the day has left, and it asks nothing more once the day's line is spent by anyone (the room is read again
  before every call: the swarm's own equity questions spend the same line meanwhile). Where E2's day line is under
  `usd_run` (as when E2 holds its day to a share of the swarm's Sail model line), a probe moves on by what each
  Saturday's line gives it and finishes over the next weeks, where "skipped while the room is under `usd_run`"
  would have skipped every run and told nobody.
- THE KEY's prefix is E2's own (`KEY_PREFIX`, "swarm:elane:probe"). E2's request keys begin "swarm:elane:", the mark
  by which the swarm's meters tell the equity lanes' model dollars from the options researchers' (where they read
  the spend rows by key: E2's own pace and the researchers' hourly one). Under it the probe's dollars sit in the
  equity lanes' meters, and one probe does not pause every options researcher for the hour after it. What makes a
  key: the route, `probe_n`, the run (`attempt`) and the batch's hash.
- THE UNIVERSE is the House's (`league.ops.equity_data.universe()`: every symbol the daily store is fetched for). S1's
  symbols are its index ETFs; S2's every ETF but SPY; S3's the stocks; S4's every symbol but SPY.
- A PERIOD (`periods`) is a calendar month ("YYYY-MM") or, for S4, an ISO week named by the day it ends on; it belongs
  to the era its last session falls in. Its return runs from the last session BEFORE it (`first`) to its own last
  session (`last`), so a period with no session before it in the store's calendar (January 2016, and 2016's first
  week) is not in any grid.
- A cell's `skipped` counts the questions with no usable answer, and "answered" in `readable` is the share of the
  cell's questions with one. A question whose truth is missing or a tie stays in the grid (the permutation needs it
  whole) and enters no share.
- THE TIMES in the file (`at`, `attempted_at`, `first_attempted_at`) are ISO text (`league.ops.schedule.iso`); `due`
  reads either that or epoch seconds. `first_attempted_at` is the route's first mark, written once and never moved
  (CP1's 45 days of a route no probe ever finished on count from it: league/ops/forward_report.py). A published
  route also carries `newly_recalled` (the "stratum/era" cells recalled now and not in its result before), which CP1
  reads; a partial is kept from a route's first billed call, so its dollars are whole.
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
import re
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
#: THE DEEP ERAS (release R1): asked only while the House holds a complete deep store, after E3's and the panel's.
DEEP_ERAS: dict[str, tuple[dt.date, dt.date]] = {
    "2001-08": (dt.date(2001, 4, 9), dt.date(2008, 12, 31)),
    "2010-15": (dt.date(2010, 1, 4), dt.date(2015, 12, 31)),
}
DEEP_STRATA = ("S1", "S2", "S4")
#: The reason the job mints its `DeepGateCapability` with (the 2001-08 truths read the sealed era).
DEEP_GATE_REASON = "contamination-probe"
#: THE PANEL STRATA (release E4): asked only with a plan (`probe(ctx, panel=...)`), after E3's own.
PANEL_STRATA = ("P4", "P5", "P6")
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
                                     "S4": ("more", "less"), "P4": ("more", "less"), "P5": ("more", "less"),
                                     "P6": ("more", "less")}
#: A period's kind by stratum (S4 and P5 ask by week).
WEEKLY = ("S4", "P5")
#: P6's names: the House panel factors (league/xs/results.py `factors`), each the top third of the index against the
#: bottom third, re-formed at the close before the month. What a question says of its two thirds, the top first.
FACTORS = ("mom", "strev", "beta")
FACTOR_WORDS: dict[str, tuple[str, str]] = {
    "mom": ("with the highest return over the year before the month, its last month left out,", "with the lowest"),
    "strev": ("that had fallen the most over the five sessions before the month", "that had risen the most"),
    "beta": ("with the highest market beta at the month's start", "with the lowest"),
}
#: A name a plan may hand in for P4 and P5: a ticker, capitals and at most one dot. No digit: no figure rides in one.
NAME = re.compile(r"^[A-Z]{1,6}(\.[A-Z]{1,2})?$")
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
def _span_periods(first: dt.date, last: dt.date, weekly: bool, deep: bool = False) -> tuple[tuple[str, str, str], ...]:
    """(period, the last session before it, its last session) of every month (or ISO week) whose last session lies in
    [first, last], oldest first; the calendar is `league.equity.store.nyse_sessions` and nothing else (`deep`: the
    deep calendar, league/deep/calendar.py, for `DEEP_ERAS`). A period with no session before it in that calendar
    (the calendar's first month and week) is left out."""
    from ..equity.store import FIRST_YEAR, nyse_sessions

    if deep:
        from ..deep import calendar as deep_calendar
        from ..deep import config as deep_config

        floor = dt.date(deep_config.FIRST_DAY.year, 1, 1)
        days = deep_calendar.sessions(max(first - dt.timedelta(days=45), floor), last + dt.timedelta(days=10))
    else:
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
    before the period and `last` its own last session (ISO days). Months for S1-S3, P4, P6 and the recall
    ("YYYY-MM"), ISO weeks for S4 and P5 (the day the week ends on). The calendar's, whole: which of them a panel
    stratum may ask is its plan's to say (`panel_questions`). KeyError for an era that is none of `ERAS` (the
    recall's is its own)."""
    if stratum == RECALL:
        (y0, m0), (y1, m1) = RECALL_MONTHS
        last = (dt.date(y1 + (m1 == 12), m1 % 12 + 1, 1) - dt.timedelta(days=1))
        return list(_span_periods(dt.date(y0, m0, 1), last, False))
    if stratum not in STRATA and stratum not in PANEL_STRATA:
        raise KeyError(f"no stratum {stratum!r}; one of {', '.join((*STRATA, *PANEL_STRATA))}")
    if era in DEEP_ERAS:
        first, last = DEEP_ERAS[era]
        return list(_span_periods(first, last, stratum in WEEKLY, True))
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
    if not names:
        return [], []
    return _grid(names, [name for name, _, _ in periods(stratum, era)], stratum, era, per_cell)


def _grid(names: Sequence[str], every: Sequence[str], stratum: str, era: str, per_cell: int) -> tuple[list[str], list[str]]:
    """THE HASH RULE of a cell, E3's strata and the panel's alike: (the K names, the P periods), K = min(the names,
    `SYMBOLS_PER_CELL`), P = min(the periods, floor(`per_cell` / K)), each the first by
    `sha256(f"contam-1|{stratum}|{era}|{name or period}")`."""
    k = min(len(names), SYMBOLS_PER_CELL)
    if not k:
        return [], []
    chosen = sorted(names, key=lambda sym: _digest(f"{VERSION}|{stratum}|{era}|{sym}"))[:k]
    p = min(len(every), max(0, int(per_cell)) // k)
    return chosen, sorted(every, key=lambda period: _digest(f"{VERSION}|{stratum}|{era}|{period}"))[:p]


def _month_words(period: str) -> str:
    return f"{MONTHS[int(period[5:7]) - 1]} {period[:4]}"


def _text(stratum: str, symbol: str, period: str) -> str:
    if stratum == RECALL:
        return f"State {symbol}'s total return in {_month_words(period)} to the nearest percent."
    if stratum == "S1":
        return f"Did {symbol} finish {_month_words(period)} higher or lower than it finished the month before?"
    if stratum == "P6":
        top, bottom = FACTOR_WORDS[symbol]
        return (f"In {_month_words(period)}, did the equally weighted third of S&P 500 stocks {top} return more or "
                f"less than the third {bottom}?")
    against = "the Select Sector SPDR fund of its sector" if stratum in PANEL_STRATA else AGAINST
    if stratum in WEEKLY:
        return f"Did {symbol} return more or less than {against} in the week ending {period}?"
    return f"Did {symbol} return more or less than {against} in {_month_words(period)}?"


def _question(stratum: str, era: str, symbol: str, period: str, first: str, last: str) -> dict[str, Any]:
    return {"id": f"{stratum}|{era}|{symbol}|{period}", "stratum": stratum, "era": era, "symbol": symbol,
            "against": None if stratum in ("S1", RECALL, *PANEL_STRATA) else AGAINST, "first": first, "last": last,
            "period": period, "text": _text(stratum, symbol, period)}


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


def panel_questions(panel: Any, *, per_cell: int) -> list[dict[str, Any]]:
    """Every question of the panel strata's cells, shaped and ordered as `questions`' rows (stratum, then era; a full
    grid a cell under `_grid`'s one hash rule; `against` None: the plan knows what a truth is against). THE PLAN HANDS
    IN NAMES AND PERIODS, NEVER A WORD OF A PROMPT: `panel.names(stratum, era)` for P4 and P5 (tickers by `NAME`, none
    twice; P6's names are `FACTORS`) and `panel.periods(stratum, era)` (period names of `periods(stratum, era)`, none
    twice). ValueError for a name or a period outside that: a plan that could put a figure in a prompt asks nothing.
    A stratum and era with no name or no period has no cell."""
    out = []
    for stratum in PANEL_STRATA:
        for era in ERAS:
            calendar = {name: (first, last) for name, first, last in periods(stratum, era)}
            every = [str(period) for period in panel.periods(stratum, era)]
            if len(set(every)) != len(every) or any(period not in calendar for period in every):
                raise ValueError(f"the panel plan's periods of {stratum}/{era} are not periods of the calendar, once each")
            names = list(FACTORS) if stratum == "P6" else [str(name) for name in panel.names(stratum, era)]
            if len(set(names)) != len(names) or (stratum != "P6" and any(not NAME.match(name) for name in names)):
                raise ValueError(f"the panel plan's names of {stratum}/{era} are not tickers, once each")
            chosen, asked = _grid(names, every, stratum, era, per_cell)
            for period in asked:
                for symbol in chosen:
                    out.append(_question(stratum, era, symbol, period, *calendar[period]))
    return out


def recall_questions() -> list[dict[str, Any]]:
    """R2021's 24 questions (SPY's total return a month, 2020-01..2021-12), shaped as `questions`' rows."""
    return [_question(RECALL, RECALL_ERA, AGAINST, name, first, last) for name, first, last in periods(RECALL, RECALL_ERA)]


def deep_questions(symbols: Mapping[str, str], *, per_cell: int) -> list[dict[str, Any]]:
    """Every question of the deep eras' cells (THE DEEP ERAS), shaped and ordered as `questions`' rows: strata
    `DEEP_STRATA`, then `DEEP_ERAS`, each a full grid under `_grid`'s one hash rule, on the universe's ETFs that have a
    deep history. Pure of prices: names and the deep calendar only."""
    from ..deep import config as deep_config

    out = []
    for stratum in DEEP_STRATA:
        for era in DEEP_ERAS:
            names = [s for s in stratum_symbols(symbols, stratum) if s in deep_config.DEEP_UNIVERSE]
            bounds = {name: (first, last) for name, first, last in periods(stratum, era)}
            chosen, asked = _grid(names, list(bounds), stratum, era, per_cell)
            for period in asked:
                for symbol in chosen:
                    out.append(_question(stratum, era, symbol, period, *bounds[period]))
    return out


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

    if dt.date.fromisoformat(day) < config.WINDOWS["train"][0]:  # THE DEEP ERAS: the deep store's truth, or none
        reader = getattr(store, "deep_close", None)
        return reader(symbol, day) if callable(reader) else None
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
def _count(value: Any) -> int:
    """A counter the file keeps (`probes`, `attempts`, `idle`): its integer, 0 for anything else."""
    return int(value) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _owing_eras(doc: Mapping[str, Any], eras: Sequence[str]) -> dict[str, Any]:
    """`doc` as `due` is shown it while the deep store is there: a route whose published result holds no cell of one
    of the deep `eras` reads as never published (its `at` left out), so it is due at once (as `_owing`)."""
    def whole(row: Mapping[str, Any]) -> bool:
        cells = row.get("cells") if isinstance(row.get("cells"), Mapping) else {}
        return all(any(isinstance(by, Mapping) and era in by for by in cells.values()) for era in eras)

    return {**doc, "routes": {key: (row if whole(row) else {k: v for k, v in row.items() if k != "at"})
                              for key, row in doc["routes"].items()}}


class _DeepTruth:
    """THE DEEP ERAS' TRUTH (the module docstring): adjustment=all closes rebuilt from the deep store's raw closes
    and events, one as-of chain for 2001-08 (the history and sealed spans) and one for 2009-15 (the open span), each
    read once a symbol. A deep store that cannot be read is `MissingData` (the run ends as for a store being
    rewritten). `store`: a league/deep/blocks.py `DeepStore` opened with the deep gate's capability."""

    def __init__(self, store: Any):
        self.store = store
        self._chains: dict[tuple[str, tuple[str, ...]], dict[str, float]] = {}

    def symbols(self) -> dict[str, str]:
        from ..deep import config as deep_config

        return {s: "etf" for s in deep_config.DEEP_UNIVERSE}

    def deep_close(self, symbol: str, day: str) -> float | None:
        from ..deep import blocks
        from ..equity.store import MissingData

        chain = ("history", "dval") if day <= "2008-12-31" else ("traind",)
        if (symbol, chain) not in self._chains:
            try:
                self._chains[(symbol, chain)] = blocks.as_of_closes(self.store, symbol, chain)
            except (blocks.DeepMissing, blocks.DeepRefused) as exc:
                raise MissingData(f"the deep store cannot be read ({type(exc).__name__})") from None
        return self._chains[(symbol, chain)].get(day)


def _owing(doc: Mapping[str, Any], strata: Sequence[str]) -> dict[str, Any]:
    """`doc` as `due` is shown it while a plan asks the panel `strata`: a route whose published result lacks one of
    them reads as never published (its `at` left out), so it is due at once. Nothing is written from this view."""
    def whole(row: Mapping[str, Any]) -> bool:
        cells = row.get("cells") if isinstance(row.get("cells"), Mapping) else {}
        return all(isinstance(cells.get(stratum), Mapping) and cells[stratum] for stratum in strata)

    return {**doc, "routes": {key: (row if whole(row) else {k: v for k, v in row.items() if k != "at"})
                              for key, row in doc["routes"].items()}}


class Probe:
    """One run of the job on one route (the module docstring), over what `run` opens: the swarm store (it books the
    dollars), the swarm's settings, the model router, the House's equity store opened with the gate's capability, and
    the universe. `clock` times the run for `ASK_SECONDS` (monotonic); the file's times are `ctx.now()`. `panel`:
    release E4's plan of the panel strata (THE PANEL STRATA: `names`, `periods`, `truths`, `published`), or None."""

    def __init__(self, ctx: Any, *, store: Any, settings: Mapping[str, Any] | None, router: Any, equity: Any,
                 symbols: Mapping[str, str], clock: Callable[[], float] = time.monotonic, panel: Any = None,
                 deep: Any = None):
        self.ctx = ctx
        self.root = Path(ctx.root)
        self.store = store
        self.settings = settings
        self.router = router
        self.equity = equity
        self.symbols = dict(symbols)
        self.clock = clock
        self.panel = panel
        self.deep = deep

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
        # THE PANEL STRATA, when a plan was handed in: its questions first (a plan that cannot be asked fails the run
        # before any route is marked), and a route whose result lacks a stratum they ask is due at once.
        further = panel_questions(self.panel, per_cell=c["questions_per_cell"]) if self.panel is not None else []
        asks = sorted({str(q["stratum"]) for q in further})
        # THE DEEP ERAS, while the House holds a deep store: asked after the panel's, a route lacking one due at once.
        deeper = deep_questions(self.symbols, per_cell=c["questions_per_cell"]) if self.deep is not None else []
        deep_eras = sorted({str(q["era"]) for q in deeper})
        view = _owing(doc, asks) if asks else doc
        view = _owing_eras(view, deep_eras) if deep_eras else view
        key = due(view, list(served), now=now, every_days=c["every_days"])
        if key is None:
            return {"status": "skipped", "why": "no route is due a probe"}
        room = float(elane_yield.room(self.store, self.settings, now))
        bound = round(min(float(c["usd_run"]), room), 6)  # THE BOUND: never more than E2's day has left
        if not bound > 0:
            return {"status": "skipped", "why": "E2's model dollars for the day are spent: no room for a probe "
                                                "(elane.e2.usd_day)"}
        route = served[key]
        row = dict(doc["routes"].get(key) or {})
        probe_n = 1 + _count(row.get("probes"))
        asked_of = questions(self.symbols, per_cell=c["questions_per_cell"])
        recall = recall_questions()
        mine = qset([*asked_of, *recall])   # E3's own questions and nothing of the panel's: its cells never move
        theirs = qset(further) if further else None
        deep_set = qset(deeper) if deeper else None
        partial = row.get("partial") if isinstance(row.get("partial"), Mapping) else None
        if partial is None or partial.get("qset") != mine or partial.get("probe_n") != probe_n \
                or not isinstance(partial.get("cells"), Mapping):
            partial = None  # another question set, or another probe's: dropped
        row.pop("partial", None)
        cells: dict[str, dict[str, Any]] = {s: dict(e) for s, e in ((partial or {}).get("cells") or {}).items()
                                            if isinstance(e, Mapping)}
        if theirs is None or (partial or {}).get("panel_qset") != theirs:
            for stratum in PANEL_STRATA:  # another panel question set, or no plan now: the PANEL cells are dropped
                cells.pop(stratum, None)
        if deep_set is None or (partial or {}).get("deep_qset") != deep_set:
            for by_era in cells.values():  # another deep question set, or no deep store now: the DEEP cells dropped
                for era in DEEP_ERAS:
                    by_era.pop(era, None)
        kept_recall = (partial or {}).get("recall") if isinstance((partial or {}).get("recall"), Mapping) else None
        before = _num((partial or {}).get("usd")) or 0.0
        answered_as = (partial or {}).get("model") if isinstance((partial or {}).get("model"), str) else None
        dearest = _num((partial or {}).get("batch_usd"))
        # FIRST the attempt: a route that cannot move goes to the back of the line, and THIS RUN'S KEYS are its own.
        attempt = 1 + _count(row.get("attempts"))
        row["attempts"] = attempt
        # Written once, never moved by a later attempt (a row of an earlier build: its last attempt is the oldest known).
        row.setdefault("first_attempted_at", row["attempted_at"] if _epoch(row.get("attempted_at")) is not None
                       else schedule.iso(now))
        row["attempted_at"] = schedule.iso(now)
        row["idle"] = _count(row.get("idle")) + 1
        def kept(usd: float, batch_usd: Any, model: Any) -> dict[str, Any]:
            """The partial as the file keeps it; `panel_qset` only while a plan asks (without one the file is E3's)."""
            held = {"probe_n": probe_n, "qset": mine, "usd": round(usd, 6), "batch_usd": batch_usd, "model": model,
                    "cells": cells, "recall": kept_recall}
            if theirs is not None:
                held["panel_qset"] = theirs
            if deep_set is not None:
                held["deep_qset"] = deep_set
            return held

        if partial is not None:
            row["partial"] = kept(before, dearest, answered_as)
        doc["routes"][key] = row
        self.write(doc)

        began = self.clock()
        state: dict[str, Any] = {"spent": 0.0, "asked": 0, "stopped": None, "error": None, "model": answered_as,
                                 "scored": 0, "dearest": dearest}

        def save() -> None:
            row["partial"] = kept(before + state["spent"], state["dearest"], state["model"])
            doc["routes"][key] = row
            self.write(doc)

        def left() -> float:
            """The dollars this run may still spend: its bound, and E2's day as it stands NOW (the swarm's own equity
            questions spend the same line meanwhile)."""
            return min(bound - state["spent"], float(elane_yield.room(self.store, self.settings, now)))

        def ask(batch: Sequence[Mapping[str, Any]]) -> list[Any] | None:
            """One batch's answers, or None once the run stopped asking (`state["stopped"]` says why)."""
            if round(state["spent"], 6) >= bound or not left() > 0:  # THE BOUND
                state["stopped"] = "usd"
                return None
            if self.clock() - began >= ASK_SECONDS:
                state["stopped"] = "time"
                return None
            system, user = prompt(batch)
            call = f"{KEY_PREFIX}:{route.key}:{probe_n}:{attempt}:{_digest(user)[:12]}"
            if elane_yield.booked_for(self.store, call) > 0:
                # A KEY IS ASKED ONCE: the swarm's spend rows already carry this one (the file's counters began again).
                # The router would answer it from the Provider's stored row, at that row's cost and maybe blanked.
                state["stopped"] = "error"
                state["error"] = (f"a request key of probe {probe_n}, run {attempt} was booked before: it is not asked "
                                  "again (the next run's keys are new)")
                return None
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
            text = answer.get("text") if isinstance(answer, Mapping) else None
            said = isinstance(text, str) and bool(text.strip())
            elane_yield.book(self.store, f"probe:{route.key}", usd=usd, known=known, purpose="probe", answered=said,
                             now=now)
            state["spent"] += usd
            state["dearest"] = round(max(usd, state["dearest"] or 0.0), 6)
            if not said:
                # NO TEXT IS NO ANSWER: a call that produced nothing (or a stored row whose response was blanked) is
                # never read as a batch of skipped items. Its dollars are booked; the next run asks under new keys.
                state["stopped"], state["error"] = "error", f"route {route.key} answered a batch with no text"
                return None
            state["asked"] += 1
            if isinstance(answer.get("model"), str) and answer["model"]:
                state["model"] = answer["model"]
            return parse(text, batch)

        def cell(batch_of: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
            """A cell's aggregates once all its batches are in: answers first, then its truths (dropped with them)."""
            # A CELL IS BEGUN ONLY WHEN THE RUN CAN PAY FOR IT: a stop inside a cell costs its batches again next run.
            batches = -(-len(batch_of) // c["batch"])
            if state["dearest"] and round(batches * state["dearest"], 6) > round(left(), 6):
                state["stopped"] = "usd"
                return None
            answers: list[Any] = []
            for i in range(0, len(batch_of), c["batch"]):
                got = ask(batch_of[i:i + c["batch"]])
                if got is None:
                    return None
                answers.extend(got)
            stratum = str(batch_of[0]["stratum"])
            try:
                if stratum in PANEL_STRATA:
                    # THE PLAN'S TRUTHS, a cell at once (it reads the panel store). One outside the stratum's words
                    # is no truth; a plan that fails here ends the run as a store being rewritten does (the dollars
                    # of the cell are booked; the next run asks it again).
                    try:
                        truths = list(self.panel.truths(batch_of))
                    except (MissingData, StoreRefused):
                        raise
                    except Exception as exc:  # noqa: BLE001 - the plan's own fault: never a scored cell
                        state["stopped"], state["error"] = "data", f"the panel plan: {type(exc).__name__}: {str(exc)[:140]}"
                        return None
                    if len(truths) != len(batch_of):
                        state["stopped"], state["error"] = "data", "the panel plan gave no truth a question"
                        return None
                    truths = [t if isinstance(t, str) and t in (*WORDS[stratum], "tie") else None for t in truths]
                else:
                    source = self.deep if str(batch_of[0]["era"]) in DEEP_ERAS else self.equity
                    truths = [truth(source, q) for q in batch_of]
            except (MissingData, StoreRefused) as exc:  # the store is being rewritten: what is scored so far stays
                state["stopped"], state["error"] = "data", f"{type(exc).__name__}: {str(exc)[:160]}"
                return None
            return score(batch_of, answers, truths)

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for q in [*asked_of, *further, *deeper]:  # E3's cells first, then the panel's, then the deep eras
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
            if self.panel is not None:
                try:  # THE LOOK'S PERMIT is the plan's to write; the result above is published whatever it does
                    self.panel.published(doc)
                    permit = True
                except Exception as exc:  # noqa: BLE001
                    permit = False
                    self.ctx.alert("warning", f"the contamination probe published route {key} and its plan could not "
                                              f"write the look permit ({type(exc).__name__})")
        elif state["spent"] > 0 or "partial" in row:
            save()  # the dollars so far stay with the probe they bought
        if row["idle"] >= IDLE_ALARM:
            self.ctx.alert("warning", f"CP2: the contamination probe's route {key} added no cell in its last "
                                      f"{int(row['idle'])} attempts")
        out = {"route": key, "probe": probe_n, "usd": round(state["spent"], 6), "bound": round(bound, 6),
               "finished": finished, "cells": state["scored"], "asked": state["asked"], "stopped": state["stopped"]}
        if state["error"]:
            out["error"] = state["error"]
        if self.panel is not None:
            out["panel"] = len({(q["stratum"], q["era"]) for q in further})
            if finished:
                out["permit"] = permit
        return out


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (the module docstring; league/ops/registry.py), as release E3 built it: no panel stratum. The receipt:
    {"route", "probe" (its number), "usd", "bound" (the run's dollars at most), "finished", "cells" (scored this
    run), "asked", "stopped" ("usd" | "time" | "error" | "data" | "fallback" | None)} and, when a call or the store
    failed or another profile answered, "error"."""
    return probe(ctx)


def probe(ctx: Any, *, panel: Callable[..., Any] | None = None) -> dict[str, Any]:
    """THE JOB, with or without the panel strata. `panel`: None (`run`), or a plan's maker, asked ONCE THE HOUSE'S
    OWN STORE IS OPEN AND BEFORE ANY ROUTE IS MARKED: `panel(ctx, settings, capability, periods=periods,
    eras=tuple(ERAS))`, with the swarm's settings, the gate's capability this job minted (under `GATE_REASON`: the
    one capability of a run) and this module's own calendar (the maker imports nothing of this module). It answers a
    plan; None (no panel stratum this run: the probe is E3's); or a receipt (a dict with "status": the job ends
    with it, as where the panel's work could meet a wall). A `MissingData` or `StoreRefused` it raises (a panel
    store that cannot be read) fails the job there. In each of those no route is marked and no dollar spent. The
    receipt is `run`'s, with `panel` and `permit` beside (THE PANEL STRATA)."""
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
        capability = mint_equity_gate_capability(root / STORE_DIR, GATE_REASON)
        equity = EquityStore(root / STORE_DIR, gate=capability)
    except (MissingData, StoreRefused) as exc:
        return {"status": "failed", "error": f"the equity store cannot be read ({type(exc).__name__}): {str(exc)[:200]}"}
    deep = None
    from ..deep import blocks as deep_blocks
    from ..deep import config as deep_config
    from ..deep import gate as deep_gate

    try:  # THE DEEP ERAS only with a deep store whose audit passed (league/ops/equity_deep.py); else E3's probe
        found = deep_blocks.DeepStore(root / deep_config.STORE_DIR)
    except deep_blocks.DeepMissing:
        found = None
    if found is not None and found.audit().get("ok"):
        try:
            cap = deep_gate.mint_deep_gate_capability(root / deep_config.STORE_DIR, DEEP_GATE_REASON)
            deep = _DeepTruth(deep_blocks.DeepStore(root / deep_config.STORE_DIR, gate=cap))
        except (deep_blocks.DeepMissing, deep_blocks.DeepRefused) as exc:
            return {"status": "failed", "error": f"the deep store cannot be read ({type(exc).__name__})"}
    plan = None
    if panel is not None:
        try:
            plan = panel(ctx, settings, capability, periods=periods, eras=tuple(ERAS))
        except (MissingData, StoreRefused) as exc:
            return {"status": "failed", "error": f"the panel store cannot be read ({type(exc).__name__}): {str(exc)[:200]}"}
        if isinstance(plan, Mapping):
            return dict(plan)  # the maker's own receipt: nothing was opened for a route
    from ..swarm.models import build_router
    from ..swarm.store import SwarmStore

    store = SwarmStore(root)
    try:
        router = build_router(root, store, settings, config=ctx.config)
        out = Probe(ctx, store=store, settings=settings, router=router, equity=equity,
                    symbols=equity_data.universe(), panel=plan, deep=deep).run()
    finally:
        store.close()
    if plan is not None and "permit" not in out:
        try:  # nothing was published this run: the permit is made again from the file as it stands, all the same
            plan.published(read(root))
        except Exception as exc:  # noqa: BLE001 - the next run writes it again
            ctx.alert("warning", f"the contamination probe's plan could not write the look permit ({type(exc).__name__})")
    return out


__all__ = ["FILE", "VERSION", "GATE_REASON", "ERAS", "STRATA", "PANEL_STRATA", "FACTORS", "FACTOR_WORDS", "NAME",
           "RECALL", "RECALL_MONTHS", "ROLE", "SYMBOLS_PER_CELL",
           "PERMUTATIONS", "ASK_SECONDS", "READABLE_ANSWERED", "READABLE_PERIODS", "ALPHA", "HISTORY", "MODES",
           "DEFAULTS", "BOUNDS", "SYSTEM", "KEY_PREFIX", "AGAINST", "WORDS", "RECALL_ERA", "IDLE_ALARM", "JUDGED_ERAS", "CELL_KEYS",
           "RECALL_KEYS", "DEEP_ERAS", "DEEP_STRATA", "DEEP_GATE_REASON", "cfg", "mode", "periods", "stratum_symbols",
           "grid", "questions", "panel_questions", "deep_questions", "recall_questions", "qset", "truth", "prompt", "parse", "wilson", "perm_p", "score", "read", "due", "Probe",
           "run", "probe"]
