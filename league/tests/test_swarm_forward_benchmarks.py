"""THE FORWARD LADDER'S BENCHMARK (`league/swarm/forward_benchmarks.py`): its worlds are the plan's, its rows are the
practice ledger's shape, the drift control does what it claims on them, the sealed look's bootstrap port agrees with the
original, and the binding rule is the pre-registered one. Small desks only (the full run is an operator's)."""

from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

try:
    import numpy  # noqa: F401

    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

from league.live import ladder as L
from league.swarm import forward_benchmarks as FB


class TheDefinition(unittest.TestCase):
    def test_the_plans_worlds_are_there_with_their_kinds(self):
        kinds = {name: spec["kind"] for name, spec in FB.WORLDS.items()}
        for name in ("absent", "cost_erased", "drift_only", "fading"):
            self.assertEqual(kinds[name], "negative", name)
        for name in ("planted_dense", "planted_sparse"):
            self.assertEqual(kinds[name], "positive", name)
        self.assertEqual(FB.WORLDS["cost_erased"]["edge_forward"] < 0 < FB.WORLDS["cost_erased"]["edge"], True)
        self.assertEqual(FB.WORLDS["fading"]["edge_forward"] < 0 < FB.WORLDS["fading"]["edge"], True)
        self.assertGreater(FB.WORLDS["drift_only"]["delta"], 0)
        self.assertEqual(FB.suite_sha(), FB.suite_sha())

    def test_the_binding_rule_needs_both_pools_at_or_under_the_sealed_look(self):
        def rows(world, kind, ladder, sealed, bare=None, n=10):
            return [{"world": world, "kind": kind, "ladder": i < ladder, "sealed": i < sealed,
                     "sealed_bare": i < (sealed if bare is None else bare), "validation_passed": False,
                     "drift_hold": False, "variants": {v: False for v in FB.VARIANTS}, "last": {}} for i in range(n)]

        def desks(*parts):
            return [{"world": p[0], "rows": rows(*p)} for p in parts]

        self.assertTrue(FB.aggregate(desks(("absent", "negative", 1, 1), ("fading", "negative", 0, 5)))["binding"])
        out = FB.aggregate(desks(("absent", "negative", 3, 0), ("fading", "negative", 0, 5)))
        self.assertEqual(out["conditions"], {"pooled": True, "mixed": True, "every_world": False})
        self.assertFalse(out["binding"], "a pooled count that hides a world where the ladder is worse does not bind")
        self.assertEqual(out["worlds_where_ladder_exceeds_sealed"], ["absent"])
        self.assertFalse(FB.aggregate(desks(("absent", "negative", 6, 0), ("fading", "negative", 0, 5)))["binding"])
        self.assertFalse(FB.aggregate(desks(("absent", "negative", 0, 1), ("mixed", "negative", 2, 1)))["binding"],
                         "the mixed desks' negatives too")
        self.assertFalse(FB.aggregate(desks(("absent", "negative", 2, 3, 1)))["binding"], "and the bare sealed look's")
        self.assertFalse(FB.aggregate(desks(("planted_dense", "positive", 0, 0)))["binding"], "no negative: not met")
        missed = FB.aggregate(desks(("planted_dense", "positive", 7, 9)))["worlds"]["planted_dense"]["missed_signals"]
        self.assertEqual((missed["ladder"]["count"], missed["sealed"]["count"]), (3, 1))

    def test_rates_carry_exact_bounds(self):
        r = FB.rate(0, 1000)
        self.assertEqual((r["count"], r["rate"], r["lower_95"]), (0, 0.0, 0.0))
        self.assertAlmostEqual(r["upper_95"], 0.00368, places=4)
        r = FB.rate(5, 100)
        self.assertLess(r["lower_95"], 0.05)
        self.assertGreater(r["upper_95"], 0.05)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheRows(unittest.TestCase):
    def forward(self, world, n=40):
        days = FB.nyse_sessions("2026-10-05", n)
        drift = float(FB.WORLDS[world].get("drift", FB.PROTOCOL["market_drift"]))
        path = FB.market(days, drift=drift, replication=0, period="forward", world=world)
        return days, FB.trades(world, 0, 0, "forward", days, path)

    def test_the_rows_are_the_practice_ledgers_and_judge_the_same_through_the_store(self):
        from league.live.observe import ObserveStore

        days, closes = self.forward("planted_dense")
        rows = FB.ledger_rows(closes, start=1)       # the store numbers its rows from 1: the same keys, the same seed
        cohort = {"family": "f", "version": 1, "first_day": days[0], "snapshot": {"run_sha": "s", "practice_evaluator": "e"}}
        rules = L.Rules.from_constitution()
        direct = L.judge(cohort, {"first_day": days[0], "sessions": len(days)}, rows, through=days[-1], rules=rules)
        with tempfile.TemporaryDirectory() as tmp:
            store = ObserveStore(tmp, clock=lambda: 1.0)
            store.evaluator = "e"
            engine = [dict(r["body"], id=r["seq"], day=r["exit_day"], evaluator="e") for r in rows]
            self.assertTrue(store.add("f@1:o", "f", 1, engine, account="a"))
            store._connect().execute("INSERT INTO practice(family, version, tier, capital, first_at, first_day, last_at, "
                                     "last_day, sessions) VALUES('f', 1, 'train', 10000, 1, ?, 2, ?, ?)",
                                     (days[0], days[-1], len(days)))
            practice, stored = store.ladder_rows("f", 1, evaluator="e", first_day=days[0], through=days[-1])
            through = L.judge(cohort, practice, stored, through=days[-1], rules=rules)
            store.close()
        for key in ("closes", "mean", "lcb", "p", "windows", "drift", "lines"):
            self.assertEqual(json.dumps(direct[key], sort_keys=True), json.dumps(through[key], sort_keys=True), key)

    def test_the_drift_control_stops_drift_keeps_premium_and_costs_the_timing_edge(self):
        for world, passed in (("drift_only", False), ("planted_dense", True), ("planted_premium", True),
                              ("planted_directional", False)):
            _, closes = self.forward(world, 60)
            line = L.drift_line([L.close_of(r) for r in FB.ledger_rows(closes)], 0.9)
            self.assertEqual(line["passed"], passed, world)
            self.assertEqual(line["share"], 1.0, "every figure is known in the ledger's rows")
        _, closes = self.forward("drift_only", 60)
        self.assertGreater(sum(c["pnl"] for c in closes), 0, "drift alone looks like an edge before the control")

    def test_the_numpy_bootstrap_agrees_with_the_original(self):
        out = FB.bootstrap_agreement()
        self.assertLess(out["max_p_gap"], 0.03)
        for case in out["cases"]:
            self.assertLess(abs(case["lcb_original"] - case["lcb_numpy"]), 0.06)

    def test_the_drift_hold_holds_the_drift_world_only(self):
        days = FB.weekdays(__import__("datetime").date(2025, 1, 2), 252)
        held = {}
        for world in ("drift_only", "absent", "planted_dense"):
            drift = float(FB.WORLDS[world].get("drift", FB.PROTOCOL["market_drift"]))
            path = FB.market(days, drift=drift, replication=1, period="validation", world=world)
            closes = FB.trades(world, 0, 1, "validation", days, path)
            held[world] = FB.drift_hold(FB.gym_result(closes, days), path, closes)
        self.assertEqual(held, {"drift_only": True, "absent": False, "planted_dense": False})


@unittest.skipUnless(HAVE, "numpy not installed")
class TheDesk(unittest.TestCase):
    def test_a_small_desk_runs_both_designs_on_the_same_entrants(self):
        out = FB.desk("absent", 0, slots=3, sessions=45)
        self.assertEqual(out["entrants"], len(out["rows"]))
        self.assertGreaterEqual(out["entrants"], 3)
        for row in out["rows"]:
            self.assertEqual(row["kind"], "negative")
            self.assertIn(row["ladder_outcome"], ("promoted", "validation_failed", "prefilter_negative", "window",
                                                  "running"))
            self.assertEqual(set(row["variants"]), set(FB.VARIANTS))
        again = FB.desk("absent", 0, slots=3, sessions=45)
        self.assertEqual(json.dumps(out, sort_keys=True), json.dumps(again, sort_keys=True), "deterministic")

    def test_a_strong_planted_edge_can_climb_the_ladder(self):
        out = FB.desk("planted_dense", 0, slots=4, sessions=70)
        self.assertTrue(any(r["ladder"] for r in out["rows"]), [r["ladder_outcome"] for r in out["rows"]])
        promoted = [r for r in out["rows"] if r["ladder"]]
        self.assertTrue(all(r["holdout_nonnegative"] for r in promoted), "never past a negative pre-filter")
        self.assertTrue(all(r["validation_passed"] for r in promoted), "never past a Validation line it did not meet")

    def test_the_ladder_arm_reads_the_validation_line_before_the_prefilter(self):
        """Suite 2 (the WP6 review): an entrant that meets L1-L5 without having met the Validation line fails there; the
        `no_validation` variant is the ladder without that rung."""
        out = FB.desk("skewed_null", 2, slots=8, sessions=60)  # a desk where nulls meet L1-L5 (found, then pinned)
        failed = [r for r in out["rows"] if r["ladder_outcome"] == "validation_failed"]
        self.assertTrue(failed, [r["ladder_outcome"] for r in out["rows"]])
        self.assertTrue(all(not r["validation_passed"] and not r["ladder"] for r in failed))
        self.assertTrue(all(r["validation_passed"] for r in out["rows"] if r["ladder"]))
        self.assertTrue(any(r["variants"]["no_validation"] for r in failed), "without the rung some would have gone on")
        self.assertEqual(FB.SEED_ID, "forward-suite-1", "the worlds' streams are suite 1's")


    def test_a_mixed_desk_draws_several_worlds_and_the_report_renders(self):
        part = FB.run([FB.MIXED, "drift_only"], 1, slots=3, sessions=64)
        self.assertGreater(len({r["world"] for d in part["desks"] if d["world"] == FB.MIXED for r in d["rows"]}), 1)
        report = FB.combine([part])
        text = FB.markdown(report)
        self.assertIn("Binding rule", text)
        self.assertIn("drift_only", text)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "part.json"
            path.write_text(json.dumps(part, default=str))
            self.assertEqual(FB.main(["--combine", str(path), "--report", str(Path(tmp) / "r.md")]), 0)
            self.assertTrue((Path(tmp) / "r.md").read_text().startswith("# Forward ladder benchmark"))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheDemotionRule(unittest.TestCase):
    """THE DEMOTION RULE's measurement (the WP6 review): the ladder's demotion through the money table's own functions,
    and the other readings of its words, on a promoted program's forward stream."""

    def test_the_readings_are_ordered_as_their_definitions_say(self):
        for world in ("absent", "planted_dense"):
            out = FB.demotions(world, programs=12, horizon=40)
            self.assertEqual((out["world"], out["programs"], out["horizon"]), (world, 12, 40))
            r = {name: {m: by[m]["count"] for m in by} for name, by in out["readings"].items()}
            self.assertEqual(set(r["as_built"]), {"20", "40"})
            for m in ("20", "40"):
                self.assertGreaterEqual(r["bound_95"][m], r["as_built"][m], "a higher confidence's bound is lower")
                self.assertLessEqual(r["blocks_of_20"][m], r["as_built"][m], "a block reads the bound less often")
                self.assertLessEqual(r["negative_only"][m], r["as_built"][m])
                self.assertLessEqual(r["as_built"]["20"], r["as_built"]["40"])
        self.assertEqual(json.dumps(FB.demotions("absent", programs=3, horizon=25), sort_keys=True),
                         json.dumps(FB.demotions("absent", programs=3, horizon=25), sort_keys=True), "deterministic")

    def test_its_part_combines_into_the_report(self):
        part = FB.run(["absent"], 1, slots=2, sessions=30)
        demotion = FB.run_demotions(["absent", FB.MIXED], programs=2, horizon=25)
        self.assertEqual([w["world"] for w in demotion["demotion"]], ["absent"], "a world's own programs, never mixed")
        report = FB.combine([part, demotion])
        self.assertEqual([w["world"] for w in report["demotion"]], ["absent"])
        self.assertIn("The demotion rule", FB.markdown(report))
        with self.assertRaises(ValueError):
            FB.combine([part, dict(demotion, suite_sha="another")])


if __name__ == "__main__":
    unittest.main()
