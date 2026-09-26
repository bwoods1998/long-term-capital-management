"""The sealed-box driver against a fake Sail client that runs the box's commands locally: the code
bundle goes up once, programs go in as files, results come back; transient API errors are retried;
missing data, a timeout and a failed command are clear errors. Also the batch CLI's own contract."""

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import batch as B
    from league.gym import driver as DR
    from league.gym import synth

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "league" / "gym" / "examples"


class FakeError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status = status


class FakeResult:
    def __init__(self, return_code, stdout="", stderr="", status=None):
        self.return_code, self.stdout, self.stderr = return_code, stdout, stderr
        self.status = status or ("succeeded" if return_code == 0 else "failed")


class FakeSail:
    """upload / download / exec with the real client's signatures, on the local disk. `fail` lists
    (method, status) errors to raise, in order, before the call goes through."""

    def __init__(self, fail=(), timeout_exec=False):
        self.fail = list(fail)
        self.timeout_exec = timeout_exec
        self.log = []

    def _maybe_fail(self, method):
        if self.fail and self.fail[0][0] == method:
            raise FakeError(self.fail.pop(0)[1])

    def upload(self, sailbox, path, content, *, mode=0o600, create_parents=True, timeout=300.0):
        self.log.append(("upload", path))
        self._maybe_fail("upload")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(content)
        return {"path": path}

    def download(self, sailbox, path, *, timeout=300.0):
        self.log.append(("download", path))
        self._maybe_fail("download")
        return Path(path).read_bytes()

    def exec(self, sailbox, command, *, cwd=None, env=None, timeout=600, background=False, on_output=None, idempotency_key=None):
        self.log.append(("exec", command))
        self._maybe_fail("exec")
        if self.timeout_exec and "league.gym.batch --programs" in command:
            return FakeResult(None, status="timed_out")
        env = dict(os.environ, TMPDIR=os.environ.get("TMPDIR", "/tmp"))
        done = subprocess.run(["bash", "-c", command], capture_output=True, text=True, timeout=timeout, env=env)
        return FakeResult(done.returncode, done.stdout, done.stderr)


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class SealedBoxDriver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="gym-driver-"))
        cls.store = cls.dir / "store"
        synth.generate(cls.store, roots=("SPY",), days=synth.weekdays(dt.date(2023, 5, 1), 4), strikes_each_side=6, max_dte=3)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def driver(self, client, **kw):
        remote = self.dir / "box" / self._testMethodName
        return DR.GymDriver(client, "sb_0123456789abcdef", remote_root=str(remote), store_root=str(self.store),
                            python=sys.executable, sleep=lambda s: None, **kw)

    def test_a_batch_round_trip_uploads_the_code_once(self):
        client = FakeSail()
        drv = self.driver(client)
        code = (EXAMPLES / "condor_vrp.py").read_text()
        doc = drv.run({"condor": (code, [{"vrp_min": 0.5}, {"vrp_min": 0.9}]), "dip": (EXAMPLES / "putspread_dip.py").read_text()},
                      window="train", roots=["SPY"], workers=2)
        self.assertEqual(doc["batch"]["trials"], 3)
        self.assertEqual([r["status"] for r in doc["results"]], ["ok", "ok", "ok"])
        self.assertEqual(doc["batch"]["bundle"], drv.version)
        uploads = [p for kind, p in client.log if kind == "upload"]
        self.assertEqual(sum(p.endswith(".tgz") and "/code/" in p for p in uploads), 1)
        drv.run({"dip": (EXAMPLES / "putspread_dip.py").read_text()}, window="train", roots=["SPY"])
        uploads = [p for kind, p in client.log if kind == "upload"]
        self.assertEqual(sum("/code/" in p for p in uploads), 1)   # the second batch reuses the bundle
        self.assertEqual(drv.check_data("train", ["SPY"])["roots"]["SPY"]["nbbo"], 4)

    def test_transient_errors_are_retried(self):
        client = FakeSail(fail=[("exec", 503), ("upload", 429), ("download", 502)])
        doc = self.driver(client).run({"dip": (EXAMPLES / "putspread_dip.py").read_text()}, window="train", roots=["SPY"])
        self.assertEqual(doc["results"][0]["status"], "ok")
        self.assertFalse(client.fail)

    def test_a_permanent_error_is_not_retried(self):
        client = FakeSail(fail=[("exec", 404)])
        with self.assertRaises(DR.GymError):
            self.driver(client).ensure_code()
        self.assertEqual(sum(1 for kind, _ in client.log if kind == "exec"), 1)

    def test_missing_data_is_a_clear_error(self):
        drv = self.driver(FakeSail())
        with self.assertRaises(DR.GymDataMissing) as caught:
            drv.check_data("train", ["SPY", "QQQ"])
        self.assertIn("missing data", str(caught.exception))
        self.assertIn("QQQ", str(caught.exception))
        with self.assertRaises(DR.GymDataMissing):
            drv.run({"dip": (EXAMPLES / "putspread_dip.py").read_text()}, window="validation", roots=["SPY"])

    def test_a_timeout_is_a_clear_error(self):
        with self.assertRaises(DR.GymTimeout):
            self.driver(FakeSail(timeout_exec=True)).run({"dip": (EXAMPLES / "putspread_dip.py").read_text()},
                                                        window="train", roots=["SPY"], timeout=5)

    def test_the_bundle_is_reproducible_and_complete(self):
        a, va = DR.build_bundle()
        b, vb = DR.build_bundle()
        self.assertEqual((a, va), (b, vb))
        import io
        import tarfile
        names = tarfile.open(fileobj=io.BytesIO(a), mode="r:gz").getnames()
        for needed in ("league/__init__.py", "league/safety.py", "league/structure_core.py", "league/stats.py",
                       "league/gym/engine.py", "league/gym/batch.py", "league/CONTRACT.md"):
            self.assertIn(needed, names)
        self.assertFalse(any("test" in n for n in names))


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class BatchContract(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="gym-batch-"))
        synth.generate(self.dir / "store", roots=("SPY",), days=synth.weekdays(dt.date(2023, 5, 1), 6), strikes_each_side=6, max_dte=3)
        (self.dir / "progs").mkdir()
        shutil.copy(EXAMPLES / "condor_vrp.py", self.dir / "progs" / "condor.py")
        (self.dir / "progs" / "bad.py").write_text("import os\nNEEDS = {}\nPARAMS = {}\ndef decide(ctx):\n    return []\n")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_refused_programs_are_reported_not_fatal_and_split_merges(self):
        jobs = B.find_programs(self.dir / "progs")
        doc = B.run_batch(jobs, store_root=str(self.dir / "store"), window="train", roots=["SPY"], workers=2, split=2)
        by_name = {r["program"]: r for r in doc["results"]}
        self.assertEqual(by_name["bad"]["status"], "refused")
        self.assertIn("math and numpy", by_name["bad"]["reason"])
        self.assertEqual(by_name["condor"]["status"], "ok")
        self.assertEqual(len(by_name["condor"]["daily"]), 6)
        self.assertEqual(len(by_name["condor"]["segments"]), 2)
        self.assertEqual(doc["batch"]["trials"], 1)
        again = B.run_batch(jobs, store_root=str(self.dir / "store"), window="train", roots=["SPY"], workers=1, split=2)
        self.assertEqual({r["program"]: r.get("result_sha") for r in again["results"]},
                         {r["program"]: r.get("result_sha") for r in doc["results"]})

    def test_the_cli_exit_codes(self):
        env = dict(os.environ)
        run = lambda *a: subprocess.run([sys.executable, "-m", "league.gym.batch", *a], capture_output=True, text=True,  # noqa: E731
                                        cwd=REPO, env=env)
        out = self.dir / "out.json"
        ok = run("--programs", str(self.dir / "progs"), "--window", "train", "--roots", "SPY", "--store", str(self.dir / "store"),
                 "--out", str(out), "--workers", "1")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(len(json.loads(out.read_text())["results"]), 2)
        missing = run("--programs", str(self.dir / "progs"), "--window", "train", "--roots", "QQQ", "--store", str(self.dir / "store"),
                      "--out", str(out))
        self.assertEqual(missing.returncode, 3)
        self.assertIn("missing data", missing.stderr)
        sealed = run("--programs", str(self.dir / "progs"), "--window", "holdout", "--roots", "SPY", "--store", str(self.dir / "store"),
                     "--out", str(out))
        self.assertEqual(sealed.returncode, 4)


if __name__ == "__main__":
    unittest.main()
