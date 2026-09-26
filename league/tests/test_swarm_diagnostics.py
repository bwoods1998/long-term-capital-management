"""Researchers see the daily statistic the evidence line actually evaluates."""
import unittest

from league.swarm import diagnostics


class CompactTrainingFeedback(unittest.TestCase):
    def test_correlated_intraday_success_does_not_hide_weak_daily_evidence(self):
        result = {
            "status": "ok", "window": "train",
            "summary": {
                "trades": 800, "days_traded": 60,
                "mean_return_on_max_loss": .03, "t_stat": 9,
                "mean_return_on_max_loss_daily": -.005, "t_daily": -.6, "sharpe_daily": -.04,
            },
            "fills": {"orders": 100, "filled": 70, "partial_fills": 12},
        }
        view = diagnostics.train_view(result)
        self.assertEqual(view["summary"]["t_daily"], -.6)
        self.assertEqual(view["summary"]["mean_return_on_max_loss_daily"], -.005)
        self.assertEqual(view["summary"]["sharpe_daily"], -.04)
        self.assertEqual(view["fills"]["partial_fills"], 12)
        # The compact feedback may still carry per-trade diagnostics with their explicit names.
        self.assertEqual(view["summary"]["t_stat"], 9)
