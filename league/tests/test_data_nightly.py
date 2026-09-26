"""The nightly forward job with fake boxes (scripts/data/nightly.py): the day it picks, the order of
its steps, idempotence after a finished or a failed night, and that forward days reach only the gate."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

import nightly as nt  # noqa: E402
import storelib as sl  # noqa: E402

UTC = dt.timezone.utc


def calendar():
    return sl.Calendar({dt.date(2026, 11, 26): None, dt.date(2026, 11, 27): (570, 780)})


class FakeData:
    def __init__(self, day, *, running=True, pull_ok=True):
        self.day = day
        self.running = running
        self.pull_ok = pull_ok
        self.calls = []
        self.files = {}
        self.pulled = False
        for root in ("SPY", "XSP"):
            for kind in ("nbbo", "underlying"):
                path = sl.rel_path(kind, root, day)
                self.files[f"{sl.STORE_ROOT}/{path}"] = f"{kind}-{root}".encode()

    def wake(self):
        self.calls.append("wake")

    def sleep(self, wake_at):
        self.calls.append(("sleep", wake_at))

    def backfill_running(self):
        return self.running

    def stop_backfill(self):
        self.calls.append("stop")
        self.running = False

    def start_backfill(self, args):
        self.calls.append(("start", args))
        self.running = True

    def run(self, args, timeout):
        self.calls.append(("run", args.split()[0], args.split()[1]))
        if args.startswith("backfill.py run"):
            assert not self.running, "the pull ran while the backfill held the ThetaData session"
            self.pulled = self.pull_ok
            return self.pull_ok, "" if self.pull_ok else "boom"
        if args.startswith("backfill.py records"):
            lines = []
            for full, blob in self.files.items():
                rel = full[len(sl.STORE_ROOT) + 1:]
                kind, root, _ = sl.parse_rel_path(rel)
                rec = sl.file_record(kind, root, self.day, rows=1, sha256=hashlib.sha256(blob).hexdigest(),
                                     size=len(blob), source="fake", fetched_at="t")
                lines.append(json.dumps(rec))
            return True, "\n".join(lines)
        return False, "unknown"

    def download(self, path):
        return self.files[path]


class FakeGate:
    box_id = "sb_gate"

    def __init__(self, fail_adopt=False):
        self.uploads = {}
        self.calls = []
        self.fail_adopt = fail_adopt

    def wake(self):
        self.calls.append("wake")

    def sleep(self, wake_at):
        self.calls.append("sleep")

    def upload(self, path, blob, mode):
        self.uploads[path] = blob

    def run(self, args, timeout):
        self.calls.append(("run", args))
        if self.fail_adopt:
            return False, "checksum mismatch"
        return True, "{}"


def job(data, gate, images, *, now, gym_ids=(), checkpoints=None):
    saved = []
    counter = checkpoints if checkpoints is not None else []

    def checkpoint():
        counter.append(f"sbcp_{len(counter) + 1:08d}")
        return counter[-1]

    return nt.Nightly(data=data, gate=gate, images=images, save=lambda d: saved.append(json.dumps(d)),
                      checkpoint=checkpoint, calendar=calendar(), last_backfill_args="--stages 1,2",
                      gym_box_ids=gym_ids, log=lambda text: None, clock=lambda: now), saved, counter


class TheDay(unittest.TestCase):
    def test_previous_trading_day_after_the_publication_time(self):
        cal = calendar()
        # Tuesday 06:00Z = 02:00 ET: Monday
        self.assertEqual(nt.target_day(dt.datetime(2026, 9, 29, 6, 0, tzinfo=UTC), cal), dt.date(2026, 9, 28))
        # Monday 06:00Z: Friday
        self.assertEqual(nt.target_day(dt.datetime(2026, 10, 5, 6, 0, tzinfo=UTC), cal), dt.date(2026, 10, 2))
        # 01:00 ET is too early
        with self.assertRaises(ValueError):
            nt.target_day(dt.datetime(2026, 9, 29, 5, 0, tzinfo=UTC), cal)
        # the day after Thanksgiving's half day: the half day itself
        self.assertEqual(nt.target_day(dt.datetime(2026, 11, 30, 7, 0, tzinfo=UTC), cal), dt.date(2026, 11, 27))

    def test_next_wake_follows_a_trading_day(self):
        cal = calendar()
        # Saturday 07:00Z -> Tuesday 06:00Z (Sunday and Monday mornings follow no trading day)
        self.assertEqual(nt.next_wake(dt.datetime(2026, 10, 3, 7, 0, tzinfo=UTC), cal),
                         dt.datetime(2026, 10, 6, 6, 0, tzinfo=UTC))
        # Monday 20:00Z -> Tuesday 06:00Z
        self.assertEqual(nt.next_wake(dt.datetime(2026, 9, 28, 20, 0, tzinfo=UTC), cal),
                         dt.datetime(2026, 9, 29, 6, 0, tzinfo=UTC))

    def test_winter_runs_after_publication_and_outages_catch_up(self):
        cal = calendar()
        self.assertEqual(nt.next_wake(dt.datetime(2026, 11, 2, 20, 0, tzinfo=UTC), cal),
                         dt.datetime(2026, 11, 3, 7, 0, tzinfo=UTC))
        self.assertEqual(nt.due_days(dt.datetime(2026, 9, 29, 5, 59, tzinfo=UTC), cal), [])
        self.assertEqual(nt.due_days(dt.datetime(2026, 9, 29, 6, 0, tzinfo=UTC), cal), [dt.date(2026, 9, 28)])
        self.assertEqual(nt.due_days(dt.datetime(2026, 10, 1, 6, 0, tzinfo=UTC), cal, ["2026-09-28"]),
                         [dt.date(2026, 9, 29), dt.date(2026, 9, 30)])


class Night(unittest.TestCase):
    NOW = dt.datetime(2026, 9, 29, 6, 5, tzinfo=UTC)
    DAY = dt.date(2026, 9, 28)

    def test_a_night_in_order_then_nothing_the_second_time(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        nightly, saved, checkpoints = job(data, gate, images, now=self.NOW)
        result = nightly.run()
        self.assertEqual(result["day"], "2026-09-28")
        self.assertEqual(data.calls[:2], ["wake", "stop"])  # the backfill yields the ThetaData session
        self.assertIn(("start", "--stages 1,2"), data.calls)  # and gets it back
        runs = [i for i, c in enumerate(data.calls) if c == ("run", "backfill.py", "run")]
        self.assertEqual(len(runs), 2)  # stage 7, then stage 8
        self.assertLess(runs[-1], data.calls.index(("start", "--stages 1,2")))
        self.assertEqual(len(gate.uploads), 5)  # four files and the records
        self.assertEqual(gate.uploads[f"{sl.STORE_ROOT}/nbbo/SPY/2026-09-28.parquet"], b"nbbo-SPY")
        self.assertIn(("run", "backfill.py adopt --records /data/work/nightly-2026-09-28.jsonl"), gate.calls)
        self.assertEqual(images["gate"]["current_checkpoint"], checkpoints[-1])
        self.assertEqual(gate.calls[-1], "sleep")
        # the second run of the same night does nothing at all
        data.calls.clear()
        gate.uploads.clear()
        again = nightly.run()
        self.assertTrue(again["already"])
        self.assertEqual(data.calls, [])
        self.assertEqual(gate.uploads, {})
        self.assertEqual(len(checkpoints), 1)

    def test_a_failed_pull_restarts_the_backfill_and_is_retried_next_run(self):
        data, gate, images = FakeData(self.DAY, pull_ok=False), FakeGate(), {}
        nightly, _, checkpoints = job(data, gate, images, now=self.NOW)
        with self.assertRaises(RuntimeError):
            nightly.run()
        self.assertTrue(data.running)  # the backfill got its session back
        self.assertEqual(gate.uploads, {})
        self.assertEqual(checkpoints, [])
        data.pull_ok = True
        result = nightly.run()
        self.assertTrue(result["checkpoint"])

    def test_sip_relay_runs_before_restart_and_failure_keeps_day_pending(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        nightly, _, checkpoints = job(data, gate, images, now=self.NOW)
        def relay(day, handle):
            self.assertEqual(day, self.DAY)
            self.assertIs(handle, data)
            self.assertFalse(data.running)
            raise RuntimeError("missing SIP bars")
        nightly.relay = relay
        with self.assertRaises(RuntimeError):
            nightly.run()
        self.assertTrue(data.running)
        self.assertEqual(checkpoints, [])
        self.assertNotIn("pulled", nightly.state(self.DAY))

    def test_a_refused_adoption_is_not_checkpointed_and_the_pull_is_not_repeated(self):
        data, gate, images = FakeData(self.DAY), FakeGate(fail_adopt=True), {}
        nightly, _, checkpoints = job(data, gate, images, now=self.NOW)
        with self.assertRaises(RuntimeError):
            nightly.run()
        self.assertEqual(checkpoints, [])
        gate.fail_adopt = False
        data.calls.clear()
        nightly.run()
        self.assertNotIn(("run", "backfill.py", "run"), data.calls)  # the day was already pulled
        self.assertEqual(len(checkpoints), 1)

    def test_a_changed_file_is_refused(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        nightly, _, _ = job(data, gate, images, now=self.NOW)
        original = data.download
        data.download = lambda path: original(path) + b"x"
        with self.assertRaises(RuntimeError):
            nightly.run()

    def test_never_a_gym_box_never_a_holdout_day(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        nightly, _, _ = job(data, gate, images, now=self.NOW, gym_ids=["sb_gate"])
        with self.assertRaises(ValueError):
            nightly.run()
        nightly, _, _ = job(FakeData(dt.date(2026, 9, 25)), FakeGate(), {}, now=self.NOW)
        with self.assertRaises(ValueError):
            nightly.run(dt.date(2026, 9, 25))

    def test_explicit_days_cannot_bypass_the_publication_time(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        nightly, _, _ = job(data, gate, images, now=self.NOW - dt.timedelta(minutes=30))
        with self.assertRaises(ValueError):
            nightly.run(self.DAY)
        self.assertEqual(data.calls, [])

    def test_running_backfill_needs_restart_arguments_before_stopping(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        nightly, _, _ = job(data, gate, images, now=self.NOW)
        nightly.last_backfill_args = None
        with self.assertRaises(RuntimeError):
            nightly.run()
        self.assertTrue(data.running)
        self.assertNotIn("stop", data.calls)

    def test_a_missing_underlying_is_not_checkpointed(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        data.files.pop(f"{sl.STORE_ROOT}/underlying/SPY/{self.DAY}.parquet")
        nightly, _, checkpoints = job(data, gate, images, now=self.NOW)
        with self.assertRaises(RuntimeError):
            nightly.run()
        self.assertEqual(checkpoints, [])
        self.assertNotIn("pulled", images["gate"]["forward_days"][str(self.DAY)])

    def test_a_mismatched_record_path_is_not_uploaded(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        old = data.run
        def run(args, timeout):
            ok, out = old(args, timeout)
            if args.startswith("backfill.py records"):
                rows = [json.loads(line) for line in out.splitlines()]
                rows[0]["path"] = "nbbo/../../escape/2026-09-28.parquet"
                out = "\n".join(json.dumps(row) for row in rows)
            return ok, out
        data.run = run
        nightly, _, checkpoints = job(data, gate, images, now=self.NOW)
        with self.assertRaises(RuntimeError):
            nightly.run()
        self.assertEqual(gate.uploads, {})

    def test_a_holiday_is_skipped(self):
        data, gate, images = FakeData(dt.date(2026, 11, 26)), FakeGate(), {}
        nightly, _, _ = job(data, gate, images, now=self.NOW)
        self.assertEqual(nightly.run(dt.date(2026, 11, 26))["skipped"], "not a trading day")
        self.assertEqual(data.calls, [])

    def test_the_data_box_sleeps_until_the_next_night_when_idle(self):
        data, gate, images = FakeData(self.DAY, running=False), FakeGate(), {}
        nightly, _, _ = job(data, gate, images, now=self.NOW)
        nightly.run()
        self.assertEqual(data.calls[-1], ("sleep", "2026-09-30T06:00:00Z"))


class ForwardStage(unittest.TestCase):
    def test_stage_eight_is_the_back_months_after_the_day(self):
        tasks = sl.plan(calendar(), stages=(7, 8), forward=[dt.date(2026, 9, 28)])
        eight = [t for t in tasks if t.stage == 8]
        self.assertEqual({(t.root, t.job) for t in eight}, {("SPY", "back"), ("QQQ", "back")})
        self.assertGreater(tasks.index(eight[0]), max(i for i, t in enumerate(tasks) if t.stage == 7))

    def test_stage_seven_is_the_universe_on_forward_days_only(self):
        tasks = sl.plan(calendar(), stages=(7,), names=["TSLA"], forward=[dt.date(2026, 9, 28)])
        self.assertEqual({t.root for t in tasks}, set(sl.CORE_FIVE) | {"TSLA"})
        self.assertTrue(all(t.window == "forward" for t in tasks))
        with self.assertRaises(ValueError):
            sl.plan(calendar(), stages=(7,), forward=[dt.date(2026, 9, 25)])


if __name__ == "__main__":
    unittest.main()


class Rehearsal(unittest.TestCase):
    def test_a_rehearsal_copies_a_holdout_day_without_a_pull_and_leaves_the_gate_record_alone(self):
        day = dt.date(2026, 9, 23)
        data = FakeData(day)
        gate, images = FakeGate(), {"gate": {"current_checkpoint": "sbcp_real"}}
        nightly, _, checkpoints = job(data, gate, images, now=dt.datetime(2026, 9, 26, 7, 0, tzinfo=UTC))
        nightly.rehearsal = True
        # FakeData stamps its records with the day's window: holdout here
        result = nightly.run(day)
        self.assertNotIn(("run", "backfill.py", "run"), data.calls)
        self.assertEqual(images["gate"]["current_checkpoint"], "sbcp_real")
        self.assertEqual(images["nightly_rehearsals"]["2026-09-23:sb_gate"]["checkpoint"], checkpoints[-1])
        self.assertTrue(result["checkpoint"])
        nightly.rehearsal = False
        with self.assertRaises(ValueError):
            nightly.run(day)

    def test_a_new_rehearsal_target_does_not_reuse_another_boxs_checkpoint(self):
        day = dt.date(2026, 9, 23)
        images = {}
        first, _, _ = job(FakeData(day), FakeGate(), images, now=dt.datetime(2026, 9, 26, 7, 0, tzinfo=UTC))
        first.rehearsal = True
        first.run(day)
        second_gate = FakeGate()
        second_gate.box_id = "sb_second_gate"
        second, _, _ = job(FakeData(day), second_gate, images, now=dt.datetime(2026, 9, 26, 7, 0, tzinfo=UTC))
        second.rehearsal = True
        self.assertNotIn("already", second.run(day))
        self.assertTrue(second_gate.uploads)


class Schedule(unittest.TestCase):
    def test_failed_day_retries_then_publishes_only_a_completed_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = [dt.datetime(2026, 9, 29, 6, 0, tzinfo=UTC)]
            calls = []
            def run(day):
                calls.append(day)
                if len(calls) == 1:
                    raise RuntimeError("vendor unavailable")
                return {"day": day.isoformat(), "checkpoint": "sbcp_new", "roots": ["SPY"]}
            controller = nt.Controller(root, root / "ready.json", calendar(), run=run, clock=lambda: now[0])
            self.assertEqual(controller.tick()["phase"], "retry")
            self.assertFalse((root / "ready.json").exists())
            self.assertEqual(controller.tick()["phase"], "retry")
            self.assertEqual(len(calls), 1)
            now[0] += dt.timedelta(minutes=5)
            self.assertEqual(controller.tick()["phase"], "complete")
            ready = json.loads((root / "ready.json").read_text())
            self.assertEqual((ready["day"], ready["gate_checkpoint"]), ("2026-09-28", "sbcp_new"))
            self.assertEqual((root / "ready.json").stat().st_mode & 0o777, 0o600)
            # A fresh controller resumes the durable completed record without replaying the day.
            again = nt.Controller(root, root / "ready.json", calendar(), run=run, clock=lambda: now[0])
            self.assertEqual(again.tick()["phase"], "waiting")
            self.assertEqual(len(calls), 2)

    def test_no_forward_day_before_tuesday_and_no_false_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def run(day):
                raise AssertionError("not due")
            controller = nt.Controller(root, root / "ready.json", calendar(), run=run,
                                       clock=lambda: dt.datetime(2026, 9, 26, 16, 0, tzinfo=UTC))
            self.assertEqual(controller.tick()["next_wake"], "2026-09-29T06:00:00+00:00")
            with self.assertRaises(ValueError):
                nt.publish_ready(root / "ready.json", {"day": "2026-09-28"}, controller.clock())
            self.assertFalse((root / "ready.json").exists())
