"""The trusted options House: keep the live path, swarm, records and operator checks running.

The swarm owns programs, family budgets, evidence and promotion. `league.live` owns market reads,
shadow/paper/real books, orders and exits. The House does not interpret a strategy or allocate
capital: it supervises those proven components and keeps their ledger and health available.
"""
from __future__ import annotations
import json
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping
from .constitution import digest as constitution_digest
from .data import market_open_at
from .ledger import Ledger, now_iso
from .watchdog import environment

REPEAT_WARNINGS = 10
REPEAT_WINDOW_SECONDS = 1800.0
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_NUMBERED = re.compile(r"[\w.:/@+\-]*\d[\w.:/@+\-]*")

@dataclass
class Settings:
    tick_seconds: float = 30.0
    publish_seconds: float = 60.0
    real_money: bool = False
    ops_workers: int = 3

def alert_key(text: Any) -> str:
    """What makes two warnings the same text: ids and numbers folded, so "failed 3 times" and "failed
    4 times" are one, and two agents' identical failures with two order ids are one. A UUID becomes
    `<id>` and every token that carries a digit (a count, an amount, a time, an agent or order id, a
    URL with a version in it) becomes `#`; words stay, so two books or two desks stay apart."""
    folded = _NUMBERED.sub("#", _UUID.sub("<id>", str(text or "")))
    return re.sub(r"\s+", " ", folded).strip()[:300]


def _count_repeat(runs: dict[str, Any], text: str, now: float, stamp: str, service: Any = None) -> dict[str, Any]:
    """Count one warning of `text`, written at `now` (`stamp` in ISO), into its run of repeats: runs
    quiet for the window are dropped first, and a run keeps the times inside the window. A run keeps
    the `environment` marker (H2, Sept 25, 2026) only while every warning of it carried the same one:
    "sailbox api 503" and "sailbox api 400" fold to one text, and a run that mixes a service's failure
    with the House's own escalates unmarked."""
    for quiet in [k for k, run in runs.items() if now - float(run.get("last_epoch") or 0) >= REPEAT_WINDOW_SECONDS]:
        runs.pop(quiet)
    marker = service if isinstance(service, str) and service else None  # the warning's `environment`, if any
    run = runs.setdefault(alert_key(text), {"first_seen": stamp, "count": 0, "times": [], "escalated": None, "environment": marker})
    if "environment" not in run or run["environment"] != marker:
        run["environment"] = None  # a run of mixed kinds, or one counted before the marker existed
    run["count"] = int(run.get("count") or 0) + 1
    run["times"] = [t for t in run.get("times") or [] if now - float(t) < REPEAT_WINDOW_SECONDS][-4 * REPEAT_WARNINGS:] + [now]
    run.update(text=text[:300], last_seen=stamp, last_epoch=now)
    return run


class _TickLaps:
    """The seconds each step of one tick took, on the monotonic clock (`time.perf_counter`, well
    under a microsecond a lap): `lap(step)` books the time since the previous lap to `step`, so every
    moment of the tick belongs to exactly one step (health.json `tick_steps`, `House._tick_steps`)."""

    __slots__ = ("began", "last", "seconds")

    def __init__(self) -> None:
        self.began = self.last = time.perf_counter()
        self.seconds: dict[str, float] = {}

    def lap(self, step: str) -> None:
        now = time.perf_counter()
        self.seconds[step] = self.seconds.get(step, 0.0) + (now - self.last)
        self.last = now


def _epoch(iso: str) -> float:
    from league.broker import instant

    parsed = instant(iso)
    return parsed.timestamp() if parsed else 0.0


class House:
    PLUGGABLE_STEPS = ("options_live", "swarm")
    TICK_STEPS_KEPT = 240
    TICK_STEPS_SLOWEST = 8
    SHUTDOWN_WAIT_SECONDS = 5.0

    def __init__(self, root: str | Path, *, settings: Settings | None = None,
                 grant: Any = None, publisher: Any = None, budget: Any = None,
                 clock: Callable[[], float] = time.time):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.clock, self.settings = clock, settings or Settings()
        self.ledger = Ledger(self.root / "ledger.sqlite", clock=clock)
        if grant is None:
            from .live_trading import STORE, LiveGrant
            grant = LiveGrant(self.root / STORE, clock=clock)
        self.grant, self.publisher, self.budget = grant, publisher, budget
        self.options_live = self.swarm = self.backup = self.updater = self.engineer = None
        self._closing = threading.Event()
        self._state_lock = threading.RLock()
        self._state_path = self.root / "house.json"
        try:
            self._state = json.loads(self._state_path.read_text())
        except (OSError, ValueError):
            self._state = {}
        self._lanes = {"ops": threading.Semaphore(max(1, self.settings.ops_workers))}
        self._jobs, self._job_status, self._lane_last = {}, {}, {}
        self._cadence, self._data_cache = {}, {}
        self._laps, self._tick_last = None, None
        self._tick_hour = deque(maxlen=self.TICK_STEPS_KEPT)
        self._record_start()

    def _record_start(self) -> None:
        self.ledger.append("ops.started", {"constitution": constitution_digest(),
                           "real_money": self.settings.real_money,
                           "release": Path(__file__).resolve().parents[1].name})

    def tick(self) -> dict[str, Any]:
        self._laps = _TickLaps()
        summary = {"at": now_iso(self.clock)}
        pause = self.paused()
        open_for_business = not (pause or self.stopped() or self._closing.is_set())
        if self.budget is not None:
            try:
                open_for_business = self.budget.check() == "open" and open_for_business
            except Exception as error:
                open_for_business = False
                self.alert("warning", f"compute budget unavailable: {type(error).__name__}")
        summary.update(budget="open" if open_for_business else "stopped", pause=pause)
        # Closed for new work still calls the live step: it must reconcile and manage exits.
        for name in self.PLUGGABLE_STEPS:
            self._pluggable_step(name, summary, open_for_business)
        if not self._closing.is_set() and not self.stopped():
            if self.backup is not None and self.backup.due():
                self._background("backup:daily", self._run_backup)
            if self.updater is not None and self.updater.due():
                self._background("updater:check", self._update)
            if open_for_business and self.engineer is not None and self.engineer.due():
                self._background("engineer:repair", self.engineer.step)
        self._lap("operator_jobs")
        self._save_state()
        self._lap("save_state")
        if self.publisher is not None and self._cadence_due("publish", self.settings.publish_seconds):
            self._cadence["publish"] = self.clock()
            try:
                self.publisher.publish(self)
            except Exception as error:
                self.alert("warning", f"publishing failed ({type(error).__name__}: {str(error)[:200]})",
                           **environment("site", error))
        self._lap("publish")
        self.ledger.append("ops.tick", {"at": summary["at"], "budget": summary.get("budget")})
        self._health(summary)
        return summary

    def _health(self, summary: Mapping[str, Any]) -> None:
        now = self.clock()
        with self._state_lock:
            jobs = [{"key": key, "state": "queued" if row["started_at"] is None else "running",
                     "queued_seconds": max(0, (row["started_at"] or now) - row["queued_at"]),
                     "running_seconds": max(0, now - row["started_at"]) if row["started_at"] is not None else 0}
                    for key, row in sorted(self._job_status.items())]
        health = {"at": summary["at"], "ledger_seq": self.ledger.head()[0],
                  "real_money": self.settings.real_money, "release": Path(__file__).resolve().parents[1].name,
                  "tick_duration_seconds": round(max(0, now - _epoch(summary["at"])), 3),
                  "background_jobs": jobs, "pause": summary.get("pause"), "budget": summary.get("budget"),
                  "pluggable_steps": {name: getattr(self, name) is not None for name in self.PLUGGABLE_STEPS},
                  "options_live": self._step_health("options_live"), "swarm": self._step_health("swarm"),
                  "repeating_warnings": self._repeating_health(), "failures": [], **self._restarts_health()}
        health["tick_steps"] = self._tick_steps(str(summary["at"]))
        tmp = self.root / "health.tmp"
        tmp.write_text(json.dumps(health, sort_keys=True), encoding="utf-8")
        tmp.chmod(0o600)
        os.replace(tmp, self.root / "health.json")

    def close(self, *, wait: float | None = SHUTDOWN_WAIT_SECONDS) -> None:
        self._closing.set()
        for name in self.PLUGGABLE_STEPS:
            closer = getattr(getattr(self, name), "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass
        self.wait(wait)
        self._save_state()
        self.ledger.close()
        close = getattr(self.grant, "close", None)
        if callable(close):
            close()

    def _save_state(self) -> None:
        # The write under the lock too: the audit job saves from its own thread (it persists the
        # audit it starts and the one it finishes), and two writers sharing one temporary file
        # could lose a replace or leave an older snapshot behind a newer one.
        with self._state_lock:
            text = json.dumps(self._state, sort_keys=True)
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._state_path)


    def alert(self, level: str, text: str, **payload: Any) -> None:
        """An `ops.alert` row. `payload` rides in the same row beside the level and the text (D1,
        Sept 24, 2026: the Alpha Lab's step sends its traceback as `_traceback`; a key that starts
        with an underscore is private, and `ledger.public_view` strips it from everything published).

        A warning that repeats escalates (L3, Sept 24, 2026; `_repeating`): the same text
        (`alert_key`) `REPEAT_WARNINGS` times inside `REPEAT_WINDOW_SECONDS` becomes ONE error alert
        carrying the last warning's payload -- its traceback when the caller supplied one -- with
        `repeated` (the folded text, the count, first and last seen) and `began_at` (when the run of
        repeats began: `league/watchdog.py` counts an error whose condition began before a promotion
        as inherited, never as the new release's doing). It carries the `environment` marker (H2,
        Sept 25, 2026: a service outside the House failed, never a rollback) only when every warning
        of the run carried the same one."""
        row = self.ledger.append("ops.alert", {**payload, "level": level, "text": str(text)[:1000]})
        if str(level).lower() == "warning":
            self._repeating(str(text), payload, seq=getattr(row, "seq", None))


    def _repeating(self, text: str, payload: Mapping[str, Any], *, seq: int | None = None) -> None:
        """Count one warning toward its run of repeats; escalate once when the run reaches the line.
        The runs live in the House's state (house.json), so a restart neither forgets a run nor
        escalates it again; a House whose state holds none rebuilds them from the ledger
        (`_repeating_runs`, before `seq`: this warning's own row, which is counted here)."""
        lock, state = getattr(self, "_state_lock", None), getattr(self, "_state", None)
        if lock is None or state is None:
            return  # an alert raised while the House is still being built
        now = self.clock()
        key = alert_key(text)
        escalate = None
        with lock:
            run = _count_repeat(self._repeating_runs(before=seq), text, now, now_iso(self.clock), payload.get("environment"))
            if len(run["times"]) >= REPEAT_WARNINGS and not run.get("escalated"):
                run["escalated"] = now_iso(self.clock)
                escalate = {k: run.get(k) for k in ("first_seen", "last_seen", "count", "environment")} | {"in_window": len(run["times"])}
        if escalate is not None:
            minutes = int(REPEAT_WINDOW_SECONDS // 60)
            marked = {"environment": escalate["environment"]} if escalate["environment"] else {}  # H2: a service's run stays its
            self.ledger.append("ops.alert", {
                **{k: v for k, v in payload.items() if k != "environment"}, **marked, "level": "error",
                "text": f"a warning repeated {escalate['in_window']} times in {minutes} minutes: {text}"[:1000],
                "repeated": {"text": key, "count": escalate["count"], "first_seen": escalate["first_seen"], "last_seen": escalate["last_seen"]},
                "began_at": escalate["first_seen"]})


    def _repeating_runs(self, *, before: int | None = None) -> dict[str, Any]:
        """The runs of repeats in the House's state (call under `_state_lock`). A state that holds
        none -- the first start of this code over an older House's house.json, or a lost house.json
        -- rebuilds them from the ledger's own recent warnings and escalations, so a condition that
        was already repeating keeps the moment it began and an escalated run is not said again.

        Review of #236 (Sept 24, 2026): Deploy A's House counted no runs, so Deploy B's House would
        have begun every run at its own restart, and a warning that repeated all through Deploy A (a
        site refusing every checkpoint: 11 in the 12 minutes after three restarts on Sept 23) would
        have escalated inside Deploy B's watch with `began_at` after the promotion -- and the
        watchdog would have rolled the healthy release back for a condition it inherited."""
        runs = self._state.get("repeating_warnings")
        if isinstance(runs, dict):
            return runs
        runs = {}
        try:
            rows = self.ledger.read(kinds="ops.alert", limit=2000, newest=True)
        except Exception:  # noqa: BLE001 - a ledger that cannot be read leaves the runs to begin now
            rows = []
        for entry in rows:
            if before is not None and entry.seq >= before:
                continue  # the warning being counted now
            level, repeated = str(entry.payload.get("level") or "").lower(), entry.payload.get("repeated")
            try:
                at = _epoch(entry.at)
            except (TypeError, ValueError):
                continue
            if level == "error" and isinstance(repeated, Mapping):
                escalated = runs.get(str(repeated.get("text") or ""))
                if escalated is not None:
                    escalated["escalated"] = entry.at
            elif level == "warning":
                _count_repeat(runs, str(entry.payload.get("text") or ""), at, entry.at, entry.payload.get("environment"))
        now = self.clock()
        for quiet in [k for k, run in runs.items() if now - float(run.get("last_epoch") or 0) >= REPEAT_WINDOW_SECONDS]:
            runs.pop(quiet)
        self._state["repeating_warnings"] = runs
        return runs


    def _repeating_health(self) -> list[dict[str, Any]]:
        """health.json `repeating_warnings`: each escalated run until it has been quiet for the window."""
        now = self.clock()
        with self._state_lock:
            runs = self._repeating_runs()
            for quiet in [k for k, run in runs.items() if now - float(run.get("last_epoch") or 0) >= REPEAT_WINDOW_SECONDS]:
                runs.pop(quiet)
            return [{"text": run.get("text"), "key": key, "count": run.get("count"), "first_seen": run.get("first_seen"),
                     "last_seen": run.get("last_seen"), "escalated_at": run.get("escalated")}
                    for key, run in sorted(runs.items(), key=lambda kv: str(kv[1].get("first_seen"))) if run.get("escalated")]


    def begin_close(self) -> None:
        """TERM: start no new background work from now on, and let the tick in hand skip its births.
        The loop ends after the tick in hand, which no longer waits on any box background work holds."""
        self._closing.set()


    def stopped(self) -> bool:
        return (self.root / "STOP").exists()


    def paused(self) -> dict[str, Any] | None:
        """The operator's maintenance pause: `PAUSE` in the House root, with the reason as its text.

        STOP ends the loop, and with it reconciliation and every exit. PAUSE keeps the loop and
        closes everything that spends or enters: no research, Merton, semantic lab, survey, replay,
        births or payouts; no promotion; only agents already holding a position are woken, and
        only their exits and cancels reach a book. Research in flight defers at its next paid turn
        and resumes from its checkpoint when the file is removed. The clock-based culls wait too,
        because an agent cannot replay or trade its way out of a pause."""
        path = self.root / "PAUSE"
        try:
            text = path.read_text(encoding="utf-8")[:500].strip()
        except FileNotFoundError:
            return None
        except OSError:
            text = ""
        return {"reason": text or "maintenance"}


    def _update(self) -> None:
        outcome = self.updater.check()
        action = outcome.get("action")
        if action == "deploying":
            # A promotion signals this process and a fresh one comes up thirty seconds later, so
            # every research pass still running is thrown away with everything it has read. The
            # canary and its watch give about ten minutes of warning: stop STARTING passes now and
            # the ones in flight finish on their own. Measured Sept 20, 2026: three deploys inside
            # thirteen minutes killed eleven passes, which is most of an hour's research.
            with self._state_lock:
                self._state["deploying_at"] = self.clock()
        if action == "deploying" or (action == "refused" and outcome.get("new", True)) or outcome.get("new"):
            # The attestation is the record of what GitHub said about the exact commit (see
            # league/updater.py); a head that is merely waiting for its checks is not news.
            self.ledger.append("ops.deploy", {k: v for k, v in outcome.items() if k in ("action", "release", "reasons", "files", "sha", "attestation")})
        if action in ("refused", "blocked", "waiting") and outcome.get("new"):
            # A warning, never an error: an error alert inside a release's watch rolls THAT release
            # back, and a head that cannot be deployed says nothing about the one running.
            self.alert("warning", f"main {str(outcome.get('sha') or '?')[:12]} was not deployed ({action}): "
                                  + "; ".join(str(r) for r in outcome.get("reasons") or [])[:700])


    def _background(self, key: str, work: Callable[..., Any], *args: Any) -> bool:
        """Run slow work beside the tick. One job per key at a time; failures become alerts."""
        if self._closing.is_set():
            return False
        running = self._jobs.get(key)
        if running is not None and running.is_alive():
            return False

        lane_name = "ops"
        lane = self._lanes[lane_name]
        # The House's own bookkeeping runs every minute (`_house_job`): a started and a finished `ops.job`
        # row for each would be 5,760 ledger rows a day that say nothing. Its last run is in health.json
        # (`tick_steps.background.house`) and a failure is still a warning.
        rows = lane_name != "house"
        with self._state_lock:
            self._job_status[key] = {"queued_at": self.clock(), "started_at": None}

        def job() -> None:
            with lane:
                if self._closing.is_set():
                    with self._state_lock:
                        self._job_status.pop(key, None)
                    return
                queued_at = self._job_status[key]["queued_at"]
                started_at = self.clock()
                began = time.perf_counter()  # the lane's run for health.json `tick_steps.background`
                with self._state_lock:
                    self._job_status[key]["started_at"] = started_at
                job_id = f"{key}:{queued_at:.6f}"
                state = "finished"
                try:
                    if rows:
                        self.ledger.append("ops.job", {"job": job_id, "key": key, "state": "started",
                            "queued_seconds": max(0, started_at - queued_at)})
                    work(*args)
                except Exception as exc:  # noqa: BLE001
                    state = "failed"
                    try:
                        self.alert("warning", f"{key} failed ({type(exc).__name__}: {str(exc)[:200]})",
                                   **environment(key.split(":", 1)[0], exc))  # H2: GitHub, a data host, Sail
                    except Exception:  # noqa: BLE001 - the ledger may already be closed on the way out
                        pass
                finally:
                    try:
                        if rows:
                            self.ledger.append("ops.job", {"job": job_id, "key": key, "state": state,
                                "queued_seconds": max(0, started_at - queued_at),
                                "running_seconds": max(0, self.clock() - started_at),
                                "elapsed_seconds": max(0, self.clock() - queued_at)})
                    except Exception:
                        pass  # a missing finish remains visible as interrupted work after restart
                    with self._state_lock:
                        self._job_status.pop(key, None)
                        self._lane_last[lane_name] = {"key": key, "state": state, "seconds": round(time.perf_counter() - began, 3),
                                                      "at": now_iso(self.clock)}

        thread = threading.Thread(target=job, name=f"league-slow:{key}"[:60], daemon=True)
        self._jobs[key] = thread
        thread.start()
        return True


    def wait(self, timeout: float | None = None) -> None:
        """Block until the slow work in hand is done (tests use it; the run loop does not), including
        work that work in hand starts: since H5 (Sept 25, 2026) the House's research scheduling runs on
        its own lane and queues the research jobs from there, so one pass over the threads could end
        before the jobs it started had begun."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            alive = [thread for thread in list(self._jobs.values()) if thread.is_alive()]
            if not alive:
                return
            for thread in alive:
                thread.join(None if deadline is None else max(0, deadline - time.monotonic()))
            if deadline is not None and time.monotonic() >= deadline:
                return


    def _run_backup(self) -> None:
        """One backup, and what the House says about it (`Backup.notice`, H2, Sept 25, 2026): a Sail outage is ONE error
        when it begins, a warning at each later backoff step and an info with its length when it ends, all marked
        `environment: "sail"`, which the watchdog never rolls a release back for; a failure of the House's own code is an
        unmarked error each time, with `began_at` (Sept 24) so one that began before a promotion is inherited. A failure
        that came back while the House was shutting down is a warning, and a backup the shutdown cut off (`close`)
        writes nothing: its thread dies with the process, or finds the ledger closed."""
        before = self.backup.failures_in_a_row()
        said = self.backup.notice(self.backup.run(closing=self._closing.is_set), before)
        if said is not None:
            level, text, payload = said
            self.alert(level, text, **payload)


    def _cadence_due(self, step: str, seconds: float) -> bool:
        """H5 (Sept 25, 2026): is a step the tick keeps at its own cadence due (`_cadence`, stamped by the caller
        when it runs)? The tick runs every `tick_seconds` (30) for the wakes; these keep the cadence they had."""
        return self.clock() - self._cadence.get(step, float("-inf")) >= float(seconds)


    def _lap(self, step: str) -> None:
        """The time since the tick's previous lap is `step`'s (`_TickLaps`); nothing outside a tick."""
        laps = self._laps
        if laps is not None:
            laps.lap(step)


    def _tick_steps(self, at: str) -> dict[str, Any]:
        """health.json `tick_steps` (Sept 24, 2026). Written last in a tick's health, which ends the
        tick's laps: `last` (the tick's `at`, `total_seconds` and each step's seconds, `health`, the
        health block itself, included), `slowest_hour` (each step's slowest in the ticks of the last
        hour on the House's clock, slowest first, with that tick's `at`), `ticks_in_hour`, and
        `background` (each lane's last job: its key, state, seconds and when it ended; beside the tick,
        never in its time). Measured on the box, Sept 24, 2026 08:40-08:50Z: ticks of 51-64 s landing
        70-80 s apart, and nothing that said which step cost what."""
        laps, self._laps = self._laps, None
        now = self.clock()
        if laps is not None:
            laps.lap("health")
            steps = {step: round(seconds, 3) for step, seconds in laps.seconds.items()}
            self._tick_last = {"at": at, "total_seconds": round(laps.last - laps.began, 3), "steps": steps}
            self._tick_hour.append((now, at, steps))
        while self._tick_hour and now - self._tick_hour[0][0] > 3600:
            self._tick_hour.popleft()
        slowest: dict[str, tuple[float, str]] = {}
        for _, stamp, steps in self._tick_hour:
            for step, seconds in steps.items():
                if seconds > slowest.get(step, (-1.0, ""))[0]:
                    slowest[step] = (seconds, stamp)
        with self._state_lock:
            background = {lane: dict(row) for lane, row in sorted(self._lane_last.items())}
        return {"last": self._tick_last, "ticks_in_hour": len(self._tick_hour),
                "slowest_hour": [{"step": step, "seconds": seconds, "at": stamp} for step, (seconds, stamp)
                                 in sorted(slowest.items(), key=lambda kv: (-kv[1][0], kv[0]))[:self.TICK_STEPS_SLOWEST]],
                "background": background}


    def _step_health(self, name: str) -> Any:
        step = getattr(self, name, None)
        health = getattr(step, "health", None)
        if not callable(health):
            return None
        try:
            return health()
        except Exception as exc:  # noqa: BLE001 - one step's health never costs health.json
            return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}


    def site_inputs(self) -> dict[str, Any]:
        """The site's inputs from the two pluggable steps (the publisher's `site_inputs` hook, `league/publish.py`): the
        swarm's (`gym`, `agents`, and `compute`: the swarm's own spend) and the live path's (`structures`: the open real
        and shadow structures). A block both give is merged: lists are joined, and `compute`'s numbers are added part by
        part (each gives its own spend). A step that fails costs its own blocks only, never the checkpoint."""
        out: dict[str, Any] = {}
        for name in ("swarm", "options_live"):
            hook = getattr(getattr(self, name, None), "site_inputs", None)
            if not callable(hook):
                continue
            try:
                given = hook() or {}
            except Exception as exc:  # noqa: BLE001
                self.alert("warning", f"the {name} step's site inputs failed ({type(exc).__name__}: {str(exc)[:160]})")
                continue
            for key, value in dict(given).items():
                if key not in out or out[key] is None:
                    out[key] = value
                elif isinstance(out[key], list) and isinstance(value, list):
                    out[key] = out[key] + value
                elif key == "compute" and isinstance(out[key], Mapping) and isinstance(value, Mapping):
                    merged = dict(out[key])
                    for part, amount in value.items():
                        if part == "as_of":
                            merged[part] = max(str(merged.get(part) or ""), str(amount or "")) or None
                        elif merged.get(part) is None:
                            merged[part] = amount
                        elif amount is not None:
                            merged[part] = Decimal(str(merged[part])) + Decimal(str(amount))
                    out[key] = merged
        return out


    def _pluggable_step(self, name: str, summary: dict[str, Any], open_for_business: bool) -> None:
        """Run one of `PLUGGABLE_STEPS` when it is set; see there."""
        step = getattr(self, name, None)
        if step is None:
            return
        try:
            out = step.tick(self, open_for_business=open_for_business)
            if out is not None:
                summary[name] = out
        except Exception as exc:  # noqa: BLE001 - a step that fails this tick runs again on the next
            self.alert("warning", f"the {name} step failed ({type(exc).__name__}: {str(exc)[:200]})")
        self._lap(name)


    def _restarts_health(self) -> dict[str, Any]:
        """health.json `restarts_24h` (the `ops.started` rows of the last 24 hours on the House's clock),
        `restarts_24h_in_session` (those that fell inside a regular US equity session, which the release train
        must never restart the House in) and `last_start` (the newest: at, release, ledger seq). Read at most
        once a minute. H6 (Sept 25, 2026): 26 starts in the day to 04:25Z, 24-37 a day Sept 20-24, seven inside
        the Sept 24 session; the plan's line is six a day and none in a session, and health said nothing."""
        now = self.clock()
        hit = self._data_cache.get("restarts")
        if hit is not None and now - hit[0] < 60:
            return hit[1]
        try:
            rows = self.ledger.read(kinds="ops.started", limit=500, newest=True)
            since = now_iso(lambda: now - 86400)
            recent = [row for row in rows if row.at >= since]
            in_session = 0
            for row in recent:
                try:
                    in_session += bool(market_open_at(row.at))
                except Exception:  # noqa: BLE001 - a moment outside the computed calendar is not a session
                    pass
            last = rows[-1] if rows else None
            value = {"restarts_24h": len(recent), "restarts_24h_in_session": in_session,
                     "last_start": None if last is None else {"at": last.at, "release": last.payload.get("release"), "seq": last.seq}}
        except Exception as exc:  # noqa: BLE001 - health is written whatever the ledger says
            value = {"restarts_24h": None, "restarts_24h_in_session": None, "last_start": {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}}
        self._data_cache["restarts"] = (now, value)
        return value

