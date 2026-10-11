"""Fakes for release E2's tests (the equity lanes' births, Train, seal and yield): E1's switch and card admission as the
interfaces fix them (league/equity/INTERFACES.md sections 8.1-8.3; E1's own implementations land with E1), a store that
accepts the equity structures, a scripted router, an isolated runner that answers each Train span with that span's rows,
and the decider kinds the restart check drives (a program loaded in this process, its STATE fresh at every load) over an
invented ctx stream. Every family, program and number here is invented; no market data is read."""

from __future__ import annotations

import itertools
import json
import math
import tempfile
from types import SimpleNamespace
from typing import Any, Callable, Mapping
from unittest import mock

from league.swarm import cards, elane, elane_train
from league.swarm import store as store_mod
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

_N = itertools.count(1)

UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD"]


def lane_block(**e2: Any) -> dict[str, Any]:
    """The settings' `elane` block with the lanes on at a quarter of births, and `e2` keys."""
    return {"mode": "gate", "universe": list(UNIVERSE), "structures": ["etf"], "birth_share": 0.25, "roster": 3,
            "e2": dict(e2)}


def settings(**e2: Any) -> dict[str, Any]:
    return {"elane": lane_block(**e2), "population": {"start": 48, "ceiling": 96}, "architect": {}, "gym": {}}


def fake_cfg(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane.cfg` as INTERFACES 8.1 fixes its keys (E1's bounds are E1's tests)."""
    block = dict((raw or {}).get("elane") or {})
    return {"mode": block.get("mode", "off"), "universe": list(block.get("universe") or ["SPY", "QQQ", "IWM", "DIA"]),
            "structures": list(block.get("structures") or ["etf"]), "birth_share": float(block.get("birth_share") or 0.0),
            "roster": 3, "val_tries": 1, "looks_per_lineage": 1, "program_loss_usd": -300}


def fake_validate(raw: Any, structure: Any = None, *, roots: Any = None, settings: Any = None):
    """`cards.validate` for an equity card (E1 admits it through `elane.card_errors`): the card back, or its missing
    fields named."""
    if not isinstance(raw, Mapping):
        return None, ["card: missing"]
    missing = [k for k in ("hypothesis", "mechanism_class", "comparison", "falsification") if not raw.get(k)]
    if missing:
        return None, [f"{k}: required" for k in missing]
    return dict(raw), []


_FAMILIES = SwarmStore.families


def lanes_families(self: SwarmStore, *, alive: bool | None = None, lanes: Any = None) -> list[dict[str, Any]]:
    """`SwarmStore.families(alive=..., lanes=...)` as INTERFACES 2.5 fixes it (E1's store change): `lanes` None the
    options lanes only, `LANES` the equity families only, "all" everything."""
    from league.equity import LANES

    try:  # E1's own store (its `lanes` keyword: "all" is every family); the skeleton's has no such keyword
        fams = _FAMILIES(self, alive=alive, lanes="all")
    except TypeError:
        fams = _FAMILIES(self, alive=alive)
    if lanes == "all":
        return fams
    equity = [f for f in fams if (f.get("spec") or {}).get("lane") in LANES]
    if lanes is None:
        return [f for f in fams if (f.get("spec") or {}).get("lane") not in LANES]
    return [f for f in equity if (f.get("spec") or {}).get("lane") in tuple(lanes)]


def switch_on(case: Any) -> None:
    """E1's names this release calls, as their interfaces fix them, for the life of `case`: the switch, the card
    admission, and a store that takes the equity structures and filters `families` by lane (E1's store change)."""
    patches = [mock.patch.object(elane, "on", lambda s: ((s or {}).get("elane") or {}).get("mode") == "gate"),
               mock.patch.object(elane, "cfg", fake_cfg),
               mock.patch.object(cards, "validate", fake_validate),
               mock.patch.object(store_mod, "STRUCTURES", tuple(dict.fromkeys((*store_mod.STRUCTURES, "etf", "stock")))),
               mock.patch.object(SwarmStore, "families", lanes_families),
               mock.patch.object(elane_train, "state_inputs", state_inputs)]
    for p in patches:
        p.start()
        case.addCleanup(p.stop)


def new_store(case: Any, clock: Clock | None = None) -> SwarmStore:
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    store = SwarmStore(tmp.name, clock=clock or Clock())
    case.addCleanup(store.close)
    return store


PROGRAM = '''import math
import numpy as np

NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}
PARAMS = {"share": 0.5}


def decide(ctx):
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    out.append({"buy": "SPY", "share": ctx.params["share"], "at": "close"})
    return out
'''


def program(symbol: str = "SPY", share: float = 0.5) -> str:
    return PROGRAM.replace('"SPY"', json.dumps(symbol)).replace("0.5", repr(share))


def card(lane: str = "beta", symbols: tuple[str, ...] = ("SPY",), **extra: Any) -> dict[str, Any]:
    return {"lane": lane, "structure": "etf", "symbols": list(symbols),
            "hypothesis": "Holders demand a premium to carry index risk overnight, when news arrives and they cannot "
                          "trade (an invented test card).",
            "mechanism_class": "calendar_flow", "inputs": ["clock"], "holding": "days_1_3",
            "cost": {"hurdle": 0.0004, "why": "two half-spreads and the sell fees on an index ETF"},
            "comparison": "the same symbol held through the same sessions without the condition",
            "ablation": {"param": "signal_on", "off": 0},
            "falsification": "net P&L at or below zero at 1.5x the half-spread over Train", **extra}


def proposal(slug: str, *, lane: str = "beta", agenda: str = "overnight", symbols: tuple[str, ...] = ("SPY",),
             code: str | None = None, mechanism: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"slug": slug, "lane": lane, "agenda": agenda, "structure": "etf", "symbols": list(symbols),
            "mechanism": mechanism or f"Invented mechanism {slug}: index holders are paid for overnight risk they cannot "
                                      "trade out of.",
            "rejection": "loses at 1.5x", "sketch": "buy at the close, sell at the next open",
            "card": card(lane, symbols), "program": code if code is not None else program(symbols[0]), **extra}


def answer(rows: list[dict[str, Any]], *, cost: float = 0.10, route: str = "sail", model: str = "pro_asap") -> dict[str, Any]:
    text = json.dumps({"families": rows})
    return {"text": text, "json": {"families": rows}, "route": route, "model": model, "cost_usd": cost, "truncated": False}


class FakeRouter:
    """`ModelRouter.ask` scripted: `script(call) -> answer` (an Exception raises); each call kept in `calls`."""

    def __init__(self, script: Callable[[dict[str, Any]], Any] | None = None, *, claude_roles: tuple[str, ...] = ()):
        self.calls: list[dict[str, Any]] = []
        self.script = script or (lambda call: answer([]))
        self.claude_roles = claude_roles

    def claude_enabled(self, role: str) -> bool:
        return role in self.claude_roles

    def ask(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        out = self.script(kw)
        if isinstance(out, BaseException):
            raise out
        return out


#: The Train years (2016-19 and 2022-24; 2020-21 is the reserve: league/swarm/elane_train.py `TRAIN_SPANS`).
TRAIN_YEARS = (2016, 2017, 2018, 2019, 2022, 2023, 2024)


def year_rows(*, trades: int = 60, days: int = 30, pnl: float = 20.0, t: float = 0.6,
              years: Any = TRAIN_YEARS, override: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    rows = {str(y): {"trades": trades, "days": 252, "days_traded": days, "pnl": pnl, "t_daily": t, "exposure_mean": 0.3,
                     "bh_pnl": 6.0} for y in years}
    for y, row in (override or {}).items():
        rows[str(y)] = {**rows.get(str(y), {}), **row}
    return rows


def daily_rows(by_year: Mapping[str, Any]) -> list[list[Any]]:
    """Four invented daily rows a by-year row ([day, pnl, equity, exposure]), dated inside its year, summing to its P&L."""
    out = []
    for y, row in sorted(by_year.items()):
        pnl = float(row.get("pnl") or 0.0)
        for month, part in (("03", 0.4), ("06", 0.1), ("09", 0.3), ("12", 0.2)):
            out.append([f"{y}-{month}-15", round(pnl * part, 2), 1000.0, 0.3])
    return out


def train_result(*, k: float = 1.0, pnl: float = 180.0, status: str = "ok", by_year: Mapping[str, Any] | None = None,
                 bh: float = 50.0, start: str = "2016-01-04", end: str = "2024-12-31") -> dict[str, Any]:
    """An invented Train result over every Train year (league/equity/results.py's keys); `FakeRunner` answers each span
    with its part (`span_result`)."""
    years = dict(by_year if by_year is not None else year_rows())
    return {"run_id": f"eq-run-{next(_N)}", "program": "p", "status": status, "window": "train", "start": start,
            "end": end, "k": k, "trials": 1 if status == "ok" else 0, "symbols": ["SPY"],
            "summary": {"trades": sum(int(r.get("trades") or 0) for r in years.values()),
                        "days_traded": sum(int(r.get("days_traded") or 0) for r in years.values()), "pnl": pnl,
                        "fees": 3.0, "t_daily": 1.7, "win_rate": 0.55, "exposure_mean": 0.3, "max_drawdown": 40.0,
                        "mean_net_return": 0.001},
            "by_year": years, "daily": daily_rows(years), "bh": {"pnl": bh}, "mte": {"mean": 0.0004, "t": 0.9, "n": 400}}


def span_result(full: Mapping[str, Any], start: Any, end: Any) -> dict[str, Any]:
    """An invented whole-Train result cut to one Train span, as E1's runner answers `train(start, end)`: the by-year and
    daily rows of the span's years, its counts, and the P&L, fees and buy-and-hold in proportion to its years. A row of a
    year in no span (a leak to catch) goes with the span on its side of 2022: 2020, 2021 or 2015 with the first, 2025 or
    2026 with the second; the result's own start goes with the first span and its end with the second."""
    first = end is not None and end.year < 2022
    by_year = dict(full.get("by_year") or {})
    rows = {y: r for y, r in by_year.items() if (int(str(y)[:4]) < 2022) == first}
    share = len(rows) / len(by_year) if by_year else 0.5
    out = {**dict(full), "run_id": f"{full.get('run_id')}-{'a' if first else 'b'}", "by_year": rows,
           "daily": [d for d in full.get("daily") or [] if (int(str(d[0])[:4]) < 2022) == first],
           "start": full.get("start") if first else start.isoformat(),
           "end": end.isoformat() if first else full.get("end")}
    summary = dict(full.get("summary") or {})
    for key in ("pnl", "fees"):
        if summary.get(key) is not None:
            summary[key] = summary[key] * share
    summary.update(trades=sum(int(r.get("trades") or 0) for r in rows.values()),
                   days_traded=sum(int(r.get("days_traded") or 0) for r in rows.values()))
    out["summary"] = summary
    if isinstance(full.get("bh"), Mapping) and full["bh"].get("pnl") is not None:
        out["bh"] = {"pnl": full["bh"]["pnl"] * share}
    if isinstance(full.get("mte"), Mapping) and full["mte"].get("n"):
        out["mte"] = {"mean": full["mte"].get("mean"), "t": (full["mte"].get("t") or 0.0) * share ** 0.5,
                      "n": int(full["mte"]["n"] * share)}
    return out


def review_answer(verdict: str = "pass", *, excerpt: str | None = None, reference: str = "levels",
                  reasons: tuple[str, ...] = (), model: str = "pro_balanced", cost: float = 0.02) -> dict[str, Any]:
    """An invented answer of the equity review or audit (league/swarm/elane_review.py `REVIEW`'s JSON)."""
    findings = [] if excerpt is None else [{"code_excerpt": excerpt, "contract_reference": reference,
                                            "counterexample": "when the invented condition holds the program buys on a "
                                                              "remembered level, which identifies the years"}]
    data = {"verdict": verdict, "reasons": list(reasons or ([f"an invented {verdict} reason"])), "findings": findings}
    return {"text": json.dumps(data), "json": data, "route": "sail", "model": model, "cost_usd": cost}


def is_review(call: Mapping[str, Any]) -> bool:
    """Whether a router call is the equity review's or audit's (its key)."""
    key = str(call.get("key") or "")
    return key.startswith("swarm:elane:review:") or key.startswith("swarm:elane:audit:")


class FakeRunner:
    """E1's `runner.Isolated` (INTERFACES 4.8): `train(start, end)` answers the span's part (`span_result`) of
    `answer(code, k)` (an invented whole-Train result; an Exception raises); calls kept. Its `decider` is a
    `FakeDecider` (the restart check's kinds)."""

    def __init__(self, answer_: Callable[[str, float], Any] | None = None):
        self.calls: list[dict[str, Any]] = []
        self.answer = answer_ or (lambda code, k: train_result(k=k, pnl=180.0 if k == 1.0 else 120.0))
        self.decider = FakeDecider()

    def train(self, code: str, params: Any, *, name: str, start: Any = None, end: Any = None, k: float = 1.0) -> Any:
        self.calls.append({"code": code, "params": params, "name": name, "start": start, "end": end, "k": k})
        out = self.answer(code, k)
        if isinstance(out, BaseException):
            raise out
        return SimpleNamespace(result=span_result(out, start, end), bars=None)


class FakeDecider:
    """E1's decider kinds the restart check drives (league/live/decider.py `kind_load`, `kind` "decide", `kind_drop`)
    in this process: a load executes the invented program's file in a namespace of its own (so its STATE starts empty,
    as a fresh instance's does in E1's child), a decide calls its `decide` with the job's invented inputs as the ctx
    and answers E1's `stats` (the instance's `calls` since its load, its `errors`, `disqualified` once they reach the
    load's `max_errors`: a disqualified instance answers nothing and counts no call, as E1's runner).

    What a test can make of the child: `restart_after` (a restart E1's decider counts in `restarts`, once that many
    decides were answered), `reload_after` (the child died between two requests: every instance is loaded again with
    fresh memory before the next decide, and `restarts` does not move, as in E1's `Decider._ask`), `counts` False (an
    answer without `stats.calls`), `counts_errors` False (one without `stats.errors`), `fails` (an exception every
    decide raises: a child that failed)."""

    def __init__(self) -> None:
        self.instances: dict[str, dict[str, Any]] = {}
        self.loads: list[str] = []
        self.decides = 0
        self.restarts = 0
        self.restart_after: int | None = None
        self.reload_after: int | None = None
        self.counts = True
        self.counts_errors = True
        self.fails: BaseException | None = None

    def _fresh(self, key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        space: dict[str, Any] = {}
        exec(compile(str(payload["code"]), f"<{key}>", "exec"), space)  # noqa: S102 - an invented test program
        params = {**dict(space.get("PARAMS") or {}), **dict(payload.get("params") or {})}
        self.instances[key] = {"space": space, "params": params, "payload": dict(payload), "calls": 0, "errors": 0,
                               "disqualified": None}
        return self.instances[key]

    def kind_load(self, kind: str, key: str, payload: Mapping[str, Any], *, budget_seconds: Any = None) -> dict:
        assert kind == "equity", kind
        instance = self._fresh(str(key), payload)
        self.loads.append(str(key))
        return {"needs": dict(instance["space"].get("NEEDS") or {}), "params": instance["params"]}

    def kind_drop(self, kind: str, key: str, *, budget_seconds: float = 10.0) -> None:
        self.instances.pop(str(key), None)

    def kind(self, kind: str, op: str, payload: Mapping[str, Any], *, budget_seconds: Any = None) -> dict:
        assert (kind, op) == ("equity", "decide"), (kind, op)
        if self.fails is not None:
            raise self.fails
        if self.reload_after is not None and self.decides >= self.reload_after:
            self.reload_after = None
            for key, instance in list(self.instances.items()):
                self._fresh(key, instance["payload"])
        results: dict[str, Any] = {}
        for job in payload.get("jobs") or ():
            key = str(job["key"])
            instance = self.instances.get(key)
            if instance is None:
                results[key] = {"intents": [], "stats": None, "missing": True}
                continue
            intents: list = []
            if not instance["disqualified"]:
                instance["calls"] += 1
                try:
                    intents = list(instance["space"]["decide"](SimpleNamespace(**dict(job["inputs"]),
                                                                               params=instance["params"])) or [])
                except Exception:  # noqa: BLE001 - a failed decide is no intent and one error, as E1's runner counts it
                    instance["errors"] += 1
                    if instance["errors"] >= int(instance["payload"].get("max_errors", 25)):
                        instance["disqualified"] = f"{instance['errors']} errors"
            stats = {"calls": instance["calls"], "errors": instance["errors"], "disqualified": instance["disqualified"]}
            if not self.counts_errors:
                del stats["errors"]
            results[key] = {"intents": json.loads(json.dumps(intents)), "stats": stats if self.counts else {}}
            self.decides += 1
        if self.restart_after is not None and self.decides >= self.restart_after:
            self.restarts += 1
            self.restart_after = None
        return {"ok": True, "results": results}


#: The decision sessions the invented ctx stream gives a Train span: the check empties instance B's STATE 7 sessions
#: in and every 20 after (league/swarm/elane_train.py `BAR`), so at sessions 7 and 27 here, both with a lot held.
STATE_SESSIONS = 45


def state_inputs(run: Any, sessions: int = STATE_SESSIONS) -> Any:
    """The restart check's ctx stream, invented (E1's ctx builds the real one: league/swarm/elane_train.py
    `state_inputs`): `sessions` (`STATE_SESSIONS`) decision sessions of one Train span, each with its symbols' last
    closes, the calendar fields and, every other session, an open lot."""
    symbols = [str(s) for s in ((getattr(run, "result", None) or {}).get("symbols") or ["SPY"])]
    for i in range(sessions):
        # Invented closes around 100 with no period and four decimals (a sum of their returns has rounding to show).
        closes = [round(100.0 * math.exp(0.03 * math.sin(1.7 * j) + 0.02 * math.cos(0.37 * j * j)), 4)
                  for j in range(i + 1)][-31:]
        yield {"symbols": symbols, "bars": {s: SimpleNamespace(close=list(closes)) for s in symbols},
               "prices": {s: closes[-1] for s in symbols}, "weekday": i % 5, "session_of_month": i % 21 + 1,
               "sessions_to_month_end": 20 - i % 21, "events": {}, "events_next": {},
               "positions": [{"id": 1000 + i, "symbol": symbols[0], "qty": 1.0, "held_sessions": 1}] if i % 2 else [],
               "orders": [], "closed": [], "rejects": [], "cash": 500.0, "equity": 1000.0, "budget": 1000.0,
               "caps": {s: 500.0 for s in symbols}}


#: An invented program that counts sessions in STATE (a clock of its own): its intents change when STATE is emptied.
COUNTER = '''import math

NEEDS = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 3}
PARAMS = {"share": 0.5, "every": 7}
STATE = {}


def decide(ctx):
    STATE["n"] = STATE.get("n", 0) + 1
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    if STATE["n"] % ctx.params["every"] == 0:
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "close"})
    return out
'''

def counter(every: int) -> str:
    """`COUNTER` with a clock of `every` sessions (5 a week, 10, 20: the periods that divide the check's 20)."""
    return COUNTER.replace('"every": 7', f'"every": {int(every)}')


#: An invented program that raises at every call (a decide that fails is no intent: two silent instances agree).
RAISES = '''import math

NEEDS = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 3}
PARAMS = {"share": 0.5}


def decide(ctx):
    raise ValueError("an invented failure")
'''

#: An invented program whose STATE only caches a value it recomputes from ctx (a moving average keyed by the closes).
CACHE = '''import math

NEEDS = {"symbols": ["SPY"], "history": 30, "max_hold_sessions": 3}
PARAMS = {"share": 0.5, "n": 20}
STATE = {}


def decide(ctx):
    close = ctx.bars["SPY"].close
    key = (len(close), float(close[-1]))
    if STATE.get("key") != key:
        tail = [float(x) for x in close[-ctx.params["n"]:] if math.isfinite(float(x))]
        STATE["key"] = key
        STATE["mean"] = sum(tail) / len(tail) if tail else None
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    mean = STATE["mean"]
    if mean is not None and float(close[-1]) > mean and not ctx.positions:
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "close"})
    return out
'''


#: An invented program whose decide needs what STATE held before a restart: it writes a lot's peak at entry and reads it
#: while the lot is held, so with STATE emptied under a held lot it raises, and a decide that raises answers nothing, as
#: the uninterrupted one does while it holds (the stop is never reached on the invented stream).
PEAK = '''import math

NEEDS = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 3}
PARAMS = {"share": 0.5, "stop": 0.5}
STATE = {}


def decide(ctx):
    px = ctx.prices["SPY"]
    if ctx.positions:
        STATE["peak"] = max(STATE["peak"], px)
        if px < STATE["peak"] * (1.0 - ctx.params["stop"]):
            return [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
        return []
    STATE["peak"] = px
    return [{"buy": "SPY", "share": ctx.params["share"], "at": "close"}]
'''

#: An invented program whose STATE holds the value ctx gives (a rolling sum of squared returns over the last n sessions)
#: but UPDATED IN PLACE: the newest term added, the oldest dropped. The sum is the one ctx gives, added in another
#: order, so the size of its buy differs from a fresh instance's in the last digits only (floating-point noise).
INPLACE = '''import math

NEEDS = {"symbols": ["SPY"], "history": 30, "max_hold_sessions": 3}
PARAMS = {"n": 20, "target": 0.0002}
STATE = {}


def squared(close, back):
    return (float(close[-1 - back]) / float(close[-2 - back]) - 1.0) ** 2


def decide(ctx):
    close = ctx.bars["SPY"].close
    n = ctx.params["n"]
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    if len(close) < n + 2:
        return out
    if "ss" not in STATE:
        STATE["ss"] = sum(squared(close, back) for back in range(n))
    else:
        STATE["ss"] += squared(close, 0) - squared(close, n)
    variance = max(STATE["ss"], 1e-12) / n
    out.append({"buy": "SPY", "share": min(1.0, ctx.params["target"] / variance), "at": "close"})
    return out
'''

#: `INPLACE` recomputing its sum from ctx at every call (what the bar asks for): nothing carried, nothing to drift.
RECOMPUTED = INPLACE.replace("STATE[\"ss\"] += squared(close, 0) - squared(close, n)",
                             "STATE[\"ss\"] = sum(squared(close, back) for back in range(n))")

#: `INPLACE` with a value that is NOT the one ctx gives: a decayed running sum of every session since its load (it
#: drops nothing, it fades), so the size of its buy depends on how long ago it was loaded.
CARRIED = INPLACE.replace("STATE[\"ss\"] += squared(close, 0) - squared(close, n)",
                          "STATE[\"ss\"] = 0.9 * STATE[\"ss\"] + squared(close, 0)")


def e2_family(store: SwarmStore, slug: str, *, lane: str = "beta", agenda: str = "overnight",
              symbols: tuple[str, ...] = ("SPY",), route: str = "sail:pro_asap", code: str | None = None,
              record: Mapping[str, Any] | None = None, mechanism: str | None = None) -> dict[str, Any]:
    """An E2 family as the equity pass bears it (its spec), with a v1 when `code` is given."""
    from league.swarm import elane_train

    spec = {"id": slug, "mechanism": mechanism or f"Invented mechanism {slug}: holders are paid for overnight index risk.",
            "structure": "etf", "roots": list(symbols), "symbols": list(symbols), "lane": lane, "agenda": agenda,
            "e2_route": route}
    fam = store.add_family(spec, origin="architect")
    if code is not None:
        store.add_version(fam["id"], code, {}, author="architect:test")
    store.set_state(fam["id"], **{elane_train.STATE_KEY: dict(record or {"status": "researching", "versions": {}})})
    return store.family(fam["id"])


class RunFailed(RuntimeError):
    """The name E1's runner gives a child that failed a run (league/equity/runner.py `RunFailed`)."""


class DeciderError(RuntimeError):
    """The name E1's decider gives a child that failed a request (league/live/decider.py `DeciderError`)."""


class ProgramRefused(ValueError):
    """The name E1's runner gives a program the child would not load (league/equity/runner.py `ProgramRefused`)."""


class MissingData(FileNotFoundError):
    """The name E1's store gives a store not yet written (league/equity/store.py `MissingData`)."""


def reviewed(store: SwarmStore, fid: str, n: int = 1) -> None:
    """Write the review record E1's look reads for version `n` (league/swarm/elane_review.py `record`)."""
    from league.swarm import elane_review
    from league.swarm.gate import run_sha

    sha = run_sha(store.version(fid, n))
    held = elane_review.record(sha, {"model": "pro_balanced", "route": "sail:pro_balanced"},
                               {"model": "k3_balanced", "route": "sail:k3_balanced"}, at=store.now(), version=n)
    store.set_state(fid, review=held)
    from league.swarm import elane_train

    rec = elane_train.record_of(store.family(fid))
    rec["passed_review"] = held
    store.set_state(fid, **{elane_train.STATE_KEY: rec})


__all__ = ["UNIVERSE", "lane_block", "settings", "fake_cfg", "fake_validate", "switch_on", "new_store", "PROGRAM",
           "program", "card", "proposal", "answer", "FakeRouter", "TRAIN_YEARS", "year_rows", "daily_rows", "train_result",
           "span_result", "FakeRunner", "FakeDecider", "STATE_SESSIONS", "state_inputs", "COUNTER", "counter", "RAISES",
           "CACHE", "PEAK", "INPLACE", "RECOMPUTED", "CARRIED", "e2_family", "review_answer", "is_review", "RunFailed",
           "DeciderError", "ProgramRefused", "MissingData", "reviewed"]
