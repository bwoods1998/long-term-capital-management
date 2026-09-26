#!/usr/bin/env python3
"""Resumable completion of the full store and its private images, supervised by nightly.py.

Opt in with `<state>/completion-config.json`: {"enabled": true}. The worker waits for all
ThetaData stages, relays completed SIP bars in at most 31-day chunks, builds both images without
forcing missing data, calibrates on the sealed Gym, and emits `<state>/images-ready.json`.
It never changes swarm.json or selects an image for the House. `step` is also callable by hand.

    python3 scripts/data/complete.py --state /workspace/state/data step|status
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boxlib as bl
import storelib as sl

STAGES = (1, 2, 3, 4, 5, 6)


def theta_ready(progress: dict, running: bool) -> bool:
    stages = progress.get("stages") or {}
    return not running and all(isinstance(stages.get(str(stage)), dict)
                               and int(stages[str(stage)].get("planned", 0)) > 0
                               and int(stages[str(stage)].get("done", 0)) == int(stages[str(stage)]["planned"])
                               and int(stages[str(stage)].get("failing", 0)) == 0 for stage in STAGES)


class Operations:
    def __init__(self):
        from nightly import BoxHandle

        self.api = bl.client()
        self.data = BoxHandle(self.api, bl.data_box_id())
        self.state = bl.STATE_DIR

    def staging(self) -> Path:
        target = self.state / "next-images"
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in ("data_box.json", "calendar.json", "universe.json", "images.json"):
            if not (target / name).exists():
                value = bl.read_json(self.state / name)
                if value:
                    bl.write_json(target / name, value)
        return target

    def theta_status(self) -> dict:
        self.data.wake()
        progress = json.loads(self.data.download("/data/work/progress.json"))
        running = self.data.backfill_running()
        resumed = False
        if not running and not theta_ready(progress, False):
            # The vendor runner intentionally exits after a bounded set of retries. A transient
            # outage must not strand completion forever with an incomplete, idle queue.
            with bl.RemoteLease(self.api, self.data.box_id) as lease:
                progress = json.loads(self.data.download("/data/work/progress.json"))
                running = self.data.backfill_running()
                if not running and not theta_ready(progress, False):
                    args = (bl.read_json(bl.DATA_BOX).get("runs") or [{}])[-1].get("args")
                    if not args:
                        raise RuntimeError("incomplete backfill has no recorded restart arguments")
                    lease.check()
                    self.data.start_backfill(args)
                    running, resumed = self.data.backfill_running(), True
        ready = theta_ready(progress, running)
        if ready:
            universe = json.loads(self.data.download("/data/work/universe.json"))
            # Rank/spread measurements stay on the data box. Only root identities are needed here.
            bl.write_json(bl.UNIVERSE, {key: universe[key] for key in ("core", "names", "roots")})
        return {"ready": ready, "running": running, "resumed": resumed,
                "stages": progress.get("stages", {}), "at": progress.get("at")}

    def relay_chunk(self, start: dt.date, end: dt.date) -> dict:
        from sip import relay_day

        if (end - start).days >= 31:
            raise ValueError("SIP chunks span at most 31 calendar days")
        self.data.wake()
        with bl.RemoteLease(self.api, self.data.box_id):
            if self.data.backfill_running():
                raise RuntimeError("a backfill restarted; wait for it before historical SIP ingestion")
            bl.push_code(self.api, self.data.box_id)
            calendar = sl.Calendar.from_json(json.loads(self.data.download("/data/work/calendar.json"))["exceptions"])
            count = 0
            for day in calendar.days(start, end):
                relay_day(day, self.data, calendar=calendar, source_root=sl.source_root)
                count += 1
        return {"start": start.isoformat(), "end": end.isoformat(), "trading_days": count}

    def build(self, kind: str, version: str) -> dict:
        from images import build

        with bl.using_state(self.staging()):
            current = (bl.read_json(bl.IMAGES).get(kind) or {}).get("current") or {}
            if current.get("version") == version and len(current.get("checkpoints", [])) == 2 and current.get("verified"):
                return current
            universe = bl.read_json(bl.UNIVERSE)
            roots = tuple(universe.get("roots") or ())
            if not roots:
                raise RuntimeError("the full universe has not been recorded")
            return build(kind, version=version, force=False, needs=STAGES, roots=roots)

    def calibrate(self, version: str) -> dict:
        from calibration import prepare_pair

        with bl.using_state(self.staging()):
            return prepare_pair(version=version)

    def schedule(self) -> str:
        from nightly import next_wake

        self.data.wake()
        with bl.RemoteLease(self.api, self.data.box_id):
            if self.data.backfill_running():
                raise RuntimeError("a backfill is running; cannot put the data box to sleep")
            calendar = sl.Calendar.from_json(json.loads(self.data.download("/data/work/calendar.json"))["exceptions"])
            wake = next_wake(dt.datetime.now(dt.timezone.utc), calendar).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.data.sleep(wake)  # the data-box lock holder must exit before sleep
        return wake


class Completion:
    def __init__(self, state: Path, *, operations: Any = None, clock: Callable[[], float] = time.time):
        self.state, self.operations, self.clock = state, operations, clock

    def tick(self) -> dict:
        config = bl.read_json(self.state / "completion-config.json")
        if config.get("enabled") is not True:
            return {"phase": "disabled"}
        record = bl.read_json(self.state / "completion.json") or {"schema": 1, "phase": "theta"}
        if record.get("phase") == "complete":
            return record
        if float(record.get("retry_at", 0)) > self.clock():
            return record
        version = str(config.get("version") or "full-20260926")
        phase = record["phase"]
        try:
            ops = self.operations or Operations()
            if phase == "theta":
                status = ops.theta_status()
                record["theta"] = status
                if status["ready"]:
                    record.update({"phase": "sip", "next_day": sl.TRAIN[0].isoformat()})
            elif phase == "sip":
                start = dt.date.fromisoformat(record["next_day"])
                end = min(start + dt.timedelta(days=30), sl.HOLDOUT[1])
                record["last_chunk"] = ops.relay_chunk(start, end)
                record["next_day"] = (end + dt.timedelta(days=1)).isoformat()
                if end == sl.HOLDOUT[1]:
                    record["phase"] = "gym"
            elif phase in ("gym", "gate"):
                image = ops.build(phase, version)
                record[phase] = {"box_id": image["box_id"], "checkpoints": image["checkpoints"]}
                record["phase"] = "gate" if phase == "gym" else "calibrate"
            elif phase == "calibrate":
                calibration = ops.calibrate(version + "-calibrated")
                wake = ops.schedule()
                ready = {"schema": 1, "ready_at": bl.now(), "version": version,
                         "data_wake_at": wake,
                         "staged_records": str(self.state / "next-images"),
                         "gym_checkpoint": calibration["checkpoints"]["gym"][0],
                         "gate_checkpoint": calibration["checkpoints"]["gate"][0],
                         "checkpoints": calibration["checkpoints"],
                         "calibration": {key: calibration[key] for key in ("sha256", "model_version", "samples")},
                         "roots": bl.read_json(bl.UNIVERSE).get("roots", [])}
                bl.write_json(self.state / "images-ready.json", ready)
                record.update({"phase": "complete", "ready": ready})
            else:
                raise ValueError("unrecognized completion phase")
            record.update({"error": None, "retry_at": 0, "updated_at": bl.now()})
        except (Exception, SystemExit) as error:
            record.update({"error": f"{type(error).__name__}: {str(error)[:500]}",
                           "retry_at": self.clock() + 300, "updated_at": bl.now()})
        bl.write_json(self.state / "completion.json", record)
        return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("command", choices=("step", "status"))
    args = parser.parse_args(argv)
    bl.configure_state(args.state)
    if args.command == "status":
        result = bl.read_json(args.state / "completion.json")
    else:
        from locking import process_lock

        with process_lock(args.state / "nightly.lock"):
            result = Completion(args.state).tick()
    print(json.dumps(result, sort_keys=True))
    return int(bool(result.get("error")))


if __name__ == "__main__":
    raise SystemExit(main())
