"""The arms canary's inputs (the lanestats study, Oct 1 2026; PR #481): the research canary holds half the families for
twelve hours, `cycle_error_rate` has an absolute floor, a unit that held most of a check's events in the capture sits out
both arms (`DOMINANT_SHARE`, event counts only: `AMOUNTS`), the birth balance survives a large window, and every frozen
symbol resolves. Checks are judged on the point estimate, as before: a bootstrap guard rule was tried and dropped
because it did not beat it on the same simulated windows."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from league.swarm import harness_lanes as lanes

RESEARCH = lanes.LANES["research"]
DQ = RESEARCH.bottlenecks[0]
WASTED = DQ.secondary[0]


def families(n, prefix, *, dq, runs=20, usd=1.0, cycles=20, errors=0):
    """`n` research families: a DQ count each (the primary) and a cycle-error count each."""
    return {f"{prefix}{k}": {"train_runs": runs, "dq_runs": dq, "ok_runs": runs - dq, "ok_zero_trade_runs": 0,
                             "research_usd": usd, "births": 1, "wasted_gym_seconds": dq * 100.0, "cycles": cycles,
                             "cycle_errors": errors, "gym_cycles": cycles, "gym_cycles_unmatched": 0}
            for k in range(n)}


def check(result, name):
    return next(c for c in result["checks"] if c["metric"] == name)


class CanaryRules(unittest.TestCase):
    def test_the_rule_symbols_are_pinned(self):
        self.assertEqual((lanes.DOMINANT_SHARE, lanes.DOMINANT_EVENTS), (0.25, 20))
        rules = lanes.RULE_SYMBOLS["league/swarm/harness_lanes.py"]
        for name in ("DOMINANT_SHARE", "AMOUNTS", "motivating_units", "compare", "binomial_low", "retention"):
            self.assertIn(name, rules, "a change voids open canaries")
        self.assertRegex(lanes.rules_sha(), r"^[0-9a-f]{64}$")
        unknown = {**lanes.RULE_SYMBOLS, "league/swarm/harness_lanes.py": rules + ("NO_SUCH_RULE",)}
        with patch.dict(lanes._RULES, clear=True), patch.object(lanes, "RULE_SYMBOLS", unknown):
            with self.assertRaisesRegex(ValueError, "NO_SUCH_RULE is not defined"):
                lanes.rules_sha()

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
        control = families(40, "c", dq=4, cycles=1000, errors=5)   # 0.5% of cycles
        # 0.9%: 80% worse relative, under half a point absolute. Without the floor this failed the 20% tolerance.
        within = lanes.retention(RESEARCH, DQ, families(40, "t", dq=1, cycles=1000, errors=9), control, seed="s")
        self.assertTrue(check(within, "cycle_error_rate")["ok"])
        self.assertEqual(within["decision"], "retained", within)
        beyond = lanes.retention(RESEARCH, DQ, families(40, "t", dq=1, cycles=1000, errors=11), control, seed="s")
        self.assertFalse(check(beyond, "cycle_error_rate")["ok"])
        self.assertEqual(beyond["decision"], "revert_recommended")

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
