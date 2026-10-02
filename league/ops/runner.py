"""The House's job runner: called once a tick (`House._ops_step` -> `league.ops.tick`), cheap, never waiting.

Each tick it (1) looks at the job child it started, if any: settled when it exits (its result file read into the
receipt), killed when it outlives its wall time; (2) when no child runs, walks the registry's occurrences up to now
(`league/ops/schedule.py`) and settles each one that has no receipt: a job that is switched off or whose module is not
in this release gets a `skipped` row, one past its grace gets a `missed` row (one House warning a tick names them
all), and the earliest one still inside its grace is started as `python -m league.ops run <job>` (niced, its memory and
CPU bounded, a scrubbed environment, its own process group); (3) every `RECEIPTS_EVERY` seconds refreshes the private
receipts file (`league/ops/receipts.py`) on the House's background lane.

One child at a time: a job due while another runs waits, inside its own grace. A child the House's own restart left
behind is killed at the next start and its row marked `interrupted`; it is started again while its grace allows (at
most `store.MAX_ATTEMPTS` times). A job's own alerts (a pre-open FAIL) become House alerts when it ends, at most at
warning level: a job's verdict on the world is never a fault of the release the watchdog is watching, and with any dollar
figure in its text redacted (`ops.alert` is public; the figure rides in the private `_detail`).

While the House is in a maintenance PAUSE, only the jobs the registry marks `in_pause` (the read-only checks, the close
economics, the budget) run; every other due occurrence gets a `skipped` receipt naming the pause. While it has stopped
buying work, the `paid` jobs are skipped the same way.

Occurrences older than this runner's `installed_at` (its first tick on this state) or `LOOKBACK` are never reported.
"""
from __future__ import annotations

import importlib.util
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import schedule as S
from .context import RELEASE, read_json, settings as read_settings
from .registry import JOBS, Job
from .store import INTERRUPTED, OpsStore, retryable

LOOKBACK = 8 * 86400
RECEIPTS_EVERY = 600
#: The child's address space above what the interpreter holds when it starts (`RLIMIT_AS`).
EXTRA_MB = 500
#: The environment a job's child keeps (`league/data_job.py` keeps the same secrets for the nightly collector).
ENV_NAMES = ("PATH", "LANG", "LC_ALL", "TZ", "HOME", "SAIL_API_KEY", "GATEWAY_TOKEN", "SSL_CERT_FILE", "SSL_CERT_DIR",
             "SAILBOX_ID", "SAIL_SAILBOX_ID")
LOG_MAX_BYTES = 5 * 2 ** 20
ALERT_LEVELS = ("info", "warning")


def process_info(pid: int) -> tuple[list[str], str] | None:
    from ..data_job import process_info as info

    return info(pid)


def module_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


class Ops:
    def __init__(self, root: str | Path, *, base: str | Path | None = None, release: str | Path | None = None,
                 python: str = sys.executable, clock: Callable[[], float] = time.time, jobs: Sequence[Job] = JOBS,
                 spawn: Callable[..., Any] | None = None, kill: Callable[[int, int], None] | None = None,
                 proc: Callable[[int], Any] = process_info, present: Callable[[str], bool] = module_present,
                 lookback: float = LOOKBACK):
        self.root = Path(root)
        self.base = Path(base) if base is not None else self.root.parent
        self.release = Path(release) if release is not None else RELEASE
        self.python, self.clock, self.jobs = python, clock, tuple(jobs)
        self.spawn = spawn or self._popen
        self.kill = kill or _killpg
        self.proc, self.present, self.lookback = proc, present, float(lookback)
        self.store = OpsStore(self.root)
        self.started_at = float(clock())
        installed = S.epoch(self.store.get("installed_at"))
        if installed is None:
            installed = self.started_at
            self.store.put("installed_at", S.iso(installed))
        self.installed_at = installed
        self.child: dict[str, Any] | None = None
        self.receipts_at = float("-inf")
        self._settled: set[tuple[str, str]] = set()
        self.last: dict[str, Any] = {}
        #: What holds jobs this tick (`held_by`): {"paused": reason, "stopped": reason}.
        self._holds: dict[str, str] = {}
        self.recovered = self._recover()

    def close(self) -> None:
        self.store.close()

    # ------------------------------------------------------------------ the tick
    def tick(self, house: Any = None) -> dict[str, Any]:
        now = float(self.clock())
        settings = read_settings(self.root)
        out: dict[str, Any] = {}
        if self.child is not None:
            out.update(self._poll(now, house))
        if settings.get("enabled") is False:
            out["enabled"] = False
        elif self.child is None:
            self._holds = held_by(house)
            try:
                out.update(self._dispatch(now, house, settings))
            finally:
                self._holds = {}
        if now - self.receipts_at >= RECEIPTS_EVERY:
            self.receipts_at = now
            self._receipts(house, now)
        self.last = {"at": S.iso(now), **out}
        return out

    def due(self, now: float, settings: Mapping[str, Any] | None = None) -> list[tuple[float, Job, str]]:
        """Every unsettled occurrence up to `now`, earliest first: (due_at, job, kind) with kind `run`, `skip`
        (switched off, or its module is absent) or `missed` (past its grace)."""
        settings = read_settings(self.root) if settings is None else settings
        start = max(self.installed_at - 1, now - self.lookback)
        out: list[tuple[float, Job, str]] = []
        for job in self.jobs:
            for due_at in self._instants(job, start, now):
                key = (job.name, S.iso(due_at))
                if key in self._settled:
                    continue
                row = self.store.run(*key)
                if row is not None and not retryable(row):
                    self._settled.add(key)
                    continue
                if not self._enabled(job, settings) or not self.present(job.module) or self._held(job):
                    kind = "skip"
                elif now > due_at + job.grace:
                    kind = "missed"
                else:
                    kind = "run"
                out.append((due_at, job, kind))
        out.sort(key=lambda item: (item[0], item[1].name))
        return out

    def _instants(self, job: Job, start: float, now: float) -> list[float]:
        found: set[float] = set()
        for trigger in job.triggers:
            if trigger.kind == "start":
                if start < self.started_at <= now:
                    found.add(float(int(self.started_at)))
            elif trigger.kind == "after":
                for row in self.store.ok_since(trigger.job, S.iso(start)):
                    at = S.epoch(row.get("finished_at"))
                    if at is not None and at <= now:
                        found.add(float(int(at)))
            else:
                found.update(S.occurrences(trigger, start, now))
        return sorted(found)

    def _held(self, job: Job) -> str | None:
        """Why the House's own state holds `job` now (its maintenance pause, or its stop on buying work for a paid job)."""
        if self._holds.get("paused") and not job.in_pause:
            return f"the House is paused ({self._holds['paused'][:200]})"
        if self._holds.get("stopped") and job.paid:
            return f"the House has stopped buying work ({self._holds['stopped'][:200]})"
        return None

    @staticmethod
    def _enabled(job: Job, settings: Mapping[str, Any]) -> bool:
        jobs = settings.get("jobs") if isinstance(settings.get("jobs"), Mapping) else {}
        mine = jobs.get(job.name) if isinstance(jobs.get(job.name), Mapping) else {}
        return mine.get("enabled", True) is not False

    def _dispatch(self, now: float, house: Any, settings: Mapping[str, Any]) -> dict[str, Any]:
        missed, skipped, started = [], [], None
        for due_at, job, kind in self.due(now, settings):
            due_iso = S.iso(due_at)
            if kind == "skip":
                why = ("switched off in ops.json" if not self._enabled(job, settings)
                       else f"{job.module} is not in this release ({job.owner})" if not self.present(job.module)
                       else self._held(job) or "held")
                if self.store.run(job.name, due_iso) is None:
                    self.store.record(job.name, due_iso, "skipped", S.iso(now), summary={"why": why})
                else:
                    self._settle_retry(job.name, due_iso, "skipped", now, why)
                self._settled.add((job.name, due_iso))
                skipped.append(job.name)
            elif kind == "missed":
                why = f"not started within {int(job.grace // 60)} minutes of {due_iso}"
                if self.store.run(job.name, due_iso) is None:
                    self.store.record(job.name, due_iso, "missed", S.iso(now), error=why)
                else:
                    self._settle_retry(job.name, due_iso, "missed", now, why)
                self._settled.add((job.name, due_iso))
                missed.append(f"{job.name} due {due_iso}")
            elif started is None:
                started = self._start(job, due_at, now)
        if missed:
            self._alert(house, "warning", f"ops: {len(missed)} job occurrence(s) missed (not started within their grace): "
                                          + "; ".join(missed[:8]) + (" ..." if len(missed) > 8 else ""))
        out: dict[str, Any] = {}
        if started:
            out["started"] = started
        if missed:
            out["missed"] = missed
        if skipped:
            out["skipped"] = sorted(set(skipped))
        return out

    def _settle_retry(self, job: str, due_iso: str, status: str, now: float, why: str) -> None:
        row = self.store.run(job, due_iso)
        if row is not None:
            self.store.finish(int(row["id"]), status, S.iso(now), error=f"{row.get('error')}; then {why}")

    # ------------------------------------------------------------------ the child
    def _start(self, job: Job, due_at: float, now: float) -> str:
        due_iso = S.iso(due_at)
        run_id = self.store.start(job.name, due_iso, S.iso(now))
        result = self.root / "ops" / "results" / f"{run_id}.json"
        result.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            result.unlink()
        except FileNotFoundError:
            pass
        argv = [self.python, "-m", "league.ops", "run", job.name, "--state", str(self.root), "--base", str(self.base),
                "--due", due_iso, "--result", str(result), "--cpu", str(int(job.cpu)), "--extra-mb", str(EXTRA_MB)]
        try:
            child = self.spawn(argv, job)
        except Exception as exc:  # noqa: BLE001 - a start that fails is that occurrence's failed receipt
            self.store.finish(run_id, "failed", S.iso(now), error=f"the child could not start: {type(exc).__name__}: {str(exc)[:300]}")
            self._settled.add((job.name, due_iso))
            return f"{job.name} (start failed)"
        self.store.set_pid(run_id, int(child.pid))
        self.child = {"proc": child, "job": job, "run_id": run_id, "due_at": due_iso, "started": now, "result": result,
                      "pid": int(child.pid)}
        return job.name

    def _poll(self, now: float, house: Any) -> dict[str, Any]:
        child = self.child
        assert child is not None
        code = child["proc"].poll()
        job: Job = child["job"]
        if code is None:
            if now - child["started"] <= job.wall:
                return {"running": job.name}
            try:
                self.kill(child["pid"], signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            self._settle(house, now, "failed", None, f"killed after {job.wall} s of wall time", alerts=[])
            return {"killed": job.name}
        result = read_json(child["result"], None)
        try:
            child["result"].unlink()
        except OSError:
            pass
        if not isinstance(result, dict) or result.get("status") not in ("ok", "failed", "skipped"):
            why = f"exit code {code} and no result" + (" (killed by a signal: CPU or memory limit?)" if code < 0 else "")
            self._settle(house, now, "failed", None, why, alerts=[])
        else:
            self._settle(house, now, result["status"], result.get("summary"), result.get("error"),
                         alerts=result.get("alerts") or [])
        return {"finished": job.name}

    def _settle(self, house: Any, now: float, status: str, summary: Any, error: Any, *, alerts: list) -> None:
        child, self.child = self.child, None
        assert child is not None
        job: Job = child["job"]
        summary = summary if isinstance(summary, Mapping) else ({"value": summary} if summary is not None else None)
        self.store.finish(child["run_id"], status, S.iso(now), summary=summary, error=None if error is None else str(error))
        self._settled.add((job.name, child["due_at"]))
        for row in alerts[:20]:
            if isinstance(row, Mapping) and row.get("text"):
                level = str(row.get("level") or "warning").lower()
                self._alert(house, level if level in ALERT_LEVELS else "warning", f"ops {job.name}: {row['text']}")
        if status == "failed":
            self._alert(house, "warning", f"ops: the {job.name} job failed ({str(error or 'no detail')[:300]})")

    def _alert(self, house: Any, level: str, text: str) -> None:
        """A House alert (`ops.alert`, a PUBLIC ledger kind). A job's text may carry a dollar figure of the account (a
        pre-open check's capital, the grant's refusal): the public text says `$[private]`, and the figures ride in the
        underscore-private `_detail` the ledger keeps off everything published. The receipt keeps them too."""
        alert = getattr(house, "alert", None)
        if not callable(alert):
            return
        public = redact(text)
        if public != text:
            alert(level, public, _detail=str(text)[:1000])
        else:
            alert(level, text)

    def _recover(self) -> list[str]:
        """Rows left `running` by a House that stopped: their child (verified by its command line) is killed, and the
        row is `failed` with `INTERRUPTED` (retried while its grace allows)."""
        out = []
        for row in self.store.running():
            pid = row.get("pid")
            seen = self.proc(int(pid)) if pid else None
            if seen and "league.ops" in seen[0] and row["job"] in seen[0]:
                try:
                    self.kill(int(pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            self.store.finish(int(row["id"]), "failed", S.iso(self.started_at),
                              error=f"{INTERRUPTED}: the House restarted while it ran")
            out.append(row["job"])
        return out

    def _popen(self, argv: list[str], job: Job) -> Any:
        logs = self.root / "ops" / "logs"
        logs.mkdir(parents=True, exist_ok=True, mode=0o700)
        log_path = logs / f"{job.name}.log"
        if log_path.exists() and log_path.stat().st_size > LOG_MAX_BYTES:
            log_path.replace(log_path.with_name(log_path.name + ".1"))
        env = {name: os.environ[name] for name in ENV_NAMES if name in os.environ}
        env.update(PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
        with log_path.open("ab") as log:
            return subprocess.Popen(argv, cwd=str(self.release), env=env, stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, close_fds=True, start_new_session=True)

    # ------------------------------------------------------------------ receipts and health
    def _receipts(self, house: Any, now: float) -> None:
        from .receipts import write

        background = getattr(house, "_background", None)
        if callable(background):
            background("house:ops-receipts", write, self.root, self.base, now)
        else:
            try:
                write(self.root, self.base, now)
            except Exception:  # noqa: BLE001 - receipts are written again in ten minutes
                pass

    def health(self) -> dict[str, Any]:
        """health.json `ops`: the UTC day's occurrences by state (`due`: every occurrence today so far; `late`: due,
        not started, inside its grace; `failed`/`missed`/`skipped`/`ok`: settled today) and the job running now."""
        now = float(self.clock())
        day = S.iso(now)[:10]
        rows = self.store.between(day + "T00:00:00Z", day + "T99")
        counts: dict[str, list[str]] = {"ok": [], "failed": [], "missed": [], "skipped": []}
        for row in rows:
            if row["status"] in counts:
                counts[row["status"]].append(row["job"])
        late = []
        try:
            midnight = S.epoch(day + "T00:00:00Z") or now
            late = [job.name for due_at, job, kind in self.due(now) if kind == "run" and due_at >= midnight]
        except Exception:  # noqa: BLE001 - health is written whatever the calendar says
            pass
        return {"day": day, "due": len(rows) + len(late), "ok": len(counts["ok"]), "failed": sorted(set(counts["failed"])),
                "missed": sorted(set(counts["missed"])), "skipped": len(counts["skipped"]), "late": sorted(set(late)),
                "running": self.child["job"].name if self.child is not None else None,
                "installed_at": S.iso(self.installed_at)}


#: A dollar figure ($1,234.56, $ 87, $-3.2): never in a public alert's text.
DOLLARS = re.compile(r"\$\s?-?\d[\d,]*(?:\.\d+)?")


def redact(text: str) -> str:
    return DOLLARS.sub("$[private]", str(text))


def held_by(house: Any) -> dict[str, str]:
    """What in the House's own state holds jobs: its maintenance pause (`House.paused()`) and its stop on buying work
    (house.json `stopped.reason`, the same reason the tick summary's `stopped_because` gives). Unreadable is no hold."""
    out: dict[str, str] = {}
    if house is None:
        return out
    try:
        paused = house.paused() if callable(getattr(house, "paused", None)) else None
        if paused:
            out["paused"] = str((paused or {}).get("reason") or "maintenance") if isinstance(paused, Mapping) else "maintenance"
    except Exception:  # noqa: BLE001 - a pause that cannot be read holds nothing; the House's own steps still honour it
        pass
    try:
        state = getattr(house, "_state", None)
        stopped = (state.get("stopped") or {}) if isinstance(state, Mapping) else {}
        reason = str(stopped.get("reason") or "") if isinstance(stopped, Mapping) else ""
        if reason and not reason.startswith("maintenance pause"):
            out["stopped"] = reason
    except Exception:  # noqa: BLE001
        pass
    return out


def _killpg(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        os.kill(pid, sig)
