"""The swarm's evidence lines (league/swarm/evidence.py): exactly the plan's, each check able to fail on its own."""

from __future__ import annotations

import random
import unittest

from league.swarm import evidence as E
from league.tests.swarm_fakes import result, summary


def good(**kw):
    daily = kw.pop("daily", None)
    if daily is None:
        rng = random.Random(3)
        daily = [rng.gauss(4.0, 10.0) for _ in range(250)]
    r = result("p", daily=daily, **kw)
    return r


class ValidationLine(unittest.TestCase):
    def line(self, r, stressed=None, trials=5, sharpes=(0.0, 0.05, -0.05)):
        stressed = stressed if stressed is not None else {"summary": {"pnl": 100.0}}
        return E.validation_line(r, stressed, lineage_trials=trials, trial_sharpes=list(sharpes))

    def test_a_strong_result_meets_every_check(self):
        out = self.line(good())
        self.assertTrue(out["passed"], out)
        self.assertEqual(set(out["checks"]), {"status_ok", "trades", "days", "mean_positive", "t", "dsr", "quarters", "stress"})

    def test_each_check_fails_alone(self):
        cases = {
            "trades": dict(trades=99),
            "days": dict(days=59),
            "mean_positive": dict(mean=-0.01),
            "t": dict(t=1.99),
            "quarters": dict(quarters="2/4"),
        }
        for check, kw in cases.items():
            out = self.line(good(**kw))
            self.assertFalse(out["passed"], check)
            self.assertFalse(out["checks"][check], check)
            others = {k: v for k, v in out["checks"].items() if k != check}
            self.assertTrue(all(others.values()), (check, others))

    def test_the_stress_run_must_stay_positive(self):
        out = self.line(good(), stressed={"summary": {"pnl": -1.0}})
        self.assertEqual([k for k, v in out["checks"].items() if not v], ["stress"])
        self.assertFalse(self.line(good(), stressed={})["checks"]["stress"], "no stress run is no pass")

    def test_the_deflated_sharpe_charges_for_the_lineages_trials(self):
        rng = random.Random(9)
        daily = [rng.gauss(1.0, 10.0) for _ in range(250)]  # a thin edge
        few = self.line(good(daily=daily), trials=2, sharpes=[0.0, 0.01])
        many = self.line(good(daily=daily), trials=20000, sharpes=[rng.gauss(0, 0.08) for _ in range(500)])
        self.assertGreater(few["numbers"]["dsr"], many["numbers"]["dsr"])
        self.assertFalse(many["checks"]["dsr"])

    def test_the_t_is_the_daily_one_never_the_per_trade_one(self):
        r = good(t=1.2)
        r["summary"]["t_stat"] = 9.0  # correlated intraday entries inflate a per-trade t
        self.assertFalse(self.line(r)["checks"]["t"])
        del r["summary"]["t_daily"]
        self.assertFalse(self.line(r)["checks"]["t"], "no daily t, no pass")

    def test_a_summary_only_view_is_judged_with_conservative_moments(self):
        r = good()
        view = {k: r[k] for k in ("status", "summary")}  # the Gym's validation view: no daily series, no trades
        view["summary"] = {**r["summary"], "sharpe_daily": 0.35, "days": 250}
        out = self.line(view)
        self.assertTrue(out["checks"]["dsr"], out)
        normal = self.line({**view, "summary": {**view["summary"], "skew_daily": 0.0, "kurt_daily": 3.0}})
        self.assertGreaterEqual(normal["numbers"]["dsr"], out["numbers"]["dsr"], "missing moments never flatter")
        self.assertFalse(self.line({**view, "summary": {**view["summary"], "sharpe_daily": 0.02}})["checks"]["dsr"])

    def test_a_disqualified_run_never_passes(self):
        self.assertFalse(self.line(good(status="disqualified"))["passed"])


class HoldoutLine(unittest.TestCase):
    def test_bootstrap_is_deterministic_and_one_sided(self):
        xs = [5.0 + (i % 7) - 3 for i in range(120)]
        a, b = E.block_bootstrap(xs, seed="x"), E.block_bootstrap(xs, seed="x")
        self.assertEqual(a, b)
        self.assertGreater(a["lcb95"], 0)
        neg = E.block_bootstrap([-x for x in xs], seed="x")
        self.assertLess(neg["lcb95"], 0)
        self.assertGreater(neg["p"], 0.9)
        self.assertIsNone(E.block_bootstrap([1.0], seed="x"))

    def test_holm_steps_down_across_every_look(self):
        self.assertTrue(E.holm_passes(0.01, [])[0])
        self.assertFalse(E.holm_passes(0.06, [])[0])
        # Ten earlier looks with large p: the new small one faces alpha / 11 as the smallest.
        ok, threshold = E.holm_passes(0.004, [0.5] * 10)
        self.assertTrue(ok)
        self.assertAlmostEqual(threshold, 0.05 / 11)
        self.assertFalse(E.holm_passes(0.006, [0.5] * 10)[0])
        # The step-down stops at the first rank that fails: a later small p cannot pass behind it.
        self.assertFalse(E.holm_passes(0.02, [0.02, 0.6])[0])

    def test_the_line_needs_pnl_bootstrap_holm_and_half_the_validation_sharpe(self):
        rng = random.Random(4)
        daily = [rng.gauss(6.0, 10.0) for _ in range(180)]
        r = result("h", daily=daily, pnl=sum(daily))
        out = E.holdout_line(r, validation_sharpe=0.3, previous_ps=[], seed="s")
        self.assertTrue(out["passed"], out)
        self.assertFalse(E.holdout_line(r, validation_sharpe=5.0, previous_ps=[], seed="s")["checks"]["sharpe"])
        self.assertFalse(E.holdout_line(r, validation_sharpe=0.3, previous_ps=[0.001] * 3 + [0.9] * 200, seed="s")["passed"])
        losing = result("h", daily=[-x for x in daily], pnl=-sum(daily))
        self.assertFalse(E.holdout_line(losing, validation_sharpe=0.3, previous_ps=[], seed="s")["passed"])

    def test_the_leakage_alarm(self):
        self.assertFalse(E.leakage_alarm(9, 9))
        self.assertFalse(E.leakage_alarm(10, 3))
        self.assertTrue(E.leakage_alarm(10, 4))


class Forward(unittest.TestCase):
    def test_sized_needs_twenty_trades_a_positive_mean_and_bound(self):
        good = [{"pnl": 10.0 if i % 4 else -5.0, "max_loss": 100.0} for i in range(24)]
        self.assertTrue(E.forward_record(good)["sized"])
        self.assertFalse(E.forward_record(good[:19])["sized"])
        bad = [{"pnl": -3.0, "max_loss": 100.0} for _ in range(20)]
        self.assertTrue(E.forward_record(bad)["negative"])
        self.assertFalse(E.forward_record(bad[:19])["negative"])


class Bandit(unittest.TestCase):
    def test_shares_sum_to_one_and_new_families_get_a_quarter(self):
        fams = [{"id": f"old{i}", "validations": 3, "mean": 0.01 * i, "t": 1.0 + i} for i in range(6)]
        fams += [{"id": f"new{i}", "validations": 0, "mean": None, "t": None} for i in range(3)]
        shares = E.thompson(fams, rng=random.Random(1))
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertAlmostEqual(sum(v for k, v in shares.items() if k.startswith("new")), 0.25)

    def test_better_evidence_wins_more_often(self):
        fams = [{"id": "strong", "validations": 5, "mean": 0.08, "t": 4.0}, {"id": "weak", "validations": 5, "mean": -0.02, "t": -1.0}]
        wins = sum(E.thompson(fams, rng=random.Random(s))["strong"] > 0.5 for s in range(200))
        self.assertGreater(wins, 190)

    def test_only_new_families_take_everything(self):
        shares = E.thompson([{"id": "a", "validations": 0}, {"id": "b", "validations": 0}], rng=random.Random(2))
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertEqual(E.thompson([]), {})


class Score(unittest.TestCase):
    def test_score_is_the_t_above_a_minimum_of_trades(self):
        self.assertEqual(E.score(summary(trades=40, t=1.5)), 1.5)
        self.assertIsNone(E.score(summary(trades=10, t=9.0)))
        self.assertIsNone(E.score(None))


if __name__ == "__main__":
    unittest.main()
