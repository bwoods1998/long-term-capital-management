"""The equity daily store: its NYSE calendar from 2016, its windows, the gate's capability, and atomic, verified files.

Every store here is synthetic (`league.equity.synth`) or written by hand through `write_store`: no market data.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import numpy as np

from league.equity import EQUITY_STORE_VERSION, config, synth
from league.equity.store import (GATE_MARK, LOOK, EquityGateCapability, EquityStore, MissingData, StoreRefused,
                                 mint_equity_gate_capability, nyse_sessions, window_of, write_store)

D = dt.date


def row(days, price=100.0):
    out = {"days": list(days), "raw_v": [1000.0] * len(days)}
    for name in ("raw_o", "raw_h", "raw_l", "raw_c", "all_o", "all_h", "all_l", "all_c"):
        out[name] = [price] * len(days)
    return out


class Calendar(unittest.TestCase):
    def test_session_counts_match_the_nyse_years_2016_to_2026(self):
        counts = Counter(d.year for d, _ in nyse_sessions(D(2016, 1, 1), D(2026, 12, 31)))
        self.assertEqual(dict(counts), {2016: 252, 2017: 251, 2018: 251, 2019: 252, 2020: 253, 2021: 252, 2022: 251,
                                        2023: 250, 2024: 252, 2025: 250, 2026: 251})

    def test_rules_before_2022_have_no_juneteenth_and_the_2018_closure(self):
        days = {d for d, _ in nyse_sessions(D(2016, 1, 1), D(2021, 12, 31))}
        self.assertIn(D(2021, 6, 18), days, "Juneteenth (observed) was a trading day before 2022")
        self.assertNotIn(D(2018, 12, 5), days, "the National Day of Mourning closed the exchange")
        self.assertNotIn(D(2020, 7, 3), days, "Independence Day on a Saturday is observed on the Friday")
        self.assertNotIn(D(2021, 12, 24), days, "Christmas on a Saturday is observed on the Friday")
        self.assertIn(D(2021, 12, 31), days, "a Saturday New Year's Day is not observed on the Friday before")
        self.assertNotIn(D(2016, 3, 25), days, "Good Friday")
        early = {d for d, e in nyse_sessions(D(2016, 1, 1), D(2021, 12, 31)) if e}
        self.assertEqual(early, {D(2016, 11, 25), D(2017, 7, 3), D(2017, 11, 24), D(2018, 7, 3), D(2018, 11, 23),
                                 D(2018, 12, 24), D(2019, 7, 3), D(2019, 11, 29), D(2019, 12, 24), D(2020, 11, 27),
                                 D(2020, 12, 24), D(2021, 11, 26)})

    def test_from_2022_it_is_ltcm_data_exactly(self):
        from ltcm.data import us_equity_session

        day = D(2022, 1, 1)
        expected = []
        while day <= D(2026, 12, 31):
            session = us_equity_session(day)
            if session is not None:
                expected.append((day, session.early_close))
            day += dt.timedelta(days=1)
        self.assertEqual(nyse_sessions(D(2022, 1, 1), D(2026, 12, 31)), expected)
        self.assertNotIn(D(2025, 1, 9), {d for d, _ in expected})

    def test_before_2016_is_refused(self):
        with self.assertRaises(ValueError):
            nyse_sessions(D(2015, 12, 1), D(2016, 1, 10))

    def test_window_of(self):
        self.assertEqual([window_of(d) for d in (D(2015, 12, 31), D(2016, 1, 4), D(2024, 12, 31), D(2025, 1, 2),
                                                  D(2025, 12, 31), D(2026, 1, 2), D(2026, 9, 25), D(2026, 9, 28))],
                         ["pre", "train", "train", "validation", "validation", "holdout", "holdout", "forward"])
        self.assertEqual(window_of(D(2026, 1, 1)), "gap")


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name) / "equity-daily"


class Writing(StoreCase):
    def test_round_trip_layout_and_manifest(self):
        cal = nyse_sessions(D(2025, 1, 2), D(2025, 1, 31))
        days = [d for d, _ in cal]
        manifest = write_store(self.root, calendar=cal, series={"spy": row(days), "TLT": row(days[2:], 90.0)},
                               classes={"SPY": "etf", "tlt": "etf"}, fetched_through=days[-1], source="synthetic",
                               gate=False, audit={"passed": True})
        self.assertEqual((self.root / "VERSION").read_text().strip(), EQUITY_STORE_VERSION)
        self.assertFalse((self.root / GATE_MARK).exists())
        self.assertEqual(set(manifest["symbols"]), {"SPY", "TLT"})
        tlt = manifest["symbols"]["TLT"]
        self.assertEqual((tlt["first"], tlt["last"], tlt["rows"]), (days[2].isoformat(), days[-1].isoformat(),
                                                                     len(days) - 2))
        self.assertEqual(tlt["sha256"], hashlib.sha256((self.root / "bars" / "TLT.npz").read_bytes()).hexdigest())
        store = EquityStore(self.root)
        self.assertEqual(store.symbols(), {"SPY": "etf", "TLT": "etf"})
        self.assertEqual(store.manifest()["audit"], {"passed": True})
        self.assertEqual(store.sessions(), days)
        bars = store.bars(["SPY", "TLT"], "validation", history=0)
        self.assertTrue(np.isnan(bars.raw["TLT"][0]).all(), "no bar is NaN, never a guess")
        self.assertEqual(float(bars.raw["TLT"][2, 3]), 90.0)

    def test_the_same_data_is_the_same_bytes(self):
        cal = nyse_sessions(D(2025, 1, 2), D(2025, 1, 10))
        days = [d for d, _ in cal]
        kw = dict(calendar=cal, series={"SPY": row(days)}, classes={"SPY": "etf"}, fetched_through=days[-1],
                  source="synthetic", gate=False)
        first = write_store(self.root, **kw)
        second = write_store(Path(self.dir.name) / "again", **kw)
        self.assertEqual(first, second)

    def test_malformed_input_is_refused(self):
        cal = nyse_sessions(D(2025, 1, 2), D(2025, 1, 10))
        days = [d for d, _ in cal]
        base = dict(calendar=cal, classes={"SPY": "etf"}, fetched_through=days[-1], source="synthetic", gate=False)
        bad = row(days)
        bad["raw_c"] = bad["raw_c"][:-1]
        with self.assertRaisesRegex(ValueError, "aligned"):
            write_store(self.root, series={"SPY": bad}, **base)
        with self.assertRaisesRegex(ValueError, "calendar"):
            write_store(self.root, series={"SPY": row([*days, D(2025, 1, 11)])}, **base)
        with self.assertRaisesRegex(ValueError, "class"):
            write_store(self.root, series={"QQQ": row(days)}, **base)
        with self.assertRaisesRegex(ValueError, "increasing"):
            write_store(self.root, series={"SPY": row(days[::-1])}, **base)

    def test_a_changed_file_is_refused_not_mixed(self):
        synth.constant_store(self.root)
        path = self.root / "bars" / "SPY.npz"
        path.write_bytes(path.read_bytes() + b"\0")
        with self.assertRaises(MissingData):
            EquityStore(self.root).bars(["SPY"], "validation", history=0)

    def test_a_rewrite_with_fewer_symbols_drops_the_old_files(self):
        synth.synthetic_store(self.root, symbols=("SPY", "QQQ"), start=D(2025, 1, 2), end=D(2025, 2, 28))
        synth.synthetic_store(self.root, symbols=("SPY",), start=D(2025, 1, 2), end=D(2025, 2, 28))
        self.assertFalse((self.root / "bars" / "QQQ.npz").exists())
        with self.assertRaises(MissingData):
            EquityStore(self.root).bars(["QQQ"], "validation", history=0)

    def test_no_store_is_missing_data(self):
        with self.assertRaises(MissingData):
            EquityStore(self.root)


class Gate(StoreCase):
    def setUp(self):
        super().setUp()
        synth.synthetic_store(self.root, symbols=("SPY",), start=D(2024, 11, 1), end=D(2026, 10, 9), gate=True)

    def test_the_capability_cannot_be_constructed(self):
        with self.assertRaises(TypeError):
            EquityGateCapability()

    def test_minting_needs_the_gate_mark_and_a_reason(self):
        with self.assertRaises(StoreRefused):
            mint_equity_gate_capability(self.root, "  ")
        plain = Path(self.dir.name) / "gym"
        synth.constant_store(plain)
        with self.assertRaises(StoreRefused):
            mint_equity_gate_capability(plain, "the look")
        cap = mint_equity_gate_capability(self.root, "the look")
        self.assertEqual(cap.reason, "the look")
        with self.assertRaises(StoreRefused):
            EquityStore(plain, gate=cap)   # minted for another store

    def test_sealed_days_open_only_with_the_capability(self):
        store = EquityStore(self.root)
        for window in ("holdout", "forward", LOOK):
            with self.assertRaises(StoreRefused):
                store.bars(["SPY"], window, history=0)
            with self.assertRaises(StoreRefused):
                store.sessions(window)
        with self.assertRaises(StoreRefused):
            EquityStore(self.root, gate=object())
        gated = EquityStore(self.root, gate=mint_equity_gate_capability(self.root, "the look"))
        self.assertTrue(gated.gate)
        holdout = gated.bars(["SPY"], "holdout", history=3)
        self.assertEqual((holdout.day(holdout.first), holdout.day(holdout.n - 1)), (D(2026, 1, 2), D(2026, 9, 25)))
        self.assertEqual(holdout.first, 3)
        self.assertEqual(holdout.day(0).year, 2025, "history comes from the window before")

    def test_the_look_runs_to_the_last_close_capped_at_the_end_of_2026(self):
        gated = EquityStore(self.root, gate=mint_equity_gate_capability(self.root, "the look"))
        look = gated.bars(["SPY"], LOOK, history=0)
        self.assertEqual((look.day(0), look.day(look.n - 1)), (config.LOOK_FIRST, D(2026, 10, 9)))
        self.assertEqual(look.window, LOOK)
        later = Path(self.dir.name) / "later"
        synth.synthetic_store(later, symbols=("SPY",), start=D(2026, 11, 2), end=D(2027, 1, 29), gate=True)
        capped = EquityStore(later, gate=mint_equity_gate_capability(later, "the look")).bars(["SPY"], LOOK, history=0)
        self.assertEqual(capped.day(capped.n - 1), D(2026, 12, 31))

    def test_validation_history_never_reads_a_sealed_day_and_train_spans_stay_in_train(self):
        store = EquityStore(self.root)
        bars = store.bars(["SPY"], "validation", history=10)
        self.assertTrue(all(window_of(bars.day(i)) in ("train", "validation") for i in range(bars.n)))
        with self.assertRaises(StoreRefused):
            store.span(["SPY"], D(2024, 12, 1), D(2025, 1, 31), history=0)
        span = store.span(["SPY"], D(2024, 12, 2), D(2024, 12, 31), history=5)
        self.assertEqual((span.window, span.day(span.first)), ("train", D(2024, 12, 2)))
        with self.assertRaises(StoreRefused):
            store.bars(["SPY"], "nonsense", history=0)


class Slices(StoreCase):
    def test_history_first_cut_and_data_version(self):
        synth.synthetic_store(self.root, symbols=("SPY", "QQQ"), start=D(2024, 10, 1), end=D(2025, 3, 31),
                              gaps={"QQQ": [D(2025, 1, 6)]})
        store = EquityStore(self.root)
        bars = store.bars(["spy", "QQQ"], "validation", history=4, start=D(2025, 1, 3), end=D(2025, 1, 31))
        self.assertEqual(bars.symbols, ("SPY", "QQQ"))
        self.assertEqual((bars.first, bars.day(bars.first), bars.day(bars.n - 1)), (4, D(2025, 1, 3), D(2025, 1, 31)))
        self.assertEqual(bars.raw["SPY"].shape, (bars.n, 5))
        self.assertEqual(bars.adj["SPY"].shape, (bars.n, 4))
        gap = [bars.day(i) for i in range(bars.n)].index(D(2025, 1, 6))
        self.assertTrue(np.isnan(bars.raw["QQQ"][gap]).all())
        self.assertFalse(np.isnan(bars.raw["SPY"][gap]).any())
        with self.assertRaises(ValueError):
            bars.raw["SPY"][0, 0] = 1.0   # a slice is read-only
        self.assertEqual(len(bars.data_version), 24)
        self.assertEqual(bars.data_version, store.bars(["SPY", "QQQ"], "validation", history=4, start=D(2025, 1, 3),
                                                       end=D(2025, 1, 31)).data_version)
        self.assertNotEqual(bars.data_version, store.bars(["SPY"], "validation", history=4).data_version)


if __name__ == "__main__":
    unittest.main()
