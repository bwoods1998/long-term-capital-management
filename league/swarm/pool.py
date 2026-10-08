"""The Gym pool: sealed size-l boxes forked from the Gym image, driven in batches, asleep when idle.

- BOXES. A Gym box is a fork of the Gym image checkpoint (`gym.image_checkpoint`; W1 records it in
  `.data/gym/images.json`), sealed (`no_network`, kept from the image), size l. The pool starts `start_boxes` (4 by
  default) when there is work, grows to `max_boxes` (8 by default) while the queue is long and the guard allows, puts a
  box to sleep after `idle_sleep_seconds` without work (a sleeping box costs nothing), and terminates a box whose image
  is no longer the configured one (a version change). Gate boxes are forks of the GATE image (holdout and forward days),
  one at a time, used only by the gate and the nightly forward replays; a Gym box never opens a sealed window (the Gym's
  own capability check).
- BATCHES. Jobs (one program version, one window) queue here; a box's dispatcher takes up to
  `batch_programs` jobs with the same settings and runs them together, day-major (the Gym's
  `driver.run`: each day's chain is loaded once for the whole batch). The highest priority first (the
  family's allocation share), then the oldest; a short batch waits `batch_wait_seconds` for company. A researcher's sweep
  (`gym_sweep`) queues its variants at once as one `group`, so they ride the same batches and never supersede one another.
- ROBUSTNESS runs (a new best version re-run on Train at 1.5x the half-spread and at the mid, Sept 26) have the lowest
  priority (`ROBUSTNESS_PRIORITY`): a box takes them only when nothing else waits AND another Gym box is free (ready or
  asleep), so they fill idle boxes and never delay a researcher's run or a validation. They never start, grow or keep
  awake a box (`manage` counts only other work), and a family's queued runs of a version that is no longer its best
  are superseded. So a busy queue cannot starve them (validation waits on the 1.5x run), one waiting past
  `pool.robust_age_seconds` (600; the mid run twice that) takes a Train job's priority and any free box. THE INCUBATOR'S
  RE-RUNS (`GymJob.incubator`, Oct 8, 2026; `incubator.reruns`) run at this priority too, for a version an active
  practice cohort holds that is not its family's best: a newer best's robustness runs never supersede them, and they
  supersede nothing.
- FAILURES. A root the box's store lacks fails its job at once with the Gym's own words; a batch that
  errs or times out is retried once on another box, then its jobs fail. A failure never kills the pool. A job that
  failed for MISSING DATA carries the roots it lacked (`GymJob.missing`): the box's own list lacks them, or the Gym's
  exit-3 answer NAMES them ("no holdout days for GOOGL, MSFT in ..."). The gate counts no try for it (`gate.py`, the owed
  look). An exit-3 answer that names no root (no store, a missing package) is not missing data: its jobs fail as before.
- THE GATE'S HOLDOUT COVERAGE (Oct 1, 2026). A gate box lists, when it starts, which roots its store holds holdout days
  for: FILE NAMES only (`nbbo/<ROOT>/<day>.parquet` and `underlying/...` dated in the holdout; no file is opened and the
  gate's capability is never minted). The roots with the image's full count of both (the count most roots have) are
  `Box.holdout`; a holdout job needing another root fails at once as missing data. A store with no holdout at all fails
  the box, records the image as holding none, and fails the holdout looks waiting for it as missing data. The coverage
  is kept per gate image (kv `gate_coverage`, with the roots a Gym exit-3 answer named since), and the gate reads it
  (`holdout_coverage`) to refuse a look up front. A gate image that lacks any of `gym.roots` raises one `swarm.status`
  alert. Sept 30: every gate box had advertised every root of `gym.roots` without looking, and three looks failed on a
  five-root holdout.
- COST. Every awake second of a box (starting, ready and idle, busy, resuming) is booked at `box_usd_hour`
  as `gym_box` spend, at least every `book_seconds` and whenever it sleeps or ends (an estimate: Sail bills
  boxes on measured use, about $0.12-0.20 an hour for a busy l box; Sail's meter is the record, and the
  guard reads the balance itself). A sleeping box books nothing.
- NAMES. Every box is `ltcm-swarm-<token>-<kind>-<epoch>-<n>`; the token is the store's own (kv
  `pool_token`), so a pool sweeps (`reconcile`) only its own strays, never another state root's (a laptop
  trial's) boxes, and never one forked in the last `reconcile_grace_seconds`. Stage 1 (Sept 26, 10:22Z) named
  its boxes `ltcm-swarm-<kind>-<epoch>-<n>` without a token: `adopt` takes back every box the store knows
  whatever its name, and `reconcile` also ends an untokened one it does not know (`LEGACY_NAME`).
- ROWS (Oct 2, 2026). A box that failed is `failed` in the store until Sail accepts its terminate call, then
  `terminated`. `reconcile` settles the rest against Sail's list: a `failed` row, or a live row the pool does not hold
  after `adopt` (one adopt could not take back), becomes `terminated` when Sail lists the box as gone or no longer
  lists it, and a box Sail still runs is ended first (`_settle_rows`).
- CAP. `max_boxes` counts every live box of the kind the pool holds, the store records, or Sail lists.
- TRAIN'S FIRST DAY (the 2020-21 switch, Sept 27, 2026). Every Train job without its own `start` starts at the running
  swarm's span: its store's migrated objective (`settings.objective_span`; 2022-01-03 until a start migrates the switch
  on), stamped when it is queued (`start`, `span`). A box learns its image's first Train day when it starts (the Gym's
  `train_first`), and a Train batch whose image does not start Train at the job's span is refused, both ways: a
  2022-2024 image under a 2020-2024 swarm would score three years as five, and a 2020 image under a 2022 swarm would
  give January 2022 a history the old image never had. A result carries the span its image covered as `train_from`,
  which a batch reports; the Train split and time limit follow the span unless the operator sets them
  (`settings.train_split`, `settings.run_timeout`).
- THE GAME'S PRIVATE JOBS (the learning game, Oct 8, 2026; league/swarm/game.py). `submit` is the one door every Train
  job passes, so it holds the hidden years: a Train job that starts in a calendar year before the running span's first
  year fails there at once (by year: the zero-trade probe starts on January 1 of a span year), unless its purpose is
  "private", the game's own hidden run, which is never stamped, has no span check, and must start and end before the
  span. With `gym.allow_earlier_image` true a job stamped with the span runs on an image whose Train starts EARLIER (the
  2020 image under the 2022 span: the job's own start cuts the window, and the result's `train_from` is the job's
  start); an image that starts later than the span is refused as ever. Without it, today's refusal both ways.

The Gym's driver (`league.gym.driver.GymDriver`) is imported when a box starts; tests hand in fakes.
Standard library only.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import re
import secrets
import shlex
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import settings as settings_mod
from .store import SwarmStore

_IDS = itertools.count(1)
#: Below every other job's (a researcher's run carries its family's share, 0 to 1; validation 1; the gate 5 and 10).
ROBUSTNESS_PRIORITY = -1.0
#: The name of every box the pool forks begins with this (and no other box on the account's does).
NAME_PREFIX = "ltcm-swarm-"
#: The holdout's first and last day (league/gym/day.py's WINDOWS; a test holds them equal). The pool is standard library
#: only, so they are repeated here.
HOLDOUT_FIRST, HOLDOUT_LAST = "2026-01-02", "2026-09-25"
#: Gate images whose coverage is kept (kv `gate_coverage`), the newest.
COVERAGE_KEPT = 6
#: Run on a gate box at its start (THE GATE'S HOLDOUT COVERAGE): per root, how many holdout-dated nbbo and underlying file
#: NAMES its store holds. It opens no file and mints no gate capability.
HOLDOUT_LISTING = r"""
import json, os, sys
store, first, last = sys.argv[1:4]
out = {}
for kind in ("nbbo", "underlying"):
    base = os.path.join(store, kind)
    for root in (sorted(os.listdir(base)) if os.path.isdir(base) else []):
        folder = os.path.join(base, root)
        names = os.listdir(folder) if os.path.isdir(folder) else []
        out.setdefault(root, {})[kind] = sum(1 for n in names if n.endswith(".parquet") and first <= n[:10] <= last)
print(json.dumps(out, sort_keys=True))
"""
_MISSING_ROOTS = re.compile(r"no \w+ days for ([A-Z0-9., ]+?) in ")


def named_missing(text: str) -> tuple[str, ...]:
    """The roots a Gym "missing data" answer names ("no holdout days for GOOGL, MSFT in /data/store"); () when it names
    none (a store-level fault: no store, no calendar, a missing package), which is not the image lacking a root."""
    found = _MISSING_ROOTS.search(str(text))
    return tuple(sorted({r.strip().upper() for r in found.group(1).split(",") if r.strip()})) if found else ()


class HoldoutMissing(RuntimeError):
    """A gate box's listing ran and found no root with holdout days: the image's data, not a fault of the box."""


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
    #: The jobs of one researcher sweep (`gym_sweep`) share a group: they never supersede one another.
    group: str | None = None
    #: Train's first day this job was stamped with (the running swarm's span; None: a job with its own `start`).
    span: str | None = None
    #: The roots a MISSING DATA failure named (the box lacks them, or the Gym's own words); None for any other failure.
    missing: tuple[str, ...] | None = None
    #: THE INCUBATOR'S RE-RUNS (Oct 8, 2026; `incubator.reruns`): a robustness-priority job for a version an active
    #: practice cohort holds, which need not be its family's best. A newer best's robustness runs never supersede it (the
    #: best moves on while the cohort practises), and its own submission supersedes no other job.
    incubator: bool = False

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
    train_first: str | None = None    # its image's first Train day (the Gym's data check says; None: not known)
    holdout: tuple[str, ...] | None = None  # a gate box's roots with holdout days (its listing; None: not listed)


AWAKE = ("starting", "ready", "busy")
#: Sail statuses of a box that is gone or going (it bills nothing more).
GONE = ("terminated", "terminating", "failed", "create_failed")
#: The most boxes one read of Sail's list asks for; a list this long may be cut short.
LIST_LIMIT = 1000
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
        self._span_alerts: set[tuple[Any, ...]] = set()
        #: True once `adopt` has taken back the store's boxes: only then is a live row this pool does not hold stale.
        self._adopted = False
        self.token = str(store.get("pool_token") or "")
        if not self.token:
            self.token = secrets.token_hex(3)
            store.put("pool_token", self.token)

    # ------------------------------------------------------------------ settings
    @property
    def gym(self) -> Mapping[str, Any]:
        return self.settings.get("gym", {})

    def span(self) -> dt.date:
        """The running swarm's Train span: its store's migrated objective (`settings.objective_span`), not the setting,
        which takes effect at the next start's migration."""
        return settings_mod.objective_span(self.store.get("train_objective"))

    def _span_refused(self, box: Box, span: str, found: str, jobs: Sequence[GymJob]) -> None:
        why = (f"the Gym image starts Train at {found} but the swarm scores Train from {span}: adopt the image built for that "
               "span (gym.image_checkpoint) and restart, or set gym.train_from back")
        key = (box.version, span, found)
        if key not in self._span_alerts:
            self._span_alerts.add(key)
            self.store.event("swarm.status", None, {"action": "train_span_mismatch", "box": box.id, "image": box.version,
                                                    "image_train_first": found, "span": span, "alert": True, "text": why})
        for job in jobs:
            self._fail(job, why)

    def _earlier_ok(self, first: str, span: str) -> bool:
        """An image whose Train starts at `first` may run a job stamped with `span`: only one that starts EARLIER, and only
        with `gym.allow_earlier_image` true (JSON true: THE GAME'S PRIVATE JOBS in the module docstring)."""
        return self.gym.get("allow_earlier_image") is True and str(first) < str(span)

    def image(self, kind: str) -> str | None:
        return self.gym.get("image_checkpoint") if kind == "gym" else self.gym.get("gate_checkpoint")

    def bundle(self) -> str | None:
        """The engine code shipped by this process; a checkpoint alone identifies only its saved data."""
        if self.driver_factory is not None:
            return next((getattr(b.driver, "version", None) for b in self.boxes.values() if b.driver is not None), None)
        if not hasattr(self, "_bundle_version"):
            from ..gym.driver import build_bundle
            self._bundle_version = build_bundle()[1]
        return self._bundle_version

    # ------------------------------------------------------------------ jobs
    def submit(self, job: GymJob) -> GymJob:
        """Queue a job. A family has at most one Train job (or one sweep's jobs: the same `group`) waiting: a newer one
        supersedes it (its waiter, if any, is told; it never ran), so a backlog of orphaned versions cannot build up."""
        job.created = self.clock()
        refused = None
        if job.window == "train" and not job.gate:
            # THE GAME'S PRIVATE JOBS (the module docstring): the hidden years are reached by a private job alone.
            span = self.span().isoformat()
            if job.purpose == "private":
                if not job.start or not job.end or not str(job.start) <= str(job.end) < span:
                    refused = "a private Train job runs only on days before the swarm's Train span"
            elif job.start is None:
                job.start = job.span = span
            elif str(job.start)[:4].isdigit() and int(str(job.start)[:4]) < int(span[:4]):
                refused = f"a Train job may not start before the swarm's Train span ({span[:4]})"
        with self._wake, self.store.atomic():
            if refused:
                self._fail(job, refused)
                return job
            if (self.store.family(job.family) or {}).get("retired_at"):
                self._fail(job, "the family retired before dispatch")
                return job
            if job.purpose == "train" and not job.gate:
                for old in [j for j in self.queue if j.family == job.family and j.purpose == "train" and not j.gate
                            and (job.group is None or j.group != job.group)]:
                    self.queue.remove(old)
                    self._fail(old, "superseded by a newer version before it ran")
            if job.purpose == "robustness" and not job.incubator:
                fam = self.store.family(job.family) or {}
                current = {job.version, fam.get("best_version"), (fam.get("state") or {}).get("best_train_version")}
                for old in [j for j in self.queue if j.family == job.family and j.purpose == "robustness" and j.version not in current
                            and not j.incubator]:
                    self.queue.remove(old)
                    self._fail(old, "superseded by a newer best before it ran")
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

    def queued(self, kind: str | None = None, *, robustness: bool = True) -> int:
        """Jobs waiting (of `kind`); `robustness=False` leaves out the robustness runs (they never drive the boxes)."""
        with self._lock:
            return sum(1 for j in self.queue if (kind is None or (kind == "gate") == bool(j.gate))
                       and (robustness or j.purpose != "robustness"))

    def cancel_family(self, family: str) -> None:
        with self._lock:
            for job in [j for j in self.queue if j.family == family]:
                self.queue.remove(job)
                self._fail(job, "the family retired")

    def _fail(self, job: GymJob, why: str, *, missing: Sequence[str] | None = None) -> None:
        job.error = why
        if missing:
            job.missing = tuple(sorted({str(r).upper() for r in missing}))
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
        # Retirement commits before cancel_family takes the pool lock. Serialize the final queue handoff with
        # that commit too; after this handoff work is in flight and its result must still count. No network here.
        with self._lock, self.store.atomic():
            for job in list(self.queue):
                if (self.store.family(job.family) or {}).get("retired_at"):
                    self.queue.remove(job)
                    self._fail(job, "the family retired before dispatch")
            return self._take_active(box)

    def _take_active(self, box: Box) -> list[GymJob]:
        gate = box.kind == "gate"
        mine = [j for j in self.queue if bool(j.gate) == gate]
        if not mine:
            return []
        # AGING: a robustness run waiting past `pool.robust_age_seconds` (the 1.5x run and the drift run at the normal spread,
        # which validation waits on; the mid run at twice that) takes a Train job's priority, the top one waiting, so it has
        # its turn by age on any free box.
        now = self.clock()
        age = float(self.settings.get("pool", {}).get("robust_age_seconds", 600))
        train = max([j.priority for j in mine if j.purpose == "train"] + [0.0])

        def aged(j: GymJob) -> bool:
            return j.purpose == "robustness" and now - j.created >= age * (1.0 if float(j.stress) in (1.5, 1.0) else 2.0)

        mine.sort(key=lambda j: (-(train if aged(j) else j.priority), j.created, j.id))
        head = mine[0]
        if head.purpose == "robustness" and not aged(head) and not any(
                b is not box and b.kind == box.kind and b.state in ("ready", "asleep") for b in self.boxes.values()):
            return []  # the last free box stays free for the inner loop
        # A robustness run never rides in a researcher's batch (a longer batch would delay the researcher's result).
        same = [j for j in mine if j.key() == head.key() and (j.purpose == "robustness") == (head.purpose == "robustness")]
        same = same[: max(1, int(self.gym.get("batch_programs", 8)))]
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
            box.train_first = report.get("train_first") if kind == "gym" and isinstance(report, Mapping) else None
            if kind == "gate":
                box.holdout = self._holdout_listing(box_id)  # THE GATE'S HOLDOUT COVERAGE: by file name, before any look
        except Exception as exc:  # noqa: BLE001
            self._accrue(box)
            box.state = "failed"
            self._failed_fork(kind, str(exc)[:200])
            self.store.set_box_state(box_id, "failed")
            self.store.event("swarm.pool", None, {"action": "box_failed", "box": box_id, "kind": kind, "error": str(exc)[:400]})
            self._end_failed(box_id)
            with self._lock:
                self.boxes.pop(box_id, None)
            if isinstance(exc, HoldoutMissing):
                self._no_holdout(str(image), box_id, str(exc))
            return
        self._accrue(box)
        with self._wake:
            box.state = "ready"
            box.last_used = self.clock()
            self.fork_failures[kind] = 0
            self._wake.notify_all()
        self.store.upsert_box(box_id, kind=kind, version=str(image), state="ready", detail={"name": name, "roots": list(box.roots),
                                                                                           "bundle": getattr(box.driver, "version", None),
                                                                                           "train_first": box.train_first,
                                                                                           "holdout_roots": None if box.holdout is None
                                                                                           else list(box.holdout)})
        self.store.event("swarm.pool", None, {"action": "box_ready", "box": box_id, "kind": kind, "roots": list(box.roots),
                                              **({} if box.holdout is None else {"holdout_roots": list(box.holdout)})})
        if box.holdout is not None:
            try:
                self._note_coverage(str(image), roots=box.holdout, box=box_id)
            except Exception:  # noqa: BLE001 - the record is the gate's early refusal; the box's own check still holds
                pass
        if self._stopping:  # the pool stopped while this fork was in flight: it sleeps (the next process adopts it)
            self._sleep(box)
            return
        self._spawn(box)

    def _holdout_listing(self, box_id: str) -> tuple[str, ...] | None:
        """THE GATE'S HOLDOUT COVERAGE: the roots a gate box's store holds the whole holdout for, by FILE NAME (nbbo and
        underlying files dated in the holdout; `HOLDOUT_LISTING` opens none). A root counts when it has the image's full
        count of both: the count most roots have (the larger on a tie), so a root copied in part is not taken for whole.
        None when the client cannot run a command (test clients only); an error, so the box is not used, when the
        listing fails twice, and `HoldoutMissing` when it finds no root at all."""
        run = getattr(self.client, "exec", None)
        if run is None:
            return None
        command = " ".join(shlex.quote(part) for part in (str(self.gym.get("python", "python3")), "-c", HOLDOUT_LISTING,
                                                          str(self.gym.get("store_root", "/data/store")),
                                                          HOLDOUT_FIRST, HOLDOUT_LAST))
        last: Exception | None = None
        for _ in range(2):
            try:
                result = run(box_id, command, timeout=300)
                if getattr(result, "return_code", None) != 0:
                    raise RuntimeError(f"exit {getattr(result, 'return_code', None)}: "
                                       f"{str(getattr(result, 'stderr', '') or '')[-300:]}")
                rows = json.loads(str(result.stdout).strip().splitlines()[-1])
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
        else:
            raise RuntimeError(f"the gate box's holdout listing failed: {str(last)[:300]}")
        held: dict[str, int] = {}
        for root, row in (rows or {}).items():
            if isinstance(row, Mapping):
                try:
                    days = min(int(row.get("nbbo") or 0), int(row.get("underlying") or 0))
                except (TypeError, ValueError):
                    continue
                if days > 0:
                    held[str(root).upper()] = days
        if not held:
            raise HoldoutMissing("the gate image holds no holdout days for any root")
        counts = sorted(held.values())
        full = max(counts, key=lambda n: (counts.count(n), n))
        return tuple(sorted(r for r, days in held.items() if days >= full))

    def _no_holdout(self, image: str, box_id: str, why: str) -> None:
        """A gate box of `image` found no holdout at all (`HoldoutMissing`): the image is recorded as holding none, so the
        gate refuses every look up front, and the holdout looks queued for this image fail now as missing data (no try)
        rather than wait to be abandoned."""
        try:
            self._note_coverage(image, roots=(), box=box_id)
        except Exception:  # noqa: BLE001 - the box's own failure still stands
            pass
        with self._lock:
            if image != str(self.image("gate") or ""):
                return
            waiting = [j for j in self.queue if j.gate and j.window == "holdout"]
            for job in waiting:
                self.queue.remove(job)
        for job in waiting:
            self._fail(job, f"the Gym has no holdout data for {', '.join(job.roots)} ({why})", missing=job.roots)

    def holdout_coverage(self, image: str | None = None) -> dict[str, Any] | None:
        """What the pool knows of a gate image's holdout (by default the configured one): {"roots": the roots a gate box's
        listing found (None: not listed yet), "missing": the roots a Gym "missing data" answer named since}; None when
        nothing is known (no gate box of it has started or failed a look)."""
        image = str(image or self.image("gate") or "")
        record = (self.store.get("gate_coverage") or {}).get(image) if image else None
        return dict(record) if isinstance(record, Mapping) else None

    def _note_coverage(self, image: str, *, roots: Sequence[str] | None = None, missing: Sequence[str] = (),
                       box: str | None = None) -> dict[str, Any]:
        """Keep what a gate box found (`roots`, its listing) or a holdout batch was told (`missing`) about `image`, and
        raise one `swarm.status` alert per image while it lacks a root of `gym.roots`."""
        with self.store.atomic():
            kept = {k: v for k, v in dict(self.store.get("gate_coverage") or {}).items() if isinstance(v, Mapping)}
            record = dict(kept.get(image) or {})
            if roots is not None:
                record.update(roots=sorted({str(r).upper() for r in roots}), box=box, listed_at=self.clock())
            if missing:
                record["missing"] = sorted(set(record.get("missing") or ()) | {str(r).upper() for r in missing})
            record["at"] = self.clock()
            wanted = {str(r).upper() for r in self.gym.get("roots", [])}
            lacking = sorted((wanted - set(record["roots"]) if record.get("roots") is not None else set())
                             | (wanted & set(record.get("missing") or ())))
            alert = bool(lacking) and record.get("alerted") != lacking
            if alert:
                record["alerted"] = lacking
            kept[image] = record
            for old in sorted(kept, key=lambda k: float(kept[k].get("at") or 0))[:-COVERAGE_KEPT]:
                kept.pop(old, None)
            self.store.put("gate_coverage", kept)
        if alert:
            self.store.event("swarm.status", None, {
                "action": "gate_coverage", "alert": True, "image": image, "missing": lacking, "box": box,
                "text": (f"the gate image {image} holds no holdout for {', '.join(lacking)} (gym.roots): the gate refuses "
                         "those looks up front, with no try counted, until gym.gate_checkpoint names an image that holds "
                         "them")})
        return record

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

    def _end_failed(self, box_id: str) -> None:
        """End a box that failed (its row is already `failed`): the row becomes `terminated` once Sail accepts the
        terminate call. A call that fails leaves the row `failed`, and `reconcile` settles it against Sail's list."""
        try:
            self.client.terminate(box_id)
        except Exception:  # noqa: BLE001
            return
        self.store.set_box_state(box_id, "terminated")

    def reconcile(self) -> int:
        """End every box on the account named like ours (`ltcm-swarm-`) that this pool does not know: a fork whose
        answer was lost, or one a process that died left behind; and settle the store's own rows against Sail's list
        (THE ROWS, `_settle_rows`). Returns how many boxes were ended."""
        lister = getattr(self.client, "list_boxes", None)
        if lister is None:
            return 0
        try:
            rows = lister(limit=LIST_LIMIT)
        except Exception:  # noqa: BLE001
            return 0
        with self._lock:
            known = set(self.boxes) | {r["id"] for r in self.store.boxes(live=True)}
            in_flight = set(self.forking)
        mine = f"{NAME_PREFIX}{self.token}-"
        grace = float(self.gym.get("reconcile_grace_seconds", 300))
        try:
            n = self._settle_rows(rows, grace=grace)
        except Exception:  # noqa: BLE001 - the rows wait for the next pass; the stray sweep still runs
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

    def _settle_rows(self, listed: Sequence[Mapping[str, Any]], *, grace: float) -> int:
        """THE ROWS (Oct 2, 2026: six `failed` rows sat in the pool table for days, their boxes long gone). Each `failed`
        row, and each STALE row (a live state the store records for a box this pool does not hold after `adopt`, older
        than `grace`: one adopt could not take back), is read against Sail's list: a box Sail lists as terminal or no
        longer lists becomes `terminated`; a box Sail still runs is ended, and its row becomes `terminated` once Sail
        accepts the call. A list that may be cut short (`LIST_LIMIT` rows) proves nothing absent. Returns how many boxes
        were ended."""
        by_id = {str(r.get("sailbox_id") or r.get("id") or ""): r for r in listed}
        complete = len(listed) < LIST_LIMIT
        now = self.clock()
        with self._lock:
            held = set(self.boxes)
            in_flight = set(self.forking)
            adopted = self._adopted
        ended = 0
        for row in self.store.boxes(live=False):
            state = str(row.get("state"))
            if state == "terminated":
                continue
            if state != "failed":
                name = (row.get("detail") or {}).get("name")
                if not adopted or row["id"] in held or name in in_flight:
                    continue
                born = forked_at({"created_at": row.get("created_at")})
                if born is None or now - born < grace:
                    continue
            listing = by_id.get(str(row["id"]))
            if listing is None and not complete:
                continue
            status = None if listing is None else str(listing.get("status"))
            if listing is None or status in GONE:
                self.store.set_box_state(row["id"], "terminated")
                self.store.event("swarm.pool", None, {"action": "row_settled", "box": row["id"], "kind": row.get("kind"),
                                                      "was": state, "sail": status or "absent"})
                continue
            try:
                self.client.terminate(row["id"])
            except Exception:  # noqa: BLE001 - the row stays as it is: the next pass tries again
                continue
            ended += 1
            self.store.set_box_state(row["id"], "terminated")
            self.store.event("swarm.pool", None, {"action": "row_box_ended", "box": row["id"], "kind": row.get("kind"),
                                                  "was": state, "sail": status})
        return ended

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
            held = box.holdout if box.kind == "gate" and job.window == "holdout" and box.holdout is not None else box.roots
            lacking = [r for r in job.roots if held and str(r).upper() not in held]
            (missing if lacking else runnable).append((job, lacking))
        for job, lacking in missing:
            held = box.holdout if box.kind == "gate" and job.window == "holdout" and box.holdout is not None else box.roots
            self._fail(job, f"the Gym has no {job.window} data for {', '.join(lacking)} yet (it holds {', '.join(held)})",
                       missing=lacking)
        batch = [job for job, _ in runnable]
        if not batch:
            return
        span = batch[0].span if batch[0].window == "train" else None
        if span and box.train_first and box.train_first != span and not self._earlier_ok(box.train_first, span):
            self._span_refused(box, span, box.train_first, batch)  # nothing runs: the image covers another Train span
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
                self._end_failed(box.id)
                return
            box.booked_at = resuming  # the resume is awake time
        box.state = "busy"
        self.store.set_box_state(box.id, "busy")
        head = batch[0]
        roots = sorted({r for j in batch for r in j.roots})
        # Only Train is split (a boundary values open positions at the mid): every other window runs whole. The split and
        # the time limit follow Train's span unless the operator set them.
        span_day = dt.date.fromisoformat(head.start) if head.window == "train" and head.start else None
        split = head.split or (settings_mod.train_split(self.settings, span_day) if head.window == "train"
                               else int(self.gym.get("validation_split", 1)))
        programs = {job.name: (job.code, dict(job.params or {})) for job in batch}
        began = self.clock()
        try:
            doc = box.driver.run(programs, window=head.window, roots=roots, workers=int(self.gym.get("workers", 8)), split=split,
                                 stress=float(head.stress), capital=float(self.gym.get("capital", 10000.0)), detail=head.detail,
                                 start=head.start, end=head.end, gate_reason=head.gate,
                                 timeout=int(settings_mod.run_timeout(self.settings, span_day)))
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
                named = named_missing(str(exc))  # () when it names no root: a store fault, failed (and counted) as before
                if named and box.kind == "gate" and head.window == "holdout":
                    try:  # the gate refuses these roots' looks up front from now on, on this image
                        self._note_coverage(box.version, missing=named, box=box.id)
                    except Exception:  # noqa: BLE001
                        pass
                for job in batch:
                    self._fail(job, f"the Gym is missing data: {str(exc)[:300]}",
                               missing=(tuple(r for r in named if r in {str(x).upper() for x in job.roots}) or named) or None)
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
        covered = info.get("train_first") if head.window == "train" else None
        if covered and not box.train_first:
            box.train_first = str(covered)
        if span and covered and str(covered) != span and not self._earlier_ok(str(covered), span):
            self._span_refused(box, span, str(covered), batch)  # ran, but over another span: never delivered as this one
            return
        years = 0.0
        for job in batch:
            result = by_name.get(job.name)
            if result is None:
                self._fail(job, "the batch returned no result for this program")
                continue
            result = {**result, "gym_image": box.version, "gym_bundle": getattr(box.driver, "version", None)}
            if job.window == "train":
                # The span the Train score is over: the job's own start (a job stamped with the swarm's span gets here only
                # on an image that covers it from that day, or from earlier with `gym.allow_earlier_image`, where the
                # job's start cut the window), else the image's first Train day the batch reported.
                result["train_from"] = job.start or (str(covered) if covered else None)
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
                if not allowed or (idle >= limit and not self.queued(kind, robustness=False)):
                    self._sleep(box)
                    out["slept"] += 1
            if not allowed:
                continue
            demand = self.queued(kind, robustness=False)  # robustness runs fill the boxes other work keeps; they start none
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
                        listed = lister(limit=LIST_LIMIT)
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
                box.train_first = (row.get("detail") or {}).get("train_first")
                listed = (row.get("detail") or {}).get("holdout_roots")
                box.holdout = tuple(listed) if kind == "gate" and isinstance(listed, list) and listed else None
            except Exception:  # noqa: BLE001
                continue
            with self._lock:
                self.boxes[box.id] = box
            self._spawn(box)
            n += 1
        with self._lock:
            self._adopted = True
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


__all__ = ["GymPool", "GymJob", "PoolError", "Box", "cleanup_stopped", "ROBUSTNESS_PRIORITY"]
