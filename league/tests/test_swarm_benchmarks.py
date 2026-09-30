"""Known-outcome statistical experiments use real arithmetic and independent confirmation streams."""
import unittest

from league.swarm import benchmarks as B
from league.swarm import evidence


class SyntheticGateExperiments(unittest.TestCase):
    def test_independent_cohorts_and_stress_reuse_only_the_gross_path(self):
        normal = B.generated("planted_edge", "development", 0, [2025])
        again = B.generated("planted_edge", "development", 0, [2025])
        other = B.generated("planted_edge", "confirmation", 0, [2025])
        stressed = B.generated("planted_edge", "development", 0, [2025], stress=1.5)
        self.assertEqual(normal, again)
        self.assertNotEqual(normal["daily"], other["daily"])
        for a, b in zip(normal["daily"], stressed["daily"]):
            self.assertAlmostEqual(a[1] - b[1], 0.45)

    def test_splitting_identical_daily_exposure_does_not_create_evidence(self):
        one = B.generated("absent_signal", "confirmation", 1, [2025])
        many = B.generated("absent_signal", "confirmation", 1, [2025], copies=20)
        self.assertEqual(one["summary"]["t_daily"], many["summary"]["t_daily"])
        self.assertEqual(one["summary"]["days_traded"], many["summary"]["days_traded"])
        self.assertEqual(evidence.traded_sharpe(one["summary"]), evidence.traded_sharpe(many["summary"]))

    def test_strong_known_edge_survives_and_disappearing_edge_fails_fresh_holdout(self):
        positive = B.trial("planted_edge", "confirmation", 0, [])
        negative = B.trial("edge_disappears", "confirmation", 0, [])
        self.assertTrue(positive["pipeline_passed"], positive)
        self.assertTrue(negative["holdout_tested"], negative)
        self.assertFalse(negative["pipeline_passed"], negative)

    def test_sparse_positive_is_reported_as_frequency_diagnostic(self):
        out = B.trial("positive_sparse", "confirmation", 0, [])
        self.assertFalse(out["train_eligible"])
        self.assertIn("trades", out["train_why"])
        self.assertIn("trades", out["validation_failed_checks"])
        self.assertFalse(out["pipeline_passed"])


if __name__ == "__main__":
    unittest.main()
