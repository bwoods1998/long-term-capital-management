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

THE JOB (`run`): skipped when the mode is "off", no route is due (`due`), or `elane_yield.room(store, settings, now) <
usd_run`. One route a run: `router = models.build_router(ctx.root, store, settings, config=ctx.config)`; routes =
`elane_yield.routes(settings, router)`. FIRST it writes the route's `attempted_at` and `idle` + 1 (`idle`: its
attempts in a row that added no cell; a cell written sets it to 0), so a route that cannot move goes to the back of
the line and never blocks the others. `probe_n` = 1 + the route's `probes` (its completed probes, a counter never
truncated). Cell by cell in a fixed order, then the recall: each batch `elane_yield.ask_on(router, route, role=ROLE,
system=SYSTEM, user=..., key=KEY, max_output=2000, effort="low")` with `KEY = f"contam:{route.key}:{probe_n}:{h}"`, h =
the first 12 hex of sha256(the batch's user text); booked `elane_yield.book(store, f"probe:{route.key}", usd=...,
known=..., purpose="probe", answered=..., now=now)` (rows of their own, inside E2's day line; that function counts a
purpose it does not name under `usd_research`). THE KEY: the Provider answers a request key it has seen from its
store, at $0. So a resumed probe (the same `probe_n`) re-reads its own batches for nothing; a new probe (`probe_n` +
1) asks afresh and is billed; a batch whose questions changed has another hash and never meets an old answer. A cell
whose batches are all in is scored and written at once to `routes[route].partial` (aggregates only, with `probe_n`,
`qset` and the dollars so far); a partial with another `qset` is dropped. The run stops asking once its booked
dollars reach `usd_run` or `ASK_SECONDS` have passed; the next run of that route goes on from the partial. When every
cell and the recall are in, the result is published (`at`, `model`, `usd`, `cells`, `recall`), `probes` + 1, `idle` 0,
`partial` removed, `history` appended. Truths and answers are dropped before every write. A `MissingData` (the store
being rewritten) ends the run with the cells already scored kept and the billed dollars booked.

SETTINGS (`cfg`, `mode`): `elane.contam.*` (`DEFAULTS`, `BOUNDS`); a malformed value is its code default; an
unreadable block is "off". The receipt holds `route`, `usd` and `finished`. Standard library and numpy only.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Sequence

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


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane.contam` in the swarm's settings: every key of `DEFAULTS`, each value inside its bound; a malformed value
    is its code default; an unreadable block is `DEFAULTS` (mode "off")."""
    raise NotImplementedError("E: league/ops/contam_probe.py cfg")


def mode(settings: Mapping[str, Any] | None) -> str:
    """`cfg(settings)["mode"]`: "off" | "record"."""
    raise NotImplementedError("E: league/ops/contam_probe.py mode")


def grid(symbols: Mapping[str, str], stratum: str, era: str, *, per_cell: int) -> tuple[list[str], list[str]]:
    """D16's full grid of one cell: (its K symbols, its P periods), each in hash order. `symbols`: {symbol: class}
    (the House universe); a month period is "YYYY-MM", a week period the ISO day it ends on."""
    raise NotImplementedError("E: league/ops/contam_probe.py grid")


def questions(symbols: Mapping[str, str], *, per_cell: int) -> list[dict[str, Any]]:
    """Every question of every cell, in a fixed order: {"id", "stratum", "era", "symbol", "against", "first", "last",
    "period", "text"}. Pure of prices: names and the calendar only."""
    raise NotImplementedError("E: league/ops/contam_probe.py questions")


def recall_questions() -> list[dict[str, Any]]:
    """R2021's 24 questions (SPY's total return a month, 2020-01..2021-12), shaped as `questions`' rows."""
    raise NotImplementedError("E: league/ops/contam_probe.py recall_questions")


def qset(questions: Sequence[Mapping[str, Any]]) -> str:
    """The sha256 of the questions' ids, in order: a partial made on another set is dropped."""
    raise NotImplementedError("E: league/ops/contam_probe.py qset")


def truth(store: Any, question: Mapping[str, Any]) -> str | float | None:
    """A question's truth from the House's store (`EquityStore` with the capability): "higher" | "lower" (S1), "more"
    | "less" (S2-S4), the percent return (R2021), "tie" for a zero, None when a price is missing. Never written."""
    raise NotImplementedError("E: league/ops/contam_probe.py truth")


def prompt(batch: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    """(`SYSTEM`, the user text) of one batch of questions: numbered items, no truth, no score, no price."""
    raise NotImplementedError("E: league/ops/contam_probe.py prompt")


def parse(text: Any, batch: Sequence[Mapping[str, Any]]) -> list[Any]:
    """The batch's answers from a model's reply, one an item in order (None for an item not answered, or for all when
    the reply is not a JSON array)."""
    raise NotImplementedError("E: league/ops/contam_probe.py parse")


def wilson(k: int, n: int) -> tuple[float, float]:
    """The Wilson 95% interval (lo, hi) of k of n ((0.0, 1.0) when n is 0)."""
    raise NotImplementedError("E: league/ops/contam_probe.py wilson")


def perm_p(answers: Sequence[Any], truths: Sequence[Any], periods: Sequence[str], *, seed: str) -> float:
    """D16's p_perm of one cell: answers and truths a question, `periods` each question's period; the cell's periods
    are permuted whole, `PERMUTATIONS` times, seeded by `seed`."""
    raise NotImplementedError("E: league/ops/contam_probe.py perm_p")


def score(questions: Sequence[Mapping[str, Any]], answers: Sequence[Any], truths: Sequence[Any]) -> dict[str, Any]:
    """One cell's aggregates (the module docstring): {n, correct, ties, skipped, periods, symbols, acc, base, m, lo,
    hi, p_perm, readable, recalled}; for R2021's questions {n, rho, p_perm, sign_acc}. Never a per-question row."""
    raise NotImplementedError("E: league/ops/contam_probe.py score")


def due(doc: Mapping[str, Any] | None, routes: Sequence[str], *, now: float, every_days: float) -> str | None:
    """The route to probe now, None when none is due. Among the routes with no result or one older than `every_days`:
    first a route whose probe is under way and moving (a `partial`, `idle` 0), the oldest `attempted_at` first, so a
    probe that costs more than one run's dollars finishes in the next weeks; then the one whose max(`at`,
    `attempted_at`) is oldest (never tried first)."""
    raise NotImplementedError("E: league/ops/contam_probe.py due")


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (the module docstring; league/ops/registry.py). The receipt: {"route", "usd", "finished", "cells"
    (scored this run), "asked", "stopped" ("usd" | "time" | None)}."""
    raise NotImplementedError("E: league/ops/contam_probe.py run")


__all__ = ["FILE", "VERSION", "GATE_REASON", "ERAS", "STRATA", "RECALL", "RECALL_MONTHS", "ROLE", "SYMBOLS_PER_CELL",
           "PERMUTATIONS", "ASK_SECONDS", "READABLE_ANSWERED", "READABLE_PERIODS", "ALPHA", "HISTORY", "MODES",
           "DEFAULTS", "BOUNDS", "SYSTEM", "cfg", "mode", "grid", "questions", "recall_questions", "qset", "truth",
           "prompt", "parse", "wilson", "perm_p", "score", "due", "run"]
