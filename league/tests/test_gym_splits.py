"""Stock splits in the Gym (Sept 28, 2026): a position on a single name held into a split session could be neither marked
nor closed (the OCC's adjusted contracts are not in the chain under the old keys) and expired against the post-split
price. Now the public split table (`events.SPLITS`) closes every position on the root on the split's eve at the natural
and keeps any opening order from being held across it, without a word to the program; the price ratio only raises an
alert (a crash is not a split). Synthetic stores only: the names ACME and CRSH, their prices and quotes are made up;
split factors are public facts."""

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
    from league.gym import events as EV
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


# Opens a 3-day ACME call at 10:00 of each session (refused silently on a split's eve); the first time it sees any text
# in ctx.rejects it opens a SPY put spread tagged with it: a trade tagged "saw:" is a refusal the program was told of.
SNOOP = '''
NEEDS = {"roots": ["ROOT", "SPY"], "dte": [0, 10], "band": 0.3, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"told": False}
def decide(ctx):
    out = []
    for r in ctx.rejects:
        if not STATE["told"]:
            STATE["told"] = True
            out.append({"open": "debit_vertical", "root": "SPY", "qty": 1, "tag": "saw: " + r[:60],
                        "legs": [{"side": "long", "right": "P", "dte": 0, "strike": 400}, {"side": "short", "right": "P", "dte": 0, "strike": 395}]})
    if ctx.minute == 600 and "ROOT" in ctx.chains:
        out.append({"open": "long_call", "root": "ROOT", "qty": 1, "tag": "probe",
                    "legs": [{"side": "long", "right": "C", "dte": 3, "strike": STRIKE}]})
    return out
'''


def snoop(root, strike):
    return R.load_program(SNOOP.replace("ROOT", root).replace("STRIKE", repr(float(strike))), name="snoop")


# Mon-Fri; ACME splits 3-for-1 at the open of D[2] (in the table while these tests run), so D[1] is the eve.
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
    ACME = ("ACME", dt.date(2023, 3, 8), 3.0)

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-splits-")
        w = synth.Writer(cls.dir)
        w.calendar(D)
        c = lambda exp, k, right, quotes: {"expiration": exp, "strike": k, "right": right, "quotes": quotes}  # noqa: E731
        # Before the split: ACME at 300, the 300/305 and 290/310 calls to D[4], and a put pair and a call expiring on the
        # eve. On the eve the put pair's quotes stop at 14:50 (so the House cannot close it and an in-the-money short put
        # is assigned) and the 290 call's at 15:00 (so no minute of the last half hour quotes both 290 and 310).
        synth.flat_day(w, "ACME", D[0], [c(D[4], 300, "C", {571: (5.00, 5.20)}), c(D[4], 305, "C", {571: (2.90, 3.00)}),
                                         c(D[4], 290, "C", {571: (12.00, 12.20)}), c(D[4], 310, "C", {571: (1.90, 2.00)}),
                                         c(D[1], 305, "P", {571: (6.00, 6.20)}), c(D[1], 295, "P", {571: (0.90, 1.00)})],
                       prices=300.0)
        synth.flat_day(w, "ACME", D[1], [c(D[4], 300, "C", {571: (6.00, 6.20)}), c(D[4], 305, "C", {571: (3.40, 3.50)}),
                                         c(D[4], 290, "C", {571: (13.00, 13.20), 900: (None, None)}),
                                         c(D[4], 310, "C", {571: (2.40, 2.50)}),
                                         c(D[1], 305, "P", {571: (5.10, 5.30), 890: (None, None)}),
                                         c(D[1], 295, "P", {571: (0.05, 0.10), 890: (None, None)}),
                                         c(D[1], 300, "C", {571: (1.00, 1.10)})],
                       prices=300.0)
        # From the split: ACME at 100; the chain lists the new strikes only (the old keys are gone).
        for day in D[2:]:
            synth.flat_day(w, "ACME", day, [c(D[4], 100, "C", {571: (2.00, 2.10)}), c(D[4], 102, "C", {571: (1.00, 1.05)})],
                           prices=100.0)
        for day in D:
            synth.flat_day(w, "SPY", day, [c(D[4], 400, "C", {571: (3.00, 3.10)}), c(D[4], 405, "C", {571: (1.00, 1.05)}),
                                           c(D[4], 400, "P", {571: (3.00, 3.10)}), c(D[4], 395, "P", {571: (1.00, 1.05)})],
                           prices=402.0)
        w.finish()
        cls.store = S.Store(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        patcher = mock.patch.object(EV, "SPLITS", EV.SPLITS + (self.ACME,))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_opens(self, opens, roots=("ACME", "SPY"), days=None, splits=True):
        program = opener(opens)
        cfg = E.RunConfig(window="train", roots=roots)
        if splits:
            [r] = E.run([program], self.store, cfg, days=days)
        else:  # the engine before the fix: no split in the table
            with mock.patch.object(EV, "SPLITS", ()):
                [r] = E.run([program], self.store, cfg, days=days)
        self.assertEqual(r["status"], "ok", r["runtime"])
        return r

    def test_the_eve_comes_from_the_table(self):
        self.assertEqual(E.split_eves(self.store, ["ACME", "SPY"], D),
                         [{"root": "ACME", "ex_date": "2023-03-08", "factor": 3.0, "eve": D[1]}])
        self.assertEqual(E.split_eves(self.store, ["ACME"], D[:2])[0]["eve"], D[1])   # a run ending on the eve: the calendar
        self.assertEqual(E.split_eves(self.store, ["ACME"], D[:1]), [])              # one ending before it: not its split
        self.assertEqual(E.split_eves(self.store, ["ACME"], D[2:]), [])
        self.assertEqual(E.split_eves(self.store, ["SPY"], D), [])
        with mock.patch.object(EV, "SPLITS", ()):
            self.assertEqual(E.split_eves(self.store, ["ACME", "SPY"], D), [])       # the prices alone close nothing
        self.assertEqual(self.store.price_ends("ACME", D[1]), (300.0, 300.0))

    def test_the_price_cross_check_only_alerts(self):
        self.assertEqual(E.split_check(self.store, ["ACME", "SPY"], D), [])          # the table and the prices agree
        with mock.patch.object(EV, "SPLITS", ()):                                    # a split the table lacks
            self.assertEqual(E.split_check(self.store, ["ACME", "SPY"], D),
                             [{"root": "ACME", "day": "2023-03-08", "prior_day": "2023-03-07", "ratio": 3.0, "table": None,
                               "prices": 3.0}])
        with mock.patch.object(EV, "SPLITS", (("ACME", D[3], 3.0),)):                # a table date the prices contradict
            self.assertEqual([(a["day"], a["table"], a["prices"]) for a in E.split_check(self.store, ["ACME"], D)],
                             [("2023-03-08", None, 3.0), ("2023-03-09", 3.0, None)])
        # In a run, an alert is recorded in the result and nothing else changes.
        opens = [vertical("ACME", 0, 4, 300, 305, "held")]
        with mock.patch.object(EV, "SPLITS", ()):
            [r] = E.run([opener(opens)], self.store, E.RunConfig(window="train", roots=("ACME", "SPY")))
        self.assertEqual(r["stock_splits"], {"alerts": [{"root": "ACME", "day": "2023-03-08", "prior_day": "2023-03-07",
                                                         "ratio": 3.0, "table": None, "prices": 3.0}]})
        self.assertEqual([t["exit_reason"] for t in r["trades"]], ["expired"])

    def test_the_table_is_part_of_every_run_identity_and_the_cli_checks_it(self):
        with_acme = E.tables_digest()
        with mock.patch.object(EV, "SPLITS", ()):
            self.assertNotEqual(E.tables_digest(), with_acme)
        from league.gym import batch as B
        args = ["--split-check", "--window", "train", "--roots", "ACME,SPY", "--store", self.dir]
        with mock.patch("sys.stdout"):
            self.assertEqual(B.main(args), B.EXIT_OK)
            with mock.patch.object(EV, "SPLITS", ()):
                self.assertEqual(B.main(args), B.EXIT_SPLITS)

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
        self.assertEqual(r["stock_splits"], {"applied": [{"root": "ACME", "ex_date": "2023-03-08", "factor": 3.0, "eve": "2023-03-07"}]})

    def test_with_no_minute_quoting_every_leg_each_leg_closes_on_its_own(self):
        # The 290 call's quotes stop at 15:00 on the eve: no minute of the last half hour quotes both legs. The 310 call
        # is bought back at its ask 2.50 (fee 0.05); the 290 call, with no quote, is sold at its intrinsic value at the
        # eve's level, 300 - 290 = 10.00 (fee 0.07 with the SEC fee): 7.50 against the 10.30 paid (12.20 - 1.90, fees
        # 0.05 + 0.05): -280.00 - 0.22.
        [t] = self.run_opens([vertical("ACME", 0, 4, 290, 310, "legs")])["trades"]
        self.assertEqual((t["exit_reason"], t["exit_day"], t["exit_minute"]), ("stock_split_legs", "2023-03-07", 959))
        self.assertEqual((t["entry"], t["exit"], t["fees"], t["pnl"]), (10.30, 7.50, 0.22, -280.22))

    def test_no_opening_order_is_held_across_the_split_and_the_program_is_not_told(self):
        opens = [vertical("ACME", 1, 3, 300, 305, "across"),                                  # the eve, to D[4]: refused
                 {"root": "ACME", "session": 1, "type": "long_call", "tag": "same day",       # the eve, expiring the eve
                  "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 300}]},
                 vertical("ACME", 2, 2, 100, 102, "after")]                                  # the split day itself
        r = self.run_opens(opens)
        self.assertEqual(r["fills"]["reject_reasons"], {"stock split": 1})               # counted for the operator
        self.assertEqual(sorted((t["tag"], t["day"], t["exit_day"]) for t in r["trades"]),
                         [("after", "2023-03-08", "2023-03-10"), ("same day", "2023-03-07", "2023-03-07")])
        # Before the fix the eve's open went through (and expired worthless against 100).
        before = self.run_opens(opens, splits=False)
        self.assertEqual(before["fills"]["rejected"], 0)
        self.assertIn(("across", "expired"), [(t["tag"], t["exit_reason"]) for t in before["trades"]])
        # A program that acts on anything in ctx.rejects: its eve probe is refused, and it never hears of it.
        # (From the split day no expiry is 3 days out: those refusals are ordinary, and said.)
        [r] = E.run([snoop("ACME", 300)], self.store, E.RunConfig(window="train", roots=("ACME", "SPY")))
        self.assertEqual(r["fills"]["reject_reasons"], {"no quoted expiry at or after 3 days": 3, "stock split": 1})
        self.assertEqual([(t["tag"], t["day"]) for t in r["trades"] if t["tag"] != "probe"],
                         [("saw: no quoted expiry at or after 3 days", "2023-03-08")])     # told first on the split day
        self.assertEqual([(t["day"], t["exit_reason"]) for t in r["trades"] if t["tag"] == "probe"],
                         [("2023-03-06", "stock_split")])

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
        # A program on SPY alone, run in one batch with the ACME program (so the day's split applies to ACME): its whole
        # result is the same, to the byte, as with no split handling at all.
        programs = lambda: [opener(opens, name="both"), opener(opens, roots=("SPY",), name="spy")]  # noqa: E731
        cfg = E.RunConfig(window="train", roots=("ACME", "SPY"))
        both, alone = E.run(programs(), self.store, cfg)
        with mock.patch.object(E, "split_eves", return_value=[]), mock.patch.object(E, "split_alert", return_value=None):
            _, alone_before = E.run(programs(), self.store, cfg)
        self.assertEqual([t["root"] for t in alone["trades"]], ["SPY", "SPY"])
        self.assertNotIn("stock_splits", alone)
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

    def test_a_run_that_ends_on_the_eve_closes_there_too(self):
        # The split is public, so a run (or a segment) whose last day is the eve closes at the natural there, as the
        # whole window does, never at the window's end or a segment's mid.
        [t] = self.run_opens([vertical("ACME", 0, 4, 300, 305, "held")], days=D[:2])["trades"]
        self.assertEqual((t["exit_reason"], t["pnl"]), ("stock_split", 19.79))


class TheTable(unittest.TestCase):
    def test_the_public_splits(self):
        # Public facts (root, ex-date, factor): 2022-25 confirmed in the Gym image's prices and against the issuers'
        # notices; 2020-21 (names the 2020-24 image holds from 2022 only) against the issuers' notices and a public
        # split history.
        from league.gym import events
        self.assertEqual([(r, d.isoformat(), f) for r, d, f in events.SPLITS],
                         [("AAPL", "2020-08-31", 4.0), ("TSLA", "2020-08-31", 5.0), ("TQQQ", "2021-01-21", 2.0),
                          ("SOXL", "2021-03-02", 15.0), ("NVDA", "2021-07-20", 4.0),
                          ("TQQQ", "2022-01-13", 2.0), ("AMZN", "2022-06-06", 20.0), ("GOOGL", "2022-07-18", 20.0),
                          ("TSLA", "2022-08-25", 3.0), ("SMH", "2023-05-05", 2.0), ("NVDA", "2024-06-10", 10.0),
                          ("SMCI", "2024-10-01", 10.0), ("TQQQ", "2025-11-20", 2.0)])
        self.assertTrue(all(d.weekday() < 5 for _, d, _ in events.SPLITS))
        self.assertEqual(list(events.SPLITS), sorted(events.SPLITS, key=lambda s: s[1]))


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class ACrashIsNotASplit(unittest.TestCase):
    """The review of #406: an overnight crash of 52% on a name the table has no split for reads like a 2-for-1 in the
    prices. Nothing closes early, no order is refused, the program is told nothing; the result carries an alert."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-crash-")
        w = synth.Writer(cls.dir)
        w.calendar(D)
        c = lambda exp, k, right, quotes: {"expiration": exp, "strike": k, "right": right, "quotes": quotes}  # noqa: E731
        pre = [c(D[4], 95, "P", {571: (1.60, 1.70)}), c(D[4], 90, "P", {571: (0.55, 0.65)}), c(D[4], 100, "C", {571: (2.0, 2.1)})]
        post = [c(D[4], 95, "P", {571: (46.8, 47.2)}), c(D[4], 90, "P", {571: (41.8, 42.2)}), c(D[4], 100, "C", {571: (0.0, 0.05)})]
        synth.flat_day(w, "CRSH", D[0], pre, prices=100.0)
        synth.flat_day(w, "CRSH", D[1], pre, prices=100.0)
        for day in D[2:]:
            synth.flat_day(w, "CRSH", day, post, prices=48.0)      # -52% overnight; the same contracts stay listed
        for day in D:
            synth.flat_day(w, "SPY", day, [c(D[4], 400, "P", {571: (3.00, 3.10)}), c(D[4], 395, "P", {571: (1.00, 1.05)})],
                           prices=402.0)
        w.finish()
        cls.store = S.Store(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_a_crash_closes_nothing_early_and_says_nothing(self):
        seller = R.load_program(OPENER.replace("ROOTS", repr(["CRSH"])).replace("LIST", repr(
            [vertical("CRSH", 0, 4, 90, 95, "short put spread", right="P", kind="credit_vertical")])), name="seller")
        cfg = E.RunConfig(window="train", roots=("CRSH", "SPY"))
        sell, probe = E.run([seller, snoop("CRSH", 100)], self.store, cfg)
        # The short put spread rides the crash: closed by the House on its expiry day at the natural, as on main.
        self.assertEqual([(t["exit_reason"], t["exit_day"], t["pnl"]) for t in sell["trades"]],
                         [("expiry_close", "2023-03-10", -405.28)])   # #404: the -5.40 buy-back closes at the width, -5.00
        # The probe opens every session it can (3 days out: D0 and D1 only), the eve included; no text reaches the program.
        self.assertEqual([(t["tag"], t["day"], t["exit_reason"]) for t in probe["trades"] if t["root"] == "CRSH"],
                         [("probe", "2023-03-06", "expired"), ("probe", "2023-03-07", "expired")])
        self.assertEqual(probe["fills"]["reject_reasons"], {"no quoted expiry at or after 3 days": 3})
        self.assertEqual([(t["tag"], t["day"]) for t in probe["trades"] if t["root"] == "SPY"],
                         [("saw: no quoted expiry at or after 3 days", "2023-03-08")])   # the ordinary refusals only
        # The only trace: the alert in each CRSH result, for the operator (the table lacks a split the prices suggest).
        alert = {"alerts": [{"root": "CRSH", "day": "2023-03-08", "prior_day": "2023-03-07", "ratio": 2.0833, "table": None,
                             "prices": 2.0}]}
        self.assertEqual((sell["stock_splits"], probe["stock_splits"]), (alert, alert))
        # And everything else is what the engine without split handling returns.
        with mock.patch.object(E, "split_eves", return_value=[]), mock.patch.object(E, "split_alert", return_value=None):
            plain = E.run([R.load_program(seller.code, name="seller"), snoop("CRSH", 100)], self.store, cfg)
        def strip(r):  # the alert, and what hashes or times it
            out = {k: v for k, v in r.items() if k not in ("stock_splits", "result_sha", "seconds")}
            out["runtime"] = {k: v for k, v in r["runtime"].items() if k != "decide_seconds"}
            return RS.canonical(out)
        for now, then in zip((sell, probe), plain):
            self.assertEqual(strip(now), strip(then))


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
        self.assertEqual(E.split_eves(self.store, ["SPY", "QQQ"], self.days), [])
        self.assertEqual(E.split_check(self.store, ["SPY", "QQQ"], self.days), [])
        cfg = E.RunConfig(window="train", roots=("SPY", "QQQ"), fill_model=self.model)
        after = E.run(self.programs(), self.store, cfg)
        with mock.patch.object(E, "split_eves", return_value=[]), mock.patch.object(E, "split_alert", return_value=None):
            before = E.run(self.programs(), self.store, cfg)
        self.assertFalse(any("stock_splits" in r for r in after))
        self.assertEqual([r["result_sha"] for r in after], [r["result_sha"] for r in before])
        self.assertGreater(sum(r["summary"]["trades"] for r in after), 0)
        self.assertEqual(RS.canonical([r["trades"] for r in after]), RS.canonical([r["trades"] for r in before]))

    def test_a_split_train_batch_is_unchanged(self):
        from league.gym import batch as B
        jobs = [("mid", MID_TRADER, {"k": 1}), ("condor", (EXAMPLES / "condor_vrp.py").read_text(), {"vrp_min": 0.5})]
        run = lambda: B.run_batch(jobs, store_root=self.dir, window="train", roots=["SPY", "QQQ"], split=2,  # noqa: E731
                                  stress_twin=False, _raw=True, workers=1)["results"]
        after = run()
        with mock.patch.object(E, "split_eves", return_value=[]), mock.patch.object(E, "split_alert", return_value=None):
            before = run()
        self.assertEqual([r["result_sha"] for r in after], [r["result_sha"] for r in before])


if __name__ == "__main__":
    unittest.main()
