"""The swarm's evidence lines (league/swarm/evidence.py): the plan's as the owner's decision D2 amended them (Sept 26),
each check able to fail on its own; and the robust Train objective."""

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
    def line(self, r, stressed=None, versions=1, sharpes=()):
        stressed = stressed if stressed is not None else {"summary": {"pnl": 100.0}}
        return E.validation_line(r, stressed, validated_versions=versions, version_sharpes=list(sharpes), lineage_trials=700)

    def test_d2_frequency_is_fifty_trades_on_twenty_five_days(self):
        self.assertEqual((E.MIN_TRADES, E.MIN_DAYS), (50, 25))
        self.assertTrue(self.line(good(trades=50, days=25, t=3.0))["checks"]["trades"])
        self.assertTrue(self.line(good(trades=50, days=25, t=3.0))["checks"]["days"])

    def test_a_strong_result_meets_every_check(self):
        out = self.line(good())
        self.assertTrue(out["passed"], out)
        self.assertEqual(set(out["checks"]), {"status_ok", "trades", "days", "mean_positive", "t", "dsr", "quarters", "stress"})

    def test_each_check_fails_alone(self):
        cases = {
            "trades": dict(trades=49),
            "days": dict(days=24),
            "mean_positive": dict(mean=-0.01),
            "t": dict(t=1.64),  # FAST LANE V2: the t line is 1.65
            "quarters": dict(quarters="1/4"),  # FAST LANE V2: 2 of 4 quarters
        }
        # FAST LANE V2: with N = 1 the deflated Sharpe is the probabilistic Sharpe against 0, a moments-adjusted t of
        # about 1.645 that is never above the t itself: a t under the line fails it too.
        along = {"t": {"dsr"}}
        for check, kw in cases.items():
            out = self.line(good(**kw))
            self.assertFalse(out["passed"], check)
            self.assertFalse(out["checks"][check], check)
            others = {k: v for k, v in out["checks"].items() if k != check and k not in along.get(check, ())}
            self.assertTrue(all(others.values()), (check, others))

    def test_fast_lane_v2_the_line_is_t_1_65_and_two_of_four_quarters(self):
        self.assertEqual((E.MIN_T, E.MIN_QUARTERS_POSITIVE, E.MIN_DSR), (1.65, 2, 0.95))
        edge = self.line(good(t=1.65, quarters="2/4", trades=400, days=200))
        self.assertTrue(edge["checks"]["t"] and edge["checks"]["quarters"], edge)
        self.assertFalse(self.line(good(t=1.64, quarters="2/4", trades=400, days=200))["checks"]["t"])

    def test_the_stress_run_must_stay_positive(self):
        out = self.line(good(), stressed={"summary": {"pnl": -1.0}})
        self.assertEqual([k for k, v in out["checks"].items() if not v], ["stress"])
        self.assertFalse(self.line(good(), stressed={})["checks"]["stress"], "no stress run is no pass")

    def test_the_deflated_sharpe_charges_for_the_lineages_validated_versions_not_its_trials(self):
        few = self.line(good(t=2.6), versions=1)
        many = self.line(good(t=2.6), versions=200, sharpes=[0.01 * (i % 21 - 10) for i in range(200)])
        self.assertTrue(few["checks"]["dsr"], few["numbers"])
        self.assertGreater(few["numbers"]["dsr"], many["numbers"]["dsr"])
        self.assertFalse(many["checks"]["dsr"])
        self.assertEqual((few["numbers"]["validated_versions"], few["numbers"]["lineage_trials"]), (1, 700),
                         "the lineage's trials are recorded, not divided by")

    def test_the_deflated_sharpe_is_on_traded_days_so_a_sparse_mechanism_is_not_capped(self):
        # 30 traded days of 250 with a daily t of 3: the all-days Sharpe of such a series is capped near sqrt(f / (1 - f)).
        sparse = good(trades=60, days=30, t=3.0, sharpe_daily=0.03)
        out = self.line(sparse)
        self.assertAlmostEqual(out["numbers"]["sharpe_traded"], 3.0 / 30 ** 0.5)
        self.assertTrue(out["checks"]["dsr"], out["numbers"])
        self.assertAlmostEqual(E.traded_sharpe({"t_daily": 2.0, "days_traded": 16}), 0.5)
        self.assertIsNone(E.traded_sharpe({"t_daily": 2.0, "days_traded": 0}))

    def test_the_t_is_the_daily_one_never_the_per_trade_one(self):
        r = good(t=1.2)
        r["summary"]["t_stat"] = 9.0  # correlated intraday entries inflate a per-trade t
        self.assertFalse(self.line(r)["checks"]["t"])
        del r["summary"]["t_daily"]
        self.assertFalse(self.line(r)["checks"]["t"], "no daily t, no pass")

    def test_a_view_without_traded_day_moments_is_judged_with_conservative_ones(self):
        r = good(t=2.4)
        view = {k: r[k] for k in ("status", "summary")}  # the Gym's validation view: no daily series, no trades
        out = self.line(view)
        self.assertTrue(out["checks"]["dsr"], out)
        normal = self.line({**view, "summary": {**view["summary"], "skew_traded": 0.0, "kurt_traded": 3.0}})
        self.assertGreaterEqual(normal["numbers"]["dsr"], out["numbers"]["dsr"], "missing moments never flatter")
        self.assertFalse(self.line({**view, "summary": {**view["summary"], "t_daily": 0.5}})["checks"]["dsr"])

    def test_checks_passed_is_a_count_only(self):
        out = self.line(good(t=1.5, quarters="1/4"))
        self.assertEqual(E.checks_passed(out), (5, 8))  # t, the deflated Sharpe and the quarters fail
        self.assertEqual(E.checks_passed(None), (0, 0))

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

    def test_the_line_needs_pnl_a_flat_level_and_half_the_validation_sharpe(self):
        rng = random.Random(4)
        daily = [rng.gauss(6.0, 10.0) for _ in range(180)]
        r = result("h", daily=daily, pnl=sum(daily))
        out = E.holdout_line(r, validation_sharpe=0.3, previous_ps=[], seed="s")
        self.assertTrue(out["passed"], out)
        self.assertEqual(set(out["checks"]), {"status_ok", "pnl", "level", "sharpe"}, "no bootstrap or Holm check")
        self.assertEqual((out["numbers"]["level"], out["numbers"]["rule"], out["numbers"]["draws"]),
                         (E.LOOK_LEVEL, "flat", E.BOOTSTRAP_DRAWS))
        self.assertNotIn("holm_threshold", out["numbers"])
        self.assertNotIn("holm_reachable", out["numbers"])
        self.assertFalse(E.holdout_line(r, validation_sharpe=5.0, previous_ps=[], seed="s")["checks"]["sharpe"])
        losing = result("h", daily=[-x for x in daily], pnl=-sum(daily))
        self.assertFalse(E.holdout_line(losing, validation_sharpe=0.3, previous_ps=[], seed="s")["passed"])

    def test_the_look_is_flat_whatever_the_looks_before(self):
        rng = random.Random(8)
        modest_daily = [rng.gauss(1.0, 10.0) for _ in range(180)]
        modest = result("h", daily=modest_daily, pnl=sum(modest_daily))
        alone = E.holdout_line(modest, validation_sharpe=0.01, previous_ps=[], seed="s")
        many = E.holdout_line(modest, validation_sharpe=0.01, previous_ps=[0.001] * 3 + [0.9] * 200, seed="s")
        self.assertEqual(alone["p"], many["p"])
        self.assertEqual(alone["checks"], many["checks"], "no Holm: the 204th look faces the same level as the first")
        self.assertEqual((alone["numbers"]["looks_before"], many["numbers"]["looks_before"]), (0, 203))

    def test_the_level_check_is_the_bootstrap_p_at_the_level(self):
        rng = random.Random(4)
        daily = [rng.gauss(30.0, 5.0) for _ in range(150)]  # overwhelming: every resampled mean above zero
        r = result("h", daily=daily, pnl=sum(daily))
        out = E.holdout_line(r, validation_sharpe=0.3, previous_ps=[0.9] * 120, seed="s")
        self.assertTrue(out["checks"]["level"], out["numbers"])
        self.assertAlmostEqual(out["p"], 1.0 / (E.BOOTSTRAP_DRAWS + 1))
        strict = E.holdout_line(r, validation_sharpe=0.3, previous_ps=[], seed="s", level=0.0)
        self.assertFalse(strict["checks"]["level"], "the level is a keyword the benchmark may set")

    def test_the_contamination_tail_is_reported_and_never_a_check(self):
        rng = random.Random(5)
        days = [f"2026-{m:02d}-{d:02d}" for m in range(1, 10) for d in (5, 12, 19, 26)]
        values = [rng.gauss(8.0, 10.0) if day < E.CONTAMINATION_TAIL_FROM else -3.0 for day in days]
        r = result("h", daily=values, pnl=sum(values))
        r["daily"] = [[day, x, 0.0] for day, x in zip(days, values)]
        out = E.holdout_line(r, validation_sharpe=0.1, previous_ps=[], seed="s")
        tail = out["numbers"]["tail"]
        self.assertEqual((tail["from"], tail["days"]), ("2026-07-01", sum(1 for d in days if d >= "2026-07-01")))
        self.assertAlmostEqual(tail["pnl"], -3.0 * tail["days"])
        self.assertGreater(tail["p"], 0.9)
        self.assertTrue(out["passed"], "a losing tail never changes the verdict")
        self.assertNotIn("tail", out["checks"])

    def test_the_leakage_alarm(self):
        self.assertFalse(E.leakage_alarm(9, 9))
        self.assertFalse(E.leakage_alarm(10, 3))
        self.assertTrue(E.leakage_alarm(10, 4))


def rows(n, source="nightly", pnl=10.0, max_loss=100.0, version=None, day0=0):
    return [{"source": source, "day": f"d{day0 + i:03d}", "pnl": pnl if i % 4 else -pnl / 2, "max_loss": max_loss, "version": version}
            for i in range(n)]


class Forward(unittest.TestCase):
    """The forward record as the live path computes it (league/live/money.py, agreed through the main session)."""

    def test_sized_needs_twenty_trades_a_positive_mean_and_bound(self):
        good = rows(24)
        self.assertTrue(E.forward_record(good)["sized"])
        self.assertFalse(E.forward_record(good[:19])["sized"])
        bad = [{"source": "nightly", "day": f"d{i}", "pnl": -3.0, "max_loss": 100.0} for i in range(20)]
        self.assertTrue(E.forward_record(bad)["negative"])
        self.assertFalse(E.forward_record(bad[:19])["negative"])

    def test_one_source_a_market_day_real_then_shadow_then_nightly(self):
        same_days = rows(10, "nightly") + rows(10, "shadow")
        out = E.forward_record(same_days)
        self.assertEqual(out["trades"], 10, "the nightly replay and the shadow book of one day are one record")
        self.assertFalse(out["sized"])
        mixed = rows(3, "nightly") + [{"source": "real", "day": "d000", "pnl": -50.0, "max_loss": 100.0, "version": None}]
        out = E.forward_record(mixed)
        self.assertEqual(out["trades"], 3)
        self.assertEqual(out["pnl_usd"], -50.0 + 10.0 + 10.0, "day d000 is the real trade")

    def test_only_the_current_version_counts_once_rows_carry_versions(self):
        old = rows(22, "shadow", pnl=-4.0, version=3)
        new = rows(2, "nightly", pnl=10.5, version=7, day0=100)
        out = E.forward_record(old + new, version=7)
        self.assertEqual((out["trades"], out["negative"]), (2, False))
        legacy = rows(5, "shadow")  # no version on any row: they all count
        self.assertEqual(E.forward_record(legacy, version=7)["trades"], 5)

    def test_negative_is_on_the_mean_return_and_trades_without_a_max_loss_are_not_returns(self):
        rs = [{"source": "shadow", "day": f"d{i}", "pnl": 1.0 if i else -100.0, "max_loss": 100.0} for i in range(20)]
        self.assertTrue(E.forward_record(rs)["negative"], "mean return below zero, though most trades won")
        free = [{"source": "shadow", "day": f"d{i}", "pnl": 5.0, "max_loss": 0.0} for i in range(18)]
        free += [{"source": "real", "day": f"r{i}", "pnl": 5.0 + i, "max_loss": 100.0} for i in range(2)]
        out = E.forward_record(free)
        self.assertEqual(out["trades"], 2)
        self.assertFalse(out["sized"], "two returns are not twenty")

    def test_ten_losing_real_trades_are_real_bad(self):
        out = E.forward_record(rows(15, "shadow", day0=0) + [{"source": "real", "day": f"r{i}", "pnl": -1.0, "max_loss": 100.0}
                                                              for i in range(10)])
        self.assertTrue(out["real_bad"])
        self.assertFalse(E.forward_record(rows(15, "shadow"))["real_bad"])


class Bandit(unittest.TestCase):
    def test_shares_sum_to_one_and_the_explore_pool_gets_a_quarter(self):
        fams = [{"id": f"old{i}", "validations": 3, "mean": 0.01 * i, "t": 1.0 + i} for i in range(6)]
        fams += [{"id": f"new{i}", "validations": 0, "mean": None, "t": None} for i in range(3)]
        shares = E.thompson(fams, rng=random.Random(1))
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        # R11-5: old0's mean is 0, so it explores with the new families; five positive old families leave the floor at 25%.
        self.assertAlmostEqual(sum(v for k, v in shares.items() if k.startswith("new") or k == "old0"), 0.25)

    def test_better_evidence_wins_more_often(self):
        fams = [{"id": "strong", "validations": 5, "mean": 0.08, "t": 4.0}, {"id": "weak", "validations": 5, "mean": 0.005, "t": 0.3}]
        wins = sum(E.thompson(fams, rng=random.Random(s))["strong"] > 0.5 for s in range(200))
        self.assertGreater(wins, 190)

    def test_only_new_families_take_everything(self):
        shares = E.thompson([{"id": "a", "validations": 0}, {"id": "b", "validations": 0}], rng=random.Random(2))
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertEqual(E.thompson([]), {})


def yearly(t=(2.0, 3.0, 2.5), trades=(60, 60, 60), days=(30, 30, 30), quarters="12/12", status="ok"):
    """A Train result with the Gym's per-year block (2022-2024)."""
    by_year = {str(2022 + i): {"trades": trades[i], "days": 252, "days_traded": days[i], "pnl": 10.0 * t[i] if t[i] is not None else 0.0,
                                "t_daily": t[i], "mean_return_on_max_loss_daily": 0.01, "quarters_positive": "4/4"} for i in range(3)}
    return {"status": status, "summary": {**summary(trades=sum(trades), t=4.0, quarters=quarters)}, "by_year": by_year}


class TrainScore(unittest.TestCase):
    def test_the_score_is_the_worst_year_times_the_share_of_quarters_positive(self):
        out = E.train_score(yearly(quarters="9/12"))
        self.assertTrue(out["eligible"], out)
        self.assertEqual((out["score"], out["worst_year"]), (2.0 * 0.75, "2022"))
        self.assertEqual(set(out["years"]), {"2022", "2023", "2024"})

    def test_a_losing_worst_year_is_never_flattered_by_fewer_positive_quarters(self):
        few = E.train_score(yearly(t=(-2.0, 3.0, 3.0), quarters="3/12"))["score"]
        more = E.train_score(yearly(t=(-2.0, 3.0, 3.0), quarters="9/12"))["score"]
        self.assertLess(few, more)
        self.assertLess(more, 0)

    def test_every_train_year_needs_forty_trades_on_twenty_days(self):
        self.assertEqual((E.TRAIN_YEAR_MIN_TRADES, E.TRAIN_YEAR_MIN_DAYS), (40, 20))
        for kw in (dict(trades=(60, 39, 60)), dict(days=(30, 30, 19))):
            out = E.train_score(yearly(**kw))
            self.assertFalse(out["eligible"], kw)
            self.assertIsNotNone(out["score"], "the score is still shown")
            self.assertIn("every Train year", out["why"])
        self.assertTrue(E.train_score(yearly(trades=(40, 40, 40), days=(20, 20, 20)))["eligible"])

    def test_a_year_without_a_t_or_a_failed_run_has_no_score(self):
        self.assertIsNone(E.train_score(yearly(t=(2.0, None, 2.0)))["score"])
        self.assertFalse(E.train_score(yearly(status="disqualified"))["eligible"])
        self.assertFalse(E.train_score({"status": "ok", "summary": summary()})["eligible"], "no per-year rows, no eligibility")

    def test_a_sparse_full_window_t_no_longer_wins(self):
        # The old score: one strong year's filter showed a high full-window t on few trades.
        sparse = E.train_score(yearly(t=(9.0, 0.2, 0.1), trades=(80, 12, 10), days=(40, 8, 6)))
        steady = E.train_score(yearly(t=(1.5, 1.6, 1.4)))
        self.assertFalse(sparse["eligible"])
        self.assertTrue(steady["eligible"])

    def test_years_come_from_the_trades_when_the_gym_sent_no_block(self):
        daily = [[f"{y}-0{m}-1{d}", 1.0, 0.0] for y in (2023, 2024) for m in (1, 4, 7) for d in range(3)]
        trades = [{"day": row[0], "pnl": 2.0 if i % 3 else -1.0, "max_loss": 50.0} for i, row in enumerate(daily)]
        years = E.years_of({"daily": daily, "trades": trades})
        self.assertEqual(set(years), {"2023", "2024"})
        self.assertEqual((years["2023"]["trades"], years["2023"]["days_traded"]), (9, 9))


if __name__ == "__main__":
    unittest.main()
