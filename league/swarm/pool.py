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
- COST. Each batch books its box time at `box_usd_hour` as `gym_box` spend (an estimate: Sail bills boxes
  on measured use, about $0.12-0.20 an hour for a busy l box; Sail's meter is the record, and the guard
  reads the balance itself). Model inference is where the money goes, so boxes scale up without fear.

The Gym's driver (`league.gym.driver.GymDriver`) is imported when a box starts; tests hand in fakes.
Standard library only.
"""

from __future__ import annotations

import itertools
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .store import SwarmStore

_IDS = itertools.count(1)


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

    # ------------------------------------------------------------------ settings
    @property
    def gym(self) -> Mapping[str, Any]:
        return self.settings.get("gym", {})

    def image(self, kind: str) -> str | None:
        return self.gym.get("image_checkpoint") if kind == "gym" else self.gym.get("gate_checkpoint")

    # ------------------------------------------------------------------ jobs
    def submit(self, job: GymJob) -> GymJob:
        job.created = self.clock()
        with self._wake:
            self.queue.append(job)
            self._wake.notify_all()
        return job

    def wait(self, job: GymJob, timeout: float | None = None, *, late: Any = None) -> dict[str, Any]:
        """The job's result. On a timeout the job leaves the queue if it has not started (nothing ran); if it is
        running, `late(result)` records it when it lands (it is still a trial)."""
        if not job.done.wait(timeout):
            with self._lock:
                if job in self.queue:
                    self.queue.remove(job)
                    job.error = "abandoned before it ran"
                else:
                    job.late = late
            if job.done.is_set() and job.result is not None and late is not None and job.late is not None:
                job.late = None
                late(job.result)
            raise PoolError(f"the Gym did not answer within {timeout:.0f} s (queue {self.queued()})")
        if job.error:
            raise PoolError(job.error)
        return job.result  # type: ignore[return-value]

    def run(self, job: GymJob, timeout: float | None = None, *, late: Any = None) -> dict[str, Any]:
        return self.wait(self.submit(job), timeout, late=late)

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
        job.done.set()

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

    def _start_box(self, kind: str) -> None:
        """Fork one box from its image and make it ready (runs on its own thread)."""
        image = self.image(kind)
        n = next(self._counter)
        name = f"ltcm-{kind}-{int(self.clock())}-{n}"
        placeholder = f"pending-{kind}-{n}"
        with self._lock:
            self.boxes[placeholder] = Box(placeholder, kind, str(image), "starting")
        try:
            row = self.client.from_checkpoint(image, name=name)
            box_id = str(row.get("sailbox_id"))
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.boxes.pop(placeholder, None)
            self._failed_fork(kind)
            self.store.event("swarm.pool", None, {"action": "fork_failed", "kind": kind, "image": image, "error": str(exc)[:300]})
            return
        box = Box(box_id, kind, str(image), "starting", last_used=self.clock(), booked_at=self.clock())
        with self._lock:
            self.boxes.pop(placeholder, None)
            self.boxes[box_id] = box
        self.store.upsert_box(box_id, kind=kind, version=str(image), state="starting", detail={"name": name})
        try:
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
            box.state = "failed"
            self._failed_fork(kind)
            self.store.set_box_state(box_id, "failed")
            self.store.event("swarm.pool", None, {"action": "box_failed", "box": box_id, "kind": kind, "error": str(exc)[:400]})
            try:
                self.client.terminate(box_id)
            except Exception:  # noqa: BLE001
                pass
            return
        with self._wake:
            box.state = "ready"
            self.fork_failures[kind] = 0
            self._wake.notify_all()
        self.store.upsert_box(box_id, kind=kind, version=str(image), state="ready", detail={"name": name, "roots": list(box.roots),
                                                                                           "bundle": getattr(box.driver, "version", None)})
        self.store.event("swarm.pool", None, {"action": "box_ready", "box": box_id, "kind": kind, "roots": list(box.roots)})
        self._spawn(box)

    def _failed_fork(self, kind: str) -> None:
        """Back off after a fork that failed or a box that never became ready: 60 s, doubling to 30 minutes."""
        with self._lock:
            self.fork_failures[kind] = self.fork_failures.get(kind, 0) + 1
            self.fork_after[kind] = self.clock() + min(1800.0, 60.0 * 2 ** (self.fork_failures[kind] - 1))

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
            try:
                self.client.resume(box.id)
            except Exception as exc:  # noqa: BLE001
                self._requeue(batch, f"resuming {box.id} failed: {exc}")
                box.state = "failed"
                return
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
            self._book(box, elapsed, len(batch))
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
        self._book(box, elapsed, len(batch))
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

    def _book(self, box: Box, seconds: float, jobs: int) -> None:
        """A batch's box time as `gym_box` spend at `box_usd_hour` (Sail bills measured use: a busy l box is
        about $0.12-0.20 an hour, measured Sept 26; an idle or sleeping one close to nothing)."""
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
            boxes = list(self.boxes.values())
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
            if not demand:
                continue
            with self._lock:  # asleep boxes count: their dispatchers wake them when a batch comes
                available = [b for b in self.boxes.values() if b.kind == kind and b.state in ("starting", "ready", "busy", "asleep")
                             and (b.id.startswith("pending-") or b.version == str(image))]
            per = max(1, int(g.get("batch_programs", 8)))
            if kind == "gym":
                target = min(int(g.get("max_boxes", 8)), max(int(g.get("start_boxes", 4)), math.ceil(demand / per)))
            else:
                target = 1
            if now < self.fork_after.get(kind, 0.0):
                out["fork_backoff"] = round(self.fork_after[kind] - now)
                continue  # the last fork failed: wait (a bad image must not become a storm of paid boxes)
            for _ in range(max(0, target - len(available))):
                out["started"] += 1
                if self.threaded:
                    threading.Thread(target=self._start_box, args=(kind,), name=f"fork-{kind}", daemon=True).start()
                else:
                    self._start_box(kind)
        out.update(self.status())
        return out

    def _sleep(self, box: Box) -> None:
        try:
            self.client.sleep(box.id)
            box.state = "asleep"
            self.store.set_box_state(box.id, "asleep")
        except Exception as exc:  # noqa: BLE001
            self.store.event("swarm.pool", None, {"action": "sleep_failed", "box": box.id, "error": str(exc)[:200]})

    def adopt(self) -> int:
        """After a restart: take back the boxes the store says are ours (asleep or awake), so a restart never
        forks a second pool. A box of an old image is terminated."""
        n = 0
        for row in self.store.boxes():
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
        return n

    def scale_to_zero(self, why: str) -> int:
        """The guard's brake: every Gym and gate box to sleep now (a running batch finishes first)."""
        n = 0
        with self._lock:
            boxes = [b for b in self.boxes.values() if b.state in ("ready", "starting")]
        for box in boxes:
            if not box.id.startswith("pending-"):
                self._sleep(box)
                n += 1
        if n:
            self.store.event("swarm.pool", None, {"action": "scaled_to_zero", "boxes": n, "why": why})
        return n

    def stop(self) -> None:
        with self._wake:
            self._stopping = True
            self._wake.notify_all()

    def status(self) -> dict[str, Any]:
        with self._lock:
            states: dict[str, int] = {}
            for b in self.boxes.values():
                states[f"{b.kind}:{b.state}"] = states.get(f"{b.kind}:{b.state}", 0) + 1
            return {"boxes": states, "queue": len(self.queue), **{k: (round(v, 2) if isinstance(v, float) else v)
                                                                 for k, v in self.stats.items()}}


__all__ = ["GymPool", "GymJob", "PoolError", "Box"]
