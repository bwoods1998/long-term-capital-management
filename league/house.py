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
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ltcm.broker import Instrument, money

from . import seeds as seeds_module
from .agents import Agent, Registry, niche_of
from . import capital, niches as niches_module
from .book import Book, BookError, Intent, Limits, step_of
from .commons import Commons
from .constitution import CONSTITUTION, digest as constitution_digest
from .economy import Economy, Standing, load_game
from .evaluator import Evaluator, Verdict
from .fees import Fees
from .ledger import HOUSE, Ledger, now_iso
from .researcher import Researcher
from .pacer import Pacer
from .rules import rules_text
from .sandbox import SandboxError
from .venues import family_of, instrument_for, market_hours

#: How many bars of a watched underlier a replay tape carries per symbol, and the sizes it may
#: choose between. A three-week window of one-minute bars is millions of rows and a box killed for
#: memory (Sept 19, 2026); four thousand of them is about two megabytes for six symbols.
MAX_OBSERVED_BARS = 4000
OBSERVED_BAR_SIZES = (("5Min", 300), ("15Min", 900), ("1Hour", 3600), ("1Day", 86400))
from ltcm.data import market_open_at

ZERO = Decimal(0)
CONTRACT_PATH = Path(__file__).resolve().parent / "CONTRACT.md"

#: Which book an agent trades on, by venue family and rung.
PRACTICE_BOOK = {"alpaca": "alpaca-paper", "kalshi": "kalshi-shadow"}
REAL_BOOK = {"alpaca": "alpaca", "kalshi": "kalshi"}
PROBE_BOX = "house-probe"


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
    niche_survey_hours: float = 24.0  # how often the venue is surveyed so the universes follow the season (0: never)


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
        self.game = dict(game or load_game())
        self.ledger = Ledger(self.root / "ledger.sqlite", clock=clock)
        from .experiments import Experiments
        from .recordings import Recorder

        self.experiments = Experiments(self.root / "experiments", self.ledger, clock=clock)
        self.recorder = Recorder(self.root / "recordings.sqlite", clock=clock)
        self.registry = Registry(self.ledger)
        self.economy = Economy(self.ledger, self.game, clock=clock)
        self.evaluator = Evaluator(self.ledger, clock=clock, archive=self.experiments.archive)
        from .campaigns import CampaignPacer

        self.campaigns = campaigns
        self.pacer = CampaignPacer(self.ledger, campaigns, clock=clock) if campaigns else Pacer(self.ledger, clock=clock)
        self.commons = commons or Commons(self.ledger)
        self.sandbox = sandbox
        self.alpaca_data = alpaca_data
        self.kalshi_data = kalshi_data
        self.provider = provider
        self.auditor = auditor
        self.publisher = publisher
        self.budget = budget
        self.merton: Any = None  # set by the service: Merton's pull-request roles, and the consultancy agents hire
        self.backup: Any = None  # set by the service on the House box: a daily checkpoint of the box, kept by Sail
        self.updater: Any = None  # set by the service on the House box: pulls main, hands it to the watchdog
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
            )
        self._state_path = self.root / "house.json"
        self._state = self._load_state()
        self.niches = niches_module.load()
        for niche_id, live in (self._state.get("niche_live") or {}).items():
            if niche_id in self.niches:
                self.niches[niche_id].live = tuple(live)
        self._data_cache: dict[str, tuple[float, Any]] = {}
        self._tapes: dict[str, tuple[float, dict[str, Any]]] = {}
        self._tape_lock = threading.Lock()
        self._state_lock = threading.RLock()
        # Serialize lifecycle commits, not slow model/box/audit calls. A completed result must
        # still belong to the same strategy and rung when its effects reach the floor.
        self._lifecycle_lock = threading.RLock()
        # Slow work runs on daemon threads: a flex-window model call can take a quarter of an hour,
        # and a House that is told to stop must stop. (The provider settles an orphaned call later.)
        # Three lanes (measured on the first production start, Sept 19, 2026: with one two-slot queue,
        # research, the daily backup and the niche survey all waited behind 28 founders' replays).
        self._lanes = {"replay": threading.Semaphore(max(1, self.settings.slow_workers)),
                       "research": threading.Semaphore(max(1, self.settings.research_workers)),
                       "ops": threading.Semaphore(max(1, self.settings.ops_workers))}
        self._jobs: dict[str, threading.Thread] = {}
        self._job_status: dict[str, dict[str, Any]] = {}
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
                rung=self.evaluator.rung,
            )
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
                book.open_baseline()
            except Exception as exc:  # noqa: BLE001 - a venue that is down now is reconciled on a later tick
                self.alert("warning", f"{name}: could not take its baseline at start ({type(exc).__name__}: {str(exc)[:160]})")
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
            state = {}
        for key in ("next_wake", "memory", "last_research", "tried", "last_mark", "settled", "niche_live", "series_category", "idle"):
            state.setdefault(key, {})
        return state

    def _save_state(self) -> None:
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

    def stopped(self) -> bool:
        return (self.root / "STOP").exists()

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
        """Give the architect's merged strategies their life: each is born once, on rung 0, with a
        seed's endowment, while the population has room. They answer to replay like any child."""
        from . import strategies

        born = []
        known = {a.founder for a in self.registry.agents.values()}
        for row in strategies.all_strategies():
            if row["name"] in known or len(self.registry.living()) >= int(self.game["economy"]["max_population"]):
                continue
            try:
                # Named from the desk its NEEDS put it on, like every other agent: the strategy's
                # own name in the registry is what says it has already been born.
                born.append(self.spawn("", row["family"], row["code"], reason="Merton, as architect: " + row["why"], founder=row["name"]))
            except ValueError as exc:
                self.alert("warning", f"the architect's strategy {row['name']} could not be born: {str(exc)[:200]}")
        return born

    def learn(self) -> int:
        """Load the teacher's merged lessons (league/playbook/*.md) into the ledger's playbook, once each."""
        have = {e.payload.get("title") for e in self.ledger.iter(kinds="playbook.entry")}
        added = 0
        for path in sorted((Path(__file__).resolve().parent / "playbook").glob("*.md")):
            title = f"Lesson: {path.stem}"
            if path.name != "README.md" and title not in have:
                self.commons.playbook_add(title, path.read_text(encoding="utf-8"), source="teacher")
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
              specialty: str | None = None, founder: str | None = None) -> Agent:
        # A strategy's NEEDS are read by running its module body, so that happens in a box too: one
        # sealed probe box the House keeps for the purpose, never the House's own process.
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
        if niche is not None and not niche.replay:
            # The House cannot replay this specialty (no recorded option chains): paper is its replay.
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
    def book_of(self, agent: Agent) -> Book | None:
        rung = self.evaluator.rung(agent.id)
        if rung >= 2 and REAL_BOOK[agent.venue] in self.books:
            return self.books[REAL_BOOK[agent.venue]]
        return self.books.get(PRACTICE_BOOK[agent.venue])

    def _limits(self, rung: int, agent: Agent | None = None, staked: Decimal | None = None) -> Limits:
        row = CONSTITUTION["rungs"][str(min(max(rung, 1), 2))]
        position, order = Decimal(row["max_position_usd"]), Decimal(row["max_order_usd"])
        if rung >= 3 and staked is not None:
            position, order = capital.scaled_limits(staked)  # rung 3's limits follow its stake
        niche = self.niche_of(agent)
        classes = Limits.__dataclass_fields__["asset_classes"].default
        if niche is not None and niche.asset_class == "option":
            classes = ("option",)
            if rung == 2:  # one contract cannot be cut smaller: the micro rung's option cap
                position = order = Decimal(row["option_max_position_usd"])
        return Limits(position, order, asset_classes=classes, max_hours_to_resolve=self.horizon_hours(agent))

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
            try:
                book.stake(agent.id, stake, note=f"rung {rung} stake")
            except BookError as exc:  # a real book not reconciled yet, or out of real cash: try again next wake
                self.alert("warning", f"{agent.id} could not be staked on {book.name}: {exc}")

    # ------------------------------------------------------------------- data
    def _cached(self, key: str, ttl: float, build: Callable[[], Any]) -> Any:
        hit = self._data_cache.get(key)
        if hit and self.clock() - hit[0] < ttl:
            return hit[1]
        started = self.clock()
        value = build()
        try:
            self.recorder.record(key, value, started=started)
        except Exception as exc:  # recording failure must not prevent position management
            self.alert("warning", f"market recording failed ({type(exc).__name__})")
        self._data_cache[key] = (self.clock(), value)
        return value

    def snapshot(self, agent: Agent, book: Book) -> dict[str, Any]:
        """Everything a strategy sees, as plain data (floats: the box converts nothing back)."""
        needs = agent.needs
        account = book.account(agent.id)
        limits = book.limits.get(agent.id) or self._limits(1, agent)
        ctx: dict[str, Any] = {
            "now": now_iso(self.clock),
            "venue": agent.venue,
            "rung": self.evaluator.rung(agent.id),
            "params": agent.params,
            "memory": self._state["memory"].get(agent.id) or {},
            "cash": float(account.cash),
            "equity": float(book.equity(agent.id)),
            "limits": {"max_position_usd": float(limits.max_position_usd), "max_order_usd": float(limits.max_order_usd)},
            "fees": {"crypto_taker": 0.0025, "crypto_maker": 0.0015, "kalshi_taker_rate": 0.07},
            "positions": [],
            "open_orders": [],
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
        if agent.venue == "alpaca":
            symbols = [str(s) for s in (needs.get("symbols") or [])][:12]
            bars = dict(needs.get("bars") or {})
            timeframe = str(bars.get("timeframe") or "5Min")
            limit = max(1, min(int(bars.get("limit") or 120), 500))
            key = f"bars:{','.join(symbols)}:{timeframe}:{limit}"
            ctx["bars"] = self._cached(key, 50, lambda: self.alpaca_data.bars(symbols, timeframe, limit=limit))
            ctx["quotes"] = self._cached(f"quotes:{','.join(symbols)}", 20, lambda: self.alpaca_data.quotes(symbols))
            niche = self.niche_of(agent)
            if niche is not None and niche.asset_class == "option":
                days = max(2, min(int(needs.get("max_days_to_expiry") or 21), 45))
                afford = float(limits.max_order_usd) / 100.0  # a contract is 100 shares: what one order can pay a share
                ctx["chain"] = self._cached(f"chain:{','.join(symbols)}:{days}:{afford}", 120, lambda: self._chain(symbols[:8], days, afford, ctx["quotes"]))
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
        return ctx

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
        return out[: min(self.settings.max_wakes_per_tick, self.settings.cold_wakes_per_tick) if cold else self.settings.max_wakes_per_tick]

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
            self._state["next_wake"][agent.id] = self.clock() + agent.wake_minutes * 60
            rung = self.evaluator.rung(agent.id)
            if self._state["tried"].get(agent.id) != agent.code_sha256:
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
        except SandboxError as exc:
            self.alert("warning", f"{agent.id}: its box did not run ({str(exc)[:200]})")
            return {"agent": agent.id, "skipped": "sandbox"}
        self._charge_box(agent.id, run, note="a decision")
        result = run.result
        # Sizing may need a venue quote, so do it before the short result commit.
        intents, dropped = self._intents(agent, book, result.get("intents") or []) if result.get("ok") else ([], [])
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
                 "offered": offered, **({"barren": idle["barren"]} if idle["barren"] else {}), **({"shut": idle["shut"]} if idle["shut"] else {})},
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
                intents.extend(outcome.get("intents") or [])
            return self.books[book_name].submit(intents) if intents else []

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
        if (niche.asset_class if niche else "") in ("equity", "option") and not market_open_at(ctx["now"]):
            return 0
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

    def _intents(self, agent: Agent, book: Book, rows: list[Mapping[str, Any]]) -> tuple[list[Intent], list[str]]:
        intents, dropped = [], []
        now = now_iso(self.clock)
        for index, row in enumerate(rows):
            try:
                instrument = instrument_for(book.broker.venue, dict(row))
                side = str(row.get("side") or "").lower()
                if book.real_money and side == "buy" and self.campaigns and not self.campaigns.policy["allow_new_live_capital"]:
                    raise ValueError("this phase permits exits but no new real-money entries")
                niche = self.niche_of(agent)
                if niche is not None and side == "buy" and not niche.holds(instrument):
                    raise ValueError(f"{instrument.market_id or instrument.symbol} is outside the {niche.id} specialty")
                order_type = str(row.get("type") or "market").lower()
                limit = None if row.get("limit_price") is None else money(str(row["limit_price"]))
                if row.get("quantity") is not None:
                    quantity = money(str(row["quantity"]))
                else:
                    notional = money(str(row["notional_usd"]))
                    quote = book.broker.quote(instrument)
                    price = limit or (quote.ask if side == "buy" else quote.bid)
                    if price is None or price <= 0:
                        raise ValueError("no price to size the order at")
                    step = step_of(instrument, order_type)
                    quantity = ((notional / (price * instrument.multiplier)) / step).to_integral_value(rounding=ROUND_DOWN) * step
                if quantity <= 0:
                    raise ValueError("the size rounds down to nothing")
                intents.append(
                    Intent.new(
                        agent=agent.id, instrument=instrument, side=side, quantity=quantity, order_type=order_type,
                        limit_price=limit, post_only=bool(row.get("post_only")), reason=str(row.get("reason") or ""),
                        created_at=now, nonce=f"{now}:{index}",
                    )
                )
            except Exception as exc:  # noqa: BLE001 - one malformed intent is dropped, the rest stand
                dropped.append(f"{type(exc).__name__}: {str(exc)[:160]}")
        return intents, dropped

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
        if outcome.get("action") != "none":
            # A promotion signals this process and a fresh one comes up thirty seconds later, so
            # every research pass still running is thrown away with everything it has read. The
            # canary and its watch give about ten minutes of warning: stop STARTING passes now and
            # the ones in flight finish on their own. Measured Sept 20, 2026: three deploys inside
            # thirteen minutes killed eleven passes, which is most of an hour's research.
            with self._state_lock:
                self._state["deploying_at"] = self.clock()
            self.ledger.append("ops.deploy", {k: v for k, v in outcome.items() if k in ("action", "release", "reasons", "files")})

    def deploying(self) -> bool:
        """Is a release on its way in? True from the moment one is staged until the grace is up."""
        since = float(self._state.get("deploying_at") or 0)
        return bool(since) and self.clock() - since < float(self.settings.deploy_grace_seconds)

    def _wake_safely(self, agent: Agent) -> dict[str, Any]:
        try:
            return self.wake(agent)
        except Exception as exc:  # noqa: BLE001 - one agent's wake must never take the tick down
            self.alert("error", f"{agent.id}: its wake failed ({type(exc).__name__}: {str(exc)[:200]})")
            return {"agent": agent.id, "error": str(exc)}

    def _holds_real_money(self, agent: Agent) -> bool:
        book = self.books.get(REAL_BOOK[agent.venue])
        return bool(book and agent.id in book.accounts and (book.account(agent.id).holdings or book.open_orders(agent.id)))

    # ----------------------------------------------------------------- replay
    def tape_for(self, needs: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        """The recorded history a strategy with these NEEDS is replayed over (cached for a day)."""
        venue, horizon, _ = niche_of(needs)
        end = self.clock()
        if venue == "kalshi":
            # The first dry run's agents asked for this themselves: one day of hourly markets is 17
            # active blocks and a week of daily ones is 7, against the 30 the replay gate needs.
            days = self.settings.kalshi_replay_days * (7 if horizon == "day" else 1)
        else:
            days = self.settings.replay_days * (6 if horizon == "day" else 1)
        start_iso, end_iso = now_iso(lambda: end - days * 86400), now_iso(lambda: end)
        watched = needs.get("observe") if isinstance(needs.get("observe"), dict) else {}
        if venue == "alpaca":
            symbols = sorted(str(s) for s in (needs.get("symbols") or []))[:12]
            # What the strategy watches rides on the same tape, so a replay sees what a wake sees.
            symbols = sorted(set(symbols) | {str(s) for s in (watched.get("symbols") or [])[:6]})
            timeframe = str((needs.get("bars") or {}).get("timeframe") or "5Min")
            warmup = max(1, min(500, int((needs.get("bars") or {}).get("limit") or 120)))
            key = f"alpaca:{','.join(symbols)}:{timeframe}:{warmup}:{horizon}:{start_iso[:10]}"
            build = lambda: self.alpaca_data.tape(symbols, timeframe, start=start_iso, end=end_iso, horizon=horizon, warmup_bars=warmup)  # noqa: E731
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
            key = f"kalshi:{','.join(series)}:{horizon}:{step}:{markets}:{start_iso[:10]}:{','.join(under)}:{observed_timeframe}:{observed_limit}"

            def build(series=series, under=under, step=step, markets=markets, start_iso=start_iso, end_iso=end_iso, horizon=horizon):
                tape = self.kalshi_data.tape(series, start=start_iso, end=end_iso, horizon=horizon, max_markets=markets, step_seconds=step)
                bars = self._underlier_bars(under, start_iso, end_iso, timeframe=observed_timeframe, warmup=observed_limit)
                if bars:
                    tape["observed_bars"] = bars
                    tape["observed_timeframe"] = observed_timeframe
                return tape
        with self._tape_lock:  # one build at a time: two agents of one family want the same tape
            hit = self._tapes.get(key)
            if hit is None or end - hit[0] > 86400:
                self._tapes[key] = (end, build())
            return key, self._tapes[key][1]

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
        if self.campaigns and not self.pacer.may_spend("sail"):
            raise ValueError("campaign allowance is closed")
        tape_id, tape = self.tape_for(needs)
        observed = needs.get("observe") or {}
        if needs.get("venue") == "kalshi" and any(not (tape.get("observed_bars") or {}).get(s) for s in observed.get("symbols") or []):
            raise ValueError("unsupported input: required observed bars are missing")
        if needs.get("venue") == "alpaca" and observed.get("series"):
            raise ValueError("unsupported input: cross-venue event observations are not recorded on equity tapes")
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
        return {**run.result, "experiment": artifact}, attempt["tape"]

    def _background(self, key: str, work: Callable[..., Any], *args: Any) -> bool:
        """Run slow work beside the tick. One job per key at a time; failures become alerts."""
        running = self._jobs.get(key)
        if running is not None and running.is_alive():
            return False

        lane = self._lanes["research" if key.startswith("research:") else "replay" if key.startswith("replay") else "ops"]
        with self._state_lock:
            self._job_status[key] = {"queued_at": self.clock(), "started_at": None}

        def job() -> None:
            with lane:
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
        for thread in list(self._jobs.values()):
            thread.join(timeout)

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
        try:
            result, tape_id = self._run_replay(agent, agent.code, agent.needs, agent.params)
        except Exception as exc:  # noqa: BLE001 - no tape or no box: try again next wake
            self.alert("warning", f"{agent.id}: replay could not run ({type(exc).__name__}: {str(exc)[:200]})")
            return {"agent": agent.id, "skipped": "replay unavailable"}
        crash = self._crashed(result)
        if crash:
            self.alert("warning", f"{agent.id}: its replay was not run ({crash[:160]}); it is not counted as a trial and will be tried again")
            return {"agent": agent.id, "skipped": f"the replay could not be run: {crash[:120]}"}
        with self._lifecycle_lock:
            current = self._generation(agent.id) == generation
            if current:
                with self._state_lock:
                    self._state["tried"][agent.id] = agent.code_sha256
            # A stale replay still consumed a trial, but cannot qualify or mark a replacement
            # strategy as tested. Its captured code and parameters remain on the trial row.
            verdict = self.evaluator.record_trial(agent.id, agent.family, result, tape_id=tape_id,
                                                  promote=current, lineage=self.registry.lineage(agent.id))
            if verdict.decision == "promote":
                self.seat(self.registry.get(agent.id))
        return {"agent": agent.id, "replay": verdict.decision, "reasons": verdict.numbers.get("reasons")}

    def _candidate_replay(self, agent: Agent, code: str) -> dict[str, Any]:
        """The researcher's `replay` tool: a counted trial of candidate code, never a promotion."""
        described = self.sandbox.needs(PROBE_BOX, code)
        self._charge_box(agent.id, described, note="reading a candidate's NEEDS")
        info = described.result
        if not info.get("ok"):
            return {"passed": False, "error": info.get("error"), "numbers": {}}
        try:
            venue, horizon, _ = niche_of(info["needs"])
            if (venue, horizon) != (agent.venue, agent.horizon):
                return {"passed": False, "error": "a candidate must stay on your venue and horizon", "numbers": {}}
            niche = self.niche_of(agent)
            if niche is not None:
                info["needs"] = niches_module.constrain(info["needs"], niche)
            if niche is not None and not niche.replay:
                # No history to walk: the candidate must at least decide on what its parent sees now.
                # It is not a counted trial and proves no edge; its child answers on paper.
                book = self.book_of(agent)
                ctx = self.snapshot(agent, book) if book is not None else None
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
                return {"passed": ok, "error": None if ok else (run.result.get("error") if run else "no book"), "needs": info["needs"], "params": info.get("params") or {},
                        "numbers": {"passed": ok, "untested": blind, "reasons": [] if ok else ["it did not run on the live view"], "note": note}}
            result, tape_id = self._run_replay(agent, code, info["needs"], info.get("params") or {})
        except Exception as exc:  # noqa: BLE001
            return {"passed": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "numbers": {}}
        crash = self._crashed(result)
        if crash:
            self.alert("warning", f"{agent.id}: a candidate's replay was not run ({crash[:160]}); it is not counted as a trial")
            return {"passed": False, "error": f"the replay could not be run and is NOT a trial against you: {crash[:160]}. "
                                              "Ask for a smaller question of the tape, or tell the House with `request_tool`.",
                    "numbers": {}, "needs": info["needs"], "params": info.get("params") or {}}
        verdict = self.evaluator.record_trial(agent.id, agent.family, result, tape_id=tape_id, promote=False, lineage=self.registry.lineage(agent.id))
        return {"passed": bool(verdict.numbers.get("passed")), "numbers": verdict.numbers, "needs": info["needs"], "params": info.get("params") or {},
                "digest": result.get("digest")}

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
            if verdict.decision not in ("die", "eligible") and rung >= 2:
                drift = self.evaluator.drift(agent.id, book.name, agent.horizon)
                if drift.decision == "demote":
                    self._move_books(agent, book)
                    return drift
        if verdict.decision == "die":
            self.kill(agent, "evidence", verdict.reason, expected_generation=generation)
        elif verdict.decision == "eligible":
            self._promote(agent, verdict, expected_generation=generation)
        return verdict

    def _promote(self, agent: Agent, verdict: Verdict, *, expected_generation: tuple | None = None) -> None:
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None or (expected_generation is not None and generation != expected_generation):
                return
            agent = deepcopy(self.registry.get(agent.id))
            rung = self.evaluator.rung(agent.id)
            if rung != verdict.rung:
                return
            if rung >= 1 and self.campaigns and not self.campaigns.policy["allow_new_live_capital"]:
                return
            if rung == 1:
                if not self.settings.real_money or REAL_BOOK[agent.venue] not in self.books:
                    return  # it stays eligible on paper until the owner turns real money on
                state = self.tuition()
                if not state["room"]:
                    if not self._state.get("tuition_told"):
                        self._state["tuition_told"] = True
                        self.alert("warning", f"{agent.id} cleared the paper screen and was not promoted: the micro rung has "
                                              f"{state['seated']} of {state['max_agents']} agents seated and ${state['headroom_usd']:.2f} of "
                                              f"headroom under its ${state['limit_usd']} tuition. It waits on paper.")
                    return
                self._state["tuition_told"] = False
                if self.auditor is None or not self._audit_due(agent):
                    return
        if rung == 1:
            audit = self.auditor.audit(agent, verdict)  # the provider never holds the lifecycle lock
            if not audit.get("approve"):
                return  # it stays on paper, where its record is the auditor's counterfactual
        with self._lifecycle_lock:
            if self._generation(agent.id) != generation or (rung == 1 and not self.tuition()["room"]):
                return
            agent = self.registry.get(agent.id)
            old = self.book_of(agent)
            self.evaluator.promote(agent.id, rung + 1, verdict.reason, verdict.numbers)
            if rung == 1 and old is not None:
                self._move_books(agent, old)

    def _run_backup(self) -> None:
        row = self.backup.run()
        if not row.get("ok"):
            self.alert("error", f"The daily backup of the House box failed ({row.get('error')}). The ledger lives on one disk until one succeeds.")

    # -------------------------------------------------------------- expedition
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
        if not self._state.get("niche_live"):
            return self.clock() - float(self._state.get("last_niche_try") or 0) >= 1800  # never surveyed yet: every half hour until one works
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
    def tuition(self) -> dict[str, Any]:
        """What the micro rung has cost so far, and whether it may take another agent.

        The paper screen lets through agents with no proven edge, on purpose: real fills are the
        test. What that may cost is a number in the constitution, not a statistic. The cost is
        the net loss of every real-money account that has never earned rung 3 (a swept account
        counts what it lost: its equity is zero and what was not returned is still staked). A
        new agent is seated only while every active micro stake, the remaining risk of abandoned
        accounts, and its own stake fit under the loss line. A drawdown stop is not a guaranteed
        exit price: an option or a contract held to settlement can lose its entire purchase."""
        rules = CONSTITUTION["tuition"]
        active = {agent.id for agent in self.registry.living() if self.evaluator.rung(agent.id) == 2}
        stake = Decimal(CONSTITUTION["rungs"]["2"]["stake_usd"])
        pnl, worst_loss, pending_accounts = ZERO, ZERO, 0
        accounted = set()
        for book in self.books.values():
            if not book.real_money:
                continue
            for agent_id in book.agents():
                if self.evaluator.max_rung(agent_id) < 3:
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
        worst_loss += sum((stake for agent_id in active - accounted if self.evaluator.max_rung(agent_id) < 3), ZERO)
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
        state = self.tuition()
        if not state["closed"]:
            self._state["tuition_closed"] = False
            return
        for agent in self.registry.living():
            if self.evaluator.rung(agent.id) == 2:
                old = self.book_of(agent)
                self.evaluator.demote(agent.id, f"the micro rung's tuition of ${state['limit_usd']} is spent", {"spent_usd": str(state["spent_usd"])})
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
                                "or a change to `tuition.max_loss_usd` in the constitution.")

    def _audit_due(self, agent: Agent) -> bool:
        """An audit is about a quarter of a dollar, charged to the agent. A vetoed agent is not
        audited again at every look: it waits out a cooldown on paper (where its record is the
        auditor's counterfactual), and no agent is audited that cannot pay for it and live.

        An audit that did not happen -- the call refused, the answer unreadable -- is not a verdict
        and must not cost the agent a day at the top of the ladder for the gate's own malfunction.
        It waits the short cooldown instead, long enough not to hammer a frontier that is down."""
        rules = self.game.get("audit") or {}
        if self.economy.balance(agent.id) < Decimal(str(rules.get("min_credits_usd", "0.60"))):
            return False
        last = self.ledger.last("audit.verdict", agent=agent.id)
        if last is None:
            return True
        hours = float(rules.get("error_cooldown_hours", 0.5) if last.payload.get("error") else rules.get("cooldown_hours", 72))
        return self.clock() - _epoch(last.at) >= hours * 3600

    def _move_books(self, agent: Agent, old: Book) -> None:
        """Leave one book for another: cancel, sell what can be sold, and take the stake back."""
        self._wind_down(agent, old)
        self.seat(agent)

    def _wind_down(self, agent: Agent, book: Book) -> None:
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
            exits.append(Intent.new(agent=agent.id, instrument=holding.instrument, side="sell", quantity=quantity,
                                    reason="the House is closing this account", created_at=now, nonce=f"wind-down:{now}"))
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
                    self._wind_down(agent, book)
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
             staked_by_house: bool = False) -> Agent | None:
        """A rich agent has a child and endows it. With no new code the child is a mechanical
        mutation of the parent's parameters; either way it answers for itself from replay up,
        unless its code already passed replay as its parent's candidate.

        `staked_by_house`: the child's code is a research candidate that PASSED replay and its
        parent cannot afford the endowment. The House stakes it from the pool instead (at most one
        a parent a day): an agent above rung 0 cannot edit itself, so without this an improvement
        that research found and replay confirmed would wait weeks for its parent to save up."""
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
        child_params = dict(params) if params is not None else (parent.params if code else mutate(parent.params, seed=f"{parent.id}:{len(self.registry.agents)}"))
        child = self.spawn(parent.line or parent.name, parent.family, child_code, parent=parent.id, params=child_params, reason=reason or "a parameter mutation of its parent",
                           endowment=rules["endowment_usd"] if staked_by_house else None)
        if staked_by_house:
            self._state["last_staked"][parent.id] = self.clock()
        else:
            self.economy.transfer(parent.id, child.id, rules["fork_endowment_usd"], "fork endowment")
        forked = False
        try:
            forked = bool(self.sandbox.fork(parent.id, child.id))
        except SandboxError as exc:
            self.alert("warning", f"{child.id}: could not fork its parent's box, starting from the clean image ({str(exc)[:160]})")
        self.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["endowment_usd" if staked_by_house else "fork_endowment_usd"], "box_forked": forked,
                                            "reason": reason, "new_code": bool(code), "staked_by": "house" if staked_by_house else "parent"}, agent=parent.id)
        if passed_replay:
            self.evaluator.seat(child.id, 1, "its code passed replay as its parent's candidate")
            self._state["tried"][child.id] = child.code_sha256
            self.seat(child)
        return child

    # --------------------------------------------------------------- research
    def research_due(self, agent: Agent) -> bool:
        if not agent.alive or self.researcher is None or not self.settings.research:
            return False
        rules = self.game.get("research") or {}
        if self.economy.balance(agent.id) <= Decimal(str(rules.get("min_credits_usd", "0.10"))) * 2:
            return False
        if not self.pacer.may_spend("sail"):
            return False  # today's share of the expedition's Sail budget is spent (or the expedition is over)
        if self.deploying():
            return False  # a restart is minutes away and would throw the pass away half-read
        last = float(self._state["last_research"].get(agent.id) or 0)
        return self.clock() - last >= self.research_interval_hours(agent) * 3600

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

    def _weakest(self, rules: Mapping[str, Any]) -> Agent | None:
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
        nothing is judged by nobody and costs a box and a seat for as long as it is left there."""
        epoch = float(rules["epoch_seconds"])
        grace = float(rules.get("displace_after_epochs", 2)) * epoch
        now = self.clock()
        rank = []
        for standing in self.standings():
            agent = self.registry.get(standing.agent)
            if standing.rung >= 2 or standing.mean_growth > 0:
                continue
            opportunity = _epoch(agent.born_at)
            niche = self.niche_of(agent)
            if standing.rung == 1 and niche is not None and niche.asset_class in ("equity", "option"):
                # The rebuilt league was born on a Saturday. Twelve wall-clock hours later
                # its equity agents were displaced before their first market session. Start
                # their paper-seat grace at an actual offered opportunity (or a legacy fill),
                # not at a weekend birth. Replay-only agents still have their normal deadline.
                first = next((e for e in self.ledger.iter(kinds=("agent.woke", "book.fill"), agent=agent.id)
                              if e.kind == "book.fill" or (e.payload.get("ok") and int(e.payload.get("offered") or 0) > 0)), None)
                if first is None:
                    continue
                opportunity = max(opportunity, _epoch(first.at))
            if now - opportunity < grace:
                continue
            rank.append((standing.active_blocks > 0, standing.mean_growth, standing.active_blocks,
                         float(self.economy.balance(agent.id)), agent))
        rank.sort(key=lambda row: row[:4])  # has it traded at all, then growth, then how much, then its purse
        return rank[0][4] if rank else None

    def research_order(self) -> list[Agent]:
        """Who gets asked first when the day's frontier allowance is nearly all the floor has.

        Twenty-eight agents on a three-hour cadence want more passes in a day than the expedition
        funds, so the allowance -- not the cadence -- is what really decides who researches. Taken
        in the order they were born, the same agents would claim it every morning and the youngest
        desks would never research at all. Stuck first, then whoever has waited longest."""
        return sorted(self.registry.living(),
                      key=lambda a: (0 if self.idle_reason(a) else 1, float(self._state["last_research"].get(a.id) or 0)))

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
        """How long an agent waits between research passes. The game file's number, halved (never
        under an hour) while today's Sail spending is running behind the clock: the owner wants
        the expedition's budget used, and an allowance still unspent at noon is research not done.
        An agent that cannot act at all waits the idle interval instead -- it has nothing else to
        spend its time on, and every wake it sits out is a wake it did not learn from."""
        base = float((self.game.get("research") or {}).get("min_hours_between", 6))
        if agent is not None and self.idle_reason(agent):
            base = min(base, float((self.game.get("research") or {}).get("idle", {}).get("min_hours_between", 1)))
        return max(1.0, base / 2) if self.behind_the_clock("sail") else base

    def _research_if_due(self, agent: Agent) -> Any:
        """Recheck after waiting for a research worker: a queued job owns no budget or seat."""
        current = self.registry.get(agent.id)
        if current is None or not self.research_due(current):
            return None
        if self.budget is not None and self.budget.mode == "stopped":
            return None
        return self.research(current)

    def research(self, agent: Agent) -> Any:
        with self._lifecycle_lock:
            generation = self._generation(agent.id)
            if generation is None:
                return None
            agent = deepcopy(self.registry.get(agent.id))
            rung = self.evaluator.rung(agent.id)
            standing = {
                "rung": rung, "credits_usd": format(self.economy.balance(agent.id), "f"),
                "blocks": len(self.evaluator.blocks(agent.id)),
                "last_trial": next((e.payload for e in reversed(list(self.ledger.iter(kinds="eval.trial", agent=agent.id)))), None),
                "last_look": next((e.payload for e in reversed(list(self.ledger.iter(kinds="eval.verdict", agent=agent.id))) if e.payload.get("decision") == "look"), None),
                "can_fork": self.economy.can_fork(agent.id),
                "recent_trades": self._recent_trades(agent.id),
                "idle": {**self.idle_run(agent), "why_now": self.idle_reason(agent)},
                "rewrites_in_place": rung == 0 or (rung == 1 and self.record_is_empty(agent)),
            }
        try:
            outcome = self.researcher.research(agent, standing, session=f"research:{agent.id}:{int(self.clock())}")
        finally:
            with self._lifecycle_lock:
                with self._state_lock:
                    if self._generation(agent.id) is not None:
                        self._state["last_research"][agent.id] = self.clock()  # a failing provider is not retried every tick
        with self._lifecycle_lock:
            candidate = self._commit_research(agent.id, generation, outcome)
        if candidate:
            # Forking probes and copies a sandbox. Its parent strategy was validated above;
            # these slow operations do not block decisions or settlements on the other desks.
            try:
                child = self.fork(agent, code=candidate["code"], params=candidate["params"], reason=candidate["purpose"], passed_replay=True,
                                  staked_by_house=not self.economy.can_fork(agent.id))
            except Exception as exc:
                self.ledger.append("agent.research", {"tool": "candidate", "status": "fork_error",
                    "reason": f"{type(exc).__name__}: {str(exc)[:200]}", "_candidate": candidate}, agent=agent.id)
                raise
            self.ledger.append("agent.research", {"tool": "candidate", "status": "forked" if child else "deferred",
                "child": child.id if child else None, "reason": "a child was admitted" if child else "a child was not admitted",
                "_candidate": candidate}, agent=agent.id)
        return outcome

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
        barren = self.idle_run(agent)["barren"]
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
            if not (traded and rung == 1 and self.record_is_empty(agent) and barren >= int((self.game.get("research") or {}).get("idle", {}).get("barren_wakes", 10))):
                candidate = None
        if candidate and outcome.consulted and candidate["code"].strip() == outcome.consulted.strip():
            candidate = {**candidate, "purpose": "Merton wrote this file for it: " + candidate["purpose"]}
        if candidate:
            if rung == 0 or (rung == 1 and self.record_is_empty(agent)):
                # Empty paper records can restart in place. A real-money identity always forks
                # new code: its existing code earned the paper screen and audit, even before
                # its first real trade has created a record in the current book.
                was = self.registry.get(agent.id).code_sha256
                self.registry.adopt(agent.id, code=candidate["code"], needs=candidate["needs"], params=candidate["params"], reason=candidate["purpose"])
                self._state["tried"][agent.id] = self.registry.get(agent.id).code_sha256
                self._state["idle"].pop(agent.id, None)  # new rules, a fresh count of the wakes they sit out
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
        rows = []
        for entry in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent_id):
            p = entry.payload
            pnl = p.get("pnl") if entry.kind == "book.settle" else p.get("realized")
            if pnl is None or p.get("source") == "dust":
                continue
            inst = p.get("instrument") or {}
            rows.append({"at": entry.at[:16], "what": inst.get("market_id") or inst.get("symbol"), "leg": inst.get("right"), "pnl_usd": str(pnl),
                         "result": p.get("result") or "sold", "real_money": bool(p.get("real_money")), "why": str(p.get("reason") or p.get("entry_reason") or "")[:160]})
        return rows[-limit:]

    # ----------------------------------------------------------------- economy
    def standing_of(self, agent_id: str) -> dict[str, Any]:
        """One agent's record at its current rung: what it has earned the right to ask for."""
        agent = self.registry.get(agent_id)
        rung = self.evaluator.rung(agent_id)
        book = self.book_of(agent)
        rows = self.evaluator.blocks(agent_id, since_seq=self.evaluator._rung_entered(agent_id), book=book.name) if rung >= 1 and book else []
        growth = [float(r["log_growth"]) for r in rows]
        return {"rung": rung, "active_blocks": sum(1 for r in rows if r.get("active")),
                "mean_growth": (sum(growth) / len(growth)) if growth else 0.0, "niche": agent.niche}

    def standings(self) -> list[Standing]:
        epoch = float(self.game["economy"]["epoch_seconds"])
        out = []
        for agent in self.registry.living():
            rung = self.evaluator.rung(agent.id)
            entered = self.evaluator._rung_entered(agent.id)
            book = self.book_of(agent)
            rows = self.evaluator.blocks(agent.id, since_seq=entered, book=book.name) if rung >= 1 and book else []
            growth = [float(r["log_growth"]) for r in rows]
            active = sum(1 for r in rows if r.get("active"))
            out.append(Standing(agent.id, agent.niche, rung, (sum(growth) / len(growth)) if growth else 0.0, active,
                                working=self._working(agent, epoch)))
        return out

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

    def keep_population(self, *, refill: bool = True) -> None:
        rules = self.game["economy"]
        deadline = float(rules.get("replay_deadline_epochs", 3)) * float(rules["epoch_seconds"])
        broke = Decimal(str((self.game.get("research") or {}).get("min_credits_usd", "0.10"))) * 2
        stuck = int(rules.get("idle_broke_wakes", 30))
        for agent in self.registry.living():
            if not self.economy.alive(agent.id):
                self.kill(agent, "credits", "its compute credits reached zero")
            elif self.evaluator.rung(agent.id) == 0 and self.clock() - _epoch(agent.born_at) > deadline:
                self.kill(agent, "never qualified", f"it did not pass replay within {rules.get('replay_deadline_epochs', 3)} epochs of its birth")
            elif self.idle_run(agent)["barren"] >= stuck and self.economy.balance(agent.id) <= broke:
                # Neither able to trade nor able to buy a new idea: it cannot change and it cannot
                # act, and it will sit at this balance for as long as the floor runs, holding a
                # seat on its desk that a newcomer could use. A shut market does not count here --
                # that is the calendar, not the agent.
                self.kill(agent, "stuck", f"{self.idle_run(agent)['barren']} wakes in a row with a live market in front of it and nothing done, "
                                          f"and too few credits left to research its way out")
        for agent in self.registry.living():
            if self.economy.can_fork(agent.id) and self.evaluator.rung(agent.id) >= 1:
                last = float(self._state.setdefault("last_fork", {}).get(agent.id) or 0)
                if self.clock() - last >= float(rules["epoch_seconds"]):
                    self._state["last_fork"][agent.id] = self.clock()
                    self.fork(agent)
        if not refill:
            return
        if len(self.registry.living()) < int(rules["min_population"]):
            self.found()
        self.enroll()
        self._refill(rules)

    def _refill(self, rules: Mapping[str, Any]) -> Agent | None:
        """Keep a seat filled. A death that leaves an empty seat is only useful if something new
        sits in it: before this the House staked a newcomer only below the population FLOOR, so a
        failure shrank the league from 28 towards 12 instead of cycling it. Now it fills up to the
        ceiling, one at a time, and puts the newcomer on the desk that is furthest from full, so
        exploration spreads across the firm instead of converging on whoever is winning."""
        living = self.registry.living()
        if not living:
            return None
        if len(living) >= int(rules["max_population"]):
            # A ceiling with nothing dying under it is a floor that has stopped searching. Measured
            # Sept 20, 2026: thirty-three agents born in twelve hours and NOT ONE dead, four births
            # from a league that could never try anything again. So the last seat is a tournament:
            # a newcomer takes it from the worst agent that has had its chance, which is the
            # selection pressure the ceiling was meant to create and never did.
            loser = self._weakest(rules)
            if loser is None:
                return None
            self.kill(loser, "displaced", self.postmortem(loser, "displaced",
                                                          "the league was full and it was the weakest agent with a fair chance behind it"))
            living = self.registry.living()
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
        room = [n for n in self.niches.values() if not n.dormant and self.members(n.id) < n.max_members]
        seats = {n.id: n.max_members - self.members(n.id) for n in room}
        here = [a for a in living if a.specialty in seats] or living
        if seats:
            widest = max(seats.values())
            here = [a for a in here if seats.get(a.specialty) == widest] or here
        best = max(here, key=lambda a: (self.evaluator.rung(a.id), self.economy.balance(a.id)))
        with self._state_lock:
            self._state["last_newcomer"]["at"] = self.clock()
        child = self.spawn(best.line or best.name, best.family, best.code, parent=best.id, endowment=rules["endowment_usd"],
                           params=mutate(best.params, seed=f"newcomer:{len(self.registry.agents)}"),
                           reason=f"a House-staked mutation of {best.id}: its desk had the most room, and the league was {len(living)} of {rules['max_population']}")
        self.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["endowment_usd"], "box_forked": False,
                                            "reason": "population", "new_code": False}, agent=best.id)
        return child

    # -------------------------------------------------------------------- tick
    def tick(self) -> dict[str, Any]:
        summary: dict[str, Any] = {"at": now_iso(self.clock), "woke": [], "orders": 0, "deaths": [], "reconciled": {}}
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
        # Past the monthly compute line only agents holding real money are woken, so they can exit.
        open_for_business = self.budget is None or self.budget.check() == "open"
        if self.campaigns:
            meter = getattr(self.provider, "transport", None)
            metered = bool(meter and hasattr(meter, "refresh") and meter.refresh())
            open_for_business = open_for_business and metered and self.pacer.may_spend("sail")
        summary["budget"] = "open" if open_for_business else "stopped"
        batches: dict[str, list[Mapping[str, Any]]] = {}
        waking = [a for a in self.due() if self.economy.alive(a.id) and (open_for_business or self._holds_real_money(a))]
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
        for name, book in self.books.items():
            if now - float(self._state["last_mark"].get(name) or 0) < self.settings.mark_every_seconds:
                continue
            self._state["last_mark"][name] = now
            try:
                book.poll()
                book.mark()
                result = book.reconcile()
                summary["reconciled"][name] = result.ok
                if not result.ok:
                    self.alert("error", f"{name} does not reconcile: {result.detail}")
            except Exception as exc:  # noqa: BLE001
                self.alert("warning", f"{name}: could not mark or reconcile ({type(exc).__name__}: {str(exc)[:200]})")
            for agent in self.registry.living():
                if self.book_of(agent) is book:
                    self.judge(agent)
                elif agent.id in book.accounts:
                    self._retry_wind_down(agent, book)
                    self._observe_wind_down(agent, book)
            for agent in self.registry.dead():
                if agent.id in book.accounts:
                    self._retry_wind_down(agent, book)
                    self._observe_wind_down(agent, book)
                    self._sweep(agent.id, book)
        for agent in self.research_order() if open_for_business else []:
            if self.research_due(agent):
                # Stamped when the pass ENDS (in `research`), not when it is queued: on the first
                # production day every agent was stamped at 18:02, queued, and lost to a restart,
                # so nobody researched for an hour and a half. A pass in hand is not queued twice.
                self._background(f"research:{agent.id}", self._research_if_due, agent)
        if open_for_business and self.survey_due():
            self._background("niche-survey", self.survey_niches)  # stamped when it ends; one in hand is not started twice
        if self.backup is not None and self.backup.due():
            self._background("backup", self._run_backup)
        if self.updater is not None and self.updater.due():
            self._background("update", self._update)
        if self.budget is not None and getattr(self.budget, "pacer", None) is None:
            self.budget.pacer = self.pacer
        self._pace_inference()
        if open_for_business and self.merton is not None:
            for role in self.merton.due():
                # One role at a time against today's allowance: a pass is a dime to a few dollars,
                # and its cost is only known when it ends.
                if self.pacer.may_spend("openai") and not any(key.startswith("merton:") and key != "merton:follow" and job.is_alive() for key, job in self._jobs.items()):
                    self._background(f"merton:{role}", self.merton.run, role)
            self._background("merton:follow", self.merton.follow)
        if open_for_business and self.economy.payout_due():
            self.learn()
            for agent in self.registry.living():
                if self.evaluator.rung(agent.id) >= 3:
                    capital.resize(self, agent)
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
        self.keep_population(refill=open_for_business)
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
        health = {
            "at": summary["at"], "living": len(self.registry.living()), "dead": len(self.registry.dead()),
            "books": {name: {"frozen": book.frozen, "open_orders": len(book.open_orders())} for name, book in self.books.items()},
            "ledger_seq": self.ledger.head()[0], "real_money": self.settings.real_money,
            "release": Path(__file__).resolve().parents[1].name,
            "tick_duration_seconds": round(max(now - _epoch(summary["at"]), 0), 3),
            "background_jobs": jobs,
            "recordings": self.recorder.stats(),
            "campaign": self.campaigns.report() if self.campaigns else None,
        }
        tmp = self.root / "health.tmp"
        tmp.write_text(json.dumps(health, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.root / "health.json")

    def close(self, *, wait: float | None = 5.0) -> None:
        self.wait(wait)
        self._save_state()
        self.recorder.close()
        self.ledger.close()
        if self.campaigns:
            self.campaigns.close()


def _epoch(iso: str) -> float:
    from ltcm.broker import instant

    parsed = instant(iso)
    return parsed.timestamp() if parsed else 0.0


def mutate(params: Mapping[str, Any], *, seed: str, scale: float = 0.2) -> dict[str, Any]:
    """A child's parameters: each number moved by up to `scale`, deterministically from the seed.
    Integers stay integers, booleans and everything else are inherited unchanged."""
    rng = random.Random(seed)
    out: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            out[key] = value
        elif isinstance(value, int):
            out[key] = max(1, int(round(value * (1 + rng.uniform(-scale, scale))))) if value > 0 else value
        else:
            out[key] = round(value * (1 + rng.uniform(-scale, scale)), 6)
    return out


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
