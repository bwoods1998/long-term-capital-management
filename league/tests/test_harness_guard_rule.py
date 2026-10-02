"""The arms canary's guard rule (the lanestats study, Oct 1 2026): a secondary or guard check is judged on the cluster
bootstrap, not on its point estimate. It fails on a significant worsening beyond its tolerance (`GUARD_ALPHA`) or when
the canary cannot rule out a gross harm (`GUARD_BETA`): twice its tolerance, or for a zero-tolerance check a relative
`GUARD_GROSS`; a population guard, a group count and the window lanes keep the point estimate."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from league.swarm import harness_lanes as lanes

RESEARCH = lanes.LANES["research"]
DQ = RESEARCH.bottlenecks[0]
ZERO_TRADE = next(m for m in RESEARCH.guards if m.name == "zero_trade_ok_rate")
WASTED = DQ.secondary[0]


def families(n, prefix, *, dq, zero=(0,), wasted=None, runs=20, usd=1.0, cycles=20, errors=0):
    """`n` research families: a DQ count each (the primary), zero-trade OK runs cycling through `zero`."""
    return {f"{prefix}{k}": {"train_runs": runs, "dq_runs": dq, "ok_runs": runs - dq,
                             "ok_zero_trade_runs": zero[k % len(zero)], "research_usd": usd, "births": 1,
                             "wasted_gym_seconds": (dq * 100.0 if wasted is None else wasted[k % len(wasted)]),
                             "cycles": cycles, "cycle_errors": errors, "gym_cycles": cycles, "gym_cycles_unmatched": 0}
            for k in range(n)}


def check(result, name):
    return next(c for c in result["checks"] if c["metric"] == name)


class GuardRule(unittest.TestCase):
    def test_constants_are_pinned(self):
        self.assertEqual((lanes.GUARD_ALPHA, lanes.GUARD_BETA, lanes.GUARD_GROSS), (0.10, 0.20, 0.25))
        rules = lanes.RULE_SYMBOLS["league/swarm/harness_lanes.py"]
        for name in ("GUARD_ALPHA", "GUARD_GROSS", "tolerated", "AMOUNTS", "DOMINANT_SHARE"):
            self.assertIn(name, rules, "a change voids open canaries")

    def test_composition_noise_past_the_tolerance_is_no_breach(self):
        # 40 families a side, the canary's zero-trade share 11% above the control's on the point estimate (beyond the
        # 10% tolerance), spread across heterogeneous families: not significant, and twice the tolerance ruled out.
        out = lanes.retention(RESEARCH, DQ, families(40, "t", dq=1, zero=(4, 5, 6, 8, 10)),
                              families(40, "c", dq=4, zero=(3, 4, 5, 6, 7)), seed="s")
        row = check(out, "zero_trade_ok_rate")
        self.assertFalse(row["point_ok"], "the base rule's point estimate fails it")
        self.assertGreater(row["harm_p"], lanes.GUARD_ALPHA)
        self.assertLessEqual(row["beyond_twice"], lanes.GUARD_BETA)
        self.assertTrue(row["ok"])
        self.assertEqual(out["decision"], "retained", out)

    def test_a_significant_harm_beyond_the_tolerance_reverts(self):
        out = lanes.retention(RESEARCH, DQ, families(40, "t", dq=1, zero=(8, 9, 10)),
                              families(40, "c", dq=4, zero=(4, 5, 6)), seed="s")
        row = check(out, "zero_trade_ok_rate")
        self.assertLessEqual(row["harm_p"], lanes.GUARD_ALPHA)
        self.assertFalse(row["ok"])
        self.assertEqual(out["decision"], "revert_recommended")

    def test_a_canary_too_thin_to_rule_out_twice_the_tolerance_reverts(self):
        # Twelve canary families, five of them never trading: the worsening is not significant, but more than
        # GUARD_BETA of the replicates are beyond twice the tolerance. The primary passes; the change is not retained.
        out = lanes.retention(RESEARCH, DQ, families(12, "t", dq=1, zero=(0,) * 7 + (19,) * 5),
                              families(60, "c", dq=4, zero=(0, 2, 4, 6, 8, 10)), seed="s")
        row = check(out, "zero_trade_ok_rate")
        self.assertLessEqual(out["primary"]["p_value"], 0.05)
        self.assertGreater(row["harm_p"], lanes.GUARD_ALPHA, "a significance test alone would pass it")
        self.assertGreater(row["beyond_twice"], lanes.GUARD_BETA)
        self.assertFalse(row["ok"])
        self.assertEqual(out["decision"], "revert_recommended")

    def test_a_zero_tolerance_check_fails_on_a_significant_or_a_gross_worsening(self):
        control = families(40, "c", dq=4, wasted=(0, 100, 200, 300, 400))
        noisy = lanes.retention(RESEARCH, DQ, families(40, "t", dq=1, wasted=(0, 100, 200, 300, 450)), control,
                                seed="s")
        row = check(noisy, WASTED.name)
        self.assertFalse(row["point_ok"], "5% worse on the point estimate, against a tolerance of 0")
        self.assertGreater(row["harm_p"], lanes.GUARD_ALPHA)
        self.assertLessEqual(row["beyond_twice"], lanes.GUARD_BETA, "a worsening beyond GUARD_GROSS is ruled out")
        self.assertTrue(row["ok"])
        self.assertEqual(noisy["decision"], "retained", noisy)
        worse = lanes.retention(RESEARCH, DQ, families(40, "t", dq=1, wasted=(300, 400, 500, 600)), control, seed="s")
        self.assertFalse(check(worse, WASTED.name)["ok"])
        self.assertEqual(worse["decision"], "revert_recommended")
        # 50% worse on the point estimate, carried by one family in five: not significant, but the canary cannot rule
        # out a worsening beyond GUARD_GROSS (the #481 review, finding 2: with no band this was retained).
        gross = lanes.retention(RESEARCH, DQ, families(40, "t", dq=1, wasted=(0, 0, 0, 0, 1500)), control, seed="s")
        row = check(gross, WASTED.name)
        self.assertLessEqual(gross["primary"]["p_value"], 0.05)
        self.assertGreater(row["harm_p"], lanes.GUARD_ALPHA, "a significance test alone would pass it")
        self.assertGreater(row["beyond_twice"], lanes.GUARD_BETA)
        self.assertFalse(row["ok"])
        self.assertEqual(gross["decision"], "revert_recommended")

    def test_the_gross_band_is_twice_the_tolerance_or_guard_gross_without_one(self):
        t = families(30, "t", dq=1, zero=(0, 3, 6, 9), wasted=(0, 0, 0, 900))
        c = families(30, "c", dq=4, zero=(0, 2, 4, 6), wasted=(0, 100, 200, 300))
        rows = {}
        for g in (0.10, lanes.GUARD_GROSS, 5.0):
            with patch.object(lanes, "GUARD_GROSS", g):
                rows[g] = {m.name: lanes.compare(m, t, c, seed="s", guard=True) for m in (WASTED, ZERO_TRADE)}
        narrow, default, wide = (rows[g][WASTED.name] for g in (0.10, lanes.GUARD_GROSS, 5.0))
        self.assertEqual({row[ZERO_TRADE.name]["beyond_twice"] for row in rows.values()},
                         {rows[0.10][ZERO_TRADE.name]["beyond_twice"]},
                         "a check with a tolerance keeps twice it, whatever GUARD_GROSS is")
        self.assertEqual(narrow["harm_p"], default["harm_p"], "the band moves only the gross share")
        self.assertGreater(narrow["beyond_twice"], default["beyond_twice"])
        self.assertGreater(default["beyond_twice"], wide["beyond_twice"])
        self.assertEqual(default, lanes.compare(WASTED, t, c, seed="s", guard=True))

    def test_population_guards_and_window_lanes_keep_the_point_estimate(self):
        out = lanes.retention(RESEARCH, DQ, families(40, "t", dq=1), families(40, "c", dq=4), seed="s",
                              population=({"unattributed_usd": 30.0, "hours": 12.0}, {"unattributed_usd": 20.0, "hours": 24.0}))
        pop = check(out, "unattributed_usd_per_hour")
        self.assertNotIn("harm_p", pop)
        self.assertFalse(pop["ok"])
        self.assertEqual(out["decision"], "revert_recommended")
        data = lanes.LANES["data"]
        boxes = {f"b{k}": {"slots": 100, "slots_failed": 0, "ok_slots": 100, "gym_usd": 1.0 + k} for k in range(6)}
        before = {f"a{k}": {"slots": 100, "slots_failed": 5, "ok_slots": 95, "gym_usd": 1.0} for k in range(6)}
        window = lanes.retention(data, data.bottlenecks[0], boxes, before, seed="s")
        row = check(window, "gym_usd_per_ok_slot")
        self.assertNotIn("harm_p", row, "a window lane is a before/after comparison: no arms bootstrap for its checks")
        self.assertEqual(row["ok"], row["point_ok"])

    def test_a_unit_that_held_most_of_a_checks_events_in_the_capture_sits_out_both_arms(self):
        units = {f"f{k}": {"cycles": 50, "cycle_errors": 1 if k < 10 else 0} for k in range(40)}
        units["broken"] = {"cycles": 56, "cycle_errors": 53}
        units["swarm"] = {"cycles": 900, "cycle_errors": 400}   # a pseudo-unit is never a unit
        capture = {"examples": [{"families": ["shown"]}], "units": units}
        self.assertEqual(lanes.motivating_units("research", capture), ["broken", "shown"])
        few = {"units": {"a": {"cycles": 10, "cycle_errors": 6}, "b": {"cycles": 10, "cycle_errors": 0}}}
        self.assertEqual(lanes.motivating_units("research", few), [], "fewer than DOMINANT_EVENTS: no outlier")
        boxes = {"units": {"b0": {"gym_usd": 90.0, "ok_slots": 10}, "b1": {"gym_usd": 10.0, "ok_slots": 10}}}
        self.assertEqual(lanes.motivating_units("data", boxes), [], "a window lane compares before and after: no arms")
        treated, control = lanes.split_arms({"broken": {"cycles": 5}, "f1": {"cycles": 5}}, key="k", salt="s",
                                            fraction=0.5, exclude=lanes.motivating_units("research", capture))
        self.assertNotIn("broken", {**treated, **control})

    def test_an_amount_names_no_outlier(self):
        # The family that wasted most of the capture's Gym seconds is the primary's most informative unit, and twenty
        # seconds are not twenty events: only a check whose numerator counts events names an outlier (#481, finding 6).
        units = {f"f{k}": {"cycles": 50, "cycle_errors": 1 if k < 10 else 0, "births": 1, "dq_runs": 2,
                           "wasted_gym_seconds": 100.0} for k in range(40)}
        units["slow"] = {"cycles": 50, "cycle_errors": 0, "births": 1, "dq_runs": 40, "wasted_gym_seconds": 9000.0}
        units["broken"] = {"cycles": 56, "cycle_errors": 53}
        self.assertEqual(lanes.motivating_units("research", {"units": units}), ["broken"])
        self.assertIn(WASTED.numerator, lanes.AMOUNTS)
        # Every amount a lane metric names is listed: a field in seconds, dollars or hours that is missing would be
        # counted as events.
        fields = {f for lane in lanes.LANES.values()
                  for m in [x for b in lane.bottlenecks for x in (b.metric, *b.secondary)] + list(lane.guards)
                  + list(lane.population_guards) for f in (m.numerator, m.denominator)}
        amounts = {f for f in fields if f.endswith(("_seconds", "_usd")) or f == "hours"}
        self.assertTrue(amounts)
        self.assertLessEqual(amounts, set(lanes.AMOUNTS))

    def test_cycle_errors_have_an_absolute_floor(self):
        cycle_errors = next(m for m in RESEARCH.guards if m.name == "cycle_error_rate")
        self.assertEqual((cycle_errors.min_effect, cycle_errors.abs_tolerance), (0.20, 0.005))
        self.assertTrue(lanes.tolerated(cycle_errors, 0.009, 0.005), "under half a point more")
        self.assertFalse(lanes.tolerated(cycle_errors, 0.011, 0.005))

    def test_the_birth_balance_survives_a_large_window(self):
        # math.comb(1100, 550) is no float: the old terms raised OverflowError from 1,030 births.
        self.assertAlmostEqual(lanes.binomial_low(3, 10, 0.5), 176 / 1024, places=12)
        self.assertEqual((lanes.binomial_low(4, 4, 1.0), lanes.binomial_low(3, 4, 1.0), lanes.binomial_low(0, 9, 0.0)),
                         (1.0, 0.0, 1.0))
        self.assertEqual([lanes.binomial_low(-1, n, p) for n, p in ((9, 0.0), (9, 0.3), (9, 1.0), (0, 0.5))], [0.0] * 4,
                         "P(X <= -1) is 0 at every p, the p = 0 edge included")
        self.assertAlmostEqual(lanes.binomial_low(550, 1100, 0.5), 0.5 + 0.5 * lanes.binomial_low(550, 1100, 0.5)
                               - 0.5 * lanes.binomial_low(549, 1100, 0.5), places=9)
        self.assertLess(lanes.binomial_low(450, 1100, 0.5), 1e-9)
        memory = lanes.LANES["memory"]
        units = {f"u{k}": {"births": 1, "rebirths": 0, "units": 1, "validation_runs": 1, "research_usd": 0.05}
                 for k in range(1060)}
        treated = {u: r for k, (u, r) in enumerate(units.items()) if k % 2}
        control = {u: r for k, (u, r) in enumerate(units.items()) if not k % 2}
        out = lanes.retention(memory, memory.bottleneck("validation_attempts_per_usd"), treated, control, seed="s",
                              fraction=0.5)
        self.assertTrue(next(c for c in out["checks"] if c["metric"] == "birth_balance")["ok"])

    def test_the_research_canary_has_the_activity_to_decide(self):
        canary = RESEARCH.canary_for(DQ)
        self.assertEqual((canary["fraction"], canary["observe_seconds"]), (0.5, 12 * 3600))

    def test_the_guard_bootstrap_leaves_the_primary_and_the_tolerance_unchanged(self):
        t, c = families(20, "t", dq=1), families(20, "c", dq=4)
        plain = lanes.compare(DQ.metric, t, c, seed="s")
        guarded = lanes.compare(DQ.metric, t, c, seed="s", guard=True)
        self.assertEqual(plain["p_value"], guarded["p_value"], "the same replicates, the same p")
        self.assertNotIn("harm_p", plain)
        # `tolerated` is the base rule's tolerance: relative, or absolute when set; a zero control passes only on the
        # absolute tolerance; unmeasured passes; `times` scales both.
        cycle_errors = lanes.Metric("cycle_error_rate", "cycle_errors", "cycles", min_effect=0.20)  # no floor
        self.assertFalse(lanes.tolerated(cycle_errors, 0.01, 0.0))
        self.assertTrue(lanes.tolerated(cycle_errors, 0.0, 0.0))
        self.assertTrue(lanes.tolerated(cycle_errors, None, 0.02))
        self.assertTrue(lanes.tolerated(cycle_errors, 0.023, 0.02))
        self.assertFalse(lanes.tolerated(cycle_errors, 0.025, 0.02))
        self.assertTrue(lanes.tolerated(cycle_errors, 0.025, 0.02, 2.0))
        self.assertTrue(lanes.tolerated(ZERO_TRADE, 0.015, 0.0))
        self.assertFalse(lanes.tolerated(ZERO_TRADE, 0.025, 0.0))
        self.assertTrue(lanes.tolerated(ZERO_TRADE, 0.035, 0.0, 2.0))
        self.assertTrue(lanes.tolerated(ZERO_TRADE, 0.325, 0.30), "within 10% relative")
        self.assertFalse(lanes.tolerated(ZERO_TRADE, 0.34, 0.30))
        ok_per_usd = next(m for m in RESEARCH.guards if m.name == "ok_runs_per_usd")
        self.assertTrue(lanes.tolerated(ok_per_usd, 90.0, 100.0))
        self.assertFalse(lanes.tolerated(ok_per_usd, 89.0, 100.0))
        self.assertTrue(lanes.tolerated(ok_per_usd, 81.0, 100.0, 2.0))


class FrozenSymbolsExist(unittest.TestCase):
    """Every frozen qualname resolves in its file: a typo would silently unfreeze it (the #481 review, follow-up 2)."""

    def test_every_frozen_symbol_resolves(self):
        import ast
        root = Path(__file__).resolve().parents[2]
        missing = []
        for rel, names in lanes.FROZEN_SYMBOLS.items():
            tree = ast.parse((root / rel).read_text())
            top, methods = set(), set()
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    top.add(node.name)
                    if isinstance(node, ast.ClassDef):
                        methods.update(f"{node.name}.{m.name}" for m in node.body
                                       if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)))
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                        for leaf in ast.walk(target):
                            if isinstance(leaf, ast.Name):
                                top.add(leaf.id)
            missing += [f"{rel}:{n}" for n in names if n not in (methods if "." in n else top)]
        self.assertEqual(missing, [])

    def test_the_retire_guard_closure_is_frozen(self):
        frozen = set(lanes.FROZEN_SYMBOLS["league/swarm/researcher.py"])
        for name in ("Researcher.guarded", "retire_guard", "RETIRE_GUARD_DAYS", "validation_refuted", "record_verdict"):
            self.assertIn(name, frozen)


if __name__ == "__main__":
    unittest.main()
