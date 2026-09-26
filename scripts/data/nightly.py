#!/usr/bin/env python3
"""The nightly forward job: yesterday's market into the data box's store and the gate image only.

    python3 scripts/data/nightly.py run [--day YYYY-MM-DD] [--dry-run]
    python3 scripts/data/nightly.py schedule        legacy burst sleep; post-burst uses the House controller
    python3 scripts/data/nightly.py status
    python3 scripts/data/nightly.py daemon --state /workspace/state/data \
        --ready-file /workspace/state/gym-forward.json

`run` (idempotent; each step checks what is already done, so a rerun after any failure finishes
the night and a second run of a finished night does nothing):
  1. the day: the last trading day before today (ET), which must be a forward day (after the
     holdout's 2026-09-25) and at least 01:45 ET behind us (ThetaData serves the previous day from
     then);
  2. the data box: woken; the backfill stopped if it is running (ThetaData allows one session per
     account); `backfill.py run --stages 7 --forward-days DAY` pulls the day for the whole universe,
     then `--stages 8` its SPY/QQQ back months (resumable: a root already in the journal is not
     fetched again); burst backfill is restarted with its last arguments; post-burst resume intent is retained;
  3. the gate image: its box woken (or, when it is gone, forked from its current checkpoint and sealed
     again), each of the day's files downloaded from the data box and uploaded to the same path,
     `backfill.py adopt` there checks every sha256 and journals them, and the gate is re-checkpointed
     with a one-year TTL; the new checkpoint becomes `gate.current_checkpoint` in images.json;
  4. both boxes back to sleep. During the burst a next-night wake may be scheduled; afterward
     the House admits each due 02:00 ET job (06:00Z in summer, 07:00Z in winter) against its current budget.

Forward days go to the gate image and never to a Gym box: the Gym image's box id is refused as a
target. The House supervises `daemon` after the operator installs the private data records and
enables it. The daemon catches up missing forward days, retries failures, and atomically publishes
a checkpoint-ready manifest for the swarm. Its first due time is Tuesday 2026-09-29 06:00Z.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import signal
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import storelib as sl  # noqa: E402

FIRST_FORWARD_DAY = dt.date(2026, 9, 28)
READY_ET_MINUTES = 105  # 01:45 ET

BACKFILL_IDENTITY = r'''
import os, pathlib
def identity(pid, proc_root='/proc'):
    try:
        base = pathlib.Path(proc_root) / str(pid)
        stat = (base / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        argv = (base / 'cmdline').read_bytes().decode().split('\0')
        cwd = (base / 'cwd').resolve()
        exact = any(pathlib.Path(arg).name == 'backfill.py' and argv[i+1] == 'run'
                    and (cwd / arg).resolve() == pathlib.Path('/data/code/backfill.py')
                    for i, arg in enumerate(argv[:-1]))
        return (stat[19], int(stat[2])) if exact else None
    except (OSError, ValueError, IndexError, UnicodeError):
        return None
'''


def eastern(now: dt.datetime) -> dt.datetime:
    from zoneinfo import ZoneInfo

    return now.astimezone(ZoneInfo("America/New_York"))


def target_day(now: dt.datetime, calendar: sl.Calendar) -> dt.date:
    """The previous trading day, if ThetaData has published it; ValueError otherwise."""
    local = eastern(now)
    if local.hour * 60 + local.minute < READY_ET_MINUTES:
        raise ValueError(f"it is {local:%H:%M} ET: the previous day is served from 01:45 ET")
    return calendar.previous(local.date())


def next_wake(now: dt.datetime, calendar: sl.Calendar) -> dt.datetime:
    """02:00 America/New_York after a trading day; 06:00Z in summer, 07:00Z in winter."""
    day = eastern(now).date()
    while True:
        candidate = scheduled_at(day)
        if candidate > now and day > FIRST_FORWARD_DAY and calendar.is_trading(day - dt.timedelta(days=1)):
            return candidate
        day += dt.timedelta(days=1)


def scheduled_at(morning: dt.date, minute: int = 120) -> dt.datetime:
    from zoneinfo import ZoneInfo

    return dt.datetime.combine(morning, dt.time(minute // 60, minute % 60),
                               ZoneInfo("America/New_York")).astimezone(dt.timezone.utc)


def due_days(now: dt.datetime, calendar: sl.Calendar, finished: Sequence[str] = ()) -> list[dt.date]:
    """All missing forward sessions already due, oldest first (also recovers an outage)."""
    return [day for day in calendar.days(FIRST_FORWARD_DAY, eastern(now).date() - dt.timedelta(days=1))
            if day.isoformat() not in finished and scheduled_at(day + dt.timedelta(days=1)) <= now]


class Nightly:
    """The job over two box handles and a record store; every dependency is injected for tests.

    `data` and `gate` are objects with: status() -> str; wake(); sleep(wake_at: str | None);
    run(args: str, timeout: int) -> (ok: bool, stdout: str); download(path) -> bytes;
    upload(path, bytes, mode). `images` is a dict-like record (images.json), saved with `save()`.
    `checkpoint(box_id) -> id` checkpoints the gate. `backfill` holds the last backfill args.
    """

    def __init__(self, *, data: Any, gate: Any, images: dict[str, Any], save: Callable[[dict[str, Any]], None],
                 checkpoint: Callable[[], str], calendar: sl.Calendar, last_backfill_args: str | None,
                 gym_box_ids: Sequence[str] = (), log: Callable[[str], None] = print,
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc), rehearsal: bool = False,
                 relay: Callable[[dt.date, Any], None] | None = None,
                 check_lease: Callable[[], None] = lambda: None, resume_backfill: bool = True):
        self.data, self.gate, self.images, self.save = data, gate, images, save
        self.checkpoint = checkpoint
        self.calendar = calendar
        self.last_backfill_args = last_backfill_args
        self.gym_box_ids = set(gym_box_ids)
        self.log = log
        self.clock = clock
        #: A rehearsal copies a day the data box already holds (a holdout day) to a rehearsal gate box,
        #: skips the pull, and records under `nightly_rehearsals`, never as the gate's state.
        self.rehearsal = rehearsal
        self.relay = relay
        self.check_lease = check_lease
        self.resume_backfill = resume_backfill

    def persist(self) -> None:
        self.check_lease()
        self.save(self.images)

    def state(self, day: dt.date) -> dict[str, Any]:
        if self.rehearsal:
            key = f"{day.isoformat()}:{self.gate.box_id}"
            return self.images.setdefault("nightly_rehearsals", {}).setdefault(key, {})
        nights = self.images.setdefault("gate", {}).setdefault("forward_days", {})
        return nights.setdefault(day.isoformat(), {})

    def run(self, day: dt.date | None = None, *, dry_run: bool = False) -> dict[str, Any]:
        now = self.clock()
        day = day or target_day(now, self.calendar)
        if sl.window_of(day) != "forward" and not (self.rehearsal and sl.window_of(day) == "holdout"):
            raise ValueError(f"{day} is {sl.window_of(day)}, not a forward day")
        if not self.calendar.is_trading(day):
            return {"day": day.isoformat(), "skipped": "not a trading day"}
        if not self.rehearsal and now < scheduled_at(day + dt.timedelta(days=1), READY_ET_MINUTES):
            raise ValueError(f"{day} has not been published yet (01:45 ET on the following day)")
        if getattr(self.gate, "box_id", None) in self.gym_box_ids:
            raise ValueError("the gate target is a Gym box: forward days never reach a Gym box")
        state = self.state(day)
        self.check_lease()
        if state.get("checkpoint"):
            self.log(f"{day}: already done (gate checkpoint {state['checkpoint']})")
            return {"day": day.isoformat(), "already": True, **state}
        if dry_run:
            return {"day": day.isoformat(), "would": ["pull", "copy", "checkpoint"]}

        # 1. the pull, on the data box, with the backfill paused (one ThetaData session per account)
        self.data.wake()
        need_pull = not state.get("pulled") and not self.rehearsal
        was_running = (need_pull or not self.resume_backfill) and self.data.backfill_running()
        if was_running:
            if not self.last_backfill_args:
                raise RuntimeError("cannot pause a running backfill without its restart arguments")
            state["resume_backfill"] = self.last_backfill_args
            self.persist()
            self.check_lease()
            self.data.stop_backfill()
        try:
            if need_pull:
                for stage in (7, 8):  # the day's chains, then (needing them) the back months
                    self.check_lease()
                    ok, out = self.data.run(f"backfill.py run --stages {stage} --forward-days {day.isoformat()} "
                                            "--threads 8 --passes 3 --pause 120", timeout=1800)
                    if not ok:
                        raise RuntimeError(f"the forward pull (stage {stage}) failed: {out[-800:]}")
                if self.relay:
                    self.check_lease()
                    self.relay(day, self.data)
                state["pulled"] = self.clock().isoformat()
                self.persist()
            ok, out = self.data.run(f"backfill.py records --date {day.isoformat()}", timeout=600)
            if not ok:
                raise RuntimeError(f"no records for {day}: {out[-400:]}")
            records = [json.loads(line) for line in out.splitlines() if line.strip().startswith("{")]
        finally:
            if state.get("resume_backfill") and not self.resume_backfill:
                state["resume_backfill_deferred"] = "post-burst bulk backfill paused; arguments retained for an authorized funded run"
                self.persist()
            elif state.get("resume_backfill") and not self.data.backfill_running():
                self.check_lease()
                self.data.start_backfill(state["resume_backfill"])
                state.pop("resume_backfill")
                self.persist()
        files = [r for r in records if r.get("type") == "file"]
        if not files:
            raise RuntimeError(f"the data box holds no files for {day}")
        allowed = ("forward", "holdout") if self.rehearsal else ("forward",)
        if any(r.get("window") not in allowed for r in files):
            raise RuntimeError("a record that is not a forward day was about to reach the gate")
        for record in files:
            parsed = sl.parse_rel_path(record.get("path", ""))
            if (parsed is None or record.get("path") != sl.rel_path(*parsed) or parsed[2] != day
                    or parsed != (record.get("kind"), record.get("root"), day)
                    or record.get("date") != day.isoformat()):
                raise RuntimeError("invalid or mismatched path in forward records")
        kinds = {}
        for record in files:
            kinds.setdefault(record["root"], set()).add(record["kind"])
        if any("nbbo" in present and "underlying" not in present for present in kinds.values()):
            state.pop("pulled", None)
            self.persist()
            raise RuntimeError("the forward day has NBBO without its underlying series")

        # 2. the copy, file by file, checked on arrival
        self.gate.wake()
        copied = 0
        for record in files:
            self.check_lease()
            blob = self.data.download(f"{sl.STORE_ROOT}/{record['path']}")
            if hashlib.sha256(blob).hexdigest() != record["sha256"]:
                raise RuntimeError(f"{record['path']} changed on the way (sha256)")
            self.gate.upload(f"{sl.STORE_ROOT}/{record['path']}", blob, 0o644)
            copied += 1
        payload = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records).encode()
        records_path = f"/data/work/nightly-{day.isoformat()}.jsonl"
        self.check_lease()
        self.gate.upload(records_path, payload, 0o644)
        ok, out = self.gate.run(f"backfill.py adopt --records {records_path}", timeout=1800)
        if not ok:
            raise RuntimeError(f"the gate refused the day: {out[-800:]}")
        state.update({"files": copied, "adopted": self.clock().isoformat(), "roots": sorted({r['root'] for r in files})})
        self.persist()

        # 3. the gate's new checkpoint
        self.check_lease()
        checkpoint = self.checkpoint()
        self.check_lease()
        state["checkpoint"] = checkpoint
        if not self.rehearsal:
            gate = self.images.setdefault("gate", {})
            gate["current_checkpoint"] = checkpoint
            gate.setdefault("checkpoints", []).append({"id": checkpoint, "day": day.isoformat(), "at": self.clock().isoformat()})
        self.persist()
        self.gate.sleep(None)
        if not self.data.backfill_running():
            self.data.sleep(next_wake(self.clock(), self.calendar).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.log(f"{day}: {copied} files to the gate; checkpoint {checkpoint}")
        return {"day": day.isoformat(), **state}


# ------------------------------------------------------------------------------ the real handles
class BoxHandle:
    def __init__(self, api: Any, box_id: str, *, defer_sleep: bool = False):
        self.api, self.box_id = api, box_id
        self.defer_sleep = defer_sleep
        self.pending_sleep = False
        self.wake_at = None

    def status(self) -> str:
        return str((self.api.get(self.box_id) or {}).get("status") or "")

    def wake(self) -> None:
        import boxlib as bl

        bl.ensure_running(self.api, self.box_id)

    def sleep(self, wake_at: str | None) -> None:
        if self.defer_sleep:
            self.pending_sleep, self.wake_at = True, wake_at
        else:
            self.api.sleep(self.box_id, wake_at=wake_at)

    def flush_sleep(self) -> None:
        if self.pending_sleep:
            self.api.sleep(self.box_id, wake_at=self.wake_at)
            self.pending_sleep = False

    def run(self, args: str, timeout: int) -> tuple[bool, str]:
        import boxlib as bl

        result = bl.run_py(self.api, self.box_id, args, timeout=timeout)
        return result.ok, result.stdout if result.ok else result.output

    def download(self, path: str) -> bytes:
        return self.api.download(self.box_id, path, timeout=900)

    def upload(self, path: str, blob: bytes, mode: int) -> None:
        self.api.upload(self.box_id, path, blob, mode=mode, timeout=900)

    def backfill_running(self) -> bool:
        code = BACKFILL_IDENTITY + """
p = pathlib.Path('/data/work/backfill.pid')
try:
    pid = int(p.read_text())
    print('yes' if identity(pid) is not None else 'no')
except (OSError, ValueError):
    print('no')
"""
        out = self.api.exec(self.box_id, ["/opt/data-venv/bin/python", "-c", code], timeout=60)
        if not out.ok:
            raise RuntimeError("could not read the backfill process state")
        return out.stdout.strip() == "yes"

    def backfill_receipt(self) -> dict[str, Any] | None:
        code = BACKFILL_IDENTITY + """
import json
try:
    pid = int(pathlib.Path('/data/work/backfill.pid').read_text())
except FileNotFoundError:
    print('null'); raise SystemExit(0)
found = identity(pid)
if found is None:
    if pathlib.Path('/proc', str(pid)).exists():
        raise SystemExit('backfill process identity is unreadable or changed')
    print('null'); raise SystemExit(0)
argv = pathlib.Path('/proc', str(pid), 'cmdline').read_bytes().decode().split('\\0')
index = next(i for i, arg in enumerate(argv[:-1]) if pathlib.Path(arg).name == 'backfill.py' and argv[i+1] == 'run')
print(json.dumps({'pid': pid, 'start': found[0], 'pgid': found[1], 'args': [x for x in argv[index+2:] if x]}))
"""
        result = self.api.exec(self.box_id, ["/opt/data-venv/bin/python", "-c", code], timeout=60).check()
        row = json.loads(result.stdout)
        if row is not None and (not isinstance(row, dict) or type(row.get("pid")) is not int
                                or type(row.get("pgid")) is not int or not str(row.get("start", "")).isdigit()
                                or not isinstance(row.get("args"), list)):
            raise RuntimeError("invalid backfill process receipt")
        return row

    def stop_backfill(self, expected: Mapping[str, Any] | None = None) -> None:
        code = BACKFILL_IDENTITY + """
import json, signal, time
expected = json.loads(EXPECTED_JSON)
try:
    pid = int(pathlib.Path('/data/work/backfill.pid').read_text())
except (OSError, ValueError):
    raise SystemExit(0)
initial = identity(pid)
if expected is not None and (pid != expected['pid'] or initial != (expected['start'], expected['pgid'])):
    raise SystemExit('backfill ownership changed before stop')
def alive():
    return initial is not None and identity(pid) == initial
if initial is not None:
    def send(sig):
        # Re-check start ticks, exact script path/argv and group ownership before EVERY signal.
        if not alive():
            return
        try:
            os.killpg(pid, sig) if initial[1] == pid else os.kill(pid, sig)
        except ProcessLookupError:
            pass
    send(signal.SIGTERM)
    for _ in range(60):
        if not alive(): break
        time.sleep(1)
    if alive(): send(signal.SIGKILL)
    for _ in range(10):
        if not alive(): break
        time.sleep(1)
    if alive(): raise SystemExit('backfill did not stop')
if identity(pid) is not None:
    raise SystemExit('backfill identity changed during stop; retry under the operation lease')
"""
        code = code.replace("EXPECTED_JSON", repr(json.dumps(expected)))
        self.api.exec(self.box_id, ["/opt/data-venv/bin/python", "-c", code], timeout=90).check()

    def start_backfill(self, args: str) -> None:
        import boxlib as bl

        if self.backfill_running():
            raise RuntimeError("refusing to start a second backfill session")
        receipt = f"/data/work/restart-{uuid.uuid4().hex}.exit"
        run = shlex.join([bl.VENV_PY, "backfill.py", "run", *shlex.split(args)])
        inner = f"{run}; status=$?; echo $status > {shlex.quote(receipt)}; exit $status"
        command = (f"mkdir -p /data/work && cd {shlex.quote(bl.CODE_DIR)} && setsid nohup sh -c {shlex.quote(inner)} "
                   ">> /data/work/backfill.out 2>&1 < /dev/null &")
        self.api.exec(self.box_id, command, timeout=60, background=True).check()
        for _ in range(20):
            if self.backfill_running():
                return
            result = self.api.exec(self.box_id, ["bash", "-c", f"cat {shlex.quote(receipt)} 2>/dev/null || true"], timeout=60)
            if result.stdout.strip():
                if result.stdout.strip() == "0":
                    return  # the resumable queue was already empty and finished cleanly
                raise RuntimeError(f"the backfill restart exited with {result.stdout.strip()}")
            time.sleep(0.5)
        raise RuntimeError("the restarted backfill never confirmed its running identity or a clean completion")


def real_job(*, rehearsal_gate: str | None = None, api: Any = None,
             check_lease: Callable[[], None] = lambda: None, resume_backfill: bool = True) -> Nightly:
    import boxlib as bl

    api = api or bl.client()
    images = bl.read_json(bl.IMAGES)
    gate = {"box_id": rehearsal_gate} if rehearsal_gate else ((images.get("gate") or {}).get("current") or {})
    if not gate.get("box_id"):
        raise RuntimeError("no gate image recorded in images.json; build it first (images.py build gate)")
    gym_ids = [e.get("box_id") for e in (images.get("gym") or {}).get("history", []) if e.get("box_id")]
    data = BoxHandle(api, bl.data_box_id(), defer_sleep=True)
    data.wake()
    calendar_json = json.loads(api.download(data.box_id, "/data/work/calendar.json"))
    calendar = sl.Calendar.from_json(calendar_json["exceptions"])
    try:
        status = str((api.get(gate["box_id"]) or {}).get("status", ""))
    except bl.SailboxError as error:
        if error.status != 404:
            raise
        status = "terminated"
    if status in ("terminated", "terminating", "failed", "create_failed"):
        if rehearsal_gate:
            raise RuntimeError("the rehearsal gate no longer exists")
        checkpoint_id = images["gate"].get("current_checkpoint") or gate["checkpoints"][0]
        check_lease()
        new = api.from_checkpoint(checkpoint_id, name="ltcm-gate-image-forward", timeout=1800)
        gate["box_id"] = new["sailbox_id"]
        from images import seal

        seal(api, gate["box_id"])
        check_lease()
        bl.write_json(bl.IMAGES, images)
    gate_handle = BoxHandle(api, gate["box_id"])
    gate_handle.wake()
    document = (api.egress(gate_handle.box_id) or {}).get("document", {})
    if document.get("no_network") is not True:
        raise RuntimeError("the forward target is not sealed")
    api.exec(gate_handle.box_id, ["test", "-f", "/data/store/GATE"], timeout=60).check()
    check_lease()
    bl.push_code(api, gate_handle.box_id)
    last_args = (bl.read_json(bl.DATA_BOX).get("runs") or [{}])[-1].get("args")

    def checkpoint() -> str:
        from images import checkpoint_with_retry

        row = checkpoint_with_retry(api, gate["box_id"], name=f"ltcm-gate-{bl.now().replace(':', '')}",
                                    ttl_seconds=(2 if rehearsal_gate else 365) * 86400, check_lease=check_lease)
        return row["checkpoint_id"]

    def relay(day, handle):
        from sip import GatewayBars, relay_day
        gateway = None
        if isinstance(api, PaidNight):
            config = json.loads((Path(__file__).resolve().parents[2] / "league/config.json").read_text())
            gateway = GatewayBars(config["gateway_url"], os.environ.get("GATEWAY_TOKEN", ""),
                                  deadline=api.deadline, clock=api.budget.clock, check=check_lease)
        return relay_day(day, handle, gateway=gateway)

    return Nightly(data=data, gate=gate_handle, images=images, save=lambda d: bl.write_json(bl.IMAGES, d),
                   checkpoint=checkpoint, calendar=calendar, last_backfill_args=last_args, gym_box_ids=gym_ids,
                   rehearsal=bool(rehearsal_gate), relay=relay, check_lease=check_lease, resume_backfill=resume_backfill)


def _run_real(day: dt.date | None = None, *, rehearsal_gate: str | None = None,
              dry_run: bool = False, operation: Any = None) -> dict[str, Any]:
    import boxlib as bl

    api = operation if operation is not None else bl.client()
    data_box = bl.data_box_id()
    bl.ensure_running(api, data_box)
    job = None
    with bl.RemoteLease(operation.client if operation is not None else api, data_box) as lease:
        def check():
            lease.check()
            if operation is not None:
                operation.check()
        try:
            # Gate recovery/verification and code changes are covered by the same cross-host lease.
            job = real_job(rehearsal_gate=rehearsal_gate, api=api, check_lease=check, resume_backfill=operation is None)
            check()
            bl.push_code(api, data_box)
            result = job.run(day, dry_run=dry_run)
            if operation is None:
                job.gate.sleep(None)
            if operation is None and not job.data.backfill_running():
                job.data.sleep(next_wake(job.clock(), job.calendar).strftime("%Y-%m-%dT%H:%M:%SZ"))
        except BaseException:
            # Sleep only while we still own the gate. A lost lease may have a new controller.
            try:
                if job is not None and operation is None:
                    lease.check()
                    job.gate.sleep(None)
            except Exception:
                pass
            raise
        finally:
            if operation is not None:
                operation.cleanup(lease)
    if operation is None:
        job.data.flush_sleep()  # legacy burst behavior
    return result


class PaidNight:
    """One exclusive data/Gate operation; holds survive a lost response or unconfirmed cleanup."""
    def __init__(self, api, budget, key, day, amount, deadline, record=None):
        from league.swarm.lifecycle import BoundedClient
        self.client, self.budget, self.key = api, budget, key
        self.deadline = deadline
        self.record = record or {"key": key, "day": day.isoformat(), "amount": amount, "started": budget.clock(),
                                 "deadline": deadline, "boxes": [], "pending_forks": [], "status": "running"}
        self.bounded = BoundedClient(api, lambda: deadline, clock=budget.clock)
        self.cleaned = False
        self.save()

    def save(self):
        self.budget.store.put("nightly_operation", self.record)

    def check(self):
        from league.swarm.lifecycle import BudgetDeferred
        if self.budget.clock() >= self.deadline - 120:
            raise BudgetDeferred("nightly runtime bound reached")

    def own(self, box):
        from league.swarm.lifecycle import capacity
        dims = capacity(self.client.get(box), float(self.budget.cfg.get("box_rate_usd_hour", .6)))
        if box not in self.record["boxes"]:
            self.record["boxes"].append(box)
            self.save()
        return dims

    def __getattr__(self, name):
        return getattr(self.bounded, name)

    def resume(self, box, **kwargs):
        self.own(box)
        return self.bounded.resume(box, **kwargs)

    def from_checkpoint(self, checkpoint, *, name, **kwargs):
        from league.swarm.lifecycle import capacity
        bound = (self.budget.store.get("checkpoint_capacities") or {}).get(checkpoint)
        capacity(bound or {}, float(self.budget.cfg.get("box_rate_usd_hour", .6)))
        # Exact persisted ownership before POST; a lost POST is found by this name alone.
        name = "ltcm-nightly-" + hashlib.sha256(self.key.encode()).hexdigest()[:20]
        self.record["pending_forks"].append(name)
        self.save()
        row = self.bounded.from_checkpoint(checkpoint, name=name, **kwargs)
        box = row["sailbox_id"]
        self.record["boxes"].append(box)  # own even an oversized bad fork, so cleanup can end it
        self.record["pending_forks"].remove(name)
        self.record["forks"] = int(self.record.get("forks", 0)) + 1
        self.save()
        self.own(box)
        return row

    def checkpoint(self, box, **kwargs):
        before = self.own(box)
        row = self.bounded.checkpoint(box, **kwargs)
        after = self.own(box)
        if before != after:
            raise RuntimeError("gate capacity changed across its checkpoint")
        with self.budget.store.atomic():
            known = self.budget.store.get("checkpoint_capacities") or {}
            known[row["checkpoint_id"]] = {**after, "source": "exclusive nightly lease: same GET dimensions before/after checkpoint POST",
                                          "checkpoint": row["checkpoint_id"], "verified_at": self.budget.clock()}
            self.budget.store.put("checkpoint_capacities", known)
        return row

    def sleep(self, box, **kwargs):
        # Nightly.run requests sleeps before it returns. Cleanup performs them together under ownership.
        return {"deferred_to_owned_cleanup": True}

    def cleanup(self, lease):
        """Only under the data lease. Confirm sleeps; keep the lease until expiry to prevent a release/sleep race."""
        import boxlib as bl
        from league.swarm.lifecycle import BudgetDeferred
        if self.record.get("status") == "cleaned":
            return
        data = bl.data_box_id()
        lease.check()
        self.record["lease_token"] = lease.token
        self.record["owner_pid"] = os.getpid()
        self.record["owner_start"] = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19]
        self.save()
        lease.stop.set()
        if lease.worker is not None:
            lease.worker.join(timeout=65)
            if lease.worker.is_alive():
                raise BudgetDeferred("lease renewer did not stop; cannot sleep its data box")
        lease.preserve_for_sleep = True
        self.record["retry_not_before"] = self.budget.clock() + 2400
        self.save()
        if self.record["pending_forks"]:
            rows = self.client.list_boxes(limit=1000)
            for name in list(self.record["pending_forks"]):
                found = [r for r in rows if r.get("name") == name]
                if not found:
                    continue  # it may still materialize; absence is not confirmed cancellation
                for row in found:
                    box = str(row.get("sailbox_id") or row.get("id"))
                    if box not in self.record["boxes"]:
                        self.record["boxes"].append(box)
                self.record["forks"] = int(self.record.get("forks", 0)) + len(found)
                self.record["pending_forks"].remove(name)
            self.save()
        errors = []
        for box in sorted(set(self.record["boxes"]), key=lambda b: b == data):
            try:
                lease.check()
                if box == data:
                    lease.preserve_for_sleep = True
                    self.record["retry_not_before"] = self.budget.clock() + 2400
                    self.save()
                self.client.sleep(box)
                if self.client.get(box).get("status") not in ("sleeping", "paused", "terminated"):
                    raise RuntimeError("sleep not confirmed")
            except Exception as exc:
                errors.append(f"{box}: {type(exc).__name__}")
        if errors or self.record["pending_forks"]:
            self.record.update(status="cleanup_pending", errors=errors, retry_not_before=self.budget.clock() + 2400)
            self.save()
            raise BudgetDeferred("nightly cleanup is unresolved; its commitment remains held")
        elapsed = max(0, self.budget.clock() - float(self.record["started"]))
        charge = (max(2, len(set(self.record["boxes"]))) * float(self.budget.cfg.get("box_rate_usd_hour", .6)) * elapsed / 3600
                  + int(self.record.get("forks", 0)) * float(self.budget.cfg.get("box_creation_usd", .012)))
        with self.budget.store.atomic():
            self.budget.store.add_spend("data_box", charge, detail={"budget_key": self.key, "seconds": elapsed,
                                       "basis": "capacity bound; both owned boxes; confirmed sleeping"})
            self.budget.charge(self.key, charge, final=True)
            self.record.update(status="cleaned", charge_usd=charge)
            self.save()
        self.cleaned = True


def run_real(day: dt.date | None = None, *, rehearsal_gate: str | None = None, dry_run: bool = False,
             budget_root: Path | None = None) -> dict[str, Any]:
    """The automatic and manual paid paths share the House's budget after the burst."""
    import boxlib as bl
    from league.swarm import settings as swarm_settings
    from league.swarm.lifecycle import BudgetDeferred, SailBudget, capacity, number
    from league.swarm.store import SwarmStore

    root = Path(budget_root) if budget_root is not None else bl.STATE_DIR.parent
    cfg = swarm_settings.load(root)
    end = dt.datetime.fromisoformat(cfg["guard"]["burst_until"].replace("Z", "+00:00")).timestamp()
    if not (root / "swarm.sqlite").exists():
        if time.time() < end:
            return _run_real(day, rehearsal_gate=rehearsal_gate, dry_run=dry_run)
        raise BudgetDeferred("post-burst nightly work requires the House budget ledger")
    store = SwarmStore(root, clock=time.time)
    try:
        budget = SailBudget(store, cfg)
        if budget.burst():
            return _run_real(day, rehearsal_gate=rehearsal_gate, dry_run=dry_run)
        if day is None:
            calendar = sl.Calendar.from_json(bl.read_json(bl.STATE_DIR / "calendar.json")["exceptions"])
            day = target_day(dt.datetime.now(dt.timezone.utc), calendar)
        cached = (store.get("nightly_results") or {}).get(day.isoformat())
        if cached is not None and not rehearsal_gate:
            return cached
        old = store.get("nightly_operation") or {}
        if time.time() < float(old.get("retry_not_before") or 0):
            raise BudgetDeferred("prior nightly owner retained the sleeping lease until its expiry")
        if old.get("status") in ("running", "cleanup_pending"):
            if old.get("status") == "running" and time.time() < float(old.get("deadline") or 0):
                raise BudgetDeferred("prior nightly operation still owns a commitment or sleeping lease")
            api = bl.client()
            op = PaidNight(api, budget, old["key"], dt.date.fromisoformat(old["day"]), old["amount"], old["deadline"], record=old)
            # No fresh paid job until the previous exact ownership is resolved under the operation lease.
            bl.ensure_running(api, bl.data_box_id())
            with bl.RemoteLease(api, bl.data_box_id()) as lease:
                op.cleanup(lease)
            raise BudgetDeferred("prior nightly operation cleaned; retry from its durable stage record")
        api = bl.client()
        data = bl.data_box_id()
        capacity(api.get(data), float(budget.cfg.get("box_rate_usd_hour", .6)))
        images = bl.read_json(bl.IMAGES)
        gate = rehearsal_gate or ((images.get("gate") or {}).get("current") or {}).get("box_id")
        if not gate:
            raise BudgetDeferred("no owned gate image is configured")
        try:
            gate_row = api.get(gate)
        except Exception as exc:
            if getattr(exc, "status", None) != 404:
                raise
            gate_row = {"status": "terminated"}
        if gate_row.get("status") not in ("terminated", "terminating", "failed", "create_failed"):
            capacity(gate_row, float(budget.cfg.get("box_rate_usd_hour", .6)))
        else:
            checkpoint = images["gate"].get("current_checkpoint") or images["gate"]["current"]["checkpoints"][0]
            capacity((store.get("checkpoint_capacities") or {}).get(checkpoint) or {}, float(budget.cfg.get("box_rate_usd_hour", .6)))
        status = budget.status()
        amount = min(float(budget.cfg.get("maintenance_usd", {}).get("nightly", 0)), status["room_usd"],
                     max(0., status["maintenance"].get("nightly", 0) - status["buckets"]["nightly"]))
        rate = float(budget.cfg.get("box_rate_usd_hour", .6))
        fee = number(budget.cfg.get("box_creation_usd", .012))
        if fee < .012:
            raise BudgetDeferred("nightly creation fee bound is below the observed l-box rate")
        duration = min(10800, number(budget.cfg.get("nightly_max_seconds", 10800)), (amount - fee) / (2 * rate) * 3600)
        if duration < 300:
            raise BudgetDeferred("nightly budget cannot fund a bounded work interval")
        key = f"nightly:{day}:{uuid.uuid4().hex}"
        with store.atomic():
            if (store.get("nightly_operation") or {}) != old:
                raise BudgetDeferred("nightly controller state changed during admission; retry")
            budget.reserve(key, amount, kind="data_box", bucket="nightly", detail={"day": day.isoformat()})
            op = PaidNight(api, budget, key, day, amount, time.time() + duration)
        op.own(data)
        if gate_row.get("status") not in ("terminated", "terminating", "failed", "create_failed"):
            op.own(gate)
        result = _run_real(day, rehearsal_gate=rehearsal_gate, dry_run=dry_run, operation=op)
        result["resources"] = (store.get("checkpoint_capacities") or {}).get(result.get("checkpoint"))
        if not rehearsal_gate and not dry_run:
            with store.atomic():
                results = store.get("nightly_results") or {}
                results[day.isoformat()] = result
                store.put("nightly_results", results)
        return result
    finally:
        store.close()


def publish_ready(path: Path, result: Mapping[str, Any], now: dt.datetime) -> dict[str, Any]:
    """Only a completed, checkpointed forward day becomes visible to the swarm; no data leaves."""
    import boxlib as bl

    if not result.get("checkpoint") or not str(result["checkpoint"]).startswith("sbcp_"):
        raise ValueError("a completed gate checkpoint is required")
    day = dt.date.fromisoformat(result["day"])
    if sl.window_of(day) != "forward":
        raise ValueError("only forward days can be published")
    document = {"schema": 1, "gate_checkpoint": result["checkpoint"], "day": day.isoformat(),
                "ready_at": now.isoformat(), "roots": list(result.get("roots") or ())}
    if result.get("resources"):
        document["resources"] = result["resources"]
    previous = bl.read_json(path)
    if str(previous.get("day", "")) <= day.isoformat():
        bl.write_json(path, document)
    return document


class Controller:
    """A durable schedule; a failed night stays pending, and outages are caught up oldest first."""

    def __init__(self, state: Path, ready_file: Path, calendar: sl.Calendar, *,
                 run: Callable[[dt.date], dict[str, Any]], retry_seconds: int = 300,
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)):
        self.state, self.ready_file, self.calendar = state, ready_file, calendar
        self.run, self.retry_seconds, self.clock = run, retry_seconds, clock

    def tick(self) -> dict[str, Any]:
        import boxlib as bl

        now = self.clock()
        record = bl.read_json(self.state / "nightly.json")
        finished = record.get("completed", {})
        pending = due_days(now, self.calendar, finished)
        if not pending:
            return {"phase": "waiting", "next_wake": next_wake(now, self.calendar).isoformat()}
        if float(record.get("retry_at", 0)) > now.timestamp():
            return {"phase": "retry", "retry_at": record["retry_at"], "error": record.get("error")}
        day = pending[0]
        try:
            result = self.run(day)
            ready = publish_ready(self.ready_file, result, self.clock())
        except Exception as error:
            record.update({"error": f"{type(error).__name__}: {str(error)[:500]}",
                           "retry_at": self.clock().timestamp() + self.retry_seconds, "day": day.isoformat()})
            bl.write_json(self.state / "nightly.json", record)
            return {"phase": "retry", **record}
        finished[day.isoformat()] = ready["gate_checkpoint"]
        record.update({"completed": finished, "error": None, "retry_at": 0, "day": day.isoformat()})
        bl.write_json(self.state / "nightly.json", record)
        return {"phase": "complete", "day": day.isoformat(), "gate_checkpoint": ready["gate_checkpoint"]}


def daemon(state: Path, ready_file: Path, *, poll: float = 30.0) -> int:
    import boxlib as bl
    from locking import process_lock

    calendar_file = state / "calendar.json"
    calendar = sl.Calendar.from_json(json.loads(calendar_file.read_text())["exceptions"])
    stop = threading.Event()
    finished = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    status: dict[str, Any] = {"phase": "starting"}
    cutoff_status: dict[str, Any] = {"status": "starting"}
    release = str(Path(__file__).resolve().parents[2])
    start = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19]
    identity = {"pid": os.getpid(), "start": start, "release": release}

    def heartbeat():
        while not finished.is_set():
            bl.write_json(state / "nightly.heartbeat", {**identity, "at": time.time(), **status,
                                                       "completion_cutoff": dict(cutoff_status),
                                                       "state": status.get("phase"),
                                                       "busy": status.get("phase") == "running"})
            finished.wait(30)

    def watch_cutoff():
        # A Completion call can be waiting on remote work while the burst ends. This independent,
        # bounded cleanup observer keeps the already running backfill from escaping the transition.
        from burst_cutoff import Cutoff
        from league.swarm import settings as swarm_settings
        from league.swarm.store import SwarmStore
        store = SwarmStore(ready_file.parent)
        try:
            cutoff = Cutoff(state, store, swarm_settings.load(ready_file.parent))
            while not finished.is_set():
                try:
                    result = cutoff.tick()
                except Exception as exc:
                    result = {"status": "unavailable", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
                cutoff_status.clear()
                cutoff_status.update(result)
                finished.wait(30)
        finally:
            store.close()

    def run(day):
        status.clear()
        status.update({"phase": "running", "day": day.isoformat()})
        return run_real(day, budget_root=ready_file.parent)

    with process_lock(state / "nightly.lock") as lock:
        lock.seek(0)
        lock.truncate()
        json.dump(identity, lock)
        lock.flush()
        os.fsync(lock.fileno())
        (state / "nightly.pid").write_text(str(os.getpid()))
        worker = threading.Thread(target=heartbeat, daemon=True)
        worker.start()
        cutoff_worker = threading.Thread(target=watch_cutoff, daemon=True, name="completion-cutoff")
        cutoff_worker.start()
        controller = Controller(state, ready_file, calendar, run=run)
        try:
            while not stop.is_set() and not (state / "nightly.stop").exists():
                result = controller.tick()
                status.clear()
                status.update(result)
                if (not stop.is_set() and not (state / "nightly.stop").exists()
                        and bl.read_json(state / "completion-config.json").get("enabled") is True):
                    from complete import Completion
                    from league.swarm import settings as swarm_settings
                    from league.swarm.lifecycle import Lifecycle
                    from league.swarm.store import SwarmStore

                    budget_store = SwarmStore(ready_file.parent)
                    try:
                        burst = Lifecycle(budget_store, swarm_settings.load(ready_file.parent)).burst()
                    finally:
                        budget_store.close()
                    if not burst:
                        status.update(completion="deferred", completion_error="bulk store completion is outside the post-burst maintenance allocation")
                        stop.wait(poll)
                        continue

                    status.clear()
                    status.update({"phase": "running", "job": "store-completion"})
                    completion = Completion(state).tick()
                    status.clear()
                    status.update({**result, "completion": completion.get("phase"),
                                   "completion_error": completion.get("error")})
                stop.wait(poll)
        finally:
            stop.set()
            finished.set()
            worker.join(timeout=35)
            (state / "nightly.pid").unlink(missing_ok=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", default=None, help="controller records (default .data/gym)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--day", default=None)
    r.add_argument("--dry-run", action="store_true")
    rh = sub.add_parser("rehearse", help="copy a holdout day the data box holds to a rehearsal gate box")
    rh.add_argument("--gate-box", required=True)
    rh.add_argument("--day", required=True)
    sub.add_parser("schedule")
    sub.add_parser("status")
    d = sub.add_parser("daemon", help="run the autonomous forward controller on the House")
    d.add_argument("--state", default=None, dest="daemon_state")
    d.add_argument("--ready-file", required=True)
    args = parser.parse_args(argv)
    state = getattr(args, "daemon_state", None) or args.state
    if state:
        os.environ["LTCM_GYM_STATE"] = state
        import boxlib as bl

        bl.configure_state(Path(state))
    if args.cmd == "daemon":
        import boxlib as bl

        return daemon(bl.STATE_DIR, Path(args.ready_file))
    if args.cmd == "status":
        import boxlib as bl

        print(json.dumps({"forward_days": (bl.read_json(bl.IMAGES).get("gate") or {}).get("forward_days", {}),
                          "controller": bl.read_json(bl.STATE_DIR / "nightly.json"),
                          "heartbeat": bl.read_json(bl.STATE_DIR / "nightly.heartbeat")}, indent=1))
        return 0
    if args.cmd == "rehearse":
        print(json.dumps(run_real(dt.date.fromisoformat(args.day), rehearsal_gate=args.gate_box), indent=1, default=str))
        return 0
    if args.cmd == "schedule":
        # A scheduled wake cannot reserve tomorrow's dollars. After the burst the House daemon
        # owns wake/sleep under that day's ledger and exclusive operation lease.
        import boxlib as bl
        from league.swarm import settings as swarm_settings
        from league.swarm.lifecycle import Lifecycle
        from league.swarm.store import SwarmStore
        root = bl.STATE_DIR.parent
        cfg = swarm_settings.load(root)
        burst = time.time() < dt.datetime.fromisoformat(cfg["guard"]["burst_until"].replace("Z", "+00:00")).timestamp()
        if (root / "swarm.sqlite").exists():
            store = SwarmStore(root, clock=time.time)
            try:
                burst = Lifecycle(store, cfg).burst()
            finally:
                store.close()
        if not burst:
            print("the House nightly controller will wake the data box after reserving the current period's budget")
            return 0
        job = real_job()
        if job.data.backfill_running():
            print("the backfill is running; the data box stays awake")
            return 0
        wake = next_wake(dt.datetime.now(dt.timezone.utc), job.calendar).strftime("%Y-%m-%dT%H:%M:%SZ")
        job.data.sleep(wake)
        job.data.flush_sleep()
        print(f"the data box sleeps until {wake}")
        return 0
    day = dt.date.fromisoformat(args.day) if args.day else None
    print(json.dumps(run_real(day, dry_run=args.dry_run), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
