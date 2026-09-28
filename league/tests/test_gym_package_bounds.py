"""A package never trades outside what it can be worth at expiry: a blown-out leg quote cannot make a 5-wide
vertical lose many times its maximum loss.

Found Sept 28, 2026 tracing an SPXW family whose validation lost several times the maximum loss it opened: the
natural price of a structure is the sum of its legs' touches, and when one leg's quote blows out (an in-the-money
index leg quoted with no bid and a far ask, the minute of an FOMC release, the last minutes of an expiry) that sum
leaves the package's no-arbitrage range, and a stop at the natural "sold" a 5-wide debit vertical for a large
DEBIT. Every store here is synthetic and tiny (`league.gym.synth`); its quotes are made up, and every expected
number is worked out in the comments.
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
    from league.gym import legs as L
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth

D1, D2 = dt.date(2023, 3, 6), dt.date(2023, 3, 7)

# Open a 5000/5005 SPXW call debit vertical at 600 (fills at 601); close it at the natural at CLOSE_AT (fills a
# minute later). {"hold": True} never closes it (it settles, or the run's end closes it).
PROGRAM = '''
NEEDS = {"roots": ["SPXW"], "dte": [0, 3], "band": 0.2, "cadence": 1, "start": 600}
PARAMS = {"close_at": 700, "dte": 0, "hold": False}
STATE = {"opened": False}
def decide(ctx):
    p = ctx.params
    if not STATE["opened"] and ctx.minute == 600:
        STATE["opened"] = True
        return [{"open": "debit_vertical", "root": "SPXW", "legs": [
            {"side": "long", "right": "C", "dte": p["dte"], "strike": 5000},
            {"side": "short", "right": "C", "dte": p["dte"], "strike": 5005}], "qty": 1, "tif": "day"}]
    if ctx.positions and not p["hold"] and ctx.minute == p["close_at"] and not ctx.orders:
        return [{"close": ctx.positions[0]["id"], "limit": "natural", "tif": "day"}]
    return []
'''

NORMAL = {"5000": (10.00, 10.40), "5005": (7.00, 7.40)}   # natural open 10.40 - 7.00 = 3.40; natural close 2.60
BLOWN = {"5000": (0.00, 24.00), "5005": (5.00, 30.00)}    # natural close 0.00 - 30.00 = -30.00: a blown-out quote
RICH = {"5000": (20.00, 20.40), "5005": (7.00, 7.40)}     # natural close 20.00 - 7.40 = 12.60, over the 5.00 width
CROSSED = {"5000": (4.60, 5.00), "5005": (8.00, 8.40)}   # natural open 5.00 - 8.00 = -3.00: paid to buy a vertical


def day(writer, when, steps, *, expiration=None):
    """One SPXW day: {minute: quotes} steps for the 5000 and 5005 calls, spot 5002 all day."""
    exp = expiration or when
    contracts = [{"expiration": exp, "strike": int(k), "right": "C", "quotes": {m: q[k] for m, q in steps.items()}}
                 for k in ("5000", "5005")]
    synth.flat_day(writer, "SPXW", when, contracts, prices=5002.0)


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class PackageBounds(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gym-bounds-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_day(self, steps, *, expiration=None, **params):
        w = synth.Writer(self.dir)
        w.calendar([D1])
        day(w, D1, steps, expiration=expiration)
        w.finish()
        [r] = E.run([R.load_program(PROGRAM, name="bounds", params=params)], S.Store(self.dir),
                    E.RunConfig(window="train", roots=("SPXW",)))
        self.assertEqual(r["status"], "ok", r["runtime"])
        return r

    def test_value_bounds_of_each_structure(self):
        def leg(side, right, strike, ratio=1, dte=0):
            return L.LegFill(0, 0, side, ratio, dte, float(strike), right == "C")
        cases = {
            "call debit vertical": ([leg(1, "C", 100), leg(-1, "C", 105)], (0.0, 5.0)),
            "put debit vertical": ([leg(1, "P", 105), leg(-1, "P", 100)], (0.0, 5.0)),
            "put credit vertical": ([leg(-1, "P", 100), leg(1, "P", 95)], (-5.0, 0.0)),
            "iron condor, wings 3 and 3": ([leg(1, "P", 445), leg(-1, "P", 448), leg(-1, "C", 452), leg(1, "C", 455)], (-3.0, 0.0)),
            "iron condor, wings 2 and 5": ([leg(1, "P", 446), leg(-1, "P", 448), leg(-1, "C", 452), leg(1, "C", 457)], (-5.0, 0.0)),
            "long call butterfly": ([leg(1, "C", 95), leg(-1, "C", 100, 2), leg(1, "C", 105)], (0.0, 5.0)),
            "iron butterfly": ([leg(1, "P", 95), leg(-1, "P", 100), leg(-1, "C", 100), leg(1, "C", 105)], (-5.0, 0.0)),
            "long put": ([leg(1, "P", 100)], (0.0, 100.0)),
        }
        for name, (legs, want) in cases.items():
            self.assertEqual(L.value_bounds(legs), want, name)
        self.assertEqual(L.value_bounds([leg(1, "C", 100)]), (0.0, math.inf))
        self.assertEqual(L.value_bounds([leg(1, "C", 100), leg(1, "P", 100)]), (0.0, math.inf))       # a straddle
        self.assertEqual(L.value_bounds([leg(-1, "C", 100, dte=1), leg(1, "C", 100, dte=8)]), (-math.inf, math.inf))  # calendar

    def test_a_blown_out_leg_never_closes_a_vertical_below_zero(self):
        r = self.run_day({571: NORMAL, 700: BLOWN}, close_at=700)
        [t] = r["trades"]
        # Open 600 -> 601 at the natural 3.40: max loss 340. The close meets 701's quotes, whose natural is -30.00:
        # paying 30.00 to part with a vertical that is worth 0 to 5. It sells at the vertical's least, 0.00.
        self.assertEqual((t["entry"], t["max_loss"]), (3.40, 340.0))
        self.assertEqual(t["exit"], 0.0)
        self.assertEqual(t["exit_reason"], "program")
        self.assertLessEqual(-t["pnl"], t["max_loss"] + t["fees"] + 1e-9)

    def test_an_open_below_the_package_waits_for_a_real_price(self):
        # Decided at 600 on normal quotes (limit 3.40); at 601 the legs cross: the natural open is -3.00, a
        # vertical worth 0 to 5 bought for a 3.00 CREDIT. It is marketable, but no one sells a vertical for less
        # than nothing: the order keeps working and fills at 602 on normal quotes again, at 3.40.
        r = self.run_day({571: NORMAL, 601: CROSSED, 602: NORMAL}, hold=True)
        [t] = r["trades"]
        self.assertEqual(t["entry"], 3.40)
        self.assertEqual(t["filled_minute"], 602)

    def test_a_close_over_the_width_waits_for_a_real_price(self):
        # The close meets 701's natural 12.60 for a vertical worth at most 5.00: no fill (no windfall); at 702 the
        # quotes are normal again and it sells at their natural, 2.60.
        r = self.run_day({571: NORMAL, 701: RICH, 702: NORMAL}, close_at=700)
        [t] = r["trades"]
        self.assertEqual(t["exit"], 2.60)
        self.assertEqual(t["exit_minute"], 702)

    def test_the_window_end_closes_inside_the_package(self):
        # A 1-DTE vertical still open when a one-day run ends: the window closes it at the natural of the last
        # minute, which is blown out (-30.00). It leaves at the package's least, 0.00, not below it.
        r = self.run_day({571: NORMAL, 900: BLOWN}, expiration=D2, dte=1, hold=True)
        [t] = r["trades"]
        self.assertEqual(t["exit_reason"], "window_end")
        self.assertEqual(t["exit"], 0.0)
        self.assertLessEqual(-t["pnl"], t["max_loss"] + t["fees"] + 1e-9)

    def test_normal_quotes_are_untouched(self):
        r = self.run_day({571: NORMAL}, close_at=700)
        [t] = r["trades"]
        # 3.40 in, 2.60 out (10.00 - 7.40): (2.60 - 3.40) x 100 less fees, exactly as before.
        self.assertEqual((t["entry"], t["exit"]), (3.40, 2.60))


if __name__ == "__main__":
    unittest.main()
