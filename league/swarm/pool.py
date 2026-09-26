"""The Gym pool: sealed size-l boxes forked from the Gym image, driven in batches, asleep when idle.

- BOXES. A Gym box is a fork of the Gym image checkpoint (`gym.image_checkpoint`; W1 records it in
  `.data/gym/images.json`), sealed (`no_network`, kept from the image), size l. The pool starts
  `start_boxes` (4) when there is work, grows to `max_boxes` (8) while the queue is long and the guard
  allows, puts a box to sleep after `idle_sleep_seconds` without work (a sleeping box costs nothing),
  and terminates a box whose image is no longer the configured one (a version change). Gate boxes are
  forks of the GATE image (holdout and forward days), one at a time, used only by the gate and the
  nightly forward replays; a Gym box never opens a sealed window (the Gym's own capability check).
- BATCHES. Jobs (one program version, one window) queue here; a box's dispatcher takes up to
  `batch_programs` jobs with the same settings and runs them together, day-major (the Gym's
  `driver.run`: each day's chain is loaded once for the whole batch). The highest priority first (the
  bandit's share), then the oldest; a short batch waits `batch_wait_seconds` for company.
- FAILURES. A root the box's store lacks fails its job at once with the Gym's own words; a batch that
  errs or times out is retried once on another box, then its jobs fail. A failure never kills the pool.
- COST. Every awake second of a box (starting, ready and idle, busy, resuming) is booked at `box_usd_hour`
  as `gym_box` spend, at least every `book_seconds` and whenever it sleeps or ends (an estimate: Sail bills
  boxes on measured use, about $0.12-0.20 an hour for a busy l box; Sail's meter is the record, and the
  guard reads the balance itself). A sleeping box books nothing.
- NAMES. Every box is `ltcm-swarm-<token>-<kind>-<epoch>-<n>`; the token is the store's own (kv
  `pool_token`), so a pool sweeps (`reconcile`) only its own strays, never another state root's (a laptop
  trial's) boxes, and never one forked in the last `reconcile_grace_seconds`. Stage 1 (Sept 26, 10:22Z) named
  its boxes `ltcm-swarm-<kind>-<epoch>-<n>` without a token: `adopt` takes back every box the store knows
  whatever its name, and `reconcile` also ends an untokened one it does not know (`LEGACY_NAME`).
- CAP. `max_boxes` counts every live box of the kind the pool holds, the store records, or Sail lists.

The Gym's driver (`league.gym.driver.GymDriver`) is imported when a box starts; tests hand in fakes.
Standard library only.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .store import SwarmStore

_IDS = itertools.count(1)
#: The name of every box the pool forks begins with this (and no other box on the account's does).
NAME_PREFIX = "ltcm-swarm-"


class PoolError(RuntimeError):
    """A job could not be run (the message says why)."""


@dataclass
class GymJob:
    """One program version over one window."""

    family: str
    version: int | None
    code: str
    params: dict[str, Any]
    window: str
    roots: tuple[str, ...]
    stress: float = 1.0
    purpose: str = "train"
    gate: str | None = None          # the gate's reason (holdout or forward): gate boxes only
    detail: str = "full"
    split: int | None = None
    start: str | None = None
    end: str | None = None
    priority: float = 0.0
    id: int = field(default_factory=lambda: next(_IDS))
    created: float = field(default_factory=time.time)
    attempts: int = 0
    result: dict[str, Any] | None = None
    batch: dict[str, Any] | None = None
    error: str | None = None
    done: threading.Event = field(default_factory=threading.Event)
    #: Called with the result when it arrives after its waiter gave up (`GymPool.wait` timed out): an evaluation the Gym
    #: made is a trial whether or not anyone was still waiting for it.
    late: Any = None
    #: Called with the reason when a job whose waiter gave up then FAILS (retried out, cancelled, missing data): the
    #: waiter's owner learns the job will never land (the gate owes a look it could not make).
    late_fail: Any = None

    @property
    def name(self) -> str:
        return f"j{self.id}-{self.family}"[:80].replace("/", "-")

    def key(self) -> tuple:
        return (self.gate or "", self.window, float(self.stress), self.detail, self.split, self.start, self.end)


@dataclass
class Box:
    id: str
    kind: str                         # gym | gate
    version: str                      # the image checkpoint it was forked from
    state: str = "starting"           # starting | ready | busy | asleep | terminated | failed
    driver: Any = None
    roots: tuple[str, ...] = ()       # roots its store holds for the train/validation windows
    last_used: float = 0.0
    booked_at: float = 0.0
    thread: threading.Thread | None = None
    failures: int = 0


AWAKE = ("starting", "ready", "busy")
#: A box name from before the per-store token (the stage-1 release): ours, whichever store made it.
LEGACY_NAME = re.compile(r"^ltcm-swarm-(gym|gate)-\d+-\d+$")


def forked_at(row: Mapping[str, Any]) -> float | None:
    """When Sail made a listed box: its `created_at` (epoch or ISO), else the epoch in our own name."""
    value = row.get("created_at")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    parts = str(row.get("name") or "").split("-")
    return float(parts[-2]) if len(parts) >= 2 and parts[-2].isdigit() else None


class GymPool:
    """The pool (the module docstring)."""

    def __init__(self, store: SwarmStore, client: Any, settings: Mapping[str, Any], *, driver_factory: Callable[..., Any] | None = None,
                 clock: Callable[[], float] = time.time, allowed: Callable[[str], bool] | None = None,
                 threaded: bool = True):
        self.store = store
        self.client = client
        self.settings = settings
        self.driver_factory = driver_factory
        self.clock = clock
        self.allowed = allowed or (lambda kind: True)
        self.threaded = threaded
        self._lock = threading.RLock()
        self._wake = threading.Condition(self._lock)
        self.queue: list[GymJob] = []
        self.boxes: dict[str, Box] = {}
        self._stopping = False
        self.stats = {"batches": 0, "jobs": 0, "failed_jobs": 0, "program_years": 0.0, "seconds": 0.0}
        self._counter = itertools.count(1)
        self.fork_failures: dict[str, int] = {}
        self.fork_after: dict[str, float] = {}
        self.fork_times: list[float] = []
        self.reconciled_at = float("-inf")
        #: Forks whose POST is in flight, by name (persisted as `forking` for the operator; a new process starts with none:
        #: a fork a dead process left in flight is a stray, ended by `reconcile`).
        self.forking: dict[str, float] = {}
        #: The fork threads (joined by `stop`).
        self.fork_threads: list[threading.Thread] = []
        self.token = str(store.get("pool_token") or "")
        if not self.token:
            self.token = secrets.token_hex(3)
            store.put("pool_token", self.token)

    # ------------------------------------------------------------------ settings
    @property
    def gym(self) -> Mapping[str, Any]:
        return self.settings.get("gym", {})

    def image(self, kind: str) -> str | None:
        return self.gym.get("image_checkpoint") if kind == "gym" else self.gym.get("gate_checkpoint")

    # ------------------------------------------------------------------ jobs
    def submit(self, job: GymJob) -> GymJob:
        """Queue a job. A family has at most one Train job waiting: a newer one supersedes it (its waiter, if any, is
        told; it never ran), so a backlog of orphaned versions cannot build up."""
        job.created = self.clock()
        with self._wake:
            if job.purpose == "train" and not job.gate:
                for old in [j for j in self.queue if j.family == job.family and j.purpose == "train" and not j.gate]:
                    self.queue.remove(old)
                    self._fail(old, "superseded by a newer version before it ran")
            self.queue.append(job)
            self._wake.notify_all()
        return job

    def wait(self, job: GymJob, timeout: float | None = None, *, late: Any = None, late_fail: Any = None) -> dict[str, Any]:
        """The job's result. On a timeout the job leaves the queue if it has not started (nothing ran); if it is
        running, `late(result)` records it when it lands (it is still a trial), and `late_fail(why)` if it fails."""
        if not job.done.wait(timeout):
            with self._lock:
                if job in self.queue:
                    self.queue.remove(job)
                    job.error = "abandoned before it ran"
                else:
                    job.late = late
                    job.late_fail = late_fail
            if job.done.is_set() and job.result is not None and late is not None and job.late is not None:
                job.late = None
                late(job.result)
            raise PoolError(f"the Gym did not answer within {timeout:.0f} s (queue {self.queued()})")
        if job.error:
            raise PoolError(job.error)
        return job.result  # type: ignore[return-value]

    def run(self, job: GymJob, timeout: float | None = None, *, late: Any = None, late_fail: Any = None) -> dict[str, Any]:
        return self.wait(self.submit(job), timeout, late=late, late_fail=late_fail)

    def queued(self, kind: str | None = None) -> int:
        with self._lock:
            return sum(1 for j in self.queue if kind is None or (kind == "gate") == bool(j.gate))

    def cancel_family(self, family: str) -> None:
        with self._lock:
            for job in [j for j in self.queue if j.family == family]:
                self.queue.remove(job)
                self._fail(job, "the family retired")

    def _fail(self, job: GymJob, why: str) -> None:
        job.error = why
        self.stats["failed_jobs"] += 1
        callback, job.late_fail = job.late_fail, None
        job.done.set()
        if callback is not None:
            try:
                callback(why)
            except Exception:  # noqa: BLE001 - never breaks the dispatcher
                pass

    def _take(self, box: Box) -> list[GymJob]:
        """The next batch for `box` (called under the lock)."""
        gate = box.kind == "gate"
        mine = [j for j in self.queue if bool(j.gate) == gate]
        if not mine:
            return []
        mine.sort(key=lambda j: (-j.priority, j.created, j.id))
        head = mine[0]
        same = [j for j in mine if j.key() == head.key()][: max(1, int(self.gym.get("batch_programs", 8)))]
        wait = float(self.gym.get("batch_wait_seconds", 8))
        if len(same) < int(self.gym.get("batch_programs", 8)) and self.clock() - head.created < wait and not gate:
            return []
        for job in same:
            self.queue.remove(job)
        return same

    # ------------------------------------------------------------------ boxes
    def _driver(self, box_id: str) -> Any:
        if self.driver_factory is not None:
            return self.driver_factory(self.client, box_id)
        from ..gym.driver import GymDriver

        g = self.gym
        return GymDriver(self.client, box_id, remote_root=str(g.get("remote_root", "/workspace/gym")),
                         store_root=str(g.get("store_root", "/data/store")), python=str(g.get("python", "python3")))

    def name_prefix(self, kind: str) -> str:
        """Every box this pool forks is named `ltcm-swarm-<token>-<kind>-...`; no other box on the account is (W1's image
        boxes are `ltcm-<kind>-image-...`, the House `ltcm-floor`, another state root's pool has another token), so a
        stray of ours can be found and ended by its name alone."""
        return f"{NAME_PREFIX}{self.token}-{kind}-"

    def _start_box(self, kind: str) -> None:
        """Fork one box from its image, check its seal, make it ready (runs on its own thread). Its start-up time is booked;
        a failure backs the next fork off; the box is recorded as 'forking' before the POST, so a fork whose answer is
        lost is found by name and ended (`reconcile`)."""
        image = self.image(kind)
        n = next(self._counter)
        name = f"{self.name_prefix(kind)}{int(self.clock())}-{n}"
        placeholder = f"pending-{kind}-{n}"
        began = self.clock()
        with self._lock:
            if self._stopping:
                return
            self.boxes[placeholder] = Box(placeholder, kind, str(image), "starting")
            self.forking[name] = began  # a fork in flight: `reconcile` never takes it for a stray
            self.store.put("forking", dict(self.forking))
        try:
            row = self.client.from_checkpoint(image, name=name)
            box_id = str(row.get("sailbox_id"))
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.boxes.pop(placeholder, None)
                self.forking.pop(name, None)
                self.store.put("forking", dict(self.forking))
            self._failed_fork(kind, f"the fork failed: {str(exc)[:200]}")
            self.store.event("swarm.pool", None, {"action": "fork_failed", "kind": kind, "image": image, "error": str(exc)[:300]})
            self.reconciled_at = float("-inf")  # the POST may have created a box: reconcile before another fork
            return
        box = Box(box_id, kind, str(image), "starting", last_used=self.clock(), booked_at=began)
        with self._lock:
            self.boxes.pop(placeholder, None)
            self.boxes[box_id] = box
            self.store.upsert_box(box_id, kind=kind, version=str(image), state="starting", detail={"name": name})
            self.forking.pop(name, None)
            self.store.put("forking", dict(self.forking))
        try:
            if not self.sealed(box_id):
                self.store.event("swarm.pool", None, {"action": "unsealed", "box": box_id, "kind": kind, "image": image})
                raise RuntimeError(f"the fork of {image} is not sealed (no_network): refused")
            box.driver = self._driver(box_id)
            box.driver.ensure_code()
            roots = [r for r in self.gym.get("roots", [])]
            window = "holdout" if kind == "gate" else "train"
            try:
                report = box.driver.check_data(window, roots) if kind == "gym" else {"roots": {r: {"nbbo": 1} for r in roots}}
            except Exception as exc:  # noqa: BLE001 - a root missing: learn which roots it has, one by one
                report = {"roots": {}}
                for r in roots:
                    try:
                        box.driver.check_data(window, [r])
                        report["roots"][r] = {"nbbo": 1}
                    except Exception:  # noqa: BLE001
                        pass
                if not report["roots"]:
                    raise exc
            box.roots = tuple(sorted(r for r, row in (report.get("roots") or {}).items() if row and row.get("nbbo")))
        except Exception as exc:  # noqa: BLE001
            self._accrue(box)
            box.state = "failed"
            self._failed_fork(kind, str(exc)[:200])
            self.store.set_box_state(box_id, "failed")
            self.store.event("swarm.pool", None, {"action": "box_failed", "box": box_id, "kind": kind, "error": str(exc)[:400]})
            try:
                self.client.terminate(box_id)
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self.boxes.pop(box_id, None)
            return
        self._accrue(box)
        with self._wake:
            box.state = "ready"
            box.last_used = self.clock()
            self.fork_failures[kind] = 0
            self._wake.notify_all()
        self.store.upsert_box(box_id, kind=kind, version=str(image), state="ready", detail={"name": name, "roots": list(box.roots),
                                                                                           "bundle": getattr(box.driver, "version", None)})
        self.store.event("swarm.pool", None, {"action": "box_ready", "box": box_id, "kind": kind, "roots": list(box.roots)})
        if self._stopping:  # the pool stopped while this fork was in flight: it sleeps (the next process adopts it)
            self._sleep(box)
            return
        self._spawn(box)

    def sealed(self, box_id: str) -> bool:
        """The box runs under `no_network` (read back from Sail; a client that cannot say is trusted only in tests)."""
        read = getattr(self.client, "egress", None)
        if read is None:
            return True
        try:
            policy = read(box_id) or {}
        except Exception:  # noqa: BLE001 - cannot confirm the seal: not sealed
            return False
        document = policy.get("document") if isinstance(policy, Mapping) else None
        return bool(isinstance(document, Mapping) and document.get("no_network")) or policy.get("mode") == "no_network"

    def _failed_fork(self, kind: str, why: str = "") -> None:
        """Back off after a fork that failed or a box that never became ready: 60 s, doubling to 30 minutes. After
        `unavailable_after` failures in a row the Gym is UNAVAILABLE (researchers idle; one `swarm.status` alert)."""
        with self._lock:
            self.fork_failures[kind] = self.fork_failures.get(kind, 0) + 1
            failures = self.fork_failures[kind]
            self.fork_after[kind] = self.clock() + min(1800.0, 60.0 * 2 ** (failures - 1))
        if failures == int(self.gym.get("unavailable_after", 3)):
            self.store.event("swarm.status", None, {"action": f"{kind}_unavailable", "failures": failures, "why": why,
                                                    "image": self.image(kind), "alert": True,
                                                    "text": f"the {kind} boxes fail to start ({why[:160]}): the researchers idle"})

    def unavailable(self, kind: str = "gym") -> bool:
        return self.fork_failures.get(kind, 0) >= int(self.gym.get("unavailable_after", 3))

    def reconcile(self) -> int:
        """End every box on the account named like ours (`ltcm-swarm-`) that this pool does not know: a fork whose
        answer was lost, or one a process that died left behind. Returns how many were ended."""
        lister = getattr(self.client, "list_boxes", None)
        if lister is None:
            return 0
        try:
            rows = lister(limit=1000)
        except Exception:  # noqa: BLE001
            return 0
        with self._lock:
            known = set(self.boxes) | {r["id"] for r in self.store.boxes(live=True)}
            in_flight = set(self.forking)
        mine = f"{NAME_PREFIX}{self.token}-"
        grace = float(self.gym.get("reconcile_grace_seconds", 300))
        n = 0
        for row in rows:
            box_id, name = str(row.get("sailbox_id") or row.get("id") or ""), str(row.get("name") or "")
            if name in in_flight:
                continue  # its POST has not returned: ours, not a stray
            if not (name.startswith(mine) or LEGACY_NAME.match(name)) or box_id in known or str(row.get("status")) in ("terminated", "terminating",
                                                                                            "failed", "create_failed"):
                continue
            born = forked_at(row)
            if born is None or self.clock() - born < grace:
                continue  # made minutes ago (or cannot say when): a fork whose answer may still be on its way
            try:
                self.client.terminate(box_id)
                n += 1
                self.store.event("swarm.pool", None, {"action": "stray_terminated", "box": box_id, "name": name})
            except Exception:  # noqa: BLE001
                pass
        self.reconciled_at = self.clock()
        return n

    def _spawn(self, box: Box) -> None:
        if self.threaded:
            box.thread = threading.Thread(target=self._serve, args=(box,), name=f"gym-{box.id[-8:]}", daemon=True)
            box.thread.start()

    def _serve(self, box: Box) -> None:
        """A box's dispatcher: take a batch, run it, deliver; until the box stops."""
        while True:
            with self._wake:
                while True:
                    if self._stopping or box.state in ("terminated", "failed"):
                        return
                    if box.state in ("ready", "asleep") and self.allowed(box.kind):
                        batch = self._take(box)
                        if batch:
                            break
                    self._wake.wait(1.0)
            self.run_batch(box, batch)

    def run_batch(self, box: Box, batch: list[GymJob]) -> None:
        """Run one batch on one box and deliver its results (also called directly by tests)."""
        runnable, missing = [], []
        for job in batch:
            lacking = [r for r in job.roots if box.roots and r not in box.roots]
            (missing if lacking else runnable).append((job, lacking))
        for job, lacking in missing:
            self._fail(job, f"the Gym has no {job.window} data for {', '.join(lacking)} yet (it holds {', '.join(box.roots)})")
        batch = [job for job, _ in runnable]
        if not batch:
            return
        if box.state == "asleep":
            resuming = self.clock()
            try:
                self.client.resume(box.id)
            except Exception as exc:  # noqa: BLE001
                self._requeue(batch, f"resuming {box.id} failed: {exc}")
                box.booked_at = resuming
                self._accrue(box, awake=True)
                box.state = "failed"
                self.store.set_box_state(box.id, "failed")
                self.store.event("swarm.pool", None, {"action": "resume_failed", "box": box.id, "error": str(exc)[:300]})
                try:
                    self.client.terminate(box.id)
                except Exception:  # noqa: BLE001
                    pass
                return
            box.booked_at = resuming  # the resume is awake time
        box.state = "busy"
        self.store.set_box_state(box.id, "busy")
        head = batch[0]
        roots = sorted({r for j in batch for r in j.roots})
        split = head.split or int(self.gym.get("train_split" if head.window == "train" else "validation_split", self.gym.get("split", 8)))
        programs = {job.name: (job.code, dict(job.params or {})) for job in batch}
        began = self.clock()
        try:
            doc = box.driver.run(programs, window=head.window, roots=roots, workers=int(self.gym.get("workers", 8)), split=split,
                                 stress=float(head.stress), capital=float(self.gym.get("capital", 10000.0)), detail=head.detail,
                                 start=head.start, end=head.end, gate_reason=head.gate,
                                 timeout=int(self.gym.get("run_timeout_seconds", 900)))
        except Exception as exc:  # noqa: BLE001
            elapsed = self.clock() - began
            self._accrue(box, jobs=len(batch))
            box.failures += 1
            box.state = "ready" if box.failures < 3 else "failed"
            self.store.box_used(box.id, elapsed, jobs=0)
            self.store.set_box_state(box.id, box.state)
            self.store.event("swarm.pool", None, {"action": "batch_failed", "box": box.id, "jobs": len(batch),
                                                  "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            if type(exc).__name__ == "GymDataMissing":
                for job in batch:
                    self._fail(job, f"the Gym is missing data: {str(exc)[:300]}")
            else:
                self._requeue(batch, f"{type(exc).__name__}: {str(exc)[:300]}")
            if box.state == "failed":
                self._retire_box(box, "three failed batches")
            return
        elapsed = self.clock() - began
        self._accrue(box, jobs=len(batch))
        box.failures = 0
        box.last_used = self.clock()
        box.state = "ready"
        self.store.box_used(box.id, elapsed, jobs=len(batch))
        self.store.set_box_state(box.id, "ready")
        by_name = {str(r.get("program")): r for r in (doc.get("results") or []) if isinstance(r, Mapping)}
        info = dict(doc.get("batch") or {})
        years = 0.0
        for job in batch:
            result = by_name.get(job.name)
            if result is None:
                self._fail(job, "the batch returned no result for this program")
                continue
            result = {**result, "gym_image": box.version}  # which Gym (image: code and data) made it
            job.result = result
            job.batch = {**info, "box": box.id, "programs_in_batch": len(batch), "wall_seconds": round(elapsed, 2)}
            days = (result.get("summary") or {}).get("days") or len(result.get("daily") or [])
            years += float(days) / 252.0 * max(1, len(result.get("roots") or job.roots))
            with self._lock:
                late, job.late = job.late, None
                job.done.set()
            if late is not None:
                try:
                    late(result)
                except Exception:  # noqa: BLE001 - recording a late result never breaks the dispatcher
                    pass
        with self._lock:
            self.stats["batches"] += 1
            self.stats["jobs"] += len(batch)
            self.stats["program_years"] += years
            self.stats["seconds"] += elapsed

    def _accrue(self, box: Box, *, jobs: int = 0, awake: bool | None = None) -> None:
        """Book a box's awake seconds since it was last booked (none while it sleeps) and start its next stretch."""
        now = self.clock()
        with self._lock:
            was_awake = box.state in AWAKE if awake is None else awake
            seconds = now - box.booked_at if box.booked_at else 0.0
            box.booked_at = now
        if was_awake and seconds > 0 and not box.id.startswith("pending-"):
            self._book(box, seconds, jobs)

    def _book(self, box: Box, seconds: float, jobs: int) -> None:
        """Box time as `gym_box` spend at `box_usd_hour` (Sail bills measured use: a busy l box is about $0.12-0.20
        an hour, measured Sept 26)."""
        rate = float(self.gym.get("box_usd_hour", 0.20)) / 3600.0
        if seconds > 0:
            self.store.add_spend("gym_box", seconds * rate, detail={"box": box.id, "seconds": round(seconds, 1), "jobs": jobs})

    def _requeue(self, batch: Sequence[GymJob], why: str) -> None:
        with self._wake:
            for job in batch:
                job.attempts += 1
                if job.attempts >= 2:
                    self._fail(job, f"the Gym failed twice: {why}")
                else:
                    self.queue.append(job)
            self._wake.notify_all()

    def _retire_box(self, box: Box, why: str) -> None:
        self._accrue(box)
        box.state = "terminated"
        try:
            self.client.terminate(box.id)
        except Exception:  # noqa: BLE001
            pass
        self.store.set_box_state(box.id, "terminated")
        self.store.event("swarm.pool", None, {"action": "terminated", "box": box.id, "kind": box.kind, "why": why})

    # ------------------------------------------------------------------ the manager (the loop calls it)
    def awake(self, kind: str | None = None) -> list[Box]:
        with self._lock:
            return [b for b in self.boxes.values() if b.state in ("starting", "ready", "busy") and (kind is None or b.kind == kind)]

    def manage(self) -> dict[str, Any]:
        """Scale, sleep, book cost, retire stale versions. Never blocks on a fork (forks run on threads)."""
        now = self.clock()
        g = self.gym
        out: dict[str, Any] = {"started": 0, "slept": 0, "terminated": 0}
        with self._lock:
            for dead in [k for k, b in self.boxes.items() if b.state in ("terminated", "failed")]:
                self.boxes.pop(dead, None)  # nothing kept of a box that is gone
            boxes = list(self.boxes.values())
        for box in boxes:  # idle awake time is paid for too
            if box.state in AWAKE and box.booked_at and now - box.booked_at >= float(g.get("book_seconds", 300)):
                self._accrue(box)
        if now - self.reconciled_at >= float(g.get("reconcile_seconds", 600)):
            out["strays"] = self.reconcile()
        for kind in ("gym", "gate"):
            image = self.image(kind)
            allowed = bool(g.get("enabled")) and bool(image) and self.allowed(kind)
            mine = [b for b in boxes if b.kind == kind and b.state not in ("terminated", "failed") and not b.id.startswith("pending-")]
            for box in mine:
                if box.version != str(image):
                    if box.state != "busy":
                        self._retire_box(box, "the image changed")
                        out["terminated"] += 1
                    continue
                if box.state != "ready":
                    continue
                idle = now - (box.last_used or now)
                limit = float(g.get("idle_sleep_seconds", 600)) if kind == "gym" else float(
                    self.settings.get("gate", {}).get("gate_box_idle_sleep_seconds", 300))
                if not allowed or (idle >= limit and not self.queued(kind)):
                    self._sleep(box)
                    out["slept"] += 1
            if not allowed:
                continue
            demand = self.queued(kind)
            if not demand and kind == "gym" and self.unavailable(kind) and now >= self.fork_after.get(kind, 0.0) \
                    and not [b for b in boxes if b.kind == kind and b.state == "starting"]:
                demand = 1  # the researchers idle while the Gym is unavailable: one probe fork after each backoff finds it back
            if not demand:
                continue
            with self._lock:  # asleep boxes count: their dispatchers wake them when a batch comes
                available = [b for b in self.boxes.values() if b.kind == kind and b.state in ("starting", "ready", "busy", "asleep")
                             and (b.id.startswith("pending-") or b.version == str(image))]
            per = max(1, int(g.get("batch_programs", 8)))
            if kind == "gym":
                cap = int(g.get("max_boxes", 8))
                target = min(cap, max(int(g.get("start_boxes", 4)), math.ceil(demand / per)))
            else:
                cap = target = 1
            with self._lock:  # every live box of the kind counts against the cap: the pool's and the store's
                live = {b.id for b in self.boxes.values() if b.kind == kind and b.state not in ("terminated", "failed")}
            live |= {r["id"] for r in self.store.boxes(kind=kind, live=True)}
            if target > len(available) and cap > len(live):
                # A lost POST's young stray is protected by reconciliation's grace period, but still occupies a slot.
                # Read the venue before creating capacity; an unreadable inventory never permits extra boxes.
                lister = getattr(self.client, "list_boxes", None)
                if lister is not None:
                    try:
                        listed = lister(limit=1000)
                    except Exception:  # noqa: BLE001
                        out["inventory_unreadable"] = True
                        continue
                    for row in listed:
                        name = str(row.get("name") or "")
                        if (name.startswith(self.name_prefix(kind)) or name.startswith(f"{NAME_PREFIX}{kind}-")) and \
                                str(row.get("status")) not in ("terminated", "terminating", "failed", "create_failed"):
                            live.add(str(row.get("sailbox_id") or row.get("id")))
            if now < self.fork_after.get(kind, 0.0):
                out["fork_backoff"] = round(self.fork_after[kind] - now)
                continue  # the last fork failed: wait (a bad image must not become a storm of paid boxes)
            for _ in range(max(0, min(target - len(available), cap - len(live)))):
                with self._lock:
                    self.fork_times = [t for t in self.fork_times if now - t < 3600]
                    if len(self.fork_times) >= int(g.get("max_forks_hour", 16)):
                        out["fork_cap"] = True
                        break
                    self.fork_times.append(now)  # counted now; `_start_box` adds nothing twice (see below)
                out["started"] += 1
                if self.threaded:
                    thread = threading.Thread(target=self._start_box, args=(kind,), name=f"fork-{kind}", daemon=True)
                    with self._lock:
                        self.fork_threads = [t for t in self.fork_threads if t.is_alive()] + [thread]
                    thread.start()
                else:
                    self._start_box(kind)
        out.update(self.status())
        return out

    def _sleep(self, box: Box) -> None:
        self._accrue(box)
        try:
            self.client.sleep(box.id)
            box.state = "asleep"
            self.store.set_box_state(box.id, "asleep")
        except Exception as exc:  # noqa: BLE001
            self.store.event("swarm.pool", None, {"action": "sleep_failed", "box": box.id, "error": str(exc)[:200]})

    def adopt(self) -> int:
        """After a restart: take back the boxes the store says are ours (asleep or awake), so a restart never forks a
        second pool; end a box of an old image, one that is no longer sealed, and every stray named like ours."""
        n = 0
        for row in self.store.boxes():
            if not self.sealed(row["id"]):
                try:
                    self.client.terminate(row["id"])
                except Exception:  # noqa: BLE001
                    pass
                self.store.set_box_state(row["id"], "terminated")
                self.store.event("swarm.pool", None, {"action": "unsealed", "box": row["id"], "kind": row["kind"]})
                continue
            kind = row["kind"]
            if row["version"] != str(self.image(kind)):
                try:
                    self.client.terminate(row["id"])
                except Exception:  # noqa: BLE001
                    pass
                self.store.set_box_state(row["id"], "terminated")
                continue
            box = Box(row["id"], kind, row["version"], "asleep" if row["state"] == "asleep" else "ready",
                      last_used=self.clock(), booked_at=self.clock())
            try:
                box.driver = self._driver(box.id)
                box.roots = tuple((row.get("detail") or {}).get("roots") or ())
            except Exception:  # noqa: BLE001
                continue
            with self._lock:
                self.boxes[box.id] = box
            self._spawn(box)
            n += 1
        self.reconcile()
        return n

    def scale_to_zero(self, why: str, *, busy: bool = False) -> int:
        """The guard's brake: every Gym and gate box to sleep now (a running batch finishes first). A stopping process
        passes `busy`: its running batches die with it, so their boxes sleep too."""
        n = 0
        with self._lock:
            boxes = [b for b in self.boxes.values() if b.state in (("ready", "starting", "busy") if busy else ("ready", "starting"))]
        for box in boxes:
            if not box.id.startswith("pending-"):
                self._sleep(box)
                n += 1
        if n:
            self.store.event("swarm.pool", None, {"action": "scaled_to_zero", "boxes": n, "why": why})
        return n

    def stop(self, *, join_seconds: float = 60.0) -> None:
        """Stop the dispatchers and wait (up to `join_seconds`) for forks in flight: a fork that lands after the stop
        sleeps its box, so the caller's `scale_to_zero` leaves nothing awake."""
        with self._wake:
            self._stopping = True
            self._wake.notify_all()
            forks = list(self.fork_threads)
        deadline = time.monotonic() + join_seconds
        for thread in forks:
            thread.join(max(0.0, deadline - time.monotonic()))

    def status(self) -> dict[str, Any]:
        with self._lock:
            states: dict[str, int] = {}
            for b in self.boxes.values():
                states[f"{b.kind}:{b.state}"] = states.get(f"{b.kind}:{b.state}", 0) + 1
            return {"boxes": states, "queue": len(self.queue), **{k: (round(v, 2) if isinstance(v, float) else v)
                                                                 for k, v in self.stats.items()}}


def cleanup_stopped(root: str | Path, client: Any, *, limit: int = 100) -> dict[str, Any]:
    """Bounded House-side cleanup after a stopped process, including forks whose POST returned after it died.

    Only this store's recorded IDs, pending names and exact pool token are owned. Keep unresolved names until a
    later inventory confirms termination; a submitted fork may not appear in Sail's list yet. The process lock
    prevents a replacement swarm from adopting a box while this function terminates it.
    """
    import fcntl

    from . import DB_NAME, LOCK_FILE

    root = Path(root)
    out: dict[str, Any] = {"active": False, "inspected": 0, "requested": 0, "confirmed": 0, "pending": 0, "errors": []}
    if not (root / DB_NAME).exists():
        return out
    with (root / LOCK_FILE).open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            out["active"] = True
            return out
        store = SwarmStore(root)
        try:
            token = str(store.get("pool_token") or "")
            pending = dict(store.get("forking") or {})
            known = {r["id"] for r in store.boxes(live=False)}
            def owned(row):
                return (str(row.get("sailbox_id") or row.get("id") or "") in known or row.get("name") in pending or
                        bool(token and str(row.get("name") or "").startswith(f"{NAME_PREFIX}{token}-")))
            try:
                rows = client.list_boxes(limit=1000)
            except Exception as exc:  # noqa: BLE001
                out["errors"].append(f"inventory: {type(exc).__name__}: {str(exc)[:160]}")
                out["pending"] = len(pending)
                return out
            terminal = ("terminated", "failed", "create_failed")
            for row in [r for r in rows if owned(r)][:max(0, int(limit))]:
                out["inspected"] += 1
                box_id = str(row.get("sailbox_id") or row.get("id") or "")
                if str(row.get("status")) in terminal or str(row.get("status")) == "terminating":
                    continue
                try:
                    client.terminate(box_id)
                    out["requested"] += 1
                except Exception as exc:  # noqa: BLE001
                    out["errors"].append(f"{box_id}: {type(exc).__name__}: {str(exc)[:160]}")
            try:
                confirmed = client.list_boxes(limit=1000) if out["requested"] else rows
            except Exception as exc:  # noqa: BLE001
                out["errors"].append(f"confirmation: {type(exc).__name__}: {str(exc)[:160]}")
                confirmed = []
            for row in confirmed:
                if owned(row) and str(row.get("status")) in terminal:
                    box_id = str(row.get("sailbox_id") or row.get("id") or "")
                    store.set_box_state(box_id, "terminated")
                    pending.pop(str(row.get("name") or ""), None)
                    out["confirmed"] += 1
            store.put("forking", pending)
            out["pending"] = len(pending)
            return out
        finally:
            store.close()


__all__ = ["GymPool", "GymJob", "PoolError", "Box", "cleanup_stopped"]
