"""Synthetic policy mechanics, actual gate arithmetic, and frozen confirmation protocol; no market data."""

import unittest
from unittest.mock import patch

from league.swarm import evidence
from league.swarm import long_single_benchmarks as B


class Generator(unittest.TestCase):
    def test_oracle_payoffs_separate_incremental_signal_drift_and_erased_edge(self):
        mu = B.PROTOCOL["market_drift"]
        costs = B.PROTOCOL["round_trip_spread_usd"] + B.PROTOCOL["round_trip_fees_usd"]
        self.assertGreater(B.fair_payoff(mu) - B.fair_payoff(0) - costs, 0)
        for case in ("sparse_planted_edge", "incremental_after_drift", "cost_erased_signal"):
            signal = B.PROTOCOL["cases"][case]["signal"]
            added = 0.5 * (B.fair_payoff(signal + mu) + B.fair_payoff(signal - mu) -
                           B.fair_payoff(mu) - B.fair_payoff(-mu)) - costs
            self.assertEqual(added > 0, B.PROTOCOL["cases"][case]["positive"])

    def test_one_lot_cash_and_maximum_loss_are_consistent(self):
        for case in B.PROTOCOL["cases"]:
            value = B.generated(case, "development", 0, "train")
            self.assertEqual(sum(t["pnl"] for t in value["trades"]), sum(r[1] for r in value["daily"]))
            self.assertAlmostEqual(value["cash"]["end"], B.PROTOCOL["capital_usd"] + sum(r[1] for r in value["daily"]))
            self.assertTrue(all(t["qty"] == 1 and t["pnl"] >= -t["max_loss"] for t in value["trades"]))
            self.assertTrue(all(t["terminal_value"] >= 0 and t["entry_premium"] <= B.PROTOCOL["premium_cap_usd"] for t in value["trades"]))
            self.assertTrue(all(row[2] >= 0 for row in value["daily"]))
            self.assertEqual(set(value["by_year"]), {str(y) for y in B.PROTOCOL["train_years"]})
            self.assertEqual(set(value["drift"]["years"]), set(value["by_year"]))

    def test_stress_changes_cost_only_and_independent_domains_change_paths(self):
        value = B.generated("incremental_after_drift", "development", 2, "validation")
        again = B.generated("incremental_after_drift", "development", 2, "validation")
        stress = B.generated("incremental_after_drift", "development", 2, "validation", stress=1.5)
        diagnostic = B.generated("incremental_after_drift", "development", 2, "diagnostic")
        self.assertEqual(value, again)
        self.assertEqual(value["market_sha"], stress["market_sha"])
        self.assertNotEqual(value["path_sha"], diagnostic["path_sha"])
        for normal, wider in zip(value["trades"], stress["trades"]):
            self.assertEqual(normal["day"], wider["day"])
            self.assertAlmostEqual(normal["pnl"] - wider["pnl"], 0.5 * B.PROTOCOL["round_trip_spread_usd"])
        self.assertNotEqual(B.rng("development", 2).random(), B.rng("confirmation", 2).random())

    def test_adaptive_versions_share_the_market_but_differ_in_ex_ante_policy(self):
        baseline = B.generated("unselected_noise", "development", 0, "train")
        first = B.generated("adaptive_noise", "development", 0, "train")
        second = B.generated("adaptive_noise", "development", 0, "train", 1)
        self.assertEqual(baseline["path_sha"], first["path_sha"])
        self.assertEqual(first["market_sha"], second["market_sha"])
        self.assertNotEqual(first["path_sha"], second["path_sha"])

    def test_sparse_signal_and_validation_gap_are_explicit_frequency_failures(self):
        sparse = B.generated("sparse_planted_edge", "development", 0, "train")
        gap = B.generated("train_validation_frequency_gap", "development", 0, "train")
        self.assertFalse(evidence.train_score(sparse, first_year=2020)["eligible"])
        self.assertEqual({r["trades"] for r in sparse["by_year"].values()}, {12})
        self.assertTrue(evidence.train_score(gap, first_year=2020)["eligible"])
        validation = B.generated("train_validation_frequency_gap", "development", 0, "validation")
        stressed = B.generated("train_validation_frequency_gap", "development", 0, "validation", stress=1.5)
        line = evidence.validation_line(validation, stressed, validated_versions=1, version_sharpes=[])
        self.assertFalse(line["checks"]["trades"])
        self.assertTrue(line["checks"]["days"])

    def test_drift_fit_charges_directional_exposure_and_retains_planted_signal(self):
        directional = B.generated("drift_only_directional", "development", 0, "train")
        edge = B.generated("incremental_after_drift", "development", 0, "train")
        for value in (directional, edge):
            pooled = value["drift"]["pooled"]
            self.assertAlmostEqual(pooled["pnl"], pooled["alpha_usd"] + pooled["drift_usd"], places=1)
        self.assertGreater(directional["drift"]["pooled"]["drift_usd"], 0)
        self.assertFalse(evidence.drift_screen(evidence.drift_numbers(directional["drift"]), first_year=2020)["passed"])
        self.assertTrue(evidence.drift_screen(evidence.drift_numbers(edge["drift"]), first_year=2020)["passed"])


class Protocol(unittest.TestCase):
    def test_planted_signal_reaches_actual_holdout_with_prior_looks_preserved(self):
        row = B.trial("incremental_after_drift", "development", 0)
        self.assertTrue(row["statistical_pipeline_passed"])
        self.assertEqual(row["accounting"]["lineage_trials"], 8)  # Train + two robustness + two validation + look + two probes
        self.assertEqual(row["accounting"]["lineage_looks"], 1)
        self.assertEqual(row["accounting"]["global_looks"], 3)
        holdout = row["attempts"][0]["holdout"]
        self.assertEqual(holdout["numbers"]["looks_before"], 2)
        self.assertAlmostEqual(holdout["numbers"]["holm_threshold"], evidence.HOLDOUT_ALPHA / 3)

    def test_real_store_counts_every_noise_version_and_never_resets_lineage(self):
        row = B.trial("adaptive_noise", "development", 0)
        accounting = row["accounting"]
        normal = B.PROTOCOL["adaptive_variants"]
        stress_mid = 2 * len(row["attempts"])
        validation = 2 * sum(a["validation"] is not None for a in row["attempts"])
        holdout = sum(a["holdout"] is not None for a in row["attempts"])
        self.assertEqual(accounting["lineage_trials"], normal + stress_mid + validation + holdout)
        self.assertEqual(accounting["trial_rows"], accounting["lineage_trials"])
        self.assertEqual(accounting["global_looks"], B.PROTOCOL["prior_global_failed_looks"] + holdout)
        self.assertLessEqual(holdout, evidence.LOOKS_PER_LINEAGE)
        seen = 0
        for attempt in row["attempts"]:
            if attempt["validation"]:
                seen += 1
                self.assertEqual(attempt["validation"]["numbers"]["validated_versions"], seen)
        self.assertEqual(accounting["validated_versions"], seen)

    def test_blocked_sparse_policy_never_opens_holdout_and_probe_cannot_qualify_it(self):
        row = B.trial("sparse_planted_edge", "development", 0)
        self.assertEqual(row["attempts"], [])
        self.assertFalse(row["statistical_pipeline_passed"])
        self.assertEqual(row["accounting"]["lineage_looks"], 0)
        self.assertEqual(row["accounting"]["lineage_trials"], 3)
        self.assertEqual(row["accounting"]["validated_versions"], 0)
        self.assertTrue(row["diagnostic_validation"]["not_used_for_selection"])

    def test_confirmation_refuses_changed_or_incomplete_preregistration_before_generating(self):
        frozen = {"cohort": "development", "replications": 1, **B.fingerprints(),
                  "cases": {name: {"replications": [{}]} for name in B.PROTOCOL["cases"]}}
        with patch.object(B, "trial", side_effect=AssertionError("must reject before generating confirmation")):
            for bad in (None, {**frozen, "generator_sha": "changed"}, {**frozen, "protocol_sha": "changed"},
                        {**frozen, "evaluator_sha": "changed"}, {**frozen, "cases": {}}, {**frozen, "replications": 2}):
                with self.assertRaises(ValueError):
                    B.benchmark("confirmation", 1, frozen=bad)


if __name__ == "__main__":
    unittest.main()
