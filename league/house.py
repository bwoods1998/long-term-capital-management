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
from . import allocator as allocator_module, capital, feeds as feeds_module, niches as niches_module
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


@dataclass
class Settings:
    """The House's own dials (not the game's, not the constitution's)."""

    tick_seconds: int = 60
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



def _replay_rules_key() -> str:
    """The replay gate's rules, hashed: a replay verdict is only as current as the rules it was reached under."""
    return hashlib.sha256(json.dumps(CONSTITUTION["ladder"]["replay"], sort_keys=True).encode()).hexdigest()[:16]

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
        self.provider = provider
        self.auditor = auditor
        self.publisher = publisher
        self.budget = budget
        self.merton: Any = None  # set by the service: Merton's pull-request roles, and the consultancy agents hire
        self.engineer: Any = None  # set by the service: the repair worklist's engineer (`league/engineer.py`)
        self.semantic_lab: Any = None
        self.options_history: Any = None  # set by the service: listed-option history (`league/options_history.py`)
        self.feeds: Any = None  # set by the service: scoreboards, perp funding, DVOL and settled funding (`league/feeds.py`)
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
            self.books[name] = Book(
                name, broker, self.ledger, fees=Fees(family_of(name)), real_money=real, clock=clock,
                market_open=market_hours, kill_switch=kill_switch,
                resolves_at=self._resolves_at if family_of(name) == "kalshi" else None,
                event_capital_budget=(lambda venue=family_of(name): self._event_capital_budget(venue)) if family_of(name) == 'kalshi' else None,
            )
        self._state_path = self.root / "house.json"
        self._state = self._load_state()
        self.niches = niches_module.load()
        for niche_id, live in (self._state.get("niche_live") or {}).items():
            if niche_id in self.niches:
                self.niches[niche_id].live = tuple(live)
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
                       "feeds": threading.Semaphore(1)}
        self._jobs: dict[str, threading.Thread] = {}
        self._job_status: dict[str, dict[str, Any]] = {}
        self._standings_memo: dict[str, Any] | None = None  # one standings table a tick (`standings`)
        # What the tick put off because a box was busy (`_defer`): shown in health.json, told hourly.
        self._deferred: dict[str, dict[str, Any]] = {}
        self._deferred_told: dict[str, float] = {}
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
        self._born_at = self.clock()
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
                        self.alert("warning", f"{name}: could not poll the venue before reconciling ({type(exc).__name__}: {str(exc)[:160]})")
                    book.reconcile()  # repair/check receipts before health, agent wakes or sizing
                else:
                    book.open_baseline()
            except Exception as exc:  # noqa: BLE001 - a venue that is down now is reconciled on a later tick
                self.alert("warning", f"{name}: could not initialize venue accounting ({type(exc).__name__}: {str(exc)[:160]})")
        # The Alpha Lab (league/lab.py): built only when game.json switches it on and a lab box is
        # configured; its tools for researchers, and longer sessions for agents with evidence.
        from .lab import attach as attach_lab
        attach_lab(self)
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

    def alert(self, level: str, text: str) -> None:
        self.ledger.append("ops.alert", {"level": level, "text": str(text)[:1000]})

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
        rows = [row for row in strategies.all_strategies()
                if row["name"] not in known and refused.get(row["name"]) != code_sha(row["code"])]
        rows.sort(key=lambda row: not isinstance(row.get("repair"), dict))  # corrected children first
        for row in rows:
            if len(born) >= max(1, int(self.settings.enroll_per_tick)):
                break
            loser = None
            if len(self.registry.living()) >= int(rules["max_population"]):
                if not self.settings.enroll_displaces:
                    break
                # The seat of an agent still running the code this strategy corrects (it cannot be
                # promoted: its defect is on record), else the weakest resident that has had its chance.
                loser = self._defective_resident(row) or self._weakest(rules)
                if loser is None:
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

    def spawn(self, name: str, family: str, code: str, *, parent: str | None = None, reason: str = "",
              # `name` is the line the agent is numbered from. Empty means "the desk its NEEDS put
              # it on": that is how the architect's strategies join a desk rather than arriving
              # with a slug of their own.
              params: Mapping[str, Any] | None = None, endowment: Any | None = None, keep_probe_awake: bool = False,
              specialty: str | None = None, founder: str | None = None, described: Any | None = None) -> Agent:
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
            # Bands of capital: a real position is `position_share` of the allocator's stake, never
            # under the venue's minimum order, every order within the gateway's cap.
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

    def _generation(self, agent_id: str) -> tuple[str, str, int, int] | None:
        """Identity of the strategy and rung stay, read while holding the lifecycle lock."""
        agent = self.registry.get(agent_id)
        if agent is None or not agent.alive:
            return None
        strategy = json.dumps([agent.params, agent.needs], sort_keys=True, separators=(",", ":"))
        last_strategy = self.ledger.last("agent.strategy", agent=agent_id)
        return agent.code_sha256, strategy, last_strategy.seq if last_strategy else 0, self.evaluator._rung_entered(agent_id)

    def wake(self, agent: Agent) -> dict[str, Any]:
        """One wake of one agent. Returns what happened, for the caller and the tests."""
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None:
                return {"agent": agent.id, "skipped": "retired"}
            agent = deepcopy(self.registry.get(agent.id))
            self._state["next_wake"][agent.id] = self._next_wake(agent, self.clock())
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
            self.alert("warning", f"{agent.id}: its box did not run ({str(exc)[:200]})")
            return {"agent": agent.id, "skipped": "sandbox"}
        self._charge_box(agent.id, run, note="a decision")
        result = run.result
        # Sizing may need a venue quote, so do it before the short result commit.
        adjusted: list[str] = []
        # The decision's cancels are applied below, after sizing, but the book judges its new orders
        # after them: the real-money trim must not count a bid this decision withdraws (`_fit_real_entry`).
        cancelling = frozenset(c for c in (result.get("cancels") or ()) if isinstance(c, str)) if result.get("ok") else frozenset()
        intents, dropped = (self._intents(agent, book, result.get("intents") or [], adjusted=adjusted, cancelling=cancelling)
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
            idle = self._note_wake(agent, acted=bool(intents or cancelled or ctx["positions"] or ctx["open_orders"]), offered=offered)
            self.ledger.append(
                "agent.woke",
                {"ok": True, "book": book.name, "intents": len(intents), "dropped": dropped, "cancels": len(cancelled), "seconds": result.get("seconds"),
                 "offered": offered, **({"barren": idle["barren"]} if idle["barren"] else {}), **({"shut": idle["shut"]} if idle["shut"] else {}),
                 **({"adjusted": adjusted[:16]} if adjusted else {})},
                agent=agent.id,
            )
        return {"agent": agent.id, "book": book.name, "intents": intents, "dropped": dropped, "offered": offered,
                "_generation": generation}

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
          stops wakes too (`_note_stopped` says so after three ticks): this says which markets it
          is leaving unattended.
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
                last = max(float(woke.get(niche_id) or 0), paused_at, self._born_at)
                if now - last < QUIET_ROUND_THE_CLOCK_SECONDS or now - float(told_quiet.get(niche_id) or float("-inf")) < QUIET_ROUND_THE_CLOCK_SECONDS:
                    continue
                told_quiet[niche_id] = now
                stopped = str((self._state.get("stopped") or {}).get("reason") or "")
                alerts.append(f"{niche_id}: no wake on a round-the-clock desk for {int((now - last) // 60)} minutes with {len(members)} "
                              f"living member(s) and the House not paused" + (f" ({stopped})" if stopped else "")
                              + ". Its markets are live and unattended.")
        with self._state_lock:
            state.update(cursor=int(cursor), paused_at=paused_at,
                         dead_told={k: v for k, v in told_dead.items() if v >= today},
                         quiet_told={k: v for k, v in told_quiet.items() if now - float(v) < QUIET_ROUND_THE_CLOCK_SECONDS})
        for text in alerts:
            self.alert("warning", text)

    def _offered(self, agent: Agent, ctx: Mapping[str, Any]) -> int:
        """How many live, tradeable things this wake actually put in front of the strategy.

        Zero means there was nothing to act on -- a shut equity session, an empty Kalshi window --
        and doing nothing was the only right answer. A number above zero with nothing done means
        the strategy looked at a live market and its rules did not fire: that is the strategy's
        problem to solve, and the House should hand it a research pass rather than wake it into
        the same wall for hours."""
        if family_of(agent.venue) == "kalshi":
            return len(ctx.get("markets") or [])
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
                refusal = ""
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
            self.alert("error", f"{agent.id}: its wake failed ({type(exc).__name__}: {str(exc)[:200]})")
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
        # window (the backfilled vol and funding cover the live window): a strategy that reads either
        # is replayed on the live tape.
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
        one) before a replay can judge a strategy that reads it. `sports` and `perps` are recorded
        live and never backfilled, so that is twenty blocks of recording; `vol` and `funding` are
        point-in-time history backfilled over the window (Sept 23, 2026), so they cover it as soon as
        the backfill is in -- and a key still waiting for its first page is a wait, not missing data."""
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
            polled = {feed: (self.feeds.keys(feed) if self.feeds is not None else []) for feed in feeds_module.FEEDS}
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
        (then the live tape is used, exactly as before). Deep tapes are cached like live ones."""
        from . import deep_replay
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
                    self._tapes[key] = (self.clock(), deep_replay.dev_tape(store, needs, feed=feed, days=self.settings.deep_replay_days or None,
                                                                          holdout=self.holdout_window)[1])
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
            self.alert("warning", f"the underlier bars of {', '.join(symbols)} could not be recorded ({type(exc).__name__}: {str(exc)[:160]})")
            return {}
        return {s: list(bars)[-MAX_OBSERVED_BARS:] for s, bars in (rows or {}).items() if bars}

    def _run_replay(self, agent: Agent, code: str, needs: Mapping[str, Any], params: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
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
        stake = float(row["stake_usd"])
        limits = {"max_position_usd": float(row["max_position_usd"]), "max_order_usd": float(row["max_order_usd"])}
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

        lane = self._lanes["research" if key.startswith("research:") else "replay" if key.startswith("replay")
                           else "audit" if key.startswith("audit:") else "feeds" if key.startswith("feeds:") else "ops"]
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
                with self._state_lock:
                    self._job_status[key]["started_at"] = started_at
                job_id = f"{key}:{queued_at:.6f}"
                state = "finished"
                try:
                    self.ledger.append("ops.job", {"job": job_id, "key": key, "state": "started",
                        "queued_seconds": max(0, started_at - queued_at)})
                    work(*args)
                except Exception as exc:  # noqa: BLE001
                    state = "failed"
                    try:
                        self.alert("warning", f"{key} failed ({type(exc).__name__}: {str(exc)[:200]})")
                    except Exception:  # noqa: BLE001 - the ledger may already be closed on the way out
                        pass
                finally:
                    try:
                        self.ledger.append("ops.job", {"job": job_id, "key": key, "state": state,
                            "queued_seconds": max(0, started_at - queued_at),
                            "running_seconds": max(0, self.clock() - started_at),
                            "elapsed_seconds": max(0, self.clock() - queued_at)})
                    except Exception:
                        pass  # a missing finish remains visible as interrupted work after restart
                    with self._state_lock:
                        self._job_status.pop(key, None)

        thread = threading.Thread(target=job, name=f"league-slow:{key}"[:60], daemon=True)
        self._jobs[key] = thread
        thread.start()
        return True

    def wait(self, timeout: float | None = None) -> None:
        """Block until the slow work in hand is done (tests use it; the run loop does not)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        for thread in list(self._jobs.values()):
            thread.join(None if deadline is None else max(0, deadline - time.monotonic()))

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
                                      f"({type(exc).__name__}: {str(exc)[:200]})")
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
        verdicts = list(self.ledger.iter(kinds="audit.verdict", agent=agent_id, after=int(record.get("since_seq") or 0)))
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
        if any(not e.payload.get("error") for e in self.ledger.iter(kinds="audit.verdict", agent=agent.id, after=entered)):
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
            source_book = self.book_of(agent)
            if rung >= 1 and source_book is not None and not source_book.evidence_integrity(agent.id)['ok']:
                self._promotion_status(agent, verdict, 'accounting_integrity',
                    'position attribution changed during the audit; the source record requires repair',
                    accounting=source_book.evidence_integrity(agent.id))
                return
            if rung >= 1 and self.campaigns and not self.campaigns.allows_live(rung + 1):
                self._promotion_status(agent, verdict, 'campaign', 'the live allocation window closed during the audit')
                return
            authorization = self.campaigns.live_authorization() if self.campaigns else None
            if rung == 1 and allocator_module.enabled():
                # A known defect's bunt, committed after its audit: the allocator's envelope decides.
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
        row = self.backup.run()
        if not row.get("ok"):
            self.alert("error", f"The daily backup of the House box failed ({row.get('error')}). The ledger lives on one disk until one succeeds.")

    # -------------------------------------------------------------- expedition
    def _note_stopped(self, reason: str) -> None:
        """Say so when the floor stops buying work, and why, once a stop has lasted three ticks;
        and say so again when it reopens.

        Measured Sept 22, 2026: the campaign's Sail meter latched at 16:47:39Z and the floor stopped
        research, Merton, audits and births with $139 of allowance unspent -- and nothing said so.
        Every tick summary read "stopped", every alert stayed quiet, and it was found 23 minutes
        later by reading the ledger. A warning, not an error: a vendor-side stop is no reason to
        roll back the release being watched. A maintenance pause is the operator's own act and is
        not announced."""
        tell = told = None
        with self._state_lock:
            row = dict(self._state.get("stopped") or {"reason": "", "ticks": 0, "told": False})
            if not reason:
                if row.get("told"):
                    told = row.get("reason")
                self._state["stopped"] = {"reason": "", "ticks": 0, "told": False}
            else:
                row["ticks"] = int(row.get("ticks") or 0) + 1 if row.get("reason") == reason else 1
                row["reason"] = reason
                if row["ticks"] >= 3 and not row.get("told") and not reason.startswith("maintenance pause"):
                    row["told"] = True
                    tell = row["ticks"]
                self._state["stopped"] = row
        if tell:
            self.alert("warning", f"the floor has stopped buying work for {tell} ticks: {reason}. "
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
    def _enforce_horizon(self) -> int:
        """Close crypto positions held past the horizon (the entry side of the rule, for Kalshi, is
        in the book's check). The agent's own working orders in that coin are cancelled first, so
        the whole holding is free to sell; a position is closed by the House, at the market."""
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
                    for working in book.open_orders(agent_id):
                        if working.instrument.key == holding.instrument.key:
                            book.cancel(agent_id, working.order_id)
                    quantity = book.account(agent_id).holdings.get(holding.instrument.key)
                    if quantity is None or quantity.quantity <= 0:
                        continue
                    exits.append(Intent.new(
                        agent=agent_id, instrument=holding.instrument, side="sell", quantity=quantity.quantity,
                        reason=f"The House's horizon rule: held {held:.0f} hours, and a crypto position is closed after {hours:g}.",
                        created_at=now, nonce=f"horizon:{holding.opened_at}:{int(self.clock()) // 3600}",
                    ))
            # A long option is sold before it can expire: in the money at the bell it would be
            # exercised into a hundred shares this account cannot carry. From 14:30 New York on
            # its last day the House sells it at the bid, again each tick until it is gone; one
            # with no bid left is worthless and is written off once the venue has cleared it.
            today, hour = _new_york(self.clock)
            for agent_id in book.agents():
                for holding in list(book.account(agent_id).holdings.values()):
                    inst = holding.instrument
                    if inst.asset_class != "option" or holding.quantity <= 0 or str(inst.expiry or "9999") > today or hour < 14.5:
                        continue
                    for working in book.open_orders(agent_id):
                        if working.instrument.key == inst.key:
                            book.cancel(agent_id, working.order_id)
                    quote = book.broker.quote(inst)
                    if quote.bid is None or quote.bid <= 0:
                        continue
                    exits.append(Intent.new(
                        agent=agent_id, instrument=inst, side="sell", quantity=holding.quantity, order_type="limit", limit_price=quote.bid,
                        reason="The House's expiry rule: a long option is sold on its last afternoon, never left to be exercised.",
                        created_at=now, nonce=f"expiry:{inst.key}:{int(self.clock() // 600)}",
                    ))
            if exits:
                closed += sum(1 for o in book.submit(exits) if o.status not in ("refused", "duplicate"))
            closed += book.expire_options()
        return closed

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
        last = self.ledger.last("audit.verdict", agent=agent.id)
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
        for holding in list(book.account(agent.id).holdings.values()):
            if holding.instrument.asset_class == "event":
                continue  # a Kalshi contract is held to settlement: selling a favourite at the bid gives the edge back
            quantity = max(holding.quantity - reserved.get(holding.instrument.key, ZERO), ZERO)
            if quantity <= 0:
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
        if exits:
            book.submit(exits)
            book.poll()
        self._sweep(agent.id, book)

    def _sweep(self, agent_id: str, book: Book) -> None:
        """Return a finished account's free cash to the House's side of the book."""
        account = book.account(agent_id)
        if not account.holdings and not book.open_orders(agent_id) and account.cash > 0 and not account.swept:
            book.stake(agent_id, -account.cash, note="account closed")  # all of it: what is left of the stake, and any profit

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
            for key in ("next_wake", "memory", "last_research", "tried", "idle"):
                self._state[key].pop(agent.id, None)
        try:
            self.sandbox.retire(agent.id)
        except Exception as exc:  # noqa: BLE001
            self.alert("warning", f"{agent.id}: its box could not be retired ({type(exc).__name__})")

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
        child_code = code or parent.code
        child_params = dict(params) if params is not None else (parent.params if code else self._mutated_params(parent, seed=f"{parent.id}:{len(self.registry.agents)}"))
        if child_params is None:
            return None
        child = self.spawn(parent.line or parent.name, parent.family, child_code, parent=parent.id, params=child_params, reason=reason or "a parameter mutation of its parent",
                           endowment=rules["endowment_usd"] if staked_by_house else None, described=described)
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
            self.alert("warning", f"{child.id}: could not fork its parent's box, starting from the clean image ({str(exc)[:160]})")
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
        if self._closing.is_set() or not agent.alive or self.researcher is None or not self.settings.research:
            return False
        if self.paused():
            return False
        if not self.pacer.may_spend(self._research_budget_kind(agent)):
            return False
        if self.deploying():
            return False  # existing sessions are checkpointed; do not add work during staging
        pending = self.research_jobs.active(agent.id)
        if pending:
            return self.clock() >= pending["available"]
        rules = self.game.get("research") or {}
        if self.economy.balance(agent.id) <= Decimal(str(rules.get("min_credits_usd", "0.10"))) * 2:
            return False
        last = max(float(self._state["last_research"].get(agent.id) or 0), self.research_jobs.last_finished(agent.id))
        # A new execution failure is actionable evidence. Give it one prompt response,
        # retaining the provider budget, earned-credit and durable-job checks above.
        refusal = self.ledger.last('book.refused', agent=agent.id)
        book = self.book_of(agent)
        if (refusal is not None and book is not None and refusal.payload.get('book') == book.name
                and _epoch(refusal.at) > last and self.clock() - last >= 60):
            return True
        interval = self.research_interval_hours(agent) * 3600
        if self.clock() - last < interval:
            return False
        return self._gate(agent, last, interval)

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
            row = self.ledger.last(kind, agent=agent.id)
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
        """Count empty passes in a row: no candidate, no replay trial and no Merton strategy."""
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

    def _weakest(self, rules: Mapping[str, Any], *, specialty: str | None = None, exclude: Sequence[str] = ()) -> Agent | None:
        """The agent a newcomer displaces, or None when nobody has earned displacing.

        Never one on real money -- what that may cost is already bounded by the tuition, and the
        auditor put it there. Never a profitable one, however small its record. Never one too young
        to have had a fair chance. Of the rest, the one with the LEAST EVIDENCE of an edge.

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
        now = self.clock()
        stamp = None  # now, as a market-hours check reads it: made once, and only if a desk keeps hours
        rank = []
        for standing in self.standings():
            agent = self.registry.get(standing.agent)
            if agent.id in exclude or (specialty is not None and agent.specialty != specialty):
                continue
            if standing.rung >= 2 or standing.mean_growth > 0 or standing.score_growth > 0:
                continue
            opportunity = _epoch(agent.born_at)
            opportunity_seq = 0
            agent_grace = grace
            niche = self.niche_of(agent)
            keeps_hours = standing.rung == 1 and niche is not None and niche.keeps_hours(agent.needs)
            if standing.rung == 0 and self._burst:
                # Completed research is the opportunity; waiting out an hour adds no evidence.
                # Queued/paid work and a late-qualified program must not die on a calendar timer.
                opportunity = max(opportunity, self._burst['started'])
                if self.research_jobs.active(agent.id):
                    continue
                completed = sum(1 for e in self.ledger.iter(kinds='agent.research', agent=agent.id)
                    if e.payload.get('tool') == 'summary' and _epoch(e.at) >= opportunity
                    and not str(e.payload.get('reason') or '').startswith(('provider:', 'tool outcome unconfirmed')))
                # A failed replay of its own code is a finished chance too. Sept 23, 2026: research is
                # paced by record now (an agent with none waits three intervals), and without this a
                # rung-0 agent that failed replay twice would hold its seat until the 72-hour cull.
                completed += sum(1 for e in self.ledger.iter(kinds='eval.trial', agent=agent.id)
                                 if not e.payload.get('passed') and _epoch(e.at) >= opportunity)
                if completed < self._burst['policy']['minimum_research_passes']:
                    continue
                agent_grace = 0
            if standing.rung == 1:
                # A late replay pass or a new empty-record strategy has not had the old
                # program's trading opportunity. Meriwether-8 passed replay at 00:21 and
                # was displaced at 01:01 with zero forward blocks because its birth was
                # already fourteen hours old. Recover the current program's start from
                # the ledger, including across restarts; duplicate strategy rows do not
                # buy another grace period.
                #
                # On a desk that keeps hours, a rewrite of an agent that has never traded is NOT a
                # new opportunity (Sept 23, 2026): research rewrote idle stock agents every few
                # hours (mcentee-34 three times in eight), each rewrite restarted the clock, and
                # the agents that never traded outlived the ones that did.
                first_fill = None
                if keeps_hours:
                    found = next(iter(self.ledger.iter(kinds="book.fill", agent=agent.id)), None)
                    first_fill = None if found is None else found.seq
                signature = None
                for entry in self.ledger.iter(kinds=("agent.born", "agent.strategy", "eval.verdict"), agent=agent.id):
                    p = entry.payload
                    if entry.kind in ("agent.born", "agent.strategy"):
                        current = (p.get("code_sha256"), p.get("params"), p.get("needs"))
                        if current != signature:
                            if signature is None or not keeps_hours or (first_fill is not None and first_fill < entry.seq):
                                opportunity, opportunity_seq = _epoch(entry.at), entry.seq
                            signature = current
                    elif p.get("decision") in ("seat", "promote", "demote") and p.get("to_rung") == 1:
                        opportunity, opportunity_seq = _epoch(entry.at), entry.seq
                if self._burst:
                    from .episodes import completed
                    book = self.book_of(agent)
                    episodes = completed(self.ledger, agent.id, book.name, since_seq=opportunity_seq) if book else []
                    if len(episodes) >= int(CONSTITUTION['ladder']['completed_exposures']['min_episodes']):
                        # An evidenced non-winner can make room once it has finished actual risk.
                        # The paper clock remains a fallback for strategies without that record.
                        if self.research_jobs.active(agent.id):
                            continue
                        agent_grace = 0
            traded = False
            if keeps_hours:
                # The rebuilt league was born on a Saturday. Twelve wall-clock hours later
                # its equity agents were displaced before their first market session. Start
                # their paper-seat grace at an actual offered opportunity (or a legacy fill),
                # not at a weekend birth. Replay-only agents still have their normal deadline.
                first = next((e for e in self.ledger.iter(kinds=("agent.woke", "book.fill"), agent=agent.id, after=opportunity_seq)
                              if e.kind == "book.fill" or (e.payload.get("ok") and int(e.payload.get("offered") or 0) > 0)), None)
                if first is None:
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
                        continue
                traded = next(iter(self.ledger.iter(kinds="book.fill", agent=agent.id, after=opportunity_seq)), None) is not None
                if traded and self._trading_pending(agent, book, opportunity, now, rules):
                    continue
            if standing.rung == 1 and agent_grace > 0 and agent.horizon == "day" and self._screen_pending(agent, opportunity_seq, now - opportunity):
                continue
            # A desk that keeps hours offers nothing between the close and the next open: its grace
            # is counted in regular-session time.
            seated = session_time(opportunity, now)[0] if keeps_hours else now - opportunity
            if seated < agent_grace:
                continue
            rank.append((standing.active_blocks > 0 or traded, standing.mean_growth, standing.active_blocks,
                         float(self.economy.balance(agent.id)), agent))
        rank.sort(key=lambda row: row[:4])  # has it traded at all, then growth, then how much, then its purse
        return rank[0][4] if rank else None

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
        displaced once either is reached, and a profitable one never was displaceable."""
        owed = int(rules.get("displace_trading_after_sessions", 3))
        if session_time(opportunity, now)[1] >= owed:
            return False
        if book is None:
            return False
        closed, _ = allocator_module.closed_trades(self, agent.id, book.name)
        return closed < int(CONSTITUTION["allocator"]["bunt_min_trades"])

    def frontier_remaining(self) -> Decimal | None:
        """The tighter of the two OpenAI lines: the gateway's month (`FrontierMonth`) and the House's
        own campaign allowance, which refuses at its own line whatever the gateway has left.

        The reserve that keeps the last dollars for audits read only the gateway. On Sept 22, 2026 the
        campaign -- which books every call at the House's ceiling prices, about twice the gateway's --
        had $139 left against the gateway's $166 while committing about $17 an hour: it would have
        refused every call, audits included, while the tier still said "all". None when neither line
        can be read; the campaign counts only beside a month reader, as in production."""
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
                self.alert("warning", f"the gateway's profit-indexed raise could not be mirrored ({type(exc).__name__}: {str(exc)[:160]})")
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
        once, so the owner reads why Merton went quiet."""
        from .frontier import frontier_tier

        remaining = self.frontier_remaining()
        tier = frontier_tier(remaining, self.game.get("frontier_reserve"))
        with self._state_lock:
            changed = tier != self._state.get("frontier_tier", "all")
            self._state["frontier_tier"] = tier
        if changed:
            shown = f"${remaining:.2f}" if remaining is not None else "unknown"
            self.alert("warning" if tier != "all" else "info", {
                "all": f"frontier budget {shown} left: every role runs again",
                "earned": f"frontier budget {shown} left: cheap research moves to Sail and the unearned roles pause",
                "audits": f"frontier budget {shown} left: only audits and winners' consultations remain"}[tier])
        return tier

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
            # The two backfilled histories (Sept 23, 2026), said plainly: a strategy that reads them can
            # be replayed now, which no live-recorded feed can offer on its first day.
            history = {feed: {'backfilled_since': (described.get(feed) or {}).get('backfilled_since'),
                              'replayable_now': (described.get(feed) or {}).get('replayable_now')}
                       for feed in feeds_module.HISTORY_FEEDS if (described.get(feed) or {}).get('recording')}
            if history:
                result['observations']['replayable_history'] = {
                    **history,
                    'note': 'vol (Deribit DVOL, BTC and ETH, hourly candles stamped at their close) and funding (OKX settled '
                            'funding per coin, stamped at settlement, with avg_24h, avg_7d, zscore_30d) are point-in-time '
                            'history backfilled over the replay window: declare NEEDS["feeds"] = {"vol": [...], "funding": [...]} '
                            'and a replay can judge the strategy now. Row shapes: observations.feeds and the contract.'}
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
                                                                    '(sports and perps are recorded live; vol and funding are backfilled '
                                                                    'over the live replay window)' if wanted
                                                             else 'the history store has not fetched every input yet' if self.settings.deep_replay else 'deep replay is off'})
            feeds = None
            if wanted:
                # What the declared feeds hold over this tape's window, and whether a replay may use them yet.
                short = self._feeds_shortfall(effective, wanted, tape.get('feeds_coverage') or {}) if self.feeds is not None else \
                    'unsupported input: this House records no live feeds'
                feeds = {'requested': wanted, 'coverage': tape.get('feeds_coverage'), 'replay_ready': not short,
                         **({'blocked_by': short} if short else {}),
                         'note': 'Every row is replayed point in time by its t. sports and perps rows are recorded live with their '
                                 'receive time, and nothing before recording began exists. vol and funding rows are point-in-time '
                                 'history, stamped when each value became final (a DVOL candle at its close, a funding rate at its '
                                 'settlement) and backfilled over the replay window (coverage.<feed>.<key>.backfill says from where '
                                 'and since when), so they are replayable as soon as the backfill is in. A live wake is handed '
                                 'ctx["feeds"] whether or not a replay may use them yet.'}
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
                self.research_jobs.finish(session, 'candidate commit unconfirmed; evidence retained')
                return None
            with self._lifecycle_lock:
                current = self._generation(agent.id)
                if current is None or list(current[:-1]) != job['generation'][:-1]:
                    self.research_jobs.finish(session, 'retired or changed before resume', cancelled=True)
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
            self.research_jobs.finish(session, getattr(outcome, 'reason', 'finished'))
            self._note_research_result(agent.id, outcome)
            with self._lifecycle_lock:
                with self._state_lock:
                    if self._generation(agent.id) is not None:
                        self._state['last_research'][agent.id] = self.clock()
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
                loser = self._weakest(rules, specialty=niche.id if niche_full else None, exclude=(parent.id,))
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
        if row.get("band") in ("bunt", "swing", "star"):
            # Already on real money: the line it now has to hold is the bunt line with hysteresis.
            out.update(on_real_money=True, holds_real_money_down_to_E=round(at * float(r.get("hysteresis", 1.0)), 6))
        return out

    def standings(self) -> list[Standing]:
        """Every living agent's standing. Inside a tick, on the tick's own thread, the table is built
        once and reused while the living roster is unchanged (a birth or a death rebuilds it); anywhere
        else it is built fresh."""
        epoch = float(self.game['economy']['epoch_seconds'])
        living = list(self.registry.living())
        memo = getattr(self, "_standings_memo", None)
        if memo is None or memo["thread"] != threading.get_ident():
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
        if not refill or self._closing.is_set():
            return  # births buy sandbox work; culling above remains available after spending stops
        # Every birth reads its strategy's NEEDS in the probe box. The tick holds that box for the
        # whole phase (each probe reenters it), or, when background work has it, births wait for
        # the next tick with the reason recorded. A Sail call that fails is deferred the same way.
        with self._probe_turn("births") as free:
            if free:
                try:
                    self._births(rules)
                except SandboxError as exc:
                    self._defer("births", f"infrastructure: {type(exc).__name__}: {str(exc)[:200]}")

    def _births(self, rules: Mapping[str, Any]) -> None:
        """Forks of rich agents, the founders below the floor, merged strategies, then the refill."""
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
            with self._lifecycle_lock:
                for row in Admissions(self.ledger).pending():
                    child = self._admit_candidate(row, displace=True)
                    if child is not None:
                        state['at'] = self.clock()
                        return child
        living = self.registry.living()
        if not living:
            return None
        loser = None
        if len(living) >= int(rules["max_population"]):
            # A ceiling with nothing dying under it is a floor that has stopped searching. Measured
            # Sept 20, 2026: thirty-three agents born in twelve hours and NOT ONE dead, four births
            # from a league that could never try anything again. So the last seat is a tournament:
            # a newcomer takes it from the worst agent that has had its chance, which is the
            # selection pressure the ceiling was meant to create and never did.
            loser = self._weakest(rules)
            if loser is None:
                return None
            # Do not retire a resident until the cadence is due and a valid replacement exists.
            living = [a for a in living if a.id != loser.id]
        urgent = len(living) < int(rules["min_population"])
        every = float(rules["newcomer_seconds"]) / (4 if urgent else 1)
        if self.clock() - self._born_at < 300:
            return None  # this process has just started: settle first, as `due()` does with wakes
        # The wait is since the last newcomer, or since the floor first ran -- NOT since this
        # process started. Measured Sept 20, 2026: the interval was anchored on `_born_at`, which
        # moves on every restart, and a floor that deploys itself restarts every half hour. In six
        # hours the hour never once elapsed, `last_newcomer` was never written, and the league sat
        # at its founding size with seven seats empty. A floor that rewrites itself deploys often
        # by design, so anything paced longer than a deploy must survive one.
        state = self._state.setdefault("last_newcomer", {})
        last = float(state.get("at") or state.get("since") or self._born_at)
        if self.clock() - last < every:
            return None
        if self.hypotheses is not None and self.hypotheses.replaces_refill():
            # Hypotheses, not blind mutations (league/hypotheses.py): a replay-passing card, or a
            # mutation of a parent that is earning forward, never a draw placed by open seats.
            return self.hypotheses.refill(rules, living=living, loser=loser)
        seats = {n.id: n.max_members - sum(a.specialty == n.id for a in living)
                 for n in self.niches.values() if not n.dormant}
        seats = {key: value for key, value in seats.items() if value > 0}
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
            if exhausted(best):
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

    def _absorb_stale_holds(self) -> None:
        """Every ten minutes, release Sail holds older than the meter's lag into the balance meter
        that already counts their charge (`CampaignBudget.absorb_stale`), and say so on the ledger."""
        if self.clock() - float(self._state.get("holds_absorbed_at") or 0) < 600:
            return
        self._state["holds_absorbed_at"] = self.clock()
        absorb = getattr(self.campaigns, "absorb_stale", None)
        if absorb is None or "sail" not in (getattr(self.campaigns, "policy", {}) or {}).get("meter_required", []):
            return
        try:
            out = absorb("sail", older_than_seconds=self.STALE_HOLD_SECONDS, evidence={"by": "house", "release": Path(__file__).resolve().parents[1].name})
        except Exception as exc:  # noqa: BLE001 - a reconciliation that fails leaves the holds counted
            self.alert("warning", f"stale Sail holds could not be absorbed ({type(exc).__name__}: {str(exc)[:160]})")
            return
        if out.get("absorbed"):
            self.ledger.append("ops.budget", {"what": "holds absorbed", "kind": "sail", **out})

    def tick(self) -> dict[str, Any]:
        """One pass of the floor. It never waits on a box background work holds: a wake whose box
        is busy is retried on the next tick, and births wait for the probe box at most
        `probe_wait_seconds` (`_births`). What it put off is in health.json's `deferred`."""
        # One standings table a tick (Sept 23, 2026): displacement, the refill and the foundry each
        # ranked every living agent afresh, several ledger scans an agent each time, and a profile of the
        # production tick found about 80% of its main thread there (191 s ticks at 10:53Z).
        self._standings_memo = {"thread": threading.get_ident(), "living": None, "rows": None}
        try:
            with self._box_patience():
                return self._tick()
        finally:
            self._standings_memo = None

    def _tick(self) -> dict[str, Any]:
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
        for name, book in self.books.items():
            try:
                advance = getattr(book.broker, "advance", None)
                if advance:
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
                self.alert("warning", f"{name}: could not poll or settle ({type(exc).__name__}: {str(exc)[:200]})")
        try:
            self._cancel_stale_resting()
        except Exception as exc:  # noqa: BLE001 - a guard that fails this tick runs again on the next
            self.alert("warning", f"stale resting orders could not be checked ({type(exc).__name__}: {str(exc)[:160]})")
        try:
            self._order_path_invariants()  # code over house.json and the ledger's new refusals; runs while paused too
        except Exception as exc:  # noqa: BLE001 - a check that fails this tick runs again on the next
            self.alert("warning", f"the order path's invariants could not be checked ({type(exc).__name__}: {str(exc)[:160]})")
        # Past the monthly compute line only agents holding real money are woken, so they can exit.
        open_for_business = self.budget is None or self.budget.check() == "open"
        stopped_because = "" if open_for_business else f"the Sail meter's monthly line or reserve (league/budget.py mode {getattr(self.budget, 'mode', '?')})"
        if self.campaigns:
            meter = getattr(self.provider, "transport", None)
            metered = bool(meter and hasattr(meter, "refresh") and meter.refresh())
            if metered:
                self._absorb_stale_holds()
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
        # Each wake is mostly waiting on the agent's box, so they run side by side; every agent
        # has its own box and its own lock, and the ledger and the books are thread-safe.
        with ThreadPoolExecutor(max_workers=max(1, min(self.settings.wake_workers, len(waking) or 1))) as pool:
            outcomes = list(pool.map(self._wake_safely, waking))
        for agent, outcome in zip(waking, outcomes):
            summary["woke"].append(agent.id)
            if outcome.get("intents"):
                batches.setdefault(outcome["book"], []).append(outcome)
        for name, wakes in batches.items():
            submitted = self._submit_wakes(name, wakes)
            summary["orders"] += sum(1 for o in submitted if o.status not in ("refused", "duplicate"))
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
                result = book.reconcile()
                summary["reconciled"][name] = result.ok
                if not result.ok:
                    # A few cents short on a PAPER book, with every position agreeing, is the venue's
                    # end-of-day fee activity not posted yet (`Book._book_venue_fees` books it when it
                    # is). Measured Sept 22, 2026: two paper option buys left the book $0.06 over the
                    # venue for one mark pass, and an error then -- inside a deploy's watch -- rolls a
                    # good release back. Real money, or any position difference, stays an error.
                    minor = (not book.real_money and not result.position_diffs
                             and abs(Decimal(result.cash_diff)) <= Decimal("1.00"))
                    self.alert("warning" if minor else "error", f"{name} does not reconcile: {result.detail}")
            except Exception as exc:  # noqa: BLE001
                self.alert("warning", f"{name}: could not mark or reconcile ({type(exc).__name__}: {str(exc)[:200]})")
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
        if marked_any and allocator_module.enabled():
            # Capital is the ladder: bands and stakes follow the evidence of this very mark pass.
            try:
                moved = self.allocator.rebalance()
                summary["allocator"] = {k: len(v) if isinstance(v, list) else v for k, v in moved.items()}
            except Exception as exc:  # noqa: BLE001 - a pass that fails runs again at the next mark
                self.alert("error", f"the allocator's pass failed ({type(exc).__name__}: {str(exc)[:200]})")
        self._cancel_retired_research()
        for agent in self.research_order() if open_for_business else []:
            if self.research_due(agent):
                # Persist before dispatch, so queued work also survives process exit.
                self.queue_research(agent)
        if open_for_business and self.survey_due():
            self._background("niche-survey", self.survey_niches)  # stamped when it ends; one in hand is not started twice
        if open_for_business and self.semantic_lab is not None and self.semantic_lab.due():
            self._background('semantic-lab', self.semantic_lab.run)
        if self.jev_floor is not None:
            self.jev_floor.tick(open_for_business)
        if self.backup is not None and self.backup.due():
            self._background("backup", self._run_backup)
        # Both are code over the ledger and cost nothing, so they run while the House is paused too.
        if self.pre_audit is not None and self.pre_audit.due():
            self._background("pre-audit", self.pre_audit.run, self)
        if self.consult_recovery is not None and self.consult_recovery.due():
            self._background("consult-recovery", self._recover_consults)
        self._history_coverage()
        if self.updater is not None and self.updater.due():
            self._background("update", self._update)
        if self.budget is not None and getattr(self.budget, "pacer", None) is None:
            self.budget.pacer = self.pacer
        self._pace_inference()
        if open_for_business and self.merton is not None:
            allowed = TIER_ROLES[self.frontier_tier()]
            for role in self.merton.due():
                if allowed is not None and role not in allowed:
                    continue  # the month's last dollars are kept for code, audits and winners
                # One role at a time against today's allowance: a pass is a dime to a few dollars,
                # and its cost is only known when it ends.
                if self.pacer.may_spend("openai") and not any(key.startswith("merton:") and key != "merton:follow" and job.is_alive() for key, job in self._jobs.items()):
                    self._background(f"merton:{role}", self.merton.run, role)
            self._background("merton:follow", self.merton.follow)
        if open_for_business and self.engineer is not None and self.engineer.due():
            # The repair worklist: its sources, its free follow-ups and at most one paid patch a
            # step, each against its own per-job ceiling and the day's frontier allowance.
            self._background("engineer", self.engineer.step)
        if self.hypotheses is not None:
            self.hypotheses.tick(open_for_business=open_for_business)  # its own tier, budget and cadence gates
        if self.lab is not None:
            self.lab.tick(open_for_business=open_for_business)  # schedules one bounded step off the tick (league/lab.py)
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
        # Outside every gate, because this is the one thing that says a budget is gone and it used
        # to sit inside the payout that a spent budget closes -- it could only be delivered while
        # the condition it announces was false. It tells the owner once per kind; a tick is cheap.
        self._expedition_notices()
        try:
            self._enforce_horizon()
        except Exception as exc:  # noqa: BLE001 - a venue that is down now is asked again next tick
            self.alert("warning", f"the horizon rule could not close a position ({type(exc).__name__}: {str(exc)[:160]})")
        if self.settings.real_money:
            self._enforce_tuition()
        # Culling is not spending: an agent whose credits reached zero should still die, and its
        # post-mortem still be written, when the meter has stopped the floor. Only the refill that
        # follows it costs anything, and that waits for business.
        self.keep_population(refill=open_for_business, clock=not pause)
        summary["deaths"] = sorted(living_before - {a.id for a in self.registry.living()})
        self._save_state()
        if self.publisher is not None:
            try:
                self.publisher.publish(self)
            except Exception as exc:  # noqa: BLE001 - the site is downstream of the floor, never upstream
                self.alert("warning", f"publishing failed ({type(exc).__name__}: {str(exc)[:200]})")
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
            "feeds": self.feeds.health() if self.feeds is not None else None,
            "deferred": deferred,
        }
        tmp = self.root / "health.tmp"
        tmp.write_text(json.dumps(health, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.root / "health.json")

    def close(self, *, wait: float | None = 5.0) -> None:
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
