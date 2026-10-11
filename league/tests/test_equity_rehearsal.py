"""WHAT THE REHEARSAL ON REAL DATA FOUND (release E1, Oct 11, 2026): the data job, its audit, the store, the three
seeds' Train runs and the screen's floor were run once on the House box against real SIP bars before the first deploy,
and an independent check read the result. The data job's own two defects are held in league/tests/test_equity_data.py;
this file holds the rest, by the rehearsal's finding:

- `TheVendorsCents`, `TheEngineOnCentRoundedPrices` (rehearsal-3, rehearsal-10): the vendor rounds its adjustment=all
  prices to the cent, so the all/raw ratio jitters from bar to bar with no event. The engine read that jitter as
  dividends and anomalies, and read a split whose step the rounding had pushed above its factor as a neighbouring
  fraction with a dividend;
- `TheMorningAfterAnExDate` (rehearsal-4): the book's morning audit read every ex-dividend morning as a price mismatch,
  which cancels the decision's buys and counts a failed decide. One bound serves both (`config.rounding_bound`);
- `TheNextDaysFetch` (rehearsal-9, with the review's evidence-1): the volume is no part of a day's audit mark either;
- `TheSeedsDeclaredOrder` (rehearsal-5): the two overnight seeds are one lineage, and which of them spends its one
  look is the declared order of `seeds.EQUITY_SEEDS`, never the clock;
- `TheEventTablesCoverage` (rehearsal-8): `ctx.events` says nothing before the tables' first year or after a table's
  last row, the same live and in the Gym;
- `TheCtxOfALaterStore` (rehearsal-6): a live ctx does not reproduce byte for byte from a later store once an event
  has restated the series, and by how much it may differ.

Every price here is invented (round numbers and a few cents), never a market's."""

from __future__ import annotations

import datetime as dt
import random
import unittest
from decimal import Decimal
from fractions import Fraction

from league.equity import config, engine
from league.equity import live as L
from league.equity.engine import run, split_factor
from league.tests import test_equity_book as T
from league.tests import test_equity_engine as E

D = Decimal
MONDAY, TUESDAY = T.MONDAY, T.TUESDAY


def cents(value: float) -> float:
    """A price as the vendor publishes its adjusted series: rounded to the cent."""
    return round(value, 2)


# ------------------------------------------------------------------------------------------- the one shared bound
class TheVendorsCents(unittest.TestCase):
    def test_the_bound_is_half_a_cent_over_each_price_with_its_guard(self):
        self.assertEqual((config.ADJUSTED_HALF_STEP, config.ROUNDING_GUARD), (0.005, 1.5))
        self.assertAlmostEqual(config.rounding_bound(100.0, 100.0), 1.5 * 0.005 * 0.02, places=15)
        self.assertAlmostEqual(config.rounding_bound(600.0, 600.0, 600.0, 600.0), 5e-5, places=15)
        self.assertGreater(config.rounding_bound(20.0, 20.0), config.rounding_bound(200.0, 200.0),
                           "a cent is more of a low price")
        for bad in ((), (0.0, 100.0), (-1.0,), (float("nan"), 100.0), (float("inf"),), ("x",)):
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                config.rounding_bound(*bad)

    def test_the_engines_tolerance_is_that_bound_never_under_its_floor(self):
        self.assertAlmostEqual(engine.ratio_tolerance(100.0, 100.0), 1.5e-4, places=15)
        self.assertEqual(engine.ratio_tolerance(1e6, 1e6), engine.RATIO_TOLERANCE, "the floor, for a price in the millions")
        self.assertEqual(engine.ratio_tolerance(float("nan"), 100.0), engine.RATIO_TOLERANCE,
                         "a close that is no price has no rounding to allow for: the step is judged as before")

    def test_a_split_is_read_exactly_on_cent_rounded_prices(self):
        """rehearsal-10: with the fixed bound the search refused the true factor whenever the rounding had pushed its
        residual above 1, and took the nearest smaller fraction with the rest as a dividend (39:2 for a 20-for-1)."""
        rng = random.Random(20261011)
        wrong_before = 0
        for factor in (Fraction(20), Fraction(4), Fraction(10), Fraction(2), Fraction(3, 2), Fraction(1, 10)):
            for dividend in (0.0, 0.004):                      # none, or one on the split's own day
                for _ in range(250):
                    before = cents(rng.uniform(40.0, 900.0))    # the raw close before the split
                    after = cents(before / float(factor) * (1.0 + rng.uniform(-0.03, 0.03)))
                    level = rng.choice((1.0, 0.97, 0.88))       # later events' factor on both adjusted closes
                    adj_before = cents(before / float(factor) * level * (1.0 - dividend))
                    adj_after = cents(after * level)
                    step = (adj_before / before) / (adj_after / after)
                    tolerance = engine.ratio_tolerance(adj_before, adj_after)
                    self.assertEqual(split_factor(step, tolerance), factor, (factor, dividend, before, after, level))
                    wrong_before += split_factor(step) != factor
        self.assertGreater(wrong_before, 100, "the fixed bound alone misread many of the same steps")

    def test_the_exact_steps_read_as_before(self):
        for step, want in ((0.5, 2), (0.05, 20), (10.0, Fraction(1, 10)), (2 / 3, Fraction(3, 2)), (0.5 * 0.99, 2)):
            self.assertEqual(split_factor(step, 1.5e-4), want)
        self.assertIsNone(split_factor(0.98, 1.5e-4), "a dividend is not a split")
        self.assertIsNone(split_factor(1.0, 1.5e-4))


# -------------------------------------------------------------------------------------------------- the engine
HOLD = """
if STATE['n'] == 1:
    return [{'buy': 'SPY', 'usd': 300, 'at': 'close'}]
return []
"""


def rows(raw_closes, adjusted):
    """`hand_store` rows (raw open, raw close, all open, all close) of flat bars."""
    return [(r, r, a, a) for r, a in zip(raw_closes, adjusted)]


class TheEngineOnCentRoundedPrices(E.Case):
    RAW = [100.37, 101.12, 99.81, 100.05, 102.33, 101.47, 100.91, 99.64, 100.88, 101.73, 100.19, 99.95]

    def held(self, raw, adjusted):
        bars, days = E.hand_store(self.tmp / "s", {"SPY": rows(raw, adjusted)})
        return run(E.program(HOLD, max_hold=40), bars), days

    def test_the_rounding_of_the_adjusted_series_is_no_dividend_and_no_anomaly(self):
        """rehearsal-3: an earlier dividend left the adjusted series a constant factor under the raw one, and the vendor
        rounds each adjusted price to the cent. Nothing happens in these twelve sessions; the engine read some of the
        ratio's jitter as dividends (cash credited to the lot) and some as anomalies, one-sided."""
        adjusted = [cents(r * 0.9731) for r in self.RAW]
        steps = [(adjusted[i - 1] / self.RAW[i - 1]) / (adjusted[i] / self.RAW[i]) - 1.0 for i in range(1, len(self.RAW))]
        self.assertGreater(sum(abs(s) > engine.RATIO_TOLERANCE for s in steps), 3, "the jitter is past the fixed bound")
        result, _ = self.held(self.RAW, adjusted)
        self.assertEqual(result["actions"], [])
        (lot,) = result["lots"]
        self.assertEqual((lot["div"], lot["reason"]), (0.0, "open"))
        self.assertEqual(result["summary"]["dividends"], 0.0)

    def test_a_real_dividend_is_still_credited_within_a_cent_a_share_of_its_rounding(self):
        ex, paid = 6, 0.50                                         # ex-dividend at session 6: $0.50 a share
        level = 1.0 - paid / self.RAW[ex - 1]
        adjusted = [cents(r * level) if i < ex else r for i, r in enumerate(self.RAW)]
        result, days = self.held(self.RAW, adjusted)
        (action,) = result["actions"]
        self.assertEqual((action["symbol"], action["day"], action["kind"]), ("SPY", days[ex].isoformat(), "dividend"))
        self.assertAlmostEqual(action["per_share"], paid, delta=0.011)
        (lot,) = result["lots"]
        self.assertAlmostEqual(lot["div"], lot["qty"] * paid, delta=0.04)

    def test_a_split_and_a_dividend_on_neighbouring_days(self):
        """rehearsal-10 in the engine: a 20-for-1 split at session 3 and a $0.40 dividend at session 4. With the fixed
        bound these very prices read as a 39-for-2 split with a dividend of a fortieth of the price."""
        raw = [2003.37, 2011.90, 1998.44, 101.33, 100.87, 101.10, 100.64, 101.02]
        level = 1.0 - 0.40 / raw[3]
        adjusted = [cents(raw[0] / 20 * level), cents(raw[1] / 20 * level), cents(raw[2] / 20 * level),
                    cents(raw[3] * level), *raw[4:]]
        step = (adjusted[2] / raw[2]) / (adjusted[3] / raw[3])
        self.assertEqual(split_factor(step), Fraction(39, 2), "what the fixed bound made of it")
        result, days = self.held(raw, adjusted)
        split, dividend = result["actions"]
        self.assertEqual(split, {"symbol": "SPY", "day": days[3].isoformat(), "kind": "split", "factor": "20:1"})
        self.assertEqual((dividend["day"], dividend["kind"]), (days[4].isoformat(), "dividend"))
        self.assertAlmostEqual(dividend["per_share"], 0.40, delta=0.011)
        (lot,) = result["lots"]
        bought = (D(300) / D(str(engine.fill_price(raw[1], "buy", config.half_spread("SPY"), 1.0)))).quantize(
            D("0.000001"), rounding="ROUND_DOWN")
        self.assertEqual(D(str(lot["qty"])), (bought * 20).quantize(D("0.000001")), "twenty shares for each one bought")
        self.assertAlmostEqual(lot["div"], float(bought * 20) * 0.40, delta=0.05)


# ------------------------------------------------------------------------------------------- the morning's audit
def readings(price: float, level: float, restated: float, *, n: int = 6):
    """Two readings of one symbol's bars: the 16:20 one (raw, and the adjusted series a factor `level` under it) and
    the next morning's, after an ex-date restated every adjusted price by `restated`; each adjusted price to the cent.
    -> (old_raw, old_all, fresh_raw, fresh_all, day) as `live._bars_verdict` takes them."""
    days = [f"2026-10-{d:02d}" for d in range(1, 1 + n)]
    raw = {d: tuple(cents(price + 0.37 * i + x) for x in (-0.20, 0.55, -0.61, 0.0)) + (1000 + i,)
           for i, d in enumerate(days)}
    old_all = {d: tuple(cents(x * level) for x in raw[d][:4]) for d in days}
    fresh_raw = {d: dict(zip("ohlcv", raw[d])) for d in days}
    fresh_all = {d: dict(zip("ohlc", (cents(x * level * restated) for x in raw[d][:4]))) for d in days}
    return raw, old_all, fresh_raw, fresh_all, days[-1]


class TheMorningAfterAnExDate(T.BookTest):
    """rehearsal-4: on an ex-dividend morning the vendor has restated the whole adjusted series by the event's factor,
    each price rounded to the cent again. The as-of prices a program saw are the same; compared to a millionth they
    never were, so every ex-date (monthly for one of the four index ETFs) cancelled the decision's buys and counted a
    failed decide."""

    LEVELS = (600.0, 450.0, 220.0, 100.0)
    EX_DATES = (0.9987, 0.9971, 0.9925)           # a monthly, a quarterly and a large dividend's factor

    def test_a_series_an_ex_date_restated_gives_the_same_as_of_prices(self):
        differ_before = 0
        for price in self.LEVELS:
            for restated in self.EX_DATES:
                raw, old_all, fresh_raw, fresh_all, day = readings(price, 0.9731, restated)
                self.assertTrue(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day), (price, restated))
                self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "ok")
                differ_before += any(
                    abs(old_all[d][i] * raw[day][3] / old_all[day][3] - fresh_all[d][k] * raw[day][3] / fresh_all[day]["c"])
                    > 1e-6 * old_all[d][i] for d in old_all for i, k in enumerate("ohlc"))
        self.assertEqual(differ_before, len(self.LEVELS) * len(self.EX_DATES), "to a millionth every one of them differs")

    def test_a_price_that_really_moved_is_still_a_mismatch(self):
        for price, moved in ((600.0, 0.0005), (220.0, 0.0005), (100.0, 0.002), (41.07, 0.002)):
            raw, old_all, fresh_raw, fresh_all, day = readings(price, 0.9731, 0.9971)
            first = sorted(fresh_all)[0]
            fresh_all[first]["c"] = fresh_all[first]["c"] * (1.0 + moved)
            self.assertFalse(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day), (price, moved))
            self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "mismatch")

    def test_a_raw_price_is_exact_and_an_unreadable_one_is_a_difference(self):
        raw, old_all, fresh_raw, fresh_all, day = readings(600.0, 0.9731, 0.9971)
        fresh_raw[day]["l"] = cents(fresh_raw[day]["l"] - 0.01)     # the raw series is the tape's own: a cent is a cent
        self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "mismatch")
        raw, old_all, fresh_raw, fresh_all, day = readings(600.0, 0.9731, 0.9971)
        fresh_all[sorted(fresh_all)[1]]["h"] = 0.0
        self.assertFalse(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day), "never read as all rounding")
        fresh_all[sorted(fresh_all)[1]]["h"] = None
        self.assertFalse(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day))

    def decided(self) -> tuple[T.Harness, L.Intent]:
        h = self.harness()
        inst = h.instance()
        h.decider.needs[inst.id] = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 20}
        h.decider.plans[inst.id] = [{"buy": "SPY", "share": 0.5}]
        h.decide_setup(MONDAY)
        for row, source in zip(h.market.bar_rows["all"]["SPY"], h.market.bar_rows["raw"]["SPY"]):
            row.update({k: cents(source[k] * 0.9731) for k in "ohlc"})  # the vendor's cents
        h.tick(16, 31)
        (buy,) = h.intents(kind="buy")
        return h, buy

    def restate(self, h: T.Harness, factor: float) -> None:
        for row, source in zip(h.market.bar_rows["all"]["SPY"], h.market.bar_rows["raw"]["SPY"]):
            row.update({k: cents(source[k] * 0.9731 * factor) for k in "ohlc"})

    def test_the_books_audit_on_an_ex_dividend_morning_cancels_nothing(self):
        h, buy = self.decided()
        self.restate(h, 0.9971)                                      # Tuesday is the ex-date
        h.tick(8, 31, day=TUESDAY)
        decision = h.state.get("eq_decision")
        self.assertEqual((decision["audit"], decision["mismatch"]), ("ok", []))
        self.assertEqual(h.get_intent(buy.iid).status, "planned")
        (inst,) = h.book._instances(alive=True)
        self.assertEqual(inst.failed_decides, 0)
        self.assertEqual([a for a in h.alerts if a[0] == "error"], [])
        self.assertEqual({r["audit"] for r in h.state.rows("SELECT audit FROM eq_bars WHERE day=?", (MONDAY.isoformat(),))},
                         {"ok"})

    def test_and_a_moved_close_on_that_morning_still_cancels_the_buy(self):
        h, buy = self.decided()
        self.restate(h, 0.9971)
        h.market.bar_rows["all"]["SPY"][-3]["c"] *= 1.0005           # five basis points on one adjusted close
        h.tick(8, 31, day=TUESDAY)
        decision = h.state.get("eq_decision")
        self.assertEqual((decision["audit"], decision["mismatch"]), ("mismatch", ["SPY"]))
        self.assertEqual(h.get_intent(buy.iid).status, "canceled")
        (inst,) = h.book._instances(alive=True)
        self.assertEqual(inst.failed_decides, 1)


class TheNextDaysFetch(T.BookTest):
    """rehearsal-9 (the review's evidence-1 and ops-4 hold the audit itself): the vendor's 1Day volume of a session is
    not final at the 16:20 fetch, so the NEXT day's fetch always reads another volume for it. The store's upsert took
    that for a changed row and cleared the day's morning audit mark, which the twins then report as never audited."""

    def audited(self) -> T.Harness:
        h = self.harness()
        inst = h.instance()
        h.decider.needs[inst.id] = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 20}
        h.decider.plans[inst.id] = []
        h.decide_setup(MONDAY)
        h.tick(16, 31)
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(self.mark(h), {"ok"})
        for name in ("raw", "all"):                                   # Tuesday's bar, as the 16:20 fetch reads it
            last = h.market.bar_rows[name]["SPY"][-1]
            h.market.bar_rows[name]["SPY"].append({**last, "t": f"{TUESDAY.isoformat()}T04:00:00Z"})
        return h

    def mark(self, h: T.Harness) -> set:
        return {r["audit"] for r in h.state.rows("SELECT audit FROM eq_bars WHERE day=? AND symbol='SPY'",
                                                 (MONDAY.isoformat(),))}

    def monday(self, h: T.Harness, name: str = "raw") -> dict:
        return h.market.bar_rows[name]["SPY"][-2]

    def test_a_volume_that_grew_keeps_the_days_audit_mark(self):
        h = self.audited()
        before = self.monday(h)["v"]
        self.monday(h)["v"] = before + 250_000                        # the after-hours prints, counted by Tuesday
        h.tick(16, 31, day=TUESDAY)
        self.assertEqual(h.state.get("eq_decision")["day"], TUESDAY.isoformat(), "Tuesday's bars were stored")
        self.assertEqual(self.mark(h), {"ok"}, "its prices are the audited ones")
        [stored] = h.state.rows("SELECT v FROM eq_bars WHERE day=? AND symbol='SPY' AND adjustment='raw'",
                                (MONDAY.isoformat(),))
        self.assertEqual(D(stored["v"]), D(str(before + 250_000)), "the store holds the later volume")

    def test_a_price_that_changed_is_unaudited_again(self):
        h = self.audited()
        self.monday(h)["c"] += 0.25
        h.tick(16, 31, day=TUESDAY)
        marks = {(r["adjustment"], r["audit"]) for r in h.state.rows(
            "SELECT adjustment, audit FROM eq_bars WHERE day=? AND symbol='SPY'", (MONDAY.isoformat(),))}
        self.assertEqual(marks, {("raw", None), ("all", "ok")})


if __name__ == "__main__":
    unittest.main()
