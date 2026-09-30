"""The decider (`league/live/decider.py`): programs run in a child process with no secrets, a time limit on each call,
and a House-side deadline that kills and restarts a child that stops answering."""

import os
import subprocess
import sys
import unittest

try:
    import numpy as np
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import venue as V
    from league.gym.ctx import Snapshot, underlying_view
    from league.live.decider import Decider, DeciderError, InlineDecider, ProgramRefused
    from league.tests.live_fakes import VERTICAL

LOOP = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0}
PARAMS = {}

def decide(ctx):
    n = 0
    while True:
        n += 1
'''


def snapshot():
    strikes = np.arange(590.0, 611.0)
    k = np.repeat(strikes, 2)
    call = np.tile([True, False], strikes.size)
    dte = np.ones(k.size, dtype=int)
    mid = np.maximum(0.05, np.where(call, 600.5 - k, k - 599.5)) + 1.0
    return Snapshot("SPY", 600, 600.0, dte, k, call, mid - 0.01, mid + 0.01, np.full(k.size, 50), np.full(k.size, 50), rate=0.04)


def job(key):
    return {"key": key, "mi": 30, "minute": 600, "open_minute": 570, "close_minute": 960, "weekday": 0, "roots": ["SPY"],
            "positions": [], "orders": [], "cash": 10000.0, "equity": 10000.0, "budget": 10000.0, "buying_power": 10000.0,
            "rules": {"SPY": V.rules_for("SPY").as_dict()}, "events": {}, "events_next": {}, "closed": [], "rejects": []}


@unittest.skipUnless(HAVE, "numpy not installed")
class TheChild(unittest.TestCase):
    def setUp(self):
        self.decider = Decider(timeout=0.5, python=sys.executable, allow_unisolated=True)

    def tearDown(self):
        self.decider.close()

    def test_the_child_answers_as_the_inline_decider_does_and_holds_no_secret(self):
        os.environ["GATEWAY_TOKEN"] = "x" * 40
        try:
            ping = self.decider.ping()
        finally:
            del os.environ["GATEWAY_TOKEN"]
        self.assertNotIn("GATEWAY_TOKEN", ping["env"])
        self.assertNotIn("SAIL_API_KEY", ping["env"])
        self.assertNotEqual(ping["pid"], os.getpid())
        inline = InlineDecider()
        for d in (self.decider, inline):
            d.load("v", VERTICAL, {}, "vert")
        snaps, unders = {("SPY", 30): snapshot()}, {("SPY", 2, 30): underlying_view("SPY", [600.0, 600.1])}
        remote, local = self.decider.decide(snaps, unders, [job("v")]), inline.decide(snaps, unders, [job("v")])
        for answer in (remote, local):
            self.assertGreaterEqual(answer["v"]["stats"].pop("seconds"), 0)
        self.assertEqual(remote, local)

    def test_the_child_has_no_network_where_the_box_allows_a_namespace(self):
        import ipaddress
        import shutil

        if not (shutil.which("unshare") and subprocess.run(["unshare", "--net", "--map-root-user", "true"],
                                                            capture_output=True).returncode == 0):
            self.skipTest("no unprivileged network namespace here")
        ping = self.decider.ping()
        self.assertTrue(self.decider.netns)
        # Some kernels include the dormant sit0 tunnel in a fresh namespace. An interface name alone does not mean
        # external connectivity: there must be no external address or route through any interface.
        self.assertIsNotNone(ping["routed_interfaces"])
        self.assertLessEqual(set(ping["routed_interfaces"]), {"lo"})
        self.assertIsNotNone(ping["addresses"])
        for address in ping["addresses"]:
            parsed = ipaddress.ip_address(address)
            self.assertTrue(parsed.is_loopback or parsed.is_unspecified, address)

    def test_a_program_that_never_returns_is_cut_off_and_counted(self):
        self.decider.load("loop", LOOP, {}, "loop")
        answer = self.decider.decide({("SPY", 30): snapshot()}, {("SPY", 0, 30): underlying_view("SPY", [600.0])}, [job("loop")])["loop"]
        self.assertEqual(answer["intents"], [])
        self.assertEqual(answer["stats"]["timeouts"], 1)
        self.assertEqual(self.decider.restarts, 0)

    def test_a_refused_program_does_not_load(self):
        with self.assertRaises(ProgramRefused):
            self.decider.load("bad", "import os\nNEEDS={'roots':['SPY']}\nPARAMS={}\ndef decide(ctx):\n    return []\n", {}, "bad")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheHousesSide(unittest.TestCase):
    def test_a_batch_never_holds_the_minute(self):
        from league.live.decider import batch_deadline

        self.assertLessEqual(batch_deadline(1.0, 500), 40.0)
        self.assertEqual(batch_deadline(1.0, 2), 5.0 + 2 * 1.25)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux prctl")
    def test_the_house_process_is_not_readable_by_a_child_of_its_uid(self):
        import ctypes

        from league.live.decider import protect_house_process

        libc = ctypes.CDLL(None, use_errno=True)
        try:
            self.assertTrue(protect_house_process())
            self.assertEqual(libc.prctl(3, 0, 0, 0, 0), 0)          # PR_GET_DUMPABLE: 0, /proc/<pid>/environ is root's
        finally:
            libc.prctl(4, 1, 0, 0, 0)                               # PR_SET_DUMPABLE back for the rest of the tests


@unittest.skipUnless(HAVE, "numpy not installed")
class AHungChild(unittest.TestCase):
    def test_the_house_kills_it_restarts_it_and_reloads_every_program(self):
        class Stuck(Decider):
            hang = False

            def _spawn(self, budget_seconds=10.0):
                if Stuck.hang:
                    self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.PIPE,
                                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    Stuck.hang = False
                else:
                    super()._spawn(budget_seconds=budget_seconds)

        decider = Stuck(timeout=0.2, python=sys.executable, allow_unisolated=True)
        try:
            decider.load("v", VERTICAL, {}, "vert")
            decider._kill()
            Stuck.hang = True
            with self.assertRaises(DeciderError):
                decider.decide({("SPY", 30): snapshot()}, {("SPY", 2, 30): underlying_view("SPY", [600.0])}, [job("v")])
            self.assertEqual(decider.restarts, 1)
            # The next child has every program again (fresh memory).
            answer = decider.decide({("SPY", 30): snapshot()}, {("SPY", 2, 30): underlying_view("SPY", [600.0])}, [job("v")])
            self.assertIn("v", answer)
            self.assertTrue(answer["v"]["intents"])
        finally:
            decider.close()


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE, "numpy not installed")
class ASpentBudget(unittest.TestCase):
    """The review of #390 (lens 3): a minute whose budget is spent before a request goes skips that request; the child
    is not killed, so its programs keep their memory (a kill is only for a child that did not answer)."""

    def test_nothing_is_sent_and_the_child_is_not_killed(self):
        from league.live.decider import BudgetSpent, Decider, DeciderError

        d = Decider(allow_unisolated=True)
        killed = []
        d._kill = lambda: killed.append(True)
        with self.assertRaises(BudgetSpent) as caught:
            d._ask(("decide", {}, {}, []), 0.0)
        self.assertIsInstance(caught.exception, DeciderError, "the House's minute treats it as any decider trouble")
        self.assertEqual((killed, d.restarts, d.proc), ([], 0, None), "no child was spawned, killed or restarted")


@unittest.skipUnless(HAVE, "numpy not installed")
class OffARootHouse(unittest.TestCase):
    """The scan of Sept 30 (scan-a section 3): off a root House a child would keep the House user's files and, without a
    namespace, its network. A `Decider` there refuses before it probes or spawns anything."""

    def test_a_non_root_decider_refuses_before_it_spawns(self):
        from unittest.mock import patch

        from league.live import decider as D

        with patch.object(D.os, "geteuid", return_value=1000):
            d = D.Decider()
        try:
            self.assertEqual((d.isolated, d.allow_unisolated), (False, False))
            with patch.object(D, "_netns_available") as probe, patch.object(D.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(DeciderError, "only as uid 65534 in a private network namespace"):
                    d.ping()
                with self.assertRaisesRegex(DeciderError, "only as uid 65534"):
                    d.load("v", VERTICAL, {}, "vert")
            self.assertEqual((probe.call_count, popen.call_count), (0, 0))
            self.assertIsNone(d.proc)
        finally:
            d.close()


@unittest.skipUnless(HAVE, "numpy not installed")
class ANamespaceProbe(unittest.TestCase):
    """The scan of Sept 30: a probe that timed out (its timeout was whatever was left of the minute) was kept as False,
    and the root House refused every later spawn until a restart. Only a success is kept now; a failure is probed again
    at a spawn `NETNS_RETRY_SECONDS` later (never once for each load in a minute), with a timeout of at least
    `NETNS_PROBE_MIN_SECONDS`."""

    def test_a_probe_that_times_out_once_lets_a_later_spawn_proceed(self):
        import tempfile
        import time
        from pathlib import Path
        from unittest.mock import patch

        from league.live import decider as D

        timeouts, answers, spawned = [], [False, True], []
        real_popen = subprocess.Popen

        def probe(timeout, *, credentials=None):
            timeouts.append(timeout)
            self.assertEqual(credentials, {"user": 65534, "group": 65534, "extra_groups": []})
            return answers.pop(0)

        def popen(command, **kw):
            # This test is not root: the uid drop and the namespace the root House asks for are recorded, and the same
            # child is started without them, from the checkout.
            isolation = {k: kw.pop(k) for k in ("user", "group", "extra_groups")}
            spawned.append((list(command), isolation))
            if command[:3] == ["unshare", "--net", "--map-root-user"]:
                command = command[3:]
            kw["cwd"] = str(D.REPO)
            return real_popen(command, **kw)

        with patch.object(D.os, "geteuid", return_value=0):
            d = D.Decider(timeout=0.5, python=sys.executable)  # as the root House builds it
        d._runtime = Path(tempfile.mkdtemp(prefix="ltcm-decider-test-"))  # no root-owned read-only copy off root
        try:
            self.assertTrue(d.isolated)
            with patch.object(D, "_netns_available", side_effect=probe), patch.object(D.subprocess, "Popen", side_effect=popen), \
                    patch.object(D, "NETNS_RETRY_SECONDS", 0.3):
                # A nearly spent minute: the probe still gets its minimum timeout, and it times out.
                with self.assertRaisesRegex(DeciderError, "requires a network namespace"):
                    d._ask(("ping",), 0.05)
                self.assertEqual(timeouts, [D.NETNS_PROBE_MIN_SECONDS])
                self.assertFalse(d.netns)
                # Inside the retry window: refused again at once, without another probe.
                with self.assertRaisesRegex(DeciderError, "requires a network namespace"):
                    d.ping()
                self.assertEqual((len(timeouts), spawned), (1, []))
                time.sleep(0.35)
                # The next spawn probes again, succeeds, and the child answers.
                ping = d.ping()
                self.assertEqual(ping["pid"], d.pid)
                self.assertTrue(d.netns)
                self.assertEqual(timeouts[1], D.NETNS_PROBE_MAX_SECONDS)
                self.assertEqual(spawned[0][0][:3], ["unshare", "--net", "--map-root-user"])
                self.assertEqual(spawned[0][1], {"user": 65534, "group": 65534, "extra_groups": []})
                # A success is kept: a restarted child is not probed for again.
                d._kill()
                d.ping()
                self.assertEqual((len(timeouts), len(spawned)), (2, 2))
        finally:
            d.close()

    def test_off_root_a_failed_probe_is_retried_too(self):
        from unittest.mock import patch

        from league.live import decider as D

        d = D.Decider(allow_unisolated=True)
        with patch.object(D, "_netns_available", side_effect=[False, True]) as probe:
            self.assertFalse(d._namespace(0.001, {}))
            self.assertFalse(d._namespace(10.0, {}))       # inside the window: no probe
            d._netns_retry_at = float("-inf")               # the window has passed
            self.assertTrue(d._namespace(0.001, {}))
            self.assertTrue(d._namespace(0.001, {}))       # kept
        self.assertEqual([c.kwargs["timeout"] for c in probe.call_args_list], [D.NETNS_PROBE_MIN_SECONDS] * 2)


@unittest.skipUnless(HAVE, "numpy not installed")
@unittest.skipUnless(sys.platform.startswith("linux"), "Linux rlimits and /proc")
class TheChildsLimits(unittest.TestCase):
    """The scan of Sept 30: the child sets a file-size cap and no new process or thread, beside `RLIMIT_AS` and
    `PR_SET_NO_NEW_PRIVS`, and still runs a normal program and logs to stderr."""

    def test_a_normal_program_runs_under_the_limits(self):
        import tempfile
        from pathlib import Path

        from league.live.decider import FILE_MB

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "live-decider.log"
            d = Decider(timeout=0.5, python=sys.executable, log=log, allow_unisolated=True)
            try:
                d.load("v", VERTICAL, {}, "vert")
                limits = {line[:26].strip(): line[26:].split() for line in
                          Path(f"/proc/{d.pid}/limits").read_text().splitlines()[1:]}
                self.assertEqual(limits["Max file size"][:2], [str(FILE_MB * 1024 * 1024)] * 2)
                self.assertEqual(limits["Max processes"][:2], ["0", "0"])
                self.assertEqual(limits["Max address space"][:2], [str(2048 * 1024 * 1024)] * 2)
                answer = d.decide({("SPY", 30): snapshot()}, {("SPY", 2, 30): underlying_view("SPY", [600.0, 600.1])},
                                  [job("v")])
                self.assertTrue(answer["v"]["intents"])
                self.assertEqual(d.restarts, 0)
            finally:
                d.close()

    @unittest.skipIf(os.geteuid() == 0, "root is exempt from RLIMIT_NPROC; the House's child is uid 65534")
    def test_no_fork_a_capped_file_and_stderr_still_works(self):
        import tempfile

        from league.live.decider import REPO

        script = (
            "import os, sys\n"
            "from league.live.decider import FILE_MB, limit_child\n"
            "limit_child()\n"
            "import numpy\n"
            "assert float(numpy.linalg.inv(numpy.eye(3)).sum()) == 3.0\n"
            "try:\n"
            "    os.fork()\n"
            "    os._exit(0)\n"
            "except OSError:\n"
            "    print('fork refused')\n"
            "try:\n"
            "    with open('big', 'wb') as f:\n"
            "        f.seek(FILE_MB * 1024 * 1024)\n"
            "        f.write(b'x')\n"
            "except OSError as exc:\n"
            "    print('file capped', exc.errno)\n"
            "sys.stderr.write('logged\\n')\n"
            "sys.stderr.flush()\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": tmp, "PYTHONPATH": str(REPO),
                   "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
            done = subprocess.run([sys.executable, "-s", "-c", script], cwd=tmp, env=env, capture_output=True, text=True,
                                  timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.split("\n")[:2], ["fork refused", "file capped 27"])     # EFBIG, not SIGXFSZ
        self.assertIn("logged", done.stderr)

    def test_a_log_past_half_the_cap_is_moved_aside_before_a_spawn(self):
        import tempfile
        from pathlib import Path

        from league.live.decider import rotate_log

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "live-decider.log"
            rotate_log(log, 10)                                 # no log yet: nothing to do
            log.write_bytes(b"x" * 5)
            rotate_log(log, 10)
            self.assertEqual(log.read_bytes(), b"x" * 5)
            log.write_bytes(b"y" * 10)
            rotate_log(log, 10)
            self.assertFalse(log.exists())
            self.assertEqual((Path(tmp) / "live-decider.log.1").read_bytes(), b"y" * 10)
