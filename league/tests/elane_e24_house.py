"""An invented House for the equity lanes' replays (release E2.4; league/tests/test_elane_health.py `TheReplays`).

The swarm's own code runs: the real `SwarmStore`, `settings.load` (the budget at its floor: no budget.json), the equity
pass (`Architect.equity_pass`), the Train round (`EquityResearcher`), `elane_yield`'s pace and day, and the real stall
job (league/ops/stall.py `run`) at :20 and :50 of every hour. Faked: the model router (scripted answers, each booked as
a spend row under its request key, as the real router books it, so E2's own pace and day read it), E1's isolated runner
(an invented Train result a program) and the gateway (its two windows, keyed as the House keys a notice).

Every family, program, error text, dollar and number here is invented."""

from __future__ import annotations

import calendar
import json
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Callable
from unittest import mock

from league.ops import elane_health as EH
from league.ops import guard as ops_guard
from league.ops import stall as ST
from league.ops.context import Context
from league.swarm import elane_train
from league.swarm import settings as settings_mod
from league.swarm.architect import Architect
from league.swarm.elane_train import EquityResearcher
from league.swarm.store import SwarmStore
from league.tests import elane_e2_fakes as fx
from league.tests.test_swarm_store import SPEC as OPTIONS_SPEC

HOUR = 3600.0


def at(text: str) -> float:
    return float(calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ")))


class Gateway:
    """The gateway's /v1/notify for a stall notice: one mail a key inside its window (12 hours for a notice with an
    owner step, 24 for one without: gateway/lib/gate.mjs), the key the House's own (`stall.notice_id`, which
    gateway/lib/email.mjs `stallKey` computes the same way)."""

    def __init__(self, clock: Callable[[], float]):
        self.clock = clock
        self.delivered: dict[str, float] = {}
        self.mails: list[dict[str, Any]] = []

    def __call__(self, facts: dict[str, Any]) -> dict[str, Any]:
        key, now = facts["notice_id"], self.clock()
        last = self.delivered.get(key)
        if last is not None and now - last < (24 if key.startswith("stall:info") else 12) * HOUR:
            return {"sent": True, "duplicate": True}
        self.delivered[key] = now
        self.mails.append({"at": now, "key": key, "causes": [c["cause"] for c in facts["causes"]],
                           "owner": [c["cause"] for c in facts["causes"] if c.get("owner_step")]})
        return {"sent": True}


class Router:
    """`ModelRouter.ask` scripted (`script(call) -> answer`; an exception raises), each answered call booked as a
    `sail_model` spend row under its request key."""

    def __init__(self, house: "House", script: Callable[[dict[str, Any]], Any]):
        self.house, self.script, self.calls = house, script, []

    def claude_enabled(self, role: str) -> bool:
        return False

    def ask(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        out = self.script(kw)
        if isinstance(out, BaseException):
            raise out
        cost = float(out.get("cost_usd") or 0.0)
        if cost:
            self.house.store.add_spend("sail_model", cost, detail={"key": kw.get("key")})
        return out


class House:
    """The swarm's store, settings, equity rounds and stall job on one invented clock (`now`), from `start`."""

    def __init__(self, case: Any, start: float, *, e2: dict[str, Any] | None = None,
                 release: str = "/workspace/releases/an-invented-release"):
        tmp = tempfile.TemporaryDirectory(prefix="e24-house-")
        case.addCleanup(tmp.cleanup)
        patch = mock.patch.object(elane_train, "state_inputs", fx.state_inputs)  # E1's ctx stream needs real bars
        patch.start()
        case.addCleanup(patch.stop)
        self.base = Path(tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.now, self.started, self.release = float(start), float(start), release
        self.store = SwarmStore(self.root, clock=lambda: self.now)
        case.addCleanup(self.store.close)
        lanes = {"mode": "gate", "birth_share": 0.25, "e2": dict(e2 or {})}
        (self.root / "swarm.json").write_text(json.dumps({"elane": lanes}))
        self.gateway = Gateway(lambda: self.now)
        self.results: dict[str, Any] = {}
        self.router = Router(self, lambda call: fx.answer([], cost=0.0))
        runner = fx.FakeRunner(lambda code, k: self.results.get(code)
                               or fx.train_result(k=k, pnl=180.0 if k == 1.0 else 120.0))
        with ops_guard.readonly():
            self.settings = settings_mod.load(self.root, config={})
        self.arch = Architect(self.store, self.router, self.settings, clock=lambda: self.now)
        self.researcher = EquityResearcher(self.store, self.router, self.settings, runner=runner, clock=lambda: self.now)
        self.rows: list[dict[str, Any]] = []
        self.steps = {"taken": 0, "skipped": 0}
        self.beat()

    def beat(self) -> None:
        beat = {"at": self.now, "started_at": self.started, "release": self.release}
        (self.root / EH.HEARTBEAT).write_text(json.dumps(beat))

    def restart(self, release: str | None = None) -> None:
        """The swarm restarts at `now`: the same release (the watchdog's, a settings apply) unless `release` names
        another. Its settings are read again."""
        self.started = self.now
        self.release = release or self.release
        with ops_guard.readonly():
            self.settings = settings_mod.load(self.root, config={})
        self.arch.settings = self.researcher.settings = self.settings
        self.beat()

    def keep_options(self) -> None:
        """The options lanes healthy at `now` (a birth, ten Gym runs and a Validation run): none of their causes stand."""
        if self.store.family("opt") is None:
            self.store.add_family({**OPTIONS_SPEC, "id": "opt"}, origin="seed")
            self.store.event("swarm.guard", None, {"action": "release", "causes": []})
        self.store.event("swarm.born", "opt", {"origin": "architect"})
        stamp = int(self.now)
        for i in range(10):
            self.store.add_run("opt", 1, {"run_id": f"opt-train-{stamp}-{i}", "status": "ok", "trials": 1}, window="train",
                               stress=1.0, purpose="train", prune=False)
        self.store.add_run("opt", 1, {"run_id": f"opt-val-{stamp}", "status": "ok", "trials": 1}, window="validation",
                           stress=1.0, purpose="validation", prune=False)

    def loop(self, until: float, step: float = 60.0) -> None:
        """The swarm's main loop for the equity rounds (league/swarm/loop.py: `equity_due` -> `equity_pass`, `due` ->
        `run`; a round that raises leaves a `swarm.status` event), one pass every `step` seconds until `until`."""
        while self.now < until:
            for name, due, fn in (("elane", self.arch.equity_due, self.arch.equity_pass),
                                  ("elane_train", self.researcher.due, self.researcher.run)):
                try:
                    if due():
                        out = fn()
                        for row in (out.get("steps") or []) if name == "elane_train" else []:
                            self.steps["skipped" if row.get("skipped") else "taken"] += 1
                except Exception:  # noqa: BLE001 - as the loop's `_round`
                    self.store.event("swarm.status", None, {"round": name, "error": traceback.format_exc()[-600:]})
            self.now = min(until, self.now + step)
        self.beat()

    def stall(self) -> dict[str, Any]:
        """One run of the real stall job at `now`: {at, stalled, notice, errors, checks (the four equity causes'),
        alerts (the House warnings it raised)}."""
        self.keep_options()
        ctx = Context("stall", root=self.root, base=self.base, due_at=self.now, config={}, clock=lambda: self.now,
                      settings_value={})
        ctx.notify = self.gateway
        ctx.population_ceiling = 20
        ctx.binds = []
        out = ST.run(ctx)
        row = {"at": self.now, "stalled": out["stalled"], "notice": out["notice"], "errors": out["errors"],
               "checks": {cause: out["checks"][cause] for cause in EH.CAUSES}, "alerts": [a["text"] for a in ctx.alerts]}
        self.rows.append(row)
        return row

    def run(self, until: float) -> None:
        """The loop to `until`, the stall job at :20 and :50 of every hour on the way."""
        while self.now < until:
            nxt = self.now - self.now % 1800.0 + 1200.0
            if nxt <= self.now:
                nxt += 1800.0
            self.loop(min(nxt, until))
            if self.now == nxt:
                self.stall()


__all__ = ["House", "Gateway", "Router", "at", "HOUR"]
