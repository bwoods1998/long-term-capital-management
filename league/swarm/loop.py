"""The swarm's process: `python -m league.swarm run --root /workspace/state`.

One process beside the House loop, niced. Its threads:

- RESEARCHERS: `researcher.concurrency` workers, each taking the next family (the bandit's share first,
  then the longest-waiting) and running one cycle, while the guard allows;
- THE GYM POOL's dispatchers (one per box) and forks (`pool.py`);
- ROUNDS on their own threads so none blocks another: the tournament (hourly), the gate (every few
  minutes), the nightly forward (once a day), the architect (every four hours);
- THE MAIN LOOP (every few seconds): re-read the settings, check the guard (brake: the Gym to sleep and the
  researchers idle), manage the pool, start the rounds that are due, write the heartbeat, and leave when
  asked (the STOP files, `<root>/swarm.stop`) or when the House's release changed (the House starts the new one).

The heartbeat (`<root>/swarm.heartbeat`, JSON) carries the pid, the release directory, the time, and a live
status (families, cycles and spend in the last hour by kind, the guard, the pool): the House's `SwarmStep`
reads it to supervise the process and the operator reads it to see the swarm.

Standard library only (the Gym's driver is imported when a box starts).
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Mapping

from . import HEARTBEAT, PID_FILE, settings as settings_mod
from .architect import Architect
from .gate import Gate
from .guard import SailGuard, provider_reader
from .pool import GymPool
from .researcher import Researcher
from .seeds import SEEDS, family_spec, program_for
from .store import SwarmStore
from .tournament import Tournament

CODE_DIR = Path(__file__).resolve().parents[2]


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}  {message}", flush=True)


def load_env(path: str | os.PathLike | None) -> None:
    """NAME=value lines into the environment (never overriding what is set), like `league.service.load_env`."""
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


class Scheduler:
    """Which family runs next: the bandit's share first, then the longest wait; one cycle per family at a time."""

    def __init__(self, store: SwarmStore, *, clock: Callable[[], float] = time.time):
        self.store = store
        self.clock = clock
        self._lock = threading.Lock()
        self.running: set[str] = set()
        self.last: dict[str, float] = {}
        self.cooldown: dict[str, float] = {}
        self.errors: dict[str, int] = {}

    def take(self, *, idle_seconds: float = 5.0) -> str | None:
        now = self.clock()
        fams = self.store.families(alive=True)
        with self._lock:
            ready = [f for f in fams if f["id"] not in self.running and self.cooldown.get(f["id"], 0) <= now
                     and now - self.last.get(f["id"], 0) >= idle_seconds]
            if not ready:
                return None
            n = max(1, len(fams))
            # A family's share (the bandit's) buys it an earlier turn: a share at the average is worth nothing, twice it
            # is worth a minute of waiting.
            ready.sort(key=lambda f: (self.last.get(f["id"], 0) - 60.0 * (float(f.get("weight") or (1.0 / n)) * n - 1.0), f["id"]))
            fid = ready[0]["id"]
            self.running.add(fid)
            self.last[fid] = now
            return fid

    def release(self, fid: str, result: Mapping[str, Any]) -> None:
        with self._lock:
            self.running.discard(fid)
            self.last[fid] = self.clock()
            error = str(result.get("error") or "")
            if "budget" in error.lower() or "BudgetExceeded" in error:
                midnight = self.clock() - (self.clock() % 86400) + 86400
                self.cooldown[fid] = midnight  # its model budget is spent for today
            elif error:
                self.errors[fid] = self.errors.get(fid, 0) + 1
                self.cooldown[fid] = self.clock() + min(1800.0, 30.0 * 2 ** min(self.errors[fid], 6))
            else:
                self.errors.pop(fid, None)


class Swarm:
    """The process (the module docstring). Every collaborator can be handed in (tests use fakes)."""

    def __init__(self, root: str | Path, *, settings: Mapping[str, Any] | None = None, config: Mapping[str, Any] | None = None,
                 store: SwarmStore | None = None, router: Any = None, pool: Any = None, guard: Any = None, client: Any = None,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep):
        self.root = Path(root)
        self.config = dict(config) if config is not None else None
        self.settings = dict(settings) if settings is not None else settings_mod.load(self.root, config=self.config)
        self.clock = clock
        self.sleep = sleep
        self.store = store or SwarmStore(self.root, clock=clock)
        if router is None:
            from .models import build_router

            router = build_router(self.root, self.store, self.settings, config=self.config or _config())
        self.router = router
        if guard is None:
            guard = SailGuard(self.store, self.settings, provider_reader(router.provider), clock=clock)
        self.guard = guard
        if pool is None:
            if client is None:
                client = _sail_client()
            pool = GymPool(self.store, client, self.settings, clock=clock, allowed=lambda kind: self.guard.allows(kind))
        self.pool = pool
        self.scheduler = Scheduler(self.store, clock=clock)
        self.researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=clock,
                                     starter=lambda spec: program_for(spec))
        self.tournament = Tournament(self.store, self.pool, self.settings, clock=clock)
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=clock)
        self.architect = Architect(self.store, self.router, self.settings, clock=clock)
        self.stop = threading.Event()
        self.workers: list[threading.Thread] = []
        self.rounds: dict[str, threading.Thread] = {}
        self.started_at = clock()
        self.why_stopped = ""
        self._beat = float("-inf")

    # ------------------------------------------------------------------ the population
    def seed(self) -> list[str]:
        """The founding population, once: the first `population.start` seeds (each a `swarm.born` event)."""
        if self.store.families():
            return []
        born = []
        for spec in SEEDS[: int(self.settings.get("population", {}).get("start", 48))]:
            fam = self.store.add_family(family_spec(spec), origin="seed")
            self.store.event("swarm.born", fam["id"], {"parent": None, "mechanism": fam["mechanism"], "structure": fam["structure"],
                                                        "roots": fam["roots"], "origin": "seed", "founder": spec.get("founder")})
            born.append(fam["id"])
        return born

    # ------------------------------------------------------------------ status and heartbeat
    def status(self) -> dict[str, Any]:
        now = self.clock()
        hour = now - 3600
        spend = {k: round(self.store.spent([k], since=hour), 4) for k in ("sail_model", "gym_box", "openai")}
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(hour))
        recent = [json.loads(row["payload"]) for row in
                  self.store._all("SELECT payload FROM events WHERE kind='swarm.cycle' AND at >= ? ORDER BY seq DESC LIMIT 3000", (since,))]
        seconds = sorted(float(p.get("seconds") or 0) for p in recent[:300] if not p.get("error"))
        return {"families_alive": len(self.store.families(alive=True)), "running": len(self.scheduler.running),
                "totals": self.store.totals(), "spend_last_hour": spend, "usd_per_hour": round(sum(spend.values()), 4),
                "median_cycle_seconds": seconds[len(seconds) // 2] if seconds else None, "cycles_last_hour": len(recent),
                "cycle_errors_last_hour": sum(1 for p in recent if p.get("error")),
                "guard": getattr(self.guard, "last", {}), "braked": not self.guard.allows(), "pool": self.pool.status(),
                "rounds": sorted(k for k, t in self.rounds.items() if t.is_alive())}

    def heartbeat(self, extra: Mapping[str, Any] | None = None) -> None:
        body = {"pid": os.getpid(), "at": self.clock(), "release": str(CODE_DIR), "started_at": self.started_at,
                "status": self.status(), **(extra or {})}
        tmp = self.root / (HEARTBEAT + ".tmp")
        tmp.write_text(json.dumps(body, default=str))
        tmp.replace(self.root / HEARTBEAT)

    # ------------------------------------------------------------------ why stop
    def should_stop(self) -> str:
        for stop in (self.root / "STOP", self.root.parent / "STOP", self.root / "swarm.stop"):
            if stop.exists():
                return f"{stop} exists"
        current = self.root.parent / "current"
        if current.exists() and (self.root.parent / "releases").exists():
            try:
                if current.resolve() != CODE_DIR:
                    return f"the House's release changed ({current.resolve().name})"
            except OSError:
                pass
        if not self.settings.get("enabled"):
            return "the swarm is disabled in its settings"
        return ""

    # ------------------------------------------------------------------ the threads
    def _worker(self, index: int) -> None:
        idle = float(self.settings.get("researcher", {}).get("idle_seconds", 5))
        while not self.stop.is_set():
            if not self.guard.allows() or index >= int(self.settings.get("researcher", {}).get("concurrency", 48)):
                self.sleep(5.0)
                continue
            fid = self.scheduler.take(idle_seconds=idle)
            if fid is None:
                self.sleep(2.0)
                continue
            result: dict[str, Any] = {}
            try:
                result = self.researcher.cycle(fid)
            except Exception as exc:  # noqa: BLE001 - never kill a worker
                result = {"error": f"{type(exc).__name__}: {exc}"}
                log(f"cycle {fid} crashed: {traceback.format_exc()[-800:]}")
            finally:
                self.scheduler.release(fid, result)

    def _round(self, name: str, fn: Callable[[], Any]) -> None:
        thread = self.rounds.get(name)
        if thread is not None and thread.is_alive():
            return

        def body() -> None:
            try:
                result = fn()
                log(f"{name}: {json.dumps(result, default=str)[:600]}")
            except Exception:  # noqa: BLE001
                log(f"{name} failed: {traceback.format_exc()[-1200:]}")
                self.store.event("swarm.status", None, {"round": name, "error": traceback.format_exc()[-600:]})

        thread = threading.Thread(target=body, name=f"round-{name}", daemon=True)
        self.rounds[name] = thread
        thread.start()

    def step(self) -> None:
        """One pass of the main loop (tests call it directly)."""
        fresh = settings_mod.load(self.root, config=self.config)
        self.settings.clear()
        self.settings.update(fresh)
        if getattr(self.guard, "due", lambda: True)():
            was = not self.guard.allows()
            self.guard.check()
            if not self.guard.allows():
                if not was:
                    log(f"guard: brake ({getattr(self.guard, 'reason', '')})")
                self.pool.scale_to_zero(getattr(self.guard, "reason", "the guard"))
        self.pool.manage()
        if self.guard.allows():
            if self.tournament.due():
                self._round("tournament", self.tournament.run)
            if self.gate.due():
                self._round("gate", self.gate.run)
            if self.gate.forward_due():
                self._round("forward", self.gate.forward)
            if self.architect.due() and self.store.get("tournament_at"):
                self._round("architect", self.architect.run)
        if self.clock() - self._beat >= float(self.settings.get("heartbeat_seconds", 20)):
            self._beat = self.clock()
            self.heartbeat()

    def run(self, *, once: bool = False) -> int:
        """The process: seed, start the workers, loop until asked to stop."""
        try:
            os.nice(int(self.settings.get("nice", 10)))
        except OSError:
            pass
        (self.root / PID_FILE).write_text(str(os.getpid()))
        why = self.should_stop()
        if why:
            log(f"not starting: {why}")
            return 0
        born = self.seed()
        if born:
            log(f"seeded {len(born)} families")
        adopted = self.pool.adopt() if hasattr(self.pool, "adopt") else 0
        self.store.event("swarm.status", None, {"action": "started", "pid": os.getpid(), "release": str(CODE_DIR), "adopted": adopted,
                                                "families": len(self.store.families(alive=True))})
        log(f"started: pid {os.getpid()}, release {CODE_DIR}, {len(self.store.families(alive=True))} families, {adopted} boxes adopted")
        n = int(self.settings.get("researcher", {}).get("concurrency", 48))
        for i in range(max(n, 1) if not once else 0):
            t = threading.Thread(target=self._worker, args=(i,), name=f"researcher-{i}", daemon=True)
            t.start()
            self.workers.append(t)
        try:
            while not self.stop.is_set():
                why = self.should_stop()
                if why:
                    self.why_stopped = why
                    break
                try:
                    self.step()
                except Exception:  # noqa: BLE001 - the loop survives its own failures
                    log(f"step failed: {traceback.format_exc()[-1200:]}")
                if once:
                    break
                self.sleep(float(self.settings.get("heartbeat_seconds", 20)) / 4)
        finally:
            self.stop.set()
            self.pool.stop()
            self.store.event("swarm.status", None, {"action": "stopped", "why": self.why_stopped or "asked"})
            self.heartbeat({"stopped": self.why_stopped or "asked"})
            log(f"stopped: {self.why_stopped or 'asked'}")
        return 0


def _config() -> dict[str, Any]:
    try:
        return json.loads((CODE_DIR / "league" / "config.json").read_text())
    except (OSError, ValueError):
        return {}


def _sail_client() -> Any:
    try:
        from ..sailbox import SailboxClient  # the options overhaul's home for it
    except ImportError:
        from ltcm.sailbox import SailboxClient
    return SailboxClient()


def main_run(root: str, *, once: bool = False) -> int:
    load_env(os.environ.get("LEAGUE_ENV") or (Path(root).parent / ".env"))
    swarm = Swarm(root)

    def on_term(signum: int, frame: Any) -> None:
        swarm.why_stopped = f"signal {signum}"
        swarm.stop.set()

    signal.signal(signal.SIGTERM, on_term)
    return swarm.run(once=once)


__all__ = ["Swarm", "Scheduler", "main_run", "load_env"]
