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

# Open a 5000/5005 SPXW call debit vertical at 600 (fills at 601 or later); close it at CLOSE_AT (fills a minute
# later or after). {"hold": True} never closes it (it settles, or the run's end closes it). "open_price" and
# "close_price" are the orders' limits: 0 for "natural", or v for {"price": v}, a patient order.
PROGRAM = '''
NEEDS = {"roots": ["SPXW"], "dte": [0, 3], "band": 0.2, "cadence": 1, "start": 600}
PARAMS = {"close_at": 700, "dte": 0, "hold": False, "open_price": 0, "close_price": 0}
STATE = {"opened": False}
def decide(ctx):
    p = ctx.params
    if not STATE["opened"] and ctx.minute == 600:
        STATE["opened"] = True
        return [{"open": "debit_vertical", "root": "SPXW", "legs": [
            {"side": "long", "right": "C", "dte": p["dte"], "strike": 5000},
            {"side": "short", "right": "C", "dte": p["dte"], "strike": 5005}], "qty": 1, "tif": "day",
            "limit": {"price": p["open_price"]} if p["open_price"] else "natural"}]
    if ctx.positions and not p["hold"] and ctx.minute == p["close_at"] and not ctx.orders:
        return [{"close": ctx.positions[0]["id"], "limit": {"price": p["close_price"]} if p["close_price"] else "natural",
                 "tif": "day"}]
    return []
'''

NORMAL = {"5000": (10.00, 10.40), "5005": (7.00, 7.40)}   # natural open 10.40 - 7.00 = 3.40; natural close 2.60
BLOWN = {"5000": (0.00, 24.00), "5005": (5.00, 30.00)}    # natural close 0.00 - 30.00 = -30.00: a blown-out quote
RICH = {"5000": (20.00, 20.40), "5005": (7.00, 7.40)}     # natural close 20.00 - 7.40 = 12.60, over the 5.00 width
CROSSED = {"5000": (4.60, 5.00), "5005": (8.00, 8.40)}   # natural open 5.00 - 8.00 = -3.00: paid to buy a vertical
UP = {"5000": (10.60, 11.00), "5005": (7.00, 7.40)}       # natural close 10.60 - 7.40 = 3.20
DOWN = {"5000": (9.90, 10.20), "5005": (7.40, 7.80)}      # natural open 10.20 - 7.40 = 2.80
LOCKED = {"5000": (6.90, 7.00), "5005": (7.00, 7.40)}     # natural open 7.00 - 7.00 = 0.00: a vertical for nothing
GONE = {"5000": (None, None), "5005": (None, None)}       # no quote from here on (`synth.flat_day`)


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

    def run_day(self, steps, *, expiration=None, then=None, **params):
        """One day of `steps` (and a second day of `then` steps, when given)."""
        w = synth.Writer(self.dir)
        w.calendar([D1] if then is None else [D1, D2])
        day(w, D1, steps, expiration=expiration)
        if then is not None:
            day(w, D2, then, expiration=expiration)
        w.finish()
        [r] = E.run([R.load_program(PROGRAM, name="bounds", params=params)], S.Store(self.dir),
                    E.RunConfig(window="train", roots=("SPXW",)))
        self.assertEqual(r["status"], "ok", r["runtime"])
        return r

    def fresh(self):
        """A new store directory: two runs in one test must not share a store."""
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir = tempfile.mkdtemp(prefix="gym-bounds-")

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
            self.assertEqual(L.value_bounds(legs, [D1] * len(legs)), want, name)
        self.assertEqual(L.value_bounds([leg(1, "C", 100)], [D1]), (0.0, math.inf))
        self.assertEqual(L.value_bounds([leg(1, "C", 100), leg(1, "P", 100)], [D1, D1]), (0.0, math.inf))       # a straddle
        self.assertEqual(L.value_bounds([leg(-1, "C", 100, dte=1), leg(1, "C", 100, dte=8)], [1, 8]), (-math.inf, math.inf))  # calendar

    def test_value_bounds_reads_expirations_never_the_legs_dte(self):
        def leg(side, strike):
            return L.LegFill(0, 0, side, 1, 0, float(strike), True)
        # The live path builds a held position's legs with dte 0 placeholders (league/live/step.py): a calendar or a
        # diagonal whose legs all say dte 0 is still two expiries, and has no bound.
        calendar = [leg(-1, 100), leg(1, 100)]
        diagonal = [leg(-1, 105), leg(1, 100)]
        self.assertEqual(L.value_bounds(calendar, [D1, D2]), (-math.inf, math.inf))
        self.assertEqual(L.value_bounds(diagonal, [D1, D2]), (-math.inf, math.inf))
        with self.assertRaises(ValueError):
            L.value_bounds(calendar, [D1])           # one expiry for two legs: never guessed

    def test_an_open_at_the_least_is_never_free(self):
        # The open's check is strict at a finite least: a debit vertical or a long call bought for 0.00 would be free.
        self.assertIsNone(E.Account._in_bounds(0.0, 0.0, 5.0, True))
        self.assertIsNone(E.Account._in_bounds(0.0, 0.0, math.inf, True))
        self.assertEqual(E.Account._in_bounds(0.01, 0.0, 5.0, True), 0.01)
        self.assertFalse(E.Account._tradeable(0.0, 0.0, 5.0, True))
        self.assertTrue(E.Account._tradeable(0.01, 0.0, 5.0, True))
        # A close at the least is a price (the floor itself); a calendar (no bound) trades at any price.
        self.assertEqual(E.Account._in_bounds(-1.0, 0.0, 5.0, False), 0.0)
        self.assertEqual(E.Account._in_bounds(-1.0, -math.inf, math.inf, True), -1.0)

    def test_a_locked_natural_never_buys_a_vertical_for_free(self):
        # Decided at 600 on normal quotes (limit 3.40); at 601 the long leg's ask meets the short leg's bid: the natural
        # open is 0.00. No one gives a vertical away: nothing fills, and at 602 it buys at 3.40, its own limit.
        r = self.run_day({571: NORMAL, 601: LOCKED, 602: NORMAL}, hold=True)
        [t] = r["trades"]
        self.assertEqual((t["entry"], t["filled_minute"]), (3.40, 602))
        self.assertEqual(r["fills"]["blocked_out_of_range"], 1)

    def test_a_blocked_arrival_never_makes_a_patient_close_a_taker(self):
        # A close at 3.00 decided at 700 on normal quotes (natural 2.60: it waits for the market to come to it). It
        # arrives at 701 into a blown-out quote (natural 12.60, over the 5.00 width): nothing fills there, and the order
        # RESTS. At 702 the market comes through its limit (natural 3.20): it sells at its own 3.00, exactly as when it
        # arrives on normal quotes; before this, the blocked minute made it a taker and it sold at 3.20.
        blocked = self.run_day({571: NORMAL, 701: RICH, 702: UP}, close_price=3.0)
        self.fresh()
        normal = self.run_day({571: NORMAL, 702: UP}, close_price=3.0)
        [b], [n] = blocked["trades"], normal["trades"]
        self.assertEqual((b["exit"], b["exit_minute"]), (3.00, 702))
        self.assertEqual((b["entry"], b["exit"], b["exit_minute"], b["pnl"]), (n["entry"], n["exit"], n["exit_minute"], n["pnl"]))
        self.assertEqual((blocked["fills"]["blocked_out_of_range"], normal["fills"]["blocked_out_of_range"]), (1, 0))

    def test_a_blocked_arrival_never_makes_a_patient_open_a_taker(self):
        # An open at 3.00 decided at 600 on normal quotes (natural 3.40: it waits). It arrives at 601 into crossed legs
        # (natural -3.00): nothing fills, and it rests. At 602 the natural is 2.80: it buys at its own 3.00, exactly as
        # when it arrives on normal quotes; before this it bought at 2.80.
        blocked = self.run_day({571: NORMAL, 601: CROSSED, 602: DOWN}, hold=True, open_price=3.0)
        self.fresh()
        normal = self.run_day({571: NORMAL, 602: DOWN}, hold=True, open_price=3.0)
        [b], [n] = blocked["trades"], normal["trades"]
        self.assertEqual((b["entry"], b["filled_minute"]), (3.00, 602))
        self.assertEqual((b["entry"], b["filled_minute"], b["pnl"]), (n["entry"], n["filled_minute"], n["pnl"]))

    def test_a_blocked_minute_never_fills_a_resting_order_at_its_limit(self):
        # A close at 3.00 rests from 701 (natural 2.60). At 702 a blown-out quote (natural 12.60) "crosses" its limit: it
        # is no market, so nothing fills; the order keeps working and sells at 3.00 when the market really comes to it
        # (750, natural 3.20).
        r = self.run_day({571: NORMAL, 702: RICH, 703: NORMAL, 750: UP}, close_price=3.0)
        [t] = r["trades"]
        self.assertEqual((t["exit"], t["exit_minute"]), (3.00, 750))
        self.assertEqual(r["fills"]["blocked_out_of_range"], 1)

    def test_the_account_mark_stays_inside_the_package(self):
        # A 1-DTE vertical held overnight: the program's last look (929) is a blown-out quote whose mid is
        # (0 + 24) / 2 - (5 + 30) / 2 = -5.50, and the last half hour has no quote, so the day's close finds no newer
        # mark. The day's equity counts the vertical at its least, 0.00, never at -5.50 (a loss of 890 on a 340 risk).
        r = self.run_day({571: NORMAL, 900: BLOWN, 930: GONE}, expiration=D2, dte=1, hold=True, then={571: NORMAL})
        [t] = r["trades"]
        first_day_pnl = r["daily"][0][1]
        self.assertEqual(t["max_loss"], 340.0)
        self.assertGreaterEqual(first_day_pnl, -(t["max_loss"] + t["fees"]) - 1e-6)
        self.assertLess(first_day_pnl, -340.0 + 1e-6)

    def test_a_blown_out_leg_never_closes_a_vertical_below_zero(self):
        r = self.run_day({571: NORMAL, 700: BLOWN}, close_at=700)
        [t] = r["trades"]
        # Open 600 -> 601 at the natural 3.40: max loss 340. The close meets 701's quotes, whose natural is -30.00:
        # paying 30.00 to part with a vertical that is worth 0 to 5. It sells at the vertical's least, 0.00.
        self.assertEqual((t["entry"], t["max_loss"]), (3.40, 340.0))
        self.assertEqual(t["exit"], 0.0)
        self.assertEqual(t["exit_reason"], "program")
        self.assertLessEqual(-t["pnl"], t["max_loss"] + t["fees"] + 1e-9)
        # Counted and flagged, and never recorded as price improvement: the blown-out quote's mid is -5.50, and 0.00
        # against it would read as 5.50 better than the mid. The only close was held at the least, so the close-slip
        # figures have no row at all.
        self.assertTrue(t["bounded"])
        self.assertEqual(r["fills"]["bounded_close"], 1)
        self.assertIsNone(r["fills"]["close_slip_share"])
        self.assertIsNotNone(r["fills"]["open_slip_share"])

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
        self.assertTrue(t["bounded"])
        self.assertEqual(r["fills"]["bounded_close"], 1)

    def test_normal_quotes_are_untouched(self):
        r = self.run_day({571: NORMAL}, close_at=700)
        [t] = r["trades"]
        # 3.40 in, 2.60 out (10.00 - 7.40): (2.60 - 3.40) x 100 less fees, exactly as before.
        self.assertEqual((t["entry"], t["exit"]), (3.40, 2.60))
        self.assertFalse(t["bounded"])
        self.assertEqual((r["fills"]["bounded_close"], r["fills"]["blocked_out_of_range"]), (0, 0))
        self.assertIsNotNone(r["fills"]["close_slip_share"])


if __name__ == "__main__":
    unittest.main()
