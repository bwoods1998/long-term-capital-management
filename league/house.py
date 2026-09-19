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
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from ltcm.broker import Instrument, money

from . import seeds as seeds_module
from .agents import Agent, Registry, niche_of
from .book import Book, Intent, Limits, step_of
from .commons import Commons
from .constitution import CONSTITUTION, digest as constitution_digest
from .economy import Economy, Standing, load_game
from .evaluator import Evaluator, Verdict
from .fees import Fees
from .ledger import HOUSE, Ledger, now_iso
from .researcher import Researcher
from .rules import rules_text
from .sandbox import SandboxError
from .venues import family_of, instrument_for, market_hours

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
    wake_workers: int = 6
    slow_workers: int = 2  # replays and research passes run beside the tick, never inside it
    kalshi_replay_days: int = 7
    kalshi_replay_markets: int = 300


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
        self.registry = Registry(self.ledger)
        self.economy = Economy(self.ledger, self.game, clock=clock)
        self.evaluator = Evaluator(self.ledger, clock=clock)
        self.commons = commons or Commons(self.ledger)
        self.sandbox = sandbox
        self.alpaca_data = alpaca_data
        self.kalshi_data = kalshi_data
        self.provider = provider
        self.auditor = auditor
        self.publisher = publisher
        self.budget = budget
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
            )
        self._state_path = self.root / "house.json"
        self._state = self._load_state()
        self._data_cache: dict[str, tuple[float, Any]] = {}
        self._tapes: dict[str, tuple[float, dict[str, Any]]] = {}
        self._tape_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._slow = ThreadPoolExecutor(max_workers=max(1, self.settings.slow_workers), thread_name_prefix="league-slow")
        self._jobs: dict[str, Future] = {}
        self.researcher = None
        if provider is not None:
            self.researcher = Researcher(
                ledger=self.ledger, provider=provider, commons=self.commons, economy=self.economy,
                rules=rules_text(self.game), contract=CONTRACT_PATH.read_text(encoding="utf-8"),
                run_replay=self._candidate_replay, settings=self.game.get("research") or {}, clock=clock,
            )
        self._record_start()

    # ------------------------------------------------------------------ state
    def _load_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        for key in ("next_wake", "memory", "last_research", "tried", "last_mark", "settled"):
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
             "sandbox": type(self.sandbox).__name__},
        )

    def alert(self, level: str, text: str) -> None:
        self.ledger.append("ops.alert", {"level": level, "text": str(text)[:1000]})

    def stopped(self) -> bool:
        return (self.root / "STOP").exists()

    # ------------------------------------------------------------ population
    def found(self, names: list[str] | None = None) -> list[Agent]:
        """Seed the first population (idempotent: a seed already born is not born again)."""
        born = []
        existing = {a.name for a in self.registry.agents.values()} | set(self.registry.agents)
        for seed in seeds_module.all_seeds():
            if names is not None and seed["name"] not in names:
                continue
            if seed["name"] in existing:
                continue
            agent = self.spawn(seed["name"], seed["family"], seed["code"], reason=seed["why"])
            # The founders are the owner's priors (what the first run measured, and published
            # research): they start their forward test at once, because paper costs nothing and
            # forward evidence is the evidence that counts. Their replay is still run and still
            # counts as their family's first trial. Everything born later must pass replay first.
            self.evaluator.seat(agent.id, 1, "a founding seed: forward-tested from the first day")
            self.seat(agent)
            born.append(agent)
        return born

    def spawn(self, name: str, family: str, code: str, *, parent: str | None = None, reason: str = "",
              params: Mapping[str, Any] | None = None, endowment: Any | None = None) -> Agent:
        # A strategy's NEEDS are read by running its module body, so that happens in a box too: one
        # sealed probe box the House keeps for the purpose, never the House's own process.
        described = self.sandbox.needs(PROBE_BOX, code)
        info = described.result
        if not info.get("ok"):
            raise ValueError(f"{name}: {info.get('error')}")
        niche_of(info["needs"])
        agent = self.registry.born(
            name=name, family=family, code=code, needs=info["needs"], params={**info.get("params", {}), **dict(params or {})},
            parent=parent, reason=reason,
        )
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

    def _limits(self, rung: int) -> Limits:
        row = CONSTITUTION["rungs"][str(min(max(rung, 1), 2))]
        return Limits(Decimal(row["max_position_usd"]), Decimal(row["max_order_usd"]))

    def seat(self, agent: Agent) -> None:
        """Give an agent its limits and its stake on the book of its rung (once per book)."""
        rung = self.evaluator.rung(agent.id)
        book = self.book_of(agent)
        if rung < 1 or book is None:
            return
        book.limits[agent.id] = self._limits(rung if book.real_money else 1)
        if book.account(agent.id).staked <= 0:
            stake = CONSTITUTION["rungs"]["2" if book.real_money else "1"]["stake_usd"]
            book.stake(agent.id, stake, note=f"rung {rung} stake")

    # ------------------------------------------------------------------- data
    def _cached(self, key: str, ttl: float, build: Callable[[], Any]) -> Any:
        hit = self._data_cache.get(key)
        if hit and self.clock() - hit[0] < ttl:
            return hit[1]
        value = build()
        self._data_cache[key] = (self.clock(), value)
        return value

    def snapshot(self, agent: Agent, book: Book) -> dict[str, Any]:
        """Everything a strategy sees, as plain data (floats: the box converts nothing back)."""
        needs = agent.needs
        account = book.account(agent.id)
        limits = book.limits.get(agent.id) or self._limits(1)
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
            else:
                row["symbol"] = inst.market_id or inst.symbol
            ctx["open_orders"].append(row)
        if agent.venue == "alpaca":
            symbols = [str(s) for s in (needs.get("symbols") or [])][:12]
            bars = dict(needs.get("bars") or {})
            timeframe = str(bars.get("timeframe") or "5Min")
            limit = max(1, min(int(bars.get("limit") or 120), 500))
            key = f"bars:{','.join(symbols)}:{timeframe}:{limit}"
            ctx["bars"] = self._cached(key, 50, lambda: self.alpaca_data.bars(symbols, timeframe, limit=limit))
            ctx["quotes"] = self._cached(f"quotes:{','.join(symbols)}", 20, lambda: self.alpaca_data.quotes(symbols))
        else:
            series = [str(s) for s in (needs.get("series") or [])][:12]
            hours = float(needs.get("max_hours_to_close") or 24)
            ctx["markets"] = self._cached(f"markets:{','.join(series)}:{hours}", 50, lambda: self.kalshi_data.markets(series, max_hours_to_close=hours))
        return ctx

    # ------------------------------------------------------------------- wake
    def due(self) -> list[Agent]:
        now = self.clock()
        out = [a for a in self.registry.living() if float(self._state["next_wake"].get(a.id) or 0) <= now]
        return out[: self.settings.max_wakes_per_tick]

    def wake(self, agent: Agent) -> dict[str, Any]:
        """One wake of one agent. Returns what happened, for the caller and the tests."""
        self._state["next_wake"][agent.id] = self.clock() + agent.wake_minutes * 60
        rung = self.evaluator.rung(agent.id)
        if self._state["tried"].get(agent.id) != agent.code_sha256:
            self._background(f"replay:{agent.id}", self._replay_own, agent)  # its code has not had its replay yet
        if rung == 0:
            return {"agent": agent.id, "skipped": "in replay"}
        book = self.book_of(agent)
        if book is None:
            return {"agent": agent.id, "skipped": "no book for its venue"}
        self.seat(agent)
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
        if not result.get("ok"):
            self.ledger.append("agent.woke", {"ok": False, "error": str(result.get("error"))[:400], "book": book.name}, agent=agent.id)
            return {"agent": agent.id, "error": result.get("error")}
        self._state["memory"][agent.id] = result.get("memory") or {}
        thought = str(result.get("thought") or "").strip()
        if thought:
            self.ledger.append("agent.thought", {"text": thought, "phase": "decide", "book": book.name}, agent=agent.id)
        cancelled = [book.cancel(agent.id, order_id).status for order_id in result.get("cancels") or []]
        intents, dropped = self._intents(agent, book, result.get("intents") or [])
        self.ledger.append(
            "agent.woke",
            {"ok": True, "book": book.name, "intents": len(intents), "dropped": dropped, "cancels": len(cancelled), "seconds": result.get("seconds")},
            agent=agent.id,
        )
        return {"agent": agent.id, "book": book.name, "intents": intents, "dropped": dropped}

    def _intents(self, agent: Agent, book: Book, rows: list[Mapping[str, Any]]) -> tuple[list[Intent], list[str]]:
        intents, dropped = [], []
        now = now_iso(self.clock)
        for index, row in enumerate(rows):
            try:
                instrument = instrument_for(book.broker.venue, dict(row))
                side = str(row.get("side") or "").lower()
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
            days = self.settings.kalshi_replay_days * (3 if horizon == "day" else 1)
        else:
            days = self.settings.replay_days * (6 if horizon == "day" else 1)
        start_iso, end_iso = now_iso(lambda: end - days * 86400), now_iso(lambda: end)
        if venue == "alpaca":
            symbols = sorted(str(s) for s in (needs.get("symbols") or []))[:12]
            timeframe = str((needs.get("bars") or {}).get("timeframe") or "5Min")
            key = f"alpaca:{','.join(symbols)}:{timeframe}:{horizon}:{start_iso[:10]}"
            build = lambda: self.alpaca_data.tape(symbols, timeframe, start=start_iso, end=end_iso, horizon=horizon)  # noqa: E731
        else:
            series = sorted(str(s) for s in (needs.get("series") or []))[:12]
            key = f"kalshi:{','.join(series)}:{horizon}:{start_iso[:10]}"
            build = lambda: self.kalshi_data.tape(series, start=start_iso, end=end_iso, horizon=horizon, max_markets=self.settings.kalshi_replay_markets)  # noqa: E731
        with self._tape_lock:  # one build at a time: two agents of one family want the same tape
            hit = self._tapes.get(key)
            if hit is None or end - hit[0] > 86400:
                self._tapes[key] = (end, build())
            return key, self._tapes[key][1]

    def _run_replay(self, agent: Agent, code: str, needs: Mapping[str, Any], params: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        tape_id, tape = self.tape_for(needs)
        row = CONSTITUTION["rungs"]["1"]
        run = self.sandbox.replay(
            agent.id, code, params, tape, stake=float(row["stake_usd"]),
            limits={"max_position_usd": float(row["max_position_usd"]), "max_order_usd": float(row["max_order_usd"])},
            timeout=self.settings.replay_timeout,
        )
        self._charge_box(agent.id, run, note="a replay")
        return run.result, tape_id

    def _background(self, key: str, work: Callable[..., Any], *args: Any) -> bool:
        """Run slow work beside the tick. One job per key at a time; failures become alerts."""
        running = self._jobs.get(key)
        if running is not None and not running.done():
            return False

        def job() -> Any:
            try:
                return work(*args)
            except Exception as exc:  # noqa: BLE001
                self.alert("warning", f"{key} failed ({type(exc).__name__}: {str(exc)[:200]})")
                return None

        self._jobs[key] = self._slow.submit(job)
        return True

    def wait(self, timeout: float | None = None) -> None:
        """Block until the slow work in hand is done (tests, and an orderly stop)."""
        for future in list(self._jobs.values()):
            future.result(timeout=timeout)

    def _replay_own(self, agent: Agent) -> dict[str, Any]:
        """An agent's own code gets one replay, counted as a trial. For an agent on rung 0 it is
        the way up; after it, only research can change its fate."""
        if self._state["tried"].get(agent.id) == agent.code_sha256:
            return {"agent": agent.id, "skipped": "its code has had its replay; research may change it"}
        try:
            result, tape_id = self._run_replay(agent, agent.code, agent.needs, agent.params)
        except Exception as exc:  # noqa: BLE001 - no tape or no box: try again next wake
            self.alert("warning", f"{agent.id}: replay could not run ({type(exc).__name__}: {str(exc)[:200]})")
            return {"agent": agent.id, "skipped": "replay unavailable"}
        with self._state_lock:
            self._state["tried"][agent.id] = agent.code_sha256
        verdict = self.evaluator.record_trial(agent.id, agent.family, result, tape_id=tape_id)
        if verdict.decision == "promote":
            self.seat(agent)
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
            result, tape_id = self._run_replay(agent, code, info["needs"], info.get("params") or {})
        except Exception as exc:  # noqa: BLE001
            return {"passed": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "numbers": {}}
        verdict = self.evaluator.record_trial(agent.id, agent.family, result, tape_id=tape_id, promote=False)
        return {"passed": bool(verdict.numbers.get("passed")), "numbers": verdict.numbers, "needs": info["needs"], "params": info.get("params") or {}}

    # ----------------------------------------------------------------- judging
    def judge(self, agent: Agent) -> Verdict | None:
        book = self.book_of(agent)
        rung = self.evaluator.rung(agent.id)
        if book is None or rung < 1:
            return None
        self.evaluator.observe(agent.id, book.name, agent.horizon)
        verdict = self.evaluator.judge(agent.id, book.name)
        if verdict.decision == "die":
            self.kill(agent, "evidence", verdict.reason)
        elif verdict.decision == "eligible":
            self._promote(agent, verdict)
        elif rung >= 2:
            drift = self.evaluator.drift(agent.id, book.name)
            if drift.decision == "demote":
                self._move_books(agent, book)
                return drift
        return verdict

    def _promote(self, agent: Agent, verdict: Verdict) -> None:
        rung = self.evaluator.rung(agent.id)
        if rung == 1:
            if not self.settings.real_money or REAL_BOOK[agent.venue] not in self.books:
                return  # it stays eligible on paper until the owner turns real money on
            if self.auditor is None:
                return
            audit = self.auditor.audit(agent, verdict)
            if not audit.get("approve"):
                return  # it stays on paper, where its record is the auditor's counterfactual
        old = self.book_of(agent)
        self.evaluator.promote(agent.id, rung + 1, verdict.reason, verdict.numbers)
        if rung == 1 and old is not None:
            self._move_books(agent, old)

    def _move_books(self, agent: Agent, old: Book) -> None:
        """Leave one book for another: cancel, sell what can be sold, and take the stake back."""
        self._wind_down(agent, old)
        self.seat(agent)

    def _wind_down(self, agent: Agent, book: Book) -> None:
        book.cancel_all(agent.id)
        now = now_iso(self.clock)
        exits = []
        for holding in list(book.account(agent.id).holdings.values()):
            if holding.instrument.asset_class == "event":
                continue  # a Kalshi contract is held to settlement: selling a favourite at the bid gives the edge back
            exits.append(Intent.new(agent=agent.id, instrument=holding.instrument, side="sell", quantity=holding.quantity,
                                    reason="the House is closing this account", created_at=now, nonce=f"wind-down:{now}"))
        if exits:
            book.submit(exits)
            book.poll()
        self._sweep(agent.id, book)

    def _sweep(self, agent_id: str, book: Book) -> None:
        """Return a finished account's free cash to the House's side of the book."""
        account = book.account(agent_id)
        if not account.holdings and not book.open_orders(agent_id) and account.cash > 0 and account.staked > 0:
            book.stake(agent_id, -min(account.cash, account.staked), note="account closed")

    # ------------------------------------------------------------------ death
    def kill(self, agent: Agent, cause: str, detail: str = "") -> None:
        if not agent.alive:
            return
        for book in self.books.values():
            if agent.id in book.accounts:
                self._wind_down(agent, book)
        text = self.postmortem(agent, cause, detail)
        self.ledger.append("agent.postmortem", {"text": text, "cause": cause}, agent=agent.id)
        self.commons.playbook_add(f"Post-mortem: {agent.id}", text, source="graveyard", agent=agent.id)
        self.registry.died(agent.id, cause, detail)
        try:
            self.sandbox.retire(agent.id)
        except Exception as exc:  # noqa: BLE001
            self.alert("warning", f"{agent.id}: its box could not be retired ({type(exc).__name__})")
        for key in ("next_wake", "memory", "last_research", "tried"):
            self._state[key].pop(agent.id, None)

    def postmortem(self, agent: Agent, cause: str, detail: str) -> str:
        rung = self.evaluator.rung(agent.id)
        trials = [e.payload for e in self.ledger.iter(kinds="eval.trial", agent=agent.id)]
        blocks = self.evaluator.blocks(agent.id)
        growth = sum(float(b["log_growth"]) for b in blocks)
        spent = sum(Decimal(e.payload["usd"]) for e in self.ledger.iter(kinds="credit.charge", agent=agent.id))
        lines = [
            f"{agent.id} (family {agent.family}, niche {agent.niche}, generation {agent.generation}) died on rung {rung} of {cause}. {detail}".strip(),
            f"It ran {len(trials)} replay trials, traded {len(blocks)} blocks forward for a total log growth of {growth:+.4f}, and spent ${spent:.2f} of compute.",
        ]
        if trials:
            last = trials[-1]
            lines.append(f"Its last replay: Sharpe {last.get('sharpe')}, deflated {last.get('deflated_sharpe')}, {last.get('trades')} trades; " + "; ".join(last.get("reasons") or ["passed"]))
        return " ".join(lines)

    # ------------------------------------------------------------------- forks
    def fork(self, parent: Agent, *, code: str | None = None, params: Mapping[str, Any] | None = None, reason: str = "", passed_replay: bool = False) -> Agent | None:
        """A rich agent has a child and endows it. With no new code the child is a mechanical
        mutation of the parent's parameters; either way it answers for itself from replay up,
        unless its code already passed replay as its parent's candidate."""
        rules = self.game["economy"]
        if len(self.registry.living()) >= int(rules["max_population"]) or not self.economy.can_fork(parent.id):
            return None
        child_code = code or parent.code
        child_params = dict(params) if params is not None else (parent.params if code else mutate(parent.params, seed=f"{parent.id}:{len(self.registry.agents)}"))
        child = self.spawn(parent.name, parent.family, child_code, parent=parent.id, params=child_params, reason=reason or "a parameter mutation of its parent")
        self.economy.transfer(parent.id, child.id, rules["fork_endowment_usd"], "fork endowment")
        forked = False
        try:
            forked = bool(self.sandbox.fork(parent.id, child.id))
        except SandboxError as exc:
            self.alert("warning", f"{child.id}: could not fork its parent's box, starting from the clean image ({str(exc)[:160]})")
        self.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["fork_endowment_usd"], "box_forked": forked, "reason": reason, "new_code": bool(code)}, agent=parent.id)
        if passed_replay:
            self.evaluator.seat(child.id, 1, "its code passed replay as its parent's candidate")
            self._state["tried"][child.id] = child.code_sha256
            self.seat(child)
        return child

    # --------------------------------------------------------------- research
    def research_due(self, agent: Agent) -> bool:
        if self.researcher is None or not self.settings.research:
            return False
        rules = self.game.get("research") or {}
        if self.economy.balance(agent.id) <= Decimal(str(rules.get("min_credits_usd", "0.10"))) * 2:
            return False
        last = float(self._state["last_research"].get(agent.id) or 0)
        return self.clock() - last >= float(rules.get("min_hours_between", 6)) * 3600

    def research(self, agent: Agent) -> Any:
        rung = self.evaluator.rung(agent.id)
        standing = {
            "rung": rung, "credits_usd": format(self.economy.balance(agent.id), "f"),
            "blocks": len(self.evaluator.blocks(agent.id)),
            "last_trial": next((e.payload for e in reversed(list(self.ledger.iter(kinds="eval.trial", agent=agent.id)))), None),
            "last_look": next((e.payload for e in reversed(list(self.ledger.iter(kinds="eval.verdict", agent=agent.id))) if e.payload.get("decision") == "look"), None),
            "can_fork": self.economy.can_fork(agent.id),
        }
        outcome = self.researcher.research(agent, standing, session=f"research:{agent.id}:{int(self.clock())}")
        candidate = outcome.candidate
        if candidate:
            if rung == 0:
                self.registry.adopt(agent.id, code=candidate["code"], needs=candidate["needs"], params=candidate["params"], reason=candidate["purpose"])
                self._state["tried"][agent.id] = self.registry.get(agent.id).code_sha256
                self.evaluator.promote(agent.id, 1, "its new code passed replay against every trial its family has run", candidate["numbers"])
                self.seat(self.registry.get(agent.id))
            else:
                self.fork(agent, code=candidate["code"], params=candidate["params"], reason=candidate["purpose"], passed_replay=True)
        return outcome

    # ----------------------------------------------------------------- economy
    def standings(self) -> list[Standing]:
        out = []
        for agent in self.registry.living():
            rung = self.evaluator.rung(agent.id)
            entered = self.evaluator._rung_entered(agent.id)
            rows = self.evaluator.blocks(agent.id, since_seq=entered) if rung >= 1 else []
            growth = [float(r["log_growth"]) for r in rows]
            out.append(Standing(agent.id, agent.niche, rung, (sum(growth) / len(growth)) if growth else 0.0, sum(1 for r in rows if r.get("active"))))
        return out

    def keep_population(self) -> None:
        rules = self.game["economy"]
        deadline = float(rules.get("replay_deadline_epochs", 3)) * float(rules["epoch_seconds"])
        for agent in self.registry.living():
            if not self.economy.alive(agent.id):
                self.kill(agent, "credits", "its compute credits reached zero")
            elif self.evaluator.rung(agent.id) == 0 and self.clock() - _epoch(agent.born_at) > deadline:
                self.kill(agent, "never qualified", f"it did not pass replay within {rules.get('replay_deadline_epochs', 3)} epochs of its birth")
        for agent in self.registry.living():
            if self.economy.can_fork(agent.id) and self.evaluator.rung(agent.id) >= 1:
                last = float(self._state.setdefault("last_fork", {}).get(agent.id) or 0)
                if self.clock() - last >= float(rules["epoch_seconds"]):
                    self._state["last_fork"][agent.id] = self.clock()
                    self.fork(agent)
        if len(self.registry.living()) < int(rules["min_population"]):
            self.found()
        living = self.registry.living()
        if living and len(living) < int(rules["min_population"]):
            # Every seed has had its life. The House stakes a newcomer: a mutation of whoever
            # stands highest, endowed from the pool like a seed, answering for itself from replay.
            best = max(living, key=lambda a: (self.evaluator.rung(a.id), self.economy.balance(a.id)))
            last = float(self._state.setdefault("last_newcomer", {}).get("at") or 0)
            if self.clock() - last >= float(rules["epoch_seconds"]) / 4:
                self._state["last_newcomer"]["at"] = self.clock()
                child = self.spawn(best.name, best.family, best.code, parent=best.id, endowment=rules["endowment_usd"],
                                   params=mutate(best.params, seed=f"newcomer:{len(self.registry.agents)}"),
                                   reason=f"a House-staked mutation of {best.id}: the population was below its floor")
                self.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["endowment_usd"], "box_forked": False, "reason": "population floor", "new_code": False}, agent=best.id)

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
        summary["budget"] = "open" if open_for_business else "stopped"
        batches: dict[str, list[Intent]] = {}
        waking = [a for a in self.due() if self.economy.alive(a.id) and (open_for_business or self._holds_real_money(a))]
        # Each wake is mostly waiting on the agent's box, so they run side by side; every agent
        # has its own box and its own lock, and the ledger and the books are thread-safe.
        with ThreadPoolExecutor(max_workers=max(1, min(self.settings.wake_workers, len(waking) or 1))) as pool:
            outcomes = list(pool.map(self._wake_safely, waking))
        for agent, outcome in zip(waking, outcomes):
            summary["woke"].append(agent.id)
            if outcome.get("intents"):
                batches.setdefault(outcome["book"], []).extend(outcome["intents"])
        for name, intents in batches.items():
            outcomes = self.books[name].submit(intents)
            summary["orders"] += sum(1 for o in outcomes if o.status not in ("refused", "duplicate"))
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
            for agent in self.registry.dead():
                if agent.id in book.accounts:
                    self._sweep(agent.id, book)
        for agent in self.registry.living() if open_for_business else []:
            if self.research_due(agent):
                with self._state_lock:
                    self._state["last_research"][agent.id] = self.clock()
                self._background(f"research:{agent.id}", self.research, agent)
        if open_for_business and self.economy.payout_due():
            self.economy.payout(self.standings())
            if self.auditor is not None:
                self.auditor.score()
        if open_for_business:
            self.keep_population()
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
        health = {
            "at": summary["at"], "living": len(self.registry.living()), "dead": len(self.registry.dead()),
            "books": {name: {"frozen": book.frozen, "open_orders": len(book.open_orders())} for name, book in self.books.items()},
            "ledger_seq": self.ledger.head()[0], "real_money": self.settings.real_money,
        }
        tmp = self.root / "health.tmp"
        tmp.write_text(json.dumps(health, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.root / "health.json")

    def close(self) -> None:
        self._slow.shutdown(wait=True)
        self._save_state()
        self.ledger.close()


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
