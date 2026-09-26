"""The Gym reproduces hand-computed P&L to the cent: a vertical, a condor and a calendar, fees included.

Every store here is synthetic and tiny (built in a temp dir by `league.gym.synth`); every expected
number is worked out by hand in the comments from the quotes the test writes. Skips cleanly when
numpy or pyarrow is absent (requirements-gym.txt).
"""

import datetime as dt
import math
import shutil
import tempfile
import unittest

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import engine as E
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth, venue

D1, D2, D3 = dt.date(2023, 3, 6), dt.date(2023, 3, 7), dt.date(2023, 3, 8)

# Buy 0.0403 a contract (OCC 0.025 + ORF 0.015 + CAT 0.0003); a sell adds TAF 0.00329 and SEC 20.6e-6 x premium x 100.
VERTICAL = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {"qty": 2}
STATE = {"opened": False}
def decide(ctx):
    if not ctx.positions and not STATE["opened"] and ctx.minute == 600:
        STATE["opened"] = True
        return [{"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 400},
                 {"side": "short", "right": "C", "dte": 0, "strike": 401}], "qty": ctx.params["qty"]}]
    if ctx.positions and ctx.minute == 720:
        return [{"close": ctx.positions[0]["id"]}]
    return []
'''

CONDOR = '''
NEEDS = {"roots": ["XSP"], "dte": [0, 3], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"opened": False}
def decide(ctx):
    if not STATE["opened"]:
        STATE["opened"] = True
        return [{"open": "iron_condor", "legs": [
            {"side": "long", "right": "P", "dte": 0, "strike": 445}, {"side": "short", "right": "P", "dte": 0, "strike": 448},
            {"side": "short", "right": "C", "dte": 0, "strike": 452}, {"side": "long", "right": "C", "dte": 0, "strike": 455}],
            "qty": 1}]
    return []
'''

CALENDAR = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 5], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"opened": False, "sessions": 0, "last": 10000}
def decide(ctx):
    if ctx.minute < STATE["last"]:
        STATE["sessions"] += 1
    STATE["last"] = ctx.minute
    if not STATE["opened"]:
        STATE["opened"] = True
        return [{"open": "calendar", "legs": [{"side": "short", "right": "C", "dte": 1, "strike": 400},
                                              {"side": "long", "right": "C", "dte": 2, "strike": 400}], "qty": 1}]
    if ctx.positions and STATE["sessions"] == 2 and ctx.minute == 700:
        return [{"close": ctx.positions[0]["id"]}]
    return []
'''

# A back-month debit vertical: NEEDS a 30-45 DTE slice; the tag records the expiries the slice showed.
BACK_MONTH = '''
NEEDS = {"roots": ["SPY"], "dte": [30, 45], "band": 0.05, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"seen": []}
def decide(ctx):
    STATE["seen"].append(",".join(str(int(x)) for x in ctx.chain.expiries))
    if not ctx.positions and not ctx.orders and len(STATE["seen"]) == 1:
        return [{"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": 30, "strike": 400},
                 {"side": "short", "right": "C", "rel": 0, "offset": 5.0}], "qty": 1, "tag": STATE["seen"][0]}]
    if ctx.positions and ctx.positions[0]["held_days"] == 1 and ctx.minute == 700:
        return [{"close": ctx.positions[0]["id"], "tag": STATE["seen"][-1]}]
    return []
'''


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class BackMonths(unittest.TestCase):
    """SPY/QQQ back months (15-45 DTE, backfill stage 6) sit in the day's NBBO file beside the 0-14 DTE
    chain: the store serves them, NEEDS asks for them, and a structure on them is held across sessions."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gym-back-")
        w = synth.Writer(self.dir)
        w.calendar([D1, D2])
        e = D1 + dt.timedelta(days=35)
        synth.flat_day(w, "SPY", D1, [
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10)}},
            {"expiration": e, "strike": 400, "right": "C", "quotes": {571: (8.00, 8.20)}},
            {"expiration": e, "strike": 405, "right": "C", "quotes": {571: (5.00, 5.20)}}], prices=402.0)
        synth.flat_day(w, "SPY", D2, [
            {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10)}},
            {"expiration": e, "strike": 400, "right": "C", "quotes": {571: (8.50, 8.70)}},
            {"expiration": e, "strike": 405, "right": "C", "quotes": {571: (5.20, 5.40)}}], prices=402.0)
        w.finish()
        self.store = S.Store(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_35_dte_vertical_held_overnight_to_the_cent(self):
        [r] = E.run([R.load_program(BACK_MONTH, name="back")], self.store, E.RunConfig(window="train", roots=("SPY",)))
        self.assertEqual(r["status"], "ok", r["runtime"])
        [t] = r["trades"]
        # The slice showed only the back month (35 days out on D1), never the 0DTE contract.
        self.assertEqual((t["tag"], t["context"]["dte"], t["sessions_held"]), ("35", 35, 1))
        # D1 600 -> 601: buy the 400 call at 8.20, sell the 405 call at 5.00: 3.20. D2 700 -> 701: sell at 8.50,
        # buy back at 5.40: 3.10.
        self.assertEqual((t["entry"], t["exit"], t["max_loss"]), (3.20, 3.10, 320.0))
        # Fees: open 0.05 (buy) + 0.06 (sell 5.00: 0.04359 + 0.0103); close 0.07 (sell 8.50: 0.04359 + 0.01751) + 0.05.
        self.assertEqual(t["fees"], 0.23)
        self.assertEqual(t["pnl"], -10.23)
        self.assertEqual(list(r["breakdown"]["dte"]), ["15+"])
        # D1 marks it at the mids (8.10 - 5.10 = 3.00); D2 realizes the rest.
        self.assertAlmostEqual(r["daily"][0][1], (3.00 - 3.20) * 100 - 0.11, places=6)
        self.assertAlmostEqual(sum(d[1] for d in r["daily"]), -10.23, places=6)

    def test_the_syntax_limit_is_60_and_is_not_coverage(self):
        with self.assertRaises(R.NeedsRefused):
            R.parse_needs({"roots": ["SPY"], "dte": [30, 61]})
        self.assertEqual(R.parse_needs({"roots": ["SPY"], "dte": [15, 45]}).dte_max, 45)
        # 50 days is legal syntax, but nothing is quoted that far out: the leg is refused, not invented.
        code = BACK_MONTH.replace('"dte": 30, "strike": 400', '"dte": 50, "strike": 400')
        [r] = E.run([R.load_program(code, name="far")], self.store, E.RunConfig(window="train", roots=("SPY",)))
        self.assertEqual(r["summary"]["trades"], 0)
        self.assertTrue(any("no quoted expiry" in k for k in r["fills"]["reject_reasons"]), r["fills"]["reject_reasons"])


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class HandComputedPnL(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gym-pnl-")
        w = synth.Writer(self.dir)
        w.calendar([D1, D2, D3])
        # SPY on D1: a 0DTE call vertical 400/401, and D1's and D2's calendar legs.
        spy = [
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10), 700: (3.00, 3.10)}},
            {"expiration": D1, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.50), 700: (1.90, 2.00)}},
            {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.05)}},
            {"expiration": D3, "strike": 400, "right": "C", "quotes": {571: (3.00, 3.10)}},
        ]
        synth.flat_day(w, "SPY", D1, spy, prices=400.5)
        synth.flat_day(w, "SPY", D2, [
            {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.05), 700: (2.10, 2.15)}},
            {"expiration": D3, "strike": 400, "right": "C", "quotes": {571: (3.00, 3.10), 700: (3.40, 3.50)}}], prices=400.5)
        synth.flat_day(w, "SPY", D3, [
            {"expiration": D3, "strike": 400, "right": "C", "quotes": {571: (0.40, 0.45)}}], prices=400.5)
        # XSP on D1: a condor 445/448/452/455 held to the cash settlement at the close's 452.30.
        xsp = [
            {"expiration": D1, "strike": 445, "right": "P", "quotes": {571: (0.10, 0.12)}},
            {"expiration": D1, "strike": 448, "right": "P", "quotes": {571: (0.40, 0.44)}},
            {"expiration": D1, "strike": 452, "right": "C", "quotes": {571: (0.50, 0.55)}},
            {"expiration": D1, "strike": 455, "right": "C", "quotes": {571: (0.15, 0.18)}},
        ]
        synth.flat_day(w, "XSP", D1, xsp, prices={570: 450.0, 960: 452.30})
        w.finish()
        self.store = S.Store(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_one(self, code, roots, **cfg):
        [result] = E.run([R.load_program(code, name="hand")], self.store, E.RunConfig(window="train", roots=roots, **cfg))
        self.assertEqual(result["status"], "ok", result["runtime"])
        return result

    def test_fee_table_by_hand(self):
        self.assertEqual(venue.leg_fee("SPY", 2, 2.10, sell=False), 0.09)   # 2 x 0.0403 = 0.0806 -> 0.09
        self.assertEqual(venue.leg_fee("SPY", 2, 1.40, sell=True), 0.10)    # 2 x 0.04359 + 0.005768 = 0.092948 -> 0.10
        self.assertEqual(venue.leg_fee("SPY", 2, 3.00, sell=True), 0.10)    # 0.08718 + 0.01236 = 0.09954 -> 0.10
        self.assertEqual(venue.leg_fee("SPY", 2, 6.00, sell=True), 0.12)    # 0.08718 + 0.02472 = 0.1119 -> 0.12
        self.assertEqual(venue.leg_fee("XSP", 1, 0.12, sell=False), 0.55)   # 0.0403 + 0.50 index fee + $0 XSP under 10
        self.assertEqual(venue.leg_fee("XSP", 1, 0.50, sell=True), 0.55)    # 0.04359 + 0.00103 + 0.50 = 0.54462 -> 0.55
        self.assertEqual(venue.leg_fee("SPXW", 1, 5.00, sell=False), 1.21)  # 0.0403 + 0.50 + 0.66 (ASSUMED) = 1.2003 -> 1.21
        self.assertEqual(venue.leg_fee("SPY", 0, 1.0, sell=True), 0.0)

    def test_debit_vertical_to_the_cent(self):
        r = self.run_one(VERTICAL, ("SPY",))
        [t] = r["trades"]
        # Decision 600 -> fill at 601: long 400C at its ask 2.10, short 401C at its bid 1.40: value 0.70, qty 2.
        self.assertEqual(t["entry"], 0.70)
        # Decision 720 -> fill at 721: long sold at its bid 3.00, short bought at its ask 2.00: value 1.00.
        self.assertEqual(t["exit"], 1.00)
        # Fees: open 0.09 + 0.10; close 0.10 (sell 2 at 3.00) + 0.09 (buy 2) = 0.38.
        self.assertEqual(t["fees"], 0.38)
        self.assertEqual(t["pnl"], 59.62)  # (1.00 - 0.70) x 100 x 2 - 0.38
        self.assertEqual(t["max_loss"], 140.0)
        self.assertEqual(t["exit_reason"], "program")
        self.assertEqual(r["summary"]["account_pnl"], 59.62)

    def test_iron_condor_cash_settled_to_the_cent(self):
        r = self.run_one(CONDOR, ("XSP",))
        [t] = r["trades"]
        # Open value: +0.12 (445P ask) - 0.40 (448P bid) - 0.50 (452C bid) + 0.18 (455C ask) = -0.60, a 0.60 credit.
        self.assertEqual(t["entry"], -0.60)
        # Max loss: the 3.00 wing less the credit, a share: 2.40 x 100.
        self.assertEqual(t["max_loss"], 240.0)
        # Settled at 452.30: only the short 452 call is in the money (0.30): value -0.30. No fee at settlement.
        self.assertEqual(t["exit"], -0.30)
        self.assertEqual(t["exit_reason"], "settled")
        # Fees: 4 legs x 0.55 (index options: 0.0403 [+ sells] + 0.50, rounded up) = 2.20.
        self.assertEqual(t["fees"], 2.20)
        self.assertEqual(t["pnl"], 27.80)  # (-0.30 + 0.60) x 100 - 2.20
        self.assertEqual(r["summary"]["account_pnl"], 27.80)

    def test_calendar_to_the_cent_across_sessions(self):
        r = self.run_one(CALENDAR, ("SPY",))
        [t] = r["trades"]
        # D1 600 -> 601: long the D3 400C at 3.10, short the D2 400C at 2.00: value 1.10 (a debit).
        self.assertEqual(t["entry"], 1.10)
        self.assertEqual(t["max_loss"], 110.0)
        # D2 700 -> 701: sell the D3 call at 3.40, buy back the D2 call at 2.15: value 1.25.
        self.assertEqual(t["exit"], 1.25)
        # Fees: open 0.05 (buy) + 0.05 (sell 2.00: 0.04359 + 0.00412); close 0.06 (sell 3.40: 0.04359 + 0.007004) + 0.05.
        self.assertEqual(t["fees"], 0.21)
        self.assertEqual(t["pnl"], 14.79)
        self.assertEqual(t["sessions_held"], 1)
        # The daily P&L sums to the trade: D1 marks the calendar at its mids (3.05 - 2.025), D2 realizes the rest.
        self.assertAlmostEqual(sum(d[1] for d in r["daily"]), 14.79, places=6)
        self.assertAlmostEqual(r["daily"][0][1], (3.05 - 2.025 - 1.10) * 100 - 0.10, places=6)

    def test_calendar_refused_on_an_index_root(self):
        code = CALENDAR.replace('"roots": ["SPY"]', '"roots": ["XSP"]')
        r = self.run_one(code, ("XSP",))
        self.assertEqual(r["summary"]["trades"], 0)
        self.assertTrue(any("index options" in k for k in r["fills"]["reject_reasons"]), r["fills"]["reject_reasons"])


if __name__ == "__main__":
    unittest.main()
