"""THE EQUITY TRAIN (release E2, Oct 2026): the bar the swarm's own share programs meet on Train before their one
Validation try (equity-v1), the Train runs on the House, the equity review at the first pass, the equity TRAIN MAP the
architect reads, and the minimal equity researcher that writes and revises a family's program on Train alone.

THE TRAIN YEARS (amendment A15). E2's Train is the TRAIN SPANS (`TRAIN_SPANS`): 2016-01-04..2019-12-31 and
2022-01-03..2024-12-31, seven years (`TRAIN_YEARS`). A version's Train run is two runs of E1's isolated runner
(`league.equity.runner.Isolated.train(start, end)`, one a span: the program in the decider child, never in the swarm
process), each starting flat, SUMMED (`combine`). 2020-2021 is THE RESERVE (`RESERVE_YEARS`), kept for a later
accessor: no E2 run has a session in it, and a result carrying a row of a day outside its own span (a 2020 or 2021 row
exactly as a 2025 or 2026 one: a by-year row, a daily row, a trade's, a lot's or a booked dividend's day, its start or
end) is refused whole and judged on nothing (WINDOW). No 2020-2021 session is ever a run session, so no 2020-2021
figure or P&L exists to reach a family's record, the Train map, the yield ledger or a generator. WHAT OF THE RESERVE
DOES REACH TRAIN, stated: its BARS, as look-back. The 2022-2024 run's decisions read the bars before 2022-01-03 as
history (NEEDS `history` + 1 sessions, the first decision's own session among them: E1's `store._slice`; up to
`league.equity.config.MAX_HISTORY` + 1, so back into 2020), as a Validation run looks back on 2024's. So a program
with look-back has 2022-2024 Train figures that are functions of reserve bars (directly while its look-back still
reaches before 2022-01-03, at most two years; after that only through the lots, cash and equity the run carries), and
so are the sums and the pooled t they enter. Its 2016-2019 figures are not. EVEN A PROGRAM WITH NO LOOK-BACK READS THE
LAST 2021 SESSION: the 2022-2024 run's first decision is at that session's close, so its bar is in every program's
slice (one reserve bar at least, never none), and the buy-and-hold reported beside 2022 is measured from that close. E2
blanks nothing: a blanked look-back would need a hook in E1's runner
or store and would cost a long-look-back program most of 2022 (the captain's call, with the later accessor).
THE LOOSENING, stated: the bar reads seven Train years, not the nine of 2016-2024, so "active in three years" is three
of seven, "no year's t below the floor" has two years fewer to fail in, and the two P&L rules sum seven years.

THE BAR, equity-v1 (the design's section 6b on the Train years; `train_score`, then `restart_check`, then
`start_check`). The summed runs at 1.0x and at 1.5x the half-spread (`league.equity.config.K_BASE`, `K_STRESS`). A
version PASSES when all hold:
  Y1  ACTIVE in at least `min_active_years` (3) of the seven Train years: a year with at least `year_min_trades` (40)
      closed lots and `year_min_days` (20) entry days, on the 1.0x runs;
  Y2  no Train year's t (the year's daily P&L t, `by_year.t_daily`; a flat year reads 0) below `year_t_floor` (-1.0),
      on the 1.0x runs;
  P1  the 1.5x runs' net P&L over Train above zero;
  R1  the 1.0x net P&L above zero and the 1.5x P&L at least `cost_ratio` (0.5) of it;
  STATE  (checked once Y1-R1 hold) the program run again with its STATE emptied every `state_every` (20) sessions
      gives the uninterrupted run's intents on at least `state_match` (99%) of the Train sessions (THE RESTART CHECK
      below). The House's decider child restarts on every deploy and a restart empties a program's memory: a program
      whose decisions hang on STATE beyond a cache of what ctx gives again would trade live other than its replay
      (and so would one whose decide fails once its STATE is gone).
  START  (release E2.1; checked once STATE holds) each Train span run again from `start_shifts` (61 and 127) decision
      sessions in, every run starting flat, gives the orders of the run from the span's first session on at least
      `start_match` (99%) of each later run's compared sessions, and on at least `start_active` (95%) of those on
      which either run asked an order (THE START CHECK below). The House starts every program live on a fresh date,
      and every judged window starts flat: a program whose decisions depend on when its run started (a profit lock, a
      size from the run's own standing, a clock counted from its first trade) trades live other than its replay, and
      the share screen's false-positive line does not hold for it.
REPORTED BESIDE, NEVER A BAR: the same-exposure buy-and-hold over the same sessions (`bh.pnl`), the mean
time-matched excess (MTE: `mte.mean`, `mte.t`) and the DRIFT SHARE (the buy-and-hold P&L over the program's, while
the program's is above zero: near one, the program earned what holding its average exposure earned). Every number
here is a Train figure. The bar's constants are rules (`BAR`), never a market result.

THE RESTART CHECK (`restart_check`, `state_inputs`). E1's decider child keeps a loaded program instance across "decide"
requests (the live path's hooks: `kind_load`, `kind(..., "decide", ...)`, `kind_drop`), so an instance's STATE lives
until it is dropped. For each Train span two instances of the version are loaded: A, never reset, and B, dropped and
loaded fresh every `state_every` sessions. At every decision session of the span both read THE SAME ctx (`state_inputs`:
E1's Gym inputs over the span's own 1.0x run: its bars, its open lots marked at the close, the lots it closed that
session, its cash, equity and caps), so only the program's own memory can make their answers differ. A failed STATE
check is the program's ("STATE": like DQ, LOAD, RUN and REVIEW it judges a program, not the mechanism).
  THE RESETS ARE OFF THE SPAN'S START. B is loaded with A at the span's first session, emptied again `state_first`
  (7) sessions in, and then every `state_every` (20): at decision sessions 7, 27, 47 and on. Were B's resets counted
  from the first session, where A starts too, a session counter whose period divides 20 (a weekly clock of 5, or 2, 4,
  10, 20) would stay in phase with its reset twin on every session and pass; a deploy restarts a live clock at any
  session. With 7 and 20 a counter of any period above one falls out of phase with its twin (7 + 20k is a multiple of
  a period p for every k only when p is 1).
  WHAT MATCHES (`same_intents`). A session matches when the two decides ENDED ALIKE: the same orders in the same
  order (each buy's symbol, fill point and tag, each sell's lot, each cancel's order), every buy the same size, and the
  same count of errors in that call (`stats.errors`: an exception, a timeout, a malformed intent). A decide that
  raises because STATE was emptied answers nothing, as the uninterrupted one may: the intents alone would agree, and
  live the House exits a program's lots after two failed decides in a row (EQUITY.md), so the error counts are
  compared too and such a session is no match (`failed`). Two buys are THE SAME SIZE within `SIZE_TOL`: one part in a
  million of the sleeve for a `share` (six places, the engine's `QTY_PLACES`), a cent for `usd`; so a cache that holds
  the value ctx gives, summed in another order, matches (floating-point noise in the last digits is no memory).
  Anything larger is a difference: a value CARRIED from session to session and updated in place (a running sum, an
  average, a peak) drifts from what ctx gives now, because ctx's history is adjusted as of each session and rounded;
  such a version fails STATE, and its record says how many sessions differed in a buy's size alone and by how much
  (`sized`, `size_gap`), so its brief can say so. A session an instance was disqualified at (its own errors) matches
  nothing.
NEVER A SILENT PASS: the check holds only on sessions it really compared. Each answer's `stats.calls` (E1's runner
counts an instance's decides) must be the number of decides that instance was asked since it was loaded: an instance
the child reloaded (a restart, counted by the decider's `restarts` or not) has lost its memory, and the check stops.
A check that cannot run or finish (no decider on the runner, an answer without the call count or the error count, a
reloaded or missing instance, a ctx that cannot be built, a span with no session) is the House's: the version is not
scored, and its `train_max_errors`-th such failure with no judgment of the version in between is an alert, once. A
child that fails a decide is judged as a run's failure is.

THE START CHECK (`start_check`, `later_runs`, `start_run`; release E2.1). A program's decisions must not depend on WHEN
its run started. THE HOLE IT CLOSES: a program can stop or shrink its trading once its own run is ahead (a profit
lock). E1's screen builds a program's floor from slices of long Train runs, which start flat once, while Validation
and the sealed look each start flat; so a lock passes a positive-sum, t-above-a-floor screen far more often than the
screen's stated rate. The static rule refuses the spellings it can follow and the paid readers' rubric names the
pattern; this check runs the program and looks.
  THE RUNS. For each Train span: run A, the bar's own 1.0x run from the span's first session, and one later run a
  shift of `start_shifts` (61 and 127: two different primes, so a clock of any period above one is out of phase with
  run A in at least one of them), each one more run of E1's isolated runner (`Isolated.train(start, end)`), starting
  FLAT on the session after run A's decision number `shift` and ending with the span. Four more runs a version at the
  spans' real lengths; they are the check's, kept in no record and stored as no run. Then one instance a run is
  loaded through E1's decider kinds, never reset, and at every decision session each decides on ITS OWN run's ctx
  (`state_inputs` over that run: its bars, its own lots, cash, equity and caps).
  WHAT IS COMPARED. A later run's session is compared with run A's same session (a) once the later run has WARMED UP:
  its own first max(NEEDS `history`, NEEDS `max_hold_sessions`) + `start_warm` (20) decision sessions are behind it
  (run A may hold lots a fresh run does not; they are gone inside the maximum hold); and (b) BEFORE that, only where
  the two runs show their program THE SAME BOOK (`same_book`: the same open lots, each by symbol, fill point, sessions
  held, entry price and mark, and the same lots closed since the last call; never a lot's id, quantity, value, pnl or
  tag). With the same bars, calendar and book, nothing but the run's own standing (its equity, cash and caps, its
  lots' ids, sizes and tags, its memory) can make the two decides differ, so such a session is held to run A from the
  later run's first decision. Without (b) a lock that closes inside the warm-up was invisible, and a program chose its
  own warm-up by declaring a long `history`.
  WHAT MATCHES (`start_orders`, then the restart check's `same_intents`). The same list of orders in the same order:
  each order's kind, symbol and fill point; a buy's `share` or `usd` within `SIZE_TOL`; a sell names its lot's
  symbol (two runs number their lots apart); tags are ignored (a program's own words). A decide that failed in one run
  and not the other, and a session an instance was disqualified at, match nothing, as in the restart check.
  THE RULE. A version passes START when EVERY later run matches run A on at least `start_match` (99%) of its compared
  sessions AND on at least `start_active` (95%) of those on which either run asked an order (a program that trades
  once a month asks nothing on nineteen sessions in twenty: read on all sessions alone, a fifth of its trades could
  differ inside the 1%); else it fails the bar with the code START: the program's fault, like STATE (it judges a
  program, not the mechanism, so it refutes nothing and spends no Validation try). Its record keeps the counts by
  later run and the sessions that differed, counted from the later run's own first decision (never a day), and what
  the two runs asked where they first differed; the next brief says so and says what a program may decide from
  (`start_text`).
  WHAT FITS (`start_plan`). A shift is used in a span that leaves its later run at least `start_min` (120) warmed-up
  sessions; a span too short for a shift goes without it and the record says so (`skipped`). On the Train spans
  (1,006 and 753 sessions) the 61-session start fits every program the contract allows; the 127-session start does
  not fit 2022-24 for a program with `history` above 486.
  NEVER A SILENT PASS, as the restart check (`_decided`, the two checks' one reader). A check that cannot run or finish
  (no decider, a reloaded or missing instance, a decider that restarted, a later run that ended in no result or does
  not share its span's sessions, spans that fit no later start) is the House's (`StartCheckInterrupted`): the version
  is not scored, and its `train_max_errors`-th such failure since it was last judged is an alert, once
  (`elane_train_start`). A child that fails a later run or a decide is judged as a run's failure is.
  A PASS JUDGED BEFORE THIS CHECK EXISTED (a verdict with no `start` record) is not current until its version has had
  its Validation try: it is Train-scored again before E1 may validate it (`pass_current`).
  WHAT IT COSTS, AND WHAT IT DOES NOT CATCH: league/swarm/ELANE_E2.md, section 3.

WHAT A VERDICT IS (`score`). Only the PROGRAM's own doing is judged: its runs finished ("ok": the bar), it was
disqualified by its own errors or timeouts ("DQ"), the child refused to load it ("LOAD": a `ProgramRefused`, a
`CodeRefused` or a `NeedsRefused`), the child failed its run (or its restart check's decides) `train_max_errors` times
in a row while other programs' Train judgments completed after the first of those failures ("RUN"), its intents
changed when its STATE was emptied ("STATE"), or its orders changed with the day its run started ("START"). Anything
else is the House's (no equity store yet, the store being rewritten, a decider child that could not start, a restart
check or a start check that could not run or finish, a result outside the Train years, "no_data"): the version is NOT
scored, spends no budget and asks no model; it is tried again after a backoff (`train_every_seconds` doubling with
every failure of any kind, at most `BACKOFF_MAX`); a result outside the Train years is also an alert, and so is a
restart check or a start check that could not finish `train_max_errors` times. THE HOUSE'S FAILURES ARE COUNTED BY
KIND (`house_failure`; the record's `infra`): "in a row" for RUN means the child's failures of this version one after
another, so a failure of another kind in between (a restart check the House interrupted, whose attempt ran the
version's Train runs through; a store being rewritten) starts the row again and never counts toward RUN; the restart
check's alert and the start check's each count that kind's failures since the version was last judged, whatever came
between, and each is sent once. Of the verdicts, only Y1, Y2, P1 and R1 judge the MECHANISM (`JUDGED`); the others
judge a program that could not be judged.

THE REVIEW (league/swarm/elane_review.py). A program holding a raw price or volume level against a constant or a PARAMS
value is refused before it is stored (`check_code`), and so is one that reads its own profit since the run began: the
sleeve's dollars against a constant, the run's capital or what a lot cost (the level rule's 1b and 1d). At a version's first bar pass two different models read it under
the leakage rubric (`EquityResearcher.review_step`) before it may be its lineage's Validation try: a pass of both
writes the record E1's look reads (`state["review"]`) and makes it the family's pass; a failure is a Train failure of
that version ("REVIEW") and spends no try.

THE RECORD (family state `STATE_KEY`, E2's own; `record_of`). Per version: its verdict, its fails, its Train figures,
its restart check's counts (`state`), its start check's (`start`) and the equity identity it was judged under
(`identity`); the family's `status` ("researching", "passed", "refuted", "stalled", "closed"), `passed_version`, a
pending `review`, the `passed_review`
(E2's copy of the record E1 reads), its write `attempts`, its `refused` programs and an `infra` backoff. The FIRST
version that passes the bar AND the review ends the family's Train research: it is the lineage's one Validation try
(`may_validate`, the guard E1's tournament applies: ELANE_E2_PATCHES.md patch 5; the family's `best_version` and
`best_train` are set to it). A family whose Train budget (`train_budget` scored versions, 4) or attempts
(`train_max_attempts`) are spent with no pass, or whose researcher stops after a judged version, is RETIRED: REFUTED
on Train (a graveyard row in E2's own words, Train facts only, and its record's `refuted`) when at least one version
was judged on the bar, else STALLED (no graveyard row, no cell count: no program of it could be judged, which says
nothing of the mechanism). The equity generators read the record, never the graveyard table.

THE IDENTITY (`identity`; E1's `evaluator.equity_identity`). Each verdict carries the identity it was judged under. A
pass judged under another identity, whose version has not had its Validation try, is Train-scored again before E1 may
validate it (`pass_current`): passed again it stands; failed, the pass is withdrawn and the research goes on. E1's
adoption clears `best_version` and the review state; the round restores both for a pass that stands (`upkeep`).

THE EQUITY TRAIN MAP (`train_map`, `train_map_text`). The cells (lane x agenda mechanism x universe group: `cell_of`)
of every E2 family, alive or retired, with its births, the families Train-scored, passed, refuted on Train and stalled,
and the best passing pooled Train t (one decimal), labelled IN-SAMPLE everywhere (`MAP_LABEL`). Computed on the House
from E2's own records at each request: never a committed figure, never a census figure, never a Validation or look
outcome (A9 D3: a family's later fate does not move its row). A cell with `refuted_cell_cap` (3) refutations (each with
a judged version) and no pass is CLOSED (`closed_cells`): the equity pass refuses a birth there.

THE RESEARCHER (`EquityResearcher`; minimal by design). A round (`run`; every `train_every_seconds`, at most
`train_per_round` families, the least recently worked first) gives each E2 family one step: re-score a stale pass, or
review a bar pass, or Train-score its newest version, or write its first program or a revision on its birth route, or
retire it. The question (`brief`) holds the family's card and agenda prior, EQUITY.md, the bar, and its own versions'
Train figures, fails and review reasons, nothing else (league/swarm/elane_seal.py). A program is checked statically
before it is stored (`league.gym.safety.check_program`; NEEDS a literal dict whose symbols are the family's own; the
level rule), and its PARAMS are its declaration's (a version's params are {}). A `stop` answer before any version was
judged on the bar is not accepted (it counts as an attempt).

With `elane.mode` "off" nothing here acts; nor does anything while no family of E2's exists (`EquityResearcher.due`:
the births were never on), so `elane.birth_share` zero from the start keeps this module silent too. Once families were
born, `elane.birth_share` zero stops the births only: the families already born finish their Train research inside
`elane.e2.usd_day` (zero there asks no model). Standard library only.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import math
import re
import time
from typing import Any, Callable, Iterable, Iterator, Mapping, NamedTuple, Sequence

from ..equity import BETA, EQUITY, LANES
from ..equity import config as eqconfig
from . import elane_review, elane_seal, elane_yield

# ----------------------------------------------------------------------------------------------------------- vocabulary
OBJECTIVE = "equity-v1"
#: E2's family-state key (its own Train record).
STATE_KEY = "elane_e2"
#: The store's kv key of the researcher's last round.
TRAIN_AT_KEY = "elane_e2_train_at"
#: The store's kv key of the last time any E2 Train judgment completed (its runs and, where it had one, its restart
#: check): a child that fails one program while this moves on is that program's fault ("RUN").
TRAIN_OK_KEY = "elane_e2_train_ok_at"
#: The longest backoff after a failure of the House's (no store, a child that could not start, a result outside Train).
BACKOFF_MAX = 6 * 3600.0
#: How often `EquityResearcher.due` looks again while no round has work (a look reads the equity families; it writes
#: nothing), and the kv key of the equity pass's clock (league/swarm/elane_births.py `BIRTHS_AT_KEY`): a pass since the
#: last look is looked at at once, so a family's first Train round never waits on the look.
IDLE_LOOK_SECONDS = 30.0
BIRTHS_AT = "elane_e2_births_at"
#: The store's kv key of the last alert of a standing House failure, by kind ({"run": epoch, "store": epoch}).
HOUSE_ALERT_KEY = "elane_e2_house_alert_at"
#: E1's TRAIN WINDOW (league/equity/config.py WINDOWS["train"]): the outer bounds of the spans below.
TRAIN_FIRST, TRAIN_LAST = eqconfig.WINDOWS["train"][0], eqconfig.WINDOWS["train"][1]
#: THE TRAIN SPANS (A15; the module docstring): the only sessions an E2 run has, each span one run starting flat.
TRAIN_SPANS: tuple[tuple[dt.date, dt.date], ...] = ((dt.date(2016, 1, 4), dt.date(2019, 12, 31)),
                                                    (dt.date(2022, 1, 3), dt.date(2024, 12, 31)))
#: THE RESERVE (A15): no E2 run has a session in these years, and a result row of one is refused whole.
RESERVE_YEARS = (2020, 2021)
TRAIN_YEARS = tuple(y for first, last in TRAIN_SPANS for y in range(first.year, last.year + 1))
#: The Train years in words (the map, the briefs, the architect's request).
TRAIN_LABEL = "Train years 2016-19 and 2022-24"
#: The bar's rules (the design's 6b; rules, never market figures). `state_every`, `state_first`, `state_match`: THE
#: RESTART CHECK (STATE emptied `state_first` sessions into a span, then every `state_every`; the share that must match).
#: `state_first` shares no factor with `state_every`, so no counter's period keeps in phase with the resets.
#: `start_shifts`, `start_warm`, `start_min`, `start_match`, `start_active`: THE START CHECK (the later starts, in
#: decision sessions into a Train span: two different primes, so no clock's period divides both; the sessions added to
#: a later run's warm-up; the warmed-up sessions a later run must have for its shift to be used; the share of its
#: compared sessions that must match; and the share that must match of those on which either run asked an order, so a
#: program that trades on few sessions cannot hide what differs among the sessions that ask nothing).
BAR: dict[str, Any] = {"min_active_years": 3, "year_min_trades": 40, "year_min_days": 20, "year_t_floor": -1.0,
                       "cost_ratio": 0.5, "state_every": 20, "state_first": 7, "state_match": 0.99,
                       "start_shifts": (61, 127), "start_warm": 20, "start_min": 120, "start_match": 0.99,
                       "start_active": 0.95}
#: The decide limits the restart check loads its instances with (league/equity/EQUITY.md: 1 second a call, 25 errors).
DECIDE_TIMEOUT, DECIDE_MAX_ERRORS = 1.0, 25
#: THE SAME SIZE (the restart check): two buys' sizes within these are one size. A `share` within one part in a million
#: of the sleeve (six places: the engine's quantity precision, `league.equity.config.QTY_PLACES`), a `usd` within a cent.
SIZE_TOL: dict[str, float] = {"share": 10.0 ** -int(eqconfig.QTY_PLACES), "usd": 0.01}
FAILS: dict[str, str] = {
    "RUN": "the decider child failed this program's Train run again and again while other programs' runs completed",
    "DQ": "the program was disqualified on Train by its own errors or timeouts",
    "LOAD": "the decider child refused to load the program",
    "REVIEW": "the equity review refused the program (an absolute level, a reconstructed calendar, a rule keyed to the "
              "run's own profit since it began, or lookahead)",
    "STATE": f"run again with its STATE emptied every {BAR['state_every']} sessions (as a restart of the House's decider "
             f"empties it), the program's intents matched the uninterrupted run's on fewer than "
             f"{BAR['state_match']:.0%} of the Train sessions (a decide that fails in one run and not the other is no "
             "match)",
    "START": f"run again from later starts ({' and '.join(str(x) for x in BAR['start_shifts'])} sessions into a Train "
             f"span, each run starting flat as a live program does on its first day), the program's orders matched the "
             f"run from the span's start on fewer than {BAR['start_match']:.0%} of a later run's compared sessions (or "
             f"on fewer than {BAR['start_active']:.0%} of those on which either run asked an order): its decisions "
             "depend on when its run started",
    "WINDOW": f"the Train result carried a day outside the {TRAIN_LABEL} and was refused whole",
    "Y1": f"active (at least {BAR['year_min_trades']} closed lots on {BAR['year_min_days']} entry days) in fewer than "
          f"{BAR['min_active_years']} of the {len(TRAIN_YEARS)} Train years",
    "Y2": f"a Train year's daily P&L t below {BAR['year_t_floor']:g}",
    "P1": "net P&L at or below zero at 1.5x the half-spread",
    "R1": f"the 1.0x net P&L at or below zero, or the 1.5x P&L under {BAR['cost_ratio']:g} of it",
}
#: The researcher's settings (`elane.e2` keys; defaults here, policy.json in ELANE_E2_PATCHES.md) and their bounds.
DEFAULTS: dict[str, Any] = {"train_budget": 4, "train_max_attempts": 7, "train_max_errors": 3, "train_every_seconds": 600,
                            "train_per_round": 3, "train_max_output_tokens": 12000, "train_effort": "medium",
                            "refuted_cell_cap": 3}
BOUNDS: dict[str, tuple[float, float]] = {"train_budget": (1, 12), "train_max_attempts": (1, 30),
                                          "train_max_errors": (1, 10), "train_every_seconds": (60, 86400),
                                          "train_per_round": (1, 20), "train_max_output_tokens": (2000, 64000),
                                          "refuted_cell_cap": (1, 50)}
EFFORTS = ("minimal", "low", "medium", "high", "xhigh")
STATUSES = ("researching", "passed", "refuted", "stalled", "closed")
#: The fails that judge the MECHANISM on Train (the bar's). A family is REFUTED only with a version judged by one of these;
#: RUN, DQ, LOAD, REVIEW, STATE and START judge a program, so a family with no other is STALLED (no graveyard row, no
#: cell count).
JUDGED = ("Y1", "Y2", "P1", "R1")
#: The exception classes (by name, anywhere in the class's MRO) that are a program the child would not load: "LOAD".
LOAD_REFUSALS = ("ProgramRefused", "CodeRefused", "NeedsRefused")
#: The exception classes that are the child failing a run (league/equity/runner.py `RunFailed`; the decider's own): the
#: program's fault ("RUN") only once other programs' runs complete meanwhile, else the House's.
RUN_FAILURES = ("RunFailed", "DeciderError")
MAP_LABEL = (f"in-sample: the swarm's own Train runs, {TRAIN_LABEL}, at 1.0x and 1.5x the half-spread; the screen "
             "decides")
REFUTED_TAG = "REFUTED"
STALLED_TAG = "STALLED"

#: THE AGENDA (the mechanisms the equity pass offers, each with its published prior; no figure). `available` False:
#: no program can read its inputs today (earnings dates and surprises are not in the House's data), so a card of it
#: is refused. The key is the family's spec `agenda` and the Train map's mechanism.
AGENDA: dict[str, dict[str, Any]] = {
    "overnight": {"title": "the overnight effect", "available": True, "lane": "beta (always in) or equity (conditioned)",
                  "text": "index ETFs have earned a large share of their return between the close and the next open, "
                          "and little intraday; buy at the close (\"at\": \"close\") and sell at the next open. Always "
                          "in, it is market beta; conditioned (after a down close, by volatility, around events), it is a "
                          "timing claim",
                  "priors": "Cliff, Cooper and Gulen (2008); Lou, Polk and Skouras (2019, Journal of Financial "
                            "Economics)"},
    "reversal": {"title": "short-term reversal", "available": True, "lane": "equity",
                 "text": "after a sharp one- to five-session fall, liquidity providers are paid to absorb the selling and "
                         "prices tend to rebound over the next sessions, more so when volatility is high",
                 "priors": "Jegadeesh (1990); Lehmann (1990); Nagel (2012, Review of Financial Studies); Connors and "
                           "Alvarez (2008) on index ETFs"},
    "trend": {"title": "time-series trend", "available": True, "lane": "equity",
              "text": "an asset whose own trailing 3-12 month return is positive tends to keep rising; hold it while its "
                      "trend is up (its trailing return, or its price against a long moving average), else hold cash",
              "priors": "Moskowitz, Ooi and Pedersen (2012, Journal of Financial Economics); Faber (2007); Hurst, Ooi "
                        "and Pedersen (2017)"},
    "rotation": {"title": "cross-sectional and sector momentum, rotation", "available": True, "lane": "equity",
                 "text": "rank the sector ETFs (or the index ETFs) by their trailing 3-12 month return, skipping the last "
                         "month, and hold the strongest few, rebalanced on a monthly clock",
                 "priors": "Jegadeesh and Titman (1993); Moskowitz and Grinblatt (1999, industries); Asness, Moskowitz "
                           "and Pedersen (2013)"},
    "low_vol": {"title": "low volatility", "available": True, "lane": "equity",
                "text": "low-volatility assets have earned about as much as high-volatility ones with less risk; hold the "
                        "lowest-volatility ETFs of a set, or scale exposure inversely to recent realized volatility",
                "priors": "Ang, Hodrick, Xing and Zhang (2006); Frazzini and Pedersen (2014); Moreira and Muir (2017)"},
    "turn_of_month": {"title": "turn of the month", "available": True, "lane": "beta or equity",
                      "text": "equity returns have concentrated from the last session of a month through the first few "
                              "sessions of the next (payroll and pension flows); ctx.sessions_to_month_end and "
                              "ctx.session_of_month give the clock",
                      "priors": "Ariel (1987); Lakonishok and Smidt (1988); McConnell and Xu (2008)"},
    "earnings_drift": {"title": "post-earnings drift", "available": False, "lane": "equity",
                       "text": "prices keep moving in the direction of an earnings surprise for weeks. NOT AVAILABLE: the "
                               "House has no earnings dates or surprises yet, so no program can read them; a card of "
                               "this mechanism is refused until they exist",
                       "priors": "Ball and Brown (1968); Bernard and Thomas (1989)"},
    "other": {"title": "another mechanism", "available": True, "lane": "beta or equity",
              "text": "a mechanism outside this list, with its own published prior named in the card's hypothesis",
              "priors": "named in the card"},
}
#: The universe groups of the map's cells (in this order).
GROUPS = ("index", "sectors", "defensive", "stocks")


# ----------------------------------------------------------------------------------------------------------- settings
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """The researcher's settings from `elane.e2`, each inside its bound (a malformed value is its default)."""
    raw = elane_yield.e2_settings(settings)
    out = dict(DEFAULTS)
    for key, (lo, hi) in BOUNDS.items():
        x = _num(raw.get(key))
        if x is not None and lo <= x <= hi:
            out[key] = int(x) if isinstance(DEFAULTS[key], int) else x
    if raw.get("train_effort") in EFFORTS:
        out["train_effort"] = raw["train_effort"]
    return out


def lane_on(settings: Mapping[str, Any] | None) -> bool:
    """`elane.mode` is "gate" (E1's `elane.on`). An `elane` that cannot be read is off (fail closed)."""
    from . import elane

    try:
        return bool(elane.on(settings))
    except Exception:  # noqa: BLE001 - an unreadable switch is off
        return False


def symbols_group(symbols: Sequence[str]) -> str:
    """The universe group of a symbol set ("index", "sectors", "defensive", "stocks", joined by "+")."""
    seen = set()
    for raw in symbols:
        sym = str(raw).upper()
        if sym in eqconfig.INDEX_ETFS:
            seen.add("index")
        elif eqconfig.UNIVERSE.get(sym) == eqconfig.STOCK:
            seen.add("stocks")
        elif sym in ("TLT", "GLD"):
            seen.add("defensive")
        elif sym.startswith("XL"):
            seen.add("sectors")
    return "+".join(g for g in GROUPS if g in seen) or "none"


def cell_of(lane: Any, agenda: Any, symbols: Sequence[str]) -> tuple[str, str, str]:
    """A Train map cell: (lane, agenda mechanism, universe group)."""
    return (str(lane), str(agenda if agenda in AGENDA else "other"), symbols_group(symbols))


def cell_text(cell: Sequence[str]) -> str:
    return f"{cell[0]} / {cell[1]} / {cell[2]}"


# ----------------------------------------------------------------------------------------------------------- the bar
def _year_key(key: Any) -> int | None:
    try:
        return int(str(key)[:4])
    except (TypeError, ValueError):
        return None


def _inside(day: Any, spans: Sequence[tuple[dt.date, dt.date]]) -> bool:
    """Whether an ISO day (or a timestamp starting with one) lies inside one of `spans`; an unreadable day does not."""
    try:
        when = dt.date.fromisoformat(str(day)[:10])
    except ValueError:
        return False
    return any(first <= when <= last for first, last in spans)


def _row_days(result: Mapping[str, Any]) -> Iterator[Any]:
    """Every day a result's rows name: its start and end, its entry days, its daily rows, and the days of its trades,
    lots and booked dividends and splits (`actions`)."""
    yield result.get("start")
    yield result.get("end")
    entry_days = result.get("entry_days")
    if isinstance(entry_days, (list, tuple)):
        yield from entry_days
    daily = result.get("daily")
    for row in daily if isinstance(daily, (list, tuple)) else ():
        if isinstance(row, (list, tuple)) and row:
            yield row[0]
    for name in ("trades", "lots", "actions"):
        rows = result.get(name)
        for row in rows if isinstance(rows, (list, tuple)) else ():
            if isinstance(row, Mapping):
                yield from (row.get(k) for k in ("day", "entry_day", "exit_day"))


def _year_maps(result: Mapping[str, Any]) -> Iterator[Mapping[Any, Any]]:
    """Every by-year map of a result: its own, the buy-and-hold's and the exposure's."""
    for holder in (result, result.get("bh"), result.get("exposure")):
        rows = holder.get("by_year") if isinstance(holder, Mapping) else None
        if isinstance(rows, Mapping):
            yield rows


def outside_years(result: Mapping[str, Any] | None, *,
                  spans: Sequence[tuple[dt.date, dt.date]] = TRAIN_SPANS) -> list[str]:
    """What of a result lies outside `spans` (the Train spans; one run is held to its own span) (WINDOW): a by-year row
    of another year (its own, the buy-and-hold's or the exposure's), a day of its start, end, entry days, daily rows,
    trades, lots or actions outside them, another window. A 2020 or 2021 row (THE RESERVE) is outside exactly as a 2025
    or 2026 one is."""
    result = result or {}
    years = {y for first, last in spans for y in range(first.year, last.year + 1)}
    out = []
    for rows in _year_maps(result):
        for key in rows:
            year = _year_key(key)
            if year is None or year not in years:
                out.append(str(key))
    for day in _row_days(result):
        if day not in (None, "") and not _inside(day, spans):
            out.append(str(day)[:10])
    window = result.get("window")
    if window not in (None, "train"):
        out.append(str(window))
    return list(dict.fromkeys(out))


def _pooled(parts: Sequence[tuple[int, float | None, float | None]]) -> tuple[float | None, float | None]:
    """(mean, one-sample t) of the union of samples each given as (n, mean, t), every part's sample sd recovered from its
    mean and t; (None, None) when a part of two or more points gives no t (its spread cannot be recovered)."""
    parts = [(int(n), m, t) for n, m, t in parts if n and n > 0]
    total = sum(n for n, _, _ in parts)
    if not total or any(m is None for _, m, _ in parts):
        return None, None
    mean = sum(n * float(m) for n, m, _ in parts) / total
    if total < 2:
        return mean, None
    ss = 0.0
    for n, m, t in parts:
        if n >= 2:
            if not t or not m:
                return mean, None
            sd = abs(float(m)) * math.sqrt(n) / abs(float(t))
            ss += (n - 1) * sd * sd
        ss += n * (float(m) - mean) ** 2
    sd = math.sqrt(ss / (total - 1))
    return mean, (mean / sd * math.sqrt(total) if sd > 1e-15 else None)


def _daily_t(daily: Sequence[Any]) -> float | None:
    """The one-sample t of daily P&L values (E1's `results` definition: the sample sd; None under two points or with no
    spread)."""
    xs = [float(x) for x in daily if _num(x) is not None]
    if len(xs) < 2:
        return None
    mean = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))
    return round(mean / sd * math.sqrt(len(xs)), 4) if sd > 1e-15 else None


def combine(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """THE TRAIN SPANS' runs summed into one Train result (the module docstring): each started flat, so their counts,
    P&L and fees add; the pooled daily t is the t of their daily P&L rows together (else pooled from each run's mean and
    t); rates and exposure are weighted by trades and days; the worst drawdown is the larger. `by_year` is the union of
    the runs' own years. Status "ok" only when every run is; a disqualified run makes the whole "disqualified"."""
    parts = [p if isinstance(p, Mapping) else {} for p in parts]
    statuses = [str(p.get("status")) for p in parts]
    status = "ok" if parts and all(s == "ok" for s in statuses) else (
        "disqualified" if "disqualified" in statuses else next((s for s in statuses if s != "ok"), "no_data"))
    sums = [_summary(p) for p in parts]

    def total(key: str, ndigits: int = 2) -> float | None:
        xs = [x for x in (_num(s.get(key)) for s in sums) if x is not None]
        if not xs:
            return None
        return int(round(sum(xs))) if ndigits == 0 else round(sum(xs), ndigits)

    def weighted(key: str, weight: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None]) -> float | None:
        pairs = [(_num(s.get(key)), weight(p, s)) for p, s in zip(parts, sums)]
        pairs = [(x, w) for x, w in pairs if x is not None and w]
        weights = sum(w for _, w in pairs)
        return round(sum(x * w for x, w in pairs) / weights, 6) if weights else None

    def days(p: Mapping[str, Any], s: Mapping[str, Any]) -> float | None:
        return _num(s.get("days")) or (float(len(p["daily"])) if isinstance(p.get("daily"), list) else None)

    def trades(p: Mapping[str, Any], s: Mapping[str, Any]) -> float | None:
        return _num(s.get("trades"))

    dailies = [p.get("daily") for p in parts]
    if dailies and all(isinstance(d, list) and d for d in dailies):
        t_daily = _daily_t([row[1] for d in dailies for row in d if isinstance(row, (list, tuple)) and len(row) > 1])
    else:
        _, t_daily = _pooled([(int(_num(s.get("days")) or 0), _num(s.get("mean_pnl_daily")), _num(s.get("t_daily")))
                              for s in sums])
        t_daily = round(t_daily, 4) if t_daily is not None else None
    drawdowns = [x for x in (_num(s.get("max_drawdown")) for s in sums) if x is not None]
    summary = {"trades": total("trades", 0), "days": total("days", 0), "days_traded": total("days_traded", 0),
               "pnl": total("pnl"), "fees": total("fees"), "dividends": total("dividends"), "t_daily": t_daily,
               "win_rate": weighted("win_rate", trades), "exposure_mean": weighted("exposure_mean", days),
               "max_drawdown": max(drawdowns) if drawdowns else None,
               "mean_net_return": weighted("mean_net_return", trades)}
    by_year: dict[str, Any] = {}
    for p in parts:
        rows = p.get("by_year")
        by_year.update(rows if isinstance(rows, Mapping) else {})
    bh = [_num((p.get("bh") or {}).get("pnl")) if isinstance(p.get("bh"), Mapping) else None for p in parts]
    mtes = [p.get("mte") if isinstance(p.get("mte"), Mapping) else {} for p in parts]
    mte_mean, mte_t = _pooled([(int(_num(m.get("n")) or 0), _num(m.get("mean")), _num(m.get("t"))) for m in mtes])
    out = {"status": status, "window": "train", "start": parts[0].get("start") if parts else None,
           "end": parts[-1].get("end") if parts else None, "spans": len(parts), "summary": summary, "by_year": by_year,
           "bh": {"pnl": round(sum(x for x in bh if x is not None), 2) if any(x is not None for x in bh) else None},
           "mte": {"mean": round(mte_mean, 6) if mte_mean is not None else None,
                   "t": round(mte_t, 4) if mte_t is not None else None,
                   "n": sum(int(_num(m.get("n")) or 0) for m in mtes)}}
    reason = next((p.get("reason") for p in parts if p.get("status") == "disqualified" and p.get("reason")), None)
    if reason:
        out["reason"] = reason
    return out


def year_rows(result: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The Train years' rows of a result's `by_year` ({"2016": {trades, days_traded, pnl, t, exposure, bh_pnl}})."""
    out = {}
    for key, row in sorted(((result or {}).get("by_year") or {}).items(), key=lambda kv: str(kv[0])):
        year = _year_key(key)
        if year is None or year not in TRAIN_YEARS or not isinstance(row, Mapping):
            continue
        out[str(year)] = {"trades": int(_num(row.get("trades")) or 0), "days_traded": int(_num(row.get("days_traded")) or 0),
                          "pnl": _num(row.get("pnl")), "t": _num(row.get("t_daily")),
                          "exposure": _num(row.get("exposure_mean")), "bh_pnl": _num(row.get("bh_pnl"))}
    return out


def _summary(result: Mapping[str, Any] | None) -> Mapping[str, Any]:
    s = (result or {}).get("summary")
    return s if isinstance(s, Mapping) else {}


def train_score(base: Mapping[str, Any] | None, stress: Mapping[str, Any] | None) -> dict[str, Any]:
    """equity-v1's Y1, Y2, P1 and R1 on a version's 1.0x (`base`) and 1.5x (`stress`) Train results, each the Train
    spans' runs summed (`combine`; the module docstring): {objective, passed, fails, why, score (the pooled daily t at
    1.0x), years, active_years, pnl_10, pnl_15, ratio, summary, beside}. A result outside the Train years (WINDOW) or
    not "ok" (RUN) is judged on nothing else and shows no figure. STATE is the restart check's (`restart_check`) and
    START the start check's (`start_check`), run on the House once these hold."""
    out: dict[str, Any] = {"objective": OBJECTIVE, "passed": False, "fails": [], "why": None, "score": None,
                           "years": {}, "active_years": 0, "pnl_10": None, "pnl_15": None, "ratio": None,
                           "summary": {}, "beside": {}}
    for result in (base, stress):
        if outside_years(result):
            out["fails"], out["why"] = ["WINDOW"], FAILS["WINDOW"]
            return out
    if not isinstance(base, Mapping) or base.get("status") != "ok" or not isinstance(stress, Mapping) \
            or stress.get("status") != "ok":
        out["fails"], out["why"] = ["RUN"], FAILS["RUN"]
        return out
    years = year_rows(base)
    for row in years.values():
        row["active"] = row["trades"] >= BAR["year_min_trades"] and row["days_traded"] >= BAR["year_min_days"]
    active = sum(1 for r in years.values() if r["active"])
    s10, s15 = _summary(base), _summary(stress)
    pnl_10, pnl_15 = _num(s10.get("pnl")), _num(s15.get("pnl"))
    fails = []
    if active < BAR["min_active_years"]:
        fails.append("Y1")
    if any((r["t"] if r["t"] is not None else 0.0) < BAR["year_t_floor"] for r in years.values()):
        fails.append("Y2")
    if pnl_15 is None or pnl_15 <= 0:
        fails.append("P1")
    if pnl_10 is None or pnl_10 <= 0 or pnl_15 is None or pnl_15 < BAR["cost_ratio"] * pnl_10:
        fails.append("R1")
    bh = (base.get("bh") or {}) if isinstance(base.get("bh"), Mapping) else {}
    mte = (base.get("mte") or {}) if isinstance(base.get("mte"), Mapping) else {}
    bh_pnl = _num(bh.get("pnl"))
    out.update({
        "passed": not fails, "fails": fails, "why": "; ".join(FAILS[f] for f in fails) or None,
        "score": _num(s10.get("t_daily")), "years": years, "active_years": active, "pnl_10": pnl_10, "pnl_15": pnl_15,
        "ratio": (round(pnl_15 / pnl_10, 4) if pnl_10 and pnl_10 > 0 and pnl_15 is not None else None),
        "summary": {k: _num(s10.get(k)) for k in ("trades", "days_traded", "pnl", "fees", "t_daily", "win_rate",
                                                 "exposure_mean", "max_drawdown", "mean_net_return")},
        "beside": {"bh_pnl": bh_pnl, "mte_mean": _num(mte.get("mean")), "mte_t": _num(mte.get("t")),
                   "drift_share": (round(bh_pnl / pnl_10, 4) if bh_pnl is not None and pnl_10 and pnl_10 > 0 else None)},
    })
    return out


def bar_text() -> str:
    """THE BAR in words (rules only)."""
    return (f"THE TRAIN BAR ({OBJECTIVE}), on the House's {TRAIN_LABEL} (one run a span, each starting flat, summed) "
            f"at 1.0x and 1.5x the half-spread: (Y1) at least {BAR['year_min_trades']} closed lots on "
            f"{BAR['year_min_days']} entry days in each of at least {BAR['min_active_years']} of the {len(TRAIN_YEARS)} "
            f"Train years; (Y2) no Train year's daily P&L t below {BAR['year_t_floor']:g}; (P1) net P&L above zero at "
            f"1.5x; (R1) the 1.0x net P&L above zero and the 1.5x P&L at least {BAR['cost_ratio']:g} of it; (STATE) run "
            f"again with its STATE emptied every {BAR['state_every']} sessions, the program's intents match the "
            f"uninterrupted run's on at least {BAR['state_match']:.0%} of the sessions: the House's decider restarts on "
            "every deploy and a restart empties STATE, so keep in STATE only a cache of what ctx gives again (holdings "
            "are in ctx.positions, the clock in ctx's calendar fields). A session matches when both runs give the same "
            "orders, each buy the same size to six places of its share (a cent of its usd), and neither decide failed "
            "where the other did not: a decide must work on an empty STATE at any session, lots held or not. Never "
            "carry a value from session to session and update it in place (a running sum, a moving average, a peak "
            "since entry): ctx's history is adjusted as of each session and rounded, so the carried value drifts from "
            "what ctx gives now and the sizes differ; recompute it from ctx.bars at every call (a lot's own facts are "
            f"in ctx.positions). (START) each Train span run again from "
            f"{' and '.join(str(x) for x in BAR['start_shifts'])} sessions in, every run starting flat, the program's "
            f"orders (each order's kind, symbol and fill point, each buy's size; tags apart) match the run from the "
            f"span's start on at least {BAR['start_match']:.0%} of each later run's sessions (and on at least "
            f"{BAR['start_active']:.0%} of those on which either run asked an order), compared once the later "
            "run has warmed up (the longer of the program's history and maximum hold, and "
            f"{BAR['start_warm']} sessions more) and before that wherever the two runs hold the same lots. "
            f"{START_ADVICE} Reported beside, never a bar: the same-exposure "
            "buy-and-hold over the same sessions, the mean time-matched excess (MTE) and the drift share. The first "
            "version that passes is the lineage's ONE Validation try, then ONE sealed look; their outcomes are sealed and "
            "never shown to anyone who writes programs.")


# ----------------------------------------------------------------------------------------------------------- the record
def record_of(fam: Mapping[str, Any] | None) -> dict[str, Any]:
    """E2's Train record of a family ({} for a family E2 did not bear)."""
    return elane_seal.e2_record(fam, STATE_KEY)


def e2_family(fam: Mapping[str, Any] | None) -> bool:
    """A family the equity pass bore (its spec's `e2_route`): E2 researches it on Train, and E1's tournament validates
    it only where `may_validate` allows (ELANE_E2_PATCHES.md patch 5)."""
    spec = (fam or {}).get("spec") or {}
    return isinstance(spec, Mapping) and bool(spec.get(elane_yield.ROUTE_KEY)) and \
        elane_seal.lane_of_spec(spec) is not None


def passed_version(fam: Mapping[str, Any] | None) -> int | None:
    n = record_of(fam).get("passed_version")
    return int(n) if isinstance(n, int) and not isinstance(n, bool) else None


def identity() -> dict[str, str] | None:
    """The equity identity verdicts are judged under now (E1's `evaluator.equity_identity`: the league/equity code's
    fingerprint and the engine version), or None when it cannot be read (then no pass reads as stale)."""
    try:
        from .evaluator import equity_identity

        value = equity_identity()
    except Exception:  # noqa: BLE001 - no identity: nothing is judged stale by it
        return None
    return dict(value) if isinstance(value, Mapping) else None


def judged(rec: Mapping[str, Any]) -> int:
    """How many of a record's versions the bar judged on the mechanism (a fail among `JUDGED`)."""
    return sum(1 for v in versions_of(rec).values() if any(f in JUDGED for f in (v.get("fails") or [])))


def tried(store: Any, fid: str, n: int) -> bool:
    """Whether version `n` of the family has had its Validation try (a Validation run at k 1.0 that the runner made: E1's
    `elane.lineage_tries` rule for one version). Outcome-free: only that the try happened."""
    try:
        row = store._one("SELECT 1 AS ok FROM runs WHERE family=? AND version=? AND \"window\"='validation' AND stress=1.0 "
                         "AND COALESCE(status, '') NOT IN ('error', 'no_data') LIMIT 1", (str(fid), int(n)))
    except Exception:  # noqa: BLE001 - unreadable: read as tried (a stale pass is then left to E1, never re-scored twice)
        return True
    return row is not None


def pass_current(store: Any, fam: Mapping[str, Any] | None) -> bool:
    """THE IDENTITY (the module docstring): the family's pass was judged under the equity identity in force, or its
    version has had its Validation try (E1 owns it from there), or no identity can be read. AND THE WHOLE BAR (release
    E2.1): a pass whose verdict carries no start check (`start`: it was judged before START was part of the bar) is
    not current either, until its version has had its try."""
    n = passed_version(fam)
    if n is None:
        return False
    verdict = versions_of(record_of(fam)).get(str(n)) or {}
    whole = isinstance(verdict.get("start"), Mapping)
    now = identity()
    if now is None and whole:
        return True
    return (whole and verdict.get("identity") == now) or tried(store, str((fam or {}).get("id")), n)


def may_validate(store: Any, fam: Mapping[str, Any] | None, n: Any) -> bool:
    """THE GUARD E1'S TOURNAMENT APPLIES (ELANE_E2_PATCHES.md patch 5, after `n = elane.next_try(...)`): True for a family
    E2 did not bear; for an E2 family, only when `n` is its pass (the first version that passed equity-v1 AND the equity
    review), the review E1's look reads is in its state for that exact program, and the pass is current (`pass_current`).
    E1's `next_try` keeps its own due, stale and retry logic: a Validation gone stale is validated again through here."""
    if not e2_family(fam):
        return True
    fam = fam or {}
    p = passed_version(fam)
    if n is None or p is None or fam.get("retired_at"):
        return False
    try:
        if int(n) != p:
            return False
        version = store.version(str(fam["id"]), p)
        if version is None or not version.get("code"):
            return False
        from .gate import run_sha

        if not elane_review.holds(fam.get("state"), run_sha(version)):
            return False
        return pass_current(store, fam)
    except Exception:  # noqa: BLE001 - a guard that cannot be read admits nothing
        return False


def compact(score: Mapping[str, Any], *, at: str, ident: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A version's verdict as the record keeps it (Train figures and its restart and start checks' counts only), with the
    identity it was judged under. Of a verdict's words the record keeps `said` alone (`program_fault`: what its author may
    read), never its raw `why`."""
    out = {"at": at, "objective": OBJECTIVE, "passed": bool(score.get("passed")), "fails": list(score.get("fails") or []),
           "score": score.get("score"), "active_years": score.get("active_years"), "pnl_10": score.get("pnl_10"),
           "pnl_15": score.get("pnl_15"), "ratio": score.get("ratio"), "years": dict(score.get("years") or {}),
           "summary": dict(score.get("summary") or {}), "beside": dict(score.get("beside") or {}),
           "identity": dict(ident) if isinstance(ident, Mapping) else None}
    if isinstance(score.get("state"), Mapping):
        out["state"] = dict(score["state"])
    if isinstance(score.get("start"), Mapping):
        out["start"] = dict(score["start"])
    if isinstance(score.get("said"), str) and score["said"]:
        out["why"] = score["said"][:400]
    return out


#: The exception classes a disqualification may name to its author (`dq_said`): Python's own and numpy's, by name. A
#: program defines no class (league/gym/safety.py), so its errors are of these; any other word is not shown.
ERROR_CLASSES = frozenset({
    "ArithmeticError", "AssertionError", "AttributeError", "FloatingPointError", "IndexError", "KeyError", "LookupError",
    "MemoryError", "NameError", "NotImplementedError", "OverflowError", "RecursionError", "RuntimeError", "StopIteration",
    "TypeError", "UnboundLocalError", "ValueError", "ZeroDivisionError", "LinAlgError", "AxisError", "Exception"})
_DQ_ERRORS = re.compile(r"^(\d{1,6}) errors \(first: (.*)\)$", re.S)
_DQ_LINE = re.compile(r"^line (\d{1,6})$")


def dq_said(reason: Any) -> str:
    """WHAT A DISQUALIFICATION SAYS TO ITS AUTHOR: counts, a line of its own file and an exception CLASS, never the
    exception's text. E1's reason carries the program's own message (`25 errors (first: line 12: ValueError: <up to 160
    characters the program chose>)`), and a program can put anything it read there (a bar of the 2020-21 reserve it
    reads as look-back), so the text never reaches a record or a brief."""
    text = str(reason or "")
    found = _DQ_ERRORS.match(text)
    if found:
        parts = found.group(2).split(": ", 2)
        where = parts[0] if parts and _DQ_LINE.match(parts[0]) else ""
        kind = parts[1] if len(parts) > 1 and parts[1] in ERROR_CLASSES else ""
        if not kind and "ran past" in (parts[0] if parts else ""):
            kind = "time limit"
        first = " ".join(x for x in (f"a {kind}" if kind and kind != "time limit" else
                                     "a decide past its time limit" if kind else "", f"at {where}" if where else "") if x)
        return f"{int(found.group(1))} errors in decide" + (f", the first {first}" if first else "")
    if text.startswith("decide used") and "budget" in text:
        return "its decides ran past the run's time budget"
    return "its own errors or timeouts"


def program_fault(code: str, why: str, *, said: str | None = None) -> dict[str, Any]:
    """The verdict of a version judged on its program alone (RUN, DQ, LOAD): no figure. `why` is the House's own record
    of the step; `said` is what the version's record keeps and its author reads in the next brief (`compact`): the
    House's own refusal text for LOAD (static, bounded: a program that would not load read no market data), counts and
    an exception class for DQ (`dq_said`), the failure's class for RUN. A `said` that only repeats the end of the
    failure's own sentence adds nothing and is said once (a disqualification with no count to name read "... by its own
    errors or timeouts: its own errors or timeouts" in `version_text`)."""
    told = FAILS[code] if said and FAILS[code].endswith(str(said)) else f"{FAILS[code]}: {said}"
    return {"objective": OBJECTIVE, "passed": False, "fails": [code], "why": f"{FAILS[code]}: {why}"[:400],
            "said": told[:400] if said else None, "score": None,
            "years": {}, "active_years": 0, "pnl_10": None, "pnl_15": None, "ratio": None, "summary": {}, "beside": {}}


# ----------------------------------------------------------------------------------------------------------- the restart check
#: The decider kind the restart check loads its instances under (league/equity/kinds.py `KINDS`; E1's runner `KIND`).
KIND = "equity"


class StateCheckInterrupted(RuntimeError):
    """The restart check could not run or finish on the House's side (no decider, an instance the child reloaded or lost,
    an answer without its call count, a ctx that could not be built, a span with no session): the House's, never the
    program's, and never a pass."""


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def same_intents(a: Any, b: Any) -> tuple[bool, dict[str, float] | None]:
    """WHAT MATCHES (the module docstring), for two decide answers' intents: (True, None) when they are the same orders
    in the same order, every buy the same size within `SIZE_TOL`; (False, {"share" | "usd": the largest gap}) when the
    sizes of their buys are ALL they differ in (the mark of a value carried in STATE and updated in place); (False,
    None) when they differ in anything else (another count, order, symbol, lot, fill point or tag, a `share` against a
    `usd`)."""
    a = a if isinstance(a, list) else []
    b = b if isinstance(b, list) else []
    if len(a) != len(b):
        return False, None
    gaps: dict[str, float] = {}
    for x, y in zip(a, b):
        if not isinstance(x, Mapping) or not isinstance(y, Mapping):
            if _canon(x) != _canon(y):
                return False, None
            continue
        if set(x) != set(y):
            return False, None
        for key, u in x.items():
            v = y[key]
            if key in SIZE_TOL and _num(u) is not None and _num(v) is not None:
                gap = abs(float(u) - float(v))
                if gap > SIZE_TOL[key]:
                    gaps[key] = max(gaps.get(key, 0.0), gap)
            elif _canon(u) != _canon(v):
                return False, None
    return (False, gaps) if gaps else (True, None)


def _asked(row: Mapping[str, Any]) -> tuple[int | None, int | None, bool]:
    """(the decides the answering instance has run since it was loaded, the errors it has counted since, whether it is
    disqualified) from one job's answer (`stats`: E1's `EquityRunner.stats`); a None for a count the answer does not
    carry."""
    stats = row.get("stats")
    stats = stats if isinstance(stats, Mapping) else {}
    calls, errors = (None if isinstance(x, bool) or not isinstance(x, int) else x
                     for x in (stats.get("calls"), stats.get("errors")))
    return calls, errors, bool(stats.get("disqualified"))


def _decided(decider: Any, jobs: Sequence[Mapping[str, Any]], tally: Mapping[str, dict[str, int]], restarts: Any, *,
             what: str, interrupted: type[StateCheckInterrupted]) -> dict[str, tuple[Mapping[str, Any], int | None]]:
    """ONE DECIDE of a check's instances, NEVER A SILENT PASS (the restart check's and the start check's one reader):
    {key: (its answer, the errors its instance counted in this decide; None for an instance that is disqualified)} for
    `jobs` ([{key, inputs}]). `tally[key]` is what each instance has been asked and has counted since its load, moved
    here. Every answer's `stats.calls` must be the decides its instance was asked since its load, so an instance the
    child reloaded is caught whether or not the decider counted a restart; a decider that restarted, an answer that
    is no result, a missing instance, a ctx that could not be built, and an answer without its call count or its
    error count raise `interrupted` (the House's). The decider's own errors pass through."""
    answer = decider.kind(KIND, "decide", {"jobs": list(jobs)})
    if getattr(decider, "restarts", None) != restarts:
        raise interrupted(f"the decider child restarted during the {what} (its instances were reloaded with fresh "
                          "memory)")
    results = answer.get("results") if isinstance(answer, Mapping) and answer.get("ok") else None
    if not isinstance(results, Mapping):
        why = answer.get("error") if isinstance(answer, Mapping) else type(answer).__name__
        raise interrupted(f"the decider child did not answer a decide: {str(why)[:200]}")
    rows = [(str(job["key"]), results.get(job["key"])) for job in jobs]
    if any(not isinstance(row, Mapping) or row.get("missing") for _, row in rows):
        raise interrupted(f"an instance of the {what} went missing in the decider child")
    failed = next((row.get("error") for _, row in rows if row.get("error")), None)
    if failed:
        raise interrupted(f"the child could not build a ctx: {str(failed)[:200]}")
    out: dict[str, tuple[Mapping[str, Any], int | None]] = {}
    for key, row in rows:
        mine = tally[key]
        mine["asked"] += 1
        calls, errors, gone = _asked(row)
        if calls is None or errors is None:
            raise interrupted(
                "a decide answer carries no call count (stats.calls): an instance the child reloaded could "
                "not be told from one that kept its memory" if calls is None else
                "a decide answer carries no error count (stats.errors): a decide that failed could not be "
                "told from one that answered nothing")
        if gone:
            out[key] = (row, None)  # a disqualified instance answers nothing and counts no call: no match
        elif calls != mine["asked"] or errors < mine["errors"]:
            raise interrupted(f"the decider child reloaded an instance during the {what} (it answered its decide "
                              f"{calls}, not {mine['asked']}): its memory was lost")
        else:
            out[key] = (row, errors - mine["errors"])
            mine["errors"] = errors
    return out


def state_inputs(run: Any) -> Iterator[Any]:
    """THE CTX STREAM of the restart check (the module docstring) for one Train span's uninterrupted 1.0x run (E1's
    `runner.Run`: its result and the `store.Bars` it ran on): E1's Gym inputs (`league.equity.ctx.inputs_from_bars`) at
    every session the engine decides on (the one before the run's first through the one before its last), holding the
    lots the run had open at that close (marked at the close), the lots it closed in that session, its equity from the
    daily record (E0 before the first session), the cash that leaves, the caps and the run's PARAMS. A generator: one
    session's inputs at a time (they carry the program's history).

    What the result does not keep is left out for both instances alike: the intents the engine refused
    (`ctx.rejects` is empty), the tag of a lot still open at the run's end, and a lot's quantity before a split during
    its hold (the result keeps its last quantity). A result that does not fit its bars (a lot's day outside them, a
    daily record of another length) raises `StateCheckInterrupted`."""
    from decimal import Decimal

    from ..equity import config as C
    from ..equity import ctx as X
    from ..equity.program import parse_needs
    from ..equity.store import from_ordinal

    result = getattr(run, "result", None)
    result = dict(result) if isinstance(result, Mapping) else {}
    bars = getattr(run, "bars", None)
    if bars is None:
        raise StateCheckInterrupted("the Train run carries no bars to build the restart check's ctx from")
    needs = parse_needs(result.get("needs"))
    params = dict(result.get("params") or {})
    capital = float(Decimal(str(result.get("capital") or C.SLEEVE_USD)))
    n, first = int(bars.n), int(bars.first)
    daily = [row for row in (result.get("daily") or []) if isinstance(row, (list, tuple)) and len(row) > 2]
    if len(daily) != n - first:
        raise StateCheckInterrupted(f"the Train run's daily record has {len(daily)} rows for {n - first} run sessions")
    index = {from_ordinal(int(d)).isoformat(): i for i, d in enumerate(bars.days)}
    trades = {int(t["id"]): t for t in (result.get("trades") or []) if isinstance(t, Mapping) and t.get("id") is not None}
    opened: dict[int, list[tuple[int, Mapping[str, Any]]]] = {}
    shut: dict[int, list[tuple[int, Mapping[str, Any]]]] = {}
    for lot in result.get("lots") or []:
        if not isinstance(lot, Mapping):
            continue
        entry = index.get(str(lot.get("entry_day")))
        if entry is None:
            raise StateCheckInterrupted(f"lot {lot.get('lid')} names an entry day outside the run's bars")
        opened.setdefault(entry, []).append((entry, lot))
        if lot.get("exit_day"):
            leave = index.get(str(lot["exit_day"]))
            if leave is None:
                raise StateCheckInterrupted(f"lot {lot.get('lid')} names an exit day outside the run's bars")
            shut.setdefault(leave, []).append((entry, lot))
    equity_at = {index[str(row[0])]: float(row[2]) for row in daily if str(row[0]) in index}
    marks: dict[str, list[float | None]] = {}
    for sym in needs.symbols:
        column, last, out = bars.raw[sym], None, []
        for i in range(n):
            value = float(column[i][3])
            last = value if math.isfinite(value) and value > 0 else last
            out.append(last)
        marks[sym] = out
    held: dict[int, tuple[int, Mapping[str, Any]]] = {}
    equity = capital
    for j in range(max(first - 1, 0), n - 1):
        for entry, lot in opened.get(j, ()):
            held[int(lot["lid"])] = (entry, lot)
        closed = []
        for entry, lot in shut.get(j, ()):
            held.pop(int(lot["lid"]), None)
            trade = trades.get(int(lot["lid"])) or {}
            closed.append(X.closed_row(lid=int(lot["lid"]), symbol=str(lot["symbol"]), qty=float(lot["qty"]),
                                       entry=float(lot["entry_px"]), exit=float(lot.get("exit_px") or 0.0),
                                       net=float(trade.get("net") or 0.0), held_sessions=j - entry,
                                       reason=str(lot.get("reason") or "program"), tag=str(trade.get("tag") or "")))
        positions, value, own = [], 0.0, {}
        for lid, (entry, lot) in sorted(held.items()):
            sym = str(lot["symbol"])
            mark = (marks.get(sym) or [None] * n)[j]
            mark = float(lot["entry_px"]) if mark is None else mark
            qty = float(lot["qty"])
            positions.append(X.lot_row(lid=lid, symbol=sym, klass=str(lot.get("class") or C.class_of(sym) or C.ETF),
                                       qty=qty, entry=float(lot["entry_px"]), mark=mark, held_sessions=j - entry,
                                       at=str(lot.get("entry_at") or "open"), tag=str((trades.get(lid) or {}).get("tag") or "")))
            value += qty * mark
            own[sym] = own.get(sym, 0.0) + qty * mark
        equity = equity_at.get(j, equity)
        cash = max(0.0, equity - value)
        caps = {s: round(max(0.0, min(float(C.POSITION_SHARE[C.class_of(s) or C.ETF]) * capital - own.get(s, 0.0), cash)),
                         2) for s in needs.symbols}
        yield X.inputs_from_bars(bars, j, needs=needs, positions=positions, closed=closed, rejects=(), cash=cash,
                                 equity=equity, budget=capital, caps=caps, params=params)


def restart_check(decider: Any, code: str, params: Mapping[str, Any] | None, *, name: str,
                  streams: Iterable[Iterable[Any]], every: int | None = None, first: int | None = None) -> dict[str, Any]:
    """THE RESTART CHECK (the module docstring) through E1's decider kinds: for each stream (one a Train span) instance A,
    loaded once, and instance B, loaded with it and then loaded fresh `first` (`BAR["state_first"]`) sessions in and
    every `every` (`BAR["state_every"]`) sessions after, decide on the same inputs at every session. {sessions, matched,
    share, every, first, need, held (matched on at least `BAR["state_match"]` of the sessions), disqualified (the
    sessions an instance was disqualified at: they match nothing), failed (the sessions the two decides did not count
    the same errors: one failed and the other did not), sized (the sessions the two answers were the same orders and
    differed in a buy's size alone), size_gap (the largest such gap, by `share` and by `usd`), first_miss ({span,
    session, after_reset} of the first session they differed)}.

    NEVER A SILENT PASS: every answer's `stats.calls` must be the decides its instance was asked since its load (A: every
    session of the span so far; B: every session since its reset), so an instance the child reloaded is caught whether or
    not the decider counted a restart; an answer without that count or without `stats.errors` (a decide that failed
    could not be told from one that answered nothing), a missing instance, a ctx that could not be built and a stream
    with no session raise `StateCheckInterrupted` (the House's). The decider's own errors pass through (a child that
    failed: `DeciderError`; a program it would not load: `ProgramRefused`). Every instance is dropped at the end."""
    every = max(1, int(every or BAR["state_every"]))
    first = max(0, int(BAR["state_first"] if first is None else first))
    need = float(BAR["state_match"])
    payload = {"code": str(code), "params": dict(params or {}), "name": str(name), "timeout": DECIDE_TIMEOUT,
               "max_errors": DECIDE_MAX_ERRORS}
    restarts = getattr(decider, "restarts", None)
    loaded: list[str] = []
    sessions = matched = disqualified = failed = sized = 0
    size_gap: dict[str, float] = {}
    first_miss: dict[str, int] | None = None

    def load(key: str) -> dict[str, int]:
        loaded.append(key)
        decider.kind_load(KIND, key, payload)
        return {"asked": 0, "errors": 0}  # what a fresh instance has been asked and has counted

    def drop(key: str) -> None:
        loaded.remove(key)
        decider.kind_drop(KIND, key)

    try:
        for span, stream in enumerate(streams):
            a, b = f"e2-state:{name}:{span}:a", ""
            tally = {a: load(a)}
            seen = resets = since = 0
            for i, inputs in enumerate(stream):
                # B's resets, off the span's start (the module docstring): with A at session 0, then `first` sessions in
                # and every `every` after.
                if i == 0 or (i >= first and (i - first) % every == 0):
                    if b:
                        drop(b)
                        tally.pop(b, None)
                    b, resets, since = f"e2-state:{name}:{span}:b{resets}", resets + 1, i
                    tally[b] = load(b)
                answers = _decided(decider, [{"key": a, "inputs": inputs}, {"key": b, "inputs": inputs}], tally, restarts,
                                   what="restart check", interrupted=StateCheckInterrupted)
                (ra, erred_a), (rb, erred_b) = answers[a], answers[b]  # the errors each instance counted in this decide
                sessions, seen = sessions + 1, seen + 1
                same = False
                if erred_a is None or erred_b is None:
                    disqualified += 1  # a disqualified instance answers nothing and counts no call: no match
                elif erred_a != erred_b:
                    failed += 1  # one decide failed (or returned a malformed intent) and the other did not: no match
                else:
                    same, gaps = same_intents(ra.get("intents"), rb.get("intents"))
                    if gaps:
                        sized += 1
                        for unit, gap in gaps.items():
                            size_gap[unit] = max(size_gap.get(unit, 0.0), gap)
                if same:
                    matched += 1
                elif first_miss is None:
                    first_miss = {"span": span, "session": i, "after_reset": i - since}
            if not seen:
                raise StateCheckInterrupted(f"Train span {span} gave the restart check no session")
    finally:
        for key in list(loaded):
            try:
                decider.kind_drop(KIND, key)
            except Exception:  # noqa: BLE001 - a drop that fails leaves an instance a restart clears
                pass
    if not sessions:
        raise StateCheckInterrupted("the restart check had no Train session to compare")
    return {"sessions": sessions, "matched": matched, "share": round(matched / sessions, 4), "every": every, "first": first,
            "need": need, "disqualified": disqualified, "failed": failed, "sized": sized,
            "size_gap": {unit: float(f"{gap:.2g}") for unit, gap in sorted(size_gap.items())},
            "held": matched >= need * sessions - 1e-9, "first_miss": first_miss}


#: What of a restart check the record keeps (`with_state`): counts and the program's own size gaps, no market figure.
STATE_KEYS = ("sessions", "matched", "share", "every", "first", "need", "disqualified", "failed", "sized", "size_gap",
              "first_miss")


def with_state(verdict: Mapping[str, Any], check: Mapping[str, Any]) -> dict[str, Any]:
    """A bar verdict with its restart check: as it was when the check held, else failed STATE (its Train figures kept, so
    the brief shows what the program earned). A check with no session compared never holds."""
    out = dict(verdict)
    out["state"] = {k: check.get(k) for k in STATE_KEYS}
    if not check.get("held") or not check.get("sessions"):
        out.update(passed=False, fails=["STATE"],
                   why=f"{FAILS['STATE']}: {check.get('matched')} of {check.get('sessions')} sessions matched")
    return out


# ----------------------------------------------------------------------------------------------------------- the start check
class StartCheckInterrupted(StateCheckInterrupted):
    """The start check could not run or finish on the House's side (no decider, a later run that does not share its
    span's sessions, an instance the child reloaded or lost, a ctx that could not be built, no span long enough for a
    later start): the House's, never the program's, and never a pass."""


class StartRun(NamedTuple):
    """One Train run as the start check reads it (`start_run`): `days`, its decision sessions, oldest first (E1's
    engine decides at the close of every session from the one before the run's first, or its first where the store has
    none before it, to the one before its last); `inputs`, its ctx stream, one inputs a decision session
    (`state_inputs`); `history` and `max_hold`, the program's NEEDS (the warm-up's two terms)."""

    days: Sequence[dt.date]
    inputs: Iterable[Any]
    history: int
    max_hold: int


def start_run(run: Any) -> StartRun:
    """A Train run of E1's runner (`runner.Run`: its result and the bars it ran on) as the start check reads it: its
    decision sessions from its bars, its ctx stream from `state_inputs` (each inputs held to its own session's day),
    its NEEDS from its result. A run with no bars, a result whose NEEDS do not parse or a stream that does not follow
    the bars raises `StartCheckInterrupted`."""
    from ..equity.program import parse_needs
    from ..equity.store import from_ordinal

    result = getattr(run, "result", None)
    bars = getattr(run, "bars", None)
    if bars is None or not isinstance(result, Mapping):
        raise StartCheckInterrupted("a Train run carries no bars to build the start check's ctx from")
    try:
        needs = parse_needs(result.get("needs"))
    except Exception as exc:  # noqa: BLE001 - the child loaded the program: a result whose NEEDS do not parse is the House's
        raise StartCheckInterrupted(f"a Train run's NEEDS do not parse: {type(exc).__name__}") from None
    n, first = int(bars.n), int(bars.first)
    ordinals = [int(d) for d in bars.days[max(first - 1, 0):max(n - 1, 0)]]

    def stream() -> Iterator[Any]:
        count = 0
        for inputs in state_inputs(run):
            if count >= len(ordinals) or int(inputs.days[-1]) != ordinals[count]:
                raise StartCheckInterrupted("a Train run's ctx stream does not follow its bars' sessions")
            count += 1
            yield inputs
        if count != len(ordinals):
            raise StartCheckInterrupted(f"a Train run's ctx stream has {count} sessions for {len(ordinals)} decisions")

    return StartRun([from_ordinal(d) for d in ordinals], stream(), int(needs.history), int(needs.max_hold_sessions))


def start_plan(sessions: int, history: int, max_hold: int) -> dict[str, Any]:
    """WHICH LATER STARTS FIT a Train span of `sessions` decision sessions, for a program of NEEDS `history` and
    `max_hold`: {warm (the later run's own first sessions it is not held to: max(history, max_hold) +
    `BAR["start_warm"]`), shifts (those of `BAR["start_shifts"]` that leave a later run at least `BAR["start_min"]`
    warmed-up sessions), skipped ([{shift, why}] for the rest: a span shorter than the shift, the warm-up and
    `start_min` together uses what fits and says so)}."""
    warm = max(int(history), int(max_hold)) + int(BAR["start_warm"])
    fits: list[int] = []
    skipped: list[dict[str, Any]] = []
    for shift in BAR["start_shifts"]:
        left = int(sessions) - int(shift) - warm
        if left >= int(BAR["start_min"]):
            fits.append(int(shift))
        else:
            skipped.append({"shift": int(shift), "why": f"a start {shift} sessions into a span of {int(sessions)} leaves "
                                                        f"{max(left, 0)} sessions after its warm-up of {warm}; "
                                                        f"{BAR['start_min']} are needed"})
    return {"warm": warm, "shifts": fits, "skipped": skipped}


def _field(inputs: Any, name: str) -> Any:
    """A field of a decision's inputs (E1's `ctx.Inputs`, an object; a mapping in the tests' invented streams)."""
    return inputs.get(name) if isinstance(inputs, Mapping) else getattr(inputs, name, None)


def start_orders(intents: Any, inputs: Any) -> list[Any]:
    """A decide's intents AS THE START CHECK COMPARES THEM (the module docstring): each order's kind, its symbol and its
    fill point, a buy's `share` or `usd`; never a tag, and a sell names its lot's SYMBOL (read from the positions of the
    inputs it decided on: two runs number their lots apart). A cancel is a cancel (the Gym holds no pending order)."""
    lots: dict[Any, str] = {}
    positions = _field(inputs, "positions")
    for lot in positions if isinstance(positions, (list, tuple)) else ():
        if isinstance(lot, Mapping):
            lots[_num(lot.get("id"))] = str(lot.get("symbol"))
    out: list[Any] = []
    for intent in intents if isinstance(intents, list) else []:
        if not isinstance(intent, Mapping):
            out.append(intent)
        elif "buy" in intent:
            out.append({"buy": str(intent["buy"]), "at": str(intent.get("at") or "open"),
                        **{unit: intent[unit] for unit in SIZE_TOL if intent.get(unit) is not None}})
        elif "sell" in intent:
            out.append({"sell": lots.get(_num(intent["sell"]), "a lot it does not hold"),
                        "at": str(intent.get("at") or "open")})
        elif "cancel" in intent:
            out.append({"cancel": True})
        else:
            out.append({str(k): v for k, v in intent.items() if k != "tag"})
    return out


def _order_text(order: Any) -> str:
    """One compared order in words ("buy SPY 0.5 of the sleeve at the open")."""
    if not isinstance(order, Mapping):
        return "an order that is no intent"
    at = f" at the {order.get('at')}" if order.get("at") else ""
    if "buy" in order:
        share, usd = _num(order.get("share")), _num(order.get("usd"))
        size = f" {share:.4g} of the sleeve" if share is not None else (f" ${usd:,.2f}" if usd is not None else "")
        return f"buy {order['buy']}{size}{at}"
    if "sell" in order:
        return f"sell {order['sell']}{at}"
    return "cancel an order" if "cancel" in order else "an order of no kind"


def _orders_text(orders: Sequence[Any], limit: int = 4) -> str:
    said = [_order_text(o) for o in orders[:limit]]
    if len(orders) > limit:
        said.append(f"and {len(orders) - limit} more")
    return "; ".join(said) if said else "nothing"


def same_book(a: Any, b: Any) -> bool:
    """Whether two runs show their program THE SAME BOOK at one session (the module docstring): the same open lots in
    the same order (each lot's symbol, fill point, sessions held, entry price and mark), the same lots closed since
    the last call (symbol, sessions held, reason, entry and exit prices) and as many pending orders. What a run's own
    standing sets is left out: a lot's id, quantity, value, pnl and net, and its tag (a program's own words)."""
    def book(inputs: Any) -> str:
        def rows(name: str, keys: Sequence[str]) -> list[Any]:
            value = _field(inputs, name)
            return [[row.get(k) for k in keys] if isinstance(row, Mapping) else row
                    for row in (value if isinstance(value, (list, tuple)) else ())]
        orders = _field(inputs, "orders")
        return _canon([rows("positions", ("symbol", "at", "held_sessions", "entry", "mark")),
                       rows("closed", ("symbol", "held_sessions", "reason", "entry", "exit")),
                       len(orders) if isinstance(orders, (list, tuple)) else 0])
    return book(a) == book(b)


def later_runs(runner: Any, code: str, params: Mapping[str, Any] | None, *, name: str, runs: Sequence[Any],
               spans: Sequence[tuple[dt.date, dt.date]] = TRAIN_SPANS) -> list[dict[str, Any]]:
    """THE START CHECK'S RUNS (the module docstring): for each Train span and its 1.0x run from the span's first
    session (`runs`, in the spans' order), the later starts that fit (`start_plan`), each one more run of E1's isolated
    runner at 1.0x, starting flat on the session after the base run's decision number `shift` and ending with the
    span. One row a span for `start_check`: {"base", "later": [(shift, `StartRun`)], "skipped"}. A later run is kept
    in no record and stored nowhere: it is the check's, not Train evidence. One that ended neither "ok" nor
    "disqualified", or carries a day outside its span, raises `StartCheckInterrupted` (the House's); the runner's own
    errors pass through (a child that failed: `RunFailed`; a program it would not load: `ProgramRefused`)."""
    out: list[dict[str, Any]] = []
    for (first, last), run in zip(spans, runs):
        base = start_run(run)
        plan = start_plan(len(base.days), base.history, base.max_hold)
        later: list[tuple[int, StartRun]] = []
        for shift in plan["shifts"]:
            other = runner.train(code, dict(params or {}), name=name, start=base.days[shift + 1], end=last,
                                 k=float(eqconfig.K_BASE))
            result = getattr(other, "result", None)
            result = result if isinstance(result, Mapping) else {}
            if result.get("status") not in ("ok", "disqualified"):
                raise StartCheckInterrupted(f"the run started {shift} sessions into the Train span from {first} ended "
                                            f"{result.get('status')}")
            if outside_years(result, spans=[(first, last)]):
                raise StartCheckInterrupted(f"the run started {shift} sessions into the Train span from {first} carried "
                                            "a day outside its span")
            later.append((int(shift), start_run(other)))
        out.append({"base": base, "later": later, "skipped": plan["skipped"]})
    return out


#: How many of a later run's differing sessions its record names (`start_check`'s `misses`).
START_MISSES = 12


def start_check(decider: Any, code: str, params: Mapping[str, Any] | None, *, name: str,
                spans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """THE START CHECK (the module docstring) through E1's decider kinds. `spans`: one a Train span, {"base": the
    `StartRun` of the run from the span's first session, "later": [(shift, the `StartRun` of the run started `shift`
    decision sessions later)], "skipped": `start_plan`'s}. Per span one instance a run, each loaded once and never
    reset, each deciding on ITS OWN run's ctx at every session of its run; a later run's answer is held against the
    base run's at the same session.

    {sessions (compared, all later runs), matched, share (the LOWEST later run's: the one the rule reads), need,
    active (the compared sessions on which either run asked an order), active_matched, active_share (the lowest later
    run's), active_need, warm, shifts, held (every later run matched on at least `BAR["start_match"]` of its compared
    sessions AND on at least `BAR["start_active"]` of its active ones), runs ([{span, shift, sessions, early (those
    compared before its warm-up ended: the same book), matched, share, active, active_matched, active_share, held,
    disqualified, failed, sized, misses (its first `START_MISSES` differing sessions, counted from its own first
    decision), first_miss ({session, what ("orders" | "size" | "failed" | "disqualified"), base, later: the two runs'
    orders in words})}]), skipped ([{span, shift, why}]), disqualified, failed, sized, size_gap, first_miss ({span,
    shift, session, what, base, later} of the first later run that did not hold, else of the first that differed at
    all)}.

    NEVER A SILENT PASS, as the restart check (`_decided`): an instance the child reloaded or lost, a decider that
    restarted, an answer without its counts or a ctx that could not be built raise `StartCheckInterrupted`; so do a
    later run that does not start `shift` decision sessions into its span or does not share the span's sessions, a
    later run with fewer than `BAR["start_min"]` warmed-up sessions, and spans that fit no later start at all. The
    decider's own errors pass through. Every instance is dropped at the end."""
    need, busy = float(BAR["start_match"]), float(BAR["start_active"])
    payload = {"code": str(code), "params": dict(params or {}), "name": str(name), "timeout": DECIDE_TIMEOUT,
               "max_errors": DECIDE_MAX_ERRORS}
    restarts = getattr(decider, "restarts", None)
    loaded: list[str] = []
    runs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    size_gap: dict[str, float] = {}
    warm: int | None = None

    def load(key: str) -> dict[str, int]:
        loaded.append(key)
        decider.kind_load(KIND, key, payload)
        return {"asked": 0, "errors": 0}  # what a fresh instance has been asked and has counted

    try:
        for span, row in enumerate(spans):
            base = row["base"]
            skipped.extend({"span": span, **dict(s)} for s in row.get("skipped") or ())
            later = [(int(shift), run) for shift, run in row.get("later") or ()]
            if not later:
                continue  # no later start fits this span (said in `skipped`)
            warm = max(int(base.history), int(base.max_hold)) + int(BAR["start_warm"])
            days = list(base.days)
            a = f"e2-start:{name}:{span}:a"
            tally = {a: load(a)}
            others: list[dict[str, Any]] = []
            for shift, run in later:
                theirs = list(run.days)
                if not 0 < shift < len(days) or theirs != days[shift:]:
                    raise StartCheckInterrupted(f"the run started {shift} sessions into Train span {span} does not share "
                                                "the span's decision sessions from there on")
                if len(theirs) - warm < int(BAR["start_min"]):
                    raise StartCheckInterrupted(f"the run started {shift} sessions into Train span {span} has "
                                                f"{max(len(theirs) - warm, 0)} sessions after its warm-up of {warm}; "
                                                f"{BAR['start_min']} are needed")
                key = f"e2-start:{name}:{span}:s{shift}"
                tally[key] = load(key)
                others.append({"key": key, "inputs": iter(run.inputs),
                               "out": {"span": span, "shift": shift, "sessions": 0, "early": 0, "matched": 0,
                                       "active": 0, "active_matched": 0, "disqualified": 0, "failed": 0, "sized": 0,
                                       "misses": [], "first_miss": None}})
            seen = 0
            for i, inputs in enumerate(base.inputs):
                if i >= len(days):
                    raise StartCheckInterrupted(f"Train span {span}'s ctx stream runs past its decision sessions")
                jobs = [{"key": a, "inputs": inputs}]
                live: list[tuple[dict[str, Any], Any]] = []
                for other in others:
                    if i < other["out"]["shift"]:
                        continue
                    theirs = next(other["inputs"], None)
                    if theirs is None:
                        raise StartCheckInterrupted(f"the run started {other['out']['shift']} sessions into Train span "
                                                    f"{span} gave no ctx for one of its sessions")
                    jobs.append({"key": other["key"], "inputs": theirs})
                    live.append((other, theirs))
                answers = _decided(decider, jobs, tally, restarts, what="start check", interrupted=StartCheckInterrupted)
                seen += 1
                ra, erred_a = answers[a]
                for other, theirs in live:
                    out = other["out"]
                    k = i - out["shift"]  # the later run's own decision session
                    if k < warm:
                        # Before its warm-up ends a later run is held to the base run only where both show the same
                        # book: there nothing but the run's own standing can make the two decides differ.
                        if not same_book(inputs, theirs):
                            continue
                        out["early"] += 1
                    rb, erred_b = answers[other["key"]]
                    out["sessions"] += 1
                    mine, yours = start_orders(ra.get("intents"), inputs), start_orders(rb.get("intents"), theirs)
                    asked = bool(mine or yours)  # a session on which either run asked an order
                    out["active"] += int(asked)
                    what = None
                    if erred_a is None or erred_b is None:
                        out["disqualified"] += 1  # a disqualified instance answers nothing: no match
                        what = "disqualified"
                    elif erred_a != erred_b:
                        out["failed"] += 1  # one decide failed (or returned a malformed intent) and the other did not
                        what = "failed"
                    else:
                        same, gaps = same_intents(mine, yours)
                        if gaps:
                            out["sized"] += 1
                            for unit, gap in gaps.items():
                                size_gap[unit] = max(size_gap.get(unit, 0.0), gap)
                        if not same:
                            what = "size" if gaps else "orders"
                    if what is None:
                        out["matched"] += 1
                        out["active_matched"] += int(asked)
                        continue
                    if len(out["misses"]) < START_MISSES:
                        out["misses"].append(k)
                    if out["first_miss"] is None:
                        out["first_miss"] = {"session": k, "what": what, "base": _orders_text(mine)[:240],
                                             "later": _orders_text(yours)[:240]}
            if seen != len(days):
                raise StartCheckInterrupted(f"Train span {span} gave the start check {seen} sessions for {len(days)} "
                                            "decisions")
            for other in others:
                if next(other["inputs"], None) is not None:
                    raise StartCheckInterrupted(f"the run started {other['out']['shift']} sessions into Train span "
                                                f"{span} has a session after the span's last")
                runs.append(other["out"])
            for key in list(loaded):
                loaded.remove(key)
                decider.kind_drop(KIND, key)
    finally:
        for key in list(loaded):
            try:
                decider.kind_drop(KIND, key)
            except Exception:  # noqa: BLE001 - a drop that fails leaves an instance a restart clears
                pass
    if not runs or warm is None:
        raise StartCheckInterrupted("no Train span is long enough for a later start: the start check had no run to "
                                    "compare")
    for out in runs:
        out["share"] = round(out["matched"] / out["sessions"], 4) if out["sessions"] else 0.0
        out["active_share"] = round(out["active_matched"] / out["active"], 4) if out["active"] else 1.0
        out["held"] = (bool(out["sessions"]) and out["matched"] >= need * out["sessions"] - 1e-9
                       and out["active_matched"] >= busy * out["active"] - 1e-9)
    sessions = sum(out["sessions"] for out in runs)
    matched = sum(out["matched"] for out in runs)
    worst = next((out for out in runs if not out["held"]), None) or next((out for out in runs if out["first_miss"]), None)
    first_miss = {"span": worst["span"], "shift": worst["shift"], **worst["first_miss"]} \
        if worst is not None and worst["first_miss"] else None
    return {"sessions": sessions, "matched": matched, "share": min(out["share"] for out in runs), "need": need,
            "active": sum(out["active"] for out in runs), "active_matched": sum(out["active_matched"] for out in runs),
            "active_share": min(out["active_share"] for out in runs), "active_need": busy,
            "warm": warm, "shifts": [int(x) for x in BAR["start_shifts"]], "runs": runs, "skipped": skipped,
            "disqualified": sum(out["disqualified"] for out in runs), "failed": sum(out["failed"] for out in runs),
            "sized": sum(out["sized"] for out in runs),
            "size_gap": {unit: float(f"{gap:.2g}") for unit, gap in sorted(size_gap.items())},
            "held": all(out["held"] for out in runs), "first_miss": first_miss}


#: What of a start check the record keeps (`with_start`): counts, sessions counted from a later run's own start and the
#: program's own orders in words; no day and no market figure.
START_KEYS = ("sessions", "matched", "share", "need", "active", "active_matched", "active_share", "active_need", "warm",
              "shifts", "runs", "skipped", "disqualified", "failed", "sized", "size_gap", "first_miss")


def with_start(verdict: Mapping[str, Any], check: Mapping[str, Any]) -> dict[str, Any]:
    """A bar verdict with its start check: as it was when the check held, else failed START (its Train figures and its
    restart check kept, so the brief shows what the program earned). A check with no session compared never holds."""
    out = dict(verdict)
    out["start"] = {k: check.get(k) for k in START_KEYS}
    if not check.get("held") or not check.get("sessions"):
        out.update(passed=False, fails=["START"],
                   why=f"{FAILS['START']}: the lowest later run matched {_pct(check.get('share'))} of its sessions and "
                       f"{_pct(check.get('active_share'))} of those with an order")
    return out


def _update(store: Any, fid: str, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Read-modify-write the family's record under the store's lock."""
    with store.atomic():
        fam = store.family(fid) or {}
        rec = record_of(fam)
        rec.setdefault("status", "researching")
        rec.setdefault("versions", {})
        change(rec)
        rec["last_at"] = store.now()
        store.set_state(fid, **{STATE_KEY: rec})
    return rec


# ----------------------------------------------------------------------------------------------------------- the map
def train_map(store: Any) -> list[dict[str, Any]]:
    """THE EQUITY TRAIN MAP's rows, one a cell (the module docstring), the cells with a pass first, then by births."""
    cells: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fam in elane_seal.equity_families(store):
        if not e2_family(fam):
            continue
        facts = elane_seal.train_facts(fam, STATE_KEY)
        rec = facts["record"]
        cell = cell_of(facts["lane"], facts["agenda"], facts["symbols"])
        row = cells.setdefault(cell, {"cell": cell, "births": 0, "scored": 0, "passed": 0, "refuted": 0, "stalled": 0,
                                      "best_t": None})
        row["births"] += 1
        versions = rec.get("versions") if isinstance(rec.get("versions"), Mapping) else {}
        row["scored"] += int(bool(versions))
        n = rec.get("passed_version")
        if isinstance(n, int) and not isinstance(n, bool):
            row["passed"] += 1
            t = _num((versions.get(str(n)) or {}).get("score"))
            if t is not None and (row["best_t"] is None or t > row["best_t"]):
                row["best_t"] = t
        # A refutation counts only with a version the bar judged on the mechanism (a family refuted before this rule with
        # none reads as stalled): the House's failures and programs that never ran close no cell.
        refuted = rec.get("status") == "refuted"
        row["refuted"] += int(refuted and judged(rec) > 0)
        row["stalled"] += int(rec.get("status") == "stalled" or (refuted and judged(rec) == 0))
    return sorted(cells.values(), key=lambda r: (-r["passed"], -r["births"], r["cell"]))


def closed_cells(store: Any, settings: Mapping[str, Any] | None) -> list[tuple[str, str, str]]:
    """The cells with at least `refuted_cell_cap` Train refutations (each with a version the bar judged) and no Train
    pass: a birth there is refused."""
    cap = cfg(settings)["refuted_cell_cap"]
    return [r["cell"] for r in train_map(store) if r["refuted"] >= cap and not r["passed"]]


def train_map_text(store: Any, settings: Mapping[str, Any] | None, *, limit: int = 40) -> str:
    """THE EQUITY TRAIN MAP for the architect's equity request ("" with no E2 family yet). Train facts only."""
    rows = train_map(store)
    if not rows:
        return ""
    closed = set(closed_cells(store, settings))
    lines = [f"EQUITY TRAIN MAP (lane / mechanism / universe group; {MAP_LABEL}). Each cell: births, families "
             "Train-scored, passed equity-v1 and the equity review (the best passing pooled daily t at 1.0x), refuted on "
             "Train by the bar, stalled (no program of the family could be judged: nothing said of the mechanism):"]
    for r in rows[:limit]:
        best = f" (best t {r['best_t']:.1f})" if r["best_t"] is not None else ""
        shut = "; CLOSED: no birth here" if r["cell"] in closed else ""
        lines.append(f"- {cell_text(r['cell'])}: births {r['births']}, scored {r['scored']}, passed {r['passed']}{best}, "
                     f"refuted {r['refuted']}, stalled {r['stalled']}{shut}")
    if len(rows) > limit:
        lines.append(f"- ... and {len(rows) - limit} more cells")
    return "\n".join(lines)


def refuted_rows(store: Any, *, limit: int = 30) -> list[dict[str, Any]]:
    """E2's equity graveyard: the families it refuted on Train with a version the bar judged (from its record, newest
    first): {id, lane, agenda, symbols, mechanism, codes, versions, why}. The rows that bind the equity cards
    (`closed_cells`); a stalled family is none."""
    out = []
    for fam in elane_seal.equity_families(store):
        if not e2_family(fam):
            continue
        facts = elane_seal.train_facts(fam, STATE_KEY)
        refuted = facts["record"].get("refuted")
        if facts["record"].get("status") != "refuted" or not isinstance(refuted, Mapping) or not judged(facts["record"]):
            continue
        out.append({"id": facts["id"], "lane": facts["lane"], "agenda": facts["agenda"], "symbols": facts["symbols"],
                    "mechanism": facts["mechanism"][:200], "codes": list(refuted.get("codes") or []),
                    "versions": int(refuted.get("versions") or 0), "why": str(refuted.get("why") or "")[:300],
                    "at": str(refuted.get("at") or "")})
    return sorted(out, key=lambda r: (r["at"], r["id"]), reverse=True)[:limit]


# ----------------------------------------------------------------------------------------------------------- programs
def needs_literal(code: str) -> dict[str, Any] | None:
    """The program's NEEDS when it is a literal dict at the top level, else None."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == "NEEDS":
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                return None
            return dict(value) if isinstance(value, dict) else None
    return None


def check_code(code: Any, symbols: Sequence[str]) -> str | None:
    """Why a program cannot be a version of a family trading `symbols`, or None: the Gym's static rules
    (`league.gym.safety.check_program`, never executed here), NEEDS a literal dict whose symbols are the family's, the
    equity memory rule (`elane_review.memory_text`: no object of a module held as memory) and the equity level rule
    (`elane_review.level_text`)."""
    from ..gym.safety import CodeRefused, check_program

    text = str(code or "")
    try:
        check_program(text)
    except CodeRefused as exc:
        return f"refused by the code rules: {str(exc)[:300]}"
    except Exception as exc:  # noqa: BLE001 - an unreadable program is refused
        return f"refused: {type(exc).__name__}"
    needs = needs_literal(text)
    if needs is None:
        return "NEEDS must be a literal dict at the top level ({\"symbols\": [...], \"history\": n, \"max_hold_sessions\": n})"
    named = needs.get("symbols")
    if not isinstance(named, list) or not named:
        return "NEEDS[\"symbols\"] must be a non-empty list of the family's symbols"
    own = {str(s).upper() for s in symbols}
    foreign = [str(s) for s in named if str(s).upper() not in own]
    if foreign:
        return f"NEEDS names {', '.join(foreign[:6])}, outside the family's symbols ({', '.join(sorted(own))})"
    # THE MEMORY RULE (league/swarm/elane_review.py): an object that belongs to a module is memory outside STATE, shared
    # by every program in the decider child.
    memory = elane_review.memory_text(text)
    if memory is not None:
        return memory
    # THE LEVEL RULE (league/swarm/elane_review.py): a raw price or volume level held against a constant or a PARAMS
    # value, and the run's own dollars held against a constant or the run's anchor.
    return elane_review.level_text(text)


_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def program_of(answer: Mapping[str, Any] | None) -> tuple[str | None, str, str | None]:
    """(the program, its note, a stop reason) from a researcher's answer: the JSON's `program` (else the first fenced
    Python block of its text), its `note`; `stop` when it gave up."""
    from .models import extract_json

    answer = answer or {}
    data = answer.get("json") if isinstance(answer.get("json"), Mapping) else extract_json(str(answer.get("text") or ""))
    data = data if isinstance(data, Mapping) else {}
    stop = data.get("stop")
    if isinstance(stop, str) and stop.strip():
        return None, "", " ".join(stop.split())[:400]
    code = data.get("program")
    if not isinstance(code, str) or "def decide" not in code:
        found = _FENCE.search(str(answer.get("text") or ""))
        code = found.group(1) if found else None
    return (code if isinstance(code, str) and code.strip() else None), " ".join(str(data.get("note") or "").split())[:400], None


def contract_text() -> str:
    """EQUITY.md, the program contract, as the House holds it (core's file; a short stand-in when it cannot be read)."""
    from pathlib import Path

    try:
        return (Path(__file__).resolve().parents[1] / "equity" / "EQUITY.md").read_text()[:12000]
    except OSError:
        return ("An equity program is one Python file: NEEDS = {\"symbols\": [...], \"history\": n, \"max_hold_sessions\": n}, "
                "PARAMS = {...}, and decide(ctx) returning intents: {\"buy\": SYM, \"share\": 0..1, \"at\": \"open\" | "
                "\"close\"}, {\"sell\": lot id}, {\"cancel\": order id}. math and numpy only; no date.")


# ----------------------------------------------------------------------------------------------------------- the researcher
RESEARCHER_SYSTEM = """You write ONE program for one family of the swarm's EQUITY LANES: long-only ETF programs (stocks in
a later release) that the House runs once a session after the close, each order executing at the next session's open or
close. You see your own family's Train runs (Train years 2016-19 and 2022-24) and nothing else: no Validation figure, no
holdout figure and no other program's outcome. Validation (2025) and ONE sealed holdout look per lineage judge every
program, and nothing of them ever reaches a program's author, so a program cannot be fitted to them: write the mechanism,
not the history. The first version that passes the Train bar in the request AND the equity review is your lineage's ONE
Validation try: send the version you would stake the lineage on. A rule that works only because you know which years fell
is not a mechanism; use scale-free state (returns, volatility, a price against its own moving average or recent high, the
calendar fields), never a price level or a date. THE LEVEL RULE refuses, before it runs, a program that holds a price, an
average or range of prices, a lot's entry or mark, a share volume, or the log of any of them, against a constant or a
PARAMS value (compared with, offset by, bucketed by or clipped at one); a ratio of two levels of the SAME symbol is fine
(a ratio of two different symbols' prices against a constant is not). It also refuses RUN-START DEPENDENCE: every judged
run starts flat with the same capital (ctx.budget), so never hold ctx.equity, ctx.cash, ctx.budget, ctx.caps or a lot's
value, pnl or qty against a constant or a PARAMS value, never the sleeve's dollars against ctx.budget, ctx.caps or what
a lot cost (its qty times a price, its value less its pnl), and never write them into a lot's tag (no profit lock, no
sleeve-wide stop, no size that changes once the run is ahead or behind, whatever its spelling): size by a share of the
sleeve, check a sign (a lot's pnl below zero) and exit on a lot's own return (mark over entry). THE REVIEW (two
other models) refuses absolute levels, a calendar reconstructed by counting sessions in STATE, tables of dates or levels,
run-start dependence and lookahead. THE STATE RULE (part of the bar): the House's decider restarts on every deploy and a restart empties STATE,
so the bar runs your program again with STATE emptied every 20 sessions and fails it (STATE) unless its intents match the
uninterrupted run's on 99% of sessions. Keep in STATE only a cache of what ctx gives again; read holdings from
ctx.positions and the clock from ctx's calendar fields, never from a count you keep. Your decide must work on an empty
STATE at any session, lots held or not: a decide that raises after a restart is no match. Never carry a value from
session to session and update it in place (a running sum, a moving average, a peak since entry): ctx's history is
adjusted as of each session and rounded, so the carried value drifts from what ctx gives now and your buys' sizes differ
(they must agree to six places of a share); recompute it from ctx.bars at every call. THE START RULE (part of the bar):
the House starts every program live on a fresh date and every judged run starts flat, so the bar runs your program again
from later starts inside each Train span and fails it (START) unless its orders match the run from the span's start on
99% of each later run's sessions and on 95% of those where either run asked an order. Decide from ctx.bars, ctx's calendar fields and each lot's own facts (its symbol, entry,
mark, held_sessions, its own return) alone, never from how your run stands: not ctx.equity, ctx.cash or ctx.caps, not a
lot's qty, value, pnl or weight in the sleeve as a measure of the run, not a lot's id, not a value carried from earlier
lots in a tag or in STATE, not a count of sessions, lots or wins since the run began. Size a buy by a constant share of
the sleeve. A hold that simply ends at the House's max-hold exit and is bought again at once is counted from the run's
start too: exit and re-enter on ctx's calendar (ctx.weekday, ctx.session_of_month) or on a market condition.

Reply with ONE JSON object: {"program": "<the whole Python file>", "note": "what this version changes and why, one or two
sentences"}; or, once a version of yours was judged by the bar (Y1, Y2, P1 or R1) and no honest revision is left,
{"stop": "why, in one or two sentences"}. PARAMS are your program's own declaration (the House runs it as written).

THE PROGRAM CONTRACT (league/equity/EQUITY.md):
"""


def _usd(x: Any) -> str:
    v = _num(x)
    return "n/a" if v is None else (f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}")


def _t(x: Any) -> str:
    v = _num(x)
    return "n/a" if v is None else f"{v:.2f}"


def version_text(n: Any, v: Mapping[str, Any]) -> str:
    """One scored version in words (Train figures, its restart and start checks' counts and the review's reasons
    only)."""
    fails = list(v.get("fails") or [])
    if not v.get("years") and fails and fails[0] in ("RUN", "DQ", "LOAD", "WINDOW"):
        return f"v{n}: {v.get('why') or FAILS[fails[0]]}."
    s = v.get("summary") or {}
    side = v.get("beside") or {}
    if "REVIEW" in fails:
        status = "passed the Train bar but the EQUITY REVIEW refused it"
    elif "STATE" in fails:
        status = "met Y1, Y2, P1 and R1 but failed STATE"
    elif "START" in fails:
        status = "met Y1, Y2, P1, R1 and STATE but failed START"
    else:
        status = "PASSED" if v.get("passed") else "failed " + ", ".join(fails)
    head = (f"v{n}: {status}. At 1.0x: net P&L "
            f"{_usd(v.get('pnl_10'))}, pooled daily t {_t(v.get('score'))}, closed lots "
            f"{int(_num(s.get('trades')) or 0)}, entry days {int(_num(s.get('days_traded')) or 0)}, mean exposure "
            f"{_t(s.get('exposure_mean'))}; at 1.5x: net P&L {_usd(v.get('pnl_15'))}.")
    years = "; ".join(f"{y} {'IN' if r.get('active') else 'out'} lots {r.get('trades')} entry days {r.get('days_traded')} "
                      f"P&L {_usd(r.get('pnl'))} t {_t(r.get('t'))}" for y, r in sorted((v.get("years") or {}).items()))
    beside = (f"Beside (never a bar): the same-exposure buy-and-hold {_usd(side.get('bh_pnl'))}, MTE mean "
              f"{_t(side.get('mte_mean'))} (t {_t(side.get('mte_t'))}), drift share {_t(side.get('drift_share'))}.")
    words = " ".join(f"({f}) {FAILS[f]}." for f in fails if f in FAILS and f != "REVIEW")
    review = v.get("review") if isinstance(v.get("review"), Mapping) else {}
    said = "; ".join(str(r) for r in (review.get("reasons") or [])[:3])
    told = f"(REVIEW) the {review.get('stage') or 'review'} refused it: {said or FAILS['REVIEW']}." if "REVIEW" in fails else ""
    return " ".join(x for x in (head, f"By Train year: {years}." if years else "", beside, words, restart_text(v),
                                start_text(v), told) if x)


def restart_text(v: Mapping[str, Any]) -> str:
    """A version's restart check in words ("" when it had none): the sessions matched and where they first differed."""
    state = v.get("state") if isinstance(v.get("state"), Mapping) else None
    if not state or not state.get("sessions"):
        return ""
    miss = state.get("first_miss") if isinstance(state.get("first_miss"), Mapping) else None
    where = (f"; they first differed on session {int(_num(miss.get('after_reset')) or 0) + 1} after a reset" if miss else "")
    gone = int(_num(state.get("disqualified")) or 0)
    lost = f"; on {gone} sessions an instance was disqualified by its own errors (no match)" if gone else ""
    broke = int(_num(state.get("failed")) or 0)
    fell = (f"; on {broke} sessions the decide failed (raised, timed out or returned a malformed intent) in one run and "
            "not in the other (no match): a decide must work on an empty STATE at any session, lots held or not"
            if broke else "")
    sized = int(_num(state.get("sized")) or 0)
    gaps = state.get("size_gap") if isinstance(state.get("size_gap"), Mapping) else {}
    by = " and ".join(x for x in (f"{_num(gaps.get('share')):.2g} of the sleeve" if _num(gaps.get("share")) else "",
                                  f"${_num(gaps.get('usd')):.2g}" if _num(gaps.get("usd")) else "") if x)
    size = (f"; on {sized} sessions the two runs gave the same orders and differed only in a buy's size"
            + (f" (by at most {by})" if by else "") + ": a value carried in STATE from session to session and updated "
            "in place drifts from what ctx gives now, so recompute it from ctx.bars at every call" if sized else "")
    return (f"Restart check: with STATE emptied every {state.get('every')} sessions, its intents matched the uninterrupted "
            f"run's on {state.get('matched')} of {state.get('sessions')} Train sessions ({_pct(state.get('share'))}; "
            f"{_pct(state.get('need'))} needed){where}{lost}{fell}{size}.")


def start_text(v: Mapping[str, Any]) -> str:
    """A version's start check in words ("" when it had none): the later runs, the sessions that matched, and for a
    version that failed it which later run fell short, the sessions that differed (counted from that run's own first
    decision: never a day), what the two runs asked where they first differed, and what a program may decide from."""
    start = v.get("start") if isinstance(v.get("start"), Mapping) else None
    if not start or not start.get("sessions"):
        return ""
    runs = [r for r in (start.get("runs") or []) if isinstance(r, Mapping)]
    shifts = " and ".join(str(x) for x in (start.get("shifts") or []))
    left = [s for s in (start.get("skipped") or []) if isinstance(s, Mapping)]
    short = (f" ({len(left)} later start{'s' if len(left) != 1 else ''} did not fit a span after the warm-up and "
             f"{'were' if len(left) != 1 else 'was'} not run)" if left else "")
    head = (f"Start check: run again from {shifts} sessions into each Train span (every run starts flat){short}, its "
            f"orders matched the run from the span's start on {start.get('matched')} of {start.get('sessions')} compared "
            f"sessions, and on {start.get('active_matched')} of the {start.get('active')} on which either run asked an "
            f"order; the lowest of the {len(runs)} later runs matched {_pct(start.get('share'))} of its sessions "
            f"({_pct(start.get('need'))} needed of each) and {_pct(start.get('active_share'))} of those with an order "
            f"({_pct(start.get('active_need'))} needed)")
    failed = [r for r in runs if not r.get("held")]
    if not failed:
        return head + "."
    said = []
    for r in failed[:2]:
        misses = [int(k) + 1 for k in (r.get("misses") or []) if _num(k) is not None]
        lost = int(_num(r.get("sessions")) or 0) - int(_num(r.get("matched")) or 0)
        more = f" and {lost - len(misses)} more" if lost > len(misses) else ""
        said.append(f"the run started {r.get('shift')} sessions into span {int(_num(r.get('span')) or 0) + 1} matched "
                    f"{r.get('matched')} of {r.get('sessions')} ({r.get('active_matched')} of {r.get('active')} with an "
                    f"order) and differed on its sessions {', '.join(str(k) for k in misses)}{more}")
    miss = start.get("first_miss") if isinstance(start.get("first_miss"), Mapping) else None
    kinds = {"size": "the two runs asked the same orders in different sizes",
             "failed": "the decide failed (raised, timed out or returned a malformed intent) in one run and not in the "
                       "other",
             "disqualified": "an instance was disqualified by its own errors", "orders": "the two runs asked different "
                                                                                           "orders"}
    where = ""
    if miss:
        where = (f" Where the run started {miss.get('shift')} sessions into span {int(_num(miss.get('span')) or 0) + 1} "
                 f"first differed (its session {int(_num(miss.get('session')) or 0) + 1}), "
                 f"{kinds.get(str(miss.get('what')), kinds['orders'])}: the run from the span's start asked "
                 f"[{miss.get('base')}], the later run asked [{miss.get('later')}].")
    sized = int(_num(start.get("sized")) or 0)
    gaps = start.get("size_gap") if isinstance(start.get("size_gap"), Mapping) else {}
    by = " and ".join(x for x in (f"{_num(gaps.get('share')):.2g} of the sleeve" if _num(gaps.get("share")) else "",
                                  f"${_num(gaps.get('usd')):.2g}" if _num(gaps.get("usd")) else "") if x)
    size = (f" On {sized} sessions in all the orders were the same and only a buy's size differed"
            + (f" (by at most {by})" if by else "") + ": size a buy by a constant share of the sleeve, never by dollars "
            "worked out from ctx.equity, ctx.cash or ctx.caps." if sized else "")
    rest = f"; {len(failed) - 2} more later runs fell short too" if len(failed) > 2 else ""
    return (f"{head}: {'; '.join(said)}{rest} (sessions are counted from a later run's own first decision).{where}{size} "
            f"{START_ADVICE}")


#: What a version that failed START is told (`start_text`), and what the bar and the researcher's prompt say before one
#: is written.
START_ADVICE = ("The House starts every program live on a fresh date, so a program must give the same orders whenever "
                "its run began: decide from ctx's bars, its calendar fields and each lot's own facts (its symbol, entry, "
                "mark, held_sessions and own return) alone, NEVER from how the run stands: not ctx.equity, ctx.cash or "
                "ctx.caps, not a lot's qty, value, pnl or weight in the sleeve as a measure of the run, not a lot's id, "
                "not a value carried from earlier lots in a tag or in STATE, not a count of sessions, lots or wins since "
                "the run began. Size a buy by a constant share of the sleeve. A hold that ends at the House's max-hold "
                "exit and is bought again at once is counted from the run's start too: exit and re-enter on ctx's "
                "calendar or on a market condition.")


def _pct(x: Any) -> str:
    v = _num(x)
    return "n/a" if v is None else f"{100 * v:.1f}%"


def _named(exc: BaseException, names: Sequence[str]) -> bool:
    return any(cls.__name__ in names for cls in type(exc).__mro__)


class EquityResearcher:
    """THE RESEARCHER (the module docstring). `runner` is E1's `league.equity.runner.Isolated` (built lazily from
    `elane.isolated_runner(root)` when not handed in); `router` the swarm's `ModelRouter`."""

    def __init__(self, store: Any, router: Any, settings: Mapping[str, Any], *, runner: Any = None, root: Any = None,
                 clock: Callable[[], float] = time.time):
        self.store = store
        self.router = router
        self.settings = settings
        self._runner = runner
        self.root = root if root is not None else getattr(store, "root", None)
        self.clock = clock
        #: When `due` last looked and found nothing a round could do, and the equity pass's clock it saw then (in
        #: memory: no key, no event, no log line).
        self._looked: tuple[float, Any] = (float("-inf"), None)

    # ------------------------------------------------------------------ plumbing
    def runner(self) -> Any:
        if self._runner is None:
            from . import elane

            self._runner = elane.isolated_runner(self.root)
        return self._runner

    def due(self) -> bool:
        """The lane is on, `train_every_seconds` passed since the last round (or since the last look that found nothing
        to do), and a round has WORK it can do now (`idle`). So while `elane.birth_share` has been zero since the start
        (no equity pass ever bore a family) no round runs, no key is written and no event is made: with the births off
        E2 does nothing at all. Nor does a round start while every family of E2's is past its research (a Candidate or
        a Probe program lives for weeks), waits out a backoff, or needs a model E2 may not ask now: before, one empty
        round every ten minutes left an event and a log line each (the integration review's merge-4)."""
        if not lane_on(self.settings):
            return False
        now = self.clock()
        if now - (_num(self.store.get(TRAIN_AT_KEY)) or 0.0) < cfg(self.settings)["train_every_seconds"]:
            return False
        try:
            # Nothing to do is looked at again every `IDLE_LOOK_SECONDS`, and at once after an equity pass (a birth).
            births_at = self.store.get(BIRTHS_AT)
            if births_at == self._looked[1] and 0.0 <= now - self._looked[0] < IDLE_LOOK_SECONDS:
                return False
            if self.idle():
                self._looked = (now, births_at)
                return False
            return True
        except Exception:  # noqa: BLE001 - a store that cannot be read gives no round
            return False

    def idle(self) -> bool:
        """No round has work it can do now: no E2 family retired elsewhere with its record still saying it researches
        (`close_retired`'s work), no standing pass whose review record or best version an adoption cleared (`upkeep`'s),
        and no family of the queue whose step can be taken now (`needs_model`: one that must ask a model is no work
        while E2 may ask none, `elane_yield.hold`). The captain's seeds are never E2's."""
        for fam in elane_seal.equity_families(self.store, alive=False):
            if e2_family(fam) and record_of(fam).get("status", "researching") == "researching":
                return False
        if self.upkeep(dry=True):
            return False
        queue = self.queue()
        if not queue:
            return True
        if elane_yield.hold(self.store, self.settings, self.clock()) is None:
            return False
        return all(self.needs_model(fam) for fam in queue)

    def needs_model(self, fam: Mapping[str, Any]) -> bool:
        """Whether a family's next step (`step`) asks a model: a review still to be read, or a program to be written.
        Re-scoring a stale pass, scoring its newest version and retiring it ask none."""
        c = cfg(self.settings)
        fid = str(fam["id"])
        rec = record_of(fam)
        if rec.get("status") == "passed":
            return False
        pending = rec.get("review") if isinstance(rec.get("review"), Mapping) else None
        if pending is not None and pending.get("version") is not None:
            return True
        latest = self.store.latest_version(fid)
        versions = versions_of(rec)
        if latest is not None and str(latest["n"]) not in versions:
            return False
        return not (len(versions) >= c["train_budget"] or int(rec.get("attempts") or 0) >= c["train_max_attempts"])

    def waiting(self, rec: Mapping[str, Any]) -> bool:
        """Whether a family waits out a backoff: after a failure of the House's (`infra.next_at`), or after a question
        of its own no route answered (`unanswered.next_at`)."""
        for name in ("infra", "unanswered"):
            held = rec.get(name) if isinstance(rec.get(name), Mapping) else {}
            if (_num(held.get("next_at")) or 0.0) > self.clock():
                return True
        return False

    def unanswered(self, fid: str, what: str, errors: Sequence[str]) -> dict[str, Any]:
        """A QUESTION NO ROUTE ANSWERED (a Train write, a review or an audit read): nothing is counted against the
        program, and the family waits out a backoff before it asks again (`train_every_seconds` doubling with every
        question in a row left unanswered, at most `BACKOFF_MAX`), as it does after a failure of the House's. Without it
        a family whose routes were down asked every route again each round under a fresh key, each timed-out call a
        hold on the swarm's meter (the integration review's loop-2). An answered question clears it (`answered`)."""
        c = cfg(self.settings)
        now = self.clock()
        held = record_of(self.store.family(fid) or {}).get("unanswered")
        count = int(held.get("count") or 0) + 1 if isinstance(held, Mapping) else 1
        delay = min(float(c["train_every_seconds"]) * (2 ** min(count, 12)), BACKOFF_MAX)
        record = {"count": count, "at": now, "next_at": now + delay, "what": what,
                  "sent": not elane_yield.unsent(errors)}
        _update(self.store, fid, lambda r: r.update(unanswered=record))
        return {"family": fid, "error": f"no {what} route answered" if what != "train" else "no route answered",
                "errors": list(errors)[:3], "retry_in": delay}

    def reader_now(self, route: Any) -> str:
        """The model that would answer `route` NOW: its own, or, for a Sail profile whose window is flagged stalled, the
        model of the asap profile the router's window fallback sends E2's role to (league/swarm/models.py
        `sail_fallback`: k3_balanced and pro_balanced both fall to pro_asap for a role that is not the gate's audit)."""
        if getattr(route, "kind", None) == "sail":
            try:
                fallback = self.router.sail_fallback(route.name, role=elane_yield.ROLE)
                if fallback is not None and self.router.window_stalled(fallback[0]) is not None:
                    return elane_review.model_of(f"sail:{fallback[1]}")
            except Exception:  # noqa: BLE001 - a router that cannot say: the route's own model
                pass
        return elane_review.model_of(route.key)

    def queue(self) -> list[dict[str, Any]]:
        """The living E2 families with a step to take (researching, or a pass to re-score under a new equity identity),
        none waiting out a backoff, the least recently worked first, at most `train_per_round`."""
        rows = []
        for fam in elane_seal.equity_families(self.store, alive=True):
            if not e2_family(fam):
                continue
            rec = record_of(fam)
            status = rec.get("status", "researching")
            if self.waiting(rec):
                continue
            if status == "researching" or (status == "passed" and not pass_current(self.store, fam)):
                rows.append((str(rec.get("last_at") or ""), str(fam.get("born_at") or ""), fam))
        rows.sort(key=lambda r: (r[0], r[1], str(r[2]["id"])))
        return [r[2] for r in rows[: cfg(self.settings)["train_per_round"]]]

    def run(self) -> dict[str, Any]:
        """One round: the upkeep of the passes, then a step for each family of the queue; one `swarm.elane` event when
        anything was done (a step, a record closed, a pass restored), none for a round that found nothing."""
        self.store.put(TRAIN_AT_KEY, self.clock())
        if not lane_on(self.settings):
            return {"pass": "train", "skipped": "the equity lanes are off (elane.mode)"}
        closed = self.close_retired()
        kept = self.upkeep()
        steps = []
        for fam in self.queue():
            try:
                steps.append(self.step(fam))
            except Exception as exc:  # noqa: BLE001 - one family's trouble never stops the round
                steps.append({"family": fam["id"], "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
        out: dict[str, Any] = {"pass": "train", "steps": steps}
        if closed:
            out["closed"] = closed
        if kept:
            out["restored"] = kept
        if steps or closed or kept:
            self.store.event("swarm.elane", None, out)
        return out

    def close_retired(self) -> list[str]:
        """E2 families retired outside E2 while their record says they research: their record is closed ("closed"),
        so the equity request's counts stop holding them (the record alone is what the generators read)."""
        out = []
        for fam in elane_seal.equity_families(self.store, alive=False):
            if e2_family(fam) and record_of(fam).get("status", "researching") == "researching":
                _update(self.store, str(fam["id"]), lambda r: r.update(status="closed"))
                out.append(str(fam["id"]))
        return out

    def upkeep(self, *, dry: bool = False) -> list[str]:
        """THE PASSES KEPT IN FORCE (the module docstring, THE IDENTITY): for each living E2 family whose current pass
        stands, the review record E1's look reads and the family's `best_version` are written again when they are missing
        (E1's equity adoption clears both). No model is asked and nothing is run. `dry`: the families it would write,
        nothing written (`idle`)."""
        from .gate import run_sha

        out = []
        for fam in elane_seal.equity_families(self.store, alive=True):
            if not e2_family(fam) or record_of(fam).get("status") != "passed" or not pass_current(self.store, fam):
                continue
            fid, n = str(fam["id"]), passed_version(fam)
            rec = record_of(fam)
            version = self.store.version(fid, n)
            kept = rec.get("passed_review") if isinstance(rec.get("passed_review"), Mapping) else None
            if version is None or kept is None:
                continue
            changed = False
            sha = run_sha(version)
            if kept.get("sha") == sha and not elane_review.holds(fam.get("state"), sha):
                if not dry:
                    self.store.set_state(fid, **{elane_review.STATE_REVIEW: dict(kept)})
                changed = True
            if fam.get("best_version") != n:
                if not dry:
                    score = (versions_of(rec).get(str(n)) or {}).get("score")
                    self.store.update_family(fid, best_version=n, best_train=score)
                changed = True
            if changed:
                out.append(fid)
        return out

    # ------------------------------------------------------------------ one family's step
    def step(self, fam: Mapping[str, Any]) -> dict[str, Any]:
        """One step of a family (the module docstring): re-score a stale pass; review a bar pass; score its newest
        unscored version; else, with budget left, ask for a program (its first, or a revision); else retire it."""
        c = cfg(self.settings)
        fid = str(fam["id"])
        rec = record_of(fam)
        if rec.get("status") == "passed":
            n = passed_version(fam)
            version = self.store.version(fid, n) if n is not None else None
            if version is None:
                return {"family": fid, "skipped": "its passing version cannot be read"}
            return self.score(fam, version, rescore=True)
        pending = rec.get("review") if isinstance(rec.get("review"), Mapping) else None
        if pending is not None and pending.get("version") is not None:
            return self.review_step(fam, int(pending["version"]))
        latest = self.store.latest_version(fid)
        versions = versions_of(rec)
        if latest is not None and str(latest["n"]) not in versions:
            return self.score(fam, latest)
        if len(versions) >= c["train_budget"] or int(rec.get("attempts") or 0) >= c["train_max_attempts"]:
            return self.finish(fam, "its Train budget is spent with no version passing")
        held = elane_yield.hold(self.store, self.settings, self.clock())
        if held is not None:  # the day's line, or E2's own hourly pace: no model is asked
            return {"family": fid, "skipped": held}
        return self.write(fam)

    def brief(self, fam: Mapping[str, Any]) -> str:
        """The question's user turn: the family's card, its agenda prior, the bar and its own Train versions (Train
        facts and the review's reasons only: league/swarm/elane_seal.py)."""
        from . import cards, elane

        c = cfg(self.settings)
        facts = elane_seal.train_facts(fam, STATE_KEY)
        rec = facts["record"]
        lane = facts["lane"]
        agenda = AGENDA.get(facts["agenda"], AGENDA["other"])
        try:
            card = (cards.card_of(self.store, facts["id"]) or {}).get("card") or {}
        except Exception:  # noqa: BLE001 - the brief goes without the card
            card = {}
        label = elane.LABELS.get(lane, str(lane).upper())
        lines = [f"YOUR FAMILY: {facts['id']}, lane {label}"
                 + (f" ({elane.BETA_NOTE})" if lane == BETA else "") + f". Symbols: {', '.join(facts['symbols'])}; "
                 f"structure {facts['structure']}. Mechanism: {facts['mechanism']}",
                 f"ITS AGENDA MECHANISM: {agenda['title']}: {agenda['text']}. Published priors: {agenda['priors']}."]
        for name in ("hypothesis", "comparison", "falsification"):
            if card.get(name):
                lines.append(f"CARD {name.upper()}: {card[name]}")
        lines.append(bar_text())
        done = sorted(((int(k), v) for k, v in versions_of(rec).items()), key=lambda kv: kv[0])
        if done:
            lines.append(f"YOUR VERSIONS ON TRAIN ({TRAIN_LABEL}):\n" + "\n".join(f"- {version_text(n, v)}" for n, v in done))
        refused = [r for r in (rec.get("refused") or []) if isinstance(r, Mapping)][-3:]
        if refused:
            lines.append("PROGRAMS REFUSED BEFORE THEY RAN:\n" + "\n".join(f"- {r.get('why')}" for r in refused))
        latest = self.store.latest_version(facts["id"])
        if latest is not None and latest.get("code"):
            lines.append(f"YOUR NEWEST PROGRAM (v{latest['n']}):\n```python\n{str(latest['code'])[:12000]}\n```")
        left = c["train_budget"] - len(done)
        lines.append(f"TRAIN BUDGET: {left} of {c['train_budget']} scored versions left"
                     + ("" if judged(rec) else "; none judged by the bar yet, so a stop is not accepted") + ". Write version "
                     f"{(latest['n'] + 1) if latest is not None else 1}: the whole file.")
        return "\n\n".join(lines)

    def write(self, fam: Mapping[str, Any]) -> dict[str, Any]:
        """Ask the family's birth route for its next program; store it as a version once it passes the static checks
        (a refusal is recorded and counts as an attempt)."""
        c = cfg(self.settings)
        fid = str(fam["id"])
        facts = elane_seal.train_facts(fam, STATE_KEY)
        first = elane_yield.Route.of(facts["route"]) if facts["route"] else None
        answer, route, errors = elane_yield.ask(
            self.router, self.store, self.settings, first=first, role=elane_yield.ROLE,
            system=RESEARCHER_SYSTEM + contract_text(), user=self.brief(fam), key=f"swarm:elane:train:{fid}:{int(self.clock())}",
            max_output=c["train_max_output_tokens"], effort=c["train_effort"], purpose="research", now=self.clock(), family=fid)
        if answer is None:
            return self.unanswered(fid, "train", errors)
        # An answered question is one attempt (`train_max_attempts`); a route that could not answer spends none.

        def answered(r: dict[str, Any]) -> None:
            r.pop("unanswered", None)
            r["attempts"] = int(r.get("attempts") or 0) + 1
        _update(self.store, fid, answered)
        code, note, stop = program_of(answer)
        if stop is not None:
            if not judged(record_of(self.store.family(fid) or fam)):
                # A stop before the bar judged anything refutes nothing: the mechanism was never tested (B8).
                why = (f"a stop is accepted only once a version was judged by the bar (Y1, Y2, P1 or R1); none was: "
                       f"{stop}")[:400]

                def unheard(r: dict[str, Any]) -> None:
                    r["refused"] = [*(r.get("refused") or []), {"at": self.store.now(), "why": why}][-5:]
                _update(self.store, fid, unheard)
                return {"family": fid, "refused": why, "route": route.key if route else None}
            self.store.note(fid, f"The equity researcher stopped: {stop}")
            return self.finish(self.store.family(fid) or fam, f"its researcher found the mechanism refuted on Train: {stop}")
        why = check_code(code, facts["symbols"]) if code else "the answer held no program"
        if why is not None:
            def refuse(r: dict[str, Any]) -> None:
                r["refused"] = [*(r.get("refused") or []), {"at": self.store.now(), "why": why}][-5:]
            _update(self.store, fid, refuse)
            return {"family": fid, "refused": why, "route": route.key if route else None}
        known = versions_of(record_of(self.store.family(fid) or fam))
        version = self.store.add_version(fid, str(code), {}, author=f"elane:{route.key if route else 'model'}",
                                         note=note or "the equity researcher's version")
        if str(version["n"]) in known:
            # The store keeps one version a program: the same file again is no new version (and no new Train run).
            why = f"the same program as v{version['n']}, already scored"

            def again(r: dict[str, Any]) -> None:
                r["refused"] = [*(r.get("refused") or []), {"at": self.store.now(), "why": why}][-5:]
            _update(self.store, fid, again)
            return {"family": fid, "refused": why, "route": route.key if route else None}
        out = {"family": fid, "version": version["n"], "route": route.key if route else None}
        latest = self.store.family(fid) or fam
        out["score"] = self.score(latest, version)
        return out

    # ------------------------------------------------------------------ the Train run
    def fault(self, fam: Mapping[str, Any], n: int, exc: BaseException, *,
              check: bool | str = False) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """A Train run's exception, or a check's (`check`: True or "state" the restart check's, "start" the start
        check's), judged (the module docstring, WHAT A VERDICT IS): (the program's verdict, None) for LOAD, or for RUN
        once the child failed it `train_max_errors` times in a row (no failure of another kind between them) while
        other programs' Train judgments completed; else (None, the House's backoff answer: "run" a child's failure,
        "state" a restart check that could not run or finish, "start" a start check that could not, "store" the
        rest)."""
        why = f"{type(exc).__name__}: {str(exc)[:200]}"
        if _named(exc, LOAD_REFUSALS):
            refusal = " ".join(str(exc).split())[:300]
            return program_fault("LOAD", refusal, said=refusal), None
        kind = "run" if _named(exc, RUN_FAILURES) else (
            "start" if check == "start" else "state" if check else "store")
        out = self.house_failure(fam, n, why, kind=kind)
        return (None, out) if out is not None else (program_fault("RUN", why, said=f"a {type(exc).__name__}"), None)

    def restart(self, fid: str, code: str, params: Mapping[str, Any], runs: Sequence[Any]) -> dict[str, Any]:
        """THE RESTART CHECK of a version on its uninterrupted 1.0x Train runs (`restart_check` over `state_inputs`),
        through the isolated runner's decider (E1's `Isolated.decider`)."""
        decider = getattr(self.runner(), "decider", None)
        if decider is None:
            raise StateCheckInterrupted("the isolated runner has no decider: the restart check cannot run")
        return restart_check(decider, code, params, name=fid, streams=[state_inputs(run) for run in runs])

    def start(self, fid: str, code: str, params: Mapping[str, Any], runs: Sequence[Any]) -> dict[str, Any]:
        """THE START CHECK of a version on its 1.0x Train runs (`start_check` over `later_runs`: the later starts are
        run here, through the isolated runner, and decided through its decider)."""
        runner = self.runner()
        decider = getattr(runner, "decider", None)
        if decider is None:
            raise StartCheckInterrupted("the isolated runner has no decider: the start check cannot run")
        return start_check(decider, code, params, name=fid,
                           spans=later_runs(runner, code, params, name=fid, runs=runs))

    def house_failure(self, fam: Mapping[str, Any], n: int, why: str, *, kind: str) -> dict[str, Any] | None:
        """A failure of the House's (the module docstring, WHAT A VERDICT IS): nothing scored, no budget, no model call; a
        backoff that doubles with every failure of the version, of any kind (`count`). COUNTED BY KIND: `streak` is the
        failures of this `kind` one after another (another kind in between starts it again, `streak_at` its first) and
        `kinds` every failure of each kind since the version was last judged. For a child's run failure ("run") whose
        streak reaches `train_max_errors` while other programs' Train judgments completed since the streak's first,
        None: the caller judges the program RUN (never on the strength of the House's other failures). A result outside
        the Train years ("window") is an alert at once; a restart check that could not run or finish ("state"), and a
        start check that could not ("start"), once each, when the version has `train_max_errors` of them (one restart
        of the child is no news; a check that never finishes is), whatever failed in between. A STANDING FAILURE OF THE HOUSE'S ("run": the child fails every
        program's runs; "store": no equity store, a store being rewritten for good) is an alert too, when a version has
        `train_max_errors` of that kind since it was last judged, and at most once every `BACKOFF_MAX` for the lanes
        whichever family meets it (`HOUSE_ALERT_KEY`): before, every Train score ended in a backoff doubling to six
        hours, births went on until the lanes were full, and nobody was told (the integration review's loop-5)."""
        c = cfg(self.settings)
        fid = str(fam["id"])
        now = self.clock()
        held = record_of(self.store.family(fid) or fam).get("infra")
        held = dict(held) if isinstance(held, Mapping) and held.get("version") == n else {}
        count = int(held.get("count") or 0) + 1
        first = _num(held.get("first_at")) or now
        again = held.get("kind") == kind
        streak = (int(held.get("streak") or 0) if again else 0) + 1
        since = (_num(held.get("streak_at")) if again else None) or now
        kinds = {str(k): int(v) for k, v in (held.get("kinds") if isinstance(held.get("kinds"), Mapping) else {}).items()
                 if isinstance(v, int) and not isinstance(v, bool)}
        kinds[kind] = kinds.get(kind, 0) + 1
        alerted = [str(k) for k in (held.get("alerted") if isinstance(held.get("alerted"), list) else [])]
        if kind == "run" and streak >= c["train_max_errors"] and (_num(self.store.get(TRAIN_OK_KEY)) or 0.0) > since:
            return None
        delay = min(float(c["train_every_seconds"]) * (2 ** min(count - 1, 12)), BACKOFF_MAX)
        tell = kind in ("state", "start") and kinds[kind] >= c["train_max_errors"] and kind not in alerted
        standing = kind in ("run", "store") and kinds[kind] >= c["train_max_errors"] and kind not in alerted
        if tell or standing:
            alerted.append(kind)
        if standing:  # one alert for the lanes, not one a family: every family meets the same missing store
            said = self.store.get(HOUSE_ALERT_KEY)
            said = dict(said) if isinstance(said, Mapping) else {}
            standing = now - (_num(said.get(kind)) or float("-inf")) >= BACKOFF_MAX
            if standing:
                self.store.put(HOUSE_ALERT_KEY, {**said, kind: now})
        record = {"version": n, "count": count, "first_at": first, "next_at": now + delay, "kind": kind, "why": why[:240],
                  "streak": streak, "streak_at": since, "kinds": kinds, "alerted": alerted}
        _update(self.store, fid, lambda r: r.update(infra=record))
        if kind == "window":
            self.store.event("swarm.status", fid, {"action": "elane_train_window", "alert": True, "version": n,
                                                   "text": f"an equity Train result carried a day outside the "
                                                           f"{TRAIN_LABEL}: refused whole; E2 judges nothing on it "
                                                           "(check the runner)"})
        if standing:
            what = ("the swarm's decider child failed its Train runs" if kind == "run" else
                    "its Train runs could not start (the equity store under equity-daily is missing, unreadable or "
                    "being rewritten, or the child gave no result)")
            last = _num(self.store.get(TRAIN_OK_KEY))
            self.store.event("swarm.status", fid, {
                "action": "elane_train_house", "alert": True, "version": n, "kind": kind,
                "text": f"the equity lanes' Train is not running: {what} {kinds[kind]} times for this version with no "
                        f"judgment in between ({why[:160]}); no equity program is scored until it does, and the "
                        f"families born meanwhile wait (the last equity Train judgment: "
                        f"{'never' if last is None else time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(last))}). "
                        "Check the equity data job and the swarm's equity-decider.log"})
        if tell:
            which = "restart check (STATE)" if kind == "state" else "start check (START)"
            self.store.event("swarm.status", fid, {"action": f"elane_train_{kind}", "alert": True, "version": n,
                                                   "text": f"the equity Train bar's {which} could not "
                                                           f"finish {kinds[kind]} times since this version was last "
                                                           f"judged: {why[:160]}; the version is not scored and cannot "
                                                           "pass until it does (check the isolated runner's decider)"})
        return {"family": fid, "version": n, "house": kind, "why": why[:200], "retry_in": delay}

    def score(self, fam: Mapping[str, Any], version: Mapping[str, Any], *, rescore: bool = False) -> dict[str, Any]:
        """Run a version over the Train spans at 1.0x and 1.5x (E1's isolated runner, one run a span, summed) and judge it
        (the module docstring, WHAT A VERDICT IS); once Y1-R1 hold, THE RESTART CHECK on the 1.0x runs, and once that
        holds THE START CHECK (the 1.0x runs again from later starts). A bar pass goes to the equity review
        (`review_step`); `rescore` (a pass judged under another equity identity): passed again it stands, else the pass
        is withdrawn."""
        c = cfg(self.settings)
        fid, n = str(fam["id"]), int(version["n"])
        code, params = str(version.get("code") or ""), dict(version.get("params") or {})
        runs: dict[float, list[Any]] = {}
        verdict: dict[str, Any] | None = None
        try:
            for k in (eqconfig.K_BASE, eqconfig.K_STRESS):
                runs[float(k)] = [self.runner().train(code, params, name=fid, start=first, end=last, k=float(k))
                                  for first, last in TRAIN_SPANS]
        except Exception as exc:  # noqa: BLE001 - a refusal is the program's; a run failure is judged below
            verdict, out = self.fault(fam, n, exc)
            if out is not None:
                return out
        if verdict is None:
            parts = {k: [dict(getattr(run, "result", run) or {}) for run in rs] for k, rs in runs.items()}
            if any(outside_years(result, spans=[span]) for rs in parts.values() for result, span in zip(rs, TRAIN_SPANS)):
                return self.house_failure(fam, n, f"a Train result carried a day outside its span of the {TRAIN_LABEL}",
                                          kind="window") or {}
            statuses = {str(result.get("status")) for rs in parts.values() for result in rs}
            if "disqualified" in statuses:
                why = next((str(r["reason"]) for rs in parts.values() for r in rs if r.get("reason")),
                           "its own errors or timeouts")
                verdict = program_fault("DQ", why, said=dq_said(why))
            elif statuses != {"ok"}:
                return self.house_failure(fam, n, f"the Train runs ended {', '.join(sorted(statuses))}",
                                          kind="store") or {}
            else:
                verdict = train_score(combine(parts[float(eqconfig.K_BASE)]), combine(parts[float(eqconfig.K_STRESS)]))
                through = True
                if verdict["passed"]:
                    # THE RESTART CHECK: no pass without it. What stops it is the House's (nothing scored, no run
                    # stored) or, for a child that keeps failing it while other programs are judged, the program's.
                    try:
                        check = self.restart(fid, code, params, runs[float(eqconfig.K_BASE)])
                    except Exception as exc:  # noqa: BLE001 - judged as a run's failure is
                        verdict, out = self.fault(fam, n, exc, check=True)
                        if out is not None:
                            return out
                        through = False
                    else:
                        verdict = with_state(verdict, check)
                if through and verdict["passed"]:
                    # THE START CHECK, once the restart check holds: no pass without it either, and what stops it is
                    # judged as what stops the restart check is.
                    try:
                        check = self.start(fid, code, params, runs[float(eqconfig.K_BASE)])
                    except Exception as exc:  # noqa: BLE001 - judged as a run's failure is
                        verdict, out = self.fault(fam, n, exc, check="start")
                        if out is not None:
                            return out
                        through = False
                    else:
                        verdict = with_start(verdict, check)
                if through:
                    # The child judged a program through: what another program's RUN rule reads (never before the
                    # restart and start checks, or a version's own runs would prove the child sound against its own
                    # checks' failures; never for a check the child failed).
                    self.store.put(TRAIN_OK_KEY, self.clock())
                for k, rs in parts.items():
                    for result in rs:
                        try:
                            self.store.add_run(fid, n, result, window="train", stress=float(k), purpose="elane_train")
                        except Exception:  # noqa: BLE001 - the verdict stands without the stored run
                            pass
        at = self.store.now()
        ident = identity()
        if rescore:
            return self.rescored(fam, n, verdict, at=at, ident=ident)

        def put(r: dict[str, Any]) -> None:
            r.pop("infra", None)
            r["versions"] = {**(r.get("versions") or {}), str(n): compact(verdict, at=at, ident=ident)}
            if verdict["passed"] and r.get("passed_version") is None:
                r["review"] = {"version": n, "unclear": {}, "at": at}  # THE REVIEW, before the pass is the try
        rec = _update(self.store, fid, put)
        out: dict[str, Any] = {"family": fid, "version": n, "passed": bool(verdict["passed"]), "fails": verdict["fails"]}
        if verdict["passed"]:
            out["review"] = self.review_step(self.store.family(fid) or fam, n)
            return out
        if len(versions_of(rec)) >= c["train_budget"]:
            out["retired"] = self.finish(self.store.family(fid) or fam, "its Train budget is spent with no version passing")
        return out

    def rescored(self, fam: Mapping[str, Any], n: int, verdict: Mapping[str, Any], *, at: str,
                 ident: Mapping[str, Any] | None) -> dict[str, Any]:
        """THE IDENTITY (the module docstring): a stale pass judged again. Passed, its verdict is stamped with the identity
        in force (the review stands: the program is the same); failed, the pass is withdrawn (no `passed_version`, no
        `best_version`, no review record) and the family researches again with its budget."""
        fid = str(fam["id"])
        kept = bool(verdict.get("passed"))

        def put(r: dict[str, Any]) -> None:
            r.pop("infra", None)
            old = dict((r.get("versions") or {}).get(str(n)) or {})
            fresh = compact(verdict, at=at, ident=ident)
            if kept:
                fresh["passed"] = True
                fresh["rescored_from"] = old.get("identity")
            r["versions"] = {**(r.get("versions") or {}), str(n): fresh}
            if not kept:
                r["passed_version"], r["status"] = None, "researching"
                r["withdrawn"] = [*(r.get("withdrawn") or []), {"version": n, "at": at, "fails": list(verdict["fails"])}][-5:]
                r.pop("passed_review", None)
        _update(self.store, fid, put)
        if kept:
            self.store.note(fid, f"v{n} passed {OBJECTIVE} on Train again under the equity identity now in force.")
            return {"family": fid, "version": n, "rescored": "kept"}
        self.store.update_family(fid, best_version=None, best_train=None)
        self.store.set_state(fid, **{elane_review.STATE_REVIEW: None})
        self.store.note(fid, f"v{n} no longer passes {OBJECTIVE} on Train under the equity identity now in force: its pass is "
                             "withdrawn and its Train research goes on.")
        return {"family": fid, "version": n, "rescored": "withdrawn", "fails": list(verdict["fails"])}

    # ------------------------------------------------------------------ the review
    def review_step(self, fam: Mapping[str, Any], n: int) -> dict[str, Any]:
        """THE EQUITY REVIEW of a bar pass (league/swarm/elane_review.py): the level rule, then the review and the audit on
        two different models. Both pass: the version is the family's pass (its lineage's one Validation try). A failure
        (or `review_max_unclear` unclear reads of one stage) is a Train failure of the version ("REVIEW"). A question no
        route answered counts nothing and is asked again after a backoff (`unanswered`).

        THE AUDIT'S READER IS NEVER THE REVIEWER'S MODEL, wherever the router takes the call: a candidate whose window
        is flagged stalled is read as the model its fallback reaches (`reader_now`) and left out when that is the
        reviewer's, and an answer that came back from the reviewer's model all the same (the window stalled on this very
        call) is booked, discarded, and the next candidate is asked in the same step. EVERY QUESTION HAS ITS OWN KEY
        (`asked`, counted once its outcome is handled): the Provider answers a repeated key from its store, so a key
        asked again would be booked a second time for one call, and once the router's hourly compaction has blanked the
        stored answer the re-read is empty. An answer with no text at all counts as no answer (at most
        `review_max_unclear` times a stage; after that it is an unclear read).

        E2'S DOLLARS ARE READ BEFORE EVERY MODEL CALL (`elane_yield.hold`): before the review, and AGAIN before the audit
        when the review was asked in this same step, for the review's own call may have used up the hour's pace or the
        day's line. A held audit keeps the review's pass and is asked in a later step."""
        from .gate import run_sha

        fid = str(fam["id"])
        rec = record_of(fam)
        pending = dict(rec.get("review") or {}) if isinstance(rec.get("review"), Mapping) else {"version": n}
        version = self.store.version(fid, n)
        if version is None or not version.get("code"):
            return {"family": fid, "version": n, "error": "the version cannot be read"}
        code = str(version["code"])
        static = elane_review.memory_text(code) or elane_review.level_text(code)
        if static is not None:
            return self.review_failed(fam, n, "the level rule" if static.startswith("refused by the equity level") else
                                      "the memory rule", [static])
        held = elane_yield.hold(self.store, self.settings, self.clock())
        if held is not None:  # the day's line, or E2's own hourly pace: no model is asked
            return {"family": fid, "version": n, "skipped": held}
        rc = elane_review.cfg(self.settings)
        served = elane_yield.served([elane_yield.Route.of(k) for k in rc["review_routes"]], self.router)
        from . import cards, elane

        try:
            card = (cards.card_of(self.store, fid) or {}).get("card") or {}
        except Exception:  # noqa: BLE001
            card = {}
        facts = elane_seal.train_facts(fam, STATE_KEY)
        lane_label = elane.LABELS.get(facts["lane"], str(facts["lane"]).upper())
        train = version_text(n, versions_of(rec).get(str(n)) or {})
        unclear = dict(pending.get("unclear") or {})
        asked_now = False
        for stage in ("review", "audit"):
            done = pending.get(stage)
            if isinstance(done, Mapping) and done.get("verdict") == "pass":
                continue
            if asked_now:  # the review was asked in this step: its dollars count before the audit is
                held = elane_yield.hold(self.store, self.settings, self.clock())
                if held is not None:
                    return {"family": fid, "version": n, "skipped": held, "stage": stage}
            reader = (pending.get("review") or {}).get("route") if stage == "audit" else None
            taken = elane_review.model_of(str(reader or "")) if stage == "audit" else None
            if stage == "audit":
                candidates = [r for r in served if self.reader_now(r) != taken]
            else:
                candidates = list(served)
            if not candidates:
                return {"family": fid, "version": n, "error": f"no {stage} route on a second model (elane.e2.review_routes)"}
            tries = int(unclear.get(stage) or 0)
            asked = dict(pending.get("asked") or {})
            turn = int(asked.get(stage) or 0)
            answer, route, errors = elane_yield.ask(
                self.router, self.store, self.settings, first=None, role=elane_yield.ROLE,
                system=elane_review.REVIEW + contract_text(),
                user=elane_review.question(fam, version, card=card, train=train, lane_label=lane_label, stage=stage),
                key=f"swarm:elane:{stage}:{fid}:{n}:{turn}", max_output=rc["review_max_output_tokens"],
                effort=rc["review_effort"], purpose="review", now=self.clock(), family=fid, candidates=candidates,
                book_as=lambda r: f"review:{r.key}",
                accept=(lambda r, taken=taken: elane_review.model_of(r.key) != taken) if stage == "audit" else None)
            # This question's outcome is handled from here on: the next one of this stage has a key of its own.
            asked[stage] = turn + 1
            pending["asked"] = asked
            asked_now = True
            if answer is None or route is None:
                _update(self.store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
                return {"version": n, **self.unanswered(fid, stage, errors)}
            if not str(answer.get("text") or "").strip() and not answer.get("json"):
                blank = dict(pending.get("blank") or {})
                blank[stage] = int(blank.get(stage) or 0) + 1
                pending["blank"] = blank
                if blank[stage] <= rc["review_max_unclear"]:
                    # An answer with no text is no read (a key re-read after the router blanked its stored answer).
                    _update(self.store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
                    return {"family": fid, "version": n, "error": f"the {stage} answered nothing", "blank": blank[stage]}
            _update(self.store, fid, lambda r: r.pop("unanswered", None))
            read = {**elane_review.grounded(answer, code), "route": route.key}
            if read["verdict"] == "fail":
                return self.review_failed(fam, n, stage, read["reasons"] or [f"the {stage} failed it"], read=read)
            if read["verdict"] != "pass":
                unclear[stage] = tries + 1
                if unclear[stage] >= rc["review_max_unclear"]:
                    return self.review_failed(fam, n, stage, [f"the {stage} stayed unclear after {unclear[stage]} reads"]
                                              + read["reasons"][:2], read=read)
                _update(self.store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
                return {"family": fid, "version": n, stage: "unclear", "reads": unclear[stage]}
            if stage == "audit" and elane_review.model_of(route.key) == taken:
                # Never reached (`accept` refuses such an answer): the two-reader rule is held here too.
                _update(self.store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
                return {"family": fid, "version": n, "error": "the audit was answered by the reviewer's model"}
            pending[stage] = {k: read.get(k) for k in ("verdict", "route", "model", "reasons")}
            _update(self.store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
        sha = run_sha(version)
        at = self.store.now()
        held = elane_review.record(sha, pending["review"], pending["audit"], at=at, version=n)
        score = (versions_of(rec).get(str(n)) or {}).get("score")

        def put(r: dict[str, Any]) -> None:
            r.pop("review", None)
            if r.get("passed_version") is None:
                r["passed_version"], r["status"] = n, "passed"
                r["passed_review"] = held
        rec = _update(self.store, fid, put)
        if rec.get("passed_version") == n:
            self.store.set_state(fid, **{elane_review.STATE_REVIEW: held})
            self.store.update_family(fid, best_version=n, best_train=score)
            self.store.note(fid, f"v{n} passed {OBJECTIVE} on Train and the equity review: it is the lineage's one "
                                 "Validation try.")
        return {"family": fid, "version": n, "passed": True, "review": "pass"}

    def review_failed(self, fam: Mapping[str, Any], n: int, stage: str, reasons: Sequence[str], *,
                      read: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """The review refused version `n`: a Train failure of it ("REVIEW", its reasons in the next brief); the family's
        research goes on with its budget, or ends (`finish`) once the budget is spent. No Validation try is spent."""
        c = cfg(self.settings)
        fid = str(fam["id"])
        said = [" ".join(str(x).split())[:400] for x in reasons][:4]

        def put(r: dict[str, Any]) -> None:
            r.pop("review", None)
            v = dict((r.get("versions") or {}).get(str(n)) or {})
            v.update(passed=False, bar_passed=True, fails=["REVIEW"],
                     review={"stage": stage, "reasons": said, "route": (read or {}).get("route"),
                             "model": (read or {}).get("model")})
            r["versions"] = {**(r.get("versions") or {}), str(n): v}
        rec = _update(self.store, fid, put)
        self.store.note(fid, f"v{n} passed the Train bar but the equity {stage} refused it: {'; '.join(said)[:600]}")
        out: dict[str, Any] = {"family": fid, "version": n, "passed": False, "fails": ["REVIEW"], "stage": stage}
        if len(versions_of(rec)) >= c["train_budget"]:
            out["retired"] = self.finish(self.store.family(fid) or fam, "its Train budget is spent with no version passing")
        return out

    # ------------------------------------------------------------------ the end of the research
    def finish(self, fam: Mapping[str, Any], why: str) -> dict[str, Any]:
        """The research ends with no pass: REFUTED on Train when the bar judged a version, else STALLED."""
        return self.refute(fam, why) if judged(record_of(fam)) else self.stall(fam, why)

    def refute(self, fam: Mapping[str, Any], why: str) -> dict[str, Any]:
        """Retire a family REFUTED on Train: its record, a graveyard row in E2's own words (Train facts), the store's
        retirement."""
        fid = str(fam["id"])
        rec = record_of(fam)
        versions = versions_of(rec)
        codes = sorted({f for v in versions.values() for f in (v.get("fails") or [])})
        at = self.store.now()

        def put(r: dict[str, Any]) -> None:
            r["status"] = "refuted"
            r.pop("review", None)
            r["refuted"] = {"at": at, "codes": codes, "versions": len(versions), "why": why[:300]}
        _update(self.store, fid, put)
        facts = elane_seal.train_facts(self.store.family(fid) or fam, STATE_KEY)
        words = "; ".join(f"({c}) {FAILS[c]}" for c in codes if c in FAILS) or "no version was scored"
        title = AGENDA.get(facts["agenda"], AGENDA["other"])["title"]
        lesson = (f"{REFUTED_TAG} on Train ({OBJECTIVE}, {facts['lane']} lane, {title} on {', '.join(facts['symbols'])}): "
                  f"{why}. {len(versions)} versions scored; their fails: {words}.")
        self.store.bury(fid, lesson, {"objective": OBJECTIVE, "codes": codes, "versions": len(versions)})
        self.store.retire(fid, f"{REFUTED_TAG} on Train ({OBJECTIVE}): {why}"[:2000],
                          public_reason="refuted on Train by the equity lane's bar")
        self.store.event("swarm.elane", fid, {"pass": "refuted", "codes": codes, "versions": len(versions)})
        return {"family": fid, "refuted": codes}

    def stall(self, fam: Mapping[str, Any], why: str) -> dict[str, Any]:
        """Retire a family STALLED on Train: no version of it was judged by the bar (its programs failed to run, to load,
        or the review), so nothing is said of its mechanism: no graveyard row, no cell count, its record's `stalled`."""
        fid = str(fam["id"])
        rec = record_of(fam)
        versions = versions_of(rec)
        codes = sorted({f for v in versions.values() for f in (v.get("fails") or [])})
        at = self.store.now()

        def put(r: dict[str, Any]) -> None:
            r["status"] = "stalled"
            r.pop("review", None)
            r["stalled"] = {"at": at, "codes": codes, "versions": len(versions), "why": why[:300]}
        _update(self.store, fid, put)
        self.store.retire(fid, f"{STALLED_TAG} on Train ({OBJECTIVE}): no version could be judged by the bar; {why}"[:2000],
                          public_reason="stalled on Train: no version of its program could be judged by the equity bar")
        self.store.event("swarm.elane", fid, {"pass": "stalled", "codes": codes, "versions": len(versions)})
        return {"family": fid, "stalled": codes}


def versions_of(rec: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    versions = rec.get("versions") if isinstance(rec.get("versions"), Mapping) else {}
    return {str(k): dict(v) for k, v in versions.items() if isinstance(v, Mapping) and str(k).isdigit()}


__all__ = ["OBJECTIVE", "STATE_KEY", "TRAIN_AT_KEY", "TRAIN_OK_KEY", "HOUSE_ALERT_KEY", "TRAIN_FIRST", "TRAIN_LAST", "TRAIN_SPANS",
           "RESERVE_YEARS", "TRAIN_YEARS", "TRAIN_LABEL", "BAR", "FAILS", "JUDGED", "DEFAULTS", "AGENDA", "GROUPS",
           "MAP_LABEL", "cfg", "lane_on", "symbols_group", "cell_of", "cell_text", "outside_years", "combine", "year_rows",
           "train_score", "bar_text", "record_of", "e2_family", "passed_version", "identity", "judged", "tried",
           "pass_current", "may_validate", "compact", "dq_said", "program_fault", "KIND", "StateCheckInterrupted", "state_inputs",
           "SIZE_TOL", "same_intents", "restart_check", "with_state", "restart_text", "train_map",
           "closed_cells", "train_map_text", "refuted_rows", "needs_literal", "check_code", "program_of", "contract_text",
           "RESEARCHER_SYSTEM", "version_text", "EquityResearcher", "versions_of", "BETA", "EQUITY", "LANES"]
