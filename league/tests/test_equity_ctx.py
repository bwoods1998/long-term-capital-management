"""What an equity program sees (I6): one constructor for the Gym and the House, prices as of t, nothing after t.

The same-ctx helper (`synth.same_ctx_cases`) is the hooks package's I6 test input; here it is held against the live
builder directly, and the as-of identity is held across a store written after a split and a dividend.
"""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import numpy as np

from league.equity import synth
from league.equity.ctx import (Inputs, as_of, build, calendar_around, closed_row, ctx_bytes, inputs_from_bars,
                               inputs_from_fetch, lot_row)
from league.equity.program import Needs
from league.equity.store import EquityStore, ordinal

D = dt.date
COMMON = {"cash": 400.0, "equity": 1000.0, "budget": 1000.0, "caps": {"SPY": 100.0}, "params": {"a": [1, 2]}}


def inputs(days, closes, *, raw_closes=None, symbol="SPY", **kw):
    """Hand-made inputs: `closes` the adjustment=all closes, `raw_closes` the raw ones (default equal)."""
    raw_closes = closes if raw_closes is None else raw_closes
    raw = np.array([[c, c, c, c, 10.0] for c in raw_closes], dtype=np.float64)
    adj = np.array([[c, c, c, c] for c in closes], dtype=np.float64)
    trading, early = calendar_around(days[-1])
    base = dict(symbols=(symbol,), history=len(days) - 1, days=np.array([ordinal(d) for d in days], dtype=np.int32),
                raw={symbol: raw}, adj={symbol: adj}, trading_days=trading, early=early, positions=(), orders=(),
                closed=(), rejects=(), cash=1.0, equity=1.0, budget=1.0, caps={}, params={})
    base.update(kw)
    return Inputs(**base)


class AsOf(unittest.TestCase):
    def test_the_factor_cancels_every_later_event(self):
        adj = np.array([50.0, 60.0, 100.0])
        self.assertEqual(as_of(adj, 200.0, 100.0).tolist(), [100.0, 120.0, 200.0])
        self.assertEqual(as_of(adj * 0.25, 200.0, 25.0).tolist(), [100.0, 120.0, 200.0])
        self.assertTrue(np.isnan(as_of(adj, float("nan"), 100.0)).all())
        self.assertTrue(np.isnan(as_of(adj, 200.0, 0.0)).all())
        self.assertEqual(as_of(np.array([1.0 / 3.0]), 1.0, 1.0).tolist(), [0.3333])


class Building(unittest.TestCase):
    def test_fields_calendar_and_events(self):
        days = [D(2025, 1, 27), D(2025, 1, 28)]
        ctx = build(inputs(days, [100.0, 101.0], positions=({"id": 1},), rejects=("no",), caps={"SPY": 5},
                           params={"x": [1]}))
        self.assertEqual(ctx.symbols, ("SPY",))
        self.assertEqual(ctx.weekday, 1)
        self.assertFalse(ctx.events["fomc"])
        self.assertTrue(ctx.events_next["fomc"], "2025-01-29 was an FOMC statement day")
        self.assertEqual((ctx.session_of_month, ctx.sessions_to_month_end), (17, 3), "Jan 9, 2025 was a closure")
        self.assertEqual(ctx.prices, {"SPY": 101.0})
        self.assertEqual((ctx.positions, ctx.rejects, ctx.caps), ([{"id": 1}], ["no"], {"SPY": 5.0}))
        bars = ctx.bars["SPY"]
        self.assertEqual(bars.close.tolist(), [100.0, 101.0])
        self.assertTrue(np.isnan(bars.ret[0]))
        self.assertAlmostEqual(float(bars.ret[1]), 0.01)
        self.assertEqual(bars.volume.tolist(), [10.0, 10.0])
        with self.assertRaises(ValueError):
            bars.close[0] = 1.0
        with self.assertRaises(ValueError):
            bars.close.setflags(write=True)
        ctx.params["x"].append(2)
        self.assertEqual(build(inputs(days, [100.0, 101.0], params={"x": [1]})).params, {"x": [1]})

    def test_month_ends_and_half_days(self):
        ctx = build(inputs([D(2025, 1, 31)], [1.0]))
        self.assertEqual((ctx.session_of_month, ctx.sessions_to_month_end), (20, 0))
        ctx = build(inputs([D(2025, 1, 2)], [1.0]))
        self.assertEqual(ctx.session_of_month, 1)
        ctx = build(inputs([D(2025, 11, 26)], [1.0]))
        self.assertTrue(ctx.events_next["half_day"], "the next session is the 13:00 close after Thanksgiving")
        self.assertFalse(ctx.events["half_day"])
        ctx = build(inputs([D(2025, 12, 31)], [1.0]))
        self.assertTrue(ctx.events["quarter_end"])
        self.assertEqual(ctx.sessions_to_month_end, 0)

    def test_prices_are_as_of_t_and_a_missing_bar_at_t_is_nan(self):
        days = [D(2025, 6, 2), D(2025, 6, 3), D(2025, 6, 4)]
        # all = raw halved before a later 2-for-1 (fetched after it): as of t the history is raw again.
        ctx = build(inputs(days, [50.0, 51.0, 52.0], raw_closes=[100.0, 102.0, 104.0]))
        self.assertEqual(ctx.bars["SPY"].close.tolist(), [100.0, 102.0, 104.0])
        gap = inputs(days, [50.0, 51.0, float("nan")], raw_closes=[100.0, 102.0, float("nan")])
        ctx = build(gap)
        self.assertTrue(np.isnan(ctx.prices["SPY"]))
        self.assertEqual(ctx.bars["SPY"].close[:2].tolist(), [100.0, 102.0], "the last bar's factor")

    def test_rows(self):
        self.assertEqual(lot_row(lid=3, symbol="SPY", klass="etf", qty=1.23456789, entry=100.123456, mark=101.0,
                                 held_sessions=2, at="close", tag="x"),
                         {"id": 3, "symbol": "SPY", "class": "etf", "qty": 1.234568, "entry": 100.1235, "mark": 101.0,
                          "value": 124.6914, "pnl": 1.0822, "held_sessions": 2, "at": "close", "tag": "x"})
        self.assertIsNone(lot_row(lid=1, symbol="SPY", klass="etf", qty=1, entry=1, mark=float("nan"),
                                  held_sessions=0, at="open")["pnl"])
        self.assertEqual(closed_row(lid=3, symbol="SPY", qty=2, entry=10, exit=11, net=1.98766, held_sessions=1,
                                    reason="program"),
                         {"id": 3, "symbol": "SPY", "qty": 2.0, "entry": 10.0, "exit": 11.0, "net": 1.9877,
                          "held_sessions": 1, "reason": "program", "tag": ""})

    def test_ctx_bytes_is_canonical(self):
        days = [D(2025, 3, 3), D(2025, 3, 4)]
        a = ctx_bytes(build(inputs(days, [1.0, 2.0], caps={"B": 1, "A": 2})))
        self.assertEqual(a, ctx_bytes(build(inputs(days, [1.0, 2.0], caps={"A": 2, "B": 1}))))
        self.assertNotEqual(a, ctx_bytes(build(inputs(days, [1.0, 2.0], caps={"A": 2, "B": 1}, cash=2.0))))
        self.assertNotEqual(a, ctx_bytes(build(inputs(days, [1.0, 2.0001], caps={"A": 2, "B": 1}))))


class FromFetch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = synth.synthetic_store(Path(self.dir.name) / "s", symbols=("SPY", "QQQ"), start=D(2024, 6, 3),
                                          end=D(2025, 12, 31))

    def test_i6_the_live_builder_on_the_stores_bars_is_the_gyms_ctx_byte_for_byte(self):
        cases = synth.same_ctx_cases(self.root, symbols=("SPY", "QQQ"), history=30, count=20, seed=11)
        self.assertEqual(len(cases), 20)
        for case in cases:
            live = inputs_from_fetch(case["raw_rows"], case["all_rows"], day=case["day"], needs=case["needs"],
                                     **case["common"])
            self.assertEqual(ctx_bytes(build(live)), ctx_bytes(build(case["gym"])), case["day"])

    def test_the_gym_never_hands_over_a_row_after_t(self):
        bars = EquityStore(self.root).bars(["SPY"], "validation", history=5)
        needs = Needs(("SPY",), 5, 20)
        for t in (bars.first, bars.first + 7, bars.n - 1):
            got = inputs_from_bars(bars, t, needs=needs, **COMMON)
            self.assertEqual(int(got.days[-1]), int(bars.days[t]))
            self.assertEqual(got.raw["SPY"].shape, (6, 5))
            np.testing.assert_array_equal(got.raw["SPY"], bars.raw["SPY"][t - 5:t + 1])

    def test_refusals(self):
        bars = EquityStore(self.root).bars(["SPY", "QQQ"], "validation", history=3)
        needs = Needs(("SPY",), 3, 20)
        t = bars.first + 4
        day = bars.day(t).isoformat()
        raw = {"SPY": synth.bar_rows(bars, "SPY", t, adjustment="raw")}
        alls = {"SPY": synth.bar_rows(bars, "SPY", t, adjustment="all")}
        inputs_from_fetch(raw, alls, day=day, needs=needs, **COMMON)
        with self.assertRaisesRegex(ValueError, "no bar"):
            inputs_from_fetch({"SPY": raw["SPY"][:-1]}, {"SPY": alls["SPY"][:-1]}, day=day, needs=needs, **COMMON)
        with self.assertRaisesRegex(ValueError, "disagree"):
            inputs_from_fetch({"SPY": raw["SPY"][:-2] + raw["SPY"][-1:]}, alls, day=day, needs=needs, **COMMON)
        with self.assertRaisesRegex(ValueError, "twice"):
            inputs_from_fetch({"SPY": raw["SPY"] + raw["SPY"][-1:]}, alls, day=day, needs=needs, **COMMON)
        with self.assertRaisesRegex(ValueError, "not a session"):
            inputs_from_fetch(raw, alls, day="2025-01-01", needs=needs, **COMMON)
        t = [bars.day(i) for i in range(bars.n)].index(D(2025, 1, 21))
        raw, alls = (synth.bar_rows(bars, "SPY", t, adjustment=a) for a in ("raw", "all"))
        holiday = dict(raw[-1], t="2025-01-20T05:00:00Z")   # Martin Luther King Jr. Day
        with self.assertRaisesRegex(ValueError, "not a session"):
            inputs_from_fetch({"SPY": [*raw, holiday]}, {"SPY": [*alls, holiday]}, day="2025-01-21",
                              needs=Needs(("SPY",), 10, 20), **COMMON)


class AsOfIdentity(unittest.TestCase):
    def test_a_store_written_after_a_split_and_a_dividend_gives_the_same_ctx_at_t(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw = dict(symbols=("SPY", "QQQ"), start=D(2024, 11, 1), end=D(2025, 12, 31), seed=3,
                      splits={"SPY": [(D(2025, 8, 4), 2.0)]},
                      dividends={"SPY": [(D(2025, 3, 21), 1.75), (D(2025, 9, 19), 1.8)],
                                 "QQQ": [(D(2025, 6, 23), 0.8)]})
            early = synth.synthetic_store(Path(tmp) / "early", as_of=D(2025, 7, 15), **kw)
            late = synth.synthetic_store(Path(tmp) / "late", **kw)
            needs = Needs(("SPY", "QQQ"), 120, 20)
            a = EquityStore(early).bars(needs.symbols, "validation", history=120)
            b = EquityStore(late).bars(needs.symbols, "validation", history=120, end=D(2025, 7, 15))
            self.assertFalse(np.allclose(a.adj["SPY"], b.adj["SPY"]), "the later fetch rescaled the history")
            np.testing.assert_array_equal(a.raw["SPY"], b.raw["SPY"])
            total = 0
            for t in range(a.first, a.n):
                x = build(inputs_from_bars(a, t, needs=needs, **COMMON))
                y = build(inputs_from_bars(b, t, needs=needs, **COMMON))
                for sym in needs.symbols:
                    self.assertEqual(x.prices[sym], y.prices[sym])
                    # The vendor rounds the adjusted series to 4 decimals at its own scale: a later fetch agrees within
                    # that rounding (scaled by the split), never by an event's size.
                    for name in ("open", "high", "low", "close"):
                        u, v = getattr(x.bars[sym], name), getattr(y.bars[sym], name)
                        self.assertLessEqual(float(np.nanmax(np.abs(u - v))), 5e-4, (t, sym, name))
                    self.assertLessEqual(float(np.nanmax(np.abs(x.bars[sym].ret - y.bars[sym].ret))), 1e-5)
                total += 1
            self.assertGreater(total, 100)

    def test_a_later_fetch_with_no_new_event_is_the_same_ctx_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw = dict(symbols=("SPY",), start=D(2024, 11, 1), end=D(2025, 9, 30), seed=5,
                      dividends={"SPY": [(D(2025, 3, 21), 1.75)]})
            early = synth.synthetic_store(Path(tmp) / "early", as_of=D(2025, 7, 15), **kw)
            late = synth.synthetic_store(Path(tmp) / "late", **kw)
            needs = Needs(("SPY",), 60, 20)
            a = EquityStore(early).bars(needs.symbols, "validation", history=60)
            b = EquityStore(late).bars(needs.symbols, "validation", history=60, end=D(2025, 7, 15))
            for t in range(a.first, a.n, 7):
                self.assertEqual(ctx_bytes(build(inputs_from_bars(a, t, needs=needs, **COMMON))),
                                 ctx_bytes(build(inputs_from_bars(b, t, needs=needs, **COMMON))))


if __name__ == "__main__":
    unittest.main()
