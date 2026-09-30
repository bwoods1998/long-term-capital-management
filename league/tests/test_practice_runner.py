"""Finite local simulation boundaries; all quotes/programs below are invented test fixtures."""

import copy
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from league import practice_runner as P
from league.live.decider import DeciderError, InlineDecider
try:
    from league.tests.live_fakes import Clock, MONDAY, Market, VERTICAL, at
    HAVE = True
except ModuleNotFoundError as exc:
    if exc.name != "numpy":
        raise
    HAVE = False


def bundle(minutes=16):
    """Public-format fixture builder; no providers, models, credentials or real quotes."""
    clock = Clock(at(MONDAY, 9, 30))
    market = Market(clock, day=MONDAY, width=2, expiries=(1,))
    out = {"schema": 1, "kind": "synthetic", "label": "Invented vertical mechanics",
           "programs": [{"family": "vertical", "version": 1, "code": VERTICAL, "params": {},
                         "roots": ["SPY"], "structure": "debit_vertical"}], "frames": []}
    for minute in range(minutes):
        clock.set(at(MONDAY, 9, 30) + minute * 60)
        stamp = dt.datetime.fromtimestamp(clock(), dt.timezone.utc).isoformat()
        stocks = market.stocks(["SPY"])
        options = {sym: {"latestQuote": {k: v for k, v in row["latestQuote"].items() if k in {"t", "bp", "ap", "bs", "as"}}}
                   for sym, row in market.rows("SPY").items()}
        out["frames"].append({"at": stamp, "stocks": stocks, "options": options})
    return json.loads(json.dumps(out))


@unittest.skipUnless(HAVE, "numpy not installed")
class Case(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "bundle.json"
        self.output = self.root / "output"
        self.doc = bundle()
        self.input.write_text(json.dumps(self.doc))

    def tearDown(self):
        self.temp.cleanup()

    def simulate(self, doc=None, name="scratch", decider=None):
        doc = P.validate_bundle(doc or self.doc)
        return P._simulate(doc, self.root / name, P.identity(doc), decider or InlineDecider())


class Contract(Case):
    def test_future_quotes_nonchronological_frames_and_undeclared_roots_are_refused(self):
        mutations = (
            lambda d: d["frames"][0]["stocks"]["SPY"]["latestQuote"].update(t=d["frames"][1]["at"]),
            lambda d: next(iter(d["frames"][0]["options"].values()))["latestQuote"].update(t=d["frames"][1]["at"]),
            lambda d: d["frames"].reverse(),
            lambda d: d["frames"].insert(0, d["frames"][0]),
            lambda d: d["programs"][0].update(roots=["QQQ"]),
            lambda d: d["frames"][0]["stocks"].update(QQQ={}),
        )
        for mutate in mutations:
            doc = copy.deepcopy(self.doc)
            mutate(doc)
            with self.subTest(mutation=mutate), self.assertRaises(P.PracticeError):
                P.validate_bundle(doc)

    def test_nonfinite_duplicate_json_and_hidden_capabilities_are_refused(self):
        for raw in (b'{"a":1,"a":2}', b'{"v":NaN}'):
            with self.assertRaises(P.PracticeError):
                P._json(raw)
        for field in ("gateway_url", "real_money", "history", "credentials"):
            doc = copy.deepcopy(self.doc)
            doc[field] = "forbidden"
            with self.assertRaises(P.PracticeError):
                P.validate_bundle(doc)

    def test_market_never_fills_gaps_or_exposes_incomplete_bars(self):
        market = P.RecordedMarket()
        frame = copy.deepcopy(self.doc["frames"][0])
        frame["stocks"]["SPY"]["minuteBar"] = {"t": frame["at"], "v": 10}
        market.select(frame)
        self.assertNotIn("minuteBar", market.stocks(["SPY"])["SPY"])
        market.select({"at": self.doc["frames"][1]["at"], "stocks": {}, "options": {}})
        self.assertEqual(market.stocks(["SPY"]), {})
        self.assertEqual(market.contracts(list(frame["options"])), {})
        self.assertEqual(market.bars(["SPY"]), {"SPY": []})
        self.assertFalse(hasattr(market, "client"))
        self.assertFalse(hasattr(market, "request"))

    def test_cohort_cap_and_frozen_source(self):
        families = P.ObserveOnlyFamilies(self.doc["programs"])
        rows = families.observe()
        rows[0]["params"]["hold"] = 900
        self.assertEqual(families.observe()[0]["params"], {})
        self.assertEqual(families.read(), [])
        for name in ("set_band", "add_forward", "admit_open", "confirm_band"):
            with self.assertRaises(P.PracticeError):
                getattr(families, name)()
        doc = copy.deepcopy(self.doc)
        doc["programs"] *= 5
        with self.assertRaises(P.PracticeError):
            P.validate_bundle(doc)


class Mechanics(Case):
    def test_input_exhaustion_preserves_open_mark_without_inventing_an_exit(self):
        report = self.simulate(bundle(minutes=5))
        row = report["summary"]["rows"][0]
        self.assertEqual(row["open_positions"], 1)
        self.assertEqual(row["trades"], 0)
        self.assertEqual(row["forced"], 0)

    def test_load_failure_is_not_a_successful_zero_trade_run(self):
        class Failed(InlineDecider):
            def load(self, *args, **kwargs):
                raise DeciderError("mandatory sandbox failed after its probe")
        with self.assertRaisesRegex(P.PracticeError, "incomplete"):
            self.simulate(decider=Failed())

    def test_open_fill_close_and_pins_without_accounts_forward_or_bands(self):
        from league.live import step
        with patch.object(step, "RealBook", side_effect=AssertionError("real")), \
             patch.object(step, "PaperProof", side_effect=AssertionError("paper")):
            report = self.simulate()
        row = report["summary"]["rows"][0]
        self.assertGreaterEqual(row["trades"], 1)
        self.assertEqual(row["open_positions"], 0)
        self.assertEqual(row["family"], "local_vertical")
        self.assertEqual(row["forced"], 0)
        self.assertIn("not live practice", report["use"])
        self.assertEqual(report["provenance"]["fill_model"]["basis"], "natural_only")
        with closing(sqlite3.connect(self.root / "scratch" / "observe.sqlite")) as db:
            events = [r[0] for r in db.execute("SELECT kind FROM events")]
            snapshot = json.loads(db.execute("SELECT snapshot FROM cohorts").fetchone()[0])
        self.assertIn("intent", events)
        self.assertGreaterEqual(events.count("fill"), 2)
        self.assertEqual(snapshot["code"], VERTICAL)
        self.assertEqual(snapshot["params"], {})
        self.assertTrue(snapshot["practice_evaluator"].startswith("local-simulation-natural-only:"))
        self.assertFalse((self.root / "scratch" / "swarm.sqlite").exists())
        with closing(sqlite3.connect(self.root / "scratch" / "live.sqlite")) as db:
            self.assertIsNone(db.execute("SELECT value FROM kv WHERE key='underlying_volume_session'").fetchone(),
                              "missing volumes must not be materialized as zero")

    def test_missing_quotes_count_as_missing_not_strategy_losses(self):
        doc = copy.deepcopy(self.doc)
        for frame in doc["frames"]:
            frame["options"] = {}
        report = self.simulate(doc)
        row = report["summary"]["rows"][0]
        self.assertEqual(row["trades"], 0)
        self.assertGreater(row["missed_quotes"], 0)
        self.assertEqual(row["decisions_made"], 0)

    def test_completed_first_observed_volume_survives_late_revision_missing_stays_unknown(self):
        doc = copy.deepcopy(self.doc)
        start = dt.datetime.fromtimestamp(at(MONDAY, 9, 30, 0), dt.timezone.utc).isoformat()
        doc["frames"][0]["stocks"]["SPY"]["minuteBar"] = {"t": start, "v": 900}  # not complete
        doc["frames"][1]["stocks"]["SPY"]["minuteBar"] = {"t": start, "v": 100}
        doc["frames"][2]["stocks"]["SPY"]["minuteBar"] = {"t": start, "v": 999}  # later revision
        report = self.simulate(doc)
        db = sqlite3.connect(self.root / "scratch" / "live.sqlite")
        try:
            volumes = json.loads(db.execute("SELECT value FROM kv WHERE key='underlying_volume_session'").fetchone()[0])
        finally:
            db.close()
        self.assertEqual(volumes["roots"]["SPY"], [[1, 100.0, 1]])
        self.assertGreaterEqual(report["capabilities"]["incomplete_bars_withheld"], 1)


class State(Case):
    def test_busy_finalization_refuses_and_later_seal_preserves_committed_wal(self):
        state = self.root / "busy"
        state.mkdir()
        path = state / "live.sqlite"
        writer = sqlite3.connect(path)
        reader = sqlite3.connect(path)
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("CREATE TABLE receipts(value INTEGER)")
            writer.execute("INSERT INTO receipts VALUES(1)")
            writer.commit()
            reader.execute("BEGIN")
            reader.execute("SELECT * FROM receipts").fetchall()
            writer.execute("INSERT INTO receipts VALUES(2)")
            writer.commit()
            with self.assertRaisesRegex(P.PracticeError, "busy or incomplete"):
                P._finalize_state(state)
        finally:
            reader.close()
            writer.close()
        P._finalize_state(state)
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            self.assertEqual(db.execute("SELECT value FROM receipts ORDER BY value").fetchall(), [(1,), (2,)])
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")

    def test_normalized_system_and_numerical_mount_paths_and_hardlinks_are_refused(self):
        import numpy
        for path in (Path("/tmp/../usr/local/practice-output"), Path(numpy.__file__).parent / "uncreated-output"):
            with self.assertRaises(P.PracticeError), P.private_output(path, self.input):
                pass
        alias = self.root / "second-input.json"
        os.link(self.input, alias)
        with self.assertRaises(P.PracticeError):
            P.load_bundle(alias)

    def test_completed_private_state_tampering_is_refused(self):
        class Fixture(InlineDecider):
            def probe(self):
                return {}
            def __init__(self, **_):
                super().__init__()
        with patch.object(P, "SandboxedDecider", Fixture):
            P.run(self.input, self.output)
        (self.output / "state" / "progress.json").write_text("{}")
        with self.assertRaisesRegex(P.PracticeError, "state changed"):
            P.run(self.input, self.output)

    def test_committed_wal_changes_are_not_excluded_from_completed_identity(self):
        class Fixture(InlineDecider):
            def probe(self):
                return {}
            def __init__(self, **_):
                super().__init__()
        with patch.object(P, "SandboxedDecider", Fixture):
            P.run(self.input, self.output)
        db = sqlite3.connect(self.output / "state" / "observe.sqlite")
        try:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            db.execute("UPDATE practice SET decisions_made=decisions_made+1")
            db.commit()
            self.assertTrue((self.output / "state" / "observe.sqlite-wal").exists())
            with self.assertRaisesRegex(P.PracticeError, "state changed"):
                P.run(self.input, self.output)
        finally:
            db.close()

    def test_unknown_existing_symlink_checkout_and_locked_output_are_refused(self):
        self.output.mkdir(mode=0o700)
        with self.assertRaises(P.PracticeError), P.private_output(self.output, self.input):
            pass
        (self.output / P.MARKER).write_text("{}")
        alias = self.root / "alias"
        alias.symlink_to(self.output, target_is_directory=True)
        with self.assertRaises(P.PracticeError), P.private_output(alias, self.input):
            pass
        with self.assertRaises(P.PracticeError), P.private_output(P.REPO / "unsafe-practice", self.input):
            pass
        with P.private_output(self.output, self.input):
            with self.assertRaises(P.PracticeError), P.private_output(self.output, self.input):
                pass

    def test_real_instances_and_nonobserve_shadow_state_fail_before_constructor(self):
        state = self.root / "badstate"
        state.mkdir()
        db = sqlite3.connect(state / "live.sqlite")
        db.execute("CREATE TABLE instances(id TEXT)")
        db.execute("INSERT INTO instances VALUES('unsafe:r')")
        db.commit()
        db.close()
        with self.assertRaises(P.PracticeError):
            P.check_state(state)
        (state / "live.sqlite").unlink()
        (state / "live-shadow.json").write_text(json.dumps({"version": 1, "accounts": [{"instance": "unsafe:s"}]}))
        with self.assertRaises(P.PracticeError):
            P.check_state(state)

    def test_interrupted_run_rebuilds_frozen_input_without_duplicate_trades(self):
        # A trusted fixture seam only: the public API does not accept a decider argument or an isolation bypass.
        class Fixture(InlineDecider):
            def probe(self):
                return {}
            def __init__(self, **_):
                super().__init__()

        actual = P._simulate
        def interrupted(doc, root, provenance, decider):
            actual({**doc, "frames": doc["frames"][:6]}, root, provenance, decider)
            raise KeyboardInterrupt("invented interruption after a fill")
        with patch.object(P, "SandboxedDecider", Fixture), patch.object(P, "_simulate", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                P.run(self.input, self.output)
        self.assertEqual(json.loads((self.output / "attempt" / "progress.json").read_text())["frames_completed"], 6)
        # SIGKILL can leave the engine's mkstemp file midway through JSON. It is discarded with the incomplete
        # attempt, never parsed/restored or accepted as part of a completed result.
        scratch = self.output / "attempt" / "live-shadow.json.abcdefgh.tmp"
        scratch.write_text('{"accounts":[')
        with self.assertRaises(P.PracticeError):
            P.check_state(self.output / "attempt")
        with patch.object(P, "SandboxedDecider", Fixture):
            resumed = P.run(self.input, self.output)
        self.assertEqual(resumed["recovery"], "replayed_from_start")
        self.assertEqual(resumed["summary"]["rows"][0]["trades"], 1)
        with patch.object(P, "SandboxedDecider", side_effect=AssertionError("cached run must not execute")):
            self.assertEqual(P.run(self.input, self.output), resumed)
        self.doc["programs"][0]["params"] = {"hold": 12}
        self.input.write_text(json.dumps(self.doc))
        with self.assertRaisesRegex(P.PracticeError, "identity changed"):
            P.run(self.input, self.output)

    def test_incomplete_scratch_exception_does_not_admit_unknown_or_linked_files(self):
        state = self.root / "scratch"
        state.mkdir()
        unknown = state / "live-shadow.json.not-engine-scratch.tmp"
        unknown.write_text("unknown")
        with self.assertRaises(P.PracticeError):
            P.check_state(state, allow_scratch=True)
        unknown.unlink()
        scratch = state / "live-shadow.json.abcdefgh.tmp"
        scratch.write_text("partial")
        P.check_state(state, allow_scratch=True)
        os.link(scratch, self.root / "linked-scratch")
        with self.assertRaises(P.PracticeError):
            P.check_state(state, allow_scratch=True)

    def test_missing_sandbox_refuses_before_strategy_loading(self):
        with patch.object(P.shutil, "which", return_value=None), patch.object(P, "_simulate", side_effect=AssertionError("program execution")):
            with self.assertRaisesRegex(P.PracticeError, "mandatory sandbox"):
                P.run(self.input, self.output)
        self.assertNotEqual(json.loads((self.output / P.MARKER).read_text())["status"], "complete")


@unittest.skipUnless(shutil.which("bwrap") and (Path(sys.executable).parent.parent / "pyvenv.cfg").exists()
                     and Path(sys.executable).resolve().is_relative_to("/usr"),
                     "requires bubblewrap and isolated system-Python venv; public run refuses without them")
class Isolation(Case):
    def test_separate_process_readonly_inspection_then_cached_cli_needs_no_sandbox(self):
        command = [sys.executable, "-B", str(P.REPO / "scripts/practice_run.py"),
                   "--input", str(self.input), "--output", str(self.output)]
        env = {"PATH": "/usr/bin:/bin", "OPENBLAS_NUM_THREADS": "1"}
        first = subprocess.run(command, capture_output=True, env=env, timeout=30)
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        original = (self.output / "report.json").read_bytes()
        inspector = ("import sqlite3,sys; from pathlib import Path; "
                     "p=Path(sys.argv[1]); db=sqlite3.connect(p.as_uri()+'?mode=ro', uri=True); "
                     "assert db.execute('PRAGMA journal_mode').fetchone()[0]=='delete'; "
                     "assert db.execute('SELECT COUNT(*) FROM trades').fetchone()[0] > 0; db.close()")
        inspected = subprocess.run([sys.executable, "-B", "-c", inspector,
                                    str(self.output / "state" / "observe.sqlite")], capture_output=True, env=env, timeout=15)
        self.assertEqual(inspected.returncode, 0, inspected.stderr.decode())
        self.assertFalse(list((self.output / "state").glob("*-wal")))
        self.assertFalse(list((self.output / "state").glob("*-shm")))
        cached = subprocess.run(command, capture_output=True, env={**env, "PATH": "/no-sandbox-binary"}, timeout=15)
        self.assertEqual(cached.returncode, 0, cached.stderr.decode())
        self.assertEqual((self.output / "report.json").read_bytes(), original)

    def test_actual_child_roots_and_post_probe_transport_failure_refuse_the_run(self):
        self.doc["programs"][0]["code"] += '\nNEEDS["roots"] = ["QQQ"]\n'
        self.input.write_text(json.dumps(self.doc))
        with self.assertRaisesRegex(P.PracticeError, "incomplete"):
            P.run(self.input, self.output)
        self.assertEqual(json.loads((self.output / P.MARKER).read_text())["status"], "running")
        self.doc = bundle()
        self.input.write_text(json.dumps(self.doc))
        original = P.SandboxedDecider._raw
        def failed(decider, message, deadline):
            if message[0] == "load":
                raise DeciderError("invented post-probe transport failure")
            return original(decider, message, deadline)
        with patch.object(P.SandboxedDecider, "_raw", failed), self.assertRaisesRegex(P.PracticeError, "incomplete"):
            P.run(self.input, self.root / "another-output")

    def test_real_sandbox_can_run_mechanics_and_has_no_host_paths_environment_or_network(self):
        with patch.dict(os.environ, {"GATEWAY_TOKEN": "must-not-reach-child", "SAIL_API_KEY": "private"}):
            report = P.run(self.input, self.output)
        self.assertEqual(report["summary"]["rows"][0]["trades"], 1)
        runtime = self.root / "runtime"
        runtime.mkdir()
        P._stage_runtime(runtime)
        argv = P.sandbox_command(runtime, python=Path(sys.executable))
        command = argv[:argv.index("--") + 1] + ["/venv/bin/python", "-E", "-s", "-B", "-c",
            "import os,socket; from pathlib import Path; "
            "assert 'GATEWAY_TOKEN' not in os.environ; assert 'SAIL_API_KEY' not in os.environ; "
            "assert not Path('/home').exists(); assert not Path('/output').exists(); "
            "assert not Path('/input').exists(); assert not Path('/work/.git').exists(); "
            "assert not Path('/work/.data').exists(); assert not Path('/work/.env').exists(); "
            "s=socket.socket(); s.settimeout(.1); assert s.connect_ex(('1.1.1.1',443)) != 0; "
            "assert len(list(Path('/work').rglob('*.py'))) == 11\n"
            "try: Path('/work/league/live/decider.py').write_text('bad')\n"
            "except OSError: pass\n"
            "else: raise AssertionError('writable runtime')\n"]
        result = subprocess.run(command, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
