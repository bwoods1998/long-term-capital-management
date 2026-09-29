#!/usr/bin/env python3
"""The long history fetch's controller: keep a backfill of the private blocks (stages 11 and up) running outside the
nightly job's quiet window, and resume it only after the night's forward day is checkpointed.

    python3 scripts/data/window.py --state /workspace/state/data enable --blocks-file F --args "..." [--not-before ISO]
    python3 scripts/data/window.py --state /workspace/state/data loop [--every 60]     (detached; one at a time)
    python3 scripts/data/window.py --state /workspace/state/data tick | status
    python3 scripts/data/window.py --state /workspace/state/data disable [--stop]

The record is `<state>/backfill-window/window.json`, next to the blocks file (`blocks.json`, uploaded to the data box
as `/data/work/blocks.json`, mode 600) and a log (`window.log`); the directory is the owner's only. Once the nightly
daemon runs a release with this module it calls `daemon_tick` every poll, in its own thread, so the pause, the nightly
pull and the resume are strictly sequential. Until then (or instead) a standalone `loop` holds `window.lock`, and the
daemon leaves the ticks to it.

Each tick, never raising:
  - inside the quiet window (from `BACKSTOP_SECONDS` before it): stop a running backfill under the data-operation
    lease. A backstop: the runner, started with `--nightly-quiet`, has already stopped before the window;
  - outside it: wake the data box. When no backfill runs, judge the last run this controller started from its exit
    receipt: 0 is complete; 75 was deferred by the window; anything else counts toward a stall when the run finished
    no new block task, and after `STALL_RUNS` such runs in a row the phase is `stalled` and nothing restarts. Then, once
    the nightly has no due day unfinished, is not busy and has a fresh heartbeat, push this code, upload the blocks file
    and start the recorded arguments under the lease.
Only runs this controller started are judged. The House's own recorded backfill arguments (`data_box.json` runs) are
never read or written, so the nightly and the completion supervisor never restart this run with other code.
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
import uuid
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storelib as sl  # noqa: E402

DIR_NAME = "backfill-window"
REMOTE_BLOCKS = "/data/work/blocks.json"
#: The controller's own stop, this long before the quiet window (the runner stops 10 minutes before it).
BACKSTOP_SECONDS = 180
#: No run starts this close to the quiet window (it would stop at once).
START_LEAD_SECONDS = 1200
#: Runs in a row that end without finishing a new block task before the fetch is `stalled`.
STALL_RUNS = 2
#: After a run that failed (not complete, not deferred), wait this long before starting again.
RETRY_SECONDS = 1800
#: The nightly daemon's heartbeat must be this fresh for a start.
HEARTBEAT_STALE_SECONDS = 900
KEEP_STARTS = 60


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text: str) -> dt.datetime:
    """An ISO time, `Z` or an offset, as aware UTC (never compared as strings)."""
    value = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError(f"{text!r} has no time zone")
    return value.astimezone(dt.timezone.utc)


def directory(state: Path) -> Path:
    return Path(state) / DIR_NAME


def block_stages(args: str) -> list[int]:
    """The block stages a run's arguments plan. The arguments must plan at least one block from the uploaded blocks
    file and pass --nightly-quiet; they may not name forward days (the nightly's own stages)."""
    parts = shlex.split(args)

    def value(flag: str) -> str | None:
        if flag in parts:
            index = parts.index(flag)
            return parts[index + 1] if index + 1 < len(parts) else None
        for part in parts:
            if part.startswith(flag + "="):
                return part.split("=", 1)[1]
        return None

    if "--nightly-quiet" not in parts:
        raise ValueError("the fetch's arguments must include --nightly-quiet")
    if value("--blocks") != REMOTE_BLOCKS:
        raise ValueError(f"the fetch's arguments must read the uploaded blocks file: --blocks {REMOTE_BLOCKS}")
    if value("--forward-days") or any(p.startswith("--forward-days") for p in parts):
        raise ValueError("forward days are the nightly job's, never the history fetch's")
    stages = [int(s) for s in (value("--stages") or "").split(",") if s.strip()]
    if any(s in (7, 8) for s in stages):
        raise ValueError("stages 7 and 8 are the nightly job's")
    blocks = [s for s in stages if s >= sl.FIRST_BLOCK_STAGE]
    if not blocks:
        raise ValueError("the fetch's --stages name no block (stage 11 and up)")
    return blocks


def block_done(progress: dict[str, Any] | None, stages: list[int]) -> int | None:
    """Finished block tasks in a progress file, or None when it is not this fetch's (e.g. the nightly's)."""
    rows = (progress or {}).get("stages") or {}
    if not stages or any(str(s) not in rows for s in stages):
        return None
    return sum(int(rows[str(s)].get("done", 0)) for s in stages)


class Ops:
    """The real handles: the data box through the Sail API, and the nightly's records on this host."""

    def __init__(self, state: Path):
        import boxlib as bl
        from nightly import BoxHandle

        self.state = Path(state)
        self.api = bl.client()
        self.box = bl.data_box_id()
        self.data = BoxHandle(self.api, self.box)

    def awake(self) -> bool:
        return self.data.status() == "running"

    def wake(self) -> None:
        self.data.wake()

    def running(self) -> bool:
        return self.data.backfill_running()

    def stop(self) -> None:
        self.data.stop_backfill()

    def receipt(self, path: str) -> int | None:
        return self.data.receipt(path)

    def progress(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.api.download(self.box, "/data/work/progress.json"))
        except Exception:  # noqa: BLE001 - informative only
            return None

    def lease(self) -> Any:
        import boxlib as bl

        return bl.RemoteLease(self.api, self.box)

    def start(self, args: str, blocks: bytes) -> str:
        import boxlib as bl

        bl.push_code(self.api, self.box)
        self.api.upload(self.box, REMOTE_BLOCKS, blocks, mode=0o600)
        return self.data.start_backfill(args)

    def nightly_ready(self, now: dt.datetime) -> tuple[bool, str]:
        import boxlib as bl
        from nightly import due_days

        record = bl.read_json(self.state / "nightly.json")
        calendar = sl.Calendar.from_json(json.loads((self.state / "calendar.json").read_text())["exceptions"])
        pending = due_days(now, calendar, record.get("completed", {}))
        if pending:
            return False, f"the nightly has not finished {pending[0].isoformat()} ({len(pending)} due)"
        beat = bl.read_json(self.state / "nightly.heartbeat")
        if not beat:
            return False, "no nightly heartbeat"
        if now.timestamp() - float(beat.get("at") or 0) > HEARTBEAT_STALE_SECONDS:
            return False, "the nightly daemon's heartbeat is stale"
        if beat.get("busy"):
            return False, "the nightly job is running"
        return True, "the nightly is caught up"


class Window:
    def __init__(self, state: Path, *, ops: Callable[[], Any] | None = None,
                 clock: Callable[[], dt.datetime] | None = None):
        self.state = Path(state)
        self.dir = directory(self.state)
        self.record_path = self.dir / "window.json"
        self.blocks_path = self.dir / "blocks.json"
        self.ops_factory = ops or (lambda: Ops(self.state))
        self.clock = clock or (lambda: utcnow())

    def read(self) -> dict[str, Any]:
        try:
            return json.loads(self.record_path.read_text())
        except (OSError, ValueError):
            return {}

    def write(self, record: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.record_path.with_name(f"window.json.tmp-{uuid.uuid4().hex[:8]}")
        tmp.write_text(json.dumps(record, indent=1, sort_keys=True, default=str) + "\n")
        tmp.chmod(0o600)
        tmp.replace(self.record_path)

    def log(self, line: str) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            with open(self.dir / "window.log", "a") as handle:
                handle.write(f"{iso(self.clock())} {line}\n")
        except OSError:
            pass

    def tick(self) -> dict[str, Any]:
        record = self.read()
        if not record.get("enabled"):
            return {"phase": "disabled"}
        if record.get("phase") in ("complete", "stalled"):
            return record
        before = (record.get("phase"), record.get("why"), record.get("error"))
        now = self.clock()
        try:
            self._tick(record, now)
            record["error"] = None
        except (Exception, SystemExit) as error:  # noqa: BLE001 - a tick never raises into its caller
            record["error"] = f"{type(error).__name__}: {str(error)[:300]}"
            record["error_at"] = iso(now)
        record["checked_at"] = iso(now)
        record["starts"] = record.get("starts", [])[-KEEP_STARTS:]
        self.write(record)
        if (record.get("phase"), record.get("why"), record.get("error")) != before:
            self.log(f"phase={record.get('phase')} why={record.get('why')} error={record.get('error')}")
        return record

    def _tick(self, record: dict[str, Any], now: dt.datetime) -> None:
        ops = self.ops_factory()
        start, end = sl.next_quiet(now)
        starts = record.setdefault("starts", [])
        last = starts[-1] if starts else None
        if start - dt.timedelta(seconds=BACKSTOP_SECONDS) <= now < end:
            record["resume_after"] = iso(end)
            if ops.awake() and ops.running():
                with ops.lease():
                    if ops.running():
                        ops.stop()
                        record["paused_at"] = iso(now)
                        if last is not None:
                            last["stopped"] = "backstop before the quiet window"
                record.update(phase="paused", why="the nightly job's quiet window")
            else:
                record.update(phase="quiet", why="the nightly job's quiet window")
            return
        if not ops.awake():
            ops.wake()
        if ops.running():
            record.update(phase="running", why=None)
            return
        stages = [int(s) for s in record.get("stages") or []]
        if last is not None and last.get("ended_at") is None:
            code = ops.receipt(str(last.get("receipt")))
            done = block_done(ops.progress(), stages)
            last.update(ended_at=iso(now), exit=code, done_after=done if done is not None else last.get("done_before"))
            if code == 0:
                record.update(phase="complete", why="every planned task is done", completed_at=iso(now))
                self.log("complete")
                return
            if code != sl.QUIET_EXIT and not last.get("stopped"):
                before, after = last.get("done_before"), last.get("done_after")
                record["stalls"] = int(record.get("stalls", 0)) + 1 if (
                    before is not None and after is not None and after <= before) else 0
                record["retry_at"] = iso(now + dt.timedelta(seconds=RETRY_SECONDS))
                if record["stalls"] >= STALL_RUNS:
                    record.update(phase="stalled", stalled_at=iso(now),
                                  why=f"{STALL_RUNS} runs in a row ended (exit {code}) without finishing a block task")
                    self.log(record["why"])
                    return
            else:
                record.pop("retry_at", None)
        waits = []
        if record.get("not_before") and now < parse_time(record["not_before"]):
            waits.append(f"not before {record['not_before']}")
        if record.get("retry_at") and now < parse_time(record["retry_at"]):
            waits.append(f"retry after {record['retry_at']} (the last run failed)")
        if (start - now).total_seconds() < START_LEAD_SECONDS:
            waits.append("the quiet window is near")
        if waits:
            record.update(phase="waiting", why="; ".join(waits))
            return
        ready, why = ops.nightly_ready(now)
        if not ready:
            record.update(phase="waiting-nightly", why=why)
            return
        blocks = self.blocks_path.read_bytes()
        if hashlib.sha256(blocks).hexdigest() != record.get("blocks_sha256"):
            raise RuntimeError("the blocks file changed since `enable`; enable again")
        with ops.lease():
            if ops.running():
                record.update(phase="running", why=None)
                return
            done = block_done(ops.progress(), stages)
            if done is None and last is not None:
                done = last.get("done_after")
            receipt = ops.start(str(record["args"]), blocks)
        starts.append({"at": iso(now), "receipt": receipt, "done_before": done, "run_id": record.get("run_id")})
        record.update(phase="running", why=None, resumed_at=iso(now))
        record.pop("retry_at", None)
        self.log(f"started run {len(starts)} ({record.get('run_id')}); receipt {receipt}")


def enable(state: Path, blocks_file: Path, args: str, *, not_before: str | None = None,
           names: list[str] | None = None, clock: Callable[[], dt.datetime] = utcnow) -> dict[str, Any]:
    """Check and record a fetch. The blocks file is parsed with the universe's names and copied (mode 600)."""
    window = Window(state, clock=clock)
    current = window.read()
    if current.get("enabled") and current.get("phase") in ("running", "paused"):
        raise SystemExit("a fetch is active: `disable --stop` it first")
    stages = block_stages(args)
    raw = Path(blocks_file).read_bytes()
    if names is None:
        try:
            names = [str(n) for n in json.loads((Path(state) / "universe.json").read_text()).get("names", [])]
        except (OSError, ValueError):
            names = []
    blocks = sl.parse_blocks(json.loads(raw), names=names)
    missing = [s for s in stages if s not in blocks]
    if missing:
        raise SystemExit(f"stages {missing} have no block in {blocks_file}")
    if not_before:
        parse_time(not_before)
    window.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    window.dir.chmod(0o700)
    tmp = window.blocks_path.with_name("blocks.json.tmp")
    tmp.write_bytes(raw)
    tmp.chmod(0o600)
    tmp.replace(window.blocks_path)
    record = {"schema": 1, "enabled": True, "run_id": uuid.uuid4().hex[:12], "since": iso(clock()), "args": args,
              "stages": stages, "blocks_sha256": hashlib.sha256(raw).hexdigest(), "not_before": not_before,
              "phase": "waiting", "why": "enabled", "starts": [], "stalls": 0}
    if current:
        record["previous"] = {k: current.get(k) for k in ("run_id", "since", "phase", "why", "completed_at", "stalled_at")}
    window.write(record)
    window.log(f"enabled run {record['run_id']}: stages {stages}")
    return record


def disable(state: Path, *, stop: bool = False, ops: Callable[[], Any] | None = None) -> dict[str, Any]:
    window = Window(state, ops=ops)
    record = window.read()
    record.update(enabled=False, phase="disabled", why="disabled by the operator", disabled_at=iso(utcnow()))
    window.write(record)
    if stop:
        handle = window.ops_factory()
        if handle.awake() and handle.running():
            with handle.lease():
                if handle.running():
                    handle.stop()
                    record["stopped_at"] = iso(utcnow())
        window.write(record)
    window.log(f"disabled{' and stopped' if stop else ''}")
    return record


def daemon_tick(state: Path, *, ops: Callable[[], Any] | None = None) -> str | None:
    """The nightly daemon's hook: one tick when enabled and no standalone `loop` holds the controller's lock."""
    from locking import process_lock

    window = Window(state, ops=ops)
    if not window.read().get("enabled"):
        return None
    try:
        with process_lock(window.dir / "window.lock"):
            return str(window.tick().get("phase"))
    except RuntimeError as error:
        if "holds" in str(error):
            return "standalone"
        raise


def loop(state: Path, every: float = 60.0) -> int:
    from locking import process_lock

    window = Window(state)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    window.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with process_lock(window.dir / "window.lock"):
        (window.dir / "window.pid").write_text(str(os.getpid()))
        window.log("loop started")
        try:
            while not stop.is_set():
                record = window.tick()
                if not record.get("enabled") or record.get("phase") in ("complete", "stalled"):
                    window.log(f"loop ends: {record.get('phase')}")
                    break
                stop.wait(every)
        finally:
            (window.dir / "window.pid").unlink(missing_ok=True)
            window.log("loop stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", required=True, type=Path, help="the House's data records, e.g. /workspace/state/data")
    sub = parser.add_subparsers(dest="cmd", required=True)
    en = sub.add_parser("enable")
    en.add_argument("--blocks-file", required=True, type=Path)
    en.add_argument("--args", required=True, help="backfill.py run arguments, with --nightly-quiet and --blocks")
    en.add_argument("--not-before", default=None, help="no start before this ISO time")
    lp = sub.add_parser("loop")
    lp.add_argument("--every", type=float, default=60.0)
    sub.add_parser("tick")
    sub.add_parser("status")
    di = sub.add_parser("disable")
    di.add_argument("--stop", action="store_true", help="also stop a running backfill (under the lease)")
    args = parser.parse_args(argv)
    import boxlib as bl

    bl.configure_state(args.state)
    if args.cmd == "enable":
        print(json.dumps(enable(args.state, args.blocks_file, args.args, not_before=args.not_before), indent=1))
    elif args.cmd == "loop":
        return loop(args.state, args.every)
    elif args.cmd == "tick":
        from locking import process_lock

        window = Window(args.state)
        with process_lock(window.dir / "window.lock"):
            print(json.dumps(window.tick(), indent=1, default=str))
    elif args.cmd == "status":
        window = Window(args.state)
        now = utcnow()
        start, end = sl.next_quiet(now)
        print(json.dumps({"record": window.read(), "now": iso(now),
                          "quiet_window": [iso(start), iso(end)]}, indent=1, default=str))
    elif args.cmd == "disable":
        print(json.dumps(disable(args.state, stop=args.stop), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
