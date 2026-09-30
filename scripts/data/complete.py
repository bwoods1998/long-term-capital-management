#!/usr/bin/env python3
"""Resumable completion of the full store and its private images, supervised by nightly.py.

Opt in with `<state>/completion-config.json`: {"enabled": true}. The worker waits for all
ThetaData stages, scans SIP bars in at most 31-day chunks, and retains unresolved root-days in
`sip-progress.sqlite`. Only a complete, reverified queue can build images and emit images-ready.
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
from sip_progress import Progress, SCHEMA, digest

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

    def sip_plan(self, *, hash_files=False) -> dict:
        command = f'backfill.py sip-plan --start {sl.TRAIN[0]} --end {sl.HOLDOUT[1]}'
        ok, output = self.data.run(command + (' --hash-files' if hash_files else ''), timeout=1800)
        if not ok:
            raise RuntimeError('could not read the historical SIP plan/file identities')
        return json.loads(output.strip().splitlines()[-1])

    def _relay_days(self, days, progress, calendar, check_lease):
        from sip import relay_day, status_day

        for day in days:
            check_lease()
            if sl.in_quiet(dt.datetime.now(dt.timezone.utc), 600):
                raise RuntimeError('historical SIP deferred for the nightly quiet window')
            recovery = progress.reserve_recovery(str(day))
            try:
                status = status_day(self.data, day)
                due = progress.reserve(str(day), status['roots'])
            except Exception as error:
                progress.recovery_result(str(day), recovery, error=f'{type(error).__name__}: {str(error)[:200]}')
                raise
            progress.recovery_result(str(day), recovery, rows=status['roots'])
            if due:
                try:
                    result = relay_day(day, self.data, calendar=calendar, source_root=sl.source_root,
                                       roots=due, verified=status, allow_gaps=True, check_lease=check_lease)
                except Exception as error:
                    progress.record(str(day), [{**r, 'complete': False, 'status': 'error', 'uncertain_write': True,
                                                'error': f'{type(error).__name__}: {str(error)[:200]}'}
                                               for r in status['roots'] if r['root'] in due])
                    raise
                progress.record(str(day), result['coverage'])
            progress.scanned(str(day))

    def relay_chunk(self, start: dt.date, end: dt.date) -> dict:

        if (end - start).days >= 31:
            raise ValueError("SIP chunks span at most 31 calendar days")
        self.data.wake()
        with bl.RemoteLease(self.api, self.data.box_id) as lease:
            if self.data.backfill_running():
                raise RuntimeError("a backfill restarted; wait for it before historical SIP ingestion")
            lease.check()
            bl.push_code(self.api, self.data.box_id)
            calendar = sl.Calendar.from_json(json.loads(self.data.download("/data/work/calendar.json"))["exceptions"])
            days = list(calendar.days(start, end))
            with Progress(self.state / 'sip-progress.sqlite', self.sip_plan()['plan']) as progress:
                self._relay_days(days, progress, calendar, lease.check)
                summary = progress.summary()
        return {"start": start.isoformat(), "end": end.isoformat(), "trading_days": len(days), **summary}

    def retry_gaps(self) -> dict:
        with Progress.existing(self.state / 'sip-progress.sqlite') as progress:
            if not progress.due_days():
                return progress.summary()  # deferred/backoff queues do not wake the box or query a provider
        self.data.wake()
        with bl.RemoteLease(self.api, self.data.box_id) as lease:
            if self.data.backfill_running():
                raise RuntimeError('a backfill restarted; wait before historical SIP retries')
            lease.check()
            bl.push_code(self.api, self.data.box_id)
            calendar = sl.Calendar.from_json(json.loads(self.data.download('/data/work/calendar.json'))['exceptions'])
            with Progress(self.state / 'sip-progress.sqlite', self.sip_plan()['plan']) as progress:
                self._relay_days([dt.date.fromisoformat(d) for d in progress.due_days()], progress, calendar, lease.check)
                return progress.summary()

    def _sip_ready(self) -> dict:
        current = self.sip_plan(hash_files=True)
        with Progress(self.state / 'sip-progress.sqlite', current['plan']) as progress:
            progress.compare_files(current['files'])
            return {**progress.summary(), 'verified_at': bl.now(), 'source_box_id': self.data.box_id,
                    'scope': 'historical_stock_underlying_completed_grid',
                    'start': str(sl.TRAIN[0]), 'end': str(sl.HOLDOUT[1]),
                    'windows': ['train', 'validation', 'holdout'], 'forward_excluded': True}

    def sip_ready(self) -> dict:
        self.data.wake()
        with bl.RemoteLease(self.api, self.data.box_id):
            if self.data.backfill_running():
                raise RuntimeError('a backfill restarted; cannot verify historical SIP readiness')
            return self._sip_ready()

    def build(self, kind: str, version: str, *, sip_receipt: str) -> dict:
        from images import build, KINDS

        roots = tuple(sorted(bl.read_json(self.state / 'universe.json').get('roots') or ()))
        spec = {'kind': kind, 'roots': list(roots), 'windows': list(KINDS[kind]['keep']),
                'train_from': None, 'root_first': None}

        def source_check(source_box: str):
            # images.build calls this under its existing lease, with the backfill stopped,
            # immediately before snapshotting the source. No price columns leave the box.
            if source_box != self.data.box_id:
                raise RuntimeError('staged image source differs from the verified SIP data box')
            status = self._sip_ready()
            if not status['complete'] or status.get('receipt_sha256') != sip_receipt:
                raise RuntimeError('historical SIP evidence changed before the image snapshot')
            return {'sip_receipt': sip_receipt, 'plan': status['plan'], 'source_box_id': source_box,
                    'verified_at': status['verified_at'], 'image_spec': spec,
                    'scope': status['scope'], 'start': status['start'], 'end': status['end'],
                    'coverage_windows': status['windows'], 'forward_excluded': True}

        with bl.using_state(self.staging()):
            if bl.data_box_id() != self.data.box_id:
                raise RuntimeError('staged image source differs from the verified SIP data box')
            if tuple(sorted(bl.read_json(bl.UNIVERSE).get('roots') or ())) != roots:
                raise RuntimeError('staged image universe differs from the requested root set')
            current = (bl.read_json(bl.IMAGES).get(kind) or {}).get("current") or {}
            evidence = current.get('source_evidence') or {}
            if (current.get("version") == version and len(current.get("checkpoints", [])) == 2 and current.get("verified")
                    and evidence.get('sip_receipt') == sip_receipt and evidence.get('source_box_id') == self.data.box_id):
                if (evidence.get('image_spec') == spec and current.get('roots') == list(roots)
                        and current.get('windows') == spec['windows'] and current.get('train_from') is None
                        and current.get('root_first') is None):
                    return current
            if not roots:
                raise RuntimeError("the full universe has not been recorded")
            return build(kind, version=version, force=False, needs=STAGES, roots=roots,
                         api=self.api, source_check=source_check)

    def calibrate(self, version: str, *, sip_receipt: str, pair: dict) -> dict:
        from calibration import prepare_pair

        def pair_check(source_box, entries):
            if source_box != self.data.box_id:
                raise RuntimeError('staged image source differs from the verified SIP data box')
            binding = {'input_pair': pair, 'sip_receipt': sip_receipt,
                       'source_evidence': {k: e.get('source_evidence') for k, e in entries.items()}}
            for kind, entry in entries.items():
                evidence = entry.get('source_evidence') or {}
                if (entry.get('version') not in (version.removesuffix('-calibrated'), version)
                        or evidence.get('sip_receipt') != sip_receipt or evidence.get('source_box_id') != self.data.box_id
                        or entry.get('box_id') != pair[kind]['box_id'] or evidence != pair[kind]['source_evidence']
                        or entry.get('roots') != pair[kind]['roots'] or entry.get('windows') != pair[kind]['windows']
                        or entry.get('train_from') is not None or entry.get('root_first') is not None):
                    raise RuntimeError('staged image pair is not bound to this verified SIP source receipt')
                if entry.get('checkpoints') != pair[kind]['checkpoints']:
                    # A partial calibration can change checkpoints repeatedly; its stable original
                    # input pair must survive independently of the checkpoint used for a later fit.
                    if entry.get('version') != version or (entry.get('calibration') or {}).get('pair_binding') != binding:
                        raise RuntimeError('staged image checkpoint changed without this calibration input-pair receipt')
            if pair['gym']['roots'] != pair['gate']['roots']:
                raise RuntimeError('staged image pair roots differ')
            return binding

        with bl.using_state(self.staging()):
            receipt = prepare_pair(version=version, api=self.api, pair_check=pair_check)
            return {**receipt, 'source_evidence': receipt['pair_binding']['source_evidence'], 'roots': pair['gym']['roots']}

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
        record = bl.read_json(self.state / "completion.json") or {"schema": SCHEMA, "phase": "theta"}
        version = str(config.get("version") or "full-20260926")
        requested = {'version': version, 'config': {k: v for k, v in config.items() if k != 'enabled'},
                     'source_box_id': bl.read_json(self.state / 'data_box.json').get('box_id'),
                     'coverage_schema': sl.SIP_COVERAGE_SCHEMA, 'source': sl.SIP_SOURCE,
                     'windows': [[str(d) for d in w] for w in (sl.TRAIN, sl.VALIDATION, sl.HOLDOUT)]}
        if record.get('schema') != SCHEMA:
            # SOURCE-only cursors may have skipped sparse files. Re-scan without deleting history/images.
            legacy = self.state / 'completion-legacy-sip-v1.json'
            if not legacy.exists():
                bl.write_json(legacy, record)
            ready = self.state / 'images-ready.json'
            if ready.exists():
                ready.replace(self.state / 'images-ready-legacy-sip-v1.json')
            record = {'schema': SCHEMA, 'phase': 'theta' if record['phase'] == 'theta' else 'sip',
                      'next_day': sl.TRAIN[0].isoformat(), 'migration': 'reverify legacy SOURCE-only receipts'}
        if record.get('requested') is not None and record['requested'] != requested:
            ready = self.state / 'images-ready.json'
            if ready.exists():
                ready.replace(self.state / ('images-ready-archived-' + digest(record['requested'])[:16] + '.json'))
            record.update(phase='review_required', desired_request=requested,
                          error='completion request changed; review a new adoption cycle in a new state directory')
            bl.write_json(self.state / 'completion.json', record)
            return record
        record.setdefault('requested', requested)
        if record.get('phase') == 'review_required':
            return record
        if record.get("phase") == "complete":
            # A certificate for immutable checkpoints, not a continuing claim about the mutable collection box.
            return record
        if float(record.get("retry_at", 0)) > self.clock():
            return record
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
                record['sip'] = record['last_chunk']
                record["next_day"] = (end + dt.timedelta(days=1)).isoformat()
                if end == sl.HOLDOUT[1]:
                    record["phase"] = "gym" if record['sip']['complete'] else 'sip_gaps'
            elif phase == 'sip_gaps':
                record['sip'] = ops.retry_gaps()
                if record['sip']['complete']:
                    record['phase'] = 'gym'
            elif phase in ("gym", "gate"):
                status = ops.sip_ready()
                record['sip'] = status
                if not status['complete']:
                    record['phase'] = 'sip_gaps'
                else:
                    receipt = status['receipt_sha256']
                    if record.get('sip_receipt') != receipt:
                        phase = 'gym'
                    record['sip_receipt'] = receipt
                    version += '-sip2-' + receipt[:12]
                    image = ops.build(phase, version, sip_receipt=receipt)
                    record[phase] = {k: image[k] for k in ('box_id', 'checkpoints', 'source_evidence', 'roots', 'windows')}
                    record["phase"] = "gate" if phase == "gym" else "calibrate"
            elif phase == "calibrate":
                status = ops.sip_ready()
                record['sip'] = status
                if not status['complete'] or status['receipt_sha256'] != record.get('sip_receipt'):
                    record['phase'] = 'gym' if status['complete'] else 'sip_gaps'
                    bl.write_json(self.state / 'completion.json', record)
                    return record
                version += '-sip2-' + record['sip_receipt'][:12]
                calibration = ops.calibrate(version + "-calibrated", sip_receipt=record['sip_receipt'],
                                            pair={k: record[k] for k in ('gym', 'gate')})
                wake = ops.schedule()
                ready = {"schema": SCHEMA, "ready_at": bl.now(), "version": version, 'sip': status,
                         'scope': 'immutable_staged_checkpoint_pair', 'requested': requested,
                         'source_evidence': calibration['source_evidence'],
                         "data_wake_at": wake,
                         "staged_records": str(self.state / "next-images"),
                         "gym_checkpoint": calibration["checkpoints"]["gym"][0],
                         "gate_checkpoint": calibration["checkpoints"]["gate"][0],
                         "checkpoints": calibration["checkpoints"],
                         "calibration": {key: calibration[key] for key in ("sha256", "model_version", "samples")},
                         "roots": calibration['roots']}
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
    parser.add_argument("command", choices=("step", "status", "reconsider"))
    parser.add_argument('--day', type=dt.date.fromisoformat)
    parser.add_argument('--root')
    parser.add_argument('--evidence', help='specific new data/provider evidence; identical reasons never reset attempts')
    args = parser.parse_args(argv)
    bl.configure_state(args.state)
    if args.command == "status":
        result = bl.read_json(args.state / "completion.json")
    else:
        from locking import process_lock

        with process_lock(args.state / "nightly.lock"):
            if args.command == 'reconsider':
                if not args.day or not args.root or not args.evidence:
                    parser.error('reconsider needs --day, --root and --evidence')
                with Progress.existing(args.state / 'sip-progress.sqlite') as progress:
                    changed = progress.reconsider(str(args.day), args.root, args.evidence)
                    result = {'reconsidered': changed, **progress.summary()}
            else:
                result = Completion(args.state).tick()
    print(json.dumps(result, sort_keys=True))
    return int(bool(result.get("error")))


if __name__ == "__main__":
    raise SystemExit(main())
