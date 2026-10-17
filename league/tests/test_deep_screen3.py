"""S3's KEYS, BARS, FLOORS AND RULES (HISTORY-PLAN.md section 5.3, "Rules" and "Receipt"; league/deep/screen3.py):
the mask is one-sided; the 750-session, turnover, overnight, liquidity and recall rules refuse what they should; S3's
zero-edge FP on synthetic null worlds is at most 2.5% joint and 15% / 12% a key at the receipt's bars; the own
floors are a program's own null and the crash-stress null; the canary halt fires above its band.

Synthetic series only: no market data."""

from __future__ import annotations

import datetime as dt
import math
import unittest

import numpy as np

from league.deep import calendar, config, gate, screen3

KEEP = None


def dval_keep() -> np.ndarray:
    global KEEP
    if KEEP is None:
        plan = screen3.layout(["SPY"], 0, {"SPY": dt.date(1999, 1, 4)}, {})
        KEEP = gate._layout_keep(plan)
    return KEEP


class TheMaskIsOneSided(unittest.TestCase):
    def test_the_full_dval_layout(self):
        keep = dval_keep()
        self.assertEqual((keep.shape[0], int(keep.sum()), int((~keep).sum())), (1944, 1709, 235))

    def test_gains_made_only_in_the_masked_windows_do_not_pass(self):
        rng = np.random.default_rng(1)
        keep = dval_keep()
        x = rng.normal(0, 1e-3, keep.shape[0])
        x[~keep] += 4e-3                      # the famous windows only
        out = screen3.deep_key(x, x[keep], 1.0, 1.01)
        self.assertTrue(out["checks"]["full"])
        self.assertFalse(out["checks"]["masked"])
        self.assertFalse(out["passed"])

    def test_losses_in_the_masked_windows_count(self):
        rng = np.random.default_rng(2)
        keep = dval_keep()
        x = rng.normal(1.5e-4, 1e-3, keep.shape[0])
        x[~keep] -= 3e-3                      # a crash bought and held through
        out = screen3.deep_key(x, x[keep], 1.0, 1.01)
        self.assertTrue(out["checks"]["masked"])
        self.assertFalse(out["checks"]["full"])
        self.assertFalse(out["passed"])

    def test_the_stress_sum_must_be_above_zero_and_only_booleans_come_back(self):
        x = np.full(1944, 1e-3) + np.random.default_rng(3).normal(0, 1e-3, 1944)
        self.assertTrue(screen3.deep_key(x, x[dval_keep()], 0.5, 1.01)["passed"])
        out = screen3.deep_key(x, x[dval_keep()], -0.1, 1.01)
        self.assertFalse(out["passed"])
        self.assertEqual(out, {"passed": False, "checks": {"full": True, "masked": True, "stress": False}})
        for value in (out["passed"], *out["checks"].values()):
            self.assertIsInstance(value, bool)


class TheRules(unittest.TestCase):
    FIRST = {s: dt.date(1999, 1, 4) for s in config.DEEP_UNIVERSE}

    def rules(self, **kw):
        base = dict(symbols=["SPY", "QQQ"], history=40, first_days=self.FIRST, late_clean={}, round_trips=10.0,
                    overnight=0.0, strong_recall=False, blind=True)
        base.update(kw)
        return screen3.rules(**base)

    def test_an_eligible_program(self):
        out = self.rules()
        self.assertEqual((out["eligible"], out["why"], out["wait"]), (True, None, False))
        self.assertEqual(out["layout"]["scored"], 1944)

    def test_each_refusal(self):
        cases = {
            "not ETF only": dict(symbols=["SPY", "AAPL"]),
            "not ETF only (XLRE)": dict(symbols=["XLRE"]),
            "not calendar-blind": dict(blind=False),
            "more than 50 round trips a year": dict(round_trips=50.5),
            "more than 25% close-to-next-open lots": dict(overnight=0.26),
            "fewer than 750 scored DVAL sessions": dict(symbols=["GLD", "XLB"], history=252),
            "a strong-recall route": dict(strong_recall=True),
        }
        for why, kw in cases.items():
            with self.subTest(why):
                out = self.rules(**kw)
                self.assertFalse(out["eligible"])
                self.assertTrue(out["why"].startswith(why.split(" (")[0]), out["why"])
        self.assertTrue(self.rules(round_trips=50.0, overnight=0.25)["eligible"], "the bounds are inclusive")

    def test_an_unmeasured_route_waits(self):
        out = self.rules(strong_recall=None)
        self.assertEqual((out["eligible"], out["wait"]), (False, True))

    def test_the_liquid_core_and_the_late_spdrs(self):
        core = screen3.layout(["SPY", "XLF"], 20, self.FIRST, {})
        self.assertEqual(set(k for k, v in core["segments"].items() if v), {"A", "B"})
        late = screen3.layout(["SPY", "XLB"], 20, self.FIRST, {"XLB": False})
        self.assertEqual(late["scored"], 0, "XLB is not in A's core, and B waits on its stale-close audit")
        clean = screen3.layout(["SPY", "XLB"], 20, self.FIRST, {"XLB": True})
        self.assertEqual((clean["segments"]["A"], clean["segments"]["B"]["sessions"]), (None, 1007 - 0))

    def test_scored_sessions_start_after_inception_and_look_back(self):
        tlt = screen3.layout(["TLT"], 252, {"TLT": dt.date(2002, 7, 30)}, {})
        back, scored = calendar.segment("A")
        days = back + scored
        i0 = next(i for i, d in enumerate(days) if d >= dt.date(2002, 7, 30))
        self.assertEqual(tlt["segments"]["A"]["start"], i0 + 253)
        self.assertGreater(days[tlt["segments"]["A"]["start"]], dt.date(2003, 7, 1), "TLT from mid-2003")
        gld = screen3.layout(["GLD"], 252, {"GLD": dt.date(2004, 11, 18)}, {})
        self.assertIsNone(gld["segments"]["A"])
        b_back, b_scored = calendar.segment("B")
        start = gld["segments"]["B"]["start"]
        self.assertGreater((b_back + b_scored)[start], dt.date(2005, 11, 1), "GLD from late 2005")
        self.assertGreaterEqual(gld["scored"], config.MIN_SCORED_SESSIONS)

    def test_a_segment_with_a_needs_funds_gap_is_not_scored(self):
        full = screen3.layout(["SPY", "QQQ"], 40, self.FIRST, {})
        gap_b = screen3.layout(["SPY", "QQQ"], 40, self.FIRST, {}, {"QQQ": {"dval": 1}})
        self.assertEqual((gap_b["segments"]["A"], gap_b["segments"]["B"]), (None, None), "dval feeds both segments")
        self.assertIn("gaps", gap_b["why"]["B"])
        history_gap = screen3.layout(["SPY", "QQQ"], 40, self.FIRST, {}, {"SPY": {"history": 2}})
        self.assertIsNone(history_gap["segments"]["A"], "A's look-back is the history span")
        self.assertEqual(history_gap["segments"]["B"], full["segments"]["B"], "B reads dval alone")
        other = screen3.layout(["SPY", "QQQ"], 40, self.FIRST, {}, {"XLK": {"dval": 3}, "QQQ": {"traind": 1}})
        self.assertEqual(other["scored"], full["scored"], "another fund's gap, or a TRAIN-D one, unscores nothing")
        out = self.rules(gaps={"QQQ": {"dval": 1}})
        self.assertEqual((out["eligible"], out["why"]), (False, "fewer than 750 scored DVAL sessions"))

    def test_the_first_decision_holds_history_plus_one_bars(self):
        """Review 1's note 10: `i0 + history + 1` is the engine's rule (league/equity/store.py `_slice` hands a run
        history + 1 sessions before its first: its first decision's whole ctx), so at history 504 segment B scores
        1,006 sessions; the census counts one session looser."""
        b = screen3.layout(["SPY"], 504, self.FIRST, {})["segments"]["B"]
        self.assertEqual((b["start"], b["sessions"]), (505, 1006))
        self.assertEqual(screen3.layout(["SPY"], 503, self.FIRST, {})["segments"]["B"]["sessions"], 1007)

    def test_turnover_and_the_overnight_share(self):
        lots = [{"exit_day": "2016-02-01", "entry_at": "close", "exit_at": "open", "held_sessions": 1}] * 3 + \
               [{"exit_day": "2016-02-01", "entry_at": "open", "exit_at": "open", "held_sessions": 4}] + \
               [{"exit_day": None, "entry_at": "close", "exit_at": None, "held_sessions": 9}]
        self.assertAlmostEqual(screen3.round_trips_a_year([(lots, 252)]), 4.0)
        self.assertAlmostEqual(screen3.overnight_share(lots), 0.6)
        self.assertEqual(screen3.overnight_share([]), 0.0)


class TheBars(unittest.TestCase):
    def test_a_bar_is_the_larger_of_the_receipt_and_the_floor_plus_the_margin(self):
        self.assertEqual(screen3.bar(1.01, 0.70), 1.01)
        self.assertEqual(screen3.bar(1.01, 1.20), 1.25)
        self.assertEqual(screen3.bar(1.004, 0.0), 1.01, "a receipt figure is rounded up to the grid")
        self.assertIsNone(screen3.bar(1.01, None))
        self.assertIsNone(screen3.bar(1.01, 4.96), "past 5.00: ineligible")

    def test_the_receipt_figures_are_the_pinned_files(self):
        import hashlib
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / config.RECEIPT_PATH
        data = path.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), config.RECEIPT_SHA256)
        doc = json.loads(data)
        gates = doc["gates"]
        self.assertEqual((config.RECEIPT["c_D"], config.RECEIPT["c_R"]), (doc["c_D_receipt"], doc["c_R_receipt"]))
        self.assertEqual(config.RECEIPT["fp_zero_edge"], gates["G3_joint_le_0.025"]["value"])
        self.assertEqual(config.RECEIPT["fp_deep"], gates["G1_deep_alone_le_0.15"]["value"])
        self.assertEqual(config.RECEIPT["fp_recent"], gates["G2_recent_alone_le_0.12"]["value"])
        self.assertEqual(config.RECEIPT["worst_no_edge_now"], gates["G4_worst_no_edge_now_le_0.12_section3"]["value"])
        self.assertTrue(doc["all_gates_pass"])
        self.assertEqual(doc["prereg"]["sha256"], config.PREREG_SHA256)
        self.assertEqual(doc["c_margin"], config.FLOOR_MARGIN)
        self.assertEqual((doc["fp_cap_deep_alone"], doc["fp_cap_recent_alone"], doc["fp_cap_joint"],
                          doc["worst_no_edge_now_cap"]),
                         (config.DEEP_FP, config.RECENT_FP, config.JOINT_FP_MAX, config.WORST_NO_EDGE_NOW_MAX))
        self.assertEqual(doc["canary"]["U_by_n"], {str(n): gate.band_upper(n) for n in range(1, 16)})
        self.assertEqual((doc["looks"]["per_mechanism_cell_max"], doc["looks"]["total_before_erosion_review"]),
                         (config.LOOKS_PER_CELL, config.LOOK_BUDGET))
        self.assertEqual(doc["mask"]["by_window"], list(config.MASK_BY_WINDOW))
        self.assertEqual(doc["calendar"]["sha256"], config.CALENDAR_SHA256)
        self.assertIn("default_rng([20261017, 3, 7,", doc["floor"]["seeds"])
        self.assertIn("mean block 120", doc["floor"]["worlds"])
        self.assertEqual((config.FLOOR_SEED, config.FLOOR_BLOCK, config.FLOOR_WORLDS, config.STRESS_SHARE),
                         ((20261017, 3, 7), 120, 20_000, 0.05))
        self.assertIn("default_rng([20261017, 3, 8, block])", doc["canary"]["schedule"])
        self.assertIn("default_rng([20261017, 3, 9, look index])", doc["canary"]["construction"])


class TheReceiptHoldsOnSyntheticNulls(unittest.TestCase):
    """S3's zero-edge FP at the receipt's bars on fresh synthetic null worlds (another seed than the receipt's)."""

    WORLDS = 3000

    def worlds(self, name: str, length: int, seed: int) -> np.ndarray:
        rng = np.random.default_rng([seed, length])
        if name == "iid":
            return rng.standard_normal((self.WORLDS, length))
        if name == "ar1":
            e = rng.standard_normal((self.WORLDS, length)) * math.sqrt(0.99)
            x = np.empty_like(e)
            x[:, 0] = rng.standard_normal(self.WORLDS)
            for t in range(1, length):
                x[:, t] = 0.1 * x[:, t - 1] + e[:, t]
            return x
        x = rng.standard_normal((self.WORLDS, length))       # crash-stress: three times the vol in the mask
        if length == 1944:
            x[:, ~dval_keep()] *= 3.0
        return x

    def test_per_key_and_joint_fp(self):
        keep = dval_keep()
        for name in ("iid", "ar1", "crash"):
            d = self.worlds(name, 1944, 11)
            deep = np.mean([screen3.deep_key(row, row[keep], 1.0, config.RECEIPT["c_D"])["passed"] for row in d])
            r = self.worlds(name, 949, 12)
            recent = np.mean([screen3.recent_key([row[:505], row[505:755], row[755:]], config.RECEIPT["c_R"])["passed"]
                              for row in r])
            sd = lambda p: math.sqrt(p * (1 - p) / self.WORLDS)  # noqa: E731
            with self.subTest(world=name):
                self.assertLessEqual(deep, config.DEEP_FP + 3 * sd(config.DEEP_FP))
                self.assertLessEqual(recent, config.RECENT_FP + 3 * sd(config.RECENT_FP))
                self.assertLessEqual(deep * recent, config.JOINT_FP_MAX)


class TheOwnFloors(unittest.TestCase):
    """The receipt's floor: a stationary block bootstrap of the program's own sessions, BASE and CRASH, the key as
    judged in every world, null N0."""

    WORLDS = 3000

    def pool(self, seed: int = 0, edge: float = 0.0, scale: float = 1e-3, symbols: int = 2, phi: float = 0.0):
        rng = np.random.default_rng(seed)
        pieces = []
        for n in (1004, 751, 1508):
            W = np.full((symbols, n), 0.5 / symbols)
            RET = rng.normal(2e-4, 1e-2, (symbols, n))
            e = rng.normal(0, scale, n)
            noise = np.empty(n)
            noise[0] = e[0]
            for t in range(1, n):          # the program's own serial dependence (phi 0: none)
                noise[t] = phi * noise[t - 1] + e[t]
            r2 = (W * (RET + edge)).sum(0) + noise
            pieces.append({"r2": r2, "r1": r2 + 1e-5, "w": W.sum(0), "W": W, "RET": RET, "b": RET.mean(0)})
        return pieces

    def test_the_floor_is_the_programs_own_and_only_raises_the_bar_where_its_series_is_dependent(self):
        """A pool only 1.7 times a DVAL world gives an iid program a floor under the receipt's bar (the receipt
        binds: an own floor can only raise a bar); a strongly serially dependent one gets a higher floor."""
        keep = dval_keep()
        iid = screen3.deep_floor(self.pool(), keep, version_tag=7, worlds=self.WORLDS)
        self.assertIsNotNone(iid)
        self.assertLess(iid + config.FLOOR_MARGIN, config.RECEIPT["c_D"])
        self.assertEqual(screen3.bar(config.RECEIPT["c_D"], iid), config.RECEIPT["c_D"])
        self.assertEqual(iid, screen3.deep_floor(self.pool(), keep, version_tag=7, worlds=self.WORLDS),
                         "seeded by the version: the same floor again")
        dependent = screen3.deep_floor(self.pool(phi=0.6, scale=3e-3), keep, version_tag=7, worlds=self.WORLDS)
        self.assertGreater(dependent, iid + 0.2)

    def test_the_n0_null_removes_the_programs_own_edge_and_a_static_tilt_scores_nothing(self):
        keep = dval_keep()
        a = screen3.deep_floor(self.pool(edge=0.0), keep, version_tag=7, worlds=self.WORLDS)
        b = screen3.deep_floor(self.pool(edge=5e-4), keep, version_tag=7, worlds=self.WORLDS)
        self.assertLess(abs(a - b), 0.15, "a Train-era edge does not move the floor: it is removed")

    def test_the_crash_set_reads_the_stress_sessions(self):
        pool = screen3.Pool(self.pool())
        self.assertEqual(len(pool.stress), int(np.ceil(0.05 * len(pool.w))) or len(pool.stress))
        idx = screen3._worlds(np.random.default_rng(1), pool, 50, 1944, ~dval_keep())
        self.assertTrue(np.isin(idx[:, ~dval_keep()][:, 0], pool.stress).all(), "a stretch begins in a stress session")
        self.assertTrue((idx >= 0).all() and (idx < len(pool.w)).all())

    def test_no_pool_or_no_exposure_is_ineligible(self):
        keep = dval_keep()
        short = [{k: v[..., :200] for k, v in p.items()} for p in self.pool()]
        self.assertIsNone(screen3.deep_floor(short, keep, version_tag=1, worlds=200))
        flat = [{**p, "w": np.zeros_like(p["w"]), "W": np.zeros_like(p["W"])} for p in self.pool()]
        self.assertIsNone(screen3.deep_floor(flat, keep, version_tag=1, worlds=200))
        self.assertIsNone(screen3.recent_floor(flat, version_tag=1, worlds=200))

    def test_the_recent_floor_and_its_crash_positions(self):
        at = screen3.recent_stress_positions()
        self.assertEqual(at.shape, (949,))
        from league.equity import store as estore

        self.assertEqual(int(at.sum()), len(estore.nyse_sessions(*config.RECENT_STRESS)), "2020-02-20..03-23")
        self.assertFalse(at[505:].any())
        floor = screen3.recent_floor(self.pool(), version_tag=3, worlds=self.WORLDS)
        self.assertIsNotNone(floor)
        self.assertLess(floor + config.FLOOR_MARGIN, config.RECEIPT["c_R"] + 0.3)
        self.assertGreater(screen3.recent_floor(self.pool(phi=0.6, scale=3e-3), version_tag=3, worlds=self.WORLDS),
                           floor)


class TheCanaryHalt(unittest.TestCase):
    def test_the_band(self):
        self.assertEqual([gate.band_upper(n) for n in (1, 2, 5, 10, 15)], [1, 1, 3, 4, 5])

    def test_the_halt_fires_above_the_band(self):
        from league.tests import deep_fakes as F

        ledger = gate.Ledger(F.tmpdir(self))
        for i, deep in enumerate([True, True, True, False, False]):
            ledger.looks.append({"key": f"c{i}", "kind": "canary", "verdict": {"passed": deep, "deep": deep,
                                                                                "recent": None}})
        self.assertFalse(ledger.halted(), "3 of 5 is inside the band")
        ledger.looks[-1]["verdict"]["deep"] = True
        self.assertTrue(ledger.halted(), "4 of 5 is above it")
        ledger.cleared = [f"c{i}" for i in range(5)]
        self.assertFalse(ledger.halted(), "the captain's clearing")


if __name__ == "__main__":
    unittest.main()
