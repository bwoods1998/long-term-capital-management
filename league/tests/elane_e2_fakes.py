"""Fakes for release E2's tests (the equity lanes' births, Train, seal and yield): E1's switch and card admission as the
interfaces fix them (league/equity/INTERFACES.md sections 8.1-8.3; E1's own implementations land with E1), a store that
accepts the equity structures, a scripted router and an isolated runner. Every family, program and number here is
invented; no market data is read."""

from __future__ import annotations

import itertools
import json
import tempfile
from types import SimpleNamespace
from typing import Any, Callable, Mapping
from unittest import mock

from league.swarm import cards, elane
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
               mock.patch.object(store_mod, "STRUCTURES", tuple(store_mod.STRUCTURES) + ("etf", "stock")),
               mock.patch.object(SwarmStore, "families", lanes_families)]
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


def year_rows(*, trades: int = 60, days: int = 30, pnl: float = 20.0, t: float = 0.6,
              years: Any = range(2016, 2025), override: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    rows = {str(y): {"trades": trades, "days": 252, "days_traded": days, "pnl": pnl, "t_daily": t, "exposure_mean": 0.3,
                     "bh_pnl": 6.0} for y in years}
    for y, row in (override or {}).items():
        rows[str(y)] = {**rows.get(str(y), {}), **row}
    return rows


def train_result(*, k: float = 1.0, pnl: float = 180.0, status: str = "ok", by_year: Mapping[str, Any] | None = None,
                 bh: float = 50.0, start: str = "2016-01-04", end: str = "2024-12-31") -> dict[str, Any]:
    """An invented Train result (league/equity/results.py's keys)."""
    years = dict(by_year if by_year is not None else year_rows())
    return {"run_id": f"eq-run-{next(_N)}", "program": "p", "status": status, "window": "train", "start": start,
            "end": end, "k": k, "trials": 1 if status == "ok" else 0,
            "summary": {"trades": sum(int(r.get("trades") or 0) for r in years.values()),
                        "days_traded": sum(int(r.get("days_traded") or 0) for r in years.values()), "pnl": pnl,
                        "fees": 3.0, "t_daily": 1.7, "win_rate": 0.55, "exposure_mean": 0.3, "max_drawdown": 40.0,
                        "mean_net_return": 0.001},
            "by_year": years, "bh": {"pnl": bh}, "mte": {"mean": 0.0004, "t": 0.9, "n": 400}}


class FakeRunner:
    """E1's `runner.Isolated.train` (INTERFACES 4.8): `answer(code, k) -> result` (an Exception raises); calls kept."""

    def __init__(self, answer_: Callable[[str, float], Any] | None = None):
        self.calls: list[dict[str, Any]] = []
        self.answer = answer_ or (lambda code, k: train_result(k=k, pnl=180.0 if k == 1.0 else 120.0))

    def train(self, code: str, params: Any, *, name: str, start: Any = None, end: Any = None, k: float = 1.0) -> Any:
        self.calls.append({"code": code, "params": params, "name": name, "start": start, "end": end, "k": k})
        out = self.answer(code, k)
        if isinstance(out, BaseException):
            raise out
        return SimpleNamespace(result=out, bars=None)


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


__all__ = ["UNIVERSE", "lane_block", "settings", "fake_cfg", "fake_validate", "switch_on", "new_store", "PROGRAM",
           "program", "card", "proposal", "answer", "FakeRouter", "year_rows", "train_result", "FakeRunner", "e2_family"]
