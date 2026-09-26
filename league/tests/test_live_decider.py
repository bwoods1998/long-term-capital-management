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
        self.decider = Decider(timeout=0.5, python=sys.executable)

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

        decider = Stuck(timeout=0.2, python=sys.executable)
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
