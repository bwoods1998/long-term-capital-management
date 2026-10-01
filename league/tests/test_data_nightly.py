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

    def test_lease_lost_during_checkpoint_never_publishes_or_reuses_success(self):
        data, gate, records = FakeData(self.DAY), FakeGate(), {}
        nightly, saved, checkpoints = job(data, gate, records, now=self.NOW)
        held = [True]
        def check():
            if not held[0]:
                raise RuntimeError("lease expired")
        def checkpoint():
            held[0] = False
            return "sbcp_unowned"
        nightly.check_lease, nightly.checkpoint = check, checkpoint
        with self.assertRaisesRegex(RuntimeError, "lease expired"):
            nightly.run()
        self.assertNotIn("checkpoint", nightly.state(self.DAY))
        self.assertNotIn("current_checkpoint", records["gate"])
        self.assertTrue(all("sbcp_unowned" not in value for value in saved))
        held[0] = True
        nightly.checkpoint = lambda: "sbcp_owned"
        self.assertEqual(nightly.run()["checkpoint"], "sbcp_owned")

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

    def test_cached_pulled_marker_cannot_bypass_current_sip_coverage(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        nightly, _, checkpoints = job(data, gate, images, now=self.NOW)
        nightly.state(self.DAY)['pulled'] = 'legacy source-only marker'
        def incomplete(day, handle):
            self.assertEqual(day, self.DAY)
            self.assertIs(handle, data)
            raise RuntimeError('forward SIP coverage is incomplete')
        nightly.sip_check = incomplete
        with self.assertRaisesRegex(RuntimeError, 'coverage is incomplete'):
            nightly.run()
        self.assertNotIn('pulled', nightly.state(self.DAY))
        self.assertEqual(checkpoints, [])
        self.assertEqual(gate.uploads, {})

    def test_nightly_coverage_receipt_binds_the_exact_copied_hashes_and_roots(self):
        for alteration in ('none', 'hash', 'roots'):
            with self.subTest(alteration=alteration):
                data, gate, images = FakeData(self.DAY), FakeGate(), {}
                nightly, _, checkpoints = job(data, gate, images, now=self.NOW)
                def verified(day, handle):
                    pairs = sorted((sl.parse_rel_path(path.removeprefix(sl.STORE_ROOT + '/'))[1],
                                    hashlib.sha256(blob).hexdigest()) for path, blob in data.files.items()
                                   if '/underlying/' in path and '/XSP/' not in path)
                    proof = {'schema': sl.SIP_COVERAGE_SCHEMA, 'status': 'complete', 'day': str(day),
                             'roots': [r for r, _ in pairs],
                             'files_sha256': hashlib.sha256(json.dumps(pairs, sort_keys=True).encode()).hexdigest()}
                    if alteration == 'hash':
                        proof['files_sha256'] = 'hash-of-other-files'
                    if alteration == 'roots':
                        proof['roots'] = ['OTHER']
                    return proof
                nightly.sip_check = verified
                if alteration == 'none':
                    result = nightly.run()
                    self.assertEqual(result['sip_coverage']['status'], 'complete')
                    self.assertEqual(nightly.run()['sip_coverage'], result['sip_coverage'])
                    self.assertEqual(len(checkpoints), 1)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'proof differs'):
                        nightly.run()
                    self.assertEqual(checkpoints, [])
                    self.assertEqual(gate.uploads, {})
                    self.assertNotIn('sip_coverage', nightly.state(self.DAY))

    def test_legacy_checkpoint_never_gets_retroactive_current_source_proof(self):
        data, gate, images = FakeData(self.DAY), FakeGate(), {}
        nightly, _, _ = job(data, gate, images, now=self.NOW)
        nightly.state(self.DAY)['checkpoint'] = 'sbcp_legacy'
        nightly.sip_check = lambda *_: self.fail('a later source read cannot certify an old checkpoint')
        result = nightly.run()
        self.assertEqual(result['sip_coverage'], {'status': 'legacy_unverified'})
        self.assertEqual(result['checkpoint'], 'sbcp_legacy')

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
                return {"day": day.isoformat(), "checkpoint": "sbcp_new", "roots": ["SPY"], "base_checkpoint": "sbcp_gate",
                        "holdout_roots": ["SPY"]}
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


class ChainIdentity(unittest.TestCase):
    """THE CHAIN'S RULE (Oct 1, 2026): the forward chain names the gate image it extends, and the nightly never extends a
    gate whose holdout lacks a root of the swarm. Sept 29-30: the chain extended the five-root gate while swarm.json named
    the 25-root one, and its ready file silently replaced it."""

    NOW = dt.datetime(2026, 9, 29, 6, 5, tzinfo=UTC)
    DAY = dt.date(2026, 9, 28)

    def test_each_day_names_the_gate_image_it_extends_and_the_swarm_takes_only_that_chain(self):
        from league.swarm import settings as S

        images = {"gate": {"current": {"box_id": "sb_gate", "version": "bm-25", "checkpoints": ["sbcp_base25", "sbcp_b"],
                                       "roots": ["SPY", "XSP", "googl"]}}}
        nightly, _, checkpoints = job(FakeData(self.DAY), FakeGate(), images, now=self.NOW)
        result = nightly.run()
        self.assertEqual((result["base_checkpoint"], result["holdout_roots"]), ("sbcp_base25", ["GOOGL", "SPY", "XSP"]))
        self.assertEqual(images["gate"]["forward_days"]["2026-09-28"]["base_checkpoint"], "sbcp_base25")
        self.assertEqual(images["gate"]["checkpoints"][-1], {"id": checkpoints[-1], "day": "2026-09-28",
                                                             "at": self.NOW.isoformat(), "base": "sbcp_base25"})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready = nt.publish_ready(root / "gym-forward.json", result, self.NOW)
            written = json.loads((root / "gym-forward.json").read_text())
            self.assertEqual(written, ready)
            self.assertEqual((written["base_checkpoint"], written["holdout_roots"]), ("sbcp_base25", ["GOOGL", "SPY", "XSP"]))
            # The swarm takes the chain while swarm.json names its base, and not when it names another gate.
            (root / "swarm.json").write_text(json.dumps({"gym": {"gate_checkpoint": "sbcp_base25", "roots": ["SPY", "GOOGL"]}}))
            self.assertEqual(S.load(root, config={})["gym"]["gate_checkpoint"], checkpoints[-1])
            (root / "swarm.json").write_text(json.dumps({"gym": {"gate_checkpoint": "sbcp_other", "roots": ["SPY"]}}))
            self.assertEqual(S.load(root, config={})["gym"]["gate_checkpoint"], "sbcp_other")

    def test_a_day_finished_without_its_gate_image_is_complete_but_never_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = nt.Controller(root, root / "ready.json", calendar(),
                                       run=lambda day: {"day": day.isoformat(), "checkpoint": "sbcp_legacy", "roots": ["SPY"]},
                                       clock=lambda: dt.datetime(2026, 9, 29, 6, 5, tzinfo=UTC))
            out = controller.tick()
            self.assertEqual((out["phase"], out["published"]), ("complete", False))
            self.assertFalse((root / "ready.json").exists(), "the swarm never sees a checkpoint it cannot place")
            record = json.loads((root / "nightly.json").read_text())
            self.assertEqual(record["completed"], {"2026-09-28": "sbcp_legacy"})
            self.assertEqual(record["unpublished"]["day"], "2026-09-28")

    def records(self, root, gate, swarm_roots):
        (root / "data").mkdir(exist_ok=True)
        (root / "data" / "images.json").write_text(json.dumps({"gate": {"current": gate}}))
        (root / "data" / "data_box.json").write_text(json.dumps({"box_id": "sb_data"}))
        (root / "swarm.json").write_text(json.dumps({"gym": {"roots": swarm_roots}}))

    def test_the_job_refuses_to_extend_a_gate_whose_holdout_lacks_a_root_of_the_swarm(self):
        import boxlib as bl

        class Touched(Exception):
            pass

        class NoBoxes:
            def __getattr__(self, name):
                raise Touched(name)

        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp) / "data"):
            root = Path(tmp)
            core = {"box_id": "sb_core", "version": "core-five", "checkpoints": ["sbcp_core"]}
            # Sept 29-30: images.json's gate was the core-five image `images.py finish` recorded without its roots.
            self.records(root, {**core, "roots": None}, ["SPY", "GOOGL", "MSFT"])
            with self.assertRaises(RuntimeError) as caught:
                nt.real_job(api=NoBoxes())
            self.assertIn("refused to extend the gate", str(caught.exception))
            self.records(root, {**core, "roots": ["SPY", "QQQ", "IWM", "XSP", "SPXW"]}, ["SPY", "GOOGL", "MSFT"])
            with self.assertRaises(RuntimeError) as caught:
                nt.real_job(api=NoBoxes(), swarm_root=root)
            self.assertIn("no holdout for GOOGL, MSFT", str(caught.exception))
            # A gate that holds them is extended (the job goes on to the boxes); so is any gate for a rehearsal, and
            # `schedule`, which extends nothing, is never refused.
            self.records(root, {**core, "roots": ["SPY", "GOOGL", "MSFT", "QQQ"]}, ["SPY", "GOOGL", "MSFT"])
            with self.assertRaises(Touched):
                nt.real_job(api=NoBoxes(), swarm_root=root)
            self.records(root, {**core, "roots": None}, ["SPY", "GOOGL", "MSFT"])
            with self.assertRaises(Touched):
                nt.real_job(api=NoBoxes(), extending=False)
            with self.assertRaises(Touched):
                nt.real_job(api=NoBoxes(), rehearsal_gate="sb_rehearsal")

    def test_a_refused_night_wakes_no_box_not_even_the_data_box(self):
        import boxlib as bl
        from unittest import mock

        class Touched(Exception):
            pass

        def touched(*args, **kwargs):
            raise Touched("a box was reached")

        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp) / "data"):
            root = Path(tmp)
            self.records(root, {"box_id": "sb_core", "checkpoints": ["sbcp_core"], "roots": ["SPY", "QQQ"]},
                         ["SPY", "GOOGL"])
            with mock.patch.object(bl, "client", touched), mock.patch.object(bl, "ensure_running", touched):
                # The daemon retries a refused night every 300 s: each retry must leave the data box asleep.
                with self.assertRaisesRegex(RuntimeError, "refused to extend the gate"):
                    nt.run_real(dt.date(2026, 9, 28), swarm_root=root)
                with self.assertRaisesRegex(RuntimeError, "refused to extend the gate"):
                    nt.run_real(dt.date(2026, 9, 28), swarm_root=root, dry_run=True)

    GATE25 = {"box_id": "sb_gate25", "version": "bm-25", "checkpoints": ["sbcp_base25", "sbcp_base25b"],
              "roots": ["SPY", "GOOGL"], "built_at": "2026-09-27T12:04:44Z"}

    def test_the_job_refuses_a_chain_whose_tip_is_not_on_the_gate_image(self):
        import boxlib as bl

        def chain(tip, entries, built_at=self.GATE25["built_at"]):
            return {"gate": {"current": {**self.GATE25, "built_at": built_at}, "current_checkpoint": tip,
                             "checkpoints": entries}}

        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp) / "data"):
            root = Path(tmp)
            (root / "swarm.json").write_text(json.dumps({"gym": {"roots": ["SPY", "GOOGL"]}}))
            ok = [chain(None, []), chain("sbcp_base25", []),  # a fresh chain: the image itself
                  chain("sbcp_c29", [{"id": "sbcp_c29", "day": "2026-09-29", "at": "2026-10-01T06:31:00+00:00"}]),
                  chain("sbcp_c30", [{"id": "sbcp_c30", "day": "2026-09-30", "at": "2026-09-26T06:00:00+00:00",
                                      "base": "sbcp_base25"}])]
            for images in ok:
                nt.preflight(images, root)
            # images.py replaced `current` and left the chain of the image before it: a re-fork from its tip would
            # carry the old image's holdout under the new image's name.
            stale = [chain("sbcp_c29", [{"id": "sbcp_c29", "day": "2026-09-29", "at": "2026-09-30T06:05:00+00:00"}],
                           built_at="2026-10-02T09:00:00Z"),
                     chain("sbcp_c30", [{"id": "sbcp_c30", "day": "2026-09-30", "at": "2026-10-02T06:05:00+00:00",
                                         "base": "sbcp_core5"}]),
                     chain("sbcp_unrecorded", [])]
            for images in stale:
                with self.assertRaisesRegex(RuntimeError, "chain's tip .* is not proven on the gate image"):
                    nt.preflight(images, root)

    def test_a_day_an_earlier_release_checkpointed_is_published_with_its_proven_image(self):
        entry = {"id": "sbcp_legacy", "day": "2026-09-28", "at": "2026-10-01T06:31:00+00:00"}
        images = {"gate": {"current": dict(self.GATE25), "current_checkpoint": "sbcp_legacy", "checkpoints": [entry],
                           "forward_days": {"2026-09-28": {"checkpoint": "sbcp_legacy", "roots": ["SPY"]}}}}
        nightly, _, _ = job(FakeData(self.DAY), FakeGate(), images, now=self.NOW)
        result = nightly.run()
        self.assertTrue(result["already"])
        self.assertEqual((result["base_checkpoint"], result["holdout_roots"]), ("sbcp_base25", ["GOOGL", "SPY"]))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotIn("published", nt.publish_ready(Path(tmp) / "ready.json", result, self.NOW))
        images["gate"]["checkpoints"] = [{**entry, "at": "2026-09-26T06:00:00+00:00"}]  # from before the image: unproven
        nightly, _, _ = job(FakeData(self.DAY), FakeGate(), images, now=self.NOW)
        result = nightly.run()
        self.assertNotIn("base_checkpoint", result)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIs(nt.publish_ready(Path(tmp) / "ready.json", result, self.NOW)["published"], False)


class StampReady(unittest.TestCase):
    """The deploy step: `stamp-ready` names the gate image in the legacy ready file the swarm already takes."""

    NAMED = "sbcp_base25"
    LEGACY = {"schema": 1, "day": "2026-09-29", "ready_at": "2026-10-01T06:32:00+00:00", "gate_checkpoint": "sbcp_c29",
              "roots": ["GOOGL", "SPY"], "sip_coverage": {"status": "legacy_unverified"}}

    def setUp(self):
        import boxlib as bl

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        state = bl.using_state(self.root / "data")
        state.__enter__()
        self.addCleanup(state.__exit__, None, None, None)
        (self.root / "data").mkdir()
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"gate_checkpoint": self.NAMED, "roots": ["SPY", "GOOGL"]}}))
        self.images = {"gate": {"current": {"box_id": "sb_gate25", "checkpoints": [self.NAMED, "sbcp_b"],
                                            "roots": ["SPY", "googl", "QQQ"], "built_at": "2026-09-27T12:04:44Z"},
                                "current_checkpoint": "sbcp_c29",
                                "checkpoints": [{"id": "sbcp_c29", "day": "2026-09-29", "at": "2026-10-01T06:31:00+00:00"}],
                                "forward_days": {"2026-09-29": {"checkpoint": "sbcp_c29",
                                                                "adopted": "2026-10-01T06:30:00+00:00"}}}}
        (self.root / "data" / "images.json").write_text(json.dumps(self.images))
        self.ready = self.root / "gym-forward.json"
        self.ready.write_text(json.dumps(self.LEGACY))

    def test_a_legacy_file_that_stands_is_stamped_with_its_image_and_the_gate_does_not_move(self):
        from league.swarm import settings as S

        dry = nt.stamp_ready(self.ready)
        self.assertEqual(json.loads(self.ready.read_text()), self.LEGACY, "a dry run writes nothing")
        self.assertEqual(dry["would_write"]["base_checkpoint"], self.NAMED)
        out = nt.stamp_ready(self.ready, apply=True)
        written = json.loads(self.ready.read_text())
        self.assertEqual((out["stamped"], out["gate_checkpoint"]), (True, "sbcp_c29"))
        self.assertEqual((written["base_checkpoint"], written["holdout_roots"]), (self.NAMED, ["GOOGL", "QQQ", "SPY"]))
        self.assertEqual({k: v for k, v in written.items() if k not in ("base_checkpoint", "holdout_roots")}, self.LEGACY)
        # The swarm now takes it without images.json, and a second stamp has nothing to do.
        (self.root / "data" / "images.json").unlink()
        self.assertEqual(S.load(self.root, config={})["gym"]["gate_checkpoint"], "sbcp_c29")
        self.assertFalse(nt.stamp_ready(self.ready, apply=True)["stamped"])

    def test_a_file_the_swarm_does_not_take_is_never_stamped_and_a_running_daemon_blocks_it(self):
        from locking import process_lock

        self.images["gate"]["current"]["built_at"] = "2026-10-02T00:00:00Z"  # the chain predates the image
        (self.root / "data" / "images.json").write_text(json.dumps(self.images))
        with self.assertRaisesRegex(RuntimeError, "the swarm does not take this ready file"):
            nt.stamp_ready(self.ready, apply=True)
        self.assertEqual(json.loads(self.ready.read_text()), self.LEGACY)
        with process_lock(self.root / "data" / "nightly.lock"):
            with self.assertRaisesRegex(RuntimeError, "another process holds"):
                nt.stamp_ready(self.ready, apply=True)
