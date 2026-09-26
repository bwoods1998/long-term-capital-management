#!/usr/bin/env python3
"""The nightly forward job: yesterday's market into the data box's store and the gate image only.

    python3 scripts/data/nightly.py run [--day YYYY-MM-DD] [--dry-run]
    python3 scripts/data/nightly.py schedule        sleep the data box until the next 06:00Z wake
    python3 scripts/data/nightly.py status

`run` (idempotent; each step checks what is already done, so a rerun after any failure finishes
the night and a second run of a finished night does nothing):
  1. the day: the last trading day before today (ET), which must be a forward day (after the
     holdout's 2026-09-25) and at least 01:45 ET behind us (ThetaData serves the previous day from
     then);
  2. the data box: woken; the backfill stopped if it is running (ThetaData allows one session per
     account); `backfill.py run --stages 7 --forward-days DAY` pulls the day for the whole universe,
     then `--stages 8` its SPY/QQQ back months (resumable: a root already in the journal is not
     fetched again); the backfill restarted with its last arguments;
  3. the gate image: its box woken (or, when it is gone, forked from its current checkpoint and sealed
     again), each of the day's files downloaded from the data box and uploaded to the same path,
     `backfill.py adopt` there checks every sha256 and journals them, and the gate is re-checkpointed
     with a one-year TTL; the new checkpoint becomes `gate.current_checkpoint` in images.json;
  4. both boxes back to sleep (the data box only when no backfill runs), the data box with a wake
     at the next trading night's 06:00Z.

Forward days go to the gate image and never to a Gym box: the Gym image's box id is refused as a
target. The House calls this once a night; the owner's machine can run it by hand.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storelib as sl  # noqa: E402

WAKE_HOUR_UTC = 6
READY_ET_MINUTES = 105  # 01:45 ET


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
    """The next 06:00Z that follows a trading day (so there is a new day to pull)."""
    candidate = now.astimezone(dt.timezone.utc).replace(hour=WAKE_HOUR_UTC, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += dt.timedelta(days=1)
    while not calendar.is_trading((candidate - dt.timedelta(days=1)).date()):
        candidate += dt.timedelta(days=1)
    return candidate


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
                 clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)):
        self.data, self.gate, self.images, self.save = data, gate, images, save
        self.checkpoint = checkpoint
        self.calendar = calendar
        self.last_backfill_args = last_backfill_args
        self.gym_box_ids = set(gym_box_ids)
        self.log = log
        self.clock = clock

    def state(self, day: dt.date) -> dict[str, Any]:
        nights = self.images.setdefault("gate", {}).setdefault("forward_days", {})
        return nights.setdefault(day.isoformat(), {})

    def run(self, day: dt.date | None = None, *, dry_run: bool = False) -> dict[str, Any]:
        now = self.clock()
        day = day or target_day(now, self.calendar)
        if sl.window_of(day) != "forward":
            raise ValueError(f"{day} is {sl.window_of(day)}, not a forward day")
        if not self.calendar.is_trading(day):
            return {"day": day.isoformat(), "skipped": "not a trading day"}
        if getattr(self.gate, "box_id", None) in self.gym_box_ids:
            raise ValueError("the gate target is a Gym box: forward days never reach a Gym box")
        state = self.state(day)
        if state.get("checkpoint"):
            self.log(f"{day}: already done (gate checkpoint {state['checkpoint']})")
            return {"day": day.isoformat(), "already": True, **state}
        if dry_run:
            return {"day": day.isoformat(), "would": ["pull", "copy", "checkpoint"]}

        # 1. the pull, on the data box, with the backfill paused (one ThetaData session per account)
        self.data.wake()
        was_running = self.data.backfill_running()
        if was_running:
            self.data.stop_backfill()
        try:
            if not state.get("pulled"):
                for stage in (7, 8):  # the day's chains, then (needing them) the back months
                    ok, out = self.data.run(f"backfill.py run --stages {stage} --forward-days {day.isoformat()} "
                                            "--threads 8 --passes 3 --pause 120", timeout=5400)
                    if not ok:
                        raise RuntimeError(f"the forward pull (stage {stage}) failed: {out[-800:]}")
                state["pulled"] = self.clock().isoformat()
                self.save(self.images)
            ok, out = self.data.run(f"backfill.py records --date {day.isoformat()}", timeout=600)
            if not ok:
                raise RuntimeError(f"no records for {day}: {out[-400:]}")
            records = [json.loads(line) for line in out.splitlines() if line.strip().startswith("{")]
        finally:
            if was_running and self.last_backfill_args:
                self.data.start_backfill(self.last_backfill_args)
        files = [r for r in records if r.get("type") == "file"]
        if not files:
            raise RuntimeError(f"the data box holds no files for {day}")
        if any(r.get("window") != "forward" for r in files):
            raise RuntimeError("a record that is not a forward day was about to reach the gate")

        # 2. the copy, file by file, checked on arrival
        self.gate.wake()
        copied = 0
        for record in files:
            blob = self.data.download(f"{sl.STORE_ROOT}/{record['path']}")
            if hashlib.sha256(blob).hexdigest() != record["sha256"]:
                raise RuntimeError(f"{record['path']} changed on the way (sha256)")
            self.gate.upload(f"{sl.STORE_ROOT}/{record['path']}", blob, 0o644)
            copied += 1
        payload = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records).encode()
        records_path = f"/data/work/nightly-{day.isoformat()}.jsonl"
        self.gate.upload(records_path, payload, 0o644)
        ok, out = self.gate.run(f"backfill.py adopt --records {records_path}", timeout=1800)
        if not ok:
            raise RuntimeError(f"the gate refused the day: {out[-800:]}")
        state.update({"files": copied, "adopted": self.clock().isoformat(), "roots": sorted({r['root'] for r in files})})
        self.save(self.images)

        # 3. the gate's new checkpoint
        checkpoint = self.checkpoint()
        state["checkpoint"] = checkpoint
        gate = self.images.setdefault("gate", {})
        gate["current_checkpoint"] = checkpoint
        gate.setdefault("checkpoints", []).append({"id": checkpoint, "day": day.isoformat(), "at": self.clock().isoformat()})
        self.save(self.images)
        self.gate.sleep(None)
        if not self.data.backfill_running():
            self.data.sleep(next_wake(self.clock(), self.calendar).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.log(f"{day}: {copied} files to the gate; checkpoint {checkpoint}")
        return {"day": day.isoformat(), **state}


# ------------------------------------------------------------------------------ the real handles
class BoxHandle:
    def __init__(self, api: Any, box_id: str):
        self.api, self.box_id = api, box_id

    def status(self) -> str:
        return str((self.api.get(self.box_id) or {}).get("status") or "")

    def wake(self) -> None:
        import boxlib as bl

        bl.ensure_running(self.api, self.box_id)

    def sleep(self, wake_at: str | None) -> None:
        self.api.sleep(self.box_id, wake_at=wake_at)

    def run(self, args: str, timeout: int) -> tuple[bool, str]:
        import boxlib as bl

        result = bl.run_py(self.api, self.box_id, args, timeout=timeout)
        return result.ok, result.stdout if result.ok else result.output

    def download(self, path: str) -> bytes:
        return self.api.download(self.box_id, path, timeout=900)

    def upload(self, path: str, blob: bytes, mode: int) -> None:
        self.api.upload(self.box_id, path, blob, mode=mode, timeout=900)

    def backfill_running(self) -> bool:
        out = self.api.exec(self.box_id, ["bash", "-c", "p=$(cat /data/work/backfill.pid 2>/dev/null); "
                                                         "[ -n \"$p\" ] && kill -0 $p 2>/dev/null && echo yes || echo no"], timeout=60)
        return out.stdout.strip() == "yes"

    def stop_backfill(self) -> None:
        self.api.exec(self.box_id, ["bash", "-c", "p=$(cat /data/work/backfill.pid); kill -- -$p 2>/dev/null || kill $p; "
                                                  "for i in $(seq 1 60); do kill -0 $p 2>/dev/null || break; sleep 1; done; "
                                                  "pkill -f multiprocessing.spawn; true"], timeout=120)

    def start_backfill(self, args: str) -> None:
        import boxlib as bl

        command = (f"mkdir -p /data/work && cd {bl.CODE_DIR} && setsid nohup {bl.VENV_PY} backfill.py run {args} "
                   f">> /data/work/backfill.out 2>&1 < /dev/null &")
        self.api.exec(self.box_id, command, timeout=60, background=True)


def real_job() -> Nightly:
    import boxlib as bl

    api = bl.client()
    images = bl.read_json(bl.IMAGES)
    gate = (images.get("gate") or {}).get("current") or {}
    if not gate.get("box_id"):
        raise SystemExit("no gate image recorded in .data/gym/images.json; build it first (images.py build gate)")
    gym_ids = [e.get("box_id") for e in (images.get("gym") or {}).get("history", []) if e.get("box_id")]
    data = BoxHandle(api, bl.data_box_id())
    data.wake()
    bl.push_code(api, data.box_id)
    calendar_json = json.loads(api.download(data.box_id, "/data/work/calendar.json"))
    calendar = sl.Calendar.from_json(calendar_json["exceptions"])
    gate_handle = BoxHandle(api, gate["box_id"])
    last_args = (bl.read_json(bl.DATA_BOX).get("runs") or [{}])[-1].get("args")

    def checkpoint() -> str:
        from images import checkpoint_with_retry

        row = checkpoint_with_retry(api, gate["box_id"], name=f"ltcm-gate-{bl.now().replace(':', '')}",
                                    ttl_seconds=365 * 86400)
        return row["checkpoint_id"]

    return Nightly(data=data, gate=gate_handle, images=images, save=lambda d: bl.write_json(bl.IMAGES, d),
                   checkpoint=checkpoint, calendar=calendar, last_backfill_args=last_args, gym_box_ids=gym_ids)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--day", default=None)
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("schedule")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    if args.cmd == "status":
        import boxlib as bl

        print(json.dumps((bl.read_json(bl.IMAGES).get("gate") or {}).get("forward_days", {}), indent=1))
        return 0
    job = real_job()
    if args.cmd == "schedule":
        if job.data.backfill_running():
            print("the backfill is running; the data box stays awake")
            return 0
        wake = next_wake(dt.datetime.now(dt.timezone.utc), job.calendar).strftime("%Y-%m-%dT%H:%M:%SZ")
        job.data.sleep(wake)
        print(f"the data box sleeps until {wake}")
        return 0
    day = dt.date.fromisoformat(args.day) if args.day else None
    print(json.dumps(job.run(day, dry_run=args.dry_run), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
