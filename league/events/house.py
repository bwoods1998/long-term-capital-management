"""The event lane on the House (release R1, WP1): the desktop's passes as one bounded scheduler beside the House's tick.

PHASE 2 of goal-2026-10-19/EVL-DESIGN.md: the functions blake-desktop ran from systemd timers run inside the House's
process, on its state root (`<state>/events/`: events.sqlite and docs/, the same store), with the House's gateway token
and its SEC contact. `league/service.py` attaches the lane when `config.json` `events.enabled` is true, on the House
box's own loop only (never a canary, never a `tick` or `status` beside the loop).

THE HOOK. The lane is NOT `House.feeds`: a non-None `feeds` also wakes the House's legacy feed paths (the agents'
`ctx["feeds"]`, the replay tapes' feeds and coverage, `_require_feeds`' refusals, research_capabilities'
`observations.feeds`, the tool requests' fulfilment), and research_capabilities answers differently for any non-None
`feeds` whatever it holds (league/tests/test_events_house.py shows it). So the lane takes the other unprotected hook the
spec names: `house.publisher` is wrapped (`LanePublisher`), and on each of the tick's publishes (every
`publish_seconds`, 60 s) the original publisher runs exactly as before and then, when the lane is due, its turn is
started on the House's one-slot feeds lane with `house._background("feeds:evl", lane.run)`. `house.feeds` stays None,
so every legacy path behaves as it does today.

ONE TURN, ONE TASK, BOUNDED. `run()` does the single most urgent due task, never raises (a failure is a warning at most
once an hour per task, so the House's repeat rule never turns it into an error), and keeps its time:
1. a DECISION due: the open at 09:15 ET, the close's at the close - 14 minutes (a minute later, for the 15:30 minute
   bar); live within 10 minutes of its time, a backfill after (the judge's rule: league/events/run.py `live_run`); then
   a missed one, then a pending
   one again (the hourly re-decision of the last three sessions, as the desktop's catchup, waits for the record pass;
   so does PREREG-EVL-4'S ROWS' OWN DECISION, `decide-close-evl4`, of every older close a release without them decided:
   release 1019c's review, `_refill_redecide`);
2. VERDICTS for a decision within 30 minutes (today's open or close), or for a decision that is pending (a close
   decision waiting on verdicts only its session's OPEN decision asks, PREREG-EVL-4's PM rows, has those asked by the
   open decision's own code; a wait no call of the pass could answer backs off like one the gateway refused);
3. the RECORD pass every 2 minutes: EDGAR's current feeds and the news, at most 90 s, resumable (a new filing is stored
   `listed` at once and fetched in order, so a pass cut short loses nothing), then today's verdicts with the time
   left (its open decision's, then its close decision's: PREREG-EVL-2's day news is read through the session);
4. NIGHTLY: the account equity after the close, the score at 20:30 ET, the screen (with PREREG-EVL-3's band review
   of the real fills: demotion and Sized, league/events/bands.py `review`) and the report after it;
5. the TICKER snapshot at 07:00 ET;
6. EARLY VERDICTS from 07:30 ET (the session's universe is fixed then: its tickers copy is the latest before 07:30 ET),
   for its open decision and then its close decision;
7. the daily-index BACKFILL of the last weekdays, for anything the live pass missed or failed (a filing whose fetch fails
   in it is tried again on the record pass's backoff, its day done after its last try with the filing named; a federal
   holiday's missing index is done: `SEC_HOLIDAYS`).
A backlog (missed decisions, a long verdict queue) never holds the record pass past a second cadence: then only a live
decision goes before it. A task ends early when a decision falls due; a decision's and a verdict task's network reads
stop at their bound and the next turn goes on from what was stored (universe rows, cik_info, bars and verdicts are kept
as they are read). `<state>/events/STOP` idles the lane without a deploy: the lane only, never the House's event book,
which still decides each auction on the store as it stands (the instant stop of event buys is the gateway's
`STOCK_EVENT_BUYS` off or `equity_money.event.enabled` False: docs/operations.md, release 1019b's Rollback).

Paid work: a verdict is asked only while the House is not paused (`PAUSE`), and only under THE LANE'S LINE of a UTC
day (00:00-24:00 UTC: budget rule 3's day, on which the Sail guard, the router and the cap breach judge theirs; the
review of r2/alarms, its major 1: held on New York days, the lane could spend one day's line after 20:00 ET and the next
day's from 00:00 ET, two lines in one UTC day): the lower of `events.verdict_usd_day` ($3, the default too: release
1019b's second review, the goal's cost rule, the House box's about $1.29 a day and the verdicts inside its $5 base) and
the budget rule's allowance for the lane's verdicts (league/ops/budget.py `lane_allowance`: the Claude meter's lane part
in `<state>/budget.json`, its no-profit floor when the file is not usable, 0 under the cap breach hold), so the verdicts
and every other metered dollar stay under the day's cap (budget rule 3; release 1019c). Over it, READ events wait
(PREREG-EVL-1 section 4), as they do for any call with no answer.
Market-data reads are spaced `DATA_INTERVAL` apart (Alpaca's Basic plan is shared
with the House's own book).
"""

from __future__ import annotations

import collections
import dataclasses
import datetime as dt
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from . import bands as BA
from . import calendar as C
from . import edgar as E
from . import gw as G
from . import news as N
from . import programs as P
from . import report as RP
from . import run as R
from . import score as SC
from . import screen as SN
from . import store as S
from . import universe as U
from . import verdicts as V

UTC = dt.timezone.utc
ROOT_NAME = "events"
HEALTH_FILE = "lane.json"
STOP_FILE = "STOP"                            # <state>/events/STOP: the lane idles while it exists (no deploy needed)
BACKGROUND_KEY = "feeds:evl"

RECORD_EVERY = dt.timedelta(minutes=2)
RECORD_BUDGET = 90.0
NEWS_BUDGET = 30.0
DECIDE_BUDGET = 150.0
VERDICT_BUDGET = 90.0
SCORE_BUDGET = 120.0
BACKFILL_BUDGET = 90.0
#: A task never runs into a decision: it ends this long before one falls due.
DECISION_MARGIN = 5.0
#: The verdict step of a record pass starts only with this much of its bound left.
VERDICT_STEP_MIN = 10.0

#: A decision run this soon after its time is live: THE JUDGE'S (release 1019b's third review: each run's rule fixes its
#: session's eligibility for good), defined once in league/events/run.py behind the wall; every live-or-backfill choice
#: here is `R.live_run`'s.
LIVE_WITHIN = R.LIVE_WITHIN
CLOSE_GRACE = dt.timedelta(minutes=1)         # C1 runs a minute after its time: the 15:30 bar is on the tape at 15:46
PENDING_RETRY = dt.timedelta(minutes=5)       # a decision waiting on verdicts is tried again this often
STALE_RETRY = dt.timedelta(minutes=10)        # a decision whose run never finished, when it is not this lane's
DECIDE_RETRY = dt.timedelta(minutes=1)        # a decision that FAILED (an error, not its bound) is tried again this soon
REDECIDE_EVERY = dt.timedelta(hours=1)
#: THE RE-DECISION REACH IS THE JUDGE'S (release 1019b's second review): a look waits until its close is out of the
#: sessions the House still decides again (league/events/screen.py `final_until`), so the House takes its reach from
#: the protected judge (league/events/screen.py, behind league/ci.py's wall), defined there once: a change of this file
#: the updater ships by itself can only use the reach, never widen it (and `final_until` waits out the larger reach if
#: one ever did). REDECIDE_SESSIONS: the last sessions decided again every hour (league.events.__main__'s catchup too);
#: LOOKBACK: decisions older than this are the CLI's (`catchup`); BACKFILL_WEEKDAYS: the daily-index backfill's reach.
REDECIDE_SESSIONS = SN.FINAL_SESSIONS
LOOKBACK = SN.FINAL_LOOKBACK
#: PREREG-EVL-4'S ROWS DECIDED BY THEMSELVES (release 1019c's review): the decision kind (its receipt
#: `decide-close-evl4:<day>`, league/events/run.py `decide_close` with `evl4_only`) the lane runs, once and as a
#: backfill, for every close since PREREG-EVL-4's registration that a release without its rows decided and the hourly
#: re-decision no longer reaches (league/events/screen.py `made_without`, the judge's: until it is made the close is not
#: final for those programs). The earlier rows of such a close are never decided again by it.
FOUR_KIND = SN.FOUR_KIND
URGENT_BEFORE = dt.timedelta(minutes=30)
VERDICT_BACKOFF = dt.timedelta(minutes=10)    # verdicts that got no answer (refused, failed, paused, over the line)
UNIVERSE_AT = dt.time(7, 30)
TICKERS_AT = dt.time(7, 0)
TICKERS_RETRY = dt.timedelta(minutes=5)
SCORE_AT = dt.time(20, 30)
REPORT_AT = dt.time(21, 5)                    # a day with no session: its report at this time
EQUITY_AFTER = dt.timedelta(minutes=3)
EQUITY_RETRY = dt.timedelta(minutes=10)
BACKFILL_WEEKDAYS = SN.FINAL_BACKFILL_WEEKDAYS
BACKFILL_AT = dt.time(5, 0)                   # a weekday's daily index is read from 05:00 ET the next day
BACKFILL_RETRY = dt.timedelta(hours=1)
#: SEC HOLIDAYS (release 1019f): EDGAR accepts no filings on a US federal holiday and publishes no daily index for it,
#: so such a weekday's index URL answers 404 for good, and its backfill waited every hour while the day was in reach
#: (every look across Wed Nov 11, 2026, Veterans Day, on which NYSE trades). A weekday in this table whose index answers
#: 404 is done, "no index: SEC holiday"; a 404 on any other weekday, or a holiday's index that answers anything else,
#: waits as an unpublished index does, and a holiday's index that exists is read as any day's. The federal holidays of
#: 2026 and 2027 as OPM lists them (https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/, read Oct 21,
#: 2026), and Fri Dec 31, 2027: New Year's Day 2028 falls on a Saturday, so the Friday before is its holiday (5 U.S.C.
#: 6103(b)(1)). A closure by executive order (a Christmas Eve) is not in it: add the day before it falls; 2028's before
#: Jan 2028.
SEC_HOLIDAYS: dict[dt.date, str] = {
    dt.date(2026, 1, 1): "New Year's Day", dt.date(2026, 1, 19): "Birthday of Martin Luther King, Jr.",
    dt.date(2026, 2, 16): "Washington's Birthday", dt.date(2026, 5, 25): "Memorial Day",
    dt.date(2026, 6, 19): "Juneteenth National Independence Day", dt.date(2026, 7, 3): "Independence Day",
    dt.date(2026, 9, 7): "Labor Day", dt.date(2026, 10, 12): "Columbus Day", dt.date(2026, 11, 11): "Veterans Day",
    dt.date(2026, 11, 26): "Thanksgiving Day", dt.date(2026, 12, 25): "Christmas Day",
    dt.date(2027, 1, 1): "New Year's Day", dt.date(2027, 1, 18): "Birthday of Martin Luther King, Jr.",
    dt.date(2027, 2, 15): "Washington's Birthday", dt.date(2027, 5, 31): "Memorial Day",
    dt.date(2027, 6, 18): "Juneteenth National Independence Day", dt.date(2027, 7, 5): "Independence Day",
    dt.date(2027, 9, 6): "Labor Day", dt.date(2027, 10, 11): "Columbus Day", dt.date(2027, 11, 11): "Veterans Day",
    dt.date(2027, 11, 25): "Thanksgiving Day", dt.date(2027, 12, 24): "Christmas Day",
    dt.date(2027, 12, 31): "New Year's Day",
}
SEC_HOLIDAY_WHY = "no index: SEC holiday"
CALENDAR_EVERY = dt.timedelta(hours=20)
CALENDAR_RETRY = dt.timedelta(minutes=10)
CALENDAR_BACK = dt.timedelta(days=60)
CALENDAR_AHEAD = dt.timedelta(days=120)
IDLE_LOOK = dt.timedelta(minutes=5)           # nothing due: look again at the latest this soon
FAIL_BACKOFF = dt.timedelta(minutes=10)       # a task that failed (record, nightly, tickers, backfill) waits this long
WAIT_LOOK = 60.0                              # no store yet: look again this often (seconds of the House clock)
FETCH_WINDOW = dt.timedelta(days=2)           # listed filings the record pass still fetches
FETCH_TRIES = 6                               # ... and a failed fetch is tried this many times in all,
#: ... again at the first record pass this long after its FIRST failure (release 1019b's second review: tried at every
#: pass, an SEC outage of about 12 minutes, or SEC's 10-minute rate-limit block, spent every try): 2, 4, 8, 16 and 32
#: minutes, then left to the daily-index backfill. The backfill tries a daily-index filing by the same two (release
#: 1019f: `_backfill`), with its own count.
FETCH_BACKOFF = tuple(dt.timedelta(minutes=2 ** k) for k in range(1, FETCH_TRIES))

WARN_EVERY = 3600.0
DATA_INTERVAL = 0.5
ASSETS_TTL = 1800.0
VERDICT_USD_DAY = 3.0                         # league/config.json events.verdict_usd_day (the goal's cost rule)
VERDICT_USD_UNKNOWN = 0.01                    # a verdict whose cost the gateway did not state


class LaneCut(OSError):
    """A Claude call the lane refused itself (past its bound, the House paused, the day's line reached): no answer, so
    the verdict is asked again later (league.events.verdicts.ask treats it as a transport failure)."""


class LaneDeadline(Exception):
    """A network read past the task's bound: the task stops, and the next turn goes on from what it stored."""


def events_enabled(config: Mapping[str, Any], *, canary: bool = False) -> bool:
    """`config.json` `events.enabled` (a missing key is OFF), never on a canary."""
    return not canary and (config.get("events") or {}).get("enabled") is True


@dataclasses.dataclass
class Task:
    name: str
    run: Callable[["LaneContext", float], dict[str, Any]]
    budget: float | None
    cut: bool = False   # network reads stop at the bound (their progress is kept in the store)


@dataclasses.dataclass
class VerdictLook:
    at: dt.datetime     # when the session's verdicts were last looked at (the House's clock)
    missing: int
    stalled: bool       # nothing stored and something refused or failed: wait VERDICT_BACKOFF


# ---------------------------------------------------------------------------------------------------- the gateway
class LaneGateway:
    """The lane's gateway for one task: market-data reads spaced and (`cut`) stopped at the bound; Claude calls refused
    (`LaneCut`) past the bound, while the House is paused or over the day's line, and counted."""

    def __init__(self, inner: Any, lane: "EventLane", deadline: float | None, *, cut: bool):
        self.inner, self.lane, self.deadline, self.cut = inner, lane, deadline, cut
        self.counts: collections.Counter[str] = collections.Counter()

    @property
    def last_headers(self) -> Mapping[str, str]:
        return getattr(self.inner, "last_headers", {}) or {}

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        if self.cut and self.lane.late(self.deadline):
            raise LaneDeadline(f"the task's bound passed before {path}")
        self.lane.throttle()
        return self.inner.get_json(path, params)

    def post_json(self, path: str, body: Any, headers: Mapping[str, str] | None = None) -> tuple[int, Any]:
        if path != V.PATH:
            return self.inner.post_json(path, body, headers)
        why = self.lane.claude_refusal(self.deadline)
        if why:
            self.counts[f"cut_{why}"] += 1
            raise LaneCut(why)
        self.counts["asked"] += 1
        try:
            code, payload = self.inner.post_json(path, body, headers)
        except OSError:
            self.counts["failed"] += 1
            raise
        if 200 <= code < 300:
            self.counts["answered"] += 1
            self.lane.spent(self.last_headers.get(V.COST_HEADER))
        elif 400 <= code < 500 and code != 429:
            self.counts["refused"] += 1
        else:
            self.counts["failed"] += 1
        return code, payload


class LaneContext(R.Context):
    """league.events.run's Context with the lane's caches: the asset list (`ASSETS_TTL`) and the parsed ticker
    snapshots outlive one turn, so a turn does not download either again."""

    def __init__(self, lane: "EventLane", store: S.Store, gw: LaneGateway, sec: Callable[[str], bytes],
                 now: Callable[[], dt.datetime]):
        super().__init__(store, gw, sec, now=now)
        self._lane = lane

    def _parsed(self, sha: str) -> dict[str, list[tuple[str, str]]]:
        cache = self._lane._tickers
        if sha not in cache:
            data = self.store.get_document(sha)
            while len(cache) >= 2:
                cache.pop(next(iter(cache)))
            cache[sha] = U.sec_tickers(lambda url: data)
        return cache[sha]

    def assets(self, live: bool = True) -> dict[str, Mapping[str, Any]]:
        return self._lane.assets(self.gw, "active" if live else "all")


# ---------------------------------------------------------------------------------------------------- the lane
class EventLane:
    """The event lane's scheduler on the House (see the module docstring). `due()`, `run()`, `shipped()` (False) and
    `health()`, the feeds lane's interface; `turn(house)` is what the wrapped publisher calls."""

    def __init__(self, house: Any, root: str | os.PathLike[str], *, gateway: Any = None,
                 sec: Callable[[str], bytes] | None = None, settings: Mapping[str, Any] | None = None,
                 monotonic: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.house = house
        self.root = Path(root)
        self.settings = dict(settings or {})
        self.verdict_usd_day = float(self.settings.get("verdict_usd_day", VERDICT_USD_DAY))
        self._line = {"usd_day": 0.0, "source": "not read yet"}   # THE LANE'S LINE (`_spend_today`): none before it is read
        self._gateway = gateway
        self._sec_base = sec
        self._mono = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._running: str | None = None
        self._next_look = float("-inf")        # House clock: due() says nothing before this
        self._ready = False
        self._stopped = False
        self._waiting_told = False
        self._stop_told = False
        self._started_told = False
        self._born = self.now()
        self._last_get = float("-inf")
        self._asset_cache: dict[str, tuple[float, dict[str, Mapping[str, Any]]]] = {}
        self._tickers: dict[str, dict[str, list[tuple[str, str]]]] = {}
        self._warned: dict[str, float] = {}
        self._warnings = 0
        self._tasks: dict[str, dict[str, Any]] = {}
        self._last: dict[str, Any] | None = None
        self._cut: set[tuple[str, dt.date]] = set()
        self._redecide: set[tuple[str, dt.date]] = set()
        self._redecide_next = self._born
        self._four: set[dt.date] = set()        # closes whose PREREG-EVL-4 rows wait for their own decision
        self._looks: dict[tuple[str, dt.date], VerdictLook] = {}
        self._events_at = self._born            # when a record pass last stored something new
        self._universe_told: set[dt.date] = set()
        self._attempts: dict[str, dt.datetime] = {}
        self._score_seen: dict[dt.date, set[tuple[str, int, str]]] = {}
        self._backfill_seen: dict[dt.date, set[str]] = {}
        # day -> accession -> (the backfill's fetches tried, when the first failed, form, the last error): a failed
        # daily-index filing, this process's (`_backfill`); and day -> when its next retry is due (`_backfill_due`)
        self._backfill_failed: dict[dt.date, dict[str, tuple[int, dt.datetime, str, str]]] = {}
        self._backfill_wait: dict[dt.date, dt.datetime] = {}
        self._index_rows: dict[dt.date, list[dict[str, Any]]] = {}
        self._usd = {"day": None, "usd": 0.0}
        self._paused = False
        self._failed: dict[str, dt.datetime] = {}
        # accession -> (the fetches tried, when the first one failed), this process's (`_record_steps`)
        self._fetch_tries: dict[str, tuple[int, dt.datetime | None]] = {}

    # -- the feeds lane's interface ---------------------------------------------------------------------------------
    def shipped(self) -> bool:
        """Nothing the House's tool requests could read: the lane answers none of them (the feeds interface)."""
        return False

    def due(self) -> bool:
        """Cheap and on the tick's thread: whether a turn is worth starting. Never raises."""
        try:
            with self._lock:
                if self._running is not None or self.house.clock() < self._next_look:
                    return False
            if not self.ready():
                self._tell_stopped() if self._stopped else self._tell_waiting()
                with self._lock:
                    self._next_look = self.house.clock() + WAIT_LOOK
                return False
            self._stop_told = False
            return True
        except Exception:  # noqa: BLE001 - the tick never pays for the lane
            return False

    def turn(self, house: Any) -> None:
        """Start a turn on the House's feeds lane when one is due (the wrapped publisher's call). Never raises."""
        try:
            if self.due():
                house._background(BACKGROUND_KEY, self.run)
        except Exception as exc:  # noqa: BLE001
            self.warn("turn", exc)

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {"enabled": True, "ready": self._ready, "stopped": self._stopped, "root": str(self.root),
                    "running": self._running,
                    "next_look": _iso_epoch(self._next_look), "last": dict(self._last) if self._last else None,
                    "tasks": {k: dict(v) for k, v in sorted(self._tasks.items())},
                    "verdict_usd_today": round(float(self._usd["usd"]), 4), "verdict_usd_day": self.verdict_usd_day,
                    "verdict_line_usd": round(float(self._line["usd_day"]), 4), "verdict_line_source": self._line["source"],
                    "warnings": self._warnings}

    def ready(self) -> bool:
        """The store exists (the migration, scripts/evl_migrate.py, made it, or the operator did; the lane never makes
        its own root, so it cannot race the migration that fills it) and no `STOP` file is in it."""
        self._ready = (self.root / S.DB_NAME).is_file()
        self._stopped = self._ready and (self.root / STOP_FILE).exists()
        return self._ready and not self._stopped

    # -- clocks, bounds and paid work -------------------------------------------------------------------------------
    def now(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(float(self.house.clock()), UTC)

    def closing(self) -> bool:
        flag = getattr(self.house, "_closing", None)
        return bool(flag is not None and flag.is_set())

    def late(self, deadline: float | None) -> bool:
        return self.closing() or (deadline is not None and self._mono() >= deadline)

    def throttle(self) -> None:
        wait = self._last_get + DATA_INTERVAL - self._mono()
        if wait > 0:
            self._sleep(wait)
        self._last_get = self._mono()

    def claude_refusal(self, deadline: float | None) -> str | None:
        if self.closing():
            return "closed"
        if deadline is not None and self._mono() >= deadline:
            return "deadline"
        if self._paused:
            return "paused"
        if self._usd["usd"] >= self._line["usd_day"]:
            return "cap"
        return None

    def spent(self, header: Any) -> None:
        try:
            usd = float(header) if header not in (None, "") else VERDICT_USD_UNKNOWN
        except (TypeError, ValueError):
            usd = VERDICT_USD_UNKNOWN
        self._usd["usd"] += max(0.0, usd)

    def _spend_today(self, st: S.Store, now: dt.datetime) -> None:
        """The day's verdict dollars so far, from the store, and the line the next call is held to (`verdict_line`). THE
        DAY is the UTC day (`verdict_day`: budget rule 3's, every other line's and the cap breach's)."""
        day, (lo, hi) = verdict_day(now)
        row = st.db.execute("SELECT COALESCE(SUM(usd), 0), COALESCE(SUM(usd IS NULL), 0) FROM verdicts WHERE "
                            "answered_at>=? AND answered_at<?", (lo, hi)).fetchone()
        self._usd = {"day": day, "usd": float(row[0]) + VERDICT_USD_UNKNOWN * int(row[1])}
        self._line = self.verdict_line(now)

    def verdict_line(self, now: dt.datetime) -> dict[str, Any]:
        """THE LANE'S LINE (the module docstring): {usd_day, source}, the lower of `events.verdict_usd_day` and the budget
        rule's allowance (league/ops/budget.py `lane_allowance`, which never raises and falls back to the rule's own
        no-profit line). Anything else that goes wrong is no line at all: no paid call (FAIL CLOSED)."""
        try:
            from ..ops import budget as B

            got = B.lane_allowance(self.root.parent, now.timestamp())
            allowance, source = max(0.0, float(got["usd_day"])), str(got.get("source") or "budget.json")
        except Exception as exc:  # noqa: BLE001 - no allowance read is no paid verdict
            return {"usd_day": 0.0, "source": f"the budget's allowance could not be read ({type(exc).__name__})"}
        if self.verdict_usd_day <= allowance:
            return {"usd_day": self.verdict_usd_day, "source": "events.verdict_usd_day"}
        return {"usd_day": allowance, "source": f"the budget's allowance: {source}"}

    def assets(self, gw: Any, key: str) -> dict[str, Mapping[str, Any]]:
        """Alpaca's asset list (`key` "active" for the live rule, "all" for the backfill rule), kept ASSETS_TTL. An
        EMPTY answer is never kept (release 1019b's third review): league/events/run.py `eligibility` decides nothing on
        it, so the next turn asks Alpaca again, inside the live decision's window, instead of failing on it for half an
        hour."""
        have = self._asset_cache.get(key)
        if have is not None and self._mono() - have[0] < ASSETS_TTL:
            return have[1]
        rows = U.alpaca_assets(gw, key)
        keep = ("symbol", "class", "exchange", "status", "tradable")
        slim = {sym: {k: a.get(k) for k in keep} for sym, a in rows.items()}
        if slim:
            self._asset_cache[key] = (self._mono(), slim)
        else:
            self._asset_cache.pop(key, None)
        return slim

    def gateway(self) -> Any:
        if self._gateway is None:
            from ..service import secret  # the House's own token source, as league/service.py gives the live path

            self._gateway = G.Gateway(lambda: secret("GATEWAY_TOKEN"))
        return self._gateway

    def sec(self) -> Callable[[str], bytes]:
        if self._sec_base is None:
            self._sec_base = G.sec_getter()   # ltcm.data CONTACT_USER_AGENT, one transport: one SEC rate
        return self._sec_base

    def _sec_for(self, deadline: float | None, cut: bool) -> Callable[[str], bytes]:
        base = self.sec()

        def get(url: str) -> bytes:
            if cut and self.late(deadline):
                raise LaneDeadline(f"the task's bound passed before {url[:80]}")
            return base(url)
        return get

    # -- warnings ---------------------------------------------------------------------------------------------------
    def warn(self, task: str, exc: BaseException | str) -> None:
        """A warning at most once an hour per task: never ten of one text in 30 minutes, so never an error alert."""
        try:
            clock = float(self.house.clock())
            if clock - self._warned.get(task, float("-inf")) < WARN_EVERY:
                return
            self._warned[task] = clock
            self._warnings += 1
            what = exc if isinstance(exc, str) else f"{type(exc).__name__}: {str(exc)[:200]}"
            self.house.alert("warning", f"the event lane's {task} failed ({what}); it is tried again on its schedule "
                                        "(league/events/house.py)")
        except Exception:  # noqa: BLE001 - a warning that cannot be written costs nothing more
            pass

    def _info(self, text: str) -> None:
        try:
            self.house.alert("info", text)
        except Exception:  # noqa: BLE001
            pass

    def _tell_stopped(self) -> None:
        if not self._stop_told:
            self._stop_told = True
            self._info(f"the event lane is stopped by {self.root / STOP_FILE}; it records, decides and asks nothing "
                       "until the file is removed")

    def _tell_waiting(self) -> None:
        if not self._waiting_told:
            self._waiting_told = True
            self._info(f"the event lane is switched on and waits for its store at {self.root} (scripts/evl_migrate.py "
                       "copies the desktop's there); it records nothing until then")

    # -- one turn ---------------------------------------------------------------------------------------------------
    def run(self) -> None:
        """One turn: the single most urgent due task, bounded. Never raises (a failure is `warn`'s)."""
        with self._lock:
            if self._running is not None:
                return
            self._running = "planning"
        began = self._mono()
        name = "turn"
        next_look = self.house.clock() + WAIT_LOOK
        try:
            if not self.ready():
                return
            with S.Store(self.root) as st:
                if not self._started_told:
                    self._started_told = True
                    self._info(f"the event lane runs on the House: store {self.root} (league/events/house.py)")
                now = self.now()
                self._maintain(st, now)
                task, _ = self._plan(st, now)
                if task is not None:
                    name = task.name
                    with self._lock:
                        self._running = name
                    status, summary = self._do(st, task)
                    self._note(name, status, summary, began)
                now = self.now()
                follow, at = self._plan(st, now)
                next_look = self.house.clock() if follow is not None else \
                    self.house.clock() + max(0.0, (at - now).total_seconds())
        except Exception as exc:  # noqa: BLE001 - a turn's failure is a warning, never the tick's
            self._failed[name] = self.now()
            self._note(name, "failed", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, began)
            self.warn(name, exc)
        finally:
            with self._lock:
                self._running = None
                self._next_look = next_look
            self._write_health()

    def _do(self, st: S.Store, task: Task) -> tuple[str, dict[str, Any]]:
        """Run `task` under its bound; its Claude calls are counted into a `verdicts` receipt."""
        now = self.now()
        deadline = self._deadline(st, now, task)
        gw = LaneGateway(self.gateway(), self, deadline, cut=task.cut)
        self._paused = bool(self._house_paused())
        self._spend_today(st, now)
        ctx = LaneContext(self, st, gw, self._sec_for(deadline, task.cut), self.now)
        try:
            out = task.run(ctx, deadline) or {}
            status = str(out.pop("_status", "ok"))
        except LaneDeadline as exc:
            out, status = {"cut": str(exc)[:200]}, "cut"
        finally:
            self._verdict_receipt(st, task.name, gw)
        return status, out

    def _house_paused(self) -> Any:
        paused = getattr(self.house, "paused", None)
        try:
            return paused() if callable(paused) else None
        except Exception:  # noqa: BLE001 - an unreadable PAUSE file pauses nothing new here
            return None

    def _deadline(self, st: S.Store, now: dt.datetime, task: Task) -> float | None:
        if task.budget is None:
            return None
        bound = float(task.budget)
        if not task.name.startswith("decide"):
            nxt = self._next_decision(st, now)
            if nxt is not None:
                bound = min(bound, max(1.0, (nxt - now).total_seconds() - DECISION_MARGIN))
        return self._mono() + bound

    def _note(self, name: str, status: str, summary: Mapping[str, Any], began: float) -> None:
        row = {"at": S.iso(self.now()), "status": status, "seconds": round(self._mono() - began, 3)}
        brief = {k: v for k, v in summary.items() if isinstance(v, (int, float, str, bool)) or v is None}
        with self._lock:
            self._tasks[name] = row | ({"summary": brief} if brief else {})
            self._last = {"task": name, **row}

    def _verdict_receipt(self, st: S.Store, task: str, gw: LaneGateway) -> None:
        """A `verdicts` receipt for every task that asked: asked, answered, refused, failed and each kind of the lane's
        own refusal (WP2's evl_verdicts reads the day's)."""
        if not gw.counts:
            return
        try:
            rid = st.start_receipt("verdicts", now=self.now())
            st.finish_receipt(rid, "ok", {"task": task, **dict(gw.counts)}, now=self.now())
        except Exception:  # noqa: BLE001 - the counts are a report, never the task's outcome
            pass

    def _write_health(self) -> None:
        if not self._ready:
            return
        try:
            path = self.root / HEALTH_FILE
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(self.health(), sort_keys=True, default=str) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        except Exception:  # noqa: BLE001
            pass

    # -- the calendar ----------------------------------------------------------------------------------------------
    def _maintain(self, st: S.Store, now: dt.datetime) -> None:
        """The NYSE calendar from Alpaca, about once a day and whenever it does not reach 30 days ahead."""
        last = st.meta("evl:lane:sessions_at")
        tried = self._attempts.get("sessions")
        today = now.astimezone(C.NY).date()
        row = st.db.execute("SELECT max(day) FROM sessions").fetchone()
        short = row[0] is None or dt.date.fromisoformat(row[0]) < today + dt.timedelta(days=30)
        stale = last is None or now - S.parse_iso(last) >= CALENDAR_EVERY
        if not (short or stale) or (tried is not None and now - tried < CALENDAR_RETRY):
            return
        self._attempts["sessions"] = now
        gw = LaneGateway(self.gateway(), self, None, cut=False)
        try:
            n = C.refresh(st, gw, today - CALENDAR_BACK, today + CALENDAR_AHEAD)
            st.set_meta("evl:lane:sessions_at", S.iso(now))
            self._note("sessions", "ok", {"sessions": n}, self._mono())
        except Exception as exc:  # noqa: BLE001 - the stored calendar serves until the next try
            self._note("sessions", "failed", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, self._mono())
            self.warn("calendar refresh", exc)

    def _next_decision(self, st: S.Store, now: dt.datetime) -> dt.datetime | None:
        today = now.astimezone(C.NY).date()
        for s in C.sessions(st, today, today + dt.timedelta(days=10)):
            for at in (s.open_decide, s.close_decide + CLOSE_GRACE):
                if at > now:
                    return at
        return None

    # -- the plan ---------------------------------------------------------------------------------------------------
    def _plan(self, st: S.Store, now: dt.datetime) -> tuple[Task | None, dt.datetime]:
        """The most urgent due task (or None) and, when there is none, when to look again."""
        soon: list[dt.datetime] = [now + IDLE_LOOK]
        today = now.astimezone(C.NY).date()
        session = C.session(st, today)
        latest = self._decide_receipts(st, now)
        if now >= self._redecide_next:
            self._refill_redecide(st, now, today, latest)
        last_record = self._last_started(st, "record")
        record_due = last_record is None or now >= last_record + RECORD_EVERY
        # a backlog (missed decisions, a long verdict queue) never starves the record pass past a second cadence
        starved = record_due and (last_record is None or now >= last_record + 2 * RECORD_EVERY) and \
            not self._quiet("record", now, [])
        decision = self._due_decision(st, now, latest, soon)
        if decision is not None and (decision[0] == 0 or (decision[0] < 3 and not starved)):
            return self._decision_task(decision), now
        urgent, early = self._verdict_targets(st, now, today, session, latest, soon)
        if urgent is not None and not starved:
            kind, day, live = urgent
            return Task("verdicts", lambda ctx, deadline: self._verdicts(ctx, kind, day, live), VERDICT_BUDGET,
                        cut=True), now
        if not record_due:
            soon.append(last_record + RECORD_EVERY)
        elif not self._quiet("record", now, soon):
            return Task("record", self._record, RECORD_BUDGET), now
        if decision is not None and decision[0] < 3:   # the record pass could not run (it failed lately)
            return self._decision_task(decision), now
        if urgent is not None:
            kind, day, live = urgent
            return Task("verdicts", lambda ctx, deadline: self._verdicts(ctx, kind, day, live), VERDICT_BUDGET,
                        cut=True), now
        if decision is not None:   # the hourly re-decision, and the backfill's: after the record pass
            return self._decision_task(decision), now
        nightly = self._nightly(st, now, today, session, soon)
        if nightly is not None:
            return nightly, now
        if self._tickers_due(st, now, today, soon) and not self._quiet("tickers", now, soon):
            return Task("tickers", self._snapshot, None), now
        if early is not None:
            kind, day, live = early
            return Task("verdicts", lambda ctx, deadline: self._verdicts(ctx, kind, day, live), VERDICT_BUDGET,
                        cut=True), now
        backfill = self._backfill_due(st, now, today, soon)
        if backfill is not None and not self._quiet("backfill", now, soon):
            return Task("backfill", lambda ctx, deadline: self._backfill(ctx, backfill, deadline), BACKFILL_BUDGET), now
        return None, min(soon)

    def _decision_task(self, decision: tuple[int, dt.datetime, str, dt.date, bool]) -> Task:
        _, _, kind, day, live = decision
        return Task(f"decide-{kind}", lambda ctx, deadline: self._decide(ctx, kind, day, live), DECIDE_BUDGET, cut=True)

    def _quiet(self, name: str, now: dt.datetime, soon: list[dt.datetime]) -> bool:
        """True while task `name` failed less than FAIL_BACKOFF ago (a failing task never retries every minute)."""
        at = self._failed.get(name)
        if at is not None and now < at + FAIL_BACKOFF:
            soon.append(at + FAIL_BACKOFF)
            return True
        return False

    def _decide_receipts(self, st: S.Store, now: dt.datetime) -> dict[str, tuple[str, dt.datetime]]:
        """job -> (status, started_at) of each decision's latest receipt in the look-back."""
        since = S.iso(now - LOOKBACK - dt.timedelta(days=1))
        out: dict[str, tuple[str, dt.datetime]] = {}
        for row in st.db.execute("SELECT job, status, started_at FROM receipts WHERE job LIKE 'decide-%' AND started_at>=? "
                                 "ORDER BY id", (since,)):
            out[str(row["job"])] = (str(row["status"] or ""), S.parse_iso(row["started_at"]))
        return out

    def _decision_times(self, st: S.Store, first: dt.date, last: dt.date) -> Iterable[tuple[C.Session, str, dt.datetime, dt.datetime]]:
        """(session, kind, scheduled time, the time it is run from) for every decision of the sessions in [first, last],
        and PREREG-EVL-4's rows' own decision (`FOUR_KIND`) of each close that waits for it (`_four`)."""
        for s in C.sessions(st, first, last):
            yield s, "open", s.open_decide, s.open_decide
            yield s, "close", s.close_decide, s.close_decide + CLOSE_GRACE
            if s.day in self._four:
                yield s, FOUR_KIND, s.close_decide, s.close_decide + CLOSE_GRACE

    def _refill_redecide(self, st: S.Store, now: dt.datetime, today: dt.date,
                         latest: Mapping[str, tuple[str, dt.datetime]] | None = None) -> None:
        """Once an hour: the last REDECIDE_SESSIONS sessions' decisions again (late events still get their decision).

        Then PREREG-EVL-4'S ROWS (release 1019c's review): every older close since its registration, back to LOOKBACK,
        that a release without its rows decided last (league/events/screen.py `made_without`) gets their own decision,
        `FOUR_KIND`, once, as a backfill: release 1019b's closes from 16:01:05Z Oct 19 to this release's deploy that
        the hourly re-decision no longer reaches. A close it still reaches is decided again whole by it, and a close
        whose latest decision is pending is decided again whole by its retry: each names their rows then. One decided
        by themselves and then again by such a release (stale) is decided again."""
        self._redecide_next = now + REDECIDE_EVERY
        start = P.registered().astimezone(C.NY).date()
        due = [s for s in C.sessions(st, max(start, today - dt.timedelta(days=14)), today) if s.open_decide <= now]
        recent = due[-REDECIDE_SESSIONS:]
        for s in recent:
            self._redecide.add(("open", s.day))
            if s.close_decide + CLOSE_GRACE <= now:
                self._redecide.add(("close", s.day))
        reached = {s.day for s in recent}
        latest = self._decide_receipts(st, now) if latest is None else latest
        four: set[dt.date] = set()
        for day, stale in SN.made_without(st, today, first=(now - LOOKBACK).astimezone(C.NY).date()).items():
            status = latest.get(f"decide-close:{day.isoformat()}", (None, None))[0]
            if day in reached or status != "ok":
                continue
            four.add(day)
            if stale:
                self._redecide.add((FOUR_KIND, day))
        self._four = four

    def _due_decision(self, st: S.Store, now: dt.datetime, latest: Mapping[str, tuple[str, dt.datetime]],
                      soon: list[dt.datetime]) -> tuple[int, dt.datetime, str, dt.date, bool] | None:
        """The most urgent decision: (0) a live one (within LIVE_WITHIN of its time) not yet made, (1) a missed one, oldest
        first, (2) one cut by the lane's bound, pending on verdicts or never finished, (3) the hourly re-decision (and
        the backfill's), which waits for the record pass. None when none is due."""
        today = now.astimezone(C.NY).date()
        start = max(P.registered().astimezone(C.NY).date(), (now - LOOKBACK).astimezone(C.NY).date())
        best: tuple[int, dt.datetime, str, dt.date, bool] | None = None
        for s, kind, scheduled, at in self._decision_times(st, start, today + dt.timedelta(days=7)):
            if at > now:
                soon.append(at)
                continue
            key = (kind, s.day)
            status, last = latest.get(f"decide-{kind}:{s.day.isoformat()}", (None, None))
            live = kind != FOUR_KIND and R.live_run(scheduled, now)   # PREREG-EVL-4's rows' own: always a backfill
            # (Release 1019b's second review: the receipt's own status first, then this lane's cut: a decision cut once
            # and failing since waits as a failed one does, never every turn.)
            if status is None:
                rank = 3 if kind == FOUR_KIND else (0 if live else 1)   # (a re-decision: after the record pass)
            elif status == "ok":
                if key not in self._redecide:
                    continue
                rank = 3
            elif status == "pending":
                look = self._looks.get(key)
                if look is not None and look.at >= last and look.missing == 0:
                    retry = now                      # every verdict it waited for is stored now: decide at once
                elif look is not None and look.stalled:
                    retry = max(last + PENDING_RETRY, look.at + VERDICT_BACKOFF)   # its verdicts get no answer
                else:
                    retry = last + PENDING_RETRY
                if now < retry:
                    soon.append(retry)
                    continue
                rank = 0 if live else 2
            elif status == "failed":   # a run that raised (`_decide`): again a minute later while live, else STALE_RETRY
                retry = last + (DECIDE_RETRY if live else STALE_RETRY)
                if now < retry:
                    soon.append(retry)
                    continue
                rank = 0 if live else 2
            elif key in self._cut:     # cut by this lane's bound: it goes on at once
                rank = 0 if live else 2
            else:  # 'running' (a run that never finished), 'cut' or anything else
                if last >= self._born and now < last + STALE_RETRY:
                    soon.append(last + STALE_RETRY)
                    continue
                rank = 0 if live else 2
            candidate = (rank, at, kind, s.day, live)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        return best

    def _decide(self, ctx: LaneContext, kind: str, day: dt.date, live: bool) -> dict[str, Any]:
        key = (kind, day)
        self._redecide.discard(key)
        before = self._stored_verdicts(ctx.store)
        try:
            if kind == "open":
                out = R.decide_open(ctx, day, backfill_run=not live)
            elif kind == FOUR_KIND:
                out = R.decide_close(ctx, day, backfill_run=True, evl4_only=True)
            else:
                out = R.decide_close(ctx, day, backfill_run=not live)
        except LaneDeadline:
            self._cut.add(key)
            self._close_running(ctx.store, f"decide-{kind}:{day.isoformat()}", "the lane's time bound; it goes on next turn")
            raise
        except Exception as exc:
            # (Release 1019b's review: a run that raised, one gateway 429 in its eligibility reads say, was left
            # `running` and waited STALE_RETRY, past LIVE_WITHIN: the session's live decision became a backfill. It is
            # closed `failed` and tried again after DECIDE_RETRY, live while within LIVE_WITHIN; it is no longer a cut
            # one, whatever it was before: the second review.)
            self._cut.discard(key)
            self._close_running(ctx.store, f"decide-{kind}:{day.isoformat()}",
                                f"{type(exc).__name__}: {str(exc)[:160]}", status="failed")
            raise
        self._cut.discard(key)
        missing = sum((out.get("pending") or {}).values())
        self._look(key, missing, self._stored_verdicts(ctx.store) - before, ctx.gw)
        return {"day": day.isoformat(), "live": live, "pending": missing,
                "_status": "pending" if out.get("pending") else "ok"}

    @staticmethod
    def _close_running(st: S.Store, job: str, why: str, *, status: str = "cut") -> None:
        row = st.db.execute("SELECT id FROM receipts WHERE job=? AND status='running' ORDER BY id DESC LIMIT 1",
                            (job,)).fetchone()
        if row is not None:
            st.finish_receipt(int(row["id"]), status, {"why": why})

    # -- verdicts ---------------------------------------------------------------------------------------------------
    def _verdict_targets(self, st: S.Store, now: dt.datetime, today: dt.date, session: C.Session | None,
                         latest: Mapping[str, tuple[str, dt.datetime]], soon: list[dt.datetime]
                         ) -> tuple[tuple[str, dt.date, bool] | None, tuple[str, dt.date, bool] | None]:
        """(urgent, early), each (kind, day, live) or None: a decision within URGENT_BEFORE of its time or pending, and
        today's next one before that (from 07:30 ET), only while its verdicts may still be missing."""
        urgent = early = None
        if session is not None:
            ready = session.at(UNIVERSE_AT)
            for kind, decide_at in (("open", session.open_decide), ("close", session.close_decide)):
                status = latest.get(f"decide-{kind}:{today.isoformat()}", (None, None))[0]
                if status == "ok":
                    continue
                if now < ready:
                    soon.append(ready)
                    continue
                if not self._verdicts_due((kind, today), now, soon, fresh=True):
                    continue
                live = R.live_run(decide_at, now)
                if status == "pending" or now >= decide_at - URGENT_BEFORE:
                    urgent = urgent or (kind, today, live)
                else:
                    early = early or (kind, today, live)
                    soon.append(decide_at - URGENT_BEFORE)
        if urgent is None:
            pending = sorted((dt.date.fromisoformat(job.split(":", 1)[1]), job[len("decide-"):].split(":", 1)[0])
                             for job, (status, _) in latest.items() if status == "pending")
            for day, kind in pending:
                if kind == FOUR_KIND and day not in self._four:
                    continue    # (its close was decided again whole since: that decision's own wait is the one read)
                if day != today and self._verdicts_due((kind, day), now, soon, fresh=False):
                    urgent = (kind, day, False)
                    break
        return urgent, early

    def _verdicts_due(self, key: tuple[str, dt.date], now: dt.datetime, soon: list[dt.datetime], *, fresh: bool) -> bool:
        look = self._looks.get(key)
        if look is None or (fresh and self._events_at > look.at):
            return True
        if look.missing == 0:
            return False
        if look.stalled and now < look.at + VERDICT_BACKOFF:
            soon.append(look.at + VERDICT_BACKOFF)
            return False
        return True

    def _verdicts(self, ctx: LaneContext, kind: str, day: dt.date, live: bool) -> dict[str, Any]:
        """Every verdict the `kind` decision of session `day` will read, asked now: league.events.run's own decision
        code with `ask_only` (no intent, no receipt), so what is stored is what the decision reads. A close decision
        that waits on verdicts only the session's OPEN decision asks (PREREG-EVL-4's EVL-NEWSPM-READ-ON and its control
        read EVL-NEWS-READ-O1's PROMPT-NEWS verdicts and ask none of their own: `run.waits_on_open`) has that open
        decision's own asks made now (`decide_open` with `ask_only`), then is counted again: such a wait is never left
        to the hourly re-decision."""
        key = (kind, day)
        before = self._stored_verdicts(ctx.store)
        gw = ctx.gw
        if kind == "open":
            decide = R.decide_open
        elif kind == FOUR_KIND:     # PREREG-EVL-4's rows' own decision (a backfill): their verdicts alone
            def decide(ctx: Any, day: dt.date, *, backfill_run: bool, ask_only: bool) -> dict[str, Any]:
                return R.decide_close(ctx, day, backfill_run=True, ask_only=ask_only, evl4_only=True)
        else:
            decide = R.decide_close
        try:
            out = decide(ctx, day, backfill_run=not live, ask_only=True)
            if kind in ("close", FOUR_KIND) and R.waits_on_open(out):
                session = C.session(ctx.store, day)
                opened = R.live_run(session.open_decide, ctx.now()) if session is not None else False
                R.decide_open(ctx, day, backfill_run=not opened, ask_only=True)
                out = decide(ctx, day, backfill_run=not live, ask_only=True)
        except LaneDeadline:
            had = self._looks.get(key)
            self._looks[key] = VerdictLook(self.now(), max(1, had.missing if had else 1), False)
            raise
        except Exception:
            had = self._looks.get(key)
            self._looks[key] = VerdictLook(self.now(), max(1, had.missing if had else 1), True)
            raise
        missing = sum((out.get("pending") or {}).values())
        stored = self._stored_verdicts(ctx.store) - before
        stalled = self._look(key, missing, stored, gw)
        if gw.counts.get("cut_cap"):
            self.warn("verdict line", f"the day's ${self._line['usd_day']:.2f} line for verdicts is reached "
                                      f"({self._line['source']}); READ events wait for the next day's")
        if kind != FOUR_KIND and day not in self._universe_told and isinstance(out.get("events"), Mapping):
            self._universe_told.add(day)
            self._receipted(ctx.store, "universe", "ok", {"day": day.isoformat(), "decision": kind,
                                                          **dict(out["events"])})
        return {"day": day.isoformat(), "decision": kind, "missing": missing, "stored": stored, "stalled": stalled}

    def _look(self, key: tuple[str, dt.date], missing: int, stored: int, gw: LaneGateway) -> bool:
        """Note what a decision's verdicts look like now; True (stalled) when some are missing, none was stored and
        the calls got no answer (refused, failed, the House paused, the day's line) rather than running out of time,
        or no call was made at all (every missing verdict is one this pass does not ask: PREREG-EVL-4's PM rows wait on
        the open decision's asks), so the same pass would only find them missing again: then neither the verdict task
        nor the pending decision asks again for VERDICT_BACKOFF."""
        cut_time = gw.counts.get("cut_deadline", 0) + gw.counts.get("cut_closed", 0)
        no_answer = (gw.counts.get("refused", 0) + gw.counts.get("failed", 0) + gw.counts.get("cut_paused", 0)
                     + gw.counts.get("cut_cap", 0))
        asked = gw.counts.get("asked", 0) + sum(n for k, n in gw.counts.items() if str(k).startswith("cut_"))
        stalled = missing > 0 and stored == 0 and cut_time == 0 and (no_answer > 0 or asked == 0)
        self._looks[key] = VerdictLook(self.now(), missing, stalled)
        return stalled

    @staticmethod
    def _stored_verdicts(st: S.Store) -> int:
        return int(st.db.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0])

    # -- recording --------------------------------------------------------------------------------------------------
    def _last_started(self, st: S.Store, job: str) -> dt.datetime | None:
        row = st.db.execute("SELECT max(started_at) FROM receipts WHERE job=?", (job,)).fetchone()
        return S.parse_iso(row[0]) if row and row[0] else None

    def _record(self, ctx: LaneContext, deadline: float) -> dict[str, Any]:
        """EDGAR's current feeds (8-K and 4) and the news, bounded and resumable; then the next session's verdicts.

        Every new feed entry is stored at once as `listed` (so the next poll stops at it), then fetched oldest first,
        8-Ks before Form 4s, while the bound lasts: a pass cut short leaves `listed` rows the next pass fetches. An
        unlisted filer's 8-K stays `listed`, as in league.events.run.record_pass."""
        st = ctx.store
        rid = st.start_receipt("record", now=ctx.now())
        try:
            out, new, cut = self._record_steps(ctx, deadline)
        except BaseException as exc:
            st.finish_receipt(rid, "failed", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, now=ctx.now())
            raise
        st.finish_receipt(rid, "ok", out, now=ctx.now())
        return {"new": new, "cut": cut}

    def _record_steps(self, ctx: LaneContext, deadline: float) -> tuple[dict[str, Any], int, bool]:
        st = ctx.store
        now = ctx.now()
        out: dict[str, Any] = {}
        try:
            listed: set[str] | None = set(ctx.tickers)
        except Exception as exc:  # noqa: BLE001 - no tickers copy at all (an empty store, SEC down): 8-Ks wait, the rest goes on
            listed = None
            out["tickers"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        new = 0
        for form in E.FORMS:
            known = [r[0] for r in st.db.execute("SELECT accession FROM filings WHERE form=? ORDER BY accepted_at DESC "
                                                 "LIMIT 2000", (form,))]
            try:
                entries = E.poll_current(ctx.sec, form, known)
            except LaneDeadline:
                raise
            except Exception as exc:  # noqa: BLE001 - one feed's outage never stops the other or the news
                out[form] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
                continue
            with st.tx():   # listed at once, in one commit (record_filing with fetch=False only inserts)
                for entry in entries:
                    E.record_filing(st, ctx.sec, entry, source="current", now=ctx.now(), fetch=False)
            out[form] = {"new": len(entries), "fetched": 0, "failed": 0, "unlisted": 0}
        out["news"] = self._news(ctx, min(deadline, self._mono() + NEWS_BUDGET))
        new += int((out["news"] or {}).get("stored") or 0)
        cut = False
        # The listed filings, and those whose fetch FAILED (release 1019b's review: one transient SEC error lost the
        # filing's live decision, as nothing fetched it again before the next day's daily-index backfill), each tried
        # again FETCH_BACKOFF after its first failure, FETCH_TRIES tries in all (`_fetch_tries`, kept by this process);
        # new ones first. (A form whose feed failed this pass holds its error in `out`: its counts go beside it, the
        # second review's KeyError.)
        rows = st.db.execute("SELECT accession, form, cik, company, items, accepted_at, index_url, status FROM filings "
                             "WHERE (status='listed' OR status LIKE 'failed:%') AND source='current' AND received_at>=? "
                             "ORDER BY form='4', status!='listed', accepted_at, accession",
                             (S.iso(now - FETCH_WINDOW),)).fetchall()

        def bump(counts: dict[str, Any], key: str) -> None:
            counts[key] = int(counts.get(key) or 0) + 1

        for row in rows:
            counts = out.setdefault(str(row["form"]), {"new": 0, "fetched": 0, "failed": 0, "unlisted": 0})
            if row["form"] == "8-K" and (listed is None or row["cik"] not in listed):
                bump(counts, "unlisted" if listed is not None else "waiting")
                continue
            accession = str(row["accession"])
            again = str(row["status"]).startswith("failed")
            tries, first = self._fetch_tries.get(accession, (1 if again else 0, None))
            if again and tries >= FETCH_TRIES:
                continue    # (left to the daily-index backfill)
            if again and first is not None and now < first + FETCH_BACKOFF[tries - 1]:
                continue    # (its next try is not due yet: the tries-th after the first failure)
            if self.late(deadline):
                cut = True
                break
            self._fetch_tries[accession] = (tries + 1, first or now)    # (counted before it is tried: a raise counts)
            entry = {"form": row["form"], "cik": row["cik"], "accession": row["accession"], "company": row["company"],
                     "items": json.loads(row["items"] or "[]"), "accepted_at": S.parse_iso(row["accepted_at"]),
                     "index_url": row["index_url"]}
            status = E.record_filing(st, ctx.sec, entry, source="current", now=ctx.now(), fetch=True)
            if again:
                bump(counts, "retried")
            if status == "fetched":
                bump(counts, "fetched")
                new += 1
                self._fetch_tries.pop(accession, None)
            elif status.startswith("failed"):
                bump(counts, "failed")
        out["cut"] = cut
        if new:
            self._events_at = self.now()
        out["verdicts"] = self._verdict_step(ctx, deadline)
        return out, new, cut

    def _news(self, ctx: LaneContext, deadline: float) -> dict[str, Any]:
        """New Alpaca news since the newest stored (less 5 minutes), oldest first, page by page until `deadline`: a
        pass cut short has stored its pages, and the next goes on from the newest."""
        st = ctx.store
        gw = LaneGateway(ctx.gw.inner, self, deadline, cut=True)
        try:
            since = N.latest_created(st) or (ctx.now() - dt.timedelta(hours=2))
            return dict(N.record(st, gw, since - dt.timedelta(minutes=5), ctx.now(), now=ctx.now()))
        except LaneDeadline:
            return {"cut": True}
        except Exception as exc:  # noqa: BLE001 - the news failing never stops the filings
            return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}

    def _verdict_step(self, ctx: LaneContext, deadline: float) -> list[dict[str, Any]]:
        """The record pass's last step: today's verdicts with the time left, once its universe is fixed (07:30 ET):
        its open decision's until that is made, then its close decision's."""
        out: list[dict[str, Any]] = []
        now = ctx.now()
        today = now.astimezone(C.NY).date()
        session = C.session(ctx.store, today)
        if session is None or now < session.at(UNIVERSE_AT):
            return out
        latest = self._decide_receipts(ctx.store, now)
        for kind, decide_at in (("open", session.open_decide), ("close", session.close_decide)):
            if deadline - self._mono() < VERDICT_STEP_MIN:
                break
            if latest.get(f"decide-{kind}:{today.isoformat()}", (None,))[0] == "ok":
                continue
            if not self._verdicts_due((kind, today), now, [], fresh=True):
                continue
            # its reads stop at the pass's bound too (the eligibility it reads is kept as it is read)
            step = LaneGateway(ctx.gw.inner, self, deadline, cut=True)
            bounded = LaneContext(self, ctx.store, step, self._sec_for(deadline, True), self.now)
            try:
                out.append(self._verdicts(bounded, kind, today, R.live_run(decide_at, now)))
            except LaneDeadline:
                out.append({"decision": kind, "cut": True})
                break
            except Exception as exc:  # noqa: BLE001 - the record pass is the feeds': its verdict step never fails it
                # (Release 1019b's third review: an Alpaca outage in the eligibility it reads, or an empty asset list,
                # failed the whole record pass, and FAIL_BACKOFF then cut EDGAR's and the news' polling from every 2
                # minutes to every 10. `_verdicts` marks the decision's verdicts stalled, so they wait VERDICT_BACKOFF by
                # themselves; the pass goes on to the other decision and ends ok.)
                out.append({"decision": kind, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
                self.warn("record pass's verdict step", exc)
            finally:
                ctx.gw.counts.update(step.counts)
        return out

    # -- nightly ----------------------------------------------------------------------------------------------------
    def _nightly(self, st: S.Store, now: dt.datetime, today: dt.date, session: C.Session | None,
                 soon: list[dt.datetime]) -> Task | None:
        evening = _wall(today, SCORE_AT)
        if session is not None:
            close_after = session.close_at + EQUITY_AFTER
            if st.meta(SC.equity_key(today)) is None:
                if now < close_after:
                    soon.append(close_after)
                elif self._retry_ok("equity", now, EQUITY_RETRY, soon) and not self._quiet("equity", now, soon):
                    return Task("equity", self._equity, None)
            if now < evening:
                soon.append(evening)
            else:
                if not self._receipt_since(st, "score", evening, status="ok"):
                    if not self._quiet("score", now, soon):
                        return Task("score", self._score, SCORE_BUDGET)
                    return None
                if not self._receipt_since(st, "screen", evening):
                    if not self._quiet("screen", now, soon):
                        return Task("screen", self._screen, None)
                    return None
        report_at = evening if session is not None else _wall(today, REPORT_AT)
        if now < report_at:
            soon.append(report_at)
        elif (session is None or self._receipt_since(st, "screen", evening)) and \
                not (st.root / "reports" / f"{today.isoformat()}.txt").exists() and \
                not self._quiet("report", now, soon):
            return Task("report", self._report, None)
        return None

    def _retry_ok(self, what: str, now: dt.datetime, every: dt.timedelta, soon: list[dt.datetime]) -> bool:
        tried = self._attempts.get(what)
        if tried is not None and now < tried + every:
            soon.append(tried + every)
            return False
        return True

    @staticmethod
    def _receipt_since(st: S.Store, job: str, since: dt.datetime, *, status: str | None = None) -> bool:
        sql = "SELECT 1 FROM receipts WHERE job=? AND started_at>=?" + (" AND status=?" if status else "") + " LIMIT 1"
        args: tuple[Any, ...] = (job, S.iso(since)) + ((status,) if status else ())
        return st.db.execute(sql, args).fetchone() is not None

    def _receipted(self, st: S.Store, job: str, status: str, summary: Mapping[str, Any]) -> None:
        rid = st.start_receipt(job, now=self.now())
        st.finish_receipt(rid, status, summary, now=self.now())

    def _equity(self, ctx: LaneContext, deadline: float | None) -> dict[str, Any]:
        self._attempts["equity"] = ctx.now()
        out = SC.record_equity(ctx.store, ctx.gw, now=ctx.now())
        self._receipted(ctx.store, "equity", "ok", {k: v for k, v in out.items() if k != "equity"})
        return {k: v for k, v in out.items() if k != "equity"}

    def _score(self, ctx: LaneContext, deadline: float) -> dict[str, Any]:
        """The score job (league.events.score.settle), resumable: each due intent is tried once a night, in order,
        while the bound lasts; the night's pass is `ok` once every one has been tried."""
        st, now = ctx.store, ctx.now()
        day = now.astimezone(C.NY).date()
        for other in [d for d in self._score_seen if d != day]:
            self._score_seen.pop(other)
        seen = self._score_seen.setdefault(day, set())
        counts = {"due": 0, "settled": 0, "skipped": 0, "waiting": 0, "errors": 0}
        errors: list[str] = []
        complete = True
        for intent in SC.due(st, now):
            key = (str(intent["program"]), int(intent["version"]), str(intent["event"]))
            if key in seen:
                continue
            if self.late(deadline):
                complete = False
                break
            seen.add(key)
            counts["due"] += 1
            try:
                status = SC.settle_one(st, ctx.gw, intent, now=now)
            except Exception as exc:  # noqa: BLE001 - one intent's failure is its own (as score.settle)
                counts["errors"] += 1
                errors.append(f"{key[0]}:{key[2]}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            counts[status.split(":")[0]] = counts.get(status.split(":")[0], 0) + 1
        summary = {"day": day.isoformat(), "complete": complete, **counts, "errors_seen": errors[:5]}
        self._receipted(st, "score", "ok" if complete else "partial", summary)
        if errors:
            self.warn("score", f"{len(errors)} intents could not be settled this pass, the first: {errors[0]}")
        return summary | {"_status": "ok" if complete else "partial"}

    def _screen(self, ctx: LaneContext, deadline: float | None) -> dict[str, Any]:
        """The screen (league.events.screen.run: the looks, and the band moves a look makes in its own transaction:
        Probe, retired), then PREREG-EVL-3's review of the real fills the House's book wrote back
        (league.events.bands.review: demotion to learning, Sized), WHATEVER THE SCREEN DID (release 1019b's review: a
        failing look stopped every program's demotion and Sized). A program whose looks failed, or a review that failed,
        is a warning and the screen's receipt says so (`partial`); it runs again next night."""
        now = ctx.now()
        try:
            out = SN.run(ctx.store, now.astimezone(C.NY).date(), now=now)
        except Exception as exc:  # noqa: BLE001 - the review below runs all the same
            out = {"written": [], "waiting": [], "errors": [{"error": f"{type(exc).__name__}: {str(exc)[:200]}"}]}
        summary: dict[str, Any] = {"day": now.astimezone(C.NY).date().isoformat(),
                                   "written": len(out.get("written") or []), "waiting": len(out.get("waiting") or [])}
        status = "ok"
        if out.get("errors"):
            status = "partial"
            summary["errors"] = list(out["errors"])[:5]
            self.warn("screen", f"{len(out['errors'])} program(s) could not be screened, the first: {out['errors'][0]}")
        try:
            moved = BA.review(ctx.store, now=now)
        except Exception as exc:  # noqa: BLE001 - the looks are written; the review is read again next night
            status = "partial"
            summary["review"] = f"failed: {type(exc).__name__}: {str(exc)[:160]}"
            self.warn("bands", exc)
        else:
            summary["review"] = [{k: c.get(k) for k in ("program", "version", "band")} for c in moved]
        self._receipted(ctx.store, "screen", status, summary)
        return summary | {"_status": status}

    def _report(self, ctx: LaneContext, deadline: float | None) -> dict[str, Any]:
        """The daily one-screen report into `<root>/reports/<day>.txt` and `.json`, as the CLI's `report` writes it."""
        now = ctx.now()
        day = now.astimezone(C.NY).date()
        rep = RP.build(ctx.store, day, now=now)
        folder = ctx.store.root / "reports"
        folder.mkdir(exist_ok=True)
        (folder / f"{day.isoformat()}.json").write_text(json.dumps(rep, default=str, sort_keys=True), encoding="utf-8")
        (folder / f"{day.isoformat()}.txt").write_text(RP.render(rep) + "\n", encoding="utf-8")
        self._receipted(ctx.store, "report", "ok", {"day": day.isoformat()})
        return {"day": day.isoformat()}

    # -- the ticker snapshot ----------------------------------------------------------------------------------------
    def _tickers_due(self, st: S.Store, now: dt.datetime, today: dt.date, soon: list[dt.datetime]) -> bool:
        at = _wall(today, TICKERS_AT)
        if today.weekday() >= 5:
            soon.append(_wall(today + dt.timedelta(days=7 - today.weekday()), TICKERS_AT))
            return False
        if now < at:
            soon.append(at)
            return False
        if st.db.execute("SELECT 1 FROM meta WHERE key>=? AND key<? LIMIT 1",
                         (f"tickers@{S.iso(at)}", "tickers@~")).fetchone() is not None:
            return False
        return self._retry_ok("tickers", now, TICKERS_RETRY, soon)

    def _snapshot(self, ctx: LaneContext, deadline: float | None) -> dict[str, Any]:
        self._attempts["tickers"] = ctx.now()
        sha = ctx.snapshot_tickers()
        self._receipted(ctx.store, "tickers", "ok", {"sha": sha})
        return {"sha": sha}

    # -- the backfill -----------------------------------------------------------------------------------------------
    def _backfill_due(self, st: S.Store, now: dt.datetime, today: dt.date, soon: list[dt.datetime]) -> dt.date | None:
        start = P.registered().astimezone(C.NY).date()
        day, days = today, []
        while len(days) < BACKFILL_WEEKDAYS:
            day -= dt.timedelta(days=1)
            if day.weekday() < 5:
                days.append(day)
        for day in sorted(days):
            if day < start or st.meta(f"evl:backfill:{day.isoformat()}") == "done":
                continue
            at = _wall(day + dt.timedelta(days=1), BACKFILL_AT)
            if now < at:
                soon.append(at)
                continue
            wait = self._backfill_wait.get(day)
            if wait is not None and now < wait:   # only failed filings left, their next try not due: a later day goes on
                soon.append(wait)
                continue
            if self._retry_ok(f"backfill:{day.isoformat()}", now, BACKFILL_RETRY, soon):
                return day
        return None

    def _backfill(self, ctx: LaneContext, day: dt.date, deadline: float) -> dict[str, Any]:
        """Every 8-K (of a listed filer) and Form 4 in EDGAR's daily index of `day` that the store has not fetched,
        fetched now (league.events.run.backfill, bounded and resumable); the sessions they enter are decided again."""
        st = ctx.store
        if day not in self._index_rows:
            try:
                self._index_rows[day] = E.parse_daily_index(ctx.sec(E.daily_index_url(day)), E.FORMS)
            except G.GatewayError as exc:
                holiday = SEC_HOLIDAYS.get(day)
                if getattr(exc, "status", None) == 404 and holiday is not None:   # EDGAR was closed: no index, ever
                    st.set_meta(f"evl:backfill:{day.isoformat()}", "done")
                    summary = {"day": day.isoformat(), "complete": True, "why": SEC_HOLIDAY_WHY, "holiday": holiday}
                    self._receipted(st, "backfill", "ok", summary)
                    return summary | {"_status": "ok"}
                # not published yet: tried again within the hour, said in the receipt
                self._attempts[f"backfill:{day.isoformat()}"] = ctx.now()
                self._receipted(st, "backfill", "waiting", {"day": day.isoformat(), "why": str(exc)[:120]})
                return {"day": day.isoformat(), "waiting": str(exc)[:120], "_status": "waiting"}
        rows = self._index_rows[day]
        seen = self._backfill_seen.setdefault(day, set())
        failed = self._backfill_failed.setdefault(day, {})
        now = ctx.now()
        listed = set(ctx.tickers)
        # ONE FILING, ONE ROW EACH FILER (A82): EDGAR's daily index lists a filing once per filer, so a Form 4 stands
        # under its issuer and its reporting owner and an 8-K under each co-registrant (Oct 19, 2026: 1,189 rows, 665
        # filings). The backfill goes filing by filing and is complete when every filing is seen; an 8-K is a listed
        # filer's when any of its filers is listed, under that filer's CIK (a Form 4's issuer is read from its document).
        filings: dict[str, dict[str, Any]] = {}
        for row in rows:
            first = filings.setdefault(row["accession"], row)
            if row["form"] == "8-K" and first["cik"] not in listed and row["cik"] in listed:
                filings[row["accession"]] = row
        # A FAILED FETCH IS NOT SEEN (release 1019f): a filing whose fetch failed is tried again FETCH_BACKOFF after its
        # first failure, FETCH_TRIES tries in all, across passes, as the record pass tries a live one (its own count:
        # `_backfill_failed`, kept by this process); the day is done only when every filing is fetched, known or
        # unlisted, or past its last try: those are named in the receipt (`unfetched`: accession, form, tries, error)
        # and the day is done with `failed` > 0, so one dead document never holds a look for good.
        counts = {"rows": len(rows), "filings": len(filings), "known": 0, "fetched": 0, "unlisted": 0, "retried": 0}
        entered: set[tuple[str, dt.date]] = set()
        cut = False
        for row in filings.values():
            accession = str(row["accession"])
            if accession in seen:
                continue
            if self.late(deadline):
                cut = True
                break
            if row["form"] == "8-K" and row["cik"] not in listed:
                seen.add(accession)
                counts["unlisted"] += 1
                continue
            have = st.db.execute("SELECT status FROM filings WHERE accession=?", (accession,)).fetchone()
            if have is not None and have["status"] == "fetched":   # (the record pass may have fetched a failed one)
                seen.add(accession)
                failed.pop(accession, None)
                counts["known"] += 1
                continue
            tried = failed.get(accession)
            if tried is not None and now < tried[1] + FETCH_BACKOFF[tried[0] - 1]:
                continue    # (its next try is not due yet: the tries-th after the first failure)
            status = E.record_filing(st, ctx.sec, row | {"accepted_at": None, "index_url": None, "items": []},
                                     source="daily-index", now=ctx.now(), fetch=True)
            if tried is not None:
                counts["retried"] += 1
            if status.startswith("failed"):
                tries = (tried[0] if tried is not None else 0) + 1
                failed[accession] = (tries, tried[1] if tried is not None else now, str(row["form"]), status)
                if tries >= FETCH_TRIES:
                    seen.add(accession)    # (past its last try: named below, the day goes on without it)
                continue
            seen.add(accession)
            failed.pop(accession, None)
            if status == "fetched":
                counts["fetched"] += 1
                entered |= self._entry_sessions(st, accession)
        retrying = {acc: f for acc, f in failed.items() if acc not in seen}
        complete = len(seen) >= len(filings)
        if complete:   # (a filing past its last try that the record pass has fetched since is not named)
            for acc in list(failed):
                have = st.db.execute("SELECT status FROM filings WHERE accession=?", (acc,)).fetchone()
                if have is not None and have["status"] == "fetched":
                    failed.pop(acc)
        today = ctx.now().astimezone(C.NY).date()
        self._redecide |= {(kind, session_day) for kind, session_day in entered if session_day <= today}
        summary = {"day": day.isoformat(), "complete": complete, **counts, "failed": len(failed),
                   "retrying": len(retrying), "redecide": len(entered)}
        next_try = min((f[1] + FETCH_BACKOFF[f[0] - 1] for f in retrying.values()), default=None)
        if next_try is not None:
            summary["next_try"] = S.iso(next_try)
        if complete and failed:
            summary["unfetched"] = [{"accession": acc, "form": f[2], "tries": f[0], "error": f[3][:120]}
                                    for acc, f in sorted(failed.items())]
        if complete:
            st.set_meta(f"evl:backfill:{day.isoformat()}", "done")
            self._index_rows.pop(day, None)
            self._backfill_seen.pop(day, None)
            self._backfill_failed.pop(day, None)
            self._backfill_wait.pop(day, None)
        elif next_try is not None and not cut:   # nothing left but failed filings: the day waits for the next try
            self._backfill_wait[day] = next_try
        else:                          # cut by its bound: the next turn goes on from what was seen
            self._backfill_wait.pop(day, None)
        status = ("done-failed" if failed else "ok") if complete else "partial"
        self._receipted(st, "backfill", status, summary)
        return summary | {"_status": status}

    @staticmethod
    def _entry_sessions(st: S.Store, accession: str) -> set[tuple[str, dt.date]]:
        row = st.db.execute("SELECT knowable_at FROM filings WHERE accession=?", (accession,)).fetchone()
        if row is None:
            return set()
        knowable = S.parse_iso(row["knowable_at"])
        out = set()
        first = C.first_open_entry(st, knowable)
        if first is not None:
            out.add(("open", first.day))
        close = C.first_close_decision(st, knowable)
        if close is not None:
            out.add(("close", close.day))
        return out


# ---------------------------------------------------------------------------------------------------- the hook
class LanePublisher:
    """`house.publisher`, wrapped: the original publisher's `publish(house)` exactly as before (its failure is still
    the House's "publishing failed" warning), then the lane's turn (`EventLane.turn`, which never raises). Every other
    attribute is the original publisher's."""

    def __init__(self, inner: Any, lane: EventLane):
        self.inner = inner
        self.lane = lane

    def publish(self, house: Any) -> None:
        try:
            if self.inner is not None:
                self.inner.publish(house)
        finally:
            self.lane.turn(house)

    def __getattr__(self, name: str) -> Any:
        inner = self.__dict__.get("inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)


def attach(house: Any, state_root: str | os.PathLike[str], config: Mapping[str, Any], *,
           token: Callable[[], str] | str) -> EventLane:
    """The lane on `house` (league/service.py, when `events_enabled(config)`): its store at `<state>/events/`, its
    gateway calls with the House's token source, `house.publisher` wrapped. `house.feeds` is left as it is (None)."""
    gateway = G.Gateway(token, url=str(config.get("gateway_url") or G.GATEWAY_URL))
    lane = EventLane(house, Path(state_root) / ROOT_NAME, gateway=gateway, settings=config.get("events") or {})
    house.publisher = LanePublisher(house.publisher, lane)
    return lane


def _wall(day: dt.date, at: dt.time) -> dt.datetime:
    return dt.datetime.combine(day, at, tzinfo=C.NY).astimezone(UTC)


def _iso_epoch(value: float) -> str | None:
    if value in (float("inf"), float("-inf")):
        return None
    try:
        return S.iso(dt.datetime.fromtimestamp(value, UTC))
    except (OverflowError, OSError, ValueError):
        return None


def verdict_day(now: dt.datetime) -> tuple[dt.date, tuple[str, str]]:
    """THE DAY THE LANE'S LINE IS HELD ON (the module docstring): the UTC day of `now` and its [00:00, 24:00) UTC as the
    store's strings, the day budget rule 3 holds every line on and the cap breach is judged on (league/ops/metered.py
    `day_bounds`)."""
    day = now.astimezone(UTC).date()
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=UTC)
    return day, (S.iso(start), S.iso(start + dt.timedelta(days=1)))


__all__ = ["EventLane", "LanePublisher", "LaneGateway", "LaneContext", "LaneCut", "LaneDeadline", "attach",
           "events_enabled", "verdict_day", "ROOT_NAME", "BACKGROUND_KEY"]
