"""THE DIRECTION LANE's core (league/swarm/dlane.py, release D-1, Oct 9, 2026): its settings and their bounds, the Train
bar direction-v2 (E1, E3, E4, E5 at 1.0x; P1, R2, R3 at 1.5x; E2 and R1 reported only), the unit's live context, the card
box, the birth quota, the screen and its receipt, the agenda guard, the text agents read, and the walls that protect it.

Every figure here is invented: the fixtures are built so the rules can be read off them, never from the operator's
studies, and the dates of the invented closes are far from any year the swarm is judged on.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
import unittest
from pathlib import Path

from league import ci
from league.gym.results import _t_of
from league.swarm import architect, cards, dlane, evidence
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

GATE = {"dlane": {"mode": "gate"}}
#: Any figure or label of these years in text an agent reads is a leak (the hidden years, Validation, the holdout).
LEAK = re.compile(r"(?<![\d.$,])20(?:20|21|25|26)(?![\d])")


def pp_for(pnl: float, t: float, n: int) -> float:
    """The sum of squares of n daily P&Ls that sum to `pnl` and give the all-days t `t` (`results._t_of`)."""
    if t == 0 or pnl == 0:
        return 1.0e4 * (n - 1)
    var = (pnl / n / t) ** 2 * n
    return var * (n - 1) + pnl * pnl / n


def year(pnl: float, t: float, *, held: int = 240, days: int = 250, trades: int = 120, days_traded: int = 110,
         stats: bool = False) -> tuple[dict, dict]:
    """(by_year row, drift year row) of one invented Train year."""
    by = {"trades": trades, "days": days, "days_traded": days_traded, "pnl": pnl, "t_daily": t,
          "quarters_positive": "2/4", "quarter_pnl": {}}
    drift = {"days": days, "held_days": held, "pnl": pnl, "alpha": 0.0, "alpha_usd": pnl * 0.1, "t": 0.2, "beta": 900.0,
             "drift_usd": pnl * 0.9, "sum_sq": pp_for(pnl, t, days), "sum_pp": pp_for(pnl, t, days),
             "root_days": {"SPY": days}}
    if stats:
        drift["stats"] = {"roots": {"SPY": [days, 0.05, 0.07, 390.0 * days]}}
    return by, drift


def run(years: dict, *, trades_2024: list | None = None, status: str = "ok", pnl: float | None = None,
        stats: bool = False) -> dict:
    """An invented Train result over the years given ({year: (pnl, t, kwargs)})."""
    out = {"status": status, "roots": ["SPY"], "summary": {"quarters_positive": "6/12"}, "by_year": {},
           "drift": {"basis": "held-hours", "years": {}, "roots": ["SPY"],
                     "pooled": {"days": 750, "held_days": 600, "pnl": 0.0, "alpha": 0.0, "alpha_usd": 0.0, "beta": 900.0,
                                "drift_usd": 0.0, "t": 0.3}}}
    total = 0.0
    for y, (p, t, kw) in years.items():
        out["by_year"][y], out["drift"]["years"][y] = year(p, t, stats=stats, **kw)
        total += p
    rows = out["drift"]["years"].values()
    out["drift"]["pooled"].update(pnl=total, alpha_usd=sum(r["alpha_usd"] for r in rows),
                                  drift_usd=sum(r["drift_usd"] for r in rows))
    out["summary"]["pnl"] = total if pnl is None else pnl
    out["trades"] = trades_2024 if trades_2024 is not None else [
        {"day": f"2024-03-{d:02d}", "root": "SPY", "max_loss": 70.0 + d, "fees": 2.6, "qty": 1, "pnl": 1.0}
        for d in range(1, 22)]
    return out


def always_in(**over) -> dict:
    """Every Train year in the market (a prototype-shaped call program): 2022 at t -3.9, 2023 and 2024 up."""
    years = {"2022": (-1500.0, -3.9, {}), "2023": (2600.0, 2.1, {}), "2024": (2400.0, 1.9, {})}
    years.update(over)
    return run(years)


def unit_ctx(root: Path, *, spy: float | None = 649.08, sod: str | None = "1000.00", last: str | None = "1010.00") -> dict:
    """Write invented closes and health files under `root` and read them back (`unit_context`)."""
    if spy is not None:
        (root / dlane.CLOSES_FILE).write_text(json.dumps({"schema": 1, "closes": {"SPY": {"2099-01-02": spy - 5, "2099-01-03": spy}}}))
    stops = {}
    if sod is not None:
        stops["sod_equity"] = sod
    if last is not None:
        stops["last_reading"] = [0.0, last, "2099-01-03"]
    (root / dlane.HEALTH_FILE).write_text(json.dumps({"options_live": {"stops": stops}}))
    return dlane.unit_context(root, GATE)


def visible_text(*parts) -> str:
    return "\n".join(json.dumps(p, default=str) if not isinstance(p, str) else p for p in parts)


def _keys(doc) -> list:
    """Every key of a JSON document, at every depth."""
    if isinstance(doc, dict):
        return [k for key, value in doc.items() for k in (key, *_keys(value))]
    if isinstance(doc, list):
        return [k for value in doc for k in _keys(value)]
    return []


# ------------------------------------------------------------------------------------------------ 1. settings
class Settings(unittest.TestCase):
    def test_the_code_default_is_the_rollback_and_the_policy_switches_the_lane_on(self):
        self.assertEqual(dlane.cfg(None)["mode"], "off")
        self.assertFalse(dlane.on(None))
        self.assertFalse(dlane.on({"dlane": {}}))
        policy = json.loads((Path(ci.REPO) / "league" / "swarm" / "policy.json").read_text())["dlane"]
        defaults = dlane.cfg({"dlane": {**dlane.DEFAULTS}})
        # The committed block is the defaults, switched on in gate mode, with release D-1b's deploy (DSCREEN-ADOPT): calls
        # only, and D2 chosen with DSCREEN-2's receipt pinned. The code's defaults stay D-1's (S-C, no pin): a dropped
        # policy layer is the rollback whatever else it held.
        d2 = {"receipt_sha256": "c36059470d00241db67e1542361097e397289b87f024261b96da2db323c63b5b", "c": 1.0,
              "fp_lane_mixed": 0.1037, "fp_lane_2224": 0.1239, "power10": 0.1995, "fp_unconditional": None,
              "fp_both_windows_rose": None, "fp_lane_ci_mixed": [0.0957, 0.1116], "fp_lane_cluster_mixed": [0.079, 0.1276]}
        self.assertEqual(dlane.cfg({"dlane": policy}),
                         {**defaults, "mode": "gate", "structures": ["long_single"], "screen": "D2",
                          "screens": {"S-C": defaults["screens"]["S-C"], "D2": d2}},
                         "the committed block is the defaults, switched on in gate mode, with D-1b's deploy")
        c = dlane.cfg({"dlane": policy})
        # The operator's decisions of Oct 9, 05:30Z, as committed.
        self.assertEqual((c["birth_share"], c["max_share"], c["min_per_pass"]), (0.5, 0.6, 1))
        self.assertEqual((c["arm_fraction"], c["screen"]), (0.0, "D2"))
        self.assertEqual(c["screens"]["S-C"], {"look_level": 0.2, "sharpe_share": 0.25, "fp_unconditional": 0.0141,
                                               "fp_both_windows_rose": 0.0222, "fp_lane_2224": 0.0209})
        self.assertEqual(c["screens"]["D2"]["receipt_sha256"], d2["receipt_sha256"])
        self.assertEqual((c["val_tries"], c["looks_per_lineage"]), (1, 1))
        self.assertEqual((dlane.DEFAULTS["screen"], dlane.DEFAULTS["screens"]["D2"]), ("S-C", {"receipt_sha256": None}))
        self.assertEqual((c["alarm_min_looks"], c["alarm_pass_share"]), (10, 0.6))
        self.assertEqual((c["done_zero_edge_p"], c["k5_net_usd"], c["k5_clear"]), (0.13, -600.0, False))

    def test_a_malformed_value_is_its_default_and_a_number_past_a_bound_is_the_bound(self):
        c = dlane.cfg({"dlane": {"mode": "on", "birth_share": "half", "max_share": 0.2, "min_per_pass": 1.5,
                                 "active_share": 0.95, "min_active_years": 1, "out_t_floor": -3, "min_entry_days": 500,
                                 "c_train": 9, "cost_ratio": True, "unit_cap_usd": 500, "unit_share": 0.5,
                                 "arm_fraction": float("nan"), "screen": "D3", "roots": ["spy", "GLD", 3], "holding": "x",
                                 "structures": ["credit_vertical"], "classes": ["equity premium", "skew"]}})
        self.assertEqual(c["mode"], "shadow", "a malformed mode is shadow")
        self.assertEqual(c["birth_share"], 0.5)
        self.assertEqual(c["max_share"], 0.5, "never under birth_share")
        self.assertEqual(c["min_per_pass"], 1, "a count is a whole number")
        self.assertEqual((c["active_share"], c["min_active_years"], c["out_t_floor"], c["min_entry_days"]), (0.8, 2, -1.5, 200))
        self.assertEqual((c["c_train"], c["cost_ratio"]), (3.0, 0.5))
        self.assertEqual((c["unit_cap_usd"], c["unit_share"], c["arm_fraction"]), (129.0, 0.1, 0.0))
        self.assertEqual(c["screen"], "S-C")
        self.assertEqual(c["roots"], ["SPY"], "only the lane's roots")
        self.assertEqual(c["holding"], list(dlane.HOLDINGS))
        self.assertEqual(c["structures"], ["long_single", "debit_vertical"], "an empty list after filtering is the default")
        self.assertEqual(c["classes"], ["equity_premium"])
        self.assertIsNone(dlane.cfg({"dlane": {"unit_cap_usd": "x"}})["unit_cap_usd"])
        self.assertEqual(dlane.cfg({"dlane": {"unit_cap_usd": 10}})["unit_cap_usd"], 25.0)

    def test_the_evidence_numbers_can_only_be_tightened(self):
        c = dlane.cfg({"dlane": {"screens": {"S-C": {"look_level": 0.5, "sharpe_share": 0.1}}, "alarm_pass_share": 0.9,
                                 "alarm_min_looks": 3, "k5_net_usd": -5000}})
        self.assertEqual((c["screens"]["S-C"]["look_level"], c["screens"]["S-C"]["sharpe_share"]), (0.2, 0.25))
        self.assertEqual((c["alarm_pass_share"], c["alarm_min_looks"], c["k5_net_usd"]), (0.6, 10, -600.0))
        tight = dlane.cfg({"dlane": {"screens": {"S-C": {"look_level": 0.1, "sharpe_share": 0.5}}, "alarm_pass_share": 0.4,
                                     "k5_net_usd": -300}})
        self.assertEqual((tight["screens"]["S-C"]["look_level"], tight["screens"]["S-C"]["sharpe_share"]), (0.1, 0.5))
        self.assertEqual((tight["alarm_pass_share"], tight["k5_net_usd"]), (0.4, -300.0))

    def test_d2_block_keeps_only_a_well_formed_receipt(self):
        self.assertEqual(dlane.cfg({"dlane": {"screens": {"D2": {"receipt_sha256": "ABC", "c": 9}}}})["screens"]["D2"],
                         {"receipt_sha256": None, "c": None, "fp_unconditional": None, "fp_both_windows_rose": None,
                          "fp_lane_mixed": None, "fp_lane_2224": None, "power10": None, "fp_lane_ci_mixed": None,
                          "fp_lane_cluster_mixed": None})
        bad = dlane.cfg({"dlane": {"screens": {"D2": {"fp_lane_mixed": 1.5, "fp_lane_ci_mixed": [0.2, 0.1],
                                                      "fp_lane_cluster_mixed": [0.1], "power10": True}}}})["screens"]["D2"]
        self.assertEqual((bad["fp_lane_mixed"], bad["fp_lane_ci_mixed"], bad["fp_lane_cluster_mixed"], bad["power10"]),
                         (None, None, None, None), "a rate outside [0, 1] or an interval out of order is no figure")
        sha = "a" * 64
        self.assertEqual(dlane.cfg({"dlane": {"screens": {"D2": {"receipt_sha256": sha, "c": 1.7}}}})["screens"]["D2"]["c"], 1.7)


class Rollback(unittest.TestCase):
    def test_swarm_json_mode_off_rolls_the_committed_lane_back(self):
        """THE ROLLBACK (`dlane.mode` "off" in the box's swarm.json, read on the next loop): over the committed policy."""
        from unittest import mock

        from league.swarm import settings as S
        from league.tests import REAL_POLICY_PATH

        with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "POLICY_PATH", REAL_POLICY_PATH):
            (Path(d) / "swarm.json").write_text(json.dumps({"enabled": True}))
            self.assertEqual(dlane.cfg(S.load(d))["mode"], "gate", "the committed policy switches the lane on")
            (Path(d) / "swarm.json").write_text(json.dumps({"enabled": True, "dlane": {"mode": "off"}}))
            loaded = S.load(d)
            self.assertEqual(dlane.cfg(loaded)["mode"], "off")
            self.assertEqual(dlane.cfg(loaded)["birth_share"], 0.5, "the rest of the block holds")
            self.assertFalse(dlane.on(loaded))


class ModesAndK5(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.store = SwarmStore(Path(self.dir.name), clock=Clock())
        self.addCleanup(self.store.close)

    def test_k5_turns_gate_into_shadow_until_the_operator_clears_it(self):
        self.assertEqual(dlane.mode_effective(self.store, GATE), "gate")
        self.assertTrue(dlane.candidates_open(self.store, GATE))
        self.assertFalse(dlane.k5_trip(self.store, GATE, -599.99), "above the line: nothing")
        self.assertTrue(dlane.k5_trip(self.store, GATE, -600.0))
        self.assertFalse(dlane.k5_trip(self.store, GATE, -700.0), "written once")
        self.assertEqual(dlane.mode_effective(self.store, GATE), "shadow")
        self.assertFalse(dlane.candidates_open(self.store, GATE))
        state = dlane.k5_state(self.store, GATE)
        self.assertEqual((state["tripped"], state["net"]), (True, -600.0))
        cleared = {"dlane": {"mode": "gate", "k5_clear": True}}
        self.assertEqual(dlane.mode_effective(self.store, cleared), "gate", "swarm.json's k5_clear")
        self.assertFalse(dlane.k5_trip(self.store, cleared, -900.0))
        self.store.put(dlane.K5_KEY, None)
        self.assertEqual(dlane.mode_effective(self.store, GATE), "gate", "or deleting the kv")
        self.store.put(dlane.K5_KEY, "garbage")
        self.assertEqual(dlane.mode_effective(self.store, GATE), "shadow", "a malformed kv holds (fail-closed)")
        self.assertEqual(dlane.mode_effective(self.store, {"dlane": {"mode": "off"}}), "off", "K5 never switches the lane on")

    def test_an_unreadable_store_trips_nothing(self):
        class Broken:
            def get(self, key):
                raise OSError("disk")

        self.assertFalse(dlane.k5_state(Broken(), GATE)["tripped"])


# ------------------------------------------------------------------------------------------------ 2. train_score
class TrainScore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.unit = unit_ctx(self.root, sod="2000.00", last="2010.00")  # SPY scale 1.2, cap $200: E5 holds

    def score(self, result, **kw):
        return dlane.train_score(result, first_year=2022, unit=self.unit, settings=GATE, **kw)

    def test_score_is_the_pooled_t_of_daily_pnl_and_active_and_out_follow_exposure_and_frequency(self):
        r = run({"2022": (-50.0, -0.3, {"held": 60, "trades": 30, "days_traded": 25}), "2023": (2600.0, 2.1, {}),
                 "2024": (2400.0, 1.9, {})})
        out = self.score(r)
        rows = r["drift"]["years"]
        expect = _t_of(sum(x["pnl"] for x in rows.values()), sum(x["sum_pp"] for x in rows.values()), 750,
                       sum(x["sum_pp"] for x in rows.values()))
        self.assertAlmostEqual(out["score"], expect, places=5)
        self.assertEqual(out["t_pool"], out["score"])
        self.assertEqual(out["active"], ["2023", "2024"], "2022: under half the busiest exposure and too few trades")
        self.assertFalse(out["years"]["2022"]["active"])
        self.assertAlmostEqual(out["years"]["2022"]["t"], -0.3, places=3)
        self.assertTrue(out["eligible"], out["why"])
        self.assertEqual(out["objective"], "direction-v2")
        self.assertTrue(out["reported"]["E2"], "every in-market year's t is at least 0")
        # Exposure alone makes a year OUT, and the frequency floor alone does too.
        low = self.score(run({"2022": (0.0, 0.0, {"held": 100}), "2023": (2600.0, 2.1, {}), "2024": (2400.0, 1.9, {})}))
        self.assertFalse(low["years"]["2022"]["active"])
        thin = self.score(run({"2022": (10.0, 0.1, {"trades": 39}), "2023": (2600.0, 2.1, {}), "2024": (2400.0, 1.9, {})}))
        self.assertFalse(thin["years"]["2022"]["active"])
        few_days = self.score(run({"2022": (10.0, 0.1, {"days_traded": 19}), "2023": (2600.0, 2.1, {}),
                                   "2024": (2400.0, 1.9, {})}))
        self.assertFalse(few_days["years"]["2022"]["active"])

    def test_a_prototype_shaped_always_in_program_passes_the_bar_with_e2_reported_false(self):
        out = self.score(always_in())
        self.assertEqual(out["active"], ["2022", "2023", "2024"])
        self.assertTrue(out["eligible"], out["why"])
        self.assertIs(out["reported"]["E2"], False, "2022 is in the market and negative: reported, never a bar")
        self.assertEqual(out["worst_year"], "2022")
        self.assertEqual(out["fails"], [])

    def test_the_same_program_flat_in_2022_passes_with_e3(self):
        out = self.score(always_in(**{"2022": (-80.0, -0.6, {"held": 30, "trades": 12, "days_traded": 12})}))
        self.assertEqual(out["active"], ["2023", "2024"])
        self.assertTrue(out["eligible"], out["why"])
        self.assertTrue(out["reported"]["E2"])

    def test_e1_alone(self):
        out = self.score(run({"2022": (0.0, 0.0, {"held": 10, "trades": 5, "days_traded": 5}),
                              "2023": (0.0, 0.0, {"held": 10, "trades": 5, "days_traded": 5}),
                              "2024": (2400.0, 1.9, {})}))
        self.assertEqual(out["fails"], ["E1"])
        self.assertFalse(out["eligible"])
        self.assertTrue(out["why"].startswith("fails E1:"), out["why"])

    def test_e3_both_halves(self):
        out_year = {"held": 30, "trades": 12, "days_traded": 12}
        t_half = self.score(always_in(**{"2022": (-80.0, -1.1, out_year)}))
        self.assertEqual(t_half["fails"], ["E3"], "an OUT year at t -1.1 fails")
        self.assertIn("t is -1.10", t_half["why"])
        ok = self.score(always_in(**{"2022": (-80.0, -0.9, out_year)}))
        self.assertTrue(ok["eligible"], "at t -0.9 it passes")
        # The money half: the mean in-market P&L is 2,500, so an OUT year may lose 1,250 at most.
        money = self.score(always_in(**{"2022": (-1300.0, -0.5, out_year)}))
        self.assertEqual(money["fails"], ["E3"])
        self.assertIn("-$1,300", money["why"])
        edge = self.score(always_in(**{"2022": (-1250.0, -0.5, out_year)}))
        self.assertTrue(edge["eligible"], edge["why"])

    def test_a_flat_out_year_with_no_variance_reads_t_zero(self):
        out = self.score(always_in(**{"2022": (0.0, 0.0, {"held": 0, "trades": 0, "days_traded": 0})}))
        out_year = run({"2022": (0.0, 0.0, {"held": 0, "trades": 0, "days_traded": 0}), "2023": (2600.0, 2.1, {}),
                        "2024": (2400.0, 1.9, {})})
        out_year["drift"]["years"]["2022"]["sum_pp"] = 0.0  # every day zero: `_t_of` has no t
        flat = self.score(out_year)
        self.assertIsNone(flat["years"]["2022"]["t"])
        self.assertTrue(flat["eligible"], flat["why"])
        self.assertTrue(out["eligible"])

    def test_e4_alone(self):
        out = self.score(always_in(**{"2023": (2600.0, 2.1, {"days_traded": 59})}))
        self.assertEqual(out["fails"], ["E4"])
        self.assertIn("2023", out["why"])

    def test_e5_fail_pass_and_unknown(self):
        # 2024 units: (70+d+2.6), d = 1..21: median 83.6; x 1.2 = 100.32, over a $100 cap (10% of $1,000).
        small = unit_ctx(Path(tempfile.mkdtemp(dir=self.dir.name)))
        out = dlane.train_score(always_in(), unit=small, settings=GATE)
        self.assertEqual(out["unit"]["median_2024_usd"], 83.6)
        self.assertAlmostEqual(out["unit"]["scale"], 1.2, places=6)
        self.assertEqual((out["unit"]["scaled_usd"], out["unit"]["cap_usd"]), (100.32, 100.0))
        self.assertEqual(out["unit"]["verdict"], "fail")
        self.assertEqual(out["fails"], ["E5"])
        self.assertFalse(out["eligible"])
        self.assertTrue(out["why"].startswith("fails E5:"))
        # The unit cap read live: a larger account fits it.
        self.assertEqual(self.score(always_in())["unit"]["verdict"], "pass")
        # Unknown passes: no closes, no equity, or no 2024 trade.
        for ctx in (unit_ctx(Path(tempfile.mkdtemp(dir=self.dir.name)), spy=None),
                    unit_ctx(Path(tempfile.mkdtemp(dir=self.dir.name)), sod=None, last=None), None):
            got = dlane.train_score(always_in(), unit=ctx, settings=GATE)
            self.assertEqual(got["unit"]["verdict"], "unknown", got["unit"])
            self.assertTrue(got["eligible"], got["why"])
        none = always_in()
        none["trades"] = [{**t, "day": "2023" + t["day"][4:]} for t in none["trades"]]
        self.assertEqual(self.score(none)["unit"]["verdict"], "unknown")
        # qty and fees: a two-lot trade is priced per lot.
        two = always_in()
        two["trades"] = [{"day": "2024-05-01", "root": "SPY", "max_loss": 120.0, "fees": 4.0, "qty": 2, "pnl": 0.0}]
        self.assertEqual(self.score(two)["unit"]["median_2024_usd"], 62.0)

    def test_older_years_are_never_read(self):
        base = always_in(**{"2023": (2600.0, 2.1, {})})
        older = json.loads(json.dumps(base))
        by, drift = year(-9000.0, -5.0)
        older["by_year"]["2021"], older["drift"]["years"]["2021"] = by, drift
        a, b = self.score(base), dlane.train_score(older, first_year=2020, unit=self.unit, settings=GATE)
        self.assertEqual(a["score"], b["score"])
        self.assertEqual(sorted(b["years"]), ["2022", "2023", "2024"])

    def test_a_run_that_did_not_complete_or_predates_the_figures_is_never_eligible(self):
        self.assertFalse(self.score(always_in() | {"status": "error"})["eligible"])
        old = always_in()
        for row in old["drift"]["years"].values():
            row.pop("sum_pp")
        out = self.score(old)
        self.assertFalse(out["eligible"])
        self.assertEqual(out["fails"], [])
        self.assertIn("predates", out["why"])
        self.assertIsNone(out["score"])

    def test_beside_figures_are_reported(self):
        r = always_in()
        r["drift"] = json.loads(json.dumps(r["drift"]))
        r["drift"]["years"]["2023"]["stats"] = {"roots": {"SPY": [250, 0.04, 0.10, 97500.0]}}
        out = self.score(r)
        self.assertEqual(out["beside"]["beta_per_1pct"], 9.0)
        self.assertIsNotNone(out["beside"]["drift_share"])
        self.assertIsNone(out["beside"]["always_in_usd"], "only when every year carries its statistics")
        full = run({"2022": (-1500.0, -3.9, {}), "2023": (2600.0, 2.1, {}), "2024": (2400.0, 1.9, {})}, stats=True)
        self.assertAlmostEqual(self.score(full)["beside"]["always_in_usd"], 3 * 900.0 * 0.12, places=2)


# ------------------------------------------------------------------------------------------------ 3. robust_verdict
class RobustVerdict(unittest.TestCase):
    def setUp(self):
        self.base = dlane.train_score(always_in(), settings=GATE)  # unit unknown: eligible
        self.assertTrue(self.base["eligible"], self.base["why"])

    def test_p1_r2_r3_and_r1_reported_only(self):
        ok = dlane.robust_verdict(self.base, run({"2022": (-1800.0, -4.2, {}), "2023": (2100.0, 1.4, {}),
                                                  "2024": (1900.0, 1.3, {})}), settings=GATE)
        self.assertTrue(ok["known"])
        self.assertTrue(ok["passed"], ok["why"])
        self.assertEqual(ok["checks"], {"P1": True, "R2": True, "R3": True})
        self.assertFalse(ok["reported"]["R1"], "the pooled t at 1.5x is under 1.5: reported, never a bar")
        self.assertAlmostEqual(ok["ratio"], 2200.0 / 3500.0, places=4)
        lost = dlane.robust_verdict(self.base, run({"2022": (-1800.0, -4.2, {}), "2023": (2100.0, 1.4, {}),
                                                    "2024": (1900.0, 1.3, {})}, pnl=-1.0), settings=GATE)
        self.assertEqual(lost["fails"], ["P1"], "the run's own P&L, the House's existing rule")
        self.assertTrue(lost["why"].startswith("fails P1:"))
        r2 = dlane.robust_verdict(self.base, run({"2022": (0.0, 0.0, {"held": 5, "trades": 3, "days_traded": 3}),
                                                  "2023": (0.0, 0.0, {"held": 5, "trades": 3, "days_traded": 3}),
                                                  "2024": (4000.0, 2.0, {})}), settings=GATE)
        self.assertEqual(r2["fails"], ["R2"], "E1 at 1.5x")
        r2b = dlane.robust_verdict(self.base, run({"2022": (-900.0, -1.4, {"held": 30, "trades": 12, "days_traded": 12}),
                                                   "2023": (2400.0, 1.8, {}), "2024": (2200.0, 1.7, {})}), settings=GATE)
        self.assertEqual(r2b["fails"], ["R2"], "E3 at 1.5x")
        r3 = dlane.robust_verdict(self.base, run({"2022": (-1900.0, -4.4, {}), "2023": (1700.0, 1.1, {}),
                                                  "2024": (1800.0, 1.2, {})}), settings=GATE)
        self.assertEqual(r3["fails"], ["R3"], "1,600 is under half of 3,500")
        self.assertFalse(r3["passed"])

    def test_counts_the_15x_run_lacks_are_the_10x_runs(self):
        r15 = run({"2022": (-1800.0, -4.2, {}), "2023": (2100.0, 1.4, {}), "2024": (1900.0, 1.3, {})})
        r15["by_year"] = {y: {"pnl": row["pnl"], "trades": row["trades"]} for y, row in r15["by_year"].items()}
        out = dlane.robust_verdict(self.base, r15, settings=GATE)
        self.assertTrue(out["passed"], out["why"])

    def test_nothing_to_judge_is_never_a_demotion(self):
        for r15 in (run({"2023": (1.0, 0.1, {})}, status="error"), {"status": "ok", "summary": {"pnl": 5.0}}):
            out = dlane.robust_verdict(self.base, r15, settings=GATE)
            self.assertFalse(out["known"])
            self.assertFalse(out["passed"])
        out = dlane.robust_verdict(None, run({"2022": (-1800.0, -4.2, {}), "2023": (2100.0, 1.4, {}),
                                              "2024": (1900.0, 1.3, {})}), settings=GATE)
        self.assertFalse(out["known"], "no 1.0x score: R3 cannot be read")


# ------------------------------------------------------------------------------------------------ 5. cards and the lane
class Cards(unittest.TestCase):
    CARD = {"lane": "direction", "mechanism_class": "equity_premium", "holding": "days_4_10",
            "ablation": {"param": "gate_on", "off": 0}}

    def test_alpha_cards_and_a_direction_card_in_the_box(self):
        self.assertEqual(dlane.card_errors({"mechanism_class": "skew"}, "debit_vertical", ["XSP"], GATE), [])
        self.assertEqual(dlane.card_errors({**self.CARD, "lane": "alpha"}, "iron_condor", ["GLD"], GATE), [])
        self.assertEqual(dlane.card_errors(self.CARD, "long_single", ["SPY", "qqq"], GATE), [])
        self.assertEqual(dlane.lane_value({})[0], "alpha")
        self.assertEqual(dlane.lane_value({"lane": " Direction "}), ("direction", None))

    def test_every_reason_is_named(self):
        bad = {"lane": "direction", "mechanism_class": "skew", "holding": "intraday", "ablation": {"flat": True}}
        errors = dlane.card_errors(bad, "iron_condor", ["SPY", "GLD"], GATE)
        self.assertEqual([e.split(":")[0] for e in errors], ["mechanism_class", "structure", "roots", "holding", "ablation"])
        self.assertIn("never flat", errors[-1])
        self.assertIn("GLD", errors[2])
        self.assertEqual(dlane.card_errors({**self.CARD, "ablation": "flat"}, "long_single", ["SPY"], GATE)[0].split(":")[0],
                         "ablation")
        self.assertIn("none given", dlane.card_errors(self.CARD, "long_single", [], GATE)[0])
        self.assertEqual(dlane.card_errors({"lane": "beta"}, "long_single", ["SPY"], GATE),
                         ["lane: 'beta' is not one of alpha, direction"])

    def test_the_lane_off_refuses_every_direction_card(self):
        errors = dlane.card_errors(self.CARD, "long_single", ["SPY"], {"dlane": {"mode": "off"}})
        self.assertEqual(len(errors), 1)
        self.assertIn("dlane.mode is off", errors[0])


class Lane(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.store = SwarmStore(Path(self.dir.name), clock=Clock())
        self.addCleanup(self.store.close)

    def family(self, mechanism, **spec):
        return self.store.add_family({"mechanism": mechanism, "structure": "long_single", "roots": ["SPY"], **spec},
                                     origin="architect")

    def test_lane_from_spec_or_card_and_alpha_while_off_without_a_store_read(self):
        legacy = self.family("A legacy family born before the direction lane existed at all.")
        direct = self.family("Index calls held while implied volatility is calm against its own year.", lane="direction")
        carded = self.family("Index calls held while price is above its own long moving average.")
        cards.put(self.store, carded["id"], {"lane": "direction", "mechanism_class": "trend_momentum"}, "long_single")
        self.assertEqual(dlane.lane_of(self.store, legacy, GATE), "alpha")
        self.assertEqual(dlane.lane_of(self.store, direct, GATE), "direction")
        self.assertEqual(dlane.lane_of(self.store, carded, GATE), "direction")

        class NoStore:
            def __getattr__(self, name):
                raise AssertionError("the rollback reads no store")

        for fam in (legacy, direct, carded):
            self.assertEqual(dlane.lane_of(NoStore(), fam, {"dlane": {"mode": "off"}}), "alpha")
            self.assertEqual(dlane.lane_of(NoStore(), fam, {}), "alpha")
        self.assertEqual(dlane.declared_lane(self.store, direct), "direction", "whatever the mode")
        self.assertEqual(dlane.alive_direction(self.store, GATE), 2)
        self.assertEqual(dlane.alive_direction(self.store, {}), 0)


# ------------------------------------------------------------------------------------------------ the birth quota
class Quota(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)

    def births(self, alpha, direction):
        for _ in range(alpha):
            self.store.event("swarm.born", "a", {"structure": "long_single"})
        for _ in range(direction):
            self.store.event("swarm.born", "d", {"structure": "long_single", "lane": "direction"})

    def quota(self, want, settings=GATE, alive=0):
        return dlane.DirectionQuota(self.store, settings, now=self.clock(), want=want, alive=alive)

    def test_the_floor_is_reserved_for_direction_and_never_filled_with_alpha(self):
        q = self.quota(6)
        self.assertEqual((q.floor, q.pass_cap), (3, 3))
        self.assertTrue(all(q.admits("alpha") for _ in range(3)))
        for _ in range(3):
            q.born("alpha")
        self.assertFalse(q.admits("alpha"), "the reserved births are never alpha's")
        self.assertIn("never filled with alpha", q.reasons[-1])
        self.assertEqual(q.short(), 3)
        q.born("direction")
        self.assertEqual(q.event(), {"lane_births": {"alpha": 3, "direction": 1}, "lane_refused": {"alpha": 1, "direction": 0},
                                     "lane_short": 2})
        self.assertEqual(self.quota(1).floor, 1, "at least min_per_pass while the lane is behind")
        self.assertEqual(self.quota(5).floor, 3)

    def test_at_its_share_nothing_is_reserved_and_the_cap_holds_the_alpha_lanes_forty_percent(self):
        self.births(5, 5)
        q = self.quota(4)
        self.assertEqual(q.floor, 0, "at its share: nothing reserved")
        self.assertTrue(q.admits("alpha"))
        self.births(0, 2)  # 7 of 12: one more would be 8 of 13, past 60%
        q = self.quota(4)
        self.assertFalse(q.admits("direction"))
        self.assertIn("dlane.max_share", q.reasons[-1])
        self.assertTrue(q.admits("alpha"))

    def test_the_pass_cap_and_max_alive(self):
        self.births(20, 0)
        q = self.quota(6)
        for _ in range(3):
            self.assertTrue(q.admits("direction"))
            q.born("direction")
        self.assertFalse(q.admits("direction"), "the pass's cap: max(floor, floor(0.6 x 6))")
        full = self.quota(6, alive=24)
        self.assertEqual(full.floor, 0)
        self.assertFalse(full.admits("direction"))
        self.assertIn("dlane.max_alive", full.reasons[-1])

    def test_off_limits_no_alpha_birth_and_admits_no_direction(self):
        self.births(0, 5)
        q = self.quota(6, settings={"dlane": {"mode": "off"}})
        self.assertEqual((q.floor, q.pass_cap, q.window), (0, 0, {"alpha": 0, "direction": 0}))
        for _ in range(6):
            self.assertTrue(q.admits("alpha"))
            q.born("alpha")
        self.assertFalse(q.admits("direction"))
        self.assertEqual(q.text(), "")

    def test_text_and_counts(self):
        self.births(3, 1)
        q = self.quota(4)
        self.assertIn("direction 1 of 4 (25%)", q.text())
        self.assertIn("at least 2 of its 4 births are DIRECTION", q.text())
        self.assertIsNone(LEAK.search(q.text()))
        self.assertEqual(dlane.born_counts(self.store, 24, now=self.clock()), {"alpha": 3, "direction": 1})

    def test_lane_only_after_twelve_hours_without_a_direction_birth(self):
        self.assertEqual(dlane.lane_only_due(self.store, {}, now=self.clock())[0], False)
        self.assertEqual(dlane.lane_only_due(self.store, GATE, now=self.clock())[0], False, "the lane just started")
        self.clock.advance(13 * 3600)
        due, why = dlane.lane_only_due(self.store, GATE, now=self.clock(), alive=10, ceiling=20)
        self.assertTrue(due, why)
        self.assertFalse(dlane.lane_only_due(self.store, GATE, now=self.clock(), alive=20, ceiling=20)[0])
        dlane.lane_only_mark(self.store, now=self.clock())
        self.assertFalse(dlane.lane_only_due(self.store, GATE, now=self.clock())[0], "one request a window")
        self.clock.advance(13 * 3600)
        self.births(0, 1)
        self.assertFalse(dlane.lane_only_due(self.store, GATE, now=self.clock())[0], "a direction birth in the window")
        self.assertIsNotNone(dlane.last_direction_birth(self.store))


# ------------------------------------------------------------------------------------------------ the unit's context
class UnitContext(unittest.TestCase):
    def test_it_reads_the_last_close_and_the_lower_equity_and_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = unit_ctx(Path(d))
            self.assertTrue(ctx["known"])
            self.assertEqual(ctx["closes"], {"SPY": 649.08})
            self.assertAlmostEqual(ctx["scale"]["SPY"], 1.2, places=9)
            self.assertEqual((ctx["equity_usd"], ctx["cap_usd"]), (1000.0, 100.0))
            capped = dlane.unit_context(Path(d), {"dlane": {"mode": "gate", "unit_cap_usd": 75}})
            self.assertEqual(capped["cap_usd"], 75.0)
            over = dlane.unit_context(Path(d), {"dlane": {"mode": "gate", "unit_cap_usd": 129}})
            self.assertEqual(over["cap_usd"], 100.0, "never above the share of the live equity")
            (Path(d) / dlane.CLOSES_FILE).write_text("{not json")
            (Path(d) / dlane.HEALTH_FILE).write_text(json.dumps({"options_live": {"stops": {"sod_equity": "x",
                                                                                           "last_reading": [1]}}}))
            ctx = dlane.unit_context(Path(d), GATE)
            self.assertFalse(ctx["known"])
            self.assertIn("no index close", ctx["why"])
            self.assertIn("no account equity", ctx["why"])
        self.assertFalse(dlane.unit_context("/nowhere/at/all", GATE)["known"])
        self.assertFalse(dlane.unit_context(None, GATE)["known"])

    def test_a_store_names_its_root(self):
        with tempfile.TemporaryDirectory() as d:
            store = SwarmStore(Path(d), clock=Clock())
            try:
                unit_ctx(Path(d))
                self.assertTrue(dlane.unit_context(store, GATE)["known"])
            finally:
                store.close()


# ------------------------------------------------------------------------------------------------ records and the mark
class Records(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.fam = self.store.add_family({"mechanism": "Index calls held while implied vol is calm against its year.",
                                          "structure": "long_single", "roots": ["SPY"], "lane": "direction"},
                                         origin="architect")

    def test_record_and_failure_counts_are_ids_and_counts_only(self):
        fail = dlane.train_score(always_in(**{"2023": (2600.0, 2.1, {"days_traded": 59})}), settings=GATE)
        good = dlane.train_score(always_in(), settings=GATE)
        dlane.record(self.store, self.fam["id"], 1, score=fail)
        dlane.record(self.store, self.fam["id"], 2, score=good)
        dlane.record(self.store, self.fam["id"], 2, robust={"known": True, "passed": False, "fails": ["R3"],
                                                            "reported": {"R1": False}})
        out = dlane.failure_counts(self.store, 48, now=self.clock())
        self.assertEqual((out["families"], out["versions"], out["eligible"]), (1, 2, 1))
        self.assertEqual(out["fails"]["E4"], 1)
        self.assertEqual(out["robust"]["R3"], 1)
        self.assertEqual(out["reported_misses"], {"E2": 2, "R1": 1})
        self.assertEqual(out["ids"], [self.fam["id"]])
        text = json.dumps(out)
        self.assertNotIn("2022", text, "no year, no figure")
        self.clock.advance(49 * 3600)
        self.assertEqual(dlane.failure_counts(self.store, 48, now=self.clock())["versions"], 0)
        state = self.store.family(self.fam["id"])["state"][dlane.STATE_KEY]
        self.assertEqual(sorted(state["versions"]), ["1", "2"])
        for n in range(3, 20):
            dlane.record(self.store, self.fam["id"], n, score=good)
        self.assertEqual(len(self.store.family(self.fam["id"])["state"][dlane.STATE_KEY]["versions"]), dlane.VERSIONS_KEPT)

    def add(self, result, n, stress, *, summary_extra=None, prune=False):
        result = {**result, "run_id": f"r{n}-{stress}"}
        if summary_extra:
            result["summary"] = {**result["summary"], **summary_extra}
        row = self.store.add_run(self.fam["id"], n, result, window="train", stress=stress,
                                 purpose="research" if stress == 1.0 else "robustness")
        if prune:
            self.store._exec("UPDATE runs SET path=NULL WHERE run_id=?", (row["run_id"],))
        return row

    def test_the_incubator_mark_from_the_lane_verdict(self):
        unit = {"scale": {"SPY": 1.0}, "cap_usd": 200.0}
        out = dlane.lane_verdict(self.store, self.fam, 1, GATE, unit=unit)
        self.assertEqual((out["known"], out["drop"], out["why"]), (False, False, "no completed Train run"))
        self.add(always_in(), 1, 1.0)
        owed = dlane.lane_verdict(self.store, self.fam, 1, GATE, unit=unit)
        self.assertEqual((owed["known"], owed["passed"], owed["drop"]), (False, False, False))
        self.assertIn("1.5x", owed["why"])
        self.add(run({"2022": (-1800.0, -4.2, {}), "2023": (2100.0, 1.4, {}), "2024": (1900.0, 1.3, {})}), 1, 1.5)
        mark = dlane.lane_verdict(self.store, self.fam, 1, GATE, unit=unit)
        self.assertEqual((mark["known"], mark["passed"], mark["drop"]), (True, True, False), mark["why"])
        self.assertEqual(mark["lane"], "direction")
        self.assertEqual(mark["score"]["unit"]["verdict"], "pass")
        # A known bar failure drops the mark; an E5 failure (today's prices) never does.
        self.add(always_in(**{"2023": (2600.0, 2.1, {"days_traded": 59})}), 2, 1.0)
        bad = dlane.lane_verdict(self.store, self.fam, 2, GATE, unit=unit)
        self.assertEqual((bad["known"], bad["passed"], bad["drop"]), (True, False, True))
        tight = dlane.lane_verdict(self.store, self.fam, 1, GATE, unit={"scale": {"SPY": 1.0}, "cap_usd": 50.0})
        self.assertEqual((tight["known"], tight["passed"], tight["drop"]), (True, False, False))
        self.assertTrue(tight["why"].startswith("fails E5"))

    def test_a_pruned_run_reads_its_stored_compact_score(self):
        unit = {"scale": {"SPY": 1.0}, "cap_usd": 200.0}
        score = dlane.train_score(always_in(), unit=unit, settings=GATE)
        self.add(always_in(), 3, 1.0, summary_extra={dlane.STATE_KEY: dlane.compact(score)}, prune=True)
        r15 = run({"2022": (-1800.0, -4.2, {}), "2023": (2100.0, 1.4, {}), "2024": (1900.0, 1.3, {})})
        self.add(r15, 3, 1.5, prune=True)
        self.store.set_state(self.fam["id"], robustness={"3": {"stress_1.5": evidence.robustness_view(r15)}})
        fam = self.store.family(self.fam["id"])
        mark = dlane.lane_verdict(self.store, fam, 3, GATE, unit=unit)
        self.assertEqual((mark["known"], mark["passed"]), (True, True), mark["why"])
        repriced = dlane.lane_verdict(self.store, fam, 3, GATE, unit={"scale": {"SPY": 1.0}, "cap_usd": 50.0})
        self.assertEqual((repriced["passed"], repriced["drop"]), (False, False))
        self.assertIn("E5", repriced["why"])
        self.add(always_in(), 4, 1.0, prune=True)
        owed = dlane.lane_verdict(self.store, fam, 4, GATE, unit=unit)
        self.assertEqual((owed["known"], owed["drop"]), (False, False))


# ------------------------------------------------------------------------------------------------ 12. the screen
class Screen(unittest.TestCase):
    D2 = {"dlane": {"mode": "gate", "screen": "D2", "structures": ["long_single"]}}

    def test_alpha_is_the_evidence_lines_exactly_and_sc_is_the_direction_lanes(self):
        alpha = dlane.screen_effective(GATE, "alpha")
        self.assertEqual((alpha["screen"], alpha["look_level"], alpha["sharpe_share"]),
                         ("S-B", evidence.LOOK_LEVEL, evidence.HOLDOUT_SHARPE_SHARE))
        self.assertEqual((evidence.LOOK_LEVEL, evidence.HOLDOUT_SHARPE_SHARE, evidence.ALARM_PASS_SHARE), (0.10, 0.5, 0.30),
                         "the alpha lane's lines are not moved by this release")
        sc = dlane.screen_effective(GATE, "direction")
        self.assertEqual((sc["lane"], sc["screen"], sc["look_level"], sc["sharpe_share"], sc["receipt"]),
                         ("direction", "S-C", 0.2, 0.25, None))
        self.assertEqual(dlane.screen_effective({"dlane": {"mode": "off"}}, "direction")["screen"], "S-B",
                         "the rollback: every lane is alpha")
        self.assertEqual(dlane.screen_effective({"dlane": {"mode": "shadow"}}, "direction")["screen"], "S-C")

    def test_d2_is_refused_without_a_receipt_pinned_in_the_repositorys_policy(self):
        refused = dlane.screen_effective(self.D2, "direction", policy={})
        self.assertEqual(refused["screen"], "S-C")
        self.assertIn("D2 refused", refused["why"])
        sha = hashlib.sha256(b"an invented receipt").hexdigest()
        swarm_json = {"dlane": {"mode": "gate", "screen": "D2", "screens": {"D2": {"receipt_sha256": sha, "c": 1.5}}}}
        self.assertEqual(dlane.screen_effective(swarm_json, "direction", policy={})["screen"], "S-C",
                         "a receipt in the box's settings is never a pin")
        no_c = {"dlane": {"screens": {"D2": {"receipt_sha256": sha}}}}
        self.assertIn("no calibrated c", dlane.screen_effective(self.D2, "direction", policy=no_c)["why"])
        pinned = {"dlane": {"screens": {"D2": {"receipt_sha256": sha, "c": 1.5, "fp_unconditional": 0.1}}}}
        d2 = dlane.screen_effective(self.D2, "direction", policy=pinned)
        self.assertEqual((d2["screen"], d2["receipt"], d2["c"], d2["validation"]), ("D2", sha, 1.5, "precheck"))
        self.assertEqual(dlane.screen_effective(GATE, "direction", policy=pinned)["screen"], "S-C", "only when chosen")
        self.assertEqual(dlane.screen_effective(self.D2, "alpha", policy=pinned)["screen"], "S-B")
        # Release D-1b: D2 was measured on single calls, so it runs only while the lane is calls only.
        wide = {"dlane": {**self.D2["dlane"], "structures": ["long_single", "debit_vertical"]}}
        refused = dlane.screen_effective(wide, "direction", policy=pinned)
        self.assertEqual(refused["screen"], "S-C")
        self.assertIn("measured on single calls", refused["why"])
        self.assertEqual(dlane.screen_effective({"dlane": {**self.D2["dlane"], "structures": ["long_call"]}}, "direction",
                                                policy=pinned)["screen"], "D2", "long calls are calls")

    def test_the_committed_receipt_matches_its_benchmark_file(self):
        """CI's pin (decision 6; release D-1b): a D2 receipt sha in the committed policy.json must be the sha256 of
        docs/benchmarks/direction_screen_2.json (DSCREEN-2's receipt, copied byte for byte), and every figure the policy
        states beside it must be that receipt's (its `c`, and its lane figures at four decimals); with none pinned, the
        committed policy runs S-C. The receipt is public: aggregate figures, the rule and the shas only, so no per-cell
        result and no figure of a hidden or a later year (2020, 2021, 2025, 2026) beyond the window labels."""
        policy = json.loads((Path(ci.REPO) / "league" / "swarm" / "policy.json").read_text())
        pinned = dlane._policy_d2(policy)
        receipt = Path(ci.REPO) / "docs" / "benchmarks" / "direction_screen_2.json"
        if pinned["receipt_sha256"] is None:
            self.assertEqual(dlane.screen_effective({"dlane": {**policy["dlane"], "screen": "D2"}}, "direction",
                                                    policy=policy)["screen"], "S-C")
            return
        self.assertTrue(receipt.exists(), "a pinned receipt needs its file")
        self.assertEqual(dlane.receipt_sha256(receipt), pinned["receipt_sha256"])
        doc = json.loads(receipt.read_text())
        self.assertEqual(set(doc), {"c", "fp_zero_edge", "fp_zero_edge_per_lineage_lane", "power_lane", "rule", "sha256"})
        self.assertEqual(doc["c"], pinned["c"])
        lane = doc["fp_zero_edge"]["lane"]
        self.assertEqual(pinned["fp_lane_mixed"], round(lane["mixed_worlds"]["rate"], 4))
        self.assertEqual(pinned["fp_lane_2224"], round(lane["blocks_2022_24"]["rate"], 4))
        self.assertEqual(pinned["fp_lane_ci_mixed"], [round(x, 4) for x in lane["mixed_worlds"]["ci95_worlds"]])
        self.assertEqual(pinned["fp_lane_cluster_mixed"], [round(x, 4) for x in lane["mixed_worlds"]["ci95_cluster"]])
        self.assertEqual(pinned["power10"], round(doc["power_lane"]["plus10"]["mixed_worlds"]["rate"], 4))
        self.assertLessEqual(lane["mixed_worlds"]["rate"], 0.15, "the owner's ceiling: at most 15% per program")
        self.assertLessEqual(lane["blocks_2022_24"]["ci95_worlds"][1], 0.15)
        text = receipt.read_text()
        self.assertIsNone(re.search(r"20(?:20|21|25|26)", text), "no figure of a hidden or a later year")
        self.assertNotIn("cell", json.dumps(sorted(_keys(doc))).replace("all_eligible_cells", ""),
                         "aggregates only: no per-cell key")
        # The committed policy runs D2 on that receipt, calls only.
        live = dlane.screen_effective({"dlane": policy["dlane"]}, "direction", policy=policy)
        self.assertEqual((live["screen"], live["receipt"], live["c"]), ("D2", pinned["receipt_sha256"], 1.0))
        self.assertEqual((live["fp_lane_mixed"], live["fp_lane_2224"]), (0.1037, 0.1239))

    def test_d2_statistics_fail_closed(self):
        val = {"trades": 60, "days_traded": 40, "mean_return_on_max_loss_daily": 0.05, "t_daily": 1.0}
        hold = {"trades": 50, "days_traded": 30, "mean_return_on_max_loss_daily": 0.04, "t_daily": 0.8}
        self.assertTrue(dlane.d2_precheck(val)["passed"])
        self.assertFalse(dlane.d2_precheck({**val, "trades": 49})["passed"])
        self.assertFalse(dlane.d2_precheck({**val, "mean_return_on_max_loss_daily": 0.0})["passed"])
        t = dlane.d2_pooled_t(val, hold)
        xs_n = 70
        self.assertTrue(math.isfinite(t) and 0.8 < t < 1.8, t)
        self.assertIsNone(dlane.d2_pooled_t(val, {**hold, "t_daily": None}))
        self.assertIsNone(dlane.d2_pooled_t(val, None))
        self.assertEqual(xs_n, val["days_traded"] + hold["days_traded"])

    def test_the_sigma_writers_figure(self):
        """Decision 4: the sd of per-trade P&L per dollar of maximum loss in a Validation run (|mean| sqrt(n) / |t|),
        finite and above zero, else None (omitted)."""
        self.assertAlmostEqual(dlane.validation_r_sd({"mean_return_on_max_loss": 0.05, "t_stat": 0.5, "trades": 100}), 1.0)
        self.assertAlmostEqual(dlane.validation_r_sd({"mean_return_on_max_loss": -0.1, "t_stat": -1.0, "trades": 64}), 0.8)
        for bad in ({}, {"mean_return_on_max_loss": 0.0, "t_stat": 0.0, "trades": 50},
                    {"mean_return_on_max_loss": 0.05, "t_stat": None, "trades": 50},
                    {"mean_return_on_max_loss": 0.05, "t_stat": 0.5, "trades": 1}, None):
            self.assertIsNone(dlane.validation_r_sd(bad))

    def test_the_direction_lanes_leakage_alarm(self):
        self.assertFalse(dlane.leakage_alarm(9, 9, GATE))
        self.assertFalse(dlane.leakage_alarm(10, 6, GATE), "60% is not over 60%")
        self.assertTrue(dlane.leakage_alarm(10, 7, GATE))
        self.assertFalse(evidence.leakage_alarm(10, 3) or not evidence.leakage_alarm(10, 4), "alpha's: unchanged")


# ------------------------------------------------------------------------------------------------ 13. the agenda guard
class Agenda(unittest.TestCase):
    def test_length_ascii_and_hidden_years(self):
        self.assertEqual(dlane.AGENDA_MAX, architect.AGENDA_LOCKED_MAX)
        self.assertEqual(dlane.agenda_problems("x" * 4000), [])
        self.assertEqual(len(dlane.agenda_problems("x" * 4407)), 1, "the old agenda's length is refused")
        self.assertIn("4,407 characters", dlane.agenda_problems("x" * 4407)[0])
        self.assertIn("not ASCII", " ".join(dlane.agenda_problems("café")))
        self.assertIn("hidden year", " ".join(dlane.agenda_problems("Train is 2022-24; 2021 is hidden")))
        self.assertEqual(dlane.agenda_problems("No 2026 facts; Validation is the year after Train."), [])
        self.assertEqual(dlane.agenda_problems("  "), ["the agenda is empty"])


# ------------------------------------------------------------------------------------------------ what agents see
class Text(unittest.TestCase):
    def test_every_text_says_what_the_lane_is_and_names_no_hidden_validation_or_holdout_year(self):
        r = always_in()
        by, drift = year(-9000.0, -5.0)
        r["by_year"]["2021"], r["drift"]["years"]["2021"] = by, drift  # a hidden year the result carries
        with tempfile.TemporaryDirectory() as d:
            unit = unit_ctx(Path(d))
        score = dlane.train_score(r, first_year=2020, unit=unit, settings=GATE)
        robust = dlane.robust_verdict(score, run({"2022": (-1800.0, -4.2, {}), "2023": (2100.0, 1.4, {}),
                                                  "2024": (1900.0, 1.3, {})}), settings=GATE)
        brief = dlane.brief_text(GATE, ["SPY"])
        status = dlane.status_text(score, robust, version=7, mechanism="failed", settings=GATE)
        lanes = dlane.lanes_text(GATE)
        shown = dlane.view(score, robust, mechanism="passed")
        for text in (brief, status, lanes, json.dumps(shown)):
            self.assertIn(dlane.ALWAYS_IN_NOTE, text)
            self.assertIsNone(LEAK.search(text), LEAK.search(text) and text[max(0, LEAK.search(text).start() - 60):][:120])
        self.assertEqual(sorted(shown["years"]), ["2022", "2023", "2024"])
        self.assertIn("2022 IN t -3.90", status)
        self.assertIn("OVER the unit cap", status)
        self.assertIn(dlane.UNIT_HINT, status)
        self.assertEqual(shown["unit"], {"verdict": "fail", "hint": dlane.UNIT_HINT}, "E5's verdict alone, no figure")
        self.assertIn("gate vs the every-session twin: failed", status)
        self.assertEqual(shown["reported"]["mechanism"], "passed")
        self.assertEqual(shown["verdict"], "not eligible")
        self.assertIn("fails E5", shown["why"])
        self.assertNotIn("fp_", visible_text(brief, status, lanes, shown), "no private figure in agent text")
        self.assertNotIn("0.0141", visible_text(brief, status, lanes, shown))
        self.assertIn("no scored Train run yet", dlane.status_text(None, settings=GATE))
        self.assertIsNone(dlane.view({"score": 1.0}))

    def test_nothing_while_off(self):
        off = {"dlane": {"mode": "off"}}
        self.assertEqual((dlane.brief_text(off), dlane.lanes_text(off), dlane.status_text({}, settings=off)), ("", "", ""))

    def test_the_new_class_sentence(self):
        self.assertTrue(dlane.EQUITY_PREMIUM.startswith("the equity risk premium"))
        self.assertNotIn("equity_premium", cards.MECHANISM_CLASSES, "the cards builder adds it, for the direction lane")


# ------------------------------------------------------------------------------------------------ the walls
class Wall(unittest.TestCase):
    def test_dlane_py_is_protected_by_the_updater_and_the_gateway(self):
        self.assertIn("league/swarm/dlane.py", ci.FORBIDDEN)
        source = (Path(ci.REPO) / "gateway" / "lib" / "protected.mjs").read_text(encoding="utf-8")
        self.assertIn("'league/swarm/dlane.py'", source)
        self.assertTrue(ci.guard(["league/swarm/dlane.py"], None))
        self.assertTrue(ci.guard(["league/swarm/dlane.py"], "engineer/memory"))

    def test_standard_library_and_the_packages_own_modules_only(self):
        source = (Path(ci.REPO) / "league" / "swarm" / "dlane.py").read_text()
        imports = re.findall(r"^\s*(?:from|import) ([\w.]+)", source, re.M)
        allowed = {"__future__", "hashlib", "json", "math", "re", "time", "pathlib", "typing", ".", "..gym.results", ".store"}
        self.assertEqual(set(imports) - allowed, set())

    def test_the_done_rule_is_pinned_not_a_setting(self):
        self.assertEqual(dlane.DONE["rule_sha256"], "0d007696c9a6a1cbbd7d2cc345811359ab1cec389cf88f75ceff295bbbc48dca")
        self.assertEqual((dlane.DONE["min_closes"], dlane.DONE["min_programs"], dlane.DONE["min_closes_per_program"]), (30, 2, 5))
        self.assertEqual((dlane.DONE["gap_limit"], dlane.DONE["gap_min_matched"]), (0.10, 5))
        self.assertEqual((dlane.DONE["first_checkpoint"], dlane.DONE["checkpoint_every"]), (30, 10))
        self.assertNotIn("min_closes", dlane.cfg(GATE))


if __name__ == "__main__":
    unittest.main()
