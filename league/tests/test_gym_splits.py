"""Stock splits in the Gym (Sept 28, 2026): a position on a single name held into a split session could be neither marked
nor closed (the OCC's adjusted contracts are not in the chain under the old keys) and expired against the post-split
price. Now every position on the root closes on the split's eve at the natural, and no opening order may be held across
it. Synthetic stores only: the name ACME, its prices and its quotes are made up; split factors are public facts."""

import datetime as dt
import shutil
import tempfile
import unittest
from unittest import mock

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import engine as E
    from league.gym import results as RS
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth
    from league.tests.test_gym_determinism import EXAMPLES, MID_TRADER

# Opens what OPENS lists at 10:00 of its session (0 = the run's first), one qty each; never closes.
OPENER = '''
NEEDS = {"roots": ROOTS, "dte": [0, 10], "band": 0.3, "cadence": 5, "start": 600}
PARAMS = {}
OPENS = LIST
STATE = {"sessions": 0, "last": 10000}
def decide(ctx):
    if ctx.minute < STATE["last"]:
        STATE["sessions"] += 1
    STATE["last"] = ctx.minute
    out = []
    if ctx.minute == 600:
        for o in OPENS:
            if o["session"] == STATE["sessions"] - 1 and o["root"] in ctx.roots:
                out.append({"open": o["type"], "root": o["root"], "legs": o["legs"], "qty": 1, "tag": o["tag"]})
    return out
'''


def opener(opens, roots=("ACME", "SPY"), name="opener"):
    return R.load_program(OPENER.replace("ROOTS", repr(list(roots))).replace("LIST", repr(list(opens))), name=name)


# Mon-Fri; ACME splits 3-for-1 at the open of D[2], so D[1] is the eve.
D = [dt.date(2023, 3, 6), dt.date(2023, 3, 7), dt.date(2023, 3, 8), dt.date(2023, 3, 9), dt.date(2023, 3, 10)]


def vertical(root, session, dte, low, high, tag, right="C", kind="debit_vertical"):
    long_, short = (low, high) if right == "C" else (high, low)
    if kind == "credit_vertical":
        long_, short = short, long_
    return {"root": root, "session": session, "type": kind, "tag": tag,
            "legs": [{"side": "long", "right": right, "dte": dte, "strike": long_},
                     {"side": "short", "right": right, "dte": dte, "strike": short}]}


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class StockSplits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-splits-")
        w = synth.Writer(cls.dir)
        w.calendar(D)
        c = lambda exp, k, right, quotes: {"expiration": exp, "strike": k, "right": right, "quotes": quotes}  # noqa: E731
        # Before the split: ACME at 300, the 300/305 calls to D[4], and a put pair and a call expiring on the eve (whose
        # quotes stop at 14:50 there, so the House cannot close them and an in-the-money short put is assigned).
        synth.flat_day(w, "ACME", D[0], [c(D[4], 300, "C", {571: (5.00, 5.20)}), c(D[4], 305, "C", {571: (2.90, 3.00)}),
                                         c(D[1], 305, "P", {571: (6.00, 6.20)}), c(D[1], 295, "P", {571: (0.90, 1.00)})],
                       prices=300.0)
        synth.flat_day(w, "ACME", D[1], [c(D[4], 300, "C", {571: (6.00, 6.20)}), c(D[4], 305, "C", {571: (3.40, 3.50)}),
                                         c(D[1], 305, "P", {571: (5.10, 5.30), 890: (None, None)}),
                                         c(D[1], 295, "P", {571: (0.05, 0.10), 890: (None, None)}),
                                         c(D[1], 300, "C", {571: (1.00, 1.10)})],
                       prices=300.0)
        # From the split: ACME at 100; the chain lists the new strikes only (the old 300/305 keys are gone).
        for day in D[2:]:
            synth.flat_day(w, "ACME", day, [c(D[4], 100, "C", {571: (2.00, 2.10)}), c(D[4], 102, "C", {571: (1.00, 1.05)})],
                           prices=100.0)
        for day in D:
            synth.flat_day(w, "SPY", day, [c(D[4], 400, "C", {571: (3.00, 3.10)}), c(D[4], 405, "C", {571: (1.00, 1.05)})],
                           prices=402.0)
        w.finish()
        cls.store = S.Store(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_opens(self, opens, roots=("ACME", "SPY"), days=None, splits=True):
        program = opener(opens)
        cfg = E.RunConfig(window="train", roots=roots)
        if splits:
            [r] = E.run([program], self.store, cfg, days=days)
        else:  # the engine before the fix: no split calendar
            with mock.patch.object(E, "split_eves", return_value={}):
                [r] = E.run([program], self.store, cfg, days=days)
        self.assertEqual(r["status"], "ok", r["runtime"])
        return r

    def test_the_split_is_found_from_the_underlying(self):
        self.assertEqual(E.split_eves(self.store, ["ACME", "SPY"], D), {D[1]: {"ACME": 3.0}})
        self.assertEqual(E.split_eves(self.store, ["ACME"], D[:2]), {})   # the run's own days only
        self.assertEqual(E.split_eves(self.store, ["ACME"], D[2:]), {})
        self.assertEqual(self.store.price_ends("ACME", D[1]), (300.0, 300.0))

    def test_split_factor(self):
        # Ratios of the prior session's last price to the next session's first: the public factors of recent splits
        # (2, 3, 10, 20 for 1) with an overnight move on top, a 1-for-10 reverse split, and ordinary gaps.
        for before, after, want in ((300.0, 100.0, 3.0), (300.0, 104.0, 3.0), (200.0, 95.0, 2.0), (1000.0, 103.0, 10.0),
                                    (2000.0, 98.0, 20.0), (10.0, 100.0, 0.1), (5.0, 48.0, 0.1)):
            self.assertEqual(E.split_factor(before, after), want, (before, after))
        for before, after in ((100.0, 100.0), (100.0, 70.0), (141.0, 100.0), (100.0, 138.0), (240.0, 100.0), (100.0, 0.0),
                              (float("nan"), 1.0), (None, 1.0), (1e6, 1.0)):
            self.assertIsNone(E.split_factor(before, after), (before, after))
        self.assertEqual((E.split_label(3.0), E.split_label(0.1)), ("3-for-1", "1-for-10"))

    def test_a_position_held_into_the_split_is_closed_on_the_eve_at_the_natural(self):
        opens = [vertical("ACME", 0, 4, 300, 305, "held")]
        # Before the fix: held into the split, never marked again, expired against 100: -2.30 x 100 - 0.10 of fees.
        [t] = self.run_opens(opens, splits=False)["trades"]
        self.assertEqual((t["exit_reason"], t["exit_day"], t["pnl"]), ("expired", "2023-03-10", -230.10))
        # Now: bought D0 at the natural 2.30 (5.20 - 2.90; fees 0.05 + 0.05), closed at the eve's last minute at its
        # natural 2.50 (6.00 - 3.50; fees 0.06 selling at 6.00 with the SEC fee, 0.05): +20.00 - 0.21.
        r = self.run_opens(opens)
        [t] = r["trades"]
        self.assertEqual((t["exit_reason"], t["day"], t["exit_day"], t["exit_minute"]), ("stock_split", "2023-03-06", "2023-03-07", 959))
        self.assertEqual((t["entry"], t["exit"], t["fees"], t["pnl"]), (2.30, 2.50, 0.21, 19.79))
        self.assertAlmostEqual(sum(d[1] for d in r["daily"]), 19.79, places=6)
        self.assertEqual([round(d[1], 2) for d in r["daily"]][2:], [0.0, 0.0, 0.0])   # nothing is held after the eve
        self.assertEqual(r["breakdown"]["exit_reason"]["stock_split"]["n"], 1)

    def test_a_close_with_no_quote_left_takes_the_mark(self):
        # No leg quoted in the eve's last half hour: the close takes the last mark, with no fee (`stock_split_mark`).
        acct = E.Account(opener([]), E.RunConfig(window="train", roots=("ACME",)), ("ACME",))
        pos = mock.MagicMock(root="ACME", qty=2, last_mark=1.25, entry=2.0, cash=-400.0, fees=0.0, exit_value_qty=0.0,
                             closing=0, pid=7, info={})
        pos.legs_today.return_value = ()
        day = mock.MagicMock(chains={}, minutes=391, ordinal=19423)
        with mock.patch.object(acct, "_finish") as finish:
            acct._split_close(day, pos)
        finish.assert_called_once()
        self.assertEqual((pos.reason, pos.qty, pos.exit_mi, pos.cash, pos.fees), ("stock_split_mark", 0, 389, -150.0, 0.0))

    def test_no_opening_order_is_held_across_the_split(self):
        opens = [vertical("ACME", 1, 3, 300, 305, "across"),                                  # the eve, to D[4]: refused
                 {"root": "ACME", "session": 1, "type": "long_call", "tag": "same day",       # the eve, expiring the eve
                  "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 300}]},
                 vertical("ACME", 2, 2, 100, 102, "after")]                                  # the split day itself
        r = self.run_opens(opens)
        self.assertEqual(r["fills"]["reject_reasons"], {"stock split": 1})
        self.assertEqual(sorted((t["tag"], t["day"], t["exit_day"]) for t in r["trades"]),
                         [("after", "2023-03-08", "2023-03-10"), ("same day", "2023-03-07", "2023-03-07")])
        # Before the fix the eve's open went through (and expired worthless against 100).
        before = self.run_opens(opens, splits=False)
        self.assertEqual(before["fills"]["rejected"], 0)
        self.assertIn(("across", "expired"), [(t["tag"], t["exit_reason"]) for t in before["trades"]])

    def test_only_the_splitting_root_is_touched(self):
        opens = [vertical("ACME", 0, 4, 300, 305, "acme"), vertical("SPY", 0, 4, 400, 405, "spy"),
                 vertical("SPY", 1, 3, 400, 405, "spy eve")]
        after, before = self.run_opens(opens), self.run_opens(opens, splits=False)
        acme = [t for t in after["trades"] if t["root"] == "ACME"]
        self.assertEqual([(t["exit_reason"], t["exit_day"]) for t in acme], [("stock_split", "2023-03-07")])
        # SPY's trades (one opened on ACME's eve) are the same trades, to the byte.
        spy = lambda r: RS.canonical([t for t in r["trades"] if t["root"] == "SPY"])  # noqa: E731
        self.assertEqual(spy(after), spy(before))
        self.assertEqual(len([t for t in after["trades"] if t["root"] == "SPY"]), 2)
        # A program on SPY alone, run in one batch with the ACME program (so the day's split calendar names ACME): its
        # whole result is the same, to the byte, with or without the split calendar.
        programs = lambda: [opener(opens, name="both"), opener(opens, roots=("SPY",), name="spy")]  # noqa: E731
        cfg = E.RunConfig(window="train", roots=("ACME", "SPY"))
        both, alone = E.run(programs(), self.store, cfg)
        with mock.patch.object(E, "split_eves", return_value={}):
            _, alone_before = E.run(programs(), self.store, cfg)
        self.assertEqual([t["root"] for t in alone["trades"]], ["SPY", "SPY"])
        self.assertEqual(alone["result_sha"], alone_before["result_sha"])
        self.assertEqual(RS.canonical(both["trades"]), RS.canonical(after["trades"]))

    def test_assigned_shares_are_not_carried_into_the_split(self):
        # A put credit spread expiring on the eve: its quotes stop at 14:50, so the House cannot close it and the short
        # 305 put is assigned at 300 (100 shares). Before the fix the shares were marked to the split session's first
        # price, 100: a 20,000 loss that never happened. Now they are marked at the eve's level, as at a window's end.
        opens = [vertical("ACME", 0, 1, 295, 305, "assigned", right="P", kind="credit_vertical")]
        [t] = self.run_opens(opens, splits=False)["trades"]
        self.assertEqual((t["exit_reason"], t["pnl"]), ("exercised", -20000.11))
        [t] = self.run_opens(opens)["trades"]
        # Credit 5.00 (6.00 - 1.00; fees 0.06 + 0.05), assigned for 5.00 of intrinsic, the shares at the eve's level.
        self.assertEqual((t["exit_reason"], t["exit_day"], t["pnl"]), ("exercised", "2023-03-07", -0.11))

    def test_a_run_that_ends_on_the_eve_does_not_look_past_it(self):
        [t] = self.run_opens([vertical("ACME", 0, 4, 300, 305, "held")], days=D[:2])["trades"]
        self.assertEqual(t["exit_reason"], "window_end")


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class NoSplitIsByteIdentical(unittest.TestCase):
    """A run that never meets a split returns the same result, to the byte, as the engine before splits were handled
    (the same run with no split calendar): the determinism suite's store and programs, one run and a split Train batch."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-nosplit-")
        cls.days = synth.weekdays(dt.date(2023, 5, 1), 8)
        synth.generate(cls.dir, roots=("SPY", "QQQ"), days=cls.days, strikes_each_side=10, max_dte=4, seed=11)
        cls.store = S.Store(cls.dir)
        cls.model = synth.uniform_model(0.08, ("SPY", "QQQ"), levels=(2, 3), size=5)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def programs(self):
        return [R.load_program((EXAMPLES / "condor_vrp.py").read_text(), name="condor", params={"vrp_min": 0.5}),
                R.load_program((EXAMPLES / "putspread_dip.py").read_text(), name="dip", params={"trend_days": 2, "dip_pct": 0.05}),
                R.load_program(MID_TRADER, name="mid"), R.load_program(MID_TRADER.replace('"SPY"', '"QQQ"'), name="mid qqq")]

    def test_no_split_calendar_changes_nothing(self):
        self.assertEqual(E.split_eves(self.store, ["SPY", "QQQ"], self.days), {})
        cfg = E.RunConfig(window="train", roots=("SPY", "QQQ"), fill_model=self.model)
        after = E.run(self.programs(), self.store, cfg)
        with mock.patch.object(E, "split_eves", return_value={}):
            before = E.run(self.programs(), self.store, cfg)
        self.assertEqual([r["result_sha"] for r in after], [r["result_sha"] for r in before])
        self.assertGreater(sum(r["summary"]["trades"] for r in after), 0)
        self.assertEqual(RS.canonical([r["trades"] for r in after]), RS.canonical([r["trades"] for r in before]))

    def test_a_split_train_batch_is_unchanged(self):
        from league.gym import batch as B
        jobs = [("mid", MID_TRADER, {"k": 1}), ("condor", (EXAMPLES / "condor_vrp.py").read_text(), {"vrp_min": 0.5})]
        run = lambda: B.run_batch(jobs, store_root=self.dir, window="train", roots=["SPY", "QQQ"], split=2,  # noqa: E731
                                  stress_twin=False, _raw=True, workers=1)["results"]
        after = run()
        with mock.patch.object(E, "split_eves", return_value={}):
            before = run()
        self.assertEqual([r["result_sha"] for r in after], [r["result_sha"] for r in before])


if __name__ == "__main__":
    unittest.main()
