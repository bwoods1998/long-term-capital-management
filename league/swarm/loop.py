"""The swarm's process: `python -m league.swarm run --root /workspace/state`.

One process beside the House loop, niced. Its threads:

- RESEARCHERS: `researcher.concurrency` workers, each taking the next family (the bandit's share first,
  then the longest-waiting) and running one cycle, while the guard allows; a family that held waits out its hold
  (`Scheduler`'s durable event-driven holds);
- THE GYM POOL's dispatchers (one per box) and forks (`pool.py`);
- ROUNDS on their own threads so none blocks another: the tournament (hourly), the idle pass between its rounds (every
  five minutes, the idle rule's retirements alone: `Tournament.idle_pass`), the gate (every few
  minutes), the nightly forward (once a day), the architect (`architect.every_seconds`, four hours by default), the
  diagnostician (every few
  minutes, Claude on the stuck and the nearly-there families);
- RESEEDS (the sprint, Sept 26): below `population.start` while the architect is not due, the seeds' mechanisms are
  founded again on admitted roots they never tried (`reseed`, at most `population.reseed_max` a pass);
- THE MAIN LOOP (every few seconds): re-read the settings, check the guard (brake: the Gym to sleep and the
  researchers idle), manage the pool, start the rounds that are due, write the heartbeat, and leave when
  asked (the STOP files, `<root>/swarm.stop`) or when the House's release changed (the House starts the new one).

The heartbeat (`<root>/swarm.heartbeat`, JSON) carries the pid, the release directory, the time, and a live
status (families, cycles and spend in the last hour by kind, the guard, the pool): the House's `SwarmStep`
reads it to supervise the process and the operator reads it to see the swarm.

Standard library only (the Gym's driver is imported when a box starts).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Mapping

from . import HEARTBEAT, LOCK_FILE, LOG_FILE, PID_FILE, settings as settings_mod
from .architect import Architect, GraveyardDigest
from .diagnostician import Diagnostician
from .gate import Gate
from .guard import SailGuard, provider_reader
from .pool import GymPool
from .researcher import Researcher, dormant_count, dormant_limit, migrate_objective
from .seeds import SEEDS, family_spec, program_for
from .store import SwarmStore
from .strategist import PAIR_SECONDS, Strategist
from .tournament import INDEX, NOT_ROTATED, Tournament

CODE_DIR = Path(__file__).resolve().parents[2]


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}  {message}", flush=True)


#: How often a standing 2020-21 switch alert is raised again as a `swarm.status` event (`Swarm.train_span_notice`).
TRAIN_SPAN_NOTICE_EVERY = 600.0


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


#: `researcher.hold_idle_seconds` and `researcher.hold_idle_max_seconds` unless the settings say otherwise (HOLD BACKOFF).
HOLD_IDLE_SECONDS = 300.0
HOLD_IDLE_MAX_SECONDS = 1800.0


def _seconds(raw: Any, default: float) -> float:
    """A wait in seconds: null is 0 (off); a boolean, a non-number, a negative or a non-finite number is the default."""
    if raw is None:
        return 0.0
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or raw < 0:
        return float(default)
    return float(raw)


def hold_wait(settings: Mapping[str, Any], dormant: int) -> float:
    """HOLD BACKOFF (R4, Sept 28): the wait before the next turn of a family whose cycle ended in a hold with no new
    evaluation and no run queued, its dormant cycles (`researcher.dormant_count`) counted after that cycle.
    `researcher.hold_idle_seconds`, doubled for each dormant cycle past `researcher.dormant_cycles` (a family the idle
    rule exempts while it holds: its best awaits validation, a version is at the gate, the population is at its floor),
    up to `researcher.hold_idle_max_seconds`. Below the dormancy clause's count it never doubles: doubling from the first
    hold would stretch the clause from about 3.4 hours of holds (40 x 300 s) to about 19 (40 holds, most of them 1800 s
    apart), keeping families whose mechanism is refuted in their slots. With the clause off (`dormant_cycles` 0) it
    doubles from the second hold. 0 when the backoff is off."""
    cfg = settings.get("researcher") or {}
    base = _seconds(cfg.get("hold_idle_seconds", HOLD_IDLE_SECONDS), HOLD_IDLE_SECONDS)
    if base <= 0:
        return 0.0
    cap = max(base, _seconds(cfg.get("hold_idle_max_seconds", HOLD_IDLE_MAX_SECONDS), HOLD_IDLE_MAX_SECONDS))
    past = max(0, int(dormant) - max(1, dormant_limit(settings)))
    return min(cap, base * 2.0 ** min(past, 30))


class Scheduler:
    """Which family runs next: the bandit's share first, then the longest wait; one cycle per family at a time.

    By default a hold is persisted in family state and resumes only when its evidence/context key changes.
    Time, weight changes and process restarts never buy another model call. Trials, gate state, rewrites,
    notebook guidance, the agenda, data and the harness release can wake it. Pending work stays runnable.
    ``researcher.hold_until_news=false`` restores the optional legacy timer (`hold_wait`); those waits
    are kept in memory and also end when news arrives. Only local evidence inspection is periodic."""

    #: A worker with nothing to take sleeps until the next family could be ready (its hold's end, its idle seconds, its
    #: cooldown), at least `MIN_PAUSE` and at most `MAX_PAUSE` (news is noticed within it), so idle workers do not all
    #: decode every family's state every 2 s while the families wait out holds.
    MIN_PAUSE = 2.0
    MAX_PAUSE = 10.0

    def __init__(self, store: SwarmStore, *, clock: Callable[[], float] = time.time, settings: Mapping[str, Any] | None = None):
        self.store = store
        self.clock = clock
        self.settings = settings if settings is not None else {}  # the Swarm's dict, re-read in place every loop
        self._lock = threading.Lock()
        self.running: set[str] = set()
        self.last: dict[str, float] = {}
        self.cooldown: dict[str, float] = {}
        self.errors: dict[str, int] = {}
        #: family -> (trials, gate_ready, band) when its running cycle began: the baseline of its news (HOLD BACKOFF).
        self.began: dict[str, tuple[int, bool, Any]] = {}
        #: family -> (since, until, trials, gate_ready, band, dormant) while it waits out a hold (HOLD BACKOFF).
        self.held: dict[str, tuple[float, float, int, bool, Any, int]] = {}
        self.soon = float("-inf")  # when the last `take` that found nothing saw the next family ready (`pause`)

    @property
    def event_holds(self) -> bool:
        """Waiting is free: a held researcher resumes on new evidence, never merely on a timer."""
        return (self.settings.get("researcher") or {}).get("hold_until_news", True) is not False

    def evidence_key(self, fam: Mapping[str, Any]) -> str:
        """Only actionable context invalidates a durable hold, not weights, spend, or wall-clock time.

        Notebook additions include operator/diagnostician guidance. A changed agenda, admitted data image,
        release, or explicit ``research_wake`` token also gives a parked family something new to work with.
        No validation numbers or holdout observations are exposed to the model by this scheduling key.
        """
        state, gym = fam.get("state") or {}, self.settings.get("gym") or {}
        notes = self.store.notebook(str(fam["id"]), limit=1)
        agenda = self.store.get("architect_agenda_section") or {}
        from .practice import feedback_revision
        body = {
            "family": {key: fam.get(key) for key in ("trials", "band", "revisions", "best_version", "validated_version", "validations")},
            "state": {key: state.get(key) for key in ("gate_ready", "gate_hold", "look_inflight", "gated_sha", "rewrite_ready",
                       "extension_hold", "research_wake", "research_feedback_revision")},
            "note": notes[-1]["seq"] if notes else None,
            "agenda": agenda.get("text") if isinstance(agenda, Mapping) else agenda,
            "gym": {key: gym.get(key) for key in ("image_checkpoint", "gate_checkpoint", "train_from")},
            "release": str(CODE_DIR),
            "practice": feedback_revision(self.store, self.settings, str(fam["id"])),
        }
        return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def seen(fam: Mapping[str, Any]) -> tuple[int, bool, Any]:
        return int(fam.get("trials") or 0), bool((fam.get("state") or {}).get("gate_ready")), fam.get("band")

    @staticmethod
    def news(fam: Mapping[str, Any], held: tuple[float, float, int, bool, Any, int]) -> bool:
        """Something the family's researcher should read happened since the hold's baseline."""
        _, _, trials, gate_ready, band, dormant = held
        trials_now, gate_now, band_now = Scheduler.seen(fam)
        return (trials_now > trials or gate_now != gate_ready or band_now != band or dormant_count(fam) < dormant
                or bool((fam.get("state") or {}).get("rewrite_ready")))

    def holding(self, fam: Mapping[str, Any], now: float) -> bool:
        """The family waits out a hold (HOLD BACKOFF); a wait that ran out, that news lifted or that the clock going back
        passed is forgotten. Under the lock."""
        if self.event_holds:
            wait = (fam.get("state") or {}).get("research_wait")
            if isinstance(wait, Mapping) and wait.get("format") == 1:
                return wait.get("evidence") == self.evidence_key(fam)
            return False
        held = self.held.get(fam["id"])
        if held is None:
            return False
        since, until = held[0], held[1]
        if now >= until or now < since or self.news(fam, held):
            del self.held[fam["id"]]
            return False
        return True

    def waiting(self) -> int:
        """Families waiting out a hold now (the heartbeat's `holding`): not a retired one, nor one whose news lifted it."""
        fams = self.store.families(alive=True)
        now = self.clock()
        with self._lock:
            self._prune(fams)
            return sum(1 for f in fams if self.holding(f, now))

    def _prune(self, fams: list[dict[str, Any]]) -> None:
        """Forget the holds of families no longer alive (under the lock)."""
        alive = {f["id"] for f in fams}
        for fid in [fid for fid in self.held if fid not in alive]:
            del self.held[fid]

    def pause(self) -> float:
        """How long a worker that found nothing to take sleeps: until the next family could be ready as the last such
        `take` saw it, within [MIN_PAUSE, MAX_PAUSE] (MAX_PAUSE when every family was in a cycle)."""
        return max(self.MIN_PAUSE, min(self.MAX_PAUSE, self.soon - self.clock()))

    def take(self, *, idle_seconds: float = 5.0) -> str | None:
        now = self.clock()
        fams = self.store.families(alive=True)
        with self._lock:
            self._prune(fams)
            ready, soon = [], float("inf")
            for f in fams:
                if f["id"] in self.running:
                    continue
                # A last turn "in the future" (the clock went back) never strands a family (nor, `holding`, does a hold).
                at = max(self.cooldown.get(f["id"], 0), min(self.last.get(f["id"], 0), now) + idle_seconds)
                if self.holding(f, now):
                    if self.event_holds:
                        continue  # local polling may inspect evidence; no paid model turn is scheduled
                    at = max(at, self.held[f["id"]][1])
                if at <= now:
                    ready.append(f)
                else:
                    soon = min(soon, at)
            if not ready:
                self.soon = soon
                return None
            n = max(1, len(fams))
            # A family's share (the bandit's) buys it an earlier turn: a share at the average is worth nothing, twice it
            # is worth a minute of waiting.
            ready.sort(key=lambda f: (self.last.get(f["id"], 0) - 60.0 * (float(f.get("weight") or (1.0 / n)) * n - 1.0), f["id"]))
            fid = ready[0]["id"]
            self.running.add(fid)
            self.last[fid] = now
            self.began[fid] = self.seen(ready[0])
            return fid

    def busy(self, fid: str) -> bool:
        """The family is in a researcher's cycle now."""
        with self._lock:
            return fid in self.running

    def _hold_after(self, fid: str, result: Mapping[str, Any], began: tuple[int, bool, Any] | None) -> tuple | None:
        """The hold a finished cycle leaves (HOLD BACKOFF), or None: only a hold with no new evaluation and no run queued,
        on a living family, with no news since its cycle began (a result landing mid-cycle, unseen by its model, is news)."""
        if not result.get("hold") or int(result.get("trials") or 0) or result.get("pending_run") or result.get("retired"):
            return None
        fam = self.store.family(fid)
        if fam is None or fam.get("retired_at"):
            return None
        dormant = dormant_count(fam)
        wait = float("inf") if self.event_holds else hold_wait(self.settings, dormant)
        counted = result.get("dormant_cycles")
        if wait <= 0 or (isinstance(counted, int) and dormant < counted):
            return None  # no backoff; or its dormant count restarted since the cycle ended (a result of its own landed)
        now = self.clock()
        held = (now, now + wait, *(began if began is not None else self.seen(fam)), dormant)
        return None if self.news(fam, held) else held

    def release(self, fid: str, result: Mapping[str, Any]) -> None:
        """The cycle ended: its hold (if any) is recorded and its error backs it off. Never raises, and the family is never
        left marked running (a store that cannot be read means no hold wait)."""
        result = result if isinstance(result, Mapping) else {}
        with self._lock:
            began = self.began.pop(fid, None)
        try:
            with self.store.atomic():
                held = self._hold_after(fid, result, began)
                fam = self.store.family(fid)
                if fam is not None:
                    # Durable across process restarts; creating it in the same transaction as the evidence read
                    # prevents a late result or guidance note from being swallowed by the hold baseline.
                    wait = ({"format": 1, "since": self.clock(), "evidence": self.evidence_key(fam)}
                            if self.event_holds and held is not None else None)
                    if wait is not None or (fam.get("state") or {}).get("research_wait") is not None:
                        self.store.set_state(fid, research_wait=wait)
        except Exception:  # noqa: BLE001 - a hold is an economy, never a reason to strand a family
            held = None
        with self._lock:
            try:
                if held is None:
                    self.held.pop(fid, None)
                else:
                    self.held[fid] = held
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
            finally:
                self.running.discard(fid)


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
        self.scheduler = Scheduler(self.store, clock=clock, settings=self.settings)
        self.researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=clock,
                                     starter=lambda spec: program_for(spec))
        self.researcher.pace = self.over_pace
        self.tournament = Tournament(self.store, self.pool, self.settings, clock=clock)
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=clock)
        # The whole graveyard as one sealed digest, shared by the architect and the strategist (Sept 29, 2026): one pass's
        # two Claude calls send the same bytes, so the second reads the first's cache entry.
        self.digest = GraveyardDigest(self.store, self.settings, clock=clock)
        self.architect = Architect(self.store, self.router, self.settings, clock=clock, digest=self.digest)
        self.strategist = Strategist(self.store, self.router, self.settings, digest=self.digest, clock=clock,
                                     architect=self.architect)
        self.diagnostician = Diagnostician(self.store, self.router, self.settings, pool=self.pool, researcher=self.researcher,
                                           clock=clock)
        self.stop = threading.Event()
        self.workers: list[threading.Thread] = []
        self.rounds: dict[str, threading.Thread] = {}
        self.started_at = clock()
        self.why_stopped = ""
        self._beat = float("-inf")
        self._pace = (float("-inf"), "", 0.0)

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
        # The first tournament an hour after the founding (it validates what the first hour's cycles submitted), and the
        # architect after it: a round over families that have not run yet would only spend.
        self.store.put("tournament_at", self.clock())
        self.store.put("architect_at", self.clock())
        return born

    def reseed(self) -> list[str]:
        """Families from the seeds on admitted roots their mechanism never tried (a seed never founded on its own slice
        first), while fewer than `population.start` live, at most `population.reseed_max` a pass and one a seed. A
        reseed of a founded mechanism joins that founder's lineage like a fork (its trials, validated versions and
        holdout looks); never XSP (its fee), never a calendar or diagonal on an index root. Each is a `swarm.born`."""
        pop = self.settings.get("population", {})
        room = min(int(pop.get("start", 48)) - len(self.store.families(alive=True)), int(pop.get("reseed_max", 0)))
        if room <= 0:
            return []
        admitted = [str(r).upper() for r in self.settings.get("gym", {}).get("roots", []) if str(r).upper() not in NOT_ROTATED]
        families = self.store.families()
        born: list[str] = []
        for seed in SEEDS:
            if len(born) >= room:
                break
            mechanism = " ".join(str(seed["mechanism"]).split())
            kin = [f for f in families if f["mechanism"] == mechanism]
            tried = {r for f in kin for r in f["roots"]}
            own = [r.upper() for r in seed["roots"]]
            choices = ([own] if not kin and all(r in admitted for r in own) else []) + [[r] for r in admitted if r not in tried]
            for roots in choices:
                if seed["structure"] in ("calendar", "diagonal") and any(r in INDEX for r in roots):
                    continue
                spec = family_spec(seed)
                spec.update({"id": seed["id"] if roots == own else f"{seed['id']}-{roots[0].lower()}", "roots": roots,
                             "needs": {**spec["needs"], "roots": roots}, "seed": seed["id"]})
                founder = next((f for f in kin if f["origin"] in ("seed", "reseed")), None)
                dead = [f for f in families if f["retired_at"] and f["structure"] == seed["structure"] and sorted(f["roots"]) == roots]
                with self.store.atomic():
                    if len(self.store.families(alive=True)) >= int(pop.get("start", 48)):
                        return born
                    fam = self.store.add_family(spec, origin="reseed", parent=founder["id"] if founder else None,
                                                prior_lineage=dead[-1]["lineage"] if dead and not founder else None)
                self.store.event("swarm.born", fam["id"], {"parent": founder["id"] if founder else None, "mechanism": fam["mechanism"],
                                                            "structure": fam["structure"], "roots": fam["roots"], "origin": "reseed",
                                                            "founder": seed.get("founder")})
                born.append(fam["id"])
                families.append(fam)
                break
        return born

    # ------------------------------------------------------------------ status and heartbeat
    def status(self) -> dict[str, Any]:
        now = self.clock()
        hour = now - 3600
        spend = {k: round(self.store.spent([k], since=hour), 4) for k in ("sail_model", "gym_box", "openai", "claude")}
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(hour))
        recent = [json.loads(row["payload"]) for row in
                  self.store._all("SELECT payload FROM events WHERE kind='swarm.cycle' AND at >= ? ORDER BY seq DESC LIMIT 3000", (since,))]
        seconds = sorted(float(p.get("seconds") or 0) for p in recent[:300] if not p.get("error"))
        return {"families_alive": len(self.store.families(alive=True)), "running": len(self.scheduler.running),
                "holding": self.scheduler.waiting(),
                "totals": self.store.totals(), "spend_last_hour": spend, "usd_per_hour": round(sum(spend.values()), 4),
                "median_cycle_seconds": seconds[len(seconds) // 2] if seconds else None, "cycles_last_hour": len(recent),
                "cycle_errors_last_hour": sum(1 for p in recent if p.get("error")),
                "researcher_pace": self.pace_status(),
                "guard": getattr(self.guard, "last", {}), "braked": not self.guard.allows(), "pool": self.pool.status(),
                "rounds": sorted(k for k, t in self.rounds.items() if t.is_alive())}

    def heartbeat(self, extra: Mapping[str, Any] | None = None) -> None:
        body = {"pid": os.getpid(), "at": self.clock(), "release": str(CODE_DIR), "started_at": self.started_at,
                "status": self.status(), **(extra or {})}
        if getattr(self, "span_alert", None):
            body["train_span_alert"] = self.span_alert.get("text")
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
    def gym_ready(self) -> bool:
        """The Gym is configured (enabled, with an image) and its boxes start (not `unavailable` after repeated start-up
        failures): until then nothing that needs it starts (no model is paid to wait for a box that cannot come)."""
        gym = self.settings.get("gym", {})
        unavailable = getattr(self.pool, "unavailable", lambda kind="gym": False)
        return bool(gym.get("enabled")) and bool(gym.get("image_checkpoint")) and not unavailable("gym")

    def pace_status(self) -> dict[str, Any]:
        """The funded researcher stream's trailing-hour spend; absent/null Sail limit keeps the legacy combined cap."""
        cfg = self.settings.get("researcher", {})
        sail_limit = cfg.get("sail_usd_per_hour")
        scope = "sail_model" if sail_limit is not None else "all_models"
        key = "sail_usd_per_hour" if sail_limit is not None else "usd_per_hour"
        raw_limit = sail_limit if sail_limit is not None else cfg.get("usd_per_hour", 4.0)
        try:
            limit = float(raw_limit)
            valid = not isinstance(raw_limit, bool) and math.isfinite(limit) and limit >= 0
        except (TypeError, ValueError, OverflowError):
            limit, valid = 0.0, False
        now = self.clock()
        cached = self._pace
        if now - cached[0] >= 10.0 or now < cached[0] or cached[1] != scope:
            spent = self.store.spent(["sail_model"] if scope == "sail_model" else ["sail_model", "openai"], since=now - 3600)
            cached = self._pace = (now, scope, spent)
        paused = not valid or cached[2] >= limit
        label = "Sail models" if scope == "sail_model" else "Sail and OpenAI models"
        reason = (f"invalid researcher.{key}; research paused" if not valid else
                  f"{label} spent ${cached[2]:.4f} in the last hour, at the ${limit:.4f} pace" if paused else None)
        return {"scope": scope, "limit_usd_per_hour": limit if valid else None,
                "spent_last_hour_usd": round(cached[2], 6), "paused": paused, "reason": reason}

    def over_pace(self) -> bool:
        """No new cycles/rewrites above their configured model pace (spend reads cached for at most 10 s)."""
        return self.pace_status()["paused"]

    def _worker(self, index: int) -> None:
        idle = float(self.settings.get("researcher", {}).get("idle_seconds", 5))
        while not self.stop.is_set():
            if not self.guard.allows() or not self.gym_ready() or index >= int(self.settings.get("researcher", {}).get("concurrency", 48)):
                self.sleep(5.0)
                continue
            if self.over_pace():
                self.sleep(10.0)
                continue
            fid = self.scheduler.take(idle_seconds=idle)
            if fid is None:
                self.sleep(self.scheduler.pause())
                continue
            result: dict[str, Any] = {}
            try:
                result = self.researcher.cycle(fid)
            except Exception as exc:  # noqa: BLE001 - never kill a worker
                result = {"error": f"{type(exc).__name__}: {exc}"}
                log(f"cycle {fid} crashed: {traceback.format_exc()[-800:]}")
            finally:
                try:
                    self.scheduler.release(fid, result)
                except Exception:  # noqa: BLE001 - release never strands the family (it leaves `running` first)
                    log(f"release {fid} failed: {traceback.format_exc()[-800:]}")

    def architect_pass(self) -> dict[str, Any]:
        """The architect's round: the strategist first when it is due and this pass may add families (only the architect
        reads its section, so it never writes one nobody reads), then the architect. The architect's call marks the
        sealed digest for the five-minute cache only when the strategist's last Claude call just marked it and started
        less than PAIR_SECONDS ago (the entry lives five minutes from the start of the call that wrote or last read it). A strategist that
        fails or raises leaves the agenda as it was and never stops the architect."""
        out: dict[str, Any] = {}
        began = self.clock()
        try:
            if self.architect.want() > 0 and self.strategist.due():
                out["strategist"] = self.strategist.run()
        except Exception as exc:  # noqa: BLE001 - run() never raises; this is the belt to its braces
            out["strategist"] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        ran = out.get("strategist") or {}
        # From the start of the strategist's last Claude call that marked the digest (a repair turn's read refreshes the
        # entry), else from the pass's start.
        primed_at = ran.get("primed_at")
        since = float(primed_at) if isinstance(primed_at, (int, float)) and not isinstance(primed_at, bool) else began
        paired = bool(ran.get("primed")) and self.clock() - since < PAIR_SECONDS
        return {**self.architect.run(paired=paired), **({"strategist": {k: ran.get(k) for k in (
            "accepted", "route", "cost_usd", "reasons", "skipped", "error", "primed", "turns", "note")}} if ran else {})}

    def round_alive(self, name: str) -> bool:
        thread = self.rounds.get(name)
        return thread is not None and thread.is_alive()

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

    def train_span_notice(self) -> dict[str, Any] | None:
        """THE 2020-21 SWITCH, as the operator sees it, while something about it stands: `gym.train_from` snapped, ignored or
        missing while Train is not 2022-2024 (`settings.train_from_note`: the running span is kept, never a silent switch
        back), or asking for a Train span the running swarm has not migrated to (its next start does). Every loop it is in
        the heartbeat (`train_span_alert`); the `swarm.status` alert and the log line come when it changes and again every
        `TRAIN_SPAN_NOTICE_EVERY` seconds until it is resolved. Returns the event's payload when one was raised."""
        running = settings_mod.objective_span(self.store.get("train_objective"))
        wanted = settings_mod.train_from(self.settings, running)
        note = settings_mod.train_from_note(self.settings, running)
        if note is None and wanted == running:
            self.span_alert = None
            return None
        raw = (self.settings.get("gym") or {}).get("train_from")
        text = " ".join(x for x in (note, None if wanted == running else
                                    f"gym.train_from asks for Train from {wanted}; the running swarm scores Train from {running} "
                                    "until its next start migrates (restart the swarm, with the matching Gym image)") if x)
        payload = {"action": "train_span_pending" if wanted != running else "train_from_setting", "alert": True, "text": text,
                   "setting": raw, "wanted": wanted.isoformat(), "running": running.isoformat()}
        self.span_alert = payload
        seen = f"{raw!r}|{running}"
        last = self.store.get("train_span_notice")
        now = float(self.clock())
        if isinstance(last, dict) and last.get("seen") == seen and now - float(last.get("at") or 0) < TRAIN_SPAN_NOTICE_EVERY:
            return None
        self.store.put("train_span_notice", {"seen": seen, "at": now})
        self.store.event("swarm.status", None, payload)
        log(text)
        return payload

    def step(self) -> None:
        """One pass of the main loop (tests call it directly)."""
        fresh = settings_mod.load(self.root, config=self.config)
        self.settings.update(fresh)  # in place (every piece holds this dict), and no key ever disappears mid-read
        try:
            self.train_span_notice()
        except Exception:  # noqa: BLE001 - a notice never stops the loop
            pass
        if getattr(self.guard, "due", lambda: True)():
            was = not self.guard.allows()
            self.guard.check()
            try:  # requests a stopped process left in flight: settled or released (their holds would count forever)
                self.router.provider.reconcile_stale()
                self.router.settle_holds()  # what the swarm booked for unanswered calls, trued up
            except Exception:  # noqa: BLE001
                pass
            try:  # old conversations out of the Provider's file (the disk)
                self.router.compact()
            except Exception:  # noqa: BLE001
                pass
            if not self.guard.allows():
                if not was:
                    log(f"guard: brake ({getattr(self.guard, 'reason', '')})")
                self.pool.scale_to_zero(getattr(self.guard, "reason", "the guard"))
        self.pool.manage()
        if self.guard.allows() and self.gym_ready():
            if self.tournament.due():
                self._round("tournament", self.tournament.run)
            elif self.tournament.idle_due() and not self.round_alive("tournament"):
                # THE IDLE PASS: the idle rule alone between the hourly rounds, never while one runs (its validations may be
                # re-validating the very families the pass would judge), never on a family in a researcher's cycle.
                self._round("idle", lambda: self.tournament.idle_pass(busy=self.scheduler.busy))
            if self.gate.due():
                self._round("gate", self.gate.run)
            if self.gate.forward_due():
                self._round("forward", self.gate.forward)
            # Refilling to the start population always (a birth spends nothing by itself: the pace caps all cycles);
            # growing past it toward the ceiling only while the hourly spend is under the pace.
            if self.architect.due() and self.store.get("tournament_at") and (self.architect.refilling() or not self.over_pace()):
                self._round("architect", self.architect_pass)
            elif self.architect.refilling() and not self.architect.due() and self.store.get("tournament_at"):
                born = self.reseed()
                if born:
                    log(f"reseeded {len(born)}: {', '.join(born)}")
            if self.diagnostician.due():  # Claude's own funded line and daily budget, not the researchers' pace
                self._round("diagnostician", self.diagnostician.run)
        if self.clock() - self._beat >= float(self.settings.get("heartbeat_seconds", 20)):
            self._beat = self.clock()
            self.heartbeat()
            self.bound_log()

    def run(self, *, once: bool = False) -> int:
        """The process: seed, start the workers, loop until asked to stop."""
        try:
            os.nice(int(self.settings.get("nice", 10)))
        except OSError:
            pass
        if not self.take_lock():
            log("not starting: another swarm holds the lock (one swarm per state root)")
            return 0
        (self.root / PID_FILE).write_text(str(os.getpid()))
        why = self.should_stop()
        if why:
            log(f"not starting: {why}")
            self.release_lock()
            return 0
        self._beat = self.clock()
        self.heartbeat({"starting": True})  # before any network call: the House sees it alive at once
        born = self.seed()
        if born:
            log(f"seeded {len(born)} families")
        # once per store and Train span (`gym.train_from`, the 2020-21 switch): the bests chosen anew under the robust Train
        # objective, beating so the House waits for it
        try:
            moved = migrate_objective(self.store, beat=lambda: self.heartbeat({"starting": True, "migrating": True}),
                                      settings=self.settings)
            if moved["migrated"] or moved["failed"]:
                log(f"train objective: {moved['migrated']} families' bests chosen anew, {moved['with_best']} with an eligible best, "
                    f"{moved['failed']} emptied after an error")
        except Exception:  # noqa: BLE001 - the migration never keeps the swarm from starting; it runs again next start
            log(f"train objective migration failed: {traceback.format_exc()[-800:]}")
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
            # Forks in flight get a short wait (the House kills a swarm 30 s after asking it to stop).
            self.pool.stop(join_seconds=float(self.settings.get("gym", {}).get("stop_join_seconds", 15)))
            try:  # a stopped swarm leaves no box awake (the next one adopts and wakes them)
                self.pool.scale_to_zero(f"the swarm stopped: {self.why_stopped or 'asked'}", busy=True)
            except Exception:  # noqa: BLE001
                pass
            self.store.event("swarm.status", None, {"action": "stopped", "why": self.why_stopped or "asked"})
            self.heartbeat({"stopped": self.why_stopped or "asked"})
            log(f"stopped: {self.why_stopped or 'asked'}")
            self.release_lock()
        return 0

    def bound_log(self, max_bytes: int = 50 * 2 ** 20) -> None:
        """The swarm's own log (its stdout, opened for appending by the House) never grows past `max_bytes`: it is cut
        back to empty, and says so (the House also rotates it at each start)."""
        path = self.root / LOG_FILE
        try:
            if path.stat().st_size > max_bytes:
                os.truncate(path, 0)
                log(f"the log passed {max_bytes // 2 ** 20} MB and was cut")
        except OSError:
            pass

    # ------------------------------------------------------------------ one swarm per state root
    lock_tries = 10

    def take_lock(self) -> bool:
        """An exclusive flock on `<root>/swarm.lock`, held for the process's life (the kernel drops it when the process
        dies), with this process's pid, start time and release written in it. Tried for a few seconds: the House's
        supervisor tests the lock with a moment's flock of its own."""
        import fcntl

        handle = open(self.root / LOCK_FILE, "a+")  # noqa: SIM115 - held until release_lock
        for attempt in range(max(1, int(self.lock_tries))):
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if attempt == int(self.lock_tries) - 1:
                    handle.close()
                    return False
                time.sleep(0.5)
        from .hook import read_proc

        seen = read_proc(os.getpid())
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid(), "start": seen[1] if seen else None, "release": str(CODE_DIR),
                                 "at": self.clock()}))
        handle.flush()
        self._lock_handle = handle
        return True

    def release_lock(self) -> None:
        handle = getattr(self, "_lock_handle", None)
        if handle is not None:
            handle.close()
            self._lock_handle = None


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
