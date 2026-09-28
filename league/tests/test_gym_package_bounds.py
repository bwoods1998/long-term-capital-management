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
import json
import math
import shutil
import tempfile
import unittest

try:
    import numpy
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

from types import SimpleNamespace

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

    def run_day(self, steps, *, expiration=None, then=None, split_mark=False, **params):
        """One day of `steps` (and a second day of `then` steps, when given)."""
        w = synth.Writer(self.dir)
        w.calendar([D1] if then is None else [D1, D2])
        day(w, D1, steps, expiration=expiration)
        if then is not None:
            day(w, D2, then, expiration=expiration)
        w.finish()
        [r] = E.run([R.load_program(PROGRAM, name="bounds", params=params)], S.Store(self.dir),
                    E.RunConfig(window="train", roots=("SPXW",), split_mark=split_mark))
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

    def test_the_account_mark_keeps_its_last_price_inside_the_package(self):
        # A 1-DTE vertical held overnight: from 900 its quotes blow out (mid (0 + 24) / 2 - (5 + 30) / 2 = -5.50, or
        # (20.00 + 20.40) / 2 - 7.20 = 13.00 in its favour) and the last half hour has no quote, so the day's close
        # finds no newer mark. The day's equity counts it at its last mid inside the package, 3.00 (10.20 - 7.20):
        # never -5.50 (a loss of 890 on a 340 risk), never 13.00, and never a bound (0.00 or the full 5.00 width).
        # Day one: -340.00 paid, 2.43 of open fees, +300.00 of mark: -42.43.
        for blown in (BLOWN, RICH):
            self.fresh()
            r = self.run_day({571: NORMAL, 900: blown, 930: GONE}, expiration=D2, dte=1, hold=True, then={571: NORMAL})
            [t] = r["trades"]
            self.assertEqual(t["max_loss"], 340.0)
            self.assertAlmostEqual(r["daily"][0][1], -42.43, places=6)

    def test_a_window_end_in_a_favourable_blow_out_leaves_at_the_last_real_price(self):
        # The verification's case: a 1-DTE vertical still open when a one-day run ends, its last hour blown out in its
        # favour (natural close 12.60, over the 5.00 width). No close there; before this fix it left at its mark
        # clamped to the full width, 5.00, for +157.57. It leaves at the last natural the package traded at (2.60,
        # 899) with its close fees: -84.87, exactly the run with normal quotes to the end.
        normal = self.run_day({571: NORMAL}, expiration=D2, dte=1, hold=True)
        [n] = normal["trades"]
        self.assertEqual((n["exit"], n["exit_reason"], n["pnl"]), (2.60, "window_end", -84.87))
        for steps in ({571: NORMAL, 900: RICH}, {571: NORMAL, 959: RICH, 960: NORMAL}):
            with self.subTest(steps=sorted(steps)):
                self.fresh()
                r = self.run_day(steps, expiration=D2, dte=1, hold=True)
                [t] = r["trades"]
                self.assertEqual((t["exit"], t["exit_reason"], t["pnl"], t["fees"]), (2.60, "window_end", n["pnl"], n["fees"]))
                self.assertTrue(t["bounded"])
                self.assertGreaterEqual(r["fills"]["blocked_out_of_range"], 1)

    def test_a_split_mark_in_a_favourable_blow_out_leaves_at_the_last_real_price(self):
        # The same position ending a segment another continues: the close's mid (13.00) is no price, so the split is
        # not an accounting mark at it (nor at 5.00): the last natural the package traded at (2.60) with its fees.
        r = self.run_day({571: NORMAL, 900: RICH}, expiration=D2, dte=1, hold=True, split_mark=True)
        [t] = r["trades"]
        self.assertEqual((t["exit"], t["exit_reason"], t["pnl"]), (2.60, "split_mark", -84.87))
        self.assertTrue(t["bounded"])
        # With normal quotes the split stays an accounting mark: the mid, 3.00, with no fee.
        self.fresh()
        r = self.run_day({571: NORMAL}, expiration=D2, dte=1, hold=True, split_mark=True)
        [t] = r["trades"]
        self.assertEqual((t["exit"], t["exit_reason"], t["pnl"], t["bounded"]), (3.00, "split_mark", -42.43, False))

    def test_a_marketable_close_arriving_in_a_blocked_minute_takes_the_next_real_natural(self):
        # The verification's case: closes decided at 700 on normal quotes (natural 2.60) with limits at or through it
        # (0.05, 2.00, the natural): takers. They arrive at 701 into a blown-out quote (natural 12.60): nothing fills,
        # and at 702 they take the natural, 2.60, as on a normal arrival. Before this fix the close at 0.05 rested
        # and sold at 0.05 against a 2.60 market.
        for price in (0.05, 2.0, 0):
            with self.subTest(close_price=price):
                self.fresh()
                r = self.run_day({571: NORMAL, 701: RICH, 702: NORMAL}, close_price=price)
                [t] = r["trades"]
                self.assertEqual((t["exit"], t["exit_minute"], t["pnl"]), (2.60, 702, -84.87))

    def test_an_exit_at_a_stale_mark_takes_the_last_real_price_with_fees(self):
        # A data-hole exit (`_mark_exit`) with no chain today. Its mark (3.00) is inside the package: it leaves there
        # with no fee. When the latest mid was outside (`mark_out`), the mark is stale: it leaves at the last natural a
        # day's close recorded (2.60, its legs 10.00 / 7.40) with that close's fees; with none recorded, at its mark.
        acc = E.Account(R.load_program(PROGRAM, name="bounds"), E.RunConfig(window="train", roots=("SPXW",)), ("SPXW",))
        legs = (L.LegFill(0, 1, 1, 1, 1, 5000.0, True), L.LegFill(1, 2, -1, 1, 1, 5005.0, True))
        prior = D1.toordinal()

        def position(**info):
            return E.Position(pid=1, type="debit_vertical", root="SPXW", legs=legs, keys=numpy.array([1, 2]),
                              expirations=numpy.array([prior + 1, prior + 1]), qty=2, opened_qty=2, entry=3.40,
                              max_loss_share=3.40, collateral=0.0, opened_day=prior, opened_mi=31, opened_session=0,
                              info=dict(info), idx=numpy.array([-1, -1]), last_mark=3.00)

        day = SimpleNamespace(chains={}, ordinal=prior + 2, minutes=391)
        pos = position()
        self.assertEqual(acc._mark_exit(day, pos, None), (3.00, 0.0))
        self.assertNotIn("bounded", pos.info)
        pos = position(mark_out=True, close_at=[2.60, [10.00, 7.40], prior, 389])
        value, fees = acc._mark_exit(day, pos, None)
        self.assertEqual(value, 2.60)
        self.assertEqual(fees, L.order_fees("SPXW", legs, [10.00, 7.40], 2, "close"))
        self.assertGreater(fees, 0.0)
        self.assertTrue(pos.info["bounded"])
        pos = position(mark_out=True)
        self.assertEqual(acc._mark_exit(day, pos, None), (3.00, 0.0))
        # A close recorded LATER today than the exit is never used (no look ahead).
        pos = position(mark_out=True, close_at=[2.60, [10.00, 7.40], prior + 2, 389])
        self.assertEqual(acc._mark_exit(day, pos, 388), (3.00, 0.0))

    def test_a_mark_outside_the_package_is_dropped_never_clamped(self):
        pos = SimpleNamespace(last_mark=3.00, info={}, bounds=lambda: (0.0, 5.0))
        E.Account._set_mark(pos, 13.00)
        self.assertEqual((pos.last_mark, pos.info), (3.00, {"mark_out": True}))
        E.Account._set_mark(pos, -5.50)
        self.assertEqual((pos.last_mark, pos.info), (3.00, {"mark_out": True}))
        E.Account._set_mark(pos, 3.20)
        self.assertEqual((pos.last_mark, pos.info), (3.20, {}))

    def test_the_shadow_book_saves_the_stale_mark_flag(self):
        # The shadow book (league/live/shadow.py, unchanged) saves a position's info and last mark: the flag and the
        # recorded close survive a restart without a change to the live code.
        from league.live.shadow import _position_from, _position_state
        pos = E.Position(pid=1, type="debit_vertical", root="SPXW", legs=(L.LegFill(0, 1, 1, 1, 1, 5000.0, True),
                         L.LegFill(1, 2, -1, 1, 1, 5005.0, True)), keys=numpy.array([1, 2]),
                         expirations=numpy.array([738951, 738951]), qty=1, opened_qty=1, entry=3.40, max_loss_share=3.40,
                         collateral=0.0, opened_day=738950, opened_mi=31, opened_session=0,
                         info={"mark_out": True, "close_at": [2.6, [10.0, 7.4], 738950, 329]}, idx=numpy.array([0, 1]),
                         last_mark=3.00)
        back = _position_from(json.loads(json.dumps(_position_state(pos))))
        self.assertEqual((back.last_mark, back.info), (3.00, pos.info))

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
