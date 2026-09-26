"""The venue's clock in the Gym: expiry cutoffs, the House's expiry close of near-the-money equity
structures, the 15:30 liquidation, far out-of-the-money structures left to expire, exercise into shares
marked to the next open, cash settlement (see test_gym_pnl), and a half day. Synthetic stores only."""

import datetime as dt
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

OPEN_AT = '''
NEEDS = {"roots": ["ROOT"], "dte": [0, 3], "band": 0.2, "cadence": 1, "start": 600}
PARAMS = {"open_at": [600], "close_at": [], "structure": "debit_vertical", "low": 400}
STATE = {"done": []}
def decide(ctx):
    out = []
    p = ctx.params
    if ctx.minute in p["open_at"] and ctx.minute not in STATE["done"]:
        STATE["done"].append(ctx.minute)
        if p["structure"] == "debit_vertical":
            legs = [{"side": "long", "right": "C", "dte": 0, "strike": p["low"]},
                    {"side": "short", "right": "C", "dte": 0, "strike": p["low"] + 1}]
        else:
            legs = [{"side": "short", "right": "P", "dte": 0, "strike": 400}, {"side": "long", "right": "P", "dte": 0, "strike": 399}]
        out.append({"open": p["structure"], "legs": legs, "qty": 1})
    if ctx.minute in p["close_at"]:
        for pos in ctx.positions:
            out.append({"close": pos["id"]})
    return out
'''


def program(root, **params):
    return R.load_program(OPEN_AT.replace("ROOT", root), name=f"{root}-{sorted(params)}", params=params)


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class VenueClock(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gym-venue-")
        w = synth.Writer(self.dir)
        w.calendar([D1, D2, D3], half_days=[D3])
        for root in ("SPY", "IWM"):
            synth.flat_day(w, root, D1, [
                {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10), 930: (2.50, 2.60)}},
                {"expiration": D1, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.50), 930: (1.60, 1.70)}},
                # The put vertical's quotes stop at 15:00 (no rows from 900): neither the House's expiry close nor
                # the venue's liquidation can fill it.
                {"expiration": D1, "strike": 400, "right": "P", "quotes": {571: (0.60, 0.65), 900: (None, None)}},
                {"expiration": D1, "strike": 399, "right": "P", "quotes": {571: (0.20, 0.25), 900: (None, None)}},
                # A call vertical over 2% out of the money all day: never near the money.
                {"expiration": D1, "strike": 410, "right": "C", "quotes": {571: (0.10, 0.12)}},
                {"expiration": D1, "strike": 411, "right": "C", "quotes": {571: (0.05, 0.07)}},
            ], prices={570: 400.5, 940: 399.50})
            synth.flat_day(w, root, D2, [
                {"expiration": D2, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.10)}}], prices={570: 398.00, 700: 401.0})
        # QQQ on D1: the 410/411 call vertical is far from the money through the House's window (15:15-15:24)
        # and comes within 1% of it at 15:28 (406.00 against the 410 strike: 0.98%).
        synth.flat_day(w, "QQQ", D1, [
            {"expiration": D1, "strike": 410, "right": "C", "quotes": {571: (0.10, 0.12), 928: (0.60, 0.65)}},
            {"expiration": D1, "strike": 411, "right": "C", "quotes": {571: (0.05, 0.07), 928: (0.40, 0.45)}},
        ], prices={570: 400.5, 928: 406.0})
        # D3 is a half day (close 13:00): the same offsets from 13:00.
        synth.flat_day(w, "SPY", D3, [
            {"expiration": D3, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10), 750: (2.40, 2.50)}},
            {"expiration": D3, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.50), 750: (1.60, 1.70)}},
        ], prices=400.5, close_min=780)
        w.finish()
        self.store = S.Store(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_one(self, prog, roots, days=None):
        [r] = E.run([prog], self.store, E.RunConfig(window="train", roots=roots), days=days)
        self.assertEqual(r["status"], "ok", r["runtime"])
        return r

    def test_rules_table(self):
        spy, iwm, xsp = venue.rules_for("SPY"), venue.rules_for("IWM"), venue.rules_for("XSP")
        self.assertEqual((spy.open_cutoff, spy.expiry_close, spy.close_cutoff, spy.liquidation), (900, 915, 925, 930))
        self.assertEqual((iwm.open_cutoff, iwm.expiry_close, iwm.close_cutoff, iwm.liquidation), (900, 900, 910, 930))
        self.assertEqual((xsp.kind, xsp.expiry_close, xsp.liquidation, xsp.calendars), ("index", None, None, False))
        half = venue.rules_for("SPY", close_minute=780)
        self.assertEqual((half.open_cutoff, half.expiry_close, half.close_cutoff, half.liquidation), (720, 735, 745, 750))
        self.assertEqual(spy.as_dict()["near_money_share"], 0.01)

    def test_near_the_money_is_the_live_paths_predicate(self):
        # In the money, or out of it by at most 1% of the strike (league/live/step.py `_near_money`).
        self.assertTrue(venue.near_money(400, True, 400.5))
        self.assertTrue(venue.near_money(404, True, 400.0))      # 400 >= 404 x 0.99 = 399.96
        self.assertFalse(venue.near_money(405, True, 400.0))     # 400 < 400.95
        self.assertTrue(venue.near_money(397, False, 400.0))     # 400 <= 397 x 1.01 = 400.97
        self.assertFalse(venue.near_money(396, False, 400.0))    # 400 > 399.96
        self.assertTrue(venue.near_money(410, True, float("nan")))  # no price to tell: closed

    def test_no_new_open_on_an_expiring_contract_from_1500(self):
        # 894 -> arrives 895: allowed. 899 -> arrives 900: refused.
        r = self.run_one(program("SPY", open_at=[894, 899]), ("SPY",), days=[D1])
        self.assertEqual(r["fills"]["opens"], 1)
        self.assertEqual(r["fills"]["reject_reasons"], {"expiry cutoff": 1})

    def test_close_cutoff_is_1525_for_spy_and_1510_for_iwm(self):
        # The far out-of-the-money vertical: the House leaves it alone, so the program's own close meets the cutoff.
        spy = self.run_one(program("SPY", low=410, close_at=[919]), ("SPY",), days=[D1])
        self.assertEqual(spy["trades"][0]["exit_reason"], "program")
        iwm = self.run_one(program("IWM", low=410, close_at=[919]), ("IWM",), days=[D1])
        self.assertEqual(iwm["fills"]["reject_reasons"], {"expiry cutoff": 1})
        self.assertEqual(iwm["trades"][0]["exit_reason"], "expired")
        late = self.run_one(program("SPY", low=410, close_at=[924]), ("SPY",), days=[D1])  # arrives 925: refused
        self.assertEqual(late["fills"]["reject_reasons"], {"expiry cutoff": 1})

    def test_the_house_closes_near_the_money_ten_minutes_before_the_cutoff(self):
        r = self.run_one(program("SPY"), ("SPY",), days=[D1])
        [t] = r["trades"]
        # The 400/401 call vertical (spot 400.50: the 400 call in the money) is closed at 15:15, the House's
        # expiry close for SPY (the close cutoff 15:25 less 10 minutes), at that minute's natural.
        self.assertEqual((t["exit_reason"], t["exit_minute"]), ("expiry_close", 915))
        # Entry 2.10 - 1.40 = 0.70; exit 2.00 (bid) - 1.50 (ask) = 0.50.
        self.assertEqual((t["entry"], t["exit"]), (0.70, 0.50))
        # Fees 0.05 + 0.05 open; 0.05 (sell 2.00: 0.04359 + 0.00412) + 0.05 close.
        self.assertEqual(t["fees"], 0.20)
        self.assertEqual(t["pnl"], -20.20)
        self.assertEqual(r["fills"]["liquidated"], 1)
        iwm = self.run_one(program("IWM"), ("IWM",), days=[D1])
        self.assertEqual((iwm["trades"][0]["exit_reason"], iwm["trades"][0]["exit_minute"]), ("expiry_close", 900))

    def test_liquidated_at_the_natural_from_1530_when_it_comes_near_the_money(self):
        r = self.run_one(program("QQQ", low=410), ("QQQ",), days=[D1])
        [t] = r["trades"]
        # Far from the money through the House's window; within 1% from 15:28; liquidated at 15:30's natural.
        self.assertEqual((t["exit_reason"], t["exit_minute"]), ("liquidated", 930))
        # Entry 0.12 - 0.05 = 0.07; exit 0.60 (bid) - 0.45 (ask) = 0.15.
        self.assertEqual((t["entry"], t["exit"]), (0.07, 0.15))
        # Fees: open 0.05 (buy) + 0.05 (sell 0.05: 0.04359 + 0.000103); close 0.05 (sell 0.60) + 0.05 (buy).
        self.assertEqual(t["fees"], 0.20)
        self.assertEqual(t["pnl"], 7.80)
        self.assertEqual(r["fills"]["liquidated"], 1)

    def test_far_out_of_the_money_expires_at_intrinsic_with_no_fee(self):
        r = self.run_one(program("SPY", low=410), ("SPY",), days=[D1])
        [t] = r["trades"]
        # Never within 1% of the money: neither closed by the House nor liquidated; it expires at the close's
        # 399.50, both calls worthless, with no closing fee.
        self.assertEqual((t["exit_reason"], t["entry"], t["exit"]), ("expired", 0.07, 0.0))
        self.assertEqual(t["fees"], 0.10)
        self.assertEqual(t["pnl"], -7.10)                   # (0 - 0.07) x 100 - 0.10
        self.assertEqual((r["fills"]["liquidated"], r["fills"]["exercised"]), (0, 0))
        self.assertAlmostEqual(r["daily"][0][1], -7.10, places=6)

    def test_assigned_short_leg_becomes_shares_marked_to_the_next_open(self):
        r = self.run_one(program("SPY", structure="credit_vertical"), ("SPY",), days=[D1, D2])
        [t] = r["trades"]
        self.assertEqual(t["exit_reason"], "exercised")
        self.assertEqual(t["entry"], -0.35)          # 0.25 (399P ask) - 0.60 (400P bid)
        self.assertEqual(t["exit"], -0.50)           # at the close's 399.50 the short 400P is 0.50 in the money
        self.assertEqual(t["context"]["dte"], 0)
        # The short put's assignment leaves +100 shares at 399.50, sold at the next session's first price 398.00.
        self.assertEqual(t["pnl"], round(-15.0 - 0.10 - 150.0, 2))
        self.assertAlmostEqual(r["daily"][0][1], -15.10, places=6)
        self.assertAlmostEqual(r["daily"][1][1], -150.0, places=6)

    def test_half_day_expiry_close_at_1215(self):
        r = self.run_one(program("SPY"), ("SPY",), days=[D3])
        [t] = r["trades"]
        # The half day's close cutoff is 12:25; the House closes from 12:15 at the natural.
        self.assertEqual((t["exit_reason"], t["exit_minute"]), ("expiry_close", 735))
        self.assertEqual(t["exit"], 0.50)  # 2.00 - 1.50


if __name__ == "__main__":
    unittest.main()
