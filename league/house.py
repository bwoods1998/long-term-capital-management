"""The House: the one trusted process. It keeps the ledger, wakes the agents, nets and sends their
orders, scores them, pays them, buries them, and publishes all of it.

One `tick()` is the whole loop:

1. settle and poll every book (resting fills, Kalshi settlements);
2. wake each agent that is due: build its market snapshot, run its `decide` in its own sealed box,
   charge it the box seconds, turn what it returned into intents, and submit them as one batch
   per book so opposite orders net;
3. mark every account, reconcile every book to its venue, close finished blocks of log growth and
   judge each agent by the constitution: promote (through the audit, for real money), demote on
   drift, or kill;
4. run due research passes and act on what they produce (adopt on rung 0, fork above it);
5. pay the epoch's credits, kill anything at zero, keep the population above its floor;
6. publish.

Nothing here decides a trade, and nothing here can be changed by an agent: agents' code runs in
other boxes and returns plain data.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Callable, Collection, Iterator, Mapping, Sequence

from ltcm.broker import Instrument, money

from . import seeds as seeds_module
from .agents import Agent, Registry, code_sha, niche_of
from .admissions import Admissions
from . import allocator as allocator_module, capital, feeds as feeds_module, niches as niches_module, shards as shards_module
from . import parameters
from .parameters import mutate  # retained as a public import for callers of league.house.mutate
from .book import Book, BookError, Intent, Limits, step_of
from .commons import Commons
from .constitution import CONSTITUTION, digest as constitution_digest
from .economy import Economy, Standing, load_game
from .evaluator import Evaluator, Verdict
from .fees import Fees
from .frontier import TIER_ROLES
from .ledger import HOUSE, Ledger, LedgerConflict, now_iso
from .researcher import Researcher, pass_state, restore_pass
from .research_jobs import ResearchJobs, ResearchPending
from .pacer import Pacer
from .rules import rules_text
from .sandbox import SandboxBusy, SandboxError
from .venues import family_of, instrument_for, market_hours, min_order_usd, price_increment, snap_limit
from .watchdog import environment  # H2: an alert about a service's own failure is marked, never a rollback

#: How many bars of a watched underlier a replay tape carries per symbol, and the sizes it may
#: choose between. A three-week window of one-minute bars is millions of rows and a box killed for
#: memory (Sept 19, 2026); four thousand of them is about two megabytes for six symbols.
MAX_OBSERVED_BARS = 4000
OBSERVED_BAR_SIZES = (("5Min", 300), ("15Min", 900), ("1Hour", 3600), ("1Day", 86400))
from ltcm.data import market_open_at, next_session, to_datetime, us_equity_session

ZERO = Decimal(0)
CENT = Decimal("0.01")
#: A desk that keeps an exchange's session is woken this many seconds after the regular open when
#: its next wake would otherwise land later (`House._next_wake`). Measured Sept 23, 2026: the options
#: desk woke at 13:29:55Z on a clock 4.3-4.6 s slow, saw a shut market, and 5 of its 8 agents did
#: not wake again until 14:01Z or later.
OPEN_WAKE_SECONDS = 5.0
#: The floor's cheap invariants (`_floor_invariants`, Sept 23, 2026): how often the ledger's new rows
#: are read, how many rows the first pass reads back (never the whole ledger), and what makes a
#: desk quiet: offered markets on this many wakes inside the trailing hour and no intent from any
#: of its agents.
INVARIANTS_EVERY_SECONDS = 300.0
INVARIANTS_FIRST_ROWS = 5000
QUIET_DESK_SECONDS = 3600.0
QUIET_DESK_WAKES = 3
#: A desk whose agents offered markets are all day-horizon is quiet only after a day with no intent: a
#: day program acts around its events, not every hour. Sept 24, 2026: kalshi-sports (16 members, all
#: "day") wrote 2-7 intents an hour from 00Z to 07Z and none from 11Z to 14Z -- its favourites programs
#: wait for game time -- while two of its agents made the floor's profit; the hourly rule called it
#: quiet six times that day ("offered markets on 32 wakes in the last hour and no agent of the desk
#: wrote an intent").
QUIET_DESK_DAY_SECONDS = 24 * 3600.0
#: The books that hold real money, by name (`Book.real_money`), for a refusal on a book that is not mounted.
REAL_BOOKS = ("kalshi", "alpaca")
#: Beside the House's state: when each deadline-type Kalshi series' markets paid after their close
#: (`resolution.SettleLags`, which reads it as untrusted data), which the horizon rule judges such a market by.
SETTLE_LAGS_FILE = "settle_lags.json"
#: X1 (Sept 24, 2026): an in-place parameter edit is replayed first on a book this share of the
#: practice book's stake and caps ("at half notional"), and an agent gets one such replay a day,
#: passed or not, so it cannot search its parameters in place for a lucky look that is no trial.
EDIT_REPLAY_NOTIONAL = 0.5
EDIT_REPLAY_EVERY_SECONDS = 24 * 3600.0
#: A reconcile that fails is read once more after this many seconds and a fresh poll, before it is
#: called a mismatch (`reconcile_with_second_look`).
SECOND_LOOK_SECONDS = 3.0


def reconcile_with_second_look(book: Any) -> Any:
    """`book.reconcile()`, and when it fails, one more look after a short wait and a fresh poll.

    A fill in flight is not a mismatch. Measured Sept 23, 2026 at 21:48:57Z: haghani-37's marketable
    LINK/USD limit sell on the practice account filled seconds after the mark pass's poll, the venue's
    positions and cash already showed it while its orders endpoint did not, and the reconcile read
    "cash differs by 40.0116; positions differ: LINK -3.262934654". The fill was booked one poll
    later, but the error alert inside the deploy's watch rolled Deploy B back. A mismatch that is
    still there on the second look is real and stands (the book stays frozen, the alert is raised).
    """
    result = book.reconcile()
    if result.ok or not book.open_orders():
        return result  # with no order working, nothing can be in flight: the mismatch stands as read
    # The second look re-reads the same pass: it must not count twice toward a practice book's
    # adoption of the venue (`Book.reconcile`, ADOPT_AFTER consecutive failed readings).
    counted = getattr(book, "_unreconciled", None)
    if isinstance(counted, int) and counted > 0:
        book._unreconciled = counted - 1
    book.sleep(SECOND_LOOK_SECONDS)
    book.poll()
    return book.reconcile()
CONTRACT_PATH = Path(__file__).resolve().parent / "CONTRACT.md"
#: An agent's resting entries are cancelled once none of its wakes has completed on their book for
#: this many of its own wake intervals, and never sooner than `STALE_FLOOR_SECONDS` (see
#: `House._cancel_stale_resting`).
STALE_WAKES = 3
STALE_FLOOR_SECONDS = 1800
#: How long a Kalshi market's price grid is trusted before it is read again (as the adapter's).
PRICE_GRID_TTL_SECONDS = 600.0

#: Which book an agent trades on, by venue family and rung.
PRACTICE_BOOK = {"alpaca": "alpaca-paper", "kalshi": "kalshi-shadow"}
REAL_BOOK = {"alpaca": "alpaca", "kalshi": "kalshi"}
PROBE_BOX = "house-probe"
#: The order path's own invariants (`House._order_path_invariants`, workstream B, Sept 23, 2026):
#: how often they run, how many ledger rows the first pass reads back (never the whole ledger),
#: and how long a round-the-clock desk may go without one wake, while the House is not paused,
#: before the operator is told. Measured Sept 22, 2026: 8.4 hours without a wake on any desk
#: (07:05-15:28Z) while the 15-minute crypto series settled 96 times a coin, and nothing said so.
ORDER_INVARIANTS_EVERY_SECONDS = 60.0
ORDER_INVARIANTS_FIRST_ROWS = 2000
QUIET_ROUND_THE_CLOCK_SECONDS = 1800.0
#: Warnings that repeat are defects (L3, Sept 24, 2026): the same warning text (`alert_key`) this many
#: times inside the window is ONE error alert, and it is listed in health.json `repeating_warnings`
#: until it has been quiet for the window. "the lab's step failed (IndexError: list index out of
#: range)" was a warning 115 times in 2 h 18 min on Sept 23-24, 43 of them in two hours, and nothing
#: escalated; at this rule it would have been an error, with its traceback, at 23:44:48Z.
REPEAT_WARNINGS = 10
REPEAT_WINDOW_SECONDS = 1800.0
#: A session the provider broke gives the agent its turn back this soon (`House.research`).
PROVIDER_RETRY_SECONDS = 900.0
#: A stop of the floor's paid work is told once it has lasted this long (`House._note_stopped`): the three
#: sixty-second ticks it waited for until H5 (Sept 25, 2026) halved the tick.
STOPPED_TELL_SECONDS = 120.0
#: H6 (Sept 25, 2026): how a research session in flight at a restart ends when it cannot be resumed safely
#: (`House._session_lost`). `provider: campaign_post_unconfirmed`: the restart killed the model call's POST
#: after its campaign hold was written and before Sail's answer was linked, and a second POST could be a
#: second bill (`funded.FundedTransport`); `tool outcome unconfirmed`: it killed a tool between its intent
#: and its receipt, and no side effect is repeated (`Researcher.research`). Read from research.sqlite on
#: the box for the day to 04:39Z Sept 25 (26 restarts): 110 sessions began before a restart and ended
#: after it; 84 resumed and ended as usual, 23 ended campaign_post_unconfirmed and 2 tool outcome
#: unconfirmed (every such ending that day spanned a restart), 1 ended in a provider 502 -- and nothing
#: said so: each was closed as a finished pass, which restarts the agent's research clock.
SESSION_LOSSES = ("provider: campaign_post_unconfirmed", "tool outcome unconfirmed")
#: The sessions lost to restarts that health.json names (`restart_research.lost`), newest last.
SESSION_LOSSES_SHOWN = 20
#: The lab evaluated nothing for this long while its queue was not empty: a health failure (L3).
LAB_IDLE_SECONDS = 3600.0
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_NUMBERED = re.compile(r"[\w.:/@+\-]*\d[\w.:/@+\-]*")


def alert_key(text: Any) -> str:
    """What makes two warnings the same text: ids and numbers folded, so "failed 3 times" and "failed
    4 times" are one, and two agents' identical failures with two order ids are one. A UUID becomes
    `<id>` and every token that carries a digit (a count, an amount, a time, an agent or order id, a
    URL with a version in it) becomes `#`; words stay, so two books or two desks stay apart."""
    folded = _NUMBERED.sub("#", _UUID.sub("<id>", str(text or "")))
    return re.sub(r"\s+", " ", folded).strip()[:300]


def _count_repeat(runs: dict[str, Any], text: str, now: float, stamp: str, service: Any = None) -> dict[str, Any]:
    """Count one warning of `text`, written at `now` (`stamp` in ISO), into its run of repeats: runs
    quiet for the window are dropped first, and a run keeps the times inside the window. A run keeps
    the `environment` marker (H2, Sept 25, 2026) only while every warning of it carried the same one:
    "sailbox api 503" and "sailbox api 400" fold to one text, and a run that mixes a service's failure
    with the House's own escalates unmarked."""
    for quiet in [k for k, run in runs.items() if now - float(run.get("last_epoch") or 0) >= REPEAT_WINDOW_SECONDS]:
        runs.pop(quiet)
    marker = service if isinstance(service, str) and service else None  # the warning's `environment`, if any
    run = runs.setdefault(alert_key(text), {"first_seen": stamp, "count": 0, "times": [], "escalated": None, "environment": marker})
    if "environment" not in run or run["environment"] != marker:
        run["environment"] = None  # a run of mixed kinds, or one counted before the marker existed
    run["count"] = int(run.get("count") or 0) + 1
    run["times"] = [t for t in run.get("times") or [] if now - float(t) < REPEAT_WINDOW_SECONDS][-4 * REPEAT_WARNINGS:] + [now]
    run.update(text=text[:300], last_seen=stamp, last_epoch=now)
    return run


#: The evidence clock (S1, the close-the-gaps run, Sept 24, 2026): per desk, the Kaplan-Meier median hours
#: from a member's first own fill to its third independent settlement (distinct events on the event
#: books, closed trades on Alpaca, any book), over the members whose first fill is in the last
#: `EVIDENCE_CLOCK_DAYS`, measured again once a day. The scoreboard (`scripts/gap_scoreboard.py`
#: `evidence_clocks`) measured it at T0: kalshi-crypto-15m 1.9 h, alpaca-crypto-alts 3.8, kalshi-crypto-
#: strikes 4.4, alpaca-megacaps 4.4, alpaca-index-etfs 18.1, kalshi-sports 20.5, alpaca-options 23.9,
#: kalshi-weather 31.8, kalshi-prices 36.5, while the seat clock was twelve hours for every desk.
EVIDENCE_CLOCK_DAYS = 7.0
EVIDENCE_CLOCK_REFRESH_SECONDS = 86400.0
EVIDENCE_CLOCK_SETTLEMENTS = 3
#: A resident with this many fills of its own since its program's opportunity is displaced only by a
#: newcomer whose forward score beats its own forward record (S1).
FORWARD_RULE_FILLS = 3
#: A never-traded paper seat's fair chance against an evidenced newcomer is at least this long (the fix of Sept 24, 2026,
#: `House._fair_chance`): after Deploy B six newborns were displaced 33 s to 14 min after birth by the next waiter.
FAIR_CHANCE_FLOOR_SECONDS = 3600.0
#: The seat market's capacity (R2, the close-the-gaps run, Sept 24, 2026). Measured on the 15:06Z snapshot: 82 newcomers
#: waited for a seat (41 lab graduates, the longest 24.5 h since passing; 15 cards, 47.3 h; 11 retained candidates; 15
#: merged strategies) in a league of 112 of 112 whose every desk they waited for was full; 20 of them waited for
#: kalshi-crypto-15m, a desk the search had closed (every one of its 8 families with three active blocks there negative),
#: and a graduate with a losing forward window (-0.000142 a block over 4 active blocks) still counted. So a waiter the
#: search has closed leaves the queue (`_expire_waiters`), a forward-scored waiter takes a stale seat (S3,
#: `_stale_seat`), desk caps and the population follow the waiters (`_follow_the_search`, `_population_rule`), and a
#: newcomer that waits longer than this is named once an hour a desk with the rule that holds it (`_seat_market_watch`).
SEAT_WAIT_WARN_SECONDS = 2 * 3600.0
#: The search's closed desks are read at most this often: the foundry's rule reads the `eval.block` rows of every agent
#: that ever lived on them (`Foundry._closed_desk_forward`), the lab's idle rule a few rows a member (`Lab._idle_desk`).
SEARCH_CLOSED_TTL_SECONDS = 600.0
#: An expired waiter is remembered this long (house.json `seat_expired`): it does not wait again in that time.
SEAT_EXPIRED_KEEP_SECONDS = 7 * 86400.0
#: Sail's burn is the falls of its balance over this trailing window (league/budget.py `Budget.check`: an `ops.budget`
#: "sail" row every fifteen minutes with the balance read from Sail and the fall since the reading before), scaled to a
#: day; readings spanning less than the minimum measure nothing. At 15:06Z: $34.44 of falls in 23.7 hours of readings,
#: $34.88 a day (the owner's $100 top-up is a rise, never a fall), against a $162.30 balance: 4.5 days over the $5 reserve.
SAIL_BURN_WINDOW_SECONDS = 86400.0
SAIL_BURN_MIN_SPAN_SECONDS = 6 * 3600.0
#: A proven family's program that has no distinct valid PARAMS mutation left (`_mutated_params`: no declared or standard
#: knob, the anchor's PARAMS outside its own rules, or 64 proposals that all repeat a living twin) is held this long
#: before it is asked again (`_proven_births`, the review of #276, Sept 24, 2026): while held nothing is owed and its desk
#: is not kept from other families' newcomers. Before, it stayed owed for good -- its desk gave every other family's
#: newcomer no seat -- and the pass asked for the desk's weakest resident and a mutation on every tick. An hour, because
#: what reopens a mutation (a living twin's death, a new anchor) happens on the scale of the newcomer cadence, not ticks.
PROVEN_UNBRED_RETRY_SECONDS = 3600.0
#: Once the population rule holds the league (`_population_rule`), it grows again only when Sail's runway is over the
#: floor (`economy.population_runway_days`) by this band (the review of #276, Sept 24, 2026). Measured on the 15:06Z
#: snapshot's 492 Sail meter readings: the runway moves a median 0.6% a reading, 2.6% at the 90th percentile and 7.9% at
#: the 99th, and it rose with no top-up in 243 of 491 readings, so a runway near 1.5 days crossed it back and forth. Each
#: crossing was an alert, and each ten-minute window over the floor seated newcomers the next never removed: the league
#: crept to its ceiling on a runway at the floor. A quarter day is 17% of the 1.5-day floor, over twice the 99th
#: percentile's move, and six hours of the measured burn (about $8.70 at $34.88 a day); a top-up clears it at once.
POPULATION_RUNWAY_BAND_DAYS = 0.25
#: How the House's own closing sales read on a fill: the House's, never the agent's evidence.
HOUSE_CLOSING = "the House is closing"
#: Why a held probe's resting buy is cancelled (`House._cancel_paused_entries` under the R5 drain hold): the House's hold,
#: which ends with the drain, not the agent's own pause, which ends when it resumes.
DRAIN_HOLD_WHY = ("the House holds this probe's entries while it goes back to practice: its family's pooled forward record "
                  "is losing (allocator.family_probe), so it only exits until it is flat")
#: The same refusal of a House-sent order (a wind-down) this many times in a row stops its retries
#: (Sept 24, 2026: 107 identical refusals of a 0.000000001 LINK/USD sale in 12 hours).
WIND_DOWN_REFUSALS = 3
#: ...and it is tried again this long after the last refusal (the review of #245, Sept 24, 2026): a refusal that is
#: transient but identical three times in a row (an outage, a rate limit, a halt) must not strand a holding for good.
WIND_DOWN_RETRY_SECONDS = 86400.0

#: L1 (Sept 24, 2026): the words with which a research child's own account of its program names its
#: parent's ENTRY mechanism as the defect -- the liquidity it takes, the fee that costs, the side it
#: buys -- and the fix. Read together with the parent's own entry fills (`House._entry_fills`), never alone:
#: mullins-14's birth reason says "post-only" about a maker parent's code and names no defect of it.
_DEFECT_WORDS = re.compile(r"\b(defects?|fix(?:es|ed)?|wrong|replac(?:e|es|ed|ing)|switch(?:es|ed)?|instead of|loses|losing|bleeds?)\b", re.I)
_TAKER_WORDS = re.compile(r"\b(takers?|marketable|cross(?:es|ing)? the (?:touch|spread)|at the ask|lift(?:s|ing)? the (?:ask|offer)|market orders?)\b", re.I)
_MAKER_WORDS = re.compile(r"\b(makers?|post[- ]only|resting (?:bids?|orders?|limits?)|rest(?:s|ing)? (?:a |its )?(?:bids?|limits?)|join(?:s|ing)? the bid)\b", re.I)
_FEE_WORDS = re.compile(r"\bfees?\b", re.I)
#: A claim that the side is wrong, never a description of what is bought: "the opposite side of the favourite" names
#: no defect (the review of #245, Sept 24, 2026: with it, any child that bought NO retired a parent that entered at all).
_SIDE_WORDS = re.compile(r"\bwrong side\b|\bside (?:is|was) wrong\b|\bflip(?:s|ped|ping)? (?:the |its )?side\b", re.I)


def entry_defect(text: str) -> str | None:
    """Which part of an entry mechanism a research child's account of its program names as the defect:
    "liquidity" (a taker entry, fixed by resting maker orders), "fee" (the fee a taker entry pays, fixed
    the same way), "side" (the side it buys), or None when it names none of them as a defect.

    Every kind needs a defect claimed in so many words (the review of #245, Sept 24, 2026). An account that
    speaks of makers and takers is about liquidity whatever else it says, so the parent's taker entries and
    the child's post-only program are checked (`House._corrected_entry`): meriwether-44's birth reason calls
    its parent's TAKER "the wrong side" of a maker edge, and as a "side" defect it retired a MAKER parent."""
    text = str(text or "")
    if not _DEFECT_WORDS.search(text):
        return None
    maker, taker = _MAKER_WORDS.search(text), _TAKER_WORDS.search(text)
    if maker and taker:
        return "liquidity"
    if maker and _FEE_WORDS.search(text):
        return "fee"
    if not (maker or taker) and _SIDE_WORDS.search(text):
        return "side"
    return None


def posts_maker_entries(code: str) -> bool:
    """Whether a strategy file rests its entries post-only: some intent literal in it is a buy with
    `post_only` True (a dict literal or `dict(...)` call, read with `ast`, never run). A maker fix of a taker
    entry is a program that does this; a child that moves to market orders "for a guaranteed taker fill"
    (meriwether's rewrite of Sept 21, 2026) names makers and takers too, and fixes nothing of the kind.
    Measured on the T0 snapshot (Sept 24, 2026): all 145 of 503 programs that set `post_only` True do it on
    a buy literal; meriwether-h2d625d's KXMLBTOTAL file does not, nor its child's first (moneyline) file."""
    import ast

    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            pairs = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
            pairs = {k.arg: k.value for k in node.keywords if k.arg}
        else:
            continue
        side, post = pairs.get("side"), pairs.get("post_only")
        if isinstance(side, ast.Constant) and side.value == "buy" and isinstance(post, ast.Constant) and post.value is True:
            return True
    return False


@dataclass(frozen=True)
class Newcomer:
    """Who asks for a seat (S1, the close-the-gaps run, Sept 24, 2026): its family and venue, whose pooled
    record the allocator keeps (`Allocator.family`: proven or not), and its forward score (`Lab.forward_score`,
    None without one). A caller that does not know yet which newcomer it seats -- the House's own mutation
    refill, the foundry's card pass -- passes none: an unproven newcomer with no forward score."""

    family: str | None = None
    venue: str | None = None
    forward: float | None = None
    what: str = ""


def kaplan_meier_median(times: Sequence[tuple[float, bool]]) -> float | None:
    """The median of (time, reached) with the unreached censored at their time (as the scoreboard's
    `kaplan_meier_median`); None when the survival curve never falls to one half."""
    rows = sorted(times)
    at_risk, survival = len(rows), 1.0
    i = 0
    while i < len(rows):
        t = rows[i][0]
        events = censored = 0
        while i < len(rows) and rows[i][0] == t:
            events += 1 if rows[i][1] else 0
            censored += 0 if rows[i][1] else 1
            i += 1
        if events:
            survival *= 1.0 - events / at_risk
            if survival <= 0.5:
                return t
        at_risk -= events + censored
    return None


def measure_evidence_clocks(ledger: Any, agents: Sequence[Any], now: float, *, days: float = EVIDENCE_CLOCK_DAYS,
                            settlements: int = EVIDENCE_CLOCK_SETTLEMENTS) -> dict[str, dict[str, Any]]:
    """Per desk: the hours from a member's first own fill to its `settlements`-th independent settlement,
    for the members whose first own fill is in the last `days` -- the scoreboard's definition, read from the
    House's own ledger (Sept 24, 2026). An own fill is a venue or cross fill, never the House's closing sale;
    a settlement is a `book.settle` or a sale that left the position flat, on any book, counted once per
    EVENT on the event books (`evaluator.event_key`, the allocator's count) and once per trade on Alpaca,
    after each book's evidence cutoff -- never the House's closing sale either: a forced exit at a death
    says nothing of how long the desk's markets take (the review of #245). A settlement after a death is
    the market's own verdict and counts. A member that has not reached it is censored at its death or now.

    Each desk: `members`, `reached`, `hours` (the Kaplan-Meier median, None when it is not reached: most
    members never traded enough to measure how long the desk's markets take, which says nothing of the
    markets' clock, so the plain grace stands there), `median_reached_hours` and `longest_waiting_hours`."""
    from .evaluator import EVENT_BOOKS, event_key

    start = now - days * 86400.0
    rows = list(ledger.iter(kinds=("book.fill", "book.settle", "book.fill_correction", "book.baseline")))
    cutoffs: dict[tuple[str, str], int] = {}
    for entry in rows:
        p = entry.payload
        if entry.kind == "book.fill_correction":
            key = (entry.agent, str(p.get("book")))
            cutoffs[key] = max(cutoffs.get(key, 0), entry.seq)
        elif entry.kind == "book.baseline":
            for repair in p.get("repairs") or []:
                if isinstance(repair, Mapping):
                    key = (str(repair.get("agent")), str(p.get("book")))
                    cutoffs[key] = max(cutoffs.get(key, 0), entry.seq)
    first: dict[str, float] = {}
    closes: dict[str, list[tuple[float, str]]] = {}
    for entry in rows:
        if entry.kind not in ("book.fill", "book.settle") or entry.agent == HOUSE:
            continue
        p = entry.payload
        book = str(p.get("book"))
        if entry.seq <= cutoffs.get((entry.agent, book), 0):
            continue
        at = _epoch(entry.at)
        if entry.kind == "book.fill" and p.get("source") in ("venue", "cross") \
                and not str(p.get("reason") or "").startswith(HOUSE_CLOSING):
            first.setdefault(entry.agent, at)
        closing = str(p.get("reason") or "").startswith(HOUSE_CLOSING)  # the House's sale at a death, never the member's
        if entry.kind == "book.settle" or (p.get("realized") is not None and p.get("source") != "dust" and p.get("flat", True)
                                           and not closing):
            key = (event_key(p.get("instrument")) if book in EVENT_BOOKS else None) or f"#{entry.seq}"
            closes.setdefault(entry.agent, []).append((at, key))
    desks: dict[str, list[tuple[float, bool]]] = {}
    for agent in agents:
        began = first.get(agent.id)
        if began is None or began < start or not agent.specialty:
            continue
        seen: set[str] = set()
        third = None
        for at, key in closes.get(agent.id, ()):
            if at < began:
                continue
            seen.add(key)
            if len(seen) >= settlements:
                third = at
                break
        if third is not None:
            desks.setdefault(agent.specialty, []).append(((third - began) / 3600.0, True))
        else:
            ended = _epoch(agent.died_at) if not agent.alive and agent.died_at else now
            desks.setdefault(agent.specialty, []).append((max(0.0, ended - began) / 3600.0, False))
    out: dict[str, dict[str, Any]] = {}
    for desk, times in sorted(desks.items()):
        reached = sorted(t for t, ok in times if ok)
        waiting = [t for t, ok in times if not ok]
        median = kaplan_meier_median(times)
        middle = (reached[(len(reached) - 1) // 2] + reached[len(reached) // 2]) / 2 if reached else None
        out[desk] = {"members": len(times), "reached": len(reached),
                     "hours": None if median is None else round(median, 1),
                     "median_reached_hours": None if middle is None else round(middle, 1),
                     "longest_waiting_hours": round(max(waiting), 1) if waiting else None}
    return out


@dataclass
class Settings:
    """The House's own dials (not the game's, not the constitution's)."""

    # The run loop's tick (league/config.json `tick_seconds`): 30 since H5 (Sept 25, 2026), for the wakes, which
    # saw the tick lines 60-68 s apart at p50 while it was 60; the steps beside them keep their own cadences below.
    tick_seconds: int = 30
    mark_every_seconds: int = 300
    real_money: bool = False  # the owner's switch: False keeps every agent on practice books
    replay_days: int = 21
    replay_timeout: int = 600
    research: bool = True
    max_wakes_per_tick: int = 16
    cold_wakes_per_tick: int = 5  # in a House's first five minutes (see `due`)
    enroll_per_tick: int = 3  # architect strategies born per tick (see `enroll`)
    # A merged strategy takes a seat even when the league is full (the weakest eligible resident, or
    # an agent still running the code a repair corrects, gives it up), and agents running code a
    # BORN repair corrects are retired. Off: merged strategies wait for an empty seat, as before.
    enroll_displaces: bool = True
    # No new research from the moment a release is staged. It wants to be a little longer than a
    # research pass (one to three minutes, measured) so the ones in flight finish before the
    # restart, and a good deal SHORTER than a deploy: at fifteen minutes against a half-hourly
    # deploy, a floor that is improving itself quickly would have spent half its life waiting.
    deploy_grace_seconds: int = 420
    wake_workers: int = 6
    slow_workers: int = 3  # replays at once, beside the tick and never inside it
    research_workers: int = 5  # research passes at once: each is minutes of WAITING on Sail's flex window, not work
    ops_workers: int = 3  # the backup, the survey, the updater and Merton: never queued behind a replay
    kalshi_replay_days: int = 7
    kalshi_replay_markets: int = 2000
    kalshi_day_step_seconds: int = 1800  # a daily strategy is not judged on five-minute moves
    kalshi_day_markets: int = 500
    specialists: bool = True  # every new agent must sit in a specialty of league/niches.json
    # The Alpha Lab's box key, when `league/config.json` `lab` names a box (`service.lab_box_key`):
    # with `game.json` `lab.enabled` too, the lab runs (league/lab.py).
    lab_box: str = ""
    niche_survey_hours: float = 24.0  # how often the venue is surveyed so the universes follow the season (0: never)
    # Historical options replay and options-derived features (`league/options_history.py`). ON:
    # with no ingested history nothing changes (paper stays the options desk's replay), so it is
    # safe by default; once the store covers a strategy's underlyings, it is replayed like any other.
    options_replay: bool = True
    history_coverage: bool = True  # each finished history ingestion (`league.history`) becomes a data.coverage row
    # Alpaca replays walk the history store's development window (`league/deep_replay.py`) when it
    # holds every input, and the live 21-day tape when it does not; a deep-replay pass is promoted
    # only after the sealed holdout passes too, at most `holdout_lineage_budget` times a lineage.
    deep_replay: bool = True
    deep_replay_days: int = 0  # 0: deep_replay.DEV_DAYS by horizon (252 daily, 63 hourly)
    holdout_gate: bool = True
    holdout_lineage_budget: int = 3
    # The tick never waits on a box that background work holds (`House.tick`). A wake whose box is
    # busy (its research replaying a candidate there) is skipped and retried on the next tick; the
    # births phase needs the probe box and waits at most `probe_wait_seconds` for it (a probe is
    # about 20 s and a box's sleep up to about 17 s, measured Sept 22, 2026), then defers to the
    # next tick. Measured Sept 23, 2026, 05:07Z: a hypothesis replay held the probe box through a
    # hung Sail call, and the House's first tick waited about twelve minutes for it.
    box_wait_seconds: float = 2.0
    probe_wait_seconds: float = 15.0
    # H5 (Sept 25, 2026, the forward-first run): the tick serves the wakes, every `tick_seconds` (30), and
    # what it did beside them keeps the cadence it had while ticks were sixty seconds or more apart.
    # Measured on the box 04:31-05:00Z Sept 25 (26 ticks, 128 living): ticks of 19-100 s, p50 60.8 s --
    # population 22.0 s at p50, 75.3 s at its slowest (the refill asked the displacement scan once for
    # each of 395 deferred research candidates, every tick: 399 scans, 17.1 of the 18.4 s the same tick
    # took on the T0 snapshot here), research 6.3, wakes 6.2, poll:kalshi-shadow 5.5, hypotheses 2.2,
    # publish 1.2. The log's tick lines landed 60-68 s apart at p50 in quiet hours (tick_seconds 60 was
    # the floor) and 97-121 s in the US session of Sept 24.
    #: The births pass (proven families, forks, merged strategies, the refill: the seat caps, the waiters
    #: and the displacement scan) at most this often, and on the first tick after any birth or death.
    population_pass_seconds: float = 300.0
    #: Research scheduling and the foundry's bookkeeping, on the House's own lane beside the tick.
    house_job_seconds: float = 60.0
    #: A simulated venue's pass (kalshi-shadow: resting orders re-quoted, held markets asked for a
    #: result). Its maker fills are decided on the quotes it samples, so sampling it twice as often
    #: would fill more practice orders than the record was earned under: the fill model's cadence stays.
    simulated_poll_seconds: float = 60.0
    #: A real venue's pass (`kalshi`, `alpaca`, and `alpaca-paper`, a real venue's practice account: every open order
    #: read, new settlements applied, the next slices of the exits sent) at most this often, as at sixty-second ticks
    #: (the review of #297, Sept 25, 2026). Every tick it doubled the venue calls and the exits' re-sends, and a venue
    #: failing every pass reached the ten warnings in thirty minutes that escalate to an error (`REPEAT_WARNINGS`) in
    #: about 4.5 minutes instead of about 9.5, inside a deploy's ten-minute watch: "alpaca-paper: could not poll or
    #: settle" came 10 times in 19 minutes on Sept 23 07:32-07:52Z at sixty-second ticks.
    venue_poll_seconds: float = 60.0
    #: The site's checkpoint: the site's load does not double with the tick.
    publish_seconds: float = 60.0
    #: At most one displacement a desk in this long (`_displaceable`): the "one a tick" of sixty-second ticks.
    desk_displacement_seconds: float = 60.0



def _replay_rules_key() -> str:
    """The replay gate's rules, hashed: a replay verdict is only as current as the rules it was reached under."""
    return hashlib.sha256(json.dumps(CONSTITUTION["ladder"]["replay"], sort_keys=True).encode()).hexdigest()[:16]


class _TickLaps:
    """The seconds each step of one tick took, on the monotonic clock (`time.perf_counter`, well
    under a microsecond a lap): `lap(step)` books the time since the previous lap to `step`, so every
    moment of the tick belongs to exactly one step (health.json `tick_steps`, `House._tick_steps`)."""

    __slots__ = ("began", "last", "seconds")

    def __init__(self) -> None:
        self.began = self.last = time.perf_counter()
        self.seconds: dict[str, float] = {}

    def lap(self, step: str) -> None:
        now = time.perf_counter()
        self.seconds[step] = self.seconds.get(step, 0.0) + (now - self.last)
        self.last = now


class House:
    def __init__(
        self,
        root: str | Path,
        *,
        brokers: Mapping[str, Any],
        sandbox: Any,
        alpaca_data: Any = None,
        kalshi_data: Any = None,
        provider: Any = None,
        commons: Commons | None = None,
        auditor: Any = None,
        publisher: Any = None,
        budget: Any = None,
        campaigns: Any = None,
        game: Mapping[str, Any] | None = None,
        settings: Settings | None = None,
        clock: Callable[[], float] = time.time,
        kill_switch: Callable[[], bool] | None = None,
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.settings = settings or Settings()
        from .overnight import active, game_for
        self._base_game = deepcopy(dict(game or load_game()))
        self._burst = active(campaigns, clock)
        self.game = game_for(self._base_game, self._burst)
        # L2 (Sept 24, 2026): turbo.json `sail_research_usd_per_hour`, the Sail research cap
        # (`_sail_cap_state`). It only ever holds research back, so it applies with or without a burst.
        from .overnight import load_turbo

        cap = load_turbo().get("sail_research_usd_per_hour")
        self._sail_research_cap: Decimal | None = Decimal(str(cap)) if cap is not None else None
        self._sail_cap_cache: tuple[float, dict[str, Any]] | None = None
        if self._burst:
            from .overnight import policy_with_turbo
            accelerated = policy_with_turbo(self._burst)
            self.settings.research_workers = accelerated['research_workers']
            self.settings.slow_workers = accelerated['replay_workers']
        self.ledger = Ledger(self.root / "ledger.sqlite", clock=clock)
        from .experiments import Experiments
        from .recordings import Recorder

        self.experiments = Experiments(self.root / "experiments", self.ledger, clock=clock)
        self.recorder = Recorder(self.root / "recordings.sqlite", clock=clock)
        self.research_jobs = ResearchJobs(self.root / "research.sqlite", clock=clock)
        self._closing = threading.Event()
        self.registry = Registry(self.ledger)
        self.economy = Economy(self.ledger, self.game, clock=clock)
        self.evaluator = Evaluator(self.ledger, clock=clock, archive=self.experiments.archive)
        from .campaigns import CampaignPacer

        self.campaigns = campaigns
        self.pacer = CampaignPacer(self.ledger, campaigns, clock=clock) if campaigns else Pacer(self.ledger, clock=clock)
        self.commons = commons or Commons(self.ledger)
        self.sandbox = sandbox
        self.alpaca_data = alpaca_data
        from .deep_replay import HOLDOUT

        self.holdout_window: tuple[str, str] = HOLDOUT  # the sealed window (tests shorten it)
        self.kalshi_data = kalshi_data
        if kalshi_data is not None and hasattr(kalshi_data, "settle_lags") and getattr(kalshi_data, "settle_lags", None) is None:
            # When each deadline-type series' markets pay after their close, measured on the settled
            # markets its replay tapes read, and kept beside the House's state (`resolution.SettleLags`):
            # what the horizon rule judges such a market by (review of #249, P1).
            from .resolution import SettleLags  # the protected answer (`ci.FORBIDDEN`) reads its own file

            kalshi_data.settle_lags = SettleLags(self.root / SETTLE_LAGS_FILE)
        self.provider = provider
        self.auditor = auditor
        self.publisher = publisher
        self.budget = budget
        self.merton: Any = None  # set by the service: Merton's pull-request roles, and the consultancy agents hire
        self.engineer: Any = None  # set by the service: the repair worklist's engineer (`league/engineer.py`)
        self.semantic_lab: Any = None
        self.options_history: Any = None  # set by the service: listed-option history (`league/options_history.py`)
        self.feeds: Any = None  # set by the service: the recorded feeds (`league/feeds.py`: scoreboards, perps, DVOL, funding, weather, earnings, rates ...)
        self._feeds_waiting: dict[str, float] = {}  # agent -> when it was last said its replay waits for recorded feeds
        self._feed_requests_at = 0.0  # when the tool requests the feeds answer were last looked at
        self.jev_floor: Any = None  # set by the service: research gate, inactivity, triage, links, exposure (league/sensors.py)
        self.hypotheses: Any = None  # set by the service: the hypothesis foundry (league/hypotheses.py)
        self.backup: Any = None  # set by the service on the House box: a daily checkpoint of the box, kept by Sail
        self.updater: Any = None  # set by the service on the House box: pulls main, hands it to the watchdog
        #: A cheap deterministic look at a paper agent's first wakes and code (`league/preaudit.py`):
        #: repair reports and a promotion-status mark, never a kill and never a statistic.
        from .preaudit import PreAudit
        from .consult_recovery import ConsultRecovery

        self.pre_audit: Any = PreAudit(self.ledger, clock=clock, settings=self.game.get("pre_audit"))
        #: Actionable work left in past `ask_merton` consults and research summaries, as repair
        #: reports (`league/consult_recovery.py`): a one-shot backfill, then incremental.
        self.consult_recovery: Any = ConsultRecovery(self.ledger, clock=clock, settings=self.game.get("consult_recovery"))
        self.kill_switch = kill_switch
        self.books: dict[str, Book] = {}
        for name, broker in brokers.items():
            real = name in REAL_BOOK.values()
            if real and not self.settings.real_money:
                continue
            if real and not getattr(self.sandbox, "secure", False):
                raise RuntimeError("real money needs agents in sealed Sailboxes, not the local sandbox")
            # A practice option fill pays the OCC clearing fee the paper account takes at the fill
            # (`league/fees.py`, Sept 24, 2026); when a real account takes it is not measured yet.
            self.books[name] = Book(
                name, broker, self.ledger, fees=Fees(family_of(name), option_clearing=not real), real_money=real, clock=clock,
                market_open=market_hours, kill_switch=kill_switch,
                resolves_at=self._resolves_at if family_of(name) == "kalshi" else None,
                event_capital_budget=(lambda venue=family_of(name): self._event_capital_budget(venue)) if family_of(name) == 'kalshi' else None,
                # The constitution's daily-loss keys (Sept 23, 2026, `allocator.bunt_daily_loss` and
                # `allocator.real_halt`) need two facts from the allocator, which is built after the
                # books, so a real book reads them lazily.
                band_of=(lambda agent_id: self.allocator.band_of(agent_id)) if real else None,
                halt_basis_usd=(lambda venue=family_of(name): self.allocator.halt_basis_usd(venue)) if real else None,
                # X0 (Sept 24, 2026): `allocator.real_entry_liquidity` holds a real event entry to a post-only
                # limit unless the agent's family's pooled taker record is positive; the allocator keeps that
                # record (`Allocator.family_taker`). An allocator without it answers None: not measured.
                family_taker=(lambda agent_id: getattr(self.allocator, "family_taker", lambda _agent: None)(agent_id)) if real else None,
            )
        self._state_path = self.root / "house.json"
        self._state = self._load_state()
        self.niches = niches_module.load()
        for niche_id, live in (self._state.get("niche_live") or {}).items():
            if niche_id in self.niches:
                self.niches[niche_id].live = tuple(live)
        #: R2 (Sept 24, 2026): each desk's niches.json cap, which a desk the search closes is held under
        #: (`_follow_the_search`) and gets back when it reopens; and the population the owner's turbo.json
        #: allows, which the league grows toward only while Sail's runway holds (`_population_rule`).
        self._base_caps = {desk: int(niche.max_members) for desk, niche in self.niches.items()}
        self._population_ceiling: int | None = int(self.game["economy"]["max_population"]) if self._burst else None
        self._data_cache: dict[str, tuple[Any, ...]] = {}  # key -> (read at, value, fetch began at)
        self._opens: dict[str, float | None] = {}  # UTC date -> that day's regular-session open (`_opened_since`)
        self._price_grids: dict[str, tuple[float, tuple[Any, ...]]] = {}  # "book:ticker" -> (read at, bands)
        self._tapes: dict[str, tuple[float, dict[str, Any]]] = {}
        self._tape_lock = threading.Lock()
        self._state_lock = threading.RLock()
        # Serialize lifecycle commits, not slow model/box/audit calls. A completed result must
        # still belong to the same strategy and rung when its effects reach the floor.
        self._lifecycle_lock = threading.RLock()
        #: Capital is the ladder (`league/allocator.py`, the owner's direction of Sept 23, 2026): when
        #: the constitution's `allocator.enabled`, bands and stakes follow evidence at every mark pass.
        self.allocator = allocator_module.Allocator(self, self.root)
        #: Collateral on every Kalshi exchange shard the desks trade (`league/shards.py`, Sept 23, 2026):
        #: an hourly pass on its own lane, and one at once after an `insufficient_shard_balance` refusal.
        self.shards: Any = shards_module.ShardFunder(self, self.root) if REAL_BOOK["kalshi"] in self.books else None
        # Slow work runs on daemon threads: a flex-window model call can take a quarter of an hour,
        # and a House that is told to stop must stop. (The provider settles an orphaned call later.)
        # Three lanes (measured on the first production start, Sept 19, 2026: with one two-slot queue,
        # research, the daily backup and the niche survey all waited behind 28 founders' replays).
        self._lanes = {"replay": threading.Semaphore(max(1, self.settings.slow_workers)),
                       "research": threading.Semaphore(max(1, self.settings.research_workers)),
                       "ops": threading.Semaphore(max(1, self.settings.ops_workers)),
                       # Audits wait behind no Merton pass and no backup: one at a time, their own lane.
                       "audit": threading.Semaphore(1),
                       # The live feeds too (`league/feeds.py`): a scoreboard polled behind a Merton pass
                       # or the backup is minutes of a live game the record never sees.
                       "feeds": threading.Semaphore(1),
                       # And the Kalshi shard funder (`league/shards.py`): a pass a refusal asked for
                       # must not wait behind Merton, the backup or a repair; one at a time.
                       "shards": threading.Semaphore(1),
                       # H5 (Sept 25, 2026): the tick's own bookkeeping, moved beside it (`_house_job`):
                       # research scheduling and the foundry's step. Behind Merton's three ops slots they
                       # would wait out a pass of minutes; one at a time, never two of the same.
                       "house": threading.Semaphore(1)}
        self._jobs: dict[str, threading.Thread] = {}
        self._job_status: dict[str, dict[str, Any]] = {}
        #: The tick's own clock (health.json `tick_steps`, Sept 24, 2026): the laps of the tick in hand,
        #: the last tick's, the ticks of the last hour (at, stamp, seconds a step) and each background
        #: lane's last run (`_background`; its time is not the tick's).
        self._laps: _TickLaps | None = None
        self._tick_last: dict[str, Any] | None = None
        self._tick_hour: deque[tuple[float, str, dict[str, float]]] = deque(maxlen=self.TICK_STEPS_KEPT)
        self._lane_last: dict[str, dict[str, Any]] = {}
        self._standings_memo: dict[str, Any] | None = None  # one standings table a tick (`standings`)
        #: H5 (Sept 25, 2026): the displacement scan's answers inside one births pass (`_displaceable`), and
        #: when the last pass ran and on which roster (`_births_due`).
        self._scan_memo: dict[str, Any] | None = None
        self._lane_memos: dict[int, dict[str, Any]] = {}  # a House-lane job's standings table (`_house_job`)
        self._births_pass: tuple[float, tuple[int, int]] | None = None
        self._foundry_turn = threading.Lock()  # a births pass and the foundry's step never run side by side
        #: H5: when the tick last ran each step it keeps at its own cadence ("publish", "house:research",
        #: "poll:<simulated book>" ...), on the House's clock.
        self._cadence: dict[str, float] = {}
        # What the tick put off because a box was busy (`_defer`): shown in health.json, told hourly.
        self._deferred: dict[str, dict[str, Any]] = {}
        self._deferred_told: dict[str, float] = {}
        #: When each desk last lost a resident to displacement (`kill`): one a desk a tick (`_displaceable`).
        self._desk_displaced: dict[str, float] = {}
        #: The desks' evidence clocks are measured by one thread at a time (`evidence_clocks`, S1).
        self._clock_lock = threading.Lock()
        #: (parent, its code, child, its code) -> when L1 last found no corrected entry there
        #: (`_supersede_by_research`): the look is taken again at most hourly a pair.
        self._supersede_seen: dict[tuple[str, str, str, str], float] = {}
        #: (agent, keeps hours) -> (what it was read from, its program's opportunity) (`_program_opportunity`).
        self._opportunities: dict[tuple[str, bool], tuple[tuple[int, int | None], tuple[float, int]]] = {}
        self.researcher = None
        if provider is not None:
            self.researcher = Researcher(
                ledger=self.ledger, provider=provider, commons=self.commons, economy=self.economy,
                rules=rules_text(self.game), contract=CONTRACT_PATH.read_text(encoding="utf-8"),
                run_replay=self._candidate_replay, settings=self.game.get("research") or {}, clock=clock,
                specialty=lambda agent: (self.niche_of(agent).text() if self.niche_of(agent) else ""),
                look=lambda agent: self.snapshot(agent, self.book_of(agent)), lineage=self.registry.lineage,
                standing=self.standing_of,
                merton_settings=self.game.get("consult") or {}, house_budget=lambda: self.pacer.may_spend("openai"),
                rung=self.evaluator.rung, jobs=self.research_jobs,
                may_continue=self._research_permission, capabilities=self.research_capabilities,
                coverage=self.research_coverage,
            )
        #: The gateway's monthly frontier line (`FrontierMonth`), set by `service.build`. None in
        #: tests and on a canary: every tier is then "all" and the gateway's 402 is the only line.
        self.frontier_month = None
        if self.researcher is not None:
            self.researcher.frontier_tier = self.frontier_tier
            self.researcher.trades = lambda agent_id: self._recent_trades(agent_id, limit=200)
            self.researcher.edit_replay = self._edit_replay  # `edit_params` (X1, Sept 24, 2026)
        self._born_at = self.clock()
        #: H6 (Sept 25, 2026): the research sessions in flight when this House started (a saved session that
        #: had begun), and what became of them (`_session_resumed`, `_session_lost`; health.json `restart_research`).
        self._restart_research: dict[str, Any] = {
            "started_at": now_iso(self.clock),
            "in_flight": {job["session"]: job["agent"] for job in self.research_jobs.pending() if job["status"] != "queued"},
            "resumed": 0, "retired": 0, "lost": [], "untold": []}
        self._restart_research["at_start"] = len(self._restart_research["in_flight"])
        self._inference_ceiling: Decimal | None = None  # the config's hard cap, read once (`_pace_inference`)
        # Written once, on the first ever start, and persisted: `_refill` paces newcomers from it
        # when none has been born yet (see there for why this must outlive a restart).
        self._state.setdefault("last_newcomer", {}).setdefault("since", self._born_at)
        self._record_start()
        # Every book's baseline is taken now, before anything can trade: what the venue holds at
        # this moment is what is not the book's. (Taken later, a resting order's reserved cash or a
        # first fill would be folded into the baseline and come back as a mismatch.)
        for name, book in self.books.items():
            try:
                if book.real_money:
                    # Fills the venue made while no House ran are booked first: a resting order that
                    # filled during a restart is a receipt, not a mismatch. Sept 23, 2026 05:07Z: a
                    # $9.50 Kalshi bid filled during a deploy's restart, this reconcile ran before the
                    # poll, froze the real book, and the watchdog rolled a good release back; the fill
                    # was booked twelve seconds later, on the first mark pass.
                    try:
                        book.poll()
                    except Exception as exc:  # noqa: BLE001 - the reconcile below says what is unknown
                        self.alert("warning", f"{name}: could not poll the venue before reconciling ({type(exc).__name__}: {str(exc)[:160]})",
                                   **environment("gateway", exc))
                    book.reconcile()  # repair/check receipts before health, agent wakes or sizing
                else:
                    book.open_baseline()
            except Exception as exc:  # noqa: BLE001 - a venue that is down now is reconciled on a later tick
                self.alert("warning", f"{name}: could not initialize venue accounting ({type(exc).__name__}: {str(exc)[:160]})")
        # The Alpha Lab (league/lab.py): built only when game.json switches it on and a lab box is
        # configured; its tools for researchers, and longer sessions for agents with evidence.
        from .lab import attach as attach_lab
        attach_lab(self)
        # The desks' evidence clocks (S1, Sept 24, 2026), measured at startup when the stored reading is a
        # day old or missing: a few thousand fill rows, well under a second, before any seat is judged.
        self.evidence_clocks()
        # R2 (Sept 24, 2026): the population the league may grow to, from Sail's runway, before any seat is asked for.
        try:
            self._population_rule()
        except Exception as exc:  # noqa: BLE001 - the ceiling stands until the next pass reads the meter
            self.alert("warning", f"the population rule could not read Sail's runway ({type(exc).__name__}: {str(exc)[:160]})",
                       **environment("sail", exc))
        # Alive, with its books open: the watchdog reads this file, and a House's first tick is its slowest.
        self._health({"at": now_iso(self.clock)})

    def _chain(self, symbols: list[str], days: int, afford: float, quotes: Mapping[str, Any]) -> list[dict[str, Any]]:
        """The option contracts an agent may consider: its underlyings, expiring after today and
        within `days`, within a fifth of the underlying's price, two-sided, and affordable in one
        order. At most 40 an underlying, nearest the money first. Empty where the venue cannot list."""
        broker = next((b.broker for name, b in self.books.items() if family_of(name) == "alpaca" and hasattr(b.broker, "option_chain")), None)
        if broker is None:
            return []
        today = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        first, last = _plus_days(today, 1), _plus_days(today, days)
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            touch = quotes.get(symbol) or {}
            spot = ((touch.get("bid") or 0) + (touch.get("ask") or 0)) / 2 or None
            try:
                chain = broker.option_chain(symbol, expiry_from=first, expiry_to=last)
            except Exception as exc:  # noqa: BLE001 - one underlying's outage is not the wake's
                self.alert("warning", f"option chain {symbol}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            if self.options_history is not None:
                try:  # the quotes are already in hand: keeping them is the options replay's quote history
                    self.options_history.record_quotes([c for c in chain if spot is None or abs(c["strike"] / spot - 1) <= 0.20],
                                                       source=str(getattr(broker, "option_feed", "") or ""))
                except Exception as exc:  # noqa: BLE001 - a full disk is not the wake's problem
                    self.alert("warning", f"option quotes not kept ({type(exc).__name__}: {str(exc)[:120]})")
            near = [c for c in chain if c["ask"] <= afford and (spot is None or abs(c["strike"] / spot - 1) <= 0.20)]
            near.sort(key=lambda c: (abs(c["strike"] / spot - 1) if spot else 0, c["expiry"]))
            rows += [{**c, "occ": c["symbol"], "underlying_price": spot} for c in near[:40]]
        return rows

    def _observed(self, watched: Mapping[str, Any], needs: Mapping[str, Any]) -> dict[str, Any]:
        """What a strategy may watch and may not trade: bars and the touch of any Alpaca symbol,
        and the open markets of any Kalshi series, on either venue whatever its own is. Measured
        Sept 19, 2026: five agents asked the toolsmith for exactly this and it could not be built
        as a tool, because what they wanted was data the House does not fetch."""
        out: dict[str, Any] = {}
        symbols = [str(x) for x in (watched.get("symbols") or [])][:6]
        series = [str(x) for x in (watched.get("series") or [])][:6]
        if symbols and self.alpaca_data is not None:
            bars = dict(needs.get("bars") or {})
            timeframe = str(bars.get("timeframe") or "1Hour")
            limit = max(1, min(int(bars.get("limit") or 60), 200))
            key = f"observe:{','.join(symbols)}:{timeframe}:{limit}"
            try:
                out["bars"] = self._cached(key, 60, lambda: self.alpaca_data.bars(symbols, timeframe, limit=limit))
                out["quotes"] = self._cached(f"observe-q:{','.join(symbols)}", 30, lambda: self.alpaca_data.quotes(symbols))
            except Exception as exc:  # noqa: BLE001 - a feed that is down is not the agent's wake
                out["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        if series and self.kalshi_data is not None:
            try:
                out["markets"] = self._cached(f"observe-m:{','.join(series)}", 60, lambda: self._markets(series, 24.0, 120.0))
            except Exception as exc:  # noqa: BLE001
                out["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return out

    def _markets(self, series: list[str], hours: float, max_age: float) -> list[dict[str, Any]]:
        try:
            return self.kalshi_data.markets(series, max_hours_to_close=hours, max_age=max_age)
        except TypeError:  # a data source that does not share listings
            return self.kalshi_data.markets(series, max_hours_to_close=hours)

    def _resolves_at(self, instrument: Any) -> float | None:
        if self.kalshi_data is None:
            return None
        return self.kalshi_data.resolves_at(instrument.market_id or instrument.symbol)

    def _horizon_refusal(self, agent: Agent, book: Book, instrument: Instrument) -> str:
        """The horizon rule's refusal of a Kalshi entry, saying what the House judged it by, or "".

        X2 (Sept 24, 2026, the close-the-gaps run): the book refuses an entry expected to pay past the
        agent's horizon ("this market is expected to resolve in N hours"), and its refusal cannot say
        what N was measured to (`league/resolution.py`, a money judge in `ci.FORBIDDEN`): the market's
        scheduled expiration; its close plus
        its series' measured settle lag, where the venue's "expected" expiration is a deadline days
        after the close; that deadline, where the lag cannot be measured yet; or its close, where the
        venue lists none. The House asks the book's own question of the book's own answer
        (`_resolves_at` reads the same `KalshiData.resolution_of`, the same seat limit) before the
        book does, and says which. Whatever it cannot tell it leaves to the book, which refuses it
        ("cannot tell when this market resolves"): this never admits an entry the book would refuse."""
        if instrument.asset_class != "event" or self.kalshi_data is None:
            return ""
        limits = book.limits.get(agent.id)
        horizon = getattr(limits, "max_hours_to_resolve", None)
        lookup = getattr(self.kalshi_data, "resolution_of", None)
        if horizon is None or not callable(lookup):
            return ""
        try:
            found = lookup(instrument.market_id or instrument.symbol)
            hours = None if found is None else (float(found.due) - self.clock()) / 3600.0
        except Exception:  # noqa: BLE001 - not knowing is the book's to refuse
            return ""
        if hours is None or hours <= float(horizon):
            return ""
        from .resolution import CLOSE, DEADLINE, SCHEDULED, SETTLE_LAG, SETTLE_LAG_MIN_MARKETS
        from .tapes import iso as tape_iso

        if found.basis == SCHEDULED:
            judged = f"by its scheduled expiration ({tape_iso(found.due)})"
        elif found.basis == SETTLE_LAG:
            judged = (f"by its close plus its series' measured settle lag ({tape_iso(found.due)}: {found.lag_hours:g} hours after the "
                      f"close, the 95th percentile of its last {found.markets} settled markets; its expected expiration, "
                      f"{tape_iso(found.deadline)}, is a deadline, not a schedule)")
        elif found.basis == DEADLINE:
            judged = (f"by its expected expiration ({tape_iso(found.due)}), a deadline days after its close: its series has fewer than "
                      f"{SETTLE_LAG_MIN_MARKETS} settled markets on record to measure when it pays")
        elif found.basis == CLOSE:
            judged = f"by its close ({tape_iso(found.due)}): the venue lists no scheduled expiration for it"
        else:
            judged = f"({tape_iso(found.due)})"
        return f"this market is expected to resolve in {hours:.0f} hours, {judged}; entries must resolve within {float(horizon):g}"

    # ------------------------------------------------------------------ state
    def _load_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A new House has no replay verdict reached under older rules to revisit.
            state = {"replay_rules": _replay_rules_key()}
        for key in ("next_wake", "memory", "last_research", "tried", "last_mark", "settled", "niche_live", "series_category", "idle"):
            state.setdefault(key, {})
        return state

    def _replay_rules_changed(self) -> None:
        """A rung-0 agent's code gets one replay (`_replay_own`), judged under the replay rules then
        in force, and afterwards "only research can change its fate". When the owner changes those
        rules, each living rung-0 agent gets one fresh replay under the new ones: its old verdict
        answered a question the league no longer asks. Sept 22, 2026: the revision that took the
        deflated Sharpe off the paper gate found 33 agents on rung 0 -- whole desks, Alpaca
        megacaps and crypto majors among them -- whose code had had its replay under the old gate."""
        key = _replay_rules_key()
        if self._state.get("replay_rules") != key:
            with self._state_lock:
                retried = [a.id for a in self.registry.living()
                           if self.evaluator.rung(a.id) == 0 and self._state["tried"].pop(a.id, None) is not None]
                self._state["replay_rules"] = key
                self._state["revive_pending"] = True
            if retried:
                self.alert("info", f"the replay rules changed: {len(retried)} agent(s) on rung 0 get one fresh replay under them")
        if not self._state.get("revive_pending") or self._closing.is_set():
            return
        # Each revival probes its code's NEEDS: with the probe box busy it waits for a later tick.
        with self._probe_turn("revival") as free:
            if free:
                try:
                    self._revive_near_misses()
                except SandboxError as exc:
                    self._defer("revival", f"infrastructure: {str(exc)[:200]}")
                    return
                with self._state_lock:
                    self._state.pop("revive_pending", None)

    #: How an agent that never left rung 0 may have died without its code being judged unfit.
    REVIVABLE_CAUSES = ("never qualified", "displaced", "stuck", "credits")

    def _revive_near_misses(self, *, within_seconds: float = 2 * 86400, limit: int = 12) -> list[str]:
        """When the replay gate loosens its out-of-sample floor, bring back, once, the code of agents
        that died on rung 0 in the last two days after a replay whose ONLY failure was out-of-sample
        growth the new floor admits: a newcomer on the same line, with the same parameters, where the
        league and its desk have seats (never more than half the league's free seats). It is on rung 0
        and replayed like any newcomer, so today's tape decides, not the old verdict; its lineage is
        kept, holdout budget and all.

        Swing and bunt, Sept 23, 2026: 38 of 148 replays from 21:00Z Sept 22 to 03:20Z failed by less
        than the new floor allows. Most were hourly Alpaca crypto -- the only strategies that trade the
        Alpaca account around the clock, where one agent of thirty was a crypto agent -- and their
        agents had died on rung 0 before the rules moved."""
        floor = float(CONSTITUTION["ladder"]["replay"].get("min_oos_growth", 0.0))
        if floor >= 0:
            return []
        rules = self.game["economy"]
        living = self.registry.living()
        budget = min(limit, (int(rules["max_population"]) - len(living)) // 2)
        if budget <= 0:
            return []
        now = self.clock()
        recent = [a for a in reversed(self.registry.dead())  # the most recent deaths first
                  if a.cause in self.REVIVABLE_CAUSES and a.died_at and now - _epoch(a.died_at) <= within_seconds]
        if not recent:
            return []
        wanted = {a.id for a in recent}
        last_trial: dict[str, Mapping[str, Any]] = {}
        for entry in self.ledger.iter(kinds="eval.trial"):
            if entry.agent in wanted:
                last_trial[entry.agent] = entry.payload
        # A strategy is its code AND its parameters: a line's mutations share code and differ in params.
        same = lambda a: (a.code_sha256, json.dumps(a.params or {}, sort_keys=True))  # noqa: E731
        running = {same(a) for a in living}
        revived: list[str] = []
        for agent in recent:
            if len(revived) >= budget:
                break
            trial = last_trial.get(agent.id) or {}
            reasons, oos = list(trial.get("reasons") or []), trial.get("oos_mean_log_growth")
            if self.evaluator.max_rung(agent.id) > 0 or not reasons or oos is None \
                    or not all(str(r).startswith("out-of-sample growth is not above") for r in reasons):
                continue
            # Exactly zero is a program that sat the out-of-sample stretch out, which the floor does not admit.
            if not floor < float(oos) < 0 or same(agent) in running:
                continue
            # Code a merged repair corrects is not brought back: it would be retired as superseded
            # within the hour (haghani-40 to -42, Sept 23, 2026 04:23Z).
            if self._known_defect(agent):
                continue
            # Nor the code of a family the forward record has already judged (Sept 23, 2026).
            if self._losing_family(agent.family):
                continue
            niche = self.niches.get(agent.specialty or "")
            if niche is None or niche.dormant or self.members(niche.id) >= niche.max_members:
                continue
            running.add(same(agent))
            try:
                child = self.spawn(agent.line or agent.name, agent.family, agent.code, parent=agent.id, params=agent.params,
                                   endowment=rules["endowment_usd"], specialty=niche.id,
                                   reason=(f"revived under the loosened replay gate: {agent.id} died on rung 0 ({agent.cause}) after a "
                                           f"replay that failed only on out-of-sample growth ({float(oos):+.4%} a block), which the "
                                           f"floor of {floor:+.3%} a block now admits; it is replayed afresh on today's tape"))
            except ValueError as exc:
                self.alert("info", f"{agent.id}: not revived under the loosened replay gate ({str(exc)[:160]})")
                continue
            revived.append(child.id)
        if revived:
            self.alert("info", f"the replay gate loosened: {len(revived)} strateg{'y' if len(revived) == 1 else 'ies'} that died on "
                               f"rung 0 by less than the new out-of-sample floor were born again ({', '.join(revived)})")
        return revived

    def _save_state(self) -> None:
        # The write under the lock too: the audit job saves from its own thread (it persists the
        # audit it starts and the one it finishes), and two writers sharing one temporary file
        # could lose a replace or leave an older snapshot behind a newer one.
        with self._state_lock:
            text = json.dumps(self._state, sort_keys=True)
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._state_path)

    def _record_start(self) -> None:
        self.ledger.append(
            "ops.started",
            {"constitution": constitution_digest(), "real_money": self.settings.real_money, "books": sorted(self.books),
             "sandbox": type(self.sandbox).__name__, "release": Path(__file__).resolve().parents[1].name},
        )

    def alert(self, level: str, text: str, **payload: Any) -> None:
        """An `ops.alert` row. `payload` rides in the same row beside the level and the text (D1,
        Sept 24, 2026: the Alpha Lab's step sends its traceback as `_traceback`; a key that starts
        with an underscore is private, and `ledger.public_view` strips it from everything published).

        A warning that repeats escalates (L3, Sept 24, 2026; `_repeating`): the same text
        (`alert_key`) `REPEAT_WARNINGS` times inside `REPEAT_WINDOW_SECONDS` becomes ONE error alert
        carrying the last warning's payload -- its traceback when the caller supplied one -- with
        `repeated` (the folded text, the count, first and last seen) and `began_at` (when the run of
        repeats began: `league/watchdog.py` counts an error whose condition began before a promotion
        as inherited, never as the new release's doing). It carries the `environment` marker (H2,
        Sept 25, 2026: a service outside the House failed, never a rollback) only when every warning
        of the run carried the same one."""
        row = self.ledger.append("ops.alert", {**payload, "level": level, "text": str(text)[:1000]})
        if str(level).lower() == "warning":
            self._repeating(str(text), payload, seq=getattr(row, "seq", None))

    def _repeating(self, text: str, payload: Mapping[str, Any], *, seq: int | None = None) -> None:
        """Count one warning toward its run of repeats; escalate once when the run reaches the line.
        The runs live in the House's state (house.json), so a restart neither forgets a run nor
        escalates it again; a House whose state holds none rebuilds them from the ledger
        (`_repeating_runs`, before `seq`: this warning's own row, which is counted here)."""
        lock, state = getattr(self, "_state_lock", None), getattr(self, "_state", None)
        if lock is None or state is None:
            return  # an alert raised while the House is still being built
        now = self.clock()
        key = alert_key(text)
        escalate = None
        with lock:
            run = _count_repeat(self._repeating_runs(before=seq), text, now, now_iso(self.clock), payload.get("environment"))
            if len(run["times"]) >= REPEAT_WARNINGS and not run.get("escalated"):
                run["escalated"] = now_iso(self.clock)
                escalate = {k: run.get(k) for k in ("first_seen", "last_seen", "count", "environment")} | {"in_window": len(run["times"])}
        if escalate is not None:
            minutes = int(REPEAT_WINDOW_SECONDS // 60)
            marked = {"environment": escalate["environment"]} if escalate["environment"] else {}  # H2: a service's run stays its
            self.ledger.append("ops.alert", {
                **{k: v for k, v in payload.items() if k != "environment"}, **marked, "level": "error",
                "text": f"a warning repeated {escalate['in_window']} times in {minutes} minutes: {text}"[:1000],
                "repeated": {"text": key, "count": escalate["count"], "first_seen": escalate["first_seen"], "last_seen": escalate["last_seen"]},
                "began_at": escalate["first_seen"]})

    def _repeating_runs(self, *, before: int | None = None) -> dict[str, Any]:
        """The runs of repeats in the House's state (call under `_state_lock`). A state that holds
        none -- the first start of this code over an older House's house.json, or a lost house.json
        -- rebuilds them from the ledger's own recent warnings and escalations, so a condition that
        was already repeating keeps the moment it began and an escalated run is not said again.

        Review of #236 (Sept 24, 2026): Deploy A's House counted no runs, so Deploy B's House would
        have begun every run at its own restart, and a warning that repeated all through Deploy A (a
        site refusing every checkpoint: 11 in the 12 minutes after three restarts on Sept 23) would
        have escalated inside Deploy B's watch with `began_at` after the promotion -- and the
        watchdog would have rolled the healthy release back for a condition it inherited."""
        runs = self._state.get("repeating_warnings")
        if isinstance(runs, dict):
            return runs
        runs = {}
        try:
            rows = self.ledger.read(kinds="ops.alert", limit=2000, newest=True)
        except Exception:  # noqa: BLE001 - a ledger that cannot be read leaves the runs to begin now
            rows = []
        for entry in rows:
            if before is not None and entry.seq >= before:
                continue  # the warning being counted now
            level, repeated = str(entry.payload.get("level") or "").lower(), entry.payload.get("repeated")
            try:
                at = _epoch(entry.at)
            except (TypeError, ValueError):
                continue
            if level == "error" and isinstance(repeated, Mapping):
                escalated = runs.get(str(repeated.get("text") or ""))
                if escalated is not None:
                    escalated["escalated"] = entry.at
            elif level == "warning":
                _count_repeat(runs, str(entry.payload.get("text") or ""), at, entry.at, entry.payload.get("environment"))
        now = self.clock()
        for quiet in [k for k, run in runs.items() if now - float(run.get("last_epoch") or 0) >= REPEAT_WINDOW_SECONDS]:
            runs.pop(quiet)
        self._state["repeating_warnings"] = runs
        return runs

    def _repeating_health(self) -> list[dict[str, Any]]:
        """health.json `repeating_warnings`: each escalated run until it has been quiet for the window."""
        now = self.clock()
        with self._state_lock:
            runs = self._repeating_runs()
            for quiet in [k for k, run in runs.items() if now - float(run.get("last_epoch") or 0) >= REPEAT_WINDOW_SECONDS]:
                runs.pop(quiet)
            return [{"text": run.get("text"), "key": key, "count": run.get("count"), "first_seen": run.get("first_seen"),
                     "last_seen": run.get("last_seen"), "escalated_at": run.get("escalated")}
                    for key, run in sorted(runs.items(), key=lambda kv: str(kv[1].get("first_seen"))) if run.get("escalated")]

    # ------------------------------------------------------- a tick that never blocks
    def _box_patience(self) -> Any:
        """Within this block, a sandbox call from this thread waits at most `box_wait_seconds` for
        a box another caller holds, then raises `SandboxBusy` (league/sandbox.py). A sandbox with
        no locks of its own (the local one, the tests' in-process ones) runs as before."""
        patience = getattr(self.sandbox, "patience", None)
        return patience(self.settings.box_wait_seconds) if patience is not None else nullcontext()

    @contextmanager
    def _probe_turn(self, what: str) -> Iterator[bool]:
        """The probe box, held for a block of births (their NEEDS probes reenter it), or False
        after `probe_wait_seconds` with the deferral recorded: never a failure of any strategy."""
        claim = getattr(self.sandbox, "claim", None)
        if claim is None:
            yield True
            return
        with claim(PROBE_BOX, wait=self.settings.probe_wait_seconds) as held:
            if not held:
                self._defer(what, f"the probe box is in use by background work (waited {self.settings.probe_wait_seconds:g}s)")
            yield held

    def _defer(self, what: str, reason: str) -> None:
        """Work the tick put off because a box was busy or Sail did not answer. Kept for health.json
        and told as an info alert at most every fifteen minutes a kind: it is infrastructure, not a
        strategy's result, and it is tried again on the next tick."""
        now = self.clock()
        with self._state_lock:
            row = self._deferred.setdefault(what, {"count": 0, "first_at": now_iso(self.clock)})
            row.update(count=row["count"] + 1, reason=str(reason)[:300], at=now_iso(self.clock), epoch=now)
            tell = now - self._deferred_told.get(what, float("-inf")) >= 900
            if tell:
                self._deferred_told[what] = now
        if tell:
            self.alert("info", f"{what} deferred to a later tick: {str(reason)[:300]}")

    def begin_close(self) -> None:
        """TERM: start no new background work from now on, and let the tick in hand skip its births.
        The loop ends after the tick in hand, which no longer waits on any box background work holds."""
        self._closing.set()

    def stopped(self) -> bool:
        return (self.root / "STOP").exists()

    def paused(self) -> dict[str, Any] | None:
        """The operator's maintenance pause: `PAUSE` in the House root, with the reason as its text.

        STOP ends the loop, and with it reconciliation and every exit. PAUSE keeps the loop and
        closes everything that spends or enters: no research, Merton, semantic lab, survey, replay,
        births or payouts; no promotion; only agents already holding a position are woken, and
        only their exits and cancels reach a book. Research in flight defers at its next paid turn
        and resumes from its checkpoint when the file is removed. The clock-based culls wait too,
        because an agent cannot replay or trade its way out of a pause."""
        path = self.root / "PAUSE"
        try:
            text = path.read_text(encoding="utf-8")[:500].strip()
        except FileNotFoundError:
            return None
        except OSError:
            text = ""
        return {"reason": text or "maintenance"}

    def _holds_position(self, agent: Agent) -> bool:
        """Anything on its own book that a pause must still let it manage: holdings or orders."""
        book = self.book_of(agent)
        return bool(book and agent.id in book.accounts and (book.account(agent.id).holdings or book.open_orders(agent.id)))

    # ------------------------------------------------------------ population
    def founders(self) -> list[dict[str, Any]]:
        """Every founder of every open specialty: a seed's program pointed at the niche's markets."""
        rows = {row["name"]: row for row in seeds_module.SEEDS}
        out = []
        for niche in self.niches.values():
            if niche.dormant:
                continue
            for founder in niche.founders:
                seed = rows[founder["seed"]]
                # One family a program a specialty: real-money records are pooled among agents that
                # run the same idea on the same kind of market. (Replay trials are counted by line.)
                family = seed["family"] if founder["key"] == founder["seed"] else f"{niche.id.split('-', 1)[1]}-{seed['family'].split('-', 1)[-1]}"
                out.append({"name": niche.desk, "key": founder["key"], "family": family, "niche": niche.id, "why": seed["why"],
                            "code": niches_module.founder_code(seeds_module.load(founder["seed"]), niche, founder)})
        return out

    def found(self, names: list[str] | None = None) -> list[Agent]:
        """Seed the first population (idempotent: a founder already born is not born again).

        Founders of one desk share a name and number themselves: the six of the Meriwether desk are
        `meriwether`, `meriwether-2` ... `meriwether-6`. So what says a founder is already born is
        its `key` (the role it plays on that desk), not the name it ends up with."""
        born = []
        existing = {a.founder for a in self.registry.agents.values()}
        wanted = [f for f in self.founders() if (names is None or names_match(f, names)) and f["key"] not in existing]
        for index, seed in enumerate(wanted):
            # The probe box stays awake between seeds: most of reading a strategy's NEEDS is the box waking.
            agent = self.spawn(seed["name"], seed["family"], seed["code"], reason=seed["why"], specialty=seed["niche"],
                               founder=seed["key"], keep_probe_awake=index < len(wanted) - 1)
            # The founders are the owner's priors (what the first run measured, and published
            # research): they start their forward test at once, because paper costs nothing and
            # forward evidence is the evidence that counts. Their replay is still run and still
            # counts as their family's first trial. Everything born later must pass replay first.
            if self.evaluator.rung(agent.id) < 1:
                self.evaluator.seat(agent.id, 1, "a founding seed: forward-tested from the first day")
            self.seat(agent)
            born.append(agent)
        return born

    def enroll(self) -> list[Agent]:
        """Give merged strategies their life: each is born once, on rung 0, with a seed's
        endowment. They answer to replay like any child. Corrected children (a `repair` row) come
        first, and a full league makes room for them.

        Until Sept 23, 2026 a strategy was born only while the population had an empty seat, and
        the refill kept all 64 seats full: the engineer's fifteen merged repairs and the architect's
        megacap strategy were deployed as files and never born. The repair queue waited at
        `observing` for children that could not arrive, and the defective parents kept trading."""
        from . import strategies

        # A few a tick: each birth probes the strategy's NEEDS in a box (about 20 s). Measured Sept 22,
        # 2026: a fresh canary enrolled all sixteen merged strategies in one tick, its third tick
        # took over 300 s, and the watchdog refused the release -- every later release would have
        # failed the same way as the engineer merged more strategies. The rest are born next tick.
        born = []
        known = {a.founder for a in self.registry.agents.values()}
        refused = self._state.setdefault("enroll_refused", {})
        rules = self.game["economy"]
        waiters = self.seat_waiters()  # first: a strategy whose desk the search has closed leaves the queue here (R2)
        gone = self._state.get("seat_expired") or {}
        rows = [row for row in strategies.all_strategies()
                if row["name"] not in known and refused.get(row["name"]) != code_sha(row["code"]) and f"strategies:{row['name']}" not in gone]
        foundry = getattr(self, "hypotheses", None)
        if foundry is not None and foundry.enabled():
            # Sept 23, 2026: a corrected child is replayed before it takes any seat (league/hypotheses.py
            # `takes_strategy`); the engineer's 16 children had 0 forward blocks and 7 died on rung 0.
            rows = [row for row in rows if not (isinstance(row.get("repair"), dict) and foundry.takes_strategy(row))]
        rows.sort(key=lambda row: not isinstance(row.get("repair"), dict))  # corrected children first
        # Sept 23, 2026: a merged strategy has forward evidence (it passed review and CI), so it may
        # take a replay-only or never-traded seat inside its grace (`_weakest`, `evidenced`), but the
        # desks a lab graduate or a replay-passed card waits for are theirs first. Six merged
        # strategies (#34, #49, #121, #154, #161, #169) had never been born, and nothing said so.
        reserved = self._reserved_desks(waiters, below="strategies")
        for row in rows:
            if len(born) >= max(1, int(self.settings.enroll_per_tick)):
                break
            loser = None
            if len(self.registry.living()) >= int(rules["max_population"]):
                if not self.settings.enroll_displaces:
                    break
                # The seat of an agent still running the code this strategy corrects (it cannot be
                # promoted: its defect is on record), else the weakest resident that has had its chance.
                loser = self._defective_resident(row) or self._weakest(
                    rules, evidenced=True, exclude=self._keep_for(reserved),
                    newcomer=Newcomer(family=row.get("family"), venue=_code_venue(row["code"]), what=f"the merged strategy {row['name']}"))
                if loser is None:
                    self._refuse_birth("strategies", len(rows) - len(born),
                                       "the league is full and no resident may be displaced, even by a newcomer with forward evidence"
                                       + (f" ({len(reserved)} desk(s) are held for waiting graduates or cards)" if reserved else ""))
                    break
            try:
                # Named from the desk its NEEDS put it on, like every other agent: the strategy's
                # own name in the registry is what says it has already been born.
                child = self.spawn("", row["family"], row["code"], reason="Merton, as architect: " + row["why"], founder=row["name"])
            except ValueError as exc:
                refused[row["name"]] = code_sha(row["code"])  # once per file version, not every tick
                self.alert("warning", f"the architect's strategy {row['name']} could not be born: {str(exc)[:200]}")
                continue
            born.append(child)
            if loser is not None:
                self.kill(loser, "displaced", self.postmortem(loser, "displaced",
                    f"the league was full and the merged strategy {row['name']} ({child.id}) takes its seat"))
        if self.settings.enroll_displaces:
            self._retire_superseded()
        self._supersede_by_research()  # L1: the research route joins the repair route (the constitution's key gates it)
        return born

    def _defective_shas(self, row: Mapping[str, Any]) -> set[str]:
        """The code a merged repair corrects: the sha in a `strategy_defect:<agent>:<sha12>` key, and
        the named parent's code. Empty for a repair that names neither (a bug report or a refusal
        pattern is evidence about a desk, not about one program)."""
        repair = row.get("repair") if isinstance(row.get("repair"), Mapping) else {}
        shas = set()
        parts = str(repair.get("key") or "").split(":")
        if len(parts) == 3 and parts[0] == "strategy_defect" and len(parts[2]) >= 12:
            shas.add(parts[2])
        parent = self.registry.get(str(repair.get("parent") or ""))
        if parent is not None:
            shas.add(parent.code_sha256)
        return shas

    def _running_defect(self, shas: set[str], *, exclude: Sequence[str] = ()) -> list[Agent]:
        """Living agents off real money whose code is one of `shas` (a full sha or a 12-character prefix)."""
        # The code check first: `rung` reads the ledger, and this runs every tick.
        return [a for a in self.registry.living()
                if a.id not in exclude and any(a.code_sha256.startswith(s) for s in shas) and self.evaluator.rung(a.id) <= 1]

    def _defective_resident(self, row: Mapping[str, Any]) -> Agent | None:
        """An agent running the code `row` corrects, replay agents before paper ones."""
        found = self._running_defect(self._defective_shas(row))
        return min(found, key=lambda a: (self.evaluator.rung(a.id), a.born_at)) if found else None

    def _retire_superseded(self) -> int:
        """Retire every agent (never one on real money) still running code that a BORN corrected
        child replaces. Its defect is on record, so no audit would pass it and its forward record
        measures the defect as much as the idea; the child is judged on its own evidence."""
        from . import strategies

        born = {a.founder: a for a in self.registry.agents.values() if a.founder}
        retired = 0
        for row in strategies.all_strategies():
            child = born.get(row["name"])
            if child is None or not isinstance(row.get("repair"), Mapping):
                continue
            shas = self._defective_shas(row) - {child.code_sha256}
            for agent in self._running_defect(shas, exclude=(child.id,)) if shas else ():
                self.kill(agent, "superseded", f"its code carries the defect that {row['name']} ({child.id}) corrects "
                                               f"(repair {row['repair'].get('key')}); the corrected child is judged on its own evidence")
                retired += 1
        return retired

    #: How long an L1 look that found no corrected entry is not taken again (`_supersede_by_research`).
    SUPERSEDE_RECHECK_SECONDS = 3600

    def _supersede_by_research(self) -> int:
        """L1 (the close-the-gaps run, Sept 24, 2026; `CONSTITUTION["allocator"]["corrected_child_supersedes"]`,
        off without the key): when a research child of a living parent has passed replay and its own account
        of its program names the parent's ENTRY mechanism as the defect -- the liquidity it takes, the fee
        that costs, the side it buys (`entry_defect`), borne out by the parent's own entry fills
        (`_entry_fills`) -- the parent is superseded at once: demoted to practice through the evaluator first
        when it is on real money, then retired as `superseded`, as the engineer's repair route retires the
        agents a merged corrected child replaces (`_retire_superseded`). The child keeps its seat and enters
        real money when the allocator's rules seat it on its own evidence, as a probe or a bunt by its
        family's state; the House stakes nothing here. Evidence: meriwether-h2d625d kept taking 7%-fee taker
        moneylines on real money after its child meriwether-h2d625d-2 passed replay (40 trades) with the
        maker fix at 00:18:31Z Sept 24. Returns how many parents it superseded."""
        if allocator_module.rules().get("corrected_child_supersedes") is not True:
            return 0
        now = self.clock()
        done = 0
        for child in list(self.registry.living()):
            parent = self.registry.get(child.parent) if child.parent else None
            if parent is None or not parent.alive or parent.code_sha256 == child.code_sha256:
                continue
            key = (parent.id, parent.code_sha256, child.id, child.code_sha256)
            if now - self._supersede_seen.get(key, float("-inf")) < self.SUPERSEDE_RECHECK_SECONDS:
                continue
            why = self._corrected_entry(parent, child)
            if why is None:
                self._supersede_seen[key] = now
                continue
            done += self._supersede(parent, child, why)
        return done

    def _corrected_entry(self, parent: Agent, child: Agent) -> str | None:
        """Why `child` supersedes `parent` under L1, or None: the child is seated on paper or above, research
        wrote its current program (its parent's research candidate, or its own rewrite), that program passed
        replay, its account of itself names an entry defect of the PARENT's current program, and the programs
        bear it out -- a liquidity or fee defect needs a parent whose entries were takers and a child whose
        program rests its entries post-only (`posts_maker_entries`), a side defect a parent that entered at
        all. A maker parent is never superseded for "post-only" in its child's words (mullins-2 and mullins-14),
        nor a taker parent for a child that takes too."""
        if self.evaluator.rung(child.id) < 1:
            return None
        account = self._program_account(parent, child)
        if account is None:
            return None
        passed = any(e.payload.get("passed") and e.payload.get("code_sha256") == child.code_sha256
                     for who in (child.id, parent.id) for e in self.ledger.iter(kinds="eval.trial", agent=who))
        if not passed:
            return None
        kind = entry_defect(account)
        if kind is None:
            return None
        taker, maker = self._entry_fills(parent)
        if kind in ("liquidity", "fee"):
            if not (taker and taker >= maker and posts_maker_entries(child.code)):
                return None
            proven = self._taker_proven(parent)
            if proven is not None:
                # A maker "fix" of a mechanism whose family's pooled TAKER record is proven positive -- the record the
                # real book's X0 rule reads to let that family take -- is not a defect fix (the main session's
                # decision on the review of #245, Sept 24, 2026). Told once, as L1 tells its supersessions.
                self._note_supersede_skipped(parent, child, kind, proven)
                return None
        if kind == "side" and not (taker or maker):
            return None
        return (f"{kind}: its account names the parent's entry as the defect, and {taker} of the parent's "
                f"{taker + maker} entry fills were takers")

    def _program_account(self, parent: Agent, child: Agent) -> str | None:
        """The research account of the child's CURRENT program, when it is an account of its PARENT's current
        program -- the one whose entries the parent trades:
        - the purpose of the child's own rewrite (the `agent.strategy` row that adopted its current code),
          when the program that rewrite replaced was the parent's current code (a mutation or copy of the
          parent, fixed in place);
        - else the reason it was born with, when it was born with new code from its parent's research
          candidate while the parent ran the program it runs now, and it runs that code still.
        None otherwise: a House mutation, a lab graduate, and a child whose rewrite fixed its OWN earlier
        program. The review of #245 (Sept 24, 2026): meriwether-h2d625d trades KXMLBTOTAL unders; its child
        meriwether-h2d625d-2 was born with a moneyline-favourites file its parent never ran and then fixed that
        file's taker entry ("the current file buys at the ask"). Read as the parent's defect, L1's first pass
        would have retired the floor's best real record (5 of 5 real settlements won) for it."""
        changes: list[tuple[int, str | None, str, str, str]] = []  # (seq, code it replaced, its code, reason, kind)
        current = None
        for entry in self.ledger.iter(kinds=("agent.born", "agent.strategy"), agent=child.id):
            code = entry.payload.get("code_sha256")
            if not code or code == current:
                continue  # the House's own row after a rewrite ("it rewrote itself", `was`) repeats the code
            changes.append((entry.seq, current, str(code), str(entry.payload.get("reason") or ""), entry.kind))
            current = code
        adopted = next((row for row in reversed(changes) if row[2] == child.code_sha256), None)
        if adopted is None:
            return None
        _, replaced, _, reason, kind = adopted
        if kind == "agent.strategy":
            if replaced != parent.code_sha256 or not reason or reason.startswith("it rewrote itself"):
                return None
            return reason
        fork = next((e for e in self.ledger.iter(kinds="agent.forked", agent=parent.id)
                     if e.payload.get("child") == child.id and e.payload.get("new_code")), None)
        if fork is None or self._code_at(parent, fork.seq) != parent.code_sha256:
            return None
        return reason

    def _taker_proven(self, agent: Agent) -> dict[str, Any] | None:
        """The agent's family's pooled TAKER record when it is proven positive, else None: read from the one source the
        real book's `real_entry_liquidity` rule (X0) reads to let the family take -- `Allocator.family_taker`, which
        the book is handed as `family_taker` -- never recomputed. None while the allocator is off, as the book reads it,
        and when the record cannot be read (the book then treats the family as unproven too)."""
        reader = getattr(getattr(self, "allocator", None), "family_taker", None)
        if reader is None:
            return None
        try:
            record = reader(agent.id)
        except Exception:  # noqa: BLE001 - `Allocator.family_taker` never raises; an unreadable record proves nothing
            return None
        return dict(record) if isinstance(record, Mapping) and record.get("positive") is True else None

    def _note_supersede_skipped(self, parent: Agent, child: Agent, kind: str, taker: Mapping[str, Any]) -> None:
        """Tell once a pair (house.json `supersede_skipped`, so a restart does not tell it again) that L1 left a parent
        in place because its family's taker record is proven: an info alert with the record, beside the alerts that
        tell L1's supersessions."""
        key = f"{parent.id}|{parent.code_sha256[:16]}|{child.id}|{child.code_sha256[:16]}"
        with self._state_lock:
            told = self._state.setdefault("supersede_skipped", {})
            if key in told:
                return
            told[key] = now_iso(self.clock)
            while len(told) > 200:
                told.pop(next(iter(told)))
        bound = taker.get("bound")
        measured = f"{int(taker.get('n') or 0)} taker settlements" + ("" if bound is None else f", bound {float(bound):+.4g}")
        self.alert("info", f"{parent.id} is not superseded by its research child {child.id}: the child's account names a {kind} "
                           f"defect of the parent's taker entry, but the family {parent.family}'s pooled taker record is proven "
                           f"positive ({measured}), which is what lets the family take on the real book: a maker fix of a "
                           "proven taker mechanism is not a defect fix (allocator.corrected_child_supersedes)",
                   parent=parent.id, child=child.id, family=parent.family, defect=kind, taker=dict(taker),
                   rule="allocator.corrected_child_supersedes")

    def _code_at(self, agent: Agent, seq: int) -> str | None:
        """The code an agent ran at a ledger position: its birth's, or its latest `agent.strategy` row's before it."""
        code = None
        for entry in self.ledger.iter(kinds=("agent.born", "agent.strategy"), agent=agent.id):
            if entry.seq > seq:
                break
            code = entry.payload.get("code_sha256") or code
        return code

    def _entry_fills(self, agent: Agent) -> tuple[int, int]:
        """(taker, maker) counts of the agent's own entry fills (buys, venue or cross) on every book."""
        taker = maker = 0
        for entry in self.ledger.iter(kinds="book.fill", agent=agent.id):
            p = entry.payload
            if p.get("side") != "buy" or p.get("source") not in ("venue", "cross"):
                continue
            taker += p.get("liquidity") == "taker"
            maker += p.get("liquidity") == "maker"
        return taker, maker

    def _supersede(self, parent: Agent, child: Agent, why: str) -> bool:
        """Supersede one parent (L1): on real money, demoted to practice through the evaluator first, as the
        allocator demotes (`Allocator._move_down`: a `demote` verdict a rung, with its band numbers); then
        retired as `superseded`, which winds its books down (a Kalshi contract is held to settlement)."""
        with self._lifecycle_lock:
            # Read outside the lock: the allocator's pass or a death may have moved either since (review of #245).
            now_parent, now_child = self.registry.get(parent.id), self.registry.get(child.id)
            if now_parent is None or not now_parent.alive or now_parent.code_sha256 != parent.code_sha256 \
                    or now_child is None or not now_child.alive or now_child.code_sha256 != child.code_sha256:
                return False
            rung = self.evaluator.rung(parent.id)
            if rung >= 2:
                band_from = "swing" if rung >= 3 else (self.allocator.tier(parent) if allocator_module.enabled() else "bunt")
                numbers = {"via": "house", "band_from": band_from, "band_to": "paper", "stake_usd": None, "reason_detail": why,
                           "superseded_by": child.id, "rule": "allocator.corrected_child_supersedes"}
                while self.evaluator.rung(parent.id) > 1:
                    self.evaluator.demote(parent.id, f"superseded: its research child {child.id} passed replay with a fix to its "
                                                     f"entry mechanism ({why})", numbers)
            self.kill(parent, "superseded", f"its research child {child.id} passed replay with a fix to its entry mechanism ({why}); "
                                            + ("it was demoted from real money first; " if rung >= 2 else "")
                                            + "the child is judged on its own evidence and enters real money by its family's state")
        self.alert("info", f"{parent.id} was superseded by its research child {child.id}"
                           + (" and left real money" if rung >= 2 else "") + f": {why}")
        return True

    def learn(self) -> int:
        """Load the teacher's merged lessons (league/playbook/*.md) into the ledger's playbook: once
        each, and again when a lesson's text changes. Until Sept 23, 2026 a corrected lesson never
        reached the ledger, and agents kept planning against thresholds it no longer stated."""
        from .commons import MAX_NOTE_CHARS

        have: dict[str, str] = {}
        for entry in self.ledger.iter(kinds="playbook.entry"):
            have[str(entry.payload.get("title"))] = str(entry.payload.get("text") or "")
        added = 0
        for path in sorted((Path(__file__).resolve().parent / "playbook").glob("*.md")):
            title = f"Lesson: {path.stem}"
            text = path.read_text(encoding="utf-8")
            if path.name != "README.md" and have.get(title) != text[:MAX_NOTE_CHARS]:
                self.commons.playbook_add(title, text, source="teacher")
                added += 1
        return added

    def niche_of(self, agent: Agent | None) -> niches_module.Niche | None:
        return self.niches.get(agent.specialty) if agent is not None and agent.specialty else None

    def members(self, niche_id: str) -> int:
        return sum(1 for a in self.registry.living() if a.specialty == niche_id)

    @staticmethod
    def _markets_and_style(needs: Mapping[str, Any]) -> tuple[str, frozenset[str], frozenset[str], str]:
        """What a program trades and what it says it is: its venue, its series and symbols (as sets), and its NEEDS
        `style` (lowercase, dashes; never cut short)."""
        style = re.sub(r"[^a-z0-9-]+", "-", str(needs.get("style") or "").lower()).strip("-")
        return (str(needs.get("venue") or "").lower(), frozenset(str(s).upper() for s in needs.get("series") or ()),
                frozenset(str(s).upper() for s in needs.get("symbols") or ()), style)

    def _program_family(self, parent: Agent, family: str, needs: Mapping[str, Any], niche: Any) -> str:
        """The family a child with NEW code is born into (Sept 24, 2026): its parent's (`family`) when its NEEDS name the
        same markets -- venue, series, symbols -- and the same style as the parent's program now (a fix of the same
        program: a maker entry, a price floor, a guard; the family record already splits maker and taker), else a family
        of its own, named from its desk and its style and rooted in the parent's family (`<desk>-<style>-<6 hex>`: the
        same research direction from one family is one family), so a different mechanism never inherits a family's
        proof. Measured on the 15:06Z snapshot: 98 children had been born into their parent's family with code other
        than the parent's program beyond PARAMS (39 of the 112 living); 71 of them (28 living) named other markets or
        another style -- meriwether-h2d625d-2 among them, a CFB and soccer moneyline-favourites file carrying the
        KXMLBTOTAL run-unders' proven family (sports-central-run-under) -- and 27 were fixes of the same program."""
        mine, theirs = self._markets_and_style(needs), self._markets_and_style(parent.needs or {})
        if mine == theirs:
            # A PROVEN family's name stays with the program that proved it (the review of #276): a parent that carries
            # the name with another program (meriwether-h2d625d-2, born into sports-central-run-under with a moneyline
            # file) passes the test above with a fix of its own file, and its forks would carry the proof on.
            founding = self._family_program(family, parent.venue) if self._family_proven(family, parent.venue) else None
            if founding is None or founding == mine:
                return family
        style = mine[3] or "program"
        desk = niche.id.split("-", 1)[-1] if niche is not None else (mine[0] or "desk")
        base = style if style.startswith(desk) else f"{desk}-{style}"
        root = hashlib.sha256(f"{parent.family}|{style}".encode("utf-8")).hexdigest()[:6]
        return f"{base[:33].rstrip('-')}-{root}"

    def _family_program(self, family: str, venue: str) -> tuple[str, frozenset[str], frozenset[str], str] | None:
        """The markets and style (`_markets_and_style`) of a family's founding program: the NEEDS its first member (the
        earliest born on `venue`, living or dead: a card, a graduate, a seed or a merged strategy -- whatever named the
        family) was born with, read from its `agent.born` row (its current NEEDS when the row carries none). None for a
        family with no member. The review of #276, Sept 24, 2026: sports-central-run-under's is meriwether-h2d625d's
        KXMLBTOTAL run-unders; meriwether-h2d625d-2, born into it later with a CFB and soccer moneyline file, is not."""
        with (getattr(self.registry, "_lock", None) or nullcontext()):
            members = [a for a in self.registry.agents.values() if a.family == family and a.venue == venue]
        if not members:
            return None
        first = min(members, key=lambda a: (a.born_at, a.id))
        born = self.ledger.get(f"born:{first.id}")
        needs = (born.payload.get("needs") if born is not None else None) or first.needs or {}
        return self._markets_and_style(needs if isinstance(needs, Mapping) else {})

    def _candidate_family(self, parent: Agent, candidate: Mapping[str, Any], niche: Any) -> str:
        """The family a research candidate of `parent` will be born into (`_program_family`), read from the NEEDS it was
        replayed on: what it asks for a seat as, and what a retained one waits as (a proven family's first)."""
        code, needs = candidate.get("code"), candidate.get("needs")
        if not code or not isinstance(needs, Mapping) or code_sha(str(code)) == parent.code_sha256:
            return parent.family
        return self._program_family(parent, parent.family, needs, niche)

    def spawn(self, name: str, family: str, code: str, *, parent: str | None = None, reason: str = "",
              # `name` is the line the agent is numbered from. Empty means "the desk its NEEDS put
              # it on": that is how the architect's strategies join a desk rather than arriving
              # with a slug of their own.
              params: Mapping[str, Any] | None = None, endowment: Any | None = None, keep_probe_awake: bool = False,
              specialty: str | None = None, founder: str | None = None, described: Any | None = None,
              # A research fork's or a retained candidate's NEW code: born into its own family when its NEEDS name other
              # markets or another style than this agent's program (`_program_family`).
              new_code_of: Agent | None = None) -> Agent:
        # A strategy's NEEDS are read by running its module body, so that happens in a box too: one
        # sealed probe box the House keeps for the purpose, never the House's own process.
        # `described`: that probe's run of this same code, made by a caller that must not call Sail
        # here (a research admission, under the lifecycle lock: `_admit_researched`).
        if described is None:
            described = self.sandbox.needs(PROBE_BOX, code, keep_awake=keep_probe_awake) if keep_probe_awake else self.sandbox.needs(PROBE_BOX, code)
        info = described.result
        if not info.get("ok"):
            if keep_probe_awake:
                self.sandbox.rest(PROBE_BOX)
            raise ValueError(f"{name}: {info.get('error')}")
        niche_of(info["needs"])
        needs = dict(info["needs"])
        # A child is of its parent's specialty; a strategy that arrives with none (the architect's)
        # joins the open specialty its NEEDS sit in, or is not born.
        inherited = self.registry.get(parent).specialty if parent and self.registry.get(parent) else None
        niche = self.niches.get(specialty or inherited or "") or (None if (specialty or inherited) else niches_module.match(needs, self.niches))
        try:
            if niche is None and (specialty or parent is None) and self.settings.specialists:
                raise ValueError("its NEEDS sit in no open specialty of league/niches.json")
            if niche is not None:
                if niche.dormant:
                    raise ValueError(f"the {niche.id} specialty is not open yet: {niche.dormant_reason}")
                needs = niches_module.constrain(needs, niche)
        except ValueError as exc:
            if keep_probe_awake:
                self.sandbox.rest(PROBE_BOX)
            raise ValueError(f"{name}: {exc}") from exc
        if new_code_of is not None and code_sha(code) != new_code_of.code_sha256:
            own = self._program_family(new_code_of, family, needs, niche)
            if own != family:
                reason = (f"{reason} [born into its own family {own}, not {family}: its NEEDS name other markets or another "
                          f"style than {new_code_of.id}'s program]").strip()
                family = own
        agent = self.registry.born(
            name=name or (niche.desk if niche else ""), family=family, code=code, needs=needs, params={**info.get("params", {}), **dict(params or {})},
            parent=parent, reason=reason, specialty=niche.id if niche else None, founder=founder,
        )
        if niche is not None and not self._replayable(niche, needs):
            # The House cannot replay this specialty here (no recorded option chains): paper is its replay.
            self.evaluator.seat(agent.id, 1, f"paper is the {niche.id} specialty's replay")
            self._state["tried"][agent.id] = agent.code_sha256
        if parent is None or endowment is not None:
            # A seed, or a newcomer the House stakes itself. (A fork is endowed by its parent.)
            self.economy.grant(agent.id, self.game["economy"]["endowment_usd"] if endowment is None else endowment, "endowment", id=f"endow:{agent.id}")
        self._charge_box(agent.id, described, note="reading its strategy's NEEDS")
        return agent

    def _charge_box(self, agent: str, run: Any, *, note: str) -> None:
        cost = self.economy.box_cost(run.seconds, created=run.created)
        self.economy.charge(agent, cost, "sandbox seconds", detail={"seconds": round(run.seconds, 2), "for": note})

    # ------------------------------------------------------------------ books
    def _event_capital_budget(self, venue: str) -> Decimal | None:
        """Read an existing explicit venue envelope; never activate or enlarge one."""
        authorization = self.campaigns.live_authorization() if self.campaigns else None
        limits = (authorization or {}).get('policy', {}).get('venue_capital_usd') or {}
        return Decimal(limits[venue]) if venue in limits else None

    def book_of(self, agent: Agent) -> Book | None:
        rung = self.evaluator.rung(agent.id)
        if rung >= 2 and REAL_BOOK[agent.venue] in self.books:
            return self.books[REAL_BOOK[agent.venue]]
        return self.books.get(PRACTICE_BOOK[agent.venue])

    def _limits(self, rung: int, agent: Agent | None = None, staked: Decimal | None = None) -> Limits:
        """The seat's own caps, which `seat` writes into the book and the book enforces as "this
        rung's". Not always what an entry can have: on real-money Alpaca the book also holds it to
        half the account's equity, and an agent is SHOWN the smaller of the two (`_real_limits`)."""
        row = CONSTITUTION["rungs"][str(min(max(rung, 1), 2))]
        position, order = Decimal(row["max_position_usd"]), Decimal(row["max_order_usd"])
        allocated = rung >= 2 and agent is not None and allocator_module.enabled()
        if allocated:
            # Bands of capital: a real position is `position_share` of the allocator's stake
            # (`position_share_event` on Kalshi since Sept 24, 2026), never under the venue's minimum
            # order, every order within the gateway's cap.
            position, order = self.allocator.limits(agent, staked if staked is not None else Decimal(0))
        elif rung >= 3 and staked is not None:
            position, order = capital.scaled_limits(staked)  # rung 3's limits follow its stake
        niche = self.niche_of(agent)
        classes = Limits.__dataclass_fields__["asset_classes"].default
        if niche is not None and niche.asset_class == "option":
            classes = ("option",)
            if rung == 2 and not allocated:  # one contract cannot be cut smaller: the micro rung's option cap
                position = order = Decimal(row["option_max_position_usd"])
            elif allocated:
                position = order = max(position, Decimal(row["option_max_position_usd"]))
        return Limits(position, order, asset_classes=classes, max_hours_to_resolve=self.horizon_hours(agent))

    def _real_limits(self, agent: Agent, book: Book, limits: Limits) -> tuple[Decimal, Decimal]:
        """(max position, max order) in dollars that a fresh entry can actually have on this book now:
        what an agent is shown (`snapshot`), what its option chain is filtered by, and what the House
        trims a real buy to (`_fit_real_entry`). It changes nothing the book enforces.

        On a real-money Alpaca book the seat's caps (`_limits`) are not the only rule. The book's risk
        rules also hold a position, valued at the ask, and an order to half the account's CURRENT
        equity (`book.DEFAULT_RULES` max_position_pct and max_order_notional_pct). Measured Sept 23,
        2026: haghani-37, a $25 crypto bunt shown $12.50, was refused 3 times once its equity fell to
        $24.89-24.96; and an options bunt is staked $40 and shown $40, while the book takes $20 a
        contract. Here it is the smaller of the two, a cent under the equity line, so an order sized
        to it is under the line rather than on it. Every other book: the seat's caps as they are."""
        position, order = limits.max_position_usd, limits.max_order_usd
        if not book.real_money or family_of(book.broker.venue) != "alpaca":
            return position, order
        equity = book.equity(agent.id)

        def line(rule: str) -> Decimal:
            return max((equity * money(str(book.rules[rule])) - CENT).quantize(CENT, rounding=ROUND_DOWN), ZERO)

        return min(position, line("max_position_pct")), min(order, line("max_order_notional_pct"))

    def _fit_real_entry(self, agent: Agent, book: Book, instrument: Instrument, quantity: Decimal, limit: Decimal | None,
                        step: Decimal, minimum: Decimal | None, cancelling: Collection[str] = ()) -> tuple[Decimal, str] | None:
        """A real-money Alpaca buy trimmed to what the book will take: (quantity, why) when less than
        asked fits, None when the order fits as it is or cannot be made to (the book then refuses it
        and says why). Only ever smaller, never under the venue's minimum, and never for a sell.

        The book values the position a buy leaves at the ASK (`ltcm.risk.rule_position_limit`), with
        what the agent holds and bids already, while an order is sized at its own limit price. So a
        bid under the ask sized to its limit to the dollar is over the line at the ask: 7 of
        haghani-37's 10 real refusals by Sept 23, 2026, all at equity at or above its stake.

        `cancelling` is the order ids the same decision cancels. `wake` sizes before it applies the
        decision's cancels, and the book judges the new bid after them, so a bid being cancelled is
        not counted as one the agent still has. Otherwise a strategy that cancels its resting bid and
        bids again each wake had a room of a sliver under the $10 minimum, its replacement was sent
        untrimmed, and the book refused it at the ask once the old bid was gone: no order at all. If a
        cancel does not go through, the old bid stays and the book, still the judge, refuses the new
        one as it would have."""
        limits = book.limits.get(agent.id)
        if limits is None:
            return None
        try:
            ask = book.broker.quote(instrument).ask
        except Exception:  # noqa: BLE001 - no quote, no trim: the book judges the order as asked
            return None
        if ask is None or ask <= 0:
            return None
        position_cap, order_cap = self._real_limits(agent, book, limits)
        unit = ask * instrument.multiplier
        held = book.account(agent.id).holdings.get(instrument.key)
        committed = held.quantity * unit if held else ZERO
        for working in book.open_orders(agent.id):
            if working.side == "buy" and working.instrument.key == instrument.key and working.order_id not in cancelling:
                left = sum((share.quantity - share.filled for share in working.shares if share.agent == agent.id), ZERO)
                committed += left * (working.limit_price or ask) * instrument.multiplier
        paid = min(ask, limit) if limit is not None and limit > 0 else ask  # the book's order notional
        room = min((position_cap - committed) / unit, order_cap / (paid * instrument.multiplier))
        fits = (room / step).to_integral_value(rounding=ROUND_DOWN) * step
        if fits <= 0 or fits >= quantity:
            return None
        if minimum is not None and fits * (limit or ask) * instrument.multiplier < minimum:
            return None
        return fits, (f"the book values the position at the ask of {ask} and holds it to ${position_cap}, "
                      f"an order to ${order_cap} (half this account's ${book.equity(agent.id):.2f} equity, less a cent, "
                      f"or the seat's limits if smaller)")

    def horizon_hours(self, agent: Agent | None) -> float | None:
        """The horizon rule for this agent's entries: Kalshi only (hours by its block length)."""
        rules = self.game.get("horizon") or {}
        if agent is None or agent.venue != "kalshi" or not rules:
            return None
        return float(rules["kalshi_day_max_hours" if agent.horizon == "day" else "kalshi_hour_max_hours"])

    def seat(self, agent: Agent) -> None:
        """Give an agent its limits and its stake on the book of its rung (once per book)."""
        rung = self.evaluator.rung(agent.id)
        book = self.book_of(agent)
        if rung < 1 or book is None:
            return
        account = book.account(agent.id)
        book.limits[agent.id] = self._limits(rung if book.real_money else 1, agent, account.staked)
        # A new seat, or a return to a book the House had closed the agent's account on (a
        # demotion after a loss leaves `staked` above zero and cash at zero: it is staked afresh).
        if not account.funded or (account.swept and not account.holdings):
            stake = CONSTITUTION["rungs"]["2" if book.real_money else "1"]["stake_usd"]
            if book.real_money and allocator_module.enabled():
                stake = self.allocator.seat_stake(agent)  # a bunt's stake, or a swing's by its evidence
                if self.allocator.headroom(agent.venue, exclude=agent.id) < stake:
                    # The allocator is the only place a real stake is decided: no envelope, no stake.
                    self.alert("warning", f"{agent.id} was not staked on {book.name}: the {agent.venue} envelope has no room for ${stake}")
                    return
            try:
                book.stake(agent.id, stake, note=f"rung {rung} stake")
            except BookError as exc:  # a real book not reconciled yet, or out of real cash: try again next wake
                self.alert("warning", f"{agent.id} could not be staked on {book.name}: {exc}")

    # ------------------------------------------------------------------- data
    def _cached(self, key: str, ttl: float, build: Callable[[], Any], *, record: bool = True) -> Any:
        """`build()`, shared for `ttl` seconds, and kept in the market recordings. `record=False` for
        what is already stored with its receive time elsewhere (the feed store): recorded twice, a
        scoreboard every half minute would crowd market snapshots out of the recorder's 256 MB.

        What a fetch that began before the regular session opened read is never served after the
        open: a desk woken at the open (`_next_wake`) must see the session, not the quotes and the
        option chain an agent woken a few seconds earlier cached from a shut market."""
        hit = self._data_cache.get(key)
        if hit and self.clock() - hit[0] < ttl and not self._opened_since(hit[2] if len(hit) > 2 else hit[0]):
            return hit[1]
        started = self.clock()
        value = build()
        if record:
            try:
                self.recorder.record(key, value, started=started)
            except Exception as exc:  # recording failure must not prevent position management
                self.alert("warning", f"market recording failed ({type(exc).__name__})")
        self._data_cache[key] = (self.clock(), value, started)
        return value

    def _session_open(self, moment: float) -> float | None:
        """When the regular US equity session opened (or opens) on `moment`'s UTC date; None on a
        closed day. The open is 13:30 or 14:30 UTC, so the UTC date is New York's date there."""
        day = time.strftime("%Y-%m-%d", time.gmtime(moment))
        if day not in self._opens:
            try:
                session = us_equity_session(day)
                opened = to_datetime(session.open_at).timestamp() if session is not None else None
            except Exception:  # noqa: BLE001 - a date outside the computed calendar has no open we know of
                opened = None
            if len(self._opens) > 64:
                self._opens.clear()
            self._opens[day] = opened
        return self._opens[day]

    def _opened_since(self, then: float) -> bool:
        """Whether the regular session opened after `then` and by now."""
        now = self.clock()
        opened = self._session_open(now)
        return opened is not None and then < opened <= now

    def snapshot(self, agent: Agent, book: Book) -> dict[str, Any]:
        """Everything a strategy sees, as plain data (floats: the box converts nothing back)."""
        from .auditor import order_outcomes
        needs = agent.needs
        account = book.account(agent.id)
        limits = book.limits.get(agent.id) or self._limits(1, agent)
        # What an entry can actually have on this book now (`_real_limits`), not only the seat's caps.
        max_position, max_order = self._real_limits(agent, book, limits)
        # `now` is stamped at the end, once the market data is in hand (`_stamped`).
        ctx: dict[str, Any] = {
            "venue": agent.venue,
            "rung": self.evaluator.rung(agent.id),
            "params": agent.params,
            "memory": self._state["memory"].get(agent.id) or {},
            "cash": float(account.cash),
            "equity": float(book.equity(agent.id)),
            "limits": {"max_position_usd": float(max_position), "max_order_usd": float(max_order)},
            "fees": {"crypto_taker": 0.0025, "crypto_maker": 0.0015, "kalshi_taker_rate": 0.07},
            "positions": [],
            "open_orders": [],
            "recent_order_outcomes": order_outcomes(self.ledger, agent.id, book.name),
            # What the venue asks of an order, by tradeable symbol, where it is known (`_venue_rules`).
            # Empty for a Kalshi or options agent: a market's or a contract's grid is not known up front.
            "venue_rules": {},
        }
        for holding in account.holdings.values():
            inst = holding.instrument
            row = {
                "quantity": float(holding.quantity), "average_cost": float(holding.average_cost),
                "mark": float(book.marks.get(inst.key) or holding.average_cost),
                "opened_at": holding.opened_at, "reason": holding.reason,
            }
            if inst.asset_class == "event":
                row.update(market=inst.market_id or inst.symbol, leg=inst.right or "yes")
            elif inst.asset_class == "option":
                row.update(occ=occ_symbol(inst), symbol=inst.symbol, expiry=inst.expiry, strike=float(inst.strike), right=inst.right)
            else:
                row["symbol"] = inst.market_id or inst.symbol
            ctx["positions"].append(row)
        for working in book.open_orders(agent.id):
            inst = working.instrument
            row = {
                "order_id": working.order_id, "side": working.side, "quantity": float(working.quantity),
                "limit_price": None if working.limit_price is None else float(working.limit_price),
                "filled": float(working.filled), "submitted_at": working.submitted_at,
            }
            if inst.asset_class == "event":
                row.update(market=inst.market_id or inst.symbol, leg=inst.right or "yes")
            elif inst.asset_class == "option":
                row.update(occ=occ_symbol(inst), symbol=inst.symbol)
            else:
                row["symbol"] = inst.market_id or inst.symbol
            ctx["open_orders"].append(row)
        watched = needs.get("observe") if isinstance(needs.get("observe"), dict) else {}
        if watched:
            ctx["observed"] = self._observed(watched, needs)
        wanted = self._feeds_wanted(needs)
        if wanted and self.feeds is not None:
            # The recorded live feeds (`league/feeds.py`): each declared key's latest row received by
            # now, the rows a replay tape carries. A key with nothing recorded is absent -- unavailable,
            # never zero -- and a store that cannot be read costs the block, not the wake.
            try:
                ctx["feeds"] = self._cached("feeds:" + json.dumps(wanted, sort_keys=True), 30,
                                            lambda: self.feeds.latest(wanted, self.clock()), record=False)
            except Exception as exc:  # noqa: BLE001
                self.alert("warning", f"{agent.id}: the feeds could not be read this wake ({type(exc).__name__}: {str(exc)[:160]})")
        if agent.venue == "alpaca":
            symbols = [str(s) for s in (needs.get("symbols") or [])][:12]
            bars = dict(needs.get("bars") or {})
            timeframe = str(bars.get("timeframe") or "5Min")
            limit = max(1, min(int(bars.get("limit") or 120), 500))
            key = f"bars:{','.join(symbols)}:{timeframe}:{limit}"
            ctx["bars"] = self._cached(key, 50, lambda: self.alpaca_data.bars(symbols, timeframe, limit=limit))
            ctx["quotes"] = self._cached(f"quotes:{','.join(symbols)}", 20, lambda: self.alpaca_data.quotes(symbols))
            if needs.get("options_features") and self.options_history is not None:
                # The same stored rows a replay tape carries, the latest already available now.
                ctx["options_features"] = self._cached(f"options-features:{','.join(symbols)}", 300,
                                                       lambda: self.options_history.features_at(symbols, self.clock()))
            niche = self.niche_of(agent)
            if niche is not None and niche.asset_class == "option":
                days = max(2, min(int(needs.get("max_days_to_expiry") or 21), 45))
                # A contract is 100 shares: what one contract may cost a share, by the same number the
                # agent is shown, so the chain holds nothing the book would refuse on size (an options
                # bunt staked $40 is held to $20 a contract by half its equity).
                afford = float(min(max_order, max_position)) / 100.0
                ctx["chain"] = self._cached(f"chain:{','.join(symbols)}:{days}:{afford}", 120, lambda: self._chain(symbols[:8], days, afford, ctx["quotes"]))
            else:
                ctx["venue_rules"] = self._venue_rules(book, symbols, ctx["quotes"])
        else:
            series = [str(s) for s in (needs.get("series") or [])][:12]
            hours = float(needs.get("max_hours_to_close") or 24)
            age = 300.0 if agent.horizon == "day" else 60.0  # how old a shared listing may be: a daily strategy is not racing anyone
            ctx["markets"] = self._cached(f"markets:{','.join(series)}:{hours}", 50, lambda: self._markets(series, hours, age))
            niche = self.niche_of(agent)
            if not ctx["markets"] and niche is not None and niche.live:
                # Its own series are dark (a season ended, a quiet night): the busiest live series of its specialty.
                busiest = [x for x in niche.live if x not in series][: niches_module.MAX_UNIVERSE]
                if busiest:
                    ctx["markets"] = self._cached(f"markets:{','.join(busiest)}:{hours}", 120, lambda: self._markets(busiest, hours, age))
                    ctx["note"] = "None of the series your strategy names has a market open inside your window, so these are the busiest live series of your specialty."
        if agent.venue == 'kalshi':
            ctx['event_risk'] = book.event_risk(agent.id, (row['market'] for row in ctx['markets']))
            caps = [value for key, value in ctx['event_risk'].items() if key.endswith('_cap_usd') and value is not None]
            if caps:
                # These are upper bounds on a fresh entry. Per-market remaining capacity
                # accounts for existing holdings and other agents' pending orders below them.
                for key in ('max_position_usd', 'max_order_usd'):
                    ctx['limits'][key] = min(ctx['limits'][key], *caps)
        return self._stamped(ctx)

    def _stamped(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """The snapshot with its `now`, read AFTER the bars, the quotes, the option chain and the
        listings were fetched, so no quote in it is later than its `now` because the fetch took
        time. Measured Sept 23, 2026: stamped before an options desk's chain was fetched, 170-280 of
        about 300 contracts a snapshot carried quotes later than `now`, and a strategy that rejects a
        quote from the future could not enter. No quote's own timestamp is ever changed. (The rest
        was the box's clock, 4.3-4.6 s slow: that is the box's NTP, not something to paper over.)"""
        return {"now": now_iso(self.clock), **ctx}

    # ------------------------------------------------------------------- wake
    def due(self) -> list[Agent]:
        now = self.clock()
        out = [a for a in self.registry.living() if float(self._state["next_wake"].get(a.id) or 0) <= now]
        # Serve the oldest deadline first. Birth order alone can starve the tail forever when
        # an earlier cohort becomes due again before the bounded wake batch reaches it.
        # Python's stable sort retains the registry's birth/id order for equal deadlines.
        out.sort(key=lambda a: float(self._state["next_wake"].get(a.id) or 0))
        # A House that has just started has every cache cold: each wake re-reads its venue listings.
        # Measured Sept 19, 2026: sixteen cold wakes in one tick took over four minutes, and the
        # watchdog rightly rolled the release back as a House whose ticks do not finish. For its
        # first five minutes a House wakes a few agents a tick; the rest are a minute late.
        cold = now - self._born_at < 300
        cap = min(self.settings.max_wakes_per_tick, self.settings.cold_wakes_per_tick) if cold else self.settings.max_wakes_per_tick
        if len(out) <= cap:
            return out
        return self._every_desk_first(out, cap)

    def _every_desk_first(self, due: list[Agent], cap: int) -> list[Agent]:
        """The `cap` agents woken this tick when more are due than fit: one from each desk in turn,
        the desk that has gone longest without a wake first (`desk_woke`, stamped in `wake`), and
        within a desk the oldest deadline first, as `due` sorted them.

        A backlog is what a resumed House has: every agent is due at once after a maintenance pause
        lifts or a restart, and served in deadline order alone the first ticks all went to whichever
        desks happened to be oldest. Measured Sept 22, 2026, after the 15:28Z resume: the first
        seventeen minutes reached five of the twelve desks (scholes first, then krasker, meriwether,
        hawkins, mullins) while the 15-minute crypto desks, live around the clock, waited. The desk
        stamps live in house.json, so the turn carries across ticks and restarts; with no backlog the
        order does not matter and `due` returns everyone."""
        woke = self._state.get("desk_woke") or {}
        queues: dict[str, list[Agent]] = {}
        for agent in due:
            queues.setdefault(getattr(agent, "specialty", None) or agent.id, []).append(agent)  # an agent of no desk is its own
        order = sorted(queues, key=lambda desk: (float(woke.get(desk) or 0), float(self._state["next_wake"].get(queues[desk][0].id) or 0)))
        picked: list[Agent] = []
        while len(picked) < cap:
            before = len(picked)
            for desk in order:
                if queues[desk]:
                    picked.append(queues[desk].pop(0))
                    if len(picked) >= cap:
                        break
            if len(picked) == before:
                break
        return picked

    def _next_wake(self, agent: Agent, now: float) -> float:
        """When an agent woken at `now` is due again: `wake_minutes` on, or a few seconds after the
        regular session's open (`OPEN_WAKE_SECONDS`) for a desk that keeps the session (stocks,
        options, an open desk naming a stock) when its next wake would otherwise land later. The
        wake is moved, not added: the cadence runs on from it (so a cadence of a day or more wakes at
        each open), and every other wake, and every coin or Kalshi desk's, is where it was."""
        due = now + agent.wake_minutes * 60
        niche = self.niche_of(agent)
        if niche is None or not niche.keeps_hours(agent.needs):
            return due
        try:
            session = next_session(now)  # the first session opening strictly after now
            at_open = to_datetime(session.open_at).timestamp() + OPEN_WAKE_SECONDS if session is not None else None
        except Exception:  # noqa: BLE001 - no calendar, no move: the cadence stands
            return due
        return at_open if at_open is not None and at_open < due else due

    def _shut_session(self, agent: Agent) -> str:
        """Why this agent's wake is not run now, or "": everything it may trade keeps the regular US
        session (a stock or option desk; an open desk naming no coin) and the session is shut.

        The wake skip (Sept 24, 2026, the close-the-gaps run). Outside the session nothing such an
        agent decides can trade: an entry waits for the open, a market exit is refused by the book
        ("market orders outside regular hours are not permitted"), and the strategy reads a shut
        market's stale quotes. Measured on the T0 snapshot, the 48 hours to 01:41Z Sept 24: 2,891 of
        9,884 wakes (29%) were stock or option agents outside the session, billed 9,424 box seconds,
        and sent 79 intents, 75 of them refused as market orders outside regular hours (scholes-
        h7dd043-2 and scholes-25 exiting, 10-14 an hour all night). Such a wake is not run: no
        snapshot, no box, no order, no `agent.woke` row. Its cadence and its idle bookkeeping stand
        (`wake`), and `_next_wake` already wakes the desk a few seconds after the bell, where a held
        position's exit goes at once. A House wind-down's held sells wait for the open as before
        (`_release_wind_downs`). An open desk naming a coin is woken all night for the coin; its stock
        or option entries wait instead (`_intents`)."""
        niche = self.niche_of(agent)
        if niche is None or not niche.keeps_hours(agent.needs):
            return ""
        if niche.open and any(not niche.keeps_hours({"symbols": [symbol]}) for symbol in agent.needs.get("symbols") or []):
            return ""  # it names a coin, which trades all night
        try:
            if market_open_at(now_iso(self.clock)):
                return ""
        except Exception:  # noqa: BLE001 - a moment outside the computed calendar: wake as before
            return ""
        return ("the regular session is shut: a stock or option desk is not woken until the open, "
                "a few seconds after the bell (nothing it sends before then can trade)")

    def _count_skipped_wake(self, agent: Agent) -> None:
        """health.json `wakes_skipped`: how many wakes the skip saved since it was first counted, by desk."""
        with self._state_lock:
            skips = self._state.setdefault("wakes_skipped", {"since": now_iso(self.clock), "count": 0, "by_desk": {}})
            skips["count"] = int(skips.get("count") or 0) + 1
            desk = agent.specialty or agent.niche
            skips.setdefault("by_desk", {})[desk] = int(skips["by_desk"].get(desk) or 0) + 1
            skips["last_at"] = now_iso(self.clock)

    def _generation(self, agent_id: str) -> tuple[str, str, int, int] | None:
        """Identity of the strategy and rung stay, read while holding the lifecycle lock. An agent's
        own pause or resume of its entries (X1) restates its strategy and does not move it
        (`allocator.adopted_strategy`): an audit, a candidate's admission, a promotion or a death
        keyed to the generation stands. A buy decided before a pause is held at `_submit_wakes`."""
        agent = self.registry.get(agent_id)
        if agent is None or not agent.alive:
            return None
        strategy = json.dumps([agent.params, agent.needs], sort_keys=True, separators=(",", ":"))
        last_strategy = allocator_module.adopted_strategy(self.ledger, agent_id)
        return agent.code_sha256, strategy, last_strategy.seq if last_strategy else 0, self.evaluator._rung_entered(agent_id)

    def wake(self, agent: Agent) -> dict[str, Any]:
        """One wake of one agent. Returns what happened, for the caller and the tests."""
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None:
                return {"agent": agent.id, "skipped": "retired"}
            agent = deepcopy(self.registry.get(agent.id))
            next_wake = self._next_wake(agent, self.clock())
            # Under the state lock (the #203 review, Sept 23, 2026): `_save_state` serializes the
            # state under it from the audit thread, and a key added here while it iterates would
            # raise "dictionary changed size during iteration" (the desk stamps are new keys on the
            # first round after a deploy).
            with self._state_lock:
                self._state["next_wake"][agent.id] = next_wake
                if agent.specialty:
                    self._state.setdefault("desk_woke", {})[agent.specialty] = self.clock()  # the desk's turn was served (`_every_desk_first`)
            rung = self.evaluator.rung(agent.id)
            if self._state["tried"].get(agent.id) != agent.code_sha256 and not self.paused():
                self._background(f"replay:{agent.id}", self._replay_own, agent)
            if rung == 0:
                return {"agent": agent.id, "skipped": "in replay"}
            book = self.book_of(agent)
            if book is None:
                return {"agent": agent.id, "skipped": "no book for its venue"}
            self.seat(agent)
            if book.account(agent.id).cash <= 0 and not book.account(agent.id).holdings:
                return {"agent": agent.id, "skipped": "no stake on its book yet"}
            shut = self._shut_session(agent)
            if shut:
                # The wake skip: no snapshot, no box, no order. Only the bookkeeping a shut wake always
                # did, so research is paced exactly as before (`idle_reason`'s bench time).
                self._note_wake(agent, acted=bool(book.account(agent.id).holdings or book.open_orders(agent.id)), offered=0)
                self._count_skipped_wake(agent)
                return {"agent": agent.id, "skipped": shut}
        try:
            ctx = self.snapshot(agent, book)
        except Exception as exc:  # noqa: BLE001 - a data outage skips a wake, it does not stop the floor
            self.alert("warning", f"{agent.id}: no market data this wake ({type(exc).__name__}: {str(exc)[:200]})")
            return {"agent": agent.id, "skipped": "no data"}
        try:
            run = self.sandbox.decide(agent.id, agent.code, ctx)
        except SandboxBusy as exc:
            # Its research is replaying a candidate in its box (or the box is being put to sleep):
            # the tick does not wait for that. Due again at once, so it is woken on the next tick.
            with self._state_lock:
                self._state["next_wake"][agent.id] = self.clock()
            self._defer("wakes", f"{agent.id}: {str(exc)[:200]}")
            return {"agent": agent.id, "skipped": "its box is in use by background work; woken on the next tick"}
        except SandboxError as exc:
            self.alert("warning", f"{agent.id}: its box did not run ({str(exc)[:200]})", **environment("sail", exc))
            return {"agent": agent.id, "skipped": "sandbox"}
        self._charge_box(agent.id, run, note="a decision")
        result = run.result
        # Sizing may need a venue quote, so do it before the short result commit.
        adjusted: list[str] = []
        # The decision's cancels are applied below, after sizing, but the book judges its new orders
        # after them: the real-money trim must not count a bid this decision withdraws (`_fit_real_entry`).
        cancelling = frozenset(c for c in (result.get("cancels") or ()) if isinstance(c, str)) if result.get("ok") else frozenset()
        asked = list(result.get("intents") or []) if result.get("ok") else []
        # X1 (Sept 24, 2026): an agent that paused its entries (`pause_entries`) has every buy held here,
        # counted on the wake and never refused (a refusal row would buy it a research pass each wake);
        # its sells go on. A pause made after this read holds the buys at the batch (`_submit_wakes`).
        paused = self.registry.entries_paused(agent.id)
        held = 0
        if paused:
            kept = [row for row in asked if not (isinstance(row, Mapping) and str(row.get("side") or "").lower() == "buy")]
            held, asked = len(asked) - len(kept), kept
        intents, dropped = (self._intents(agent, book, asked, adjusted=adjusted, cancelling=cancelling)
                            if result.get("ok") else ([], []))
        offered = self._offered(agent, ctx)
        with self._lifecycle_lock:
            if self._generation(agent.id) != generation:
                return {"agent": agent.id, "skipped": "strategy or rung changed during decision"}
            if not result.get("ok"):
                self.ledger.append("agent.woke", {"ok": False, "error": str(result.get("error"))[:400], "book": book.name}, agent=agent.id)
                return {"agent": agent.id, "error": result.get("error")}
            self._state["memory"][agent.id] = result.get("memory") or {}
            thought = str(result.get("thought") or "").strip()
            if thought:
                self.ledger.append("agent.thought", {"text": thought, "phase": "decide", "book": book.name}, agent=agent.id)
            cancelled = [book.cancel(agent.id, order_id).status for order_id in result.get("cancels") or []]
            if paused:
                cancelled += self._cancel_paused_entries(agent, book)
            # Held buys are not activity (review of #249, P3): a paused agent that holds nothing and is shown
            # live markets is barren, for the stuck rule and research's idle cadence alike (`_note_wake`).
            idle = self._note_wake(agent, acted=bool(intents or cancelled or ctx["positions"] or ctx["open_orders"]), offered=offered)
            self.ledger.append(
                "agent.woke",
                {"ok": True, "book": book.name, "intents": len(intents), "dropped": dropped, "cancels": len(cancelled), "seconds": result.get("seconds"),
                 "offered": offered, **({"barren": idle["barren"]} if idle["barren"] else {}), **({"shut": idle["shut"]} if idle["shut"] else {}),
                 **({"adjusted": adjusted[:16]} if adjusted else {}), **({"held": held} if held else {})},
                agent=agent.id,
            )
        return {"agent": agent.id, "book": book.name, "intents": intents, "dropped": dropped, "offered": offered,
                "_generation": generation}

    def _cancel_paused_entries(self, agent: Agent, book: Book) -> list[str]:
        """Cancel a paused agent's resting buys (X1): a bid left resting would fill after the agent
        asked for no more entries. Only orders that are its alone: a share of another agent's order is
        that agent's to manage. Exits are never touched. Returns the cancels' statuses. The order's
        cancelled row says whose pause it is: the House's drain hold (`DRAIN_SESSION`) is not the
        agent's own, and it ends when the drain does, not when the agent resumes."""
        paused = self.registry.entries_paused(agent.id) or {}
        why = (DRAIN_HOLD_WHY if paused.get("session") == self.DRAIN_SESSION
               else "its own pause_entries: its entries are held until it resumes them")
        out = []
        for working in book.open_orders(agent.id):
            if working.side == "buy" and all(share.agent == agent.id for share in working.shares):
                out.append(book.cancel(agent.id, working.order_id, why=why).status)
        return out

    #: The House's own entry controls (the R5 drain hold) are recorded under this research session.
    DRAIN_SESSION = "house:drain"

    def _hold_draining_probes(self, moved: Mapping[str, Any] | None) -> None:
        """R5's drain, completed (Sept 24, 2026). A probe on a losing family goes back to practice once it is flat
        (`allocator.family_probe`: an Alpaca probe holding a coin, a stock or an option is never sold for it), and until
        then it was lent nothing more -- but it could still buy: krasker-14, an $80 options probe on options-pullback (19
        active blocks, -0.383), bought a second real contract ($15) at 18:52:30Z, nine minutes into Deploy D, while it
        waited to be flat. A probe the allocator reports waiting (`probes_waiting_flat`, every pass) now has its entries
        held the way an agent holds its own (X1 `pause_entries`: buys held at the wake, its resting buys cancelled, every
        sell goes on) by a House row under `DRAIN_SESSION`, so it drains; the hold is released by a House row once the pass
        has ended its drain (`_drain_ended`: it went back to practice, died, or its family's record turned). An agent that
        had paused itself is left as it is, and a research request to resume is refused while the hold stands
        (`_control_refusal`). Kept in house.json `drain_holds` (agent -> since) across restarts. `moved` is None while the
        allocator is off: nothing drains a probe then, and every hold is released.

        The adversarial review of the hold (Sept 24, 2026), each with a test in `league/tests/test_drain_hold.py`:
        - A pass that cannot read the gate (a failed fold, forward or tape read), a family's record or a probe's own
          evidence lists no probe waiting, as the gate fails closed; read as "no longer waiting", the hold was released and
          the losing family's probe could buy on real money until the next readable pass held it again. Only a pass that
          ended the drain releases it now.
        - The ledger, not house.json, says which pauses are the House's (the row's session): house.json is saved at the
          end of the tick, many steps after the pass, so a restart in between -- or a pass that stopped at one probe's row
          -- left a House row with no `drain_holds` entry, read ever after as the probe's own pause and never released.
        - The release writes a row only over the House's own pause: a pause research makes while the House holds is the
          agent's own (`_apply_controls` takes the hold over), and outlasts the drain.
        - A probe that paused itself before it waited is held by its own pause (no House row) and may not lift it while
          it waits: it could, and its buys went through until the next pass.
        - The rows are written under the lifecycle lock, as research writes its controls (`_apply_controls`, on its own
          thread): a House row restates the strategy it read, and landing on an edit made meanwhile it would undo it.
        - One probe whose row cannot be written is told and tried again at the next pass; the others are held."""
        off = moved is None or moved.get("enabled") is False
        waiting = set() if off else {str(a) for a in (moved.get("probes_waiting_flat") or ())}
        with self._lifecycle_lock:
            with self._state_lock:
                kept = dict(self._state.get("drain_holds") or {})
            holds = {**{agent_id: str(paused.get("since") or now_iso(self.clock)) for agent_id, paused in self._drain_rows().items()},
                     **kept}
            for agent_id in sorted(waiting):
                agent = self.registry.get(agent_id)
                if agent is None or not agent.alive:
                    continue
                if self.registry.entries_paused(agent_id):
                    # Held already: by the House's row, or by its own pause, which the House leaves as it is and which it
                    # may not lift while it waits (`_control_refusal`).
                    holds.setdefault(agent_id, now_iso(self.clock))
                    continue
                try:
                    self._house_control(agent, "pause_entries",
                                        f"the House holds this probe's entries while it goes back to practice: its family "
                                        f"{agent.family}'s pooled forward record is losing (allocator.family_probe), so it only "
                                        "exits until it is flat")
                except Exception as exc:  # noqa: BLE001 - the others are held; the next pass tries again
                    self.alert("warning", f"{agent_id}: the House could not hold its entries at the drain ({type(exc).__name__}: "
                                          f"{str(exc)[:160]}); the next pass tries again")
                    continue
                holds[agent_id] = now_iso(self.clock)
                book = self.book_of(agent)
                if book is not None:
                    try:
                        self._cancel_paused_entries(agent, book)
                    except Exception as exc:  # noqa: BLE001 - the hold stands; its next wake cancels again
                        self.alert("warning", f"{agent_id}: its resting buys could not be cancelled at the drain hold "
                                              f"({type(exc).__name__}: {str(exc)[:160]}); its next wake asks again")
            for agent_id in sorted(set(holds) - waiting):
                agent = self.registry.get(agent_id)
                alive = agent is not None and agent.alive
                if alive and not off and not self._drain_ended(agent):
                    continue  # the pass could not say its drain ended: the hold stands
                paused = self.registry.entries_paused(agent_id) if alive else None
                if paused and paused.get("session") == self.DRAIN_SESSION:
                    why = ("the allocator is off: nothing drains a probe, and the House holds no entries for it" if off else
                           "the House releases its drain hold: the allocator no longer holds this agent as a probe waiting "
                           "to go back to practice")
                    try:
                        self._house_control(agent, "resume_entries", why)
                    except Exception as exc:  # noqa: BLE001 - the hold stands until the next pass releases it
                        self.alert("warning", f"{agent_id}: the House could not release its drain hold ({type(exc).__name__}: "
                                              f"{str(exc)[:160]}); the next pass tries again")
                        continue
                holds.pop(agent_id, None)
            if holds != kept:
                with self._state_lock:
                    self._state["drain_holds"] = holds

    def _drain_rows(self) -> dict[str, dict[str, Any]]:
        """The living agents whose entries stand paused by the House's own row (`DRAIN_SESSION`), as the registry folds
        them from the ledger: {agent id: {"since", "note", "session"}}."""
        registry = self.registry
        with (getattr(registry, "_lock", None) or nullcontext()):
            rows = {agent_id: dict(paused) for agent_id, paused in registry.paused.items()}
        return {agent_id: paused for agent_id, paused in rows.items()
                if paused.get("session") == self.DRAIN_SESSION and (agent := registry.get(agent_id)) is not None and agent.alive}

    def _drain_ended(self, agent: Agent) -> bool:
        """Whether the pass just run ended a held probe's drain: it left rung 2 (back to practice, or any other move), or
        it is still a probe whose family's gate reads neither "losing" nor "unreadable" (its record turned, a probe
        demotion holds the family only against newcomers, its family was proven, or the rule is off: the allocator
        drains it no longer). A family record that cannot be read, a gate that cannot, or a read of either that
        fails ends nothing: the pass could not say (`_hold_draining_probes`)."""
        try:
            if self.evaluator.rung(agent.id) != 2:
                return True
            allocator = self.allocator
            if allocator.family(agent.family, agent.venue).get("error"):
                return False
            gate = allocator.probe_gate(agent)
        except Exception:  # noqa: BLE001 - what cannot be read ends nothing
            return False
        return gate is None or gate.get("gate") not in ("losing", "unreadable")

    def _house_control(self, agent: Agent, control: str, note: str) -> None:
        """Record an entry control (X1) the House makes itself: the row an agent's own `pause_entries` or `resume_entries`
        writes, under `DRAIN_SESSION`, so every reader of `Registry.entries_paused` treats it alike."""
        paused = self.registry.entries_paused(agent.id)
        prior = self.ledger.last("agent.strategy", agent=agent.id)
        carried = str((prior.payload if prior is not None else {}).get("reason") or "")
        row: dict[str, Any] = {"code_sha256": agent.code_sha256, "params": dict(agent.params), "needs": dict(agent.needs),
                               "wake_minutes": agent.wake_minutes, "_code": agent.code, "control": control, "note": note[:600],
                               "session": self.DRAIN_SESSION, **({"reason": carried} if carried else {})}
        if control == "pause_entries":
            row.update(entries="paused", was={"entries": "open"})
        else:
            row.update(entries="open", was={"entries": "paused", "since": (paused or {}).get("since")})
        stamp = now_iso(self.clock)
        self.ledger.append("agent.strategy", row, agent=agent.id, id=f"control:{self.DRAIN_SESSION}:{agent.id}:{control}:{stamp}")
        self.registry.refresh()

    def _submit_wakes(self, book_name: str, outcomes: Sequence[Mapping[str, Any]]) -> list[Any]:
        """Validate again at the batched order boundary: a wake may have waited for other boxes."""
        with self._lifecycle_lock:
            intents = []
            for outcome in outcomes:
                generation = outcome.get("_generation")
                agent = self.registry.get(outcome["agent"])
                if generation is None or self._generation(outcome["agent"]) != generation:
                    continue
                if self.book_of(agent) is not self.books[book_name]:
                    continue
                rows = list(outcome.get("intents") or [])
                if agent.id not in self.books[book_name].limits:
                    # No seat on the book means the book refuses every intent, one `book.refused`
                    # row each ("has no seat on the ... book"), and a strategy reads its own
                    # decisions as refused for a reason it cannot act on. A wake seats a living agent
                    # (`seat`), so this is a seat lost between the decision and its submission (a
                    # demotion, a closed account): drop the intents here, and say so once an agent a
                    # day (workstream B, Sept 23, 2026: 607 such refusals in 48 hours, all of them
                    # the House's own wind-down exits after a restart, fixed in `_wind_down` on Sept
                    # 22; this is the same guard on the agents' side of the path).
                    self._note_unseated(agent, book_name, len(rows))
                    continue
                if self.registry.entries_paused(agent.id):
                    # Its own pause, made after this wake decided (X1): a pause moves no generation
                    # (`_generation`), so its buys are held here. Its sells go on.
                    rows = [intent for intent in rows if intent.side != 'buy']
                if self.paused() and any(intent.side == 'buy' for intent in rows):
                    self.ledger.append('book.refused', {'book': book_name,
                        'reasons': ['the House is paused for maintenance: exits and cancels only']}, agent=agent.id)
                    rows = [intent for intent in rows if intent.side != 'buy']
                if (self.books[book_name].real_money and self.campaigns
                        and not self.campaigns.allows_live(self.evaluator.rung(agent.id))):
                    if any(intent.side == 'buy' for intent in rows):
                        self.ledger.append('book.refused', {'book': book_name,
                            'reasons': ['the live allocation window closed before submission']}, agent=agent.id)
                    rows = [intent for intent in rows if intent.side != 'buy']
                intents.extend(rows)
            return self.books[book_name].submit(intents) if intents else []

    def _note_unseated(self, agent: Agent, book_name: str, dropped: int) -> None:
        """Say once an agent a day that its decisions were dropped for want of a seat (`_submit_wakes`)."""
        today = now_iso(self.clock)[:10]
        with self._state_lock:
            told = self._state.setdefault("unseated_told", {})
            if told.get(agent.id) == today:
                return
            told[agent.id] = today
            for key in [k for k, day in told.items() if day != today]:
                told.pop(key, None)
        self.alert("warning", f"{agent.id}: {dropped} intent(s) dropped before the {book_name} book: it has no seat there "
                              "(a seat lost between its decision and the submission). Nothing was refused on its record; "
                              "its next wake seats it again if it is still on that book.")

    def _order_path_invariants(self) -> None:
        """Workstream B (Sept 23, 2026): the order path finds its own next defect. Two checks a
        tick, each raised as an ops warning, each throttled so a standing condition is told once:

        - A `book.refused` row for an agent that is not alive, told once an agent a day. The dead
          do not decide: such a refusal is the House's own exit of an abandoned account walking into
          a wall on every mark pass (Sept 21-22, 2026: 607 "has no seat" and 576 "outside regular
          hours" refusals, found by reading the ledger a day later). Read from a cursor kept in
          house.json, never the whole ledger; the first pass reads back `ORDER_INVARIANTS_FIRST_ROWS`.
        - A round-the-clock desk (coins, Kalshi: `Niche.keeps_hours` false) with living members and
          no wake for `QUIET_ROUND_THE_CLOCK_SECONDS` while the House is not paused, told once a desk
          per that long. The stamps are `desk_woke` (set by `wake`); a pause, and the House's own
          start, reset the clock, since neither is a scheduler fault. A closed compute allowance
          stops wakes too (`_note_stopped` says so after two minutes): this says which markets it
          is leaving unattended. So does the birth of the desk's oldest living member (a desk with no
          member has no one to wake), and a desk is late only at twice its briskest member's
          `wake_minutes`. Sept 24, 2026: kalshi-open's first member ever was born at 14:12:14Z and the
          desk was called unwoken "for 146 minutes" at 14:12:43Z (the House had started at 11:46Z);
          kalshi-attention's one member woke every 30-31 minutes as scheduled and was called unwoken
          twelve times that day, at 30 or 31 minutes each.
        """
        now = self.clock()
        with self._state_lock:
            state = self._state.setdefault("order_invariants", {})
            if now - float(state.get("at") or 0) < ORDER_INVARIANTS_EVERY_SECONDS:
                return
            state["at"] = now
            cursor = state.get("cursor")
            told_dead: dict[str, str] = dict(state.get("dead_told") or {})
            told_quiet: dict[str, float] = dict(state.get("quiet_told") or {})
            paused_at = float(state.get("paused_at") or 0)
        if cursor is None:
            head = self.ledger.read(limit=1, newest=True)
            cursor = max(0, (head[-1].seq if head else 0) - ORDER_INVARIANTS_FIRST_ROWS)
        alerts: list[str] = []
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        walls: dict[str, list[Any]] = {}
        for row in self.ledger.iter(kinds="book.refused", after=int(cursor)):
            cursor = row.seq
            agent = self.registry.get(row.agent)
            if row.agent == HOUSE or (agent is not None and agent.alive) or told_dead.get(row.agent) == str(row.at)[:10]:
                continue
            wall = walls.setdefault(row.agent, [0, str(row.payload.get("book") or ""), ""])
            wall[0] += 1
            wall[2] = wall[2] or str((row.payload.get("reasons") or [""])[0])[:160]
        for agent_id, (count, book_name, reason) in walls.items():
            told_dead[agent_id] = today
            alerts.append(f"{agent_id}: {count} intent(s) refused on {book_name} for an agent that is not alive ({reason!r}). "
                          "The dead do not decide: this is the House's own exit of an abandoned account walking into a wall "
                          "on every mark pass (`_wind_down`), not a strategy's mistake.")
        if self.paused():
            paused_at = now
        else:
            woke = self._state.get("desk_woke") or {}
            living = self.registry.living()
            for niche_id, niche in self.niches.items():
                members = [a for a in living if a.specialty == niche_id]
                if not members or all(niche.keeps_hours(a.needs) for a in members):
                    continue  # no one to wake, or a desk that keeps the session: its quiet nights are its own
                awake = [a for a in members if not niche.keeps_hours(a.needs)]  # the members a night wakes
                last = max(float(woke.get(niche_id) or 0), paused_at, self._born_at, min(_epoch(a.born_at) for a in awake))
                late = max(QUIET_ROUND_THE_CLOCK_SECONDS, 2 * 60.0 * min(max(1, int(a.wake_minutes or 0)) for a in awake))
                if now - last < late or now - float(told_quiet.get(niche_id) or float("-inf")) < late:
                    continue
                told_quiet[niche_id] = now
                stopped = str((self._state.get("stopped") or {}).get("reason") or "")
                alerts.append(f"{niche_id}: no wake on a round-the-clock desk for {int((now - last) // 60)} minutes with {len(members)} "
                              f"living member(s) and the House not paused" + (f" ({stopped})" if stopped else "")
                              + ". Its markets are live and unattended.")
        with self._state_lock:
            state.update(cursor=int(cursor), paused_at=paused_at,
                         dead_told={k: v for k, v in told_dead.items() if v >= today},
                         quiet_told={k: v for k, v in told_quiet.items() if now - float(v) < QUIET_DESK_DAY_SECONDS})
        for text in alerts:
            self.alert("warning", text)

    def _offered(self, agent: Agent, ctx: Mapping[str, Any]) -> int:
        """How many live, tradeable things this wake actually put in front of the strategy.

        Zero means there was nothing to act on -- a shut equity session, an empty Kalshi window --
        and doing nothing was the only right answer. A number above zero with nothing done means
        the strategy looked at a live market and its rules did not fire: that is the strategy's
        problem to solve, and the House should hand it a research pass rather than wake it into
        the same wall for hours.

        A Kalshi wake counts only the markets of the series its NEEDS names that resolve inside its
        horizon (`horizon_hours`, what the book would admit). Sept 24, 2026: greenwich-h4cb387 (NFL
        props closing within 6 hours; the next game was ten hours off) was shown 76, 70, 63 and 46
        markets of its desk's busiest live series -- the fallback `snapshot` puts in front of a program
        whose own series are dark (UEFA and DJI, its own research noted at 14:16Z) -- which its code
        skips by series, and each wake was counted "barren": the desk was called quiet at 14:58Z, and
        the barren run feeds the research gate and the "stuck" cull. Those wakes had nothing in its
        window."""
        if family_of(agent.venue) == "kalshi":
            own = {str(series).upper() for series in (agent.needs.get("series") or [])}
            horizon = self.horizon_hours(agent)
            return sum(1 for market in ctx.get("markets") or []
                       if (not own or str(market.get("series") or "").upper() in own)
                       and (horizon is None or market.get("hours_to_resolve") is None
                            or float(market["hours_to_resolve"]) <= horizon))
        niche = self.niche_of(agent)
        if niche is not None and niche.keeps_hours(agent.needs) and not market_open_at(ctx["now"]):
            # A shut session offers only coins (an open desk may mix both; every other desk is one or the other).
            return sum(1 for symbol, quote in (ctx.get("quotes") or {}).items() if quote and niche.open and "/" in str(symbol))
        return sum(1 for quote in (ctx.get("quotes") or {}).values() if quote)

    def _note_wake(self, agent: Agent, *, acted: bool, offered: int) -> dict[str, int]:
        """Keep a running count of the wakes an agent has spent doing nothing, split by whose
        fault it was: `barren` (it saw a live market and its rules did not fire) and `shut` (there
        was nothing open). Either run is time the agent is not learning, and `research_due` reads
        them; acting resets both."""
        with self._state_lock:
            idle = dict(self._state["idle"].get(agent.id) or {"barren": 0, "shut": 0})
            if acted:
                idle = {"barren": 0, "shut": 0}
            elif offered > 0:
                idle["barren"] = int(idle.get("barren") or 0) + 1
            else:
                idle["shut"] = int(idle.get("shut") or 0) + 1
            idle["offered"] = offered
            self._state["idle"][agent.id] = idle
        return idle

    def _intents(self, agent: Agent, book: Book, rows: list[Mapping[str, Any]], *,
                 adjusted: list[str] | None = None, cancelling: Collection[str] = ()) -> tuple[list[Intent], list[str]]:
        """What a decision asked for, as sized intents for the book; what cannot be read is dropped.

        On the way the order guards (Sept 22, 2026) put each order on the venue's own terms. They
        only ever make an order smaller or less aggressive -- except one step up to reach a venue
        minimum, which the book still caps -- and the book stays the final judge of every order:

        - a limit price is snapped to the venue's grid (`venues.price_increment`), a buy DOWN and a
          sell UP; a coin whose increment the venue has not stated is left as it is;
        - a given `quantity` is floored to the instrument's step, as a `notional_usd` always was;
        - a BUY asked under the venue's minimum (`venues.min_order_usd`, $10 for Alpaca crypto) is
          refused here, as a House refusal on the record (`book.refused`, "below the venue
          minimum") that the strategy sees in `recent_order_outcomes`; one asked at or over it that
          the step floored under it is raised one step. Measured Sept 20-22, 2026: Alpaca refused 55
          paper orders under its $10 minimum in 48 hours, among them requests of exactly $10.00 the
          step had floored to $9.9999999. Sells are left alone: whether Alpaca holds an exit to the
          minimum is not measured.
        - a real-money Alpaca BUY is trimmed to what the book will take (`_fit_real_entry`): the
          position it leaves valued at the ask, as the book values it, within `_real_limits`. A bid
          under the ask sized to its own price was otherwise refused as over half the equity. A bid
          the same decision cancels (`cancelling`) is not counted against the new one;
        - an OPTION asked for at market becomes a limit at the touch, and a POST-ONLY Kalshi bid or
          offer that would cross the touch is re-priced one tick inside it (`_fit_order_type`,
          Sept 23, 2026): the decision trades, or rests, instead of being refused or rejected.

        Each change a guard made is appended to `adjusted` (the wake records it on `agent.woke`)."""
        intents, dropped = [], []
        now = now_iso(self.clock)
        for index, row in enumerate(rows):
            try:
                instrument = instrument_for(book.broker.venue, dict(row))
                side = str(row.get("side") or "").lower()
                if (book.real_money and side == "buy" and self.campaigns
                        and not self.campaigns.allows_live(self.evaluator.rung(agent.id))):
                    raise ValueError("this phase permits exits but no new real-money entries")
                niche = self.niche_of(agent)
                if niche is not None and side == "buy" and not niche.holds(instrument):
                    raise ValueError(f"{instrument.market_id or instrument.symbol} is outside the {niche.id} specialty")
                order_type = str(row.get("type") or "market").lower()
                notes: list[str] = []
                limit = None if row.get("limit_price") is None else money(str(row["limit_price"]))
                if limit is not None:
                    increment = self._price_increment(book, instrument, limit)
                    snapped = snap_limit(instrument, side, limit, increment)
                    if snapped != limit:
                        notes.append(f"limit {limit} snapped {'down' if side == 'buy' else 'up'} to {snapped} (the venue's {increment} grid)")
                        limit = snapped
                fitted_order = self._fit_order_type(book, instrument, side, order_type, limit, bool(row.get("post_only")))
                if fitted_order is not None:
                    order_type, limit, note = fitted_order
                    notes.append(note)
                step = step_of(instrument, order_type)
                price = limit
                requested: Decimal | None = None  # the order's dollars as asked, once there is a price to count them at
                if row.get("quantity") is not None:
                    asked = money(str(row["quantity"]))
                    floored = (asked / step).to_integral_value(rounding=ROUND_DOWN) * step
                    quantity = asked if floored == asked else floored
                    if 0 < quantity != asked:
                        notes.append(f"quantity {asked} floored to {quantity} (the instrument's step of {step})")
                else:
                    requested = money(str(row["notional_usd"]))
                    quote = book.broker.quote(instrument)
                    price = limit or (quote.ask if side == "buy" else quote.bid)
                    if price is None or price <= 0:
                        raise ValueError("no price to size the order at")
                    quantity = ((requested / (price * instrument.multiplier)) / step).to_integral_value(rounding=ROUND_DOWN) * step
                if quantity <= 0:
                    raise ValueError("the size rounds down to nothing")
                minimum = min_order_usd(instrument) if side == "buy" else None
                # A Kalshi entry past the horizon is refused here, saying what it was judged by (X2).
                refusal = self._horizon_refusal(agent, book, instrument) if side == "buy" else ""
                if not refusal and side == "buy" and market_hours(instrument, now) is False:
                    # The wake skip's other half (Sept 24, 2026): an agent still woken outside the session
                    # (an open desk naming a coin) sends no stock or option entry. A market buy would be
                    # refused by the book, and a limit would only wait at the venue for the open.
                    refusal = ("outside the regular session no stock or option entry is sent: it could not trade before "
                               "the open. The House wakes a desk that keeps hours a few seconds after the bell; decide it then")
                if minimum is not None:
                    if price is None:
                        try:  # a market buy sized in units: the ask it will pay
                            price = book.broker.quote(instrument).ask
                        except Exception:  # noqa: BLE001 - no price, no guess: the book and the venue judge it
                            price = None
                    if price is not None and price > 0:
                        if requested is None:
                            requested = asked * price * instrument.multiplier
                        if requested < minimum:
                            refusal = (f"a ${requested:.2f} buy is below the venue minimum of ${minimum} an order "
                                       f"(Alpaca refuses a crypto order under ${minimum}); size it at ${minimum} or more")
                        elif quantity * price * instrument.multiplier < minimum:
                            quantity += step
                            notes.append(f"quantity raised one step to {quantity}: the ${requested:.2f} asked, floored to the step, "
                                         f"was under the venue minimum of ${minimum}")
                if side == "buy" and not refusal and book.real_money and family_of(book.broker.venue) == "alpaca":
                    fitted = self._fit_real_entry(agent, book, instrument, quantity, limit, step, minimum, cancelling)
                    if fitted is not None:
                        notes.append(f"quantity {quantity} trimmed to {fitted[0]}: {fitted[1]}")
                        quantity = fitted[0]
                intent = Intent.new(
                    agent=agent.id, instrument=instrument, side=side, quantity=quantity, order_type=order_type,
                    limit_price=limit, post_only=bool(row.get("post_only")), reason=str(row.get("reason") or ""),
                    created_at=now, nonce=f"{now}:{index}",
                )
                if refusal:
                    try:
                        # The shape of the book's own refusal row, so the strategy, the pre-audit and
                        # the site read it the same way; it was never sent, so there is no order row.
                        self.ledger.append("book.refused", {"book": book.name, "intent_id": intent.id, "reasons": [refusal],
                                                            "instrument": instrument.to_dict()},
                                           agent=agent.id, id=f"refused:{intent.id}")
                    except LedgerConflict:
                        pass  # this very intent was refused already
                    continue
                intents.append(intent)
                if adjusted is not None:
                    shown = occ_symbol(instrument) if instrument.asset_class == "option" else (instrument.market_id or instrument.symbol)
                    adjusted.extend(f"{shown} {side}: {note}" for note in notes)
            except Exception as exc:  # noqa: BLE001 - one malformed intent is dropped, the rest stand
                dropped.append(f"{type(exc).__name__}: {str(exc)[:160]}")
        return intents, dropped

    def _fit_order_type(self, book: Book, instrument: Instrument, side: str, order_type: str, limit: Decimal | None,
                        post_only: bool) -> tuple[str, Decimal | None, str] | None:
        """Two fittings of an order's type and price to what the book and the venue take, each done
        once and said on the wake (`adjusted`): (order type, limit, why), or None when the order
        stands as asked. The book stays the judge of the fitted order.

        - An OPTION asked for at market becomes a limit at the touch: the ask to buy, the bid to
          sell. The book takes no option market order ("an option order must be a limit order",
          `Book.check`) and neither does Alpaca; a decision sent that way was refused whole.
          Measured Sept 22, 2026: 125 refusals on alpaca-paper, every one of them the House's own
          wind-down of a dead options account (fixed at the bid the same day); this is the same
          guard for the agents' own decisions. The book's `max_limit_deviation_pct` is measured
          from the touch on the order's side (`ltcm.risk.rule_limit_sanity`), so a limit AT the
          touch is inside it by construction.
        - A POST-ONLY Kalshi bid at or over the ask (an offer at or under the bid) is re-priced one
          tick inside the touch, snapped to the market's grid. Kalshi rejects a post-only order that
          would cross ("post only cross": 8 of 50 real maker orders on Sept 23, 2026, huang-h51fdd3-2
          bidding NO at a touch that had moved since its decision) and the shadow book does the
          same, so the decision was lost each time; resting one tick inside is what the strategy
          meant by post-only. Re-priced once, on the quote of this moment: if the touch moves again
          before the venue has it, the venue's rejection stands and says so (`Book._route`).
        The re-price for the House's own wind-down (an exit that would meet the House's own bid rests
        at the ask, `_wind_down`) is the same idea for the other wall."""
        option_at_market = instrument.asset_class == "option" and order_type == "market"
        maker = post_only and order_type == "limit" and limit is not None and family_of(book.broker.venue) == "kalshi"
        if not option_at_market and not maker:
            return None
        try:
            quote = book.broker.quote(instrument)
        except Exception:  # noqa: BLE001 - no quote, no fitting: the book judges the order as asked
            return None
        touch = getattr(quote, "ask" if side == "buy" else "bid", None) if quote is not None else None
        if touch is None or touch <= 0:
            return None
        touch = money(touch)
        increment = self._price_increment(book, instrument, touch)
        if option_at_market:
            fitted = snap_limit(instrument, side, touch, increment) or touch
            return "limit", fitted, (f"a market {side} became a limit at the {'ask' if side == 'buy' else 'bid'} of {fitted}: "
                                     "an option order must be a limit order (the book takes no other)")
        crosses = limit >= touch if side == "buy" else limit <= touch
        if not crosses:
            return None
        tick = increment if increment is not None and increment > 0 else Decimal("0.01")
        inside = touch - tick if side == "buy" else touch + tick
        inside = snap_limit(instrument, side, inside, tick) or inside
        if not 0 < inside < 1:
            return None  # nothing rests inside a touch at the contract's own bound; the venue says so
        return order_type, inside, (f"post-only limit {limit} re-priced to {inside}, one tick inside the "
                                    f"{'ask' if side == 'buy' else 'bid'} of {touch}: it would have crossed, and the venue rejects a post-only order that crosses")

    def _price_increment(self, book: Book, instrument: Instrument, price: Decimal | None) -> Decimal | None:
        """The price grid of this book's venue for this instrument at this price
        (`venues.price_increment`), with what only the venue can say: a coin's asset record (the
        adapter's cached `asset`; fakes, the simulator and the Kalshi shadow have none, so a coin's
        increment is then unknown) and a Kalshi market's price bands."""
        if instrument.asset_class == "crypto":
            lookup = getattr(book.broker, "asset", None)
            asset = None
            if callable(lookup):
                try:
                    asset = lookup(instrument.market_id or instrument.symbol)
                except Exception:  # noqa: BLE001 - an unread record is an unknown increment
                    asset = None
            return price_increment(instrument, price, asset=asset if isinstance(asset, Mapping) else None)
        if instrument.asset_class == "event":
            return price_increment(instrument, price, bands=self._price_grid(book, instrument))
        return price_increment(instrument, price)

    def _price_grid(self, book: Book, instrument: Instrument) -> tuple[Any, ...]:
        """A Kalshi market's own price bands as its book's venue reads them -- the real adapter's
        `price_ranges`, the shadow's market data -- kept `PRICE_GRID_TTL_SECONDS` a ticker. Empty when
        the venue cannot say; `venues.price_increment` then takes the cent, as both adapters do."""
        ticker = str(instrument.market_id or instrument.symbol).upper()
        key = f"{book.name}:{ticker}"
        hit = self._price_grids.get(key)
        if hit is not None and self.clock() - hit[0] < PRICE_GRID_TTL_SECONDS:
            return hit[1]
        reader = getattr(book.broker, "price_ranges", None) or getattr(getattr(book.broker, "market_data", None), "price_ranges", None)
        bands: tuple[Any, ...] = ()
        if callable(reader):
            try:
                bands = tuple(band for band in reader(ticker) or () if isinstance(band, Mapping)
                              and all(isinstance(band.get(k), Decimal) for k in ("start", "end", "step")))
            except Exception:  # noqa: BLE001 - an unread grid is the cent, never a guessed finer one
                bands = ()
        if len(self._price_grids) > 5000:
            self._price_grids.clear()  # a day's markets are gone by the next; nothing here is state
        self._price_grids[key] = (self.clock(), bands)
        return bands

    def _venue_rules(self, book: Book, symbols: Sequence[str], quotes: Mapping[str, Any] | None) -> dict[str, dict[str, float]]:
        """`ctx["venue_rules"]`: what the venue asks of an order in each tradeable symbol, where it
        is known -- `min_order_usd` ($10 for Alpaca crypto) and `price_increment` (a stock's at its
        current touch, a coin's from the venue's asset record). A strategy that sizes and prices by
        these is never refused or adjusted by the order guards in `_intents`."""
        rules: dict[str, dict[str, float]] = {}
        for symbol in symbols:
            try:
                instrument = instrument_for(book.broker.venue, {"symbol": symbol})
                quote = (quotes or {}).get(symbol) or {}
                touch = (quote.get("ask") or quote.get("bid")) if isinstance(quote, Mapping) else None
                price = money(str(touch)) if isinstance(touch, (int, float, str, Decimal)) and not isinstance(touch, bool) else None
                rule: dict[str, float] = {}
                minimum = min_order_usd(instrument)
                if minimum is not None:
                    rule["min_order_usd"] = float(minimum)
                increment = self._price_increment(book, instrument, price if price is not None and price > 0 else None)
                if increment is not None:
                    rule["price_increment"] = float(increment)
            except Exception:  # noqa: BLE001 - a rule that cannot be told is left out, never guessed
                continue
            if rule:
                rules[symbol] = rule
        return rules

    def _cancel_stale_resting(self) -> int:
        """Cancel the resting ENTRIES of an agent whose wakes have stopped completing. Returns how
        many orders it asked the venue to cancel.

        Only a strategy's own wake can cancel its order, so a resting buy outlives every wake that
        does not complete: a snapshot that cannot be built (the wake is skipped), a box that does
        not run, a decide that raises, a floor whose meter has stopped waking paper agents. Sept 22,
        2026: the frontier auditor vetoed a crypto agent partly because its resting buys had no
        stale guard, and the House had none either. Here, a buy -- on Kalshi, every buy opens or
        adds to a position -- is cancelled through the book's own cancel path once no wake of every
        agent sharing it has completed (`agent.woke` with ok) on its book for `STALE_WAKES` of that
        agent's wake intervals, and never sooner than `STALE_FLOOR_SECONDS`. The clock starts at
        this House's own start at the earliest: a wake the House did not attempt is not the
        strategy failing. Exits are never touched, on any book. Each cancellation is noted on the
        agent's record (`agent.inactive`, reason `wakes_failing`).

        Cheap by construction, since it runs every tick: only open, acknowledged buys are looked at,
        with one indexed ledger read for each agent that owns one."""
        now = self.clock()
        asked = 0
        for book in list(self.books.values()):
            last_wakes: dict[str, Any] = {}
            for working in book.open_orders():
                if working.side != "buy" or working.status not in ("accepted", "partially_filled"):
                    continue  # an exit, or an order the venue has not acknowledged (the poll resolves those)
                owners = sorted({share.agent for share in working.shares})
                stale: list[tuple[Agent, Any, float]] = []
                for owner in owners:
                    agent = self.registry.get(owner)
                    if agent is None or not agent.alive:
                        break  # a dead agent's account is the wind-down's to close, not this guard's
                    if owner not in last_wakes:
                        last_wakes[owner] = next((e for e in reversed(self.ledger.read(kinds="agent.woke", agent=owner, limit=50, newest=True))
                                                  if e.payload.get("ok") is True and e.payload.get("book") in (None, book.name)), None)
                    last = last_wakes[owner]
                    allowance = max(STALE_WAKES * agent.wake_minutes * 60, STALE_FLOOR_SECONDS)
                    since = max(_epoch(last.at) if last is not None else 0.0, self._born_at)
                    if now - since <= allowance:
                        break  # this agent is managing its orders
                    stale.append((agent, last, allowance))
                if not owners or len(stale) != len(owners):
                    continue
                try:
                    outcome = book.cancel(owners[0], working.order_id)
                except Exception as exc:  # noqa: BLE001 - one order that cannot be cancelled now is asked again next tick
                    self.alert("warning", f"{owners[0]}: a stale resting buy {working.order_id} on {book.name} could not be cancelled "
                                          f"({type(exc).__name__}: {str(exc)[:160]})")
                    continue
                if outcome.status in ("refused", "rejected"):
                    continue  # the venue did not take the cancel (or it closed meanwhile): asked again next tick while it stays open
                asked += 1
                for agent, last, allowance in stale:
                    since = last.at if last is not None else None
                    payload = {"agent": agent.id, "reason": "wakes_failing", "book": book.name, "order_id": working.order_id,
                               "last_completed_wake": since, "allowance_minutes": round(allowance / 60, 1),
                               "detail": (f"no wake has completed on {book.name} since {since or 'the record began'}, "
                                          f"over the {allowance / 60:g} minutes allowed: the House asked the venue to cancel its "
                                          f"resting buy {working.order_id} (exits are never cancelled)")}
                    try:
                        self.ledger.append("agent.inactive", payload, agent=agent.id,
                                           id=f"agent-inactive:{agent.id}:wakes_failing:{working.order_id}")
                    except LedgerConflict:
                        pass  # already noted when the cancel was first asked
        return asked

    def _pace_inference(self) -> None:
        """The provider's own daily cap on the floor's inference follows the expedition's allowance.

        Two numbers for one budget always end with the tighter one winning silently. Measured Sept
        20, 2026: the pacer allowed $14.29 of Sail a day and the provider's fixed cap was $9.00, so
        every research pass on the floor stopped at nine dollars -- ten in a row refused as
        `provider_floor_cap_exceeded` -- with the owner's budget half unspent and nothing saying
        why. The config number stays on as a CEILING, so a pacer that miscomputes still cannot
        spend past what the owner set by hand."""
        provider = getattr(self.researcher, "provider", None) if self.researcher is not None else None
        if provider is None or not hasattr(provider, "floor_cap"):
            return
        if self._inference_ceiling is None:
            self._inference_ceiling = Decimal(str(provider.floor_cap))
        allowance = self.pacer.allowance("sail") if self.pacer.running() else ZERO
        provider.floor_cap = min(self._inference_ceiling, allowance) if allowance > 0 else self._inference_ceiling
        # A request is charged against the day before it is sent, and only settling, abandoning or
        # reconciling gives it back. A pass killed by a restart -- which a floor that deploys itself
        # does often -- leaves its reservation standing until midnight UTC, against the same cap
        # this method just set. `reconcile_stale` is the documented cure and nothing on the floor
        # was calling it: its one caller is `spent_today`, which nothing in league/ uses.
        if hasattr(provider, "reconcile_stale"):
            try:
                provider.reconcile_stale()
            except Exception as exc:  # noqa: BLE001 - a stale sweep that fails is a warning, not a tick
                self.alert("warning", f"stale inference reservations could not be reconciled ({type(exc).__name__}: {str(exc)[:160]})")

    def _update(self) -> None:
        outcome = self.updater.check()
        action = outcome.get("action")
        if action == "deploying":
            # A promotion signals this process and a fresh one comes up thirty seconds later, so
            # every research pass still running is thrown away with everything it has read. The
            # canary and its watch give about ten minutes of warning: stop STARTING passes now and
            # the ones in flight finish on their own. Measured Sept 20, 2026: three deploys inside
            # thirteen minutes killed eleven passes, which is most of an hour's research.
            with self._state_lock:
                self._state["deploying_at"] = self.clock()
        if action == "deploying" or (action == "refused" and outcome.get("new", True)) or outcome.get("new"):
            # The attestation is the record of what GitHub said about the exact commit (see
            # league/updater.py); a head that is merely waiting for its checks is not news.
            self.ledger.append("ops.deploy", {k: v for k, v in outcome.items() if k in ("action", "release", "reasons", "files", "sha", "attestation")})
        if action in ("refused", "blocked", "waiting") and outcome.get("new"):
            # A warning, never an error: an error alert inside a release's watch rolls THAT release
            # back, and a head that cannot be deployed says nothing about the one running.
            self.alert("warning", f"main {str(outcome.get('sha') or '?')[:12]} was not deployed ({action}): "
                                  + "; ".join(str(r) for r in outcome.get("reasons") or [])[:700])

    def _history_coverage(self) -> None:
        """What the history ingestion (a separate process, `python -m league.history`) fetched
        becomes `data.coverage` ledger rows here, because only the House writes the ledger."""
        now = self.clock()
        if not self.settings.history_coverage or now - getattr(self, "_history_checked", 0.0) < 300:
            return
        self._history_checked = now
        try:
            from .history import publish_coverage

            publish_coverage(self.ledger, self.root, clock=self.clock)
        except Exception as exc:  # noqa: BLE001 - a bad store file must never take the tick down
            self.alert("warning", f"history coverage could not be recorded ({type(exc).__name__}: {str(exc)[:160]})")

    def _fulfil_feed_requests(self) -> None:
        """Answer the tool requests that plainly ask for a feed the House now records (`FeedRecorder.
        fulfil_requests`): the `tool.fulfilled` row is what wakes the research of the line that asked
        (the research gate counts it), and what tells consult recovery the data has arrived."""
        done = self.feeds.fulfil_requests(self.commons)
        if done:
            self.alert("info", f"the live feeds answered {len(done)} open tool request(s)")

    def deploying(self) -> bool:
        """Is a release on its way in? True from the moment one is staged until the grace is up."""
        since = float(self._state.get("deploying_at") or 0)
        return bool(since) and self.clock() - since < float(self.settings.deploy_grace_seconds)

    def _wake_safely(self, agent: Agent) -> dict[str, Any]:
        try:
            with self._box_patience():  # a pool thread of the tick: it never waits on background work
                return self.wake(agent)
        except Exception as exc:  # noqa: BLE001 - one agent's wake must never take the tick down
            self.alert("error", f"{agent.id}: its wake failed ({type(exc).__name__}: {str(exc)[:200]})", **environment("gateway", exc))
            return {"agent": agent.id, "error": str(exc)}

    def _holds_real_money(self, agent: Agent) -> bool:
        book = self.books.get(REAL_BOOK[agent.venue])
        return bool(book and agent.id in book.accounts and (book.account(agent.id).holdings or book.open_orders(agent.id)))

    # ----------------------------------------------------------------- replay
    def _replayable(self, niche: Any, needs: Mapping[str, Any]) -> bool:
        """Can this specialty be replayed for these NEEDS? The options desk can once the options
        history covers every underlying it trades over the replay window (Alpaca has option bars
        since Jan 18, 2024 and no historical quotes: `league/options_history.py`)."""
        if getattr(niche, "replay", True):
            return True
        if getattr(niche, "asset_class", None) != "option" or not self.settings.options_replay or self.options_history is None:
            return False
        symbols = [str(s).upper() for s in (needs.get("symbols") or [])][:8]
        end = self.clock()
        start = end - self.settings.replay_days * (6 if str(needs.get("horizon")) == "day" else 1) * 86400
        try:
            start_iso = max(now_iso(lambda: start), self._after_holdout())
            return bool(symbols) and len(self.options_history.covers(symbols, "15Min", start_iso, now_iso(lambda: end))) == len(symbols)
        except Exception as exc:  # noqa: BLE001 - an unreadable store is no history, and paper stays the replay
            self.alert("warning", f"options history unreadable ({type(exc).__name__}: {str(exc)[:120]})")
            return False

    def _after_holdout(self) -> str:
        """The first moment after the sealed holdout window, as an ISO stamp."""
        from datetime import date, timedelta
        return (date.fromisoformat(str(self.holdout_window[1])[:10]) + timedelta(days=1)).isoformat() + "T00:00:00Z"

    def _refresh_options_history(self) -> dict[str, Any]:
        """The daily options-history job (ops lane, market-data GETs only): the underlyings living
        options strategies trade, at 1Day and 15Min; the feature symbols of living equity
        strategies (and SPY, QQQ, IWM) at 1Day; then their feature rows. A symbol the store does
        not yet cover over the replay window is backfilled across it first; the chunk journal
        makes that a one-off (six underlyings over three and a half months took about ten
        minutes and 70 MB, Sept 22, 2026). Until a symbol is covered, paper stays its replay."""
        from .options_history import adapter_from, refresh
        options = {n.id for n in self.niches.values() if n.asset_class == "option"}
        replay = sorted({str(s).upper() for a in self.registry.living() if a.specialty in options for s in (a.needs.get("symbols") or [])[:8]})
        wanted = sorted({str(s).upper() for a in self.registry.living() if a.needs.get("options_features") for s in (a.needs.get("symbols") or [])}
                        | {"SPY", "QQQ", "IWM"})
        wanted = [s for s in wanted if s not in replay]
        underlier = adapter_from(self.alpaca_data)
        span = self.settings.replay_days * 6 + 5
        start, end = now_iso(lambda: self.clock() - span * 86400), now_iso(self.clock)
        done: dict[str, Any] = {"features": {}, "coverage": []}
        for group, timeframes, band in ((replay, ("1Day", "15Min"), 0.2), (wanted, ("1Day",), 0.10)):
            covered = set(self.options_history.covers(group, timeframes[-1], start, end))
            for days, symbols in ((10, [s for s in group if s in covered]), (span, [s for s in group if s not in covered])):
                if symbols:
                    ran = refresh(self.options_history, symbols, underlier, days=days, timeframes=timeframes, band=band, max_days=45)
                    done["features"].update(ran["features"])
                    done["coverage"] += ran["coverage"]
        self.ledger.append("ops.budget", {"what": "options history refresh", "replay_symbols": len(replay), "feature_symbols": len(wanted),
                                          "features_made": done["features"],
                                          "not_complete": [r for r in done["coverage"] if r.get("status") not in ("complete", "current")][:20]})
        with self._state_lock:
            self._state["options_history_day"] = _new_york(self.clock)[0]  # done for today only once it ran through
        return done

    def tape_for(self, needs: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        """The recorded history a strategy with these NEEDS is replayed over (cached for a day)."""
        venue, horizon, _ = niche_of(needs)
        option = venue == "alpaca" and str(needs.get("asset_class") or "") == "option"
        wanted = self._feeds_wanted(needs)
        # The history store holds no option chains, and no feed reaches back into its development
        # window (the backfilled history feeds cover the live window): a strategy that reads either is
        # replayed on the live tape.
        if venue == "alpaca" and self.settings.deep_replay and not option and not wanted:
            deep = self._deep_tape(needs)
            if deep is not None:
                return deep
        start, end = self._live_window(needs)
        start_iso, end_iso = now_iso(lambda: start), now_iso(lambda: end)
        watched = needs.get("observe") if isinstance(needs.get("observe"), dict) else {}
        if option and self.options_history is not None:
            from .options_history import adapter_from
            # Development data never reaches into the sealed holdout (`deep_replay.HOLDOUT`): the
            # options window starts after it ends (the default 126 days already do).
            start_iso = max(start_iso, self._after_holdout())
            execution = "15Min"
            under = [str(s).upper() for s in (needs.get("symbols") or [])][:8]
            warmup = max(1, min(500, int((needs.get("bars") or {}).get("limit") or 120)))
            timeframe = str((needs.get("bars") or {}).get("timeframe") or "1Day")
            key = f"options:{','.join(under)}:{timeframe}:{int(needs.get('max_days_to_expiry') or 21)}:{warmup}:{horizon}:{start_iso[:10]}:{execution}"
            build = lambda: self.options_history.tape(needs, start_iso, end_iso, horizon=horizon, warmup=warmup, execution=execution,  # noqa: E731
                                                      underlier_bars=adapter_from(self.alpaca_data),
                                                      max_order_usd=float(CONSTITUTION["rungs"]["1"]["max_order_usd"]))
        elif venue == "alpaca":
            symbols = sorted(str(s) for s in (needs.get("symbols") or []))[:12]
            # What the strategy watches rides on the same tape, so a replay sees what a wake sees.
            symbols = sorted(set(symbols) | {str(s) for s in (watched.get("symbols") or [])[:6]})
            timeframe = str((needs.get("bars") or {}).get("timeframe") or "5Min")
            warmup = max(1, min(500, int((needs.get("bars") or {}).get("limit") or 120)))
            key = f"alpaca:{','.join(symbols)}:{timeframe}:{warmup}:{horizon}:{start_iso[:10]}:{getattr(self.alpaca_data, 'feed', 'unknown')}"
            build = lambda: self.alpaca_data.tape(symbols, timeframe, start=start_iso, end=end_iso, horizon=horizon, warmup_bars=warmup)  # noqa: E731
            if needs.get("options_features") and self.options_history is not None:
                key += ":options-features"
                plain = build

                def build(plain=plain, symbols=symbols):  # the feature rows carry their availability stamps
                    tape = plain()
                    tape["options_features"] = self.options_history.feature_series(symbols)
                    return tape
        else:
            series = sorted(str(s) for s in (needs.get("series") or []))[:12]
            # What it watches rides on the tape too, so a replay sees what a wake sees: the series
            # of another desk, and -- the thing six agents across four desks asked the toolsmith
            # for, and that no strategy helper could ever supply -- the bars of the underlier its
            # strikes are written on. Recorded once for the whole window and sliced per step.
            series = sorted(set(series) | {str(s) for s in (watched.get("series") or [])[:niches_module.MAX_OBSERVED]})
            under = sorted({str(s) for s in (watched.get("symbols") or [])})[:niches_module.MAX_OBSERVED]
            observed_timeframe = str((needs.get("bars") or {}).get("timeframe") or "1Hour")
            observed_limit = max(1, min(200, int((needs.get("bars") or {}).get("limit") or 60)))
            # A tape is JSON handed to a sealed box, and a seven-week sports tape at five-minute
            # steps is hundreds of megabytes: three agents of the sports desk had their replays
            # KILLED (exit 137) on Sept 19, 2026, and were charged a trial each for it. A strategy
            # judged on daily blocks does not need five-minute resolution, so a daily tape steps by
            # the half hour and carries fewer markets.
            step = self.settings.kalshi_day_step_seconds if horizon == "day" else 300
            markets = self.settings.kalshi_replay_markets if horizon == "hour" else min(self.settings.kalshi_replay_markets, self.settings.kalshi_day_markets)
            key = f"kalshi:{','.join(series)}:{horizon}:{step}:{markets}:{start_iso[:10]}:{','.join(under)}:{observed_timeframe}:{observed_limit}:{getattr(self.alpaca_data, 'feed', 'unknown')}"

            def build(series=series, under=under, step=step, markets=markets, start_iso=start_iso, end_iso=end_iso, horizon=horizon):
                tape = self.kalshi_data.tape(series, start=start_iso, end=end_iso, horizon=horizon, max_markets=markets, step_seconds=step)
                bars = self._underlier_bars(under, start_iso, end_iso, timeframe=observed_timeframe, warmup=observed_limit)
                if bars:
                    tape["observed_bars"] = bars
                    tape["observed_timeframe"] = observed_timeframe
                return tape
        if wanted and self.feeds is not None and not option:
            # The recorded live feeds ride on the tape (`league/feeds.py`), each row stamped with when
            # the House received it, over the window this tape was asked for. The key says whether
            # they spanned the replay gate then: a tape built before they did is not reused for a day
            # once they do.
            ready = not self._feeds_shortfall(needs, wanted, self.feeds.coverage(wanted, start, end))
            key += ":feeds:" + json.dumps(wanted, sort_keys=True, separators=(",", ":")) + (":ready" if ready else ":short")
            plain = build

            def build(plain=plain, wanted=wanted, start=start, end=end):
                tape = plain()
                tape["feeds"] = self.feeds.series(wanted, start, end, float(tape.get("step_seconds") or 300))
                tape["feeds_coverage"] = self.feeds.coverage(wanted, start, end)
                return tape
        with self._tape_lock:  # one build at a time: two agents of one family want the same tape
            hit = self._tapes.get(key)
            if hit is None or end - hit[0] > 86400:
                self._tapes[key] = (end, build())
            return key, self._tapes[key][1]

    def _live_window(self, needs: Mapping[str, Any]) -> tuple[float, float]:
        """(start, end) of the recent live tape a strategy with these NEEDS is replayed over."""
        venue, horizon, _ = niche_of(needs)
        end = self.clock()
        if venue == "kalshi":
            # The first dry run's agents asked for this themselves: one day of hourly markets is 17
            # active blocks and a week of daily ones is 7, against the 30 the replay gate needs.
            days = self.settings.kalshi_replay_days * (7 if horizon == "day" else 1)
        else:
            days = self.settings.replay_days * (6 if horizon == "day" else 1)
        return end - days * 86400, end

    @staticmethod
    def _feeds_wanted(needs: Mapping[str, Any]) -> dict[str, list[str]]:
        """The recorded live feeds these NEEDS declare, held to what the House records (`feeds.requested`)."""
        return feeds_module.requested(needs.get("feeds")) if isinstance(needs.get("feeds"), Mapping) else {}

    def _feeds_shortfall(self, needs: Mapping[str, Any], wanted: Mapping[str, Sequence[str]], coverage: Mapping[str, Any]) -> str:
        """Why the recorded feeds cannot carry a replay of these NEEDS; '' when they can. Every
        declared key must cover the replay gate's `min_blocks` blocks of the strategy's horizon inside
        the window (20 on Sept 22, 2026: twenty hours for an hourly strategy, twenty days for a daily
        one) before a replay can judge a strategy that reads it. The live feeds (`sports`, `perps` and
        the live recorders of Sept 24, 2026) are never backfilled, so that is twenty blocks of
        recording; the history feeds (`feeds.HISTORY_FEEDS`: `vol` and `funding` since Sept 23, the
        forecast, earnings and open-interest histories since Sept 24) are point-in-time history
        backfilled over the window, so they cover it as soon as the backfill is in -- and a key still
        waiting for its first page is a wait, not missing data."""
        horizon = "day" if str(needs.get("horizon") or "") == "day" else "hour"
        block = 86400.0 if horizon == "day" else 3600.0
        need = int(CONSTITUTION["ladder"]["replay"]["min_blocks"])
        rows = [(feed, key, ((coverage or {}).get(feed) or {}).get(key) or {}) for feed, keys in wanted.items() for key in keys]
        missing = [f"{feed} {key}" for feed, key, row in rows if not row.get("first_ok")]
        filling = [f"{feed} {key}" for feed, key, row in rows if not row.get("first_ok") and (row.get("backfill") or {}).get("pending")]
        if missing and filling == missing:
            return (f"{feeds_module.BACKFILLING}: " + ", ".join(filling) + " -- the House is fetching their point-in-time history "
                    "(league/feeds.py), and the replay runs once it is in. A live wake is handed ctx['feeds'] as soon as a row is.")
        if missing:
            # What the House records of the feeds these NEEDS declare (seventeen feeds since Sept 24, 2026:
            # every key of all of them would bury the answer).
            polled = {feed: (self.feeds.keys(feed) if self.feeds is not None else []) for feed in wanted}
            return ("unsupported input: feeds not recorded: " + ", ".join(missing) + "; the House records "
                    + "; ".join(f"{feed} {', '.join(keys) or 'nothing'}" for feed, keys in polled.items()))
        blocks = {f"{feed} {key}": float(row.get("covered_seconds") or 0.0) / block for feed, key, row in rows}
        have = min(blocks.values(), default=0.0)
        if have >= need:
            return ""
        since = max(str(row["first_ok"]) for _, _, row in rows)
        return (f"{feeds_module.WAITING} {since}; a replay needs {need} {horizon} blocks of them and has {have:.1f} ("
                + ", ".join(f"{name}: {value:.1f}" for name, value in blocks.items())
                + "). A live wake is handed ctx['feeds'] now; the replay waits for recorded history.")

    def _require_feeds(self, needs: Mapping[str, Any], wanted: Mapping[str, Sequence[str]], coverage: Mapping[str, Any]) -> None:
        """Raise "unsupported input" -- unavailable data, which is not a trial -- unless the recorded
        feeds these NEEDS declare can carry their replay."""
        if self.feeds is None:
            raise ValueError("unsupported input: this House records no live feeds, so NEEDS['feeds'] cannot be replayed")
        if str(needs.get("asset_class") or "") == "option":
            raise ValueError("unsupported input: the options replay tape carries no live feeds")
        short = self._feeds_shortfall(needs, wanted, coverage)
        if short:
            raise ValueError(short)

    def _history_store(self) -> Any:
        """The history store (`league.history`), read-only, or None before anything was ingested."""
        from .history import DB_NAME, HISTORY_DIR, HistoryStore

        path = self.root / HISTORY_DIR / DB_NAME
        return HistoryStore(path, readonly=True) if path.exists() else None

    def _deep_tape(self, needs: Mapping[str, Any]) -> tuple[str, dict[str, Any]] | None:
        """The development-window tape from the history store, or None when it is not all fetched
        (then the live tape is used, exactly as before). Deep tapes are cached like live ones.

        A window the store HAS fetched and holds no bars of a symbol for (it did not trade yet) is
        unsupported input, raised with that reason and never cached (Sept 24, 2026, D1's root: an
        ADA/USD development tape over 2025-09-12..2025-11-14, where the store holds ADA/USD from
        2026-02-01, was built with no steps, and the lab's step failed on it for hours). Replay,
        research coverage and the lab read `tape_for`, so each says why and none counts a trial."""
        from . import deep_replay
        from .history import series_without_bars
        from .tapes import TapeError

        store = self._history_store()
        if store is None:
            return None
        feed = getattr(self.alpaca_data, "feed", None) or "sip"
        horizon = str(needs.get("horizon") or "hour")
        days = deep_replay.dev_days(needs, self.settings.deep_replay_days or None)
        start, end = deep_replay.dev_window(horizon, days=days, holdout=self.holdout_window)
        timeframe = str((needs.get("bars") or {}).get("timeframe") or "5Min")
        warmup = int((needs.get("bars") or {}).get("limit") or 120)
        key = f"deep:alpaca:{','.join(deep_replay._symbols_of(needs))}:{timeframe}:{warmup}:{horizon}:{start}:{end}:{feed}"
        try:
            with self._tape_lock:
                hit = self._tapes.get(key)
                if hit is None or self.clock() - hit[0] > 86400:
                    empty = series_without_bars(store, deep_replay._symbols_of(needs), timeframe, start, end, feed=feed)
                    if empty:
                        raise ValueError("unsupported input: " + "; ".join(empty[:4]))
                    tape = deep_replay.dev_tape(store, needs, feed=feed, days=self.settings.deep_replay_days or None,
                                                holdout=self.holdout_window)[1]
                    if not tape.get("steps"):
                        raise ValueError(f"unsupported input: the development tape {key} has no steps: nothing was recorded in its window")
                    self._tapes[key] = (self.clock(), tape)
                return key, self._tapes[key][1]
        except TapeError:
            return None  # not fetched yet: a gap in the store is never a result against the strategy
        finally:
            store.close()

    def _holdout(self, agent: Agent, code: str, needs: Mapping[str, Any], params: Mapping[str, Any], *,
                 lineage: Sequence[str] | None = None) -> dict[str, Any]:
        """The sealed holdout, once per strategy version, rationed per lineage: the base replay
        and the double-spread one must both pass the replay gate. Pass or fail and coarse
        numbers come back; the detail stays in the private `holdout.access` row. `lineage`: the
        selection path of a candidate not in the registry yet (league/lab.py), root last."""
        from . import deep_replay

        store = self._history_store()
        if store is None:
            return {"evaluated": False, "refused": "no history store"}
        feed = getattr(self.alpaca_data, "feed", None) or "sip"
        row = CONSTITUTION["rungs"]["1"]
        stake = float(row["stake_usd"])
        limits = {"max_position_usd": float(row["max_position_usd"]), "max_order_usd": float(row["max_order_usd"])}
        lineage = list(lineage) if lineage else self.registry.lineage(agent.id)

        def run(window: tuple[str, str]) -> dict[str, Any]:
            out = {}
            for name, stress in (("base", 1.0), ("stressed", deep_replay.STRESS)):
                tape = deep_replay.holdout_tape(store, needs, feed=feed, stress=stress, holdout=window)
                done = self.sandbox.replay(agent.id, code, params, tape, stake=stake, limits=limits, timeout=self.settings.replay_timeout)
                self._charge_box(agent.id, done, note="a sealed holdout replay")
                out[name] = done.result
            return out

        def passed(results: Mapping[str, Any]) -> bool:
            return all(self.evaluator.replay_gate(agent.family, r, lineage=lineage, counted=True)[0] for r in results.values())

        try:
            # A sealed window the store holds no bars of a symbol for would be a failed run that spends
            # one of the lineage's evaluations on nothing: refused before the seal is opened. Whether a
            # symbol traded at all in the window is coverage, which `data.coverage` rows already
            # publish; no price in the window is read (Sept 24, 2026).
            from .history import series_without_bars

            timeframe = str((needs.get("bars") or {}).get("timeframe") or "5Min")
            empty = series_without_bars(store, deep_replay._symbols_of(needs), timeframe, self.holdout_window[0],
                                        self.holdout_window[1], feed=feed)
            if empty:
                return {"evaluated": False, "refused": "unsupported input: " + "; ".join(empty[:4])}
            seal = deep_replay.HoldoutSeal(self.ledger, budget=self.settings.holdout_lineage_budget, window=self.holdout_window)
            return seal.evaluate(agent=agent.id, lineage=lineage[-1] if lineage else agent.id, code=code, params=params,
                                 run=run, passed=passed)
        finally:
            store.close()

    def _underlier_bars(self, symbols: Sequence[str], start_iso: str, end_iso: str, *, timeframe: str | None = None, warmup: int = 0) -> dict[str, list[dict[str, Any]]]:
        """Bars of what a Kalshi strategy watches on Alpaca, over the same window as its tape.

        Production passes the same timeframe/limit as the live NEEDS declaration and includes
        warmup. An oversized declared window is unsupported rather than silently resampled.
        Legacy direct callers without a timeframe retain the old capacity-based choice.
        Missing bars become an explicit unsupported-input result before paid replay."""
        if not symbols or self.alpaca_data is None:
            return {}
        span = max(_epoch(end_iso) - _epoch(start_iso), 1.0)
        from .tapes import AlpacaData, TIMEFRAME_SECONDS, TapeError, iso, is_crypto

        timeframe = timeframe or next((name for name, secs in OBSERVED_BAR_SIZES if span / secs <= MAX_OBSERVED_BARS), OBSERVED_BAR_SIZES[-1][0])
        if timeframe not in TIMEFRAME_SECONDS or span / TIMEFRAME_SECONDS[timeframe] + warmup > MAX_OBSERVED_BARS:
            raise TapeError("unsupported input: declared observed timeframe exceeds the replay capacity")
        if warmup:
            reach = max(AlpacaData.default_lookback(timeframe, warmup, crypto=is_crypto(s)) for s in symbols)
            start_iso = iso(_epoch(start_iso) - reach)
        try:
            rows = self.alpaca_data.bars(list(symbols), timeframe, start=start_iso, end=end_iso, limit=MAX_OBSERVED_BARS)
        except Exception as exc:  # noqa: BLE001
            self.alert("warning", f"the underlier bars of {', '.join(symbols)} could not be recorded ({type(exc).__name__}: {str(exc)[:160]})",
                       **environment("data", exc))
            return {}
        return {s: list(bars)[-MAX_OBSERVED_BARS:] for s, bars in (rows or {}).items() if bars}

    def _run_replay(self, agent: Agent, code: str, needs: Mapping[str, Any], params: Mapping[str, Any], *,
                    scale: float = 1.0) -> tuple[dict[str, Any], str]:
        """`scale` sizes the replay's book: the practice rung's stake and caps times it (an in-place edit
        is replayed at half notional, `EDIT_REPLAY_NOTIONAL`; everything else at the practice book's)."""
        parameters.require_valid(params, needs)
        if self.campaigns and not self.pacer.may_spend("sail"):
            raise ValueError("campaign allowance is closed")
        wanted = self._feeds_wanted(needs)
        if wanted:
            # Live-only data is judged before any tape is built: until the declared feeds have been
            # recorded long enough, a strategy that reads them would be tested on nothing.
            start, end = self._live_window(needs)
            self._require_feeds(needs, wanted, self.feeds.coverage(wanted, start, end) if self.feeds is not None else {})
        tape_id, tape = self.tape_for(needs)
        if wanted:
            self._require_feeds(needs, wanted, tape.get("feeds_coverage") or {})  # what this very tape carries
        observed = needs.get("observe") or {}
        missing = [s for s in observed.get('symbols') or [] if not (tape.get('observed_bars') or {}).get(s)]
        if needs.get("venue") == "kalshi" and missing:
            raise ValueError("unsupported input: required observed bars are missing for " + ', '.join(missing)
                             + "; use replay_coverage with the candidate NEEDS to inspect each symbol")
        if needs.get("venue") == "alpaca" and observed.get("series"):
            raise ValueError("unsupported input: cross-venue event observations are not recorded on equity tapes")
        if needs.get("options_features") and str(needs.get("asset_class") or "") != "option":
            # Unavailable data, not a result: a strategy that reads a feature the House has no
            # history of would be tested on nothing. The daily job backfills what living agents ask for.
            missing = [s for s in (needs.get("symbols") or [])[:12] if not (tape.get("options_features") or {}).get(str(s).upper())]
            if missing:
                raise ValueError("unsupported input: no options-feature history for " + ", ".join(map(str, missing)))
        row = CONSTITUTION["rungs"]["1"]
        stake = float(row["stake_usd"]) * scale
        limits = {"max_position_usd": float(row["max_position_usd"]) * scale, "max_order_usd": float(row["max_order_usd"]) * scale}
        attempt = self.experiments.begin(agent=agent.id, family=agent.family,
            lineage=self.registry.lineage(agent.id), code=code, params=params, needs=needs,
            tape=tape, query=tape_id, stake=stake, limits=limits)
        try:
            run = self.sandbox.replay(agent.id, code, params, tape, stake=stake, limits=limits,
                                      timeout=self.settings.replay_timeout)
        except Exception as exc:
            self.experiments.finish(attempt, {"ok": False, "error": f"sandbox: {type(exc).__name__}"})
            raise
        self._charge_box(agent.id, run, note="a replay")
        artifact = self.experiments.finish(attempt, run.result, seconds=run.seconds)
        if (tape.get("source") or {}).get("store") == "history":
            from .deep_replay import walk_forward

            return {**run.result, "experiment": artifact, "tape_source": "history-dev",
                    "walk_forward": walk_forward(run.result, tape)}, attempt["tape"]
        return {**run.result, "experiment": artifact, "tape_source": "live"}, attempt["tape"]

    def _background(self, key: str, work: Callable[..., Any], *args: Any) -> bool:
        """Run slow work beside the tick. One job per key at a time; failures become alerts."""
        if self._closing.is_set():
            return False
        running = self._jobs.get(key)
        if running is not None and running.is_alive():
            return False

        lane_name = ("research" if key.startswith("research:") else "replay" if key.startswith("replay")
                     else "audit" if key.startswith("audit:") else "feeds" if key.startswith("feeds:")
                     else "shards" if key.startswith("shards:") else "house" if key.startswith("house:") else "ops")
        lane = self._lanes[lane_name]
        # The House's own bookkeeping runs every minute (`_house_job`): a started and a finished `ops.job`
        # row for each would be 5,760 ledger rows a day that say nothing. Its last run is in health.json
        # (`tick_steps.background.house`) and a failure is still a warning.
        rows = lane_name != "house"
        with self._state_lock:
            self._job_status[key] = {"queued_at": self.clock(), "started_at": None}

        def job() -> None:
            with lane:
                if self._closing.is_set():
                    with self._state_lock:
                        self._job_status.pop(key, None)
                    return
                queued_at = self._job_status[key]["queued_at"]
                started_at = self.clock()
                began = time.perf_counter()  # the lane's run for health.json `tick_steps.background`
                with self._state_lock:
                    self._job_status[key]["started_at"] = started_at
                job_id = f"{key}:{queued_at:.6f}"
                state = "finished"
                try:
                    if rows:
                        self.ledger.append("ops.job", {"job": job_id, "key": key, "state": "started",
                            "queued_seconds": max(0, started_at - queued_at)})
                    work(*args)
                except Exception as exc:  # noqa: BLE001
                    state = "failed"
                    try:
                        self.alert("warning", f"{key} failed ({type(exc).__name__}: {str(exc)[:200]})",
                                   **environment(key.split(":", 1)[0], exc))  # H2: GitHub, a data host, Sail
                    except Exception:  # noqa: BLE001 - the ledger may already be closed on the way out
                        pass
                finally:
                    try:
                        if rows:
                            self.ledger.append("ops.job", {"job": job_id, "key": key, "state": state,
                                "queued_seconds": max(0, started_at - queued_at),
                                "running_seconds": max(0, self.clock() - started_at),
                                "elapsed_seconds": max(0, self.clock() - queued_at)})
                    except Exception:
                        pass  # a missing finish remains visible as interrupted work after restart
                    with self._state_lock:
                        self._job_status.pop(key, None)
                        self._lane_last[lane_name] = {"key": key, "state": state, "seconds": round(time.perf_counter() - began, 3),
                                                      "at": now_iso(self.clock)}

        thread = threading.Thread(target=job, name=f"league-slow:{key}"[:60], daemon=True)
        self._jobs[key] = thread
        thread.start()
        return True

    def wait(self, timeout: float | None = None) -> None:
        """Block until the slow work in hand is done (tests use it; the run loop does not), including
        work that work in hand starts: since H5 (Sept 25, 2026) the House's research scheduling runs on
        its own lane and queues the research jobs from there, so one pass over the threads could end
        before the jobs it started had begun."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            alive = [thread for thread in list(self._jobs.values()) if thread.is_alive()]
            if not alive:
                return
            for thread in alive:
                thread.join(None if deadline is None else max(0, deadline - time.monotonic()))
            if deadline is not None and time.monotonic() >= deadline:
                return

    @staticmethod
    def _crashed(result: Mapping[str, Any]) -> str:
        """The error when the replay HARNESS failed rather than the strategy: the process was
        killed or timed out and printed no result at all. Such a run is not a hypothesis tested,
        so it is not a trial and must not deflate the agent's line (measured Sept 19, 2026: three
        agents of the sports desk were each charged a trial for a tape that exhausted its box)."""
        if result.get("ok"):
            return ""
        error = str(result.get("error") or "")
        if "timed out" in error or "Killed" in error:
            return error
        exit_code = re.search(r"no result line \(exit (-?\d+)\)", error)
        return error if exit_code and exit_code.group(1) != "0" else ""

    def _replay_own(self, agent: Agent) -> dict[str, Any]:
        """An agent's own code gets one replay, counted as a trial. For an agent on rung 0 it is
        the way up; after it, only research can change its fate."""
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None:
                return {"agent": agent.id, "skipped": "retired"}
            agent = deepcopy(self.registry.get(agent.id))
            if self._state["tried"].get(agent.id) == agent.code_sha256:
                return {"agent": agent.id, "skipped": "its code has had its replay; research may change it"}
        errors = parameters.inspect(agent.params, agent.needs)['errors']
        if errors:
            return {"agent": agent.id, "skipped": "invalid parameters", "errors": errors}
        try:
            result, tape_id = self._run_replay(agent, agent.code, agent.needs, agent.params)
        except Exception as exc:  # noqa: BLE001 - no tape or no box: try again next wake
            if str(exc).startswith((feeds_module.WAITING, feeds_module.BACKFILLING)):
                # Recorded feeds that do not span the replay gate yet, or a backfill not yet in, are a
                # wait, not a defect: said once a day an agent, and never as "replay could not run",
                # which the foundry counts against the line as missing data
                # (`hypotheses._retire_unrunnable`: five such hours retire it).
                if self.clock() - self._feeds_waiting.get(agent.id, float("-inf")) >= 86400:
                    self._feeds_waiting[agent.id] = self.clock()
                    self.alert("info", f"{agent.id}: its replay waits for recorded feeds ({str(exc)[:200]})")
                return {"agent": agent.id, "skipped": "waiting for recorded feeds"}
            if isinstance(exc, SandboxError):
                # Sail did not answer (or the box was busy): the House's infrastructure, not the
                # strategy. Worded so `hypotheses._retire_unrunnable` does not count it against the
                # line, and it is not a trial; the next wake tries again.
                self.alert("warning", f"{agent.id}: its replay box did not answer, infrastructure and not a trial "
                                      f"({type(exc).__name__}: {str(exc)[:200]})", **environment("sail", exc))
                return {"agent": agent.id, "skipped": "replay box unavailable (infrastructure)"}
            self.alert("warning", f"{agent.id}: replay could not run ({type(exc).__name__}: {str(exc)[:200]})")
            return {"agent": agent.id, "skipped": "replay unavailable"}
        crash = self._crashed(result)
        if crash:
            self.alert("warning", f"{agent.id}: its replay was not run ({crash[:160]}); it is not counted as a trial and will be tried again")
            return {"agent": agent.id, "skipped": f"the replay could not be run: {crash[:120]}"}
        # A pass on the history store's development window is promoted only once the sealed
        # holdout agrees (`_holdout`); the live tape's pass is promoted as it always was.
        sealed = self.settings.holdout_gate and result.get("tape_source") == "history-dev"
        with self._lifecycle_lock:
            current = self._generation(agent.id) == generation
            if current:
                with self._state_lock:
                    self._state["tried"][agent.id] = agent.code_sha256
            # A stale replay still consumed a trial, but cannot qualify or mark a replacement
            # strategy as tested. Its captured code and parameters remain on the trial row.
            verdict = self.evaluator.record_trial(agent.id, agent.family, result, tape_id=tape_id,
                                                  promote=current and not sealed, lineage=self.registry.lineage(agent.id))
            if verdict.decision == "promote":
                self.seat(self.registry.get(agent.id))
        holdout = None
        if sealed and current and verdict.numbers.get("passed") and self.evaluator.rung(agent.id) == 0:
            holdout = self._holdout(agent, agent.code, agent.needs, agent.params)  # slow: outside the lock
            redundant = None
            with self._lifecycle_lock:
                if holdout.get("passed") and holdout.get("evaluated") and self._generation(agent.id) == generation \
                        and self.evaluator.rung(agent.id) == 0:
                    verdict = self.evaluator.promote(agent.id, 1, "passed deep replay and the sealed holdout",
                                                     {**verdict.numbers, "holdout": holdout})
                    self.seat(self.registry.get(agent.id))
                elif self._generation(agent.id) == generation:
                    # A development pass the holdout did not admit must say why, or the agent sits on
                    # rung 0 with a passing trial and nothing to act on (mcentee-32 and -33, Sept 22,
                    # 2026: the lineage's three holdout evaluations were spent by clones of their own
                    # code, and their code was marked as tried).
                    reason = (f"its development replay passed, but the sealed holdout refused it: {holdout.get('refused')}"
                              if not holdout.get("evaluated") else "its development replay passed, but the sealed holdout did not")
                    self.ledger.append("eval.verdict", {"decision": "progress", "rung": 0, "stage": "holdout",
                                                        "reason": reason, "holdout": holdout}, agent=agent.id)
                    if not holdout.get("evaluated"):
                        # The same program already holding a seat on paper makes this one a clone: it
                        # cannot add evidence the sibling is not already gathering, and it holds a seat.
                        redundant = next((a for a in self.registry.living() if a.id != agent.id and a.code_sha256 == agent.code_sha256
                                          and self.evaluator.rung(a.id) >= 1), None)
            if redundant is not None:
                self.kill(agent, "redundant", f"{reason}; the same program already trades on paper as {redundant.id}",
                          expected_generation=generation)
        out = {"agent": agent.id, "replay": verdict.decision, "reasons": verdict.numbers.get("reasons")}
        if holdout is not None:
            out["holdout"] = holdout
        return out

    def _candidate_replay(self, agent: Agent, code: str, *, lineage: Sequence[str] | None = None) -> dict[str, Any]:
        """The researcher's `replay` tool: a counted trial of candidate code, never a promotion.
        `lineage`: the selection path of a candidate not in the registry yet (league/lab.py)."""
        try:
            described = self.sandbox.needs(PROBE_BOX, code)
        except SandboxError as exc:
            # The probe box did not answer: infrastructure, never a trial and never the candidate's
            # outcome (`hypotheses.evaluate` leaves its card pending for another attempt).
            return {"counted_as_trial": False, "passed": False, "infrastructure": True, "numbers": {},
                    "error": f"the House's probe box did not answer (infrastructure, NOT a trial against you): "
                             f"{type(exc).__name__}: {str(exc)[:200]}"}
        self._charge_box(agent.id, described, note="reading a candidate's NEEDS")
        info = described.result
        if not info.get("ok"):
            return {"counted_as_trial": False, "passed": False, "error": info.get("error"), "numbers": {}}
        try:
            venue, horizon, _ = niche_of(info["needs"])
            if (venue, horizon) != (agent.venue, agent.horizon):
                return {"counted_as_trial": False, "passed": False, "error": "a candidate must stay on your venue and horizon", "numbers": {}}
            niche = self.niche_of(agent)
            if niche is not None:
                info["needs"] = niches_module.constrain(info["needs"], niche)
            parameters.require_valid(info.get("params") or {}, info["needs"])
            if niche is not None and not self._replayable(niche, info["needs"]):
                # No history to walk: the candidate must at least decide on what its parent sees now.
                # It is not a counted trial and proves no edge; its child answers on paper.
                book = self.book_of(agent)
                candidate_agent = deepcopy(agent)
                candidate_agent.code, candidate_agent.needs = code, info["needs"]
                candidate_agent.params = dict(info.get("params") or {})
                ctx = self.snapshot(candidate_agent, book) if book is not None else None
                run = self.sandbox.decide(agent.id, code, ctx) if ctx is not None else None
                if run is not None:
                    self._charge_box(agent.id, run, note="a candidate's smoke run")
                ok = bool(run is not None and run.result.get("ok"))
                # On a weekend an options desk is handed an empty view, and code that only ever
                # answered "the session is closed" has proved nothing at all -- not even that it
                # runs on the path that matters. Say so, rather than let a pass be read as one.
                blind = ok and ctx is not None and self._offered(agent, ctx) == 0
                note = ("this specialty has no replay, and its market is shut: this run proved only that your code does not "
                        "raise on an empty view. Nothing about its edge, and nothing about what it does when there is "
                        "something to trade, has been tested. Paper, when the market opens, is the first real test."
                        if blind else "this specialty has no replay: paper is the test")
                return {"counted_as_trial": False, "passed": ok, "error": None if ok else (run.result.get("error") if run else "no book"), "needs": info["needs"], "params": info.get("params") or {},
                        "numbers": {"passed": ok, "untested": blind, "reasons": [] if ok else ["it did not run on the live view"], "note": note}}
            result, tape_id = self._run_replay(agent, code, info["needs"], info.get("params") or {})
        except Exception as exc:  # noqa: BLE001
            return {"counted_as_trial": False, "passed": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "numbers": {},
                    **({"infrastructure": True} if isinstance(exc, SandboxError) else {})}
        crash = self._crashed(result)
        if crash:
            self.alert("warning", f"{agent.id}: a candidate's replay was not run ({crash[:160]}); it is not counted as a trial")
            return {"counted_as_trial": False, "passed": False, "error": f"the replay could not be run and is NOT a trial against you: {crash[:160]}. "
                                              "Ask for a smaller question of the tape, or tell the House with `request_tool`.",
                    "numbers": {}, "needs": info["needs"], "params": info.get("params") or {}}
        verdict = self.evaluator.record_trial(agent.id, agent.family, result, tape_id=tape_id, promote=False,
                                              lineage=list(lineage) if lineage else self.registry.lineage(agent.id))
        out = {"counted_as_trial": True, "passed": bool(verdict.numbers.get("passed")), "numbers": verdict.numbers, "needs": info["needs"], "params": info.get("params") or {},
               "digest": result.get("digest")}
        if result.get("tape_source") == "history-dev":
            # Development history, fold by fold. A pass here still needs the sealed holdout to be
            # promoted, and nothing about the holdout is ever shown.
            out["walk_forward"] = result.get("walk_forward") or []
            out["note"] = "replayed on the development window before the sealed holdout; promotion also needs the holdout"
        return out

    def _edit_replay(self, agent: Agent, changes: Mapping[str, Any], *, session: str = "") -> dict[str, Any]:
        """The researcher's `edit_params` (X1, Sept 24, 2026): replay an in-place parameter edit.

        The agent keeps its seat, its record and its code; only numeric PARAMS that `parameters.inspect`
        lists as mutable change, each inside its bounds. The House replays the code with the edited
        PARAMS first, on a book of half the practice stake and caps (`EDIT_REPLAY_NOTIONAL`), on the
        tape its replays use -- the development window, never the sealed holdout -- and judges it by
        the replay gate against the line's trials with this look, and every earlier edit look of the
        line, counted in the deflation (`evaluator.replay_gate`, counted=False, `looks`). It records no
        `eval.trial` and spends none of the line's holdout evaluations. One such replay an agent a day
        (`EDIT_REPLAY_EVERY_SECONDS`), passed or not, recorded as an `agent.research` row (tool
        "edit_replay", read in full by `_edit_looks`), so the look that is no trial cannot be
        repeated into a lucky one. A passing edit is applied when the pass ends (`_apply_controls`);
        this changes nothing itself.

        Returns {"passed", "reasons", "params", "was", "code_sha256", "numbers"}, or {"error"} for an
        edit refused before any replay (or a replay that could not run, which is no look)."""
        with self._lifecycle_lock:
            current = self.registry.get(agent.id)
            if current is None or not current.alive:
                return {"error": "the agent is no longer alive"}
            if (current.code_sha256, current.params, current.needs) != (agent.code_sha256, agent.params, agent.needs):
                return {"error": "your strategy changed during this pass: look at it again before you edit it"}
            if self.evaluator.rung(current.id) < 1:
                return {"error": "on rung 0 a replay is the way up: submit the edited file with `replay` (a counted trial)"}
            refusal = self._control_refusal(current, "edit_params")
            if refusal:
                return {"error": refusal}
            current = deepcopy(current)
        lineage = self.registry.lineage(current.id)
        looks = self._edit_looks(lineage)
        last = next((e for e in reversed(looks) if e.agent == current.id), None)
        if last is not None and self.clock() - _epoch(last.at) < EDIT_REPLAY_EVERY_SECONDS:
            return {"error": f"one in-place edit replay a day, passed or not: your last was at {last.at}; "
                             f"the next may run from {now_iso(lambda: _epoch(last.at) + EDIT_REPLAY_EVERY_SECONDS)}"}
        rules = parameters.inspect(current.params, current.needs)
        errors, edited = [], dict(current.params)
        for key, value in dict(changes).items():
            if key not in current.params:
                errors.append(f"{key} is not one of your PARAMS")
            elif key not in rules["mutable"]:
                errors.append(f"{key} is not a bounded, unfrozen numeric knob (parameter_validation.mutable lists those)")
            elif type(value) not in (int, float) or not math.isfinite(value):
                errors.append(f"{key} must be a number")
            elif type(current.params[key]) is int and float(value) != int(value):
                errors.append(f"{key} is a whole number")
            else:
                edited[key] = int(value) if type(current.params[key]) is int else float(value)
        if errors:
            return {"error": "; ".join(errors)}
        if edited == current.params:
            return {"error": "nothing changed: give the knobs you change and their new values"}
        checked = parameters.inspect(edited, current.needs)
        if not checked["valid"]:
            return {"error": "invalid parameters: " + "; ".join(checked["errors"])}
        niche = self.niche_of(current)
        if niche is not None and not self._replayable(niche, current.needs):
            return {"error": "this specialty has no replay to judge an edit by: an edit here waits for one"}
        try:
            result, tape_id = self._run_replay(current, current.code, current.needs, edited, scale=EDIT_REPLAY_NOTIONAL)
        except Exception as exc:  # noqa: BLE001 - a replay that cannot run is no look, and changes nothing
            return {"error": f"the edit's replay could not run (not a look; nothing changed): {type(exc).__name__}: {str(exc)[:200]}"}
        crash = self._crashed(result)
        if crash:
            return {"error": f"the edit's replay was not run (not a look; nothing changed): {crash[:160]}"}
        # This look, and every earlier edit look of the line (no `eval.trial` records them), are tries in
        # the deflation: one look a day, but not each one judged as if it were the first.
        passed, reasons, growth, sharpe, deflated, trials, oos = self.evaluator._replay_reasons(
            current.family, result, lineage, counted=False, looks=[e.payload.get("sharpe") for e in looks])
        numbers = {"trades": int(result.get("trades") or 0), "blocks": len(growth), "sharpe": sharpe, "trials": len(trials),
                   "deflated_sharpe": None if deflated is None else deflated["dsr"], "return_pct": result.get("return_pct"),
                   "max_drawdown": result.get("max_drawdown"), "oos_mean_log_growth": oos.get("mean_log_growth"),
                   "fees_usd": result.get("fees_usd"), "tape": tape_id, "tape_source": result.get("tape_source"),
                   "stake_usd": float(CONSTITUTION["rungs"]["1"]["stake_usd"]) * EDIT_REPLAY_NOTIONAL}
        self.ledger.append("agent.research", {"tool": "edit_replay", "session": session, "passed": passed, "reasons": reasons,
                                              "params": edited, "was": dict(current.params), **numbers}, agent=current.id)
        return {"passed": passed, "reasons": reasons, "params": edited, "was": dict(current.params),
                "code_sha256": current.code_sha256, "numbers": numbers}

    def _edit_looks(self, agent_ids: Sequence[str]) -> list[Any]:
        """Every in-place edit replay (`edit_replay` rows) of these agents, oldest first: the one-a-day
        rule and the deflation read them. Read in full, never from a window of the newest rows: an
        agent writes up to 1,700 `agent.research` rows a day, and on the T0 snapshot of the close-the-
        gaps run 26 of 487 agents wrote 400 inside a day (meriwether-37 in 2.8 hours), so a window of
        400 lost the day's look and let a second one run (review of #249). The busiest agent's whole
        research record decodes in about 20 ms."""
        looks = [entry for agent_id in dict.fromkeys(agent_ids) for entry in self.ledger.iter(kinds="agent.research", agent=agent_id)
                 if entry.payload.get("tool") == "edit_replay"]
        return sorted(looks, key=lambda entry: entry.seq)

    # ----------------------------------------------------------------- judging
    def judge(self, agent: Agent) -> Verdict | None:
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None:
                return None
            book = self.book_of(agent)
            rung = self.evaluator.rung(agent.id)
            if book is None or rung < 1:
                return None
            self.evaluator.observe(agent.id, book.name, agent.horizon)
            peers = [a.id for a in self.registry.agents.values() if a.family == agent.family and a.venue == agent.venue and a.id != agent.id]
            verdict = self.evaluator.judge(agent.id, book.name, peers=peers if rung == 2 else (), family=agent.family, horizon=agent.horizon)
            if verdict.decision != 'eligible' and not allocator_module.enabled():
                # Under the allocator its own statuses are the only ones (two writers alternated a
                # `progress` row every pass for every waiting agent, Sept 23, 2026 review).
                self._promotion_status(agent, verdict, 'evidence', verdict.reason)
            fall = (CONSTITUTION["ladder"].get("micro_demotion") or {}).get("max_loss")
            allocated = allocator_module.enabled()
            if allocated and verdict.decision == "eligible":
                # Capital is the ladder: the screen and the micro bound no longer promote. The
                # allocator moves bands from evidence at the end of this mark pass; death, drift
                # and replay stay where they were.
                verdict = Verdict(verdict.agent, verdict.rung, "hold", "the allocator decides bands from evidence", verdict.numbers)
            if verdict.decision not in ("die", "eligible") and rung == 2 and fall and not allocated:
                # The fast lane: a live micro agent down this much since promotion goes back to paper.
                import math
                rows = self.evaluator.blocks(agent.id, since_seq=self.evaluator._rung_entered(agent.id), book=book.name)
                change = math.exp(max(sum(float(r["log_growth"]) for r in rows), -700.0)) - 1.0
                if rows and change <= -float(fall):
                    demoted = self.evaluator.demote(agent.id, f"down {-change:.1%} on real money since promotion; "
                                                    f"micro-real keeps no agent down {float(fall):.0%}: back to paper to earn it again",
                                                    {"change": change, "blocks": len(rows)})
                    self._move_books(agent, book)
                    return demoted
            if verdict.decision not in ("die", "eligible") and rung >= 2:
                drift = self.evaluator.drift(agent.id, book.name, agent.horizon)
                if drift.decision == "demote":
                    if allocated and self.evaluator.rung(agent.id) >= 2:
                        self.seat(agent)  # a swing drifting to a bunt keeps its book: the stake follows, nothing is sold
                    else:
                        self._move_books(agent, book)
                    return drift
        if rung == 2 and verdict.decision != "die" and self.auditor is not None:
            # Audit after promotion: an audit that finished before a restart is committed, and
            # one that is owed (never run, or it could not run) is started.
            self._settle_after_audit(agent, generation)
        if verdict.decision == "die":
            self.kill(agent, "evidence", verdict.reason, expected_generation=generation)
        elif verdict.decision == "eligible":
            self._promote(agent, verdict, expected_generation=generation)
        return verdict

    def _promotion_status(self, agent: Agent, verdict: Verdict, stage: str, reason: str, **detail) -> None:
        """Persist why the next transition waits; passing a screen must never disappear silently."""
        row = {'at': now_iso(self.clock), 'agent': agent.id, 'rung': verdict.rung,
               'target_rung': verdict.rung + 1, 'code_sha256': agent.code_sha256,
               'stage': stage, 'reason': reason,
               'evidence': {k: verdict.numbers[k] for k in ('active_blocks', 'episodes', 'via', 'trades', 'recent_drawdown', 'mean', 'lcb')
                            if k in verdict.numbers}, **detail}
        from .preaudit import mark_of

        with self._state_lock:
            mark = mark_of(self._state, agent)
        if mark:
            # The pre-audit's finding rides along with every status, so a broken strategy is seen
            # (by the agent's research packet and the site) as needing a corrected child.
            row['pre_audit'] = {k: mark.get(k) for k in ('verdict', 'flags', 'repair_key')}
        with self._state_lock:
            states = self._state.setdefault('promotion_status', {})
            old = states.get(agent.id) or {}
            states[agent.id] = row
        if any(old.get(k) != row.get(k) for k in ('stage', 'reason', 'code_sha256')):
            self.ledger.append('eval.verdict', {'decision': 'progress', **row}, agent=agent.id)

    def _promote(self, agent: Agent, verdict: Verdict, *, expected_generation: tuple | None = None) -> None:
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None or (expected_generation is not None and generation != expected_generation):
                return
            agent = deepcopy(self.registry.get(agent.id))
            rung = self.evaluator.rung(agent.id)
            if rung != verdict.rung:
                return
            if self.paused():
                self._promotion_status(agent, verdict, 'paused', 'the House is paused for maintenance; promotions wait')
                return
            source_book = self.book_of(agent)
            if rung >= 1 and source_book is not None and not source_book.evidence_integrity(agent.id)['ok']:
                self._promotion_status(agent, verdict, 'accounting_integrity',
                    'the source record contains an unresolved position attribution defect',
                    accounting=source_book.evidence_integrity(agent.id))
                return
            if rung >= 1 and self.campaigns and not self.campaigns.allows_live(rung + 1):
                self._promotion_status(agent, verdict, 'campaign',
                    'the campaign has not released this live rung; a screen pass alone cannot allocate money')
                return
            if rung == 1:
                if not self.settings.real_money or REAL_BOOK[agent.venue] not in self.books:
                    self._promotion_status(agent, verdict, 'live_book', 'the live venue is not enabled')
                    return  # it stays eligible on paper until the owner turns real money on
                state = self.tuition()
                pilot = self.campaigns.live_authorization() if self.campaigns else None
                verdict = Verdict(verdict.agent, verdict.rung, verdict.decision, verdict.reason,
                    {**verdict.numbers, 'allocation_context': {
                        'tuition': {'max_loss_usd': str(state['limit_usd']), 'max_agents': state['max_agents']},
                        'headroom_usd': str(state['headroom_usd']), 'seated': state['seated'],
                        'live_pilot': pilot}})
                if not state["room"] or (pilot and pilot['policy'].get('venue_capital_usd')
                                         and not self.tuition(agent.venue)['room']):
                    self._promotion_status(agent, verdict, 'tuition', 'the aggregate micro risk budget has no free stake',
                                           headroom_usd=str(state['headroom_usd']))
                    if not self._state.get("tuition_told"):
                        self._state["tuition_told"] = True
                        self.alert("warning", f"{agent.id} cleared the paper screen and was not promoted: the micro rung has "
                                              f"{state['seated']} of {state['max_agents']} agents seated and ${state['headroom_usd']:.2f} of "
                                              f"headroom under its ${state['limit_usd']} tuition. It waits on paper.")
                    return
                self._state["tuition_told"] = False
                if self.auditor is None:
                    self._promotion_status(agent, verdict, 'audit_unavailable', 'the production auditor is unavailable')
                    return
                inflight = self._audit_inflight(agent.id, generation)
                if inflight == "running":
                    return  # one audit at a time: the job in hand commits its own result
                if inflight is None:
                    wait = self._audit_wait(agent)
                    if wait:
                        self._promotion_status(agent, verdict, **wait)
                        return
                    if self._audit_after() and self._known_defect(agent) is None:
                        self._promote_then_audit(agent, verdict, source_book)
                        return
                    self._promotion_status(agent, verdict, 'auditing', 'a fresh production audit is in progress')
                    self._start_audit(agent, verdict, generation)
                    return
        if rung == 1:
            # An audit that finished before a restart and never reached its commit: its verdict
            # is on the ledger, bound to this very generation, so it is committed, not bought again.
            self._finish_audit(agent.id, verdict, generation, inflight)
            return
        self._commit_promotion(agent.id, verdict, rung, generation)

    # ------------------------------------------------------------------ audits
    # The audit is a frontier call of up to ~570 s. It used to run inline in `_promote`, which is
    # called from `judge`, which the tick calls in its mark pass: one audit stalled every wake of
    # the floor for up to ten minutes, real-money exits included. It now runs as a background job
    # with the generation checked before and after; its "auditing" status and the generation it is
    # bound to are persisted, so a restart neither loses an approval nor pays for a second audit.
    AUDITS = "audits"

    def _audit_inflight(self, agent_id: str, generation: tuple) -> Any:
        """"running" while this process audits the agent; the recorded verdict when an audit of
        this exact generation finished before a restart and its commit never happened; else None.
        A record for another generation, or one whose audit left no verdict (the process died
        mid-call), is dropped: the next eligible screen is audited afresh."""
        job = self._jobs.get(f"audit:{agent_id}")
        if job is not None and job.is_alive():
            return "running"
        with self._state_lock:
            record = (self._state.get(self.AUDITS) or {}).get(agent_id)
        if not record:
            return None
        if list(record.get("generation") or []) != list(generation):
            self._drop_audit(agent_id)
            return None
        # A family swing's verdict (`family_swing`) is written against one member but is the family's, never this
        # agent's own audit (review of #242, Sept 24, 2026).
        verdicts = [e for e in self.ledger.iter(kinds="audit.verdict", agent=agent_id, after=int(record.get("since_seq") or 0))
                    if not e.payload.get("family_swing")]
        if not verdicts:
            self._drop_audit(agent_id)
            return None
        return {**verdicts[-1].payload, "resumed_from_seq": verdicts[-1].seq}

    def _drop_audit(self, agent_id: str) -> None:
        with self._state_lock:
            (self._state.get(self.AUDITS) or {}).pop(agent_id, None)

    def _audit_after(self) -> bool:
        """The constitution's audit timing (`ladder.paper.audit`, owner revision of Sept 23, 2026):
        "after" promotes a screen-passer to the micro rung at once and audits it there."""
        return str(CONSTITUTION["ladder"]["paper"].get("audit", "before")) == "after"

    def _promote_then_audit(self, agent: Agent, verdict: Verdict, source_book: Book | None) -> None:
        """Audit AFTER, not before (called under the lifecycle lock, once the screen, accounting,
        the campaign, the live venue and the capital envelope have all passed, and no veto's
        cooldown is running). The agent takes the micro stake now; the frontier audit runs on the
        record that earned it, and a veto sends it straight back to paper (`_finish_audit`)."""
        numbers = {**verdict.numbers, "audit_timing": "after"}
        promoted = Verdict(verdict.agent, verdict.rung, verdict.decision, verdict.reason, numbers)
        self.evaluator.promote(agent.id, verdict.rung + 1, verdict.reason + "; the frontier audit follows on the micro rung", numbers)
        self._promotion_status(agent, promoted, 'promoted', 'the screen and allocation gates passed; the frontier audit follows on the micro rung')
        if source_book is not None:
            self._move_books(agent, source_book)
        generation = self._generation(agent.id)
        if generation is not None:
            self._start_audit(agent, promoted, generation, after=True)

    def _audit_owed(self, agent: Agent) -> dict[str, Any] | None:
        """The promotion row of a micro agent promoted under audit-after whose audit has not yet
        reached a verdict (a restart, or an audit that could not run), else None."""
        entered = self.evaluator._rung_entered(agent.id)
        promotion = next((e for e in self.ledger.iter(kinds="eval.verdict", agent=agent.id, after=entered - 1)
                          if e.seq == entered), None)
        if promotion is None or promotion.payload.get("decision") != "promote" or promotion.payload.get("audit_timing") != "after":
            return None
        if any(not e.payload.get("error") and not e.payload.get("family_swing")
               for e in self.ledger.iter(kinds="audit.verdict", agent=agent.id, after=entered)):
            return None
        return dict(promotion.payload)

    def _settle_after_audit(self, agent: Agent, generation: tuple) -> None:
        """On the micro rung: commit an after-audit that finished before a restart, or start one
        that is owed (called from `judge`, outside the lifecycle lock)."""
        inflight = self._audit_inflight(agent.id, generation)
        if inflight == "running":
            return
        if self.paused() and not isinstance(inflight, dict):
            return  # a maintenance pause stops paid work, an owed audit included; it runs after
        owed = self._audit_owed(agent) if not isinstance(inflight, dict) else None
        if not isinstance(inflight, dict) and owed is None:
            return
        numbers = {k: v for k, v in (owed or {}).items() if k not in ("decision", "from_rung", "to_rung", "reason")}
        verdict = Verdict(agent.id, 1, "eligible", "the micro promotion's audit (audit after promotion)", {**numbers, "audit_timing": "after"})
        if isinstance(inflight, dict):
            with self._state_lock:
                record = (self._state.get(self.AUDITS) or {}).get(agent.id) or {}
            if record.get("after"):
                self._finish_audit(agent.id, verdict, generation, inflight)
            return
        if self._audit_wait(agent) is not None:
            return  # an audit that could not run waits out the short error cooldown
        with self._lifecycle_lock:
            if self._generation(agent.id) == generation:
                self._start_audit(agent, verdict, generation, after=True)

    def _known_defect(self, agent: Agent) -> str | None:
        """Why an agent's code is known to be defective, or None: a red pre-audit, or a merged
        corrected child of its code. Such an agent is audited BEFORE any promotion, never after."""
        from . import strategies
        from .preaudit import mark_of

        with self._state_lock:
            mark = mark_of(self._state, agent)
        if mark and mark.get("verdict") == "red":
            return f"the pre-audit found {', '.join(mark.get('flags') or []) or 'a defect'}"
        for row in strategies.all_strategies():
            if isinstance(row.get("repair"), Mapping) and any(agent.code_sha256.startswith(s) for s in self._defective_shas(row)):
                return f"the merged repair {row['name']} corrects its code"
        return None

    def _start_audit(self, agent: Agent, verdict: Verdict, generation: tuple, *, after: bool = False) -> None:
        """Persist the audit before dispatching it (called under the lifecycle lock)."""
        with self._state_lock:
            self._state.setdefault(self.AUDITS, {})[agent.id] = {
                "generation": list(generation), "since_seq": self.ledger.head()[0], "at": now_iso(self.clock),
                "rung": verdict.rung, "code_sha256": agent.code_sha256, "after": bool(after)}
        self._save_state()
        if not self._background(f"audit:{agent.id}", self._run_audit, agent.id, verdict, generation):
            self._drop_audit(agent.id)  # closing: the next process audits it afresh

    def _audit_charges_agent(self) -> bool:
        """Who pays for a promotion audit. From Sept 23, 2026 the House does (`game.json`
        `audit.house_pays`): hawkins cleared the screen on Sept 22 and waited at "cannot cover its
        audit and operating credit floor", a paper agent's purse deciding whether real money looks at it."""
        return not bool((self.game.get("audit") or {}).get("house_pays", False))

    def _call_auditor(self, agent: Agent, verdict: Verdict) -> Mapping[str, Any]:
        """The audit, telling an auditor that takes `charge` who pays (a stand-in may not take it)."""
        import inspect

        try:
            takes_charge = "charge" in inspect.signature(self.auditor.audit).parameters
        except (TypeError, ValueError):
            takes_charge = False
        if takes_charge:
            return self.auditor.audit(agent, verdict, charge=self._audit_charges_agent())
        return self.auditor.audit(agent, verdict)

    def _run_audit(self, agent_id: str, verdict: Verdict, generation: tuple) -> None:
        with self._lifecycle_lock:
            if self._generation(agent_id) != generation:
                self._drop_audit(agent_id)
                return  # retired, rewritten or moved while it waited for a lane
            agent = deepcopy(self.registry.get(agent_id))
        try:
            audit = self._call_auditor(agent, verdict)  # the provider never holds the lifecycle lock
        except Exception as exc:  # noqa: BLE001 - an auditor that raises has not audited
            # Recorded the way the auditor records its own failures, so the short error cooldown
            # applies: otherwise a broken audit is retried at every mark pass, five minutes apart.
            audit = {"approve": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                     "summary": "the audit could not run; the agent stays on paper"}
            self.ledger.append("audit.verdict", {**audit, "policy_digest": getattr(self.auditor, "policy_digest", None)}, agent=agent_id)
        self._finish_audit(agent_id, verdict, generation, audit)

    def _finish_after_audit(self, agent_id: str, verdict: Verdict, generation: tuple, audit: Mapping[str, Any]) -> None:
        """The verdict on an agent already on the micro rung: a veto sends it back to paper; an
        audit that could not run leaves it trading and is owed again after the error cooldown."""
        with self._lifecycle_lock:
            if self._generation(agent_id) != generation:
                return  # demoted, retired or rewritten while it was audited: nothing to act on
            agent = self.registry.get(agent_id)
            if audit.get("approve"):
                self._promotion_status(agent, verdict, 'audit_confirmed', 'the frontier audit confirmed the micro promotion')
                return
            if audit.get("error"):
                self._promotion_status(agent, verdict, 'audit_retry',
                                       f"the audit could not run ({str(audit.get('error'))[:120]}); it trades the micro stake "
                                       "and is audited again after the short cooldown")
                return
            old = self.book_of(agent)
            summary = str(audit.get("summary") or "the audit did not approve")[:300]
            self.evaluator.demote(agent_id, f"the frontier audit after promotion vetoed it: {summary}",
                                  {"audit_timing": "after", "findings": [f.get("issue") for f in audit.get("findings") or []][:5]})
            if old is not None:
                self._move_books(agent, old)
            self._promotion_status(agent, verdict, 'audit_veto', summary)

    def _finish_audit(self, agent_id: str, verdict: Verdict, generation: tuple, audit: Mapping[str, Any]) -> None:
        with self._state_lock:
            after = bool(((self._state.get(self.AUDITS) or {}).get(agent_id) or {}).get("after"))
        if after:
            try:
                self._finish_after_audit(agent_id, verdict, generation, audit)
            finally:
                self._drop_audit(agent_id)
                self._save_state()
            return
        try:
            if not audit.get("approve"):
                agent = self.registry.get(agent_id)
                if agent is not None:
                    self._promotion_status(agent, verdict, 'audit_veto', str(audit.get('summary') or audit.get('error') or 'audit did not approve'))
                return  # it stays on paper, where its record is the auditor's counterfactual
            # The rung the audit was asked for: 1 -> 2 on the old ladder (and for a known defect under
            # the allocator), 2 -> 3 for the allocator's first entry into the swing band.
            self._commit_promotion(agent_id, verdict, int(verdict.rung or 1), generation)
        finally:
            self._drop_audit(agent_id)
            self._save_state()

    def _commit_promotion(self, agent_id: str, verdict: Verdict, rung: int, generation: tuple) -> None:
        """The gates again after the audit, exactly as before it moved off the tick."""
        with self._lifecycle_lock:
            if self._generation(agent_id) != generation:
                return
            agent = self.registry.get(agent_id)
            paused = self.registry.entries_paused(agent_id)
            if paused:
                # It paused its entries while it was audited (X1): a paused agent is promoted to no real
                # band (review of #249, P2); the allocator weighs it again once it resumes.
                self._promotion_status(agent, verdict, 'paused', f"its entries were paused (since {paused.get('since')}) when "
                                                                 "the audit finished: a paused agent is not promoted")
                return
            source_book = self.book_of(agent)
            if rung >= 1 and source_book is not None and not source_book.evidence_integrity(agent.id)['ok']:
                self._promotion_status(agent, verdict, 'accounting_integrity',
                    'position attribution changed during the audit; the source record requires repair',
                    accounting=source_book.evidence_integrity(agent.id))
                return
            if rung >= 1 and self.campaigns and not self.campaigns.allows_live(rung + 1):
                self._promotion_status(agent, verdict, 'campaign', 'the live allocation window closed during the audit')
                return
            if rung == 2 and allocator_module.enabled() and not self.allocator.swing_allowed(agent):
                # Only a proven family's agent swings (Sept 24, 2026; the constitution's
                # `allocator.swing_requires_proven_family` since Deploy B): a swing audit that finishes after its
                # family's record stopped being proven does not commit (`Allocator.family` never raises).
                self._promotion_status(agent, verdict, 'family', "its family's pooled record is not proven: "
                                                                  "only a proven family's agent swings")
                return
            authorization = self.campaigns.live_authorization() if self.campaigns else None
            if rung == 1 and allocator_module.enabled():
                # A known defect's bunt, committed after its audit: the allocator's envelope decides.
                if self.allocator.refuses_probe(agent, verdict): return  # R5 (Sept 24, 2026): the probe gate again after the audit
                if self.allocator.headroom(agent.venue) < self.allocator.target_stake(agent, "bunt"):
                    self._promotion_status(agent, verdict, 'envelope', 'the envelope has no room for the bunt the audit approved')
                    return
            elif rung == 1 and (not self.tuition()["room"] or
                    (authorization and authorization['policy'].get('venue_capital_usd')
                     and not self.tuition(agent.venue)['room'])):
                self._promotion_status(agent, verdict, 'tuition', 'another admission used the available micro stake')
                return
            agent = self.registry.get(agent.id)
            old = self.book_of(agent)
            self.evaluator.promote(agent.id, rung + 1, verdict.reason, verdict.numbers)
            self._promotion_status(agent, verdict, 'promoted', 'the screen, audit and allocation gates passed')
            if rung == 1 and old is not None:
                self._move_books(agent, old)

    def _recover_consults(self) -> None:
        # On a copy: `_save_state` must never see the dict change in the middle of its dump.
        from .consult_recovery import STATE_KEY

        with self._state_lock:
            state = dict(self._state.get(STATE_KEY) or {})
        self.consult_recovery.run(state)
        with self._state_lock:
            self._state[STATE_KEY] = state

    def _run_backup(self) -> None:
        """One backup, and what the House says about it (`Backup.notice`, H2, Sept 25, 2026): a Sail outage is ONE error
        when it begins, a warning at each later backoff step and an info with its length when it ends, all marked
        `environment: "sail"`, which the watchdog never rolls a release back for; a failure of the House's own code is an
        unmarked error each time, with `began_at` (Sept 24) so one that began before a promotion is inherited. A failure
        that came back while the House was shutting down is a warning, and a backup the shutdown cut off (`close`)
        writes nothing: its thread dies with the process, or finds the ledger closed."""
        before = self.backup.failures_in_a_row()
        said = self.backup.notice(self.backup.run(closing=self._closing.is_set), before)
        if said is not None:
            level, text, payload = said
            self.alert(level, text, **payload)

    # -------------------------------------------------------------- expedition
    def _note_stopped(self, reason: str) -> None:
        """Say so when the floor stops buying work, and why, once a stop has lasted three ticks;
        and say so again when it reopens.

        Measured Sept 22, 2026: the campaign's Sail meter latched at 16:47:39Z and the floor stopped
        research, Merton, audits and births with $139 of allowance unspent -- and nothing said so.
        Every tick summary read "stopped", every alert stayed quiet, and it was found 23 minutes
        later by reading the ledger. A warning, not an error: a vendor-side stop is no reason to
        roll back the release being watched. A maintenance pause is the operator's own act and is
        not announced.

        "Three ticks" were two minutes of a stop while ticks were sixty seconds apart (the stop seen at
        0, 60 and 120 s); since H5 (Sept 25, 2026) ticks are thirty seconds apart, and three of them
        would tell a stop of one minute -- a Sail meter read that failed twice (it is read at most once a
        minute, `FundedTransport.refresh`). So the stop is told once it has lasted `STOPPED_TELL_SECONDS`
        (the review of #297), whatever the tick."""
        tell = told = None
        now = self.clock()
        with self._state_lock:
            row = dict(self._state.get("stopped") or {"reason": "", "ticks": 0, "told": False})
            if not reason:
                if row.get("told"):
                    told = row.get("reason")
                self._state["stopped"] = {"reason": "", "ticks": 0, "told": False}
            else:
                same = row.get("reason") == reason
                row["ticks"] = int(row.get("ticks") or 0) + 1 if same else 1
                # A row an older release wrote has no `since`: its stop is timed from now.
                row["since"] = float(row["since"]) if same and row.get("since") is not None else now
                row["reason"] = reason
                if now - row["since"] >= STOPPED_TELL_SECONDS and not row.get("told") and not reason.startswith("maintenance pause"):
                    row["told"] = True
                    tell = (row["ticks"], now - row["since"])
                self._state["stopped"] = row
        if tell:
            self.alert("warning", f"the floor has stopped buying work for {tell[1] / 60:.0f} minutes ({tell[0]} ticks): {reason}. "
                                  "No research, Merton, births or payouts; exits and reconciliation go on.")
        if told:
            self.alert("info", f"the floor is open for business again (it had stopped: {told})")

    def _expedition_notices(self) -> None:
        """Tell the owner, once each, when a budget is gone or the expedition's last day is over."""
        told = self._state.setdefault("expedition_told", {})
        for kind, name in (("sail", "Sail"), ("openai", "frontier model")):
            if self.pacer.over(kind) and not told.get(kind):
                told[kind] = True
                spent, budget = self.pacer.spent(kind), self.pacer.budget[kind]
                why = "its budget is spent" if spent >= budget else f"day {self.pacer.days} is over with ${budget - spent:.2f} unspent"
                if self.campaigns:
                    self.alert("info", f"{self.campaigns.policy['phase']}: {name} allowance closed ({why}). "
                               "New paid work stops; position reconciliation and exits continue. The next phase is not automatically funded.")
                    continue
                self.alert("error", f"The expedition's {name} spending has stopped: {why} (${spent:.2f} of ${budget}). "
                                    + ("Research passes stop; agents still wake and trade." if kind == "sail" else "Merton's five pull-request roles stop. Audits are not paced and go on under the gateway's monthly cap."))

    def _floor_invariants(self) -> None:
        """Workstream B (Sept 23, 2026): the floor finds the next blocker itself. Two checks over the
        ledger rows written since the last pass -- from a cursor saved in house.json, so never the
        whole ledger, and on the first pass only the newest `INVARIANTS_FIRST_ROWS` -- each raised
        as an ops warning once per condition:

        - A desk offered markets for an hour with zero intents: `agent.woke` rows with `offered > 0`
          on `QUIET_DESK_WAKES` or more wakes of the desk's agents inside the trailing hour, the
          first of them most of an hour ago, and no intent from any agent of the desk in that hour
          (a wake's `intents` count, or an `agent.intent` row). Told once a desk an hour. Its rules
          are not firing on what it is shown: that wants a research pass, not more wakes. A desk whose
          offered agents are all day programs is told only after a day with no intent from any of its
          agents (`QUIET_DESK_DAY_SECONDS`, measured from `quiet_since`, its first unanswered offer since
          its last intent), once a day; an offer is only what matches the program (`_offered`).
        - A real-money bunt frozen by a daily-loss rule: a `book.refused` row on a real book whose
          reasons mention a daily loss, for an agent on rung 2. Told once an agent a day. The book's
          daily rule is meant not to apply to a bunt (the plan's U1); this says if it ever does.
        """
        now = self.clock()
        with self._state_lock:
            state = self._state.setdefault("invariants", {})
            if now - float(state.get("at") or 0) < INVARIANTS_EVERY_SECONDS:
                return
            state["at"] = now
            cursor = state.get("cursor")
            wakes: dict[str, list[list[Any]]] = {k: list(v) for k, v in (state.get("wakes") or {}).items()}
            told_quiet: dict[str, float] = dict(state.get("quiet_told") or {})
            told_frozen: dict[str, str] = dict(state.get("frozen_told") or {})
            quiet_since: dict[str, float] = dict(state.get("quiet_since") or {})
        if cursor is None:
            head = self.ledger.read(limit=1, newest=True)
            cursor = max(0, (head[-1].seq if head else 0) - INVARIANTS_FIRST_ROWS)
        alerts: list[str] = []
        for row in self.ledger.iter(kinds=("agent.woke", "agent.intent", "book.refused"), after=int(cursor)):
            cursor = row.seq
            if row.kind == "book.refused":
                name = str(row.payload.get("book") or "")
                book = self.books.get(name)
                real = book.real_money if book is not None else name in REAL_BOOKS
                hit = next((str(r) for r in (row.payload.get("reasons") or ()) if "daily loss" in str(r).lower()), None)
                if not real or hit is None or self.evaluator.rung(row.agent) != 2:
                    continue
                day = str(row.at)[:10]
                if told_frozen.get(row.agent) == day:
                    continue
                told_frozen[row.agent] = day
                alerts.append(f"{row.agent}: a real-money bunt on {name} was frozen by a daily-loss rule ({hit!r}). "
                              "Rung 2 is meant to be governed by the allocator's stay drawdown, not the book's daily rule "
                              "(Sept 23, 2026); if this stands, the rule is applying again.")
                continue
            agent = self.registry.get(row.agent)
            if agent is None or not agent.specialty:
                continue
            at = _epoch(row.at)
            if row.kind == "agent.intent":
                wakes.setdefault(agent.specialty, []).append([at, row.agent, 0, 1])
            elif row.payload.get("ok"):
                # A buy its own pause held (X1, `held`) is its rules firing, not a desk gone quiet.
                wakes.setdefault(agent.specialty, []).append(
                    [at, row.agent, int(row.payload.get("offered") or 0),
                     int(row.payload.get("intents") or 0) + int(row.payload.get("held") or 0)])
            else:
                continue
            if int(wakes[agent.specialty][-1][3]):
                quiet_since.pop(agent.specialty, None)  # the desk acted: its quiet starts again at the next offer
            elif int(wakes[agent.specialty][-1][2]):
                quiet_since.setdefault(agent.specialty, at)
        for niche_id, rows in list(wakes.items()):
            rows = [r for r in rows if now - float(r[0]) <= QUIET_DESK_SECONDS][-400:]  # eight seats waking every five minutes is 96 an hour
            if not rows:
                wakes.pop(niche_id)
                continue
            wakes[niche_id] = rows
            offered = [r for r in rows if int(r[2]) > 0]
            if len(offered) < QUIET_DESK_WAKES or any(int(r[3]) for r in rows):
                continue
            # Day programs act around their events: their desk is quiet after a day, not an hour.
            day = all(getattr(self.registry.get(str(r[1])), "horizon", "") == "day" for r in offered)
            window = QUIET_DESK_DAY_SECONDS if day else QUIET_DESK_SECONDS
            start = float(quiet_since.get(niche_id, now)) if day else float(offered[0][0])
            if now - start < window * 0.75 or now - float(told_quiet.get(niche_id) or float("-inf")) < window:
                continue
            told_quiet[niche_id] = now
            agents = sorted({str(r[1]) for r in offered})
            alerts.append(f"{niche_id}: offered markets on {len(offered)} wakes in the last hour (offered "
                          f"{', '.join(str(r[2]) for r in offered[-8:])}) and no agent of the desk wrote an intent"
                          + (f" for {int((now - start) // 3600)} hours (a desk of day programs)" if day else "")
                          + f" ({', '.join(agents[:8])}). Its rules are not firing on what it is shown: a research pass, not more wakes.")
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        with self._state_lock:
            state.update(cursor=int(cursor), wakes=wakes, quiet_since=quiet_since,
                         quiet_told={k: v for k, v in told_quiet.items() if now - float(v) < QUIET_DESK_DAY_SECONDS},
                         frozen_told={k: v for k, v in told_frozen.items() if v >= today})
        for text in alerts:
            self.alert("warning", text)

    # ---------------------------------------------------------------- seasons
    def survey_due(self) -> bool:
        every = float(self.settings.niche_survey_hours)
        if every <= 0 or self.kalshi_data is None or not hasattr(getattr(self.kalshi_data, "market_data", None), "markets"):
            return False
        live = self._state.get("niche_live") or {}
        # Never surveyed yet, or a Kalshi desk has been added since (the open desk's discovery list
        # comes from the survey): every half hour until one works, not at tomorrow's turn.
        if not live or any(n.venue == "kalshi" and not n.dormant and n.id not in live for n in self.niches.values()):
            return self.clock() - float(self._state.get("last_niche_try") or 0) >= 1800
        return self.clock() - float(self._state.get("last_niche_survey") or 0) >= every * 3600

    def _series_category(self, series: str) -> str | None:
        known = self._state["series_category"]
        if series not in known:
            try:
                raw = self.kalshi_data.market_data._get(f"/series/{series}", what=f"kalshi series {series}")
                known[series] = str((raw.get("series") or raw).get("category") or "")
            except Exception:  # noqa: BLE001 - not knowing keeps a stranger out
                return None
        return known[series]

    def survey_niches(self) -> dict[str, list[str]]:
        """Survey the venue and let every Kalshi specialty's universe follow what is trading now."""
        with self._state_lock:
            self._state["last_niche_try"] = self.clock()
        paced = getattr(self.kalshi_data, "_paced", None)  # the survey shares the agents' pace limit with Kalshi
        source = type("Paced", (), {"markets": staticmethod(paced)})() if paced else self.kalshi_data.market_data
        volumes = niches_module.survey(source, clock=self.clock)
        if not volumes:
            return {}
        live = niches_module.apply_survey(self.niches, volumes, self._series_category)
        with self._state_lock:
            self._state["niche_live"] = live
            self._state["last_niche_survey"] = self.clock()
        joined = {nid: [x for x in rows if x not in self.niches[nid].listed] for nid, rows in live.items()}
        self.ledger.append("ops.budget", {"what": "niche survey", "series_trading": len(volumes),
                                          "live": {nid: len(rows) for nid, rows in live.items()}, "joined": {k: v[:20] for k, v in joined.items() if v}})
        return live

    # ---------------------------------------------------------------- horizon
    #: The reasons the House's own exits carry (`_enforce_horizon`): how it knows its exit from the agent's orders.
    HORIZON_EXIT = "The House's horizon rule"
    EXPIRY_EXIT = "The House's expiry rule"

    def _enforce_horizon(self) -> int:
        """Close crypto positions held past the horizon (the entry side of the rule, for Kalshi, is
        in the book's check). The agent's own working orders in that coin are cancelled first, so
        the whole holding is free to sell; a position is closed by the House, at the market.

        The House's own exit, once sent, stands until the venue reports it (the review of #297, Sept 25,
        2026). Until then this rule cancelled every working order in the coin, its own exit included, and
        sent the exit again under the same nonce: the same intent id, refused by the book as a duplicate,
        so a market sell the venue had not yet reported (Alpaca accepts first and fills on a later read)
        left the position with no exit until the hour turned -- and with the venues polled once a minute
        beside a thirty-second tick, the tick between a send and its poll always met it unreported. An
        exit is sent only while none of the House's stands (`_house_exits`), so a second sell is never
        beside a first that might still fill; one after an exit the venue cancelled carries that exit's
        order id in its nonce, so it is never the cancelled one's duplicate."""
        hours = float((self.game.get("horizon") or {}).get("crypto_max_hold_hours") or 0)
        if hours <= 0:
            hours = float("inf")  # the crypto rule is off; the option expiry rule below is not a dial
        closed = 0
        for book in self.books.values():
            if family_of(book.name) != "alpaca":
                continue
            exits = []
            now = now_iso(self.clock)
            for agent_id in book.agents():
                for holding in list(book.account(agent_id).holdings.values()):
                    if holding.instrument.asset_class != "crypto" or not holding.opened_at or holding.quantity <= 0:
                        continue
                    held = (self.clock() - _epoch(holding.opened_at)) / 3600.0
                    if held <= hours:
                        continue
                    standing, after = self._house_exits(book, agent_id, holding.instrument.key, self.HORIZON_EXIT)
                    for working in book.open_orders(agent_id):
                        if working.instrument.key == holding.instrument.key and working.order_id not in standing:
                            book.cancel(agent_id, working.order_id)
                    if standing:
                        continue  # the House's market sell stands until the venue says what became of it
                    quantity = book.account(agent_id).holdings.get(holding.instrument.key)
                    if quantity is None or quantity.quantity <= 0:
                        continue
                    exits.append(Intent.new(
                        agent=agent_id, instrument=holding.instrument, side="sell", quantity=quantity.quantity,
                        reason=f"{self.HORIZON_EXIT}: held {held:.0f} hours, and a crypto position is closed after {hours:g}.",
                        created_at=now, nonce=f"horizon:{holding.opened_at}:{int(self.clock()) // 3600}{after}",
                    ))
            # A long option is sold before it can expire: in the money at the bell it would be
            # exercised into a hundred shares this account cannot carry. From 14:30 New York on
            # its last day the House sells it at the bid; one with no bid left is worthless and is
            # written off once the venue has cleared it. Its sell stands while its limit is at or under
            # the bid (it can fill there); one above a bid that fell is cancelled, and the next goes at
            # the new bid only once the venue has confirmed that cancel -- in this pass or a later one.
            today, hour = _new_york(self.clock)
            for agent_id in book.agents():
                for holding in list(book.account(agent_id).holdings.values()):
                    inst = holding.instrument
                    if inst.asset_class != "option" or holding.quantity <= 0 or str(inst.expiry or "9999") > today or hour < 14.5:
                        continue
                    quote = book.broker.quote(inst)
                    bid = quote.bid if quote.bid is not None and quote.bid > 0 else None
                    standing, _ = self._house_exits(book, agent_id, inst.key, self.EXPIRY_EXIT)
                    for working in book.open_orders(agent_id):
                        if working.instrument.key != inst.key:
                            continue
                        if working.order_id not in standing or (bid is not None and working.limit_price is not None and working.limit_price > bid):
                            book.cancel(agent_id, working.order_id)  # the agent's own, or the House's above a bid that fell
                    standing, after = self._house_exits(book, agent_id, inst.key, self.EXPIRY_EXIT)
                    if standing or bid is None:
                        continue  # its sell stands, or a cancel the venue has not confirmed may yet fill: never a second
                    left = book.account(agent_id).holdings.get(inst.key)
                    if left is None or left.quantity <= 0:
                        continue
                    exits.append(Intent.new(
                        agent=agent_id, instrument=inst, side="sell", quantity=left.quantity, order_type="limit", limit_price=bid,
                        reason=f"{self.EXPIRY_EXIT}: a long option is sold on its last afternoon, never left to be exercised.",
                        created_at=now, nonce=f"expiry:{inst.key}:{int(self.clock() // 600)}{after}",
                    ))
            if exits:
                closed += sum(1 for o in book.submit(exits) if o.status not in ("refused", "duplicate"))
            closed += book.expire_options()
        return closed

    @staticmethod
    def _house_exits(book: Book, agent_id: str, key: str, rule: str) -> tuple[set[str], str]:
        """The House's own exits of one holding under `rule` (`HORIZON_EXIT`, `EXPIRY_EXIT`: the reason its sells
        carry) that are still open on the book -- sent, and not yet reported filled, cancelled or rejected by the
        venue -- and the nonce suffix of the next one: `:<order id>` of the newest the venue cancelled, or "" when
        none was. A rejected exit adds nothing, so its duplicate waits for the nonce's own hour (or ten minutes) as
        before; a cancelled one is sent again at once, as a new intent. The review of #297 (Sept 25, 2026)."""
        with book._lock:
            mine = [w for w in book.orders.values() if w.side == "sell" and w.instrument.key == key
                    and any(s.agent == agent_id and s.reason.startswith(rule) for s in w.shares)]
        standing = {w.order_id for w in mine if w.open}
        cancelled = [w for w in mine if w.status == "cancelled"]
        newest = max(cancelled, key=lambda w: (w.submitted_at, w.order_id), default=None)
        return standing, (f":{newest.order_id}" if newest is not None else "")

    # ---------------------------------------------------------------- tuition
    def tuition(self, venue: str | None = None) -> dict[str, Any]:
        """What the micro rung has cost so far, and whether it may take another agent.

        The paper screen lets through agents with no proven edge, on purpose: real fills are the
        test. What that may cost is a number in the constitution, not a statistic. The cost is
        the net loss of every real-money account that has never earned rung 3 (a swept account
        counts what it lost: its equity is zero and what was not returned is still staked). A
        new agent is seated only while every active micro stake, the remaining risk of abandoned
        accounts, and its own stake fit under the loss line. A drawdown stop is not a guaranteed
        exit price: an option or a contract held to settlement can lose its entire purchase."""
        rules = dict(CONSTITUTION["tuition"])
        pilot = self.campaigns.live_authorization() if self.campaigns else None
        if pilot:
            # The owner explicitly funds this envelope. Reaching rung 3 or expiry must never
            # erase its losses, reserved stakes or abandoned positions from the experiment.
            rules['max_loss_usd'] = pilot['policy']['max_loss_usd']
            rules['max_agents'] = pilot['policy']['max_agents']
            if venue is not None and 'venue_capital_usd' in pilot['policy']:
                rules['max_loss_usd'] = pilot['policy']['venue_capital_usd'][venue]
        active = {agent.id for agent in self.registry.living()
                  if (venue is None or agent.venue == venue)
                  and (self.evaluator.rung(agent.id) == 2 or pilot and self.evaluator.rung(agent.id) >= 3)}
        stake = Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"])
        pnl, worst_loss, pending_accounts = ZERO, ZERO, 0
        accounted = set()
        for book in self.books.values():
            if not book.real_money or venue is not None and book.name != REAL_BOOK[venue]:
                continue
            for agent_id in book.agents():
                if pilot or self.evaluator.max_rung(agent_id) < 3:
                    account = book.account(agent_id)
                    pnl += book.equity(agent_id) - account.staked
                    working = book.open_orders(agent_id)
                    if agent_id in active:
                        # All its cash can still be spent. Reserve a future stake as well when
                        # seat() has yet to fund a newly promoted or previously swept account.
                        funding = stake if not account.funded or (account.swept and not account.holdings) else ZERO
                        worst_loss += account.staked + funding - min(account.cash, ZERO)
                        accounted.add(agent_id)
                    else:
                        pending_accounts += bool(account.holdings or working)
                        # Retired/demoted cash is safe unless an unresolved entry can spend it.
                        safe_cash = min(account.cash, ZERO) if any(w.side == "buy" for w in working) else account.cash
                        worst_loss += account.staked - safe_cash
        worst_loss += sum((stake for agent_id in active - accounted if pilot or self.evaluator.max_rung(agent_id) < 3), ZERO)
        worst_loss = max(worst_loss, ZERO)
        seated = len(active)
        spent = max(-pnl, ZERO)
        limit = Decimal(rules["max_loss_usd"])
        room = seated < int(rules["max_agents"]) and worst_loss + stake <= limit
        # Reserved headroom can return when abandoned positions settle. Do not describe that
        # wait as a permanently exhausted budget. A flat floor unable to fund even one full
        # stake is closed and must still report that condition rather than waiting silently.
        closed = spent >= limit or (not room and seated == 0 and pending_accounts == 0)
        return {"pnl_usd": pnl, "spent_usd": spent, "limit_usd": limit, "seated": seated,
                "max_agents": int(rules["max_agents"]), "room": room, "closed": closed,
                "headroom_usd": limit - worst_loss, "worst_case_loss_usd": worst_loss,
                "reserved_loss_usd": max(worst_loss - spent, ZERO), "pending_accounts": pending_accounts}

    def _enforce_tuition(self) -> None:
        """At the line the micro rung closes: everyone on it goes back to paper, once."""
        with self._lifecycle_lock:
            self._enforce_tuition_locked()

    def _enforce_tuition_locked(self) -> None:
        authorization = self.campaigns.live_authorization() if self.campaigns else None
        # Venue allocations are separate purses: profit at Alpaca cannot refill Kalshi's risk.
        if authorization and authorization['policy'].get('venue_capital_usd'):
            for venue in authorization['policy']['venue_capital_usd']:
                state = self.tuition(venue)
                if state['closed']:
                    for agent in self.registry.living():
                        if agent.venue == venue and self.evaluator.rung(agent.id) >= 2:
                            old = self.book_of(agent)
                            while self.evaluator.rung(agent.id) >= 2:
                                self.evaluator.demote(agent.id, f"the {venue} capital allocation is exhausted",
                                                      {'spent_usd': str(state['spent_usd'])})
                            if old is not None:
                                self._move_books(agent, old)
        state = self.tuition()
        if not state["closed"]:
            self._state["tuition_closed"] = False
            return
        pilot = self.campaigns.live_authorization() if self.campaigns else None
        for agent in self.registry.living():
            if self.evaluator.rung(agent.id) == 2 or pilot and self.evaluator.rung(agent.id) >= 3:
                old = self.book_of(agent)
                while self.evaluator.rung(agent.id) >= 2:
                    self.evaluator.demote(agent.id, f"the live learning tuition of ${state['limit_usd']} is spent", {"spent_usd": str(state["spent_usd"])})
                if old is not None:
                    self._move_books(agent, old)
        if not self._state.get("tuition_closed"):
            self._state["tuition_closed"] = True
            reached = state["spent_usd"] >= state["limit_usd"]
            why = (f"has lost ${state['spent_usd']:.2f} of its ${state['limit_usd']} tuition"
                   if reached else
                   f"has lost ${state['spent_usd']:.2f} of its ${state['limit_usd']} tuition, and one more agent's full stake "
                   f"no longer fits under the line")
            self.alert("error", f"The micro rung {why} and is closed. Further promotion waits for settled headroom "
                                "or a larger envelope from the owner: the live grant's `max_loss_usd` while one is active, "
                                "`tuition.max_loss_usd` in the constitution otherwise.")

    def _audit_due(self, agent: Agent) -> bool:
        """An audit is about a quarter of a dollar, paid by the House (`game.json` `audit.house_pays`,
        Sept 23, 2026; charged to the agent before, or when that is off). A vetoed agent is not
        audited again at every look: it waits out a cooldown on paper (where its record is the
        auditor's counterfactual), and, where agents pay, no agent is audited that cannot pay and live.

        An audit that did not happen -- the call refused, the answer unreadable -- is not a verdict
        and must not cost the agent a day at the top of the ladder for the gate's own malfunction.
        It waits the short cooldown instead, long enough not to hammer a frontier that is down."""
        return self._audit_wait(agent) is None

    def _audit_wait(self, agent: Agent) -> dict | None:
        rules = self.game.get("audit") or {}
        if self._audit_charges_agent() and self.economy.balance(agent.id) < Decimal(str(rules.get("min_credits_usd", "0.60"))):
            return {'stage': 'audit_credits', 'reason': 'the agent cannot cover its audit and operating credit floor'}
        # The agent's own last verdict: a family swing's (`family_swing`, Deploy B) is written against one member of
        # the family but judged the family's stake, and never starts this agent's cooldown (review of #242).
        last = next((e for e in reversed(self.ledger.read(kinds="audit.verdict", agent=agent.id, limit=200, newest=True))
                     if not e.payload.get("family_swing")), None)
        if last is None:
            return None
        current = getattr(self.auditor, 'policy_digest', None)
        revised = bool(current and last.payload.get('policy_digest') != current)
        short = bool(last.payload.get('error')) or revised
        hours = float(rules.get("error_cooldown_hours", 0.5) if short else rules.get("cooldown_hours", 72))
        if self._burst and not short:
            # A full day is a duplicate-request backoff, not a requirement to ignore fresh
            # forward outcomes. The evaluator must still qualify the agent, and a NEW audit
            # must approve it. Repeated reads or partial exits do not create observations.
            from .episodes import completed
            book = self.book_of(agent)
            if book is not None and book.evidence_integrity(agent.id)['ok']:
                new_episodes = completed(self.ledger, agent.id, book.name, since_seq=last.seq)
                new_blocks = self.evaluator.blocks(agent.id, since_seq=last.seq, book=book.name)
                if (len(new_episodes) >= int(CONSTITUTION['ladder']['completed_exposures']['look_every_episodes'])
                        or sum(bool(row.get('active')) for row in new_blocks) >= int(CONSTITUTION['ladder']['look_every_active_blocks'])):
                    return None
        due = _epoch(last.at) + hours * 3600
        if self.clock() >= due:
            return None
        return {'stage': 'audit_cooldown', 'reason': 'waiting before reconsidering an audit under a corrected policy' if revised
                else 'waiting before repeating the production audit', 'retry_at': due}

    def _move_books(self, agent: Agent, old: Book) -> None:
        """Leave one book for another: cancel, sell what can be sold, and take the stake back."""
        self._wind_down(agent, old)
        self.seat(agent)

    def _wind_down(self, agent: Agent, book: Book) -> None:
        # A seat's limits live only in memory, and only living agents are seated on start. After
        # a restart a dead agent still holding a position had none, so every exit was refused as
        # "has no seat on the book", every mark pass, forever. Measured Sept 22, 2026, after the
        # night's deploys: haghani-2, krasker, krasker-3 and krasker-4 were refused 45 times in an
        # hour on alpaca-paper. An exit needs a seat to be checked against; give it the lowest
        # rung's, on this book, so closing an account never depends on when the House restarted.
        if agent.id not in book.limits:
            book.limits[agent.id] = self._limits(2 if book.real_money else 1, agent, book.account(agent.id).staked)
        # An unfinished sell already closes this account. Keep it in flight and reserve its
        # remaining units so retrying after a venue outage cannot duplicate or cancel that exit.
        for working in book.open_orders(agent.id):
            if working.side == "buy":
                book.cancel(agent.id, working.order_id)
        reserved: dict[str, Decimal] = {}
        for working in book.open_orders(agent.id):
            if working.side == "sell":
                reserved[working.instrument.key] = reserved.get(working.instrument.key, ZERO) + sum(
                    (share.quantity - share.filled for share in working.shares if share.agent == agent.id), ZERO)
        now = now_iso(self.clock)
        exits = []
        held_back: dict[str, Decimal] = {}
        for holding in list(book.account(agent.id).holdings.values()):
            if holding.instrument.asset_class == "event":
                continue  # a Kalshi contract is held to settlement: selling a favourite at the bid gives the edge back
            quantity = max(holding.quantity - reserved.get(holding.instrument.key, ZERO), ZERO)
            if quantity <= 0:
                continue
            dust = self._dust_reason(book, holding.instrument, quantity)
            if dust is not None:
                # A holding the venue will not trade is never sent (Sept 24, 2026: 107 refused sells of haghani-
                # h426990's 0.000000001 LINK/USD in twelve hours): booked as dust, and the account can close.
                self._book_dust(agent, book, holding.instrument, quantity, dust)
                continue
            if self._wind_down_stopped(agent, book, holding.instrument, quantity):
                continue  # the venue refused this very sale `WIND_DOWN_REFUSALS` times in a row: told once, not retried
            if market_hours(holding.instrument, now) is False:
                # A stock or an option sells only in the regular session: outside it the book refuses
                # a market sell ("market orders outside regular hours are not permitted") and an
                # option's bid is stale or gone. Measured Sept 22-23, 2026: 576 such refusals and 116
                # "an option order must be a limit order", every one the House winding down a dead
                # agent's position on every mark pass through the night. Hold the sale for the open
                # instead: `_release_wind_downs` places it in the first tick after the bell, and the
                # mark pass would within five minutes anyway. The hold is kept in house.json, so a
                # restart keeps it; a coin or a Kalshi position is not held (their markets never close).
                held_back[holding.instrument.key] = quantity
                continue
            if holding.instrument.asset_class == "option":
                # An option sells only at a limit (`Book.check`), so a market wind-down was refused on
                # every mark pass. Measured Sept 22, 2026: four dead options agents, twelve refusals in
                # eight minutes. Sell at the bid, as the expiry rule does; one with no bid left is the
                # expiry rule's to write off.
                quote = book.broker.quote(holding.instrument)
                if quote is None or quote.bid is None or quote.bid <= 0:
                    continue
                exits.append(Intent.new(agent=agent.id, instrument=holding.instrument, side="sell", quantity=quantity,
                                        order_type="limit", limit_price=quote.bid,
                                        reason="the House is closing this account at the bid (an option sells only at a limit)",
                                        created_at=now, nonce=f"wind-down:{now}"))
                continue
            intent = Intent.new(agent=agent.id, instrument=holding.instrument, side="sell", quantity=quantity,
                                reason="the House is closing this account", created_at=now, nonce=f"wind-down:{now}")
            if book._would_cross_own(intent, None):
                # Another agent rests a bid on this symbol and a market sell could hit it, so the
                # book refuses it -- on every wake, for ever (haghani-2, Sept 21, 2026). Rest the
                # exit at the ask instead: it cannot cross the House's bid and it still closes.
                quote = book._quote(holding.instrument)
                if quote is not None and quote.ask is not None and quote.ask > 0:
                    intent = Intent.new(agent=agent.id, instrument=holding.instrument, side="sell", quantity=quantity,
                                        order_type="limit", limit_price=quote.ask,
                                        reason="the House is closing this account at the ask (a market sell would meet the House's own bid)",
                                        created_at=now, nonce=f"wind-down:{now}")
            exits.append(intent)
        self._note_held_wind_downs(agent, book, held_back)
        if exits:
            outcomes = book.submit(exits)
            self._note_wind_down_refusals(agent, book, exits, outcomes)
            book.poll()
        self._sweep(agent.id, book)

    def _dust_reason(self, book: Book, instrument: Instrument, quantity: Decimal) -> str | None:
        """Why a holding is one the venue will not trade, or None: worth under a cent (the reconciliation's
        own dust line, `book.DUST_USD`) even at the best price quoted for it, or, where the venue's asset
        record states it (`broker.asset`, a crypto pair), under the venue's minimal order quantity.

        The mark is the last quote's BID (`Book._quote`), which a thin crypto book can leave as a stub: half a
        LINK under a $0.01 bid and a $12.28 ask read as half a cent, and the House booked six dollars the venue
        would buy as dust (the review of #245, Sept 24, 2026). So a holding under a cent at its mark is quoted
        again and valued at the highest of its mark, bid and ask; with no ask quoted it is not called dust by
        its value (the sale is tried, and the refusal invariant stands behind it)."""
        from .book import DUST_USD

        multiplier = Decimal(str(instrument.multiplier or 1))
        mark = book.marks.get(instrument.key)
        if mark is None or mark <= 0 or quantity * mark * multiplier < DUST_USD:
            quote = book._quote(instrument)
            ask = quote.ask if quote is not None and quote.ask is not None and quote.ask > 0 else None
            if ask is not None:
                best = max(p for p in (mark, quote.bid, ask) if p is not None and p > 0)
                value = quantity * best * multiplier
                if value < DUST_USD:
                    return f"worth ${value:.8f} even at the ask, under a cent"
        asset = getattr(book.broker, "asset", None)
        if asset is not None and instrument.asset_class == "crypto":
            try:
                minimum = (asset(instrument.market_id or instrument.symbol) or {}).get("min_order_size")
            except Exception:  # noqa: BLE001 - an unreadable record states no minimum
                minimum = None
            if minimum is not None and quantity < Decimal(str(minimum)):
                return f"under the venue's minimal order quantity {minimum}"
        return None

    def _book_dust(self, agent: Agent, book: Book, instrument: Instrument, quantity: Decimal, why: str) -> None:
        """Book a holding the venue will not trade as dust (Sept 24, 2026), the way the reconciliation books a
        sub-cent position difference (`Book._position_dust`): off the agent's account at no price, onto the
        House row, which then holds the units the venue still shows, so the book still reconciles and the
        account can close. Said once on the ledger: the two dust fills and one info alert.

        The two fills are ONE ledger group (`Ledger.append_many`), applied to the book only once both are written:
        as two appends, a crash or a failed write between them (a "database is locked" on a busy box) left the book
        short of the venue by the holding -- under a cent the reconciliation re-books the crumb, but dust by the
        venue's minimal quantity can be worth more, and that difference froze the book's entries, in the process
        and after a restart (the review of #245, Sept 24, 2026)."""
        from .book import text

        common = {"book": book.name, "source": "dust", "instrument": instrument.to_dict(), "quantity": text(quantity), "price": "0",
                  "fee_usd": "0", "cash_delta": "0", "real_money": book.real_money}
        with book._lock:
            entries = self.ledger.append_many([
                {"kind": "book.fill", "agent": agent.id, "payload": {**common, "side": "sell", "position_delta": text(-quantity),
                                                                     "reason": f"the House booked it as dust: {why}"}},
                # The House row, as `Book._position_dust` books a surplus: the units the venue still shows.
                {"kind": "book.fill", "agent": HOUSE, "payload": {**common, "side": "buy", "position_delta": text(quantity)}},
            ])
            for entry in entries:
                book._apply(entry.kind, entry.agent, entry.payload, entry.at)
        self.alert("info", f"{agent.id}: {book.name} booked {text(quantity)} {instrument.market_id or instrument.symbol} as dust "
                           f"instead of selling it ({why}); the account can close")

    def _wind_down_stopped(self, agent: Agent, book: Book, instrument: Instrument, quantity: Decimal) -> bool:
        """Whether this sale was refused `WIND_DOWN_REFUSALS` times in a row, for this very quantity: then it
        is not sent again until the holding changes, or until `WIND_DOWN_RETRY_SECONDS` after the last refusal
        (a refusal then stops it for another day, with no second warning). `_note_wind_down_refusals` keeps
        the count. The review of #245: a dead agent's holding never changes, so an outage refused three
        times in a row stranded it for good."""
        row = ((self._state.get("wind_down_refusals") or {}).get(agent.id) or {}).get(book.name, {}).get(instrument.key)
        if not (row and int(row.get("count") or 0) >= WIND_DOWN_REFUSALS and row.get("quantity") == format(quantity, "f")):
            return False
        return self.clock() - float(row.get("epoch") or 0) < WIND_DOWN_RETRY_SECONDS

    def _note_wind_down_refusals(self, agent: Agent, book: Book, exits: Sequence[Intent], outcomes: Sequence[Any]) -> None:
        """The invariant for orders no agent sent at a wake (Sept 24, 2026): the same refusal of a House-sent
        sale -- by the venue or the book -- `WIND_DOWN_REFUSALS` times in a row stops its retries, with ONE
        warning naming the order; it is tried again once a day (`_wind_down_stopped`). A sale that goes through,
        a different refusal or a changed quantity starts the count again. Kept in house.json
        (`wind_down_refusals`), so a restart does not start it again."""
        by_intent = {o.intent_id: o for o in outcomes}
        with self._state_lock:
            mine = self._state.setdefault("wind_down_refusals", {}).setdefault(agent.id, {}).setdefault(book.name, {})
            told = []
            for intent in exits:
                outcome = by_intent.get(intent.id)
                key = intent.instrument.key
                if outcome is not None and outcome.status == "duplicate":
                    continue  # the same intent twice in one second: no new answer from anyone
                if outcome is None or outcome.status not in ("rejected", "refused"):
                    mine.pop(key, None)
                    continue
                why = re.sub(r"\d+(?:\.\d+)?", "#", str(outcome.detail or ""))[:200]
                quantity = format(intent.quantity, "f")
                row = mine.get(key) or {}
                count = int(row.get("count") or 0) + 1 if (row.get("why") == why and row.get("quantity") == quantity) else 1
                mine[key] = {"why": why, "quantity": quantity, "count": count, "order": outcome.order_id, "epoch": self.clock(),
                             "detail": str(outcome.detail or "")[:300], "at": now_iso(self.clock)}
                if count == WIND_DOWN_REFUSALS:
                    told.append(mine[key] | {"symbol": intent.instrument.market_id or intent.instrument.symbol})
            if not mine:
                (self._state.get("wind_down_refusals") or {}).get(agent.id, {}).pop(book.name, None)
        for row in told:
            self.alert("warning", f"{agent.id}: the House's sale of {row['quantity']} {row['symbol']} on {book.name} was refused "
                                  f"{WIND_DOWN_REFUSALS} times in a row ({row['detail']}; order {row['order']}): it is not sent again "
                                  "until the holding changes, or once a day", order=row["order"])

    def _note_held_wind_downs(self, agent: Agent, book: Book, held_back: Mapping[str, Decimal]) -> None:
        """Keep, in house.json, which of an abandoned account's positions wait for their market to
        open (`_wind_down`), and say so once a position: the operator sees a held sale as one info
        alert, never as a refused order every mark pass. A position sold, or no longer held back,
        leaves the record."""
        with self._state_lock:
            held = self._state.setdefault("wind_down_held", {})
            mine = dict((held.get(agent.id) or {}).get(book.name) or {})
            new = [key for key in held_back if key not in mine]
            mine = {key: (mine.get(key) or {"since": now_iso(self.clock), "quantity": str(held_back[key])}) for key in held_back}
            books = dict(held.get(agent.id) or {})
            if mine:
                books[book.name] = mine
            else:
                books.pop(book.name, None)
            if books:
                held[agent.id] = books
            else:
                held.pop(agent.id, None)
        for key in new:
            self.alert("info", f"{agent.id}: {book.name} holds {held_back[key]} {key} for the open; the House sells it "
                               "once the market opens, not before (a market sell outside regular hours is refused)")

    def _release_wind_downs(self) -> None:
        """Place the sales `_wind_down` held for the open (`wind_down_held` in house.json) in the
        first tick after the regular session's bell, once a session: the mark pass would place them
        within `mark_every_seconds` anyway, but a dead agent's stock should not wait even that long
        once the market is there to take it. A hold whose agent is alive and back on that book, or
        whose book is gone, is dropped: the sale is no longer the House's to make."""
        held = self._state.get("wind_down_held") or {}
        if not held:
            return
        last = float(self._state.get("wind_down_released") or 0)
        if not (market_open_at(now_iso(self.clock)) and self._opened_since(last)):
            return
        self._state["wind_down_released"] = self.clock()
        for agent_id, books in list(held.items()):
            agent = self.registry.get(agent_id)
            for name in list(books):
                book = self.books.get(name)
                if agent is None or book is None or agent_id not in book.accounts or (agent.alive and self.book_of(agent) is book):
                    with self._state_lock:
                        (self._state.get("wind_down_held") or {}).get(agent_id, {}).pop(name, None)
                        if not (self._state.get("wind_down_held") or {}).get(agent_id):
                            (self._state.get("wind_down_held") or {}).pop(agent_id, None)
                    continue
                self._retry_wind_down(agent, book)

    def _sweep(self, agent_id: str, book: Book) -> None:
        """Return a finished account's free cash to the House's side of the book."""
        account = book.account(agent_id)
        # Free cash only: what a buy closed as never arrived still binds while the book keeps asking
        # the venue about it (`Book._reservations`) is swept on a later pass, once that window closes;
        # `stake` refuses to take reserved cash, and this runs unguarded in the mark pass.
        free = account.cash - book._reserved_cash(agent_id)
        if not account.holdings and not book.open_orders(agent_id) and free > 0 and not account.swept:
            book.stake(agent_id, -free, note="account closed")  # all of it: what is left of the stake, and any profit

    def _observe_wind_down(self, agent: Agent, book: Book) -> None:
        """Keep the evidence until an abandoned account's final trades and sweep are observed.

        A dead or demoted agent can still hold contracts awaiting settlement. Those outcomes
        belong on the record even though this book no longer decides the agent's current rung.
        The zero-equity block after the sweep needs a later mark to finish; once it exists there
        is no unfinished capital left to observe, and flat marks need not be scanned again.
        """
        account = book.account(agent.id)
        if account.swept and account.cash == 0 and not account.holdings and not book.open_orders(agent.id):
            rows = self.evaluator.blocks(agent.id, book=book.name)
            if rows and float(rows[-1]["end_equity"]) == 0:
                return
        self.evaluator.observe(agent.id, book.name, agent.horizon)

    def _retry_wind_down(self, agent: Agent, book: Book) -> None:
        """Retry an abandoned account's exits without letting one venue failure stop the floor."""
        try:
            self._wind_down(agent, book)
        except Exception as exc:  # noqa: BLE001 - the next mark pass retries the unfinished account
            self.alert("warning", f"{agent.id}: {book.name} could not finish winding down ({type(exc).__name__}: {str(exc)[:160]})")

    # ------------------------------------------------------------------ death
    def kill(self, agent: Agent, cause: str, detail: str = "", *, expected_generation: tuple | None = None) -> None:
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None or (expected_generation is not None and generation != expected_generation):
                return
            agent = self.registry.get(agent.id)
            for book in self.books.values():
                if agent.id in book.accounts:
                    # A venue that is down when an agent dies must not keep it alive: the death is
                    # recorded now and the mark pass retries its exits (`_retry_wind_down`).
                    self._retry_wind_down(agent, book)
            text = self.postmortem(agent, cause, detail)
            self.ledger.append("agent.postmortem", {"text": text, "cause": cause}, agent=agent.id)
            self.commons.playbook_add(f"Post-mortem: {agent.id}", text, source="graveyard", agent=agent.id)
            self.registry.died(agent.id, cause, detail)
            if cause == "displaced" and agent.specialty:
                self._desk_displaced[agent.specialty] = self.clock()
            for key in ("next_wake", "memory", "last_research", "tried", "idle"):
                self._state[key].pop(agent.id, None)
            try:
                self._hand_off_retained(agent, cause)  # S3: its latest replay-passed candidate waits for a seat
            except Exception as exc:  # noqa: BLE001 - a hand-off that fails never keeps an agent alive
                self.alert("warning", f"{agent.id}: its retained candidate could not be handed to the seat queue "
                                      f"({type(exc).__name__}: {str(exc)[:160]}); the admission pass picks it up")
        try:
            self.sandbox.retire(agent.id)
        except Exception as exc:  # noqa: BLE001
            self.alert("warning", f"{agent.id}: its box could not be retired ({type(exc).__name__})", **environment("sail", exc))

    def postmortem(self, agent: Agent, cause: str, detail: str) -> str:
        rung = self.evaluator.rung(agent.id)
        trials = [e.payload for e in self.ledger.iter(kinds="eval.trial", agent=agent.id)]
        blocks = self.evaluator.blocks(agent.id)
        growth = sum(float(b["log_growth"]) for b in blocks)
        spent = sum(Decimal(e.payload["usd"]) for e in self.ledger.iter(kinds="credit.charge", agent=agent.id))
        detail = detail.strip()
        detail = (detail[0].upper() + detail[1:] + ("" if detail.endswith(".") else ".")) if detail else ""
        lines = [
            f"{agent.id} (family {agent.family}, niche {agent.niche}, generation {agent.generation}) died on rung {rung} of {cause}. {detail}".strip(),
            f"It ran {len(trials)} replay trials, traded {len(blocks)} blocks forward for a total log growth of {growth:+.4f}, and spent ${spent:.2f} of compute.",
        ]
        if trials:
            last = trials[-1]
            lines.append(f"Its last replay: Sharpe {last.get('sharpe')}, deflated {last.get('deflated_sharpe')}, {last.get('trades')} trades; " + "; ".join(last.get("reasons") or ["passed"]))
        return " ".join(lines)

    # ------------------------------------------------------------------- forks
    def fork(self, parent: Agent, *, code: str | None = None, params: Mapping[str, Any] | None = None, reason: str = "", passed_replay: bool = False,
             staked_by_house: bool = False, described: Any | None = None) -> Agent | None:
        """A rich agent has a child and endows it. With no new code the child is a mechanical
        mutation of the parent's parameters; either way it answers for itself from replay up,
        unless its code already passed replay as its parent's candidate.

        `staked_by_house`: the child's code is a research candidate that PASSED replay and its
        parent cannot afford the endowment. The House stakes it from the pool instead (at most one
        a parent a day): an agent above rung 0 cannot edit itself, so without this an improvement
        that research found and replay confirmed would wait weeks for its parent to save up.

        `described`: the child's NEEDS, read by the caller in the probe box before it took the
        lifecycle lock (`_admit_researched`). Then nothing here calls Sail: the child's box starts
        from the clean image, not a checkpoint of its parent's."""
        rules = self.game["economy"]
        if len(self.registry.living()) >= int(rules["max_population"]):
            return None
        if staked_by_house:
            last = float(self._state.setdefault("last_staked", {}).get(parent.id) or 0)
            if not (code and passed_replay) or self.clock() - last < float(rules["epoch_seconds"]):
                return None
        elif not self.economy.can_fork(parent.id):
            return None
        niche = self.niche_of(parent)
        if niche is not None and self.members(niche.id) >= niche.max_members:
            return None  # its specialty is full: no niche may crowd out the rest
        if code is None and self._losing_family(parent.family):
            return None  # a parameter copy repeats a mechanism the forward record has already judged (Sept 23, 2026)
        child_code = code or parent.code
        child_params = dict(params) if params is not None else (parent.params if code else self._mutated_params(parent, seed=f"{parent.id}:{len(self.registry.agents)}"))
        if child_params is None:
            return None
        child = self.spawn(parent.line or parent.name, parent.family, child_code, parent=parent.id, params=child_params, reason=reason or "a parameter mutation of its parent",
                           endowment=rules["endowment_usd"] if staked_by_house else None, described=described,
                           new_code_of=parent if code else None)  # a different program is born into its own family
        if staked_by_house:
            self._state["last_staked"][parent.id] = self.clock()
        else:
            self.economy.transfer(parent.id, child.id, rules["fork_endowment_usd"], "fork endowment")
        forked = False
        try:
            forked = described is None and bool(self.sandbox.fork(parent.id, child.id))
        except SandboxBusy:
            pass  # the parent's box is in use by its own replay or research: the clean image, no wait
        except SandboxError as exc:
            self.alert("warning", f"{child.id}: could not fork its parent's box, starting from the clean image ({str(exc)[:160]})",
                       **environment("sail", exc))
        self.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["endowment_usd" if staked_by_house else "fork_endowment_usd"], "box_forked": forked,
                                            "reason": reason, "new_code": bool(code), "staked_by": "house" if staked_by_house else "parent"}, agent=parent.id)
        if passed_replay:
            self.evaluator.seat(child.id, 1, "its code passed replay as its parent's candidate")
            self._state["tried"][child.id] = child.code_sha256
            self.seat(child)
        return child

    def _mutated_params(self, parent: Agent, *, seed: str) -> dict[str, Any] | None:
        """Reject structural failures and duplicate living programs before buying a probe."""
        excluded = [a.params for a in self.registry.living()
                    if a.code_sha256 == parent.code_sha256 and a.niche == parent.niche]
        try:
            return mutate(parent.params, seed=seed, needs=parent.needs, excluded=excluded)
        except ValueError as exc:
            identity = hashlib.sha256(json.dumps([parent.code_sha256, parent.params, parent.needs, seed], sort_keys=True).encode()).hexdigest()
            self.ledger.append('agent.mutation', {'status': 'rejected', 'reason': str(exc), 'seed': seed,
                'counted_as_trial': False}, agent=parent.id, id=f'mutation:{parent.id}:{identity}')
            return None

    # --------------------------------------------------------------- research
    def _research_budget_kind(self, agent: Agent) -> str:
        """A resumed session keeps its provider even when a cohort assignment changes."""
        pending = self.research_jobs.active(agent.id)
        saved = self.research_jobs.get(pending['session']) if pending else None
        checkpoint = (saved or {}).get('checkpoint') or {}
        settings = self.game.get('research') or {}
        provider = getattr(self.researcher, 'provider', None)
        if not checkpoint and hasattr(provider, 'settings_for'):
            settings = provider.settings_for(agent, settings)
        profile = checkpoint.get('profile', settings.get('profile'))
        return 'openai' if profile == 'openai_luna' else 'sail'

    def research_due(self, agent: Agent) -> bool:
        """Is a research pass due for this agent now: every check below must pass.

        The campaign's budget (`pacer.may_spend`) is asked after the checks that read and write nothing
        (Sept 24, 2026, R6-perf): it cost 17.7 ms a call on a copy of the 17:27Z snapshot (a scan of
        campaigns.sqlite's 50,360 commitments and two sums over them), and this was asked of every
        living agent on every tick, about 2 s of a tick's CPU there, though most agents are not due for
        their own reasons (a pass in hand, its interval not over). The answer is the same conjunction of
        the same checks. The Sail research cap and the gate, which write (an `ops.budget` row when the
        cap opens or closes, `research.gate` rows), are still asked only after the budget, as before."""
        if self._closing.is_set() or not agent.alive or self.researcher is None or not self.settings.research:
            return False
        if self.paused():
            return False
        kind = self._research_budget_kind(agent)
        if self.deploying():
            return False  # existing sessions are checkpointed; do not add work during staging
        pending = self.research_jobs.active(agent.id)
        if pending:
            if self.clock() < pending["available"]:
                return False
            if not self.pacer.may_spend(kind):
                return False
            # A job still `queued` has bought nothing yet: the tick enqueues every due agent at once and
            # the research lane's workers take them in turn (up to 34 waited at once, Sept 24 00Z), so it
            # waits for the Sail cap like a new session; one under way resumes (review of #236).
            return not (pending.get("status") == "queued" and kind == "sail" and self._sail_research_capped())
        rules = self.game.get("research") or {}
        if self.economy.balance(agent.id) <= Decimal(str(rules.get("min_credits_usd", "0.10"))) * 2:
            return False
        last = max(float(self._state["last_research"].get(agent.id) or 0), self.research_jobs.last_finished(agent.id))
        # A new execution failure is actionable evidence. Give it one prompt response,
        # retaining the provider budget, earned-credit and durable-job checks.
        refusal = self.ledger.last('book.refused', agent=agent.id)
        book = self.book_of(agent)
        prompt = (refusal is not None and book is not None and refusal.payload.get('book') == book.name
                  and _epoch(refusal.at) > last and self.clock() - last >= 60)
        interval = 0.0
        if not prompt:
            interval = self.research_interval_hours(agent) * 3600
            if self.clock() - last < interval:
                return False
        if not self.pacer.may_spend(kind):
            return False
        if kind == "sail" and self._sail_research_capped():
            return False  # no NEW Sail session while the last hour's Sail research spend is at the cap (L2)
        return True if prompt else self._gate(agent, last, interval)

    def _gate(self, agent: Agent, last: float, interval: float) -> bool:
        """Back off research that keeps coming back empty while nothing about the agent has changed.

        Measured Sept 21-22, 2026: 82% of research sessions in twelve hours ended with no
        candidate and no replay ("no credits justified"), about $64 of $94, and agents cited the
        same missing inputs pass after pass. After `after` empty passes in a row the interval
        doubles per further empty pass (up to `max_factor`), unless something new reached the
        agent's record since its last pass: a fill, a settlement, a verdict or a new strategy.
        A deterministic `sample_percent` of the skipped windows run anyway, so what the gate
        misses stays measurable (`research.gate` rows with sampled=true).

        With the Jev floor wired (`league/sensors.py`) its gate decides instead, on the same dials:
        exact triggers beyond these four, explicit blockers, a heartbeat and Jev's note relevance
        (`league/research_gate.py`). This body is the fallback when it is switched off."""
        rules = dict((self.game.get("research") or {}).get("gate") or {})
        if not rules.get("enabled", True):
            return True
        if self.jev_floor is not None and self.jev_floor.gate is not None:
            return self.jev_floor.research_due(agent, last=last, due=True)
        streak = int((self._state.get("empty_research") or {}).get(agent.id) or 0)
        after = int(rules.get("after", 2))
        if streak < after:
            return True
        since = now_iso(lambda: last)
        for kind in ("book.fill", "book.settle", "eval.verdict", "agent.strategy"):
            # A pause or resume of its entries restates its strategy (X1): not a new one.
            row = allocator_module.adopted_strategy(self.ledger, agent.id) if kind == "agent.strategy" else self.ledger.last(kind, agent=agent.id)
            if row is not None and row.at > since:
                self._gate_note(agent, "run", f"new {kind} since the last pass", streak, last)
                return True
        factor = min(2 ** (streak - after + 1), float(rules.get("max_factor", 8)))
        if self.clock() - last >= interval * factor:
            self._gate_note(agent, "run", f"backoff x{factor:g} elapsed after {streak} empty passes", streak, last)
            return True
        digest = hashlib.sha256(f"{agent.id}:{int(last)}".encode()).digest()
        if digest[0] * 100 < 256 * float(rules.get("sample_percent", 10)):
            self._gate_note(agent, "sample", f"{streak} empty passes and nothing new; sampled to measure misses", streak, last)
            return True
        self._gate_note(agent, "skip", f"{streak} empty passes and nothing new; next pass after x{factor:g} the interval", streak, last)
        return False

    def _gate_note(self, agent: Agent, decision: str, reason: str, streak: int, last: float) -> None:
        """One `research.gate` row per agent per research window, not one per tick."""
        with self._state_lock:
            noted = self._state.setdefault("gate_noted", {})
            key = f"{int(last)}:{decision}"
            if noted.get(agent.id) == key:
                return
            noted[agent.id] = key
        self.ledger.append("research.gate", {"agent": agent.id, "decision": decision, "reason": reason,
                                             "empty_streak": streak, "sampled": decision == "sample"}, agent=agent.id)

    def _note_research_result(self, agent_id: str, outcome: Any) -> None:
        """Count empty passes in a row: no candidate, no replay trial and no Merton strategy. A session
        that is no completed pass (`research_gate.completed_pass`: a provider failure) moves nothing,
        as it moves nothing in the Jev gate's streak (Sept 24, 2026)."""
        from .research_gate import completed_pass

        if not completed_pass({"reason": getattr(outcome, "reason", "")}):
            return
        useful = bool(getattr(outcome, "candidate", None) or int(getattr(outcome, "trials", 0) or 0)
                      or getattr(outcome, "consulted", ""))
        with self._state_lock:
            streaks = self._state.setdefault("empty_research", {})
            streaks[agent_id] = 0 if useful else int(streaks.get(agent_id) or 0) + 1

    def idle_run(self, agent: Agent) -> dict[str, int]:
        """This agent's unbroken run of wakes that did nothing, and why (see `_note_wake`)."""
        row = self._state["idle"].get(agent.id) or {}
        return {"barren": int(row.get("barren") or 0), "shut": int(row.get("shut") or 0), "offered": int(row.get("offered") or 0)}

    def idle_reason(self, agent: Agent) -> str:
        """Why this agent should research NOW rather than on its usual clock, or "" if it should not.

        Measured over the floor's first evening: agents woke for hours into a wall -- the sports
        desk saw live markets and found none inside the band it was born with, and every equity
        desk answered "the session is closed" from Friday night until Monday. Both are wasted
        learning time, and both are fixed in the same place: by the strategy, in a research pass.
        So a run of either kind pulls the next pass forward to the idle interval."""
        rules = dict((self.game.get("research") or {}).get("idle") or {})
        idle = self.idle_run(agent)
        if idle["barren"] >= int(rules.get("barren_wakes", 10)):
            return f"{idle['barren']} wakes in a row with {idle['offered']} live markets in front of you and nothing done: your rules are not meeting this market"
        if idle["shut"] >= int(rules.get("shut_wakes", 6)):
            return f"{idle['shut']} wakes in a row with nothing open to trade: this is bench time, and the bench is where a better strategy is written"
        return ""

    def _weakest(self, rules: Mapping[str, Any], *, specialty: str | None = None, exclude: Sequence[str] = (),
                 evidenced: bool = False, newcomer: Newcomer | None = None) -> Agent | None:
        """The agent a newcomer displaces, or None when nobody has earned displacing: the first of
        `_displaceable`, which holds the rules.

        `evidenced` (Sept 23, 2026): the newcomer has forward evidence of its own -- an Alpha Lab
        graduate that passed the House's replay and the sealed holdout, a replay-passed foundry card,
        a merged strategy, and since Sept 24, 2026 a dead author's retained research candidate -- and
        may take a seat inside its holder's grace when the holder is replay-only code (rung 0) or has
        never traded since its current program's opportunity. The Alpha Lab (`Lab._seat_for`,
        `_finish_birth`), the foundry (`Foundry._admit`), `enroll` and `_admit_orphan` pass it; the
        House's own mutation refill and a living author's research admission never do.

        `newcomer` (S1, Sept 24, 2026): who asks, for the rules that compare it with the resident -- its
        family's proof and its forward score (`Newcomer`). None: an unproven newcomer with no forward score."""
        rank = self._displaceable(rules, specialty=specialty, exclude=exclude, evidenced=evidenced, newcomer=newcomer)
        return rank[0][-1] if rank else None

    def _displaceable(self, rules: Mapping[str, Any], *, specialty: str | None = None, exclude: Sequence[str] = (),
                      evidenced: bool = False, newcomer: Newcomer | None = None,
                      why: dict[str, int] | None = None) -> list[tuple[Any, ...]]:
        """Every resident a newcomer may displace, the one with the LEAST EVIDENCE of an edge first;
        each row ends with the agent (`_weakest` takes the first, health.json counts them). `why`, when
        given, counts the rule that kept each resident of the search (the two-hour warning names it, R2).

        **The seat market's capacity** (R2, the close-the-gaps run, Sept 24, 2026):
        - S3, a stale seat: a newcomer with a positive forward score (the lab's forward windows, `Newcomer.forward`)
          may take the seat of a paper resident whose desk evidence clock has run -- its seat is older than the
          clock (the plain grace where none is measured) and than its fair chance, and a desk that keeps hours has
          closed a session since -- with no positive record of its own (no winner's standing, no positive forward
          window): past the S1 forward rule, the trading and the screen protections, which exist so a record can be
          measured and which the clock says has had its time (`_stale_seat`). Never inside its clock or its fair
          chance, never a real-money seat, never a proven family's member by an unproven newcomer, never one holding
          a position while its market is shut, and one displacement a desk a tick, as for everyone. At 15:06Z, 29
          paper seats were stale by this test (10 on the index ETFs, 5 options, 4 crypto-15m, 3 megacaps ...) and one
          waiter had a forward score to take one (a megacaps graduate, +0.000102 a block over 3 active blocks);
        - an evidenced newcomer asking for a desk the search closes (`_search_closed_desks`, `specialty`) is given no
          seat there: its waiters have left the queue (`_expire_waiters`), and the desk's cap is held at its members
          (`_follow_the_search`);
        - a desk whose proven family's program is owed births (R3, `_waiting_proven`) gives its next seat to them:
          a newcomer of another family asking for it (`specialty`) is given none until they are born.

        Never one on real money -- what that may cost is already bounded by the tuition, and the
        auditor put it there. Never a profitable one, however small its record. Never one too young
        to have had a fair chance. Of the rest, the one with the LEAST EVIDENCE of an edge.

        **The evidence clock** (S1, the close-the-gaps run, Sept 24, 2026). Measured on the T0 snapshot:
        103 deaths in 24 hours, median life 14.3 h, 70 of them before three fills, while a day-horizon
        desk needs one to three days per settlement; displacement took traders with 38, 26 and 24 fills,
        and mullins-14 holding a replay-passed candidate. So:
        - a paper seat's grace is the larger of the plain grace (`displace_after_epochs` epochs, twelve
          hours) and its desk's evidence clock (`evidence_clocks`: the median hours from a member's first
          fill to its third independent settlement, measured from the ledger every day), the clock in
          wall-clock hours on every desk (a desk that keeps hours still needs its twelve SESSION hours);
        - a resident with `FORWARD_RULE_FILLS` (3) fills of its own since its program's opportunity is
          displaced only by a newcomer whose forward score beats the resident's own forward record
          (`Lab.resident_forward`: the lab scores every resident's program, S2); with no record of its
          own YET there is nothing to compare, and it keeps its seat -- but a trader the lab can never
          score (`Lab.can_score`: an options or unreplayed desk, a blocked program) is judged as before,
          or its desk's waiters would starve for good (the review of #245);
        - a resident whose family is proven (the allocator's family record, `Allocator.family`) is never
          displaced by an unproven newcomer -- except one that has never traded and whose grace has run;
        - never-traded residents past their grace still go first, then the members of a family whose
          pooled forward record is negative after `losing_family_min_blocks` active blocks (such a family
          is not bred again, `_losing_family`), then the rest by rung, growth, blocks and purse.

        Sept 23, 2026 (the seat market follows evidence): 312 of 345 deaths since Sept 19 were
        displacements, 254 of them of rung-0 House mutations after a median three hours, while 20
        lab graduates, 6 replay-passed cards and 6 merged strategies waited because ~86 of 96
        residents were inside a protection. So with `evidenced` a rung-0 resident, or a rung-1 one
        that has never traded since its current program's opportunity, may be taken inside its
        grace; a desk that keeps hours is exempt until its first regular session has closed (the
        case the grace was written for, #190); and never a trader short of its record on any desk
        (`_trading_pending`), a winner, real money, or one holding a position while its market is
        shut. Replay-only code ranks before code that passed replay, and at most one resident a
        desk is displaced in a tick (`kill` stamps `_desk_displaced`), so churn stays bounded.

        Least evidence means, first and above everything, that it has never traded. Ranking by
        growth alone did the opposite of what it was for: an agent that has never placed an order
        has a mean growth of exactly 0.0, which sorts above every negative number, so the agents
        that never traded were the SAFEST on the floor and the ones doing the work were displaced.
        It killed hilibrand at 09:46 on Sept 20, 2026 -- the agent furthest up the ladder, twelve
        active blocks of the fifteen the screen wants -- while twenty-six agents that had never
        traded at all sat untouched. An agent that is trading and losing is being judged by the
        evaluator, which will kill it on its own evidence at twenty blocks; an agent that trades
        nothing is judged by nobody and costs a box and a seat for as long as it is left there.

        On a desk that keeps an exchange's hours (stocks, options) the chance is counted in the
        market's own time (Sept 23, 2026). The grace is regular-session time, not wall-clock time;
        an agent that is trading keeps its seat until it has closed the bunt line's
        `bunt_min_trades` or had `displace_trading_after_sessions` sessions (`_trading_pending`);
        one holding a position while its market is shut is not removed, because its own exit is at
        the next open and the House would only sell it there instead; and a rewrite of an agent
        that has never traded does not restart its clock. Nine stock and option agents were
        displaced Sept 21-23 after a median 6.5 session hours, every one with fills and none with
        more than four closed trades, and three of them while holding contracts."""
        epoch = float(rules["epoch_seconds"])
        grace = float(rules.get("displace_after_epochs", 2)) * epoch
        clocks = self._desk_clocks()
        now = self.clock()
        stamp = None  # now, as a market-hours check reads it: made once, and only if a desk keeps hours
        bound = float(self.settings.desk_displacement_seconds)  # not the tick: it runs every 30 s since H5
        # Read from a copy (the review of #297): `kill` stamps a desk from whichever thread displaces -- the tick's births
        # pass, the lab's thread -- while this scan runs on the tick, the lab's thread or, since H5, the House lane's
        # foundry step (`Foundry.allocate`), and a desk's first stamp landing mid-read raised "dictionary changed size".
        recently = {desk for desk, at in dict(self._desk_displaced).items() if now - at < bound}
        newcomer = newcomer or Newcomer()

        def kept(rule: str) -> None:
            if why is not None:
                why[rule] = why.get(rule, 0) + 1

        if specialty is not None:
            if evidenced and specialty in self._search_closed_desks((specialty,)):
                kept("the search closes the desk")
                return []  # R2: no seat is made on a desk the search closes; its waiters have left the queue
            owed: dict[str, set[str]] = {}
            for w in self.seat_waiters().get("proven") or ():
                owed.setdefault(str(w.get("niche")), set()).add(str(w.get("family")))  # every owed family: the review of #276
            if specialty in owed and newcomer.family not in owed[specialty]:
                kept(f"held for the proven famil{'y' if len(owed[specialty]) == 1 else 'ies'} {', '.join(sorted(owed[specialty]))}'s births")
                return []  # R3: the desk's next seat is the proven family's program's
        newcomer_proven = self._family_proven(newcomer.family, newcomer.venue)
        # S3 (R2): a newcomer with a winning forward window may take a stale seat (`_stale_seat`).
        scored = newcomer.forward is not None and newcomer.forward > 0
        # H5 (Sept 25, 2026): inside one births pass the scan below is asked the same question over and over
        # -- once for each deferred research candidate of a full desk, 399 scans for 10 distinct questions on
        # the T0 snapshot -- so the pass keeps each answer (`_scan_memo`) while no one is born or dies. The
        # question is the desk, whether the newcomer is evidenced, whether its family is proven and its
        # forward score; `exclude` only drops residents from the answer, so it is applied to the kept one.
        # The review of #297: one thing the kept answer can miss with nobody born or dead is a research job the House
        # lane queues beside the pass (`_schedule_research`), which protects a replay-only resident from an evidenced
        # newcomer ("research in flight" below); before H5 research was queued on the tick, before the pass, so no
        # scan inside the pass could miss it. A kept answer asks the research queue again for those rows. Under a
        # burst the rule reads the queue for paper residents too, and no answer is kept.
        memo, question = self._scan_memo, None
        if why is None and memo is not None and memo["thread"] == threading.get_ident() and not self._burst:
            roster = self._roster()
            if memo["roster"] != roster:
                memo["roster"], memo["scans"] = roster, {}
            question = (specialty, bool(evidenced), bool(newcomer_proven), newcomer.forward, id(rules))
            kept_answer = memo["scans"].get(question)
            if kept_answer is not None:
                return [row for row in kept_answer if row[-1].id not in exclude
                        and not (evidenced and row[2] == 0 and self.research_jobs.active(row[-1].id))]
        skip = () if question is not None else exclude
        losing_blocks = int(rules.get("losing_family_min_blocks", 6))
        pooled = self.family_forward()
        rank = []
        for standing in self.standings():
            agent = self.registry.get(standing.agent)
            if agent.id in skip or (specialty is not None and agent.specialty != specialty):
                continue
            if standing.rung >= 2:
                kept("real money")
                continue
            if standing.mean_growth > 0 or standing.score_growth > 0:
                kept("a winner")
                continue
            if agent.specialty in recently:
                kept("one displacement a desk a tick")
                continue  # one displacement a desk a tick
            opportunity = _epoch(agent.born_at)
            opportunity_seq = 0
            agent_grace = grace
            # S1: a paper seat's desk clock, in wall-clock hours (0 where none is measured: the plain grace).
            clock = clocks.get(agent.specialty or "", 0.0) if standing.rung >= 1 else 0.0
            niche = self.niche_of(agent)
            keeps_hours = standing.rung == 1 and niche is not None and niche.keeps_hours(agent.needs)
            if standing.rung == 0 and (self._burst or evidenced):
                # Completed research is the opportunity; waiting out an hour adds no evidence.
                # Queued/paid work and a late-qualified program must not die on a calendar timer.
                if self._burst:
                    opportunity = max(opportunity, self._burst['started'])
                if self.research_jobs.active(agent.id):
                    kept("research in flight")
                    continue
                if evidenced:
                    agent_grace = 0  # replay-only code makes way for code that passed replay
                else:
                    completed = sum(1 for e in self.ledger.iter(kinds='agent.research', agent=agent.id)
                        if e.payload.get('tool') == 'summary' and _epoch(e.at) >= opportunity
                        and not str(e.payload.get('reason') or '').startswith(('provider:', 'tool outcome unconfirmed')))
                    # A failed replay of its own code is a finished chance too. Sept 23, 2026: research is
                    # paced by record now (an agent with none waits three intervals), and without this a
                    # rung-0 agent that failed replay twice would hold its seat until the 72-hour cull.
                    completed += sum(1 for e in self.ledger.iter(kinds='eval.trial', agent=agent.id)
                                     if not e.payload.get('passed') and _epoch(e.at) >= opportunity)
                    if completed < self._burst['policy']['minimum_research_passes']:
                        kept("its research passes are not done")
                        continue
                    agent_grace = 0
            if standing.rung == 1:
                # A late replay pass or a new empty-record strategy has not had the old
                # program's trading opportunity (`_program_opportunity`).
                opportunity, opportunity_seq = self._program_opportunity(agent, keeps_hours=keeps_hours)
                if self._burst:
                    from .episodes import completed
                    book = self.book_of(agent)
                    episodes = completed(self.ledger, agent.id, book.name, since_seq=opportunity_seq) if book else []
                    if len(episodes) >= int(CONSTITUTION['ladder']['completed_exposures']['min_episodes']):
                        # An evidenced non-winner can make room once it has finished actual risk.
                        # The paper clock remains a fallback for strategies without that record.
                        if self.research_jobs.active(agent.id):
                            kept("research in flight")
                            continue
                        agent_grace = 0
            # Its own pause (X1; review of #249, P3): held buys are not activity, and a resident paused past
            # the grace is displaceable like one that never traded -- no trader's, screen's or grace's
            # wait, ranked with the idle. A winner and real money stay protected, as for everyone.
            idle_pause = standing.rung == 1 and self._paused_past(agent, max(grace, clock), now)
            if idle_pause:
                agent_grace = 0
            traded = False
            if standing.rung == 1 and (keeps_hours or evidenced) and not idle_pause:
                # Has it traded since its current program's opportunity? Read for every desk when an
                # evidenced newcomer asks (a never-traded seat is what it may take); the plain
                # tournament reads it only where the session rules below need it.
                traded = bool(self.ledger.read(kinds="book.fill", agent=agent.id, after=opportunity_seq, limit=1))
            book = None
            if keeps_hours:
                # The rebuilt league was born on a Saturday. Twelve wall-clock hours later
                # its equity agents were displaced before their first market session. Start
                # their paper-seat grace at an actual offered opportunity (or a legacy fill),
                # not at a weekend birth. Replay-only agents still have their normal deadline.
                first = self._first_row(("agent.woke", "book.fill"), agent.id, opportunity_seq,
                                        lambda e: e.kind == "book.fill" or (e.payload.get("ok") and int(e.payload.get("offered") or 0) > 0))
                if first is None:
                    kept("never offered a session since its program's opportunity")
                    continue
                opportunity = max(opportunity, _epoch(first.at))
                book = self.book_of(agent)
                if book is not None and agent.id in book.accounts:
                    if stamp is None:
                        stamp = now_iso(self.clock)
                    held = list(book.account(agent.id).holdings.values())  # copied at once: wakes run beside this
                    if any(market_hours(h.instrument, stamp) is False for h in held):
                        # Its own exit closes this at the next open. Displaced now, the House
                        # would sell it there instead (scholes-23 at 07:11Z on Sept 23, mid-basket).
                        kept("holding a position while its market is shut")
                        continue
            # S3 (R2): its desk's evidence clock has run with no positive record of its own; a newcomer with a winning
            # forward window need not wait for the record the protections below exist to let it measure.
            stale = (scored and standing.rung == 1 and not idle_pause and self._stale_seat(agent, opportunity, clock, grace, keeps_hours, now)
                     and not self._awaits_settlement(agent))
            if keeps_hours:
                if traded and not stale and self._trading_pending(agent, book, opportunity, now, rules):
                    kept("a trader short of its record")
                    continue
            elif evidenced and traded and not stale and self._trading_pending(agent, self.book_of(agent), opportunity, now, rules):
                kept("a trader short of its record")
                continue  # a trader short of its record is not taken by an evidenced newcomer either
            if standing.rung == 1 and agent_grace > 0 and not stale and agent.horizon == "day" \
                    and self._screen_pending(agent, opportunity_seq, now - opportunity):
                kept("its day screen is pending")
                continue
            if evidenced and standing.rung == 1 and not traded and (not keeps_hours or session_time(opportunity, now)[1] >= 1) \
                    and now - opportunity >= self._fair_chance(clock, grace):
                # A seat that has never traded since its program's opportunity: an evidenced
                # newcomer need not wait out its grace -- once the seat has had a fair chance to
                # trade (`_fair_chance`), so a newborn is never taken by the next waiter before it
                # could trade, and an idle old seat still makes way at once. A desk that keeps
                # hours is exempt until its first regular session has closed.
                agent_grace = 0
            if stale:
                agent_grace = 0
            # A desk that keeps hours offers nothing between the close and the next open: its grace
            # is counted in regular-session time. The desk's evidence clock is wall-clock hours (S1).
            seated = session_time(opportunity, now)[0] if keeps_hours else now - opportunity
            past_grace = (seated >= grace and now - opportunity >= clock) or idle_pause  # never `stale`: the proven rule reads it
            if agent_grace > 0 and not past_grace:
                kept("inside its grace or its desk's evidence clock")
                continue
            fills = self._own_fills(agent.id, after=opportunity_seq) if standing.rung == 1 and not idle_pause else 0
            has_traded = not idle_pause and (standing.active_blocks > 0 or traded or fills > 0)
            if not newcomer_proven and (has_traded or not past_grace) and self._family_proven(agent.family, agent.venue):
                kept("a proven family's member")
                continue  # S1: a proven family's resident is never displaced by an unproven newcomer
            if fills >= FORWARD_RULE_FILLS and not stale:
                # S1: a trader is displaced only by a newcomer whose forward score beats its own record -- while it
                # has one, or the lab can still give it one (`_forward_scorable`). A trader the lab never scores (an
                # options or unreplayed desk, a blocked program) is judged as before: no record could ever be
                # compared, and keeping its seat for that would starve its desk's waiters for good (review of #245).
                mine = self._resident_forward(agent)
                if (mine is not None or self._forward_scorable(agent)) \
                        and (newcomer.forward is None or mine is None or not newcomer.forward > mine):
                    kept("its forward record is not beaten by the newcomer's")
                    continue
            blocks, growth = pooled.get(agent.family, (0, 0.0))
            losing = blocks >= losing_blocks and growth <= -1e-9  # `_losing_family`'s line, read without its alert
            rank.append((has_traded, not losing, standing.rung, standing.mean_growth, standing.active_blocks,
                         float(self.economy.balance(agent.id)), agent))
        # Has it traded at all, a losing family first, replay-only first, then growth, how much, and its purse.
        rank.sort(key=lambda row: row[:6])
        if question is not None:
            memo["scans"][question] = rank
            return [row for row in rank if row[-1].id not in exclude]
        return rank

    def _paused_past(self, agent: Agent, grace: float, now: float) -> bool:
        """Whether the agent has held its own entries (X1, `pause_entries`) for `grace` seconds or more:
        a resident paused past its resident grace (the plain grace and its desk's evidence clock) holds
        no evidence of trading, for displacement and the seat report alike (review of #249, P3). The
        House's drain hold (`DRAIN_SESSION`) is not its own: a probe the House demotes between passes
        (an audit's veto after promotion) sits on practice under it until the next pass releases it,
        and a hold older than the grace read as a pause past it (the adversarial review of the hold,
        Sept 24, 2026)."""
        paused = self.registry.entries_paused(agent.id)
        if not paused or paused.get("session") == self.DRAIN_SESSION:
            return False
        return now - _epoch(str(paused.get("since") or now_iso(self.clock))) >= grace

    @staticmethod
    def _fair_chance(clock: float, grace: float) -> float:
        """How long a paper seat that has never traded since its program's opportunity is kept from an evidenced
        newcomer (seconds): its desk's evidence clock (`clock`, 0 where none is measured) capped at the plain grace
        (`grace`), and never less than `FAIR_CHANCE_FLOOR_SECONDS`. After that, if it still has not traded, an
        evidenced newcomer takes it at once; before the plain grace and the clock have run, no one else may.

        S1's principle: evidence is measured before a seat is lost. After Deploy B (08:31Z Sept 24, 2026) a
        never-traded paper seat had no grace at all against an evidenced newcomer, and a newcomer seated a minute
        earlier has never traded, so evidenced waiters displaced each other: of the 12 deaths to 09:34Z (median
        life 0.28 h), haghani-ld3630c lived 33 s, huang-h6d3302-3 2.3 min, haghani-ladcac2 3.8 min, huang-l5aa23e-3
        5.6 min, haghani-64 11 min, haghani-lbf6075 14 min -- each taken by the next graduate or retained candidate
        without a trade."""
        return max(FAIR_CHANCE_FLOOR_SECONDS, min(float(clock or 0.0), float(grace)))

    def _stale_seat(self, agent: Agent, opportunity: float, clock: float, grace: float, keeps_hours: bool, now: float) -> bool:
        """S3 (R2, the close-the-gaps run, Sept 24, 2026): has this paper seat outlived its desk's evidence clock with no
        positive record of its own? Its seat (its program's opportunity) is older than the clock -- the plain grace
        where none is measured, which is what the clock's own measurement says stands there -- and than its fair
        chance (`_fair_chance`: never under an hour); on a desk that keeps hours, a regular session has closed since;
        and its own forward window (`Lab.resident_forward`) is not positive. A winner's standing never reaches here
        (`_displaceable` keeps winners first). The evidence clock is the median hours from a member's first fill to
        its third independent settlement (measured at 08:32Z Sept 24: crypto-15m 2.8 h, crypto-strikes 3.2,
        crypto-alts 3.7, megacaps 4.4, index ETFs 19.2, sports 20.5, options 23.9, weather 31.8, prices 36.5): a
        resident past it has had the time a typical member takes to show three settlements."""
        stale_after = max(float(clock) if clock and clock > 0 else float(grace), self._fair_chance(clock, grace))
        if now - opportunity < stale_after:
            return False
        if keeps_hours and session_time(opportunity, now)[1] < 1:
            return False
        mine = self._resident_forward(agent)
        return mine is None or mine <= 0

    def _awaits_settlement(self, agent: Agent) -> bool:
        """Whether a practice resident holds an event contract still to settle (the review of #276, Sept 24, 2026). S3
        takes a seat whose desk's evidence clock has run with no positive record; a resident holding open event positions
        is waiting for exactly the settlements that clock measures, and displaced now its wind-down would sell them at
        the bid on the practice book and lose them (before S3 the trading protection kept such a trader until 3
        settlements or 3 sessions). So S3 waits for them; the other rules still apply to it."""
        book = self.book_of(agent)
        if book is None or book.real_money or agent.id not in book.accounts:
            return False
        held = list(book.account(agent.id).holdings.values())  # copied at once: wakes run beside this
        return any(h.instrument.asset_class == "event" and h.quantity != 0 for h in held)

    def _program_opportunity(self, agent: Agent, *, keeps_hours: bool = False) -> tuple[float, int]:
        """(when, ledger position) a rung-1 agent's current program was given its chance: its birth, its
        latest new program (`agent.strategy` with other code, parameters or NEEDS; never one of its own
        entry controls, which keep the seat and the record: X1, review of #249), or its latest seat on
        rung 1, whichever is last.

        A late replay pass or a new empty-record strategy has not had the old program's trading
        opportunity. Meriwether-8 passed replay at 00:21 and was displaced at 01:01 with zero forward
        blocks because its birth was already fourteen hours old. Recovered from the ledger, so it
        survives restarts; duplicate strategy rows do not buy another grace period.

        On a desk that keeps hours (`keeps_hours`), a rewrite of an agent that has never traded is NOT
        a new opportunity (Sept 23, 2026): research rewrote idle stock agents every few hours (mcentee-34
        three times in eight), each rewrite restarted the clock, and the agents that never traded
        outlived the ones that did.

        Remembered for each agent until it has a new `agent.born`, `agent.strategy` or `eval.verdict` row or its
        first fill (R6-perf, Sept 24, 2026): the seat market asks for every resident on every question, and in six
        ticks of a full league on a copy of the 17:27Z snapshot that was 2,256 reads of each agent's every verdict
        (81,096 rows parsed, 3.2 s). The answer is a fold of exactly those rows, so the same rows are the same answer."""
        first_fill = None
        if keeps_hours:
            found = self.ledger.read(kinds="book.fill", agent=agent.id, limit=1)  # its first fill, one row
            first_fill = found[0].seq if found else None
        newest = self.ledger.read(kinds=("agent.born", "agent.strategy", "eval.verdict"), agent=agent.id, limit=1, newest=True)
        read_from = (newest[-1].seq if newest else 0, first_fill)
        hit = self._opportunities.get((agent.id, keeps_hours))
        if hit is not None and hit[0] == read_from:
            return hit[1]
        opportunity, opportunity_seq = _epoch(agent.born_at), 0
        signature = None
        for entry in self.ledger.iter(kinds=("agent.born", "agent.strategy", "eval.verdict"), agent=agent.id):
            p = entry.payload
            if entry.kind == "agent.strategy" and p.get("control"):
                # Its own entry control (X1): a pause or resume restates the program, and an in-place edit
                # keeps its seat and its record, so neither is a new opportunity. Read as one, an edit bought
                # a fresh grace and cleared "traded since", which let an evidenced newcomer take a trader's
                # seat at once (review of #249).
                continue
            if entry.kind in ("agent.born", "agent.strategy"):
                current = (p.get("code_sha256"), p.get("params"), p.get("needs"))
                if current != signature:
                    if signature is None or not keeps_hours or (first_fill is not None and first_fill < entry.seq):
                        opportunity, opportunity_seq = _epoch(entry.at), entry.seq
                    signature = current
            elif p.get("decision") in ("seat", "promote", "demote") and p.get("to_rung") == 1:
                opportunity, opportunity_seq = _epoch(entry.at), entry.seq
        self._opportunities[(agent.id, keeps_hours)] = (read_from, (opportunity, opportunity_seq))
        return opportunity, opportunity_seq

    def _first_row(self, kinds: Any, agent_id: str, after: int, match: Callable[[Any], Any], *, page: int = 64) -> Any:
        """The first of an agent's rows of `kinds` after `after` that `match` accepts, or None: the rows `ledger.iter`
        gives, in the same order, read `page` at a time instead of 5,000 (R6-perf, Sept 24, 2026), so a question its
        first rows answer parses only those. In six ticks of a full league on a copy of the 17:27Z snapshot, the seat
        market's "offered a session since its program's opportunity?" parsed 60,495 rows in 414 questions."""
        while True:
            batch = self.ledger.read(kinds=kinds, agent=agent_id, after=after, limit=page)
            for entry in batch:
                if match(entry):
                    return entry
            if len(batch) < page:
                return None
            after = batch[-1].seq

    def _own_fills(self, agent_id: str, *, after: int = 0, enough: int = FORWARD_RULE_FILLS) -> int:
        """The agent's own fills after a ledger position, counted up to `enough`: venue and cross fills
        (a row that names no source is a test's), never dust, a venue fee or the House's closing sale."""
        count = 0
        for entry in self.ledger.iter(kinds="book.fill", agent=agent_id, after=after):
            p = entry.payload
            if p.get("source") in (None, "venue", "cross") and not str(p.get("reason") or "").startswith(HOUSE_CLOSING):
                count += 1
                if count >= enough:
                    break
        return count

    def _family_proven(self, family: str | None, venue: str | None) -> bool:
        """Whether a family's pooled record is proven: the allocator's family record (`Allocator.family`,
        Deploy A's P1; read, never recomputed here), "proven" or "swing". A family on no venue it names is
        read on both. False for no family, and whenever the record cannot be read."""
        if not family:
            return False
        reader = getattr(self.allocator, "family", None)
        if reader is None:
            return False
        for place in ([venue] if venue else list(REAL_BOOK)):
            try:
                record = reader(family, place)
            except Exception:  # noqa: BLE001 - `Allocator.family` never raises; an unreadable record proves nothing
                continue
            if record and (record.get("proven") or record.get("state") in ("proven", "swing")):
                return True
        return False

    def _resident_forward(self, agent: Agent, *, ranked: bool = False) -> float | None:
        """A resident's own forward record for the seat market (S2): the mean log growth per block of its
        current program's latest forward window (`Lab.resident_forward`), or, `ranked`, its forward score
        (only with the lab's `forward_min_active_blocks`). None without a lab or a record."""
        reader = getattr(getattr(self, "lab", None), "resident_forward", None)
        if reader is None:
            return None
        try:
            return reader(agent, ranked=ranked)
        except Exception:  # noqa: BLE001 - the lab's store is its own; no record is no record
            return None

    def _forward_scorable(self, agent: Agent) -> bool:
        """Whether the lab's forward windows can ever give a resident's current program a record (`Lab.can_score`).
        False with no lab. A read that fails counts as scorable: nobody loses a seat because a read failed."""
        reader = getattr(getattr(self, "lab", None), "can_score", None)
        if reader is None:
            return False
        try:
            return bool(reader(agent))
        except Exception:  # noqa: BLE001 - the lab's store is its own
            return True

    def evidence_clocks(self, *, fresh: bool = False) -> dict[str, Any]:
        """The desks' evidence clocks (S1, Sept 24, 2026; `measure_evidence_clocks`), kept in house.json
        (`evidence_clocks`: `at`, `epoch`, `days`, `desks`) and measured again when a day old -- at startup
        (`__init__`) and then at the first seat question after the day has passed. One info alert says
        what changed. Never raises: a measurement that fails keeps the last one and is tried an hour on."""
        with self._clock_lock:
            stored = self._state.get("evidence_clocks") or {}
            now = self.clock()
            if not fresh and stored and now - float(stored.get("epoch") or 0) < EVIDENCE_CLOCK_REFRESH_SECONDS:
                return stored
            try:
                with (getattr(self.registry, "_lock", None) or nullcontext()):
                    agents = list(self.registry.agents.values())
                desks = measure_evidence_clocks(self.ledger, agents, now)
            except Exception as exc:  # noqa: BLE001 - the last reading stands, and the floor goes on
                retry = {**stored, "epoch": now - EVIDENCE_CLOCK_REFRESH_SECONDS + 3600}
                with self._state_lock:
                    self._state["evidence_clocks"] = retry
                self.alert("warning", f"the desks' evidence clocks could not be measured ({type(exc).__name__}: {str(exc)[:160]})")
                return retry
            report = {"at": now_iso(self.clock), "epoch": now, "days": EVIDENCE_CLOCK_DAYS,
                      "settlements": EVIDENCE_CLOCK_SETTLEMENTS, "desks": desks}
            with self._state_lock:
                self._state["evidence_clocks"] = report
        measured = {d: row["hours"] for d, row in desks.items() if row.get("hours") is not None}
        before = {d: (row or {}).get("hours") for d, row in (stored.get("desks") or {}).items() if (row or {}).get("hours") is not None}
        if measured and measured != before:
            unmeasured = sorted(d for d, row in desks.items() if row.get("hours") is None)
            self.alert("info", "the desks' evidence clocks (median hours from a member's first fill to its third independent "
                               f"settlement, last {EVIDENCE_CLOCK_DAYS:g} days): "
                               + ", ".join(f"{d} {h:g} h" for d, h in sorted(measured.items(), key=lambda kv: kv[1]))
                               + (f"; not reached on {', '.join(unmeasured)} (the plain grace)" if unmeasured else ""),
                       evidence_clocks=desks)
        return report

    def _desk_clocks(self) -> dict[str, float]:
        """Desk -> its measured evidence clock in seconds, for the desks where one was reached."""
        desks = (self.evidence_clocks().get("desks") or {})
        return {desk: float(row["hours"]) * 3600.0 for desk, row in desks.items()
                if isinstance(row, Mapping) and row.get("hours") is not None}

    def _screen_pending(self, agent: Agent, since_seq: int, seated_for: float) -> bool:
        """Is a trading daily agent still short of the closed days its paper screen needs?

        A daily agent is judged on closed New York days, and the screen wants
        `min_active_blocks_day` of them, so it cannot be screened until a day and a half to two
        days after its seat. The twelve-hour grace let the league displace it first: of the 32
        paper agents that died Sept 21-22, 2026, 25 were displaced -- 24 of them daily, half after
        a day or less on paper -- and not one had reached a screen, so no daily agent could climb.
        One that is trading keeps its seat until that many days have closed since its opportunity,
        and never for more than a day beyond them. One that has never traded is judged by nobody
        and keeps the plain grace."""
        days = int(CONSTITUTION["ladder"]["paper"].get("min_active_blocks_day", 2))
        if seated_for >= (days + 1) * 86400:
            return False
        if next(iter(self.ledger.iter(kinds="book.fill", agent=agent.id, after=since_seq)), None) is None:
            return False
        # The screen's own view: finished blocks that began after the seat, past any accounting cutoff.
        closed = sum(1 for row in self.evaluator.blocks(agent.id, since_seq=since_seq) if row.get("horizon") == "day")
        return closed < days

    def _trading_pending(self, agent: Agent, book: Book | None, opportunity: float, now: float,
                         rules: Mapping[str, Any]) -> bool:
        """Is a trading agent on a desk that keeps hours still short of a record the bunt line can read?

        Real money needs `bunt_min_trades` closed trades (the constitution's allocator, read here
        and never changed), and a stock or option desk offers a round trip or two a session: an
        ETF basket bought in the last hour is sold at the next open. So an agent that is trading,
        hourly or daily, keeps its seat until it has closed that many trades, or until
        `displace_trading_after_sessions` (game.json) regular sessions have closed since its
        opportunity -- whichever comes first. Only its seat is kept: an unprofitable one is still
        displaced once either is reached, and a profitable one never was displaceable.

        The record is the one the bunt line reads (`allocator.bunt_ready`, Sept 24, 2026): closed trades,
        or on an event book `bunt_min_settled` settlements, each counted once per event
        (`allocator.closed_trades`). Before, only `bunt_min_trades` was read, so a Kalshi trader with three
        independent settlements and fewer than five closes was treated as short of a record it had."""
        owed = int(rules.get("displace_trading_after_sessions", 3))
        if session_time(opportunity, now)[1] >= owed:
            return False
        if book is None:
            return False
        line = CONSTITUTION["allocator"]
        closed, settled = allocator_module.closed_trades(self, agent.id, book.name)
        if book.name in allocator_module.EVENT_BOOKS and settled >= int(line.get("bunt_min_settled", 3)):
            return False
        return closed < int(line["bunt_min_trades"])

    # ------------------------------------------------------------ the seat market
    #: Who waits for a seat, in the order a freed seat goes to them (Sept 23, 2026): Alpha Lab
    #: graduates (replay and sealed holdout passed), replay-passed foundry cards, merged strategies.
    #: A House mutation is staked only when none of them waits. Since Sept 24, 2026 (S3) the retained
    #: research candidates of residents that died holding them rank with the graduates: neither class
    #: holds a desk from the other, and both hold theirs from cards and merged strategies.
    #: R3 (Sept 24, 2026): a proven family's program comes first on its desk (`_waiting_proven`): its births, House
    #: mutations of the program that proved it, until `economy.proven_family_members` living members run it.
    SEAT_WAITERS = ("proven", "graduates", "retained", "cards", "strategies")
    SEAT_WAITER_NAMES = {"proven": "proven family's birth", "graduates": "Alpha Lab graduate", "retained": "retained research candidate",
                         "cards": "replay-passed foundry card", "strategies": "merged strategy"}
    #: Their plurals, written out: an "s" appended made "8 merged strategys" in the owner's alerts (Sept 24, 2026).
    SEAT_WAITER_PLURALS = {"proven": "proven family's births", "graduates": "Alpha Lab graduates",
                           "retained": "retained research candidates", "cards": "replay-passed foundry cards",
                           "strategies": "merged strategies"}

    @classmethod
    def _waiters_named(cls, kind: str, count: int) -> str:
        """`count` waiters of `kind` in words: "1 merged strategy", "8 merged strategies"."""
        return f"{count} {cls.SEAT_WAITER_NAMES[kind] if count == 1 else cls.SEAT_WAITER_PLURALS[kind]}"
    #: What names a waiter of each class in its expiry key (house.json `seat_expired`, the `seat-expired:` ledger ids).
    SEAT_WAITER_IDS = {"proven": "family", "graduates": "candidate", "retained": "session", "cards": "card", "strategies": "strategy"}
    #: S3 (Sept 24, 2026): a dead author's retained candidate waits for a seat this long after its author's
    #: death (its replay grows old), and the House picks up, once, the candidates of authors that died in
    #: this window before the rule was deployed (their admissions were cancelled with them).
    RETAINED_TTL_SECONDS = 72 * 3600
    RETAINED_CANCELLED = "parent retired or changed; candidate evidence retained"

    def _waiting_graduates(self) -> list[dict[str, Any]]:
        """Lab graduates that passed the House's replay (and the sealed holdout where it applies)
        and wait for a seat: `graduations.state='passed'` in lab.sqlite, read through the lab's own
        query and never written. [] without a lab, or when its table cannot be read. A graduate waits
        from the ledger's `lab.graduate:<id>:passed` row, written once, as `Lab.waiting` counts it: the
        table's `at` moves at every retry of its birth (every ten minutes), so read from there no
        graduate ever waited more than ten minutes (R2, Sept 24, 2026)."""
        query = getattr(getattr(self, "lab", None), "_q", None)
        if query is None:
            return []
        try:
            rows = query("SELECT candidate, niche, family, at, detail FROM graduations WHERE state='passed' ORDER BY at")
        except Exception:  # noqa: BLE001 - the lab's table is its own; read again on the next tick
            return []
        out = []
        for r in rows:
            ident = str(r["candidate"])
            passed = self.ledger.get(f"lab.graduate:{ident}:passed")
            out.append({"candidate": ident, "niche": str(r["niche"] or ""), "family": str(r["family"] or ""),
                        "since": _epoch(passed.at) if passed is not None else float(r["at"] or 0), "detail": str(r["detail"] or "")[:120]})
        return out

    def _waiting_cards(self) -> list[dict[str, Any]]:
        """Foundry cards that passed replay and were never born (`Foundry.inventory`), each waiting from its passing
        evaluation (`Foundry.evaluations`, as the scoreboard dates it) or, unread, from its creation."""
        if self.hypotheses is None:
            return []
        try:
            cards = self.hypotheses.inventory()
            evaluations = self.hypotheses.evaluations() if hasattr(self.hypotheses, "evaluations") else {}
        except Exception:  # noqa: BLE001 - the foundry's fold is its own; read again on the next tick
            return []
        out = []
        for c in cards:
            passed = (evaluations.get(str(c.get("id"))) or {}).get("_at")
            out.append({"card": str(c.get("id")), "niche": str(c.get("niche") or ""), "family": str(c.get("family") or ""),
                        "since": _epoch(passed) if passed else float(c.get("created_epoch") or 0)})
        return out

    def _waiting_strategies(self) -> list[dict[str, Any]]:
        """Merged strategies (`league/strategies`) not yet born and not refused at their current
        file version: what `enroll` will try next. Its desk is the one its literal NEEDS would place it
        on (`niches.match`, read without running it; "" when they cannot be read: its birth decides);
        `replaces`, a corrected child whose defect a living resident still runs, whose seat it takes
        (`_defective_resident`); it waits from when the House first saw it waiting (house.json
        `seat_seen`: a merge has no time of its own on the ledger)."""
        from . import strategies
        from .lab import static_literal

        known = {a.founder for a in self.registry.agents.values()}
        refused = self._state.get("enroll_refused", {})
        now = self.clock()
        out = []
        for row in strategies.all_strategies():
            if row["name"] in known or refused.get(row["name"]) == code_sha(row["code"]):
                continue
            try:
                niche = niches_module.match(static_literal(row["code"], "NEEDS") or {}, self.niches)
            except Exception:  # noqa: BLE001 - a desk that cannot be read is decided at its birth
                niche = None
            repair = isinstance(row.get("repair"), Mapping)
            with self._state_lock:
                since = self._state.setdefault("seat_seen", {}).setdefault(f"strategies:{row['name']}", now)
            out.append({"strategy": str(row["name"]), "niche": niche.id if niche is not None else "", "repair": repair,
                        "family": str(row.get("family") or ""), "since": float(since),
                        "replaces": bool(repair and self._running_defect(self._defective_shas(row)))})
        with self._state_lock:
            waiting = {f"strategies:{w['strategy']}" for w in out}
            seen = self._state.setdefault("seat_seen", {})
            for key in [k for k in seen if k.startswith("strategies:") and k not in waiting]:
                seen.pop(key, None)  # born, refused or gone: its wait is over
        return out

    def seat_waiters(self, *, fresh: bool = False) -> dict[str, list[dict[str, Any]]]:
        """Everyone waiting for a seat, by class in `SEAT_WAITERS` order -- never a waiter the search has closed,
        which has left the queue with its reason (`_expire_waiters`, R2). Cached for a minute: the refill,
        `enroll` and health.json all ask within one tick."""
        hit = self._data_cache.get("seat_waiters")
        if hit and not fresh and self.clock() - hit[0] < 60:
            return hit[1]
        raw = {"proven": self._waiting_proven(), "graduates": self._waiting_graduates(), "retained": self._retained_waiting(left=True),
               "cards": self._waiting_cards(), "strategies": self._waiting_strategies()}
        value = self._expire_waiters(raw)
        self._data_cache["seat_waiters"] = (self.clock(), value)
        return value

    # ------------------------------------------------- the seat market's capacity (R2)
    def _waiter_key(self, cls: str, waiter: Mapping[str, Any]) -> str:
        """`<class>:<its id>`: what names a waiter in house.json `seat_expired` and its ledger row."""
        return f"{cls}:{waiter.get(self.SEAT_WAITER_IDS[cls])}"

    def _search_closed_desks(self, desks: Collection[str] = ()) -> dict[str, str]:
        """Desk -> why the search closes it (R2, the close-the-gaps run, Sept 24, 2026): what the search would put
        on that desk no more, read from the search's own functions and never recomputed here --
        - the foundry's closed desks (E2, `Foundry._closed_desks`): game.json `hypotheses.closed_desks` until a
          family that lived there shows a positive pooled forward record over `closed_reopen_blocks` active
          blocks ON THAT DESK. At 15:06Z kalshi-crypto-15m was closed (8 families with three blocks there, every
          one negative: crypto-15m-favorites 44 blocks, -0.855) and kalshi-crypto-strikes had reopened (the lab's
          crypto-strikes-lab-955dae, 17 blocks, +0.234, on real money since 02:00Z; crypto-strikes-lab-1b9d16, 7, +0.026);
        - the lab's idle desks among `desks` (E1, `Lab._idle_desk`): offered markets and no intent for
          `lab.idle_desk_hours` (48), and no feed the desk asked for arrived in that time.
        The foundry's answer is kept for SEARCH_CLOSED_TTL_SECONDS (its rule reads every block of every agent that
        lived on those desks), the lab's is its own ten-minute memo a desk. {} without either; a read that fails
        closes nothing."""
        now = self.clock()
        hit = self._data_cache.get("search_closed")
        if hit is not None and now - hit[0] < SEARCH_CLOSED_TTL_SECONDS:
            closed = dict(hit[1])
        else:
            closed = {}
            reader = getattr(self.hypotheses, "_closed_desks", None) if self.hypotheses is not None else None
            if reader is not None:
                try:
                    closed = {str(desk): f"the foundry's closed desk (E2): {why}" for desk, why in dict(reader()).items()}
                except Exception:  # noqa: BLE001 - an unreadable record closes nothing
                    closed = {}
            self._data_cache["search_closed"] = (now, dict(closed))
        idle = getattr(getattr(self, "lab", None), "_idle_desk", None)
        for desk in desks:
            if not desk or desk in closed or idle is None:
                continue
            try:
                why = idle(desk)
            except Exception:  # noqa: BLE001 - the lab's record is its own; an unread one closes nothing
                why = None
            if why:
                closed[desk] = f"the lab's idle desk (E1): {why}"
        return closed

    def _waiter_forward(self) -> dict[str, float]:
        """The lab's ranked forward scores (`Lab.forward_scores`, one query): what a waiting graduate's own forward
        window says (the lab scores the graduates waiting for seats first, `Lab.forward_due`). {} without a lab."""
        reader = getattr(getattr(self, "lab", None), "forward_scores", None)
        if reader is None:
            return {}
        try:
            return dict(reader())
        except Exception:  # noqa: BLE001 - the lab's store is its own; no score expires nobody
            return {}

    def _expiry(self, cls: str, waiter: Mapping[str, Any], closed: Mapping[str, str],
                scores: Mapping[str, float]) -> tuple[str, str] | None:
        """(rule, why) a waiter leaves the seat queue, or None (R2, Sept 24, 2026): its desk is one the search closes
        (`_search_closed_desks`) -- except a merged corrected child whose defect a living resident still runs, which
        takes that resident's seat rather than a new one -- or, for a lab graduate, its own forward window loses
        (`Lab.forward_score` at or below zero: the search tape only admits, and the lab holds such a graduate before
        its birth too, `Lab._hold`). A proven family's births never expire: `_waiting_proven` owes them."""
        if cls == "proven":
            return None
        desk = str(waiter.get("niche") or "")
        if desk and desk in closed and not (cls == "strategies" and waiter.get("replaces")):
            return "closed", f"its desk {desk} is closed by the search: {closed[desk]}"
        if cls == "graduates":
            forward = scores.get(str(waiter.get("candidate")))
            if forward is not None and forward <= 0:
                return "forward", (f"its own forward window loses ({forward:+.6f} a block on data after its code was frozen, "
                                   "Lab.forward_score): the search tape only admits")
        return None

    def _expire_waiters(self, raw: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        """The waiters that remain once those the search has closed have left (R2 (1), Sept 24, 2026). A waiter
        leaves once, with its reason: house.json `seat_expired` (kept SEAT_EXPIRED_KEEP_SECONDS), one
        `route.decision` row (`seat-expired:<class>:<id>`, route "expired"), and an info alert at most once an hour
        a desk. An expired retained candidate is held by the admission pass, never seated, until its desk reopens or
        its TTL drops it (`_admit_orphan`), an expired merged strategy is not enrolled (`enroll`), an expired card's
        desk is kept from the foundry's admission (`_refill`), and no seat is made for an expired graduate on a
        closed desk (`_displaceable`, `_follow_the_search`). None is counted as waiting while its reason holds: not in
        health.json, not in the refusals, not in the desks the waiters reserve.

        Measured at 15:06Z: 21 of the 82 waiters would have left -- the 20 of kalshi-crypto-15m (3 graduates, 6
        cards, 4 retained candidates, 7 merged corrected children whose defective code no living agent runs) and
        a megacaps graduate whose window lost -0.000142 a block over 4 active blocks.

        A waiter that left is asked again each pass, and is a waiter again once its reason is gone -- its desk
        reopened, its forward window no longer loses (the review of #276, Sept 24, 2026). Before, it stayed out for
        SEAT_EXPIRED_KEEP_SECONDS whatever happened: the foundry reopens a closed desk on one family's pooled record
        there (kalshi-crypto-strikes at 15:06Z, on +0.234 over 17 active blocks and +0.026 over 7) and the House
        reads that through a ten-minute cache, so the waiters of a desk that reopened stayed uncounted for a week
        while the lab and the foundry, which never read the House's expiry, seated them there, and a retained
        candidate was dropped for good by the next admission pass. Its ledger row stays (the first reason stands);
        a second departure is kept in house.json and told as the first was."""
        desks = {str(w.get("niche") or "") for rows in raw.values() for w in rows}
        closed = self._search_closed_desks(desks)
        scores = self._waiter_forward() if raw.get("graduates") else {}
        now = self.clock()
        with self._state_lock:
            expired = self._state.setdefault("seat_expired", {})
            for key in [k for k, row in expired.items() if now - float((row or {}).get("epoch") or 0) > SEAT_EXPIRED_KEEP_SECONDS]:
                expired.pop(key, None)
            known = set(expired)
        out: dict[str, list[dict[str, Any]]] = {}
        leaving: list[tuple[str, Mapping[str, Any], str, tuple[str, str]]] = []
        back: list[str] = []
        for cls in self.SEAT_WAITERS:
            kept = []
            for waiter in raw.get(cls) or ():
                key = self._waiter_key(cls, waiter)
                why = self._expiry(cls, waiter, closed, scores)
                if why is None:
                    kept.append(dict(waiter))
                    if key in known:
                        back.append(key)  # its desk reopened, or its window no longer loses: a waiter again
                elif key not in known:
                    leaving.append((cls, waiter, key, why))
            out[cls] = kept
        if back:
            with self._state_lock:
                for key in back:
                    self._state["seat_expired"].pop(key, None)
        if leaving:
            self._record_expired(leaving)
        return out

    def _record_expired(self, leaving: Sequence[tuple[str, Mapping[str, Any], str, tuple[str, str]]]) -> None:
        """Write the waiters that leave the queue (`_expire_waiters`): state, one ledger row each, an info alert a desk."""
        now = self.clock()
        stamp = now_iso(self.clock)
        by_desk: dict[str, list[tuple[str, str, str]]] = {}
        with self._state_lock:
            expired = self._state.setdefault("seat_expired", {})
            for cls, waiter, key, (rule, why) in leaving:
                expired[key] = {"class": cls, "desk": str(waiter.get("niche") or ""), "rule": rule, "why": why[:300],
                                "at": stamp, "epoch": now, "since": waiter.get("since")}
        for cls, waiter, key, (rule, why) in leaving:
            since = float(waiter.get("since") or 0) or None
            waited = round(max(0.0, now - since) / 3600, 2) if since else None
            try:
                self.ledger.append("route.decision", {"task": f"seat:{key}", "route": "expired", "model": None, "reason": why[:600],
                                                      "evidence": {"class": cls, "desk": str(waiter.get("niche") or "") or None,
                                                                   "rule": rule, "waited_hours": waited}},
                                   id=f"seat-expired:{key}"[:200])
            except LedgerConflict:
                pass  # written by an earlier House with other words: the first reason stands
            by_desk.setdefault(str(waiter.get("niche") or "") or "an unknown desk", []).append((cls, rule, why))
        with self._state_lock:
            told = self._state.setdefault("seat_expired_told", {})
            tell = [desk for desk in by_desk if now - float(told.get(desk) or 0) >= 3600]
            for desk in tell:
                told[desk] = now
        for desk in tell:
            rows = by_desk[desk]
            classes = ", ".join(self._waiters_named(c, n)
                                for c, n in sorted({c: sum(1 for x in rows if x[0] == c) for c, _, _ in rows}.items()))
            self.alert("info", f"{len(rows)} waiter{'' if len(rows) == 1 else 's'} for {desk} left the seat queue ({classes}): {rows[0][2][:240]}",
                       desk=desk, expired=len(rows), rule=rows[0][1])

    def _follow_the_search(self) -> dict[str, dict[str, int]]:
        """R2 (3), Sept 24, 2026: fewer seats where the search is closed. While the foundry closes a desk
        (`Foundry._closed_desks`, `_search_closed_desks`), its cap is held at its living members, never above its
        niches.json cap: no newcomer from outside is born there -- not the lab's graduates that passed before the
        rule, not a card, not a House mutation -- and no evidenced newcomer is given a seat there (`_displaceable`); it
        shrinks as its members die. Two ways still end one for one there, never growing it: a resident's own research
        candidate (`_admission_gate`, the plain tournament: a resident past its grace makes way), and a merged corrected
        child whose defect a resident still runs (`enroll`, which then retires the defect). The niches.json cap comes
        back when the desk reopens. Returns desk -> {"cap", "base", "members"} for the desks held.
        At 15:06Z: kalshi-crypto-15m, 10 members, closed (and cut to 8 in niches.json: see its note)."""
        closed = self._search_closed_desks()
        base = getattr(self, "_base_caps", None)
        if base is None:
            base = self._base_caps = {desk: int(niche.max_members) for desk, niche in self.niches.items()}
        held: dict[str, dict[str, int]] = {}
        with self._state_lock:
            stamped = self._state.setdefault("closed_caps", {})
            for desk, niche in self.niches.items():
                cap = int(base.get(desk, niche.max_members))
                if desk in closed:
                    members = self.members(desk)
                    niche.max_members = min(cap, members)
                    held[desk] = {"cap": niche.max_members, "base": cap, "members": members}
                    stamped.setdefault(desk, now_iso(self.clock))
                elif desk in stamped:
                    niche.max_members = cap  # reopened: its niches.json cap again
                    stamped.pop(desk, None)
        return held

    def _sail_runway(self) -> dict[str, Any] | None:
        """Sail's runway as the House's Sail meter measures it (league/budget.py `Budget.check`: every fifteen minutes an
        `ops.budget` "sail" row with the balance read from Sail and `spent_usd`, its fall since the reading before; a
        top-up is a rise and never a fall): the latest balance less `budgets.sail_reserve_usd`, over the falls of the
        readings in the trailing SAIL_BURN_WINDOW_SECONDS scaled to a day. None without readings spanning
        SAIL_BURN_MIN_SPAN_SECONDS. Read at most every ten minutes. At 15:06Z: $162.30, $34.88 a day, 4.51 days."""
        now = self.clock()
        hit = self._data_cache.get("sail_runway")
        if hit is not None and now - hit[0] < 600:
            return hit[1]
        rows = [e for e in self.ledger.read(kinds="ops.budget", limit=2000, newest=True)
                if e.payload.get("what") == "sail" and e.payload.get("balance_usd") is not None]
        window = [e for e in rows if now - _epoch(e.at) <= SAIL_BURN_WINDOW_SECONDS]
        value = None
        if len(window) >= 2 and _epoch(window[-1].at) - _epoch(window[0].at) >= SAIL_BURN_MIN_SPAN_SECONDS:
            span = _epoch(window[-1].at) - _epoch(window[0].at)
            falls = math.fsum(float(e.payload.get("spent_usd") or 0) for e in window[1:])  # each is its fall since the row before
            balance = float(window[-1].payload["balance_usd"])
            reserve = float(CONSTITUTION["budgets"].get("sail_reserve_usd") or 0)
            burn = falls / span * 86400.0
            runway = math.inf if burn <= 0 else max(0.0, balance - reserve) / burn
            value = {"balance_usd": round(balance, 2), "reserve_usd": round(reserve, 2), "burn_usd_per_day": round(burn, 2),
                     "runway_days": None if math.isinf(runway) else round(runway, 2), "unlimited": math.isinf(runway),
                     "readings": len(window), "hours": round(span / 3600, 1), "at": window[-1].at}
        self._data_cache["sail_runway"] = (now, value)
        return value

    def _population_rule(self) -> dict[str, Any] | None:
        """R2 (3), Sept 24, 2026: the population grows toward turbo.json `max_population` (the owner's ceiling, 64-128) only
        while Sail's runway (`_sail_runway`) is over `economy.population_runway_days` (1.5, the plan's floor); otherwise,
        or while the runway is unread, it is held at `economy.max_population_short_runway` (112, the population before
        this rule). Nobody is killed by it: a held league only stops growing, and shrinks to the held size as its members
        die. It sets the league's `max_population`, which every seat question reads (the lab's, the foundry's and the
        House's own), and says so once when it changes. Only under the owner's burst, where turbo.json sets the population;
        None otherwise. Sixteen more seats cost about $0.43 a day of Sail box time ($0.027 a box a day, measured Sept 23)
        and their research is inside the $2 an hour Sail research cap; at 15:06Z the runway was 4.5 days.

        Once held it grows again only over the floor by POPULATION_RUNWAY_BAND_DAYS (house.json `population_held`, so a
        restart keeps it), and a meter that cannot be read holds it like an unread one (the review of #276, Sept 24,
        2026): the runway moved 2.6% a reading at the 90th percentile and rose with no top-up in half the readings, so
        at the floor the rule flipped with the readings, alerting each time, and every window over the floor seated
        newcomers that no later window removed; an exception raised out of it and left turbo.json's 128 standing."""
        ceiling = getattr(self, "_population_ceiling", None)
        if not self._burst or ceiling is None:
            return None
        economy = self.game["economy"]
        held = min(int(ceiling), int(economy.get("max_population_short_runway", ceiling)))
        floor = float(economy.get("population_runway_days", 1.5))
        unread = ""
        try:
            sail = self._sail_runway()
        except Exception as exc:  # noqa: BLE001 - a meter that cannot be read grows nothing
            sail, unread = None, f" ({type(exc).__name__}: {str(exc)[:120]})"
        days = None if sail is None else (math.inf if sail.get("unlimited") else sail.get("runway_days"))
        with self._state_lock:
            was_held = bool(self._state.get("population_held"))
        over = floor + POPULATION_RUNWAY_BAND_DAYS if was_held else floor
        grows = days is not None and days > over
        with self._state_lock:
            self._state["population_held"] = not grows
        target = int(ceiling) if grows else held
        before = int(economy["max_population"])
        economy["max_population"] = target
        shown = f"unread{unread}" if days is None else ("unlimited" if math.isinf(days) else f"{days:.2f} days")
        band = f" ({floor:g} and the {POPULATION_RUNWAY_BAND_DAYS:g}-day band a held league grows again over)" if was_held else ""
        report = {"max_population": target, "ceiling": int(ceiling), "held_at": held, "runway_floor_days": floor,
                  "grows_over_days": over, "runway_days": None if days is None or math.isinf(days) else days, "sail": sail,
                  "rule": (f"toward the ceiling {ceiling}: Sail's runway {shown} is over {over:g} days{band}" if grows else
                           f"held at {held}: Sail's runway {shown} is not over {over:g} days{band}")}
        if target != before:
            self.alert("info" if grows else "warning", f"the league's population is now {target} (was {before}): {report['rule']}",
                       population=target, runway_days=report["runway_days"])
        self._population_report = report
        return report

    def _desk_caps(self) -> dict[str, dict[str, Any]]:
        """Each open desk's cap, members and the waiters that remain for it (health.json `seats.caps`)."""
        waiters = self.seat_waiters()
        waiting: dict[str, int] = {}
        for rows in waiters.values():
            for w in rows:
                if w.get("niche"):
                    waiting[str(w["niche"])] = waiting.get(str(w["niche"]), 0) + 1
        base = getattr(self, "_base_caps", None) or {}
        return {desk: {"cap": int(niche.max_members), "base": int(base.get(desk, niche.max_members)), "members": self.members(desk),
                       "waiting": waiting.get(desk, 0)}
                for desk, niche in sorted(self.niches.items()) if not niche.dormant}

    # ---------------------------------------------------- the proven family's program (R3)
    def _proven_programs(self) -> list[dict[str, Any]]:
        """Each proven family's program and who runs it (R3, the close-the-gaps run, Sept 24, 2026). A family is proven
        by the allocator's record (`_family_proven`: "proven" or "swing"). Its program is its ANCHOR's: the living member
        on the highest rung with fills of its own (the earliest born first) -- the member whose record proved it -- and
        it runs on the living members of the family on the anchor's desk whose code is the anchor's beyond PARAMS
        (`lab.mechanism_digest`): the anchor and the House's mutations of its parameters. A member that inherited the
        family's name with other code is not the program: meriwether-h2d625d-2 carries sports-central-run-under but was
        born with a moneyline-favourites file its parent never ran (the review of #245), and has no practice trade.

        Each row: `family`, `venue`, `niche`, `anchor` (the Agent), `running` (the Agents), `wanted` (members short of
        `economy.proven_family_members`), `held` (why no birth is made now, or ""), `record` (the family record)."""
        target = int(self.game["economy"].get("proven_family_members", 0) or 0)
        if target <= 0:
            return []
        from .families import swing_rule
        from .lab import family_at_capacity, mechanism_digest

        groups: dict[tuple[str, str], list[Agent]] = {}
        for agent in self.registry.living():
            if agent.family and agent.specialty:
                groups.setdefault((agent.family, agent.venue), []).append(agent)
        digests: dict[str, str | None] = {}

        def digest(agent: Agent) -> str | None:
            if agent.code_sha256 not in digests:
                digests[agent.code_sha256] = mechanism_digest(agent.code)
            return digests[agent.code_sha256]

        out = []
        for (family, venue), members in sorted(groups.items()):
            if not self._family_proven(family, venue):
                continue
            ranked = sorted(members, key=lambda a: (-self.evaluator.rung(a.id), a.born_at, a.id))
            # Only a member running the family's founding program's markets and style may anchor it (the review of #276):
            # ranked by rung and birth alone, meriwether-h2d625d-2's moneyline file would be bred as the run-unders'
            # program the day meriwether-h2d625d died and -2 had a fill.
            founding = self._family_program(family, venue)
            anchor = next((a for a in ranked if self.evaluator.rung(a.id) >= 1 and self._own_fills(a.id, enough=1)
                           and (founding is None or self._markets_and_style(a.needs or {}) == founding)), None)
            if anchor is None:
                continue
            mine = digest(anchor)
            running = [a for a in members if a.specialty == anchor.specialty
                       and (a.code_sha256 == anchor.code_sha256 or (mine is not None and digest(a) == mine))]
            record: Mapping[str, Any] = {}
            try:
                record = self.allocator.family(family, venue) or {}
            except Exception:  # noqa: BLE001 - `Allocator.family` never raises; an unread record breeds nothing
                record = {}
            held = ""
            unbred = (self._state.get("proven_unbred") or {}).get(family) or {}
            if family_at_capacity(record, swing_rule()):
                held = "the family is at its measured capacity (E3): more members find no more room in its markets"
            elif self._losing_family(family):
                held = "its pooled forward record is negative"
            elif self._holdout_spent(anchor):
                held = "its line has spent its sealed-holdout ration"
            elif unbred.get("program") == [anchor.id, anchor.code_sha256, json.dumps(anchor.params or {}, sort_keys=True)] \
                    and self.clock() - float(unbred.get("epoch") or 0) < PROVEN_UNBRED_RETRY_SECONDS:
                held = (f"no distinct valid mutation of {anchor.id}'s PARAMS was left at {unbred.get('at')} (`_mutated_params`); "
                        f"asked again {PROVEN_UNBRED_RETRY_SECONDS / 3600:g} h on")
            out.append({"family": family, "venue": venue, "niche": anchor.specialty, "anchor": anchor, "running": running,
                        "wanted": max(0, target - len(running)), "held": held, "record": record})
        return out

    def _read_proven(self) -> list[dict[str, Any]]:
        """`_proven_programs`, or [] with a warning at most once an hour when it cannot be read (the review of #276,
        Sept 24, 2026). It reads the allocator's family records, every living member's rung and fills, and the lab's
        mechanism digests; unguarded, one exception there stopped every seat question (`seat_waiters` is on the lab's
        step, `_displaceable` for a desk, `enroll`, `_refill`) and every birth pass, failing the tick until it cleared,
        where every other waiter source is read again on the next tick."""
        try:
            return self._proven_programs()
        except Exception as exc:  # noqa: BLE001 - no birth is owed and no desk held until it can be read
            now = self.clock()
            with self._state_lock:
                tell = now - float(self._state.get("proven_read_told") or 0) >= 3600
                if tell:
                    self._state["proven_read_told"] = now
            if tell:
                self.alert("warning", f"the proven families' programs could not be read ({type(exc).__name__}: {str(exc)[:160]}): "
                                      "no birth is owed and no desk is held for them until they can")
            return []

    def _waiting_proven(self) -> list[dict[str, Any]]:
        """R3: a proven family's program that runs on fewer than `economy.proven_family_members` living members waits
        for a seat on its anchor's desk, first of every class (`SEAT_WAITERS`), until it has them. It waits from when
        the House first saw it short (house.json `seat_seen`)."""
        now = self.clock()
        out = []
        for row in self._read_proven():
            if row["wanted"] <= 0 or row["held"]:
                continue
            with self._state_lock:
                since = self._state.setdefault("seat_seen", {}).setdefault(f"proven:{row['family']}", now)
            out.append({"family": row["family"], "niche": row["niche"], "venue": row["venue"], "anchor": row["anchor"].id,
                        "members": [a.id for a in row["running"]], "wanted": row["wanted"], "since": float(since)})
        with self._state_lock:
            waiting = {f"proven:{w['family']}" for w in out}
            seen = self._state.setdefault("seat_seen", {})
            for key in [k for k in seen if k.startswith("proven:") and k not in waiting]:
                seen.pop(key, None)
        return out

    def _proven_births(self, rules: Mapping[str, Any]) -> Agent | None:
        """R3 (the close-the-gaps run, Sept 24, 2026): one birth into a proven family's program a tick, first of every
        birth, paced at `newcomer_seconds` a family, until `economy.proven_family_members` living members run it.

        How the House breeds a family's program today, and the path used here: a House-staked mutation of a living
        member's PARAMS inside its `parameter_rules` bounds (`_mutated_params`, which refuses a copy of a living program)
        on the member's code, line and family -- the refill's mutation (`_refill`) and the foundry's evidence mutation
        (`Foundry._evidence_mutation`) both make it so; a parent's own fork (`fork`) is the same child paid by a rich
        parent, and a revival (`_revive_near_misses`) brings back a dead rung-0 program. None of them reached the proven
        family: no House mutation is staked while any newcomer waits (82 did at 15:06Z), a fork needs a free seat in a
        full league (112 of 112), and the foundry's mutation breeds only what earns forward on practice (the anchor
        trades real money). The child starts on rung 0 and is replayed like any mutation; a pass seats it on practice,
        where the existing bunt line (`allocator.bunt_ready`) takes it to real money on its own record.

        Its seat: a free one on the anchor's desk in a league with room, else the desk's (or the league's) weakest
        eligible resident, the newcomer asking as a proven family's (`Newcomer`, `evidenced`: the family's record is the
        strongest evidence on the floor) -- never one of the members that run the program. Measured at 15:06Z: one
        proven family (sports-central-run-under: pooled n 19, bound +0.204, real n 5), one member running its program
        (meriwether-h2d625d, on real money), so three births are owed at the default four."""
        now = self.clock()
        for row in self._read_proven():
            if row["wanted"] <= 0 or row["held"]:
                continue
            family, anchor = row["family"], row["anchor"]
            with self._state_lock:
                last = float((self._state.get("proven_births") or {}).get(family) or 0)
            if now - last < float(rules["newcomer_seconds"]):
                continue
            niche = self.niches.get(anchor.specialty or "")
            if niche is None or niche.dormant:
                continue
            # The mutation first: with none left there is nothing to seat, and the family is held (not owed) for
            # PROVEN_UNBRED_RETRY_SECONDS, so its desk is not kept from other families meanwhile (review of #276).
            params = self._mutated_params(anchor, seed=f"proven:{family}:{len(self.registry.agents)}")
            with self._state_lock:
                unbred = self._state.setdefault("proven_unbred", {})
                if params is None:
                    self._state.setdefault("proven_births", {})[family] = now
                    unbred[family] = {"at": now_iso(self.clock), "epoch": now,
                                      "program": [anchor.id, anchor.code_sha256, json.dumps(anchor.params or {}, sort_keys=True)]}
                else:
                    unbred.pop(family, None)
            if params is None:
                self._data_cache.pop("seat_waiters", None)
                continue  # no valid mutation left inside its bounds (recorded by `_mutated_params`)
            keep = [a.id for a in row["running"]]
            newcomer = Newcomer(family=family, venue=anchor.venue, what=f"a birth of the proven family {family}'s program")
            loser = None
            if self.members(niche.id) >= niche.max_members:
                loser = self._weakest(rules, specialty=niche.id, exclude=keep, evidenced=True, newcomer=newcomer)
            elif len(self.registry.living()) >= int(rules["max_population"]):
                loser = self._weakest(rules, exclude=keep, evidenced=True, newcomer=newcomer)
            else:
                loser = False  # a free seat
            if loser is None:
                self._refuse_birth("proven", row["wanted"], f"{family} on {niche.id}: its desk (or the league) is full of residents that "
                                                            "may not be displaced, even by a proven family's newcomer")
                continue
            with self._state_lock:
                self._state.setdefault("proven_births", {})[family] = now
            record = row["record"] or {}
            real = record.get("real") or {}
            child = self.spawn(anchor.line or anchor.name, family, anchor.code, parent=anchor.id, endowment=rules["endowment_usd"],
                               params=params, specialty=niche.id,
                               reason=(f"a House mutation of the proven family {family}'s program ({anchor.id}'s code, its parameters inside "
                                       f"their bounds): the family's pooled record is proven (n {record.get('n')}, bound "
                                       f"{record.get('bound')}, real n {record.get('real_n')}) and {len(keep)} of "
                                       f"{int(rules.get('proven_family_members') or 0)} living members run its program"))
            self.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["endowment_usd"], "box_forked": False,
                                                "reason": "proven family", "new_code": False, "staked_by": "house"}, agent=anchor.id)
            if self.ledger.get(f"birth-route:{child.id}") is None:
                self.ledger.append("route.decision", {"task": f"birth:{child.id}", "route": "proven_family", "model": None,
                                                       "reason": f"a House mutation of the proven family {family}'s program ({anchor.id})",
                                                       "evidence": {"family": family, "anchor": anchor.id, "members": keep,
                                                                    "n": record.get("n"), "bound": record.get("bound"),
                                                                    "real_n": record.get("real_n") if record.get("real_n") is not None else real.get("n"),
                                                                    "replay_passed": False, "starts_on_rung": 0,
                                                                    "displaced": loser.id if loser else None}},
                                   id=f"birth-route:{child.id}")
            if loser and loser.alive:
                self.kill(loser, "displaced", self.postmortem(loser, "displaced",
                          f"the proven family {family}'s program comes first on its desk: a House mutation of {anchor.id} takes the seat"))
            self._data_cache.pop("seat_waiters", None)
            return child
        return None

    def _reserved_desks(self, waiters: Mapping[str, Sequence[Mapping[str, Any]]], *, below: str) -> set[str]:
        """The desks whose next freed seat belongs to a higher class than `below`: a waiting
        graduate's desk is kept from cards and merged strategies, a waiting card's from merged
        strategies. A seat elsewhere in the league is not held."""
        order = self.SEAT_WAITERS
        reserved: set[str] = set()
        for cls in order[:order.index(below)]:
            reserved |= {str(w.get("niche")) for w in waiters.get(cls, ()) if w.get("niche")}
        return reserved

    def _keep_for(self, reserved: set[str]) -> list[str]:
        """The residents of `reserved` desks, to leave out of a lower class's search for a seat."""
        return [a.id for a in self.registry.living() if a.specialty in reserved] if reserved else []

    def _refuse_birth(self, cls: str, count: int, why: str) -> None:
        """A class of waiter that cannot be born now. Kept for health.json (`seats.last_refused_birth`)
        and told as a warning at most once an hour a class: until Sept 23, 2026 `enroll` broke
        silently and no ops row recorded a refused birth."""
        now = self.clock()
        with self._state_lock:
            refused = self._state.setdefault("seat_refusals", {})
            refused[cls] = {"count": int(count), "why": str(why)[:300], "at": now_iso(self.clock), "epoch": now}
            told = self._state.setdefault("seat_refusals_told", {})
            tell = now - float(told.get(cls) or 0) >= 3600
            if tell:
                told[cls] = now
        if tell:
            self.alert("warning", f"{self._waiters_named(cls, count)} wait{'s' if count == 1 else ''} for a seat: {why}")

    def _seat_market_watch(self, *, fresh: bool = False) -> dict[str, Any]:
        """The seat market once an hour (cached in state `seat_market`; health.json shows it): the
        residents an evidenced newcomer could displace, the never-traded residents past their grace,
        whether any waiting graduate can be seated (told as a refusal when none can), and a warning
        when more than `seat_waiters_warning` newcomers have waited for over an hour.

        Since Sept 24, 2026 (S4, the close-the-gaps run): the seats that hold none of a forward score, a
        fill or a grace still running (`seats_holding_none`, count and ids: `_seats_holding_none`), and
        the desks' evidence clocks the grace follows (`evidence_clocks`, desk -> hours, and when).

        R2 (Sept 24, 2026), the invariant: no newcomer waits over SEAT_WAIT_WARN_SECONDS (two hours), or one warning
        a desk an hour names the desk, how many wait there, the longest wait and the rule that holds them
        (`_held_by`). The report carries `longest_wait` (class, id, desk, hours, reason), `over_two_hours` (desk ->
        count, longest hours, rule), `expired` (the waiters that left the queue in the last day, by rule), `caps`
        (each desk's cap, niches.json cap, members and waiters: `_desk_caps`) and `population` (`_population_rule`).
        Measured at 15:06Z: 50 of the 82 waiters had waited over two hours, and the only warning said how many
        waited, never where or why."""
        now = self.clock()
        cached = self._state.get("seat_market") or {}
        if not fresh and cached and now - float(cached.get("epoch") or 0) < 3600:
            return cached
        rules = self.game["economy"]
        waiters = self.seat_waiters()
        counts = {cls: len(rows) for cls, rows in waiters.items()}
        total = sum(counts.values())
        rank = self._displaceable(rules, evidenced=True)
        never_traded = sum(1 for row in rank if not row[0])
        by_desk: dict[str, int] = {}
        for rows in waiters.values():
            for w in rows:
                if w.get("niche"):
                    by_desk[str(w["niche"])] = by_desk.get(str(w["niche"]), 0) + 1
        graduates = waiters.get("graduates") or []
        if graduates:
            living = self.registry.living()
            room = len(living) < int(rules["max_population"])
            seatable = 0
            lab = getattr(self, "lab", None)
            for niche_id in {str(w["niche"]) for w in graduates if w.get("niche")}:
                niche = self.niches.get(niche_id)
                if niche is None or niche.dormant:
                    continue
                # Each graduate asks with its own family and forward score (S1), as `Lab._seat_for` does.
                asking = [Newcomer(family=w.get("family") or None, venue=niche.venue,
                                   forward=lab.forward_score(w["candidate"]) if lab is not None else None)
                          for w in graduates if str(w.get("niche")) == niche_id]
                if self.members(niche_id) < niche.max_members:
                    if room or any(self._weakest(rules, evidenced=True, newcomer=n) for n in asking):
                        seatable += 1
                elif any(self._weakest(rules, specialty=niche_id, evidenced=True, newcomer=n) is not None for n in asking):
                    seatable += 1
            if not seatable:
                desks = ", ".join(f"{d} {n}" for d, n in sorted(by_desk.items()) if any(str(w.get("niche")) == d for w in graduates))
                self._refuse_birth("graduates", len(graduates),
                                   f"no resident of their desks may be displaced, even by a newcomer with forward evidence ({desks})")
        threshold = int(rules.get("seat_waiters_warning", 8))
        with self._state_lock:
            since = float(self._state.get("seat_waiters_since") or 0)
            if total > threshold:
                if not since:
                    since = now
                self._state["seat_waiters_since"] = since
            else:
                since = 0.0
                self._state.pop("seat_waiters_since", None)
            told = float(self._state.get("seat_waiters_told") or 0)
            tell = bool(since) and now - since > 3600 and now - told >= 3600
            if tell:
                self._state["seat_waiters_told"] = now
        if tell:
            self.alert("warning", f"{total} newcomers have waited for seats for over an hour ({', '.join(f'{n} {cls}' for cls, n in counts.items() if n)}): "
                                  f"{len(rank)} residents could be displaced by one with forward evidence")
        empty = self._seats_holding_none(rules)
        clocks = self.evidence_clocks()
        overdue = self._overdue(waiters, rules, now)
        report = {"at": now_iso(self.clock), "epoch": now, "waiters": counts, "waiters_by_desk": by_desk,
                  "displaceable": len(rank), "never_traded_past_grace": never_traded,
                  "waiting_over_an_hour": bool(since) and now - since > 3600,
                  "seats_holding_none": {"count": len(empty), "ids": empty[:40]},
                  "evidence_clocks": {"at": clocks.get("at"), "hours": {d: row.get("hours") for d, row in (clocks.get("desks") or {}).items()}},
                  "over_two_hours": overdue, "longest_wait": self._longest_wait(waiters, now, overdue),
                  "expired": self._expired_summary(now), "caps": self._desk_caps(), "population": self._population_rule()}
        with self._state_lock:
            self._state["seat_market"] = report
        return report

    def _overdue(self, waiters: Mapping[str, Sequence[Mapping[str, Any]]], rules: Mapping[str, Any], now: float) -> dict[str, dict[str, Any]]:
        """R2 (4), the invariant: desk -> {"count", "longest_hours", "longest", "rule"} for the newcomers that have waited
        over SEAT_WAIT_WARN_SECONDS, with the rule that holds them (`_held_by`); one warning a desk an hour names the
        desk, the count, the longest wait and that rule."""
        found: dict[str, list[tuple[float, str, Mapping[str, Any]]]] = {}
        for cls, rows in waiters.items():
            for w in rows:
                since = float(w.get("since") or 0)
                if since and now - since > SEAT_WAIT_WARN_SECONDS:
                    found.setdefault(str(w.get("niche") or ""), []).append((now - since, cls, w))
        out: dict[str, dict[str, Any]] = {}
        for desk, rows in sorted(found.items()):
            rows.sort(key=lambda r: -r[0])
            hours, cls, first = rows[0]
            out[desk or "unknown"] = {"count": len(rows), "longest_hours": round(hours / 3600, 1),
                                      "longest": f"{cls}:{first.get(self.SEAT_WAITER_IDS[cls])}",
                                      "rule": self._held_by(desk, rows, rules)}
        with self._state_lock:
            told = self._state.setdefault("seat_overdue_told", {})
            for desk in [d for d in told if d not in out]:
                told.pop(desk, None)  # nobody waits over two hours there now: the next wait is told afresh
            tell = [desk for desk in out if now - float(told.get(desk) or 0) >= 3600]
            for desk in tell:
                told[desk] = now
        for desk in tell:
            row = out[desk]
            many = row["count"] != 1
            self.alert("warning", f"{row['count']} newcomer{'s' if many else ''} ha{'ve' if many else 's'} waited over "
                                  f"{SEAT_WAIT_WARN_SECONDS / 3600:g} hours for a seat on {desk} (the longest {row['longest_hours']} h, "
                                  f"{row['longest']}): {row['rule']}", desk=desk, waiting=row["count"], rule=row["rule"])
        return out

    def _held_by(self, desk: str, rows: Sequence[tuple[float, str, Mapping[str, Any]]], rules: Mapping[str, Any]) -> str:
        """Why the waiters of one desk are not seated, in words (R2 (4)): a free seat the birth passes have not
        reached, or the rules that keep every resident of the desk (or of the league, when the desk has room and the
        league has none) from the best newcomer that asks -- the waiter with the best forward score, as the lab's
        graduate asks (`_displaceable`'s `why`: real money, winners, inside the grace or the desk's evidence clock, a
        trader short of its record, a proven family's member ...)."""
        living, most = len(self.registry.living()), int(rules["max_population"])
        niche = self.niches.get(desk) if desk else None
        if niche is None:
            return (f"its desk is decided at its birth (a merged strategy's NEEDS are read then), and the league is {living} of {most}"
                    + ("" if living < most else ": a seat is made only by displacing an eligible resident"))
        if niche.dormant:
            return f"its desk {desk} is not open ({niche.dormant_reason or 'dormant'})"
        members, cap = self.members(desk), int(niche.max_members)
        scores = self._waiter_forward() if any(cls == "graduates" for _, cls, _ in rows) else {}
        forward = max((scores.get(str(w.get("candidate"))) for _, cls, w in rows if cls == "graduates"
                       and scores.get(str(w.get("candidate"))) is not None), default=None)
        family = next((str(w.get("family")) for _, cls, w in rows if cls == "proven"), None) or next(
            (str(w.get("family")) for _, _, w in rows if w.get("family")), None)
        newcomer = Newcomer(family=family, venue=niche.venue, forward=forward, what=f"the waiters of {desk}")
        if members < cap and living < most:
            return (f"a seat is free ({members} of {cap} on the desk, {living} of {most} in the league): the next birth pass seats "
                    f"it (the lab births at most {int(((self.game.get('lab') or {}).get('max_births_per_hour')) or 6)} an hour, "
                    f"the refill one every {float(rules['newcomer_seconds']):g} s)")
        why: dict[str, int] = {}
        if members >= cap:
            rank = self._displaceable(rules, specialty=desk, evidenced=True, newcomer=newcomer, why=why)
            where = (f"its {cap} seat{'s' if cap != 1 else ''} ({members} member{'s' if members != 1 else ''}) "
                     f"{'are' if cap != 1 else 'is'} held")
        else:
            rank = self._displaceable(rules, evidenced=True, newcomer=newcomer, why=why)
            where = f"the league's {most} seats are held (the desk has {cap - members} free)"
        if rank:
            return f"{rank[0][-1].id} may make way for them now: the next birth pass takes its seat"
        held = ", ".join(f"{n} {rule}" for rule, n in sorted(why.items(), key=lambda kv: (-kv[1], kv[0])))
        return f"{where}: {held or 'nobody could be read'}"

    def _longest_wait(self, waiters: Mapping[str, Sequence[Mapping[str, Any]]], now: float,
                      overdue: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
        """The newcomer that has waited longest (R2 (4)): class, id, desk, hours, since and the rule that holds it."""
        best = None
        for cls, rows in waiters.items():
            for w in rows:
                since = float(w.get("since") or 0)
                if since and (best is None or since < best[0]):
                    best = (since, cls, w)
        if best is None:
            return None
        since, cls, w = best
        desk = str(w.get("niche") or "")
        return {"class": cls, "id": str(w.get(self.SEAT_WAITER_IDS[cls])), "desk": desk or None,
                "hours": round(max(0.0, now - since) / 3600, 1), "since": now_iso(lambda: since),
                "reason": (overdue.get(desk or "unknown") or {}).get("rule")}

    def _expired_summary(self, now: float) -> dict[str, Any]:
        """The waiters that left the seat queue in the last day (house.json `seat_expired`), by rule and by desk."""
        rows = [r for r in (self._state.get("seat_expired") or {}).values() if now - float((r or {}).get("epoch") or 0) <= 86400]
        by_rule: dict[str, int] = {}
        by_desk: dict[str, int] = {}
        for r in rows:
            by_rule[str(r.get("rule"))] = by_rule.get(str(r.get("rule")), 0) + 1
            by_desk[str(r.get("desk") or "unknown")] = by_desk.get(str(r.get("desk") or "unknown"), 0) + 1
        return {"last_day": len(rows), "by_rule": by_rule, "by_desk": by_desk}

    def _seats_holding_none(self, rules: Mapping[str, Any]) -> list[str]:
        """S4 (Sept 24, 2026): the living residents off real money whose seat holds none of a program with a
        forward score (`Lab.resident_forward`, ranked), a fill of its own since its program's opportunity, or
        a grace still running (the plain grace, or its desk's evidence clock, in wall-clock hours from that
        opportunity), oldest first -- and every resident that has held its own entries for longer than that
        grace (`_paused_past`), as displacement counts it. The population stays 112; these are the seats
        that carry no evidence."""
        grace = float(rules.get("displace_after_epochs", 2)) * float(rules["epoch_seconds"])
        clocks = self._desk_clocks()
        now = self.clock()
        out: list[tuple[float, str]] = []
        for agent in self.registry.living():
            if now - _epoch(agent.born_at) < grace:
                continue  # its program's opportunity is no older than its birth: its grace still runs
            rung = self.evaluator.rung(agent.id)
            if rung >= 2:
                continue
            opportunity, seq = self._program_opportunity(agent) if rung == 1 else (_epoch(agent.born_at), 0)
            clock = clocks.get(agent.specialty or "", 0.0) if rung == 1 else 0.0
            if rung == 1 and self._paused_past(agent, max(grace, clock), now):
                # Its own pause, past its grace: held buys are not trading, and its fills and forward score
                # are its record, not evidence that it trades now (review of #249, P3; the seat report).
                out.append((opportunity, agent.id))
                continue
            if now - opportunity < max(grace, clock):
                continue
            if self._own_fills(agent.id, after=seq, enough=1):
                continue
            if self._resident_forward(agent, ranked=True) is not None:
                continue
            out.append((opportunity, agent.id))
        return [agent_id for _, agent_id in sorted(out)]

    def _seats_health(self) -> dict[str, Any]:
        """The `seats` block of health.json: the hourly watch, the waiters now and the last refusal a class; since R2
        (Sept 24, 2026) the longest wait now, with the rule the hourly watch found holding its desk, and the
        population the league may grow to now (`_population_rule`)."""
        watch = dict(self._state.get("seat_market") or {})
        watch.pop("epoch", None)
        waiters = self.seat_waiters()
        out = {**watch, "waiters": {cls: len(rows) for cls, rows in waiters.items()},
               "reserved_desks": sorted(self._reserved_desks(waiters, below="strategies")),
               "last_refused_birth": {cls: {k: v for k, v in row.items() if k != "epoch"}
                                      for cls, row in (self._state.get("seat_refusals") or {}).items()},
               "longest_wait": self._longest_wait(waiters, self.clock(), watch.get("over_two_hours") or {})}
        population = getattr(self, "_population_report", None)
        if population is not None:
            out["population"] = population
        return out

    def _desk_traders(self, living: Sequence[Agent]) -> dict[str, list[str]]:
        """Each desk's trading members: on rung 1 or above with a fill since they entered their
        rung. Analyst C, Sept 23, 2026: two crypto desks had no trading member for 34-35 of 48 hours
        while "full" of rung-0 replay-only children cycling through births and displacements."""
        traders: dict[str, list[str]] = {}
        for agent in living:
            if not agent.specialty or self.evaluator.rung(agent.id) < 1:
                continue
            entered = self.evaluator._rung_entered(agent.id)
            if next(iter(self.ledger.iter(kinds="book.fill", agent=agent.id, after=entered)), None) is not None:
                traders.setdefault(agent.specialty, []).append(agent.id)
        return traders

    def _mutation_room(self, living: Sequence[Agent]) -> dict[str, int]:
        """Seats a House mutation (replay-only, rung 0) may take, a desk: its free seats, less one
        held for a member that trades while the desk has none. So rung-0 children can never fill a
        desk, and a desk with no trading member gives its next seat to a graduate or a replay-passed
        newcomer (`_refill`), never a mutation."""
        traders = self._desk_traders(living)
        room = {}
        for niche in self.niches.values():
            if niche.dormant:
                continue
            free = niche.max_members - sum(a.specialty == niche.id for a in living)
            room[niche.id] = free - (0 if traders.get(niche.id) else 1)
        return {key: value for key, value in room.items() if value > 0}

    def _last_traders(self, living: Sequence[Agent]) -> list[str]:
        """The only trading member of each desk: a House mutation never takes that seat."""
        return [ids[0] for ids in self._desk_traders(living).values() if len(ids) == 1]

    def family_forward(self) -> dict[str, tuple[int, float]]:
        """Each family's pooled forward record: active `eval.block` count and summed log growth over
        every agent ever born into it, living or dead (a block exists only once an agent holds a
        paper seat). Cached for five minutes, as `line_trials` is; accounting cutoffs are not applied
        (they mark a book's reset, and the pooled sign is what this reads)."""
        def build():
            family = {a.id: a.family for a in self.registry.agents.values()}
            out: dict[str, list[float]] = {}
            for entry in self.ledger.iter(kinds="eval.block"):
                if not entry.payload.get("active"):
                    continue
                row = out.setdefault(family.get(entry.agent, ""), [0, 0.0])
                row[0] += 1
                row[1] += float(entry.payload.get("log_growth") or 0.0)
            return {key: (int(n), growth) for key, (n, growth) in out.items() if key}
        hit = self._data_cache.get("family_forward")
        if hit and self.clock() - hit[0] < 300:
            return hit[1]
        value = build()
        self._data_cache["family_forward"] = (self.clock(), value)
        return value

    def _losing_family(self, family: str) -> str | None:
        """Why a House mutation, parameter fork or revival of `family` is not made: its pooled
        forward record is negative after `losing_family_min_blocks` (game.json, 6) active blocks.
        None when the family may be bred. The mechanism is the code: a child that runs its parent's
        code (a mutation of its parameters, a revival) repeats the family's mechanism; one with new
        code -- a research candidate's fork, a card, a graduate -- is judged on its own. Told as an
        info alert once an hour a family.

        Measured Sept 23, 2026 (analyst B, L3.1): 44 births followed evidence deaths in two families
        (kalshi-favorites 23 after its death, crypto-15m-favorites 21 after five, all negative
        forward), and every family with two or more forward-tested replay passes was negative."""
        minimum = int(self.game["economy"].get("losing_family_min_blocks", 6))
        blocks, growth = self.family_forward().get(family, (0, 0.0))
        # A pooled record that nets to zero is not a loss: six blocks of +0.01 and -0.01 sum to
        # -3.5e-18 in floating point, which is no evidence of anything.
        if blocks < minimum or growth > -1e-9:
            return None
        why = f"the family {family} is not bred again: its pooled forward record is {growth:+.4f} over {blocks} active blocks"
        now = self.clock()
        with self._state_lock:
            told = self._state.setdefault("losing_family_told", {})
            tell = now - float(told.get(family) or 0) >= 3600
            if tell:
                told[family] = now
        if tell:
            self.alert("info", why + " (a child with different code is still born on its own evidence)")
        return why

    def frontier_remaining(self) -> Decimal | None:
        """The tighter of the two OpenAI lines: the gateway's month (`FrontierMonth`) and the House's
        own campaign allowance, which refuses at its own line whatever the gateway has left.

        The reserve that keeps the last dollars for audits read only the gateway. On Sept 22, 2026 the
        campaign -- which books every call at the House's ceiling prices, about twice the gateway's --
        had $139 left against the gateway's $166 while committing about $17 an hour: it would have
        refused every call, audits included, while the tier still said "all". None when neither line
        can be read; the campaign counts only beside a month reader, as in production.

        Reading the month also reads OpenAI's meter (Sept 24, 2026): `FrontierMonth` feeds each
        reading to `CampaignBudget.observe_month`, and the tick calls this every time so the meter
        stays fresh and the stale OpenAI holds can be absorbed against it (`_absorb_stale_holds`)."""
        month = self.frontier_month
        remaining = month.remaining() if month is not None else None
        campaigns = self.campaigns if month is not None else None
        # Profit-indexed compute: the House's OpenAI line is raised by exactly what the gateway's
        # profit indexing added to its month, never more (`CampaignBudget.mirror_gateway_bonus`).
        bonus = getattr(month, "profit_bonus", None)
        mirror = getattr(campaigns, "mirror_gateway_bonus", None)
        if bonus is not None and mirror is not None:
            try:
                raised = bonus()
                if raised is not None:
                    mirror("openai", raised)
            except Exception as exc:  # noqa: BLE001 - the configured line stands
                self.alert("warning", f"the gateway's profit-indexed raise could not be mirrored ({type(exc).__name__}: {str(exc)[:160]})",
                           **environment("gateway", exc))
        if campaigns is not None:
            now = self.clock()
            cached = getattr(self, "_campaign_openai", None)
            if cached is None or now - cached[0] >= 30:
                try:
                    value = Decimal(str(campaigns.remaining("openai")))
                    cached = (now, value if value.is_finite() else None)
                except Exception:  # noqa: BLE001 - unreadable is unknown, never a number
                    cached = (now, None)
                self._campaign_openai = cached
            if cached[1] is not None:
                remaining = cached[1] if remaining is None else min(remaining, cached[1])
        return remaining

    def frontier_tier(self) -> str:
        """What frontier work the OpenAI budget still pays for (`frontier.frontier_tier`), on the
        tighter of its two lines (`frontier_remaining`). A change of tier is written to the ledger
        once, so the owner reads why Merton went quiet.

        While OpenAI's meter is not ready (`_openai_meter_unread`: the gateway's month unread for
        three minutes), every OpenAI reservation is refused whatever either line says, so the tier
        is "audits": no role is scheduled into a refusal, and a Luna-cohort agent's new research
        session runs on Sail (`fast_research.ResearchRouter`) instead of being refused and left
        unconfirmed. The owner is told when it starts and when the meter is read again. Found in the
        Sept 24, 2026 review: with the gateway's health route down, the tier still read "all" and
        nothing said that paid OpenAI work, audits included, had stopped."""
        from .frontier import frontier_tier

        remaining = self.frontier_remaining()
        unread = self._openai_meter_unread()
        tier = "audits" if unread else frontier_tier(remaining, self.game.get("frontier_reserve"))
        with self._state_lock:
            changed = tier != self._state.get("frontier_tier", "all")
            was_unread = bool(self._state.get("frontier_meter_unread"))
            self._state["frontier_tier"] = tier
            self._state["frontier_meter_unread"] = unread
        if unread and not was_unread:
            self.alert("warning", "OpenAI's meter is not ready (the gateway's frontier month has not been read for three "
                                  "minutes, or a charge exceeded its reservation): every OpenAI call is refused until it is. "
                                  "New research runs on Sail; Merton, audits and the lab's Luna and Sol calls wait.")
        elif not unread and (changed or was_unread):
            shown = f"${remaining:.2f}" if remaining is not None else "unknown"
            text = {
                "all": f"frontier budget {shown} left: every role runs again",
                "earned": f"frontier budget {shown} left: cheap research moves to Sail and the unearned roles pause",
                "audits": f"frontier budget {shown} left: only audits and winners' consultations remain"}[tier]
            self.alert("warning" if tier != "all" else "info", ("OpenAI's meter is read again; " + text) if was_unread else text)
        return tier

    def _openai_meter_unread(self) -> bool:
        """True while the campaign meters OpenAI by the gateway's month (`campaigns.json`
        `meter_required`, with the month's reader in place, as in production) and would refuse every
        OpenAI reservation for want of a fresh reading (`CampaignBudget.ready`)."""
        campaigns = self.campaigns if self.frontier_month is not None else None
        ready = getattr(campaigns, "ready", None)
        if ready is None or "openai" not in ((getattr(campaigns, "policy", None) or {}).get("meter_required") or []):
            return False
        try:
            return not ready("openai")
        except Exception:  # noqa: BLE001 - an unreadable store is not a reading; the reservation says so itself
            return False

    def research_order(self) -> list[Agent]:
        """Who gets asked first when the day's frontier allowance is nearly all the floor has.

        Twenty-eight agents on a three-hour cadence want more passes in a day than the expedition
        funds, so the allowance -- not the cadence -- is what really decides who researches. Taken
        in the order they were born, the same agents would claim it every morning and the youngest
        desks would never research at all. Stuck first, then whoever has waited longest."""
        pending = {job["agent"]: job for job in self.research_jobs.pending()}
        return sorted(self.registry.living(), key=lambda a: (
            0 if a.id in pending else 1,
            pending[a.id]["created"] if a.id in pending else (0 if self.idle_reason(a) else 1),
            float(self._state["last_research"].get(a.id) or 0)))

    def behind_the_clock(self, kind: str) -> bool:
        """Is today's share of this budget running behind the day? The owner funded a fortnight to
        be spent, and an allowance still unspent at noon is work that was not done."""
        if getattr(self.pacer, "no_catch_up", False):
            return False
        allowance = self.pacer.allowance(kind)
        if allowance <= 0:
            return False
        day_gone = (self.clock() % 86400) / 86400.0
        return day_gone > 0.25 and float(1 - self.pacer.room(kind) / allowance) < 0.6 * day_gone

    def frontier_pace(self) -> float:
        """The share of its usual wait one of Merton's roles serves, halved while the day's
        frontier allowance runs behind the clock.

        Measured Sept 20, 2026, eleven hours in: the gateway had billed $1.72 of frontier calls
        against $7.14 a day, while the agents spent two and a half times their Sail allowance on
        research. The cheap model was the bottleneck and the dear one sat half idle -- and the dear
        one is the half that writes strategies, builds the tools eighteen requests are waiting on,
        and reads the floor. A budget the owner funded to be spent is not thrift unspent."""
        return 0.5 if self.behind_the_clock("openai") else 1.0

    def research_interval_hours(self, agent: Agent | None = None) -> float:
        """How long an agent waits between research passes. Long intervals are halved down to
        an hour while today's Sail spending is behind; faster configured intervals stay fast.
        The owner wants
        the expedition's budget used, and an allowance still unspent at noon is research not done.
        An agent that cannot act at all waits the idle interval instead -- it has nothing else to
        spend its time on, and every wake it sits out is a wake it did not learn from."""
        rules = self.game.get("research") or {}
        base = float(rules.get("min_hours_between", 6))
        idle = agent is not None and bool(self.idle_reason(agent))
        if idle:
            base = min(base, float(rules.get("idle", {}).get("min_hours_between", 1)))
        base = min(base, max(1.0, base / 2)) if self.behind_the_clock("sail") else base
        return base * self.research_pace(agent, idle=idle) if agent is not None else base

    def research_pace(self, agent: Agent, *, idle: bool = False) -> float:
        """The share of the usual research interval this agent waits, from its own record.

        Winners run: an agent whose earned record is profitable researches at `winner_share` of the
        interval, and every candidate its research passes through replay is born its child -- so a
        winning line breeds faster. An agent on paper or above with `loser_min_observations` of
        evidence and a losing record waits `loser_multiple` times as long. An agent with no earned
        record at all waits `unproven_multiple` times as long (Sept 23, 2026: 84% of sessions ended
        by abstaining, most of them by agents with nothing yet to learn from); everyone else keeps
        the interval (owner's direction, Sept 21, 2026)."""
        pace = (self.game.get("research") or {}).get("pace") or {}
        if not pace:
            return 1.0
        try:
            row = self.standing_of(agent.id)
        except Exception:  # noqa: BLE001 - a record that cannot be read changes nothing
            return 1.0
        growth, seen = float(row.get("earned_growth") or 0.0), int(row.get("earned_observations") or 0)
        if seen > 0 and growth > 0:
            return float(pace.get("winner_share", 1.0))
        if row.get("rung", 0) >= 1 and seen >= int(pace.get("loser_min_observations", 5)) and growth < 0:
            return float(pace.get("loser_multiple", 1.0))
        if seen == 0 and not idle:  # an idle agent's research is pulled forward, not put off
            return float(pace.get("unproven_multiple", 1.0))
        return 1.0

    def _research_if_due(self, agent: Agent) -> Any:
        """Recheck after waiting for a research worker: a queued job owns no budget or seat."""
        current = self.registry.get(agent.id)
        if current is None or not self.research_due(current):
            return None
        if self.budget is not None and self.budget.mode == "stopped":
            return None
        return self.research(current)

    def queue_research(self, agent: Agent) -> bool:
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None or self._closing.is_set():
                return False
            self.research_jobs.enqueue(agent.id, generation)
        return self._background(f'research:{agent.id}', self._research_if_due, agent)

    def _research_permission(self, agent: Agent) -> str:
        if self._closing.is_set() or self.deploying():
            return 'deployment or shutdown'
        with self._lifecycle_lock:
            job = self.research_jobs.active(agent.id)
            current = self._generation(agent.id)
            if current is None or (job and list(current[:-1]) != job['generation'][:-1]):
                return 'retired or changed'
        if self.stopped() or (self.budget is not None and self.budget.mode == 'stopped'):
            return 'research stopped'
        if self.paused():
            return 'maintenance pause'
        if not self.pacer.may_spend(self._research_budget_kind(agent)):
            return 'campaign allowance unavailable'
        return ''

    def _sail_research_capped(self) -> bool:
        """Whether the last hour's Sail research spend has reached turbo.json
        `sail_research_usd_per_hour` (`_sail_cap_state`): then no NEW session starts on Sail."""
        state = self._sail_cap_state()
        return bool(state and state["capped"])

    def _sail_cap_state(self) -> dict[str, Any] | None:
        """The Sail research cap as health.json shows it, read at most once a minute; None without a
        cap or a campaign guard. One `ops.budget` row ("sail research cap") each time it closes or
        opens.

        The hour's spend is the settled cost of the Sail commitments created in the last hour
        (campaigns.sqlite `commitments`, kind `sail`: every Sail call is research, campaign
        `baseline-research`). A call in flight counts once it settles, seconds to minutes later: its
        reservation is its worst case, about $0.25 against a median $0.016, and six in flight would
        read as a spent cap. Sept 23, 2026, 22-23Z: Sail research settled $11.66 in an hour (344
        calls) once cheap research moved to Sail; $1.27 in the hour before T0."""
        cap, guard = getattr(self, "_sail_research_cap", None), self.campaigns
        if cap is None or guard is None:
            return None
        now = self.clock()
        cached = getattr(self, "_sail_cap_cache", None)
        if cached is not None and now - cached[0] < 60:
            return cached[1]
        try:
            with guard.lock:
                settled, calls, inflight, held = guard.db.execute(
                    "SELECT COALESCE(SUM(cost),0), COALESCE(SUM(cost IS NOT NULL),0), COALESCE(SUM(cost IS NULL),0),"
                    " COALESCE(SUM(CASE WHEN cost IS NULL THEN reserved ELSE 0 END),0) FROM commitments WHERE kind='sail' AND created>=?",
                    (now - 3600,)).fetchone()
        except Exception as exc:  # noqa: BLE001 - an unreadable meter caps nothing; the campaign's own limits stand
            return {"error": f"{type(exc).__name__}: {str(exc)[:160]}", "capped": False}
        spent = (Decimal(int(settled)) / 1_000_000).quantize(CENT)
        state = {"cap_usd": format(cap, "f"), "last_hour_usd": format(spent, "f"), "calls": int(calls),
                 "inflight_calls": int(inflight), "inflight_reserved_usd": format((Decimal(int(held)) / 1_000_000).quantize(CENT), "f"),
                 "capped": spent >= cap}
        with self._state_lock:
            before = bool(self._state.get("sail_research_capped"))
            self._state["sail_research_capped"] = state["capped"]
        if state["capped"] != before:
            self.ledger.append("ops.budget", {"what": "sail research cap", "capped": state["capped"], "last_hour_usd": state["last_hour_usd"],
                                              "cap_usd": state["cap_usd"], "calls": state["calls"],
                                              "reason": ("the last hour's Sail research spend reached the cap: no new Sail session starts"
                                                         if state["capped"] else "the last hour's Sail research spend is under the cap again")})
        self._sail_cap_cache = (now, state)
        return state

    def research_capabilities(self, agent: Agent) -> dict[str, Any]:
        from .capabilities import describe
        result = describe(agent, self.settings, self.niche_of(agent), clock=self.clock,
                          alpaca=self.alpaca_data is not None, kalshi=self.kalshi_data is not None)
        result['observations']['stock_feed'] = getattr(self.alpaca_data, 'feed', None)
        paper = self.books.get('alpaca-paper')
        result['observations']['option_feed'] = getattr(paper.broker, 'option_feed', None) if paper else None
        niche = self.niche_of(agent)
        if niche is not None and getattr(niche, 'asset_class', None) == 'option' and self._replayable(niche, agent.needs):
            limits = [x for x in result['replay']['limitations'] if x != 'no historical option-chain replay']
            result['replay'].update(mode='historical_development_estimated_option_quotes',
                                    requested_window_days=self.settings.replay_days * (6 if agent.horizon == 'day' else 1),
                                    limitations=limits + ['options: Alpaca has trade bars since 2024-01-18 and no historical quotes; replay bid/ask are '
                                                          'ESTIMATES from prints, fills are bar-based and conservative (see CONTRACT.md)'])
        if self.semantic_lab is not None:
            observed = agent.needs.get('observe') or {}
            result['semantic_research'] = self.semantic_lab.evidence(agent.id,
                series=[*(agent.needs.get('series') or []), *(observed.get('series') or [])])
        if self.feeds is not None:
            # The live feeds (league/feeds.py): what is recorded, since when, and what replay needs. A
            # feed that has recorded something is no longer "not supplied".
            try:
                described = self.feeds.describe()
            except Exception as exc:  # noqa: BLE001 - an unreadable store announces nothing
                described = {'error': f'{type(exc).__name__}: {str(exc)[:160]}'}
            result['observations']['feeds'] = described
            shipped = {'sports': 'live sports score feed', 'perps': 'perpetual funding/open-interest feed'}
            gone = {text for feed, text in shipped.items() if (described.get(feed) or {}).get('recording_since')}
            result['observations']['not_supplied'] = [x for x in result['observations'].get('not_supplied') or [] if x not in gone]
            # The backfilled histories (Sept 23 and 24, 2026), said plainly: a strategy that reads them can
            # be replayed now, which no live-recorded feed can offer on its first day.
            history = {feed: {'backfilled_since': (described.get(feed) or {}).get('backfilled_since'),
                              'replayable_now': (described.get(feed) or {}).get('replayable_now')}
                       for feed in feeds_module.HISTORY_FEEDS if (described.get(feed) or {}).get('recording')}
            if history:
                result['observations']['replayable_history'] = {
                    **history,
                    'note': 'vol (Deribit DVOL, BTC and ETH, hourly candles stamped at their close), funding (OKX settled '
                            'funding per coin, stamped at settlement), forecast (GFS and ECMWF daily highs, lows and rain at one '
                            'to three days lead per settlement station, stamped 11:00 local standard time), earnings (each 8-K '
                            'Item 2.02 at EDGAR\'s acceptance time) and oi (OKX hourly open interest, stamped at the hour\'s end) '
                            'are point-in-time history backfilled over the replay window: declare them in NEEDS["feeds"] and a '
                            'replay can judge the strategy now. Row shapes: observations.feeds and the contract.'}
        return result

    def research_coverage(self, agent: Agent, needs: Mapping[str, Any] | None = None) -> dict[str, Any]:
        from .capabilities import coverage_needs, tape_coverage
        niche = self.niche_of(agent)
        if niche is not None and not self._replayable(niche, dict(needs or agent.needs)):
            return {'mode': 'smoke_only', 'counted_as_trial': False,
                    'note': 'No historical option-chain replay here: the options history does not cover these underlyings. A smoke check cannot measure edge or fills.'}
        try:
            effective = coverage_needs(agent, needs, niche)
            if effective.get('asset_class') == 'option' and not (niche is not None and self._replayable(niche, effective)):
                return {'mode': 'smoke_only', 'counted_as_trial': False,
                        'note': 'No historical option-chain replay.'}
            if effective.get('asset_class') == 'option':
                query, tape = self.tape_for(effective)
                return {'query': query, **tape_coverage(tape), 'effective_needs': effective, 'counted_as_trial': False,
                        'options': {'contracts': len(tape.get('contracts') or {}), 'coverage': tape.get('coverage'),
                                    'quotes': 'estimated from trade prints: Alpaca has no historical option quotes'}}
            query, tape = self.tape_for(effective)
            requested = (effective.get('observe') or {}).get('symbols') or []
            missing = [s for s in requested if not (tape.get('observed_bars') or {}).get(s)] if agent.venue == 'kalshi' else []
            wanted = self._feeds_wanted(effective)
            history = None
            if agent.venue == 'alpaca':
                # Which history judges this: the store's development window, or the live tape
                # because the store has not fetched these inputs yet (not a fact about the market).
                history = ({'tape': 'development window before the sealed holdout', **dict(tape.get('source') or {})}
                           if query.startswith('deep:') else {'tape': 'live recent tape',
                                                             'why': 'no feed reaches back into the history store\'s development window '
                                                                    '(the live feeds are recorded as received; the history feeds are '
                                                                    'backfilled over the live replay window)' if wanted
                                                             else 'the history store has not fetched every input yet' if self.settings.deep_replay else 'deep replay is off'})
            feeds = None
            if wanted:
                # What the declared feeds hold over this tape's window, and whether a replay may use them yet.
                short = self._feeds_shortfall(effective, wanted, tape.get('feeds_coverage') or {}) if self.feeds is not None else \
                    'unsupported input: this House records no live feeds'
                feeds = {'requested': wanted, 'coverage': tape.get('feeds_coverage'), 'replay_ready': not short,
                         **({'blocked_by': short} if short else {}),
                         'note': 'Every row is replayed point in time by its t. A live feed\'s rows are recorded with their receive '
                                 'time, and nothing before recording began exists. A history feed\'s rows (' + ', '.join(feeds_module.HISTORY_FEEDS)
                                 + ') are stamped when each value became final (a candle at its close, a rate at its settlement, an 8-K at '
                                 'its acceptance, a forecast at its issue plus its publication allowance) and backfilled over the replay '
                                 'window (coverage.<feed>.<key>.backfill says from where and since when), so they are replayable as soon as '
                                 'the backfill is in. A live wake is handed ctx["feeds"] whether or not a replay may use them yet.'}
            return {'query': query, **tape_coverage(tape), 'effective_needs': effective, **({'history': history} if history else {}),
                    **({'feeds': feeds} if feeds else {}),
                    'proposed_inputs': needs is not None,
                    'required_observed_symbols': list(requested), 'missing_observed_symbols': missing,
                    'observed_inputs_available': not missing,
                    'input_note': 'Missing required symbols block this configuration, not every symbol or every hypothesis. Bar presence alone does not prove complete coverage.'}
        except Exception as exc:
            return {'mode': 'unavailable', 'counted_as_trial': False,
                    'error': f'{type(exc).__name__}: {str(exc)[:200]}'}

    def _research_standing(self, agent: Agent):
        from .auditor import order_outcomes
        rung = self.evaluator.rung(agent.id)
        book = self.book_of(agent)
        ladder = self.evaluator.ladder
        peers = []
        for entry in self.ledger.iter(kinds='eval.trial'):
            other = self.registry.get(entry.agent)
            if other is not None and other.id != agent.id and other.niche == agent.niche and entry.payload.get('passed'):
                peers.append({'agent': entry.agent, 'at': entry.at, 'seq': entry.seq,
                    **{k: entry.payload.get(k) for k in ('passed', 'trades', 'blocks', 'trials', 'deflated_sharpe', 'experiment')}})
        return {
            'rung': rung, 'credits_usd': format(self.economy.balance(agent.id), 'f'),
            'blocks': len(self.evaluator.blocks(agent.id)),
            # How far its own evidence is from real money, as the allocator measured it (read only).
            'bunt_line': self.bunt_line(agent),
            'last_trial': next((e.payload for e in reversed(list(self.ledger.iter(kinds='eval.trial', agent=agent.id)))), None),
            'last_look': next((e.payload for e in reversed(list(self.ledger.iter(kinds='eval.verdict', agent=agent.id))) if e.payload.get('decision') in ('look', 'episode-look')), None),
            'can_fork': self.economy.can_fork(agent.id), 'recent_trades': self._recent_trades(agent.id),
            'book_accounting': book.evidence_integrity(agent.id) if book else None,
            'recent_order_outcomes': order_outcomes(self.ledger, agent.id, book.name) if book else [],
            'candidate_submission': {'allowed': True, 'parent_can_fund_child': self.economy.can_fork(agent.id),
                'house_can_stake_replay_pass': True, 'full_seats_queue_candidate': True,
                'style_may_change_within_venue_horizon_specialty': True,
                'note': 'can_fork describes paying an endowment, not permission to research or submit. '
                        'You may replace a failed decision rule with a different hypothesis in your specialty. '
                        'The original lineage and every trial remain counted.'},
            'parameter_validation': parameters.inspect(agent.params, agent.needs),
            'idle': {**self.idle_run(agent), 'why_now': self.idle_reason(agent)},
            # X1 (Sept 24, 2026): whether its entries are paused, since when and why, and its last edit replay.
            'entries': self._entries_standing(agent),
            'rewrites_in_place': rung == 0 or (rung == 1 and self.record_is_empty(agent)),
            'runtime_capabilities': self.research_capabilities(agent),
            'qualification_policy': {
                'replay': dict(ladder['replay']),
                'lineage_trials': len(self.evaluator.family_trials(agent.family, self.registry.lineage(agent.id))),
                'hard_trial_limit': None,
                'paper': {**ladder['paper'], 'required_active_blocks_for_this_horizon': self.evaluator._gate_blocks(1, agent.horizon),
                          'min_closed_trades': ladder['min_closed_trades']},
                'micro': dict(ladder['micro']),
                'completed_exposures': dict(ladder.get('completed_exposures') or {}),
                'audit_reconsideration': {**self.game.get('audit', {}),
                    'fresh_evidence_instead_of_cooldown': bool(self._burst),
                    'fresh_completed_episodes': ladder['completed_exposures']['look_every_episodes'],
                    'fresh_active_blocks': ladder['look_every_active_blocks'],
                    'note': 'A new evidence batch can earn another audit during the accelerated game. The screen and fresh audit must still pass; repeated reads and partial exits do not count.'},
                'live_pilot': self.campaigns.live_pilot() if self.campaigns else None,
                'live_trading': self.campaigns.live_trading() if self.campaigns else None,
                'live_tuition': {k: str(v) if isinstance(v, Decimal) else v for k, v in self.tuition().items()},
                'promotion_status': self._state.get('promotion_status', {}).get(agent.id),
                'new_live_capital_allowed_by_campaign': self.campaigns.allows_live(2) if self.campaigns else self.settings.real_money,
                # Capital is the ladder (Sept 23, 2026): the rules, and this agent's own evidence and band now.
                'allocator': ({**{k: v for k, v in (CONSTITUTION.get('allocator') or {}).items()},
                               'your_band': (self.allocator.board().get('agents') or {}).get(agent.id, {}).get('band'),
                               'your_evidence': (self.allocator.board().get('agents') or {}).get(agent.id, {}).get('evidence'),
                               # P1 (Sept 24, 2026): your family's pooled record decides whether real money
                               # starts as a probe or a bunt (`allocator.family_proven`).
                               'your_family': {k: (self.allocator.board().get('agents') or {}).get(agent.id, {}).get(k)
                                               for k in ('family', 'family_state', 'family_bound', 'family_n', 'capacity', 'stake_limit')},
                               'note': 'While enabled, the paper screen and the micro bound above no longer promote: bands and '
                                       'stakes follow E = W_paper^paper_weight x W_real at every mark pass.'}
                              if allocator_module.enabled() else None),
                'note': 'Replay selection penalties depend on the observed record and trial history; there is no fixed five-to-nine-trial cutoff. The paper gate is a screen, not a positive confidence bound.'},
            'peer_replay_passes': peers[-3:],
            'peer_evidence_note': 'Recorded historical passes, including retired peers. Counterexamples to impossibility claims, not proof of edge or independent validation. Source programs and all trials remain in their own lineages.',
        }

    def research(self, agent: Agent) -> Any:
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None:
                return None
            job = self.research_jobs.enqueue(agent.id, generation)
        session = job['session']
        with self.research_jobs.claim(session) as claimed:
            if not claimed:
                return None
            job = self.research_jobs.get(session)
            if job['status'] not in ('queued', 'working', 'ready', 'applying'):
                return None
            if job['status'] == 'applying':
                # A crash may have occurred after adoption/forking. Keep the outcome on the
                # queue and ledger, but do not repeat a capital/credit/lifecycle side effect.
                self.ledger.append('agent.research', {'tool': 'candidate', 'status': 'commit_unconfirmed',
                    'session': session, 'reason': 'restart during candidate commit; not repeated',
                    '_candidate': (job['outcome'] or {}).get('candidate')}, agent=agent.id,
                    id=f'research-commit-unconfirmed:{session}')
                self._apply_controls(agent.id, session)  # its ids make a second application a no-op (X1)
                self.research_jobs.finish(session, 'candidate commit unconfirmed; evidence retained')
                self._session_lost(agent.id, session, 'candidate commit unconfirmed; evidence retained', recovered=False)
                return None
            with self._lifecycle_lock:
                current = self._generation(agent.id)
                if current is None or list(current[:-1]) != job['generation'][:-1]:
                    if job['status'] == 'ready':
                        # Its pass had ended: what it asked of its entries is still its to have, or is
                        # refused on the record (an edit of a strategy that changed, a dead agent). A stop
                        # between an edit and a pause of one pass moved the generation (X1).
                        self._apply_controls(agent.id, session)
                    self.research_jobs.finish(session, 'retired or changed before resume', cancelled=True)
                    self._session_resumed(session, retired=True)
                    return None
                generation = tuple(job['generation'])
                if job['snapshot'] is None:
                    snapshot = {'agent': asdict(self.registry.get(agent.id)),
                                'standing': self._research_standing(agent)}
                else:
                    snapshot = job['snapshot']
            agent = Agent(**snapshot['agent'])
            if job['status'] in ('queued', 'working'):
                job = self.research_jobs.start(session, snapshot)
                try:
                    outcome = self.researcher.research(agent, snapshot['standing'], session=session)
                except ResearchPending as exc:
                    self.research_jobs.defer(session, str(exc))
                    return None
                except BaseException:
                    # Preserve the checkpoint. A tool intent without a receipt is resolved
                    # conservatively by Researcher on resume, not retried every tick.
                    self.research_jobs.defer(session, 'interrupted before research completion')
                    raise
                self.research_jobs.ready(session, pass_state(outcome))
            else:
                outcome = restore_pass(job['outcome'])
            if outcome.candidate:
                self.research_jobs.applying(session)
                with self._lifecycle_lock:
                    candidate = self._commit_research(agent.id, generation, outcome)
                if candidate:
                    self._admit_researched(agent.id, generation, candidate, session)
                self._trace_adoption(agent.id, session, outcome.candidate)
            # After any candidate (an edit is a new strategy, which moves the generation), and BEFORE the
            # job is done: a restart resumes an unfinished job and applies them (ids make it a no-op the
            # second time), but never a finished one (review of #249: a stop between the two lost the pause).
            # What a pass the provider broke had already asked is the agent's still (X1).
            self._apply_controls(agent.id, session)
            # Sept 24, 2026 (L2): a session the provider broke (a 5xx; `research_gate.provider_fault`) was
            # refunded by the researcher and is not a completed pass: its job is closed as cancelled, so
            # it does not restart the research clock, and the agent may research again in
            # PROVIDER_RETRY_SECONDS instead of after its whole interval. Every other ending is a pass.
            from .research_gate import provider_fault

            broken = provider_fault(getattr(outcome, 'reason', ''))
            # H6 (Sept 25, 2026): a session a restart (or a tool's exception) left unconfirmed was no pass either:
            # it is named in a warning, and its agent's turn comes back as a broken session's does. One that
            # recovered a retained candidate is a pass (its candidate is applied above).
            reason = str(getattr(outcome, 'reason', '') or '')
            if reason.startswith(SESSION_LOSSES):
                broken = self._session_lost(agent.id, session, reason, recovered=bool(outcome.candidate)) or broken
            else:
                self._session_resumed(session)
            retry = self.research_interval_hours(agent) * 3600 - PROVIDER_RETRY_SECONDS if broken else 0.0
            self.research_jobs.finish(session, getattr(outcome, 'reason', 'finished'), cancelled=broken)
            self._note_research_result(agent.id, outcome)
            with self._lifecycle_lock:
                with self._state_lock:
                    if self._generation(agent.id) is not None:
                        self._state['last_research'][agent.id] = self.clock() - max(0.0, retry)
            return outcome

    def _trace_adoption(self, agent_id: str, session: str, candidate: Mapping[str, Any]) -> None:
        """Join what became of a pass's candidate to its research trace (league/traces.py)."""
        traces = getattr(self.researcher, 'traces', None)
        if traces is None:
            return
        from .traces import adoption_outcome, trace_id

        try:
            outcome, useful = adoption_outcome(self.ledger, self.registry, agent_id, session, candidate)
            traces.outcome(trace_id('research', session), outcome=outcome, useful=useful, agent=agent_id)
        except Exception as exc:  # noqa: BLE001 - a trace never costs an adoption
            self.alert('warning', f'trace outcome for {agent_id}: {type(exc).__name__}: {str(exc)[:160]}')

    def _cancel_retired_research(self):
        for job in self.research_jobs.pending():
            if self._generation(job['agent']) is not None:
                continue
            with self.research_jobs.claim(job['session']) as claimed:
                if claimed:
                    self.research_jobs.finish(job['session'], 'retired before resume', cancelled=True)
                    self._session_resumed(job['session'], retired=True)

    def _session_resumed(self, session: str, *, retired: bool = False) -> None:
        """H6: a session in flight at this House's start has ended as sessions do (`resumed`), or was closed
        because its agent died or changed meanwhile (`retired`: not the restart's doing)."""
        with self._state_lock:
            book = self._restart_research
            if book["in_flight"].pop(session, None) is not None:
                book["retired" if retired else "resumed"] += 1

    def _session_lost(self, agent_id: str, session: str, reason: str, *, recovered: bool) -> bool:
        """H6 (Sept 25, 2026): a research session that ended unconfirmed (`SESSION_LOSSES`, or a candidate
        commit a restart interrupted) is kept for the next tick's warning (`_tell_lost_sessions`) and for
        health.json `restart_research.lost`, whether it began before this House's start or not (a tool that
        raised leaves the same state). Returns True when it produced nothing -- no retained candidate was
        recovered -- so its agent gets its turn back (`research`)."""
        with self._state_lock:
            book = self._restart_research
            spanned = book["in_flight"].pop(session, None) is not None
            row = {"session": session, "agent": agent_id, "reason": str(reason)[:160], "at": now_iso(self.clock),
                   "began_before_start": spanned, "candidate_recovered": bool(recovered)}
            book["lost"] = (book["lost"] + [row])[-SESSION_LOSSES_SHOWN:]
            book["lost_count"] = int(book.get("lost_count") or 0) + 1
            book["untold"].append(row)
        return not recovered

    def _tell_lost_sessions(self) -> None:
        """One warning a tick names every research session lost since the last (`_session_lost`). One a tick,
        not one a session: after a restart several end within minutes of each other, and ten warnings of one
        text in half an hour escalate to an error (`REPEAT_WARNINGS`) that a deploy's watch would read as the
        new release's failure (Sept 25, 2026: up to four sessions a restart, two restarts five minutes apart)."""
        with self._state_lock:
            rows, self._restart_research["untold"] = list(self._restart_research["untold"]), []
        if not rows:
            return
        spanned = [row for row in rows if row["began_before_start"]]
        where = (f"lost to the restart at {self._restart_research['started_at']}" if len(spanned) == len(rows)
                 else "ended unconfirmed")
        names = "; ".join(f"{row['session']} ({row['reason']}{', its retained candidate recovered' if row['candidate_recovered'] else ''})"
                          for row in rows)
        self.alert("warning", f"{len(rows)} research session{'' if len(rows) == 1 else 's'} {where}: {names}"[:1000],
                   sessions=[row["session"] for row in rows], agents=sorted({row["agent"] for row in rows}))

    def _admission_gate(self, row, *, displace=False):
        """An admission's checks, under the lifecycle lock and with no Sail call: `(parent, candidate,
        staked, niche, loser)` when it may go ahead, else None with the row recorded (waiting,
        cancelled or unconfirmed)."""
        queue = Admissions(self.ledger)
        if row['status'] == 'admitting':
            queue.record(row, 'unconfirmed', 'restart during admission; inspect the retained evidence before retrying')
            return None
        if row['status'] not in ('queued', 'deferred'):
            return None
        parent = self.registry.get(row['agent'])
        generation = self._generation(row['agent'])
        expected = row.get('_generation')
        if expected is None:  # a deferred receipt written before the queue existed
            job = self.research_jobs.get(row['session'])
            expected = job['generation'] if job else None
        if generation is None or expected is None or list(generation[:-1]) != list(expected[:-1]):
            queue.record(row, 'cancelled', 'parent retired or changed; candidate evidence retained')
            return None
        candidate = row['_candidate']
        if candidate.get('passed') is not True or parameters.inspect(candidate['params'], candidate['needs'])['errors']:
            queue.record(row, 'cancelled', 'candidate did not pass replay or has invalid parameters')
            return None
        rules = self.game['economy']
        staked = not self.economy.can_fork(parent.id)
        if staked and self.clock() - float(self._state.setdefault('last_staked', {}).get(parent.id) or 0) < float(rules['epoch_seconds']):
            queue.record(row, 'deferred', 'waiting for the parent House-endowment cadence')
            return None
        niche = self.niche_of(parent)
        niche_full = niche is not None and self.members(niche.id) >= niche.max_members
        full = len(self.registry.living()) >= int(rules['max_population'])
        loser = None
        if niche_full or full:
            if displace:
                # It asks as its parent's family (S1, Sept 24, 2026). A living author's candidate waits out a new
                # paper seat's grace, as before; a dead author's retained one is evidenced (`_admit_orphan`).
                loser = self._weakest(rules, specialty=niche.id if niche_full else None, exclude=(parent.id,),
                                      newcomer=Newcomer(family=self._candidate_family(parent, candidate, niche), venue=parent.venue,
                                                        what=f"{parent.id}'s research candidate"))
            if loser is None:
                queue.record(row, 'deferred', 'niche is full; waiting for an eligible seat' if niche_full else 'population is full; waiting for an eligible seat')
                return None
        return parent, candidate, staked, niche, loser

    def _admit_candidate(self, row, *, displace=False, described=None):
        """Retry a known deferred fork under the lifecycle lock; never retry an unknown write.

        `described`: the candidate's NEEDS, read in the probe box by a caller that holds the lifecycle
        lock and must make no Sail call under it (`_admit_researched`, which never displaces)."""
        gate = self._admission_gate(row, displace=displace)
        if gate is None:
            return None
        parent, candidate, staked, niche, loser = gate
        queue = Admissions(self.ledger)
        if loser is not None:
            # Verify the replacement before retiring anyone. Its module executes only in the
            # sealed probe box, exactly as at spawn. A bad file must not displace a resident.
            try:
                validated = self.sandbox.needs(PROBE_BOX, candidate['code'])
                self._charge_box(parent.id, validated, note='validating a deferred candidate admission')
                info = validated.result
                if not info.get('ok') or niche_of(info['needs'])[:2] != (parent.venue, parent.horizon):
                    raise ValueError('candidate no longer describes the same venue and horizon')
                needs = niches_module.constrain(info['needs'], niche) if niche else info['needs']
                if needs != candidate['needs']:
                    raise ValueError('candidate description differs from its replayed inputs')
                parameters.require_valid({**info.get('params', {}), **candidate['params']}, needs)
            except Exception as exc:
                queue.record(row, 'deferred', f'candidate validation unavailable: {type(exc).__name__}: {str(exc)[:160]}')
                return None
        # The child's birth probes its NEEDS in the probe box, under the lifecycle lock, so it never
        # waits long for that box: held by background work, the admission is deferred and retried,
        # before anything is written. Already `described`, the birth needs no box at all.
        claim = getattr(self.sandbox, 'claim', None) if described is None else None
        with claim(PROBE_BOX, wait=self.settings.probe_wait_seconds) if claim is not None else nullcontext(True) as free:
            if not free:
                queue.record(row, 'deferred', 'the probe box is in use by background work; retried at the next admission pass')
                return None
            queue.record(row, 'admitting', 'paper admission write started', displaced=loser.id if loser else None)
            try:
                if loser is not None:
                    self.kill(loser, 'displaced', self.postmortem(loser, 'displaced',
                        'a replay-passing deferred candidate has priority over an untested mutation'))
                child = self.fork(parent, code=candidate['code'], params=candidate['params'],
                                  reason=candidate['purpose'], passed_replay=True, staked_by_house=staked, described=described)
            except SandboxError as exc:
                if loser is None:
                    # Sail did not answer before anything was born (the NEEDS probe comes first): a
                    # deferral, not an unknown write. With a resident displaced it stays unconfirmed.
                    queue.record(row, 'deferred', f'infrastructure: {type(exc).__name__}: {str(exc)[:160]}')
                    return None
                queue.record(row, 'unconfirmed', f'admission interrupted: {type(exc).__name__}: {str(exc)[:160]}')
                self.alert('warning', f"{parent.id}: candidate admission is unconfirmed; retained for inspection")
                return None
            except Exception as exc:
                queue.record(row, 'unconfirmed', f'admission interrupted: {type(exc).__name__}: {str(exc)[:160]}')
                self.alert('warning', f"{parent.id}: candidate admission is unconfirmed; retained for inspection")
                return None
        if child is None:
            queue.record(row, 'deferred', 'fork returned without admission; capacity or endowment unavailable')
            return None
        queue.record(row, 'admitted', 'a replay-passing child was seated on paper', child=child.id)
        return child

    def _admit_researched(self, agent_id: str, generation: tuple, candidate: Mapping[str, Any], session: str) -> Agent | None:
        """A research candidate's child, from the research thread, with no Sail call under the
        lifecycle lock. Every wake of the tick takes that lock, so Sail stalling under it stalls the
        whole tick, and TERM with it (review of PR 159: this path held it through the child's NEEDS
        probe and the parent's box fork, a checkpoint and a restore at the client's ten- and
        fifteen-minute timeouts). So: the queue row and its checks first (an admission that must
        wait buys no probe); then the NEEDS probe, holding nothing but the probe box; then, under
        the lock again, the birth from that probe's result into a box from the clean image. The row
        is read back before the birth, so a candidate the tick's admission pass seated meanwhile is
        never born twice. A busy probe box or a Sail failure leaves it deferred for that pass:
        infrastructure, never the candidate's result."""
        queue = Admissions(self.ledger)
        with self._lifecycle_lock:
            row = queue.enqueue(agent_id, generation, candidate, session)
            if self._admission_gate(row) is None:
                return None
        described, why = None, ''
        claim = getattr(self.sandbox, 'claim', None)
        try:
            with claim(PROBE_BOX, wait=600) if claim is not None else nullcontext(True) as free:
                if free:
                    described = self.sandbox.needs(PROBE_BOX, candidate['code'])
                else:
                    why = 'the probe box is in use by background work; retried at the next admission pass'
        except Exception as exc:  # noqa: BLE001 - nothing is written yet: the admission pass retries it
            why = f"{'infrastructure' if isinstance(exc, SandboxError) else 'NEEDS probe failed'}: {type(exc).__name__}: {str(exc)[:160]}"
        with self._lifecycle_lock, self._box_patience():
            row = queue.enqueue(agent_id, generation, candidate, session)  # as it stands now
            if described is None:
                if row['status'] in ('queued', 'deferred'):
                    queue.record(row, 'deferred', why)
                return None
            child = self._admit_candidate(row, described=described)
            if child is None and row.get('status') != 'unconfirmed' and self._generation(agent_id) is not None:
                # The probe seated nobody (the seat went meanwhile, or the tick's pass seated it):
                # its seconds are the parent's, as a validation probe's are.
                self._charge_box(agent_id, described, note="reading a candidate's NEEDS for an admission that did not seat it")
            return child

    # ------------------------------------------------------- retained candidates (S3)
    def _retainable(self, row: Mapping[str, Any]) -> bool:
        """An admission whose candidate a seat can be given to: it passed the House's replay, and its
        parameters are valid for its inputs."""
        candidate = row.get("_candidate")
        if not isinstance(candidate, Mapping) or candidate.get("passed") is not True or not candidate.get("code"):
            return False
        try:
            return not parameters.inspect(candidate.get("params") or {}, candidate.get("needs") or {})["errors"]
        except Exception:  # noqa: BLE001 - a candidate that cannot be read cannot be seated
            return False

    def _retain(self, author: Agent, row: dict[str, Any], why: str) -> dict[str, Any]:
        """Hand one retained candidate of a dead author to the seat queue: its admission row goes
        `orphaned` (written once) and a waiter is kept in house.json (`retained`, by session)."""
        died = _epoch(author.died_at) if author.died_at else self.clock()
        numbers = (row.get("_candidate") or {}).get("numbers") or {}
        entry = {"session": row["session"], "author": author.id, "venue": author.venue,
                 "family": self._candidate_family(author, row.get("_candidate") or {}, self.niche_of(author)),
                 "niche": author.specialty or "", "since": died, "trades": numbers.get("trades"),
                 "return_pct": numbers.get("return_pct")}
        if row.get("status") != "orphaned":
            Admissions(self.ledger).record(row, "orphaned", why, author_died_at=author.died_at)
        with self._state_lock:
            self._state.setdefault("retained", {})[row["session"]] = entry
            self._state.setdefault("retained_authors", {})[author.id] = died
        self._data_cache.pop("seat_waiters", None)
        return entry

    def _hand_off_retained(self, author: Agent, cause: str) -> dict[str, Any] | None:
        """S3 (the close-the-gaps run, Sept 24, 2026): a resident that dies holding a replay-passed research
        candidate hands its LATEST one to the seat queue with its lineage, instead of it being cancelled with
        it. mullins-14 died `displaced` at 00:12:02Z Sept 24 holding three (the latest made +38.4% on 113
        replay trades) and its admissions were cancelled "parent retired or changed" at 01:38:54Z. Its other
        admissions are cancelled by the admission pass as before. Called by `kill` under the lifecycle lock;
        it reads only the author's own rows."""
        latest = None
        for row in Admissions(self.ledger).rows(agent=author.id):
            if row.get("status") in ("queued", "deferred") and self._retainable(row):
                latest = row  # oldest first: the last is the latest
        if latest is None:
            return None
        return self._retain(self.registry.get(author.id), latest,
                            f"its author {author.id} died ({cause}) holding it: it waits for a seat with its author's lineage")

    def _adopt_orphans(self, rows: Sequence[dict[str, Any]]) -> int:
        """The retroactive half of S3, from the admission pass's own fold: the latest replay-passed candidate of
        each author that died within `RETAINED_TTL_SECONDS` -- still pending, or cancelled with it ("parent
        retired or changed; candidate evidence retained") before this rule reached the floor -- enters the
        seat queue, once an author. mullins-14's is the case."""
        now = self.clock()
        with self._state_lock:
            handled = {a: at for a, at in (self._state.get("retained_authors") or {}).items()
                       if now - float(at or 0) <= self.RETAINED_TTL_SECONDS}
            self._state["retained_authors"] = handled
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            author = self.registry.get(str(row.get("agent") or ""))
            if author is None or author.alive or author.id in handled or not author.died_at:
                continue
            if now - _epoch(author.died_at) > self.RETAINED_TTL_SECONDS:
                continue
            status = row.get("status")
            if (status in ("queued", "deferred", "orphaned") or (status == "cancelled" and row.get("reason") == self.RETAINED_CANCELLED)) \
                    and self._retainable(row):
                latest[author.id] = row  # the fold is oldest first: the last is the latest
        for author_id, row in latest.items():
            self._retain(self.registry.get(author_id), row, f"its author {author_id} died holding it: it waits for a seat with its "
                                                            "author's lineage (picked up after the author's death)")
        return len(latest)

    def _retained_waiting(self, *, expired: bool = False, left: bool = False) -> list[dict[str, Any]]:
        """The retained candidates waiting for a seat (house.json `retained`) in the order the admission
        pass seats them: a proven family's first -- the seat follows proof at the family level (at T0 only
        mullins-14's weather-favorites was proven among fourteen authors that had died holding candidates
        that day, and it had died after ten of them) -- then the longest wait. Those past
        `RETAINED_TTL_SECONDS`, and those that left the seat queue (R2, `_expire_waiters`), only with `expired`
        (the admission pass drops the first and holds the second); those that left the seat queue also with
        `left` (`seat_waiters`, which asks each pass whether their reason is gone: the review of #276)."""
        now = self.clock()
        gone = self._state.get("seat_expired") or {}
        rows = [dict(r) for r in (self._state.get("retained") or {}).values()
                if expired or (now - float(r.get("since") or 0) <= self.RETAINED_TTL_SECONDS
                               and (left or f"retained:{r.get('session')}" not in gone))]
        return sorted(rows, key=lambda r: (not self._family_proven(r.get("family"), r.get("venue")),
                                           float(r.get("since") or 0), str(r.get("session"))))

    def _admit_orphan(self, entry: Mapping[str, Any], rules: Mapping[str, Any], rows: Sequence[dict[str, Any]]) -> Agent | None:
        """Seat one retained candidate of a dead author (S3), under the lifecycle lock: born on its author's
        line (the author is its parent, so it inherits the author's selection path and holdout ration),
        House-staked, seated on paper because its code passed replay as the author's candidate, and told as
        a `retained` birth. It asks for a seat as its author's family with no forward score of its own
        (`_weakest`, evidenced). A file that would displace a resident is read in the probe box first, as
        `_admit_candidate` reads one; one that cannot be born, or that a living agent already runs, is
        dropped; one past `RETAINED_TTL_SECONDS` is dropped as too old, and one that left the seat queue
        because the search closed its desk (R2, `_expire_waiters`) is held, never seated, until the desk reopens
        or that TTL drops it."""
        queue = Admissions(self.ledger)
        session = str(entry.get("session"))
        row = next((r for r in rows if r.get("session") == session), None)
        author = self.registry.get(str(entry.get("author") or ""))

        def forget() -> None:
            with self._state_lock:
                (self._state.get("retained") or {}).pop(session, None)
            self._data_cache.pop("seat_waiters", None)

        if row is None or author is None or row.get("status") != "orphaned":
            forget()  # seated, dropped or left unconfirmed by an earlier pass
            return None
        if self.clock() - float(entry.get("since") or 0) > self.RETAINED_TTL_SECONDS:
            queue.record(row, "dropped", f"no seat within {self.RETAINED_TTL_SECONDS / 3600:g} hours of its author's death: "
                                         "its replay is too old to seat")
            forget()
            return None
        if (self._state.get("seat_expired") or {}).get(f"retained:{session}"):
            # It left the seat queue while the search closes its desk (R2, `_expire_waiters`): never counted, never
            # seated there, and back in the queue if the desk reopens inside its TTL. Dropped here, a desk closed for
            # one pass lost a replay-passed program for good (the review of #276).
            return None
        candidate = row["_candidate"]
        living = self.registry.living()
        sha = code_sha(candidate["code"])
        if any(a.code_sha256 == sha and dict(a.params or {}) == dict(candidate.get("params") or {}) for a in living):
            queue.record(row, "dropped", "a living agent already runs this program")
            forget()
            return None
        niche = self.niche_of(author)
        if niche is None or niche.dormant:
            queue.record(row, "orphaned", "its desk is closed: it waits for it to open")
            return None
        niche_full = self.members(niche.id) >= niche.max_members
        loser = None
        if niche_full or len(living) >= int(rules["max_population"]):
            loser = self._weakest(rules, specialty=niche.id if niche_full else None, evidenced=True,
                                  newcomer=Newcomer(family=self._candidate_family(author, candidate, niche), venue=author.venue,
                                                    what=f"the retained candidate of {author.id}"))
            if loser is None:
                queue.record(row, "orphaned", f"waiting for an eligible seat: {'its desk' if niche_full else 'the league'} is full of "
                                              "residents that may not be displaced")
                return None
        claim = getattr(self.sandbox, "claim", None)
        with claim(PROBE_BOX, wait=self.settings.probe_wait_seconds) if claim is not None else nullcontext(True) as free:
            if not free:
                return None  # the probe box is in use by background work: the next admission pass
            try:
                described = self.sandbox.needs(PROBE_BOX, candidate["code"])
                info = described.result
                if not info.get("ok"):
                    raise ValueError(str(info.get("error") or "its NEEDS could not be read"))
                if loser is not None:
                    # A bad file must not displace a resident: the replayed inputs, exactly (`_admit_candidate`).
                    if not info.get("ok") or niche_of(info["needs"])[:2] != (author.venue, author.horizon):
                        raise ValueError("it no longer describes its author's venue and horizon")
                    if niches_module.constrain(info["needs"], niche) != candidate["needs"]:
                        raise ValueError("its description differs from the inputs it was replayed on")
                    parameters.require_valid({**info.get("params", {}), **candidate["params"]}, candidate["needs"])
            except SandboxError as exc:
                self._defer("retained", f"infrastructure: {type(exc).__name__}: {str(exc)[:200]}")
                return None
            except Exception as exc:  # noqa: BLE001 - the file cannot be born: nothing was written
                queue.record(row, "dropped", f"it cannot be born: {type(exc).__name__}: {str(exc)[:160]}")
                forget()
                return None
            queue.record(row, "admitting", "paper admission write started", displaced=loser.id if loser else None)
            purpose = str(candidate.get("purpose") or "")
            try:
                if loser is not None:
                    self.kill(loser, "displaced", self.postmortem(loser, "displaced",
                              f"the retained research candidate of {author.id}, which died holding it, takes the seat"))
                child = self.spawn(author.line or author.name, author.family, candidate["code"], parent=author.id,
                                   params=candidate["params"], endowment=rules["endowment_usd"], described=described, new_code_of=author,
                                   reason=f"the retained research candidate of {author.id}, which died holding it: {purpose}"[:1500])
            except Exception as exc:  # noqa: BLE001 - an unknown write is kept for inspection, never retried
                if isinstance(exc, ValueError) and loser is None:
                    # `spawn` refused it before anything was written (no open specialty for its NEEDS).
                    queue.record(row, "dropped", f"it cannot be born: {str(exc)[:200]}")
                else:
                    queue.record(row, "unconfirmed", f"admission interrupted: {type(exc).__name__}: {str(exc)[:160]}")
                    self.alert("warning", f"{author.id}'s retained candidate: its admission is unconfirmed; retained for inspection")
                forget()
                return None
        self.evaluator.seat(child.id, 1, f"its code passed replay as the candidate of {author.id}, which died before it was seated")
        with self._state_lock:
            self._state["tried"][child.id] = child.code_sha256
        self.seat(child)
        numbers = candidate.get("numbers") or {}
        self.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["endowment_usd"], "box_forked": False,
                                            "reason": purpose[:600], "new_code": True, "staked_by": "house", "retained": True},
                           agent=author.id)
        if self.ledger.get(f"birth-route:{child.id}") is None:
            self.ledger.append("route.decision", {"task": f"birth:{child.id}", "route": "retained", "model": None,
                                                   "reason": f"the retained research candidate of {author.id}, which died holding it",
                                                   "evidence": {"author": author.id, "session": session, "replay_passed": True,
                                                                "trades": numbers.get("trades"), "return_pct": numbers.get("return_pct"),
                                                                "displaced": loser.id if loser else None}},
                               id=f"birth-route:{child.id}")
        queue.record(row, "admitted", "the retained candidate of a dead author was seated on paper", child=child.id)
        forget()
        return child

    def _commit_research(self, agent_id: str, generation: tuple, outcome: Any) -> dict[str, Any] | None:
        """Apply a candidate under the lifecycle lock, or return it for a separate child."""
        # A pass can outlive a promotion, a displacement or another code adoption. Its old
        # rung must never authorize replacing code that has since acquired a trading record.
        current_generation = self._generation(agent_id)
        if current_generation is None or current_generation[:-1] != generation[:-1]:
            if outcome.candidate:
                self.ledger.append("agent.research", {"tool": "candidate", "status": "not_adopted",
                    "reason": "the agent retired or its code changed during research",
                    "_candidate": outcome.candidate}, agent=agent_id)
            return None
        agent = self.registry.get(agent_id)
        rung = self.evaluator.rung(agent.id)
        candidate = outcome.candidate
        if candidate:
            errors = parameters.inspect(candidate['params'], candidate['needs'])['errors']
            if errors:
                self.ledger.append('agent.research', {'tool': 'candidate', 'status': 'not_adopted',
                    'reason': 'invalid parameters: ' + '; '.join(errors), '_candidate': candidate}, agent=agent.id)
                return None
        barren = self.idle_run(agent)["barren"]
        repair = bool(candidate and rung == 0 and not parameters.inspect(agent.params, agent.needs)['valid']
                      and self.record_is_empty(agent) and candidate['needs'] == agent.needs
                      and parameters.same_logic(agent.code, candidate['code']))
        if candidate is not None and not candidate.get("passed", True):
            # A failed replay buys nothing -- unless the agent is in the one position where replay
            # cannot help it. Measured Sept 20, 2026: the six agents of the sports desk each saw up
            # to two hundred live markets, found none inside the band they were born with, ran
            # thirteen research passes and eight trials between them, and rewrote themselves NOT
            # ONCE, because a looser rule that fires twice on a thin tape can never clear twenty
            # closed trades. Their live rules were therefore frozen exactly as born. With no record
            # to protect and no position in hand, a file that at least TRADES is worth more than
            # one that provably does nothing, and the paper screen is what stands above it.
            traded = float(candidate.get("numbers", {}).get("trades") or 0) > 0
            if not repair and not (traded and rung == 1 and self.record_is_empty(agent) and barren >= int((self.game.get("research") or {}).get("idle", {}).get("barren_wakes", 10))):
                candidate = None
        if candidate and outcome.consulted and candidate["code"].strip() == outcome.consulted.strip():
            candidate = {**candidate, "purpose": "A specialist wrote this file for it: " + candidate["purpose"]}
        if candidate:
            if rung == 0 or (rung == 1 and self.record_is_empty(agent)):
                # Empty paper records can restart in place. A real-money identity always forks
                # new code: its existing code earned the paper screen and audit, even before
                # its first real trade has created a record in the current book.
                was = self.registry.get(agent.id).code_sha256
                self.registry.adopt(agent.id, code=candidate["code"], needs=candidate["needs"], params=candidate["params"], reason=candidate["purpose"])
                self._state["tried"][agent.id] = self.registry.get(agent.id).code_sha256
                self._state["idle"].pop(agent.id, None)  # new rules, a fresh count of the wakes they sit out
                if repair and not candidate.get('passed', True):
                    self.ledger.append('agent.research', {'tool': 'parameter_repair', 'status': 'adopted',
                        'reason': 'invalid configuration repaired with unchanged decision logic; replay did not qualify',
                        'rung': 0, 'passed_replay': False, 'prior_code_sha256': was,
                        'code_sha256': self.registry.get(agent.id).code_sha256}, agent=agent.id)
                    return None  # preserve rung, trial history, credits and all qualification gates
                if rung == 0:
                    self.evaluator.promote(agent.id, 1, "its new code passed replay against every trial in its own line", candidate["numbers"])
                else:
                    why = ("it rewrote itself: it had no record to protect" if candidate.get("passed", True) else
                           f"it rewrote itself: its own rules had not fired in {barren} wakes with a live market in "
                           f"front of them, it had no record to protect, and this file at least trades")
                    self.ledger.append("agent.strategy", {"code_sha256": self.registry.get(agent.id).code_sha256, "was": was,
                                                          "reason": why, "passed_replay": bool(candidate.get("passed", True)), "_code": candidate["code"],
                                                          "params": candidate["params"], "needs": candidate["needs"]}, agent=agent.id)
                self.seat(self.registry.get(agent.id))
            else:
                return candidate
        return None

    def _control_refusal(self, agent: Agent, control: str) -> str:
        """Why this control (X1) may not be recorded for this agent now, or "".

        A pause or resume restates the strategy in force: it moves no generation and sets no audit
        verdict aside (`allocator.adopted_strategy`), so it is always made -- a vetoed or audited agent
        on real money can hold its own entries (review of #249).

        An edit is a new strategy (its PARAMS), and two readers take it as one: an audit in flight is
        dropped as stale when the generation moves (a veto of an agent already on real money would
        then never be acted on), and `allocator.audit_standing` reads no verdict from before it (a veto
        would be set aside before its cooldown). So none is made while an audit of the agent runs or
        is owed, or while its latest audit is a veto. Nor while an audit's approval of the strategy as
        it runs stands and the agent is on real money (rung 2 or above: a swing's first entry is
        audited, a known defect's bunt is audited, and the auditor reads the PARAMS): the edit would
        trade PARAMS the auditor never saw, and nothing audits a seated swing again (review of #249:
        a swing raised its notional 30 -> 37 in place and kept the band). Called under the lifecycle
        lock, as audits are started under it."""
        if control == "resume_entries":
            # The R5 drain hold (`_hold_draining_probes`): the House's row, or the probe's own pause while it waits to be
            # flat. The row's session speaks for the House too when house.json lost its entry (the adversarial review of
            # the hold, Sept 24, 2026).
            with self._state_lock:
                held = (self._state.get("drain_holds") or {}).get(agent.id)
            paused = self.registry.entries_paused(agent.id) or {}
            if not held and paused.get("session") == self.DRAIN_SESSION:
                held = paused.get("since")
            if held:
                return (f"the House holds your entries since {held}: your family's pooled forward record is losing, so a probe on it only "
                        "exits until it is flat and goes back to practice (allocator.family_probe); the hold ends then")
        if control != "edit_params":
            return ""
        with self._state_lock:
            auditing = agent.id in (self._state.get(self.AUDITS) or {})
        if auditing or self._audit_owed(agent) is not None:
            return "an audit of your strategy is under way or owed; a change recorded now would set its verdict aside. Ask again after it"
        standing = allocator_module.audit_standing(self, agent)
        if standing == "vetoed":
            return ("the latest audit of your strategy vetoed it; a change recorded now would read as new code to the audit check, "
                    "so none is made while the veto stands")
        if standing == "approved" and self.evaluator.rung(agent.id) >= 2:
            return ("an audit approved your strategy as it runs and you stand on real money: an edit in place would trade PARAMS "
                    "that audit never saw. Pause your entries, or replay the changed file for a new agent")
        return ""

    def _apply_controls(self, agent_id: str, session: str) -> list[str]:
        """Apply what a finished research pass asked of the agent's own deployed strategy (X1, Sept 24,
        2026): the `agent.research` rows `Researcher._request_control` wrote (tool "control", status
        "requested"), oldest first. Returns the controls applied.

        Each is one `agent.strategy` row (id `control:<session>:<n>`) restating the strategy in force,
        with `control`, `was` (the state before) and the agent's `note`, so the ledger shows it and the
        registry folds it: `pause_entries` (entries "paused"), `resume_entries` (entries "open"), or
        `edit_params` (the replayed PARAMS). Its `reason` is carried from the row before, so a reader
        that asks why this strategy (`hypotheses._mechanism`) still gets the strategy's answer. One
        that cannot be made is a status row (`control-refused:<session>:<n>`, status "not_applied")
        saying why. Both ids make a restart's second look a no-op. Neither touches a limit, a stake or a
        band: the book, the allocator and every rule above them still decide those."""
        applied: list[str] = []
        # Read in full, never from a window of the newest rows (an agent writes up to 1,700 research rows a
        # day, and a pass resumed after a restart is applied late: review of #249).
        research = [e for e in self.ledger.iter(kinds="agent.research", agent=agent_id)
                    if e.payload.get("session") == session and e.payload.get("tool") in ("control", "edit_replay")]
        rows = [e for e in research if e.payload.get("tool") == "control" and e.payload.get("status") == "requested"]
        for entry in rows:
            key = entry.id.split("control-request:", 1)[1] if entry.id.startswith("control-request:") else f"{session}:{entry.seq}"
            if self.ledger.get(f"control:{key}") is not None or self.ledger.get(f"control-refused:{key}") is not None:
                continue
            p, control = entry.payload, str(entry.payload.get("control") or "")
            with self._lifecycle_lock:
                agent = self.registry.get(agent_id)
                refusal = "" if agent is not None and agent.alive else "the agent is no longer alive"
                refusal = refusal or self._control_refusal(agent, control)
                paused = self.registry.entries_paused(agent_id)
                if not refusal and control == "pause_entries" and paused and paused.get("session") != self.DRAIN_SESSION:
                    refusal = f"its entries were already paused (since {paused.get('since')})"
                elif not refusal and control == "resume_entries" and not paused:
                    refusal = "its entries were not paused"
                elif not refusal and control == "edit_params":
                    # Made only on the House's own record of a passing replay of exactly this edit in
                    # this pass (`_edit_replay`), never on the request's word alone.
                    replayed = any(e.payload.get("tool") == "edit_replay" and e.payload.get("passed") is True
                                   and e.payload.get("params") == p.get("params") and e.payload.get("was") == p.get("was")
                                   for e in research)
                    if not replayed:
                        refusal = "no passing replay of this edit is on record for the pass: the edit is not made"
                    elif (agent.code_sha256, agent.params) != (p.get("code_sha256"), p.get("was")):
                        refusal = "its strategy changed after the edit was replayed: the edit is not made"
                    elif not isinstance(p.get("params"), Mapping) or not parameters.inspect(dict(p["params"]), agent.needs)["valid"]:
                        refusal = "the edited parameters are not valid for its NEEDS"
                elif not refusal and control not in ("pause_entries", "resume_entries", "edit_params"):
                    refusal = f"no such control {control!r}"
                if refusal:
                    self.ledger.append("agent.research", {"tool": "control", "status": "not_applied", "control": control,
                                                          "session": session, "reason": refusal}, agent=agent_id, id=f"control-refused:{key}")
                    continue
                prior = self.ledger.last("agent.strategy", agent=agent_id)
                carried = str((prior.payload if prior is not None else {}).get("reason") or "")
                row: dict[str, Any] = {"code_sha256": agent.code_sha256, "params": dict(agent.params), "needs": dict(agent.needs),
                                       "wake_minutes": agent.wake_minutes, "_code": agent.code, "control": control,
                                       "note": str(p.get("note") or "")[:600], "session": session, **({"reason": carried} if carried else {})}
                if control == "pause_entries":
                    # Over the House's drain hold, its own pause takes the hold over (the adversarial review of the hold,
                    # Sept 24, 2026): refused as "already paused", it was lost, and the House's release then opened the
                    # entries it had asked to hold. Its own now, it outlasts the drain, as a pause made before it does.
                    row.update(entries="paused", was={"entries": "paused", "since": paused.get("since"), "session": self.DRAIN_SESSION}
                               if paused else {"entries": "open"})
                elif control == "resume_entries":
                    row.update(entries="open", was={"entries": "paused", "since": paused.get("since")})
                else:
                    row.update(params=dict(p["params"]), was={"params": dict(agent.params)}, replay=p.get("replay"))
                self.ledger.append("agent.strategy", row, agent=agent_id, id=f"control:{key}")
                self.registry.refresh()
                if control == "pause_entries":
                    # Its resting buys go now, not at its next wake, `wake_minutes` away (up to a day):
                    # a bid left resting filled after the agent asked for no more entries (review of
                    # #249). A cancel the venue refuses is asked again at each wake.
                    book = self.book_of(agent)
                    if book is not None:
                        try:
                            self._cancel_paused_entries(agent, book)
                        except Exception as exc:  # noqa: BLE001 - the pause stands; its next wake cancels again
                            self.alert("warning", f"{agent_id}: its resting buys could not be cancelled at its pause "
                                                  f"({type(exc).__name__}: {str(exc)[:160]}); its next wake asks again")
                if control == "edit_params":
                    with self._state_lock:
                        self._state["idle"].pop(agent_id, None)  # new parameters, a fresh count of the wakes they sit out
                applied.append(control)
        return applied

    def _entries_standing(self, agent: Agent) -> dict[str, Any]:
        """What a research pass is shown of its entry controls (X1): paused or open, since when, why, and
        how many buys the House has held since; and its last in-place edit replay."""
        paused = self.registry.entries_paused(agent.id)
        out: dict[str, Any] = {"state": "paused" if paused else "open",
                               "tools": "pause_entries / resume_entries hold and release your buys (your sells always go on); edit_params "
                                        "changes your PARAMS in place once its replay at half notional passes"}
        if paused:
            since = str(paused.get("since") or "")
            held = sum(int(e.payload.get("held") or 0) for e in self.ledger.read(kinds="agent.woke", agent=agent.id, limit=2000, newest=True)
                       if e.at >= since)
            out.update(since=since, note=paused.get("note"), held_since_pause=held)
        last = next(reversed(self._edit_looks([agent.id])), None)
        if last is not None:
            out["last_edit_replay"] = {"at": last.at, "passed": last.payload.get("passed"), "reasons": last.payload.get("reasons"),
                                       "next_allowed_at": now_iso(lambda: _epoch(last.at) + EDIT_REPLAY_EVERY_SECONDS)}
        return out

    def record_is_empty(self, agent: Agent) -> bool:
        """True when nothing this agent has done could be evidence and nothing is in its hands: no
        holding, no working order, no active block and no closed trade on the book of its rung.
        On paper this permits an in-place rewrite: no record or position is inherited. A real
        agent still has its earlier paper qualification to protect and must fork new code."""
        book = self.book_of(agent)
        if book is None:
            return True
        if book.account(agent.id).holdings or book.open_orders(agent.id):
            return False  # new code must not inherit a position it does not know how to leave
        entered = self.evaluator._rung_entered(agent.id)
        if any(row.get("active") for row in self.evaluator.blocks(agent.id, since_seq=entered, book=book.name)):
            return False
        returns, _ = self.evaluator.trade_returns(agent.id, book.name, since_seq=entered)
        return not returns

    def _recent_trades(self, agent_id: str, limit: int = 12) -> list[dict[str, Any]]:
        """Its own last closed trades, forward-tested or real: what research should learn from first."""
        from .accounting import evidence_cutoffs
        cutoffs = evidence_cutoffs(self.ledger, agent_id)
        rows = []
        for entry in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent_id):
            p = entry.payload
            if entry.seq <= cutoffs.get(p.get('book'), 0):
                continue
            pnl = p.get("pnl") if entry.kind == "book.settle" else p.get("realized")
            if pnl is None or p.get("source") == "dust":
                continue
            inst = p.get("instrument") or {}
            rows.append({"at": entry.at[:16], "what": inst.get("market_id") or inst.get("symbol"), "leg": inst.get("right"), "pnl_usd": str(pnl),
                         "result": p.get("result") or "sold", "real_money": bool(p.get("real_money")), "why": str(p.get("reason") or p.get("entry_reason") or "")[:160]})
        return rows[-limit:]

    # ----------------------------------------------------------------- economy
    def standing_of(self, agent_id: str) -> dict[str, Any]:
        """Current-rung results and earned evidence for purchasing research resources."""
        agent = self.registry.get(agent_id)
        row = self._standing(agent, float(self.game['economy']['epoch_seconds']))
        return {'rung': row.rung, 'active_blocks': row.active_blocks,
                'mean_growth': row.mean_growth, 'niche': agent.niche,
                'earned_observations': row.score_observations, 'earned_growth': row.score_growth,
                'earned_rung': row.score_rung, 'bunt_line': self.bunt_line(agent)}

    def bunt_line(self, agent: Agent) -> dict[str, Any] | None:
        """How far this agent's own evidence is from real money: its E, W_paper and closed trades as
        the allocator measured them at its last pass, against the constitution's bunt line. Read
        only -- nothing here moves a band, and the line is the constitution's, quoted, never set.
        None while the allocator is off.

        Sept 23, 2026: the best stock agent (scholes-21) was at E 0.9987 on 4 closed trades, $4.53
        short, and no stock or options agent could see that. rules.py states the line; this is the
        agent's own position against it."""
        if not allocator_module.enabled():
            return None
        r = allocator_module.rules()
        at, trades_needed = float(r["bunt_at"]), int(r["bunt_min_trades"])
        settled_needed = int(r.get("bunt_min_settled") or 0)
        weight = float((r.get("evidence") or {}).get("paper_weight", 0.5))
        board = self.allocator.board()
        row = (board.get("agents") or {}).get(agent.id) or {}
        ev = row.get("evidence")
        out: dict[str, Any] = {"band": row.get("band"), "bunt_at": at, "bunt_min_trades": trades_needed,
                               **({"bunt_min_settled": settled_needed} if agent.venue == "kalshi" else {})}
        if not ev:
            return {**out, "measured": False,
                    "note": "The allocator reads evidence from rung 1 (paper) on, at every mark pass; there is none for you yet."}
        e, w_paper, w_real = float(ev["E"]), float(ev["W_paper"]), float(ev["W_real"])
        trades, settled = int(ev.get("trades") or 0), int(ev.get("settled") or 0)
        short = max(0, trades_needed - trades)
        if agent.venue == "kalshi" and settled_needed:
            short = min(short, max(0, settled_needed - settled))
        # E = W_paper ** weight x W_real, so with the real record as it stands the line is this W_paper.
        needed = (at / w_real) ** (1.0 / weight) if weight > 0 and w_real > 0 else math.inf
        gain = max(0.0, needed / w_paper - 1.0) if w_paper > 0 else math.inf
        paper = self.books.get(PRACTICE_BOOK[agent.venue])
        equity = float(paper.equity(agent.id)) if paper is not None and agent.id in paper.accounts else None
        out.update(measured=True, measured_at=board.get("at"), E=e, W_paper=w_paper, W_real=w_real,
                   closed_trades=trades, **({"settled": settled} if agent.venue == "kalshi" else {}),
                   e_short=round(max(0.0, at - e), 6), trades_short=short,
                   w_paper_needed=round(needed, 6) if math.isfinite(needed) else None,
                   paper_gain_needed_pct=round(100 * gain, 4) if math.isfinite(gain) else None,
                   paper_gain_needed_usd=(round(gain * equity, 2) if equity is not None and math.isfinite(gain) else None),
                   at_the_line=bool(e >= at and short == 0),
                   note=("W_paper is after the practice haircut, and more trading pays more of it; the dollars are "
                         "the gain on your paper equity now that would put E on the line. Crossing it is judged by "
                         "the allocator at its next pass, as for everyone; nothing here changes the line."))
        if row.get("band") in ("probe", "bunt", "swing", "star"):
            # Already on real money: the line it now has to hold is the bunt line with hysteresis, once
            # `hysteresis_after_settled` independent real settlements are in this stay (P2, Sept 24, 2026:
            # before that only the stay drawdown sends it back).
            out.update(on_real_money=True, holds_real_money_down_to_E=round(at * float(r.get("hysteresis", 1.0)), 6),
                       exit_line_applies_after_real_settlements=int(r.get("hysteresis_after_settled") or 0),
                       real_settlements_this_stay=int(ev.get("stay_closed") or 0))
        return out

    def standings(self) -> list[Standing]:
        """Every living agent's standing. Inside a tick, on the tick's own thread, and inside a House-lane
        job on its thread (`_house_job`, H5), the table is built once and reused while the living roster
        is unchanged (a birth or a death rebuilds it); anywhere else it is built fresh."""
        epoch = float(self.game['economy']['epoch_seconds'])
        living = list(self.registry.living())
        memo = getattr(self, "_standings_memo", None)
        if memo is None or memo["thread"] != threading.get_ident():
            memo = getattr(self, "_lane_memos", {}).get(threading.get_ident())  # a House-lane job's own (H5)
        if memo is None:
            return [self._standing(agent, epoch) for agent in living]
        roster = tuple(a.id for a in living)
        if memo["living"] != roster or memo["rows"] is None:
            memo["rows"], memo["living"] = [self._standing(agent, epoch) for agent in living], roster
        return list(memo["rows"])

    def _standing(self, agent, epoch):
        rung = self.evaluator.rung(agent.id)
        entered = self.evaluator._rung_entered(agent.id)
        book = self.book_of(agent)
        if book is not None and not book.evidence_integrity(agent.id)['ok']:
            return Standing(agent.id, agent.niche, rung, 0.0, 0, working=False,
                            reward_growth=0.0, reward_observations=0, reward_rung=rung)
        rows = self.evaluator.blocks(agent.id, since_seq=entered, book=book.name) if rung >= 1 and book else []
        growth = [float(r["log_growth"]) for r in rows]
        active = sum(1 for r in rows if r.get("active"))
        reward_rows, reward_rung = list(rows), rung
        reward_since = entered
        if rung >= 3:
            reward_rows = self.evaluator._record_below(agent.id, 3) + reward_rows
            changes = [e for e in self.ledger.iter(kinds='eval.verdict', agent=agent.id)
                       if e.seq < entered and e.payload.get('decision') in ('seat', 'promote', 'demote')
                       and e.payload.get('to_rung') == 2]
            if changes:
                reward_since = changes[-1].seq
        reward = self._reward_evidence(agent, book, reward_rows, reward_since) if book else (0.0, 0)
        minimum = int(self.game['economy'].get('performance_min_blocks', 0))
        if (rung == 2 and reward[1] < max(minimum, 1) and sum(growth) >= 0
                and book and book.equity(agent.id) >= book.account(agent.id).staked):
            # Admission must not erase the evidence that earned the research allocation.
            # Paper evidence retains PAPER weight until a real record earns the live weight.
            prior = self.evaluator._record_below(agent.id, 2)
            changes = [e for e in self.ledger.iter(kinds='eval.verdict', agent=agent.id)
                       if e.seq < entered and e.payload.get('decision') in ('seat', 'promote', 'demote')
                       and e.payload.get('to_rung') == 1]
            paper = self.books.get(PRACTICE_BOOK[agent.venue])
            old = self._reward_evidence(agent, paper, prior, changes[-1].seq if changes else 0,
                                        until=entered) if paper else (0.0, 0)
            if old[0] > 0 and old[1] >= minimum:
                reward, reward_rung = old, 1
        return Standing(agent.id, agent.niche, rung, (sum(growth) / len(growth)) if growth else 0.0, active,
                            working=self._working(agent, epoch), reward_growth=reward[0],
                            reward_observations=reward[1], reward_rung=reward_rung)

    def _reward_evidence(self, agent, book, rows, since, *, until=None):
        if not book.evidence_integrity(agent.id)['ok']:
            return 0.0, 0
        growth = [float(r['log_growth']) for r in rows]
        # A daily block is worth as many observations as the constitution's own screen says: it
        # asks 15 hourly or 5 daily blocks, so a day counts three. Counted one for one, a daily desk
        # up 1.4% on two days lost the whole performance share to an hourly one up 0.15% on thirty
        # (Sept 21, 2026), and needed five days to be ranked at all.
        paper = CONSTITUTION['ladder']['paper']
        per_day = max(1, int(paper['min_active_blocks']) // int(paper.get('min_active_blocks_day', paper['min_active_blocks'])))
        active = sum((per_day if r.get('horizon', agent.horizon) == 'day' else 1) for r in rows if r.get('active'))
        # A day's return is not compared with an hour's return as though their clocks matched.
        hours = sum(24 if r.get('horizon', agent.horizon) == 'day' else 1 for r in rows)
        rate = sum(growth) / hours if hours else 0.0
        if active > 0 and active >= int(self.game['economy'].get('performance_min_blocks', 0)):
            return rate, active
        from .episodes import completed
        episodes = completed(self.ledger, agent.id, book.name, since_seq=since, until_seq=until)
        if len(episodes) >= int(CONSTITUTION['ladder']['completed_exposures']['min_episodes']):
            hours = (_epoch(episodes[-1]['closed_at']) - _epoch(episodes[0]['opened_at'])) / 3600
            if hours > 0:
                rate = sum(r['log_growth'] for r in episodes) / hours
                if until is None and book.equity(agent.id) < book.account(agent.id).staked:
                    rate = min(rate, 0.0)  # realized winners cannot buy a reward while marked underwater
                return rate, len(episodes)
        return rate, active

    def _working(self, agent: Agent, epoch: float) -> bool:
        """Has it traded in the last epoch, or is it too new to have had the chance? An agent that
        has done neither earns no niche floor and spends down what it has: idleness must cost.

        Idleness, though, not the calendar. An equity desk is shut from Friday evening until Monday
        morning, and an agent that would be trading if it could must not be starved to death over a
        weekend for a market it does not control: its floor pays for the research that is the only
        work the weekend has. Doing nothing in a market that IS open still costs, as it should."""
        if self.clock() - _epoch(agent.born_at) < epoch:
            return True
        book = self.book_of(agent)
        if book is not None and book.open_orders(agent.id):
            return True  # an order resting at the venue is work, even before it fills
        since = now_iso(lambda: self.clock() - epoch)
        if any(e.at >= since for e in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent.id)):
            return True
        idle = self.idle_run(agent)
        return bool(idle["shut"]) and not idle["barren"] and not idle["offered"]

    def keep_population(self, *, refill: bool = True, clock: bool = True) -> None:
        rules = self.game["economy"]
        deadline = float(rules.get("replay_deadline_epochs", 3)) * float(rules["epoch_seconds"])
        broke = Decimal(str((self.game.get("research") or {}).get("min_credits_usd", "0.10"))) * 2
        stuck = int(rules.get("idle_broke_wakes", 30))
        for agent in self.registry.living():
            if not self.economy.alive(agent.id):
                self.kill(agent, "credits", "its compute credits reached zero")
            elif clock and self.evaluator.rung(agent.id) == 0 and self.clock() - _epoch(agent.born_at) > deadline:
                self.kill(agent, "never qualified", f"it did not pass replay within {rules.get('replay_deadline_epochs', 3)} epochs of its birth")
            elif clock and self.idle_run(agent)["barren"] >= stuck and self.economy.balance(agent.id) <= broke:
                # Neither able to trade nor able to buy a new idea: it cannot change and it cannot
                # act, and it will sit at this balance for as long as the floor runs, holding a
                # seat on its desk that a newcomer could use. A shut market does not count here --
                # that is the calendar, not the agent.
                self.kill(agent, "stuck", f"{self.idle_run(agent)['barren']} wakes in a row with a live market in front of it and nothing done, "
                                          f"and too few credits left to research its way out")
        # R2 (Sept 24, 2026): the caps follow the search and the population follows Sail's runway before any seat is
        # given, by the House or by the lab's step and the foundry, which read the same caps. They spend nothing.
        try:
            self._follow_the_search()
        except Exception as exc:  # noqa: BLE001 - the caps stand as they are until the next tick
            self.alert("warning", f"the seat market's caps could not follow the search ({type(exc).__name__}: {str(exc)[:160]})")
        try:
            self._population_rule()  # apart: a search that cannot be read must not skip Sail's runway (review of #276)
        except Exception as exc:  # noqa: BLE001 - the ceiling stands until the next tick
            self.alert("warning", f"the population rule could not be applied ({type(exc).__name__}: {str(exc)[:160]})")
        if not refill or self._closing.is_set():
            return  # births buy sandbox work; culling above remains available after spending stops
        roster = self._roster()
        if not self._births_due(roster):
            return  # H5: nothing was born and nothing died since a pass that is under five minutes old
        # H5: the foundry's step runs beside the tick now, and it labels births (`annotate_births`) and moves its
        # cards; a pass of births beside it could write a birth's route under the id it is labelling. So the two
        # take turns (`_foundry_turn`): the tick waits for it at most `box_wait_seconds`, then leaves the pass due.
        if not self._foundry_turn.acquire(timeout=float(self.settings.box_wait_seconds)):
            return
        try:
            # Every birth reads its strategy's NEEDS in the probe box. The tick holds that box for the
            # whole phase (each probe reenters it), or, when background work has it, births wait for
            # the next tick with the reason recorded. A Sail call that fails is deferred the same way.
            with self._probe_turn("births") as free:
                if free:
                    # The roster the pass began on: a birth or death it makes itself asks for the next tick's pass,
                    # as a pass that seats someone is often followed by another (three merged strategies a tick).
                    # A pass deferred for the probe box or Sail is not a pass: the next tick tries again.
                    self._scan_memo = {"thread": threading.get_ident(), "roster": None, "scans": {}}
                    try:
                        self._births(rules)
                        self._births_pass = (self.clock(), roster)
                    except SandboxError as exc:
                        self._defer("births", f"infrastructure: {type(exc).__name__}: {str(exc)[:200]}")
                    finally:
                        self._scan_memo = None
        finally:
            self._foundry_turn.release()

    def _roster(self) -> tuple[int, int]:
        """(agents ever born, agents that died): it moves at every birth and every death, whichever thread made it."""
        with self.registry._lock:
            agents = list(self.registry.agents.values())
        return len(agents), sum(1 for agent in agents if not agent.alive)

    def _births_due(self, roster: tuple[int, int]) -> bool:
        """H5 (Sept 25, 2026): is the births pass due -- none yet in this process, the last one
        `population_pass_seconds` (300) old, or a birth or a death since it began (the House's own, the
        lab's, a research admission's, a displacement's)?

        The pass is the seat market: the proven families' births, forks, merged strategies and the refill,
        which reads the waiters and asks the displacement scan for every candidate. With the league at its
        ceiling and no resident displaceable it seats nobody, and it cost the tick 22.0 s at p50 (15.4-17.6 s
        on the T0 snapshot here, 17.1 s of it the scan asked once for each of 395 deferred research
        candidates) on every tick. Nothing it reads changes between passes but the clock -- a grace that runs
        out, a waiter that arrives, a card that passes replay -- and those now wait at most five minutes,
        inside the refill's own ten-minute newcomer cadence. A freed seat is looked at on the next tick."""
        last = self._births_pass
        if last is None or last[1] != roster:
            return True
        return self.clock() - last[0] >= float(self.settings.population_pass_seconds)

    def _births(self, rules: Mapping[str, Any]) -> None:
        """A proven family's program first (R3, `_proven_births`), then forks of rich agents, the founders below the
        floor, merged strategies, then the refill."""
        self._proven_births(rules)
        for agent in self.registry.living():
            if self.economy.can_fork(agent.id) and self.evaluator.rung(agent.id) >= 1:
                last = float(self._state.setdefault("last_fork", {}).get(agent.id) or 0)
                if self.clock() - last >= float(rules["epoch_seconds"]):
                    self._state["last_fork"][agent.id] = self.clock()
                    if self._holdout_spent(agent):
                        continue  # its child could pass no replay: asked again next epoch
                    try:
                        child = self.fork(agent)
                    except SandboxError:
                        self._state["last_fork"][agent.id] = last  # not its fault: asked again next tick
                        raise
                    if child is not None:
                        # The first burst payout launched seven children serially, holding one
                        # tick for over seven minutes. Give the next parent its turn on the next
                        # tick; the persisted per-parent cadence survives restart.
                        return
        if len(self.registry.living()) < int(rules["min_population"]):
            self.found()
        self.enroll()
        self._refill(rules)

    def _seal_applies(self, agent: Agent) -> bool:
        """Is this agent's line judged by the sealed holdout: are its forks and new versions replayed
        on the history store's development window (an Alpaca strategy, not an option, reading no
        live-only feed)? Then its lineage's holdout ration is what lets it grow (`_holdout_spent`),
        and the Alpha Lab leaves that ration a reserve (league/lab.py)."""
        needs = agent.needs or {}
        venue, _, _ = niche_of(needs)
        return venue == "alpaca" and bool(self.settings.deep_replay) and str(needs.get("asset_class") or "") != "option" \
            and not self._feeds_wanted(needs)

    def _holdout_spent(self, agent: Agent) -> bool:
        """Would a plain mutation of this agent be refused the sealed holdout? It shares the parent's
        lineage, and a lineage that has spent `holdout_lineage_budget` evaluations passes no further
        development replay: the child dies `redundant` minutes after its birth. Measured Sept 23,
        2026, 03:58-04:25Z: the revived crypto lines forked eight such children in half an hour."""
        if not self._seal_applies(agent):
            return False
        from . import deep_replay

        lineage = self.registry.lineage(agent.id)
        seal = deep_replay.HoldoutSeal(self.ledger, budget=self.settings.holdout_lineage_budget, window=self.holdout_window)
        return seal.used(lineage[-1] if lineage else agent.id) >= seal.budget

    def _refill(self, rules: Mapping[str, Any]) -> Agent | None:
        """Keep a seat filled. A death that leaves an empty seat is only useful if something new
        sits in it: before this the House staked a newcomer only below the population FLOOR, so a
        failure shrank the league from 28 towards 12 instead of cycling it. Now it fills up to the
        ceiling, one at a time, and puts the newcomer on the desk that is furthest from full, so
        exploration spreads across the firm instead of converging on whoever is winning."""
        # Replay-passing candidates precede random mutations at the same newcomer cadence.
        # The ledger queue survives a research pass finishing and the House restarting.
        state = self._state.setdefault('last_newcomer', {})
        last = float(state.get('at') or state.get('since') or self._born_at)
        if self.clock() - self._born_at >= 300 and self.clock() - last >= float(rules['newcomer_seconds']):
            self.seat_waiters()  # R2: a retained candidate whose desk the search has closed leaves the queue first
            with self._lifecycle_lock:
                rows = Admissions(self.ledger).rows()
                # S3 (Sept 24, 2026): the retained candidates of dead authors first, oldest death first; they
                # rank with the lab's graduates, and a living author can research again, a dead one cannot.
                self._adopt_orphans(rows)
                for entry in self._retained_waiting(expired=True):
                    child = self._admit_orphan(entry, rules, rows)
                    if child is not None:
                        state['at'] = self.clock()
                        return child
                left = self._retained_waiting()
                if left:
                    self._refuse_birth("retained", len(left), "none could be seated: their desks are full of residents that may "
                                                              "not be displaced, even by a newcomer with forward evidence")
                for row in [r for r in rows if r.get('status') in ('queued', 'deferred', 'admitting') and r.get('_candidate')]:
                    if row['session'] in (self._state.get('retained') or {}):
                        # Handed to the seat queue in this very pass: an admission above displaced its author, whose
                        # row this fold still reads as pending. Cancelled as its dead author's, it was lost (review of #245).
                        continue
                    child = self._admit_candidate(row, displace=True)
                    if child is not None:
                        state['at'] = self.clock()
                        return child
        living = self.registry.living()
        if not living:
            return None
        if self.clock() - self._born_at < 300:
            return None  # this process has just started: settle first, as `due()` does with wakes
        full = len(living) >= int(rules["max_population"])
        urgent = len(living) < int(rules["min_population"])
        every = float(rules["newcomer_seconds"]) / (4 if urgent else 1)
        # The wait is since the last newcomer, or since the floor first ran -- NOT since this
        # process started. Measured Sept 20, 2026: the interval was anchored on `_born_at`, which
        # moves on every restart, and a floor that deploys itself restarts every half hour. In six
        # hours the hour never once elapsed, `last_newcomer` was never written, and the league sat
        # at its founding size with seven seats empty. A floor that rewrites itself deploys often
        # by design, so anything paced longer than a deploy must survive one.
        state = self._state.setdefault("last_newcomer", {})
        last = float(state.get("at") or state.get("since") or self._born_at)
        waiters = self.seat_waiters()
        self._seat_market_watch()  # hourly: what the market looks like, and who cannot be seated
        if any(waiters.values()):
            # Sept 23, 2026: the seat market follows evidence. While an Alpha Lab graduate, a
            # replay-passed card or a merged strategy waits for a seat, no House mutation is staked:
            # every freed seat is theirs, in that order (`SEAT_WAITERS`). Graduates are born by the
            # lab's own step and merged strategies by `enroll`; the cards are born here, at the
            # newcomer cadence, on any desk no graduate waits for. Measured at 16:28Z: House
            # mutations took 36 of the last 111 births while 32 evidenced newcomers waited.
            if waiters["cards"] and self.hypotheses is not None and self.hypotheses.enabled() and self.clock() - last >= every:
                reserved = self._reserved_desks(waiters, below="cards")
                loser = self._weakest(rules, evidenced=True, exclude=self._keep_for(reserved)) if full else None
                # A full league with nobody to displace seats no card: the foundry would otherwise
                # put one on a desk with room and overfill the league by one. No card is admitted onto a desk
                # the search has closed (R2): the foundry's admission skips it as it skips a reserved desk.
                closed = set(self._search_closed_desks())
                child = None if full and loser is None else \
                    self.hypotheses.refill(rules, living=living, loser=loser, mutations=False, reserved=reserved | closed)
                if child is None:
                    self._refuse_birth("cards", len(waiters["cards"]),
                                       "none could be seated: its desk is full of residents that may not be displaced, "
                                       "even by a newcomer with forward evidence, or is held for a waiting graduate")
                return child
            return None
        if self.clock() - last < every:
            return None
        loser = None
        if full:
            # A ceiling with nothing dying under it is a floor that has stopped searching. Measured
            # Sept 20, 2026: thirty-three agents born in twelve hours and NOT ONE dead, four births
            # from a league that could never try anything again. So the last seat is a tournament:
            # a newcomer takes it from the worst agent that has had its chance, which is the
            # selection pressure the ceiling was meant to create and never did. Never a desk's last
            # trading member (Sept 23, 2026): a replay-only child must not leave a desk with nobody
            # who can place an order.
            loser = self._weakest(rules, exclude=self._last_traders(living))
            if loser is None:
                return None
            # Do not retire a resident until the cadence is due and a valid replacement exists.
            living = [a for a in living if a.id != loser.id]
        if self.hypotheses is not None and self.hypotheses.replaces_refill():
            # Hypotheses, not blind mutations (league/hypotheses.py): a replay-passing card, or a
            # mutation of a parent that is earning forward, never a draw placed by open seats. Never a card
            # onto a desk the search has closed (R2): its card left the queue, and the foundry's admission
            # would otherwise seat it here, where no one waits any more.
            return self.hypotheses.refill(rules, living=living, loser=loser, reserved=set(self._search_closed_desks()))
        seats = self._mutation_room(living)
        here = [a for a in living if a.specialty in seats or (a.specialty is None and not self.settings.specialists)]
        with self._state_lock:
            self._state["last_newcomer"]["at"] = self.clock()
        child_params = None
        # Births follow evidence. A desk where some agent is making money is bred first, from that
        # agent, before the emptiest desk; only then does exploration spread by open seats. Ranked
        # by open seats, rung and purse alone, the Sept 21, 2026 floor bred hilibrand-2 (losing, but
        # rich on least-bad payouts) and the never-trading options desk while the weather desk,
        # the one where every agent was up, waited its turn.
        standing = {s.agent: s for s in self.standings()}

        def earning(agent):
            row = standing.get(agent.id)
            return bool(row is not None and row.score_growth > 0 and row.score_observations > 0)

        paying = {a.specialty for a in here if earning(a)}
        lines = self.line_trials()
        exhaust = int(rules.get("line_exhausted_trials", 15))

        def line_of(agent):
            return lines.get(agent.line or agent.name) or (0, 0)

        def exhausted(agent):
            tried, passed = line_of(agent)
            return passed == 0 and tried >= exhaust and not earning(agent)

        def desk_pass_rate(agent):
            rows = [line_of(a) for a in here if a.specialty == agent.specialty]
            tried = sum(t for t, _ in rows)
            return (sum(p for _, p in rows) + 1) / (tried + 2)  # a desk with no trials starts at one half

        # Births follow evidence first: an earning desk, then a line that is not exhausted, then the
        # desk's replay pass rate, and only then open seats. Measured Sept 21-22, 2026: seats-first
        # sent 66% of 210 births to six desks that had never produced a live agent, from lines that
        # already held a median of 15 failed trials. One birth in `explore_every` still goes by open
        # seats alone, so an unexplored desk keeps a bounded share of the search.
        explore = int(rules.get("explore_every", 5))
        exploring = explore > 0 and len(self.registry.agents) % explore == 0
        order = (lambda a: (not exhausted(a), seats.get(a.specialty, 0), earning(a), self.evaluator.rung(a.id))) if exploring else \
                (lambda a: (a.specialty in paying, not exhausted(a), desk_pass_rate(a), earning(a), seats.get(a.specialty, 0),
                            self.evaluator.rung(a.id), self.economy.balance(a.id)))
        for agent in here:
            if exhausted(agent):
                self._retire_line(agent, *line_of(agent))
        for best in sorted(here, key=order, reverse=True):
            if exhausted(best) or self._losing_family(best.family):
                continue
            child_params = self._mutated_params(best, seed=f"newcomer:{len(self.registry.agents)}")
            if child_params is not None:
                break
        if child_params is None:
            return None
        if loser is not None:
            self.kill(loser, "displaced", self.postmortem(loser, "displaced",
                "the league was full and a valid newcomer replaces its weakest eligible agent"))
        tried, passed = line_of(best)
        why = ("exploration: open desks with more room were tried first" if exploring else
               f"evidence: earning desks, live lines and the desk's replay pass rate ({desk_pass_rate(best):.0%}) before open seats")
        child = self.spawn(best.line or best.name, best.family, best.code, parent=best.id, endowment=rules["endowment_usd"],
                           params=child_params,
                           reason=f"a House-staked valid mutation of {best.id} by {why}; its line has {passed} passes in {tried} trials; "
                                  f"the league was {len(living)} of {rules['max_population']}")
        self.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["endowment_usd"], "box_forked": False,
                                            "reason": "population", "new_code": False}, agent=best.id)
        return child

    def line_trials(self) -> dict[str, tuple[int, int]]:
        """Replay trials and passes per line (`Agent.line`, else its name), cached for five minutes."""
        def build():
            line = {a.id: (a.line or a.name) for a in self.registry.agents.values()}
            out: dict[str, list[int]] = {}
            for entry in self.ledger.iter(kinds="eval.trial"):
                row = out.setdefault(line.get(entry.agent, entry.agent), [0, 0])
                row[0] += 1
                row[1] += bool(entry.payload.get("passed"))
            return {key: (tried, passed) for key, (tried, passed) in out.items()}
        hit = self._data_cache.get("line_trials")
        if hit and self.clock() - hit[0] < 300:
            return hit[1]
        value = build()
        self._data_cache["line_trials"] = (self.clock(), value)
        return value

    def _retire_line(self, agent: Agent, tried: int, passed: int) -> None:
        """Say once that a line is no longer bred. Its living agents keep their seats and records;
        only House-staked mutations stop. It is a heuristic starting point, not a statistical law."""
        line = agent.line or agent.name
        with self._state_lock:
            told = self._state.setdefault("retired_lines", {})
            if line in told:
                return
            told[line] = tried
        self.ledger.append("hypothesis.retired", {"id": f"line:{line}", "reason": "disproven", "failures": tried - passed,
                                                  "evidence": f"{tried} replay trials and {passed} passes; House mutations stop"},
                           id=f"line-retired:{line}:{tried}")

    # -------------------------------------------------------------------- tick
    #: A Sail hold older than this has had its charge (if any) reach the balance meter.
    STALE_HOLD_SECONDS = 3600
    #: An OpenAI hold older than this belongs to a call that ended long before (the House reads for
    #: 600 s, the gateway waits 570 s), and the gateway's month already counts it (Sept 24, 2026).
    STALE_OPENAI_HOLD_SECONDS = 6 * 3600

    def _absorb_stale_holds(self, *, sail: bool = True) -> None:
        """Every ten minutes, release each metered provider's holds older than its meter's lag into
        the meter that already counts their charge (`CampaignBudget.absorb_stale`), and say so on
        the ledger: Sail's once its balance was read this tick (`sail`), OpenAI's against the
        gateway's frontier month, which the tick reads first (Sept 24, 2026). A try that had nothing
        yet to check the month against (`retry`) is made again on the next tick, not in ten minutes."""
        absorb = getattr(self.campaigns, "absorb_stale", None)
        required = (getattr(self.campaigns, "policy", {}) or {}).get("meter_required", [])
        if absorb is None:
            return
        for kind, age, key, read in (("sail", self.STALE_HOLD_SECONDS, "holds_absorbed_at", sail),
                                     ("openai", self.STALE_OPENAI_HOLD_SECONDS, "openai_holds_absorbed_at", True)):
            if kind not in required or not read or self.clock() - float(self._state.get(key) or 0) < 600:
                continue
            self._state[key] = self.clock()
            try:
                out = absorb(kind, older_than_seconds=age, evidence={"by": "house", "release": Path(__file__).resolve().parents[1].name})
            except Exception as exc:  # noqa: BLE001 - a reconciliation that fails leaves the holds counted
                self.alert("warning", f"stale {'Sail' if kind == 'sail' else 'OpenAI'} holds could not be absorbed "
                                      f"({type(exc).__name__}: {str(exc)[:160]})")
                continue
            if out.get("retry"):
                self._state[key] = 0
            if out.get("absorbed"):
                self.ledger.append("ops.budget", {"what": "holds absorbed", "kind": kind, **out})
            self._watch_absorb(kind, out)

    #: A release that keeps being refused this long is said once (Sept 24, 2026: the first check of
    #: the OpenAI release compared a moving House figure with a reading a tick old and refused every
    #: try for as long as research ran; nothing on the ledger or in health said so).
    ABSORB_STALL_SECONDS = 1800

    def _watch_absorb(self, kind: str, out: Mapping[str, Any]) -> None:
        """The invariant on the release of stale holds: while every try comes back with a reason and
        nothing released, since when is kept in the House's state, and past `ABSORB_STALL_SECONDS` one
        warning says why, with the check's numbers; a release, or a try with nothing to release,
        clears it (and an info alert says so if the warning went out)."""
        key = f"absorb_stalled:{kind}"
        stalled = self._state.setdefault("absorb_stalled", {})
        if out.get("absorbed") or not out.get("why"):
            row = stalled.pop(kind, None)
            if row and row.get("told"):
                self.alert("info", f"stale {'Sail' if kind == 'sail' else 'OpenAI'} holds are being released again")
            return
        row = stalled.setdefault(kind, {"since": self.clock(), "told": False})
        row["why"] = str(out.get("why"))[:200]
        if not row["told"] and self.clock() - float(row["since"]) >= self.ABSORB_STALL_SECONDS:
            row["told"] = True
            minutes = (self.clock() - float(row["since"])) / 60
            self.alert("warning", f"stale {'Sail' if kind == 'sail' else 'OpenAI'} holds have not been released for {minutes:.0f} minutes: "
                                  f"{row['why']}", check=dict(out.get("check") or {}), key=key)

    def _cadence_due(self, step: str, seconds: float) -> bool:
        """H5 (Sept 25, 2026): is a step the tick keeps at its own cadence due (`_cadence`, stamped by the caller
        when it runs)? The tick runs every `tick_seconds` (30) for the wakes; these keep the cadence they had."""
        return self.clock() - self._cadence.get(step, float("-inf")) >= float(seconds)

    def _house_job(self, work: Callable[..., Any], *args: Any) -> Any:
        """One of the tick's own steps on the House lane (`_background`, "house:"), with a standings table of
        its own for the run (`standings`), as the tick has: the foundry asks the displacement scan of every desk."""
        ident = threading.get_ident()
        self._lane_memos[ident] = {"thread": ident, "living": None, "rows": None}
        try:
            return work(*args)
        finally:
            self._lane_memos.pop(ident, None)

    def _schedule_research(self, open_for_business: bool) -> int:
        """Queue a research job for every agent whose pass is due (`research_due`), stuck and longest-waiting first
        (`research_order`); a dead agent's saved session is closed first. Runs on the House lane once a minute
        (H5, Sept 25, 2026), as it ran once a tick while ticks were a minute apart: `research_due` and
        `queue_research` were already asked from the research workers' threads (`_research_if_due`), and a
        worker asks `research_due` again before it spends anything. Returns the jobs queued."""
        self._cancel_retired_research()
        queued = 0
        for agent in self.research_order() if open_for_business else []:
            if self._closing.is_set():
                break
            if self.research_due(agent):
                # Persist before dispatch, so queued work also survives process exit.
                queued += bool(self.queue_research(agent))
        return queued

    def _foundry_step(self, open_for_business: bool) -> None:
        """The hypothesis foundry's step (`Foundry.tick`: its bookkeeping, and a paid call when its own gates allow),
        never beside a births pass (`_foundry_turn`, `keep_population`)."""
        if self.hypotheses is not None:
            with self._foundry_turn:
                self.hypotheses.tick(open_for_business=open_for_business)

    def tick(self) -> dict[str, Any]:
        """One pass of the floor. It never waits on a box background work holds: a wake whose box
        is busy is retried on the next tick, and births wait for the probe box at most
        `probe_wait_seconds` (`_births`). What it put off is in health.json's `deferred`, and what
        each of its steps took in `tick_steps`."""
        # One standings table a tick (Sept 23, 2026): displacement, the refill and the foundry each
        # ranked every living agent afresh, several ledger scans an agent each time, and a profile of the
        # production tick found about 80% of its main thread there (191 s ticks at 10:53Z).
        self._standings_memo = {"thread": threading.get_ident(), "living": None, "rows": None}
        self._laps = _TickLaps()
        try:
            with self._box_patience():
                return self._tick()
        finally:
            self._standings_memo = None
            self._laps = None

    #: health.json `tick_steps`: the ticks kept for `slowest_hour` (at most, whatever their age) and
    #: how many of its steps it lists.
    TICK_STEPS_KEPT = 240
    TICK_STEPS_SLOWEST = 8

    def _lap(self, step: str) -> None:
        """The time since the tick's previous lap is `step`'s (`_TickLaps`); nothing outside a tick."""
        laps = self._laps
        if laps is not None:
            laps.lap(step)

    def _tick_steps(self, at: str) -> dict[str, Any]:
        """health.json `tick_steps` (Sept 24, 2026). Written last in a tick's health, which ends the
        tick's laps: `last` (the tick's `at`, `total_seconds` and each step's seconds, `health`, the
        health block itself, included), `slowest_hour` (each step's slowest in the ticks of the last
        hour on the House's clock, slowest first, with that tick's `at`), `ticks_in_hour`, and
        `background` (each lane's last job: its key, state, seconds and when it ended; beside the tick,
        never in its time). Measured on the box, Sept 24, 2026 08:40-08:50Z: ticks of 51-64 s landing
        70-80 s apart, and nothing that said which step cost what."""
        laps, self._laps = self._laps, None
        now = self.clock()
        if laps is not None:
            laps.lap("health")
            steps = {step: round(seconds, 3) for step, seconds in laps.seconds.items()}
            self._tick_last = {"at": at, "total_seconds": round(laps.last - laps.began, 3), "steps": steps}
            self._tick_hour.append((now, at, steps))
        while self._tick_hour and now - self._tick_hour[0][0] > 3600:
            self._tick_hour.popleft()
        slowest: dict[str, tuple[float, str]] = {}
        for _, stamp, steps in self._tick_hour:
            for step, seconds in steps.items():
                if seconds > slowest.get(step, (-1.0, ""))[0]:
                    slowest[step] = (seconds, stamp)
        with self._state_lock:
            background = {lane: dict(row) for lane, row in sorted(self._lane_last.items())}
        return {"last": self._tick_last, "ticks_in_hour": len(self._tick_hour),
                "slowest_hour": [{"step": step, "seconds": seconds, "at": stamp} for step, (seconds, stamp)
                                 in sorted(slowest.items(), key=lambda kv: (-kv[1][0], kv[0]))[:self.TICK_STEPS_SLOWEST]],
                "background": background}

    def _tick(self) -> dict[str, Any]:
        lap = self._lap
        if self._burst and not self.campaigns.running():
            self.game = deepcopy(self._base_game)
            self.economy.game, self.economy.rules = self.game, self.game['economy']
            if self.researcher is not None:
                self.researcher.settings = dict(self.game['research'])
                self.researcher.rules = rules_text(self.game)
            self.ledger.append('ops.budget', {'what': 'burst-ended', 'id': self._burst['id'],
                'reason': 'timed research settings restored; new paid work is closed'}, id='burst-ended:'+self._burst['id'])
            self._burst = None
        summary: dict[str, Any] = {"at": now_iso(self.clock), "woke": [], "orders": 0, "deaths": [], "reconciled": {}}
        self._replay_rules_changed()
        lap("replay_rules")
        if self.options_history is not None and self.settings.options_replay:
            today, hour = _new_york(self.clock)
            # Once a day after the session's bars are final; a failed run is tried again hourly.
            if (hour >= 17.0 and self._state.get("options_history_day") != today
                    and self.clock() - float(self._state.get("options_history_tried") or 0) >= 3600
                    and self._background("ops:options-history", self._refresh_options_history)):
                self._state["options_history_tried"] = self.clock()
        if self.feeds is not None:
            # Public, keyless data that costs nothing: recorded while the House is paused too, on the
            # feeds lane (`_background`), and the tool requests it answers are closed hourly once it has.
            if self.feeds.due():
                self._background("feeds:record", self.feeds.run)
            if (self.feeds.shipped() and self.clock() - self._feed_requests_at >= 3600
                    and self._background("feeds:requests", self._fulfil_feed_requests)):
                self._feed_requests_at = self.clock()
        living_before = {a.id for a in self.registry.living()}
        lap("feeds")
        for name, book in self.books.items():
            advance = getattr(book.broker, "advance", None)
            # H5 (Sept 25, 2026): a simulated venue (kalshi-shadow, a canary's) is passed at its fill model's cadence,
            # never every tick (`Settings.simulated_poll_seconds`); its step was 5.5 s at p50 on the box (45 held
            # instruments asked for a result, 13 resting orders re-quoted, one venue call each). A real venue keeps its
            # minute too (`venue_poll_seconds`, the review of #297): its calls, its exits' re-sends and the arithmetic of
            # a failing venue's warnings stay as they were. The mark pass polls every book on its own, every five minutes.
            every = self.settings.simulated_poll_seconds if advance is not None else self.settings.venue_poll_seconds
            if not self._cadence_due(f"poll:{name}", every):
                lap(f"poll:{name}")
                continue
            self._cadence[f"poll:{name}"] = self.clock()
            try:
                if advance and book.open_orders():  # nothing working: nothing to re-quote (H5)
                    advance()
                book.poll()
                settlements = getattr(book.broker, "settlements", None)
                if settlements:
                    for row in settlements(self._state["settled"].get(name)):
                        if row.get("result") in ("yes", "no"):
                            book.settle(str(row["ticker"]), str(row["result"]))
                            stamp = str(row.get("settled_time") or "")
                            if stamp > str(self._state["settled"].get(name) or ""):
                                self._state["settled"][name] = stamp
            except Exception as exc:  # noqa: BLE001 - one venue's outage must not stop the others
                self.alert("warning", f"{name}: could not poll or settle ({type(exc).__name__}: {str(exc)[:200]})", **environment("gateway", exc))
            lap(f"poll:{name}")
        try:
            self._cancel_stale_resting()
        except Exception as exc:  # noqa: BLE001 - a guard that fails this tick runs again on the next
            self.alert("warning", f"stale resting orders could not be checked ({type(exc).__name__}: {str(exc)[:160]})")
        lap("cancel_stale")
        try:
            self._order_path_invariants()  # code over house.json and the ledger's new refusals; runs while paused too
        except Exception as exc:  # noqa: BLE001 - a check that fails this tick runs again on the next
            self.alert("warning", f"the order path's invariants could not be checked ({type(exc).__name__}: {str(exc)[:160]})")
        lap("order_path_invariants")
        # Past the monthly compute line only agents holding real money are woken, so they can exit.
        open_for_business = self.budget is None or self.budget.check() == "open"
        stopped_because = "" if open_for_business else f"the Sail meter's monthly line or reserve (league/budget.py mode {getattr(self.budget, 'mode', '?')})"
        if self.campaigns:
            meter = getattr(self.provider, "transport", None)
            metered = bool(meter and hasattr(meter, "refresh") and meter.refresh())
            # OpenAI's meter is the gateway's frontier month (`FrontierMonth`, fed to the campaign):
            # read here on every tick, at most once a minute, so it is fresh for every OpenAI
            # reservation, and an unreadable gateway stops only paid OpenAI work (Sept 24, 2026).
            # The tier reads it (`frontier_remaining`) and says so when it goes unread.
            try:
                self.frontier_tier()
            except Exception as exc:  # noqa: BLE001 - an unread month is an unread meter, never a failed tick
                self.alert("warning", f"the gateway's frontier month could not be read ({type(exc).__name__}: {str(exc)[:160]})",
                           **environment("gateway", exc))
            lap("meter")
            self._absorb_stale_holds(sail=metered)
            lap("hold_absorb")
            allowed = self.pacer.may_spend("sail")
            if open_for_business and not metered:
                stopped_because = "the campaign's Sail meter is unread or failed (meter_health in campaigns.sqlite)"
            elif open_for_business and not allowed:
                stopped_because = "the campaign's Sail allowance is closed"
            open_for_business = open_for_business and metered and allowed
        pause = self.paused()
        if pause:
            open_for_business = False
            summary["paused"] = pause["reason"]
            stopped_because = f"maintenance pause: {pause['reason']}"
        summary["budget"] = "open" if open_for_business else "stopped"
        if stopped_because:
            summary["stopped_because"] = stopped_because
        self._note_stopped(stopped_because)
        batches: dict[str, list[Mapping[str, Any]]] = {}
        waking = [a for a in self.due() if self.economy.alive(a.id)
                  and (open_for_business or self._holds_real_money(a) or (pause and self._holds_position(a)))]
        lap("due")
        # Each wake is mostly waiting on the agent's box, so they run side by side; every agent
        # has its own box and its own lock, and the ledger and the books are thread-safe.
        with ThreadPoolExecutor(max_workers=max(1, min(self.settings.wake_workers, len(waking) or 1))) as pool:
            outcomes = list(pool.map(self._wake_safely, waking))
        for agent, outcome in zip(waking, outcomes):
            summary["woke"].append(agent.id)
            if outcome.get("intents"):
                batches.setdefault(outcome["book"], []).append(outcome)
        lap("wakes")
        for name, wakes in batches.items():
            submitted = self._submit_wakes(name, wakes)
            summary["orders"] += sum(1 for o in submitted if o.status not in ("refused", "duplicate"))
            lap(f"submit:{name}")
        try:
            self._release_wind_downs()  # a dead agent's stock or option, held for the open, sells at the bell
        except Exception as exc:  # noqa: BLE001 - the mark pass retries every held sale within minutes
            self.alert("warning", f"held wind-downs could not be released ({type(exc).__name__}: {str(exc)[:160]})")
        lap("wind_downs")
        now = self.clock()
        marked_any = False
        for name, book in self.books.items():
            if now - float(self._state["last_mark"].get(name) or 0) < self.settings.mark_every_seconds:
                continue
            self._state["last_mark"][name] = now
            marked_any = True
            try:
                book.poll()
                book.mark()
                result = reconcile_with_second_look(book)
                summary["reconciled"][name] = result.ok
                if not result.ok:
                    # A few cents short on a PAPER book, with every position agreeing, are the venue's
                    # option fees and rounding. Measured Sept 22, 2026: two paper option buys left the
                    # book $0.06 over the venue for one mark pass, and an error then -- inside a deploy's
                    # watch -- rolls a good release back. Since Sept 24, 2026 the book books such cents
                    # as dust itself (`book.PRACTICE_DUST_USD`), so what still arrives here with cents is
                    # a practice book with an order in doubt. Real money, or any position difference,
                    # stays an error.
                    minor = (not book.real_money and not result.position_diffs
                             and abs(Decimal(result.cash_diff)) <= Decimal("1.00"))
                    # Only an order whose outcome the venue has not yet told (the book asks a second
                    # time 60 s later before it calls an order never-arrived, #203): the book stays
                    # frozen for entries until it is known, which is the protection; an error here
                    # would roll a good release back inside a deploy's watch (the #203 review).
                    pending_only = (not result.position_diffs and "outcome is unknown" in result.detail
                                    and "cash differs" not in result.detail)
                    minor = minor or pending_only
                    self.alert("warning" if minor else "error", f"{name} does not reconcile: {result.detail}")
            except Exception as exc:  # noqa: BLE001
                self.alert("warning", f"{name}: could not mark or reconcile ({type(exc).__name__}: {str(exc)[:200]})")
            lap(f"mark:{name}")
            for agent in self.registry.living():
                if self.book_of(agent) is book:
                    if pause and not book.real_money:
                        continue  # a paused paper record is frozen, not failing: judge it after
                    self.judge(agent)
                elif agent.id in book.accounts:
                    self._retry_wind_down(agent, book)
                    self._observe_wind_down(agent, book)
            for agent in self.registry.dead():
                if agent.id in book.accounts:
                    self._retry_wind_down(agent, book)
                    self._observe_wind_down(agent, book)
                    self._sweep(agent.id, book)
            lap(f"judge:{name}")
        if marked_any and allocator_module.enabled():
            # Capital is the ladder: bands and stakes follow the evidence of this very mark pass.
            moved = None
            try:
                moved = self.allocator.rebalance()
                summary["allocator"] = {k: len(v) if isinstance(v, list) else v for k, v in moved.items()}
            except Exception as exc:  # noqa: BLE001 - a pass that fails runs again at the next mark
                self.alert("error", f"the allocator's pass failed ({type(exc).__name__}: {str(exc)[:200]})")
            if moved is not None:  # a pass that failed says nothing of any drain: every hold stands
                try:
                    self._hold_draining_probes(moved)
                except Exception as exc:  # noqa: BLE001 - the holds stand; the next pass keeps them again
                    self.alert("warning", f"the drain holds could not be kept ({type(exc).__name__}: {str(exc)[:200]})")
        elif marked_any:
            try:
                self._hold_draining_probes(None)  # the allocator is off: nothing drains a probe, and no hold stands for it
            except Exception as exc:  # noqa: BLE001 - the holds stand until the next mark releases them
                self.alert("warning", f"the drain holds could not be released ({type(exc).__name__}: {str(exc)[:200]})")
        lap("allocator")
        try:
            self._floor_invariants()  # code over the ledger's new rows; costs nothing, so it runs while paused too
        except Exception as exc:  # noqa: BLE001 - a check that fails this tick runs again on the next
            self.alert("warning", f"the floor's invariants could not be checked ({type(exc).__name__}: {str(exc)[:160]})")
        lap("floor_invariants")
        # H5 (Sept 25, 2026): research is scheduled on the House's own lane, once a minute, never inside the tick
        # (`_schedule_research`): 6.3 s of the tick at p50 on the box, 24.0 s at its slowest, for work whose
        # answer (a job queued for a research worker) nobody on the tick waits for.
        if self._cadence_due("house:research", self.settings.house_job_seconds) \
                and self._background("house:research", self._house_job, self._schedule_research, open_for_business):
            self._cadence["house:research"] = self.clock()
        lap("research")
        if open_for_business and self.survey_due():
            self._background("niche-survey", self.survey_niches)  # stamped when it ends; one in hand is not started twice
        if open_for_business and self.semantic_lab is not None and self.semantic_lab.due():
            self._background('semantic-lab', self.semantic_lab.run)
        lap("schedule")
        if self.jev_floor is not None:
            self.jev_floor.tick(open_for_business)
        lap("jev")
        if self.backup is not None and self.backup.due():
            self._background("backup", self._run_backup)
        # Both are code over the ledger and cost nothing, so they run while the House is paused too.
        if self.pre_audit is not None and self.pre_audit.due():
            self._background("pre-audit", self.pre_audit.run, self)
        if self.consult_recovery is not None and self.consult_recovery.due():
            self._background("consult-recovery", self._recover_consults)
        lap("schedule")
        self._history_coverage()
        lap("history_coverage")
        if self.updater is not None and self.updater.due():
            self._background("update", self._update)
        if self.budget is not None and getattr(self.budget, "pacer", None) is None:
            self.budget.pacer = self.pacer
        self._pace_inference()
        lap("schedule")
        if open_for_business and self.merton is not None:
            allowed = TIER_ROLES[self.frontier_tier()]
            for role in self.merton.due():
                if allowed is not None and role not in allowed:
                    continue  # the month's last dollars are kept for code, audits and winners
                # One role at a time against today's allowance: a pass is a dime to a few dollars,
                # and its cost is only known when it ends. The jobs are copied before they are walked
                # (the review of #297, Sept 25, 2026): the House lane queues research beside the tick
                # (`_schedule_research`), and a key it added mid-walk raised "dictionary changed size
                # during iteration" -- a failed tick, an error alert inside a deploy's watch. Nearly
                # every research job a process queues is a new key: 26 restarts a day, one process an hour.
                if self.pacer.may_spend("openai") and not any(key.startswith("merton:") and key != "merton:follow" and job.is_alive()
                                                              for key, job in list(self._jobs.items())):
                    self._background(f"merton:{role}", self.merton.run, role)
            self._background("merton:follow", self.merton.follow)
        if open_for_business and self.engineer is not None and self.engineer.due():
            # The repair worklist: its sources, its free follow-ups and at most one paid patch a
            # step, each against its own per-job ceiling and the day's frontier allowance.
            self._background("engineer", self.engineer.step)
        lap("merton")
        # R2: a desk the search closes is held at its members BEFORE the foundry's and the lab's steps, which seat
        # newcomers by the desks' caps (the lab's on its own thread); read only in the population step below, the first
        # tick after a restart showed them a closed desk's niches.json cap (the review of #276). Cached: cheap twice.
        try:
            self._follow_the_search()
        except Exception:  # noqa: BLE001 - the caps stand as they are; the population step tries again and says so
            pass  # (once a tick: two warnings of one text a tick would reach the repeat escalation twice as fast)
        if self.hypotheses is not None and self._cadence_due("house:hypotheses", self.settings.house_job_seconds) \
                and self._background("house:hypotheses", self._house_job, self._foundry_step, open_for_business):
            # H5: the foundry's step beside the tick, once a minute (its own tier, budget and cadence gates
            # inside): 2.2 s of the tick at p50 on the box, 9.4 s at its slowest (23.0 s in the hour to 04:25Z).
            self._cadence["house:hypotheses"] = self.clock()
        lap("hypotheses")
        if self.lab is not None:
            self.lab.tick(open_for_business=open_for_business)  # schedules one bounded step off the tick (league/lab.py)
        lap("lab")
        if self.shards is not None:
            # Cheap on the tick (a cursor scan of new order rows); the venue calls run on the shards lane.
            self.shards.tick()
        lap("shards")
        if open_for_business and self.economy.payout_due():
            self.learn()
            with self._lifecycle_lock:
                for agent in self.registry.living() if not allocator_module.enabled() else ():
                    if self.evaluator.rung(agent.id) >= 3:
                        capital.resize(self, agent)
                    elif self.evaluator.rung(agent.id) == 2:
                        capital.top_up_micro(self, agent)
            capital.recommend(self, {name: (book.venue_cash or ZERO) for name, book in self.books.items() if book.real_money})
            # During the expedition the day's pool IS the day's Sail allowance: what the owner wants
            # spent is what the agents are given to spend.
            self.economy.payout(self.standings(),
                                pool=self.pacer.credit_pool(per_seconds=float(self.game["economy"]["epoch_seconds"])) if self.pacer.running() else None)
            self.ledger.append("ops.budget", {"what": "expedition", **self.pacer.report()})
            if self.auditor is not None:
                self.auditor.score()
        lap("payout")
        # Outside every gate, because this is the one thing that says a budget is gone and it used
        # to sit inside the payout that a spent budget closes -- it could only be delivered while
        # the condition it announces was false. It tells the owner once per kind; a tick is cheap.
        self._expedition_notices()
        self._tell_lost_sessions()
        lap("notices")
        try:
            self._enforce_horizon()
        except Exception as exc:  # noqa: BLE001 - a venue that is down now is asked again next tick
            self.alert("warning", f"the horizon rule could not close a position ({type(exc).__name__}: {str(exc)[:160]})")
        lap("horizon")
        if self.settings.real_money:
            self._enforce_tuition()
        lap("tuition")
        # Culling is not spending: an agent whose credits reached zero should still die, and its
        # post-mortem still be written, when the meter has stopped the floor. Only the refill that
        # follows it costs anything, and that waits for business.
        self.keep_population(refill=open_for_business, clock=not pause)
        summary["deaths"] = sorted(living_before - {a.id for a in self.registry.living()})
        lap("population")
        self._save_state()
        lap("save_state")
        if self.publisher is not None and self._cadence_due("publish", self.settings.publish_seconds):
            self._cadence["publish"] = self.clock()  # H5: once a minute, as at sixty-second ticks
            try:
                self.publisher.publish(self)
            except Exception as exc:  # noqa: BLE001 - the site is downstream of the floor, never upstream
                self.alert("warning", f"publishing failed ({type(exc).__name__}: {str(exc)[:200]})", **environment("site", exc))
        lap("publish")
        self._health(summary)
        return summary

    def _health(self, summary: Mapping[str, Any]) -> None:
        now = self.clock()
        with self._state_lock:
            jobs = [{"key": key, "state": "queued" if job["started_at"] is None else "running",
                     "queued_seconds": round(max((job["started_at"] if job["started_at"] is not None else now) - job["queued_at"], 0), 3),
                     "running_seconds": round(max(now - job["started_at"], 0), 3) if job["started_at"] is not None else 0}
                    for key, job in sorted(self._job_status.items())]
            deferred = {what: {k: row[k] for k in ("count", "reason", "at", "first_at")}
                        for what, row in sorted(self._deferred.items()) if now - row["epoch"] < 3600}
        try:
            seats = self._seats_health()
        except Exception as exc:  # noqa: BLE001 - health is written whatever the seat market says
            seats = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        lab = self.lab.health() if self.lab is not None else None
        # L3 (Sept 24, 2026): warnings that repeat, and the health failures the in-box watchdog reads.
        try:
            repeating = self._repeating_health()
        except Exception as exc:  # noqa: BLE001
            repeating = [{"error": f"{type(exc).__name__}: {str(exc)[:160]}"}]
        try:
            failures = self._health_failures(lab)
        except Exception as exc:  # noqa: BLE001 - a check that cannot run is not a failure it found
            failures = []
            self.alert("warning", f"the health failures could not be checked ({type(exc).__name__}: {str(exc)[:160]})")
        try:
            economy = {"sail_cap": self._sail_cap_state(),
                       "merton": self.merton.pause_state() if getattr(self.merton, "pause_state", None) else None}
        except Exception as exc:  # noqa: BLE001
            economy = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        health = {
            "at": summary["at"], "living": len(self.registry.living()), "dead": len(self.registry.dead()),
            "books": {name: {"frozen": book.frozen, "open_orders": len(book.open_orders()),
                             "attribution_issues": {a: report['issues'] for a in book.agents()
                                                    if not (report := book.evidence_integrity(a))['ok']}}
                      for name, book in self.books.items()},
            "ledger_seq": self.ledger.head()[0], "real_money": self.settings.real_money,
            "data_feeds": {name: {'stocks': getattr(book.broker, 'feed', None),
                                  'options': getattr(book.broker, 'option_feed', None)}
                           for name, book in self.books.items() if name.startswith('alpaca')},
            "release": Path(__file__).resolve().parents[1].name,
            "tick_duration_seconds": round(max(now - _epoch(summary["at"]), 0), 3),
            # The wake skip (Sept 24, 2026): stock and option wakes not run into a shut session (`_shut_session`).
            "wakes_skipped": dict(self._state.get("wakes_skipped") or {}),
            "background_jobs": jobs,
            "invalid_parameters": {a.id: report['errors'] for a in self.registry.living()
                                   if not (report := parameters.inspect(a.params, a.needs))['valid']},
            "durable_research": [{k: j[k] for k in ("session", "agent", "status", "created", "updated", "available", "reason", "resumes")}
                                 for j in self.research_jobs.pending()],
            "candidate_admissions": [{k: row.get(k) for k in ('session', 'agent', 'status', 'reason', 'child')}
                                     for row in Admissions(self.ledger).rows()[-30:]],
            "recordings": self.recorder.stats(),
            "campaign": self.campaigns.report() if self.campaigns else None,
            "promotion_status": [dict(row) for agent in self.registry.living()
                                 if (row := self._state.get('promotion_status', {}).get(agent.id))
                                 and row.get('code_sha256') == agent.code_sha256],
            "semantic_lab": self.semantic_lab.stats() if self.semantic_lab else None,
            "stopped_because": summary.get("stopped_because"),
            "jev": self.jev_floor.health() if self.jev_floor else None,
            "hypotheses": self.hypotheses.stats() if self.hypotheses is not None else None,
            "lab": lab,  # closed since when, paid phases skipped, graduates waiting
            "feeds": self.feeds.health() if self.feeds is not None else None,
            "shards": self.shards.health() if self.shards is not None else None,
            "deferred": deferred,
            "seats": seats,
            "repeating_warnings": repeating,
            "failures": failures,
            "research_economy": economy,
            # H6 (Sept 25, 2026): the restarts of the last day and what became of the research in flight at this one.
            **self._restarts_health(),
            "restart_research": self._restart_research_health(),
        }
        health["tick_steps"] = self._tick_steps(str(summary["at"]))  # last: its `health` step is this block
        tmp = self.root / "health.tmp"
        tmp.write_text(json.dumps(health, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.root / "health.json")

    def _restarts_health(self) -> dict[str, Any]:
        """health.json `restarts_24h` (the `ops.started` rows of the last 24 hours on the House's clock),
        `restarts_24h_in_session` (those that fell inside a regular US equity session, which the release train
        must never restart the House in) and `last_start` (the newest: at, release, ledger seq). Read at most
        once a minute. H6 (Sept 25, 2026): 26 starts in the day to 04:25Z, 24-37 a day Sept 20-24, seven inside
        the Sept 24 session; the plan's line is six a day and none in a session, and health said nothing."""
        now = self.clock()
        hit = self._data_cache.get("restarts")
        if hit is not None and now - hit[0] < 60:
            return hit[1]
        try:
            rows = self.ledger.read(kinds="ops.started", limit=500, newest=True)
            since = now_iso(lambda: now - 86400)
            recent = [row for row in rows if row.at >= since]
            in_session = 0
            for row in recent:
                try:
                    in_session += bool(market_open_at(row.at))
                except Exception:  # noqa: BLE001 - a moment outside the computed calendar is not a session
                    pass
            last = rows[-1] if rows else None
            value = {"restarts_24h": len(recent), "restarts_24h_in_session": in_session,
                     "last_start": None if last is None else {"at": last.at, "release": last.payload.get("release"), "seq": last.seq}}
        except Exception as exc:  # noqa: BLE001 - health is written whatever the ledger says
            value = {"restarts_24h": None, "restarts_24h_in_session": None, "last_start": {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}}
        self._data_cache["restarts"] = (now, value)
        return value

    def _restart_research_health(self) -> dict[str, Any]:
        """health.json `restart_research` (H6): the research sessions in flight when this House started
        (`at_start`), how many have since ended as usual (`resumed`), were closed because their agent died or
        changed (`retired`), or were lost (`lost_count`, and the last `SESSION_LOSSES_SHOWN` in `lost`: session,
        agent, reason, whether it began before this start), and the ones still `waiting` to resume."""
        with self._state_lock:
            book = self._restart_research
            return {"started_at": book["started_at"], "at_start": book["at_start"], "resumed": book["resumed"],
                    "retired": book["retired"], "lost_count": int(book.get("lost_count") or 0),
                    "lost": [dict(row) for row in book["lost"]], "waiting": sorted(book["in_flight"])}

    def _health_failures(self, lab: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        """health.json `failures`: what the in-box watchdog (league/watchdog.py) reads as a failure of
        the House, each `{check, text, since}`. The House says so once when one begins (an error
        alert whose `began_at` is its `since`) and once when it ends (an info).

        `lab_evaluates` (L3, Sept 24, 2026): the Alpha Lab evaluated nothing for LAB_IDLE_SECONDS
        while its queue was not empty. At T0 of the close-the-gaps run its last batch was 23:37:17Z
        with 618 candidates queued, and only a warning a step said anything. What the watchdog does
        with it is in its `read_health`: a canary would refuse on it, the watch after a promotion
        never rolls back for it (an hour of nothing cannot begin inside a ten-minute watch)."""
        out = []
        idle = self._lab_idle(lab)
        if idle is not None:
            out.append(idle)
        current = {row["check"]: row for row in out}
        with self._state_lock:
            known = self._state.setdefault("health_failures", {})
            began = [row for check, row in current.items() if check not in known]
            ended = [check for check in list(known) if check not in current]
            for row in began:
                known[row["check"]] = row["since"]
            for check in ended:
                known.pop(check, None)
        for row in began:
            self.alert("error", f"health failure: {row['text']}", failure=row["check"], began_at=row["since"])
        for check in ended:
            self.alert("info", {"lab_evaluates": "the lab evaluates again"}.get(check, f"the health failure {check} has cleared"),
                       failure=check)
        return out

    def _lab_idle(self, lab: Mapping[str, Any] | None) -> dict[str, Any] | None:
        """The lab's health failure, or None: candidates queued, and no batch for LAB_IDLE_SECONDS since
        the later of its last batch and its oldest queued candidate (a queue that filled half an hour
        ago has not had its hour)."""
        if self.lab is None or not isinstance(lab, Mapping):
            return None
        queued = int(lab.get("queued") or 0)
        if queued <= 0:
            return None
        last = self.lab._q("SELECT MAX(at) AS at FROM batches")[0]["at"]
        oldest = self.lab._q("SELECT MIN(created) AS at FROM candidates WHERE status='queued'")[0]["at"]
        since = max(float(last or 0), float(oldest or 0))
        if not since or self.clock() - since < LAB_IDLE_SECONDS:
            return None
        shown = now_iso(lambda: float(last)) if last else "never"
        notes = "".join(f"; {name}: {str(lab.get(key))[:200]}" for key, name in (("refusal", "closed"), ("error", "its step fails"))
                        if lab.get(key))
        return {"check": "lab_evaluates", "since": now_iso(lambda: since),
                "text": f"the lab evaluated nothing in the last hour while {queued} candidates are queued (last batch {shown}{notes})"}

    #: How long the graceful shutdown waits, in all, for the background work in flight (a backup, a replay, a research
    #: turn) before it closes the House's stores; the process then exits and the work with it. Sept 25, 2026: the
    #: owner's release promoted at 00:04:42Z was judged on the OLD House's backup, which had been in flight in Sail's
    #: checkpoint call since 00:03:13Z and failed at 00:05:55Z, 3 s before that House exited. The TERM-to-exit time
    #: (76 s there; 24-82 s over the 13 restarts from 18:43Z Sept 24) was the tick in hand, the rest of the tick's
    #: minute (`league/__main__.py`) and `sandbox.sleep_all` (at most 60 s); this wait is the last 5 s at most.
    SHUTDOWN_WAIT_SECONDS = 5.0

    def close(self, *, wait: float | None = SHUTDOWN_WAIT_SECONDS) -> None:
        self._closing.set()
        self.wait(wait)
        self._save_state()
        self.recorder.close()
        if self.feeds is not None:
            self.feeds.close()
        self.research_jobs.close()
        self.ledger.close()
        if self.campaigns:
            self.campaigns.close()


def _code_venue(code: str) -> str | None:
    """The venue a strategy file's literal NEEDS name, read without running it; None when it names none."""
    from .lab import static_literal

    needs = static_literal(str(code or ""), "NEEDS") or {}
    return str(needs.get("venue")) if needs.get("venue") else None


def _epoch(iso: str) -> float:
    from ltcm.broker import instant

    parsed = instant(iso)
    return parsed.timestamp() if parsed else 0.0


def names_match(founder: Mapping[str, Any], names: Sequence[str]) -> bool:
    """`league found --seeds` takes either the desk name or the founder's role key."""
    return founder["key"] in names or founder["name"] in names


def occ_symbol(instrument: Any) -> str:
    """`F260925C00013000`: root, YYMMDD, C or P, the strike in thousandths."""
    expiry = str(instrument.expiry or "").replace("-", "")
    right = "C" if str(instrument.right or "").lower() == "call" else "P"
    return f"{str(instrument.symbol).upper()}{expiry[2:]}{right}{int(Decimal(str(instrument.strike)) * 1000):08d}"


def _plus_days(date: str, days: int) -> str:
    from datetime import date as _date, timedelta

    return (_date.fromisoformat(date) + timedelta(days=days)).isoformat()


def _new_york(clock: Callable[[], float]) -> tuple[str, float]:
    """(date, hour of the day as a decimal) in New York now."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    moment = datetime.fromtimestamp(clock(), tz=timezone.utc).astimezone(ZoneInfo("America/New_York"))
    return moment.strftime("%Y-%m-%d"), moment.hour + moment.minute / 60.0


def session_time(start: float, end: float, *, horizon_days: int = 30) -> tuple[float, int]:
    """(seconds of regular US equity session, sessions that closed) between two instants, holidays
    and early closes included. A session counts as closed when its close falls after `start` and
    no later than `end`, so the session an agent was first offered counts once it closes.

    A span longer than `horizon_days` is plenty of both: it is reported as infinite time and as
    many sessions as it has days, without walking the calendar. Outside the computed NYSE calendar
    the span is wall-clock time and whole days, which is what the grace measured before."""
    from datetime import datetime, timedelta, timezone

    from ltcm.data import NEW_YORK, DataError, to_datetime, us_equity_session

    if end <= start:
        return 0.0, 0
    if end - start > horizon_days * 86400:
        return math.inf, int((end - start) // 86400)
    day = datetime.fromtimestamp(start, timezone.utc).astimezone(NEW_YORK).date()
    last = datetime.fromtimestamp(end, timezone.utc).astimezone(NEW_YORK).date()
    seconds, closed = 0.0, 0
    try:
        while day <= last:
            session = us_equity_session(day)
            if session is not None:
                opened = to_datetime(session.open_at).timestamp()
                closes = to_datetime(session.close_at).timestamp()
                seconds += max(0.0, min(end, closes) - max(start, opened))
                if start < closes <= end:
                    closed += 1
            day += timedelta(days=1)
    except DataError:
        return end - start, int((end - start) // 86400)
    return seconds, closed
