"""Completed stock volume is causal and has the same meaning in replay and live decisions. Invented data only."""

import datetime as dt
import math
import pickle
import tempfile
import unittest
from unittest.mock import patch

try:
    import numpy as np
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

try:
    import pyarrow  # noqa: F401
    HAVE_STORE = HAVE
except ImportError:  # pragma: no cover
    HAVE_STORE = False

if HAVE:
    from league.gym import engine as E
    from league.gym import runtime as R
    from league.gym.ctx import underlying_view
    from league.gym.day import Underlying, ordinal
    from league.gym.events import EventCalendar
    from league.live.chains import LiveChain, LiveDay, trading_days_around
    from league.tests.live_fakes import MONDAY
    from league.tests.test_live_step import LiveCase
    from scripts.data.sip import NY, completed_rows
if HAVE_STORE:
    from league.gym import store as S
    from league.gym import synth


DAY = dt.date(2024, 3, 14)


def bar(minute=570, volume=10.0, day=DAY):
    stamp = dt.datetime.combine(day, dt.time(), NY) + dt.timedelta(minutes=minute)
    return {"t": stamp.astimezone(dt.timezone.utc).isoformat(), "v": volume,
            "o": 400.0, "h": 401.0, "l": 399.0, "c": 400.0}


@unittest.skipUnless(HAVE, "numpy not installed")
class CompletedVolume(unittest.TestCase):
    def test_missing_and_invalid_volume_are_not_zero_and_never_forward_fill(self):
        for volumes in (None, np.array([999, 0, np.nan, -1, np.inf, 4])):
            under = Underlying(price=np.full(6, 400.0), volume=volumes)
            values = under.completed_volumes(5)
            expected = [0, np.nan, np.nan, np.nan, 4] if volumes is not None else [np.nan] * 5
            np.testing.assert_equal(values, expected)
            view = underlying_view("SPY", under.price, minute_volumes=values)
            self.assertTrue(math.isnan(view.volume))
            self.assertEqual(view.volume_coverage["minute_expected"], 5)
            self.assertEqual(view.volume_coverage["minute_bars"], 2 if volumes is not None else 0)
            self.assertTrue(math.isnan(under.session_volume()))
        zero = Underlying(price=np.full(3, 400.0), volume=np.array([np.nan, 0, 0]))
        self.assertEqual(zero.session_volume(), 0)
        self.assertEqual(underlying_view("SPY", zero.price, minute_volumes=zero.completed_volumes(2)).volume, 0)

    def test_current_bar_is_incomplete_and_late_bars_do_not_rewrite_past_decisions(self):
        chain = LiveChain("SPY", DAY, 570, 960)
        self.assertFalse(chain.record_volume(0, bar(570, 99)))
        self.assertFalse(chain.record_volume(1, bar(571, 99)))
        self.assertEqual(chain.underlying.completed_volumes(0).size, 0)
        self.assertTrue(chain.record_volume(1, bar(570, 0)))
        self.assertFalse(chain.record_volume(3, bar(570, 999)), "observed bars are never revised backward")
        self.assertTrue(chain.record_volume(3, bar(571, 42)))  # completed at 09:32, first seen at 09:33
        np.testing.assert_equal(chain.underlying.completed_volumes(2), [0, np.nan])
        np.testing.assert_equal(chain.underlying.completed_volumes(3), [0, 42, np.nan])

    def test_bad_or_extended_session_bars_and_index_proxy_volume_are_unavailable(self):
        bad = [None, {}, bar(569), bar(960), bar(570, day=DAY - dt.timedelta(days=1)),
               *[bar(volume=v) for v in (None, True, -1, np.inf, np.nan, "bad")],
               {**bar(), "t": "2024-03-14T09:30:00"}, {**bar(), "t": "2024-03-14T13:30:30Z"}]
        for item in bad:
            with self.subTest(bar=item):
                chain = LiveChain("SPY", DAY, 570, 960)
                self.assertFalse(chain.record_volume(390, item))
                self.assertTrue(np.isnan(chain.underlying.completed_volumes(390)).all())
        for root in ("XSP", "SPXW"):
            chain = LiveChain(root, DAY, 570, 960)
            self.assertFalse(chain.record_volume(1, bar(volume=100000)))

    def test_half_day_has_210_completed_bars_and_excludes_the_after_close_bar(self):
        chain = LiveChain("SPY", DAY, 570, 780)
        self.assertTrue(chain.record_volume(210, bar(779, 7)))
        self.assertFalse(chain.record_volume(210, bar(780, 999)))
        self.assertEqual(len(chain.underlying.completed_volumes(210)), 210)
        self.assertEqual(chain.underlying.completed_volumes(210)[-1], 7)
        self.assertTrue(math.isnan(chain.underlying.session_volume()))

    def test_arrays_are_immutable_copies_and_coverage_excludes_missing_history(self):
        minute = np.array([0, 20, np.nan])
        daily = np.array([120, np.nan, 0])
        view = underlying_view("SPY", [400] * 4, closes=[398, 399, 400],
                               minute_volumes=minute, daily_volumes=daily)
        minute[0] = daily[0] = 999
        self.assertEqual(view.minute_volumes[0], 0)
        self.assertEqual(view.daily_volumes[0], 120)
        self.assertEqual(view.prior_volume, 0)
        self.assertEqual(view.volume_coverage, {"basis": "completed_regular_session_bars", "minute_bars": 2,
            "minute_expected": 3, "history_sessions": 2, "history_expected": 3})
        for value in (view.minute_volumes, view.daily_volumes):
            self.assertNotIsInstance(value.base, np.ndarray)
            with self.assertRaises(ValueError):
                value.setflags(write=True)
        received = pickle.loads(pickle.dumps(view))  # the live decider's trusted incoming transport
        np.testing.assert_equal(received.minute_volumes, view.minute_volumes)
        np.testing.assert_equal(received.daily_volumes, view.daily_volumes)
        self.assertEqual(received.volume_coverage, view.volume_coverage)
        for value in (received.prices, received.closes, received.minute_volumes, received.daily_volumes):
            with self.assertRaises(ValueError):
                value.setflags(write=True)
        with self.assertRaisesRegex(ValueError, "completed minutes"):
            underlying_view("SPY", [400, 400], minute_volumes=[1, 2])
        with self.assertRaisesRegex(ValueError, "prior-session"):
            underlying_view("SPY", [400], closes=[399], daily_volumes=[])

    def test_history_keeps_volume_aligned_with_the_same_prior_price_sessions(self):
        history = E.History(2)
        self.assertTrue(history.add("SPY", np.array([1, 2]), volume=100))
        self.assertFalse(history.add("SPY", np.array([np.nan]), volume=999))
        history.add("SPY", np.array([2, 3]))
        history.add("SPY", np.array([3, 4]), volume=0)
        np.testing.assert_equal(history.arrays("SPY", 2)[3], [3, 4])
        np.testing.assert_equal(history.volume_array("SPY", 2), [np.nan, 0])
        np.testing.assert_equal(history.volume_array("SPY", 1), [0])
        self.assertEqual(history.volume_array("SPY", 0).size, 0)


@unittest.skipUnless(HAVE_STORE, "numpy/pyarrow not installed")
class ReplayVolume(unittest.TestCase):
    @staticmethod
    def quotes(writer, day):
        writer.nbbo("SPY", day, expiration=[day + dt.timedelta(days=1)], strike=[400.0], right=["C"],
                    minute=[571], bid=[1.0], ask=[1.1], bid_size=[50], ask_size=[50])

    def test_actual_sip_ingest_store_and_live_contexts_agree_at_each_completion(self):
        bars = [bar(570, 0), bar(571, 10), bar(573, 1000)]  # missing 09:32 must stay missing
        rows = completed_rows(bars, DAY, (570, 960))
        with tempfile.TemporaryDirectory() as path:
            writer = synth.Writer(path)
            writer.calendar([DAY])
            self.quotes(writer, DAY)
            writer.underlying("SPY", DAY, [r["minute"] for r in rows], [r["price"] for r in rows],
                              extra={"volume": [r["volume"] for r in rows]})
            writer.finish()
            store = S.Store(path)
            historical = E.DayData(store, DAY, ["SPY"], EventCalendar([DAY], store.session), E.History(2), ordinal(DAY))
            live = LiveDay(DAY, 570, 960, trading_days=trading_days_around(DAY))
            chain = live.chain("SPY")
            for mi in range(5):
                for item in bars:
                    row = completed_rows([item], DAY, (570, 960))[0]
                    if row["minute"] == 570 + mi:
                        self.assertTrue(chain.record_volume(mi, item))
                        chain.set_price(mi, row["price"])
                if mi and not math.isfinite(chain.underlying.price[mi]):
                    chain.set_price(mi, 400.0)
                actual, expected = live.under("SPY", mi, 2), historical.under("SPY", mi, 2)
                np.testing.assert_equal(actual.minute_volumes, expected.minute_volumes)
                np.testing.assert_equal(actual.volume, expected.volume)
                self.assertEqual(actual.volume_coverage, expected.volume_coverage)
            self.assertEqual(historical.under("SPY", 2, 2).volume, 10)
            self.assertTrue(math.isnan(historical.under("SPY", 4, 2).volume))
            earlier = historical.under("SPY", 2, 2).minute_volumes
            historical.chains["SPY"].underlying.volume[4] = 999999
            np.testing.assert_equal(earlier, [0, 10])
            historical.close()

    def test_replay_warm_history_and_completed_sessions_exclude_todays_total(self):
        prior, tomorrow = DAY - dt.timedelta(days=1), DAY + dt.timedelta(days=1)
        with tempfile.TemporaryDirectory() as path:
            writer = synth.Writer(path)
            writer.calendar([prior, DAY, tomorrow])
            for day, volume in ((prior, 1), (DAY, 2), (tomorrow, 3)):
                self.quotes(writer, day)
                writer.underlying("SPY", day, np.arange(570, 961), np.full(391, 400.0),
                                  extra={"volume": np.r_[np.nan, np.full(390, volume)]})
            writer.finish()
            code = '''
NEEDS = {"roots": ["SPY"], "history": 2, "cadence": 30, "start": 571, "end": 571}
PARAMS = {}
STATE = {"seen": []}
def decide(ctx):
    STATE["seen"].append([ctx.under.volume, ctx.under.daily_volumes.tolist(), ctx.under.prior_volume])
    return []
'''
            keep = []
            [result] = E.run([R.load_program(code)], S.Store(path), E.RunConfig(window="train", roots=("SPY",)),
                             days=[DAY, tomorrow], keep=keep)
            self.assertEqual(result["runtime"]["errors"], 0)
            self.assertEqual(keep[0].runner._namespace["STATE"]["seen"], [[2, [390], 390], [3, [390, 780], 780]])


@unittest.skipUnless(HAVE, "numpy not installed")
class LiveVolume(LiveCase if HAVE else unittest.TestCase):
    def test_existing_stock_snapshot_supplies_volume_without_an_extra_data_request(self):
        live = self.make([], real_money=False)
        day = live._ensure_day(MONDAY, 570, 960)
        original = self.market.stocks

        def stocks(symbols):
            result = original(symbols)
            for row in result.values():
                row["minuteBar"] = bar(570, 7, MONDAY)
            return result

        with patch.object(self.market, "stocks", side_effect=stocks):
            before = self.market.calls
            live._read(day, 1, {"SPY": (0, 1, .01)}, {})
            self.assertEqual(self.market.calls - before, 2, "one existing stock snapshot and one existing chain call")
            self.assertEqual(day.under("SPY", 1, 0).volume, 7)
            self.assertEqual(day.under("SPY", 0, 0).minute_volumes.size, 0)
        self.assertTrue(live._volume_dirty)
        self.assertNotIn("volume_error", live._done({}))
        self.assertEqual(live.state.get("underlying_volume_session")["roots"]["SPY"], [[1, 7.0, 1]])

    def test_restart_preserves_gaps_and_first_observed_minute_and_never_restores_another_day(self):
        live = self.make([], real_money=False)
        day = live._ensure_day(MONDAY, 570, 960)
        day.chain("SPY").record_volume(3, bar(570, 7, MONDAY))
        live._save_volume(day)
        live.state.close()
        live = self.make([], real_money=False)
        restored = live._ensure_day(MONDAY, 570, 960)
        np.testing.assert_equal(restored.under("SPY", 2, 0).minute_volumes, [np.nan, np.nan])
        np.testing.assert_equal(restored.under("SPY", 3, 0).minute_volumes, [7, np.nan, np.nan])
        self.assertTrue(math.isnan(restored.under("SPY", 3, 0).volume))
        tomorrow = live._ensure_day(MONDAY + dt.timedelta(days=1), 570, 960)
        self.assertEqual(tomorrow.chains, {})

    def test_prior_totals_require_all_regular_session_bars_and_ignore_daily_api_volume(self):
        live = self.make([], real_money=False)
        day = live._ensure_day(MONDAY, 570, 960)
        for root in ("SPY", "QQQ"):
            under = day.chain(root).underlying
            under.volume[1:] = 0
            under.volume_available_at[1:] = np.arange(1, 391)
        day.chain("QQQ").underlying.volume[3] = np.nan
        live._end_volume(day)
        totals = live.state.get("underlying_volume_history")
        self.assertEqual(totals["SPY"][MONDAY.isoformat()], {"volume": 0, "known": 390, "expected": 390})
        self.assertEqual(totals["QQQ"][MONDAY.isoformat()], {"volume": None, "known": 389, "expected": 390})
        tomorrow = MONDAY + dt.timedelta(days=1)
        later = LiveDay(tomorrow, 570, 960, trading_days=trading_days_around(tomorrow))

        def bars(symbols, **kwargs):
            return {root: [bar(570, 123456789, MONDAY - dt.timedelta(days=3)), bar(570, 999999999, MONDAY)]
                    for root in symbols}

        with patch.object(self.market, "bars", side_effect=bars):
            for root in ("SPY", "QQQ", "XSP"):
                live._history(later, root, 400.0, 400.0)
                later.chain(root).set_price(1, 400.0)
            np.testing.assert_equal(later.under("SPY", 1, 2).daily_volumes, [np.nan, 0])
            self.assertEqual(later.under("SPY", 1, 2).prior_volume, 0)
            self.assertEqual(later.under("SPY", 1, 2).volume_coverage["history_sessions"], 1)
            self.assertTrue(np.isnan(later.under("QQQ", 1, 2).daily_volumes).all())
            self.assertTrue(np.isnan(later.under("XSP", 1, 2).daily_volumes).all())
            # Even if the endpoint accidentally includes today's bar, today's recorded total is not prior history.
            same_day = LiveDay(MONDAY, 570, 960, trading_days=trading_days_around(MONDAY))
            live._history(same_day, "SPY", 400, 400)
            self.assertTrue(np.isnan(same_day.history_volumes["SPY"]).all())

    def test_volume_checkpoint_failure_is_visible_and_does_not_erase_observed_values(self):
        live = self.make([], real_money=False)
        day = live._ensure_day(MONDAY, 570, 960)
        day.chain("SPY").record_volume(1, bar(570, 7, MONDAY))
        live._volume_dirty = True
        with patch.object(live, "_save_volume", side_effect=OSError("unavailable")):
            self.assertEqual(live._done({})["volume_error"], "volume checkpoint: OSError")
        self.assertTrue(live._volume_dirty)
        self.assertEqual(day.under("SPY", 1, 0).volume, 7)
        self.assertNotIn("volume_error", live._done({}))
        self.assertFalse(live._volume_dirty)


if __name__ == "__main__":
    unittest.main()
